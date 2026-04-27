import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np

from utils.helpers import _normalize, now_vn, now_vn_iso, today_vn, fmt_vn
from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches


def module_nhap_hang():
    st.markdown("### 📥 Nhập/Trả hàng NCC")
    active = get_active_branch()
    user   = get_user() or {}
    ho_ten = user.get("ho_ten", user.get("username", ""))

    def _fmt(v): return f"{int(v):,}".replace(",", ".")

    # ── Helpers dùng chung ──
    @st.cache_data(ttl=60)
    def _load_ncc() -> pd.DataFrame:
        try:
            res = supabase.table("nha_cung_cap").select("*") \
                .eq("active", True).order("ten_ncc").execute()
            return pd.DataFrame(res.data) if res.data else pd.DataFrame()
        except Exception: return pd.DataFrame()

    def _gen_ma_pnh() -> str:
        try:
            res = supabase.rpc("get_next_pnh_num", {}).execute()
            data = res.data
            num = int(data[0] if isinstance(data, list) else data) if data else 1
            return f"PNH{num:06d}"
        except Exception:
            return f"PNH{now_vn().strftime('%y%m%d%H%M')}"

    def _gen_ma_th() -> str:
        try:
            res = supabase.rpc("get_next_th_num", {}).execute()
            data = res.data
            num = int(data[0] if isinstance(data, list) else data) if data else 1
            return f"TH{num:06d}"
        except Exception:
            return f"TH{now_vn().strftime('%y%m%d%H%M')}"

    # ── Tabs chính ──
    main_tabs = ["📦 Nhập hàng", "↩️ Trả hàng NCC"]
    if is_admin():
        main_tabs.append("🏭 Nhà cung cấp")
    tab_nhap, tab_tra, *rest = st.tabs(main_tabs)
    tab_ncc = rest[0] if rest else None

    # ══════════════════════════════════════════
    # TAB CHÍNH 1 — NHẬP HÀNG
    # ══════════════════════════════════════════
    with tab_nhap:
        sub_ds, sub_tao, sub_dt = st.tabs(
            ["Danh sách phiếu", "Tạo phiếu nhập", "Chi tiết / Duyệt"]
        )

        TRANG_THAI_PNH = ["Nháp", "Chờ xác nhận", "Đã nhập kho", "Đã hủy"]

        @st.cache_data(ttl=60)
        def _load_phieu_nhap(cn: str) -> pd.DataFrame:
            try:
                res = supabase.table("phieu_nhap_hang").select("*") \
                    .eq("chi_nhanh", cn).order("created_at", desc=True).execute()
                return pd.DataFrame(res.data) if res.data else pd.DataFrame()
            except Exception: return pd.DataFrame()

        def _load_ct_nhap(ma: str) -> pd.DataFrame:
            try:
                res = supabase.table("phieu_nhap_hang_ct").select("*") \
                    .eq("ma_phieu", ma).execute()
                if not res.data: return pd.DataFrame()
                df = pd.DataFrame(res.data)
                for c in ["so_luong", "gia_von", "gia_ban_moi", "gia_ban_cu"]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
                return df
            except Exception: return pd.DataFrame()

        # ── Sub-tab: Danh sách ──
        with sub_ds:
            tt_f = st.selectbox("Trạng thái:", ["Tất cả"] + TRANG_THAI_PNH,
                                key="pnh_tt_filter")
            df_ds = _load_phieu_nhap(active)
            if not df_ds.empty and tt_f != "Tất cả":
                df_ds = df_ds[df_ds["trang_thai"] == tt_f]
            if df_ds.empty:
                st.info("Chưa có phiếu nhập nào.")
            else:
                view = df_ds.rename(columns={
                    "ma_phieu": "Mã Phiếu", "ten_ncc": "NCC",
                    "trang_thai": "Trạng Thái", "created_by": "Người Tạo",
                    "confirmed_by": "Người Duyệt", "chi_nhanh": "Chi Nhánh"
                })
                cols = ["Mã Phiếu", "NCC", "Chi Nhánh", "Trạng Thái",
                        "Người Tạo", "Người Duyệt"]
                cols = [c for c in cols if c in view.columns]
                st.dataframe(view[cols], use_container_width=True,
                             hide_index=True, height=300)
                st.caption(f"Tổng: {len(df_ds)} phiếu")

                # Xem chi tiết
                st.markdown("---")
                st.caption("📋 Xem chi tiết hàng hóa của một phiếu:")
                ma_opts_ds = view["Mã Phiếu"].tolist()
                picked_ds = st.selectbox("Chọn phiếu:", ["-- Chọn --"] + ma_opts_ds,
                                         key="pnh_ds_detail_pick")
                if picked_ds != "-- Chọn --":
                    ct_ds = _load_ct_nhap(picked_ds)
                    if ct_ds.empty:
                        st.info("Phiếu này chưa có hàng hóa.")
                    else:
                        ct_ds_view = ct_ds.copy()
                        ct_ds_view["Đổi giá"] = ct_ds_view.apply(
                            lambda r: f"{_fmt(r['gia_ban_cu'])} → {_fmt(r['gia_ban_moi'])}"
                            if pd.notna(r.get("gia_ban_cu")) and
                               r["gia_ban_moi"] != r["gia_ban_cu"] else "", axis=1)
                        cols_v = ["ma_hang", "ten_hang", "so_luong",
                                  "gia_von", "gia_ban_moi", "Đổi giá"]
                        rename_v = {"ma_hang": "Mã", "ten_hang": "Tên",
                                    "so_luong": "SL", "gia_von": "Giá vốn",
                                    "gia_ban_moi": "Giá bán mới"}
                        ct_ds_view = ct_ds_view[
                            [c for c in cols_v if c in ct_ds_view.columns]
                        ].rename(columns=rename_v)
                        st.dataframe(ct_ds_view, use_container_width=True, hide_index=True)
                        tong_von_ds = int((ct_ds["so_luong"] * ct_ds["gia_von"]).sum())
                        st.metric("Tổng giá vốn", f"{_fmt(tong_von_ds)}đ")

        # ── Sub-tab: Tạo phiếu ──
        with sub_tao:
            if not is_ke_toan_or_admin():
                st.info("Chỉ kế toán và admin được tạo phiếu nhập.")
            else:
                cnt = st.session_state.get("pnh_cnt", 0)
                st.info(f"Chi nhánh: **{active}**")

                df_ncc = _load_ncc()
                if df_ncc.empty:
                    st.warning("Chưa có NCC nào. Admin thêm NCC ở tab Nhà cung cấp trước.")
                else:
                    ncc_opts = {"-- Chọn NCC --": ("", "")}
                    for _, r in df_ncc.iterrows():
                        ncc_opts[f"{r['ma_ncc']} — {r['ten_ncc']}"] = (r["ma_ncc"], r["ten_ncc"])
                    ncc_label = st.selectbox("Nhà cung cấp: *", list(ncc_opts.keys()),
                                             key=f"pnh_ncc_{cnt}")
                    ma_ncc, ten_ncc = ncc_opts[ncc_label]

                    ghi_chu = st.text_area("Ghi chú:", key=f"pnh_gc_{cnt}",
                                           placeholder="Số hóa đơn NCC, ghi chú giao hàng...")

                    st.markdown("**Danh sách hàng nhập:**")
                    items_key = f"pnh_items_{cnt}"
                    st.session_state.setdefault(items_key, [])

                    with st.expander(
                        f"➕ Thêm sản phẩm ({len(st.session_state[items_key])} mục)",
                        expanded=True
                    ):
                        hh = load_hang_hoa()
                        ma_tim = st.text_input("Tìm mã / tên hàng:", key=f"pnh_tim_{cnt}",
                                               placeholder="Nhập mã hoặc tên...")
                        hits = pd.DataFrame()
                        if ma_tim.strip() and not hh.empty:
                            s = ma_tim.strip().lower().replace(" ", "")
                            def _fz(v): v2 = str(v).lower(); return s in v2 or s in v2.replace(" ", "")
                            hits = hh[hh["ma_hang"].apply(_fz) | hh["ten_hang"].apply(_fz)].head(6)

                        if not hits.empty:
                            hh1, hh2, hh3, hh4, hh5 = st.columns([3, 1, 2, 2, 1])
                            with hh2: st.markdown("**Số lượng**")
                            with hh3: st.markdown("**Giá vốn**")
                            with hh4: st.markdown("**Giá bán**")
                            for _, r in hits.iterrows():
                                gb_cu = int(r.get("gia_ban", 0))
                                h1, h2, h3, h4, h5 = st.columns([3, 1, 2, 2, 1])
                                with h1: st.markdown(f"**{r['ma_hang']}** — {r['ten_hang']}")
                                with h2: sl = st.number_input("SL", min_value=1, value=1,
                                    key=f"pnh_sl_{cnt}_{r['ma_hang']}", label_visibility="collapsed")
                                with h3: gv = st.number_input("Giá vốn", min_value=0, step=1000,
                                    value=0, key=f"pnh_gv_{cnt}_{r['ma_hang']}", label_visibility="collapsed")
                                with h4: gb = st.number_input("Giá bán", min_value=0, step=1000,
                                    value=gb_cu, key=f"pnh_gb_{cnt}_{r['ma_hang']}", label_visibility="collapsed")
                                with h5:
                                    if st.button("➕", key=f"pnh_add_{cnt}_{r['ma_hang']}"):
                                        mh_str = str(r["ma_hang"])
                                        existing = st.session_state.get(items_key, [])
                                        found = False
                                        for item in existing:
                                            if item["ma_hang"] == mh_str:
                                                item["so_luong"]    += int(sl)
                                                item["gia_von"]      = int(gv)
                                                item["gia_ban_moi"]  = int(gb)
                                                item["doi_gia"]      = gb != gb_cu
                                                found = True
                                                break
                                        if not found:
                                            st.session_state[items_key].append({
                                                "ma_hang":    mh_str,
                                                "ten_hang":   str(r["ten_hang"]),
                                                "so_luong":   int(sl),
                                                "gia_von":    int(gv),
                                                "gia_ban_moi":int(gb),
                                                "gia_ban_cu": gb_cu,
                                                "doi_gia":    gb != gb_cu,
                                            })
                                        st.rerun()
                        elif ma_tim.strip():
                            st.caption("Không tìm thấy — tạo mã mới:")
                            n1, n2, n3 = st.columns([2, 2, 2])
                            with n1: new_ma   = st.text_input("Mã hàng:", key=f"pnh_new_ma_{cnt}")
                            with n2: new_vach = st.text_input("Mã vạch:", key=f"pnh_new_vach_{cnt}")
                            with n3: new_ten  = st.text_input("Tên hàng:", key=f"pnh_new_ten_{cnt}")
                            hh_master = load_hang_hoa()
                            loai_opts = sorted(hh_master["loai_hang"].dropna().unique().tolist()) \
                                if "loai_hang" in hh_master.columns else []
                            n4, n5 = st.columns(2)
                            with n4:
                                loai_new = st.selectbox("Loại hàng:",
                                    ["-- Chọn --"] + loai_opts + ["(Nhập mới)"],
                                    key=f"pnh_new_loai_{cnt}")
                                if loai_new == "(Nhập mới)":
                                    loai_new = st.text_input("Tên loại mới:", key=f"pnh_new_loai_txt_{cnt}")
                                elif loai_new == "-- Chọn --":
                                    loai_new = ""
                            with n5:
                                th_opts = []
                                if loai_new and "thuong_hieu" in hh_master.columns:
                                    th_opts = sorted(hh_master[hh_master["loai_hang"] == loai_new][
                                        "thuong_hieu"].dropna().unique().tolist())
                                th_new = st.selectbox("Thương hiệu:",
                                    ["-- Chọn --"] + th_opts + ["(Nhập mới)"],
                                    key=f"pnh_new_th_{cnt}")
                                if th_new == "(Nhập mới)":
                                    th_new = st.text_input("Tên thương hiệu mới:", key=f"pnh_new_th_txt_{cnt}")
                                elif th_new == "-- Chọn --":
                                    th_new = ""
                            n6, n7, n8 = st.columns(3)
                            with n6: new_gv = st.number_input("Giá vốn:", min_value=0, step=1000, key=f"pnh_new_gv_{cnt}")
                            with n7: new_gb = st.number_input("Giá bán:", min_value=0, step=1000, key=f"pnh_new_gb_{cnt}")
                            with n8: new_sl = st.number_input("Số lượng:", min_value=1, value=1, key=f"pnh_new_sl_{cnt}")
                            if st.button("➕ Thêm mới", key=f"pnh_new_add_{cnt}") and new_ma.strip() and new_ten.strip():
                                st.session_state[items_key].append({
                                    "ma_hang":     new_ma.strip().upper(),
                                    "ma_vach":     new_vach.strip() or None,
                                    "ten_hang":    new_ten.strip(),
                                    "loai_hang":   loai_new or None,
                                    "thuong_hieu": th_new or None,
                                    "so_luong":    int(new_sl),
                                    "gia_von":     int(new_gv),
                                    "gia_ban_moi": int(new_gb),
                                    "gia_ban_cu":  None,
                                    "doi_gia":     False,
                                    "_is_new":     True,
                                })
                                st.rerun()

                    # Giỏ hàng
                    items = st.session_state.get(items_key, [])
                    if items:
                        st.markdown("---")
                        hdr = st.columns([3, 1, 2, 2, 1, 1])
                        for lbl, col in zip(["Tên hàng", "SL", "Giá vốn", "Giá bán", "⚠️", ""], hdr):
                            col.caption(lbl)
                        doi_gia_list = []
                        for i, item in enumerate(items):
                            c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 2, 2, 1, 1])
                            label = f"{'🆕 ' if item.get('_is_new') else ''}{item['ma_hang']} — {item['ten_hang']}"
                            with c1: st.markdown(f"<span style='font-size:0.88rem'>{label}</span>", unsafe_allow_html=True)
                            with c2: st.markdown(f"<span style='font-size:0.88rem'>x{item['so_luong']}</span>", unsafe_allow_html=True)
                            with c3: st.markdown(f"<span style='font-size:0.88rem'>{_fmt(item['gia_von'])}đ</span>", unsafe_allow_html=True)
                            with c4: st.markdown(f"<span style='font-size:0.88rem'>{_fmt(item['gia_ban_moi'])}đ</span>", unsafe_allow_html=True)
                            with c5:
                                if item.get("doi_gia") and item.get("gia_ban_cu") is not None and not item.get("_is_new"):
                                    doi_gia_list.append(item)
                                    st.markdown("⚠️")
                            with c6:
                                if st.button("✕", key=f"pnh_del_{cnt}_{i}"):
                                    st.session_state[items_key].pop(i); st.rerun()

                        tong_sl  = sum(x["so_luong"] for x in items)
                        tong_von = sum(x["so_luong"] * x["gia_von"] for x in items)
                        tong_ban = sum(x["so_luong"] * x["gia_ban_moi"] for x in items)
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Tổng số lượng", f"{tong_sl:,}".replace(",", "."))
                        m2.metric("Tổng giá vốn", f"{_fmt(tong_von)}đ")
                        m3.metric("Tổng giá bán", f"{_fmt(tong_ban)}đ")

                        if doi_gia_list:
                            with st.expander(f"⚠️ {len(doi_gia_list)} mặt hàng thay đổi giá bán — cần in tem mới", expanded=True):
                                for x in doi_gia_list:
                                    st.caption(f"• {x['ma_hang']} {x['ten_hang']}: "
                                               f"{_fmt(x['gia_ban_cu'])}đ → **{_fmt(x['gia_ban_moi'])}đ**")

                    st.markdown("---")
                    can_save = bool(ma_ncc) and len(items) > 0
                    c_draft, c_submit = st.columns(2)
                    with c_draft:
                        if st.button("💾 Lưu nháp", use_container_width=True,
                                     disabled=not can_save, key="pnh_save_draft"):
                            try:
                                ma = _gen_ma_pnh()
                                supabase.table("phieu_nhap_hang").insert({
                                    "ma_phieu": ma, "ma_ncc": ma_ncc, "ten_ncc": ten_ncc,
                                    "chi_nhanh": active, "trang_thai": "Nháp",
                                    "ghi_chu": ghi_chu.strip() or None,
                                    "created_by": ho_ten,
                                    "created_at": now_vn_iso(),
                                    "updated_at": now_vn_iso(),
                                }).execute()
                                supabase.table("phieu_nhap_hang_ct").insert([
                                    {"ma_phieu": ma, "ma_hang": x["ma_hang"], "ten_hang": x["ten_hang"],
                                     "so_luong": x["so_luong"], "gia_von": x["gia_von"],
                                     "gia_ban_moi": x["gia_ban_moi"], "gia_ban_cu": x.get("gia_ban_cu"),
                                     "ma_vach": x.get("ma_vach"), "loai_hang": x.get("loai_hang"),
                                     "thuong_hieu": x.get("thuong_hieu")} for x in items
                                ]).execute()
                                st.session_state["pnh_cnt"] = cnt + 1
                                st.cache_data.clear()
                                log_action("PNH_DRAFT", f"ma={ma} ncc={ten_ncc}")
                                st.success(f"✓ Đã lưu nháp **{ma}**"); st.rerun()
                            except Exception as e: st.error(f"Lỗi: {e}")
                    with c_submit:
                        if st.button("📤 Gửi chờ xác nhận", type="primary",
                                     use_container_width=True, disabled=not can_save,
                                     key="pnh_submit"):
                            try:
                                ma = _gen_ma_pnh()
                                supabase.table("phieu_nhap_hang").insert({
                                    "ma_phieu": ma, "ma_ncc": ma_ncc, "ten_ncc": ten_ncc,
                                    "chi_nhanh": active, "trang_thai": "Chờ xác nhận",
                                    "ghi_chu": ghi_chu.strip() or None,
                                    "created_by": ho_ten,
                                    "created_at": now_vn_iso(),
                                    "updated_at": now_vn_iso(),
                                }).execute()
                                supabase.table("phieu_nhap_hang_ct").insert([
                                    {"ma_phieu": ma, "ma_hang": x["ma_hang"], "ten_hang": x["ten_hang"],
                                     "so_luong": x["so_luong"], "gia_von": x["gia_von"],
                                     "gia_ban_moi": x["gia_ban_moi"], "gia_ban_cu": x.get("gia_ban_cu"),
                                     "ma_vach": x.get("ma_vach"), "loai_hang": x.get("loai_hang"),
                                     "thuong_hieu": x.get("thuong_hieu")} for x in items
                                ]).execute()
                                st.session_state["pnh_cnt"] = cnt + 1
                                st.cache_data.clear()
                                log_action("PNH_SUBMIT", f"ma={ma} ncc={ten_ncc}")
                                st.success(f"✓ Đã gửi **{ma}** chờ admin xác nhận"); st.rerun()
                            except Exception as e: st.error(f"Lỗi: {e}")

        # ── Sub-tab: Chi tiết / Duyệt ──
        with sub_dt:
            df_all = _load_phieu_nhap(active)
            if df_all.empty:
                st.info("Chưa có phiếu nào.")
            else:
                search_pnh = st.text_input("Tìm mã phiếu / NCC:", key="pnh_search_dt",
                                           placeholder="PNH000001 hoặc tên NCC...")
                df_f = df_all.copy()
                if search_pnh.strip():
                    s = search_pnh.strip().lower()
                    df_f = df_f[df_f["ma_phieu"].str.lower().str.contains(s, na=False) |
                                df_f["ten_ncc"].astype(str).str.lower().str.contains(s, na=False)]

                if df_f.empty:
                    st.info("Không tìm thấy.")
                else:
                    opts = [f"{r['ma_phieu']} · {r.get('ten_ncc', '')} · {r.get('trang_thai', '')}"
                            for _, r in df_f.iterrows()]
                    picked = st.selectbox("Chọn phiếu:", opts, key="pnh_detail_pick")
                    ma_pick = picked.split(" · ")[0]
                    phieu = df_all[df_all["ma_phieu"] == ma_pick].iloc[0]
                    ct = _load_ct_nhap(ma_pick)
                    tt = phieu.get("trang_thai", "")

                    p1, p2, p3 = st.columns(3)
                    with p1:
                        st.markdown(f"**Mã phiếu:** {ma_pick}")
                        st.markdown(f"**NCC:** {phieu.get('ten_ncc', '—')}")
                    with p2:
                        st.markdown(f"**Chi nhánh:** {phieu.get('chi_nhanh', '')}")
                        st.markdown(f"**Người tạo:** {phieu.get('created_by', '—')}")
                    with p3:
                        st.markdown(f"**Trạng thái:** {tt}")
                        st.markdown(f"**Người duyệt:** {phieu.get('confirmed_by') or '—'}")
                    if phieu.get("ghi_chu"):
                        st.markdown(f"**Ghi chú:** {phieu.get('ghi_chu', '')}")

                    if not ct.empty:
                        st.markdown("---")
                        doi_gia = ct[
                            ct["gia_ban_cu"].notna() &
                            (ct["gia_ban_cu"] > 0) &
                            (ct["gia_ban_moi"] != ct["gia_ban_cu"])
                        ]
                        if not doi_gia.empty:
                            st.warning(f"⚠️ {len(doi_gia)} mặt hàng thay đổi giá bán — nhớ in tem mới.")
                        ct_view = ct.copy()
                        ct_view["Đổi giá"] = ct_view.apply(
                            lambda r: f"{_fmt(r['gia_ban_cu'])} → {_fmt(r['gia_ban_moi'])}"
                            if pd.notna(r.get("gia_ban_cu")) and r["gia_ban_moi"] != r["gia_ban_cu"] else "", axis=1)
                        cols_v = ["ma_hang", "ten_hang", "so_luong", "gia_von", "gia_ban_moi", "Đổi giá"]
                        rename_v = {"ma_hang": "Mã", "ten_hang": "Tên", "so_luong": "SL",
                                    "gia_von": "Giá vốn", "gia_ban_moi": "Giá bán mới"}
                        ct_view = ct_view[[c for c in cols_v if c in ct_view.columns]].rename(columns=rename_v)
                        st.dataframe(ct_view, use_container_width=True, hide_index=True)
                        tong_von = int((ct["so_luong"] * ct["gia_von"]).sum())
                        st.metric("Tổng giá vốn", f"{_fmt(tong_von)}đ")

                    st.markdown("---")

                    if tt == "Nháp" and is_ke_toan_or_admin():
                        if st.button("📤 Gửi chờ xác nhận", type="primary",
                                     use_container_width=True, key="pnh_to_cho"):
                            supabase.table("phieu_nhap_hang").update({
                                "trang_thai": "Chờ xác nhận",
                                "updated_at": now_vn_iso()
                            }).eq("ma_phieu", ma_pick).execute()
                            st.cache_data.clear(); st.success("✓ Đã gửi chờ xác nhận"); st.rerun()

                    if tt == "Chờ xác nhận" and is_admin():
                        st.info("Xác nhận phiếu sẽ cộng SL vào tồn kho và cập nhật giá bán.")
                        if st.button("✅ Xác nhận — Nhập kho", type="primary",
                                     use_container_width=True, key="pnh_confirm"):
                            try:
                                now_vn = now_vn_iso()
                                chi_nhanh = phieu.get("chi_nhanh", "")
                                ma_hangs  = ct["ma_hang"].astype(str).tolist()

                                kho_rows2, batch2, offset2 = [], 1000, 0
                                while True:
                                    r2 = supabase.table("the_kho").select("*") \
                                        .eq("Chi nhánh", chi_nhanh) \
                                        .range(offset2, offset2+batch2-1).execute()
                                    if not r2.data: break
                                    kho_rows2.extend(r2.data)
                                    if len(r2.data) < batch2: break
                                    offset2 += batch2
                                ma_hangs_set = {str(m).strip() for m in ma_hangs}
                                ma_key2 = next((k for k in (kho_rows2[0].keys() if kho_rows2 else [])
                                                if "m" in k.lower() and "h" in k.lower() and len(k) <= 8), "Mã hàng")
                                kho_map = {str(r.get(ma_key2, "")).strip(): r
                                           for r in kho_rows2
                                           if str(r.get(ma_key2, "")).strip() in ma_hangs_set}

                                hh_res = supabase.table("hang_hoa").select("ma_hang,gia_ban") \
                                    .in_("ma_hang", ma_hangs).execute()
                                hh_map = {r["ma_hang"]: r for r in (hh_res.data or [])}

                                kho_updates, kho_inserts = [], []
                                hh_updates, hh_inserts   = [], []

                                for _, r in ct.iterrows():
                                    mh     = str(r["ma_hang"])
                                    sl     = int(r["so_luong"])
                                    gb_moi = int(r["gia_ban_moi"])
                                    gb_cu  = r.get("gia_ban_cu")

                                    if mh in kho_map:
                                        cur = int(kho_map[mh].get("Tồn cuối kì") or 0)
                                        kho_updates.append({"id": kho_map[mh]["id"], "Tồn cuối kì": cur + sl})
                                    else:
                                        kho_inserts.append({"Mã hàng": mh, "Chi nhánh": chi_nhanh,
                                                            "Tên hàng": str(r["ten_hang"]),
                                                            "Tồn cuối kì": sl, "Tồn đầu kì": 0})

                                    if mh in hh_map:
                                        if gb_cu is not None and gb_moi != int(gb_cu or 0):
                                            hh_updates.append({"ma_hang": mh, "gia_ban": gb_moi})
                                    else:
                                        hh_inserts.append({
                                            "ma_hang":     mh, "ten_hang": str(r["ten_hang"]),
                                            "gia_ban":     gb_moi,
                                            "ma_vach":     str(r.get("ma_vach") or "") or None,
                                            "loai_hang":   str(r.get("loai_hang") or "") or None,
                                            "thuong_hieu": str(r.get("thuong_hieu") or "") or None,
                                        })

                                for u in kho_updates:
                                    supabase.table("the_kho").update({"Tồn cuối kì": u["Tồn cuối kì"]}) \
                                        .eq("id", u["id"]).execute()
                                if kho_inserts:
                                    supabase.table("the_kho").insert(kho_inserts).execute()
                                for u in hh_updates:
                                    supabase.table("hang_hoa").update({"gia_ban": u["gia_ban"]}) \
                                        .eq("ma_hang", u["ma_hang"]).execute()
                                if hh_inserts:
                                    supabase.table("hang_hoa").insert(hh_inserts).execute()

                                supabase.table("phieu_nhap_hang").update({
                                    "trang_thai": "Đã nhập kho", "confirmed_by": ho_ten,
                                    "confirmed_at": now_vn, "updated_at": now_vn,
                                }).eq("ma_phieu", ma_pick).execute()

                                st.cache_data.clear()
                                log_action("PNH_CONFIRM", f"ma={ma_pick} cn={chi_nhanh}")
                                st.success(f"✓ Đã nhập kho **{ma_pick}** — tồn kho đã cập nhật!")
                                st.rerun()
                            except Exception as e: st.error(f"Lỗi xác nhận: {e}")

                    if is_admin() and tt in ("Nháp", "Chờ xác nhận"):
                        st.markdown("---")
                        if st.button("🗑️ Hủy phiếu", type="secondary",
                                     use_container_width=True, key="pnh_cancel"):
                            supabase.table("phieu_nhap_hang").update({
                                "trang_thai": "Đã hủy",
                                "updated_at": now_vn_iso()
                            }).eq("ma_phieu", ma_pick).execute()
                            st.cache_data.clear()
                            log_action("PNH_CANCEL", f"ma={ma_pick}", level="warning")
                            st.success("Đã hủy phiếu."); st.rerun()

                    if is_admin() and tt == "Đã nhập kho":
                        st.markdown("---")
                        if st.button("↩️ Hoàn tác nhập kho", type="secondary",
                                     use_container_width=True, key="pnh_revert"):
                            try:
                                chi_nhanh    = phieu.get("chi_nhanh", "")
                                ma_hangs     = ct["ma_hang"].astype(str).str.strip().tolist()
                                ma_hangs_set = set(ma_hangs)
                                sl_map = {str(r["ma_hang"]).strip(): int(r["so_luong"])
                                          for _, r in ct.iterrows()}

                                kho_rows, batch, offset = [], 1000, 0
                                while True:
                                    r2 = supabase.table("the_kho").select("*") \
                                        .eq("Chi nhánh", chi_nhanh) \
                                        .range(offset, offset+batch-1).execute()
                                    if not r2.data: break
                                    kho_rows.extend(r2.data)
                                    if len(r2.data) < batch: break
                                    offset += batch

                                ma_key = next((k for k in (kho_rows[0].keys() if kho_rows else [])
                                               if "m" in k.lower() and "h" in k.lower() and len(k) <= 8), "Mã hàng")
                                kho_map = {str(r.get(ma_key, "")).strip(): r
                                           for r in kho_rows
                                           if str(r.get(ma_key, "")).strip() in ma_hangs_set}

                                for mh, kho_row in kho_map.items():
                                    sl  = sl_map.get(mh, 0)
                                    cur = int(kho_row.get("Tồn cuối kì") or 0)
                                    supabase.table("the_kho").update(
                                        {"Tồn cuối kì": max(0, cur - sl)}
                                    ).eq("id", kho_row["id"]).execute()

                                supabase.table("phieu_nhap_hang").update({
                                    "trang_thai": "Đã hủy",
                                    "updated_at": now_vn_iso()
                                }).eq("ma_phieu", ma_pick).execute()
                                st.cache_data.clear()
                                log_action("PNH_REVERT", f"ma={ma_pick}", level="warning")
                                st.success("✓ Đã hoàn tác — tồn kho trừ lại."); st.rerun()
                            except Exception as e: st.error(f"Lỗi hoàn tác: {e}")

    # ══════════════════════════════════════════
    # TAB CHÍNH 2 — TRẢ HÀNG NCC
    # ══════════════════════════════════════════
    with tab_tra:
        if not is_ke_toan_or_admin():
            st.info("Chỉ kế toán và admin được tạo phiếu trả hàng.")
        else:
            TRANG_THAI_TH = ["Nháp", "Chờ xác nhận", "Đã trả hàng", "Đã hủy"]

            def _load_phieu_tra(cn: str) -> pd.DataFrame:
                try:
                    res = supabase.table("phieu_tra_hang").select("*") \
                        .eq("chi_nhanh", cn).order("created_at", desc=True).execute()
                    return pd.DataFrame(res.data) if res.data else pd.DataFrame()
                except Exception: return pd.DataFrame()

            def _load_ct_tra(ma: str) -> pd.DataFrame:
                try:
                    res = supabase.table("phieu_tra_hang_ct").select("*") \
                        .eq("ma_phieu", ma).execute()
                    if not res.data: return pd.DataFrame()
                    df = pd.DataFrame(res.data)
                    for c in ["so_luong", "gia_tra"]:
                        if c in df.columns:
                            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
                    return df
                except Exception: return pd.DataFrame()

            sub_tra_ds, sub_tra_tao, sub_tra_dt = st.tabs(
                ["Danh sách phiếu trả", "Tạo phiếu trả", "Chi tiết / Duyệt"]
            )

            # ── Sub-tab: Danh sách phiếu trả ──
            with sub_tra_ds:
                tt_f_th = st.selectbox("Trạng thái:", ["Tất cả"] + TRANG_THAI_TH,
                                       key="th_tt_filter")
                df_tra = _load_phieu_tra(active)
                if not df_tra.empty and tt_f_th != "Tất cả":
                    df_tra = df_tra[df_tra["trang_thai"] == tt_f_th]
                if df_tra.empty:
                    st.info("Chưa có phiếu trả hàng nào.")
                else:
                    view_tra = df_tra.rename(columns={
                        "ma_phieu": "Mã Phiếu", "ten_ncc": "NCC",
                        "trang_thai": "Trạng Thái", "created_by": "Người Tạo",
                        "confirmed_by": "Người Duyệt", "chi_nhanh": "Chi Nhánh"
                    })
                    cols_tra = ["Mã Phiếu", "NCC", "Chi Nhánh", "Trạng Thái",
                                "Người Tạo", "Người Duyệt"]
                    cols_tra = [c for c in cols_tra if c in view_tra.columns]
                    st.dataframe(view_tra[cols_tra], use_container_width=True,
                                 hide_index=True, height=300)
                    st.caption(f"Tổng: {len(df_tra)} phiếu")

                    # Xem chi tiết
                    st.markdown("---")
                    st.caption("📋 Xem chi tiết hàng hóa của một phiếu:")
                    ma_opts_tra = view_tra["Mã Phiếu"].tolist()
                    picked_tra_ds = st.selectbox("Chọn phiếu:", ["-- Chọn --"] + ma_opts_tra,
                                                 key="th_ds_detail_pick")
                    if picked_tra_ds != "-- Chọn --":
                        ct_tra_ds = _load_ct_tra(picked_tra_ds)
                        if ct_tra_ds.empty:
                            st.info("Phiếu này chưa có hàng hóa.")
                        else:
                            ct_v = ct_tra_ds[["ma_hang", "ten_hang", "so_luong", "gia_tra"]].copy()
                            ct_v["thanh_tien"] = ct_v["so_luong"] * ct_v["gia_tra"]
                            ct_v = ct_v.rename(columns={
                                "ma_hang": "Mã", "ten_hang": "Tên",
                                "so_luong": "SL", "gia_tra": "Giá trả",
                                "thanh_tien": "Thành tiền"
                            })
                            st.dataframe(ct_v, use_container_width=True, hide_index=True)
                            tong_gt_ds = int((ct_tra_ds["so_luong"] * ct_tra_ds["gia_tra"]).sum())
                            st.metric("Tổng giá trị trả", f"{_fmt(tong_gt_ds)}đ")

            # ── Sub-tab: Tạo phiếu trả ──
            with sub_tra_tao:
                cnt_th = st.session_state.get("th_cnt", 0)
                st.info(f"Chi nhánh: **{active}**")

                df_ncc_th = _load_ncc()
                if df_ncc_th.empty:
                    st.warning("Chưa có NCC nào.")
                else:
                    ncc_opts_th = {"-- Chọn NCC --": ("", "")}
                    for _, r in df_ncc_th.iterrows():
                        ncc_opts_th[f"{r['ma_ncc']} — {r['ten_ncc']}"] = (r["ma_ncc"], r["ten_ncc"])
                    ncc_label_th = st.selectbox("Nhà cung cấp: *", list(ncc_opts_th.keys()),
                                                key=f"th_ncc_{cnt_th}")
                    ma_ncc_th, ten_ncc_th = ncc_opts_th[ncc_label_th]

                    ghi_chu_th = st.text_area("Ghi chú:", key=f"th_gc_{cnt_th}",
                                              placeholder="Lý do trả hàng, số biên bản...")

                    st.markdown("**Danh sách hàng trả:**")
                    items_key_th = f"th_items_{cnt_th}"
                    st.session_state.setdefault(items_key_th, [])

                    with st.expander(
                        f"➕ Thêm hàng trả ({len(st.session_state[items_key_th])} mục)",
                        expanded=True
                    ):
                        hh_th = load_hang_hoa()
                        ma_tim_th = st.text_input("Tìm mã / tên hàng:", key=f"th_tim_{cnt_th}",
                                                   placeholder="Nhập mã hoặc tên...")
                        hits_th = pd.DataFrame()
                        if ma_tim_th.strip() and not hh_th.empty:
                            s_th = ma_tim_th.strip().lower().replace(" ", "")
                            def _fz_th(v): v2 = str(v).lower(); return s_th in v2 or s_th in v2.replace(" ", "")
                            hits_th = hh_th[
                                hh_th["ma_hang"].apply(_fz_th) | hh_th["ten_hang"].apply(_fz_th)
                            ].head(6)

                        if not hits_th.empty:
                            h_l1, h_l2, h_l3, h_l4 = st.columns([3, 1, 2, 1])
                            with h_l2: st.markdown("**Số lượng**")
                            with h_l3: st.markdown("**Giá trả**")
                            for _, r in hits_th.iterrows():
                                c1, c2, c3, c4 = st.columns([3, 1, 2, 1])
                                with c1: st.markdown(f"**{r['ma_hang']}** — {r['ten_hang']}")
                                with c2:
                                    sl_th = st.number_input("SL", min_value=1, value=1,
                                        key=f"th_sl_{cnt_th}_{r['ma_hang']}", label_visibility="collapsed")
                                with c3:
                                    gia_th = st.number_input("Giá trả", min_value=0, step=1000,
                                        value=int(r.get("gia_ban", 0)),
                                        key=f"th_gia_{cnt_th}_{r['ma_hang']}", label_visibility="collapsed")
                                with c4:
                                    if st.button("➕", key=f"th_add_{cnt_th}_{r['ma_hang']}"):
                                        mh_str_th = str(r["ma_hang"])
                                        found_th = False
                                        for item in st.session_state[items_key_th]:
                                            if item["ma_hang"] == mh_str_th:
                                                item["so_luong"] += int(sl_th)
                                                item["gia_tra"]   = int(gia_th)
                                                found_th = True
                                                break
                                        if not found_th:
                                            st.session_state[items_key_th].append({
                                                "ma_hang":  mh_str_th,
                                                "ten_hang": str(r["ten_hang"]),
                                                "so_luong": int(sl_th),
                                                "gia_tra":  int(gia_th),
                                            })
                                        st.rerun()
                        elif ma_tim_th.strip():
                            st.caption("Không tìm thấy hàng hóa.")

                    items_th = st.session_state.get(items_key_th, [])
                    if items_th:
                        st.markdown("---")
                        hdr_th = st.columns([3, 1, 2, 1])
                        for lbl, col in zip(["Tên hàng", "SL", "Giá trả", ""], hdr_th):
                            col.caption(lbl)
                        for i, item in enumerate(items_th):
                            c1, c2, c3, c4 = st.columns([3, 1, 2, 1])
                            with c1:
                                st.markdown(f"<span style='font-size:0.88rem'>"
                                            f"{item['ma_hang']} — {item['ten_hang']}</span>",
                                            unsafe_allow_html=True)
                            with c2:
                                st.markdown(f"<span style='font-size:0.88rem'>x{item['so_luong']}</span>",
                                            unsafe_allow_html=True)
                            with c3:
                                st.markdown(f"<span style='font-size:0.88rem'>{_fmt(item['gia_tra'])}đ</span>",
                                            unsafe_allow_html=True)
                            with c4:
                                if st.button("✕", key=f"th_del_{cnt_th}_{i}"):
                                    st.session_state[items_key_th].pop(i); st.rerun()

                        tong_sl_th = sum(x["so_luong"] for x in items_th)
                        tong_gt_th = sum(x["so_luong"] * x["gia_tra"] for x in items_th)
                        m1, m2 = st.columns(2)
                        m1.metric("Tổng số lượng trả", f"{tong_sl_th:,}".replace(",", "."))
                        m2.metric("Tổng giá trị trả", f"{_fmt(tong_gt_th)}đ")

                    st.markdown("---")
                    can_save_th = bool(ma_ncc_th) and len(items_th) > 0
                    c_draft_th, c_submit_th = st.columns(2)
                    with c_draft_th:
                        if st.button("💾 Lưu nháp", use_container_width=True,
                                     disabled=not can_save_th, key="th_save_draft"):
                            try:
                                ma_th = _gen_ma_th()
                                supabase.table("phieu_tra_hang").insert({
                                    "ma_phieu": ma_th, "ma_ncc": ma_ncc_th, "ten_ncc": ten_ncc_th,
                                    "chi_nhanh": active, "trang_thai": "Nháp",
                                    "ghi_chu": ghi_chu_th.strip() or None,
                                    "created_by": ho_ten,
                                    "created_at": now_vn_iso(),
                                    "updated_at": now_vn_iso(),
                                }).execute()
                                supabase.table("phieu_tra_hang_ct").insert([
                                    {"ma_phieu": ma_th, "ma_hang": x["ma_hang"],
                                     "ten_hang": x["ten_hang"], "so_luong": x["so_luong"],
                                     "gia_tra": x["gia_tra"]} for x in items_th
                                ]).execute()
                                st.session_state["th_cnt"] = cnt_th + 1
                                st.cache_data.clear()
                                log_action("TH_DRAFT", f"ma={ma_th} ncc={ten_ncc_th}")
                                st.success(f"✓ Đã lưu nháp **{ma_th}**"); st.rerun()
                            except Exception as e: st.error(f"Lỗi: {e}")
                    with c_submit_th:
                        if st.button("📤 Gửi chờ xác nhận", type="primary",
                                     use_container_width=True, disabled=not can_save_th,
                                     key="th_submit"):
                            try:
                                ma_th = _gen_ma_th()
                                supabase.table("phieu_tra_hang").insert({
                                    "ma_phieu": ma_th, "ma_ncc": ma_ncc_th, "ten_ncc": ten_ncc_th,
                                    "chi_nhanh": active, "trang_thai": "Chờ xác nhận",
                                    "ghi_chu": ghi_chu_th.strip() or None,
                                    "created_by": ho_ten,
                                    "created_at": now_vn_iso(),
                                    "updated_at": now_vn_iso(),
                                }).execute()
                                supabase.table("phieu_tra_hang_ct").insert([
                                    {"ma_phieu": ma_th, "ma_hang": x["ma_hang"],
                                     "ten_hang": x["ten_hang"], "so_luong": x["so_luong"],
                                     "gia_tra": x["gia_tra"]} for x in items_th
                                ]).execute()
                                st.session_state["th_cnt"] = cnt_th + 1
                                st.cache_data.clear()
                                log_action("TH_SUBMIT", f"ma={ma_th} ncc={ten_ncc_th}")
                                st.success(f"✓ Đã gửi **{ma_th}** chờ xác nhận"); st.rerun()
                            except Exception as e: st.error(f"Lỗi: {e}")

            # ── Sub-tab: Chi tiết / Duyệt phiếu trả ──
            with sub_tra_dt:
                df_all_th = _load_phieu_tra(active)
                if df_all_th.empty:
                    st.info("Chưa có phiếu trả hàng nào.")
                else:
                    search_th = st.text_input("Tìm mã phiếu / NCC:", key="th_search_dt",
                                              placeholder="TH000001 hoặc tên NCC...")
                    df_f_th = df_all_th.copy()
                    if search_th.strip():
                        s_th2 = search_th.strip().lower()
                        df_f_th = df_f_th[
                            df_f_th["ma_phieu"].str.lower().str.contains(s_th2, na=False) |
                            df_f_th["ten_ncc"].astype(str).str.lower().str.contains(s_th2, na=False)
                        ]

                    if df_f_th.empty:
                        st.info("Không tìm thấy.")
                    else:
                        opts_th = [f"{r['ma_phieu']} · {r.get('ten_ncc', '')} · {r.get('trang_thai', '')}"
                                   for _, r in df_f_th.iterrows()]
                        picked_th = st.selectbox("Chọn phiếu:", opts_th, key="th_detail_pick")
                        ma_pick_th = picked_th.split(" · ")[0]
                        phieu_th = df_all_th[df_all_th["ma_phieu"] == ma_pick_th].iloc[0]
                        ct_th = _load_ct_tra(ma_pick_th)
                        tt_th = phieu_th.get("trang_thai", "")

                        p1, p2, p3 = st.columns(3)
                        with p1:
                            st.markdown(f"**Mã phiếu:** {ma_pick_th}")
                            st.markdown(f"**NCC:** {phieu_th.get('ten_ncc', '—')}")
                        with p2:
                            st.markdown(f"**Chi nhánh:** {phieu_th.get('chi_nhanh', '')}")
                            st.markdown(f"**Người tạo:** {phieu_th.get('created_by', '—')}")
                        with p3:
                            st.markdown(f"**Trạng thái:** {tt_th}")
                            st.markdown(f"**Người duyệt:** {phieu_th.get('confirmed_by') or '—'}")
                        if phieu_th.get("ghi_chu"):
                            st.markdown(f"**Ghi chú:** {phieu_th.get('ghi_chu', '')}")

                        if not ct_th.empty:
                            st.markdown("---")
                            ct_th_view = ct_th[["ma_hang", "ten_hang", "so_luong", "gia_tra"]].copy()
                            ct_th_view["thanh_tien"] = ct_th_view["so_luong"] * ct_th_view["gia_tra"]
                            ct_th_view = ct_th_view.rename(columns={
                                "ma_hang": "Mã", "ten_hang": "Tên",
                                "so_luong": "SL", "gia_tra": "Giá trả",
                                "thanh_tien": "Thành tiền"
                            })
                            st.dataframe(ct_th_view, use_container_width=True, hide_index=True)
                            tong_gt2 = int((ct_th["so_luong"] * ct_th["gia_tra"]).sum())
                            st.metric("Tổng giá trị trả", f"{_fmt(tong_gt2)}đ")

                        st.markdown("---")

                        if tt_th == "Nháp" and is_ke_toan_or_admin():
                            if st.button("📤 Gửi chờ xác nhận", type="primary",
                                         use_container_width=True, key="th_to_cho"):
                                supabase.table("phieu_tra_hang").update({
                                    "trang_thai": "Chờ xác nhận",
                                    "updated_at": now_vn_iso()
                                }).eq("ma_phieu", ma_pick_th).execute()
                                st.cache_data.clear()
                                st.success("✓ Đã gửi chờ xác nhận"); st.rerun()

                        if tt_th == "Chờ xác nhận" and is_admin():
                            st.info("Xác nhận sẽ **trừ** số lượng các mặt hàng khỏi tồn kho.")
                            if st.button("✅ Xác nhận — Trả hàng", type="primary",
                                         use_container_width=True, key="th_confirm"):
                                try:
                                    chi_nhanh_th = phieu_th.get("chi_nhanh", "")
                                    now_vn_th = now_vn_iso()
                                    ma_hangs_th  = ct_th["ma_hang"].astype(str).str.strip().tolist()
                                    ma_hangs_set_th = set(ma_hangs_th)
                                    sl_map_th = {str(r["ma_hang"]).strip(): int(r["so_luong"])
                                                 for _, r in ct_th.iterrows()}

                                    kho_rows_th, batch_th, offset_th = [], 1000, 0
                                    while True:
                                        r2 = supabase.table("the_kho").select("*") \
                                            .eq("Chi nhánh", chi_nhanh_th) \
                                            .range(offset_th, offset_th+batch_th-1).execute()
                                        if not r2.data: break
                                        kho_rows_th.extend(r2.data)
                                        if len(r2.data) < batch_th: break
                                        offset_th += batch_th

                                    ma_key_th = next(
                                        (k for k in (kho_rows_th[0].keys() if kho_rows_th else [])
                                         if "m" in k.lower() and "h" in k.lower() and len(k) <= 8),
                                        "Mã hàng"
                                    )
                                    kho_map_th = {
                                        str(r.get(ma_key_th, "")).strip(): r
                                        for r in kho_rows_th
                                        if str(r.get(ma_key_th, "")).strip() in ma_hangs_set_th
                                    }

                                    for mh, kho_row in kho_map_th.items():
                                        sl  = sl_map_th.get(mh, 0)
                                        cur = int(kho_row.get("Tồn cuối kì") or 0)
                                        supabase.table("the_kho").update(
                                            {"Tồn cuối kì": max(0, cur - sl)}
                                        ).eq("id", kho_row["id"]).execute()

                                    supabase.table("phieu_tra_hang").update({
                                        "trang_thai": "Đã trả hàng",
                                        "confirmed_by": ho_ten,
                                        "confirmed_at": now_vn_th,
                                        "updated_at": now_vn_th,
                                    }).eq("ma_phieu", ma_pick_th).execute()

                                    st.cache_data.clear()
                                    log_action("TH_CONFIRM", f"ma={ma_pick_th} cn={chi_nhanh_th}")
                                    st.success(f"✓ Đã trả hàng **{ma_pick_th}** — tồn kho đã trừ!")
                                    st.rerun()
                                except Exception as e: st.error(f"Lỗi xác nhận: {e}")

                        if is_admin() and tt_th in ("Nháp", "Chờ xác nhận"):
                            st.markdown("---")
                            if st.button("🗑️ Hủy phiếu", type="secondary",
                                         use_container_width=True, key="th_cancel"):
                                supabase.table("phieu_tra_hang").update({
                                    "trang_thai": "Đã hủy",
                                    "updated_at": now_vn_iso()
                                }).eq("ma_phieu", ma_pick_th).execute()
                                st.cache_data.clear()
                                log_action("TH_CANCEL", f"ma={ma_pick_th}", level="warning")
                                st.success("Đã hủy phiếu."); st.rerun()

                        if is_admin() and tt_th == "Đã trả hàng":
                            st.markdown("---")
                            if st.button("↩️ Hoàn tác trả hàng", type="secondary",
                                         use_container_width=True, key="th_revert"):
                                try:
                                    chi_nhanh_th = phieu_th.get("chi_nhanh", "")
                                    ma_hangs_th  = ct_th["ma_hang"].astype(str).str.strip().tolist()
                                    ma_hangs_set_th = set(ma_hangs_th)
                                    sl_map_th = {str(r["ma_hang"]).strip(): int(r["so_luong"])
                                                 for _, r in ct_th.iterrows()}

                                    kho_rows_th, batch_th, offset_th = [], 1000, 0
                                    while True:
                                        r2 = supabase.table("the_kho").select("*") \
                                            .eq("Chi nhánh", chi_nhanh_th) \
                                            .range(offset_th, offset_th+batch_th-1).execute()
                                        if not r2.data: break
                                        kho_rows_th.extend(r2.data)
                                        if len(r2.data) < batch_th: break
                                        offset_th += batch_th

                                    ma_key_th = next(
                                        (k for k in (kho_rows_th[0].keys() if kho_rows_th else [])
                                         if "m" in k.lower() and "h" in k.lower() and len(k) <= 8),
                                        "Mã hàng"
                                    )
                                    kho_map_th = {
                                        str(r.get(ma_key_th, "")).strip(): r
                                        for r in kho_rows_th
                                        if str(r.get(ma_key_th, "")).strip() in ma_hangs_set_th
                                    }

                                    for mh, kho_row in kho_map_th.items():
                                        sl  = sl_map_th.get(mh, 0)
                                        cur = int(kho_row.get("Tồn cuối kì") or 0)
                                        supabase.table("the_kho").update(
                                            {"Tồn cuối kì": cur + sl}
                                        ).eq("id", kho_row["id"]).execute()

                                    supabase.table("phieu_tra_hang").update({
                                        "trang_thai": "Đã hủy",
                                        "updated_at": now_vn_iso()
                                    }).eq("ma_phieu", ma_pick_th).execute()

                                    st.cache_data.clear()
                                    log_action("TH_REVERT", f"ma={ma_pick_th}", level="warning")
                                    st.success("✓ Đã hoàn tác — tồn kho cộng lại."); st.rerun()
                                except Exception as e: st.error(f"Lỗi hoàn tác: {e}")

    # ══════════════════════════════════════════
    # TAB CHÍNH 3 — NHÀ CUNG CẤP (Admin only)
    # ══════════════════════════════════════════
    if tab_ncc:
        with tab_ncc:
            st.markdown("**Danh sách nhà cung cấp:**")
            df_ncc2 = _load_ncc()
            if not df_ncc2.empty:
                st.dataframe(df_ncc2[["ma_ncc", "ten_ncc", "sdt", "dia_chi", "ghi_chu"]].rename(
                    columns={"ma_ncc": "Mã", "ten_ncc": "Tên NCC", "sdt": "SĐT",
                             "dia_chi": "Địa chỉ", "ghi_chu": "Ghi chú"}),
                    use_container_width=True, hide_index=True)

                st.markdown("**Xóa NCC:**")
                ncc_del_opts = ["-- Chọn NCC để xóa --"] + [
                    f"{r['ma_ncc']} — {r['ten_ncc']}" for _, r in df_ncc2.iterrows()
                ]
                ncc_del = st.selectbox("", ncc_del_opts, key="ncc_del_pick",
                                       label_visibility="collapsed")
                if ncc_del != "-- Chọn NCC để xóa --":
                    ma_del = ncc_del.split(" — ")[0]
                    if st.button("🗑️ Xóa NCC này", type="secondary", key="ncc_del_btn"):
                        try:
                            supabase.table("nha_cung_cap").update({"active": False}) \
                                .eq("ma_ncc", ma_del).execute()
                            st.cache_data.clear()
                            st.success(f"✓ Đã xóa {ncc_del}"); st.rerun()
                        except Exception as e: st.error(f"Lỗi: {e}")

            st.markdown("---")
            st.markdown("**Thêm NCC mới:**")
            n1, n2 = st.columns(2)
            with n1:
                ncc_ma  = st.text_input("Mã NCC:", key="ncc_new_ma", placeholder="VD: NCC001")
                ncc_ten = st.text_input("Tên NCC: *", key="ncc_new_ten")
            with n2:
                ncc_sdt = st.text_input("SĐT:", key="ncc_new_sdt")
                ncc_dc  = st.text_input("Địa chỉ:", key="ncc_new_dc")
            ncc_gc = st.text_input("Ghi chú:", key="ncc_new_gc")
            if st.button("➕ Thêm NCC", type="primary", key="ncc_add_btn"):
                if not ncc_ten.strip():
                    st.warning("Nhập tên NCC.")
                else:
                    try:
                        auto_ma = ncc_ma.strip().upper()
                        if not auto_ma:
                            res_ncc = supabase.table("nha_cung_cap").select("ma_ncc") \
                                .like("ma_ncc", "NCC%").order("ma_ncc", desc=True).limit(1).execute()
                            if res_ncc.data:
                                digits = "".join(filter(str.isdigit, res_ncc.data[0]["ma_ncc"]))
                                auto_ma = f"NCC{int(digits)+1:03d}" if digits else "NCC001"
                            else:
                                auto_ma = "NCC001"
                        supabase.table("nha_cung_cap").insert({
                            "ma_ncc": auto_ma, "ten_ncc": ncc_ten.strip(),
                            "sdt": ncc_sdt.strip() or None, "dia_chi": ncc_dc.strip() or None,
                            "ghi_chu": ncc_gc.strip() or None,
                            "created_at": now_vn_iso(),
                        }).execute()
                        st.cache_data.clear()
                        st.success(f"✓ Đã thêm NCC **{ncc_ten.strip()}** (mã: {auto_ma})"); st.rerun()
                    except Exception as e: st.error(f"Lỗi: {e}")

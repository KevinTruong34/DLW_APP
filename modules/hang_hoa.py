import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches

from utils.helpers import _normalize


def module_hang_hoa():
    try:
        active     = get_active_branch()
        accessible = get_accessible_branches()

        # ── Chi nhánh filter ──
        if is_ke_toan_or_admin() and len(accessible) > 1:
            view_branches = st.multiselect(
                "Chi nhánh:", accessible, default=[active],
                key="hh_cn", label_visibility="collapsed")
            if not view_branches: st.warning("Chọn ít nhất một chi nhánh."); return
        else:
            view_branches = [active]

        # ── Load data ──
        master   = load_hang_hoa()
        the_kho  = load_the_kho(branches_key=tuple(view_branches))
        has_master = not master.empty

        if not has_master and the_kho.empty:
            # Nếu chưa có dữ liệu, vẫn cho admin thêm mới
            if is_admin():
                st.info("Chưa có dữ liệu hàng hóa.")
                _render_them_moi()
            else:
                st.info("Chưa có dữ liệu. Vào ⚙️ Quản trị → Upload để tải lên.")
            return

        # ── Build df ──
        if has_master and not the_kho.empty:
            kho_agg = the_kho.groupby("Mã hàng", as_index=False).agg(
                Ton_cuoi=("Tồn cuối kì","sum"))
            df = master.merge(kho_agg, left_on="ma_hang", right_on="Mã hàng", how="left")
            df["Ton_cuoi"] = df["Ton_cuoi"].fillna(0).astype(int)
        elif has_master:
            df = master.copy(); df["Ton_cuoi"] = 0
        else:
            df = the_kho.groupby(["Mã hàng","Tên hàng"], as_index=False).agg(
                Ton_cuoi=("Tồn cuối kì","sum"))
            df["ma_hang"]=""; df["ma_vach"]=""; df["ten_hang"]=df["Tên hàng"]
            df["nhom_hang"]=""; df["thuong_hieu"]=""; df["loai_hang"]=""; df["gia_ban"]=0; df["bao_hanh"]=""
            df["ma_hang"] = df["Mã hàng"]; df["ma_vach"] = df["Mã hàng"]

        if "loai_hang" in df.columns and df["loai_hang"].fillna("").str.strip().any():
            df["_cha"] = df["loai_hang"].fillna("").str.strip()
            df["_con"] = df.get("thuong_hieu", pd.Series([""] * len(df))).fillna("").str.strip()
        else:
            nhom_col = df["nhom_hang"].fillna("") if "nhom_hang" in df.columns \
                       else pd.Series([""] * len(df))
            split = nhom_col.str.split(">>", n=1, expand=True)
            df["_cha"] = split[0].str.strip()
            df["_con"] = (split[1].str.strip() if 1 in split.columns else "").fillna("")

        df["_norm_ma"]   = df["ma_hang"].apply(_normalize)
        df["_norm_vach"] = df.get("ma_vach", df["ma_hang"]).apply(
            lambda x: _normalize(x) if pd.notna(x) else "")
        df["_norm_ten"]  = df["ten_hang"].apply(_normalize)

        # ══════ SEARCH + FILTER ══════
        cha_list = sorted([c for c in df["_cha"].dropna().unique() if c])

        col_s, col_f = st.columns([5, 1])
        with col_s:
            _sc = st.session_state.get("hh_search_cnt", 0)
            keyword = st.text_input("", key=f"hh_search_{_sc}",
                placeholder="🔍  Tìm mã hàng, mã vạch hoặc tên...",
                label_visibility="collapsed")
        with col_f:
            with st.popover("⊞ Lọc", use_container_width=True):
                cha_chon = st.selectbox("Nhóm hàng:", ["Tất cả"] + cha_list,
                    key="hh_cha", label_visibility="collapsed")
                if cha_chon != "Tất cả":
                    con_list = sorted([c for c in
                        df[df["_cha"]==cha_chon]["_con"].dropna().unique() if c])
                    con_chon = st.selectbox("Nhóm con:", ["Tất cả"] + con_list,
                        key="hh_con", label_visibility="collapsed")
                else:
                    con_chon = "Tất cả"
        cha_chon = st.session_state.get("hh_cha", "Tất cả")
        con_chon = st.session_state.get("hh_con", "Tất cả")

        filtered = df.copy()
        kw = _normalize(keyword) if keyword.strip() else ""
        if kw:
            filtered = filtered[
                filtered["_norm_ma"].str.contains(kw, na=False) |
                filtered["_norm_vach"].str.contains(kw, na=False) |
                filtered["_norm_ten"].str.contains(kw, na=False)]
        if cha_chon != "Tất cả":
            filtered = filtered[filtered["_cha"] == cha_chon]
        if con_chon != "Tất cả":
            filtered = filtered[filtered["_con"] == con_chon]

        filtered = filtered.sort_values("Ton_cuoi", ascending=False).reset_index(drop=True)

        if filtered.empty:
            st.warning("Không tìm thấy hàng hóa phù hợp.")
            if is_admin():
                st.markdown("---")
                _render_them_moi()
            return

        if len(filtered) == 1:
            st.session_state["hh_ma_chon"] = filtered.iloc[0]["ma_hang"]

        ma_chon = st.session_state.get("hh_ma_chon")
        if ma_chon and ma_chon not in filtered["ma_hang"].values:
            ma_chon = None; st.session_state.pop("hh_ma_chon", None)

        # ══════ DETAIL CARD ══════
        if ma_chon:
            row_m = filtered[filtered["ma_hang"] == ma_chon].iloc[0]
            ma_display = str(row_m["ma_hang"])
            vach       = str(row_m.get("ma_vach","") or "")
            nhom_full  = (f"{row_m['_cha']} › {row_m['_con']}"
                         if row_m.get("_con","") else row_m.get("_cha",""))
            gb = int(row_m.get("gia_ban", 0) or 0)

            extra_parts = []
            if pd.notna(row_m.get("thuong_hieu","")) and str(row_m.get("thuong_hieu","")).strip():
                extra_parts.append(f"Thương hiệu: {row_m['thuong_hieu']}")
            if pd.notna(row_m.get("bao_hanh","")) and str(row_m.get("bao_hanh","")).strip():
                extra_parts.append(f"Bảo hành: {row_m['bao_hanh']}")
            extra_str = " · ".join(extra_parts)

            vach_str   = f" · {vach}" if vach and vach != ma_display else ""
            nhom_html  = f"<div style='font-size:0.75rem;color:#aaa;margin-top:1px;'>{nhom_full}</div>" if nhom_full else ""
            extra_html = f"<div style='font-size:0.78rem;color:#666;margin-top:6px;'>{extra_str}</div>" if extra_str else ""
            gb_html    = (f"<div style='margin-top:10px;font-size:0.75rem;color:#888;'>Giá bán</div>"
                         f"<div style='font-size:1.1rem;font-weight:700;color:#1a1a2e;'>"
                         f"{'—' if not gb else f'{gb:,} đ'}</div>")

            c_card, c_close = st.columns([8, 1])
            with c_card:
                st.markdown(
                    f"<div style='background:#fff;border:1px solid #e0e0e0;"
                    f"border-radius:12px;padding:14px 16px;'>"
                    f"<div style='font-weight:700;font-size:1.05rem;color:#1a1a2e;'>"
                    f"{row_m['ten_hang']}</div>"
                    f"{nhom_html}"
                    f"<div style='margin-top:10px;'>"
                    f"<span style='font-family:monospace;font-size:0.95rem;font-weight:700;"
                    f"background:#f4f6fa;padding:4px 10px;border-radius:6px;color:#1a1a2e;'>"
                    f"{ma_display}</span>"
                    f"<span style='font-size:0.82rem;color:#999;margin-left:8px;'>{vach_str}</span>"
                    f"</div>"
                    f"{extra_html}"
                    f"{gb_html}"
                    f"</div>",
                    unsafe_allow_html=True)
            with c_close:
                st.markdown("<div style='padding-top:10px;'>", unsafe_allow_html=True)
                if st.button("✕", key="btn_close", help="Đóng"):
                    st.session_state.pop("hh_ma_chon", None)
                    st.session_state["hh_search_cnt"] = st.session_state.get("hh_search_cnt", 0) + 1
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            # Tồn kho 3 chi nhánh
            st.markdown(
                "<div style='font-size:0.82rem;font-weight:600;"
                "color:#555;margin:10px 0 6px;'>Tồn kho chi nhánh</div>",
                unsafe_allow_html=True)
            try:
                all_kho = load_the_kho(branches_key=tuple(ALL_BRANCHES))
                branch_tons = {cn: 0 for cn in ALL_BRANCHES}
                branch_kho_ids = {cn: None for cn in ALL_BRANCHES}
                if not all_kho.empty:
                    rows_kho = all_kho[all_kho["Mã hàng"].astype(str).str.strip() == str(ma_chon).strip()]
                    for _, kr in rows_kho.iterrows():
                        cn = kr.get("Chi nhánh", "")
                        if cn in branch_tons:
                            branch_tons[cn] += int(kr.get("Tồn cuối kì", 0) or 0)
                            branch_kho_ids[cn] = kr.get("id")

                cn_cols = st.columns(3)
                for idx, cn_name in enumerate(ALL_BRANCHES):
                    with cn_cols[idx]:
                        ton    = branch_tons[cn_name]
                        is_cur = (cn_name == active)
                        clr    = "#1a7f37" if ton > 5 else ("#cf4c2c" if ton > 0 else "#aaa")
                        border = "2px solid #e63946" if is_cur else "1px solid #e8e8e8"
                        bg     = "#fff8f8" if is_cur else "#fff"
                        icon   = "📍 " if is_cur else ""
                        st.markdown(
                            f"<div style='text-align:center;padding:10px 4px;"
                            f"border:{border};border-radius:10px;background:{bg};'>"
                            f"<div style='font-size:0.68rem;color:#777;"
                            f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>"
                            f"{icon}{CN_SHORT.get(cn_name, cn_name)}</div>"
                            f"<div style='font-size:1.4rem;font-weight:700;color:{clr};'>"
                            f"{ton:,}</div></div>",
                            unsafe_allow_html=True)

                # ── Chỉnh tồn kho (admin only) ──
                if is_admin():
                    with st.expander("✏️ Chỉnh tồn kho", expanded=False):
                        st.caption("Điều chỉnh trực tiếp tồn kho tại từng chi nhánh. "
                                   "Thay đổi sẽ ghi thẳng vào the_kho.")
                        adj_cols = st.columns(3)
                        adj_vals = {}
                        for idx, cn_name in enumerate(ALL_BRANCHES):
                            with adj_cols[idx]:
                                adj_vals[cn_name] = st.number_input(
                                    CN_SHORT.get(cn_name, cn_name),
                                    min_value=0,
                                    value=branch_tons[cn_name],
                                    step=1,
                                    key=f"adj_ton_{ma_chon}_{cn_name}"
                                )
                        if st.button("💾 Lưu tồn kho", type="primary",
                                     use_container_width=True, key=f"save_ton_{ma_chon}"):
                            try:
                                changed = []
                                for cn_name in ALL_BRANCHES:
                                    new_ton = int(adj_vals[cn_name])
                                    old_ton = branch_tons[cn_name]
                                    if new_ton == old_ton:
                                        continue
                                    kho_id = branch_kho_ids[cn_name]
                                    if kho_id:
                                        # Dòng đã tồn tại → update
                                        supabase.table("the_kho").update(
                                            {"Tồn cuối kì": new_ton}
                                        ).eq("id", kho_id).execute()
                                    else:
                                        # Chưa có dòng → insert mới
                                        supabase.table("the_kho").insert({
                                            "Mã hàng":    str(ma_chon),
                                            "Tên hàng":   str(row_m.get("ten_hang", "")),
                                            "Chi nhánh":  cn_name,
                                            "Tồn cuối kì": new_ton,
                                            "Tồn đầu kì":  0,
                                        }).execute()
                                    changed.append(
                                        f"{CN_SHORT.get(cn_name, cn_name)}: "
                                        f"{old_ton} → {new_ton}"
                                    )
                                if changed:
                                    st.cache_data.clear()
                                    log_action("KHO_ADJ",
                                               f"ma={ma_chon} " + ", ".join(changed))
                                    st.success("✓ Đã cập nhật: " + " · ".join(changed))
                                    st.rerun()
                                else:
                                    st.info("Không có thay đổi.")
                            except Exception as e:
                                st.error(f"Lỗi: {e}")

            except Exception:
                pass

            # ── Admin actions: Sửa thông tin & Ẩn hàng hóa ──
            if is_admin():
                with st.expander("✏️ Sửa thông tin hàng hóa", expanded=False):
                    _render_sua_hang_hoa(row_m)

                st.markdown("---")
                _render_an_hang_hoa(ma_chon, str(row_m.get("ten_hang", "")))

            st.markdown("<hr style='margin:12px 0 6px;'>", unsafe_allow_html=True)

        # ══════ BẢNG HÀNG HÓA ══════
        total = len(filtered)
        filter_label = (f"{cha_chon}" if cha_chon != "Tất cả" else "")
        st.caption(
            f"**{total}** sản phẩm"
            + (f" · {filter_label}" if filter_label else "")
            + f" · {', '.join(view_branches)}"
            + (" — lọc thêm để thu hẹp" if total > 100 else "")
        )

        disp_cols = {"ten_hang":"Tên hàng","ma_hang":"Mã hàng","Ton_cuoi":"Tồn kho"}
        if "ma_vach" in filtered.columns:
            disp_cols = {"ten_hang":"Tên hàng","ma_hang":"Mã hàng",
                         "ma_vach":"Mã vạch","Ton_cuoi":"Tồn kho"}
        avail = {k:v for k,v in disp_cols.items() if k in filtered.columns}
        disp  = filtered[list(avail.keys())].rename(columns=avail).copy()
        disp["Tồn kho"] = disp["Tồn kho"].astype(int)

        ROW_H  = 35
        HEADER = 42
        N_ROWS = 10
        tbl_h  = HEADER + N_ROWS * ROW_H

        event = st.dataframe(
            disp,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="hh_table",
            column_config={
                "Tên hàng": st.column_config.TextColumn("Tên hàng", width="medium"),
                "Mã hàng":  st.column_config.TextColumn("Mã hàng",  width="medium"),
                "Mã vạch":  st.column_config.TextColumn("Mã vạch",  width="medium"),
                "Tồn kho":  st.column_config.NumberColumn("Tồn", width="small", format="%d"),
            },
            height=tbl_h,
        )

        sel = event.selection.rows
        if sel and sel[0] < len(disp):
            new_ma = disp.iloc[sel[0]]["Mã hàng"]
            if new_ma != ma_chon:
                st.session_state["hh_ma_chon"] = new_ma
                st.rerun()

        if not ma_chon:
            st.caption("↑ Chọn một dòng để xem chi tiết sản phẩm")

        # ── Nút thêm hàng hóa mới (admin) ──
        if is_admin():
            st.markdown("---")
            with st.expander("➕ Thêm hàng hóa mới", expanded=False):
                _render_them_moi()

    except Exception as e:
        st.error(f"Lỗi tải Hàng hóa: {e}")


# ══════════════════════════════════════════════════════════
# ADMIN HELPERS
# ══════════════════════════════════════════════════════════

def _render_them_moi():
    """Form thêm hàng hóa mới vào master."""
    master = load_hang_hoa()

    # Gợi ý loai_hang và thuong_hieu từ master hiện có
    loai_opts = sorted(master["loai_hang"].dropna().unique().tolist()) \
        if not master.empty and "loai_hang" in master.columns else []

    cnt = st.session_state.get("hh_them_cnt", 0)

    c1, c2 = st.columns(2)
    with c1:
        new_ma   = st.text_input("Mã hàng: *", key=f"hh_new_ma_{cnt}",
                                  placeholder="VD: PDH130")
        new_ten  = st.text_input("Tên hàng: *", key=f"hh_new_ten_{cnt}")
        new_vach = st.text_input("Mã vạch:", key=f"hh_new_vach_{cnt}")
        new_gb   = st.number_input("Giá bán:", min_value=0, step=10000,
                                    key=f"hh_new_gb_{cnt}", value=0)
    with c2:
        loai_sel = st.selectbox("Loại hàng:",
            ["-- Chọn --"] + loai_opts + ["(Nhập mới)"],
            key=f"hh_new_loai_{cnt}")
        if loai_sel == "(Nhập mới)":
            new_loai = st.text_input("Tên loại mới:", key=f"hh_new_loai_txt_{cnt}")
        elif loai_sel == "-- Chọn --":
            new_loai = ""
        else:
            new_loai = loai_sel

        th_opts = []
        if new_loai and not master.empty and "thuong_hieu" in master.columns:
            th_opts = sorted(master[master["loai_hang"] == new_loai][
                "thuong_hieu"].dropna().unique().tolist())
        th_sel = st.selectbox("Thương hiệu:",
            ["-- Chọn --"] + th_opts + ["(Nhập mới)"],
            key=f"hh_new_th_{cnt}")
        if th_sel == "(Nhập mới)":
            new_th = st.text_input("Tên thương hiệu mới:", key=f"hh_new_th_txt_{cnt}")
        elif th_sel == "-- Chọn --":
            new_th = ""
        else:
            new_th = th_sel

        new_bh = st.text_input("Bảo hành:", key=f"hh_new_bh_{cnt}",
                                placeholder="VD: 12 tháng")

    can_add = bool(new_ma.strip()) and bool(new_ten.strip())
    if st.button("➕ Thêm hàng hóa", type="primary",
                 use_container_width=True, key=f"hh_add_btn_{cnt}",
                 disabled=not can_add):
        ma_clean = new_ma.strip().upper()
        # Kiểm tra trùng mã
        if not master.empty and ma_clean in master["ma_hang"].astype(str).str.upper().values:
            st.error(f"Mã hàng **{ma_clean}** đã tồn tại trong hệ thống.")
        else:
            try:
                supabase.table("hang_hoa").insert({
                    "ma_hang":    ma_clean,
                    "ten_hang":   new_ten.strip(),
                    "ma_vach":    new_vach.strip() or None,
                    "gia_ban":    int(new_gb),
                    "loai_hang":  new_loai or None,
                    "thuong_hieu": new_th or None,
                    "bao_hanh":   new_bh.strip() or None,
                    "active":     True,
                }).execute()
                st.cache_data.clear()
                log_action("HH_ADD", f"ma={ma_clean} ten={new_ten.strip()}")
                st.success(f"✓ Đã thêm **{ma_clean}** — {new_ten.strip()}")
                st.session_state["hh_them_cnt"] = cnt + 1
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi: {e}")


def _render_sua_hang_hoa(row_m):
    """Form sửa thông tin hàng hóa đã có."""
    ma = str(row_m["ma_hang"])
    cnt = st.session_state.get(f"hh_sua_cnt_{ma}", 0)

    master = load_hang_hoa()
    loai_opts = sorted(master["loai_hang"].dropna().unique().tolist()) \
        if not master.empty and "loai_hang" in master.columns else []
    cur_loai = str(row_m.get("loai_hang") or "")
    cur_th   = str(row_m.get("thuong_hieu") or "")

    c1, c2 = st.columns(2)
    with c1:
        new_ten  = st.text_input("Tên hàng:", value=str(row_m.get("ten_hang","")),
                                  key=f"hh_sua_ten_{ma}_{cnt}")
        new_vach = st.text_input("Mã vạch:", value=str(row_m.get("ma_vach","") or ""),
                                  key=f"hh_sua_vach_{ma}_{cnt}")
        new_gb   = st.number_input("Giá bán:", min_value=0, step=10000,
                                    value=int(row_m.get("gia_ban",0) or 0),
                                    key=f"hh_sua_gb_{ma}_{cnt}")
    with c2:
        loai_idx = (loai_opts.index(cur_loai) + 1) if cur_loai in loai_opts else 0
        loai_sel = st.selectbox("Loại hàng:",
            ["-- Giữ nguyên --"] + loai_opts,
            index=loai_idx, key=f"hh_sua_loai_{ma}_{cnt}")
        new_loai = "" if loai_sel == "-- Giữ nguyên --" else loai_sel

        th_opts = []
        check_loai = new_loai or cur_loai
        if check_loai and not master.empty and "thuong_hieu" in master.columns:
            th_opts = sorted(master[master["loai_hang"] == check_loai][
                "thuong_hieu"].dropna().unique().tolist())
        th_idx = (th_opts.index(cur_th) + 1) if cur_th in th_opts else 0
        th_sel = st.selectbox("Thương hiệu:",
            ["-- Giữ nguyên --"] + th_opts,
            index=th_idx, key=f"hh_sua_th_{ma}_{cnt}")
        new_th = "" if th_sel == "-- Giữ nguyên --" else th_sel

        new_bh = st.text_input("Bảo hành:", value=str(row_m.get("bao_hanh","") or ""),
                                key=f"hh_sua_bh_{ma}_{cnt}")

    if st.button("💾 Lưu thay đổi", type="primary",
                 use_container_width=True, key=f"hh_sua_btn_{ma}_{cnt}"):
        try:
            payload = {
                "ten_hang": new_ten.strip(),
                "ma_vach":  new_vach.strip() or None,
                "gia_ban":  int(new_gb),
                "bao_hanh": new_bh.strip() or None,
            }
            if new_loai: payload["loai_hang"]   = new_loai
            if new_th:   payload["thuong_hieu"] = new_th
            supabase.table("hang_hoa").update(payload).eq("ma_hang", ma).execute()
            st.cache_data.clear()
            log_action("HH_EDIT", f"ma={ma}")
            st.success("✓ Đã cập nhật thông tin hàng hóa.")
            st.session_state[f"hh_sua_cnt_{ma}"] = cnt + 1
            st.rerun()
        except Exception as e:
            st.error(f"Lỗi: {e}")


def _render_an_hang_hoa(ma: str, ten: str):
    """Nút soft-delete hàng hóa."""
    st.caption(
        "Ẩn hàng hóa sẽ xóa khỏi danh sách tìm kiếm nhưng giữ lại lịch sử giao dịch."
    )
    confirm_key = f"hh_an_confirm_{ma}"
    if not st.session_state.get(confirm_key):
        if st.button(f"🚫 Ẩn hàng hóa này ({ma})", type="secondary",
                     use_container_width=True, key=f"hh_an_btn_{ma}"):
            st.session_state[confirm_key] = True
            st.rerun()
    else:
        st.warning(f"Xác nhận ẩn **{ma} — {ten}**? Hành động này có thể hoàn tác bằng cách upload lại master.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✓ Xác nhận ẩn", type="primary",
                         use_container_width=True, key=f"hh_an_ok_{ma}"):
                try:
                    supabase.table("hang_hoa").update({"active": False}) \
                        .eq("ma_hang", ma).execute()
                    st.cache_data.clear()
                    log_action("HH_HIDE", f"ma={ma} ten={ten}")
                    st.session_state.pop(confirm_key, None)
                    st.session_state.pop("hh_ma_chon", None)
                    st.success(f"✓ Đã ẩn {ma}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")
        with c2:
            if st.button("Hủy", use_container_width=True, key=f"hh_an_cancel_{ma}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()

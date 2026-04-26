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

from utils.helpers import _build_phieu_html, _in_phieu_sc

def module_sua_chua():
    st.markdown("### 🔧 Sửa chữa")
    active = get_active_branch()
    accessible = get_accessible_branches()
    user = get_user() or {}
    ho_ten = user.get("ho_ten", user.get("username", ""))

    tab_list, tab_create, tab_detail, tab_hoadon = st.tabs(
        ["Danh sách phiếu", "Tạo phiếu mới", "Chi tiết / Cập nhật", "Tạo hóa đơn sửa"]
    )

    # ── HELPERS ──
    @st.cache_data(ttl=60)
    def _load_phieu(branches_key: tuple) -> pd.DataFrame:
        try:
            res = supabase.table("phieu_sua_chua").select("*") \
                .in_("chi_nhanh", list(branches_key)) \
                .order("created_at", desc=True).execute()
            if not res.data: return pd.DataFrame()
            df = pd.DataFrame(res.data)
            if "ngay_tiep_nhan" in df.columns:
                df["_ngay"] = (pd.to_datetime(df["ngay_tiep_nhan"], utc=True)
                               .dt.tz_convert("Asia/Ho_Chi_Minh"))
                df["Ngày TN"] = df["_ngay"].dt.strftime("%d/%m/%Y %H:%M")
            return df
        except Exception as e:
            st.error(f"Lỗi tải phiếu: {e}"); return pd.DataFrame()

    def _load_chi_tiet(ma_phieu: str) -> pd.DataFrame:
        try:
            res = supabase.table("phieu_sua_chua_chi_tiet").select("*") \
                .eq("ma_phieu", ma_phieu).execute()
            if not res.data: return pd.DataFrame()
            df = pd.DataFrame(res.data)
            for col in ["so_luong", "don_gia"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            return df
        except Exception: return pd.DataFrame()

    def _gen_ma_phieu() -> str:
        try:
            res = supabase.table("phieu_sua_chua").select("ma_phieu") \
                .like("ma_phieu", "SC______").order("ma_phieu", desc=True).limit(1).execute()
            num = int(res.data[0]["ma_phieu"][2:]) + 1 if res.data else 1
            return f"SC{num:06d}"
        except Exception:
            return f"SC{datetime.now().strftime('%y%m%d%H%M')}"

    def _gen_ma_apsc() -> str:
        """Sinh mã APSC kế tiếp qua Postgres function."""
        try:
            res = supabase.rpc("get_next_apsc_num", {}).execute()
            data = res.data
            if isinstance(data, list):
                num = int(data[0]) if data else 1
            elif data is not None:
                num = int(data)
            else:
                num = 1
            return f"APSC{num:06d}"
        except Exception:
            return f"APSC{(datetime.now() + timedelta(hours=7)).strftime('%y%m%d%H%M')}"

    def _tao_hoa_don_apsc(phieu: dict, ct: pd.DataFrame,
                           giam_gia: int, pttt: dict) -> str:
        """Tạo hóa đơn APSC với giảm giá và PTTT tuỳ chỉnh."""
        ma_hd = _gen_ma_apsc()
        now_vn = datetime.now() + timedelta(hours=7)
        now_str = now_vn.strftime("%d/%m/%Y %H:%M:%S")
        tong = int((ct["so_luong"] * ct["don_gia"]).sum()) if not ct.empty else 0
        can_tra = max(0, tong - giam_gia - int(phieu.get("khach_tra_truoc", 0)))
        rows = []
        base = {
            "Mã hóa đơn": ma_hd, "Chi nhánh": phieu.get("chi_nhanh",""),
            "Mã YCSC": phieu.get("ma_phieu", ""),
            "Thời gian": now_str, "Thời gian tạo": now_str,
            "Tên khách hàng": phieu.get("ten_khach",""),
            "Điện thoại": phieu.get("sdt_khach",""),
            "Trạng thái": "Hoàn thành", "Người bán": ho_ten,
            "Tổng tiền hàng": tong, "Giảm giá hóa đơn": giam_gia,
            "Khách cần trả": can_tra, "Khách đã trả": can_tra,
            "Tiền mặt": pttt.get("tien_mat", 0),
            "Chuyển khoản": pttt.get("chuyen_khoan", 0),
            "Thẻ": pttt.get("the", 0),
            "Ví": 0, "Điểm": 0, "Còn cần thu (COD)": 0,
            "Kênh bán": "Tại quầy", "Ghi chú": phieu.get("mo_ta_loi",""),
        }
        if ct.empty:
            rows.append(base)
        else:
            for _, r in ct.iterrows():
                tt = int(r["so_luong"]) * int(r["don_gia"])
                row = {**base,
                    "Mã hàng": str(r.get("ma_hang") or ""),
                    "Mã vạch": str(r.get("ma_hang") or ""),
                    "Tên hàng": str(r.get("ten_hang","")),
                    "Số lượng": int(r["so_luong"]),
                    "Đơn giá": int(r["don_gia"]),
                    "Thành tiền": tt, "Giá bán": int(r["don_gia"]),
                    "Giảm giá %": 0, "Giảm giá": 0,
                }
                rows.append(row)
        supabase.table("hoa_don").insert(rows).execute()
        return ma_hd

    TRANG_THAI_LIST = ["Đang sửa", "Chờ linh kiện", "Chờ giao khách"]
    LOAI_YC_LIST   = ["Sửa chữa", "Bảo hành"]
    LOAI_DONG_LIST = ["Dịch vụ", "Linh kiện"]

    # ── Helper: widget thêm dịch vụ/linh kiện dùng chung ──
    def _widget_them_dv(key_prefix: str, items_key: str):
        hh = load_hang_hoa()
        ma_tim = st.text_input("🔍 Tìm mã / tên hàng hóa:", key=f"{key_prefix}_ma_tim",
                                placeholder="VD: PDH, pin, lau dầu...")
        hits = pd.DataFrame()
        if ma_tim.strip() and not hh.empty:
            s = ma_tim.strip().lower()
            s_nospace = s.replace(" ", "")
            def _fuzzy(val):
                v = str(val).lower()
                return s in v or s_nospace in v.replace(" ", "")
            mask = (hh["ma_hang"].apply(_fuzzy) | hh["ten_hang"].apply(_fuzzy))
            hits = hh[mask].head(8)

        if not hits.empty:
            for _, row in hits.iterrows():
                gia = int(row.get("gia_ban", 0))
                label = f"{row['ma_hang']} — {row['ten_hang']}  |  {gia:,}đ".replace(",",".")
                col_lbl, col_sl, col_btn = st.columns([5, 1, 1])
                with col_lbl: st.markdown(f"<span style='font-size:0.9rem'>{label}</span>", unsafe_allow_html=True)
                with col_sl:
                    sl = st.number_input("SL", min_value=1, value=1,
                                          key=f"{key_prefix}_sl_{row['ma_hang']}", label_visibility="collapsed")
                with col_btn:
                    if st.button("➕", key=f"{key_prefix}_add_{row['ma_hang']}"):
                        st.session_state.setdefault(items_key, []).append({
                            "loai_dong": "Dịch vụ",
                            "ten_hang":  str(row["ten_hang"]),
                            "ma_hang":   str(row["ma_hang"]),
                            "so_luong":  int(sl),
                            "don_gia":   gia,
                        })
                        st.rerun()
        elif ma_tim.strip():
            st.caption("Không tìm thấy — có thể nhập tay bên dưới:")
            ca, cb, cc, cd = st.columns([3, 1, 2, 1])
            with ca: ten_tay = st.text_input("Tên:", key=f"{key_prefix}_tay_ten")
            with cb: sl_tay  = st.number_input("SL:", min_value=1, value=1, key=f"{key_prefix}_tay_sl")
            with cc: gia_tay = st.number_input("Đơn giá:", min_value=0, step=10000,
                                                value=0, key=f"{key_prefix}_tay_gia")
            with cd:
                st.write("")
                if st.button("➕", key=f"{key_prefix}_tay_add") and ten_tay.strip():
                    st.session_state.setdefault(items_key, []).append({
                        "loai_dong": "Dịch vụ", "ten_hang": ten_tay.strip(),
                        "ma_hang": None, "so_luong": sl_tay, "don_gia": gia_tay,
                    })
                    st.rerun()

    def _hien_thi_items(items_key: str):
        items = st.session_state.get(items_key, [])
        if not items:
            st.caption("_(Chưa có mục nào)_")
            return
        for i, item in enumerate(items):
            ci1, ci2, ci3, ci4, ci5 = st.columns([2, 4, 1, 2, 1])
            with ci1: st.markdown(f"<span style='font-size:0.9rem'>{item.get('loai_dong','')}</span>", unsafe_allow_html=True)
            with ci2: st.markdown(f"<span style='font-size:0.9rem'>{item.get('ten_hang','')}</span>", unsafe_allow_html=True)
            with ci3: st.markdown(f"<span style='font-size:0.9rem'>x{item.get('so_luong',1)}</span>", unsafe_allow_html=True)
            with ci4: st.markdown(f"<span style='font-size:0.9rem'>{item.get('don_gia',0):,}đ</span>".replace(",","."), unsafe_allow_html=True)
            with ci5:
                if st.button("✕", key=f"del_{items_key}_{i}"):
                    st.session_state[items_key].pop(i); st.rerun()

    # ══════ TAB 1 — DANH SÁCH ══════
    with tab_list:
        cn_filter = active
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_filter = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible, key="sc_cn_filter")
        branches = accessible if cn_filter == "Tất cả" else [cn_filter]

        tt_filter = st.selectbox("Trạng thái:", ["Tất cả"] + TRANG_THAI_LIST + ["Hoàn thành"], key="sc_tt_filter")
        search = st.text_input("Tìm SĐT / Mã phiếu / Tên khách:", key="sc_search",
                                placeholder="VD: '900' tìm SC000900...")

        df = _load_phieu(tuple(branches))
        if df.empty:
            st.info("Chưa có phiếu sửa chữa.")
        else:
            if tt_filter != "Tất cả":
                df = df[df["trang_thai"] == tt_filter]
            if search.strip():
                s = search.strip().lower()
                def _match_ma(ma):
                    try: return str(int(ma[2:])).endswith(s) if ma.startswith("SC") else s in ma.lower()
                    except: return s in str(ma).lower()
                mask = (df["ma_phieu"].apply(_match_ma) |
                        df["sdt_khach"].astype(str).str.lower().str.contains(s, na=False) |
                        df["ten_khach"].astype(str).str.lower().str.contains(s, na=False))
                df = df[mask]

            if df.empty:
                st.info("Không tìm thấy phiếu phù hợp.")
            else:
                view = df.rename(columns={
                    "ma_phieu": "Mã Phiếu", "chi_nhanh": "Chi Nhánh",
                    "ten_khach": "Khách hàng", "sdt_khach": "SĐT",
                    "loai_yeu_cau": "Loại", "hieu_dong_ho": "Hiệu ĐH",
                    "trang_thai": "Trạng Thái", "ngay_hen_tra": "Hẹn Trả",
                    "nguoi_tiep_nhan": "NV Tiếp Nhận"
                })
                cols = ["Mã Phiếu", "Chi Nhánh", "Khách hàng", "SĐT", "Loại",
                        "Hiệu ĐH", "Trạng Thái", "Hẹn Trả", "Ngày TN", "NV Tiếp Nhận"]
                cols = [c for c in cols if c in view.columns]
                st.dataframe(view[cols], use_container_width=True, hide_index=True, height=360)
                st.caption(f"Tổng: {len(df)} phiếu")

                st.markdown("---")
                st.caption("📋 Xem chi tiết dịch vụ / linh kiện của một phiếu:")
                ma_opts = view["Mã Phiếu"].tolist() if "Mã Phiếu" in view.columns else []
                picked_list = st.selectbox("Chọn phiếu:", ["-- Chọn --"] + ma_opts, key="sc_list_pick")
                if picked_list != "-- Chọn --":
                    ct_list = _load_chi_tiet(picked_list)
                    if ct_list.empty:
                        st.info("Phiếu này chưa có dịch vụ.")
                    else:
                        ct_list["Thành tiền"] = ct_list["so_luong"] * ct_list["don_gia"]
                        ct_view = ct_list.rename(columns={
                            "loai_dong": "Loại", "ten_hang": "Tên", "ma_hang": "Mã",
                            "so_luong": "SL", "don_gia": "Đơn giá"
                        })
                        vcols = ["Loại", "Tên", "Mã", "SL", "Đơn giá", "Thành tiền"]
                        vcols = [c for c in vcols if c in ct_view.columns]
                        st.dataframe(ct_view[vcols], use_container_width=True, hide_index=True)

    # ══════ TAB 2 — TẠO PHIẾU ══════
    with tab_create:
        cnt = st.session_state.get("sc_create_count", 0)
        cn_create = active
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_create = st.selectbox("Chi nhánh tiếp nhận:", accessible,
                                     index=accessible.index(active) if active in accessible else 0,
                                     key=f"sc_cn_create_{cnt}")

        ma_du_kien = _gen_ma_phieu()
        st.info(f"🏷️ Mã phiếu dự kiến: **{ma_du_kien}**")

        c1, c2 = st.columns(2)
        with c1:
            sdt_khach = st.text_input("Số điện thoại: *", key=f"sc_sdt_kh_{cnt}")
            sdt_prev_key = f"sc_sdt_prev_{cnt}"
            ten_key      = f"sc_ten_kh_{cnt}"
            kh_key       = f"sc_kh_found_{cnt}"
            if sdt_khach.strip() != st.session_state.get(sdt_prev_key, ""):
                st.session_state[sdt_prev_key] = sdt_khach.strip()
                kh_found = lookup_khach_hang(sdt_khach) if sdt_khach.strip() else None
                st.session_state[kh_key] = kh_found
                if kh_found:
                    st.session_state[ten_key] = kh_found["ten_kh"]
                else:
                    st.session_state[ten_key] = ""
                st.rerun()
            kh_found = st.session_state.get(kh_key)
            if sdt_khach.strip() and not kh_found:
                st.caption("⚠️ SĐT chưa có — khách mới sẽ được lưu tự động")
            hieu_dh  = st.text_input("Hiệu đồng hồ:", key=f"sc_hieu_dh_{cnt}",
                                      placeholder="Casio, Citizen, Seiko...")
            dac_diem = st.text_input("Đặc điểm (IMEI / mô tả):", key=f"sc_dac_diem_{cnt}",
                                      placeholder="Số serial, màu sắc, trầy xước...")
        with c2:
            ten_khach = st.text_input("Tên khách hàng: *", key=ten_key)
            loai_yc   = st.selectbox("Loại yêu cầu:", LOAI_YC_LIST, key=f"sc_loai_yc_{cnt}")
            ngay_hen  = st.date_input("Ngày hẹn trả:", key=f"sc_ngay_hen_{cnt}",
                                       value=None, format="DD/MM/YYYY")

        mo_ta = st.text_area("Mô tả lỗi / yêu cầu: *", key=f"sc_mo_ta_{cnt}",
                              placeholder="Mô tả chi tiết tình trạng đồng hồ...")
        tra_truoc = st.number_input("Khách trả trước (đ):", min_value=0, step=10000,
                                     key=f"sc_tra_truoc_{cnt}", value=0)
        if tra_truoc > 0:
            st.caption(f"= {int(tra_truoc):,}đ".replace(",","."))
        ghi_chu   = st.text_area("Ghi chú nội bộ:", key=f"sc_ghi_chu_nb_{cnt}",
                                  placeholder="Thợ kỹ thuật ghi chú...")

        st.markdown("**Dịch vụ / Linh kiện dự kiến:**")
        st.caption("Có thể bỏ trống — thêm sau khi thợ đánh giá")
        items_key = f"sc_items_{cnt}"
        st.session_state.setdefault(items_key, [])
        with st.expander(f"Danh sách ({len(st.session_state[items_key])} mục)",
                          expanded=len(st.session_state[items_key]) > 0):
            _hien_thi_items(items_key)
            st.markdown("---")
            _widget_them_dv(f"sc_new_{cnt}", items_key)

        items = st.session_state.get(items_key, [])
        if items:
            tong = sum(x["so_luong"] * x["don_gia"] for x in items)
            st.metric("Tổng dự kiến:", f"{tong:,}đ".replace(",","."))

        st.markdown("---")
        can_create = ten_khach.strip() and sdt_khach.strip() and mo_ta.strip()
        if st.button("✅ Tạo phiếu & In", type="primary", use_container_width=True,
                     disabled=not can_create):
            try:
                ma = _gen_ma_phieu()
                supabase.table("phieu_sua_chua").insert({
                    "ma_phieu": ma, "chi_nhanh": cn_create,
                    "ten_khach": ten_khach.strip(), "sdt_khach": sdt_khach.strip(),
                    "loai_yeu_cau": loai_yc, "hieu_dong_ho": hieu_dh.strip() or None,
                    "dac_diem": dac_diem.strip() or None, "mo_ta_loi": mo_ta.strip(),
                    "khach_tra_truoc": int(tra_truoc), "ghi_chu_noi_bo": ghi_chu.strip() or None,
                    "trang_thai": "Đang sửa", "nguoi_tiep_nhan": ho_ten,
                    "ngay_hen_tra": ngay_hen.isoformat() if ngay_hen else None,
                    "created_by": user.get("username",""),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }).execute()
                if items:
                    supabase.table("phieu_sua_chua_chi_tiet").insert(
                        [{"ma_phieu": ma, **item} for item in items]
                    ).execute()

                _upsert_khach_hang(ten_khach.strip(), sdt_khach.strip(), cn_create)

                ct_new = pd.DataFrame(items) if items else pd.DataFrame()
                if not ct_new.empty:
                    for col in ["so_luong","don_gia"]:
                        ct_new[col] = pd.to_numeric(ct_new[col], errors="coerce").fillna(0).astype(int)
                phieu_data = {
                    "ma_phieu": ma, "ten_khach": ten_khach.strip(),
                    "sdt_khach": sdt_khach.strip(), "hieu_dong_ho": hieu_dh.strip(),
                    "loai_yeu_cau": loai_yc, "dac_diem": dac_diem.strip(),
                    "mo_ta_loi": mo_ta.strip(), "khach_tra_truoc": int(tra_truoc),
                    "ngay_hen_tra": str(ngay_hen) if ngay_hen else None,
                    "nguoi_tiep_nhan": ho_ten,
                    "Ngày TN": (datetime.now() + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M"),
                }
                st.session_state["sc_pending_print_html"] = _build_phieu_html(phieu_data, ct_new)

                st.session_state["sc_create_count"] = cnt + 1
                st.session_state["sc_active_ma"] = ma
                st.cache_data.clear()
                log_action("SC_CREATE", f"ma={ma} kh={ten_khach} cn={cn_create}")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi tạo phiếu: {e}")

        if st.session_state.get("sc_pending_print_html"):
            _in_phieu_sc(st.session_state.pop("sc_pending_print_html"), key="sc_print_new")
            st.success(f"✓ Đã tạo phiếu — cửa sổ in đang mở")

    # ══════ TAB 3 — CHI TIẾT / CẬP NHẬT (chỉ phiếu chưa Hoàn thành) ══════
    with tab_detail:
        df_all = _load_phieu(tuple(accessible))
        df_chua_xong = df_all[df_all["trang_thai"] != "Hoàn thành"].copy() if not df_all.empty else df_all
        if df_chua_xong.empty:
            st.info("Không có phiếu nào đang xử lý.")
        else:
            search_dt = st.text_input("Tìm SĐT / Mã phiếu / Tên khách:", key="sc_search_dt",
                                       placeholder="VD: '900' tìm SC000900...")
            df_filtered = df_chua_xong.copy()
            if search_dt.strip():
                s = search_dt.strip().lower()
                def _match_ma2(ma):
                    try: return str(int(ma[2:])).endswith(s) if ma.startswith("SC") else s in ma.lower()
                    except: return s in str(ma).lower()
                mask = (df_filtered["ma_phieu"].apply(_match_ma2) |
                        df_filtered["sdt_khach"].astype(str).str.lower().str.contains(s, na=False) |
                        df_filtered["ten_khach"].astype(str).str.lower().str.contains(s, na=False))
                df_filtered = df_filtered[mask]

            if df_filtered.empty:
                st.info("Không tìm thấy phiếu phù hợp.")
            else:
                opts = [f"{r['ma_phieu']} · {r.get('ten_khach','')} · {r.get('trang_thai','')}"
                        for _, r in df_filtered.iterrows()]
                idx = 0
                saved = st.session_state.get("sc_active_ma")
                if saved:
                    for i, o in enumerate(opts):
                        if o.startswith(saved): idx = i; break

                picked = st.selectbox("Chọn phiếu:", opts, index=idx, key="sc_detail_pick")
                ma_pick = picked.split(" · ")[0]
                st.session_state["sc_active_ma"] = ma_pick

                phieu = df_chua_xong[df_chua_xong["ma_phieu"] == ma_pick].iloc[0]
                ct    = _load_chi_tiet(ma_pick)

                # ── Thông tin header ──
                st.markdown(f"#### {ma_pick} — {phieu.get('ten_khach','')} | {phieu.get('sdt_khach','')}")
                i1, i2, i3 = st.columns(3)
                with i1:
                    st.markdown(f"**Chi nhánh:** {phieu.get('chi_nhanh','')}")
                    st.markdown(f"**Hiệu ĐH:** {phieu.get('hieu_dong_ho') or '—'}")
                    st.markdown(f"**Đặc điểm:** {phieu.get('dac_diem') or '—'}")
                with i2:
                    st.markdown(f"**Loại YC:** {phieu.get('loai_yeu_cau','')}")
                    st.markdown(f"**Trả trước:** {int(phieu.get('khach_tra_truoc',0)):,}đ".replace(",","."))
                    st.markdown(f"**Hẹn trả:** {phieu.get('ngay_hen_tra') or '—'}")
                with i3:
                    st.markdown(f"**NV tiếp nhận:** {phieu.get('nguoi_tiep_nhan') or '—'}")
                    st.markdown(f"**Ngày TN:** {phieu.get('Ngày TN','—')}")
                    st.markdown(f"**Trạng thái:** {phieu.get('trang_thai','')}")
                st.markdown(f"**Mô tả lỗi:** {phieu.get('mo_ta_loi','')}")
                if phieu.get("ghi_chu_noi_bo"):
                    st.markdown(f"**Ghi chú nội bộ:** {phieu.get('ghi_chu_noi_bo','')}")

                # ── Bảng dịch vụ (chỉ đọc — summary) ──
                if not ct.empty:
                    st.markdown("**Dịch vụ / Linh kiện:**")
                    ct["Thành tiền"] = ct["so_luong"] * ct["don_gia"]
                    ct_view = ct.rename(columns={
                        "loai_dong": "Loại", "ten_hang": "Tên", "ma_hang": "Mã",
                        "so_luong": "SL", "don_gia": "Đơn giá", "ghi_chu": "Ghi chú"
                    })
                    vcols = ["Loại", "Tên", "Mã", "SL", "Đơn giá", "Thành tiền"]
                    vcols = [c for c in vcols if c in ct_view.columns]
                    st.dataframe(ct_view[vcols], use_container_width=True, hide_index=True)
                    tong = int(ct["Thành tiền"].sum())
                    con_lai = tong - int(phieu.get("khach_tra_truoc", 0))
                    m1, m2, m3 = st.columns(3)
                    with m1: st.metric("Tổng cộng", f"{tong:,}đ".replace(",","."))
                    with m2: st.metric("Đã trả trước", f"{int(phieu.get('khach_tra_truoc',0)):,}đ".replace(",","."))
                    with m3: st.metric("Còn lại", f"{con_lai:,}đ".replace(",","."))

                st.markdown("---")

                # ── Cập nhật phiếu ──
                if "sc_upd_open" not in st.session_state:
                    st.session_state["sc_upd_open"] = False
                with st.expander("✏️ Cập nhật phiếu", expanded=st.session_state["sc_upd_open"]):
                    cur_tt = phieu.get("trang_thai", "Đang sửa")
                    new_tt = st.selectbox("Trạng thái:", TRANG_THAI_LIST,
                                          index=TRANG_THAI_LIST.index(cur_tt) if cur_tt in TRANG_THAI_LIST else 0,
                                          key="sc_upd_tt")
                    new_gc  = st.text_area("Ghi chú nội bộ:", value=phieu.get("ghi_chu_noi_bo") or "",
                                            key="sc_upd_gc")
                    new_hen = st.date_input("Ngày hẹn trả:", key="sc_upd_hen",
                                             value=pd.to_datetime(phieu["ngay_hen_tra"]).date()
                                             if phieu.get("ngay_hen_tra") else None,
                                             format="DD/MM/YYYY")

                    # ── Dịch vụ đã lưu — có thể xóa ──
                    if not ct.empty:
                        st.markdown("**Dịch vụ / Linh kiện đã lưu:**")
                        for _, row in ct.iterrows():
                            ci1, ci2, ci3, ci4, ci5 = st.columns([2, 4, 1, 2, 1])
                            with ci1:
                                st.markdown(f"<span style='font-size:0.9rem'>{row.get('loai_dong','')}</span>", unsafe_allow_html=True)
                            with ci2:
                                st.markdown(f"<span style='font-size:0.9rem'>{row.get('ten_hang','')}</span>", unsafe_allow_html=True)
                            with ci3:
                                st.markdown(f"<span style='font-size:0.9rem'>x{int(row.get('so_luong',1))}</span>", unsafe_allow_html=True)
                            with ci4:
                                st.markdown(f"<span style='font-size:0.9rem'>{int(row.get('don_gia',0)):,}đ</span>".replace(",","."), unsafe_allow_html=True)
                            with ci5:
                                if st.button("✕", key=f"del_ct_{row['id']}"):
                                    try:
                                        supabase.table("phieu_sua_chua_chi_tiet").delete() \
                                            .eq("id", int(row["id"])).execute()
                                        st.cache_data.clear()
                                        log_action("SC_DEL_ITEM", f"ma={ma_pick} item={row.get('ten_hang','')}")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Lỗi xóa: {e}")
                        st.markdown("---")

                    # Thêm dịch vụ/linh kiện ngay trong cập nhật
                    st.markdown("**Thêm dịch vụ / Linh kiện:**")
                    _widget_them_dv("sc_upd_dv", "sc_upd_items")
                    upd_items = st.session_state.get("sc_upd_items", [])
                    _hien_thi_items("sc_upd_items")
                    if upd_items:
                        tong_moi = sum(x["so_luong"] * x["don_gia"] for x in upd_items)
                        st.caption(f"Tổng dịch vụ mới thêm: **{tong_moi:,}đ**".replace(",","."))

                    if st.button("💾 Lưu cập nhật", type="primary", use_container_width=True, key="sc_save_upd"):
                        try:
                            supabase.table("phieu_sua_chua").update({
                                "trang_thai":     new_tt,
                                "ghi_chu_noi_bo": new_gc.strip() or None,
                                "ngay_hen_tra":   new_hen.isoformat() if new_hen else None,
                                "updated_at":     datetime.now().isoformat(),
                            }).eq("ma_phieu", ma_pick).execute()

                            new_items = st.session_state.get("sc_upd_items", [])
                            if new_items:
                                supabase.table("phieu_sua_chua_chi_tiet").insert(
                                    [{"ma_phieu": ma_pick, **item} for item in new_items]
                                ).execute()
                                st.session_state["sc_upd_items"] = []

                            st.cache_data.clear()
                            log_action("SC_UPDATE", f"ma={ma_pick} trang_thai={new_tt}")
                            st.session_state["sc_upd_open"] = False
                            st.success("✓ Đã cập nhật!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi: {e}")

                # ── In phiếu ──
                if st.button("🖨️ In phiếu (A5)", use_container_width=True, key="sc_print_detail"):
                    _in_phieu_sc(_build_phieu_html(dict(phieu), ct), key="sc_print_d")
                st.caption("💡 Nếu thấy URL trên phiếu in: vào More settings → bỏ tick **Headers and footers**")

                # ── Xóa phiếu (admin only) ──
                if is_admin():
                    st.markdown("---")
                    if st.button("🗑️ Hủy / Xóa phiếu này", type="secondary",
                                 use_container_width=True, key="sc_delete"):
                        try:
                            supabase.table("phieu_sua_chua_chi_tiet").delete() \
                                .eq("ma_phieu", ma_pick).execute()
                            supabase.table("phieu_sua_chua").delete() \
                                .eq("ma_phieu", ma_pick).execute()
                            st.session_state.pop("sc_active_ma", None)
                            st.cache_data.clear()
                            log_action("SC_DELETE", f"ma={ma_pick}", level="warning")
                            st.success("Đã xóa phiếu."); st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi xóa: {e}")


    # ══════ TAB 4 — TẠO HÓA ĐƠN SỬA ══════
    with tab_hoadon:
        df_all_hd = _load_phieu(tuple(accessible))
        cho_giao = df_all_hd[df_all_hd["trang_thai"] == "Chờ giao khách"].copy() \
            if not df_all_hd.empty else pd.DataFrame()

        if cho_giao.empty:
            st.info("Không có phiếu nào ở trạng thái **Chờ giao khách**.")
            st.caption("Cập nhật trạng thái phiếu sang 'Chờ giao khách' ở tab Chi tiết / Cập nhật trước.")
        else:
            opts_hd = [f"{r['ma_phieu']} · {r.get('ten_khach','')} · {r.get('sdt_khach','')}"
                       for _, r in cho_giao.iterrows()]
            picked_hd = st.selectbox("Chọn phiếu:", opts_hd, key="sc_hd_pick")
            ma_hd_pick = picked_hd.split(" · ")[0]

            phieu_hd = cho_giao[cho_giao["ma_phieu"] == ma_hd_pick].iloc[0]
            ct_hd    = _load_chi_tiet(ma_hd_pick)

            st.markdown(f"**{ma_hd_pick}** — {phieu_hd.get('ten_khach','')} | {phieu_hd.get('sdt_khach','')}")
            st.caption(f"Hiệu ĐH: {phieu_hd.get('hieu_dong_ho') or '—'} · "
                       f"Mô tả: {phieu_hd.get('mo_ta_loi','')}")

            if ct_hd.empty:
                st.warning("Phiếu chưa có dịch vụ/linh kiện nào. Thêm trước ở tab Chi tiết.")
            else:
                ct_hd["Thành tiền"] = ct_hd["so_luong"] * ct_hd["don_gia"]
                ct_view = ct_hd.rename(columns={
                    "ten_hang": "Tên", "ma_hang": "Mã",
                    "so_luong": "SL", "don_gia": "Đơn giá"
                })
                vcols = ["Tên", "Mã", "SL", "Đơn giá", "Thành tiền"]
                vcols = [c for c in vcols if c in ct_view.columns]
                st.dataframe(ct_view[vcols], use_container_width=True, hide_index=True)

            tong_dv = int(ct_hd["Thành tiền"].sum()) if not ct_hd.empty else 0
            tra_truoc = int(phieu_hd.get("khach_tra_truoc", 0))

            st.markdown("---")
            st.markdown("**Thông tin hóa đơn:**")

            giam_gia = st.number_input("Giảm giá (đ):", min_value=0, step=10000,
                                        value=0, key="sc_hd_giam")
            if giam_gia > 0:
                st.caption(f"= {int(giam_gia):,}đ".replace(",","."))
            can_tra = max(0, tong_dv - giam_gia - tra_truoc)

            m1, m2, m3 = st.columns(3)
            with m1: st.metric("Tổng dịch vụ", f"{tong_dv:,}đ".replace(",","."))
            with m2: st.metric("Giảm giá + Trả trước", f"{giam_gia + tra_truoc:,}đ".replace(",","."))
            with m3: st.metric("Khách cần trả", f"{can_tra:,}đ".replace(",","."))

            st.markdown("**Phương thức thanh toán:**")
            chia_pttt = st.checkbox("Chia nhiều phương thức", key="sc_hd_chia")

            if not chia_pttt:
                pttt_chon = st.radio("PTTT:", ["Tiền mặt", "Chuyển khoản", "Thẻ"],
                                      horizontal=True, key="sc_hd_pttt")
                pttt = {
                    "tien_mat":      can_tra if pttt_chon == "Tiền mặt" else 0,
                    "chuyen_khoan":  can_tra if pttt_chon == "Chuyển khoản" else 0,
                    "the":           can_tra if pttt_chon == "Thẻ" else 0,
                }
            else:
                p1, p2, p3 = st.columns(3)
                with p1:
                    tm = st.number_input("Tiền mặt:", min_value=0, step=10000,
                                          value=can_tra, key="sc_hd_tm")
                    if tm > 0: st.caption(f"= {int(tm):,}đ".replace(",","."))
                with p2:
                    ck = st.number_input("Chuyển khoản:", min_value=0, step=10000,
                                          value=0, key="sc_hd_ck")
                    if ck > 0: st.caption(f"= {int(ck):,}đ".replace(",","."))
                with p3:
                    the = st.number_input("Thẻ:", min_value=0, step=10000,
                                           value=0, key="sc_hd_the")
                    if the > 0: st.caption(f"= {int(the):,}đ".replace(",","."))
                tong_pttt = tm + ck + the
                lech = tong_pttt - can_tra
                if lech != 0:
                    lech_label = f"Dư: +{lech:,}đ" if lech > 0 else f"Thiếu: {lech:,}đ"
                    st.warning(
                        f"Tổng cần trả: **{can_tra:,}đ** &nbsp;|&nbsp; "
                        f"Đã nhập: **{tong_pttt:,}đ** &nbsp;|&nbsp; {lech_label}".replace(",",".")
                    )
                pttt = {"tien_mat": tm, "chuyen_khoan": ck, "the": the}

            st.markdown("---")
            if st.button("✅ Tạo hóa đơn APSC", type="primary",
                          use_container_width=True, key="sc_hd_create",
                          disabled=ct_hd.empty):
                try:
                    apsc_ma = _tao_hoa_don_apsc(dict(phieu_hd), ct_hd, giam_gia, pttt)
                    supabase.table("phieu_sua_chua").update({
                        "trang_thai": "Hoàn thành",
                        "updated_at": (datetime.now() + timedelta(hours=7)).isoformat(),
                    }).eq("ma_phieu", ma_hd_pick).execute()
                    st.cache_data.clear()
                    log_action("SC_HOA_DON", f"ma={ma_hd_pick} apsc={apsc_ma}")
                    st.success(f"✓ Đã tạo hóa đơn **{apsc_ma}** — phiếu chuyển sang Hoàn thành!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi tạo hóa đơn: {e}")

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

def module_khach_hang():
    st.markdown("### 👥 Khách hàng")
    tab_list, tab_detail = st.tabs(["Danh sách", "Chi tiết khách"])

    with tab_list:
        search = st.text_input("Tìm SĐT / Tên / Mã KH:", key="kh_search",
                                placeholder="Nhập SĐT hoặc tên...")
        df = load_khach_hang_list()
        if df.empty:
            st.info("Chưa có khách hàng nào. Upload file từ tab Quản trị.")
        else:
            if search.strip():
                s = search.strip().lower()
                mask = (df["sdt"].astype(str).str.contains(s, na=False) |
                        df["ten_kh"].astype(str).str.lower().str.contains(s, na=False) |
                        df["ma_kh"].astype(str).str.lower().str.contains(s, na=False))
                df = df[mask]
            if df.empty:
                st.info("Không tìm thấy.")
            else:
                view = df.rename(columns={
                    "ma_kh": "Mã KH", "ten_kh": "Tên KH", "sdt": "SĐT",
                    "chi_nhanh_tao": "Chi Nhánh", "nhom_kh": "Nhóm",
                    "tong_ban": "Tổng mua", "diem_hien_tai": "Điểm",
                    "ngay_gd_cuoi": "GD Cuối"
                })
                cols = ["Mã KH", "Tên KH", "SĐT", "Chi Nhánh", "Nhóm",
                        "Tổng mua", "Điểm", "GD Cuối"]
                cols = [c for c in cols if c in view.columns]
                st.dataframe(view[cols], use_container_width=True, hide_index=True, height=420)
                st.caption(f"Tổng: {len(df)} khách")

    with tab_detail:
        search_dt = st.text_input("Tìm SĐT / Tên:", key="kh_detail_search",
                                   placeholder="Nhập SĐT để tra cứu...")
        df_all = load_khach_hang_list()
        if df_all.empty:
            st.info("Chưa có dữ liệu.")
        else:
            df_f = df_all.copy()
            if search_dt.strip():
                s = search_dt.strip().lower()
                mask = (df_f["sdt"].astype(str).str.contains(s, na=False) |
                        df_f["ten_kh"].astype(str).str.lower().str.contains(s, na=False))
                df_f = df_f[mask]

            if df_f.empty:
                st.info("Không tìm thấy khách.")
            else:
                opts = [f"{r['ma_kh']} · {r['ten_kh']} · {r['sdt']}"
                        for _, r in df_f.iterrows()]
                picked = st.selectbox("Chọn khách:", opts, key="kh_detail_pick")
                ma_pick = picked.split(" · ")[0]
                kh = df_all[df_all["ma_kh"] == ma_pick].iloc[0]

                # Helper lọc nan
                def _val(v):
                    if v is None: return "—"
                    s = str(v).strip()
                    return "—" if s.lower() in ("nan","none","") else s

                # Thông tin khách
                k1, k2, k3 = st.columns(3)
                with k1:
                    st.markdown(f"**Mã KH:** {_val(kh.get('ma_kh'))}")
                    st.markdown(f"**Tên:** {_val(kh.get('ten_kh'))}")
                    st.markdown(f"**SĐT:** {_val(kh.get('sdt'))}")
                with k2:
                    st.markdown(f"**Chi nhánh:** {_val(kh.get('chi_nhanh_tao'))}")
                    st.markdown(f"**Nhóm KH:** {_val(kh.get('nhom_kh'))}")
                    st.markdown(f"**Giới tính:** {_val(kh.get('gioi_tinh'))}")
                with k3:
                    st.markdown(f"**Tổng mua:** {int(kh.get('tong_ban',0)):,}đ".replace(',','.'))
                    st.markdown(f"**Điểm:** {int(kh.get('diem_hien_tai',0))}")
                    st.markdown(f"**GD cuối:** {_val(kh.get('ngay_gd_cuoi'))}")
                ghi_chu = _val(kh.get('ghi_chu'))
                if ghi_chu != "—":
                    st.markdown(f"**Ghi chú:** {ghi_chu}")

                st.markdown("---")

                # Lịch sử hóa đơn
                sdt_kh = str(kh.get("sdt",""))
                ten_kh = str(kh.get("ten_kh",""))
                try:
                    hd_data = load_hoa_don(tuple(get_accessible_branches()))
                    if not hd_data.empty:
                        # Match theo SĐT hoặc tên
                        mask_hd = (hd_data["Điện thoại"].astype(str).str.replace(" ","").str.contains(sdt_kh.replace(" ",""), na=False))
                        hd_kh = hd_data[mask_hd].copy()
                        if not hd_kh.empty:
                            st.markdown(f"**Lịch sử hóa đơn ({hd_kh['Mã hóa đơn'].nunique()} HĐ):**")
                            hd_view = hd_kh.drop_duplicates(subset=["Mã hóa đơn"]) \
                                [["Mã hóa đơn","Thời gian","Chi nhánh","Tổng tiền hàng","Trạng thái"]] \
                                .sort_values("Thời gian", ascending=False)
                            st.dataframe(hd_view, use_container_width=True, hide_index=True, height=200)
                        else:
                            st.caption("Chưa có hóa đơn.")
                except Exception: st.caption("Không tải được lịch sử HĐ.")

                # Lịch sử phiếu sửa chữa
                try:
                    sc_data = supabase.table("phieu_sua_chua").select(
                        "ma_phieu,trang_thai,mo_ta_loi,ngay_tiep_nhan,chi_nhanh"
                    ).eq("sdt_khach", sdt_kh).order("created_at", desc=True).execute()
                    if sc_data.data:
                        st.markdown(f"**Lịch sử sửa chữa ({len(sc_data.data)} phiếu):**")
                        sc_df = pd.DataFrame(sc_data.data)
                        # Format ngày tiếp nhận về giờ VN
                        if "ngay_tiep_nhan" in sc_df.columns:
                            sc_df["ngay_tiep_nhan"] = pd.to_datetime(
                                sc_df["ngay_tiep_nhan"], utc=True, errors="coerce"
                            ).dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d/%m/%Y %H:%M")
                        sc_df = sc_df.rename(columns={
                            "ma_phieu":"Mã Phiếu","trang_thai":"Trạng Thái",
                            "mo_ta_loi":"Mô tả","ngay_tiep_nhan":"Ngày TN",
                            "chi_nhanh":"Chi Nhánh"
                        })
                        st.dataframe(sc_df, use_container_width=True, hide_index=True, height=200)
                    else:
                        st.caption("Chưa có phiếu sửa chữa.")
                except Exception: st.caption("Không tải được lịch sử SC.")

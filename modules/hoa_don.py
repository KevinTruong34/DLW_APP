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

import plotly.graph_objects as go

def module_hoa_don():
    # Các tên cột có thể chứa "người bán" trong KiotViet
    NGUOI_BAN_COLS = ["Người bán", "Nhân viên bán", "Người tạo", "Nhân viên"]
    # Các tên cột tương ứng với 4 phương thức thanh toán (AQ-AT trong file KiotViet)
    PAYMENT_COLS = [
        ("Tiền mặt",      "💵"),
        ("Thẻ",           "💳"),
        ("Ví",            "📱"),
        ("Chuyển khoản",  "🏦"),
    ]

    def render_invoice(inv_df, code):
        row    = inv_df.iloc[0]
        status = row.get("Trạng thái","N/A")
        color  = "#1a7f37" if status=="Hoàn thành" else "#cf4c2c"

        # Lấy người bán nếu có
        nguoi_ban = ""
        for col in NGUOI_BAN_COLS:
            if col in inv_df.columns:
                val = row.get(col, "")
                if val and str(val).strip() and str(val).strip().lower() != "nan":
                    nguoi_ban = str(val).strip()
                    break

        # Lấy phương thức thanh toán — chỉ hiện cái > 0
        payments = []
        for col, icon in PAYMENT_COLS:
            if col in inv_df.columns:
                try:
                    val = float(row.get(col, 0) or 0)
                    if val > 0:
                        payments.append(f"{icon} {col}: <b>{val:,.0f}đ</b>".replace(",","."))
                except (ValueError, TypeError):
                    pass

        sdt_hd = str(row.get("Điện thoại","") or "").strip()
        if sdt_hd.lower() in ("nan","none",""): sdt_hd = ""

        ten_kh = row.get("Tên khách hàng","Khách lẻ") or "Khách lẻ"
        title_parts = [code, str(row.get("Thời gian","")), ten_kh]
        if sdt_hd:
            title_parts.append(f"SĐT: {sdt_hd}")

        with st.expander("  ·  ".join(title_parts), expanded=True):
            # Status badge + Người bán
            header_html = (
                f'<span style="background:{color};color:#fff;padding:3px 12px;'
                f'border-radius:20px;font-size:.8rem;font-weight:600;">{status}</span>'
            )
            if nguoi_ban:
                header_html += (
                    f'<span style="margin-left:10px;font-size:0.82rem;color:#555;">'
                    f'👤 <b>{nguoi_ban}</b></span>'
                )
            st.markdown(header_html, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            c1, c2, c3 = st.columns([4, 3, 3])
            c1.metric("Tổng tiền hàng", f"{row.get('Tổng tiền hàng',0):,.0f}đ".replace(",","."))
            gg = float(row.get("Giảm giá hóa đơn", 0) or 0)
            if gg > 0:
                c2.metric("Giảm giá HĐ", f"{gg:,.0f}đ".replace(",","."))
            else:
                c2.metric("Giảm giá HĐ", "0đ")
            c3.metric("Khách đã trả", f"{row.get('Khách đã trả',0):,.0f}đ".replace(",","."))

            # Phương thức thanh toán
            if payments:
                st.markdown(
                    f"<div style='background:#f8fafc;border-radius:6px;"
                    f"padding:8px 12px;margin:6px 0;font-size:0.85rem;color:#333;'>"
                    f"<b>Phương thức thanh toán:</b> "
                    + " · ".join(payments) + "</div>",
                    unsafe_allow_html=True
                )

            cols = ["Mã hàng","Tên hàng","Số lượng","Đơn giá","Thành tiền","Ghi chú hàng hóa"]
            dv = inv_df[[c for c in cols if c in inv_df.columns]].copy()
            for c in ["Đơn giá","Thành tiền"]:
                if c in dv.columns: dv[c] = dv[c].apply(lambda x: f"{x:,.0f}".replace(",","."))
            with st.expander("Chi tiết hàng hóa", expanded=False):
                st.dataframe(dv, use_container_width=True, hide_index=True)

    def render_list(res):
        ok  = res[res["Trạng thái"] != "Đã hủy"]
        huy = res[res["Trạng thái"] == "Đã hủy"]
        for code in ok["Mã hóa đơn"].unique():
            render_invoice(ok[ok["Mã hóa đơn"]==code], code)
        if not huy.empty:
            with st.expander(f"Hóa đơn đã hủy ({huy['Mã hóa đơn'].nunique()})", expanded=False):
                for code in huy["Mã hóa đơn"].unique():
                    render_invoice(huy[huy["Mã hóa đơn"]==code], code)

    def _render_recent(data, n=6):
        """Hiển thị n hóa đơn gần nhất theo thời gian (chưa bấm tìm)."""
        if "_ngay" in data.columns:
            # Lấy unique mã HĐ, sort theo ngày gần nhất
            recent_codes = (
                data.dropna(subset=["_ngay"])
                    .sort_values("_ngay", ascending=False)
                    ["Mã hóa đơn"].drop_duplicates().head(n).tolist()
            )
            res = data[data["Mã hóa đơn"].isin(recent_codes)]
            if not res.empty:
                st.caption(f"📋 {len(recent_codes)} hóa đơn gần nhất:")
                render_list(res)
            else:
                st.caption("Chưa có hóa đơn.")
        else:
            st.caption("Chưa có dữ liệu hóa đơn.")

    try:
        active = get_active_branch()
        accessible = get_accessible_branches()

        # Admin/kế toán có thể lọc theo CN; nhân viên chỉ thấy CN hiện tại
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_filter = st.selectbox(
                "Chi nhánh:", ["Tất cả"] + accessible,
                index=(accessible.index(active) + 1) if active in accessible else 0,
                key="hd_cn", label_visibility="collapsed"
            )
            load_cns = tuple(accessible) if cn_filter == "Tất cả" else (cn_filter,)
        else:
            load_cns = (active,)
            st.caption(f"📍 {active}")

        raw = load_hoa_don(branches_key=load_cns)
        if raw.empty:
            st.info("Chưa có dữ liệu hóa đơn."); return

        if st.session_state.get("so_dong_trung",0) > 0:
            st.caption(f"⚠ {st.session_state['so_dong_trung']} dòng trùng đã lọc.")

        data = raw.copy()
        data["SĐT_Search"] = data["Điện thoại"].fillna("").str.replace(r"\D+","",regex=True)

        t1,t2,t3 = st.tabs(["Số điện thoại","Mã hóa đơn","Ngày tháng"])
        with t1:
            phone = st.text_input("Số điện thoại:", key="in_phone", placeholder="Nhập số điện thoại...")
            if phone:
                res = data[data["SĐT_Search"].str.contains(phone.replace(" ",""),na=False)]
                if not res.empty:
                    st.caption(f"Khách hàng: **{res.iloc[0].get('Tên khách hàng','Khách lẻ')}**")
                    render_list(res)
                else: st.warning("Không tìm thấy số điện thoại.")
            else:
                # Chưa nhập → hiện 6 hóa đơn gần nhất theo Thời gian
                _render_recent(data, 6)
        with t2:
            inv = st.text_input("Mã hóa đơn:", key="in_inv", placeholder="VD: 1007 hoặc HD011007")
            if inv:
                res = data[data["Mã hóa đơn"].str.upper().str.endswith(inv.strip().upper(),na=False)]
                if not res.empty: render_list(res)
                else: st.warning("Không tìm thấy mã hóa đơn.")
            else:
                _render_recent(data, 6)
        with t3:
            ds = st.text_input("Ngày:", key="in_date", placeholder="VD: 14/04/2026")
            if ds:
                res = data[data["Thời gian"].astype(str).str.contains(ds.strip(),na=False)]
                if not res.empty:
                    st.caption(f"Tìm thấy {res['Mã hóa đơn'].nunique()} hóa đơn")
                    render_list(res)
                else: st.warning("Không có dữ liệu trong ngày này.")
            else:
                _render_recent(data, 6)
    except Exception as e:
        st.error(f"Lỗi: {e}")


# ==========================================
# MODULE: HÀNG HÓA
# ==========================================


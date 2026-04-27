import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

from utils.helpers import today_vn
from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches

import plotly.graph_objects as go

def module_tong_quan():
    """
    Tổng quan — welcome + tóm tắt nhanh.
    KHÔNG còn dashboard doanh số (đã chuyển sang Quản trị).
    """
    user   = get_user()
    active = get_active_branch()
    role_label = {
        "admin":     "Admin",
        "ke_toan":   "Kế toán",
        "nhan_vien": "Nhân viên"
    }.get(user.get("role"), "")

    # Greeting card
    st.markdown(
        f"<div style='background:#fff;border:1px solid #e8e8e8;border-radius:12px;"
        f"padding:18px 20px;margin-bottom:12px;'>"
        f"<div style='font-size:0.82rem;color:#888;'>Xin chào</div>"
        f"<div style='font-size:1.25rem;font-weight:700;color:#1a1a2e;margin-top:2px;'>"
        f"{user.get('ho_ten','')}</div>"
        f"<div style='margin-top:8px;'>"
        f"<span style='display:inline-block;background:#fff0f1;color:#e63946;"
        f"border-radius:16px;padding:3px 12px;font-size:0.78rem;font-weight:600;'>"
        f"{role_label}</span>"
        f"<span style='color:#888;font-size:0.85rem;margin-left:10px;'>"
        f"📍 {active}</span>"
        f"</div></div>",
        unsafe_allow_html=True
    )

    # Quick stats hôm nay (gọn — không phải dashboard đầy đủ)
    try:
        raw = load_hoa_don(branches_key=(active,))
        if not raw.empty and "_date" in raw.columns:
            today = today_vn()
            yest  = today - timedelta(days=1)
            ht    = raw[raw["Trạng thái"] == "Hoàn thành"].copy()

            def _stats(d):
                if d.empty: return 0, 0
                u = d.drop_duplicates(subset=["Mã hóa đơn"], keep="first")
                return int(u["Khách đã trả"].sum()), u["Mã hóa đơn"].nunique()

            dt_td, hd_td = _stats(ht[ht["_date"] == today])
            dt_ye, hd_ye = _stats(ht[ht["_date"] == yest])

            st.markdown(
                "<div style='font-size:0.82rem;font-weight:600;color:#555;"
                "margin:6px 0 8px;'>Chi nhánh hôm nay</div>",
                unsafe_allow_html=True
            )
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Doanh thu hôm nay",
                          f"{dt_td:,} đ" if dt_td < 1_000_000
                          else f"{dt_td/1_000_000:.2f} tr đ")
                st.caption(f"{hd_td} hóa đơn")
            with c2:
                st.metric("Hôm qua",
                          f"{dt_ye:,} đ" if dt_ye < 1_000_000
                          else f"{dt_ye/1_000_000:.2f} tr đ")
                st.caption(f"{hd_ye} hóa đơn")
        else:
            st.info("Chưa có dữ liệu hóa đơn tại chi nhánh này.")
    except Exception as e:
        st.caption(f"Chưa thể tải dữ liệu: {e}")

    # Hướng dẫn nhanh
    st.markdown(
        "<div style='background:#f9f9fb;border-radius:10px;padding:14px 16px;"
        "margin-top:16px;font-size:0.88rem;color:#555;line-height:1.6;'>"
        "<b style='color:#1a1a2e;'>Menu chức năng:</b><br>"
        "• <b>Hóa đơn</b> — tra cứu theo SĐT, mã hóa đơn, ngày<br>"
        "• <b>Hàng hóa</b> — tìm sản phẩm, xem tồn kho 3 chi nhánh<br>"
        "• <b>Chuyển hàng</b> — xem và tạo phiếu chuyển kho"
        + ("<br>• <b>Quản trị</b> — dashboard doanh số, upload dữ liệu, quản lý nhân viên"
           if is_admin() else "")
        + "</div>",
        unsafe_allow_html=True
    )


# ==========================================
# DASHBOARD (CHỈ ADMIN — trong Quản trị)
# ==========================================

def hien_thi_dashboard(show_filter: bool = True):
    accessible = get_accessible_branches()
    if show_filter and is_admin() and len(accessible) > 1:
        report_branches = st.multiselect(
            "Chi nhánh báo cáo:", accessible, default=accessible, key="db_cn")
        if not report_branches:
            st.warning("Chọn ít nhất một chi nhánh."); return
    else:
        report_branches = accessible if is_admin() else [get_active_branch()]

    try:
        raw = load_hoa_don(branches_key=tuple(report_branches))
        if raw.empty or "_date" not in raw.columns:
            st.info("Chưa có dữ liệu hóa đơn."); return

        today       = today_vn()
        yesterday   = today - timedelta(1)
        first_month = today.replace(day=1)
        first_last  = (first_month - timedelta(1)).replace(day=1)
        last_last   = first_month - timedelta(1)

        ky = st.selectbox("Kỳ xem:",
            ["Hôm nay","Hôm qua","7 ngày qua","Tháng này","Tháng trước"],
            index=3, label_visibility="collapsed")

        if ky=="Hôm nay":      df,dt,cf,ct,lb = today,today,yesterday,yesterday,"so với hôm qua"
        elif ky=="Hôm qua":    df,dt,cf,ct,lb = yesterday,yesterday,yesterday-timedelta(1),yesterday-timedelta(1),"so với hôm kia"
        elif ky=="7 ngày qua": df,dt,cf,ct,lb = today-timedelta(6),today,today-timedelta(13),today-timedelta(7),"so với 7 ngày trước"
        elif ky=="Tháng này":
            df,dt,cf = first_month,today,first_last
            try:    ct = first_last.replace(day=today.day)
            except: ct = last_last
            lb = "so với cùng kỳ tháng trước"
        else:
            df,dt = first_last,last_last
            m2f = (first_last-timedelta(1)).replace(day=1)
            cf,ct,lb = m2f,first_last-timedelta(1),"so với tháng trước nữa"

        ht   = raw[raw["Trạng thái"]=="Hoàn thành"].copy()
        d_ky = ht[(ht["_date"]>=df)&(ht["_date"]<=dt)]
        d_ss = ht[(ht["_date"]>=cf)&(ht["_date"]<=ct)]
        d_td = ht[ht["_date"]==today]
        d_ye = ht[ht["_date"]==yesterday]

        def tinh(d):
            if d.empty: return 0,0
            u = d.drop_duplicates(subset=["Mã hóa đơn"],keep="first")
            return u["Khách đã trả"].sum(), u["Mã hóa đơn"].nunique()

        def pct(a,b): return ((a-b)/b*100) if b else None

        dt_td,hd_td = tinh(d_td); dt_ye,_ = tinh(d_ye)
        dt_ky,hd_ky = tinh(d_ky); dt_ss,_ = tinh(d_ss)
        p_ye = pct(dt_td,dt_ye); p_ss = pct(dt_ky,dt_ss)

        st.markdown("#### Hôm nay")
        m1,m2,m3,m4 = st.columns(4)
        with m1: st.metric("Doanh thu",f"{dt_td:,.0f}"); st.caption(f"{hd_td} hóa đơn")
        with m2: st.metric("Trả hàng","0")
        with m3: st.metric("So hôm qua", f"{'↑' if (p_ye or 0)>=0 else '↓'} {abs(p_ye):.1f}%" if p_ye is not None else "—")
        with m4: st.metric(lb.capitalize(), f"{'↑' if (p_ss or 0)>=0 else '↓'} {abs(p_ss):.1f}%" if p_ss is not None else "—")

        st.caption(f"Doanh thu thuần kỳ này: **{dt_ky:,.0f} đ** ({hd_ky} hóa đơn)")

        if not d_ky.empty:
            base  = d_ky.drop_duplicates(subset=["Mã hóa đơn"],keep="first")
            chart = base.groupby(["_date","Chi nhánh"])["Khách đã trả"].sum().reset_index()
            chart.columns = ["Ngày","Chi nhánh","Doanh thu"]
            pivot = chart.pivot_table(index="Ngày",columns="Chi nhánh",values="Doanh thu",fill_value=0).sort_index()
            cmap  = {"100 Lê Quý Đôn":"#2E86DE","Coop Vũng Tàu":"#27AE60","GO BÀ RỊA":"#F39C12"}
            fig   = go.Figure()
            for i,cn in enumerate(pivot.columns):
                fig.add_trace(go.Bar(
                    x=[d.strftime("%d") for d in pivot.index], y=pivot[cn], name=CN_SHORT.get(cn,cn),
                    marker_color=cmap.get(cn,["#2E86DE","#27AE60","#F39C12"][i%3]),
                    hovertemplate=f"{cn}<br>Ngày %{{x}}<br>%{{y:,.0f}} đ<extra></extra>",
                ))
            fig.update_layout(
                barmode="stack", height=320,
                margin=dict(l=0,r=0,t=8,b=0),
                legend=dict(orientation="h",yanchor="bottom",y=-0.3,xanchor="center",x=0.5),
                yaxis=dict(tickformat=",.0f",gridcolor="#eee"),
                xaxis=dict(title=None,dtick=1),
                plot_bgcolor="white", font=dict(size=11), dragmode=False,
            )
            mx = pivot.sum(axis=1).max() if not pivot.empty else 0
            if mx >= 1_000_000:
                step = max(6_000_000, int(mx/8)//1_000_000*1_000_000)
                tvs  = list(range(0,int(mx+step),step))
                fig.update_layout(yaxis=dict(tickvals=tvs,ticktext=[f"{int(v/1_000_000)}tr" for v in tvs],gridcolor="#eee"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
        else:
            st.info("Không có dữ liệu trong kỳ này.")
    except Exception as e:
        st.error(f"Lỗi dashboard: {e}")


# ==========================================
# MODULE: HÓA ĐƠN — THÊM NGƯỜI BÁN
# ==========================================


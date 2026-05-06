import streamlit as st

from utils.config import ALL_BRANCHES, CN_SHORT
from utils.auth import (
    get_user,
    is_admin,
    get_active_branch,
    get_selectable_branches,
    do_logout,
    save_branch_to_url,
    run_auth_gate,
)

from modules.tong_quan import module_tong_quan
from modules.hoa_don import module_hoa_don
from modules.hang_hoa import module_hang_hoa
from modules.sua_chua import module_sua_chua
from modules.nhap_hang import module_nhap_hang
from modules.khach_hang import module_khach_hang
from modules.kiem_ke import module_kiem_ke
from modules.chuyen_hang import module_chuyen_hang
from modules.bao_cao import module_bao_cao
from modules.quan_tri import module_quan_tri
from modules.nhan_vien import module_nhan_vien


APP_TITLE = "DL Watch Store"

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root { color-scheme: light only !important; }
    html, body, .stApp, [data-testid="stAppViewContainer"] {
        background: #f5f6f8 !important;
        color: #1a1a2e !important;
        color-scheme: light only !important;
    }
    header, footer, #stDecoration, .stAppDeployButton,
    [data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="stElementToolbar"], [data-testid="stDecoration"] {
        display: none !important;
    }
    .block-container {
        padding: 0.6rem 0.8rem 1.2rem 0.8rem !important;
        max-width: 1350px !important;
    }
    [data-testid="stBaseButton-primary"] {
        background: #e63946 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        color: #fff !important;
    }
    [data-testid="stBaseButton-secondary"] {
        border-radius: 8px !important;
        border: 1px solid #ddd !important;
        background: #fff !important;
        color: #1a1a2e !important;
    }
    [data-testid="stTabs"] [data-testid="stTab"] {
        font-size: 0.88rem !important;
        font-weight: 500 !important;
    }
    [data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {
        color: #e63946 !important;
        border-bottom-color: #e63946 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

run_auth_gate()

user = get_user() or {}
active_cn = get_active_branch()
sel_cns = get_selectable_branches()
cn_short = CN_SHORT.get(active_cn, active_cn[:8])
ho_ten = user.get("ho_ten", "")
initials = "".join(w[0].upper() for w in ho_ten.split()[:2]) if ho_ten else "?"
role_lbl = {"admin": "Admin", "ke_toan": "Kế toán", "nhan_vien": "Nhân viên"}.get(user.get("role", ""), "")

col_reload, col_title, col_avatar = st.columns([1, 3, 1])
with col_reload:
    if st.button("↺ Tải lại", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with col_title:
    st.markdown(f"### {APP_TITLE}")
    st.caption(f"📍 {cn_short}")
with col_avatar:
    with st.popover(initials, use_container_width=True):
        st.markdown(
            f"<div style='text-align:center;padding:8px 0 4px;'>"
            f"<div style='font-size:1.05rem;font-weight:700;'>{ho_ten}</div>"
            f"<div style='font-size:0.8rem;color:#888;'>{role_lbl}</div>"
            f"<div style='font-size:0.78rem;color:#aaa;margin-top:2px;'>📍 {active_cn}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        if len(sel_cns) > 1:
            st.caption("Đổi chi nhánh:")
            for cn in sel_cns:
                is_active_cn = (cn == active_cn)
                lbl = f"✓ {cn}" if is_active_cn else cn
                if st.button(lbl, key=f"sw_cn_{cn}", use_container_width=True,
                             type="primary" if is_active_cn else "secondary",
                             disabled=is_active_cn):
                    st.session_state["active_chi_nhanh"] = cn
                    save_branch_to_url(cn)
                    st.session_state.pop("ck_items", None)
                    st.rerun()
            st.markdown("---")
        if st.button("🚪 Đăng xuất", use_container_width=True, key="btn_logout_pop"):
            do_logout()
            st.rerun()

st.markdown("<hr style='margin:4px 0 10px 0;'>", unsafe_allow_html=True)

menu = [
    "📊 Tổng quan",
    "🧾 Hóa đơn",
    "📦 Hàng hóa",
    "🔄 Chuyển hàng",
    "🧮 Kiểm kê",
    "🔧 Sửa chữa",
    "👥 Khách hàng",
    "📥 Nhập/Trả hàng",
    "📊 Báo cáo",
    "👥 Nhân viên",
]
if is_admin():
    menu.append("⚙️ Quản trị")

page = st.pills("nav", menu, default=menu[0], label_visibility="collapsed") or menu[0]
page_clean = page.split(" ", 1)[1] if " " in page else page

if page_clean == "Tổng quan":
    module_tong_quan()
elif page_clean == "Hóa đơn":
    module_hoa_don()
elif page_clean == "Hàng hóa":
    module_hang_hoa()
elif page_clean == "Chuyển hàng":
    module_chuyen_hang()
elif page_clean == "Kiểm kê":
    module_kiem_ke()
elif page_clean == "Sửa chữa":
    module_sua_chua()
elif page_clean == "Khách hàng":
    module_khach_hang()
elif page_clean == "Nhập/Trả hàng":
    module_nhap_hang()
elif page_clean == "Báo cáo":
    module_bao_cao()
elif page_clean == "Nhân viên":
    module_nhan_vien()
elif page_clean == "Quản trị":
    module_quan_tri()

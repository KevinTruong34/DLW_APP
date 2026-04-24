import streamlit as st
from utils.config import ALL_BRANCHES, CN_SHORT

st.set_page_config(
    page_title="DL Watch Store",
    page_icon="static/favicon.png",
    layout="wide"
)

st.markdown("""
<style>
/* ══════════════════════════════════════════
   PHIEN BAN: 15.0 — Force light theme
   ══════════════════════════════════════════ */

/* ── FORCE LIGHT MODE (fix Edge dark stuck) ── */
:root {
    color-scheme: light only !important;
    --bg-main: #f5f6f8;
    --bg-card: #ffffff;
    --text-main: #1a1a2e;
    --text-muted: #888;
    --border: #e8e8e8;
    --accent: #e63946;
}
html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: #f5f6f8 !important;
    color: #1a1a2e !important;
    color-scheme: light only !important;
}
@media (prefers-color-scheme: dark) {
    html, body, .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stMain"], .main, .block-container {
        background: #f5f6f8 !important;
        color: #1a1a2e !important;
    }
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMarkdownContainer"] div,
    [data-testid="stText"], .stText {
        color: #1a1a2e !important;
    }
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
        color: #1a1a2e !important;
    }
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input,
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background: #fff !important;
        color: #1a1a2e !important;
    }
    [data-testid="stExpander"] {
        background: #fff !important;
        color: #1a1a2e !important;
    }
    [data-testid="stDataFrame"] {
        background: #fff !important;
    }
}

/* ── Ẩn chrome Streamlit ── */
header, footer, #stDecoration, .stAppDeployButton,
[data-testid="stHeader"], [data-testid="stToolbar"],
[data-testid="stElementToolbar"], [data-testid="stDecoration"]
{ display: none !important; }

/* ── Base ── */
html, body { overflow-x: hidden !important; max-width: 100vw !important; }
*, *::before, *::after { box-sizing: border-box; }

/* ── Layout ── */
.block-container {
    padding: 0.6rem 0.8rem 1.5rem 0.8rem !important;
    max-width: 1350px !important;
}

/* ── Metric ── */
[data-testid="stMetricValue"] { font-size: 1.25rem !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { font-size: 0.78rem !important; color: #888 !important; }

/* ── Search input ── */
[data-testid="stTextInput"] input {
    font-size: 0.95rem !important;
    padding: 0.55rem 0.75rem !important;
    border-radius: 8px !important;
    border: 1px solid #e0e0e0 !important;
    background: #fff !important;
    color: #1a1a2e !important;
}
[data-testid="stTextArea"] textarea {
    background: #fff !important;
    color: #1a1a2e !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 8px !important;
}
[data-testid="stNumberInput"] input {
    background: #fff !important;
    color: #1a1a2e !important;
}

/* ── Buttons ── */
[data-testid="stBaseButton-primary"] {
    background: #e63946 !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    color: #fff !important;
}
[data-testid="stBaseButton-primary"]:hover {
    background: #c1121f !important;
}
[data-testid="stBaseButton-secondary"] {
    border-radius: 8px !important;
    border: 1px solid #ddd !important;
    background: #fff !important;
    color: #1a1a2e !important;
}
[data-testid="stBaseButton-secondary"]:hover {
    background: #f9f9f9 !important;
    border-color: #bbb !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [data-testid="stTab"] {
    font-size: 0.88rem !important;
    font-weight: 500 !important;
}
[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {
    color: #e63946 !important;
    border-bottom-color: #e63946 !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 8px !important; overflow: hidden !important; }
[data-testid="stDataFrame"] > div { overscroll-behavior: contain !important; }
iframe { touch-action: pan-y; }

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #e8e8e8 !important;
    border-radius: 8px !important;
    background: #fff !important;
}

/* ── Divider ── */
hr { border-color: #ebebeb !important; margin: 8px 0 !important; }

/* ── Caption ── */
[data-testid="stCaptionContainer"] { color: #888 !important; font-size: 0.78rem !important; }

/* ── Info/Warning/Success ── */
[data-testid="stAlert"] { border-radius: 8px !important; }

/* ── Login form: bỏ chữ "None" dưới form ── */
[data-testid="stForm"] > div:empty { display: none !important; }
[data-testid="stForm"] { border: none !important; padding: 0 !important; }

/* ── Mobile ── */
@media (max-width: 640px) {
    .block-container { padding: 0.4rem 0.5rem 1rem 0.5rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.05rem !important; }
}

/* ── Card utility ── */
.ws-card {
    background: #fff;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 14px 16px;
    margin: 8px 0;
}
.ws-tag {
    display: inline-block;
    background: #fff0f1;
    color: #e63946;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.75rem;
    font-weight: 600;
}
.ws-badge-green { color: #1a7f37; font-weight: 700; font-size: 1.1rem; }
.ws-badge-red   { color: #cf4c2c; font-weight: 700; font-size: 1.1rem; }
.ws-badge-gray  { color: #aaa;    font-weight: 700; font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)


# ── Auth gate — phải chạy trước khi import modules ──
from utils.auth import (get_user, is_admin, get_active_branch,
                        get_accessible_branches, get_selectable_branches,
                        do_logout, save_branch_to_url, run_auth_gate)
from utils.db import supabase, log_action

run_auth_gate()

# ── Import modules sau khi auth đã xác nhận user ──
from modules.tong_quan   import module_tong_quan, hien_thi_dashboard
from modules.hoa_don     import module_hoa_don
from modules.hang_hoa    import module_hang_hoa
from modules.sua_chua    import module_sua_chua
from modules.nhap_hang   import module_nhap_hang
from modules.khach_hang  import module_khach_hang
from modules.kiem_ke     import module_kiem_ke
from modules.chuyen_hang import module_chuyen_hang
from modules.quan_tri    import module_quan_tri

# ── Navigation ──
# ==========================================
# NAVIGATION  v15.0
# ==========================================

user      = get_user()
active_cn = get_active_branch()
sel_cns   = get_selectable_branches()
cn_short  = CN_SHORT.get(active_cn, active_cn[:8])
ho_ten    = user.get("ho_ten","") if user else ""
initials  = "".join(w[0].upper() for w in ho_ten.split()[:2]) if ho_ten else "?"
role_lbl  = {"admin":"Admin","ke_toan":"Kế toán","nhan_vien":"Nhân viên"}.get(
    user.get("role",""), "")

# Menu: BỎ Tổng quan khỏi vị trí có dashboard — chỉ còn welcome
# Sắp xếp thứ tự theo ý anh: Tổng quan -> Hóa đơn -> Hàng hóa -> Chuyển hàng -> Kiểm kê
menu = ["📊 Tổng quan", "🧾 Hóa đơn", "📦 Hàng hóa", "🔄 Chuyển hàng", "🧮 Kiểm kê", "🔧 Sửa chữa", "👥 Khách hàng", "📥 Nhập hàng"]

if is_admin():
    menu.append("⚙️ Quản trị")

page = st.pills("nav", menu, default=menu[0], label_visibility="collapsed")

# ── Hàng 2: reload + avatar ──
col_rel, col_avatar = st.columns([1, 1])

with col_rel:
    if st.button("↺  Tải lại", use_container_width=True, help="Tải lại dữ liệu"):
        st.cache_data.clear(); st.rerun()

with col_avatar:
    with st.popover(initials, use_container_width=True):
        st.markdown(
            f"<div style='text-align:center;padding:8px 0 4px;'>"
            f"<div style='font-size:1.1rem;font-weight:700;'>{ho_ten}</div>"
            f"<div style='font-size:0.8rem;color:#888;'>{role_lbl}</div>"
            f"<div style='font-size:0.78rem;color:#aaa;margin-top:2px;'>"
            f"📍 {active_cn}</div>"
            f"</div>",
            unsafe_allow_html=True)
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
                    # reset giỏ tạo phiếu khi đổi CN
                    st.session_state.pop("ck_items", None)
                    st.rerun()
            st.markdown("---")

        if st.button("🚪 Đăng xuất", use_container_width=True, key="btn_logout_pop"):
            do_logout(); st.rerun()

# strip icon từ page value để routing
page = page or menu[0]  # fallback nếu pills trả None
page_clean = page.split(" ", 1)[1] if " " in page else page
st.markdown("<hr style='margin:4px 0 10px 0;'>", unsafe_allow_html=True)

if page_clean == "Tổng quan":     module_tong_quan()
elif page_clean == "Hóa đơn":     module_hoa_don()
elif page_clean == "Hàng hóa":    module_hang_hoa()
elif page_clean == "Chuyển hàng": module_chuyen_hang()
elif page_clean == "Quản trị":    module_quan_tri()
elif page_clean == "Kiểm kê":     module_kiem_ke()
elif page_clean == "Sửa chữa":    module_sua_chua()
elif page_clean == "Khách hàng":  module_khach_hang()
elif page_clean == "Nhập hàng":   module_nhap_hang()

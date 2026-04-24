import streamlit as st
import streamlit.components.v1 as components
import streamlit.components.v1 as components
from utils.config import ALL_BRANCHES, CN_SHORT

st.set_page_config(
    page_title="DL Watch Store",
    page_icon="static/favicon.png",
    layout="wide"
)

APPLE_ICON_B64 = "data:image/png;base64,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"
components.html(
    "<script>"
    "var d=window.parent.document;"
    "var l=d.querySelector(\"link[rel~='apple-touch-icon']\");"
    "if(!l){l=d.createElement('link');l.rel='apple-touch-icon';d.head.appendChild(l);}"
    "l.href='" + APPLE_ICON_B64 + "';"
    "</script>",
    height=0, width=0
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

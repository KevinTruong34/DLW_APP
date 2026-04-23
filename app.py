import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime, timedelta
import numpy as np
import bcrypt
import uuid
import logging

# ==========================================
# LOGGING — ghi ra stdout (Streamlit Cloud lưu ~7 ngày)
# ==========================================
# Format: [thời gian] [level] [user@chi_nhanh] action: chi tiết
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger("watchstore")


def log_action(action: str, detail: str = "", level: str = "info"):
    """
    Ghi log hành động của user.
    Prefix tự động [username@chi_nhanh] để biết ai làm gì.
    """
    user = st.session_state.get("user") or {}
    cn   = st.session_state.get("active_chi_nhanh", "-")
    username = user.get("username", "anonymous")
    prefix = f"[{username}@{cn}]"
    msg = f"{prefix} {action}"
    if detail:
        msg += f" — {detail}"
    getattr(_logger, level, _logger.info)(msg)

# ==========================================
# PHIEN BAN: 15.0 — Fix UI + Tao phieu chuyen
# ==========================================

st.set_page_config(page_title="Watch Store", layout="wide")

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
    max-width: 900px !important;
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


# ==========================================
# SUPABASE
# ==========================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error("Chưa cấu hình SUPABASE_URL và SUPABASE_KEY trong Streamlit Secrets!")
    st.stop()

ALL_BRANCHES = ["100 Lê Quý Đôn", "Coop Vũng Tàu", "GO BÀ RỊA"]
CN_SHORT = {
    "100 Lê Quý Đôn": "Lê Quý Đôn",
    "Coop Vũng Tàu":  "Coop VT",
    "GO BÀ RỊA":      "GO Bà Rịa",
}

# Marker phân biệt phiếu tạo trong app (ảnh hưởng tồn kho hiệu dụng)
# vs phiếu upload từ KiotViet (đã được phản ánh trong the_kho)
IN_APP_MARKER = "Chuyển hàng (App)"
ARCHIVED_MARKER = "Chuyển hàng (App - đã đồng bộ)"


# ==========================================
# SESSION TOKEN (URL-based — đơn giản, ổn định)
# ==========================================
#
# Security notes:
# - Token UUID4 128-bit — không đoán được
# - Session trong DB expire sau 3 ngày (giảm từ 30 ngày)
# - Logout xóa session khỏi DB → token cũ không dùng được kể cả khi lộ
# - Rủi ro: token lộ qua URL share/screenshot/history → mitigation là
#   expiry ngắn + khuyến cáo nhân viên không share URL.

SESSION_EXPIRY_DAYS = 3

def get_token_from_url():
    """Đọc session token từ URL query params."""
    return st.query_params.get("token")


def save_token_to_url(token: str):
    """Lưu token vào URL query params."""
    st.query_params["token"] = token


def save_branch_to_url(branch: str):
    """Lưu chi nhánh vào URL query params."""
    st.query_params["branch"] = branch


def get_branch_from_url():
    """Đọc chi nhánh từ URL query params."""
    return st.query_params.get("branch")


def clear_session_params():
    """Xóa token + branch khỏi URL khi logout."""
    for k in ("token", "branch"):
        if k in st.query_params:
            del st.query_params[k]


# ==========================================
# SCROLL-TO-BOTTOM RELOAD
# ==========================================



# ==========================================
# AUTH
# ==========================================

def verify_password(plain, hashed):
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False

def hash_password(plain):
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def create_session_token(nv_id):
    token = str(uuid.uuid4())
    supabase.table("sessions").insert({
        "token": token,
        "nhan_vien_id": nv_id,
        "expires_at": (datetime.utcnow() + timedelta(days=SESSION_EXPIRY_DAYS)).isoformat()
    }).execute()
    return token

def delete_session(token):
    supabase.table("sessions").delete().eq("token", token).execute()

def load_user_by_id(nv_id):
    res = supabase.table("nhan_vien").select("*").eq("id", nv_id).eq("active", True).execute()
    if not res.data:
        return None
    u = res.data[0]; u.pop("mat_khau", None)
    cn = supabase.table("nhan_vien_chi_nhanh") \
        .select("chi_nhanh(ten)").eq("nhan_vien_id", nv_id).execute()
    u["chi_nhanh_list"] = [x["chi_nhanh"]["ten"] for x in cn.data] if cn.data else []
    return u

def restore_session(token):
    try:
        res = supabase.table("sessions").select("nhan_vien_id,expires_at").eq("token", token).execute()
        if not res.data: return None
        s = res.data[0]
        if datetime.fromisoformat(s["expires_at"].replace("Z","+00:00")).replace(tzinfo=None) < datetime.utcnow():
            delete_session(token); return None
        return load_user_by_id(s["nhan_vien_id"])
    except Exception:
        return None

def do_login(username, password):
    try:
        res = supabase.table("nhan_vien").select("*").eq("username", username).eq("active", True).execute()
        if not res.data:
            _logger.warning(f"LOGIN_FAIL — username={username} (không tồn tại/bị khóa)")
            return None, "Tài khoản không tồn tại hoặc đã bị khóa."
        u = res.data[0]
        if not verify_password(password, u["mat_khau"]):
            _logger.warning(f"LOGIN_FAIL — username={username} (sai mật khẩu)")
            return None, "Mật khẩu không chính xác."
        u.pop("mat_khau", None)
        cn = supabase.table("nhan_vien_chi_nhanh") \
            .select("chi_nhanh(ten)").eq("nhan_vien_id", u["id"]).execute()
        u["chi_nhanh_list"] = [x["chi_nhanh"]["ten"] for x in cn.data] if cn.data else []
        _logger.info(f"LOGIN_OK — username={username} role={u.get('role','?')}")
        return u, None
    except Exception as e:
        _logger.error(f"LOGIN_ERROR — username={username}: {e}")
        return None, f"Lỗi hệ thống: {e}"

def do_logout():
    user = st.session_state.get("user") or {}
    username = user.get("username", "?")
    _logger.info(f"LOGOUT — username={username}")
    token = get_token_from_url()
    if token: delete_session(token)
    clear_session_params()
    st.session_state.clear()


# ==========================================
# SESSION HELPERS
# ==========================================

def get_user(): return st.session_state.get("user")
def is_admin(): u = get_user(); return u and u.get("role") == "admin"
def is_ke_toan_or_admin(): u = get_user(); return u and u.get("role") in ("admin","ke_toan")
def get_active_branch(): return st.session_state.get("active_chi_nhanh","")

def get_accessible_branches():
    u = get_user()
    if not u: return []
    return ALL_BRANCHES if u.get("role") == "admin" else u.get("chi_nhanh_list", [])

def get_selectable_branches():
    return get_accessible_branches()


# ==========================================
# FIRST RUN
# ==========================================

def is_first_run():
    try:
        return (supabase.table("nhan_vien").select("id",count="exact").execute().count or 0) == 0
    except: return False

def show_first_run():
    st.title("Khởi tạo hệ thống")
    st.info("Chưa có tài khoản nào. Tạo tài khoản Admin để bắt đầu.")
    with st.form("setup", clear_on_submit=False, border=False):
        u = st.text_input("Username:"); n = st.text_input("Họ tên:")
        p = st.text_input("Mật khẩu:", type="password")
        p2 = st.text_input("Xác nhận:", type="password")
        if st.form_submit_button("Tạo tài khoản Admin", type="primary"):
            if not all([u,n,p,p2]): st.error("Điền đầy đủ.")
            elif p != p2: st.error("Mật khẩu không khớp.")
            elif len(p) < 6: st.error("Tối thiểu 6 ký tự.")
            else:
                try:
                    supabase.table("nhan_vien").insert({
                        "username":u,"ho_ten":n,"mat_khau":hash_password(p),"role":"admin","active":True
                    }).execute()
                    st.success("Tạo thành công! Hãy đăng nhập."); st.rerun()
                except Exception as e: st.error(f"Lỗi: {e}")


# ==========================================
# LOGIN
# ==========================================

def show_login():
    """
    Form đăng nhập kết hợp — 2 giai đoạn:
    1. Nhập username + password → verify
    2. Sau khi verify đúng, hiện dropdown chi nhánh → chọn + submit
    Lợi ích:
    - Gộp login + chọn CN thành 1 flow liền mạch
    - Không lộ danh sách chi nhánh với người không có tài khoản
    - Sau khi xong, lưu cả token + chi nhánh vào URL để F5 khôi phục đủ
    """
    # Đẩy form xuống giữa trang cho thoáng
    st.markdown("<div style='padding-top: 15vh;'></div>", unsafe_allow_html=True)

    st.title("Đăng nhập")

    # Giai đoạn 1: nếu chưa xác thực user
    pending_user = st.session_state.get("_pending_user")

    if not pending_user:
        with st.form("login_step1", clear_on_submit=False, border=False):
            u = st.text_input("Tài khoản:", placeholder="Nhập tên tài khoản")
            p = st.text_input("Mật khẩu:", type="password", placeholder="Nhập mật khẩu")
            submitted = st.form_submit_button(
                "Tiếp tục", type="primary", use_container_width=True
            )
            if submitted:
                if not u or not p:
                    st.error("Nhập đầy đủ.")
                else:
                    with st.spinner("Đang xác thực..."):
                        user, err = do_login(u, p)
                    if err:
                        st.error(err)
                    else:
                        branches = (ALL_BRANCHES if user.get("role") == "admin"
                                   else user.get("chi_nhanh_list", []))
                        if not branches:
                            st.error("Tài khoản chưa được gán chi nhánh. "
                                    "Liên hệ admin để được hỗ trợ.")
                        elif len(branches) == 1:
                            # Chỉ có 1 CN — login + set active luôn, không cần hỏi
                            _finalize_login(user, branches[0])
                        else:
                            # Chuyển sang giai đoạn 2 (chọn chi nhánh)
                            st.session_state["_pending_user"] = user
                            st.rerun()
    else:
        # Giai đoạn 2: đã verify user, chọn chi nhánh
        branches = (ALL_BRANCHES if pending_user.get("role") == "admin"
                   else pending_user.get("chi_nhanh_list", []))

        st.markdown(
            f"<div style='text-align:center;padding:8px 0 16px 0;'>"
            f"<div style='font-size:1.05rem;font-weight:600;color:#1a1a2e;'>"
            f"Xin chào, {pending_user.get('ho_ten','')}</div>"
            f"<div style='font-size:0.85rem;color:#888;margin-top:2px;'>"
            f"Chọn chi nhánh để bắt đầu</div>"
            f"</div>",
            unsafe_allow_html=True
        )

        for i, branch in enumerate(branches):
            if st.button(branch, key=f"login_cn_{i}",
                        use_container_width=True, type="secondary"):
                _finalize_login(pending_user, branch)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← Quay lại", key="login_back",
                    use_container_width=True):
            st.session_state.pop("_pending_user", None)
            st.rerun()


def _finalize_login(user: dict, branch: str):
    """Hoàn tất login: tạo session, lưu token + chi nhánh vào URL."""
    token = create_session_token(user["id"])
    st.session_state["user"] = user
    st.session_state["active_chi_nhanh"] = branch
    st.session_state.pop("_pending_user", None)

    save_token_to_url(token)
    save_branch_to_url(branch)

    st.rerun()


# ==========================================
# SESSION RESTORE
# ==========================================

if "user" not in st.session_state:
    # Đọc token từ URL
    token = get_token_from_url()

    if token:
        user = restore_session(token)
        if user:
            st.session_state["user"] = user
            # Khôi phục chi nhánh từ URL (nếu có và hợp lệ)
            saved_branch = get_branch_from_url()
            if saved_branch:
                accessible = (ALL_BRANCHES if user.get("role") == "admin"
                             else user.get("chi_nhanh_list", []))
                if saved_branch in accessible:
                    st.session_state["active_chi_nhanh"] = saved_branch
        else:
            # Token invalid/expired → dọn sạch URL
            clear_session_params()

if "user" not in st.session_state:
    show_first_run() if is_first_run() else show_login()
    st.stop()

# Nếu user đã login nhưng chưa có active_chi_nhanh (edge case: chi nhánh
# trong URL không hợp lệ hoặc đã bị xóa khỏi quyền) → hiện form chọn lại
if "active_chi_nhanh" not in st.session_state:
    user = get_user()
    branches = (ALL_BRANCHES if user.get("role") == "admin"
               else user.get("chi_nhanh_list", []))
    if len(branches) == 1:
        st.session_state["active_chi_nhanh"] = branches[0]
        save_branch_to_url(branches[0])
        st.rerun()
    elif branches:
        # Đẩy form xuống giữa trang
        st.markdown("<div style='padding-top: 15vh;'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='text-align:center;padding:20px 0;'>"
            f"<div style='font-size:1.05rem;font-weight:600;'>"
            f"Xin chào, {user.get('ho_ten','')}</div>"
            f"<div style='font-size:0.85rem;color:#888;margin-top:2px;'>"
            f"Chọn chi nhánh để bắt đầu</div></div>",
            unsafe_allow_html=True
        )
        for i, branch in enumerate(branches):
            if st.button(branch, key=f"re_cn_{i}",
                        use_container_width=True, type="secondary"):
                st.session_state["active_chi_nhanh"] = branch
                save_branch_to_url(branch)
                st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Đăng xuất", key="re_logout",
                    use_container_width=True):
            do_logout(); st.rerun()
        st.stop()
    else:
        st.error("Tài khoản của bạn chưa được gán chi nhánh. "
                "Liên hệ admin để được hỗ trợ.")
        if st.button("Đăng xuất"):
            do_logout(); st.rerun()
        st.stop()


# ==========================================
# DATA LOADING
# ==========================================

@st.cache_data(ttl=300)
def load_hoa_don(branches_key: tuple):
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("hoa_don").select("*") \
            .in_("Chi nhánh", list(branches_key)) \
            .range(offset, offset+batch-1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    tong = len(df); df = df.drop_duplicates()
    st.session_state["so_dong_trung"] = tong - len(df)
    for col in ["Tổng tiền hàng","Khách cần trả","Khách đã trả","Đơn giá","Thành tiền"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "Thời gian" in df.columns:
        # Thử parse format KiotViet gốc trước, sau đó fallback các format khác
        df["_ngay"] = pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")
        df["_date"] = df["_ngay"].dt.date
    return df


@st.cache_data(ttl=60)
def load_stock_deltas() -> dict:
    """
    Tính delta tồn kho từ các phiếu tạo trong app (loai_phieu = IN_APP_MARKER).
    Trả về dict {(ma_hang, chi_nhanh): delta_int}.

    Quy tắc:
      - Phiếu tạm, Đã hủy: không ảnh hưởng (delta = 0)
      - Đang chuyển: -SL tại CN nguồn (đã rời kho, chưa tới đích)
      - Đã nhận:    -SL tại CN nguồn, +SL tại CN đích

    Phiếu upload từ KiotViet (loai_phieu khác IN_APP_MARKER) được bỏ qua
    vì đã được phản ánh trong the_kho snapshot.
    """
    rows = []
    try:
        batch, offset = 1000, 0
        while True:
            res = supabase.table("phieu_chuyen_kho").select(
                "ma_hang,tu_chi_nhanh,toi_chi_nhanh,so_luong_chuyen,trang_thai"
            ).eq("loai_phieu", IN_APP_MARKER) \
             .range(offset, offset + batch - 1).execute()
            if not res.data: break
            rows.extend(res.data)
            if len(res.data) < batch: break
            offset += batch
    except Exception:
        return {}

    deltas = {}
    for r in rows:
        tt  = str(r.get("trang_thai", "") or "").strip()
        mh  = str(r.get("ma_hang", "") or "").strip()
        sl  = int(r.get("so_luong_chuyen", 0) or 0)
        tu  = str(r.get("tu_chi_nhanh", "") or "").strip()
        toi = str(r.get("toi_chi_nhanh", "") or "").strip()

        if not mh or sl <= 0:
            continue

        # Rời kho nguồn khi phiếu đã được xác nhận chuyển
        if tt in ("Đang chuyển", "Đã nhận") and tu:
            deltas[(mh, tu)] = deltas.get((mh, tu), 0) - sl

        # Vào kho đích chỉ khi đã nhận
        if tt == "Đã nhận" and toi:
            deltas[(mh, toi)] = deltas.get((mh, toi), 0) + sl

    return deltas


@st.cache_data(ttl=600)
def get_archive_reminder() -> dict:
    """
    Kiểm tra có cần nhắc admin kết sổ phiếu App không.

    Trả về dict:
      - need_reminder: True nếu thoả cả 2 điều kiện
      - n_active: số phiếu App (không phải dòng) đang active
      - days_oldest: số ngày kể từ phiếu App cũ nhất
      - oldest_date: ngày phiếu cũ nhất (date object)

    Điều kiện nhắc: > 30 ngày kể từ phiếu App cũ nhất chưa archive
                    VÀ có > 20 phiếu App active (đếm theo ma_phieu unique).
    """
    THRESHOLD_DAYS = 30
    THRESHOLD_PHIEU = 20

    try:
        res = supabase.table("phieu_chuyen_kho") \
            .select("ma_phieu, ngay_chuyen") \
            .eq("loai_phieu", IN_APP_MARKER) \
            .execute()
        if not res.data:
            return {"need_reminder": False, "n_active": 0,
                    "days_oldest": 0, "oldest_date": None}

        # Đếm số phiếu unique + tìm ngày cũ nhất
        unique_phieu = {}
        for r in res.data:
            ma = r.get("ma_phieu")
            ngay = r.get("ngay_chuyen")
            if ma and ngay and ma not in unique_phieu:
                unique_phieu[ma] = ngay

        n_active = len(unique_phieu)
        if n_active == 0:
            return {"need_reminder": False, "n_active": 0,
                    "days_oldest": 0, "oldest_date": None}

        oldest_iso = min(unique_phieu.values())
        oldest_dt = pd.to_datetime(oldest_iso, errors="coerce")
        if pd.isna(oldest_dt):
            return {"need_reminder": False, "n_active": n_active,
                    "days_oldest": 0, "oldest_date": None}

        days_oldest = (datetime.now() - oldest_dt.to_pydatetime()).days

        need = (days_oldest > THRESHOLD_DAYS) and (n_active > THRESHOLD_PHIEU)
        return {
            "need_reminder": need,
            "n_active": n_active,
            "days_oldest": days_oldest,
            "oldest_date": oldest_dt.date(),
        }
    except Exception:
        return {"need_reminder": False, "n_active": 0,
                "days_oldest": 0, "oldest_date": None}


@st.cache_data(ttl=300)
def load_the_kho(branches_key: tuple):
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("the_kho").select("*") \
            .in_("Chi nhánh", list(branches_key)) \
            .range(offset, offset+batch-1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["Tồn đầu kì","Giá trị đầu kì","Nhập NCC","Giá trị nhập NCC",
                "Xuất bán","Giá trị xuất bán","Tồn cuối kì","Giá trị cuối kì"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # ── Áp delta tồn kho từ phiếu App ──
    try:
        deltas = load_stock_deltas()
        if deltas and "Mã hàng" in df.columns and "Chi nhánh" in df.columns:
            # Strip whitespace trên keys để match chính xác
            df["_ma_key"] = df["Mã hàng"].astype(str).str.strip()
            df["_cn_key"] = df["Chi nhánh"].astype(str).str.strip()

            def _apply_delta(row):
                return deltas.get((row["_ma_key"], row["_cn_key"]), 0)
            df["_delta"] = df.apply(_apply_delta, axis=1)
            df["Tồn cuối kì"] = (df["Tồn cuối kì"] + df["_delta"]).astype(int)

            # Tìm các (mã, CN) có delta nhưng KHÔNG có dòng trong the_kho
            # → phải thêm dòng mới để tồn kho tăng lên
            existing_keys = set(zip(df["_ma_key"], df["_cn_key"]))
            # Chỉ xét các CN đang load (branches_key)
            load_cns_set = set(branches_key)

            # Lookup tên hàng từ master để fill khi tạo row mới
            try:
                master = load_hang_hoa()
                name_map = (dict(zip(master["Mã hàng"].astype(str),
                                     master["Tên hàng"].astype(str)))
                           if not master.empty else {})
            except Exception:
                name_map = {}

            new_rows = []
            for (mh, cn), dlt in deltas.items():
                if cn not in load_cns_set:
                    continue  # CN không load → bỏ qua
                if (mh, cn) in existing_keys:
                    continue  # đã có, đã áp delta ở trên
                if dlt == 0:
                    continue
                # Tạo dòng mới cho (mã, CN) chưa tồn tại
                new_rows.append({
                    "Mã hàng":       mh,
                    "Chi nhánh":     cn,
                    "Tên hàng":      name_map.get(mh, ""),
                    "Tồn đầu kì":    0,
                    "Tồn cuối kì":   int(dlt),   # delta thành tồn luôn
                    "Nhập NCC":      0,
                    "Xuất bán":      0,
                    "Giá trị đầu kì":  0,
                    "Giá trị nhập NCC": 0,
                    "Giá trị xuất bán": 0,
                    "Giá trị cuối kì": 0,
                    "_ma_key":       mh,
                    "_cn_key":       cn,
                    "_delta":        int(dlt),
                })
            if new_rows:
                df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

            df = df.drop(columns=["_delta", "_ma_key", "_cn_key"])
    except Exception:
        pass

    return df


@st.cache_data(ttl=600)
def load_hang_hoa() -> pd.DataFrame:
    """Master data sản phẩm — cache 10 phút."""
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("hang_hoa").select("*") \
            .range(offset, offset + batch - 1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "gia_ban" in df.columns:
        df["gia_ban"] = pd.to_numeric(df["gia_ban"], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=300)
def load_phieu_chuyen_kho(branches_key: tuple = None):
    """Load phiếu chuyển kho — filter theo chi nhánh (từ HOẶC tới)."""
    all_rows, batch, offset = [], 1000, 0
    while True:
        q = supabase.table("phieu_chuyen_kho").select("*") \
            .order("ngay_chuyen", desc=True)
        res = q.range(offset, offset + batch - 1).execute()
        if not res.data: break
        all_rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    if branches_key:
        bk = list(branches_key)
        mask = df["tu_chi_nhanh"].isin(bk) | df["toi_chi_nhanh"].isin(bk)
        df = df[mask].reset_index(drop=True)
    for col in ["so_luong_chuyen","so_luong_nhan","tong_sl_chuyen","tong_sl_nhan",
                "tong_mat_hang","gia_chuyen","thanh_tien_chuyen","thanh_tien_nhan","tong_gia_tri"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "ngay_chuyen" in df.columns:
        df["_ngay"] = pd.to_datetime(df["ngay_chuyen"], errors="coerce")
        df["_date"] = df["_ngay"].dt.date
    return df


def get_gia_ban_map() -> dict:
    """Map ma_hang → gia_ban từ master hang_hoa."""
    hh = load_hang_hoa()
    if hh.empty or "ma_hang" not in hh.columns or "gia_ban" not in hh.columns:
        return {}
    return dict(zip(hh["ma_hang"].astype(str), hh["gia_ban"].fillna(0).astype(int)))


# ==========================================
# MODULE: TỔNG QUAN — FIX NameError (bỏ dashboard)
# ==========================================

# ==========================================
# MODULE: KIỂM KÊ — MVP v1
# Workflow: Nháp/Đang kiểm → Chờ duyệt admin → Đã duyệt
# ==========================================

@st.cache_data(ttl=120)
def load_phieu_kiem_ke(branches_key: tuple = None) -> pd.DataFrame:
    rows, batch, offset = [], 1000, 0
    while True:
        q = supabase.table("phieu_kiem_ke").select("*").order("created_at", desc=True)
        res = q.range(offset, offset + batch - 1).execute()
        if not res.data:
            break
        rows.extend(res.data)
        if len(res.data) < batch:
            break
        offset += batch

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if branches_key and "chi_nhanh" in df.columns:
        df = df[df["chi_nhanh"].isin(list(branches_key))].reset_index(drop=True)
    if "created_at" in df.columns:
        df["_created"] = pd.to_datetime(df["created_at"], errors="coerce")
    return df


def _kk_get_lines(ma_phieu: str) -> pd.DataFrame:
    res = supabase.table("phieu_kiem_ke_chi_tiet").select("*") \
        .eq("ma_phieu_kk", ma_phieu).execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    for col in ["ton_snapshot", "sl_quet", "sl_thuc_te", "ton_ky_vong_luc_duyet", "chenh_lech"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    # Sắp xếp: mã vừa quét gần nhất lên đầu (updated_at desc)
    # Hàng chưa quét (sl_quet=0) xuống cuối
    if "updated_at" in df.columns:
        df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")
        df["_da_quet"] = (df["sl_quet"] > 0).astype(int)
        df = df.sort_values(["_da_quet", "updated_at"], ascending=[False, False])
        df = df.drop(columns=["_da_quet"])
    else:
        df = df.sort_values("sl_quet", ascending=False)
    return df.reset_index(drop=True)


def _kk_complete(ma_phieu: str) -> tuple[bool, str]:
    """Nhân viên hoàn thành quét → chuyển phiếu sang Chờ duyệt admin."""
    try:
        supabase.table("phieu_kiem_ke").update({
            "trang_thai": "Chờ duyệt admin",
        }).eq("ma_phieu_kk", ma_phieu).execute()
        st.cache_data.clear()
        log_action("KIEMKE_COMPLETE", f"ma={ma_phieu}")
        return True, f"Phiếu {ma_phieu} đã chuyển sang Chờ duyệt admin."
    except Exception as e:
        return False, f"Lỗi hoàn thành phiếu: {e}"


def _kk_gen_ma_phieu() -> str:
    try:
        res = supabase.table("phieu_kiem_ke").select("ma_phieu_kk") \
            .like("ma_phieu_kk", "KK______").order("ma_phieu_kk", desc=True).limit(1).execute()
        if res.data:
            try:
                num = int(str(res.data[0]["ma_phieu_kk"])[2:]) + 1
            except Exception:
                num = 1
        else:
            num = 1
        return f"KK{num:06d}"
    except Exception:
        return f"KK{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:4].upper()}"


def _kk_build_scope_rows(chi_nhanh: str, nhom_hang_chon: str) -> tuple[list, str]:
    master = load_hang_hoa()
    kho = load_the_kho(branches_key=(chi_nhanh,))
    if master.empty or kho.empty:
        return [], "Chưa đủ dữ liệu master/thẻ kho để tạo phiếu kiểm kê."
    
    kho_map = kho.groupby("Mã hàng", as_index=False).agg(ton=("Tồn cuối kì", "sum"))
    df = master.merge(kho_map, left_on="ma_hang", right_on="Mã hàng", how="left")
    df["ton"] = pd.to_numeric(df["ton"], errors="coerce").fillna(0).astype(int)

    # Hỗ trợ đa nhóm: nhom_hang_chon có thể là "A|B|C"
    # DB lưu format "Cha>>Con" không có dấu cách quanh >>
    nhom_col = df["nhom_hang"].fillna("") if "nhom_hang" in df.columns else pd.Series([""] * len(df))
    nhom_list = [x.strip() for x in nhom_hang_chon.split("|") if x.strip()]
    mask = pd.Series([False] * len(df), index=df.index)
    for nhom in nhom_list:
        # Chuẩn hóa: bỏ dấu cách quanh >> để khớp format DB
        nhom_norm = ">>".join(p.strip() for p in nhom.split(">>"))
        if ">>" in nhom_norm:
            # Nhóm con cụ thể: khớp chính xác
            mask = mask | (nhom_col == nhom_norm)
        else:
            # Nhóm cha: lấy hàng thuộc cha đó hoặc bất kỳ nhóm con nào
            mask = mask | (nhom_col == nhom_norm) | nhom_col.str.startswith(nhom_norm + ">>")
    df = df[mask].copy()

    if df.empty:
        return [], f"Nhóm **{nhom_hang_chon}** không có mặt hàng nào tại chi nhánh này."

    # Tách thành 2 nhóm: có tồn > 0 (đưa vào phiếu luôn) và tồn = 0 (bỏ qua)
    # Nhân viên có thể quét phát sinh thêm nếu thực tế có hàng mà hệ thống chưa ghi nhận
    df = df[df["ton"] >= 0].copy()  # giữ cả ton=0 để snapshot đúng thực tế
    
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "ma_hang": str(r.get("ma_hang", "") or ""),
            "ma_vach": str(r.get("ma_vach", "") or ""),
            "ten_hang": str(r.get("ten_hang", "") or ""),
            "nhom_hang": str(r.get("nhom_hang", "") or ""),
            "ton_snapshot": int(r.get("ton", 0) or 0),
            "sl_quet": 0,
            "sl_thuc_te": 0,
            "ton_ky_vong_luc_duyet": 0,
            "chenh_lech": 0,
            "trang_thai_dong": "Đang kiểm",
        })
    return rows, ""


def _kk_create_phieu(chi_nhanh: str, nhom_cha: str, ghi_chu: str) -> tuple[bool, str]:
    rows, err = _kk_build_scope_rows(chi_nhanh, nhom_cha)
    if err:
        return False, err

    ma = _kk_gen_ma_phieu()
    user = get_user() or {}
    try:
        supabase.table("phieu_kiem_ke").insert({
            "ma_phieu_kk": ma,
            "chi_nhanh": chi_nhanh,
            "trang_thai": "Đang kiểm",
            "nhom_cha": nhom_cha,
            "ghi_chu": ghi_chu.strip(),
            "created_by": user.get("ho_ten", ""),
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "approved_by": None,
            "approved_at": None,
        }).execute()

        payload = []
        for r in rows:
            p = dict(r)
            p["ma_phieu_kk"] = ma
            payload.append(p)
        for i in range(0, len(payload), 500):
            supabase.table("phieu_kiem_ke_chi_tiet").insert(payload[i:i+500]).execute()
        st.cache_data.clear()
        log_action("KIEMKE_CREATE", f"ma={ma} cn={chi_nhanh} nhom={nhom_cha} rows={len(rows)}")
        return True, ma
    except Exception as e:
        return False, f"Lỗi tạo phiếu kiểm kê: {e}"


def _kk_scan_plus_one(ma_phieu: str, code: str) -> tuple[bool, str]:
    code = str(code or "").strip()
    if not code:
        return False, "Mã quét rỗng."
    
    code_n = code.lower()
    try:
        # 1. Tìm mã trong DÒNG CHI TIẾT của phiếu hiện tại
        rows = supabase.table("phieu_kiem_ke_chi_tiet") \
            .select("id,ma_hang,ma_vach,sl_quet,sl_thuc_te") \
            .eq("ma_phieu_kk", ma_phieu).execute().data or []
        
        hit = None
        for r in rows:
            mh = str(r.get("ma_hang", "") or "").strip().lower()
            mv = str(r.get("ma_vach", "") or "").strip().lower()
            if code_n == mh or code_n == mv:
                hit = r; break
                
        if hit:
            # ĐÃ CÓ TRONG PHIẾU: Cộng dồn +1
            sl_quet = int(hit.get("sl_quet", 0) or 0) + 1
            sl_tt = int(hit.get("sl_thuc_te", 0) or 0) + 1
            supabase.table("phieu_kiem_ke_chi_tiet").update({
                "sl_quet": sl_quet, "sl_thuc_te": sl_tt
            }).eq("id", hit["id"]).execute()
            return True, str(hit.get("ma_hang", "") or code)
        
        else:
            # KHÔNG CÓ TRONG PHIẾU (Tồn = 0): Lấy từ Master Data chèn vào
            master = load_hang_hoa()
            if master.empty:
                return False, "Dữ liệu Hàng hóa (Master) trống."
            
            match_mask = (master["ma_hang"].astype(str).str.strip().str.lower() == code_n) | \
                         (master["ma_vach"].astype(str).str.strip().str.lower() == code_n)
            m_hit = master[match_mask]
            
            if m_hit.empty:
                return False, f"Mã '{code}' hoàn toàn không tồn tại trong hệ thống KiotViet."
            
            row_data = m_hit.iloc[0]
            mh_new = str(row_data.get("ma_hang", ""))
            
            supabase.table("phieu_kiem_ke_chi_tiet").insert({
                "ma_phieu_kk": ma_phieu,
                "ma_hang": mh_new,
                "ma_vach": str(row_data.get("ma_vach", "")),
                "ten_hang": str(row_data.get("ten_hang", "")),
                "nhom_hang": str(row_data.get("nhom_hang", "")),
                "ton_snapshot": 0, # Tồn lúc tạo phiếu là 0
                "sl_quet": 1,      # Lần quét đầu tiên
                "sl_thuc_te": 1,
                "ton_ky_vong_luc_duyet": 0,
                "chenh_lech": 0,
                "trang_thai_dong": "Đang kiểm"
            }).execute()
            
            return True, f"{mh_new} (Phát sinh mới)"
            
    except Exception as e:
        return False, f"Lỗi scan: {e}"


def _kk_cancel_phieu(ma_phieu: str) -> tuple[bool, str]:
    try:
        supabase.table("phieu_kiem_ke_chi_tiet").delete().eq("ma_phieu_kk", ma_phieu).execute()
        supabase.table("phieu_kiem_ke").delete().eq("ma_phieu_kk", ma_phieu).execute()
        st.cache_data.clear()
        log_action("KIEMKE_CANCEL", f"ma={ma_phieu}")
        return True, "Đã hủy và xóa phiếu kiểm kê."
    except Exception as e:
        return False, f"Lỗi hủy phiếu: {e}"
def _kk_approve(ma_phieu: str) -> tuple[bool, str]:
    try:
        lines = _kk_get_lines(ma_phieu)
        if lines.empty:
            return False, "Phiếu không có dòng hàng."
        for _, r in lines.iterrows():
            ton_ss = int(r.get("ton_snapshot", 0) or 0)
            sl_tt = int(r.get("sl_thuc_te", 0) or 0)
            ch = sl_tt - ton_ss
            supabase.table("phieu_kiem_ke_chi_tiet").update({
                "ton_ky_vong_luc_duyet": ton_ss,
                "chenh_lech": ch,
                "trang_thai_dong": "Đã duyệt",
            }).eq("id", int(r["id"])).execute()

        supabase.table("phieu_kiem_ke").update({
            "trang_thai": "Đã duyệt",
            "approved_by": (get_user() or {}).get("ho_ten", ""),
            "approved_at": datetime.now().isoformat(),
        }).eq("ma_phieu_kk", ma_phieu).execute()
        st.cache_data.clear()
        log_action("KIEMKE_APPROVE", f"ma={ma_phieu}")
        return True, "Đã duyệt phiếu kiểm kê."
    except Exception as e:
        return False, f"Lỗi duyệt phiếu: {e}"


def module_kiem_ke():
    st.markdown("### 🧮 Kiểm kê")
    st.caption("MVP v1.1: Quét +1, hỗ trợ lọc nhóm con, Hủy phiếu rác.")
    active = get_active_branch()
    accessible = get_accessible_branches()

    tab_list, tab_create, tab_scan, tab_approve = st.tabs(
        ["Danh sách phiếu", "Tạo phiếu", "Quét kiểm kê", "Duyệt admin"]
    )

    with tab_list:
        try:
            df = load_phieu_kiem_ke(tuple(accessible))
            if df.empty:
                st.info("Chưa có phiếu kiểm kê.")
            else:
                view = df.copy()
                if "created_at" in view.columns:
                    view["Ngày Tạo"] = (pd.to_datetime(view["created_at"], utc=True)
                                        .dt.tz_convert("Asia/Ho_Chi_Minh")
                                        .dt.strftime("%d/%m/%Y %H:%M"))
                rename_map = {
                    "ma_phieu_kk": "Mã Phiếu", "chi_nhanh": "Chi Nhánh", 
                    "nhom_cha": "Nhóm Hàng", "trang_thai": "Trạng Thái", 
                    "created_by": "Người Tạo", "ghi_chu": "Ghi Chú"
                }
                view = view.rename(columns=rename_map)
                cols = ["Mã Phiếu", "Chi Nhánh", "Nhóm Hàng", "Trạng Thái", "Người Tạo", "Ngày Tạo", "Ghi Chú"]
                cols = [c for c in cols if c in view.columns]
                st.dataframe(view[cols], use_container_width=True, hide_index=True, height=380)

                # Xem chi tiết phiếu đã duyệt
                st.markdown("---")
                st.caption("📋 Xem chi tiết mặt hàng của một phiếu:")
                ma_options = view["Mã Phiếu"].tolist() if "Mã Phiếu" in view.columns else []
                picked_ma = st.selectbox("Chọn phiếu để xem chi tiết:", ["-- Chọn phiếu --"] + ma_options, key="kk_list_detail_pick")
                if picked_ma != "-- Chọn phiếu --":
                    detail = _kk_get_lines(picked_ma)
                    if detail.empty:
                        st.info("Phiếu này chưa có dữ liệu chi tiết.")
                    else:
                        detail["Chênh lệch"] = detail["sl_thuc_te"] - detail["ton_snapshot"]
                        detail_view = detail.rename(columns={
                            "ma_hang": "Mã Hàng", "ten_hang": "Tên Hàng",
                            "ton_snapshot": "Tồn Sổ Sách", "sl_thuc_te": "SL Thực Tế",
                            "sl_quet": "SL Quét"
                        })
                        dcols = ["Mã Hàng", "Tên Hàng", "Tồn Sổ Sách", "SL Quét", "SL Thực Tế", "Chênh lệch"]
                        dcols = [c for c in dcols if c in detail_view.columns]
                        st.dataframe(detail_view[dcols], use_container_width=True, hide_index=True, height=360)

                        # Xuất Excel import KiotViet — đặt ở đây để luôn truy cập được
                        # kể cả sau khi phiếu đã duyệt xong
                        import io
                        df_export = detail[["ma_hang", "sl_thuc_te"]].copy()
                        df_export.columns = ["Mã hàng", "Số lượng"]
                        buf = io.BytesIO()
                        df_export.to_excel(buf, index=False)
                        buf.seek(0)
                        st.download_button(
                            label="📥 Xuất Excel import KiotViet",
                            data=buf,
                            file_name=f"KiemKe_{picked_ma}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key=f"dl_kk_{picked_ma}"
                        )
        except Exception as e:
            st.error(f"Lỗi tải danh sách: {e}")

    with tab_create:
        cn_create = active
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_create = st.selectbox("Chi nhánh kiểm kê:", accessible, index=max(0, accessible.index(active)))
        
        ma_du_kien = _kk_gen_ma_phieu()
        st.info(f"🏷️ Mã phiếu dự kiến: **{ma_du_kien}**")

        master = load_hang_hoa()
        if master.empty:
            st.warning("Chưa có dữ liệu hàng hóa.")
        else:
            # Xử lý cắt chuỗi "Cha >> Con" để lấy dữ liệu 2 cấp
            nhom_col = master["nhom_hang"].fillna("") if "nhom_hang" in master.columns else pd.Series([""] * len(master))
            split = nhom_col.str.split(">>", n=1, expand=True)
            master["_cha"] = split[0].fillna("").str.strip()
            master["_con"] = split[1].fillna("").str.strip() if len(split.columns) > 1 else ""

            nhom_cha_list = sorted([str(x) for x in master["_cha"].unique() if str(x)])
            
            if not nhom_cha_list:
                st.warning("Không tìm thấy dữ liệu nhóm hàng.")
            else:
                # Build danh sách phẳng: gồm cả nhóm cha và nhóm con "Cha >> Con"
                nhom_flat = []
                for cha in nhom_cha_list:
                    nhom_flat.append(cha)
                    con_list = sorted([str(x) for x in master[master["_cha"] == cha]["_con"].unique() if str(x)])
                    for con in con_list:
                        nhom_flat.append(f"{cha}>>{con}")  # khớp format DB, không có dấu cách

                nhom_chon_list = st.multiselect(
                    "Chọn nhóm hàng kiểm kê (có thể chọn nhiều):",
                    options=nhom_flat,
                    placeholder="Chọn ít nhất 1 nhóm...",
                    key=f"kk_nhom_select_{st.session_state.get('kk_create_count', 0)}"
                )

                if nhom_chon_list:
                    st.caption(f"Đã chọn: {', '.join(nhom_chon_list)}")
                    # Lưu dưới dạng chuỗi phân cách "|" để truyền vào hàm tạo phiếu
                    nhom_chon = "|".join(nhom_chon_list)
                else:
                    nhom_chon = ""

                ghi_chu = st.text_area("Ghi chú phiếu:", key=f"kk_ghi_chu_{st.session_state.get('kk_create_count', 0)}", placeholder="Ghi chú đợt kiểm kê...")
                if st.button("Tạo phiếu kiểm kê", type="primary", use_container_width=True, disabled=not nhom_chon):
                    ok, msg = _kk_create_phieu(cn_create, nhom_chon, ghi_chu)
                    if ok:
                        st.session_state["kk_active_ma"] = msg
                        # Tăng counter để reset multiselect và text_area
                        st.session_state["kk_create_count"] = st.session_state.get("kk_create_count", 0) + 1
                        st.success(f"Đã tạo phiếu {msg}.")
                        st.rerun()
                    else:
                        st.error(msg)

    with tab_scan:
        try:
            df = load_phieu_kiem_ke(tuple(accessible))
            if df.empty:
                st.info("Chưa có phiếu để quét.")
            else:
                candidates = df[df["trang_thai"] == "Đang kiểm"].copy() if "trang_thai" in df.columns else pd.DataFrame()
                if candidates.empty:
                    st.info("Không có phiếu ở trạng thái Đang kiểm.")
                else:
                    opts = [f"{r['ma_phieu_kk']} · {r.get('chi_nhanh','')} · {r.get('nhom_cha','')}" for _, r in candidates.iterrows()]
                    idx = 0
                    ma_saved = st.session_state.get("kk_active_ma")
                    if ma_saved:
                        for i, x in enumerate(opts):
                            if x.startswith(ma_saved):
                                idx = i; break
                    
                    picked = st.selectbox("Chọn phiếu đang kiểm:", opts, index=idx)
                    ma_phieu = picked.split(" · ")[0]
                    st.session_state["kk_active_ma"] = ma_phieu

                    with st.form("kk_scan_form", clear_on_submit=True):
                        code = st.text_input("Quét mã vạch / mã hàng:", key="kk_scan_code", placeholder="Đưa con trỏ ở đây và quét...")
                        submitted = st.form_submit_button("Quét +1", use_container_width=True)
                    if submitted:
                        ok, msg = _kk_scan_plus_one(ma_phieu, code)
                        if ok:
                            st.success(f"✓ Đã cộng +1 cho mã {msg}")
                            st.cache_data.clear()
                        else:
                            st.warning(msg)

                    lines = _kk_get_lines(ma_phieu)
                    if not lines.empty:
                        view = lines.copy()
                        view["Lệch Tạm"] = view["sl_thuc_te"] - view["ton_snapshot"]
                        
                        rename_map = {
                            "id": "ID", "ma_hang": "Mã Hàng", "ma_vach": "Mã Vạch", "ten_hang": "Tên Hàng",
                            "ton_snapshot": "Tồn Kho", "sl_quet": "SL Quét", "sl_thuc_te": "SL Thực Tế"
                        }
                        view = view.rename(columns=rename_map)
                        cols = ["ID", "Mã Hàng", "Mã Vạch", "Tên Hàng", "Tồn Kho", "SL Quét", "SL Thực Tế", "Lệch Tạm"]
                        cols = [c for c in cols if c in view.columns]
                        
                        editor_key = f"kk_editor_{ma_phieu}"
                        st.caption("💡 *Mẹo: Nháy đúp vào ô thuộc cột **SL Thực Tế ✏️** để sửa trực tiếp.*")
                        edited_df = st.data_editor(
                            view[cols],
                            use_container_width=True,
                            hide_index=True,
                            key=editor_key,
                            height=360,
                            column_config={
                                "ID": None,
                                "Mã Hàng": st.column_config.TextColumn(disabled=True),
                                "Mã Vạch": st.column_config.TextColumn(disabled=True),
                                "Tên Hàng": st.column_config.TextColumn(disabled=True),
                                "Tồn Kho": st.column_config.NumberColumn(disabled=True),
                                "SL Quét": st.column_config.NumberColumn(disabled=True),
                                "Lệch Tạm": st.column_config.NumberColumn(disabled=True),
                                "SL Thực Tế": st.column_config.NumberColumn(
                                    "SL Thực Tế ✏️", 
                                    min_value=0, 
                                    step=1,
                                    help="Nháy đúp để sửa số lượng thực tế"
                                )
                            }
                        )

                        changes = st.session_state.get(editor_key, {}).get("edited_rows", {})
                        if changes:
                            st.warning("⚠️ Bảng có thay đổi chưa lưu. Hãy bấm 'Lưu các dòng đã sửa' trước khi làm việc khác!")
                            if st.button("💾 Lưu các dòng đã sửa", type="primary", use_container_width=True):
                                try:
                                    for row_idx, edit_data in changes.items():
                                        if "SL Thực Tế" in edit_data:
                                            new_sl = int(edit_data["SL Thực Tế"])
                                            row_id = int(view.iloc[row_idx]["ID"])
                                            supabase.table("phieu_kiem_ke_chi_tiet").update({
                                                "sl_thuc_te": new_sl
                                            }).eq("id", row_id).execute()
                                    st.success("✓ Đã cập nhật số lượng thành công!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Lỗi khi lưu: {e}")

                        st.markdown("---")
                        c1, c2, c3 = st.columns(3)
                        with c1: st.metric("Tổng tồn", f"{int(view['Tồn Kho'].sum())}")
                        with c2: st.metric("Tổng quét", f"{int(view['SL Quét'].sum())}")
                        with c3:
                            lech = int(view["Lệch Tạm"].sum())
                            st.metric("Tổng chênh lệch", f"{lech:+d}")

                        st.markdown("---")
                        # Nút Hủy luôn hiển thị (không phụ thuộc vào changes)
                        if not changes:
                            c_left, c_right = st.columns(2)
                            with c_left:
                                if st.button("Hoàn thành kiểm kê", type="primary", use_container_width=True):
                                    ok, msg = _kk_complete(ma_phieu)
                                    if ok: st.success(msg); st.rerun()
                                    else: st.error(msg)
                            with c_right:
                                if st.button("🗑️ Hủy phiếu này", type="secondary", use_container_width=True):
                                    ok, msg = _kk_cancel_phieu(ma_phieu)
                                    if ok:
                                        st.session_state.pop("kk_active_ma", None)
                                        st.success(msg); st.rerun()
                                    else: st.error(msg)
                        else:
                            # Khi có thay đổi chưa lưu: chỉ hiện nút Hủy, ẩn Hoàn thành
                            if st.button("🗑️ Hủy phiếu này", type="secondary", use_container_width=True, key="kk_cancel_pending"):
                                ok, msg = _kk_cancel_phieu(ma_phieu)
                                if ok:
                                    st.session_state.pop("kk_active_ma", None)
                                    st.success(msg); st.rerun()
                                else: st.error(msg)
        except Exception as e:
            st.error(f"Lỗi màn hình quét kiểm kê: {e}")

    with tab_approve:
        if not is_admin():
            st.info("Chỉ admin có quyền duyệt phiếu kiểm kê.")
        else:
            try:
                df = load_phieu_kiem_ke(tuple(accessible))
                pending = df[df["trang_thai"] == "Chờ duyệt admin"].copy() if (not df.empty and "trang_thai" in df.columns) else pd.DataFrame()
                if pending.empty:
                    st.info("Không có phiếu chờ duyệt.")
                else:
                    opts = [f"{r['ma_phieu_kk']} · {r.get('chi_nhanh','')} · {r.get('nhom_cha','')}" for _, r in pending.iterrows()]
                    picked = st.selectbox("Phiếu chờ duyệt:", opts, key="kk_pending_pick")
                    ma_phieu = picked.split(" · ")[0]
                    lines = _kk_get_lines(ma_phieu)
                    if not lines.empty:
                        lines["Lệch Dự Kiến"] = lines["sl_thuc_te"] - lines["ton_snapshot"]

                        # Lấy giá bán để tính giá trị
                        gia_map = get_gia_ban_map()
                        lines["_gia"] = lines["ma_hang"].astype(str).map(gia_map).fillna(0).astype(int)
                        lines["_gt_thuc_te"] = lines["sl_thuc_te"] * lines["_gia"]
                        lines["_gt_lech"] = lines["Lệch Dự Kiến"] * lines["_gia"]

                        tong_thuc_te_sl = int(lines["sl_thuc_te"].sum())
                        tong_thuc_te_gt = int(lines["_gt_thuc_te"].sum())
                        lech_tang = lines[lines["Lệch Dự Kiến"] > 0]
                        lech_giam = lines[lines["Lệch Dự Kiến"] < 0]
                        tong_tang_sl = int(lech_tang["Lệch Dự Kiến"].sum())
                        tong_tang_gt = int(lech_tang["_gt_lech"].sum())
                        tong_giam_sl = int(lech_giam["Lệch Dự Kiến"].sum())
                        tong_giam_gt = int(lech_giam["_gt_lech"].sum())
                        tong_lech_sl = tong_tang_sl + tong_giam_sl
                        tong_lech_gt = tong_tang_gt + tong_giam_gt

                        def fmt_vnd(x): return f"{x:,.0f}".replace(",", ".")

                        m1, m2, m3, m4 = st.columns(4)
                        with m1: st.metric(f"Tổng thực tế ({tong_thuc_te_sl})", fmt_vnd(tong_thuc_te_gt))
                        with m2: st.metric(f"Lệch tăng (+{tong_tang_sl})", fmt_vnd(tong_tang_gt))
                        with m3: st.metric(f"Lệch giảm ({tong_giam_sl})", fmt_vnd(abs(tong_giam_gt)))
                        with m4: st.metric(f"Tổng chênh ({tong_lech_sl:+d})", fmt_vnd(tong_lech_gt))
                        view = lines.rename(columns={
                            "ma_hang": "Mã Hàng", "ten_hang": "Tên Hàng", 
                            "ton_snapshot": "Tồn Kho", "sl_thuc_te": "SL Thực Tế"
                        })
                        cols = ["Mã Hàng", "Tên Hàng", "Tồn Kho", "SL Thực Tế", "Lệch Dự Kiến"]
                        cols = [c for c in cols if c in view.columns]
                        st.dataframe(view[cols], use_container_width=True, hide_index=True, height=320)
                        st.warning("Lưu ý: Rà soát kỹ trước khi duyệt.")
                        
                        c_left, c_right = st.columns(2)
                        with c_left:
                            if st.button("Duyệt & chốt phiếu", type="primary", use_container_width=True):
                                ok, msg = _kk_approve(ma_phieu)
                                if ok: st.success(msg); st.rerun()
                                else: st.error(msg)
                        with c_right:
                            if st.button("🗑️ Hủy / Xóa phiếu", type="secondary", use_container_width=True):
                                ok, msg = _kk_cancel_phieu(ma_phieu)
                                if ok: st.success(msg); st.rerun()
                                else: st.error(msg)
            except Exception as e:
                st.error(f"Lỗi màn hình duyệt phiếu: {e}")
def _build_phieu_html(phieu: dict, ct: pd.DataFrame) -> str:
    """Tạo HTML phiếu sửa chữa A5 dọc để in."""
    tong_in   = int((ct["so_luong"] * ct["don_gia"]).sum()) if not ct.empty else 0
    con_lai   = tong_in - int(phieu.get("khach_tra_truoc", 0))
    rows_html = ""
    if not ct.empty:
        for _, r in ct.iterrows():
            tt = int(r["so_luong"]) * int(r["don_gia"])
            rows_html += (
                f"<tr><td>{r.get('ten_hang','')}</td>"
                f"<td class='c'>{int(r['so_luong'])}</td>"
                f"<td class='r'>{int(r['don_gia']):,}</td>"
                f"<td class='r'>{tt:,}</td></tr>"
            ).replace(",", ".")
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
  @page {{ size: A5 portrait; margin: 10mm 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: Arial, sans-serif; font-size: 13px; color: #000; margin:0; }}
  h2 {{ text-align:center; font-size:16px; font-weight:700; margin:0 0 2px; }}
  .sub {{ text-align:center; font-size:12px; color:#444; margin-bottom:10px; }}
  .info {{ width:100%; border-collapse:collapse; margin-bottom:8px; }}
  .info td {{ padding:3px 4px; font-size:13px; vertical-align:top; }}
  .info .lbl {{ font-weight:700; white-space:nowrap; width:22%; }}
  .info .val {{ width:28%; }}
  .svc {{ width:100%; border-collapse:collapse; margin-top:6px; }}
  .svc th {{ background:#eee; border:1px solid #aaa; padding:4px 5px; font-size:12px; }}
  .svc td {{ border:1px solid #aaa; padding:4px 5px; font-size:12px; }}
  .c {{ text-align:center; }}
  .r {{ text-align:right; }}
  .total-row td {{ font-weight:700; background:#f7f7f7; }}
  .sign {{ display:flex; justify-content:space-between; margin-top:20px; font-size:12px; }}
  .sign div {{ text-align:center; width:45%; }}
  hr {{ border:none; border-top:1px solid #ccc; margin:8px 0; }}
</style></head><body>
<h2>PHIẾU TIẾP NHẬN SỬA CHỮA</h2>
<div class='sub'>Mã: <b>{phieu.get('ma_phieu','')}</b> &nbsp;·&nbsp; {phieu.get('Ngày TN','')}</div>
<hr>
<table class='info'>
  <tr><td class='lbl'>Khách hàng:</td><td class='val'><b>{phieu.get('ten_khach','')}</b></td>
      <td class='lbl'>SĐT:</td><td><b>{phieu.get('sdt_khach','')}</b></td></tr>
  <tr><td class='lbl'>Hiệu đồng hồ:</td><td class='val'>{phieu.get('hieu_dong_ho') or '—'}</td>
      <td class='lbl'>Loại YC:</td><td>{phieu.get('loai_yeu_cau','')}</td></tr>
  <tr><td class='lbl'>Đặc điểm:</td><td colspan='3'>{phieu.get('dac_diem') or '—'}</td></tr>
  <tr><td class='lbl'>Mô tả lỗi:</td><td colspan='3'>{phieu.get('mo_ta_loi','')}</td></tr>
  <tr><td class='lbl'>Hẹn trả:</td><td class='val'>{phieu.get('ngay_hen_tra') or '—'}</td>
      <td class='lbl'>Trả trước:</td><td>{int(phieu.get('khach_tra_truoc',0)):,}đ</td></tr>
</table>
<hr>
<table class='svc'>
  <tr><th>Dịch vụ / Linh kiện</th><th class='c'>SL</th><th class='r'>Đơn giá</th><th class='r'>T.Tiền</th></tr>
  {rows_html or "<tr><td colspan='4' style='text-align:center;color:#999;padding:8px'>Chưa có dịch vụ</td></tr>"}
  <tr class='total-row'>
    <td colspan='3' class='r'>Tổng cộng:</td><td class='r'>{tong_in:,}đ</td></tr>
  <tr><td colspan='3' class='r'>Đã trả trước:</td>
      <td class='r'>{int(phieu.get('khach_tra_truoc',0)):,}đ</td></tr>
  <tr class='total-row'>
    <td colspan='3' class='r'>Còn lại:</td><td class='r'>{con_lai:,}đ</td></tr>
</table>
<div class='sign'>
  <div>Khách hàng ký<br><br><br><br>_______________</div>
  <div>Nhân viên tiếp nhận<br><br><br><br>_______________<br>{phieu.get('nguoi_tiep_nhan','')}</div>
</div>
<script>window.onload=function(){{window.print();}}</script>
</body></html>""".replace(",", ".")


def _in_phieu_sc(phieu_html: str, key: str):
    """Mở tab mới và in phiếu — dùng Blob URL để giữ đúng UTF-8 tiếng Việt."""
    import base64
    b64 = base64.b64encode(phieu_html.encode("utf-8")).decode("ascii")
    st.components.v1.html(
        f"""<script>
        var b = new Blob(
            [new TextDecoder('utf-8').decode(
                Uint8Array.from(atob('{b64}'), c => c.charCodeAt(0))
            )],
            {{type: 'text/html; charset=utf-8'}}
        );
        var w = window.open(URL.createObjectURL(b), '_blank');
        </script>""",
        height=0
    )


def lookup_khach_hang(sdt: str) -> dict | None:
    """Tra cứu khách hàng theo SĐT. Trả None nếu không tìm thấy."""
    if not sdt or not sdt.strip(): return None
    try:
        sdt_clean = sdt.strip().replace(" ", "")
        res = supabase.table("khach_hang").select("*").eq("sdt", sdt_clean).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception: return None


def _gen_ma_akh() -> str:
    """Sinh mã AKH kế tiếp qua Postgres function."""
    try:
        res = supabase.rpc("get_next_akh_num", {}).execute()
        data = res.data
        num = int(data[0] if isinstance(data, list) else data) if data else 1
        return f"AKH{num:06d}"
    except Exception:
        return f"AKH{(datetime.now() + timedelta(hours=7)).strftime('%y%m%d%H%M')}"


def _upsert_khach_hang(ten: str, sdt: str, chi_nhanh: str = "") -> str:
    """Thêm mới hoặc bỏ qua nếu SĐT đã tồn tại. Trả về ma_kh."""
    sdt_clean = sdt.strip().replace(" ", "")
    existing = lookup_khach_hang(sdt_clean)
    if existing:
        return existing.get("ma_kh", "")
    try:
        ma = _gen_ma_akh()
        supabase.table("khach_hang").insert({
            "ma_kh": ma, "ten_kh": ten.strip(), "sdt": sdt_clean,
            "chi_nhanh_tao": chi_nhanh,
            "created_at": (datetime.now() + timedelta(hours=7)).isoformat(),
            "updated_at": (datetime.now() + timedelta(hours=7)).isoformat(),
        }).execute()
        return ma
    except Exception: return ""


@st.cache_data(ttl=120)
def load_khach_hang_list() -> pd.DataFrame:
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("khach_hang").select("*") \
            .order("updated_at", desc=True).range(offset, offset+batch-1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["tong_ban", "diem_hien_tai"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


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

                # Thông tin khách
                k1, k2, k3 = st.columns(3)
                with k1:
                    st.markdown(f"**Mã KH:** {kh.get('ma_kh','')}")
                    st.markdown(f"**Tên:** {kh.get('ten_kh','')}")
                    st.markdown(f"**SĐT:** {kh.get('sdt','')}")
                with k2:
                    st.markdown(f"**Chi nhánh:** {kh.get('chi_nhanh_tao') or '—'}")
                    st.markdown(f"**Nhóm KH:** {kh.get('nhom_kh') or '—'}")
                    st.markdown(f"**Giới tính:** {kh.get('gioi_tinh') or '—'}")
                with k3:
                    st.markdown(f"**Tổng mua:** {int(kh.get('tong_ban',0)):,}đ".replace(',','.'))
                    st.markdown(f"**Điểm:** {int(kh.get('diem_hien_tai',0))}")
                    st.markdown(f"**GD cuối:** {kh.get('ngay_gd_cuoi') or '—'}")
                if kh.get("ghi_chu"):
                    st.markdown(f"**Ghi chú:** {kh.get('ghi_chu','')}")

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
                        sc_df = sc_df.rename(columns={
                            "ma_phieu":"Mã Phiếu","trang_thai":"Trạng Thái",
                            "mo_ta_loi":"Mô tả","ngay_tiep_nhan":"Ngày TN",
                            "chi_nhanh":"Chi Nhánh"
                        })
                        st.dataframe(sc_df, use_container_width=True, hide_index=True, height=200)
                    else:
                        st.caption("Chưa có phiếu sửa chữa.")
                except Exception: st.caption("Không tải được lịch sử SC.")


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
            # supabase-py có thể trả scalar int hoặc list tuỳ version
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
        # Tìm kết quả — chuẩn hoá bỏ dấu cách để "pin150" khớp "pin 150"
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
        # Luôn hiện container kể cả khi rỗng để tránh collapse đột ngột
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

                # Xem chi tiết phiếu
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
            # Auto-fill: khi SĐT thay đổi, lookup và set tên vào session_state
            sdt_prev_key = f"sc_sdt_prev_{cnt}"
            ten_key      = f"sc_ten_kh_{cnt}"
            kh_key       = f"sc_kh_found_{cnt}"
            if sdt_khach.strip() != st.session_state.get(sdt_prev_key, ""):
                st.session_state[sdt_prev_key] = sdt_khach.strip()
                kh_found = lookup_khach_hang(sdt_khach) if sdt_khach.strip() else None
                st.session_state[kh_key] = kh_found
                if kh_found:
                    # Set trực tiếp vào session_state của text_input tên
                    st.session_state[ten_key] = kh_found["ten_kh"]
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

        # Dịch vụ / linh kiện
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

                # Lưu khách hàng mới vào DB nếu chưa tồn tại
                _upsert_khach_hang(ten_khach.strip(), sdt_khach.strip(), cn_create)

                # Lưu HTML phiếu vào session_state để render sau rerun
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

                # Reset form
                st.session_state["sc_create_count"] = cnt + 1
                st.session_state["sc_active_ma"] = ma
                st.cache_data.clear()
                log_action("SC_CREATE", f"ma={ma} kh={ten_khach} cn={cn_create}")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi tạo phiếu: {e}")

        # Render lệnh in sau rerun (nếu có)
        if st.session_state.get("sc_pending_print_html"):
            _in_phieu_sc(st.session_state.pop("sc_pending_print_html"), key="sc_print_new")
            st.success(f"✓ Đã tạo phiếu — cửa sổ in đang mở")

    # ══════ TAB 3 — CHI TIẾT / CẬP NHẬT (chỉ phiếu chưa Hoàn thành) ══════
    with tab_detail:
        df_all = _load_phieu(tuple(accessible))
        # Không hiện phiếu đã Hoàn thành — chúng đã có hóa đơn
        df_chua_xong = df_all[df_all["trang_thai"] != "Hoàn thành"].copy() if not df_all.empty else df_all
        if df_chua_xong.empty:
            st.info("Không có phiếu nào đang xử lý.")
        else:
            # Search giống tab danh sách
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

                # ── Bảng dịch vụ ──
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

                            # Thêm các dịch vụ mới nếu có
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
        # Chỉ hiện phiếu "Chờ giao khách" — sẵn sàng xuất hóa đơn
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

            # Tóm tắt phiếu
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
                    # Chuyển phiếu sang Hoàn thành
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
            today = datetime.now().date()
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

        today       = datetime.now().date()
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

        # Chuẩn hóa SĐT: bỏ .0 nếu bị float
        sdt_raw = row.get("Điện thoại","") or ""
        try:
            sdt_hd = str(int(float(str(sdt_raw)))) if sdt_raw and str(sdt_raw).strip() not in ("","nan","None") else ""
        except Exception:
            sdt_hd = str(sdt_raw).strip()

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

def _normalize(text: str) -> str:
    """Fuzzy search: bỏ space/dash/dot → 'F 94' khớp 'F94'."""
    import re
    return re.sub(r"[\s\-_./]", "", str(text)).upper()


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
            st.info("Chưa có dữ liệu. Vào ⚙️ Quản trị → Upload để tải lên."); return

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
            df["nhom_hang"]=""; df["thuong_hieu"]=""; df["gia_ban"]=0; df["bao_hanh"]=""
            df["ma_hang"] = df["Mã hàng"]; df["ma_vach"] = df["Mã hàng"]

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
            keyword = st.text_input("", key="hh_search",
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
            st.warning("Không tìm thấy hàng hóa phù hợp."); return

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
                    st.session_state.pop("hh_ma_chon", None); st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            # Tồn kho 3 chi nhánh, highlight CN hiện tại (active, không phải active_cn)
            st.markdown(
                "<div style='font-size:0.82rem;font-weight:600;"
                "color:#555;margin:10px 0 6px;'>Tồn kho chi nhánh</div>",
                unsafe_allow_html=True)
            try:
                all_kho  = load_the_kho(branches_key=tuple(ALL_BRANCHES))
                branch_tons = {cn: 0 for cn in ALL_BRANCHES}
                if not all_kho.empty:
                    rows_kho = all_kho[all_kho["Mã hàng"] == ma_chon]
                    for _, kr in rows_kho.iterrows():
                        cn = kr.get("Chi nhánh","")
                        if cn in branch_tons:
                            branch_tons[cn] = int(kr.get("Tồn cuối kì", 0))

                cn_cols = st.columns(3)
                for idx, cn_name in enumerate(ALL_BRANCHES):
                    with cn_cols[idx]:
                        ton    = branch_tons[cn_name]
                        is_cur = (cn_name == active)  # FIX: active thay vì active_cn
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
            except Exception:
                pass

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

    except Exception as e:
        st.error(f"Lỗi tải Hàng hóa: {e}")


# ==========================================
# MODULE: CHUYỂN HÀNG — v16.0
# Workflow: Phiếu tạm → Đang chuyển → Đã nhận
#           (Admin: → Đã hủy bất cứ lúc nào)
# ==========================================

PHIEU_PER_PAGE   = 20    # Giới hạn 20 phiếu/trang
SUGGEST_LIMIT    = 5     # Giới hạn 5 sản phẩm gợi ý


def _gen_ma_phieu() -> str:
    """
    Sinh mã phiếu serial tăng dần: CH000001, CH000002, ...
    Query max hiện tại trong DB rồi +1.

    Race condition: nếu 2 user tạo cùng lúc cùng ra 1 mã → INSERT lỗi
    do UNIQUE INDEX → _submit_phieu sẽ retry với mã mới.
    """
    try:
        # Lấy tất cả ma_phieu bắt đầu bằng "CH" + 6 số
        res = supabase.table("phieu_chuyen_kho") \
            .select("ma_phieu") \
            .like("ma_phieu", "CH______") \
            .order("ma_phieu", desc=True) \
            .limit(1) \
            .execute()

        if res.data:
            last_ma = res.data[0]["ma_phieu"]
            # Parse số từ "CH000123" → 123
            try:
                last_num = int(last_ma[2:])
            except (ValueError, IndexError):
                last_num = 0
        else:
            last_num = 0

        next_num = last_num + 1
        return f"CH{next_num:06d}"
    except Exception:
        # Fallback an toàn: nếu query fail, dùng timestamp (ít khả năng trùng)
        return f"CH{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:4].upper()}"


def _update_trang_thai_phieu(ma_phieu: str, trang_thai_moi: str,
                              extra: dict = None):
    """Cập nhật trạng thái (và các field liên quan) cho toàn bộ dòng của 1 phiếu."""
    payload = {"trang_thai": trang_thai_moi}
    if extra:
        payload.update(extra)
    supabase.table("phieu_chuyen_kho").update(payload) \
        .eq("ma_phieu", ma_phieu).execute()


def _delete_phieu_rows(ma_phieu: str):
    """Xóa tất cả dòng của một phiếu (dùng cho edit: DELETE + INSERT)."""
    supabase.table("phieu_chuyen_kho").delete() \
        .eq("ma_phieu", ma_phieu).execute()


def _nhan_hang(ma_phieu: str, nguoi_nhan: str = ""):
    """Nhận hàng: trạng thái = Đã nhận, ngày nhận = now, SL nhận = SL chuyển.
    nguoi_nhan: tên người nhận (để ghi vào DB)."""
    # Update chung
    extra = {"ngay_nhan": datetime.now().isoformat()}
    if nguoi_nhan:
        extra["nguoi_nhan"] = nguoi_nhan
    _update_trang_thai_phieu(ma_phieu, "Đã nhận", extra=extra)
    # Copy so_luong_chuyen → so_luong_nhan cho từng dòng
    try:
        rows = supabase.table("phieu_chuyen_kho").select("id,so_luong_chuyen,thanh_tien_chuyen") \
            .eq("ma_phieu", ma_phieu).execute().data or []
        for r in rows:
            supabase.table("phieu_chuyen_kho").update({
                "so_luong_nhan":   int(r.get("so_luong_chuyen") or 0),
                "thanh_tien_nhan": int(r.get("thanh_tien_chuyen") or 0),
            }).eq("id", r["id"]).execute()
        # Tổng SL nhận = tổng SL chuyển
        tong = sum(int(r.get("so_luong_chuyen") or 0) for r in rows)
        supabase.table("phieu_chuyen_kho").update({
            "tong_sl_nhan": tong
        }).eq("ma_phieu", ma_phieu).execute()
    except Exception as e:
        st.warning(f"Đã nhận phiếu nhưng cập nhật SL nhận gặp lỗi: {e}")


def _view_phieu_chuyen(df_all: pd.DataFrame):
    """View danh sách phiếu chuyển kho với action buttons + pagination."""
    active     = get_active_branch()
    accessible = get_accessible_branches()

    # ── Filter bar ──
    col_ky, col_cn = st.columns([2, 2])
    with col_ky:
        ky = st.selectbox("Kỳ:", ["Tháng này","Tháng trước","Tất cả"],
            key="ck_ky", label_visibility="collapsed")
    with col_cn:
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_filter = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible,
                key="ck_cn", label_visibility="collapsed")
        else:
            cn_filter = active
            st.caption(f"📍 {active}")

    # Reset pagination về trang 1 nếu filter thay đổi
    filter_sig = f"{ky}|{cn_filter}"
    if st.session_state.get("_ck_last_filter") != filter_sig:
        st.session_state["_ck_last_filter"] = filter_sig
        st.session_state["ck_vpage"] = 0

    if df_all.empty:
        st.info("Chưa có dữ liệu chuyển hàng. Vào tab **Tạo phiếu** để tạo mới hoặc Quản trị → Upload.")
        return

    df = df_all.copy()

    today       = datetime.now().date()
    first_month = today.replace(day=1)
    first_last  = (first_month - timedelta(days=1)).replace(day=1)

    if ky == "Tháng này":
        df = df[df["_date"] >= first_month]
    elif ky == "Tháng trước":
        last_end = first_month - timedelta(days=1)
        df = df[(df["_date"] >= first_last) & (df["_date"] <= last_end)]

    if cn_filter != "Tất cả":
        df = df[(df["tu_chi_nhanh"] == cn_filter) | (df["toi_chi_nhanh"] == cn_filter)]

    if df.empty:
        st.info("Không có phiếu trong kỳ này.")
        return

    # Summary: số phiếu
    phieu_df = df.drop_duplicates(subset=["ma_phieu"], keep="first")
    so_phieu = len(phieu_df)
    st.metric("Số phiếu trong kỳ", str(so_phieu))

    # ── Pagination ──
    total_pages = max(1, (so_phieu + PHIEU_PER_PAGE - 1) // PHIEU_PER_PAGE)
    page = int(st.session_state.get("ck_vpage", 0))
    if page >= total_pages: page = total_pages - 1
    if page < 0: page = 0

    def _render_pager(pos: str):
        """Render thanh phân trang."""
        if total_pages <= 1: return
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("← Trước", key=f"pg_prev_{pos}",
                        disabled=(page == 0), use_container_width=True):
                st.session_state["ck_vpage"] = page - 1
                st.rerun()
        with c2:
            st.markdown(
                f"<div style='text-align:center;padding-top:6px;font-size:0.85rem;color:#666;'>"
                f"Trang <b>{page+1}</b>/{total_pages} · "
                f"Hiển thị {page*PHIEU_PER_PAGE + 1}"
                f"–{min((page+1)*PHIEU_PER_PAGE, so_phieu)} / {so_phieu} phiếu</div>",
                unsafe_allow_html=True
            )
        with c3:
            if st.button("Sau →", key=f"pg_next_{pos}",
                        disabled=(page >= total_pages - 1), use_container_width=True):
                st.session_state["ck_vpage"] = page + 1
                st.rerun()

    _render_pager("top")
    st.markdown("---")

    # Lấy mã phiếu trang hiện tại (theo thứ tự ngày giảm dần)
    phieu_sorted = phieu_df.sort_values("_ngay", ascending=False)
    start = page * PHIEU_PER_PAGE
    end   = start + PHIEU_PER_PAGE
    ma_phieu_page = phieu_sorted.iloc[start:end]["ma_phieu"].tolist()
    df_page = df[df["ma_phieu"].isin(ma_phieu_page)]

    # Map giá bán
    gia_ban_map = get_gia_ban_map()

    # ── Group by date ──
    dates = sorted(df_page["_date"].dropna().unique(), reverse=True)
    for dt in dates:
        df_day = df_page[df_page["_date"] == dt]
        phieu_day = [m for m in ma_phieu_page if m in df_day["ma_phieu"].values]

        today_dt = datetime.now().date()
        yest     = today_dt - timedelta(days=1)
        if dt == today_dt:   day_lbl = "HÔM NAY"
        elif dt == yest:     day_lbl = "HÔM QUA"
        else:
            try:
                weekday = ["THỨ HAI","THỨ BA","THỨ TƯ","THỨ NĂM",
                           "THỨ SÁU","THỨ BẢY","CHỦ NHẬT"][dt.weekday()]
                day_lbl = f"{weekday}, {dt.strftime('%d/%m/%Y')}"
            except Exception:
                day_lbl = dt.strftime("%d/%m/%Y")

        st.markdown(
            f"<div style='font-size:0.72rem;font-weight:700;color:#aaa;"
            f"letter-spacing:1px;margin:12px 0 6px;'>{day_lbl}</div>",
            unsafe_allow_html=True)

        for ma_phieu in phieu_day:
            df_phieu = df_day[df_day["ma_phieu"] == ma_phieu]
            _render_phieu_card(df_phieu, ma_phieu, gia_ban_map)

    st.markdown("---")
    _render_pager("bottom")


def _render_phieu_card(df_phieu: pd.DataFrame, ma_phieu: str, gia_ban_map: dict):
    """Render một phiếu chuyển trong expander với action buttons."""
    active    = get_active_branch()
    row_h     = df_phieu.iloc[0]

    tu_cn   = row_h.get("tu_chi_nhanh","")
    toi_cn  = row_h.get("toi_chi_nhanh","")
    tt      = str(row_h.get("trang_thai","") or "").strip()
    tsl     = int(row_h.get("tong_sl_chuyen", 0) or 0)
    tmat    = int(row_h.get("tong_mat_hang", 0) or 0)

    nguoi_tao      = str(row_h.get("nguoi_tao","") or "").strip()
    nguoi_nhan     = str(row_h.get("nguoi_nhan","") or "").strip()
    ghi_chu_chuyen = str(row_h.get("ghi_chu_chuyen","") or "").strip()
    ghi_chu_nhan   = str(row_h.get("ghi_chu_nhan","") or "").strip()
    for bad in ("nan", "None"):
        if nguoi_tao.lower() == bad.lower(): nguoi_tao = ""
        if nguoi_nhan.lower() == bad.lower(): nguoi_nhan = ""
        if ghi_chu_chuyen.lower() == bad.lower(): ghi_chu_chuyen = ""
        if ghi_chu_nhan.lower() == bad.lower(): ghi_chu_nhan = ""

    ngay_str = ""
    try:
        ngay_str = pd.Timestamp(row_h["ngay_chuyen"]).strftime("%d/%m %H:%M")
    except Exception:
        pass

    # Tổng giá bán
    total_gia_ban = 0
    for _, r in df_phieu.iterrows():
        mh  = str(r.get("ma_hang",""))
        slc = int(r.get("so_luong_chuyen", 0) or 0)
        gb  = gia_ban_map.get(mh, 0)
        total_gia_ban += slc * gb
    gia_str = (f"{total_gia_ban/1_000_000:.2f} tr đ" if total_gia_ban >= 1_000_000
               else f"{total_gia_ban:,} đ")

    # Màu trạng thái
    tt_colors = {
        "Phiếu tạm":   ("#856404", "#fff8e0"),
        "Đang chuyển": ("#0c5464", "#d1ecf1"),
        "Đã nhận":     ("#1a7f37", "#f0faf4"),
        "Đã hủy":      ("#721c24", "#f5d5d5"),
    }
    tt_color, tt_bg = tt_colors.get(tt, ("#555", "#f5f5f5"))

    # Phiếu tạo trong app = ảnh hưởng tồn kho
    loai_phieu = str(row_h.get("loai_phieu", "") or "")
    is_app_phieu      = (loai_phieu == IN_APP_MARKER)
    is_archived_phieu = (loai_phieu == ARCHIVED_MARKER)

    hang_list = df_phieu[["ten_hang","so_luong_chuyen"]].dropna().head(3)
    hang_str  = ", ".join(
        f"{r['ten_hang']} <b>x{int(r['so_luong_chuyen'])}</b>"
        for _, r in hang_list.iterrows()
    )
    if len(df_phieu) > 3:
        hang_str += f" <span style='color:#aaa;'>+{len(df_phieu)-3} khác</span>"

    # Expander title: hiện cả trạng thái
    title = (f"[{tt}] {tmat} mặt hàng · SL: {tsl}   —   {gia_str}")

    with st.expander(title, expanded=False):
        col_info, col_status = st.columns([4, 1])
        with col_info:
            tu_color  = "#2E86DE"
            toi_color = "#27AE60"
            st.markdown(
                f"<div style='font-size:0.88rem;'>"
                f"Từ <span style='color:{tu_color};font-weight:600;'>{tu_cn}</span>"
                f" → Đến <span style='color:{toi_color};font-weight:600;'>{toi_cn}</span>"
                f"</div>"
                f"<div style='font-size:0.78rem;color:#888;margin-top:3px;'>"
                f"{ngay_str} · {ma_phieu}</div>",
                unsafe_allow_html=True)
        with col_status:
            badge_parts = [
                f"<span style='background:{tt_bg};color:{tt_color};"
                f"padding:3px 10px;border-radius:20px;font-size:0.75rem;"
                f"font-weight:600;'>{tt}</span>"
            ]
            if is_app_phieu:
                badge_parts.append(
                    "<span style='background:#fff0f1;color:#e63946;"
                    "padding:3px 8px;border-radius:20px;font-size:0.7rem;"
                    "font-weight:600;margin-left:4px;'>📱 App</span>"
                )
            elif is_archived_phieu:
                badge_parts.append(
                    "<span style='background:#f0f0f0;color:#888;"
                    "padding:3px 8px;border-radius:20px;font-size:0.7rem;"
                    "font-weight:600;margin-left:4px;'>Kết sổ</span>"
                )
            st.markdown(
                f"<div style='text-align:right;margin-top:4px;'>"
                + "".join(badge_parts)
                + "</div>",
                unsafe_allow_html=True)

        # Người tạo / nhận + ghi chú
        info_parts = []
        if nguoi_tao:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:8px;'>"
                f"👤 <b>Người gửi/tạo phiếu:</b> {nguoi_tao}</div>")
        if nguoi_nhan:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:4px;'>"
                f"📥 <b>Người nhận:</b> {nguoi_nhan}</div>")
        if ghi_chu_chuyen:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:4px;'>"
                f"📝 <b>Ghi chú chuyển:</b> <span style='color:#666;'>{ghi_chu_chuyen}</span></div>")
        if ghi_chu_nhan:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:4px;'>"
                f"📥 <b>Ghi chú nhận:</b> <span style='color:#666;'>{ghi_chu_nhan}</span></div>")
        if info_parts:
            st.markdown("".join(info_parts), unsafe_allow_html=True)

        # Tóm tắt + bảng chi tiết
        st.markdown(
            f"<div style='font-size:0.82rem;color:#444;margin:10px 0 4px;'>"
            f"<b>Tóm tắt:</b> {hang_str}</div>",
            unsafe_allow_html=True)

        cols_detail = ["ten_hang","ma_hang","so_luong_chuyen","so_luong_nhan"]
        cols_avail  = [c for c in cols_detail if c in df_phieu.columns]
        dv = df_phieu[cols_avail].copy()
        dv = dv.rename(columns={
            "ten_hang":"Tên hàng","ma_hang":"Mã hàng",
            "so_luong_chuyen":"SL chuyển","so_luong_nhan":"SL nhận"})
        st.dataframe(dv, use_container_width=True, hide_index=True,
                     height=min(200, 42 + len(dv)*35))

        # ══════ ACTION BUTTONS ══════
        st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
        actions = []

        # Sửa phiếu — chỉ khi Phiếu tạm + đang ở CN chuyển đi
        if tt == "Phiếu tạm" and active == tu_cn:
            actions.append(("sua", "✏ Sửa phiếu", "secondary"))
            actions.append(("xac_nhan", "🚚 Xác nhận chuyển hàng", "primary"))

        # Nhận hàng — chỉ khi Đang chuyển + đang ở CN nhận
        if tt == "Đang chuyển" and active == toi_cn:
            actions.append(("nhan", "✓ Nhận hàng", "primary"))

        # Hủy phiếu — admin only, khi chưa Đã nhận / Đã hủy
        if is_admin() and tt not in ("Đã nhận", "Đã hủy"):
            actions.append(("huy", "🗑 Hủy phiếu", "secondary"))

        if actions:
            cols = st.columns(len(actions))
            for i, (ac, label, btn_type) in enumerate(actions):
                with cols[i]:
                    if st.button(label, key=f"act_{ac}_{ma_phieu}",
                                type=btn_type, use_container_width=True):
                        _handle_action(ac, ma_phieu, df_phieu, tu_cn, toi_cn)

            # Form nhập người nhận (chỉ hiện khi đã bấm "Nhận hàng")
            if st.session_state.get(f"pending_nhan_{ma_phieu}"):
                st.markdown("---")
                # Auto-fill tên user hiện tại
                default_nn = (get_user() or {}).get("ho_ten", "")
                nn_key = f"nn_input_{ma_phieu}"
                if nn_key not in st.session_state:
                    st.session_state[nn_key] = default_nn
                st.text_input("Người nhận:", key=nn_key,
                             placeholder="Tên người nhận hàng")

                # Checkbox xác nhận — chống bấm nhầm
                chk_key = f"chk_nhan_{ma_phieu}"
                confirmed = st.checkbox(
                    "Tôi xác nhận đã kiểm tra và nhận đủ hàng",
                    key=chk_key
                )

                c_ok, c_cancel = st.columns([2, 1])
                with c_ok:
                    if st.button("✓ Xác nhận nhận hàng",
                                key=f"confirm_nhan_{ma_phieu}",
                                type="primary", use_container_width=True,
                                disabled=not confirmed,
                                help=("Tick ô xác nhận ở trên trước"
                                      if not confirmed else None)):
                        nn = st.session_state.get(nn_key, "").strip()
                        if not nn:
                            st.error("Vui lòng nhập người nhận.")
                        else:
                            try:
                                _nhan_hang(ma_phieu, nguoi_nhan=nn)
                                st.cache_data.clear()
                                log_action("PHIEU_RECEIVE",
                                          f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} nguoi_nhan={nn}")
                                st.session_state.pop(f"pending_nhan_{ma_phieu}", None)
                                st.session_state.pop(nn_key, None)
                                st.session_state.pop(chk_key, None)
                                st.success(f"✓ Đã nhận hàng cho phiếu {ma_phieu}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi: {e}")
                with c_cancel:
                    if st.button("Hủy", key=f"cancel_nhan_{ma_phieu}",
                                use_container_width=True):
                        st.session_state.pop(f"pending_nhan_{ma_phieu}", None)
                        st.session_state.pop(nn_key, None)
                        st.session_state.pop(chk_key, None)
                        st.rerun()
        else:
            # Không có action nào khả dụng → hint
            if tt == "Phiếu tạm" and active != tu_cn:
                st.caption(f"ℹ Để sửa/chuyển phiếu này, đổi sang chi nhánh: **{tu_cn}**")
            elif tt == "Đang chuyển" and active != toi_cn:
                st.caption(f"ℹ Để nhận phiếu này, đổi sang chi nhánh: **{toi_cn}**")
            elif tt == "Đã nhận":
                st.caption("✓ Phiếu đã hoàn tất.")
            elif tt == "Đã hủy":
                st.caption("⊘ Phiếu đã hủy.")


def _handle_action(action: str, ma_phieu: str, df_phieu: pd.DataFrame,
                   tu_cn: str, toi_cn: str):
    """Xử lý các action trên phiếu."""
    try:
        if action == "xac_nhan":
            _update_trang_thai_phieu(ma_phieu, "Đang chuyển")
            st.cache_data.clear()
            log_action("PHIEU_CONFIRM", f"ma={ma_phieu} tu={tu_cn} toi={toi_cn}")
            st.success(f"✓ Đã xác nhận chuyển hàng cho phiếu {ma_phieu}")
            st.rerun()

        elif action == "nhan":
            # Không nhận ngay — set flag để form "Người nhận" hiện ra
            st.session_state[f"pending_nhan_{ma_phieu}"] = True
            st.rerun()

        elif action == "huy":
            _update_trang_thai_phieu(ma_phieu, "Đã hủy")
            st.cache_data.clear()
            log_action("PHIEU_CANCEL", f"ma={ma_phieu} tu={tu_cn} toi={toi_cn}",
                      level="warning")
            st.success(f"✓ Đã hủy phiếu {ma_phieu}")
            st.rerun()

        elif action == "sua":
            # Preload vào session state cho tab Tạo phiếu
            row_h = df_phieu.iloc[0]
            items = []
            gia_ban_map = get_gia_ban_map()
            for _, r in df_phieu.iterrows():
                mh = str(r.get("ma_hang",""))
                gb = int(r.get("gia_chuyen") or gia_ban_map.get(mh, 0))
                items.append({
                    "ma_hang":  mh,
                    "ten_hang": str(r.get("ten_hang","")),
                    "so_luong": int(r.get("so_luong_chuyen", 0) or 0),
                    "gia_ban":  gb,
                    "ton_src":  0,  # sẽ cập nhật sau
                })

            st.session_state["ck_editing"]     = ma_phieu
            st.session_state["ck_items"]       = items
            st.session_state["ck_edit_meta"]   = {
                "tu_cn":     tu_cn,
                "toi_cn":    toi_cn,
                "nguoi_tao": str(row_h.get("nguoi_tao","") or ""),
                "ghi_chu":   str(row_h.get("ghi_chu_chuyen","") or ""),
            }
            st.info(f"🔄 Đã tải phiếu **{ma_phieu}** vào chế độ sửa. "
                   "Vui lòng chuyển sang tab **➕ Tạo / Sửa phiếu** ở trên.")
    except Exception as e:
        st.error(f"Lỗi thao tác: {e}")


def _tao_phieu_chuyen():
    """Tab tạo phiếu chuyển mới / sửa phiếu."""
    user   = get_user()
    active = get_active_branch()

    # ── Kiểm tra edit mode ──
    editing_ma = st.session_state.get("ck_editing")
    edit_meta  = st.session_state.get("ck_edit_meta", {}) if editing_ma else {}

    if editing_ma:
        st.markdown(
            f"<div style='background:#fff8e0;border:1px solid #f0c36d;"
            f"border-radius:10px;padding:12px 14px;margin-bottom:10px;'>"
            f"<b style='color:#856404;'>🔄 Đang sửa phiếu: {editing_ma}</b><br>"
            f"<span style='font-size:0.82rem;color:#666;'>"
            f"Nhấn 'Hủy sửa' để thoát, hoặc 'Cập nhật phiếu' để lưu thay đổi.</span>"
            f"</div>",
            unsafe_allow_html=True
        )
        if st.button("✕ Hủy sửa (quay về tạo mới)", key="ck_cancel_edit"):
            st.session_state.pop("ck_editing", None)
            st.session_state.pop("ck_edit_meta", None)
            st.session_state["ck_items"] = []
            st.rerun()
    else:
        st.markdown(
            "<div style='font-size:0.95rem;font-weight:700;margin-bottom:6px;'>"
            "Tạo phiếu chuyển hàng mới</div>",
            unsafe_allow_html=True
        )

    # Load master
    hh = load_hang_hoa()
    if hh.empty:
        st.warning("Chưa có dữ liệu Hàng hóa master. Vui lòng upload trong Quản trị.")
        return

    # ══════ META INFO (từ/đến/người/ghi chú) ══════
    col_tu, col_toi = st.columns(2)
    with col_tu:
        # Từ CN: luôn hiển thị CN hiện tại (không dùng widget có key để tránh lỗi kẹt)
        if is_admin() and not editing_ma:
            tu_cn = st.selectbox("Từ chi nhánh:", ALL_BRANCHES,
                index=ALL_BRANCHES.index(active) if active in ALL_BRANCHES else 0,
                key="ck_tu_cn_sel")
        elif editing_ma:
            tu_cn = edit_meta.get("tu_cn", active)
            st.markdown(
                f"<div style='padding:4px 0;'>"
                f"<div style='font-size:0.82rem;color:#555;margin-bottom:2px;'>Từ chi nhánh</div>"
                f"<div style='background:#f4f6fa;border:1px solid #e0e0e0;"
                f"border-radius:8px;padding:8px 12px;color:#888;'>"
                f"🔒 {tu_cn}</div></div>",
                unsafe_allow_html=True
            )
        else:
            # Role nhan_vien/ke_toan: dùng markdown (không phải widget) để luôn hiện active
            tu_cn = active
            st.markdown(
                f"<div style='padding:4px 0;'>"
                f"<div style='font-size:0.82rem;color:#555;margin-bottom:2px;'>Từ chi nhánh</div>"
                f"<div style='background:#f4f6fa;border:1px solid #e0e0e0;"
                f"border-radius:8px;padding:8px 12px;color:#1a1a2e;font-weight:600;'>"
                f"📍 {tu_cn}</div></div>",
                unsafe_allow_html=True
            )
    with col_toi:
        options_toi = [c for c in ALL_BRANCHES if c != tu_cn]
        if editing_ma:
            # Khóa toi_cn khi sửa
            toi_cn = edit_meta.get("toi_cn", options_toi[0] if options_toi else "")
            st.markdown(
                f"<div style='padding:4px 0;'>"
                f"<div style='font-size:0.82rem;color:#555;margin-bottom:2px;'>Đến chi nhánh</div>"
                f"<div style='background:#f4f6fa;border:1px solid #e0e0e0;"
                f"border-radius:8px;padding:8px 12px;color:#888;'>"
                f"🔒 {toi_cn}</div></div>",
                unsafe_allow_html=True
            )
        else:
            # Dọn session state nếu giá trị cũ không hợp lệ
            stored_toi = st.session_state.get("ck_toi_cn")
            if stored_toi and stored_toi not in options_toi:
                st.session_state.pop("ck_toi_cn", None)
            toi_cn = st.selectbox("Đến chi nhánh:", options_toi, key="ck_toi_cn") \
                     if options_toi else ""

    col_ng, col_gc = st.columns([1, 2])
    with col_ng:
        default_ng = edit_meta.get("nguoi_tao", user.get("ho_ten","") if user else "")
        nguoi_tao = st.text_input("Người gửi/tạo phiếu:",
            value=default_ng, key="ck_ng_tao")
    with col_gc:
        default_gc = edit_meta.get("ghi_chu", "")
        ghi_chu = st.text_input("Ghi chú chuyển (tuỳ chọn):",
            value=default_gc,
            placeholder="VD: Chuyển bổ sung hàng tuần...",
            key="ck_ghi_chu")

    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

    # ══════ GIỎ HÀNG (TRƯỚC DANH SÁCH CHUYỂN) ══════
    if "ck_items" not in st.session_state:
        st.session_state["ck_items"] = []

    # Load tồn kho từ chi nhánh nguồn (cho suggestion + hiển thị trong giỏ)
    kho_src = load_the_kho(branches_key=(tu_cn,)) if tu_cn else pd.DataFrame()
    ton_map = {}
    if not kho_src.empty and "Mã hàng" in kho_src.columns:
        ton_map = dict(zip(
            kho_src["Mã hàng"].astype(str),
            kho_src["Tồn cuối kì"].fillna(0).astype(int)
        ))

    # Cập nhật ton_src cho items hiện tại
    for it in st.session_state["ck_items"]:
        it["ton_src"] = int(ton_map.get(str(it["ma_hang"]), it.get("ton_src", 0)))

    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;margin-bottom:6px;'>"
        f"🛒 Giỏ hàng ({len(st.session_state['ck_items'])} sản phẩm)</div>",
        unsafe_allow_html=True
    )

    if st.session_state["ck_items"]:
        total_sl = 0
        total_gb = 0
        has_overflow = False  # Track có item nào vượt tồn không

        # Container có scroll khi giỏ > 3 items (mỗi item ~60px cao)
        n_items = len(st.session_state["ck_items"])
        if n_items > 3:
            cart_container = st.container(height=240)
        else:
            cart_container = st.container()

        with cart_container:
            for idx, it in enumerate(st.session_state["ck_items"]):
                ton_src = int(it.get("ton_src", 0))
                over    = it["so_luong"] > ton_src
                if over: has_overflow = True

                c_tn, c_sl, c_del = st.columns([4, 2, 1])
                with c_tn:
                    # Highlight đỏ nếu vượt tồn
                    ton_color = "#cf4c2c" if over else "#888"
                    ton_label = (f"Tồn nguồn: <b style='color:{ton_color};'>{ton_src}</b>"
                                + (" ⚠ vượt tồn" if over else ""))
                    st.markdown(
                        f"<div style='padding-top:10px;font-size:0.85rem;'>"
                        f"<b>{it['ten_hang']}</b><br>"
                        f"<span style='font-family:monospace;font-size:0.72rem;color:#777;'>{it['ma_hang']}</span>"
                        f" · <span style='font-size:0.72rem;color:{ton_color};'>{ton_label}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with c_sl:
                    new_sl = st.number_input(
                        "SL", min_value=1, max_value=99999,
                        value=int(it["so_luong"]),
                        step=1, key=f"sl_{idx}", label_visibility="collapsed"
                    )
                    if new_sl != it["so_luong"]:
                        st.session_state["ck_items"][idx]["so_luong"] = int(new_sl)
                with c_del:
                    st.markdown("<div style='padding-top:5px;'>", unsafe_allow_html=True)
                    if st.button("🗑", key=f"del_{idx}", use_container_width=True):
                        st.session_state["ck_items"].pop(idx)
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

                total_sl += it["so_luong"]
                total_gb += it["so_luong"] * it["gia_ban"]

        # Hiện cảnh báo tổng hợp nếu có item vượt tồn
        if has_overflow:
            st.warning(
                "⚠ Một số sản phẩm có SL chuyển vượt tồn nguồn. "
                "Không thể tạo phiếu cho đến khi sửa lại."
            )

        # Tổng
        st.markdown(
            f"<div style='background:#fff8f8;border:1px solid #ffd5d9;border-radius:10px;"
            f"padding:10px 14px;margin-top:10px;'>"
            f"<div style='display:flex;justify-content:space-between;font-size:0.88rem;'>"
            f"<span>Tổng số lượng:</span><b>{total_sl:,}</b></div>"
            f"<div style='display:flex;justify-content:space-between;font-size:0.88rem;margin-top:4px;'>"
            f"<span>Tổng giá bán:</span><b style='color:#e63946;'>"
            f"{(total_gb/1_000_000):.2f} tr đ</b></div>"
            f"</div>",
            unsafe_allow_html=True
        )

        col_clear, col_submit = st.columns([1, 2])
        with col_clear:
            if st.button("Xóa giỏ", use_container_width=True, key="ck_clear"):
                st.session_state["ck_items"] = []
                st.rerun()
        with col_submit:
            submit_label = "💾 Cập nhật phiếu" if editing_ma else "✓ Tạo phiếu chuyển"
            if st.button(submit_label, use_container_width=True,
                        type="primary", key="ck_submit",
                        disabled=has_overflow,
                        help=("Sửa SL các mặt hàng vượt tồn trước khi tạo phiếu"
                              if has_overflow else None)):
                if tu_cn == toi_cn:
                    st.error("Chi nhánh nguồn và đích phải khác nhau.")
                elif not nguoi_tao.strip():
                    st.error("Vui lòng nhập tên người gửi.")
                elif not toi_cn:
                    st.error("Vui lòng chọn chi nhánh đến.")
                else:
                    _submit_phieu(
                        tu_cn, toi_cn, nguoi_tao.strip(), ghi_chu.strip(),
                        st.session_state["ck_items"],
                        editing_ma=editing_ma
                    )
    else:
        st.caption("Giỏ hàng trống. Tìm và thêm sản phẩm ở danh sách bên dưới.")

    st.markdown("<hr style='margin:14px 0 10px;'>", unsafe_allow_html=True)

    # ══════ DANH SÁCH HÀNG CHUYỂN (search + suggest) ══════
    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;margin-bottom:6px;'>"
        "🔍 Danh sách hàng chuyển</div>",
        unsafe_allow_html=True
    )

    search_col, add_col = st.columns([3, 2])
    with search_col:
        kw = st.text_input("", placeholder="🔍 Tìm sản phẩm theo mã, tên...",
                          key="ck_search", label_visibility="collapsed")
    with add_col:
        only_in_stock = st.checkbox("Chỉ hàng còn tồn ở nguồn",
                                    value=True, key="ck_only_stock")

    # Filter
    hh_list = hh.copy()
    hh_list["_ton_src"] = hh_list["ma_hang"].astype(str).map(ton_map).fillna(0).astype(int)
    if kw.strip():
        kwn = _normalize(kw)
        hh_list["_n_ma"]  = hh_list["ma_hang"].apply(_normalize)
        hh_list["_n_ten"] = hh_list["ten_hang"].apply(_normalize)
        hh_list = hh_list[
            hh_list["_n_ma"].str.contains(kwn, na=False) |
            hh_list["_n_ten"].str.contains(kwn, na=False)
        ]
    if only_in_stock:
        hh_list = hh_list[hh_list["_ton_src"] > 0]
    hh_list = hh_list.head(SUGGEST_LIMIT)

    if not hh_list.empty:
        for _, r in hh_list.iterrows():
            mh = str(r["ma_hang"])
            tn = str(r["ten_hang"])
            gb = int(r.get("gia_ban", 0) or 0)
            tn_src = int(r.get("_ton_src", 0) or 0)
            already = any(it["ma_hang"] == mh for it in st.session_state["ck_items"])

            c_info, c_btn = st.columns([5, 1])
            with c_info:
                st.markdown(
                    f"<div style='padding:6px 0;font-size:0.85rem;'>"
                    f"<b>{tn}</b><br>"
                    f"<span style='font-family:monospace;font-size:0.75rem;color:#777;'>{mh}</span>"
                    f" · <span style='color:#888;font-size:0.78rem;'>Tồn: {tn_src}</span>"
                    f" · <span style='color:#1a7f37;font-size:0.78rem;'>{gb:,}đ</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with c_btn:
                if already:
                    st.caption("✓ Đã thêm")
                else:
                    if st.button("➕", key=f"add_{mh}", use_container_width=True):
                        st.session_state["ck_items"].append({
                            "ma_hang":  mh,
                            "ten_hang": tn,
                            "so_luong": 1,
                            "gia_ban":  gb,
                            "ton_src":  tn_src,
                        })
                        st.rerun()

        if len(hh) > SUGGEST_LIMIT and not kw.strip():
            st.caption(f"ℹ Hiển thị {SUGGEST_LIMIT} sản phẩm — nhập từ khóa để tìm chính xác hơn.")
    elif kw.strip():
        st.caption("Không tìm thấy sản phẩm phù hợp.")
    else:
        st.caption("Gõ mã/tên sản phẩm để tìm kiếm.")


def _validate_stock(tu_cn: str, items: list, editing_ma: str = None) -> tuple:
    """
    Kiểm tra SL chuyển có vượt quá tồn hiệu dụng không.
    Trả về (ok: bool, errors: list[str]).

    Khi edit: cộng bù lại SL của phiếu cũ (vì phiếu cũ đang trong trạng thái
    Phiếu tạm nên chưa ảnh hưởng delta, nhưng logic đúng hơn là tính độc lập).
    Phiếu tạm → delta=0, nên chỉ cần so với tồn hiện tại.
    """
    if not tu_cn or not items:
        return True, []

    # Load tồn hiệu dụng hiện tại tại CN nguồn (đã áp dụng delta từ phiếu App)
    kho = load_the_kho(branches_key=(tu_cn,))
    if kho.empty or "Mã hàng" not in kho.columns:
        return True, []  # Không có dữ liệu kho → skip (fallback mềm)

    ton_map = dict(zip(
        kho["Mã hàng"].astype(str),
        kho["Tồn cuối kì"].fillna(0).astype(int)
    ))

    errors = []
    for it in items:
        mh = str(it["ma_hang"])
        sl = int(it["so_luong"])
        ton = ton_map.get(mh, 0)
        if sl > ton:
            errors.append(
                f"• **{it['ten_hang']}** ({mh}): "
                f"yêu cầu chuyển {sl:,}, tồn hiệu dụng chỉ có {ton:,}"
            )
    return len(errors) == 0, errors


def _submit_phieu(tu_cn: str, toi_cn: str, nguoi_tao: str, ghi_chu: str,
                  items: list, editing_ma: str = None):
    """Insert phiếu mới hoặc update phiếu đang sửa."""
    # ── Validate tồn kho trước khi submit ──
    ok, errors = _validate_stock(tu_cn, items, editing_ma=editing_ma)
    if not ok:
        st.error(
            "**Không thể tạo phiếu** — một số sản phẩm vượt quá tồn hiệu dụng "
            f"tại **{tu_cn}**:\n\n" + "\n".join(errors) +
            "\n\nVui lòng giảm SL hoặc xóa sản phẩm khỏi giỏ rồi thử lại."
        )
        log_action(
            "STOCK_VALIDATION_FAIL",
            f"tu={tu_cn} items={len(items)} errors={len(errors)}",
            level="warning"
        )
        return

    try:
        with st.spinner("Đang xử lý..."):
            now_iso  = datetime.now().isoformat()

            tong_sl    = sum(it["so_luong"] for it in items)
            tong_mat   = len(items)
            tong_gtri  = sum(it["so_luong"] * it["gia_ban"] for it in items)

            # Khi sửa: giữ nguyên trạng thái "Phiếu tạm" (chỉ phiếu tạm mới sửa được)
            trang_thai = "Phiếu tạm"

            def _build_records(ma):
                """Build records với ma_phieu cho sẵn."""
                return [{
                    "ma_phieu":         ma,
                    "loai_phieu":       IN_APP_MARKER,
                    "tu_chi_nhanh":     tu_cn,
                    "toi_chi_nhanh":    toi_cn,
                    "ngay_chuyen":      now_iso,
                    "ngay_nhan":        None,
                    "nguoi_tao":        nguoi_tao,
                    "ghi_chu_chuyen":   ghi_chu or None,
                    "ghi_chu_nhan":     None,
                    "tong_sl_chuyen":   tong_sl,
                    "tong_sl_nhan":     0,
                    "tong_gia_tri":     int(tong_gtri),
                    "tong_mat_hang":    tong_mat,
                    "trang_thai":       trang_thai,
                    "ma_hang":          str(it["ma_hang"]),
                    "ma_vach":          None,
                    "ten_hang":         str(it["ten_hang"]),
                    "thuong_hieu":      None,
                    "so_luong_chuyen":  int(it["so_luong"]),
                    "so_luong_nhan":    0,
                    "gia_chuyen":       int(it["gia_ban"]),
                    "thanh_tien_chuyen":int(it["so_luong"] * it["gia_ban"]),
                    "thanh_tien_nhan":  0,
                } for it in items]

            if editing_ma:
                # Sửa phiếu: dùng luôn ma cũ, DELETE + INSERT
                _delete_phieu_rows(editing_ma)
                supabase.table("phieu_chuyen_kho").insert(_build_records(editing_ma)).execute()
                ma_phieu = editing_ma
                msg = f"💾 Đã cập nhật phiếu **{ma_phieu}**!"
                log_action(
                    "PHIEU_UPDATE",
                    f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} "
                    f"sl={tong_sl} items={tong_mat}"
                )
            else:
                # Tạo mới: retry nếu duplicate (race condition hiếm gặp)
                ma_phieu = None
                last_err = None
                for attempt in range(3):
                    try_ma = _gen_ma_phieu()
                    try:
                        supabase.table("phieu_chuyen_kho").insert(_build_records(try_ma)).execute()
                        ma_phieu = try_ma
                        break
                    except Exception as e:
                        last_err = e
                        err_str = str(e).lower()
                        # Chỉ retry nếu là duplicate key error
                        if "duplicate" in err_str or "unique" in err_str:
                            _logger.warning(
                                f"PHIEU_RETRY — attempt={attempt+1} ma={try_ma} "
                                f"(race condition, thử lại)"
                            )
                            continue
                        # Lỗi khác → raise ngay, không retry
                        raise

                if ma_phieu is None:
                    raise RuntimeError(
                        f"Không sinh được mã phiếu sau 3 lần thử: {last_err}"
                    )

                msg = f"✓ Tạo phiếu **{ma_phieu}** thành công!"
                log_action(
                    "PHIEU_CREATE",
                    f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} "
                    f"sl={tong_sl} items={tong_mat} gtri={int(tong_gtri)}"
                )

            # Reset
            st.session_state["ck_items"] = []
            st.session_state.pop("ck_editing", None)
            st.session_state.pop("ck_edit_meta", None)
            st.cache_data.clear()

            st.success(msg)
            if not editing_ma:
                st.balloons()

            # Delay cho user thấy success message, rồi auto-rerun
            # để form reset + chuyển về trạng thái sạch
            import time
            time.sleep(1.5)
            st.rerun()
    except Exception as e:
        st.error(f"Lỗi xử lý phiếu: {e}")


def module_chuyen_hang():
    """View + Tạo/Sửa phiếu chuyển kho."""
    try:
        active    = get_active_branch()
        view_cns  = tuple(get_accessible_branches()) if is_ke_toan_or_admin() else (active,)
        df_all    = load_phieu_chuyen_kho(branches_key=view_cns)

        # Tab label động: khi đang edit → nhắc user
        editing = st.session_state.get("ck_editing")
        create_tab_label = ("➕ Tạo / Sửa phiếu"
                           + (" 🔄" if editing else ""))

        tab_view, tab_create = st.tabs(
            ["📋 Danh sách phiếu", create_tab_label]
        )
        with tab_view:
            _view_phieu_chuyen(df_all)
        with tab_create:
            _tao_phieu_chuyen()

    except Exception as e:
        st.error(f"Lỗi tải Chuyển hàng: {e}")


# ==========================================
# MODULE: QUẢN LÝ NHÂN VIÊN
# ==========================================

def module_nhan_vien():
    st.markdown("### Quản lý nhân viên")
    try:
        cn_res = supabase.table("chi_nhanh").select("*").eq("active",True).execute()
        cn_map = {cn["ten"]: cn["id"] for cn in cn_res.data} if cn_res.data else {}
    except Exception as e:
        st.error(f"Lỗi tải chi nhánh: {e}"); return

    tab_add, tab_list = st.tabs(["Thêm nhân viên","Danh sách"])
    with tab_add:
        with st.form("them_nv", clear_on_submit=True, border=False):
            c1,c2 = st.columns(2)
            with c1:
                nu  = st.text_input("Username:")
                nn  = st.text_input("Họ tên:")
                nr  = st.selectbox("Role:", ["nhan_vien","ke_toan","admin"])
            with c2:
                np1 = st.text_input("Mật khẩu:", type="password")
                np2 = st.text_input("Xác nhận:", type="password")
                ncs = st.multiselect("Chi nhánh:", list(cn_map.keys()))
            if st.form_submit_button("Tạo tài khoản", type="primary"):
                if not all([nu,nn,np1,np2]): st.error("Điền đầy đủ.")
                elif np1!=np2: st.error("Mật khẩu không khớp.")
                elif len(np1)<6: st.error("Tối thiểu 6 ký tự.")
                elif not ncs and nr!="admin": st.error("Chọn ít nhất một chi nhánh.")
                else:
                    try:
                        res = supabase.table("nhan_vien").insert({
                            "username":nu,"ho_ten":nn,"mat_khau":hash_password(np1),"role":nr,"active":True
                        }).execute()
                        nv_id = res.data[0]["id"]
                        for cn in ncs:
                            supabase.table("nhan_vien_chi_nhanh").insert({
                                "nhan_vien_id":nv_id,"chi_nhanh_id":cn_map[cn]
                            }).execute()
                        st.success(f"Tạo tài khoản **{nn}** thành công!")
                    except Exception as e: st.error(f"Lỗi: {e}")

    with tab_list:
        try:
            nv_list = supabase.table("nhan_vien").select("*").order("id").execute().data or []
            cur = get_user()
            for nv in nv_list:
                cn2      = supabase.table("nhan_vien_chi_nhanh") \
                    .select("chi_nhanh(ten)").eq("nhan_vien_id",nv["id"]).execute()
                cn_names = [x["chi_nhanh"]["ten"] for x in cn2.data] if cn2.data else []
                status   = "Hoạt động" if nv["active"] else "Đã khóa"
                role_lbl = {"admin":"Admin","ke_toan":"Kế toán","nhan_vien":"Nhân viên"}.get(nv["role"],"")
                is_self  = (nv["id"]==cur.get("id"))
                with st.expander(
                    f"**{nv['ho_ten']}** · {role_lbl} · {status}"
                    + (" (bạn)" if is_self else "")
                ):
                    st.caption(f"Username: `{nv['username']}` · Chi nhánh: {', '.join(cn_names) if cn_names else '—'}")
                    ci,cp,ca = st.columns([2,2,1])
                    with ci:
                        nr2 = st.selectbox("Role:",["nhan_vien","ke_toan","admin"],
                            index=["nhan_vien","ke_toan","admin"].index(nv["role"]),
                            key=f"role_{nv['id']}")
                        if st.button("Lưu role", key=f"sr_{nv['id']}"):
                            supabase.table("nhan_vien").update({"role":nr2}).eq("id",nv["id"]).execute()
                            st.success("Đã cập nhật!"); st.rerun()
                    with cp:
                        np_ = st.text_input("Mật khẩu mới:", type="password", key=f"np_{nv['id']}")
                        if st.button("Đổi mật khẩu", key=f"sp_{nv['id']}"):
                            if np_ and len(np_)>=6:
                                supabase.table("nhan_vien").update(
                                    {"mat_khau":hash_password(np_)}).eq("id",nv["id"]).execute()
                                st.success("Đã đổi mật khẩu!")
                            else: st.warning("Tối thiểu 6 ký tự.")
                    with ca:
                        if not is_self:
                            if st.button("Khóa" if nv["active"] else "Mở khóa", key=f"tog_{nv['id']}"):
                                supabase.table("nhan_vien").update(
                                    {"active":not nv["active"]}).eq("id",nv["id"]).execute()
                                st.rerun()
                        else: st.caption("(bạn)")
        except Exception as e: st.error(f"Lỗi: {e}")


# ==========================================
# MODULE: QUẢN TRỊ
# ==========================================

def module_quan_tri():
    if not is_admin():
        st.error("Bạn không có quyền truy cập."); return

    # ── Banner nhắc kết sổ (nếu vượt ngưỡng) ──
    rem = get_archive_reminder()
    if rem["need_reminder"]:
        st.warning(
            f"⚠ **Nên kết sổ phiếu App** — đã **{rem['days_oldest']} ngày** kể từ "
            f"phiếu App cũ nhất (ngày {rem['oldest_date'].strftime('%d/%m/%Y')}), "
            f"hiện có **{rem['n_active']} phiếu** đang tính delta vào tồn kho. "
            f"Quy trình: upload `the_kho` mới từ KiotViet ở tab **Upload**, "
            f"rồi sang tab **Xóa dữ liệu** để nhấn nút **Kết sổ tất cả phiếu App**."
        )

    tab_up, tab_del, tab_nv, tab_kh = st.tabs(["Upload","Xóa dữ liệu","Nhân viên","Upload KH"])

    with tab_up:
        s1, s2, s3, s4 = st.tabs(["Hàng hóa (master)","Thẻ kho","Hóa đơn","Chuyển kho"])

        with s1:
            st.caption("File **Danh sách sản phẩm** từ KiotViet (.xlsx) — upload một lần, cập nhật khi có sản phẩm mới.")
            up = st.file_uploader("Chọn file:", type=["xlsx","xls"], key="up_hh")
            if up:
                try:
                    df = pd.read_excel(up)
                    st.success(f"Đọc được {len(df)} dòng")
                    col_map = {
                        "Mã hàng":          "ma_hang",
                        "Mã vạch":          "ma_vach",
                        "Tên hàng":         "ten_hang",
                        "Nhóm hàng(3 Cấp)": "nhom_hang",
                        "Thương hiệu":      "thuong_hieu",
                        "Giá bán":          "gia_ban",
                        "Bảo hành":         "bao_hanh",
                        "Đang kinh doanh":  "dang_kd",
                    }
                    miss = [c for c in ["Mã hàng","Tên hàng"] if c not in df.columns]
                    if miss:
                        st.error(f"Thiếu cột bắt buộc: {', '.join(miss)}")
                    else:
                        avail = {k:v for k,v in col_map.items() if k in df.columns}
                        df_out = df[list(avail.keys())].rename(columns=avail).copy()
                        if "nhom_hang" in df_out.columns:
                            split = df_out["nhom_hang"].fillna("").str.split(">>", n=1, expand=True)
                            df_out["nhom_cha"] = split[0].str.strip()
                            df_out["nhom_con"] = split[1].str.strip() if 1 in split.columns else ""
                            df_out["nhom_con"] = df_out["nhom_con"].fillna("")
                        df_out["ma_hang"]  = df_out["ma_hang"].astype(str).str.strip()
                        df_out["ten_hang"] = df_out["ten_hang"].astype(str).str.strip()
                        if "gia_ban" in df_out.columns:
                            df_out["gia_ban"] = pd.to_numeric(df_out["gia_ban"], errors="coerce").fillna(0).astype(int)
                        if "dang_kd" in df_out.columns:
                            df_out["dang_kd"] = df_out["dang_kd"].fillna(1).astype(bool)

                        def _clean(val):
                            if val is None: return None
                            try:
                                if pd.isna(val): return None
                            except Exception: pass
                            if isinstance(val, (np.integer,)):  return int(val)
                            if isinstance(val, (np.floating,)): return None if np.isnan(val) else float(val)
                            if isinstance(val, float) and (val != val): return None
                            return val

                        records = [
                            {k: _clean(v) for k, v in row.items()}
                            for row in df_out.to_dict(orient="records")
                        ]

                        st.info(f"{len(records)} sản phẩm sẽ được upsert")
                        with st.expander("Xem trước"):
                            st.dataframe(df_out.head(), use_container_width=True, hide_index=True)

                        if st.button("Upload Hàng hóa", key="btn_up_hh", type="primary"):
                            with st.spinner("Đang upload..."):
                                total, ok = len(records), 0
                                prog = st.progress(0, text="Đang upload...")
                                for i in range(0, total, 500):
                                    try:
                                        supabase.table("hang_hoa").upsert(
                                            records[i:i+500],
                                            on_conflict="ma_hang"
                                        ).execute()
                                        ok += len(records[i:i+500])
                                        prog.progress(min(ok/total,1.0), text=f"{ok}/{total}...")
                                    except Exception as e:
                                        st.error(f"Batch {i}: {e}")
                                prog.empty()
                                if ok == total:
                                    log_action("UPLOAD_HANG_HOA", f"rows={ok}")
                                    st.success(f"✅ Upsert {ok} sản phẩm thành công!")
                                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

        with s2:
            st.caption("File **Xuất nhập tồn chi tiết** từ KiotViet (.xlsx)")
            up = st.file_uploader("Chọn file:", type=["xlsx","xls"], key="up_kho")
            if up:
                try:
                    df   = pd.read_excel(up)
                    st.success(f"Đọc được {len(df)} dòng")
                    miss = [c for c in ["Mã hàng","Tên hàng","Chi nhánh","Tồn cuối kì"] if c not in df.columns]
                    if miss: st.error(f"Thiếu cột: {', '.join(miss)}")
                    else:
                        st.info(f"Chi nhánh: {', '.join(df['Chi nhánh'].unique())}")
                        with st.expander("Xem trước"):
                            st.dataframe(df.head(), use_container_width=True, hide_index=True)
                        if st.button("Upload thẻ kho", key="btn_up_kho", type="primary"):
                            with st.spinner("Đang xử lý..."):
                                tc = ["Nhóm hàng","Mã hàng","Mã vạch","Tên hàng","Thương hiệu","Chi nhánh"]
                                for col in tc:
                                    if col in df.columns:
                                        df[col] = df[col].astype(str).str.replace(","," ",regex=False) \
                                            .str.replace("\n"," ",regex=False).str.strip()
                                        df.loc[df[col]=="nan",col] = None
                                for col in [c for c in df.columns if c not in tc]:
                                    df[col] = pd.to_numeric(df[col],errors="coerce").fillna(0).astype(int)

                                def _clean_val(v):
                                    if v is None: return None
                                    try:
                                        if pd.isna(v): return None
                                    except Exception: pass
                                    if isinstance(v, float) and (v != v): return None
                                    if isinstance(v, np.integer): return int(v)
                                    if isinstance(v, np.floating): return None if np.isnan(v) else float(v)
                                    return v

                                records = [{k: _clean_val(v) for k,v in row.items()}
                                           for row in df.to_dict(orient="records")]

                                # Xóa các dòng có (Mã hàng, Chi nhánh) trùng với file đang upload
                                # để tránh duplicate — lịch sử mã hàng/chi nhánh khác không bị ảnh hưởng
                                ma_hang_list = df["Mã hàng"].dropna().unique().tolist()
                                cn_list = df["Chi nhánh"].dropna().unique().tolist()
                                try:
                                    supabase.table("the_kho").delete() \
                                        .in_("Mã hàng", ma_hang_list) \
                                        .in_("Chi nhánh", cn_list) \
                                        .execute()
                                except Exception as e:
                                    st.error(f"Lỗi xóa dữ liệu cũ: {e}")
                                    st.stop()

                                total,ok = len(records),0
                                prog = st.progress(0,text="Đang upload...")
                                for i in range(0,total,500):
                                    try:
                                        supabase.table("the_kho").insert(records[i:i+500]).execute()
                                        ok+=len(records[i:i+500])
                                        prog.progress(min(ok/total,1.0),text=f"{ok}/{total}...")
                                    except Exception as e: st.error(f"Batch {i}: {e}")
                                prog.empty()
                                if ok==total:
                                    log_action("UPLOAD_THE_KHO", f"rows={ok}")
                                    st.success(f"Upload {ok} dòng thành công!"); st.cache_data.clear()
                except Exception as e: st.error(f"Lỗi: {e}")

        with s3:
            st.caption("File **Danh sách hóa đơn** từ KiotViet (.xlsx)")
            up = st.file_uploader("Chọn file:", type=["xlsx","xls"], key="up_hd")
            if up:
                try:
                    df   = pd.read_excel(up)
                    st.success(f"Đọc được {len(df)} dòng")
                    miss = [c for c in ["Mã hóa đơn","Thời gian","Chi nhánh"] if c not in df.columns]
                    if miss: st.error(f"Thiếu cột: {', '.join(miss)}")
                    else:
                        st.info(f"{df['Mã hóa đơn'].nunique()} hóa đơn · {', '.join(df['Chi nhánh'].unique())}")
                        with st.expander("Xem trước"):
                            st.dataframe(df.head(), use_container_width=True, hide_index=True)
                        if st.button("Upload hóa đơn", key="btn_up_hd", type="primary"):
                            with st.spinner("Đang xử lý..."):
                                for col in df.columns:
                                    if df[col].dtype=="object":
                                        df[col] = df[col].astype(str).str.replace("\n"," ",regex=False).str.strip()
                                        df.loc[df[col]=="nan",col] = None
                                for col in ["Tổng tiền hàng","Khách cần trả","Khách đã trả","Đơn giá","Thành tiền"]:
                                    if col in df.columns:
                                        df[col] = pd.to_numeric(df[col],errors="coerce").fillna(0).astype(int)

                                def _clean_val_hd(v):
                                    if v is None: return None
                                    try:
                                        if pd.isna(v): return None
                                    except Exception: pass
                                    if isinstance(v, float) and (v != v): return None
                                    if isinstance(v, np.integer): return int(v)
                                    if isinstance(v, np.floating): return None if np.isnan(v) else float(v)
                                    # Timestamp: convert sang format giống KiotViet để đồng nhất trong DB
                                    if isinstance(v, pd.Timestamp):
                                        return v.strftime("%d/%m/%Y %H:%M:%S")
                                    return v

                                records = [{k: _clean_val_hd(v) for k,v in row.items()}
                                           for row in df.to_dict(orient="records")]

                                # Xóa các hóa đơn trùng mã trong file đang upload
                                # → upload lại file cũ không bị nhân đôi, lịch sử tháng khác an toàn
                                ma_hd_list = df["Mã hóa đơn"].dropna().unique().tolist()
                                try:
                                    supabase.table("hoa_don").delete() \
                                        .in_("Mã hóa đơn", ma_hd_list) \
                                        .execute()
                                except Exception as e:
                                    st.error(f"Lỗi xóa dữ liệu cũ: {e}")
                                    st.stop()

                                total,ok = len(records),0
                                prog = st.progress(0,text="Đang upload...")
                                for i in range(0,total,500):
                                    try:
                                        supabase.table("hoa_don").insert(records[i:i+500]).execute()
                                        ok+=len(records[i:i+500])
                                        prog.progress(min(ok/total,1.0),text=f"{ok}/{total}...")
                                    except Exception as e: st.error(f"Batch {i}: {e}")
                                    except Exception as e: st.error(f"Batch {i}: {e}")
                                prog.empty()
                                if ok==total:
                                    log_action("UPLOAD_HOA_DON", f"rows={ok}")
                                    st.success(f"Upload {ok} dòng thành công!"); st.cache_data.clear()
                except Exception as e: st.error(f"Lỗi: {e}")

        with s4:
            st.caption("File **Danh sách chi tiết chuyển hàng** từ KiotViet (.xlsx)")
            up = st.file_uploader("Chọn file:", type=["xlsx","xls"], key="up_ck")
            if up:
                try:
                    df = pd.read_excel(up)
                    st.success(f"Đọc được {len(df)} dòng — {df['Mã chuyển hàng'].nunique()} phiếu")
                    miss = [c for c in ["Mã chuyển hàng","Từ chi nhánh","Tới chi nhánh"] if c not in df.columns]
                    if miss:
                        st.error(f"Thiếu cột: {', '.join(miss)}")
                    else:
                        st.info(f"Từ {df['Ngày chuyển'].min()} đến {df['Ngày chuyển'].max()}")
                        with st.expander("Xem trước"):
                            st.dataframe(df.head(), use_container_width=True, hide_index=True)

                        if st.button("Upload Chuyển kho", key="btn_up_ck", type="primary"):
                            with st.spinner("Đang xử lý..."):
                                col_map = {
                                    "Mã chuyển hàng":    "ma_phieu",
                                    "Loại phiếu":        "loai_phieu",
                                    "Từ chi nhánh":      "tu_chi_nhanh",
                                    "Tới chi nhánh":     "toi_chi_nhanh",
                                    "Ngày chuyển":       "ngay_chuyen",
                                    "Ngày nhận":         "ngay_nhan",
                                    "Người tạo":         "nguoi_tao",
                                    "Ghi chú chuyển":    "ghi_chu_chuyen",
                                    "Ghi chú nhận":      "ghi_chu_nhan",
                                    "Tổng SL chuyển":    "tong_sl_chuyen",
                                    "Tổng SL nhận":      "tong_sl_nhan",
                                    "Tổng giá trị chuyển":"tong_gia_tri",
                                    "Tổng số mặt hàng":  "tong_mat_hang",
                                    "Trạng thái":        "trang_thai",
                                    "Mã hàng":           "ma_hang",
                                    "Mã vạch":           "ma_vach",
                                    "Tên hàng":          "ten_hang",
                                    "Thương hiệu":       "thuong_hieu",
                                    "Số lượng chuyển":   "so_luong_chuyen",
                                    "Số lượng nhận":     "so_luong_nhan",
                                    "Giá chuyển/nhận":   "gia_chuyen",
                                    "Thành tiền chuyển": "thanh_tien_chuyen",
                                    "Thành tiền nhận":   "thanh_tien_nhan",
                                }
                                avail = {k:v for k,v in col_map.items() if k in df.columns}
                                df_out = df[list(avail.keys())].rename(columns=avail).copy()

                                for col in df_out.select_dtypes(include="object").columns:
                                    df_out[col] = df_out[col].astype(str).str.strip()
                                    df_out.loc[df_out[col]=="nan", col] = None

                                int_cols = ["tong_sl_chuyen","tong_sl_nhan","tong_mat_hang",
                                            "so_luong_chuyen","so_luong_nhan",
                                            "gia_chuyen","thanh_tien_chuyen","thanh_tien_nhan",
                                            "tong_gia_tri"]
                                for col in int_cols:
                                    if col in df_out.columns:
                                        df_out[col] = pd.to_numeric(df_out[col], errors="coerce").fillna(0).astype(int)

                                for col in ["ngay_chuyen","ngay_nhan"]:
                                    if col in df_out.columns:
                                        df_out[col] = pd.to_datetime(df_out[col], errors="coerce")
                                        df_out[col] = df_out[col].apply(
                                            lambda x: x.isoformat() if pd.notna(x) else None)

                                def _clean(v):
                                    if v is None: return None
                                    try:
                                        if pd.isna(v): return None
                                    except Exception: pass
                                    if isinstance(v, np.integer):  return int(v)
                                    if isinstance(v, np.floating):
                                        return None if np.isnan(v) else float(v)
                                    return v

                                records = [{k: _clean(v) for k,v in row.items()}
                                           for row in df_out.to_dict(orient="records")]

                                total, ok = len(records), 0
                                prog = st.progress(0, text="Đang upload...")
                                for i in range(0, total, 500):
                                    try:
                                        supabase.table("phieu_chuyen_kho").insert(
                                            records[i:i+500]).execute()
                                        ok += len(records[i:i+500])
                                        prog.progress(min(ok/total,1.0), text=f"{ok}/{total}...")
                                    except Exception as e:
                                        st.error(f"Batch {i}: {e}")
                                prog.empty()
                                if ok == total:
                                    log_action("UPLOAD_CHUYEN_KHO",
                                              f"rows={ok} phieu={df['Mã chuyển hàng'].nunique()}")
                                    st.success(f"✅ Upload {ok} dòng ({df['Mã chuyển hàng'].nunique()} phiếu)!")
                                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    with tab_del:
        st.caption("Xóa dữ liệu cũ trước khi upload lại.")
        c1,c2 = st.columns(2)
        with c1:
            bang = st.selectbox("Bảng:", ["the_kho","hoa_don","phieu_chuyen_kho"], key="del_table")
        with c2:
            try:
                if bang == "phieu_chuyen_kho":
                    ds = ["Tất cả"] + ALL_BRANCHES
                else:
                    tmp = load_the_kho(tuple(ALL_BRANCHES)) if bang=="the_kho" else load_hoa_don(tuple(ALL_BRANCHES))
                    ds  = ["Tất cả"]+sorted(tmp["Chi nhánh"].dropna().unique().tolist()) if not tmp.empty else ["Tất cả"]
            except: ds = ["Tất cả"]
            cn_x = st.selectbox("Chi nhánh:", ds, key="del_cn")
        try:
            q   = supabase.table(bang).select("id",count="exact")
            if cn_x!="Tất cả":
                if bang == "phieu_chuyen_kho":
                    pass
                else:
                    q = q.eq("Chi nhánh",cn_x)
            cnt = q.execute().count or 0
        except: cnt="?"
        pv = f"chi nhánh **{cn_x}**" if cn_x!="Tất cả" else "**toàn bộ**"
        st.warning(f"Sẽ xóa **{cnt}** dòng từ `{bang}` — {pv}")
        confirm = st.text_input("Gõ XOA để xác nhận:", key="confirm_del")
        if st.button("Xóa dữ liệu", key="btn_del", type="primary"):
            if confirm!="XOA": st.error("Gõ đúng XOA để xác nhận.")
            else:
                with st.spinner("Đang xóa..."):
                    try:
                        q = supabase.table(bang).delete()
                        if bang == "phieu_chuyen_kho":
                            q = q.neq("id", -999999)
                        else:
                            q = q.eq("Chi nhánh",cn_x) if cn_x!="Tất cả" else q.neq("id",-999999)
                        q.execute()
                        log_action("DATA_DELETE",
                                  f"table={bang} chi_nhanh={cn_x} count={cnt}",
                                  level="warning")
                        st.success("Xóa thành công!"); st.cache_data.clear()
                    except Exception as e: st.error(f"Lỗi: {e}")

        # ══════ KẾT SỔ PHIẾU APP ══════
        st.markdown("---")
        st.markdown("**🔄 Kết sổ phiếu App (đồng bộ sau khi upload the_kho mới)**")
        st.caption(
            "Sau khi bạn upload the_kho mới từ KiotViet (snapshot đã phản ánh các "
            "chuyển hàng vừa rồi), nhấn nút này để phiếu App <b>ngừng cộng/trừ</b> "
            "thêm vào tồn kho. Phiếu vẫn lưu trong danh sách để tra cứu lịch sử.",
            unsafe_allow_html=True
        )
        try:
            n_active = supabase.table("phieu_chuyen_kho").select("id", count="exact") \
                .eq("loai_phieu", IN_APP_MARKER).execute().count or 0
            n_archived = supabase.table("phieu_chuyen_kho").select("id", count="exact") \
                .eq("loai_phieu", ARCHIVED_MARKER).execute().count or 0
        except Exception:
            n_active, n_archived = 0, 0

        ca1, ca2 = st.columns(2)
        with ca1:
            st.metric("Đang active (tính delta)", str(n_active))
        with ca2:
            st.metric("Đã kết sổ", str(n_archived))

        if st.button("🔄 Kết sổ tất cả phiếu App", disabled=(n_active == 0),
                     key="btn_archive_app"):
            try:
                supabase.table("phieu_chuyen_kho").update(
                    {"loai_phieu": ARCHIVED_MARKER}
                ).eq("loai_phieu", IN_APP_MARKER).execute()
                st.cache_data.clear()
                log_action("PHIEU_ARCHIVE", f"rows={n_active}")
                st.success(f"✓ Đã kết sổ {n_active} dòng phiếu App!")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi: {e}")

        if n_archived > 0:
            if st.button("↩ Khôi phục phiếu đã kết sổ (chỉ khi cần)",
                         key="btn_restore_archive"):
                try:
                    supabase.table("phieu_chuyen_kho").update(
                        {"loai_phieu": IN_APP_MARKER}
                    ).eq("loai_phieu", ARCHIVED_MARKER).execute()
                    st.cache_data.clear()
                    log_action("PHIEU_RESTORE", f"rows={n_archived}",
                              level="warning")
                    st.success(f"✓ Đã khôi phục {n_archived} dòng!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    with tab_nv:
        module_nhan_vien()

    with tab_kh:
        st.caption("Upload file **Danh sách khách hàng** từ KiotViet (.xlsx)")
        up_kh = st.file_uploader("Chọn file:", type=["xlsx","xls"], key="up_khach_hang")
        if up_kh:
            try:
                df_kh = pd.read_excel(up_kh)
                st.success(f"Đọc được {len(df_kh)} dòng")
                miss = [c for c in ["Mã khách hàng","Tên khách hàng","Điện thoại"] if c not in df_kh.columns]
                if miss:
                    st.error(f"Thiếu cột: {', '.join(miss)}")
                else:
                    st.info(f"{df_kh['Mã khách hàng'].nunique()} khách hàng")
                    with st.expander("Xem trước"):
                        st.dataframe(df_kh.head(), use_container_width=True, hide_index=True)
                    if st.button("Upload khách hàng", key="btn_up_kh", type="primary"):
                        with st.spinner("Đang xử lý..."):
                            def _cv(v):
                                if v is None: return None
                                try:
                                    if pd.isna(v): return None
                                except Exception: pass
                                if isinstance(v, float) and (v != v): return None
                                if isinstance(v, np.integer): return int(v)
                                if isinstance(v, np.floating): return None if np.isnan(v) else float(v)
                                if isinstance(v, pd.Timestamp): return v.strftime("%Y-%m-%d")
                                return str(v).strip() if str(v).strip() not in ("nan","None","") else None

                            def _to_int(v, default=0):
                                try:
                                    if v is None: return default
                                    if isinstance(v, float) and v != v: return default
                                    return int(float(v))
                                except: return default

                            rows_kh = []
                            for _, r in df_kh.iterrows():
                                sdt_raw = str(r.get("Điện thoại","") or "").strip().replace(" ","")
                                if not sdt_raw or sdt_raw == "nan": continue
                                rows_kh.append({
                                    "ma_kh":          _cv(r.get("Mã khách hàng")),
                                    "ten_kh":         _cv(r.get("Tên khách hàng")) or "Không tên",
                                    "sdt":            sdt_raw,
                                    "gioi_tinh":      _cv(r.get("Giới tính")),
                                    "ngay_sinh":      _cv(r.get("Ngày sinh")),
                                    "nhom_kh":        _cv(r.get("Nhóm khách hàng")),
                                    "chi_nhanh_tao":  _cv(r.get("Chi nhánh tạo")),
                                    "tong_ban":       _to_int(r.get("Tổng bán trừ trả hàng")),
                                    "diem_hien_tai":  _to_int(r.get("Điểm hiện tại")),
                                    "ngay_gd_cuoi":   _cv(r.get("Ngày giao dịch cuối")),
                                    "ghi_chu":        _cv(r.get("Ghi chú")),
                                    "trang_thai":     _to_int(r.get("Trạng thái"), default=1),
                                    "updated_at":     (datetime.now() + timedelta(hours=7)).isoformat(),
                                })

                            total, ok = len(rows_kh), 0
                            prog = st.progress(0, text="Đang upload...")
                            for i in range(0, total, 200):
                                batch = rows_kh[i:i+200]
                                try:
                                    # Upsert theo sdt — không trùng lặp
                                    supabase.table("khach_hang").upsert(
                                        batch, on_conflict="sdt"
                                    ).execute()
                                    ok += len(batch)
                                    prog.progress(min(ok/total, 1.0), text=f"{ok}/{total}...")
                                except Exception as e:
                                    st.error(f"Batch {i}: {e}")
                            prog.empty()
                            if ok == total:
                                log_action("UPLOAD_KHACH_HANG", f"rows={ok}")
                                st.success(f"✓ Upload {ok} khách hàng thành công!")
                                st.cache_data.clear()
            except Exception as e:
                st.error(f"Lỗi: {e}")


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
menu = ["📊 Tổng quan", "🧾 Hóa đơn", "📦 Hàng hóa", "🔄 Chuyển hàng", "🧮 Kiểm kê", "🔧 Sửa chữa", "👥 Khách hàng"]

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

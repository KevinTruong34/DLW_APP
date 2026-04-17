import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime, timedelta
import numpy as np
import bcrypt
import uuid

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

/* ── Radio nav ── */
[data-testid="stRadio"] > label:first-child { display: none; }
[data-testid="stRadio"] label { font-size: 0.88rem !important; }
[data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {
    font-size: 0.88rem !important;
    color: #1a1a2e !important;
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

/* ── Pull-to-refresh indicator ── */
.pull-refresh-zone {
    text-align: center;
    padding: 20px 0 10px 0;
    color: #aaa;
    font-size: 0.85rem;
    border-top: 1px dashed #e0e0e0;
    margin-top: 24px;
}

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
# SCROLL-TO-BOTTOM RELOAD
# ==========================================

def inject_scroll_refresh():
    """Khi user scroll gần đáy trang → reload."""
    components.html("""
    <div id="ws-sentinel"></div>
    <script>
    (function() {
      try {
        const parentWin = window.parent;
        if (parentWin.__ws_scroll_handler_installed) return;
        parentWin.__ws_scroll_handler_installed = true;

        let triggered = false;
        let lastY = 0;
        const threshold = 80;

        parentWin.addEventListener('scroll', function() {
          if (triggered) return;
          const sy = parentWin.scrollY || parentWin.pageYOffset;
          const ih = parentWin.innerHeight;
          const doc = parentWin.document.documentElement;
          const sh = Math.max(doc.scrollHeight, parentWin.document.body.scrollHeight);
          const atBottom = (sy + ih) >= (sh - threshold);
          const scrollingDown = sy > lastY;
          lastY = sy;
          if (atBottom && scrollingDown && sh > ih + 200) {
            triggered = true;
            parentWin.scrollTo({top: sh, behavior: 'smooth'});
            setTimeout(() => { parentWin.location.reload(); }, 250);
          }
        }, { passive: true });
      } catch(e) { /* cross-origin fallback silently */ }
    })();
    </script>
    """, height=0)


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
        "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat()
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
        if not res.data: return None, "Tài khoản không tồn tại hoặc đã bị khóa."
        u = res.data[0]
        if not verify_password(password, u["mat_khau"]): return None, "Mật khẩu không chính xác."
        u.pop("mat_khau", None)
        cn = supabase.table("nhan_vien_chi_nhanh") \
            .select("chi_nhanh(ten)").eq("nhan_vien_id", u["id"]).execute()
        u["chi_nhanh_list"] = [x["chi_nhanh"]["ten"] for x in cn.data] if cn.data else []
        return u, None
    except Exception as e:
        return None, f"Lỗi hệ thống: {e}"

def do_logout():
    token = st.query_params.get("token")
    if token: delete_session(token)
    st.session_state.clear(); st.query_params.clear()


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
    st.title("Đăng nhập")
    with st.form("login", clear_on_submit=False, border=False):
        u = st.text_input("Tài khoản:", placeholder="Nhập tên tài khoản")
        p = st.text_input("Mật khẩu:", type="password", placeholder="Nhập mật khẩu")
        submitted = st.form_submit_button("Đăng nhập", type="primary", use_container_width=True)
        if submitted:
            if not u or not p:
                st.error("Nhập đầy đủ.")
            else:
                with st.spinner("Đang xác thực..."):
                    user, err = do_login(u, p)
                if err:
                    st.error(err)
                else:
                    token = create_session_token(user["id"])
                    st.session_state["user"] = user
                    st.query_params["token"] = token
                    st.rerun()


# ==========================================
# BRANCH SELECTION — TẤT CẢ NÚT CÙNG MÀU
# ==========================================

def show_branch_selection():
    user     = get_user()
    branches = get_selectable_branches()

    if len(branches) == 1:
        st.session_state["active_chi_nhanh"] = branches[0]
        st.rerun(); return

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(f"""
            <div style="text-align:center;padding:32px 0 24px 0;">
                <div style="font-size:1.5rem;font-weight:700;color:#1a1a2e;margin-bottom:4px;">
                    Xin chào, {user.get('ho_ten','')}
                </div>
                <div style="font-size:0.9rem;color:#888;">
                    Chọn chi nhánh để bắt đầu ca làm việc
                </div>
            </div>
        """, unsafe_allow_html=True)

        # TẤT CẢ nút chi nhánh cùng màu secondary (không có nút đầu đỏ nữa)
        for i, branch in enumerate(branches):
            if st.button(
                branch,
                key=f"sel_{i}",
                use_container_width=True,
                type="secondary",
            ):
                st.session_state["active_chi_nhanh"] = branch
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Đăng xuất", use_container_width=True, key="logout_branch"):
            do_logout(); st.rerun()


# ==========================================
# SESSION RESTORE
# ==========================================

if "user" not in st.session_state:
    token = st.query_params.get("token")
    if token:
        user = restore_session(token)
        if user: st.session_state["user"] = user
        else: st.query_params.clear()

if "user" not in st.session_state:
    show_first_run() if is_first_run() else show_login()
    st.stop()

if "active_chi_nhanh" not in st.session_state:
    show_branch_selection(); st.stop()


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
        df["_ngay"] = pd.to_datetime(df["Thời gian"], format="%d/%m/%Y %H:%M", errors="coerce")
        if df["_ngay"].isna().all():
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
        tt  = str(r.get("trang_thai", "") or "")
        mh  = str(r.get("ma_hang", "") or "")
        sl  = int(r.get("so_luong_chuyen", 0) or 0)
        tu  = str(r.get("tu_chi_nhanh", "") or "")
        toi = str(r.get("toi_chi_nhanh", "") or "")

        if not mh or sl <= 0:
            continue

        # Rời kho nguồn khi phiếu đã được xác nhận chuyển
        if tt in ("Đang chuyển", "Đã nhận") and tu:
            deltas[(mh, tu)] = deltas.get((mh, tu), 0) - sl

        # Vào kho đích chỉ khi đã nhận
        if tt == "Đã nhận" and toi:
            deltas[(mh, toi)] = deltas.get((mh, toi), 0) + sl

    return deltas


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
            def _apply_delta(row):
                return deltas.get((str(row["Mã hàng"]), row["Chi nhánh"]), 0)
            df["_delta"] = df.apply(_apply_delta, axis=1)
            df["Tồn cuối kì"] = (df["Tồn cuối kì"] + df["_delta"]).astype(int)
            df = df.drop(columns=["_delta"])
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

        with st.expander(
            f"{code}  ·  {row.get('Thời gian','')}  ·  {row.get('Tên khách hàng','Khách lẻ')}",
            expanded=True
        ):
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

            c1,c2 = st.columns(2)
            c1.metric("Tổng tiền hàng", f"{row.get('Tổng tiền hàng',0):,.0f} đ")
            c2.metric("Khách đã trả",   f"{row.get('Khách đã trả',0):,.0f} đ")

            cols = ["Mã hàng","Tên hàng","Số lượng","Đơn giá","Thành tiền","Ghi chú hàng hóa"]
            dv = inv_df[[c for c in cols if c in inv_df.columns]].copy()
            for c in ["Đơn giá","Thành tiền"]:
                if c in dv.columns: dv[c] = dv[c].apply(lambda x: f"{x:,.0f}")
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

    try:
        active = get_active_branch()
        raw = load_hoa_don(branches_key=(active,))
        if raw.empty:
            st.info("Chưa có dữ liệu hóa đơn tại chi nhánh này."); return

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
        with t2:
            inv = st.text_input("Mã hóa đơn:", key="in_inv", placeholder="VD: 1007 hoặc HD011007")
            if inv:
                res = data[data["Mã hóa đơn"].str.upper().str.endswith(inv.strip().upper(),na=False)]
                if not res.empty: render_list(res)
                else: st.warning("Không tìm thấy mã hóa đơn.")
        with t3:
            ds = st.text_input("Ngày:", key="in_date", placeholder="VD: 14/04/2026")
            if ds:
                res = data[data["Thời gian"].astype(str).str.contains(ds.strip(),na=False)]
                if not res.empty:
                    st.caption(f"Tìm thấy {res['Mã hóa đơn'].nunique()} hóa đơn")
                    render_list(res)
                else: st.warning("Không có dữ liệu trong ngày này.")
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
                "Tên hàng": st.column_config.TextColumn("Tên hàng", width="large"),
                "Mã hàng":  st.column_config.TextColumn("Mã hàng",  width="small"),
                "Mã vạch":  st.column_config.TextColumn("Mã vạch",  width="small"),
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
    """Sinh mã phiếu CH + YYMMDD + 4 hex random (12 ký tự, giống KiotViet)."""
    today = datetime.now().strftime("%y%m%d")
    rand  = uuid.uuid4().hex[:4].upper()
    return f"CH{today}{rand}"


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


def _nhan_hang(ma_phieu: str):
    """Nhận hàng: trạng thái = Đã nhận, ngày nhận = now, SL nhận = SL chuyển."""
    # Update chung
    _update_trang_thai_phieu(ma_phieu, "Đã nhận", extra={
        "ngay_nhan": datetime.now().isoformat()
    })
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
    ghi_chu_chuyen = str(row_h.get("ghi_chu_chuyen","") or "").strip()
    ghi_chu_nhan   = str(row_h.get("ghi_chu_nhan","") or "").strip()
    for bad in ("nan", "None"):
        if nguoi_tao.lower() == bad.lower(): nguoi_tao = ""
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

        # Người tạo + ghi chú
        info_parts = []
        if nguoi_tao:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:8px;'>"
                f"👤 <b>Người gửi/tạo phiếu:</b> {nguoi_tao}</div>")
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

        # Hint về ảnh hưởng tồn kho
        if is_app_phieu:
            if tt == "Phiếu tạm":
                hint_msg = "📦 Phiếu App — <b>chưa ảnh hưởng</b> tồn kho (chờ xác nhận chuyển)"
                hint_bg  = "#fff8e0"
            elif tt == "Đang chuyển":
                hint_msg = f"📦 Phiếu App — đã <b>trừ {tsl:,}</b> tại kho nguồn, chưa vào kho đích"
                hint_bg  = "#d1ecf1"
            elif tt == "Đã nhận":
                hint_msg = f"📦 Phiếu App — đã chuyển <b>{tsl:,}</b> từ {tu_cn} → {toi_cn}"
                hint_bg  = "#f0faf4"
            elif tt == "Đã hủy":
                hint_msg = "📦 Phiếu App — đã hủy, tồn kho đã hoàn nguyên"
                hint_bg  = "#f5d5d5"
            else:
                hint_msg = None
            if hint_msg:
                st.markdown(
                    f"<div style='background:{hint_bg};border-radius:6px;"
                    f"padding:6px 10px;font-size:0.78rem;color:#444;margin:8px 0 4px;'>"
                    f"{hint_msg}</div>",
                    unsafe_allow_html=True
                )

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
            st.success(f"✓ Đã xác nhận chuyển hàng cho phiếu {ma_phieu}")
            st.rerun()

        elif action == "nhan":
            _nhan_hang(ma_phieu)
            st.cache_data.clear()
            st.success(f"✓ Đã nhận hàng cho phiếu {ma_phieu}")
            st.rerun()

        elif action == "huy":
            _update_trang_thai_phieu(ma_phieu, "Đã hủy")
            st.cache_data.clear()
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
        for idx, it in enumerate(st.session_state["ck_items"]):
            c_tn, c_sl, c_del = st.columns([4, 2, 1])
            with c_tn:
                st.markdown(
                    f"<div style='padding-top:10px;font-size:0.85rem;'>"
                    f"<b>{it['ten_hang']}</b><br>"
                    f"<span style='font-family:monospace;font-size:0.72rem;color:#777;'>{it['ma_hang']}</span>"
                    f" · <span style='color:#888;font-size:0.72rem;'>Tồn nguồn: {it.get('ton_src',0)}</span>"
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
                        type="primary", key="ck_submit"):
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


def _submit_phieu(tu_cn: str, toi_cn: str, nguoi_tao: str, ghi_chu: str,
                  items: list, editing_ma: str = None):
    """Insert phiếu mới hoặc update phiếu đang sửa."""
    try:
        with st.spinner("Đang xử lý..."):
            ma_phieu = editing_ma or _gen_ma_phieu()
            now_iso  = datetime.now().isoformat()

            tong_sl    = sum(it["so_luong"] for it in items)
            tong_mat   = len(items)
            tong_gtri  = sum(it["so_luong"] * it["gia_ban"] for it in items)

            # Khi sửa: giữ nguyên trạng thái "Phiếu tạm" (chỉ phiếu tạm mới sửa được)
            trang_thai = "Phiếu tạm"

            records = []
            for it in items:
                records.append({
                    "ma_phieu":         ma_phieu,
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
                })

            if editing_ma:
                _delete_phieu_rows(editing_ma)
                supabase.table("phieu_chuyen_kho").insert(records).execute()
                msg = f"💾 Đã cập nhật phiếu **{ma_phieu}**!"
            else:
                supabase.table("phieu_chuyen_kho").insert(records).execute()
                msg = f"✓ Tạo phiếu **{ma_phieu}** thành công!"

            # Reset
            st.session_state["ck_items"] = []
            st.session_state.pop("ck_editing", None)
            st.session_state.pop("ck_edit_meta", None)
            st.cache_data.clear()

            st.success(msg)
            if not editing_ma:
                st.balloons()
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

    tab_ds, tab_up, tab_del, tab_nv = st.tabs(["Doanh số","Upload","Xóa dữ liệu","Nhân viên"])

    with tab_ds:
        hien_thi_dashboard(show_filter=False)

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
                                records = df.where(pd.notnull(df),None).to_dict(orient="records")
                                for r in records:
                                    for k,v in r.items():
                                        if isinstance(v,np.integer): r[k]=int(v)
                                        elif isinstance(v,np.floating): r[k]=float(v)
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
                                records = df.where(pd.notnull(df),None).to_dict(orient="records")
                                for r in records:
                                    for k,v in r.items():
                                        if isinstance(v,np.integer): r[k]=int(v)
                                        elif isinstance(v,np.floating): r[k]=float(v)
                                total,ok = len(records),0
                                prog = st.progress(0,text="Đang upload...")
                                for i in range(0,total,500):
                                    try:
                                        supabase.table("hoa_don").insert(records[i:i+500]).execute()
                                        ok+=len(records[i:i+500])
                                        prog.progress(min(ok/total,1.0),text=f"{ok}/{total}...")
                                    except Exception as e: st.error(f"Batch {i}: {e}")
                                prog.empty()
                                if ok==total:
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
                        q.execute(); st.success("Xóa thành công!"); st.cache_data.clear()
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
                    st.success(f"✓ Đã khôi phục {n_archived} dòng!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    with tab_nv:
        module_nhan_vien()


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
menu = ["📊 Tổng quan", "🧾 Hóa đơn", "📦 Hàng hóa", "🔄 Chuyển hàng"]
if is_admin(): menu.append("⚙️ Quản trị")
page = st.radio("nav", menu, horizontal=True, label_visibility="collapsed")

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
                    # reset giỏ tạo phiếu khi đổi CN
                    st.session_state.pop("ck_items", None)
                    st.rerun()
            st.markdown("---")

        if st.button("🚪 Đăng xuất", use_container_width=True, key="btn_logout_pop"):
            do_logout(); st.rerun()

# strip icon từ page value để routing
page_clean = page.split(" ", 1)[1] if " " in page else page
st.markdown("<hr style='margin:4px 0 10px 0;'>", unsafe_allow_html=True)

if page_clean == "Tổng quan":     module_tong_quan()
elif page_clean == "Hóa đơn":     module_hoa_don()
elif page_clean == "Hàng hóa":    module_hang_hoa()
elif page_clean == "Chuyển hàng": module_chuyen_hang()
elif page_clean == "Quản trị":    module_quan_tri()

# ── SCROLL-TO-BOTTOM RELOAD ──
st.markdown(
    "<div class='pull-refresh-zone'>↓ Kéo xuống cuối để tải lại ↓</div>",
    unsafe_allow_html=True
)
inject_scroll_refresh()

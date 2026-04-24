import streamlit as st
import bcrypt
import uuid
from datetime import datetime, timedelta

from utils.config import ALL_BRANCHES, SESSION_EXPIRY_DAYS
from utils.db import supabase, _logger


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


# ── Session restore on app load ──
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

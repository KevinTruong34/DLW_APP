import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from datetime import datetime, timedelta
import numpy as np
import bcrypt
import uuid

# ==========================================
# PHIEN BAN: 12.1 — Fix branch selection
# ==========================================

st.set_page_config(page_title="Hệ thống Watch Store", layout="wide")

st.markdown("""
    <style>
    header {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    #stDecoration {display:none !important;}
    .stAppDeployButton {display:none !important;}
    [data-testid="stHeader"] {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}
    .block-container {padding-top: 1rem !important; padding-bottom: 0rem !important;}
    [data-testid="stMetricValue"] {font-size: 1.4rem !important;}
    [data-testid="stMetricLabel"] {font-size: 0.9rem !important; color: gray;}
    [data-testid="stElementToolbar"] {display: none !important;}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# SUPABASE INIT
# ==========================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error("Chưa cấu hình SUPABASE_URL và SUPABASE_KEY trong Streamlit Secrets!")
    st.stop()

ALL_BRANCHES = ["100 Lê Quý Đôn", "Coop Vũng Tàu", "GO BÀ RỊA"]
CN_ICON = {
    "100 Lê Quý Đôn": "🏪",
    "Coop Vũng Tàu":  "🛒",
    "GO BÀ RỊA":      "🏬",
}


# ==========================================
# AUTH HELPERS
# ==========================================

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def create_session_token(nhan_vien_id: int) -> str:
    token = str(uuid.uuid4())
    expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat()
    supabase.table("sessions").insert({
        "token": token,
        "nhan_vien_id": nhan_vien_id,
        "expires_at": expires_at
    }).execute()
    return token

def delete_session(token: str):
    supabase.table("sessions").delete().eq("token", token).execute()

def load_nhan_vien_by_id(nv_id: int):
    res = supabase.table("nhan_vien").select("*").eq("id", nv_id).eq("active", True).execute()
    if not res.data:
        return None
    user = res.data[0]
    user.pop("mat_khau", None)
    cn_res = supabase.table("nhan_vien_chi_nhanh") \
        .select("chi_nhanh_id, chi_nhanh(ten)") \
        .eq("nhan_vien_id", nv_id).execute()
    user["chi_nhanh_list"] = [x["chi_nhanh"]["ten"] for x in cn_res.data] if cn_res.data else []
    return user

def restore_session_from_token(token: str):
    try:
        res = supabase.table("sessions") \
            .select("nhan_vien_id, expires_at").eq("token", token).execute()
        if not res.data:
            return None
        sess = res.data[0]
        expires = datetime.fromisoformat(sess["expires_at"].replace("Z", "+00:00"))
        if expires.replace(tzinfo=None) < datetime.utcnow():
            delete_session(token)
            return None
        return load_nhan_vien_by_id(sess["nhan_vien_id"])
    except Exception:
        return None

def do_login(username: str, password: str):
    try:
        res = supabase.table("nhan_vien") \
            .select("*").eq("username", username).eq("active", True).execute()
        if not res.data:
            return None, "Tài khoản không tồn tại hoặc đã bị khóa."
        user = res.data[0]
        if not verify_password(password, user["mat_khau"]):
            return None, "Mật khẩu không chính xác."
        user.pop("mat_khau", None)
        cn_res = supabase.table("nhan_vien_chi_nhanh") \
            .select("chi_nhanh_id, chi_nhanh(ten)") \
            .eq("nhan_vien_id", user["id"]).execute()
        user["chi_nhanh_list"] = [x["chi_nhanh"]["ten"] for x in cn_res.data] if cn_res.data else []
        return user, None
    except Exception as e:
        return None, f"Lỗi hệ thống: {e}"

def do_logout():
    token = st.query_params.get("token")
    if token:
        delete_session(token)
    st.session_state.clear()
    st.query_params.clear()


# ==========================================
# SESSION HELPERS
# ==========================================

def get_user():
    return st.session_state.get("user")

def is_admin():
    u = get_user()
    return u and u.get("role") == "admin"

def is_ke_toan_or_admin():
    u = get_user()
    return u and u.get("role") in ("admin", "ke_toan")

def get_active_branch() -> str:
    """Chi nhánh đang làm việc — luôn là 1 chi nhánh cụ thể."""
    return st.session_state.get("active_chi_nhanh", "")

def get_active_branch_as_filter() -> tuple:
    """Tuple dùng cho cache key — chỉ active branch."""
    b = get_active_branch()
    return (b,) if b else ()

def get_user_accessible_branches() -> list:
    """Toàn bộ chi nhánh user được phép truy cập (dùng cho báo cáo)."""
    u = get_user()
    if not u:
        return []
    if u.get("role") == "admin":
        return ALL_BRANCHES
    return u.get("chi_nhanh_list", [])

def get_selectable_branches() -> list:
    """Chi nhánh user có thể chọn làm việc — KHÔNG có 'Tất cả'."""
    return get_user_accessible_branches()


# ==========================================
# FIRST RUN SETUP
# ==========================================

def is_first_run() -> bool:
    try:
        res = supabase.table("nhan_vien").select("id", count="exact").execute()
        return (res.count or 0) == 0
    except Exception:
        return False

def show_first_run():
    st.title("🛠️ Khởi tạo hệ thống lần đầu")
    st.info("Chưa có tài khoản nào. Tạo tài khoản **Admin** để bắt đầu.")
    with st.form("form_setup"):
        username = st.text_input("Username:")
        ho_ten   = st.text_input("Họ tên:")
        pwd      = st.text_input("Mật khẩu:", type="password")
        pwd2     = st.text_input("Xác nhận mật khẩu:", type="password")
        if st.form_submit_button("🚀 Tạo tài khoản Admin", type="primary"):
            if not all([username, ho_ten, pwd, pwd2]):
                st.error("Điền đầy đủ thông tin.")
            elif pwd != pwd2:
                st.error("Mật khẩu không khớp.")
            elif len(pwd) < 6:
                st.error("Tối thiểu 6 ký tự.")
            else:
                try:
                    supabase.table("nhan_vien").insert({
                        "username": username, "ho_ten": ho_ten,
                        "mat_khau": hash_password(pwd),
                        "role": "admin", "active": True,
                    }).execute()
                    st.success(f"✅ Tạo tài khoản **{ho_ten}** thành công!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")


# ==========================================
# LOGIN PAGE
# ==========================================

def show_login():
    st.title("🔐 Đăng nhập hệ thống")
    with st.form("login_form"):
        username = st.text_input("Tài khoản:")
        password = st.text_input("Mật khẩu:", type="password")
        if st.form_submit_button("Đăng nhập", type="primary", use_container_width=True):
            if not username or not password:
                st.error("Nhập đầy đủ tài khoản và mật khẩu.")
            else:
                with st.spinner("Đang xác thực..."):
                    user, err = do_login(username, password)
                if err:
                    st.error(err)
                else:
                    token = create_session_token(user["id"])
                    st.session_state["user"] = user
                    st.query_params["token"] = token
                    st.rerun()


# ==========================================
# BRANCH SELECTION SCREEN
# ==========================================

def show_branch_selection():
    user     = get_user()
    branches = get_selectable_branches()

    # Chỉ 1 chi nhánh → tự động vào luôn, không cần chọn
    if len(branches) == 1:
        st.session_state["active_chi_nhanh"] = branches[0]
        st.rerun()
        return

    st.markdown(f"## 👋 Xin chào, **{user.get('ho_ten', '')}**!")
    st.markdown("### Bạn đang làm việc tại chi nhánh nào?")
    st.caption("Chọn chi nhánh để bắt đầu ca làm việc. Có thể đổi bất cứ lúc nào.")
    st.markdown("<br>", unsafe_allow_html=True)

    cols = st.columns(len(branches))
    for i, branch in enumerate(branches):
        icon = CN_ICON.get(branch, "🏪")
        with cols[i]:
            st.markdown(f"""
                <div style="
                    border: 2px solid #e0e0e0; border-radius: 16px;
                    padding: 28px 16px 12px 16px; text-align: center;
                    margin-bottom: 10px; background: #fafafa;
                ">
                    <div style="font-size: 3rem;">{icon}</div>
                    <div style="font-size: 1rem; font-weight: 600;
                         margin-top: 10px; color: #333; line-height: 1.4;">
                        {branch}
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Chọn chi nhánh này", key=f"sel_cn_{i}",
                         use_container_width=True, type="primary"):
                st.session_state["active_chi_nhanh"] = branch
                st.rerun()

    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("🚪 Đăng xuất"):
        do_logout()
        st.rerun()


# ==========================================
# SESSION RESTORE
# ==========================================

if "user" not in st.session_state:
    token = st.query_params.get("token")
    if token:
        user = restore_session_from_token(token)
        if user:
            st.session_state["user"] = user
        else:
            st.query_params.clear()

# ==========================================
# ROUTING: FIRST RUN → LOGIN → BRANCH → APP
# ==========================================

if "user" not in st.session_state:
    if is_first_run():
        show_first_run()
    else:
        show_login()
    st.stop()

if "active_chi_nhanh" not in st.session_state:
    show_branch_selection()
    st.stop()


# ==========================================
# DATA LOADING
# ==========================================

@st.cache_data(ttl=300)
def load_hoa_don(branches_key: tuple):
    all_rows = []
    batch, offset = 1000, 0
    while True:
        q = supabase.table("hoa_don").select("*").in_("Chi nhánh", list(branches_key))
        res = q.range(offset, offset + batch - 1).execute()
        rows = res.data
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < batch:
            break
        offset += batch
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    tong = len(df)
    df = df.drop_duplicates()
    st.session_state["so_dong_trung"] = tong - len(df)
    for col in ["Tổng tiền hàng", "Khách cần trả", "Khách đã trả", "Đơn giá", "Thành tiền"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "Thời gian" in df.columns:
        df["_ngay"] = pd.to_datetime(df["Thời gian"], format="%d/%m/%Y %H:%M", errors="coerce")
        if df["_ngay"].isna().all():
            df["_ngay"] = pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")
        df["_date"] = df["_ngay"].dt.date
    return df

@st.cache_data(ttl=300)
def load_the_kho(branches_key: tuple):
    all_rows = []
    batch, offset = 1000, 0
    while True:
        q = supabase.table("the_kho").select("*").in_("Chi nhánh", list(branches_key))
        res = q.range(offset, offset + batch - 1).execute()
        rows = res.data
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < batch:
            break
        offset += batch
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    for col in ["Tồn đầu kì", "Giá trị đầu kì", "Nhập NCC", "Giá trị nhập NCC",
                "Xuất bán", "Giá trị xuất bán", "Tồn cuối kì", "Giá trị cuối kì"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


# ==========================================
# MODULE 0: TỔNG QUAN
# ==========================================

def module_tong_quan():
    user   = get_user()
    active = get_active_branch()
    icon   = CN_ICON.get(active, "🏪")
    role_label = {
        "admin":    "👑 Admin",
        "ke_toan":  "📊 Kế toán",
        "nhan_vien":"👤 Nhân viên"
    }.get(user.get("role"), "")
    st.markdown(f"### 👋 Xin chào, **{user.get('ho_ten', '')}**!")
    st.caption(f"{role_label}   |   {icon} Đang tại: **{active}**")
    st.markdown("---")
    if is_ke_toan_or_admin():
        hien_thi_dashboard()
    else:
        st.info("🚧 Trang tổng quan nhân viên đang phát triển.")


# ==========================================
# DASHBOARD DOANH SỐ
# ==========================================

def hien_thi_dashboard():
    """
    Dashboard có 2 lớp filter:
    - nhan_vien: chỉ thấy active branch, không có filter
    - ke_toan / admin: có thêm bộ lọc chi nhánh bên trong báo cáo
      (tách biệt với active_chi_nhanh — đây là filter báo cáo, không phải context làm việc)
    """
    accessible = get_user_accessible_branches()

    # ── Bộ lọc chi nhánh báo cáo (chỉ ke_toan/admin mới thấy) ──
    if is_ke_toan_or_admin() and len(accessible) > 1:
        st.caption("📊 Báo cáo — bạn có thể xem nhiều chi nhánh cùng lúc")
        report_branches = st.multiselect(
            "Chi nhánh trong báo cáo:",
            options=accessible,
            default=accessible,
            key="dashboard_cn_filter",
            label_visibility="collapsed"
        )
        if not report_branches:
            st.warning("Chọn ít nhất một chi nhánh.")
            return
    else:
        # nhan_vien hoặc chỉ có 1 chi nhánh → chỉ thấy active branch
        report_branches = [get_active_branch()]

    try:
        raw = load_hoa_don(branches_key=tuple(report_branches))
        if raw.empty or "_date" not in raw.columns:
            st.info("💡 Chưa có dữ liệu hóa đơn.")
            return

        today         = datetime.now().date()
        yesterday     = today - timedelta(days=1)
        first_month   = today.replace(day=1)
        first_last    = (first_month - timedelta(days=1)).replace(day=1)
        last_last     = first_month - timedelta(days=1)

        col_f, _ = st.columns([2, 3])
        with col_f:
            ky = st.selectbox("Kỳ xem:",
                ["Hôm nay", "Hôm qua", "7 ngày qua", "Tháng này", "Tháng trước"],
                index=3, label_visibility="collapsed")

        if ky == "Hôm nay":
            df, dt, cf, ct = today, today, yesterday, yesterday
            label = "so với hôm qua"
        elif ky == "Hôm qua":
            df, dt = yesterday, yesterday
            cf, ct = yesterday - timedelta(1), yesterday - timedelta(1)
            label = "so với hôm kia"
        elif ky == "7 ngày qua":
            df, dt = today - timedelta(6), today
            cf, ct = today - timedelta(13), today - timedelta(7)
            label = "so với 7 ngày trước"
        elif ky == "Tháng này":
            df, dt = first_month, today
            cf = first_last
            try:    ct = first_last.replace(day=today.day)
            except: ct = last_last
            label = "so với cùng kỳ tháng trước"
        else:
            df, dt = first_last, last_last
            m2f = (first_last - timedelta(1)).replace(day=1)
            cf, ct = m2f, first_last - timedelta(1)
            label = "so với tháng trước nữa"

        ht    = raw[raw["Trạng thái"] == "Hoàn thành"].copy()
        d_ky  = ht[(ht["_date"] >= df)  & (ht["_date"] <= dt)]
        d_ss  = ht[(ht["_date"] >= cf)  & (ht["_date"] <= ct)]
        d_td  = ht[ht["_date"] == today]
        d_ye  = ht[ht["_date"] == yesterday]

        def tinh(d):
            if d.empty: return 0, 0
            u = d.drop_duplicates(subset=["Mã hóa đơn"], keep="first")
            return u["Khách đã trả"].sum(), u["Mã hóa đơn"].nunique()

        def pct(a, b):
            return ((a - b) / b * 100) if b else None

        dt_td, hd_td = tinh(d_td)
        dt_ye, _     = tinh(d_ye)
        dt_ky, hd_ky = tinh(d_ky)
        dt_ss, _     = tinh(d_ss)
        p_ye = pct(dt_td, dt_ye)
        p_ss = pct(dt_ky, dt_ss)

        st.markdown("#### Kết quả bán hàng hôm nay")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("💰 Doanh thu hôm nay", f"{dt_td:,.0f}")
            st.caption(f"{hd_td} hóa đơn")
        with m2:
            st.metric("🔄 Trả hàng", "0")
        with m3:
            st.metric("So hôm qua",
                f"{'↑' if (p_ye or 0) >= 0 else '↓'} {abs(p_ye):.1f}%"
                if p_ye is not None else "—")
        with m4:
            st.metric(label.capitalize(),
                f"{'↑' if (p_ss or 0) >= 0 else '↓'} {abs(p_ss):.1f}%"
                if p_ss is not None else "—")

        st.markdown(f"**Doanh thu thuần kỳ này: {dt_ky:,.0f} đ** ({hd_ky} hóa đơn)")

        if not d_ky.empty:
            base  = d_ky.drop_duplicates(subset=["Mã hóa đơn"], keep="first")
            chart = base.groupby(["_date", "Chi nhánh"])["Khách đã trả"].sum().reset_index()
            chart.columns = ["Ngày", "Chi nhánh", "Doanh thu"]
            pivot = chart.pivot_table(
                index="Ngày", columns="Chi nhánh",
                values="Doanh thu", fill_value=0
            ).sort_index()

            cmap = {
                "100 Lê Quý Đôn": "#2E86DE",
                "Coop Vũng Tàu":   "#27AE60",
                "GO BÀ RỊA":       "#F39C12",
            }
            fallback = ["#2E86DE", "#27AE60", "#F39C12", "#E74C3C", "#9B59B6"]
            fig = go.Figure()
            for i, cn in enumerate(pivot.columns):
                fig.add_trace(go.Bar(
                    x=[d.strftime("%d") for d in pivot.index],
                    y=pivot[cn], name=cn,
                    marker_color=cmap.get(cn, fallback[i % len(fallback)]),
                    hovertemplate=f"{cn}<br>Ngày %{{x}}<br>%{{y:,.0f}} đ<extra></extra>",
                ))
            fig.update_layout(
                barmode="stack", height=400,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=-0.25,
                            xanchor="center", x=0.5),
                yaxis=dict(tickformat=",.0f", gridcolor="#eee"),
                xaxis=dict(title=None, dtick=1),
                plot_bgcolor="white", font=dict(size=12), dragmode=False,
            )
            mx = pivot.sum(axis=1).max() if not pivot.empty else 0
            if mx >= 1_000_000:
                step = max(6_000_000, int(mx / 8) // 1_000_000 * 1_000_000)
                tvs  = list(range(0, int(mx + step), step))
                fig.update_layout(yaxis=dict(
                    tickvals=tvs,
                    ticktext=[f"{int(v / 1_000_000)} tr" for v in tvs],
                    gridcolor="#eee"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Không có dữ liệu trong kỳ này.")

    except Exception as e:
        st.error(f"Lỗi dashboard: {e}")


# ==========================================
# MODULE 1: HÓA ĐƠN
# ==========================================

def module_hoa_don():
    def show_invoice(inv_df, code):
        row    = inv_df.iloc[0]
        status = row.get("Trạng thái", "N/A")
        bg     = "#28a745" if status == "Hoàn thành" else "#dc3545"
        header = (f"🧾 **{code}** — {row.get('Thời gian', '')} | "
                  f"**{row.get('Tên khách hàng', 'Khách lẻ')}** "
                  f"({row.get('Điện thoại', 'N/A')})")
        with st.expander(header, expanded=True):
            st.markdown(
                f"""<div style="display:flex;justify-content:flex-end;margin-top:-40px;">
                <span style="background:{bg};color:white;padding:4px 15px;
                border-radius:20px;font-weight:bold;font-size:.85rem;">{status}</span>
                </div>""", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.metric("Tổng tiền hàng", f"{row.get('Tổng tiền hàng', 0):,.0f} đ")
            c2.metric("Thực tế trả",    f"{row.get('Khách đã trả', 0):,.0f} đ")
            cols = ["Mã hàng", "Tên hàng", "Số lượng", "Đơn giá", "Thành tiền", "Ghi chú hàng hóa"]
            dv = inv_df[[c for c in cols if c in inv_df.columns]].copy()
            for c in ["Đơn giá", "Thành tiền"]:
                if c in dv.columns:
                    dv[c] = dv[c].apply(lambda x: f"{x:,.0f} đ")
            with st.expander("📋 Chi tiết hàng hóa", expanded=False):
                st.dataframe(dv, use_container_width=True, hide_index=True)

    def show_list(res):
        active   = res[res["Trạng thái"] != "Đã hủy"]
        canceled = res[res["Trạng thái"] == "Đã hủy"]
        for code in active["Mã hóa đơn"].unique():
            show_invoice(active[active["Mã hóa đơn"] == code], code)
        if not canceled.empty:
            n = canceled["Mã hóa đơn"].nunique()
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander(f"🗑️ Hóa đơn Đã hủy ({n})", expanded=False):
                for code in canceled["Mã hóa đơn"].unique():
                    show_invoice(canceled[canceled["Mã hóa đơn"] == code], code)

    try:
        # Module hóa đơn luôn filter theo active branch
        active = get_active_branch()
        raw = load_hoa_don(branches_key=(active,))
        if raw.empty:
            st.info("💡 Chưa có dữ liệu hóa đơn tại chi nhánh này.")
            return

        if st.session_state.get("so_dong_trung", 0) > 0:
            st.warning(f"⚠️ Phát hiện {st.session_state['so_dong_trung']} dòng trùng đã lọc.")

        data = raw.copy()
        data["SĐT_Search"] = data["Điện thoại"].fillna("").str.replace(r"\D+", "", regex=True)

        t1, t2, t3 = st.tabs(["📞 Số điện thoại", "🧾 Mã Hóa Đơn", "📅 Ngày tháng"])
        with t1:
            phone = st.text_input("Nhập số điện thoại:", key="in_phone")
            if phone:
                res = data[data["SĐT_Search"].str.contains(phone.replace(" ", ""), na=False)]
                if not res.empty:
                    st.info(f"Khách hàng: **{res.iloc[0].get('Tên khách hàng', 'Khách lẻ')}**")
                    show_list(res)
                else:
                    st.warning("Không tìm thấy số điện thoại.")
        with t2:
            inv = st.text_input("Nhập mã (Ví dụ: 1007 hoặc HD011007):", key="in_inv")
            if inv:
                res = data[data["Mã hóa đơn"].str.upper().str.endswith(inv.strip().upper(), na=False)]
                if not res.empty: show_list(res)
                else: st.warning("Không tìm thấy mã hóa đơn.")
        with t3:
            ds = st.text_input("Nhập ngày/tháng (Ví dụ: 14/04/2026):", key="in_date")
            if ds:
                res = data[data["Thời gian"].astype(str).str.contains(ds.strip(), na=False)]
                if not res.empty:
                    st.success(f"Tìm thấy {res['Mã hóa đơn'].nunique()} hóa đơn.")
                    show_list(res)
                else:
                    st.warning("Không có dữ liệu trong ngày này.")
    except Exception as e:
        st.error(f"Lỗi tải Hóa đơn: {e}")


# ==========================================
# MODULE 2: THẺ KHO
# ==========================================

def module_the_kho():
    try:
        active = get_active_branch()
        data = load_the_kho(branches_key=(active,))
        if data.empty:
            st.info("💡 Chưa có dữ liệu thẻ kho tại chi nhánh này.")
            return
        ma = st.text_input("🔍 Nhập Mã hàng hóa (Ví dụ: CASIO-01):").strip().upper()
        if ma:
            res = data[data["Mã hàng"].str.upper().str.contains(ma, na=False)]
            if not res.empty:
                st.success(f"Tìm thấy **{len(res)}** dòng — **{res.iloc[0].get('Tên hàng', ma)}**")
                cols = ["Chi nhánh", "Mã hàng", "Tên hàng", "Tồn đầu kì", "Nhập NCC",
                        "Xuất bán", "Tồn cuối kì", "Giá trị cuối kì"]
                dv = res[[c for c in cols if c in res.columns]].copy()
                for c in ["Giá trị cuối kì", "Giá trị đầu kì"]:
                    if c in dv.columns:
                        dv[c] = dv[c].apply(lambda x: f"{x:,.0f} đ")
                st.dataframe(dv, use_container_width=True, hide_index=True)
            else:
                st.warning("Không tìm thấy mã hàng này.")
    except Exception as e:
        st.error(f"Lỗi tải Thẻ kho: {e}")


# ==========================================
# MODULE QUẢN LÝ NHÂN VIÊN
# ==========================================

def module_nhan_vien():
    st.markdown("### 👥 Quản lý nhân viên")
    try:
        cn_res = supabase.table("chi_nhanh").select("*").eq("active", True).execute()
        cn_map = {cn["ten"]: cn["id"] for cn in cn_res.data} if cn_res.data else {}
    except Exception as e:
        st.error(f"Lỗi tải chi nhánh: {e}"); return

    tab_add, tab_list = st.tabs(["➕ Thêm nhân viên", "📋 Danh sách"])

    with tab_add:
        with st.form("form_them_nv", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                nu  = st.text_input("Username:")
                nn  = st.text_input("Họ tên:")
                nr  = st.selectbox("Role:", ["nhan_vien", "ke_toan", "admin"])
            with c2:
                np1 = st.text_input("Mật khẩu:", type="password")
                np2 = st.text_input("Xác nhận MK:", type="password")
                ncs = st.multiselect("Chi nhánh:", list(cn_map.keys()))
            if st.form_submit_button("➕ Tạo tài khoản", type="primary"):
                if not all([nu, nn, np1, np2]):
                    st.error("Điền đầy đủ thông tin.")
                elif np1 != np2:
                    st.error("Mật khẩu không khớp.")
                elif len(np1) < 6:
                    st.error("Tối thiểu 6 ký tự.")
                elif not ncs and nr != "admin":
                    st.error("Chọn ít nhất một chi nhánh.")
                else:
                    try:
                        res = supabase.table("nhan_vien").insert({
                            "username": nu, "ho_ten": nn,
                            "mat_khau": hash_password(np1),
                            "role": nr, "active": True,
                        }).execute()
                        nv_id = res.data[0]["id"]
                        for cn in ncs:
                            supabase.table("nhan_vien_chi_nhanh").insert({
                                "nhan_vien_id": nv_id,
                                "chi_nhanh_id": cn_map[cn]
                            }).execute()
                        st.success(f"✅ Tạo tài khoản **{nn}** thành công!")
                    except Exception as e:
                        st.error(f"Lỗi: {e}")

    with tab_list:
        try:
            nv_list = supabase.table("nhan_vien").select("*").order("id").execute().data or []
            current = get_user()
            for nv in nv_list:
                cn2      = supabase.table("nhan_vien_chi_nhanh") \
                    .select("chi_nhanh(ten)").eq("nhan_vien_id", nv["id"]).execute()
                cn_names = [x["chi_nhanh"]["ten"] for x in cn2.data] if cn2.data else []
                ia       = "🟢" if nv["active"] else "🔴"
                ir       = {"admin": "👑", "ke_toan": "📊", "nhan_vien": "👤"}.get(nv["role"], "👤")
                is_self  = (nv["id"] == current.get("id"))
                with st.expander(
                    f"{ia} {ir} **{nv['ho_ten']}** — `{nv['username']}`"
                    + (" *(bạn)*" if is_self else "")
                ):
                    ci, cp, ca = st.columns([2, 2, 1])
                    with ci:
                        st.caption(f"Role: **{nv['role']}**")
                        st.caption(f"Chi nhánh: {', '.join(cn_names) if cn_names else '—'}")
                        nr2 = st.selectbox("Đổi role:", ["nhan_vien", "ke_toan", "admin"],
                            index=["nhan_vien", "ke_toan", "admin"].index(nv["role"]),
                            key=f"role_{nv['id']}")
                        if st.button("💾 Lưu role", key=f"sr_{nv['id']}"):
                            supabase.table("nhan_vien").update({"role": nr2}).eq("id", nv["id"]).execute()
                            st.success("Đã cập nhật!"); st.rerun()
                    with cp:
                        np_ = st.text_input("Mật khẩu mới:", type="password", key=f"np_{nv['id']}")
                        if st.button("🔑 Đổi MK", key=f"sp_{nv['id']}"):
                            if np_ and len(np_) >= 6:
                                supabase.table("nhan_vien").update(
                                    {"mat_khau": hash_password(np_)}).eq("id", nv["id"]).execute()
                                st.success("Đã đổi mật khẩu!")
                            else:
                                st.warning("Tối thiểu 6 ký tự.")
                    with ca:
                        if not is_self:
                            lbl = "🔒 Khóa" if nv["active"] else "🔓 Mở"
                            if st.button(lbl, key=f"tog_{nv['id']}"):
                                supabase.table("nhan_vien").update(
                                    {"active": not nv["active"]}).eq("id", nv["id"]).execute()
                                st.rerun()
                        else:
                            st.caption("*(tài khoản bạn)*")
        except Exception as e:
            st.error(f"Lỗi: {e}")


# ==========================================
# MODULE 3: QUẢN TRỊ
# ==========================================

def module_quan_tri():
    if not is_admin():
        st.error("⛔ Bạn không có quyền truy cập.")
        return

    tab_ds, tab_up, tab_del, tab_nv = st.tabs([
        "📊 Doanh số", "📤 Upload", "🗑️ Xóa dữ liệu", "👥 Nhân viên"
    ])

    with tab_ds:
        hien_thi_dashboard()

    with tab_up:
        s1, s2 = st.tabs(["📦 Thẻ kho", "🧾 Hóa đơn"])
        with s1:
            st.markdown("**Hướng dẫn:** File **Xuất nhập tồn chi tiết** từ KiotViet (`.xlsx`).")
            up = st.file_uploader("Chọn file:", type=["xlsx", "xls"], key="up_kho")
            if up:
                try:
                    df   = pd.read_excel(up)
                    st.success(f"Đọc được **{len(df)}** dòng")
                    miss = [c for c in ["Mã hàng", "Tên hàng", "Chi nhánh", "Tồn cuối kì"]
                            if c not in df.columns]
                    if miss:
                        st.error(f"Thiếu cột: {', '.join(miss)}")
                    else:
                        st.info(f"Chi nhánh: {', '.join(df['Chi nhánh'].unique())}")
                        with st.expander("👁️ Xem trước"):
                            st.dataframe(df.head(), use_container_width=True, hide_index=True)
                        if st.button("🚀 Upload Thẻ kho", key="btn_up_kho", type="primary"):
                            with st.spinner("Đang xử lý..."):
                                tc = ["Nhóm hàng", "Mã hàng", "Mã vạch", "Tên hàng", "Thương hiệu", "Chi nhánh"]
                                for col in tc:
                                    if col in df.columns:
                                        df[col] = df[col].astype(str) \
                                            .str.replace(",", " ", regex=False) \
                                            .str.replace("\n", " ", regex=False).str.strip()
                                        df.loc[df[col] == "nan", col] = None
                                for col in [c for c in df.columns if c not in tc]:
                                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
                                records = df.where(pd.notnull(df), None).to_dict(orient="records")
                                for r in records:
                                    for k, v in r.items():
                                        if isinstance(v, np.integer):  r[k] = int(v)
                                        elif isinstance(v, np.floating): r[k] = float(v)
                                total, ok = len(records), 0
                                prog = st.progress(0, text="Đang upload...")
                                for i in range(0, total, 500):
                                    try:
                                        supabase.table("the_kho").insert(records[i:i+500]).execute()
                                        ok += len(records[i:i+500])
                                        prog.progress(min(ok / total, 1.0), text=f"{ok}/{total}...")
                                    except Exception as e:
                                        st.error(f"Batch {i}: {e}")
                                prog.empty()
                                if ok == total:
                                    st.success(f"✅ Upload {ok} dòng thành công!")
                                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

        with s2:
            st.markdown("**Hướng dẫn:** File **Danh sách hóa đơn** từ KiotViet (`.xlsx`).")
            up = st.file_uploader("Chọn file:", type=["xlsx", "xls"], key="up_hd")
            if up:
                try:
                    df   = pd.read_excel(up)
                    st.success(f"Đọc được **{len(df)}** dòng")
                    miss = [c for c in ["Mã hóa đơn", "Thời gian", "Chi nhánh"]
                            if c not in df.columns]
                    if miss:
                        st.error(f"Thiếu cột: {', '.join(miss)}")
                    else:
                        st.info(f"{df['Mã hóa đơn'].nunique()} hóa đơn — "
                                f"{', '.join(df['Chi nhánh'].unique())}")
                        with st.expander("👁️ Xem trước"):
                            st.dataframe(df.head(), use_container_width=True, hide_index=True)
                        if st.button("🚀 Upload Hóa đơn", key="btn_up_hd", type="primary"):
                            with st.spinner("Đang xử lý..."):
                                for col in df.columns:
                                    if df[col].dtype == "object":
                                        df[col] = df[col].astype(str) \
                                            .str.replace("\n", " ", regex=False).str.strip()
                                        df.loc[df[col] == "nan", col] = None
                                for col in ["Tổng tiền hàng", "Khách cần trả", "Khách đã trả",
                                            "Đơn giá", "Thành tiền"]:
                                    if col in df.columns:
                                        df[col] = pd.to_numeric(
                                            df[col], errors="coerce").fillna(0).astype(int)
                                records = df.where(pd.notnull(df), None).to_dict(orient="records")
                                for r in records:
                                    for k, v in r.items():
                                        if isinstance(v, np.integer):  r[k] = int(v)
                                        elif isinstance(v, np.floating): r[k] = float(v)
                                total, ok = len(records), 0
                                prog = st.progress(0, text="Đang upload...")
                                for i in range(0, total, 500):
                                    try:
                                        supabase.table("hoa_don").insert(records[i:i+500]).execute()
                                        ok += len(records[i:i+500])
                                        prog.progress(min(ok / total, 1.0), text=f"{ok}/{total}...")
                                    except Exception as e:
                                        st.error(f"Batch {i}: {e}")
                                prog.empty()
                                if ok == total:
                                    st.success(f"✅ Upload {ok} dòng thành công!")
                                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    with tab_del:
        st.caption("Xóa dữ liệu cũ trước khi upload lại.")
        c1, c2 = st.columns(2)
        with c1:
            bang = st.selectbox("Bảng:", ["the_kho", "hoa_don"], key="sel_del_table")
        with c2:
            try:
                tmp = load_the_kho(branches_key=tuple(ALL_BRANCHES)) \
                      if bang == "the_kho" \
                      else load_hoa_don(branches_key=tuple(ALL_BRANCHES))
                ds  = ["-- Tất cả --"] + sorted(tmp["Chi nhánh"].dropna().unique().tolist()) \
                      if not tmp.empty else ["-- Tất cả --"]
            except Exception:
                ds = ["-- Tất cả --"]
            cn_x = st.selectbox("Chi nhánh:", ds, key="sel_del_branch")
        try:
            q   = supabase.table(bang).select("id", count="exact")
            if cn_x != "-- Tất cả --": q = q.eq("Chi nhánh", cn_x)
            cnt = q.execute().count or 0
        except Exception:
            cnt = "?"
        pv = f"chi nhánh **{cn_x}**" if cn_x != "-- Tất cả --" else "**TOÀN BỘ**"
        st.warning(f"Sẽ xóa **{cnt}** dòng từ `{bang}` — {pv}")
        confirm = st.text_input("Gõ **XOA** để xác nhận:", key="confirm_del")
        if st.button("🗑️ Thực hiện xóa", key="btn_del"):
            if confirm != "XOA":
                st.error("Gõ đúng XOA để xác nhận.")
            else:
                with st.spinner("Đang xóa..."):
                    try:
                        q = supabase.table(bang).delete()
                        q = q.eq("Chi nhánh", cn_x) \
                            if cn_x != "-- Tất cả --" \
                            else q.neq("id", -999999)
                        q.execute()
                        st.success("✅ Xóa thành công!")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")

    with tab_nv:
        module_nhan_vien()


# ==========================================
# NAVIGATION HEADER
# ==========================================

user       = get_user()
active_cn  = get_active_branch()
icon_cn    = CN_ICON.get(active_cn, "🏪")
selectable = get_selectable_branches()

col_menu, col_cn, col_btns = st.columns([4, 2, 1])

with col_menu:
    menu = ["📊 Tổng quan", "🧾 Hóa đơn", "📦 Thẻ kho"]
    if is_admin():
        menu.append("⚙️ Quản trị")
    chuc_nang = st.radio("Phân hệ:", menu, horizontal=True, label_visibility="collapsed")

with col_cn:
    st.markdown(
        f"<div style='padding-top:6px;font-size:0.95rem;'>"
        f"{icon_cn} <b>{active_cn}</b></div>",
        unsafe_allow_html=True
    )
    # Nút đổi chi nhánh — chỉ hiện nếu user có nhiều hơn 1 lựa chọn
    if len(selectable) > 1:
        if st.button("🔀 Đổi chi nhánh", use_container_width=True):
            del st.session_state["active_chi_nhanh"]
            st.rerun()

with col_btns:
    if st.button("🔄", use_container_width=True, help="Reload dữ liệu"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🚪", use_container_width=True, help="Đăng xuất"):
        do_logout()
        st.rerun()

st.markdown("<hr style='margin-top:0;margin-bottom:20px;'>", unsafe_allow_html=True)

if chuc_nang == "📊 Tổng quan":
    module_tong_quan()
elif chuc_nang == "🧾 Hóa đơn":
    module_hoa_don()
elif chuc_nang == "📦 Thẻ kho":
    module_the_kho()
elif chuc_nang == "⚙️ Quản trị":
    module_quan_tri()

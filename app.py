import streamlit as st
import pandas as pd
from supabase import create_client, Client

# ==========================================
# PHIÊN BẢN: 7.0.0
# ==========================================

# 1. CẤU HÌNH GIAO DIỆN
st.set_page_config(page_title="Hệ thống Tra cứu Watch Store", layout="wide")

# --- CSS TỐI THƯỢNG ---
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

# 2. THÔNG TIN HỆ THỐNG
PASSWORD_SYSTEM = "9999"

# Kết nối Supabase từ Secrets
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error("Chưa cấu hình SUPABASE_URL và SUPABASE_KEY trong Streamlit Secrets!")
    st.stop()

# 3. BẢO MẬT ĐĂNG NHẬP
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔐 Đăng nhập hệ thống")
    user_pwd = st.text_input("Nhập mật khẩu truy cập:", type="password")
    if st.button("Xác nhận"):
        if user_pwd == PASSWORD_SYSTEM:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Mật khẩu không chính xác!")
    st.stop()

# 4. HÀM XỬ LÝ CHUNG
def parse_money(val):
    if pd.isna(val): return 0
    val = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0

@st.cache_data(ttl=300)
def load_hoa_don():
    """Load toàn bộ bảng hoa_don từ Supabase (tự động phân trang)"""
    all_rows = []
    batch = 1000
    offset = 0
    while True:
        res = supabase.table("hoa_don").select("*").range(offset, offset + batch - 1).execute()
        rows = res.data
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < batch:
            break
        offset += batch

    df = pd.DataFrame(all_rows)

    # Đếm trùng lặp
    tong_ban_dau = len(df)
    df = df.drop_duplicates()
    st.session_state['so_dong_trung'] = tong_ban_dau - len(df)

    money_cols = ['Tổng tiền hàng', 'Khách cần trả', 'Khách đã trả', 'Đơn giá', 'Thành tiền']
    for col in money_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df

@st.cache_data(ttl=300)
def load_the_kho():
    """Load toàn bộ bảng the_kho từ Supabase"""
    all_rows = []
    batch = 1000
    offset = 0
    while True:
        res = supabase.table("the_kho").select("*").range(offset, offset + batch - 1).execute()
        rows = res.data
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < batch:
            break
        offset += batch

    df = pd.DataFrame(all_rows)

    numeric_kho = [
        "Tồn đầu kì", "Giá trị đầu kì", "Nhập NCC", "Giá trị nhập NCC",
        "Xuất bán", "Giá trị xuất bán", "Tồn cuối kì", "Giá trị cuối kì"
    ]
    for col in numeric_kho:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df

# ==========================================
# MODULE 1: HÓA ĐƠN
# ==========================================
def module_hoa_don():
    def hien_thi_hoa_don(inv_data, inv_code):
        row = inv_data.iloc[0]
        status = row.get('Trạng thái', 'N/A')
        bg_color = "#28a745" if status == "Hoàn thành" else "#dc3545"
        ten_kh = row.get('Tên khách hàng', 'Khách lẻ')
        sdt = row.get('Điện thoại', 'N/A')

        header = f"🧾 **{inv_code}** — {row.get('Thời gian', '')} | **{ten_kh}** ({sdt})"

        with st.expander(header, expanded=True):
            st.markdown(f"""
                <div style="display: flex; justify-content: flex-end; margin-top: -40px;">
                    <span style="background-color: {bg_color}; color: white; padding: 4px 15px; border-radius: 20px; font-weight: bold; font-size: 0.85rem;">
                        {status}
                    </span>
                </div>
            """, unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            c1.metric("Tổng tiền hàng", f"{row.get('Tổng tiền hàng', 0):,.0f} đ")
            c2.metric("Thực tế trả", f"{row.get('Khách đã trả', 0):,.0f} đ")

            cols = ['Mã hàng', 'Tên hàng', 'Số lượng', 'Đơn giá', 'Thành tiền', 'Ghi chú hàng hóa']
            df_view = inv_data[[c for c in cols if c in inv_data.columns]].copy()

            for c in ['Đơn giá', 'Thành tiền']:
                if c in df_view.columns:
                    df_view[c] = df_view[c].apply(lambda x: f"{x:,.0f} đ")

            with st.expander("📋 Xem chi tiết hàng hóa", expanded=False):
                st.dataframe(df_view, use_container_width=True, hide_index=True)

    def xu_ly_danh_sach_hoa_don(res):
        res_active = res[res['Trạng thái'] != 'Đã hủy']
        res_canceled = res[res['Trạng thái'] == 'Đã hủy']

        if not res_active.empty:
            for code in res_active['Mã hóa đơn'].unique():
                hien_thi_hoa_don(res_active[res_active['Mã hóa đơn'] == code], code)

        if not res_canceled.empty:
            so_luong_huy = len(res_canceled['Mã hóa đơn'].unique())
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander(f"🗑️ Xem các hóa đơn Đã hủy ({so_luong_huy})", expanded=False):
                for code in res_canceled['Mã hóa đơn'].unique():
                    hien_thi_hoa_don(res_canceled[res_canceled['Mã hóa đơn'] == code], code)

    try:
        raw_data = load_hoa_don()
        list_chi_nhanh = raw_data['Chi nhánh'].dropna().unique().tolist()
        selected_branches = st.multiselect("Chi nhánh:", options=list_chi_nhanh, default=list_chi_nhanh)

        if st.session_state.get('so_dong_trung', 0) > 0:
            st.warning(f"⚠️ **Cảnh báo dữ liệu:** Phát hiện {st.session_state['so_dong_trung']} dòng trùng lặp.")

        data = raw_data[raw_data['Chi nhánh'].isin(selected_branches)].copy()
        data['SĐT_Search'] = data['Điện thoại'].fillna('').str.replace(r'\D+', '', regex=True)

        tab1, tab2, tab3 = st.tabs(["📞 Số điện thoại", "🧾 Mã Hóa Đơn", "📅 Ngày tháng"])

        with tab1:
            search_phone = st.text_input("Nhập số điện thoại:", key="in_phone")
            if search_phone:
                clean_phone = search_phone.replace(" ", "")
                res = data[data['SĐT_Search'].str.contains(clean_phone, na=False)]
                if not res.empty:
                    st.info(f"Khách hàng: **{res.iloc[0].get('Tên khách hàng', 'Khách lẻ')}**")
                    xu_ly_danh_sach_hoa_don(res)
                else:
                    st.warning("Không tìm thấy số điện thoại.")

        with tab2:
            search_inv = st.text_input("Nhập mã (Ví dụ: 1007 hoặc HD011007):", key="in_inv")
            if search_inv:
                query = search_inv.strip().upper()
                res = data[data['Mã hóa đơn'].str.upper().str.endswith(query, na=False)]
                if not res.empty:
                    xu_ly_danh_sach_hoa_don(res)
                else:
                    st.warning("Không tìm thấy mã hóa đơn.")

        with tab3:
            search_date = st.text_input("Nhập ngày/tháng (Ví dụ: 14/04/2026):", key="in_date")
            if search_date:
                res = data[data['Thời gian'].astype(str).str.contains(search_date.strip(), na=False)]
                if not res.empty:
                    st.success(f"Tìm thấy {len(res['Mã hóa đơn'].unique())} hóa đơn.")
                    xu_ly_danh_sach_hoa_don(res)
                else:
                    st.warning("Không có dữ liệu trong thời gian này.")

    except Exception as e:
        st.error(f"Lỗi tải dữ liệu Hóa đơn: {e}")

# ==========================================
# MODULE 2: THẺ KHO
# ==========================================
def module_the_kho():
    try:
        data_kho = load_the_kho()

        if data_kho.empty:
            st.info("💡 Chưa có dữ liệu thẻ kho trong database.")
            return

        search_ma = st.text_input("🔍 Nhập Mã hàng hóa cần kiểm tra (Ví dụ: CASIO-01):").strip().upper()

        if search_ma:
            res = data_kho[data_kho['Mã hàng'].str.upper().str.contains(search_ma, na=False)]

            if not res.empty:
                st.success(f"Tìm thấy **{len(res)}** dòng cho: **{res.iloc[0].get('Tên hàng', search_ma)}**")

                cols_view = ['Chi nhánh', 'Mã hàng', 'Tên hàng', 'Tồn đầu kì', 'Nhập NCC',
                             'Xuất bán', 'Tồn cuối kì', 'Giá trị cuối kì']
                cols_view = [c for c in cols_view if c in res.columns]

                df_view = res[cols_view].copy()
                for c in ['Giá trị cuối kì', 'Giá trị đầu kì']:
                    if c in df_view.columns:
                        df_view[c] = df_view[c].apply(lambda x: f"{x:,.0f} đ")

                st.dataframe(df_view, use_container_width=True, hide_index=True)
            else:
                st.warning("Không tìm thấy mã hàng này.")

    except Exception as e:
        st.error(f"Lỗi tải dữ liệu Thẻ kho: {e}")

# ==========================================
# 5. ĐIỀU HƯỚNG CHÍNH
# ==========================================
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    chuc_nang = st.radio("Chọn phân hệ:", ["🧾 Tra cứu Hóa đơn", "📦 Lịch sử Thẻ kho"], horizontal=True, label_visibility="collapsed")
with col_h2:
    if st.button("🔄 Reload App", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("<hr style='margin-top: 0px; margin-bottom: 20px;'>", unsafe_allow_html=True)

if chuc_nang == "🧾 Tra cứu Hóa đơn":
    module_hoa_don()
else:
    module_the_kho()

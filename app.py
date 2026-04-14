import streamlit as st
import pandas as pd

# 1. CẤU HÌNH GIAO DIỆN
st.set_page_config(page_title="Hệ thống Tra cứu Watch Store", layout="wide")

# --- XÓA MENU STREAMLIT VÀ GITHUB ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .stAppDeployButton {display:none;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# 2. THÔNG TIN HỆ THỐNG
PASSWORD_SYSTEM = "9999"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT27nMRVzpVgaCVNmvREvonJM_fRJ2uGxm4I8LT2PuBxIaFtvuqIO54tOixVCmmpEcLThzEkG92iNsb/pub?output=csv"

# 3. BẢO MẬT
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

# 4. HÀM XỬ LÝ TIỀN TỆ
def parse_money(val):
    if pd.isna(val): return 0
    val = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0

@st.cache_data(ttl=300)
def load_data(url):
    df = pd.read_csv(url, dtype=str)
    money_cols = ['Tổng tiền hàng', 'Khách cần trả', 'Khách đã trả', 'Đơn giá', 'Thành tiền']
    for col in money_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_money)
    return df

# 5. HÀM VẼ 1 HÓA ĐƠN ĐƠN LẺ
def hien_thi_hoa_don(inv_data, inv_code):
    row = inv_data.iloc[0]
    status = row.get('Trạng thái', 'N/A')
    bg_color = "#28a745" if status == "Hoàn thành" else "#dc3545"
    ten_kh = row.get('Tên khách hàng', 'Khách lẻ')
    sdt = row.get('Điện thoại', 'N/A')
    
    header = f"🧾 {inv_code} — {row.get('Thời gian', '')} | {ten_kh} ({sdt})"
    
    with st.expander(header, expanded=True):
        st.markdown(f"""
            <div style="display: flex; justify-content: flex-end; margin-top: -40px;">
                <span style="background-color: {bg_color}; color: white; padding: 4px 15px; border-radius: 20px; font-weight: bold; font-size: 0.85rem;">
                    {status}
                </span>
            </div>
        """, unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Tổng tiền hàng", f"{row.get('Tổng tiền hàng', 0):,.0f} đ")
        c2.metric("Tổng hóa đơn", f"{row.get('Khách cần trả', 0):,.0f} đ")
        c3.metric("Thực tế trả", f"{row.get('Khách đã trả', 0):,.0f} đ")
        
        cols = ['Mã hàng', 'Tên hàng', 'Số lượng', 'Đơn giá', 'Thành tiền', 'Ghi chú hàng hóa']
        df_view = inv_data[[c for c in cols if c in inv_data.columns]].copy()
        
        for c in ['Đơn giá', 'Thành tiền']:
            if c in df_view.columns:
                df_view[c] = df_view[c].apply(lambda x: f"{x:,.0f} đ")
                
        # NÂNG CẤP: Bọc bảng sản phẩm vào một nút mở rộng mặc định đóng
        with st.expander("📦 Xem chi tiết hàng hóa", expanded=False):
            st.dataframe(df_view, use_container_width=True, hide_index=True)

# 6. HÀM QUẢN LÝ DANH SÁCH (Tách Đơn hoàn thành & Đơn hủy)
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

# 7. GIAO DIỆN CHÍNH
try:
    raw_data = load_data(SHEET_URL)
    
    col_title, col_filter, col_refresh = st.columns([2, 1.5, 0.5])
    with col_title:
        st.title("🔍 Tra cứu Hóa đơn")
    with col_filter:
        list_chi_nhanh = raw_data['Chi nhánh'].unique().tolist()
        selected_branches = st.multiselect("Lọc Chi nhánh:", options=list_chi_nhanh, default=list_chi_nhanh)
    with col_refresh:
        st.write("") 
        if st.button("🔄 Reload"):
            st.cache_data.clear()
            st.rerun()

    data = raw_data[raw_data['Chi nhánh'].isin(selected_branches)]
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
            else: st.warning("Không tìm thấy số điện thoại này.")

    with tab2:
        search_inv = st.text_input("Nhập mã (Ví dụ: 11119 hoặc HD011119):", key="in_inv")
        if search_inv:
            query = search_inv.strip().upper()
            res = data[data['Mã hóa đơn'].str.upper().str.endswith(query, na=False)]
            if not res.empty:
                xu_ly_danh_sach_hoa_don(res)
            else: st.warning("Không tìm thấy mã hóa đơn này.")

    with tab3:
        search_date = st.text_input("Nhập ngày/tháng (Ví dụ: 13/04/2026 hoặc 04/2026):", key="in_date")
        if search_date:
            res = data[data['Thời gian'].astype(str).str.contains(search_date.strip(), na=False)]
            if not res.empty:
                st.success(f"Tìm thấy {len(res['Mã hóa đơn'].unique())} hóa đơn tại các chi nhánh đã chọn.")
                xu_ly_danh_sach_hoa_don(res)
            else: st.warning("Không có hóa đơn nào trong thời gian này.")

except Exception as e:
    st.error(f"Lỗi: {e}")

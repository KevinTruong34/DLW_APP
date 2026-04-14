import streamlit as st
import pandas as pd

# 1. CẤU HÌNH GIAO DIỆN
st.set_page_config(page_title="Hệ thống Tra cứu Watch Store", layout="wide")

PASSWORD_SYSTEM = "9999"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT27nMRVzpVgaCVNmvREvonJM_fRJ2uGxm4I8LT2PuBxIaFtvuqIO54tOixVCmmpEcLThzEkG92iNsb/pub?output=csv"

# 2. BẢO MẬT
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

# 3. HÀM XỬ LÝ TIỀN TỆ
def parse_money(val):
    if pd.isna(val): return 0
    val = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0

@st.cache_data(ttl=300)
def load_data(url):
    df = pd.read_csv(url, dtype=str)
    # Xử lý các cột tiền ngay khi tải
    money_cols = ['Tổng tiền hàng', 'Khách cần trả', 'Khách đã trả', 'Đơn giá', 'Thành tiền']
    for col in money_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_money)
    return df

# 4. HÀM HIỂN THỊ HÓA ĐƠN
def hien_thi_hoa_don(inv_data, inv_code):
    row = inv_data.iloc[0]
    status = row.get('Trạng thái', 'N/A')
    bg_color = "#28a745" if status == "Hoàn thành" else "#dc3545"
    ten_kh = row.get('Tên khách hàng', 'Khách lẻ')
    sdt = row.get('Điện thoại', 'N/A')
    
    # Tiêu đề hiển thị đầy đủ thông tin
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
                
        st.dataframe(df_view, use_container_width=True, hide_index=True)

# 5. GIAO DIỆN CHÍNH
try:
    raw_data = load_data(SHEET_URL)
    
    # Khu vực bộ lọc trên cùng
    col_title, col_filter, col_refresh = st.columns([2, 1.5, 0.5])
    
    with col_title:
        st.title("🔍 Tra cứu Hóa đơn")
        
    with col_filter:
        # Lấy danh sách chi nhánh thực tế từ database
        list_chi_nhanh = raw_data['Chi nhánh'].unique().tolist()
        selected_branches = st.multiselect(
            "Lọc Chi nhánh:", 
            options=list_chi_nhanh, 
            default=list_chi_nhanh
        )
        
    with col_refresh:
        st.write("") # Căn lề
        if st.button("🔄 Reload"):
            st.cache_data.clear()
            st.rerun()

    # Lọc dữ liệu theo chi nhánh đã chọn
    data = raw_data[raw_data['Chi nhánh'].isin(selected_branches)]
    
    # Xử lý tìm kiếm số điện thoại (Xóa ký tự không phải số)
    data['SĐT_Search'] = data['Điện thoại'].fillna('').str.replace(r'\D+', '', regex=True)

    tab1, tab2, tab3 = st.tabs(["📞 Số điện thoại", "🧾 Mã Hóa Đơn", "📅 Ngày tháng"])
    
    with tab1:
        search_phone = st.text_input("Nhập số điện thoại:", key="in_phone")
        if search_phone:
            clean_phone = search_phone.replace(" ", "")
            res = data[data['SĐT_Search'].str.contains(clean_phone, na=False)]
            if not res.empty:
                for code in res['Mã hóa đơn'].unique():
                    hien_thi_hoa_don(res[res['Mã hóa đơn'] == code], code)
            else: st.warning("Không tìm thấy số điện thoại này.")

    with tab2:
        search_inv = st.text_input("Nhập mã (Ví dụ: 11119 hoặc HD011119):", key="in_inv")
        if search_inv:
            query = search_inv.strip().upper()
            # Tìm kiếm linh hoạt: Nếu gõ số thì tìm phần đuôi, nếu gõ đầy đủ HD thì tìm chính xác
            res = data[data['Mã hóa đơn'].str.contains(query, na=False)]
            if not res.empty:
                for code in res['Mã hóa đơn'].unique():
                    hien_thi_hoa_don(res[res['Mã hóa đơn'] == code], code)
            else: st.warning("Không tìm thấy mã hóa đơn này.")

    with tab3:
        search_date = st.text_input("Nhập ngày/tháng (Ví dụ: 13/04/2026 hoặc 04/2026):", key="in_date")
        if search_date:
            res = data[data['Thời gian'].astype(str).str.contains(search_date.strip(), na=False)]
            if not res.empty:
                codes = res['Mã hóa đơn'].unique()
                st.success(f"Tìm thấy {len(codes)} hóa đơn tại các chi nhánh đã chọn.")
                for code in codes:
                    hien_thi_hoa_don(res[res['Mã hóa đơn'] == code], code)
            else: st.warning("Không có hóa đơn nào trong thời gian này.")

except Exception as e:
    st.error(f"Lỗi: {e}")

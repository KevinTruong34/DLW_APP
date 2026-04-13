import streamlit as st
import pandas as pd

# --- CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="Tra cứu Hóa đơn KiotViet", layout="wide")

PASSWORD_SYSTEM = "9999"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT27nMRVzpVgaCVNmvREvonJM_fRJ2uGxm4I8LT2PuBxIaFtvuqIO54tOixVCmmpEcLThzEkG92iNsb/pub?output=csv"

# --- BẢO MẬT ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔐 Đăng nhập hệ thống tra cứu")
    user_pwd = st.text_input("Nhập mật khẩu truy cập:", type="password")
    if st.button("Xác nhận"):
        if user_pwd == PASSWORD_SYSTEM:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Mật khẩu không chính xác!")
    st.stop()

# --- HÀM XỬ LÝ DỮ LIỆU ---
def parse_money(val):
    if pd.isna(val): return 0
    val = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0

@st.cache_data(ttl=300)
def load_data(url):
    return pd.read_csv(url, dtype=str)

# --- HÀM GIAO DIỆN HIỂN THỊ HÓA ĐƠN CHUẨN ---
def hien_thi_hoa_don(inv_data, inv_code):
    row = inv_data.iloc[0]
    status = row.get('Trạng thái', 'N/A')
    bg_color = "#28a745" if status == "Hoàn thành" else "#dc3545"
    
    header = f"🧾 {inv_code} — {row.get('Thời gian', '')} ({row.get('Chi nhánh', '')})"
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

# --- GIAO DIỆN CHÍNH ---
col1, col2 = st.columns([3, 1])
with col1:
    st.title("🔍 Tra cứu Lịch sử Khách hàng")
with col2:
    if st.button("🔄 Cập nhật dữ liệu", use_container_width=True):
        st.cache_data.clear()
        st.success("Đã đồng bộ!")

try:
    # Tải và làm sạch dữ liệu
    data = load_data(SHEET_URL)
    data = data.dropna(subset=['Điện thoại', 'Mã hóa đơn'])
    
    # Tạo bản sao số điện thoại chỉ chứa số để tìm kiếm cho chuẩn
    data['SĐT_Clean'] = data['Điện thoại'].str.replace(r'\D+', '', regex=True)
    
    for col in ['Tổng tiền hàng', 'Khách cần trả', 'Khách đã trả', 'Đơn giá', 'Thành tiền']:
        if col in data.columns:
            data[col] = data[col].apply(parse_money)

    # CHIA 3 TAB CHỨC NĂNG TÌM KIẾM
    tab1, tab2, tab3 = st.tabs(["📞 Tìm theo Số điện thoại", "🧾 Tìm theo Mã Hóa Đơn", "📅 Tìm theo Ngày tháng"])
    
    # --- TAB 1: SỐ ĐIỆN THOẠI ---
    with tab1:
        search_phone = st.text_input("Nhập số điện thoại khách hàng:", key="phone")
        if search_phone:
            clean_phone = search_phone.replace(" ", "")
            result = data[data['SĐT_Clean'].str.contains(clean_phone, na=False)]
            
            if not result.empty:
                st.info(f"Khách hàng: **{result.iloc[0].get('Tên khách hàng', 'Ẩn danh')}**")
                unique_invoices = result['Mã hóa đơn'].unique()
                for inv_code in unique_invoices:
                    inv_data = result[result['Mã hóa đơn'] == inv_code]
                    hien_thi_hoa_don(inv_data, inv_code)
            else:
                st.warning("Không tìm thấy dữ liệu cho số điện thoại này.")

    # --- TAB 2: MÃ HÓA ĐƠN ---
    with tab2:
        search_inv = st.text_input("Nhập chính xác Mã hóa đơn (Ví dụ: HD011119):", key="invoice")
        if search_inv:
            clean_inv = search_inv.strip().upper()
            result = data[data['Mã hóa đơn'].str.upper() == clean_inv]
            
            if not result.empty:
                st.info(f"Khách hàng: **{result.iloc[0].get('Tên khách hàng', 'Ẩn danh')}** - SĐT: {result.iloc[0].get('Điện thoại', '')}")
                hien_thi_hoa_don(result, result.iloc[0]['Mã hóa đơn'])
            else:
                st.warning("Không tìm thấy mã hóa đơn này.")

    # --- TAB 3: NGÀY THÁNG ---
    with tab3:
        search_date = st.text_input("Nhập ngày cần tìm (Ví dụ: 13/04/2026 hoặc 04/2026):", key="date")
        if search_date:
            clean_date = search_date.strip()
            # Lọc các dòng mà cột 'Thời gian' chứa chuỗi ngày tháng nhập vào
            result = data[data['Thời gian'].astype(str).str.contains(clean_date, na=False)]
            
            if not result.empty:
                unique_invoices = result['Mã hóa đơn'].unique()
                st.success(f"Tìm thấy {len(unique_invoices)} hóa đơn trong thời gian này.")
                for inv_code in unique_invoices:
                    inv_data = result[result['Mã hóa đơn'] == inv_code]
                    hien_thi_hoa_don(inv_data, inv_code)
            else:
                st.warning("Không có hóa đơn nào trong khoảng thời gian này.")

except Exception as e:
    st.error(f"Lỗi hệ thống: {e}")

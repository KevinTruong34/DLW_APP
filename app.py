import streamlit as st
import pandas as pd

st.set_page_config(page_title="Tra cứu Hóa đơn Nội bộ", layout="wide")

# --- CẤU HÌNH BẢO MẬT ---
PASSWORD_SYSTEM = "9999" # BẠN HÃY ĐỔI MẬT KHẨU NÀY THEO Ý MUỐN
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT27nMRVzpVgaCVNmvREvonJM_fRJ2uGxm4I8LT2PuBxIaFtvuqIO54tOixVCmmpEcLThzEkG92iNsb/pub?output=csv"

# Kiểm tra mật khẩu trước khi hiện nội dung
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔐 Đăng nhập hệ thống")
    user_pwd = st.text_input("Nhập mật khẩu truy cập:", type="password")
    if st.button("Đăng nhập"):
        if user_pwd == PASSWORD_SYSTEM:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Sai mật khẩu!")
    st.stop()

# --- NỘI DUNG CHÍNH (Chỉ hiện sau khi đăng nhập đúng) ---
st.title("🔍 Hệ thống Tra cứu Khách hàng")

if st.button("🔄 Cập nhật dữ liệu từ Google Sheets"):
    st.cache_data.clear()
    st.success("Đã đồng bộ dữ liệu mới nhất!")

def parse_kiotviet_currency(val):
    if pd.isna(val): return 0
    val = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0

@st.cache_data(ttl=300)
def load_data_from_sheets(url):
    return pd.read_csv(url, dtype=str)

try:
    data = load_data_from_sheets(SHEET_URL)
    data = data.dropna(subset=['Điện thoại'])
    data['Điện thoại'] = data['Điện thoại'].str.replace(r'\D+', '', regex=True)
    
    money_cols = ['Tổng tiền hàng', 'Khách cần trả', 'Khách đã trả', 'Đơn giá', 'Giá bán', 'Thành tiền']
    for col in money_cols:
        if col in data.columns:
            data[col] = data[col].apply(parse_kiotviet_currency)

    search_query = st.text_input("Nhập số điện thoại khách hàng:")
    if search_query:
        clean_query = search_query.replace(" ", "")
        result = data[data['Điện thoại'].str.contains(clean_query, na=False)]
        
        if not result.empty:
            unique_invoices = result['Mã hóa đơn'].unique()
            st.info(f"Khách hàng: **{result.iloc[0].get('Tên khách hàng', 'Ẩn danh')}** - {len(unique_invoices)} hóa đơn.")
            
            for inv_code in unique_invoices:
                inv_data = result[result['Mã hóa đơn'] == inv_code]
                first_row = inv_data.iloc[0]
                with st.expander(f"🧾 {inv_code} - Ngày: {first_row.get('Thời gian', '')}", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Tổng hàng", f"{first_row.get('Tổng tiền hàng', 0):,.0f} đ")
                    c2.metric("Phải trả", f"{first_row.get('Khách cần trả', 0):,.0f} đ")
                    c3.metric("Thực trả", f"{first_row.get('Khách đã trả', 0):,.0f} đ")
                    
                    display_cols = ['Mã hàng', 'Tên hàng', 'Số lượng', 'Đơn giá', 'Thành tiền', 'Ghi chú hàng hóa']
                    df_view = inv_data[[c for c in display_cols if c in inv_data.columns]].copy()
                    st.dataframe(df_view, use_container_width=True, hide_index=True)
        else:
            st.warning("Không tìm thấy dữ liệu.")
except Exception as e:
    st.error(f"Lỗi: {e}")
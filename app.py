import streamlit as st
import pandas as pd

# 1. Cấu hình trang web
st.set_page_config(page_title="Hệ thống Tra cứu Hóa đơn", layout="wide")

# --- CẤU HÌNH BẢO MẬT ---
PASSWORD_SYSTEM = "9999" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT27nMRVzpVgaCVNmvREvonJM_fRJ2uGxm4I8LT2PuBxIaFtvuqIO54tOixVCmmpEcLThzEkG92iNsb/pub?output=csv"

# Kiểm tra đăng nhập
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

# --- NỘI DUNG CHÍNH ---
st.title("🔍 Tra cứu Lịch sử Khách hàng")

if st.button("🔄 Làm mới dữ liệu"):
    st.cache_data.clear()
    st.success("Đã đồng bộ dữ liệu mới nhất!")

def parse_money(val):
    if pd.isna(val): return 0
    val = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0

@st.cache_data(ttl=300)
def load_data(url):
    return pd.read_csv(url, dtype=str)

try:
    data = load_data(SHEET_URL)
    data = data.dropna(subset=['Điện thoại'])
    data['Điện thoại'] = data['Điện thoại'].str.replace(r'\D+', '', regex=True)
    
    # Xử lý các cột tiền
    money_cols = ['Tổng tiền hàng', 'Khách cần trả', 'Khách đã trả', 'Đơn giá', 'Thành tiền']
    for col in money_cols:
        if col in data.columns:
            data[col] = data[col].apply(parse_money)

    search_query = st.text_input("Nhập số điện thoại cần tìm:")
    if search_query:
        clean_query = search_query.replace(" ", "")
        result = data[data['Điện thoại'].str.contains(clean_query, na=False)]
        
        if not result.empty:
            unique_invoices = result['Mã hóa đơn'].unique()
            st.info(f"Khách hàng: **{result.iloc[0].get('Tên khách hàng', 'Ẩn danh')}**")
            
            for inv_code in unique_invoices:
                inv_data = result[result['Mã hóa đơn'] == inv_code]
                first_row = inv_data.iloc[0]
                
                # Logic xác định màu sắc trạng thái
                status = first_row.get('Trạng thái', 'N/A')
                bg_color = "#28a745" if status == "Hoàn thành" else "#dc3545"
                
                # Tạo tiêu đề expander kèm ngày tháng
                header_text = f"🧾 {inv_code} — Ngày: {first_row.get('Thời gian', '')}"
                
                with st.expander(header_text, expanded=True):
                    # Hiển thị Badge trạng thái ở góc phải bằng HTML
                    st.markdown(f"""
                        <div style="display: flex; justify-content: flex-end; margin-top: -40px;">
                            <span style="background-color: {bg_color}; color: white; padding: 4px 12px; border-radius: 15px; font-weight: bold; font-size: 0.9rem;">
                                {status}
                            </span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Các chỉ số tài chính
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Tổng tiền hàng", f"{first_row.get('Tổng tiền hàng', 0):,.0f} đ")
                    c2.metric("Tổng hóa đơn (Cần trả)", f"{first_row.get('Khách cần trả', 0):,.0f} đ")
                    c3.metric("Thực tế khách trả", f"{first_row.get('Khách đã trả', 0):,.0f} đ")
                    
                    # Bảng sản phẩm
                    display_cols = ['Mã hàng', 'Tên hàng', 'Số lượng', 'Đơn giá', 'Thành tiền', 'Ghi chú hàng hóa']
                    df_view = inv_data[[c for c in display_cols if c in inv_data.columns]].copy()
                    
                    # Format tiền trong bảng cho dễ nhìn
                    for col in ['Đơn giá', 'Thành tiền']:
                        if col in df_view.columns:
                            df_view[col] = df_view[col].apply(lambda x: f"{x:,.0f} đ")
                            
                    st.dataframe(df_view, use_container_width=True, hide_index=True)
        else:
            st.warning("Không tìm thấy dữ liệu.")
except Exception as e:
    st.error(f"Lỗi tải dữ liệu: {e}")

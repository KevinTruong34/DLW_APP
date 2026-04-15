import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# ==========================================
# PHIÊN BẢN: 8.0.0
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

# 2. THONG TIN HE THONG
PASSWORD_SYSTEM = "9999"
PASSWORD_ADMIN = "8888"

# Ket noi Supabase tu Secrets
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error("Chua cau hinh SUPABASE_URL va SUPABASE_KEY trong Streamlit Secrets!")
    st.stop()

# 3. BAO MAT DANG NHAP
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

# 4. HAM XU LY CHUNG
def parse_money(val):
    if pd.isna(val): return 0
    val = str(val).strip().replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0

@st.cache_data(ttl=300)
def load_hoa_don():
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
# MODULE 1: HOA DON
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
# MODULE 2: THE KHO
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
# MODULE 3: QUAN TRI DU LIEU
# ==========================================
def module_quan_tri():
    # --- Xac thuc Admin ---
    if "admin_auth" not in st.session_state:
        st.session_state["admin_auth"] = False

    if not st.session_state["admin_auth"]:
        st.markdown("### 🔒 Xác thực Quản trị viên")
        admin_pwd = st.text_input("Nhập mật khẩu quản trị:", type="password", key="admin_pwd")
        if st.button("Xác nhận", key="btn_admin"):
            if admin_pwd == PASSWORD_ADMIN:
                st.session_state["admin_auth"] = True
                st.rerun()
            else:
                st.error("Sai mật khẩu quản trị!")
        return

    # ====== TONG QUAN DU LIEU ======
    st.markdown("### 📊 Tổng quan dữ liệu")
    col1, col2 = st.columns(2)

    with col1:
        try:
            res = supabase.table("hoa_don").select("id", count="exact").execute()
            so_hd = res.count if res.count else 0
        except Exception:
            so_hd = "?"
        st.metric("Hóa đơn", f"{so_hd:,} dòng" if isinstance(so_hd, int) else so_hd)

    with col2:
        try:
            res = supabase.table("the_kho").select("id", count="exact").execute()
            so_tk = res.count if res.count else 0
        except Exception:
            so_tk = "?"
        st.metric("Thẻ kho", f"{so_tk:,} dòng" if isinstance(so_tk, int) else so_tk)

    try:
        data_kho = load_the_kho()
        if not data_kho.empty and 'Chi nhánh' in data_kho.columns:
            thong_ke = data_kho.groupby('Chi nhánh').size().reset_index(name='Số dòng')
            st.markdown("**Thẻ kho theo chi nhánh:**")
            st.dataframe(thong_ke, use_container_width=True, hide_index=True)
    except Exception:
        pass

    st.markdown("---")

    # ====== UPLOAD DU LIEU ======
    st.markdown("### 📤 Upload dữ liệu")
    tab_up1, tab_up2 = st.tabs(["📦 Upload Thẻ kho", "🧾 Upload Hóa đơn"])

    # ------ TAB UPLOAD THE KHO ------
    with tab_up1:
        st.markdown("""
        **Hướng dẫn:** Tải file **Xuất nhập tồn chi tiết** từ KiotViet (`.xlsx`), kéo thả vào đây.
        Hệ thống sẽ tự xử lý format và đẩy lên database.
        """)
        uploaded_kho = st.file_uploader("Chọn file Excel thẻ kho:", type=["xlsx", "xls"], key="up_kho")

        if uploaded_kho:
            try:
                df_kho = pd.read_excel(uploaded_kho)
                st.success(f"Đọc được **{len(df_kho)}** dòng, **{len(df_kho.columns)}** cột")

                required_cols = ['Mã hàng', 'Tên hàng', 'Chi nhánh', 'Tồn cuối kì']
                missing = [c for c in required_cols if c not in df_kho.columns]
                if missing:
                    st.error(f"File thiếu cột: {', '.join(missing)}")
                    st.stop()

                branches = df_kho['Chi nhánh'].unique().tolist()
                st.info(f"**Chi nhánh:** {', '.join(branches)} — **Tổng:** {len(df_kho)} dòng")

                with st.expander("👁️ Xem trước 5 dòng đầu", expanded=False):
                    st.dataframe(df_kho.head(), use_container_width=True, hide_index=True)

                if st.button("🚀 Xác nhận Upload Thẻ kho", key="btn_up_kho", type="primary"):
                    with st.spinner("Đang xử lý và upload..."):
                        text_cols = ['Nhóm hàng', 'Mã hàng', 'Mã vạch', 'Tên hàng', 'Thương hiệu', 'Chi nhánh']
                        for col in text_cols:
                            if col in df_kho.columns:
                                df_kho[col] = (df_kho[col].astype(str)
                                    .str.replace(',', ' ', regex=False)
                                    .str.replace('\n', ' ', regex=False)
                                    .str.replace('\r', ' ', regex=False)
                                    .str.strip())
                                df_kho.loc[df_kho[col] == 'nan', col] = None

                        numeric_cols = [c for c in df_kho.columns if c not in text_cols]
                        for col in numeric_cols:
                            df_kho[col] = pd.to_numeric(df_kho[col], errors='coerce').fillna(0).astype(int)

                        df_kho = df_kho.where(pd.notnull(df_kho), None)
                        records = df_kho.to_dict(orient='records')

                        # Convert numpy int to Python int for JSON
                        import numpy as np
                        for rec in records:
                            for k, v in rec.items():
                                if isinstance(v, (np.integer,)):
                                    rec[k] = int(v)
                                elif isinstance(v, (np.floating,)):
                                    rec[k] = float(v)

                        batch_size = 500
                        total = len(records)
                        success = 0
                        errors_list = []
                        progress = st.progress(0, text="Đang upload...")

                        for i in range(0, total, batch_size):
                            batch = records[i:i + batch_size]
                            try:
                                supabase.table("the_kho").insert(batch).execute()
                                success += len(batch)
                                progress.progress(min(success / total, 1.0),
                                                  text=f"Đã upload {success}/{total} dòng...")
                            except Exception as e:
                                errors_list.append(f"Batch {i}-{i+len(batch)}: {e}")

                        progress.empty()
                        if success == total:
                            st.success(f"✅ Upload thành công **{success}** dòng thẻ kho!")
                            st.cache_data.clear()
                        else:
                            st.warning(f"Upload: {success}/{total} thành công")
                            for err in errors_list:
                                st.error(err)
            except Exception as e:
                st.error(f"Lỗi đọc file: {e}")

    # ------ TAB UPLOAD HOA DON ------
    with tab_up2:
        st.markdown("""
        **Hướng dẫn:** Tải file **Danh sách hóa đơn** từ KiotViet (`.xlsx`), kéo thả vào đây.
        """)
        uploaded_hd = st.file_uploader("Chọn file Excel hóa đơn:", type=["xlsx", "xls"], key="up_hd")

        if uploaded_hd:
            try:
                df_hd = pd.read_excel(uploaded_hd)
                st.success(f"Đọc được **{len(df_hd)}** dòng, **{len(df_hd.columns)}** cột")

                required_cols_hd = ['Mã hóa đơn', 'Thời gian', 'Chi nhánh']
                missing_hd = [c for c in required_cols_hd if c not in df_hd.columns]
                if missing_hd:
                    st.error(f"File thiếu cột: {', '.join(missing_hd)}")
                    st.stop()

                branches_hd = df_hd['Chi nhánh'].unique().tolist()
                so_hd_unique = df_hd['Mã hóa đơn'].nunique()
                st.info(f"**Chi nhánh:** {', '.join(branches_hd)} — **{so_hd_unique}** hóa đơn, **{len(df_hd)}** dòng")

                with st.expander("👁️ Xem trước 5 dòng đầu", expanded=False):
                    st.dataframe(df_hd.head(), use_container_width=True, hide_index=True)

                if st.button("🚀 Xác nhận Upload Hóa đơn", key="btn_up_hd", type="primary"):
                    with st.spinner("Đang xử lý và upload..."):
                        for col in df_hd.columns:
                            if df_hd[col].dtype == 'object' or str(df_hd[col].dtype) == 'string':
                                df_hd[col] = (df_hd[col].astype(str)
                                    .str.replace('\n', ' ', regex=False)
                                    .str.replace('\r', ' ', regex=False)
                                    .str.strip())
                                df_hd.loc[df_hd[col] == 'nan', col] = None

                        money_cols = ['Tổng tiền hàng', 'Khách cần trả', 'Khách đã trả', 'Đơn giá', 'Thành tiền']
                        for col in money_cols:
                            if col in df_hd.columns:
                                df_hd[col] = pd.to_numeric(df_hd[col], errors='coerce').fillna(0).astype(int)

                        df_hd = df_hd.where(pd.notnull(df_hd), None)
                        records_hd = df_hd.to_dict(orient='records')

                        import numpy as np
                        for rec in records_hd:
                            for k, v in rec.items():
                                if isinstance(v, (np.integer,)):
                                    rec[k] = int(v)
                                elif isinstance(v, (np.floating,)):
                                    rec[k] = float(v)

                        batch_size = 500
                        total_hd = len(records_hd)
                        success_hd = 0
                        errors_hd = []
                        progress_hd = st.progress(0, text="Đang upload...")

                        for i in range(0, total_hd, batch_size):
                            batch = records_hd[i:i + batch_size]
                            try:
                                supabase.table("hoa_don").insert(batch).execute()
                                success_hd += len(batch)
                                progress_hd.progress(min(success_hd / total_hd, 1.0),
                                                     text=f"Đã upload {success_hd}/{total_hd} dòng...")
                            except Exception as e:
                                errors_hd.append(f"Batch {i}-{i+len(batch)}: {e}")

                        progress_hd.empty()
                        if success_hd == total_hd:
                            st.success(f"✅ Upload thành công **{success_hd}** dòng hóa đơn!")
                            st.cache_data.clear()
                        else:
                            st.warning(f"Upload: {success_hd}/{total_hd} thành công")
                            for err in errors_hd:
                                st.error(err)
            except Exception as e:
                st.error(f"Lỗi đọc file: {e}")

    st.markdown("---")

    # ====== XOA DU LIEU ======
    st.markdown("### 🗑️ Xóa dữ liệu")

    with st.expander("⚠️ Khu vực nguy hiểm — Xóa dữ liệu", expanded=False):
        col_del1, col_del2 = st.columns(2)

        with col_del1:
            bang_xoa = st.selectbox("Chọn bảng:", ["the_kho", "hoa_don"], key="sel_del_table")

        with col_del2:
            try:
                if bang_xoa == "the_kho":
                    data_tmp = load_the_kho()
                else:
                    data_tmp = load_hoa_don()
                if not data_tmp.empty and 'Chi nhánh' in data_tmp.columns:
                    ds_cn = ["-- Tất cả --"] + sorted(data_tmp['Chi nhánh'].dropna().unique().tolist())
                else:
                    ds_cn = ["-- Tất cả --"]
            except Exception:
                ds_cn = ["-- Tất cả --"]
            cn_xoa = st.selectbox("Chi nhánh:", ds_cn, key="sel_del_branch")

        try:
            if cn_xoa == "-- Tất cả --":
                res_count = supabase.table(bang_xoa).select("id", count="exact").execute()
            else:
                res_count = supabase.table(bang_xoa).select("id", count="exact").eq("Chi nhánh", cn_xoa).execute()
            so_dong_xoa = res_count.count if res_count.count else 0
        except Exception:
            so_dong_xoa = "?"

        pham_vi = f" (chi nhánh: {cn_xoa})" if cn_xoa != "-- Tất cả --" else " (TOÀN BỘ)"
        st.warning(f"Sẽ xóa **{so_dong_xoa}** dòng từ bảng `{bang_xoa}`{pham_vi}")

        confirm_text = st.text_input('Gõ **XOA** để xác nhận:', key="confirm_del")

        if st.button("🗑️ Thực hiện xóa", key="btn_del"):
            if confirm_text != "XOA":
                st.error('Bạn phải gõ đúng **XOA** để xác nhận.')
            else:
                with st.spinner("Đang xóa..."):
                    try:
                        if cn_xoa == "-- Tất cả --":
                            supabase.table(bang_xoa).delete().neq("id", -999999).execute()
                        else:
                            supabase.table(bang_xoa).delete().eq("Chi nhánh", cn_xoa).execute()
                        st.success("✅ Đã xóa thành công!")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Lỗi xóa: {e}")


# ==========================================
# 5. DIEU HUONG CHINH
# ==========================================
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    chuc_nang = st.radio(
        "Chọn phân hệ:",
        ["🧾 Tra cứu Hóa đơn", "📦 Lịch sử Thẻ kho", "⚙️ Quản trị"],
        horizontal=True,
        label_visibility="collapsed"
    )
with col_h2:
    if st.button("🔄 Reload App", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("<hr style='margin-top: 0px; margin-bottom: 20px;'>", unsafe_allow_html=True)

if chuc_nang == "🧾 Tra cứu Hóa đơn":
    module_hoa_don()
elif chuc_nang == "📦 Lịch sử Thẻ kho":
    module_the_kho()
else:
    module_quan_tri()

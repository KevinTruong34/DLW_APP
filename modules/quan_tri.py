import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
import bcrypt

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

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

    # ── Banner nhắc kết sổ (nếu vượt ngưỡng) ──
    rem = get_archive_reminder()
    if rem["need_reminder"]:
        st.warning(
            f"⚠ **Nên kết sổ phiếu App** — đã **{rem['days_oldest']} ngày** kể từ "
            f"phiếu App cũ nhất (ngày {rem['oldest_date'].strftime('%d/%m/%Y')}), "
            f"hiện có **{rem['n_active']} phiếu** đang tính delta vào tồn kho. "
            f"Quy trình: upload `the_kho` mới từ KiotViet ở tab **Upload**, "
            f"rồi sang tab **Xóa dữ liệu** để nhấn nút **Kết sổ tất cả phiếu App**."
        )

    tab_up, tab_del, tab_nv, tab_kh = st.tabs(["Upload","Xóa dữ liệu","Nhân viên","Upload KH"])

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
                        "Loại hàng":        "loai_sp",
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
                            df_out["loai_hang"]  = split[0].str.strip()
                            df_out["thuong_hieu"] = (split[1].str.strip() if 1 in split.columns else "").fillna("")
                        # thuong_hieu từ cột KiotViet nếu có (override parse)
                        if "thuong_hieu" in df_out.columns and "Thương hiệu" in df.columns:
                            df_out["thuong_hieu"] = df["Thương hiệu"].fillna(df_out["thuong_hieu"])
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
                                    log_action("UPLOAD_HANG_HOA", f"rows={ok}")
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

                                def _clean_val(v):
                                    if v is None: return None
                                    try:
                                        if pd.isna(v): return None
                                    except Exception: pass
                                    if isinstance(v, float) and (v != v): return None
                                    if isinstance(v, np.integer): return int(v)
                                    if isinstance(v, np.floating): return None if np.isnan(v) else float(v)
                                    return v

                                records = [{k: _clean_val(v) for k,v in row.items()}
                                           for row in df.to_dict(orient="records")]

                                # Xóa các dòng có (Mã hàng, Chi nhánh) trùng với file đang upload
                                # để tránh duplicate — lịch sử mã hàng/chi nhánh khác không bị ảnh hưởng
                                ma_hang_list = df["Mã hàng"].dropna().unique().tolist()
                                cn_list = df["Chi nhánh"].dropna().unique().tolist()
                                try:
                                    supabase.table("the_kho").delete() \
                                        .in_("Mã hàng", ma_hang_list) \
                                        .in_("Chi nhánh", cn_list) \
                                        .execute()
                                except Exception as e:
                                    st.error(f"Lỗi xóa dữ liệu cũ: {e}")
                                    st.stop()

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
                                    log_action("UPLOAD_THE_KHO", f"rows={ok}")
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

                                def _clean_val_hd(v):
                                    if v is None: return None
                                    try:
                                        if pd.isna(v): return None
                                    except Exception: pass
                                    if isinstance(v, float) and (v != v): return None
                                    if isinstance(v, np.integer): return int(v)
                                    if isinstance(v, np.floating): return None if np.isnan(v) else float(v)
                                    # Timestamp: convert sang format giống KiotViet để đồng nhất trong DB
                                    if isinstance(v, pd.Timestamp):
                                        return v.strftime("%d/%m/%Y %H:%M:%S")
                                    return v

                                records = [{k: _clean_val_hd(v) for k,v in row.items()}
                                           for row in df.to_dict(orient="records")]

                                # Xóa các hóa đơn trùng mã trong file đang upload
                                # → upload lại file cũ không bị nhân đôi, lịch sử tháng khác an toàn
                                ma_hd_list = df["Mã hóa đơn"].dropna().unique().tolist()
                                try:
                                    supabase.table("hoa_don").delete() \
                                        .in_("Mã hóa đơn", ma_hd_list) \
                                        .execute()
                                except Exception as e:
                                    st.error(f"Lỗi xóa dữ liệu cũ: {e}")
                                    st.stop()

                                total,ok = len(records),0
                                prog = st.progress(0,text="Đang upload...")
                                for i in range(0,total,500):
                                    try:
                                        supabase.table("hoa_don").insert(records[i:i+500]).execute()
                                        ok+=len(records[i:i+500])
                                        prog.progress(min(ok/total,1.0),text=f"{ok}/{total}...")
                                    except Exception as e: st.error(f"Batch {i}: {e}")
                                    except Exception as e: st.error(f"Batch {i}: {e}")
                                prog.empty()
                                if ok==total:
                                    log_action("UPLOAD_HOA_DON", f"rows={ok}")
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
                                    log_action("UPLOAD_CHUYEN_KHO",
                                              f"rows={ok} phieu={df['Mã chuyển hàng'].nunique()}")
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
                        q.execute()
                        log_action("DATA_DELETE",
                                  f"table={bang} chi_nhanh={cn_x} count={cnt}",
                                  level="warning")
                        st.success("Xóa thành công!"); st.cache_data.clear()
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
                log_action("PHIEU_ARCHIVE", f"rows={n_active}")
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
                    log_action("PHIEU_RESTORE", f"rows={n_archived}",
                              level="warning")
                    st.success(f"✓ Đã khôi phục {n_archived} dòng!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    with tab_nv:
        module_nhan_vien()

    with tab_kh:
        st.caption("Upload file **Danh sách khách hàng** từ KiotViet (.xlsx)")
        up_kh = st.file_uploader("Chọn file:", type=["xlsx","xls"], key="up_khach_hang")
        if up_kh:
            try:
                df_kh = pd.read_excel(up_kh)
                st.success(f"Đọc được {len(df_kh)} dòng")
                miss = [c for c in ["Mã khách hàng","Tên khách hàng","Điện thoại"] if c not in df_kh.columns]
                if miss:
                    st.error(f"Thiếu cột: {', '.join(miss)}")
                else:
                    st.info(f"{df_kh['Mã khách hàng'].nunique()} khách hàng")
                    with st.expander("Xem trước"):
                        st.dataframe(df_kh.head(), use_container_width=True, hide_index=True)
                    if st.button("Upload khách hàng", key="btn_up_kh", type="primary"):
                        with st.spinner("Đang xử lý..."):
                            def _cv(v):
                                if v is None: return None
                                try:
                                    if pd.isna(v): return None
                                except Exception: pass
                                if isinstance(v, float) and (v != v): return None
                                if isinstance(v, np.integer): return int(v)
                                if isinstance(v, np.floating): return None if np.isnan(v) else float(v)
                                if isinstance(v, pd.Timestamp): return v.strftime("%Y-%m-%d")
                                return str(v).strip() if str(v).strip() not in ("nan","None","") else None

                            def _to_int(v, default=0):
                                try:
                                    if v is None: return default
                                    if isinstance(v, float) and v != v: return default
                                    return int(float(v))
                                except: return default

                            rows_kh = []
                            for _, r in df_kh.iterrows():
                                sdt_raw = str(r.get("Điện thoại","") or "").strip().replace(" ","")
                                if not sdt_raw or sdt_raw == "nan": continue
                                rows_kh.append({
                                    "ma_kh":          _cv(r.get("Mã khách hàng")),
                                    "ten_kh":         _cv(r.get("Tên khách hàng")) or "Không tên",
                                    "sdt":            sdt_raw,
                                    "gioi_tinh":      _cv(r.get("Giới tính")),
                                    "ngay_sinh":      _cv(r.get("Ngày sinh")),
                                    "nhom_kh":        _cv(r.get("Nhóm khách hàng")),
                                    "chi_nhanh_tao":  _cv(r.get("Chi nhánh tạo")),
                                    "tong_ban":       _to_int(r.get("Tổng bán trừ trả hàng")),
                                    "diem_hien_tai":  _to_int(r.get("Điểm hiện tại")),
                                    "ngay_gd_cuoi":   _cv(r.get("Ngày giao dịch cuối")),
                                    "ghi_chu":        _cv(r.get("Ghi chú")),
                                    "trang_thai":     _to_int(r.get("Trạng thái"), default=1),
                                    "updated_at":     (datetime.now() + timedelta(hours=7)).isoformat(),
                                })

                            total, ok = len(rows_kh), 0
                            prog = st.progress(0, text="Đang upload...")
                            for i in range(0, total, 200):
                                batch = rows_kh[i:i+200]
                                try:
                                    # Upsert theo sdt — không trùng lặp
                                    supabase.table("khach_hang").upsert(
                                        batch, on_conflict="sdt"
                                    ).execute()
                                    ok += len(batch)
                                    prog.progress(min(ok/total, 1.0), text=f"{ok}/{total}...")
                                except Exception as e:
                                    st.error(f"Batch {i}: {e}")
                            prog.empty()
                            if ok == total:
                                log_action("UPLOAD_KHACH_HANG", f"rows={ok}")
                                st.success(f"✓ Upload {ok} khách hàng thành công!")
                                st.cache_data.clear()
            except Exception as e:
                st.error(f"Lỗi: {e}")

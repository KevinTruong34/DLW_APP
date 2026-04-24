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

def _kk_get_lines(ma_phieu: str) -> pd.DataFrame:
    res = supabase.table("phieu_kiem_ke_chi_tiet").select("*") \
        .eq("ma_phieu_kk", ma_phieu).execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    for col in ["ton_snapshot", "sl_quet", "sl_thuc_te", "ton_ky_vong_luc_duyet", "chenh_lech"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    # Sắp xếp: mã vừa quét gần nhất lên đầu (updated_at desc)
    # Hàng chưa quét (sl_quet=0) xuống cuối
    if "updated_at" in df.columns:
        df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")
        df["_da_quet"] = (df["sl_quet"] > 0).astype(int)
        df = df.sort_values(["_da_quet", "updated_at"], ascending=[False, False])
        df = df.drop(columns=["_da_quet"])
    else:
        df = df.sort_values("sl_quet", ascending=False)
    return df.reset_index(drop=True)


def _kk_complete(ma_phieu: str) -> tuple[bool, str]:
    """Nhân viên hoàn thành quét → chuyển phiếu sang Chờ duyệt admin."""
    try:
        supabase.table("phieu_kiem_ke").update({
            "trang_thai": "Chờ duyệt admin",
        }).eq("ma_phieu_kk", ma_phieu).execute()
        st.cache_data.clear()
        log_action("KIEMKE_COMPLETE", f"ma={ma_phieu}")
        return True, f"Phiếu {ma_phieu} đã chuyển sang Chờ duyệt admin."
    except Exception as e:
        return False, f"Lỗi hoàn thành phiếu: {e}"


def _kk_gen_ma_phieu() -> str:
    try:
        res = supabase.table("phieu_kiem_ke").select("ma_phieu_kk") \
            .like("ma_phieu_kk", "KK______").order("ma_phieu_kk", desc=True).limit(1).execute()
        if res.data:
            try:
                num = int(str(res.data[0]["ma_phieu_kk"])[2:]) + 1
            except Exception:
                num = 1
        else:
            num = 1
        return f"KK{num:06d}"
    except Exception:
        return f"KK{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:4].upper()}"


def _kk_build_scope_rows(chi_nhanh: str, nhom_hang_chon: str) -> tuple[list, str]:
    master = load_hang_hoa()
    kho = load_the_kho(branches_key=(chi_nhanh,))
    if master.empty or kho.empty:
        return [], "Chưa đủ dữ liệu master/thẻ kho để tạo phiếu kiểm kê."
    
    kho_map = kho.groupby("Mã hàng", as_index=False).agg(ton=("Tồn cuối kì", "sum"))
    # inner join: chỉ lấy hàng thực sự tồn tại trong kho chi nhánh này
    df = master.merge(kho_map, left_on="ma_hang", right_on="Mã hàng", how="inner")
    df["ton"] = pd.to_numeric(df["ton"], errors="coerce").fillna(0).astype(int)

    # Dùng loai_hang + thuong_hieu nếu có, fallback nhom_hang cũ
    def _get_nhom_col(df_in):
        if "loai_hang" in df_in.columns:
            th = df_in.get("thuong_hieu", pd.Series([""] * len(df_in))).fillna("")
            lt = df_in["loai_hang"].fillna("")
            return lt.where(th == "", lt + ">>" + th)
        return df_in["nhom_hang"].fillna("") if "nhom_hang" in df_in.columns else pd.Series([""] * len(df_in))

    nhom_col  = _get_nhom_col(df)
    nhom_list = [x.strip() for x in nhom_hang_chon.split("|") if x.strip()]
    mask = pd.Series([False] * len(df), index=df.index)
    for nhom in nhom_list:
        nhom_norm = ">>".join(p.strip() for p in nhom.split(">>"))
        if ">>" in nhom_norm:
            mask = mask | (nhom_col == nhom_norm)
        else:
            mask = mask | (nhom_col == nhom_norm) | nhom_col.str.startswith(nhom_norm + ">>")
    df = df[mask].copy()

    if df.empty:
        return [], f"Nhóm **{nhom_hang_chon}** không có mặt hàng nào tại chi nhánh này."

    # Tách thành 2 nhóm: có tồn > 0 (đưa vào phiếu luôn) và tồn = 0 (bỏ qua)
    # Nhân viên có thể quét phát sinh thêm nếu thực tế có hàng mà hệ thống chưa ghi nhận
    df = df[df["ton"] >= 0].copy()  # giữ cả ton=0 để snapshot đúng thực tế
    
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "ma_hang": str(r.get("ma_hang", "") or ""),
            "ma_vach": str(r.get("ma_vach", "") or ""),
            "ten_hang": str(r.get("ten_hang", "") or ""),
            "nhom_hang": str(r.get("nhom_hang", "") or ""),
            "ton_snapshot": int(r.get("ton", 0) or 0),
            "sl_quet": 0,
            "sl_thuc_te": 0,
            "ton_ky_vong_luc_duyet": 0,
            "chenh_lech": 0,
            "trang_thai_dong": "Đang kiểm",
        })
    return rows, ""


def _kk_create_phieu(chi_nhanh: str, nhom_cha: str, ghi_chu: str) -> tuple[bool, str]:
    rows, err = _kk_build_scope_rows(chi_nhanh, nhom_cha)
    if err:
        return False, err

    ma = _kk_gen_ma_phieu()
    user = get_user() or {}
    try:
        supabase.table("phieu_kiem_ke").insert({
            "ma_phieu_kk": ma,
            "chi_nhanh": chi_nhanh,
            "trang_thai": "Đang kiểm",
            "nhom_cha": nhom_cha,
            "ghi_chu": ghi_chu.strip(),
            "created_by": user.get("ho_ten", ""),
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "approved_by": None,
            "approved_at": None,
        }).execute()

        payload = []
        for r in rows:
            p = dict(r)
            p["ma_phieu_kk"] = ma
            payload.append(p)
        for i in range(0, len(payload), 500):
            supabase.table("phieu_kiem_ke_chi_tiet").insert(payload[i:i+500]).execute()
        st.cache_data.clear()
        log_action("KIEMKE_CREATE", f"ma={ma} cn={chi_nhanh} nhom={nhom_cha} rows={len(rows)}")
        return True, ma
    except Exception as e:
        return False, f"Lỗi tạo phiếu kiểm kê: {e}"


def _kk_scan_plus_one(ma_phieu: str, code: str) -> tuple[bool, str]:
    code = str(code or "").strip()
    if not code:
        return False, "Mã quét rỗng."
    
    code_n = code.lower()
    try:
        # 1. Tìm mã trong DÒNG CHI TIẾT của phiếu hiện tại
        rows = supabase.table("phieu_kiem_ke_chi_tiet") \
            .select("id,ma_hang,ma_vach,sl_quet,sl_thuc_te") \
            .eq("ma_phieu_kk", ma_phieu).execute().data or []
        
        hit = None
        for r in rows:
            mh = str(r.get("ma_hang", "") or "").strip().lower()
            mv = str(r.get("ma_vach", "") or "").strip().lower()
            if code_n == mh or code_n == mv:
                hit = r; break
                
        if hit:
            # ĐÃ CÓ TRONG PHIẾU: Cộng dồn +1
            sl_quet = int(hit.get("sl_quet", 0) or 0) + 1
            sl_tt = int(hit.get("sl_thuc_te", 0) or 0) + 1
            supabase.table("phieu_kiem_ke_chi_tiet").update({
                "sl_quet": sl_quet, "sl_thuc_te": sl_tt
            }).eq("id", hit["id"]).execute()
            return True, str(hit.get("ma_hang", "") or code)
        
        else:
            # KHÔNG CÓ TRONG PHIẾU (Tồn = 0): Lấy từ Master Data chèn vào
            master = load_hang_hoa()
            if master.empty:
                return False, "Dữ liệu Hàng hóa (Master) trống."
            
            match_mask = (master["ma_hang"].astype(str).str.strip().str.lower() == code_n) | \
                         (master["ma_vach"].astype(str).str.strip().str.lower() == code_n)
            m_hit = master[match_mask]
            
            if m_hit.empty:
                return False, f"Mã '{code}' hoàn toàn không tồn tại trong hệ thống KiotViet."
            
            row_data = m_hit.iloc[0]
            mh_new = str(row_data.get("ma_hang", ""))
            
            supabase.table("phieu_kiem_ke_chi_tiet").insert({
                "ma_phieu_kk": ma_phieu,
                "ma_hang": mh_new,
                "ma_vach": str(row_data.get("ma_vach", "")),
                "ten_hang": str(row_data.get("ten_hang", "")),
                "nhom_hang": str(row_data.get("nhom_hang", "")),
                "ton_snapshot": 0, # Tồn lúc tạo phiếu là 0
                "sl_quet": 1,      # Lần quét đầu tiên
                "sl_thuc_te": 1,
                "ton_ky_vong_luc_duyet": 0,
                "chenh_lech": 0,
                "trang_thai_dong": "Đang kiểm"
            }).execute()
            
            return True, f"{mh_new} (Phát sinh mới)"
            
    except Exception as e:
        return False, f"Lỗi scan: {e}"


def _kk_cancel_phieu(ma_phieu: str) -> tuple[bool, str]:
    try:
        supabase.table("phieu_kiem_ke_chi_tiet").delete().eq("ma_phieu_kk", ma_phieu).execute()
        supabase.table("phieu_kiem_ke").delete().eq("ma_phieu_kk", ma_phieu).execute()
        st.cache_data.clear()
        log_action("KIEMKE_CANCEL", f"ma={ma_phieu}")
        return True, "Đã hủy và xóa phiếu kiểm kê."
    except Exception as e:
        return False, f"Lỗi hủy phiếu: {e}"
def _kk_approve(ma_phieu: str) -> tuple[bool, str]:
    try:
        lines = _kk_get_lines(ma_phieu)
        if lines.empty:
            return False, "Phiếu không có dòng hàng."
        for _, r in lines.iterrows():
            ton_ss = int(r.get("ton_snapshot", 0) or 0)
            sl_tt = int(r.get("sl_thuc_te", 0) or 0)
            ch = sl_tt - ton_ss
            supabase.table("phieu_kiem_ke_chi_tiet").update({
                "ton_ky_vong_luc_duyet": ton_ss,
                "chenh_lech": ch,
                "trang_thai_dong": "Đã duyệt",
            }).eq("id", int(r["id"])).execute()

        supabase.table("phieu_kiem_ke").update({
            "trang_thai": "Đã duyệt",
            "approved_by": (get_user() or {}).get("ho_ten", ""),
            "approved_at": datetime.now().isoformat(),
        }).eq("ma_phieu_kk", ma_phieu).execute()
        st.cache_data.clear()
        log_action("KIEMKE_APPROVE", f"ma={ma_phieu}")
        return True, "Đã duyệt phiếu kiểm kê."
    except Exception as e:
        return False, f"Lỗi duyệt phiếu: {e}"


def module_kiem_ke():
    st.markdown("### 🧮 Kiểm kê")
    st.caption("MVP v1.1: Quét +1, hỗ trợ lọc nhóm con, Hủy phiếu rác.")
    active = get_active_branch()
    accessible = get_accessible_branches()

    tab_list, tab_create, tab_scan, tab_approve = st.tabs(
        ["Danh sách phiếu", "Tạo phiếu", "Quét kiểm kê", "Duyệt admin"]
    )

    with tab_list:
        try:
            df = load_phieu_kiem_ke(tuple(accessible))
            if df.empty:
                st.info("Chưa có phiếu kiểm kê.")
            else:
                view = df.copy()
                if "created_at" in view.columns:
                    view["Ngày Tạo"] = (pd.to_datetime(view["created_at"], utc=True)
                                        .dt.tz_convert("Asia/Ho_Chi_Minh")
                                        .dt.strftime("%d/%m/%Y %H:%M"))
                rename_map = {
                    "ma_phieu_kk": "Mã Phiếu", "chi_nhanh": "Chi Nhánh", 
                    "nhom_cha": "Nhóm Hàng", "trang_thai": "Trạng Thái", 
                    "created_by": "Người Tạo", "ghi_chu": "Ghi Chú"
                }
                view = view.rename(columns=rename_map)
                cols = ["Mã Phiếu", "Chi Nhánh", "Nhóm Hàng", "Trạng Thái", "Người Tạo", "Ngày Tạo", "Ghi Chú"]
                cols = [c for c in cols if c in view.columns]
                st.dataframe(view[cols], use_container_width=True, hide_index=True, height=380)

                # Xem chi tiết phiếu đã duyệt
                st.markdown("---")
                st.caption("📋 Xem chi tiết mặt hàng của một phiếu:")
                ma_options = view["Mã Phiếu"].tolist() if "Mã Phiếu" in view.columns else []
                picked_ma = st.selectbox("Chọn phiếu để xem chi tiết:", ["-- Chọn phiếu --"] + ma_options, key="kk_list_detail_pick")
                if picked_ma != "-- Chọn phiếu --":
                    detail = _kk_get_lines(picked_ma)
                    if detail.empty:
                        st.info("Phiếu này chưa có dữ liệu chi tiết.")
                    else:
                        detail["Chênh lệch"] = detail["sl_thuc_te"] - detail["ton_snapshot"]
                        detail_view = detail.rename(columns={
                            "ma_hang": "Mã Hàng", "ten_hang": "Tên Hàng",
                            "ton_snapshot": "Tồn Sổ Sách", "sl_thuc_te": "SL Thực Tế",
                            "sl_quet": "SL Quét"
                        })
                        dcols = ["Mã Hàng", "Tên Hàng", "Tồn Sổ Sách", "SL Quét", "SL Thực Tế", "Chênh lệch"]
                        dcols = [c for c in dcols if c in detail_view.columns]
                        st.dataframe(detail_view[dcols], use_container_width=True, hide_index=True, height=360)

                        # Xuất Excel import KiotViet — đặt ở đây để luôn truy cập được
                        # kể cả sau khi phiếu đã duyệt xong
                        import io
                        df_export = detail[["ma_hang", "sl_thuc_te"]].copy()
                        df_export.columns = ["Mã hàng", "Số lượng"]
                        buf = io.BytesIO()
                        df_export.to_excel(buf, index=False)
                        buf.seek(0)
                        st.download_button(
                            label="📥 Xuất Excel import KiotViet",
                            data=buf,
                            file_name=f"KiemKe_{picked_ma}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key=f"dl_kk_{picked_ma}"
                        )
        except Exception as e:
            st.error(f"Lỗi tải danh sách: {e}")

    with tab_create:
        cn_create = active
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_create = st.selectbox("Chi nhánh kiểm kê:", accessible, index=max(0, accessible.index(active)))
        
        ma_du_kien = _kk_gen_ma_phieu()
        st.info(f"🏷️ Mã phiếu dự kiến: **{ma_du_kien}**")

        master = load_hang_hoa()
        if master.empty:
            st.warning("Chưa có dữ liệu hàng hóa.")
        else:
            # Dùng loai_hang + thuong_hieu nếu có, fallback nhom_hang cũ
            if "loai_hang" in master.columns:
                master["_cha"] = master["loai_hang"].fillna("")
                master["_con"] = master.get("thuong_hieu", pd.Series([""] * len(master))).fillna("")
            else:
                nhom_col = master["nhom_hang"].fillna("") if "nhom_hang" in master.columns else pd.Series([""] * len(master))
                split = nhom_col.str.split(">>", n=1, expand=True)
                master["_cha"] = split[0].fillna("").str.strip()
                master["_con"] = split[1].fillna("").str.strip() if len(split.columns) > 1 else ""

            nhom_cha_list = sorted([str(x) for x in master["_cha"].unique() if str(x)])
            
            if not nhom_cha_list:
                st.warning("Không tìm thấy dữ liệu nhóm hàng.")
            else:
                # Build danh sách phẳng: gồm cả nhóm cha và nhóm con "Cha >> Con"
                nhom_flat = []
                for cha in nhom_cha_list:
                    nhom_flat.append(cha)
                    con_list = sorted([str(x) for x in master[master["_cha"] == cha]["_con"].unique() if str(x)])
                    for con in con_list:
                        nhom_flat.append(f"{cha}>>{con}")  # khớp format DB, không có dấu cách

                nhom_chon_list = st.multiselect(
                    "Chọn nhóm hàng kiểm kê (có thể chọn nhiều):",
                    options=nhom_flat,
                    placeholder="Chọn ít nhất 1 nhóm...",
                    key=f"kk_nhom_select_{st.session_state.get('kk_create_count', 0)}"
                )

                if nhom_chon_list:
                    st.caption(f"Đã chọn: {', '.join(nhom_chon_list)}")
                    # Lưu dưới dạng chuỗi phân cách "|" để truyền vào hàm tạo phiếu
                    nhom_chon = "|".join(nhom_chon_list)
                else:
                    nhom_chon = ""

                ghi_chu = st.text_area("Ghi chú phiếu:", key=f"kk_ghi_chu_{st.session_state.get('kk_create_count', 0)}", placeholder="Ghi chú đợt kiểm kê...")
                if st.button("Tạo phiếu kiểm kê", type="primary", use_container_width=True, disabled=not nhom_chon):
                    ok, msg = _kk_create_phieu(cn_create, nhom_chon, ghi_chu)
                    if ok:
                        st.session_state["kk_active_ma"] = msg
                        # Tăng counter để reset multiselect và text_area
                        st.session_state["kk_create_count"] = st.session_state.get("kk_create_count", 0) + 1
                        st.success(f"Đã tạo phiếu {msg}.")
                        st.rerun()
                    else:
                        st.error(msg)

    with tab_scan:
        try:
            df = load_phieu_kiem_ke(tuple(accessible))
            if df.empty:
                st.info("Chưa có phiếu để quét.")
            else:
                candidates = df[df["trang_thai"] == "Đang kiểm"].copy() if "trang_thai" in df.columns else pd.DataFrame()
                if candidates.empty:
                    st.info("Không có phiếu ở trạng thái Đang kiểm.")
                else:
                    opts = [f"{r['ma_phieu_kk']} · {r.get('chi_nhanh','')} · {r.get('nhom_cha','')}" for _, r in candidates.iterrows()]
                    idx = 0
                    ma_saved = st.session_state.get("kk_active_ma")
                    if ma_saved:
                        for i, x in enumerate(opts):
                            if x.startswith(ma_saved):
                                idx = i; break
                    
                    picked = st.selectbox("Chọn phiếu đang kiểm:", opts, index=idx)
                    ma_phieu = picked.split(" · ")[0]
                    st.session_state["kk_active_ma"] = ma_phieu

                    with st.form("kk_scan_form", clear_on_submit=True):
                        code = st.text_input("Quét mã vạch / mã hàng:", key="kk_scan_code", placeholder="Đưa con trỏ ở đây và quét...")
                        submitted = st.form_submit_button("Quét +1", use_container_width=True)
                    if submitted:
                        ok, msg = _kk_scan_plus_one(ma_phieu, code)
                        if ok:
                            st.success(f"✓ Đã cộng +1 cho mã {msg}")
                            st.cache_data.clear()
                        else:
                            st.warning(msg)

                    lines = _kk_get_lines(ma_phieu)
                    if not lines.empty:
                        view = lines.copy()
                        view["Lệch Tạm"] = view["sl_thuc_te"] - view["ton_snapshot"]
                        
                        rename_map = {
                            "id": "ID", "ma_hang": "Mã Hàng", "ma_vach": "Mã Vạch", "ten_hang": "Tên Hàng",
                            "ton_snapshot": "Tồn Kho", "sl_quet": "SL Quét", "sl_thuc_te": "SL Thực Tế"
                        }
                        view = view.rename(columns=rename_map)
                        cols = ["ID", "Mã Hàng", "Mã Vạch", "Tên Hàng", "Tồn Kho", "SL Quét", "SL Thực Tế", "Lệch Tạm"]
                        cols = [c for c in cols if c in view.columns]
                        
                        editor_key = f"kk_editor_{ma_phieu}"
                        st.caption("💡 *Mẹo: Nháy đúp vào ô thuộc cột **SL Thực Tế ✏️** để sửa trực tiếp.*")
                        edited_df = st.data_editor(
                            view[cols],
                            use_container_width=True,
                            hide_index=True,
                            key=editor_key,
                            height=360,
                            column_config={
                                "ID": None,
                                "Mã Hàng": st.column_config.TextColumn(disabled=True),
                                "Mã Vạch": st.column_config.TextColumn(disabled=True),
                                "Tên Hàng": st.column_config.TextColumn(disabled=True),
                                "Tồn Kho": st.column_config.NumberColumn(disabled=True),
                                "SL Quét": st.column_config.NumberColumn(disabled=True),
                                "Lệch Tạm": st.column_config.NumberColumn(disabled=True),
                                "SL Thực Tế": st.column_config.NumberColumn(
                                    "SL Thực Tế ✏️", 
                                    min_value=0, 
                                    step=1,
                                    help="Nháy đúp để sửa số lượng thực tế"
                                )
                            }
                        )

                        changes = st.session_state.get(editor_key, {}).get("edited_rows", {})
                        if changes:
                            st.warning("⚠️ Bảng có thay đổi chưa lưu. Hãy bấm 'Lưu các dòng đã sửa' trước khi làm việc khác!")
                            if st.button("💾 Lưu các dòng đã sửa", type="primary", use_container_width=True):
                                try:
                                    for row_idx, edit_data in changes.items():
                                        if "SL Thực Tế" in edit_data:
                                            new_sl = int(edit_data["SL Thực Tế"])
                                            row_id = int(view.iloc[row_idx]["ID"])
                                            supabase.table("phieu_kiem_ke_chi_tiet").update({
                                                "sl_thuc_te": new_sl
                                            }).eq("id", row_id).execute()
                                    st.success("✓ Đã cập nhật số lượng thành công!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Lỗi khi lưu: {e}")

                        st.markdown("---")
                        c1, c2, c3 = st.columns(3)
                        with c1: st.metric("Tổng tồn", f"{int(view['Tồn Kho'].sum())}")
                        with c2: st.metric("Tổng quét", f"{int(view['SL Quét'].sum())}")
                        with c3:
                            lech = int(view["Lệch Tạm"].sum())
                            st.metric("Tổng chênh lệch", f"{lech:+d}")

                        st.markdown("---")
                        # Nút Hủy luôn hiển thị (không phụ thuộc vào changes)
                        if not changes:
                            c_left, c_right = st.columns(2)
                            with c_left:
                                if st.button("Hoàn thành kiểm kê", type="primary", use_container_width=True):
                                    ok, msg = _kk_complete(ma_phieu)
                                    if ok: st.success(msg); st.rerun()
                                    else: st.error(msg)
                            with c_right:
                                if st.button("🗑️ Hủy phiếu này", type="secondary", use_container_width=True):
                                    ok, msg = _kk_cancel_phieu(ma_phieu)
                                    if ok:
                                        st.session_state.pop("kk_active_ma", None)
                                        st.success(msg); st.rerun()
                                    else: st.error(msg)
                        else:
                            # Khi có thay đổi chưa lưu: chỉ hiện nút Hủy, ẩn Hoàn thành
                            if st.button("🗑️ Hủy phiếu này", type="secondary", use_container_width=True, key="kk_cancel_pending"):
                                ok, msg = _kk_cancel_phieu(ma_phieu)
                                if ok:
                                    st.session_state.pop("kk_active_ma", None)
                                    st.success(msg); st.rerun()
                                else: st.error(msg)
        except Exception as e:
            st.error(f"Lỗi màn hình quét kiểm kê: {e}")

    with tab_approve:
        if not is_admin():
            st.info("Chỉ admin có quyền duyệt phiếu kiểm kê.")
        else:
            try:
                df = load_phieu_kiem_ke(tuple(accessible))
                pending = df[df["trang_thai"] == "Chờ duyệt admin"].copy() if (not df.empty and "trang_thai" in df.columns) else pd.DataFrame()
                if pending.empty:
                    st.info("Không có phiếu chờ duyệt.")
                else:
                    opts = [f"{r['ma_phieu_kk']} · {r.get('chi_nhanh','')} · {r.get('nhom_cha','')}" for _, r in pending.iterrows()]
                    picked = st.selectbox("Phiếu chờ duyệt:", opts, key="kk_pending_pick")
                    ma_phieu = picked.split(" · ")[0]
                    lines = _kk_get_lines(ma_phieu)
                    if not lines.empty:
                        lines["Lệch Dự Kiến"] = lines["sl_thuc_te"] - lines["ton_snapshot"]

                        # Lấy giá bán để tính giá trị
                        gia_map = get_gia_ban_map()
                        lines["_gia"] = lines["ma_hang"].astype(str).map(gia_map).fillna(0).astype(int)
                        lines["_gt_thuc_te"] = lines["sl_thuc_te"] * lines["_gia"]
                        lines["_gt_lech"] = lines["Lệch Dự Kiến"] * lines["_gia"]

                        tong_thuc_te_sl = int(lines["sl_thuc_te"].sum())
                        tong_thuc_te_gt = int(lines["_gt_thuc_te"].sum())
                        lech_tang = lines[lines["Lệch Dự Kiến"] > 0]
                        lech_giam = lines[lines["Lệch Dự Kiến"] < 0]
                        tong_tang_sl = int(lech_tang["Lệch Dự Kiến"].sum())
                        tong_tang_gt = int(lech_tang["_gt_lech"].sum())
                        tong_giam_sl = int(lech_giam["Lệch Dự Kiến"].sum())
                        tong_giam_gt = int(lech_giam["_gt_lech"].sum())
                        tong_lech_sl = tong_tang_sl + tong_giam_sl
                        tong_lech_gt = tong_tang_gt + tong_giam_gt

                        def fmt_vnd(x): return f"{x:,.0f}".replace(",", ".")

                        m1, m2, m3, m4 = st.columns(4)
                        with m1: st.metric(f"Tổng thực tế ({tong_thuc_te_sl})", fmt_vnd(tong_thuc_te_gt))
                        with m2: st.metric(f"Lệch tăng (+{tong_tang_sl})", fmt_vnd(tong_tang_gt))
                        with m3: st.metric(f"Lệch giảm ({tong_giam_sl})", fmt_vnd(abs(tong_giam_gt)))
                        with m4: st.metric(f"Tổng chênh ({tong_lech_sl:+d})", fmt_vnd(tong_lech_gt))
                        view = lines.rename(columns={
                            "ma_hang": "Mã Hàng", "ten_hang": "Tên Hàng", 
                            "ton_snapshot": "Tồn Kho", "sl_thuc_te": "SL Thực Tế"
                        })
                        cols = ["Mã Hàng", "Tên Hàng", "Tồn Kho", "SL Thực Tế", "Lệch Dự Kiến"]
                        cols = [c for c in cols if c in view.columns]
                        st.dataframe(view[cols], use_container_width=True, hide_index=True, height=320)
                        st.warning("Lưu ý: Rà soát kỹ trước khi duyệt.")
                        
                        c_left, c_right = st.columns(2)
                        with c_left:
                            if st.button("Duyệt & chốt phiếu", type="primary", use_container_width=True):
                                ok, msg = _kk_approve(ma_phieu)
                                if ok: st.success(msg); st.rerun()
                                else: st.error(msg)
                        with c_right:
                            if st.button("🗑️ Hủy / Xóa phiếu", type="secondary", use_container_width=True):
                                ok, msg = _kk_cancel_phieu(ma_phieu)
                                if ok: st.success(msg); st.rerun()
                                else: st.error(msg)
            except Exception as e:
                st.error(f"Lỗi màn hình duyệt phiếu: {e}")

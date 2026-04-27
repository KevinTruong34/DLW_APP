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

from utils.helpers import _build_phieu_html, _in_phieu_sc


# ══════════════════════════════════════════════════════════
# CSS scoped — chỉ apply cho module Sửa chữa
# ══════════════════════════════════════════════════════════
_SC_CSS = """
<style>
.sc-card {
    background: #fff;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 16px 18px;
    margin: 8px 0;
}
.sc-card-header {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 4px;
}
.sc-card-sub {
    font-size: 0.82rem;
    color: #888;
    margin-bottom: 10px;
}
.sc-info-row {
    display: flex;
    margin: 4px 0;
    font-size: 0.9rem;
}
.sc-info-label {
    color: #777;
    min-width: 110px;
}
.sc-info-val {
    color: #1a1a2e;
    font-weight: 500;
    flex: 1;
}
.sc-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    background: #fff7e0;
    color: #b78103;
    border: 1px solid #f3d984;
}
.sc-badge-green {
    background: #e8f5e9;
    color: #1a7f37;
    border-color: #a8d4ad;
}
.sc-badge-red {
    background: #ffebee;
    color: #cf4c2c;
    border-color: #f5b5a8;
}
.sc-section-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: #1a1a2e;
    margin: 14px 0 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid #ebebeb;
}
.sc-money-card {
    background: #fff;
    border: 1px solid #e8e8e8;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: center;
}
.sc-money-card-red {
    border: 2px solid #e63946;
    background: #fff8f8;
}
.sc-money-label {
    font-size: 0.78rem;
    color: #777;
    margin-bottom: 4px;
}
.sc-money-value {
    font-size: 1.2rem;
    font-weight: 700;
    color: #1a1a2e;
}
.sc-money-value-red {
    color: #e63946;
}
</style>
"""


def module_sua_chua():
    st.markdown(_SC_CSS, unsafe_allow_html=True)

    # ── Header ──
    st.markdown(
        "<div style='display:flex;align-items:center;justify-content:space-between;"
        "margin-bottom:16px;'>"
        "<div>"
        "<div style='font-size:1.4rem;font-weight:700;color:#1a1a2e;'>🔧 Sửa chữa</div>"
        "<div style='font-size:0.82rem;color:#888;'>Tạo và quản lý phiếu sửa chữa</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True
    )

    active = get_active_branch()
    accessible = get_accessible_branches()
    user = get_user() or {}
    ho_ten = user.get("ho_ten", user.get("username", ""))

    tab_list, tab_create, tab_detail, tab_hoadon = st.tabs(
        ["Danh sách phiếu", "Tạo phiếu mới", "Chi tiết / Cập nhật", "Tạo hóa đơn sửa"]
    )

    # ══════════════════════════════════════════════════════════
    # HELPERS — giữ nguyên 100% logic
    # ══════════════════════════════════════════════════════════
    @st.cache_data(ttl=60)
    def _load_phieu(branches_key: tuple) -> pd.DataFrame:
        try:
            res = supabase.table("phieu_sua_chua").select("*") \
                .in_("chi_nhanh", list(branches_key)) \
                .order("created_at", desc=True).execute()
            if not res.data: return pd.DataFrame()
            df = pd.DataFrame(res.data)
            if "ngay_tiep_nhan" in df.columns:
                df["_ngay"] = (pd.to_datetime(df["ngay_tiep_nhan"], utc=True)
                               .dt.tz_convert("Asia/Ho_Chi_Minh"))
                df["Ngày TN"] = df["_ngay"].dt.strftime("%d/%m/%Y %H:%M")
            return df
        except Exception as e:
            st.error(f"Lỗi tải phiếu: {e}"); return pd.DataFrame()

    def _load_chi_tiet(ma_phieu: str) -> pd.DataFrame:
        try:
            res = supabase.table("phieu_sua_chua_chi_tiet").select("*") \
                .eq("ma_phieu", ma_phieu).execute()
            if not res.data: return pd.DataFrame()
            df = pd.DataFrame(res.data)
            for col in ["so_luong", "don_gia"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            return df
        except Exception: return pd.DataFrame()

    def _gen_ma_phieu() -> str:
        try:
            res = supabase.table("phieu_sua_chua").select("ma_phieu") \
                .like("ma_phieu", "SC______").order("ma_phieu", desc=True).limit(1).execute()
            num = int(res.data[0]["ma_phieu"][2:]) + 1 if res.data else 1
            return f"SC{num:06d}"
        except Exception:
            return f"SC{datetime.now().strftime('%y%m%d%H%M')}"

    def _gen_ma_apsc() -> str:
        try:
            res = supabase.rpc("get_next_apsc_num", {}).execute()
            data = res.data
            if isinstance(data, list):
                num = int(data[0]) if data else 1
            elif data is not None:
                num = int(data)
            else:
                num = 1
            return f"APSC{num:06d}"
        except Exception:
            return f"APSC{(datetime.now() + timedelta(hours=7)).strftime('%y%m%d%H%M')}"

    def _tao_hoa_don_apsc(phieu: dict, ct: pd.DataFrame,
                           giam_gia: int, pttt: dict) -> str:
        ma_hd = _gen_ma_apsc()
        now_vn = datetime.now() + timedelta(hours=7)
        now_str = now_vn.strftime("%d/%m/%Y %H:%M:%S")
        tong = int((ct["so_luong"] * ct["don_gia"]).sum()) if not ct.empty else 0
        can_tra = max(0, tong - giam_gia - int(phieu.get("khach_tra_truoc", 0)))
        rows = []
        base = {
            "Mã hóa đơn": ma_hd, "Chi nhánh": phieu.get("chi_nhanh",""),
            "Mã YCSC": phieu.get("ma_phieu", ""),
            "Thời gian": now_str, "Thời gian tạo": now_str,
            "Tên khách hàng": phieu.get("ten_khach",""),
            "Điện thoại": phieu.get("sdt_khach",""),
            "Trạng thái": "Hoàn thành", "Người bán": ho_ten,
            "Tổng tiền hàng": tong, "Giảm giá hóa đơn": giam_gia,
            "Khách cần trả": can_tra, "Khách đã trả": can_tra,
            "Tiền mặt": pttt.get("tien_mat", 0),
            "Chuyển khoản": pttt.get("chuyen_khoan", 0),
            "Thẻ": pttt.get("the", 0),
            "Ví": 0, "Điểm": 0, "Còn cần thu (COD)": 0,
            "Kênh bán": "Tại quầy", "Ghi chú": phieu.get("mo_ta_loi",""),
        }
        if ct.empty:
            rows.append(base)
        else:
            for _, r in ct.iterrows():
                tt = int(r["so_luong"]) * int(r["don_gia"])
                row = {**base,
                    "Mã hàng": str(r.get("ma_hang") or ""),
                    "Mã vạch": str(r.get("ma_hang") or ""),
                    "Tên hàng": str(r.get("ten_hang","")),
                    "Số lượng": int(r["so_luong"]),
                    "Đơn giá": int(r["don_gia"]),
                    "Thành tiền": tt, "Giá bán": int(r["don_gia"]),
                    "Giảm giá %": 0, "Giảm giá": 0,
                }
                rows.append(row)
        supabase.table("hoa_don").insert(rows).execute()
        return ma_hd

    TRANG_THAI_LIST = ["Đang sửa", "Chờ linh kiện", "Chờ giao khách"]
    LOAI_YC_LIST   = ["Sửa chữa", "Bảo hành"]
    LOAI_DONG_LIST = ["Dịch vụ", "Linh kiện"]

    def _badge_status_html(tt: str) -> str:
        """Trả về badge HTML cho trạng thái."""
        cls = "sc-badge"
        if tt == "Hoàn thành":
            cls += " sc-badge-green"
        elif tt == "Chờ giao khách":
            pass  # vàng default
        else:
            cls += " sc-badge-red"
        return f'<span class="{cls}">{tt}</span>'

    def _widget_them_dv(key_prefix: str, items_key: str):
        hh = load_hang_hoa()
        ma_tim = st.text_input("🔍 Tìm mã / tên hàng hóa:", key=f"{key_prefix}_ma_tim",
                                placeholder="VD: PDH, pin, lau dầu...")
        hits = pd.DataFrame()
        if ma_tim.strip() and not hh.empty:
            s = ma_tim.strip().lower()
            s_nospace = s.replace(" ", "")
            def _fuzzy(val):
                v = str(val).lower()
                return s in v or s_nospace in v.replace(" ", "")
            mask = (hh["ma_hang"].apply(_fuzzy) | hh["ten_hang"].apply(_fuzzy))
            hits = hh[mask].head(8)

        if not hits.empty:
            for _, row in hits.iterrows():
                gia = int(row.get("gia_ban", 0))
                label = f"{row['ma_hang']} — {row['ten_hang']}  |  {gia:,}đ".replace(",",".")
                col_lbl, col_sl, col_btn = st.columns([5, 1, 1])
                with col_lbl: st.markdown(f"<span style='font-size:0.9rem'>{label}</span>", unsafe_allow_html=True)
                with col_sl:
                    sl = st.number_input("SL", min_value=1, value=1,
                                          key=f"{key_prefix}_sl_{row['ma_hang']}", label_visibility="collapsed")
                with col_btn:
                    if st.button("➕", key=f"{key_prefix}_add_{row['ma_hang']}"):
                        st.session_state.setdefault(items_key, []).append({
                            "loai_dong": "Dịch vụ",
                            "ten_hang":  str(row["ten_hang"]),
                            "ma_hang":   str(row["ma_hang"]),
                            "so_luong":  int(sl),
                            "don_gia":   gia,
                        })
                        st.rerun()
        elif ma_tim.strip():
            st.caption("Không tìm thấy — có thể nhập tay bên dưới:")
            ca, cb, cc, cd = st.columns([3, 1, 2, 1])
            with ca: ten_tay = st.text_input("Tên:", key=f"{key_prefix}_tay_ten")
            with cb: sl_tay  = st.number_input("SL:", min_value=1, value=1, key=f"{key_prefix}_tay_sl")
            with cc: gia_tay = st.number_input("Đơn giá:", min_value=0, step=10000,
                                                value=0, key=f"{key_prefix}_tay_gia")
            with cd:
                st.write("")
                if st.button("➕", key=f"{key_prefix}_tay_add") and ten_tay.strip():
                    st.session_state.setdefault(items_key, []).append({
                        "loai_dong": "Dịch vụ", "ten_hang": ten_tay.strip(),
                        "ma_hang": None, "so_luong": sl_tay, "don_gia": gia_tay,
                    })
                    st.rerun()

    def _hien_thi_items(items_key: str):
        items = st.session_state.get(items_key, [])
        if not items:
            st.caption("_(Chưa có mục nào)_")
            return
        for i, item in enumerate(items):
            ci1, ci2, ci3, ci4, ci5 = st.columns([2, 4, 1, 2, 1])
            with ci1: st.markdown(f"<span style='font-size:0.9rem'>{item.get('loai_dong','')}</span>", unsafe_allow_html=True)
            with ci2: st.markdown(f"<span style='font-size:0.9rem'>{item.get('ten_hang','')}</span>", unsafe_allow_html=True)
            with ci3: st.markdown(f"<span style='font-size:0.9rem'>x{item.get('so_luong',1)}</span>", unsafe_allow_html=True)
            with ci4: st.markdown(f"<span style='font-size:0.9rem'>{item.get('don_gia',0):,}đ</span>".replace(",","."), unsafe_allow_html=True)
            with ci5:
                if st.button("✕", key=f"del_{items_key}_{i}"):
                    st.session_state[items_key].pop(i); st.rerun()

    # ══════════════════════════════════════════════════════════
    # TAB 1 — DANH SÁCH PHIẾU
    # ══════════════════════════════════════════════════════════
    with tab_list:
        # ── Filter bar trong card ──
        with st.container():
            st.markdown('<div class="sc-section-title">🔍 Bộ lọc</div>', unsafe_allow_html=True)
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                cn_filter = active
                if is_ke_toan_or_admin() and len(accessible) > 1:
                    cn_filter = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible, key="sc_cn_filter")
                else:
                    st.caption(f"📍 Chi nhánh: **{active}**")
                branches = accessible if cn_filter == "Tất cả" else [cn_filter]
            with col_f2:
                tt_filter = st.selectbox("Trạng thái:",
                    ["Tất cả"] + TRANG_THAI_LIST + ["Hoàn thành"], key="sc_tt_filter")

            search = st.text_input("Tìm SĐT / Mã phiếu / Tên khách:", key="sc_search",
                                    placeholder="VD: '900' tìm SC000900...")

        df = _load_phieu(tuple(branches))
        if df.empty:
            st.info("Chưa có phiếu sửa chữa.")
        else:
            if tt_filter != "Tất cả":
                df = df[df["trang_thai"] == tt_filter]
            if search.strip():
                s = search.strip().lower()
                def _match_ma(ma):
                    try: return str(int(ma[2:])).endswith(s) if ma.startswith("SC") else s in ma.lower()
                    except: return s in str(ma).lower()
                mask = (df["ma_phieu"].apply(_match_ma) |
                        df["sdt_khach"].astype(str).str.lower().str.contains(s, na=False) |
                        df["ten_khach"].astype(str).str.lower().str.contains(s, na=False))
                df = df[mask]

            if df.empty:
                st.info("Không tìm thấy phiếu phù hợp.")
            else:
                st.markdown(
                    f'<div class="sc-section-title">📋 Danh sách ({len(df)} phiếu)</div>',
                    unsafe_allow_html=True
                )
                view = df.rename(columns={
                    "ma_phieu": "Mã Phiếu", "chi_nhanh": "Chi Nhánh",
                    "ten_khach": "Khách hàng", "sdt_khach": "SĐT",
                    "loai_yeu_cau": "Loại", "hieu_dong_ho": "Hiệu ĐH",
                    "trang_thai": "Trạng Thái", "ngay_hen_tra": "Hẹn Trả",
                    "nguoi_tiep_nhan": "NV Tiếp Nhận"
                })
                cols = ["Mã Phiếu", "Chi Nhánh", "Khách hàng", "SĐT", "Loại",
                        "Hiệu ĐH", "Trạng Thái", "Hẹn Trả", "Ngày TN", "NV Tiếp Nhận"]
                cols = [c for c in cols if c in view.columns]
                st.dataframe(view[cols], use_container_width=True, hide_index=True, height=380)

                # ── Section Xem chi tiết ──
                st.markdown(
                    '<div class="sc-section-title" style="margin-top:18px;">'
                    '📄 Xem chi tiết dịch vụ / linh kiện</div>',
                    unsafe_allow_html=True
                )
                ma_opts = view["Mã Phiếu"].tolist() if "Mã Phiếu" in view.columns else []
                picked_list = st.selectbox("Chọn phiếu:", ["-- Chọn --"] + ma_opts,
                    key="sc_list_pick", label_visibility="collapsed")
                if picked_list != "-- Chọn --":
                    ct_list = _load_chi_tiet(picked_list)
                    if ct_list.empty:
                        st.info("Phiếu này chưa có dịch vụ.")
                    else:
                        ct_list["Thành tiền"] = ct_list["so_luong"] * ct_list["don_gia"]
                        ct_view = ct_list.rename(columns={
                            "loai_dong": "Loại", "ten_hang": "Tên", "ma_hang": "Mã",
                            "so_luong": "SL", "don_gia": "Đơn giá"
                        })
                        vcols = ["Loại", "Tên", "Mã", "SL", "Đơn giá", "Thành tiền"]
                        vcols = [c for c in vcols if c in ct_view.columns]
                        st.dataframe(ct_view[vcols], use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════
    # TAB 2 — TẠO PHIẾU MỚI
    # ══════════════════════════════════════════════════════════
    with tab_create:
        cnt = st.session_state.get("sc_create_count", 0)

        # ── Header thông tin tạo phiếu ──
        col_h1, col_h2 = st.columns([2, 1])
        with col_h1:
            ma_du_kien = _gen_ma_phieu()
            st.markdown(
                f'<div class="sc-card" style="background:#f4f6fa;border-color:#d6def0;">'
                f'<div style="font-size:0.78rem;color:#777;">Mã phiếu dự kiến</div>'
                f'<div style="font-size:1.3rem;font-weight:700;color:#2E86DE;'
                f'font-family:monospace;">{ma_du_kien}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with col_h2:
            cn_create = active
            if is_ke_toan_or_admin() and len(accessible) > 1:
                cn_create = st.selectbox("Chi nhánh tiếp nhận:", accessible,
                                         index=accessible.index(active) if active in accessible else 0,
                                         key=f"sc_cn_create_{cnt}")
            else:
                st.markdown(
                    f'<div class="sc-card" style="background:#fff8f8;border-color:#f5b5a8;">'
                    f'<div style="font-size:0.78rem;color:#777;">Chi nhánh</div>'
                    f'<div style="font-size:1rem;font-weight:600;color:#1a1a2e;">📍 {cn_create}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # ── Section: Thông tin khách hàng ──
        st.markdown(
            '<div class="sc-section-title">👤 Thông tin khách hàng</div>',
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            sdt_khach = st.text_input("Số điện thoại: *", key=f"sc_sdt_kh_{cnt}",
                                       placeholder="0xxx xxx xxx")
            sdt_prev_key = f"sc_sdt_prev_{cnt}"
            ten_key      = f"sc_ten_kh_{cnt}"
            kh_key       = f"sc_kh_found_{cnt}"
            if sdt_khach.strip() != st.session_state.get(sdt_prev_key, ""):
                st.session_state[sdt_prev_key] = sdt_khach.strip()
                kh_found = lookup_khach_hang(sdt_khach) if sdt_khach.strip() else None
                st.session_state[kh_key] = kh_found
                if kh_found:
                    st.session_state[ten_key] = kh_found["ten_kh"]
                else:
                    st.session_state[ten_key] = ""
                st.rerun()
            kh_found = st.session_state.get(kh_key)
            if sdt_khach.strip() and not kh_found:
                st.caption("⚠️ SĐT chưa có — khách mới sẽ được lưu tự động")
            elif kh_found:
                st.caption(f"✓ Khách cũ: **{kh_found['ten_kh']}**")
        with c2:
            ten_khach = st.text_input("Tên khách hàng: *", key=ten_key)

        # ── Section: Thông tin đồng hồ ──
        st.markdown(
            '<div class="sc-section-title">⌚ Thông tin đồng hồ</div>',
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            hieu_dh  = st.text_input("Hiệu đồng hồ:", key=f"sc_hieu_dh_{cnt}",
                                      placeholder="Casio, Citizen, Seiko...")
            loai_yc   = st.selectbox("Loại yêu cầu:", LOAI_YC_LIST, key=f"sc_loai_yc_{cnt}")
        with c2:
            dac_diem = st.text_input("Đặc điểm (IMEI / mô tả):", key=f"sc_dac_diem_{cnt}",
                                      placeholder="Số serial, màu sắc, trầy xước...")
            ngay_hen  = st.date_input("Ngày hẹn trả:", key=f"sc_ngay_hen_{cnt}",
                                       value=None, format="DD/MM/YYYY")

        mo_ta = st.text_area("Mô tả lỗi / yêu cầu: *", key=f"sc_mo_ta_{cnt}",
                              placeholder="Mô tả chi tiết tình trạng đồng hồ...",
                              height=80)

        # ── Section: Thanh toán & Ghi chú ──
        st.markdown(
            '<div class="sc-section-title">💰 Thanh toán & Ghi chú</div>',
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            tra_truoc = st.number_input("Khách trả trước (đ):", min_value=0, step=10000,
                                         key=f"sc_tra_truoc_{cnt}", value=0)
            if tra_truoc > 0:
                st.caption(f"= {int(tra_truoc):,}đ".replace(",","."))
        with c2:
            ghi_chu   = st.text_area("Ghi chú nội bộ:", key=f"sc_ghi_chu_nb_{cnt}",
                                      placeholder="Thợ kỹ thuật ghi chú...",
                                      height=80)

        # ── Section: Dịch vụ / Linh kiện dự kiến ──
        st.markdown(
            '<div class="sc-section-title">🔧 Dịch vụ / Linh kiện dự kiến '
            '<span style="font-weight:400;color:#888;font-size:0.82rem;">'
            '(có thể bỏ trống — thêm sau khi thợ đánh giá)</span></div>',
            unsafe_allow_html=True
        )
        items_key = f"sc_items_{cnt}"
        st.session_state.setdefault(items_key, [])
        with st.expander(f"Danh sách ({len(st.session_state[items_key])} mục)",
                          expanded=len(st.session_state[items_key]) > 0):
            _hien_thi_items(items_key)
            st.markdown("---")
            _widget_them_dv(f"sc_new_{cnt}", items_key)

        items = st.session_state.get(items_key, [])
        if items:
            tong = sum(x["so_luong"] * x["don_gia"] for x in items)
            st.markdown(
                f'<div class="sc-money-card sc-money-card-red" style="margin-top:10px;">'
                f'<div class="sc-money-label">Tổng dự kiến</div>'
                f'<div class="sc-money-value sc-money-value-red">'
                f'{tong:,}đ</div></div>'.replace(",","."),
                unsafe_allow_html=True
            )

        st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
        can_create = ten_khach.strip() and sdt_khach.strip() and mo_ta.strip()
        if st.button("✅ Tạo phiếu & In", type="primary", use_container_width=True,
                     disabled=not can_create):
            try:
                ma = _gen_ma_phieu()
                supabase.table("phieu_sua_chua").insert({
                    "ma_phieu": ma, "chi_nhanh": cn_create,
                    "ten_khach": ten_khach.strip(), "sdt_khach": sdt_khach.strip(),
                    "loai_yeu_cau": loai_yc, "hieu_dong_ho": hieu_dh.strip() or None,
                    "dac_diem": dac_diem.strip() or None, "mo_ta_loi": mo_ta.strip(),
                    "khach_tra_truoc": int(tra_truoc), "ghi_chu_noi_bo": ghi_chu.strip() or None,
                    "trang_thai": "Đang sửa", "nguoi_tiep_nhan": ho_ten,
                    "ngay_hen_tra": ngay_hen.isoformat() if ngay_hen else None,
                    "created_by": user.get("username",""),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }).execute()
                if items:
                    supabase.table("phieu_sua_chua_chi_tiet").insert(
                        [{"ma_phieu": ma, **item} for item in items]
                    ).execute()

                _upsert_khach_hang(ten_khach.strip(), sdt_khach.strip(), cn_create)

                ct_new = pd.DataFrame(items) if items else pd.DataFrame()
                if not ct_new.empty:
                    for col in ["so_luong","don_gia"]:
                        ct_new[col] = pd.to_numeric(ct_new[col], errors="coerce").fillna(0).astype(int)
                phieu_data = {
                    "ma_phieu": ma, "ten_khach": ten_khach.strip(),
                    "sdt_khach": sdt_khach.strip(), "hieu_dong_ho": hieu_dh.strip(),
                    "loai_yeu_cau": loai_yc, "dac_diem": dac_diem.strip(),
                    "mo_ta_loi": mo_ta.strip(), "khach_tra_truoc": int(tra_truoc),
                    "ngay_hen_tra": str(ngay_hen) if ngay_hen else None,
                    "nguoi_tiep_nhan": ho_ten,
                    "Ngày TN": (datetime.now() + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M"),
                }
                st.session_state["sc_pending_print_html"] = _build_phieu_html(phieu_data, ct_new)

                st.session_state["sc_create_count"] = cnt + 1
                st.session_state["sc_active_ma"] = ma
                st.cache_data.clear()
                log_action("SC_CREATE", f"ma={ma} kh={ten_khach} cn={cn_create}")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi tạo phiếu: {e}")

        if st.session_state.get("sc_pending_print_html"):
            _in_phieu_sc(st.session_state.pop("sc_pending_print_html"), key="sc_print_new")
            st.success(f"✓ Đã tạo phiếu — cửa sổ in đang mở")

    # ══════════════════════════════════════════════════════════
    # TAB 3 — CHI TIẾT / CẬP NHẬT (theo mẫu ChatGPT)
    # ══════════════════════════════════════════════════════════
    with tab_detail:
        # Scroll lên đầu sau khi lưu cập nhật
        if st.session_state.pop("sc_scroll_top", False):
            st.components.v1.html(
                "<script>window.parent.document.querySelector('section.main').scrollTo(0,0);</script>",
                height=0
            )
        df_all = _load_phieu(tuple(accessible))
        df_chua_xong = df_all[df_all["trang_thai"] != "Hoàn thành"].copy() if not df_all.empty else df_all
        if df_chua_xong.empty:
            st.info("Không có phiếu nào đang xử lý.")
        else:
            # ── Search bar ──
            search_dt = st.text_input("Tìm kiếm / Mã phiếu / Tên khách:", key="sc_search_dt",
                                       placeholder="VD: '900' hoặc 'SC000900'...")
            df_filtered = df_chua_xong.copy()
            if search_dt.strip():
                s = search_dt.strip().lower()
                def _match_ma2(ma):
                    try: return str(int(ma[2:])).endswith(s) if ma.startswith("SC") else s in ma.lower()
                    except: return s in str(ma).lower()
                mask = (df_filtered["ma_phieu"].apply(_match_ma2) |
                        df_filtered["sdt_khach"].astype(str).str.lower().str.contains(s, na=False) |
                        df_filtered["ten_khach"].astype(str).str.lower().str.contains(s, na=False))
                df_filtered = df_filtered[mask]

            if df_filtered.empty:
                st.info("Không tìm thấy phiếu phù hợp.")
            else:
                opts = [f"{r['ma_phieu']} · {r.get('ten_khach','')} · {r.get('trang_thai','')}"
                        for _, r in df_filtered.iterrows()]
                idx = 0
                saved = st.session_state.get("sc_active_ma")
                if saved:
                    for i, o in enumerate(opts):
                        if o.startswith(saved): idx = i; break

                picked = st.selectbox("Chọn phiếu:", opts, index=idx, key="sc_detail_pick")
                ma_pick = picked.split(" · ")[0]
                st.session_state["sc_active_ma"] = ma_pick

                phieu = df_chua_xong[df_chua_xong["ma_phieu"] == ma_pick].iloc[0]
                ct    = _load_chi_tiet(ma_pick)

                # ── Header phiếu với badge trạng thái ──
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:center;margin:18px 0 10px;">'
                    f'<div>'
                    f'<div style="font-size:1.25rem;font-weight:700;color:#1a1a2e;">'
                    f'{ma_pick} — {phieu.get("ten_khach","")}</div>'
                    f'<div style="font-size:0.85rem;color:#777;">'
                    f'📞 {phieu.get("sdt_khach","")}</div>'
                    f'</div>'
                    f'<div>{_badge_status_html(phieu.get("trang_thai",""))}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # ── Layout 2 cột: Thông tin khách + Chi tiết DV ──
                col_left, col_right = st.columns([1, 1])

                with col_left:
                    # Card thông tin tiếp nhận
                    info_html = (
                        '<div class="sc-card">'
                        '<div class="sc-card-header">📋 Thông tin tiếp nhận</div>'
                    )
                    rows = [
                        ("Chi nhánh", phieu.get("chi_nhanh","")),
                        ("Hiệu ĐH", phieu.get("hieu_dong_ho") or "—"),
                        ("Đặc điểm", phieu.get("dac_diem") or "—"),
                        ("Loại YC", phieu.get("loai_yeu_cau","")),
                        ("NV tiếp nhận", phieu.get("nguoi_tiep_nhan") or "—"),
                        ("Ngày TN", phieu.get("Ngày TN","—")),
                        ("Hẹn trả", phieu.get("ngay_hen_tra") or "—"),
                    ]
                    for label, val in rows:
                        info_html += (
                            f'<div class="sc-info-row">'
                            f'<div class="sc-info-label">{label}:</div>'
                            f'<div class="sc-info-val">{val}</div>'
                            f'</div>'
                        )
                    info_html += '</div>'
                    st.markdown(info_html, unsafe_allow_html=True)

                    # Card mô tả lỗi
                    desc_html = (
                        '<div class="sc-card">'
                        '<div class="sc-card-header">📝 Mô tả lỗi / Ghi chú</div>'
                        f'<div style="font-size:0.92rem;color:#1a1a2e;line-height:1.5;">'
                        f'{phieu.get("mo_ta_loi","") or "—"}</div>'
                    )
                    if phieu.get("ghi_chu_noi_bo"):
                        desc_html += (
                            f'<div style="margin-top:8px;padding-top:8px;'
                            f'border-top:1px dashed #ddd;">'
                            f'<div style="font-size:0.78rem;color:#888;">Ghi chú nội bộ:</div>'
                            f'<div style="font-size:0.88rem;color:#555;">'
                            f'{phieu.get("ghi_chu_noi_bo","")}</div>'
                            f'</div>'
                        )
                    desc_html += '</div>'
                    st.markdown(desc_html, unsafe_allow_html=True)

                with col_right:
                    # Card dịch vụ / linh kiện
                    st.markdown(
                        '<div class="sc-card-header" style="margin-top:8px;">'
                        '🔧 Dịch vụ / Linh kiện</div>',
                        unsafe_allow_html=True
                    )
                    if not ct.empty:
                        ct["Thành tiền"] = ct["so_luong"] * ct["don_gia"]
                        ct_view = ct.rename(columns={
                            "loai_dong": "Loại", "ten_hang": "Tên", "ma_hang": "Mã",
                            "so_luong": "SL", "don_gia": "Đơn giá"
                        })
                        vcols = ["Loại", "Tên", "Mã", "SL", "Đơn giá", "Thành tiền"]
                        vcols = [c for c in vcols if c in ct_view.columns]
                        st.dataframe(ct_view[vcols], use_container_width=True, hide_index=True,
                                     height=min(280, 42 + len(ct_view) * 35))

                        # 3 metric cards
                        tong = int(ct["Thành tiền"].sum())
                        tra_truoc = int(phieu.get("khach_tra_truoc", 0))
                        con_lai = tong - tra_truoc

                        m1, m2, m3 = st.columns(3)
                        with m1:
                            st.markdown(
                                f'<div class="sc-money-card">'
                                f'<div class="sc-money-label">Tổng cộng</div>'
                                f'<div class="sc-money-value">{tong:,}đ</div>'
                                f'</div>'.replace(",","."),
                                unsafe_allow_html=True
                            )
                        with m2:
                            st.markdown(
                                f'<div class="sc-money-card">'
                                f'<div class="sc-money-label">Đã trả trước</div>'
                                f'<div class="sc-money-value">{tra_truoc:,}đ</div>'
                                f'</div>'.replace(",","."),
                                unsafe_allow_html=True
                            )
                        with m3:
                            st.markdown(
                                f'<div class="sc-money-card sc-money-card-red">'
                                f'<div class="sc-money-label">Còn lại</div>'
                                f'<div class="sc-money-value sc-money-value-red">'
                                f'{con_lai:,}đ</div>'
                                f'</div>'.replace(",","."),
                                unsafe_allow_html=True
                            )
                    else:
                        st.caption("_Chưa có dịch vụ / linh kiện nào_")

                # ── Section: Cập nhật phiếu ──
                if "sc_upd_open" not in st.session_state:
                    st.session_state["sc_upd_open"] = False
                if (st.session_state.get("sc_upd_dv_ma_tim", "").strip()
                        or st.session_state.get("sc_upd_items", [])):
                    st.session_state["sc_upd_open"] = True

                st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)

                with st.expander("✏️ Cập nhật phiếu", expanded=st.session_state["sc_upd_open"]):
                    cur_tt = phieu.get("trang_thai", "Đang sửa")

                    col_u1, col_u2 = st.columns(2)
                    with col_u1:
                        new_tt = st.selectbox("Trạng thái:", TRANG_THAI_LIST,
                                              index=TRANG_THAI_LIST.index(cur_tt) if cur_tt in TRANG_THAI_LIST else 0,
                                              key="sc_upd_tt")
                    with col_u2:
                        new_hen = st.date_input("Ngày hẹn trả:", key="sc_upd_hen",
                                                 value=pd.to_datetime(phieu["ngay_hen_tra"]).date()
                                                 if phieu.get("ngay_hen_tra") else None,
                                                 format="DD/MM/YYYY")

                    new_gc  = st.text_area("Ghi chú nội bộ:", value=phieu.get("ghi_chu_noi_bo") or "",
                                            key="sc_upd_gc", height=80)

                    # Dịch vụ đã lưu
                    if not ct.empty:
                        st.markdown(
                            '<div class="sc-section-title" style="margin-top:14px;">'
                            'Dịch vụ / Linh kiện đã lưu</div>',
                            unsafe_allow_html=True
                        )
                        for _, row in ct.iterrows():
                            ci1, ci2, ci3, ci4, ci5 = st.columns([2, 4, 1, 2, 1])
                            with ci1:
                                st.markdown(f"<span style='font-size:0.9rem'>{row.get('loai_dong','')}</span>", unsafe_allow_html=True)
                            with ci2:
                                st.markdown(f"<span style='font-size:0.9rem'>{row.get('ten_hang','')}</span>", unsafe_allow_html=True)
                            with ci3:
                                st.markdown(f"<span style='font-size:0.9rem'>x{int(row.get('so_luong',1))}</span>", unsafe_allow_html=True)
                            with ci4:
                                st.markdown(f"<span style='font-size:0.9rem'>{int(row.get('don_gia',0)):,}đ</span>".replace(",","."), unsafe_allow_html=True)
                            with ci5:
                                if st.button("✕", key=f"del_ct_{row['id']}"):
                                    try:
                                        supabase.table("phieu_sua_chua_chi_tiet").delete() \
                                            .eq("id", int(row["id"])).execute()
                                        st.cache_data.clear()
                                        log_action("SC_DEL_ITEM", f"ma={ma_pick} item={row.get('ten_hang','')}")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Lỗi xóa: {e}")

                    # Thêm dịch vụ mới
                    st.markdown(
                        '<div class="sc-section-title" style="margin-top:14px;">'
                        '➕ Thêm dịch vụ / Linh kiện</div>',
                        unsafe_allow_html=True
                    )
                    _widget_them_dv("sc_upd_dv", "sc_upd_items")
                    upd_items = st.session_state.get("sc_upd_items", [])
                    _hien_thi_items("sc_upd_items")
                    if upd_items:
                        tong_moi = sum(x["so_luong"] * x["don_gia"] for x in upd_items)
                        st.caption(f"Tổng dịch vụ mới thêm: **{tong_moi:,}đ**".replace(",","."))

                    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
                    if st.button("💾 Lưu cập nhật", type="primary", use_container_width=True, key="sc_save_upd"):
                        try:
                            supabase.table("phieu_sua_chua").update({
                                "trang_thai":     new_tt,
                                "ghi_chu_noi_bo": new_gc.strip() or None,
                                "ngay_hen_tra":   new_hen.isoformat() if new_hen else None,
                                "updated_at":     datetime.now().isoformat(),
                            }).eq("ma_phieu", ma_pick).execute()

                            new_items = st.session_state.get("sc_upd_items", [])
                            if new_items:
                                supabase.table("phieu_sua_chua_chi_tiet").insert(
                                    [{"ma_phieu": ma_pick, **item} for item in new_items]
                                ).execute()
                                st.session_state["sc_upd_items"] = []

                            st.cache_data.clear()
                            log_action("SC_UPDATE", f"ma={ma_pick} trang_thai={new_tt}")
                            st.session_state["sc_upd_open"] = False
                            st.session_state["sc_scroll_top"] = True
                            st.success("✓ Đã cập nhật!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi: {e}")

                # ── Action buttons ──
                st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    if st.button("🖨️ In phiếu (A5)", use_container_width=True, key="sc_print_detail"):
                        _in_phieu_sc(_build_phieu_html(dict(phieu), ct), key="sc_print_d")

                with col_a2:
                    if is_admin():
                        if st.button("🗑️ Hủy / Xóa phiếu này", type="secondary",
                                     use_container_width=True, key="sc_delete"):
                            try:
                                supabase.table("phieu_sua_chua_chi_tiet").delete() \
                                    .eq("ma_phieu", ma_pick).execute()
                                supabase.table("phieu_sua_chua").delete() \
                                    .eq("ma_phieu", ma_pick).execute()
                                st.session_state.pop("sc_active_ma", None)
                                st.cache_data.clear()
                                log_action("SC_DELETE", f"ma={ma_pick}", level="warning")
                                st.success("Đã xóa phiếu."); st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi xóa: {e}")

    # ══════════════════════════════════════════════════════════
    # TAB 4 — TẠO HÓA ĐƠN SỬA
    # ══════════════════════════════════════════════════════════
    with tab_hoadon:
        df_all_hd = _load_phieu(tuple(accessible))
        cho_giao = df_all_hd[df_all_hd["trang_thai"] == "Chờ giao khách"].copy() \
            if not df_all_hd.empty else pd.DataFrame()

        if cho_giao.empty:
            st.info("Không có phiếu nào ở trạng thái **Chờ giao khách**.")
            st.caption("Cập nhật trạng thái phiếu sang 'Chờ giao khách' ở tab Chi tiết / Cập nhật trước.")
        else:
            # ── Search + Select phiếu ──
            opts_hd = [f"{r['ma_phieu']} · {r.get('ten_khach','')} · {r.get('sdt_khach','')}"
                       for _, r in cho_giao.iterrows()]

            search_hd = st.text_input("Tìm SĐT / Mã phiếu / Tên khách:", key="sc_hd_search",
                                       placeholder="VD: '900' tìm SC000900...")
            if search_hd.strip():
                s_hd = search_hd.strip().lower()
                opts_hd = [o for o in opts_hd if s_hd in o.lower()]
                if not opts_hd:
                    st.warning("Không tìm thấy phiếu phù hợp.")
                    st.stop()

            picked_hd = st.selectbox("Chọn phiếu:", opts_hd, key="sc_hd_pick")
            ma_hd_pick = picked_hd.split(" · ")[0]

            phieu_hd = cho_giao[cho_giao["ma_phieu"] == ma_hd_pick].iloc[0]
            ct_hd    = _load_chi_tiet(ma_hd_pick)

            # ── Header phiếu chọn ──
            st.markdown(
                f'<div class="sc-card" style="margin-top:14px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<div class="sc-card-header">{ma_hd_pick} — {phieu_hd.get("ten_khach","")}</div>'
                f'<div class="sc-card-sub">📞 {phieu_hd.get("sdt_khach","")}'
                f' · ⌚ {phieu_hd.get("hieu_dong_ho") or "—"}</div>'
                f'</div>'
                f'<div>{_badge_status_html("Chờ giao khách")}</div>'
                f'</div>'
                f'<div style="margin-top:8px;font-size:0.88rem;color:#555;">'
                f'<b>Mô tả:</b> {phieu_hd.get("mo_ta_loi","") or "—"}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            # ── Bảng dịch vụ ──
            if ct_hd.empty:
                st.warning("Phiếu chưa có dịch vụ/linh kiện nào. Thêm trước ở tab Chi tiết.")
            else:
                st.markdown(
                    '<div class="sc-section-title">🔧 Chi tiết dịch vụ / linh kiện</div>',
                    unsafe_allow_html=True
                )
                ct_hd["Thành tiền"] = ct_hd["so_luong"] * ct_hd["don_gia"]
                ct_view = ct_hd.rename(columns={
                    "ten_hang": "Tên", "ma_hang": "Mã",
                    "so_luong": "SL", "don_gia": "Đơn giá"
                })
                vcols = ["Tên", "Mã", "SL", "Đơn giá", "Thành tiền"]
                vcols = [c for c in vcols if c in ct_view.columns]
                st.dataframe(ct_view[vcols], use_container_width=True, hide_index=True)

            tong_dv = int(ct_hd["Thành tiền"].sum()) if not ct_hd.empty else 0
            tra_truoc = int(phieu_hd.get("khach_tra_truoc", 0))

            # ── Section: Thông tin hóa đơn ──
            st.markdown(
                '<div class="sc-section-title">💰 Thông tin hóa đơn</div>',
                unsafe_allow_html=True
            )

            col_g, col_pttt = st.columns([1, 1])
            with col_g:
                giam_gia = st.number_input("Giảm giá (đ):", min_value=0, step=10000,
                                            value=0, key="sc_hd_giam")
                if giam_gia > 0:
                    st.caption(f"= {int(giam_gia):,}đ".replace(",","."))
            with col_pttt:
                chia_pttt = st.checkbox("Chia nhiều phương thức", key="sc_hd_chia",
                                         help="Bật để chia tiền giữa các phương thức")

            can_tra = max(0, tong_dv - giam_gia - tra_truoc)

            # ── 3 metric cards ──
            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown(
                    f'<div class="sc-money-card">'
                    f'<div class="sc-money-label">Tổng dịch vụ</div>'
                    f'<div class="sc-money-value">{tong_dv:,}đ</div>'
                    f'</div>'.replace(",","."),
                    unsafe_allow_html=True
                )
            with m2:
                st.markdown(
                    f'<div class="sc-money-card">'
                    f'<div class="sc-money-label">Giảm giá + Trả trước</div>'
                    f'<div class="sc-money-value">{giam_gia + tra_truoc:,}đ</div>'
                    f'</div>'.replace(",","."),
                    unsafe_allow_html=True
                )
            with m3:
                st.markdown(
                    f'<div class="sc-money-card sc-money-card-red">'
                    f'<div class="sc-money-label">Khách cần trả</div>'
                    f'<div class="sc-money-value sc-money-value-red">{can_tra:,}đ</div>'
                    f'</div>'.replace(",","."),
                    unsafe_allow_html=True
                )

            # ── Phương thức thanh toán ──
            st.markdown(
                '<div class="sc-section-title">💳 Phương thức thanh toán</div>',
                unsafe_allow_html=True
            )

            if not chia_pttt:
                pttt_chon = st.radio("PTTT:", ["Tiền mặt", "Chuyển khoản", "Thẻ"],
                                      horizontal=True, key="sc_hd_pttt",
                                      label_visibility="collapsed")
                pttt = {
                    "tien_mat":      can_tra if pttt_chon == "Tiền mặt" else 0,
                    "chuyen_khoan":  can_tra if pttt_chon == "Chuyển khoản" else 0,
                    "the":           can_tra if pttt_chon == "Thẻ" else 0,
                }
            else:
                p1, p2, p3 = st.columns(3)
                with p1:
                    tm = st.number_input("Tiền mặt:", min_value=0, step=10000,
                                          value=can_tra, key="sc_hd_tm")
                    if tm > 0: st.caption(f"= {int(tm):,}đ".replace(",","."))
                with p2:
                    ck = st.number_input("Chuyển khoản:", min_value=0, step=10000,
                                          value=0, key="sc_hd_ck")
                    if ck > 0: st.caption(f"= {int(ck):,}đ".replace(",","."))
                with p3:
                    the = st.number_input("Thẻ:", min_value=0, step=10000,
                                           value=0, key="sc_hd_the")
                    if the > 0: st.caption(f"= {int(the):,}đ".replace(",","."))
                tong_pttt = tm + ck + the
                lech = tong_pttt - can_tra
                if lech != 0:
                    lech_label = f"Dư: +{lech:,}đ" if lech > 0 else f"Thiếu: {lech:,}đ"
                    st.warning(
                        f"Tổng cần trả: **{can_tra:,}đ** &nbsp;|&nbsp; "
                        f"Đã nhập: **{tong_pttt:,}đ** &nbsp;|&nbsp; {lech_label}".replace(",",".")
                    )
                pttt = {"tien_mat": tm, "chuyen_khoan": ck, "the": the}

            st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
            if st.button("✅ Tạo hóa đơn APSC", type="primary",
                          use_container_width=True, key="sc_hd_create",
                          disabled=ct_hd.empty):
                try:
                    apsc_ma = _tao_hoa_don_apsc(dict(phieu_hd), ct_hd, giam_gia, pttt)
                    supabase.table("phieu_sua_chua").update({
                        "trang_thai": "Hoàn thành",
                        "updated_at": (datetime.now() + timedelta(hours=7)).isoformat(),
                    }).eq("ma_phieu", ma_hd_pick).execute()
                    st.cache_data.clear()
                    log_action("SC_HOA_DON", f"ma={ma_hd_pick} apsc={apsc_ma}")
                    st.success(f"✓ Đã tạo hóa đơn **{apsc_ma}** — phiếu chuyển sang Hoàn thành!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi tạo hóa đơn: {e}")

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_hoa_don_unified, \
    load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder, \
    load_psc_for_apsc
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
from utils.hd_style import (
    inject_hoa_don_css,
    list_card_html, detail_rail_html, empty_rail_html,
    smart_search_predicate,
    fmt_money, short_time,
)

# Prefix helpers — import pattern giống bao_cao.py
PDT_PREFIXES = ["AHDD"]
POS_PREFIXES = ["AHD"]
APSC_PREFIXES = ["APSC"]


def _is_pdt_hd(ma: str) -> bool:
    return any(str(ma).startswith(p) for p in PDT_PREFIXES)


def _is_pos_hd(ma: str) -> bool:
    s = str(ma)
    if any(s.startswith(p) for p in PDT_PREFIXES):
        return False
    return any(s.startswith(p) for p in POS_PREFIXES)


def _is_apsc_hd(ma: str) -> bool:
    return any(str(ma).startswith(p) for p in APSC_PREFIXES)


NGUOI_BAN_COLS = ["Người bán", "Nhân viên bán", "Người tạo", "Nhân viên"]


def _items_from_rows(rows: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in rows.iterrows():
        out.append({
            "ma":  str(r.get("Mã hàng", "") or ""),
            "ten": str(r.get("Tên hàng", "") or ""),
            "sl":  int(r.get("Số lượng", 0) or 0),
            "dg":  int(r.get("Đơn giá", 0) or 0),
            "tt":  int(r.get("Thành tiền", 0) or 0),
        })
    return out


def _build_invoice_dicts(df: pd.DataFrame) -> list[dict]:
    """Group dataframe theo Mã hóa đơn → list inv dicts cho list_card_html
    và detail_rail_html. inv["psc"] là dict|None (1:1)."""
    if df.empty:
        return []

    nb_col = None
    for col in NGUOI_BAN_COLS:
        if col in df.columns:
            nb_col = col
            break

    out = []
    for ma, grp in df.groupby("Mã hóa đơn", sort=False):
        head = grp.iloc[0]
        is_pdt = _is_pdt_hd(ma)
        is_apsc = _is_apsc_hd(ma)
        kenh = str(head.get("Kênh bán", "") or ("POS" if str(ma).startswith("AHD") else ""))
        loai = "Đổi/Trả" if is_pdt else ("Sửa chữa" if is_apsc else "")

        pttt = {}
        for src, key in [("Tiền mặt", "tm"), ("Chuyển khoản", "ck"),
                         ("Thẻ", "the"), ("Ví", "vi")]:
            if src in grp.columns:
                v = float(head.get(src, 0) or 0)
                if v > 0:
                    pttt[key] = v

        inv = {
            "ma": ma,
            "tg": str(head.get("Thời gian", "")),
            "kenh": kenh, "loai": loai,
            "status": str(head.get("Trạng thái", "Hoàn thành")),
            "khach": str(head.get("Tên khách hàng", "") or "Khách lẻ"),
            "sdt":   str(head.get("Điện thoại", "") or "").strip(),
            "nv":    str(head.get(nb_col, "") or "").strip() if nb_col else "",
            "pttt":  pttt,
            "tong":  int(head.get("Tổng tiền hàng", 0) or 0),
            "giam":  int(head.get("Giảm giá hóa đơn", 0) or 0),
            "tra":   int(head.get("Khách đã trả", 0) or 0),
        }

        if is_pdt:
            inv["chenh"] = int(head.get("_pdt_chenh_lech", head.get("Khách đã trả", 0)) or 0)
            tra_rows = grp[grp.get("_pdt_kieu", pd.Series(dtype=str)) == "tra"] \
                       if "_pdt_kieu" in grp.columns else pd.DataFrame()
            moi_rows = grp[grp.get("_pdt_kieu", pd.Series(dtype=str)) == "moi"] \
                       if "_pdt_kieu" in grp.columns else pd.DataFrame()
            inv["items_tra"] = _items_from_rows(tra_rows)
            inv["items_moi"] = _items_from_rows(moi_rows)
        else:
            inv["items"] = _items_from_rows(grp)

        if is_apsc:
            ma_ycsc = str(head.get("Mã YCSC", "") or "").strip()
            inv["psc"] = load_psc_for_apsc(ma_ycsc) if ma_ycsc else None

        out.append(inv)

    if "_ngay" in df.columns:
        order_map = dict(zip(df["Mã hóa đơn"],
                              pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")))
        out.sort(key=lambda x: order_map.get(x["ma"]) or pd.Timestamp.min, reverse=True)
    return out


def _trigger_print_invoice(inv: dict):
    st.toast("🖨 TODO: triển khai in HĐ ở phase 3", icon="🚧")


def _copy_invoice_to_clipboard(inv: dict):
    text = f"{inv['ma']} · {inv['tg']}\n{inv.get('khach', '')} · {inv.get('sdt', '')}\n"
    text += f"Tổng: {fmt_money(inv.get('tra', 0))}\n"
    for it in inv.get("items", []):
        text += f"  - {it['ten']} × {it['sl']} = {fmt_money(it['tt'])}\n"
    st.session_state["_hd_clipboard"] = text
    st.toast("📋 Đã sao chép HĐ (clipboard JS triển khai sau)", icon="✅")


def module_hoa_don():
    inject_hoa_don_css()

    try:
        active = get_active_branch()
        accessible = get_accessible_branches()

        # ── Branch picker (giữ nguyên logic) ─────────────────────────
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_filter = st.selectbox(
                "Chi nhánh:", ["Tất cả"] + accessible,
                index=(accessible.index(active) + 1) if active in accessible else 0,
                key="hd_cn", label_visibility="collapsed",
            )
            load_cns = tuple(accessible) if cn_filter == "Tất cả" else (cn_filter,)
        else:
            load_cns = (active,)
            st.caption(f"📍 {active}")

        # ── Load data (giữ nguyên) ───────────────────────────────────
        raw = load_hoa_don_unified(branches_key=load_cns)
        if raw.empty:
            st.info("Chưa có dữ liệu hóa đơn."); return

        if st.session_state.get("so_dong_trung", 0) > 0:
            st.caption(f"⚠ {st.session_state['so_dong_trung']} dòng trùng đã lọc.")

        data = raw.copy()
        data["SĐT_Search"] = data["Điện thoại"].fillna("").str.replace(r"\D+", "", regex=True)

        # ── Distinct NV list ─────────────────────────────────────────
        nv_options = ["Tất cả NV"]
        for col in NGUOI_BAN_COLS:
            if col in data.columns:
                nv_options += sorted([n for n in data[col].dropna().astype(str).unique()
                                      if n.strip() and n.strip().lower() != "nan"])
                break

        # ── Title row ────────────────────────────────────────────────
        import datetime as _dt
        _wd = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        _now = _dt.datetime.now()
        title_l, title_r = st.columns([3, 1])
        with title_l:
            st.html(
                f'<h2 style="font-size:22px;font-weight:600;letter-spacing:-.2px;'
                f'margin:0 0 10px;font-family:Be Vietnam Pro,system-ui,sans-serif;">'
                f'Hoá đơn · {_wd[_now.weekday()]} {_now.strftime("%d/%m/%Y")}</h2>'
            )
        with title_r:
            st.caption(f"{data['Mã hóa đơn'].nunique()} chứng từ")

        # ── Filter container (thay 3 sub-tab cũ) ─────────────────────
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 1])
            with c1:
                keyword = st.text_input(
                    "Tìm kiếm", key="hd_search",
                    placeholder="Tìm mã HĐ, số điện thoại, tên khách… (số→SĐT, chữ→tên)",
                    label_visibility="collapsed",
                )
            with c2:
                with st.popover("📅 Khoảng ngày", use_container_width=True):
                    d_from = st.date_input(
                        "Từ:", value=_now.date() - _dt.timedelta(days=7),
                        key="hd_date_from", format="DD/MM/YYYY",
                    )
                    d_to = st.date_input(
                        "Đến:", value=_now.date(),
                        key="hd_date_to", format="DD/MM/YYYY",
                    )
            with c3:
                sel_nv = st.selectbox("NV", nv_options, key="hd_filter_nv",
                                      label_visibility="collapsed")
            with c4:
                sel_pttt = st.selectbox(
                    "PTTT", ["Tất cả PTTT", "Tiền mặt", "CK", "Thẻ", "Ví"],
                    key="hd_filter_pttt", label_visibility="collapsed",
                )
            with c5:
                sel_loai = st.selectbox(
                    "Loại", ["Tất cả loại", "POS", "Đổi/Trả", "Sửa chữa", "KiotViet"],
                    key="hd_filter_loai", label_visibility="collapsed",
                )

            # Status segmented (radio horizontal — CSS biến thành seg)
            n_all    = data["Mã hóa đơn"].nunique()
            n_ok     = data[data["Trạng thái"] == "Hoàn thành"]["Mã hóa đơn"].nunique()
            n_cancel = data[data["Trạng thái"] == "Đã hủy"]["Mã hóa đơn"].nunique()
            n_pdt    = data[data["Mã hóa đơn"].apply(_is_pdt_hd)]["Mã hóa đơn"].nunique()
            n_apsc   = data[data["Mã hóa đơn"].apply(_is_apsc_hd)]["Mã hóa đơn"].nunique()
            sel_status = st.radio(
                "Trạng thái",
                [f"Tất cả ({n_all})", f"● Hoàn thành ({n_ok})", f"✕ Đã hủy ({n_cancel})",
                 f"↔ Đổi/Trả ({n_pdt})", f"🔧 Sửa chữa ({n_apsc})"],
                horizontal=True, label_visibility="collapsed", key="hd_filter_status",
            )

        # ── Apply filters ───────────────────────────────────────────
        filt = data.copy()

        if "_date" in filt.columns:
            filt = filt[filt["_date"].between(d_from, d_to)]
        else:
            _ngay = pd.to_datetime(filt["Thời gian"], dayfirst=True, errors="coerce").dt.date
            filt = filt[_ngay.between(d_from, d_to)]

        if keyword:
            pred = smart_search_predicate(keyword)
            mask = filt.apply(pred, axis=1)
            filt = filt[mask]

        if sel_nv != "Tất cả NV":
            for col in NGUOI_BAN_COLS:
                if col in filt.columns:
                    filt = filt[filt[col].astype(str).str.strip() == sel_nv]
                    break

        pttt_col_map = {"Tiền mặt": "Tiền mặt", "CK": "Chuyển khoản",
                        "Thẻ": "Thẻ", "Ví": "Ví"}
        if sel_pttt != "Tất cả PTTT" and sel_pttt in pttt_col_map:
            col = pttt_col_map[sel_pttt]
            if col in filt.columns:
                filt = filt[pd.to_numeric(filt[col], errors="coerce").fillna(0) > 0]

        if sel_loai == "POS":
            mask_kenh_pos = filt["Kênh bán"].fillna("") == "POS" \
                if "Kênh bán" in filt.columns else pd.Series(False, index=filt.index)
            filt = filt[mask_kenh_pos &
                        (~filt["Mã hóa đơn"].apply(_is_pdt_hd)) &
                        (~filt["Mã hóa đơn"].apply(_is_apsc_hd))]
        elif sel_loai == "Đổi/Trả":
            filt = filt[filt["Mã hóa đơn"].apply(_is_pdt_hd)]
        elif sel_loai == "Sửa chữa":
            filt = filt[filt["Mã hóa đơn"].apply(_is_apsc_hd)]
        elif sel_loai == "KiotViet":
            mask_kenh_pos = filt["Kênh bán"].fillna("") == "POS" \
                if "Kênh bán" in filt.columns else pd.Series(False, index=filt.index)
            filt = filt[(~mask_kenh_pos) & (~filt["Mã hóa đơn"].apply(_is_pdt_hd))]

        if "Hoàn thành" in sel_status:
            filt = filt[filt["Trạng thái"] == "Hoàn thành"]
        elif "Đã hủy" in sel_status:
            filt = filt[filt["Trạng thái"] == "Đã hủy"]
        elif "Đổi/Trả" in sel_status:
            filt = filt[filt["Mã hóa đơn"].apply(_is_pdt_hd)]
        elif "Sửa chữa" in sel_status:
            filt = filt[filt["Mã hóa đơn"].apply(_is_apsc_hd)]

        # ── Master-detail grid ──────────────────────────────────────
        if filt.empty:
            st.warning("🔍 Không tìm thấy chứng từ phù hợp")
            return

        invoices = _build_invoice_dicts(filt)
        sel_ma = st.session_state.get("hd_sel_ma")
        if sel_ma and sel_ma not in {i["ma"] for i in invoices}:
            sel_ma = None
            st.session_state.pop("hd_sel_ma", None)

        col_list, col_rail = st.columns([6, 4], gap="medium")
        with col_list:
            for inv in invoices:
                is_sel = inv["ma"] == sel_ma
                st.html(list_card_html(inv, selected=is_sel))
                if st.button("Xem chi tiết →", key=f"hd_open_{inv['ma']}",
                             use_container_width=True,
                             type="primary" if is_sel else "secondary"):
                    st.session_state["hd_sel_ma"] = inv["ma"]
                    st.rerun()

        with col_rail:
            if sel_ma:
                sel_inv = next((i for i in invoices if i["ma"] == sel_ma), None)
                if sel_inv:
                    st.html(detail_rail_html(sel_inv))
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("🖨 In lại", key=f"hd_print_{sel_ma}",
                                     use_container_width=True, type="primary"):
                            _trigger_print_invoice(sel_inv)
                    with b2:
                        if st.button("⎘ Sao chép", key=f"hd_copy_{sel_ma}",
                                     use_container_width=True):
                            _copy_invoice_to_clipboard(sel_inv)
                    with b3:
                        if st.button("⤴ Phiếu kho", key=f"hd_kho_{sel_ma}",
                                     use_container_width=True):
                            st.toast("TODO: link to phiếu kho", icon="🚧")
            else:
                st.html(empty_rail_html())

    except Exception as e:
        st.error(f"Lỗi: {e}")


# ==========================================
# MODULE: HÀNG HÓA
# ==========================================

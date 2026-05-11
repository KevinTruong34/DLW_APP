"""
Module Chuyển hàng — Master-Detail UX (Streamlit-thuần).

Refactor v16.1:
- Bỏ custom React/Babel iframe (quá nặng, lag, freeze khi rerun).
- Master-detail dùng `st.dataframe` row-select + `st.dialog` cho actions.
- Backend (RPC, race-retry mã phiếu, log_action, cache_data.clear): GIỮ NGUYÊN.

State flow:
- ch_query/ch_period/ch_branch/ch_status: filter values.
- ch_page: current page (pagination).
- _ch_dialog_for: ma_phieu vừa được mở detail (dedup row-select rerun).
- _ch_open_edit / _ch_open_receive / _ch_open_cancel: handoff giữa các dialog
  (chỉ mở 1 dialog/run trong Streamlit, nên detail close → flag set → main run
  mở dialog kế tiếp).
- ck_items / _ck_loaded_for: giỏ hàng cho create/edit dialog.
"""
import streamlit as st
import pandas as pd
import uuid
from datetime import datetime, timedelta

from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, _logger, log_action, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, get_gia_ban_map
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
from utils.helpers import _normalize, now_vn_iso

PHIEU_PER_PAGE = 20
SUGGEST_LIMIT  = 6

STATUS_EMOJI = {
    "Phiếu tạm":   "🟡",
    "Đang chuyển": "🔵",
    "Đã nhận":     "🟢",
    "Đã hủy":      "🔴",
}


# ════════════════════════════════════════════════════════════════
# BACKEND HELPERS — RPC + race-retry mã phiếu (giữ nguyên hành vi)
# ════════════════════════════════════════════════════════════════

def _gen_ma_phieu() -> str:
    """Sinh mã CH###### kế tiếp; fallback random nếu DB lỗi."""
    try:
        res = supabase.table("phieu_chuyen_kho") \
            .select("ma_phieu") \
            .like("ma_phieu", "CH______") \
            .order("ma_phieu", desc=True) \
            .limit(1) \
            .execute()
        if res.data:
            last_ma = res.data[0]["ma_phieu"]
            try:
                last_num = int(last_ma[2:])
            except (ValueError, IndexError):
                last_num = 0
        else:
            last_num = 0
        return f"CH{last_num + 1:06d}"
    except Exception:
        return f"CH{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:4].upper()}"


def _delete_phieu_rows(ma_phieu: str):
    supabase.table("phieu_chuyen_kho").delete().eq("ma_phieu", ma_phieu).execute()


def _insert_phieu_rows(records: list[dict]):
    supabase.table("phieu_chuyen_kho").insert(records).execute()


def _nhan_hang_rpc(ma_phieu: str, nguoi_nhan: str = "") -> tuple[bool, str]:
    try:
        res = supabase.rpc("nhan_hang", {
            "p_ma_phieu":   ma_phieu,
            "p_nguoi_nhan": nguoi_nhan,
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0]
        if result.get("ok"):
            return True, ""
        return False, result.get("error", "Lỗi không xác định")
    except Exception as e:
        return False, str(e)


def _xac_nhan_chuyen_rpc(ma_phieu: str) -> tuple[bool, str]:
    try:
        res = supabase.rpc("xac_nhan_chuyen_hang", {"p_ma_phieu": ma_phieu}).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0]
        if result.get("ok"):
            return True, ""
        return False, result.get("error", "Lỗi không xác định")
    except Exception as e:
        return False, str(e)


def _huy_phieu_rpc(ma_phieu: str, huy_boi: str) -> tuple[bool, dict, str]:
    try:
        res = supabase.rpc("huy_phieu_chuyen_kho", {
            "p_ma_phieu": ma_phieu,
            "p_huy_boi":  huy_boi,
        }).execute()
        result = res.data if isinstance(res.data, dict) else (res.data or {})
        if not result.get("ok"):
            return False, {}, result.get("error", "Lỗi không xác định")
        return True, result, ""
    except Exception as e:
        return False, {}, str(e)


def _build_records(ma: str, tu_cn: str, toi_cn: str, nguoi_tao: str,
                   ghi_chu: str, items: list[dict], now_iso: str) -> list[dict]:
    """Build records để insert vào table phieu_chuyen_kho (1 row/item)."""
    tong_sl   = sum(int(it["so_luong"]) for it in items)
    tong_mat  = len(items)
    tong_gtri = sum(int(it["so_luong"]) * int(it["gia_ban"]) for it in items)
    return [{
        "ma_phieu":          ma,
        "loai_phieu":        IN_APP_MARKER,
        "tu_chi_nhanh":      tu_cn,
        "toi_chi_nhanh":     toi_cn,
        "ngay_chuyen":       now_iso,
        "ngay_nhan":         None,
        "nguoi_tao":         nguoi_tao,
        "ghi_chu_chuyen":    ghi_chu or None,
        "ghi_chu_nhan":      None,
        "tong_sl_chuyen":    tong_sl,
        "tong_sl_nhan":      0,
        "tong_gia_tri":      int(tong_gtri),
        "tong_mat_hang":     tong_mat,
        "trang_thai":        "Phiếu tạm",
        "ma_hang":           str(it["ma_hang"]),
        "ma_vach":           None,
        "ten_hang":          str(it["ten_hang"]),
        "thuong_hieu":       None,
        "so_luong_chuyen":   int(it["so_luong"]),
        "so_luong_nhan":     0,
        "gia_chuyen":        int(it["gia_ban"]),
        "thanh_tien_chuyen": int(it["so_luong"]) * int(it["gia_ban"]),
        "thanh_tien_nhan":   0,
    } for it in items]


# ════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ════════════════════════════════════════════════════════════════

def _fmt_money_short(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f} tr đ"
    return f"{n:,} đ".replace(",", ".")


def _fmt_branch(b: str) -> str:
    return CN_SHORT.get(b, b)


def _clean_str(v) -> str:
    s = str(v or "").strip()
    return "" if s.lower() in ("nan", "none") else s


def _format_date_label(d) -> str:
    """Format date label cho group header: HÔM NAY / HÔM QUA / THỨ X, dd/mm/yyyy."""
    today = datetime.now().date()
    if d == today:
        return "HÔM NAY"
    if d == today - timedelta(days=1):
        return "HÔM QUA"
    weekdays = ["THỨ HAI", "THỨ BA", "THỨ TƯ", "THỨ NĂM",
                "THỨ SÁU", "THỨ BẢY", "CHỦ NHẬT"]
    return f"{weekdays[d.weekday()]}, {d.strftime('%d/%m/%Y')}"


def _apply_filters(df_all: pd.DataFrame, query: str, period: str, branch: str,
                   status: str, first_month, first_last) -> pd.DataFrame:
    df = df_all.copy()
    if period == "Tháng này":
        df = df[df["_date"] >= first_month]
    elif period == "Tháng trước":
        last_end = first_month - timedelta(days=1)
        df = df[(df["_date"] >= first_last) & (df["_date"] <= last_end)]
    if branch != "Tất cả":
        df = df[(df["tu_chi_nhanh"] == branch) | (df["toi_chi_nhanh"] == branch)]
    if status == "Tất cả (trừ phiếu hủy)":
        df = df[df["trang_thai"] != "Đã hủy"]
    elif status != "Tất cả":
        df = df[df["trang_thai"] == status]
    if query.strip():
        q = _normalize(query)
        masks = []
        for col in ["ma_phieu", "tu_chi_nhanh", "toi_chi_nhanh",
                    "nguoi_tao", "nguoi_nhan", "ghi_chu_chuyen",
                    "ten_hang", "ma_hang"]:
            if col in df.columns:
                masks.append(df[col].apply(lambda x: q in _normalize(str(x or ""))))
        if masks:
            combined = masks[0]
            for m in masks[1:]:
                combined = combined | m
            keep = df.loc[combined, "ma_phieu"].unique()
            df = df[df["ma_phieu"].isin(keep)]
    return df


def _build_display_df(df: pd.DataFrame, gia_map: dict) -> pd.DataFrame:
    """Build dataframe để hiển thị — 1 row/phiếu. Cột `_date_key` ẩn dùng để group."""
    if df.empty:
        return pd.DataFrame()
    rows = []
    for ma, grp in df.groupby("ma_phieu"):
        head = grp.iloc[0]
        try:
            ts = pd.Timestamp(head["ngay_chuyen"])
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            ts_vn = ts.tz_convert("Asia/Ho_Chi_Minh")
            time_str = ts_vn.strftime("%H:%M")
            date_key = ts_vn.date()
            ts_sort = ts_vn
        except Exception:
            time_str = ""
            date_key = None
            ts_sort = None
        tu = _clean_str(head.get("tu_chi_nhanh"))
        toi = _clean_str(head.get("toi_chi_nhanh"))
        tt = _clean_str(head.get("trang_thai"))
        tong_sl = int(head.get("tong_sl_chuyen", 0) or 0)
        n_mat = int(head.get("tong_mat_hang", 0) or len(grp))
        tot_gia = 0
        for _, r in grp.iterrows():
            slc = int(r.get("so_luong_chuyen", 0) or 0)
            gb  = int(r.get("gia_chuyen") or gia_map.get(str(r.get("ma_hang", "")), 0) or 0)
            tot_gia += slc * gb
        rows.append({
            "_sort": ts_sort,
            "_date_key": date_key,
            "Mã phiếu":   ma,
            "Giờ":        time_str,
            "Chi nhánh":  f"{_fmt_branch(tu)} → {_fmt_branch(toi)}",
            "Mặt hàng":   f"{n_mat} mục · {tong_sl} SL",
            "Giá trị":    _fmt_money_short(tot_gia),
            "Người tạo":  _clean_str(head.get("nguoi_tao")),
            "Trạng thái": f"{STATUS_EMOJI.get(tt, '')} {tt}".strip(),
        })
    res = pd.DataFrame(rows).sort_values("_sort", ascending=False, na_position="last") \
        .drop(columns=["_sort"]).reset_index(drop=True)
    return res


# ════════════════════════════════════════════════════════════════
# DIALOGS
# ════════════════════════════════════════════════════════════════

@st.dialog("Chi tiết phiếu", width="large")
def _dlg_detail(ma_phieu: str, df_phieu: pd.DataFrame):
    active = get_active_branch()
    head = df_phieu.iloc[0]
    tu  = _clean_str(head.get("tu_chi_nhanh"))
    toi = _clean_str(head.get("toi_chi_nhanh"))
    tt  = _clean_str(head.get("trang_thai"))
    nguoi_tao    = _clean_str(head.get("nguoi_tao"))
    nguoi_nhan   = _clean_str(head.get("nguoi_nhan"))
    ghi_chu      = _clean_str(head.get("ghi_chu_chuyen"))
    ghi_chu_nhan = _clean_str(head.get("ghi_chu_nhan"))
    loai_phieu   = _clean_str(head.get("loai_phieu"))
    archived     = (loai_phieu == ARCHIVED_MARKER)

    try:
        ts = pd.Timestamp(head["ngay_chuyen"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        date_str = ts.tz_convert("Asia/Ho_Chi_Minh").strftime("%d/%m/%Y %H:%M")
    except Exception:
        date_str = ""

    # Header
    arch_tag = " · 📦 Kết sổ" if archived and tt != "Đã hủy" else ""
    st.markdown(
        f"#### `{ma_phieu}` &nbsp; {STATUS_EMOJI.get(tt, '')} {tt}{arch_tag}\n\n"
        f":blue[**{tu}**] → :green[**{toi}**]  \n"
        f":gray[{date_str}]"
    )

    # Meta
    cols = st.columns(2)
    cols[0].markdown(f":gray[👤 Người gửi/tạo:] **{nguoi_tao or '—'}**")
    cols[1].markdown(f":gray[📥 Người nhận:] **{nguoi_nhan or 'Chưa nhận'}**")

    if ghi_chu:
        st.info(f"**Ghi chú chuyển:** {ghi_chu}", icon="📝")
    if ghi_chu_nhan:
        st.success(f"**Ghi chú nhận:** {ghi_chu_nhan}", icon="📥")

    # Items
    st.markdown("**Danh sách hàng chuyển**")
    items_df = df_phieu[["ten_hang", "ma_hang", "so_luong_chuyen",
                         "so_luong_nhan", "gia_chuyen"]].copy()
    items_df["Thành tiền"] = (
        items_df["so_luong_chuyen"].astype(int) * items_df["gia_chuyen"].astype(int)
    )
    show_recv = tt in ("Đang chuyển", "Đã nhận", "Đã hủy")
    cols_show = ["ten_hang", "ma_hang", "so_luong_chuyen"]
    if show_recv:
        cols_show.append("so_luong_nhan")
    cols_show.append("Thành tiền")
    items_show = items_df[cols_show].rename(columns={
        "ten_hang":         "Tên hàng",
        "ma_hang":          "Mã hàng",
        "so_luong_chuyen":  "SL chuyển",
        "so_luong_nhan":    "SL nhận",
    })
    st.dataframe(items_show, use_container_width=True, hide_index=True,
                 height=min(280, 42 + len(items_show) * 35))

    # Totals
    tong_sl = int(head.get("tong_sl_chuyen", 0) or 0)
    tong_recv = int(df_phieu["so_luong_nhan"].fillna(0).astype(int).sum()) if "so_luong_nhan" in df_phieu.columns else 0
    tong_gia = int(items_df["Thành tiền"].sum())
    cols = st.columns(3)
    cols[0].metric("Mặt hàng", len(items_df))
    cols[1].metric(
        "Tổng SL",
        f"{tong_sl:,}".replace(",", "."),
        delta=(f"nhận {tong_recv}" if tt == "Đã nhận" and tong_recv != tong_sl else None),
        delta_color="inverse",
    )
    cols[2].metric("Tổng giá trị", _fmt_money_short(tong_gia))

    # Action eligibility
    can_edit_or_confirm = tt == "Phiếu tạm" and active == tu
    can_receive         = tt == "Đang chuyển" and active == toi
    can_cancel          = is_admin() and tt not in ("Đã nhận", "Đã hủy")

    st.divider()

    if can_edit_or_confirm:
        col_a, col_b = st.columns([1, 2])
        if col_a.button("✏ Sửa phiếu", use_container_width=True, key=f"d_edit_{ma_phieu}"):
            st.session_state["_ch_open_edit"] = ma_phieu
            st.rerun()
        if col_b.button("🚚 Xác nhận chuyển hàng", type="primary",
                        use_container_width=True, key=f"d_conf_{ma_phieu}"):
            with st.spinner("Đang xác nhận..."):
                ok, err = _xac_nhan_chuyen_rpc(ma_phieu)
            if ok:
                log_action("PHIEU_CONFIRM", f"ma={ma_phieu} tu={tu} toi={toi}")
                st.cache_data.clear()
                st.toast(f"✓ Đã xác nhận chuyển hàng cho {ma_phieu}", icon="✅")
                st.rerun()
            else:
                st.error(f"Không thể xác nhận: {err}")

    elif can_receive:
        if st.button("✓ Nhận hàng", type="primary",
                     use_container_width=True, key=f"d_recv_{ma_phieu}"):
            st.session_state["_ch_open_receive"] = ma_phieu
            st.rerun()

    if can_cancel:
        if st.button("🗑 Hủy phiếu", use_container_width=True, key=f"d_cancel_{ma_phieu}"):
            st.session_state["_ch_open_cancel"] = ma_phieu
            st.rerun()

    if not (can_edit_or_confirm or can_receive or can_cancel):
        if tt == "Phiếu tạm" and active != tu:
            st.caption(f"ℹ Để sửa/chuyển phiếu này, đổi sang chi nhánh **{tu}**")
        elif tt == "Đang chuyển" and active != toi:
            st.caption(f"ℹ Để nhận phiếu này, đổi sang chi nhánh **{toi}**")
        elif tt == "Đã nhận":
            st.caption("✓ Phiếu đã hoàn tất.")
        elif tt == "Đã hủy":
            st.caption("⊘ Phiếu đã hủy.")


@st.dialog("Tạo phiếu chuyển hàng", width="large")
def _dlg_create():
    _render_form(ma_phieu=None, df_phieu=None)


@st.dialog("Cập nhật phiếu", width="large")
def _dlg_edit(ma_phieu: str, df_phieu: pd.DataFrame):
    _render_form(ma_phieu=ma_phieu, df_phieu=df_phieu)


def _render_form(ma_phieu: str | None, df_phieu: pd.DataFrame | None):
    """Render form tạo/sửa phiếu. Cùng UI cho 2 chế độ."""
    is_edit = ma_phieu is not None
    user = get_user() or {}
    active = get_active_branch()

    # Init cart trong session_state — chỉ load lại khi mở dialog mới
    loaded_key = f"edit_{ma_phieu}" if is_edit else "create"
    if st.session_state.get("_ck_loaded_for") != loaded_key:
        if is_edit:
            gia_map = get_gia_ban_map()
            items = []
            for _, r in df_phieu.iterrows():
                mh = str(r.get("ma_hang", ""))
                gb = int(r.get("gia_chuyen") or gia_map.get(mh, 0) or 0)
                items.append({
                    "ma_hang":  mh,
                    "ten_hang": str(r.get("ten_hang", "")),
                    "so_luong": int(r.get("so_luong_chuyen", 0) or 0),
                    "gia_ban":  gb,
                })
            st.session_state["ck_items"] = items
            head = df_phieu.iloc[0]
            st.session_state["_ck_tu_cn"]   = _clean_str(head.get("tu_chi_nhanh"))
            st.session_state["_ck_toi_cn"]  = _clean_str(head.get("toi_chi_nhanh"))
            st.session_state["_ck_ng_init"] = _clean_str(head.get("nguoi_tao"))
            st.session_state["_ck_gc_init"] = _clean_str(head.get("ghi_chu_chuyen"))
        else:
            st.session_state["ck_items"]    = []
            st.session_state["_ck_tu_cn"]   = active
            st.session_state["_ck_toi_cn"]  = ""
            st.session_state["_ck_ng_init"] = user.get("ho_ten", "")
            st.session_state["_ck_gc_init"] = ""
        st.session_state["_ck_loaded_for"] = loaded_key

    if is_edit:
        st.warning(
            "🔄 Đang sửa phiếu — thay đổi chỉ áp dụng khi bấm **Lưu thay đổi**.",
            icon="✏️",
        )

    # ── Form fields ──
    cols = st.columns(2)
    with cols[0]:
        if is_edit:
            st.markdown(f":gray[Từ chi nhánh]\n\n**🔒 {st.session_state['_ck_tu_cn']}**")
            tu_cn = st.session_state["_ck_tu_cn"]
        elif is_admin():
            tu_options = ALL_BRANCHES
            tu_idx = tu_options.index(active) if active in tu_options else 0
            tu_cn = st.selectbox("Từ chi nhánh *", tu_options, index=tu_idx, key="ck_tu_cn_sel")
        else:
            st.markdown(f":gray[Từ chi nhánh]\n\n**📍 {active}**")
            tu_cn = active
    with cols[1]:
        if is_edit:
            st.markdown(f":gray[Đến chi nhánh]\n\n**🔒 {st.session_state['_ck_toi_cn']}**")
            toi_cn = st.session_state["_ck_toi_cn"]
        else:
            toi_options = ["— Chọn chi nhánh —"] + [b for b in ALL_BRANCHES if b != tu_cn]
            toi_sel = st.selectbox("Đến chi nhánh *", toi_options, key="ck_toi_cn_sel")
            toi_cn = "" if toi_sel == "— Chọn chi nhánh —" else toi_sel

    cols = st.columns([1, 2])
    nguoi_tao = cols[0].text_input(
        "Người gửi/tạo *",
        value=st.session_state.get("_ck_ng_init", ""),
        key="ck_ng_tao",
    )
    ghi_chu = cols[1].text_input(
        "Ghi chú",
        value=st.session_state.get("_ck_gc_init", ""),
        placeholder="VD: Chuyển bổ sung hàng tuần...",
        key="ck_ghi_chu",
    )

    st.divider()

    # ── Load tồn nguồn ──
    kho_src = load_the_kho(branches_key=(tu_cn,)) if tu_cn else pd.DataFrame()
    ton_map: dict[str, int] = {}
    if not kho_src.empty and "Mã hàng" in kho_src.columns:
        ton_map = dict(zip(
            kho_src["Mã hàng"].astype(str),
            kho_src["Tồn cuối kì"].fillna(0).astype(int),
        ))

    # ── Cart display ──
    items = st.session_state.get("ck_items", [])
    total_sl = 0
    total_gb = 0
    has_overflow = False

    st.markdown(f"**🛒 Giỏ hàng** ({len(items)} sản phẩm)")

    if not items:
        st.caption("Giỏ hàng trống. Tìm và thêm sản phẩm ở danh sách bên dưới.")
    else:
        for idx, it in enumerate(items):
            ton_src = int(ton_map.get(str(it["ma_hang"]), 0))
            c_info, c_sl, c_gia, c_del = st.columns([5, 2, 2, 1])
            with c_info:
                st.markdown(
                    f"**{it['ten_hang']}**  \n"
                    f":gray[`{it['ma_hang']}`] · :gray[Tồn nguồn: **{ton_src}**]"
                )
            with c_sl:
                new_sl = st.number_input(
                    "SL", min_value=1, max_value=99999,
                    value=int(it["so_luong"]), step=1,
                    key=f"ck_sl_{idx}", label_visibility="collapsed",
                )
                items[idx]["so_luong"] = int(new_sl)
            over = int(new_sl) > ton_src
            if over:
                has_overflow = True
            with c_gia:
                color = "red" if over else "gray"
                tien = int(new_sl) * int(it["gia_ban"])
                st.markdown(f":{color}[{tien:,}đ]".replace(",", "."))
            with c_del:
                if st.button("🗑", key=f"ck_del_{idx}", use_container_width=True,
                             help="Xóa khỏi giỏ"):
                    items.pop(idx)
                    st.session_state["ck_items"] = items
                    # Không gọi st.rerun() — sẽ đóng dialog. Streamlit tự rerun
                    # khi button click; cart re-render với items đã update.
            total_sl += int(new_sl)
            total_gb += int(new_sl) * int(it["gia_ban"])

        if has_overflow:
            st.error("⚠ Một số sản phẩm có SL chuyển vượt tồn nguồn. Sửa lại trước khi lưu.",
                     icon="⚠️")

        cols = st.columns(2)
        cols[0].metric("Tổng SL", f"{total_sl:,}".replace(",", "."))
        cols[1].metric("Tổng giá trị", _fmt_money_short(total_gb))

    st.divider()

    # ── Search & add ──
    # Luôn enforce "chỉ hàng còn tồn ở nguồn" — không cho phép chuyển hàng hết kho.
    st.markdown("**🔍 Thêm sản phẩm**")
    kw = st.text_input("Tìm", placeholder="Tìm theo mã, tên...",
                       key="ck_search", label_visibility="collapsed")

    hh = load_hang_hoa()
    if hh.empty:
        st.warning("Chưa có dữ liệu Hàng hóa master.")
    elif not kw.strip():
        # Không hiện gợi ý khi search trống — chỉ render kết quả khi user gõ.
        st.caption("Gõ mã/tên sản phẩm để tìm kiếm.")
    else:
        hh_list = hh.copy()
        hh_list["_ton_src"] = hh_list["ma_hang"].astype(str).map(ton_map).fillna(0).astype(int)
        kwn = _normalize(kw)
        hh_list["_n_ma"]  = hh_list["ma_hang"].apply(_normalize)
        hh_list["_n_ten"] = hh_list["ten_hang"].apply(_normalize)
        hh_list = hh_list[
            (hh_list["_n_ma"].str.contains(kwn, na=False) |
             hh_list["_n_ten"].str.contains(kwn, na=False))
            & (hh_list["_ton_src"] > 0)
        ]
        hh_list = hh_list.head(SUGGEST_LIMIT)

        if hh_list.empty:
            st.caption("Không tìm thấy sản phẩm còn tồn ở nguồn.")
        else:
            for _, r in hh_list.iterrows():
                mh     = str(r["ma_hang"])
                tn     = str(r["ten_hang"])
                gb     = int(r.get("gia_ban", 0) or 0)
                tn_src = int(r.get("_ton_src", 0) or 0)
                already = any(it["ma_hang"] == mh for it in items)
                c_info, c_btn = st.columns([5, 1])
                with c_info:
                    st.markdown(
                        f"**{tn}**  \n"
                        f":gray[`{mh}`] · :gray[Tồn: {tn_src}] · :green[{gb:,}đ]".replace(",", ".")
                    )
                with c_btn:
                    if already:
                        st.markdown(":green[✓ Đã thêm]")
                    else:
                        if st.button("➕", key=f"ck_add_{mh}", use_container_width=True):
                            items.append({
                                "ma_hang":  mh,
                                "ten_hang": tn,
                                "so_luong": 1,
                                "gia_ban":  gb,
                            })
                            st.session_state["ck_items"] = items
                            # Không gọi st.rerun() — đóng dialog. Button click tự rerun.

    # ── Validation + Submit ──
    st.divider()
    same_branch = tu_cn == toi_cn
    can_save = len(items) > 0 and nguoi_tao.strip() and not same_branch and not has_overflow and toi_cn

    if same_branch and toi_cn:
        st.error("⚠ Chi nhánh nguồn và đích phải khác nhau.")

    col_cancel, col_submit = st.columns([1, 2])
    if col_cancel.button("Hủy", use_container_width=True, key="ck_cancel_dlg"):
        _clear_cart_state()
        st.rerun()

    submit_label = "💾 Lưu thay đổi" if is_edit else "✓ Tạo phiếu chuyển"
    submit_disabled_msg = None
    if not can_save:
        if not toi_cn:
            submit_disabled_msg = "Chọn chi nhánh đích trước"
        elif not items:
            submit_disabled_msg = "Thêm ít nhất 1 mặt hàng"
        elif not nguoi_tao.strip():
            submit_disabled_msg = "Nhập tên người gửi"
        elif has_overflow:
            submit_disabled_msg = "Sửa SL vượt tồn trước"
        elif same_branch:
            submit_disabled_msg = "Chi nhánh nguồn ≠ đích"

    if col_submit.button(submit_label, type="primary", use_container_width=True,
                        disabled=not can_save, help=submit_disabled_msg,
                        key="ck_submit_dlg"):
        _submit_phieu(tu_cn, toi_cn, nguoi_tao.strip(), ghi_chu.strip(),
                      items, editing_ma=ma_phieu)


def _clear_cart_state():
    for k in ("ck_items", "_ck_loaded_for", "_ck_tu_cn", "_ck_toi_cn",
              "_ck_ng_init", "_ck_gc_init"):
        st.session_state.pop(k, None)


def _submit_phieu(tu_cn: str, toi_cn: str, nguoi_tao: str, ghi_chu: str,
                  items: list[dict], editing_ma: str | None = None):
    """Insert/Update phiếu. Race-retry mã phiếu khi tạo mới."""
    try:
        with st.spinner("Đang xử lý..."):
            now_iso = now_vn_iso()
            tong_sl = sum(int(it["so_luong"]) for it in items)
            tong_mat = len(items)

            if editing_ma:
                _delete_phieu_rows(editing_ma)
                _insert_phieu_rows(_build_records(editing_ma, tu_cn, toi_cn,
                                                  nguoi_tao, ghi_chu, items, now_iso))
                log_action("PHIEU_UPDATE",
                           f"ma={editing_ma} tu={tu_cn} toi={toi_cn} "
                           f"sl={tong_sl} items={tong_mat}")
                msg = f"💾 Đã cập nhật phiếu {editing_ma}"
            else:
                ma_phieu, last_err = None, None
                for attempt in range(3):
                    try_ma = _gen_ma_phieu()
                    try:
                        _insert_phieu_rows(_build_records(
                            try_ma, tu_cn, toi_cn, nguoi_tao, ghi_chu, items, now_iso
                        ))
                        ma_phieu = try_ma
                        break
                    except Exception as e:
                        last_err = e
                        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                            _logger.warning(f"PHIEU_RETRY — attempt={attempt+1} ma={try_ma}")
                            continue
                        raise
                if ma_phieu is None:
                    raise RuntimeError(f"Không sinh được mã phiếu sau 3 lần thử: {last_err}")
                tong_gtri = sum(int(it["so_luong"]) * int(it["gia_ban"]) for it in items)
                log_action("PHIEU_CREATE",
                           f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} sl={tong_sl} "
                           f"items={tong_mat} gtri={int(tong_gtri)}")
                msg = f"✓ Tạo phiếu {ma_phieu} thành công"

        _clear_cart_state()
        st.cache_data.clear()
        st.toast(msg, icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"Lỗi xử lý phiếu: {e}")


@st.dialog("Nhận hàng")
def _dlg_receive(ma_phieu: str, df_phieu: pd.DataFrame):
    head = df_phieu.iloc[0]
    tu  = _clean_str(head.get("tu_chi_nhanh"))
    toi = _clean_str(head.get("toi_chi_nhanh"))
    user = get_user() or {}
    default_nn = user.get("ho_ten", "")

    st.markdown(
        f"Phiếu `{ma_phieu}` · :blue[{tu}] → :green[{toi}]"
    )
    tong_sl = int(head.get("tong_sl_chuyen", 0) or 0)
    st.info(f"**Tổng SL chuyển:** {tong_sl:,}".replace(",", "."), icon="📦")

    nn = st.text_input("Người nhận *", value=default_nn,
                       placeholder="Tên người nhận hàng", key="rcv_nn")
    confirmed = st.checkbox("Tôi xác nhận đã kiểm tra và nhận đủ hàng",
                            key="rcv_confirm")

    col_a, col_b = st.columns([1, 2])
    if col_a.button("Hủy", use_container_width=True, key="rcv_cancel"):
        st.rerun()
    if col_b.button("✓ Xác nhận nhận hàng", type="primary",
                    use_container_width=True,
                    disabled=not (confirmed and nn.strip()),
                    help=None if (confirmed and nn.strip()) else "Tick xác nhận + nhập tên",
                    key="rcv_submit"):
        with st.spinner("Đang nhận hàng..."):
            ok, err = _nhan_hang_rpc(ma_phieu, nguoi_nhan=nn.strip())
        if ok:
            log_action("PHIEU_RECEIVE",
                       f"ma={ma_phieu} tu={tu} toi={toi} nguoi_nhan={nn.strip()}")
            st.cache_data.clear()
            st.toast(f"✓ Đã nhận hàng cho phiếu {ma_phieu}", icon="✅")
            st.rerun()
        else:
            st.error(f"Lỗi nhận hàng: {err}")


@st.dialog("Hủy phiếu chuyển?")
def _dlg_cancel(ma_phieu: str, df_phieu: pd.DataFrame):
    head = df_phieu.iloc[0]
    tt = _clean_str(head.get("trang_thai"))
    tu = _clean_str(head.get("tu_chi_nhanh"))

    if tt == "Đang chuyển":
        st.warning(
            f"Phiếu **{ma_phieu}** đang chuyển. Hủy phiếu sẽ **hoàn lại tồn kho** cho {tu}.",
            icon="⚠️",
        )
    else:
        st.markdown(
            f"Hủy phiếu **{ma_phieu}**? Thao tác này **không thể hoàn tác**."
        )

    col_a, col_b = st.columns([1, 2])
    if col_a.button("Đóng", use_container_width=True, key="cnc_close"):
        st.rerun()
    if col_b.button("🗑 Hủy phiếu", type="primary", use_container_width=True,
                    key="cnc_submit"):
        user = get_user() or {}
        huy_boi = user.get("ho_ten") or user.get("username") or "admin"
        with st.spinner("Đang hủy phiếu..."):
            ok, result, err = _huy_phieu_rpc(ma_phieu, huy_boi)
        if not ok:
            st.error(f"Không thể hủy: {err}")
            return
        prev = result.get("prev_status", "?")
        n_restored = result.get("items_restored", 0)
        st.cache_data.clear()
        if prev == "Đang chuyển" and n_restored > 0:
            st.toast(
                f"✓ Đã hủy {ma_phieu} — kho nguồn hoàn lại {n_restored} mặt hàng",
                icon="✅",
            )
        else:
            st.toast(f"✓ Đã hủy phiếu {ma_phieu}", icon="✅")
        st.rerun()


# ════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════

def module_chuyen_hang():
    try:
        active = get_active_branch()
        accessible = get_accessible_branches()
        view_cns = tuple(accessible) if is_ke_toan_or_admin() else (active,)
        df_all = load_phieu_chuyen_kho(branches_key=view_cns)

        # Filter bar
        st.markdown(
            f"##### 🔄 Chuyển hàng &nbsp; :gray[· đang xem từ] **{active}**"
        )
        cols = st.columns([3, 2, 2, 2, 1.5])
        with cols[0]:
            query = st.text_input(
                "Tìm",
                placeholder="🔍 Mã phiếu, sản phẩm, người tạo...",
                key="ch_query",
                label_visibility="collapsed",
            )
        with cols[1]:
            period = st.selectbox(
                "Kỳ",
                ["Tháng này", "Tháng trước", "Tất cả"],
                key="ch_period",
                label_visibility="collapsed",
            )
        with cols[2]:
            if is_ke_toan_or_admin() and len(accessible) > 1:
                branch_opts = ["Tất cả"] + accessible
                branch = st.selectbox(
                    "Chi nhánh", branch_opts, key="ch_branch",
                    label_visibility="collapsed",
                )
            else:
                branch = active
                st.caption(f"📍 {active}")
        with cols[3]:
            status_options = [
                "Tất cả (trừ phiếu hủy)",
                "Tất cả",
                "Phiếu tạm",
                "Đang chuyển",
                "Đã nhận",
                "Đã hủy",
            ]
            status = st.selectbox(
                "Trạng thái",
                status_options,
                index=0,
                key="ch_status",
                label_visibility="collapsed",
            )
        with cols[4]:
            create_clicked = st.button(
                "➕ Tạo phiếu",
                type="primary", use_container_width=True,
                key="ch_btn_create",
            )

        # ════════════════════════════════════════════════════════
        # RENDER LIST TRƯỚC, DIALOG OPEN SAU
        # — Tránh trang trắng khi user đóng dialog bằng X (rerun
        # đôi khi không trigger đúng nếu trước đó early-return).
        # — Bảo đảm chỉ 1 dialog mở mỗi run qua elif chain.
        # ════════════════════════════════════════════════════════

        detail_ma_candidate = None  # set bởi row selection (xử lý cuối cùng)

        if df_all.empty:
            st.info("Chưa có phiếu chuyển nào. Bấm **Tạo phiếu** để bắt đầu.")
        else:
            # Filtered df
            today = datetime.now().date()
            first_month = today.replace(day=1)
            first_last = (first_month - timedelta(days=1)).replace(day=1)
            df_filtered = _apply_filters(df_all, query, period, branch, status,
                                         first_month, first_last)

            # Summary metrics
            ma_unique = df_filtered["ma_phieu"].unique() if not df_filtered.empty else []
            total_count = len(ma_unique)
            df_unique_phieu = (df_filtered.drop_duplicates(subset=["ma_phieu"])
                                if not df_filtered.empty else df_filtered)
            total_sl = int(df_unique_phieu["tong_sl_chuyen"].fillna(0).astype(int).sum()) \
                if "tong_sl_chuyen" in df_unique_phieu.columns else 0
            total_gt = int(df_unique_phieu["tong_gia_tri"].fillna(0).astype(int).sum()) \
                if "tong_gia_tri" in df_unique_phieu.columns else 0

            m_cols = st.columns(3)
            m_cols[0].metric("Số phiếu trong kỳ", total_count)
            m_cols[1].metric("Tổng số lượng", f"{total_sl:,}".replace(",", "."))
            m_cols[2].metric("Tổng giá trị", _fmt_money_short(total_gt))

            if df_filtered.empty:
                st.info("Không có phiếu phù hợp bộ lọc.")
            else:
                # Pagination
                page_key = "ch_page"
                filter_sig = f"{query}|{period}|{branch}|{status}"
                if st.session_state.get("_ch_filter_sig") != filter_sig:
                    st.session_state["_ch_filter_sig"] = filter_sig
                    st.session_state[page_key] = 0
                page = int(st.session_state.get(page_key, 0))
                total_pages = max(1, (total_count + PHIEU_PER_PAGE - 1) // PHIEU_PER_PAGE)
                if page >= total_pages:
                    page = total_pages - 1
                if page < 0:
                    page = 0

                # Build display df (paginated)
                ma_sorted = (df_filtered.drop_duplicates(subset=["ma_phieu"])
                             .sort_values("_ngay", ascending=False)["ma_phieu"].tolist())
                start = page * PHIEU_PER_PAGE
                end = start + PHIEU_PER_PAGE
                ma_page = ma_sorted[start:end]
                df_page = df_filtered[df_filtered["ma_phieu"].isin(ma_page)]
                gia_map = get_gia_ban_map()
                display_df = _build_display_df(df_page, gia_map)

                # ─── Render group theo ngày ───
                # Mỗi group = 1 st.dataframe riêng với key unique theo date.
                # Selection state mỗi group độc lập; logic dưới chọn group
                # đang có selection MỚI (vs _ch_dialog_for) để mở detail.
                col_cfg = {
                    "Mã phiếu":   st.column_config.TextColumn(width="small"),
                    "Giờ":        st.column_config.TextColumn(width="small"),
                    "Chi nhánh":  st.column_config.TextColumn(width="medium"),
                    "Mặt hàng":   st.column_config.TextColumn(width="small"),
                    "Giá trị":    st.column_config.TextColumn(width="small"),
                    "Người tạo":  st.column_config.TextColumn(width="small"),
                    "Trạng thái": st.column_config.TextColumn(width="small"),
                }

                any_selection = False
                for date_key, group_df in display_df.groupby("_date_key", sort=False):
                    label = _format_date_label(date_key) if date_key else "—"
                    st.markdown(
                        f"<div style='font-size:0.78rem;font-weight:600;color:#888;"
                        f"margin:14px 0 4px;letter-spacing:0.5px;'>{label}</div>",
                        unsafe_allow_html=True,
                    )
                    grp_view = group_df.drop(columns=["_date_key"]).reset_index(drop=True)
                    grp_key = f"ch_list_{date_key.isoformat()}" if date_key else "ch_list_none"
                    sel = st.dataframe(
                        grp_view,
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                        height=42 + len(grp_view) * 36,
                        key=grp_key,
                        column_config=col_cfg,
                    )
                    sel_rows = (sel.selection.rows if hasattr(sel, "selection") else []) or []
                    if sel_rows:
                        any_selection = True
                        ma = grp_view.iloc[sel_rows[0]]["Mã phiếu"]
                        # Chỉ mở dialog cho NEW selection — first new wins.
                        if (detail_ma_candidate is None and
                                st.session_state.get("_ch_dialog_for") != ma):
                            detail_ma_candidate = ma

                # User bỏ chọn hết → reset dedup flag để có thể click lại
                if not any_selection:
                    st.session_state.pop("_ch_dialog_for", None)

                # Pagination controls
                if total_pages > 1:
                    col_l, col_m, col_r = st.columns([1, 2, 1])
                    if col_l.button("← Trước", disabled=(page == 0),
                                    use_container_width=True, key="ch_pg_prev"):
                        st.session_state[page_key] = page - 1
                        st.rerun()
                    col_m.markdown(
                        f"<div style='text-align:center;padding-top:6px;font-size:0.85rem;color:#666;'>"
                        f"Trang <b>{page+1}</b>/{total_pages} · "
                        f"{start+1}–{min(end, total_count)} / {total_count} phiếu</div>",
                        unsafe_allow_html=True,
                    )
                    if col_r.button("Sau →", disabled=(page >= total_pages - 1),
                                    use_container_width=True, key="ch_pg_next"):
                        st.session_state[page_key] = page + 1
                        st.rerun()

        # ════════════════════════════════════════════════════════
        # DIALOG DISPATCH — chỉ 1 dialog mở mỗi run (elif chain)
        # ════════════════════════════════════════════════════════
        edit_id = st.session_state.pop("_ch_open_edit", None)
        recv_id = st.session_state.pop("_ch_open_receive", None)
        cnc_id  = st.session_state.pop("_ch_open_cancel", None)

        if create_clicked:
            _clear_cart_state()
            _dlg_create()
        elif edit_id:
            df_phieu = df_all[df_all["ma_phieu"] == edit_id]
            if not df_phieu.empty:
                _clear_cart_state()
                _dlg_edit(edit_id, df_phieu)
        elif recv_id:
            df_phieu = df_all[df_all["ma_phieu"] == recv_id]
            if not df_phieu.empty:
                _dlg_receive(recv_id, df_phieu)
        elif cnc_id:
            df_phieu = df_all[df_all["ma_phieu"] == cnc_id]
            if not df_phieu.empty:
                _dlg_cancel(cnc_id, df_phieu)
        elif detail_ma_candidate:
            st.session_state["_ch_dialog_for"] = detail_ma_candidate
            df_phieu = df_all[df_all["ma_phieu"] == detail_ma_candidate]
            if not df_phieu.empty:
                _dlg_detail(detail_ma_candidate, df_phieu)

    except Exception as e:
        st.error(f"Lỗi tải Chuyển hàng: {e}")
        import traceback
        st.code(traceback.format_exc())

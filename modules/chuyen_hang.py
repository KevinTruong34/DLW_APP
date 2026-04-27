import streamlit as st
import pandas as pd
import uuid
from datetime import datetime, timedelta
import numpy as np

from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, _logger, log_action, load_hoa_don, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
from utils.helpers import _normalize

PHIEU_PER_PAGE = 20
SUGGEST_LIMIT  = 5

def _gen_ma_phieu() -> str:
    """
    Sinh mã phiếu serial tăng dần: CH000001, CH000002, ...
    Query max hiện tại trong DB rồi +1.

    Race condition: nếu 2 user tạo cùng lúc cùng ra 1 mã → INSERT lỗi
    do UNIQUE INDEX → _submit_phieu sẽ retry với mã mới.
    """
    try:
        # Lấy tất cả ma_phieu bắt đầu bằng "CH" + 6 số
        res = supabase.table("phieu_chuyen_kho") \
            .select("ma_phieu") \
            .like("ma_phieu", "CH______") \
            .order("ma_phieu", desc=True) \
            .limit(1) \
            .execute()

        if res.data:
            last_ma = res.data[0]["ma_phieu"]
            # Parse số từ "CH000123" → 123
            try:
                last_num = int(last_ma[2:])
            except (ValueError, IndexError):
                last_num = 0
        else:
            last_num = 0

        next_num = last_num + 1
        return f"CH{next_num:06d}"
    except Exception:
        # Fallback an toàn: nếu query fail, dùng timestamp (ít khả năng trùng)
        return f"CH{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:4].upper()}"


def _update_trang_thai_phieu(ma_phieu: str, trang_thai_moi: str,
                              extra: dict = None):
    """Cập nhật trạng thái (và các field liên quan) cho toàn bộ dòng của 1 phiếu."""
    payload = {"trang_thai": trang_thai_moi}
    if extra:
        payload.update(extra)
    supabase.table("phieu_chuyen_kho").update(payload) \
        .eq("ma_phieu", ma_phieu).execute()


def _delete_phieu_rows(ma_phieu: str):
    """Xóa tất cả dòng của một phiếu (dùng cho edit: DELETE + INSERT)."""
    supabase.table("phieu_chuyen_kho").delete() \
        .eq("ma_phieu", ma_phieu).execute()


def _nhan_hang(ma_phieu: str, nguoi_nhan: str = "") -> tuple[bool, str]:
    """Gọi RPC nhan_hang — atomic, an toàn race condition."""
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
        else:
            return False, result.get("error", "Lỗi không xác định")
    except Exception as e:
        return False, str(e)


def _view_phieu_chuyen(df_all: pd.DataFrame):
    """View danh sách phiếu chuyển kho với action buttons + pagination."""
    active     = get_active_branch()
    accessible = get_accessible_branches()

    # ── Filter bar ──
    col_ky, col_cn = st.columns([2, 2])
    with col_ky:
        ky = st.selectbox("Kỳ:", ["Tháng này","Tháng trước","Tất cả"],
            key="ck_ky", label_visibility="collapsed")
    with col_cn:
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_filter = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible,
                key="ck_cn", label_visibility="collapsed")
        else:
            cn_filter = active
            st.caption(f"📍 {active}")

    # Reset pagination về trang 1 nếu filter thay đổi
    filter_sig = f"{ky}|{cn_filter}"
    if st.session_state.get("_ck_last_filter") != filter_sig:
        st.session_state["_ck_last_filter"] = filter_sig
        st.session_state["ck_vpage"] = 0

    if df_all.empty:
        st.info("Chưa có dữ liệu chuyển hàng. Vào tab **Tạo phiếu** để tạo mới hoặc Quản trị → Upload.")
        return

    df = df_all.copy()

    today       = datetime.now().date()
    first_month = today.replace(day=1)
    first_last  = (first_month - timedelta(days=1)).replace(day=1)

    if ky == "Tháng này":
        df = df[df["_date"] >= first_month]
    elif ky == "Tháng trước":
        last_end = first_month - timedelta(days=1)
        df = df[(df["_date"] >= first_last) & (df["_date"] <= last_end)]

    if cn_filter != "Tất cả":
        df = df[(df["tu_chi_nhanh"] == cn_filter) | (df["toi_chi_nhanh"] == cn_filter)]

    if df.empty:
        st.info("Không có phiếu trong kỳ này.")
        return

    # Summary: số phiếu
    phieu_df = df.drop_duplicates(subset=["ma_phieu"], keep="first")
    so_phieu = len(phieu_df)
    st.metric("Số phiếu trong kỳ", str(so_phieu))

    # ── Pagination ──
    total_pages = max(1, (so_phieu + PHIEU_PER_PAGE - 1) // PHIEU_PER_PAGE)
    page = int(st.session_state.get("ck_vpage", 0))
    if page >= total_pages: page = total_pages - 1
    if page < 0: page = 0

    def _render_pager(pos: str):
        """Render thanh phân trang."""
        if total_pages <= 1: return
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("← Trước", key=f"pg_prev_{pos}",
                        disabled=(page == 0), use_container_width=True):
                st.session_state["ck_vpage"] = page - 1
                st.rerun()
        with c2:
            st.markdown(
                f"<div style='text-align:center;padding-top:6px;font-size:0.85rem;color:#666;'>"
                f"Trang <b>{page+1}</b>/{total_pages} · "
                f"Hiển thị {page*PHIEU_PER_PAGE + 1}"
                f"–{min((page+1)*PHIEU_PER_PAGE, so_phieu)} / {so_phieu} phiếu</div>",
                unsafe_allow_html=True
            )
        with c3:
            if st.button("Sau →", key=f"pg_next_{pos}",
                        disabled=(page >= total_pages - 1), use_container_width=True):
                st.session_state["ck_vpage"] = page + 1
                st.rerun()

    _render_pager("top")
    st.markdown("---")

    # Lấy mã phiếu trang hiện tại (theo thứ tự ngày giảm dần)
    phieu_sorted = phieu_df.sort_values("_ngay", ascending=False)
    start = page * PHIEU_PER_PAGE
    end   = start + PHIEU_PER_PAGE
    ma_phieu_page = phieu_sorted.iloc[start:end]["ma_phieu"].tolist()
    df_page = df[df["ma_phieu"].isin(ma_phieu_page)]

    # Map giá bán
    gia_ban_map = get_gia_ban_map()

    # ── Group by date ──
    dates = sorted(df_page["_date"].dropna().unique(), reverse=True)
    for dt in dates:
        df_day = df_page[df_page["_date"] == dt]
        phieu_day = [m for m in ma_phieu_page if m in df_day["ma_phieu"].values]

        today_dt = datetime.now().date()
        yest     = today_dt - timedelta(days=1)
        if dt == today_dt:   day_lbl = "HÔM NAY"
        elif dt == yest:     day_lbl = "HÔM QUA"
        else:
            try:
                weekday = ["THỨ HAI","THỨ BA","THỨ TƯ","THỨ NĂM",
                           "THỨ SÁU","THỨ BẢY","CHỦ NHẬT"][dt.weekday()]
                day_lbl = f"{weekday}, {dt.strftime('%d/%m/%Y')}"
            except Exception:
                day_lbl = dt.strftime("%d/%m/%Y")

        st.markdown(
            f"<div style='font-size:0.72rem;font-weight:700;color:#aaa;"
            f"letter-spacing:1px;margin:12px 0 6px;'>{day_lbl}</div>",
            unsafe_allow_html=True)

        for ma_phieu in phieu_day:
            df_phieu = df_day[df_day["ma_phieu"] == ma_phieu]
            _render_phieu_card(df_phieu, ma_phieu, gia_ban_map)

    st.markdown("---")
    _render_pager("bottom")


def _render_phieu_card(df_phieu: pd.DataFrame, ma_phieu: str, gia_ban_map: dict):
    """Render một phiếu chuyển trong expander với action buttons."""
    active    = get_active_branch()
    row_h     = df_phieu.iloc[0]

    tu_cn   = row_h.get("tu_chi_nhanh","")
    toi_cn  = row_h.get("toi_chi_nhanh","")
    tt      = str(row_h.get("trang_thai","") or "").strip()
    tsl     = int(row_h.get("tong_sl_chuyen", 0) or 0)
    tmat    = int(row_h.get("tong_mat_hang", 0) or 0)

    nguoi_tao      = str(row_h.get("nguoi_tao","") or "").strip()
    nguoi_nhan     = str(row_h.get("nguoi_nhan","") or "").strip()
    ghi_chu_chuyen = str(row_h.get("ghi_chu_chuyen","") or "").strip()
    ghi_chu_nhan   = str(row_h.get("ghi_chu_nhan","") or "").strip()
    for bad in ("nan", "None"):
        if nguoi_tao.lower() == bad.lower(): nguoi_tao = ""
        if nguoi_nhan.lower() == bad.lower(): nguoi_nhan = ""
        if ghi_chu_chuyen.lower() == bad.lower(): ghi_chu_chuyen = ""
        if ghi_chu_nhan.lower() == bad.lower(): ghi_chu_nhan = ""

    ngay_str = ""
    try:
        ngay_str = pd.Timestamp(row_h["ngay_chuyen"]).strftime("%d/%m %H:%M")
    except Exception:
        pass

    # Tổng giá bán
    total_gia_ban = 0
    for _, r in df_phieu.iterrows():
        mh  = str(r.get("ma_hang",""))
        slc = int(r.get("so_luong_chuyen", 0) or 0)
        gb  = gia_ban_map.get(mh, 0)
        total_gia_ban += slc * gb
    gia_str = (f"{total_gia_ban/1_000_000:.2f} tr đ" if total_gia_ban >= 1_000_000
               else f"{total_gia_ban:,} đ")

    # Màu trạng thái
    tt_colors = {
        "Phiếu tạm":   ("#856404", "#fff8e0"),
        "Đang chuyển": ("#0c5464", "#d1ecf1"),
        "Đã nhận":     ("#1a7f37", "#f0faf4"),
        "Đã hủy":      ("#721c24", "#f5d5d5"),
    }
    tt_color, tt_bg = tt_colors.get(tt, ("#555", "#f5f5f5"))

    # Phiếu tạo trong app = ảnh hưởng tồn kho
    loai_phieu = str(row_h.get("loai_phieu", "") or "")
    is_app_phieu      = (loai_phieu == IN_APP_MARKER)
    is_archived_phieu = (loai_phieu == ARCHIVED_MARKER)

    hang_list = df_phieu[["ten_hang","so_luong_chuyen"]].dropna().head(3)
    hang_str  = ", ".join(
        f"{r['ten_hang']} <b>x{int(r['so_luong_chuyen'])}</b>"
        for _, r in hang_list.iterrows()
    )
    if len(df_phieu) > 3:
        hang_str += f" <span style='color:#aaa;'>+{len(df_phieu)-3} khác</span>"

    # Expander title: hiện cả trạng thái
    title = (f"[{tt}] {tmat} mặt hàng · SL: {tsl}   —   {gia_str}")

    with st.expander(title, expanded=False):
        col_info, col_status = st.columns([4, 1])
        with col_info:
            tu_color  = "#2E86DE"
            toi_color = "#27AE60"
            st.markdown(
                f"<div style='font-size:0.88rem;'>"
                f"Từ <span style='color:{tu_color};font-weight:600;'>{tu_cn}</span>"
                f" → Đến <span style='color:{toi_color};font-weight:600;'>{toi_cn}</span>"
                f"</div>"
                f"<div style='font-size:0.78rem;color:#888;margin-top:3px;'>"
                f"{ngay_str} · {ma_phieu}</div>",
                unsafe_allow_html=True)
        with col_status:
            badge_parts = [
                f"<span style='background:{tt_bg};color:{tt_color};"
                f"padding:3px 10px;border-radius:20px;font-size:0.75rem;"
                f"font-weight:600;'>{tt}</span>"
            ]
            if is_app_phieu:
                badge_parts.append(
                    "<span style='background:#fff0f1;color:#e63946;"
                    "padding:3px 8px;border-radius:20px;font-size:0.7rem;"
                    "font-weight:600;margin-left:4px;'>📱 App</span>"
                )
            elif is_archived_phieu:
                badge_parts.append(
                    "<span style='background:#f0f0f0;color:#888;"
                    "padding:3px 8px;border-radius:20px;font-size:0.7rem;"
                    "font-weight:600;margin-left:4px;'>Kết sổ</span>"
                )
            st.markdown(
                f"<div style='text-align:right;margin-top:4px;'>"
                + "".join(badge_parts)
                + "</div>",
                unsafe_allow_html=True)

        # Người tạo / nhận + ghi chú
        info_parts = []
        if nguoi_tao:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:8px;'>"
                f"👤 <b>Người gửi/tạo phiếu:</b> {nguoi_tao}</div>")
        if nguoi_nhan:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:4px;'>"
                f"📥 <b>Người nhận:</b> {nguoi_nhan}</div>")
        if ghi_chu_chuyen:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:4px;'>"
                f"📝 <b>Ghi chú chuyển:</b> <span style='color:#666;'>{ghi_chu_chuyen}</span></div>")
        if ghi_chu_nhan:
            info_parts.append(
                f"<div style='font-size:0.82rem;color:#444;margin-top:4px;'>"
                f"📥 <b>Ghi chú nhận:</b> <span style='color:#666;'>{ghi_chu_nhan}</span></div>")
        if info_parts:
            st.markdown("".join(info_parts), unsafe_allow_html=True)

        # Tóm tắt + bảng chi tiết
        st.markdown(
            f"<div style='font-size:0.82rem;color:#444;margin:10px 0 4px;'>"
            f"<b>Tóm tắt:</b> {hang_str}</div>",
            unsafe_allow_html=True)

        cols_detail = ["ten_hang","ma_hang","so_luong_chuyen","so_luong_nhan"]
        cols_avail  = [c for c in cols_detail if c in df_phieu.columns]
        dv = df_phieu[cols_avail].copy()
        dv = dv.rename(columns={
            "ten_hang":"Tên hàng","ma_hang":"Mã hàng",
            "so_luong_chuyen":"SL chuyển","so_luong_nhan":"SL nhận"})
        st.dataframe(dv, use_container_width=True, hide_index=True,
                     height=min(200, 42 + len(dv)*35))

        # ══════ ACTION BUTTONS ══════
        st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
        actions = []

        # Sửa phiếu — chỉ khi Phiếu tạm + đang ở CN chuyển đi
        if tt == "Phiếu tạm" and active == tu_cn:
            actions.append(("sua", "✏ Sửa phiếu", "secondary"))
            actions.append(("xac_nhan", "🚚 Xác nhận chuyển hàng", "primary"))

        # Nhận hàng — chỉ khi Đang chuyển + đang ở CN nhận
        if tt == "Đang chuyển" and active == toi_cn:
            actions.append(("nhan", "✓ Nhận hàng", "primary"))

        # Hủy phiếu — admin only, khi chưa Đã nhận / Đã hủy
        if is_admin() and tt not in ("Đã nhận", "Đã hủy"):
            actions.append(("huy", "🗑 Hủy phiếu", "secondary"))

        if actions:
            cols = st.columns(len(actions))
            for i, (ac, label, btn_type) in enumerate(actions):
                with cols[i]:
                    if st.button(label, key=f"act_{ac}_{ma_phieu}",
                                type=btn_type, use_container_width=True):
                        _handle_action(ac, ma_phieu, df_phieu, tu_cn, toi_cn)

            # Form nhập người nhận (chỉ hiện khi đã bấm "Nhận hàng")
            if st.session_state.get(f"pending_nhan_{ma_phieu}"):
                st.markdown("---")
                # Auto-fill tên user hiện tại
                default_nn = (get_user() or {}).get("ho_ten", "")
                nn_key = f"nn_input_{ma_phieu}"
                if nn_key not in st.session_state:
                    st.session_state[nn_key] = default_nn
                st.text_input("Người nhận:", key=nn_key,
                             placeholder="Tên người nhận hàng")

                # Checkbox xác nhận — chống bấm nhầm
                chk_key = f"chk_nhan_{ma_phieu}"
                confirmed = st.checkbox(
                    "Tôi xác nhận đã kiểm tra và nhận đủ hàng",
                    key=chk_key
                )

                c_ok, c_cancel = st.columns([2, 1])
                with c_ok:
                    if st.button("✓ Xác nhận nhận hàng", ...):
                            nn = st.session_state.get(nn_key, "").strip()
                            if not nn:
                                st.error("Vui lòng nhập người nhận.")
                            else:
                                ok, err = _nhan_hang(ma_phieu, nguoi_nhan=nn)
                                if ok:
                                    st.cache_data.clear()
                                    log_action("PHIEU_RECEIVE",
                                              f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} nguoi_nhan={nn}")
                                    st.session_state.pop(f"pending_nhan_{ma_phieu}", None)
                                    st.session_state.pop(nn_key, None)
                                    st.session_state.pop(chk_key, None)
                                    st.success(f"✓ Đã nhận hàng cho phiếu {ma_phieu}")
                                    st.rerun()
                                else:
                                    st.error(f"Lỗi nhận hàng: {err}")
                with c_cancel:
                    if st.button("Hủy", key=f"cancel_nhan_{ma_phieu}",
                                use_container_width=True):
                        st.session_state.pop(f"pending_nhan_{ma_phieu}", None)
                        st.session_state.pop(nn_key, None)
                        st.session_state.pop(chk_key, None)
                        st.rerun()
        else:
            # Không có action nào khả dụng → hint
            if tt == "Phiếu tạm" and active != tu_cn:
                st.caption(f"ℹ Để sửa/chuyển phiếu này, đổi sang chi nhánh: **{tu_cn}**")
            elif tt == "Đang chuyển" and active != toi_cn:
                st.caption(f"ℹ Để nhận phiếu này, đổi sang chi nhánh: **{toi_cn}**")
            elif tt == "Đã nhận":
                st.caption("✓ Phiếu đã hoàn tất.")
            elif tt == "Đã hủy":
                st.caption("⊘ Phiếu đã hủy.")


def _handle_action(action: str, ma_phieu: str, df_phieu: pd.DataFrame,
                   tu_cn: str, toi_cn: str):
    """Xử lý các action trên phiếu."""
    try:
        if action == "xac_nhan":
            try:
                res = supabase.rpc("xac_nhan_chuyen_hang", {
                    "p_ma_phieu": ma_phieu,
                }).execute()
                result = res.data
                if isinstance(result, list):
                    result = result[0]
                if result.get("ok"):
                    st.cache_data.clear()
                    log_action("PHIEU_CONFIRM", f"ma={ma_phieu} tu={tu_cn} toi={toi_cn}")
                    st.success(f"✓ Đã xác nhận chuyển hàng cho phiếu {ma_phieu}")
                    st.rerun()
                else:
                    st.error(f"Không thể xác nhận: {result.get('error', 'Lỗi không xác định')}")
            except Exception as e:
                st.error(f"Lỗi: {e}")

        elif action == "nhan":
            # Không nhận ngay — set flag để form "Người nhận" hiện ra
            st.session_state[f"pending_nhan_{ma_phieu}"] = True
            st.rerun()

        elif action == "huy":
            _update_trang_thai_phieu(ma_phieu, "Đã hủy")
            st.cache_data.clear()
            log_action("PHIEU_CANCEL", f"ma={ma_phieu} tu={tu_cn} toi={toi_cn}",
                      level="warning")
            st.success(f"✓ Đã hủy phiếu {ma_phieu}")
            st.rerun()

        elif action == "sua":
            # Preload vào session state cho tab Tạo phiếu
            row_h = df_phieu.iloc[0]
            items = []
            gia_ban_map = get_gia_ban_map()
            for _, r in df_phieu.iterrows():
                mh = str(r.get("ma_hang",""))
                gb = int(r.get("gia_chuyen") or gia_ban_map.get(mh, 0))
                items.append({
                    "ma_hang":  mh,
                    "ten_hang": str(r.get("ten_hang","")),
                    "so_luong": int(r.get("so_luong_chuyen", 0) or 0),
                    "gia_ban":  gb,
                    "ton_src":  0,  # sẽ cập nhật sau
                })

            st.session_state["ck_editing"]     = ma_phieu
            st.session_state["ck_items"]       = items
            st.session_state["ck_edit_meta"]   = {
                "tu_cn":     tu_cn,
                "toi_cn":    toi_cn,
                "nguoi_tao": str(row_h.get("nguoi_tao","") or ""),
                "ghi_chu":   str(row_h.get("ghi_chu_chuyen","") or ""),
            }
            st.info(f"🔄 Đã tải phiếu **{ma_phieu}** vào chế độ sửa. "
                   "Vui lòng chuyển sang tab **➕ Tạo / Sửa phiếu** ở trên.")
    except Exception as e:
        st.error(f"Lỗi thao tác: {e}")


def _tao_phieu_chuyen():
    """Tab tạo phiếu chuyển mới / sửa phiếu."""
    user   = get_user()
    active = get_active_branch()

    # ── Kiểm tra edit mode ──
    editing_ma = st.session_state.get("ck_editing")
    edit_meta  = st.session_state.get("ck_edit_meta", {}) if editing_ma else {}

    if editing_ma:
        st.markdown(
            f"<div style='background:#fff8e0;border:1px solid #f0c36d;"
            f"border-radius:10px;padding:12px 14px;margin-bottom:10px;'>"
            f"<b style='color:#856404;'>🔄 Đang sửa phiếu: {editing_ma}</b><br>"
            f"<span style='font-size:0.82rem;color:#666;'>"
            f"Nhấn 'Hủy sửa' để thoát, hoặc 'Cập nhật phiếu' để lưu thay đổi.</span>"
            f"</div>",
            unsafe_allow_html=True
        )
        if st.button("✕ Hủy sửa (quay về tạo mới)", key="ck_cancel_edit"):
            st.session_state.pop("ck_editing", None)
            st.session_state.pop("ck_edit_meta", None)
            st.session_state["ck_items"] = []
            st.rerun()
    else:
        st.markdown(
            "<div style='font-size:0.95rem;font-weight:700;margin-bottom:6px;'>"
            "Tạo phiếu chuyển hàng mới</div>",
            unsafe_allow_html=True
        )

    # Load master
    hh = load_hang_hoa()
    if hh.empty:
        st.warning("Chưa có dữ liệu Hàng hóa master. Vui lòng upload trong Quản trị.")
        return

    # ══════ META INFO (từ/đến/người/ghi chú) ══════
    col_tu, col_toi = st.columns(2)
    with col_tu:
        # Từ CN: luôn hiển thị CN hiện tại (không dùng widget có key để tránh lỗi kẹt)
        if is_admin() and not editing_ma:
            tu_cn = st.selectbox("Từ chi nhánh:", ALL_BRANCHES,
                index=ALL_BRANCHES.index(active) if active in ALL_BRANCHES else 0,
                key="ck_tu_cn_sel")
        elif editing_ma:
            tu_cn = edit_meta.get("tu_cn", active)
            st.markdown(
                f"<div style='padding:4px 0;'>"
                f"<div style='font-size:0.82rem;color:#555;margin-bottom:2px;'>Từ chi nhánh</div>"
                f"<div style='background:#f4f6fa;border:1px solid #e0e0e0;"
                f"border-radius:8px;padding:8px 12px;color:#888;'>"
                f"🔒 {tu_cn}</div></div>",
                unsafe_allow_html=True
            )
        else:
            # Role nhan_vien/ke_toan: dùng markdown (không phải widget) để luôn hiện active
            tu_cn = active
            st.markdown(
                f"<div style='padding:4px 0;'>"
                f"<div style='font-size:0.82rem;color:#555;margin-bottom:2px;'>Từ chi nhánh</div>"
                f"<div style='background:#f4f6fa;border:1px solid #e0e0e0;"
                f"border-radius:8px;padding:8px 12px;color:#1a1a2e;font-weight:600;'>"
                f"📍 {tu_cn}</div></div>",
                unsafe_allow_html=True
            )
    with col_toi:
        options_toi = [c for c in ALL_BRANCHES if c != tu_cn]
        if editing_ma:
            # Khóa toi_cn khi sửa
            toi_cn = edit_meta.get("toi_cn", options_toi[0] if options_toi else "")
            st.markdown(
                f"<div style='padding:4px 0;'>"
                f"<div style='font-size:0.82rem;color:#555;margin-bottom:2px;'>Đến chi nhánh</div>"
                f"<div style='background:#f4f6fa;border:1px solid #e0e0e0;"
                f"border-radius:8px;padding:8px 12px;color:#888;'>"
                f"🔒 {toi_cn}</div></div>",
                unsafe_allow_html=True
            )
        else:
            # Dọn session state nếu giá trị cũ không hợp lệ
            stored_toi = st.session_state.get("ck_toi_cn")
            if stored_toi and stored_toi not in options_toi:
                st.session_state.pop("ck_toi_cn", None)
            toi_cn = st.selectbox("Đến chi nhánh:", options_toi, key="ck_toi_cn") \
                     if options_toi else ""

    col_ng, col_gc = st.columns([1, 2])
    with col_ng:
        default_ng = edit_meta.get("nguoi_tao", user.get("ho_ten","") if user else "")
        nguoi_tao = st.text_input("Người gửi/tạo phiếu:",
            value=default_ng, key="ck_ng_tao")
    with col_gc:
        default_gc = edit_meta.get("ghi_chu", "")
        ghi_chu = st.text_input("Ghi chú chuyển (tuỳ chọn):",
            value=default_gc,
            placeholder="VD: Chuyển bổ sung hàng tuần...",
            key="ck_ghi_chu")

    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

    # ══════ GIỎ HÀNG (TRƯỚC DANH SÁCH CHUYỂN) ══════
    if "ck_items" not in st.session_state:
        st.session_state["ck_items"] = []

    # Load tồn kho từ chi nhánh nguồn (cho suggestion + hiển thị trong giỏ)
    kho_src = load_the_kho(branches_key=(tu_cn,)) if tu_cn else pd.DataFrame()
    ton_map = {}
    if not kho_src.empty and "Mã hàng" in kho_src.columns:
        ton_map = dict(zip(
            kho_src["Mã hàng"].astype(str),
            kho_src["Tồn cuối kì"].fillna(0).astype(int)
        ))

    # Cập nhật ton_src cho items hiện tại
    for it in st.session_state["ck_items"]:
        it["ton_src"] = int(ton_map.get(str(it["ma_hang"]), it.get("ton_src", 0)))

    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;margin-bottom:6px;'>"
        f"🛒 Giỏ hàng ({len(st.session_state['ck_items'])} sản phẩm)</div>",
        unsafe_allow_html=True
    )

    if st.session_state["ck_items"]:
        total_sl = 0
        total_gb = 0
        has_overflow = False  # Track có item nào vượt tồn không

        # Container có scroll khi giỏ > 3 items (mỗi item ~60px cao)
        n_items = len(st.session_state["ck_items"])
        if n_items > 3:
            cart_container = st.container(height=240)
        else:
            cart_container = st.container()

        with cart_container:
            for idx, it in enumerate(st.session_state["ck_items"]):
                ton_src = int(it.get("ton_src", 0))
                over    = it["so_luong"] > ton_src
                if over: has_overflow = True

                c_tn, c_sl, c_del = st.columns([4, 2, 1])
                with c_tn:
                    # Highlight đỏ nếu vượt tồn
                    ton_color = "#cf4c2c" if over else "#888"
                    ton_label = (f"Tồn nguồn: <b style='color:{ton_color};'>{ton_src}</b>"
                                + (" ⚠ vượt tồn" if over else ""))
                    st.markdown(
                        f"<div style='padding-top:10px;font-size:0.85rem;'>"
                        f"<b>{it['ten_hang']}</b><br>"
                        f"<span style='font-family:monospace;font-size:0.72rem;color:#777;'>{it['ma_hang']}</span>"
                        f" · <span style='font-size:0.72rem;color:{ton_color};'>{ton_label}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with c_sl:
                    new_sl = st.number_input(
                        "SL", min_value=1, max_value=99999,
                        value=int(it["so_luong"]),
                        step=1, key=f"sl_{idx}", label_visibility="collapsed"
                    )
                    if new_sl != it["so_luong"]:
                        st.session_state["ck_items"][idx]["so_luong"] = int(new_sl)
                with c_del:
                    st.markdown("<div style='padding-top:5px;'>", unsafe_allow_html=True)
                    if st.button("🗑", key=f"del_{idx}", use_container_width=True):
                        st.session_state["ck_items"].pop(idx)
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

                total_sl += it["so_luong"]
                total_gb += it["so_luong"] * it["gia_ban"]

        # Hiện cảnh báo tổng hợp nếu có item vượt tồn
        if has_overflow:
            st.warning(
                "⚠ Một số sản phẩm có SL chuyển vượt tồn nguồn. "
                "Không thể tạo phiếu cho đến khi sửa lại."
            )

        # Tổng
        st.markdown(
            f"<div style='background:#fff8f8;border:1px solid #ffd5d9;border-radius:10px;"
            f"padding:10px 14px;margin-top:10px;'>"
            f"<div style='display:flex;justify-content:space-between;font-size:0.88rem;'>"
            f"<span>Tổng số lượng:</span><b>{total_sl:,}</b></div>"
            f"<div style='display:flex;justify-content:space-between;font-size:0.88rem;margin-top:4px;'>"
            f"<span>Tổng giá bán:</span><b style='color:#e63946;'>"
            f"{(total_gb/1_000_000):.2f} tr đ</b></div>"
            f"</div>",
            unsafe_allow_html=True
        )

        col_clear, col_submit = st.columns([1, 2])
        with col_clear:
            if st.button("Xóa giỏ", use_container_width=True, key="ck_clear"):
                st.session_state["ck_items"] = []
                st.rerun()
        with col_submit:
            submit_label = "💾 Cập nhật phiếu" if editing_ma else "✓ Tạo phiếu chuyển"
            if st.button(submit_label, use_container_width=True,
                        type="primary", key="ck_submit",
                        disabled=has_overflow,
                        help=("Sửa SL các mặt hàng vượt tồn trước khi tạo phiếu"
                              if has_overflow else None)):
                if tu_cn == toi_cn:
                    st.error("Chi nhánh nguồn và đích phải khác nhau.")
                elif not nguoi_tao.strip():
                    st.error("Vui lòng nhập tên người gửi.")
                elif not toi_cn:
                    st.error("Vui lòng chọn chi nhánh đến.")
                else:
                    _submit_phieu(
                        tu_cn, toi_cn, nguoi_tao.strip(), ghi_chu.strip(),
                        st.session_state["ck_items"],
                        editing_ma=editing_ma
                    )
    else:
        st.caption("Giỏ hàng trống. Tìm và thêm sản phẩm ở danh sách bên dưới.")

    st.markdown("<hr style='margin:14px 0 10px;'>", unsafe_allow_html=True)

    # ══════ DANH SÁCH HÀNG CHUYỂN (search + suggest) ══════
    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;margin-bottom:6px;'>"
        "🔍 Danh sách hàng chuyển</div>",
        unsafe_allow_html=True
    )

    search_col, add_col = st.columns([3, 2])
    with search_col:
        kw = st.text_input("", placeholder="🔍 Tìm sản phẩm theo mã, tên...",
                          key="ck_search", label_visibility="collapsed")
    with add_col:
        only_in_stock = st.checkbox("Chỉ hàng còn tồn ở nguồn",
                                    value=True, key="ck_only_stock")

    # Filter
    hh_list = hh.copy()
    hh_list["_ton_src"] = hh_list["ma_hang"].astype(str).map(ton_map).fillna(0).astype(int)
    if kw.strip():
        kwn = _normalize(kw)
        hh_list["_n_ma"]  = hh_list["ma_hang"].apply(_normalize)
        hh_list["_n_ten"] = hh_list["ten_hang"].apply(_normalize)
        hh_list = hh_list[
            hh_list["_n_ma"].str.contains(kwn, na=False) |
            hh_list["_n_ten"].str.contains(kwn, na=False)
        ]
    if only_in_stock:
        hh_list = hh_list[hh_list["_ton_src"] > 0]
    hh_list = hh_list.head(SUGGEST_LIMIT)

    if not hh_list.empty:
        for _, r in hh_list.iterrows():
            mh = str(r["ma_hang"])
            tn = str(r["ten_hang"])
            gb = int(r.get("gia_ban", 0) or 0)
            tn_src = int(r.get("_ton_src", 0) or 0)
            already = any(it["ma_hang"] == mh for it in st.session_state["ck_items"])

            c_info, c_btn = st.columns([5, 1])
            with c_info:
                st.markdown(
                    f"<div style='padding:6px 0;font-size:0.85rem;'>"
                    f"<b>{tn}</b><br>"
                    f"<span style='font-family:monospace;font-size:0.75rem;color:#777;'>{mh}</span>"
                    f" · <span style='color:#888;font-size:0.78rem;'>Tồn: {tn_src}</span>"
                    f" · <span style='color:#1a7f37;font-size:0.78rem;'>{gb:,}đ</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with c_btn:
                if already:
                    st.caption("✓ Đã thêm")
                else:
                    if st.button("➕", key=f"add_{mh}", use_container_width=True):
                        st.session_state["ck_items"].append({
                            "ma_hang":  mh,
                            "ten_hang": tn,
                            "so_luong": 1,
                            "gia_ban":  gb,
                            "ton_src":  tn_src,
                        })
                        st.rerun()

        if len(hh) > SUGGEST_LIMIT and not kw.strip():
            st.caption(f"ℹ Hiển thị {SUGGEST_LIMIT} sản phẩm — nhập từ khóa để tìm chính xác hơn.")
    elif kw.strip():
        st.caption("Không tìm thấy sản phẩm phù hợp.")
    else:
        st.caption("Gõ mã/tên sản phẩm để tìm kiếm.")


def _validate_stock(tu_cn: str, items: list, editing_ma: str = None) -> tuple:
    """
    Kiểm tra SL chuyển có vượt quá tồn hiệu dụng không.
    Trả về (ok: bool, errors: list[str]).

    Khi edit: cộng bù lại SL của phiếu cũ (vì phiếu cũ đang trong trạng thái
    Phiếu tạm nên chưa ảnh hưởng delta, nhưng logic đúng hơn là tính độc lập).
    Phiếu tạm → delta=0, nên chỉ cần so với tồn hiện tại.
    """
    if not tu_cn or not items:
        return True, []

    # Load tồn hiệu dụng hiện tại tại CN nguồn (đã áp dụng delta từ phiếu App)
    kho = load_the_kho(branches_key=(tu_cn,))
    if kho.empty or "Mã hàng" not in kho.columns:
        return True, []  # Không có dữ liệu kho → skip (fallback mềm)

    ton_map = dict(zip(
        kho["Mã hàng"].astype(str),
        kho["Tồn cuối kì"].fillna(0).astype(int)
    ))

    errors = []
    for it in items:
        mh = str(it["ma_hang"])
        sl = int(it["so_luong"])
        ton = ton_map.get(mh, 0)
        if sl > ton:
            errors.append(
                f"• **{it['ten_hang']}** ({mh}): "
                f"yêu cầu chuyển {sl:,}, tồn hiệu dụng chỉ có {ton:,}"
            )
    return len(errors) == 0, errors


def _submit_phieu(tu_cn: str, toi_cn: str, nguoi_tao: str, ghi_chu: str,
                  items: list, editing_ma: str = None):
    """Insert phiếu mới hoặc update phiếu đang sửa."""
    # ── Validate tồn kho trước khi submit ──
    

    try:
        with st.spinner("Đang xử lý..."):
            now_iso  = datetime.now().isoformat()

            tong_sl    = sum(it["so_luong"] for it in items)
            tong_mat   = len(items)
            tong_gtri  = sum(it["so_luong"] * it["gia_ban"] for it in items)

            # Khi sửa: giữ nguyên trạng thái "Phiếu tạm" (chỉ phiếu tạm mới sửa được)
            trang_thai = "Phiếu tạm"

            def _build_records(ma):
                """Build records với ma_phieu cho sẵn."""
                return [{
                    "ma_phieu":         ma,
                    "loai_phieu":       IN_APP_MARKER,
                    "tu_chi_nhanh":     tu_cn,
                    "toi_chi_nhanh":    toi_cn,
                    "ngay_chuyen":      now_iso,
                    "ngay_nhan":        None,
                    "nguoi_tao":        nguoi_tao,
                    "ghi_chu_chuyen":   ghi_chu or None,
                    "ghi_chu_nhan":     None,
                    "tong_sl_chuyen":   tong_sl,
                    "tong_sl_nhan":     0,
                    "tong_gia_tri":     int(tong_gtri),
                    "tong_mat_hang":    tong_mat,
                    "trang_thai":       trang_thai,
                    "ma_hang":          str(it["ma_hang"]),
                    "ma_vach":          None,
                    "ten_hang":         str(it["ten_hang"]),
                    "thuong_hieu":      None,
                    "so_luong_chuyen":  int(it["so_luong"]),
                    "so_luong_nhan":    0,
                    "gia_chuyen":       int(it["gia_ban"]),
                    "thanh_tien_chuyen":int(it["so_luong"] * it["gia_ban"]),
                    "thanh_tien_nhan":  0,
                } for it in items]

            if editing_ma:
                # Sửa phiếu: dùng luôn ma cũ, DELETE + INSERT
                _delete_phieu_rows(editing_ma)
                supabase.table("phieu_chuyen_kho").insert(_build_records(editing_ma)).execute()
                ma_phieu = editing_ma
                msg = f"💾 Đã cập nhật phiếu **{ma_phieu}**!"
                log_action(
                    "PHIEU_UPDATE",
                    f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} "
                    f"sl={tong_sl} items={tong_mat}"
                )
            else:
                # Tạo mới: retry nếu duplicate (race condition hiếm gặp)
                ma_phieu = None
                last_err = None
                for attempt in range(3):
                    try_ma = _gen_ma_phieu()
                    try:
                        supabase.table("phieu_chuyen_kho").insert(_build_records(try_ma)).execute()
                        ma_phieu = try_ma
                        break
                    except Exception as e:
                        last_err = e
                        err_str = str(e).lower()
                        # Chỉ retry nếu là duplicate key error
                        if "duplicate" in err_str or "unique" in err_str:
                            _logger.warning(
                                f"PHIEU_RETRY — attempt={attempt+1} ma={try_ma} "
                                f"(race condition, thử lại)"
                            )
                            continue
                        # Lỗi khác → raise ngay, không retry
                        raise

                if ma_phieu is None:
                    raise RuntimeError(
                        f"Không sinh được mã phiếu sau 3 lần thử: {last_err}"
                    )

                msg = f"✓ Tạo phiếu **{ma_phieu}** thành công!"
                log_action(
                    "PHIEU_CREATE",
                    f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} "
                    f"sl={tong_sl} items={tong_mat} gtri={int(tong_gtri)}"
                )

            # Reset
            st.session_state["ck_items"] = []
            st.session_state.pop("ck_editing", None)
            st.session_state.pop("ck_edit_meta", None)
            st.cache_data.clear()

            st.success(msg)
            if not editing_ma:
                st.balloons()

            # Delay cho user thấy success message, rồi auto-rerun
            # để form reset + chuyển về trạng thái sạch
            import time
            time.sleep(1.5)
            st.rerun()
    except Exception as e:
        st.error(f"Lỗi xử lý phiếu: {e}")


def module_chuyen_hang():
    """View + Tạo/Sửa phiếu chuyển kho."""
    try:
        active    = get_active_branch()
        view_cns  = tuple(get_accessible_branches()) if is_ke_toan_or_admin() else (active,)
        df_all    = load_phieu_chuyen_kho(branches_key=view_cns)

        # Tab label động: khi đang edit → nhắc user
        editing = st.session_state.get("ck_editing")
        create_tab_label = ("➕ Tạo / Sửa phiếu"
                           + (" 🔄" if editing else ""))

        tab_view, tab_create = st.tabs(
            ["📋 Danh sách phiếu", create_tab_label]
        )
        with tab_view:
            _view_phieu_chuyen(df_all)
        with tab_create:
            _tao_phieu_chuyen()

    except Exception as e:
        st.error(f"Lỗi tải Chuyển hàng: {e}")


# ==========================================
# MODULE: QUẢN LÝ NHÂN VIÊN
# ==========================================

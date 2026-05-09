"""Admin POS — tạo HĐ / phiếu đổi-trả / phiếu sửa chữa + sửa HĐ POS.

B1 (tạo): PLAN_ADMIN_B1.md.
B2a (sửa HĐ POS): plan admin b2a (admin_edit_history snapshot).
Chỉ admin truy cập được.
"""

import re
import streamlit as st
from datetime import datetime, date, timedelta

from utils.auth import require_admin, get_user
from utils.db import (
    supabase, call_rpc, load_all_nhan_vien, load_hang_hoa,
    invalidate_hoa_don_cache,
    search_hd_pos_for_edit, load_hd_with_edit_history, has_active_pdt_for_hd,
    search_pdt_for_edit, search_sc_for_edit, load_record_with_history,
    lookup_khach_hang, upsert_khach_hang_with_update,
)
from utils.config import ALL_BRANCHES
from utils.helpers import now_vn


def fmt_vnd(n) -> str:
    try:
        return f"{int(n or 0):,}đ".replace(",", ".")
    except Exception:
        return "0đ"


def _safe_key(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", str(s or ""))


def _clean_sdt(s: str) -> str:
    """Chỉ giữ digit, max 15."""
    return "".join(c for c in str(s or "") if c.isdigit())[:15]


def _render_kh_lookup_input(
    key_prefix: str,
    default_ten: str = "",
    default_sdt: str = "",
    label_sdt: str = "SĐT khách",
    label_ten: str = "Tên khách",
):
    """Render SĐT + tên KH inputs với auto-lookup khach_hang.

    Behavior:
    - SĐT thay đổi → lookup khach_hang → auto-fill tên (override editable).
    - SĐT không đổi → giữ tên user đã edit (không override).
    - Sau RPC success, caller gọi upsert_khach_hang_with_update(ten, sdt, chi_nhanh)
      để propagate tên về khach_hang master.

    Returns: (ten_clean, sdt_clean, kh_existed_bool, ma_kh_or_none).
    """
    sdt_key = f"{key_prefix}_sdt"
    ten_key = f"{key_prefix}_ten"
    last_lookup_key = f"{key_prefix}_last_lookup"
    lookup_kh_key = f"{key_prefix}_last_result"

    if sdt_key not in st.session_state:
        st.session_state[sdt_key] = default_sdt or ""
    if ten_key not in st.session_state:
        st.session_state[ten_key] = default_ten or ""

    col_sdt, col_ten = st.columns(2)
    with col_sdt:
        sdt_raw = st.text_input(
            label_sdt, key=sdt_key, max_chars=15, placeholder="0xxx xxx xxx",
        )
    sdt_clean = _clean_sdt(sdt_raw)

    last_lookup = st.session_state.get(last_lookup_key, "")
    if sdt_clean and sdt_clean != last_lookup:
        kh = lookup_khach_hang(sdt_clean)
        st.session_state[last_lookup_key] = sdt_clean
        st.session_state[lookup_kh_key] = kh
        st.session_state[ten_key] = (kh.get("ten_kh") if kh else "") or ""
    elif not sdt_clean and last_lookup:
        st.session_state[last_lookup_key] = ""
        st.session_state[lookup_kh_key] = None
        st.session_state[ten_key] = ""

    with col_ten:
        ten_raw = st.text_input(label_ten, key=ten_key)

    ten_clean = (ten_raw or "").strip()
    kh_found = st.session_state.get(lookup_kh_key)

    if sdt_clean:
        if kh_found:
            old_name = (kh_found.get("ten_kh") or "").strip()
            if ten_clean and ten_clean != old_name:
                st.info(
                    f"✏️ Khách hiện có (tên cũ: **{old_name or '—'}**) — "
                    f"tên mới sẽ ghi đè vào `khach_hang` khi submit."
                )
            else:
                st.success(f"✓ Khách hiện có: **{old_name or '(chưa có tên)'}**")
        else:
            if ten_clean:
                st.caption("⚠️ SĐT chưa có — sẽ tạo khách mới khi submit.")
            else:
                st.caption("⚠️ SĐT chưa có — nhập tên để tạo khách mới.")

    ma_kh = kh_found.get("ma_kh") if kh_found else None
    return ten_clean, sdt_clean, bool(kh_found), ma_kh


def _reset_kh_lookup_state(key_prefix: str):
    """Reset state của _render_kh_lookup_input (sau submit success / quay lại)."""
    for suffix in ("_sdt", "_ten", "_last_lookup", "_last_result"):
        st.session_state.pop(f"{key_prefix}{suffix}", None)


def display_hd_admin_badge(hd: dict | None):
    """Reusable: render badge '🛡 ADMIN' + admin_note nếu HĐ là admin-created."""
    if not hd or not hd.get("is_admin_created"):
        return
    st.markdown("🛡 **HĐ Admin**")
    if hd.get("admin_note"):
        st.caption(f"📝 Lý do: {hd['admin_note']}")


def _build_created_at(date_key: str, time_key: str) -> str:
    """Combine date + time inputs thành ISO string với timezone VN."""
    d = st.session_state.get(date_key)
    t = st.session_state.get(time_key)
    if not d or not t:
        return now_vn().isoformat()
    return datetime.combine(d, t).replace(tzinfo=now_vn().tzinfo).isoformat()


def _nv_options(include_inactive: bool = True) -> tuple[list[str], dict]:
    """Trả về (labels, mapping label→nv) cho dropdown chọn NV."""
    nvs = load_all_nhan_vien(include_inactive=include_inactive)
    mapping = {}
    labels = []
    for nv in nvs:
        tag = "" if nv.get("active") else " · NGHỈ"
        role_tag = f" [{nv.get('role','?')}]"
        label = f"{nv['ho_ten']}{role_tag}{tag}"
        mapping[label] = nv
        labels.append(label)
    return labels, mapping


def _confirm_block(prefix: str, summary_lines: list[str]) -> bool:
    """Block xác nhận — gõ 'XÁC NHẬN' để bật nút submit. Return: enabled?"""
    with st.expander("⚠️ Xác nhận tạo (admin)", expanded=False):
        for line in summary_lines:
            st.write(line)
        confirm_text = st.text_input(
            "Gõ **XÁC NHẬN** để bật nút tạo:",
            key=f"{prefix}_confirm_text"
        )
        return confirm_text.strip().upper() == "XÁC NHẬN"


# ════════════════════════════════════════════════════════════
# TAB 1 — TẠO HĐ POS ADMIN
# ════════════════════════════════════════════════════════════
def _render_tao_hd_pos():
    user = get_user()
    cart_key = "admin_hd_cart"
    if cart_key not in st.session_state:
        st.session_state[cart_key] = []
    cart = st.session_state[cart_key]

    # ── 1. Backdate ──
    col_d, col_t = st.columns(2)
    with col_d:
        st.date_input(
            "Ngày HĐ",
            value=date.today(),
            min_value=date.today() - timedelta(days=90),
            max_value=date.today(),
            key="admin_hd_date",
        )
    with col_t:
        st.time_input("Giờ HĐ", value=now_vn().time().replace(microsecond=0),
                      key="admin_hd_time")

    # ── 2. NV bán + Chi nhánh ──
    col_nv, col_cn = st.columns(2)
    with col_nv:
        nv_labels, nv_map = _nv_options(include_inactive=True)
        if not nv_labels:
            st.error("Không tải được danh sách NV"); return
        nv_label = st.selectbox("Người bán", options=nv_labels, key="admin_hd_nv")
    with col_cn:
        chi_nhanh = st.selectbox("Chi nhánh", options=ALL_BRANCHES, key="admin_hd_cn")
    nv_chosen = nv_map[nv_label]

    # ── 3. Khách hàng (optional) — auto-lookup từ SĐT, tên có thể override ──
    ten_khach, sdt_khach, _, _ = _render_kh_lookup_input(
        "admin_hd_kh",
        label_sdt="SĐT khách (optional)",
        label_ten="Tên khách (optional)",
    )

    # ── 4. Items ──
    st.markdown("---")
    st.markdown("**Items**")

    search = st.text_input("Tìm hàng hóa/dịch vụ (mã hoặc tên)",
                           key="admin_hd_search",
                           placeholder="VD: '1234' hoặc 'Casio'")
    if search and len(search.strip()) >= 2:
        df = load_hang_hoa()
        if not df.empty:
            kw = search.strip().lower()
            mask = (
                df["ma_hang"].astype(str).str.lower().str.contains(kw, na=False) |
                df["ten_hang"].astype(str).str.lower().str.contains(kw, na=False)
            )
            results = df[mask].head(8)
            for _, hh in results.iterrows():
                ma = str(hh.get("ma_hang") or "")
                ten = str(hh.get("ten_hang") or "")
                gia = int(hh.get("gia_ban") or 0)
                is_op = bool(hh.get("is_open_price"))
                if st.button(
                    f"➕ {ma} — {ten} (mặc định {fmt_vnd(gia)})"
                    + (" · open-price" if is_op else ""),
                    key=f"admin_hd_add_{_safe_key(ma)}",
                    use_container_width=True
                ):
                    cart.append({
                        "ma_hang": ma,
                        "ten_hang": ten,
                        "so_luong": 1,
                        "don_gia": gia,
                        "is_open_price": is_op,
                    })
                    st.rerun()

    # Hiển thị cart — đơn giá editable cho MỌI item (admin override)
    delete_idx = None
    for i, line in enumerate(cart):
        col_info, col_sl, col_dg, col_x = st.columns([4, 1.4, 2, 0.6])
        with col_info:
            badge = "✏️" if line.get("is_open_price") else "📦"
            st.markdown(f"{badge} **{line['ten_hang']}** ({line['ma_hang']})")
        with col_sl:
            line["so_luong"] = st.number_input(
                "SL", min_value=1, value=int(line["so_luong"]),
                key=f"admin_hd_sl_{i}", label_visibility="collapsed"
            )
        with col_dg:
            line["don_gia"] = st.number_input(
                "Đơn giá", min_value=0, value=int(line["don_gia"]), step=10000,
                key=f"admin_hd_dg_{i}", label_visibility="collapsed"
            )
        with col_x:
            if st.button("✕", key=f"admin_hd_del_{i}"):
                delete_idx = i
    if delete_idx is not None:
        cart.pop(delete_idx); st.rerun()

    tong_tien_hang = sum(int(l["so_luong"]) * int(l["don_gia"]) for l in cart)
    st.markdown(f"**Tổng tiền hàng:** {fmt_vnd(tong_tien_hang)}")

    # ── 5. Giảm giá đơn (optional) ──
    st.session_state.setdefault("admin_hd_gg", 0)
    giam_gia_don = st.number_input(
        "Giảm giá đơn (optional, default 0)",
        min_value=0, step=10000,
        key="admin_hd_gg",
        help="Để bù HĐ KiotViet/POS gốc có giảm giá"
    )
    if giam_gia_don > tong_tien_hang:
        st.error(f"Giảm giá ({fmt_vnd(giam_gia_don)}) vượt tổng tiền hàng")
    khach_can_tra = max(0, tong_tien_hang - giam_gia_don)
    if giam_gia_don > 0:
        st.markdown(f"**Khách cần trả:** {fmt_vnd(khach_can_tra)}")

    # ── 6. PTTT ──
    st.markdown("---")
    st.markdown(f"**Phương thức thanh toán** (khách cần trả: {fmt_vnd(khach_can_tra)})")

    st.session_state.setdefault("admin_hd_tm", 0)
    st.session_state.setdefault("admin_hd_ck", 0)
    st.session_state.setdefault("admin_hd_the", 0)

    # Quick-fill: chỉ 1 PTTT, reset 2 cái kia về 0
    col_q1, col_q2, col_q3 = st.columns(3)
    with col_q1:
        if st.button("💵 Toàn bộ Tiền mặt", key="admin_hd_qf_tm",
                     use_container_width=True):
            st.session_state["admin_hd_tm"] = int(khach_can_tra)
            st.session_state["admin_hd_ck"] = 0
            st.session_state["admin_hd_the"] = 0
            st.rerun()
    with col_q2:
        if st.button("🏦 Toàn bộ Chuyển khoản", key="admin_hd_qf_ck",
                     use_container_width=True):
            st.session_state["admin_hd_tm"] = 0
            st.session_state["admin_hd_ck"] = int(khach_can_tra)
            st.session_state["admin_hd_the"] = 0
            st.rerun()
    with col_q3:
        if st.button("💳 Toàn bộ Thẻ", key="admin_hd_qf_the",
                     use_container_width=True):
            st.session_state["admin_hd_tm"] = 0
            st.session_state["admin_hd_ck"] = 0
            st.session_state["admin_hd_the"] = int(khach_can_tra)
            st.rerun()

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        tien_mat = st.number_input("Tiền mặt", min_value=0, step=1000,
                                   key="admin_hd_tm")
    with col_p2:
        chuyen_khoan = st.number_input("Chuyển khoản", min_value=0, step=1000,
                                        key="admin_hd_ck")
    with col_p3:
        the = st.number_input("Thẻ", min_value=0, step=1000, key="admin_hd_the")

    # Tổng PTTT vs khách cần trả
    tong_pttt = int(tien_mat) + int(chuyen_khoan) + int(the)
    diff = tong_pttt - int(khach_can_tra)
    if diff == 0:
        st.success(f"✓ Tổng PTTT: {fmt_vnd(tong_pttt)} (khớp)")
    elif diff > 0:
        st.info(f"Tổng PTTT: {fmt_vnd(tong_pttt)} (khách trả thừa {fmt_vnd(diff)})")
    else:
        st.warning(f"Tổng PTTT: {fmt_vnd(tong_pttt)} (còn thiếu {fmt_vnd(-diff)})")

    # ── 7. Admin note ──
    admin_note = st.text_area(
        "Lý do tạo HĐ admin (optional)",
        placeholder="VD: Bù HĐ ngày 2026-04-15 NV quên ghi",
        key="admin_hd_note"
    )

    # ── 8. Submit ──
    st.markdown("---")
    if not cart:
        st.caption("Thêm ít nhất 1 item để tạo HĐ")
        return

    created_at = _build_created_at("admin_hd_date", "admin_hd_time")
    summary = [
        f"- **Ngày HĐ:** {created_at}",
        f"- **Người bán:** {nv_chosen['ho_ten']} (id={nv_chosen['id']}, {nv_chosen['role']})",
        f"- **Chi nhánh:** {chi_nhanh}",
        f"- **Items:** {len(cart)} dòng",
        f"- **Tổng tiền hàng:** {fmt_vnd(tong_tien_hang)}",
        f"- **Giảm giá:** {fmt_vnd(giam_gia_don)}",
        f"- **Khách cần trả:** {fmt_vnd(khach_can_tra)}",
    ]
    enabled = _confirm_block("admin_hd", summary)

    if st.button("🛡 Tạo HĐ Admin", disabled=not enabled,
                 type="primary", key="admin_hd_submit",
                 use_container_width=True):
        payload = {
            "admin_id": user["id"],
            "created_at": created_at,
            "nguoi_ban_id": nv_chosen["id"],
            "chi_nhanh": chi_nhanh,
            "ten_khach": ten_khach.strip() or None,
            "sdt_khach": sdt_khach.strip() or None,
            "tien_mat": int(tien_mat),
            "chuyen_khoan": int(chuyen_khoan),
            "the": int(the),
            "giam_gia_don": int(giam_gia_don),
            "ghi_chu": "",
            "admin_note": admin_note.strip() or None,
            "items": [
                {
                    "ma_hang": l["ma_hang"],
                    "ten_hang": l["ten_hang"],
                    "so_luong": int(l["so_luong"]),
                    "don_gia": int(l["don_gia"]),
                }
                for l in cart
            ],
        }
        try:
            result = call_rpc("tao_hoa_don_pos_admin", {"payload": payload})
        except Exception as e:
            st.error(f"❌ Lỗi RPC: {e}"); return

        if result and result.get("ok"):
            st.success(
                f"✅ Đã tạo {result['ma_hd']} — "
                f"khách trả {fmt_vnd(result.get('khach_can_tra'))}"
            )
            if sdt_khach and ten_khach:
                upsert_khach_hang_with_update(ten_khach, sdt_khach, chi_nhanh)
            st.session_state[cart_key] = []
            _reset_kh_lookup_state("admin_hd_kh")
            invalidate_hoa_don_cache()
            st.rerun()
        else:
            st.error(f"❌ {result.get('error', 'Unknown error') if result else 'No response'}")


# ════════════════════════════════════════════════════════════
# TAB 2 — TẠO PHIẾU ĐỔI/TRẢ ADMIN
# ════════════════════════════════════════════════════════════
def _load_hd_goc(ma_hd: str) -> dict | None:
    if not ma_hd: return None
    try:
        res = supabase.table("hoa_don_pos").select("*").eq("ma_hd", ma_hd).limit(1).execute()
        if res.data:
            hd = res.data[0]
            ct = supabase.table("hoa_don_pos_ct").select("*").eq("ma_hd", ma_hd).execute()
            hd["_items"] = ct.data or []
            return hd
    except Exception as e:
        st.error(f"Lỗi load HĐ: {e}")
    return None


def _render_tao_doi_tra():
    user = get_user()
    tra_key = "admin_pdt_items_tra"
    moi_key = "admin_pdt_items_moi"
    if tra_key not in st.session_state: st.session_state[tra_key] = []
    if moi_key not in st.session_state: st.session_state[moi_key] = []

    # ── 1. Mã HĐ gốc ──
    ma_hd_goc = st.text_input("Mã HĐ gốc (AHD000XXX)",
                              key="admin_pdt_ma_hd_goc",
                              placeholder="VD: AHD000050")
    hd_goc = _load_hd_goc(ma_hd_goc.strip()) if ma_hd_goc else None
    if ma_hd_goc and not hd_goc:
        st.warning("Chưa tìm thấy HĐ gốc — kiểm tra lại mã")
        return
    if not hd_goc:
        st.caption("Nhập mã HĐ gốc để load thông tin")
        return

    # ── 2. Hiển thị HĐ gốc (read-only, chi_nhanh locked) ──
    chi_nhanh = hd_goc["chi_nhanh"]
    st.info(
        f"**HĐ gốc:** {hd_goc['ma_hd']} · {chi_nhanh} · "
        f"khách: {hd_goc.get('ten_khach') or '—'} · "
        f"tổng: {fmt_vnd(hd_goc.get('khach_can_tra'))} · "
        f"trạng thái: {hd_goc.get('trang_thai')}"
    )
    if hd_goc.get("trang_thai") == "Đã hủy":
        st.error("HĐ gốc đã hủy — không thể tạo phiếu đổi/trả")
        return

    # ── 3. Backdate ──
    col_d, col_t = st.columns(2)
    with col_d:
        st.date_input(
            "Ngày phiếu",
            value=date.today(),
            min_value=date.today() - timedelta(days=90),
            max_value=date.today(),
            key="admin_pdt_date",
        )
    with col_t:
        st.time_input("Giờ phiếu", value=now_vn().time().replace(microsecond=0),
                      key="admin_pdt_time")

    # ── 4. NV tạo ──
    nv_labels, nv_map = _nv_options(include_inactive=True)
    nv_label = st.selectbox("Người tạo phiếu", options=nv_labels, key="admin_pdt_nv")
    nv_chosen = nv_map[nv_label]

    # ── 5. Items TRẢ — pick từ HĐ gốc ──
    st.markdown("---")
    st.markdown("**Items trả** (từ HĐ gốc)")
    items_tra = st.session_state[tra_key]

    for ct in hd_goc["_items"]:
        ma = ct["ma_hang"]
        ten = ct.get("ten_hang") or ma
        sl_goc = int(ct.get("so_luong") or 0)
        dg_goc = int(ct.get("don_gia") or 0)

        existing = next((it for it in items_tra if it["ma_hang"] == ma), None)
        col_chk, col_info, col_sl, col_dg = st.columns([0.5, 4, 1.5, 2])
        with col_chk:
            chk = st.checkbox(
                "_", value=existing is not None,
                key=f"admin_pdt_chk_{_safe_key(ma)}",
                label_visibility="collapsed"
            )
        with col_info:
            st.markdown(f"**{ten}** ({ma}) · gốc SL={sl_goc} @ {fmt_vnd(dg_goc)}")
        with col_sl:
            sl_default = existing["so_luong"] if existing else sl_goc
            sl_in = st.number_input(
                "SL trả", min_value=1, max_value=sl_goc, value=sl_default,
                key=f"admin_pdt_sl_{_safe_key(ma)}",
                label_visibility="collapsed",
                disabled=not chk,
            )
        with col_dg:
            dg_default = existing["don_gia"] if existing else dg_goc
            dg_in = st.number_input(
                "Đơn giá", min_value=0, value=dg_default, step=10000,
                key=f"admin_pdt_dg_{_safe_key(ma)}",
                label_visibility="collapsed",
                disabled=not chk,
            )

        if chk:
            if existing:
                existing["so_luong"] = int(sl_in)
                existing["don_gia"] = int(dg_in)
            else:
                items_tra.append({
                    "ma_hang": ma, "ten_hang": ten,
                    "so_luong": int(sl_in), "don_gia": int(dg_in),
                })
        else:
            if existing:
                items_tra.remove(existing)

    tong_tra = sum(it["so_luong"] * it["don_gia"] for it in items_tra)
    st.markdown(f"**Tổng tiền trả:** {fmt_vnd(tong_tra)}")

    # ── 6. Items MỚI (optional) ──
    st.markdown("---")
    st.markdown("**Items mới** (đổi sang — optional)")
    items_moi = st.session_state[moi_key]

    search_m = st.text_input("Tìm hàng mới", key="admin_pdt_search_moi",
                              placeholder="Mã hoặc tên")
    if search_m and len(search_m.strip()) >= 2:
        df = load_hang_hoa()
        if not df.empty:
            kw = search_m.strip().lower()
            mask = (
                df["ma_hang"].astype(str).str.lower().str.contains(kw, na=False) |
                df["ten_hang"].astype(str).str.lower().str.contains(kw, na=False)
            )
            for _, hh in df[mask].head(6).iterrows():
                ma = str(hh.get("ma_hang") or "")
                ten = str(hh.get("ten_hang") or "")
                gia = int(hh.get("gia_ban") or 0)
                if st.button(
                    f"➕ {ma} — {ten} ({fmt_vnd(gia)})",
                    key=f"admin_pdt_add_moi_{_safe_key(ma)}",
                    use_container_width=True
                ):
                    items_moi.append({
                        "ma_hang": ma, "ten_hang": ten,
                        "so_luong": 1, "don_gia": gia,
                    })
                    st.rerun()

    delete_moi_idx = None
    for i, line in enumerate(items_moi):
        c1, c2, c3, c4 = st.columns([4, 1.4, 2, 0.6])
        with c1: st.markdown(f"**{line['ten_hang']}** ({line['ma_hang']})")
        with c2:
            line["so_luong"] = st.number_input(
                "SL", min_value=1, value=int(line["so_luong"]),
                key=f"admin_pdt_moi_sl_{i}", label_visibility="collapsed"
            )
        with c3:
            line["don_gia"] = st.number_input(
                "Đơn giá", min_value=0, value=int(line["don_gia"]), step=10000,
                key=f"admin_pdt_moi_dg_{i}", label_visibility="collapsed"
            )
        with c4:
            if st.button("✕", key=f"admin_pdt_moi_del_{i}"):
                delete_moi_idx = i
    if delete_moi_idx is not None:
        items_moi.pop(delete_moi_idx); st.rerun()

    tong_moi = sum(it["so_luong"] * it["don_gia"] for it in items_moi)
    chenh_lech = tong_moi - tong_tra
    st.markdown(f"**Tổng tiền mới:** {fmt_vnd(tong_moi)}")
    st.markdown(f"**Chênh lệch:** {fmt_vnd(chenh_lech)} "
                f"({'khách bù' if chenh_lech > 0 else 'shop hoàn' if chenh_lech < 0 else 'cân'})")

    # ── 7. PTTT ──
    st.markdown("---")
    if chenh_lech > 0:
        st.caption(f"Khách cần bù {fmt_vnd(chenh_lech)}")

        st.session_state.setdefault("admin_pdt_tm", 0)
        st.session_state.setdefault("admin_pdt_ck", 0)
        st.session_state.setdefault("admin_pdt_the", 0)

        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            if st.button("💵 Toàn bộ Tiền mặt", key="admin_pdt_qf_tm",
                         use_container_width=True):
                st.session_state["admin_pdt_tm"] = int(chenh_lech)
                st.session_state["admin_pdt_ck"] = 0
                st.session_state["admin_pdt_the"] = 0
                st.rerun()
        with col_q2:
            if st.button("🏦 Toàn bộ Chuyển khoản", key="admin_pdt_qf_ck",
                         use_container_width=True):
                st.session_state["admin_pdt_tm"] = 0
                st.session_state["admin_pdt_ck"] = int(chenh_lech)
                st.session_state["admin_pdt_the"] = 0
                st.rerun()
        with col_q3:
            if st.button("💳 Toàn bộ Thẻ", key="admin_pdt_qf_the",
                         use_container_width=True):
                st.session_state["admin_pdt_tm"] = 0
                st.session_state["admin_pdt_ck"] = 0
                st.session_state["admin_pdt_the"] = int(chenh_lech)
                st.rerun()

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            tien_mat = st.number_input("Tiền mặt", min_value=0, step=1000,
                                       key="admin_pdt_tm")
        with col_p2:
            chuyen_khoan = st.number_input("Chuyển khoản", min_value=0,
                                            step=1000, key="admin_pdt_ck")
        with col_p3:
            the = st.number_input("Thẻ", min_value=0, step=1000,
                                  key="admin_pdt_the")

        tong_pttt = int(tien_mat) + int(chuyen_khoan) + int(the)
        diff = tong_pttt - int(chenh_lech)
        if diff == 0:
            st.success(f"✓ Tổng PTTT: {fmt_vnd(tong_pttt)} (khớp)")
        elif diff > 0:
            st.info(f"Tổng PTTT: {fmt_vnd(tong_pttt)} (thừa {fmt_vnd(diff)})")
        else:
            st.warning(f"Tổng PTTT: {fmt_vnd(tong_pttt)} (thiếu {fmt_vnd(-diff)})")
    elif chenh_lech < 0:
        st.caption(f"Shop hoàn {fmt_vnd(-chenh_lech)} — chỉ tiền mặt (số âm)")
        tien_mat = chenh_lech
        chuyen_khoan = 0
        the = 0
    else:
        tien_mat = chuyen_khoan = the = 0

    # ── 8. Admin note + ghi chú ──
    ghi_chu = st.text_input("Ghi chú phiếu (optional)", key="admin_pdt_ghichu")
    admin_note = st.text_area("Lý do admin (optional)", key="admin_pdt_note")

    # ── 9. Submit ──
    st.markdown("---")
    if not items_tra:
        st.caption("Chọn ít nhất 1 item trả để tiếp tục")
        return

    created_at = _build_created_at("admin_pdt_date", "admin_pdt_time")
    summary = [
        f"- **HĐ gốc:** {hd_goc['ma_hd']} · {chi_nhanh}",
        f"- **Ngày phiếu:** {created_at}",
        f"- **NV tạo:** {nv_chosen['ho_ten']} (id={nv_chosen['id']})",
        f"- **Items trả:** {len(items_tra)} ({fmt_vnd(tong_tra)})",
        f"- **Items mới:** {len(items_moi)} ({fmt_vnd(tong_moi)})",
        f"- **Chênh lệch:** {fmt_vnd(chenh_lech)}",
    ]
    enabled = _confirm_block("admin_pdt", summary)

    if st.button("🛡 Tạo phiếu đổi/trả Admin", disabled=not enabled,
                 type="primary", key="admin_pdt_submit",
                 use_container_width=True):
        payload = {
            "admin_id": user["id"],
            "created_at": created_at,
            "ma_hd_goc": hd_goc["ma_hd"],
            "nguoi_tao_id": nv_chosen["id"],
            "tien_mat": int(tien_mat),
            "chuyen_khoan": int(chuyen_khoan),
            "the": int(the),
            "ghi_chu": ghi_chu.strip() or None,
            "admin_note": admin_note.strip() or None,
            "items_tra": items_tra,
            "items_moi": items_moi,
        }
        try:
            result = call_rpc("tao_phieu_doi_tra_pos_admin", {"payload": payload})
        except Exception as e:
            st.error(f"❌ Lỗi RPC: {e}"); return

        if result and result.get("ok"):
            st.success(
                f"✅ Đã tạo {result['ma_pdt']} ({result.get('loai_phieu')}) — "
                f"chênh lệch {fmt_vnd(result.get('chenh_lech'))}"
            )
            st.session_state[tra_key] = []
            st.session_state[moi_key] = []
            invalidate_hoa_don_cache()
            st.rerun()
        else:
            st.error(f"❌ {result.get('error', 'Unknown error') if result else 'No response'}")


# ════════════════════════════════════════════════════════════
# TAB 3 — TẠO PHIẾU SỬA CHỮA ADMIN
# ════════════════════════════════════════════════════════════
def _render_tao_sua_chua():
    user = get_user()
    items_key = "admin_sc_items"
    if items_key not in st.session_state:
        st.session_state[items_key] = []
    items = st.session_state[items_key]

    # ── 1. Backdate ──
    col_d, col_t = st.columns(2)
    with col_d:
        st.date_input(
            "Ngày tiếp nhận",
            value=date.today(),
            min_value=date.today() - timedelta(days=90),
            max_value=date.today(),
            key="admin_sc_date",
        )
    with col_t:
        st.time_input("Giờ tiếp nhận", value=now_vn().time().replace(microsecond=0),
                      key="admin_sc_time")

    # ── 2. Chi nhánh + NV tiếp nhận ──
    col_cn, col_nv = st.columns(2)
    with col_cn:
        chi_nhanh = st.selectbox("Chi nhánh", options=ALL_BRANCHES, key="admin_sc_cn")
    with col_nv:
        nv_labels, nv_map = _nv_options(include_inactive=True)
        nv_label = st.selectbox("NV tiếp nhận", options=nv_labels, key="admin_sc_nv")
        nv_chosen = nv_map[nv_label]

    # ── 3. Khách hàng — auto-lookup từ SĐT, tên có thể override ──
    ten_khach, sdt_khach, _, _ = _render_kh_lookup_input(
        "admin_sc_kh",
        label_sdt="SĐT khách",
        label_ten="Tên khách",
    )

    # ── 4. Thông tin đồng hồ ──
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        loai_yc = st.selectbox(
            "Loại yêu cầu",
            options=["Sửa chữa", "Bảo hành", "Bảo dưỡng", "Khác"],
            key="admin_sc_loai_yc",
        )
    with col_h2:
        hieu_dh = st.text_input("Hiệu đồng hồ (optional)", key="admin_sc_hieu")

    dac_diem = st.text_input("Đặc điểm máy (optional)", key="admin_sc_dac_diem")
    mo_ta_loi = st.text_area("Mô tả lỗi", key="admin_sc_mo_ta")

    # ── 5. Khách trả trước + ngày hẹn ──
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        khach_tra_truoc = st.number_input("Khách trả trước",
                                          min_value=0, value=0, step=10000,
                                          key="admin_sc_tra_truoc")
    with col_t2:
        ngay_hen = st.date_input("Ngày hẹn trả (optional)",
                                  value=None, key="admin_sc_ngay_hen")

    ghi_chu_noi_bo = st.text_input("Ghi chú nội bộ (optional)",
                                    key="admin_sc_ghi_chu_nb")

    # ── 6. Items dịch vụ (optional, không trừ kho) ──
    st.markdown("---")
    st.markdown("**Dịch vụ / Linh kiện (optional — không trừ kho)**")

    with st.form("admin_sc_add_item", clear_on_submit=True, border=False):
        c1, c2, c3, c4 = st.columns([2, 4, 1.4, 2])
        with c1:
            loai_dong = st.selectbox("Loại", options=["Dịch vụ", "Linh kiện"],
                                      key="admin_sc_add_loai")
        with c2:
            ten = st.text_input("Tên", key="admin_sc_add_ten")
        with c3:
            sl = st.number_input("SL", min_value=1, value=1, key="admin_sc_add_sl")
        with c4:
            dg = st.number_input("Đơn giá", min_value=0, value=0, step=10000,
                                  key="admin_sc_add_dg")
        if st.form_submit_button("➕ Thêm dòng", use_container_width=True):
            if ten.strip():
                items.append({
                    "loai_dong": loai_dong,
                    "ma_hang": None,
                    "ten_hang": ten.strip(),
                    "so_luong": int(sl),
                    "don_gia": int(dg),
                })
                st.rerun()
            else:
                st.warning("Nhập tên dòng trước khi thêm")

    delete_sc_idx = None
    for i, line in enumerate(items):
        c1, c2, c3, c4 = st.columns([1.5, 4, 2.5, 0.6])
        with c1: st.caption(line.get("loai_dong", "Dịch vụ"))
        with c2: st.markdown(f"**{line['ten_hang']}**")
        with c3:
            st.caption(f"SL={line['so_luong']} · {fmt_vnd(line['don_gia'])} · "
                       f"= {fmt_vnd(line['so_luong'] * line['don_gia'])}")
        with c4:
            if st.button("✕", key=f"admin_sc_del_{i}"):
                delete_sc_idx = i
    if delete_sc_idx is not None:
        items.pop(delete_sc_idx); st.rerun()

    if items:
        tong_dv = sum(it["so_luong"] * it["don_gia"] for it in items)
        st.markdown(f"**Tổng dịch vụ:** {fmt_vnd(tong_dv)}")

    # ── 7. Admin note ──
    admin_note = st.text_area("Lý do admin (optional)", key="admin_sc_note")

    # ── 8. Submit ──
    st.markdown("---")
    if not ten_khach.strip() or not sdt_khach.strip() or not mo_ta_loi.strip():
        st.caption("Điền tên khách + SĐT + mô tả lỗi để tiếp tục")
        return

    created_at = _build_created_at("admin_sc_date", "admin_sc_time")
    summary = [
        f"- **Chi nhánh:** {chi_nhanh}",
        f"- **Ngày tiếp nhận:** {created_at}",
        f"- **NV tiếp nhận:** {nv_chosen['ho_ten']} (id={nv_chosen['id']})",
        f"- **Khách:** {ten_khach} · {sdt_khach}",
        f"- **Loại YC:** {loai_yc}",
        f"- **Items dịch vụ:** {len(items)}",
    ]
    enabled = _confirm_block("admin_sc", summary)

    if st.button("🛡 Tạo phiếu sửa chữa Admin", disabled=not enabled,
                 type="primary", key="admin_sc_submit",
                 use_container_width=True):
        payload = {
            "admin_id": user["id"],
            "created_at": created_at,
            "chi_nhanh": chi_nhanh,
            "nguoi_tiep_nhan_id": nv_chosen["id"],
            "ten_khach": ten_khach.strip(),
            "sdt_khach": sdt_khach.strip(),
            "loai_yeu_cau": loai_yc,
            "hieu_dong_ho": hieu_dh.strip() or None,
            "dac_diem": dac_diem.strip() or None,
            "mo_ta_loi": mo_ta_loi.strip(),
            "khach_tra_truoc": int(khach_tra_truoc),
            "ngay_hen_tra": ngay_hen.isoformat() if ngay_hen else "",
            "ghi_chu_noi_bo": ghi_chu_noi_bo.strip() or None,
            "trang_thai": "Đang sửa",
            "admin_note": admin_note.strip() or None,
            "items": items,
        }
        try:
            result = call_rpc("tao_phieu_sua_chua_admin", {"payload": payload})
        except Exception as e:
            st.error(f"❌ Lỗi RPC: {e}"); return

        if result and result.get("ok"):
            st.success(
                f"✅ Đã tạo {result['ma_phieu']} ({result.get('items_count')} dịch vụ)"
            )
            if sdt_khach and ten_khach:
                upsert_khach_hang_with_update(ten_khach, sdt_khach, chi_nhanh)
            st.session_state[items_key] = []
            _reset_kh_lookup_state("admin_sc_kh")
            st.rerun()
        else:
            st.error(f"❌ {result.get('error', 'Unknown error') if result else 'No response'}")


# ════════════════════════════════════════════════════════════
# B2a — TAB 4: SỬA HĐ POS (search → edit form)
# ════════════════════════════════════════════════════════════
def _render_sua_hd_pos():
    """Entry. 2-step flow: search → edit."""
    st.markdown(
        "Sửa nội dung HĐ POS đã tạo. "
        "**LOCK**: mã HĐ, ngày tạo, chi nhánh, trạng thái."
    )

    if "admin_edit_selected_ma_hd" not in st.session_state:
        st.session_state["admin_edit_selected_ma_hd"] = None

    if st.session_state["admin_edit_selected_ma_hd"] is None:
        _render_search_hd_step()
    else:
        _render_edit_form_step(st.session_state["admin_edit_selected_ma_hd"])


def _clear_edit_form_state():
    for k in list(st.session_state.keys()):
        if k.startswith("adm_edit_form_") or k.startswith("adm_edit_items_"):
            del st.session_state[k]


def _render_search_hd_step():
    """Filter + list HĐ Hoàn thành. Default 7 ngày gần nhất."""
    st.markdown("### 🔍 Tìm HĐ cần sửa")

    col_d1, col_d2, col_cn = st.columns([1, 1, 1.4])
    with col_d1:
        ngay_tu = st.date_input(
            "Từ ngày",
            value=date.today() - timedelta(days=7),
            max_value=date.today(),
            key="adm_edit_tu",
        )
    with col_d2:
        ngay_den = st.date_input(
            "Đến ngày",
            value=date.today(),
            max_value=date.today(),
            key="adm_edit_den",
        )
    with col_cn:
        chi_nhanh_filter = st.selectbox(
            "Chi nhánh",
            options=["Tất cả"] + ALL_BRANCHES,
            key="adm_edit_cn",
        )

    ma_hd_search = st.text_input(
        "🔎 Mã HĐ (optional)",
        placeholder="VD: AHD000050",
        key="adm_edit_ma_search",
    )

    ngay_tu_iso = (
        datetime.combine(ngay_tu, datetime.min.time()).isoformat()
        if ngay_tu else None
    )
    ngay_den_iso = (
        datetime.combine(ngay_den, datetime.max.time()).isoformat()
        if ngay_den else None
    )

    results = search_hd_pos_for_edit(
        chi_nhanh=None if chi_nhanh_filter == "Tất cả" else chi_nhanh_filter,
        ngay_tu=ngay_tu_iso,
        ngay_den=ngay_den_iso,
        ma_hd_search=ma_hd_search.strip() if ma_hd_search.strip() else None,
        limit=50,
    )

    st.caption(f"Tìm thấy {len(results)} HĐ")

    if not results:
        st.info("Không có HĐ Hoàn thành trong khoảng ngày này. "
                "Mở rộng filter hoặc nhập mã HĐ trực tiếp.")
        return

    for hd in results:
        col_info, col_btn = st.columns([5, 1])
        with col_info:
            badge_admin = " 🛡" if hd.get("is_admin_created") else ""
            ngay = (hd.get("created_at") or "")[:10]
            ten_kh = hd.get("ten_khach") or "—"
            st.markdown(
                f"**{hd['ma_hd']}**{badge_admin} · {hd['chi_nhanh']} · "
                f"{ngay} · NV: {hd.get('nguoi_ban') or '—'} · "
                f"KH: {ten_kh} · {fmt_vnd(hd.get('khach_can_tra'))}"
            )
        with col_btn:
            if st.button("✏️ Sửa",
                         key=f"adm_edit_pick_{_safe_key(hd['ma_hd'])}",
                         use_container_width=True):
                st.session_state["admin_edit_selected_ma_hd"] = hd["ma_hd"]
                _clear_edit_form_state()
                st.rerun()


def _render_edit_form_step(ma_hd: str):
    """Form sửa cho 1 HĐ cụ thể."""
    user = get_user()

    if st.button("← Quay lại danh sách", key="adm_edit_back"):
        st.session_state["admin_edit_selected_ma_hd"] = None
        _clear_edit_form_state()
        st.rerun()

    data = load_hd_with_edit_history(ma_hd)
    if not data or not data.get("header"):
        st.error(f"Không tìm thấy HĐ {ma_hd}")
        return

    header = data["header"]
    items_old = data.get("items") or []
    edit_count = data.get("edit_count", 0)
    history = data.get("edit_history") or []

    st.markdown(f"### ✏️ Sửa {ma_hd}")
    badges = []
    if header.get("is_admin_created"):
        badges.append("🛡 ADMIN CREATED")
    if edit_count > 0:
        badges.append(f"✏️ ĐÃ CHỈNH SỬA ({edit_count} lần)")
    if badges:
        st.markdown(" · ".join([f"**{b}**" for b in badges]))

    if history:
        with st.expander(f"📜 Lịch sử chỉnh sửa ({len(history)} lần)"):
            _render_history_compact(history)

    pdt_count = has_active_pdt_for_hd(ma_hd)
    items_locked = pdt_count > 0
    if items_locked:
        st.warning(
            f"⚠️ HĐ này có {pdt_count} phiếu đổi/trả active. "
            "Chỉ sửa được HEADER (NV bán, KH, PTTT, ghi chú). Items bị BLOCK."
        )

    st.markdown("---")
    st.markdown("**🔒 Read-only (LOCKED):**")
    st.markdown(f"- Mã HĐ: `{header['ma_hd']}`")
    st.markdown(f"- Ngày tạo: `{(header.get('created_at') or '')[:19]}`")
    st.markdown(f"- Chi nhánh: `{header['chi_nhanh']}`")
    st.markdown(f"- Trạng thái: `{header['trang_thai']}`")

    st.markdown("---")
    st.markdown("**✏️ Editable:**")

    nv_list = load_all_nhan_vien(include_inactive=True)
    nv_options: list[str] = []
    nv_id_to_label: dict[int, str] = {}
    nv_label_to_id: dict[str, int] = {}
    for nv in nv_list:
        tag = "" if nv.get("active") else " · NGHỈ"
        role_tag = f" [{nv.get('role','?')}]"
        label = f"{nv['ho_ten']}{role_tag}{tag}"
        nv_options.append(label)
        nv_id_to_label[nv["id"]] = label
        nv_label_to_id[label] = nv["id"]

    current_nv_id = header.get("nguoi_ban_id")
    current_label = nv_id_to_label.get(current_nv_id)
    default_index = nv_options.index(current_label) if current_label in nv_options else 0

    new_nv_label = st.selectbox(
        "Người bán", options=nv_options, index=default_index,
        key=f"adm_edit_form_nv_{ma_hd}",
    )
    new_nv_id = nv_label_to_id.get(new_nv_label)

    new_ten_khach, new_sdt_khach, _, _ = _render_kh_lookup_input(
        f"adm_edit_form_kh_{ma_hd}",
        default_ten=header.get("ten_khach") or "",
        default_sdt=header.get("sdt_khach") or "",
        label_sdt="SĐT khách",
        label_ten="Tên khách",
    )

    new_ghi_chu = st.text_area(
        "Ghi chú",
        value=header.get("ghi_chu") or "",
        key=f"adm_edit_form_gc_{ma_hd}",
    )

    items_state_key = f"adm_edit_items_{ma_hd}"
    if items_locked:
        st.markdown("**Items (READ-ONLY do có PDT active):**")
        for it in items_old:
            tt = it.get("thanh_tien") or (int(it["so_luong"]) * int(it["don_gia"]))
            st.markdown(
                f"- {it['ma_hang']} ({it.get('ten_hang') or it['ma_hang']}) "
                f"× {it['so_luong']} @ {fmt_vnd(it['don_gia'])} = {fmt_vnd(tt)}"
            )
        new_items = None
        new_tong_tien_hang = int(header.get("tong_tien_hang") or 0)
    else:
        new_items = _render_editable_items(items_old, items_state_key, ma_hd)
        new_tong_tien_hang = sum(int(i["so_luong"]) * int(i["don_gia"]) for i in new_items)
        st.markdown(f"**Tổng tiền hàng:** {fmt_vnd(new_tong_tien_hang)}")

    gg_key = f"adm_edit_form_gg_{ma_hd}"
    if gg_key not in st.session_state:
        st.session_state[gg_key] = int(header.get("giam_gia_don") or 0)
    new_giam_gia = st.number_input(
        "Giảm giá đơn", min_value=0, step=1000, key=gg_key,
    )
    if new_giam_gia > new_tong_tien_hang:
        st.error(
            f"Giảm giá ({fmt_vnd(new_giam_gia)}) "
            f"vượt tổng tiền hàng ({fmt_vnd(new_tong_tien_hang)})"
        )
    new_khach_can_tra = max(0, new_tong_tien_hang - new_giam_gia)
    st.markdown(f"**Khách cần trả:** {fmt_vnd(new_khach_can_tra)}")

    st.markdown("---")
    st.markdown("**Phương thức thanh toán**")

    tm_key = f"adm_edit_form_tm_{ma_hd}"
    ck_key = f"adm_edit_form_ck_{ma_hd}"
    the_key = f"adm_edit_form_the_{ma_hd}"
    if tm_key not in st.session_state:
        st.session_state[tm_key] = int(header.get("tien_mat") or 0)
    if ck_key not in st.session_state:
        st.session_state[ck_key] = int(header.get("chuyen_khoan") or 0)
    if the_key not in st.session_state:
        st.session_state[the_key] = int(header.get("the") or 0)

    col_q1, col_q2, col_q3 = st.columns(3)
    with col_q1:
        if st.button("💵 Toàn bộ Tiền mặt",
                     key=f"adm_edit_qf_tm_{ma_hd}", use_container_width=True):
            st.session_state[tm_key] = int(new_khach_can_tra)
            st.session_state[ck_key] = 0
            st.session_state[the_key] = 0
            st.rerun()
    with col_q2:
        if st.button("🏦 Toàn bộ Chuyển khoản",
                     key=f"adm_edit_qf_ck_{ma_hd}", use_container_width=True):
            st.session_state[tm_key] = 0
            st.session_state[ck_key] = int(new_khach_can_tra)
            st.session_state[the_key] = 0
            st.rerun()
    with col_q3:
        if st.button("💳 Toàn bộ Thẻ",
                     key=f"adm_edit_qf_the_{ma_hd}", use_container_width=True):
            st.session_state[tm_key] = 0
            st.session_state[ck_key] = 0
            st.session_state[the_key] = int(new_khach_can_tra)
            st.rerun()

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        new_tien_mat = st.number_input("Tiền mặt", min_value=0, step=1000, key=tm_key)
    with col_p2:
        new_chuyen_khoan = st.number_input("Chuyển khoản", min_value=0, step=1000, key=ck_key)
    with col_p3:
        new_the = st.number_input("Thẻ", min_value=0, step=1000, key=the_key)

    tong_pttt = int(new_tien_mat) + int(new_chuyen_khoan) + int(new_the)
    diff = tong_pttt - new_khach_can_tra
    if diff == 0:
        st.success(f"✓ Tổng PTTT: {fmt_vnd(tong_pttt)} (khớp)")
    elif diff > 0:
        st.info(f"Tổng PTTT: {fmt_vnd(tong_pttt)} (khách trả thừa {fmt_vnd(diff)})")
    else:
        st.warning(f"Tổng PTTT: {fmt_vnd(tong_pttt)} (còn thiếu {fmt_vnd(-diff)})")

    st.markdown("---")
    edit_reason = st.text_area(
        "🔴 Lý do sửa (BẮT BUỘC)",
        placeholder="VD: Sửa nhầm đơn giá kính sapphire 350k → 500k theo yêu cầu khách",
        key=f"adm_edit_form_reason_{ma_hd}",
    )

    new_data = {
        "nguoi_ban_id": new_nv_id,
        "ten_khach": (new_ten_khach or "").strip(),
        "sdt_khach": (new_sdt_khach or "").strip(),
        "ghi_chu": (new_ghi_chu or "").strip(),
        "items": new_items,
        "giam_gia_don": int(new_giam_gia),
        "tien_mat": int(new_tien_mat),
        "chuyen_khoan": int(new_chuyen_khoan),
        "the": int(new_the),
    }
    changes = _detect_changes(header, items_old, new_data, items_locked=items_locked)

    if not changes:
        st.info("Chưa có thay đổi nào — chỉnh sửa giá trị nào đó để bật submit.")
        return

    has_valid_reason = bool(edit_reason and edit_reason.strip())
    if not has_valid_reason:
        st.error("⚠️ Phải nhập lý do sửa (không được để trống).")

    st.markdown("---")
    with st.expander(f"⚠️ Xác nhận sửa HĐ ({len(changes)} thay đổi)", expanded=True):
        for label, diff_text in changes.items():
            st.markdown(f"- **{label}**: {diff_text}")

        confirm_text = st.text_input(
            "Gõ **XÁC NHẬN** để bật nút sửa:",
            key=f"adm_edit_form_confirm_{ma_hd}",
        )

        confirm_ok = confirm_text.strip().upper() == "XÁC NHẬN"
        disabled = not (has_valid_reason and confirm_ok)

        if st.button("✏️ Sửa HĐ Admin",
                     disabled=disabled, type="primary",
                     key=f"adm_edit_form_submit_{ma_hd}",
                     use_container_width=True):
            payload = {
                "admin_id": user["id"],
                "ma_hd": ma_hd,
                "edit_reason": edit_reason.strip(),
                "nguoi_ban_id": new_nv_id,
                "ten_khach": (new_ten_khach or "").strip() or None,
                "sdt_khach": (new_sdt_khach or "").strip() or None,
                "ghi_chu": (new_ghi_chu or "").strip() or None,
                "giam_gia_don": int(new_giam_gia),
                "tien_mat": int(new_tien_mat),
                "chuyen_khoan": int(new_chuyen_khoan),
                "the": int(new_the),
            }
            if new_items is not None and not items_locked:
                payload["items"] = new_items

            try:
                result = call_rpc("sua_hoa_don_pos_admin", {"payload": payload})
            except Exception as e:
                st.error(f"❌ Lỗi RPC: {e}")
                return

            if result and result.get("ok"):
                fc = result.get("fields_changed") or []
                if fc:
                    st.success(f"✅ Đã sửa {ma_hd}. Fields changed: {', '.join(fc)}")
                else:
                    st.info(result.get("message", "Không có field nào thay đổi"))
                # Propagate KH name change về khach_hang master nếu có thay đổi
                if new_sdt_khach and new_ten_khach:
                    upsert_khach_hang_with_update(
                        new_ten_khach, new_sdt_khach, header.get("chi_nhanh", "")
                    )
                st.session_state["admin_edit_selected_ma_hd"] = None
                _clear_edit_form_state()
                invalidate_hoa_don_cache()
                st.rerun()
            else:
                err = result.get("error", "Unknown error") if result else "No response"
                st.error(f"❌ {err}")


def _render_editable_items(items_old: list[dict], state_key: str, ma_hd: str) -> list[dict]:
    """Render editable items list. Returns current cart from session_state."""
    if state_key not in st.session_state:
        st.session_state[state_key] = [
            {
                "ma_hang": it["ma_hang"],
                "ten_hang": it.get("ten_hang") or it["ma_hang"],
                "so_luong": int(it["so_luong"]),
                "don_gia": int(it["don_gia"]),
            }
            for it in items_old
        ]
    cart = st.session_state[state_key]

    st.markdown("**Items:**")

    search = st.text_input(
        "Tìm hàng để thêm",
        key=f"adm_edit_search_{ma_hd}",
        placeholder="Mã hoặc tên",
    )
    if search and len(search.strip()) >= 2:
        df = load_hang_hoa()
        if not df.empty:
            kw = search.strip().lower()
            mask = (
                df["ma_hang"].astype(str).str.lower().str.contains(kw, na=False)
                | df["ten_hang"].astype(str).str.lower().str.contains(kw, na=False)
            )
            for _, hh in df[mask].head(6).iterrows():
                ma = str(hh.get("ma_hang") or "")
                ten = str(hh.get("ten_hang") or "")
                gia = int(hh.get("gia_ban") or 0)
                if st.button(
                    f"➕ {ma} — {ten} ({fmt_vnd(gia)})",
                    key=f"adm_edit_add_{_safe_key(ma)}_{ma_hd}",
                    use_container_width=True,
                ):
                    cart.append({
                        "ma_hang": ma, "ten_hang": ten,
                        "so_luong": 1, "don_gia": gia,
                    })
                    st.rerun()

    delete_idx = None
    for i, line in enumerate(cart):
        col_info, col_sl, col_dg, col_x = st.columns([4, 1.4, 2, 0.6])
        with col_info:
            st.markdown(f"📦 **{line['ten_hang']}** ({line['ma_hang']})")
        with col_sl:
            line["so_luong"] = st.number_input(
                "SL", min_value=1, value=int(line["so_luong"]),
                key=f"adm_edit_sl_{i}_{ma_hd}", label_visibility="collapsed",
            )
        with col_dg:
            line["don_gia"] = st.number_input(
                "Đơn giá", min_value=0, value=int(line["don_gia"]), step=1000,
                key=f"adm_edit_dg_{i}_{ma_hd}", label_visibility="collapsed",
            )
        with col_x:
            if st.button("✕", key=f"adm_edit_del_{i}_{ma_hd}"):
                delete_idx = i
    if delete_idx is not None:
        cart.pop(delete_idx)
        st.rerun()

    return cart


def _detect_changes(old_header: dict, old_items: list[dict],
                    new_data: dict, items_locked: bool = False) -> dict:
    """Compare old vs new. Return {label: diff_text} for each changed field.

    Rules:
    - NULL/None/'nan' (DB) vs '' (form) → KHÔNG count là change
    - Money fields compare as int
    - Items: deep diff by ma_hang (add/remove/SL/ĐG change)
    """
    changes: dict[str, str] = {}

    def _norm(v) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() == "nan" else s

    if old_header.get("nguoi_ban_id") != new_data.get("nguoi_ban_id"):
        old_name = old_header.get("nguoi_ban") or "—"
        changes["Người bán"] = (
            f"`{old_name}` → ID={new_data.get('nguoi_ban_id')}"
        )

    for label, key in [
        ("Tên khách", "ten_khach"),
        ("SĐT khách", "sdt_khach"),
        ("Ghi chú", "ghi_chu"),
    ]:
        old_v = _norm(old_header.get(key))
        new_v = _norm(new_data.get(key))
        if old_v != new_v:
            changes[label] = f"`{old_v or '—'}` → `{new_v or '—'}`"

    for label, key in [
        ("Giảm giá đơn", "giam_gia_don"),
        ("Tiền mặt", "tien_mat"),
        ("Chuyển khoản", "chuyen_khoan"),
        ("Thẻ", "the"),
    ]:
        old_v = int(old_header.get(key) or 0)
        new_v = int(new_data.get(key) or 0)
        if old_v != new_v:
            changes[label] = f"{fmt_vnd(old_v)} → {fmt_vnd(new_v)}"

    if not items_locked and new_data.get("items") is not None:
        items_diffs = _diff_items(old_items, new_data["items"])
        if items_diffs:
            changes["Items"] = "  \n  " + "  \n  ".join(items_diffs)

    return changes


def _diff_items(old_items: list[dict], new_items: list[dict]) -> list[str]:
    """Deep diff items by ma_hang. Returns human-readable diff lines."""
    old_map: dict[str, list[dict]] = {}
    for it in old_items:
        old_map.setdefault(it["ma_hang"], []).append(it)
    new_map: dict[str, list[dict]] = {}
    for it in new_items:
        new_map.setdefault(it["ma_hang"], []).append(it)

    diffs: list[str] = []
    all_ma = sorted(set(old_map.keys()) | set(new_map.keys()))
    for ma in all_ma:
        old_list = old_map.get(ma, [])
        new_list = new_map.get(ma, [])
        old_total_sl = sum(int(x["so_luong"]) for x in old_list)
        new_total_sl = sum(int(x["so_luong"]) for x in new_list)
        ten = ""
        if new_list:
            ten = new_list[0].get("ten_hang") or ma
        elif old_list:
            ten = old_list[0].get("ten_hang") or ma

        if not old_list and new_list:
            dg = int(new_list[0]["don_gia"])
            diffs.append(f"➕ {ma} ({ten}) × {new_total_sl} @ {fmt_vnd(dg)}")
        elif old_list and not new_list:
            dg = int(old_list[0]["don_gia"])
            diffs.append(f"➖ {ma} ({ten}) × {old_total_sl} @ {fmt_vnd(dg)}")
        else:
            old_dg = int(old_list[0]["don_gia"])
            new_dg = int(new_list[0]["don_gia"])
            sl_changed = old_total_sl != new_total_sl
            dg_changed = old_dg != new_dg
            if sl_changed and dg_changed:
                diffs.append(
                    f"✏️ {ma} ({ten}) SL {old_total_sl}→{new_total_sl}, "
                    f"ĐG {fmt_vnd(old_dg)}→{fmt_vnd(new_dg)}"
                )
            elif sl_changed:
                diffs.append(f"✏️ {ma} ({ten}) SL {old_total_sl}→{new_total_sl}")
            elif dg_changed:
                diffs.append(f"✏️ {ma} ({ten}) ĐG {fmt_vnd(old_dg)}→{fmt_vnd(new_dg)}")

    return diffs


def _render_history_compact(history: list[dict]):
    """Render history list compact, 1 line per entry. RPC returns DESC."""
    for h in history:
        edited_at = (h.get("edited_at") or "")[:16].replace("T", " ")
        edited_by = h.get("edited_by_name") or "—"
        fields = h.get("fields_changed") or []
        reason = (h.get("edit_reason") or "").strip()
        if reason:
            reason_display = (
                f'"{reason[:60]}{"..." if len(reason) > 60 else ""}"'
            )
        else:
            reason_display = "_(không ghi)_"
        st.markdown(
            f"- `{edited_at}` · **{edited_by}** · "
            f"changed: `{', '.join(fields) or '—'}` · {reason_display}"
        )


# ════════════════════════════════════════════════════════════
# B2b — SUB-TAB: SỬA PHIẾU ĐỔI/TRẢ
# ════════════════════════════════════════════════════════════
def _render_sua_doi_tra():
    """Entry. 2-step flow: search → edit."""
    st.markdown(
        "Sửa nội dung phiếu đổi/trả đã tạo. "
        "**LOCK**: ma_pdt, ngày tạo, chi nhánh, trạng thái, NV tạo, HĐ gốc. "
        "**BLOCK items_tra** (hủy phiếu rồi tạo lại nếu cần đổi)."
    )

    if "admin_edit_pdt_selected_ma_pdt" not in st.session_state:
        st.session_state["admin_edit_pdt_selected_ma_pdt"] = None

    if st.session_state["admin_edit_pdt_selected_ma_pdt"] is None:
        _render_search_pdt_step()
    else:
        _render_edit_pdt_form_step(
            st.session_state["admin_edit_pdt_selected_ma_pdt"]
        )


def _clear_edit_pdt_form_state():
    for k in list(st.session_state.keys()):
        if k.startswith("adm_edit_pdt_form_") or k.startswith("adm_edit_pdt_items_"):
            del st.session_state[k]


def _render_search_pdt_step():
    st.markdown("### 🔍 Tìm phiếu đổi/trả cần sửa")

    col_d1, col_d2, col_cn = st.columns([1, 1, 1.4])
    with col_d1:
        ngay_tu = st.date_input(
            "Từ ngày", value=date.today() - timedelta(days=7),
            max_value=date.today(), key="adm_edit_pdt_tu",
        )
    with col_d2:
        ngay_den = st.date_input(
            "Đến ngày", value=date.today(),
            max_value=date.today(), key="adm_edit_pdt_den",
        )
    with col_cn:
        chi_nhanh_filter = st.selectbox(
            "Chi nhánh", options=["Tất cả"] + ALL_BRANCHES,
            key="adm_edit_pdt_cn",
        )

    ma_pdt_search = st.text_input(
        "🔎 Mã phiếu (optional)", placeholder="VD: AHDD000004",
        key="adm_edit_pdt_ma_search",
    )

    ngay_tu_iso = (
        datetime.combine(ngay_tu, datetime.min.time()).isoformat()
        if ngay_tu else None
    )
    ngay_den_iso = (
        datetime.combine(ngay_den, datetime.max.time()).isoformat()
        if ngay_den else None
    )

    results = search_pdt_for_edit(
        chi_nhanh=None if chi_nhanh_filter == "Tất cả" else chi_nhanh_filter,
        ngay_tu=ngay_tu_iso, ngay_den=ngay_den_iso,
        ma_pdt_search=ma_pdt_search.strip() if ma_pdt_search.strip() else None,
        limit=50,
    )

    st.caption(f"Tìm thấy {len(results)} phiếu")
    if not results:
        st.info("Không có phiếu Hoàn thành trong khoảng này.")
        return

    for pdt in results:
        col_info, col_btn = st.columns([5, 1])
        with col_info:
            badge_admin = " 🛡" if pdt.get("is_admin_created") else ""
            ngay = (pdt.get("created_at") or "")[:10]
            cl = int(pdt.get("chenh_lech") or 0)
            cl_str = (
                f"+{fmt_vnd(cl)}" if cl > 0
                else (f"−{fmt_vnd(-cl)}" if cl < 0 else "đổi ngang")
            )
            ten_kh = pdt.get("ten_khach") or "—"
            st.markdown(
                f"**{pdt['ma_pdt']}**{badge_admin} · từ {pdt.get('ma_hd_goc', '—')} · "
                f"{pdt['chi_nhanh']} · {ngay} · {pdt.get('loai_phieu', '—')} · "
                f"{cl_str} · KH: {ten_kh}"
            )
        with col_btn:
            if st.button(
                "✏️ Sửa",
                key=f"adm_edit_pdt_pick_{_safe_key(pdt['ma_pdt'])}",
                use_container_width=True,
            ):
                st.session_state["admin_edit_pdt_selected_ma_pdt"] = pdt["ma_pdt"]
                _clear_edit_pdt_form_state()
                st.rerun()


def _render_edit_pdt_form_step(ma_pdt: str):
    user = get_user()

    if st.button("← Quay lại danh sách", key="adm_edit_pdt_back"):
        st.session_state["admin_edit_pdt_selected_ma_pdt"] = None
        _clear_edit_pdt_form_state()
        st.rerun()

    data = load_record_with_history("phieu_doi_tra_pos", ma_pdt)
    if not data or not data.get("header"):
        st.error(f"Không tìm thấy phiếu {ma_pdt}")
        return

    header = data["header"]
    items_all = data.get("items") or []
    items_tra = [it for it in items_all if it.get("kieu") == "tra"]
    items_moi_old = [it for it in items_all if it.get("kieu") == "moi"]
    edit_count = data.get("edit_count", 0)
    history = data.get("edit_history") or []

    st.markdown(f"### ✏️ Sửa {ma_pdt}")
    badges = []
    if header.get("is_admin_created"):
        badges.append("🛡 ADMIN CREATED")
    if edit_count > 0:
        badges.append(f"✏️ ĐÃ CHỈNH SỬA ({edit_count} lần)")
    if badges:
        st.markdown(" · ".join([f"**{b}**" for b in badges]))

    if history:
        with st.expander(f"📜 Lịch sử chỉnh sửa ({len(history)} lần)"):
            _render_history_compact(history)

    st.markdown("---")
    st.markdown("**🔒 Read-only (LOCKED):**")
    st.markdown(f"- Mã phiếu: `{header['ma_pdt']}`")
    st.markdown(f"- HĐ gốc: `{header.get('ma_hd_goc', '—')}`")
    st.markdown(f"- Ngày tạo: `{(header.get('created_at') or '')[:19]}`")
    st.markdown(f"- Chi nhánh: `{header['chi_nhanh']}`")
    st.markdown(f"- Trạng thái: `{header['trang_thai']}`")
    st.markdown(f"- Người tạo: `{header.get('nguoi_tao', '—')}`")
    st.markdown(f"- Loại phiếu: `{header.get('loai_phieu', '—')}`")
    st.markdown(
        f"- **Tiền hàng trả: {fmt_vnd(header.get('tien_hang_tra', 0))}** "
        f"(không sửa được — items_tra blocked)"
    )

    st.markdown("---")
    st.markdown("**📦 Items trả (READ-ONLY):**")
    if not items_tra:
        st.caption("Không có items trả")
    else:
        for it in items_tra:
            tt = it.get("thanh_tien") or (int(it["so_luong"]) * int(it["don_gia"]))
            st.markdown(
                f"- {it['ma_hang']} ({it.get('ten_hang') or it['ma_hang']}) "
                f"× {it['so_luong']} @ {fmt_vnd(it['don_gia'])} = {fmt_vnd(tt)}"
            )
    st.caption(
        "⚠️ items_tra BLOCKED. Cần đổi → hủy phiếu (POS) rồi tạo lại bằng tab 'Tạo'."
    )

    st.markdown("---")
    st.markdown("**✏️ Editable:**")

    new_ten_khach, new_sdt_khach, _, _ = _render_kh_lookup_input(
        f"adm_edit_pdt_form_kh_{ma_pdt}",
        default_ten=header.get("ten_khach") or "",
        default_sdt=header.get("sdt_khach") or "",
        label_sdt="SĐT khách",
        label_ten="Tên khách",
    )

    new_ghi_chu = st.text_area(
        "Ghi chú",
        value=header.get("ghi_chu") or "",
        key=f"adm_edit_pdt_form_gc_{ma_pdt}",
    )

    items_moi_state_key = f"adm_edit_pdt_items_moi_{ma_pdt}"
    new_items_moi = _render_editable_items(
        items_moi_old, items_moi_state_key, ma_pdt
    )
    new_tien_hang_moi = sum(
        int(i["so_luong"]) * int(i["don_gia"]) for i in new_items_moi
    )
    st.markdown(f"**Tổng tiền hàng mới:** {fmt_vnd(new_tien_hang_moi)}")

    tien_hang_tra = int(header.get("tien_hang_tra") or 0)
    new_chenh_lech = new_tien_hang_moi - tien_hang_tra

    if new_chenh_lech > 0:
        st.markdown(f"**Chênh lệch:** +{fmt_vnd(new_chenh_lech)} (khách bù)")
    elif new_chenh_lech < 0:
        st.markdown(f"**Chênh lệch:** −{fmt_vnd(-new_chenh_lech)} (shop hoàn)")
    else:
        st.markdown("**Chênh lệch:** 0 (đổi ngang)")

    st.markdown("---")
    if new_chenh_lech > 0:
        st.caption(f"Khách cần bù {fmt_vnd(new_chenh_lech)}")

        tm_key = f"adm_edit_pdt_form_tm_{ma_pdt}"
        ck_key = f"adm_edit_pdt_form_ck_{ma_pdt}"
        the_key = f"adm_edit_pdt_form_the_{ma_pdt}"
        if tm_key not in st.session_state:
            st.session_state[tm_key] = int(header.get("tien_mat") or 0)
        if ck_key not in st.session_state:
            st.session_state[ck_key] = int(header.get("chuyen_khoan") or 0)
        if the_key not in st.session_state:
            st.session_state[the_key] = int(header.get("the") or 0)

        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            if st.button("💵 Toàn bộ Tiền mặt",
                         key=f"adm_edit_pdt_qf_tm_{ma_pdt}",
                         use_container_width=True):
                st.session_state[tm_key] = int(new_chenh_lech)
                st.session_state[ck_key] = 0
                st.session_state[the_key] = 0
                st.rerun()
        with col_q2:
            if st.button("🏦 Toàn bộ Chuyển khoản",
                         key=f"adm_edit_pdt_qf_ck_{ma_pdt}",
                         use_container_width=True):
                st.session_state[tm_key] = 0
                st.session_state[ck_key] = int(new_chenh_lech)
                st.session_state[the_key] = 0
                st.rerun()
        with col_q3:
            if st.button("💳 Toàn bộ Thẻ",
                         key=f"adm_edit_pdt_qf_the_{ma_pdt}",
                         use_container_width=True):
                st.session_state[tm_key] = 0
                st.session_state[ck_key] = 0
                st.session_state[the_key] = int(new_chenh_lech)
                st.rerun()

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            new_tien_mat = st.number_input("Tiền mặt", min_value=0, step=1000, key=tm_key)
        with col_p2:
            new_chuyen_khoan = st.number_input("Chuyển khoản", min_value=0, step=1000, key=ck_key)
        with col_p3:
            new_the = st.number_input("Thẻ", min_value=0, step=1000, key=the_key)

        tong_pttt = int(new_tien_mat) + int(new_chuyen_khoan) + int(new_the)
        diff = tong_pttt - new_chenh_lech
        if diff == 0:
            st.success(f"✓ Tổng PTTT: {fmt_vnd(tong_pttt)} (khớp)")
        elif diff > 0:
            st.info(f"Tổng PTTT: {fmt_vnd(tong_pttt)} (thừa {fmt_vnd(diff)})")
        else:
            st.warning(f"Tổng PTTT: {fmt_vnd(tong_pttt)} (thiếu {fmt_vnd(-diff)})")
    elif new_chenh_lech < 0:
        st.caption(f"Shop hoàn {fmt_vnd(-new_chenh_lech)} — chỉ tiền mặt (số âm)")
        new_tien_mat = new_chenh_lech
        new_chuyen_khoan = 0
        new_the = 0
    else:
        new_tien_mat = 0
        new_chuyen_khoan = 0
        new_the = 0

    st.markdown("---")
    edit_reason = st.text_area(
        "🔴 Lý do sửa (BẮT BUỘC)",
        placeholder="VD: Khách đổi sang đồng hồ giá cao hơn, cộng thêm chênh lệch",
        key=f"adm_edit_pdt_form_reason_{ma_pdt}",
    )

    new_data = {
        "ten_khach": (new_ten_khach or "").strip(),
        "sdt_khach": (new_sdt_khach or "").strip(),
        "ghi_chu": (new_ghi_chu or "").strip(),
        "items_moi": new_items_moi,
        "tien_mat": int(new_tien_mat),
        "chuyen_khoan": int(new_chuyen_khoan),
        "the": int(new_the),
    }
    changes = _detect_changes_pdt(header, items_moi_old, new_data)

    if not changes:
        st.info("Chưa có thay đổi nào — chỉnh sửa giá trị nào đó để bật submit.")
        return

    has_valid_reason = bool(edit_reason and edit_reason.strip())
    if not has_valid_reason:
        st.error("⚠️ Phải nhập lý do sửa (không được để trống).")

    st.markdown("---")
    with st.expander(f"⚠️ Xác nhận sửa phiếu ({len(changes)} thay đổi)", expanded=True):
        for label, diff_text in changes.items():
            st.markdown(f"- **{label}**: {diff_text}")

        confirm_text = st.text_input(
            "Gõ **XÁC NHẬN** để bật nút sửa:",
            key=f"adm_edit_pdt_form_confirm_{ma_pdt}",
        )
        confirm_ok = confirm_text.strip().upper() == "XÁC NHẬN"
        disabled = not (has_valid_reason and confirm_ok)

        if st.button(
            "✏️ Sửa Phiếu Đổi/Trả Admin",
            disabled=disabled, type="primary",
            key=f"adm_edit_pdt_form_submit_{ma_pdt}",
            use_container_width=True,
        ):
            payload = {
                "admin_id": user["id"],
                "ma_pdt": ma_pdt,
                "edit_reason": edit_reason.strip(),
                "ten_khach": (new_ten_khach or "").strip() or None,
                "sdt_khach": (new_sdt_khach or "").strip() or None,
                "ghi_chu": (new_ghi_chu or "").strip() or None,
                "tien_mat": int(new_tien_mat),
                "chuyen_khoan": int(new_chuyen_khoan),
                "the": int(new_the),
                "items_moi": new_items_moi,
            }
            try:
                result = call_rpc("sua_phieu_doi_tra_pos_admin", {"payload": payload})
            except Exception as e:
                st.error(f"❌ Lỗi RPC: {e}")
                return

            if result and result.get("ok"):
                fc = result.get("fields_changed") or []
                if fc:
                    st.success(f"✅ Đã sửa {ma_pdt}. Fields changed: {', '.join(fc)}")
                else:
                    st.info(result.get("message", "Không có field nào thay đổi"))
                if new_sdt_khach and new_ten_khach:
                    upsert_khach_hang_with_update(
                        new_ten_khach, new_sdt_khach, header.get("chi_nhanh", "")
                    )
                st.session_state["admin_edit_pdt_selected_ma_pdt"] = None
                _clear_edit_pdt_form_state()
                invalidate_hoa_don_cache()
                st.rerun()
            else:
                err = result.get("error", "Unknown error") if result else "No response"
                st.error(f"❌ {err}")


def _detect_changes_pdt(old_header, old_items_moi, new_data):
    """Detect changes for PDT edit. Items diff for items_moi only (items_tra blocked)."""
    changes: dict[str, str] = {}

    def _norm(v):
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() == "nan" else s

    for label, key in [
        ("Tên khách", "ten_khach"),
        ("SĐT khách", "sdt_khach"),
        ("Ghi chú", "ghi_chu"),
    ]:
        old_v = _norm(old_header.get(key))
        new_v = _norm(new_data.get(key))
        if old_v != new_v:
            changes[label] = f"`{old_v or '—'}` → `{new_v or '—'}`"

    for label, key in [
        ("Tiền mặt", "tien_mat"),
        ("Chuyển khoản", "chuyen_khoan"),
        ("Thẻ", "the"),
    ]:
        old_v = int(old_header.get(key) or 0)
        new_v = int(new_data.get(key) or 0)
        if old_v != new_v:
            changes[label] = f"{fmt_vnd(old_v)} → {fmt_vnd(new_v)}"

    if new_data.get("items_moi") is not None:
        items_diffs = _diff_items(old_items_moi, new_data["items_moi"])
        if items_diffs:
            changes["Items mới"] = "  \n  " + "  \n  ".join(items_diffs)

    return changes


# ════════════════════════════════════════════════════════════
# B2b — SUB-TAB: SỬA PHIẾU SỬA CHỮA
# ════════════════════════════════════════════════════════════
_SC_STATUS_OPTIONS_DB = ["Đang sửa", "Hoàn thành", "Chờ giao khách"]


def _render_sua_sua_chua():
    """Entry. 2-step flow: search → edit."""
    st.markdown(
        "Sửa nội dung phiếu sửa chữa. "
        "**LOCK**: ma_phieu, ngày tạo, chi nhánh, NV tạo. "
        "**Items READ-ONLY** nếu phiếu đã convert APSC."
    )

    if "admin_edit_sc_selected_ma_phieu" not in st.session_state:
        st.session_state["admin_edit_sc_selected_ma_phieu"] = None

    if st.session_state["admin_edit_sc_selected_ma_phieu"] is None:
        _render_search_sc_step()
    else:
        _render_edit_sc_form_step(
            st.session_state["admin_edit_sc_selected_ma_phieu"]
        )


def _clear_edit_sc_form_state():
    for k in list(st.session_state.keys()):
        if k.startswith("adm_edit_sc_form_") or k.startswith("adm_edit_sc_items_"):
            del st.session_state[k]


def _render_search_sc_step():
    st.markdown("### 🔍 Tìm phiếu sửa chữa cần sửa")

    col_d1, col_d2, col_cn, col_tt = st.columns([1, 1, 1.4, 1.5])
    with col_d1:
        ngay_tu = st.date_input(
            "Từ ngày", value=date.today() - timedelta(days=7),
            max_value=date.today(), key="adm_edit_sc_tu",
        )
    with col_d2:
        ngay_den = st.date_input(
            "Đến ngày", value=date.today(),
            max_value=date.today(), key="adm_edit_sc_den",
        )
    with col_cn:
        chi_nhanh_filter = st.selectbox(
            "Chi nhánh", options=["Tất cả"] + ALL_BRANCHES,
            key="adm_edit_sc_cn",
        )
    with col_tt:
        status_filter = st.selectbox(
            "Trạng thái",
            options=["Tất cả (trừ Đã hủy)"] + _SC_STATUS_OPTIONS_DB,
            key="adm_edit_sc_status",
        )

    ma_phieu_search = st.text_input(
        "🔎 Mã phiếu (optional)", placeholder="VD: SC000019",
        key="adm_edit_sc_ma_search",
    )

    ngay_tu_iso = (
        datetime.combine(ngay_tu, datetime.min.time()).isoformat()
        if ngay_tu else None
    )
    ngay_den_iso = (
        datetime.combine(ngay_den, datetime.max.time()).isoformat()
        if ngay_den else None
    )

    results = search_sc_for_edit(
        chi_nhanh=None if chi_nhanh_filter == "Tất cả" else chi_nhanh_filter,
        trang_thai=None if status_filter == "Tất cả (trừ Đã hủy)" else status_filter,
        ngay_tu=ngay_tu_iso, ngay_den=ngay_den_iso,
        ma_phieu_search=ma_phieu_search.strip() if ma_phieu_search.strip() else None,
        limit=50,
    )

    st.caption(f"Tìm thấy {len(results)} phiếu")
    if not results:
        st.info("Không có phiếu trong khoảng này.")
        return

    for sc in results:
        col_info, col_btn = st.columns([5, 1])
        with col_info:
            badge_admin = " 🛡" if sc.get("is_admin_created") else ""
            ngay = (sc.get("created_at") or "")[:10]
            ten_kh = sc.get("ten_khach") or "—"
            hieu = sc.get("hieu_dong_ho") or ""
            tt = sc.get("trang_thai") or "—"
            st.markdown(
                f"**{sc['ma_phieu']}**{badge_admin} · {sc['chi_nhanh']} · {ngay} · "
                f"`{tt}` · KH: {ten_kh}"
                + (f" · {hieu}" if hieu else "")
            )
        with col_btn:
            if st.button(
                "✏️ Sửa",
                key=f"adm_edit_sc_pick_{_safe_key(sc['ma_phieu'])}",
                use_container_width=True,
            ):
                st.session_state["admin_edit_sc_selected_ma_phieu"] = sc["ma_phieu"]
                _clear_edit_sc_form_state()
                st.rerun()


def _render_edit_sc_form_step(ma_phieu: str):
    user = get_user()

    if st.button("← Quay lại danh sách", key="adm_edit_sc_back"):
        st.session_state["admin_edit_sc_selected_ma_phieu"] = None
        _clear_edit_sc_form_state()
        st.rerun()

    data = load_record_with_history("phieu_sua_chua", ma_phieu)
    if not data or not data.get("header"):
        st.error(f"Không tìm thấy phiếu {ma_phieu}")
        return

    header = data["header"]
    items_old = data.get("items") or []
    edit_count = data.get("edit_count", 0)
    history = data.get("edit_history") or []

    # Check has_apsc qua RPC helper
    try:
        check_result = call_rpc("_admin_check_can_edit_sc", {"p_ma_phieu": ma_phieu})
        has_apsc = bool((check_result or {}).get("has_apsc"))
        apsc_detail = (check_result or {}).get("apsc_detail") or ""
    except Exception:
        has_apsc = False
        apsc_detail = ""

    st.markdown(f"### ✏️ Sửa {ma_phieu}")
    badges = []
    if header.get("is_admin_created"):
        badges.append("🛡 ADMIN CREATED")
    if edit_count > 0:
        badges.append(f"✏️ ĐÃ CHỈNH SỬA ({edit_count} lần)")
    if badges:
        st.markdown(" · ".join([f"**{b}**" for b in badges]))

    if has_apsc:
        st.warning(
            "⚠️ Phiếu đã convert APSC. Items READ-ONLY, chỉ sửa header."
            + (f"  \n_{apsc_detail[:120]}_" if apsc_detail else "")
        )

    if history:
        with st.expander(f"📜 Lịch sử chỉnh sửa ({len(history)} lần)"):
            _render_history_compact(history)

    st.markdown("---")
    st.markdown("**🔒 Read-only (LOCKED):**")
    st.markdown(f"- Mã phiếu: `{header['ma_phieu']}`")
    st.markdown(f"- Ngày tiếp nhận: `{(header.get('ngay_tiep_nhan') or '')[:19]}`")
    st.markdown(f"- Chi nhánh: `{header['chi_nhanh']}`")
    st.markdown(f"- Người tạo: `{header.get('created_by', '—')}`")

    st.markdown("---")
    st.markdown("**✏️ Editable:**")

    # 2-cột layout
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**👤 Khách + NV + Thời gian**")
        new_ten_khach, new_sdt_khach, _, _ = _render_kh_lookup_input(
            f"adm_edit_sc_form_kh_{ma_phieu}",
            default_ten=header.get("ten_khach") or "",
            default_sdt=header.get("sdt_khach") or "",
            label_sdt="SĐT khách",
            label_ten="Tên khách",
        )

        new_nguoi_tn = st.text_input(
            "NV tiếp nhận",
            value=header.get("nguoi_tiep_nhan") or "",
            key=f"adm_edit_sc_form_nv_{ma_phieu}",
        )

        cur_hen = header.get("ngay_hen_tra")
        try:
            cur_hen_date = datetime.fromisoformat(cur_hen).date() if cur_hen else None
        except Exception:
            cur_hen_date = None
        new_ngay_hen = st.date_input(
            "Ngày hẹn trả (optional)",
            value=cur_hen_date,
            key=f"adm_edit_sc_form_hen_{ma_phieu}",
        )

        new_khach_tra_truoc = st.number_input(
            "Khách trả trước",
            min_value=0,
            value=int(header.get("khach_tra_truoc") or 0),
            step=1000,
            key=f"adm_edit_sc_form_tra_truoc_{ma_phieu}",
        )

        all_status_options = _SC_STATUS_OPTIONS_DB + ["Đã hủy"]
        cur_tt = header.get("trang_thai", "Đang sửa")
        default_idx = (
            all_status_options.index(cur_tt)
            if cur_tt in all_status_options else 0
        )
        new_trang_thai = st.selectbox(
            "Trạng thái",
            options=all_status_options,
            index=default_idx,
            key=f"adm_edit_sc_form_tt_{ma_phieu}",
            help="Lưu ý: 'Đã hủy' là one-way (sau đó không sửa được).",
        )

    with col_right:
        st.markdown("**🔧 Chi tiết sửa chữa**")
        loai_options = ["Sửa chữa", "Bảo hành", "Bảo dưỡng", "Khác"]
        cur_loai = header.get("loai_yeu_cau", "Sửa chữa")
        new_loai_yc = st.selectbox(
            "Loại yêu cầu",
            options=loai_options,
            index=loai_options.index(cur_loai) if cur_loai in loai_options else 0,
            key=f"adm_edit_sc_form_loai_{ma_phieu}",
        )
        new_hieu_dh = st.text_input(
            "Hiệu đồng hồ",
            value=header.get("hieu_dong_ho") or "",
            key=f"adm_edit_sc_form_hieu_{ma_phieu}",
        )
        new_dac_diem = st.text_input(
            "Đặc điểm",
            value=header.get("dac_diem") or "",
            key=f"adm_edit_sc_form_dac_{ma_phieu}",
        )
        new_mo_ta = st.text_area(
            "Mô tả lỗi",
            value=header.get("mo_ta_loi") or "",
            key=f"adm_edit_sc_form_mota_{ma_phieu}",
        )
        new_ghi_chu_nb = st.text_area(
            "Ghi chú nội bộ",
            value=header.get("ghi_chu_noi_bo") or "",
            key=f"adm_edit_sc_form_ghichu_{ma_phieu}",
        )

    # Items section (full width)
    st.markdown("---")
    if has_apsc:
        st.markdown("**Dịch vụ / Linh kiện (READ-ONLY do có APSC):**")
        if not items_old:
            st.caption("Không có items")
        else:
            for it in items_old:
                tt_val = int(it["so_luong"]) * int(it["don_gia"])
                loai = it.get("loai_dong") or "Dịch vụ"
                st.markdown(
                    f"- [{loai}] {it.get('ten_hang', '—')} "
                    f"× {it['so_luong']} @ {fmt_vnd(it['don_gia'])} = {fmt_vnd(tt_val)}"
                )
        new_items = None
    else:
        st.markdown("**Dịch vụ / Linh kiện (KHÔNG đụng kho):**")
        items_state_key = f"adm_edit_sc_items_{ma_phieu}"
        new_items = _render_editable_sc_items(items_old, items_state_key, ma_phieu)
        if new_items:
            tong_dv = sum(int(it["so_luong"]) * int(it["don_gia"]) for it in new_items)
            st.markdown(f"**Tổng dịch vụ:** {fmt_vnd(tong_dv)}")

    st.markdown("---")
    edit_reason = st.text_area(
        "🔴 Lý do sửa (BẮT BUỘC)",
        placeholder="VD: Sửa nhầm hiệu đồng hồ — Casio thay vì Citizen",
        key=f"adm_edit_sc_form_reason_{ma_phieu}",
    )

    new_data = {
        "ten_khach": (new_ten_khach or "").strip(),
        "sdt_khach": (new_sdt_khach or "").strip(),
        "loai_yeu_cau": new_loai_yc,
        "hieu_dong_ho": (new_hieu_dh or "").strip(),
        "dac_diem": (new_dac_diem or "").strip(),
        "mo_ta_loi": (new_mo_ta or "").strip(),
        "ghi_chu_noi_bo": (new_ghi_chu_nb or "").strip(),
        "nguoi_tiep_nhan": (new_nguoi_tn or "").strip(),
        "trang_thai": new_trang_thai,
        "khach_tra_truoc": int(new_khach_tra_truoc),
        "ngay_hen_tra": new_ngay_hen.isoformat() if new_ngay_hen else "",
        "items": new_items,
    }
    changes = _detect_changes_sc(header, items_old, new_data, items_locked=has_apsc)

    if not changes:
        st.info("Chưa có thay đổi nào — chỉnh sửa giá trị nào đó để bật submit.")
        return

    has_valid_reason = bool(edit_reason and edit_reason.strip())
    if not has_valid_reason:
        st.error("⚠️ Phải nhập lý do sửa (không được để trống).")

    st.markdown("---")
    with st.expander(f"⚠️ Xác nhận sửa phiếu ({len(changes)} thay đổi)", expanded=True):
        for label, diff_text in changes.items():
            st.markdown(f"- **{label}**: {diff_text}")

        confirm_text = st.text_input(
            "Gõ **XÁC NHẬN** để bật nút sửa:",
            key=f"adm_edit_sc_form_confirm_{ma_phieu}",
        )
        confirm_ok = confirm_text.strip().upper() == "XÁC NHẬN"
        disabled = not (has_valid_reason and confirm_ok)

        if st.button(
            "✏️ Sửa Phiếu Sửa Chữa Admin",
            disabled=disabled, type="primary",
            key=f"adm_edit_sc_form_submit_{ma_phieu}",
            use_container_width=True,
        ):
            payload = {
                "admin_id": user["id"],
                "ma_phieu": ma_phieu,
                "edit_reason": edit_reason.strip(),
                "ten_khach": new_data["ten_khach"] or None,
                "sdt_khach": new_data["sdt_khach"] or None,
                "loai_yeu_cau": new_data["loai_yeu_cau"],
                "hieu_dong_ho": new_data["hieu_dong_ho"] or None,
                "dac_diem": new_data["dac_diem"] or None,
                "mo_ta_loi": new_data["mo_ta_loi"] or None,
                "ghi_chu_noi_bo": new_data["ghi_chu_noi_bo"] or None,
                "nguoi_tiep_nhan": new_data["nguoi_tiep_nhan"] or None,
                "trang_thai": new_data["trang_thai"],
                "khach_tra_truoc": new_data["khach_tra_truoc"],
                "ngay_hen_tra": new_data["ngay_hen_tra"],
            }
            if new_items is not None and not has_apsc:
                payload["items"] = new_items

            try:
                result = call_rpc("sua_phieu_sua_chua_admin", {"payload": payload})
            except Exception as e:
                st.error(f"❌ Lỗi RPC: {e}")
                return

            if result and result.get("ok"):
                fc = result.get("fields_changed") or []
                if fc:
                    st.success(f"✅ Đã sửa {ma_phieu}. Fields changed: {', '.join(fc)}")
                else:
                    st.info(result.get("message", "Không có field nào thay đổi"))
                if new_sdt_khach and new_ten_khach:
                    upsert_khach_hang_with_update(
                        new_ten_khach, new_sdt_khach, header.get("chi_nhanh", "")
                    )
                st.session_state["admin_edit_sc_selected_ma_phieu"] = None
                _clear_edit_sc_form_state()
                st.rerun()
            else:
                err = result.get("error", "Unknown error") if result else "No response"
                st.error(f"❌ {err}")


def _render_editable_sc_items(items_old, state_key, ma_phieu):
    """Items list editable cho phiếu sửa chữa (no stock).

    Khác `_render_editable_items`: không search hang_hoa (sửa chữa items
    thường là dịch vụ tự nhập). Manual form add.
    """
    if state_key not in st.session_state:
        st.session_state[state_key] = [
            {
                "loai_dong": it.get("loai_dong") or "Dịch vụ",
                "ma_hang": it.get("ma_hang"),
                "ten_hang": it.get("ten_hang") or "",
                "so_luong": int(it["so_luong"]),
                "don_gia": int(it["don_gia"]),
                "ghi_chu": it.get("ghi_chu") or "",
            }
            for it in items_old
        ]
    items = st.session_state[state_key]

    with st.form(f"adm_edit_sc_add_item_{ma_phieu}", clear_on_submit=True, border=False):
        c1, c2, c3, c4 = st.columns([2, 4, 1.4, 2])
        with c1:
            loai_dong = st.selectbox(
                "Loại", options=["Dịch vụ", "Linh kiện"],
                key=f"adm_edit_sc_add_loai_{ma_phieu}",
            )
        with c2:
            ten = st.text_input("Tên", key=f"adm_edit_sc_add_ten_{ma_phieu}")
        with c3:
            sl = st.number_input(
                "SL", min_value=1, value=1,
                key=f"adm_edit_sc_add_sl_{ma_phieu}",
            )
        with c4:
            dg = st.number_input(
                "Đơn giá", min_value=0, value=0, step=1000,
                key=f"adm_edit_sc_add_dg_{ma_phieu}",
            )
        if st.form_submit_button("➕ Thêm dòng", use_container_width=True):
            if ten.strip():
                items.append({
                    "loai_dong": loai_dong,
                    "ma_hang": None,
                    "ten_hang": ten.strip(),
                    "so_luong": int(sl),
                    "don_gia": int(dg),
                    "ghi_chu": "",
                })
                st.rerun()

    delete_idx = None
    for i, line in enumerate(items):
        c1, c2, c3, c4 = st.columns([1.5, 4, 2.5, 0.6])
        with c1:
            st.caption(line.get("loai_dong") or "Dịch vụ")
        with c2:
            st.markdown(f"**{line['ten_hang']}**")
        with c3:
            tt_val = int(line["so_luong"]) * int(line["don_gia"])
            st.caption(
                f"SL={line['so_luong']} · {fmt_vnd(line['don_gia'])} = {fmt_vnd(tt_val)}"
            )
        with c4:
            if st.button("✕", key=f"adm_edit_sc_del_{i}_{ma_phieu}"):
                delete_idx = i
    if delete_idx is not None:
        items.pop(delete_idx)
        st.rerun()

    return items


def _detect_changes_sc(old_header, old_items, new_data, items_locked: bool = False):
    """Detect changes for phiếu sửa chữa edit."""
    changes: dict[str, str] = {}

    def _norm(v):
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() == "nan" else s

    text_field_labels = {
        "ten_khach": "Tên khách",
        "sdt_khach": "SĐT khách",
        "loai_yeu_cau": "Loại yêu cầu",
        "hieu_dong_ho": "Hiệu đồng hồ",
        "dac_diem": "Đặc điểm",
        "mo_ta_loi": "Mô tả lỗi",
        "ghi_chu_noi_bo": "Ghi chú nội bộ",
        "nguoi_tiep_nhan": "NV tiếp nhận",
        "trang_thai": "Trạng thái",
    }
    for key, label in text_field_labels.items():
        old_v = _norm(old_header.get(key))
        new_v = _norm(new_data.get(key))
        if old_v != new_v:
            changes[label] = f"`{old_v or '—'}` → `{new_v or '—'}`"

    old_ttt = int(old_header.get("khach_tra_truoc") or 0)
    new_ttt = int(new_data.get("khach_tra_truoc") or 0)
    if old_ttt != new_ttt:
        changes["Khách trả trước"] = f"{fmt_vnd(old_ttt)} → {fmt_vnd(new_ttt)}"

    old_hen = _norm(old_header.get("ngay_hen_tra"))[:10]
    new_hen = _norm(new_data.get("ngay_hen_tra"))[:10]
    if old_hen != new_hen:
        changes["Ngày hẹn trả"] = f"`{old_hen or '—'}` → `{new_hen or '—'}`"

    if not items_locked and new_data.get("items") is not None:
        items_diffs = _diff_sc_items(old_items, new_data["items"])
        if items_diffs:
            changes["Items"] = "  \n  " + "  \n  ".join(items_diffs)

    return changes


def _diff_sc_items(old_items, new_items):
    """Diff for SC items by ten_hang (no ma_hang for services)."""
    diffs: list[str] = []

    old_names = {(it.get("ten_hang") or "").strip(): it for it in old_items}
    new_names = {(it.get("ten_hang") or "").strip(): it for it in new_items}

    for ten in sorted(set(old_names.keys()) | set(new_names.keys())):
        if not ten:
            continue
        old_it = old_names.get(ten)
        new_it = new_names.get(ten)

        if old_it and not new_it:
            old_dg = int(old_it["don_gia"])
            old_sl = int(old_it["so_luong"])
            diffs.append(f"➖ {ten} × {old_sl} @ {fmt_vnd(old_dg)}")
        elif not old_it and new_it:
            new_dg = int(new_it["don_gia"])
            new_sl = int(new_it["so_luong"])
            diffs.append(f"➕ {ten} × {new_sl} @ {fmt_vnd(new_dg)}")
        else:
            old_sl = int(old_it["so_luong"])
            new_sl = int(new_it["so_luong"])
            old_dg = int(old_it["don_gia"])
            new_dg = int(new_it["don_gia"])
            sl_changed = old_sl != new_sl
            dg_changed = old_dg != new_dg
            if sl_changed and dg_changed:
                diffs.append(
                    f"✏️ {ten} SL {old_sl}→{new_sl}, "
                    f"ĐG {fmt_vnd(old_dg)}→{fmt_vnd(new_dg)}"
                )
            elif sl_changed:
                diffs.append(f"✏️ {ten} SL {old_sl}→{new_sl}")
            elif dg_changed:
                diffs.append(f"✏️ {ten} ĐG {fmt_vnd(old_dg)}→{fmt_vnd(new_dg)}")

    return diffs


# ════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════
def module_admin_pos():
    require_admin()

    st.title("🛡 Admin POS")
    st.warning(
        "⚠️ Mọi thao tác ở đây ghi vào audit log. "
        "Tạo HĐ: backdate ≤90 ngày. Sửa HĐ: snapshot before/after."
    )

    outer_tao, outer_sua = st.tabs(["🆕 Tạo", "✏️ Sửa"])

    with outer_tao:
        sub_tao_hd, sub_tao_dt, sub_tao_sc = st.tabs([
            "🛒 HĐ POS", "🔄 Đổi/trả", "🛠 Sửa chữa",
        ])
        with sub_tao_hd: _render_tao_hd_pos()
        with sub_tao_dt: _render_tao_doi_tra()
        with sub_tao_sc: _render_tao_sua_chua()

    with outer_sua:
        sub_sua_hd, sub_sua_dt, sub_sua_sc = st.tabs([
            "🛒 HĐ POS", "🔄 Đổi/trả", "🛠 Sửa chữa",
        ])
        with sub_sua_hd: _render_sua_hd_pos()
        with sub_sua_dt: _render_sua_doi_tra()
        with sub_sua_sc: _render_sua_sua_chua()

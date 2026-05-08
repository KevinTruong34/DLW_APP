"""Admin POS — tạo HĐ / phiếu đổi-trả / phiếu sửa chữa với mọi tham số override.

Phase B1 (PLAN_ADMIN_B1.md). Chỉ admin truy cập được.
"""

import re
import streamlit as st
from datetime import datetime, date, timedelta

from utils.auth import require_admin, get_user
from utils.db import (
    supabase, call_rpc, load_all_nhan_vien, load_hang_hoa,
    invalidate_hoa_don_cache,
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

    # ── 3. Khách hàng (optional) ──
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        ten_khach = st.text_input("Tên khách (optional)", key="admin_hd_ten_kh")
    with col_k2:
        sdt_khach = st.text_input("SĐT khách (optional)", key="admin_hd_sdt_kh")

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
            st.session_state[cart_key] = []
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

    # ── 3. Khách hàng ──
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        ten_khach = st.text_input("Tên khách", key="admin_sc_ten_kh")
    with col_k2:
        sdt_khach = st.text_input("SĐT khách", key="admin_sc_sdt_kh")

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
            st.session_state[items_key] = []
            st.rerun()
        else:
            st.error(f"❌ {result.get('error', 'Unknown error') if result else 'No response'}")


# ════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════
def module_admin_pos():
    require_admin()

    st.title("🛡 Admin POS")
    st.warning(
        "⚠️ Mọi phiếu tạo ở đây đánh dấu **is_admin_created=true** "
        "và ghi audit log. Backdate tối đa 90 ngày."
    )

    tab1, tab2, tab3 = st.tabs([
        "🛒 Tạo HĐ POS",
        "🔄 Tạo phiếu đổi/trả",
        "🛠 Tạo phiếu sửa chữa",
    ])

    with tab1: _render_tao_hd_pos()
    with tab2: _render_tao_doi_tra()
    with tab3: _render_tao_sua_chua()

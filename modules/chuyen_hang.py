"""
Module Chuyển hàng — Master-Detail single-page UX.

Refactor v16.0:
- Bỏ UX 2-tab (Danh sách / Tạo-Sửa) → single page với side drawer + modal.
- Render qua custom Streamlit component (components/chuyen_hang_mvc/).
- Backend behavior, RPC contract, logging, race-retry mã phiếu: GIỮ NGUYÊN.

Event protocol (component → Python):
- {action: 'create', payload, nonce}
- {action: 'update', id, payload, nonce}
- {action: 'confirm_transfer', id, nonce}
- {action: 'receive', id, receiver, nonce}
- {action: 'cancel', id, nonce}
- {action: 'reload', nonce}
"""
import streamlit as st
import pandas as pd
import uuid
from datetime import datetime, timedelta

from utils.config import ALL_BRANCHES, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, _logger, log_action, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, get_gia_ban_map
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
from utils.helpers import now_vn_iso

from components.chuyen_hang_mvc import chuyen_hang_component

PHIEU_PER_PAGE = 20  # phân trang trong component


# ════════════════════════════════════════════════════════════════
# BACKEND HELPERS — race-retry mã phiếu + RPC wrappers (giữ nguyên hành vi)
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


def _nhan_hang_rpc(ma_phieu: str, nguoi_nhan: str = "") -> tuple[bool, str]:
    """RPC nhan_hang — atomic, set status='Đã nhận' + qty nhận = qty chuyển."""
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
    """RPC xac_nhan_chuyen_hang — status Phiếu tạm → Đang chuyển + trừ kho nguồn."""
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
    """RPC huy_phieu_chuyen_kho — set Đã hủy + restore kho nếu prev='Đang chuyển'."""
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


def _insert_phieu_rows(records: list[dict]):
    supabase.table("phieu_chuyen_kho").insert(records).execute()


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
# DATA SHAPING — DataFrame → list dict cho component
# ════════════════════════════════════════════════════════════════

def _build_tickets(df_all: pd.DataFrame) -> list[dict]:
    """Group rows theo ma_phieu, trả về list dict shape phù hợp với frontend."""
    if df_all.empty:
        return []
    out: list[dict] = []
    gia_map = get_gia_ban_map()
    # Sort theo ngay_chuyen desc
    df = df_all.sort_values("_ngay", ascending=False) if "_ngay" in df_all.columns else df_all
    for ma, grp in df.groupby("ma_phieu", sort=False):
        head = grp.iloc[0]
        # Date/time formatting (VN tz)
        try:
            ts = pd.Timestamp(head["ngay_chuyen"])
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            ts_vn = ts.tz_convert("Asia/Ho_Chi_Minh")
            date_str = ts_vn.strftime("%d/%m/%Y %H:%M")
            iso_date = ts_vn.strftime("%Y-%m-%d")
        except Exception:
            date_str = ""
            iso_date = ""

        loai_phieu = str(head.get("loai_phieu", "") or "")
        archived   = (loai_phieu == ARCHIVED_MARKER)

        items = []
        for _, r in grp.iterrows():
            ma_h = str(r.get("ma_hang", "") or "")
            gia  = int(r.get("gia_chuyen") or gia_map.get(ma_h, 0) or 0)
            items.append({
                "ma":   ma_h,
                "name": str(r.get("ten_hang", "") or ""),
                "qty":  int(r.get("so_luong_chuyen", 0) or 0),
                "recv": int(r.get("so_luong_nhan", 0) or 0),
                "gia":  gia,
            })

        def _clean(v):
            s = str(v or "").strip()
            return "" if s.lower() in ("nan", "none") else s

        out.append({
            "id":       ma,
            "from":     str(head.get("tu_chi_nhanh", "") or ""),
            "to":       str(head.get("toi_chi_nhanh", "") or ""),
            "date":     date_str,
            "_date":    iso_date,
            "creator":  _clean(head.get("nguoi_tao")),
            "receiver": _clean(head.get("nguoi_nhan")),
            "status":   str(head.get("trang_thai", "") or "").strip(),
            "note":     _clean(head.get("ghi_chu_chuyen")),
            "noteRecv": _clean(head.get("ghi_chu_nhan")),
            "source":   "archived" if archived else "app",
            "archived": archived,
            "items":    items,
        })
    return out


def _build_hang_hoa(df: pd.DataFrame) -> list[dict]:
    """Build list sản phẩm cho frontend suggestion."""
    if df.empty:
        return []
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "ma":   str(r.get("ma_hang", "") or ""),
            "name": str(r.get("ten_hang", "") or ""),
            "gia":  int(r.get("gia_ban", 0) or 0),
        })
    return rows


def _build_the_kho_by_branch(branches: list[str]) -> dict:
    """Load tồn kho cho các chi nhánh — {branch: {ma: ton}}. 1 query duy nhất."""
    out: dict[str, dict] = {b: {} for b in branches}
    if not branches:
        return out
    try:
        kho = load_the_kho(branches_key=tuple(branches))
        if kho.empty or "Mã hàng" not in kho.columns or "Chi nhánh" not in kho.columns:
            return out
        for cn, grp in kho.groupby("Chi nhánh"):
            out[str(cn)] = dict(zip(
                grp["Mã hàng"].astype(str),
                grp["Tồn cuối kì"].fillna(0).astype(int)
            ))
    except Exception:
        pass
    return out


# ════════════════════════════════════════════════════════════════
# EVENT HANDLERS — gọi RPC + log_action + cache_data.clear()
# ════════════════════════════════════════════════════════════════

def _handle_create(payload: dict):
    """Tạo phiếu mới — race-retry mã phiếu, log PHIEU_CREATE."""
    tu_cn   = payload["tu_chi_nhanh"]
    toi_cn  = payload["toi_chi_nhanh"]
    ng_tao  = payload["nguoi_tao"]
    ghi_chu = payload.get("ghi_chu", "")
    items   = payload["items"]

    if tu_cn == toi_cn:
        st.error("Chi nhánh nguồn và đích phải khác nhau.")
        return
    if not items:
        st.error("Vui lòng thêm ít nhất 1 mặt hàng.")
        return
    if not ng_tao.strip():
        st.error("Vui lòng nhập tên người gửi.")
        return

    now_iso = now_vn_iso()
    ma_phieu, last_err = None, None
    for attempt in range(3):
        try_ma = _gen_ma_phieu()
        try:
            _insert_phieu_rows(_build_records(try_ma, tu_cn, toi_cn,
                                              ng_tao, ghi_chu, items, now_iso))
            ma_phieu = try_ma
            break
        except Exception as e:
            last_err = e
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                _logger.warning(f"PHIEU_RETRY — attempt={attempt+1} ma={try_ma}")
                continue
            raise
    if ma_phieu is None:
        st.error(f"Không sinh được mã phiếu sau 3 lần thử: {last_err}")
        return

    tong_sl   = sum(int(it["so_luong"]) for it in items)
    tong_mat  = len(items)
    tong_gtri = sum(int(it["so_luong"]) * int(it["gia_ban"]) for it in items)
    log_action("PHIEU_CREATE",
               f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} sl={tong_sl} "
               f"items={tong_mat} gtri={int(tong_gtri)}")
    st.cache_data.clear()
    st.toast(f"✓ Đã tạo phiếu {ma_phieu}")


def _handle_update(ma_phieu: str, payload: dict):
    """Sửa phiếu — DELETE rows + INSERT lại, giữ status='Phiếu tạm'. Log PHIEU_UPDATE."""
    # Lấy meta gốc từ DB để giữ tu_cn/toi_cn (frontend disable nên không gửi)
    try:
        res = supabase.table("phieu_chuyen_kho").select("*").eq("ma_phieu", ma_phieu).execute()
        if not res.data:
            st.error(f"Phiếu {ma_phieu} không tồn tại.")
            return
        head = res.data[0]
        tu_cn  = head["tu_chi_nhanh"]
        toi_cn = head["toi_chi_nhanh"]
    except Exception as e:
        st.error(f"Lỗi đọc phiếu: {e}")
        return

    ng_tao  = payload["nguoi_tao"]
    ghi_chu = payload.get("ghi_chu", "")
    items   = payload["items"]
    if not items:
        st.error("Vui lòng thêm ít nhất 1 mặt hàng.")
        return

    now_iso = now_vn_iso()
    try:
        _delete_phieu_rows(ma_phieu)
        _insert_phieu_rows(_build_records(ma_phieu, tu_cn, toi_cn,
                                          ng_tao, ghi_chu, items, now_iso))
    except Exception as e:
        st.error(f"Lỗi cập nhật phiếu: {e}")
        return

    tong_sl  = sum(int(it["so_luong"]) for it in items)
    tong_mat = len(items)
    log_action("PHIEU_UPDATE",
               f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} sl={tong_sl} items={tong_mat}")
    st.cache_data.clear()
    st.toast(f"💾 Đã cập nhật phiếu {ma_phieu}")


def _handle_confirm_transfer(ma_phieu: str):
    """Xác nhận chuyển hàng — RPC + log PHIEU_CONFIRM."""
    ok, err = _xac_nhan_chuyen_rpc(ma_phieu)
    if not ok:
        st.error(f"Không thể xác nhận: {err}")
        return
    # Lấy info để log
    try:
        res = supabase.table("phieu_chuyen_kho").select("tu_chi_nhanh,toi_chi_nhanh") \
            .eq("ma_phieu", ma_phieu).limit(1).execute()
        if res.data:
            tu_cn  = res.data[0].get("tu_chi_nhanh", "")
            toi_cn = res.data[0].get("toi_chi_nhanh", "")
            log_action("PHIEU_CONFIRM", f"ma={ma_phieu} tu={tu_cn} toi={toi_cn}")
    except Exception:
        log_action("PHIEU_CONFIRM", f"ma={ma_phieu}")
    st.cache_data.clear()
    st.toast(f"✓ Đã xác nhận chuyển hàng cho phiếu {ma_phieu}")


def _handle_receive(ma_phieu: str, receiver: str):
    """Nhận hàng — RPC nhan_hang + log PHIEU_RECEIVE."""
    if not receiver.strip():
        st.error("Vui lòng nhập tên người nhận.")
        return
    ok, err = _nhan_hang_rpc(ma_phieu, nguoi_nhan=receiver.strip())
    if not ok:
        st.error(f"Lỗi nhận hàng: {err}")
        return
    try:
        res = supabase.table("phieu_chuyen_kho").select("tu_chi_nhanh,toi_chi_nhanh") \
            .eq("ma_phieu", ma_phieu).limit(1).execute()
        if res.data:
            tu_cn  = res.data[0].get("tu_chi_nhanh", "")
            toi_cn = res.data[0].get("toi_chi_nhanh", "")
            log_action("PHIEU_RECEIVE",
                       f"ma={ma_phieu} tu={tu_cn} toi={toi_cn} nguoi_nhan={receiver}")
    except Exception:
        log_action("PHIEU_RECEIVE", f"ma={ma_phieu} nguoi_nhan={receiver}")
    st.cache_data.clear()
    st.toast(f"✓ Đã nhận hàng cho phiếu {ma_phieu}")


def _handle_cancel(ma_phieu: str):
    """Hủy phiếu — RPC huy_phieu_chuyen_kho (restore kho nếu cần)."""
    user = get_user() or {}
    huy_boi = user.get("ho_ten") or user.get("username") or "admin"
    ok, result, err = _huy_phieu_rpc(ma_phieu, huy_boi)
    if not ok:
        st.error(f"Không thể hủy: {err}")
        return
    prev = result.get("prev_status", "?")
    n_restored = result.get("items_restored", 0)
    st.cache_data.clear()
    if prev == "Đang chuyển" and n_restored > 0:
        st.toast(f"✓ Đã hủy phiếu {ma_phieu} — kho CN nguồn hoàn lại {n_restored} mặt hàng.")
    else:
        st.toast(f"✓ Đã hủy phiếu {ma_phieu}")


def _process_event(ev: dict) -> bool:
    """Dispatch event. Return True nếu đã xử lý (cần rerun)."""
    action = ev.get("action")
    if action == "create":
        _handle_create(ev.get("payload", {}))
    elif action == "update":
        _handle_update(ev["id"], ev.get("payload", {}))
    elif action == "confirm_transfer":
        _handle_confirm_transfer(ev["id"])
    elif action == "receive":
        _handle_receive(ev["id"], ev.get("receiver", ""))
    elif action == "cancel":
        _handle_cancel(ev["id"])
    elif action == "reload":
        st.cache_data.clear()
    else:
        return False
    return True


# ════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════

def module_chuyen_hang():
    try:
        user   = get_user() or {}
        active = get_active_branch()
        accessible = get_accessible_branches()
        view_cns = tuple(accessible) if is_ke_toan_or_admin() else (active,)

        df_all  = load_phieu_chuyen_kho(branches_key=view_cns)
        hang_hoa_df = load_hang_hoa()
        tickets = _build_tickets(df_all)
        hang_hoa = _build_hang_hoa(hang_hoa_df)
        the_kho_by_branch = _build_the_kho_by_branch(accessible)

        today = datetime.now().date()
        first_month = today.replace(day=1)
        first_last  = (first_month - timedelta(days=1)).replace(day=1)

        ev = chuyen_hang_component(
            tickets=tickets,
            branches=ALL_BRANCHES,
            accessible_branches=accessible,
            active_branch=active,
            is_admin=is_admin(),
            current_user=user.get("ho_ten", ""),
            hang_hoa=hang_hoa,
            the_kho_by_branch=the_kho_by_branch,
            first_month_iso=first_month.isoformat(),
            first_last_iso=first_last.isoformat(),
            key="chuyen_hang_mvc_main",
            height=900,
        )

        if ev and isinstance(ev, dict):
            nonce = ev.get("nonce")
            last_nonce = st.session_state.get("_ck_last_nonce")
            if nonce and nonce != last_nonce:
                st.session_state["_ck_last_nonce"] = nonce
                handled = _process_event(ev)
                if handled:
                    st.rerun()

    except Exception as e:
        st.error(f"Lỗi tải Chuyển hàng: {e}")
        import traceback
        st.code(traceback.format_exc())

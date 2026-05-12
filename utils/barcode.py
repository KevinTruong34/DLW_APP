"""
Helper lookup hàng hóa theo ma_vach (barcode scan).

Decode đã chuyển sang client-side (utils/scanner_component.py). File này
chỉ chứa DB lookup logic.

Schema return của lookup_hang_by_ma_vach match với row của
load_hang_hoa_pos (utils/db.py) để wire vào _add_to_cart() pattern hiện tại.

Refs: PLAN_v2.md mục Phase 2.
"""
from .db import supabase


def lookup_hang_by_ma_vach(code: str, chi_nhanh: str) -> dict:
    """
    Lookup SP theo ma_vach, kèm tồn tại chi nhánh.

    Args:
        code:      mã vạch decode được từ barcode scanner
        chi_nhanh: CN active của user (để fetch tồn)

    Returns standard dict:
        {"ok": True, "item": {...}}              — found
        {"ok": False, "error": "empty"}          — code rỗng
        {"ok": False, "error": "not_found", ...} — không có trong DB
        {"ok": False, "error": "duplicate", ...} — duplicate (không xảy ra
                                                    sau UNIQUE index, defensive)
        {"ok": False, "error": "db_error", ...}  — Supabase error

    Schema item match với row của load_hang_hoa_pos:
        ma_hang, ten_hang, loai_sp, is_open, gia_ban, ton
    """
    code = (code or "").strip()
    if not code:
        return {"ok": False, "error": "empty"}

    try:
        res = supabase.table("hang_hoa") \
            .select("ma_hang, ten_hang, loai_sp, is_open_price, gia_ban") \
            .eq("ma_vach", code) \
            .eq("active", True) \
            .limit(2) \
            .execute()
    except Exception as e:
        return {"ok": False, "error": "db_error", "detail": str(e)}

    rows = res.data or []

    if not rows:
        return {"ok": False, "error": "not_found", "code": code}

    if len(rows) > 1:
        # Defensive — sau UNIQUE partial index không nên xảy ra.
        return {
            "ok": False,
            "error": "duplicate",
            "code": code,
            "ma_hang_list": [r["ma_hang"] for r in rows],
        }

    sp = rows[0]
    ma_hang = sp["ma_hang"]
    loai_sp = sp.get("loai_sp") or "Hàng hóa"
    is_open = bool(sp.get("is_open_price"))

    # Fetch tồn ở chi_nhanh (pattern match load_hang_hoa_pos).
    # Dịch vụ + open-price (SPK/DVPS) → tồn vô hạn, skip query.
    if loai_sp == "Dịch vụ" or is_open:
        ton = 999999
    else:
        try:
            ton_res = supabase.table("the_kho") \
                .select('"Tồn cuối kì"') \
                .eq("Mã hàng", ma_hang) \
                .eq("Chi nhánh", chi_nhanh) \
                .execute()
            # Có thể có nhiều dòng (legacy), cộng dồn theo pattern load_hang_hoa_pos.
            ton = sum(int(r.get("Tồn cuối kì", 0) or 0) for r in (ton_res.data or []))
        except Exception:
            ton = 0

    return {
        "ok": True,
        "item": {
            "ma_hang": ma_hang,
            "ten_hang": sp.get("ten_hang") or "",
            "loai_sp": loai_sp,
            "is_open": is_open,
            "gia_ban": int(sp.get("gia_ban") or 0),
            "ton": ton,
        },
    }

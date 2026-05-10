"""
Print queue APSC — enqueue lệnh in HĐ sửa chữa (APSC) vào print_queue.

Flow song song với utils/print_queue.py bên POS app:
- DLW gọi enqueue_apsc() sau khi tạo HĐ APSC thành công
- Hàm load HĐ qua mã từ hoa_don, build text 42 cols, insert print_queue
- Daemon poll → in K80 (cùng infra với POS)

Khác POS:
- doc_type    = 'hoa_don_apsc'
- source_app  = 'dlw_app' (vs default 'pos_app')
- Header lớn  = 'HÓA ĐƠN SỬA CHỮA' + Mã YCSC
- Items render thêm dòng "Bảo hành: ..." nếu có

Cũng expose call_huy_hoa_don_apsc() — wrapper RPC huy_hoa_don_apsc
để tab_list (Phase 5) gọi 1 chỗ duy nhất.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from utils.db import supabase

_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

# ════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════

LINE_WIDTH = 42
SEP_THIN   = "-" * LINE_WIDTH
SEP_THICK  = "=" * LINE_WIDTH

# Whitelist CN có máy in — phải khớp với utils/print_queue.py bên POS.
# CN ngoài list → enqueue_apsc trả ok=False, error="Chi nhánh chưa có máy in".
PRINT_ENABLED_BRANCHES = {
    "100 Lê Quý Đôn",
}

_CN_ADDR_SHORT = {
    "100 Lê Quý Đôn": "100 Lê Quý Đôn, Bà Rịa",
    "Coop Vũng Tàu":  "Coop Vũng Tàu - 36 Nguyễn Thái Học",
    "GO BÀ RỊA":      "Siêu thị GO, Bà Rịa",
}


# ════════════════════════════════════════════════════════════════
# LAYOUT HELPERS (duplicate từ utils/print_queue.py POS — cross-repo
# không import được, giữ song song để daemon nhận text format y hệt)
# ════════════════════════════════════════════════════════════════

def _center(s: str, width: int = LINE_WIDTH) -> str:
    s = s.strip()
    if len(s) >= width:
        return s[:width]
    pad = (width - len(s)) // 2
    return " " * pad + s


def _two_cols(left: str, right: str, width: int = LINE_WIDTH) -> str:
    left = str(left)
    right = str(right)
    space = width - len(left) - len(right)
    if space < 1:
        left = left[: max(0, width - len(right) - 1)]
        space = width - len(left) - len(right)
    return left + " " * space + right


def _wrap(text: str, width: int = LINE_WIDTH) -> list[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    out = []
    line = ""
    for word in text.split():
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    final = []
    for ln in out:
        while len(ln) > width:
            final.append(ln[:width])
            ln = ln[width:]
        final.append(ln)
    return final or [""]


def _fmt_vnd(n) -> str:
    try:
        n = int(n or 0)
    except Exception:
        return "0đ"
    return f"{n:,}đ".replace(",", ".")


def _header(chi_nhanh: str) -> list[str]:
    addr = _CN_ADDR_SHORT.get(chi_nhanh, chi_nhanh)
    return [_center("DL Watch"), _center(addr)]


# ════════════════════════════════════════════════════════════════
# LOADER — group hoa_don rows theo "Mã hóa đơn"
# ════════════════════════════════════════════════════════════════

def _load_apsc_by_ma(ma_hd: str) -> dict | None:
    """Load HĐ APSC từ bảng hoa_don, group thành 1 dict + items list.

    Trả None nếu không tìm thấy.
    """
    try:
        res = supabase.table("hoa_don").select("*") \
            .eq("Mã hóa đơn", ma_hd).execute()
    except Exception:
        return None

    rows = res.data or []
    if not rows:
        return None

    head = rows[0]
    items = []
    for r in rows:
        ma_h = (r.get("Mã hàng") or "").strip()
        ten  = (r.get("Tên hàng") or "").strip()
        if not ma_h and not ten:
            continue
        items.append({
            "ma_hang":   ma_h,
            "ten_hang":  ten,
            "so_luong":  int(r.get("Số lượng") or 0),
            "don_gia":   int(r.get("Đơn giá") or 0),
            "thanh_tien": int(r.get("Thành tiền") or 0),
            "bao_hanh":  (r.get("Bảo hành") or "").strip(),
        })

    return {
        "ma_hd":          head.get("Mã hóa đơn", ""),
        "chi_nhanh":      head.get("Chi nhánh", ""),
        "ma_ycsc":        head.get("Mã YCSC", ""),
        "thoi_gian_tao":  head.get("Thời gian tạo") or head.get("Thời gian", ""),
        "ten_khach":      head.get("Tên khách hàng", ""),
        "sdt_khach":      head.get("Điện thoại", ""),
        "nguoi_ban":      head.get("Người bán", ""),
        "ghi_chu":        head.get("Ghi chú", ""),
        "trang_thai":     head.get("Trạng thái", ""),
        "tong_tien_hang": int(head.get("Tổng tiền hàng") or 0),
        "giam_gia_don":   int(head.get("Giảm giá hóa đơn") or 0),
        "khach_can_tra":  int(head.get("Khách cần trả") or 0),
        "tien_mat":       int(head.get("Tiền mặt") or 0),
        "chuyen_khoan":   int(head.get("Chuyển khoản") or 0),
        "the":            int(head.get("Thẻ") or 0),
        "items":          items,
    }


# ════════════════════════════════════════════════════════════════
# BUILDER — HÓA ĐƠN SỬA CHỮA
# ════════════════════════════════════════════════════════════════

def _build_text_apsc(hd: dict) -> str:
    chi_nhanh = hd.get("chi_nhanh", "")
    items = hd.get("items", []) or []

    lines = []
    lines.extend(_header(chi_nhanh))
    lines.append(SEP_THICK)
    lines.append(_center("HÓA ĐƠN SỬA CHỮA"))
    lines.append(SEP_THICK)

    lines.append(_two_cols("Mã HĐ:",   hd.get("ma_hd", "")))
    if hd.get("ma_ycsc"):
        lines.append(_two_cols("Mã YCSC:", hd["ma_ycsc"]))
    if hd.get("thoi_gian_tao"):
        lines.append(_two_cols("Ngày:",    hd["thoi_gian_tao"]))
    lines.append(_two_cols("NV:",      hd.get("nguoi_ban", "—")))

    lines.append(SEP_THIN)

    lines.append(_two_cols("Khách:", hd.get("ten_khach") or "Khách lẻ"))
    if hd.get("sdt_khach"):
        lines.append(_two_cols("SĐT:", hd["sdt_khach"]))

    # Trạng thái 'Đã hủy' → in badge cảnh báo (cho luồng "in lại HĐ đã hủy")
    if (hd.get("trang_thai") or "").strip() == "Đã hủy":
        lines.append(SEP_THIN)
        lines.append(_center("*** ĐÃ HỦY ***"))

    lines.append(SEP_THICK)

    if not items:
        lines.append("(Không có chi tiết)")
    for ct in items:
        ten = ct.get("ten_hang", "")
        sl  = int(ct.get("so_luong", 0) or 0)
        dg  = int(ct.get("don_gia", 0) or 0)
        tt  = int(ct.get("thanh_tien", 0) or 0)
        bh  = ct.get("bao_hanh") or ""

        for w in _wrap(ten):
            lines.append(w)

        left = f"  {sl} x {_fmt_vnd(dg)}"
        lines.append(_two_cols(left, _fmt_vnd(tt)))

        if bh:
            lines.append(f"  Bảo hành: {bh}")

    lines.append(SEP_THIN)

    tong = hd.get("tong_tien_hang", 0)
    gg   = hd.get("giam_gia_don", 0)
    can  = hd.get("khach_can_tra", 0)
    tm   = hd.get("tien_mat", 0)
    ck   = hd.get("chuyen_khoan", 0)
    the  = hd.get("the", 0)

    lines.append(_two_cols("Tổng tiền hàng:", _fmt_vnd(tong)))
    if gg > 0:
        lines.append(_two_cols("Giảm giá:", "-" + _fmt_vnd(gg)))
    lines.append(_two_cols("Khách cần trả:", _fmt_vnd(can)))

    if tm > 0 or ck > 0 or the > 0:
        lines.append(SEP_THIN)
        if tm > 0:
            lines.append(_two_cols("Tiền mặt:", _fmt_vnd(tm)))
        if ck > 0:
            lines.append(_two_cols("Chuyển khoản:", _fmt_vnd(ck)))
        if the > 0:
            lines.append(_two_cols("Thẻ:", _fmt_vnd(the)))

    if hd.get("ghi_chu"):
        lines.append(SEP_THIN)
        lines.append("Ghi chú:")
        for w in _wrap(hd["ghi_chu"]):
            lines.append("  " + w)

    lines.append(SEP_THICK)
    lines.append(_center("Cảm ơn quý khách!"))

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
# INSERT print_queue
# ════════════════════════════════════════════════════════════════

def _insert_print_job(doc_type: str, doc_id: str, chi_nhanh: str,
                      text: str, data: dict, created_by: str = "",
                      source_app: str = "dlw_app") -> dict:
    if not text or not text.strip():
        return {"ok": False, "error": "Nội dung in rỗng"}
    try:
        payload = {"text": text, "title": doc_id, "data": data or {}}
        row = {
            "doc_type":     doc_type,
            "doc_id":       doc_id,
            "chi_nhanh":    chi_nhanh,
            "payload_json": payload,
            "created_by":   created_by or "",
            "source_app":   source_app,
        }
        res = supabase.table("print_queue").insert(row).execute()
        if res.data:
            return {"ok": True, "id": res.data[0].get("id")}
        return {"ok": False, "error": "Insert không trả về data"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════

def enqueue_apsc(ma_hd: str, created_by: str = "") -> dict:
    """Enqueue lệnh in HĐ APSC.

    Trả {ok: bool, id?: int, error?: str}. Caller (sua_chua.py /
    tab_list) wrap try/except + toast — luôn fail-silent với HĐ đã
    insert, không rollback.
    """
    if not ma_hd:
        return {"ok": False, "error": "Thiếu mã HĐ"}

    hd = _load_apsc_by_ma(ma_hd)
    if not hd:
        return {"ok": False, "error": f"Không tìm thấy HĐ {ma_hd}"}

    chi_nhanh = hd.get("chi_nhanh", "")
    if chi_nhanh not in PRINT_ENABLED_BRANCHES:
        return {"ok": False, "error": "Chi nhánh chưa có máy in"}

    text = _build_text_apsc(hd)
    return _insert_print_job(
        doc_type="hoa_don_apsc",
        doc_id=ma_hd,
        chi_nhanh=chi_nhanh,
        text=text,
        data={"ma_hd": ma_hd, "ma_ycsc": hd.get("ma_ycsc", "")},
        created_by=created_by,
        source_app="dlw_app",
    )


def call_huy_hoa_don_apsc(ma_hd: str, cancelled_by: str) -> dict:
    """Wrapper RPC huy_hoa_don_apsc.

    Trả jsonb từ RPC: {ok, ma_hd?, items_count?, kho_restored?,
    units_restored?, error?}. Phase 5 UI gọi 1 chỗ duy nhất.
    """
    if not ma_hd:
        return {"ok": False, "error": "Thiếu mã HĐ"}
    if not cancelled_by:
        return {"ok": False, "error": "Thiếu người hủy"}
    try:
        res = supabase.rpc("huy_hoa_don_apsc", {
            "p_ma_hd":        ma_hd,
            "p_cancelled_by": cancelled_by,
        }).execute()
        data = res.data if isinstance(res.data, dict) else (res.data or {})
        return data or {"ok": False, "error": "RPC không trả về data"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

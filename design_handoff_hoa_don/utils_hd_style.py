# utils/hd_style.py — Helpers for the hoa_don.py redesign
#
# STREAMLIT_DESIGN_RULES.md compliance:
#   1. All custom HTML below uses INLINE style="..." attributes (no class
#      hooks into st.html() content).
#   2. We DO NOT wrap Streamlit widgets in <div class="X">…</div> via st.html
#      calls — every visual frame around a widget uses st.container(border=True).
#   3. The .css file (static/hoa_don.css) only overrides Streamlit native
#      widgets via [data-testid="…"].
#
# Drop into: utils/hd_style.py
# CSS path:  static/hoa_don.css
#
# All public helpers prefix `hd_` so they don't collide with utils/hh_style.
#
# Schema notes (verified from utils/db.py + utils/print_queue_apsc.py):
#   - phieu_sua_chua relationship is 1:1 with hoa_don APSC via "Mã YCSC".
#   - inv["psc"] is dict|None — NOT a list.

from __future__ import annotations
from pathlib import Path
from typing import Iterable, Optional
import streamlit as st


# ─── Design tokens (also live in static/hoa_don.css as CSS vars; mirror them
# here so Python-rendered HTML can build inline styles without a stylesheet) ─
TOK = {
    "bg":        "#f7f7f8",
    "surface":   "#ffffff",
    "surface_2": "#fafafa",
    "surface_3": "#f3f3f5",
    "border":    "#e7e7ea",
    "border_2":  "#d8d8dc",
    "ink":       "#18181b",
    "ink_2":     "#3f3f46",
    "ink_3":     "#71717a",
    "ink_4":     "#a1a1aa",
    "accent":      "#e63946",
    "accent_d":    "#c1121f",
    "accent_soft": "#fdecee",
    "good":        "#1a7f37",
    "good_soft":   "#e6f4ea",
    "warn":        "#cf4c2c",
    "warn_soft":   "#fdecec",
    "info":        "#2563eb",
    "info_soft":   "#e7efff",
    "purple":      "#7c3aed",
    "purple_soft": "#f1e9ff",
    "amber":       "#b45309",
    "amber_soft":  "#fef3c7",
    "radius":      "10px",
    "radius_sm":   "6px",
    "shadow_sm":   "0 1px 2px rgba(24,24,27,.04), 0 0 0 1px #e7e7ea",
    "font":        "'Be Vietnam Pro', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "mono":        "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace",
}


# ─── CSS injection ────────────────────────────────────────────────────────
def inject_hoa_don_css() -> None:
    """Inject hoa_don.css once per session.

    Call at the very top of module_hoa_don() before any other render.
    """
    if st.session_state.get("_hd_css_injected"):
        return
    css_path = Path(__file__).parent.parent / "static" / "hoa_don.css"
    if css_path.exists():
        st.html(f"<style>{css_path.read_text(encoding='utf-8')}</style>")
    else:
        # Defensive — let the page still render even if file missing.
        st.html("<style>/* hoa_don.css missing */</style>")
    # Marker div so the CSS body-padding selector activates
    st.html('<div class="hd-scope" style="display:none"></div>')
    st.session_state["_hd_css_injected"] = True


# ─── Formatters ───────────────────────────────────────────────────────────
def fmt_money(n) -> str:
    try:
        n = int(round(float(n or 0)))
    except (TypeError, ValueError):
        return "—"
    sign = "-" if n < 0 else ""
    return f"{sign}{abs(n):,}đ".replace(",", ".")


def fmt_money_short(n) -> str:
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return "—"
    a = abs(n)
    if a >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}".rstrip("0").rstrip(".") + "tr"
    if a >= 1_000:
        return f"{int(round(n/1000))}k"
    return f"{int(round(n))}"


def short_time(tg: str) -> str:
    """'15/05/2026 11:42:01' → '11:42'"""
    import re
    m = re.search(r"\d{2}:\d{2}", str(tg or ""))
    return m.group(0) if m else ""


# ─── Atomic visual primitives — all return inline-styled HTML strings ─────

def status_badge_html(status: str) -> str:
    """Pill: ● Hoàn thành / ✕ Đã hủy / ⏱ Nợ."""
    bg, fg, dot = TOK["good_soft"], TOK["good"], "●"
    if status == "Đã hủy":
        bg, fg, dot = TOK["warn_soft"], TOK["warn"], "✕"
    elif status == "Nợ":
        bg, fg, dot = "#fff8e0", "#8a6d00", "⏱"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px;'
        f'height:20px;padding:0 8px;font-size:11px;font-weight:600;'
        f'border-radius:999px;background:{bg};color:{fg};">{dot} {status}</span>'
    )


def type_badge_html(kenh: str, loai: str) -> str:
    """🛒 POS / ↔ Đổi-Trả / 🔧 Sửa chữa / KiotViet."""
    if loai == "Đổi/Trả":
        bg, fg, ic, lbl = TOK["purple_soft"], TOK["purple"], "↔", "Đổi/Trả"
    elif loai == "Sửa chữa":
        bg, fg, ic, lbl = TOK["amber_soft"], TOK["amber"], "🔧", "Sửa chữa"
    elif kenh == "POS":
        bg, fg, ic, lbl = TOK["info_soft"], TOK["info"], "🛒", "POS"
    else:
        bg, fg, ic, lbl = TOK["surface_3"], TOK["ink_3"], "", "KiotViet"
    icon = f"{ic} " if ic else ""
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px;'
        f'height:20px;padding:0 8px;font-size:11px;font-weight:600;'
        f'border-radius:999px;background:{bg};color:{fg};">{icon}{lbl}</span>'
    )


def pay_icons_html(pttt: dict) -> str:
    """Pill row for payment methods > 0."""
    if not pttt:
        return f'<span style="color:{TOK["ink_4"]};font-size:12px">—</span>'
    parts = []
    spec = [
        ("tm",  "đ",  TOK["good_soft"],  TOK["good"],   "#cce8d3"),
        ("ck",  "CK", TOK["info_soft"],  TOK["info"],   "#d4ddf9"),
        ("the", "T",  "#fff1e3",          TOK["amber"],  "#f8dcb2"),
        ("vi",  "V",  TOK["purple_soft"], TOK["purple"], "#e3d2f5"),
    ]
    for k, lbl, bg, fg, border in spec:
        v = float(pttt.get(k, 0) or 0)
        if v > 0:
            parts.append(
                f'<span title="{k}" style="display:inline-grid;place-items:center;'
                f'width:22px;height:22px;border-radius:5px;font-family:{TOK["mono"]};'
                f'font-size:11px;font-weight:600;background:{bg};color:{fg};'
                f'border:1px solid {border};">{lbl}</span>'
            )
    if not parts:
        return f'<span style="color:{TOK["ink_4"]};font-size:12px">—</span>'
    return f'<span style="display:inline-flex;gap:4px;align-items:center">{"".join(parts)}</span>'


def nv_pill_html(ten: str) -> str:
    """Avatar circle + name."""
    ten = (ten or "").strip() or "—"
    initials = "".join(
        (s[0] if s else "") for s in ten.split()[-2:]
    ).upper()[:2] or "?"
    palette = ["#e63946", "#2563eb", "#7c3aed", "#1a7f37", "#a8530b"]
    h = sum(ord(c) for c in ten) % len(palette)
    bg = palette[h]
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'font-size:12.5px;color:{TOK["ink_2"]};">'
        f'<span style="width:22px;height:22px;border-radius:50%;'
        f'display:inline-grid;place-items:center;color:#fff;font-size:10.5px;'
        f'font-weight:600;background:{bg};">{initials}</span>{ten}</span>'
    )


def khach_cell_html(khach: str, sdt: str, repeat: bool = False) -> str:
    """Customer two-line cell: name (+ repeat badge) / phone."""
    is_walk = (not khach or khach == "Khách lẻ") and not sdt
    name_html = (
        f'<span style="color:{TOK["ink_4"]}">Khách lẻ</span>'
        if is_walk else (khach or "Khách lẻ")
    )
    repeat_html = ""
    if repeat:
        repeat_html = (
            f'<span title="Khách quay lại" style="font-size:10px;padding:1px 6px;'
            f'border-radius:999px;background:#fff4d6;color:#8a6d00;'
            f'font-weight:600;letter-spacing:.2px;">↻</span>'
        )
    sdt_html = (
        f'<span style="font-size:11.5px;color:{TOK["ink_3"]};'
        f'font-family:{TOK["mono"]};">{sdt}</span>'
        if sdt else ""
    )
    return (
        f'<div style="display:flex;flex-direction:column;line-height:1.25">'
        f'<span style="font-weight:500;display:flex;align-items:center;gap:6px">'
        f'{name_html}{repeat_html}</span>{sdt_html}</div>'
    )


# ─── List card — left column row (used inside a button-like clickable) ────

def list_card_html(inv: dict, selected: bool = False) -> str:
    """One invoice card for the master list.

    `inv` must have: ma, tg, kenh, loai, status, khach, sdt, nv, items (list)
                    pttt (dict), tong, tra, chenh (for Đổi/Trả), psc (dict|None, APSC 1:1)
    """
    is_pdt = inv.get("loai") == "Đổi/Trả"
    is_apsc = inv.get("loai") == "Sửa chữa"

    items = inv.get("items") or []
    items_count = (
        len(inv.get("items_tra") or []) + len(inv.get("items_moi") or [])
        if is_pdt else len(items)
    )

    if is_pdt:
        v = inv.get("chenh", 0) or 0
        if v > 0:
            total_html = f'<span style="color:{TOK["good"]}">+{fmt_money_short(v)}</span>'
        else:
            total_html = f'<span style="color:{TOK["warn"]}">{fmt_money_short(v)}</span>'
    elif inv.get("status") == "Đã hủy":
        total_html = (
            f'<span style="color:{TOK["ink_3"]};text-decoration:line-through">'
            f'{fmt_money(inv.get("tong", 0))}</span>'
        )
    else:
        total_html = fmt_money(inv.get("tra", 0))

    # Linked PSC badge (APSC with linked phiếu — 1:1 relationship)
    # inv["psc"] is dict|None (NOT a list — see schema note at top of file).
    psc_badge = ""
    if is_apsc and inv.get("psc"):
        psc_badge = (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'height:20px;padding:0 8px;font-size:11px;font-weight:500;'
            f'border-radius:999px;background:#ffffff;color:{TOK["amber"]};'
            f'border:1px solid #f3d99c;">🔗 PSC</span>'
        )

    bg = TOK["accent_soft"] if selected else TOK["surface"]
    border = "#f6c3c7" if selected else TOK["border"]
    shadow = "inset 3px 0 0 " + TOK["accent"] if selected else TOK["shadow_sm"]

    return (
        f'<div style="background:{bg};border:1px solid {border};'
        f'border-radius:{TOK["radius"]};padding:10px 12px;box-shadow:{shadow};'
        f'transition:background .1s, border-color .1s;font-family:{TOK["font"]};">'
        # Row 1
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'margin-bottom:6px;">'
        f'  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
        f'    <span style="font-family:{TOK["mono"]};font-weight:600;font-size:13px;'
        f'           color:{TOK["ink"]}">{inv.get("ma","")}</span>'
        f'    <span style="font-family:{TOK["mono"]};font-size:12px;'
        f'           color:{TOK["ink_3"]}">{short_time(inv.get("tg",""))}</span>'
        f'    {type_badge_html(inv.get("kenh",""), inv.get("loai",""))}'
        f'    {psc_badge}'
        f'  </div>'
        f'  {status_badge_html(inv.get("status","Hoàn thành"))}'
        f'</div>'
        # Row 2
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'gap:10px;">'
        f'  <div style="min-width:0;flex:1">'
        f'    {khach_cell_html(inv.get("khach",""), inv.get("sdt",""), inv.get("repeat", False))}'
        f'  </div>'
        f'  <div style="display:flex;align-items:center;gap:10px">'
        f'    {nv_pill_html(inv.get("nv",""))}'
        f'    <span style="font-size:12px;color:{TOK["ink_3"]};'
        f'          font-family:{TOK["mono"]}">{items_count} SP</span>'
        f'    {pay_icons_html(inv.get("pttt", {}))}'
        f'    <span style="font-family:{TOK["mono"]};font-weight:600;font-size:13.5px;'
        f'          min-width:10ch;text-align:right;color:{TOK["ink"]}">{total_html}</span>'
        f'  </div>'
        f'</div>'
        f'</div>'
    )


# ─── Detail rail — full breakdown of selected invoice ─────────────────────

def detail_rail_html(inv: dict) -> str:
    """Right rail content for a single invoice.

    Renders header + customer + totals + payment + (optional) PSC link +
    items table. Caller still places Streamlit buttons for In/Sao chép below.
    """
    is_pdt = inv.get("loai") == "Đổi/Trả"
    is_apsc = inv.get("loai") == "Sửa chữa"

    # ── Header
    repeat_pill = ""
    if inv.get("repeat"):
        repeat_pill = (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'height:20px;padding:0 8px;font-size:11px;font-weight:600;'
            f'border-radius:999px;background:#fff4d6;color:#8a6d00;">↻ Khách quay lại</span>'
        )
    header = (
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;">'
        f'  <div>'
        f'    <div style="display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap">'
        f'      {type_badge_html(inv.get("kenh",""), inv.get("loai",""))}'
        f'      {status_badge_html(inv.get("status","Hoàn thành"))}'
        f'      {repeat_pill}'
        f'    </div>'
        f'    <div style="font-size:18px;font-weight:600;letter-spacing:-.2px;'
        f'         font-family:{TOK["mono"]}">{inv.get("ma","")}</div>'
        f'    <div style="font-size:12px;color:{TOK["ink_3"]};margin-top:2px">'
        f'         {inv.get("tg","")}</div>'
        f'  </div>'
        f'</div>'
    )

    # ── Customer
    customer = (
        f'<div style="background:transparent;border:1px solid {TOK["border"]};'
        f'border-radius:{TOK["radius"]};padding:10px 12px;margin-top:12px;'
        f'display:flex;align-items:center;justify-content:space-between;gap:10px">'
        f'  <div style="display:flex;flex-direction:column;line-height:1.25">'
        f'    <span style="font-weight:600">{inv.get("khach","Khách lẻ") or "Khách lẻ"}</span>'
        + (
            f'    <span style="font-size:11.5px;color:{TOK["ink_3"]};'
            f'          font-family:{TOK["mono"]}">{inv["sdt"]}</span>'
            if inv.get("sdt") else ""
        )
        + f'  </div>{nv_pill_html(inv.get("nv",""))}</div>'
    )

    # ── Totals
    if is_pdt:
        chenh = inv.get("chenh", 0) or 0
        lbl = "Khách bù thêm" if chenh >= 0 else "Cửa hàng hoàn"
        totals = _metric_grid([
            (lbl, fmt_money(abs(chenh)), TOK["ink"]),
            ("Phương thức", pay_icons_html(inv.get("pttt", {})), TOK["ink"]),
        ])
    else:
        giam = inv.get("giam", 0) or 0
        totals = _metric_grid([
            ("Tổng hàng",   fmt_money(inv.get("tong", 0)), TOK["ink"]),
            ("Giảm giá",    fmt_money(giam), TOK["warn"] if giam > 0 else TOK["ink"]),
            ("Khách đã trả", fmt_money(inv.get("tra", 0)), TOK["accent"]),
        ])

    # ── Payment methods inline (non-Đổi/Trả)
    payment_block = ""
    if not is_pdt:
        breakdown = []
        for k, label in [("tm","TM"), ("ck","CK"), ("the","Thẻ"), ("vi","Ví")]:
            v = float((inv.get("pttt") or {}).get(k, 0) or 0)
            if v > 0:
                breakdown.append(
                    f'<span style="margin-left:8px">{label}: {fmt_money_short(v)}</span>'
                )
        payment_block = (
            f'<div style="border:1px solid {TOK["border"]};border-radius:{TOK["radius"]};'
            f'padding:8px 12px;margin-top:10px;display:flex;align-items:center;gap:8px;'
            f'font-family:{TOK["font"]}">'
            f'  <span style="font-size:12px;color:{TOK["ink_3"]};min-width:90px">Phương thức:</span>'
            f'  {pay_icons_html(inv.get("pttt", {}))}'
            f'  <span style="margin-left:auto;font-family:{TOK["mono"]};font-size:12px">'
            f'    {"".join(breakdown)}</span>'
            f'</div>'
        )

    # ── PSC liên đới (APSC only — 1:1 relationship)
    # inv["psc"] is dict|None. Render single card if present.
    psc_block = ""
    psc = inv.get("psc")
    if is_apsc and psc and isinstance(psc, dict):
        tinh_trang = str(psc.get("tinh_trang", "—") or "—")
        # Badge color theo trạng thái
        tt_lower = tinh_trang.lower()
        if "đã giao" in tt_lower or "hoàn thành" in tt_lower:
            tt_bg, tt_fg, tt_border = TOK["good_soft"], TOK["good"], "#cce8d3"
        elif "đang sửa" in tt_lower or "chờ" in tt_lower:
            tt_bg, tt_fg, tt_border = "#ffffff", TOK["amber"], "#f3d99c"
        elif "hủy" in tt_lower:
            tt_bg, tt_fg, tt_border = TOK["warn_soft"], TOK["warn"], "#fbcfca"
        else:
            tt_bg, tt_fg, tt_border = TOK["surface_3"], TOK["ink_3"], TOK["border"]

        psc_block = (
            f'<div style="margin-top:14px">'
            f'  <div style="display:flex;justify-content:space-between;align-items:center;'
            f'       margin-bottom:6px">'
            f'    <span style="font-size:12px;font-weight:600;color:{TOK["ink_3"]};'
            f'          letter-spacing:.4px;text-transform:uppercase">'
            f'      Phiếu sửa chữa liên đới</span>'
            f'  </div>'
            f'  <div style="background:{TOK["amber_soft"]};border:1px solid #f3d99c;'
            f'       border-radius:{TOK["radius_sm"]};padding:10px 12px">'
            f'    <div style="display:flex;align-items:center;justify-content:space-between;'
            f'         margin-bottom:6px;gap:8px;flex-wrap:wrap">'
            f'      <span style="font-family:{TOK["mono"]};font-size:13px;'
            f'            font-weight:600;color:{TOK["amber"]}">🔧 {psc.get("ma","—")}</span>'
            f'      <span style="display:inline-flex;align-items:center;height:20px;'
            f'            padding:0 8px;font-size:11px;font-weight:600;border-radius:999px;'
            f'            background:{tt_bg};color:{tt_fg};border:1px solid {tt_border}">'
            f'        {tinh_trang}</span>'
            f'    </div>'
            f'    <div style="font-size:12.5px;color:{TOK["ink_2"]};margin-bottom:6px">'
            f'      {psc.get("san_pham","—")}</div>'
            f'    <div style="display:flex;gap:14px;font-size:11.5px;'
            f'         color:{TOK["ink_3"]};flex-wrap:wrap">'
            f'      <span>Nhận: <span style="font-family:{TOK["mono"]};'
            f'            color:{TOK["ink_2"]}">{psc.get("ngay_nhan","—")}</span></span>'
            f'      <span>Hẹn trả: <span style="font-family:{TOK["mono"]};'
            f'            color:{TOK["ink_2"]}">{psc.get("ngay_tra","—")}</span></span>'
            f'      <span>KTV: <span style="color:{TOK["ink_2"]}">'
            f'        {psc.get("kt_vien","—")}</span></span>'
            f'    </div>'
            f'  </div>'
            f'</div>'
        )

    # ── Items table
    items_block = _items_html(inv, is_pdt)

    return (
        f'<div style="font-family:{TOK["font"]};color:{TOK["ink"]}">'
        f'{header}{customer}<div style="margin-top:12px">{totals}</div>'
        f'{payment_block}{psc_block}{items_block}</div>'
    )


def _metric_grid(items) -> str:
    """items = [(label, value_html, color)]"""
    n = len(items)
    cells = []
    for label, val, color in items:
        cells.append(
            f'<div style="background:{TOK["surface"]};border:1px solid {TOK["border"]};'
            f'border-radius:{TOK["radius"]};padding:10px 12px;box-shadow:{TOK["shadow_sm"]}">'
            f'  <div style="font-size:11px;font-weight:600;letter-spacing:.4px;'
            f'       text-transform:uppercase;color:{TOK["ink_3"]}">{label}</div>'
            f'  <div style="font-family:{TOK["mono"]};font-size:17px;font-weight:600;'
            f'       letter-spacing:-.3px;color:{color};margin-top:2px">{val}</div>'
            f'</div>'
        )
    return (
        f'<div style="display:grid;grid-template-columns:repeat({n},1fr);gap:8px">'
        f'{"".join(cells)}</div>'
    )


def _items_html(inv: dict, is_pdt: bool) -> str:
    is_apsc = inv.get("loai") == "Sửa chữa"
    title = "Chi tiết đổi/trả" if is_pdt else (
        "Dịch vụ sửa chữa" if is_apsc else "Chi tiết hàng hoá")
    item_unit = "dịch vụ" if is_apsc else "mặt hàng"

    def _table(items):
        if not items:
            return f'<div style="padding:10px;color:{TOK["ink_3"]};font-size:12px">—</div>'
        rows = []
        for it in items:
            rows.append(
                f'<tr>'
                f'  <td style="padding:8px 10px;border-bottom:1px solid {TOK["border"]};'
                f'       font-family:{TOK["mono"]};font-size:12px;color:{TOK["ink_2"]}">{it.get("ma","")}</td>'
                f'  <td style="padding:8px 10px;border-bottom:1px solid {TOK["border"]};'
                f'       font-size:12.5px">{it.get("ten","")}</td>'
                f'  <td style="padding:8px 10px;border-bottom:1px solid {TOK["border"]};'
                f'       text-align:right;font-family:{TOK["mono"]}">{it.get("sl",0)}</td>'
                f'  <td style="padding:8px 10px;border-bottom:1px solid {TOK["border"]};'
                f'       text-align:right;font-family:{TOK["mono"]}">{fmt_money_short(it.get("dg",0))}</td>'
                f'  <td style="padding:8px 10px;border-bottom:1px solid {TOK["border"]};'
                f'       text-align:right;font-family:{TOK["mono"]};font-weight:600">'
                f'       {fmt_money(it.get("tt",0))}</td>'
                f'</tr>'
            )
        return (
            f'<table style="width:100%;border-collapse:separate;border-spacing:0;font-size:12.5px">'
            f'  <thead><tr>'
            f'    <th style="text-align:left;font-size:11px;font-weight:600;letter-spacing:.4px;'
            f'         text-transform:uppercase;color:{TOK["ink_3"]};padding:8px 10px;'
            f'         background:{TOK["surface_2"]};border-bottom:1px solid {TOK["border"]}">Mã</th>'
            f'    <th style="text-align:left;font-size:11px;font-weight:600;letter-spacing:.4px;'
            f'         text-transform:uppercase;color:{TOK["ink_3"]};padding:8px 10px;'
            f'         background:{TOK["surface_2"]};border-bottom:1px solid {TOK["border"]}">Tên hàng</th>'
            f'    <th style="text-align:right;font-size:11px;font-weight:600;letter-spacing:.4px;'
            f'         text-transform:uppercase;color:{TOK["ink_3"]};padding:8px 10px;'
            f'         background:{TOK["surface_2"]};border-bottom:1px solid {TOK["border"]}">SL</th>'
            f'    <th style="text-align:right;font-size:11px;font-weight:600;letter-spacing:.4px;'
            f'         text-transform:uppercase;color:{TOK["ink_3"]};padding:8px 10px;'
            f'         background:{TOK["surface_2"]};border-bottom:1px solid {TOK["border"]}">Đơn giá</th>'
            f'    <th style="text-align:right;font-size:11px;font-weight:600;letter-spacing:.4px;'
            f'         text-transform:uppercase;color:{TOK["ink_3"]};padding:8px 10px;'
            f'         background:{TOK["surface_2"]};border-bottom:1px solid {TOK["border"]}">Thành tiền</th>'
            f'  </tr></thead><tbody>{"".join(rows)}</tbody></table>'
        )

    if is_pdt:
        body = (
            f'<div style="display:flex;flex-direction:column;gap:8px">'
            f'  <div style="border:1px solid {TOK["border"]};border-radius:{TOK["radius"]};'
            f'       overflow:hidden">'
            f'    <div style="padding:6px 10px;background:#fef0f0;font-size:11.5px;'
            f'         font-weight:600;color:{TOK["warn"]}">← KHÁCH TRẢ LẠI</div>'
            f'    {_table(inv.get("items_tra") or [])}</div>'
            f'  <div style="border:1px solid {TOK["border"]};border-radius:{TOK["radius"]};'
            f'       overflow:hidden">'
            f'    <div style="padding:6px 10px;background:#e9f6ee;font-size:11.5px;'
            f'         font-weight:600;color:{TOK["good"]}">→ KHÁCH MUA MỚI</div>'
            f'    {_table(inv.get("items_moi") or [])}</div>'
            f'</div>'
        )
        count_str = ""
    else:
        body = (
            f'<div style="border:1px solid {TOK["border"]};border-radius:{TOK["radius"]};'
            f'overflow:hidden">{_table(inv.get("items") or [])}</div>'
        )
        count_str = f'<span style="font-size:12px;color:{TOK["ink_3"]}">{len(inv.get("items") or [])} {item_unit}</span>'

    return (
        f'<div style="margin-top:14px">'
        f'  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
        f'    <span style="font-size:12px;font-weight:600;color:{TOK["ink_3"]};'
        f'         letter-spacing:.4px;text-transform:uppercase">{title}</span>'
        f'    {count_str}'
        f'  </div>{body}</div>'
    )


def empty_rail_html() -> str:
    """Empty state for the right rail when nothing is selected."""
    return (
        f'<div style="padding:40px 10px;text-align:center;font-family:{TOK["font"]}">'
        f'  <div style="width:54px;height:54px;border-radius:14px;'
        f'       background:{TOK["surface_2"]};border:1px dashed {TOK["border_2"]};'
        f'       display:inline-grid;place-items:center;margin-bottom:12px;'
        f'       font-size:20px;color:{TOK["ink_4"]}">📄</div>'
        f'  <div style="font-weight:600;margin-bottom:4px">Chưa chọn hoá đơn</div>'
        f'  <div style="font-size:12px;color:{TOK["ink_3"]};line-height:1.5">'
        f'    Click 1 dòng bên trái để xem<br>chi tiết hàng hoá, PTTT, thao tác.</div>'
        f'</div>'
    )


# ─── Smart-search dispatcher ──────────────────────────────────────────────

def smart_search_predicate(query: str):
    """Return a function(row) -> bool that matches the search query.

    Heuristic:
      - all digits  → match SĐT (contains) OR Mã HĐ (endswith)
      - alpha+      → match Tên khách hàng (contains, case-insensitive)
      - mixed       → match Mã HĐ (contains, case-insensitive)
    The caller applies this to the DataFrame's row (use .iterrows or vectorize
    with str.contains — see IMPLEMENTATION_GUIDE).
    """
    q = (query or "").strip()
    if not q:
        return lambda row: True
    digits = "".join(c for c in q if c.isdigit())
    only_digits = bool(q) and q == digits and len(digits) >= 2

    q_low = q.lower()

    def _match(row):
        sdt = str(row.get("SĐT_Search", "") or "")
        ma  = str(row.get("Mã hóa đơn", "") or "").upper()
        ten = str(row.get("Tên khách hàng", "") or "").lower()

        if only_digits:
            return (digits in sdt) or ma.endswith(q.upper()) or (digits in ma)
        if q_low.isalpha():
            return q_low in ten
        return q.upper() in ma
    return _match

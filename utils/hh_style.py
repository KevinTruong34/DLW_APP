"""
utils/hh_style.py — Helper cho hang_hoa redesign.

Lịch sử fix:
- v1: đổi inject_hang_hoa_css() dùng st.html (bypass markdown sanitizer)
- v2: đổi hh_html() dùng st.html (giữ class attribute)
- v3: dùng inline styles trong render_*() vì st.html() có CSS isolation —
      global <style> không vươn vào được content do st.html() render

Cho tương lai: nếu cần đổi visual, sửa inline styles trong các hàm render_*
dưới đây, KHÔNG sửa static/hang_hoa.css (file CSS chỉ dùng cho Streamlit
native overrides — buttons, dataframe, fonts).
"""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import streamlit as st


# Resolve CSS file relative to this module. Adjust if you move the file:
_CSS_PATH = Path(__file__).parent.parent / "static" / "hang_hoa.css"


@lru_cache(maxsize=1)
def _read_css() -> str:
    """Read and cache the CSS file content."""
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def inject_hang_hoa_css() -> None:
    """Inject hang_hoa.css + Google Fonts vào page <head>.

    CSS này chỉ apply được cho:
    - Streamlit native widgets (qua selector .main [data-testid="..."])
    - Font family chung cho cả trang
    - Streamlit dataframe styling

    KHÔNG apply được cho content render qua st.html() (do isolation behavior).
    Visual của detail card phải dùng inline styles — xem render_detail_visual().
    """
    css = _read_css()
    fonts_import = (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Be+Vietnam+Pro:wght@400;500;600;700&"
        "family=JetBrains+Mono:wght@400;500;600&display=swap');\n"
    )
    st.html(f"<style>{fonts_import}{css}</style>")


def hh_html(html: str) -> None:
    """Render HTML inline. Lưu ý CSS isolation: chỉ apply được inline styles
    trên element trực tiếp, hoặc <style> nhúng ngay trong cùng html string.
    """
    st.html(html)


# ──────────────────────────────────────────────────────────────────────────
# DESIGN TOKENS — hard-coded vào inline styles
# Lý do hardcoded thay vì dùng CSS variables: CSS variables cần CSS rule trong
# scope, mà scope của st.html() bị isolated → variables không resolve được.
# ──────────────────────────────────────────────────────────────────────────

_TOKENS = {
    "bg":          "#f7f7f8",
    "surface":     "#ffffff",
    "surface_2":   "#fafafa",
    "border":      "#e7e7ea",
    "border_2":    "#d8d8dc",
    "ink":         "#18181b",
    "ink_2":       "#3f3f46",
    "ink_3":       "#71717a",
    "ink_4":       "#a1a1aa",
    "accent":      "#e63946",
    "accent_d":    "#c1121f",
    "accent_soft": "#fdecee",
    "good":        "#1a7f37",
    "warn":        "#cf4c2c",
    "zero":        "#a1a1aa",
    "font":        "'Be Vietnam Pro', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "mono":        "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace",
}


# ──────────────────────────────────────────────────────────────────────────
# Component builders — toàn bộ dùng inline styles
# ──────────────────────────────────────────────────────────────────────────

def render_caption(total: int, branches: list[str],
                   filter_label: str | None = None,
                   sort_label: str = "Tồn ↓") -> None:
    """Caption row dưới toolbar."""
    branch_str = ", ".join(branches) if branches else "—"
    T = _TOKENS

    filter_html = ""
    if filter_label:
        filter_html = (
            f'<span style="margin:0 8px;color:{T["ink_4"]}">·</span>'
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'font-size:11px;font-weight:600;padding:2px 7px;border-radius:999px;'
            f'background:{T["accent_soft"]};color:{T["accent_d"]};'
            f'border:1px solid #f8c8cd">{filter_label}</span>'
        )

    hint = ""
    if total > 100:
        hint = (
            f'<span style="margin:0 8px;color:{T["ink_4"]}">·</span>'
            f'lọc thêm để thu hẹp'
        )

    st.html(
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'font-family:{T["font"]};font-size:12.5px;color:{T["ink_3"]};'
        f'padding:2px 4px 8px">'
        f'  <div><b style="color:{T["ink"]};font-weight:600">{total:,}</b> sản phẩm '
        f'    <span style="margin:0 8px;color:{T["ink_4"]}">·</span> {branch_str}{filter_html}{hint}'
        f'  </div>'
        f'  <div>Sắp xếp: <b style="color:{T["ink"]};font-weight:600">{sort_label}</b></div>'
        f'</div>'
    )


def render_empty_rail() -> None:
    """Empty state cho rail phải khi chưa chọn dòng nào."""
    T = _TOKENS
    st.html(
        f'<div style="background:{T["surface"]};border:1px dashed {T["border_2"]};'
        f'border-radius:10px;padding:24px 18px;text-align:center;'
        f'font-family:{T["font"]}">'
        f'  <div style="width:40px;height:40px;border-radius:50%;'
        f'        background:{T["surface_2"]};display:inline-grid;place-items:center;'
        f'        color:{T["ink_3"]};margin-bottom:10px;font-size:18px">'
        f'    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">'
        f'      <path d="M4 7h16M4 12h10M4 17h6" stroke="currentColor" '
        f'       stroke-width="1.7" stroke-linecap="round"/>'
        f'    </svg>'
        f'  </div>'
        f'  <h4 style="margin:0 0 4px;font-size:14px;font-weight:600;'
        f'        color:{T["ink"]}">Chưa chọn hàng hóa</h4>'
        f'  <p style="margin:0;font-size:12.5px;color:{T["ink_3"]};line-height:1.5">'
        f'    Bấm vào 1 dòng trong bảng để xem chi tiết, tồn kho 3 chi nhánh '
        f'    và thao tác chỉnh sửa. Chọn nhiều dòng để in tem hàng loạt.</p>'
        f'</div>'
    )


def render_detail_visual(
    ten_hang: str,
    breadcrumb: str,
    ma_hang: str,
    ma_vach: str,
    thuong_hieu: str,
    loai_sp: str,
    bao_hanh: str,
    gia_ban: int,
    branches: list[str],
    stocks: dict[str, int],
    current: str,
    short: dict[str, str],
) -> None:
    """Render visual của detail card thành 1 st.html call với inline styles.

    Bypass CSS isolation: mọi style nằm trên element trực tiếp.
    """
    T = _TOKENS

    # ── Header (title + breadcrumb) ──
    header_html = (
        f'<div style="padding:14px 16px 10px;border-bottom:1px solid {T["border"]}">'
        f'  <h3 style="margin:0;font-size:17px;line-height:1.25;font-weight:600;'
        f'        color:{T["ink"]};letter-spacing:-.1px;'
        f'        font-family:{T["font"]}">{ten_hang}</h3>'
        f'  <div style="margin-top:3px;font-size:11px;font-family:{T["mono"]};'
        f'        letter-spacing:.4px;color:{T["ink_3"]};text-transform:uppercase">'
        f'    {breadcrumb}'
        f'  </div>'
        f'</div>'
    )

    # ── Code pill + barcode ──
    vach_html = ""
    if ma_vach and ma_vach != ma_hang:
        vach_html = (
            f'<span style="font-family:{T["mono"]};font-size:11.5px;'
            f'color:{T["ink_3"]}">· Mã vạch: {ma_vach}</span>'
        )
    codes_html = (
        f'<div style="display:flex;align-items:center;gap:8px;'
        f'margin-bottom:8px;flex-wrap:wrap">'
        f'  <span style="display:inline-flex;align-items:center;gap:6px;'
        f'        font-family:{T["mono"]};font-size:12px;font-weight:600;'
        f'        background:{T["surface_2"]};border:1px solid {T["border"]};'
        f'        color:{T["ink"]};padding:3px 9px;border-radius:5px">'
        f'    {ma_hang}'
        f'  </span>'
        f'  {vach_html}'
        f'</div>'
    )

    # ── Meta dl (grid 2 cột) ──
    meta_rows_html = ""
    rows = []
    if thuong_hieu:
        rows.append(("Thương hiệu", thuong_hieu))
    rows.append(("Loại SP", loai_sp or "Hàng hóa"))
    if bao_hanh:
        rows.append(("Bảo hành", bao_hanh))

    if rows:
        items = "".join(
            f'<dt style="color:{T["ink_3"]};font-weight:500;margin:0">{label}</dt>'
            f'<dd style="margin:0;color:{T["ink"]}">{value}</dd>'
            for label, value in rows
        )
        meta_rows_html = (
            f'<dl style="display:grid;grid-template-columns:max-content 1fr;'
            f'      column-gap:10px;row-gap:4px;font-size:12.5px;'
            f'      color:{T["ink_2"]};margin:0 0 12px;'
            f'      font-family:{T["font"]}">{items}</dl>'
        )

    # ── Price box ──
    price_str = f"{gia_ban:,}".replace(",", " ") if gia_ban else "—"
    price_html = (
        f'<div style="background:{T["surface_2"]};border:1px solid {T["border"]};'
        f'border-radius:6px;padding:8px 12px;display:flex;align-items:baseline;'
        f'justify-content:space-between;margin-bottom:14px">'
        f'  <span style="font-size:11px;letter-spacing:.5px;color:{T["ink_3"]};'
        f'        text-transform:uppercase;font-weight:600;'
        f'        font-family:{T["font"]}">Giá bán</span>'
        f'  <span style="font-family:{T["mono"]};font-size:18px;font-weight:600;'
        f'        color:{T["ink"]};letter-spacing:-.3px">'
        f'    {price_str}<span style="font-size:13px;font-weight:500;'
        f'      color:{T["ink_3"]};margin-left:2px"> ₫</span>'
        f'  </span>'
        f'</div>'
    )

    # ── Section label "Tồn kho 3 chi nhánh" ──
    section_lbl_html = (
        f'<div style="font-size:11px;letter-spacing:.5px;color:{T["ink_3"]};'
        f'text-transform:uppercase;font-weight:600;margin:6px 0 8px;'
        f'font-family:{T["font"]}">Tồn kho 3 chi nhánh</div>'
    )

    # ── Stock tiles (grid 3 cột) ──
    tiles = []
    for cn in branches:
        ton = int(stocks.get(cn, 0) or 0)
        is_cur = (cn == current)

        # Color cho số tồn
        if ton > 5:
            v_color = T["good"]
        elif ton > 0:
            v_color = T["warn"]
        else:
            v_color = T["zero"]

        # Style cho tile + name
        if is_cur:
            tile_style = (
                f'border:1px solid {T["accent"]};background:{T["accent_soft"]};'
                f'box-shadow:inset 0 0 0 1px {T["accent"]}'
            )
            name_color = T["accent_d"]
            pin = "📍 "
        else:
            tile_style = f'border:1px solid {T["border"]};background:{T["surface"]}'
            name_color = T["ink_3"]
            pin = ""

        tiles.append(
            f'<div style="text-align:center;padding:8px 4px 9px;border-radius:6px;'
            f'      {tile_style}">'
            f'  <div style="font-size:11px;color:{name_color};font-weight:500;'
            f'        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
            f'        font-family:{T["font"]}">{pin}{short.get(cn, cn)}</div>'
            f'  <div style="font-family:{T["mono"]};font-size:18px;font-weight:600;'
            f'        font-variant-numeric:tabular-nums;color:{v_color};'
            f'        margin-top:2px;letter-spacing:-.3px">{ton:,}</div>'
            f'</div>'
        )

    stocks_html = (
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);'
        f'gap:6px;margin-bottom:6px">{"".join(tiles)}</div>'
    )

    # ── Render TẤT CẢ trong 1 st.html call ──
    st.html(
        header_html +
        f'<div style="padding:12px 16px 4px">'
        f'  {codes_html}'
        f'  {meta_rows_html}'
        f'  {price_html}'
        f'  {section_lbl_html}'
        f'  {stocks_html}'
        f'</div>'
    )


def render_multi_queue(items: list[dict], n: int) -> None:
    """Queue card cho multi-select.

    items: list of dict với keys 'ten_hang', 'ma_hang'
    n: tổng số items (có thể > len(items) nếu cap display)
    """
    T = _TOKENS

    items_li = []
    for it in items[:50]:
        ten = it.get("ten_hang", "?")
        ma = it.get("ma_hang", "?")
        items_li.append(
            f'<li style="display:flex;align-items:center;gap:8px;padding:8px 10px;'
            f'      border-bottom:1px solid {T["border"]};font-size:12.5px">'
            f'  <span style="flex:1;color:{T["ink"]};font-weight:500;'
            f'        overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{ten}</span>'
            f'  <span style="font-family:{T["mono"]};font-size:11.5px;'
            f'        color:{T["ink_3"]}">{ma}</span>'
            f'</li>'
        )

    st.html(
        f'<div style="background:{T["surface"]};border:1px solid {T["border"]};'
        f'border-radius:10px;box-shadow:0 1px 2px rgba(24,24,27,.04);'
        f'font-family:{T["font"]}">'
        f'  <div style="padding:14px 16px 10px;border-bottom:1px solid {T["border"]}">'
        f'    <h3 style="margin:0;font-size:17px;line-height:1.25;font-weight:600;'
        f'          color:{T["ink"]};letter-spacing:-.1px">Đã chọn {n} sản phẩm</h3>'
        f'    <div style="margin-top:3px;font-size:11px;font-family:{T["mono"]};'
        f'          letter-spacing:.4px;color:{T["ink_3"]};text-transform:uppercase">'
        f'      SẴN SÀNG IN TEM'
        f'    </div>'
        f'  </div>'
        f'  <ul style="margin:0;padding:0;list-style:none;max-height:280px;'
        f'        overflow:auto">{"".join(items_li)}</ul>'
        f'  <div style="padding:10px 12px;border-top:1px solid {T["border"]};'
        f'        background:{T["surface_2"]};display:flex;align-items:center;'
        f'        justify-content:space-between;font-size:12.5px">'
        f'    <span style="color:{T["ink_3"]}">Tổng số tem: '
        f'      <b style="color:{T["ink"]};font-family:{T["mono"]}">{n}</b>'
        f'    </span>'
        f'    <span style="display:inline-flex;align-items:center;gap:4px;'
        f'          font-size:11px;font-weight:600;padding:2px 7px;border-radius:999px;'
        f'          background:{T["surface_2"]};color:{T["ink_2"]};'
        f'          border:1px solid {T["border"]}">CODE128</span>'
        f'  </div>'
        f'</div>'
    )

"""
utils/hh_style.py  — CSS injection helper for the hang_hoa redesign.

Call inject_hang_hoa_css() ONCE at the top of module_hang_hoa().
The CSS file is cached after first read; rerunning is cheap.

Usage in modules/hang_hoa.py:

    from utils.hh_style import inject_hang_hoa_css, hh_html

    def module_hang_hoa():
        inject_hang_hoa_css()
        ...

Also exposes hh_html(html: str) which renders HTML via st.html so that
class attributes (and other non-allowlisted attrs) survive — st.markdown
runs content through bleach and strips them.
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
    """Inject hang_hoa.css + Google Fonts.

    Use st.html (Streamlit >= 1.33) instead of st.markdown to bypass the
    markdown parser / HTML sanitizer that breaks the wrapping <style>
    block when the CSS contains HTML literals, blank lines, or characters
    that confuse the parser. Fonts are loaded via @import inside <style>
    rather than a separate <link> tag (sanitizers commonly strip <link>).

    Fallback to st.markdown for Streamlit < 1.33.
    """
    css = _read_css()
    fonts_import = (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Be+Vietnam+Pro:wght@400;500;600;700&"
        "family=JetBrains+Mono:wght@400;500;600&display=swap');\n"
    )
    block = f"<style>{fonts_import}{css}</style>"
    if hasattr(st, "html"):
        st.html(block)
    else:
        st.markdown(block, unsafe_allow_html=True)


def hh_html(html: str) -> None:
    """Render HTML inline, preserving class attributes.

    Use st.html (no bleach sanitizer) instead of st.markdown — st.markdown
    with unsafe_allow_html=True still pipes content through bleach which
    strips the class attribute, so .hh-* selectors stop matching.
    """
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────
# Reusable HTML builders for components that are pure presentation.
# These keep call sites in hang_hoa.py readable.
# ──────────────────────────────────────────────────────────────────────


def render_caption(total: int, branches: list[str],
                   filter_label: str | None = None,
                   sort_label: str = "Tồn ↓") -> None:
    """Caption row under the toolbar."""
    branch_str = ", ".join(branches) if branches else "—"
    filter_html = (
        f'<span class="dot">·</span>'
        f'<span class="hh-badge red">{filter_label}</span>'
        if filter_label else ""
    )
    hint = ' <span class="dot">·</span> lọc thêm để thu hẹp' if total > 100 else ""
    hh_html(
        f'<div class="hh-caption">'
        f'  <div><b>{total:,}</b> sản phẩm '
        f'<span class="dot">·</span> {branch_str}{filter_html}{hint}</div>'
        f'  <div>Sắp xếp: <b>{sort_label}</b></div>'
        f'</div>'
    )


def render_empty_rail() -> None:
    """The 'no row selected' card shown in the right rail."""
    hh_html(
        '<div class="hh-empty">'
        '  <div class="ico">'
        '    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">'
        '      <path d="M4 7h16M4 12h10M4 17h6" stroke="currentColor" '
        '       stroke-width="1.7" stroke-linecap="round"/>'
        '    </svg>'
        '  </div>'
        '  <h4>Chưa chọn hàng hóa</h4>'
        '  <p>Bấm vào 1 dòng trong bảng để xem chi tiết, tồn kho 3 chi nhánh '
        '   và thao tác chỉnh sửa. Chọn nhiều dòng để in tem hàng loạt.</p>'
        '</div>'
    )


def render_detail_card_open(ten_hang: str, breadcrumb: str,
                            ma_hang: str, ma_vach: str = "",
                            thuong_hieu: str = "", loai_sp: str = "Hàng hóa",
                            bao_hanh: str = "", gia_ban: int = 0) -> None:
    """Open the detail card and render header + body up to the stock tiles."""
    vach_html = (
        f'<span class="vach">· Mã vạch: {ma_vach}</span>'
        if ma_vach and ma_vach != ma_hang else ""
    )
    meta_rows = []
    if thuong_hieu:
        meta_rows.append(f'<dt>Thương hiệu</dt><dd>{thuong_hieu}</dd>')
    meta_rows.append(f'<dt>Loại SP</dt><dd>{loai_sp}</dd>')
    if bao_hanh:
        meta_rows.append(f'<dt>Bảo hành</dt><dd>{bao_hanh}</dd>')
    meta_html = (
        f'<dl class="hh-meta">{"".join(meta_rows)}</dl>'
        if meta_rows else ""
    )
    price_str = f"{gia_ban:,}".replace(",", " ") if gia_ban else "—"

    hh_html(
        f'<div class="hh-card">'
        f'  <div class="hh-card-head">'
        f'    <div class="row1">'
        f'      <div>'
        f'        <h3>{ten_hang}</h3>'
        f'        <div class="breadcrumb">{breadcrumb}</div>'
        f'      </div>'
        f'    </div>'
        f'  </div>'
        f'  <div class="hh-card-body">'
        f'    <div class="hh-codes">'
        f'      <span class="hh-code-pill">{ma_hang}</span>'
        f'      {vach_html}'
        f'    </div>'
        f'    {meta_html}'
        f'    <div class="hh-price-box">'
        f'      <span class="lbl">Giá bán</span>'
        f'      <span class="val">{price_str}<span class="u"> ₫</span></span>'
        f'    </div>'
        f'    <div class="hh-section-lbl">Tồn kho 3 chi nhánh</div>'
    )


def render_stock_tiles(branches: list[str], stocks: dict[str, int],
                       current: str, short: dict[str, str]) -> None:
    """3-branch stock tiles (current branch highlighted in red)."""
    tiles = []
    for cn in branches:
        ton = int(stocks.get(cn, 0) or 0)
        is_cur = (cn == current)
        lvl = "" if ton > 5 else ("low" if ton > 0 else "zero")
        cls = "hh-stock curr" if is_cur else "hh-stock"
        pin = "📍 " if is_cur else ""
        tiles.append(
            f'<div class="{cls}">'
            f'  <div class="name">{pin}{short.get(cn, cn)}</div>'
            f'  <div class="v {lvl}">{ton:,}</div>'
            f'</div>'
        )
    hh_html(f'<div class="hh-stocks">{"".join(tiles)}</div>')


def render_detail_card_close() -> None:
    """Close the .hh-card-body and .hh-card divs."""
    hh_html('  </div></div>')


def render_fab(n: int) -> None:
    """Floating action bar for multi-select print."""
    hh_html(
        f'<div class="hh-fab-wrap"><div class="hh-fab">'
        f'  <span>Đã chọn</span>'
        f'  <span class="ct">{n} SP</span>'
        f'  <span class="sep"></span>'
        f'</div></div>'
    )

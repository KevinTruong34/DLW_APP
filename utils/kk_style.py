"""utils/kk_style.py — Helpers cho module Kiểm kê v2 redesign.

CSS injection strategy (HANDOFF_kiem_ke_v2_to_claude_code.md section 1.1):

  1. Design tokens (`:root` vars) + `@keyframes` qua
     `st.markdown(unsafe_allow_html=True)`. DOMPurify trong `st.html()` strip
     `<style>` silently — markdown là path an toàn cho global CSS để inline
     `var(--token)` resolve được ở document level.

  2. `static/kiem_ke.css` chứa font `@import` + Streamlit native widget
     overrides — đọc từ disk, inline cùng cách.

Content elements (`<div>`, `<span>`, `<section>`, ...) trong `st.html()` PHẢI
dùng inline `style="..."` với `var(--token)` — class không vượt iframe
boundary. JS chạy trong iframe nên truy cập `window.parent.document` để
target Streamlit-rendered DOM.
"""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import streamlit as st


_CSS_PATH = Path(__file__).parent.parent / "static" / "kiem_ke.css"


# Design tokens + animation keyframes. DEBUG MARKER đã xóa ở PR 8 cleanup.
_CSS_VARS_BLOCK = """
<style>
:root {
    --green-50:    #ecfdf5;
    --green-100:   #d1fae5;
    --green-200:   #a7f3d0;
    --green-500:   #10b981;
    --green-600:   #059669;
    --green-700:   #047857;
    --green-800:   #065f46;
    --green-900:   #064e3b;
    --ink:         #0b1220;
    --ink-2:       #475569;
    --ink-3:       #94a3b8;
    --line:        #e5e7eb;
    --line-strong: #cbd5e1;
    --surface:     #ffffff;
    --surface-2:   #f8fafc;
    --surface-3:   #f1f5f9;
    --bg:          #f6f7f5;
    --warn-50:     #fffbeb;
    --warn-200:    #fde68a;
    --warn-700:    #b45309;
    --bad-50:      #fef2f2;
    --bad-200:     #fecaca;
    --bad-500:     #ef4444;
    --bad-700:     #b91c1c;
    --info-50:     #eff6ff;
    --info-200:    #bfdbfe;
    --info-700:    #1d4ed8;
    --r-sm:        6px;
    --r:           10px;
    --r-lg:        14px;
    --r-xl:        18px;
    --shadow-1:    0 1px 2px rgba(15,23,42,.04), 0 1px 1px rgba(15,23,42,.03);
    --shadow-2:    0 4px 14px -4px rgba(15,23,42,.10), 0 2px 4px rgba(15,23,42,.04);
    --shadow-card: 0 8px 28px -10px rgba(4,120,87,.18), 0 2px 6px rgba(15,23,42,.04);
    --mono:        'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    --sans:        'Plus Jakarta Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

@keyframes flashOk {
    0%   { background-color: var(--green-50); box-shadow: 0 0 0 3px var(--green-100); }
    100% { background-color: var(--surface); box-shadow: var(--shadow-card); }
}
@keyframes flashBad {
    0%   { background-color: var(--bad-50); box-shadow: 0 0 0 3px var(--bad-200); }
    100% { background-color: var(--surface); box-shadow: var(--shadow-card); }
}
@keyframes rowFlash {
    0%   { background-color: var(--green-100); }
    100% { background-color: transparent; }
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: none; }
}
</style>
"""


@lru_cache(maxsize=1)
def _read_css_file() -> str:
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "/* static/kiem_ke.css missing */"


def inject_kiem_ke_css() -> None:
    """Inject design tokens + keyframes + static CSS overrides.

    Gọi đầu `module_kiem_ke()` mỗi rerun — Streamlit DOM dedup giữ chi phí
    re-inject nhỏ và styles tồn tại qua cross-module navigation.
    """
    st.markdown(_CSS_VARS_BLOCK, unsafe_allow_html=True)
    st.markdown(f"<style>{_read_css_file()}</style>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# JS injection helpers
# ═══════════════════════════════════════════════════════════════════════════

# Unlock AudioContext on first user gesture (browser policy). Per HANDOFF
# section 2.4 — README đề cập chặn nhưng không có code unlock.
_AUDIO_UNLOCK_JS = """
<script>
(function() {
    if (window.__kk_unlock_installed) return;
    window.__kk_unlock_installed = true;
    const doc = (window.parent && window.parent.document) || document;
    function unlock() {
        try {
            const Ctor = window.AudioContext || window.webkitAudioContext;
            if (!Ctor) return;
            const ac = window.__kk_ac || (window.__kk_ac = new Ctor());
            if (ac.state === 'suspended') ac.resume();
            window.__kk_unlocked = true;
        } catch(e) {}
    }
    doc.addEventListener('click', unlock);
    doc.addEventListener('keydown', unlock);
})();
</script>
"""

# Retry-focus pattern. HANDOFF section 2.3 override — README selector
# `aria-label*="Quét"` không match khi `label_visibility="collapsed"`.
# Target `[data-testid="stForm"] input` vì scan form là form duy nhất trên
# tab Quét (search input ở toolbar không nằm trong form).
_AUTO_FOCUS_JS = """
<script>
(function() {
    const doc = (window.parent && window.parent.document) || document;
    function tryFocus() {
        const inputs = doc.querySelectorAll('[data-testid="stForm"] input');
        if (inputs.length === 0) return false;
        const inp = inputs[0];
        // Skip nếu form ẩn (tab inactive) — boundingRect 0×0 khi parent hidden.
        const rect = inp.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        if (doc.activeElement !== inp) {
            inp.focus();
            try { inp.select(); } catch(e) {}
        }
        return true;
    }
    let tries = 0;
    const id = setInterval(() => {
        if (tryFocus() || ++tries > 15) clearInterval(id);
    }, 60);
})();
</script>
"""

_BEEP_OK_JS = """
<script>
(function() {
    try {
        const Ctor = window.AudioContext || window.webkitAudioContext;
        if (!Ctor) return;
        const ac = window.__kk_ac || (window.__kk_ac = new Ctor());
        if (ac.state === 'suspended') ac.resume();
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'sine'; o.frequency.value = 880;
        g.gain.value = 0.07;
        o.connect(g).connect(ac.destination);
        o.start();
        g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + 0.08);
        o.stop(ac.currentTime + 0.10);
    } catch(e) {}
})();
</script>
"""

_BEEP_BAD_JS = """
<script>
(function() {
    try {
        const Ctor = window.AudioContext || window.webkitAudioContext;
        if (!Ctor) return;
        const ac = window.__kk_ac || (window.__kk_ac = new Ctor());
        if (ac.state === 'suspended') ac.resume();
        function tone(f, d, type, delay) {
            setTimeout(() => {
                const o = ac.createOscillator(), g = ac.createGain();
                o.type = type; o.frequency.value = f;
                g.gain.value = 0.08;
                o.connect(g).connect(ac.destination);
                o.start();
                g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + d);
                o.stop(ac.currentTime + d + 0.02);
            }, delay);
        }
        tone(220, 0.18, 'square', 0);
        tone(180, 0.18, 'square', 100);
    } catch(e) {}
})();
</script>
"""


def inject_audio_unlock_js() -> None:
    """Inject AudioContext unlock script — once per session (idempotent guard
    in JS via `window.__kk_unlock_installed`)."""
    st.html(_AUDIO_UNLOCK_JS)


def inject_auto_focus_js() -> None:
    """Re-focus scan input. Gọi cuối tab Quét trên mỗi rerun."""
    st.html(_AUTO_FOCUS_JS)


def play_beep_ok() -> None:
    st.html(_BEEP_OK_JS)


def play_beep_bad() -> None:
    st.html(_BEEP_BAD_JS)


# ═══════════════════════════════════════════════════════════════════════════
# Formatters
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_int(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def _fmt_signed(n) -> str:
    """Signed integer with U+2212 minus sign (typographic, not hyphen)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    if n < 0:
        return f"−{abs(n):,}".replace(",", ".")
    if n > 0:
        return f"+{n:,}".replace(",", ".")
    return "0"


# ═══════════════════════════════════════════════════════════════════════════
# HTML render helpers — all inline-style (no class on content elements)
# ═══════════════════════════════════════════════════════════════════════════

def status_badge_html(status: str) -> str:
    """Badge pill cho trạng thái phiếu."""
    if status == "Đang kiểm":
        bg, fg, border, ic = "var(--warn-50)", "var(--warn-700)", "var(--warn-200)", "●"
    elif status == "Chờ duyệt admin":
        bg, fg, border, ic = "var(--info-50)", "var(--info-700)", "var(--info-200)", "●"
    elif status == "Đã duyệt":
        bg, fg, border, ic = "var(--green-50)", "var(--green-700)", "var(--green-200)", "✓"
    else:
        bg, fg, border, ic = "var(--surface-3)", "var(--ink-3)", "var(--line)", "•"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:{bg};color:{fg};border:1px solid {border};'
        f'border-radius:999px;padding:3px 10px;font-size:11.5px;font-weight:700;'
        f'letter-spacing:.02em;">{ic} {status}</span>'
    )


def context_bar_html(
    ma_phieu: str,
    chi_nhanh: str,
    nhom_cha: str,
    created_by: str,
    created_at_str: str,
    progress_done: int,
    progress_total: int,
    kpi_ok: int,
    kpi_bad: int,
) -> str:
    """Top context bar trong tab Quét."""
    pct = int(round(progress_done / progress_total * 100)) if progress_total else 0
    kpi_bad_color = (
        "var(--bad-700)" if kpi_bad < 0
        else "var(--green-700)" if kpi_bad > 0
        else "var(--ink-2)"
    )
    return f'''
    <div style="background:var(--surface);border:1px solid var(--line);
                border-radius:14px;padding:14px 16px;box-shadow:var(--shadow-1);
                display:flex;align-items:center;gap:18px;margin-bottom:14px;
                flex-wrap:wrap;">
      <div style="display:flex;align-items:center;gap:10px;padding:6px 10px 6px 6px;
                  border:1px solid var(--line);border-radius:10px;
                  background:var(--surface-2);">
        <span style="background:var(--green-700);color:#fff;font-family:var(--mono);
                     font-weight:700;font-size:12px;letter-spacing:.02em;
                     padding:5px 9px;border-radius:6px;">{ma_phieu}</span>
        <span style="display:flex;flex-direction:column;line-height:1.2;">
          <span style="font-weight:600;color:var(--ink);font-size:13.5px;">
            {chi_nhanh} <span style="color:var(--ink-3);">·</span> {nhom_cha}
          </span>
          <span style="font-size:11.5px;color:var(--ink-2);">
            {created_by} · tạo {created_at_str}
          </span>
        </span>
      </div>
      <div style="flex:1;min-width:240px;display:flex;flex-direction:column;gap:6px;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;
                    font-size:12px;color:var(--ink-2);">
          <span>Tiến độ quét</span>
          <span>
            <b style="color:var(--ink);font-family:var(--mono);font-weight:600;
                      font-size:13px;">{progress_done} / {progress_total}</b>
            &nbsp;·&nbsp;
            <b style="color:var(--ink);font-family:var(--mono);font-weight:600;
                      font-size:13px;">{pct}%</b>
          </span>
        </div>
        <div style="height:8px;background:var(--surface-3);border-radius:999px;
                    overflow:hidden;">
          <span style="display:block;height:100%;border-radius:999px;
                       background:linear-gradient(90deg, var(--green-500),
                                                  var(--green-700));
                       width:{pct}%;"></span>
        </div>
      </div>
      <div style="display:flex;gap:10px;">
        <div style="border:1px solid var(--line);border-radius:10px;padding:8px 12px;
                    background:var(--surface);min-width:78px;">
          <div style="font-size:11px;color:var(--ink-3);letter-spacing:.04em;
                      text-transform:uppercase;font-weight:600;">Khớp</div>
          <div style="font-family:var(--mono);font-weight:700;font-size:17px;
                      color:var(--green-700);font-variant-numeric:tabular-nums;">
            {kpi_ok}
          </div>
        </div>
        <div style="border:1px solid var(--line);border-radius:10px;padding:8px 12px;
                    background:var(--surface);min-width:78px;">
          <div style="font-size:11px;color:var(--ink-3);letter-spacing:.04em;
                      text-transform:uppercase;font-weight:600;">Lệch</div>
          <div style="font-family:var(--mono);font-weight:700;font-size:17px;
                      color:{kpi_bad_color};font-variant-numeric:tabular-nums;">
            {_fmt_signed(kpi_bad)}
          </div>
        </div>
      </div>
    </div>
    '''


def hero_scan_card_html(item: dict | None, flash: str | None = None) -> str:
    """Hero scan card với 6 cột (item id + 5 field tiles).

    `item` keys: ma_hang, ten_hang, ma_vach, gia_ban, sl_quet, sl_thuc_te, ton.
    `flash` = "ok" | "bad" | None — apply CSS animation trên shell.
    Special: `item={"error": True, "code": "..."}` → render error overlay.
    """
    shell_anim = ""
    if flash == "ok":
        shell_anim = "animation: flashOk 550ms ease;"
    elif flash == "bad":
        shell_anim = "animation: flashBad 550ms ease;"

    # Empty state — chưa quét gì
    if not item:
        return '''
        <div style="background:var(--surface);border:1px solid var(--line);
                    border-radius:18px;box-shadow:var(--shadow-2);
                    overflow:hidden;margin-bottom:14px;padding:36px 24px;
                    text-align:center;font-family:var(--sans);">
          <div style="font-size:36px;color:var(--ink-3);margin-bottom:6px;">📷</div>
          <div style="font-size:15px;font-weight:600;color:var(--ink-2);">
            Quét mã đầu tiên để bắt đầu
          </div>
          <div style="font-size:13px;color:var(--ink-3);margin-top:4px;">
            Đưa con trỏ vào ô bên dưới và quét mã vạch / mã hàng
          </div>
        </div>
        '''

    # Error state — mã không tồn tại
    if item.get("error"):
        code_show = item.get("code", "")
        return f'''
        <div style="background:var(--surface);border:1px solid var(--bad-200);
                    border-radius:18px;box-shadow:var(--shadow-2);overflow:hidden;
                    margin-bottom:14px;{shell_anim}">
          <div style="padding:18px 20px;display:flex;align-items:center;gap:12px;
                      background:var(--bad-50);font-family:var(--sans);">
            <span style="color:var(--bad-700);font-size:22px;line-height:1;">⚠</span>
            <span style="font-size:14px;color:var(--ink-2);">
              <b style="color:var(--bad-700);font-family:var(--mono);">
                Mã &lsquo;{code_show}&rsquo;
              </b> không tồn tại trong hệ thống KiotViet
            </span>
          </div>
        </div>
        '''

    # Normal state
    ma_hang = item.get("ma_hang", "—")
    ten_hang = item.get("ten_hang", "") or "—"
    ma_vach = item.get("ma_vach", "") or "—"
    gia_ban = int(item.get("gia_ban", 0) or 0)
    sl_thuc_te = int(item.get("sl_thuc_te", item.get("sl_quet", 0)) or 0)
    ton = int(item.get("ton", 0) or 0)
    lech = sl_thuc_te - ton
    if lech < 0:
        lech_color = "var(--bad-700)"
    elif lech > 0:
        lech_color = "var(--green-700)"
    else:
        lech_color = "var(--ink-2)"
    lech_str = _fmt_signed(lech)
    gia_str = _fmt_int(gia_ban) if gia_ban else "—"
    label_text = "Phát sinh mới" if item.get("phat_sinh") else "Vừa quét · +1"

    field_style = (
        "display:flex;flex-direction:column;gap:3px;min-width:0;"
        "border-left:1px solid var(--line);padding-left:14px;"
    )
    label_style = (
        "font-size:11px;letter-spacing:.04em;text-transform:uppercase;"
        "font-weight:600;color:var(--ink-3);"
    )
    num_style = (
        "font-family:var(--mono);font-weight:700;font-size:18px;color:var(--ink);"
        "font-variant-numeric:tabular-nums;white-space:nowrap;"
        "overflow:hidden;text-overflow:ellipsis;"
    )

    return f'''
    <div style="background:var(--surface);border:1px solid var(--line);
                border-radius:18px;box-shadow:var(--shadow-2);overflow:hidden;
                margin-bottom:14px;{shell_anim}">
      <div style="padding:18px 20px 20px;display:grid;
                  grid-template-columns:minmax(260px,1.4fr) repeat(5, minmax(0, 1fr));
                  gap:18px;align-items:center;font-family:var(--sans);">
        <div style="display:flex;flex-direction:column;gap:4px;min-width:0;">
          <span style="display:inline-flex;align-items:center;gap:6px;
                       background:var(--green-50);color:var(--green-700);
                       border:1px solid var(--green-200);border-radius:999px;
                       padding:3px 10px;font-size:11px;font-weight:700;
                       letter-spacing:.04em;text-transform:uppercase;
                       width:fit-content;margin-bottom:4px;">
            ✓ {label_text}
          </span>
          <span style="font-family:var(--mono);font-weight:700;font-size:22px;
                       letter-spacing:-0.01em;color:var(--ink);white-space:nowrap;
                       overflow:hidden;text-overflow:ellipsis;">{ma_hang}</span>
          <span style="font-size:13px;color:var(--ink-2);white-space:nowrap;
                       overflow:hidden;text-overflow:ellipsis;">{ten_hang}</span>
        </div>
        <div style="{field_style}">
          <span style="{label_style}">Mã vạch</span>
          <span style="{num_style}">{ma_vach}</span>
        </div>
        <div style="{field_style}">
          <span style="{label_style}">Giá bán</span>
          <span style="{num_style}">{gia_str}<small style="font-family:var(--sans);font-size:12px;color:var(--ink-3);font-weight:500;"> ₫</small></span>
        </div>
        <div style="{field_style}">
          <span style="{label_style}">SL đã quét</span>
          <span style="font-family:var(--mono);font-weight:700;font-size:22px;
                       color:var(--green-700);font-variant-numeric:tabular-nums;">
            {sl_thuc_te}
          </span>
        </div>
        <div style="{field_style}">
          <span style="{label_style}">Tồn hệ thống</span>
          <span style="{num_style}">{ton}</span>
        </div>
        <div style="{field_style}">
          <span style="{label_style}">Lệch tạm</span>
          <span style="font-family:var(--mono);font-weight:700;font-size:18px;
                       color:{lech_color};font-variant-numeric:tabular-nums;">
            {lech_str}
          </span>
        </div>
      </div>
    </div>
    '''


def detail_empty_html() -> str:
    """Empty state cho detail panel khi chưa chọn phiếu."""
    return '''
    <div style="background:var(--surface);border:1px dashed var(--line);
                border-radius:14px;padding:36px 24px;margin-top:14px;
                text-align:center;color:var(--ink-3);font-family:var(--sans);">
      <div style="font-size:14px;font-weight:600;color:var(--ink-2);">
        Chưa chọn phiếu nào
      </div>
      <div style="font-size:13px;color:var(--ink-3);margin-top:4px;">
        Click vào một dòng trong bảng để xem chi tiết &amp; hành động
      </div>
    </div>
    '''


def detail_header_html(
    ma_phieu: str,
    chi_nhanh: str,
    nhom_cha: str,
    created_by: str,
    created_at_str: str,
    status: str,
) -> str:
    """Header card cho detail panel — status badge + mã phiếu + meta."""
    return f'''
    <div style="background:var(--surface);border:1px solid var(--line);
                border-radius:14px;padding:14px 16px;margin-top:14px;
                box-shadow:var(--shadow-1);display:flex;align-items:center;
                gap:14px;flex-wrap:wrap;font-family:var(--sans);
                animation:fadeIn .2s ease;">
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="background:var(--green-700);color:#fff;font-family:var(--mono);
                     font-weight:700;font-size:14px;letter-spacing:.02em;
                     padding:6px 10px;border-radius:6px;">{ma_phieu}</span>
        {status_badge_html(status)}
      </div>
      <div style="flex:1;min-width:200px;display:flex;flex-direction:column;
                  line-height:1.3;">
        <span style="font-weight:600;color:var(--ink);font-size:14px;">
          {chi_nhanh} <span style="color:var(--ink-3);">·</span> {nhom_cha}
        </span>
        <span style="font-size:12.5px;color:var(--ink-2);">
          {created_by} · tạo {created_at_str}
        </span>
      </div>
    </div>
    '''


def _kpi_tile_html(label: str, value: str, color: str = "var(--ink)") -> str:
    return (
        f'<div style="background:var(--surface);border:1px solid var(--line);'
        f'border-radius:10px;padding:10px 12px;box-shadow:var(--shadow-1);">'
        f'<div style="font-size:11px;color:var(--ink-3);letter-spacing:.04em;'
        f'text-transform:uppercase;font-weight:600;">{label}</div>'
        f'<div style="font-family:var(--mono);font-weight:700;font-size:18px;'
        f'color:{color};font-variant-numeric:tabular-nums;margin-top:2px;">'
        f'{value}</div></div>'
    )


def kpi_tiles_scanning_html(tong_ton: int, tong_quet: int, tong_lech: int) -> str:
    """3 KPI tiles cho phiếu Đang kiểm."""
    lech_color = (
        "var(--bad-700)" if tong_lech < 0
        else "var(--green-700)" if tong_lech > 0
        else "var(--ink)"
    )
    tiles = (
        _kpi_tile_html("Tổng tồn", _fmt_int(tong_ton))
        + _kpi_tile_html("Tổng quét", _fmt_int(tong_quet), "var(--green-700)")
        + _kpi_tile_html("Tổng chênh lệch", _fmt_signed(tong_lech), lech_color)
    )
    return (
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);'
        f'gap:10px;margin-top:12px;font-family:var(--sans);">{tiles}</div>'
    )


def kpi_tiles_waiting_html(
    tong_thuc_te_sl: int,
    tong_thuc_te_gt: int,
    tong_tang_sl: int,
    tong_tang_gt: int,
    tong_giam_sl: int,
    tong_giam_gt: int,
    tong_lech_sl: int,
    tong_lech_gt: int,
) -> str:
    """4 KPI tiles cho phiếu Chờ duyệt — bao gồm giá trị tiền."""
    tiles = (
        _kpi_tile_html(
            f"Tổng thực tế ({tong_thuc_te_sl})",
            f"{_fmt_int(tong_thuc_te_gt)} ₫",
        )
        + _kpi_tile_html(
            f"Lệch tăng (+{tong_tang_sl})",
            f"{_fmt_int(tong_tang_gt)} ₫",
            "var(--green-700)",
        )
        + _kpi_tile_html(
            f"Lệch giảm ({tong_giam_sl})",
            f"{_fmt_int(abs(tong_giam_gt))} ₫",
            "var(--bad-700)",
        )
        + _kpi_tile_html(
            f"Tổng chênh ({_fmt_signed(tong_lech_sl)})",
            f"{_fmt_signed(tong_lech_gt)} ₫",
            "var(--bad-700)" if tong_lech_gt < 0 else "var(--ink)",
        )
    )
    return (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);'
        f'gap:10px;margin-top:12px;font-family:var(--sans);">{tiles}</div>'
    )


def hint_line_html(text: str) -> str:
    """Hint text dưới scan card / toolbar."""
    return (
        f'<div style="font-size:12px;color:var(--ink-3);margin-bottom:10px;'
        f'display:flex;align-items:center;gap:6px;font-family:var(--sans);">'
        f'<span style="color:var(--green-700);">💡</span>{text}</div>'
    )

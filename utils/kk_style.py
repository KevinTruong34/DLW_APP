"""utils/kk_style.py — Helpers for the kiem_ke v2 redesign.

CSS injection strategy (per HANDOFF_kiem_ke_v2_to_claude_code.md section 1.1):

  1. Design tokens (`:root` vars) + `@keyframes` + DEBUG MARKER badge are
     declared in `_CSS_VARS_BLOCK` and injected via
     `st.markdown(..., unsafe_allow_html=True)`. DOMPurify in `st.html()`
     silently strips `<style>` tags — markdown is the safe path for global
     CSS that must reach document level so inline `var(--token)` resolves.

  2. `static/kiem_ke.css` holds font `@import` + Streamlit native widget
     overrides. Loaded via the same markdown injection from disk.

Content elements (`<div>`, `<span>`, `<section>`, ...) rendered inside
`st.html()` must use inline `style="..."` referencing the document-level
`var(--token)` — classes do not cross the st.html() iframe boundary.
"""

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import streamlit as st


_CSS_PATH = Path(__file__).parent.parent / "static" / "kiem_ke.css"


# Design tokens + flash/fade keyframes + DEBUG MARKER badge.
# DEBUG MARKER is removed in PR 8 (cleanup) once user verifies the redesign
# is live in preview — see HANDOFF section 3 (Thứ tự commit) and section 5.
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

/* DEBUG MARKER — confirms _CSS_VARS_BLOCK reached the document.
   Removed in PR 8 (cleanup) after user verifies the redesign in preview. */
.stApp::before {
    content: "KIEMKE_v2_LIVE" !important;
    position: fixed !important;
    bottom: 4px !important;
    right: 4px !important;
    background: var(--green-700) !important;
    color: #ffffff !important;
    padding: 2px 8px !important;
    border-radius: 4px !important;
    font-size: 10px !important;
    font-family: var(--mono) !important;
    z-index: 99999 !important;
    opacity: 0.6 !important;
    pointer-events: none !important;
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
    """Inject design tokens + keyframes + DEBUG MARKER + static CSS file.

    Call at the top of `module_kiem_ke()` on every rerun. Streamlit's DOM
    dedup keeps re-injection cheap, and there is no session guard so the
    styles stay present after cross-module navigation.
    """
    st.markdown(_CSS_VARS_BLOCK, unsafe_allow_html=True)
    st.markdown(f"<style>{_read_css_file()}</style>", unsafe_allow_html=True)

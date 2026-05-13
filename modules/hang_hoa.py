"""
modules/hang_hoa.py
─────────────────────────────────────────────────────────────────────────────
Module Hàng hóa — Redesign v5 (match design_handoff_hang_hoa/).

Fix bug v4 (PR #49):
1. CSS injected qua `<style>` PHẢI là tag đầu tiên trong markdown string —
   `<link>` ở đầu khiến markdown parser từ chối nhận diện HTML block (Type 6
   rule, ≥ 4-space indent → fallback text). Giải pháp: nhúng Google Fonts
   bằng `@import url(...)` BÊN TRONG `<style>` thay vì dùng `<link>` riêng.
2. Dùng `textwrap.dedent(...)` để bỏ leading whitespace của triple-quoted
   string, tránh hoàn toàn hazard 4-space indent.
3. Font fallback đầy đủ system stack — không phụ thuộc Geist load thành công.

Drop-in replacement. Layout: Header · Search row · Pills · (Conditional
detail panel) · Bảng + footer in tem.

Giữ NGUYÊN:
- Imports utils.config / utils.db / utils.auth / utils.helpers.
- _build_df, _apply_filters (bỏ low_only).
- _render_them_moi / _render_sua_hang_hoa / _render_chinh_ton /
  _render_an_hang_hoa.
- _dlg_in_tem_hh / _render_dialog_in_tem / _trigger_print_window.
- Session state keys: hh_cn / hh_ma_chon / hh_search_cnt / hh_cha / hh_con /
  hh_sort / _hh_in_tem_items / _intem_hh_qty / _intem_hh_symb.
"""

import textwrap
import streamlit as st
import pandas as pd

from utils.config import ALL_BRANCHES, CN_SHORT
from utils.db import (
    supabase, log_action, load_the_kho, load_hang_hoa,
)
from utils.auth import (
    is_admin, is_ke_toan_or_admin,
    get_active_branch, get_accessible_branches,
)
from utils.helpers import _normalize


# ═══════════════════════════════════════════════════════════════════════
# DESIGN TOKENS (match design_handoff_hang_hoa/design_reference/styles.css)
# ═══════════════════════════════════════════════════════════════════════
T = {
    "bg":         "#f6f5f2",
    "surface":    "#ffffff",
    "surface_2":  "#fbfaf7",
    "ink":        "#1a1a18",
    "ink_2":      "#44443f",
    "muted":      "#8a8a82",
    "muted_2":    "#b4b3aa",
    "border":     "#ece9e2",
    "border_2":   "#e0dcd2",
    "accent":     "#c63a2b",
    "accent_2":   "#fbe9e5",
    "accent_ink": "#8a2418",
    "good":       "#2f6b3f",
}


def _inject_css_once():
    """Inject CSS 1 lần per session.

    LƯU Ý: `<style>` PHẢI là tag đầu tiên trong markdown string, không
    được có `<link>` trước. CommonMark Type 1 (script/style/pre/textarea)
    là duy nhất bypass quy tắc 4-space indent của Type 6.
    Google Fonts load qua `@import url(...)` bên trong `<style>` block.
    """
    if st.session_state.get("_hh_css_v5"):
        return
    st.session_state["_hh_css_v5"] = True
    css = textwrap.dedent(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap');

    :root {{
      --bg:        {T['bg']};
      --surface:   {T['surface']};
      --surface-2: {T['surface_2']};
      --ink:       {T['ink']};
      --ink-2:     {T['ink_2']};
      --muted:     {T['muted']};
      --muted-2:   {T['muted_2']};
      --border:    {T['border']};
      --border-2:  {T['border_2']};
      --accent:    {T['accent']};
      --accent-2:  {T['accent_2']};
      --accent-ink:{T['accent_ink']};
      --good:      {T['good']};
      --radius:    10px;
      --radius-sm: 7px;
      --font:      "Geist","Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
      --mono:      "Geist Mono","JetBrains Mono",ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
    }}

    /* Page bg (warm neutral) */
    .stApp {{ background: {T['bg']} !important; }}
    .block-container {{
      padding-top: 1.2rem !important;
      padding-bottom: 2rem !important;
      font-family: var(--font);
      color: var(--ink);
    }}
    .block-container, .block-container * {{ font-family: var(--font); }}

    /* Container bordered → white surface */
    [data-testid="stVerticalBlockBorderWrapper"] {{
      background: var(--surface) !important;
      border-radius: var(--radius) !important;
      border: 1px solid var(--border) !important;
    }}
    [data-baseweb="popover"] [data-testid="stVerticalBlockBorderWrapper"] {{
      background: var(--surface) !important;
      border: 1px solid var(--border-2) !important;
    }}

    /* ─── Header ─── */
    .hh-title {{
      font-size: 22px; font-weight: 600; letter-spacing: -.02em;
      color: var(--ink);
    }}
    .hh-sub {{
      font-size: 12px; color: var(--muted);
      font-variant-numeric: tabular-nums;
    }}
    .hh-branch-chip {{
      display: inline-flex; align-items: center; gap: 7px;
      height: 30px; padding: 0 12px;
      background: var(--surface); color: var(--ink);
      border: 1px solid var(--border-2);
      border-radius: var(--radius-sm);
      font-size: 12.5px; font-weight: 500;
    }}
    .hh-branch-chip .dot {{
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--good);
    }}

    /* ─── Code chips ─── */
    .hh-code {{
      display: inline-block;
      font-family: var(--mono); font-size: 11.5px;
      color: var(--ink-2);
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 5px;
      padding: 2px 7px;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .hh-code.dashed {{ background: transparent; border-style: dashed; }}

    /* ─── Detail panel ─── */
    .hh-detail-name {{
      font-size: 17px; font-weight: 600; letter-spacing: -.012em;
      color: var(--ink);
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    }}
    .hh-detail-meta {{
      margin-top: 6px;
      font-size: 12.5px; color: var(--muted);
      display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    }}
    .hh-detail-meta b {{
      color: var(--ink); font-weight: 600;
      font-variant-numeric: tabular-nums;
    }}
    .hh-detail-meta .sep {{ color: var(--muted-2); }}

    .hh-branch-grid {{
      margin-top: 16px;
      display: grid; gap: 10px;
      grid-template-columns: repeat(3, 1fr);
    }}
    .hh-branch-card {{
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 12px 14px;
    }}
    .hh-branch-card.active {{
      background: #fff;
      border-color: var(--ink);
    }}
    .hh-branch-card .b-label {{
      font-size: 11px; color: var(--muted);
      text-transform: uppercase; letter-spacing: .04em;
      display: flex; align-items: center; gap: 6px;
    }}
    .hh-branch-card .b-pin {{
      width: 5px; height: 5px; border-radius: 50%;
      background: var(--ink);
    }}
    .hh-branch-card .b-val {{
      margin-top: 4px;
      font-size: 26px; font-weight: 600;
      letter-spacing: -.02em;
      font-variant-numeric: tabular-nums;
      color: var(--ink);
    }}
    .hh-branch-card .b-share {{
      font-size: 11px; color: var(--muted); margin-top: 2px;
    }}
    .hh-branch-card .b-bar {{
      margin-top: 10px;
      height: 3px; background: var(--border);
      border-radius: 2px; overflow: hidden;
    }}
    .hh-branch-card .b-fill {{
      height: 100%; background: var(--ink); border-radius: 2px;
    }}
    .hh-branch-card.active .b-fill {{ background: var(--accent); }}

    /* ─── Buttons (Streamlit override) ─── */
    div[data-testid="stButton"] > button[kind="primary"] {{
      background: var(--ink); color: #faf9f6;
      border: 1px solid var(--ink);
      border-radius: 999px; height: 30px;
      font-size: 12.5px; font-weight: 500;
      padding: 0 14px;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover {{
      background: #000; border-color: #000;
    }}
    div[data-testid="stButton"] > button[kind="secondary"] {{
      background: var(--surface); color: var(--ink-2);
      border: 1px solid var(--border);
      border-radius: 999px; height: 30px;
      font-size: 12px; font-weight: 400;
      padding: 0 12px;
    }}
    div[data-testid="stButton"] > button[kind="secondary"]:hover {{
      background: var(--surface-2);
    }}

    .hh-header-actions [data-testid="stPopover"] > div > button {{
      background: var(--ink) !important;
      color: #faf9f6 !important;
      border: 1px solid var(--ink) !important;
      border-radius: var(--radius-sm) !important;
      height: 30px !important;
      font-size: 12.5px !important;
      font-weight: 500 !important;
      padding: 0 14px !important;
    }}
    .hh-header-actions [data-testid="stPopover"] > div > button:hover {{
      background: #000 !important; border-color: #000 !important;
    }}

    .hh-print-zone div[data-testid="stButton"] > button {{
      background: var(--accent) !important; color: #fff !important;
      border: 1px solid var(--accent) !important;
      border-radius: var(--radius-sm) !important;
      height: 34px !important; font-size: 13px !important;
      font-weight: 500 !important;
    }}
    .hh-print-zone div[data-testid="stButton"] > button:hover {{
      background: #b3331f !important; border-color: #b3331f !important;
    }}
    .hh-print-zone div[data-testid="stButton"] > button:disabled {{
      opacity: .45 !important; cursor: not-allowed !important;
    }}

    .hh-icon-btn div[data-testid="stButton"] > button {{
      background: var(--surface) !important; color: var(--ink-2) !important;
      border: 1px solid var(--border-2) !important;
      border-radius: var(--radius-sm) !important;
      height: 30px !important;
      font-size: 14px !important;
      padding: 0 !important;
    }}
    .hh-icon-btn div[data-testid="stButton"] > button:hover {{
      background: var(--surface-2) !important;
    }}

    .hh-filter-tag {{
      display: inline-flex; align-items: center; gap: 4px;
      background: var(--surface-2); border: 1px solid var(--border);
      border-radius: 5px; padding: 2px 7px;
      font-size: 11px; color: var(--ink-2);
      margin-left: 6px;
    }}
    </style>
    """).strip()
    st.markdown(css, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# ENTRY
# ═══════════════════════════════════════════════════════════════════════
def module_hang_hoa():
    _inject_css_once()
    try:
        active     = get_active_branch()
        accessible = get_accessible_branches()

        master = load_hang_hoa()
        if master.empty and load_the_kho(branches_key=tuple([active])).empty:
            if is_admin():
                st.info("Chưa có dữ liệu hàng hóa.")
                _render_them_moi()
            else:
                st.info("Chưa có dữ liệu. Vào ⚙️ Quản trị → Upload để tải lên.")
            return

        view_branches = _render_header(active, accessible, total=len(master))
        if not view_branches:
            st.warning("Chọn ít nhất một chi nhánh.")
            return

        the_kho = load_the_kho(branches_key=tuple(view_branches))
        df = _build_df(master, the_kho)

        keyword, sort_by = _render_search(df)
        cha_chon = _render_pills(df)
        con_chon = st.session_state.get("hh_con", "Tất cả")

        filtered = _apply_filters(df, keyword, cha_chon, con_chon, sort_by)

        if filtered.empty:
            st.warning("Không tìm thấy hàng hóa phù hợp.")
            return

        if len(filtered) == 1:
            st.session_state["hh_ma_chon"] = filtered.iloc[0]["ma_hang"]

        ma_chon = st.session_state.get("hh_ma_chon")
        if ma_chon and ma_chon not in filtered["ma_hang"].values:
            st.session_state.pop("hh_ma_chon", None)
            ma_chon = None

        if ma_chon:
            _render_product_detail(filtered, ma_chon, active)
        elif cha_chon and cha_chon != "Tất cả":
            _render_group_detail(cha_chon, filtered, active)

        _render_table(filtered, view_branches, cha_chon, keyword)

    except Exception as e:
        st.error(f"Lỗi tải Hàng hóa: {e}")


# ═══════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════
def _render_header(active: str, accessible: list, total: int):
    c1, c2, c3, c4 = st.columns([5.5, 1.6, 0.6, 1.7])

    with c1:
        st.markdown(
            f"<div style='display:flex;align-items:baseline;gap:14px;padding-top:4px;'>"
            f"<span class='hh-title'>Hàng hóa</span>"
            f"<span class='hh-sub'>{total:,} SKU · 3 chi nhánh</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with c2:
        if is_ke_toan_or_admin() and len(accessible) > 1:
            label = f"● {CN_SHORT.get(active, active)} ⌄"
            with st.popover(label, use_container_width=True):
                view = st.multiselect(
                    "Chi nhánh xem:", accessible,
                    default=st.session_state.get("hh_cn", [active]),
                    key="hh_cn", label_visibility="collapsed",
                )
                if not view:
                    view = [active]
        else:
            st.markdown(
                f"<div style='display:flex;justify-content:center;padding-top:5px;'>"
                f"<span class='hh-branch-chip'><span class='dot'></span>"
                f"{CN_SHORT.get(active, active)}</span></div>",
                unsafe_allow_html=True,
            )
            return [active]

    with c3:
        st.markdown("<div class='hh-icon-btn'>", unsafe_allow_html=True)
        if st.button("↻", key="hh_reload", help="Tải lại", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with c4:
        if is_admin():
            st.markdown("<div class='hh-header-actions'>", unsafe_allow_html=True)
            with st.popover("+ Thêm hàng hóa", use_container_width=True):
                _render_them_moi()
            st.markdown("</div>", unsafe_allow_html=True)

    return st.session_state.get("hh_cn", [active])


# ═══════════════════════════════════════════════════════════════════════
# SEARCH ROW + SORT
# ═══════════════════════════════════════════════════════════════════════
def _render_search(df: pd.DataFrame):
    with st.container(border=True):
        cs, cb, csort = st.columns([7, 0.7, 2.3])
        with cs:
            _sc = st.session_state.get("hh_search_cnt", 0)
            keyword = st.text_input(
                "", key=f"hh_search_{_sc}",
                placeholder="🔍  Tìm theo tên, mã hàng hoặc mã vạch…",
                label_visibility="collapsed",
            )
        with cb:
            st.markdown("<div class='hh-icon-btn'>", unsafe_allow_html=True)
            st.button("⌷", key="hh_scan", help="Quét mã vạch",
                      use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with csort:
            sort_by = st.selectbox(
                "Sắp xếp:",
                ["Tên A → Z", "Giá cao → thấp", "Giá thấp → cao",
                 "Mã hàng A → Z", "Tồn: cao → thấp", "Tồn: thấp → cao"],
                key="hh_sort", label_visibility="collapsed",
            )
    return keyword, sort_by


# ═══════════════════════════════════════════════════════════════════════
# PILLS (clickable - st.button primary/secondary)
# ═══════════════════════════════════════════════════════════════════════
def _render_pills(df: pd.DataFrame):
    cha_chon = st.session_state.get("hh_cha", "Tất cả")
    counts = df.groupby("_cha").size().sort_values(ascending=False)
    top_groups = [g for g in counts.index.tolist() if g][:6]
    total = len(df)

    labels = ["Tất cả"] + top_groups
    weights = [1.0] + [max(1.4, len(g) * 0.10 + 1.0) for g in top_groups]
    weights.append(2.0)

    cols = st.columns(weights)
    for i, lbl in enumerate(labels):
        with cols[i]:
            count = total if lbl == "Tất cả" else int(counts.get(lbl, 0))
            is_active = (lbl == "Tất cả" and cha_chon == "Tất cả") or (lbl == cha_chon)
            display = f"{lbl}  {count}"
            if st.button(
                display, key=f"hh_pill_{i}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                if lbl == "Tất cả":
                    st.session_state["hh_cha"] = "Tất cả"
                    st.session_state["hh_con"] = "Tất cả"
                elif lbl == cha_chon:
                    st.session_state["hh_cha"] = "Tất cả"
                    st.session_state["hh_con"] = "Tất cả"
                else:
                    st.session_state["hh_cha"] = lbl
                    st.session_state["hh_con"] = "Tất cả"
                st.session_state.pop("hh_ma_chon", None)
                st.rerun()
    with cols[-1]:
        with st.popover("⊞ Bộ lọc nâng cao", use_container_width=True):
            cha_list = sorted([c for c in df["_cha"].dropna().unique() if c])
            opts = ["Tất cả"] + cha_list
            cur_idx = opts.index(cha_chon) if cha_chon in opts else 0
            cha_sel = st.selectbox(
                "Nhóm hàng:", opts, index=cur_idx, key="hh_cha_adv",
            )
            if cha_sel != cha_chon:
                st.session_state["hh_cha"] = cha_sel
                st.session_state["hh_con"] = "Tất cả"
                st.session_state.pop("hh_ma_chon", None)
                st.rerun()
            if cha_sel != "Tất cả":
                con_list = sorted([c for c in
                    df[df["_cha"] == cha_sel]["_con"].dropna().unique() if c])
                st.selectbox(
                    "Nhóm con:", ["Tất cả"] + con_list, key="hh_con",
                )
    return st.session_state.get("hh_cha", "Tất cả")


# ═══════════════════════════════════════════════════════════════════════
# DATA BUILD + FILTERS
# ═══════════════════════════════════════════════════════════════════════
def _build_df(master: pd.DataFrame, the_kho: pd.DataFrame) -> pd.DataFrame:
    has_master = not master.empty
    if has_master and not the_kho.empty:
        kho_agg = the_kho.groupby("Mã hàng", as_index=False).agg(
            Ton_cuoi=("Tồn cuối kì", "sum"))
        df = master.merge(kho_agg, left_on="ma_hang", right_on="Mã hàng", how="left")
        df["Ton_cuoi"] = df["Ton_cuoi"].fillna(0).astype(int)
    elif has_master:
        df = master.copy()
        df["Ton_cuoi"] = 0
    else:
        df = the_kho.groupby(["Mã hàng", "Tên hàng"], as_index=False).agg(
            Ton_cuoi=("Tồn cuối kì", "sum"))
        for col, default in (("ma_hang", ""), ("ma_vach", ""), ("ten_hang", ""),
                             ("nhom_hang", ""), ("thuong_hieu", ""),
                             ("loai_hang", ""), ("gia_ban", 0), ("bao_hanh", "")):
            df[col] = default if col != "ten_hang" else df["Tên hàng"]
        df["ma_hang"] = df["Mã hàng"]; df["ma_vach"] = df["Mã hàng"]

    if "loai_hang" in df.columns and df["loai_hang"].fillna("").str.strip().any():
        df["_cha"] = df["loai_hang"].fillna("").str.strip()
        df["_con"] = df.get("thuong_hieu", pd.Series([""] * len(df))).fillna("").str.strip()
    else:
        nhom_col = df["nhom_hang"].fillna("") if "nhom_hang" in df.columns else pd.Series([""] * len(df))
        split = nhom_col.str.split(">>", n=1, expand=True)
        df["_cha"] = split[0].str.strip()
        df["_con"] = (split[1].str.strip() if 1 in split.columns else "").fillna("")

    df["_norm_ma"]   = df["ma_hang"].apply(_normalize)
    df["_norm_vach"] = df.get("ma_vach", df["ma_hang"]).apply(
        lambda x: _normalize(x) if pd.notna(x) else "")
    df["_norm_ten"]  = df["ten_hang"].apply(_normalize)
    if "gia_ban" not in df.columns:
        df["gia_ban"] = 0
    df["gia_ban"] = pd.to_numeric(df["gia_ban"], errors="coerce").fillna(0).astype(int)
    return df


def _apply_filters(df, keyword, cha_chon, con_chon, sort_by):
    out = df.copy()
    kw = _normalize(keyword) if keyword and keyword.strip() else ""
    if kw:
        out = out[
            out["_norm_ma"].str.contains(kw, na=False)
            | out["_norm_vach"].str.contains(kw, na=False)
            | out["_norm_ten"].str.contains(kw, na=False)
        ]
    if cha_chon and cha_chon != "Tất cả":
        out = out[out["_cha"] == cha_chon]
    if con_chon and con_chon != "Tất cả":
        out = out[out["_con"] == con_chon]

    sort_map = {
        "Tên A → Z":        ("ten_hang", True),
        "Giá cao → thấp":   ("gia_ban",  False),
        "Giá thấp → cao":   ("gia_ban",  True),
        "Mã hàng A → Z":    ("ma_hang",  True),
        "Tồn: cao → thấp":  ("Ton_cuoi", False),
        "Tồn: thấp → cao":  ("Ton_cuoi", True),
    }
    col, asc = sort_map.get(sort_by, ("ten_hang", True))
    if col in out.columns:
        out = out.sort_values(col, ascending=asc)
    return out.reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════
# DETAIL PANEL — Product
# ═══════════════════════════════════════════════════════════════════════
def _branch_data_for_product(ma_chon: str):
    branch_tons = {cn: 0 for cn in ALL_BRANCHES}
    branch_kho_ids = {cn: None for cn in ALL_BRANCHES}
    try:
        all_kho = load_the_kho(branches_key=tuple(ALL_BRANCHES))
        if not all_kho.empty:
            rk = all_kho[all_kho["Mã hàng"].astype(str).str.strip() == str(ma_chon).strip()]
            for _, kr in rk.iterrows():
                cn = kr.get("Chi nhánh", "")
                if cn in branch_tons:
                    branch_tons[cn] += int(kr.get("Tồn cuối kì", 0) or 0)
                    branch_kho_ids[cn] = kr.get("id")
    except Exception:
        pass
    return branch_tons, branch_kho_ids


def _branch_grid_html(branch_tons: dict, active: str) -> str:
    total = sum(branch_tons.values())
    max_v = max(branch_tons.values()) or 1
    cards = ['<div class="hh-branch-grid">']
    for cn in ALL_BRANCHES:
        n = branch_tons[cn]
        share = (n / total * 100) if total else 0
        pct_bar = (n / max_v * 100) if max_v else 0
        is_act = (cn == active)
        cls = "hh-branch-card active" if is_act else "hh-branch-card"
        pin = '<span class="b-pin"></span>' if is_act else ''
        cards.append(
            f'<div class="{cls}">'
            f'  <div class="b-label">{pin}{CN_SHORT.get(cn, cn).upper()}</div>'
            f'  <div class="b-val">{n:,}</div>'
            f'  <div class="b-share">{share:.0f}% tổng tồn</div>'
            f'  <div class="b-bar"><div class="b-fill" style="width:{pct_bar:.1f}%"></div></div>'
            f'</div>'
        )
    cards.append('</div>')
    return ''.join(cards)


def _render_product_detail(filtered: pd.DataFrame, ma_chon: str, active: str):
    row_m = filtered[filtered["ma_hang"] == ma_chon].iloc[0]
    branch_tons, branch_kho_ids = _branch_data_for_product(ma_chon)

    name = str(row_m.get("ten_hang", ""))
    ma   = str(row_m.get("ma_hang", ""))
    vach = str(row_m.get("ma_vach", "") or "")
    gb   = int(row_m.get("gia_ban", 0) or 0)
    nhom = str(row_m.get("_cha", "") or "")
    th   = str(row_m.get("thuong_hieu", "") or "")

    chips = f'<span class="hh-code">{ma}</span>'
    if vach and vach != ma:
        chips += f' <span class="hh-code dashed">{vach}</span>'

    meta_bits = []
    if nhom:
        meta_bits.append(nhom)
    if th and th != "—":
        meta_bits.append(f'<span class="sep">›</span> {th}')
    meta_html = " ".join(meta_bits)
    if meta_html:
        meta_html += ' <span class="sep">·</span> '
    meta_html += f'Giá bán <b>{(f"{gb:,} đ" if gb else "—")}</b>'

    with st.container(border=True):
        rc1, rc2 = st.columns([8.5, 0.5])
        with rc1:
            st.markdown(
                f"<div class='hh-detail-name'>{name} {chips}</div>"
                f"<div class='hh-detail-meta'>{meta_html}</div>",
                unsafe_allow_html=True,
            )
        with rc2:
            st.markdown("<div class='hh-icon-btn'>", unsafe_allow_html=True)
            if st.button("✕", key="hh_dt_close", help="Bỏ chọn",
                         use_container_width=True):
                st.session_state.pop("hh_ma_chon", None)
                st.session_state["hh_search_cnt"] = (
                    st.session_state.get("hh_search_cnt", 0) + 1)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        is_adm = is_admin()
        _spacer, ab = st.columns([6, 4])
        with ab:
            a1, a2, a3, a4 = st.columns(4)
            with a1:
                with st.popover("✎", use_container_width=True,
                                help="Sửa thông tin"):
                    if is_adm: _render_sua_hang_hoa(row_m)
                    else:      st.info("Cần quyền admin.")
            with a2:
                with st.popover("▣", use_container_width=True,
                                help="Chỉnh tồn kho"):
                    if is_adm:
                        _render_chinh_ton(ma, row_m, branch_tons, branch_kho_ids)
                    else:
                        st.info("Cần quyền admin.")
            with a3:
                with st.popover("↺", use_container_width=True,
                                help="Lịch sử giao dịch"):
                    st.caption("Lịch sử nhập / bán / chuyển kho")
                    st.info("(Đang phát triển)")
            with a4:
                with st.popover("⊘", use_container_width=True,
                                help="Ẩn hàng hóa"):
                    if is_adm: _render_an_hang_hoa(ma, name)
                    else:      st.info("Cần quyền admin.")

        st.markdown(_branch_grid_html(branch_tons, active),
                    unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# DETAIL PANEL — Group
# ═══════════════════════════════════════════════════════════════════════
def _render_group_detail(group_name: str, df_group: pd.DataFrame, active: str):
    branch_tons = {cn: 0 for cn in ALL_BRANCHES}
    try:
        ma_list = df_group["ma_hang"].astype(str).str.strip().tolist()
        all_kho = load_the_kho(branches_key=tuple(ALL_BRANCHES))
        if not all_kho.empty and ma_list:
            sub = all_kho[all_kho["Mã hàng"].astype(str).str.strip().isin(ma_list)]
            for _, kr in sub.iterrows():
                cn = kr.get("Chi nhánh", "")
                if cn in branch_tons:
                    branch_tons[cn] += int(kr.get("Tồn cuối kì", 0) or 0)
    except Exception:
        pass

    n_sku = len(df_group)
    with st.container(border=True):
        rc1, rc2 = st.columns([8.5, 0.5])
        with rc1:
            st.markdown(
                f"<div class='hh-detail-name'>{group_name} "
                f"<span class='hh-code'>{n_sku} SKU</span></div>"
                f"<div class='hh-detail-meta'>"
                f"Tồn kho theo chi nhánh <span class='sep'>·</span> "
                f"Cộng dồn toàn bộ SKU trong nhóm"
                f"</div>",
                unsafe_allow_html=True,
            )
        with rc2:
            st.markdown("<div class='hh-icon-btn'>", unsafe_allow_html=True)
            if st.button("✕", key="hh_gr_close", help="Bỏ lọc nhóm",
                         use_container_width=True):
                st.session_state["hh_cha"] = "Tất cả"
                st.session_state["hh_con"] = "Tất cả"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(_branch_grid_html(branch_tons, active),
                    unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# TABLE + IN TEM FOOTER
# ═══════════════════════════════════════════════════════════════════════
def _render_table(filtered: pd.DataFrame, view_branches: list,
                  cha_chon: str, keyword: str):
    total = len(filtered)

    ma_v = filtered.get("ma_vach", filtered["ma_hang"]).fillna("")
    disp = pd.DataFrame({
        "Sản phẩm":  filtered["ten_hang"].astype(str),
        "Nhóm":      filtered["_cha"].astype(str),
        "Mã hàng":   filtered["ma_hang"].astype(str),
        "Mã vạch":   ma_v.astype(str),
        "Giá bán":   filtered["gia_ban"].astype(int),
    })

    tags_html = ""
    if cha_chon and cha_chon != "Tất cả":
        tags_html += f"<span class='hh-filter-tag'>Nhóm: {cha_chon}</span>"
    if keyword and keyword.strip():
        tags_html += f"<span class='hh-filter-tag'>Từ khóa: \"{keyword.strip()}\"</span>"

    st.markdown(
        f"<div style='font-size:12px;color:{T['muted']};padding:4px 2px;"
        f"display:flex;align-items:center;'>"
        f"<b style='color:{T['ink']};font-weight:500'>{total:,}</b>"
        f"&nbsp;sản phẩm{tags_html}"
        f"</div>",
        unsafe_allow_html=True,
    )

    col_cfg = {
        "Sản phẩm": st.column_config.TextColumn("Sản phẩm", width="large"),
        "Nhóm":     st.column_config.TextColumn("Nhóm",     width="medium"),
        "Mã hàng":  st.column_config.TextColumn("Mã hàng",  width="small"),
        "Mã vạch":  st.column_config.TextColumn("Mã vạch",  width="small"),
        "Giá bán":  st.column_config.NumberColumn(
            "Giá bán", format="%d ₫", width="small"),
    }

    event = st.dataframe(
        disp,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key="hh_table_v5",
        column_config=col_cfg,
        height=min(560, 42 + len(disp) * 36 + 4),
    )

    sel = event.selection.rows if event.selection else []
    pre_ma = st.session_state.get("hh_ma_chon")

    if len(sel) == 1 and sel[0] < len(disp):
        new_ma = disp.iloc[sel[0]]["Mã hàng"]
        if new_ma != pre_ma:
            st.session_state["hh_ma_chon"] = new_ma
            st.rerun()
    elif len(sel) >= 2 and pre_ma:
        st.session_state.pop("hh_ma_chon", None)
        st.rerun()

    n_sel = len(sel)
    hint = ("Tick các dòng cần in tem, hoặc click 1 dòng để xem chi tiết."
            if n_sel < 2 else
            f"Đã chọn <b>{n_sel} sản phẩm</b> để in tem.")
    st.markdown("<div class='hh-print-zone'>", unsafe_allow_html=True)
    fl, fr = st.columns([5, 2])
    with fl:
        st.markdown(
            f"<div style='font-size:12px;color:{T['muted']};padding-top:8px;'>"
            f"{hint}</div>",
            unsafe_allow_html=True,
        )
    with fr:
        btn_label = (f"🏷️ In tem mã vạch  ({n_sel})"
                     if n_sel >= 2 else "🏷️ In tem mã vạch")
        if st.button(
            btn_label,
            disabled=(n_sel < 2),
            key="hh_btn_in_tem",
            use_container_width=True,
        ):
            items_for_print = []
            for idx in sel:
                if idx >= len(disp):
                    continue
                mh = disp.iloc[idx]["Mã hàng"]
                row = filtered[filtered["ma_hang"] == mh]
                if row.empty:
                    continue
                r = row.iloc[0]
                ma_vach_raw = r.get("ma_vach")
                ma_vach_clean = "" if pd.isna(ma_vach_raw) else str(ma_vach_raw).strip()
                gia_ban_raw = r.get("gia_ban", 0)
                gia_ban_clean = 0 if pd.isna(gia_ban_raw) else int(gia_ban_raw or 0)
                items_for_print.append({
                    "ma_hang":  str(r.get("ma_hang", "")),
                    "ten_hang": str(r.get("ten_hang", "")),
                    "gia_ban":  gia_ban_clean,
                    "ma_vach":  ma_vach_clean,
                    "qty":      1,
                })
            st.session_state["_hh_in_tem_items"] = items_for_print
            st.session_state.pop("_intem_hh_qty", None)
            _dlg_in_tem_hh()
    st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# ADMIN POPOVERS — Sửa info / Chỉnh tồn / Thêm mới / Ẩn
# ═══════════════════════════════════════════════════════════════════════
def _render_chinh_ton(ma_chon, row_m, branch_tons, branch_kho_ids):
    st.caption("Điều chỉnh trực tiếp tồn kho từng chi nhánh.")
    adj = {}
    for cn in ALL_BRANCHES:
        adj[cn] = st.number_input(
            CN_SHORT.get(cn, cn), min_value=0, step=1,
            value=branch_tons[cn], key=f"adj_v5_{ma_chon}_{cn}",
        )
    if st.button("💾 Lưu", type="primary", use_container_width=True,
                 key=f"save_ton_v5_{ma_chon}"):
        try:
            changed = []
            for cn in ALL_BRANCHES:
                new_n = int(adj[cn]); old_n = branch_tons[cn]
                if new_n == old_n: continue
                kho_id = branch_kho_ids[cn]
                if kho_id:
                    supabase.table("the_kho").update(
                        {"Tồn cuối kì": new_n}).eq("id", kho_id).execute()
                else:
                    supabase.table("the_kho").insert({
                        "Mã hàng":     str(ma_chon),
                        "Tên hàng":    str(row_m.get("ten_hang", "")),
                        "Chi nhánh":   cn,
                        "Tồn cuối kì": new_n,
                        "Tồn đầu kì":  0,
                    }).execute()
                changed.append(f"{CN_SHORT.get(cn, cn)}: {old_n}→{new_n}")
            if changed:
                st.cache_data.clear()
                log_action("KHO_ADJ", f"ma={ma_chon} " + ", ".join(changed))
                st.success("✓ " + " · ".join(changed))
                st.rerun()
            else:
                st.info("Không có thay đổi.")
        except Exception as e:
            st.error(f"Lỗi: {e}")


def _render_them_moi():
    master = load_hang_hoa()
    loai_opts = (sorted(master["loai_hang"].dropna().unique().tolist())
                 if not master.empty and "loai_hang" in master.columns else [])
    cnt = st.session_state.get("hh_them_cnt", 0)

    c1, c2 = st.columns(2)
    with c1:
        new_ma   = st.text_input("Mã hàng *", key=f"hh_new_ma_{cnt}",
                                  placeholder="PDH130")
        new_ten  = st.text_input("Tên hàng *", key=f"hh_new_ten_{cnt}")
        new_vach = st.text_input("Mã vạch", key=f"hh_new_vach_{cnt}")
        new_gb   = st.number_input("Giá bán", min_value=0, step=10000,
                                    key=f"hh_new_gb_{cnt}", value=0)
    with c2:
        new_loai_sp = st.radio("Loại SP:", ["Hàng hóa", "Dịch vụ"],
                                horizontal=True, key=f"hh_new_loai_sp_{cnt}")
        loai_sel = st.selectbox("Loại hàng",
            ["-- Chọn --"] + loai_opts + ["(Nhập mới)"],
            key=f"hh_new_loai_{cnt}")
        new_loai = (st.text_input("Tên loại mới", key=f"hh_new_loai_txt_{cnt}")
                    if loai_sel == "(Nhập mới)"
                    else ("" if loai_sel == "-- Chọn --" else loai_sel))

        th_opts = []
        if new_loai and not master.empty and "thuong_hieu" in master.columns:
            th_opts = sorted(master[master["loai_hang"] == new_loai][
                "thuong_hieu"].dropna().unique().tolist())
        th_sel = st.selectbox("Thương hiệu",
            ["-- Chọn --"] + th_opts + ["(Nhập mới)"],
            key=f"hh_new_th_{cnt}")
        new_th = (st.text_input("TH mới", key=f"hh_new_th_txt_{cnt}")
                  if th_sel == "(Nhập mới)"
                  else ("" if th_sel == "-- Chọn --" else th_sel))
        new_bh = st.text_input("Bảo hành", key=f"hh_new_bh_{cnt}",
                                placeholder="12 tháng")

    can_add = bool(new_ma.strip()) and bool(new_ten.strip())
    if st.button("➕ Thêm", type="primary", use_container_width=True,
                 disabled=not can_add, key=f"hh_add_btn_{cnt}"):
        ma_clean = new_ma.strip().upper()
        if (not master.empty
                and ma_clean in master["ma_hang"].astype(str).str.upper().values):
            st.error(f"Mã **{ma_clean}** đã tồn tại.")
        else:
            try:
                supabase.table("hang_hoa").insert({
                    "ma_hang":     ma_clean,
                    "ten_hang":    new_ten.strip(),
                    "ma_vach":     new_vach.strip() or None,
                    "gia_ban":     int(new_gb),
                    "loai_sp":     new_loai_sp,
                    "loai_hang":   new_loai or None,
                    "thuong_hieu": new_th or None,
                    "bao_hanh":    new_bh.strip() or None,
                    "active":      True,
                }).execute()
                st.cache_data.clear()
                log_action("HH_ADD", f"ma={ma_clean} ten={new_ten.strip()}")
                st.success(f"✓ Đã thêm {ma_clean}")
                st.session_state["hh_them_cnt"] = cnt + 1
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi: {e}")


def _render_sua_hang_hoa(row_m):
    ma = str(row_m["ma_hang"])
    cnt = st.session_state.get(f"hh_sua_cnt_{ma}", 0)
    master = load_hang_hoa()
    loai_opts = (sorted(master["loai_hang"].dropna().unique().tolist())
                 if not master.empty and "loai_hang" in master.columns else [])
    cur_loai = str(row_m.get("loai_hang") or "")
    cur_th   = str(row_m.get("thuong_hieu") or "")

    new_ten  = st.text_input("Tên", value=str(row_m.get("ten_hang", "")),
                              key=f"hh_sua_ten_{ma}_{cnt}")
    new_vach = st.text_input("Mã vạch", value=str(row_m.get("ma_vach", "") or ""),
                              key=f"hh_sua_vach_{ma}_{cnt}")
    new_gb   = st.number_input("Giá bán", min_value=0, step=10000,
                                value=int(row_m.get("gia_ban", 0) or 0),
                                key=f"hh_sua_gb_{ma}_{cnt}")
    sp_options = ["Hàng hóa", "Dịch vụ"]
    cur_sp = str(row_m.get("loai_sp") or "Hàng hóa")
    new_loai_sp = st.radio("Loại SP:", sp_options,
                            index=sp_options.index(cur_sp) if cur_sp in sp_options else 0,
                            horizontal=True, key=f"hh_sua_loai_sp_{ma}_{cnt}")
    loai_idx = (loai_opts.index(cur_loai) + 1) if cur_loai in loai_opts else 0
    loai_sel = st.selectbox("Loại hàng", ["-- Giữ nguyên --"] + loai_opts,
                             index=loai_idx, key=f"hh_sua_loai_{ma}_{cnt}")
    new_loai = "" if loai_sel == "-- Giữ nguyên --" else loai_sel

    th_opts = []
    check_loai = new_loai or cur_loai
    if check_loai and not master.empty and "thuong_hieu" in master.columns:
        th_opts = sorted(master[master["loai_hang"] == check_loai][
            "thuong_hieu"].dropna().unique().tolist())
    th_idx = (th_opts.index(cur_th) + 1) if cur_th in th_opts else 0
    th_sel = st.selectbox("Thương hiệu", ["-- Giữ nguyên --"] + th_opts,
                           index=th_idx, key=f"hh_sua_th_{ma}_{cnt}")
    new_th = "" if th_sel == "-- Giữ nguyên --" else th_sel
    new_bh = st.text_input("Bảo hành", value=str(row_m.get("bao_hanh", "") or ""),
                            key=f"hh_sua_bh_{ma}_{cnt}")

    if st.button("💾 Lưu", type="primary", use_container_width=True,
                 key=f"hh_sua_btn_{ma}_{cnt}"):
        try:
            payload = {
                "ten_hang": new_ten.strip(),
                "ma_vach":  new_vach.strip() or None,
                "gia_ban":  int(new_gb),
                "bao_hanh": new_bh.strip() or None,
                "loai_sp":  new_loai_sp,
            }
            if new_loai: payload["loai_hang"]   = new_loai
            if new_th:   payload["thuong_hieu"] = new_th
            supabase.table("hang_hoa").update(payload).eq("ma_hang", ma).execute()
            st.cache_data.clear()
            log_action("HH_EDIT", f"ma={ma}")
            st.success("✓ Đã cập nhật.")
            st.session_state[f"hh_sua_cnt_{ma}"] = cnt + 1
            st.rerun()
        except Exception as e:
            st.error(f"Lỗi: {e}")


def _render_an_hang_hoa(ma: str, ten: str):
    st.caption("Ẩn khỏi danh sách tìm kiếm nhưng giữ lịch sử giao dịch.")
    confirm_key = f"hh_an_confirm_{ma}"
    if not st.session_state.get(confirm_key):
        if st.button(f"🚫 Ẩn {ma}", type="secondary", use_container_width=True,
                     key=f"hh_an_btn_{ma}"):
            st.session_state[confirm_key] = True
            st.rerun()
    else:
        st.warning(f"Ẩn **{ma} — {ten}**?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✓ Xác nhận", type="primary", use_container_width=True,
                         key=f"hh_an_ok_{ma}"):
                try:
                    supabase.table("hang_hoa").update({"active": False}) \
                        .eq("ma_hang", ma).execute()
                    st.cache_data.clear()
                    log_action("HH_HIDE", f"ma={ma} ten={ten}")
                    st.session_state.pop(confirm_key, None)
                    st.session_state.pop("hh_ma_chon", None)
                    st.success(f"✓ Đã ẩn {ma}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")
        with c2:
            if st.button("Hủy", use_container_width=True, key=f"hh_an_cancel_{ma}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# BARCODE LABEL PRINT (GIỮ NGUYÊN — Phase 2 + script-escape fix)
# ═══════════════════════════════════════════════════════════════════════

@st.dialog("🏷️ In tem mã vạch", width="large")
def _dlg_in_tem_hh():
    items = st.session_state.get("_hh_in_tem_items", [])
    if not items:
        st.warning("Chưa chọn sản phẩm nào.")
        return
    _render_dialog_in_tem(items, dialog_key="hh")


def _render_dialog_in_tem(items: list[dict], dialog_key: str):
    """Shared dialog cho cả hang_hoa và nhap_hang."""
    from utils.barcode_label import build_label_html, SYMBOLOGY_OPTIONS, get_barcode_value

    symb_key = f"_intem_{dialog_key}_symb"
    symb = st.selectbox(
        "Loại mã vạch",
        options=list(SYMBOLOGY_OPTIONS.keys()),
        format_func=lambda k: SYMBOLOGY_OPTIONS[k],
        index=0,
        key=symb_key,
    )

    st.caption(f"Tổng {len(items)} SP đã chọn. Chỉnh SL tem cho từng SP:")
    qty_key = f"_intem_{dialog_key}_qty"
    if qty_key not in st.session_state:
        st.session_state[qty_key] = {}
    for it in items:
        if it["ma_hang"] not in st.session_state[qty_key]:
            st.session_state[qty_key][it["ma_hang"]] = int(it.get("qty", 1) or 1)

    no_code = [it for it in items if not get_barcode_value(it)]
    if no_code:
        st.error(f"❌ {len(no_code)} SP không có Mã vạch lẫn Mã hàng — sẽ bị bỏ qua: " +
                 ", ".join((it.get("ten_hang", "?") or "?")[:25] for it in no_code[:5]))

    rows = []
    for it in items:
        mh = it["ma_hang"]
        rows.append({
            "Mã hàng":  mh,
            "Tên":      (it.get("ten_hang") or "")[:40],
            "Giá":      int(it.get("gia_ban") or 0),
            "Mã vạch":  it.get("ma_vach") or "(dùng mã hàng)",
            "SL tem":   st.session_state[qty_key].get(mh, 1),
        })
    df_q = pd.DataFrame(rows)
    edited = st.data_editor(
        df_q,
        column_config={
            "SL tem": st.column_config.NumberColumn(min_value=0, max_value=999, step=1),
            "Giá":    st.column_config.NumberColumn(format="%d"),
        },
        disabled=["Mã hàng", "Tên", "Giá", "Mã vạch"],
        hide_index=True,
        key=f"_intem_{dialog_key}_editor",
        use_container_width=True,
    )
    for _, r in edited.iterrows():
        st.session_state[qty_key][r["Mã hàng"]] = int(r["SL tem"] or 0)

    total = sum(st.session_state[qty_key].get(it["ma_hang"], 0) for it in items)
    st.info(f"📋 Tổng số tem sẽ in: **{total}**")
    if total > 500:
        st.warning("⚠️ Số tem lớn, browser có thể chậm khi render.")

    if st.button("📂 Mở trang in", type="primary",
                 disabled=(total == 0), key=f"_intem_{dialog_key}_go"):
        payload_items = [
            {**it, "qty": st.session_state[qty_key].get(it["ma_hang"], 0)}
            for it in items
            if st.session_state[qty_key].get(it["ma_hang"], 0) > 0
        ]
        html_content = build_label_html(payload_items, symbology=symb)
        _trigger_print_window(html_content)


def _trigger_print_window(html_content: str):
    """Mở tab mới qua Blob URL, render HTML tem.

    Escape "</" → "<\\/" sau json.dumps để </script> trong payload không
    đóng wrapper script sớm.
    """
    import streamlit.components.v1 as components
    import json
    safe = json.dumps(html_content).replace("</", "<\\/")
    components.html(f"""
        <script>
        (function() {{
          const html = {safe};
          let url = null;
          try {{
            const blob = new Blob([html], {{type: 'text/html;charset=utf-8'}});
            url = URL.createObjectURL(blob);
          }} catch (e) {{
            document.body.innerHTML = '<div style="color:red;padding:10px;font-family:sans-serif">'
              + '⚠️ Lỗi tạo blob: ' + e.message + '</div>';
            return;
          }}
          const w = window.open(url, '_blank');
          if (!w) {{
            URL.revokeObjectURL(url);
            document.body.innerHTML = '<div style="color:red;padding:10px;font-family:sans-serif">'
              + '⚠️ Trình duyệt chặn popup. Cho phép popup cho trang này rồi thử lại.'
              + '</div>';
            return;
          }}
          setTimeout(function() {{ URL.revokeObjectURL(url); }}, 60000);
        }})();
        </script>
        <div style="color:#4caf50;font-family:sans-serif;padding:6px">
          ✅ Đã mở tab in. Kiểm tra tab mới.
        </div>
    """, height=40)

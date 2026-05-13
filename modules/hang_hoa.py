"""
modules/hang_hoa.py
─────────────────────────────────────────────────────────────────────────────
Module Hàng hóa — Redesign (Phương án B · Bold, header sáng)

Drop-in replacement. Giữ nguyên toàn bộ logic phân quyền, call supabase,
session_state keys cũ. Đồng thời preserve tính năng **In tem mã vạch**
(multi-row select trên bảng + dialog + Blob URL print) đã merge ở Phase 2.

UI/UX changes:
  1. Header sáng 1 dòng: tiêu đề + tổng SKU + chip Chi nhánh + Tải lại + Thêm.
  2. **KPI strip 4 ô** (trong khung có background): Tổng SKU · Đang bán ·
     Sắp hết (≤10) · Hết hàng (=0).
  3. **Khung Tìm kiếm + Bộ lọc** với section title — gộp search bar + filter
     pills + sort dropdown trong 1 container có viền.
  4. **Sticky banner mảnh** cho sản phẩm đang chọn: icon + name + code chips
     + mini bar 3 chi nhánh + quick-action popovers (Sửa / Tồn / Sử / Ẩn / ✕).
     Chỉ hiện khi chọn ĐÚNG 1 dòng.
  5. **Khung Bảng + nút In tem** — bảng dùng multi-row select, dưới bảng
     có nút "🏷️ In tem mã vạch (N)" enable khi chọn ≥ 1 dòng. Giữ trải
     nghiệm in tem hàng loạt cũ.
  6. Admin actions mở qua `st.popover` thay vì 3 expander xếp dọc.

Yêu cầu: Streamlit ≥ 1.32 (st.popover, dataframe selection, ProgressColumn,
container border).
"""

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
# DESIGN TOKENS
# ═══════════════════════════════════════════════════════════════════════
T = {
    "ink":      "#1c1f2a",
    "ink2":     "#4a4f5c",
    "muted":    "#7a8090",
    "border":   "#e7e8ec",
    "subtle":   "#f5f5f7",
    "surface":  "#ffffff",
    "accent":   "#cf3b2c",
    "accentBg": "#fdecea",
    "good":     "#1f8b4a",
    "goodBg":   "#e8f5ee",
    "warn":     "#c98a14",
    "warnBg":   "#fdf3e0",
    "danger":   "#cf3b2c",
    "dangerBg": "#fdecea",
    "sectionBg": "#fbfbfd",
}


def _stock_meta(n: int):
    """Trả về (fg, bg, label) cho mức tồn kho."""
    if n <= 0:   return (T["danger"], T["dangerBg"], "Hết")
    if n <= 10:  return (T["warn"],   T["warnBg"],   "Sắp hết")
    return            (T["good"],   T["goodBg"],   "Đủ")


def _inject_css_once():
    if st.session_state.get("_hh_css_v3"):
        return
    st.session_state["_hh_css_v3"] = True
    st.markdown(f"""
    <style>
      .block-container {{ padding-top: 1rem; padding-bottom: 1rem; }}

      /* Section containers (st.container border=True) — thêm background */
      [data-testid="stVerticalBlockBorderWrapper"] {{
        background: {T['sectionBg']};
        border-radius: 12px;
        border: 1px solid {T['border']} !important;
      }}
      /* Popover content giữ background trắng */
      [data-baseweb="popover"] [data-testid="stVerticalBlockBorderWrapper"] {{
        background: {T['surface']};
      }}

      /* Section title */
      .hh-section-title {{
        font-size: 10px; font-weight: 600;
        color: {T['muted']}; text-transform: uppercase;
        letter-spacing: .08em;
        margin: -2px 0 8px 0;
      }}

      /* Chip / pill */
      .hh-chip {{
        display: inline-flex; align-items: center; gap: 6px;
        height: 26px; padding: 0 11px; border-radius: 999px;
        font-size: 12px; font-weight: 500;
        background: {T['surface']}; color: {T['ink2']};
        border: 1px solid {T['border']};
      }}
      .hh-chip.active {{
        background: {T['accentBg']}; color: {T['accent']};
        border-color: {T['accentBg']};
      }}
      .hh-chip .count {{
        font-size: 11px; color: inherit; opacity: .65; margin-left: 2px;
      }}

      /* Code chip */
      .hh-code {{
        font-family: ui-monospace, "JetBrains Mono", monospace;
        font-size: 11px; padding: 2px 7px; border-radius: 5px;
        background: {T['subtle']}; border: 1px solid {T['border']};
        color: {T['ink']};
      }}

      /* KPI tile */
      .hh-kpi {{
        display: flex; flex-direction: column; gap: 2px;
        padding: 10px 18px;
        background: {T['surface']};
        border: 1px solid {T['border']};
        border-radius: 10px;
      }}
      .hh-kpi .l {{ font-size: 11px; color: {T['muted']};
        text-transform: uppercase; letter-spacing: .06em; font-weight: 500; }}
      .hh-kpi .v {{ font-size: 22px; font-weight: 600; letter-spacing: -.02em;
        font-variant-numeric: tabular-nums; }}
      .hh-kpi .s {{ font-size: 11px; color: {T['muted']}; margin-left: 4px; }}

      /* Selected product banner */
      .hh-banner {{
        background: linear-gradient(90deg, {T['accentBg']} 0%, {T['surface']} 65%);
        border: 1px solid {T['border']};
        border-left: 3px solid {T['accent']};
        border-radius: 10px;
        padding: 12px 16px;
      }}
      .hh-banner .name {{ font-size: 15px; font-weight: 600; color: {T['ink']}; }}
      .hh-banner .meta {{ font-size: 11px; color: {T['muted']}; margin-top: 2px; }}

      /* Mini bar in banner */
      .hh-mini {{
        display: flex; flex-direction: column; gap: 4px;
        padding: 6px 10px; border-radius: 8px;
        background: {T['surface']}; border: 1px solid {T['border']};
        min-width: 110px;
      }}
      .hh-mini.active {{ box-shadow: inset 0 0 0 1px {T['accent']}; }}
      .hh-mini .label {{ font-size: 10px; color: {T['muted']};
        text-transform: uppercase; letter-spacing: .04em; font-weight: 500; }}
      .hh-mini .val {{ font-size: 13px; font-weight: 600;
        font-variant-numeric: tabular-nums; }}
      .hh-mini .track {{ height: 4px; background: {T['subtle']};
        border-radius: 2px; overflow: hidden; }}
      .hh-mini .fill {{ height: 100%; border-radius: 2px; }}

      /* Status badge (inline) */
      .hh-badge {{
        display: inline-flex; align-items: center; gap: 4px;
        padding: 2px 8px; border-radius: 999px;
        font-size: 11px; font-weight: 600;
      }}
    </style>
    """, unsafe_allow_html=True)


def _section_title(text: str):
    st.markdown(
        f"<div class='hh-section-title'>{text}</div>",
        unsafe_allow_html=True,
    )


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

        # ── HEADER ──
        view_branches = _render_header(active, accessible, total=len(master))
        if not view_branches:
            st.warning("Chọn ít nhất một chi nhánh.")
            return

        # Re-load với branches đã chọn
        the_kho = load_the_kho(branches_key=tuple(view_branches))
        df = _build_df(master, the_kho)

        # ── KPI STRIP ──
        if not master.empty:
            with st.container(border=True):
                _section_title("Tổng quan")
                _render_kpi(df)

        # ── TÌM KIẾM + BỘ LỌC ──
        with st.container(border=True):
            _section_title("Tìm kiếm & bộ lọc")
            keyword = _render_search(df)
            cha_chon, con_chon, low_only, sort_by = _render_filter_pills(df)

        filtered = _apply_filters(df, keyword, cha_chon, con_chon, low_only, sort_by)

        if filtered.empty:
            st.warning("Không tìm thấy hàng hóa phù hợp.")
            return

        # Auto-select khi chỉ còn 1 kết quả
        if len(filtered) == 1:
            st.session_state["hh_ma_chon"] = filtered.iloc[0]["ma_hang"]

        ma_chon = st.session_state.get("hh_ma_chon")
        if ma_chon and ma_chon not in filtered["ma_hang"].values:
            st.session_state.pop("hh_ma_chon", None)
            ma_chon = None

        # ── BANNER (chỉ khi chọn 1 dòng) ──
        if ma_chon:
            _render_selected_banner(filtered, ma_chon, active)

        # ── BẢNG + IN TEM ──
        with st.container(border=True):
            _section_title("Danh sách sản phẩm")
            _render_table(filtered, view_branches)

    except Exception as e:
        st.error(f"Lỗi tải Hàng hóa: {e}")


# ═══════════════════════════════════════════════════════════════════════
# HEADER + KPI
# ═══════════════════════════════════════════════════════════════════════
def _render_header(active: str, accessible: list, total: int):
    c1, c2, c3, c4 = st.columns([5, 1.6, 0.5, 1.5])
    with c1:
        st.markdown(
            f"<div style='display:flex;align-items:baseline;gap:12px;padding-top:6px;'>"
            f"<span style='font-size:22px;font-weight:600;letter-spacing:-.015em;"
            f"color:{T['ink']}'>Hàng hóa</span>"
            f"<span style='font-size:12px;color:{T['muted']}'>"
            f"{total:,} SKU</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with c2:
        if is_ke_toan_or_admin() and len(accessible) > 1:
            with st.popover(f"● {CN_SHORT.get(active, active)}",
                            use_container_width=True):
                view = st.multiselect(
                    "Chi nhánh xem:", accessible,
                    default=st.session_state.get("hh_cn", [active]),
                    key="hh_cn", label_visibility="collapsed",
                )
                if not view:
                    view = [active]
        else:
            st.markdown(
                f"<div style='text-align:right;padding-top:8px;'>"
                f"<span class='hh-chip active'>● {CN_SHORT.get(active, active)}</span>"
                f"</div>", unsafe_allow_html=True,
            )
            return [active]
    with c3:
        if st.button("↻", key="hh_reload", help="Tải lại"):
            st.cache_data.clear()
            st.rerun()
    with c4:
        if is_admin():
            with st.popover("➕ Thêm hàng hóa", use_container_width=True):
                _render_them_moi()
    return st.session_state.get("hh_cn", [active])


def _render_kpi(df: pd.DataFrame):
    total = len(df)
    selling = int((df["Ton_cuoi"] > 0).sum())
    low = int(((df["Ton_cuoi"] > 0) & (df["Ton_cuoi"] <= 10)).sum())
    out = int((df["Ton_cuoi"] <= 0).sum())

    c1, c2, c3, c4 = st.columns(4)
    for col, label, val, sub, color in [
        (c1, "Tổng SKU", f"{total:,}", "trong kho", T["ink"]),
        (c2, "Đang bán", f"{selling:,}",
         f"{(selling/total*100):.0f}%" if total else "—", T["ink"]),
        (c3, "Sắp hết",  f"{low:,}",   "≤ 10 cái", T["warn"]),
        (c4, "Hết hàng", f"{out:,}",   "cần nhập", T["danger"]),
    ]:
        with col:
            st.markdown(
                f"<div class='hh-kpi'>"
                f"<div class='l'>{label}</div>"
                f"<div style='display:flex;align-items:baseline;'>"
                f"<span class='v' style='color:{color}'>{val}</span>"
                f"<span class='s'>· {sub}</span>"
                f"</div></div>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════
# SEARCH + FILTERS
# ═══════════════════════════════════════════════════════════════════════
def _render_search(df: pd.DataFrame) -> str:
    cs, cb = st.columns([10, 1])
    with cs:
        _sc = st.session_state.get("hh_search_cnt", 0)
        keyword = st.text_input(
            "", key=f"hh_search_{_sc}",
            placeholder="🔍  Tìm theo tên, mã hàng hoặc mã vạch…",
            label_visibility="collapsed",
        )
    with cb:
        st.button("📷", key="hh_scan", help="Quét mã vạch",
                  use_container_width=True)
    return keyword


def _render_filter_pills(df: pd.DataFrame):
    """Hàng pills: nhóm phổ biến + filter popover + sort."""
    cha_list = sorted([c for c in df["_cha"].dropna().unique() if c])
    top_groups = (df.groupby("_cha").size()
                  .sort_values(ascending=False).head(4).index.tolist())

    cl, cr = st.columns([7, 3])
    with cl:
        with st.popover("⊞ Bộ lọc nâng cao", use_container_width=False):
            cha_chon = st.selectbox(
                "Nhóm hàng:", ["Tất cả"] + cha_list, key="hh_cha",
            )
            if cha_chon != "Tất cả":
                con_list = sorted([c for c in
                    df[df["_cha"] == cha_chon]["_con"].dropna().unique() if c])
                _ = st.selectbox(
                    "Nhóm con:", ["Tất cả"] + con_list, key="hh_con",
                )
            st.divider()
            _ = st.checkbox("Chỉ hiện tồn ≤ 10", key="hh_low_only")

        cha_chon = st.session_state.get("hh_cha", "Tất cả")
        con_chon = st.session_state.get("hh_con", "Tất cả")
        low_only = st.session_state.get("hh_low_only", False)

        # Pills nhóm phổ biến (read-only chips)
        if top_groups:
            chips = ["<div style='display:flex;gap:6px;align-items:center;margin-top:8px;flex-wrap:wrap;'>"]
            for g in top_groups:
                n = int((df["_cha"] == g).sum())
                cls = "hh-chip active" if g == cha_chon else "hh-chip"
                chips.append(
                    f"<span class='{cls}'>{g}<span class='count'>{n}</span></span>"
                )
            if low_only:
                chips.append(f"<span class='hh-chip active'>⚠ Tồn ≤ 10</span>")
            chips.append("</div>")
            st.markdown("".join(chips), unsafe_allow_html=True)

    with cr:
        sort_by = st.selectbox(
            "Sắp xếp:",
            ["Tồn: cao → thấp", "Tồn: thấp → cao",
             "Tên: A → Z", "Giá: cao → thấp", "Giá: thấp → cao"],
            key="hh_sort", label_visibility="collapsed",
        )

    return (st.session_state.get("hh_cha", "Tất cả"),
            st.session_state.get("hh_con", "Tất cả"),
            st.session_state.get("hh_low_only", False),
            sort_by)


def _apply_filters(df, keyword, cha_chon, con_chon, low_only, sort_by):
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
    if low_only:
        out = out[out["Ton_cuoi"] <= 10]

    sort_map = {
        "Tồn: cao → thấp": ("Ton_cuoi", False),
        "Tồn: thấp → cao": ("Ton_cuoi", True),
        "Tên: A → Z":       ("ten_hang", True),
        "Giá: cao → thấp":  ("gia_ban",  False),
        "Giá: thấp → cao":  ("gia_ban",  True),
    }
    col, asc = sort_map.get(sort_by, ("Ton_cuoi", False))
    if col in out.columns:
        out = out.sort_values(col, ascending=asc)
    return out.reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════
# DATA BUILD
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


# ═══════════════════════════════════════════════════════════════════════
# SELECTED PRODUCT BANNER (slim, horizontal)
# ═══════════════════════════════════════════════════════════════════════
def _render_selected_banner(filtered: pd.DataFrame, ma_chon: str, active: str):
    row_m = filtered[filtered["ma_hang"] == ma_chon].iloc[0]

    try:
        all_kho = load_the_kho(branches_key=tuple(ALL_BRANCHES))
        branch_tons = {cn: 0 for cn in ALL_BRANCHES}
        branch_kho_ids = {cn: None for cn in ALL_BRANCHES}
        if not all_kho.empty:
            rk = all_kho[all_kho["Mã hàng"].astype(str).str.strip() == str(ma_chon).strip()]
            for _, kr in rk.iterrows():
                cn = kr.get("Chi nhánh", "")
                if cn in branch_tons:
                    branch_tons[cn] += int(kr.get("Tồn cuối kì", 0) or 0)
                    branch_kho_ids[cn] = kr.get("id")
    except Exception:
        branch_tons = {cn: 0 for cn in ALL_BRANCHES}
        branch_kho_ids = {cn: None for cn in ALL_BRANCHES}

    max_ton = max(branch_tons.values()) or 1
    gb = int(row_m.get("gia_ban", 0) or 0)
    th_str = str(row_m.get("thuong_hieu", "") or "")
    nhom = (f"{row_m.get('_cha','')} › {row_m['_con']}"
            if row_m.get("_con", "") else row_m.get("_cha", ""))

    with st.container():
        st.markdown("<div class='hh-banner'>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([4, 5, 3])

        with c1:
            vach = str(row_m.get("ma_vach", "") or "")
            vach_html = (f"<span class='hh-code' style='border-style:dashed;background:transparent;'>{vach}</span>"
                         if vach and vach != row_m["ma_hang"] else "")
            st.markdown(
                f"<div style='padding-top:4px;'>"
                f"<div style='display:flex;align-items:center;gap:8px;flex-wrap:wrap;'>"
                f"<span class='name'>{row_m['ten_hang']}</span>"
                f"<span class='hh-code'>{row_m['ma_hang']}</span>"
                f"{vach_html}"
                f"</div>"
                f"<div class='meta'>"
                f"{nhom}{(' · ' + th_str) if th_str else ''}"
                f" · Giá bán <b style='color:{T['ink']};font-variant-numeric:tabular-nums;'>"
                f"{(f'{gb:,} đ' if gb else '—')}</b>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

        with c2:
            mini_html = ["<div style='display:flex;gap:8px;'>"]
            for cn in ALL_BRANCHES:
                n = branch_tons[cn]
                pct = max(4.0, (n / max_ton) * 100) if max_ton else 0
                fg, _bg, _ = _stock_meta(n)
                is_act = cn == active
                pin = "📍 " if is_act else ""
                mini_html.append(
                    f"<div class='hh-mini{' active' if is_act else ''}'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:baseline;'>"
                    f"<span class='label'>{pin}{CN_SHORT.get(cn, cn)}</span>"
                    f"<span class='val' style='color:{fg};'>{n:,}</span>"
                    f"</div>"
                    f"<div class='track'><div class='fill' style='width:{pct:.1f}%;background:{fg};'></div></div>"
                    f"</div>"
                )
            mini_html.append("</div>")
            st.markdown("".join(mini_html), unsafe_allow_html=True)

        with c3:
            ac1, ac2, ac3, ac4, ac5 = st.columns(5)
            with ac1:
                with st.popover("✏️", use_container_width=True, help="Sửa thông tin"):
                    if is_admin(): _render_sua_hang_hoa(row_m)
                    else:          st.info("Cần quyền admin.")
            with ac2:
                with st.popover("📦", use_container_width=True, help="Chỉnh tồn kho"):
                    if is_admin():
                        _render_chinh_ton(ma_chon, row_m, branch_tons, branch_kho_ids)
                    else:
                        st.info("Cần quyền admin.")
            with ac3:
                with st.popover("⏱", use_container_width=True, help="Lịch sử giao dịch"):
                    st.caption("Lịch sử nhập / bán / chuyển kho")
                    st.info("(Truy vấn hoa_don + nhap_hang + chuyen_hang theo ma_hang)")
            with ac4:
                with st.popover("🚫", use_container_width=True, help="Ẩn hàng hóa"):
                    if is_admin():
                        _render_an_hang_hoa(ma_chon, str(row_m.get("ten_hang", "")))
                    else:
                        st.info("Cần quyền admin.")
            with ac5:
                if st.button("✕", key="hh_close", use_container_width=True, help="Bỏ chọn"):
                    st.session_state.pop("hh_ma_chon", None)
                    st.session_state["hh_search_cnt"] = (
                        st.session_state.get("hh_search_cnt", 0) + 1)
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# TABLE + IN TEM
# ═══════════════════════════════════════════════════════════════════════
def _render_table(filtered: pd.DataFrame, view_branches: list):
    total = len(filtered)

    ma_v = filtered.get("ma_vach", filtered["ma_hang"]).fillna("")
    disp = pd.DataFrame({
        "Sản phẩm":  filtered["ten_hang"].astype(str),
        "Nhóm":      filtered["_cha"].astype(str),
        "Mã hàng":   filtered["ma_hang"].astype(str),
        "Mã vạch":   ma_v.astype(str),
        "Giá bán":   filtered["gia_ban"].astype(int),
    })

    # Tồn theo từng chi nhánh
    try:
        all_kho = load_the_kho(branches_key=tuple(ALL_BRANCHES))
        per_branch = {cn: {} for cn in ALL_BRANCHES}
        if not all_kho.empty:
            for cn in ALL_BRANCHES:
                sub = all_kho[all_kho["Chi nhánh"] == cn]
                per_branch[cn] = (sub.groupby("Mã hàng")["Tồn cuối kì"]
                                  .sum().astype(int).to_dict())
    except Exception:
        per_branch = {cn: {} for cn in ALL_BRANCHES}

    for cn in ALL_BRANCHES:
        short = CN_SHORT.get(cn, cn)
        disp[short] = filtered["ma_hang"].map(per_branch[cn]).fillna(0).astype(int)
    disp["Tổng"] = sum(disp[CN_SHORT.get(cn, cn)] for cn in ALL_BRANCHES)

    active_short = CN_SHORT.get(view_branches[0], view_branches[0])
    def _status(n):
        if n <= 0:  return "🔴 Hết"
        if n <= 10: return "🟡 Sắp hết"
        return       "🟢 Đủ"
    disp["Trạng thái"] = disp[active_short].apply(_status)

    hint = " — lọc thêm để thu hẹp" if total > 100 else ""
    st.caption(f"**{total:,}** sản phẩm · {', '.join(view_branches)}{hint}")

    col_cfg = {
        "Sản phẩm": st.column_config.TextColumn("Sản phẩm", width="large"),
        "Nhóm":     st.column_config.TextColumn("Nhóm",     width="small"),
        "Mã hàng":  st.column_config.TextColumn("Mã hàng",  width="small"),
        "Mã vạch":  st.column_config.TextColumn("Mã vạch",  width="small"),
        "Giá bán":  st.column_config.NumberColumn(
            "Giá bán", format="%d ₫", width="small"),
        "Tổng":     st.column_config.NumberColumn(
            "Tổng (3 CN)", format="%d", width="small"),
        "Trạng thái": st.column_config.TextColumn(
            "Trạng thái", width="small"),
    }
    for cn in ALL_BRANCHES:
        short = CN_SHORT.get(cn, cn)
        max_v = int(max(disp[short].max(), 1))
        col_cfg[short] = st.column_config.ProgressColumn(
            short, format="%d", min_value=0, max_value=max_v, width="small",
        )

    event = st.dataframe(
        disp,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key="hh_table_v3",
        column_config=col_cfg,
        height=min(560, 42 + len(disp) * 35 + 4),
    )

    sel = event.selection.rows if event.selection else []
    pre_ma = st.session_state.get("hh_ma_chon")

    # Banner chỉ hiện khi chọn ĐÚNG 1 dòng. Multi-select ẩn banner.
    if len(sel) == 1 and sel[0] < len(disp):
        new_ma = disp.iloc[sel[0]]["Mã hàng"]
        if new_ma != pre_ma:
            st.session_state["hh_ma_chon"] = new_ma
            st.rerun()
    elif len(sel) >= 2 and pre_ma:
        st.session_state.pop("hh_ma_chon", None)
        st.rerun()

    n_sel = len(sel)
    if not pre_ma and n_sel == 0:
        st.caption("↑ Chọn 1 dòng để xem chi tiết, hoặc chọn nhiều dòng để in tem hàng loạt")

    # ── NÚT IN TEM MÃ VẠCH ──
    col_btn1, _col_btn2 = st.columns([2, 4])
    with col_btn1:
        if st.button(
            f"🏷️ In tem mã vạch{f' ({n_sel})' if n_sel else ''}",
            disabled=(n_sel == 0),
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


# ═══════════════════════════════════════════════════════════════════════
# ADMIN POPOVERS — Sửa info / Chỉnh tồn / Thêm mới / Ẩn
# ═══════════════════════════════════════════════════════════════════════
def _render_chinh_ton(ma_chon, row_m, branch_tons, branch_kho_ids):
    st.caption("Điều chỉnh trực tiếp tồn kho từng chi nhánh.")
    adj = {}
    for cn in ALL_BRANCHES:
        adj[cn] = st.number_input(
            CN_SHORT.get(cn, cn), min_value=0, step=1,
            value=branch_tons[cn], key=f"adj_v3_{ma_chon}_{cn}",
        )
    if st.button("💾 Lưu", type="primary", use_container_width=True,
                 key=f"save_ton_v3_{ma_chon}"):
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
# BARCODE LABEL PRINT (Phase 2 — preserve từ main)
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

    Escape "</" → "<\\/" trên JSON dump vì payload có chứa </script> từ
    inner bwip-js script — HTML tokenizer sẽ đóng wrapper sớm nếu không
    escape.
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

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
from utils.hh_style import (
    inject_hang_hoa_css, hh_html, render_caption, render_empty_rail,
    render_detail_card_open, render_stock_tiles, render_detail_card_close,
)

from utils.helpers import _normalize


def module_hang_hoa():
    inject_hang_hoa_css()
    try:
        active     = get_active_branch()
        accessible = get_accessible_branches()

        # ── Load master first to drive popover filter list ──
        master = load_hang_hoa()
        has_master = not master.empty
        cha_list_for_filter = sorted([c for c in master["loai_hang"].dropna().unique() if c]) \
            if has_master and "loai_hang" in master.columns else []

        # ══════ TOOLBAR (chi nhánh · search · lọc · thêm) ══════
        tb_cols = st.columns([2, 5, 1, 1])

        # 1. Branch multiselect
        with tb_cols[0]:
            if is_ke_toan_or_admin() and len(accessible) > 1:
                view_branches = st.multiselect(
                    "Chi nhánh:", accessible, default=[active],
                    key="hh_cn", label_visibility="collapsed")
            else:
                view_branches = [active]

        # 2. Search input
        with tb_cols[1]:
            _sc = st.session_state.get("hh_search_cnt", 0)
            keyword = st.text_input(
                "", key=f"hh_search_{_sc}",
                placeholder="Tìm mã hàng, mã vạch hoặc tên…",
                label_visibility="collapsed")

        # 3. Popover Lọc
        with tb_cols[2]:
            with st.popover("⊟ Lọc", use_container_width=True):
                cha_chon = st.selectbox(
                    "Nhóm hàng:", ["Tất cả"] + cha_list_for_filter,
                    key="hh_cha", label_visibility="collapsed")
                if cha_chon != "Tất cả" and has_master and "thuong_hieu" in master.columns:
                    con_list = sorted([c for c in
                        master[master["loai_hang"] == cha_chon]["thuong_hieu"]
                        .dropna().unique() if c])
                    con_chon = st.selectbox(
                        "Nhóm con:", ["Tất cả"] + con_list,
                        key="hh_con", label_visibility="collapsed")
                else:
                    con_chon = "Tất cả"

        # 4. Add button (admin only)
        with tb_cols[3]:
            if is_admin():
                if st.button("➕ Thêm hàng", type="primary",
                             use_container_width=True, key="hh_add_open"):
                    _dlg_them_hang()

        # Branch validation
        if not view_branches:
            st.warning("Chọn ít nhất một chi nhánh.")
            return

        # ── Load the_kho for selected branches ──
        the_kho = load_the_kho(branches_key=tuple(view_branches))

        if not has_master and the_kho.empty:
            if is_admin():
                st.info("Chưa có dữ liệu hàng hóa.")
                _render_them_moi()
            else:
                st.info("Chưa có dữ liệu. Vào ⚙️ Quản trị → Upload để tải lên.")
            return

        # ── Build df ──
        if has_master and not the_kho.empty:
            kho_agg = the_kho.groupby("Mã hàng", as_index=False).agg(
                Ton_cuoi=("Tồn cuối kì","sum"))
            df = master.merge(kho_agg, left_on="ma_hang", right_on="Mã hàng", how="left")
            df["Ton_cuoi"] = df["Ton_cuoi"].fillna(0).astype(int)
        elif has_master:
            df = master.copy(); df["Ton_cuoi"] = 0
        else:
            df = the_kho.groupby(["Mã hàng","Tên hàng"], as_index=False).agg(
                Ton_cuoi=("Tồn cuối kì","sum"))
            df["ma_hang"]=""; df["ma_vach"]=""; df["ten_hang"]=df["Tên hàng"]
            df["nhom_hang"]=""; df["thuong_hieu"]=""; df["loai_hang"]=""; df["gia_ban"]=0; df["bao_hanh"]=""
            df["ma_hang"] = df["Mã hàng"]; df["ma_vach"] = df["Mã hàng"]

        if "loai_hang" in df.columns and df["loai_hang"].fillna("").str.strip().any():
            df["_cha"] = df["loai_hang"].fillna("").str.strip()
            df["_con"] = df.get("thuong_hieu", pd.Series([""] * len(df))).fillna("").str.strip()
        else:
            nhom_col = df["nhom_hang"].fillna("") if "nhom_hang" in df.columns \
                       else pd.Series([""] * len(df))
            split = nhom_col.str.split(">>", n=1, expand=True)
            df["_cha"] = split[0].str.strip()
            df["_con"] = (split[1].str.strip() if 1 in split.columns else "").fillna("")

        df["_norm_ma"]   = df["ma_hang"].apply(_normalize)
        df["_norm_vach"] = df.get("ma_vach", df["ma_hang"]).apply(
            lambda x: _normalize(x) if pd.notna(x) else "")
        df["_norm_ten"]  = df["ten_hang"].apply(_normalize)

        # ══════ APPLY SEARCH + FILTERS ══════
        filtered = df.copy()
        kw = _normalize(keyword) if keyword.strip() else ""
        if kw:
            filtered = filtered[
                filtered["_norm_ma"].str.contains(kw, na=False) |
                filtered["_norm_vach"].str.contains(kw, na=False) |
                filtered["_norm_ten"].str.contains(kw, na=False)]
        if cha_chon != "Tất cả":
            filtered = filtered[filtered["_cha"] == cha_chon]
        if con_chon != "Tất cả":
            filtered = filtered[filtered["_con"] == con_chon]

        filtered = filtered.sort_values("Ton_cuoi", ascending=False).reset_index(drop=True)

        if filtered.empty:
            render_caption(total=0, branches=view_branches,
                           filter_label=cha_chon if cha_chon != "Tất cả" else None)
            col_table, col_rail = st.columns([6, 4], gap="medium")
            with col_table:
                st.warning("Không tìm thấy hàng hóa phù hợp.")
            with col_rail:
                render_empty_rail()
            return

        if len(filtered) == 1:
            st.session_state["hh_ma_chon"] = filtered.iloc[0]["ma_hang"]

        ma_chon = st.session_state.get("hh_ma_chon")
        if ma_chon and ma_chon not in filtered["ma_hang"].values:
            ma_chon = None; st.session_state.pop("hh_ma_chon", None)

        # ══════ CAPTION ══════
        render_caption(
            total=len(filtered), branches=view_branches,
            filter_label=cha_chon if cha_chon != "Tất cả" else None)

        # ══════ MASTER-DETAIL GRID (60/40) ══════
        # Build display DataFrame
        disp_cols = {"ten_hang":"Tên hàng","ma_hang":"Mã hàng","Ton_cuoi":"Tồn kho"}
        if "ma_vach" in filtered.columns:
            disp_cols = {"ten_hang":"Tên hàng","ma_hang":"Mã hàng",
                         "ma_vach":"Mã vạch","Ton_cuoi":"Tồn kho"}
        avail = {k:v for k,v in disp_cols.items() if k in filtered.columns}
        disp  = filtered[list(avail.keys())].rename(columns=avail).copy()
        disp["Tồn kho"] = disp["Tồn kho"].astype(int)

        ROW_H  = 35
        HEADER = 42
        N_ROWS = 10
        tbl_h  = HEADER + N_ROWS * ROW_H

        col_table, col_rail = st.columns([6, 4], gap="medium")

        with col_table:
            event = st.dataframe(
                disp,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="multi-row",
                key="hh_table",
                column_config={
                    "Tên hàng": st.column_config.TextColumn("Tên hàng", width="medium"),
                    "Mã hàng":  st.column_config.TextColumn("Mã hàng",  width="medium"),
                    "Mã vạch":  st.column_config.TextColumn("Mã vạch",  width="medium"),
                    "Tồn kho":  st.column_config.NumberColumn("Tồn", width="small", format="%d"),
                },
                height=tbl_h,
            )
            sel = event.selection.rows if event.selection else []

            hh_html(
                '<div class="hh-hint-row">'
                '↑ Chọn 1 dòng để xem chi tiết · chọn nhiều dòng để in tem hàng loạt'
                '</div>'
            )

            # Update hh_ma_chon from selection
            if len(sel) == 1 and sel[0] < len(disp):
                new_ma = disp.iloc[sel[0]]["Mã hàng"]
                if new_ma != ma_chon:
                    st.session_state["hh_ma_chon"] = new_ma
                    st.rerun()
            elif len(sel) >= 2 and ma_chon:
                st.session_state.pop("hh_ma_chon", None)
                st.rerun()

        with col_rail:
            if len(sel) >= 2:
                _render_rail_multi(sel, disp, filtered)
            elif ma_chon:
                _render_rail_single(filtered, ma_chon, active)
            else:
                render_empty_rail()

    except Exception as e:
        st.error(f"Lỗi tải Hàng hóa: {e}")


# ════════════════════════════════════════════════════════
# RAIL RENDERERS — Right column (master-detail)
# ════════════════════════════════════════════════════════

def _render_rail_single(filtered, ma_chon, active):
    """Detail card for a single selected item."""
    row_m = filtered[filtered["ma_hang"] == ma_chon].iloc[0]

    # Close button at top-right of rail (visually adjacent to card header)
    _, close_col = st.columns([5, 1])
    with close_col:
        if st.button("✕", key=f"hh_close_detail_{ma_chon}",
                     help="Đóng chi tiết", use_container_width=True):
            st.session_state.pop("hh_ma_chon", None)
            st.session_state["hh_search_cnt"] = st.session_state.get("hh_search_cnt", 0) + 1
            st.rerun()

    cha = str(row_m.get("_cha", "") or "")
    con = str(row_m.get("_con", "") or "")
    breadcrumb = (f"{cha} › {con}" if con else cha).upper()

    render_detail_card_open(
        ten_hang=str(row_m.get("ten_hang", "")),
        breadcrumb=breadcrumb,
        ma_hang=str(row_m.get("ma_hang", "")),
        ma_vach=str(row_m.get("ma_vach", "") or ""),
        thuong_hieu=str(row_m.get("thuong_hieu", "") or ""),
        loai_sp=str(row_m.get("loai_sp", "") or "Hàng hóa"),
        bao_hanh=str(row_m.get("bao_hanh", "") or ""),
        gia_ban=int(row_m.get("gia_ban", 0) or 0),
    )

    # Stock tiles (3 branches)
    branch_tons = {cn: 0 for cn in ALL_BRANCHES}
    branch_kho_ids = {cn: None for cn in ALL_BRANCHES}
    try:
        all_kho = load_the_kho(branches_key=tuple(ALL_BRANCHES))
        if not all_kho.empty:
            rows_kho = all_kho[
                all_kho["Mã hàng"].astype(str).str.strip() == str(ma_chon).strip()
            ]
            for _, kr in rows_kho.iterrows():
                cn = kr.get("Chi nhánh", "")
                if cn in branch_tons:
                    branch_tons[cn] += int(kr.get("Tồn cuối kì", 0) or 0)
                    branch_kho_ids[cn] = kr.get("id")
    except Exception:
        pass

    render_stock_tiles(
        branches=list(ALL_BRANCHES),
        stocks=branch_tons,
        current=active,
        short=CN_SHORT,
    )

    # ── Admin actions ──
    if is_admin():
        # "Chỉnh tồn kho" expander
        with st.expander("✎ Chỉnh tồn kho", expanded=False):
            st.caption("Điều chỉnh trực tiếp tồn kho tại từng chi nhánh. "
                       "Thay đổi sẽ ghi thẳng vào the_kho.")
            adj_cols = st.columns(3)
            adj_vals = {}
            for idx, cn_name in enumerate(ALL_BRANCHES):
                with adj_cols[idx]:
                    adj_vals[cn_name] = st.number_input(
                        CN_SHORT.get(cn_name, cn_name),
                        min_value=0,
                        value=branch_tons[cn_name],
                        step=1,
                        key=f"adj_ton_{ma_chon}_{cn_name}",
                    )
            if st.button("💾 Lưu tồn kho", type="primary",
                         use_container_width=True, key=f"save_ton_{ma_chon}"):
                try:
                    changed = []
                    for cn_name in ALL_BRANCHES:
                        new_ton = int(adj_vals[cn_name])
                        old_ton = branch_tons[cn_name]
                        if new_ton == old_ton:
                            continue
                        kho_id = branch_kho_ids[cn_name]
                        if kho_id:
                            supabase.table("the_kho").update(
                                {"Tồn cuối kì": new_ton}
                            ).eq("id", kho_id).execute()
                        else:
                            supabase.table("the_kho").insert({
                                "Mã hàng":    str(ma_chon),
                                "Tên hàng":   str(row_m.get("ten_hang", "")),
                                "Chi nhánh":  cn_name,
                                "Tồn cuối kì": new_ton,
                                "Tồn đầu kì":  0,
                            }).execute()
                        changed.append(
                            f"{CN_SHORT.get(cn_name, cn_name)}: "
                            f"{old_ton} → {new_ton}"
                        )
                    if changed:
                        st.cache_data.clear()
                        log_action("KHO_ADJ",
                                   f"ma={ma_chon} " + ", ".join(changed))
                        st.success("✓ Đã cập nhật: " + " · ".join(changed))
                        st.rerun()
                    else:
                        st.info("Không có thay đổi.")
                except Exception as e:
                    st.error(f"Lỗi: {e}")

        # Sửa / Ẩn buttons
        c_edit, c_hide = st.columns([3, 1])
        with c_edit:
            if st.button("✎ Sửa thông tin", use_container_width=True,
                         key=f"hh_open_edit_{ma_chon}"):
                _dlg_sua_hang_hoa(row_m)
        with c_hide:
            if st.button("🚫", help="Ẩn hàng hóa", use_container_width=True,
                         key=f"hh_open_hide_{ma_chon}"):
                st.session_state[f"hh_an_confirm_{ma_chon}"] = True
                st.rerun()

        # Inline hide-confirm UI (only when confirm flag set)
        if st.session_state.get(f"hh_an_confirm_{ma_chon}"):
            _render_an_hang_hoa(str(ma_chon), str(row_m.get("ten_hang", "")))

    # Close card
    render_detail_card_close()

    # ── Print button (1 SP) ──
    if st.button("🏷 In tem mã vạch", type="primary",
                 use_container_width=True, key=f"hh_print_single_{ma_chon}"):
        _ma_vach = "" if pd.isna(row_m.get("ma_vach")) else str(row_m.get("ma_vach")).strip()
        st.session_state["_hh_in_tem_items"] = [{
            "ma_hang":  str(row_m.get("ma_hang", "")),
            "ten_hang": str(row_m.get("ten_hang", "")),
            "gia_ban":  int(row_m.get("gia_ban", 0) or 0),
            "ma_vach":  _ma_vach,
            "qty":      1,
        }]
        st.session_state.pop("_intem_hh_qty", None)
        _dlg_in_tem_hh()


def _render_rail_multi(sel, disp, filtered):
    """Queue card when multiple rows selected."""
    n = len(sel)

    items_html = []
    for idx in sel[:50]:
        if idx >= len(disp):
            continue
        ten = disp.iloc[idx]["Tên hàng"]
        ma  = disp.iloc[idx]["Mã hàng"]
        items_html.append(
            f'<li><span class="ten">{ten}</span>'
            f'<span class="ma">{ma}</span><span class="rm">×</span></li>'
        )

    hh_html(
        f'<div class="hh-card hh-queue">'
        f'  <div class="hh-card-head">'
        f'    <div class="row1">'
        f'      <div>'
        f'        <h3>Đã chọn {n} sản phẩm</h3>'
        f'        <div class="breadcrumb">SẴN SÀNG IN TEM</div>'
        f'      </div>'
        f'    </div>'
        f'  </div>'
        f'  <ul>{"".join(items_html)}</ul>'
        f'  <div style="padding:10px 12px;border-top:1px solid var(--hh-border);'
        f'              background:var(--hh-surface-2);'
        f'              display:flex;align-items:center;justify-content:space-between;'
        f'              font-size:12.5px">'
        f'    <span style="color:var(--hh-ink-3)">Tổng số tem: '
        f'      <b style="color:var(--hh-ink);font-family:var(--hh-mono)">{n}</b></span>'
        f'    <span class="hh-badge">CODE128</span>'
        f'  </div>'
        f'</div>'
    )

    if st.button(f"🏷 In {n} tem mã vạch", type="primary",
                 use_container_width=True, key="hh_print_multi"):
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


# ════════════════════════════════════════════════════════
# DIALOGS — modal wrappers around existing form helpers
# ════════════════════════════════════════════════════════

@st.dialog("➕ Thêm hàng hóa mới", width="large")
def _dlg_them_hang():
    _render_them_moi()


@st.dialog("✎ Sửa thông tin hàng hóa", width="large")
def _dlg_sua_hang_hoa(row_m):
    _render_sua_hang_hoa(row_m)


# ════════════════════════════════════════════════════════
# ADMIN HELPERS
# ════════════════════════════════════════════════════════

def _render_them_moi():
    """Form thêm hàng hóa mới vào master."""
    master = load_hang_hoa()

    # Gợi ý loai_hang và thuong_hieu từ master hiện có
    loai_opts = sorted(master["loai_hang"].dropna().unique().tolist()) \
        if not master.empty and "loai_hang" in master.columns else []

    cnt = st.session_state.get("hh_them_cnt", 0)

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        new_ma   = st.text_input("Mã hàng: *", key=f"hh_new_ma_{cnt}",
                                  placeholder="VD: PDH130")
        new_ten  = st.text_input("Tên hàng: *", key=f"hh_new_ten_{cnt}")
        new_vach = st.text_input("Mã vạch:", key=f"hh_new_vach_{cnt}")
        new_gb   = st.number_input("Giá bán:", min_value=0, step=10000,
                                    key=f"hh_new_gb_{cnt}", value=0)
    with c2:
        new_loai_sp = st.radio("Loại sản phẩm:", ["Hàng hóa", "Dịch vụ"],
                                horizontal=True, key=f"hh_new_loai_sp_{cnt}")
        loai_sel = st.selectbox("Loại hàng:",
            ["-- Chọn --"] + loai_opts + ["(Nhập mới)"],
            key=f"hh_new_loai_{cnt}")
        if loai_sel == "(Nhập mới)":
            new_loai = st.text_input("Tên loại mới:", key=f"hh_new_loai_txt_{cnt}")
        elif loai_sel == "-- Chọn --":
            new_loai = ""
        else:
            new_loai = loai_sel

        th_opts = []
        if new_loai and not master.empty and "thuong_hieu" in master.columns:
            th_opts = sorted(master[master["loai_hang"] == new_loai][
                "thuong_hieu"].dropna().unique().tolist())
        th_sel = st.selectbox("Thương hiệu:",
            ["-- Chọn --"] + th_opts + ["(Nhập mới)"],
            key=f"hh_new_th_{cnt}")
        if th_sel == "(Nhập mới)":
            new_th = st.text_input("Tên thương hiệu mới:", key=f"hh_new_th_txt_{cnt}")
        elif th_sel == "-- Chọn --":
            new_th = ""
        else:
            new_th = th_sel

        new_bh = st.text_input("Bảo hành:", key=f"hh_new_bh_{cnt}",
                                placeholder="VD: 12 tháng")

    can_add = bool(new_ma.strip()) and bool(new_ten.strip())
    if st.button("➕ Thêm hàng hóa", type="primary",
                 use_container_width=True, key=f"hh_add_btn_{cnt}",
                 disabled=not can_add):
        ma_clean = new_ma.strip().upper()
        # Kiểm tra trùng mã
        if not master.empty and ma_clean in master["ma_hang"].astype(str).str.upper().values:
            st.error(f"Mã hàng **{ma_clean}** đã tồn tại trong hệ thống.")
        else:
            try:
                supabase.table("hang_hoa").insert({
                    "ma_hang":    ma_clean,
                    "ten_hang":   new_ten.strip(),
                    "ma_vach":    new_vach.strip() or None,
                    "gia_ban":    int(new_gb),
                    "loai_sp":    new_loai_sp,
                    "loai_hang":  new_loai or None,
                    "thuong_hieu": new_th or None,
                    "bao_hanh":   new_bh.strip() or None,
                    "active":     True,
                }).execute()
                st.cache_data.clear()
                log_action("HH_ADD", f"ma={ma_clean} ten={new_ten.strip()}")
                st.success(f"✓ Đã thêm **{ma_clean}** — {new_ten.strip()}")
                st.session_state["hh_them_cnt"] = cnt + 1
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi: {e}")


def _render_sua_hang_hoa(row_m):
    """Form sửa thông tin hàng hóa đã có."""
    ma = str(row_m["ma_hang"])
    cnt = st.session_state.get(f"hh_sua_cnt_{ma}", 0)

    master = load_hang_hoa()
    loai_opts = sorted(master["loai_hang"].dropna().unique().tolist()) \
        if not master.empty and "loai_hang" in master.columns else []
    cur_loai = str(row_m.get("loai_hang") or "")
    cur_th   = str(row_m.get("thuong_hieu") or "")

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        new_ten  = st.text_input("Tên hàng:", value=str(row_m.get("ten_hang","")),
                                  key=f"hh_sua_ten_{ma}_{cnt}")
        new_vach = st.text_input("Mã vạch:", value=str(row_m.get("ma_vach","") or ""),
                                  key=f"hh_sua_vach_{ma}_{cnt}")
        new_gb   = st.number_input("Giá bán:", min_value=0, step=10000,
                                    value=int(row_m.get("gia_ban",0) or 0),
                                    key=f"hh_sua_gb_{ma}_{cnt}")
    with c2:
        cur_loai_sp = str(row_m.get("loai_sp") or "Hàng hóa")
        sp_options = ["Hàng hóa", "Dịch vụ"]
        sp_idx = sp_options.index(cur_loai_sp) if cur_loai_sp in sp_options else 0
        new_loai_sp = st.radio("Loại sản phẩm:", sp_options,
                                index=sp_idx, horizontal=True,
                                key=f"hh_sua_loai_sp_{ma}_{cnt}")
        loai_idx = (loai_opts.index(cur_loai) + 1) if cur_loai in loai_opts else 0
        loai_sel = st.selectbox("Loại hàng:",
            ["-- Giữ nguyên --"] + loai_opts,
            index=loai_idx, key=f"hh_sua_loai_{ma}_{cnt}")
        new_loai = "" if loai_sel == "-- Giữ nguyên --" else loai_sel

        th_opts = []
        check_loai = new_loai or cur_loai
        if check_loai and not master.empty and "thuong_hieu" in master.columns:
            th_opts = sorted(master[master["loai_hang"] == check_loai][
                "thuong_hieu"].dropna().unique().tolist())
        th_idx = (th_opts.index(cur_th) + 1) if cur_th in th_opts else 0
        th_sel = st.selectbox("Thương hiệu:",
            ["-- Giữ nguyên --"] + th_opts,
            index=th_idx, key=f"hh_sua_th_{ma}_{cnt}")
        new_th = "" if th_sel == "-- Giữ nguyên --" else th_sel

        new_bh = st.text_input("Bảo hành:", value=str(row_m.get("bao_hanh","") or ""),
                                key=f"hh_sua_bh_{ma}_{cnt}")

    if st.button("💾 Lưu thay đổi", type="primary",
                 use_container_width=True, key=f"hh_sua_btn_{ma}_{cnt}"):
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
            st.success("✓ Đã cập nhật thông tin hàng hóa.")
            st.session_state[f"hh_sua_cnt_{ma}"] = cnt + 1
            st.rerun()
        except Exception as e:
            st.error(f"Lỗi: {e}")


def _render_an_hang_hoa(ma: str, ten: str):
    """Nút soft-delete hàng hóa."""
    st.caption(
        "Ẩn hàng hóa sẽ xóa khỏi danh sách tìm kiếm nhưng giữ lại lịch sử giao dịch."
    )
    confirm_key = f"hh_an_confirm_{ma}"
    if not st.session_state.get(confirm_key):
        if st.button(f"🚫 Ẩn hàng hóa này ({ma})", type="secondary",
                     use_container_width=True, key=f"hh_an_btn_{ma}"):
            st.session_state[confirm_key] = True
            st.rerun()
    else:
        st.warning(f"Xác nhận ẩn **{ma} — {ten}**? Hành động này có thể hoàn tác bằng cách upload lại master.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✓ Xác nhận ẩn", type="primary",
                         use_container_width=True, key=f"hh_an_ok_{ma}"):
                try:
                    supabase.table("hang_hoa").update({"active": False}) \
                        .eq("ma_hang", ma).execute()
                    st.cache_data.clear()
                    log_action("HH_HIDE", f"ma={ma} ten={ten}")
                    st.session_state.pop(confirm_key, None)
                    st.session_state.pop("hh_ma_chon", None)
                    st.success(f"✓ Đã ẩn {ma}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")
        with c2:
            if st.button("Hủy", use_container_width=True, key=f"hh_an_cancel_{ma}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()


# ════════════════════════════════════════════════════════
# BARCODE LABEL PRINT (Phase 2 — PLAN_barcode_label_print.md)
# ════════════════════════════════════════════════════════

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

    # 1. Dropdown symbology
    symb_key = f"_intem_{dialog_key}_symb"
    symb = st.selectbox(
        "Loại mã vạch",
        options=list(SYMBOLOGY_OPTIONS.keys()),
        format_func=lambda k: SYMBOLOGY_OPTIONS[k],
        index=0,
        key=symb_key,
    )

    # 2. Bảng SL tem
    st.caption(f"Tổng {len(items)} SP đã chọn. Chỉnh SL tem cho từng SP:")
    qty_key = f"_intem_{dialog_key}_qty"
    if qty_key not in st.session_state:
        st.session_state[qty_key] = {}
    # Add new items with default qty, preserve existing
    for it in items:
        if it["ma_hang"] not in st.session_state[qty_key]:
            st.session_state[qty_key][it["ma_hang"]] = int(it.get("qty", 1) or 1)

    # Cảnh báo SP không có mã
    no_code = [it for it in items if not get_barcode_value(it)]
    if no_code:
        st.error(f"❌ {len(no_code)} SP không có Mã vạch lẫn Mã hàng — sẽ bị bỏ qua: " +
                 ", ".join((it.get("ten_hang", "?") or "?")[:25] for it in no_code[:5]))

    # Editable qty grid
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
    # Save back
    for _, r in edited.iterrows():
        st.session_state[qty_key][r["Mã hàng"]] = int(r["SL tem"] or 0)

    total = sum(st.session_state[qty_key].get(it["ma_hang"], 0) for it in items)
    st.info(f"📋 Tổng số tem sẽ in: **{total}**")
    if total > 500:
        st.warning("⚠️ Số tem lớn, browser có thể chậm khi render.")

    # 3. Nút Mở trang in
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

    Dùng Blob URL thay vì document.write để tránh phải embed HTML payload
    trực tiếp trong <script>. Payload có chứa </script> (từ inner bwip-js
    script trong _PAGE_TEMPLATE) — nếu inline trong script wrapper sẽ bị
    HTML parser đóng tag sớm. Escape "</" → "<\\/" trên JSON dump để chuỗi
    JS literal an toàn.
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
          // Revoke URL sau 60s (đủ thời gian tab mới load xong)
          setTimeout(function() {{ URL.revokeObjectURL(url); }}, 60000);
        }})();
        </script>
        <div style="color:#4caf50;font-family:sans-serif;padding:6px">
          ✅ Đã mở tab in. Kiểm tra tab mới.
        </div>
    """, height=40)

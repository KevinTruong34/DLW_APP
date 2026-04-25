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

from utils.helpers import _normalize

def module_hang_hoa():
    try:
        active     = get_active_branch()
        accessible = get_accessible_branches()

        # ── Chi nhánh filter ──
        if is_ke_toan_or_admin() and len(accessible) > 1:
            view_branches = st.multiselect(
                "Chi nhánh:", accessible, default=[active],
                key="hh_cn", label_visibility="collapsed")
            if not view_branches: st.warning("Chọn ít nhất một chi nhánh."); return
        else:
            view_branches = [active]

        # ── Load data ──
        master   = load_hang_hoa()
        the_kho  = load_the_kho(branches_key=tuple(view_branches))
        has_master = not master.empty

        if not has_master and the_kho.empty:
            st.info("Chưa có dữ liệu. Vào ⚙️ Quản trị → Upload để tải lên."); return

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

        # Dùng loai_hang + thuong_hieu nếu có, fallback nhom_hang
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

        # ══════ SEARCH + FILTER ══════
        cha_list = sorted([c for c in df["_cha"].dropna().unique() if c])

        col_s, col_f = st.columns([5, 1])
        with col_s:
            _sc = st.session_state.get("hh_search_cnt", 0)
            keyword = st.text_input("", key=f"hh_search_{_sc}",
                placeholder="🔍  Tìm mã hàng, mã vạch hoặc tên...",
                label_visibility="collapsed")
        with col_f:
            with st.popover("⊞ Lọc", use_container_width=True):
                cha_chon = st.selectbox("Nhóm hàng:", ["Tất cả"] + cha_list,
                    key="hh_cha", label_visibility="collapsed")
                if cha_chon != "Tất cả":
                    con_list = sorted([c for c in
                        df[df["_cha"]==cha_chon]["_con"].dropna().unique() if c])
                    con_chon = st.selectbox("Nhóm con:", ["Tất cả"] + con_list,
                        key="hh_con", label_visibility="collapsed")
                else:
                    con_chon = "Tất cả"
        cha_chon = st.session_state.get("hh_cha", "Tất cả")
        con_chon = st.session_state.get("hh_con", "Tất cả")

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
            st.warning("Không tìm thấy hàng hóa phù hợp."); return

        if len(filtered) == 1:
            st.session_state["hh_ma_chon"] = filtered.iloc[0]["ma_hang"]

        ma_chon = st.session_state.get("hh_ma_chon")
        if ma_chon and ma_chon not in filtered["ma_hang"].values:
            ma_chon = None; st.session_state.pop("hh_ma_chon", None)

        # ══════ DETAIL CARD ══════
        if ma_chon:
            row_m = filtered[filtered["ma_hang"] == ma_chon].iloc[0]
            ma_display = str(row_m["ma_hang"])
            vach       = str(row_m.get("ma_vach","") or "")
            nhom_full  = (f"{row_m['_cha']} › {row_m['_con']}"
                         if row_m.get("_con","") else row_m.get("_cha",""))
            gb = int(row_m.get("gia_ban", 0) or 0)

            extra_parts = []
            if pd.notna(row_m.get("thuong_hieu","")) and str(row_m.get("thuong_hieu","")).strip():
                extra_parts.append(f"Thương hiệu: {row_m['thuong_hieu']}")
            if pd.notna(row_m.get("bao_hanh","")) and str(row_m.get("bao_hanh","")).strip():
                extra_parts.append(f"Bảo hành: {row_m['bao_hanh']}")
            extra_str = " · ".join(extra_parts)

            vach_str   = f" · {vach}" if vach and vach != ma_display else ""
            nhom_html  = f"<div style='font-size:0.75rem;color:#aaa;margin-top:1px;'>{nhom_full}</div>" if nhom_full else ""
            extra_html = f"<div style='font-size:0.78rem;color:#666;margin-top:6px;'>{extra_str}</div>" if extra_str else ""
            gb_html    = (f"<div style='margin-top:10px;font-size:0.75rem;color:#888;'>Giá bán</div>"
                         f"<div style='font-size:1.1rem;font-weight:700;color:#1a1a2e;'>"
                         f"{'—' if not gb else f'{gb:,} đ'}</div>")

            c_card, c_close = st.columns([8, 1])
            with c_card:
                st.markdown(
                    f"<div style='background:#fff;border:1px solid #e0e0e0;"
                    f"border-radius:12px;padding:14px 16px;'>"
                    f"<div style='font-weight:700;font-size:1.05rem;color:#1a1a2e;'>"
                    f"{row_m['ten_hang']}</div>"
                    f"{nhom_html}"
                    f"<div style='margin-top:10px;'>"
                    f"<span style='font-family:monospace;font-size:0.95rem;font-weight:700;"
                    f"background:#f4f6fa;padding:4px 10px;border-radius:6px;color:#1a1a2e;'>"
                    f"{ma_display}</span>"
                    f"<span style='font-size:0.82rem;color:#999;margin-left:8px;'>{vach_str}</span>"
                    f"</div>"
                    f"{extra_html}"
                    f"{gb_html}"
                    f"</div>",
                    unsafe_allow_html=True)
            with c_close:
                st.markdown("<div style='padding-top:10px;'>", unsafe_allow_html=True)
                if st.button("✕", key="btn_close", help="Đóng"):
                    st.session_state.pop("hh_ma_chon", None)
                    st.session_state["hh_search_cnt"] = st.session_state.get("hh_search_cnt", 0) + 1
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            # Tồn kho 3 chi nhánh, highlight CN hiện tại (active, không phải active_cn)
            st.markdown(
                "<div style='font-size:0.82rem;font-weight:600;"
                "color:#555;margin:10px 0 6px;'>Tồn kho chi nhánh</div>",
                unsafe_allow_html=True)
            try:
                # Load tất cả 3 chi nhánh trong 1 call thay vì loop 3 lần
                all_kho = load_the_kho(branches_key=tuple(ALL_BRANCHES))
                branch_tons = {cn: 0 for cn in ALL_BRANCHES}
                if not all_kho.empty:
                    rows_kho = all_kho[all_kho["Mã hàng"].astype(str).str.strip() == str(ma_chon).strip()]
                    for _, kr in rows_kho.iterrows():
                        cn = kr.get("Chi nhánh", "")
                        if cn in branch_tons:
                            branch_tons[cn] += int(kr.get("Tồn cuối kì", 0) or 0)

                cn_cols = st.columns(3)
                for idx, cn_name in enumerate(ALL_BRANCHES):
                    with cn_cols[idx]:
                        ton    = branch_tons[cn_name]
                        is_cur = (cn_name == active)  # FIX: active thay vì active_cn
                        clr    = "#1a7f37" if ton > 5 else ("#cf4c2c" if ton > 0 else "#aaa")
                        border = "2px solid #e63946" if is_cur else "1px solid #e8e8e8"
                        bg     = "#fff8f8" if is_cur else "#fff"
                        icon   = "📍 " if is_cur else ""
                        st.markdown(
                            f"<div style='text-align:center;padding:10px 4px;"
                            f"border:{border};border-radius:10px;background:{bg};'>"
                            f"<div style='font-size:0.68rem;color:#777;"
                            f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>"
                            f"{icon}{CN_SHORT.get(cn_name, cn_name)}</div>"
                            f"<div style='font-size:1.4rem;font-weight:700;color:{clr};'>"
                            f"{ton:,}</div></div>",
                            unsafe_allow_html=True)
            except Exception:
                pass

            st.markdown("<hr style='margin:12px 0 6px;'>", unsafe_allow_html=True)

        # ══════ BẢNG HÀNG HÓA ══════
        total = len(filtered)
        filter_label = (f"{cha_chon}" if cha_chon != "Tất cả" else "")
        st.caption(
            f"**{total}** sản phẩm"
            + (f" · {filter_label}" if filter_label else "")
            + f" · {', '.join(view_branches)}"
            + (" — lọc thêm để thu hẹp" if total > 100 else "")
        )

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

        event = st.dataframe(
            disp,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="hh_table",
            column_config={
                "Tên hàng": st.column_config.TextColumn("Tên hàng", width="medium"),
                "Mã hàng":  st.column_config.TextColumn("Mã hàng",  width="medium"),
                "Mã vạch":  st.column_config.TextColumn("Mã vạch",  width="medium"),
                "Tồn kho":  st.column_config.NumberColumn("Tồn", width="small", format="%d"),
            },
            height=tbl_h,
        )

        sel = event.selection.rows
        if sel and sel[0] < len(disp):
            new_ma = disp.iloc[sel[0]]["Mã hàng"]
            if new_ma != ma_chon:
                st.session_state["hh_ma_chon"] = new_ma
                st.rerun()

        if not ma_chon:
            st.caption("↑ Chọn một dòng để xem chi tiết sản phẩm")

    except Exception as e:
        st.error(f"Lỗi tải Hàng hóa: {e}")


# ==========================================
# MODULE: CHUYỂN HÀNG — v16.0
# Workflow: Phiếu tạm → Đang chuyển → Đã nhận
#           (Admin: → Đã hủy bất cứ lúc nào)
# ==========================================

PHIEU_PER_PAGE   = 20    # Giới hạn 20 phiếu/trang
SUGGEST_LIMIT    = 5     # Giới hạn 5 sản phẩm gợi ý

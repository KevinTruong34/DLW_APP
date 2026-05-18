import io
import streamlit as st
import pandas as pd
import uuid
from datetime import datetime
import numpy as np

from utils.helpers import _normalize, now_vn, now_vn_iso, today_vn, fmt_vn
from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
from utils.kk_style import (
    inject_kiem_ke_css,
    inject_audio_unlock_js,
    inject_auto_focus_js,
    play_beep_ok,
    play_beep_bad,
    hero_scan_card_html,
    context_bar_html,
    detail_empty_html,
    detail_header_html,
    kpi_tiles_scanning_html,
    kpi_tiles_waiting_html,
    hint_line_html,
)


def _kk_get_lines(ma_phieu: str) -> pd.DataFrame:
    res = supabase.table("phieu_kiem_ke_chi_tiet").select("*") \
        .eq("ma_phieu_kk", ma_phieu).execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    for col in ["ton_snapshot", "sl_quet", "sl_thuc_te", "ton_ky_vong_luc_duyet", "chenh_lech"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    # Sắp xếp: mã vừa quét gần nhất lên đầu (updated_at desc)
    # Hàng chưa quét (sl_quet=0) xuống cuối
    if "updated_at" in df.columns:
        df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")
        df["_da_quet"] = (df["sl_quet"] > 0).astype(int)
        df = df.sort_values(["_da_quet", "updated_at"], ascending=[False, False])
        df = df.drop(columns=["_da_quet"])
    else:
        df = df.sort_values("sl_quet", ascending=False)
    return df.reset_index(drop=True)


def _kk_complete(ma_phieu: str) -> tuple[bool, str]:
    """Nhân viên hoàn thành quét → chuyển phiếu sang Chờ duyệt admin."""
    try:
        supabase.table("phieu_kiem_ke").update({
            "trang_thai": "Chờ duyệt admin",
        }).eq("ma_phieu_kk", ma_phieu).execute()
        st.cache_data.clear()
        log_action("KIEMKE_COMPLETE", f"ma={ma_phieu}")
        return True, f"Phiếu {ma_phieu} đã chuyển sang Chờ duyệt admin."
    except Exception as e:
        return False, f"Lỗi hoàn thành phiếu: {e}"


def _kk_gen_ma_phieu() -> str:
    try:
        res = supabase.table("phieu_kiem_ke").select("ma_phieu_kk") \
            .like("ma_phieu_kk", "KK______").order("ma_phieu_kk", desc=True).limit(1).execute()
        if res.data:
            try:
                num = int(str(res.data[0]["ma_phieu_kk"])[2:]) + 1
            except Exception:
                num = 1
        else:
            num = 1
        return f"KK{num:06d}"
    except Exception:
        return f"KK{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:4].upper()}"


def _kk_build_scope_rows(chi_nhanh: str, nhom_hang_chon: str) -> tuple[list, str]:
    master = load_hang_hoa()
    kho = load_the_kho(branches_key=(chi_nhanh,))
    if master.empty or kho.empty:
        return [], "Chưa đủ dữ liệu master/thẻ kho để tạo phiếu kiểm kê."

    kho_map = kho.groupby("Mã hàng", as_index=False).agg(ton=("Tồn cuối kì", "sum"))
    # inner join: chỉ lấy hàng thực sự tồn tại trong kho chi nhánh này
    df = master.merge(kho_map, left_on="ma_hang", right_on="Mã hàng", how="inner")
    df["ton"] = pd.to_numeric(df["ton"], errors="coerce").fillna(0).astype(int)

    # Dùng loai_hang + thuong_hieu nếu có, fallback nhom_hang cũ
    def _get_nhom_col(df_in):
        if "loai_hang" in df_in.columns:
            th = df_in.get("thuong_hieu", pd.Series([""] * len(df_in))).fillna("")
            lt = df_in["loai_hang"].fillna("")
            return lt.where(th == "", lt + ">>" + th)
        return df_in["nhom_hang"].fillna("") if "nhom_hang" in df_in.columns else pd.Series([""] * len(df_in))

    nhom_col  = _get_nhom_col(df)
    nhom_list = [x.strip() for x in nhom_hang_chon.split("|") if x.strip()]
    mask = pd.Series([False] * len(df), index=df.index)
    for nhom in nhom_list:
        nhom_norm = ">>".join(p.strip() for p in nhom.split(">>"))
        if ">>" in nhom_norm:
            mask = mask | (nhom_col == nhom_norm)
        else:
            mask = mask | (nhom_col == nhom_norm) | nhom_col.str.startswith(nhom_norm + ">>")
    df = df[mask].copy()

    if df.empty:
        return [], f"Nhóm **{nhom_hang_chon}** không có mặt hàng nào tại chi nhánh này."

    # Tách thành 2 nhóm: có tồn > 0 (đưa vào phiếu luôn) và tồn = 0 (bỏ qua)
    # Nhân viên có thể quét phát sinh thêm nếu thực tế có hàng mà hệ thống chưa ghi nhận
    df = df[df["ton"] > 0].copy()

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "ma_hang": str(r.get("ma_hang", "") or ""),
            "ma_vach": str(r.get("ma_vach", "") or ""),
            "ten_hang": str(r.get("ten_hang", "") or ""),
            "nhom_hang": str(r.get("nhom_hang", "") or ""),
            "ton_snapshot": int(r.get("ton", 0) or 0),
            "sl_quet": 0,
            "sl_thuc_te": 0,
            "ton_ky_vong_luc_duyet": 0,
            "chenh_lech": 0,
            "trang_thai_dong": "Đang kiểm",
        })
    return rows, ""


def _kk_create_phieu(chi_nhanh: str, nhom_cha: str, ghi_chu: str) -> tuple[bool, str]:
    rows, err = _kk_build_scope_rows(chi_nhanh, nhom_cha)
    if err:
        return False, err

    ma = _kk_gen_ma_phieu()
    user = get_user() or {}
    try:
        supabase.table("phieu_kiem_ke").insert({
            "ma_phieu_kk": ma,
            "chi_nhanh": chi_nhanh,
            "trang_thai": "Đang kiểm",
            "nhom_cha": nhom_cha,
            "ghi_chu": ghi_chu.strip(),
            "created_by": user.get("ho_ten", ""),
            "created_at": now_vn_iso(),
            "completed_at": None,
            "approved_by": None,
            "approved_at": None,
        }).execute()

        payload = []
        for r in rows:
            p = dict(r)
            p["ma_phieu_kk"] = ma
            payload.append(p)
        for i in range(0, len(payload), 500):
            supabase.table("phieu_kiem_ke_chi_tiet").insert(payload[i:i+500]).execute()
        st.cache_data.clear()
        log_action("KIEMKE_CREATE", f"ma={ma} cn={chi_nhanh} nhom={nhom_cha} rows={len(rows)}")
        return True, ma
    except Exception as e:
        return False, f"Lỗi tạo phiếu kiểm kê: {e}"


def _kk_scan_plus_one(ma_phieu: str, code: str) -> tuple[bool, str]:
    code = str(code or "").strip()
    if not code:
        return False, "Mã quét rỗng."

    code_n = code.lower()
    try:
        # 1. Tìm mã trong DÒNG CHI TIẾT của phiếu hiện tại
        rows = supabase.table("phieu_kiem_ke_chi_tiet") \
            .select("id,ma_hang,ma_vach,sl_quet,sl_thuc_te") \
            .eq("ma_phieu_kk", ma_phieu).execute().data or []

        hit = None
        for r in rows:
            mh = str(r.get("ma_hang", "") or "").strip().lower()
            mv = str(r.get("ma_vach", "") or "").strip().lower()
            if code_n == mh or code_n == mv:
                hit = r; break

        if hit:
            # ĐÃ CÓ TRONG PHIẾU: Cộng dồn +1
            sl_quet = int(hit.get("sl_quet", 0) or 0) + 1
            sl_tt = int(hit.get("sl_thuc_te", 0) or 0) + 1
            supabase.table("phieu_kiem_ke_chi_tiet").update({
                "sl_quet": sl_quet, "sl_thuc_te": sl_tt
            }).eq("id", hit["id"]).execute()
            return True, str(hit.get("ma_hang", "") or code)

        else:
            # KHÔNG CÓ TRONG PHIẾU (Tồn = 0): Lấy từ Master Data chèn vào
            master = load_hang_hoa()
            if master.empty:
                return False, "Dữ liệu Hàng hóa (Master) trống."

            match_mask = (master["ma_hang"].astype(str).str.strip().str.lower() == code_n) | \
                         (master["ma_vach"].astype(str).str.strip().str.lower() == code_n)
            m_hit = master[match_mask]

            if m_hit.empty:
                return False, f"Mã '{code}' hoàn toàn không tồn tại trong hệ thống KiotViet."

            row_data = m_hit.iloc[0]
            mh_new = str(row_data.get("ma_hang", ""))

            supabase.table("phieu_kiem_ke_chi_tiet").insert({
                "ma_phieu_kk": ma_phieu,
                "ma_hang": mh_new,
                "ma_vach": str(row_data.get("ma_vach", "")),
                "ten_hang": str(row_data.get("ten_hang", "")),
                "nhom_hang": str(row_data.get("nhom_hang", "")),
                "ton_snapshot": 0, # Tồn lúc tạo phiếu là 0
                "sl_quet": 1,      # Lần quét đầu tiên
                "sl_thuc_te": 1,
                "ton_ky_vong_luc_duyet": 0,
                "chenh_lech": 0,
                "trang_thai_dong": "Đang kiểm"
            }).execute()

            return True, f"{mh_new} (Phát sinh mới)"

    except Exception as e:
        return False, f"Lỗi scan: {e}"


def _kk_cancel_phieu(ma_phieu: str) -> tuple[bool, str]:
    try:
        supabase.table("phieu_kiem_ke_chi_tiet").delete().eq("ma_phieu_kk", ma_phieu).execute()
        supabase.table("phieu_kiem_ke").delete().eq("ma_phieu_kk", ma_phieu).execute()
        st.cache_data.clear()
        log_action("KIEMKE_CANCEL", f"ma={ma_phieu}")
        return True, "Đã hủy và xóa phiếu kiểm kê."
    except Exception as e:
        return False, f"Lỗi hủy phiếu: {e}"
def _kk_approve(ma_phieu: str) -> tuple[bool, str]:
    """
    Duyệt phiếu kiểm kê — atomic qua RPC duyet_phieu_kiem_ke.
    RPC sẽ:
      1. Validate trạng thái phiếu = 'Chờ duyệt admin'
      2. Apply sl_thuc_te vào the_kho cho từng dòng (UPDATE/INSERT)
      3. Ghi chenh_lech + trạng thái 'Đã duyệt' cho chi tiết
      4. Update header phiếu
    """
    try:
        res = supabase.rpc("duyet_phieu_kiem_ke", {
            "p_ma_phieu":   ma_phieu,
            "p_nguoi_duyet": (get_user() or {}).get("ho_ten", ""),
        }).execute()
        result = res.data
        if isinstance(result, list):
            result = result[0]
        if result.get("ok"):
            n_rows = result.get("updated_rows", 0)
            cn     = result.get("chi_nhanh", "")
            st.cache_data.clear()
            log_action("KIEMKE_APPROVE",
                       f"ma={ma_phieu} cn={cn} rows={n_rows}")
            return True, f"✓ Đã duyệt phiếu — cập nhật tồn cho {n_rows} mặt hàng tại {cn}."
        else:
            return False, result.get("error", "Lỗi không xác định")
    except Exception as e:
        return False, f"Lỗi duyệt phiếu: {e}"


# ═══════════════════════════════════════════════════════════════════════════
# v2 helpers — không sửa signature 8 _kk_* helpers ở trên (HANDOFF section 5).
# Mọi optimization làm ở caller (UI) hoặc helper mới dưới đây.
# ═══════════════════════════════════════════════════════════════════════════


def _kk_lookup_after_scan(ma_phieu: str, code: str) -> dict | None:
    """Re-fetch row vừa scan để render hero card.

    Gọi sau `_kk_scan_plus_one(ok=True)`. Returns dict với keys:
    ma_hang, ten_hang, ma_vach, gia_ban, sl_quet, sl_thuc_te, ton.
    Returns None nếu không tìm thấy (hiếm — chỉ khi race condition).
    """
    code_n = (code or "").strip().lower()
    if not code_n:
        return None
    try:
        rows = supabase.table("phieu_kiem_ke_chi_tiet") \
            .select("ma_hang,ma_vach,ten_hang,ton_snapshot,sl_quet,sl_thuc_te") \
            .eq("ma_phieu_kk", ma_phieu).execute().data or []
        hit = None
        for r in rows:
            mh = str(r.get("ma_hang", "") or "").strip().lower()
            mv = str(r.get("ma_vach", "") or "").strip().lower()
            if code_n == mh or code_n == mv:
                hit = r
                break
        if not hit:
            return None
        try:
            gia = int(get_gia_ban_map().get(hit["ma_hang"], 0) or 0)
        except Exception:
            gia = 0
        return {
            "ma_hang": hit["ma_hang"],
            "ten_hang": hit.get("ten_hang", "") or "",
            "ma_vach": hit.get("ma_vach", "") or "",
            "gia_ban": gia,
            "sl_quet": int(hit.get("sl_quet", 0) or 0),
            "sl_thuc_te": int(hit.get("sl_thuc_te", 0) or 0),
            "ton": int(hit.get("ton_snapshot", 0) or 0),
        }
    except Exception:
        return None


def _fmt_phieu_date(created_at) -> str:
    if not created_at:
        return "—"
    try:
        return (pd.to_datetime(created_at, utc=True)
                .tz_convert("Asia/Ho_Chi_Minh")
                .strftime("%d/%m %H:%M"))
    except Exception:
        return str(created_at)[:16]


def _filter_chips_row(state_key: str, default: str, chips: list[tuple[str, str, int]],
                      extra_cols: int = 0) -> str:
    """Render chip row + optional reserve cho extra widgets bên phải.

    chips: [(label, key, count), ...]. Returns active filter key.
    extra_cols: số columns trống bên phải (để caller chèn search/button).
    """
    active = st.session_state.get(state_key, default)
    weights = [1.4] * len(chips) + [max(1, extra_cols)] * (1 if extra_cols else 0)
    cols = st.columns(weights, gap="small")
    for i, (label, key, count) in enumerate(chips):
        with cols[i]:
            is_active = (active == key)
            if st.button(
                f"{label} · {count}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
                key=f"chip_{state_key}_{key}",
            ):
                st.session_state[state_key] = key
                st.rerun()
    return active


def _apply_scan_filter(lines: pd.DataFrame, filt: str) -> pd.DataFrame:
    """Filter lines theo chip key trên tab Quét. Cần cột 'Lệch Tạm' + 'SL Quét'."""
    if filt == "lech":
        return lines[lines["Lệch Tạm"] != 0]
    if filt == "khop":
        return lines[(lines["Lệch Tạm"] == 0) & (lines["SL Quét"] > 0)]
    if filt == "chua":
        return lines[lines["SL Quét"] == 0]
    return lines


def _apply_manage_filter(df: pd.DataFrame, filt: str) -> pd.DataFrame:
    """Filter phiếu list theo chip key trên tab Quản lý."""
    if filt == "scanning":
        return df[df["trang_thai"] == "Đang kiểm"]
    if filt == "waiting":
        return df[df["trang_thai"] == "Chờ duyệt admin"]
    if filt == "approved":
        return df[df["trang_thai"] == "Đã duyệt"]
    return df


@st.dialog("Tạo phiếu kiểm kê mới")
def _dlg_create_phieu(active: str, accessible: list[str]) -> None:
    """Dialog form thay thế sub-tab Tạo phiếu cũ (HANDOFF section 4)."""
    # Lock chi nhánh = active. View/Quét/Quản lý chỉ thấy phiếu của active,
    # nên tạo phiếu cho branch khác sẽ tạo "phiếu ẩn" — disable selector.
    cn_create = active
    st.info(f"🏷️ Mã phiếu dự kiến: **{_kk_gen_ma_phieu()}**  ·  "
            f"📍 Chi nhánh: **{active}**")

    master = load_hang_hoa()
    if master.empty:
        st.warning("Chưa có dữ liệu hàng hóa.")
        return

    if "loai_hang" in master.columns:
        master["_cha"] = master["loai_hang"].fillna("")
        master["_con"] = master.get("thuong_hieu", pd.Series([""] * len(master))).fillna("")
    else:
        nhom_col = master["nhom_hang"].fillna("") if "nhom_hang" in master.columns else pd.Series([""] * len(master))
        split = nhom_col.str.split(">>", n=1, expand=True)
        master["_cha"] = split[0].fillna("").str.strip()
        master["_con"] = split[1].fillna("").str.strip() if len(split.columns) > 1 else ""

    nhom_cha_list = sorted([str(x) for x in master["_cha"].unique() if str(x)])
    if not nhom_cha_list:
        st.warning("Không tìm thấy dữ liệu nhóm hàng.")
        return

    nhom_flat = []
    for cha in nhom_cha_list:
        nhom_flat.append(cha)
        con_list = sorted([str(x) for x in master[master["_cha"] == cha]["_con"].unique() if str(x)])
        for con in con_list:
            nhom_flat.append(f"{cha}>>{con}")

    nhom_chon_list = st.multiselect(
        "Nhóm hàng kiểm kê (chọn nhiều):",
        options=nhom_flat,
        placeholder="Chọn ít nhất 1 nhóm…",
        key=f"kk_dlg_nhom_{st.session_state.get('kk_create_count', 0)}",
    )
    nhom_chon = "|".join(nhom_chon_list) if nhom_chon_list else ""

    ghi_chu = st.text_area(
        "Ghi chú (tùy chọn):",
        key=f"kk_dlg_ghi_chu_{st.session_state.get('kk_create_count', 0)}",
        placeholder="Ghi chú cho đợt kiểm kê này…",
    )

    c_cancel, c_ok = st.columns([1, 1.4])
    with c_cancel:
        if st.button("Hủy", use_container_width=True, key="kk_dlg_cancel"):
            st.rerun()
    with c_ok:
        if st.button("Tạo phiếu kiểm kê", type="primary",
                     use_container_width=True, disabled=not nhom_chon,
                     key="kk_dlg_create"):
            ok, msg = _kk_create_phieu(cn_create, nhom_chon, ghi_chu)
            if ok:
                st.session_state["kk_active_ma"] = msg
                st.session_state["kk_create_count"] = (
                    st.session_state.get("kk_create_count", 0) + 1
                )
                st.session_state["kk_manage_selected"] = msg
                load_phieu_kiem_ke.clear()
                st.success(f"Đã tạo phiếu {msg}.")
                st.rerun()
            else:
                st.error(msg)


def _excel_download_button(lines: pd.DataFrame, ma_phieu: str, key: str,
                            label: str = "📥 Xuất Excel KiotViet") -> None:
    """Download button cho 2-cột Excel format KiotViet."""
    df_export = lines[["ma_hang", "sl_thuc_te"]].copy()
    df_export.columns = ["Mã hàng", "Số lượng"]
    buf = io.BytesIO()
    df_export.to_excel(buf, index=False)
    buf.seek(0)
    st.download_button(
        label=label,
        data=buf,
        file_name=f"KiemKe_{ma_phieu}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=key,
    )


# ═══════════════════════════════════════════════════════════════════════════
# TAB QUÉT — hero card + scan flow + filter chips + items table + footer
# ═══════════════════════════════════════════════════════════════════════════

def _render_tab_scan(active: str, accessible: list[str]) -> None:
    # Branch scoping: chỉ load phiếu của chi nhánh đang đăng nhập (active),
    # không phải tất cả accessible. Áp dụng cho mọi role (admin/kế toán/nv).
    try:
        df = load_phieu_kiem_ke((active,))
    except Exception as e:
        st.error(f"Lỗi tải danh sách phiếu: {e}")
        return

    if df.empty or "trang_thai" not in df.columns:
        st.info("Chưa có phiếu kiểm kê. Mở tab **Quản lý phiếu** để tạo phiếu mới.")
        return

    candidates = df[df["trang_thai"] == "Đang kiểm"].copy()
    if candidates.empty:
        st.info("Không có phiếu ở trạng thái **Đang kiểm**. Tạo phiếu mới ở tab "
                "**Quản lý phiếu**.")
        return

    # ── Phiếu picker (selectbox) ───────────────────────────────────────────
    opts = [
        f"{r['ma_phieu_kk']} · {r.get('chi_nhanh','')} · {r.get('nhom_cha','')}"
        for _, r in candidates.iterrows()
    ]
    idx = 0
    ma_saved = st.session_state.get("kk_active_ma")
    if ma_saved:
        for i, x in enumerate(opts):
            if x.startswith(ma_saved):
                idx = i
                break
    picked = st.selectbox("Phiếu đang kiểm:", opts, index=idx,
                          key="kk_picker_label",
                          label_visibility="collapsed")
    ma_phieu = picked.split(" · ")[0]
    st.session_state["kk_active_ma"] = ma_phieu

    header_row = candidates[candidates["ma_phieu_kk"] == ma_phieu].iloc[0]

    # ── Load lines + compute stats cho context bar + filter counts ──────────
    try:
        lines = _kk_get_lines(ma_phieu)
    except Exception as e:
        st.error(f"Lỗi tải chi tiết phiếu: {e}")
        return

    if not lines.empty:
        lines["Lệch Tạm"] = lines["sl_thuc_te"] - lines["ton_snapshot"]
        progress_done = int(lines["sl_thuc_te"].sum())
        progress_total = int(lines["ton_snapshot"].sum())
        kpi_ok = int(((lines["Lệch Tạm"] == 0) & (lines["sl_quet"] > 0)).sum())
        kpi_bad = int(lines["Lệch Tạm"].sum())
    else:
        progress_done = progress_total = kpi_ok = kpi_bad = 0

    # ── Context bar ────────────────────────────────────────────────────────
    st.html(context_bar_html(
        ma_phieu=ma_phieu,
        chi_nhanh=str(header_row.get("chi_nhanh", "") or ""),
        nhom_cha=str(header_row.get("nhom_cha", "") or ""),
        created_by=str(header_row.get("created_by", "") or ""),
        created_at_str=_fmt_phieu_date(header_row.get("created_at")),
        progress_done=progress_done,
        progress_total=progress_total,
        kpi_ok=kpi_ok,
        kpi_bad=kpi_bad,
    ))

    # ── Hero scan card (từ session state) + beep ───────────────────────────
    last_scan = st.session_state.get("kk_last_scan")
    flash = st.session_state.pop("kk_flash", None)
    st.html(hero_scan_card_html(last_scan, flash))
    if flash == "ok":
        play_beep_ok()
    elif flash == "bad":
        play_beep_bad()

    # ── Scan form (st.form + USB scanner pattern preserved) ────────────────
    with st.form("kk_scan_form", clear_on_submit=True):
        code = st.text_input(
            "Quét mã vạch / mã hàng:",
            key="kk_scan_code",
            placeholder="Đưa con trỏ ở đây và quét mã vạch / mã hàng…",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Quét +1", type="primary", use_container_width=True
        )
    if submitted:
        code_clean = (code or "").strip()
        if not code_clean:
            st.toast("Mã quét rỗng.", icon="⚠️")
        else:
            ok, msg = _kk_scan_plus_one(ma_phieu, code_clean)
            if ok:
                item = _kk_lookup_after_scan(ma_phieu, code_clean) or {
                    "ma_hang": msg, "ten_hang": "", "ma_vach": "",
                    "gia_ban": 0, "sl_quet": 1, "sl_thuc_te": 1, "ton": 0,
                }
                if "(Phát sinh mới)" in msg:
                    item["phat_sinh"] = True
                st.session_state["kk_last_scan"] = item
                st.session_state["kk_flash"] = "ok"
            else:
                st.session_state["kk_last_scan"] = {"error": True, "code": code_clean}
                st.session_state["kk_flash"] = "bad"
            # Granular invalidate — KHÔNG dùng st.cache_data.clear() global
            # (HANDOFF section 2.1).
            load_phieu_kiem_ke.clear()
            st.rerun()

    if lines.empty:
        st.html(hint_line_html(
            "Phiếu này chưa có chi tiết. Quét mã đầu tiên để bắt đầu."
        ))
        inject_auto_focus_js()
        return

    # ── Filter chips ───────────────────────────────────────────────────────
    n_all = len(lines)
    n_lech = int((lines["Lệch Tạm"] != 0).sum())
    n_khop = int(((lines["Lệch Tạm"] == 0) & (lines["sl_quet"] > 0)).sum())
    n_chua = int((lines["sl_quet"] == 0).sum())
    active_filter = _filter_chips_row(
        "kk_scan_filter", "all",
        [("Tất cả", "all", n_all),
         ("Còn lệch", "lech", n_lech),
         ("Đã khớp", "khop", n_khop),
         ("Chưa quét", "chua", n_chua)],
    )

    # ── Hint ───────────────────────────────────────────────────────────────
    st.html(hint_line_html(
        "Nháy đúp cột <b style='color:var(--ink-2);'>SL Thực tế</b> để sửa "
        "trực tiếp · Mã vừa quét nhảy lên đầu bảng"
    ))

    # ── Data editor (filtered) ─────────────────────────────────────────────
    view = lines.rename(columns={
        "id": "ID", "ma_hang": "Mã Hàng", "ma_vach": "Mã Vạch",
        "ten_hang": "Tên Hàng", "ton_snapshot": "Tồn Kho",
        "sl_quet": "SL Quét", "sl_thuc_te": "SL Thực Tế",
    })
    view = _apply_scan_filter(view, active_filter)
    cols = ["ID", "Mã Hàng", "Mã Vạch", "Tên Hàng", "Tồn Kho",
            "SL Quét", "SL Thực Tế", "Lệch Tạm"]
    cols = [c for c in cols if c in view.columns]

    editor_key = f"kk_editor_{ma_phieu}_{active_filter}"
    edited_df = st.data_editor(
        view[cols],
        use_container_width=True,
        hide_index=True,
        key=editor_key,
        height=360,
        column_config={
            "ID": None,
            "Mã Hàng": st.column_config.TextColumn(disabled=True),
            "Mã Vạch": st.column_config.TextColumn(disabled=True),
            "Tên Hàng": st.column_config.TextColumn(disabled=True),
            "Tồn Kho": st.column_config.NumberColumn(disabled=True),
            "SL Quét": st.column_config.NumberColumn(disabled=True),
            "Lệch Tạm": st.column_config.NumberColumn(disabled=True),
            "SL Thực Tế": st.column_config.NumberColumn(
                "SL Thực Tế ✏️", min_value=0, step=1,
                help="Nháy đúp để sửa số lượng thực tế",
            ),
        },
    )

    changes = st.session_state.get(editor_key, {}).get("edited_rows", {})
    if changes:
        st.warning("⚠️ Có thay đổi chưa lưu. Bấm **Lưu các dòng đã sửa** "
                   "trước khi đổi filter hay hành động khác.")
        if st.button("💾 Lưu các dòng đã sửa", type="primary",
                     use_container_width=True, key=f"save_{editor_key}"):
            try:
                for row_idx, edit_data in changes.items():
                    if "SL Thực Tế" in edit_data:
                        new_sl = int(edit_data["SL Thực Tế"])
                        row_id = int(view.iloc[int(row_idx)]["ID"])
                        supabase.table("phieu_kiem_ke_chi_tiet").update({
                            "sl_thuc_te": new_sl
                        }).eq("id", row_id).execute()
                st.success("✓ Đã cập nhật số lượng.")
                load_phieu_kiem_ke.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi khi lưu: {e}")

    # ── Footer actions: Complete / Excel / Cancel ─────────────────────────
    st.markdown("")
    c_complete, c_excel, c_cancel = st.columns([2, 1.5, 1.2])
    with c_complete:
        if st.button("✓ Hoàn thành kiểm kê", type="primary",
                     use_container_width=True, disabled=bool(changes),
                     key=f"complete_{ma_phieu}"):
            ok, msg = _kk_complete(ma_phieu)
            if ok:
                load_phieu_kiem_ke.clear()
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    with c_excel:
        _excel_download_button(lines, ma_phieu, key=f"dl_scan_{ma_phieu}")
    with c_cancel:
        if st.button("🗑 Hủy phiếu", use_container_width=True,
                     key=f"cancel_{ma_phieu}"):
            ok, msg = _kk_cancel_phieu(ma_phieu)
            if ok:
                st.session_state.pop("kk_active_ma", None)
                load_phieu_kiem_ke.clear()
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # ── Auto-focus (HANDOFF section 2.3 override) ─────────────────────────
    inject_auto_focus_js()


# ═══════════════════════════════════════════════════════════════════════════
# TAB QUẢN LÝ — toolbar + native dataframe + detail panel
# ═══════════════════════════════════════════════════════════════════════════

_STATUS_EMOJI = {
    "Đang kiểm":       "🟡 Đang kiểm",
    "Chờ duyệt admin": "🔵 Chờ duyệt",
    "Đã duyệt":        "🟢 Đã duyệt",
}


def _render_tab_manage(active: str, accessible: list[str]) -> None:
    # Branch scoping: như _render_tab_scan, chỉ load phiếu chi nhánh active.
    try:
        df = load_phieu_kiem_ke((active,))
    except Exception as e:
        st.error(f"Lỗi tải danh sách phiếu: {e}")
        return

    # ── Toolbar: chips + search + Tạo phiếu button ─────────────────────────
    if df.empty or "trang_thai" not in df.columns:
        n_all = n_scan = n_wait = n_done = 0
    else:
        n_all = len(df)
        n_scan = int((df["trang_thai"] == "Đang kiểm").sum())
        n_wait = int((df["trang_thai"] == "Chờ duyệt admin").sum())
        n_done = int((df["trang_thai"] == "Đã duyệt").sum())

    chips = [
        ("Tất cả", "all", n_all),
        ("Đang kiểm", "scanning", n_scan),
        ("Chờ duyệt", "waiting", n_wait),
        ("Đã duyệt", "approved", n_done),
    ]
    # 4 chips + search + create button => 6 columns
    weights = [1.4] * 4 + [3.5, 1.6]
    cols = st.columns(weights, gap="small")
    active_filter = st.session_state.get("kk_mgr_filter", "all")
    for i, (label, key, count) in enumerate(chips):
        with cols[i]:
            is_a = (active_filter == key)
            if st.button(
                f"{label} · {count}",
                type="primary" if is_a else "secondary",
                use_container_width=True,
                key=f"chip_mgr_{key}",
            ):
                st.session_state["kk_mgr_filter"] = key
                st.session_state.pop("kk_manage_selected", None)
                st.rerun()
    with cols[4]:
        search_q = st.text_input(
            "Tìm phiếu", label_visibility="collapsed",
            placeholder="Tìm mã phiếu / chi nhánh / nhóm…",
            key="kk_mgr_search",
        )
    with cols[5]:
        if st.button("➕ Tạo phiếu", type="primary",
                     use_container_width=True, key="kk_mgr_create"):
            _dlg_create_phieu(active, accessible)

    if df.empty or "trang_thai" not in df.columns:
        st.html(detail_empty_html())
        return

    # ── Filter + search ────────────────────────────────────────────────────
    view_df = _apply_manage_filter(df, active_filter).copy()
    if search_q:
        q = search_q.strip().lower()
        def _match(row):
            blob = " ".join(str(row.get(c, "") or "") for c in
                            ["ma_phieu_kk", "chi_nhanh", "nhom_cha"]).lower()
            return q in blob
        view_df = view_df[view_df.apply(_match, axis=1)]

    if view_df.empty:
        st.info("Không có phiếu nào khớp filter / search hiện tại.")
        st.html(detail_empty_html())
        return

    # ── Build display dataframe ────────────────────────────────────────────
    disp = view_df.copy()
    disp["Trạng Thái"] = disp["trang_thai"].map(lambda s: _STATUS_EMOJI.get(s, s))
    if "created_at" in disp.columns:
        disp["Ngày Tạo"] = (pd.to_datetime(disp["created_at"], utc=True)
                            .dt.tz_convert("Asia/Ho_Chi_Minh")
                            .dt.strftime("%d/%m/%Y %H:%M"))
    disp = disp.rename(columns={
        "ma_phieu_kk": "Mã Phiếu",
        "chi_nhanh":   "Chi Nhánh",
        "nhom_cha":    "Nhóm Hàng",
        "created_by":  "Người Tạo",
    })
    show_cols = ["Mã Phiếu", "Chi Nhánh", "Nhóm Hàng", "Trạng Thái",
                 "Người Tạo", "Ngày Tạo"]
    show_cols = [c for c in show_cols if c in disp.columns]

    sel_event = st.dataframe(
        disp[show_cols],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=min(380, 56 + 36 * max(1, len(disp))),
        key=f"kk_mgr_table_{active_filter}",
    )

    # Defensive: API contract per HANDOFF section 2.5
    try:
        sel_rows = sel_event.selection.rows
    except (AttributeError, TypeError):
        sel_rows = []

    if sel_rows:
        sel_ma = disp.iloc[int(sel_rows[0])]["Mã Phiếu"]
        st.session_state["kk_manage_selected"] = sel_ma

    sel_ma = st.session_state.get("kk_manage_selected")
    if sel_ma and (df["ma_phieu_kk"] == sel_ma).any():
        row = df[df["ma_phieu_kk"] == sel_ma].iloc[0]
        _render_detail_panel(sel_ma, row)
    else:
        st.html(detail_empty_html())


def _render_detail_panel(ma_phieu: str, header_row) -> None:
    """Detail panel cho phiếu được chọn — header + actions + KPIs + bảng."""
    status = str(header_row.get("trang_thai", "") or "")

    # Header
    st.html(detail_header_html(
        ma_phieu=ma_phieu,
        chi_nhanh=str(header_row.get("chi_nhanh", "") or ""),
        nhom_cha=str(header_row.get("nhom_cha", "") or ""),
        created_by=str(header_row.get("created_by", "") or ""),
        created_at_str=_fmt_phieu_date(header_row.get("created_at")),
        status=status,
    ))

    try:
        lines = _kk_get_lines(ma_phieu)
    except Exception as e:
        st.error(f"Lỗi tải chi tiết phiếu: {e}")
        return

    if lines.empty:
        st.info("Phiếu này chưa có dữ liệu chi tiết.")
        return

    # ── Action buttons theo status ─────────────────────────────────────────
    a1, a2, a3 = st.columns([1.5, 1.3, 1.3])
    if status == "Đang kiểm":
        with a1:
            if st.button("▶ Quét tiếp phiếu này", type="primary",
                         use_container_width=True, key=f"go_{ma_phieu}"):
                st.session_state["kk_active_ma"] = ma_phieu
                st.toast(
                    f"Đã chọn {ma_phieu}. Bấm tab **Quét kiểm kê** phía trên ↑",
                    icon="✨",
                )
        with a2:
            if st.button("🗑 Hủy phiếu", use_container_width=True,
                         key=f"cancel_mgr_{ma_phieu}"):
                ok, msg = _kk_cancel_phieu(ma_phieu)
                if ok:
                    st.session_state.pop("kk_manage_selected", None)
                    load_phieu_kiem_ke.clear()
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    elif status == "Chờ duyệt admin":
        if is_admin():
            with a1:
                if st.button("✓ Duyệt & chốt phiếu", type="primary",
                             use_container_width=True, key=f"approve_{ma_phieu}"):
                    ok, msg = _kk_approve(ma_phieu)
                    if ok:
                        load_phieu_kiem_ke.clear()
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            with a2:
                if st.button("🗑 Hủy phiếu", use_container_width=True,
                             key=f"cancel_mgr_{ma_phieu}"):
                    ok, msg = _kk_cancel_phieu(ma_phieu)
                    if ok:
                        st.session_state.pop("kk_manage_selected", None)
                        load_phieu_kiem_ke.clear()
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        else:
            st.info("Chỉ admin mới có quyền duyệt phiếu kiểm kê.")
    elif status == "Đã duyệt":
        with a1:
            _excel_download_button(lines, ma_phieu, key=f"dl_mgr_{ma_phieu}")

    # ── KPI tiles + detail table ───────────────────────────────────────────
    lines["Lệch"] = lines["sl_thuc_te"] - lines["ton_snapshot"]

    if status == "Chờ duyệt admin":
        gia_map = get_gia_ban_map()
        lines["_gia"] = lines["ma_hang"].astype(str).map(gia_map).fillna(0).astype(int)
        lines["_gt_thuc_te"] = lines["sl_thuc_te"] * lines["_gia"]
        lines["_gt_lech"] = lines["Lệch"] * lines["_gia"]
        tong_thuc_te_sl = int(lines["sl_thuc_te"].sum())
        tong_thuc_te_gt = int(lines["_gt_thuc_te"].sum())
        lech_tang = lines[lines["Lệch"] > 0]
        lech_giam = lines[lines["Lệch"] < 0]
        tong_tang_sl = int(lech_tang["Lệch"].sum())
        tong_tang_gt = int(lech_tang["_gt_lech"].sum())
        tong_giam_sl = int(lech_giam["Lệch"].sum())
        tong_giam_gt = int(lech_giam["_gt_lech"].sum())
        tong_lech_sl = tong_tang_sl + tong_giam_sl
        tong_lech_gt = tong_tang_gt + tong_giam_gt
        st.html(kpi_tiles_waiting_html(
            tong_thuc_te_sl, tong_thuc_te_gt,
            tong_tang_sl, tong_tang_gt,
            tong_giam_sl, tong_giam_gt,
            tong_lech_sl, tong_lech_gt,
        ))
    else:
        st.html(kpi_tiles_scanning_html(
            tong_ton=int(lines["ton_snapshot"].sum()),
            tong_quet=int(lines["sl_thuc_te"].sum()),
            tong_lech=int(lines["Lệch"].sum()),
        ))

    detail = lines.rename(columns={
        "ma_hang": "Mã Hàng", "ten_hang": "Tên Hàng",
        "ton_snapshot": "Tồn Kho", "sl_thuc_te": "SL Thực Tế",
        "sl_quet": "SL Quét",
    })
    dcols = ["Mã Hàng", "Tên Hàng", "Tồn Kho", "SL Quét", "SL Thực Tế", "Lệch"]
    if status == "Chờ duyệt admin":
        detail["Giá trị lệch"] = lines["_gt_lech"]
        dcols.append("Giá trị lệch")
    dcols = [c for c in dcols if c in detail.columns]
    st.markdown("")
    st.dataframe(detail[dcols], use_container_width=True,
                 hide_index=True, height=320)


# ═══════════════════════════════════════════════════════════════════════════
# Module entry
# ═══════════════════════════════════════════════════════════════════════════

def module_kiem_ke():
    inject_kiem_ke_css()
    inject_audio_unlock_js()

    st.markdown("### 🧮 Kiểm kê")
    st.caption("v2 redesign — quét nhanh, quản lý gọn.")

    active = get_active_branch()
    accessible = get_accessible_branches()

    tab_scan, tab_manage = st.tabs(["Quét kiểm kê", "Quản lý phiếu"])

    with tab_scan:
        _render_tab_scan(active, accessible)

    with tab_manage:
        _render_tab_manage(active, accessible)

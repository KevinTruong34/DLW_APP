import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np
import html as _html_esc

from utils.helpers import _normalize, now_vn, now_vn_iso, today_vn, fmt_vn
from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches

from utils.helpers import _build_phieu_html, _in_phieu_sc


# ══════════════════════════════════════════════════════════
# Helper: phân loại SP cho phép sửa giá khi bán (SPK/DVPS)
# ══════════════════════════════════════════════════════════
def _is_open_price_row(row) -> bool:
    """True nếu row hang_hoa là open-price (đọc thẳng flag is_open_price)."""
    return bool(row.get("is_open_price", False))


# ══════════════════════════════════════════════════════════
# CSS scoped — chỉ apply cho module Sửa chữa
# ══════════════════════════════════════════════════════════
_SC_CSS = """
<style>
/* ═══════════════════════════════════════════════════════════
   SỬA CHỮA — design tokens + Streamlit overrides + components
   Pixel-faithful port từ prototype "Sửa chữa - Danh sách phiếu.html"
   (handoff README §"Design Tokens"). Tokens tại :root để cả global
   selectors như [data-testid="stButton"] đều dùng được.
   ═══════════════════════════════════════════════════════════ */

@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

:root {
    --sc-bg: #faf9f6;
    --sc-surface: #ffffff;
    --sc-surface-2: #f5f3ee;
    --sc-ink: #1a1815;
    --sc-ink-2: #4a463e;
    --sc-ink-3: #8a8478;
    --sc-line: #e8e5dd;
    --sc-line-2: #efece4;
    --sc-accent: oklch(0.56 0.11 165);
    --sc-accent-hover: oklch(0.51 0.11 165);
    --sc-accent-soft: oklch(0.96 0.025 165);
    --sc-accent-line: oklch(0.85 0.06 165);
    --sc-emerald-ink: oklch(0.4 0.11 165);
    --sc-amber: oklch(0.7 0.13 75);
    --sc-amber-soft: oklch(0.96 0.04 80);
    --sc-amber-ink: oklch(0.45 0.13 75);
    --sc-rose: oklch(0.62 0.16 22);
    --sc-rose-soft: oklch(0.97 0.03 22);
    --sc-rose-ink: oklch(0.5 0.16 22);
    --sc-indigo: oklch(0.55 0.13 260);
    --sc-indigo-soft: oklch(0.96 0.025 260);
    --sc-indigo-ink: oklch(0.4 0.13 260);
}

/* Body warm bg + font.
   Set font CHỈ trên .stApp — children tự inherit. Icon containers
   (Material Symbols / Material Icons) có font-family riêng tự override
   inheritance, nên ligature "expand_more" render đúng thành icon. */
.stApp { background: var(--sc-bg); font-family: 'Be Vietnam Pro', system-ui, -apple-system, sans-serif; }
/* Restore icon fonts nếu bị global override khác trộn vào */
[class*="material-symbols"], [class*="material-icons"],
.material-symbols-outlined, .material-symbols-rounded, .material-icons {
    font-family: 'Material Symbols Outlined', 'Material Icons' !important;
}
.sc-mono { font-family: 'DM Mono', ui-monospace, monospace; font-feature-settings: 'tnum'; }
.sc-num  { font-variant-numeric: tabular-nums; }

/* ───── Streamlit BUTTON override (global — PR3 critical fix) ───── */
[data-testid="stButton"] > button,
[data-testid="baseButton-secondary"],
[data-testid="baseButton-primary"] {
    height: 34px !important;
    padding: 0 14px !important;
    border-radius: 8px !important;
    border: 1px solid var(--sc-line) !important;
    background: var(--sc-surface) !important;
    color: var(--sc-ink) !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    transition: background .12s, border-color .12s, color .12s !important;
    box-shadow: none !important;
}
[data-testid="stButton"] > button:hover,
[data-testid="baseButton-secondary"]:hover {
    background: var(--sc-surface-2) !important;
    border-color: var(--sc-line) !important;
    color: var(--sc-ink) !important;
}
[data-testid="stButton"] > button[kind="primary"],
[data-testid="baseButton-primary"] {
    background: var(--sc-accent) !important;
    border-color: var(--sc-accent) !important;
    color: #fff !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover,
[data-testid="baseButton-primary"]:hover {
    background: var(--sc-accent-hover) !important;
    border-color: var(--sc-accent-hover) !important;
    color: #fff !important;
}
[data-testid="stButton"] > button:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
}

/* ───── Streamlit INPUT / SELECTBOX overrides ───── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input {
    border-radius: 8px !important;
    border: 1px solid var(--sc-line) !important;
    background: var(--sc-surface) !important;
    color: var(--sc-ink) !important;
    font-size: 13px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stDateInput"] input:focus {
    border-color: var(--sc-accent) !important;
    box-shadow: 0 0 0 3px var(--sc-accent-soft) !important;
}
[data-testid="stSelectbox"] > div > div {
    border-radius: 8px !important;
    border-color: var(--sc-line) !important;
    background: var(--sc-surface) !important;
    min-height: 34px !important;
}

/* ───── Tabs (st.tabs) ───── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid var(--sc-line);
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    font-size: 12.5px;
    font-weight: 500;
    color: var(--sc-ink-3);
    padding: 8px 14px;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: var(--sc-accent) !important;
    border-bottom-color: var(--sc-accent) !important;
}

/* ═══════════════ STATUS PILLS ═══════════════ */
.sc-pill {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11.5px; font-weight: 500;
    padding: 3px 9px; border-radius: 999px;
    background: var(--sc-surface-2); color: var(--sc-ink-2);
    border: 1px solid var(--sc-line);
}
.sc-pill::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--sc-ink-3); }
.sc-pill.done { background: var(--sc-accent-soft); color: var(--sc-emerald-ink); border-color: var(--sc-accent-line); }
.sc-pill.done::before { background: var(--sc-accent); }
.sc-pill.fixing { background: var(--sc-amber-soft); color: var(--sc-amber-ink); border-color: oklch(0.85 0.06 80); }
.sc-pill.fixing::before { background: var(--sc-amber); }
.sc-pill.waiting { background: var(--sc-indigo-soft); color: var(--sc-indigo-ink); border-color: oklch(0.85 0.06 260); }
.sc-pill.waiting::before { background: var(--sc-indigo); }
.sc-pill.handover { background: var(--sc-amber-soft); color: var(--sc-amber-ink); border-color: oklch(0.85 0.06 80); }
.sc-pill.handover::before { background: var(--sc-amber); }
.sc-pill.cancelled { background: var(--sc-rose-soft); color: var(--sc-rose-ink); border-color: oklch(0.85 0.06 22); }
.sc-pill.cancelled::before { background: var(--sc-rose); }

/* TABLE CARD CSS đã remove ở PR4 (revert HTML table → st.dataframe ở hotfix) */

/* Empty state */
.sc-empty { padding: 48px 24px; text-align: center; color: var(--sc-ink-3); font-size: 13px;
    background: var(--sc-surface); border: 1px solid var(--sc-line); border-radius: 12px; }
.sc-empty-title { color: var(--sc-ink-2); font-weight: 500; margin-bottom: 4px; font-size: 14px; }

/* ═══════════════ DRAWER CARDS (detail + create/edit) ═══════════════ */
.sc-drawer-head { padding: 14px 16px; border-bottom: 1px solid var(--sc-line); background: var(--sc-surface); border-radius: 10px 10px 0 0; }
.sc-drawer-head .small { font-size: 11px; color: var(--sc-ink-3); letter-spacing: 0.04em; text-transform: uppercase; margin-bottom: 4px; }
.sc-drawer-head h2 { margin: 0; font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sc-drawer-head h2 .id { font-family: 'DM Mono', monospace; font-size: 17px; color: var(--sc-ink); font-weight: 700; letter-spacing: 0.02em; margin-right: 4px; }
.sc-drawer-head .meta { margin-top: 6px; font-size: 12.5px; color: var(--sc-ink-2); display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }

.sc-d-card { background: var(--sc-surface); border: 1px solid var(--sc-line); border-radius: 10px; padding: 12px 14px; }
.sc-d-card + .sc-d-card { margin-top: 10px; }
.sc-d-card-title { font-size: 11.5px; font-weight: 600; color: var(--sc-ink-2); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; display: flex; gap: 6px; align-items: center; }

.sc-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 14px; }
.sc-info-grid .full { grid-column: 1 / -1; }
.sc-info-row { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.sc-info-row .lab { font-size: 11px; color: var(--sc-ink-3); letter-spacing: 0.02em; }
.sc-info-row .val { font-size: 13px; color: var(--sc-ink); font-weight: 500; word-break: break-word; }
.sc-info-row .val.dim { color: var(--sc-ink-3); font-weight: 400; }

.sc-desc-block { font-size: 13px; color: var(--sc-ink); line-height: 1.55; white-space: pre-wrap; }
.sc-desc-note { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--sc-line); font-size: 12.5px; color: var(--sc-ink-2); }
.sc-desc-note .lab { font-size: 11px; color: var(--sc-ink-3); margin-bottom: 2px; letter-spacing: 0.02em; }

/* Items mini-table */
.sc-items { width: 100%; border-collapse: collapse; }
.sc-items th { background: transparent; padding: 6px 8px; font-size: 10.5px; color: var(--sc-ink-3); font-weight: 500; text-align: left; letter-spacing: 0.02em; }
.sc-items th.right, .sc-items td.right { text-align: right; }
.sc-items td { padding: 7px 8px; font-size: 12.5px; border-bottom: 1px solid var(--sc-line-2); vertical-align: top; }
.sc-items tr:last-child td { border-bottom: none; }
.sc-items td.tnum { font-variant-numeric: tabular-nums; }
.sc-items td.bold { font-weight: 600; }
.sc-items .ma { font-family: 'DM Mono', monospace; color: var(--sc-ink-3); font-size: 11.5px; }
.sc-kind-tag { display: inline-block; padding: 1px 7px; border-radius: 4px; font-size: 10.5px; background: var(--sc-surface-2); color: var(--sc-ink-3); border: 1px solid var(--sc-line); }
.sc-kind-tag.dv { background: var(--sc-accent-soft); color: var(--sc-emerald-ink); border-color: var(--sc-accent-line); }

/* Money cards */
.sc-money-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 10px; }
.sc-money-mini { padding: 10px 12px; border-radius: 8px; background: var(--sc-surface-2); border: 1px solid var(--sc-line); text-align: center; }
.sc-money-mini .mlab { font-size: 10.5px; color: var(--sc-ink-3); margin-bottom: 3px; letter-spacing: 0.02em; text-transform: uppercase; }
.sc-money-mini .mval { font-size: 15px; font-weight: 600; color: var(--sc-ink); font-variant-numeric: tabular-nums; }
.sc-money-mini.danger { background: var(--sc-rose-soft); border-color: oklch(0.85 0.06 22); }
.sc-money-mini.danger .mval { color: var(--sc-rose-ink); }
.sc-money-mini.success { background: var(--sc-accent-soft); border-color: var(--sc-accent-line); }
.sc-money-mini.success .mval { color: var(--sc-emerald-ink); }

/* APSC card */
.sc-apsc-card { margin-top: 10px; padding: 12px 14px; border-radius: 10px;
    background: linear-gradient(135deg, var(--sc-accent-soft), var(--sc-surface));
    border: 1px solid var(--sc-accent-line); }
.sc-apsc-card.cancelled { background: var(--sc-rose-soft); border-color: oklch(0.85 0.06 22); }
.sc-apsc-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.sc-apsc-info .apsc-lab { font-size: 11px; color: var(--sc-ink-3); margin-bottom: 2px; letter-spacing: 0.02em; text-transform: uppercase; }
.sc-apsc-info .apsc-id { font-family: 'DM Mono', monospace; font-size: 14px; font-weight: 600; color: var(--sc-emerald-ink); }
.sc-apsc-card.cancelled .sc-apsc-info .apsc-id { color: var(--sc-rose-ink); text-decoration: line-through; }
.sc-apsc-info .apsc-meta { font-size: 11.5px; color: var(--sc-ink-2); margin-top: 2px; }

/* Empty items state */
.sc-empty-items { font-size: 12.5px; color: var(--sc-ink-3); padding: 12px 0; text-align: center; font-style: italic; }

/* Form section title (PR2 — Create drawer) */
.sc-form-section-title {
    font-size: 11.5px; font-weight: 600;
    color: var(--sc-ink-2); text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 14px 0 6px;
    padding-bottom: 5px;
    border-bottom: 1px solid var(--sc-line-2);
    display: flex; align-items: center; gap: 6px;
}

/* LEGACY classes (sc-card, sc-badge, sc-section-title, sc-money-card,
   sc-info-label, sc-info-val) đã remove ở PR4 cleanup khi tab_create
   /tab_detail/tab_hoadon bị bỏ. */
</style>
"""


def module_sua_chua():
    st.markdown(_SC_CSS, unsafe_allow_html=True)

    # ── Header ──
    st.markdown(
        "<div style='display:flex;align-items:center;justify-content:space-between;"
        "margin-bottom:16px;'>"
        "<div>"
        "<div style='font-size:1.4rem;font-weight:700;color:#1a1a2e;'>🔧 Sửa chữa</div>"
        "<div style='font-size:0.82rem;color:#888;'>Tạo và quản lý phiếu sửa chữa</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True
    )

    active = get_active_branch()
    accessible = get_accessible_branches()
    user = get_user() or {}
    ho_ten = user.get("ho_ten", user.get("username", ""))

    # PR4 cleanup: bỏ st.tabs([4 tabs]) — tất cả flow đã chuyển sang
    # drawer/dialog trong tab_list. tab_create/detail/hoadon legacy
    # đã remove, chỉ render content của tab_list duy nhất.

    # ══════════════════════════════════════════════════════════
    # HELPERS — giữ nguyên 100% logic
    # ══════════════════════════════════════════════════════════
    @st.cache_data(ttl=60)
    def _load_phieu(branches_key: tuple) -> pd.DataFrame:
        try:
            res = supabase.table("phieu_sua_chua").select("*") \
                .in_("chi_nhanh", list(branches_key)) \
                .order("created_at", desc=True).execute()
            if not res.data: return pd.DataFrame()
            df = pd.DataFrame(res.data)
            if "ngay_tiep_nhan" in df.columns:
                df["_ngay"] = (pd.to_datetime(df["ngay_tiep_nhan"], utc=True,
                                              format="ISO8601",
                                              errors="coerce")
                               .dt.tz_convert("Asia/Ho_Chi_Minh"))
                df["Ngày TN"] = df["_ngay"].dt.strftime("%d/%m/%Y %H:%M")
            return df
        except Exception as e:
            st.error(f"Lỗi tải phiếu: {e}"); return pd.DataFrame()

    def _load_chi_tiet(ma_phieu: str) -> pd.DataFrame:
        try:
            res = supabase.table("phieu_sua_chua_chi_tiet").select("*") \
                .eq("ma_phieu", ma_phieu).execute()
            if not res.data: return pd.DataFrame()
            df = pd.DataFrame(res.data)
            for col in ["so_luong", "don_gia"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            return df
        except Exception: return pd.DataFrame()

    def _sc_match_ma(ma_phieu, query: str) -> bool:
        """Match phiếu sửa chữa: substring (paste full / partial) OR numeric suffix
        (digit-only query, vd '1' → SC000001 / '405' → SC000405).
        """
        ma_l = str(ma_phieu).strip().lower()
        q = (query or "").strip().lower()
        if not q:
            return True
        if q in ma_l:
            return True
        if q.isdigit() and ma_l.startswith("sc"):
            try:
                return str(int(str(ma_phieu)[2:])).endswith(q)
            except (ValueError, TypeError):
                pass
        return False


    def _gen_ma_phieu() -> str:
        try:
            res = supabase.rpc("next_sc_seq", {}).execute()
            data = res.data
            if isinstance(data, list):
                num = int(data[0]) if data else 1
            elif data is not None:
                num = int(data)
            else:
                num = 1
            return f"SC{num:06d}"
        except Exception:
            return f"SC{datetime.now().strftime('%y%m%d%H%M')}"

    def _preview_next_ma_phieu() -> str:
        """Mã phiếu DỰ KIẾN — đọc max+1 từ DB, KHÔNG advance sc_seq.
        Tránh drift sequence khi user mở tab nhiều lần (mỗi rerun không consume seq).
        Số thực sẽ lấy từ nextval('sc_seq') khi submit (qua _gen_ma_phieu).
        """
        try:
            res = (
                supabase.table("phieu_sua_chua")
                .select("ma_phieu")
                .like("ma_phieu", "SC______")
                .order("ma_phieu", desc=True)
                .limit(1)
                .execute()
            )
            num = int(res.data[0]["ma_phieu"][2:]) + 1 if res.data else 1
            return f"SC{num:06d}"
        except Exception:
            return "SC??????"

    def _gen_ma_apsc() -> str:
        try:
            res = supabase.rpc("get_next_apsc_num", {}).execute()
            data = res.data
            if isinstance(data, list):
                num = int(data[0]) if data else 1
            elif data is not None:
                num = int(data)
            else:
                num = 1
            return f"APSC{num:06d}"
        except Exception:
            return f"APSC{(now_vn()).strftime('%y%m%d%H%M')}"

    def _preview_next_ma_apsc() -> str:
        """Mã APSC dự kiến (max+1 từ hoa_don) — KHÔNG advance get_next_apsc_num
        để tránh drift sequence khi user chỉ open dialog rồi đóng. Mã thực
        sẽ lấy từ _gen_ma_apsc() khi submit."""
        try:
            res = (
                supabase.table("hoa_don")
                .select('"Mã hóa đơn"')
                .like('"Mã hóa đơn"', "APSC______")
                .order('"Mã hóa đơn"', desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                last = res.data[0]["Mã hóa đơn"]
                num = int(str(last)[4:]) + 1
            else:
                num = 1
            return f"APSC{num:06d}"
        except Exception:
            return "APSC??????"

    def _tao_hoa_don_apsc(phieu: dict, ct: pd.DataFrame,
                           giam_gia: int, pttt: dict) -> str:
        ma_hd = _gen_ma_apsc()
        now_dt = now_vn()
        now_str = now_dt.strftime("%d/%m/%Y %H:%M:%S")
        tong = int((ct["so_luong"] * ct["don_gia"]).sum()) if not ct.empty else 0
        can_tra = max(0, tong - giam_gia - int(phieu.get("khach_tra_truoc", 0)))
        rows = []
        base = {
            "Mã hóa đơn": ma_hd, "Chi nhánh": phieu.get("chi_nhanh",""),
            "Mã YCSC": phieu.get("ma_phieu", ""),
            "Thời gian": now_str, "Thời gian tạo": now_str,
            "Tên khách hàng": phieu.get("ten_khach",""),
            "Điện thoại": phieu.get("sdt_khach",""),
            "Trạng thái": "Hoàn thành", "Người bán": ho_ten,
            "Tổng tiền hàng": tong, "Giảm giá hóa đơn": giam_gia,
            "Khách cần trả": can_tra, "Khách đã trả": can_tra,
            "Tiền mặt": pttt.get("tien_mat", 0),
            "Chuyển khoản": pttt.get("chuyen_khoan", 0),
            "Thẻ": pttt.get("the", 0),
            "Ví": 0, "Điểm": 0, "Còn cần thu (COD)": 0,
            "Kênh bán": "Tại quầy", "Ghi chú": phieu.get("mo_ta_loi",""),
        }
        if ct.empty:
            rows.append(base)
        else:
            for _, r in ct.iterrows():
                tt = int(r["so_luong"]) * int(r["don_gia"])
                row = {**base,
                    "Mã hàng": str(r.get("ma_hang") or ""),
                    "Mã vạch": str(r.get("ma_hang") or ""),
                    "Tên hàng": str(r.get("ten_hang","")),
                    "Số lượng": int(r["so_luong"]),
                    "Đơn giá": int(r["don_gia"]),
                    "Thành tiền": tt, "Giá bán": int(r["don_gia"]),
                    "Giảm giá %": 0, "Giảm giá": 0,
                }
                rows.append(row)
        supabase.table("hoa_don").insert(rows).execute()

        # === ENQUEUE PRINT (PATCH) ===
        try:
            from utils.print_queue_apsc import enqueue_apsc
            pr = enqueue_apsc(ma_hd, ho_ten or "")
            if pr.get("ok"):
                st.toast("🖨 Đã gửi lệnh in HĐ APSC", icon="🖨")
            else:
                st.toast(f"⚠️ {pr.get('error', 'Lỗi in')}", icon="⚠️")
        except Exception as e:
            st.toast(f"⚠️ Lỗi in: {e}", icon="⚠️")
        # === END PATCH ===

        # Trừ kho atomic cho linh kiện thật (skip dịch vụ + items không có trong hang_hoa).
        # RPC tru_kho_apsc tự skip items không phải Hàng hóa hoặc open-price.
        try:
            items_kho = []
            if not ct.empty:
                for _, r in ct.iterrows():
                    ma = str(r.get("ma_hang") or "").strip()
                    sl = int(r.get("so_luong") or 0)
                    if ma and sl > 0:
                        items_kho.append({"ma_hang": ma, "so_luong": sl})
            if items_kho:
                kho_res = supabase.rpc("tru_kho_apsc", {
                    "p_ma_hd":     ma_hd,
                    "p_chi_nhanh": phieu.get("chi_nhanh", ""),
                    "p_items":     items_kho,
                    "p_nguoi_ban": ho_ten,
                }).execute()
                kho_data = kho_res.data if isinstance(kho_res.data, dict) else (kho_res.data or {})
                if not kho_data.get("ok"):
                    st.warning(
                        f"⚠️ HĐ {ma_hd} đã tạo nhưng kho linh kiện chưa trừ: "
                        f"{kho_data.get('error', '?')}. Liên hệ admin xử lý thủ công."
                    )
        except Exception as e:
            st.warning(
                f"⚠️ HĐ {ma_hd} đã tạo nhưng RPC trừ kho lỗi: {e}. "
                f"Liên hệ admin xử lý thủ công."
            )

        return ma_hd

    TRANG_THAI_LIST = ["Đang sửa", "Chờ linh kiện", "Chờ giao khách"]
    LOAI_YC_LIST   = ["Sửa chữa", "Bảo hành"]
    LOAI_DONG_LIST = ["Dịch vụ", "Linh kiện"]

    def _badge_status_html(tt: str) -> str:
        """Trả về badge HTML cho trạng thái."""
        cls = "sc-badge"
        if tt == "Hoàn thành":
            cls += " sc-badge-green"
        elif tt == "Chờ giao khách":
            pass  # vàng default
        else:
            cls += " sc-badge-red"
        return f'<span class="{cls}">{tt}</span>'

    def _widget_them_dv(key_prefix: str, items_key: str):
        hh = load_hang_hoa()
        ma_tim = st.text_input("🔍 Tìm mã / tên hàng hóa:", key=f"{key_prefix}_ma_tim",
                                placeholder="VD: PDH, pin, lau dầu...")
        hits = pd.DataFrame()
        if ma_tim.strip() and not hh.empty:
            s = ma_tim.strip().lower()
            s_nospace = s.replace(" ", "")
            def _fuzzy(val):
                v = str(val).lower()
                return s in v or s_nospace in v.replace(" ", "")
            mask = (hh["ma_hang"].apply(_fuzzy) | hh["ten_hang"].apply(_fuzzy))
            hits = hh[mask].head(8)

        if not hits.empty:
            for _, row in hits.iterrows():
                gia_def = int(row.get("gia_ban", 0))
                is_open = _is_open_price_row(row)

                if is_open:
                    label = f"✏️ {row['ma_hang']} — {row['ten_hang']}"
                    col_lbl, col_sl, col_gia, col_btn = st.columns([4, 1, 2, 1])
                else:
                    label = f"{row['ma_hang']} — {row['ten_hang']}  |  {gia_def:,}đ".replace(",", ".")
                    col_lbl, col_sl, col_btn = st.columns([5, 1, 1])

                with col_lbl:
                    st.markdown(f"<span style='font-size:0.9rem'>{label}</span>",
                                unsafe_allow_html=True)
                with col_sl:
                    sl = st.number_input("SL", min_value=1, value=1,
                                          key=f"{key_prefix}_sl_{row['ma_hang']}",
                                          label_visibility="collapsed")

                if is_open:
                    with col_gia:
                        gia_input = st.number_input(
                            "Giá", min_value=0, value=gia_def, step=10000,
                            key=f"{key_prefix}_gia_{row['ma_hang']}",
                            label_visibility="collapsed",
                        )
                else:
                    gia_input = gia_def

                with col_btn:
                    can_add = (not is_open) or (gia_input > 0)
                    if st.button("➕", key=f"{key_prefix}_add_{row['ma_hang']}",
                                  disabled=not can_add):
                        st.session_state.setdefault(items_key, []).append({
                            "loai_dong": "Dịch vụ",
                            "ten_hang":  str(row["ten_hang"]),
                            "ma_hang":   str(row["ma_hang"]),
                            "so_luong":  int(sl),
                            "don_gia":   int(gia_input),
                        })
                        st.rerun()
        elif ma_tim.strip():
            st.caption("Không tìm thấy — có thể nhập tay bên dưới:")
            ca, cb, cc, cd = st.columns([3, 1, 2, 1])
            with ca: ten_tay = st.text_input("Tên:", key=f"{key_prefix}_tay_ten")
            with cb: sl_tay  = st.number_input("SL:", min_value=1, value=1, key=f"{key_prefix}_tay_sl")
            with cc: gia_tay = st.number_input("Đơn giá:", min_value=0, step=10000,
                                                value=0, key=f"{key_prefix}_tay_gia")
            with cd:
                st.write("")
                if st.button("➕", key=f"{key_prefix}_tay_add") and ten_tay.strip():
                    st.session_state.setdefault(items_key, []).append({
                        "loai_dong": "Dịch vụ", "ten_hang": ten_tay.strip(),
                        "ma_hang": None, "so_luong": sl_tay, "don_gia": gia_tay,
                    })
                    st.rerun()

    def _hien_thi_items(items_key: str):
        items = st.session_state.get(items_key, [])
        if not items:
            st.caption("_(Chưa có mục nào)_")
            return
        for i, item in enumerate(items):
            ci1, ci2, ci3, ci4, ci5 = st.columns([2, 4, 1, 2, 1])
            with ci1: st.markdown(f"<span style='font-size:0.9rem'>{item.get('loai_dong','')}</span>", unsafe_allow_html=True)
            with ci2: st.markdown(f"<span style='font-size:0.9rem'>{item.get('ten_hang','')}</span>", unsafe_allow_html=True)
            with ci3: st.markdown(f"<span style='font-size:0.9rem'>x{item.get('so_luong',1)}</span>", unsafe_allow_html=True)
            with ci4: st.markdown(f"<span style='font-size:0.9rem'>{item.get('don_gia',0):,}đ</span>".replace(",","."), unsafe_allow_html=True)
            with ci5:
                if st.button("✕", key=f"del_{items_key}_{i}"):
                    st.session_state[items_key].pop(i); st.rerun()

    # ══════════════════════════════════════════════════════════
    # PR2 — Create drawer (render trong col_drawer khi sc_form_mode=create)
    # ══════════════════════════════════════════════════════════
    def _render_create_drawer(cn_default, accessible, is_multi_branch,
                              ho_ten, user, fmt_money, close_drawer):
        """Form tạo phiếu sửa chữa mới — port từ tab_create vào drawer
        column. Logic submit + log_action + cache clear giữ nguyên 100%
        khớp tab_create để đảm bảo backward compat (tab_create vẫn
        functional song song trong PR2).
        """
        fcnt = st.session_state.setdefault("sc_drawer_form_count", 0)
        ma_du_kien = _preview_next_ma_phieu()

        # ── Header drawer ──
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown(
                f'<div class="sc-root"><div class="sc-drawer-head">'
                f'<div class="small">PHIẾU SỬA CHỮA MỚI</div>'
                f'<h2><span class="id sc-mono">{ma_du_kien}</span></h2>'
                f'<div class="meta" style="font-size:11px;color:var(--sc-ink-3);">'
                f'Mã thực sẽ cấp khi lưu</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        with head_r:
            if st.button("✕", key=f"sc_drawer_create_close_{fcnt}",
                         help="Đóng (huỷ form)",
                         use_container_width=True):
                close_drawer()
                st.rerun()

        # ── Section 1: Khách hàng ──
        st.markdown(
            '<div class="sc-root"><div class="sc-form-section-title">'
            '👤 THÔNG TIN KHÁCH HÀNG</div></div>',
            unsafe_allow_html=True,
        )
        sc1, sc2 = st.columns(2)
        with sc1:
            sdt_khach = st.text_input(
                "Số điện thoại *", key=f"sc_drawer_sdt_{fcnt}",
                placeholder="0xxx xxx xxx",
            )
            sdt_prev_key = f"sc_drawer_sdt_prev_{fcnt}"
            ten_key      = f"sc_drawer_ten_{fcnt}"
            kh_key       = f"sc_drawer_kh_found_{fcnt}"
            if sdt_khach.strip() != st.session_state.get(sdt_prev_key, ""):
                st.session_state[sdt_prev_key] = sdt_khach.strip()
                kh_found = lookup_khach_hang(sdt_khach) if sdt_khach.strip() else None
                st.session_state[kh_key] = kh_found
                st.session_state[ten_key] = kh_found["ten_kh"] if kh_found else ""
                st.rerun()
            kh_found = st.session_state.get(kh_key)
            if sdt_khach.strip() and not kh_found:
                st.caption("⚠️ SĐT chưa có — khách mới sẽ được lưu tự động")
            elif kh_found:
                st.caption(f"✓ Khách cũ: **{kh_found['ten_kh']}**")
        with sc2:
            ten_khach = st.text_input("Tên khách hàng *", key=ten_key)

        # Chi nhánh
        if is_multi_branch:
            cn_create = st.selectbox(
                "Chi nhánh tiếp nhận", accessible,
                index=accessible.index(cn_default) if cn_default in accessible else 0,
                key=f"sc_drawer_cn_{fcnt}",
            )
        else:
            cn_create = cn_default
            st.caption(f"📍 Chi nhánh: **{cn_create}**")

        # ── Section 2: Đồng hồ ──
        st.markdown(
            '<div class="sc-root"><div class="sc-form-section-title">'
            '⌚ THÔNG TIN ĐỒNG HỒ</div></div>',
            unsafe_allow_html=True,
        )
        dc1, dc2 = st.columns(2)
        with dc1:
            hieu_dh = st.text_input(
                "Hiệu đồng hồ", key=f"sc_drawer_hieu_{fcnt}",
                placeholder="Casio, Citizen, Seiko...",
            )
            loai_yc = st.selectbox(
                "Loại yêu cầu", LOAI_YC_LIST, key=f"sc_drawer_loai_yc_{fcnt}",
            )
        with dc2:
            dac_diem = st.text_input(
                "Đặc điểm (IMEI / mô tả)", key=f"sc_drawer_dac_{fcnt}",
                placeholder="Số serial, màu sắc, trầy xước...",
            )
            ngay_hen = st.date_input(
                "Ngày hẹn trả", key=f"sc_drawer_hen_{fcnt}",
                value=None, format="DD/MM/YYYY",
            )
        mo_ta = st.text_area(
            "Mô tả lỗi / yêu cầu *", key=f"sc_drawer_mota_{fcnt}",
            placeholder="Mô tả chi tiết tình trạng đồng hồ...",
            height=80,
        )

        # ── Section 3: Thanh toán & Ghi chú ──
        st.markdown(
            '<div class="sc-root"><div class="sc-form-section-title">'
            '💰 THANH TOÁN & GHI CHÚ</div></div>',
            unsafe_allow_html=True,
        )
        tc1, tc2 = st.columns(2)
        with tc1:
            tra_truoc = st.number_input(
                "Khách trả trước (đ)", min_value=0, step=10000,
                key=f"sc_drawer_tra_{fcnt}", value=0,
            )
            if tra_truoc > 0:
                st.caption(f"= {fmt_money(tra_truoc)}")
        with tc2:
            ghi_chu = st.text_area(
                "Ghi chú nội bộ", key=f"sc_drawer_ghichu_{fcnt}",
                placeholder="Thợ kỹ thuật ghi chú...", height=80,
            )

        # ── Section 4: Items ──
        st.markdown(
            '<div class="sc-root"><div class="sc-form-section-title">'
            '🔧 DỊCH VỤ / LINH KIỆN DỰ KIẾN'
            '<span style="font-weight:400;color:var(--sc-ink-3);font-size:10.5px;'
            'text-transform:none;letter-spacing:0;margin-left:8px;">'
            '(có thể bỏ trống — thêm sau khi thợ đánh giá)</span>'
            '</div></div>',
            unsafe_allow_html=True,
        )
        items_key = f"sc_drawer_items_{fcnt}"
        st.session_state.setdefault(items_key, [])
        with st.expander(f"Danh sách ({len(st.session_state[items_key])} mục)",
                          expanded=len(st.session_state[items_key]) > 0):
            _hien_thi_items(items_key)
            st.markdown("---")
            _widget_them_dv(f"sc_drawer_new_{fcnt}", items_key)

        items = st.session_state.get(items_key, [])
        if items:
            tong_du = sum(int(x.get("so_luong", 0)) * int(x.get("don_gia", 0))
                          for x in items)
            st.markdown(
                f'<div class="sc-root"><div class="sc-money-mini danger" '
                f'style="margin-top:10px;">'
                f'<div class="mlab">TỔNG DỰ KIẾN</div>'
                f'<div class="mval">{fmt_money(tong_du)}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

        # ── Footer: Hủy bỏ + Tạo phiếu & In ──
        st.markdown('<hr style="margin:14px 0 10px 0;border-color:#efece4">',
                    unsafe_allow_html=True)
        ft_l, ft_r = st.columns([1, 2])
        with ft_l:
            if st.button("Hủy bỏ", key=f"sc_drawer_cancel_{fcnt}",
                         use_container_width=True):
                close_drawer()
                st.rerun()
        with ft_r:
            can_create = (
                ten_khach.strip() and sdt_khach.strip() and mo_ta.strip()
            )
            if st.button(
                "✅ Tạo phiếu & In", key=f"sc_drawer_submit_{fcnt}",
                type="primary", use_container_width=True,
                disabled=not can_create,
            ):
                try:
                    ma = _gen_ma_phieu()
                    supabase.table("phieu_sua_chua").insert({
                        "ma_phieu": ma, "chi_nhanh": cn_create,
                        "ten_khach": ten_khach.strip(),
                        "sdt_khach": sdt_khach.strip(),
                        "loai_yeu_cau": loai_yc,
                        "hieu_dong_ho": hieu_dh.strip() or None,
                        "dac_diem": dac_diem.strip() or None,
                        "mo_ta_loi": mo_ta.strip(),
                        "khach_tra_truoc": int(tra_truoc),
                        "ghi_chu_noi_bo": ghi_chu.strip() or None,
                        "trang_thai": "Đang sửa",
                        "nguoi_tiep_nhan": ho_ten,
                        "ngay_hen_tra": ngay_hen.isoformat() if ngay_hen else None,
                        "created_by": user.get("username", ""),
                        "created_at": now_vn_iso(),
                        "updated_at": now_vn_iso(),
                    }).execute()
                    if items:
                        supabase.table("phieu_sua_chua_chi_tiet").insert(
                            [{"ma_phieu": ma, **item} for item in items]
                        ).execute()

                    _upsert_khach_hang(
                        ten_khach.strip(), sdt_khach.strip(), cn_create,
                    )

                    # Build print HTML — render sau rerun
                    ct_new = pd.DataFrame(items) if items else pd.DataFrame()
                    if not ct_new.empty:
                        for col in ["so_luong", "don_gia"]:
                            ct_new[col] = pd.to_numeric(
                                ct_new[col], errors="coerce"
                            ).fillna(0).astype(int)
                    phieu_data = {
                        "ma_phieu": ma, "chi_nhanh": cn_create,
                        "ten_khach": ten_khach.strip(),
                        "sdt_khach": sdt_khach.strip(),
                        "hieu_dong_ho": hieu_dh.strip(),
                        "loai_yeu_cau": loai_yc, "dac_diem": dac_diem.strip(),
                        "mo_ta_loi": mo_ta.strip(),
                        "khach_tra_truoc": int(tra_truoc),
                        "ngay_hen_tra": str(ngay_hen) if ngay_hen else None,
                        "nguoi_tiep_nhan": ho_ten,
                        "Ngày TN": now_vn().strftime("%d/%m/%Y %H:%M"),
                    }
                    st.session_state["sc_pending_print_html"] = \
                        _build_phieu_html(phieu_data, ct_new)
                    st.session_state["sc_just_created_ma"] = ma

                    # Đóng drawer + cleanup state + reload data
                    close_drawer()
                    st.cache_data.clear()
                    log_action("SC_CREATE",
                               f"ma={ma} kh={ten_khach} cn={cn_create}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi tạo phiếu: {e}")

    # ══════════════════════════════════════════════════════════
    # PR3b — Edit drawer (render trong col_drawer khi sc_form_mode=edit)
    # Scope match existing tab_detail: update trang_thai + ngay_hen_tra
    # + ghi_chu_noi_bo + add new items (giữ behavior hiện tại, không
    # mở rộng edit sang khách hàng / đồng hồ để tránh đụng audit logic).
    # ══════════════════════════════════════════════════════════
    def _render_edit_drawer(t, ho_ten, fmt_money, close_drawer):
        # Normalize NaN/None → empty string. pd.DataFrame.iloc[0].to_dict()
        # giữ NaN cho object cols → _html_esc.escape(NaN) crash silent
        # giữa render → khúc dưới mất hiển thị (bug PR3b cũ).
        def _v(key, default=""):
            val = t.get(key)
            if val is None:
                return default
            try:
                if isinstance(val, float) and pd.isna(val):
                    return default
            except Exception:
                pass
            return val

        fcnt = st.session_state.setdefault("sc_drawer_form_count", 0)
        ma_pick = str(_v("ma_phieu"))
        cur_tt = str(_v("trang_thai", "Đang sửa")) or "Đang sửa"
        ten_khach = str(_v("ten_khach", "—"))
        sdt_khach = str(_v("sdt_khach", "—"))

        # Map status → pill class (same as detail drawer)
        PILL_CLASS = {
            "Hoàn thành": "done", "Đang sửa": "fixing",
            "Chờ linh kiện": "waiting", "Chờ giao khách": "handover",
        }
        pill_cls = PILL_CLASS.get(cur_tt, "")

        # ── Header drawer (full-width, không nest columns) ──
        st.markdown(
            f'<div class="sc-drawer-head">'
            f'<div class="small">CẬP NHẬT PHIẾU</div>'
            f'<h2><span class="id sc-mono">{_html_esc.escape(ma_pick)}</span>'
            f' · {_html_esc.escape(ten_khach or "—")}</h2>'
            f'<div class="meta">'
            f'<span>📞 {_html_esc.escape(sdt_khach or "—")}</span>'
            f'<span class="sc-pill {pill_cls}">{_html_esc.escape(cur_tt)}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("✕ Đóng (huỷ chỉnh sửa)",
                     key=f"sc_drawer_edit_close_{fcnt}",
                     use_container_width=False):
            # Chỉ pop form_mode để quay về detail view, KHÔNG đóng drawer
            st.session_state.pop("sc_form_mode", None)
            st.session_state["sc_drawer_form_count"] = \
                st.session_state.get("sc_drawer_form_count", 0) + 1
            st.rerun()

        # ── Section: Trạng thái (selectbox đơn giản, không radio horizontal) ──
        st.markdown(
            '<div class="sc-form-section-title">📊 TRẠNG THÁI</div>',
            unsafe_allow_html=True,
        )
        new_tt_idx = (TRANG_THAI_LIST.index(cur_tt)
                      if cur_tt in TRANG_THAI_LIST else 0)
        new_tt = st.selectbox(
            "Trạng thái:", TRANG_THAI_LIST, index=new_tt_idx,
            key=f"sc_drawer_edit_tt_{fcnt}",
            label_visibility="collapsed",
        )
        st.caption("'Hoàn thành' sẽ tự set khi tạo HĐ APSC ở phiếu Chờ giao khách.")

        # ── Section: Hẹn trả + Ghi chú (2-col, single nest) ──
        st.markdown(
            '<div class="sc-form-section-title">💬 GHI CHÚ & HẸN TRẢ</div>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            cur_hen = _v("ngay_hen_tra")
            try:
                hen_value = pd.to_datetime(cur_hen).date() if cur_hen else None
            except Exception:
                hen_value = None
            new_hen = st.date_input(
                "Ngày hẹn trả", value=hen_value,
                key=f"sc_drawer_edit_hen_{fcnt}", format="DD/MM/YYYY",
            )
        with c2:
            new_gc = st.text_area(
                "Ghi chú nội bộ", value=str(_v("ghi_chu_noi_bo")),
                key=f"sc_drawer_edit_gc_{fcnt}", height=80,
            )

        # ── Section: Items hiện có (delete X) + Thêm mới ──
        st.markdown(
            '<div class="sc-form-section-title">'
            '🔧 DỊCH VỤ / LINH KIỆN'
            '</div>',
            unsafe_allow_html=True,
        )
        ct = _load_chi_tiet(ma_pick)
        if not ct.empty:
            for _, row in ct.iterrows():
                ci1, ci2, ci3, ci4, ci5 = st.columns([2, 4, 1, 2, 1])
                with ci1:
                    st.markdown(
                        f"<span style='font-size:0.9rem'>"
                        f"{_html_esc.escape(str(row.get('loai_dong','')))}</span>",
                        unsafe_allow_html=True,
                    )
                with ci2:
                    st.markdown(
                        f"<span style='font-size:0.9rem'>"
                        f"{_html_esc.escape(str(row.get('ten_hang','')))}</span>",
                        unsafe_allow_html=True,
                    )
                with ci3:
                    st.markdown(
                        f"<span style='font-size:0.9rem'>"
                        f"x{int(row.get('so_luong', 1) or 0)}</span>",
                        unsafe_allow_html=True,
                    )
                with ci4:
                    st.markdown(
                        f"<span style='font-size:0.9rem'>"
                        f"{fmt_money(row.get('don_gia', 0))}</span>",
                        unsafe_allow_html=True,
                    )
                with ci5:
                    if st.button("✕", key=f"sc_drawer_del_ct_{fcnt}_{row['id']}"):
                        try:
                            supabase.table("phieu_sua_chua_chi_tiet") \
                                .delete().eq("id", int(row["id"])).execute()
                            st.cache_data.clear()
                            log_action("SC_DEL_ITEM",
                                       f"ma={ma_pick} item={row.get('ten_hang','')}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi xóa: {e}")
        else:
            st.caption("_(Phiếu chưa có dịch vụ / linh kiện nào)_")

        # Thêm mới
        st.markdown(
            '<div style="font-size:11.5px;color:var(--sc-ink-3);'
            'margin:10px 0 4px;">➕ Thêm dịch vụ / linh kiện</div>',
            unsafe_allow_html=True,
        )
        new_items_key = f"sc_drawer_edit_items_{fcnt}"
        st.session_state.setdefault(new_items_key, [])
        _widget_them_dv(f"sc_drawer_edit_new_{fcnt}", new_items_key)
        new_items = st.session_state.get(new_items_key, [])
        if new_items:
            _hien_thi_items(new_items_key)
            tong_moi = sum(int(x.get("so_luong", 0)) * int(x.get("don_gia", 0))
                           for x in new_items)
            st.caption(f"Tổng dịch vụ mới thêm: **{fmt_money(tong_moi)}**")

        # ── Footer: Hủy + Lưu cập nhật ──
        st.markdown('<hr style="margin:14px 0 10px 0;border-color:#efece4">',
                    unsafe_allow_html=True)
        ft_l, ft_r = st.columns([1, 2])
        with ft_l:
            if st.button("Hủy bỏ", key=f"sc_drawer_edit_cancel_{fcnt}",
                         use_container_width=True):
                # Pop form_mode chỉ → quay về detail view (giữ drawer_ma)
                st.session_state.pop("sc_form_mode", None)
                st.session_state["sc_drawer_form_count"] = \
                    st.session_state.get("sc_drawer_form_count", 0) + 1
                st.rerun()
        with ft_r:
            if st.button(
                "💾 Lưu cập nhật", key=f"sc_drawer_edit_submit_{fcnt}",
                type="primary", use_container_width=True,
            ):
                try:
                    supabase.table("phieu_sua_chua").update({
                        "trang_thai":     new_tt,
                        "ngay_hen_tra":   new_hen.isoformat() if new_hen else None,
                        "ghi_chu_noi_bo": (new_gc or "").strip() or None,
                        "updated_at":     now_vn_iso(),
                    }).eq("ma_phieu", ma_pick).execute()

                    if new_items:
                        supabase.table("phieu_sua_chua_chi_tiet").insert(
                            [{"ma_phieu": ma_pick, **item} for item in new_items]
                        ).execute()
                        st.session_state[new_items_key] = []

                    st.cache_data.clear()
                    log_action("SC_UPDATE",
                               f"ma={ma_pick} trang_thai={new_tt}")
                    # Save success → quay về detail view (giữ drawer_ma)
                    st.session_state.pop("sc_form_mode", None)
                    st.session_state["sc_drawer_form_count"] = \
                        st.session_state.get("sc_drawer_form_count", 0) + 1
                    st.toast("✓ Đã cập nhật phiếu", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi cập nhật: {e}")

    # ══════════════════════════════════════════════════════════
    # PR3c — Invoice modal (@st.dialog) — tạo HĐ APSC từ phiếu
    # Chờ giao khách. Trigger từ CTA button trong detail drawer.
    # Persistence: dùng sc_invoice_open flag để dialog re-render qua reruns.
    # ══════════════════════════════════════════════════════════
    @st.dialog("🧾 Tạo hóa đơn APSC", width="large")
    def _invoice_dialog(phieu_dict, ct_df):
        ma_phieu = phieu_dict.get("ma_phieu", "")
        ma_apsc_preview = _preview_next_ma_apsc()

        st.markdown(
            f'<div style="font-size:12.5px;color:var(--sc-ink-3);margin-bottom:8px;">'
            f'Mã dự kiến: <b class="sc-mono" style="color:var(--sc-emerald-ink);">'
            f'{_html_esc.escape(ma_apsc_preview)}</b> · Cho phiếu '
            f'<b class="sc-mono">{_html_esc.escape(ma_phieu)}</b></div>',
            unsafe_allow_html=True,
        )

        # ── Section 1: Items table (read-only) ──
        st.markdown(
            '<div class="sc-form-section-title">📦 CHI TIẾT DỊCH VỤ / LINH KIỆN</div>',
            unsafe_allow_html=True,
        )
        if ct_df.empty:
            st.warning("Phiếu chưa có dịch vụ / linh kiện. Đóng modal, "
                       "thêm items qua nút ✎ Edit, rồi tạo HĐ.")
            tong_hang = 0
        else:
            _items_html = '<table class="sc-items"><thead><tr>' \
                          '<th>Loại</th><th>Tên</th><th>Mã</th>' \
                          '<th class="right">SL</th>' \
                          '<th class="right">Đơn giá</th>' \
                          '<th class="right">Thành tiền</th></tr></thead><tbody>'
            tong_hang = 0
            for _, _r in ct_df.iterrows():
                _sl = int(_r.get("so_luong") or 0)
                _dg = int(_r.get("don_gia") or 0)
                _tt = _sl * _dg
                tong_hang += _tt
                _kind = (_r.get("loai_dong") or "").strip()
                _kind_cls = "dv" if _kind == "Dịch vụ" else ""
                _items_html += (
                    '<tr>'
                    f'<td><span class="sc-kind-tag {_kind_cls}">'
                    f'{_html_esc.escape(_kind or "—")}</span></td>'
                    f'<td>{_html_esc.escape(str(_r.get("ten_hang", "") or "—"))}</td>'
                    f'<td class="ma">{_html_esc.escape(str(_r.get("ma_hang", "") or "—"))}</td>'
                    f'<td class="right tnum">{_sl}</td>'
                    f'<td class="right tnum">{_html_esc.escape(_fmt_money(_dg))}</td>'
                    f'<td class="right tnum bold">{_html_esc.escape(_fmt_money(_tt))}</td>'
                    '</tr>'
                )
            _items_html += '</tbody></table>'
            st.markdown(_items_html, unsafe_allow_html=True)

        # ── Section 2: Giảm giá + 3 money cards ──
        st.markdown(
            '<div class="sc-form-section-title">💰 THÔNG TIN HÓA ĐƠN</div>',
            unsafe_allow_html=True,
        )
        giam_gia = st.number_input(
            "Giảm giá (đ)", min_value=0, step=10000,
            value=st.session_state.get("sc_inv_giam_gia", 0),
            key="sc_inv_giam_gia",
        )
        tra_truoc = int(phieu_dict.get("khach_tra_truoc") or 0)
        gg_int = int(giam_gia or 0)
        khach_can_tra = max(0, tong_hang - gg_int - tra_truoc)
        st.markdown(
            '<div class="sc-money-grid">'
            '<div class="sc-money-mini">'
            '<div class="mlab">TỔNG DỊCH VỤ</div>'
            f'<div class="mval">{_html_esc.escape(_fmt_money(tong_hang))}</div></div>'
            '<div class="sc-money-mini">'
            '<div class="mlab">GIẢM + TRẢ TRƯỚC</div>'
            f'<div class="mval">−{_html_esc.escape(_fmt_money(gg_int + tra_truoc))}</div></div>'
            '<div class="sc-money-mini danger">'
            '<div class="mlab">KHÁCH CẦN TRẢ</div>'
            f'<div class="mval">{_html_esc.escape(_fmt_money(khach_can_tra))}</div></div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # ── Section 3: Phương thức thanh toán ──
        st.markdown(
            '<div class="sc-form-section-title">💳 PHƯƠNG THỨC THANH TOÁN</div>',
            unsafe_allow_html=True,
        )
        chia_nhieu = st.checkbox(
            "Chia nhiều phương thức", key="sc_inv_chia_nhieu",
        )
        if chia_nhieu:
            cm1, cm2, cm3 = st.columns(3)
            with cm1:
                tien_mat = st.number_input(
                    "💵 Tiền mặt", min_value=0, step=10000,
                    value=st.session_state.get("sc_inv_tm", 0),
                    key="sc_inv_tm",
                )
            with cm2:
                chuyen_khoan = st.number_input(
                    "🏦 Chuyển khoản", min_value=0, step=10000,
                    value=st.session_state.get("sc_inv_ck", 0),
                    key="sc_inv_ck",
                )
            with cm3:
                the = st.number_input(
                    "💳 Thẻ", min_value=0, step=10000,
                    value=st.session_state.get("sc_inv_the", 0),
                    key="sc_inv_the",
                )
            sum_pttt = int(tien_mat) + int(chuyen_khoan) + int(the)
            valid_pttt = (sum_pttt == khach_can_tra)
            if not valid_pttt:
                diff = khach_can_tra - sum_pttt
                st.error(
                    f"⚠️ Tổng PTTT {_fmt_money(sum_pttt)} ≠ Khách cần trả "
                    f"{_fmt_money(khach_can_tra)} (chênh "
                    f"{_fmt_money(abs(diff))})"
                )
            else:
                st.success(f"✓ Khớp {_fmt_money(khach_can_tra)}")
        else:
            method = st.radio(
                "PTTT:", ["💵 Tiền mặt", "🏦 Chuyển khoản", "💳 Thẻ"],
                horizontal=True, key="sc_inv_method",
                label_visibility="collapsed",
            )
            if method == "💵 Tiền mặt":
                tien_mat, chuyen_khoan, the = khach_can_tra, 0, 0
            elif method == "🏦 Chuyển khoản":
                tien_mat, chuyen_khoan, the = 0, khach_can_tra, 0
            else:
                tien_mat, chuyen_khoan, the = 0, 0, khach_can_tra
            valid_pttt = True

        # ── Footer buttons ──
        st.markdown('<hr style="margin:14px 0 10px 0;border-color:#efece4">',
                    unsafe_allow_html=True)

        def _close_invoice():
            for _k in ("sc_invoice_open", "sc_inv_giam_gia",
                       "sc_inv_chia_nhieu", "sc_inv_tm", "sc_inv_ck",
                       "sc_inv_the", "sc_inv_method"):
                st.session_state.pop(_k, None)

        cf1, cf2 = st.columns([1, 2])
        with cf1:
            if st.button("Hủy", key="sc_inv_cancel", use_container_width=True):
                _close_invoice()
                st.rerun()
        with cf2:
            can_create = (not ct_df.empty) and valid_pttt
            if st.button(
                "✅ Tạo hóa đơn APSC", key="sc_inv_submit",
                type="primary", use_container_width=True,
                disabled=not can_create,
            ):
                try:
                    pttt = {
                        "tien_mat":     int(tien_mat),
                        "chuyen_khoan": int(chuyen_khoan),
                        "the":          int(the),
                    }
                    ma_hd = _tao_hoa_don_apsc(
                        dict(phieu_dict), ct_df, gg_int, pttt,
                    )
                    # Update phieu trang_thai → Hoàn thành
                    supabase.table("phieu_sua_chua").update({
                        "trang_thai": "Hoàn thành",
                        "updated_at": now_vn_iso(),
                    }).eq("ma_phieu", ma_phieu).execute()
                    st.cache_data.clear()
                    log_action("SC_TAO_HD",
                               f"ma_phieu={ma_phieu} ma_hd={ma_hd}")
                    _close_invoice()
                    st.toast(f"✓ Đã tạo HĐ {ma_hd}", icon="🧾")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi tạo HĐ: {e}")

    # ══════════════════════════════════════════════════════════
    # PR4 — Confirm dialogs (@st.dialog) với type-text validation
    # ══════════════════════════════════════════════════════════
    @st.dialog("❌ Hủy hóa đơn APSC?")
    def _cancel_apsc_dialog(ma_apsc, ma_ycsc, ho_ten_user):
        st.markdown(
            f"Mã HĐ: **`{_html_esc.escape(ma_apsc)}`** · "
            f"Phiếu: **`{_html_esc.escape(ma_ycsc)}`**"
        )
        st.warning(
            "⚠️ Hành động này sẽ:\n\n"
            "- Đảo kho atomic (cộng lại cho linh kiện thật)\n"
            "- Set HĐ trạng thái = 'Đã hủy'\n"
            "- Revert phiếu sửa chữa về 'Chờ giao khách'\n"
            "- Ghi audit log ADMIN_APSC_CANCEL\n\n"
            "**Không thể hoàn tác.**"
        )
        confirm_text = st.text_input(
            "Gõ **HỦY** để xác nhận:",
            key="sc_cancel_confirm_text",
            placeholder="HỦY",
        )
        valid = (confirm_text or "").strip().upper() == "HỦY"

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Đóng", key="sc_cancel_close",
                         use_container_width=True):
                st.session_state.pop("sc_cancel_open", None)
                st.session_state.pop("sc_cancel_confirm_text", None)
                st.rerun()
        with c2:
            if st.button("✅ Xác nhận hủy", type="primary",
                         disabled=not valid,
                         key="sc_cancel_submit",
                         use_container_width=True):
                from utils.print_queue_apsc import call_huy_hoa_don_apsc
                res = call_huy_hoa_don_apsc(
                    ma_apsc, ho_ten_user or "", ma_ycsc=ma_ycsc,
                )
                if res.get("ok"):
                    if res.get("warn_revert"):
                        st.warning(res["warn_revert"])
                    st.cache_data.clear()
                    log_action("SC_CANCEL_HD",
                               f"ma_phieu={ma_ycsc} ma_hd={ma_apsc} "
                               f"kho_restored={res.get('kho_restored', 0)}")
                    st.toast(
                        f"✅ Đã hủy {ma_apsc} · "
                        f"kho restored {res.get('kho_restored', 0)} SKU",
                        icon="❌",
                    )
                    st.session_state.pop("sc_cancel_open", None)
                    st.session_state.pop("sc_cancel_confirm_text", None)
                    st.rerun()
                else:
                    st.error(f"❌ Hủy thất bại: {res.get('error', '?')}")

    @st.dialog("🗑 Xóa phiếu sửa chữa?")
    def _delete_phieu_dialog(t):
        ma = str(t.get("ma_phieu", ""))
        ten = str(t.get("ten_khach") or "—")
        hieu = str(t.get("hieu_dong_ho") or "—")

        st.markdown(
            f"Mã: **`{_html_esc.escape(ma)}`**  \n"
            f"Khách: **{_html_esc.escape(ten)}** · "
            f"Đồng hồ: **{_html_esc.escape(hieu)}**"
        )
        st.warning(
            "⚠️ Hành động này sẽ XÓA:\n\n"
            "- Toàn bộ phiếu sửa chữa\n"
            "- Tất cả dịch vụ / linh kiện chi tiết\n\n"
            "**Không thể hoàn tác.**"
        )
        confirm_text = st.text_input(
            "Gõ **XÓA** để xác nhận:",
            key="sc_delete_confirm_text",
            placeholder="XÓA",
        )
        valid = (confirm_text or "").strip().upper() == "XÓA"

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Đóng", key="sc_delete_close",
                         use_container_width=True):
                st.session_state.pop("sc_delete_open", None)
                st.session_state.pop("sc_delete_confirm_text", None)
                st.rerun()
        with c2:
            if st.button("✅ Xác nhận xóa", type="primary",
                         disabled=not valid,
                         key="sc_delete_submit",
                         use_container_width=True):
                try:
                    supabase.table("phieu_sua_chua_chi_tiet") \
                        .delete().eq("ma_phieu", ma).execute()
                    supabase.table("phieu_sua_chua") \
                        .delete().eq("ma_phieu", ma).execute()
                    log_action("SC_DELETE", f"ma={ma}", level="warn")
                    st.cache_data.clear()
                    st.session_state.pop("sc_delete_open", None)
                    st.session_state.pop("sc_delete_confirm_text", None)
                    # Drawer state reset (phiếu không còn tồn tại)
                    st.session_state.pop("sc_drawer_ma", None)
                    st.session_state.pop("sc_form_mode", None)
                    st.session_state["sc_table_key_n"] = \
                        st.session_state.get("sc_table_key_n", 0) + 1
                    st.toast(f"✓ Đã xóa phiếu {ma}", icon="🗑")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi xóa: {e}")

    # ══════════════════════════════════════════════════════════
    # MAIN VIEW — Danh sách phiếu (PR4: bỏ tab strip, render trực tiếp)
    # ══════════════════════════════════════════════════════════
    with st.container():
        # ── Helper money formatter (inline — Streamlit số đẹp) ──
        def _fmt_money(n):
            try:
                return f"{int(n or 0):,}đ".replace(",", ".")
            except Exception:
                return "0đ"

        def _close_drawer():
            """Đóng drawer (detail | create | edit) + reset selection.

            Tăng table_key_n để force fresh widget instance — cách duy
            nhất clear selection của st.dataframe(on_select="rerun").
            Cũng tăng form_count để form keys bị reset khi mở lại lần sau.
            """
            st.session_state.pop("sc_drawer_ma", None)
            st.session_state.pop("sc_form_mode", None)
            st.session_state["sc_table_key_n"] = \
                st.session_state.get("sc_table_key_n", 0) + 1
            st.session_state["sc_drawer_form_count"] = \
                st.session_state.get("sc_drawer_form_count", 0) + 1

        # ── State ──
        st.session_state.setdefault("sc_table_key_n", 0)
        st.session_state.setdefault("sc_drawer_form_count", 0)
        drawer_ma = st.session_state.get("sc_drawer_ma")
        form_mode = st.session_state.get("sc_form_mode")  # None | "create" | "edit"

        # ── Render print HTML sau khi vừa tạo phiếu (tab_list có thể đang
        #    không show drawer nữa, nhưng print iframe phải mở)
        if st.session_state.get("sc_pending_print_html"):
            _in_phieu_sc(
                st.session_state.pop("sc_pending_print_html"),
                key="sc_print_drawer_create",
            )
            ma_just = st.session_state.pop("sc_just_created_ma", "")
            st.success(
                f"✓ Đã tạo phiếu **{ma_just}** — cửa sổ in đang mở"
            )

        # ══════ Filter bar — single row ══════
        show_branch_filter = is_ke_toan_or_admin() and len(accessible) > 1
        if show_branch_filter:
            fc_search, fc_tt, fc_cn, fc_clear, _, fc_new = \
                st.columns([3, 1.4, 1.4, 1, 0.3, 1.6])
        else:
            fc_search, fc_tt, fc_clear, _, fc_new = \
                st.columns([3, 1.4, 1, 0.3, 1.6])

        with fc_search:
            search = st.text_input(
                "Tìm:", key="sc_search",
                placeholder="🔍 SĐT / Mã phiếu / Tên khách (vd: '900' → SC000900)",
                label_visibility="collapsed",
            )

        TT_OPTS_FULL = ["Trạng thái: Tất cả", "Đang sửa", "Chờ linh kiện",
                        "Chờ giao khách", "Hoàn thành"]
        with fc_tt:
            tt_filter = st.selectbox(
                "Trạng thái:", TT_OPTS_FULL,
                key="sc_tt_filter", label_visibility="collapsed",
            )

        if show_branch_filter:
            with fc_cn:
                cn_filter = st.selectbox(
                    "Chi nhánh:", ["Chi nhánh: Tất cả"] + accessible,
                    key="sc_cn_filter", label_visibility="collapsed",
                )
        else:
            cn_filter = active

        has_filter = (
            (search or "").strip() != "" or
            (tt_filter and tt_filter != "Trạng thái: Tất cả") or
            (show_branch_filter and cn_filter != "Chi nhánh: Tất cả")
        )
        with fc_clear:
            if has_filter:
                if st.button("✕ Xóa lọc", key="sc_clear_filter",
                             use_container_width=True):
                    # Set explicit default values thay vì pop —
                    # st.selectbox widget state không reset bằng pop alone.
                    st.session_state["sc_search"] = ""
                    st.session_state["sc_tt_filter"] = "Trạng thái: Tất cả"
                    if show_branch_filter:
                        st.session_state["sc_cn_filter"] = "Chi nhánh: Tất cả"
                    _close_drawer()
                    st.rerun()

        with fc_new:
            if st.button("＋ Tạo phiếu mới", key="sc_btn_create_new",
                         type="primary", use_container_width=True):
                # Mở create drawer + clear detail drawer + reset selection
                # + bump form_count để form fresh (clear data từ lần mở trước)
                st.session_state["sc_form_mode"] = "create"
                st.session_state.pop("sc_drawer_ma", None)
                st.session_state["sc_table_key_n"] = \
                    st.session_state.get("sc_table_key_n", 0) + 1
                st.session_state["sc_drawer_form_count"] = \
                    st.session_state.get("sc_drawer_form_count", 0) + 1
                st.rerun()

        # Resolve branches từ filter
        if show_branch_filter:
            branches = accessible if cn_filter == "Chi nhánh: Tất cả" else [cn_filter]
        else:
            branches = [active]

        # ══════ Load + filter data ══════
        df = _load_phieu(tuple(branches))
        if not df.empty:
            if tt_filter and tt_filter != "Trạng thái: Tất cả":
                df = df[df["trang_thai"] == tt_filter]
            if search and search.strip():
                s = search.strip().lower()
                mask = (df["ma_phieu"].apply(lambda m: _sc_match_ma(m, s)) |
                        df["sdt_khach"].astype(str).str.lower().str.contains(s, na=False) |
                        df["ten_khach"].astype(str).str.lower().str.contains(s, na=False))
                df = df[mask]

        # Drawer state cleanup: nếu drawer_ma không còn trong filtered df → reset
        # (chỉ áp dụng cho detail mode, KHÔNG đóng create drawer khi đổi filter)
        if drawer_ma and not form_mode and \
                (df.empty or df[df["ma_phieu"] == drawer_ma].empty):
            _close_drawer()
            drawer_ma = None

        # ══════ Modals (@st.dialog) — render khi flag set ══════
        # Mỗi flag lưu thông tin cần thiết, dialog re-render qua mọi rerun
        # cho đến khi user Đóng/Submit (cả 2 đều pop flag).

        # Invoice modal: sc_invoice_open = ma_phieu
        _inv_ma = st.session_state.get("sc_invoice_open")
        if _inv_ma:
            _inv_rows = df[df["ma_phieu"] == _inv_ma] if not df.empty else df
            if _inv_rows is None or _inv_rows.empty:
                st.session_state.pop("sc_invoice_open", None)
            else:
                _inv_t = _inv_rows.iloc[0].to_dict()
                _inv_ct = _load_chi_tiet(_inv_ma)
                _invoice_dialog(_inv_t, _inv_ct)

        # Cancel APSC modal: sc_cancel_open = (ma_apsc, ma_ycsc)
        _cancel_pair = st.session_state.get("sc_cancel_open")
        if _cancel_pair and isinstance(_cancel_pair, (tuple, list)) \
                and len(_cancel_pair) == 2:
            _cancel_apsc_dialog(_cancel_pair[0], _cancel_pair[1], ho_ten or "")

        # Delete phieu modal: sc_delete_open = ma_phieu
        _del_ma = st.session_state.get("sc_delete_open")
        if _del_ma:
            _del_rows = df[df["ma_phieu"] == _del_ma] if not df.empty else df
            if _del_rows is None or _del_rows.empty:
                st.session_state.pop("sc_delete_open", None)
            else:
                _del_t = _del_rows.iloc[0].to_dict()
                _delete_phieu_dialog(_del_t)

        # ══════ 2-col split khi drawer mở (Option A) ══════
        # Create form rộng hơn (60%) vì có nhiều fields
        if form_mode == "create":
            col_main, col_drawer = st.columns([2, 3], gap="medium")
        elif form_mode == "edit" and drawer_ma:
            col_main, col_drawer = st.columns([3, 2], gap="medium")
        elif drawer_ma:
            col_main, col_drawer = st.columns([3, 2], gap="medium")
        else:
            col_main = st.container()
            col_drawer = None

        # ══════ Main column: table ══════
        with col_main:
            if df.empty:
                st.markdown(
                    '<div class="sc-root"><div class="sc-empty">'
                    '<div class="sc-empty-title">Chưa có phiếu nào phù hợp</div>'
                    '<div>Hãy điều chỉnh bộ lọc hoặc tạo phiếu mới</div>'
                    '</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                # ── st.dataframe + emoji prefix cho trạng thái ──
                # Revert custom HTML table (gây crash session khi click row
                # do query_param navigation + underline cells khắp nơi).
                # Selection dùng on_select="rerun" với key động (counter
                # bump khi close để clear widget state).
                _STATUS_EMOJI = {
                    "Hoàn thành":     "🟢 Hoàn thành",
                    "Đang sửa":       "🟡 Đang sửa",
                    "Chờ linh kiện":  "🔵 Chờ linh kiện",
                    "Chờ giao khách": "🟠 Chờ giao khách",
                    "Đã hủy":         "🔴 Đã hủy",
                }

                st.caption(f"📋 Danh sách **{len(df)}** phiếu — click hàng để xem chi tiết")
                view = pd.DataFrame({
                    "Mã Phiếu":   df["ma_phieu"].astype(str),
                    "Chi Nhánh":  df["chi_nhanh"].apply(
                        lambda c: CN_SHORT.get(c, c) if isinstance(CN_SHORT, dict) else c),
                    "Khách hàng": df["ten_khach"].fillna(""),
                    "SĐT":        df["sdt_khach"].fillna("").astype(str),
                    "Loại":       df["loai_yeu_cau"].fillna(""),
                    "Hiệu ĐH":    df["hieu_dong_ho"].fillna(""),
                    "Trạng Thái": df["trang_thai"].fillna("").apply(
                        lambda s: _STATUS_EMOJI.get(s, s)),
                    "Hẹn Trả":    df["ngay_hen_tra"].fillna("").astype(str),
                    "Ngày TN":    df.get("Ngày TN", pd.Series([""] * len(df))),
                    "NV":         df["nguoi_tiep_nhan"].fillna(""),
                }).reset_index(drop=True)

                _table_key = f"sc_table_select_{st.session_state['sc_table_key_n']}"
                event = st.dataframe(
                    view,
                    use_container_width=True,
                    hide_index=True,
                    height=540,
                    on_select="rerun",
                    selection_mode="single-row",
                    key=_table_key,
                )

                try:
                    sel_rows = event.selection.rows or []
                except Exception:
                    sel_rows = []
                if sel_rows:
                    clicked_ma = view.iloc[sel_rows[0]]["Mã Phiếu"]
                    if clicked_ma != drawer_ma:
                        # Switch to detail mode, đóng create form nếu đang mở
                        st.session_state["sc_drawer_ma"] = clicked_ma
                        st.session_state.pop("sc_form_mode", None)
                        st.rerun()

        # ══════ Drawer column: create | edit | detail ══════
        if col_drawer and form_mode == "create":
            with col_drawer:
                _render_create_drawer(
                    cn_default=active,
                    accessible=accessible,
                    is_multi_branch=is_ke_toan_or_admin() and len(accessible) > 1,
                    ho_ten=ho_ten,
                    user=user,
                    fmt_money=_fmt_money,
                    close_drawer=_close_drawer,
                )
        elif col_drawer and form_mode == "edit" and drawer_ma:
            with col_drawer:
                _t_rows = df[df["ma_phieu"] == drawer_ma]
                if _t_rows.empty:
                    st.warning(f"Phiếu {drawer_ma} không còn trong filter.")
                    if st.button("✕ Đóng", key="sc_drawer_edit_close_err"):
                        _close_drawer()
                        st.rerun()
                else:
                    _render_edit_drawer(
                        t=_t_rows.iloc[0].to_dict(),
                        ho_ten=ho_ten,
                        fmt_money=_fmt_money,
                        close_drawer=_close_drawer,
                    )
        elif col_drawer:
            with col_drawer:
                t_rows = df[df["ma_phieu"] == drawer_ma]
                t = t_rows.iloc[0].to_dict() if not t_rows.empty else None

                if t is None:
                    st.warning(f"Không tìm thấy phiếu {drawer_ma}")
                    if st.button("✕ Đóng", key="sc_drawer_close_err"):
                        _close_drawer()
                        st.rerun()
                else:
                    # Normalize NaN/None → "" cho mọi field. df.iloc[0].to_dict()
                    # giữ NaN cho object cols → (NaN or "").strip() crash
                    # AttributeError. Apply uniform fix với helper local.
                    def _v(key, default=""):
                        val = t.get(key)
                        if val is None:
                            return default
                        try:
                            if isinstance(val, float) and pd.isna(val):
                                return default
                        except Exception:
                            pass
                        return val

                    # Map status → pill class
                    PILL_CLASS = {
                        "Hoàn thành":     "done",
                        "Đang sửa":       "fixing",
                        "Chờ linh kiện":  "waiting",
                        "Chờ giao khách": "handover",
                    }
                    tt_phieu = str(_v("trang_thai")) or ""
                    pill_cls = PILL_CLASS.get(tt_phieu, "")

                    # ── Header ──
                    head_l, head_r = st.columns([5, 1.2])
                    with head_l:
                        st.markdown(
                            f'<div class="sc-root"><div class="sc-drawer-head">'
                            f'<div class="small">PHIẾU SỬA CHỮA</div>'
                            f'<h2><span class="id sc-mono">{_html_esc.escape(str(_v("ma_phieu")))}</span>'
                            f' · {_html_esc.escape(str(_v("ten_khach", "—")) or "—")}</h2>'
                            f'<div class="meta">'
                            f'<span>📞 {_html_esc.escape(str(_v("sdt_khach", "—")) or "—")}</span>'
                            f'<span class="sc-pill {pill_cls}">{_html_esc.escape(tt_phieu)}</span>'
                            f'</div>'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )
                    with head_r:
                        # Edit ✎ + Close ✕
                        bcol_edit, bcol_close = st.columns(2)
                        with bcol_edit:
                            edit_disabled = (tt_phieu == "Hoàn thành")
                            if st.button("✎", key="sc_drawer_edit",
                                         help=("Phiếu Hoàn thành không thể sửa"
                                               if edit_disabled
                                               else "Cập nhật phiếu"),
                                         disabled=edit_disabled,
                                         use_container_width=True):
                                # Switch sang edit mode — drawer column
                                # render _render_edit_drawer ở rerun tới
                                st.session_state["sc_form_mode"] = "edit"
                                st.session_state["sc_drawer_form_count"] = \
                                    st.session_state.get("sc_drawer_form_count", 0) + 1
                                st.rerun()
                        with bcol_close:
                            if st.button("✕", key="sc_drawer_close",
                                         help="Đóng",
                                         use_container_width=True):
                                _close_drawer()
                                st.rerun()

                    # ── Card 1: Thông tin tiếp nhận ──
                    def _vesc(key, default="—"):
                        v = _v(key, default)
                        s = str(v) if v else default
                        return _html_esc.escape(s or default)

                    st.markdown(
                        '<div class="sc-root"><div class="sc-d-card">'
                        '<div class="sc-d-card-title">📋 Thông tin tiếp nhận</div>'
                        '<div class="sc-info-grid">'
                        f'<div class="sc-info-row"><span class="lab">Chi nhánh</span>'
                        f'<span class="val">{_vesc("chi_nhanh")}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">Loại YC</span>'
                        f'<span class="val">{_vesc("loai_yeu_cau")}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">Hiệu đồng hồ</span>'
                        f'<span class="val">{_vesc("hieu_dong_ho")}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">Đặc điểm</span>'
                        f'<span class="val">{_vesc("dac_diem")}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">NV tiếp nhận</span>'
                        f'<span class="val">{_vesc("nguoi_tiep_nhan")}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">Ngày tiếp nhận</span>'
                        f'<span class="val sc-num">{_vesc("Ngày TN")}</span></div>'
                        f'<div class="sc-info-row full"><span class="lab">Hẹn trả</span>'
                        f'<span class="val">{_vesc("ngay_hen_tra")}</span></div>'
                        '</div></div></div>',
                        unsafe_allow_html=True,
                    )

                    # ── Card 2: Mô tả lỗi + ghi chú nội bộ ──
                    mo_ta = str(_v("mo_ta_loi")).strip()
                    ghi_chu = str(_v("ghi_chu_noi_bo")).strip()
                    desc_html = (
                        '<div class="sc-root"><div class="sc-d-card">'
                        '<div class="sc-d-card-title">📝 Mô tả lỗi / Yêu cầu</div>'
                        f'<div class="sc-desc-block">'
                        f'{_html_esc.escape(mo_ta) if mo_ta else "—"}</div>'
                    )
                    if ghi_chu:
                        desc_html += (
                            '<div class="sc-desc-note">'
                            '<div class="lab">GHI CHÚ NỘI BỘ</div>'
                            f'<div>{_html_esc.escape(ghi_chu)}</div>'
                            '</div>'
                        )
                    desc_html += '</div></div>'
                    st.markdown(desc_html, unsafe_allow_html=True)

                    # ── Card 3: Items + 3 money cards ──
                    ct = _load_chi_tiet(drawer_ma)
                    tong_hang = 0
                    items_html = (
                        '<div class="sc-root"><div class="sc-d-card">'
                        '<div class="sc-d-card-title">🔧 Dịch vụ / Linh kiện</div>'
                    )
                    if ct.empty:
                        items_html += (
                            '<div class="sc-empty-items">'
                            'Chưa có dịch vụ / linh kiện nào</div>'
                        )
                    else:
                        items_html += (
                            '<table class="sc-items">'
                            '<thead><tr>'
                            '<th>Loại</th><th>Tên</th><th>Mã</th>'
                            '<th class="right">SL</th>'
                            '<th class="right">Đơn giá</th>'
                            '<th class="right">Thành tiền</th>'
                            '</tr></thead><tbody>'
                        )
                        for _, r in ct.iterrows():
                            sl = int(r.get("so_luong") or 0)
                            dg = int(r.get("don_gia") or 0)
                            tt_money = sl * dg
                            tong_hang += tt_money
                            kind = (r.get("loai_dong") or "").strip()
                            kind_cls = "dv" if kind == "Dịch vụ" else ""
                            items_html += (
                                '<tr>'
                                f'<td><span class="sc-kind-tag {kind_cls}">{kind or "—"}</span></td>'
                                f'<td>{r.get("ten_hang","") or "—"}</td>'
                                f'<td class="ma">{r.get("ma_hang","") or "—"}</td>'
                                f'<td class="right tnum">{sl}</td>'
                                f'<td class="right tnum">{_fmt_money(dg)}</td>'
                                f'<td class="right tnum bold">{_fmt_money(tt_money)}</td>'
                                '</tr>'
                            )
                        items_html += '</tbody></table>'

                    # 3 money cards
                    da_tra_truoc = int(_v("khach_tra_truoc", 0) or 0)
                    con_lai = max(0, tong_hang - da_tra_truoc)
                    con_lai_cls = "danger" if con_lai > 0 else "success"
                    items_html += (
                        '<div class="sc-money-grid">'
                        '<div class="sc-money-mini">'
                        '<div class="mlab">TỔNG CỘNG</div>'
                        f'<div class="mval">{_fmt_money(tong_hang)}</div></div>'
                        '<div class="sc-money-mini">'
                        '<div class="mlab">ĐÃ TRẢ TRƯỚC</div>'
                        f'<div class="mval">{_fmt_money(da_tra_truoc)}</div></div>'
                        f'<div class="sc-money-mini {con_lai_cls}">'
                        '<div class="mlab">CÒN LẠI</div>'
                        f'<div class="mval">{_fmt_money(con_lai)}</div></div>'
                        '</div>'
                    )
                    items_html += '</div></div>'
                    st.markdown(items_html, unsafe_allow_html=True)

                    # ── APSC card (nếu Hoàn thành + có HĐ APSC linked) ──
                    apsc_data = None
                    if tt_phieu == "Hoàn thành":
                        try:
                            apsc_res = supabase.table("hoa_don").select(
                                '"Mã hóa đơn", "Trạng thái", "Khách cần trả",'
                                '"Tiền mặt", "Chuyển khoản", "Thẻ"'
                            ).eq("Mã YCSC", drawer_ma).limit(1).execute()
                            if apsc_res.data:
                                apsc_data = apsc_res.data[0]
                        except Exception as e:
                            st.warning(f"⚠️ Không load được HĐ APSC: {e}")

                    if apsc_data:
                        ma_apsc   = apsc_data.get("Mã hóa đơn", "")
                        tt_apsc   = apsc_data.get("Trạng thái", "") or ""
                        tong_kt   = int(apsc_data.get("Khách cần trả") or 0)
                        tm        = int(apsc_data.get("Tiền mặt") or 0)
                        ck        = int(apsc_data.get("Chuyển khoản") or 0)
                        the       = int(apsc_data.get("Thẻ") or 0)
                        da_huy    = (tt_apsc == "Đã hủy")

                        # Build payment breakdown
                        pay_parts = []
                        if tm > 0:  pay_parts.append(f"Tiền mặt {_fmt_money(tm)}")
                        if ck > 0:  pay_parts.append(f"Chuyển khoản {_fmt_money(ck)}")
                        if the > 0: pay_parts.append(f"Thẻ {_fmt_money(the)}")
                        pay_str = " · ".join(pay_parts) if pay_parts else "—"

                        card_cls = "cancelled" if da_huy else ""
                        st.markdown(
                            f'<div class="sc-root"><div class="sc-apsc-card {card_cls}">'
                            f'<div class="sc-apsc-row">'
                            f'<div class="sc-apsc-info">'
                            f'<div class="apsc-lab">Hóa đơn APSC</div>'
                            f'<div class="apsc-id sc-mono">{ma_apsc}</div>'
                            f'<div class="apsc-meta">Tổng: <strong>{_fmt_money(tong_kt)}</strong>'
                            f' · {pay_str}</div>'
                            f'</div></div></div></div>',
                            unsafe_allow_html=True,
                        )

                        # Buttons: 🖨 In lại + ❌ Hủy HĐ (admin only)
                        # Hủy HĐ dùng @st.dialog _cancel_apsc_dialog với type
                        # "HỦY" validation (PR4 — replace 2-step confirm cũ).
                        cb1, cb2 = st.columns(2)
                        with cb1:
                            if st.button("🖨 In lại",
                                         key=f"sc_reprint_{ma_apsc}",
                                         use_container_width=True):
                                from utils.print_queue_apsc import enqueue_apsc
                                pr = enqueue_apsc(ma_apsc, ho_ten or "")
                                if pr.get("ok"):
                                    st.toast("🖨 Đã gửi lệnh in lại", icon="🖨")
                                else:
                                    st.toast(f"⚠️ {pr.get('error','Lỗi in')}",
                                             icon="⚠️")
                        with cb2:
                            if not da_huy and is_admin():
                                if st.button("❌ Hủy HĐ",
                                             key=f"sc_huy_{ma_apsc}",
                                             use_container_width=True):
                                    st.session_state["sc_cancel_open"] = \
                                        (ma_apsc, drawer_ma)
                                    st.rerun()

                    # ── Create invoice CTA (Chờ giao khách + chưa có HĐ APSC) ──
                    if tt_phieu == "Chờ giao khách" and not apsc_data:
                        st.markdown("&nbsp;", unsafe_allow_html=True)
                        if st.button("🧾 Tạo hóa đơn APSC cho phiếu này",
                                     key=f"sc_make_apsc_{drawer_ma}",
                                     type="primary",
                                     use_container_width=True):
                            # Mở @st.dialog modal — flag persist qua reruns
                            st.session_state["sc_invoice_open"] = drawer_ma
                            st.rerun()
                        st.caption("Phiếu đã sẵn sàng giao khách — tạo HĐ APSC để chốt thanh toán.")

                    # ── Footer: In phiếu A5 + Hủy/Xóa ──
                    st.markdown('<hr style="margin:14px 0 10px 0;border-color:#efece4">',
                                unsafe_allow_html=True)
                    foot_l, foot_r = st.columns(2)
                    with foot_l:
                        if st.button("🖨 In phiếu (A5)",
                                     key=f"sc_print_a5_{drawer_ma}",
                                     use_container_width=True):
                            try:
                                # Normalize NaN/None → "" cho _build_phieu_html
                                phieu_dict = {
                                    k: _v(k, "") for k in t.keys()
                                }
                                phieu_dict["ngay_tn_str"] = _v("Ngày TN", "")
                                html_a5 = _build_phieu_html(phieu_dict, ct)
                                _in_phieu_sc(html_a5, key=f"sc_a5_{drawer_ma}")
                            except Exception as e:
                                st.error(f"Lỗi in: {e}")
                    with foot_r:
                        # 🗑 Xóa phiếu — disabled nếu phiếu có HĐ APSC chưa hủy
                        delete_disabled = bool(apsc_data and
                                               apsc_data.get("Trạng thái") != "Đã hủy")
                        if st.button("🗑 Xóa phiếu",
                                     key=f"sc_delete_phieu_{drawer_ma}",
                                     disabled=delete_disabled,
                                     help=("Hủy HĐ APSC trước khi xóa phiếu"
                                           if delete_disabled
                                           else "Xóa phiếu + items (cần type XÓA)"),
                                     use_container_width=True):
                            st.session_state["sc_delete_open"] = drawer_ma
                            st.rerun()


import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np

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
.sc-card {
    background: #fff;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 16px 18px;
    margin: 8px 0;
}
.sc-card-header {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 4px;
}
.sc-card-sub {
    font-size: 0.82rem;
    color: #888;
    margin-bottom: 10px;
}
.sc-info-row {
    display: flex;
    margin: 4px 0;
    font-size: 0.9rem;
}
.sc-info-label {
    color: #777;
    min-width: 110px;
}
.sc-info-val {
    color: #1a1a2e;
    font-weight: 500;
    flex: 1;
}
.sc-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    background: #fff7e0;
    color: #b78103;
    border: 1px solid #f3d984;
}
.sc-badge-green {
    background: #e8f5e9;
    color: #1a7f37;
    border-color: #a8d4ad;
}
.sc-badge-red {
    background: #ffebee;
    color: #cf4c2c;
    border-color: #f5b5a8;
}
.sc-section-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: #1a1a2e;
    margin: 14px 0 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid #ebebeb;
}
.sc-money-card {
    background: #fff;
    border: 1px solid #e8e8e8;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: center;
}
.sc-money-card-red {
    border: 2px solid #e63946;
    background: #fff8f8;
}
.sc-money-label {
    font-size: 0.78rem;
    color: #777;
    margin-bottom: 4px;
}
.sc-money-value {
    font-size: 1.2rem;
    font-weight: 700;
    color: #1a1a2e;
}
.sc-money-value-red {
    color: #e63946;
}

/* ═══════════════════════════════════════════════════════════
   PR1 redesign — design tokens + new components for Tab 1
   (legacy classes above giữ nguyên cho Tab 2/3/4 đang chờ PR2-4)
   ═══════════════════════════════════════════════════════════ */

@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

/* Design tokens (apply scoped via .sc-root) */
.sc-root {
    --sc-bg: #faf9f6;
    --sc-surface: #ffffff;
    --sc-surface-2: #f5f3ee;
    --sc-ink: #1a1815;
    --sc-ink-2: #4a463e;
    --sc-ink-3: #8a8478;
    --sc-line: #e8e5dd;
    --sc-line-2: #efece4;
    --sc-accent: oklch(0.56 0.11 165);
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
    font-family: 'Be Vietnam Pro', system-ui, -apple-system, sans-serif;
    color: var(--sc-ink);
}
.sc-root .sc-mono { font-family: 'DM Mono', ui-monospace, monospace; font-feature-settings: 'tnum'; }
.sc-root .sc-num  { font-variant-numeric: tabular-nums; }

/* Header */
.sc-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.sc-h1 { font-size: 20px; font-weight: 600; letter-spacing: -0.01em; margin: 0; }
.sc-sub { font-size: 12.5px; color: var(--sc-ink-3); margin: 2px 0 0; }
.sc-branch-badge { font-size: 12px; color: var(--sc-ink-3); }

/* Status pills */
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

/* Detail drawer card */
.sc-drawer { background: var(--sc-surface); border: 1px solid var(--sc-line); border-radius: 10px;
    padding: 0; overflow: hidden;
    box-shadow: -8px 0 24px -12px rgba(20,18,15,0.12); }
.sc-drawer-head { padding: 14px 16px; border-bottom: 1px solid var(--sc-line); }
.sc-drawer-head .small { font-size: 11px; color: var(--sc-ink-3); letter-spacing: 0.04em; text-transform: uppercase; margin-bottom: 4px; }
.sc-drawer-head h2 { margin: 0; font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sc-drawer-head h2 .id { font-family: 'DM Mono', monospace; font-size: 14px; color: var(--sc-ink-2); }
.sc-drawer-head .meta { margin-top: 6px; font-size: 12.5px; color: var(--sc-ink-2); display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }

.sc-drawer-body { padding: 14px 16px; }
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
.sc-apsc-card {
    margin-top: 10px;
    padding: 12px 14px;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--sc-accent-soft), var(--sc-surface));
    border: 1px solid var(--sc-accent-line);
}
.sc-apsc-card.cancelled { background: var(--sc-rose-soft); border-color: oklch(0.85 0.06 22); }
.sc-apsc-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.sc-apsc-info .apsc-lab { font-size: 11px; color: var(--sc-ink-3); margin-bottom: 2px; letter-spacing: 0.02em; text-transform: uppercase; }
.sc-apsc-info .apsc-id { font-family: 'DM Mono', monospace; font-size: 14px; font-weight: 600; color: var(--sc-emerald-ink); }
.sc-apsc-card.cancelled .sc-apsc-info .apsc-id { color: var(--sc-rose-ink); text-decoration: line-through; }
.sc-apsc-info .apsc-meta { font-size: 11.5px; color: var(--sc-ink-2); margin-top: 2px; }

/* Empty state */
.sc-empty { padding: 40px 24px; text-align: center; color: var(--sc-ink-3); font-size: 13px;
    background: var(--sc-surface); border: 1px dashed var(--sc-line); border-radius: 10px; }
.sc-empty-title { color: var(--sc-ink-2); font-weight: 500; margin-bottom: 4px; font-size: 14px; }

/* Empty items in card */
.sc-empty-items { font-size: 12.5px; color: var(--sc-ink-3); padding: 12px 0; text-align: center; font-style: italic; }
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

    tab_list, tab_create, tab_detail, tab_hoadon = st.tabs(
        ["Danh sách phiếu", "Tạo phiếu mới", "Chi tiết / Cập nhật", "Tạo hóa đơn sửa"]
    )

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
    # TAB 1 — DANH SÁCH PHIẾU
    # ══════════════════════════════════════════════════════════
    with tab_list:
        # ── Helper money formatter (inline — Streamlit số đẹp) ──
        def _fmt_money(n):
            try:
                return f"{int(n or 0):,}đ".replace(",", ".")
            except Exception:
                return "0đ"

        def _close_drawer():
            """Đóng drawer + reset st.dataframe selection state.

            Tăng table_key_n để force fresh widget instance — cách duy
            nhất clear selection của st.dataframe(on_select="rerun").
            Nếu chỉ pop sc_drawer_ma → rerun → widget cũ vẫn giữ
            selection → block xử lý sel_rows tự re-set drawer_ma.
            """
            st.session_state.pop("sc_drawer_ma", None)
            st.session_state["sc_table_key_n"] = \
                st.session_state.get("sc_table_key_n", 0) + 1

        # ── State ──
        st.session_state.setdefault("sc_table_key_n", 0)
        drawer_ma = st.session_state.get("sc_drawer_ma")

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
                    for k in ("sc_search", "sc_tt_filter", "sc_cn_filter"):
                        st.session_state.pop(k, None)
                    _close_drawer()
                    st.rerun()

        with fc_new:
            if st.button("＋ Tạo phiếu mới", key="sc_btn_create_new",
                         type="primary", use_container_width=True):
                st.toast("PR2 sẽ thêm form drawer — tạm dùng tab 'Tạo phiếu mới'",
                         icon="ℹ️")

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
        if drawer_ma and (df.empty or df[df["ma_phieu"] == drawer_ma].empty):
            _close_drawer()
            drawer_ma = None

        # ══════ 2-col split khi drawer mở (Option A) ══════
        if drawer_ma:
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
                st.caption(f"📋 Danh sách **{len(df)}** phiếu")
                view = pd.DataFrame({
                    "Mã Phiếu":   df["ma_phieu"].astype(str),
                    "Chi Nhánh":  df["chi_nhanh"].apply(
                        lambda c: CN_SHORT.get(c, c) if isinstance(CN_SHORT, dict) else c),
                    "Khách hàng": df["ten_khach"].fillna(""),
                    "SĐT":        df["sdt_khach"].fillna("").astype(str),
                    "Loại":       df["loai_yeu_cau"].fillna(""),
                    "Hiệu ĐH":    df["hieu_dong_ho"].fillna(""),
                    "Trạng Thái": df["trang_thai"].fillna(""),
                    "Hẹn Trả":    df["ngay_hen_tra"].fillna("").astype(str),
                    "Ngày TN":    df.get("Ngày TN", pd.Series([""] * len(df))),
                    "NV":         df["nguoi_tiep_nhan"].fillna(""),
                }).reset_index(drop=True)

                # Key động theo counter để close có thể clear selection
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
                        st.session_state["sc_drawer_ma"] = clicked_ma
                        st.rerun()

        # ══════ Drawer column: detail ══════
        if col_drawer:
            with col_drawer:
                t_rows = df[df["ma_phieu"] == drawer_ma]
                t = t_rows.iloc[0].to_dict() if not t_rows.empty else None

                if t is None:
                    st.warning(f"Không tìm thấy phiếu {drawer_ma}")
                    if st.button("✕ Đóng", key="sc_drawer_close_err"):
                        _close_drawer()
                        st.rerun()
                else:
                    # Map status → pill class
                    PILL_CLASS = {
                        "Hoàn thành":     "done",
                        "Đang sửa":       "fixing",
                        "Chờ linh kiện":  "waiting",
                        "Chờ giao khách": "handover",
                    }
                    tt_phieu = t.get("trang_thai", "") or ""
                    pill_cls = PILL_CLASS.get(tt_phieu, "")

                    # ── Header ──
                    head_l, head_r = st.columns([5, 1.2])
                    with head_l:
                        st.markdown(
                            f'<div class="sc-root"><div class="sc-drawer-head">'
                            f'<div class="small">PHIẾU SỬA CHỮA</div>'
                            f'<h2><span class="id sc-mono">{t.get("ma_phieu","")}</span>'
                            f'· {t.get("ten_khach","") or "—"}</h2>'
                            f'<div class="meta">'
                            f'<span>📞 {t.get("sdt_khach","") or "—"}</span>'
                            f'<span class="sc-pill {pill_cls}">{tt_phieu}</span>'
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
                                         help="Cập nhật phiếu (PR3)",
                                         disabled=edit_disabled,
                                         use_container_width=True):
                                st.toast("PR3 sẽ thêm — tạm dùng tab 'Chi tiết / Cập nhật'",
                                         icon="ℹ️")
                        with bcol_close:
                            if st.button("✕", key="sc_drawer_close",
                                         help="Đóng",
                                         use_container_width=True):
                                _close_drawer()
                                st.rerun()

                    # ── Card 1: Thông tin tiếp nhận ──
                    st.markdown(
                        '<div class="sc-root"><div class="sc-d-card">'
                        '<div class="sc-d-card-title">📋 Thông tin tiếp nhận</div>'
                        '<div class="sc-info-grid">'
                        f'<div class="sc-info-row"><span class="lab">Chi nhánh</span>'
                        f'<span class="val">{t.get("chi_nhanh","") or "—"}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">Loại YC</span>'
                        f'<span class="val">{t.get("loai_yeu_cau","") or "—"}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">Hiệu đồng hồ</span>'
                        f'<span class="val">{t.get("hieu_dong_ho","") or "—"}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">Đặc điểm</span>'
                        f'<span class="val">{t.get("dac_diem","") or "—"}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">NV tiếp nhận</span>'
                        f'<span class="val">{t.get("nguoi_tiep_nhan","") or "—"}</span></div>'
                        f'<div class="sc-info-row"><span class="lab">Ngày tiếp nhận</span>'
                        f'<span class="val sc-num">{t.get("Ngày TN","") or "—"}</span></div>'
                        f'<div class="sc-info-row full"><span class="lab">Hẹn trả</span>'
                        f'<span class="val">{t.get("ngay_hen_tra","") or "—"}</span></div>'
                        '</div></div></div>',
                        unsafe_allow_html=True,
                    )

                    # ── Card 2: Mô tả lỗi + ghi chú nội bộ ──
                    mo_ta = (t.get("mo_ta_loi") or "").strip()
                    ghi_chu = (t.get("ghi_chu_noi_bo") or "").strip()
                    desc_html = (
                        '<div class="sc-root"><div class="sc-d-card">'
                        '<div class="sc-d-card-title">📝 Mô tả lỗi / Yêu cầu</div>'
                        f'<div class="sc-desc-block">{mo_ta or "—"}</div>'
                    )
                    if ghi_chu:
                        desc_html += (
                            '<div class="sc-desc-note">'
                            '<div class="lab">GHI CHÚ NỘI BỘ</div>'
                            f'<div>{ghi_chu}</div>'
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
                    da_tra_truoc = int(t.get("khach_tra_truoc") or 0)
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

                        # Buttons (Streamlit native, không inline được vào HTML)
                        confirm_key = f"sc_confirm_huy_{ma_apsc}"
                        if st.session_state.get(confirm_key):
                            st.warning(
                                f"⚠️ Xác nhận hủy HĐ **{ma_apsc}**? "
                                "Đảo kho atomic + audit log, "
                                "phiếu sẽ revert 'Chờ giao khách' (không thể hoàn tác)."
                            )
                            cc1, cc2 = st.columns(2)
                            with cc1:
                                if st.button("✅ Xác nhận hủy",
                                             key=f"sc_yes_huy_{ma_apsc}",
                                             type="primary",
                                             use_container_width=True):
                                    from utils.print_queue_apsc import call_huy_hoa_don_apsc
                                    res = call_huy_hoa_don_apsc(
                                        ma_apsc, ho_ten or "",
                                        ma_ycsc=drawer_ma,
                                    )
                                    if res.get("ok"):
                                        st.success(
                                            f"✅ Đã hủy {ma_apsc} · "
                                            f"kho restored {res.get('kho_restored', 0)} SKU "
                                            f"({res.get('units_restored', 0)} đv)"
                                        )
                                        if res.get("warn_revert"):
                                            st.warning(res["warn_revert"])
                                        st.cache_data.clear()
                                    else:
                                        st.error(f"❌ Hủy thất bại: {res.get('error', '?')}")
                                    st.session_state.pop(confirm_key, None)
                                    st.rerun()
                            with cc2:
                                if st.button("✖ Bỏ qua",
                                             key=f"sc_no_huy_{ma_apsc}",
                                             use_container_width=True):
                                    st.session_state.pop(confirm_key, None)
                                    st.rerun()
                        else:
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
                                        st.session_state[confirm_key] = True
                                        st.rerun()

                    # ── Create invoice CTA (Chờ giao khách + chưa có HĐ APSC) ──
                    if tt_phieu == "Chờ giao khách" and not apsc_data:
                        st.markdown("&nbsp;", unsafe_allow_html=True)
                        if st.button("🧾 Tạo hóa đơn APSC cho phiếu này",
                                     key=f"sc_make_apsc_{drawer_ma}",
                                     type="primary",
                                     use_container_width=True):
                            st.toast("PR3 sẽ thêm modal tạo HĐ — "
                                     "tạm dùng tab 'Tạo hóa đơn sửa'",
                                     icon="ℹ️")
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
                                phieu_dict = {
                                    **t,
                                    "ngay_tn_str": t.get("Ngày TN", ""),
                                }
                                html_a5 = _build_phieu_html(phieu_dict, ct)
                                _in_phieu_sc(html_a5, key=f"sc_a5_{drawer_ma}")
                            except Exception as e:
                                st.error(f"Lỗi in: {e}")
                    with foot_r:
                        delete_disabled = bool(apsc_data and
                                               apsc_data.get("Trạng thái") != "Đã hủy")
                        if st.button("🗑 Hủy / Xóa phiếu",
                                     key=f"sc_delete_phieu_{drawer_ma}",
                                     disabled=delete_disabled,
                                     help=("Hủy HĐ APSC trước"
                                           if delete_disabled else "Xóa phiếu (PR4)"),
                                     use_container_width=True):
                            st.toast("PR4 sẽ thêm confirm dialog — "
                                     "tạm dùng tab 'Chi tiết / Cập nhật'",
                                     icon="ℹ️")

    # ══════════════════════════════════════════════════════════
    # TAB 2 — TẠO PHIẾU MỚI
    # ══════════════════════════════════════════════════════════
    with tab_create:
        cnt = st.session_state.get("sc_create_count", 0)

        # ── Header thông tin tạo phiếu ──
        col_h1, col_h2 = st.columns([2, 1])
        with col_h1:
            ma_du_kien = _preview_next_ma_phieu()
            st.markdown(
                f'<div class="sc-card" style="background:#f4f6fa;border-color:#d6def0;">'
                f'<div style="font-size:0.78rem;color:#777;">Mã phiếu dự kiến (tạm tính)</div>'
                f'<div style="font-size:1.3rem;font-weight:700;color:#2E86DE;'
                f'font-family:monospace;">{ma_du_kien}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with col_h2:
            cn_create = active
            if is_ke_toan_or_admin() and len(accessible) > 1:
                cn_create = st.selectbox("Chi nhánh tiếp nhận:", accessible,
                                         index=accessible.index(active) if active in accessible else 0,
                                         key=f"sc_cn_create_{cnt}")
            else:
                st.markdown(
                    f'<div class="sc-card" style="background:#fff8f8;border-color:#f5b5a8;">'
                    f'<div style="font-size:0.78rem;color:#777;">Chi nhánh</div>'
                    f'<div style="font-size:1rem;font-weight:600;color:#1a1a2e;">📍 {cn_create}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # ── Section: Thông tin khách hàng ──
        st.markdown(
            '<div class="sc-section-title">👤 Thông tin khách hàng</div>',
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            sdt_khach = st.text_input("Số điện thoại: *", key=f"sc_sdt_kh_{cnt}",
                                       placeholder="0xxx xxx xxx")
            sdt_prev_key = f"sc_sdt_prev_{cnt}"
            ten_key      = f"sc_ten_kh_{cnt}"
            kh_key       = f"sc_kh_found_{cnt}"
            if sdt_khach.strip() != st.session_state.get(sdt_prev_key, ""):
                st.session_state[sdt_prev_key] = sdt_khach.strip()
                kh_found = lookup_khach_hang(sdt_khach) if sdt_khach.strip() else None
                st.session_state[kh_key] = kh_found
                if kh_found:
                    st.session_state[ten_key] = kh_found["ten_kh"]
                else:
                    st.session_state[ten_key] = ""
                st.rerun()
            kh_found = st.session_state.get(kh_key)
            if sdt_khach.strip() and not kh_found:
                st.caption("⚠️ SĐT chưa có — khách mới sẽ được lưu tự động")
            elif kh_found:
                st.caption(f"✓ Khách cũ: **{kh_found['ten_kh']}**")
        with c2:
            ten_khach = st.text_input("Tên khách hàng: *", key=ten_key)

        # ── Section: Thông tin đồng hồ ──
        st.markdown(
            '<div class="sc-section-title">⌚ Thông tin đồng hồ</div>',
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            hieu_dh  = st.text_input("Hiệu đồng hồ:", key=f"sc_hieu_dh_{cnt}",
                                      placeholder="Casio, Citizen, Seiko...")
            loai_yc   = st.selectbox("Loại yêu cầu:", LOAI_YC_LIST, key=f"sc_loai_yc_{cnt}")
        with c2:
            dac_diem = st.text_input("Đặc điểm (IMEI / mô tả):", key=f"sc_dac_diem_{cnt}",
                                      placeholder="Số serial, màu sắc, trầy xước...")
            ngay_hen  = st.date_input("Ngày hẹn trả:", key=f"sc_ngay_hen_{cnt}",
                                       value=None, format="DD/MM/YYYY")

        mo_ta = st.text_area("Mô tả lỗi / yêu cầu: *", key=f"sc_mo_ta_{cnt}",
                              placeholder="Mô tả chi tiết tình trạng đồng hồ...",
                              height=80)

        # ── Section: Thanh toán & Ghi chú ──
        st.markdown(
            '<div class="sc-section-title">💰 Thanh toán & Ghi chú</div>',
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            tra_truoc = st.number_input("Khách trả trước (đ):", min_value=0, step=10000,
                                         key=f"sc_tra_truoc_{cnt}", value=0)
            if tra_truoc > 0:
                st.caption(f"= {int(tra_truoc):,}đ".replace(",","."))
        with c2:
            ghi_chu   = st.text_area("Ghi chú nội bộ:", key=f"sc_ghi_chu_nb_{cnt}",
                                      placeholder="Thợ kỹ thuật ghi chú...",
                                      height=80)

        # ── Section: Dịch vụ / Linh kiện dự kiến ──
        st.markdown(
            '<div class="sc-section-title">🔧 Dịch vụ / Linh kiện dự kiến '
            '<span style="font-weight:400;color:#888;font-size:0.82rem;">'
            '(có thể bỏ trống — thêm sau khi thợ đánh giá)</span></div>',
            unsafe_allow_html=True
        )
        items_key = f"sc_items_{cnt}"
        st.session_state.setdefault(items_key, [])
        with st.expander(f"Danh sách ({len(st.session_state[items_key])} mục)",
                          expanded=len(st.session_state[items_key]) > 0):
            _hien_thi_items(items_key)
            st.markdown("---")
            _widget_them_dv(f"sc_new_{cnt}", items_key)

        items = st.session_state.get(items_key, [])
        if items:
            tong = sum(x["so_luong"] * x["don_gia"] for x in items)
            st.markdown(
                f'<div class="sc-money-card sc-money-card-red" style="margin-top:10px;">'
                f'<div class="sc-money-label">Tổng dự kiến</div>'
                f'<div class="sc-money-value sc-money-value-red">'
                f'{tong:,}đ</div></div>'.replace(",","."),
                unsafe_allow_html=True
            )

        st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
        can_create = ten_khach.strip() and sdt_khach.strip() and mo_ta.strip()
        if st.button("✅ Tạo phiếu & In", type="primary", use_container_width=True,
                     disabled=not can_create):
            try:
                ma = _gen_ma_phieu()
                supabase.table("phieu_sua_chua").insert({
                    "ma_phieu": ma, "chi_nhanh": cn_create,
                    "ten_khach": ten_khach.strip(), "sdt_khach": sdt_khach.strip(),
                    "loai_yeu_cau": loai_yc, "hieu_dong_ho": hieu_dh.strip() or None,
                    "dac_diem": dac_diem.strip() or None, "mo_ta_loi": mo_ta.strip(),
                    "khach_tra_truoc": int(tra_truoc), "ghi_chu_noi_bo": ghi_chu.strip() or None,
                    "trang_thai": "Đang sửa", "nguoi_tiep_nhan": ho_ten,
                    "ngay_hen_tra": ngay_hen.isoformat() if ngay_hen else None,
                    "created_by": user.get("username",""),
                    "created_at": now_vn_iso(),
                    "updated_at": now_vn_iso(),
                }).execute()
                if items:
                    supabase.table("phieu_sua_chua_chi_tiet").insert(
                        [{"ma_phieu": ma, **item} for item in items]
                    ).execute()

                _upsert_khach_hang(ten_khach.strip(), sdt_khach.strip(), cn_create)

                ct_new = pd.DataFrame(items) if items else pd.DataFrame()
                if not ct_new.empty:
                    for col in ["so_luong","don_gia"]:
                        ct_new[col] = pd.to_numeric(ct_new[col], errors="coerce").fillna(0).astype(int)
                phieu_data = {
                    "ma_phieu": ma, "chi_nhanh": cn_create,
                    "ten_khach": ten_khach.strip(),
                    "sdt_khach": sdt_khach.strip(), "hieu_dong_ho": hieu_dh.strip(),
                    "loai_yeu_cau": loai_yc, "dac_diem": dac_diem.strip(),
                    "mo_ta_loi": mo_ta.strip(), "khach_tra_truoc": int(tra_truoc),
                    "ngay_hen_tra": str(ngay_hen) if ngay_hen else None,
                    "nguoi_tiep_nhan": ho_ten,
                    "Ngày TN": now_vn().strftime("%d/%m/%Y %H:%M"),
                }
                st.session_state["sc_pending_print_html"] = _build_phieu_html(phieu_data, ct_new)

                st.session_state["sc_create_count"] = cnt + 1
                st.session_state["sc_active_ma"] = ma
                st.cache_data.clear()
                log_action("SC_CREATE", f"ma={ma} kh={ten_khach} cn={cn_create}")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi tạo phiếu: {e}")

        if st.session_state.get("sc_pending_print_html"):
            _in_phieu_sc(st.session_state.pop("sc_pending_print_html"), key="sc_print_new")
            st.success(f"✓ Đã tạo phiếu — cửa sổ in đang mở")

    # ══════════════════════════════════════════════════════════
    # TAB 3 — CHI TIẾT / CẬP NHẬT (theo mẫu ChatGPT)
    # ══════════════════════════════════════════════════════════
    with tab_detail:
        # Scroll lên đầu sau khi lưu cập nhật
        if st.session_state.pop("sc_scroll_top", False):
            st.components.v1.html(
                "<script>window.parent.document.querySelector('section.main').scrollTo(0,0);</script>",
                height=0
            )
        df_all = _load_phieu(tuple(accessible))
        df_chua_xong = df_all[df_all["trang_thai"] != "Hoàn thành"].copy() if not df_all.empty else df_all
        if df_chua_xong.empty:
            st.info("Không có phiếu nào đang xử lý.")
        else:
            # ── Search + Select cùng 1 hàng ──
            col_s, col_p = st.columns([1, 1])
            with col_s:
                search_dt = st.text_input("Tìm kiếm / Mã phiếu / Tên khách:", key="sc_search_dt",
                                           placeholder="VD: '900' hoặc 'SC000900'...")
            df_filtered = df_chua_xong.copy()
            if search_dt.strip():
                s = search_dt.strip().lower()
                mask = (df_filtered["ma_phieu"].apply(lambda m: _sc_match_ma(m, s)) |
                        df_filtered["sdt_khach"].astype(str).str.lower().str.contains(s, na=False) |
                        df_filtered["ten_khach"].astype(str).str.lower().str.contains(s, na=False))
                df_filtered = df_filtered[mask]

            if df_filtered.empty:
                st.info("Không tìm thấy phiếu phù hợp.")
            else:
                opts = [f"{r['ma_phieu']} · {r.get('ten_khach','')} · {r.get('trang_thai','')}"
                        for _, r in df_filtered.iterrows()]

                # Determine target pick:
                # 1) search filter narrow xuống 1 → auto-pick (user gõ mã chính xác)
                # 2) khôi phục saved selection nếu vẫn còn trong filtered opts
                target_pick = None
                if search_dt.strip() and len(opts) == 1:
                    target_pick = opts[0]
                else:
                    saved = st.session_state.get("sc_active_ma")
                    if saved:
                        for o in opts:
                            if o.startswith(saved):
                                target_pick = o
                                break

                # Sync session_state TRƯỚC khi widget render (override stale pick)
                pick_key = "sc_detail_pick"
                cur_state = st.session_state.get(pick_key)
                if target_pick and cur_state != target_pick:
                    st.session_state[pick_key] = target_pick
                elif cur_state and cur_state not in opts:
                    st.session_state[pick_key] = None

                with col_p:
                    picked = st.selectbox(
                        "Chọn phiếu:", opts,
                        index=opts.index(target_pick) if target_pick in opts else None,
                        placeholder="Chọn phiếu để xem chi tiết...",
                        key=pick_key,
                    )
                if not picked:
                    st.info("Chọn phiếu từ danh sách trên để xem chi tiết.")
                else:
                    ma_pick = picked.split(" · ")[0]
                    st.session_state["sc_active_ma"] = ma_pick

                    phieu_row = df_chua_xong[df_chua_xong["ma_phieu"] == ma_pick].iloc[0]
                    phieu = {k: (None if pd.isna(v) else v)
                             for k, v in phieu_row.to_dict().items()}
                    ct    = _load_chi_tiet(ma_pick)

                    # ── Header phiếu với badge trạng thái ──
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;'
                        f'align-items:center;margin:18px 0 10px;">'
                        f'<div>'
                        f'<div style="font-size:1.25rem;font-weight:700;color:#1a1a2e;">'
                        f'{ma_pick} — {phieu.get("ten_khach","")}</div>'
                        f'<div style="font-size:0.85rem;color:#777;">'
                        f'📞 {phieu.get("sdt_khach","")}</div>'
                        f'</div>'
                        f'<div>{_badge_status_html(phieu.get("trang_thai",""))}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                    # ── Layout 2 cột: Thông tin khách + Chi tiết DV ──
                    col_left, col_right = st.columns([1, 1])

                    with col_left:
                        # Card thông tin tiếp nhận
                        info_html = (
                            '<div class="sc-card">'
                            '<div class="sc-card-header">📋 Thông tin tiếp nhận</div>'
                        )
                        rows = [
                            ("Chi nhánh", phieu.get("chi_nhanh","")),
                            ("Hiệu ĐH", phieu.get("hieu_dong_ho") or "—"),
                            ("Đặc điểm", phieu.get("dac_diem") or "—"),
                            ("Loại YC", phieu.get("loai_yeu_cau","")),
                            ("NV tiếp nhận", phieu.get("nguoi_tiep_nhan") or "—"),
                            ("Ngày TN", phieu.get("Ngày TN","—")),
                            ("Hẹn trả", phieu.get("ngay_hen_tra") or "—"),
                        ]
                        for label, val in rows:
                            info_html += (
                                f'<div class="sc-info-row">'
                                f'<div class="sc-info-label">{label}:</div>'
                                f'<div class="sc-info-val">{val}</div>'
                                f'</div>'
                            )
                        info_html += '</div>'
                        st.markdown(info_html, unsafe_allow_html=True)

                        # Card mô tả lỗi
                        desc_html = (
                            '<div class="sc-card">'
                            '<div class="sc-card-header">📝 Mô tả lỗi / Ghi chú</div>'
                            f'<div style="font-size:0.92rem;color:#1a1a2e;line-height:1.5;">'
                            f'{phieu.get("mo_ta_loi","") or "—"}</div>'
                        )
                        if phieu.get("ghi_chu_noi_bo"):
                            desc_html += (
                                f'<div style="margin-top:8px;padding-top:8px;'
                                f'border-top:1px dashed #ddd;">'
                                f'<div style="font-size:0.78rem;color:#888;">Ghi chú nội bộ:</div>'
                                f'<div style="font-size:0.88rem;color:#555;">'
                                f'{phieu.get("ghi_chu_noi_bo","")}</div>'
                                f'</div>'
                            )
                        desc_html += '</div>'
                        st.markdown(desc_html, unsafe_allow_html=True)

                    with col_right:
                        # Card dịch vụ / linh kiện
                        st.markdown(
                            '<div class="sc-card-header" style="margin-top:8px;">'
                            '🔧 Dịch vụ / Linh kiện</div>',
                            unsafe_allow_html=True
                        )
                        if not ct.empty:
                            ct["Thành tiền"] = ct["so_luong"] * ct["don_gia"]
                            ct_view = ct.rename(columns={
                                "loai_dong": "Loại", "ten_hang": "Tên", "ma_hang": "Mã",
                                "so_luong": "SL", "don_gia": "Đơn giá"
                            })
                            vcols = ["Loại", "Tên", "Mã", "SL", "Đơn giá", "Thành tiền"]
                            vcols = [c for c in vcols if c in ct_view.columns]
                            st.dataframe(ct_view[vcols], use_container_width=True, hide_index=True,
                                         height=min(280, 42 + len(ct_view) * 35))

                            # 3 metric cards
                            tong = int(ct["Thành tiền"].sum())
                            tra_truoc = int(phieu.get("khach_tra_truoc", 0))
                            con_lai = tong - tra_truoc

                            m1, m2, m3 = st.columns(3)
                            with m1:
                                st.markdown(
                                    f'<div class="sc-money-card">'
                                    f'<div class="sc-money-label">Tổng cộng</div>'
                                    f'<div class="sc-money-value">{tong:,}đ</div>'
                                    f'</div>'.replace(",","."),
                                    unsafe_allow_html=True
                                )
                            with m2:
                                st.markdown(
                                    f'<div class="sc-money-card">'
                                    f'<div class="sc-money-label">Đã trả trước</div>'
                                    f'<div class="sc-money-value">{tra_truoc:,}đ</div>'
                                    f'</div>'.replace(",","."),
                                    unsafe_allow_html=True
                                )
                            with m3:
                                st.markdown(
                                    f'<div class="sc-money-card sc-money-card-red">'
                                    f'<div class="sc-money-label">Còn lại</div>'
                                    f'<div class="sc-money-value sc-money-value-red">'
                                    f'{con_lai:,}đ</div>'
                                    f'</div>'.replace(",","."),
                                    unsafe_allow_html=True
                                )
                        else:
                            st.caption("_Chưa có dịch vụ / linh kiện nào_")

                    # ── Section: Cập nhật phiếu ──
                    if "sc_upd_open" not in st.session_state:
                        st.session_state["sc_upd_open"] = False
                    if (st.session_state.get("sc_upd_dv_ma_tim", "").strip()
                            or st.session_state.get("sc_upd_items", [])):
                        st.session_state["sc_upd_open"] = True

                    st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)

                    with st.expander("✏️ Cập nhật phiếu", expanded=st.session_state["sc_upd_open"]):
                        cur_tt = phieu.get("trang_thai", "Đang sửa")

                        col_u1, col_u2 = st.columns(2)
                        with col_u1:
                            new_tt = st.selectbox("Trạng thái:", TRANG_THAI_LIST,
                                                  index=TRANG_THAI_LIST.index(cur_tt) if cur_tt in TRANG_THAI_LIST else 0,
                                                  key="sc_upd_tt")
                        with col_u2:
                            new_hen = st.date_input("Ngày hẹn trả:", key="sc_upd_hen",
                                                     value=pd.to_datetime(phieu["ngay_hen_tra"]).date()
                                                     if phieu.get("ngay_hen_tra") else None,
                                                     format="DD/MM/YYYY")

                        new_gc  = st.text_area("Ghi chú nội bộ:", value=phieu.get("ghi_chu_noi_bo") or "",
                                                key="sc_upd_gc", height=80)

                        # Dịch vụ đã lưu
                        if not ct.empty:
                            st.markdown(
                                '<div class="sc-section-title" style="margin-top:14px;">'
                                'Dịch vụ / Linh kiện đã lưu</div>',
                                unsafe_allow_html=True
                            )
                            for _, row in ct.iterrows():
                                ci1, ci2, ci3, ci4, ci5 = st.columns([2, 4, 1, 2, 1])
                                with ci1:
                                    st.markdown(f"<span style='font-size:0.9rem'>{row.get('loai_dong','')}</span>", unsafe_allow_html=True)
                                with ci2:
                                    st.markdown(f"<span style='font-size:0.9rem'>{row.get('ten_hang','')}</span>", unsafe_allow_html=True)
                                with ci3:
                                    st.markdown(f"<span style='font-size:0.9rem'>x{int(row.get('so_luong',1))}</span>", unsafe_allow_html=True)
                                with ci4:
                                    st.markdown(f"<span style='font-size:0.9rem'>{int(row.get('don_gia',0)):,}đ</span>".replace(",","."), unsafe_allow_html=True)
                                with ci5:
                                    if st.button("✕", key=f"del_ct_{row['id']}"):
                                        try:
                                            supabase.table("phieu_sua_chua_chi_tiet").delete() \
                                                .eq("id", int(row["id"])).execute()
                                            st.cache_data.clear()
                                            log_action("SC_DEL_ITEM", f"ma={ma_pick} item={row.get('ten_hang','')}")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Lỗi xóa: {e}")

                        # Thêm dịch vụ mới
                        st.markdown(
                            '<div class="sc-section-title" style="margin-top:14px;">'
                            '➕ Thêm dịch vụ / Linh kiện</div>',
                            unsafe_allow_html=True
                        )
                        _widget_them_dv("sc_upd_dv", "sc_upd_items")
                        upd_items = st.session_state.get("sc_upd_items", [])
                        _hien_thi_items("sc_upd_items")
                        if upd_items:
                            tong_moi = sum(x["so_luong"] * x["don_gia"] for x in upd_items)
                            st.caption(f"Tổng dịch vụ mới thêm: **{tong_moi:,}đ**".replace(",","."))

                        st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
                        if st.button("💾 Lưu cập nhật", type="primary", use_container_width=True, key="sc_save_upd"):
                            try:
                                supabase.table("phieu_sua_chua").update({
                                    "trang_thai":     new_tt,
                                    "ghi_chu_noi_bo": new_gc.strip() or None,
                                    "ngay_hen_tra":   new_hen.isoformat() if new_hen else None,
                                    "updated_at":     now_vn_iso(),
                                }).eq("ma_phieu", ma_pick).execute()

                                new_items = st.session_state.get("sc_upd_items", [])
                                if new_items:
                                    supabase.table("phieu_sua_chua_chi_tiet").insert(
                                        [{"ma_phieu": ma_pick, **item} for item in new_items]
                                    ).execute()
                                    st.session_state["sc_upd_items"] = []

                                st.cache_data.clear()
                                log_action("SC_UPDATE", f"ma={ma_pick} trang_thai={new_tt}")
                                st.session_state["sc_upd_open"] = False
                                st.session_state["sc_scroll_top"] = True
                                st.success("✓ Đã cập nhật!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi: {e}")

                    # ── Action buttons ──
                    st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
                    col_a1, col_a2 = st.columns(2)
                    with col_a1:
                        if st.button("🖨️ In phiếu (A5)", use_container_width=True, key="sc_print_detail"):
                            _in_phieu_sc(_build_phieu_html(dict(phieu), ct), key="sc_print_d")

                    with col_a2:
                        if is_admin():
                            if st.button("🗑️ Hủy / Xóa phiếu này", type="secondary",
                                         use_container_width=True, key="sc_delete"):
                                try:
                                    supabase.table("phieu_sua_chua_chi_tiet").delete() \
                                        .eq("ma_phieu", ma_pick).execute()
                                    supabase.table("phieu_sua_chua").delete() \
                                        .eq("ma_phieu", ma_pick).execute()
                                    st.session_state.pop("sc_active_ma", None)
                                    st.cache_data.clear()
                                    log_action("SC_DELETE", f"ma={ma_pick}", level="warning")
                                    st.success("Đã xóa phiếu."); st.rerun()
                                except Exception as e:
                                    st.error(f"Lỗi xóa: {e}")

    # ══════════════════════════════════════════════════════════
    # TAB 4 — TẠO HÓA ĐƠN SỬA
    # ══════════════════════════════════════════════════════════
    with tab_hoadon:
        df_all_hd = _load_phieu(tuple(accessible))
        cho_giao = df_all_hd[df_all_hd["trang_thai"] == "Chờ giao khách"].copy() \
            if not df_all_hd.empty else pd.DataFrame()

        if cho_giao.empty:
            st.info("Không có phiếu nào ở trạng thái **Chờ giao khách**.")
            st.caption("Cập nhật trạng thái phiếu sang 'Chờ giao khách' ở tab Chi tiết / Cập nhật trước.")
        else:
            # ── Search + Select phiếu ──
            opts_hd = [f"{r['ma_phieu']} · {r.get('ten_khach','')} · {r.get('sdt_khach','')}"
                       for _, r in cho_giao.iterrows()]

            col_sh, col_ph = st.columns([1, 1])
            with col_sh:
                search_hd = st.text_input("Tìm SĐT / Mã phiếu / Tên khách:", key="sc_hd_search",
                                           placeholder="VD: '900' tìm SC000900...")
            if search_hd.strip():
                s_hd = search_hd.strip().lower()
                def _match_opt_hd(opt: str) -> bool:
                    # opt format: "ma_phieu · ten_khach · ..." — match any field
                    if s_hd in opt.lower():
                        return True
                    ma_part = opt.split(" · ", 1)[0] if " · " in opt else opt
                    return _sc_match_ma(ma_part, s_hd)
                opts_hd = [o for o in opts_hd if _match_opt_hd(o)]
                if not opts_hd:
                    st.warning("Không tìm thấy phiếu phù hợp.")
                    st.stop()

            with col_ph:
                picked_hd = st.selectbox("Chọn phiếu:", opts_hd, index=None,
                                          placeholder="Chọn phiếu để tạo hóa đơn...",
                                          key="sc_hd_pick")
            if not picked_hd:
                st.info("Chọn phiếu từ danh sách trên để tạo hóa đơn.")
            else:
                ma_hd_pick = picked_hd.split(" · ")[0]

                phieu_hd_row = cho_giao[cho_giao["ma_phieu"] == ma_hd_pick].iloc[0]
                phieu_hd = {k: (None if pd.isna(v) else v)
                            for k, v in phieu_hd_row.to_dict().items()}
                ct_hd    = _load_chi_tiet(ma_hd_pick)

                # ── Header phiếu chọn ──
                st.markdown(
                    f'<div class="sc-card" style="margin-top:14px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<div>'
                    f'<div class="sc-card-header">{ma_hd_pick} — {phieu_hd.get("ten_khach","")}</div>'
                    f'<div class="sc-card-sub">📞 {phieu_hd.get("sdt_khach","")}'
                    f' · ⌚ {phieu_hd.get("hieu_dong_ho") or "—"}</div>'
                    f'</div>'
                    f'<div>{_badge_status_html("Chờ giao khách")}</div>'
                    f'</div>'
                    f'<div style="margin-top:8px;font-size:0.88rem;color:#555;">'
                    f'<b>Mô tả:</b> {phieu_hd.get("mo_ta_loi","") or "—"}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # ── Bảng dịch vụ ──
                if ct_hd.empty:
                    st.warning("Phiếu chưa có dịch vụ/linh kiện nào. Thêm trước ở tab Chi tiết.")
                else:
                    st.markdown(
                        '<div class="sc-section-title">🔧 Chi tiết dịch vụ / linh kiện</div>',
                        unsafe_allow_html=True
                    )
                    ct_hd["Thành tiền"] = ct_hd["so_luong"] * ct_hd["don_gia"]
                    ct_view = ct_hd.rename(columns={
                        "ten_hang": "Tên", "ma_hang": "Mã",
                        "so_luong": "SL", "don_gia": "Đơn giá"
                    })
                    vcols = ["Tên", "Mã", "SL", "Đơn giá", "Thành tiền"]
                    vcols = [c for c in vcols if c in ct_view.columns]
                    st.dataframe(ct_view[vcols], use_container_width=True, hide_index=True)

                tong_dv = int(ct_hd["Thành tiền"].sum()) if not ct_hd.empty else 0
                tra_truoc = int(phieu_hd.get("khach_tra_truoc", 0))

                # ── Section: Thông tin hóa đơn ──
                st.markdown(
                    '<div class="sc-section-title">💰 Thông tin hóa đơn</div>',
                    unsafe_allow_html=True
                )

                giam_gia = st.number_input("Giảm giá (đ):", min_value=0, step=10000,
                                            value=0, key="sc_hd_giam")
                if giam_gia > 0:
                    st.caption(f"= {int(giam_gia):,}đ".replace(",","."))

                can_tra = max(0, tong_dv - giam_gia - tra_truoc)

                # ── 3 metric cards ──
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.markdown(
                        f'<div class="sc-money-card">'
                        f'<div class="sc-money-label">Tổng dịch vụ</div>'
                        f'<div class="sc-money-value">{tong_dv:,}đ</div>'
                        f'</div>'.replace(",","."),
                        unsafe_allow_html=True
                    )
                with m2:
                    st.markdown(
                        f'<div class="sc-money-card">'
                        f'<div class="sc-money-label">Giảm giá + Trả trước</div>'
                        f'<div class="sc-money-value">{giam_gia + tra_truoc:,}đ</div>'
                        f'</div>'.replace(",","."),
                        unsafe_allow_html=True
                    )
                with m3:
                    st.markdown(
                        f'<div class="sc-money-card sc-money-card-red">'
                        f'<div class="sc-money-label">Khách cần trả</div>'
                        f'<div class="sc-money-value sc-money-value-red">{can_tra:,}đ</div>'
                        f'</div>'.replace(",","."),
                        unsafe_allow_html=True
                    )

                # ── Phương thức thanh toán ──
                st.markdown(
                    '<div class="sc-section-title">💳 Phương thức thanh toán</div>',
                    unsafe_allow_html=True
                )

                chia_pttt = st.checkbox("Chia nhiều phương thức", key="sc_hd_chia",
                                         help="Bật để chia tiền giữa các phương thức")

                if not chia_pttt:
                    pttt_chon = st.radio("PTTT:", ["Tiền mặt", "Chuyển khoản", "Thẻ"],
                                          horizontal=True, key="sc_hd_pttt",
                                          label_visibility="collapsed")
                    pttt = {
                        "tien_mat":      can_tra if pttt_chon == "Tiền mặt" else 0,
                        "chuyen_khoan":  can_tra if pttt_chon == "Chuyển khoản" else 0,
                        "the":           can_tra if pttt_chon == "Thẻ" else 0,
                    }
                else:
                    p1, p2, p3 = st.columns(3)
                    with p1:
                        tm = st.number_input("Tiền mặt:", min_value=0, step=10000,
                                              value=can_tra, key="sc_hd_tm")
                        if tm > 0: st.caption(f"= {int(tm):,}đ".replace(",","."))
                    with p2:
                        ck = st.number_input("Chuyển khoản:", min_value=0, step=10000,
                                              value=0, key="sc_hd_ck")
                        if ck > 0: st.caption(f"= {int(ck):,}đ".replace(",","."))
                    with p3:
                        the = st.number_input("Thẻ:", min_value=0, step=10000,
                                               value=0, key="sc_hd_the")
                        if the > 0: st.caption(f"= {int(the):,}đ".replace(",","."))
                    tong_pttt = tm + ck + the
                    lech = tong_pttt - can_tra
                    if lech != 0:
                        lech_label = f"Dư: +{lech:,}đ" if lech > 0 else f"Thiếu: {lech:,}đ"
                        st.warning(
                            f"Tổng cần trả: **{can_tra:,}đ** &nbsp;|&nbsp; "
                            f"Đã nhập: **{tong_pttt:,}đ** &nbsp;|&nbsp; {lech_label}".replace(",",".")
                        )
                    pttt = {"tien_mat": tm, "chuyen_khoan": ck, "the": the}

                st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
                if st.button("✅ Tạo hóa đơn APSC", type="primary",
                              use_container_width=True, key="sc_hd_create",
                              disabled=ct_hd.empty):
                    try:
                        apsc_ma = _tao_hoa_don_apsc(dict(phieu_hd), ct_hd, giam_gia, pttt)
                        supabase.table("phieu_sua_chua").update({
                            "trang_thai": "Hoàn thành",
                            "updated_at": (now_vn()).isoformat(),
                        }).eq("ma_phieu", ma_hd_pick).execute()
                        st.cache_data.clear()
                        log_action("SC_HOA_DON", f"ma={ma_hd_pick} apsc={apsc_ma}")
                        st.session_state.pop("sc_hd_pick", None)
                        st.success(f"✓ Đã tạo hóa đơn **{apsc_ma}** — phiếu chuyển sang Hoàn thành!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi tạo hóa đơn: {e}")

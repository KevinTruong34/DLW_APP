import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import numpy as np
import logging

from utils.helpers import now_vn, now_vn_iso, today_vn, fmt_vn
from utils.config import ALL_BRANCHES, IN_APP_MARKER, ARCHIVED_MARKER

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger("watchstore")


def log_action(action: str, detail: str = "", level: str = "info"):
    user = st.session_state.get("user") or {}
    cn   = st.session_state.get("active_chi_nhanh", "-")
    username = user.get("username", "anonymous")
    ho_ten   = user.get("ho_ten", "")
    prefix = f"[{username}@{cn}]"
    msg = f"{prefix} {action}"
    if detail:
        msg += f" — {detail}"
    getattr(_logger, level, _logger.info)(msg)
    try:
        supabase.table("action_logs").insert({
            "username":  username,
            "ho_ten":    ho_ten,
            "chi_nhanh": cn,
            "action":    action,
            "detail":    detail or None,
            "level":     level,
        }).execute()
    except Exception:
        pass  # Không để lỗi log làm crash app


# ── Supabase client ──
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error("Chưa cấu hình SUPABASE_URL và SUPABASE_KEY trong Streamlit Secrets!")
    st.stop()


def call_rpc(name: str, params: dict | None = None):
    """Generic Supabase RPC wrapper. Returns res.data as-is (dict for jsonb RPCs)."""
    res = supabase.rpc(name, params or {}).execute()
    return res.data


def load_all_nhan_vien(include_inactive: bool = False) -> list[dict]:
    """Load NV danh sách. include_inactive=True để admin chọn cả NV đã nghỉ."""
    q = supabase.table("nhan_vien").select("id, ho_ten, username, role, active")
    if not include_inactive:
        q = q.eq("active", True)
    res = q.order("ho_ten").execute()
    return res.data or []


def search_hd_pos_for_edit(
    chi_nhanh: str | None = None,
    ngay_tu: str | None = None,
    ngay_den: str | None = None,
    nguoi_ban_id: int | None = None,
    ma_hd_search: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Tìm HĐ POS để admin chọn sửa. Chỉ trả HĐ trang_thai='Hoàn thành'.

    Default UI filter: 7 ngày gần nhất (caller pass ngay_tu).
    """
    q = (
        supabase.table("hoa_don_pos")
        .select("ma_hd, chi_nhanh, created_at, nguoi_ban, nguoi_ban_id, "
                "khach_can_tra, ten_khach, sdt_khach, trang_thai, is_admin_created")
        .eq("trang_thai", "Hoàn thành")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if chi_nhanh:
        q = q.eq("chi_nhanh", chi_nhanh)
    if ngay_tu:
        q = q.gte("created_at", ngay_tu)
    if ngay_den:
        q = q.lte("created_at", ngay_den)
    if nguoi_ban_id:
        q = q.eq("nguoi_ban_id", nguoi_ban_id)
    if ma_hd_search:
        q = q.ilike("ma_hd", f"%{ma_hd_search}%")
    res = q.execute()
    return res.data or []


def load_hd_with_edit_history(ma_hd: str) -> dict:
    """Load HĐ + items + edit_count + edit_history qua RPC load_record_with_history.

    Backward-compat wrapper (B2a interface). B2b chuyển backend từ
    load_hd_pos_with_history → generic load_record_with_history(table_name, record_id).
    Shape return không đổi — UI code không cần sửa.
    """
    return load_record_with_history("hoa_don_pos", ma_hd)


def load_record_with_history(table_name: str, record_id: str) -> dict:
    """Generic loader cho 3 loại phiếu (HĐ POS / đổi-trả / sửa chữa).

    table_name: 'hoa_don_pos' | 'phieu_doi_tra_pos' | 'phieu_sua_chua'
    Returns: {header, items, edit_count, edit_history} — shape thống nhất.
    """
    res = supabase.rpc("load_record_with_history", {
        "p_table_name": table_name,
        "p_record_id": record_id,
    }).execute()
    return res.data or {}


def search_pdt_for_edit(
    chi_nhanh: str | None = None,
    ngay_tu: str | None = None,
    ngay_den: str | None = None,
    ma_pdt_search: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Tìm phiếu đổi/trả Hoàn thành để admin chọn sửa."""
    q = (
        supabase.table("phieu_doi_tra_pos")
        .select("ma_pdt, ma_hd_goc, chi_nhanh, created_at, nguoi_tao, nguoi_tao_id, "
                "loai_phieu, tien_hang_tra, tien_hang_moi, chenh_lech, "
                "ten_khach, sdt_khach, trang_thai, is_admin_created")
        .eq("trang_thai", "Hoàn thành")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if chi_nhanh:
        q = q.eq("chi_nhanh", chi_nhanh)
    if ngay_tu:
        q = q.gte("created_at", ngay_tu)
    if ngay_den:
        q = q.lte("created_at", ngay_den)
    if ma_pdt_search:
        q = q.ilike("ma_pdt", f"%{ma_pdt_search}%")
    res = q.execute()
    return res.data or []


def search_sc_for_edit(
    chi_nhanh: str | None = None,
    trang_thai: str | None = None,
    ngay_tu: str | None = None,
    ngay_den: str | None = None,
    ma_phieu_search: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Tìm phiếu sửa chữa để admin chọn sửa.

    trang_thai=None → mọi trạng thái TRỪ 'Đã hủy' (default).
    Pass cụ thể (vd 'Đang sửa') để filter chính xác.
    """
    q = (
        supabase.table("phieu_sua_chua")
        .select("ma_phieu, chi_nhanh, created_at, ten_khach, sdt_khach, "
                "loai_yeu_cau, hieu_dong_ho, trang_thai, "
                "ngay_hen_tra, nguoi_tiep_nhan, is_admin_created")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if trang_thai:
        q = q.eq("trang_thai", trang_thai)
    else:
        q = q.neq("trang_thai", "Đã hủy")
    if chi_nhanh:
        q = q.eq("chi_nhanh", chi_nhanh)
    if ngay_tu:
        q = q.gte("created_at", ngay_tu)
    if ngay_den:
        q = q.lte("created_at", ngay_den)
    if ma_phieu_search:
        q = q.ilike("ma_phieu", f"%{ma_phieu_search}%")
    res = q.execute()
    return res.data or []


def has_active_pdt_for_hd(ma_hd: str) -> int:
    """Đếm số phiếu đổi/trả active (KHÔNG bao gồm 'Đã hủy') ref đến ma_hd này."""
    res = (
        supabase.table("phieu_doi_tra_pos")
        .select("ma_pdt", count="exact")
        .eq("ma_hd_goc", ma_hd)
        .neq("trang_thai", "Đã hủy")
        .execute()
    )
    return res.count or 0


@st.cache_data(ttl=300)
def load_hoa_don(branches_key: tuple):
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("hoa_don").select("*") \
            .in_("Chi nhánh", list(branches_key)) \
            .range(offset, offset+batch-1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    tong = len(df); df = df.drop_duplicates()
    st.session_state["so_dong_trung"] = tong - len(df)
    for col in ["Tổng tiền hàng","Khách cần trả","Khách đã trả","Đơn giá","Thành tiền"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "Thời gian" in df.columns:
        df["_ngay"] = pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")
        df["_date"] = df["_ngay"].dt.date
    # Chuẩn hóa SĐT: bỏ .0, khôi phục số 0 đầu nếu mất (Excel lưu thành số)
    if "Điện thoại" in df.columns:
        def _fix_sdt(v):
            s = str(v).strip() if v is not None else ""
            if s in ("", "nan", "None"): return ""
            if s.endswith(".0"): s = s[:-2]
            # Số VN 9-10 chữ số, thêm 0 nếu thiếu
            digits = s.replace(" ", "")
            if digits.isdigit() and len(digits) == 9:
                digits = "0" + digits
            return digits
        df["Điện thoại"] = df["Điện thoại"].apply(_fix_sdt)
    return df


@st.cache_data(ttl=60)
def load_stock_deltas() -> dict:
    """
    [DEPRECATED — giữ để backward compat] Sau khi migrate sang single-source
    (the_kho là live data, mọi update qua RPC), không còn cần delta layer.
    Trả về dict rỗng để các caller cũ không bị break, nhưng không tính toán gì.
    """
    return {}


@st.cache_data(ttl=600)
def get_archive_reminder() -> dict:
    """
    Kiểm tra có cần nhắc admin kết sổ phiếu App không.

    Trả về dict:
      - need_reminder: True nếu thoả cả 2 điều kiện
      - n_active: số phiếu App (không phải dòng) đang active
      - days_oldest: số ngày kể từ phiếu App cũ nhất
      - oldest_date: ngày phiếu cũ nhất (date object)

    Điều kiện nhắc: > 30 ngày kể từ phiếu App cũ nhất chưa archive
                    VÀ có > 20 phiếu App active (đếm theo ma_phieu unique).
    """
    THRESHOLD_DAYS = 30
    THRESHOLD_PHIEU = 20

    try:
        res = supabase.table("phieu_chuyen_kho") \
            .select("ma_phieu, ngay_chuyen") \
            .eq("loai_phieu", IN_APP_MARKER) \
            .execute()
        if not res.data:
            return {"need_reminder": False, "n_active": 0,
                    "days_oldest": 0, "oldest_date": None}

        # Đếm số phiếu unique + tìm ngày cũ nhất
        unique_phieu = {}
        for r in res.data:
            ma = r.get("ma_phieu")
            ngay = r.get("ngay_chuyen")
            if ma and ngay and ma not in unique_phieu:
                unique_phieu[ma] = ngay

        n_active = len(unique_phieu)
        if n_active == 0:
            return {"need_reminder": False, "n_active": 0,
                    "days_oldest": 0, "oldest_date": None}

        oldest_iso = min(unique_phieu.values())
        oldest_dt = pd.to_datetime(oldest_iso, errors="coerce")
        if pd.isna(oldest_dt):
            return {"need_reminder": False, "n_active": n_active,
                    "days_oldest": 0, "oldest_date": None}

        days_oldest = (datetime.now() - oldest_dt.to_pydatetime()).days

        need = (days_oldest > THRESHOLD_DAYS) and (n_active > THRESHOLD_PHIEU)
        return {
            "need_reminder": need,
            "n_active": n_active,
            "days_oldest": days_oldest,
            "oldest_date": oldest_dt.date(),
        }
    except Exception:
        return {"need_reminder": False, "n_active": 0,
                "days_oldest": 0, "oldest_date": None}


@st.cache_data(ttl=300)
def load_the_kho(branches_key: tuple):
    """
    Load the_kho live data — sau migrate sang single-source.
    Mọi thay đổi tồn từ app (bán POS, chuyển hàng, nhận, đổi/trả, kiểm kê,
    sửa thủ công) đều update trực tiếp vào the_kho qua RPC.
    UI tồn = giá trị "Tồn cuối kì" trong DB (không cộng/trừ delta layer).
    """
    rows, batch, offset = [], 1000, 0
    while True:
        # FIX: thêm .order() để pagination ổn định, tránh trùng/sót rows
        res = supabase.table("the_kho").select("*") \
            .in_("Chi nhánh", list(branches_key)) \
            .order("Mã hàng").order("Chi nhánh") \
            .range(offset, offset+batch-1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["Tồn đầu kì","Giá trị đầu kì","Nhập NCC","Giá trị nhập NCC",
                "Xuất bán","Giá trị xuất bán","Tồn cuối kì","Giá trị cuối kì"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=600)
def load_hang_hoa() -> pd.DataFrame:
    """Master data sản phẩm — cache 10 phút."""
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("hang_hoa").select("*") \
        .neq("active", False) \
        .range(offset, offset + batch - 1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "gia_ban" in df.columns:
        df["gia_ban"] = pd.to_numeric(df["gia_ban"], errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=300)
def load_phieu_chuyen_kho(branches_key: tuple = None):
    """Load phiếu chuyển kho — filter theo chi nhánh (từ HOẶC tới)."""
    all_rows, batch, offset = [], 1000, 0
    while True:
        q = supabase.table("phieu_chuyen_kho").select("*") \
            .order("ngay_chuyen", desc=True)
        res = q.range(offset, offset + batch - 1).execute()
        if not res.data: break
        all_rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    if branches_key:
        bk = list(branches_key)
        mask = df["tu_chi_nhanh"].isin(bk) | df["toi_chi_nhanh"].isin(bk)
        df = df[mask].reset_index(drop=True)
    for col in ["so_luong_chuyen","so_luong_nhan","tong_sl_chuyen","tong_sl_nhan",
                "tong_mat_hang","gia_chuyen","thanh_tien_chuyen","thanh_tien_nhan","tong_gia_tri"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "ngay_chuyen" in df.columns:
        df["_ngay"] = pd.to_datetime(df["ngay_chuyen"], errors="coerce", utc=True) \
                       .dt.tz_convert("Asia/Ho_Chi_Minh")
        df["_date"] = df["_ngay"].dt.date
    return df


def get_gia_ban_map() -> dict:
    """Map ma_hang → gia_ban từ master hang_hoa."""
    hh = load_hang_hoa()
    if hh.empty or "ma_hang" not in hh.columns or "gia_ban" not in hh.columns:
        return {}
    return dict(zip(hh["ma_hang"].astype(str), hh["gia_ban"].fillna(0).astype(int)))


# ==========================================
# MODULE: TỔNG QUAN — FIX NameError (bỏ dashboard)
# ==========================================

# ==========================================
# MODULE: KIỂM KÊ — MVP v1
# Workflow: Nháp/Đang kiểm → Chờ duyệt admin → Đã duyệt
# ==========================================

@st.cache_data(ttl=120)
def load_phieu_kiem_ke(branches_key: tuple = None) -> pd.DataFrame:
    rows, batch, offset = [], 1000, 0
    while True:
        q = supabase.table("phieu_kiem_ke").select("*").order("created_at", desc=True)
        res = q.range(offset, offset + batch - 1).execute()
        if not res.data:
            break
        rows.extend(res.data)
        if len(res.data) < batch:
            break
        offset += batch

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if branches_key and "chi_nhanh" in df.columns:
        df = df[df["chi_nhanh"].isin(list(branches_key))].reset_index(drop=True)
    if "created_at" in df.columns:
        df["_created"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True) \
                          .dt.tz_convert("Asia/Ho_Chi_Minh")
    return df



def lookup_khach_hang(sdt: str) -> dict | None:
    """Tra cứu khách hàng theo SĐT. Trả None nếu không tìm thấy."""
    if not sdt or not sdt.strip(): return None
    try:
        sdt_clean = sdt.strip().replace(" ", "")
        res = supabase.table("khach_hang").select("*").eq("sdt", sdt_clean).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception: return None


def _gen_ma_akh() -> str:
    """Sinh mã AKH kế tiếp qua Postgres function."""
    try:
        res = supabase.rpc("get_next_akh_num", {}).execute()
        data = res.data
        num = int(data[0] if isinstance(data, list) else data) if data else 1
        return f"AKH{num:06d}"
    except Exception:
        return f"AKH{(now_vn()).strftime('%y%m%d%H%M')}"


def _upsert_khach_hang(ten: str, sdt: str, chi_nhanh: str = "") -> str:
    """Thêm mới hoặc bỏ qua nếu SĐT đã tồn tại. Trả về ma_kh."""
    sdt_clean = sdt.strip().replace(" ", "")
    existing = lookup_khach_hang(sdt_clean)
    if existing:
        return existing.get("ma_kh", "")
    try:
        ma = _gen_ma_akh()
        supabase.table("khach_hang").insert({
            "ma_kh": ma, "ten_kh": ten.strip(), "sdt": sdt_clean,
            "chi_nhanh_tao": chi_nhanh,
            "created_at": (now_vn()).isoformat(),
            "updated_at": (now_vn()).isoformat(),
        }).execute()
        return ma
    except Exception: return ""


def upsert_khach_hang_with_update(ten: str, sdt: str, chi_nhanh: str = "") -> str:
    """Admin variant: UPDATE ten_kh nếu SĐT đã tồn tại + tên khác; INSERT nếu mới.

    Khác `_upsert_khach_hang`: cho phép admin sửa tên khách → đẩy lên khach_hang
    master data (per yêu cầu B2a admin tab Sửa HĐ POS).
    Returns ma_kh ("" nếu lỗi/không có sdt).
    """
    if not sdt:
        return ""
    sdt_clean = "".join(c for c in str(sdt) if c.isdigit())[:15]
    ten_clean = " ".join((ten or "").split())[:100]
    if not sdt_clean:
        return ""
    existing = lookup_khach_hang(sdt_clean)
    try:
        if existing:
            old_ten = (existing.get("ten_kh") or "").strip()
            if ten_clean and old_ten != ten_clean:
                supabase.table("khach_hang").update({
                    "ten_kh": ten_clean,
                    "updated_at": now_vn().isoformat(),
                }).eq("ma_kh", existing["ma_kh"]).execute()
            return existing.get("ma_kh", "")
        if not ten_clean:
            return ""
        ma = _gen_ma_akh()
        supabase.table("khach_hang").insert({
            "ma_kh": ma, "ten_kh": ten_clean, "sdt": sdt_clean,
            "chi_nhanh_tao": chi_nhanh,
            "created_at": now_vn().isoformat(),
            "updated_at": now_vn().isoformat(),
        }).execute()
        return ma
    except Exception:
        return ""


@st.cache_data(ttl=120)
def load_khach_hang_list() -> pd.DataFrame:
    """
    Load danh sách khách hàng + tính tổng mua từ 3 nguồn:
      - tong_ban (cột sẵn có từ KiotViet upload)
      - SUM hoa_don_pos.khach_can_tra theo sdt_khach (HĐ Hoàn thành)
      - SUM phieu_doi_tra_pos.chenh_lech theo sdt_khach (phiếu Hoàn thành)
        chenh_lech > 0: khách bù thêm → cộng vào tong_ban
        chenh_lech < 0: shop hoàn → trừ tong_ban
    """
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("khach_hang").select("*") \
            .order("updated_at", desc=True).range(offset, offset+batch-1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["tong_ban", "diem_hien_tai"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # ── Cộng dồn doanh thu POS theo SĐT ──
    try:
        pos_rows, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("hoa_don_pos") \
                .select("sdt_khach,khach_can_tra,trang_thai") \
                .range(offset, offset + batch - 1).execute()
            if not res.data: break
            pos_rows.extend(res.data)
            if len(res.data) < batch: break
            offset += batch

        if pos_rows:
            pos_df = pd.DataFrame(pos_rows)
            # Chỉ tính HĐ Hoàn thành, có SĐT
            pos_df = pos_df[
                (pos_df["trang_thai"] == "Hoàn thành")
                & pos_df["sdt_khach"].notna()
                & (pos_df["sdt_khach"] != "")
            ]
            if not pos_df.empty:
                pos_df["khach_can_tra"] = pd.to_numeric(
                    pos_df["khach_can_tra"], errors="coerce"
                ).fillna(0).astype(int)
                pos_total = pos_df.groupby("sdt_khach")["khach_can_tra"].sum().to_dict()

                if "sdt" in df.columns and "tong_ban" in df.columns:
                    df["tong_ban"] = df.apply(
                        lambda r: int(r.get("tong_ban", 0) or 0)
                                  + int(pos_total.get(str(r.get("sdt", "")), 0)),
                        axis=1
                    )
    except Exception:
        # Không phá function nếu POS chưa có dữ liệu/lỗi
        pass

    # ── Cộng dồn chênh lệch từ phiếu đổi/trả POS theo SĐT ──
    try:
        pdt_rows, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("phieu_doi_tra_pos") \
                .select("sdt_khach,chenh_lech,trang_thai") \
                .range(offset, offset + batch - 1).execute()
            if not res.data: break
            pdt_rows.extend(res.data)
            if len(res.data) < batch: break
            offset += batch

        if pdt_rows:
            pdt_df = pd.DataFrame(pdt_rows)
            pdt_df = pdt_df[
                (pdt_df["trang_thai"] == "Hoàn thành")
                & pdt_df["sdt_khach"].notna()
                & (pdt_df["sdt_khach"] != "")
            ]
            if not pdt_df.empty:
                pdt_df["chenh_lech"] = pd.to_numeric(
                    pdt_df["chenh_lech"], errors="coerce"
                ).fillna(0).astype(int)
                pdt_total = pdt_df.groupby("sdt_khach")["chenh_lech"].sum().to_dict()

                if "sdt" in df.columns and "tong_ban" in df.columns:
                    df["tong_ban"] = df.apply(
                        lambda r: int(r.get("tong_ban", 0) or 0)
                                  + int(pdt_total.get(str(r.get("sdt", "")), 0)),
                        axis=1
                    )
    except Exception:
        pass

    return df

@st.cache_data(ttl=300, show_spinner=False)
def _load_hoa_don_pos_flat(branches_key: tuple) -> pd.DataFrame:
    """
    Load hoa_don_pos + hoa_don_pos_ct, flatten thành format giống bảng hoa_don
    (KiotViet) để dùng chung với load_hoa_don_unified.

    Mỗi item trong HĐ → 1 dòng. Header info lặp lại trên mỗi dòng.
    HĐ không có chi tiết (edge case): vẫn tạo 1 dòng với items rỗng.
    """
    try:
        # 1. Load headers
        rows_h, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("hoa_don_pos").select("*") \
                .in_("chi_nhanh", list(branches_key)) \
                .range(offset, offset + batch - 1).execute()
            if not res.data: break
            rows_h.extend(res.data)
            if len(res.data) < batch: break
            offset += batch

        if not rows_h:
            return pd.DataFrame()

        # 2. Load chi tiết theo các ma_hd
        ma_hd_list = [h["ma_hd"] for h in rows_h]
        rows_ct, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("hoa_don_pos_ct").select("*") \
                .in_("ma_hd", ma_hd_list) \
                .range(offset, offset + batch - 1).execute()
            if not res.data: break
            rows_ct.extend(res.data)
            if len(res.data) < batch: break
            offset += batch

        # Map: ma_hd → list items
        ct_map: dict[str, list] = {}
        for ct in rows_ct:
            ct_map.setdefault(ct["ma_hd"], []).append(ct)

        # 3. Load phieu_dat_hang để lấy cọc PTTT breakdown (chỉ khi có HĐ từ đặt hàng)
        pdat_map: dict[str, dict] = {}
        try:
            hd_co_coc = [h["ma_hd"] for h in rows_h
                         if int(h.get("tien_coc_da_thu", 0) or 0) > 0]
            if hd_co_coc:
                res_pdat = supabase.table("phieu_dat_hang") \
                    .select("ma_hd_pos,coc_tien_mat,coc_chuyen_khoan,coc_the") \
                    .in_("ma_hd_pos", hd_co_coc).execute()
                for _pdat_row in (res_pdat.data or []):
                    if _pdat_row.get("ma_hd_pos"):
                        pdat_map[_pdat_row["ma_hd_pos"]] = _pdat_row
        except Exception:
            pass  # Không có phieu_dat_hang hoặc lỗi → coc PTTT = 0

        # 4. Flatten: mỗi item của HĐ → 1 row có đầy đủ header info
        flat_rows = []
        for h in rows_h:
            ma_hd = h["ma_hd"]

            # Format Thời gian: ISO → "dd/MM/yyyy HH:mm:ss" giống KiotViet
            try:
                dt = pd.to_datetime(h.get("created_at"), errors="coerce", utc=True)
                if pd.notna(dt):
                    dt_vn = dt.tz_convert("Asia/Ho_Chi_Minh")
                    thoi_gian_str = dt_vn.strftime("%d/%m/%Y %H:%M:%S")
                else:
                    thoi_gian_str = ""
            except Exception:
                thoi_gian_str = ""

            # Trạng thái: HĐ POS dùng "Hoàn thành" hoặc "Đã hủy" (giống KiotViet)
            trang_thai = h.get("trang_thai", "Hoàn thành") or "Hoàn thành"

            nguoi_ban = h.get("nguoi_ban", "") or ""

            # Cọc PTTT từ phieu_dat_hang (nếu HĐ này từ phiếu đặt)
            coc_info = pdat_map.get(ma_hd, {})

            # Header chung lặp trên mỗi dòng
            base = {
                "Mã hóa đơn":        ma_hd,
                "Chi nhánh":         h.get("chi_nhanh", ""),
                "Mã khách hàng":     h.get("ma_kh") or "",
                "Tên khách hàng":    h.get("ten_khach", "") or "Khách lẻ",
                "Điện thoại":        h.get("sdt_khach", "") or "",
                "Thời gian":         thoi_gian_str,
                "Tổng tiền hàng":    int(h.get("tong_tien_hang", 0) or 0),
                "Giảm giá hóa đơn":  int(h.get("giam_gia_don", 0) or 0),
                "Khách cần trả":     int(h.get("khach_can_tra", 0) or 0),
                "Khách đã trả":      int(h.get("khach_can_tra", 0) or 0),
                "Tiền mặt":          int(h.get("tien_mat", 0) or 0),
                "Chuyển khoản":      int(h.get("chuyen_khoan", 0) or 0),
                "Thẻ":               int(h.get("the", 0) or 0),
                "Ví":                0,
                "Tiền cọc":          int(h.get("tien_coc_da_thu", 0) or 0),
                "Cọc tiền mặt":      int(coc_info.get("coc_tien_mat", 0) or 0),
                "Cọc chuyển khoản":  int(coc_info.get("coc_chuyen_khoan", 0) or 0),
                "Cọc thẻ":           int(coc_info.get("coc_the", 0) or 0),
                "Trạng thái":        trang_thai,
                "Người tạo":         nguoi_ban,
                "Người bán":         nguoi_ban,
                "Nhân viên":         nguoi_ban,
                "Ghi chú":           h.get("ghi_chu", "") or "",
                "Kênh bán":          "POS",
                "is_admin_created":  bool(h.get("is_admin_created", False)),
                "admin_note":        h.get("admin_note") or None,
            }

            items = ct_map.get(ma_hd, [])
            if not items:
                # HĐ rỗng (edge case) — vẫn tạo 1 dòng để giữ trong list
                flat_rows.append({**base,
                    "Mã hàng": "", "Tên hàng": "", "Số lượng": 0,
                    "Đơn giá": 0, "Thành tiền": 0,
                })
            else:
                for ct in items:
                    flat_rows.append({**base,
                        "Mã hàng":       ct.get("ma_hang", "") or "",
                        "Mã vạch":       ct.get("ma_hang", "") or "",
                        "Tên hàng":      ct.get("ten_hang", "") or "",
                        "Số lượng":      int(ct.get("so_luong", 0) or 0),
                        "Đơn giá":       int(ct.get("don_gia", 0) or 0),
                        "Thành tiền":    int(ct.get("thanh_tien", 0) or 0),
                        "Giảm giá":      int(ct.get("giam_gia_dong", 0) or 0),
                        "Giảm giá %":    0,
                        "Giá bán":       int(ct.get("don_gia", 0) or 0),
                    })

        if not flat_rows:
            return pd.DataFrame()

        df = pd.DataFrame(flat_rows)

        # Add các cột derived giống load_hoa_don
        df["_ngay"] = pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")
        df["_date"] = df["_ngay"].dt.date

        # Chuẩn hoá SĐT giống load_hoa_don
        def _fix_sdt(v):
            s = str(v).strip() if v is not None else ""
            if s in ("", "nan", "None"): return ""
            if s.endswith(".0"): s = s[:-2]
            digits = s.replace(" ", "")
            if digits.isdigit() and len(digits) == 9:
                digits = "0" + digits
            return digits
        df["Điện thoại"] = df["Điện thoại"].apply(_fix_sdt)

        return df
    except Exception as e:
        st.warning(f"Không tải được hoá đơn POS: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def _load_doi_tra_pos_flat(branches_key: tuple) -> pd.DataFrame:
    """
    Load phieu_doi_tra_pos + ct, flatten thành format giống hoa_don
    để dùng chung với load_hoa_don_unified.

    Quy ước denormalize:
      - Mỗi item trong phiếu → 1 dòng (giống hoa_don KiotViet)
      - "Mã hóa đơn" = ma_pdt (AHDD000xxx)
      - Header "Khách đã trả" = chenh_lech (CHỈ ghi ở dòng đầu, các dòng sau = 0)
        → khi drop_duplicates(subset=["Mã hóa đơn"]).sum() → đúng chenh_lech 1 lần
      - Items "tra": Thành tiền ÂM (khách trả lại → trừ doanh thu hàng)
      - Items "moi": Thành tiền DƯƠNG
      - Số lượng giữ DƯƠNG (để tính SL hàng), nhưng có thêm cột _kieu để biết tra/moi
      - "Trạng thái": "Hoàn thành" / "Đã hủy" (giống chuẩn HĐ)
      - "Kênh bán" = "POS-DT" để phân biệt với HĐ POS thường
      - "_pdt": True → flag để các module phân loại
    """
    try:
        rows_h, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("phieu_doi_tra_pos").select("*") \
                .in_("chi_nhanh", list(branches_key)) \
                .range(offset, offset + batch - 1).execute()
            if not res.data: break
            rows_h.extend(res.data)
            if len(res.data) < batch: break
            offset += batch

        if not rows_h:
            return pd.DataFrame()

        ma_pdt_list = [h["ma_pdt"] for h in rows_h]
        rows_ct, batch, offset = [], 1000, 0
        while True:
            res = supabase.table("phieu_doi_tra_pos_ct").select("*") \
                .in_("ma_pdt", ma_pdt_list) \
                .range(offset, offset + batch - 1).execute()
            if not res.data: break
            rows_ct.extend(res.data)
            if len(res.data) < batch: break
            offset += batch

        ct_map: dict[str, list] = {}
        for ct in rows_ct:
            ct_map.setdefault(ct["ma_pdt"], []).append(ct)

        flat_rows = []
        for h in rows_h:
            ma_pdt = h["ma_pdt"]

            # Format thời gian giống KiotViet
            try:
                dt = pd.to_datetime(h.get("created_at"), errors="coerce", utc=True)
                if pd.notna(dt):
                    dt_vn = dt.tz_convert("Asia/Ho_Chi_Minh")
                    thoi_gian_str = dt_vn.strftime("%d/%m/%Y %H:%M:%S")
                else:
                    thoi_gian_str = ""
            except Exception:
                thoi_gian_str = ""

            trang_thai = h.get("trang_thai", "Hoàn thành") or "Hoàn thành"
            nguoi      = h.get("nguoi_tao", "") or ""
            chenh_lech = int(h.get("chenh_lech", 0) or 0)
            tong_moi   = int(h.get("tien_hang_moi", 0) or 0)
            giam_gia   = 0  # AHDD không có giảm giá đơn

            # Header chung
            base = {
                "Mã hóa đơn":        ma_pdt,
                "Chi nhánh":         h.get("chi_nhanh", ""),
                "Mã khách hàng":     h.get("ma_kh") or "",
                "Tên khách hàng":    h.get("ten_khach", "") or "Khách lẻ",
                "Điện thoại":        h.get("sdt_khach", "") or "",
                "Thời gian":         thoi_gian_str,
                "Tổng tiền hàng":    tong_moi,
                "Giảm giá hóa đơn":  giam_gia,
                "Khách cần trả":     chenh_lech,
                # "Khách đã trả": gán ở loop dưới — chỉ dòng đầu = chenh_lech
                "Tiền mặt":          int(h.get("tien_mat", 0) or 0),
                "Chuyển khoản":      int(h.get("chuyen_khoan", 0) or 0),
                "Thẻ":               int(h.get("the", 0) or 0),
                "Ví":                0,
                "Trạng thái":        trang_thai,
                "Người tạo":         nguoi,
                "Người bán":         nguoi,
                "Nhân viên":         nguoi,
                "Ghi chú":           h.get("ghi_chu", "") or h.get("loai_phieu", "") or "",
                "Kênh bán":          "POS-DT",
                "_pdt":              True,
                "_pdt_ma_hd_goc":    h.get("ma_hd_goc", ""),
                "_pdt_loai":         h.get("loai_phieu", ""),
                "_pdt_chenh_lech":   chenh_lech,
                "is_admin_created":  bool(h.get("is_admin_created", False)),
                "admin_note":        h.get("admin_note") or None,
            }

            items = ct_map.get(ma_pdt, [])
            if not items:
                flat_rows.append({**base,
                    "Khách đã trả": chenh_lech,
                    "Mã hàng": "", "Tên hàng": "", "Số lượng": 0,
                    "Đơn giá": 0, "Thành tiền": 0,
                    "_pdt_kieu": "",
                })
            else:
                for idx, ct in enumerate(items):
                    kieu = ct.get("kieu", "")
                    sl   = int(ct.get("so_luong", 0) or 0)
                    dg   = int(ct.get("don_gia", 0) or 0)
                    tt_raw = int(ct.get("thanh_tien", 0) or 0)
                    # Đảo dấu Thành tiền cho items "tra"
                    tt_signed = -tt_raw if kieu == "tra" else tt_raw

                    flat_rows.append({**base,
                        # Header "Khách đã trả": chỉ dòng đầu = chenh_lech, sau = 0
                        # → drop_duplicates lấy dòng đầu → sum đúng 1 lần
                        "Khách đã trả": chenh_lech if idx == 0 else 0,
                        "Mã hàng":       ct.get("ma_hang", "") or "",
                        "Mã vạch":       ct.get("ma_hang", "") or "",
                        "Tên hàng":      ct.get("ten_hang", "") or "",
                        "Số lượng":      sl,
                        "Đơn giá":       dg,
                        "Thành tiền":    tt_signed,
                        "Giảm giá":      0,
                        "Giảm giá %":    0,
                        "Giá bán":       dg,
                        "_pdt_kieu":     kieu,
                    })

        if not flat_rows:
            return pd.DataFrame()

        df = pd.DataFrame(flat_rows)
        df["_ngay"] = pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")
        df["_date"] = df["_ngay"].dt.date

        def _fix_sdt(v):
            s = str(v).strip() if v is not None else ""
            if s in ("", "nan", "None"): return ""
            if s.endswith(".0"): s = s[:-2]
            digits = s.replace(" ", "")
            if digits.isdigit() and len(digits) == 9:
                digits = "0" + digits
            return digits
        df["Điện thoại"] = df["Điện thoại"].apply(_fix_sdt)

        return df
    except Exception as e:
        st.warning(f"Không tải được phiếu đổi/trả POS: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def load_hoa_don_unified(branches_key: tuple) -> pd.DataFrame:
    """
    Adapter: gộp hoa_don (KiotViet) + hoa_don_pos (POS) + phieu_doi_tra_pos (AHDD)
    thành 1 DataFrame có format giống load_hoa_don.

    Cột _pdt = True đánh dấu các dòng từ AHDD để các module phân biệt nếu cần.
    """
    df_old = load_hoa_don(branches_key)
    df_pos = _load_hoa_don_pos_flat(branches_key)
    df_pdt = _load_doi_tra_pos_flat(branches_key)

    parts = [d for d in (df_old, df_pos, df_pdt) if not d.empty]
    if not parts:
        return pd.DataFrame()
    if len(parts) == 1:
        return parts[0].reset_index(drop=True)

    return pd.concat(parts, ignore_index=True, sort=False)

def invalidate_hoa_don_cache():
    """
    Xóa cache của các function liên quan HĐ.
    Gọi sau khi tạo/hủy HĐ POS, phiếu đổi/trả, hoặc upload KiotViet.
    """
    try:
        load_hoa_don.clear()
        _load_hoa_don_pos_flat.clear()
        _load_doi_tra_pos_flat.clear()
        load_hoa_don_unified.clear()
        load_khach_hang_list.clear()
    except Exception:
        pass


# ============================================================
# Module Chấm công — helpers (Phase 2)
# Refs: PLAN_CHAM_CONG.md section 7.5
# ============================================================

@st.cache_data(ttl=300)
def load_shift_templates(include_inactive: bool = False) -> list[dict]:
    """Load shift templates. Default chỉ active=True (cho UI xếp lịch).

    include_inactive=True dùng cho UI Cấu hình > Ca làm việc (admin xem cả ca đã ẩn).
    """
    q = supabase.table("shift_templates").select("*")
    if not include_inactive:
        q = q.eq("active", True)
    res = q.order("branch_name").order("start_time").execute()
    return res.data or []


@st.cache_data(ttl=300)
def load_branch_networks() -> dict:
    """Map branch_name → ip_prefixes (TEXT[])."""
    res = supabase.table("attendance_branch_networks").select("*").execute()
    return {r["branch_name"]: (r.get("ip_prefixes") or []) for r in (res.data or [])}


@st.cache_data(ttl=300)
def load_employee_rates() -> dict:
    """Map nhan_vien_id → rate dict {salary_type, hourly_rate, monthly_fixed}."""
    res = supabase.table("attendance_employee_rates").select("*").execute()
    return {r["nhan_vien_id"]: r for r in (res.data or [])}


def count_schedules_using_template(template_id: int) -> int:
    """Count schedules ref tới template (dùng để lock fields edit shift_templates)."""
    res = (
        supabase.table("attendance_work_schedules")
        .select("id", count="exact")
        .eq("shift_template_id", template_id)
        .execute()
    )
    return res.count or 0


def load_schedules_for_week(start_monday, branch: str = None) -> list[dict]:
    """Load schedules + JOIN shift_templates + nhan_vien cho 1 tuần.

    start_monday: date object (Monday của tuần cần load).
    branch: optional filter theo shift_templates.branch_name (client-side).
    Skip status='cancelled' để khỏi render chip cancelled.
    """
    from datetime import timedelta as _td
    end_sunday = start_monday + _td(days=6)
    q = (
        supabase.table("attendance_work_schedules")
        .select("*, shift_templates(*), nhan_vien(ho_ten, role)")
        .gte("work_date", start_monday.isoformat())
        .lte("work_date", end_sunday.isoformat())
        .neq("status", "cancelled")
    )
    res = q.execute()
    rows = res.data or []
    if branch:
        rows = [r for r in rows
                if (r.get("shift_templates") or {}).get("branch_name") == branch]
    return rows

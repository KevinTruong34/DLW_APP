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
    Tính delta tồn kho từ các phiếu tạo trong app (loai_phieu = IN_APP_MARKER).
    Trả về dict {(ma_hang, chi_nhanh): delta_int}.

    Quy tắc:
      - Phiếu tạm, Đã hủy: không ảnh hưởng (delta = 0)
      - Đang chuyển: -SL tại CN nguồn (đã rời kho, chưa tới đích)
      - Đã nhận:    -SL tại CN nguồn, +SL tại CN đích

    Phiếu upload từ KiotViet (loai_phieu khác IN_APP_MARKER) được bỏ qua
    vì đã được phản ánh trong the_kho snapshot.
    """
    rows = []
    try:
        batch, offset = 1000, 0
        while True:
            res = supabase.table("phieu_chuyen_kho").select(
                "ma_hang,tu_chi_nhanh,toi_chi_nhanh,so_luong_chuyen,trang_thai"
            ).eq("loai_phieu", IN_APP_MARKER) \
             .range(offset, offset + batch - 1).execute()
            if not res.data: break
            rows.extend(res.data)
            if len(res.data) < batch: break
            offset += batch
    except Exception:
        return {}

    deltas = {}
    for r in rows:
        tt  = str(r.get("trang_thai", "") or "").strip()
        mh  = str(r.get("ma_hang", "") or "").strip()
        sl  = int(r.get("so_luong_chuyen", 0) or 0)
        tu  = str(r.get("tu_chi_nhanh", "") or "").strip()
        toi = str(r.get("toi_chi_nhanh", "") or "").strip()

        if not mh or sl <= 0:
            continue

        # Rời kho nguồn khi phiếu đã được xác nhận chuyển
        if tt in ("Đang chuyển", "Đã nhận") and tu:
            deltas[(mh, tu)] = deltas.get((mh, tu), 0) - sl

        # Vào kho đích chỉ khi đã nhận
        if tt == "Đã nhận" and toi:
            deltas[(mh, toi)] = deltas.get((mh, toi), 0) + sl

    return deltas


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

    # ── Áp delta tồn kho từ phiếu App ──
    try:
        deltas = load_stock_deltas()
        if deltas and "Mã hàng" in df.columns and "Chi nhánh" in df.columns:
            # Strip whitespace trên keys để match chính xác
            df["_ma_key"] = df["Mã hàng"].astype(str).str.strip()
            df["_cn_key"] = df["Chi nhánh"].astype(str).str.strip()

            def _apply_delta(row):
                return deltas.get((row["_ma_key"], row["_cn_key"]), 0)
            df["_delta"] = df.apply(_apply_delta, axis=1)
            df["Tồn cuối kì"] = (df["Tồn cuối kì"] + df["_delta"]).astype(int)

            # Tìm các (mã, CN) có delta nhưng KHÔNG có dòng trong the_kho
            # → phải thêm dòng mới để tồn kho tăng lên
            existing_keys = set(zip(df["_ma_key"], df["_cn_key"]))
            # Chỉ xét các CN đang load (branches_key)
            load_cns_set = set(branches_key)

            # Lookup tên hàng từ master để fill khi tạo row mới
            try:
                master = load_hang_hoa()
                name_map = (dict(zip(master["Mã hàng"].astype(str),
                                     master["Tên hàng"].astype(str)))
                           if not master.empty else {})
            except Exception:
                name_map = {}

            new_rows = []
            for (mh, cn), dlt in deltas.items():
                if cn not in load_cns_set:
                    continue  # CN không load → bỏ qua
                if (mh, cn) in existing_keys:
                    continue  # đã có, đã áp delta ở trên
                if dlt == 0:
                    continue
                # Tạo dòng mới cho (mã, CN) chưa tồn tại
                new_rows.append({
                    "Mã hàng":       mh,
                    "Chi nhánh":     cn,
                    "Tên hàng":      name_map.get(mh, ""),
                    "Tồn đầu kì":    0,
                    "Tồn cuối kì":   int(dlt),   # delta thành tồn luôn
                    "Nhập NCC":      0,
                    "Xuất bán":      0,
                    "Giá trị đầu kì":  0,
                    "Giá trị nhập NCC": 0,
                    "Giá trị xuất bán": 0,
                    "Giá trị cuối kì": 0,
                    "_ma_key":       mh,
                    "_cn_key":       cn,
                    "_delta":        int(dlt),
                })
            if new_rows:
                df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

            df = df.drop(columns=["_delta", "_ma_key", "_cn_key"])
    except Exception:
        pass

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
        df["_ngay"] = pd.to_datetime(df["ngay_chuyen"], errors="coerce")
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
        df["_created"] = pd.to_datetime(df["created_at"], errors="coerce")
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


@st.cache_data(ttl=120)
def load_khach_hang_list() -> pd.DataFrame:
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
 
        # 3. Flatten: mỗi item của HĐ → 1 row có đầy đủ header info
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
                "Trạng thái":        trang_thai,
                "Người tạo":         nguoi_ban,
                "Người bán":         nguoi_ban,
                "Nhân viên":         nguoi_ban,
                "Ghi chú":           h.get("ghi_chu", "") or "",
                "Kênh bán":          "POS",
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
def load_hoa_don_unified(branches_key: tuple) -> pd.DataFrame:
    """
    Adapter: gộp hoa_don (KiotViet) + hoa_don_pos (POS) thành 1 DataFrame
    có format giống load_hoa_don (denormalized, mỗi item = 1 dòng).
 
    Module app cũ chỉ cần đổi load_hoa_don(...) → load_hoa_don_unified(...)
    là tự động thấy thêm HĐ POS.
    """
    df_old = load_hoa_don(branches_key)
    df_pos = _load_hoa_don_pos_flat(branches_key)
 
    if df_old.empty and df_pos.empty:
        return pd.DataFrame()
    if df_old.empty:
        return df_pos.reset_index(drop=True)
    if df_pos.empty:
        return df_old.reset_index(drop=True)
 
    # Concat — pandas tự align column theo tên, NaN cho cột thiếu
    return pd.concat([df_old, df_pos], ignore_index=True, sort=False)

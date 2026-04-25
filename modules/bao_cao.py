import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date

from utils.db import supabase, load_hoa_don, load_hang_hoa, load_the_kho
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER

# Prefix HĐ do App tạo — thêm vào đây khi có module POS
APP_INVOICE_PREFIXES = ["APSC"]

def _is_app_hd(ma: str) -> bool:
    return any(str(ma).startswith(p) for p in APP_INVOICE_PREFIXES)

def _fmt(v) -> str:
    return f"{int(v):,}".replace(",", ".")


# ══════════════════════════════════════════════════════════
# WIDGET — Date filter
# ══════════════════════════════════════════════════════════

def _date_filter(key: str, default_days: int = 30) -> tuple[date, date]:
    today = datetime.now().date()
    presets = {
        "Hôm nay":     (today, today),
        "Hôm qua":     (today - timedelta(1), today - timedelta(1)),
        "7 ngày qua":  (today - timedelta(6), today),
        "30 ngày qua": (today - timedelta(29), today),
        "Tháng này":   (today.replace(day=1), today),
        "Tháng trước": (
            (today.replace(day=1) - timedelta(1)).replace(day=1),
            today.replace(day=1) - timedelta(1),
        ),
        "Tùy chọn": None,
    }
    default_idx = 3  # 30 ngày qua
    col_p, col_f, col_t = st.columns([2, 1, 1])
    with col_p:
        preset = st.selectbox("Kỳ:", list(presets.keys()),
                              index=default_idx, key=f"{key}_preset",
                              label_visibility="collapsed")
    if presets[preset] is not None:
        d_from, d_to = presets[preset]
        with col_f:
            st.date_input("Từ:", value=d_from, disabled=True,
                          key=f"{key}_f1", label_visibility="collapsed",
                          format="DD/MM/YYYY")
        with col_t:
            st.date_input("Đến:", value=d_to, disabled=True,
                          key=f"{key}_t1", label_visibility="collapsed",
                          format="DD/MM/YYYY")
    else:
        with col_f:
            d_from = st.date_input("Từ:", value=today - timedelta(29),
                                   key=f"{key}_f2", label_visibility="collapsed",
                                   format="DD/MM/YYYY")
        with col_t:
            d_to = st.date_input("Đến:", value=today,
                                 key=f"{key}_t2", label_visibility="collapsed",
                                 format="DD/MM/YYYY")
    return d_from, d_to


# ══════════════════════════════════════════════════════════
# LOAD FUNCTIONS — cache + pagination + order
# ══════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def _load_hd(branches_key: tuple, d_from: date, d_to: date) -> pd.DataFrame:
    """Load hoa_don Hoàn thành trong khoảng ngày."""
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("hoa_don").select("*") \
            .in_("Chi nhánh", list(branches_key)) \
            .eq("Trạng thái", "Hoàn thành") \
            .order("Thời gian", desc=True) \
            .range(offset, offset + batch - 1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["Tổng tiền hàng", "Khách đã trả", "Đơn giá",
                "Thành tiền", "Số lượng"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "Thời gian" in df.columns:
        df["_ngay"] = pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")
        df["_date"] = df["_ngay"].dt.date
        df = df[df["_date"].between(d_from, d_to)]
    return df.reset_index(drop=True)


@st.cache_data(ttl=300)
def _load_sc_phieu(branches_key: tuple, d_from: date, d_to: date) -> pd.DataFrame:
    """Load phieu_sua_chua trong khoảng ngày — dùng cho tab Cuối ngày."""
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("phieu_sua_chua").select(
            "ma_phieu,chi_nhanh,trang_thai,created_by,nguoi_tiep_nhan,created_at,ten_khach,sdt_khach"
        ).in_("chi_nhanh", list(branches_key)) \
         .order("created_at", desc=True) \
         .range(offset, offset + batch - 1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["_date"] = pd.to_datetime(
        df["created_at"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Ho_Chi_Minh").dt.date
    df = df[df["_date"].between(d_from, d_to)]
    return df.reset_index(drop=True)


@st.cache_data(ttl=300)
def _load_sc_can_luu_y(branches_key: tuple) -> pd.DataFrame:
    """
    Load TẤT CẢ phiếu sửa chữa chưa Hoàn thành (cho section Phiếu cần lưu ý).
    Không filter theo ngày — vì cần kiểm tra phiếu cũ vẫn còn dở dang.
    """
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("phieu_sua_chua").select(
            "ma_phieu,chi_nhanh,trang_thai,ten_khach,sdt_khach,created_at,ngay_hen_tra"
        ).in_("chi_nhanh", list(branches_key)) \
         .neq("trang_thai", "Hoàn thành") \
         .order("created_at") \
         .range(offset, offset + batch - 1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["_created"] = pd.to_datetime(
        df["created_at"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Ho_Chi_Minh")
    today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").normalize()
    df["_so_ngay"] = (today - df["_created"].dt.normalize()).dt.days
    return df.reset_index(drop=True)


@st.cache_data(ttl=300)
def _load_nhap_hang(branches_key: tuple, d_from: date, d_to: date) -> pd.DataFrame:
    """Load phieu_nhap_hang + ct đã nhập kho."""
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("phieu_nhap_hang").select(
            "ma_phieu,chi_nhanh,confirmed_at,created_by"
        ).in_("chi_nhanh", list(branches_key)) \
         .eq("trang_thai", "Đã nhập kho") \
         .order("confirmed_at", desc=True) \
         .range(offset, offset + batch - 1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows:
        return pd.DataFrame()
    df_h = pd.DataFrame(rows)
    df_h["_date"] = pd.to_datetime(
        df_h["confirmed_at"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Ho_Chi_Minh").dt.date
    df_h = df_h[df_h["_date"].between(d_from, d_to)]
    if df_h.empty:
        return pd.DataFrame()

    ma_list = df_h["ma_phieu"].tolist()
    ct, batch2, offset2 = [], 1000, 0
    while True:
        res2 = supabase.table("phieu_nhap_hang_ct").select(
            "ma_phieu,ma_hang,ten_hang,so_luong,gia_von,loai_hang,thuong_hieu"
        ).in_("ma_phieu", ma_list) \
         .order("ma_phieu") \
         .range(offset2, offset2 + batch2 - 1).execute()
        if not res2.data: break
        ct.extend(res2.data)
        if len(res2.data) < batch2: break
        offset2 += batch2
    if not ct:
        return pd.DataFrame()
    df_ct = pd.DataFrame(ct)
    for c in ["so_luong", "gia_von"]:
        df_ct[c] = pd.to_numeric(df_ct[c], errors="coerce").fillna(0).astype(int)
    return df_ct.merge(df_h[["ma_phieu", "chi_nhanh", "_date", "created_by"]],
                       on="ma_phieu", how="left")


# TODO: enable when POS module adds bảng phieu_tra_hang
# @st.cache_data(ttl=300)
# def _load_tra_hang(branches_key: tuple, d_from: date, d_to: date) -> pd.DataFrame:
#     """Load phieu_tra_hang + ct đã trả."""
#     rows, batch, offset = [], 1000, 0
#     while True:
#         res = supabase.table("phieu_tra_hang").select(
#             "ma_phieu,chi_nhanh,confirmed_at,created_by"
#         ).in_("chi_nhanh", list(branches_key)) \
#          .eq("trang_thai", "Đã trả hàng") \
#          .order("confirmed_at", desc=True) \
#          .range(offset, offset + batch - 1).execute()
#         if not res.data: break
#         rows.extend(res.data)
#         if len(res.data) < batch: break
#         offset += batch
#     if not rows:
#         return pd.DataFrame()
#     df_h = pd.DataFrame(rows)
#     df_h["_date"] = pd.to_datetime(
#         df_h["confirmed_at"], errors="coerce", utc=True
#     ).dt.tz_convert("Asia/Ho_Chi_Minh").dt.date
#     df_h = df_h[df_h["_date"].between(d_from, d_to)]
#     if df_h.empty:
#         return pd.DataFrame()
#
#     ma_list = df_h["ma_phieu"].tolist()
#     ct, batch2, offset2 = [], 1000, 0
#     while True:
#         res2 = supabase.table("phieu_tra_hang_ct").select(
#             "ma_phieu,ma_hang,ten_hang,so_luong,gia_tra"
#         ).in_("ma_phieu", ma_list) \
#          .order("ma_phieu") \
#          .range(offset2, offset2 + batch2 - 1).execute()
#         if not res2.data: break
#         ct.extend(res2.data)
#         if len(res2.data) < batch2: break
#         offset2 += batch2
#     if not ct:
#         return pd.DataFrame()
#     df_ct = pd.DataFrame(ct)
#     for c in ["so_luong", "gia_tra"]:
#         df_ct[c] = pd.to_numeric(df_ct[c], errors="coerce").fillna(0).astype(int)
#     return df_ct.merge(df_h[["ma_phieu", "chi_nhanh", "_date", "created_by"]],
#                        on="ma_phieu", how="left")


@st.cache_data(ttl=300)
def _load_chuyen_hang(branches_key: tuple, d_from: date, d_to: date) -> pd.DataFrame:
    """Load phieu_chuyen_kho App đã nhận trong khoảng ngày."""
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("phieu_chuyen_kho").select(
            "ma_phieu,tu_chi_nhanh,toi_chi_nhanh,ngay_nhan,"
            "ma_hang,ten_hang,so_luong_nhan,gia_chuyen"
        ).eq("loai_phieu", IN_APP_MARKER) \
         .eq("trang_thai", "Đã nhận") \
         .order("ngay_nhan", desc=True) \
         .range(offset, offset + batch - 1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for c in ["so_luong_nhan", "gia_chuyen"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["_date"] = pd.to_datetime(df["ngay_nhan"], errors="coerce", utc=True) \
        .dt.tz_convert("Asia/Ho_Chi_Minh").dt.date
    df = df[df["_date"].between(d_from, d_to)]
    bk = set(branches_key)
    df = df[df["tu_chi_nhanh"].isin(bk) | df["toi_chi_nhanh"].isin(bk)]
    return df.reset_index(drop=True)


@st.cache_data(ttl=300)
def _load_kiem_ke(branches_key: tuple, d_from: date, d_to: date) -> pd.DataFrame:
    """Load phieu_kiem_ke đã duyệt + chi tiết trong khoảng ngày."""
    rows, batch, offset = [], 1000, 0
    while True:
        res = supabase.table("phieu_kiem_ke").select(
            "ma_phieu_kk,chi_nhanh,approved_at,approved_by"
        ).in_("chi_nhanh", list(branches_key)) \
         .eq("trang_thai", "Đã duyệt") \
         .order("approved_at", desc=True) \
         .range(offset, offset + batch - 1).execute()
        if not res.data: break
        rows.extend(res.data)
        if len(res.data) < batch: break
        offset += batch
    if not rows:
        return pd.DataFrame()
    df_h = pd.DataFrame(rows)
    df_h["_date"] = pd.to_datetime(
        df_h["approved_at"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Ho_Chi_Minh").dt.date
    df_h = df_h[df_h["_date"].between(d_from, d_to)]
    if df_h.empty:
        return pd.DataFrame()

    ma_list = df_h["ma_phieu_kk"].tolist()
    ct, batch2, offset2 = [], 1000, 0
    while True:
        res2 = supabase.table("phieu_kiem_ke_chi_tiet").select(
            "ma_phieu_kk,ma_hang,ten_hang,chenh_lech"
        ).in_("ma_phieu_kk", ma_list) \
         .order("ma_phieu_kk") \
         .range(offset2, offset2 + batch2 - 1).execute()
        if not res2.data: break
        ct.extend(res2.data)
        if len(res2.data) < batch2: break
        offset2 += batch2
    if not ct:
        return pd.DataFrame()
    df_ct = pd.DataFrame(ct)
    df_ct["chenh_lech"] = pd.to_numeric(df_ct["chenh_lech"], errors="coerce").fillna(0).astype(int)
    return df_ct.merge(df_h[["ma_phieu_kk", "chi_nhanh", "_date", "approved_by"]],
                       on="ma_phieu_kk", how="left")


# ══════════════════════════════════════════════════════════
# HELPER — Lookup loai_sp để phân biệt Hàng hóa vs Dịch vụ
# ══════════════════════════════════════════════════════════

def _get_loai_sp_map() -> dict:
    """Map ma_hang -> loai_sp ("Hàng hóa" / "Dịch vụ") từ master."""
    hh = load_hang_hoa()
    if hh.empty or "ma_hang" not in hh.columns or "loai_sp" not in hh.columns:
        return {}
    return dict(zip(hh["ma_hang"].astype(str), hh["loai_sp"].fillna("")))


def _filter_chi_hang_hoa(df: pd.DataFrame, ma_col: str = "Mã hàng") -> pd.DataFrame:
    """Lọc DataFrame chỉ giữ các dòng là Hàng hóa (loại bỏ Dịch vụ)."""
    if df.empty or ma_col not in df.columns:
        return df
    loai_map = _get_loai_sp_map()
    if not loai_map:
        return df  # Không có master → giữ nguyên (an toàn)
    return df[df[ma_col].astype(str).map(loai_map) == "Hàng hóa"].copy()


# ══════════════════════════════════════════════════════════
# TAB 1A — CUỐI NGÀY
# ══════════════════════════════════════════════════════════

def _tab_cuoi_ngay():
    user      = get_user() or {}
    ho_ten    = user.get("ho_ten", "")
    active    = get_active_branch()
    is_kt_adm = is_ke_toan_or_admin()
    accessible = get_accessible_branches()

    if is_kt_adm and len(accessible) > 1:
        cn_sel = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible,
                              key="bc_cd_cn", label_visibility="collapsed")
        load_cns = tuple(accessible) if cn_sel == "Tất cả" else (cn_sel,)
    else:
        load_cns = (active,)
        st.caption(f"📍 {active}")

    today     = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # Load 2 ngày: hôm nay + hôm qua (để so sánh delta)
    raw_today  = _load_hd(load_cns, today, today)
    raw_yest   = _load_hd(load_cns, yesterday, yesterday)

    def _summarize(raw: pd.DataFrame) -> dict:
        if raw.empty:
            return {"tong": 0, "so_hd": 0, "dt_ban": 0, "dt_apsc": 0}
        hd_u = raw.drop_duplicates(subset=["Mã hóa đơn"], keep="first")
        hd_ban  = hd_u[~hd_u["Mã hóa đơn"].apply(_is_app_hd)]
        hd_apsc = hd_u[hd_u["Mã hóa đơn"].apply(_is_app_hd)]
        return {
            "tong":    int(hd_u["Khách đã trả"].sum()),
            "so_hd":   len(hd_u),
            "dt_ban":  int(hd_ban["Khách đã trả"].sum()),
            "dt_apsc": int(hd_apsc["Khách đã trả"].sum()),
        }

    s_today = _summarize(raw_today)
    s_yest  = _summarize(raw_yest)

    def _delta_str(cur: int, prev: int) -> str | None:
        """Trả về delta string '+18% so hôm qua' hoặc None nếu không tính được."""
        if prev == 0:
            return None if cur == 0 else "Mới phát sinh"
        pct = (cur - prev) / prev * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.0f}% so hôm qua"

    st.markdown(
        "<div style='font-size:0.82rem;font-weight:600;color:#555;margin-bottom:6px;'>"
        "💰 Doanh thu hôm nay</div>",
        unsafe_allow_html=True
    )
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Tổng doanh thu", f"{_fmt(s_today['tong'])}đ",
                  delta=_delta_str(s_today["tong"], s_yest["tong"]))
    with m2:
        st.metric("Số hóa đơn", str(s_today["so_hd"]),
                  delta=_delta_str(s_today["so_hd"], s_yest["so_hd"]))
    with m3:
        st.metric("Bán hàng", f"{_fmt(s_today['dt_ban'])}đ",
                  delta=_delta_str(s_today["dt_ban"], s_yest["dt_ban"]))
    with m4:
        st.metric("Sửa chữa (APSC)", f"{_fmt(s_today['dt_apsc'])}đ",
                  delta=_delta_str(s_today["dt_apsc"], s_yest["dt_apsc"]))

    # ── Phiếu sửa chữa hôm nay — data chung CN ──
    df_sc = _load_sc_phieu(load_cns, today, today)

    so_sc_tao    = len(df_sc)
    so_sc_xong   = len(df_sc[df_sc["trang_thai"] == "Hoàn thành"]) if not df_sc.empty else 0

    st.markdown(
        "<div style='font-size:0.82rem;font-weight:600;color:#555;"
        "margin:14px 0 6px;'>🔧 Phiếu sửa chữa hôm nay</div>",
        unsafe_allow_html=True
    )
    s1, s2 = st.columns(2)
    with s1: st.metric("Phiếu tạo trong ngày", str(so_sc_tao))
    with s2: st.metric("Phiếu hoàn thành (giao)", str(so_sc_xong))

    # ══════ PHIẾU SỬA CẦN LƯU Ý ══════
    df_check = _load_sc_can_luu_y(load_cns)

    if not df_check.empty:
        # Điều kiện 1: phiếu nhận > 5 ngày, vẫn còn ở giai đoạn sửa
        cond_1 = df_check[
            (df_check["trang_thai"].isin(["Đang sửa", "Chờ linh kiện"]))
            & (df_check["_so_ngay"] > 5)
        ].copy()

        # Điều kiện 2: phiếu Chờ giao khách > 14 ngày
        cond_2 = df_check[
            (df_check["trang_thai"] == "Chờ giao khách")
            & (df_check["_so_ngay"] > 14)
        ].copy()

        if not cond_1.empty or not cond_2.empty:
            st.markdown(
                "<div style='font-size:0.82rem;font-weight:600;color:#cf4c2c;"
                "margin:14px 0 6px;'>⚠️ Phiếu sửa cần lưu ý</div>",
                unsafe_allow_html=True
            )

            cols_show = ["ma_phieu", "ten_khach", "sdt_khach", "trang_thai",
                         "chi_nhanh", "_so_ngay"]
            rename_map = {
                "ma_phieu": "Mã phiếu", "ten_khach": "Khách",
                "sdt_khach": "SĐT", "trang_thai": "Trạng thái",
                "chi_nhanh": "Chi nhánh", "_so_ngay": "Số ngày",
            }

            if not cond_1.empty:
                st.caption(
                    f"🔧 **{len(cond_1)} phiếu** đang sửa > 5 ngày — cần follow up thợ"
                )
                view1 = cond_1[cols_show].rename(columns=rename_map) \
                    .sort_values("Số ngày", ascending=False)
                st.dataframe(view1, use_container_width=True, hide_index=True,
                             height=min(300, 42 + len(view1) * 35))

            if not cond_2.empty:
                st.caption(
                    f"📞 **{len(cond_2)} phiếu** chờ giao > 2 tuần — cần gọi nhắc khách"
                )
                view2 = cond_2[cols_show].rename(columns=rename_map) \
                    .sort_values("Số ngày", ascending=False)
                st.dataframe(view2, use_container_width=True, hide_index=True,
                             height=min(300, 42 + len(view2) * 35))

    # ── Bảng HĐ chi tiết hôm nay ──
    if not raw_today.empty:
        hd_unique = raw_today.drop_duplicates(subset=["Mã hóa đơn"], keep="first")
        st.markdown(
            "<div style='font-size:0.82rem;font-weight:600;color:#555;"
            "margin:14px 0 6px;'>📋 Danh sách hóa đơn</div>",
            unsafe_allow_html=True
        )
        cols_show = ["Mã hóa đơn", "Thời gian", "Tên khách hàng",
                     "Khách đã trả", "Người tạo", "Chi nhánh"]
        cols_avail = [c for c in cols_show if c in hd_unique.columns]
        view = hd_unique[cols_avail].copy()
        if "Khách đã trả" in view.columns:
            view["Khách đã trả"] = view["Khách đã trả"].apply(
                lambda x: f"{_fmt(x)}đ")
        st.dataframe(view, use_container_width=True, hide_index=True,
                     height=min(400, 42 + len(view) * 35))
    else:
        st.info("Chưa có hóa đơn hoàn thành hôm nay.")


# ══════════════════════════════════════════════════════════
# TAB 1B — TỔNG QUAN DOANH THU
# ══════════════════════════════════════════════════════════

def _tab_tong_quan_dt():
    accessible = get_accessible_branches()
    active     = get_active_branch()

    col_cn, col_date = st.columns([1, 2])
    with col_cn:
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_sel = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible,
                                  key="bc_tq_cn", label_visibility="collapsed")
            load_cns = tuple(accessible) if cn_sel == "Tất cả" else (cn_sel,)
        else:
            load_cns = (active,)
            st.caption(f"📍 {active}")
    with col_date:
        d_from, d_to = _date_filter("bc_tq")

    raw = _load_hd(load_cns, d_from, d_to)
    if raw.empty:
        st.info("Không có dữ liệu trong khoảng thời gian này.")
        return

    hd_u = raw.drop_duplicates(subset=["Mã hóa đơn"], keep="first")

    hd_ban  = hd_u[~hd_u["Mã hóa đơn"].apply(_is_app_hd)]
    hd_apsc = hd_u[hd_u["Mã hóa đơn"].apply(_is_app_hd)]

    tong    = int(hd_u["Khách đã trả"].sum())
    dt_ban  = int(hd_ban["Khách đã trả"].sum())
    dt_apsc = int(hd_apsc["Khách đã trả"].sum())
    so_hd   = len(hd_u)

    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("Tổng doanh thu", f"{_fmt(tong)}đ")
    with m2: st.metric("Số hóa đơn", str(so_hd))
    with m3: st.metric("Bán hàng", f"{_fmt(dt_ban)}đ")
    with m4: st.metric("Sửa chữa (APSC)", f"{_fmt(dt_apsc)}đ")

    # ── Chart doanh thu theo ngày ──
    if "_date" in hd_u.columns and not hd_u.empty:
        try:
            import plotly.graph_objects as go
            chart = hd_u.groupby(["_date", "Chi nhánh"])["Khách đã trả"].sum().reset_index()
            chart.columns = ["Ngày", "Chi nhánh", "Doanh thu"]
            pivot = chart.pivot_table(index="Ngày", columns="Chi nhánh",
                                      values="Doanh thu", fill_value=0).sort_index()
            cmap = {
                "100 Lê Quý Đôn": "#2E86DE",
                "Coop Vũng Tàu":  "#27AE60",
                "GO BÀ RỊA":      "#F39C12",
            }
            fig = go.Figure()
            for i, cn in enumerate(pivot.columns):
                fig.add_trace(go.Bar(
                    x=[str(d) for d in pivot.index],
                    y=pivot[cn],
                    name=CN_SHORT.get(cn, cn),
                    marker_color=cmap.get(cn, ["#2E86DE","#27AE60","#F39C12"][i % 3]),
                    hovertemplate=f"{cn}<br>%{{x}}<br>%{{y:,.0f}}đ<extra></extra>",
                ))
            fig.update_layout(
                barmode="stack", height=300,
                margin=dict(l=0, r=0, t=8, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=-0.35,
                            xanchor="center", x=0.5),
                yaxis=dict(tickformat=",.0f", gridcolor="#eee"),
                xaxis=dict(title=None),
                plot_bgcolor="white", font=dict(size=11), dragmode=False,
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})
        except Exception as e:
            st.caption(f"Không thể vẽ chart: {e}")

    # ── Doanh thu theo CN ──
    if "Chi nhánh" in hd_u.columns:
        st.markdown(
            "<div style='font-size:0.82rem;font-weight:600;color:#555;"
            "margin:10px 0 6px;'>Doanh thu theo chi nhánh</div>",
            unsafe_allow_html=True
        )
        cn_sum = hd_u.groupby("Chi nhánh")["Khách đã trả"].sum().reset_index()
        cn_sum.columns = ["Chi nhánh", "Doanh thu"]
        cn_sum["Doanh thu (đ)"] = cn_sum["Doanh thu"].apply(lambda x: _fmt(x) + "đ")
        cn_sum["Tỷ lệ"] = (cn_sum["Doanh thu"] / cn_sum["Doanh thu"].sum() * 100).round(1).astype(str) + "%"
        st.dataframe(cn_sum[["Chi nhánh", "Doanh thu (đ)", "Tỷ lệ"]],
                     use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════
# TAB 1C — BÁN HÀNG THEO NHÓM
# ══════════════════════════════════════════════════════════

def _tab_ban_hang():
    accessible = get_accessible_branches()
    active     = get_active_branch()

    col_cn, col_date = st.columns([1, 2])
    with col_cn:
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_sel = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible,
                                  key="bc_bh_cn", label_visibility="collapsed")
            load_cns = tuple(accessible) if cn_sel == "Tất cả" else (cn_sel,)
        else:
            load_cns = (active,)
            st.caption(f"📍 {active}")
    with col_date:
        d_from, d_to = _date_filter("bc_bh")

    raw = _load_hd(load_cns, d_from, d_to)
    if raw.empty:
        st.info("Không có dữ liệu.")
        return

    # Chỉ lấy HĐ bán thường (không phải APSC)
    df = raw[~raw["Mã hóa đơn"].apply(_is_app_hd)].copy()
    if df.empty:
        st.info("Không có hóa đơn bán hàng trong khoảng này.")
        return

    # Join với hang_hoa để lấy loai_sp, loai_hang, thuong_hieu
    hh = load_hang_hoa()
    loai_map = {}
    if not hh.empty and "ma_hang" in hh.columns:
        for col in ["loai_sp", "loai_hang", "thuong_hieu"]:
            if col in hh.columns:
                loai_map[col] = dict(zip(hh["ma_hang"].astype(str), hh[col].fillna("")))

    if "Mã hàng" in df.columns:
        mh = df["Mã hàng"].astype(str)
        df["loai_sp"]     = mh.map(loai_map.get("loai_sp", {})).fillna("Chưa phân loại")
        df["loai_hang"]   = mh.map(loai_map.get("loai_hang", {})).fillna("Chưa phân loại")
        df["thuong_hieu"] = mh.map(loai_map.get("thuong_hieu", {})).fillna("Chưa phân loại")
    else:
        df["loai_sp"] = "Chưa phân loại"
        df["loai_hang"] = "Chưa phân loại"
        df["thuong_hieu"] = "Chưa phân loại"

    # Chọn nhóm xem
    nhom_options = ["Loại SP (HH/DV)", "Loại hàng", "Thương hiệu"]
    nhom_col_map = {
        "Loại SP (HH/DV)": "loai_sp",
        "Loại hàng":       "loai_hang",
        "Thương hiệu":     "thuong_hieu",
    }
    nhom_chon = st.selectbox("Nhóm theo:", nhom_options, key="bc_bh_nhom",
                              label_visibility="collapsed")
    nhom_col = nhom_col_map[nhom_chon]

    # Tính doanh thu theo nhóm — dùng Thành tiền (dòng item) thay vì Khách đã trả
    # để tránh sai khi group theo nhóm (Khách đã trả là tổng HĐ, không phải từng item)
    if "Thành tiền" in df.columns and "Số lượng" in df.columns:
        grp = df.groupby(nhom_col).agg(
            doanh_thu=("Thành tiền", "sum"),
            so_luong=("Số lượng", "sum"),
            so_dong=("Mã hàng", "count"),
        ).reset_index().sort_values("doanh_thu", ascending=False)
        grp.columns = [nhom_chon, "Doanh thu", "Số lượng", "Số dòng HĐ"]
        grp["Doanh thu (đ)"] = grp["Doanh thu"].apply(lambda x: _fmt(x) + "đ")
        grp["Tỷ lệ"] = (grp["Doanh thu"] / grp["Doanh thu"].sum() * 100).round(1).astype(str) + "%"
        st.dataframe(
            grp[[nhom_chon, "Doanh thu (đ)", "Số lượng", "Tỷ lệ"]],
            use_container_width=True, hide_index=True
        )
        st.caption("Doanh thu tính theo Thành tiền từng dòng hàng hóa.")
    else:
        st.warning("Cột 'Thành tiền' hoặc 'Số lượng' không có trong dữ liệu hóa đơn.")


# ══════════════════════════════════════════════════════════
# TAB 2 — XUẤT NHẬP TỒN
# ══════════════════════════════════════════════════════════

def _tab_xuat_nhap_ton():
    if not is_ke_toan_or_admin():
        st.info("Chỉ kế toán và admin được xem báo cáo xuất nhập tồn.")
        return

    accessible = get_accessible_branches()
    active     = get_active_branch()

    col_cn, col_date = st.columns([1, 2])
    with col_cn:
        if len(accessible) > 1:
            cn_sel = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible,
                                  key="bc_xnt_cn", label_visibility="collapsed")
            load_cns = tuple(accessible) if cn_sel == "Tất cả" else (cn_sel,)
        else:
            load_cns = (active,)
            st.caption(f"📍 {active}")
    with col_date:
        d_from, d_to = _date_filter("bc_xnt")

    # ── Load tất cả nguồn ──
    df_nhap = _load_nhap_hang(load_cns, d_from, d_to)
    df_ck   = _load_chuyen_hang(load_cns, d_from, d_to)
    df_kk   = _load_kiem_ke(load_cns, d_from, d_to)
    df_hd   = _load_hd(load_cns, d_from, d_to)
    # TODO: df_tra = _load_tra_hang(load_cns, d_from, d_to)  # khi có module POS

    # ── Build bảng NHẬP ──
    nhap_rows = []

    if not df_nhap.empty:
        nhap_rows.append({
            "Nguồn nhập": "Nhập hàng NCC",
            "Số phiếu/dòng": df_nhap["ma_phieu"].nunique(),
            "Tổng SL": int(df_nhap["so_luong"].sum()),
            "Giá trị (đ)": _fmt(int((df_nhap["so_luong"] * df_nhap["gia_von"]).sum())) + "đ",
        })

    if not df_ck.empty:
        ck_nhap = df_ck[df_ck["toi_chi_nhanh"].isin(set(load_cns))]
        if not ck_nhap.empty:
            nhap_rows.append({
                "Nguồn nhập": "Chuyển hàng (nhận về)",
                "Số phiếu/dòng": ck_nhap["ma_phieu"].nunique(),
                "Tổng SL": int(ck_nhap["so_luong_nhan"].sum()),
                "Giá trị (đ)": _fmt(int(
                    (ck_nhap["so_luong_nhan"] * ck_nhap["gia_chuyen"]).sum()
                )) + "đ",
            })

    if not df_kk.empty:
        kk_tang = df_kk[df_kk["chenh_lech"] > 0]
        if not kk_tang.empty:
            nhap_rows.append({
                "Nguồn nhập": "Kiểm kê (chênh lệch +)",
                "Số phiếu/dòng": kk_tang["ma_phieu_kk"].nunique(),
                "Tổng SL": int(kk_tang["chenh_lech"].sum()),
                "Giá trị (đ)": "—",
            })

    # ── Build bảng XUẤT ──
    xuat_rows = []

    if not df_hd.empty:
        # Bán hàng: dùng Số lượng * Đơn giá từng dòng item
        hd_ban = df_hd[~df_hd["Mã hóa đơn"].apply(_is_app_hd)]
        # Loại trừ Dịch vụ — chỉ tính Hàng hóa thật
        hd_ban_hh = _filter_chi_hang_hoa(hd_ban, ma_col="Mã hàng")
        if not hd_ban_hh.empty and "Số lượng" in hd_ban_hh.columns:
            xuat_rows.append({
                "Nguồn xuất": "Bán hàng",
                "Số phiếu/dòng": hd_ban_hh["Mã hóa đơn"].nunique(),
                "Tổng SL": int(hd_ban_hh["Số lượng"].sum()),
                "Giá trị (đ)": _fmt(int(hd_ban_hh["Thành tiền"].sum())) + "đ"
                    if "Thành tiền" in hd_ban_hh.columns else "—",
            })
        # Sửa chữa APSC — loại trừ dịch vụ (lau dầu, đánh bóng...) chỉ tính linh kiện
        hd_apsc = df_hd[df_hd["Mã hóa đơn"].apply(_is_app_hd)]
        hd_apsc_hh = _filter_chi_hang_hoa(hd_apsc, ma_col="Mã hàng")
        if not hd_apsc_hh.empty and "Số lượng" in hd_apsc_hh.columns:
            xuat_rows.append({
                "Nguồn xuất": "Sửa chữa (APSC) — chỉ linh kiện",
                "Số phiếu/dòng": hd_apsc_hh["Mã hóa đơn"].nunique(),
                "Tổng SL": int(hd_apsc_hh["Số lượng"].sum()),
                "Giá trị (đ)": _fmt(int(hd_apsc_hh["Thành tiền"].sum())) + "đ"
                    if "Thành tiền" in hd_apsc_hh.columns else "—",
            })

    # TODO: when POS module adds phieu_tra_hang
    # if not df_tra.empty:
    #     xuat_rows.append({
    #         "Nguồn xuất": "Trả hàng NCC",
    #         "Số phiếu/dòng": df_tra["ma_phieu"].nunique(),
    #         "Tổng SL": int(df_tra["so_luong"].sum()),
    #         "Giá trị (đ)": _fmt(int(
    #             (df_tra["so_luong"] * df_tra["gia_tra"]).sum()
    #         )) + "đ",
    #     })

    if not df_ck.empty:
        ck_xuat = df_ck[df_ck["tu_chi_nhanh"].isin(set(load_cns))]
        if not ck_xuat.empty:
            xuat_rows.append({
                "Nguồn xuất": "Chuyển hàng (gửi đi)",
                "Số phiếu/dòng": ck_xuat["ma_phieu"].nunique(),
                "Tổng SL": int(ck_xuat["so_luong_nhan"].sum()),
                "Giá trị (đ)": _fmt(int(
                    (ck_xuat["so_luong_nhan"] * ck_xuat["gia_chuyen"]).sum()
                )) + "đ",
            })

    if not df_kk.empty:
        kk_giam = df_kk[df_kk["chenh_lech"] < 0]
        if not kk_giam.empty:
            xuat_rows.append({
                "Nguồn xuất": "Kiểm kê (chênh lệch −)",
                "Số phiếu/dòng": kk_giam["ma_phieu_kk"].nunique(),
                "Tổng SL": int(kk_giam["chenh_lech"].abs().sum()),
                "Giá trị (đ)": "—",
            })

    # ── Hiển thị 2 bảng tóm tắt ──
    col_n, col_x = st.columns(2)
    with col_n:
        st.markdown(
            "<div style='font-size:0.88rem;font-weight:600;color:#1a7f37;"
            "margin-bottom:6px;'>📥 Nhập kho</div>",
            unsafe_allow_html=True
        )
        if nhap_rows:
            st.dataframe(pd.DataFrame(nhap_rows), use_container_width=True,
                         hide_index=True)
            tong_nhap = sum(r["Tổng SL"] for r in nhap_rows)
            st.caption(f"Tổng SL nhập: **{_fmt(tong_nhap)}**")
        else:
            st.info("Không có nhập kho trong kỳ này.")

    with col_x:
        st.markdown(
            "<div style='font-size:0.88rem;font-weight:600;color:#cf4c2c;"
            "margin-bottom:6px;'>📤 Xuất kho</div>",
            unsafe_allow_html=True
        )
        if xuat_rows:
            st.dataframe(pd.DataFrame(xuat_rows), use_container_width=True,
                         hide_index=True)
            tong_xuat = sum(r["Tổng SL"] for r in xuat_rows)
            st.caption(f"Tổng SL xuất: **{_fmt(tong_xuat)}**")
        else:
            st.info("Không có xuất kho trong kỳ này.")

    # ══════ TỒN ĐẦU/CUỐI KỲ ══════
    # Logic: Tồn cuối kỳ = the_kho hiện tại
    #        Tồn đầu kỳ = Cuối kỳ - Nhập + Xuất (suy ngược)
    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;color:#555;"
        "margin:18px 0 6px;'>📊 Tồn đầu / cuối kỳ (theo SL)</div>",
        unsafe_allow_html=True
    )
    st.caption(
        "Tồn cuối kỳ = tồn hiện tại từ snapshot the_kho. "
        "Tồn đầu kỳ tính ngược: Cuối − Nhập + Xuất. "
        "Chỉ tính Hàng hóa, không tính Dịch vụ."
    )

    try:
        # Tổng nhập (chỉ hàng hóa) trong kỳ
        nhap_sl = 0
        if not df_nhap.empty:
            nhap_hh = _filter_chi_hang_hoa(df_nhap, ma_col="ma_hang")
            nhap_sl += int(nhap_hh["so_luong"].sum()) if not nhap_hh.empty else 0
        if not df_ck.empty:
            ck_in = df_ck[df_ck["toi_chi_nhanh"].isin(set(load_cns))]
            ck_in_hh = _filter_chi_hang_hoa(ck_in, ma_col="ma_hang")
            nhap_sl += int(ck_in_hh["so_luong_nhan"].sum()) if not ck_in_hh.empty else 0
        if not df_kk.empty:
            kk_t = df_kk[df_kk["chenh_lech"] > 0]
            kk_t_hh = _filter_chi_hang_hoa(kk_t, ma_col="ma_hang")
            nhap_sl += int(kk_t_hh["chenh_lech"].sum()) if not kk_t_hh.empty else 0

        # Tổng xuất (chỉ hàng hóa) trong kỳ
        xuat_sl = 0
        if not df_hd.empty:
            hd_hh = _filter_chi_hang_hoa(df_hd, ma_col="Mã hàng")
            if not hd_hh.empty and "Số lượng" in hd_hh.columns:
                xuat_sl += int(hd_hh["Số lượng"].sum())
        if not df_ck.empty:
            ck_out = df_ck[df_ck["tu_chi_nhanh"].isin(set(load_cns))]
            ck_out_hh = _filter_chi_hang_hoa(ck_out, ma_col="ma_hang")
            xuat_sl += int(ck_out_hh["so_luong_nhan"].sum()) if not ck_out_hh.empty else 0
        if not df_kk.empty:
            kk_g = df_kk[df_kk["chenh_lech"] < 0]
            kk_g_hh = _filter_chi_hang_hoa(kk_g, ma_col="ma_hang")
            xuat_sl += int(kk_g_hh["chenh_lech"].abs().sum()) if not kk_g_hh.empty else 0

        # Tồn cuối kỳ từ the_kho hiện tại (chỉ hàng hóa)
        the_kho = load_the_kho(branches_key=tuple(load_cns))
        if the_kho.empty:
            ton_cuoi = 0
        else:
            tk_hh = _filter_chi_hang_hoa(the_kho, ma_col="Mã hàng")
            ton_cuoi = int(tk_hh["Tồn cuối kì"].sum()) if not tk_hh.empty else 0

        # Tồn đầu kỳ = cuối − nhập + xuất
        ton_dau = ton_cuoi - nhap_sl + xuat_sl

        t1, t2, t3, t4 = st.columns(4)
        with t1: st.metric("Tồn đầu kỳ", _fmt(ton_dau))
        with t2: st.metric("Tổng nhập", f"+{_fmt(nhap_sl)}")
        with t3: st.metric("Tổng xuất", f"−{_fmt(xuat_sl)}")
        with t4: st.metric("Tồn cuối kỳ", _fmt(ton_cuoi))
    except Exception as e:
        st.caption(f"Không tính được tồn đầu/cuối kỳ: {e}")


# ══════════════════════════════════════════════════════════
# TAB 3 — NHÂN VIÊN
# ══════════════════════════════════════════════════════════

def _tab_nhan_vien():

    accessible = get_accessible_branches()
    col_cn, col_date = st.columns([1, 2])
    with col_cn:
        cn_sel = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible,
                              key="bc_nv_cn", label_visibility="collapsed")
        load_cns = tuple(accessible) if cn_sel == "Tất cả" else (cn_sel,)
    with col_date:
        d_from, d_to = _date_filter("bc_nv")

    raw = _load_hd(load_cns, d_from, d_to)
    if raw.empty:
        st.info("Không có dữ liệu.")
        return

    # Chỉ HĐ App (APSC) — filter theo APP_INVOICE_PREFIXES
    df = raw[raw["Mã hóa đơn"].apply(_is_app_hd)].copy()
    if df.empty:
        st.info("Không có hóa đơn App (APSC) trong khoảng này.")
        return

    hd_u = df.drop_duplicates(subset=["Mã hóa đơn"], keep="first")

    # ── Theo Người tạo (thu tiền) ──
    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;color:#555;"
        "margin-bottom:6px;'>👤 Theo người thu tiền (Người tạo HĐ)</div>",
        unsafe_allow_html=True
    )
    if "Người tạo" in hd_u.columns:
        grp_tao = hd_u.groupby("Người tạo").agg(
            so_hd=("Mã hóa đơn", "count"),
            doanh_thu=("Khách đã trả", "sum"),
        ).reset_index().sort_values("doanh_thu", ascending=False)
        grp_tao.columns = ["Người tạo HĐ", "Số HĐ", "Doanh thu"]
        grp_tao["Doanh thu (đ)"] = grp_tao["Doanh thu"].apply(lambda x: _fmt(x) + "đ")
        st.dataframe(grp_tao[["Người tạo HĐ", "Số HĐ", "Doanh thu (đ)"]],
                     use_container_width=True, hide_index=True)
    else:
        st.caption("Không có cột 'Người tạo' trong dữ liệu.")

    # ── Theo Người bán (tư vấn/tạo phiếu SC) ──
    st.markdown(
        "<div style='font-size:0.88rem;font-weight:600;color:#555;"
        "margin:14px 0 6px;'>👤 Theo người tư vấn/tạo phiếu SC (Người bán)</div>",
        unsafe_allow_html=True
    )
    if "Người bán" in hd_u.columns:
        grp_ban = hd_u.groupby("Người bán").agg(
            so_hd=("Mã hóa đơn", "count"),
            doanh_thu=("Khách đã trả", "sum"),
        ).reset_index().sort_values("doanh_thu", ascending=False)
        grp_ban.columns = ["Người bán", "Số HĐ", "Doanh thu"]
        grp_ban["Doanh thu (đ)"] = grp_ban["Doanh thu"].apply(lambda x: _fmt(x) + "đ")
        st.dataframe(grp_ban[["Người bán", "Số HĐ", "Doanh thu (đ)"]],
                     use_container_width=True, hide_index=True)
    else:
        st.caption("Không có cột 'Người bán' trong dữ liệu.")


# ══════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════

def module_bao_cao():
    st.markdown("### 📊 Báo cáo")

    # ── Tab chính: ẩn "Nhân viên" nếu không phải admin ──
    main_tab_labels = ["💰 Doanh thu", "📦 Xuất nhập tồn"]
    if is_admin():
        main_tab_labels.append("👥 Nhân viên")
    main_tabs = st.tabs(main_tab_labels)

    with main_tabs[0]:
        # Sub-tab Doanh thu: ẩn "Tổng quan" và "Bán hàng theo nhóm" nếu không phải admin/ke_toan
        if is_ke_toan_or_admin():
            sub_labels = ["Cuối ngày", "Tổng quan", "Bán hàng theo nhóm"]
            sub_tabs = st.tabs(sub_labels)
            with sub_tabs[0]: _tab_cuoi_ngay()
            with sub_tabs[1]: _tab_tong_quan_dt()
            with sub_tabs[2]: _tab_ban_hang()
        else:
            _tab_cuoi_ngay()

    with main_tabs[1]:
        _tab_xuat_nhap_ton()

    if is_admin():
        with main_tabs[2]:
            _tab_nhan_vien()

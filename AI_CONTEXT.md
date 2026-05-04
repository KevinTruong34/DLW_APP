# AI_CONTEXT.md — DL Watch Store App (Web App quản lý cũ)
**Cập nhật:** 04/05/2026 | **Session tiếp theo bắt đầu từ đây**

---

## PROJECT OVERVIEW

- **Stack:** Streamlit (Python, multi-file) + Supabase (PostgreSQL)
- **Deploy:** Streamlit Cloud
- **3 chi nhánh:** 100 Lê Quý Đôn · Coop Vũng Tàu · GO BÀ RỊA
- **Codebase:** `app.py` + `utils/` (config, db, auth, helpers) + `modules/` (10 modules)

**Quan hệ với POS app:** chia sẻ database (cùng Supabase project) nhưng repo riêng, deploy riêng. Web app này là **app quản lý cũ (legacy)**, đảm nhận: hàng hóa, sửa chữa, kiểm kê, chuyển hàng, báo cáo, quản trị NV. POS app riêng biệt làm bán hàng tại quầy.

User đã **bỏ KiotViet** — adapter đã xử lý sẵn, không cần sửa thêm.

---

## CẤU TRÚC FILES

```
app.py
utils/
  config.py       ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER, APP_INVOICE_PREFIXES
  db.py           supabase client + tất cả load_* + log_action + adapter unified
  auth.py         login/logout, session, get_user, is_admin, is_ke_toan_or_admin
  helpers.py      now_vn, now_vn_iso, today_vn, fmt_vn, _normalize, _build_phieu_html, _in_phieu_sc
modules/
  tong_quan.py    Dashboard + greeting (admin only - sales overview restructured)
  hoa_don.py      Tra cứu HĐ KiotViet + AHD POS + AHDD đổi/trả (merge unified)
  hang_hoa.py     Master hàng hóa + tồn kho
  sua_chua.py     Phiếu sửa chữa (UI redesign hoàn chỉnh)
  nhap_hang.py    Nhập/Trả hàng NCC
  khach_hang.py   Danh sách + tra cứu khách hàng (tong_ban đã cộng dồn POS)
  kiem_ke.py      Kiểm kê kho
  chuyen_hang.py  Chuyển hàng giữa chi nhánh (RPC + UX fixes)
  quan_tri.py     Upload, NV, logs, kết sổ, (action_logs)
  bao_cao.py      Báo cáo doanh thu (4 cột), XNT, tồn kho, AHDD chenh_lech
```

---

## DATABASE TABLES CHÍNH

| Table | Mô tả |
|-------|-------|
| `hang_hoa` | Master sản phẩm. `active` (bool), `loai_sp` ("Hàng hóa"/"Dịch vụ"), `loai_hang`, `thuong_hieu`, `gia_ban` |
| `the_kho` | Tồn kho theo CN. Cột: `Mã hàng`, `Chi nhánh`, `Tồn cuối kì`, `id` |
| `hoa_don` | HĐ KiotViet upload (denormalized). Legacy, sẽ không có dữ liệu mới khi bỏ KiotViet |
| `phieu_sua_chua` / `_chi_tiet` | Phiếu sửa chữa. Mã prefix `APSC` |
| `phieu_chuyen_kho` | Chuyển hàng. `loai_phieu` phân biệt App vs KiotViet |
| `phieu_nhap_hang` / `_ct` | Nhập NCC |
| `phieu_tra_hang` / `_ct` | Trả NCC. Active trong `bao_cao.py` |
| `phieu_kiem_ke` / `_chi_tiet` | Kiểm kê |
| `khach_hang` | Unique key `sdt`. `tong_ban` cộng dồn KiotViet + POS + AHDD chenh_lech |
| `nhan_vien` / `nhan_vien_chi_nhanh` | NV + phân CN |
| `nha_cung_cap` | NCC |
| `action_logs` | Log thao tác (POS app chưa ghi vào — pending) |
| `sessions` | Session token (cả 2 app dùng) |

### Tables của POS (web app đọc qua adapter)

- `hoa_don_pos` / `hoa_don_pos_ct` — HĐ POS, prefix `AHD`
- `phieu_doi_tra_pos` / `phieu_doi_tra_pos_ct` — Đổi/Trả, prefix `AHDD`
- `phieu_dat_hang` — Đặt hàng theo yêu cầu, prefix `AHDC`
- `pin_code` — PIN bcrypt cho NV (POS dùng, web app không cần)

---

## KEY CONSTANTS (utils/config.py)

```python
IN_APP_MARKER   = "Chuyển hàng (App)"
ARCHIVED_MARKER = "Chuyển hàng (App - đã đồng bộ)"

# Bước 6 + 7B: thêm prefix POS + đổi/trả
APP_INVOICE_PREFIXES = ["APSC", "AHD", "AHDD"]

# Helpers phân loại trong bao_cao.py:
APSC_PREFIXES = ["APSC"]                             # Sửa chữa
POS_PREFIXES  = ["AHD"]                              # POS bán hàng
AHDD_PREFIXES = ["AHDD"]                             # POS đổi/trả
```

### Helpers phân loại (bao_cao.py)

```python
_is_apsc_hd(ma)       # APSC riêng
_is_pos_hd(ma)        # AHD riêng (KHÔNG bao gồm AHDD)
_is_ahdd_hd(ma)       # AHDD riêng — Bước 7B
_is_app_hd(ma)        # APSC + AHD (KHÔNG bao gồm AHDD — chỉ HĐ thuần)
_is_kiotviet_hd(ma)   # Còn lại (KiotViet legacy)
```

**Lưu ý:** `_is_pos_hd` chỉ AHD, không match AHDD. Nếu cần bao trùm POS toàn bộ phải dùng `_is_pos_hd(ma) or _is_ahdd_hd(ma)`.

---

## IMPORT CHUẨN

```python
from utils.helpers import _normalize, now_vn, now_vn_iso, today_vn, fmt_vn
from datetime import datetime, timedelta
```

---

## COMPLETED — TẤT CẢ VIỆC ĐÃ LÀM

### Bước 6 — Adapter POS (đã làm session trước)

```python
# utils/db.py:

@st.cache_data(ttl=300, show_spinner=False)
def _load_hoa_don_pos_flat(branches_key):
    # Load hoa_don_pos + hoa_don_pos_ct
    # JOIN phieu_dat_hang qua ma_pdh để lấy cọc PTTT chi tiết (Bước 8)
    # Flatten thành format giống hoa_don (KiotViet denormalized)
    # Map: ma_hd → "Mã hóa đơn", created_at → "Thời gian" dd/MM/yyyy HH:mm:ss

@st.cache_data(ttl=300, show_spinner=False)
def load_hoa_don_unified(branches_key):
    df_old = load_hoa_don(branches_key)
    df_pos = _load_hoa_don_pos_flat(branches_key)
    df_ahdd = _load_phieu_doi_tra_flat(branches_key)   # Bước 7B
    return pd.concat([df_old, df_pos, df_ahdd], ignore_index=True, sort=False)

def invalidate_hoa_don_cache(): ...
```

Modules đã đổi `load_hoa_don()` → `load_hoa_don_unified()`:
- `modules/hoa_don.py` — tab tra cứu hiện cả AHD + AHDD
- `modules/khach_hang.py` — tab_detail
- `modules/tong_quan.py` — `module_tong_quan` + `hien_thi_dashboard`
- `modules/bao_cao.py` — phức tạp hơn (xem dưới)

### Bước 7B — Adapter cho AHDD đổi/trả (mới session này)

**4 quyết định:**

1. **Doanh thu gộp:** cộng `chenh_lech` AHDD vào doanh thu (chenh_lech > 0 thu thêm; < 0 hoàn tiền)
2. **Bán hàng theo nhóm:** tính **net items** (items mới trừ items trả) cho XNT chính xác
3. **`khach_hang.tong_ban`:** cộng dồn `chenh_lech` AHDD theo SĐT (chỉ "Hoàn thành")
4. **Tab "Tra cứu HĐ":** merge AHDD vào danh sách, hiển thị badge "Đổi/Trả"

**Implementation:**

- `_load_phieu_doi_tra_flat()` trong `utils/db.py` — flatten AHDD theo `kieu`:
  - `kieu="moi"` → đóng vai trò bán hàng (số dương)
  - `kieu="tra"` → đóng vai trò trả hàng (số âm — giảm doanh thu, giảm bán hàng)
- `bao_cao.py` báo cáo doanh thu: caption "💡 Bán hàng — KiotViet: X · POS: Y · Đổi/Trả: Z"
- `bao_cao.py` XNT: dòng "Bán hàng (POS - Đổi/Trả)" tách riêng
- `khach_hang.py` `load_khach_hang_list`: aggregate AHDD chenh_lech theo SĐT

### Bước 8 reflect web app

- `_load_hoa_don_pos_flat` JOIN `phieu_dat_hang` qua `ma_pdh` để fetch cọc PTTT chi tiết (3 cột)
- Tab tra cứu hóa đơn web app: HĐ có `ma_pdh` hiện badge "Từ phiếu đặt"
- Tab Ngày tháng (bao_cao): date range picker 3 cột (từ ngày, đến ngày, áp dụng)

### Tong_quan restructure (đã làm)

- Sales overview (revenue metrics + stacked bar chart by branch) **chuyển vào admin section** (password-protected)
- Tab Tổng quan public-facing (employee) là placeholder cho future reports

### modules/sua_chua.py — UI Redesign hoàn chỉnh
**CSS scoped** trong `_SC_CSS`:
- Classes: `sc-card`, `sc-badge`, `sc-badge-green`, `sc-badge-red`, `sc-section-title`
- `sc-money-card`, `sc-money-card-red`, `sc-money-label`, `sc-money-value`, `sc-money-value-red`
- `sc-info-row`, `sc-info-label`, `sc-info-val`

**4 tabs:** Danh sách / Tạo mới / Chi tiết & Cập nhật (Search + Selectbox cùng hàng `col_s`/`col_p`) / Tạo HĐ sửa (Search + Selectbox `col_sh`/`col_ph`).

### modules/hang_hoa.py — Admin features
- Form thêm hàng: `st.radio("Loại SP", ["Hàng hóa", "Dịch vụ"], index=0, horizontal=True)`
- Soft-delete (ẩn): xác nhận 2 bước → `active = False`
- Sửa thông tin
- Chỉnh tồn kho trực tiếp `_render_ton_kho`
- `load_hang_hoa()` filter `.neq("active", False)`
- SQL đã chạy: `ALTER TABLE hang_hoa ADD COLUMN active boolean DEFAULT true;`

### modules/bao_cao.py
- Tab **Tồn kho:** filter, pivot, metrics, chi tiết, tóm tắt
- `_load_tra_hang()` đúng (NCC)
- `df_tra` tích hợp `_tab_xuat_nhap_ton`
- Tab **Nhân viên** (admin only)

### modules/chuyen_hang.py — RPC + UX fixes
- RPC `xac_nhan_chuyen_hang`: lock FOR UPDATE, validate, trừ kho nguồn atomic, GIỮ `IN_APP_MARKER`
- RPC `nhan_hang`: cộng kho đích, set `ARCHIVED_MARKER`
- Fix checkbox `disabled=not confirmed`
- Fix tab văng về Danh sách: đảo thứ tự khi `ck_editing`
- Fix `has_overflow`: render `number_input` trước → apply `new_sl` → tính `over`

### modules/quan_tri.py — module_nhan_vien()
- Multiselect CN với diff logic (DELETE bỏ, INSERT thêm)
- Query thêm `chi_nhanh_id` để có ID khi DELETE

### utils/helpers.py — Timezone
- `now_vn()`, `now_vn_iso()`, `today_vn()`, `fmt_vn()` dùng `ZoneInfo("Asia/Ho_Chi_Minh")`
- Applied: nhap_hang, sua_chua, quan_tri, kiem_ke, chuyen_hang, db, tong_quan

### Admin upload v10
- Drag-and-drop Excel uploads trong app, replacing manual Supabase Dashboard
- CSV formatting fix: handle commas trong product names khi convert

### Inventory cards
- Đã import cho cả 3 CN
- Limitation: static snapshots không hỗ trợ true date-based inventory lookup (cần transaction-level data)

---

## SQL ĐÃ CHẠY TRÊN SUPABASE

```sql
ALTER TABLE hang_hoa ADD COLUMN active boolean DEFAULT true;
UPDATE hang_hoa SET active = true WHERE active IS NULL;

-- RPC: xac_nhan_chuyen_hang, nhan_hang
-- (xem rpc_chuyen_hang.sql)
```

POS-related SQL chạy trên cùng Supabase (xem POS AI_CONTEXT.md):
- `pos_setup.sql`, `pos_patch_01..07.sql`

---

## PERFORMANCE — PHÂN TÍCH (chưa fix)

### Vấn đề
Load module 3–10s, spinner xuất hiện khi chuyển module (đặc biệt Báo cáo).

### Nguyên nhân

**1. Nested cached calls:**
```
load_the_kho() ttl=300
  └─ load_stock_deltas() ttl=60   ← hết hạn 60s → spinner
       └─ (trong load_the_kho) load_hang_hoa() ttl=600
```

**2. `st.cache_data.clear()` toàn bộ** — 26 chỗ. Mỗi thao tác xóa toàn bộ cache.

**3. Nested trong bao_cao.py** — `_load_lich_su_ma_hang()` gọi `load_the_kho()`.

**4. Adapter unified gọi 3 nguồn** (KiotViet + POS + AHDD) trong 1 lần load — chưa parallel.

### Hướng fix (chưa implement)
1. Thêm `show_spinner=False` cho `load_stock_deltas()` và `load_hang_hoa()`
2. Tăng TTL `load_stock_deltas` 60s → 300s (đồng bộ `load_the_kho`)
3. Targeted cache invalidation thay vì `clear()` toàn bộ
4. Trước fix: thêm timing log để đo bottleneck thực tế

---

## KEY DECISIONS

| # | Quyết định |
|---|------------|
| D1 | RPC Hybrid: Python xử lý UI/validation, Supabase RPC cho "chốt chặn cuối" |
| D2 | `phieu_tra_hang` = Trả NCC. Đổi trả khách dùng bảng riêng `phieu_doi_tra_pos` (POS) |
| D3 | RPC archive logic: `xac_nhan` GIỮ `IN_APP_MARKER`. `nhan_hang` set `ARCHIVED_MARKER` |
| D4 | Service layer: chưa cần |
| D5 | Timezone: `timestamptz` + `ZoneInfo` không phải offset thủ công |
| D6 | `loai_sp` = "Hàng hóa" mặc định khi thêm hàng |
| D7 | Bước 6 adapter: tách prefix APSC / AHD / KiotViet, hiện 4 cột doanh thu |
| D8 | Bước 7B: tách AHDD riêng khỏi AHD, không gộp vào "Bán hàng (POS)" — show riêng "Đổi/Trả" |
| D9 | Bước 7B: `khach_hang.tong_ban` = sum KiotViet + POS + AHDD chenh_lech |
| D10 | AHDD `chenh_lech` âm (shop hoàn) trừ doanh thu | 
| D11 | Tong_quan public-facing là placeholder, sales overview chỉ admin |

---

## PENDING ROADMAP

### Kỹ thuật

| # | Task | Khi nào |
|---|------|---------|
| 1 | RPC Nhập/Trả NCC (atomic) | TBD |
| 2 | UI khôi phục hàng bị ẩn (un-hide) | TBD — **NHẮC KHI USER YÊU CẦU** |
| 3 | Cân bằng `the_kho` từ kiểm kê (`_kk_approve` chưa update) | TBD |
| 4 | Fix cache/spinner: timing log → targeted invalidation | Ưu tiên |
| 5 | Warning upload thiếu cột "Loại hàng" | TBD |
| 6 | Logs thao tác POS app vào `action_logs` (pending từ POS) | Khi rảnh |
| 7 | UI admin xem session POS active (LS-3 đã có DB schema, chưa có UI) | TBD |
| 8 | Module Chấm công — app Streamlit riêng | Future |

---

## TECHNICAL NOTES

### Mã phiếu
- SC, CH, KK: query max + 1 trong Python
- PNH, TH, APSC, AKH: Postgres sequence/function qua `supabase.rpc("get_next_*_num")`
- POS: AHD, AHDD, AHDC dùng sequence riêng (xem POS AI_CONTEXT)
- Xóa phiếu cũ không tái sử dụng mã

### `load_stock_deltas()`
- Chỉ tính delta cho `loai_phieu = IN_APP_MARKER`
- Sau `nhan_hang` → `ARCHIVED_MARKER` → bỏ qua → tránh double-count

### `_filter_chi_hang_hoa()` (bao_cao)
- Lọc giữ `loai_sp = "Hàng hóa"`, bỏ Dịch vụ
- Dùng: tab XNT, tính tồn đầu/cuối kỳ

### Scroll-to-top sau lưu (sua_chua)
```python
st.session_state["sc_scroll_top"] = True
# Đầu tab_detail:
if st.session_state.pop("sc_scroll_top", False):
    st.components.v1.html(
        "<script>window.parent.document.querySelector('section.main').scrollTo(0,0);</script>",
        height=0
    )
```

### Expander tự đóng khi rerun (sua_chua)
```python
if (st.session_state.get("sc_upd_dv_ma_tim", "").strip()
        or st.session_state.get("sc_upd_items", [])):
    st.session_state["sc_upd_open"] = True
```

### Bug fix (đã làm)

- `_load_hoa_don_pos_flat` thiếu `tien_coc_da_thu` → join `phieu_dat_hang` qua `ma_pdh`
- Tab Ngày tháng: thay 1 ô filter ngày → 3 cột date range picker
- `'dict' object has no attribute 'DataFrame'` → đổi tên loop var `pd` → `_pdat_row`

---

## CHECKLIST BÀN GIAO

Claude session mới nên:

1. ✅ Đọc `CLAUDE.md` trong project knowledge
2. ✅ Đọc 2 file `AI_CONTEXT.md` (POS + Web)
3. ✅ Hỏi user gửi file Python liên quan trước khi code
4. ✅ Đề xuất plan kỹ thuật, đợi approve
5. ✅ Code, deliver patch hoặc full files

---

## STYLE GUIDE

(Xem POS AI_CONTEXT — cùng style, cùng user)

- Tiếng Việt, "mình/bạn"
- CLAUDE.md: think-before-code, simplicity, surgical changes
- Trình bày 2-3 lựa chọn khi có choice, recommend 1
- Dùng `ask_user_input_v0` cho options nhanh

---

## TROUBLESHOOTING REFERENCE

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| Báo cáo load chậm | Cache nested + clear() | Pending — xem Performance section |
| HĐ POS không hiện | Cache 5 phút | Bấm "↺ Tải lại" |
| AHDD không vào báo cáo | Cache adapter | Cùng cách trên |
| Multiselect CN crash khi DELETE | Thiếu `chi_nhanh_id` | Đã fix Bước 5 |
| Duplicate widget ID | Key trùng tab | Dùng key unique theo tab |
| Streamlit credentials sai | URL vs secret key swap | Check format `https://[id].supabase.co` cho URL |

---

## CONTACT

User: **Kevin**, chủ DL Watch ở Bà Rịa - Vũng Tàu. Liên hệ qua chat Claude.

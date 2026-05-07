# AI_CONTEXT.md — DL Watch Store App (Web App quản lý cũ)
**Cập nhật:** 07/05/2026 | **Session tiếp theo bắt đầu từ đây**

---

## PROJECT OVERVIEW

- **Stack:** Streamlit (Python, multi-file) + Supabase (PostgreSQL)
- **Deploy:** Streamlit Cloud
- **3 chi nhánh:** 100 Lê Quý Đôn · Coop Vũng Tàu · GO BÀ RỊA
- **Codebase:** `app.py` + `utils/` (config, db, auth, helpers) + `modules/` (10 modules)
- **Repo:** `KevinTruong34/DLW_APP`

**Quan hệ với POS app:** chia sẻ database (cùng Supabase project) nhưng repo riêng, deploy riêng. Web app này là **app quản lý cũ (legacy)**, đảm nhận: hàng hóa, sửa chữa, kiểm kê, chuyển hàng, báo cáo, quản trị NV. POS app riêng biệt làm bán hàng tại quầy.

User đã **bỏ KiotViet** — adapter đã xử lý sẵn. Đã hoàn tất **Migration Hướng B (single-source-of-truth)** ngày 06-07/05/2026.

---

## CẤU TRÚC FILES

```
app.py
utils/
  config.py       ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER, APP_INVOICE_PREFIXES
  db.py           supabase client + load_* + log_action + adapter unified
                  ★ Hướng B: bỏ apply delta block trong load_the_kho
                  ★ load_stock_deltas() = deprecated stub return {}
  auth.py         login/logout, session, get_user, is_admin, is_ke_toan_or_admin
  helpers.py      now_vn, now_vn_iso, today_vn, fmt_vn, _normalize, _build_phieu_html, _in_phieu_sc
modules/
  tong_quan.py    Dashboard + greeting (admin only - sales overview restructured)
  hoa_don.py      Tra cứu HĐ KiotViet + AHD POS + AHDD đổi/trả (merge unified)
  hang_hoa.py     Master hàng hóa + tồn kho. ⚠ BUG: form chỉnh tồn ghi raw vào the_kho
                  (sau Hướng B không tác hại vì delta=0, nhưng nên fix khi đụng tới)
  sua_chua.py     Phiếu sửa chữa. ⚠ BUG: now_vn shadowing trong _tao_hoa_don_apsc — PENDING APPLY
  nhap_hang.py    Nhập/Trả hàng NCC
  khach_hang.py   Danh sách + tra cứu khách hàng (tong_ban đã cộng dồn POS)
  kiem_ke.py      Kiểm kê kho. ★ _kk_approve gọi RPC duyet_phieu_kiem_ke (07/05)
  chuyen_hang.py  Chuyển hàng giữa chi nhánh (RPC + UX fixes)
  quan_tri.py     Upload, NV, logs. ★ Đã clean banner archive + bỏ block KẾT SỔ APP
  bao_cao.py      Báo cáo doanh thu (4 cột), XNT, tồn kho, AHDD chenh_lech
```

---

## DATABASE TABLES CHÍNH

| Table | Mô tả |
|-------|-------|
| `hang_hoa` | Master sản phẩm. `active` (bool), `loai_sp` ("Hàng hóa"/"Dịch vụ"), `loai_hang`, `thuong_hieu`, `gia_ban` |
| `the_kho` | **Tồn kho LIVE — SINGLE SOURCE OF TRUTH (Hướng B 06-07/05/2026)**. Cột: `Mã hàng`, `Chi nhánh`, `Tồn cuối kì`, `id`. Mọi update qua RPC atomic |
| `hoa_don` | HĐ KiotViet upload (denormalized) + APSC sửa chữa từ web app + LINE Branch 3 nghe webhook trên đây |
| `phieu_sua_chua` / `_chi_tiet` | Phiếu sửa chữa. Mã prefix `APSC` |
| `phieu_chuyen_kho` | Chuyển hàng. `loai_phieu` phân biệt App vs KiotViet |
| `phieu_nhap_hang` / `_ct` | Nhập NCC |
| `phieu_tra_hang` / `_ct` | Trả NCC |
| `phieu_kiem_ke` / `_chi_tiet` | Kiểm kê. RPC duyệt apply trực tiếp the_kho |
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

## ★ HƯỚNG B — SINGLE SOURCE OF TRUTH (Migration 06-07/05/2026)

### Quyết định kiến trúc

App = **single source of truth** cho tồn kho. `the_kho.Tồn cuối kì` là **live data**, không còn delta layer.

**Trước:** `load_the_kho` tính `the_kho` snapshot + apply delta từ phiếu chuyển/nhập/kiểm kê → ra UI value. Có thể không khớp DB.

**Sau (Hướng B):** UI đọc thẳng `the_kho.Tồn cuối kì`. Mọi RPC ghi `the_kho` atomic. Delta layer bị bypass.

### Implementation

**`utils/db.py` (web app):**
- `load_the_kho`: bỏ block apply delta hoàn toàn
- `load_stock_deltas()`: deprecated → trả về `{}` stub (giữ tên để không break import)
- Bonus fix: `pd.to_datetime(utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")` cho `load_phieu_chuyen_kho._ngay` và `load_phieu_kiem_ke._created`

**RPC patch — `xac_nhan_chuyen_hang`:**
- Step 5 thêm `loai_phieu = 'Chuyển hàng (App - đã đồng bộ)'` (`ARCHIVED_MARKER`)
- Consistency với RPC `nhan_hang`
- (Initial deploy bị 2F005 do user paste thiếu RETURN cuối — fix bằng paste lại toàn bộ RPC)

**RPC mới — `duyet_phieu_kiem_ke(p_ma_phieu, p_nguoi_duyet)`:**
- Lock phiếu, validate trạng thái 'Chờ duyệt admin', validate phiếu có dòng
- Apply `sl_thuc_te` vào `the_kho` (UPDATE/INSERT)
- Ghi `chenh_lech`, archive trạng thái 'Đã duyệt', set `approved_at = NOW()`
- **Bug phát hiện:** trước migrate, `_kk_approve` chỉ ghi chenh_lech, KHÔNG update the_kho — duyệt ẢO. Sau migrate cần apply trực tiếp.

**Module patches deployed:**
- `kiem_ke.py` `_kk_approve`: gọi RPC `duyet_phieu_kiem_ke` thay logic cũ (PENDING: thêm lại import `now_vn_iso` nếu thiếu)
- `quan_tri.py`: 
  - Xóa banner `get_archive_reminder()` ở đầu module (delta layer = 0 nên không cần)
  - Xóa block "KẾT SỔ PHIẾU APP" trong tab Xóa dữ liệu (~40 dòng)
  - Tab s2 (Upload Thẻ kho) giờ là "force update tồn kho đồng loạt" — admin tool

### Workflow sau Hướng B

| Action | RPC ghi `the_kho` | Loại phiếu sau khi xong |
|--------|-------------------|--------------------------|
| Bán hàng POS | `tao_hoa_don_pos` | (HĐ riêng) |
| Hủy HĐ POS | `huy_hoa_don_pos` | (hoàn kho) |
| Đổi/trả POS | `tao_phieu_doi_tra_pos` | (atomic) |
| Hủy đổi/trả | `huy_phieu_doi_tra_pos` | (đảo ngược kho) |
| Tạo HĐ APSC | `_tao_hoa_don_apsc` (Python, không qua RPC) | trừ kho thủ công |
| Chuyển hàng — xác nhận | `xac_nhan_chuyen_hang` | `IN_APP_MARKER` (đang chuyển) |
| Chuyển hàng — nhận | `nhan_hang` | `ARCHIVED_MARKER` (đã đồng bộ) |
| Duyệt kiểm kê | `duyet_phieu_kiem_ke` | (atomic apply) |

### Test confirm (07/05/2026)

User confirmed: "Ok đã test chuyển hàng/bán hàng POS, tồn kho từng bước đúng như plan test."

Tồn âm UI residual (1 phiếu Đang chuyển CH000011 cũ) tự fix sau khi GO nhận phiếu hoặc xóa phiếu. Đã có DO block PostgreSQL atomic xóa phiếu test (đảo kho theo trạng thái + DELETE).

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

### Bước 6 — Adapter POS (session trước)

```python
# utils/db.py:
@st.cache_data(ttl=300, show_spinner=False)
def _load_hoa_don_pos_flat(branches_key):
    # Load hoa_don_pos + hoa_don_pos_ct
    # JOIN phieu_dat_hang qua ma_pdh để lấy cọc PTTT chi tiết (Bước 8)
    # Flatten thành format giống hoa_don (KiotViet denormalized)

@st.cache_data(ttl=300, show_spinner=False)
def load_hoa_don_unified(branches_key):
    df_old = load_hoa_don(branches_key)
    df_pos = _load_hoa_don_pos_flat(branches_key)
    df_ahdd = _load_phieu_doi_tra_flat(branches_key)
    return pd.concat([df_old, df_pos, df_ahdd], ignore_index=True, sort=False)

def invalidate_hoa_don_cache(): ...
```

Modules đã đổi `load_hoa_don()` → `load_hoa_don_unified()`: `hoa_don.py`, `khach_hang.py`, `tong_quan.py`, `bao_cao.py`.

### Bước 7B — Adapter cho AHDD đổi/trả

(1) Doanh thu cộng `chenh_lech` AHDD; (2) Bán hàng theo nhóm tính net items; (3) `khach_hang.tong_ban` cộng dồn `chenh_lech`; (4) Tab tra cứu HĐ web app merge AHDD với badge "Đổi/Trả".

`_load_phieu_doi_tra_flat()` flatten AHDD theo `kieu`: `kieu="moi"` → bán hàng (số dương); `kieu="tra"` → trả hàng (số âm — giảm doanh thu, giảm bán hàng).

### Bước 8 reflect web app

- `_load_hoa_don_pos_flat` JOIN `phieu_dat_hang` qua `ma_pdh` để fetch cọc PTTT chi tiết (3 cột)
- Tab tra cứu hóa đơn web app: HĐ có `ma_pdh` hiện badge "Từ phiếu đặt"
- Tab Ngày tháng (bao_cao): date range picker 3 cột (từ ngày, đến ngày, áp dụng)

### Tong_quan restructure

Sales overview chuyển vào admin section (password-protected). Tab Tổng quan public-facing là placeholder.

### modules/sua_chua.py — UI Redesign

**CSS scoped** trong `_SC_CSS`: classes `sc-card`, `sc-badge`, `sc-money-card`, etc.

**4 tabs:** Danh sách / Tạo mới / Chi tiết & Cập nhật / Tạo HĐ sửa.

**Function `_tao_hoa_don_apsc`:** insert thẳng vào `hoa_don` table (không qua RPC). Mỗi item là 1 row riêng (denormalized KiotViet schema). Insert N rows trong 1 batch `.insert([...])`.

⚠ **Bug `now_vn` shadowing — PENDING APPLY:**
```python
# Hiện tại (sai):
now_vn = now_vn()  # local var shadow function — UnboundLocalError
# Fix:
now_dt = now_vn()
now_str = now_dt.strftime("%d/%m/%Y %H:%M:%S")
```

### modules/hang_hoa.py — Admin features

- Form thêm hàng: `loai_sp` radio mặc định "Hàng hóa"
- Soft-delete (ẩn): `active = False` xác nhận 2 bước
- Sửa thông tin
- Chỉnh tồn kho trực tiếp `_render_ton_kho`
- `load_hang_hoa()` filter `.neq("active", False)`
- SQL đã chạy: `ALTER TABLE hang_hoa ADD COLUMN active boolean DEFAULT true;`

⚠ **Bug noted (không tác hại sau Hướng B):** Form chỉnh tồn đọc value từ `load_the_kho` (UI value đã apply delta) nhưng ghi raw vào `the_kho`. Sau Hướng B, UI value = the_kho value (delta=0) nên bug không còn ảnh hưởng. Để đó, fix khi đụng tới module.

### modules/bao_cao.py

- Tab **Tồn kho:** filter, pivot, metrics, chi tiết, tóm tắt
- `_load_tra_hang()` đúng (NCC)
- `df_tra` tích hợp `_tab_xuat_nhap_ton`
- Tab **Nhân viên** (admin only)

### modules/chuyen_hang.py — RPC + UX fixes

- RPC `xac_nhan_chuyen_hang`: lock FOR UPDATE, validate, trừ kho nguồn atomic, GIỮ `IN_APP_MARKER` cho phiếu Đang chuyển
- RPC `nhan_hang`: cộng kho đích, set `ARCHIVED_MARKER`
- ★ **07/05/2026 patch:** `xac_nhan_chuyen_hang` step 5 thêm archive `loai_phieu = ARCHIVED_MARKER` (consistency)
- Fix checkbox `disabled=not confirmed`
- Fix tab văng về Danh sách: đảo thứ tự khi `ck_editing`
- Fix `has_overflow`: render `number_input` trước → apply `new_sl` → tính `over`

### modules/kiem_ke.py — RPC atomic duyệt (07/05/2026)

★ **`_kk_approve` patched:** gọi RPC `duyet_phieu_kiem_ke(p_ma_phieu, p_nguoi_duyet)` thay logic cũ (chỉ ghi `chenh_lech` không update the_kho — duyệt ẢO).

User confirmed apply OK sau khi thêm lại `now_vn_iso` vào import (mình lỡ recommend bỏ).

### modules/quan_tri.py — Cleanup post Hướng B (07/05/2026)

- Xóa banner `get_archive_reminder()` ở đầu module
- Xóa block "KẾT SỔ PHIẾU APP" trong tab "Xóa dữ liệu" (~40 dòng)
- Tab s2 (Upload Thẻ kho) ý nghĩa mới: "force update tồn kho đồng loạt" (admin tool, không phải snapshot reset)
- module_nhan_vien() giữ nguyên: multiselect CN với diff logic + `chi_nhanh_id` query

### utils/helpers.py — Timezone

- `now_vn()`, `now_vn_iso()`, `today_vn()`, `fmt_vn()` dùng `ZoneInfo("Asia/Ho_Chi_Minh")`
- Applied: nhap_hang, sua_chua, quan_tri, kiem_ke, chuyen_hang, db, tong_quan

### Admin upload v10

Drag-and-drop Excel uploads trong app, replacing manual Supabase Dashboard. CSV formatting fix: handle commas trong product names khi convert.

### LINE Notification (full picture)

**Architecture:** Event-driven Edge Function (Deno/TypeScript) tên `line-notify`. Python KHÔNG gọi LINE. Database webhook → Edge Function → LINE Push API.

**3 nhánh hiện tại:**
- **Branch 1:** webhook `phieu_doi_tra_pos` INSERT → đổi/trả notification
- **Branch 2:** webhook `hoa_don_pos` INSERT → HĐ POS với phân loại VIP/AHDC/thường
- **Branch 3 (07/05/2026):** webhook `hoa_don` INSERT → APSC sửa chữa
  - Filter `record["Mã hóa đơn"]` startsWith `'APSC'` (bỏ qua HĐ KiotViet khác)
  - **Dedupe race-free:** 1 APSC = N rows insert. Chỉ row có id thấp nhất gửi LINE. Query `.lt('id', record.id)` — nếu có row cũ hơn → skip.
  - Đợi 1.5s rồi query toàn bộ rows cùng `ma_hd` để build danh sách dịch vụ
  - Đọc cột tiếng Việt: `record["Chi nhánh"]`, `record["Tổng tiền hàng"]`, `record["Người bán"]`, `record["Mã YCSC"]`, etc.
  - **Status (07/05):** đã deploy, đợi user tạo APSC để test

**Định tuyến CN:** Cấu hình cứng trong code TS:
- `100 LQĐ` + `GO BÀ RỊA` → cùng group `LINE_GROUP_BARIA`
- `Coop Vũng Tàu` → return 200, skip

**Group ID:** lấy bằng webhook.site sniff payload. Auto-response messages tắt.

---

## SQL ĐÃ CHẠY TRÊN SUPABASE

```sql
-- Đã chạy trước
ALTER TABLE hang_hoa ADD COLUMN active boolean DEFAULT true;
UPDATE hang_hoa SET active = true WHERE active IS NULL;

-- RPC: xac_nhan_chuyen_hang (gốc), nhan_hang
-- (xem rpc_chuyen_hang.sql)

-- ★ 07/05/2026: Hướng B
-- 1. RPC patch xac_nhan_chuyen_hang: step 5 thêm
--    UPDATE phieu_chuyen_kho SET loai_phieu = ARCHIVED_MARKER WHERE...
-- 2. RPC mới duyet_phieu_kiem_ke(p_ma_phieu, p_nguoi_duyet)
--    Lock + validate + apply sl_thuc_te vào the_kho + archive trạng thái
```

POS-related SQL chạy trên cùng Supabase (xem POS AI_CONTEXT.md):
- `pos_setup.sql`, `pos_patch_01..07.sql`

Edge Function deploy:
- `supabase/functions/line-notify/index.ts` — 3 nhánh (đổi/trả, HĐ POS, APSC)

---

## PERFORMANCE — PHÂN TÍCH (chưa fix, vẫn pending)

### Vấn đề
Load module 3–10s, spinner xuất hiện khi chuyển module (đặc biệt Báo cáo).

### Nguyên nhân (sau Hướng B đã giảm bớt)

**1. Nested cached calls:**
```
load_the_kho() ttl=300
  └─ ★ Sau Hướng B: KHÔNG còn gọi load_stock_deltas() (đã stub)
       chỉ còn gọi load_hang_hoa() ttl=600 cho join thông tin SP
```

**2. `st.cache_data.clear()` toàn bộ** — 26 chỗ. Mỗi thao tác xóa toàn bộ cache.

**3. Nested trong bao_cao.py** — `_load_lich_su_ma_hang()` gọi `load_the_kho()`.

**4. Adapter unified gọi 3 nguồn** (KiotViet + POS + AHDD) trong 1 lần load — chưa parallel.

### Hướng fix (chưa implement)
1. Thêm `show_spinner=False` cho `load_hang_hoa()` 
2. Targeted cache invalidation thay vì `clear()` toàn bộ
3. Trước fix: thêm timing log để đo bottleneck thực tế

---

## KEY DECISIONS

| # | Quyết định |
|---|------------|
| D1 | RPC Hybrid: Python xử lý UI/validation, Supabase RPC cho "chốt chặn cuối" |
| D2 | `phieu_tra_hang` = Trả NCC. Đổi trả khách dùng bảng riêng `phieu_doi_tra_pos` (POS) |
| D3 | RPC archive logic: `xac_nhan` GIỮ `IN_APP_MARKER`. `nhan_hang` set `ARCHIVED_MARKER`. ★ 07/05: `xac_nhan_chuyen_hang` step 5 cũng archive cho consistency |
| D4 | Service layer: chưa cần |
| D5 | Timezone: `timestamptz` + `ZoneInfo` không phải offset thủ công |
| D6 | `loai_sp` = "Hàng hóa" mặc định khi thêm hàng |
| D7 | Bước 6 adapter: tách prefix APSC / AHD / KiotViet, hiện 4 cột doanh thu |
| D8 | Bước 7B: tách AHDD riêng khỏi AHD, không gộp vào "Bán hàng (POS)" — show riêng "Đổi/Trả" |
| D9 | Bước 7B: `khach_hang.tong_ban` = sum KiotViet + POS + AHDD chenh_lech |
| D10 | AHDD `chenh_lech` âm (shop hoàn) trừ doanh thu |
| D11 | Tong_quan public-facing là placeholder, sales overview chỉ admin |
| D12 | ★ Hướng B: `the_kho` = SSOT, bỏ delta layer hoàn toàn |
| D13 | ★ Tab s2 (Upload Thẻ kho) sau Hướng B = "force update tồn kho đồng loạt" admin tool |
| D14 | ★ Bug `hang_hoa.py` form chỉnh tồn (read UI value, write raw) noted nhưng không fix vì sau Hướng B không tác hại |
| D15 | ★ POS lich_su hiện 3 nguồn: hoa_don_pos + phieu_doi_tra_pos + hoa_don APSC (read-only) |
| D16 | ★ LINE Branch 3 APSC: dedupe `lt id` race-free thay vì add column flag |

---

## PENDING ROADMAP

### Kỹ thuật

| # | Task | Khi nào | Note |
|---|------|---------|------|
| 1 | Apply bug fix `sua_chua.py` `now_vn` shadowing | Ngay | Rename local var → `now_dt`. PENDING APPLY |
| 2 | Test LINE APSC notification | Khi user tạo APSC mới | User: "đợi kết quả khi có hóa đơn phiếu sửa sau" |
| 3 | RPC Nhập/Trả NCC (atomic) | TBD | Hiện ghi không atomic |
| 4 | UI khôi phục hàng bị ẩn (un-hide) | TBD | **NHẮC KHI USER YÊU CẦU** |
| 5 | Fix cache/spinner: timing log → targeted invalidation | Ưu tiên | Đỡ hơn sau Hướng B nhưng vẫn cần |
| 6 | Warning upload thiếu cột "Loại hàng" | TBD | |
| 7 | Logs thao tác POS app vào `action_logs` | Khi rảnh | Chia với POS context |
| 8 | UI admin xem session POS active | TBD | DB schema có sẵn (LS-3) |
| 9 | Module Chấm công — app Streamlit riêng | Future | |
| 10 | Reconciliation mode cho Tab s2 (tạo phiếu kiểm kê tự động từ file KiotViet) | Deferred | |
| 11 | LINE notification mở rộng | TBD | Đổi/trả + phiếu đặt hoàn thành |
| 12 | Imports thừa (load_stock_deltas, IN_APP_MARKER ngoài badge UI) | Cosmetic cleanup | |
| 13 | use_container_width deprecated sau 2025-12-31 | Toàn codebase | width='stretch' |

---

## TECHNICAL NOTES

### Mã phiếu
- SC, CH, KK: query max + 1 trong Python
- PNH, TH, APSC, AKH: Postgres sequence/function qua `supabase.rpc("get_next_*_num")`
- POS: AHD, AHDD, AHDC dùng sequence riêng
- Xóa phiếu cũ không tái sử dụng mã

### `load_stock_deltas()` (DEPRECATED sau Hướng B)
- Trước: tính delta cho `loai_phieu = IN_APP_MARKER`, sau `nhan_hang` → archive bỏ qua
- Sau Hướng B: stub return `{}`, giữ tên để không break import. KHÔNG XÓA file ngay (cosmetic cleanup)

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

### APSC schema mapping (07/05/2026)

`hoa_don` table dùng cột tiếng Việt có dấu (KiotViet schema). Đọc qua subscript:
```python
head["Mã hóa đơn"]    # NOT head.ma_hd
head["Chi nhánh"]
head["Tổng tiền hàng"]
head["Người bán"]
head["Mã YCSC"]
```

`_tao_hoa_don_apsc` insert N rows (1 row/item) → cần dedupe khi xử lý event-driven (LINE Branch 3 đã handle qua `lt id` check).

---

## CHECKLIST BÀN GIAO

Claude session mới nên:

1. ✅ Đọc `CLAUDE.md` trong project knowledge
2. ✅ Đọc 2 file `AI_CONTEXT.md` (POS + Web — bổ trợ lẫn nhau)
3. ✅ Hỏi user gửi file Python liên quan trước khi code
4. ✅ Đề xuất plan kỹ thuật, đợi approve
5. ✅ Code, deliver patch hoặc full files

---

## STYLE GUIDE

- Tiếng Việt, "mình/bạn"
- CLAUDE.md: think-before-code, simplicity, surgical changes
- Trình bày 2-3 lựa chọn khi có choice, recommend 1
- Dùng `ask_user_input_v0` cho options nhanh
- Patches dạng search-replace inline để user apply tay (file > 500 dòng không rewrite full)
- Recommend pattern atomic RPC + verify Supabase queries trước khi sửa
- Edge case BOM, encoding, race condition luôn phải nghĩ tới

---

## OPEN ISSUES — CẦN LÀM Ở SESSION SAU

| # | Item | Status | Priority |
|---|------|--------|----------|
| 1 | Apply bug fix `sua_chua.py` `now_vn` shadowing | PENDING APPLY | High — block tạo APSC mới |
| 2 | Test LINE APSC notification | Đã deploy, chờ APSC mới | Medium |
| 3 | Verify quan_tri cleanup đã apply chưa | Uncertain | Medium |
| 4 | Print K80 tiếng Việt (POS context) | In progress | Low |
| 5 | Web app perf | Pending từ lâu | Medium |

---

## TROUBLESHOOTING REFERENCE

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| Báo cáo load chậm | Cache nested + clear() | Pending — đỡ hơn sau Hướng B |
| HĐ POS không hiện | Cache 5 phút | Bấm "↺ Tải lại" |
| AHDD không vào báo cáo | Cache adapter | Cùng cách trên |
| Multiselect CN crash khi DELETE | Thiếu `chi_nhanh_id` | Đã fix Bước 5 |
| Duplicate widget ID | Key trùng tab | Dùng key unique theo tab |
| Streamlit credentials sai | URL vs secret key swap | Check format `https://[id].supabase.co` cho URL |
| `UnboundLocalError: now_vn` khi tạo APSC | `now_vn = now_vn()` shadowing | Rename `now_dt = now_vn()`. PENDING APPLY |
| Tồn âm UI sau Hướng B | Phiếu Đang chuyển còn dở | Hoàn thành phiếu hoặc xóa atomic |
| `2F005 query has no destination for result data` | RPC paste thiếu RETURN | Paste lại toàn bộ RPC body qua SQL Editor |
| LINE APSC gửi 3 tin/HĐ | Dedupe `lt id` không match | Verify bảng `hoa_don` có cột `id` PK |
| Duyệt kiểm kê không update tồn | RPC chưa apply | Đã fix qua `duyet_phieu_kiem_ke` 07/05 |

---

## CONTACT

User: **Kevin**, chủ DL Watch ở Bà Rịa - Vũng Tàu. Liên hệ qua chat Claude.

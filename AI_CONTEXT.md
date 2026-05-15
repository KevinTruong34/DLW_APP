# AI_CONTEXT.md — DL Watch Store App (Web App quản lý cũ)
**Cập nhật:** 15/05/2026 | **Session tiếp theo bắt đầu từ đây**

---

## PROJECT OVERVIEW

- **Stack:** Streamlit (Python, multi-file) + Supabase (PostgreSQL)
- **Deploy:** Streamlit Cloud
- **3 chi nhánh:** 100 Lê Quý Đôn · Coop Vũng Tàu · GO BÀ RỊA
- **Codebase:** `app.py` + `utils/` (config, db, auth, helpers, **print_queue_apsc**, **scanner_component**, **barcode**, **hide_streamlit_badge**) + `modules/` (10 modules + **admin_pos**)
- **Repo:** `KevinTruong34/DLW_APP`

**Quan hệ với POS app:** chia sẻ database (cùng Supabase project) nhưng repo riêng, deploy riêng. Web app này là **app quản lý cũ (legacy)**, đảm nhận: hàng hóa, sửa chữa, kiểm kê, chuyển hàng, báo cáo, quản trị NV, **+ Admin Override (B1/B2a/B2b) + APSC K80 print/cancel + Barcode Live Scan trong Chuyển hàng**. POS app riêng biệt làm bán hàng tại quầy.

User đã **bỏ KiotViet** — adapter đã xử lý sẵn. Đã hoàn tất:
- Migration **Hướng B (single-source-of-truth)** ngày 06-07/05/2026
- **SPK/DVPS open-price refactor** (08/05/2026)
- **Bộ Admin Override B1 + B2a + B2b** (08-09/05/2026)
- **APSC K80 print + cancel** (10/05/2026)
- **Barcode Live Scan trong Chuyển hàng** (12/05/2026)
- **Hide Streamlit Branding** (12/05/2026)
- **★ Module Chấm công — 8 phases COMPLETE** (14-15/05/2026) — schema/RPC + Cấu hình + Lịch + POS check-in + Bảng công + Sửa công + Tính lương + Export Excel + POS "Lương của tôi" + delete period

**★ Workflow đã proven (lưu memory):** 2-phase cho big features — Phase A planning trong Claude in app (front-load decisions → PLAN.md chi tiết), Phase B execute với Claude Code (pre-flight verify, commit từng phase, smoke tests trước INSERT thật). Pattern này đã thành công 5+ lần liên tiếp (SPK/DVPS, B1, B2a, B2b, APSC K80, Barcode Scan).

---

## CẤU TRÚC FILES

```
app.py                                  # ★ Wire hide_streamlit_branding() ngay sau set_page_config
utils/
  config.py            ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER, APP_INVOICE_PREFIXES
  db.py                supabase client + load_* + log_action + adapter unified
                       ★ Hướng B: bỏ apply delta block trong load_the_kho
                       ★ B1: load_all_nhan_vien, call_rpc, search_hd_pos_for_edit, search_pdt/sc_for_edit
                       ★ B2: load_record_with_history (generic cho 3 loại phiếu)
  auth.py              login/logout, session, get_user, is_admin, is_ke_toan_or_admin
                       ★ B1: require_admin() helper
  helpers.py           now_vn, now_vn_iso, today_vn, fmt_vn, _normalize, _build_phieu_html, _in_phieu_sc
  print_queue_apsc.py  ★ MỚI (10/05/2026): enqueue HĐ APSC vào print_queue cho daemon in K80
  scanner_component.py ★ MỚI (12/05/2026): live_scanner() — shared với POS repo (copy thuần)
  barcode.py           ★ MỚI (12/05/2026): lookup_hang_by_ma_vach — shared với POS repo (copy thuần)
  hide_streamlit_badge.py ★ MỚI (12/05/2026): hide_streamlit_branding() — shared với POS repo (copy thuần)
modules/
  tong_quan.py         Dashboard + greeting (admin only - sales overview restructured)
  hoa_don.py           Tra cứu HĐ KiotViet + AHD POS + AHDD đổi/trả (merge unified)
  hang_hoa.py          Master hàng hóa + tồn kho. ★ Form thêm/sửa hỗ trợ flag is_open_price (radio "Mã giá mở") + cột `ma_vach`
  sua_chua.py          Phiếu sửa chữa. ★ Wire enqueue_apsc trong _tao_hoa_don_apsc + UI 2 nút In/Hủy trong tab_list
  nhap_hang.py         Nhập/Trả hàng NCC
  khach_hang.py        Danh sách + tra cứu khách hàng (tong_ban đã cộng dồn POS)
  kiem_ke.py           Kiểm kê kho. ★ _kk_approve gọi RPC duyet_phieu_kiem_ke
  chuyen_hang.py       ★ patched 12/05: Wire inline barcode scan trong _render_form() (Tạo + Sửa phiếu)
  quan_tri.py          Upload, NV, logs. ★ Đã clean banner archive + bỏ block KẾT SỔ APP
  bao_cao.py           Báo cáo doanh thu (4 cột), XNT, tồn kho. ★ Toggle "Bao gồm HĐ admin"
  admin_pos.py         ★ MỚI (08-09/05/2026): Admin Override panel — 6 sub-tabs (2 outer × 3 sub)
  cham_cong.py         ★ MỚI (14-15/05/2026): Module Chấm công — 2360 lines / 90KB
                       4 tabs: ⚙️ Cấu hình / 📅 Lịch / 📊 Bảng công / 💰 Tính lương
                       + dialogs: Sửa ca, Sửa lịch, Sửa session (audit), Chốt kỳ, Xóa kỳ
                       + 📥 Export Excel 2 sheets
```

---

## DATABASE TABLES CHÍNH

| Table | Mô tả |
|-------|-------|
| `hang_hoa` | Master sản phẩm. `active`, `loai_sp`, `loai_hang`, `thuong_hieu`, `gia_ban`. **★ Cột `is_open_price BOOLEAN`** (08/05) + **`ma_vach TEXT`** (đã có sẵn, data đầy đủ) |
| `the_kho` | **Tồn kho LIVE — SSOT (Hướng B 06-07/05/2026)**. Cột: `Mã hàng`, `Chi nhánh`, `Tồn cuối kì`, `id` |
| `hoa_don` | HĐ KiotViet upload + APSC sửa chữa. Mixed table (15 APSC + 110 HDSC legacy + 11k+ HD/HDD KiotViet legacy). Distinguish bằng `LEFT("Mã hóa đơn", 4)` |
| `phieu_sua_chua` / `_chi_tiet` | Phiếu sửa chữa. **★ Cột mới: `is_admin_created`, `admin_note`, `created_by_id`** |
| `phieu_chuyen_kho` | Chuyển hàng. `loai_phieu` phân biệt App vs KiotViet |
| `phieu_nhap_hang` / `_ct` | Nhập NCC |
| `phieu_tra_hang` / `_ct` | Trả NCC |
| `phieu_kiem_ke` / `_chi_tiet` | Kiểm kê. RPC duyệt apply trực tiếp the_kho |
| `khach_hang` | Unique key `sdt`. `tong_ban` cộng dồn KiotViet + POS + AHDD chenh_lech |
| `nhan_vien` / `nhan_vien_chi_nhanh` | NV + phân CN. **role='admin'** dùng cho admin override |
| `nha_cung_cap` | NCC |
| `action_logs` | Log thao tác. **★ Patterns mới: `ADMIN_HD_*`, `ADMIN_APSC_CANCEL`, `ATT_IN`, `ATT_OUT`, `ATT_SESSION_EDIT`, `ATT_SHIFT_TEMPLATE_*`, `ATT_SCHEDULE_*`, `ATT_BRANCH_NET_UPDATE`, `ATT_RATE_UPDATE`, `ATT_PAYROLL_COMPUTE/FINALIZE/DELETE`, `ATT_PAYROLL_ADJUSTMENT_*`** |
| `sessions` | Session token |
| **`admin_edit_history`** | **★ MỚI (B2a 08/05/2026): bảng audit snapshot before/after JSONB cho mọi edit của admin. ★ 14/05: CHECK whitelist mở rộng `'attendance_sessions'`** |
| **`shift_templates`** | **★ MỚI (14/05/2026 - Chấm công P1): lookup ca làm việc. Seed 8 ca LQD/GO/Coop + KTV** |
| **`attendance_work_schedules`** | **★ MỚI (P1): lịch ca/NV/ngày. EXCLUDE constraint `no_overlap_per_nv` (GIST btree) chống xếp lịch chồng** |
| **`attendance_events`** | **★ MỚI (P1): raw IN/OUT log từ POS, có IP** |
| **`attendance_sessions`** | **★ MỚI (P1): derived per schedule. status open/completed/auto_closed/absent/edited/leave_***  |
| **`attendance_branch_networks` / `attendance_employee_rates`** | **★ MỚI (P1): config IP whitelist per CN + rate per NV (hourly/monthly_fixed)** |
| **`attendance_payroll_periods` / `_items` / `attendance_adjustments`** | **★ MỚI (P1): structure cho tính lương Phase 6, chưa dùng** |
| `print_queue` | Job queue cho daemon K80. **★ Cột mới: `source_app` (default 'pos_app')** — DLW dùng `'dlw_app'` |

### Indexes quan trọng

```sql
hang_hoa_open_price_idx              -- WHERE is_open_price = true
hang_hoa_ma_vach_idx (UNIQUE)        -- ★ MỚI (11/05) WHERE ma_vach IS NOT NULL AND active = true
                                     -- Tạo từ POS Phase 1, DLW thừa hưởng
```

### Tables của POS (web app đọc qua adapter)

- `hoa_don_pos` / `hoa_don_pos_ct` — HĐ POS, prefix `AHD`. **★ Cột mới: `is_admin_created`, `admin_note`**
- `phieu_doi_tra_pos` / `phieu_doi_tra_pos_ct` — Đổi/Trả, prefix `AHDD`. **★ Cột mới: `is_admin_created`, `admin_note`**
- `phieu_dat_hang` — Đặt hàng theo yêu cầu, prefix `AHDC`
- `pin_code` — PIN bcrypt cho NV (POS dùng)

### Sequences

- `ahd_seq`, `ahdd_seq`, `ahdc_seq` — POS
- **★ `sc_seq`** (mới 08/05) — phiếu sửa chữa, race-safe. Wrapper `next_sc_seq()` cho Python.

---

## ★ BARCODE LIVE SCAN trong CHUYỂN HÀNG (12/05/2026)

### Mục đích

Admin/NV ở CN nguồn quét tem mã vạch trên hộp SP để add vào phiếu chuyển — nhanh hơn search text. Apply cả màn Tạo + Sửa phiếu (chung `_render_form()`).

### Architecture

- **Helpers shared với POS:** `utils/scanner_component.py` + `utils/barcode.py` copy thuần từ POS repo
- **UI:** Scan UI inline trong dialog `_dlg_create()` / `_dlg_edit()` — KHÔNG nested dialog (Streamlit không hỗ trợ)
- **Toggle:** `st.toggle("📷 Quét mã vạch")` mở/đóng scan section
- **chi_nhanh cho lookup:** `get_active_branch()` (CN login) — KHÔNG dùng `tu_cn` từ form dropdown (admin tự đổi active branch nếu muốn scan SP CN khác)
- **Block tồn = 0 ngay UI** (warning, KHÔNG cho add) — consistent với decision user

### Wire trong `_render_form()` của chuyen_hang.py

```python
# Section inline trước "🔍 Thêm sản phẩm" hiện tại
scan_open = st.toggle("📷 Quét mã vạch", key="_ck_scan_open")
if scan_open:
    with st.container(key="ck-scan-section"):
        _scan_and_add_to_ck_cart(active_cn)
    st.divider()
```

### Schema adapter

`lookup_hang_by_ma_vach` trả `{ma_hang, ten_hang, loai_sp, is_open_price, gia_ban, ton}`.
DLW chuyen_hang cart cần `{ma_hang, ten_hang, so_luong, gia_ban}` → adapter trong helper:
```python
_add_to_cart_cb(
    mh=item["ma_hang"],
    tn=item["ten_hang"],
    gb=int(item.get("gia_ban") or 0),
)
```

### State naming

- `_ck_scan_open` — toggle scan UI on/off
- `_ck_scan_paused` — pause camera
- `_ck_scan_last_ts` — dedup ts
- Cleanup trong `_clear_cart_state()` cùng các state khác của form

---

## ★ HIDE STREAMLIT BRANDING (12/05/2026)

### Mục đích

Ẩn logo "Hosted with Streamlit" + profile container ở góc dưới phải màn hình.

### Architecture

- Workaround tạm thời, KHÔNG phải official API
- `utils/hide_streamlit_badge.py` shared với POS repo (copy thuần, fix bug phải sync 2 repo)
- JS chạy qua `st.components.v1.html` → manipulate `window.top.document` (KHÔNG `window.parent` — vì `components.html()` tạo iframe nested, parent = iframe app)
- Selectors: `a[href*="streamlit.io/cloud"]`, `[class*="_profileContainer"]`, + fallback patterns
- Defense: setTimeout retry (100ms/500ms/1500ms) + MutationObserver re-hide

### Wire trong app.py

NGAY SAU `st.set_page_config(...)` — trước CSS lớn + trước `run_auth_gate()`:

```python
st.set_page_config(
    page_title="DL Watch Store",
    page_icon="static/favicon.png",
    layout="wide"
)

# === Hide Streamlit Cloud branding ===
from utils.hide_streamlit_badge import hide_streamlit_branding
hide_streamlit_branding()

st.markdown("""<style>...</style>""", unsafe_allow_html=True)
# ... rest of app
```

Vị trí này đảm bảo badge ẩn cả ở màn login (trước auth_gate).

### Note maintenance

Workaround dễ break khi Streamlit Cloud update:
- DOM structure (class name / href badge đổi)
- Iframe sandbox policy block top access
- Tách iframe sang subdomain khác → Same-Origin block

→ Nếu badge xuất hiện lại sau update → inspect DOM lại + cập nhật SELECTORS array.

---

## ★ SPK/DVPS OPEN-PRICE REFACTOR (08/05/2026)

### Migration

170 mã rác → 25 mã chuẩn:
- 2 mã chính: SPK, DVPS
- 23 mã nhóm dịch vụ: LAUDAU, KSA (KINHSAPPHIRE), DANHBONG, KIEMTRAMAY, THAYIC, THAYDAYDONG, THAYRON, THAYTYNUT, THAYMAYDHDUNG, THAYDAYCOTGIO, THAYDAYTHIEU, THAYBANHXE, THAYCANGCUA, KINHTHUONG, THAYMAYPIN, THAYMAYAUTO, NHATRANG, HIEUCHUAN, GANKIMCOC, THAYCHOT, LAMCHONGNUOC, CATMATDAY, OTUDONG, BMD

KHÔNG đụng:
- PIN (TPBG/PV/PDH) — cần track tồn
- MDHTT (Thay máy treo tường) — master data thực

### Helpers chia với POS

**SQL:**
```sql
CREATE FUNCTION is_open_price_sql(p_ma_hang text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT COALESCE((SELECT is_open_price FROM hang_hoa WHERE ma_hang = p_ma_hang), false);
$$;
```

**Python (web `utils/db.py` + POS):**
```python
def is_open_price_item(ma_hang, hang_hoa_dict=None) -> bool: ...
```

### Module patches

- `web_app/modules/sua_chua.py`: detect open-price khi add item, render input giá
- `web_app/modules/bao_cao.py`: filter logic
- `web_app/modules/hang_hoa.py`: form thêm/sửa hỗ trợ radio "Mã giá mở" (is_open_price)

---

## ★ HƯỚNG B — SINGLE SOURCE OF TRUTH (Migration 06-07/05/2026)

### Quyết định kiến trúc

App = **single source of truth** cho tồn kho. `the_kho.Tồn cuối kì` là **live data**, không còn delta layer.

### Implementation

**`utils/db.py` (web app):**
- `load_the_kho`: bỏ block apply delta hoàn toàn
- `load_stock_deltas()`: deprecated → trả về `{}` stub (giữ tên để không break import)

**RPC patches:**
- `xac_nhan_chuyen_hang`: step 5 thêm `loai_phieu = ARCHIVED_MARKER`
- `duyet_phieu_kiem_ke(p_ma_phieu, p_nguoi_duyet)` mới — apply atomic

**Module patches:**
- `kiem_ke.py` `_kk_approve`: gọi RPC `duyet_phieu_kiem_ke`
- `quan_tri.py`: xóa banner + xóa block "KẾT SỔ PHIẾU APP"

### Workflow sau Hướng B

| Action | RPC ghi `the_kho` |
|--------|-------------------|
| Bán hàng POS | `tao_hoa_don_pos` (skip open-price) |
| Hủy HĐ POS | `huy_hoa_don_pos` (skip open-price) |
| Đổi/trả POS | `tao_phieu_doi_tra_pos` (skip open-price) |
| Hủy đổi/trả | `huy_phieu_doi_tra_pos` (skip open-price) |
| Tạo HĐ APSC | `_tao_hoa_don_apsc` Python + `tru_kho_apsc` RPC (skip open-price) |
| **Hủy HĐ APSC** | **`huy_hoa_don_apsc` (★ MỚI 10/05) — đảo kho atomic, skip open-price** |
| Chuyển hàng — xác nhận | `xac_nhan_chuyen_hang` |
| Chuyển hàng — nhận | `nhan_hang` |
| Duyệt kiểm kê | `duyet_phieu_kiem_ke` |
| **Tạo HĐ admin** | **`tao_hoa_don_pos_admin`, `tao_phieu_doi_tra_pos_admin` (skip open-price)** |
| **Sửa HĐ admin** | **`sua_hoa_don_pos_admin`, `sua_phieu_doi_tra_pos_admin` (atomic đảo kho cho items_moi)** |

---

## ★ ADMIN OVERRIDE — BỘ B1 + B2a + B2b (08-09/05/2026)

### Mục đích

Admin (Đăng Khoa, role='admin') có quyền tạo HĐ tự do (backdate, custom giá, override stock) + sửa HĐ existing với full audit.

### Phase B1 — Tạo HĐ admin tự do (DEPLOYED + TESTED PASS)

**Schema:** thêm `is_admin_created BOOLEAN`, `admin_note TEXT` cho 3 bảng + `created_by_id BIGINT` cho `phieu_sua_chua`.

**Helper RPC:** `_admin_validate_request(p_admin_id, p_created_at)` — check role='admin', active, backdate ≤90 ngày, không future >5 phút.

**3 RPC chính:**
- `tao_hoa_don_pos_admin(payload jsonb)` — tạo HĐ POS với mọi field tùy ý, audit `ADMIN_HD_CREATE`
- `tao_phieu_doi_tra_pos_admin(payload jsonb)` — tạo phiếu đổi/trả, bypass 7-day age check, chi_nhanh lock theo HĐ gốc, validate SL trả ≤ đã bán − đã trả
- `tao_phieu_sua_chua_admin(payload jsonb)` — tạo phiếu sửa chữa với items, KHÔNG đụng kho (stage 1)

**UI:** Module mới `modules/admin_pos.py` với 3 sub-tabs đầu (sau B2 mở rộng thành 6 sub):
- 🛒 Tạo HĐ POS
- 🔄 Tạo phiếu đổi/trả
- 🛠 Tạo phiếu sửa chữa

Pattern: Backdate (max 90 ngày), dropdown NV cả `active=false`, dropdown 3 chi nhánh, custom đơn giá mọi item, optional giảm giá đơn, confirm "XÁC NHẬN".

**Báo cáo toggle:** Thêm checkbox "Bao gồm HĐ admin" (default ON, chỉ admin thấy) trong 3 sub-tab Doanh thu (Cuối ngày, Tổng quan, Bán hàng). KHÔNG apply cho XNT/Tồn kho/Nhân viên (kho thật, NV thật).

### Phase B2a — Sửa HĐ POS (DEPLOYED + TESTED PASS)

**Schema bảng riêng** `admin_edit_history`:
```sql
CREATE TABLE admin_edit_history (
    id BIGSERIAL PRIMARY KEY,
    table_name TEXT CHECK IN ('hoa_don_pos', 'phieu_doi_tra_pos', 'phieu_sua_chua'),
    record_id TEXT NOT NULL,
    snapshot_before JSONB NOT NULL,
    snapshot_after JSONB NOT NULL,
    fields_changed TEXT[] NOT NULL,
    edited_by_id BIGINT REFERENCES nhan_vien(id),
    edited_by_name TEXT,
    edit_reason TEXT,
    edited_at TIMESTAMPTZ DEFAULT now()
);
-- 3 indexes: (table_name, record_id), (edited_at DESC), (edited_by_id)
```

**3 RPC:**
- `_admin_check_can_edit_hd_pos(p_ma_hd)` — check trang_thai='Hoàn thành' + `has_active_pdt`
- `sua_hoa_don_pos_admin(payload)` — atomic, snapshot before/after, refactor stock check sang JSON return (không RAISE EXCEPTION)
- `load_hd_pos_with_history(p_ma_hd)` — UI helper, sau B2b refactor thành generic

**LOCK fields:** `ma_hd`, `trang_thai`, `nguoi_tao`, `created_at`, `chi_nhanh`

**Editable:** `nguoi_ban_id`, `ten_khach`, `sdt_khach`, `ghi_chu`, items (so_luong, don_gia, thêm/xóa), `giam_gia_don`, PTTT (tien_mat, chuyen_khoan, the)

**Edge case:** HĐ có ref bởi `phieu_doi_tra_pos` active → BLOCK items (sửa header thoải mái).

**UI:** Tab "✏️ Sửa HĐ POS" với 2-step flow (Search → Edit form). `_detect_changes` helper, history viewer expander. Edit reason BẮT BUỘC ở UI.

### Phase B2b — Sửa đổi/trả + sửa chữa (DEPLOYED + TESTED PASS)

**Refactor:** `load_hd_pos_with_history` → `load_record_with_history(p_table_name, p_record_id)` generic cho cả 3 loại phiếu. Drop B2a function. Python wrapper backward-compat.

**4 RPC mới:**
- `_admin_check_can_edit_sc(p_ma_phieu)` — check Đã hủy + has_apsc (qua `SC_HOA_DON` log)
- `sua_phieu_sua_chua_admin(payload)` — sửa SC, **NO stock logic** (stage 1 không đụng kho), BLOCK items khi đã convert APSC
- `_admin_check_can_edit_pdt(p_ma_pdt)` — check trang_thai='Hoàn thành'
- `sua_phieu_doi_tra_pos_admin(payload)` — sửa PDT, **BLOCK items_tra hoàn toàn** (workaround: hủy + tạo lại), items_moi đảo kho atomic, recompute chenh_lech + re-validate PTTT

**LOCK fields:**
- PDT: `ma_pdt, trang_thai, nguoi_tao, created_at, chi_nhanh, ma_hd_goc`
- SC: `ma_phieu, created_at, chi_nhanh, created_by_id` (KHÔNG LOCK trang_thai cho SC — admin có thể chuyển trạng thái)

**Restriction:**
- PDT: Chỉ sửa `Hoàn thành`
- SC: Sửa được mọi trạng thái trừ `Đã hủy`

**UI reorganize 4 flat tabs → 2 outer × 3 sub:**
```
🆕 Tạo                                    ✏️ Sửa
├─ 🛒 HĐ POS         (B1)                ├─ 🛒 HĐ POS         (B2a)
├─ 🔄 Đổi/trả        (B1)                ├─ 🔄 Đổi/trả        (B2b)
└─ 🛠 Sửa chữa       (B1)                └─ 🛠 Sửa chữa       (B2b)
```

---

## ★ APSC K80 + CANCEL (10/05/2026)

### Mục đích

3 gaps đã giải quyết:
1. HĐ APSC tạo trên DLW không in K80 → wire `enqueue_apsc()` vào `_tao_hoa_don_apsc()`
2. Không có RPC hủy HĐ APSC → build `huy_hoa_don_apsc`
3. Không có nút "In lại" + "Hủy" cho HĐ APSC → UI 2 nút trên DLW (Option A')

### File mới `web_app/utils/print_queue_apsc.py`

```python
# Constants (copy từ POS pattern)
LINE_WIDTH = 42
PRINT_ENABLED_BRANCHES = {"100 Lê Quý Đôn"}

# Layout helpers (_center, _two_cols, _wrap, _fmt_dt_vn, _header)

# Loader: _load_apsc_by_ma(ma_hd) — query hoa_don group N rows → 1 dict
# Builder: _build_text_apsc(apsc) — template "HÓA ĐƠN SỬA CHỮA" với Mã YCSC + items có Bảo hành
#   - Badge "*** HÓA ĐƠN ĐÃ HỦY ***" nếu in lại HĐ đã hủy
# Insert: _insert_print_job(...) với source_app='dlw_app'

# Public API:
enqueue_apsc(ma_hd, created_by) -> dict       # Insert print_queue
call_huy_hoa_don_apsc(ma_hd, cancelled_by)    # RPC wrapper
```

### RPC `huy_hoa_don_apsc`

```sql
CREATE FUNCTION huy_hoa_don_apsc(p_ma_hd text, p_cancelled_by text) RETURNS jsonb
```

Logic:
1. Validate prefix 'APSC' (skip HDSC legacy KiotViet)
2. Check không phải đã hủy
3. Đảo kho atomic — symmetric với `tru_kho_apsc` (skip nếu KHÔNG có trong hang_hoa OR KHÔNG `is_hang_hoa_co_kho`)
4. Set `"Trạng thái" = 'Đã hủy'` cho TẤT CẢ rows của HĐ
5. Audit `ADMIN_APSC_CANCEL` level='warn'

**Deviation vs plan ban đầu (đã approve):**
- Skip rule: dùng `is_hang_hoa_co_kho` thay `is_open_price_sql` để symmetric với `tru_kho_apsc` (tránh phantom stock)
- Bỏ INSERT fallback khi UPDATE 0 rows: consistent với `tru_kho_apsc`

### Wire enqueue trong `_tao_hoa_don_apsc()`

Pattern (a) — sau INSERT, trước `tru_kho_apsc`:
```python
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

# (existing) try/except gọi tru_kho_apsc
```

Lý do (a): in queue ngay cả khi `tru_kho_apsc` fail → khách vẫn có biên lai.

### UI Option A' — Trong tab_list của sua_chua.py

User chọn phiếu sc trong dropdown `picked_list`. Nếu phiếu là "Hoàn thành":
- Reverse-query `hoa_don WHERE "Mã YCSC" = ma_phieu LIMIT 1`
- Render section thêm dưới `ct` dataframe:
  ```
  🧾 Hóa đơn APSC: APSC000045
  Tổng: 250.000đ  ·  Trạng thái: Hoàn thành
  [🖨 In lại]    [❌ Hủy HĐ] (admin only)
  ```
- Nếu HĐ đã hủy: badge "❌ ĐÃ HỦY", giữ nút "In lại" (in giấy có "*** ĐÃ HỦY ***"), ẩn nút "Hủy"

### Confirm hủy dialog

Type "HỦY" → verify → call `huy_hoa_don_apsc` → toast success/error.

---

## KEY CONSTANTS (utils/config.py)

```python
IN_APP_MARKER   = "Chuyển hàng (App)"
ARCHIVED_MARKER = "Chuyển hàng (App - đã đồng bộ)"

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
_is_ahdd_hd(ma)       # AHDD riêng
_is_app_hd(ma)        # APSC + AHD
_is_kiotviet_hd(ma)   # Còn lại
```

---

## IMPORT CHUẨN

```python
from utils.helpers import _normalize, now_vn, now_vn_iso, today_vn, fmt_vn
from datetime import datetime, timedelta
from utils.auth import is_admin, require_admin, get_user
from utils.db import call_rpc, load_all_nhan_vien, load_record_with_history
```

---

## COMPLETED — TẤT CẢ VIỆC ĐÃ LÀM

### Bước 6 — Adapter POS (session trước)

`load_hoa_don_unified` merge 3 nguồn (KiotViet + POS + AHDD). `_load_hoa_don_pos_flat` JOIN `phieu_dat_hang` qua `ma_pdh` để fetch cọc PTTT.

### Bước 7B — Adapter AHDD đổi/trả

(1) Doanh thu cộng `chenh_lech` AHDD; (2) Bán hàng theo nhóm tính net items; (3) `khach_hang.tong_ban` cộng dồn `chenh_lech`; (4) Tab tra cứu HĐ web app merge AHDD với badge "Đổi/Trả".

### Bước 8 reflect web app

`_load_hoa_don_pos_flat` JOIN `phieu_dat_hang` để fetch cọc PTTT chi tiết. Tab tra cứu HĐ có badge "Từ phiếu đặt".

### Tong_quan restructure

Sales overview chuyển vào admin section (password-protected).

### modules/sua_chua.py — UI Redesign + APSC K80

**CSS scoped** trong `_SC_CSS`: classes `sc-card`, `sc-badge`, etc.

**4 tabs:** Danh sách / Tạo mới / Chi tiết & Cập nhật / Tạo HĐ sửa.

**`_tao_hoa_don_apsc`:** insert N rows vào `hoa_don` + `tru_kho_apsc` RPC. **★ Wire enqueue_apsc + UI 2 nút trong tab_list (10/05).**

✅ **Bug `now_vn` shadowing đã fix:** `now_dt = now_vn()` thay vì `now_vn = now_vn()`.

### modules/hang_hoa.py — Admin features

- Form thêm hàng: `loai_sp` radio mặc định "Hàng hóa"
- **★ Radio "Mã giá mở" (is_open_price)** (08/05) — set khi tạo SPK/DVPS-like service
- Soft-delete (`active = False`)
- Sửa thông tin
- Chỉnh tồn kho trực tiếp `_render_ton_kho`
- Form đã có sẵn input `ma_vach` (data đầy đủ cho mọi SP active)

⚠ **Bug noted (không tác hại sau Hướng B):** Form chỉnh tồn write raw vào `the_kho`. Để đó, fix khi đụng tới module.

### modules/bao_cao.py

- Tab **Tồn kho:** filter, pivot, metrics
- Tab **Nhân viên** (admin only)
- **★ Toggle "Bao gồm HĐ admin"** (08/05) — apply 3 sub-tab Doanh thu, default ON

### modules/chuyen_hang.py — RPC + UX fixes + ★ Barcode Scan (12/05)

- RPC `xac_nhan_chuyen_hang`: lock FOR UPDATE, atomic, archive marker
- RPC `nhan_hang`: cộng kho đích
- Fix checkbox `disabled=not confirmed`, fix tab văng về Danh sách
- **★ Inline barcode scan trong `_render_form()` (Tạo + Sửa phiếu)** — toggle `📷 Quét mã vạch`, lookup `get_active_branch()`, block tồn=0

### modules/kiem_ke.py — RPC atomic

`_kk_approve` gọi RPC `duyet_phieu_kiem_ke(p_ma_phieu, p_nguoi_duyet)` apply atomic vào `the_kho`.

### modules/quan_tri.py — Cleanup post Hướng B

- Xóa banner `get_archive_reminder()` 
- Xóa block "KẾT SỔ PHIẾU APP"
- Tab s2 (Upload Thẻ kho) = "force update tồn kho đồng loạt" (admin tool)

### ★ modules/admin_pos.py — MỚI (B1+B2a+B2b)

```python
def module_admin_pos():
    require_admin()
    
    outer_tab1, outer_tab2 = st.tabs(["🆕 Tạo", "✏️ Sửa"])
    
    with outer_tab1:
        sub1, sub2, sub3 = st.tabs(["🛒 HĐ POS", "🔄 Đổi/trả", "🛠 Sửa chữa"])
        # B1: render_tao_hd_pos / render_tao_doi_tra / render_tao_sua_chua
    
    with outer_tab2:
        sub1, sub2, sub3 = st.tabs(["🛒 HĐ POS", "🔄 Đổi/trả", "🛠 Sửa chữa"])
        # B2a + B2b: render_sua_hd_pos / render_sua_doi_tra / render_sua_sua_chua
```

Tab "🛡 Quản trị" trong sidebar (chỉ admin thấy). Pattern type "XÁC NHẬN" cho tạo, edit_reason BẮT BUỘC cho sửa.

### app.py — ★ Wire hide_streamlit_branding() (12/05)

Ngay sau `st.set_page_config(...)`, trước CSS lớn và `run_auth_gate()`. Badge ẩn cả ở màn login.

### LINE Notification (full picture)

3 nhánh: Branch 1 (đổi/trả), Branch 2 (HĐ POS với phân loại), Branch 3 (APSC qua dedupe `lt id`).

### ★ MODULE CHẤM CÔNG — 8 phases COMPLETE (14-15/05/2026)

**Mục đích:** Hệ thống chấm công nhân viên end-to-end xuyên 2 app (DLW + POS). NV chấm IN/OUT từ POS (IP whitelist + active branch), admin/kế toán quản lý lịch + tính lương + export Excel từ DLW.

**Tổng kết files (DLW):**
- `modules/cham_cong.py` (2360 lines / 90KB) — entry + 4 tabs + 5+ dialogs
- `utils/db.py` — 5 helpers (`load_shift_templates`, `load_branch_networks`, `load_employee_rates`, `count_schedules_using_template`, `load_schedules_for_week`)
- `app.py` — wire menu "👥 Nhân viên" cho admin + kế toán
- `sql/cham_cong_*.sql` — 8 migration files audit source

**Tổng kết files (POS):**
- `modules/cham_cong_dialog.py` (Phase 3) — @st.dialog "⏱️ Chấm công" + IP detection 2-tier + 2 RPC wrappers inline
- `modules/cham_cong_my_payroll.py` (Phase 8) — @st.dialog "📋 Lương của tôi" + 2 sub-tabs (Bảng công / Tổng kết)
- `utils/client_ip_component.py` (Phase 3 hotfix IP) — JS fetch `api.ipify.org` qua `st.components.v2.component` (giống `scanner_component.py`)
- `app.py` — avatar popover 2 buttons "⏱️ Chấm công" + "📋 Lương của tôi" với flag pattern

**Schema (9 bảng `attendance_*` + `shift_templates`):**
- `shift_templates` (seed 8 ca)
- `attendance_branch_networks` (seed 3 CN, `ip_prefixes TEXT[]`)
- `attendance_employee_rates` (enum `hourly`/`monthly_fixed`)
- `attendance_work_schedules` + EXCLUDE GIST `no_overlap_per_nv`
- `attendance_events` (raw IN/OUT từ POS)
- `attendance_sessions` (derived per schedule, status: open/completed/auto_closed/absent/edited/leave_paid/leave_unpaid)
- `attendance_payroll_periods` + `attendance_payroll_items` + `attendance_adjustments`
- `admin_edit_history` CHECK whitelist mở rộng `'attendance_sessions'`

**RPCs (deploy qua Supabase MCP `apply_migration`):**

| RPC | Phase | Purpose |
|---|---|---|
| `validate_check_in_pos(nv_id, ip, active_chi_nhanh)` | P1 + hotfix #2 | Validate before NV chấm: NV active + lịch trong khung ±2h + active_chi_nhanh khớp + IP whitelist |
| `record_attendance_event(nv_id, event_type, ip, note, active_chi_nhanh)` | P1 + hotfix #2 | Insert event với defense-in-depth re-validate |
| `build_session_for_schedule(schedule_id)` | P1 + hotfix #5 | Build session từ events; **preserve `status='edited'`** (admin sửa không bị overwrite) |
| `build_sessions_for_date(work_date, chi_nhanh)` | P1 | Bulk loop build per ngày |
| `update_session_admin(session_id, in_at, out_at, note, reason, admin_id)` | P1 | Sửa session với snapshot vào `admin_edit_history`, status→'edited' |
| `compute_payroll_period(period_id)` | P6 | Idempotent: DELETE + INSERT items, snapshot rate vào `rate_snapshot`. Skip `absent/leave_unpaid/open/pending` |
| `finalize_payroll_period(period_id, admin_id)` | P6 | Lock period: status→'finalized' + audit warn |
| `get_payroll_for_self(nv_id, period_id)` | P8 | NV xem lương cá nhân — POS dialog. Return {period, items, adjustments, totals} |
| `delete_payroll_period(period_id, admin_id)` | Addon | Admin xóa kỳ (kể cả đã chốt) — cascade items + adj + period + audit warn |

**UI structure DLW (`modules/cham_cong.py`):**

```
👥 Nhân viên
├── ⚙️ Cấu hình (admin only)
│   ├── 🌐 Mạng cửa hàng (IP whitelist per CN)
│   ├── 💵 Lương nhân viên (rate per NV, hourly/monthly_fixed)
│   └── ⏰ Ca làm việc (CRUD shift_templates với lock fields khi có schedule ref — D17)
├── 📅 Lịch làm việc (calendar 7 cột T2→CN)
│   ├── Click ➕ trống → dialog Thêm lịch
│   ├── Click chip → dialog Sửa lịch
│   └── Copy tuần trước button
├── 📊 Bảng công (admin + kế toán, role filter)
│   ├── Filter: date range / CN / NV multi-select
│   ├── 🔄 Cập nhật sessions (call build per day)
│   ├── Table 10 cols với emoji status
│   ├── ✏️ Sửa công (admin only) → dialog edit session + lịch sử
│   └── Summary per NV + overall metrics
└── 💰 Tính lương
    ├── 📅 Kỳ lương (admin CRUD)
    │   ├── ➕ Tạo kỳ
    │   ├── 💵 Tính lương button
    │   ├── 🔒 Chốt kỳ dialog
    │   └── 🗑 Xóa kỳ dialog (kể cả đã chốt)
    ├── 💰 Bảng lương (admin + ke_toan)
    │   ├── Table breakdown per NV
    │   └── 📥 Export Excel button (admin only, 2 sheets)
    └── 🎁 Phụ cấp / Thưởng (admin CRUD)
```

**UI POS (`modules/cham_cong_dialog.py` + `cham_cong_my_payroll.py`):**

```
Avatar popover
├── ⏱️ Chấm công → dialog validate IP + render info → confirm IN/OUT
└── 📋 Lương của tôi → dialog dropdown period → 2 tabs (Bảng công / Tổng kết)
```

**Role access matrix:**

| Action | admin | ke_toan | nhan_vien |
|---|---|---|---|
| Cấu hình (Mạng/Lương/Ca) | ✓ | — (xem info) | ✗ menu |
| Lịch CRUD | ✓ | xem | ✗ menu |
| Bảng công xem | all NV | ex-admin | chỉ mình |
| Sửa công | ✓ | ✗ | ✗ |
| Tính lương + Chốt + Xóa kỳ | ✓ | ✗ | ✗ |
| Bảng lương xem | all | ex-admin | ✗ menu |
| Adjustments CRUD | ✓ | xem | ✗ menu |
| Export Excel | ✓ | ✗ | ✗ |
| POS Chấm công | ✓ | ✓ | ✓ |
| POS "Lương của tôi" | ✓ | ✓ | ✓ |

**Phase summary:**

| Phase | Deliverable | PRs |
|---|---|---|
| **Phase 1** | 9 bảng + 5 RPC primitives + admin_edit_history whitelist | DLW #61 |
| **Phase 2** | DLW Config + Schedule UI + 5 helpers utils/db.py | DLW #61 + hotfix FK #62 |
| **Phase 3** | POS Dialog chấm công + IP detection | POS #58 + hotfix IP ipify #59 + hotfix active_branch (DLW #63 + POS #60) |
| **Phase 4** | DLW Bảng công + 3-query sequence pattern | DLW #64 |
| **Phase 5** | DLW Sửa công + audit history | DLW #65 + hotfix preserve edited #66 |
| **Phase 6** | DLW Tính lương 3 sub-tabs + 2 RPC (compute, finalize) | DLW #67 |
| **Phase 7** | DLW Export Excel 2 sheets (openpyxl) | DLW #68 |
| **Phase 8** | POS "Lương của tôi" + RPC get_payroll_for_self | DLW #69 + POS #61 |
| **Addon** | Admin xóa kỳ lương (kể cả đã chốt) — RPC delete_payroll_period + UI dialog | DLW #70 |

**4 Hotfixes critical bugs caught trong development:**
1. **FK disambiguation** (Phase 2 → fix): `attendance_work_schedules` có 2 FK đến `nhan_vien` (`nhan_vien_id` + `created_by`) → PostgREST nested embedding fail → hint FK: `nhan_vien!attendance_work_schedules_nhan_vien_id_fkey(...)`
2. **IP detection** (Phase 3 → fix): `st.context.ip_address` + `X-Forwarded-For` trả IP proxy Cloudflare/Streamlit thay đổi mỗi rerun → switch sang JS fetch `api.ipify.org` qua `st.components.v2.component` (pattern giống `scanner_component.py`) → IP NAT egress thật khớp `whatismyip.com`
3. **active_chi_nhanh enforce** (Phase 3 → fix): RPC `validate_check_in_pos` + `record_attendance_event` thêm param `p_active_chi_nhanh DEFAULT NULL` → reject nếu NV đang chọn CN khác CN của ca → tránh HĐ POS ghi sai CN
4. **Preserve admin-edited** (Phase 5 → fix): `build_session_for_schedule` early return nếu existing session status='edited' → admin sửa giờ không bị overwrite khi user bấm "Cập nhật sessions"

**Decisions (D30-D34):** xem KEY DECISIONS section.

---

## SQL ĐÃ CHẠY TRÊN SUPABASE

```sql
-- Đã chạy trước
ALTER TABLE hang_hoa ADD COLUMN active boolean DEFAULT true;
-- RPC: xac_nhan_chuyen_hang, nhan_hang, duyet_phieu_kiem_ke

-- ★ 08/05/2026: SPK/DVPS open-price refactor
ALTER TABLE hang_hoa ADD COLUMN is_open_price BOOLEAN DEFAULT false;
CREATE INDEX hang_hoa_open_price_idx ON hang_hoa(ma_hang) WHERE is_open_price = true;
CREATE FUNCTION is_open_price_sql(text) RETURNS boolean ...
-- Migration data: 25 mã chuẩn set is_open_price=true, xóa 170 mã rác
-- POS RPC patches: tao_hoa_don_pos, huy_hoa_don_pos, tao_phieu_doi_tra_pos, huy_phieu_doi_tra_pos

-- ★ 08/05/2026: Admin Override B1
ALTER TABLE hoa_don_pos ADD COLUMN is_admin_created BOOLEAN DEFAULT false, ADD COLUMN admin_note TEXT;
ALTER TABLE phieu_doi_tra_pos ADD COLUMN is_admin_created BOOLEAN DEFAULT false, ADD COLUMN admin_note TEXT;
ALTER TABLE phieu_sua_chua ADD COLUMN is_admin_created BOOLEAN DEFAULT false, ADD COLUMN admin_note TEXT, ADD COLUMN created_by_id BIGINT;
CREATE SEQUENCE sc_seq START WITH (max+1);
CREATE FUNCTION next_sc_seq() RETURNS bigint;  -- wrapper Python
CREATE FUNCTION _admin_validate_request(bigint, timestamptz) RETURNS jsonb;
CREATE FUNCTION tao_hoa_don_pos_admin(jsonb) RETURNS jsonb;
CREATE FUNCTION tao_phieu_doi_tra_pos_admin(jsonb) RETURNS jsonb;
CREATE FUNCTION tao_phieu_sua_chua_admin(jsonb) RETURNS jsonb;

-- ★ 08-09/05/2026: Admin Override B2a
CREATE TABLE admin_edit_history (...);
CREATE FUNCTION _admin_check_can_edit_hd_pos(text) RETURNS jsonb;
CREATE FUNCTION sua_hoa_don_pos_admin(jsonb) RETURNS jsonb;
-- (B2a load_hd_pos_with_history dropped trong B2b)

-- ★ 09/05/2026: Admin Override B2b
DROP FUNCTION load_hd_pos_with_history(text);
CREATE FUNCTION load_record_with_history(text, text) RETURNS jsonb;  -- generic
CREATE FUNCTION _admin_check_can_edit_sc(text) RETURNS jsonb;
CREATE FUNCTION sua_phieu_sua_chua_admin(jsonb) RETURNS jsonb;
CREATE FUNCTION _admin_check_can_edit_pdt(text) RETURNS jsonb;
CREATE FUNCTION sua_phieu_doi_tra_pos_admin(jsonb) RETURNS jsonb;

-- ★ 10/05/2026: APSC K80 + Cancel
CREATE FUNCTION huy_hoa_don_apsc(text, text) RETURNS jsonb;
-- (Schema print_queue.source_app đã có sẵn từ trước)

-- ★ 11/05/2026: Barcode Live Scan
DROP INDEX IF EXISTS idx_hang_hoa_ma_vach;  -- btree thường cũ
CREATE UNIQUE INDEX hang_hoa_ma_vach_idx ON hang_hoa(ma_vach)
    WHERE ma_vach IS NOT NULL AND active = true;
-- (Cột hang_hoa.ma_vach đã tồn tại từ trước, data đầy đủ)

-- ★ 14/05/2026: Module Chấm công — Phase 1 (schema + 5 RPC)
-- Migrations: cham_cong_p0_drop_legacy (cleanup 7 bảng partial), cham_cong_p1_schema,
--             cham_cong_p1_admin_edit_history_whitelist, cham_cong_p1_rpcs
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE TABLE shift_templates (...);                  -- seed 8 ca
CREATE TABLE attendance_branch_networks (...);       -- seed 3 CN, ip_prefixes='{}'
CREATE TABLE attendance_employee_rates (...);
CREATE TABLE attendance_work_schedules (...);        -- + EXCLUDE no_overlap_per_nv (GIST)
CREATE TABLE attendance_events (...);
CREATE TABLE attendance_sessions (...);              -- UNIQUE schedule_id
CREATE TABLE attendance_payroll_periods (...);
CREATE TABLE attendance_payroll_items (...);
CREATE TABLE attendance_adjustments (...);
ALTER TABLE admin_edit_history DROP CONSTRAINT admin_edit_history_table_name_check;
ALTER TABLE admin_edit_history ADD CONSTRAINT ... CHECK (... + 'attendance_sessions');
CREATE FUNCTION validate_check_in_pos(int, text) RETURNS jsonb;
CREATE FUNCTION record_attendance_event(int, text, text, text) RETURNS jsonb;
CREATE FUNCTION build_session_for_schedule(bigint) RETURNS jsonb;
CREATE FUNCTION build_sessions_for_date(date, text) RETURNS jsonb;
CREATE FUNCTION update_session_admin(bigint, timestamptz, timestamptz, text, text, int) RETURNS jsonb;

-- ★ 14/05/2026: Module Chấm công — Phase 3 hotfix (enforce active_chi_nhanh)
-- Migration: cham_cong_p3_hotfix_active_branch (+ drop_old_signatures)
DROP FUNCTION IF EXISTS validate_check_in_pos(INTEGER, TEXT);
DROP FUNCTION IF EXISTS record_attendance_event(INTEGER, TEXT, TEXT, TEXT);
CREATE FUNCTION validate_check_in_pos(INTEGER, TEXT, TEXT DEFAULT NULL) RETURNS jsonb;
CREATE FUNCTION record_attendance_event(INTEGER, TEXT, TEXT, TEXT, TEXT DEFAULT NULL) RETURNS jsonb;
-- Reject khi schedule.branch_name <> p_active_chi_nhanh

-- ★ 15/05/2026: Module Chấm công — Phase 5 hotfix (preserve admin-edited)
-- Migration: cham_cong_p5_hotfix_preserve_edited
CREATE OR REPLACE FUNCTION build_session_for_schedule(bigint) RETURNS jsonb;
-- Early return if existing session.status='edited' → tránh overwrite admin sửa

-- ★ 15/05/2026: Module Chấm công — Phase 6 (Tính lương RPCs)
-- Migration: cham_cong_p6_payroll_rpcs
CREATE FUNCTION compute_payroll_period(bigint) RETURNS jsonb;
-- Idempotent: DELETE items + build sessions + loop NV với rate, snapshot rate_snapshot
-- Audit ATT_PAYROLL_COMPUTE
CREATE FUNCTION finalize_payroll_period(bigint) RETURNS jsonb;
-- Set status='finalized', finalized_by + finalized_at. Audit ATT_PAYROLL_FINALIZE.

-- ★ 15/05/2026: Module Chấm công — Phase 8 (NV self-view)
-- Migration: cham_cong_p8_get_payroll_for_self
CREATE FUNCTION get_payroll_for_self(bigint, int) RETURNS jsonb;
-- Trả {period, items, adjustments, totals} cho NV xem lương của chính mình

-- ★ 15/05/2026: Module Chấm công — Addon (admin xóa kỳ lương)
-- Migration: cham_cong_delete_payroll_period
CREATE FUNCTION delete_payroll_period(bigint, int) RETURNS jsonb;
-- Admin-only (role check). Cascade DELETE items + adjustments + period kể cả finalized.
-- Audit ATT_PAYROLL_DELETE level='warn' với snapshot đầy đủ.
```

POS-related SQL: `pos_setup.sql`, `pos_patch_01..09.sql` (patch_09 = barcode UNIQUE).

Edge Function: `supabase/functions/line-notify/index.ts` — 3 nhánh.

---

## PERFORMANCE — PHÂN TÍCH (chưa fix, vẫn pending)

### Vấn đề
Load module 3–10s, spinner xuất hiện khi chuyển module (đặc biệt Báo cáo).

### Nguyên nhân (sau Hướng B đã giảm bớt)

**1. Nested cached calls:** `load_the_kho()` chỉ còn gọi `load_hang_hoa()` cho join thông tin SP (đã giảm so với trước).

**2. `st.cache_data.clear()` toàn bộ** — 26 chỗ. Mỗi thao tác xóa toàn bộ cache.

**3. Adapter unified gọi 3 nguồn** (KiotViet + POS + AHDD) trong 1 lần load — chưa parallel.

### Hướng fix (chưa implement)
1. Thêm `show_spinner=False` cho `load_hang_hoa()` 
2. Targeted cache invalidation thay vì `clear()` toàn bộ
3. Trước fix: thêm timing log để đo bottleneck thực tế

---

## KEY DECISIONS

| # | Quyết định |
|---|------------|
| D1 | RPC Hybrid: Python xử lý UI/validation, Supabase RPC cho "chốt chặn cuối" |
| D2 | `phieu_tra_hang` = Trả NCC. Đổi trả khách dùng bảng riêng `phieu_doi_tra_pos` |
| D3 | RPC archive logic: `xac_nhan` + `nhan_hang` đều set ARCHIVED_MARKER cho consistency |
| D5 | Timezone: `timestamptz` + `ZoneInfo` |
| D6 | `loai_sp` = "Hàng hóa" mặc định khi thêm hàng |
| D7 | Bước 6 adapter: tách prefix APSC / AHD / KiotViet |
| D8 | Bước 7B: tách AHDD riêng khỏi AHD |
| D9 | Bước 7B: `khach_hang.tong_ban` = sum KiotViet + POS + AHDD chenh_lech |
| D10 | AHDD `chenh_lech` âm trừ doanh thu |
| D12 | ★ Hướng B: `the_kho` = SSOT |
| D15 | ★ POS lich_su: 3 nguồn (HĐ POS + đổi/trả + APSC) read-only |
| D16 | ★ LINE Branch 3 APSC: dedupe `lt id` race-free |
| D17 | ★ SPK/DVPS: flag `is_open_price` thay convention OR-list |
| D18 | ★ Admin permission: `nhan_vien.role='admin'` server-side check, không tạo permission table |
| D19 | ★ Admin audit: bảng riêng `admin_edit_history` JSONB snapshot, không JSONB column trong 3 bảng chính |
| D20 | ★ B2 LOCK: `created_at` + `chi_nhanh` + `ma_hd_goc` (PDT) — đơn giản, tránh cross-branch stock movement |
| D21 | ★ B2 BLOCK items_tra: hủy + tạo lại đơn giản hơn đảo kho 2 chiều |
| D22 | ★ B2 SC items không cần stock logic: stage 1 phiếu sửa chữa = tracking, không đụng kho |
| D23 | ★ APSC K80 + Cancel: in K80 + nút action đặt trên DLW (KHÔNG POS) — tránh duplicate code |
| D24 | ★ `huy_hoa_don_apsc` skip rule: `is_hang_hoa_co_kho` (symmetric với `tru_kho_apsc`) thay `is_open_price_sql` |
| D25 | ★ Wire enqueue_apsc TRƯỚC `tru_kho_apsc`: in K80 không phụ thuộc atomicity của RPC kho |
| D26 | ★ Barcode scan DLW: inline trong dialog Tạo/Sửa phiếu (KHÔNG nested), `st.toggle` on/off — Streamlit không hỗ trợ nested dialog |
| D27 | ★ Barcode scan DLW `chi_nhanh` = `get_active_branch()` (CN login), KHÔNG dùng `tu_cn` từ form dropdown — simplicity, admin tự đổi active branch nếu cần scan CN khác |
| D28 | ★ `utils/scanner_component.py` + `utils/barcode.py` + `utils/hide_streamlit_badge.py` shared 2 repo (copy thuần, không submodule) — 2 repo Streamlit Cloud deploy độc lập; fix bug 1 file phải sync sang repo còn lại |
| **D29** | **★ Hide Streamlit branding qua JS `window.top.document` (KHÔNG `window.parent`) — `components.html()` tạo iframe nested, parent = iframe app, top = top window chứa badge. Workaround tạm thời có thể break khi Streamlit update DOM/sandbox/origin** |
| **D30** | **★ Module Chấm công Phase 1: `nhan_vien_id` FK INTEGER (match prod int4) thay BIGINT trong plan. `attendance_*` PK riêng giữ BIGSERIAL. `admin_edit_history.table_name` CHECK whitelist mở rộng thêm `'attendance_sessions'`. `build_session_for_schedule` trả `{status: 'pending'}` (không tạo row) khi chưa có event + chưa qua scheduled_end_at.** |
| **D31** | **★ Chấm công IP detection (POS): `st.context.ip_address` + `X-Forwarded-For` trả về IP proxy Cloudflare/Streamlit (thay đổi mỗi lần) → switch sang JS fetch `api.ipify.org` qua `st.components.v2.component` để lấy IP NAT egress thật của cửa hàng. Cache trong `st.session_state['_client_ip_cached']`. Pattern copy từ `scanner_component.py`.** |
| **D32** | **★ Chấm công enforce active_chi_nhanh: RPC `validate_check_in_pos` + `record_attendance_event` thêm param `p_active_chi_nhanh TEXT DEFAULT NULL`. Reject khi schedule.branch_name <> p_active_chi_nhanh — tránh NV chấm công khi UI POS đang chọn CN khác (HĐ POS tạo sau đó ghi sai CN). DEFAULT NULL = backward compat.** |
| **D33** | **★ Chấm công Phase 5 preserve admin-edited: `build_session_for_schedule` early-return nếu existing session.status='edited' → tránh overwrite công admin đã sửa thủ công khi rebuild. Idempotent ngược lại: status `pending`/`built` thì rebuild bình thường.** |
| **D34** | **★ Chấm công delete period (addon): admin-only check trực tiếp trong RPC (`v_admin_role <> 'admin'` → reject). Cascade DELETE items + adjustments + period kể cả finalized (vs. logic finalize không cho sửa). Audit `ATT_PAYROLL_DELETE` level=`warn` với snapshot đầy đủ trong `details` JSONB để có thể recover thủ công nếu cần. UI: dialog typing `"XÓA"` để confirm.** |
| **D35** | **★ FK disambiguation PostgREST: bảng có 2 FK trỏ về cùng target (`attendance_work_schedules.nhan_vien_id` + `.created_by` cùng → `nhan_vien`) → nested embed `nhan_vien(...)` báo ambiguity. Fix: hint constraint name `nhan_vien!attendance_work_schedules_nhan_vien_id_fkey(...)`. Áp dụng cho mọi multi-FK embed.** |

---

## PENDING ROADMAP

### Kỹ thuật

| # | Task | Khi nào | Note |
|---|------|---------|------|
| 1 | Test LINE APSC notification volume thực tế | Sau khi user test prod | Branch 3 đã deploy 07/05 |
| 2 | RPC Nhập/Trả NCC (atomic) | TBD | Hiện ghi không atomic |
| 3 | UI khôi phục hàng bị ẩn (un-hide) | TBD | NHẮC KHI USER YÊU CẦU |
| 4 | Fix cache/spinner: timing log → targeted invalidation | Ưu tiên | Đỡ hơn sau Hướng B nhưng vẫn cần |
| 5 | Warning upload thiếu cột "Loại hàng" | TBD | |
| 6 | Logs thao tác POS app vào `action_logs` | Khi rảnh | |
| 7 | UI admin xem session POS active | TBD | DB schema có sẵn |
| 8 | ~~Module Chấm công — app riêng~~ | ✅ DONE (8 phases 14-15/05) | Done as built-in module |
| 9 | Reconciliation mode cho Tab s2 | Deferred | |
| 10 | LINE notification mở rộng | TBD | Đổi/trả + phiếu đặt hoàn thành |
| 11 | Imports thừa cleanup | Cosmetic | |
| 12 | use_container_width deprecated | Toàn codebase | width='stretch' trước 31/12/2025 |
| 13 | Wire badge "✏️ ĐÃ CHỈNH SỬA" vào báo cáo cho 2 loại phiếu mới (PDT + SC) | Nice-to-have | Defer từ B2b |
| 14 | Cleanup `_backup_admin_b1_*`, `_backup_admin_b2a_*`, `_backup_admin_b2b_*`, `_backup_apsc_k80_*` | Sau 1-2 tuần ổn | Reduce DB clutter |
| 15 | Maintenance `hide_streamlit_badge.py` nếu Streamlit update DOM | Watch | Re-inspect + cập nhật SELECTORS array |

---

## TECHNICAL NOTES

### Mã phiếu
- SC: **★ Mới (08/05)**: `nextval('sc_seq')` qua RPC `next_sc_seq()` — race-safe
- CH, KK: query max + 1 trong Python
- PNH, TH, APSC, AKH: Postgres sequence/function qua `supabase.rpc("get_next_*_num")`
- POS: AHD, AHDD, AHDC dùng sequence riêng

### `load_stock_deltas()` (DEPRECATED sau Hướng B)
Stub return `{}`, giữ tên để không break import.

### `_filter_chi_hang_hoa()` (bao_cao)
Lọc giữ `loai_sp = "Hàng hóa"`, bỏ Dịch vụ. Dùng cho XNT.

### APSC schema mapping (CRITICAL — cột tiếng Việt)

`hoa_don` table dùng cột tiếng Việt có dấu (KiotViet schema). MỌI cột cần quote `"..."`:
```python
head["Mã hóa đơn"]    # NOT head.ma_hd
head["Chi nhánh"]
head["Tổng tiền hàng"]
head["Người bán"]
head["Mã YCSC"]
```

`hoa_don` table = mixed:
- APSC (15 unique HĐ, 23 rows) — DLW mới tạo
- HDSC (78 unique, 110 rows) — KiotViet legacy KHÔNG đụng
- HD/HDD (KiotViet legacy ~12k rows) — KHÔNG đụng

→ Distinguish APSC bằng `WHERE LEFT("Mã hóa đơn", 4) = 'APSC'`

### ★ Open-price detection pattern

```python
# Python
from utils.db import is_open_price_item
if is_open_price_item(ma_hang):
    # input giá tự do, skip stock check
```

```sql
-- SQL trong RPC
IF NOT is_open_price_sql(v_ma_hang) THEN
    -- check tồn kho + UPDATE the_kho
END IF;
```

### ★ Admin Override pattern

```python
# UI
require_admin()  # block + stop nếu non-admin

# Permission check ở RPC (server-side)
SELECT _admin_validate_request(p_admin_id, p_created_at);
# Returns {ok: bool, error?: str}

# Audit
INSERT INTO action_logs (action, level) VALUES ('ADMIN_*_*', 'warn');
INSERT INTO admin_edit_history (table_name, record_id, snapshot_before, snapshot_after, ...);
```

### ★ Print queue source_app

```python
# DLW always set source_app='dlw_app'
row = {
    "doc_type": "hoa_don_sua_chua",
    "doc_id": ma_hd,
    ...
    "source_app": "dlw_app",
}
```

POS không cần set (default 'pos_app').

### ★ Barcode scan pattern trong chuyen_hang.py

```python
# Trong _render_form() — inline (KHÔNG nested dialog)
from utils.auth import get_active_branch
active_cn = get_active_branch()

scan_open = st.toggle("📷 Quét mã vạch", key="_ck_scan_open")
if scan_open:
    with st.container(key="ck-scan-section"):
        _scan_and_add_to_ck_cart(active_cn)
    st.divider()

def _scan_and_add_to_ck_cart(active_cn: str):
    from utils.scanner_component import live_scanner
    from utils.barcode import lookup_hang_by_ma_vach
    
    scan = live_scanner(key="ck_scan")
    # ... dedup ts, lookup, block tồn=0, _add_to_cart_cb adapter
```

### ★ Hide branding pattern trong app.py

```python
st.set_page_config(...)  # MUST first

# Right after page_config, before CSS + auth_gate
from utils.hide_streamlit_badge import hide_streamlit_branding
hide_streamlit_branding()

# ... CSS, auth_gate, rest of app
```

CRITICAL: JS dùng `window.top.document` (KHÔNG `window.parent`).

---

## CHECKLIST BÀN GIAO

Claude session mới nên:

1. ✅ Đọc `CLAUDE.md` trong project knowledge
2. ✅ Đọc cả 2 file `AI_CONTEXT.md` (POS + Web — bổ trợ lẫn nhau)
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
- **★ Workflow lớn: 2-phase A planning + B execute với Claude Code** — proven SPK/DVPS, B1, B2a, B2b, APSC K80, Barcode Scan

---

## OPEN ISSUES — CẦN LÀM Ở SESSION SAU

| # | Item | Status | Priority |
|---|------|--------|----------|
| 1 | Test LINE APSC notification | Đã deploy, chờ APSC mới prod | Medium |
| 2 | Web app perf | Pending từ lâu | Medium |
| 3 | Cleanup backup tables sau 1-2 tuần ổn | Pending | Low |
| 4 | Wire badge edit-history vào báo cáo cho PDT + SC (defer từ B2b) | Pending | Low |
| 5 | RPC Nhập/Trả NCC atomic | Pending | Low |
| 6 | use_container_width deprecated | Pending | Medium (deadline 31/12/2025) |
| 7 | Maintenance hide_streamlit_badge.py nếu Streamlit update DOM | Watch | Medium |

---

## TROUBLESHOOTING REFERENCE

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| Báo cáo load chậm | Cache nested + clear() | Pending — đỡ hơn sau Hướng B |
| HĐ POS không hiện | Cache 5 phút | Bấm "↺ Tải lại" |
| AHDD không vào báo cáo | Cache adapter | Cùng cách trên |
| Multiselect CN crash khi DELETE | Thiếu `chi_nhanh_id` | Đã fix Bước 5 |
| Duplicate widget ID | Key trùng tab | Dùng key unique theo tab |
| Streamlit credentials sai | URL vs secret key swap | Check format `https://[id].supabase.co` |
| `UnboundLocalError: now_vn` khi tạo APSC | Local var shadowing | ✅ Đã fix |
| Tồn âm UI sau Hướng B | Phiếu Đang chuyển còn dở | Hoàn thành phiếu hoặc xóa atomic |
| `2F005 query has no destination` | RPC paste thiếu RETURN | Paste lại toàn bộ RPC body |
| LINE APSC gửi 3 tin/HĐ | Dedupe `lt id` không match | Verify `hoa_don.id` PK |
| Duyệt kiểm kê không update tồn | RPC chưa apply | ✅ Đã fix qua `duyet_phieu_kiem_ke` |
| ★ Admin form không hiện | Non-admin login | Check `nhan_vien.role` = 'admin' |
| ★ Admin tạo HĐ báo "Không đủ tồn" | Hàng thường thật sự không đủ | Check `the_kho` (admin không bypass stock cho hàng thường) |
| ★ Admin sửa HĐ có PDT báo "BLOCK items" | HĐ đã có phiếu đổi/trả active | Đúng behavior — sửa header thoải mái, items BLOCK |
| ★ Admin sửa SC báo "BLOCK items APSC" | Phiếu đã convert APSC | Đúng behavior — items đã materialize trong APSC |
| ★ APSC K80 in lỗi tiếng Việt | Codepage | ✅ Đã solve qua raster bitmap (07/05) |
| ★ APSC `huy_hoa_don_apsc` báo "không hợp lệ" | Mã không bắt đầu APSC | Verify prefix, không hủy được HDSC legacy |
| ★ HĐ APSC tạo nhưng không in K80 | Daemon down hoặc CN không phải 100 LQĐ | Check `print_queue` table; CN khác silent skip |
| **★ Scan trong chuyen_hang lookup ra tồn = 0** | SP hết hàng ở CN login | Đúng behavior — block UI, NV phải xử lý (đổi CN nguồn nếu admin) |
| **★ Scan ra "Không tìm thấy" cho SP có thật** | ma_vach trong DB strip dấu (lịch sử import) | NV gõ lại ma_vach trong form Hàng hóa DLW |
| **★ Badge "Hosted with Streamlit" xuất hiện lại** | Streamlit Cloud update DOM | Inspect lại → cập nhật SELECTORS trong `hide_streamlit_badge.py` |
| **★ Chấm công load Bảng công lỗi `Could not embed because more than one relationship was found for 'nhan_vien'`** | PostgREST không pick được FK (2 FK `nhan_vien_id` + `created_by` trỏ cùng `nhan_vien`) | Hint constraint name: `.select("..., nhan_vien!attendance_work_schedules_nhan_vien_id_fkey(ho_ten, role)")` |
| **★ Chấm công POS IP detection trả IP proxy** | `st.context.ip_address` + `X-Forwarded-For` ở Streamlit Cloud = IP Cloudflare/Streamlit (thay đổi) | Dùng JS fetch `api.ipify.org` qua `st.components.v2.component`. Cache session. Source = `'browser_js'`. |
| **★ Chấm công NV check-in khi UI chọn CN khác** | RPC chỉ check IP + schedule, không cross-check `active_chi_nhanh` | Param mới `p_active_chi_nhanh` ở `validate_check_in_pos` + `record_attendance_event`. Reject mismatch. |
| **★ Chấm công admin sửa session bị mất sau rebuild** | `build_session_for_schedule` overwrite session khi `build_sessions_for_date` chạy lại | Early return nếu existing.status='edited' (preserve admin edit) |
| **★ Chấm công RPC báo "function not unique"** | CREATE OR REPLACE không drop signature cũ khi đổi số param | `DROP FUNCTION IF EXISTS <name>(old_signature)` migration trước |
| **★ Chấm công không xóa được kỳ lương đã chốt** | UI Phase 6 chỉ cho `compute`/`finalize`, không có nút xóa | RPC `delete_payroll_period` (admin-only) + `_delete_period_dialog` typing `"XÓA"` confirm. Cascade items + adjustments. Audit `ATT_PAYROLL_DELETE` warn. |
| **★ Chấm công RPC báo `record "v_session" is not a scalar variable`** | Khai báo `v_session RECORD` rồi dùng `INTO v_admin_name, v_session` (scalar) | Tách scalar var `v_admin_role TEXT` riêng |
| **★ Chấm công insert admin_edit_history reject CHECK** | `table_name` không có `'attendance_sessions'` trong CHECK whitelist | ALTER constraint thêm `'attendance_sessions'` (migration p1_admin_edit_history_whitelist) |

---

## CONTACT

User: **Kevin**, chủ DL Watch ở Bà Rịa - Vũng Tàu. Liên hệ qua chat Claude.

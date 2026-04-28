# AI_CONTEXT.md — DL Watch Store App
**Cập nhật:** 28/04/2026 | **Session tiếp theo bắt đầu từ đây**

---

## PROJECT OVERVIEW

- **Stack:** Streamlit (Python, multi-file) + Supabase (PostgreSQL)
- **Deploy:** Streamlit Cloud
- **3 chi nhánh:** 100 Lê Quý Đôn · Coop Vũng Tàu · GO BÀ RỊA
- **Codebase:** `app.py` + `utils/` (config, db, auth, helpers) + `modules/` (10 modules)

---

## CẤU TRÚC FILES

```
app.py
utils/
  config.py       ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER, SESSION_EXPIRY_DAYS
  db.py           supabase client + tất cả load_* functions + log_action
  auth.py         login/logout, session, get_user, is_admin, is_ke_toan_or_admin
  helpers.py      now_vn, now_vn_iso, today_vn, fmt_vn, _normalize, _build_phieu_html, _in_phieu_sc
modules/
  tong_quan.py    Dashboard + greeting
  hoa_don.py      Tra cứu hóa đơn KiotViet
  hang_hoa.py     Master hàng hóa + tồn kho
  sua_chua.py     Phiếu sửa chữa (UI redesign hoàn chỉnh)
  nhap_hang.py    Nhập/Trả hàng NCC
  khach_hang.py   Danh sách + tra cứu khách hàng
  kiem_ke.py      Kiểm kê kho
  chuyen_hang.py  Chuyển hàng giữa chi nhánh
  quan_tri.py     Upload, nhân viên, logs, kết sổ
  bao_cao.py      Báo cáo doanh thu, XNT, tồn kho
```

---

## DATABASE TABLES CHÍNH

| Table | Mô tả |
|-------|-------|
| `hang_hoa` | Master sản phẩm. Có cột `active` (bool), `loai_sp` ("Hàng hóa"/"Dịch vụ"), `loai_hang`, `thuong_hieu`, `gia_ban` |
| `the_kho` | Tồn kho theo CN. Cột: `Mã hàng`, `Chi nhánh`, `Tồn cuối kì`, `id` |
| `hoa_don` | Hóa đơn KiotViet upload. Denormalized (mỗi item 1 dòng) |
| `phieu_sua_chua` | Header phiếu SC. Cột: `ma_phieu`, `chi_nhanh`, `trang_thai`, `ten_khach`, `sdt_khach`, `khach_tra_truoc`, v.v. |
| `phieu_sua_chua_chi_tiet` | Chi tiết dịch vụ/linh kiện SC. Cột: `id`, `ma_phieu`, `loai_dong`, `ten_hang`, `ma_hang`, `so_luong`, `don_gia` |
| `phieu_chuyen_kho` | Phiếu chuyển hàng. Cột: `loai_phieu` phân biệt App vs KiotViet |
| `phieu_nhap_hang` / `_ct` | Nhập hàng NCC |
| `phieu_tra_hang` / `_ct` | Trả hàng NCC. Đã active trong bao_cao.py |
| `phieu_kiem_ke` / `_chi_tiet` | Kiểm kê kho |
| `khach_hang` | Danh sách khách. Unique key: `sdt` |
| `nhan_vien` / `nhan_vien_chi_nhanh` | Nhân viên + phân chi nhánh |
| `nha_cung_cap` | Nhà cung cấp |
| `action_logs` | Log thao tác |
| `sessions` | Session token đăng nhập |

---

## KEY CONSTANTS (utils/config.py)

```python
IN_APP_MARKER   = "Chuyển hàng (App)"
ARCHIVED_MARKER = "Chuyển hàng (App - đã đồng bộ)"
APP_INVOICE_PREFIXES = ["APSC"]   # bao_cao.py — thêm prefix POS vào đây khi có
```

---

## IMPORT CHUẨN (đầu mỗi file module)

```python
from utils.helpers import _normalize, now_vn, now_vn_iso, today_vn, fmt_vn
from datetime import datetime, timedelta   # giữ timedelta cho filter ngày
```

---

## COMPLETED — TẤT CẢ VIỆC ĐÃ LÀM

### modules/sua_chua.py — UI Redesign hoàn chỉnh
**CSS scoped** trong constant `_SC_CSS` (inject một lần đầu module):
- Classes: `sc-card`, `sc-badge`, `sc-badge-green`, `sc-badge-red`, `sc-section-title`
- `sc-money-card`, `sc-money-card-red`, `sc-money-label`, `sc-money-value`, `sc-money-value-red`
- `sc-info-row`, `sc-info-label`, `sc-info-val`

**Tab 1 — Danh sách phiếu:**
- Filter bar: chi nhánh + trạng thái + search text
- Dataframe danh sách
- Dropdown xem chi tiết dịch vụ/linh kiện

**Tab 2 — Tạo phiếu mới:**
- Card mã phiếu dự kiến (màu xanh)
- 4 sections: Khách hàng / Đồng hồ / Thanh toán & Ghi chú / Dịch vụ dự kiến

**Tab 3 — Chi tiết / Cập nhật:**
- Search + Selectbox nằm cùng 1 hàng `st.columns([1, 1])` (keys: `col_s`, `col_p`)
- Header phiếu với badge trạng thái góc phải
- Layout 2 cột: thông tin tiếp nhận + mô tả lỗi (trái) | bảng DV + 3 metric cards (phải)
- Expander "✏️ Cập nhật phiếu" — có thể xóa từng dịch vụ đã lưu (nút ✕, gọi delete theo `id`)
- Action buttons: In phiếu A5 + Hủy/Xóa phiếu (admin)

**Tab 4 — Tạo hóa đơn sửa:**
- Search + Selectbox cùng 1 hàng (keys: `col_sh`, `col_ph`)
- Card tóm tắt phiếu + bảng DV
- Section "Thông tin hóa đơn": chỉ có ô giảm giá
- 3 metric cards: Tổng DV / Giảm giá+Trả trước / Khách cần trả
- Section "Phương thức thanh toán": checkbox "Chia nhiều phương thức" nằm ngay dưới section title

### modules/hang_hoa.py — Admin features
- Thêm hàng hóa mới: form có `st.radio("Loại SP", ["Hàng hóa", "Dịch vụ"], index=0, horizontal=True)` → lưu vào `loai_sp`, **mặc định "Hàng hóa"**
- Soft-delete (ẩn) hàng hóa: xác nhận 2 bước → update `active = False`
- Sửa thông tin hàng hóa (`_render_sua_hang_hoa`)
- Chỉnh tồn kho trực tiếp từng chi nhánh (`_render_ton_kho` expander)
- `load_hang_hoa()` filter `.neq("active", False)` — ẩn hàng inactive
- SQL đã chạy: `ALTER TABLE hang_hoa ADD COLUMN active boolean DEFAULT true; UPDATE hang_hoa SET active = true WHERE active IS NULL;`

### modules/bao_cao.py
- Tab **Tồn kho**: filter CN/loại/thương hiệu, pivot tồn theo CN, metrics, bảng chi tiết, tóm tắt theo nhóm
- `_load_tra_hang()` active và đúng — bảng `phieu_tra_hang` đã tồn tại
- `df_tra` tích hợp vào `_tab_xuat_nhap_ton()` (tính xuất kho + tồn đầu/cuối kỳ)
- Tab **Nhân viên** (admin only)

### modules/chuyen_hang.py — RPC + UX fixes
- RPC `xac_nhan_chuyen_hang`: lock FOR UPDATE (LIMIT 1), validate tồn, trừ kho CN nguồn atomic, đổi trang_thai → "Đang chuyển", GIỮ `loai_phieu = IN_APP_MARKER`
- RPC `nhan_hang`: cộng kho CN đích atomic, đổi trang_thai → "Đã nhận", set `loai_phieu = ARCHIVED_MARKER`
- Fix checkbox `disabled=not confirmed` (tham số đầy đủ)
- Fix tab văng về Danh sách khi rerun trong edit mode: đảo thứ tự tab khi `ck_editing` active
- Fix `has_overflow` tính sai: render `number_input` trước → apply `new_sl` vào session_state → tính `over`

### modules/quan_tri.py — module_nhan_vien()
- Multiselect chi nhánh với diff logic (DELETE bỏ đi, INSERT thêm vào)
- Query thêm `chi_nhanh_id` để có ID khi DELETE

### utils/helpers.py — Timezone standardization
- `now_vn()`, `now_vn_iso()`, `today_vn()`, `fmt_vn()` dùng `ZoneInfo("Asia/Ho_Chi_Minh")`
- Applied toàn bộ: nhap_hang.py, sua_chua.py, quan_tri.py, kiem_ke.py, chuyen_hang.py, db.py, tong_quan.py

### SQL đã chạy trên Supabase
```sql
ALTER TABLE hang_hoa ADD COLUMN active boolean DEFAULT true;
UPDATE hang_hoa SET active = true WHERE active IS NULL;
-- RPC: xac_nhan_chuyen_hang, nhan_hang (xem rpc_chuyen_hang.sql đã output)
```

---

## PERFORMANCE — PHÂN TÍCH (chưa fix)

### Vấn đề
Load module 3–10s, spinner xuất hiện khi chuyển module (đặc biệt Báo cáo).

### Nguyên nhân đã xác định

**1. Nested cached calls** — `load_the_kho()` gọi bên trong:
```
load_the_kho() ttl=300
  └─ load_stock_deltas() ttl=60  ← hết hạn mỗi 60s → spinner
       └─ (trong load_the_kho) load_hang_hoa() ttl=600
```
Streamlit không hỗ trợ tốt nested `@cache_data` → inner function hiển thị spinner riêng.

**2. `st.cache_data.clear()` toàn bộ** — xuất hiện 26 chỗ trong codebase. Mỗi thao tác (lưu phiếu, upload...) xóa toàn bộ cache → khi chuyển module tiếp theo tất cả phải recompute đồng thời.

**3. Nested trong bao_cao.py** — `_load_lich_su_ma_hang()` gọi `load_the_kho()` → lại nest tiếp.

### Hướng fix (chưa implement — làm session sau)
1. **Thêm `show_spinner=False`** vào `load_stock_deltas()` và `load_hang_hoa()` — ẩn spinner nested
2. **Tăng TTL** `load_stock_deltas` từ 60s → 300s (đồng bộ với `load_the_kho`)
3. **Targeted cache invalidation** thay vì `st.cache_data.clear()` toàn bộ — chưa thiết kế
4. Trước khi fix: thêm timing log để đo đúng bottleneck thực tế

---

## KEY DECISIONS

| # | Quyết định |
|---|------------|
| D1 | RPC Hybrid: Python xử lý UI/validation, Supabase RPC cho "chốt chặn cuối" khi xác nhận phiếu |
| D2 | `phieu_tra_hang` = Trả hàng NCC (có `ma_ncc`). Đổi trả khách sẽ dùng bảng riêng `phieu_doi_tra_pos` |
| D3 | RPC archive logic: `xac_nhan` GIỮ `IN_APP_MARKER` (trừ tồn CN nguồn qua delta). `nhan_hang` set `ARCHIVED_MARKER` (RPC đã cộng tồn CN đích trực tiếp) |
| D4 | Service layer: chưa cần. Xem xét khi làm POS hoặc team lớn |
| D5 | Timezone: tất cả DB column là `timestamptz`. Code chuẩn hóa dùng `ZoneInfo` không phải offset thủ công |
| D6 | `loai_sp` = "Hàng hóa" mặc định khi thêm hàng mới (không phải NULL) |

---

## PENDING ROADMAP

### Kỹ thuật đã xác định

| # | Task | Khi nào |
|---|------|---------|
| 1 | RPC cho Nhập/Trả hàng NCC (atomic khi xác nhận) | Khi làm POS |
| 2 | UI khôi phục hàng bị ẩn (un-hide) | Khi làm POS hoặc khi cần — **NHẮC KHI ĐÓ** |
| 3 | Bật cân bằng `the_kho` từ kiểm kê (`_kk_approve` chưa update `the_kho`) | TBD |
| 4 | Fix cache/spinner: timing log → targeted invalidation | Session sau (ưu tiên) |
| 5 | Warning khi upload file hàng hóa thiếu cột "Loại hàng" | TBD |

### Tính năng mới
| # | Task |
|---|------|
| 6 | Module POS — bán hàng trực tiếp, thêm prefix vào `APP_INVOICE_PREFIXES` |
| 7 | Module Chấm công — app Streamlit riêng |

---

## TECHNICAL NOTES

### Mã phiếu
- SC, CH, KK: query max + 1 trong Python
- PNH, TH, APSC, AKH: Postgres sequence/function qua `supabase.rpc("get_next_*_num")`
- Xóa phiếu cũ không tái sử dụng mã

### `load_stock_deltas()` logic
- Chỉ tính delta cho `loai_phieu = IN_APP_MARKER`
- Sau `nhan_hang` → `ARCHIVED_MARKER` → bị bỏ qua → tránh double-count với RPC

### `_filter_chi_hang_hoa()` (bao_cao.py)
- Lọc chỉ giữ `loai_sp = "Hàng hóa"`, bỏ Dịch vụ
- Dùng trong: tab XNT (bán hàng, APSC linh kiện), tính tồn đầu/cuối kỳ

### Scroll-to-top sau lưu (sua_chua.py)
```python
# Sau khi lưu cập nhật, set flag:
st.session_state["sc_scroll_top"] = True
# Đầu tab_detail, check:
if st.session_state.pop("sc_scroll_top", False):
    st.components.v1.html("<script>window.parent.document.querySelector('section.main').scrollTo(0,0);</script>", height=0)
```

### Expander tự đóng khi rerun (sua_chua.py)
```python
# Guard: chỉ mở expander khi có search text hoặc items trong basket
if (st.session_state.get("sc_upd_dv_ma_tim", "").strip()
        or st.session_state.get("sc_upd_items", [])):
    st.session_state["sc_upd_open"] = True
```

---

## FILES ĐÃ OUTPUT (có thể dùng lại)

| File | Nội dung |
|------|----------|
| `outputs/hang_hoa.py` | Admin features + loai_sp radio + soft-delete |
| `outputs/sua_chua.py` | UI redesign 4 tab hoàn chỉnh |
| `outputs/chuyen_hang.py` | RPC + UX fixes |
| `outputs/rpc_chuyen_hang.sql` | SQL tạo 2 RPC functions |
| `outputs/helpers.py` | Timezone helpers |
| `outputs/bao_cao_patch.py` | Tab tồn kho + tra_hang patch |
| `outputs/AI_CONTEXT.md` | File này |

---

## TRẠNG THÁI KIỂM KÊ HIỆN TẠI

**⚠ Có nhân viên đang thực hiện kiểm kê trực tiếp trên app** (tại thời điểm kết thúc session).
- Không deploy thay đổi gì cho đến khi họ hoàn thành.
- Module kiểm kê (`kiem_ke.py`) không có thay đổi trong các session gần đây.

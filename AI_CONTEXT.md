# AI_CONTEXT.md — DL Watch Store Management App
*Cập nhật: 24/04/2026 — Bản bàn giao đầy đủ*

---

## 1. TỔNG QUAN DỰ ÁN

**Tên app:** DL Watch Store
**Loại:** Web app quản lý cửa hàng đồng hồ nội bộ
**Stack:** Streamlit (Python, multi-file) + Supabase (PostgreSQL)
**Deploy:** Streamlit Cloud
**Trạng thái:** Chạy song song KiotViet, đang dần thay thế

---

## 2. CẤU TRÚC FILE (sau khi tách code)

```
app.py                    ← Entry point: CSS + auth gate + navigation
utils/
  __init__.py
  config.py               ← Constants: ALL_BRANCHES, CN_SHORT, markers
  db.py                   ← Supabase client, log_action, tất cả load_* functions
  auth.py                 ← Login, session, get_user, run_auth_gate()
  helpers.py              ← _normalize, _build_phieu_html, _in_phieu_sc
modules/
  __init__.py
  tong_quan.py            ← Dashboard + hien_thi_dashboard()
  hoa_don.py              ← Module hóa đơn
  hang_hoa.py             ← Module hàng hóa
  sua_chua.py             ← Module sửa chữa
  nhap_hang.py            ← Module nhập hàng + NCC
  khach_hang.py           ← Module khách hàng
  kiem_ke.py              ← Module kiểm kê
  chuyen_hang.py          ← Module chuyển hàng
  quan_tri.py             ← Module quản trị + nhân viên
```

---

## 3. STACK & CONVENTIONS

### Tech
- Python + Streamlit (multi-file, entry point `app.py`)
- Supabase (PostgREST API qua supabase-py)
- Pandas, Plotly, bcrypt, openpyxl

### Conventions bắt buộc
- Giờ VN: `datetime.now() + timedelta(hours=7)`
- Format số: dấu `.` phân cách (100.000đ) — `.replace(",",".")`
- SĐT: chuẩn hóa bỏ `.0`, thêm `0` đầu nếu 9 chữ số (trong `load_hoa_don`)
- Navigation: `st.pills` (không dùng `st.radio`)

### Mã nội bộ app (không trùng KiotViet)
| Prefix | Module | Ví dụ |
|--------|--------|-------|
| `APSC` | HĐ sửa chữa app | APSC000001 |
| `AKH` | Khách hàng app | AKH000001 |
| `SC` | Phiếu sửa chữa | SC000001 |
| `PNH` | Phiếu nhập hàng | PNH000001 |
| `KK` | Kiểm kê | KK000001 |
| `CH` | Chuyển hàng app | CH000001 |

### Postgres RPC Functions (đã tạo trong Supabase)
```sql
get_next_apsc_num()  -- regex ^APSC[0-9]{6}$ để tránh lỗi timestamp dài
get_next_akh_num()   -- regex ^AKH[0-9]{6}$
get_next_pnh_num()   -- regex ^PNH[0-9]{6}$
```

**Pattern đọc kết quả RPC:**
```python
data = res.data
num = int(data[0] if isinstance(data, list) else data) if data else 1
```

### In phiếu (UTF-8 Blob URL — tránh lỗi atob tiếng Việt)
```python
b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
# JS: new Blob([new TextDecoder('utf-8').decode(Uint8Array.from(atob(b64),...))], {type:'text/html'})
```

### Auto-fill khách hàng (session_state + rerun)
```python
if sdt != st.session_state.get(sdt_prev_key, ""):
    st.session_state[sdt_prev_key] = sdt
    kh = lookup_khach_hang(sdt)
    st.session_state[kh_key] = kh
    st.session_state[ten_key] = kh["ten_kh"] if kh else ""
    st.rerun()
```

### QUAN TRỌNG: Tên cột tiếng Việt trong Supabase PostgREST
| Trường hợp | Kết quả |
|-----------|---------|
| `.in_("Chi nhánh", list)` | ✅ HOẠT ĐỘNG — đừng thay thế |
| `.in_("Mã hàng", list)` | ❌ LỖI ENCODE — dùng `.select("*")` rồi filter Python |
| `.select("Mã hàng, Tồn cuối kì")` | ❌ LỖI ENCODE — dùng `.select("*")` |
| `.eq("Chi nhánh", value)` | ✅ HOẠT ĐỘNG |

---

## 4. DATABASE SCHEMA

### Bảng từ KiotViet (upload định kỳ)
| Bảng | Mô tả | Upload |
|------|-------|--------|
| `hoa_don` | Hóa đơn bán hàng (cột tiếng Việt có dấu) | Delete by mã HĐ + insert |
| `hang_hoa` | Danh mục hàng hóa | Upsert theo `ma_hang` |
| `the_kho` | Tồn kho snapshot | Delete-insert theo CN |
| `khach_hang` | Danh sách khách | Upsert theo `sdt` |

### Bảng do app tạo
| Bảng | Mô tả |
|------|-------|
| `nhan_vien` | Tài khoản, role, bcrypt password |
| `sessions` | Session token, TTL 3 ngày |
| `chi_nhanh` | Danh sách chi nhánh |
| `nhan_vien_chi_nhanh` | Phân quyền NV theo CN |
| `phieu_chuyen_kho` | Phiếu chuyển hàng |
| `phieu_kiem_ke` + `phieu_kiem_ke_chi_tiet` | Kiểm kê |
| `phieu_sua_chua` + `phieu_sua_chua_chi_tiet` | Sửa chữa |
| `nha_cung_cap` | Nhà cung cấp |
| `phieu_nhap_hang` + `phieu_nhap_hang_ct` | Nhập hàng |

### Cột đặc biệt trong hang_hoa
- `loai_hang` = cấp 1 (vd: "Đồng hồ đeo tay")
- `thuong_hieu` = cấp 2 (vd: "Casio")
- Upload: parse `nhom_hang` dạng `"Đồng hồ>>Casio"` thành 2 cột mới
- `nhom_hang` gốc vẫn giữ làm backup
- `ma_vach` — mã vạch riêng (khác `ma_hang`)

### Cột đặc biệt trong phieu_nhap_hang_ct
```sql
-- Đã thêm sau khi tạo ban đầu:
ALTER TABLE phieu_nhap_hang_ct
ADD COLUMN ma_vach text,
ADD COLUMN loai_hang text,
ADD COLUMN thuong_hieu text;
```

### Tồn kho
- `the_kho` = snapshot từ KiotViet
- Delta từ phiếu chuyển hàng App tính qua `load_stock_deltas()`
- Tồn thực = snapshot + delta
- Module nhập hàng: cộng thẳng vào `the_kho."Tồn cuối kì"` khi xác nhận

---

## 5. PHÂN QUYỀN

| Role | Quyền |
|------|-------|
| `admin` | Toàn quyền, xác nhận phiếu nhập, duyệt kiểm kê, xóa data |
| `ke_toan` | Xem tất cả CN, tạo phiếu nhập, xem giá vốn |
| `nhan_vien` | Chỉ CN của mình, tạo phiếu SC/chuyển/kiểm kê, xem nhập hàng |

---

## 6. AUTH FLOW

```
app.py
  ├── set_page_config()       ← PHẢI là lệnh Streamlit đầu tiên
  ├── CSS inject
  ├── from utils.auth import run_auth_gate
  ├── run_auth_gate()          ← PHẢI gọi TRƯỚC khi import modules
  │     ├── restore_session(token từ URL)
  │     ├── chưa login → show_login() → st.stop()
  │     └── chưa chọn CN → branch picker → st.stop()
  └── import modules (chỉ sau khi auth OK)
```

**Session:** URL token (`?token=uuid&branch=tên`), TTL 3 ngày, bcrypt

---

## 7. MODULES ĐÃ HOÀN THÀNH

### Module Hóa đơn
- Search SĐT / mã HĐ / ngày, hỗ trợ HD/HDSC/HDD/APSC
- SĐT hiển thị trong header, fix leading zero

### Module Hàng hóa
- Filter 2 cấp loai_hang + thuong_hieu
- Detail card tồn kho 3 CN (dùng cache per CN riêng)
- Nút ✕ clear search + bỏ chọn

### Module Chuyển hàng
- Tạo/xác nhận/nhận/hủy/kết sổ, delta tồn kho

### Module Kiểm kê
- `inner join` với the_kho (chỉ hàng tồn > 0)
- Quét phát sinh vẫn ghi nhận dù không có trong danh sách
- Duyệt admin, xuất Excel KiotViet

### Module Sửa chữa ✅ Hoàn chỉnh
- Trạng thái: Đang sửa → Chờ linh kiện → Chờ giao khách
- Tab "Tạo HĐ sửa": giảm giá + PTTT → APSC → phiếu Hoàn thành
- In phiếu A5, UTF-8 Blob, pending print qua session_state
- Auto-fill tên từ SĐT

### Module Khách hàng ✅
- Upload KiotViet, chi tiết lịch sử HĐ + SC
- Fix hiển thị `nan` → `—`, format ngày TN

### Module Nhập hàng ✅
- Nháp → Chờ XN → Đã nhập kho
- Fuzzy search + inline create (loai_hang, thuong_hieu, ma_vach)
- Gộp dòng trùng mã, flag ⚠️ thay đổi giá
- Batch query tồn kho + giá bán (pagination đầy đủ)
- Hoàn tác trừ lại tồn kho

### Module Quản trị
- Upload 5 loại file, xóa data, kết sổ phiếu App
- Quản lý nhân viên

---

## 8. KNOWN ISSUES & TECH DEBT

| ID | Mô tả | Mức độ |
|----|-------|--------|
| DEBT-01 | 4 phiếu chuyển format cũ CH26... chưa migrate | Low |
| WARN-01 | `use_container_width` deprecated → `width=` sau 2025-12-31 | Medium |
| NOTE-01 | `hien_thi_dashboard()` giữ cho module Báo cáo | — |
| NOTE-02 | In iOS: `window.open()` bị block — by design | — |
| NOTE-03 | `the_kho` cần `.select("*")` + filter Python khi filter theo `Mã hàng` | Low |
| NOTE-04 | Apple Touch Icon iOS hạn chế do Streamlit sandbox | — |

---

## 9. ROADMAP

```
✅ HOÀN THÀNH
├── Auth, Session, Navigation
├── Hóa đơn, Hàng hóa, Chuyển hàng, Kiểm kê
├── Sửa chữa, Khách hàng, Nhập hàng + NCC
└── Tách code multi-file

📋 TIẾP THEO
│
├── 1. Module Báo cáo                         ← TIẾP THEO
│   ├── Doanh thu theo CN / thời gian / loại HĐ
│   ├── Tồn kho tổng hợp
│   └── Tái dụng hien_thi_dashboard() trong tong_quan.py
│
├── 2. Module POS — App Streamlit riêng
│   ├── [ARCH] Cloud-to-LAN Print Spooler
│   │   ├── Bảng print_queue (Supabase)
│   │   │   └── id, chi_nhanh, payload(base64 ESC/POS),
│   │   │       status(pending/printing/done/error), created_at
│   │   ├── POS App (Streamlit Cloud) → INSERT vào print_queue
│   │   ├── print_daemon.py (local tại mỗi cửa hàng)
│   │   │   ├── Poll Supabase 1Hz, filter chi_nhanh
│   │   │   └── TCP socket → máy in port 9100
│   │   └── config.py: CHI_NHANH, PRINTER_IP (Static!), PORT=9100
│   ├── Máy in: Xprinter XP-365B (WiFi+LAN, ESC/POS, K80)
│   │   └── ⚠️ Switch DIP sang Receipt mode trước khi dùng
│   ├── In điện thoại: data URI (iOS/Android/Win)
│   └── Bấm "Tạo HĐ" → in ngay
│
├── 3. Module Chấm công — App Streamlit riêng
│
└── 4. Li dị KiotViet hoàn toàn
    ├── Bật cân bằng the_kho từ kiểm kê
    └── Tồn kho tính động 100% nội bộ
```

---

## 10. QUYẾT ĐỊNH KIẾN TRÚC

| # | Quyết định | Lý do |
|---|-----------|-------|
| D1 | 1 DB, phân biệt bằng cột `chi_nhanh` | Không tách DB theo CN |
| D2 | Kiểm kê xuất Excel → import KiotViet | Giai đoạn song song |
| D3 | POS là app riêng, chung Supabase | Tách UX mobile vs desktop |
| D4 | Nhập hàng cộng thẳng `the_kho` | Chỉ dùng thật khi li dị KiotViet |
| D5 | Mã APSC (không phải HDSC) | Tránh trùng KiotViet |
| D6 | Cloud-to-LAN print qua Supabase queue | Streamlit Cloud không kết nối LAN |
| D7 | Static IP máy in | DHCP reboot = mất TCP |
| D8 | Tách code multi-file | 5000+ dòng, dễ maintain |
| D9 | `.in_("Chi nhánh")` HOẠT ĐỘNG bình thường | Đã xác nhận, không filter Python |

---

## 11. THÔNG TIN SUPABASE & APP

**Supabase URL:** `gmxuolueecjhffqigmoy.supabase.co`
**Secrets:** `SUPABASE_URL`, `SUPABASE_KEY`

**Ba chi nhánh:**
- `100 Lê Quý Đôn`
- `Coop Vũng Tàu`
- `GO BÀ RỊA`

**Tài khoản admin:** username `admin` / ho_ten `Đăng Khoa`

### SQL xóa data test
```sql
-- Phiếu sửa chữa
DELETE FROM phieu_sua_chua_chi_tiet WHERE ma_phieu IN
    (SELECT ma_phieu FROM phieu_sua_chua WHERE created_by = 'Đăng Khoa');
DELETE FROM phieu_sua_chua WHERE created_by = 'Đăng Khoa';

-- Hóa đơn APSC
DELETE FROM hoa_don WHERE "Mã hóa đơn" LIKE 'APSC%';

-- Phiếu nhập
DELETE FROM phieu_nhap_hang_ct WHERE ma_phieu IN
    (SELECT ma_phieu FROM phieu_nhap_hang WHERE created_by = 'Đăng Khoa');
DELETE FROM phieu_nhap_hang WHERE created_by = 'Đăng Khoa';

-- Mã hàng test
DELETE FROM the_kho WHERE "Mã hàng" IN ('MA1', 'MA2');
DELETE FROM hang_hoa WHERE ma_hang IN ('MA1', 'MA2');
```

# AI_CONTEXT.md — Watch Store Management App
*Cập nhật: 23/04/2026*

---

## 1. TỔNG QUAN DỰ ÁN

**Loại:** Web app quản lý cửa hàng đồng hồ nội bộ  
**Stack:** Streamlit (Python, single-file) + Supabase (PostgreSQL)  
**Deploy:** Streamlit Cloud  
**File chính:** `app.py` (~4500+ dòng)  
**Trạng thái:** Chạy song song KiotViet, đang dần thay thế

---

## 2. STACK & CONVENTIONS

### Tech
- Python + Streamlit (single-file app)
- Supabase (PostgREST API qua supabase-py)
- Pandas, Plotly, openpyxl, bcrypt

### Conventions bắt buộc
- Giờ VN: `datetime.now() + timedelta(hours=7)`
- Format số: dấu `.` phân cách (100.000đ) — dùng `.replace(",",".")`
- SĐT: chuẩn hóa bỏ `.0`, thêm `0` đầu nếu 9 chữ số
- Mã nội bộ app không trùng KiotViet:
  - `APSC` = hóa đơn sửa chữa app
  - `AKH` = khách hàng app
  - `SC` = phiếu sửa chữa
  - `PNH` = phiếu nhập hàng
  - `KK` = kiểm kê
  - `CH` = chuyển hàng app

### Sinh mã
Dùng Postgres RPC để tránh lỗi encode tên cột tiếng Việt:
- `get_next_apsc_num()` → APSC hóa đơn sửa chữa
- `get_next_akh_num()` → AKH khách hàng
- `get_next_pnh_num()` → PNH phiếu nhập hàng

Pattern đọc kết quả RPC (supabase-py trả scalar hoặc list):
```python
data = res.data
num = int(data[0] if isinstance(data, list) else data) if data else 1
```

### In phiếu
Dùng Blob URL để giữ UTF-8 tiếng Việt (tránh lỗi `atob()`):
```python
b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
# JS: new Blob([new TextDecoder('utf-8').decode(Uint8Array.from(atob(b64),...))], {type:'text/html'})
```

### Auto-fill khách hàng
Dùng `session_state` + `st.rerun()` để trigger re-render:
```python
if sdt != st.session_state.get(sdt_prev_key, ""):
    st.session_state[sdt_prev_key] = sdt
    kh = lookup_khach_hang(sdt)
    st.session_state[kh_key] = kh
    st.session_state[ten_key] = kh["ten_kh"] if kh else ""
    st.rerun()
```

---

## 3. DATABASE SCHEMA

### Bảng từ KiotViet (upload định kỳ)
| Bảng | Mô tả |
|------|-------|
| `hoa_don` | Hóa đơn bán hàng (cột tiếng Việt có dấu) |
| `hang_hoa` | Danh mục hàng hóa (`ma_hang`, `ten_hang`, `gia_ban`) |
| `the_kho` | Tồn kho snapshot (`Mã hàng`, `Chi nhánh`, `Tồn cuối kì`) |
| `khach_hang` | Danh sách khách hàng (upsert theo `sdt`) |

### Bảng do app tạo
| Bảng | Mô tả |
|------|-------|
| `nhan_vien` | Tài khoản nhân viên, role, bcrypt password |
| `sessions` | Session token URL-based, TTL 3 ngày |
| `chi_nhanh` | Danh sách chi nhánh |
| `nhan_vien_chi_nhanh` | Phân quyền NV theo CN |
| `phieu_chuyen_kho` | Phiếu chuyển hàng nội bộ |
| `phieu_kiem_ke` | Phiếu kiểm kê |
| `phieu_kiem_ke_chi_tiet` | Chi tiết kiểm kê |
| `phieu_sua_chua` | Phiếu tiếp nhận sửa chữa |
| `phieu_sua_chua_chi_tiet` | Dịch vụ/linh kiện trong phiếu SC |
| `nha_cung_cap` | Nhà cung cấp |
| `phieu_nhap_hang` | Phiếu nhập hàng |
| `phieu_nhap_hang_ct` | Chi tiết phiếu nhập hàng |

### Lưu ý quan trọng về `hoa_don`
- Cột tên tiếng Việt có dấu → KHÔNG dùng `.select("cột")` trực tiếp, dễ lỗi encode
- Dùng `.select("*")` rồi filter bằng Python
- Cột `Điện thoại` bị Excel lưu thành float (`978544874.0`) → cần `_fix_sdt()` khi load
- Mã APSC hóa đơn sửa chữa app phân biệt với HDSC của KiotViet

### Tồn kho
- `the_kho` = snapshot từ KiotViet
- Delta từ phiếu App (chuyển hàng) được tính riêng trong `load_stock_deltas()`
- Tồn thực = snapshot + delta
- Module nhập hàng: cộng thẳng vào `the_kho.Tồn cuối kì` khi xác nhận

---

## 4. PHÂN QUYỀN

| Role | Quyền |
|------|-------|
| `admin` | Toàn quyền, xác nhận phiếu nhập, duyệt kiểm kê, xóa dữ liệu |
| `ke_toan` | Xem tất cả CN, tạo phiếu nhập, xem giá vốn |
| `nhan_vien` | Chỉ xem CN của mình, tạo phiếu sửa/chuyển/kiểm kê |

Helper functions: `is_admin()`, `is_ke_toan_or_admin()`, `get_active_branch()`, `get_accessible_branches()`

---

## 5. MODULES ĐÃ HOÀN THÀNH

### Navigation
`st.pills` (thay `st.radio`) — nút có viền, sáng khi chọn, không cần CSS hack

### Auth
URL token, bcrypt, session TTL 3 ngày

### Module Hóa đơn
- Search theo SĐT / mã HĐ / ngày
- Hiển thị: SĐT trong header phiếu, giảm giá HĐ, PTTT
- Hỗ trợ HD / HDSC / HDD / APSC

### Module Hàng hóa
Bảng danh mục + detail card, highlight theo CN

### Module Chuyển hàng
Tạo/xác nhận/nhận/hủy/kết sổ, delta tồn kho

### Module Kiểm kê
Tạo phiếu đa nhóm, quét mã vạch, duyệt admin, xuất Excel KiotViet

### Module Sửa chữa ✅ Hoàn chỉnh
- **Trạng thái:** Đang sửa → Chờ linh kiện → Chờ giao khách → (Hoàn thành qua tab HĐ)
- **Mã:** SC000001 (search "1" → ra SC000001)
- **Tạo phiếu:** Auto-fill tên từ SĐT, tìm dịch vụ từ `hang_hoa`, in A5 ngay khi tạo
- **Tab Tạo HĐ sửa:** Chọn phiếu "Chờ giao khách" → điền giảm giá + PTTT → tạo APSC → phiếu → Hoàn thành
- **In phiếu:** A5 dọc, UTF-8 Blob URL, `window.print()`
- **PTTT:** Tiền mặt mặc định, checkbox chia nhiều PTTT, hiện dư/thiếu rõ ràng

### Module Khách hàng ✅
- Upload file KiotViet (upsert theo `sdt`)
- Danh sách + Chi tiết (lịch sử HĐ + SC)
- `lookup_khach_hang(sdt)` — helper dùng chung
- `_upsert_khach_hang(ten, sdt, chi_nhanh)` — auto-save khi tạo phiếu SC mới
- Mã nội bộ: `AKH000001`

### Module Nhập hàng ✅ Mới nhất
- **NCC:** Admin quản lý danh sách NCC (tab riêng)
- **Tạo phiếu:** Kế toán chọn NCC → tìm hàng (fuzzy) → nhập SL + giá vốn + giá bán → lưu nháp hoặc gửi chờ duyệt
- **Inline create:** Nếu mã chưa tồn tại → tạo mới ngay trong form
- **Cảnh báo giá:** Giá bán mới ≠ giá cũ → flag ⚠️ nhắc in tem
- **Workflow:** Nháp → Chờ xác nhận → Đã nhập kho
- **Xác nhận (admin):** Cộng SL vào `the_kho`, cập nhật `hang_hoa.gia_ban`, insert hàng mới
- **Hoàn tác (admin):** Trừ lại SL, chuyển sang Đã hủy
- **Phân quyền:** NV chỉ xem, kế toán tạo/sửa, admin xác nhận/hủy/hoàn tác

---

## 6. UPLOAD PIPELINE

| Upload | Xử lý |
|--------|-------|
| Thẻ kho | Delete-insert theo CN |
| Hóa đơn | Delete by mã HĐ + insert |
| Hàng hóa | Upsert theo `ma_hang` |
| Chuyển kho | Upsert |
| Khách hàng | Upsert theo `sdt` |

---

## 7. KNOWN ISSUES & TECH DEBT

| ID | Mô tả | Mức độ |
|----|-------|--------|
| DEBT-01 | 4 phiếu chuyển format cũ CH26... chưa migrate | Low |
| DEBT-02 | Upload chuyển hàng check column trước nunique | Low |
| WARN-01 | `use_container_width` deprecated → đổi thành `width=` sau 2025-12-31 | Medium |
| NOTE-01 | `hien_thi_dashboard()` orphan — giữ cho module Báo cáo | — |
| NOTE-02 | In phiếu trên iOS không hỗ trợ (window.open bị chặn) — by design, chỉ in laptop | — |

---

## 8. ROADMAP

```
✅ HOÀN THÀNH
├── Auth, Session, Navigation (st.pills)
├── Hóa đơn, Hàng hóa, Chuyển hàng, Kiểm kê
├── Sửa chữa (full workflow + APSC)
├── Khách hàng (upload + auto-fill)
└── Nhập hàng + NCC ← vừa xong

📋 TIẾP THEO
│
├── 1. In tem mã vạch (từ phiếu nhập hàng)
│   └── Gắn liền module nhập hàng, build ngay sau
│
├── 2. Module Báo cáo
│   ├── Doanh thu theo CN / thời gian / loại HĐ
│   ├── Tồn kho tổng hợp
│   └── Tái dụng hien_thi_dashboard()
│
├── 3. Module POS — App Streamlit riêng
│   │
│   ├── [ARCH] Cloud-to-LAN Print Spooler
│   │   ├── Bảng print_queue (Supabase)
│   │   │   └── id, chi_nhanh, payload(base64 ESC/POS),
│   │   │       status(pending/printing/done/error), created_at
│   │   ├── POS App (Streamlit Cloud)
│   │   │   └── Tạo HĐ → INSERT vào print_queue
│   │   ├── print_daemon.py (chạy local mỗi cửa hàng)
│   │   │   ├── Poll Supabase 1Hz
│   │   │   ├── Filter theo chi_nhanh (config.py)
│   │   │   └── TCP socket → máy in port 9100
│   │   └── config.py
│   │       ├── CHI_NHANH = "100 Lê Quý Đôn"
│   │       ├── PRINTER_IP = "192.168.x.x" (Static IP bắt buộc)
│   │       └── PRINTER_PORT = 9100
│   │
│   ├── Máy in: Xprinter XP-365B
│   │   ├── Kết nối: WiFi + LAN (TCP port 9100)
│   │   ├── Protocol: ESC/POS — Receipt mode
│   │   ├── Khổ: K80 (80mm, 48 ký tự/dòng)
│   │   └── ⚠️ Switch DIP sang Receipt mode trước khi dùng
│   │
│   ├── In điện thoại: data URI (Hướng 2) — iOS/Android/Win đều OK
│   ├── Đăng nhập PIN + bookmark URL 30 ngày
│   └── Bấm "Tạo HĐ" → in ngay, không qua bước trung gian
│
├── 4. Module Chấm công — App Streamlit riêng
│   ├── QR động chống gian lận
│   ├── Ghi nhận giờ vào/ra
│   └── Báo cáo công theo tháng
│
└── 5. Li dị KiotViet hoàn toàn
    ├── Bật cân bằng the_kho từ kiểm kê
    ├── Bỏ upload KiotViet
    └── Tồn kho tính động 100% nội bộ
```

---

## 9. QUYẾT ĐỊNH KIẾN TRÚC QUAN TRỌNG

| # | Quyết định | Lý do |
|---|-----------|-------|
| D1 | 1 DB duy nhất, phân biệt bằng cột `chi_nhanh` | Không tách DB theo chi nhánh |
| D2 | Kiểm kê xuất Excel → import KiotViet (Hướng A) | Giai đoạn song song KiotViet |
| D3 | POS là app Streamlit riêng, chung Supabase | Tách biệt UX mobile vs desktop |
| D4 | Nhập hàng cộng thẳng `the_kho` | Module chỉ dùng thật khi li dị KiotViet |
| D5 | Mã APSC (không phải HDSC) cho HĐ sửa chữa | Tránh trùng với KiotViet |
| D6 | Cloud-to-LAN print qua Supabase queue | Streamlit Cloud không kết nối LAN trực tiếp |
| D7 | Static IP cho máy in | DHCP reboot = mất kết nối TCP |

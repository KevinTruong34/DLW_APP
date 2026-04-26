# AI_CONTEXT.md — DL Watch Store App
> Cập nhật: 27/04/2026 — Bàn giao sau session phát triển

---

## 1. TỔNG QUAN DỰ ÁN

**App:** DL Watch Store — quản lý cửa hàng đồng hồ nội bộ  
**Stack:** Streamlit (Python, multi-file) + Supabase (PostgreSQL)  
**Deploy:** Streamlit Cloud  
**3 chi nhánh:** 100 Lê Quý Đôn · Coop Vũng Tàu · GO BÀ RỊA

---

## 2. CẤU TRÚC CODEBASE

```
app.py                        # Entry point, CSS, auth gate, navigation (st.pills)
utils/
  config.py                   # ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
  db.py                       # Supabase client, log_action(), tất cả load_* functions
  auth.py                     # Login, session, role helpers
  helpers.py                  # _normalize, _build_phieu_html, _in_phieu_sc
modules/
  tong_quan.py
  hoa_don.py
  hang_hoa.py
  sua_chua.py
  nhap_hang.py                # Nhập hàng NCC + Trả hàng NCC
  khach_hang.py
  kiem_ke.py
  chuyen_hang.py
  quan_tri.py
  bao_cao.py                  # Module báo cáo (mới)
```

---

## 3. DATABASE SCHEMA — CÁC BẢNG QUAN TRỌNG

### Bảng cốt lõi
| Bảng | Mô tả |
|------|-------|
| `hoa_don` | HĐ KiotViet upload + HĐ App (prefix APSC) |
| `hang_hoa` | Master hàng hóa, có cột `loai_sp` (Hàng hóa/Dịch vụ) |
| `the_kho` | Snapshot tồn kho hiện tại theo CN |
| `phieu_sua_chua` | Phiếu sửa chữa |
| `phieu_chuyen_kho` | Phiếu chuyển kho (IN_APP_MARKER = nội bộ App) |
| `phieu_kiem_ke` + `phieu_kiem_ke_chi_tiet` | Kiểm kê |
| `phieu_nhap_hang` + `phieu_nhap_hang_ct` | Nhập hàng NCC |
| `phieu_tra_hang` + `phieu_tra_hang_ct` | Trả hàng NCC ✅ đã tạo |
| `action_logs` | Log thao tác toàn app |
| `khach_hang` | Danh sách khách hàng |

### SQL đã chạy (không cần chạy lại)
```sql
-- Bảng trả hàng NCC
CREATE TABLE phieu_tra_hang (...);
CREATE TABLE phieu_tra_hang_ct (...);
ALTER TABLE phieu_tra_hang DISABLE ROW LEVEL SECURITY;
ALTER TABLE phieu_tra_hang_ct DISABLE ROW LEVEL SECURITY;

-- RPC đánh số phiếu trả hàng
CREATE FUNCTION get_next_th_num() ...;

-- Action logs
CREATE TABLE action_logs (
  id uuid DEFAULT gen_random_uuid(),
  created_at timestamptz DEFAULT now(),
  username text, ho_ten text, chi_nhanh text,
  action text, detail text, level text
);
ALTER TABLE action_logs DISABLE ROW LEVEL SECURITY;

-- Cột loai_sp vào hang_hoa
ALTER TABLE hang_hoa ADD COLUMN loai_sp text;
```

> **Lưu ý RLS:** Tất cả bảng nội bộ App dùng service key → DISABLE RLS.

---

## 4. PHÂN QUYỀN

| Role | Quyền |
|------|-------|
| `nhan_vien` | Xem CN mình, tạo phiếu SC, tạo phiếu nhập/trả (nháp) |
| `ke_toan` | Tất cả CN, xem báo cáo XNT, tạo phiếu nhập/trả |
| `admin` | Toàn quyền — xác nhận/hoàn tác mọi phiếu |

---

## 5. CÁC MODULE ĐÃ HOÀN CHỈNH

### `modules/nhap_hang.py` — Nhập/Trả hàng NCC
- **2 tab chính:** 📦 Nhập hàng / ↩️ Trả hàng NCC + 🏭 Nhà cung cấp (admin)
- **Mỗi tab:** Danh sách / Tạo phiếu / Chi tiết·Duyệt
- **Workflow trả hàng:** Nháp → Chờ xác nhận → Đã trả hàng
- Xác nhận trả → trừ tồn `the_kho`; Hoàn tác → cộng lại
- Phân quyền: ke_toan + admin tạo; chỉ admin xác nhận/hoàn tác

### `modules/bao_cao.py` — Báo cáo ✅ hoàn chỉnh
**Hằng số:** `APP_INVOICE_PREFIXES = ["APSC"]` — thêm prefix khi có POS

**Cấu trúc tab theo role:**
- `nhan_vien`: Tab Doanh thu → Cuối ngày only
- `ke_toan/admin`: Tab Doanh thu (3 sub) + Tab Xuất nhập tồn (2 sub)
- `admin`: thêm Tab Nhân viên

**Tab Doanh thu:**
- *Cuối ngày*: metrics hôm nay vs hôm qua (delta %), phiếu SC hôm nay, phiếu SC cần lưu ý (>5 ngày sửa / >14 ngày chờ giao), danh sách HĐ
- *Tổng quan*: chart doanh thu theo ngày/CN, bảng theo CN
- *Bán hàng theo nhóm*: group theo loai_sp / loai_hang / thuong_hieu

**Tab Xuất nhập tồn:**
- *Tổng hợp*: bảng nhập kho + xuất kho từ tất cả nguồn, tồn đầu/cuối kỳ (tính ngược)
- *Tra cứu mã hàng*: tìm mã → chọn CN + khoảng ngày → lịch sử phát sinh running balance (5 nguồn: Bán hàng / Nhập NCC / Trả NCC / Chuyển hàng / Kiểm kê) + 4 metrics

**Tab Nhân viên** (admin): doanh thu APSC theo Người tạo + Người bán

**Load functions quan trọng trong bao_cao.py:**
- `_load_hd`, `_load_sc_phieu`, `_load_sc_can_luu_y` — hoa_don + SC
- `_load_nhap_hang`, `_load_tra_hang` — nhập/trả NCC
- `_load_chuyen_hang`, `_load_kiem_ke` — chuyển kho + kiểm kê
- Tất cả: `@st.cache_data(ttl=300)`, pagination với `.order()`, filter ngày sau load

**Lưu ý `_load_tra_hang`:** đã uncomment và active (bảng `phieu_tra_hang` đã tồn tại).

### `modules/hoa_don.py`
- Fix `_render_recent`: thêm reorder sau `.isin()` để 6 HĐ gần nhất đúng thứ tự mới nhất lên đầu
```python
order = {ma: i for i, ma in enumerate(recent_codes)}
res = res.assign(_order=res["Mã hóa đơn"].map(order)) \
         .sort_values("_order").drop(columns="_order")
```

### `modules/quan_tri.py`
- Cột `"Loại hàng": "loai_sp"` trong `col_map` upload Hàng hóa master
- Tab "Logs" (tab thứ 5): filter ngày/user/action, hiện 500 logs gần nhất có màu level

### `utils/db.py` — log_action()
```python
def log_action(action, detail="", level="info"):
    # Ghi logger như cũ
    # THÊM: lưu vào action_logs
    try:
        supabase.table("action_logs").insert({
            "username": ..., "ho_ten": ..., "chi_nhanh": ...,
            "action": action, "detail": detail, "level": level
        }).execute()
    except Exception:
        pass
```

### `app.py`
- Menu: `"📊 Báo cáo"`, `"📥 Nhập/Trả hàng"`
- Import + routing cho `module_bao_cao()` và `module_nhap_hang()`

---

## 6. KỸ THUẬT QUAN TRỌNG — GHI NHỚ

| # | Vấn đề | Giải pháp |
|---|---------|-----------|
| T1 | GROUP BY mã HĐ bị nhân đôi | `drop_duplicates(["Mã hóa đơn"])` trước khi SUM |
| T2 | Pagination Supabase | Mọi query phải có `.order()` + loop range |
| T3 | Giờ VN | `pd.Timestamp.now(tz="Asia/Ho_Chi_Minh")` |
| T4 | loai_sp NULL | `_filter_chi_hang_hoa()` fallback giữ nguyên nếu không có master |
| T5 | Tồn đầu kỳ | Tính ngược: `cuối - nhập + xuất` — chấp nhận ước tính, caveat rõ trong UI |
| T6 | Tab ẩn theo role | Build list tab có điều kiện, không dùng `st.info("không có quyền")` |
| T7 | `.isin()` không giữ thứ tự | Sau `.isin()` phải reorder thủ công nếu cần thứ tự |

---

## 7. QUYẾT ĐỊNH KIẾN TRÚC

| # | Quyết định | Lý do |
|---|-----------|-------|
| D1 | Thẻ kho chi tiết làm sau | Không có lịch sử cũ → tồn đầu kỳ sai |
| D2 | Tra cứu mã hàng thay thẻ kho | Đủ đáp ứng nhu cầu truy vết |
| D3 | loai_sp từ cột "Loại hàng" KiotViet | Phân biệt HH/DV cho XNT |
| D4 | log_action() duy nhất ghi DB | Không sửa call sites, chỉ sửa 1 hàm |
| D5 | APP_INVOICE_PREFIXES = ["APSC"] | Dễ mở rộng khi có POS |

---

## 8. ROADMAP

### ✅ Hoàn thành
- Module Nhập/Trả hàng NCC
- Module Báo cáo (đầy đủ 3 tab, 7 sub-tab)
- Action logs lưu DB
- Cột `loai_sp` + upload master
- Fix thứ tự 6 HĐ gần nhất

### 📋 Tiếp theo
```
1. Li dị KiotViet hoàn toàn
   ├── Bật cân bằng the_kho từ kiểm kê (hiện đang tắt)
   └── Tồn kho tính động 100% nội bộ

2. Module POS (App Streamlit riêng)
   ├── Tạo HĐ bán hàng trực tiếp
   └── Khi xong: thêm prefix vào APP_INVOICE_PREFIXES

3. Module Chấm công (App Streamlit riêng)
```

---

## 9. QUY TẮC LÀM VIỆC VỚI AI

- Tuân theo `CLAUDE.md`: Think Before Coding · Simplicity First · Surgical Changes · Goal-Driven
- **Luôn đọc file thực tế** trước khi sửa — không làm việc trên file cũ trong context
- Khi user upload file mới → đó là source of truth, ghi đè lên bất kỳ version nào đang có
- Hỏi trước khi implement nếu có nhiều cách giải quyết
- Không thêm tính năng ngoài yêu cầu

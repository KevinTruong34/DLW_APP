# Handoff: `hoa_don.py` UI redesign

> **Mục tiêu**: thay UI module Hoá đơn (Streamlit) bằng design **Master-Detail Rail** đã chốt. Giữ NGUYÊN 100% logic Supabase, prefix detection, build pipeline. Chỉ thay đổi cách trình bày + cách lọc.

---

## 1. Tóm tắt thay đổi

| Thay đổi | Cũ | Mới |
|---|---|---|
| **Sub-tabs** | 3 sub-tab `st.tabs(["SĐT","Mã HĐ","Ngày tháng"])` | 1 ô **smart search** tự nhận diện (số→SĐT/Mã, chữ→tên) + date popover + 3 selectbox lọc (NV/PTTT/Loại) + 1 segmented status |
| **Render HĐ** | Mỗi HĐ = 1 `st.expander` full-width, expanded=True, scroll dọc nhiều | Master-detail 60/40: list trái card 2-dòng/HĐ, rail phải sticky hiện chi tiết |
| **Stats** | Không có | (Tuỳ chọn) strip KPI hôm nay — **TẮT mặc định** theo yêu cầu user |
| **Info inline trên list** | Phải expand mới thấy NV, PTTT, số mặt hàng | Card 2-dòng hiện: Mã · Giờ · Loại · Status / KH · NV · #SP · PTTT · Tổng |
| **Phiếu sửa chữa liên đới** | Không hiện | Khối "Phiếu sửa chữa liên đới" trong rail cho HĐ APSC (quan hệ **1:1** qua `hoa_don."Mã YCSC"` → `phieu_sua_chua.ma_phieu`): mã PSC, ngày nhận, hẹn trả, sản phẩm/hiệu, trạng thái (badge có màu), KTV |
| **Khách quay lại** | Không có | Badge `↻` vàng nếu KH match ≥2 HĐ |

---

## 2. Nguyên tắc bất biến (KHÔNG đổi)

### Logic Python
- Hàm `module_hoa_don()` vẫn là entry point.
- `load_hoa_don_unified(branches_key=load_cns)` — không đổi cách load.
- Helper `_is_pdt_hd / _is_pos_hd / _is_apsc_hd` — giữ nguyên.
- Phân quyền `is_admin() / is_ke_toan_or_admin() / get_active_branch() / get_accessible_branches()` — không đổi.
- Cột data: `Mã hóa đơn, Mã YCSC, Thời gian, Tên khách hàng, Điện thoại, Trạng thái, Tổng tiền hàng, Giảm giá hóa đơn, Khách đã trả, Tiền cọc, _pdt_chenh_lech, _pdt_kieu, _pdt_loai, _pdt_ma_hd_goc, Tiền mặt, Thẻ, Ví, Chuyển khoản, Cọc tiền mặt, Cọc chuyển khoản, Cọc thẻ, _ngay, _date, Mã hàng, Tên hàng, Số lượng, Đơn giá, Thành tiền, Ghi chú hàng hóa` — tất cả vẫn dùng.
- Cột "Người bán" với fallback `["Người bán","Nhân viên bán","Người tạo","Nhân viên"]` — giữ nguyên.
- **KHÔNG có schema migration**. Bảng `phieu_sua_chua` giữ nguyên columns hiện tại.

### Streamlit ràng buộc (từ STREAMLIT_DESIGN_RULES.md)
- ❌ KHÔNG dùng pattern `st.html('<div class="x">') + widget + st.html('</div>')` để wrap widget.
- ✅ Wrap widget bằng `st.container(border=True)`.
- ❌ KHÔNG dùng global CSS class cho element bên trong `st.html()` — strip mất.
- ✅ Mọi style cho HTML do `st.html()` render PHẢI inline `style="..."` trên chính element đó.
- ✅ CSS file (`static/hoa_don.css`) chỉ chứa: font import, design tokens (reference), Streamlit native widget overrides qua `[data-testid="..."]`.

---

## 3. Files trong gói

| File | Vai trò | Đích |
|---|---|---|
| `README.md` | (file này) — tổng quan, tokens, spec |  |
| `IMPLEMENTATION_GUIDE.md` | Patch trước/sau từng đoạn `hoa_don.py` + `utils/db.py` |  |
| `reference_hifi.html` | Mock V2 + tham chiếu V1/V3 (mở browser xem) |  |
| `hoa_don.css` | CSS production — chỉ Streamlit overrides + font + tokens | `static/hoa_don.css` |
| `utils_hd_style.py` | Python helpers: `inject_hoa_don_css()`, `list_card_html()`, `detail_rail_html()`, `smart_search_predicate()`, etc. | `utils/hd_style.py` |

`hd-*.jsx` + `design-canvas.jsx` + `tweaks-panel.jsx` là source của `reference_hifi.html` — không copy vào repo production.

---

## 4. Cấu trúc file trong codebase sau khi áp dụng

```
DLW_APP/
├─ modules/
│  └─ hoa_don.py          ← refactor (giữ logic, thay layout)
├─ utils/
│  ├─ hh_style.py         ← (đã có, không đổi)
│  ├─ hd_style.py         ← NEW (từ utils_hd_style.py)
│  └─ db.py               ← thêm load_psc_for_apsc() (xem IMPLEMENTATION_GUIDE.md section 4)
└─ static/
   ├─ hang_hoa.css        ← (đã có, không đổi)
   └─ hoa_don.css         ← NEW (từ hoa_don.css)
```

---

## 5. Spec màn hình (Master-Detail Rail)

### 5.1 Branch row (luôn hiện)
Y hệt code cũ — `st.selectbox("Chi nhánh:", ["Tất cả"] + accessible)` cho kế toán/admin có >1 CN; caption `📍 {active}` cho nhân viên. Không đổi.

### 5.2 Title row
```
H1: "Hoá đơn · Thứ Sáu 15/05/2026"        |   "11 chứng từ"
```
Hai cột `st.columns([3,1])` — left dùng `st.html()` cho `<h2>`, right dùng `st.caption()`.

### 5.3 Filter container (thay 3 sub-tab cũ)

Trong `st.container(border=True)`:

**Row A** — `st.columns([3, 1, 1, 1, 1])`:
1. `st.text_input("", placeholder="Tìm mã HĐ, số điện thoại, tên khách… (số→SĐT, chữ→tên)")` — phím tắt `/` hiển thị qua placeholder
2. `st.popover("📅 Hôm nay · 15/05")` chứa 2 `st.date_input` Từ/Đến + checkbox "Hôm nay/Hôm qua/Tuần này"
3. `st.selectbox("NV:", ["Tất cả NV"] + ds_nv)` — label_visibility="collapsed", lấy distinct từ cột Người bán
4. `st.selectbox("PTTT:", ["Tất cả PTTT", "Tiền mặt", "CK", "Thẻ", "Ví"])` — match khi cột tương ứng > 0
5. `st.selectbox("Loại:", ["Tất cả loại", "POS", "Đổi/Trả", "Sửa chữa", "KiotViet"])`

**Row B** — `st.radio("Trạng thái", options, horizontal=True, label_visibility="collapsed")`:
- "Tất cả (N)", "● Hoàn thành (N)", "✕ Đã hủy (N)", "↔ Đổi/Trả (N)", "🔧 Sửa chữa (N)"
- CSS đã override `stRadio[role=radiogroup]` thành segmented look — không phải dot.

### 5.4 Master-Detail grid

`st.columns([6, 4], gap="medium")`:

#### Left (cột 6) — List
- Mỗi HĐ render 2 widgets:
  1. `st.html(list_card_html(inv, selected=inv['Mã hóa đơn']==selected))` — chrome card có inline styles
  2. `st.button("Xem chi tiết →", key=f"hd_open_{ma}", use_container_width=True)` ngay dưới card
- Khi click: `st.session_state["hd_sel_ma"] = ma; st.rerun()`
- **Phase 1**: dùng nút "Xem chi tiết" hiển thị bình thường dưới card (chiếm 1 dòng nhưng không vi phạm rule wrap). Phase 2 có thể thay bằng JS postMessage qua `components.v1.html` nếu cần.

#### Right (cột 4) — Rail
- Sticky qua CSS `[data-testid="column"]:nth-child(2) { position: sticky; top: 60px }` — chỉ apply trong `.hd-scope`.
- Nội dung phụ thuộc `st.session_state.get("hd_sel_ma")`:
  - Có chọn → `st.html(detail_rail_html(inv))` + bên dưới là cụm `st.columns(3)` chứa 3 nút primary `🖨 In lại / ⎘ Sao chép / ⤴ Phiếu kho`
  - Không chọn → `st.html(empty_rail_html())`

### 5.5 APSC — Phiếu sửa chữa liên đới (**quan hệ 1:1**)

**Yêu cầu của user.** Khi `_is_apsc_hd(ma)` và HĐ có cột `"Mã YCSC"` match được 1 record trong bảng `phieu_sua_chua` (qua `ma_phieu`), hiện block hổ phách trong rail giữa "Khách đã trả" và "Dịch vụ sửa chữa":

```
┌──────────────────────────────────────────────────────────┐
│ PHIẾU SỬA CHỮA LIÊN ĐỚI                                  │
├──────────────────────────────────────────────────────────┤
│ 🔧 PSC000125                       [Đã giao khách]       │
│ Vòng trầm hương 14 ly                                    │
│ Nhận: 12/05/2026 · Hẹn trả: 15/05/2026 · KTV: Thụ An     │
└──────────────────────────────────────────────────────────┘
```

**Quan hệ trong schema**: `hoa_don."Mã YCSC"` lưu mã phiếu sửa chữa. 1 HĐ APSC link tới **đúng 1** phiếu PSC (1:1). Liên kết là chuỗi text match đơn giản — không cần FK constraint.

**Source dữ liệu**: dùng helper `load_psc_for_apsc(ma_ycsc)` trong `utils/db.py` (xem `IMPLEMENTATION_GUIDE.md` section 4). Trả về **dict | None** (KHÔNG phải list):

```python
{
    "ma":         "PSC000125",          # từ ma_phieu
    "san_pham":   "Vòng trầm hương",    # từ hieu_dong_ho (fallback loai_yeu_cau, mo_ta_loi)
    "ngay_nhan":  "12/05/2026",         # từ created_at (format DD/MM/YYYY)
    "ngay_tra":   "15/05/2026",         # từ ngay_hen_tra
    "tinh_trang": "Đã giao khách",      # từ trang_thai
    "kt_vien":    "Thụ An",             # từ nguoi_tiep_nhan
}
```

**Badge trạng thái có màu**:
- "Đã giao khách" / "Hoàn thành" → xanh
- "Đang sửa" / "Chờ ..." → vàng amber
- "Đã hủy" → đỏ
- Khác → xám

Trong card list (cột trái), HĐ APSC có liên kết PSC sẽ hiện thêm badge `🔗 PSC` (không count, vì 1:1) cạnh badge `🔧 Sửa chữa`.

Nếu `"Mã YCSC"` rỗng hoặc không match → block không hiện, badge không có (graceful degrade).

### 5.6 Empty/Recent state
Khi search rỗng và filter không hoạt động (Phase 1): vẫn hiển thị toàn bộ HĐ (không cần "recent 6" như cũ — list trái đã thay thế chức năng đó). Sort mặc định: thời gian giảm dần.

Khi search có kết quả 0: rail trống + caption đỏ `🔍 Không tìm thấy chứng từ phù hợp` trong cột list.

---

## 6. Design Tokens (mirror trong `utils/hd_style.py:TOK` + `static/hoa_don.css`)

| Token | Hex | Dùng cho |
|---|---|---|
| `--hd-bg` | `#f7f7f8` | Body |
| `--hd-surface` | `#ffffff` | Card |
| `--hd-surface-2` | `#fafafa` | Hover, table head |
| `--hd-border` | `#e7e7ea` | Border default |
| `--hd-ink` | `#18181b` | Text primary |
| `--hd-ink-3` | `#71717a` | Text muted, label |
| `--hd-accent` | `#e63946` | Brand red, selected row, primary button |
| `--hd-accent-soft` | `#fdecee` | Selected card bg |
| `--hd-good` | `#1a7f37` | Hoàn thành, +chênh lệch, PSC "Đã giao" badge |
| `--hd-warn` | `#cf4c2c` | Đã hủy, giảm giá, -chênh lệch |
| `--hd-info` | `#2563eb` | POS badge, CK pill |
| `--hd-purple` | `#7c3aed` | Đổi/Trả badge, Ví pill |
| `--hd-amber` | `#b45309` | **Sửa chữa badge, PSC block** |
| `--hd-amber-soft` | `#fef3c7` | PSC card bg |

### Typography
| Use | Font | Size | Weight |
|---|---|---|---|
| H1 module | Be Vietnam Pro | 22px | 600 |
| Card primary | Be Vietnam Pro | 13px | 500 |
| Caption | Be Vietnam Pro | 12.5px | 400 |
| Label uppercase | Be Vietnam Pro | 11px | 600 |
| Mã HĐ / Mã PSC / SĐT / số tiền | JetBrains Mono | 12–13.5px | 500–600 |

---

## 7. State Management

| Key | Type | Set khi | Đọc ở đâu |
|---|---|---|---|
| `hd_sel_ma` | str/None | User click 1 dòng trong list | Detail rail render |
| `hd_search` | str | text_input (managed by widget key) | Filter pipeline |
| `hd_filter_nv` | str | selectbox NV | Filter pipeline |
| `hd_filter_pttt` | str | selectbox PTTT | Filter pipeline |
| `hd_filter_loai` | str | selectbox Loại | Filter pipeline |
| `hd_filter_status` | str | radio Status | Filter pipeline |
| `hd_date_from` | date | date_input | Filter pipeline |
| `hd_date_to` | date | date_input | Filter pipeline |
| `hd_cn` | str | selectbox Chi nhánh (đã có) | `load_cns` |

State cũ `in_phone / in_inv / in_date_from / in_date_to / in_date_active / so_dong_trung` có thể xóa hoặc giữ làm backup. Trong Phase 1 IMPLEMENTATION_GUIDE chỉ thêm key mới, không động state cũ.

---

## 8. Acceptance criteria

- [ ] Trang Hoá đơn 1440×900 không scroll dọc khi không có dòng chọn.
- [ ] Search "0912" → match SĐT chứa "0912" hoặc Mã HĐ kết thúc "0912".
- [ ] Search "Mai" → match khách hàng tên có "mai".
- [ ] Search "AHD000165" → exact match HĐ.
- [ ] Click 1 dòng → detail rail xuất hiện, cuộn list không mất rail.
- [ ] Click HĐ APSC có "Mã YCSC" match `phieu_sua_chua.ma_phieu` → rail hiện block PSC 1 card với đủ 6 fields (mã PSC, sản phẩm/hiệu, ngày nhận DD/MM/YYYY, hẹn trả, trạng thái có badge màu, KTV).
- [ ] HĐ POS, Đổi/Trả, KiotViet → KHÔNG hiện block PSC.
- [ ] HĐ APSC mà "Mã YCSC" rỗng hoặc không match → KHÔNG hiện block PSC, KHÔNG crash.
- [ ] HĐ Đổi/Trả → rail hiện 2 bảng "Khách trả lại" (đỏ) + "Khách mua mới" (xanh).
- [ ] HĐ đã hủy → list hiện gạch ngang số tiền, status badge đỏ.
- [ ] Status filter Tất cả/Hoàn thành/Hủy/Đổi-Trả/Sửa lọc đúng.
- [ ] Resize ≤1100px → grid collapse 1 cột (rail xuống dưới list).
- [ ] Logic Supabase + cache hoạt động như cũ (verify bằng cách thêm HĐ test trên POS → quay lại module hoa_don thấy ngay sau cache TTL).

---

## 9. Triển khai

Đọc tiếp **`IMPLEMENTATION_GUIDE.md`** để có:
- Patch trước/sau cho từng đoạn `hoa_don.py` (phép thay thế tối thiểu)
- Cách thêm `load_psc_for_apsc()` vào `utils/db.py` (KHÔNG cần schema migration)
- Checklist chia 3 PR
- Test thủ công từng state

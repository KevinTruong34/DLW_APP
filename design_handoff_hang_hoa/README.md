# Handoff: `hang_hoa.py` UI redesign

> **Mục tiêu**: thay UI hiện tại của module Hàng hóa (Streamlit) bằng design "Hướng A — Sticky toolbar + Right rail" đã được chốt. Giữ nguyên 100% logic hoạt động; **chỉ thay đổi cách trình bày**.

---

## 1. Về các file thiết kế trong gói này

Các file HTML trong gói này là **tài liệu tham chiếu thiết kế** (design references). Chúng không phải code production để copy-paste nguyên xi vào app — chúng là prototype mô tả chính xác diện mạo, bố cục và hành vi mong muốn.

**Nhiệm vụ**: tái dựng các thiết kế này **trong codebase Streamlit hiện có** (`DLW_APP`), sử dụng pattern và utility đã có sẵn (`st.columns`, `st.dataframe`, `st.popover`, `st.dialog`, v.v.) cộng thêm CSS injection (`st.markdown(unsafe_allow_html=True)`) cho phần chrome. **Không viết lại module sang framework khác**.

## 2. Fidelity

**Hi-fi (pixel-perfect)**. Toàn bộ màu, typography, spacing, border-radius, shadow, animation đã được chốt. Implementation cần khớp:

- Kích thước trong khoảng ±2px so với mock
- Font: `Be Vietnam Pro` cho UI, `JetBrains Mono` cho mã hàng / mã vạch / giá
- Màu: dùng đúng các token CSS trong `hang_hoa.css` (đừng tự đoán hex)
- Tương tác: hover, focus, expand/collapse animation khớp với CSS đã cung cấp

## 3. Phạm vi & nguyên tắc bất biến

### ✅ Thay đổi (UI/UX only)
- Bố cục: toolbar dày đặc 1 dòng + grid master-detail 60/40
- Visual: card, chip, button, table — refactor sang style `.hh-*`
- "Thêm hàng hóa mới" chuyển từ `st.expander` sang `@st.dialog` (modal)
- "Chỉnh tồn kho", "Sửa thông tin", "Ẩn hàng hóa" gom trong **detail rail bên phải** (sticky)
- "In tem mã vạch" hiển thị như **FAB nổi** khi multi-select; như button to dưới detail card khi single-select

### ❌ KHÔNG được đổi (logic bất biến)
- Hàm `module_hang_hoa()` và signature các hàm con (`_render_them_moi`, `_render_sua_hang_hoa`, `_render_an_hang_hoa`, `_dlg_in_tem_hh`, `_render_dialog_in_tem`, `_trigger_print_window`).
- Các thao tác Supabase: `supabase.table("hang_hoa").insert/update`, `supabase.table("the_kho").update/insert`, `log_action(...)`, `st.cache_data.clear()`.
- Khóa session_state: `hh_ma_chon`, `hh_search_cnt`, `hh_cha`, `hh_con`, `hh_them_cnt`, `hh_cn`, `hh_table`, `_hh_in_tem_items`, `hh_sua_cnt_<ma>`, `hh_an_confirm_<ma>`, `_intem_hh_qty`, `adj_ton_<ma>_<cn>`.
- Pipeline build `df` (merge master + the_kho, normalize, filter, sort).
- Phân quyền: `is_admin()`, `is_ke_toan_or_admin()`, `get_active_branch()`, `get_accessible_branches()`.
- Tính toán tồn kho theo chi nhánh (`branch_tons`, `branch_kho_ids`).
- Luồng "In tem mã vạch": vẫn dùng `@st.dialog` + `build_label_html` + `_trigger_print_window` qua Blob URL.

## 4. Files trong gói này

| File | Vai trò |
|---|---|
| `README.md` | (file này) — tổng quan, design tokens, screen spec |
| `IMPLEMENTATION_GUIDE.md` | Hướng dẫn code chi tiết: ánh xạ từng widget Streamlit ↔ class CSS, kèm patch trước/sau cho `hang_hoa.py` |
| `reference_hifi.html` | **Mock hi-fi đầy đủ 5 trạng thái** (empty / single / multi / admin / add-modal). Mở trong browser, dùng panel tweaks góc phải để xem các state |
| `wireframes_exploration.html` | (tham khảo) 4 hướng wireframe ban đầu — chọn Hướng A |
| `hang_hoa.css` | **CSS production**, copy thẳng vào `static/hang_hoa.css` |
| `utils_hh_style.py` | Helper Python: `inject_hang_hoa_css()`, `hh_html()`, và builder cho card/stock-tiles/empty/FAB. Copy vào `utils/hh_style.py` |

## 5. Cấu trúc file trong codebase sau khi áp dụng

```
DLW_APP/
├─ modules/
│  └─ hang_hoa.py          ← refactor (giữ logic, thay layout)
├─ utils/
│  └─ hh_style.py          ← NEW (từ utils_hh_style.py)
└─ static/
   └─ hang_hoa.css         ← NEW (từ hang_hoa.css)
```

---

## 6. Screens / Trạng thái

Tham chiếu `reference_hifi.html` để xem trực quan.

### 6.1 Toolbar (luôn hiển thị, sticky đầu trang)

| Slot | Widget Streamlit | Class | Ghi chú |
|---|---|---|---|
| Branch chips | `st.multiselect` (custom render) | `.hh-branches > .hh-chip` | Chỉ hiện nếu user là kế toán/admin VÀ có ≥2 chi nhánh accessible. Active chip màu đỏ, các chip khác xám nhạt. |
| Search | `st.text_input(placeholder=...)` | `.hh-search` | Placeholder: "Tìm mã hàng, mã vạch hoặc tên…". Phím tắt hint `/` ở góc phải (kbd). |
| Lọc | `st.popover("⊟ Lọc")` | `.hh-btn` | Bên trong popover: 2 selectbox (Nhóm hàng + Nhóm con). |
| Thêm hàng | `st.button("+ Thêm hàng", type="primary")` | `.hh-btn.primary` | **Chỉ admin**. Click → mở `@st.dialog` |

**Sticky**: dùng `position:sticky; top:0` trên `.hh-toolbar` (đã có sẵn trong CSS).

### 6.2 Caption row

`<b>{N}</b> sản phẩm · {Chi nhánh} · [chip lọc]    |    Sắp xếp: <b>Tồn ↓</b>`

Render bằng `render_caption(total, branches, filter_label, sort_label)`.

### 6.3 Master-detail grid (60/40)

Implement bằng `st.columns([6, 4])`. Override `display:grid` CSS không khả thi với `st.columns` đã được Streamlit set inline-style — thay vào đó **chấp nhận st.columns với gap mặc định** và chỉ override màu/spacing nội bộ.

#### Left (cột 6): Bảng dữ liệu
- Dùng `st.dataframe(...)` (đã có sẵn ở code cũ — giữ nguyên `selection_mode="multi-row"`).
- Cột: Tên hàng (medium) · Mã hàng (medium) · Mã vạch (medium) · Tồn (small, format `%d`).
- Header `text-transform:uppercase; font-size:11.5px`.
- Selected row: background `#fdecee`, viền trái 3px đỏ.
- Override qua selector `[data-testid="stDataFrame"]` trong CSS đã cung cấp.
- Hint row dưới bảng: text muted "↑ Chọn 1 dòng để xem chi tiết · chọn nhiều dòng để in tem hàng loạt".

#### Right (cột 4): Detail rail (`position:sticky; top:60px`)

3 trạng thái — switch bằng `len(sel)` và `st.session_state["hh_ma_chon"]`:

**A. Empty** — chưa chọn:
> Render `render_empty_rail()`. Icon list + heading "Chưa chọn hàng hóa" + paragraph hint.

**B. Single (`ma_chon` set, `len(sel) <= 1`)**:
> Render detail card:
> - Header: tên + breadcrumb `LOẠI › THƯƠNG HIỆU` + nút close (`✕` — clear `hh_ma_chon`)
> - Body: mã pill + mã vạch · `<dl>` meta (Thương hiệu / Loại SP / Bảo hành) · price box · "Tồn kho 3 chi nhánh" + 3 tile (chi nhánh hiện hành màu đỏ)
> - **Admin only**: `<details class="hh-collapse">` "Chỉnh tồn kho" (3 number_input + nút Lưu) + 2 nút "Sửa thông tin" (full width) và icon-only "Ẩn" (đỏ)
> - Dưới card: nút primary full-width "🏷 In tem mã vạch" (gọi `_dlg_in_tem_hh()` với 1 item)

**C. Multi (`len(sel) >= 2`)**:
> Render queue card:
> - Header "Đã chọn N sản phẩm" + close (✕ = clear selection)
> - `<ul>` liệt kê 4 dòng đầu (max-height 280px, scroll)
> - Footer: "Tổng số tem: N" + badge `CODE128`
> - Dưới card: nút primary "🏷 In N tem mã vạch"
> - **Đồng thời** render FAB ở dưới cùng màn hình (xem 6.4)

### 6.4 FAB (Floating Action Bar) — khi multi-select

`position:fixed; bottom:18px; left:50%; transform:translateX(-50%)`. Background đen, pill shape, animation fade-up 180ms.

Nội dung: `Đã chọn | [N SP] | 🏷 In tem | Bỏ chọn`

⚠️ **Streamlit caveat**: `st.button` không thể đặt vào `position:fixed` qua CSS riêng. Cách làm:
1. Render HTML `.hh-fab-wrap` chỉ là chrome trang trí (không có click handler).
2. Đặt 2 `st.button` thật ("In tem", "Bỏ chọn") ngay sau đó.
3. Dùng selector CSS `[data-testid="stVerticalBlock"]:has(> div > .hh-fab-wrap)` để bọc cả phần đó vào position:fixed (hacky nhưng OK).
4. **Hoặc đơn giản hơn**: chấp nhận FAB ở dạng inline tại đáy detail rail. Phiên bản tối giản này vẫn đẹp.

→ Khuyến nghị: **Phase 1** dùng nút inline trong detail rail (đã có). **Phase 2** mới làm FAB nổi nếu cần.

### 6.5 Modal "Thêm hàng hóa mới" — admin only

Dùng `@st.dialog("➕ Thêm hàng hóa mới", width="large")`. Bên trong dùng `st.columns(2)` cho form 2-cột:

| Cột trái | Cột phải |
|---|---|
| Mã hàng * | Loại sản phẩm (radio: Hàng hóa / Dịch vụ) |
| Tên hàng * | Loại hàng (selectbox) |
| Mã vạch | Thương hiệu (selectbox) |
| Giá bán | Bảo hành |

Footer (full width): nút primary "➕ Thêm hàng hóa". Disabled khi `not (ma.strip() and ten.strip())`.

Toàn bộ logic insert/check trùng/log_action **giữ nguyên** từ `_render_them_moi()`.

---

## 7. Design Tokens (CSS variables)

| Token | Hex | Dùng cho |
|---|---|---|
| `--hh-bg` | `#f7f7f8` | Body background |
| `--hh-surface` | `#ffffff` | Card, input, button background |
| `--hh-surface-2` | `#fafafa` | Hover / muted background, table header |
| `--hh-border` | `#e7e7ea` | Border default |
| `--hh-border-2` | `#d8d8dc` | Border hover, checkbox idle |
| `--hh-ink` | `#18181b` | Text primary, button text |
| `--hh-ink-2` | `#3f3f46` | Text secondary |
| `--hh-ink-3` | `#71717a` | Text muted, label |
| `--hh-ink-4` | `#a1a1aa` | Placeholder, icon idle |
| `--hh-accent` | `#e63946` | Brand red — primary button, active chip, selected row |
| `--hh-accent-d` | `#c1121f` | Hover của accent |
| `--hh-accent-soft` | `#fdecee` | Selected row bg, current branch tile bg |
| `--hh-good` | `#1a7f37` | Tồn kho > 5 |
| `--hh-warn` | `#cf4c2c` | Tồn kho 1–5, danger button |
| `--hh-zero` | `#a1a1aa` | Tồn kho = 0 |

### Spacing scale
| Token | px | Dùng cho |
|---|---|---|
| Gap nhỏ | 4 / 6 / 8 | Trong toolbar, chip group, stock tiles |
| Gap trung | 10 / 12 | Padding card body, gap section |
| Gap lớn | 14 / 16 / 18 | Grid gap, padding card head |

### Border radius
| Token | px | Dùng cho |
|---|---|---|
| `--hh-radius-sm` | 6 | Button, input, small card |
| `--hh-radius` | 10 | Card lớn, toolbar |
| 999 | — | Chip, FAB pill |
| 14 | — | Modal |

### Typography scale

| Use | Family | Size | Weight | Letter-spacing |
|---|---|---|---|---|
| H1 module | Be Vietnam Pro | 24px | 600 | -.2px |
| Card title h3 | Be Vietnam Pro | 17px | 600 | -.1px |
| Body | Be Vietnam Pro | 13px | 400 | 0 |
| Caption / hint | Be Vietnam Pro | 12.5px | 400 | 0 |
| Label uppercase | Be Vietnam Pro | 11px | 600 | .5px |
| Mã hàng / vạch | JetBrains Mono | 12px | 500 | 0 |
| Stock value | JetBrains Mono | 18px | 600 | -.3px |
| Price | JetBrains Mono | 18px | 600 | -.3px |

### Shadows
- `--hh-shadow-sm`: `0 1px 2px rgba(24,24,27,.04), 0 0 0 1px var(--hh-border)` — cards, inputs
- `--hh-shadow-md`: `0 4px 14px -2px rgba(24,24,27,.08), 0 0 0 1px var(--hh-border)` — popover, modal
- FAB: `0 12px 28px -8px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.06) inset` — chỉ FAB

---

## 8. Behaviors & Interactions

### Hover states
- Buttons: bg → `var(--hh-surface-2)`, border-color → `var(--hh-border-2)`
- Table rows (non-selected): bg → `var(--hh-surface-2)`
- Table rows (selected): bg → `#fbe1e3` (đậm hơn `var(--hh-accent-soft)` 1 nấc)
- Action button danger: bg → `#fff5f4`, border → `#fdd5d0`

### Focus states
- Inputs (search + form fields): border-color → `var(--hh-ink)` (đen)
- Không dùng outline mặc định của browser; outline:none + border thay đổi

### Transitions
- Buttons / inputs: `transition: background .12s, border-color .12s`
- Table rows: `transition: background .08s`
- Collapse arrow: `transform .15s`
- FAB enter: `@keyframes hh-fab-in` 180ms ease-out (`opacity 0→1; translateY 8px→0`)

### Loading & error states
- Sử dụng `st.spinner()` / `st.warning()` / `st.error()` đã có — không cần style mới (Streamlit defaults OK trong context này).

### Responsive
- ≤1100px: grid collapse thành 1 cột → detail card xuống dưới bảng (CSS `@media` đã có).
- Mobile (≤640px): toolbar wrap (browser tự xử lý), branch chips xuống dòng — chấp nhận được.

---

## 9. State Management (Streamlit session_state)

Giữ nguyên keys đã có. Tóm tắt:

| Key | Type | Set khi | Đọc ở đâu |
|---|---|---|---|
| `hh_ma_chon` | str | User chọn 1 dòng trong bảng | Detail rail render |
| `hh_search_cnt` | int | Reset search sau khi đóng card | `text_input(key=f"hh_search_{cnt}")` |
| `hh_cha` / `hh_con` | str | Trong popover Lọc | Filter dataframe |
| `hh_cn` | list[str] | Multiselect chi nhánh | `view_branches` |
| `hh_them_cnt` | int | Sau khi thêm hàng thành công | Reset form keys |
| `_hh_in_tem_items` | list[dict] | Click "In tem" | `_dlg_in_tem_hh` |
| `_intem_hh_qty` | dict[ma, qty] | Dialog in tem editor | Render label HTML |
| `adj_ton_<ma>_<cn>` | int | Number_input chỉnh tồn | "Lưu tồn kho" handler |
| `hh_sua_cnt_<ma>` | int | Sau khi sửa info | Reset form |
| `hh_an_confirm_<ma>` | bool | Click "Ẩn hàng hóa" | Hiện confirm UI |

---

## 10. Acceptance criteria

Implementation hoàn thành khi:

- [ ] Trang Hàng hóa load **không có scroll dọc** ở viewport 1440×900 khi chưa chọn dòng nào.
- [ ] Khi chọn 1 dòng, detail card xuất hiện ở rail phải; cuộn bảng không làm mất detail.
- [ ] Tất cả thao tác cũ vẫn hoạt động: search/filter/multiselect chi nhánh/chọn dòng/in tem/thêm mới/sửa/ẩn/chỉnh tồn kho.
- [ ] Multi-select ≥2 dòng → rail biến thành queue + nút "In N tem mã vạch" hoạt động.
- [ ] Admin role thấy đủ các nút (Thêm/Sửa/Ẩn/Chỉnh tồn); user thường ẩn hết.
- [ ] Visual khớp `reference_hifi.html` ±2px về spacing, đúng màu token, đúng font.
- [ ] Không có console error / warning Python sau khi rerun nhiều lần.
- [ ] Cache `@st.cache_data` không bị mất hiệu lực ngoài ý muốn (vẫn `clear()` sau insert/update đúng như cũ).

---

## 11. Risks & Gotchas

1. **`st.dataframe` selection vs custom HTML table**: Phase 1 giữ `st.dataframe` (selection event hoạt động sẵn). Đừng convert sang HTML table — sẽ mất nhiều selection logic. Chỉ override CSS qua `[data-testid="stDataFrame"]`.

2. **Sticky toolbar vs Streamlit's own sticky header**: Streamlit có header riêng (`[data-testid="stHeader"]`) cao ~3.5rem. `position:sticky; top:0` của `.hh-toolbar` sẽ "dính" dưới header đó. Nếu muốn dính sát đỉnh viewport, thêm `top: 3.5rem` hoặc ẩn header Streamlit bằng `[data-testid="stHeader"]{display:none}` (cẩn thận làm mất menu).

3. **`st.columns` không thực sự là `display:grid`**: chấp nhận gap mặc định của st.columns; **đừng** cố override `grid-template-columns` của container Streamlit — sẽ vỡ responsive.

4. **`@st.dialog` trên Streamlit < 1.31** không có. Verify version Streamlit trong `requirements.txt` ≥ 1.31. Nếu thấp hơn → upgrade hoặc fallback dùng expander cho modal (kém UX nhưng vẫn chạy).

5. **CSS injection ô nhiễm cross-module**: tất cả class đã prefix `.hh-*`, nhưng các selector `[data-testid="stButton"] > button` là **global**. Nếu các module khác (`nhap_hang`, `kiem_ke`) cũng phụ thuộc default Streamlit button → cân nhắc bọc trong `.hh-scope > [data-testid="stButton"]`. Bàn với team trước khi merge.

6. **FAB position:fixed + Streamlit re-render**: animation fade-in sẽ trigger mỗi rerun. Nếu thấy chớp, đặt `animation-fill-mode: backwards` hoặc remove animation.

7. **Font load FOUC**: lần đầu load có thể flash system font. Có thể `font-display: swap` đã set trong Google Fonts URL → OK với UX.

---

## 12. Triển khai

Đọc tiếp **`IMPLEMENTATION_GUIDE.md`** để có:
- Patch trước/sau cho từng đoạn `hang_hoa.py`
- Checklist từng PR nhỏ (để dễ review)
- Cách test thủ công các state

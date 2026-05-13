# Prompt giao việc cho Claude Code

> Copy toàn bộ phần dưới đây dán vào Claude Code khi đang ở thư mục root của repo `DLW_APP`.

---

Tôi vừa thiết kế lại UI cho module `modules/hang_hoa.py`. Gói thiết kế nằm trong folder `design_handoff_hang_hoa/` đã được upload vào repo (hoặc paste vào cùng cấp với `modules/`).

## Việc cần làm

Viết lại file `modules/hang_hoa.py` để **giao diện bám sát thiết kế trong `design_handoff_hang_hoa/design_reference/`**, đồng thời **giữ nguyên 100% logic phân quyền, truy vấn Supabase, session state keys, và tính năng in tem mã vạch**.

## Bước thực hiện

1. Đọc `design_handoff_hang_hoa/README.md` — đây là spec đầy đủ. Đọc xong rồi mới code.
2. Đọc `design_handoff_hang_hoa/design_reference/styles.css` để lấy chính xác design tokens (màu, font, spacing, radius). Copy nguyên các biến CSS này vào `_inject_css_once()` mới.
3. Đọc `design_handoff_hang_hoa/design_reference/app.jsx` để hiểu cấu trúc component + flow tương tác.
4. Xem 4 ảnh trong `design_handoff_hang_hoa/screenshots/` để đối chiếu trực quan.
5. Đọc `modules/hang_hoa.py` hiện tại để xác định những hàm/đoạn code phải giữ y nguyên.
6. Viết lại `modules/hang_hoa.py` thành drop-in replacement.

## Yêu cầu bắt buộc

### GIỮ NGUYÊN (không động vào):
- Toàn bộ imports từ `utils.config`, `utils.db`, `utils.auth`, `utils.helpers`.
- Hàm `_build_df(master, the_kho)` — chuẩn hóa data.
- Hàm `_apply_filters(...)` — search/sort logic. (Có thể bỏ tham số `low_only`.)
- Hàm `_render_them_moi()`, `_render_sua_hang_hoa()`, `_render_chinh_ton()`, `_render_an_hang_hoa()` — admin actions.
- Hàm `_dlg_in_tem_hh()`, `_render_dialog_in_tem()`, `_trigger_print_window()` — in tem mã vạch.
- Tất cả session state keys cũ: `hh_cn`, `hh_ma_chon`, `hh_search_cnt`, `hh_cha`, `hh_con`, `hh_sort`, `_hh_in_tem_items`, `_intem_hh_qty`, `_intem_hh_symb`.
- Phân quyền: `is_admin()`, `is_ke_toan_or_admin()`, `get_active_branch()`, `get_accessible_branches()` — check ở đúng vị trí cũ.
- Cache pattern: `st.cache_data.clear()` sau mỗi mutation.
- Logging: `log_action(...)` sau mỗi action.

### THAY ĐỔI (theo thiết kế mới):
1. **Bỏ hàm `_render_kpi()`** và toàn bộ chỗ gọi nó. Bỏ khối "Tổng quan" 4 KPI tiles.
2. **Bỏ checkbox "Chỉ hiện tồn ≤ 10"** trong popover bộ lọc nâng cao. Bỏ logic `low_only` trong `_apply_filters`.
3. **Bỏ banner `_render_selected_banner()` cũ** (với gradient đỏ + mini bar 3 chi nhánh). Thay bằng:
   - `_render_product_detail(row_m, branch_tons, branch_kho_ids, active)`: panel trắng 18-20px padding, 3 branch cards bên dưới (xem screenshot 02).
   - `_render_group_detail(group_name, df_group, active)`: cấu trúc tương tự nhưng cộng dồn tồn của tất cả SP trong nhóm (xem screenshot 03). Chỉ hiện khi user đang lọc theo 1 nhóm hàng cụ thể (`hh_cha != "Tất cả"`) VÀ chưa chọn SP nào.
4. **Bảng `_render_table()` đơn giản hóa**: chỉ còn 5 cột: **Sản phẩm · Nhóm · Mã hàng · Mã vạch · Giá bán**. Bỏ tất cả `ProgressColumn` của 3 chi nhánh, bỏ cột "Tổng (3 CN)", bỏ cột "Trạng thái".
5. **Pills nhóm hàng**: thay vì chỉ hiển thị read-only, để chúng **click được** để lọc — dùng `st.button` được style override thành pill (border-radius 999px, height 28px, bg ink khi active). Top 6 nhóm phổ biến.
6. **Header**: 1 dòng. Title 22px + subtitle "N SKU · 3 chi nhánh" 12px muted, branch popover, nút reload icon, nút "+ Thêm hàng hóa" primary đậm (ink bg, không phải accent đỏ).
7. **Search row**: 1 thanh trắng có border, search input flex:1 + nút quét + sort selectbox cùng dòng.
8. **Nút "In tem mã vạch"**: nút accent đỏ (`#c63a2b`) ở footer bảng, disabled khi không có dòng nào được tick (= chọn ≥ 2 dòng trong dataframe, vì 1 dòng = xem chi tiết).

### Design tokens phải dùng đúng

```python
T = {
    "bg":        "#f6f5f2",
    "surface":   "#ffffff",
    "surface_2": "#fbfaf7",
    "ink":       "#1a1a18",
    "ink_2":     "#44443f",
    "muted":     "#8a8a82",
    "muted_2":   "#b4b3aa",
    "border":    "#ece9e2",
    "border_2":  "#e0dcd2",
    "accent":    "#c63a2b",
    "accent_2":  "#fbe9e5",
    "accent_ink":"#8a2418",
}
```

Font: `Geist` (Google Fonts) cho UI, `Geist Mono` cho mã hàng/mã vạch/số. Inject qua `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap">` trong CSS injection.

## Quy tắc Streamlit-specific

- CSS injection 1 lần: `_inject_css_once()` với guard `st.session_state["_hh_css_v4"]`. Bump version.
- Override `[data-testid="stVerticalBlockBorderWrapper"]` cho container có border. Reset trong popover.
- Override `[data-testid="stButton"] button` để style pill khi cần (dùng `key` prefix `hh_pill_` để tách scope nếu cần).
- `st.dataframe` selection mode `multi-row` + `on_select="rerun"`. Đúng 1 dòng → set `hh_ma_chon` → hiện product detail. ≥ 2 dòng → clear `hh_ma_chon` + cho phép in tem.
- Pills nhóm hàng → mỗi pill là `st.button` riêng trong `st.columns`. On-click set `st.session_state["hh_cha"]` + `st.rerun()`.

## Output

1 file Python duy nhất: **`modules/hang_hoa.py`** (drop-in replacement). Đừng tạo file mới khác. Đừng đổi tên hàm public `module_hang_hoa()`.

## Kiểm tra trước khi commit

- [ ] Module render được, không exception, kể cả khi `master` rỗng.
- [ ] Search + sort + filter theo nhóm hoạt động đúng.
- [ ] Click 1 dòng → product detail panel hiện đúng tên SP + 3 branch cards với số tồn thật.
- [ ] Click pill 1 nhóm hàng + không chọn dòng nào → group detail panel hiện đúng số SKU + tồn cộng dồn.
- [ ] Tick ≥ 2 dòng → nút "In tem mã vạch (N)" enable, click mở modal đúng.
- [ ] Modal in tem in được (giữ Blob URL workflow cũ).
- [ ] Admin actions ✎ ▣ ↺ ⊘ chỉ enable khi `is_admin()`.
- [ ] Không còn cột tồn / status trong bảng.
- [ ] Không còn khối "Tổng quan".
- [ ] Visual đối chiếu screenshots 01-04 thấy match (font, màu, spacing).

Thanks!


# Bàn giao thiết kế — Redesign `modules/hang_hoa.py`

## Tổng quan

Đây là gói bàn giao thiết kế UI mới cho module **Hàng hóa** trong app DLW (Streamlit, Python). Mục tiêu: thay UI hiện tại (xem `screenshots/_old.png` / repo gốc) bằng layout sạch, gọn, tập trung vào tác vụ chính — KHÔNG đổi logic phân quyền, truy vấn Supabase, hay session state keys.

## Về các file thiết kế

Folder `design_reference/` chứa **prototype HTML/React** — đây là **bản tham chiếu hình ảnh + tương tác**, KHÔNG phải code production để copy nguyên xi.

Codebase đích là **Python + Streamlit** (xem `https://github.com/KevinTruong34/DLW_APP` — file `modules/hang_hoa.py`). Nhiệm vụ là **tái hiện thiết kế HTML này trong Streamlit**, bằng cách:
- Tận dụng `st.container(border=True)`, `st.columns`, `st.popover`, `st.dataframe`, `st.dialog` đã có sẵn.
- Inject CSS qua `st.markdown(..., unsafe_allow_html=True)` để override visual (xem `styles.css` để lấy design tokens).
- Một số micro-interaction (animation hover, dropdown menu custom) sẽ phải đơn giản hóa do giới hạn của Streamlit — ưu tiên đúng layout + spacing + typography + màu sắc, không cố pixel-perfect mọi state.

## Mức độ hoàn thiện

**High-fidelity (hifi)**. Màu, type, spacing, border-radius là final. Hãy match chính xác design tokens (xem mục dưới).

## Logic cần giữ NGUYÊN VẸN (KHÔNG ĐỘNG VÀO)

Tất cả import + helpers + DB calls + auth phải giữ. Cụ thể:
- `from utils.config import ALL_BRANCHES, CN_SHORT`
- `from utils.db import supabase, log_action, load_the_kho, load_hang_hoa`
- `from utils.auth import is_admin, is_ke_toan_or_admin, get_active_branch, get_accessible_branches`
- `from utils.helpers import _normalize`
- Hàm `_build_df(master, the_kho)` — giữ y nguyên (chuẩn hóa cột `_cha`, `_con`, `_norm_ma`, `_norm_vach`, `_norm_ten`, `Ton_cuoi`, `gia_ban`).
- Hàm `_apply_filters(...)` — giữ logic search/filter/sort. Có thể bỏ tham số `low_only` nếu không còn checkbox đó.
- Hàm `_render_them_moi()`, `_render_sua_hang_hoa()`, `_render_an_hang_hoa()`, `_render_chinh_ton()` — giữ y nguyên (đã ổn).
- Hàm `_dlg_in_tem_hh()`, `_render_dialog_in_tem()`, `_trigger_print_window()` — **GIỮ NGUYÊN**. Là logic in tem mã vạch quan trọng.
- Session state keys cũ phải tương thích: `hh_cn`, `hh_ma_chon`, `hh_search_cnt`, `hh_cha`, `hh_con`, `hh_sort`, `_hh_in_tem_items`, `_intem_hh_qty`, `_intem_hh_symb`.

## Thay đổi UX cụ thể (yêu cầu nghiệp vụ)

1. **Bỏ hoàn toàn khối "Tổng quan"** (KPI 4 ô: Tổng SKU / Đang bán / Sắp hết / Hết hàng). Xóa hàm `_render_kpi()` và toàn bộ chỗ gọi nó.
2. **Bỏ checkbox "Chỉ hiện tồn ≤ 10"** trong popover bộ lọc nâng cao (và logic `low_only` đi kèm).
3. **Bảng danh sách sản phẩm KHÔNG còn các cột**: progress bar tồn theo từng chi nhánh (Lê Quý Đôn / Coop VT / GO Bà Rịa), cột "Tổng (3 CN)", cột "Trạng thái" (🔴/🟡/🟢). Bảng chỉ còn: **Sản phẩm · Nhóm · Mã hàng · Mã vạch · Giá bán**.
4. **Tồn kho theo chi nhánh chỉ hiển thị trong 2 trường hợp** (qua 1 panel chi tiết, KHÔNG còn trong bảng):
   - **Khi chọn 1 sản phẩm cụ thể** (multi-select đúng 1 dòng): hiện tồn 3 chi nhánh CHO CHÍNH SP đó.
   - **Khi lọc theo 1 nhóm hàng cụ thể** (pill nhóm hàng được active, KHÔNG có sản phẩm nào được chọn): hiện tồn 3 chi nhánh CỘNG DỒN cho cả nhóm.
   - Khi không có cả 2 trường hợp trên → KHÔNG render panel chi tiết.
5. **Bỏ banner mini-bar 3 chi nhánh** kiểu cũ (slim banner với gradient đỏ). Thay bằng panel chi tiết mới — xem screenshot 02 + 03.

## Hệ thống thiết kế (Design tokens)

Copy nguyên các giá trị này vào CSS injection trong Streamlit:

```css
--bg:        #f6f5f2;   /* warm neutral page bg */
--surface:   #ffffff;
--surface-2: #fbfaf7;   /* hover / subtle bg */
--ink:       #1a1a18;
--ink-2:     #44443f;
--muted:     #8a8a82;
--muted-2:   #b4b3aa;
--border:    #ece9e2;
--border-2:  #e0dcd2;
--accent:    #c63a2b;   /* brand red — giữ lại từ design cũ, dùng cho nút In tem + accent nhẹ */
--accent-2:  #fbe9e5;   /* selected-row background */
--accent-ink:#8a2418;
```

- Border radius: `10px` cho container lớn, `7px` cho button + small card, `5px` cho code chip.
- Spacing: 6 / 8 / 10 / 12 / 14 / 16 / 18 / 20 / 28 px. Container padding 18–20px, table cell padding 10–14px.
- Typography:
  - UI font: **`Geist`** (Google Fonts) → fallback `"Söhne", "Inter", -apple-system, sans-serif`.
  - Mono font: **`Geist Mono`** → fallback `"JetBrains Mono", ui-monospace, monospace`.
  - Font sizes: title 22px/600/letter-spacing -.02em · section header 17px/600 · body 13px/400 · table header 11.5px/500/uppercase/letter-spacing .04em · small label 11px/muted · code 11.5px mono.
  - Tabular-nums (`font-variant-numeric: tabular-nums`) cho mọi con số.

## Layout 4 khối chính

```
┌──────────────────────────────────────────────────────────────────┐
│ Header (1 dòng)                                                  │
│   [Hàng hóa] [4,122 SKU · 3 CN]      [● Lê Quý Đôn ⌄][↻][+ Thêm]│
├──────────────────────────────────────────────────────────────────┤
│ Search row (1 thanh trắng có border, chia 3 vùng bằng divider)   │
│   [🔍 Tìm theo tên...][📷 quét]       [Sắp xếp: Tên A→Z ⌄]      │
├──────────────────────────────────────────────────────────────────┤
│ Pills hàng ngang (Tất cả + 6 nhóm hàng + ⊞ Bộ lọc nâng cao)       │
├──────────────────────────────────────────────────────────────────┤
│ (Conditional) Detail panel — chỉ hiện khi:                       │
│   A. Chọn 1 SP → product detail + 3 branch cards (cho SP đó)     │
│   B. Đang lọc 1 nhóm hàng + chưa chọn SP → group aggregate       │
│       + 3 branch cards (cộng dồn cho nhóm)                       │
├──────────────────────────────────────────────────────────────────┤
│ Bảng (5 cột): SP · Nhóm · Mã hàng · Mã vạch · Giá bán            │
│ Footer: hint text + [🏷️ In tem mã vạch (N)] nút accent đỏ        │
└──────────────────────────────────────────────────────────────────┘
```

## Chi tiết từng component

### 1. Header
- Title `"Hàng hóa"` 22px/600/letter-spacing -.02em.
- Subtitle `"4,122 SKU · 3 chi nhánh"` 12px/muted, đặt cùng dòng title (align baseline, gap 14px).
- Phải: branch popover button (style như `.btn` — height 30px, padding 0 12px, border `--border-2`, dot tròn 6px màu `--good`), nút reload icon-only, nút primary đậm (ink-bg `#1a1a18` text `#faf9f6`) "+ Thêm hàng hóa".
- KHÔNG có nút mũi tên ⌄ dropdown bên cạnh "+ Thêm" (giản hóa hơn bản cũ).

### 2. Search row
- 1 container trắng, border `--border`, radius 10, padding 6px.
- Search input bên trái flex:1, height 34px, padding 0 12px, font-size 13.5px, placeholder text muted, có icon 🔍 trái và icon ✕ phải (chỉ khi có text).
- Divider 1px x 22px màu `--border` giữa search và nút quét.
- Nút quét mã vạch icon-only.
- Divider tiếp.
- Sort selector inline (không phải `<select>` mặc định), padding 0 12px, hover surface-2, mở dropdown menu custom.

### 3. Pills nhóm hàng
- Hàng ngang, gap 6px, wrap.
- Mặc định: bg `--surface`, border `--border`, radius 999px, height 28px, padding 0 11px, font 12px, color `--ink-2`.
- Active: bg `--ink` (đen), text `#faf9f6`, border `--ink`. Active = nhóm đang lọc.
- Số count nhỏ phía sau (10.5px muted).
- Pill cuối cùng "⊞ Bộ lọc nâng cao" ghost (transparent + dashed border) — đẩy về phải bằng `spacer` flex:1.

### 4. Detail panel (xem screenshot 02 và 03)
- Container trắng bg `--surface`, border `--border`, radius 10, padding 18px 20px, margin-bottom 16px.
- Header panel:
  - Bên trái (`.info`): tên SP (hoặc tên nhóm) 17px/600, code chip mã hàng (mono, bg `--surface-2`, border, radius 5, padding 2px 7px), code chip mã vạch (giống nhưng dashed border + transparent bg). Hàng dưới `.meta` 12.5px/muted: nhóm › thương hiệu · Giá bán **2,326,000 đ** (ink).
  - Bên phải (`.actions`): 4 icon-only buttons (Sửa ✎, Chỉnh tồn ▣, Lịch sử ↺, Ẩn ⊘) — chỉ enable khi `is_admin()`.
  - Nút ✕ tuyệt đối top-right (24x24, transparent, hover surface-2) — clear selection.
- Branch grid: 3 cột bằng nhau, gap 10, margin-top 16.
- Branch card: bg `--surface-2`, border `--border`, radius 7, padding 12px 14px.
  - Label (uppercase 11px muted) — nếu là active branch thì có dot 5px màu ink phía trước.
  - Giá trị tồn 26px/600/tabular-nums.
  - "X% tổng tồn" 11px muted.
  - Bar 3px ở dưới: track `--border`, fill `--ink` (hoặc `--accent` nếu active branch). Width = (tồn / max 3 chi nhánh) * 100%.
- **Group panel** dùng cùng container nhưng không có actions buttons; tên là tên nhóm, code chip là số SKU.

### 5. Bảng (xem screenshot 01)
- Bảng trong wrap có border + radius 10, overflow:hidden.
- Header bảng `--surface-2`, padding 12px 16px, font 12 muted: `**N** sản phẩm` + các filter tag chip nhỏ (Nhóm: xxx, Từ khóa: "xxx") có nút ✕ inline để clear filter đó.
- Bảng:
  - `<th>` font 11.5/500/uppercase/letter-spacing .04em/muted, padding 10px 14px, border-bottom `--border`, bg `--surface-2`.
  - `<td>` padding 11px 14px, border-bottom `--border`, font 13.
  - Cột checkbox 28px, không padding phải.
  - Cell sản phẩm: tên SP `.pname` (ink, weight 500) + brand subtitle 11px muted dưới (chỉ nếu có).
  - Cell mã hàng + mã vạch: mono, 11.5px, color `--ink-2`.
  - Cell giá: tabular-nums, weight 500, ` ₫` suffix muted.
  - Cột giá align right.
- Row hover: bg `--surface-2`.
- Row selected (1 dòng được chọn xem chi tiết): bg `--accent-2` (đỏ nhạt), text `--accent-ink`.
- Row checked (đã tick): bg `#fffbf7`.
- Checkbox custom: 15x15, border 1.5px `--muted-2`, radius 3, khi checked bg `--ink` + dấu ✓ trắng vẽ bằng border, khi indeterminate có line ngang trắng.

### 6. Footer in tem
- Bar dưới bảng (border-top `--border`, bg `--surface-2`, padding 12px 16px).
- Trái: hint text muted 12px. Nếu chưa tick gì: "Tick các dòng cần in tem, hoặc click 1 dòng để xem chi tiết." Nếu đã tick: "Đã chọn **N sản phẩm** để in tem."
- Phải: nút `.btn-accent` bg `--accent` đỏ, text trắng. Disabled khi chưa tick. Icon 🏷️ + chữ "In tem mã vạch" + count badge (bg trắng trong suốt 22%, padding 1px 6px, radius 99px, font 11 tabular-nums).

### 7. Modal in tem mã vạch (giữ logic gốc, chỉ restyle)
- Backdrop bg rgba(20,18,12,.35) + blur 2px.
- Modal: 720px max, radius 12, bg trắng, shadow lớn.
- Head: 16px 20px, border-bottom, title 15px/600, nút ✕ right.
- Body: 2 trường (Loại mã vạch · Khổ tem) trong field 11.5/uppercase/muted label + select height 32px border `--border-2` radius 6. Bảng `print-list` 5 cột (Mã hàng mono · Tên · Giá right tabular · Mã vạch mono · SL tem input number 60px).
- Foot: bar bg `--surface-2`, "Tổng số tem sẽ in: **N**" trái, 2 nút phải ("Hủy" outline · "Mở trang in" accent đỏ).

## Quy ước implement trong Streamlit

Một vài kỹ thuật đã chứng minh hoạt động trong codebase này (xem version cũ của `hang_hoa.py`):

1. **CSS inject 1 lần**: dùng pattern `_inject_css_once()` với guard `st.session_state["_hh_css_v4"]`. Bump version mỗi lần đổi CSS để không stale.
2. **Container có background**: `st.container(border=True)` + override CSS trên `[data-testid="stVerticalBlockBorderWrapper"]` để đổi bg và border-radius. Đảm bảo popover content KHÔNG bị override (selector `[data-baseweb="popover"] [data-testid="stVerticalBlockBorderWrapper"]` reset về `--surface`).
3. **Pills không click được trực tiếp trong Streamlit HTML-only**. Workaround:
   - Cách A: dùng `st.button` cho từng nhóm hàng với CSS override để trông như pill (cần ép `border-radius:999px`, height 28px qua selector `[data-testid="stButton"] button`).
   - Cách B: dùng `st.selectbox` "Nhóm hàng" gọn 1 dòng + render `st.markdown` HTML pills bên cạnh chỉ để hiển thị visual (read-only). Cách B đơn giản hơn nhưng kém tương tác.
   - **Recommend cách A**: dùng `st.columns` chia đều, mỗi cột 1 `st.button` với key duy nhất, on-click set `st.session_state["hh_cha"]` rồi `st.rerun()`.
4. **Branch popover ở header**: dùng `st.popover` đã sẵn — chỉ cần override CSS để label hiện dot màu + chevron.
5. **Bảng**: dùng `st.dataframe` với `selection_mode="multi-row"` và `on_select="rerun"` (đã sẵn). Bỏ tất cả `st.column_config.ProgressColumn` cho cột chi nhánh — chỉ giữ 5 cột text/number. Khi user chọn đúng 1 dòng → set `hh_ma_chon`. Khi user chọn ≥ 2 dòng → set list `hh_ma_check` cho in tem (nhưng vẫn KHÔNG hiện product detail).
6. **Phân biệt "chọn xem chi tiết" vs "tick để in tem"**:
   - Logic cũ: dataframe chỉ có 1 cơ chế multi-row select; chọn đúng 1 dòng → hiện banner; ≥ 2 dòng → ẩn banner và enable in tem.
   - Giữ y hệt logic này. KHÔNG cần thêm cột checkbox riêng. Hint text đổi để phù hợp.

## Files trong gói này

```
design_handoff_hang_hoa/
├── README.md                        ← bạn đang đọc
├── PROMPT_FOR_CLAUDE_CODE.md        ← prompt copy-paste để giao cho Claude Code
├── design_reference/
│   ├── Hàng hóa.html                ← entry point — mở để xem prototype
│   ├── styles.css                   ← toàn bộ design tokens + style rules
│   ├── app.jsx                      ← logic + cấu trúc component React
│   └── data.jsx                     ← mock data (cấu trúc 1-1 với schema thật)
└── screenshots/
    ├── 01-default.png               ← state mặc định, không chọn gì
    ├── 02-product-selected.png      ← đã chọn 1 SP → hiện product detail panel
    ├── 03-group-filter.png          ← đang lọc 1 nhóm → hiện group detail panel
    └── 04-print-modal.png           ← modal in tem mã vạch (đã tick 3 dòng)
```

## Hướng dẫn cho developer

1. **Đọc trước**: mở `design_reference/Hàng hóa.html` (cần serve qua HTTP để Babel chạy — `python -m http.server 8000` rồi vào `http://localhost:8000/design_reference/Hàng hóa.html`). Click vài SP, lọc vài nhóm, mở modal in tem để cảm nhận flow.
2. **Đọc kỹ** `design_reference/styles.css` để lấy các giá trị token chính xác.
3. **So sánh** với `modules/hang_hoa.py` hiện tại — xác định phần code nào giữ, phần nào thay.
4. **Viết** module mới — drop-in replacement cho `modules/hang_hoa.py`.
5. **Test** với supabase thật: search, filter theo nhóm, click 1 SP để xem detail, tick nhiều SP để in tem.


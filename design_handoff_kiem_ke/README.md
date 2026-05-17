# Handoff: Module Kiểm kê v2 — Redesign

> **Target codebase**: DLW repo, file `kiem_ke.py` (Streamlit app, deploy lên Streamlit Cloud)
> **Tech stack**: Streamlit ≥1.33 · Python · Supabase backend · Vietnamese UI
> **Backend logic**: KHÔNG đổi. Toàn bộ Supabase queries / RPC giữ nguyên.

---

## Changelog gói handoff

**v2** (sau review):
- 🆕 `Kiem_ke_Hi-fi_v2.html` thay `Kiem_ke_Hi-fi.html` làm source of truth — markup inline-style thuần (không class), copy-paste được vào `st.html()`.
- 🔁 **Section 6** viết lại: rule rõ ràng về cái gì sống được qua iframe boundary (`:root` vars · `@keyframes` · selector trên native widget) vs cái gì không (class trên content element · pseudo-class hover).
- 🔁 **Section 8** redesign sang **Phương án A** (native `st.dataframe` + detail panel) — bỏ pattern row-by-row `st.columns` không tương thích.
- 🔁 **Section 9** bỏ pattern đổi thứ tự tab / `st.query_params` hack — dùng `st.toast()` + cue thay vào, user tự click tab Quét.
- 🔁 **Section 12** bỏ acceptance criterion `<300ms` không khả thi → đo & document trong PR.
- 🔁 **Section 13** cập nhật implementation order.

---

## 1. Overview

Redesign UI module `module_kiem_ke()` trong file `kiem_ke.py`. Mục tiêu:

1. **Giảm từ 4 sub-tab xuống 2** — gộp "Danh sách phiếu" + "Tạo phiếu" + "Duyệt admin" thành 1 tab duy nhất ("Quản lý phiếu") với action button theo trạng thái từng dòng.
2. **Card scan nổi bật** trên cùng tab quét, chứa: Mã hàng, Tên hàng, Mã vạch, Giá bán, SL đã quét, Tồn hệ thống, Lệch tạm.
3. **Phản hồi quét nhanh hơn + âm thanh khác khi quét sai** — đo lag thực tế trong PR, optimize nếu có cơ hội mà không gây stale data.
4. **Đổi accent đỏ → xanh lá** (cảm giác success / inventory).
5. **Giữ NGUYÊN toàn bộ logic** — đặc biệt UX khi bắn máy quét USB.

---

## 2. About the design files

Các file HTML trong bundle này là **design references** — prototype mô tả look & behavior mong muốn, **không phải production code để copy nguyên**.

Việc cần làm: tái tạo design này **trong Streamlit** dùng các pattern hiện có của codebase (native widgets + `st.html()` với inline styles theo constraint dưới).

- **`Kiem_ke_Hi-fi_v2.html`** — **source of truth visual + interaction**. Đây là file dùng để implement. Đặc tính quan trọng: mọi element content (div/span/section) dùng `style="..."` inline với `var(--token)`, KHÔNG dùng class — có nghĩa khi developer copy 1 đoạn markup vào `st.html('''…''')` thì visual sẽ render đúng (không phụ thuộc class CSS hoặc global `<style>`).
- `Kiem_ke_Hi-fi.html` — phiên bản v1 (deprecated, để tham khảo style nhưng KHÔNG copy markup vì dùng class). Giữ lại làm visual reference.
- `Kiem_ke_Wireframes.html` — 4 phương án wireframe đã khám phá, **đã chốt Phương án A** ("Inbox + action-per-row"). Các phương án B/C/D giữ để tham khảo.
- `kiem_ke_current.py` — code hiện tại (bản trước redesign) — đây là phiên bản logic cần được bảo toàn 100%.
- `design_system_constraints.md` — các constraint Streamlit-specific (CSS isolation, DOM wrapping, sanitizer).

**Fidelity**: Hi-fi. Implement pixel-close — colors, spacing, typography theo đúng token bên dưới.

---

## 3. Critical: Logic phải bảo toàn

Các hàm sau trong `kiem_ke_current.py` **giữ nguyên signature + behavior**. Chỉ đổi cách UI gọi chúng, không sửa body.

| Hàm | Vai trò | Lưu ý |
|---|---|---|
| `_kk_get_lines(ma_phieu)` | Load chi tiết phiếu, sort theo `updated_at desc`, dòng vừa quét lên đầu | **Giữ logic sort** — UI mới dựa vào sort này để hero card khớp dòng đầu tiên |
| `_kk_complete(ma_phieu)` | Chuyển phiếu → "Chờ duyệt admin" | Giữ |
| `_kk_gen_ma_phieu()` | Sinh mã phiếu `KK000NNN` | Giữ |
| `_kk_build_scope_rows(chi_nhanh, nhom_hang_chon)` | Build danh sách hàng kiểm kê từ master + thẻ kho | Giữ |
| `_kk_create_phieu(chi_nhanh, nhom_cha, ghi_chu)` | Insert phiếu + chi tiết | Giữ |
| **`_kk_scan_plus_one(ma_phieu, code)`** | **Logic scan +1 cốt lõi** | **TUYỆT ĐỐI không sửa.** Logic gồm: (1) tìm trong chi tiết phiếu, (2) fallback master để chèn "phát sinh mới" nếu tồn = 0. |
| `_kk_cancel_phieu(ma_phieu)` | Xóa phiếu + chi tiết | Giữ |
| `_kk_approve(ma_phieu)` | Gọi RPC `duyet_phieu_kiem_ke` atomic | Giữ |

**UX khi bắn máy quét USB phải y nguyên**:
- `st.form("kk_scan_form", clear_on_submit=True)` — máy quét USB bắn ký tự + Enter → form submit + clear ô input → sẵn sàng nhận mã tiếp theo.
- Auto-focus ô scan input sau mỗi rerun.

---

## 4. Structure change: 4 tab → 2 tab

```python
# CŨ
tab_list, tab_create, tab_scan, tab_approve = st.tabs(
    ["Danh sách phiếu", "Tạo phiếu", "Quét kiểm kê", "Duyệt admin"]
)

# MỚI
tab_scan, tab_manage = st.tabs(["Quét kiểm kê", "Quản lý phiếu"])
```

- **Tab Quét** = tab `tab_scan` cũ + reorganize.
- **Tab Quản lý phiếu** = gộp 3 tab cũ (list + create + approve). Mỗi dòng phiếu có action button theo `trang_thai`:
  - `"Đang kiểm"` → nút **"▶ Quét tiếp"** (chuyển sang tab Quét với phiếu đó được chọn) + nút Hủy.
  - `"Chờ duyệt admin"` → nút **"✓ Duyệt"** (chỉ admin, dùng `is_admin()`) + nút Xem chi tiết.
  - `"Đã duyệt"` → **"👁 Chi tiết"** + **"📥 Excel"**.
- Nút **"+ Tạo phiếu mới"** ở góc phải toolbar → mở `st.dialog()` (Streamlit ≥1.35) thay vì là sub-tab riêng.

---

## 5. Design tokens

### 5.1 Colors

```python
# Brand green (inventory / success)
GREEN_50  = "#ecfdf5"  # soft backgrounds
GREEN_100 = "#d1fae5"  # focus ring
GREEN_200 = "#a7f3d0"  # borders
GREEN_500 = "#10b981"
GREEN_600 = "#059669"  # primary hover
GREEN_700 = "#047857"  # PRIMARY accent
GREEN_800 = "#065f46"  # primary pressed
GREEN_900 = "#064e3b"  # text on green

# Neutrals
INK       = "#0b1220"  # primary text
INK_2     = "#475569"  # secondary text
INK_3     = "#94a3b8"  # subtle text / icons
LINE      = "#e5e7eb"  # default border
LINE_STR  = "#cbd5e1"  # strong border
SURFACE   = "#ffffff"
SURFACE_2 = "#f8fafc"  # alt surface (table head, kpi tile)
SURFACE_3 = "#f1f5f9"  # softer alt
BG        = "#f6f7f5"  # page background

# Semantic
WARN_50   = "#fffbeb"  # "Đang kiểm" badge bg
WARN_200  = "#fde68a"  # "Đang kiểm" border
WARN_700  = "#b45309"  # "Đang kiểm" text
BAD_50    = "#fef2f2"  # scan error bg
BAD_200   = "#fecaca"  # scan error border
BAD_500   = "#ef4444"
BAD_700   = "#b91c1c"  # negative delta text
INFO_50   = "#eff6ff"  # "Chờ duyệt" bg
INFO_200  = "#bfdbfe"  # "Chờ duyệt" border
INFO_700  = "#1d4ed8"  # "Chờ duyệt" text
```

### 5.2 Typography

```python
FONT_SANS = "'Plus Jakarta Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
FONT_MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
```

- Tất cả số / mã hàng / mã vạch → mono, `font-variant-numeric: tabular-nums`.
- Tên hàng + label → sans.
- Headings: weight 700, letter-spacing -0.01em.
- Body: weight 400-500, line-height 1.5.

**Font import** (load 1 lần ở đầu module, đưa vào `static/kiem_ke.css` hoặc inject qua `st.html` 1 lần):
```html
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
```

### 5.3 Spacing / Radius / Shadow

```python
R_SM = "6px"   # input bên trong, badge
R    = "10px"  # button, card nhỏ
R_LG = "14px"  # card lớn, scan input
R_XL = "18px"  # hero scan card

SHADOW_1    = "0 1px 2px rgba(15,23,42,.04), 0 1px 1px rgba(15,23,42,.03)"
SHADOW_2    = "0 4px 14px -4px rgba(15,23,42,.10), 0 2px 4px rgba(15,23,42,.04)"
SHADOW_CARD = "0 8px 28px -10px rgba(4,120,87,.18), 0 2px 6px rgba(15,23,42,.04)"
```

Spacing dùng scale 4 / 6 / 8 / 10 / 14 / 18 / 22 / 28 px.

---

## 6. Streamlit-safe style rules (CRITICAL — đọc trước khi code)

Learned từ nhiều vòng debug. **Vi phạm bất kỳ rule nào dưới = bug visual không match Hi-fi**.

### 6.1 Cái gì sống được qua `st.html()` iframe boundary

Chỉ 4 thứ sau đây propagate vào `st.html()`:

| Cho phép | Cách dùng |
|---|---|
| **CSS variables** trong `:root` | Khai báo 1 lần ở đầu module, gọi qua `var(--green-700)` trong inline style |
| **Body / html reset** | `body { font-family: ... }` áp dụng ở document level |
| **`@keyframes`** | Định nghĩa global, áp dụng qua inline `style="animation: flashOk 550ms ease;"` |
| **Selector trên `<button>` / `<input>` / `<select>` / `<textarea>`** | Đây là Streamlit native widgets, target qua `[data-testid="stButton"] button { ... }` trong `static/kiem_ke.css` |

**Mọi thứ khác KHÔNG propagate**:
- Class CSS định nghĩa trên `<div>` / `<span>` / `<section>` / `<article>` trong inline `<style>` block → KHÔNG match được khi render trong `st.html()`.
- Pseudo-class `:hover` / `:focus` trên content element → không hoạt động qua inline style. Hover/focus chỉ dùng được cho native widgets (qua CSS file) hoặc fallback JavaScript (set style trên `mouseenter`/`mouseleave` listener).

### 6.2 Quy tắc thực hành

1. **Content element** (`<div>`, `<span>`, `<section>`, `<article>`, `<p>`, `<h1-6>`, `<table>`, `<tr>`, `<td>`, `<th>`, `<img>`, `<svg>` …) → **inline `style="..."` ONLY**. Dùng `var(--token)` để giữ design system.
2. **Native widget** (`<button>`, `<input>`, `<select>`, `<textarea>`) → có thể dùng class. Style trong `static/kiem_ke.css` qua selector `[data-testid="..."]`.
3. **Animation** = `@keyframes` global + inline `style="animation: name 550ms ease;"`. Trigger lại animation: set `style.animation = 'none'; void el.offsetWidth; style.animation = 'flashOk 550ms ease';`.
4. **Hover effect trên content element** = Web Animations API hoặc `el.addEventListener('mouseenter', () => el.style.background = ...)`. KHÔNG dùng class `:hover`.
5. **Conditional state** (vd selected row) = set inline style từ Python: `style="background:{'var(--green-50)' if selected else 'transparent'};"`.

### 6.3 DOM wrapping rule

KHÔNG có chuyện `st.html('<div class="X">')` + `st.columns()` + `st.html('</div>')` để bao widget — Streamlit tạo DOM block độc lập cho mỗi call. Frame quanh widget phải dùng `st.container(border=True)`.

### 6.4 Pattern code mẫu — Hero scan card

Đọc `Kiem_ke_Hi-fi_v2.html` để lấy markup chính xác. Copy paste pattern vào `st.html('''…''')`:

```python
def _hero_scan_card(item: dict | None) -> None:
    """Render hero scan card. Single st.html() call, inline styles only."""
    if not item:
        st.html(_HERO_EMPTY_HTML)  # static string, inline-styled empty state
        return

    # Compute Lệch tạm color
    lech = item["sl_quet"] - item["ton"]
    lech_color = ("var(--bad-700)"   if lech < 0 else
                  "var(--green-700)" if lech > 0 else
                  "var(--ink-2)")
    lech_str = "0" if lech == 0 else ("+" if lech > 0 else "−") + str(abs(lech))

    st.html(f'''
    <div style="background:var(--surface);border:1px solid var(--line);
                border-radius:18px;box-shadow:var(--shadow-2);overflow:hidden;
                padding:18px 20px;display:grid;
                grid-template-columns:minmax(280px,1.4fr) repeat(5, minmax(0, 1fr));
                gap:18px;align-items:center;">
      <div style="display:flex;flex-direction:column;gap:4px;min-width:0;">
        <span style="display:inline-flex;align-items:center;gap:6px;
                     background:var(--green-50);color:var(--green-700);
                     border:1px solid var(--green-200);border-radius:999px;
                     padding:3px 10px;font-size:11px;font-weight:700;
                     letter-spacing:.04em;text-transform:uppercase;
                     width:fit-content;">✓ Vừa quét · +1</span>
        <span style="font-family:var(--mono);font-weight:700;font-size:22px;
                     color:var(--ink);">{item["ma_hang"]}</span>
        <span style="font-size:13px;color:var(--ink-2);">{item["ten_hang"]}</span>
      </div>
      <!-- ...5 field tiles, mỗi tile cũng inline style — copy nguyên từ Hi-fi_v2... -->
      <div style="display:flex;flex-direction:column;gap:3px;
                  border-left:1px solid var(--line);padding-left:14px;">
        <span style="font-size:11px;letter-spacing:.04em;text-transform:uppercase;
                     font-weight:600;color:var(--ink-3);">Lệch tạm</span>
        <span style="font-family:var(--mono);font-weight:700;font-size:18px;
                     color:{lech_color};font-variant-numeric:tabular-nums;">
          {lech_str}
        </span>
      </div>
    </div>
    ''')
```

### 6.5 Inject CSS variables + keyframes 1 lần đầu module

```python
_CSS_VARS_BLOCK = """
<style>
  :root {
    --bg: #f6f7f5;
    --surface: #ffffff;
    --surface-2: #f8fafc;
    --surface-3: #f1f5f9;
    --line: #e5e7eb;
    --line-strong: #cbd5e1;
    --ink: #0b1220;
    --ink-2: #475569;
    --ink-3: #94a3b8;
    --green-50: #ecfdf5;
    --green-100: #d1fae5;
    --green-200: #a7f3d0;
    --green-500: #10b981;
    --green-600: #059669;
    --green-700: #047857;
    --green-800: #065f46;
    --warn-50: #fffbeb; --warn-200: #fde68a; --warn-700: #b45309;
    --bad-50: #fef2f2;  --bad-200: #fecaca;  --bad-500: #ef4444;  --bad-700: #b91c1c;
    --info-50: #eff6ff; --info-200: #bfdbfe; --info-700: #1d4ed8;
    --shadow-1: 0 1px 2px rgba(15,23,42,.04), 0 1px 1px rgba(15,23,42,.03);
    --shadow-2: 0 4px 14px -4px rgba(15,23,42,.10), 0 2px 4px rgba(15,23,42,.04);
    --mono: 'JetBrains Mono', ui-monospace, monospace;
    --sans: 'Plus Jakarta Sans', system-ui, sans-serif;
  }
  @keyframes flashOk { 0% { background: var(--green-50); } 100% { background: var(--surface); } }
  @keyframes flashBad { 0% { background: var(--bad-50); } 100% { background: var(--surface); } }
  @keyframes rowFlash { 0% { background: var(--green-100); } 100% { background: transparent; } }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
</style>
"""

def module_kiem_ke():
    st.markdown(_CSS_VARS_BLOCK, unsafe_allow_html=True)  # 1 lần, qua st.markdown để propagate
    # ... rest of module
```

Ghi chú: `st.markdown(..., unsafe_allow_html=True)` được dùng ở đây chỉ để inject `<style>` block (không có HTML content cần class). Sanitizer strip class trên content elements, nhưng cho phép `<style>` + `:root` + `@keyframes` đi qua.

Visual styling cho native widgets (button, input, dataframe) → file riêng `static/kiem_ke.css` được load qua `st.markdown('<link rel="stylesheet" href="static/kiem_ke.css">', unsafe_allow_html=True)` hoặc tích hợp vào CSS chính của repo. Target `[data-testid="..."]`.

---

## 7. Tab 1 — Quét kiểm kê

### 7.1 Layout (top → bottom)

```
┌──────────────────────────────────────────────────────────────┐
│ Context bar                                                  │
│  [KK000013 ▾] [progress bar——————]  [KPI Khớp][KPI Lệch]   │
├──────────────────────────────────────────────────────────────┤
│ HERO SCAN CARD (sticky on scroll, ≥1100px)                   │
│  ┌──────────────┬──────┬──────┬──────┬──────┬──────┐        │
│  │ ✓ Vừa quét   │ Mã   │ Giá  │ SL   │ Tồn  │ Lệch │        │
│  │ MÃ HÀNG MONO │ vạch │ bán  │ quét │      │ tạm  │        │
│  │ Tên hàng     │      │      │      │      │      │        │
│  └──────────────┴──────┴──────┴──────┴──────┴──────┘        │
├──────────────────────────────────────────────────────────────┤
│ [📷 ô quét, autofocus              ] [↵ Enter] [+ Quét +1]  │
├──────────────────────────────────────────────────────────────┤
│ [Tất cả 9] [Còn lệch 7] [Đã khớp 2] [Chưa quét 6]  [🔍...]  │
│ 💡 Nháy đúp cột SL Thực tế để sửa · Mã vừa quét nhảy lên đầu │
├──────────────────────────────────────────────────────────────┤
│ Bảng item — st.data_editor (giữ logic hiện tại)              │
├──────────────────────────────────────────────────────────────┤
│ [✓ Hoàn thành kiểm kê] [📥 Excel] [🗑 Hủy phiếu]            │
└──────────────────────────────────────────────────────────────┘
```

### 7.2 Components

#### Context bar (`ctx-bar`)
- Container: `st.container(border=True)` HOẶC `st.html()` 1 cục.
- **Phiếu picker**: dropdown nhỏ thể hiện `<mã phiếu>` (green tag) + `<chi nhánh> · <nhóm cha>` + người tạo + ngày. Click → mở selectbox (có thể dùng `st.selectbox` ẩn label kèm `st.html` để chỉnh visual, hoặc `st.popover`).
- **Progress bar**: tỉ lệ `sum(sl_thuc_te) / sum(ton_snapshot)`. Gradient `linear-gradient(90deg, #10b981, #047857)`.
- **2 KPI tiles**: "Khớp" (số dòng có `lech == 0 && sl_quet > 0`) và "Lệch" (sum lệch). Tile bad có text color `#b91c1c`.

#### Hero scan card (THE element bạn này nhất)
- Render qua 1 call `st.html()` với inline styles.
- 6 cột grid: `minmax(280px,1.4fr) repeat(5, 1fr)`, gap 18px.
- Cột 1: ribbon "✓ Vừa quét · +1" (green pill) + Mã hàng (mono 22px bold) + Tên hàng (13px, muted).
- Cột 2–6: mỗi cột là 1 `field` với `border-left: 1px solid #e5e7eb`, padding-left 14px, có `<k>label</k>` (uppercase 11px ink-3) và `<v>value</v>` (mono 18px bold tabular).
- Cột "SL đã quét" có class `qty` — color `#047857`, font-size 22px (nổi bật hơn).
- Cột "Lệch tạm" đổi màu theo dấu:
  - `< 0` → `#b91c1c` (đỏ), prefix `−`
  - `> 0` → `#047857` (xanh), prefix `+`
  - `= 0` → `#475569` (gray)

**Empty state** (khi chưa có scan nào trong session): hiển thị placeholder "Quét mã đầu tiên để bắt đầu" với icon scanner. State lưu trong `st.session_state["kk_last_scan"]`.

**Flash animation** sau khi scan thành công:
- Border `#10b981` + box-shadow `0 0 0 3px #d1fae5` trong 550ms.
- Background nháy `#ecfdf5` → `#ffffff`.
- Trong Streamlit, set một flag `st.session_state["kk_flash"] = "ok" | "bad"` rồi inject 1 `<style>` block với class CSS keyframe + class trên hero container. Vì style từ `st.html` không thừa hưởng được, **cách đơn giản nhất**: đặt animation trực tiếp inline `style="animation: flashOk 550ms ease;"` + 1 `<style>@keyframes flashOk{...}</style>` trong CÙNG 1 `st.html()` call (keyframes vẫn dùng được nội-trong-cùng-block).

#### Scan input (`scan-input-row`)
```python
with st.form("kk_scan_form", clear_on_submit=True):
    code = st.text_input("Quét mã vạch / mã hàng:", label_visibility="collapsed",
                         placeholder="Đưa con trỏ ở đây và quét mã vạch / mã hàng…",
                         key="kk_scan_code")
    submitted = st.form_submit_button("Quét +1", type="primary", use_container_width=True)
```
Style ô input qua CSS file (`static/kiem_ke.css`) target:
```css
div[data-testid="stTextInput"] input { 
    font-family: 'JetBrains Mono', monospace;
    font-size: 17px;
    padding: 14px 16px;
    border: 1.5px solid #cbd5e1;
    border-radius: 14px;
}
div[data-testid="stTextInput"] input:focus { 
    border-color: #059669;
    box-shadow: 0 0 0 4px #d1fae5;
}
```

**Auto-focus** — sau mỗi rerun, inject JS:
```python
st.html("""
<script>
  setTimeout(() => {
    const inp = window.parent.document.querySelector('input[aria-label*="Quét"]');
    if (inp && document.activeElement !== inp) inp.focus();
  }, 50);
</script>
""")
```
(Lưu ý: Streamlit iframe có thể cần `window.parent.document` hoặc shadow DOM workaround — test kỹ.)

#### Filter chips
4 chip: Tất cả, Còn lệch, Đã khớp, Chưa quét. Count động dựa trên dataframe `lines`.

```python
chip_cols = st.columns([1,1,1,1,4])
for i, (label, key, count) in enumerate(chips):
    active = st.session_state.get("kk_filter", "all") == key
    with chip_cols[i]:
        if st.button(f"{label} ({count})", 
                     type="primary" if active else "secondary",
                     use_container_width=True):
            st.session_state["kk_filter"] = key
            st.rerun()
```

Lọc `lines` trước khi đẩy vào `st.data_editor`:
```python
filt = st.session_state.get("kk_filter", "all")
if filt == "lech":  view = view[view["Lệch Tạm"] != 0]
elif filt == "khop": view = view[(view["Lệch Tạm"] == 0) & (view["SL Quét"] > 0)]
elif filt == "chua": view = view[view["SL Quét"] == 0]
```

#### Bảng item
`st.data_editor` — **giữ y nguyên config hiện tại** (xem `kiem_ke_current.py` dòng 397-422). Chỉ thêm:
- Column "Mã Hàng / Mã Vạch" gộp 2 cột thành 1 (mã hàng trên, mã vạch dưới muted). Streamlit data_editor không support multi-line dễ — nên giữ 2 cột riêng.
- Style table head qua CSS:
  ```css
  div[data-testid="stDataFrame"] thead th {
      background: #f8fafc; color: #475569; 
      font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em;
  }
  ```

#### Footer actions
3 button: "Hoàn thành kiểm kê" (primary green), "Xuất Excel KiotViet" (default), "Hủy phiếu" (danger — text đỏ, border đỏ nhạt). Layout: `st.columns([3, 2, 1])`.

### 7.3 Scan flow

Hiện tại `_kk_scan_plus_one()` đồng bộ:
1. Form submit → reload toàn bộ chi tiết phiếu.
2. `st.cache_data.clear()` → mọi data fetch khác cũng phải re-fetch.
3. `st.rerun()` mặc định khiến full module render lại.

**Pattern đề xuất**:

```python
if submitted and code.strip():
    # 1. Lookup lấy info hiển thị hero card (lấy từ master hoặc chi tiết phiếu)
    item_info = _kk_lookup_item(ma_phieu, code)  # NEW helper, lightweight
    if not item_info:
        st.session_state["kk_last_scan"] = {"error": True, "code": code}
        st.session_state["kk_flash"] = "bad"
    else:
        st.session_state["kk_last_scan"] = item_info
        st.session_state["kk_flash"] = "ok"
        # 2. WRITE DB (sync) — gọi hàm _kk_scan_plus_one hiện tại
        ok, _ = _kk_scan_plus_one(ma_phieu, code)
        if not ok:
            st.session_state["kk_last_scan"] = {"error": True, "code": code}
            st.session_state["kk_flash"] = "bad"
    # 3. Đừng clear toàn bộ cache, chỉ invalidate phiếu hiện tại
    st.rerun()
```

Các điểm có thể cải thiện thời gian phản hồi (không cam kết fix được lag cụ thể — cần đo thay đổi trước/sau trong PR):
- **KHÔNG gọi `st.cache_data.clear()` global** — chỉ invalidate function cụ thể: `load_phieu_kiem_ke.clear()` hoặc cached `_kk_get_lines.clear()` nếu được cache.
- Cache `_kk_get_lines` với TTL ngắn (10s) hoặc dùng `@st.cache_data` với scope key `ma_phieu`.
- **Tách lookup nhẹ** (chỉ join master) ra khỏi insert/update — render card trước, write sau.

Latency bên ngoài (Streamlit Cloud + Supabase Cloud + VN network) thường 150-300ms 1 chiều — cam kết target cụ thể không feasible. Developer đo thời gian round-trip thiểu sau khi implement, document trong PR.

### 7.4 Beep âm thanh

Web Audio API qua `st.html()`:

```python
def _play_beep(kind: str) -> None:
    """kind: 'ok' or 'bad'"""
    js = """
    (() => {
      const ac = window.__kk_ac || (window.__kk_ac = new (window.AudioContext || window.webkitAudioContext)());
      function tone(f, d, type) {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = type; o.frequency.value = f;
        g.gain.value = 0.07;
        o.connect(g).connect(ac.destination);
        o.start();
        g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + d);
        o.stop(ac.currentTime + d + 0.01);
      }
      __KIND__
    })();
    """
    if kind == "ok":
        body = "tone(880, 0.08, 'sine');"
    else:
        body = "tone(220, 0.18, 'square'); setTimeout(() => tone(180, 0.18, 'square'), 100);"
    st.html(f"<script>{js.replace('__KIND__', body)}</script>")

# Sau khi scan
if st.session_state.pop("kk_flash", None) == "ok":
    _play_beep("ok")
elif st.session_state.pop("kk_flash", None) == "bad":
    _play_beep("bad")
```

Lưu ý: trình duyệt chặn AudioContext khi chưa có user gesture đầu tiên. Sau click đầu tiên là OK. Nếu cần resume:
```js
if (ac.state === 'suspended') ac.resume();
```

---

## 8. Tab 2 — Quản lý phiếu (**Phương án A: dataframe + detail panel**)

> **Vì sao Phương án A**: Streamlit không hỗ trợ button trong cell của `st.dataframe`. Render row-by-row qua `st.columns` cho 15+ phiếu = ~120 DOM block rời rạc → bảng "lỏng lẻo", không thẳng hàng, mất visual fidelity với Hi-fi. Pattern selection-driven + detail panel dùng native `st.dataframe` (gọn) + panel chi tiết dưới đó (rộng rãi, action buttons nằm trong panel chứ không trong row).

### 8.1 Layout

```
┌──────────────────────────────────────────────────────────────┐
│ [Tất cả 15] [Đang kiểm 1] [Chờ duyệt 1] [Đã duyệt 13]      │
│                                  [🔍 tìm...] [+ Tạo phiếu] │
├──────────────────────────────────────────────────────────────┤
│ st.dataframe(on_select="rerun", selection_mode="single-row") │
│ └─ Native Streamlit table, no row buttons — click row → select│
├──────────────────────────────────────────────────────────────┤
│ DETAIL PANEL (ẩn nếu chưa chọn row)                          │
│   • Header: status badge + mã phiếu + meta + action buttons  │
│   • KPI tiles (4 cho 'Chờ duyệt', 3 cho 'Đang kiểm')         │
│   • Bảng chi tiết mặt hàng (read-only)                       │
└──────────────────────────────────────────────────────────────┘
```

### 8.2 Toolbar (filter chips + search + Tạo phiếu)

```python
c_chips, c_spacer, c_search, c_create = st.columns([3, 1, 2, 1.2])
with c_chips:
    # 4 chip buttons (Tất cả / Đang kiểm / Chờ duyệt / Đã duyệt)
    # type="primary"/"secondary" theo active state
with c_search:
    q = st.text_input("", placeholder="Tìm mã phiếu / chi nhánh / nhóm…",
                      label_visibility="collapsed", key="kk_manage_search")
with c_create:
    if st.button("+ Tạo phiếu mới", type="primary", use_container_width=True):
        _dlg_create_phieu()
```

### 8.3 Bảng phiếu — native `st.dataframe`

```python
view = df.copy()  # df = load_phieu_kiem_ke(tuple(accessible))
# apply filter chip + search
if kk_filter != "all":
    view = view[view["trang_thai"].map(STATUS_MAP) == kk_filter]
if q:
    view = view[view.apply(
        lambda r: q.lower() in (r["ma_phieu_kk"] + r["chi_nhanh"] + r["nhom_cha"]).lower(),
        axis=1)]

view = view.rename(columns={...})  # tiếng Việt column names
# Tính cột "Tiến độ" = sum(sl_thuc_te)/sum(ton_snapshot) * 100 (qua join trước)

selected = st.dataframe(
    view[["Mã Phiếu", "Chi Nhánh", "Nhóm Hàng", "Trạng Thái",
          "Người Tạo", "Ngày Tạo", "Tiến độ"]],
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Tiến độ": st.column_config.ProgressColumn(
            "Tiến độ", min_value=0, max_value=100, format="%d%%"
        ),
        "Trạng Thái": st.column_config.TextColumn("Trạng Thái", width="small"),
    },
    key="kk_manage_table",
)

sel_rows = selected.selection.rows if selected and hasattr(selected, "selection") else []
if sel_rows:
    selected_ma = view.iloc[sel_rows[0]]["Mã Phiếu"]
    st.session_state["kk_manage_selected"] = selected_ma
```

**Lưu ý**: `st.dataframe(on_select="rerun", ...)` yêu cầu Streamlit ≥1.35. Nếu cluster còn version thấp hơn, fallback dùng `st.radio` hoặc `st.selectbox` ở trên bảng (read-only display).

**Status + Progress trong native dataframe**:
- Status hiển thị dạng text + emoji vì native st.dataframe không render custom HTML cell:
  - `"🟡 Đang kiểm"` · `"🔵 Chờ duyệt"` · `"🟢 Đã duyệt"`
- Progress dùng `ProgressColumn` builtin (đã có sẵn green theme nếu CSS file override).

### 8.4 Detail panel — render dưới bảng khi có row được chọn

Tách thành function helper:

```python
def _kk_render_detail_panel(ma_phieu: str, status: str):
    p = _kk_get_phieu_header(ma_phieu)  # 1 query lấy header
    lines = _kk_get_lines(ma_phieu)
    if lines.empty:
        st.info("Phiếu này chưa có dữ liệu chi tiết.")
        return

    # Header card: status + mã + meta + action buttons
    st.html(_render_detail_header(p, status))  # 1 st.html() call, inline-styled

    a1, a2, a3 = st.columns([1.3, 1.3, 5])
    with a1:
        if status == "Đang kiểm":
            if st.button("▶ Quét tiếp phiếu này", type="primary",
                         use_container_width=True, key=f"go_{ma_phieu}"):
                st.session_state["kk_active_ma"] = ma_phieu
                st.toast(
                    f"Đã chọn {ma_phieu}. Bấm tab 'Quét kiểm kê' phía trên ↑",
                    icon="✨")
        elif status == "Chờ duyệt admin" and is_admin():
            if st.button("✓ Duyệt & chốt phiếu", type="primary",
                         use_container_width=True, key=f"approve_{ma_phieu}"):
                ok, msg = _kk_approve(ma_phieu)
                if ok: st.success(msg); st.rerun()
                else:  st.error(msg)
        else:
            st.download_button(...)  # Excel

    with a2:
        if status != "Đã duyệt":
            if st.button("🗑 Hủy phiếu", use_container_width=True,
                         key=f"cancel_{ma_phieu}"):
                ok, msg = _kk_cancel_phieu(ma_phieu)
                if ok: st.success(msg); st.rerun()

    # KPI tiles
    if status == "Chờ duyệt admin":
        _render_kpis_waiting(lines)   # 1 st.html() — 4 KPI tile inline-styled
    elif status == "Đang kiểm":
        _render_kpis_scanning(lines)  # 1 st.html() — 3 KPI tile inline-styled

    # Bảng chi tiết — native st.dataframe read-only
    view = lines.rename(columns={...})
    cols = ["Mã Hàng", "Tên Hàng", "Tồn Kho", "SL Thực Tế", "Lệch"]
    if status == "Chờ duyệt admin":
        cols.append("Giá trị lệch")
    st.dataframe(view[cols], use_container_width=True,
                 hide_index=True, height=320)
```

Gọi từ tab Quản lý:

```python
sel_ma = st.session_state.get("kk_manage_selected")
if sel_ma:
    phieu_row = df[df["ma_phieu_kk"] == sel_ma]
    if not phieu_row.empty:
        _kk_render_detail_panel(sel_ma, phieu_row.iloc[0]["trang_thai"])
else:
    # Empty state — inline-styled hint card
    st.html('''<div style="background:var(--surface);border:1px dashed var(--line);
        border-radius:14px;padding:36px 24px;margin-top:14px;text-align:center;
        color:var(--ink-3);">
      <div style="font-size:14px;font-weight:600;color:var(--ink-2);">
        Chưa chọn phiếu nào
      </div>
      <div style="font-size:13px;color:var(--ink-3);margin-top:4px;">
        Click vào một dòng trong bảng để xem chi tiết &amp; hành động
      </div>
    </div>''')
```

### 8.5 Visibility theo role
- Nút "✓ Duyệt" chỉ hiện khi `status == "Chờ duyệt admin"` và `is_admin()`.
- Filter chip "Chờ duyệt" vẫn hiện với staff (read-only detail panel, không có nút duyệt).
- Tất cả role đều xem được chi tiết phiếu đã duyệt.

---

## 9. Tab navigation — KHÔNG switch programmatically

**Pattern đã bỏ** (được đề xuất ban đầu nhưng disorient UX + risk auth bug):
- Đổi thứ tự tab dựa trên state — user thấy layout thay đổi bất thời.
- `st.query_params["kk_tab"] = ...; st.rerun()` — có nguy cơ full page reload → mất session → logout (đã gặp ở module Hoá đơn trước).

**Pattern dùng**:
- Thứ tự tab **cố định**: `tab_scan, tab_manage = st.tabs(["Quét kiểm kê", "Quản lý phiếu"])`. Không đổi trong runtime.
- Khi user click "▶ Quét tiếp phiếu này" ở detail panel:
  1. Set `st.session_state["kk_active_ma"] = ma_phieu` — phiếu đã "đánh dấu sẵn".
  2. Gọi `st.toast()` rõ ràng: `"Đã chọn KK000013. Bấm tab 'Quét kiểm kê' ở trên ↑ để bắt đầu."`
  3. User tự click tab Quét → selectbox phiếu auto-select theo `kk_active_ma`.
  4. Auto-focus ô quét khi vào tab.

```python
if status == "Đang kiểm":
    if st.button("▶ Quét tiếp phiếu này", type="primary", key=f"go_{ma_phieu}"):
        st.session_state["kk_active_ma"] = ma_phieu
        st.toast(
            f"Đã chọn {ma_phieu}. Bấm tab 'Quét kiểm kê' ở trên ↑ để bắt đầu.",
            icon="✨",
        )
```

**Trade-off**: thêm 1 click cho user. Đổi lại: layout ổn định, không hack query param, không risk mất session.

---

## 10. Interactions & behaviour summary

| Tương tác | Behavior |
|---|---|
| Mở tab Quét | Auto-focus ô input ngay |
| Click vào vùng trống | Re-focus ô input (cho user dùng máy quét bị mất focus) |
| Gõ mã + Enter / máy quét bắn | Form submit → lookup → update card + table → beep |
| Mã tồn tại trong phiếu | +1 vào `sl_quet` + `sl_thuc_te`, dòng nhảy lên đầu, flash xanh |
| Mã không có trong phiếu nhưng có trong master | Chèn dòng mới "Phát sinh", show toast "Phát sinh mới: <mã>" |
| Mã không tồn tại hoàn toàn | Flash đỏ + beep 220Hz × 2 + show error overlay với `'Mã XYZ' không tồn tại` |
| Click chip filter | Lọc bảng, không rerun toàn module |
| Nháy đúp ô SL Thực tế | Edit mode (st.data_editor đã có sẵn) |
| Click "Hoàn thành kiểm kê" | Gọi `_kk_complete()`, chuyển trạng thái phiếu |
| Click "+ Tạo phiếu" trên Quản lý tab | Mở `st.dialog()` form |
| Click "▶ Quét tiếp" ở detail panel | Set `kk_active_ma` + `st.toast()` cue — user tự click tab Quét (KHÔNG switch tự động) |
| Click row trong bảng Quản lý phiếu | Render detail panel phía dưới qua `on_select="rerun"` của st.dataframe |
| Click "✓ Duyệt" (admin) | Gọi `_kk_approve()` (RPC atomic) |
| Click "🗑 Hủy phiếu" | Confirm dialog → `_kk_cancel_phieu()` |

---

## 11. State management

```python
st.session_state["kk_active_ma"]      # str — mã phiếu đang được chọn
st.session_state["kk_last_scan"]      # dict — info dòng vừa quét (cho hero card)
st.session_state["kk_flash"]          # str | None — "ok" / "bad" / None, dùng 1 lần rồi pop
st.session_state["kk_filter"]         # str — "all" / "lech" / "khop" / "chua"
st.session_state["kk_create_count"]   # int — counter để reset form Tạo (đã có)
st.session_state["kk_show_create"]    # bool — toggle dialog Tạo phiếu
```

---

## 12. Acceptance criteria

- [ ] Module chỉ hiển thị **2 tab** ("Quét kiểm kê", "Quản lý phiếu") thay vì 4.
- [ ] Hero scan card hiển thị đủ 7 thông tin: Mã hàng (mono lớn), Tên hàng, Mã vạch, Giá bán (VNĐ), SL đã quét, Tồn hệ thống, Lệch tạm (đổi màu theo dấu).
- [ ] Bắn máy quét USB → ô input nhận chuỗi + Enter → form submit → card + table update. **Thời gian end-to-end được đo và document trong PR** — optimize nếu còn cơ hội, không cam kết target cụ thể (latency Streamlit Cloud + Supabase + VN network đã 150-300ms).
- [ ] Thứ tự tab cố định, không đổi dựa trên state.
- [ ] **Style discipline**: mọi content element (`<div>`/`<span>`/`<section>`/...) trong `st.html()` dùng inline `style="..."` với `var(--token)`. KHÔNG dùng class. Chỉ `<button>`/`<input>`/`<select>`/`<textarea>` (Streamlit native widgets) mới được dùng class.
- [ ] Tab Quản lý phiếu: native `st.dataframe(on_select="rerun", selection_mode="single-row")`. Click row → detail panel render phía dưới (KHÔNG có button trong row).
- [ ] Click "▶ Quét tiếp phiếu này" ở detail panel → `st.toast()` + set `kk_active_ma`. User tự click tab Quét (KHÔNG tự động switch).
- [ ] Quét thành công: beep cao 880Hz + flash xanh card + dòng nhảy lên đầu bảng.
- [ ] Quét sai (mã không tồn tại): beep thấp đôi (220Hz×2) + flash đỏ card + error overlay.
- [ ] Auto-focus ô quét sau mỗi lần submit và khi click vùng trống.
- [ ] Filter chip trên cả 2 tab hoạt động (giữ logic phiếu hiện tại).
- [ ] Tab Quản lý phiếu: action button theo trạng thái ở **detail panel** (Quét tiếp / Duyệt / Excel / Hủy) — KHÔNG ở trong row.
- [ ] "+ Tạo phiếu mới" mở `st.dialog()` modal, không phải sub-tab.
- [ ] Click "▶ Quét tiếp" ở detail panel → toast + `kk_active_ma` set. (KHÔNG tự động switch tab.)
- [ ] Detail panel phiếu Chờ duyệt: 4 KPI (Tổng thực tế, Lệch tăng, Lệch giảm, Giá trị lệch) + bảng chi tiết + nút Duyệt (chỉ admin) + Hủy.
- [ ] Color accent đổi từ đỏ → xanh lá `#047857`. Font: Plus Jakarta Sans + JetBrains Mono cho số/code.
- [ ] **KHÔNG có hồi quy về backend**: Supabase queries, RPC, log_action behavior y nguyên.
- [ ] Toàn bộ 8 hàm helper `_kk_*` ở đầu file giữ nguyên signature.

---

## 13. Implementation order suggestion

1. **Setup design tokens** — inject `_CSS_VARS_BLOCK` (`:root` variables + `@keyframes`) qua `st.markdown(unsafe_allow_html=True)` 1 lần ở đầu `module_kiem_ke()`.
2. **`static/kiem_ke.css`** — font import + native widget overrides target `[data-testid="stButton"] button`, `[data-testid="stTextInput"] input`, `[data-testid="stDataFrame"] thead th`, etc.
3. **Skeleton 2 tab cố định** — `tab_scan, tab_manage = st.tabs(["Quét kiểm kê", "Quản lý phiếu"])`. Không đổi thứ tự.
4. **Hero scan card** — copy markup từ `Kiem_ke_Hi-fi_v2.html` vào helper `_hero_scan_card()`, rút info từ `st.session_state["kk_last_scan"]`.
5. **Scan flow** — tách lookup khỏi write, set `kk_last_scan` + `kk_flash` trong session_state. Inject beep + auto-focus JS sau mỗi rerun.
6. **Filter chips + context bar + KPI tiles** — inline-styled `st.html()`.
7. **Tab Quản lý phiếu** — native `st.dataframe(on_select="rerun")` + helper `_kk_render_detail_panel()`.
8. **`@st.dialog` Tạo phiếu** — extract form từ tab `tab_create` cũ.
9. **Toast cue cho "Quét tiếp"** — `st.toast()` + set `kk_active_ma`. KHÔNG tự động switch tab.
10. **QA** — verify với máy quét thật trên Streamlit Cloud preview, đo thời gian scan round-trip, document trong PR.

---

## 14. Files trong bundle này

| File | Mục đích |
|---|---|
| `README.md` | (this file) Spec đầy đủ để implement |
| **`Kiem_ke_Hi-fi_v2.html`** | **Source of truth visual + interaction** — markup inline-style thuần, copy paste được vào `st.html()`. Đây là file phải theo. |
| `Kiem_ke_Hi-fi.html` | (deprecated v1) Dùng class CSS — KHÔNG copy markup. Giữ để tham khảo phương hướng visual. |
| `Kiem_ke_Wireframes.html` | 4 phương án wireframe đã khám phá. Đã chốt **Phương án A**. B/C/D giữ tham khảo. |
| `kiem_ke_current.py` | Code Streamlit hiện tại (575 dòng). **Đây là logic phải bảo toàn 100%.** |
| `design_system_constraints.md` | Streamlit constraint từ design system (CSS isolation, sanitizer, etc.) |

---

## 15. Notes for developer

- **Không có local repo để chạy `streamlit run`** trên dev machine của user → mọi verification phải qua GitHub PR review hoặc Streamlit Cloud preview branch. Branch test deploy lên Cloud rồi user test máy quét thật trên đó.
- Khi mở PR, paste screenshot trước/sau từng tab vào PR description.
- Nếu phát hiện constraint Streamlit khác lúc implement (vd. `st.dialog` không có trong version đang dùng), comment lại trong PR — fallback sang `st.expander` hoặc `st.container` sticky-style.
- Test với cả role staff và admin để verify visibility của nút Duyệt.

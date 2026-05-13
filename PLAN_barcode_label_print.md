# PLAN — Barcode Label Printing (DLW App)

**Feature:** In tem mã vạch hàng loạt giống KiotViet web
**Date:** 13/05/2026
**Workflow:** Phase A planning (file này) → Phase B execute với Claude Code

---

## 1. Mục tiêu

Cho phép user in tem mã vạch cho 1 hoặc nhiều SP cùng lúc, với SL tem chỉnh được cho từng SP. Wire ở 2 entry point:
- **Hàng hóa** (chính): chọn N SP → in tem
- **Nhập NCC** (phụ): sau khi lưu phiếu → in tem cho hàng vừa nhập, SL auto = SL nhập

Tem khổ **35×22mm × 2 tem/dòng**, in qua **browser print dialog** (đơn giản, dùng được mọi máy in tem trên hệ điều hành — Xprinter XP-350B hiện tại + máy in PVC sau này).

## 2. Decisions đã chốt

| # | Quyết định | Lý do |
|---|------------|-------|
| 1 | Khổ tem `35x22mm × 2 tem/dòng` (page `70mm × 22mm`) | Đồng hồ tên dài, cần chiều rộng |
| 2 | Browser-print (HTML + `window.print()`) | Không phụ thuộc daemon, multi-CN dùng được |
| 3 | Entry points: Hàng hóa + Nhập NCC | Cover 90% use case |
| 4 | Tem content: **Tên SP (wrap 2 dòng) + Giá + Barcode** (không có "DL WATCH") | Tem nhỏ, ưu tiên info cần thiết |
| 5 | Permission: **mọi NV đều in được** | Operational task |
| 6 | Symbology: `Code128` default, dropdown switchable → `QR / DataMatrix` | Future-proof QR/DataMatrix |
| 7 | Library: **`bwip-js`** (Pure JS, hỗ trợ Code128 + QR + DataMatrix + EAN/UPC) | 1 lib cho mọi symbology |
| 8 | Fallback `ma_vach` → `ma_hang` nếu NULL | Theo decision (b) |
| 9 | Truncate tên: cứng max ~36 chars (2 dòng × ~18 chars) + "..." | Đơn giản, theo decision (a) |

## 3. Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│ User flow                                                       │
│                                                                 │
│ Hàng hóa: multi-select SP                                       │
│        ↓                                                        │
│ [🏷️ In tem mã vạch (N)] → @st.dialog config                    │
│                            ├─ Bảng SL tem mỗi SP (default 1)    │
│                            ├─ Dropdown symbology                │
│                            └─ [📂 Mở trang in] ──┐              │
│                                                  ↓              │
│ Nhập NCC: chi tiết phiếu          components.html(...)          │
│        ↓                          ↓ click button                │
│ [🏷️ In tem theo phiếu]            window.open('', '_blank')     │
│ auto qty = SL nhập                .document.write(<full HTML>)  │
│        ↓                          ↓                             │
│   (cùng dialog)                  Tab mới (no Streamlit chrome)  │
│                                   ↓ onload                      │
│                                   bwip-js render N canvas       │
│                                   ↓                             │
│                                   window.print() (auto)         │
└─────────────────────────────────────────────────────────────────┘
```

## 4. Files affected

```
utils/barcode_label.py           ★ MỚI       ~200 lines
modules/hang_hoa.py              edit        +~120 lines (dialog + state)
modules/nhap_hang.py             edit        +~80 lines  (dialog + state)
```

**Không đụng:**
- DB schema (không cần migration)
- RPC nào (in tem là client-side, không write DB)
- `print_queue` (đó là daemon K80, độc lập)
- POS repo (DLW-only feature, POS không cần)

**Shared với POS sau này?** Không. POS bán hàng, không cần in tem cho hàng hóa.

## 5. Phase 1 — utils/barcode_label.py (file mới)

### 5.1 Spec module

Public API:

```python
def build_label_html(
    items: list[dict],       # [{ma_hang, ten_hang, gia_ban, ma_vach, qty}]
    symbology: str = 'code128',
) -> str:
    """Return full HTML page string. Tab in sẽ document.write(this)."""

def get_barcode_value(item: dict) -> str:
    """Fallback ma_vach → ma_hang. Strip whitespace."""

def truncate_name(text: str, max_chars: int = 36) -> str:
    """Truncate cứng + '...'. CSS sẽ wrap 2 dòng tự nhiên."""

def fmt_price(value) -> str:
    """Format giá VND không có 'đ' (tiết kiệm chỗ): '2.450.000'"""

SYMBOLOGY_OPTIONS = {
    'code128': 'Code128 (mặc định)',
    'qrcode': 'QR Code',
    'datamatrix': 'DataMatrix',
}
```

### 5.2 Full source code

```python
# utils/barcode_label.py
"""
In tem mã vạch — generate HTML page render bằng bwip-js, in qua window.print().
Khổ tem mặc định: 35x22mm × 2 tem/dòng (page 70x22mm).
"""
import html as _html
import json

# === CONSTANTS ===
LABEL_WIDTH_MM = 35
LABEL_HEIGHT_MM = 22
LABELS_PER_ROW = 2
PAGE_WIDTH_MM = LABEL_WIDTH_MM * LABELS_PER_ROW  # 70mm

MAX_NAME_CHARS = 36  # 2 dòng × ~18 chars, CSS wrap tự nhiên

SYMBOLOGY_OPTIONS = {
    'code128':    'Code128 (mặc định)',
    'qrcode':     'QR Code',
    'datamatrix': 'DataMatrix',
}

# bwip-js render config per symbology
_BWIP_CONFIG = {
    'code128':    {'scale': 2, 'height': 8,  'includetext': True,  'textsize': 7},
    'qrcode':     {'scale': 3, 'includetext': False},
    'datamatrix': {'scale': 3, 'includetext': False},
}

# CDN — verify version mới nhất tại https://github.com/metafloor/bwip-js trước deploy
BWIP_CDN = 'https://cdn.jsdelivr.net/npm/bwip-js@4.5.1/dist/bwip-js-min.js'


# === HELPERS ===
def get_barcode_value(item: dict) -> str:
    """Fallback ma_vach → ma_hang."""
    v = (item.get('ma_vach') or '').strip()
    if v:
        return v
    return (item.get('ma_hang') or '').strip()


def truncate_name(text: str, max_chars: int = MAX_NAME_CHARS) -> str:
    if not text:
        return ''
    text = str(text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + '...'


def fmt_price(value) -> str:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return '0'
    if n <= 0:
        return '0'
    return f'{n:,}'.replace(',', '.')


# === HTML BUILDER ===
def build_label_html(items: list[dict], symbology: str = 'code128') -> str:
    """
    items: [{ma_hang, ten_hang, gia_ban, ma_vach, qty}]
    Returns full HTML string for new tab.
    """
    if symbology not in _BWIP_CONFIG:
        symbology = 'code128'

    # Expand by qty
    labels_data = []
    for it in items:
        qty = max(1, int(it.get('qty', 1) or 1))
        barcode_val = get_barcode_value(it)
        if not barcode_val:
            continue  # Skip SP không có mã nào
        labels_data.append({
            'name':    truncate_name(it.get('ten_hang', '')),
            'price':   fmt_price(it.get('gia_ban')),
            'barcode': barcode_val,
            'qty':     qty,
        })

    # Render label divs
    label_divs = []
    for ld in labels_data:
        for _ in range(ld['qty']):
            label_divs.append(_render_label_div(ld))
    body_inner = '\n'.join(label_divs)

    bwip_cfg = _BWIP_CONFIG[symbology]
    bwip_cfg_js = json.dumps({'bcid': symbology, **bwip_cfg})

    return _PAGE_TEMPLATE.format(
        page_width=PAGE_WIDTH_MM,
        label_width=LABEL_WIDTH_MM,
        label_height=LABEL_HEIGHT_MM,
        body_inner=body_inner,
        bwip_cdn=BWIP_CDN,
        bwip_cfg_js=bwip_cfg_js,
        total_labels=len(label_divs),
    )


def _render_label_div(ld: dict) -> str:
    """Render 1 ô tem (chứa name + price + canvas barcode)."""
    name_safe = _html.escape(ld['name'])
    price_safe = _html.escape(ld['price'])
    barcode_safe = _html.escape(ld['barcode'])
    return (
        f'<div class="label">'
        f'<div class="name">{name_safe}</div>'
        f'<div class="price">{price_safe}</div>'
        f'<canvas class="bc" data-text="{barcode_safe}"></canvas>'
        f'</div>'
    )


# === HTML TEMPLATE ===
_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>In tem mã vạch — {total_labels} tem</title>
<style>
  @page {{
    size: {page_width}mm {label_height}mm;
    margin: 0;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    font-family: Arial, sans-serif;
    background: #f0f0f0;
  }}
  .sheet {{
    display: flex;
    flex-wrap: wrap;
    width: {page_width}mm;
    margin: 0 auto;
    background: white;
  }}
  .label {{
    width: {label_width}mm;
    height: {label_height}mm;
    padding: 1mm 1.5mm;
    border: 0.2mm dashed #ccc;  /* preview only, in ra không thấy */
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: center;
    overflow: hidden;
    page-break-inside: avoid;
  }}
  .label .name {{
    font-size: 7pt;
    line-height: 1.05;
    text-align: center;
    word-break: break-word;
    max-height: 8mm;
    overflow: hidden;
  }}
  .label .price {{
    font-size: 8pt;
    font-weight: 700;
    line-height: 1;
  }}
  .label .bc {{
    max-width: 33mm;
    max-height: 9mm;
  }}
  /* Preview controls — ẩn khi in */
  .toolbar {{
    position: fixed;
    top: 8px; right: 8px;
    background: #222; color: white;
    padding: 8px 12px; border-radius: 6px;
    font-size: 13px; z-index: 9999;
    font-family: sans-serif;
  }}
  .toolbar button {{
    background: #4caf50; color: white; border: 0;
    padding: 4px 10px; border-radius: 4px; cursor: pointer;
    margin-left: 6px; font-size: 13px;
  }}
  @media print {{
    .toolbar {{ display: none !important; }}
    .label {{ border: none; }}
    body {{ background: white; }}
  }}
</style>
</head>
<body>
<div class="toolbar">
  Tổng: {total_labels} tem
  <button onclick="window.print()">🖨 In</button>
  <button onclick="window.close()">✕ Đóng</button>
</div>
<div class="sheet">{body_inner}</div>
<script src="{bwip_cdn}"></script>
<script>
  const cfg = {bwip_cfg_js};
  window.addEventListener('load', () => {{
    document.querySelectorAll('canvas.bc').forEach(c => {{
      try {{
        bwipjs.toCanvas(c, Object.assign({{}}, cfg, {{ text: c.dataset.text }}));
      }} catch (e) {{
        c.outerHTML = '<div style="color:red;font-size:6pt">ERR: ' + (c.dataset.text || '') + '</div>';
      }}
    }});
    // Auto print sau khi render xong
    setTimeout(() => window.print(), 600);
  }});
</script>
</body>
</html>
"""
```

### 5.3 Smoke test Phase 1

Tạo `scratch_test_barcode.py` ở root project:

```python
from utils.barcode_label import build_label_html

items = [
    {'ma_hang': 'CSO-MTP001', 'ten_hang': 'CASIO MTP-V006L-1B đồng hồ nam dây da', 'gia_ban': 2450000, 'ma_vach': '8901234567890', 'qty': 2},
    {'ma_hang': 'SK-NK01',    'ten_hang': 'Seiko 5 Sports SRPD53K1',                    'gia_ban': 8500000, 'ma_vach': None,           'qty': 1},
    {'ma_hang': 'SHORT',      'ten_hang': 'Casio',                                       'gia_ban': 500000,  'ma_vach': '',             'qty': 3},
]
html = build_label_html(items, symbology='code128')
with open('/tmp/preview.html', 'w', encoding='utf-8') as f:
    f.write(html)
print(f"OK — wrote {len(html)} chars. Open /tmp/preview.html in browser.")
```

**Acceptance Phase 1:**
- [ ] File mở được trong browser
- [ ] Đếm đúng 2 + 1 + 3 = 6 tem
- [ ] Tem 1 hiển thị tên truncate đúng
- [ ] Tem 2 fallback dùng `SK-NK01` làm barcode
- [ ] Code128 render rõ, không bị dính vạch
- [ ] In ra Xprinter: tem nằm đúng vị trí, không lệch (CHỈ test khi có máy in)
- [ ] Switch `symbology='qrcode'` → QR vuông render OK
- [ ] Switch `symbology='datamatrix'` → DM vuông render OK

→ **Commit `feat: add barcode label helper (utils/barcode_label.py)`**

---

## 6. Phase 2 — modules/hang_hoa.py wire button

### 6.1 Pre-flight verify

Trước khi sửa, đọc file để biết:

```bash
grep -n "tab" modules/hang_hoa.py | head -30        # cấu trúc tabs
grep -n "def " modules/hang_hoa.py | head -40       # functions hiện tại
grep -n "st.dataframe\|st.data_editor" modules/hang_hoa.py  # cách render bảng SP
grep -n "selection\|on_select" modules/hang_hoa.py  # đã có multi-select chưa?
```

**Câu hỏi cần xác nhận từ output:**
- Tab Danh sách đang dùng `st.dataframe` (read-only) hay `st.data_editor`?
- Có column checkbox sẵn không, hay phải thêm `selection_mode="multi-row"`?

Nếu **chưa có multi-select**, dùng `st.dataframe(..., on_select="rerun", selection_mode="multi-row")` — Streamlit ≥ 1.35.

### 6.2 Pattern wire (template)

Đặt sau bảng SP trong tab Danh sách:

```python
# === BUTTON IN TEM ===
selected_rows = event.selection.rows if event.selection else []
n_sel = len(selected_rows)

col_btn1, col_btn2 = st.columns([1, 5])
with col_btn1:
    if st.button(
        f"🏷️ In tem mã vạch{f' ({n_sel})' if n_sel else ''}",
        disabled=(n_sel == 0),
        key="hh_btn_in_tem",
        use_container_width=True,
    ):
        # Lưu selected SP vào state, mở dialog
        st.session_state["_hh_in_tem_items"] = [
            df.iloc[idx].to_dict() for idx in selected_rows
        ]
        _dlg_in_tem_hh()

@st.dialog("🏷️ In tem mã vạch", width="large")
def _dlg_in_tem_hh():
    items = st.session_state.get("_hh_in_tem_items", [])
    if not items:
        st.warning("Chưa chọn sản phẩm nào.")
        return
    _render_dialog_in_tem(items, dialog_key="hh")
```

### 6.3 Shared dialog function (đặt cuối file hang_hoa.py)

```python
def _render_dialog_in_tem(items: list[dict], dialog_key: str):
    """Shared dialog cho cả hang_hoa và nhap_hang."""
    from utils.barcode_label import build_label_html, SYMBOLOGY_OPTIONS, get_barcode_value
    import streamlit.components.v1 as components

    # 1. Dropdown symbology
    symb_key = f"_intem_{dialog_key}_symb"
    symb = st.selectbox(
        "Loại mã vạch",
        options=list(SYMBOLOGY_OPTIONS.keys()),
        format_func=lambda k: SYMBOLOGY_OPTIONS[k],
        index=0,
        key=symb_key,
    )

    # 2. Bảng SL tem
    st.caption(f"Tổng {len(items)} SP đã chọn. Chỉnh SL tem cho từng SP:")
    qty_key = f"_intem_{dialog_key}_qty"
    if qty_key not in st.session_state:
        st.session_state[qty_key] = {it['ma_hang']: int(it.get('qty', 1) or 1) for it in items}

    # Cảnh báo SP không có mã
    no_code = [it for it in items if not get_barcode_value(it)]
    if no_code:
        st.error(f"❌ {len(no_code)} SP không có Mã vạch lẫn Mã hàng — sẽ bị bỏ qua: " +
                 ", ".join(it.get('ten_hang','?')[:25] for it in no_code[:5]))

    # Editable qty grid
    import pandas as pd
    rows = []
    for it in items:
        mh = it['ma_hang']
        rows.append({
            'Mã hàng':  mh,
            'Tên':      (it.get('ten_hang') or '')[:40],
            'Giá':      int(it.get('gia_ban') or 0),
            'Mã vạch':  it.get('ma_vach') or '(dùng mã hàng)',
            'SL tem':   st.session_state[qty_key].get(mh, 1),
        })
    df_q = pd.DataFrame(rows)
    edited = st.data_editor(
        df_q,
        column_config={
            'SL tem': st.column_config.NumberColumn(min_value=0, max_value=999, step=1),
            'Giá':    st.column_config.NumberColumn(format="%d", disabled=True),
            'Mã hàng':  st.column_config.TextColumn(disabled=True),
            'Tên':      st.column_config.TextColumn(disabled=True),
            'Mã vạch':  st.column_config.TextColumn(disabled=True),
        },
        hide_index=True,
        key=f"_intem_{dialog_key}_editor",
        use_container_width=True,
    )
    # Save back
    for _, r in edited.iterrows():
        st.session_state[qty_key][r['Mã hàng']] = int(r['SL tem'] or 0)

    total = sum(st.session_state[qty_key].values())
    st.info(f"📋 Tổng số tem sẽ in: **{total}**")

    # 3. Nút Mở trang in
    if st.button("📂 Mở trang in", type="primary", disabled=(total == 0), key=f"_intem_{dialog_key}_go"):
        # Build payload + render component trigger window.open
        payload_items = [
            {**it, 'qty': st.session_state[qty_key].get(it['ma_hang'], 0)}
            for it in items
            if st.session_state[qty_key].get(it['ma_hang'], 0) > 0
        ]
        html_content = build_label_html(payload_items, symbology=symb)
        # Embed component: button + JS opens new tab + document.write
        _trigger_print_window(html_content)


def _trigger_print_window(html_content: str):
    """Render hidden component that auto-opens new tab with HTML."""
    import streamlit.components.v1 as components
    import json
    # JS-escape via JSON
    safe = json.dumps(html_content)
    components.html(f"""
        <script>
        (function() {{
          const html = {safe};
          const w = window.open('', '_blank');
          if (!w) {{
            document.body.innerHTML = '<div style="color:red;padding:10px;font-family:sans-serif">'
              + '⚠️ Trình duyệt chặn popup. Cho phép popup cho trang này rồi thử lại.'
              + '</div>';
            return;
          }}
          w.document.open();
          w.document.write(html);
          w.document.close();
        }})();
        </script>
        <div style="color:#4caf50;font-family:sans-serif;padding:6px">
          ✅ Đã mở tab in. Kiểm tra tab mới.
        </div>
    """, height=40)
```

### 6.4 Smoke test Phase 2

1. Mở Hàng hóa → tab Danh sách
2. Chọn 3 SP bằng checkbox/multi-select
3. Bấm "🏷️ In tem mã vạch (3)" → dialog mở
4. Verify bảng SL tem hiển thị đúng 3 SP, default qty=1
5. Chỉnh SL: SP1 = 2, SP2 = 5, SP3 = 0
6. Total = 7 tem
7. Bấm "📂 Mở trang in" → tab mới mở, hiển thị 7 ô tem
8. Tab tự bật print dialog sau 600ms
9. Cancel print dialog → tab giữ nguyên, có nút "🖨 In" và "✕ Đóng" góc phải
10. Test với 1 SP có `ma_vach=NULL` → barcode dùng `ma_hang`
11. Test switch symbology → tab in mới hiển thị QR/DataMatrix

→ **Commit `feat: wire barcode label print button in hang_hoa module`**

---

## 7. Phase 3 — modules/nhap_hang.py wire button

### 7.1 Pre-flight verify

```bash
grep -n "def " modules/nhap_hang.py | head -30
grep -n "phieu_nhap_hang\|_ct\|chi_tiet" modules/nhap_hang.py
grep -n "tab\|expander" modules/nhap_hang.py
```

**Xác định:** sau khi user lưu/xem chi tiết 1 phiếu nhập, có hàm/section nào render danh sách items không? Wire button vào đó.

### 7.2 Pattern wire

Sau bảng chi tiết items của phiếu nhập (lookup theo `ma_phieu` → `phieu_nhap_hang_ct`):

```python
# Sau bảng items
if st.button("🏷️ In tem theo phiếu", key=f"nh_in_tem_{ma_phieu}"):
    # Build items list với qty = SL nhập
    items_for_print = []
    for ct in chi_tiet_items:  # tên biến tùy code hiện tại
        items_for_print.append({
            'ma_hang':  ct['ma_hang'],
            'ten_hang': ct['ten_hang'],
            'gia_ban':  ct.get('gia_ban') or 0,  # JOIN từ hang_hoa nếu chưa có
            'ma_vach':  ct.get('ma_vach'),
            'qty':      int(ct['so_luong']),
        })
    st.session_state["_nh_in_tem_items"] = items_for_print
    _dlg_in_tem_nh()

@st.dialog("🏷️ In tem theo phiếu nhập", width="large")
def _dlg_in_tem_nh():
    items = st.session_state.get("_nh_in_tem_items", [])
    if not items:
        st.warning("Phiếu rỗng.")
        return
    # Import shared dialog từ hang_hoa
    from modules.hang_hoa import _render_dialog_in_tem
    _render_dialog_in_tem(items, dialog_key="nh")
```

**Lưu ý:** `phieu_nhap_hang_ct` có thể không có `gia_ban` và `ma_vach` — cần JOIN với `hang_hoa` khi load chi_tiet. Hoặc enrich trong Python sau khi load. Verify pre-flight.

### 7.3 Smoke test Phase 3

1. Mở Nhập NCC → chọn 1 phiếu vừa nhập (5-10 items)
2. Verify nút "🏷️ In tem theo phiếu" hiện ở section chi tiết
3. Bấm → dialog mở với qty auto-fill = SL nhập từng dòng
4. Bấm "📂 Mở trang in" → tab mới có đúng số tem = tổng SL nhập
5. Test edge: phiếu chỉ có SP có `is_open_price=true` (SPK/DVPS) → vẫn in được vì barcode dùng `ma_hang`

→ **Commit `feat: wire barcode label print button in nhap_hang module`**

---

## 8. Edge cases & guard rails

| Case | Behavior |
|------|----------|
| SP `active=False` | Không hiện trong list chọn (hang_hoa đã filter) — không cần xử thêm |
| `ma_vach=NULL` và `ma_hang=NULL` | Skip + cảnh báo đỏ trong dialog |
| `gia_ban=0` hoặc NULL | Hiển thị `0` (user có thể chọn không in giá nếu cần — Phase 2 mở rộng) |
| Tên SP > 36 chars | Truncate cứng + `...` |
| `qty=0` | Skip SP đó (không xuất tem) |
| Tổng tem > 500 | Cho phép, nhưng `st.warning` "Số tem lớn, browser có thể chậm" |
| Browser block popup | Component hiển thị message đỏ hướng dẫn cho phép popup |
| Tên SP chứa `<script>` hoặc HTML | `html.escape` đã handle trong `_render_label_div` |
| Code128 + ma_vach chứa Unicode | Code128 không hỗ trợ — bwip-js sẽ throw, catch → hiển thị "ERR: ..." trong ô tem. User nên switch DataMatrix |

## 9. Rollback strategy

| Phase | Cách rollback |
|-------|---------------|
| Phase 1 | `git rm utils/barcode_label.py` — file standalone, không ai import |
| Phase 2 | `git checkout HEAD -- modules/hang_hoa.py` — patch độc lập |
| Phase 3 | `git checkout HEAD -- modules/nhap_hang.py` |

Mỗi phase = 1 commit riêng → revert dễ.

## 10. Known unknowns / cần verify trước khi execute

1. **bwip-js version chính xác** — verify mới nhất tại https://github.com/metafloor/bwip-js. Nếu CDN jsdelivr không work, fallback `https://unpkg.com/bwip-js/dist/bwip-js-min.js`.
2. **`hang_hoa` tab Danh sách**: đang dùng `st.dataframe` selection mode nào? Cần đọc code thực tế ở Phase B pre-flight.
3. **`nhap_hang` chi_tiet**: có sẵn `gia_ban` và `ma_vach` trong bảng chi tiết không, hay phải JOIN với `hang_hoa`? Pre-flight verify.
4. **Streamlit version**: `selection_mode="multi-row"` cần Streamlit ≥ 1.35. Verify `requirements.txt`.
5. **Xprinter XP-350B page setup**: user phải set "Tem 70x22mm" trong driver Windows TRƯỚC khi in. Hướng dẫn này nằm ngoài scope code, note cho user.

## 11. Out of scope (defer)

- Toggle bật/tắt hiển thị **Giá** trên tem (nice-to-have)
- Lưu **template** in tem yêu thích (qty preset, symbology)
- In tem từ **Chuyển hàng** (nice-to-have, có thể wire sau với cùng pattern)
- In tem **A4 với multi-row** cho phép in tem dán giấy không phải máy in tem chuyên dụng
- Logging `action_logs` cho mỗi lần in (in tem là internal, không cần audit)
- Báo cáo "Đã in bao nhiêu tem tháng này" (không có business value)

## 12. Phase B execute checklist (cho Claude Code)

```
[ ] Đọc PLAN.md này đầu session
[ ] Pre-flight verify (mục 6.1, 7.1)
[ ] Phase 1: tạo utils/barcode_label.py + scratch_test_barcode.py + smoke test
[ ] Commit Phase 1
[ ] Phase 2: patch modules/hang_hoa.py (button + dialog + shared helper)
[ ] Smoke test Phase 2 trên local
[ ] Commit Phase 2
[ ] Phase 3: patch modules/nhap_hang.py (button + dialog reuse)
[ ] Smoke test Phase 3 trên local
[ ] Commit Phase 3
[ ] Test end-to-end với Xprinter thật (ở CN 100 LQĐ): in 5 tem, đo lệch, kiểm vạch
[ ] Update AI_CONTEXT.md đoạn "★ MỚI (13/05/2026)"
```

## 13. Estimate

- Phase 1: ~30 phút (file mới, smoke test HTML preview)
- Phase 2: ~45 phút (dialog state + multi-select, có thể tốn thời gian align UI với code hiện tại)
- Phase 3: ~20 phút (reuse Phase 2 dialog)
- Test thực với máy in: ~15 phút (user)
- **Total: ~2 giờ** (không tính waiting time của user test)

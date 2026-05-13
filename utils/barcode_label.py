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

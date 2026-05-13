"""Smoke test Phase 1 — ghi /tmp/preview.html để mở trong browser kiểm tra.

Chạy: python scratch_test_barcode.py
Kỳ vọng: 2 + 1 + 3 = 6 tem, SP2 fallback dùng ma_hang làm barcode.
"""
from utils.barcode_label import build_label_html

items = [
    {'ma_hang': 'CSO-MTP001', 'ten_hang': 'CASIO MTP-V006L-1B đồng hồ nam dây da', 'gia_ban': 2450000, 'ma_vach': '8901234567890', 'qty': 2},
    {'ma_hang': 'SK-NK01',    'ten_hang': 'Seiko 5 Sports SRPD53K1',               'gia_ban': 8500000, 'ma_vach': None,           'qty': 1},
    {'ma_hang': 'SHORT',      'ten_hang': 'Casio',                                  'gia_ban': 500000,  'ma_vach': '',             'qty': 3},
]
html = build_label_html(items, symbology='code128')
with open('/tmp/preview.html', 'w', encoding='utf-8') as f:
    f.write(html)
print(f"OK — wrote {len(html)} chars. Open /tmp/preview.html in browser.")

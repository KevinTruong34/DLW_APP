import streamlit as st
import pandas as pd
import base64
from datetime import datetime, timedelta


def _normalize(text: str) -> str:
    """Fuzzy search: bỏ space/dash/dot → 'F 94' khớp 'F94'."""
    import re
    return re.sub(r"[\s\-_./]", "", str(text)).upper()




def _build_phieu_html(phieu: dict, ct: pd.DataFrame) -> str:
    """Tạo HTML phiếu sửa chữa A5 dọc để in."""
    tong_in   = int((ct["so_luong"] * ct["don_gia"]).sum()) if not ct.empty else 0
    con_lai   = tong_in - int(phieu.get("khach_tra_truoc", 0))
    rows_html = ""
    if not ct.empty:
        for _, r in ct.iterrows():
            tt = int(r["so_luong"]) * int(r["don_gia"])
            rows_html += (
                f"<tr><td>{r.get('ten_hang','')}</td>"
                f"<td class='c'>{int(r['so_luong'])}</td>"
                f"<td class='r'>{int(r['don_gia']):,}</td>"
                f"<td class='r'>{tt:,}</td></tr>"
            ).replace(",", ".")
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
  @page {{ size: A5 portrait; margin: 10mm 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: Arial, sans-serif; font-size: 13px; color: #000; margin:0; }}
  h2 {{ text-align:center; font-size:16px; font-weight:700; margin:0 0 2px; }}
  .sub {{ text-align:center; font-size:12px; color:#444; margin-bottom:10px; }}
  .info {{ width:100%; border-collapse:collapse; margin-bottom:8px; }}
  .info td {{ padding:3px 4px; font-size:13px; vertical-align:top; }}
  .info .lbl {{ font-weight:700; white-space:nowrap; width:22%; }}
  .info .val {{ width:28%; }}
  .svc {{ width:100%; border-collapse:collapse; margin-top:6px; }}
  .svc th {{ background:#eee; border:1px solid #aaa; padding:4px 5px; font-size:12px; }}
  .svc td {{ border:1px solid #aaa; padding:4px 5px; font-size:12px; }}
  .c {{ text-align:center; }}
  .r {{ text-align:right; }}
  .total-row td {{ font-weight:700; background:#f7f7f7; }}
  .sign {{ display:flex; justify-content:space-between; margin-top:20px; font-size:12px; }}
  .sign div {{ text-align:center; width:45%; }}
  hr {{ border:none; border-top:1px solid #ccc; margin:8px 0; }}
</style></head><body>
<h2>PHIẾU TIẾP NHẬN SỬA CHỮA</h2>
<div class='sub'>Mã: <b>{phieu.get('ma_phieu','')}</b> &nbsp;·&nbsp; {phieu.get('Ngày TN','')}</div>
<hr>
<table class='info'>
  <tr><td class='lbl'>Khách hàng:</td><td class='val'><b>{phieu.get('ten_khach','')}</b></td>
      <td class='lbl'>SĐT:</td><td><b>{phieu.get('sdt_khach','')}</b></td></tr>
  <tr><td class='lbl'>Hiệu đồng hồ:</td><td class='val'>{phieu.get('hieu_dong_ho') or '—'}</td>
      <td class='lbl'>Loại YC:</td><td>{phieu.get('loai_yeu_cau','')}</td></tr>
  <tr><td class='lbl'>Đặc điểm:</td><td colspan='3'>{phieu.get('dac_diem') or '—'}</td></tr>
  <tr><td class='lbl'>Mô tả lỗi:</td><td colspan='3'>{phieu.get('mo_ta_loi','')}</td></tr>
  <tr><td class='lbl'>Hẹn trả:</td><td class='val'>{phieu.get('ngay_hen_tra') or '—'}</td>
      <td class='lbl'>Trả trước:</td><td>{int(phieu.get('khach_tra_truoc',0)):,}đ</td></tr>
</table>
<hr>
<table class='svc'>
  <tr><th>Dịch vụ / Linh kiện</th><th class='c'>SL</th><th class='r'>Đơn giá</th><th class='r'>T.Tiền</th></tr>
  {rows_html or "<tr><td colspan='4' style='text-align:center;color:#999;padding:8px'>Chưa có dịch vụ</td></tr>"}
  <tr class='total-row'>
    <td colspan='3' class='r'>Tổng cộng:</td><td class='r'>{tong_in:,}đ</td></tr>
  <tr><td colspan='3' class='r'>Đã trả trước:</td>
      <td class='r'>{int(phieu.get('khach_tra_truoc',0)):,}đ</td></tr>
  <tr class='total-row'>
    <td colspan='3' class='r'>Còn lại:</td><td class='r'>{con_lai:,}đ</td></tr>
</table>
<div class='sign'>
  <div>Khách hàng ký<br><br><br><br>_______________</div>
  <div>Nhân viên tiếp nhận<br><br><br><br>_______________<br>{phieu.get('nguoi_tiep_nhan','')}</div>
</div>
<script>window.onload=function(){{window.print();}}</script>
</body></html>""".replace(",", ".")


def _in_phieu_sc(phieu_html: str, key: str):
    """Mở tab mới và in phiếu — dùng Blob URL để giữ đúng UTF-8 tiếng Việt."""
    import base64
    b64 = base64.b64encode(phieu_html.encode("utf-8")).decode("ascii")
    st.components.v1.html(
        f"""<script>
        var b = new Blob(
            [new TextDecoder('utf-8').decode(
                Uint8Array.from(atob('{b64}'), c => c.charCodeAt(0))
            )],
            {{type: 'text/html; charset=utf-8'}}
        );
        var w = window.open(URL.createObjectURL(b), '_blank');
        </script>""",
        height=0
    )


import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

from utils.config import ALL_BRANCHES, CN_SHORT, IN_APP_MARKER, ARCHIVED_MARKER
from utils.db import supabase, log_action, load_hoa_don, load_hoa_don_unified, \
    load_the_kho, load_hang_hoa, \
    load_phieu_chuyen_kho, load_phieu_kiem_ke, get_gia_ban_map, load_stock_deltas, \
    load_khach_hang_list, lookup_khach_hang, _upsert_khach_hang, get_archive_reminder, \
    load_psc_for_apsc
from utils.auth import get_user, is_admin, is_ke_toan_or_admin, \
    get_active_branch, get_accessible_branches
from utils.hd_style import (
    inject_hoa_don_css,
    list_card_html, detail_rail_html, empty_rail_html,
    smart_search_predicate,
    fmt_money, short_time,
)

# Prefix helpers — import pattern giống bao_cao.py
PDT_PREFIXES = ["AHDD"]
POS_PREFIXES = ["AHD"]
APSC_PREFIXES = ["APSC"]


def _is_pdt_hd(ma: str) -> bool:
    return any(str(ma).startswith(p) for p in PDT_PREFIXES)


def _is_pos_hd(ma: str) -> bool:
    s = str(ma)
    if any(s.startswith(p) for p in PDT_PREFIXES):
        return False
    return any(s.startswith(p) for p in POS_PREFIXES)


def _is_apsc_hd(ma: str) -> bool:
    return any(str(ma).startswith(p) for p in APSC_PREFIXES)


NGUOI_BAN_COLS = ["Người bán", "Nhân viên bán", "Người tạo", "Nhân viên"]


def _items_from_rows(rows: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in rows.iterrows():
        out.append({
            "ma":  str(r.get("Mã hàng", "") or ""),
            "ten": str(r.get("Tên hàng", "") or ""),
            "sl":  int(r.get("Số lượng", 0) or 0),
            "dg":  int(r.get("Đơn giá", 0) or 0),
            "tt":  int(r.get("Thành tiền", 0) or 0),
        })
    return out


def _build_invoice_dicts(df: pd.DataFrame) -> list[dict]:
    """Group dataframe theo Mã hóa đơn → list inv dicts cho list_card_html
    và detail_rail_html. inv["psc"] là dict|None (1:1)."""
    if df.empty:
        return []

    nb_col = None
    for col in NGUOI_BAN_COLS:
        if col in df.columns:
            nb_col = col
            break

    out = []
    for ma, grp in df.groupby("Mã hóa đơn", sort=False):
        head = grp.iloc[0]
        is_pdt = _is_pdt_hd(ma)
        is_apsc = _is_apsc_hd(ma)
        kenh = str(head.get("Kênh bán", "") or ("POS" if str(ma).startswith("AHD") else ""))
        loai = "Đổi/Trả" if is_pdt else ("Sửa chữa" if is_apsc else "")

        pttt = {}
        for src, key in [("Tiền mặt", "tm"), ("Chuyển khoản", "ck"),
                         ("Thẻ", "the"), ("Ví", "vi")]:
            if src in grp.columns:
                v = float(head.get(src, 0) or 0)
                if v > 0:
                    pttt[key] = v

        inv = {
            "ma": ma,
            "tg": str(head.get("Thời gian", "")),
            "kenh": kenh, "loai": loai,
            "status": str(head.get("Trạng thái", "Hoàn thành")),
            "khach": str(head.get("Tên khách hàng", "") or "Khách lẻ"),
            "sdt":   str(head.get("Điện thoại", "") or "").strip(),
            "nv":    str(head.get(nb_col, "") or "").strip() if nb_col else "",
            "pttt":  pttt,
            "tong":  int(head.get("Tổng tiền hàng", 0) or 0),
            "giam":  int(head.get("Giảm giá hóa đơn", 0) or 0),
            "tra":   int(head.get("Khách đã trả", 0) or 0),
        }

        if is_pdt:
            inv["chenh"] = int(head.get("_pdt_chenh_lech", head.get("Khách đã trả", 0)) or 0)
            tra_rows = grp[grp.get("_pdt_kieu", pd.Series(dtype=str)) == "tra"] \
                       if "_pdt_kieu" in grp.columns else pd.DataFrame()
            moi_rows = grp[grp.get("_pdt_kieu", pd.Series(dtype=str)) == "moi"] \
                       if "_pdt_kieu" in grp.columns else pd.DataFrame()
            inv["items_tra"] = _items_from_rows(tra_rows)
            inv["items_moi"] = _items_from_rows(moi_rows)
        else:
            inv["items"] = _items_from_rows(grp)

        if is_apsc:
            ma_ycsc = str(head.get("Mã YCSC", "") or "").strip()
            inv["psc"] = load_psc_for_apsc(ma_ycsc) if ma_ycsc else None

        out.append(inv)

    if "_ngay" in df.columns:
        order_map = dict(zip(df["Mã hóa đơn"],
                              pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")))
        out.sort(key=lambda x: order_map.get(x["ma"]) or pd.Timestamp.min, reverse=True)
    return out


def _build_invoice_print_html(inv: dict) -> str:
    """A4-friendly HTML cho browser print preview. Inline styles only."""
    import html as _h
    esc = _h.escape

    is_pdt = inv.get("loai") == "Đổi/Trả"
    is_apsc = inv.get("loai") == "Sửa chữa"

    def _items_table(items, *, allow_negative=False):
        if not items:
            return '<tr><td colspan="5" style="padding:8px;color:#888;text-align:center">—</td></tr>'
        rows = []
        for it in items:
            tt = it.get("tt", 0) or 0
            tt_str = fmt_money(tt) if allow_negative else fmt_money(abs(tt))
            rows.append(
                f'<tr>'
                f'<td style="padding:4px 6px;border-bottom:1px solid #eee;font-family:monospace">{esc(str(it.get("ma","")))}</td>'
                f'<td style="padding:4px 6px;border-bottom:1px solid #eee">{esc(str(it.get("ten","")))}</td>'
                f'<td style="padding:4px 6px;border-bottom:1px solid #eee;text-align:right">{it.get("sl",0)}</td>'
                f'<td style="padding:4px 6px;border-bottom:1px solid #eee;text-align:right;font-family:monospace">{fmt_money(it.get("dg",0))}</td>'
                f'<td style="padding:4px 6px;border-bottom:1px solid #eee;text-align:right;font-family:monospace;font-weight:600">{tt_str}</td>'
                f'</tr>'
            )
        return "".join(rows)

    pttt = inv.get("pttt") or {}
    pttt_lines = []
    for k, label in [("tm", "Tiền mặt"), ("ck", "Chuyển khoản"), ("the", "Thẻ"), ("vi", "Ví")]:
        v = float(pttt.get(k, 0) or 0)
        if v > 0:
            pttt_lines.append(f'<div>{label}: <span style="font-family:monospace">{fmt_money(v)}</span></div>')
    pttt_block = "".join(pttt_lines) or '<div style="color:#888">—</div>'

    if is_pdt:
        items_section = (
            f'<h3 style="margin:12px 0 6px;color:#cf4c2c">← Khách trả lại</h3>'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px">'
            f'<thead><tr style="background:#fef0f0">'
            f'<th style="padding:6px;text-align:left">Mã</th><th style="padding:6px;text-align:left">Tên hàng</th>'
            f'<th style="padding:6px;text-align:right">SL</th><th style="padding:6px;text-align:right">Đơn giá</th>'
            f'<th style="padding:6px;text-align:right">Thành tiền</th></tr></thead>'
            f'<tbody>{_items_table(inv.get("items_tra") or [], allow_negative=True)}</tbody></table>'
            f'<h3 style="margin:12px 0 6px;color:#1a7f37">→ Khách mua mới</h3>'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px">'
            f'<thead><tr style="background:#e9f6ee">'
            f'<th style="padding:6px;text-align:left">Mã</th><th style="padding:6px;text-align:left">Tên hàng</th>'
            f'<th style="padding:6px;text-align:right">SL</th><th style="padding:6px;text-align:right">Đơn giá</th>'
            f'<th style="padding:6px;text-align:right">Thành tiền</th></tr></thead>'
            f'<tbody>{_items_table(inv.get("items_moi") or [])}</tbody></table>'
        )
    else:
        items_section = (
            f'<h3 style="margin:12px 0 6px">Chi tiết hàng hoá</h3>'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px">'
            f'<thead><tr style="background:#fafafa">'
            f'<th style="padding:6px;text-align:left">Mã</th><th style="padding:6px;text-align:left">Tên hàng</th>'
            f'<th style="padding:6px;text-align:right">SL</th><th style="padding:6px;text-align:right">Đơn giá</th>'
            f'<th style="padding:6px;text-align:right">Thành tiền</th></tr></thead>'
            f'<tbody>{_items_table(inv.get("items") or [])}</tbody></table>'
        )

    if is_pdt:
        chenh = inv.get("chenh", 0) or 0
        lbl = "Khách bù thêm" if chenh >= 0 else "Cửa hàng hoàn"
        totals_block = (
            f'<tr><td style="padding:4px 0">{lbl}</td>'
            f'<td style="text-align:right;font-family:monospace;font-weight:600">{fmt_money(abs(chenh))}</td></tr>'
        )
    else:
        giam = inv.get("giam", 0) or 0
        giam_row = (
            f'<tr><td style="padding:4px 0">Giảm giá</td>'
            f'<td style="text-align:right;font-family:monospace;color:#cf4c2c">{fmt_money(giam)}</td></tr>'
            if giam > 0 else ""
        )
        totals_block = (
            f'<tr><td style="padding:4px 0">Tổng hàng</td>'
            f'<td style="text-align:right;font-family:monospace">{fmt_money(inv.get("tong",0))}</td></tr>'
            f'{giam_row}'
            f'<tr><td style="padding:6px 0 0;border-top:1px solid #ccc;font-weight:600">Khách đã trả</td>'
            f'<td style="padding:6px 0 0;border-top:1px solid #ccc;text-align:right;font-family:monospace;font-weight:700;font-size:14px">{fmt_money(inv.get("tra",0))}</td></tr>'
        )

    psc_block = ""
    if is_apsc and inv.get("psc"):
        p = inv["psc"]
        psc_block = (
            f'<div style="margin-top:12px;padding:8px 10px;background:#fef3c7;border:1px solid #f3d99c;border-radius:6px">'
            f'<div style="font-size:11px;font-weight:600;color:#b45309;letter-spacing:.4px;text-transform:uppercase">Phiếu sửa chữa liên đới</div>'
            f'<div style="margin-top:4px"><b>🔧 {esc(str(p.get("ma","—")))}</b> · {esc(str(p.get("san_pham","—")))}</div>'
            f'<div style="font-size:11px;color:#555;margin-top:2px">Nhận: {esc(str(p.get("ngay_nhan","—")))} · '
            f'Hẹn trả: {esc(str(p.get("ngay_tra","—")))} · KTV: {esc(str(p.get("kt_vien","—")))} · '
            f'Trạng thái: {esc(str(p.get("tinh_trang","—")))}</div>'
            f'</div>'
        )

    return (
        f'<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        f'<title>{esc(str(inv.get("ma","")))}</title>'
        f'<style>@page{{size:A4;margin:14mm}}body{{font-family:"Be Vietnam Pro",system-ui,sans-serif;color:#18181b;font-size:13px;margin:0}}</style>'
        f'</head><body>'
        f'<div style="text-align:center;margin-bottom:12px">'
        f'<h1 style="margin:0;font-size:20px;letter-spacing:1px">HOÁ ĐƠN</h1>'
        f'<div style="font-family:monospace;font-size:14px;margin-top:4px">{esc(str(inv.get("ma","")))}</div>'
        f'<div style="font-size:11px;color:#666">{esc(str(inv.get("tg","")))}</div>'
        f'</div>'
        f'<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:8px">'
        f'<div><b>Khách:</b> {esc(str(inv.get("khach","Khách lẻ") or "Khách lẻ"))}'
        f'{" · " + esc(str(inv.get("sdt",""))) if inv.get("sdt") else ""}</div>'
        f'<div>NV: {esc(str(inv.get("nv","") or "—"))}</div>'
        f'</div>'
        f'{items_section}'
        f'<table style="width:60%;margin-left:auto;margin-top:12px;font-size:13px">{totals_block}</table>'
        f'<div style="margin-top:12px;font-size:12px"><b>Phương thức thanh toán:</b>{pttt_block}</div>'
        f'{psc_block}'
        f'<div style="margin-top:20px;text-align:center;font-size:11px;color:#888">Cảm ơn quý khách</div>'
        f'</body></html>'
    )


def _trigger_print_invoice(inv: dict):
    import base64
    import streamlit.components.v1 as components
    html_doc = _build_invoice_print_html(inv)
    b64 = base64.b64encode(html_doc.encode("utf-8")).decode("ascii")
    components.html(
        f"""<script>
        (function() {{
          try {{
            const html = new TextDecoder('utf-8').decode(
              Uint8Array.from(atob('{b64}'), c => c.charCodeAt(0))
            );
            const blob = new Blob([html], {{type: 'text/html;charset=utf-8'}});
            const url = URL.createObjectURL(blob);
            const w = window.open(url, '_blank');
            if (!w) {{
              document.body.innerHTML = '<div style="color:#cf4c2c;font:13px sans-serif">⚠ Trình duyệt chặn popup. Cho phép popup cho trang này.</div>';
              return;
            }}
            setTimeout(() => URL.revokeObjectURL(url), 60000);
          }} catch (e) {{
            document.body.innerHTML = '<div style="color:#cf4c2c;font:13px sans-serif">⚠ Lỗi mở print: ' + e.message + '</div>';
          }}
        }})();
        </script>""",
        height=0,
    )


def _copy_invoice_to_clipboard(inv: dict):
    import json
    import streamlit.components.v1 as components

    lines = [f"{inv['ma']} · {inv.get('tg', '')}"]
    if inv.get("khach"):
        lines.append(f"{inv['khach']}" + (f" · {inv['sdt']}" if inv.get("sdt") else ""))
    if inv.get("nv"):
        lines.append(f"NV: {inv['nv']}")
    if inv.get("loai") == "Đổi/Trả":
        chenh = inv.get("chenh", 0) or 0
        lbl = "Khách bù thêm" if chenh >= 0 else "Cửa hàng hoàn"
        lines.append(f"{lbl}: {fmt_money(abs(chenh))}")
        for it in inv.get("items_tra") or []:
            lines.append(f"  ← {it['ten']} × {it['sl']}")
        for it in inv.get("items_moi") or []:
            lines.append(f"  → {it['ten']} × {it['sl']} = {fmt_money(it['tt'])}")
    else:
        lines.append(f"Tổng đã trả: {fmt_money(inv.get('tra', 0))}")
        for it in inv.get("items", []) or []:
            lines.append(f"  - {it['ten']} × {it['sl']} = {fmt_money(it['tt'])}")

    text = "\n".join(lines)
    components.html(
        f"""<script>
        (async function() {{
          const text = {json.dumps(text)};
          try {{
            await navigator.clipboard.writeText(text);
            document.body.innerHTML = '<div style="color:#1a7f37;font:13px sans-serif">✓ Đã sao chép vào clipboard</div>';
          }} catch (e) {{
            // Fallback: textarea + execCommand cho non-HTTPS / old browser
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select();
            try {{ document.execCommand('copy'); }}
            catch (e2) {{ document.body.innerHTML = '<div style="color:#cf4c2c;font:13px sans-serif">⚠ Không sao chép được: ' + e.message + '</div>'; return; }}
            document.body.removeChild(ta);
            document.body.innerHTML = '<div style="color:#1a7f37;font:13px sans-serif">✓ Đã sao chép</div>';
          }}
        }})();
        </script>""",
        height=30,
    )


def module_hoa_don():
    inject_hoa_don_css()

    # ╔══════════════════════════════════════════════════════════════╗
    # ║ NUCLEAR CSS INJECT — bypass st.html sanitizer that strips    ║
    # ║ <style> tags. Use st.markdown(unsafe_allow_html=True) which  ║
    # ║ is the documented Streamlit CSS injection pattern.            ║
    # ║ DO NOT REMOVE — these 2 rules are NOT in static/hoa_don.css. ║
    # ╚══════════════════════════════════════════════════════════════╝
    st.markdown("""
    <style>
    /* 1. Force white background cho rail bên phải */
    .stApp [class*="st-key-hd_rail"] {
        background: #ffffff !important;
        border-radius: 10px !important;
        padding: 14px !important;
    }
    .stApp [class*="st-key-hd_rail"] > div {
        background: transparent !important;
    }

    /* 2. Card list — cursor pointer + hover effect.
       (Card click sẽ hoạt động qua <a href> nhúng trong HTML, không cần CSS overlay button) */
    .stApp [class*="st-key-hd_card_"] {
        cursor: pointer !important;
        margin-bottom: 6px !important;
    }
    .stApp [class*="st-key-hd_card_"] a.hd-card-link {
        text-decoration: none !important;
        color: inherit !important;
        display: block !important;
    }
    .stApp [class*="st-key-hd_card_"] a.hd-card-link:hover > div {
        border-color: #c8c8cc !important;
        box-shadow: 0 2px 8px rgba(24,24,27,0.06) !important;
        transition: all .12s ease;
    }

    /* 3. DEBUG MARKER — confirm CSS injected (xóa sau khi test xong) */
    .stApp::before {
        content: "HOA_DON_FIX_v3" !important;
        position: fixed !important;
        bottom: 4px !important; right: 4px !important;
        background: #1a7f37 !important; color: white !important;
        padding: 2px 8px !important; border-radius: 4px !important;
        font-size: 10px !important; font-family: monospace !important;
        z-index: 99999 !important; opacity: 0.6 !important;
        pointer-events: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Process click qua URL query params ────────────────────────
    qp = st.query_params
    if "hd_open" in qp:
        st.session_state["hd_sel_ma"] = qp["hd_open"]
        del st.query_params["hd_open"]
        st.rerun()

    try:
        active = get_active_branch()
        accessible = get_accessible_branches()

        # ── Branch picker (giữ nguyên logic) ─────────────────────────
        if is_ke_toan_or_admin() and len(accessible) > 1:
            cn_filter = st.selectbox(
                "Chi nhánh:", ["Tất cả"] + accessible,
                index=(accessible.index(active) + 1) if active in accessible else 0,
                key="hd_cn", label_visibility="collapsed",
            )
            load_cns = tuple(accessible) if cn_filter == "Tất cả" else (cn_filter,)
        else:
            load_cns = (active,)
            st.caption(f"📍 {active}")

        # ── Load data (giữ nguyên) ───────────────────────────────────
        raw = load_hoa_don_unified(branches_key=load_cns)
        if raw.empty:
            st.info("Chưa có dữ liệu hóa đơn."); return

        if st.session_state.get("so_dong_trung", 0) > 0:
            st.caption(f"⚠ {st.session_state['so_dong_trung']} dòng trùng đã lọc.")

        data = raw.copy()
        data["SĐT_Search"] = data["Điện thoại"].fillna("").str.replace(r"\D+", "", regex=True)

        # ── Distinct NV list ─────────────────────────────────────────
        nv_options = ["Tất cả NV"]
        for col in NGUOI_BAN_COLS:
            if col in data.columns:
                nv_options += sorted([n for n in data[col].dropna().astype(str).unique()
                                      if n.strip() and n.strip().lower() != "nan"])
                break

        import datetime as _dt
        _now = _dt.datetime.now()

        # ── Filter container (thay 3 sub-tab cũ) ─────────────────────
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 1])
            with c1:
                keyword = st.text_input(
                    "Tìm kiếm", key="hd_search",
                    placeholder="Tìm mã HĐ, số điện thoại, tên khách… (số→SĐT, chữ→tên)",
                    label_visibility="collapsed",
                )
            with c2:
                with st.popover("📅 Khoảng ngày", use_container_width=True):
                    d_from = st.date_input(
                        "Từ:", value=_now.date(),
                        key="hd_date_from", format="DD/MM/YYYY",
                    )
                    d_to = st.date_input(
                        "Đến:", value=_now.date(),
                        key="hd_date_to", format="DD/MM/YYYY",
                    )
            with c3:
                sel_nv = st.selectbox("NV", nv_options, key="hd_filter_nv",
                                      label_visibility="collapsed")
            with c4:
                sel_pttt = st.selectbox(
                    "PTTT", ["Tất cả PTTT", "Tiền mặt", "CK", "Thẻ", "Ví"],
                    key="hd_filter_pttt", label_visibility="collapsed",
                )
            with c5:
                sel_loai = st.selectbox(
                    "Loại", ["Tất cả loại", "POS", "Đổi/Trả", "Sửa chữa", "KiotViet"],
                    key="hd_filter_loai", label_visibility="collapsed",
                )

            # ── Pre-status filters (date + search + NV + PTTT + Loại) ───
            # Áp dụng TRƯỚC khi render radio để counts cập nhật realtime.
            pre = data.copy()

            if "_date" in pre.columns:
                pre = pre[pre["_date"].between(d_from, d_to)]
            else:
                _ngay = pd.to_datetime(pre["Thời gian"], dayfirst=True, errors="coerce").dt.date
                pre = pre[_ngay.between(d_from, d_to)]

            if keyword:
                pred = smart_search_predicate(keyword)
                pre = pre[pre.apply(pred, axis=1)]

            if sel_nv != "Tất cả NV":
                for col in NGUOI_BAN_COLS:
                    if col in pre.columns:
                        pre = pre[pre[col].astype(str).str.strip() == sel_nv]
                        break

            pttt_col_map = {"Tiền mặt": "Tiền mặt", "CK": "Chuyển khoản",
                            "Thẻ": "Thẻ", "Ví": "Ví"}
            if sel_pttt != "Tất cả PTTT" and sel_pttt in pttt_col_map:
                col = pttt_col_map[sel_pttt]
                if col in pre.columns:
                    pre = pre[pd.to_numeric(pre[col], errors="coerce").fillna(0) > 0]

            if sel_loai == "POS":
                mask_kenh_pos = pre["Kênh bán"].fillna("") == "POS" \
                    if "Kênh bán" in pre.columns else pd.Series(False, index=pre.index)
                pre = pre[mask_kenh_pos &
                          (~pre["Mã hóa đơn"].apply(_is_pdt_hd)) &
                          (~pre["Mã hóa đơn"].apply(_is_apsc_hd))]
            elif sel_loai == "Đổi/Trả":
                pre = pre[pre["Mã hóa đơn"].apply(_is_pdt_hd)]
            elif sel_loai == "Sửa chữa":
                pre = pre[pre["Mã hóa đơn"].apply(_is_apsc_hd)]
            elif sel_loai == "KiotViet":
                mask_kenh_pos = pre["Kênh bán"].fillna("") == "POS" \
                    if "Kênh bán" in pre.columns else pd.Series(False, index=pre.index)
                pre = pre[(~mask_kenh_pos) & (~pre["Mã hóa đơn"].apply(_is_pdt_hd))]

            # Status segmented (radio horizontal — counts từ pre, KHÔNG phải data)
            n_all    = pre["Mã hóa đơn"].nunique()
            n_ok     = pre[pre["Trạng thái"] == "Hoàn thành"]["Mã hóa đơn"].nunique()
            n_cancel = pre[pre["Trạng thái"] == "Đã hủy"]["Mã hóa đơn"].nunique()
            n_pdt    = pre[pre["Mã hóa đơn"].apply(_is_pdt_hd)]["Mã hóa đơn"].nunique()
            n_apsc   = pre[pre["Mã hóa đơn"].apply(_is_apsc_hd)]["Mã hóa đơn"].nunique()
            sel_status = st.radio(
                "Trạng thái",
                [f"Tất cả ({n_all})", f"● Hoàn thành ({n_ok})", f"✕ Đã hủy ({n_cancel})",
                 f"↔ Đổi/Trả ({n_pdt})", f"🔧 Sửa chữa ({n_apsc})"],
                index=1,
                horizontal=True, label_visibility="collapsed", key="hd_filter_status",
            )

        # ── Apply status filter to pre → filt ────────────────────────
        filt = pre
        if "Hoàn thành" in sel_status:
            filt = filt[filt["Trạng thái"] == "Hoàn thành"]
        elif "Đã hủy" in sel_status:
            filt = filt[filt["Trạng thái"] == "Đã hủy"]
        elif "Đổi/Trả" in sel_status:
            filt = filt[filt["Mã hóa đơn"].apply(_is_pdt_hd)]
        elif "Sửa chữa" in sel_status:
            filt = filt[filt["Mã hóa đơn"].apply(_is_apsc_hd)]

        # ── Master-detail grid ──────────────────────────────────────
        if filt.empty:
            st.warning("🔍 Không tìm thấy chứng từ phù hợp")
            return

        invoices = _build_invoice_dicts(filt)
        sel_ma = st.session_state.get("hd_sel_ma")
        if sel_ma and sel_ma not in {i["ma"] for i in invoices}:
            sel_ma = None
            st.session_state.pop("hd_sel_ma", None)

        # ── Pagination 10/page ───────────────────────────────────────
        PER_PAGE = 10
        total = len(invoices)
        n_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page = int(st.session_state.get("hd_page", 1) or 1)
        if page > n_pages:
            page = n_pages
            st.session_state["hd_page"] = page
        if page < 1:
            page = 1
            st.session_state["hd_page"] = 1
        start = (page - 1) * PER_PAGE
        page_invoices = invoices[start:start + PER_PAGE]

        col_list, col_rail = st.columns([6, 4], gap="medium")
        with col_list:
            import time as _t
            for inv in page_invoices:
                is_sel = inv["ma"] == sel_ma
                with st.container(key=f"hd_card_{inv['ma']}"):
                    # Card bọc trong <a href> — click trigger URL change →
                    # Streamlit rerun → query param "hd_open" được xử lý ở
                    # đầu module_hoa_don. Cache-buster (timestamp) để URL
                    # khác nhau giữa các click trên cùng card.
                    cb = int(_t.time() * 1000)
                    st.html(
                        f'<a class="hd-card-link" href="?hd_open={inv["ma"]}&_={cb}" target="_self">'
                        f'{list_card_html(inv, selected=is_sel)}'
                        f'</a>'
                    )

            if n_pages > 1:
                with st.container(key="hd_pagination"):
                    nav_l, nav_c, nav_r = st.columns([1, 8, 1])
                    with nav_l:
                        if st.button("‹", key="hd_page_prev",
                                     disabled=(page <= 1),
                                     use_container_width=True):
                            st.session_state["hd_page"] = page - 1
                            st.rerun()
                    with nav_c:
                        st.markdown(
                            f"<div style='text-align:center;font-family:"
                            f"\"JetBrains Mono\",monospace;line-height:32px;"
                            f"color:#71717a;font-size:12px'>"
                            f"Trang {page} / {n_pages}</div>",
                            unsafe_allow_html=True,
                        )
                    with nav_r:
                        if st.button("›", key="hd_page_next",
                                     disabled=(page >= n_pages),
                                     use_container_width=True):
                            st.session_state["hd_page"] = page + 1
                            st.rerun()

        with col_rail:
            with st.container(key="hd_rail", border=True):
                if sel_ma:
                    sel_inv = next((i for i in invoices if i["ma"] == sel_ma), None)
                    if sel_inv:
                        st.html(detail_rail_html(sel_inv))
                        b1, b2, b3 = st.columns(3)
                        with b1:
                            if st.button("🖨 In lại", key=f"hd_print_{sel_ma}",
                                         use_container_width=True, type="primary"):
                                _trigger_print_invoice(sel_inv)
                        with b2:
                            if st.button("⎘ Sao chép", key=f"hd_copy_{sel_ma}",
                                         use_container_width=True):
                                _copy_invoice_to_clipboard(sel_inv)
                        with b3:
                            if st.button("⤴ Phiếu kho", key=f"hd_kho_{sel_ma}",
                                         use_container_width=True):
                                st.toast("TODO: link to phiếu kho", icon="🚧")
                else:
                    st.html(empty_rail_html())

    except Exception as e:
        st.error(f"Lỗi: {e}")


# ==========================================
# MODULE: HÀNG HÓA
# ==========================================

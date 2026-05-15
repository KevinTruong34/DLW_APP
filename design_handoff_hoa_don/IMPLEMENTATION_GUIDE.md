# Implementation Guide — `hoa_don.py` redesign

Step-by-step patch cho `modules/hoa_don.py`. Mỗi section có thể PR riêng. Nhãn `# 📌 NEW` cho thêm mới, `# ✂️ REPLACE` cho thay thế, không nhãn = **giữ nguyên 100%**.

---

## 0. Chuẩn bị

```bash
# Trong root repo DLW_APP/
mkdir -p static
cp design_handoff_hoa_don/hoa_don.css        static/hoa_don.css
cp design_handoff_hoa_don/utils_hd_style.py  utils/hd_style.py
```

Verify `streamlit>=1.33` trong `requirements.txt`.

---

## 1. Inject CSS + smart-search helpers

### File: `modules/hoa_don.py`

**Thêm import ở đầu file (sau các import hiện có):**

```python
# 📌 NEW
from utils.hd_style import (
    inject_hoa_don_css,
    list_card_html, detail_rail_html, empty_rail_html,
    smart_search_predicate,
    fmt_money, short_time,
)
# 📌 NEW — load PSC liên đới cho HĐ APSC (1:1)
from utils.db import load_psc_for_apsc
```

**Trong `module_hoa_don()`, ngay sau `def module_hoa_don():`:**

```python
def module_hoa_don():
    inject_hoa_don_css()                                  # 📌 NEW
    NGUOI_BAN_COLS = ["Người bán", "Nhân viên bán", "Người tạo", "Nhân viên"]
    PAYMENT_COLS = [
        ("Tiền mặt",      "💵"),
        ("Thẻ",           "💳"),
        ("Ví",            "📱"),
        ("Chuyển khoản",  "🏦"),
    ]
    # ... giữ nguyên _loai_label, render_invoice, render_list, _render_recent
    # (Phase 1 vẫn cần các hàm này để fallback nếu PHASE_2_NEW_LAYOUT=False)
```

---

## 2. Thay khối load + 3 sub-tab bằng master-detail

### Trước (lines ~258–350 trong source)

```python
try:
    active = get_active_branch()
    accessible = get_accessible_branches()

    if is_ke_toan_or_admin() and len(accessible) > 1:
        cn_filter = st.selectbox("Chi nhánh:", ["Tất cả"] + accessible, ...)
        load_cns = tuple(accessible) if cn_filter == "Tất cả" else (cn_filter,)
    else:
        load_cns = (active,)
        st.caption(f"📍 {active}")

    raw = load_hoa_don_unified(branches_key=load_cns)
    if raw.empty:
        st.info("Chưa có dữ liệu hóa đơn."); return

    if st.session_state.get("so_dong_trung",0) > 0:
        st.caption(f"⚠ {st.session_state['so_dong_trung']} dòng trùng đã lọc.")

    data = raw.copy()
    data["SĐT_Search"] = data["Điện thoại"].fillna("").str.replace(r"\D+","",regex=True)

    t1,t2,t3 = st.tabs(["Số điện thoại","Mã hóa đơn","Ngày tháng"])
    with t1:
        phone = st.text_input("Số điện thoại:", key="in_phone", ...)
        # ... ~30 lines per tab
    with t2:
        # ...
    with t3:
        # ...
except Exception as e:
    st.error(f"Lỗi: {e}")
```

### Sau (toàn bộ thân `try` block)

```python
try:
    active = get_active_branch()
    accessible = get_accessible_branches()

    # ── Branch picker — KHÔNG ĐỔI ─────────────────────────────────────
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

    # ── Load data — KHÔNG ĐỔI ────────────────────────────────────────
    raw = load_hoa_don_unified(branches_key=load_cns)
    if raw.empty:
        st.info("Chưa có dữ liệu hóa đơn."); return

    if st.session_state.get("so_dong_trung", 0) > 0:
        st.caption(f"⚠ {st.session_state['so_dong_trung']} dòng trùng đã lọc.")

    data = raw.copy()
    data["SĐT_Search"] = data["Điện thoại"].fillna("").str.replace(r"\D+", "", regex=True)

    # ── 📌 NEW: build distinct lists for filters ─────────────────────
    nv_options = ["Tất cả NV"]
    for col in NGUOI_BAN_COLS:
        if col in data.columns:
            nv_options += sorted([n for n in data[col].dropna().astype(str).unique()
                                  if n.strip() and n.strip().lower() != "nan"])
            break

    # ── 📌 NEW: title row ────────────────────────────────────────────
    import datetime as _dt
    _wd = ["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật"]
    _now = _dt.datetime.now()
    title_l, title_r = st.columns([3, 1])
    with title_l:
        st.html(f'<h2 style="font-size:22px;font-weight:600;letter-spacing:-.2px;'
                f'margin:0 0 10px;font-family:Be Vietnam Pro,system-ui,sans-serif;">'
                f'Hoá đơn · {_wd[_now.weekday()]} {_now.strftime("%d/%m/%Y")}</h2>')
    with title_r:
        st.caption(f"{data['Mã hóa đơn'].nunique()} chứng từ")

    # ── 📌 NEW: filter container (replaces 3 sub-tabs) ───────────────
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
                d_from = st.date_input("Từ:",  value=_now.date() - _dt.timedelta(days=7),
                                       key="hd_date_from", format="DD/MM/YYYY")
                d_to   = st.date_input("Đến:", value=_now.date(),
                                       key="hd_date_to",   format="DD/MM/YYYY")
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

        # Status segmented (radio with horizontal=True → styled by CSS as seg)
        n_all    = data["Mã hóa đơn"].nunique()
        n_ok     = data[data["Trạng thái"] == "Hoàn thành"]["Mã hóa đơn"].nunique()
        n_cancel = data[data["Trạng thái"] == "Đã hủy"]["Mã hóa đơn"].nunique()
        n_pdt    = data[data["Mã hóa đơn"].apply(_is_pdt_hd)]["Mã hóa đơn"].nunique()
        n_apsc   = data[data["Mã hóa đơn"].apply(_is_apsc_hd)]["Mã hóa đơn"].nunique()
        sel_status = st.radio(
            "Trạng thái",
            [f"Tất cả ({n_all})", f"● Hoàn thành ({n_ok})", f"✕ Đã hủy ({n_cancel})",
             f"↔ Đổi/Trả ({n_pdt})", f"🔧 Sửa chữa ({n_apsc})"],
            horizontal=True, label_visibility="collapsed", key="hd_filter_status",
        )

    # ── 📌 NEW: apply filters ────────────────────────────────────────
    filt = data.copy()

    # Date
    if "_date" in filt.columns:
        filt = filt[filt["_date"].between(d_from, d_to)]
    else:
        _ngay = pd.to_datetime(filt["Thời gian"], dayfirst=True, errors="coerce").dt.date
        filt = filt[_ngay.between(d_from, d_to)]

    # Smart search
    if keyword:
        pred = smart_search_predicate(keyword)
        mask = filt.apply(pred, axis=1)
        filt = filt[mask]

    # NV
    if sel_nv != "Tất cả NV":
        for col in NGUOI_BAN_COLS:
            if col in filt.columns:
                filt = filt[filt[col].astype(str).str.strip() == sel_nv]
                break

    # PTTT
    pttt_col_map = {"Tiền mặt": "Tiền mặt", "CK": "Chuyển khoản",
                    "Thẻ": "Thẻ", "Ví": "Ví"}
    if sel_pttt != "Tất cả PTTT" and sel_pttt in pttt_col_map:
        col = pttt_col_map[sel_pttt]
        if col in filt.columns:
            filt = filt[pd.to_numeric(filt[col], errors="coerce").fillna(0) > 0]

    # Loại
    if sel_loai == "POS":
        filt = filt[(filt.get("Kênh bán", "") == "POS") &
                    (~filt["Mã hóa đơn"].apply(_is_pdt_hd)) &
                    (~filt["Mã hóa đơn"].apply(_is_apsc_hd))]
    elif sel_loai == "Đổi/Trả":
        filt = filt[filt["Mã hóa đơn"].apply(_is_pdt_hd)]
    elif sel_loai == "Sửa chữa":
        filt = filt[filt["Mã hóa đơn"].apply(_is_apsc_hd)]
    elif sel_loai == "KiotViet":
        filt = filt[(filt.get("Kênh bán", "") != "POS") &
                    (~filt["Mã hóa đơn"].apply(_is_pdt_hd))]

    # Status
    if "Hoàn thành" in sel_status:
        filt = filt[filt["Trạng thái"] == "Hoàn thành"]
    elif "Đã hủy" in sel_status:
        filt = filt[filt["Trạng thái"] == "Đã hủy"]
    elif "Đổi/Trả" in sel_status:
        filt = filt[filt["Mã hóa đơn"].apply(_is_pdt_hd)]
    elif "Sửa chữa" in sel_status:
        filt = filt[filt["Mã hóa đơn"].apply(_is_apsc_hd)]

    # ── 📌 NEW: master-detail grid ───────────────────────────────────
    if filt.empty:
        st.warning("🔍 Không tìm thấy chứng từ phù hợp")
        return

    invoices = _build_invoice_dicts(filt)
    sel_ma = st.session_state.get("hd_sel_ma")
    if sel_ma and sel_ma not in {i["ma"] for i in invoices}:
        sel_ma = None
        st.session_state.pop("hd_sel_ma", None)

    col_list, col_rail = st.columns([6, 4], gap="medium")
    with col_list:
        for inv in invoices:
            is_sel = inv["ma"] == sel_ma
            st.html(list_card_html(inv, selected=is_sel))
            # Click button — phase 1 keeps a visible "Xem chi tiết" link
            if st.button("Xem chi tiết →", key=f"hd_open_{inv['ma']}",
                         use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state["hd_sel_ma"] = inv["ma"]
                st.rerun()

    with col_rail:
        if sel_ma:
            sel_inv = next((i for i in invoices if i["ma"] == sel_ma), None)
            if sel_inv:
                st.html(detail_rail_html(sel_inv))
                # Action buttons
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
```

---

## 3. `_build_invoice_dicts` — đóng gói row Supabase thành dict frontend dùng

```python
# 📌 NEW — đặt trong hoa_don.py, gần cuối module
def _build_invoice_dicts(df: pd.DataFrame) -> list[dict]:
    """Group dataframe theo Mã hóa đơn → list of inv dicts cho list_card_html
    và detail_rail_html."""
    if df.empty:
        return []

    # Find NV column
    nb_col = None
    for col in ["Người bán", "Nhân viên bán", "Người tạo", "Nhân viên"]:
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
        for src, key in [("Tiền mặt","tm"), ("Chuyển khoản","ck"),
                          ("Thẻ","the"), ("Ví","vi")]:
            if src in grp.columns:
                v = float(head.get(src, 0) or 0)
                if v > 0: pttt[key] = v

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

        # 📌 NEW: PSC liên đới — chỉ cho HĐ APSC, 1:1 qua "Mã YCSC"
        # inv["psc"] sẽ là dict | None (KHÔNG phải list).
        if is_apsc:
            ma_ycsc = str(head.get("Mã YCSC", "") or "").strip()
            inv["psc"] = load_psc_for_apsc(ma_ycsc) if ma_ycsc else None

        out.append(inv)

    # Sort by _ngay desc (fallback to Thời gian)
    if "_ngay" in df.columns:
        order_map = dict(zip(df["Mã hóa đơn"],
                              pd.to_datetime(df["Thời gian"], dayfirst=True, errors="coerce")))
        out.sort(key=lambda x: order_map.get(x["ma"]) or pd.Timestamp.min, reverse=True)
    return out


def _items_from_rows(rows):
    cols = ["Mã hàng","Tên hàng","Số lượng","Đơn giá","Thành tiền"]
    out = []
    for _, r in rows.iterrows():
        out.append({
            "ma":  str(r.get("Mã hàng","") or ""),
            "ten": str(r.get("Tên hàng","") or ""),
            "sl":  int(r.get("Số lượng", 0) or 0),
            "dg":  int(r.get("Đơn giá", 0) or 0),
            "tt":  int(r.get("Thành tiền", 0) or 0),
        })
    return out
```

---

## 4. Thêm `load_psc_for_apsc` vào `utils/db.py`

**Schema thực tế** (verify từ `utils/db.py:search_sc_for_edit` + `utils/print_queue_apsc.py`):
- Bảng `phieu_sua_chua` có: `ma_phieu`, `hieu_dong_ho`, `loai_yeu_cau`, `mo_ta_loi`, `trang_thai`, `ngay_hen_tra`, `nguoi_tiep_nhan`, `created_at`.
- **Liên kết**: `hoa_don."Mã YCSC"` → `phieu_sua_chua.ma_phieu` (**1:1**).
- KHÔNG có cột `ma_hoa_don_apsc` trong `phieu_sua_chua` — đừng query cột này.

```python
# 📌 NEW in utils/db.py
@st.cache_data(ttl=120, show_spinner=False)
def load_psc_for_apsc(ma_ycsc: str) -> dict | None:
    """Load phiếu sửa chữa liên đới với 1 HĐ APSC (quan hệ 1:1).

    Args:
        ma_ycsc: giá trị cột "Mã YCSC" trên hoa_don (chỉ có cho HĐ APSC từ
                 KiotViet upload). Truyền chuỗi rỗng → return None.

    Returns:
        dict đã normalize keys cho khớp với detail_rail_html / list_card_html:
            {ma, san_pham, ngay_nhan, ngay_tra, tinh_trang, kt_vien}
        Hoặc None nếu ma_ycsc rỗng / không tìm thấy / lỗi DB.
    """
    if not ma_ycsc or not str(ma_ycsc).strip():
        return None
    try:
        res = (supabase.table("phieu_sua_chua")
               .select("ma_phieu, hieu_dong_ho, loai_yeu_cau, mo_ta_loi, "
                       "trang_thai, ngay_hen_tra, nguoi_tiep_nhan, created_at")
               .eq("ma_phieu", str(ma_ycsc).strip())
               .limit(1)
               .execute())
    except Exception:
        return None

    rows = res.data or []
    if not rows:
        return None

    r = rows[0]

    # Format created_at (ISO timestamptz) → "DD/MM/YYYY" cho display
    ngay_nhan = "—"
    try:
        ca = r.get("created_at")
        if ca:
            dt = pd.to_datetime(ca, errors="coerce", utc=True)
            if pd.notna(dt):
                dt_vn = dt.tz_convert("Asia/Ho_Chi_Minh")
                ngay_nhan = dt_vn.strftime("%d/%m/%Y")
    except Exception:
        pass

    # san_pham priority: hieu_dong_ho → loai_yeu_cau → mo_ta_loi → "—"
    san_pham = (r.get("hieu_dong_ho") or r.get("loai_yeu_cau")
                or r.get("mo_ta_loi") or "—")
    san_pham = str(san_pham).strip()[:80] or "—"

    return {
        "ma":         r.get("ma_phieu", "—"),
        "san_pham":   san_pham,
        "ngay_nhan":  ngay_nhan,
        "ngay_tra":   r.get("ngay_hen_tra") or "—",
        "tinh_trang": r.get("trang_thai") or "—",
        "kt_vien":    r.get("nguoi_tiep_nhan") or "—",
    }
```

**Lưu ý**: KHÔNG cần schema migration. Schema hiện tại đã đủ. Caller (`_build_invoice_dicts` ở section 3) đã wire sẵn.

---

## 5. Click overlay trick (làm card trở thành button)

Mặc định `st.button("Xem chi tiết")` xuất hiện DƯỚI card đã render. Để biến card thành clickable, thêm vào `static/hoa_don.css`:

```css
/* Hide the "Xem chi tiết" buttons under list cards, but keep them clickable */
[data-testid="stButton"] > button[kind="secondary"]:has(div:contains("Xem chi tiết")){
  /* Streamlit không cho :contains; dùng key-based label_visibility */
}
```

**Workaround sạch hơn** (phase 1): để `st.button("Xem chi tiết →", use_container_width=True)` hiển thị bình thường dưới mỗi card. Cách này hơi chiếm 1 dòng nhưng KHÔNG vi phạm rule wrap. Có thể đổi label thành emoji `›` cho gọn.

**Workaround tốt nhất** (phase 2): dùng `streamlit.components.v1.html` với postMessage thay vì st.button. Tốn công.

→ **Khuyến nghị**: Phase 1 dùng nút text rõ ràng dưới card. Đo UX rồi quyết định.

---

## 6. Helpers còn thiếu (placeholder)

```python
# 📌 NEW — đặt trong hoa_don.py
def _trigger_print_invoice(inv):
    """Dùng pattern Blob URL giống _trigger_print_window trong hang_hoa.py.
    Tham khảo: modules/hang_hoa.py:_trigger_print_window.
    """
    from utils.hh_style import _trigger_print_window  # tái dùng
    html = _build_invoice_print_html(inv)
    _trigger_print_window(html)

def _copy_invoice_to_clipboard(inv):
    """Copy human-readable summary."""
    text = f"{inv['ma']} · {inv['tg']}\n{inv.get('khach','')} · {inv.get('sdt','')}\n"
    text += f"Tổng: {fmt_money(inv.get('tra', 0))}\n"
    for it in inv.get("items", []):
        text += f"  - {it['ten']} × {it['sl']} = {fmt_money(it['tt'])}\n"
    st.session_state["_hd_clipboard"] = text
    st.toast("📋 Đã sao chép HĐ vào clipboard", icon="✅")
    # Real clipboard write requires js: st.components.v1.html(<script>...</script>)

def _build_invoice_print_html(inv) -> str:
    """Trả về HTML 80mm-friendly cho in nhiệt. Tự design tuỳ máy in."""
    return f"<html><body><pre>{inv['ma']}\n...</pre></body></html>"
```

---

## 7. PR strategy

### PR 1 — Foundation
- Add `static/hoa_don.css`, `utils/hd_style.py`
- Add `load_psc_for_apsc()` vào `utils/db.py` (section 4)
- Add `inject_hoa_don_css()` ở đầu `module_hoa_don()`
- Add helper `_build_invoice_dicts`, `_items_from_rows`
- **Không** đổi layout — vẫn giữ 3 sub-tab
- Verify: trang render, không lỗi import, font load ok

### PR 2 — Layout refactor
- ✂️ Replace 3 sub-tabs + render_invoice → smart search + filter container + master-detail grid
- Click card → state `hd_sel_ma` → rail update
- Block PSC trong rail tự động hoạt động (đã có wire ở PR 1)

### PR 3 — Polish
- Print invoice (Blob URL) → real implementation
- Clipboard copy bằng JS
- Sticky rail CSS verify
- Status counts cập nhật realtime khi filter date change

---

## 8. Test checklist (manual)

### As nhân viên
- [ ] Trang load → branch caption + title + filter row + master-detail grid
- [ ] Gõ "0912" → filter HĐ có SĐT chứa 0912
- [ ] Gõ "AHD000165" → tìm thấy đúng 1 HĐ
- [ ] Gõ "mai" → match khách hàng "Chị Mai"
- [ ] Click 1 HĐ POS → rail hiện chi tiết, KHÔNG có block PSC
- [ ] Click 1 HĐ APSC có "Mã YCSC" match phiếu sửa chữa → rail hiện 1 card PSC vàng đủ thông tin (mã PSC, tên hiệu/sản phẩm, ngày nhận DD/MM/YYYY, hẹn trả, KTV, badge trạng thái có màu)
- [ ] Click 1 HĐ APSC mà "Mã YCSC" rỗng → rail KHÔNG hiện block PSC (graceful)
- [ ] Click 1 HĐ APSC mà ma_ycsc không match bản ghi nào trong phieu_sua_chua → block PSC ẩn (graceful)
- [ ] Click 1 HĐ Đổi/Trả → rail hiện 2 bảng trả/mua, KHÔNG hiện block PSC
- [ ] Filter PTTT=CK → chỉ HĐ có Chuyển khoản > 0
- [ ] Filter NV=Bích Phượng → chỉ HĐ của NV đó
- [ ] Status segmented Đã hủy → chỉ HĐ hủy
- [ ] Date range tuần trước → filter đúng

### As admin
- [ ] Tất cả như trên + filter chi nhánh "Tất cả" → thấy HĐ từ nhiều CN
- [ ] HĐ APSC có liên kết PSC → rail hiển thị card PSC đầy đủ

### Edge cases
- [ ] Search trả về 0 → caption "Không tìm thấy"
- [ ] HĐ không có NV → list card hiển thị "—"
- [ ] HĐ không có SĐT (Khách lẻ) → hiện "Khách lẻ" muted, không lỗi
- [ ] Click HĐ rồi đổi filter → `hd_sel_ma` không còn trong filtered → rail về empty state
- [ ] Badge "🔗 PSC" chỉ hiện trên list card APSC có ma_ycsc match — KHÔNG hiện trên HĐ POS/Đổi-Trả/KiotViet thường

---

## 9. Khi bị stuck

1. **CSS không apply cho card list**: card list dùng INLINE styles từ `list_card_html` → không phụ thuộc CSS file. Kiểm tra `style="..."` trong HTML output (View Source).
2. **Click vào card không trigger rerun**: `st.button` đặt SAU `st.html(card)` — verify key unique theo `inv["ma"]`.
3. **`@st.cache_data` cho `load_psc_for_apsc` không invalidate**: TTL 120s, hoặc call `load_psc_for_apsc.clear()` sau khi update phiếu sửa chữa.
4. **Sticky rail không hoạt động**: Streamlit columns dùng flex; cần selector `[data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2)` + `position:sticky;top:60px`. Có thể bị Streamlit header che — chỉnh `top:3.5rem`.
5. **st.radio không hiển thị segmented**: verify CSS `[data-testid="stRadio"] > div[role="radiogroup"]` đã có trong `static/hoa_don.css`.
6. **Tên cột "Người bán" thiếu hoặc khác máy**: fallback list `NGUOI_BAN_COLS` — kiểm tra dữ liệu thực tế từ KiotViet vs POS.
7. **Block PSC không hiện cho HĐ APSC**: verify (a) cột "Mã YCSC" tồn tại trong `data` DataFrame (chạy `print(data.columns)`), (b) giá trị "Mã YCSC" khớp với `ma_phieu` trong bảng `phieu_sua_chua`, (c) hàm `load_psc_for_apsc` return non-None khi gọi thủ công trong Python console.
8. **Block PSC hiện toàn dấu "—"**: nghĩa là `inv["psc"]` là dict rỗng hoặc dict có keys khác với expected. Verify `load_psc_for_apsc` đã normalize keys đúng (`ma`, `san_pham`, `ngay_nhan`, `ngay_tra`, `tinh_trang`, `kt_vien`).

---

## 10. Sau khi xong

- Update `AI_CONTEXT.md`:
  - Thêm note về `utils/hd_style.py` (inline styles pattern theo STREAMLIT_DESIGN_RULES.md)
  - Thêm note về quan hệ 1:1 `hoa_don."Mã YCSC"` ↔ `phieu_sua_chua.ma_phieu`
- Commit message: `feat(hoa_don): redesign UI - master-detail rail + smart search + PSC linkage`
- Update screenshot trong repo README.

Good luck! 🚀

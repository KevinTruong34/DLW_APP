# Implementation Guide — `hang_hoa.py` redesign

Step-by-step instructions để áp dụng design lên codebase `DLW_APP`. Mỗi section là 1 đơn vị có thể PR riêng. Code có nhãn `# 📌 NEW` cho phần thêm mới, `# ✂️ REPLACE` cho phần thay thế. Logic không có nhãn = **giữ nguyên 100%**.

---

## 0. Chuẩn bị

```bash
# Trong root repo DLW_APP/
mkdir -p static
cp design_handoff_hang_hoa/hang_hoa.css        static/hang_hoa.css
cp design_handoff_hang_hoa/utils_hh_style.py   utils/hh_style.py
```

Verify `streamlit>=1.31` trong `requirements.txt` (cần cho `@st.dialog`).

---

## 1. Inject CSS một lần ở đầu `module_hang_hoa()`

### File: `modules/hang_hoa.py`

**Trước:**
```python
def module_hang_hoa():
    try:
        active     = get_active_branch()
        accessible = get_accessible_branches()
```

**Sau:**
```python
from utils.hh_style import inject_hang_hoa_css, hh_html  # 📌 NEW

def module_hang_hoa():
    inject_hang_hoa_css()                                 # 📌 NEW
    try:
        active     = get_active_branch()
        accessible = get_accessible_branches()
```

Test: mở module — verify font Be Vietnam Pro đã load (devtools → Network → check google fonts request thành công).

---

## 2. Toolbar (chi nhánh + search + lọc + thêm)

### Trước (rời rạc, nhiều block riêng)
```python
# Chi nhánh filter
view_branches = st.multiselect("Chi nhánh:", accessible, default=[active], ...)

# ... load data ...

col_s, col_f = st.columns([5, 1])
with col_s:
    keyword = st.text_input("", placeholder="🔍  Tìm mã hàng...", ...)
with col_f:
    with st.popover("⊡ Lọc", use_container_width=True):
        cha_chon = st.selectbox(...)
        con_chon = st.selectbox(...)
```

### Sau (gom 1 toolbar row)

```python
# ✂️ REPLACE: cụm chi nhánh + search + lọc + thêm
hh_html('<div class="hh-toolbar">')

# Cột 1: branch chips wrapper (custom HTML wrap quanh st.multiselect)
hh_html('<div class="hh-branches">')
if is_ke_toan_or_admin() and len(accessible) > 1:
    view_branches = st.multiselect(
        "Chi nhánh:", accessible, default=[active],
        key="hh_cn", label_visibility="collapsed",
    )
    if not view_branches:
        st.warning("Chọn ít nhất một chi nhánh."); return
else:
    view_branches = [active]
hh_html('</div>')

# Cột 2: search
_sc = st.session_state.get("hh_search_cnt", 0)
keyword = st.text_input(
    "", key=f"hh_search_{_sc}",
    placeholder="Tìm mã hàng, mã vạch hoặc tên…",
    label_visibility="collapsed",
)

# Cột 3: popover Lọc
cha_list = sorted([c for c in df["_cha"].dropna().unique() if c])  # build sau khi load df; xem note bên dưới
with st.popover("⊟ Lọc", use_container_width=False):
    cha_chon = st.selectbox(
        "Nhóm hàng:", ["Tất cả"] + cha_list,
        key="hh_cha", label_visibility="collapsed",
    )
    if cha_chon != "Tất cả":
        con_list = sorted([c for c in
            df[df["_cha"] == cha_chon]["_con"].dropna().unique() if c])
        con_chon = st.selectbox(
            "Nhóm con:", ["Tất cả"] + con_list,
            key="hh_con", label_visibility="collapsed",
        )
    else:
        con_chon = "Tất cả"

# Cột 4: nút Thêm (admin)
if is_admin():
    if st.button("➕ Thêm hàng", type="primary", key="hh_add_open"):
        st.session_state["_hh_show_add_dialog"] = True

hh_html('</div>')  # /.hh-toolbar
```

**Note quan trọng**: thứ tự code hiện tại là `load data → build df → toolbar`. Sau khi refactor, **toolbar vẫn phải đặt SAU khi build `df`** (vì popover Lọc cần `cha_list`). Đừng đảo thứ tự — chỉ thay đổi cách render.

Nếu muốn toolbar ở đầu trang **trước** dữ liệu: dựng `cha_list` từ `master` thay vì `df`:
```python
cha_list = sorted([c for c in master["loai_hang"].dropna().unique() if c]) \
           if not master.empty else []
```

---

## 3. Caption row

### Trước
```python
total = len(filtered)
filter_label = (f"{cha_chon}" if cha_chon != "Tất cả" else "")
st.caption(f"**{total}** sản phẩm" + ...)
```

### Sau
```python
from utils.hh_style import render_caption                # 📌 NEW

render_caption(
    total=len(filtered),
    branches=view_branches,
    filter_label=cha_chon if cha_chon != "Tất cả" else None,
)
```

---

## 4. Master-detail grid

### Trước (table xong rồi mới đến detail card xếp dọc)
```python
event = st.dataframe(disp, ..., on_select="rerun", selection_mode="multi-row", key="hh_table", ...)
# rồi xử lý sel
if ma_chon:
    # render card xếp dọc dưới
    ...
```

### Sau (split 60/40)
```python
col_table, col_rail = st.columns([6, 4], gap="medium")

with col_table:
    event = st.dataframe(
        disp,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key="hh_table",
        column_config={
            "Tên hàng": st.column_config.TextColumn("Tên hàng", width="medium"),
            "Mã hàng":  st.column_config.TextColumn("Mã hàng",  width="medium"),
            "Mã vạch":  st.column_config.TextColumn("Mã vạch",  width="medium"),
            "Tồn kho":  st.column_config.NumberColumn("Tồn", width="small", format="%d"),
        },
        height=tbl_h,
    )
    sel = event.selection.rows if event.selection else []

    # Hint row
    hh_html(
        '<div class="hh-hint-row">'
        '↑ Chọn 1 dòng để xem chi tiết · chọn nhiều dòng để in tem hàng loạt'
        '</div>'
    )

    # Cập nhật hh_ma_chon từ selection (logic cũ, không đổi)
    if len(sel) == 1 and sel[0] < len(disp):
        new_ma = disp.iloc[sel[0]]["Mã hàng"]
        if new_ma != ma_chon:
            st.session_state["hh_ma_chon"] = new_ma
            st.rerun()
    elif len(sel) >= 2 and ma_chon:
        st.session_state.pop("hh_ma_chon", None)
        st.rerun()

with col_rail:
    # 📌 NEW: rail có 3 nhánh state
    if len(sel) >= 2:
        _render_rail_multi(sel, disp, filtered)
    elif ma_chon:
        _render_rail_single(filtered, ma_chon, active)
    else:
        from utils.hh_style import render_empty_rail
        render_empty_rail()
```

Wrap `col_rail` content trong sticky div bằng CSS đã có. Nếu Streamlit phá sticky, fallback: bỏ `position:sticky` và chấp nhận panel cuộn cùng trang.

---

## 5. `_render_rail_single` — detail card + admin actions

Tạo hàm mới (move logic detail card hiện tại vào đây):

```python
def _render_rail_single(filtered, ma_chon, active):                # 📌 NEW
    from utils.hh_style import (
        render_detail_card_open, render_stock_tiles,
        render_detail_card_close, hh_html,
    )
    row_m = filtered[filtered["ma_hang"] == ma_chon].iloc[0]

    # Tính breadcrumb LOẠI › THƯƠNG HIỆU
    cha = str(row_m.get("_cha", "") or "")
    con = str(row_m.get("_con", "") or "")
    breadcrumb = (f"{cha} › {con}" if con else cha).upper()

    # Header + body (đến trước stocks)
    render_detail_card_open(
        ten_hang=str(row_m.get("ten_hang", "")),
        breadcrumb=breadcrumb,
        ma_hang=str(row_m.get("ma_hang", "")),
        ma_vach=str(row_m.get("ma_vach", "") or ""),
        thuong_hieu=str(row_m.get("thuong_hieu", "") or ""),
        loai_sp=str(row_m.get("loai_sp", "") or "Hàng hóa"),
        bao_hanh=str(row_m.get("bao_hanh", "") or ""),
        gia_ban=int(row_m.get("gia_ban", 0) or 0),
    )

    # Stock 3 chi nhánh — giữ nguyên cách lấy branch_tons từ all_kho
    try:
        all_kho = load_the_kho(branches_key=tuple(ALL_BRANCHES))
        branch_tons = {cn: 0 for cn in ALL_BRANCHES}
        branch_kho_ids = {cn: None for cn in ALL_BRANCHES}
        if not all_kho.empty:
            rows_kho = all_kho[
                all_kho["Mã hàng"].astype(str).str.strip() == str(ma_chon).strip()
            ]
            for _, kr in rows_kho.iterrows():
                cn = kr.get("Chi nhánh", "")
                if cn in branch_tons:
                    branch_tons[cn] += int(kr.get("Tồn cuối kì", 0) or 0)
                    branch_kho_ids[cn] = kr.get("id")

        render_stock_tiles(
            branches=list(ALL_BRANCHES),
            stocks=branch_tons,
            current=active,
            short=CN_SHORT,
        )
    except Exception:
        branch_tons = {cn: 0 for cn in ALL_BRANCHES}
        branch_kho_ids = {cn: None for cn in ALL_BRANCHES}

    # Admin actions (giữ nguyên logic, chỉ đổi cách render)
    if is_admin():
        # "Chỉnh tồn kho" — dùng st.expander (CSS đã override để đẹp)
        with st.expander("✎ Chỉnh tồn kho", expanded=False):
            adj_cols = st.columns(3)
            adj_vals = {}
            for idx, cn_name in enumerate(ALL_BRANCHES):
                with adj_cols[idx]:
                    adj_vals[cn_name] = st.number_input(
                        CN_SHORT.get(cn_name, cn_name),
                        min_value=0,
                        value=branch_tons[cn_name],
                        step=1,
                        key=f"adj_ton_{ma_chon}_{cn_name}",
                    )
            if st.button("💾 Lưu tồn kho", type="primary",
                         use_container_width=True, key=f"save_ton_{ma_chon}"):
                # ── giữ NGUYÊN block try/changed/insert/update/log_action ──
                # (copy nguyên xi từ code cũ)
                ...

        # Sửa + Ẩn (2 nút cạnh nhau)
        c_edit, c_hide = st.columns([3, 1])
        with c_edit:
            if st.button("✎ Sửa thông tin", use_container_width=True,
                         key=f"hh_open_edit_{ma_chon}"):
                st.session_state[f"_hh_show_edit_{ma_chon}"] = True

        with c_hide:
            if st.button("🚫", help="Ẩn hàng hóa", use_container_width=True,
                         key=f"hh_open_hide_{ma_chon}"):
                st.session_state[f"_hh_show_hide_{ma_chon}"] = True

        # Modal Sửa thông tin
        if st.session_state.get(f"_hh_show_edit_{ma_chon}"):
            _dlg_sua_hang_hoa(row_m)

        # Confirm Ẩn (inline trong rail)
        if st.session_state.get(f"_hh_show_hide_{ma_chon}"):
            _render_an_hang_hoa(str(ma_chon), str(row_m.get("ten_hang", "")))

    # Close card
    render_detail_card_close()

    # Nút In tem (1 SP)
    if st.button("🏷 In tem mã vạch", type="primary",
                 use_container_width=True, key=f"hh_print_single_{ma_chon}"):
        _ma_vach = "" if pd.isna(row_m.get("ma_vach")) else str(row_m.get("ma_vach")).strip()
        st.session_state["_hh_in_tem_items"] = [{
            "ma_hang":  str(row_m.get("ma_hang", "")),
            "ten_hang": str(row_m.get("ten_hang", "")),
            "gia_ban":  int(row_m.get("gia_ban", 0) or 0),
            "ma_vach":  _ma_vach,
            "qty":      1,
        }]
        st.session_state.pop("_intem_hh_qty", None)
        _dlg_in_tem_hh()
```

---

## 6. `_render_rail_multi` — queue card khi multi-select

```python
def _render_rail_multi(sel, disp, filtered):                        # 📌 NEW
    from utils.hh_style import hh_html
    n = len(sel)

    # Build list items
    items_html = []
    for idx in sel[:50]:                 # cap display at 50, scroll handles rest
        if idx >= len(disp): continue
        ten = disp.iloc[idx]["Tên hàng"]
        ma  = disp.iloc[idx]["Mã hàng"]
        items_html.append(
            f'<li><span class="ten">{ten}</span>'
            f'<span class="ma">{ma}</span><span class="rm">×</span></li>'
        )

    hh_html(
        f'<div class="hh-card hh-queue">'
        f'  <div class="hh-card-head">'
        f'    <div class="row1">'
        f'      <div>'
        f'        <h3>Đã chọn {n} sản phẩm</h3>'
        f'        <div class="breadcrumb">SẴN SÀNG IN TEM</div>'
        f'      </div>'
        f'    </div>'
        f'  </div>'
        f'  <ul>{"".join(items_html)}</ul>'
        f'  <div style="padding:10px 12px;border-top:1px solid var(--hh-border);'
        f'              background:var(--hh-surface-2);'
        f'              display:flex;align-items:center;justify-content:space-between;'
        f'              font-size:12.5px">'
        f'    <span style="color:var(--hh-ink-3)">Tổng số tem: '
        f'      <b style="color:var(--hh-ink);font-family:var(--hh-mono)">{n}</b></span>'
        f'    <span class="hh-badge">CODE128</span>'
        f'  </div>'
        f'</div>'
    )

    # Nút In N tem (giữ nguyên logic build items_for_print từ code cũ)
    if st.button(f"🏷 In {n} tem mã vạch", type="primary",
                 use_container_width=True, key="hh_print_multi"):
        items_for_print = []
        for idx in sel:
            if idx >= len(disp): continue
            mh = disp.iloc[idx]["Mã hàng"]
            row = filtered[filtered["ma_hang"] == mh]
            if row.empty: continue
            r = row.iloc[0]
            ma_vach_raw = r.get("ma_vach")
            ma_vach_clean = "" if pd.isna(ma_vach_raw) else str(ma_vach_raw).strip()
            gia_ban_raw = r.get("gia_ban", 0)
            gia_ban_clean = 0 if pd.isna(gia_ban_raw) else int(gia_ban_raw or 0)
            items_for_print.append({
                "ma_hang":  str(r.get("ma_hang", "")),
                "ten_hang": str(r.get("ten_hang", "")),
                "gia_ban":  gia_ban_clean,
                "ma_vach":  ma_vach_clean,
                "qty":      1,
            })
        st.session_state["_hh_in_tem_items"] = items_for_print
        st.session_state.pop("_intem_hh_qty", None)
        _dlg_in_tem_hh()
```

---

## 7. Chuyển "Thêm hàng hóa" sang `@st.dialog`

### Trước
```python
if is_admin():
    st.markdown("---")
    with st.expander("➕ Thêm hàng hóa mới", expanded=False):
        _render_them_moi()
```

### Sau (đặt ở cuối `module_hang_hoa()`):
```python
# Trigger sẵn ở toolbar (xem section 2): st.button(...) set _hh_show_add_dialog = True
if is_admin() and st.session_state.pop("_hh_show_add_dialog", False):
    _dlg_them_hang()                                              # 📌 NEW


@st.dialog("➕ Thêm hàng hóa mới", width="large")
def _dlg_them_hang():                                              # 📌 NEW
    _render_them_moi()
```

Hàm `_render_them_moi()` đã có sẵn — không sửa. Chỉ wrap nó trong dialog. CSS đã override để form trông đẹp.

**Cải thiện nhỏ** trong `_render_them_moi()`: thay `st.columns(2)` thành ` c1, c2 = st.columns(2, gap="medium")` để spacing khớp design.

---

## 8. Chuyển "Sửa thông tin" sang dialog

### Trước
```python
with st.expander("✏️ Sửa thông tin hàng hóa", expanded=False):
    _render_sua_hang_hoa(row_m)
```

### Sau
```python
@st.dialog("✎ Sửa thông tin hàng hóa", width="large")              # 📌 NEW
def _dlg_sua_hang_hoa(row_m):
    _render_sua_hang_hoa(row_m)
    if st.button("Đóng", key=f"close_dlg_sua_{row_m['ma_hang']}"):
        st.session_state.pop(f"_hh_show_edit_{row_m['ma_hang']}", None)
        st.rerun()
```

`_render_sua_hang_hoa()` không sửa logic.

---

## 9. CSS-only checks — không sửa Python

Một số yếu tố visual hoàn toàn do CSS — verify bằng cách so sánh với `reference_hifi.html`:

| Yếu tố | Selector CSS | Verify |
|---|---|---|
| Background trang | `body` / `.main` | `#f7f7f8` |
| Header table uppercase | `[data-testid="stDataFrame"] thead` | Header chữ HOA, 11.5px |
| Selected row đỏ nhạt | `.hh-table tbody tr.sel` hoặc Streamlit native | `#fdecee` + viền trái đỏ |
| Border-radius card | `.hh-card`, `.hh-empty` | 10px |
| Shadow card | `.hh-card` | `--hh-shadow-sm` |
| Font mono cho mã | `.hh-code-pill`, `td.mono` | JetBrains Mono |
| Pin emoji ở current branch | `.hh-stock.curr .name` | Có "📍 " prefix |

---

## 10. Test checklist (manual)

Sau khi merge, test các flow sau ở viewport 1440×900:

### As nhân viên (non-admin)
- [ ] Trang load → thấy toolbar + bảng + empty rail (không cuộn dọc)
- [ ] Gõ vào search → bảng filter realtime, count caption cập nhật
- [ ] Click popover Lọc → chọn Nhóm hàng → bảng filter
- [ ] Click 1 dòng → detail card xuất hiện rail phải (3 stock tiles, current branch viền đỏ)
- [ ] Click ✕ trên card → card đóng, rail về empty state
- [ ] Click 1 dòng → nút "🏷 In tem mã vạch" → dialog in tem mở, có 1 item
- [ ] Tick checkbox 3 dòng → rail biến thành queue, hiện 3 items, nút "🏷 In 3 tem..."
- [ ] Click nút trong queue → dialog in tem mở với đúng 3 items
- [ ] **KHÔNG** thấy nút "+ Thêm hàng", "Chỉnh tồn kho", "Sửa", "Ẩn"

### As admin
- [ ] Toolbar có nút "+ Thêm hàng" màu đỏ
- [ ] Click → modal "Thêm hàng hóa mới" mở
- [ ] Nhập Mã + Tên → "Thêm hàng hóa" enable, click → toast success, modal đóng, bảng refresh
- [ ] Mã trùng → error message "đã tồn tại"
- [ ] Mở 1 dòng có sẵn → thấy expander "Chỉnh tồn kho" + nút "Sửa thông tin" + nút icon "Ẩn"
- [ ] Mở "Chỉnh tồn kho" → đổi giá trị → "Lưu tồn kho" → toast success, stock tiles cập nhật
- [ ] Click "Sửa thông tin" → dialog mở, sửa, lưu → bảng refresh
- [ ] Click nút Ẩn (đỏ) → confirm UI hiện inline → "✓ Xác nhận ẩn" → SP biến mất khỏi bảng

### Kế toán/admin với nhiều chi nhánh
- [ ] Toolbar hiện chips chi nhánh, default = active branch
- [ ] Thêm chi nhánh khác → caption count cập nhật, stock tiles vẫn đúng 3 CN

### Edge cases
- [ ] Tìm kiếm không kết quả → "Không tìm thấy hàng hóa phù hợp" (admin vẫn thấy nút thêm)
- [ ] Database trống → message "Chưa có dữ liệu hàng hóa" (admin vẫn thêm được)
- [ ] Resize browser xuống 1000px → grid collapse 1 cột, detail xuống dưới bảng
- [ ] Rerun 10 lần liên tục → không có Python warning, không có FOUC nặng

---

## 11. PR strategy

Đề xuất chia 3 PR nhỏ để dễ review:

### PR 1: Foundation
- Add `static/hang_hoa.css`
- Add `utils/hh_style.py`
- Add `inject_hang_hoa_css()` call ở đầu `module_hang_hoa()`
- **Không** thay đổi layout — chỉ load CSS
- Verify: trang render với font + màu mới, layout cũ

### PR 2: Layout refactor
- Refactor toolbar (1 row sticky)
- Refactor master-detail thành `st.columns([6, 4])`
- Move detail logic vào `_render_rail_single/multi/empty`
- Caption sang `render_caption()`
- **Không** đổi dialog/modal — vẫn dùng expander cho Thêm/Sửa

### PR 3: Dialogs + polish
- "Thêm hàng" → `@st.dialog`
- "Sửa thông tin" → `@st.dialog`
- Tweak CSS final pass (so sánh từng pixel với `reference_hifi.html`)
- Update screenshot trong `AI_CONTEXT.md` (nếu có)

---

## 12. Khi bị stuck

1. **CSS không apply**: Inspect element → confirm class `.hh-*` đã có trên DOM. Nếu thiếu → check `hh_html()` call.
2. **`st.dataframe` selection mất sau rerun**: đặt `key="hh_table"` cố định (đã có).
3. **Sticky toolbar bị Streamlit header che**: thêm `top: 3.5rem` trong `.hh-toolbar` thay vì `top: 0`.
4. **`@st.dialog` không xuất hiện**: confirm Streamlit ≥1.31. Check Python console không có warning về deprecated dialog API.
5. **Font không load**: check Network tab → fonts.googleapis.com request. Nếu fail → host font tại `static/fonts/` và serve qua `@font-face` local.

---

## 13. Sau khi xong

- Update `AI_CONTEXT.md`: thêm note về cấu trúc mới `utils/hh_style.py` và `static/hang_hoa.css`.
- Commit message gợi ý: `feat(hang_hoa): redesign UI - sticky toolbar + right-rail master-detail`
- Tag screenshot mới vào README repo.

Good luck! 🚀

# HANDOFF Claude Code — Module Kiểm kê v2 redesign

> **Bundle**: README.md, Kiem_ke_Hi-fi_v2.html, Kiem_ke_Hi-fi.html (deprecated), Kiem_ke_Wireframes.html, kiem_ke_current.py, design_system_constraints.md
>
> **Status**: Design đã regen v2 sau review. Bundle đã trải qua 1 vòng review fix 3 vấn đề lớn (Hi-fi class-based, tab switching, bảng phiếu). Đây là handoff bổ sung từ planning, **đọc cùng với README.md trong bundle**, không thay thế nó.
>
> File này addresses các vấn đề Design không cover được (vì là Python implementation detail) + lessons learnt từ 4 vòng debug `hoa_don.py` trước.

---

## 0. PRE-FLIGHT (BẮT BUỘC trước khi sửa code)

Chạy và report ngay trước khi viết code nào:

```bash
# 1. Streamlit version
python -c "import streamlit; print(streamlit.__version__)"
# Mong đợi: ≥1.35 (vì cần st.dataframe on_select + st.dialog)

# 2. Verify Design files có sẵn
ls -la design_handoff_kiem_ke/  # hoặc folder bundle đã unzip
# Phải có: README.md, Kiem_ke_Hi-fi_v2.html, kiem_ke_current.py, design_system_constraints.md

# 3. Verify Hi-fi v2 thật sự inline-style (không phải v1 cũ)
grep -c 'class="' design_handoff_kiem_ke/Kiem_ke_Hi-fi_v2.html
grep -c 'style="' design_handoff_kiem_ke/Kiem_ke_Hi-fi_v2.html
# Mong đợi: class < 50, style > 150. Nếu sai tỉ lệ → KHÔNG phải v2 → DỪNG báo user.
```

**Report 3 kết quả** ở comment PR/message đầu tiên trước khi viết code.

Nếu Streamlit < 1.35 → DỪNG, hỏi user upgrade. **KHÔNG fallback im lặng** — sẽ tạo bug khó debug sau.

---

## 1. NHỮNG BÀI HỌC ÁP DỤNG TỪ MODULE HOÁ ĐƠN (4 vòng debug trước)

Module Hoá đơn trải qua 4 vòng fix vì các pattern sau **KHÔNG WORK** trong Streamlit. Cùng pattern sẽ tái lập bug nếu áp dụng vào Kiểm kê. **TUYỆT ĐỐI tránh**:

### 1.1. CSS injection — bài học root cause

❌ **KHÔNG dùng** `st.html("<style>...</style>")` để inject CSS — DOMPurify sanitizer strip `<style>` tags silently. CSS có vẻ "load OK" nhưng KHÔNG apply được. Đây là silent failure root cause của 3 vòng debug đầu hoa_don.

✅ **DÙNG**: `st.markdown(unsafe_allow_html=True)` với block `<style>`:

```python
# Đầu module_kiem_ke(), gọi 1 lần
st.markdown("""
<style>
:root {
    --green-50: #ecfdf5;
    --green-100: #d1fae5;
    --green-200: #a7f3d0;
    --green-500: #10b981;
    --green-600: #059669;
    --green-700: #047857;
    --green-800: #065f46;
    --green-900: #064e3b;
    --ink: #0b1220;
    --ink-2: #475569;
    --ink-3: #94a3b8;
    --line: #e5e7eb;
    --line-strong: #cbd5e1;
    --surface: #ffffff;
    --surface-2: #f8fafc;
    --surface-3: #f1f5f9;
    --bg: #f6f7f5;
    --warn-50: #fffbeb;
    --warn-200: #fde68a;
    --warn-700: #b45309;
    --bad-50: #fef2f2;
    --bad-200: #fecaca;
    --bad-500: #ef4444;
    --bad-700: #b91c1c;
    --info-50: #eff6ff;
    --info-200: #bfdbfe;
    --info-700: #1d4ed8;
    --r-sm: 6px;
    --r: 10px;
    --r-lg: 14px;
    --r-xl: 18px;
    --shadow-1: 0 1px 2px rgba(15,23,42,.04), 0 1px 1px rgba(15,23,42,.03);
    --shadow-2: 0 4px 14px -4px rgba(15,23,42,.10), 0 2px 4px rgba(15,23,42,.04);
    --shadow-card: 0 8px 28px -10px rgba(4,120,87,.18), 0 2px 6px rgba(15,23,42,.04);
    --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    --sans: 'Plus Jakarta Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* Keyframes cho flash animation — chạy được trong cùng block */
@keyframes flashOk {
    0%   { background-color: var(--green-50); box-shadow: 0 0 0 3px var(--green-100); }
    100% { background-color: var(--surface); box-shadow: var(--shadow-card); }
}
@keyframes flashBad {
    0%   { background-color: var(--bad-50); box-shadow: 0 0 0 3px var(--bad-200); }
    100% { background-color: var(--surface); box-shadow: var(--shadow-card); }
}

/* DEBUG MARKER — confirm CSS injection works.
   Xóa trong commit follow-up sau khi user verify. */
.stApp::before {
    content: "KIEMKE_v2_LIVE" !important;
    position: fixed !important;
    bottom: 4px !important; right: 4px !important;
    background: var(--green-700) !important; color: white !important;
    padding: 2px 8px !important; border-radius: 4px !important;
    font-size: 10px !important; font-family: var(--mono) !important;
    z-index: 99999 !important; opacity: 0.6 !important;
    pointer-events: none !important;
}
</style>
""", unsafe_allow_html=True)
```

`static/kiem_ke.css` chỉ chứa: font @import + Streamlit native widget overrides (`[data-testid="stButton"] button`, etc).

### 1.2. URL navigation pattern → mất session → logout

❌ **KHÔNG dùng** `<a href="?param=X" target="_self">` trong card hoặc bất kỳ HTML render qua `st.html`. Browser xử lý là full page navigation → Streamlit reload page → mất session_state → mất auth → logout.

✅ **DÙNG**: `st.button` callback (Streamlit native, qua WebSocket, không reload page).

### 1.3. Click-anywhere pattern — chỉ apply nếu cần thiết

Nếu cần "click anywhere on row triggers action" (như card hoa_don), pattern đúng là:

```python
with st.container(key="my_clickable_X"):
    st.html(card_markup)
    if st.button(" ", key=f"btn_X", use_container_width=True):
        # action
```

CSS overlay button invisible (đã verify work với hoa_don v4):
```css
[class*="st-key-my_clickable_"] {
    position: relative !important;
    cursor: pointer !important;
}
[class*="st-key-my_clickable_"] [data-testid="stElementContainer"]:has([data-testid="stButton"]) {
    position: absolute !important; inset: 0 !important;
    margin: 0 !important; padding: 0 !important;
    z-index: 10 !important;
}
[class*="st-key-my_clickable_"] [data-testid="stButton"] > button {
    width: 100% !important; height: 100% !important;
    background: transparent !important; border: none !important;
    color: transparent !important; opacity: 0 !important;
    cursor: pointer !important;
}
```

**TUY NHIÊN**: README section 8 chốt **dùng `st.dataframe(on_select="rerun")` cho bảng phiếu**, KHÔNG dùng pattern click-card. Vậy chỉ cần pattern này nếu sau này cần (vd: card phiếu trong empty state click → tạo phiếu mới).

---

## 2. CÁC ĐIỂM TRONG README CẦN OVERRIDE / LÀM RÕ

### 2.1. Section 7.3 (scan flow) — KHÔNG cache `_kk_get_lines`

README đề xuất "*Cache `_kk_get_lines` với TTL ngắn (10s)*". **KHÔNG làm**.

**Lý do**: `_kk_get_lines` đọc data thay đổi mỗi lần scan (sl_quet, sl_thuc_te). Cache TTL 10s sẽ gây:
- User scan → DB update → rerun → `_kk_get_lines` trả về data CACHED CŨ → bảng không hiện cập nhật → user tưởng scan fail → scan lại lần 2 → `sl_quet` đột nhiên = +2.

**Đúng**: giữ `_kk_get_lines` không cache (như hiện tại). Loại bỏ `st.cache_data.clear()` global ở scan flow. Code current dòng 417:

```python
# Current
if submitted:
    ok, msg = _kk_scan_plus_one(ma_phieu, code)
    if ok:
        st.success(f"✓ Đã cộng +1 cho mã {msg}")
        st.cache_data.clear()      # ← BỎ DÒNG NÀY
```

`_kk_scan_plus_one` đã update DB. Rerun sau đó sẽ tự fetch lại `_kk_get_lines` (vì hàm không cache). `st.cache_data.clear()` chỉ cần thiết để invalidate `load_phieu_kiem_ke` (cache thật) — gọi cụ thể:

```python
if ok:
    load_phieu_kiem_ke.clear()    # invalidate header list
    # _kk_get_lines KHÔNG cần clear vì không cache
```

### 2.2. Section 7.3 — Diễn giải "lag" trong README factually sai

README ghi: "*Hiện tại `_kk_scan_plus_one()` đồng bộ: 1. reload toàn bộ chi tiết phiếu, 2. `st.cache_data.clear()` → mọi data fetch khác cũng phải re-fetch*"

Đọc code current dòng 154-220: `_kk_scan_plus_one` **KHÔNG reload chi tiết phiếu** (chỉ SELECT 1 mã + 1 UPDATE/INSERT). **KHÔNG có `st.cache_data.clear()`** bên trong hàm.

Cache clear xảy ra ở **caller** (tab_scan dòng 417). Bottleneck thật là:
1. `st.cache_data.clear()` global → toàn bộ data tab khác cũng re-fetch
2. Full module rerun → render lại 4 tab (sau v2 còn 2 tab)
3. Network RTT Supabase Cloud → Streamlit Cloud (~150-300ms)

**Việc cần làm**:
- Thay `st.cache_data.clear()` global bằng `load_phieu_kiem_ke.clear()` granular
- Add timing log vào PR description (không phải code thực):
  ```python
  # Tạm thêm cho measurement, REMOVE trước final commit:
  import time
  if submitted:
      t0 = time.perf_counter()
      ok, msg = _kk_scan_plus_one(ma_phieu, code)
      t1 = time.perf_counter()
      load_phieu_kiem_ke.clear()
      st.toast(f"⏱ Scan: {(t1-t0)*1000:.0f}ms", icon="⏱️")  # remove sau khi đo
  ```
- Document timing trước và sau optimize trong PR description. **KHÔNG cam kết** target ms cụ thể (latency không đảm bảo được).

### 2.3. Section 7.2 — Auto-focus JS pattern README đề xuất KHÔNG reliable

README dùng `input[aria-label*="Quét"]` — selector này không match khi `label_visibility="collapsed"` (Streamlit không render aria-label thấy được trong DOM).

**Override**: dùng pattern retry + selector chính xác hơn:

```python
def _auto_focus_scan_input() -> None:
    """Inject JS retry-focus pattern. Call sau mỗi rerun."""
    st.html("""
    <script>
    (function() {
        function tryFocus() {
            const doc = (window.parent && window.parent.document) || document;
            // Find all text inputs, focus the last one (scan input is always last in tab Quét)
            const inputs = doc.querySelectorAll('[data-testid="stTextInputRootElement"] input, [data-testid="stTextInput"] input');
            if (inputs.length === 0) return false;
            const inp = inputs[inputs.length - 1];
            if (doc.activeElement !== inp) {
                inp.focus();
                inp.select();  // select all để máy quét overwrite
            }
            return true;
        }
        // Retry vài lần — DOM có thể chưa stable
        let tries = 0;
        const id = setInterval(() => {
            if (tryFocus() || ++tries > 15) clearInterval(id);
        }, 60);
    })();
    </script>
    """)
```

**Gọi**: cuối tab Quét, sau khi render tất cả widgets (bao gồm form scan). Mỗi rerun chạy lại.

**Lưu ý**: nếu module có nhiều text input trên trang khác (vd. search ở Quản lý phiếu), `inputs[length-1]` có thể chọn nhầm. Đảm bảo tab Quét active thì input scan là cuối cùng. Verify bằng cách render gì khác trên tab Quét trước scan input.

### 2.4. Section 7.4 — AudioContext unlock gating

README có nhắc trình duyệt chặn AudioContext trước user gesture nhưng không có code unlock. Trong production: lần quét đầu của user sẽ silent.

**Override**: unlock AudioContext khi user click bất kỳ button nào trên module:

```python
def _audio_unlock_script() -> None:
    """Inject script unlock AudioContext on first user gesture.
    Call 1 lần ở đầu module, đặt SAU st.markdown CSS injection."""
    st.html("""
    <script>
    (function() {
        if (window.__kk_unlocked) return;
        const doc = (window.parent && window.parent.document) || document;
        function unlock() {
            try {
                const ac = window.__kk_ac || (window.__kk_ac = new (window.AudioContext || window.webkitAudioContext)());
                if (ac.state === 'suspended') ac.resume();
                window.__kk_unlocked = true;
                doc.removeEventListener('click', unlock);
                doc.removeEventListener('keydown', unlock);
            } catch(e) {}
        }
        doc.addEventListener('click', unlock, { once: false });
        doc.addEventListener('keydown', unlock, { once: false });
    })();
    </script>
    """)
```

Hàm `_play_beep()` (như README) gọi `ac.resume()` đầu mỗi lần chơi (idempotent, không hại).

### 2.5. Section 8.3 — st.dataframe selection API caveat

Code đề xuất:
```python
selected = st.dataframe(..., on_select="rerun", selection_mode="single-row", ...)
sel_rows = selected.selection.rows if selected and hasattr(selected, "selection") else []
```

**Caveat**: Streamlit ≥1.35 trả về `DataframeSelectionState` object có `.selection.rows` (list of int). API có thể đổi giữa version 1.35 → 1.40 → 1.45. Verify bằng:

```python
selected = st.dataframe(...)
# Defensive:
try:
    sel_rows = selected.selection.rows
except (AttributeError, TypeError):
    sel_rows = []
```

Nếu API khác → DỪNG, báo user.

### 2.6. Bảng phiếu cần precompute "Tiến độ" trước khi pass vào dataframe

README section 8.3 nói "*Tính cột 'Tiến độ' = sum(sl_thuc_te)/sum(ton_snapshot) * 100 (qua join trước)*". Nhưng `load_phieu_kiem_ke` chỉ trả về header (1 row/phiếu), không có chi tiết.

**Cần thêm**: 1 query batch lấy progress cho tất cả phiếu trong list, hoặc compute từ existing data nếu có. Pattern:

```python
def _kk_get_progress_map(ma_phieus: tuple[str, ...]) -> dict[str, float]:
    """Return {ma_phieu: progress_percentage} for batch of phieu codes."""
    if not ma_phieus:
        return {}
    # Single query group by ma_phieu
    res = supabase.rpc("get_kiem_ke_progress", {"p_ma_phieus": list(ma_phieus)}).execute()
    # Hoặc nếu không có RPC, query trực tiếp:
    # res = supabase.table("phieu_kiem_ke_chi_tiet") \
    #     .select("ma_phieu_kk, ton_snapshot, sl_thuc_te") \
    #     .in_("ma_phieu_kk", list(ma_phieus)).execute()
    # Sau đó groupby trong Python.
    return {}  # implement
```

**Hoặc đơn giản hơn**: bỏ cột "Tiến độ" khỏi bảng → chỉ hiển thị trong detail panel. Đề xuất chọn cách này — simple hơn, không phải thêm DB query.

### 2.7. Hi-fi v2 có demo JS interaction — chỉ là reference visual

File `Kiem_ke_Hi-fi_v2.html` có `<script>` để demo interaction (scan flow, filter, modal). **Không copy script** — đây là demo. Logic thật viết bằng Python Streamlit.

Chỉ copy **markup HTML** (các đoạn `<div style="...">...</div>`).

---

## 3. THỨ TỰ COMMIT — chia nhỏ để rollback dễ

| PR | Nội dung | Test |
|---|---|---|
| 1 | Inject CSS variables + DEBUG MARKER + skeleton 2 tab. Logic giữ nguyên (4 sub-tab cũ wrap trong tab "Quản lý phiếu" tạm thời). | Mở app → thấy badge `KIEMKE_v2_LIVE` góc dưới phải. Module load OK. |
| 2 | Tab Quét: hero card empty state + scan flow refactor (split lookup/write) + auto-focus + beep + audio unlock. | Bắn máy quét → hero card update + beep + flash. |
| 3 | Tab Quét: filter chips + KPI tiles + context bar. | Click chip → bảng filter đúng. |
| 4 | Tab Quản lý: native dataframe + filter chips + search. | Click row → state lưu. |
| 5 | Tab Quản lý: detail panel với action buttons context theo status. | Click row → panel render. Action button work. |
| 6 | `@st.dialog` Tạo phiếu mới. | Click "+ Tạo phiếu" → dialog mở. |
| 7 | Polish: animation flash, hover effect (JS-based, không class :hover), final styling. | Visual match Hi-fi v2. |
| 8 | Cleanup: xóa DEBUG MARKER, xóa timing logs, doc finalize. | Badge biến mất. |

Mỗi PR có smoke test 5-10 items trong description.

---

## 4. CRITICAL LOGIC PRESERVATION CHECKS

Sau PR 5 (xong cả 2 tab), verify regression bằng test sau:

| Test | Expected |
|---|---|
| Tạo phiếu KK mới qua dialog → check DB | INSERT vào `phieu_kiem_ke` + `phieu_kiem_ke_chi_tiet` đúng schema |
| Scan mã hợp lệ trong phiếu → check DB | `sl_quet`, `sl_thuc_te` += 1 |
| Scan mã không trong phiếu nhưng có trong master → check DB | INSERT row mới với `ton_snapshot=0` |
| Scan mã không tồn tại → UI error, không touch DB | Beep bad + flash đỏ |
| Hoàn thành phiếu → check DB | `trang_thai` = "Chờ duyệt admin" |
| Duyệt phiếu (admin) → check the_kho | `the_kho` updated theo RPC `duyet_phieu_kiem_ke` |
| Hủy phiếu → check DB | DELETE cả 2 bảng |
| Edit `SL Thực Tế` qua data_editor → save → check DB | UPDATE đúng row |
| Xuất Excel KiotViet → file download | Format 2 cột "Mã hàng" / "Số lượng" |

8 hàm `_kk_*` ở đầu file (kiem_ke_current.py dòng 18-280) **không sửa signature**. Chỉ sửa cách UI gọi chúng.

---

## 5. TUYỆT ĐỐI KHÔNG LÀM

- ❌ KHÔNG `st.html("<style>...")` để inject CSS — bị DOMPurify strip. Dùng `st.markdown(unsafe_allow_html=True)`.
- ❌ KHÔNG `<a href="?...">` cho navigation — gây logout (bài học hoa_don.py).
- ❌ KHÔNG cache `_kk_get_lines` TTL — gây stale data.
- ❌ KHÔNG `st.cache_data.clear()` global sau scan — chỉ clear function cụ thể.
- ❌ KHÔNG đổi thứ tự `tab_scan, tab_manage` dựa state — disorient UX.
- ❌ KHÔNG render bảng phiếu bằng `iterrows + st.columns + st.button` per row — DOM nặng + lỏng lẻo.
- ❌ KHÔNG sửa signature 8 hàm `_kk_*` helpers.
- ❌ KHÔNG sửa logic `_kk_scan_plus_one`, `_kk_approve` (RPC atomic).
- ❌ KHÔNG copy markup từ `Kiem_ke_Hi-fi.html` (v1 cũ) — copy từ `Kiem_ke_Hi-fi_v2.html`.
- ❌ KHÔNG copy `<script>` JS demo từ Hi-fi v2 — đó là demo, logic thật viết Python.
- ❌ KHÔNG dùng class CSS trên `<div>`/`<span>`/`<section>` content trong `st.html()` — inline style only.
- ❌ KHÔNG fallback im lặng nếu Streamlit < 1.35 — DỪNG báo user.
- ❌ KHÔNG xóa DEBUG MARKER trong PR đầu — chỉ xóa ở PR cuối sau khi user verify.

---

## 6. VERIFICATION TỪNG PR

### PR 1 (skeleton + CSS injection)
- [ ] Badge `KIEMKE_v2_LIVE` xuất hiện ở góc dưới phải
- [ ] DevTools Inspect 1 element bất kỳ → Computed → font-family chứa "Plus Jakarta Sans" hoặc system fallback
- [ ] Module load không error, 4 tab cũ vẫn work (chưa refactor)

### PR 2 (hero card + scan flow)
- [ ] Bắn máy quét USB → hero card update trong dưới 1s perceived
- [ ] Quét thành công: beep + flash xanh
- [ ] Quét sai: beep đôi + flash đỏ + error text
- [ ] Auto-focus: sau mỗi quét, input ready cho mã tiếp theo

### PR 3-7
- Theo acceptance criteria README section 12

### PR 8 (cleanup)
- [ ] Badge `KIEMKE_v2_LIVE` không còn
- [ ] Toast timing log không còn
- [ ] No console errors trong DevTools

---

## 7. KHI BỊ STUCK

1. **CSS không apply ở 1 component**: verify bằng badge DEBUG MARKER. Có badge → CSS inject OK. Nếu component vẫn không style → kiểm tra inline style có resolved `var(--token)` không (DevTools Computed tab phải show hex value, không phải `var(...)`).
2. **`@st.dialog` không có**: pre-flight đã check version. Nếu vẫn lỗi, fallback `st.expander(expanded=True)` ở vị trí cố định.
3. **`st.dataframe(on_select)` không có**: pre-flight đã check. Nếu lỗi → DỪNG báo user, không tự fallback.
4. **Auto-focus không work**: open DevTools Network → khi rerun, có thấy script inject không? Console có error? Selector match được element nào? Tạm thời thêm `console.log(inputs)` vào tryFocus để debug.
5. **Beep không phát**: DevTools Console → check window.__kk_ac state. Nếu "suspended" → user gesture chưa unlock. Click bất cứ button → retry.
6. **Click row dataframe không trigger detail panel**: kiểm tra `selected.selection.rows` ở backend (print trong console). Có thể API khác → adjust theo.

---

## 8. PR DESCRIPTION TEMPLATE

```
## Module Kiểm kê v2 — PR <N>/<Total>

### What
<summary 1 dòng>

### Files changed
<list>

### Smoke test (chạy trên Streamlit Cloud preview branch)
- [ ] Test 1: <description> → <result>
- [ ] Test 2: <description> → <result>

### Screenshots
- Trước: <link/paste>
- Sau: <link/paste>

### Timing measurements (chỉ PR 2 có scan flow)
- Scan round-trip trước: ___ ms
- Scan round-trip sau: ___ ms

### Verified DEBUG MARKER badge visible: [ ] Yes / [ ] No
```

---

## 9. NHỜ USER VERIFY SAU MỖI PR

Mỗi PR, sau khi deploy preview branch, mention user check:
- [ ] Badge `KIEMKE_v2_LIVE` còn không
- [ ] Visual match Hi-fi v2 không (paste screenshot so sánh)
- [ ] Smoke test pass không

Đợi user xác nhận trước khi mở PR tiếp.

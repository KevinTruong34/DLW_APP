 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/app.py b/app.py
index d9528834cff8a9049d94e9232deb4b9d3d41a27a..918ab12178d807371a729d1b2f0f9adf39854501 100644
--- a/app.py
+++ b/app.py
@@ -14,51 +14,51 @@ import logging
 # ==========================================
 # Format: [thời gian] [level] [user@chi_nhanh] action: chi tiết
 logging.basicConfig(
     level=logging.INFO,
     format="%(asctime)s [%(levelname)s] %(message)s",
     datefmt="%Y-%m-%d %H:%M:%S",
 )
 _logger = logging.getLogger("watchstore")
 
 
 def log_action(action: str, detail: str = "", level: str = "info"):
     """
     Ghi log hành động của user.
     Prefix tự động [username@chi_nhanh] để biết ai làm gì.
     """
     user = st.session_state.get("user") or {}
     cn   = st.session_state.get("active_chi_nhanh", "-")
     username = user.get("username", "anonymous")
     prefix = f"[{username}@{cn}]"
     msg = f"{prefix} {action}"
     if detail:
         msg += f" — {detail}"
     getattr(_logger, level, _logger.info)(msg)
 
 # ==========================================
-# PHIEN BAN: 15.0 — Fix UI + Tao phieu chuyen
+# PHIEN BAN: 15.1 — Hotfix deploy (clean app.py header)
 # ==========================================
 
 st.set_page_config(page_title="Watch Store", layout="wide")
 
 st.markdown("""
 <style>
 /* ══════════════════════════════════════════
    PHIEN BAN: 15.0 — Force light theme
    ══════════════════════════════════════════ */
 
 /* ── FORCE LIGHT MODE (fix Edge dark stuck) ── */
 :root {
     color-scheme: light only !important;
     --bg-main: #f5f6f8;
     --bg-card: #ffffff;
     --text-main: #1a1a2e;
     --text-muted: #888;
     --border: #e8e8e8;
     --accent: #e63946;
 }
 html, body, .stApp, [data-testid="stAppViewContainer"] {
     background: #f5f6f8 !important;
     color: #1a1a2e !important;
     color-scheme: light only !important;
 }
@@ -877,50 +877,391 @@ def load_phieu_chuyen_kho(branches_key: tuple = None):
     if not all_rows:
         return pd.DataFrame()
     df = pd.DataFrame(all_rows)
     if branches_key:
         bk = list(branches_key)
         mask = df["tu_chi_nhanh"].isin(bk) | df["toi_chi_nhanh"].isin(bk)
         df = df[mask].reset_index(drop=True)
     for col in ["so_luong_chuyen","so_luong_nhan","tong_sl_chuyen","tong_sl_nhan",
                 "tong_mat_hang","gia_chuyen","thanh_tien_chuyen","thanh_tien_nhan","tong_gia_tri"]:
         if col in df.columns:
             df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
     if "ngay_chuyen" in df.columns:
         df["_ngay"] = pd.to_datetime(df["ngay_chuyen"], errors="coerce")
         df["_date"] = df["_ngay"].dt.date
     return df
 
 
 def get_gia_ban_map() -> dict:
     """Map ma_hang → gia_ban từ master hang_hoa."""
     hh = load_hang_hoa()
     if hh.empty or "ma_hang" not in hh.columns or "gia_ban" not in hh.columns:
         return {}
     return dict(zip(hh["ma_hang"].astype(str), hh["gia_ban"].fillna(0).astype(int)))
 
 
+# ==========================================
+# MODULE: KIỂM KÊ — MVP v1
+# Workflow: Nháp/Đang kiểm → Chờ duyệt admin → Đã duyệt
+# ==========================================
+
+@st.cache_data(ttl=120)
+def load_phieu_kiem_ke(branches_key: tuple = None) -> pd.DataFrame:
+    rows, batch, offset = [], 1000, 0
+    while True:
+        q = supabase.table("phieu_kiem_ke").select("*").order("created_at", desc=True)
+        res = q.range(offset, offset + batch - 1).execute()
+        if not res.data:
+            break
+        rows.extend(res.data)
+        if len(res.data) < batch:
+            break
+        offset += batch
+
+    if not rows:
+        return pd.DataFrame()
+    df = pd.DataFrame(rows)
+    if branches_key and "chi_nhanh" in df.columns:
+        df = df[df["chi_nhanh"].isin(list(branches_key))].reset_index(drop=True)
+    if "created_at" in df.columns:
+        df["_created"] = pd.to_datetime(df["created_at"], errors="coerce")
+    return df
+
+
+def _kk_get_lines(ma_phieu: str) -> pd.DataFrame:
+    res = supabase.table("phieu_kiem_ke_chi_tiet").select("*") \
+        .eq("ma_phieu_kk", ma_phieu).execute()
+    if not res.data:
+        return pd.DataFrame()
+    df = pd.DataFrame(res.data)
+    for col in ["ton_snapshot", "sl_quet", "sl_thuc_te", "ton_ky_vong_luc_duyet", "chenh_lech"]:
+        if col in df.columns:
+            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
+    return df
+
+
+def _kk_gen_ma_phieu() -> str:
+    try:
+        res = supabase.table("phieu_kiem_ke").select("ma_phieu_kk") \
+            .like("ma_phieu_kk", "KK______").order("ma_phieu_kk", desc=True).limit(1).execute()
+        if res.data:
+            try:
+                num = int(str(res.data[0]["ma_phieu_kk"])[2:]) + 1
+            except Exception:
+                num = 1
+        else:
+            num = 1
+        return f"KK{num:06d}"
+    except Exception:
+        return f"KK{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:4].upper()}"
+
+
+def _kk_build_scope_rows(chi_nhanh: str, nhom_cha: str) -> tuple[list, str]:
+    master = load_hang_hoa()
+    kho = load_the_kho(branches_key=(chi_nhanh,))
+    if master.empty or kho.empty:
+        return [], "Chưa đủ dữ liệu master/thẻ kho để tạo phiếu kiểm kê."
+
+    # Join tồn kho theo mã
+    kho_map = kho.groupby("Mã hàng", as_index=False).agg(ton=("Tồn cuối kì", "sum"))
+    df = master.merge(kho_map, left_on="ma_hang", right_on="Mã hàng", how="left")
+    df["ton"] = pd.to_numeric(df["ton"], errors="coerce").fillna(0).astype(int)
+
+    nhom_col = df["nhom_hang"].fillna("") if "nhom_hang" in df.columns else pd.Series([""] * len(df))
+    split = nhom_col.str.split(">>", n=1, expand=True)
+    df["_cha"] = split[0].fillna("").str.strip()
+    df = df[(df["_cha"] == nhom_cha) & (df["ton"] > 0)].copy()
+    if df.empty:
+        return [], f"Nhóm **{nhom_cha}** không có hàng tồn > 0 tại chi nhánh này."
+
+    rows = []
+    for _, r in df.iterrows():
+        rows.append({
+            "ma_hang": str(r.get("ma_hang", "") or ""),
+            "ma_vach": str(r.get("ma_vach", "") or ""),
+            "ten_hang": str(r.get("ten_hang", "") or ""),
+            "nhom_hang": str(r.get("nhom_hang", "") or ""),
+            "ton_snapshot": int(r.get("ton", 0) or 0),
+            "sl_quet": 0,
+            "sl_thuc_te": 0,
+            "ton_ky_vong_luc_duyet": 0,
+            "chenh_lech": 0,
+            "trang_thai_dong": "Đang kiểm",
+        })
+    return rows, ""
+
+
+def _kk_create_phieu(chi_nhanh: str, nhom_cha: str, ghi_chu: str) -> tuple[bool, str]:
+    rows, err = _kk_build_scope_rows(chi_nhanh, nhom_cha)
+    if err:
+        return False, err
+
+    ma = _kk_gen_ma_phieu()
+    user = get_user() or {}
+    try:
+        supabase.table("phieu_kiem_ke").insert({
+            "ma_phieu_kk": ma,
+            "chi_nhanh": chi_nhanh,
+            "trang_thai": "Đang kiểm",
+            "nhom_cha": nhom_cha,
+            "ghi_chu": ghi_chu.strip(),
+            "created_by": user.get("ho_ten", ""),
+            "created_at": datetime.now().isoformat(),
+            "completed_at": None,
+            "approved_by": None,
+            "approved_at": None,
+        }).execute()
+
+        payload = []
+        for r in rows:
+            p = dict(r)
+            p["ma_phieu_kk"] = ma
+            payload.append(p)
+        for i in range(0, len(payload), 500):
+            supabase.table("phieu_kiem_ke_chi_tiet").insert(payload[i:i+500]).execute()
+        st.cache_data.clear()
+        log_action("KIEMKE_CREATE", f"ma={ma} cn={chi_nhanh} nhom={nhom_cha} rows={len(rows)}")
+        return True, ma
+    except Exception as e:
+        return False, f"Lỗi tạo phiếu kiểm kê: {e}"
+
+
+def _kk_scan_plus_one(ma_phieu: str, code: str) -> tuple[bool, str]:
+    code = str(code or "").strip()
+    if not code:
+        return False, "Mã quét rỗng."
+    code_n = _normalize(code)
+    try:
+        rows = supabase.table("phieu_kiem_ke_chi_tiet") \
+            .select("id,ma_hang,ma_vach,sl_quet,sl_thuc_te") \
+            .eq("ma_phieu_kk", ma_phieu).execute().data or []
+        hit = None
+        for r in rows:
+            mh = _normalize(str(r.get("ma_hang", "") or ""))
+            mv = _normalize(str(r.get("ma_vach", "") or ""))
+            if code_n and (code_n == mh or code_n == mv):
+                hit = r
+                break
+        if not hit:
+            return False, f"Không tìm thấy mã trong phạm vi phiếu: {code}"
+
+        sl_quet = int(hit.get("sl_quet", 0) or 0) + 1
+        sl_tt = int(hit.get("sl_thuc_te", 0) or 0) + 1
+        supabase.table("phieu_kiem_ke_chi_tiet").update({
+            "sl_quet": sl_quet,
+            "sl_thuc_te": sl_tt
+        }).eq("id", hit["id"]).execute()
+        return True, str(hit.get("ma_hang", "") or code)
+    except Exception as e:
+        return False, f"Lỗi scan: {e}"
+
+
+def _kk_complete(ma_phieu: str) -> tuple[bool, str]:
+    try:
+        supabase.table("phieu_kiem_ke").update({
+            "trang_thai": "Chờ duyệt admin",
+            "completed_at": datetime.now().isoformat(),
+        }).eq("ma_phieu_kk", ma_phieu).execute()
+        supabase.table("phieu_kiem_ke_chi_tiet").update({
+            "trang_thai_dong": "Chờ duyệt admin"
+        }).eq("ma_phieu_kk", ma_phieu).execute()
+        st.cache_data.clear()
+        log_action("KIEMKE_COMPLETE", f"ma={ma_phieu}")
+        return True, "Đã chuyển phiếu sang trạng thái Chờ duyệt admin."
+    except Exception as e:
+        return False, f"Lỗi hoàn thành phiếu: {e}"
+
+
+def _kk_approve(ma_phieu: str) -> tuple[bool, str]:
+    try:
+        lines = _kk_get_lines(ma_phieu)
+        if lines.empty:
+            return False, "Phiếu không có dòng hàng."
+        for _, r in lines.iterrows():
+            ton_ss = int(r.get("ton_snapshot", 0) or 0)
+            sl_tt = int(r.get("sl_thuc_te", 0) or 0)
+            ch = sl_tt - ton_ss
+            supabase.table("phieu_kiem_ke_chi_tiet").update({
+                "ton_ky_vong_luc_duyet": ton_ss,
+                "chenh_lech": ch,
+                "trang_thai_dong": "Đã duyệt",
+            }).eq("id", int(r["id"])).execute()
+
+        supabase.table("phieu_kiem_ke").update({
+            "trang_thai": "Đã duyệt",
+            "approved_by": (get_user() or {}).get("ho_ten", ""),
+            "approved_at": datetime.now().isoformat(),
+        }).eq("ma_phieu_kk", ma_phieu).execute()
+        st.cache_data.clear()
+        log_action("KIEMKE_APPROVE", f"ma={ma_phieu}")
+        return True, "Đã duyệt phiếu kiểm kê."
+    except Exception as e:
+        return False, f"Lỗi duyệt phiếu: {e}"
+
+
+def module_kiem_ke():
+    st.markdown("### 🧮 Kiểm kê")
+    st.caption("MVP v1: Quét +1 mỗi lần, hoàn thành → chờ admin duyệt.")
+    active = get_active_branch()
+    accessible = get_accessible_branches()
+
+    tab_list, tab_create, tab_scan, tab_approve = st.tabs(
+        ["Danh sách phiếu", "Tạo phiếu", "Quét kiểm kê", "Duyệt admin"]
+    )
+
+    with tab_list:
+        try:
+            df = load_phieu_kiem_ke(tuple(accessible))
+            if df.empty:
+                st.info("Chưa có phiếu kiểm kê.")
+            else:
+                show_cols = ["ma_phieu_kk", "chi_nhanh", "nhom_cha", "trang_thai", "created_by", "created_at", "ghi_chu"]
+                show_cols = [c for c in show_cols if c in df.columns]
+                st.dataframe(df[show_cols], use_container_width=True, hide_index=True, height=420)
+        except Exception as e:
+            st.error(f"Không tải được danh sách phiếu kiểm kê: {e}")
+            st.caption("Kiểm tra đã tạo bảng Supabase: phieu_kiem_ke / phieu_kiem_ke_chi_tiet.")
+
+    with tab_create:
+        cn_create = active
+        if is_ke_toan_or_admin() and len(accessible) > 1:
+            cn_create = st.selectbox("Chi nhánh kiểm kê:", accessible, index=max(0, accessible.index(active)))
+        master = load_hang_hoa()
+        if master.empty:
+            st.warning("Chưa có dữ liệu hàng hóa.")
+        else:
+            nhom_col = master["nhom_hang"].fillna("") if "nhom_hang" in master.columns else pd.Series([""] * len(master))
+            split = nhom_col.str.split(">>", n=1, expand=True)
+            master["_cha"] = split[0].fillna("").str.strip()
+            nhom_cha_list = sorted([x for x in master["_cha"].dropna().unique() if str(x).strip()])
+            if not nhom_cha_list:
+                st.warning("Không tìm thấy nhóm hàng cha trong master (cột nhom_hang).")
+            else:
+                nhom_cha = st.selectbox("Nhóm hàng cha:", nhom_cha_list)
+                ghi_chu = st.text_area("Ghi chú phiếu:", key="kk_ghi_chu_create",
+                                       placeholder="Ví dụ: Kiểm kê giữa ca, tập trung đồng hồ Citizen...")
+                if st.button("Tạo phiếu kiểm kê", type="primary", use_container_width=True):
+                    ok, msg = _kk_create_phieu(cn_create, nhom_cha, ghi_chu)
+                    if ok:
+                        st.session_state["kk_active_ma"] = msg
+                        st.success(f"Đã tạo phiếu {msg}.")
+                        st.rerun()
+                    else:
+                        st.error(msg)
+
+    with tab_scan:
+        try:
+            df = load_phieu_kiem_ke(tuple(accessible))
+            if df.empty:
+                st.info("Chưa có phiếu để quét.")
+            else:
+                candidates = df[df["trang_thai"] == "Đang kiểm"].copy() if "trang_thai" in df.columns else pd.DataFrame()
+                if candidates.empty:
+                    st.info("Không có phiếu ở trạng thái Đang kiểm.")
+                else:
+                    opts = [f"{r['ma_phieu_kk']} · {r.get('chi_nhanh','')} · {r.get('nhom_cha','')}" for _, r in candidates.iterrows()]
+                    idx = 0
+                    ma_saved = st.session_state.get("kk_active_ma")
+                    if ma_saved:
+                        for i, x in enumerate(opts):
+                            if x.startswith(ma_saved):
+                                idx = i
+                                break
+                    picked = st.selectbox("Chọn phiếu đang kiểm:", opts, index=idx)
+                    ma_phieu = picked.split(" · ")[0]
+                    st.session_state["kk_active_ma"] = ma_phieu
+
+                    with st.form("kk_scan_form", clear_on_submit=True):
+                        code = st.text_input("Quét mã vạch / mã hàng:", key="kk_scan_code",
+                                             placeholder="Đưa con trỏ ở đây và quét...")
+                        submitted = st.form_submit_button("Quét +1", use_container_width=True)
+                    if submitted:
+                        ok, msg = _kk_scan_plus_one(ma_phieu, code)
+                        if ok:
+                            st.success(f"✓ Đã cộng +1 cho mã {msg}")
+                            st.cache_data.clear()
+                        else:
+                            st.warning(msg)
+
+                    lines = _kk_get_lines(ma_phieu)
+                    if not lines.empty:
+                        view = lines.copy()
+                        view["chênh lệch tạm"] = view["sl_thuc_te"] - view["ton_snapshot"]
+                        cols = ["ma_hang", "ma_vach", "ten_hang", "ton_snapshot", "sl_quet", "sl_thuc_te", "chênh lệch tạm"]
+                        cols = [c for c in cols if c in view.columns]
+                        st.dataframe(view[cols], use_container_width=True, hide_index=True, height=360)
+                        c1, c2, c3 = st.columns(3)
+                        with c1:
+                            st.metric("Số SKU", f"{len(view)}")
+                        with c2:
+                            st.metric("Tổng quét", f"{int(view['sl_quet'].sum())}")
+                        with c3:
+                            lech = int((view["sl_thuc_te"] - view["ton_snapshot"]).abs().sum())
+                            st.metric("Tổng lệch tuyệt đối", f"{lech}")
+
+                        if st.button("Hoàn thành kiểm kê (chờ admin duyệt)",
+                                     type="primary", use_container_width=True):
+                            ok, msg = _kk_complete(ma_phieu)
+                            if ok:
+                                st.success(msg)
+                                st.rerun()
+                            else:
+                                st.error(msg)
+        except Exception as e:
+            st.error(f"Lỗi màn hình quét kiểm kê: {e}")
+
+    with tab_approve:
+        if not is_admin():
+            st.info("Chỉ admin có quyền duyệt phiếu kiểm kê.")
+        else:
+            try:
+                df = load_phieu_kiem_ke(tuple(accessible))
+                pending = df[df["trang_thai"] == "Chờ duyệt admin"].copy() if (not df.empty and "trang_thai" in df.columns) else pd.DataFrame()
+                if pending.empty:
+                    st.info("Không có phiếu chờ duyệt.")
+                else:
+                    opts = [f"{r['ma_phieu_kk']} · {r.get('chi_nhanh','')} · {r.get('nhom_cha','')}" for _, r in pending.iterrows()]
+                    picked = st.selectbox("Phiếu chờ duyệt:", opts, key="kk_pending_pick")
+                    ma_phieu = picked.split(" · ")[0]
+                    lines = _kk_get_lines(ma_phieu)
+                    if not lines.empty:
+                        lines["chenh_lech_du_kien"] = lines["sl_thuc_te"] - lines["ton_snapshot"]
+                        cols = ["ma_hang", "ten_hang", "ton_snapshot", "sl_thuc_te", "chenh_lech_du_kien"]
+                        cols = [c for c in cols if c in lines.columns]
+                        st.dataframe(lines[cols], use_container_width=True, hide_index=True, height=320)
+                        st.warning("Lưu ý: MVP v1 chưa ingest realtime bán hàng ngoài hệ thống, admin cần rà soát trước khi duyệt.")
+                        if st.button("Duyệt & chốt phiếu", type="primary", use_container_width=True):
+                            ok, msg = _kk_approve(ma_phieu)
+                            if ok:
+                                st.success(msg)
+                                st.rerun()
+                            else:
+                                st.error(msg)
+            except Exception as e:
+                st.error(f"Lỗi màn hình duyệt phiếu: {e}")
+
+
 # ==========================================
 # MODULE: TỔNG QUAN — FIX NameError (bỏ dashboard)
 # ==========================================
 
 def module_tong_quan():
     """
     Tổng quan — welcome + tóm tắt nhanh.
     KHÔNG còn dashboard doanh số (đã chuyển sang Quản trị).
     """
     user   = get_user()
     active = get_active_branch()
     role_label = {
         "admin":     "Admin",
         "ke_toan":   "Kế toán",
         "nhan_vien": "Nhân viên"
     }.get(user.get("role"), "")
 
     # Greeting card
     st.markdown(
         f"<div style='background:#fff;border:1px solid #e8e8e8;border-radius:12px;"
         f"padding:18px 20px;margin-bottom:12px;'>"
         f"<div style='font-size:0.82rem;color:#888;'>Xin chào</div>"
         f"<div style='font-size:1.25rem;font-weight:700;color:#1a1a2e;margin-top:2px;'>"
         f"{user.get('ho_ten','')}</div>"
         f"<div style='margin-top:8px;'>"
@@ -2907,82 +3248,83 @@ def module_quan_tri():
                     log_action("PHIEU_RESTORE", f"rows={n_archived}",
                               level="warning")
                     st.success(f"✓ Đã khôi phục {n_archived} dòng!")
                     st.rerun()
                 except Exception as e:
                     st.error(f"Lỗi: {e}")
 
     with tab_nv:
         module_nhan_vien()
 
 
 # ==========================================
 # NAVIGATION  v15.0
 # ==========================================
 
 user      = get_user()
 active_cn = get_active_branch()
 sel_cns   = get_selectable_branches()
 cn_short  = CN_SHORT.get(active_cn, active_cn[:8])
 ho_ten    = user.get("ho_ten","") if user else ""
 initials  = "".join(w[0].upper() for w in ho_ten.split()[:2]) if ho_ten else "?"
 role_lbl  = {"admin":"Admin","ke_toan":"Kế toán","nhan_vien":"Nhân viên"}.get(
     user.get("role",""), "")
 
 # Menu: BỎ Tổng quan khỏi vị trí có dashboard — chỉ còn welcome
-menu = ["📊 Tổng quan", "🧾 Hóa đơn", "📦 Hàng hóa", "🔄 Chuyển hàng"]
+menu = ["📊 Tổng quan", "🧾 Hóa đơn", "📦 Hàng hóa", "🧮 Kiểm kê", "🔄 Chuyển hàng"]
 if is_admin(): menu.append("⚙️ Quản trị")
 page = st.radio("nav", menu, horizontal=True, label_visibility="collapsed")
 
 # ── Hàng 2: reload + avatar ──
 col_rel, col_avatar = st.columns([1, 1])
 
 with col_rel:
     if st.button("↺  Tải lại", use_container_width=True, help="Tải lại dữ liệu"):
         st.cache_data.clear(); st.rerun()
 
 with col_avatar:
     with st.popover(initials, use_container_width=True):
         st.markdown(
             f"<div style='text-align:center;padding:8px 0 4px;'>"
             f"<div style='font-size:1.1rem;font-weight:700;'>{ho_ten}</div>"
             f"<div style='font-size:0.8rem;color:#888;'>{role_lbl}</div>"
             f"<div style='font-size:0.78rem;color:#aaa;margin-top:2px;'>"
             f"📍 {active_cn}</div>"
             f"</div>",
             unsafe_allow_html=True)
         st.markdown("---")
 
         if len(sel_cns) > 1:
             st.caption("Đổi chi nhánh:")
             for cn in sel_cns:
                 is_active_cn = (cn == active_cn)
                 lbl = f"✓ {cn}" if is_active_cn else cn
                 if st.button(lbl, key=f"sw_cn_{cn}", use_container_width=True,
                              type="primary" if is_active_cn else "secondary",
                              disabled=is_active_cn):
                     st.session_state["active_chi_nhanh"] = cn
                     save_branch_to_url(cn)
                     # reset giỏ tạo phiếu khi đổi CN
                     st.session_state.pop("ck_items", None)
                     st.rerun()
             st.markdown("---")
 
         if st.button("🚪 Đăng xuất", use_container_width=True, key="btn_logout_pop"):
             do_logout(); st.rerun()
 
 # strip icon từ page value để routing
 page_clean = page.split(" ", 1)[1] if " " in page else page
 st.markdown("<hr style='margin:4px 0 10px 0;'>", unsafe_allow_html=True)
 
 if page_clean == "Tổng quan":     module_tong_quan()
 elif page_clean == "Hóa đơn":     module_hoa_don()
 elif page_clean == "Hàng hóa":    module_hang_hoa()
+elif page_clean == "Kiểm kê":     module_kiem_ke()
 elif page_clean == "Chuyển hàng": module_chuyen_hang()
 elif page_clean == "Quản trị":    module_quan_tri()
 
 # ── SCROLL-TO-BOTTOM RELOAD ──
 st.markdown(
     "<div class='pull-refresh-zone'>↓ Kéo xuống cuối để tải lại ↓</div>",
     unsafe_allow_html=True
 )
 inject_scroll_refresh()
 
EOF
)

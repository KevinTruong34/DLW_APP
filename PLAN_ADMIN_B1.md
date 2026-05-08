# PLAN_ADMIN_B1.md — Admin Override Phase B1: Tạo HĐ tự do

> **Mục đích file:** Plan đầy đủ để execute trong session Claude Code mới. Đã chốt mọi decisions, không cần hỏi user lại trừ khi gặp tình huống ngoài plan.
>
> **Generated:** 2026-05-08
> **Owner:** Kevin (DL Watch)
> **Repos:** `KevinTruong34/DLW_APP` (web app — UI ở đây), `KevinTruong34/dl-watch-pos` (POS — KHÔNG đụng trong B1)
> **DB:** Supabase (Postgres)
> **Phase:** B1 (sẽ có B2 sau — sửa HĐ existing)

---

## 0. CONTEXT

### 0.1 Mục đích Phase B1

Cho phép admin tạo:
- HĐ POS (`hoa_don_pos`)
- Phiếu đổi/trả POS (`phieu_doi_tra_pos`)
- Phiếu sửa chữa (`phieu_sua_chua`)

…với mọi tham số tự do (backdate, người bán/tạo, chi nhánh, đơn giá), bypass mọi constraint của flow normal. Mọi HĐ admin được đánh dấu `is_admin_created=true` để trace, ghi `action_logs` để audit.

### 0.2 Decisions đã chốt (Phase A)

| Decision | Value |
|---|---|
| Permission | `nhan_vien.role = 'admin'` (đã có sẵn) |
| Admin user hiện tại | Đăng Khoa (id=2, username=`0823580710`) |
| UI placement | Web app DLW_APP (giảm tải POS) |
| Scope | 3 loại phiếu (HĐ POS, đổi/trả, sửa chữa) |
| Backdate limit | Max 90 ngày trước `now()` |
| Custom nguoi_ban | Dropdown từ `nhan_vien` (cả `active=false`) |
| Custom chi nhánh | Dropdown 3 chi nhánh hiện có |
| Custom đơn giá | Override mọi item, kể cả hàng thường |
| Số HĐ | Tiếp sequence bình thường (`ahd_seq`, `ahdd_seq`, `sc_seq`) |
| Tác động kho | Trừ kho thật (skip open-price như normal) |
| Cờ đánh dấu | `is_admin_created BOOLEAN` thêm vào 3 bảng |
| Audit log | `action_logs`, pattern `ADMIN_*_CREATE` |
| Confirmation UI | Type "XÁC NHẬN" trước submit |
| Visual marker | Badge "🛡 ADMIN" khi xem chi tiết |
| LINE notification | Không (Q19 = B) |
| Phased deploy | B1 (tạo) → verify 1 tuần → B2 (sửa) |

### 0.3 Inconsistency cột audit giữa 3 bảng

Plan phải handle 3 patterns khác nhau:

| Bảng | Created info | Cancelled info |
|---|---|---|
| `hoa_don_pos` | `nguoi_ban` (text) + `nguoi_ban_id` (bigint, FK) | `cancelled_at`, `cancelled_by` |
| `phieu_doi_tra_pos` | `nguoi_tao` (text) + `nguoi_tao_id` (bigint, FK) | `cancelled_at`, `cancelled_by` |
| `phieu_sua_chua` | `created_by` (text only — không có id) | ❌ KHÔNG có cancelled_* |

→ RPC admin cho phiếu sửa chữa phải store id riêng (vd qua audit log) hoặc thêm cột `created_by_id`. Decision:
- **Recommend:** Thêm `created_by_id BIGINT` vào `phieu_sua_chua` để consistency.

### 0.4 Schema cột tổng tiền `hoa_don_pos` (verified pre-flight)

**KHÔNG có cột `tong_tien`** — actual columns:

| Cột | Kiểu | Vai trò |
|---|---|---|
| `tong_tien_hang` | int | Tổng tiền hàng (sum `so_luong * don_gia` của items) trước giảm giá |
| `giam_gia_don` | int | Giảm giá toàn đơn (default 0) |
| `khach_can_tra` | int | = `tong_tien_hang - giam_gia_don` (số khách phải trả) |
| `tien_mat`, `chuyen_khoan`, `the` | int | Phương thức thanh toán |
| `tien_thua`, `tien_coc_da_thu` | int | Phụ trợ |
| `ma_kh` | text | Mã khách (optional) |

→ RPC admin (§3.2) phải map đúng 3 cột tổng tiền. Default `giam_gia_don=0`, nhưng admin có thể nhập optional để bù HĐ thật có giảm giá (vd HĐ KiotViet gốc có giảm).

### 0.5 Sequences thực tế (verified pre-flight)

| Plan kỳ vọng | Thực tế | Note |
|---|---|---|
| `ahd_seq` | ✓ tồn tại | Dùng cho `hoa_don_pos.ma_hd` (`AHD000XXX`) |
| `ahdd_seq` | ✓ tồn tại | Dùng cho `phieu_doi_tra_pos.ma_pdt` (`AHDD000XXX`) |
| `sc_seq` | **❌ chưa có** | Phải tạo Phase 1; Python `_gen_ma_phieu` hiện dùng `SELECT max+1` (race-prone) |

→ Phase 1 thêm: tạo `sc_seq START WITH (max+1)`, wrapper RPC `next_sc_seq()`, sửa `modules/sua_chua.py:_gen_ma_phieu` dùng RPC.

Bonus: tồn tại `ahdc_seq` (không nằm trong scope B1, để nguyên).

---

## 1. PRE-FLIGHT

### 1.1 Backup

```sql
CREATE TABLE _backup_admin_b1_20260508_hoa_don_pos AS SELECT * FROM hoa_don_pos;
CREATE TABLE _backup_admin_b1_20260508_phieu_doi_tra_pos AS SELECT * FROM phieu_doi_tra_pos;
CREATE TABLE _backup_admin_b1_20260508_phieu_sua_chua AS SELECT * FROM phieu_sua_chua;
CREATE TABLE _backup_admin_b1_20260508_action_logs AS SELECT * FROM action_logs;
```

### 1.2 Verify auth flow code DLW_APP

Trước khi viết RPC + UI, **Claude Code đọc code Python hiện tại** để biết:
- File nào handle login (vd `auth.py`, `login.py`)
- Cách store user info (vd `st.session_state["user"]`)
- Cách check role (vd có hàm `is_admin()` chưa?)
- Pattern UI form đã có (để mới giống cũ)

```bash
# Trong DLW_APP repo
grep -rn "role" --include="*.py"
grep -rn "session_state" --include="*.py"
grep -rn "login\|auth" --include="*.py" | head -20
ls modules/
```

→ **Kết quả grep này quan trọng** — Claude Code phải share trước khi viết code mới.

### 1.3 Verify + tạo sequences

**Verify (đã chạy pre-flight):**

```sql
SELECT sequence_name FROM information_schema.sequences
WHERE sequence_schema = 'public'
  AND (sequence_name LIKE 'ahd%' OR sequence_name LIKE 'sc%');
```

Kết quả pre-flight: `ahd_seq` ✓, `ahdd_seq` ✓, `sc_seq` ❌ (chưa có), `ahdc_seq` (ngoài scope).

**Tạo `sc_seq` + wrapper + sửa Python (Phase 1):**

```sql
-- Lấy max num hiện tại từ ma_phieu format SC######
DO $$
DECLARE
    v_max int;
BEGIN
    SELECT COALESCE(MAX(NULLIF(regexp_replace(ma_phieu, '^SC', ''), '')::int), 0)
    INTO v_max
    FROM phieu_sua_chua
    WHERE ma_phieu ~ '^SC[0-9]+$';

    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS sc_seq START WITH %s', v_max + 1);
END $$;

-- Wrapper để Python gọi qua supabase.rpc()
CREATE OR REPLACE FUNCTION next_sc_seq()
RETURNS bigint
LANGUAGE sql
AS $$ SELECT nextval('sc_seq') $$;
```

**Sửa Python — `DLW_APP/modules/sua_chua.py:173-180`:**

```python
def _gen_ma_phieu() -> str:
    try:
        res = supabase.rpc("next_sc_seq", {}).execute()
        data = res.data
        num = int(data[0]) if isinstance(data, list) and data else int(data) if data else 1
        return f"SC{num:06d}"
    except Exception:
        return f"SC{datetime.now().strftime('%y%m%d%H%M')}"
```

→ Race-safe vĩnh viễn. RPC admin §3.4 cũng dùng `nextval('sc_seq')`.

---

## 2. PHASE 1 — SCHEMA

### 2.1 ALTER TABLE — thêm cờ admin

```sql
BEGIN;

-- HĐ POS
ALTER TABLE hoa_don_pos
    ADD COLUMN is_admin_created BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN admin_note TEXT;

-- Phiếu đổi/trả
ALTER TABLE phieu_doi_tra_pos
    ADD COLUMN is_admin_created BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN admin_note TEXT;

-- Phiếu sửa chữa (+ created_by_id để consistency)
ALTER TABLE phieu_sua_chua
    ADD COLUMN is_admin_created BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN admin_note TEXT,
    ADD COLUMN created_by_id BIGINT;

-- Indexes (partial - chỉ index khi flag true)
CREATE INDEX idx_hd_pos_admin ON hoa_don_pos(is_admin_created) WHERE is_admin_created = true;
CREATE INDEX idx_pdt_pos_admin ON phieu_doi_tra_pos(is_admin_created) WHERE is_admin_created = true;
CREATE INDEX idx_sc_admin ON phieu_sua_chua(is_admin_created) WHERE is_admin_created = true;

COMMIT;
```

### 2.2 Verify

```sql
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('hoa_don_pos', 'phieu_doi_tra_pos', 'phieu_sua_chua')
  AND column_name IN ('is_admin_created', 'admin_note', 'created_by_id')
ORDER BY table_name, column_name;
```

Expected: 7 rows (3 cờ + 3 note + 1 id).

---

## 3. PHASE 2 — RPC SQL (3 functions mới)

### 3.1 Helper: validate_admin_request()

DRY helper để các RPC dùng chung:

```sql
CREATE OR REPLACE FUNCTION _admin_validate_request(
    p_admin_id bigint,
    p_created_at timestamp with time zone
) RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_role text;
    v_active boolean;
BEGIN
    -- Permission check
    SELECT role, active INTO v_role, v_active
    FROM nhan_vien WHERE id = p_admin_id;
    
    IF v_role IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Admin user không tồn tại');
    END IF;
    IF v_role != 'admin' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Permission denied: cần role admin');
    END IF;
    IF NOT v_active THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Admin user đã bị deactivate');
    END IF;
    
    -- Backdate validation
    IF p_created_at IS NOT NULL THEN
        IF p_created_at < now() - INTERVAL '90 days' THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Backdate vượt quá 90 ngày');
        END IF;
        IF p_created_at > now() + INTERVAL '5 minutes' THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Không cho tạo HĐ trong tương lai');
        END IF;
    END IF;
    
    RETURN jsonb_build_object('ok', true);
END;
$$;
```

### 3.2 RPC: `tao_hoa_don_pos_admin`

Tương tự `tao_hoa_don_pos` nhưng:
- Validate admin (dùng helper)
- Cho phép custom mọi field
- Set `is_admin_created = true`
- Ghi `action_logs` với action='ADMIN_HD_CREATE', level='warn'
- Skip stock check cho hàng thường? **NO** — vẫn trừ kho thật (Q12 = a). Nếu kho âm → fail (admin phải kiểm trước).

```sql
CREATE OR REPLACE FUNCTION tao_hoa_don_pos_admin(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_admin_id bigint;
    v_admin_username text;
    v_admin_ho_ten text;
    v_validate jsonb;
    v_created_at timestamp with time zone;
    v_chi_nhanh text;
    v_nguoi_ban_id bigint;
    v_nguoi_ban text;
    v_seq bigint;
    v_ma_hd text;
    v_items jsonb;
    v_item jsonb;
    v_ma_hang text;
    v_so_luong int;
    v_don_gia int;
    v_thanh_tien int;
    v_tong_tien_hang int := 0;
    v_giam_gia_don int := 0;
    v_khach_can_tra int := 0;
    v_ton_hien_tai int;
BEGIN
    -- 1. Extract admin info
    v_admin_id := (payload->>'admin_id')::bigint;
    SELECT username, ho_ten INTO v_admin_username, v_admin_ho_ten
    FROM nhan_vien WHERE id = v_admin_id;
    
    -- 2. Extract created_at
    v_created_at := COALESCE(
        (payload->>'created_at')::timestamp with time zone,
        now()
    );
    
    -- 3. Validate (permission + backdate)
    SELECT _admin_validate_request(v_admin_id, v_created_at) INTO v_validate;
    IF NOT (v_validate->>'ok')::boolean THEN
        RETURN v_validate;
    END IF;
    
    -- 4. Validate items không rỗng
    v_items := COALESCE(payload->'items', '[]'::jsonb);
    IF jsonb_array_length(v_items) = 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'HĐ phải có ít nhất 1 item');
    END IF;
    
    -- 5. Generate ma_hd từ sequence
    v_seq := nextval('ahd_seq');
    v_ma_hd := 'AHD' || LPAD(v_seq::text, 6, '0');
    
    -- 6. Lookup người bán
    v_nguoi_ban_id := (payload->>'nguoi_ban_id')::bigint;
    SELECT ho_ten INTO v_nguoi_ban FROM nhan_vien WHERE id = v_nguoi_ban_id;
    IF v_nguoi_ban IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'nguoi_ban_id không tồn tại');
    END IF;
    
    -- 7. Pre-validate kho cho TẤT CẢ items (atomic check trước khi insert)
    v_chi_nhanh := payload->>'chi_nhanh';
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items)
    LOOP
        v_ma_hang := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        
        IF v_so_luong <= 0 THEN
            RETURN jsonb_build_object('ok', false, 
                'error', format('Item %s: so_luong phải > 0', v_ma_hang));
        END IF;
        
        -- Skip stock check cho open-price
        IF NOT is_open_price_sql(v_ma_hang) THEN
            SELECT COALESCE(SUM("Tồn cuối kì"), 0) INTO v_ton_hien_tai
            FROM the_kho
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
            
            IF v_ton_hien_tai < v_so_luong THEN
                RETURN jsonb_build_object('ok', false,
                    'error', format('Item %s không đủ tồn (có %s, cần %s)', 
                        v_ma_hang, v_ton_hien_tai, v_so_luong));
            END IF;
        END IF;
        
        -- Compute tong_tien_hang
        v_don_gia := (v_item->>'don_gia')::int;
        v_tong_tien_hang := v_tong_tien_hang + (v_so_luong * v_don_gia);
    END LOOP;

    -- 7b. Tính giam_gia_don + khach_can_tra
    v_giam_gia_don := COALESCE((payload->>'giam_gia_don')::int, 0);
    IF v_giam_gia_don < 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'giam_gia_don không được âm');
    END IF;
    IF v_giam_gia_don > v_tong_tien_hang THEN
        RETURN jsonb_build_object('ok', false,
            'error', format('giam_gia_don (%s) vượt quá tong_tien_hang (%s)',
                            v_giam_gia_don, v_tong_tien_hang));
    END IF;
    v_khach_can_tra := v_tong_tien_hang - v_giam_gia_don;

    -- 8. Insert header
    INSERT INTO hoa_don_pos (
        ma_hd, chi_nhanh, ten_khach, sdt_khach,
        nguoi_ban, nguoi_ban_id,
        tien_mat, chuyen_khoan, the,
        tong_tien_hang, giam_gia_don, khach_can_tra,
        ghi_chu, trang_thai,
        is_admin_created, admin_note,
        created_at
    ) VALUES (
        v_ma_hd, v_chi_nhanh,
        payload->>'ten_khach', payload->>'sdt_khach',
        v_nguoi_ban, v_nguoi_ban_id,
        COALESCE((payload->>'tien_mat')::int, 0),
        COALESCE((payload->>'chuyen_khoan')::int, 0),
        COALESCE((payload->>'the')::int, 0),
        v_tong_tien_hang, v_giam_gia_don, v_khach_can_tra,
        payload->>'ghi_chu',
        'Hoàn thành',
        true,
        payload->>'admin_note',
        v_created_at
    );
    
    -- 9. Insert chi tiết + trừ kho
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items)
    LOOP
        v_ma_hang := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia := (v_item->>'don_gia')::int;
        v_thanh_tien := v_so_luong * v_don_gia;
        
        INSERT INTO hoa_don_pos_ct (
            ma_hd, ma_hang, ten_hang, so_luong, don_gia, thanh_tien
        ) VALUES (
            v_ma_hd, v_ma_hang,
            v_item->>'ten_hang',
            v_so_luong, v_don_gia, v_thanh_tien
        );
        
        -- Trừ kho (skip open-price)
        IF NOT is_open_price_sql(v_ma_hang) THEN
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) - v_so_luong
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
        END IF;
    END LOOP;
    
    -- 10. Audit log (level='warn' để dễ filter)
    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        v_admin_username,
        v_admin_ho_ten,
        v_chi_nhanh,
        'ADMIN_HD_CREATE',
        format('ma=%s nguoi_ban=%s (id=%s) created_at=%s tong_hang=%s gg=%s can_tra=%s items=%s note=%s',
               v_ma_hd, v_nguoi_ban, v_nguoi_ban_id,
               v_created_at, v_tong_tien_hang, v_giam_gia_don, v_khach_can_tra,
               jsonb_array_length(v_items),
               COALESCE(payload->>'admin_note', '-')),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_hd', v_ma_hd,
        'tong_tien_hang', v_tong_tien_hang,
        'giam_gia_don', v_giam_gia_don,
        'khach_can_tra', v_khach_can_tra,
        'created_at', v_created_at
    );
END;
$$;
```

**Payload shape:**

```json
{
  "admin_id": 2,
  "created_at": "2026-04-15T14:30:00+07:00",
  "nguoi_ban_id": 5,
  "chi_nhanh": "100 Lê Quý Đôn",
  "ten_khach": "...", "sdt_khach": "...",
  "tien_mat": 500000, "chuyen_khoan": 0, "the": 0,
  "giam_gia_don": 0,
  "ghi_chu": "...",
  "admin_note": "Bù HĐ KiotViet ngày 2026-04-15",
  "items": [
    {"ma_hang": "...", "ten_hang": "...", "so_luong": 1, "don_gia": 500000}
  ]
}
```

### 3.3 RPC: `tao_phieu_doi_tra_pos_admin`

Tương tự nhưng cho phiếu đổi/trả. Khác biệt chính:
- Phải có `ma_hd_goc` (HĐ gốc cần đổi/trả)
- Bypass check "7 ngày" (admin override)
- Items chia 2 loại: `tra` (kho cộng) và `moi` (kho trừ)
- Sequence: `ahdd_seq` → `AHDD000XXX`
- Audit: `ADMIN_PDT_CREATE`

(Implementation details tương tự RPC #3.2, chỉ khác structure items + sequence.)

### 3.4 RPC: `tao_phieu_sua_chua_admin`

**Khác biệt cốt lõi với §3.2 / §3.3:** phiếu sửa chữa **KHÔNG đụng kho**. Logic kho chỉ trigger khi convert sang HĐ APSC (action `SC_HOA_DON` trong action_logs) — flow đó vẫn dùng path normal, RPC admin B1 không can thiệp.

**Scope RPC admin:**
- Validate admin (helper `_admin_validate_request`)
- Insert header `phieu_sua_chua` (chi nhánh, khách, NV tiếp nhận, trạng thái mặc định `'Đang sửa'`, `is_admin_created=true`, `admin_note`, `created_by_id`)
- Insert chi tiết items vào `phieu_sua_chua_chi_tiet` nếu payload có (chỉ ghi nhận giá dịch vụ/phụ tùng — KHÔNG trừ kho)
- Sequence: `sc_seq` → `SC000XXX` (đã tạo Phase 1)
- Audit: `ADMIN_SC_CREATE`, level=`warn`
- Khi admin muốn finalize → convert sang APSC qua flow normal (Phase B2 hoặc UI hiện có)

```sql
CREATE OR REPLACE FUNCTION tao_phieu_sua_chua_admin(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_admin_id bigint;
    v_admin_username text;
    v_admin_ho_ten text;
    v_validate jsonb;
    v_created_at timestamp with time zone;
    v_chi_nhanh text;
    v_nguoi_tiep_nhan_id bigint;
    v_nguoi_tiep_nhan text;
    v_seq bigint;
    v_ma_phieu text;
    v_items jsonb;
    v_item jsonb;
BEGIN
    -- 1. Extract admin info
    v_admin_id := (payload->>'admin_id')::bigint;
    SELECT username, ho_ten INTO v_admin_username, v_admin_ho_ten
    FROM nhan_vien WHERE id = v_admin_id;

    -- 2. created_at + validate
    v_created_at := COALESCE((payload->>'created_at')::timestamp with time zone, now());
    SELECT _admin_validate_request(v_admin_id, v_created_at) INTO v_validate;
    IF NOT (v_validate->>'ok')::boolean THEN
        RETURN v_validate;
    END IF;

    -- 3. NV tiếp nhận (có thể là chính admin hoặc NV khác)
    v_nguoi_tiep_nhan_id := (payload->>'nguoi_tiep_nhan_id')::bigint;
    SELECT ho_ten INTO v_nguoi_tiep_nhan FROM nhan_vien WHERE id = v_nguoi_tiep_nhan_id;
    IF v_nguoi_tiep_nhan IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'nguoi_tiep_nhan_id không tồn tại');
    END IF;

    -- 4. Generate ma_phieu
    v_seq := nextval('sc_seq');
    v_ma_phieu := 'SC' || LPAD(v_seq::text, 6, '0');

    -- 5. Insert header (KHÔNG đụng kho)
    v_chi_nhanh := payload->>'chi_nhanh';
    INSERT INTO phieu_sua_chua (
        ma_phieu, chi_nhanh, ten_khach, sdt_khach,
        loai_yeu_cau, hieu_dong_ho, dac_diem, mo_ta_loi,
        khach_tra_truoc, ghi_chu_noi_bo, trang_thai,
        nguoi_tiep_nhan, ngay_tiep_nhan, ngay_hen_tra,
        created_by, created_by_id,
        is_admin_created, admin_note,
        created_at
    ) VALUES (
        v_ma_phieu, v_chi_nhanh,
        payload->>'ten_khach', payload->>'sdt_khach',
        COALESCE(payload->>'loai_yeu_cau', 'Sửa chữa'),
        payload->>'hieu_dong_ho', payload->>'dac_diem', payload->>'mo_ta_loi',
        COALESCE((payload->>'khach_tra_truoc')::int, 0),
        payload->>'ghi_chu_noi_bo',
        COALESCE(payload->>'trang_thai', 'Đang sửa'),
        v_nguoi_tiep_nhan, v_created_at,
        NULLIF(payload->>'ngay_hen_tra','')::date,
        v_admin_username, v_admin_id,
        true, payload->>'admin_note',
        v_created_at
    );

    -- 6. Items (optional, chỉ ghi nhận giá — KHÔNG trừ kho)
    v_items := COALESCE(payload->'items', '[]'::jsonb);
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items)
    LOOP
        INSERT INTO phieu_sua_chua_chi_tiet (
            ma_phieu, ma_hang, ten_hang, so_luong, don_gia
        ) VALUES (
            v_ma_phieu,
            v_item->>'ma_hang',
            v_item->>'ten_hang',
            COALESCE((v_item->>'so_luong')::int, 1),
            COALESCE((v_item->>'don_gia')::int, 0)
        );
    END LOOP;

    -- 7. Audit
    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        v_admin_username, v_admin_ho_ten, v_chi_nhanh,
        'ADMIN_SC_CREATE',
        format('ma=%s nguoi_tiep_nhan=%s (id=%s) created_at=%s items=%s note=%s',
               v_ma_phieu, v_nguoi_tiep_nhan, v_nguoi_tiep_nhan_id,
               v_created_at, jsonb_array_length(v_items),
               COALESCE(payload->>'admin_note', '-')),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_phieu', v_ma_phieu,
        'created_at', v_created_at,
        'items_count', jsonb_array_length(v_items)
    );
END;
$$;
```

**Note:** Schema `phieu_sua_chua_chi_tiet` cần verify khi viết RPC (cột `ma_phieu, ma_hang, ten_hang, so_luong, don_gia` — Pre-flight đã thấy có table này dùng ở `sua_chua.py:163`). Nếu schema khác, adjust INSERT cho đúng.

### 3.5 Verify RPC

```sql
-- Test signature 3 RPC
SELECT routine_name, data_type AS returns
FROM information_schema.routines
WHERE routine_schema = 'public'
  AND routine_name IN (
      'tao_hoa_don_pos_admin',
      'tao_phieu_doi_tra_pos_admin',
      'tao_phieu_sua_chua_admin',
      '_admin_validate_request'
  );
-- Expected: 4 rows
```

---

## 4. PHASE 3 — PYTHON HELPER

### 4.1 Permission helper trong DLW_APP

**File:** `DLW_APP/utils/auth.py` (mới hoặc extend file existing)

```python
import streamlit as st

def is_admin(user: dict | None = None) -> bool:
    """Check if user is admin. Default: current session user."""
    if user is None:
        user = st.session_state.get("user")
    if not user:
        return False
    return user.get("role") == "admin"


def require_admin():
    """Show error + stop execution if current user is not admin."""
    if not is_admin():
        st.error("⛔ Tính năng này chỉ dành cho admin.")
        st.stop()
```

**Note cho Claude Code:** Đọc file login hiện tại của DLW_APP để xem session structure rồi adapt. Pattern trên giả định `st.session_state["user"]` là dict với key `"role"`.

### 4.2 Load all NV (kể cả inactive) — for dropdown

**File:** `DLW_APP/utils/db.py` (extend)

```python
def load_all_nhan_vien(include_inactive: bool = False) -> list[dict]:
    """Load all NV. include_inactive=True để admin chọn cả NV đã nghỉ."""
    query = supabase.table("nhan_vien").select("id, ho_ten, username, role, active")
    if not include_inactive:
        query = query.eq("active", True)
    res = query.order("ho_ten").execute()
    return res.data or []
```

---

## 5. PHASE 4 — UI ADMIN PANEL

### 5.1 Sidebar/Menu — chỉ hiện cho admin

**File:** `DLW_APP/main.py` hoặc `app.py` (entry point)

Tìm chỗ render sidebar. Thêm điều kiện:

```python
from utils.auth import is_admin

# Trong sidebar nav
if is_admin():
    st.sidebar.divider()
    st.sidebar.markdown("### 🛡 Admin")
    if st.sidebar.button("🛡 Admin POS", use_container_width=True):
        st.session_state["current_page"] = "admin_pos"
```

(Adapt với cấu trúc sidebar hiện tại sau khi Claude Code đọc code.)

### 5.2 File mới: `DLW_APP/modules/admin_pos.py`

**Cấu trúc:**

```python
"""Admin POS panel — tạo HĐ tự do với mọi tham số override."""

import streamlit as st
from datetime import datetime, date, time, timedelta
from utils.auth import require_admin
from utils.db import (
    load_all_nhan_vien,
    load_hang_hoa,        # for search items
    call_rpc,             # generic RPC caller
)

CHI_NHANH_LIST = ["100 Lê Quý Đôn", "Coop Vũng Tàu", "GO BÀ RỊA"]


def render():
    require_admin()
    
    st.title("🛡 Admin POS")
    st.warning("⚠️ Mọi HĐ tạo ở đây đánh dấu **is_admin_created=true** và ghi vào audit log.")
    
    tab1, tab2, tab3 = st.tabs([
        "🛒 Tạo HĐ POS",
        "🔄 Tạo phiếu đổi/trả",
        "🛠 Tạo phiếu sửa chữa"
    ])
    
    with tab1:
        render_tao_hd_pos()
    with tab2:
        render_tao_phieu_doi_tra()
    with tab3:
        render_tao_phieu_sua_chua()


def render_tao_hd_pos():
    """Sub-tab: Tạo HĐ POS admin."""
    
    # === 1. Backdate ===
    col1, col2 = st.columns(2)
    with col1:
        ngay = st.date_input(
            "Ngày HĐ",
            value=date.today(),
            min_value=date.today() - timedelta(days=90),
            max_value=date.today(),
            key="admin_hd_ngay"
        )
    with col2:
        gio = st.time_input(
            "Giờ HĐ",
            value=datetime.now().time(),
            key="admin_hd_gio"
        )
    created_at = datetime.combine(ngay, gio).isoformat()
    
    # === 2. NV bán ===
    nv_list = load_all_nhan_vien(include_inactive=True)
    nv_options = {
        f"{nv['ho_ten']} ({'active' if nv['active'] else 'NGHỈ'})": nv
        for nv in nv_list
    }
    nv_label = st.selectbox(
        "Người bán",
        options=list(nv_options.keys()),
        key="admin_hd_nv"
    )
    nv_chosen = nv_options[nv_label]
    
    # === 3. Chi nhánh ===
    chi_nhanh = st.selectbox(
        "Chi nhánh",
        options=CHI_NHANH_LIST,
        key="admin_hd_cn"
    )
    
    # === 4. Khách hàng (optional) ===
    col_kh1, col_kh2 = st.columns(2)
    with col_kh1:
        ten_khach = st.text_input("Tên khách (optional)", key="admin_hd_kh_ten")
    with col_kh2:
        sdt_khach = st.text_input("SĐT khách (optional)", key="admin_hd_kh_sdt")
    
    # === 5. Items cart ===
    st.markdown("---")
    st.markdown("**Items**")
    
    if "admin_hd_cart" not in st.session_state:
        st.session_state["admin_hd_cart"] = []
    cart = st.session_state["admin_hd_cart"]
    
    # Search + add UI
    search = st.text_input("Tìm hàng hóa/dịch vụ", key="admin_hd_search")
    if search and len(search) >= 2:
        results = load_hang_hoa(search=search, limit=10)
        for hh in results:
            if st.button(
                f"➕ {hh['ma_hang']} — {hh['ten_hang']} (mặc định {fmt_vnd(hh['gia_ban'])})",
                key=f"admin_hd_add_{hh['ma_hang']}",
                use_container_width=True
            ):
                cart.append({
                    "ma_hang": hh["ma_hang"],
                    "ten_hang": hh["ten_hang"],
                    "so_luong": 1,
                    "don_gia": int(hh.get("gia_ban", 0)),  # default, admin có thể sửa
                    "is_open_price": bool(hh.get("is_open_price", False)),
                    "loai_sp": hh.get("loai_sp", "Hàng hóa"),
                })
                st.rerun()
    
    # Display cart with editable đơn giá CHO MỌI ITEM (admin override)
    for i, line in enumerate(cart):
        col_info, col_sl, col_dg, col_x = st.columns([4, 1.5, 2, 0.5])
        with col_info:
            badge = "✏️" if line["is_open_price"] else "💰"
            st.markdown(f"{badge} **{line['ten_hang']}** ({line['ma_hang']})")
        with col_sl:
            line["so_luong"] = st.number_input(
                "SL", min_value=1, value=line["so_luong"],
                key=f"admin_hd_sl_{i}", label_visibility="collapsed"
            )
        with col_dg:
            line["don_gia"] = st.number_input(
                "Đơn giá", min_value=0, value=line["don_gia"], step=10000,
                key=f"admin_hd_dg_{i}", label_visibility="collapsed"
            )
        with col_x:
            if st.button("✕", key=f"admin_hd_del_{i}"):
                cart.pop(i)
                st.rerun()
    
    if cart:
        tong_tien = sum(l["so_luong"] * l["don_gia"] for l in cart)
        st.markdown(f"**Tổng tiền:** {fmt_vnd(tong_tien)}")
    else:
        tong_tien = 0
        st.caption("Chưa có item nào")
    
    # === 6. PTTT ===
    st.markdown("---")
    col_pt1, col_pt2, col_pt3 = st.columns(3)
    with col_pt1:
        tien_mat = st.number_input("Tiền mặt", min_value=0, value=tong_tien, step=10000, 
                                    key="admin_hd_tm")
    with col_pt2:
        chuyen_khoan = st.number_input("Chuyển khoản", min_value=0, value=0, step=10000,
                                        key="admin_hd_ck")
    with col_pt3:
        the = st.number_input("Thẻ", min_value=0, value=0, step=10000,
                              key="admin_hd_the")
    
    # === 7. Admin note ===
    admin_note = st.text_area(
        "Lý do tạo HĐ admin (optional)",
        placeholder="vd: Bù đơn ngày 2026-04-15 NV quên ghi",
        key="admin_hd_note"
    )
    
    # === 8. Submit với confirmation ===
    st.markdown("---")
    if cart:
        with st.expander("⚠️ Xác nhận tạo HĐ admin", expanded=False):
            st.write(f"- **Ngày:** {created_at}")
            st.write(f"- **Người bán:** {nv_chosen['ho_ten']} (id={nv_chosen['id']})")
            st.write(f"- **Chi nhánh:** {chi_nhanh}")
            st.write(f"- **Tổng tiền:** {fmt_vnd(tong_tien)}")
            st.write(f"- **Số items:** {len(cart)}")
            
            confirm_text = st.text_input(
                "Gõ **XÁC NHẬN** để submit:",
                key="admin_hd_confirm"
            )
            
            disabled = confirm_text.strip().upper() != "XÁC NHẬN"
            if st.button("🛡 Tạo HĐ Admin", disabled=disabled, type="primary",
                         key="admin_hd_submit"):
                # Build payload
                payload = {
                    "admin_id": st.session_state["user"]["id"],
                    "created_at": created_at,
                    "nguoi_ban_id": nv_chosen["id"],
                    "chi_nhanh": chi_nhanh,
                    "ten_khach": ten_khach or None,
                    "sdt_khach": sdt_khach or None,
                    "tien_mat": tien_mat,
                    "chuyen_khoan": chuyen_khoan,
                    "the": the,
                    "ghi_chu": "",
                    "admin_note": admin_note or None,
                    "items": cart,
                }
                result = call_rpc("tao_hoa_don_pos_admin", {"payload": payload})
                
                if result.get("ok"):
                    st.success(f"✅ Đã tạo {result['ma_hd']} (tổng {fmt_vnd(result['tong_tien'])})")
                    st.session_state["admin_hd_cart"] = []  # reset
                    st.rerun()
                else:
                    st.error(f"❌ {result.get('error', 'Unknown error')}")
```

(Sub-tab `render_tao_phieu_doi_tra` và `render_tao_phieu_sua_chua` tương tự — Claude Code adapt khi build.)

### 5.3 Visual marker — badge "🛡 ADMIN"

**File:** `DLW_APP/modules/bao_cao.py` hoặc bất kỳ chỗ nào display chi tiết HĐ.

```python
def display_hd_admin_badge(hd: dict):
    """Hiển thị badge nếu HĐ được tạo bởi admin."""
    if hd.get("is_admin_created"):
        st.markdown("🛡 **HĐ Admin**")
        if hd.get("admin_note"):
            st.caption(f"📝 Lý do: {hd['admin_note']}")
```

Gọi function này ở mọi chỗ render chi tiết HĐ POS / phiếu đổi/trả / phiếu sửa chữa.

---

## 6. PHASE 5 — BÁO CÁO TOGGLE

**File:** `DLW_APP/modules/bao_cao.py`

Tìm các hàm load HĐ trong báo cáo. Thêm filter:

```python
# Trong tab Doanh thu hoặc tương đương
include_admin = st.checkbox(
    "Bao gồm HĐ admin",
    value=True,
    help="HĐ admin = HĐ tạo bởi admin với tham số tự do (backdate, custom giá, v.v.). Tắt để xem doanh thu 'normal' không tính HĐ admin."
)

# Khi load HĐ:
if not include_admin and "is_admin_created" in df.columns:
    df = df[~df["is_admin_created"].fillna(False)]
```

Áp dụng cho: tab Doanh thu, tab Bán hàng theo nhóm, tab APSC (sửa chữa).

---

## 7. PHASE 6 — TEST PLAN

### 7.1 Test scenarios

```
Permission
[ ] Login admin (Đăng Khoa) → thấy menu "🛡 Admin POS"
[ ] Login NV không phải admin (vd Khánh Thư) → KHÔNG thấy menu
[ ] Truy cập trực tiếp URL admin_pos khi không phải admin → block + error message

Tạo HĐ POS Admin
[ ] Backdate 30 ngày → submit OK
[ ] Backdate 100 ngày → BLOCK ngay UI (date_input min_value)
[ ] Future date → BLOCK ngay UI (date_input max_value)
[ ] Chọn NV đã nghỉ (vd active=false) → submit OK, store đúng id
[ ] Chọn hàng thường (có tồn) → input đơn giá EDITABLE → custom 999000 → submit OK
[ ] Chọn hàng thường nhưng kho không đủ → BLOCK với error rõ ràng
[ ] Chọn open-price (SPK/DVPS) → submit OK, kho không bị trừ
[ ] Type sai "XÁC NHẬN" (vd "xacnhan") → button submit DISABLED
[ ] Type đúng "XÁC NHẬN" → button submit ENABLED → click → success

Verify sau tạo
[ ] hoa_don_pos có row mới với is_admin_created=true, admin_note đúng
[ ] hoa_don_pos_ct có items với don_gia custom (không phải gia_ban gốc)
[ ] the_kho đã trừ kho cho hàng thường (kiểm chi nhánh đúng)
[ ] action_logs có row ADMIN_HD_CREATE với detail đầy đủ, level='warn'
[ ] Mở chi tiết HĐ trong báo cáo → thấy badge "🛡 ADMIN" + admin_note

Tab Đổi/trả admin
[ ] Tương tự test cases nhưng phải có ma_hd_goc
[ ] Bypass check 7 ngày (admin override): ma_hd_goc 30 ngày trước → submit OK

Tab Sửa chữa admin
[ ] Tạo phiếu sửa chữa admin (header only) → submit OK
[ ] phieu_sua_chua có created_by_id = admin id

Báo cáo
[ ] Tab Doanh thu: toggle "Bao gồm HĐ admin" = ON → tổng include HĐ admin
[ ] Toggle = OFF → tổng KHÔNG include HĐ admin
[ ] APSC tab: toggle hoạt động tương tự
```

### 7.2 Acceptance criteria

- ✅ Toàn bộ scenarios pass
- ✅ KHÔNG có data corruption (kho consistent, sequence không vỡ)
- ✅ Audit log đầy đủ — mỗi HĐ admin có 1 row trong action_logs
- ✅ NV non-admin không có cách nào access feature này

---

## 8. PHASE 7 — ROLLBACK

### 8.1 Rollback toàn phần

```sql
BEGIN;

-- Drop RPCs
DROP FUNCTION IF EXISTS tao_hoa_don_pos_admin(jsonb);
DROP FUNCTION IF EXISTS tao_phieu_doi_tra_pos_admin(jsonb);
DROP FUNCTION IF EXISTS tao_phieu_sua_chua_admin(jsonb);
DROP FUNCTION IF EXISTS _admin_validate_request(bigint, timestamp with time zone);

-- Drop columns (cẩn thận: data is_admin_created bị mất)
ALTER TABLE hoa_don_pos DROP COLUMN IF EXISTS is_admin_created, DROP COLUMN IF EXISTS admin_note;
ALTER TABLE phieu_doi_tra_pos DROP COLUMN IF EXISTS is_admin_created, DROP COLUMN IF EXISTS admin_note;
ALTER TABLE phieu_sua_chua DROP COLUMN IF EXISTS is_admin_created, DROP COLUMN IF EXISTS admin_note, DROP COLUMN IF EXISTS created_by_id;

-- Drop indexes (auto drop khi drop column)

COMMIT;
```

### 8.2 Code revert

Git revert PR DLW_APP. Streamlit Cloud auto-redeploy.

### 8.3 Restore từ backup nếu data hỏng

```sql
-- Restore hoa_don_pos
TRUNCATE hoa_don_pos CASCADE;
INSERT INTO hoa_don_pos SELECT * FROM _backup_admin_b1_20260508_hoa_don_pos;
-- Tương tự cho phieu_doi_tra_pos, phieu_sua_chua

-- the_kho không backup được vì có thể ngoài Phase B1 đã thay đổi
-- → recompute lại nếu cần
```

---

## 9. POST-DEPLOY

### 9.1 Verify 1 tuần thực tế

- Theo dõi `action_logs WHERE action LIKE 'ADMIN_%'` mỗi ngày
- Check báo cáo doanh thu có hợp lý không
- Nếu phát hiện bug → fix incremental, không rollback

### 9.2 Sau 1 tuần ổn → Phase B2

Phase B2 sẽ build feature **Sửa HĐ existing**:
- 3 RPC: `sua_hoa_don_pos_admin`, `sua_phieu_doi_tra_pos_admin`, `sua_phieu_sua_chua_admin`
- Snapshot full trước/sau (JSONB column hoặc table riêng)
- LOCK fields: ma_hd, trang_thai, nguoi_tao
- Đảo kho atomic khi sửa items

→ Plan riêng `PLAN_ADMIN_B2.md`.

---

## 10. CONSTRAINTS & NOTES

### 10.1 PHẢI tuân thủ

- ✅ Permission check `role='admin'` ở RPC server-side (không tin client)
- ✅ Audit log MỌI HĐ admin tạo
- ✅ Trừ kho thật như HĐ normal (nếu Q12=a)
- ✅ Backdate hard limit 90 ngày (server-side validate)

### 10.2 Tránh

- ❌ KHÔNG cho admin override sequence (giữ AHD000XXX liên tục)
- ❌ KHÔNG bypass FK constraint (nguoi_ban_id phải tồn tại trong nhan_vien)
- ❌ KHÔNG bỏ qua audit log dù admin báo "test thôi"
- ❌ KHÔNG cho non-admin truy cập feature qua bất kỳ cách nào

### 10.3 File cần edit

| File | Repo | Lý do |
|---|---|---|
| `utils/auth.py` | DLW_APP | Permission helper (mới hoặc extend) |
| `utils/db.py` | DLW_APP | `load_all_nhan_vien`, `call_rpc` (extend) |
| `modules/admin_pos.py` | DLW_APP | UI panel (FILE MỚI) |
| `modules/bao_cao.py` | DLW_APP | Toggle "Bao gồm HĐ admin", badge |
| `modules/sua_chua.py` | DLW_APP | Sửa `_gen_ma_phieu` dùng `nextval('sc_seq')` qua RPC `next_sc_seq` |
| `app.py` | DLW_APP | Sidebar menu admin (đã có pattern `is_admin()` ở line 228-229) |

KHÔNG cần edit:
- `dl-watch-pos` repo (POS không đụng trong B1)
- `pos_app/utils/db.py`, `pos_app/modules/*.py`

### 10.4 Time budget

| Phase | Time |
|---|---|
| Pre-flight (verify code + backup) | 30 phút |
| Phase 1 schema | 15 phút |
| Phase 2 RPC × 3 | 1.5-2 giờ (RPC #1 lâu nhất, 2-3 sao chép pattern) |
| Phase 3 Python helper | 15 phút |
| Phase 4 UI × 3 sub-tabs | 1.5-2 giờ |
| Phase 5 báo cáo toggle | 20 phút |
| Phase 6 test | 1 giờ |
| **TỔNG** | **~5 giờ** |

Chia 2 buổi 2.5h hoặc 1 buổi 5h tùy schedule.

---

## 11. CHECKLIST THỰC HIỆN

```
PRE-FLIGHT
[x] Backup 4 bảng (hoa_don_pos, phieu_doi_tra_pos, phieu_sua_chua, action_logs)
[x] Claude Code đọc code DLW_APP để verify auth flow + UI pattern (is_admin đã có sẵn)
[x] Verify sequences (ahd_seq ✓, ahdd_seq ✓, sc_seq ❌ → tạo Phase 1)

PHASE 1 — Schema
[ ] ALTER TABLE 3 bảng: is_admin_created + admin_note
[ ] ALTER TABLE phieu_sua_chua: thêm created_by_id
[ ] CREATE 3 partial indexes
[ ] CREATE SEQUENCE sc_seq START WITH (max+1)
[ ] CREATE FUNCTION next_sc_seq() wrapper
[ ] Sửa modules/sua_chua.py:_gen_ma_phieu dùng RPC next_sc_seq
[ ] Verify schema bằng SQL query

PHASE 2 — RPC
[ ] Helper _admin_validate_request
[ ] tao_hoa_don_pos_admin
[ ] tao_phieu_doi_tra_pos_admin  
[ ] tao_phieu_sua_chua_admin
[ ] Test 1 lần mỗi RPC bằng SELECT thẳng

PHASE 3 — Python helper
[ ] utils/auth.py: is_admin(), require_admin()
[ ] utils/db.py: load_all_nhan_vien(), call_rpc() (nếu chưa có)

PHASE 4 — UI
[ ] modules/admin_pos.py: 3 sub-tabs với form đầy đủ
[ ] main.py: sidebar menu (chỉ hiện cho admin)
[ ] Confirmation pattern (type "XÁC NHẬN")
[ ] Visual badge "🛡 ADMIN" reusable function

PHASE 5 — Báo cáo
[ ] modules/bao_cao.py: toggle "Bao gồm HĐ admin"
[ ] Apply filter cho tab Doanh thu, Bán hàng theo nhóm, APSC

PHASE 6 — Test (manual)
[ ] Permission tests (admin vs non-admin)
[ ] Tạo HĐ POS admin: 10+ scenarios
[ ] Tạo phiếu đổi/trả admin
[ ] Tạo phiếu sửa chữa admin
[ ] Báo cáo toggle hoạt động
[ ] Audit log đầy đủ

DEPLOY
[ ] Merge PR DLW_APP vào main
[ ] Streamlit Cloud redeploy
[ ] Smoke test trên app live
[ ] Theo dõi action_logs 1 tuần

POST
[ ] Cleanup _backup_admin_b1_* sau 1 tuần ổn
[ ] Document feature trong README/internal docs
[ ] Sau 1 tuần → bắt đầu plan PLAN_ADMIN_B2.md (sửa HĐ)
```

---

**END OF PLAN_ADMIN_B1.md**

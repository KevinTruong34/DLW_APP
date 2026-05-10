-- ============================================================
-- RPC huy_hoa_don_apsc — hủy HĐ APSC + đảo kho atomic
-- Plan: PLAN_APSC_K80_AND_CANCEL.md §3.1 (Phase 2)
--
-- Logic:
--   1. Validate (prefix APSC, cancelled_by không rỗng)
--   2. Lookup + lock row đầu (FOR UPDATE), reject nếu không tồn tại / đã hủy
--   3. Đảo kho: với mỗi row có "Mã hàng", += "Số lượng" vào the_kho
--      Skip rules MIRROR tru_kho_apsc (đảm bảo symmetry):
--        - Skip nếu "Mã hàng" không có trong hang_hoa (synthetic services)
--        - Skip nếu is_hang_hoa_co_kho() = false (loại sp != Hàng hóa hoặc open-price)
--      KHÔNG INSERT row mới vào the_kho (tránh phantom stock — nếu the_kho
--      không có row thì tru_kho_apsc cũng không deduct được).
--   4. Set "Trạng thái" = 'Đã hủy' + "Ngày cập nhật" cho TẤT CẢ rows của HĐ
--   5. Audit log ADMIN_APSC_CANCEL vào action_logs (level=warn)
--
-- Caller: Python wrapper call_huy_hoa_don_apsc (utils/print_queue_apsc.py)
-- ============================================================

CREATE OR REPLACE FUNCTION huy_hoa_don_apsc(
    p_ma_hd        text,
    p_cancelled_by text
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_chi_nhanh    text;
    v_trang_thai   text;
    v_item         RECORD;
    v_count_items  int := 0;
    v_count_kho    int := 0;
    v_total_units  int := 0;
BEGIN
    -- 1. Validate
    IF p_ma_hd IS NULL OR p_ma_hd = '' OR LEFT(p_ma_hd, 4) <> 'APSC' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Mã HĐ APSC không hợp lệ');
    END IF;
    IF p_cancelled_by IS NULL OR p_cancelled_by = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu cancelled_by');
    END IF;

    -- 2. Lookup + lock row đầu
    SELECT "Chi nhánh", "Trạng thái"
      INTO v_chi_nhanh, v_trang_thai
    FROM hoa_don
    WHERE "Mã hóa đơn" = p_ma_hd
    LIMIT 1
    FOR UPDATE;

    IF v_chi_nhanh IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'HĐ không tồn tại');
    END IF;
    IF v_trang_thai = 'Đã hủy' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'HĐ đã bị hủy trước đó');
    END IF;

    -- 3. Đảo kho atomic — mirror skip rules tru_kho_apsc
    FOR v_item IN
        SELECT "Mã hàng" AS ma_hang,
               COALESCE("Số lượng", 0)::int AS sl
          FROM hoa_don
         WHERE "Mã hóa đơn" = p_ma_hd
           AND COALESCE("Mã hàng", '') <> ''
    LOOP
        v_count_items := v_count_items + 1;

        IF v_item.sl > 0
           AND EXISTS (SELECT 1 FROM hang_hoa hh WHERE hh.ma_hang = v_item.ma_hang)
           AND is_hang_hoa_co_kho(v_item.ma_hang)
        THEN
            UPDATE the_kho
               SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + v_item.sl
             WHERE "Mã hàng"  = v_item.ma_hang
               AND "Chi nhánh" = v_chi_nhanh;

            IF FOUND THEN
                v_count_kho   := v_count_kho + 1;
                v_total_units := v_total_units + v_item.sl;
            END IF;
        END IF;
    END LOOP;

    -- 4. Set trạng thái = 'Đã hủy' cho TẤT CẢ rows của HĐ
    UPDATE hoa_don
       SET "Trạng thái"    = 'Đã hủy',
           "Ngày cập nhật" = to_char(now() AT TIME ZONE 'Asia/Ho_Chi_Minh',
                                     'YYYY-MM-DD HH24:MI:SS')
     WHERE "Mã hóa đơn" = p_ma_hd;

    -- 5. Audit log
    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        p_cancelled_by,
        p_cancelled_by,
        v_chi_nhanh,
        'ADMIN_APSC_CANCEL',
        format('ma=%s items=%s kho_restored=%s units=%s',
               p_ma_hd, v_count_items, v_count_kho, v_total_units),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok',             true,
        'ma_hd',          p_ma_hd,
        'items_count',    v_count_items,
        'kho_restored',   v_count_kho,
        'units_restored', v_total_units
    );
END;
$$;

COMMENT ON FUNCTION huy_hoa_don_apsc(text, text) IS
'Hủy HĐ APSC: set "Trạng thái"=''Đã hủy'' + đảo kho atomic (chỉ cho item có '
'trong hang_hoa AND is_hang_hoa_co_kho — mirror skip rules của tru_kho_apsc). '
'Audit log ADMIN_APSC_CANCEL vào action_logs.';

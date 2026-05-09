-- ============================================================
-- Fix #3a: RPC tru_kho_apsc — atomic stock deduction cho APSC
-- Applied: 2026-05-09 via Supabase MCP migration `tru_kho_apsc_rpc`
--
-- Bug: khi convert phiếu sửa chữa → HĐ APSC (Python `_tao_hoa_don_apsc`
-- insert vào hoa_don legacy table), linh kiện thật KHÔNG được trừ kho
-- → kho hiển thị nhiều hơn thực tế.
-- Plan B2b §0.3 viết "APSC trừ kho" — implementation gap.
--
-- Fix step 1 (this migration): RPC atomic pre-validate + deduct.
-- Fix step 2: Python `_tao_hoa_don_apsc` gọi RPC sau khi INSERT thành công.
-- Fix step 3 (separate PR): restore historical 4 units cho 3 SKUs.
--
-- Skip rules (silently — không phải lỗi):
--   - Item missing trong hang_hoa (synthetic services như DVPS, LD300)
--   - Item is_open_price = true (vd SPK, DVPS — luôn open price)
--   - Item loai_sp != 'Hàng hóa' (services)
-- Chỉ trừ kho item thực có trong hang_hoa với loai_sp='Hàng hóa' AND NOT open_price.
-- ============================================================

CREATE OR REPLACE FUNCTION tru_kho_apsc(
    p_ma_hd      text,
    p_chi_nhanh  text,
    p_items      jsonb,
    p_nguoi_ban  text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_item RECORD;
    v_ma_hang text;
    v_so_luong int;
    v_ton_hien_tai int;
    v_total_deducted int := 0;
    v_skus_deducted int := 0;
    v_log_detail text := '';
BEGIN
    IF p_ma_hd IS NULL OR p_ma_hd = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu ma_hd');
    END IF;
    IF p_chi_nhanh IS NULL OR p_chi_nhanh = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu chi_nhanh');
    END IF;
    IF p_items IS NULL OR jsonb_array_length(p_items) = 0 THEN
        RETURN jsonb_build_object('ok', true, 'ma_hd', p_ma_hd,
                                   'message', 'Phiếu không có items',
                                   'items_deducted', 0);
    END IF;

    -- Pre-validate: gom items theo ma_hang, check stock
    FOR v_item IN
        WITH items AS (
            SELECT (it->>'ma_hang') AS ma_hang,
                   SUM((it->>'so_luong')::int)::int AS sl_total
            FROM jsonb_array_elements(p_items) it
            WHERE COALESCE(it->>'ma_hang', '') != ''
            GROUP BY (it->>'ma_hang')
        )
        SELECT i.ma_hang, i.sl_total
        FROM items i
        WHERE EXISTS (SELECT 1 FROM hang_hoa hh WHERE hh.ma_hang = i.ma_hang)
          AND is_hang_hoa_co_kho(i.ma_hang)
    LOOP
        v_ma_hang := v_item.ma_hang;
        v_so_luong := v_item.sl_total;

        SELECT COALESCE(SUM("Tồn cuối kì"), 0)::int INTO v_ton_hien_tai
        FROM the_kho
        WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = p_chi_nhanh;

        IF v_ton_hien_tai < v_so_luong THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Item %s không đủ tồn (có %s, cần %s) tại %s',
                    v_ma_hang, v_ton_hien_tai, v_so_luong, p_chi_nhanh));
        END IF;
    END LOOP;

    -- Trừ kho atomic
    FOR v_item IN
        WITH items AS (
            SELECT (it->>'ma_hang') AS ma_hang,
                   SUM((it->>'so_luong')::int)::int AS sl_total
            FROM jsonb_array_elements(p_items) it
            WHERE COALESCE(it->>'ma_hang', '') != ''
            GROUP BY (it->>'ma_hang')
        )
        SELECT i.ma_hang, i.sl_total
        FROM items i
        WHERE EXISTS (SELECT 1 FROM hang_hoa hh WHERE hh.ma_hang = i.ma_hang)
          AND is_hang_hoa_co_kho(i.ma_hang)
    LOOP
        v_ma_hang := v_item.ma_hang;
        v_so_luong := v_item.sl_total;

        UPDATE the_kho
        SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) - v_so_luong
        WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = p_chi_nhanh;

        v_total_deducted := v_total_deducted + v_so_luong;
        v_skus_deducted := v_skus_deducted + 1;
        v_log_detail := v_log_detail || format(' %s=%s', v_ma_hang, v_so_luong);
    END LOOP;

    IF v_skus_deducted > 0 THEN
        INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
        VALUES (
            COALESCE(p_nguoi_ban, 'unknown'),
            COALESCE(p_nguoi_ban, 'unknown'),
            p_chi_nhanh,
            'SC_HOA_DON_KHO_DEDUCTED',
            format('ma=%s items=[%s] total=%s', p_ma_hd, trim(v_log_detail), v_total_deducted),
            'info'
        );
    END IF;

    RETURN jsonb_build_object(
        'ok', true,
        'ma_hd', p_ma_hd,
        'skus_deducted', v_skus_deducted,
        'total_units', v_total_deducted
    );
END;
$$;

COMMENT ON FUNCTION tru_kho_apsc(text, text, jsonb, text) IS
'Trừ kho atomic cho HĐ APSC (sửa chữa convert). Skip items không có trong hang_hoa, '
'không phải Hàng hóa, hoặc open-price. Caller (Python _tao_hoa_don_apsc) gọi sau '
'INSERT hoa_don rows.';

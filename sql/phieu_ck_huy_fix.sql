-- ============================================================
-- Fix: Hủy phiếu chuyển kho phải đảo kho khi 'Đang chuyển'
-- Applied: 2026-05-09 via Supabase MCP migration `phieu_ck_huy_fix_schema_rpc`
--
-- Bug: modules/chuyen_hang.py cancel action chỉ UPDATE trang_thai='Đã hủy'
--   KHÔNG đảo kho. Phiếu ở 'Đang chuyển' đã trừ kho CN nguồn (qua
--   xac_nhan_chuyen_hang) → khi hủy, kho không được cộng lại → mất kho ảo.
--
-- Fix:
--   1) ALTER phieu_chuyen_kho: thêm cancelled_by + cancelled_at
--   2) RPC huy_phieu_chuyen_kho(p_ma_phieu, p_huy_boi) atomic:
--      - Reject nếu đã 'Đã hủy' / 'Đã nhận'
--      - Nếu 'Đang chuyển' → CỘNG kho lại CN nguồn cho mỗi item
--      - Nếu 'Phiếu tạm' → KHÔNG đụng kho (chưa trừ)
--      - UPDATE all rows: trang_thai + cancelled_by + cancelled_at
--      - Audit log via action_logs (action='PHIEU_CK_CANCEL', level='warn')
-- ============================================================

ALTER TABLE phieu_chuyen_kho
    ADD COLUMN IF NOT EXISTS cancelled_by TEXT,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

CREATE OR REPLACE FUNCTION huy_phieu_chuyen_kho(
    p_ma_phieu text,
    p_huy_boi  text
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_tu_cn text;
    v_toi_cn text;
    v_trang_thai text;
    v_item RECORD;
    v_count int := 0;
BEGIN
    IF p_ma_phieu IS NULL OR p_ma_phieu = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu ma_phieu');
    END IF;

    SELECT tu_chi_nhanh, toi_chi_nhanh, trang_thai
    INTO v_tu_cn, v_toi_cn, v_trang_thai
    FROM phieu_chuyen_kho
    WHERE ma_phieu = p_ma_phieu
    ORDER BY id LIMIT 1
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Phiếu không tồn tại');
    END IF;

    IF v_trang_thai = 'Đã hủy' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Phiếu đã hủy trước đó');
    END IF;

    IF v_trang_thai = 'Đã nhận' THEN
        RETURN jsonb_build_object('ok', false,
            'error', 'Phiếu đã nhận, không hủy được. Cần tạo phiếu chuyển ngược.');
    END IF;

    IF v_trang_thai = 'Đang chuyển' THEN
        FOR v_item IN
            SELECT ma_hang, so_luong_chuyen
            FROM phieu_chuyen_kho
            WHERE ma_phieu = p_ma_phieu
        LOOP
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + v_item.so_luong_chuyen
            WHERE "Mã hàng" = v_item.ma_hang
              AND "Chi nhánh" = v_tu_cn;
            v_count := v_count + 1;
        END LOOP;
    END IF;

    UPDATE phieu_chuyen_kho
    SET trang_thai = 'Đã hủy',
        cancelled_by = p_huy_boi,
        cancelled_at = now()
    WHERE ma_phieu = p_ma_phieu;

    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        COALESCE(p_huy_boi, 'unknown'),
        COALESCE(p_huy_boi, 'unknown'),
        v_tu_cn,
        'PHIEU_CK_CANCEL',
        format('ma=%s tu=%s toi=%s prev_status=%s items_restored=%s',
               p_ma_phieu, v_tu_cn, v_toi_cn, v_trang_thai, v_count),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_phieu', p_ma_phieu,
        'prev_status', v_trang_thai,
        'items_restored', v_count,
        'tu_chi_nhanh', v_tu_cn
    );
END;
$$;

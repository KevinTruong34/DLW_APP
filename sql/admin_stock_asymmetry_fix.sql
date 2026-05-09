-- ============================================================
-- Fix BUG #2: Stock asymmetry trong 4 admin RPCs
-- Applied: 2026-05-09 via Supabase MCP migration `admin_stock_asymmetry_fix`
--
-- Trước: condition kho không nhất quán giữa tao/sua admin và huy:
--   - tao_hoa_don_pos_admin / sua_hoa_don_pos_admin: chỉ check `NOT is_open_price`
--     (thiếu loai_sp='Hàng hóa') → trừ kho cho item dịch vụ/linh kiện sai
--   - tao_phieu_doi_tra_pos_admin / sua_phieu_doi_tra_pos_admin: chỉ check
--     `loai_sp='Hàng hóa'` (thiếu NOT is_open_price) → cộng/trừ kho open-price sai
--   - huy_* RPCs check đầy đủ `loai_sp='Hàng hóa' AND NOT is_open_price` → asymmetry
-- Sau: helper `is_hang_hoa_co_kho` thống nhất ở 4 admin RPCs, match pattern
--   của NV/huy. Tránh kho lệch khi hủy/sửa.
--
-- Audit production trước khi deploy: 0 transactions hit combo bug → no data fix needed.
-- ============================================================

CREATE OR REPLACE FUNCTION is_hang_hoa_co_kho(p_ma_hang text)
RETURNS boolean
LANGUAGE plpgsql STABLE
AS $func$
DECLARE
    v_loai_sp text;
BEGIN
    SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
    FROM hang_hoa WHERE ma_hang = p_ma_hang;
    v_loai_sp := COALESCE(v_loai_sp, 'Hàng hóa');
    RETURN v_loai_sp = 'Hàng hóa' AND NOT is_open_price_sql(p_ma_hang);
END;
$func$;

COMMENT ON FUNCTION is_hang_hoa_co_kho(text) IS
'Returns true nếu mã hàng có quản lý kho thật (loai_sp=Hàng hóa AND NOT is_open_price). '
'Dùng để symmetric trừ/cộng kho ở các RPC.';

-- 4 admin RPCs đã được CREATE OR REPLACE in-place qua DO blocks
-- (replace `NOT is_open_price_sql` / `v_loai_sp = 'Hàng hóa'` / `COALESCE(...)`
-- → `is_hang_hoa_co_kho(...)`).
-- Xem migration `admin_stock_asymmetry_fix` trong Supabase migrations để
-- xem source phiên bản đã deploy.

-- Verify (post-deploy):
--   tao_hoa_don_pos_admin       : 2 calls is_hang_hoa_co_kho
--   sua_hoa_don_pos_admin       : 3 calls
--   tao_phieu_doi_tra_pos_admin : 3 calls
--   sua_phieu_doi_tra_pos_admin : 3 calls
-- Total: 11 stock-condition calls thống nhất via helper.

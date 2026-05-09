-- ============================================================
-- Audit restore: cộng lại 13 units cho 4 phiếu hủy buggy
-- Applied: 2026-05-09 via Supabase MCP migration `phieu_ck_audit_restore_20260509`
--
-- Context: trước khi fix RPC huy_phieu_chuyen_kho, code Python chỉ UPDATE
-- trang_thai='Đã hủy' mà KHÔNG đảo kho khi phiếu ở 'Đang chuyển'. 4 phiếu
-- (CH000011, CH000013, CH000019, CH000020) ngày 2026-05-09 bị mất kho 13 units
-- tại Coop Vũng Tàu.
--
-- Audit query (xem candidates trước restore):
--   SELECT ma_phieu, ma_hang, so_luong_chuyen FROM phieu_chuyen_kho
--   WHERE trang_thai='Đã hủy' AND loai_phieu='Chuyển hàng (App - đã đồng bộ)'
--     AND ngay_chuyen >= '2026-05-06' AND cancelled_by IS NULL;
-- ============================================================

UPDATE the_kho
SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + 2
WHERE "Mã hàng" = 'AE-1000W-3AVDF' AND "Chi nhánh" = 'Coop Vũng Tàu';

UPDATE the_kho
SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + 6
WHERE "Mã hàng" = 'F 200' AND "Chi nhánh" = 'Coop Vũng Tàu';

UPDATE the_kho
SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + 4
WHERE "Mã hàng" = 'F 201' AND "Chi nhánh" = 'Coop Vũng Tàu';

UPDATE the_kho
SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + 1
WHERE "Mã hàng" = 'KBDH20300' AND "Chi nhánh" = 'Coop Vũng Tàu';

UPDATE phieu_chuyen_kho
SET cancelled_by = 'audit_restore_20260509',
    cancelled_at = COALESCE(cancelled_at, now())
WHERE ma_phieu IN ('CH000011', 'CH000013', 'CH000019', 'CH000020');

INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
VALUES (
    'audit_restore', 'Audit restore', 'Coop Vũng Tàu',
    'PHIEU_CK_AUDIT_RESTORE',
    'Restore kho 13 units cho 4 phiếu hủy buggy (CH000011, CH000013, CH000019, CH000020) '
    'tại Coop Vũng Tàu. Breakdown: AE-1000W-3AVDF +2, F 200 +6, F 201 +4, KBDH20300 +1. '
    'Bug: trước fix huy_phieu_chuyen_kho RPC, hủy phiếu Đang chuyển không đảo kho.',
    'warn'
);

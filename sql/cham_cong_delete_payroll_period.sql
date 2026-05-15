-- ============================================================
-- Cham_cong addon: delete_payroll_period RPC (admin only)
--
-- Cho phép admin xóa kỳ lương vĩnh viễn — kể cả status='finalized'.
-- Cascade delete items + adjustments + period.
--
-- Validation:
-- - Admin role required (role='admin')
-- - Period must exist
--
-- Destructive op → audit level='warn' với snapshot full:
--   {period_id, label, status_was, range, items_deleted, adjustments_deleted}
--
-- Đã apply lên Supabase qua MCP: cham_cong_delete_payroll_period
--
-- Smoke test (PASS 3/3 + cascade verified):
-- 1. NV thường role='nhan_vien' → reject "Chỉ admin được xóa kỳ lương"
-- 2. period_id không tồn tại → reject "Kỳ lương không tồn tại"
-- 3. Admin xóa period finalized (2 items + 1 adj) → ok, all 3 tables cleaned
-- ============================================================

CREATE OR REPLACE FUNCTION delete_payroll_period(
    p_period_id BIGINT,
    p_admin_id INTEGER
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_period RECORD;
    v_admin_name TEXT;
    v_admin_role TEXT;
    v_items_count INT := 0;
    v_adj_count INT := 0;
BEGIN
    -- Validate admin (chỉ admin được xóa)
    SELECT ho_ten, role INTO v_admin_name, v_admin_role
      FROM nhan_vien WHERE id = p_admin_id;
    IF v_admin_name IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Admin không tồn tại');
    END IF;
    IF v_admin_role <> 'admin' THEN
        RETURN jsonb_build_object(
            'ok', false,
            'error', 'Chỉ admin được xóa kỳ lương (role hiện tại: ' || v_admin_role || ')'
        );
    END IF;

    -- Load period
    SELECT id, label, status, start_date, end_date INTO v_period
      FROM attendance_payroll_periods WHERE id = p_period_id;
    IF v_period.id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Kỳ lương không tồn tại');
    END IF;

    -- Count for audit
    SELECT count(*) INTO v_items_count
      FROM attendance_payroll_items WHERE period_id = p_period_id;
    SELECT count(*) INTO v_adj_count
      FROM attendance_adjustments WHERE period_id = p_period_id;

    -- Cascade delete (manual vì FK không có ON DELETE CASCADE)
    DELETE FROM attendance_payroll_items WHERE period_id = p_period_id;
    DELETE FROM attendance_adjustments WHERE period_id = p_period_id;
    DELETE FROM attendance_payroll_periods WHERE id = p_period_id;

    -- Audit warn (destructive — bao gồm cả status finalized)
    INSERT INTO action_logs (ho_ten, action, level, detail)
    VALUES (
        v_admin_name,
        'ATT_PAYROLL_DELETE', 'warn',
        json_build_object(
            'period_id', p_period_id,
            'label', v_period.label,
            'status_was', v_period.status,
            'range', json_build_object(
                'start', v_period.start_date,
                'end', v_period.end_date
            ),
            'items_deleted', v_items_count,
            'adjustments_deleted', v_adj_count
        )::text
    );

    RETURN jsonb_build_object(
        'ok', true,
        'period_id', p_period_id,
        'label', v_period.label,
        'status_was', v_period.status,
        'items_deleted', v_items_count,
        'adjustments_deleted', v_adj_count
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;

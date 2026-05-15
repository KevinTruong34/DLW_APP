-- ============================================================
-- Module Chấm công — Phase 8: RPC get_payroll_for_self
-- Refs: PLAN_CHAM_CONG.md section 13.3
--
-- POS app gọi để NV xem lương cá nhân — return period + items + adjustments + tổng.
--
-- Security model: client trust (cùng pattern các RPC khác trong codebase).
-- POS app auth gate đảm bảo NV chỉ pass nv_id của họ. RPC không enforce
-- caller=p_nhan_vien_id vì Supabase anon key + custom session table (không có
-- auth.uid() native context).
--
-- Đã apply lên Supabase qua MCP apply_migration: cham_cong_p8_get_payroll_for_self
--
-- Smoke test 3/3 PASS:
-- 1. get_payroll_for_self(nv_id, period_id) hợp lệ → ok với items/adjustments/totals
-- 2. period_id không tồn tại → error "Kỳ lương không tồn tại"
-- 3. nv_id không có data trong period → ok với arrays rỗng + totals 0
-- ============================================================

CREATE OR REPLACE FUNCTION get_payroll_for_self(
    p_nhan_vien_id INTEGER,
    p_period_id BIGINT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_period jsonb;
    v_items jsonb;
    v_adjustments jsonb;
    v_total_luong_ca BIGINT := 0;
    v_total_adj BIGINT := 0;
    v_total_worked_min BIGINT := 0;
    v_total_ot_min BIGINT := 0;
    v_total_leave_min BIGINT := 0;
BEGIN
    -- Load period info
    SELECT jsonb_build_object(
        'id', id,
        'label', label,
        'start_date', start_date,
        'end_date', end_date,
        'status', status,
        'finalized_at', finalized_at
    ) INTO v_period
      FROM attendance_payroll_periods
     WHERE id = p_period_id;

    IF v_period IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Kỳ lương không tồn tại');
    END IF;

    -- Items của NV này trong period (sort by work_date ASC, NULLs last)
    SELECT
        COALESCE(jsonb_agg(
            jsonb_build_object(
                'id', i.id,
                'work_date', i.work_date,
                'shift_label', st.label,
                'item_type', i.item_type,
                'worked_minutes', i.worked_minutes,
                'ot_minutes', i.ot_minutes,
                'rate_snapshot', i.rate_snapshot,
                'salary_amount', i.salary_amount
            )
            ORDER BY i.work_date NULLS LAST, i.id
        ), '[]'::jsonb),
        COALESCE(SUM(i.salary_amount), 0),
        COALESCE(SUM(CASE WHEN i.item_type = 'shift' THEN i.worked_minutes ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN i.item_type = 'shift' THEN i.ot_minutes ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN i.item_type = 'leave_paid' THEN i.worked_minutes ELSE 0 END), 0)
    INTO v_items, v_total_luong_ca, v_total_worked_min, v_total_ot_min, v_total_leave_min
      FROM attendance_payroll_items i
      LEFT JOIN shift_templates st ON st.id = i.shift_template_id
     WHERE i.period_id = p_period_id
       AND i.nhan_vien_id = p_nhan_vien_id;

    -- Adjustments của NV này trong period
    SELECT
        COALESCE(jsonb_agg(
            jsonb_build_object(
                'id', a.id,
                'adjustment_type', a.adjustment_type,
                'amount', a.amount,
                'note', a.note,
                'created_at', a.created_at
            )
            ORDER BY a.created_at DESC
        ), '[]'::jsonb),
        COALESCE(SUM(a.amount), 0)
    INTO v_adjustments, v_total_adj
      FROM attendance_adjustments a
     WHERE a.period_id = p_period_id
       AND a.nhan_vien_id = p_nhan_vien_id;

    RETURN jsonb_build_object(
        'ok', true,
        'period', v_period,
        'items', v_items,
        'adjustments', v_adjustments,
        'totals', jsonb_build_object(
            'worked_minutes', v_total_worked_min,
            'ot_minutes', v_total_ot_min,
            'leave_minutes', v_total_leave_min,
            'luong_ca', v_total_luong_ca,
            'adjustments', v_total_adj,
            'tong_cong', v_total_luong_ca + v_total_adj
        )
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;

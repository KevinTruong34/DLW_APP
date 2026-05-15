-- ============================================================
-- Module Chấm công — Phase 6 Payroll RPCs
-- Refs: PLAN_CHAM_CONG.md sections 5.6 + 5.7
--
-- Đã apply lên Supabase project DaiLoc App qua MCP apply_migration:
--   cham_cong_p6_payroll_rpcs
--
-- Smoke test PASS:
-- 1. compute_payroll_period(1) trên period empty → ok, items_count=N, total=...
-- 2. finalize_payroll_period(1, admin_id) → ok
-- 3. compute_payroll_period(1) sau finalize → reject "Kỳ lương đã chốt"
-- ============================================================

-- 5.6 compute_payroll_period — idempotent (DELETE + INSERT items)
CREATE OR REPLACE FUNCTION compute_payroll_period(
    p_period_id BIGINT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_period RECORD;
    v_nv RECORD;
    v_rate RECORD;
    v_sess RECORD;
    v_d DATE;
    v_worked_min INT;
    v_salary INT;
    v_items_count INT := 0;
    v_total_amount BIGINT := 0;
    v_user_name TEXT;
BEGIN
    -- 1. Validate period status
    SELECT * INTO v_period FROM attendance_payroll_periods WHERE id = p_period_id;
    IF v_period.id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Kỳ lương không tồn tại');
    END IF;
    IF v_period.status <> 'open' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Kỳ lương đã chốt — không tính lại được');
    END IF;

    -- 2. DELETE existing items (idempotent)
    DELETE FROM attendance_payroll_items WHERE period_id = p_period_id;

    -- 3. Build sessions for all days in range (idempotent — preserve edited)
    v_d := v_period.start_date;
    WHILE v_d <= v_period.end_date LOOP
        PERFORM build_sessions_for_date(v_d, NULL);
        v_d := v_d + INTERVAL '1 day';
    END LOOP;

    -- 4. For each active NV with rate configured
    FOR v_nv IN
        SELECT id, ho_ten FROM nhan_vien WHERE active = true ORDER BY id
    LOOP
        SELECT * INTO v_rate FROM attendance_employee_rates WHERE nhan_vien_id = v_nv.id;
        IF v_rate.nhan_vien_id IS NULL THEN
            CONTINUE;  -- NV chưa cấu hình rate
        END IF;

        IF v_rate.salary_type = 'monthly_fixed' THEN
            INSERT INTO attendance_payroll_items (
                period_id, nhan_vien_id, rate_snapshot, salary_amount, item_type
            ) VALUES (
                p_period_id, v_nv.id, v_rate.monthly_fixed, v_rate.monthly_fixed, 'monthly_fixed'
            );
            v_items_count := v_items_count + 1;
            v_total_amount := v_total_amount + v_rate.monthly_fixed;
        ELSIF v_rate.salary_type = 'hourly' THEN
            FOR v_sess IN
                SELECT s.id AS sess_id,
                       s.status AS sess_status,
                       s.worked_minutes,
                       s.ot_minutes,
                       sch.work_date,
                       sch.shift_template_id,
                       st.default_hours
                  FROM attendance_sessions s
                  JOIN attendance_work_schedules sch ON sch.id = s.schedule_id
                  JOIN shift_templates st ON st.id = sch.shift_template_id
                 WHERE s.nhan_vien_id = v_nv.id
                   AND sch.work_date BETWEEN v_period.start_date AND v_period.end_date
            LOOP
                IF v_sess.sess_status = 'leave_paid' THEN
                    v_worked_min := COALESCE(v_sess.default_hours, 0) * 60;
                    v_salary := ROUND(v_worked_min::numeric * v_rate.hourly_rate::numeric / 60.0)::int;
                    INSERT INTO attendance_payroll_items (
                        period_id, nhan_vien_id, session_id, work_date, shift_template_id,
                        worked_minutes, ot_minutes, rate_snapshot, salary_amount, item_type
                    ) VALUES (
                        p_period_id, v_nv.id, v_sess.sess_id, v_sess.work_date, v_sess.shift_template_id,
                        v_worked_min, 0, v_rate.hourly_rate, v_salary, 'leave_paid'
                    );
                    v_items_count := v_items_count + 1;
                    v_total_amount := v_total_amount + v_salary;
                ELSIF v_sess.sess_status IN ('completed', 'auto_closed', 'edited') THEN
                    v_worked_min := COALESCE(v_sess.worked_minutes, 0);
                    IF v_worked_min > 0 THEN
                        v_salary := ROUND(v_worked_min::numeric * v_rate.hourly_rate::numeric / 60.0)::int;
                        INSERT INTO attendance_payroll_items (
                            period_id, nhan_vien_id, session_id, work_date, shift_template_id,
                            worked_minutes, ot_minutes, rate_snapshot, salary_amount, item_type
                        ) VALUES (
                            p_period_id, v_nv.id, v_sess.sess_id, v_sess.work_date, v_sess.shift_template_id,
                            v_worked_min, COALESCE(v_sess.ot_minutes, 0), v_rate.hourly_rate, v_salary, 'shift'
                        );
                        v_items_count := v_items_count + 1;
                        v_total_amount := v_total_amount + v_salary;
                    END IF;
                END IF;
                -- absent, leave_unpaid, open, pending: skip (không tính lương)
            END LOOP;
        END IF;
    END LOOP;

    -- 5. Audit
    SELECT ho_ten INTO v_user_name FROM nhan_vien WHERE id = COALESCE(v_period.created_by, 0);
    INSERT INTO action_logs (ho_ten, action, level, detail)
    VALUES (
        COALESCE(v_user_name, 'system'),
        'ATT_PAYROLL_COMPUTE', 'info',
        json_build_object(
            'period_id', p_period_id,
            'items_count', v_items_count,
            'total_amount', v_total_amount
        )::text
    );

    RETURN jsonb_build_object(
        'ok', true,
        'period_id', p_period_id,
        'items_count', v_items_count,
        'total_amount', v_total_amount
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;


-- 5.7 finalize_payroll_period — lock kỳ lương
CREATE OR REPLACE FUNCTION finalize_payroll_period(
    p_period_id BIGINT,
    p_admin_id INTEGER
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_status TEXT;
    v_admin_name TEXT;
BEGIN
    SELECT status INTO v_status FROM attendance_payroll_periods WHERE id = p_period_id;
    IF v_status IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Kỳ lương không tồn tại');
    END IF;
    IF v_status <> 'open' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Kỳ lương đã chốt');
    END IF;

    SELECT ho_ten INTO v_admin_name FROM nhan_vien WHERE id = p_admin_id;
    IF v_admin_name IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Admin không tồn tại');
    END IF;

    UPDATE attendance_payroll_periods
       SET status = 'finalized',
           finalized_by = p_admin_id,
           finalized_at = now()
     WHERE id = p_period_id;

    INSERT INTO action_logs (ho_ten, action, level, detail)
    VALUES (
        v_admin_name,
        'ATT_PAYROLL_FINALIZE', 'warn',
        json_build_object('period_id', p_period_id)::text
    );

    RETURN jsonb_build_object('ok', true, 'period_id', p_period_id);
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;

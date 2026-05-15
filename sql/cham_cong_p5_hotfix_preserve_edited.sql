-- ============================================================
-- Phase 5 Hotfix: build_session_for_schedule preserve status='edited'
--
-- Bug cũ: ON CONFLICT update giữ status='edited' nhưng overwrite
-- check_in_at/out_at/worked_minutes etc → mất công admin sửa.
--
-- Fix: early return ngay đầu function nếu existing session status='edited'.
-- Defense in depth: ON CONFLICT vẫn giữ CASE preserve status.
--
-- Đã apply lên Supabase project DaiLoc App qua MCP apply_migration:
--   cham_cong_p5_hotfix_preserve_edited
--
-- Smoke test (5/5 PASS):
-- 1. Build session → status='completed'
-- 2. Admin update_session_admin → status='edited', check_in_at lùi 15p, late=0
-- 3. Build lần 2 → returns {ok, skipped:true, reason:preserved_admin_edit}
-- 4. Session vẫn giữ data admin sửa (check_in/late/note unchanged)
-- 5. Admin update_session_admin lần 2 → vẫn work, không bị block
--
-- Refs: PLAN_CHAM_CONG.md section 5.3 cần update doc skip logic.
-- ============================================================

CREATE OR REPLACE FUNCTION build_session_for_schedule(
    p_schedule_id BIGINT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_existing RECORD;
    v_sched RECORD;
    v_in TIMESTAMPTZ;
    v_out TIMESTAMPTZ;
    v_actual_in TIMESTAMPTZ;
    v_actual_out TIMESTAMPTZ;
    v_is_late BOOLEAN := FALSE;
    v_late_min INT := 0;
    v_worked INT := 0;
    v_regular INT := 0;
    v_ot INT := 0;
    v_is_auto BOOLEAN := FALSE;
    v_status TEXT;
    v_session_id BIGINT;
    v_now TIMESTAMPTZ := now();
    v_has_event BOOLEAN;
BEGIN
    -- HOTFIX: Preserve admin-edited session — return early không touch.
    SELECT id, status INTO v_existing
      FROM attendance_sessions
     WHERE schedule_id = p_schedule_id;

    IF v_existing.id IS NOT NULL AND v_existing.status = 'edited' THEN
        RETURN jsonb_build_object(
            'ok', true,
            'session_id', v_existing.id,
            'status', 'edited',
            'skipped', true,
            'reason', 'preserved_admin_edit'
        );
    END IF;

    SELECT * INTO v_sched FROM attendance_work_schedules WHERE id = p_schedule_id;
    IF v_sched.id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Schedule không tồn tại');
    END IF;

    IF v_sched.status = 'cancelled' THEN
        DELETE FROM attendance_sessions WHERE schedule_id = p_schedule_id;
        RETURN jsonb_build_object('ok', true, 'status', 'skipped_cancelled');
    END IF;

    IF v_sched.status IN ('leave_paid', 'leave_unpaid') THEN
        INSERT INTO attendance_sessions (nhan_vien_id, schedule_id, status, worked_minutes)
        VALUES (v_sched.nhan_vien_id, p_schedule_id, v_sched.status, 0)
        ON CONFLICT (schedule_id) DO UPDATE SET
            status = EXCLUDED.status,
            worked_minutes = 0,
            updated_at = now()
        RETURNING id INTO v_session_id;
        RETURN jsonb_build_object('ok', true, 'session_id', v_session_id, 'status', v_sched.status, 'worked_minutes', 0);
    END IF;

    SELECT MIN(event_time) FILTER (WHERE event_type='IN'),
           MAX(event_time) FILTER (WHERE event_type='OUT')
      INTO v_in, v_out
      FROM attendance_events WHERE schedule_id = p_schedule_id;

    v_has_event := v_in IS NOT NULL OR v_out IS NOT NULL;

    IF NOT v_has_event THEN
        IF v_now > v_sched.scheduled_end_at THEN
            INSERT INTO attendance_sessions (nhan_vien_id, schedule_id, status, worked_minutes)
            VALUES (v_sched.nhan_vien_id, p_schedule_id, 'absent', 0)
            ON CONFLICT (schedule_id) DO UPDATE SET
                status = 'absent', worked_minutes = 0, check_in_at = NULL, check_out_at = NULL,
                actual_check_in_at = NULL, actual_check_out_at = NULL, is_late = FALSE, late_minutes = 0,
                regular_minutes = 0, ot_minutes = 0, is_auto_checkout = FALSE, updated_at = now()
            RETURNING id INTO v_session_id;
            RETURN jsonb_build_object('ok', true, 'session_id', v_session_id, 'status', 'absent', 'worked_minutes', 0);
        ELSE
            RETURN jsonb_build_object('ok', true, 'status', 'pending', 'session_id', NULL);
        END IF;
    END IF;

    v_actual_in := GREATEST(v_in, v_sched.scheduled_start_at);

    IF v_out IS NULL THEN
        IF v_now > v_sched.scheduled_end_at THEN
            v_actual_out := v_sched.scheduled_end_at;
            v_is_auto := TRUE;
            v_status := 'auto_closed';
        ELSE
            v_actual_out := NULL;
            v_status := 'open';
        END IF;
    ELSE
        v_actual_out := v_out;
        v_status := 'completed';
    END IF;

    IF v_in IS NOT NULL THEN
        v_is_late := v_in > v_sched.scheduled_start_at;
        v_late_min := GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (v_in - v_sched.scheduled_start_at)) / 60)::INT);
    END IF;

    IF v_actual_out IS NOT NULL AND v_actual_in IS NOT NULL THEN
        v_worked := GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (v_actual_out - v_actual_in)) / 60)::INT);
        v_regular := LEAST(
            v_worked,
            GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (v_sched.scheduled_end_at - v_actual_in)) / 60)::INT)
        );
        v_ot := GREATEST(0, v_worked - v_regular);
    END IF;

    INSERT INTO attendance_sessions (
        nhan_vien_id, schedule_id, check_in_at, check_out_at,
        actual_check_in_at, actual_check_out_at,
        is_late, late_minutes, worked_minutes, regular_minutes, ot_minutes,
        is_auto_checkout, status
    ) VALUES (
        v_sched.nhan_vien_id, p_schedule_id, v_in, v_out,
        v_actual_in, v_actual_out,
        v_is_late, v_late_min, v_worked, v_regular, v_ot,
        v_is_auto, v_status
    )
    ON CONFLICT (schedule_id) DO UPDATE SET
        check_in_at = EXCLUDED.check_in_at,
        check_out_at = EXCLUDED.check_out_at,
        actual_check_in_at = EXCLUDED.actual_check_in_at,
        actual_check_out_at = EXCLUDED.actual_check_out_at,
        is_late = EXCLUDED.is_late,
        late_minutes = EXCLUDED.late_minutes,
        worked_minutes = EXCLUDED.worked_minutes,
        regular_minutes = EXCLUDED.regular_minutes,
        ot_minutes = EXCLUDED.ot_minutes,
        is_auto_checkout = EXCLUDED.is_auto_checkout,
        -- Defense: edited check ở early return phía trên xử lý chính,
        -- ở đây giữ CASE phòng race condition.
        status = CASE WHEN attendance_sessions.status = 'edited' THEN 'edited' ELSE EXCLUDED.status END,
        updated_at = now()
    RETURNING id INTO v_session_id;

    RETURN jsonb_build_object(
        'ok', true,
        'session_id', v_session_id,
        'status', v_status,
        'worked_minutes', v_worked,
        'regular_minutes', v_regular,
        'ot_minutes', v_ot,
        'is_late', v_is_late,
        'late_minutes', v_late_min
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;

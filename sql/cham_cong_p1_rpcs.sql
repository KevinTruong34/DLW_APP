-- ============================================================
-- Module Chấm công — Phase 1 RPC primitives
-- Refs: PLAN_CHAM_CONG.md sections 5.1 - 5.5
-- ============================================================

-- 5.1 validate_check_in_pos
CREATE OR REPLACE FUNCTION validate_check_in_pos(
    p_nhan_vien_id INTEGER,
    p_ip_address   TEXT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_active BOOLEAN;
    v_schedule RECORD;
    v_prefixes TEXT[];
    v_pref TEXT;
    v_ip_ok BOOLEAN := FALSE;
    v_has_in BOOLEAN;
    v_has_out BOOLEAN;
    v_action TEXT;
    v_now TIMESTAMPTZ := now();
BEGIN
    SELECT active INTO v_active FROM nhan_vien WHERE id = p_nhan_vien_id;
    IF v_active IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'NV không tồn tại');
    END IF;
    IF NOT v_active THEN
        RETURN jsonb_build_object('ok', false, 'error', 'NV không active');
    END IF;

    SELECT s.id, s.scheduled_start_at, s.scheduled_end_at, st.label, st.branch_name
      INTO v_schedule
      FROM attendance_work_schedules s
      JOIN shift_templates st ON st.id = s.shift_template_id
     WHERE s.nhan_vien_id = p_nhan_vien_id
       AND s.status = 'scheduled'
       AND v_now BETWEEN (s.scheduled_start_at - INTERVAL '2 hours')
                     AND (s.scheduled_end_at   + INTERVAL '2 hours')
     ORDER BY s.scheduled_start_at
     LIMIT 1;

    IF v_schedule.id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Không có lịch trong khung giờ chấm');
    END IF;

    SELECT ip_prefixes INTO v_prefixes
      FROM attendance_branch_networks
     WHERE branch_name = v_schedule.branch_name;

    IF v_prefixes IS NULL OR array_length(v_prefixes, 1) IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Chi nhánh chưa cấu hình IP whitelist');
    END IF;

    FOREACH v_pref IN ARRAY v_prefixes LOOP
        IF p_ip_address LIKE v_pref || '%' THEN
            v_ip_ok := TRUE;
            EXIT;
        END IF;
    END LOOP;

    IF NOT v_ip_ok THEN
        RETURN jsonb_build_object('ok', false, 'error', 'IP không thuộc mạng cửa hàng');
    END IF;

    SELECT EXISTS (SELECT 1 FROM attendance_events WHERE schedule_id = v_schedule.id AND event_type = 'IN'),
           EXISTS (SELECT 1 FROM attendance_events WHERE schedule_id = v_schedule.id AND event_type = 'OUT')
      INTO v_has_in, v_has_out;

    IF v_has_in AND v_has_out THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Ca đã hoàn thành');
    ELSIF v_has_in THEN
        v_action := 'OUT';
    ELSE
        v_action := 'IN';
    END IF;

    RETURN jsonb_build_object(
        'ok', true,
        'schedule_id', v_schedule.id,
        'shift_label', v_schedule.label,
        'branch_name', v_schedule.branch_name,
        'action_expected', v_action
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;


-- 5.2 record_attendance_event
CREATE OR REPLACE FUNCTION record_attendance_event(
    p_nhan_vien_id INTEGER,
    p_event_type   TEXT,
    p_ip_address   TEXT,
    p_note         TEXT DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_validate jsonb;
    v_schedule_id BIGINT;
    v_action TEXT;
    v_event_id BIGINT;
    v_nv_name TEXT;
BEGIN
    v_validate := validate_check_in_pos(p_nhan_vien_id, p_ip_address);
    IF NOT (v_validate->>'ok')::boolean THEN
        RETURN v_validate;
    END IF;

    v_action := v_validate->>'action_expected';
    IF v_action IS DISTINCT FROM p_event_type THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Hành động không khớp (expected ' || v_action || ')');
    END IF;

    v_schedule_id := (v_validate->>'schedule_id')::BIGINT;

    INSERT INTO attendance_events (nhan_vien_id, schedule_id, event_type, event_time, ip_address, note)
    VALUES (p_nhan_vien_id, v_schedule_id, p_event_type, now(), p_ip_address, p_note)
    RETURNING id INTO v_event_id;

    SELECT ho_ten INTO v_nv_name FROM nhan_vien WHERE id = p_nhan_vien_id;

    INSERT INTO action_logs (ho_ten, action, level, detail)
    VALUES (
        v_nv_name,
        'ATT_' || p_event_type, 'info',
        json_build_object('nv', p_nhan_vien_id, 'schedule', v_schedule_id, 'ip', p_ip_address, 'event_id', v_event_id)::text
    );

    RETURN jsonb_build_object('ok', true, 'event_id', v_event_id, 'schedule_id', v_schedule_id);
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;


-- 5.3 build_session_for_schedule
CREATE OR REPLACE FUNCTION build_session_for_schedule(
    p_schedule_id BIGINT
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
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


-- 5.4 build_sessions_for_date
CREATE OR REPLACE FUNCTION build_sessions_for_date(
    p_work_date DATE,
    p_chi_nhanh TEXT DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_sched_id BIGINT;
    v_res jsonb;
    v_count INT := 0;
    v_by_status jsonb := '{}'::jsonb;
    v_status TEXT;
BEGIN
    FOR v_sched_id IN
        SELECT s.id
          FROM attendance_work_schedules s
          JOIN shift_templates st ON st.id = s.shift_template_id
         WHERE s.work_date = p_work_date
           AND (p_chi_nhanh IS NULL OR st.branch_name = p_chi_nhanh)
    LOOP
        v_res := build_session_for_schedule(v_sched_id);
        v_count := v_count + 1;
        v_status := COALESCE(v_res->>'status', 'unknown');
        v_by_status := jsonb_set(
            v_by_status,
            ARRAY[v_status],
            to_jsonb(COALESCE((v_by_status->>v_status)::INT, 0) + 1)
        );
    END LOOP;

    RETURN jsonb_build_object(
        'ok', true,
        'sessions_count', v_count,
        'by_status', v_by_status
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;


-- 5.5 update_session_admin
CREATE OR REPLACE FUNCTION update_session_admin(
    p_session_id    BIGINT,
    p_check_in_at   TIMESTAMPTZ,
    p_check_out_at  TIMESTAMPTZ,
    p_note          TEXT,
    p_reason        TEXT,
    p_admin_id      INTEGER
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_before jsonb;
    v_after jsonb;
    v_session RECORD;
    v_admin_name TEXT;
    v_actual_in TIMESTAMPTZ;
    v_actual_out TIMESTAMPTZ;
    v_is_late BOOLEAN := FALSE;
    v_late_min INT := 0;
    v_worked INT := 0;
    v_regular INT := 0;
    v_ot INT := 0;
    v_fields_changed TEXT[] := ARRAY[]::TEXT[];
BEGIN
    IF p_reason IS NULL OR length(trim(p_reason)) = 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Lý do sửa bắt buộc');
    END IF;

    SELECT ho_ten INTO v_admin_name FROM nhan_vien WHERE id = p_admin_id;
    IF v_admin_name IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Admin không tồn tại');
    END IF;

    SELECT s.id, s.note AS session_note, sch.scheduled_start_at, sch.scheduled_end_at
      INTO v_session
      FROM attendance_sessions s
      JOIN attendance_work_schedules sch ON sch.id = s.schedule_id
     WHERE s.id = p_session_id;
    IF v_session.id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Session không tồn tại');
    END IF;

    SELECT to_jsonb(s) INTO v_before FROM attendance_sessions s WHERE s.id = p_session_id;

    v_actual_in := GREATEST(p_check_in_at, v_session.scheduled_start_at);
    v_actual_out := p_check_out_at;

    IF p_check_in_at IS NOT NULL THEN
        v_is_late := p_check_in_at > v_session.scheduled_start_at;
        v_late_min := GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (p_check_in_at - v_session.scheduled_start_at)) / 60)::INT);
    END IF;

    IF v_actual_in IS NOT NULL AND v_actual_out IS NOT NULL THEN
        v_worked := GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (v_actual_out - v_actual_in)) / 60)::INT);
        v_regular := LEAST(
            v_worked,
            GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (v_session.scheduled_end_at - v_actual_in)) / 60)::INT)
        );
        v_ot := GREATEST(0, v_worked - v_regular);
    END IF;

    UPDATE attendance_sessions SET
        check_in_at = p_check_in_at,
        check_out_at = p_check_out_at,
        actual_check_in_at = v_actual_in,
        actual_check_out_at = v_actual_out,
        is_late = v_is_late,
        late_minutes = v_late_min,
        worked_minutes = v_worked,
        regular_minutes = v_regular,
        ot_minutes = v_ot,
        is_auto_checkout = FALSE,
        status = 'edited',
        note = p_note,
        updated_at = now()
    WHERE id = p_session_id;

    SELECT to_jsonb(s) INTO v_after FROM attendance_sessions s WHERE s.id = p_session_id;

    IF (v_before->>'check_in_at') IS DISTINCT FROM (v_after->>'check_in_at') THEN
        v_fields_changed := array_append(v_fields_changed, 'check_in_at');
    END IF;
    IF (v_before->>'check_out_at') IS DISTINCT FROM (v_after->>'check_out_at') THEN
        v_fields_changed := array_append(v_fields_changed, 'check_out_at');
    END IF;
    IF (v_before->>'note') IS DISTINCT FROM (v_after->>'note') THEN
        v_fields_changed := array_append(v_fields_changed, 'note');
    END IF;

    INSERT INTO admin_edit_history (
        table_name, record_id, snapshot_before, snapshot_after,
        fields_changed, edited_by_id, edited_by_name, edit_reason
    ) VALUES (
        'attendance_sessions', p_session_id::text, v_before, v_after,
        v_fields_changed, p_admin_id::bigint, v_admin_name, p_reason
    );

    INSERT INTO action_logs (ho_ten, action, level, detail)
    VALUES (
        v_admin_name, 'ATT_SESSION_EDIT', 'warn',
        json_build_object('session_id', p_session_id, 'fields', v_fields_changed, 'reason', p_reason)::text
    );

    RETURN jsonb_build_object(
        'ok', true,
        'session_id', p_session_id,
        'fields_changed', v_fields_changed
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('ok', false, 'error', SQLERRM);
END;
$$;

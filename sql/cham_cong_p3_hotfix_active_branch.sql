-- ============================================================
-- Phase 3 Hotfix #2: enforce active_chi_nhanh trong validate + record
-- Refs: PLAN_CHAM_CONG.md section 5.1, 5.2 update signature.
--
-- Backward compat: p_active_chi_nhanh DEFAULT NULL → behavior cũ.
--
-- DEPLOYMENT NOTE:
-- Vì CREATE OR REPLACE FUNCTION không thay thế khi signature thay đổi
-- (số param khác), cần DROP function cũ trước. Sau apply migration:
--   DROP FUNCTION IF EXISTS validate_check_in_pos(INTEGER, TEXT);
--   DROP FUNCTION IF EXISTS record_attendance_event(INTEGER, TEXT, TEXT, TEXT);
-- (Đã chạy trong migration cham_cong_p3_hotfix_drop_old_signatures.)
-- ============================================================

-- 5.1 validate_check_in_pos — thêm param p_active_chi_nhanh
CREATE OR REPLACE FUNCTION validate_check_in_pos(
    p_nhan_vien_id     INTEGER,
    p_ip_address       TEXT,
    p_active_chi_nhanh TEXT DEFAULT NULL
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

    -- HOTFIX #2: check active_chi_nhanh khớp branch của ca
    -- (chỉ apply khi caller pass param — backward compat)
    IF p_active_chi_nhanh IS NOT NULL
       AND v_schedule.branch_name <> p_active_chi_nhanh THEN
        RETURN jsonb_build_object(
            'ok', false,
            'error', format(
                'Bạn đang chọn chi nhánh "%s" nhưng có lịch tại "%s" hôm nay. Bấm avatar → đổi sang "%s" để chấm công.',
                p_active_chi_nhanh, v_schedule.branch_name, v_schedule.branch_name
            )
        );
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


-- 5.2 record_attendance_event — thêm param p_active_chi_nhanh, pass through validate
CREATE OR REPLACE FUNCTION record_attendance_event(
    p_nhan_vien_id     INTEGER,
    p_event_type       TEXT,
    p_ip_address       TEXT,
    p_note             TEXT DEFAULT NULL,
    p_active_chi_nhanh TEXT DEFAULT NULL
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
    -- Re-validate (defense in depth) — pass active_chi_nhanh để check lại
    -- (NV có thể đổi CN giữa lúc dialog mở và click confirm)
    v_validate := validate_check_in_pos(p_nhan_vien_id, p_ip_address, p_active_chi_nhanh);
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

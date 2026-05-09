-- ============================================================
-- Admin B2a — Phase 2 RPCs
-- Applied: 2026-05-09 via Supabase MCP migration `admin_b2a_phase2_rpcs`
--
-- 1) _admin_check_can_edit_hd_pos(p_ma_hd) → jsonb (helper)
-- 2) sua_hoa_don_pos_admin(payload jsonb) → jsonb
-- 3) load_hd_pos_with_history(p_ma_hd) → jsonb (UI helper)
--
-- Refactor vs plan §3.2: pre-validate items stock dùng net_diff
-- (new_sl - old_sl) trước khi state change → RETURN clean JSON
-- thay vì RAISE EXCEPTION. Consistent với pattern B1.
-- ============================================================

-- ════════════════════════════════════════════════════════════
-- 1) Helper: _admin_check_can_edit_hd_pos
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION _admin_check_can_edit_hd_pos(p_ma_hd text)
RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_hd hoa_don_pos%ROWTYPE;
    v_pdt_count int;
BEGIN
    SELECT * INTO v_hd FROM hoa_don_pos WHERE ma_hd = p_ma_hd;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'HĐ không tồn tại');
    END IF;

    IF v_hd.trang_thai != 'Hoàn thành' THEN
        RETURN jsonb_build_object('ok', false,
            'error', format('HĐ trang_thai = %s, chỉ sửa được HĐ Hoàn thành', v_hd.trang_thai));
    END IF;

    SELECT COUNT(*) INTO v_pdt_count
    FROM phieu_doi_tra_pos
    WHERE ma_hd_goc = p_ma_hd AND trang_thai != 'Đã hủy';

    RETURN jsonb_build_object(
        'ok', true,
        'has_active_pdt', v_pdt_count > 0,
        'pdt_count', v_pdt_count,
        'current_data', to_jsonb(v_hd)
    );
END;
$$;


-- ════════════════════════════════════════════════════════════
-- 2) sua_hoa_don_pos_admin
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION sua_hoa_don_pos_admin(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_admin_id bigint;
    v_admin_username text;
    v_admin_ho_ten text;
    v_validate jsonb;
    v_check jsonb;
    v_ma_hd text;
    v_has_pdt boolean;
    v_snapshot_before jsonb;
    v_snapshot_after jsonb;
    v_fields_changed text[] := ARRAY[]::text[];
    v_old_hd hoa_don_pos%ROWTYPE;
    v_new_hd hoa_don_pos%ROWTYPE;
    v_new_items jsonb;
    v_new_item jsonb;
    v_diff_row RECORD;
    v_chi_nhanh text;
    v_ma_hang text;
    v_so_luong int;
    v_don_gia int;
    v_ton_hien_tai int;
    v_tong_tien_hang int := 0;
    v_giam_gia int;
    v_log_detail text := '';
    v_new_nv_id bigint;
    v_new_nv_ho_ten text;
    v_history_id bigint;
BEGIN
    -- 1. Validate admin
    v_admin_id := (payload->>'admin_id')::bigint;
    SELECT username, ho_ten INTO v_admin_username, v_admin_ho_ten
    FROM nhan_vien WHERE id = v_admin_id;

    SELECT _admin_validate_request(v_admin_id, NULL) INTO v_validate;
    IF NOT (v_validate->>'ok')::boolean THEN
        RETURN v_validate;
    END IF;

    -- 2. Check HĐ có sửa được
    v_ma_hd := payload->>'ma_hd';
    IF v_ma_hd IS NULL OR v_ma_hd = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu ma_hd');
    END IF;

    SELECT _admin_check_can_edit_hd_pos(v_ma_hd) INTO v_check;
    IF NOT (v_check->>'ok')::boolean THEN
        RETURN v_check;
    END IF;
    v_has_pdt := (v_check->>'has_active_pdt')::boolean;

    -- 3. Lock + load
    SELECT * INTO v_old_hd FROM hoa_don_pos WHERE ma_hd = v_ma_hd FOR UPDATE;
    v_chi_nhanh := v_old_hd.chi_nhanh;

    -- 4. Validate LOCK fields
    IF payload ? 'created_at' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'created_at LOCKED, không được sửa');
    END IF;
    IF payload ? 'chi_nhanh' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'chi_nhanh LOCKED, không được sửa');
    END IF;
    IF payload ? 'trang_thai' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'trang_thai LOCKED');
    END IF;
    IF payload ? 'ma_hd_new' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'ma_hd LOCKED');
    END IF;

    -- 5. Items sửa khi không có PDT active
    IF v_has_pdt AND payload ? 'items' THEN
        RETURN jsonb_build_object('ok', false,
            'error', format('HĐ này có %s phiếu đổi/trả active. Cho sửa header thôi, không sửa items.',
                            v_check->>'pdt_count'));
    END IF;

    -- 6. Snapshot BEFORE
    v_snapshot_before := jsonb_build_object(
        'header', to_jsonb(v_old_hd),
        'items', COALESCE(
            (SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id) FROM hoa_don_pos_ct ct WHERE ma_hd = v_ma_hd),
            '[]'::jsonb
        )
    );

    -- 7. Pre-validate items mới (KHÔNG state change)
    IF payload ? 'items' AND NOT v_has_pdt THEN
        v_new_items := payload->'items';

        FOR v_new_item IN SELECT * FROM jsonb_array_elements(v_new_items) LOOP
            v_ma_hang := v_new_item->>'ma_hang';
            v_so_luong := (v_new_item->>'so_luong')::int;
            v_don_gia := (v_new_item->>'don_gia')::int;

            IF v_ma_hang IS NULL OR v_ma_hang = '' THEN
                RETURN jsonb_build_object('ok', false, 'error', 'Item thiếu ma_hang');
            END IF;
            IF v_so_luong <= 0 THEN
                RETURN jsonb_build_object('ok', false,
                    'error', format('Item %s: so_luong phải > 0', v_ma_hang));
            END IF;
            IF v_don_gia < 0 THEN
                RETURN jsonb_build_object('ok', false,
                    'error', format('Item %s: don_gia không được âm', v_ma_hang));
            END IF;
        END LOOP;

        FOR v_diff_row IN
            WITH old_q AS (
                SELECT ma_hang, SUM(so_luong)::int AS old_sl
                FROM hoa_don_pos_ct WHERE ma_hd = v_ma_hd
                GROUP BY ma_hang
            ),
            new_q AS (
                SELECT (it->>'ma_hang') AS ma_hang,
                       SUM((it->>'so_luong')::int)::int AS new_sl
                FROM jsonb_array_elements(v_new_items) it
                GROUP BY (it->>'ma_hang')
            )
            SELECT COALESCE(n.ma_hang, o.ma_hang) AS ma_hang,
                   COALESCE(n.new_sl, 0) - COALESCE(o.old_sl, 0) AS net_diff
            FROM new_q n
            FULL OUTER JOIN old_q o USING (ma_hang)
        LOOP
            IF v_diff_row.net_diff > 0 AND NOT is_open_price_sql(v_diff_row.ma_hang) THEN
                SELECT COALESCE(SUM("Tồn cuối kì"), 0)::int INTO v_ton_hien_tai
                FROM the_kho
                WHERE "Mã hàng" = v_diff_row.ma_hang AND "Chi nhánh" = v_chi_nhanh;

                IF v_ton_hien_tai < v_diff_row.net_diff THEN
                    RETURN jsonb_build_object('ok', false,
                        'error', format('Item %s không đủ tồn để tăng SL (có %s, cần thêm %s)',
                            v_diff_row.ma_hang, v_ton_hien_tai, v_diff_row.net_diff));
                END IF;
            END IF;
        END LOOP;
    END IF;

    -- 8. Update header fields
    IF payload ? 'nguoi_ban_id' THEN
        v_new_nv_id := (payload->>'nguoi_ban_id')::bigint;
        SELECT ho_ten INTO v_new_nv_ho_ten FROM nhan_vien WHERE id = v_new_nv_id;
        IF v_new_nv_ho_ten IS NULL THEN
            RETURN jsonb_build_object('ok', false, 'error', 'nguoi_ban_id không tồn tại');
        END IF;
        IF v_old_hd.nguoi_ban_id IS DISTINCT FROM v_new_nv_id THEN
            UPDATE hoa_don_pos SET nguoi_ban_id = v_new_nv_id, nguoi_ban = v_new_nv_ho_ten
            WHERE ma_hd = v_ma_hd;
            v_fields_changed := array_append(v_fields_changed, 'nguoi_ban');
            v_log_detail := v_log_detail || format(' nguoi_ban=%s→%s',
                                                     v_old_hd.nguoi_ban, v_new_nv_ho_ten);
        END IF;
    END IF;

    IF payload ? 'ten_khach' THEN
        IF v_old_hd.ten_khach IS DISTINCT FROM (payload->>'ten_khach') THEN
            UPDATE hoa_don_pos SET ten_khach = payload->>'ten_khach' WHERE ma_hd = v_ma_hd;
            v_fields_changed := array_append(v_fields_changed, 'ten_khach');
        END IF;
    END IF;

    IF payload ? 'sdt_khach' THEN
        IF v_old_hd.sdt_khach IS DISTINCT FROM (payload->>'sdt_khach') THEN
            UPDATE hoa_don_pos SET sdt_khach = payload->>'sdt_khach' WHERE ma_hd = v_ma_hd;
            v_fields_changed := array_append(v_fields_changed, 'sdt_khach');
        END IF;
    END IF;

    IF payload ? 'ghi_chu' THEN
        IF v_old_hd.ghi_chu IS DISTINCT FROM (payload->>'ghi_chu') THEN
            UPDATE hoa_don_pos SET ghi_chu = payload->>'ghi_chu' WHERE ma_hd = v_ma_hd;
            v_fields_changed := array_append(v_fields_changed, 'ghi_chu');
        END IF;
    END IF;

    IF payload ? 'tien_mat' THEN
        IF v_old_hd.tien_mat IS DISTINCT FROM (payload->>'tien_mat')::int THEN
            UPDATE hoa_don_pos SET tien_mat = (payload->>'tien_mat')::int WHERE ma_hd = v_ma_hd;
            v_fields_changed := array_append(v_fields_changed, 'tien_mat');
            v_log_detail := v_log_detail || format(' tien_mat=%s→%s',
                                                     v_old_hd.tien_mat, payload->>'tien_mat');
        END IF;
    END IF;
    IF payload ? 'chuyen_khoan' THEN
        IF v_old_hd.chuyen_khoan IS DISTINCT FROM (payload->>'chuyen_khoan')::int THEN
            UPDATE hoa_don_pos SET chuyen_khoan = (payload->>'chuyen_khoan')::int WHERE ma_hd = v_ma_hd;
            v_fields_changed := array_append(v_fields_changed, 'chuyen_khoan');
            v_log_detail := v_log_detail || format(' chuyen_khoan=%s→%s',
                                                     v_old_hd.chuyen_khoan, payload->>'chuyen_khoan');
        END IF;
    END IF;
    IF payload ? 'the' THEN
        IF v_old_hd.the IS DISTINCT FROM (payload->>'the')::int THEN
            UPDATE hoa_don_pos SET the = (payload->>'the')::int WHERE ma_hd = v_ma_hd;
            v_fields_changed := array_append(v_fields_changed, 'the');
            v_log_detail := v_log_detail || format(' the=%s→%s', v_old_hd.the, payload->>'the');
        END IF;
    END IF;

    -- 9. Update items
    IF payload ? 'items' AND NOT v_has_pdt THEN
        FOR v_diff_row IN
            SELECT ma_hang, so_luong FROM hoa_don_pos_ct WHERE ma_hd = v_ma_hd
        LOOP
            IF NOT is_open_price_sql(v_diff_row.ma_hang) THEN
                UPDATE the_kho
                SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + v_diff_row.so_luong
                WHERE "Mã hàng" = v_diff_row.ma_hang AND "Chi nhánh" = v_chi_nhanh;
            END IF;
        END LOOP;

        DELETE FROM hoa_don_pos_ct WHERE ma_hd = v_ma_hd;

        v_tong_tien_hang := 0;
        FOR v_new_item IN SELECT * FROM jsonb_array_elements(v_new_items) LOOP
            v_ma_hang := v_new_item->>'ma_hang';
            v_so_luong := (v_new_item->>'so_luong')::int;
            v_don_gia := (v_new_item->>'don_gia')::int;

            INSERT INTO hoa_don_pos_ct
                (ma_hd, ma_hang, ten_hang, so_luong, don_gia, thanh_tien)
            VALUES
                (v_ma_hd, v_ma_hang, v_new_item->>'ten_hang',
                 v_so_luong, v_don_gia, v_so_luong * v_don_gia);

            IF NOT is_open_price_sql(v_ma_hang) THEN
                UPDATE the_kho
                SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) - v_so_luong
                WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
            END IF;

            v_tong_tien_hang := v_tong_tien_hang + (v_so_luong * v_don_gia);
        END LOOP;

        v_fields_changed := array_append(v_fields_changed, 'items');
        v_log_detail := v_log_detail || format(' items=%s→%s',
            v_old_hd.tong_tien_hang, v_tong_tien_hang);
    ELSE
        v_tong_tien_hang := v_old_hd.tong_tien_hang;
    END IF;

    -- 10. giam_gia + recompute khach_can_tra
    IF payload ? 'giam_gia_don' THEN
        v_giam_gia := (payload->>'giam_gia_don')::int;
        IF v_giam_gia < 0 THEN
            RETURN jsonb_build_object('ok', false, 'error', 'giam_gia_don không được âm');
        END IF;
        IF v_giam_gia > v_tong_tien_hang THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('giam_gia_don (%s) vượt tong_tien_hang (%s)',
                                v_giam_gia, v_tong_tien_hang));
        END IF;
        IF v_old_hd.giam_gia_don IS DISTINCT FROM v_giam_gia THEN
            v_fields_changed := array_append(v_fields_changed, 'giam_gia_don');
            v_log_detail := v_log_detail || format(' gg=%s→%s',
                                                     v_old_hd.giam_gia_don, v_giam_gia);
        END IF;
    ELSE
        v_giam_gia := v_old_hd.giam_gia_don;
    END IF;

    UPDATE hoa_don_pos
    SET tong_tien_hang = v_tong_tien_hang,
        giam_gia_don = v_giam_gia,
        khach_can_tra = v_tong_tien_hang - v_giam_gia
    WHERE ma_hd = v_ma_hd;

    -- 11. Snapshot AFTER
    SELECT * INTO v_new_hd FROM hoa_don_pos WHERE ma_hd = v_ma_hd;
    v_snapshot_after := jsonb_build_object(
        'header', to_jsonb(v_new_hd),
        'items', COALESCE(
            (SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id) FROM hoa_don_pos_ct ct WHERE ma_hd = v_ma_hd),
            '[]'::jsonb
        )
    );

    -- 12. Insert vào admin_edit_history + audit log (chỉ nếu thực sự thay đổi)
    IF array_length(v_fields_changed, 1) IS NULL OR array_length(v_fields_changed, 1) = 0 THEN
        RETURN jsonb_build_object('ok', true, 'ma_hd', v_ma_hd,
                                   'message', 'Không có field nào thay đổi',
                                   'fields_changed', ARRAY[]::text[]);
    END IF;

    INSERT INTO admin_edit_history
        (table_name, record_id, snapshot_before, snapshot_after,
         fields_changed, edited_by_id, edited_by_name, edit_reason)
    VALUES
        ('hoa_don_pos', v_ma_hd, v_snapshot_before, v_snapshot_after,
         v_fields_changed, v_admin_id, v_admin_ho_ten, payload->>'edit_reason')
    RETURNING id INTO v_history_id;

    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        v_admin_username, v_admin_ho_ten, v_chi_nhanh,
        'ADMIN_HD_EDIT',
        format('ma=%s changed=[%s]%s reason=%s',
            v_ma_hd, array_to_string(v_fields_changed, ','),
            v_log_detail, COALESCE(payload->>'edit_reason', '-')),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_hd', v_ma_hd,
        'fields_changed', v_fields_changed,
        'edit_history_id', v_history_id
    );
END;
$$;


-- ════════════════════════════════════════════════════════════
-- 3) load_hd_pos_with_history — UI helper
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION load_hd_pos_with_history(p_ma_hd text)
RETURNS jsonb
LANGUAGE sql STABLE
AS $$
    SELECT jsonb_build_object(
        'header', to_jsonb(h),
        'items', COALESCE(
            (SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id) FROM hoa_don_pos_ct ct WHERE ma_hd = p_ma_hd),
            '[]'::jsonb
        ),
        'edit_count', (SELECT COUNT(*) FROM admin_edit_history
                        WHERE table_name = 'hoa_don_pos' AND record_id = p_ma_hd),
        'edit_history', COALESCE(
            (SELECT jsonb_agg(jsonb_build_object(
                'id', id,
                'edited_at', edited_at,
                'edited_by_name', edited_by_name,
                'fields_changed', fields_changed,
                'edit_reason', edit_reason
            ) ORDER BY edited_at DESC) FROM admin_edit_history
            WHERE table_name = 'hoa_don_pos' AND record_id = p_ma_hd),
            '[]'::jsonb
        )
    )
    FROM hoa_don_pos h
    WHERE h.ma_hd = p_ma_hd;
$$;

-- ============================================================
-- Admin B2b — Phase 2 RPCs
-- Applied: 2026-05-09 via Supabase MCP migration `admin_b2b_phase2_rpcs`
--
-- 1) _admin_check_can_edit_sc(ma_phieu) — helper SC
-- 2) sua_phieu_sua_chua_admin(payload) — sửa SC, no stock
-- 3) _admin_check_can_edit_pdt(ma_pdt) — helper PDT
-- 4) sua_phieu_doi_tra_pos_admin(payload) — sửa PDT, items_moi only,
--    items_tra BLOCKED (per plan §0.2 risk-mitigation)
-- ============================================================

-- ════════════════════════════════════════════════════════════
-- 1) _admin_check_can_edit_sc
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION _admin_check_can_edit_sc(p_ma_phieu text)
RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_phieu phieu_sua_chua%ROWTYPE;
    v_apsc_count int;
    v_apsc_list text;
BEGIN
    SELECT * INTO v_phieu FROM phieu_sua_chua WHERE ma_phieu = p_ma_phieu;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Phiếu không tồn tại');
    END IF;

    IF v_phieu.trang_thai = 'Đã hủy' THEN
        RETURN jsonb_build_object('ok', false,
            'error', 'Phiếu đã hủy, không sửa được');
    END IF;

    SELECT COUNT(*), string_agg(detail, ' | ')
    INTO v_apsc_count, v_apsc_list
    FROM action_logs
    WHERE action = 'SC_HOA_DON'
      AND detail LIKE '%ma=' || p_ma_phieu || '%';

    RETURN jsonb_build_object(
        'ok', true,
        'has_apsc', v_apsc_count > 0,
        'apsc_count', v_apsc_count,
        'apsc_detail', COALESCE(v_apsc_list, ''),
        'current_data', to_jsonb(v_phieu)
    );
END;
$$;


-- ════════════════════════════════════════════════════════════
-- 2) sua_phieu_sua_chua_admin
-- ════════════════════════════════════════════════════════════
-- (Full source: see migration `admin_b2b_phase2_rpcs` in DB)
-- Editable: ten_khach, sdt_khach, loai_yeu_cau, hieu_dong_ho, dac_diem,
--   mo_ta_loi, ghi_chu_noi_bo, nguoi_tiep_nhan, trang_thai,
--   khach_tra_truoc, ngay_hen_tra, items
-- LOCK: ma_phieu, created_at, chi_nhanh, created_by/created_by_id
-- BLOCK: items khi đã có APSC (action_logs SC_HOA_DON)
-- No stock logic (phiếu sửa chữa stage 1 không đụng kho).
CREATE OR REPLACE FUNCTION sua_phieu_sua_chua_admin(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_admin_id bigint;
    v_admin_username text;
    v_admin_ho_ten text;
    v_validate jsonb;
    v_check jsonb;
    v_ma_phieu text;
    v_has_apsc boolean;
    v_old_phieu phieu_sua_chua%ROWTYPE;
    v_new_phieu phieu_sua_chua%ROWTYPE;
    v_snapshot_before jsonb;
    v_snapshot_after jsonb;
    v_fields_changed text[] := ARRAY[]::text[];
    v_log_detail text := '';
    v_new_items jsonb;
    v_new_item jsonb;
    v_history_id bigint;
    v_text_fields text[] := ARRAY['ten_khach', 'sdt_khach', 'loai_yeu_cau',
                                    'hieu_dong_ho', 'dac_diem', 'mo_ta_loi',
                                    'ghi_chu_noi_bo', 'nguoi_tiep_nhan', 'trang_thai'];
    v_field text;
    v_old_val text;
    v_new_val text;
BEGIN
    v_admin_id := (payload->>'admin_id')::bigint;
    SELECT username, ho_ten INTO v_admin_username, v_admin_ho_ten
    FROM nhan_vien WHERE id = v_admin_id;

    SELECT _admin_validate_request(v_admin_id, NULL) INTO v_validate;
    IF NOT (v_validate->>'ok')::boolean THEN
        RETURN v_validate;
    END IF;

    v_ma_phieu := payload->>'ma_phieu';
    IF v_ma_phieu IS NULL OR v_ma_phieu = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu ma_phieu');
    END IF;

    SELECT _admin_check_can_edit_sc(v_ma_phieu) INTO v_check;
    IF NOT (v_check->>'ok')::boolean THEN
        RETURN v_check;
    END IF;
    v_has_apsc := (v_check->>'has_apsc')::boolean;

    SELECT * INTO v_old_phieu FROM phieu_sua_chua WHERE ma_phieu = v_ma_phieu FOR UPDATE;

    v_snapshot_before := jsonb_build_object(
        'header', to_jsonb(v_old_phieu),
        'items', COALESCE(
            (SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id)
             FROM phieu_sua_chua_chi_tiet ct WHERE ma_phieu = v_ma_phieu),
            '[]'::jsonb
        )
    );

    IF payload ? 'created_at' THEN RETURN jsonb_build_object('ok', false, 'error', 'created_at LOCKED'); END IF;
    IF payload ? 'chi_nhanh' THEN RETURN jsonb_build_object('ok', false, 'error', 'chi_nhanh LOCKED'); END IF;
    IF payload ? 'created_by_id' OR payload ? 'created_by' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'created_by LOCKED');
    END IF;
    IF payload ? 'ma_phieu_new' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'ma_phieu LOCKED');
    END IF;

    IF v_has_apsc AND payload ? 'items' THEN
        RETURN jsonb_build_object('ok', false,
            'error', format('Phiếu đã convert APSC. Không sửa được items. (%s)',
                COALESCE(v_check->>'apsc_detail', '-')));
    END IF;

    FOREACH v_field IN ARRAY v_text_fields LOOP
        IF payload ? v_field THEN
            v_new_val := payload->>v_field;
            EXECUTE format('SELECT %I::text FROM phieu_sua_chua WHERE ma_phieu = $1', v_field)
                INTO v_old_val USING v_ma_phieu;

            IF v_old_val IS DISTINCT FROM v_new_val THEN
                EXECUTE format('UPDATE phieu_sua_chua SET %I = $1 WHERE ma_phieu = $2', v_field)
                    USING v_new_val, v_ma_phieu;
                v_fields_changed := array_append(v_fields_changed, v_field);
                v_log_detail := v_log_detail || format(' %s=%s→%s',
                    v_field,
                    LEFT(COALESCE(v_old_val, '-'), 20),
                    LEFT(COALESCE(v_new_val, '-'), 20));
            END IF;
        END IF;
    END LOOP;

    IF payload ? 'khach_tra_truoc' THEN
        IF v_old_phieu.khach_tra_truoc IS DISTINCT FROM (payload->>'khach_tra_truoc')::int THEN
            UPDATE phieu_sua_chua
            SET khach_tra_truoc = (payload->>'khach_tra_truoc')::int
            WHERE ma_phieu = v_ma_phieu;
            v_fields_changed := array_append(v_fields_changed, 'khach_tra_truoc');
            v_log_detail := v_log_detail || format(' khach_tra_truoc=%s→%s',
                v_old_phieu.khach_tra_truoc, payload->>'khach_tra_truoc');
        END IF;
    END IF;

    IF payload ? 'ngay_hen_tra' THEN
        DECLARE v_new_date date;
        BEGIN
            v_new_date := NULLIF(payload->>'ngay_hen_tra', '')::date;
            IF v_old_phieu.ngay_hen_tra IS DISTINCT FROM v_new_date THEN
                UPDATE phieu_sua_chua SET ngay_hen_tra = v_new_date
                WHERE ma_phieu = v_ma_phieu;
                v_fields_changed := array_append(v_fields_changed, 'ngay_hen_tra');
            END IF;
        END;
    END IF;

    IF payload ? 'items' AND NOT v_has_apsc THEN
        v_new_items := payload->'items';

        DELETE FROM phieu_sua_chua_chi_tiet WHERE ma_phieu = v_ma_phieu;

        FOR v_new_item IN SELECT * FROM jsonb_array_elements(v_new_items) LOOP
            INSERT INTO phieu_sua_chua_chi_tiet
                (ma_phieu, loai_dong, ten_hang, ma_hang, so_luong, don_gia, ghi_chu)
            VALUES (
                v_ma_phieu,
                COALESCE(v_new_item->>'loai_dong', 'Dịch vụ'),
                v_new_item->>'ten_hang',
                v_new_item->>'ma_hang',
                COALESCE((v_new_item->>'so_luong')::int, 1),
                COALESCE((v_new_item->>'don_gia')::int, 0),
                v_new_item->>'ghi_chu'
            );
        END LOOP;

        v_fields_changed := array_append(v_fields_changed, 'items');
    END IF;

    IF array_length(v_fields_changed, 1) IS NULL OR array_length(v_fields_changed, 1) = 0 THEN
        RETURN jsonb_build_object('ok', true, 'ma_phieu', v_ma_phieu,
                                   'message', 'Không có field nào thay đổi',
                                   'fields_changed', ARRAY[]::text[]);
    END IF;

    UPDATE phieu_sua_chua SET updated_at = now() WHERE ma_phieu = v_ma_phieu;

    SELECT * INTO v_new_phieu FROM phieu_sua_chua WHERE ma_phieu = v_ma_phieu;
    v_snapshot_after := jsonb_build_object(
        'header', to_jsonb(v_new_phieu),
        'items', COALESCE(
            (SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id)
             FROM phieu_sua_chua_chi_tiet ct WHERE ma_phieu = v_ma_phieu),
            '[]'::jsonb
        )
    );

    INSERT INTO admin_edit_history
        (table_name, record_id, snapshot_before, snapshot_after,
         fields_changed, edited_by_id, edited_by_name, edit_reason)
    VALUES
        ('phieu_sua_chua', v_ma_phieu, v_snapshot_before, v_snapshot_after,
         v_fields_changed, v_admin_id, v_admin_ho_ten, payload->>'edit_reason')
    RETURNING id INTO v_history_id;

    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        v_admin_username, v_admin_ho_ten, v_old_phieu.chi_nhanh,
        'ADMIN_SC_EDIT',
        format('ma=%s changed=[%s]%s reason=%s',
            v_ma_phieu, array_to_string(v_fields_changed, ','),
            v_log_detail, COALESCE(payload->>'edit_reason', '-')),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_phieu', v_ma_phieu,
        'fields_changed', v_fields_changed,
        'edit_history_id', v_history_id
    );
END;
$$;


-- ════════════════════════════════════════════════════════════
-- 3) _admin_check_can_edit_pdt
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION _admin_check_can_edit_pdt(p_ma_pdt text)
RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_pdt phieu_doi_tra_pos%ROWTYPE;
BEGIN
    SELECT * INTO v_pdt FROM phieu_doi_tra_pos WHERE ma_pdt = p_ma_pdt;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Phiếu đổi/trả không tồn tại');
    END IF;

    IF v_pdt.trang_thai != 'Hoàn thành' THEN
        RETURN jsonb_build_object('ok', false,
            'error', format('Phiếu trang_thai = %s, chỉ sửa được phiếu Hoàn thành',
                v_pdt.trang_thai));
    END IF;

    RETURN jsonb_build_object('ok', true, 'current_data', to_jsonb(v_pdt));
END;
$$;


-- ════════════════════════════════════════════════════════════
-- 4) sua_phieu_doi_tra_pos_admin
--   - LOCK: ma_pdt, trang_thai, nguoi_tao*, created_at, chi_nhanh, ma_hd_goc
--   - BLOCK: items_tra (per plan §0.2 — tránh đảo kho 2 chiều phức tạp)
--   - Editable: ten_khach, sdt_khach, ghi_chu, items_moi, PTTT
--   - items_moi pre-validate stock với net_diff (consistent B2a pattern)
-- ════════════════════════════════════════════════════════════
-- (Full source: see migration `admin_b2b_phase2_rpcs` in DB)
CREATE OR REPLACE FUNCTION sua_phieu_doi_tra_pos_admin(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_admin_id bigint;
    v_admin_username text;
    v_admin_ho_ten text;
    v_validate jsonb;
    v_check jsonb;
    v_ma_pdt text;
    v_old_pdt phieu_doi_tra_pos%ROWTYPE;
    v_new_pdt phieu_doi_tra_pos%ROWTYPE;
    v_snapshot_before jsonb;
    v_snapshot_after jsonb;
    v_fields_changed text[] := ARRAY[]::text[];
    v_log_detail text := '';
    v_chi_nhanh text;
    v_new_items_moi jsonb;
    v_new_item jsonb;
    v_diff_row RECORD;
    v_ma_hang text;
    v_so_luong int;
    v_don_gia int;
    v_ton_hien_tai int;
    v_loai_sp text;
    v_tien_hang_moi int := 0;
    v_tien_hang_tra int;
    v_chenh_lech int;
    v_tien_mat int;
    v_chuyen_khoan int;
    v_the int;
    v_history_id bigint;
BEGIN
    v_admin_id := (payload->>'admin_id')::bigint;
    SELECT username, ho_ten INTO v_admin_username, v_admin_ho_ten
    FROM nhan_vien WHERE id = v_admin_id;

    SELECT _admin_validate_request(v_admin_id, NULL) INTO v_validate;
    IF NOT (v_validate->>'ok')::boolean THEN RETURN v_validate; END IF;

    v_ma_pdt := payload->>'ma_pdt';
    IF v_ma_pdt IS NULL OR v_ma_pdt = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu ma_pdt');
    END IF;

    SELECT _admin_check_can_edit_pdt(v_ma_pdt) INTO v_check;
    IF NOT (v_check->>'ok')::boolean THEN RETURN v_check; END IF;

    SELECT * INTO v_old_pdt FROM phieu_doi_tra_pos WHERE ma_pdt = v_ma_pdt FOR UPDATE;
    v_chi_nhanh := v_old_pdt.chi_nhanh;

    v_snapshot_before := jsonb_build_object(
        'header', to_jsonb(v_old_pdt),
        'items', COALESCE(
            (SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id)
             FROM phieu_doi_tra_pos_ct ct WHERE ma_pdt = v_ma_pdt),
            '[]'::jsonb
        )
    );

    IF payload ? 'created_at' THEN RETURN jsonb_build_object('ok', false, 'error', 'created_at LOCKED'); END IF;
    IF payload ? 'chi_nhanh' THEN RETURN jsonb_build_object('ok', false, 'error', 'chi_nhanh LOCKED'); END IF;
    IF payload ? 'trang_thai' THEN RETURN jsonb_build_object('ok', false, 'error', 'trang_thai LOCKED'); END IF;
    IF payload ? 'nguoi_tao' OR payload ? 'nguoi_tao_id' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'nguoi_tao LOCKED');
    END IF;
    IF payload ? 'ma_hd_goc' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'ma_hd_goc LOCKED');
    END IF;
    IF payload ? 'ma_pdt_new' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'ma_pdt LOCKED');
    END IF;

    IF payload ? 'items_tra' THEN
        RETURN jsonb_build_object('ok', false,
            'error', 'items_tra BLOCKED. Nếu cần đổi → hủy phiếu rồi tạo lại.');
    END IF;

    IF payload ? 'items_moi' THEN
        v_new_items_moi := payload->'items_moi';

        FOR v_new_item IN SELECT * FROM jsonb_array_elements(v_new_items_moi) LOOP
            v_ma_hang := v_new_item->>'ma_hang';
            v_so_luong := (v_new_item->>'so_luong')::int;
            v_don_gia := (v_new_item->>'don_gia')::int;

            IF v_ma_hang IS NULL OR v_ma_hang = '' THEN
                RETURN jsonb_build_object('ok', false, 'error', 'items_moi thiếu ma_hang');
            END IF;
            IF v_so_luong <= 0 THEN
                RETURN jsonb_build_object('ok', false,
                    'error', format('items_moi %s: so_luong phải > 0', v_ma_hang));
            END IF;
            IF v_don_gia < 0 THEN
                RETURN jsonb_build_object('ok', false,
                    'error', format('items_moi %s: don_gia không được âm', v_ma_hang));
            END IF;
        END LOOP;

        FOR v_diff_row IN
            WITH old_q AS (
                SELECT ma_hang, SUM(so_luong)::int AS old_sl
                FROM phieu_doi_tra_pos_ct
                WHERE ma_pdt = v_ma_pdt AND kieu = 'moi'
                GROUP BY ma_hang
            ),
            new_q AS (
                SELECT (it->>'ma_hang') AS ma_hang,
                       SUM((it->>'so_luong')::int)::int AS new_sl
                FROM jsonb_array_elements(v_new_items_moi) it
                GROUP BY (it->>'ma_hang')
            )
            SELECT COALESCE(n.ma_hang, o.ma_hang) AS ma_hang,
                   COALESCE(n.new_sl, 0) - COALESCE(o.old_sl, 0) AS net_diff
            FROM new_q n
            FULL OUTER JOIN old_q o USING (ma_hang)
        LOOP
            IF v_diff_row.net_diff > 0 THEN
                SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
                FROM hang_hoa WHERE ma_hang = v_diff_row.ma_hang;
                IF v_loai_sp IS NULL THEN v_loai_sp := 'Hàng hóa'; END IF;

                IF v_loai_sp = 'Hàng hóa' THEN
                    SELECT COALESCE(SUM("Tồn cuối kì"), 0)::int INTO v_ton_hien_tai
                    FROM the_kho
                    WHERE "Mã hàng" = v_diff_row.ma_hang AND "Chi nhánh" = v_chi_nhanh;
                    IF v_ton_hien_tai < v_diff_row.net_diff THEN
                        RETURN jsonb_build_object('ok', false,
                            'error', format('items_moi %s không đủ tồn (có %s, cần thêm %s)',
                                v_diff_row.ma_hang, v_ton_hien_tai, v_diff_row.net_diff));
                    END IF;
                END IF;
            END IF;
        END LOOP;
    END IF;

    IF payload ? 'ten_khach' THEN
        IF v_old_pdt.ten_khach IS DISTINCT FROM (payload->>'ten_khach') THEN
            UPDATE phieu_doi_tra_pos SET ten_khach = payload->>'ten_khach'
            WHERE ma_pdt = v_ma_pdt;
            v_fields_changed := array_append(v_fields_changed, 'ten_khach');
        END IF;
    END IF;
    IF payload ? 'sdt_khach' THEN
        IF v_old_pdt.sdt_khach IS DISTINCT FROM (payload->>'sdt_khach') THEN
            UPDATE phieu_doi_tra_pos SET sdt_khach = payload->>'sdt_khach'
            WHERE ma_pdt = v_ma_pdt;
            v_fields_changed := array_append(v_fields_changed, 'sdt_khach');
        END IF;
    END IF;
    IF payload ? 'ghi_chu' THEN
        IF v_old_pdt.ghi_chu IS DISTINCT FROM (payload->>'ghi_chu') THEN
            UPDATE phieu_doi_tra_pos SET ghi_chu = payload->>'ghi_chu'
            WHERE ma_pdt = v_ma_pdt;
            v_fields_changed := array_append(v_fields_changed, 'ghi_chu');
        END IF;
    END IF;

    IF payload ? 'items_moi' THEN
        FOR v_diff_row IN
            SELECT ma_hang, so_luong FROM phieu_doi_tra_pos_ct
            WHERE ma_pdt = v_ma_pdt AND kieu = 'moi'
        LOOP
            SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
            FROM hang_hoa WHERE ma_hang = v_diff_row.ma_hang;
            IF COALESCE(v_loai_sp, 'Hàng hóa') = 'Hàng hóa' THEN
                UPDATE the_kho
                SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + v_diff_row.so_luong
                WHERE "Mã hàng" = v_diff_row.ma_hang AND "Chi nhánh" = v_chi_nhanh;
            END IF;
        END LOOP;

        DELETE FROM phieu_doi_tra_pos_ct WHERE ma_pdt = v_ma_pdt AND kieu = 'moi';

        v_tien_hang_moi := 0;
        FOR v_new_item IN SELECT * FROM jsonb_array_elements(v_new_items_moi) LOOP
            v_ma_hang := v_new_item->>'ma_hang';
            v_so_luong := (v_new_item->>'so_luong')::int;
            v_don_gia := (v_new_item->>'don_gia')::int;

            INSERT INTO phieu_doi_tra_pos_ct
                (ma_pdt, kieu, ma_hang, ten_hang, so_luong, don_gia, thanh_tien)
            VALUES
                (v_ma_pdt, 'moi', v_ma_hang, v_new_item->>'ten_hang',
                 v_so_luong, v_don_gia, v_so_luong * v_don_gia);

            SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
            FROM hang_hoa WHERE ma_hang = v_ma_hang;
            IF COALESCE(v_loai_sp, 'Hàng hóa') = 'Hàng hóa' THEN
                UPDATE the_kho
                SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) - v_so_luong
                WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
            END IF;

            v_tien_hang_moi := v_tien_hang_moi + (v_so_luong * v_don_gia);
        END LOOP;

        v_fields_changed := array_append(v_fields_changed, 'items_moi');
        v_log_detail := v_log_detail || format(' tien_hang_moi=%s→%s',
            v_old_pdt.tien_hang_moi, v_tien_hang_moi);
    ELSE
        v_tien_hang_moi := v_old_pdt.tien_hang_moi;
    END IF;

    v_tien_hang_tra := v_old_pdt.tien_hang_tra;
    v_chenh_lech := v_tien_hang_moi - v_tien_hang_tra;

    v_tien_mat := COALESCE((payload->>'tien_mat')::int, v_old_pdt.tien_mat);
    v_chuyen_khoan := COALESCE((payload->>'chuyen_khoan')::int, v_old_pdt.chuyen_khoan);
    v_the := COALESCE((payload->>'the')::int, v_old_pdt.the);

    IF v_chenh_lech > 0 THEN
        IF (v_tien_mat + v_chuyen_khoan + v_the) < v_chenh_lech THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Khách cần bù %s, mới nhập %s',
                    v_chenh_lech, v_tien_mat + v_chuyen_khoan + v_the));
        END IF;
    ELSIF v_chenh_lech < 0 THEN
        IF v_chuyen_khoan != 0 OR v_the != 0 THEN
            RETURN jsonb_build_object('ok', false,
                'error', 'Hoàn tiền cho khách: chỉ chấp nhận tiền mặt');
        END IF;
        IF v_tien_mat != v_chenh_lech THEN
            v_tien_mat := v_chenh_lech;
        END IF;
    ELSE
        v_tien_mat := 0; v_chuyen_khoan := 0; v_the := 0;
    END IF;

    UPDATE phieu_doi_tra_pos SET
        tien_hang_moi = v_tien_hang_moi,
        chenh_lech = v_chenh_lech,
        tien_mat = v_tien_mat,
        chuyen_khoan = v_chuyen_khoan,
        the = v_the
    WHERE ma_pdt = v_ma_pdt;

    IF v_old_pdt.tien_mat IS DISTINCT FROM v_tien_mat THEN
        v_fields_changed := array_append(v_fields_changed, 'tien_mat');
        v_log_detail := v_log_detail || format(' tien_mat=%s→%s', v_old_pdt.tien_mat, v_tien_mat);
    END IF;
    IF v_old_pdt.chuyen_khoan IS DISTINCT FROM v_chuyen_khoan THEN
        v_fields_changed := array_append(v_fields_changed, 'chuyen_khoan');
    END IF;
    IF v_old_pdt.the IS DISTINCT FROM v_the THEN
        v_fields_changed := array_append(v_fields_changed, 'the');
    END IF;
    IF v_old_pdt.chenh_lech IS DISTINCT FROM v_chenh_lech THEN
        v_fields_changed := array_append(v_fields_changed, 'chenh_lech');
    END IF;

    IF array_length(v_fields_changed, 1) IS NULL OR array_length(v_fields_changed, 1) = 0 THEN
        RETURN jsonb_build_object('ok', true, 'ma_pdt', v_ma_pdt,
                                   'message', 'Không có field nào thay đổi',
                                   'fields_changed', ARRAY[]::text[]);
    END IF;

    SELECT * INTO v_new_pdt FROM phieu_doi_tra_pos WHERE ma_pdt = v_ma_pdt;
    v_snapshot_after := jsonb_build_object(
        'header', to_jsonb(v_new_pdt),
        'items', COALESCE(
            (SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id)
             FROM phieu_doi_tra_pos_ct ct WHERE ma_pdt = v_ma_pdt),
            '[]'::jsonb
        )
    );

    INSERT INTO admin_edit_history
        (table_name, record_id, snapshot_before, snapshot_after,
         fields_changed, edited_by_id, edited_by_name, edit_reason)
    VALUES
        ('phieu_doi_tra_pos', v_ma_pdt, v_snapshot_before, v_snapshot_after,
         v_fields_changed, v_admin_id, v_admin_ho_ten, payload->>'edit_reason')
    RETURNING id INTO v_history_id;

    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        v_admin_username, v_admin_ho_ten, v_chi_nhanh,
        'ADMIN_PDT_EDIT',
        format('ma=%s changed=[%s]%s reason=%s',
            v_ma_pdt, array_to_string(v_fields_changed, ','),
            v_log_detail, COALESCE(payload->>'edit_reason', '-')),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_pdt', v_ma_pdt,
        'fields_changed', v_fields_changed,
        'chenh_lech', v_chenh_lech,
        'edit_history_id', v_history_id
    );
END;
$$;

-- ============================================================
-- Admin B1 — Phase 2 RPCs
-- Applied: 2026-05-08 via Supabase MCP migration `admin_b1_phase2_rpcs`
--
-- Helper: _admin_validate_request(p_admin_id, p_created_at) → jsonb
-- 1) tao_hoa_don_pos_admin(payload jsonb) → jsonb
-- 2) tao_phieu_doi_tra_pos_admin(payload jsonb) → jsonb
-- 3) tao_phieu_sua_chua_admin(payload jsonb) → jsonb
--
-- Decisions cho RPC #2 (đổi/trả admin):
--  - chi_nhanh = HĐ gốc (KHÔNG cho override — tránh corrupt kho cross-branch)
--  - Bypass 7-day age limit (admin override by design)
--  - GIỮ validate số_lượng_trả ≤ (đã bán − đã trả) — data integrity
--  - GIỮ stock check cho items_moi
-- ============================================================

-- ════════════════════════════════════════════════════════════
-- HELPER: _admin_validate_request
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION _admin_validate_request(
    p_admin_id bigint,
    p_created_at timestamp with time zone
) RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_role text;
    v_active boolean;
BEGIN
    SELECT role, active INTO v_role, v_active
    FROM nhan_vien WHERE id = p_admin_id;

    IF v_role IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Admin user không tồn tại');
    END IF;
    IF v_role != 'admin' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Permission denied: cần role admin');
    END IF;
    IF NOT v_active THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Admin user đã bị deactivate');
    END IF;

    IF p_created_at IS NOT NULL THEN
        IF p_created_at < now() - INTERVAL '90 days' THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Backdate vượt quá 90 ngày');
        END IF;
        IF p_created_at > now() + INTERVAL '5 minutes' THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Không cho tạo HĐ trong tương lai');
        END IF;
    END IF;

    RETURN jsonb_build_object('ok', true);
END;
$$;


-- ════════════════════════════════════════════════════════════
-- RPC 1: tao_hoa_don_pos_admin
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION tao_hoa_don_pos_admin(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_admin_id bigint;
    v_admin_username text;
    v_admin_ho_ten text;
    v_validate jsonb;
    v_created_at timestamp with time zone;
    v_chi_nhanh text;
    v_nguoi_ban_id bigint;
    v_nguoi_ban text;
    v_seq bigint;
    v_ma_hd text;
    v_items jsonb;
    v_item jsonb;
    v_ma_hang text;
    v_so_luong int;
    v_don_gia int;
    v_thanh_tien int;
    v_tong_tien_hang int := 0;
    v_giam_gia_don int := 0;
    v_khach_can_tra int := 0;
    v_ton_hien_tai int;
BEGIN
    -- 1. Admin info
    v_admin_id := (payload->>'admin_id')::bigint;
    SELECT username, ho_ten INTO v_admin_username, v_admin_ho_ten
    FROM nhan_vien WHERE id = v_admin_id;

    -- 2. created_at + validate (permission + backdate)
    v_created_at := COALESCE((payload->>'created_at')::timestamp with time zone, now());
    SELECT _admin_validate_request(v_admin_id, v_created_at) INTO v_validate;
    IF NOT (v_validate->>'ok')::boolean THEN
        RETURN v_validate;
    END IF;

    -- 3. Items không rỗng
    v_items := COALESCE(payload->'items', '[]'::jsonb);
    IF jsonb_array_length(v_items) = 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'HĐ phải có ít nhất 1 item');
    END IF;

    -- 4. chi_nhanh
    v_chi_nhanh := payload->>'chi_nhanh';
    IF v_chi_nhanh IS NULL OR v_chi_nhanh = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu chi_nhanh');
    END IF;

    -- 5. Lookup người bán
    v_nguoi_ban_id := (payload->>'nguoi_ban_id')::bigint;
    SELECT ho_ten INTO v_nguoi_ban FROM nhan_vien WHERE id = v_nguoi_ban_id;
    IF v_nguoi_ban IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'nguoi_ban_id không tồn tại');
    END IF;

    -- 6. Pre-validate items + tính tong_tien_hang
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items)
    LOOP
        v_ma_hang := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia := (v_item->>'don_gia')::int;

        IF v_so_luong <= 0 THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Item %s: so_luong phải > 0', v_ma_hang));
        END IF;
        IF v_don_gia < 0 THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Item %s: don_gia không được âm', v_ma_hang));
        END IF;

        IF NOT is_open_price_sql(v_ma_hang) THEN
            SELECT COALESCE(SUM("Tồn cuối kì"), 0) INTO v_ton_hien_tai
            FROM the_kho
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;

            IF v_ton_hien_tai < v_so_luong THEN
                RETURN jsonb_build_object('ok', false,
                    'error', format('Item %s không đủ tồn (có %s, cần %s)',
                        v_ma_hang, v_ton_hien_tai, v_so_luong));
            END IF;
        END IF;

        v_tong_tien_hang := v_tong_tien_hang + (v_so_luong * v_don_gia);
    END LOOP;

    -- 7. giam_gia_don + khach_can_tra
    v_giam_gia_don := COALESCE((payload->>'giam_gia_don')::int, 0);
    IF v_giam_gia_don < 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'giam_gia_don không được âm');
    END IF;
    IF v_giam_gia_don > v_tong_tien_hang THEN
        RETURN jsonb_build_object('ok', false,
            'error', format('giam_gia_don (%s) vượt quá tong_tien_hang (%s)',
                            v_giam_gia_don, v_tong_tien_hang));
    END IF;
    v_khach_can_tra := v_tong_tien_hang - v_giam_gia_don;

    -- 8. Sinh ma_hd
    v_seq := nextval('ahd_seq');
    v_ma_hd := 'AHD' || LPAD(v_seq::text, 6, '0');

    -- 9. Insert header
    INSERT INTO hoa_don_pos (
        ma_hd, chi_nhanh, ten_khach, sdt_khach,
        nguoi_ban, nguoi_ban_id,
        tien_mat, chuyen_khoan, the,
        tong_tien_hang, giam_gia_don, khach_can_tra,
        ghi_chu, trang_thai,
        is_admin_created, admin_note,
        created_at
    ) VALUES (
        v_ma_hd, v_chi_nhanh,
        payload->>'ten_khach', payload->>'sdt_khach',
        v_nguoi_ban, v_nguoi_ban_id,
        COALESCE((payload->>'tien_mat')::int, 0),
        COALESCE((payload->>'chuyen_khoan')::int, 0),
        COALESCE((payload->>'the')::int, 0),
        v_tong_tien_hang, v_giam_gia_don, v_khach_can_tra,
        payload->>'ghi_chu',
        'Hoàn thành',
        true, payload->>'admin_note',
        v_created_at
    );

    -- 10. Insert chi tiết + trừ kho
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items)
    LOOP
        v_ma_hang := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia := (v_item->>'don_gia')::int;
        v_thanh_tien := v_so_luong * v_don_gia;

        INSERT INTO hoa_don_pos_ct (
            ma_hd, ma_hang, ten_hang, so_luong, don_gia, thanh_tien
        ) VALUES (
            v_ma_hd, v_ma_hang,
            v_item->>'ten_hang',
            v_so_luong, v_don_gia, v_thanh_tien
        );

        IF NOT is_open_price_sql(v_ma_hang) THEN
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) - v_so_luong
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
        END IF;
    END LOOP;

    -- 11. Audit
    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        v_admin_username, v_admin_ho_ten, v_chi_nhanh,
        'ADMIN_HD_CREATE',
        format('ma=%s nguoi_ban=%s (id=%s) created_at=%s tong_hang=%s gg=%s can_tra=%s items=%s note=%s',
               v_ma_hd, v_nguoi_ban, v_nguoi_ban_id,
               v_created_at, v_tong_tien_hang, v_giam_gia_don, v_khach_can_tra,
               jsonb_array_length(v_items),
               COALESCE(payload->>'admin_note', '-')),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_hd', v_ma_hd,
        'tong_tien_hang', v_tong_tien_hang,
        'giam_gia_don', v_giam_gia_don,
        'khach_can_tra', v_khach_can_tra,
        'created_at', v_created_at
    );
END;
$$;


-- ════════════════════════════════════════════════════════════
-- RPC 2: tao_phieu_doi_tra_pos_admin
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION tao_phieu_doi_tra_pos_admin(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_admin_id       bigint;
    v_admin_username text;
    v_admin_ho_ten   text;
    v_validate       jsonb;
    v_created_at     timestamp with time zone;
    v_ma_hd_goc      text;
    v_chi_nhanh      text;
    v_hd_goc         hoa_don_pos%ROWTYPE;
    v_items_tra      jsonb;
    v_items_moi      jsonb;
    v_item           jsonb;
    v_ma_hang        text;
    v_so_luong       int;
    v_don_gia        int;
    v_loai_sp        text;
    v_ton_hien_tai   int;
    v_sl_da_ban      int;
    v_sl_da_tra      int;
    v_tong_tra       int := 0;
    v_tong_moi       int := 0;
    v_chenh_lech     int;
    v_tien_mat       int;
    v_chuyen_khoan   int;
    v_the            int;
    v_loai_phieu     text;
    v_seq            bigint;
    v_ma_pdt         text;
    v_nguoi_tao_id   bigint;
    v_nguoi_tao      text;
BEGIN
    v_admin_id := (payload->>'admin_id')::bigint;
    SELECT username, ho_ten INTO v_admin_username, v_admin_ho_ten
    FROM nhan_vien WHERE id = v_admin_id;

    v_created_at := COALESCE((payload->>'created_at')::timestamp with time zone, now());
    SELECT _admin_validate_request(v_admin_id, v_created_at) INTO v_validate;
    IF NOT (v_validate->>'ok')::boolean THEN
        RETURN v_validate;
    END IF;

    v_ma_hd_goc := payload->>'ma_hd_goc';
    IF v_ma_hd_goc IS NULL OR v_ma_hd_goc = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu ma_hd_goc');
    END IF;

    SELECT * INTO v_hd_goc FROM hoa_don_pos
    WHERE ma_hd = v_ma_hd_goc FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Không tìm thấy HĐ gốc');
    END IF;
    IF v_hd_goc.trang_thai = 'Đã hủy' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'HĐ gốc đã bị hủy');
    END IF;
    v_chi_nhanh := v_hd_goc.chi_nhanh;

    v_nguoi_tao_id := (payload->>'nguoi_tao_id')::bigint;
    SELECT ho_ten INTO v_nguoi_tao FROM nhan_vien WHERE id = v_nguoi_tao_id;
    IF v_nguoi_tao IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'nguoi_tao_id không tồn tại');
    END IF;

    v_items_tra := COALESCE(payload->'items_tra', '[]'::jsonb);
    v_items_moi := COALESCE(payload->'items_moi', '[]'::jsonb);

    IF jsonb_array_length(v_items_tra) = 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Phải có ít nhất 1 item trả');
    END IF;

    -- Validate items_tra: SL ≤ (đã bán - đã trả)
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items_tra)
    LOOP
        v_ma_hang  := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia  := (v_item->>'don_gia')::int;

        IF v_so_luong <= 0 THEN CONTINUE; END IF;
        IF v_don_gia < 0 THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Item trả %s: don_gia không được âm', v_ma_hang));
        END IF;

        SELECT COALESCE(SUM(so_luong), 0) INTO v_sl_da_ban
        FROM hoa_don_pos_ct
        WHERE ma_hd = v_ma_hd_goc AND ma_hang = v_ma_hang;

        IF v_sl_da_ban = 0 THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Sản phẩm %s không có trong HĐ gốc', v_ma_hang));
        END IF;

        SELECT COALESCE(SUM(ct.so_luong), 0) INTO v_sl_da_tra
        FROM phieu_doi_tra_pos_ct ct
        JOIN phieu_doi_tra_pos pdt ON pdt.ma_pdt = ct.ma_pdt
        WHERE pdt.ma_hd_goc = v_ma_hd_goc
          AND pdt.trang_thai = 'Hoàn thành'
          AND ct.kieu = 'tra'
          AND ct.ma_hang = v_ma_hang;

        IF v_so_luong > (v_sl_da_ban - v_sl_da_tra) THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('SP %s: chỉ còn %s có thể trả (đã bán %s, đã trả %s)',
                    v_ma_hang, v_sl_da_ban - v_sl_da_tra, v_sl_da_ban, v_sl_da_tra));
        END IF;

        v_tong_tra := v_tong_tra + (v_so_luong * v_don_gia);
    END LOOP;

    -- Validate items_moi: stock check cho Hàng hóa
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items_moi)
    LOOP
        v_ma_hang  := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia  := (v_item->>'don_gia')::int;

        IF v_so_luong <= 0 THEN CONTINUE; END IF;
        IF v_don_gia < 0 THEN
            RETURN jsonb_build_object('ok', false,
                'error', format('Item mới %s: don_gia không được âm', v_ma_hang));
        END IF;

        SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
        FROM hang_hoa WHERE ma_hang = v_ma_hang;
        IF v_loai_sp IS NULL THEN v_loai_sp := 'Hàng hóa'; END IF;

        IF v_loai_sp = 'Hàng hóa' THEN
            SELECT COALESCE(SUM("Tồn cuối kì"), 0) INTO v_ton_hien_tai
            FROM the_kho
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
            IF v_ton_hien_tai < v_so_luong THEN
                RETURN jsonb_build_object('ok', false,
                    'error', format('SP %s không đủ tồn (có %s, cần %s)',
                        v_ma_hang, v_ton_hien_tai, v_so_luong));
            END IF;
        END IF;

        v_tong_moi := v_tong_moi + (v_so_luong * v_don_gia);
    END LOOP;

    v_chenh_lech := v_tong_moi - v_tong_tra;
    IF v_tong_moi = 0 THEN
        v_loai_phieu := 'Trả';
    ELSIF v_chenh_lech = 0 THEN
        v_loai_phieu := 'Đổi ngang';
    ELSE
        v_loai_phieu := 'Đổi có chênh lệch';
    END IF;

    v_tien_mat     := COALESCE((payload->>'tien_mat')::int, 0);
    v_chuyen_khoan := COALESCE((payload->>'chuyen_khoan')::int, 0);
    v_the          := COALESCE((payload->>'the')::int, 0);

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

    v_seq := nextval('ahdd_seq');
    v_ma_pdt := 'AHDD' || LPAD(v_seq::text, 6, '0');

    INSERT INTO phieu_doi_tra_pos (
        ma_pdt, ma_hd_goc, chi_nhanh,
        ma_kh, ten_khach, sdt_khach,
        loai_phieu,
        tien_hang_tra, tien_hang_moi, chenh_lech,
        tien_mat, chuyen_khoan, the,
        trang_thai, nguoi_tao, nguoi_tao_id, ghi_chu,
        is_admin_created, admin_note,
        created_at
    ) VALUES (
        v_ma_pdt, v_ma_hd_goc, v_chi_nhanh,
        v_hd_goc.ma_kh, v_hd_goc.ten_khach, v_hd_goc.sdt_khach,
        v_loai_phieu,
        v_tong_tra, v_tong_moi, v_chenh_lech,
        v_tien_mat, v_chuyen_khoan, v_the,
        'Hoàn thành', v_nguoi_tao, v_nguoi_tao_id,
        payload->>'ghi_chu',
        true, payload->>'admin_note',
        v_created_at
    );

    -- Insert chi tiết + cộng/trừ kho
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items_tra)
    LOOP
        v_ma_hang  := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia  := (v_item->>'don_gia')::int;
        IF v_so_luong <= 0 THEN CONTINUE; END IF;

        INSERT INTO phieu_doi_tra_pos_ct (
            ma_pdt, kieu, ma_hang, ten_hang, so_luong, don_gia, thanh_tien
        ) VALUES (
            v_ma_pdt, 'tra', v_ma_hang,
            v_item->>'ten_hang',
            v_so_luong, v_don_gia, v_so_luong * v_don_gia
        );

        SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
        FROM hang_hoa WHERE ma_hang = v_ma_hang;

        IF COALESCE(v_loai_sp, 'Hàng hóa') = 'Hàng hóa' THEN
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) + v_so_luong
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
            IF NOT FOUND THEN
                INSERT INTO the_kho ("Mã hàng", "Chi nhánh", "Tồn cuối kì")
                VALUES (v_ma_hang, v_chi_nhanh, v_so_luong);
            END IF;
        END IF;
    END LOOP;

    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items_moi)
    LOOP
        v_ma_hang  := v_item->>'ma_hang';
        v_so_luong := (v_item->>'so_luong')::int;
        v_don_gia  := (v_item->>'don_gia')::int;
        IF v_so_luong <= 0 THEN CONTINUE; END IF;

        INSERT INTO phieu_doi_tra_pos_ct (
            ma_pdt, kieu, ma_hang, ten_hang, so_luong, don_gia, thanh_tien
        ) VALUES (
            v_ma_pdt, 'moi', v_ma_hang,
            v_item->>'ten_hang',
            v_so_luong, v_don_gia, v_so_luong * v_don_gia
        );

        SELECT COALESCE(loai_sp, 'Hàng hóa') INTO v_loai_sp
        FROM hang_hoa WHERE ma_hang = v_ma_hang;
        IF COALESCE(v_loai_sp, 'Hàng hóa') = 'Hàng hóa' THEN
            UPDATE the_kho
            SET "Tồn cuối kì" = COALESCE("Tồn cuối kì", 0) - v_so_luong
            WHERE "Mã hàng" = v_ma_hang AND "Chi nhánh" = v_chi_nhanh;
        END IF;
    END LOOP;

    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        v_admin_username, v_admin_ho_ten, v_chi_nhanh,
        'ADMIN_PDT_CREATE',
        format('ma=%s ma_hd_goc=%s nguoi_tao=%s (id=%s) created_at=%s loai=%s tra=%s moi=%s cl=%s note=%s',
               v_ma_pdt, v_ma_hd_goc, v_nguoi_tao, v_nguoi_tao_id,
               v_created_at, v_loai_phieu, v_tong_tra, v_tong_moi, v_chenh_lech,
               COALESCE(payload->>'admin_note', '-')),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_pdt', v_ma_pdt,
        'loai_phieu', v_loai_phieu,
        'tien_hang_tra', v_tong_tra,
        'tien_hang_moi', v_tong_moi,
        'chenh_lech', v_chenh_lech,
        'created_at', v_created_at
    );
END;
$$;


-- ════════════════════════════════════════════════════════════
-- RPC 3: tao_phieu_sua_chua_admin
-- KHÔNG đụng kho — items chỉ ghi nhận giá
-- ════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION tao_phieu_sua_chua_admin(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_admin_id       bigint;
    v_admin_username text;
    v_admin_ho_ten   text;
    v_validate       jsonb;
    v_created_at     timestamp with time zone;
    v_chi_nhanh      text;
    v_nguoi_tn_id    bigint;
    v_nguoi_tn       text;
    v_seq            bigint;
    v_ma_phieu       text;
    v_items          jsonb;
    v_item           jsonb;
BEGIN
    v_admin_id := (payload->>'admin_id')::bigint;
    SELECT username, ho_ten INTO v_admin_username, v_admin_ho_ten
    FROM nhan_vien WHERE id = v_admin_id;

    v_created_at := COALESCE((payload->>'created_at')::timestamp with time zone, now());
    SELECT _admin_validate_request(v_admin_id, v_created_at) INTO v_validate;
    IF NOT (v_validate->>'ok')::boolean THEN
        RETURN v_validate;
    END IF;

    v_chi_nhanh := payload->>'chi_nhanh';
    IF v_chi_nhanh IS NULL OR v_chi_nhanh = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Thiếu chi_nhanh');
    END IF;

    v_nguoi_tn_id := (payload->>'nguoi_tiep_nhan_id')::bigint;
    SELECT ho_ten INTO v_nguoi_tn FROM nhan_vien WHERE id = v_nguoi_tn_id;
    IF v_nguoi_tn IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'nguoi_tiep_nhan_id không tồn tại');
    END IF;

    v_seq := nextval('sc_seq');
    v_ma_phieu := 'SC' || LPAD(v_seq::text, 6, '0');

    INSERT INTO phieu_sua_chua (
        ma_phieu, chi_nhanh, ten_khach, sdt_khach,
        loai_yeu_cau, hieu_dong_ho, dac_diem, mo_ta_loi,
        khach_tra_truoc, ghi_chu_noi_bo, trang_thai,
        nguoi_tiep_nhan, ngay_tiep_nhan, ngay_hen_tra,
        created_by, created_by_id,
        is_admin_created, admin_note,
        created_at, updated_at
    ) VALUES (
        v_ma_phieu, v_chi_nhanh,
        payload->>'ten_khach', payload->>'sdt_khach',
        COALESCE(payload->>'loai_yeu_cau', 'Sửa chữa'),
        payload->>'hieu_dong_ho', payload->>'dac_diem', payload->>'mo_ta_loi',
        COALESCE((payload->>'khach_tra_truoc')::int, 0),
        payload->>'ghi_chu_noi_bo',
        COALESCE(payload->>'trang_thai', 'Đang sửa'),
        v_nguoi_tn, v_created_at,
        NULLIF(payload->>'ngay_hen_tra', '')::date,
        v_admin_username, v_admin_id,
        true, payload->>'admin_note',
        v_created_at, v_created_at
    );

    -- Items optional — chỉ ghi nhận giá, KHÔNG trừ kho
    v_items := COALESCE(payload->'items', '[]'::jsonb);
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_items)
    LOOP
        INSERT INTO phieu_sua_chua_chi_tiet (
            ma_phieu, loai_dong, ma_hang, ten_hang, so_luong, don_gia, ghi_chu
        ) VALUES (
            v_ma_phieu,
            COALESCE(v_item->>'loai_dong', 'Dịch vụ'),
            v_item->>'ma_hang',
            v_item->>'ten_hang',
            COALESCE((v_item->>'so_luong')::int, 1),
            COALESCE((v_item->>'don_gia')::int, 0),
            v_item->>'ghi_chu'
        );
    END LOOP;

    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        v_admin_username, v_admin_ho_ten, v_chi_nhanh,
        'ADMIN_SC_CREATE',
        format('ma=%s nguoi_tiep_nhan=%s (id=%s) created_at=%s items=%s note=%s',
               v_ma_phieu, v_nguoi_tn, v_nguoi_tn_id,
               v_created_at, jsonb_array_length(v_items),
               COALESCE(payload->>'admin_note', '-')),
        'warn'
    );

    RETURN jsonb_build_object(
        'ok', true,
        'ma_phieu', v_ma_phieu,
        'created_at', v_created_at,
        'items_count', jsonb_array_length(v_items)
    );
END;
$$;

-- ============================================================
-- Admin B2b — Phase 1: Generic loader refactor
-- Applied: 2026-05-09 via Supabase MCP migration `admin_b2b_phase1_generic_loader`
--
-- Drop B2a's load_hd_pos_with_history → replace với generic
-- load_record_with_history(table_name, record_id) hỗ trợ 3 tables:
--   hoa_don_pos / phieu_doi_tra_pos / phieu_sua_chua
-- ============================================================

DROP FUNCTION IF EXISTS load_hd_pos_with_history(text);

CREATE OR REPLACE FUNCTION load_record_with_history(
    p_table_name text,
    p_record_id text
)
RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_header jsonb;
    v_items jsonb;
    v_edit_count int;
    v_history jsonb;
BEGIN
    IF p_table_name NOT IN ('hoa_don_pos', 'phieu_doi_tra_pos', 'phieu_sua_chua') THEN
        RETURN jsonb_build_object('error', 'Invalid table_name');
    END IF;

    IF p_table_name = 'hoa_don_pos' THEN
        SELECT to_jsonb(h) INTO v_header FROM hoa_don_pos h WHERE ma_hd = p_record_id;
        SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id) INTO v_items
        FROM hoa_don_pos_ct ct WHERE ma_hd = p_record_id;
    ELSIF p_table_name = 'phieu_doi_tra_pos' THEN
        SELECT to_jsonb(p) INTO v_header FROM phieu_doi_tra_pos p WHERE ma_pdt = p_record_id;
        SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id) INTO v_items
        FROM phieu_doi_tra_pos_ct ct WHERE ma_pdt = p_record_id;
    ELSIF p_table_name = 'phieu_sua_chua' THEN
        SELECT to_jsonb(s) INTO v_header FROM phieu_sua_chua s WHERE ma_phieu = p_record_id;
        SELECT jsonb_agg(to_jsonb(ct) ORDER BY ct.id) INTO v_items
        FROM phieu_sua_chua_chi_tiet ct WHERE ma_phieu = p_record_id;
    END IF;

    SELECT COUNT(*) INTO v_edit_count FROM admin_edit_history
    WHERE table_name = p_table_name AND record_id = p_record_id;

    SELECT jsonb_agg(jsonb_build_object(
        'id', id,
        'edited_at', edited_at,
        'edited_by_name', edited_by_name,
        'fields_changed', fields_changed,
        'edit_reason', edit_reason
    ) ORDER BY edited_at DESC) INTO v_history
    FROM admin_edit_history
    WHERE table_name = p_table_name AND record_id = p_record_id;

    RETURN jsonb_build_object(
        'header', v_header,
        'items', COALESCE(v_items, '[]'::jsonb),
        'edit_count', v_edit_count,
        'edit_history', COALESCE(v_history, '[]'::jsonb)
    );
END;
$$;

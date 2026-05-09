-- ============================================================
-- Cleanup sc_seq drift + lưu trace
-- Applied: 2026-05-09 via Supabase MCP migration `sc_seq_drift_cleanup`
--
-- Bug: tab "Tạo phiếu mới" trong modules/sua_chua.py gọi
-- _gen_ma_phieu() = nextval('sc_seq') MỖI rerun để hiển thị mã dự kiến.
-- Streamlit re-runs script mỗi tương tác → consume sequence dù không insert.
-- Drift: max DB=345 nhưng sc_seq.last_value=368 → 23 số bỏ phí.
--
-- Fix Python (sua_chua.py): tab dùng helper mới _preview_next_ma_phieu()
-- (SELECT max+1, KHÔNG nextval). Submit vẫn dùng _gen_ma_phieu() để lấy
-- số thật từ sequence (atomic).
--
-- Migration này: RESTART sc_seq về (max+1) để phiếu kế tiếp có mã liền kề.
-- ============================================================

DO $$
DECLARE
    v_max int;
    v_next int;
BEGIN
    SELECT COALESCE(MAX(NULLIF(regexp_replace(ma_phieu, '^SC', ''), '')::int), 0)
    INTO v_max
    FROM phieu_sua_chua
    WHERE ma_phieu ~ '^SC[0-9]+$';
    v_next := v_max + 1;
    EXECUTE format('ALTER SEQUENCE sc_seq RESTART WITH %s', v_next);

    INSERT INTO action_logs (username, ho_ten, chi_nhanh, action, detail, level)
    VALUES (
        'audit_restore', 'Audit restore', '-',
        'SC_SEQ_DRIFT_CLEANUP',
        format('sc_seq RESTART WITH %s (max trong DB=%s). Nguyên nhân drift: '
               'tab Tạo phiếu gọi nextval mỗi rerun. Đã fix bằng preview helper.',
               v_next, v_max),
        'warn'
    );
END $$;

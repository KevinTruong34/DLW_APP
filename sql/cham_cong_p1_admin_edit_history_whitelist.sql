-- ============================================================
-- Phase 1 patch: mở rộng admin_edit_history.table_name CHECK whitelist
-- cho phép log audit cho attendance_sessions (RPC update_session_admin).
-- ============================================================

ALTER TABLE admin_edit_history DROP CONSTRAINT admin_edit_history_table_name_check;
ALTER TABLE admin_edit_history ADD CONSTRAINT admin_edit_history_table_name_check
  CHECK (table_name = ANY (ARRAY[
    'hoa_don_pos'::text,
    'phieu_doi_tra_pos'::text,
    'phieu_sua_chua'::text,
    'attendance_sessions'::text
  ]));

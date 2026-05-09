-- ============================================================
-- Admin B2a — Phase 1 Schema
-- Applied: 2026-05-09 via Supabase MCP migration `admin_b2a_phase1_schema`
--
-- Tạo bảng admin_edit_history (append-only audit snapshot).
-- Decisions:
--   edited_by_id BIGINT (consistent với pattern B1 nguoi_ban_id/nguoi_tao_id;
--   FK references nhan_vien.id integer — PG auto-cast).
-- ============================================================

CREATE TABLE admin_edit_history (
    id BIGSERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    snapshot_before JSONB NOT NULL,
    snapshot_after JSONB NOT NULL,
    fields_changed TEXT[] NOT NULL,
    edited_by_id BIGINT NOT NULL REFERENCES nhan_vien(id),
    edited_by_name TEXT NOT NULL,
    edit_reason TEXT,
    edited_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (table_name IN ('hoa_don_pos', 'phieu_doi_tra_pos', 'phieu_sua_chua'))
);

CREATE INDEX idx_aeh_record ON admin_edit_history(table_name, record_id);
CREATE INDEX idx_aeh_edited_at ON admin_edit_history(edited_at DESC);
CREATE INDEX idx_aeh_edited_by ON admin_edit_history(edited_by_id);

COMMENT ON TABLE admin_edit_history IS
'Audit log full snapshot before/after mỗi lần admin sửa HĐ/phiếu. Append-only — không bao giờ DELETE/UPDATE.';

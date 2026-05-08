-- ============================================================
-- Admin B1 — Phase 1 Schema
-- Applied: 2026-05-08 via Supabase MCP migration `admin_b1_phase1_schema`
--
-- 1) Cờ admin trên 3 bảng + admin_note + (sửa chữa) created_by_id
-- 2) Partial indexes (chỉ index khi cờ true)
-- 3) sc_seq (mới — phiếu sửa chữa) + wrapper next_sc_seq()
-- ============================================================

-- 1. ALTER TABLE: cờ admin
ALTER TABLE hoa_don_pos
    ADD COLUMN IF NOT EXISTS is_admin_created BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS admin_note TEXT;

ALTER TABLE phieu_doi_tra_pos
    ADD COLUMN IF NOT EXISTS is_admin_created BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS admin_note TEXT;

ALTER TABLE phieu_sua_chua
    ADD COLUMN IF NOT EXISTS is_admin_created BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS admin_note TEXT,
    ADD COLUMN IF NOT EXISTS created_by_id BIGINT;

-- 2. Partial indexes
CREATE INDEX IF NOT EXISTS idx_hd_pos_admin
    ON hoa_don_pos(is_admin_created) WHERE is_admin_created = true;
CREATE INDEX IF NOT EXISTS idx_pdt_pos_admin
    ON phieu_doi_tra_pos(is_admin_created) WHERE is_admin_created = true;
CREATE INDEX IF NOT EXISTS idx_sc_admin
    ON phieu_sua_chua(is_admin_created) WHERE is_admin_created = true;

-- 3. sc_seq START WITH (max+1) từ data hiện tại
DO $$
DECLARE
    v_max int;
BEGIN
    SELECT COALESCE(MAX(NULLIF(regexp_replace(ma_phieu, '^SC', ''), '')::int), 0)
    INTO v_max
    FROM phieu_sua_chua
    WHERE ma_phieu ~ '^SC[0-9]+$';

    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS sc_seq START WITH %s', v_max + 1);
END $$;

-- Wrapper RPC để Python gọi qua supabase.rpc()
CREATE OR REPLACE FUNCTION next_sc_seq()
RETURNS bigint
LANGUAGE sql
AS $$ SELECT nextval('sc_seq') $$;

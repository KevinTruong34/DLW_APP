-- ============================================================
-- Module Chấm công — Phase 1 Schema
-- Refs: PLAN_CHAM_CONG.md sections 4 + 6.2
-- Deviation: nhan_vien_id dùng INTEGER (khớp prod), không phải BIGINT trong plan.
-- ============================================================

-- 1. Extension
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- 2. shift_templates (lookup, seed 8 ca)
CREATE TABLE shift_templates (
    id            BIGSERIAL PRIMARY KEY,
    code          TEXT UNIQUE NOT NULL,
    branch_name   TEXT NOT NULL,
    label         TEXT NOT NULL,
    start_time    TIME NOT NULL,
    end_time      TIME NOT NULL,
    default_hours INT NOT NULL,
    is_technician BOOLEAN DEFAULT FALSE,
    active        BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT now()
);

INSERT INTO shift_templates (code, branch_name, label, start_time, end_time, default_hours, is_technician) VALUES
('lqd_morning',    '100 Lê Quý Đôn', 'Ca 1 (sáng)',  '07:00', '14:00', 7,  FALSE),
('lqd_afternoon',  '100 Lê Quý Đôn', 'Ca 2 (chiều)', '14:00', '21:00', 7,  FALSE),
('go_morning',     'GO BÀ RỊA',      'Ca 1 (sáng)',  '08:00', '15:00', 7,  FALSE),
('go_afternoon',   'GO BÀ RỊA',      'Ca 2 (chiều)', '15:00', '22:00', 7,  FALSE),
('coop_morning',   'Coop Vũng Tàu',  'Ca 1 (sáng)',  '08:00', '15:00', 7,  FALSE),
('coop_afternoon', 'Coop Vũng Tàu',  'Ca 2 (chiều)', '15:00', '22:00', 7,  FALSE),
('tech_lqd',       '100 Lê Quý Đôn', 'Ca KTV',       '07:00', '19:00', 12, TRUE),
('tech_go',        'GO BÀ RỊA',      'Ca KTV',       '07:00', '19:00', 12, TRUE);

-- 3. attendance_branch_networks (seed 3 CN)
CREATE TABLE attendance_branch_networks (
    id              BIGSERIAL PRIMARY KEY,
    branch_name     TEXT UNIQUE NOT NULL,
    ip_prefixes     TEXT[] NOT NULL DEFAULT '{}',
    updated_by      INTEGER REFERENCES nhan_vien(id),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

INSERT INTO attendance_branch_networks (branch_name, ip_prefixes) VALUES
('100 Lê Quý Đôn', '{}'),
('GO BÀ RỊA',      '{}'),
('Coop Vũng Tàu',  '{}');

-- 4. attendance_employee_rates
CREATE TABLE attendance_employee_rates (
    nhan_vien_id    INTEGER PRIMARY KEY REFERENCES nhan_vien(id),
    salary_type     TEXT NOT NULL CHECK (salary_type IN ('hourly','monthly_fixed')),
    hourly_rate     INT,
    monthly_fixed   INT,
    updated_by      INTEGER REFERENCES nhan_vien(id),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    CHECK (
        (salary_type = 'hourly' AND hourly_rate IS NOT NULL AND monthly_fixed IS NULL)
        OR
        (salary_type = 'monthly_fixed' AND monthly_fixed IS NOT NULL AND hourly_rate IS NULL)
    )
);

-- 5. attendance_work_schedules + anti-overlap exclusion
CREATE TABLE attendance_work_schedules (
    id                  BIGSERIAL PRIMARY KEY,
    nhan_vien_id        INTEGER NOT NULL REFERENCES nhan_vien(id),
    work_date           DATE NOT NULL,
    shift_template_id   BIGINT NOT NULL REFERENCES shift_templates(id),
    scheduled_start_at  TIMESTAMPTZ NOT NULL,
    scheduled_end_at    TIMESTAMPTZ NOT NULL,
    status              TEXT NOT NULL DEFAULT 'scheduled'
                        CHECK (status IN ('scheduled','cancelled','leave_paid','leave_unpaid')),
    note                TEXT,
    created_by          INTEGER REFERENCES nhan_vien(id),
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (nhan_vien_id, work_date, shift_template_id)
);

CREATE INDEX idx_schedules_date ON attendance_work_schedules(work_date);
CREATE INDEX idx_schedules_nv_date ON attendance_work_schedules(nhan_vien_id, work_date);

ALTER TABLE attendance_work_schedules
ADD CONSTRAINT no_overlap_per_nv EXCLUDE USING GIST (
    nhan_vien_id WITH =,
    tstzrange(scheduled_start_at, scheduled_end_at) WITH &&
) WHERE (status = 'scheduled');

-- 6. attendance_events (raw log từ POS)
CREATE TABLE attendance_events (
    id              BIGSERIAL PRIMARY KEY,
    nhan_vien_id    INTEGER NOT NULL REFERENCES nhan_vien(id),
    schedule_id     BIGINT REFERENCES attendance_work_schedules(id),
    event_type      TEXT NOT NULL CHECK (event_type IN ('IN','OUT')),
    event_time      TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL DEFAULT 'POS',
    ip_address      TEXT,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_events_nv_time ON attendance_events(nhan_vien_id, event_time DESC);
CREATE INDEX idx_events_schedule ON attendance_events(schedule_id);

-- 7. attendance_sessions (derived từ events)
CREATE TABLE attendance_sessions (
    id                   BIGSERIAL PRIMARY KEY,
    nhan_vien_id         INTEGER NOT NULL REFERENCES nhan_vien(id),
    schedule_id          BIGINT NOT NULL UNIQUE REFERENCES attendance_work_schedules(id),
    check_in_at          TIMESTAMPTZ,
    check_out_at         TIMESTAMPTZ,
    actual_check_in_at   TIMESTAMPTZ,
    actual_check_out_at  TIMESTAMPTZ,
    is_late              BOOLEAN DEFAULT FALSE,
    late_minutes         INT DEFAULT 0,
    worked_minutes       INT DEFAULT 0,
    regular_minutes      INT DEFAULT 0,
    ot_minutes           INT DEFAULT 0,
    is_auto_checkout     BOOLEAN DEFAULT FALSE,
    status               TEXT NOT NULL DEFAULT 'open'
                         CHECK (status IN ('open','completed','auto_closed','absent','edited')),
    note                 TEXT,
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_sessions_nv_date ON attendance_sessions(nhan_vien_id, actual_check_in_at DESC);

-- 8. attendance_payroll_periods
CREATE TABLE attendance_payroll_periods (
    id              BIGSERIAL PRIMARY KEY,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    label           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','finalized')),
    created_by      INTEGER REFERENCES nhan_vien(id),
    finalized_by    INTEGER REFERENCES nhan_vien(id),
    finalized_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    CHECK (end_date >= start_date)
);

-- 9. attendance_payroll_items
CREATE TABLE attendance_payroll_items (
    id                  BIGSERIAL PRIMARY KEY,
    period_id           BIGINT NOT NULL REFERENCES attendance_payroll_periods(id),
    nhan_vien_id        INTEGER NOT NULL REFERENCES nhan_vien(id),
    session_id          BIGINT REFERENCES attendance_sessions(id),
    work_date           DATE,
    shift_template_id   BIGINT REFERENCES shift_templates(id),
    worked_minutes      INT DEFAULT 0,
    ot_minutes          INT DEFAULT 0,
    rate_snapshot       INT NOT NULL,
    salary_amount       INT NOT NULL,
    item_type           TEXT NOT NULL CHECK (item_type IN ('shift','monthly_fixed','leave_paid')),
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_payroll_items_period_nv ON attendance_payroll_items(period_id, nhan_vien_id);

-- 10. attendance_adjustments
CREATE TABLE attendance_adjustments (
    id                  BIGSERIAL PRIMARY KEY,
    period_id           BIGINT NOT NULL REFERENCES attendance_payroll_periods(id),
    nhan_vien_id        INTEGER NOT NULL REFERENCES nhan_vien(id),
    adjustment_type     TEXT NOT NULL CHECK (adjustment_type IN
                        ('bonus_holiday','allowance_meal','penalty','other')),
    amount              INT NOT NULL,
    note                TEXT,
    created_by          INTEGER REFERENCES nhan_vien(id),
    created_at          TIMESTAMPTZ DEFAULT now()
);

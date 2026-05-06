-- Attendance schema for DLW App
-- Run this once in Supabase SQL editor.

create table if not exists public.attendance_employee_rates (
    id bigserial primary key,
    nhan_vien_id bigint not null unique,
    hourly_rate numeric(12,2) not null default 0,
    updated_by text,
    updated_at timestamptz not null default now()
);

create table if not exists public.attendance_branch_networks (
    id bigserial primary key,
    branch_name text not null unique,
    wifi_name text,
    ip_prefixes text,
    updated_by text,
    updated_at timestamptz not null default now()
);

create table if not exists public.attendance_work_schedules (
    id bigserial primary key,
    nhan_vien_id bigint not null,
    work_date date not null,
    branch_name text not null,
    shift_no smallint not null,
    shift_name text,
    scheduled_start_at timestamptz not null,
    scheduled_end_at timestamptz not null,
    status text not null default 'active',
    note text,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint attendance_work_schedules_unique unique (nhan_vien_id, work_date, branch_name, shift_no)
);

create index if not exists idx_attendance_work_schedules_work_date on public.attendance_work_schedules (work_date);
create index if not exists idx_attendance_work_schedules_employee on public.attendance_work_schedules (nhan_vien_id);
create index if not exists idx_attendance_work_schedules_branch on public.attendance_work_schedules (branch_name);

create table if not exists public.attendance_events (
    id bigserial primary key,
    nhan_vien_id bigint not null,
    work_date date not null,
    branch_name text not null,
    shift_no smallint not null,
    shift_name text,
    event_type text not null check (event_type in ('IN', 'OUT')),
    event_time timestamptz not null,
    source text,
    schedule_id bigint,
    wifi_name text,
    ip_address text,
    note text,
    created_at timestamptz not null default now()
);

create index if not exists idx_attendance_events_work_date on public.attendance_events (work_date);
create index if not exists idx_attendance_events_employee on public.attendance_events (nhan_vien_id);
create index if not exists idx_attendance_events_branch on public.attendance_events (branch_name);
create index if not exists idx_attendance_events_time on public.attendance_events (event_time desc);

create table if not exists public.attendance_sessions (
    id bigserial primary key,
    nhan_vien_id bigint not null,
    work_date date not null,
    branch_name text not null,
    shift_no smallint not null,
    shift_name text,
    schedule_id bigint,
    scheduled_start_at timestamptz not null,
    scheduled_end_at timestamptz not null,
    check_in_at timestamptz not null,
    check_out_at timestamptz,
    actual_check_in_at timestamptz,
    actual_check_out_at timestamptz,
    worked_minutes integer not null default 0,
    regular_minutes integer not null default 0,
    ot_minutes integer not null default 0,
    is_auto_checkout boolean not null default false,
    status text not null default 'open',
    note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint attendance_sessions_unique unique (nhan_vien_id, work_date, branch_name, shift_no)
);

create index if not exists idx_attendance_sessions_work_date on public.attendance_sessions (work_date);
create index if not exists idx_attendance_sessions_employee on public.attendance_sessions (nhan_vien_id);
create index if not exists idx_attendance_sessions_branch on public.attendance_sessions (branch_name);
create index if not exists idx_attendance_sessions_status on public.attendance_sessions (status);

create table if not exists public.attendance_payroll_periods (
    id bigserial primary key,
    start_date date not null,
    end_date date not null,
    label text,
    status text not null default 'open',
    updated_at timestamptz not null default now()
);

create table if not exists public.attendance_payroll_items (
    id bigserial primary key,
    period_id bigint not null,
    nhan_vien_id bigint not null,
    session_id bigint,
    work_date date not null,
    branch_name text not null,
    shift_no smallint not null,
    shift_name text,
    worked_minutes integer not null default 0,
    ot_minutes integer not null default 0,
    hourly_rate numeric(12,2) not null default 0,
    salary_amount numeric(12,2) not null default 0,
    created_at timestamptz not null default now()
);

create index if not exists idx_attendance_payroll_items_period on public.attendance_payroll_items (period_id);
create index if not exists idx_attendance_payroll_items_employee on public.attendance_payroll_items (nhan_vien_id);

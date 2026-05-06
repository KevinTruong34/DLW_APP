from __future__ import annotations

from datetime import date, timedelta, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from utils.auth import is_ke_toan_or_admin, get_user, get_active_branch
from utils.config import ALL_BRANCHES, CN_SHORT
from utils.db import supabase, log_action
from utils.helpers import today_vn, now_vn
from utils.attendance import (
    load_nhan_vien_directory,
    load_work_schedules,
    upsert_work_schedule,
    load_attendance_sessions,
    load_attendance_events,
    upsert_branch_network,
    load_branch_networks,
    create_payroll_period,
    load_payroll_periods,
    compute_payroll_period,
    save_payroll_items,
)
from utils.attendance_edit import update_attendance_session

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _fmt(dt):
    try:
        return dt.astimezone(TZ).strftime("%H:%M")
    except Exception:
        return ""


def _branch_options() -> list[str]:
    return list(ALL_BRANCHES)


@st.cache_data(ttl=120)
def _load_active_employees() -> pd.DataFrame:
    return load_nhan_vien_directory(active_only=True)


def _employee_label(row: pd.Series) -> str:
    name = str(row.get("ho_ten") or row.get("username") or "").strip()
    role = str(row.get("role") or "")
    return f"{name} · {role}" if role else name


def _resolve_employee_id(df: pd.DataFrame, label: str) -> int | None:
    if df.empty or not label:
        return None
    matches = df[df.apply(lambda r: _employee_label(r) == label, axis=1)]
    if matches.empty:
        return None
    return int(matches.iloc[0]["id"])


def _employee_map_all() -> dict:
    df = load_nhan_vien_directory(active_only=False)
    if df.empty:
        return {}
    return {int(r.get("id")): (r.get("ho_ten") or r.get("username")) for _, r in df.iterrows()}


def _load_employee_map() -> pd.DataFrame:
    df = _load_active_employees()
    if df.empty:
        return df
    cols = [c for c in ["id", "username", "ho_ten", "role", "active", "hourly_rate"] if c in df.columns]
    return df[cols].copy()


def _summary_cards(df: pd.DataFrame):
    if df.empty:
        st.info("Chưa có dữ liệu.")
        return
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Số ca", len(df))
    with c2:
        st.metric("Tổng phút", int(pd.to_numeric(df.get("worked_minutes"), errors="coerce").fillna(0).sum()))
    with c3:
        st.metric("Tổng OT", int(pd.to_numeric(df.get("ot_minutes"), errors="coerce").fillna(0).sum()))
    with c4:
        if "salary_amount" in df.columns:
            st.metric("Tổng lương", f"{int(pd.to_numeric(df['salary_amount'], errors='coerce').fillna(0).sum()):,}".replace(",", "."))
        else:
            st.metric("Tổng lương", "—")


def _render_schedule_tab():
    st.subheader("Phân lịch làm việc")

    employees = _load_employee_map()
    if employees.empty:
        st.warning("Chưa có nhân viên active.")
        return

    branch_list = _branch_options()
    emp_labels = [_employee_label(r) for _, r in employees.iterrows()]

    with st.form("schedule_form", clear_on_submit=True, border=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            emp_label = st.selectbox("Nhân viên", emp_labels)
            work_day = st.date_input("Ngày làm", value=today_vn())
        with c2:
            branch_name = st.selectbox("Chi nhánh", branch_list)
            shift_no = st.selectbox("Ca", [1, 2], format_func=lambda x: "Ca 1 (sáng)" if x == 1 else "Ca 2 (chiều)")
        with c3:
            note = st.text_input("Ghi chú", placeholder="Tùy chọn")
            created_by = (get_user() or {}).get("ho_ten", "")

        submitted = st.form_submit_button("Lưu lịch", type="primary")
        if submitted:
            emp_id = _resolve_employee_id(employees, emp_label)
            if not emp_id:
                st.error("Không xác định được nhân viên.")
            else:
                res = upsert_work_schedule(
                    employee_id=emp_id,
                    work_date=work_day,
                    branch_name=branch_name,
                    shift_no=int(shift_no),
                    created_by=created_by,
                    note=note,
                )
                if res.get("ok"):
                    log_action("ATTENDANCE_SCHEDULE_UPSERT", f"emp_id={emp_id} date={work_day} branch={branch_name} shift={shift_no}")
                    st.success("Đã lưu lịch làm việc.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(res.get("error", "Lỗi không xác định"))

    st.markdown("---")
    c1, c2 = st.columns([1, 2])
    with c1:
        view_day = st.date_input("Xem lịch ngày", value=today_vn(), key="view_schedule_day")
    with c2:
        view_branch = st.selectbox("Lọc chi nhánh", ["Tất cả"] + branch_list, key="view_schedule_branch")

    df = load_work_schedules(work_date=view_day)
    if not df.empty:
        emp_map = _employee_map_all()
        df_disp = df.copy()
        df_disp["nhan_vien"] = df_disp["nhan_vien_id"].map(emp_map)
        df_disp["start"] = df_disp["scheduled_start_at"].apply(_fmt)
        df_disp["end"] = df_disp["scheduled_end_at"].apply(_fmt)
        st.dataframe(df_disp[["nhan_vien","branch_name","shift_no","start","end","work_date"]], use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có lịch cho ngày này.")

    st.markdown("---")
    st.caption("Cấu hình Wi-Fi cửa hàng để khóa chấm công.")
    with st.form("network_form", clear_on_submit=True, border=False):
        n1, n2, n3 = st.columns(3)
        with n1:
            net_branch = st.selectbox("Chi nhánh", branch_list, key="net_branch")
        with n2:
            wifi_name = st.text_input("SSID Wi-Fi", placeholder="Tên Wi-Fi")
        with n3:
            ip_prefixes = st.text_input("IP prefix", placeholder="Ví dụ: 192.168.1.,10.0.0.")
        if st.form_submit_button("Lưu cấu hình mạng", type="primary"):
            res = upsert_branch_network(net_branch, wifi_name=wifi_name, ip_prefixes=ip_prefixes, updated_by=(get_user() or {}).get("ho_ten", ""))
            if res.get("ok"):
                log_action("ATTENDANCE_NETWORK_UPSERT", f"branch={net_branch}")
                st.success("Đã lưu cấu hình mạng.")
                st.cache_data.clear()
            else:
                st.error(res.get("error", "Lỗi không xác định"))

    net_df = load_branch_networks()
    if not net_df.empty:
        st.dataframe(net_df, use_container_width=True, hide_index=True)


def _render_timesheet_tab():
    st.subheader("Bảng công")
    branch_list = _branch_options()
    employees = _load_employee_map()
    emp_labels = ["Tất cả"] + ([_employee_label(r) for _, r in employees.iterrows()] if not employees.empty else [])

    c1, c2, c3 = st.columns(3)
    with c1:
        from_day = st.date_input("Từ ngày", value=today_vn() - timedelta(days=7), key="timesheet_from")
    with c2:
        to_day = st.date_input("Đến ngày", value=today_vn(), key="timesheet_to")
    with c3:
        branch_filter = st.selectbox("Chi nhánh", ["Tất cả"] + branch_list, key="timesheet_branch")

    emp_filter = st.selectbox("Nhân viên", emp_labels, key="timesheet_emp")

    df = load_attendance_sessions()
    if df.empty:
        st.info("Chưa có dữ liệu chấm công.")
        return

    if "work_date" in df.columns:
        df["work_date"] = pd.to_datetime(df["work_date"], errors="coerce").dt.date
        df = df[(df["work_date"] >= from_day) & (df["work_date"] <= to_day)]
    if branch_filter != "Tất cả":
        df = df[df["branch_name"] == branch_filter]
    if emp_filter != "Tất cả":
        emp_id = _resolve_employee_id(employees, emp_filter)
        if emp_id is not None:
            df = df[df["nhan_vien_id"] == emp_id]

    if df.empty:
        st.info("Không có bản ghi trong khoảng thời gian này.")
        return

    _summary_cards(df)

    emp_map = _employee_map_all()
    df_disp = df.copy()
    df_disp["nhan_vien"] = df_disp["nhan_vien_id"].map(emp_map)
    df_disp["in"] = df_disp["check_in_at"].apply(_fmt)
    df_disp["out"] = df_disp["check_out_at"].apply(_fmt)

    st.dataframe(df_disp[["nhan_vien","work_date","branch_name","shift_no","in","out","worked_minutes","ot_minutes"]], use_container_width=True, hide_index=True)

    # ===== EDIT ATTENDANCE (unchanged) =====
    with st.expander("Sửa công"):
        if "id" not in df.columns:
            st.info("Không có dữ liệu để sửa")
        else:
            df_sorted = df.sort_values(["work_date", "nhan_vien_id", "shift_no"]) if all(c in df.columns for c in ["work_date","nhan_vien_id","shift_no"]) else df

            def _label(idx):
                r = df_sorted.loc[idx]
                return f"#{r.get('id')} | {r.get('work_date')} | ca {r.get('shift_no')}"

            selected_idx = st.selectbox("Chọn dòng công", options=df_sorted.index.tolist(), format_func=_label)
            row = df_sorted.loc[selected_idx]

            work_day = row.get("work_date")
            if isinstance(work_day, pd.Timestamp):
                work_day = work_day.date()

            in_dt = row.get("check_in_at")
            out_dt = row.get("check_out_at") or row.get("scheduled_end_at")

            in_time = pd.to_datetime(in_dt).time() if pd.notna(in_dt) else time(7, 0)
            out_time = pd.to_datetime(out_dt).time() if pd.notna(out_dt) else time(14, 0)

            ed_day = st.date_input("Ngày", value=work_day)
            ed_in = st.time_input("Giờ vào", value=in_time)
            ed_out = st.time_input("Giờ ra", value=out_time)
            ed_note = st.text_input("Ghi chú", value=str(row.get("note") or ""))

            if st.button("Lưu sửa công"):
                if ed_out <= ed_in:
                    st.error("Giờ ra phải lớn hơn giờ vào")
                else:
                    new_in = datetime.combine(ed_day, ed_in, tzinfo=TZ)
                    new_out = datetime.combine(ed_day, ed_out, tzinfo=TZ)
                    res = update_attendance_session(int(row.get("id")), new_in, new_out, ed_note)
                    if res.get("ok"):
                        st.success("Đã cập nhật chấm công")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(res.get("error", "Lỗi không xác định"))

    with st.expander("Xem log chấm công thô"):
        events = load_attendance_events()
        if not events.empty and "work_date" in events.columns:
            events["work_date"] = pd.to_datetime(events["work_date"], errors="coerce").dt.date
            events = events[(events["work_date"] >= from_day) & (events["work_date"] <= to_day)]
        if branch_filter != "Tất cả" and not events.empty:
            events = events[events["branch_name"] == branch_filter]
        if emp_filter != "Tất cả" and not events.empty:
            emp_id = _resolve_employee_id(employees, emp_filter)
            if emp_id is not None:
                events = events[events["nhan_vien_id"] == emp_id]
        st.dataframe(events, use_container_width=True, hide_index=True)

# rest unchanged

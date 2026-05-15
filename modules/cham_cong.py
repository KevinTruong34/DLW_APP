"""Module Chấm công nhân viên — DLW Phase 2.

Phase 2 deliver: 2 outer tabs trong "👥 Nhân viên":
  - ⚙️ Cấu hình: 3 sub-tabs (Mạng cửa hàng / Lương NV / Ca làm việc)
  - 📅 Lịch làm việc: calendar tuần + CRUD schedule

Phase 4+ sẽ thêm: 📊 Bảng công, ✏️ Sửa công, 💰 Tính lương, 📥 Export.

Refs: PLAN_CHAM_CONG.md section 7 + D17 (CRUD shift_templates).
"""
from __future__ import annotations

import streamlit as st
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from utils.auth import is_admin, is_ke_toan_or_admin, get_user
from utils.config import ALL_BRANCHES
from utils.db import (
    supabase, log_action,
    load_all_nhan_vien,
    load_shift_templates, load_branch_networks, load_employee_rates,
    count_schedules_using_template, load_schedules_for_week,
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DOW_VN = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def module_cham_cong():
    """Entry: menu '👥 Nhân viên' cho admin + kế toán."""
    if not is_ke_toan_or_admin():
        st.error("⛔ Tính năng này dành cho admin và kế toán.")
        return

    st.title("👥 Nhân viên")

    tabs = st.tabs([
        "⚙️ Cấu hình",
        "📅 Lịch làm việc",
    ])
    with tabs[0]:
        _render_config()
    with tabs[1]:
        _render_schedule()


# ============================================================
# ⚙️ CẤU HÌNH — admin only
# ============================================================

def _render_config():
    if not is_admin():
        st.info("ℹ️ Chỉ admin được cấu hình. Bạn có thể xem ở tab Lịch.")
        return

    st.subheader("Cấu hình hệ thống chấm công")
    sub = st.tabs([
        "🌐 Mạng cửa hàng",
        "💵 Lương nhân viên",
        "⏰ Ca làm việc",
    ])
    with sub[0]:
        _config_branch_networks()
    with sub[1]:
        _config_employee_rates()
    with sub[2]:
        _config_shift_templates()


def _config_branch_networks():
    """Set ip_prefixes per CN."""
    st.markdown("##### 🌐 Cấu hình IP whitelist cho từng chi nhánh")
    st.caption(
        "Lấy IP public từ `whatismyip.com` khi đang dùng Wi-Fi cửa hàng. "
        "Nhập 3 số đầu + dấu chấm, vd `113.161.74.`. Mỗi prefix 1 dòng."
    )

    networks = load_branch_networks()
    user = get_user()

    for cn in ALL_BRANCHES:
        with st.container(border=True):
            st.markdown(f"**{cn}**")
            current = networks.get(cn, [])
            current_text = "\n".join(current)

            new_text = st.text_area(
                "IP prefixes (mỗi dòng 1 prefix)",
                value=current_text,
                key=f"cc_net_{cn}",
                height=80,
                placeholder="113.161.74.\n14.225.10.",
                label_visibility="collapsed",
            )

            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("💾 Lưu", key=f"cc_net_save_{cn}", type="primary"):
                    new_prefixes = [
                        line.strip() for line in new_text.split("\n")
                        if line.strip()
                    ]
                    try:
                        supabase.table("attendance_branch_networks").update({
                            "ip_prefixes": new_prefixes,
                            "updated_by": user["id"],
                            "updated_at": datetime.now(VN_TZ).isoformat(),
                        }).eq("branch_name", cn).execute()
                        log_action("ATT_BRANCH_NET_UPDATE",
                                   f"{cn}: {len(new_prefixes)} prefix(es)")
                        load_branch_networks.clear()
                        st.toast(f"✓ Đã lưu IP cho {cn}", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
            with col2:
                if current:
                    st.caption(f"Hiện có: {', '.join(current)}")
                else:
                    st.caption("⚠️ Chưa cấu hình → NV không chấm công được")


def _config_employee_rates():
    """Set salary_type + rate per NV."""
    st.markdown("##### 💵 Cấu hình lương theo nhân viên")
    st.caption("Lương theo giờ (hourly) hoặc cố định tháng (monthly_fixed).")

    nv_list = load_all_nhan_vien(include_inactive=False)
    rates = load_employee_rates()
    user = get_user()

    role_filter = st.selectbox(
        "Lọc theo vai trò",
        ["Tất cả", "admin", "ke_toan", "nhan_vien"],
        key="cc_rate_role_filter",
    )
    if role_filter != "Tất cả":
        nv_list = [n for n in nv_list if n.get("role") == role_filter]

    if not nv_list:
        st.info("Không có NV phù hợp.")
        return

    for nv in nv_list:
        nv_id = nv["id"]
        nv_name = nv["ho_ten"]
        nv_role = nv.get("role", "")
        rate = rates.get(nv_id)

        if rate:
            stype = rate.get("salary_type", "")
            if stype == "hourly":
                badge = f"⏰ {int(rate.get('hourly_rate') or 0):,}đ/giờ"
            else:
                badge = f"📅 {int(rate.get('monthly_fixed') or 0):,}đ/tháng"
        else:
            badge = "⚠️ Chưa cấu hình"

        with st.expander(f"**{nv_name}** ({nv_role}) — {badge}"):
            stype_now = (rate or {}).get("salary_type", "hourly")
            stype = st.radio(
                "Loại lương",
                ["hourly", "monthly_fixed"],
                index=0 if stype_now == "hourly" else 1,
                format_func=lambda x: "⏰ Theo giờ" if x == "hourly" else "📅 Cố định tháng",
                key=f"cc_rate_type_{nv_id}",
                horizontal=True,
            )

            if stype == "hourly":
                hourly_val = st.number_input(
                    "Đơn giá (đ/giờ)",
                    min_value=0, step=1000,
                    value=int((rate or {}).get("hourly_rate") or 0),
                    key=f"cc_rate_hourly_{nv_id}",
                )
                fixed_val = None
            else:
                fixed_val = st.number_input(
                    "Lương cố định (đ/tháng)",
                    min_value=0, step=100000,
                    value=int((rate or {}).get("monthly_fixed") or 0),
                    key=f"cc_rate_fixed_{nv_id}",
                )
                hourly_val = None

            if st.button("💾 Lưu", key=f"cc_rate_save_{nv_id}", type="primary"):
                if stype == "hourly" and (not hourly_val or hourly_val <= 0):
                    st.error("Đơn giá phải > 0")
                    return
                if stype == "monthly_fixed" and (not fixed_val or fixed_val <= 0):
                    st.error("Lương cố định phải > 0")
                    return
                try:
                    payload = {
                        "nhan_vien_id": nv_id,
                        "salary_type": stype,
                        "hourly_rate": hourly_val if stype == "hourly" else None,
                        "monthly_fixed": fixed_val if stype == "monthly_fixed" else None,
                        "updated_by": user["id"],
                        "updated_at": datetime.now(VN_TZ).isoformat(),
                    }
                    if rate:
                        supabase.table("attendance_employee_rates") \
                            .update(payload).eq("nhan_vien_id", nv_id).execute()
                    else:
                        supabase.table("attendance_employee_rates") \
                            .insert(payload).execute()
                    log_action("ATT_RATE_UPDATE",
                               f"NV {nv_name}: {stype}={hourly_val or fixed_val}")
                    load_employee_rates.clear()
                    st.toast(f"✓ Đã lưu lương {nv_name}", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")


def _config_shift_templates():
    """CRUD shift_templates với lock fields nếu có schedule ref. D17."""
    st.markdown("##### ⏰ Ca làm việc")
    st.caption(
        "Admin tạo/sửa ca. Ca đã có schedule ref → không sửa được giờ/CN "
        "(tạo ca mới + disable ca cũ nếu cần đổi)."
    )

    col_filter, col_show, col_add = st.columns([2, 2, 1])
    with col_filter:
        cn_filter = st.selectbox(
            "Chi nhánh",
            ["Tất cả"] + ALL_BRANCHES,
            key="cc_shift_cn_filter",
        )
    with col_show:
        show_inactive = st.checkbox(
            "Hiện cả ca đã ẩn", value=False, key="cc_shift_show_inactive"
        )
    with col_add:
        st.write("")
        if st.button("➕ Thêm ca", key="cc_shift_add_btn", use_container_width=True):
            _shift_add_dialog()

    templates = load_shift_templates(include_inactive=show_inactive)
    if cn_filter != "Tất cả":
        templates = [t for t in templates if t.get("branch_name") == cn_filter]

    if not templates:
        st.info("Chưa có ca làm việc nào.")
        return

    for t in templates:
        ref_count = count_schedules_using_template(t["id"])
        active = t.get("active", True)
        is_tech = t.get("is_technician", False)
        loai_lbl = "KTV" if is_tech else "NV"
        active_badge = "✅" if active else "⛔"

        with st.container(border=True):
            col_info, col_meta, col_act = st.columns([3, 2, 1])
            with col_info:
                st.markdown(
                    f"**{t['code']}** — {t['label']}  \n"
                    f"📍 {t['branch_name']} · ⏰ {t['start_time'][:5]}–{t['end_time'][:5]} "
                    f"({t['default_hours']}h) · {loai_lbl}"
                )
            with col_meta:
                st.caption(
                    f"{active_badge} {'Active' if active else 'Đã ẩn'} · "
                    f"📋 {ref_count} schedule ref"
                )
            with col_act:
                if st.button("✏️ Sửa", key=f"cc_shift_edit_{t['id']}",
                             use_container_width=True):
                    _shift_edit_dialog(t, ref_count)


@st.dialog("➕ Thêm ca làm việc")
def _shift_add_dialog():
    code = st.text_input(
        "Code (snake_case, unique)", placeholder="vd: tech_coop",
        key="cc_shift_new_code"
    )
    branch = st.selectbox("Chi nhánh", ALL_BRANCHES, key="cc_shift_new_branch")
    label = st.text_input(
        "Label hiển thị", placeholder="vd: Ca KTV Coop",
        key="cc_shift_new_label"
    )

    col1, col2 = st.columns(2)
    with col1:
        start_t = st.time_input("Giờ bắt đầu", value=time(7, 0),
                                key="cc_shift_new_start")
    with col2:
        end_t = st.time_input("Giờ kết thúc", value=time(14, 0),
                              key="cc_shift_new_end")

    is_tech = st.checkbox("Ca KTV (kỹ thuật viên)", key="cc_shift_new_tech")

    s_min = start_t.hour * 60 + start_t.minute
    e_min = end_t.hour * 60 + end_t.minute
    if e_min > s_min:
        default_hours = round((e_min - s_min) / 60)
        st.caption(f"⏱ Tự động: **{default_hours} giờ**")
        valid_time = True
    else:
        default_hours = 0
        st.error("Giờ kết thúc phải sau giờ bắt đầu (v1 chưa hỗ trợ ca qua đêm)")
        valid_time = False

    if st.button("💾 Tạo ca", type="primary", use_container_width=True,
                 disabled=not (code.strip() and label.strip() and valid_time)):
        code_clean = code.strip()
        check = supabase.table("shift_templates").select("id") \
            .eq("code", code_clean).execute()
        if check.data:
            st.error(f"Code '{code_clean}' đã tồn tại. Chọn code khác.")
            return
        try:
            supabase.table("shift_templates").insert({
                "code": code_clean,
                "branch_name": branch,
                "label": label.strip(),
                "start_time": start_t.strftime("%H:%M:%S"),
                "end_time": end_t.strftime("%H:%M:%S"),
                "default_hours": default_hours,
                "is_technician": is_tech,
                "active": True,
            }).execute()
            log_action("ATT_SHIFT_TEMPLATE_CREATE",
                       f"{code_clean} ({branch} {start_t}-{end_t})")
            load_shift_templates.clear()
            st.toast(f"✓ Đã tạo ca {code_clean}", icon="✅")
            st.rerun()
        except Exception as e:
            st.error(f"Lỗi: {e}")


@st.dialog("✏️ Sửa ca làm việc")
def _shift_edit_dialog(template: dict, ref_count: int):
    t_id = template["id"]
    has_refs = ref_count > 0

    st.markdown(f"**Code:** `{template['code']}` (không sửa được)")
    if has_refs:
        st.warning(
            f"⚠️ Ca này đã có **{ref_count} schedule ref**. "
            "Không thể đổi giờ/chi nhánh/loại. Tạo ca mới + disable ca này nếu cần đổi."
        )

    label = st.text_input("Label", value=template["label"],
                          key=f"cc_shift_edit_label_{t_id}")

    branch_idx = (ALL_BRANCHES.index(template["branch_name"])
                  if template.get("branch_name") in ALL_BRANCHES else 0)
    branch = st.selectbox(
        "Chi nhánh", ALL_BRANCHES,
        index=branch_idx,
        disabled=has_refs,
        key=f"cc_shift_edit_branch_{t_id}",
    )

    col1, col2 = st.columns(2)
    with col1:
        start_t = st.time_input(
            "Giờ bắt đầu",
            value=datetime.strptime(template["start_time"][:5], "%H:%M").time(),
            disabled=has_refs,
            key=f"cc_shift_edit_start_{t_id}",
        )
    with col2:
        end_t = st.time_input(
            "Giờ kết thúc",
            value=datetime.strptime(template["end_time"][:5], "%H:%M").time(),
            disabled=has_refs,
            key=f"cc_shift_edit_end_{t_id}",
        )

    is_tech = st.checkbox(
        "Ca KTV", value=template.get("is_technician", False),
        disabled=has_refs,
        key=f"cc_shift_edit_tech_{t_id}",
    )
    active = st.checkbox(
        "Active (uncheck = ẩn ca khỏi UI xếp lịch)",
        value=template.get("active", True),
        key=f"cc_shift_edit_active_{t_id}",
    )

    s_min = start_t.hour * 60 + start_t.minute
    e_min = end_t.hour * 60 + end_t.minute
    default_hours = (round((e_min - s_min) / 60) if e_min > s_min
                     else template.get("default_hours", 0))

    if st.button("💾 Lưu", type="primary", use_container_width=True,
                 disabled=not label.strip(),
                 key=f"cc_shift_edit_save_{t_id}"):
        try:
            payload = {
                "label": label.strip(),
                "active": active,
            }
            if not has_refs:
                payload.update({
                    "branch_name": branch,
                    "start_time": start_t.strftime("%H:%M:%S"),
                    "end_time": end_t.strftime("%H:%M:%S"),
                    "default_hours": default_hours,
                    "is_technician": is_tech,
                })
            supabase.table("shift_templates").update(payload) \
                .eq("id", t_id).execute()
            log_action("ATT_SHIFT_TEMPLATE_EDIT",
                       f"id={t_id} active={active} label={label!r}")
            load_shift_templates.clear()
            st.toast(f"✓ Đã cập nhật ca {template['code']}", icon="✅")
            st.rerun()
        except Exception as e:
            st.error(f"Lỗi: {e}")


# ============================================================
# 📅 LỊCH LÀM VIỆC
# ============================================================

def _get_week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _render_schedule():
    today = datetime.now(VN_TZ).date()

    col_date, col_branch, col_copy = st.columns([2, 2, 2])
    with col_date:
        anchor_date = st.date_input(
            "Chọn ngày (lấy tuần chứa)",
            value=today,
            key="cc_sched_anchor",
        )
    monday = _get_week_monday(anchor_date)
    sunday = monday + timedelta(days=6)

    with col_branch:
        cn_filter = st.selectbox(
            "Chi nhánh",
            ["Tất cả"] + ALL_BRANCHES,
            key="cc_sched_cn_filter",
        )
    with col_copy:
        st.write("")
        if is_admin():
            if st.button("📋 Copy tuần trước", key="cc_sched_copy_btn",
                         use_container_width=True):
                _copy_previous_week(
                    monday,
                    branch=None if cn_filter == "Tất cả" else cn_filter,
                )

    st.caption(
        f"📅 Tuần: **{monday.strftime('%d/%m')} → {sunday.strftime('%d/%m/%Y')}**"
    )

    branch_arg = None if cn_filter == "Tất cả" else cn_filter
    schedules = load_schedules_for_week(monday, branch=branch_arg)

    by_date: dict[date, list] = {monday + timedelta(days=i): [] for i in range(7)}
    for s in schedules:
        try:
            wd = datetime.strptime(s["work_date"], "%Y-%m-%d").date()
            if wd in by_date:
                by_date[wd].append(s)
        except Exception:
            continue

    cols = st.columns(7)
    for i, col in enumerate(cols):
        d = monday + timedelta(days=i)
        is_today = (d == today)
        with col:
            day_lbl = f"{DOW_VN[i]} {d.day}/{d.month}"
            if is_today:
                st.markdown(
                    f"<div style='font-weight:700;color:#e63946;'>{day_lbl} (hôm nay)</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"<div style='font-weight:600;'>{day_lbl}</div>",
                    unsafe_allow_html=True
                )

            day_scheds = sorted(
                by_date.get(d, []),
                key=lambda s: s.get("scheduled_start_at") or ""
            )
            for s in day_scheds:
                _render_schedule_chip(s)

            if is_admin():
                if st.button("➕", key=f"cc_sched_add_{d.isoformat()}",
                             use_container_width=True,
                             help=f"Thêm lịch {d.strftime('%d/%m')}"):
                    _schedule_add_dialog(d)


def _render_schedule_chip(s: dict):
    tmpl = s.get("shift_templates") or {}
    nv = s.get("nhan_vien") or {}
    nv_name = nv.get("ho_ten", "?")
    status = s.get("status", "scheduled")

    label = tmpl.get("label", "?")

    status_lbl = {
        "scheduled": "",
        "leave_paid": " 🌴",
        "leave_unpaid": " ⚪",
    }.get(status, "")

    btn_label = f"{nv_name} · {label}{status_lbl}"

    if st.button(btn_label, key=f"cc_chip_{s['id']}",
                 use_container_width=True,
                 help=f"{tmpl.get('branch_name','')} · {tmpl.get('start_time','')[:5]}–{tmpl.get('end_time','')[:5]}"):
        _schedule_edit_dialog(s)


@st.dialog("➕ Thêm lịch làm việc")
def _schedule_add_dialog(work_date: date):
    user = get_user()
    nv_list = load_all_nhan_vien(include_inactive=False)
    templates = load_shift_templates(include_inactive=False)

    if not templates:
        st.error("Chưa có ca làm việc nào active. Tạo ca trước trong Cấu hình > Ca làm việc.")
        return

    st.markdown(f"**Ngày:** {work_date.strftime('%d/%m/%Y')}")

    nv_options = {f"{n['ho_ten']} ({n.get('role','')})": n["id"] for n in nv_list}
    nv_label = st.selectbox("Nhân viên", list(nv_options.keys()),
                            key=f"cc_sched_new_nv_{work_date.isoformat()}")
    nv_id = nv_options[nv_label]

    tmpl_options = {
        f"{t['branch_name']} — {t['label']} ({t['start_time'][:5]}-{t['end_time'][:5]})": t
        for t in templates
    }
    tmpl_label = st.selectbox("Ca làm việc", list(tmpl_options.keys()),
                              key=f"cc_sched_new_tmpl_{work_date.isoformat()}")
    tmpl = tmpl_options[tmpl_label]

    status = st.selectbox(
        "Trạng thái",
        ["scheduled", "leave_paid", "leave_unpaid"],
        format_func=lambda s: {
            "scheduled": "✅ Xếp lịch",
            "leave_paid": "🌴 Nghỉ phép có lương",
            "leave_unpaid": "⚪ Nghỉ không lương",
        }[s],
        key=f"cc_sched_new_status_{work_date.isoformat()}",
    )
    note = st.text_area("Ghi chú (optional)", height=60,
                        key=f"cc_sched_new_note_{work_date.isoformat()}")

    if st.button("💾 Tạo lịch", type="primary", use_container_width=True,
                 key=f"cc_sched_new_save_{work_date.isoformat()}"):
        start_dt = datetime.combine(
            work_date,
            datetime.strptime(tmpl["start_time"][:5], "%H:%M").time(),
            tzinfo=VN_TZ,
        )
        end_dt = datetime.combine(
            work_date,
            datetime.strptime(tmpl["end_time"][:5], "%H:%M").time(),
            tzinfo=VN_TZ,
        )

        if status == "scheduled":
            err = _check_overlap(nv_id, start_dt, end_dt, exclude_schedule_id=None)
            if err:
                st.error(err)
                return

        try:
            supabase.table("attendance_work_schedules").insert({
                "nhan_vien_id": nv_id,
                "work_date": work_date.isoformat(),
                "shift_template_id": tmpl["id"],
                "scheduled_start_at": start_dt.isoformat(),
                "scheduled_end_at": end_dt.isoformat(),
                "status": status,
                "note": note or None,
                "created_by": user["id"],
            }).execute()
            log_action("ATT_SCHEDULE_CREATE",
                       f"NV {nv_id} {work_date} ca {tmpl['code']} status={status}")
            st.toast("✓ Đã tạo lịch", icon="✅")
            st.rerun()
        except Exception as e:
            msg = str(e)
            if "no_overlap_per_nv" in msg or "exclusion" in msg.lower():
                st.error("Lịch overlap với ca khác của NV này. Kiểm tra lại giờ.")
            elif "unique" in msg.lower() or "duplicate" in msg.lower():
                st.error("NV đã có ca này trong ngày.")
            else:
                st.error(f"Lỗi: {e}")


@st.dialog("✏️ Sửa lịch làm việc")
def _schedule_edit_dialog(schedule: dict):
    tmpl = schedule.get("shift_templates") or {}
    nv = schedule.get("nhan_vien") or {}
    s_id = schedule["id"]

    st.markdown(
        f"**NV:** {nv.get('ho_ten','?')}  \n"
        f"**Ngày:** {schedule.get('work_date','?')}  \n"
        f"**Ca:** {tmpl.get('label','?')} "
        f"({tmpl.get('start_time','')[:5]}-{tmpl.get('end_time','')[:5]} · "
        f"{tmpl.get('branch_name','')})"
    )

    statuses = ["scheduled", "cancelled", "leave_paid", "leave_unpaid"]
    current_status = schedule.get("status", "scheduled")
    if current_status not in statuses:
        current_status = "scheduled"

    status = st.selectbox(
        "Trạng thái",
        statuses,
        index=statuses.index(current_status),
        format_func=lambda s: {
            "scheduled": "✅ Xếp lịch",
            "cancelled": "❌ Hủy lịch",
            "leave_paid": "🌴 Nghỉ phép có lương",
            "leave_unpaid": "⚪ Nghỉ không lương",
        }[s],
        key=f"cc_sched_edit_status_{s_id}",
        disabled=not is_admin(),
    )
    note = st.text_area(
        "Ghi chú",
        value=schedule.get("note") or "",
        height=60,
        key=f"cc_sched_edit_note_{s_id}",
        disabled=not is_admin(),
    )

    if is_admin():
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Lưu", type="primary", use_container_width=True,
                         key=f"cc_sched_edit_save_{s_id}"):
                try:
                    supabase.table("attendance_work_schedules").update({
                        "status": status,
                        "note": note or None,
                        "updated_at": datetime.now(VN_TZ).isoformat(),
                    }).eq("id", s_id).execute()
                    log_action("ATT_SCHEDULE_EDIT", f"id={s_id} status={status}")
                    st.toast("✓ Đã cập nhật", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")
        with col2:
            if st.button("🗑 Xóa lịch", use_container_width=True,
                         key=f"cc_sched_edit_del_{s_id}"):
                try:
                    supabase.table("attendance_work_schedules") \
                        .delete().eq("id", s_id).execute()
                    log_action("ATT_SCHEDULE_DELETE", f"id={s_id}")
                    st.toast("✓ Đã xóa lịch", icon="🗑")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")
    else:
        st.caption("ℹ️ Chỉ admin được sửa/xóa lịch.")


def _check_overlap(nv_id: int, start_dt: datetime, end_dt: datetime,
                   exclude_schedule_id: int | None = None) -> str | None:
    """Pre-check overlap trong Python — error rõ ràng trước khi DB constraint reject."""
    lo = (start_dt - timedelta(hours=24)).isoformat()
    hi = (end_dt + timedelta(hours=24)).isoformat()
    res = supabase.table("attendance_work_schedules").select(
        "id, scheduled_start_at, scheduled_end_at, shift_templates(label)"
    ).eq("nhan_vien_id", nv_id).eq("status", "scheduled") \
     .gte("scheduled_start_at", lo).lte("scheduled_start_at", hi).execute()

    for r in res.data or []:
        if exclude_schedule_id and r["id"] == exclude_schedule_id:
            continue
        try:
            rs = datetime.fromisoformat(r["scheduled_start_at"])
            re_ = datetime.fromisoformat(r["scheduled_end_at"])
        except Exception:
            continue
        if start_dt < re_ and end_dt > rs:
            lbl = (r.get("shift_templates") or {}).get("label", "?")
            return (
                f"NV đã có ca **{lbl}** từ "
                f"{rs.astimezone(VN_TZ).strftime('%d/%m %H:%M')} đến "
                f"{re_.astimezone(VN_TZ).strftime('%H:%M')} — overlap"
            )
    return None


def _copy_previous_week(target_monday: date, branch: str | None = None):
    """Copy scheduled lịch tuần trước → tuần này. Skip cancelled/leave_*/trùng/lỗi."""
    user = get_user()
    prev_monday = target_monday - timedelta(days=7)
    src_schedules = load_schedules_for_week(prev_monday, branch=branch)
    src_schedules = [s for s in src_schedules if s.get("status") == "scheduled"]

    if not src_schedules:
        st.toast("⚠️ Tuần trước không có lịch scheduled nào", icon="⚠️")
        return

    created = 0
    skipped = 0
    for s in src_schedules:
        try:
            wd_old = datetime.strptime(s["work_date"], "%Y-%m-%d").date()
            offset = (wd_old - prev_monday).days
            wd_new = target_monday + timedelta(days=offset)

            tmpl = s.get("shift_templates") or {}
            if not tmpl or not tmpl.get("active", True):
                skipped += 1
                continue

            start_dt = datetime.combine(
                wd_new,
                datetime.strptime(tmpl["start_time"][:5], "%H:%M").time(),
                tzinfo=VN_TZ,
            )
            end_dt = datetime.combine(
                wd_new,
                datetime.strptime(tmpl["end_time"][:5], "%H:%M").time(),
                tzinfo=VN_TZ,
            )

            supabase.table("attendance_work_schedules").insert({
                "nhan_vien_id": s["nhan_vien_id"],
                "work_date": wd_new.isoformat(),
                "shift_template_id": s["shift_template_id"],
                "scheduled_start_at": start_dt.isoformat(),
                "scheduled_end_at": end_dt.isoformat(),
                "status": "scheduled",
                "created_by": user["id"],
            }).execute()
            created += 1
        except Exception:
            skipped += 1

    log_action("ATT_SCHEDULE_COPY_WEEK",
               f"{prev_monday}→{target_monday}: {created} OK, {skipped} skipped")
    st.toast(f"✓ Copy: {created} lịch (skip {skipped} trùng/lỗi)", icon="✅")
    st.rerun()

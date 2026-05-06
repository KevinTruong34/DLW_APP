from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from utils.attendance import calc_minutes, get_shift_window, CLOSED
from utils.db import supabase
from utils.helpers import now_vn_iso

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(TZ) if value.tzinfo else value.replace(tzinfo=TZ)
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        dt = ts.to_pydatetime()
        return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)
    except Exception:
        return None


def update_attendance_session(
    session_id: int,
    check_in_at: datetime,
    check_out_at: datetime | None,
    note: str = "",
) -> dict[str, Any]:
    try:
        res = supabase.table("attendance_sessions").select("*").eq("id", session_id).limit(1).execute()
        session = res.data[0] if res.data else None
        if not session:
            return {"ok": False, "error": "Không tìm thấy phiên chấm công"}

        branch_name = str(session.get("branch_name") or "").strip()
        work_date_raw = session.get("work_date")
        shift_no = int(session.get("shift_no") or 0)
        shift_start = _to_dt(session.get("scheduled_start_at"))
        shift_end = _to_dt(session.get("scheduled_end_at"))

        if shift_start is None or shift_end is None:
            work_date = pd.to_datetime(work_date_raw, errors="coerce")
            if pd.isna(work_date):
                return {"ok": False, "error": "Thiếu dữ liệu ca chấm công"}
            window = get_shift_window(branch_name, work_date.date(), shift_no)
            if not window:
                return {"ok": False, "error": "Không tìm thấy khung ca"}
            shift_start, shift_end = window

        final_out = check_out_at or shift_end
        calc = calc_minutes(check_in_at, final_out, shift_start, shift_end)

        payload = {
            "check_in_at": check_in_at.isoformat(),
            "check_out_at": final_out.isoformat(),
            "actual_check_in_at": calc["actual_check_in"].isoformat() if calc["actual_check_in"] else check_in_at.isoformat(),
            "actual_check_out_at": calc["actual_check_out"].isoformat() if calc["actual_check_out"] else final_out.isoformat(),
            "worked_minutes": int(calc["worked_minutes"]),
            "regular_minutes": int(calc["regular_minutes"]),
            "ot_minutes": int(calc["ot_minutes"]),
            "status": CLOSED,
            "is_auto_checkout": False,
            "note": note or session.get("note"),
            "updated_at": now_vn_iso(),
        }
        out = supabase.table("attendance_sessions").update(payload).eq("id", session_id).execute()
        return {"ok": True, "data": out.data or []}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

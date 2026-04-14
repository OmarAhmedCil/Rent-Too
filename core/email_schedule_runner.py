"""
Run due rows in ``email_schedules`` (weekly payment CSV + payment reminders).

The Streamlit app only saves schedules; it does not run a background timer.
Run this module on an OS scheduler (e.g. every 5 minutes):

  cd /path/to/Contract\\ tool
  python -m core.email_schedule_runner

Uses the same SMTP and CSV logic as the in-app test sends.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, time, timedelta
from typing import Any

import pandas as pd

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_SEL_LABEL = {"all": "All Contracts", "selected": "Select Contracts", "filtered": "Filter by Type"}


def _coerce_time(val) -> time | None:
    if val is None:
        return None
    if isinstance(val, time):
        return val
    if isinstance(val, timedelta):
        sec = int(val.total_seconds()) % 86400
        h, r = divmod(sec, 3600)
        m, s = divmod(r, 60)
        return time(h, m, s)
    if isinstance(val, str) and val.strip():
        parts = val.strip().split(":")
        try:
            return time(
                int(parts[0]),
                int(parts[1]) if len(parts) > 1 else 0,
                int(parts[2]) if len(parts) > 2 else 0,
            )
        except ValueError:
            return None
    return None


def _parse_recipients(raw: str) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    parts = re.split(r"[\n,;]+", str(raw))
    email_re = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    out = []
    for p in parts:
        e = p.strip()
        if e and email_re.match(e):
            out.append(e)
    return out


def _same_iso_week(a: datetime, b: datetime) -> bool:
    def iw(dt):
        return dt.isocalendar()[0], dt.isocalendar()[1]

    return iw(a) == iw(b)


def _last_sent_dt(last_sent) -> datetime | None:
    if last_sent is None:
        return None
    try:
        return pd.to_datetime(last_sent).to_pydatetime()
    except Exception:
        return None


def _due_this_slot(
    *,
    schedule_type: str,
    day_of_week: str | None,
    send_time_raw: Any,
    now: datetime,
    last_sent_at: Any,
) -> bool:
    st_t = _coerce_time(send_time_raw)
    if st_t is None:
        return False

    if schedule_type == "weekly_payment":
        dow = (day_of_week or "").strip()
        if not dow:
            return False
        if dow != _DAYS[now.weekday()]:
            return False
    elif schedule_type == "contract_reminder":
        dow = (day_of_week or "").strip()
        if dow and dow != _DAYS[now.weekday()]:
            return False
    else:
        return False

    slot_start = datetime.combine(now.date(), st_t)
    delta = (now - slot_start).total_seconds()
    if delta < 0 or delta >= 900:
        return False

    ls = _last_sent_dt(last_sent_at)
    if ls is None:
        return True

    if schedule_type == "weekly_payment":
        if _same_iso_week(ls, now):
            return False
    else:
        if ls.date() == now.date():
            return False

    return True


def _contracts_lookup_df():
    from core.db import execute_query

    rows = execute_query("SELECT id, contract_name FROM contracts", fetch=True)
    if not rows:
        return pd.DataFrame(columns=["id", "contract_name"])
    return pd.DataFrame(rows)


def run_due_email_schedules(now: datetime | None = None) -> int:
    from core.db import get_email_schedules, mark_email_schedule_sent
    from tabs.email_notifications import (
        _calendar_week_range_containing,
        _email_html_reminder_body,
        _email_html_weekly_body,
        _html_include_contracts_scope,
        _reminder_payments_export_csv,
        _reminder_payments_summary_html,
        get_payments_csv_for_week,
        get_upcoming_payments_for_reminder_window,
        send_email_via_smtp,
    )

    now = now or datetime.now()
    schedules = get_email_schedules(is_active=True) or []
    if not schedules:
        print("No active email schedules.")
        return 0

    contracts_df = _contracts_lookup_df()
    sent = 0

    for row in schedules:
        sid = row.get("id")
        stype = row.get("schedule_type") or ""
        if not _due_this_slot(
            schedule_type=stype,
            day_of_week=row.get("day_of_week"),
            send_time_raw=row.get("send_time"),
            now=now,
            last_sent_at=row.get("last_sent_at"),
        ):
            continue

        recipients = _parse_recipients(row.get("recipients") or "")
        if not recipients:
            print(f"Schedule {sid}: no valid recipients, skip.")
            continue

        cst = row.get("contract_selection_type") or "all"
        contract_selection = _SEL_LABEL.get(cst, "All Contracts")
        ids_raw = row.get("selected_contract_ids") or ""
        types_raw = row.get("contract_types") or ""
        selected_ids = [x.strip() for x in str(ids_raw).split(",") if str(x).strip()]
        ctypes = [x.strip() for x in str(types_raw).split(",") if str(x).strip()]

        if cst == "selected" and not selected_ids:
            print(f"Schedule {sid}: contract scope is 'selected' but no IDs, skip.")
            continue
        if cst == "filtered" and not ctypes:
            print(f"Schedule {sid}: contract scope is 'filtered' but no types, skip.")
            continue

        cids = None
        ctypes_f = None
        if cst == "selected":
            cids = selected_ids
        elif cst == "filtered":
            ctypes_f = ctypes

        include_html = _html_include_contracts_scope(
            contract_selection,
            contracts_df,
            selected_ids if cst == "selected" else None,
            ctypes if cst == "filtered" else None,
        )

        ok = False
        if stype == "weekly_payment":
            w0, w1 = _calendar_week_range_containing(now.date())
            csv_data = get_payments_csv_for_week(
                w0,
                w1,
                contract_ids=cids,
                contract_types=ctypes_f,
            )
            if csv_data is None:
                print(f"Schedule {sid}: weekly CSV failed, skip.")
                continue
            subj = f"Weekly Payment Report - {w0} to {w1}"
            body = _email_html_weekly_body(
                w0,
                w1,
                is_test=False,
                include_contracts_html=include_html,
            )
            ok = send_email_via_smtp(
                recipients,
                subj,
                body,
                csv_data=csv_data,
                csv_filename=f"payments_{w0}_{w1}.csv",
            )
        elif stype == "contract_reminder":
            try:
                rd = int(row.get("reminder_days_before") or 30)
            except (TypeError, ValueError):
                rd = 30
            upcoming = get_upcoming_payments_for_reminder_window(rd, cids, ctypes_f)
            csv_data = _reminder_payments_export_csv(upcoming)
            subj = f"Payment Reminder - next {rd} days"
            body = _email_html_reminder_body(
                rd,
                is_test=False,
                summary_html=_reminder_payments_summary_html(upcoming),
            )
            ok = send_email_via_smtp(
                recipients,
                subj,
                body,
                csv_data=csv_data,
                csv_filename=f"payment_reminder_{rd}d.csv",
            )
        else:
            print(f"Schedule {sid}: unknown type {stype}, skip.")
            continue

        if ok:
            mark_email_schedule_sent(sid)
            sent += 1
            print(f"Schedule {sid} ({stype}): sent to {len(recipients)} recipient(s).")
        else:
            print(f"Schedule {sid}: send failed (SMTP).")

    return sent


def main() -> int:
    try:
        n = run_due_email_schedules()
        print(f"Done. Sends completed: {n}.")
    except Exception as e:
        import traceback

        print(f"Fatal: {e}\n{traceback.format_exc()}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Shared presentation for lessor withholding tax exempt periods (logic stays in create/edit).
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

SESSION_ROWS_CREATE = "wh_period_rows_create"


def withholding_periods_column_config():
    """Column config for data_editor (legacy); prefer render_withholding_periods_row_editor."""
    return {
        "start_date": st.column_config.DateColumn(
            "Start date",
            help="First calendar day this exemption applies (inclusive).",
            format="DD/MM/YYYY",
        ),
        "end_date": st.column_config.DateColumn(
            "End date",
            help="Last calendar day this exemption applies (inclusive).",
            format="DD/MM/YYYY",
        ),
    }


def render_withholding_exempt_periods_section_intro(*, optional: bool = False) -> None:
    """Heading + short guidance for the exempt-periods table."""
    st.markdown("##### Withholding tax exemptions")
    lead = (
        "Define date ranges where **withholding tax does not apply** to this lessor when a payment falls on those dates."
    )
    if optional:
        lead += " You can leave this list empty."
    st.caption(lead)

    with st.expander("How this works", expanded=False):
        st.markdown(
            """
**Effect**  
For each payment, the system checks the payment date. If it lies inside any period below, that payment is treated as **exempt from withholding** for this lessor.

**Rules (validated on save)**  
- **Start** and **End** are inclusive.  
- **Start** must be on or before **End**.  
- Periods must **not overlap**.
            """.strip()
        )


def _session_key_edit(lessor_id: str) -> str:
    return f"wh_period_rows_edit_{lessor_id}"


def _ensure_row_ids(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        d = dict(r)
        if not d.get("row_id"):
            d["row_id"] = uuid.uuid4().hex[:12]
        out.append(d)
    return out


def _rows_from_dataframe(df: pd.DataFrame | None) -> list[dict]:
    if df is None or df.empty:
        return []
    rows = []
    for _, p in df.iterrows():
        sd = p.get("start_date")
        ed = p.get("end_date")
        s = pd.to_datetime(sd, errors="coerce")
        e = pd.to_datetime(ed, errors="coerce")
        rows.append(
            {
                "row_id": uuid.uuid4().hex[:12],
                "start": None if pd.isna(s) else s.date(),
                "end": None if pd.isna(e) else e.date(),
            }
        )
    return rows


def _init_session_rows(
    *, mode: str, lessor_id: str | None, existing_df: pd.DataFrame | None
) -> str:
    if mode == "create":
        sk = SESSION_ROWS_CREATE
        if sk not in st.session_state:
            st.session_state[sk] = []
        return sk
    sk = _session_key_edit(str(lessor_id))
    if sk not in st.session_state:
        st.session_state[sk] = _rows_from_dataframe(existing_df)
    return sk


def render_withholding_periods_row_editor(
    *,
    mode: str,
    lessor_id: str | None = None,
    existing_df: pd.DataFrame | None = None,
) -> None:
    """
    Interactive list: Add period, per-row Remove, optional Clear all.
    Stores rows in st.session_state as list of {row_id, start, end} (date | None).
    """
    sk = _init_session_rows(mode=mode, lessor_id=lessor_id, existing_df=existing_df)
    rows: list[dict[str, Any]] = _ensure_row_ids(list(st.session_state.get(sk, [])))
    st.session_state[sk] = rows

    st.caption("Use **Add exemption period** for a new row. **Remove** deletes that row only.")

    act1, act2, _ = st.columns([1.2, 1.2, 2])
    with act1:
        if st.button("Add exemption period", key=f"{sk}_add", type="primary", use_container_width=True):
            today = date.today()
            rows.append({"row_id": uuid.uuid4().hex[:12], "start": today, "end": today})
            st.session_state[sk] = rows
            st.rerun()
    with act2:
        if st.button("Clear all periods", key=f"{sk}_clear", use_container_width=True):
            st.session_state[sk] = []
            st.rerun()

    if not rows:
        st.info("No exemption periods yet. Click **Add exemption period** to create one.")
        return

    st.markdown("---")
    updated: list[dict[str, Any]] = []
    for idx, r in enumerate(rows):
        rid = r["row_id"]
        st.markdown(f"**Period {idx + 1}**")
        c1, c2, c3 = st.columns([2, 2, 0.9])
        with c1:
            val_s = r.get("start")
            if val_s is None:
                val_s = date.today()
            s = st.date_input(
                "Start date",
                value=val_s,
                key=f"wph_{sk}_{rid}_s",
                help="First day (inclusive)",
            )
        with c2:
            val_e = r.get("end")
            if val_e is None:
                val_e = date.today()
            e = st.date_input(
                "End date",
                value=val_e,
                key=f"wph_{sk}_{rid}_e",
                help="Last day (inclusive)",
            )
        with c3:
            st.write("")  # align with date inputs
            st.write("")
            if st.button("Remove", key=f"wph_{sk}_{rid}_rm", use_container_width=True):
                st.session_state[sk] = [x for x in rows if x["row_id"] != rid]
                st.rerun()
        updated.append({"row_id": rid, "start": s, "end": e})

    st.session_state[sk] = updated


def get_period_rows_from_session(
    *, mode: str, lessor_id: str | None = None
) -> list[dict[str, Any]]:
    if mode == "create":
        sk = SESSION_ROWS_CREATE
    else:
        sk = _session_key_edit(str(lessor_id))
    return _ensure_row_ids(list(st.session_state.get(sk, [])))


def validate_period_rows_for_save(
    rows: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, str]]]:
    """
    Same rules as previous data_editor validation.
    Returns (error_messages, periods_to_save) where periods_to_save uses YYYY-MM-DD strings.
    """
    errors: list[str] = []
    raw_periods: list[dict[str, Any]] = []

    for idx, r in enumerate(rows):
        start_date = r.get("start")
        end_date = r.get("end")

        if start_date is None and end_date is None:
            continue
        if start_date is None or end_date is None:
            errors.append(
                f"Period {idx + 1}: both **Start date** and **End date** are required."
            )
            continue

        if not isinstance(start_date, date):
            sd = pd.to_datetime(start_date, errors="coerce")
        else:
            sd = pd.Timestamp(start_date)
        if not isinstance(end_date, date):
            ed = pd.to_datetime(end_date, errors="coerce")
        else:
            ed = pd.Timestamp(end_date)

        if pd.isna(sd) or pd.isna(ed):
            errors.append(f"Period {idx + 1}: invalid date.")
            continue
        if sd > ed:
            errors.append(
                f"Period {idx + 1}: **Start date** cannot be after **End date**."
            )
            continue
        raw_periods.append({"start_date": sd, "end_date": ed})

    if raw_periods:
        raw_periods.sort(key=lambda x: x["start_date"])
        for i in range(1, len(raw_periods)):
            prev = raw_periods[i - 1]
            curr = raw_periods[i]
            if curr["start_date"] <= prev["end_date"]:
                errors.append(
                    "Exempt periods cannot overlap. Please adjust the start and end dates."
                )
                break

    if errors:
        return errors, []

    periods_to_save = [
        {
            "start_date": p["start_date"].strftime("%Y-%m-%d"),
            "end_date": p["end_date"].strftime("%Y-%m-%d"),
        }
        for p in raw_periods
    ]
    return [], periods_to_save


def reset_create_period_session() -> None:
    st.session_state[SESSION_ROWS_CREATE] = []

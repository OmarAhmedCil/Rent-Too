import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission
from .withholding_periods_ui import (
    render_withholding_exempt_periods_section_intro,
    render_withholding_periods_row_editor,
    get_period_rows_from_session,
    validate_period_rows_for_save,
)

_NAV_LESSORS = f"{chr(0x1F465)} Lessors"


def render_edit_lessor():
    require_permission("lessors.edit")
    st.header("Edit Lessor")
    bc1, bc2 = st.columns([1, 4])
    with bc1:
        if st.button("← Management", key="lessor_edit_back_mgmt"):
            st.session_state.pop("lessors_edit_target_id", None)
            st.session_state.pop("lessors_editing_id", None)
            st.session_state.selected_main = _NAV_LESSORS
            st.session_state.selected_sub = "Lessor Management"
            st.rerun()
    load_all()
    lessors_df = st.session_state.lessors_df.copy()

    if lessors_df.empty:
        st.info("No lessors available to edit.")
        return

    if "lessors_edit_target_id" in st.session_state:
        st.session_state["lessors_editing_id"] = str(
            st.session_state.pop("lessors_edit_target_id")
        )

    leid = st.session_state.get("lessors_editing_id")

    if leid:
        _m = lessors_df[lessors_df["id"].astype(str) == str(leid)]
        if _m.empty:
            st.error("Lessor not found or was removed.")
            st.session_state.pop("lessors_editing_id", None)
            return
        row = _m.iloc[0]
        st.caption(f"Editing **{row.get('name', '')}** · ID `{leid}`")
    else:
        sorted_names = sorted(lessors_df["name"].astype(str).tolist())
        sel_name = st.selectbox(
            "Select lessor to edit",
            options=[""] + sorted_names,
            key="edit_sel_lessor",
        )
        if not sel_name:
            return
        row = lessors_df[lessors_df["name"] == sel_name].iloc[0]

    edit_name = st.text_input("Name", value=row.get("name", ""), key="edit_l_name")
    edit_desc = st.text_area("Description", value=row.get("description", ""), key="edit_l_desc")
    edit_tax_id = st.text_input("Tax ID", value=row.get("tax_id", ""), key="edit_l_tax_id")
    edit_supplier_code = st.text_input(
        "Supplier code", value=row.get("supplier_code", ""), key="edit_l_supplier_code"
    )
    edit_iban = st.text_input("IBAN", value=row.get("iban", ""), key="edit_l_iban")

    lwp_df = st.session_state.get(
        "lessor_withholding_periods_df",
        pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS),
    )
    existing_periods = (
        lwp_df[lwp_df["lessor_id"] == str(row["id"])] if not lwp_df.empty else pd.DataFrame()
    )
    existing_periods = (
        existing_periods[["start_date", "end_date"]]
        if not existing_periods.empty
        else pd.DataFrame(columns=["start_date", "end_date"])
    )
    if not existing_periods.empty:
        existing_periods["start_date"] = pd.to_datetime(
            existing_periods["start_date"], errors="coerce"
        )
        existing_periods["end_date"] = pd.to_datetime(
            existing_periods["end_date"], errors="coerce"
        )

    with st.container(border=True):
        render_withholding_exempt_periods_section_intro(optional=False)
        render_withholding_periods_row_editor(
            mode="edit",
            lessor_id=str(row["id"]),
            existing_df=existing_periods,
        )

    if st.button("Save changes", key="save_lessor_btn"):
        if not edit_name.strip():
            st.error("Name cannot be empty.")
        else:
            other_lessors = lessors_df[lessors_df["name"].str.strip() == edit_name.strip()]
            if not other_lessors.empty and other_lessors.iloc[0]["id"] != row["id"]:
                st.error("Lessor name already taken by another lessor.")
            else:
                lessor_data = {
                    "name": edit_name.strip(),
                    "description": edit_desc.strip(),
                    "tax_id": edit_tax_id.strip(),
                    "supplier_code": edit_supplier_code.strip(),
                    "iban": edit_iban.strip(),
                }
                if update_lessor(row["id"], lessor_data):
                    period_rows = get_period_rows_from_session(
                        mode="edit", lessor_id=str(row["id"])
                    )
                    validation_errors, periods_to_save = validate_period_rows_for_save(
                        period_rows
                    )

                    if validation_errors:
                        for msg in validation_errors:
                            st.error(msg)
                        return

                    if not upsert_lessor_withholding_periods(row["id"], periods_to_save):
                        st.error(
                            "Failed to save withholding tax exempt periods for this lessor. Please check the database schema and `lessor_withholding_periods` table."
                        )
                        return
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user["id"] if current_user else None,
                        user_name=current_user["name"] if current_user else "System",
                        action_type="edit",
                        entity_type="lessor",
                        entity_id=row["id"],
                        entity_name=edit_name.strip(),
                        action_details=f"Updated lessor: {edit_name}",
                        ip_address=get_user_ip(),
                    )
                    st.success("Lessor updated.")
                    sk = f"wh_period_rows_edit_{row['id']}"
                    st.session_state.pop(sk, None)
                    load_all()
                    st.session_state.selected_main = _NAV_LESSORS
                    st.session_state.selected_sub = "Lessor Management"
                    st.session_state.pop("lessors_editing_id", None)
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.error("Failed to update lessor.")

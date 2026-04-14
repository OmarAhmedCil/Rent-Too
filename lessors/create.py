import streamlit as st
import time
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
    reset_create_period_session,
)

_NAV_LESSORS = f"{chr(0x1F465)} Lessors"


def render_create_lessor():
    require_permission('lessors.create')
    st.header("Create Lessor")
    load_all()
    lessors_df = st.session_state.lessors_df.copy()

    st.subheader("Add new lessor")
    new_name = st.text_input("Lessor name", key="create_lessor_name")
    new_desc = st.text_area("Description (optional)", key="create_lessor_desc")
    new_tax_id = st.text_input("Tax ID (optional)", key="create_lessor_tax_id")
    new_supplier_code = st.text_input(
        "Supplier code (optional)", key="create_lessor_supplier"
    )
    new_iban = st.text_input("IBAN (optional)", key="create_lessor_iban")

    with st.container(border=True):
        render_withholding_exempt_periods_section_intro(optional=True)
        render_withholding_periods_row_editor(mode="create")

    if st.button("Add Lessor", type="primary", key="create_lessor_submit"):
        if not new_name.strip():
            st.error("Lessor name is required.")
            return

        if not lessors_df[lessors_df['name'].str.strip() == new_name.strip()].empty:
            st.error("Lessor name already exists.")
            return

        period_rows = get_period_rows_from_session(mode="create")
        validation_errors, periods_to_save = validate_period_rows_for_save(period_rows)

        if validation_errors:
            for msg in validation_errors:
                st.error(msg)
            return

        nid = next_int_id(lessors_df, 1)
        lessor_data = {
            "id": str(nid),
            "name": new_name.strip(),
            "description": new_desc.strip(),
            "tax_id": new_tax_id.strip(),
            "supplier_code": new_supplier_code.strip(),
            "iban": new_iban.strip(),
        }
        if insert_lessor(lessor_data):
            if periods_to_save:
                if not upsert_lessor_withholding_periods(str(nid), periods_to_save):
                    st.error(
                        "Lessor was created, but failed to save withholding tax exempt periods. Please check the database schema and `lessor_withholding_periods` table."
                    )
                    return

            reset_create_period_session()
            for k in (
                "create_lessor_name",
                "create_lessor_desc",
                "create_lessor_tax_id",
                "create_lessor_supplier",
                "create_lessor_iban",
            ):
                if k in st.session_state:
                    st.session_state[k] = "" if k != "create_lessor_desc" else ""

            current_user = get_current_user()
            log_action(
                user_id=current_user['id'] if current_user else None,
                user_name=current_user['name'] if current_user else 'System',
                action_type='create',
                entity_type='lessor',
                entity_id=str(nid),
                entity_name=new_name.strip(),
                action_details=f"Created lessor: {new_name}",
                ip_address=get_user_ip()
            )
            st.success(f"Added lessor: {new_name} (ID {nid})")
            load_all()
            st.session_state.selected_main = _NAV_LESSORS
            st.session_state.selected_sub = "Lessor Management"
            time.sleep(0.3)
            st.rerun()
        else:
            st.error("Failed to add lessor.")

import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission


def render_edit_service():
    require_permission("services.edit")
    st.header("Edit Service")
    bc1, bc2 = st.columns([1, 4])
    with bc1:
        if st.button("← Management", key="svc_edit_back_mgmt"):
            st.session_state.pop("services_edit_target_id", None)
            st.session_state.pop("services_editing_id", None)
            st.session_state.selected_main = "🔧 Services"
            st.session_state.selected_sub = "Service Management"
            st.rerun()
    load_all()
    services_df = st.session_state.services_df.copy()

    if services_df.empty:
        st.info("No services available to edit.")
        return

    if "services_edit_target_id" in st.session_state:
        st.session_state["services_editing_id"] = str(
            st.session_state.pop("services_edit_target_id")
        )

    seid = st.session_state.get("services_editing_id")

    if seid:
        _m = services_df[services_df["id"].astype(str) == str(seid)]
        if _m.empty:
            st.error("Service not found or was removed.")
            st.session_state.pop("services_editing_id", None)
            return
        row = _m.iloc[0]
        st.caption(f"Editing **{row.get('name', '')}** · ID `{seid}`")
    else:
        sorted_names = sorted(services_df["name"].astype(str).tolist())
        sel_name = st.selectbox(
            "Select service to edit",
            options=[""] + sorted_names,
            key="edit_sel_service",
        )
        if not sel_name:
            return
        row = services_df[services_df["name"] == sel_name].iloc[0]

    edit_name = st.text_input("Name", value=row.get("name", ""), key="edit_s_name")
    edit_desc = st.text_area("Description", value=row.get("description", ""), key="edit_s_desc")
    current_currency = row.get("currency", "EGP")
    currency_index = 0 if current_currency == "EGP" else 1
    edit_currency = st.selectbox(
        "Currency", options=["EGP", "USD"], index=currency_index, key="edit_s_currency"
    )

    if st.button("Save changes", key="save_service_btn"):
        if not edit_name.strip():
            st.error("Name cannot be empty.")
        else:
            other_services = services_df[services_df["name"].str.strip() == edit_name.strip()]
            if not other_services.empty and other_services.iloc[0]["id"] != row["id"]:
                st.error("Service name already taken by another service.")
            else:
                service_data = {
                    "name": edit_name.strip(),
                    "description": edit_desc.strip(),
                    "currency": edit_currency,
                }
                if update_service(row["id"], service_data):
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user["id"] if current_user else None,
                        user_name=current_user["name"] if current_user else "System",
                        action_type="edit",
                        entity_type="service",
                        entity_id=row["id"],
                        entity_name=edit_name.strip(),
                        action_details=f"Updated service: {edit_name}",
                        ip_address=get_user_ip(),
                    )
                    st.success("Service updated.")
                    load_all()
                    st.session_state.selected_main = "🔧 Services"
                    st.session_state.selected_sub = "Service Management"
                    st.session_state.pop("services_editing_id", None)
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.error("Failed to update service.")

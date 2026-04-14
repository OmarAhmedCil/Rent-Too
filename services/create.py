import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission


def render_create_service():
    require_permission('services.create')
    st.header("Create Service")
    load_all()
    services_df = st.session_state.services_df.copy()

    with st.form("form_add_service", clear_on_submit=True):
        st.subheader("Add new service")
        new_name = st.text_input("Service name")
        new_desc = st.text_area("Description (optional)")
        new_currency = st.selectbox("Currency", options=["EGP", "USD"], index=0)
        if st.form_submit_button("Add Service"):
            if not new_name.strip():
                st.error("Service name is required.")
            else:
                # Check if name already exists
                if not services_df[services_df['name'].str.strip() == new_name.strip()].empty:
                    st.error("Service name already exists.")
                else:
                    nid = next_int_id(services_df, 1)
                    service_data = {
                        "id": str(nid),
                        "name": new_name.strip(),
                        "description": new_desc.strip(),
                        "currency": new_currency
                    }
                    if insert_service(service_data):
                        # Log action
                        current_user = get_current_user()
                        log_action(
                            user_id=current_user['id'] if current_user else None,
                            user_name=current_user['name'] if current_user else 'System',
                            action_type='create',
                            entity_type='service',
                            entity_id=str(nid),
                            entity_name=new_name.strip(),
                            action_details=f"Created service: {new_name}",
                            ip_address=get_user_ip()
                        )
                        st.success(f"Added service: {new_name} (ID {nid})")
                        load_all()
                        st.session_state.selected_main = "🔧 Services"
                        st.session_state.selected_sub = "Service Management"
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error("Failed to add service.")

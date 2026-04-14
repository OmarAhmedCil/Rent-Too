import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission


def render_delete_service():
    require_permission('services.delete')
    st.header("Delete Service")
    load_all()
    services_df = st.session_state.services_df.copy()

    if services_df.empty:
        st.info("No services available to delete.")
        return

    search_q = st.text_input("Search by name", value="", key="delete_service_search")
    filtered = (
        services_df[services_df['name'].str.contains(search_q.strip(), case=False, na=False)]
        if search_q.strip() else services_df
    )

    if filtered.empty:
        st.info("No services found.")
    else:
        st.dataframe(filtered[['name', 'description', 'currency']], use_container_width=True)
        sel_name = st.selectbox("Select service (by name)", options=[""] + filtered['name'].tolist(), key="delete_sel_service")
        if sel_name:
            row = services_df[services_df['name'] == sel_name].iloc[0]
            st.markdown("---")
            st.warning(f"⚠️ You are about to delete service: **{row['name']}** (ID: {row['id']})")
            st.write(f"**Description:** {row.get('description', 'N/A')}")
            st.write(f"**Currency:** {row.get('currency', 'EGP')}")
            
            st.markdown("---")
            st.error("⚠️ **WARNING:** This action cannot be undone. This will also delete all contract-service relationships for this service.")
            
            confirm_text = st.text_input("Type 'DELETE' to confirm", key="delete_service_confirm")
            
            if st.button("Delete Service", key="delete_service_btn", type="primary"):
                if confirm_text != "DELETE":
                    st.error("Please type 'DELETE' to confirm deletion.")
                else:
                    if delete_service(row['id']):
                        # Log action
                        current_user = get_current_user()
                        log_action(
                            user_id=current_user['id'] if current_user else None,
                            user_name=current_user['name'] if current_user else 'System',
                            action_type='delete',
                            entity_type='service',
                            entity_id=row['id'],
                            entity_name=row['name'],
                            action_details=f"Deleted service: {row['name']}",
                            ip_address=get_user_ip()
                        )
                        st.success(f"Service deleted (ID {row['id']})")
                        load_all()
                        st.session_state.selected_main = "🔧 Services"
                        st.session_state.selected_sub = "Service Management"
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error("Failed to delete service.")

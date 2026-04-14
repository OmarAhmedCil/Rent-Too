import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission


def render_delete_lessor():
    require_permission('lessors.delete')
    st.header("Delete Lessor")
    load_all()
    lessors_df = st.session_state.lessors_df.copy()

    if lessors_df.empty:
        st.info("No lessors available to delete.")
        return

    search_q = st.text_input("Search by name", value="", key="delete_lessor_search")
    filtered = (
        lessors_df[lessors_df['name'].str.contains(search_q.strip(), case=False, na=False)]
        if search_q.strip() else lessors_df
    )

    if filtered.empty:
        st.info("No lessors found.")
    else:
        st.dataframe(filtered[['name', 'description', 'tax_id', 'supplier_code', 'iban']], use_container_width=True)
        sel_name = st.selectbox("Select lessor (by name)", options=[""] + filtered['name'].tolist(), key="delete_sel_lessor")
        if sel_name:
            row = lessors_df[lessors_df['name'] == sel_name].iloc[0]
            st.markdown("---")
            st.warning(f"⚠️ You are about to delete lessor: **{row['name']}** (ID: {row['id']})")
            st.write(f"**Description:** {row.get('description', 'N/A')}")
            st.write(f"**Tax ID:** {row.get('tax_id', 'N/A')}")
            st.write(f"**Supplier code:** {row.get('supplier_code', 'N/A')}")
            st.write(f"**IBAN:** {row.get('iban', 'N/A')}")
            
            st.markdown("---")
            st.error("⚠️ **WARNING:** This action cannot be undone.")
            
            confirm_text = st.text_input("Type 'DELETE' to confirm", key="delete_lessor_confirm")
            
            if st.button("Delete Lessor", key="delete_lessor_btn", type="primary"):
                if confirm_text != "DELETE":
                    st.error("Please type 'DELETE' to confirm deletion.")
                else:
                    if delete_lessor(row['id']):
                        current_user = get_current_user()
                        log_action(
                            user_id=current_user['id'] if current_user else None,
                            user_name=current_user['name'] if current_user else 'System',
                            action_type='delete',
                            entity_type='lessor',
                            entity_id=row['id'],
                            entity_name=row['name'],
                            action_details=f"Deleted lessor: {row['name']}",
                            ip_address=get_user_ip()
                        )
                        st.success(f"Lessor deleted (ID {row['id']})")
                        load_all()
                        st.session_state.selected_main = "👥 Lessors"
                        st.session_state.selected_sub = "Lessor Management"
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error("Failed to delete lessor.")


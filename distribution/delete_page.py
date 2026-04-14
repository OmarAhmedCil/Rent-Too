import streamlit as st
import pandas as pd
import time
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission

def render_delete_distribution():
    """Render delete distribution tab"""
    require_permission('distribution.delete')
    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("← Contracts Distribution", key="dist_del_back_mgmt"):
            st.session_state.selected_main = "📊 Distribution"
            st.session_state.selected_sub = "Contracts Distribution"
            st.rerun()
    st.header("Delete Distribution")
    load_all()
    contracts_df = st.session_state.contracts_df.copy()
    
    if contracts_df.empty:
        st.info("No contracts available.")
        return
    
    # Add filters
    st.subheader("Filters")
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    
    with filter_col1:
        search_name = st.text_input("🔍 Search by Contract Name", key="contract_search_name_delete")
    
    with filter_col2:
        contract_types = ["All"] + sorted(contracts_df['contract_type'].dropna().unique().tolist())
        filter_type = st.selectbox("Filter by Contract Type", options=contract_types, key="contract_filter_type_delete")
    
    with filter_col3:
        # Get unique asset/store names
        asset_store_names = ["All"] + sorted(contracts_df['asset_or_store_name'].dropna().unique().tolist())
        filter_asset_store = st.selectbox("Filter by Asset/Store", options=asset_store_names, key="contract_filter_asset_store_delete")
    
    # Apply filters
    filtered_df = contracts_df.copy()
    
    if search_name:
        filtered_df = filtered_df[
            filtered_df['contract_name'].str.contains(search_name, case=False, na=False)
        ]
    
    if filter_type != "All":
        filtered_df = filtered_df[filtered_df['contract_type'] == filter_type]
    
    if filter_asset_store != "All":
        filtered_df = filtered_df[filtered_df['asset_or_store_name'] == filter_asset_store]
    
    if filtered_df.empty:
        st.info("No contracts match the selected filters.")
        return
    
    # Sort by contract name for better UX
    filtered_df = filtered_df.sort_values('contract_name')
    
    # Show count
    st.caption(f"Showing {len(filtered_df)} of {len(contracts_df)} contract(s)")
    
    # Select contract for deletion
    delete_contract_options = [""] + filtered_df['contract_name'].tolist()
    selected_delete_contract_name = st.selectbox(
        "Select Contract to Delete Distribution Data",
        options=delete_contract_options,
        key="select_contract_for_delete_distribution"
    )
    
    if selected_delete_contract_name:
        delete_contract_row = filtered_df[filtered_df['contract_name'] == selected_delete_contract_name].iloc[0]
        delete_contract_id = delete_contract_row['id']
        
        # Display contract info
        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.write(f"**Contract:** {delete_contract_row['contract_name']}")
            st.write(f"**Contract Type:** {delete_contract_row['contract_type']}")
        with col_info2:
            st.write(f"**Asset/Store:** {delete_contract_row.get('asset_or_store_name', 'N/A')}")
        
        # Check what distribution data exists
        contract_type = delete_contract_row.get('contract_type', '')
        contract_dist_exists = check_distribution_exists(delete_contract_id, contract_type)
        
        # Get distribution count
        dist_count = 0
        if contract_dist_exists:
            dist_df = load_distribution_for_contract(delete_contract_id, contract_type)
            dist_count = len(dist_df) if not dist_df.empty else 0
        
        existing_service_dist_df = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
        contract_service_dist_exists = not existing_service_dist_df.empty and \
                                     len(existing_service_dist_df[existing_service_dist_df['contract_id'] == delete_contract_id]) > 0
        
        st.markdown("---")
        
        col_del1, col_del2 = st.columns(2)
        
        with col_del1:
            st.subheader("Contract Distribution")
            if contract_dist_exists:
                st.write(f"**Records:** {dist_count}")
                st.warning("⚠️ This will delete all contract distribution records for this contract.")
                confirm_text = st.text_input("Type 'DELETE' to confirm", key="delete_contract_dist_confirm")
                if st.button("🗑️ Delete Contract Distribution", key="btn_delete_contract_dist", type="primary"):
                    if confirm_text != "DELETE":
                        st.error("Please type 'DELETE' to confirm deletion.")
                    else:
                        if delete_contract_distribution(delete_contract_id, contract_type):
                            # Log action
                            current_user = get_current_user()
                            log_action(
                                user_id=current_user['id'] if current_user else None,
                                user_name=current_user['name'] if current_user else 'System',
                                action_type='delete',
                                entity_type='distribution',
                                entity_id=delete_contract_id,
                                entity_name=delete_contract_row['contract_name'],
                                action_details=f"Deleted contract distribution: {dist_count} records",
                                ip_address=get_user_ip()
                            )
                            st.success(f"✅ Contract distribution data deleted successfully!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Failed to delete contract distribution data.")
            else:
                st.info("No contract distribution data exists for this contract.")
        
        with col_del2:
            st.subheader("Service Distribution")
            if contract_service_dist_exists:
                service_dist_count = len(existing_service_dist_df[existing_service_dist_df['contract_id'] == delete_contract_id])
                st.write(f"**Records:** {service_dist_count}")
                st.warning("⚠️ This will delete all service distribution records for this contract.")
                confirm_text = st.text_input("Type 'DELETE' to confirm", key="delete_service_dist_confirm")
                if st.button("🗑️ Delete Service Distribution", key="btn_delete_service_dist", type="primary"):
                    if confirm_text != "DELETE":
                        st.error("Please type 'DELETE' to confirm deletion.")
                    else:
                        if delete_service_distribution(delete_contract_id):
                            # Log action
                            current_user = get_current_user()
                            log_action(
                                user_id=current_user['id'] if current_user else None,
                                user_name=current_user['name'] if current_user else 'System',
                                action_type='delete',
                                entity_type='service_distribution',
                                entity_id=delete_contract_id,
                                entity_name=delete_contract_row['contract_name'],
                                action_details=f"Deleted service distribution: {service_dist_count} records",
                                ip_address=get_user_ip()
                            )
                            st.success(f"✅ Service distribution data deleted successfully!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Failed to delete service distribution data.")
            else:
                st.info("No service distribution data exists for this contract.")


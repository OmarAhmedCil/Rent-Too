import streamlit as st
import pandas as pd
import time
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission

def get_contract_selection():
    """Helper function to get contract selection and info with filters"""
    load_all()
    contracts_df = st.session_state.contracts_df.copy()
    
    if contracts_df.empty:
        st.info("No contracts available. Please create contracts first.")
        return None, None
    
    # Add filters
    st.subheader("Filters")
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    
    with filter_col1:
        search_name = st.text_input("🔍 Search by Contract Name", key="contract_search_name_dist")
    
    with filter_col2:
        contract_types = ["All"] + sorted(contracts_df['contract_type'].dropna().unique().tolist())
        filter_type = st.selectbox("Filter by Contract Type", options=contract_types, key="contract_filter_type_dist")
    
    with filter_col3:
        # Get unique asset/store names
        asset_store_names = ["All"] + sorted(contracts_df['asset_or_store_name'].dropna().unique().tolist())
        filter_asset_store = st.selectbox("Filter by Asset/Store", options=asset_store_names, key="contract_filter_asset_store_dist")
    
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
        return None, None
    
    # Sort by contract name for better UX
    filtered_df = filtered_df.sort_values('contract_name')
    
    # Show count
    st.caption(f"Showing {len(filtered_df)} of {len(contracts_df)} contract(s)")
    
    # Select contract
    contract_options = [""] + filtered_df['contract_name'].tolist()
    selected_contract_name = st.selectbox(
        "Select Contract",
        options=contract_options,
        key="select_contract_for_distribution"
    )

    if not selected_contract_name:
        st.info("Select a contract to proceed.")
        return None, None

    contract_row = filtered_df[filtered_df['contract_name'] == selected_contract_name].iloc[0]
    
    # Display contract info
    st.markdown("---")
    st.subheader("Contract Details")
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.write(f"**Contract Type:** {contract_row['contract_type']}")
        st.write(f"**Currency:** {contract_row.get('currency', 'EGP')}")
        st.write(f"**Commencement date:** {contract_row['commencement_date']}")
        st.write(f"**End Date:** {contract_row['end_date']}")
    with col_info2:
        st.write(f"**Asset/Store:** {contract_row.get('asset_or_store_name', 'N/A')}")
        st.write(f"**Tax %:** {contract_row.get('tax', '0')}%")
        st.write(f"**Yearly Increase %:** {contract_row.get('yearly_increase', '0')}%")
    
    return contract_row, selected_contract_name

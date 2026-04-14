# tab_action_logs.py
# Action logs viewing tab
import streamlit as st
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user
from core.permissions import require_permission

def render_action_logs_tab():
    """Render action logs tab"""
    require_permission('logs.view')
    
    st.header("Action Logs")
    load_all()
    
    action_logs_df = st.session_state.action_logs_df.copy()
    
    if action_logs_df.empty:
        st.info("No action logs available.")
        return
    
    st.subheader("Filters")
    with st.container(border=True):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            action_types = sorted(action_logs_df['action_type'].unique()) if 'action_type' in action_logs_df.columns else []
            selected_action_type = st.selectbox("Filter by Action Type", options=["All"] + action_types, key="filter_action_type")

        with col2:
            entity_types = sorted(action_logs_df['entity_type'].dropna().unique()) if 'entity_type' in action_logs_df.columns else []
            selected_entity_type = st.selectbox("Filter by Entity Type", options=["All"] + entity_types, key="filter_entity_type")

        with col3:
            users = sorted(action_logs_df['user_name'].dropna().unique()) if 'user_name' in action_logs_df.columns else []
            selected_user = st.selectbox("Filter by User", options=["All"] + users, key="filter_user")

        with col4:
            if 'created_at' in action_logs_df.columns:
                action_logs_df['created_at'] = pd.to_datetime(action_logs_df['created_at'], errors='coerce')
                min_date = action_logs_df['created_at'].min().date() if not action_logs_df['created_at'].isna().all() else None
                max_date = action_logs_df['created_at'].max().date() if not action_logs_df['created_at'].isna().all() else None

                if min_date and max_date:
                    date_range = st.date_input(
                        "Date Range",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date,
                        key="filter_date_range"
                    )
                else:
                    date_range = None
            else:
                date_range = None

    # Apply filters
    filtered_df = action_logs_df.copy()
    
    if selected_action_type != "All":
        filtered_df = filtered_df[filtered_df['action_type'] == selected_action_type]
    
    if selected_entity_type != "All":
        filtered_df = filtered_df[filtered_df['entity_type'] == selected_entity_type]
    
    if selected_user != "All":
        filtered_df = filtered_df[filtered_df['user_name'] == selected_user]
    
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        if 'created_at' in filtered_df.columns:
            filtered_df = filtered_df[
                (filtered_df['created_at'].dt.date >= start_date) &
                (filtered_df['created_at'].dt.date <= end_date)
            ]
    
    # Display logs
    st.markdown("---")
    st.subheader(f"Action Logs ({len(filtered_df)} records)")
    
    if filtered_df.empty:
        st.info("No logs match the selected filters.")
    else:
        # Select columns to display
        display_cols = ['created_at', 'user_name', 'action_type', 'entity_type', 'entity_name', 'action_details']
        available_cols = [col for col in display_cols if col in filtered_df.columns]
        
        # Sort by created_at descending
        if 'created_at' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('created_at', ascending=False)
        
        # Display dataframe
        st.dataframe(
            filtered_df[available_cols],
            use_container_width=True,
            height=600
        )
        
        # Export option
        if st.button("Export to CSV", key="export_logs"):
            csv = filtered_df[available_cols].to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"action_logs_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key="download_logs_csv"
            )


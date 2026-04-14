import streamlit as st
import pandas as pd
import time
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission

from .helpers import get_contract_selection

def render_generate_distribution():
    """Render generate distribution tab"""
    require_permission('distribution.generate')
    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("← Contracts Distribution", key="dist_gen_back_mgmt"):
            st.session_state.selected_main = "📊 Distribution"
            st.session_state.selected_sub = "Contracts Distribution"
            st.rerun()
    st.header("Generate Distribution")
    contract_row, selected_contract_name = get_contract_selection()
    
    if contract_row is None:
        return
    
    load_all()
    lessors_df = st.session_state.lessors_df.copy()
    store_monthly_sales_df = load_df(STORE_MONTHLY_SALES_TABLE, STORE_MONTHLY_SALES_COLS)
    services_df = st.session_state.services_df.copy()
    contract_services_df = st.session_state.contract_services_df.copy()
    
    # Check if distribution already exists
    contract_type = contract_row.get('contract_type', '')
    if not contract_type:
        st.error("Contract type is missing. Cannot generate distribution.")
        return
    
    distribution_exists = check_distribution_exists(contract_row['id'], contract_type)
    
    if distribution_exists:
        st.warning("⚠️ Distribution already exists for this contract. Use 'Regenerate Distribution' to replace it.")
    else:
        if st.button("Generate Distribution", key="btn_generate_distribution", type="primary"):
            with st.spinner("Generating distribution data..."):
                distribution_rows = generate_contract_distribution(contract_row, lessors_df, store_monthly_sales_df, services_df, contract_services_df)
                service_distribution_rows = generate_service_distribution(contract_row, services_df, contract_services_df)

                if distribution_rows:
                    try:
                        # Get the correct table and columns for this contract type
                        dist_table = get_distribution_table(contract_type)
                        dist_cols = get_distribution_storage_cols(contract_type)
                        
                        # Ensure we're not using the old table
                        if dist_table == CONTRACT_DISTRIBUTION_TABLE:
                            st.error(f"Invalid contract type: {contract_type}. Cannot determine distribution table.")
                            return
                        
                        agg_dist = aggregate_distribution_rows_for_db(contract_type, distribution_rows)
                        dist_df = pd.DataFrame(agg_dist)
                        for col in dist_cols:
                            if col not in dist_df.columns:
                                dist_df[col] = None if '_date' in col.lower() else ""
                        
                        # Debug: Check if rent_date is present and has values
                        if 'rent_date' in dist_df.columns:
                            empty_rent_dates = dist_df['rent_date'].isna() | (dist_df['rent_date'] == '') | (dist_df['rent_date'].astype(str).str.strip() == '')
                            if empty_rent_dates.any():
                                st.warning(f"Warning: Found {empty_rent_dates.sum()} rows with empty rent_date. These will be set to NULL.")
                                # Try to fill missing rent_dates from other date columns or recalculate
                                # For now, just log the issue
                        
                        dist_df = dist_df[dist_cols]

                        existing_dist_df_local = load_df(dist_table, dist_cols)
                        new_dist_df = pd.concat([existing_dist_df_local, dist_df], ignore_index=True)

                        if save_df(new_dist_df, dist_table):
                            st.info(f"Saved {len(dist_df)} rows to database. Total rows: {len(new_dist_df)}")
                        else:
                            st.error("Failed to save distribution data to database.")
                            return
                    except Exception as e:
                        st.error(f"Error creating or saving DataFrame: {str(e)}")
                        import traceback
                        st.error(traceback.format_exc())
                        return

                    # IMPORTANT: Save service_distribution BEFORE creating payments
                    # This ensures service_distribution IDs are available when creating payment records
                    if service_distribution_rows:
                        service_dist_df = pd.DataFrame(
                            aggregate_service_distribution_for_db(service_distribution_rows)
                        )
                        existing_service_dist_df_local = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
                        _cid = str(contract_row["id"])
                        if not existing_service_dist_df_local.empty:
                            existing_service_dist_df_local = existing_service_dist_df_local[
                                existing_service_dist_df_local["contract_id"].astype(str) != _cid
                            ]
                        new_service_dist_df = pd.concat([existing_service_dist_df_local, service_dist_df], ignore_index=True)
                        if save_df(new_service_dist_df, SERVICE_DISTRIBUTION_TABLE):
                            st.info(f"Saved {len(service_dist_df)} service distribution rows to database.")
                        else:
                            st.error("Failed to save service distribution data to database.")
                            return
                    
                    # Create payment records AFTER both distributions are saved
                    # This ensures distribution IDs are available when creating payments
                    create_payment_records_from_distribution(
                        contract_row['id'],
                        contract_type,
                        contract_row,
                        distribution_rows=distribution_rows,
                        service_distribution_rows=service_distribution_rows,
                    )

                    current_user = get_current_user()
                    log_action(
                        user_id=current_user["id"] if current_user else None,
                        user_name=current_user["name"] if current_user else "System",
                        action_type="generate",
                        entity_type="distribution",
                        entity_id=contract_row["id"],
                        entity_name=contract_row.get("contract_name", ""),
                        action_details=(
                            f"Generated distribution: {len(distribution_rows)} contract rows, "
                            f"{len(service_distribution_rows)} service rows; payments refreshed"
                        ),
                        ip_address=get_user_ip(),
                    )

                    st.success(f"✅ Distribution generated successfully! Created {len(distribution_rows)} contract rows and {len(service_distribution_rows)} service rows.")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Failed to generate distribution data. Please check contract details.")

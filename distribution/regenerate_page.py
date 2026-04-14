import streamlit as st
import pandas as pd
import time
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission

from .helpers import get_contract_selection

def render_regenerate_distribution():
    """Render regenerate distribution tab"""
    require_permission('distribution.regenerate')
    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("← Contracts Distribution", key="dist_regen_back_mgmt"):
            st.session_state.selected_main = "📊 Distribution"
            st.session_state.selected_sub = "Contracts Distribution"
            st.rerun()
    st.header("Regenerate Distribution")
    contract_row, selected_contract_name = get_contract_selection()
    
    if contract_row is None:
        return
    
    load_all()
    lessors_df = st.session_state.lessors_df.copy()
    store_monthly_sales_df = load_df(STORE_MONTHLY_SALES_TABLE, STORE_MONTHLY_SALES_COLS)
    services_df = st.session_state.services_df.copy()
    contract_services_df = st.session_state.contract_services_df.copy()
    
    # Check if distribution exists
    contract_type = contract_row.get('contract_type', '')
    distribution_exists = check_distribution_exists(contract_row['id'], contract_type)
    
    if not distribution_exists:
        st.info("No distribution exists for this contract. Use 'Generate Distribution' to create it first.")
    else:
        st.warning("⚠️ Regenerating will replace all existing distribution data for this contract.")
        if st.button("Regenerate Distribution", key="btn_regenerate_distribution", type="primary"):
            with st.spinner("Regenerating distribution data..."):
                distribution_rows = generate_contract_distribution(contract_row, lessors_df, store_monthly_sales_df, services_df, contract_services_df)
                service_distribution_rows = generate_service_distribution(contract_row, services_df, contract_services_df)

                if distribution_rows:
                    try:
                        # Get the correct table and columns for this contract type
                        dist_table = get_distribution_table(contract_type)
                        dist_cols = get_distribution_storage_cols(contract_type)
                        
                        agg_dist = aggregate_distribution_rows_for_db(contract_type, distribution_rows)
                        dist_df = pd.DataFrame(agg_dist)
                        for col in dist_cols:
                            if col not in dist_df.columns:
                                dist_df[col] = None if '_date' in col.lower() else ""
                        dist_df = dist_df[dist_cols]

                        # Load existing distribution from the correct table and remove this contract's data
                        existing_dist_df_local = load_df(dist_table, dist_cols)
                        existing_dist_df_local = existing_dist_df_local[existing_dist_df_local['contract_id'] != contract_row['id']]
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
                    _cid = str(contract_row["id"])
                    if service_distribution_rows:
                        service_dist_df = pd.DataFrame(
                            aggregate_service_distribution_for_db(service_distribution_rows)
                        )
                        existing_service_dist_df_local = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
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
                    else:
                        existing_service_dist_df_local = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
                        if not existing_service_dist_df_local.empty:
                            trimmed = existing_service_dist_df_local[
                                existing_service_dist_df_local["contract_id"].astype(str) != _cid
                            ]
                            if len(trimmed) != len(existing_service_dist_df_local):
                                if not save_df(trimmed, SERVICE_DISTRIBUTION_TABLE):
                                    st.error("Failed to clear service distribution for this contract.")
                                    return

                    # Delete old payment records and create new ones AFTER both distributions are saved
                    # This ensures distribution IDs are available when creating payments
                    create_payment_records_from_distribution(
                        contract_row['id'],
                        contract_type,
                        contract_row,
                        distribution_rows=distribution_rows,
                        service_distribution_rows=service_distribution_rows,
                    )

                    # Log action
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='regenerate',
                        entity_type='distribution',
                        entity_id=contract_row['id'],
                        entity_name=contract_row.get('contract_name', ''),
                        action_details=(
                            f"Regenerated distribution: {len(distribution_rows)} contract rows, "
                            f"{len(service_distribution_rows)} service rows; payments refreshed"
                        ),
                        ip_address=get_user_ip()
                    )
                    st.success(f"✅ Distribution regenerated successfully! Created {len(distribution_rows)} contract rows and {len(service_distribution_rows)} service rows.")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Failed to generate distribution data. Please check contract details.")

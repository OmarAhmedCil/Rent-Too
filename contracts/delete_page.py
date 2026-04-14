# Standalone delete contract page (sidebar navigation).
import streamlit as st
import time
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission


def render_delete_contract():
    require_permission("contracts.delete")
    st.header("Delete Contract")
    load_all()
    contracts_df = st.session_state.contracts_df.copy()

    if contracts_df.empty:
        st.info("No contracts available to delete.")
        return

    st.subheader("Filters")
    col1, col2, col3 = st.columns(3)

    with col1:
        filter_contract_name = st.text_input(
            "Filter by Contract Name", value="", key="delete_filter_contract_name"
        )
        filter_contract_type = st.selectbox(
            "Filter by Contract Type",
            options=["All"] + contracts_df["contract_type"].unique().tolist(),
            key="delete_filter_contract_type",
        )

    with col2:
        filter_asset_name = st.text_input(
            "Filter by Asset/Store Name", value="", key="delete_filter_asset_name"
        )
        filter_asset_category = st.selectbox(
            "Filter by Asset Category",
            options=["All"] + contracts_df["asset_category"].unique().tolist(),
            key="delete_filter_asset_category",
        )

    with col3:
        filter_payment_freq = st.selectbox(
            "Filter by Payment Frequency",
            options=["All"] + contracts_df["payment_frequency"].unique().tolist(),
            key="delete_filter_payment_freq",
        )

    filtered_contracts_df = contracts_df.copy()

    if filter_contract_name.strip():
        filtered_contracts_df = filtered_contracts_df[
            filtered_contracts_df["contract_name"].str.contains(
                filter_contract_name.strip(), case=False, na=False
            )
        ]

    if filter_contract_type != "All":
        filtered_contracts_df = filtered_contracts_df[
            filtered_contracts_df["contract_type"] == filter_contract_type
        ]

    if filter_asset_name.strip():
        filtered_contracts_df = filtered_contracts_df[
            filtered_contracts_df["asset_or_store_name"].str.contains(
                filter_asset_name.strip(), case=False, na=False
            )
        ]

    if filter_asset_category != "All":
        filtered_contracts_df = filtered_contracts_df[
            filtered_contracts_df["asset_category"] == filter_asset_category
        ]

    if filter_payment_freq != "All":
        filtered_contracts_df = filtered_contracts_df[
            filtered_contracts_df["payment_frequency"] == filter_payment_freq
        ]

    if filtered_contracts_df.empty:
        st.info("No contracts match the filters.")
        return

    st.markdown("---")

    contract_options = {
        f"{row['id']} - {row['contract_name']}": row["id"]
        for _, row in filtered_contracts_df.iterrows()
    }
    selected_contract_display = st.selectbox(
        "Select Contract to Delete",
        options=[""] + list(contract_options.keys()),
        key="delete_contract_select",
    )

    if not selected_contract_display:
        return

    contract_id = contract_options[selected_contract_display]
    contract_row = filtered_contracts_df[filtered_contracts_df["id"] == contract_id].iloc[0]

    st.markdown("---")
    st.warning(
        f"You are about to delete contract: **{contract_row['contract_name']}** (ID: {contract_id})"
    )
    st.write(f"**Contract Type:** {contract_row['contract_type']}")
    st.write(f"**Asset/Store:** {contract_row.get('asset_or_store_name', 'N/A')}")
    st.write(f"**Commencement Date:** {contract_row.get('commencement_date', 'N/A')}")
    st.write(f"**End Date:** {contract_row.get('end_date', 'N/A')}")

    st.markdown("---")
    st.error(
        "**WARNING:** This cannot be undone. Related lessor links and distribution rows are removed."
    )

    confirm_text = st.text_input("Type 'DELETE' to confirm", key="delete_confirm_text")

    if st.button("Delete Contract", key="delete_contract_btn", type="primary"):
        if confirm_text != "DELETE":
            st.error("Please type 'DELETE' to confirm deletion.")
        else:
            if delete_contract(contract_id):
                current_user = get_current_user()
                log_action(
                    user_id=current_user["id"] if current_user else None,
                    user_name=current_user["name"] if current_user else "System",
                    action_type="delete",
                    entity_type="contract",
                    entity_id=str(contract_id),
                    entity_name=contract_row["contract_name"],
                    action_details=f"Deleted contract: {contract_row['contract_name']}",
                    ip_address=get_user_ip(),
                )
                st.success(f"Contract deleted (ID {contract_id})")
                load_all()
                st.session_state.pop("contracts_mgmt_pending_delete", None)
                st.session_state.selected_main = "\U0001f4c4 Contracts"
                st.session_state.selected_sub = "Contract Management"
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Failed to delete contract.")

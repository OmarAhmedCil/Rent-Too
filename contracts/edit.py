# Contract edit page (full form).
import streamlit as st
import json
import time
import pandas as pd
from datetime import date
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission

def render_edit_contract():
    require_permission('contracts.edit')
    st.header("Edit Contract")
    bc1, bc2 = st.columns([1, 4])
    with bc1:
        if st.button("\u2190 Management", key="edit_back_to_management"):
            st.session_state.pop("contracts_edit_target_id", None)
            st.session_state.pop("contracts_editing_id", None)
            st.session_state.pop("edit_contract_select", None)
            st.session_state.selected_main = "\U0001f4c4 Contracts"
            st.session_state.selected_sub = "Contract Management"
            st.rerun()
    load_all()
    contracts_df = st.session_state.contracts_df.copy()
    lessors_df = st.session_state.lessors_df.copy()
    assets_df = st.session_state.assets_df.copy()
    stores_df = st.session_state.stores_df.copy()
    contract_lessors_df = st.session_state.contract_lessors_df.copy()
    
    if contracts_df.empty:
        st.info("No contracts available to edit.")
        return

    filter_keys = [
        "edit_filter_contract_name",
        "edit_filter_contract_type",
        "edit_filter_asset_name",
        "edit_filter_asset_category",
        "edit_filter_payment_freq",
    ]
    if "contracts_edit_target_id" in st.session_state:
        st.session_state["contracts_editing_id"] = str(
            st.session_state.pop("contracts_edit_target_id")
        )
        for key in filter_keys:
            st.session_state.pop(key, None)
        st.session_state.pop("edit_contract_select", None)
    elif "edit_contract_select_id" in st.session_state:
        st.session_state["contracts_editing_id"] = str(
            st.session_state.pop("edit_contract_select_id")
        )
        for key in filter_keys:
            st.session_state.pop(key, None)
        st.session_state.pop("edit_contract_select", None)

    focus_id = st.session_state.get("contracts_editing_id")

    if focus_id:
        match = contracts_df[contracts_df["id"].astype(str) == str(focus_id)]
        if match.empty:
            st.error("Contract not found or was removed.")
            st.session_state.pop("contracts_editing_id", None)
            return
        contract_id_str = str(focus_id)
        contract_row = match.iloc[0]
        st.caption(
            f"Editing **{contract_row.get('contract_name', '')}** · ID `{contract_id_str}`"
        )
    else:
        contract_options = {
            f"{row['id']} - {row['contract_name']}": row["id"]
            for _, row in contracts_df.iterrows()
        }
        sorted_labels = sorted(
            contract_options.keys(),
            key=lambda lbl: str(contract_options[lbl]),
        )
        selected_contract_display = st.selectbox(
            "Select contract to edit",
            options=[""] + sorted_labels,
            key="edit_contract_select",
        )
        if not selected_contract_display:
            return
        contract_id = contract_options[selected_contract_display]
        contract_id_str = str(contract_id)
        contract_row = contracts_df[
            contracts_df["id"].astype(str) == contract_id_str
        ].iloc[0]

    contract_id = contract_row["id"]

    # Contract-scoped session keys (so switching contracts reloads correctly)
    lessors_state_key = f"edit_contract_lessors_{contract_id_str}"
    services_state_key = f"edit_contract_services_{contract_id_str}"

    # Get contract lessors - always reload from database to ensure we have the latest data
    contract_lessors_list = contract_lessors_df[contract_lessors_df['contract_id'].astype(str) == contract_id_str]
    
    # Initialize or reload lessors from database
    # Check if we need to reload (key doesn't exist or contract changed)
    current_contract_key = st.session_state.get(f"edit_current_contract_id", None)
    should_reload_lessors = (
        lessors_state_key not in st.session_state 
        or current_contract_key != contract_id_str
        or len(st.session_state.get(lessors_state_key, [])) == 0
    )
    
    if should_reload_lessors:
        st.session_state[lessors_state_key] = []
        print(f"[DEBUG Edit Contract] Loading lessors for contract {contract_id_str}")
        print(f"[DEBUG Edit Contract] Contract lessors found: {len(contract_lessors_list)}")
        
        if not contract_lessors_list.empty:
            for _, cl_row in contract_lessors_list.iterrows():
                lessor_id_str = str(cl_row['lessor_id'])
                lessor_row = lessors_df[lessors_df['id'].astype(str) == lessor_id_str]
                if not lessor_row.empty:
                    st.session_state[lessors_state_key].append({
                        "id": lessor_id_str,
                        "name": lessor_row.iloc[0]['name'],
                        "share": float(cl_row['share_pct']),
                        "supplier_code": lessor_row.iloc[0].get('supplier_code', '')
                    })
                    print(f"[DEBUG Edit Contract] Added lessor: {lessor_row.iloc[0]['name']} (ID: {lessor_id_str}, Share: {cl_row['share_pct']}%)")
                else:
                    print(f"[DEBUG Edit Contract] WARNING: Lessor ID {lessor_id_str} not found in lessors_df")
        else:
            print(f"[DEBUG Edit Contract] No lessors found in contract_lessors table for contract {contract_id_str}")
        
        print(f"[DEBUG Edit Contract] Total lessors loaded into state: {len(st.session_state[lessors_state_key])}")
        # Store current contract ID to detect contract changes
        st.session_state[f"edit_current_contract_id"] = contract_id_str
    
    # Get contract services - always reload from database to ensure we have the latest data
    contract_services_df = st.session_state.contract_services_df.copy()
    contract_services_list = contract_services_df[contract_services_df['contract_id'].astype(str) == contract_id_str]
    services_df = st.session_state.services_df.copy()
    
    # Load contract_service_lessors_df - ensure it's loaded properly
    if "contract_service_lessors_df" not in st.session_state:
        # Try to load it if not in session state
        try:
            st.session_state.contract_service_lessors_df = load_df(CONTRACT_SERVICE_LESSORS_TABLE, CONTRACT_SERVICE_LESSORS_COLS)
        except Exception:
            st.session_state.contract_service_lessors_df = pd.DataFrame(columns=CONTRACT_SERVICE_LESSORS_COLS)
    
    contract_service_lessors_df = st.session_state.contract_service_lessors_df.copy() if not st.session_state.contract_service_lessors_df.empty else pd.DataFrame(columns=CONTRACT_SERVICE_LESSORS_COLS)
    
    # Initialize or reload services from database
    # Check if we need to reload (key doesn't exist or contract changed)
    # Use the same current_contract_key check as lessors (already set above)
    should_reload_services = (
        services_state_key not in st.session_state 
        or current_contract_key != contract_id_str
        or len(st.session_state.get(services_state_key, [])) == 0
    )
    
    if should_reload_services:
        st.session_state[services_state_key] = []
        # Debug logging
        print(f"[DEBUG Edit Contract] Contract ID: {contract_id_str}")
        print(f"[DEBUG Edit Contract] Contract services found: {len(contract_services_list)}")
        print(f"[DEBUG Edit Contract] Services state key: {services_state_key}")
        print(f"[DEBUG Edit Contract] Current contract key: {current_contract_key}")
        
        if not contract_services_list.empty:
            for _, cs_row in contract_services_list.iterrows():
                service_id_from_db = str(cs_row['service_id'])
                service_row = services_df[services_df['id'].astype(str) == service_id_from_db]
                if not service_row.empty:
                    svc = {
                        "id": service_id_from_db,
                        "name": service_row.iloc[0]['name'],
                        "currency": service_row.iloc[0].get('currency', 'EGP'),
                        "amount": float(cs_row.get('amount', 0) or 0),
                        "yearly_increase_pct": float(cs_row.get('yearly_increase_pct', 0) or 0)
                    }
                    # Load per-service lessor allocations if available
                    svc_lessors = []
                    if contract_service_lessors_df is not None and isinstance(contract_service_lessors_df, pd.DataFrame) and not contract_service_lessors_df.empty:
                        try:
                            mask = (
                                (contract_service_lessors_df['contract_id'].astype(str) == contract_id_str)
                                & (contract_service_lessors_df['service_id'].astype(str) == service_id_from_db)
                            )
                            matching_lessors = contract_service_lessors_df[mask]
                            if not matching_lessors.empty:
                                for _, sl_row in matching_lessors.iterrows():
                                    lessor_row = lessors_df[lessors_df['id'].astype(str) == str(sl_row['lessor_id'])]
                                    if not lessor_row.empty:
                                        svc_lessors.append({
                                            "id": sl_row['lessor_id'],
                                            "name": lessor_row.iloc[0]['name'],
                                            "share": float(sl_row.get('share_pct', 0) or 0)
                                        })
                        except Exception as e:
                            # If there's an error loading service lessors, continue without them
                            print(f"[DEBUG] Error loading service lessors for service {service_id_from_db}: {e}")
                    svc["lessors"] = svc_lessors
                    st.session_state[services_state_key].append(svc)
                    print(f"[DEBUG Edit Contract] Added service: {svc['name']} (ID: {svc['id']}, Amount: {svc['amount']})")
                else:
                    print(f"[DEBUG Edit Contract] WARNING: Service ID {service_id_from_db} not found in services_df")
        else:
            print(f"[DEBUG Edit Contract] No services found in contract_services table for contract {contract_id_str}")
        
        print(f"[DEBUG Edit Contract] Total services loaded into state: {len(st.session_state[services_state_key])}")
    
    st.markdown("---")
    
    # First row: Contract name and Currency
    col_name, col_currency = st.columns(2)
    with col_name:
        contract_name = st.text_input("Contract name", value=contract_row['contract_name'], key="edit_c_name")
    with col_currency:
        currency = st.selectbox("Currency", options=["EGP", "USD"], index=0 if contract_row['currency'] == "EGP" else 1, key="edit_currency")
    
    # Second row: Date fields
    col_date1, col_date2, col_date3, col_date4 = st.columns(4)
    with col_date1:
        commencement_date = st.date_input("Commencement date", value=pd.to_datetime(contract_row['commencement_date']).date(), key="edit_commencement_date")
    with col_date2:
        tenure_years = st.number_input("Tenure years", min_value=0, value=int(contract_row['tenure_months']) // 12, key="edit_tenure_years")
    with col_date3:
        tenure_months_only = st.number_input("Tenure months (0-11)", min_value=0, max_value=11, value=int(contract_row['tenure_months']) % 12, key="edit_tenure_months_only")
    with col_date4:
        tenure_months = int(tenure_years)*12 + int(tenure_months_only)
        end_date_iso = calc_end_date_iso(commencement_date, tenure_months)
        st.write("**End date:**")
        st.write(end_date_iso if end_date_iso else "N/A")
    
    st.subheader("Asset")
    category_choice = st.selectbox("Select category", options=["Store","Other"], index=0 if contract_row['asset_category'] == "Store" else 1, key="edit_category_choice")
    
    if category_choice == "Store":
        contract_type = st.selectbox("Contract type", options=["Fixed","Revenue Share","ROU"], 
                                    index=["Fixed","Revenue Share","ROU"].index(contract_row['contract_type']) if contract_row['contract_type'] in ["Fixed","Revenue Share","ROU"] else 0, 
                                    key="edit_c_type")
    else:
        contract_type = st.selectbox("Contract type", options=["Fixed","ROU"], 
                                    index=0 if contract_row['contract_type'] == "Fixed" else 1, 
                                    key="edit_c_type")
    selected_asset_or_store = None
    
    if category_choice == "Store":
        stores_map = {r['id']: r['name'] for _, r in stores_df.iterrows()}
        store_choice = st.selectbox("Select store", options=[""] + list(stores_map.keys()), 
                                   format_func=lambda x: "" if x=="" else f"{x} - {stores_map[x]}",
                                   index=0 if contract_row['asset_or_store_id'] not in stores_map else list(stores_map.keys()).index(contract_row['asset_or_store_id']) + 1,
                                   key="edit_store_choice")
        if store_choice:
            selected = stores_df[stores_df['id'] == store_choice].iloc[0]
            selected_asset_or_store = {"id": selected['id'], "name": selected['name'], "cost_center": selected['cost_center']}
    else:
        assets_map = {r['id']: r['name'] for _, r in assets_df.iterrows()}
        asset_choice = st.selectbox("Select asset", options=[""] + list(assets_map.keys()), 
                                   format_func=lambda x: "" if x=="" else f"{x} - {assets_map[x]}",
                                   index=0 if contract_row['asset_or_store_id'] not in assets_map else list(assets_map.keys()).index(contract_row['asset_or_store_id']) + 1,
                                   key="edit_asset_choice")
        if asset_choice:
            a = assets_df[assets_df['id'] == asset_choice].iloc[0]
            selected_asset_or_store = {"id": a['id'], "name": a['name'], "cost_center": a['cost_center']}
    
    st.markdown("---")
    st.subheader("Lessors")
    
    # Get lessors from session state - ensure it's initialized
    if lessors_state_key not in st.session_state:
        st.session_state[lessors_state_key] = []
    
    lessors_list = st.session_state[lessors_state_key]
    lessor_names = lessors_df['name'].tolist()
    
    # Initialize counter for lessor selector reset (per contract)
    edit_lessor_counter_key = f"edit_lessor_counter_{contract_id_str}"
    if edit_lessor_counter_key not in st.session_state:
        st.session_state[edit_lessor_counter_key] = 0
    
    lcol1, lcol2, lcol3 = st.columns([4, 2, 2])
    with lcol1:
        sel_less = st.selectbox("Select lessor (by name)", options=[""] + lessor_names, key=f"edit_sel_less_name_{st.session_state[edit_lessor_counter_key]}")
    with lcol2:
        sel_share = st.number_input("Share %", min_value=0.0, max_value=100.0, value=0.0, step=0.1, key=f"edit_sel_share_{st.session_state[edit_lessor_counter_key]}")
    with lcol3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Add lessor", key="edit_btn_add_lessor"):
            if not sel_less or sel_share <= 0:
                st.error("Select lessor and enter share > 0.")
            else:
                row = lessors_df[lessors_df['name'] == sel_less].iloc[0]
                # Use lessors_list which references the session state
                if any(str(x['id']) == str(row['id']) for x in lessors_list):
                    st.warning("This lessor is already added.")
                else:
                    lessors_list.append({
                        "id": row['id'], "name": row['name'], "share": float(sel_share), "supplier_code": row.get('supplier_code', '')
                    })
                    # Increment counter to force widget reset
                    st.session_state[edit_lessor_counter_key] += 1
                    st.success("Lessor added.")
                    st.rerun()
    
    # Display lessors (lessors_list is already defined above)
    print(f"[DEBUG Edit Contract Display] Lessors state key: {lessors_state_key}")
    print(f"[DEBUG Edit Contract Display] Lessors in state: {len(lessors_list)}")
    if lessors_list:
        print(f"[DEBUG Edit Contract Display] Lessor names: {[l.get('name', 'Unknown') for l in lessors_list]}")
    
    if lessors_list:
        st.markdown("### Assigned Lessors")
        for idx, ls in enumerate(lessors_list.copy()):
            cols = st.columns([6, 1])
            with cols[0]:
                supplier_code_display = f" ({ls.get('supplier_code', '')})" if ls.get('supplier_code', '').strip() else ""
                st.markdown(f"- {ls['name']}{supplier_code_display} - {ls['share']}%")
            with cols[1]:
                if st.button("Delete", key=f"edit_del_lessor_{idx}"):
                    lessors_list.pop(idx)
                    st.rerun()
    else:
        st.info("No lessors added to this contract yet.")
    
    total_share = sum(float(x['share']) for x in lessors_list) if lessors_list else 0.0
    st.markdown(f"**Total lessor shares = {total_share:.2f}%**")
    if abs(total_share - 100.0) > 1e-6:
        st.warning("Total lessor shares must equal 100%.")
    
    st.markdown("---")
    st.subheader("Services")
    # Services are already loaded above when contract is selected/changed
    services_df = st.session_state.services_df.copy()
    service_names = services_df['name'].tolist()
    if not service_names:
        st.info("No services available. Add services in Manage Services tab.")
    else:
        # Initialize counter for service selector reset
        edit_service_counter_key = f"edit_service_counter_{contract_id_str}"
        if edit_service_counter_key not in st.session_state:
            st.session_state[edit_service_counter_key] = 0
        
        scol1, scol2, scol3, scol4 = st.columns([3, 2, 2, 1])
        with scol1:
            sel_service = st.selectbox("Select service (by name)", options=[""] + service_names, key=f"edit_sel_service_name_{st.session_state[edit_service_counter_key]}")
        with scol2:
            # Get currency from selected service
            service_currency = "EGP"
            if sel_service:
                service_row = services_df[services_df['name'] == sel_service]
                if not service_row.empty:
                    service_currency = service_row.iloc[0].get('currency', 'EGP')
            sel_service_amount = st.number_input(f"Amount ({service_currency})", min_value=0.0, value=0.0, step=0.01, key=f"edit_sel_service_amount_{st.session_state[edit_service_counter_key]}")
        with scol3:
            sel_service_yearly_increase = st.number_input("Yearly Increase %", min_value=0.0, max_value=100.0, value=0.0, step=0.1, key=f"edit_sel_service_yearly_increase_{st.session_state[edit_service_counter_key]}")
        with scol4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Add service", key="edit_btn_add_service"):
                if not sel_service or sel_service_amount <= 0:
                    st.error("Select service and enter amount > 0.")
                else:
                    row = services_df[services_df['name'] == sel_service].iloc[0]
                    if any(str(x['id']) == str(row['id']) for x in services_list):
                        st.warning("This service is already added.")
                    else:
                        services_list.append({
                            "id": row['id'], 
                            "name": row['name'],
                            "currency": row.get('currency', 'EGP'),
                            "amount": float(sel_service_amount),
                            "yearly_increase_pct": float(sel_service_yearly_increase),
                            "lessors": []
                        })
                        # Increment counter to force widget reset
                        st.session_state[edit_service_counter_key] += 1
                        st.success("Service added.")
                        st.rerun()
    
    # Get services from session state - use the actual state key
    if services_state_key not in st.session_state:
        st.session_state[services_state_key] = []
    
    services_list = st.session_state[services_state_key]
    print(f"[DEBUG Edit Contract Display] Services state key: {services_state_key}")
    print(f"[DEBUG Edit Contract Display] Services in state: {len(services_list)}")
    if services_list:
        print(f"[DEBUG Edit Contract Display] Service names: {[s.get('name', 'Unknown') for s in services_list]}")
    
    if services_list:
        st.markdown("### Assigned Services")
        for idx, svc in enumerate(services_list.copy()):
            # Ensure per-service lessor allocation exists; initialize as empty list if not present
            if "lessors" not in svc or not isinstance(svc["lessors"], list):
                services_list[idx]["lessors"] = []
                svc = services_list[idx]

            cols = st.columns([6, 1])
            with cols[0]:
                yearly_inc_text = f" (Yearly Increase: {svc.get('yearly_increase_pct', 0)}%)" if svc.get('yearly_increase_pct', 0) > 0 else ""
                service_currency = svc.get('currency', 'EGP')
                st.markdown(f"**{svc['name']}** - {svc['amount']} {service_currency}{yearly_inc_text}")

                # Per-service lessor allocation UI - always visible, no expander
                st.markdown("**Assign lessors for this service:**")
                
                # Initialize counter for service lessor selector reset
                svc_lessor_counter_key = f"edit_svc_{svc['id']}_lessor_counter"
                if svc_lessor_counter_key not in st.session_state:
                    st.session_state[svc_lessor_counter_key] = 0
                
                # Add new lessor for this service - allow selecting ANY lessor
                all_lessor_names = lessors_df['name'].tolist()
                sl_col1, sl_col2, sl_col3 = st.columns([4, 2, 1])
                with sl_col1:
                    sel_service_lessor = st.selectbox(
                        "Select lessor (by name)",
                        options=[""] + all_lessor_names,
                        key=f"edit_svc_{svc['id']}_sel_lessor_{st.session_state[svc_lessor_counter_key]}"
                    )
                with sl_col2:
                    sel_service_share = st.number_input(
                        "Share %",
                        min_value=0.0,
                        max_value=100.0,
                        value=0.0,
                        step=0.1,
                        key=f"edit_svc_{svc['id']}_sel_share_{st.session_state[svc_lessor_counter_key]}"
                    )
                with sl_col3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("Add", key=f"edit_svc_{svc['id']}_btn_add_lessor"):
                        if not sel_service_lessor or sel_service_share <= 0:
                            st.error("Select lessor and enter share > 0.")
                        else:
                            # Find lessor row from all lessors (not just contract lessors)
                            lessor_row = lessors_df[lessors_df['name'] == sel_service_lessor]
                            if lessor_row.empty:
                                st.error("Selected lessor not found.")
                            else:
                                src_ls = lessor_row.iloc[0]
                                if any(str(x['id']) == str(src_ls['id']) for x in svc["lessors"]):
                                    st.warning("This lessor is already added for this service.")
                                else:
                                    services_list[idx]["lessors"].append({
                                        "id": str(src_ls['id']),
                                        "name": src_ls['name'],
                                        "share": float(sel_service_share)
                                    })
                                    # Increment counter to force widget reset
                                    st.session_state[svc_lessor_counter_key] += 1
                                    st.success("Service lessor added.")
                                    st.rerun()

                # List assigned lessors for this service
                svc_lessors = services_list[idx]["lessors"]
                if svc_lessors:
                    st.markdown("**Assigned Service Lessors:**")
                    for li, ls in enumerate(svc_lessors.copy()):
                        lcols = st.columns([6, 1])
                        with lcols[0]:
                            st.markdown(f"- {ls['name']} - {ls.get('share', 0)}%")
                        with lcols[1]:
                            if st.button("Delete", key=f"edit_svc_{svc['id']}_del_lessor_{li}"):
                                services_list[idx]["lessors"].pop(li)
                                st.rerun()

                    total_service_share = sum(float(x.get("share", 0) or 0) for x in svc_lessors)
                    st.markdown(f"**Total service lessor shares = {total_service_share:.2f}%**")
                    if abs(total_service_share - 100.0) > 1e-6:
                        st.warning("For this service, total lessor shares should equal 100%.")
                else:
                    st.info("No lessors assigned to this service yet. Add at least one.")
                
                st.markdown("---")  # Separator between services

            with cols[1]:
                if st.button("Delete", key=f"edit_del_service_{idx}"):
                    services_list.pop(idx)
                    st.rerun()
    else:
        st.info("No services added to this contract yet.")
    
    st.markdown("---")
    st.subheader("Special Conditions")
    
    # First Payment Date is automatically set to Commencement Date
    first_payment_date = commencement_date
    
    # Define contract type flags before using them
    is_rou = (contract_type == "ROU")
    is_revenue_share = (contract_type == "Revenue Share")
    is_fixed = (contract_type == "Fixed")
    
    # Field visibility and behavior by contract type:
    # - All fields are shown for all contract types, but some are disabled based on type
    # - Fixed: rent_amount (enabled), discount_rate (disabled), rev_* fields (disabled), free_months (enabled), advance_payment (enabled)
    # - Revenue Share: rent_amount (disabled), discount_rate (disabled), rev_* fields (enabled), free_months (enabled), advance_payment (disabled)
    # - ROU: rent_amount (enabled), discount_rate (enabled), rev_* fields (disabled), free_months (enabled), advance_months (enabled), advance_payment (disabled)
    
    # ── Helper to safely read a float from contract_row ──────────
    def _fval(key, default=0.0):
        v = contract_row.get(key, default) or default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    # Safe defaults — always defined so the save block always has values
    discount_rate = _fval('discount_rate')
    tax_per = _fval('tax')
    payment_freq_options = ["Yearly", "2 Months", "Monthly", "Quarter"]
    payment_freq_val = contract_row.get('payment_frequency', 'Monthly') or 'Monthly'
    payment_freq_index = payment_freq_options.index(payment_freq_val) if payment_freq_val in payment_freq_options else 2
    payment_frequency = payment_freq_val
    rent_amount = _fval('rent_amount')
    rev_min = _fval('rev_min')
    rev_max = _fval('rev_max')
    rev_share_pct = _fval('rev_share_pct')
    rev_share_after_max_pc = _fval('rev_share_after_max_pc')
    sales_type = contract_row.get('sales_type', 'Net') or 'Net'
    yearly_increase_type = str(contract_row.get('yearly_increase_type', 'Increased %') or 'Increased %')
    yearly_increase = _fval('yearly_increase')
    yearly_increase_fixed_amount = _fval('yearly_increase_fixed_amount')

    if is_fixed:
        # ── Fixed: Rent, Tax, Payment Frequency ───────────────
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            rent_amount = st.number_input(
                "Rent Amount (EGP/month)",
                min_value=0.0, value=_fval('rent_amount'),
                key="edit_rent_amount",
                help="Monthly rent amount"
            )
            tax_per = st.number_input(
                "Tax (%)", min_value=0.0, max_value=100.0, value=_fval('tax'), key="edit_tax"
            )
        with col_f2:
            payment_frequency = st.selectbox(
                "Payment frequency",
                options=payment_freq_options,
                index=payment_freq_index,
                key="edit_payment_frequency"
            )

    elif is_revenue_share:
        # ── Revenue Share: Tax, Frequency, Revenue fields, Sales Type ──
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            tax_per = st.number_input(
                "Tax (%)", min_value=0.0, max_value=100.0, value=_fval('tax'), key="edit_tax"
            )
            rev_min = st.number_input(
                "Revenue minimum (EGP)", min_value=0.0, value=_fval('rev_min'), key="edit_rev_min"
            )
            rev_share_pct = st.number_input(
                "Revenue share %", min_value=0.0, max_value=100.0,
                value=_fval('rev_share_pct'), key="edit_rev_share_pct"
            )
        with col_r2:
            payment_frequency = st.selectbox(
                "Payment frequency",
                options=payment_freq_options,
                index=payment_freq_index,
                key="edit_payment_frequency"
            )
            rev_max = st.number_input(
                "Revenue maximum (EGP)", min_value=0.0, value=_fval('rev_max'), key="edit_rev_max"
            )
            rev_share_after_max_pc = st.number_input(
                "Share % after maximum", min_value=0.0, max_value=100.0,
                value=_fval('rev_share_after_max_pc'), key="edit_rev_share_after_max_pc"
            )
        sales_type_options = ["Net", "Total without discount"]
        current_sales_type = contract_row.get('sales_type', 'Net') or 'Net'
        sales_type = st.selectbox(
            "Sales Type",
            options=sales_type_options,
            index=sales_type_options.index(current_sales_type) if current_sales_type in sales_type_options else 0,
            key="edit_sales_type"
        )

    elif is_rou:
        # ── ROU: Rent, Discount Rate, Tax, Payment Frequency ──
        col_o1, col_o2 = st.columns(2)
        with col_o1:
            rent_amount = st.number_input(
                "Rent Amount (EGP/month)",
                min_value=0.0, value=_fval('rent_amount'),
                key="edit_rent_amount",
                help="Monthly rent amount"
            )
            tax_per = st.number_input(
                "Tax (%)", min_value=0.0, max_value=100.0, value=_fval('tax'), key="edit_tax"
            )
        with col_o2:
            discount_rate = st.number_input(
                "Discount rate (%)",
                min_value=0.0, max_value=100.0, value=_fval('discount_rate'),
                key="edit_discount_rate",
                help="Annual discount rate (required for ROU contracts)"
            )
            payment_frequency = st.selectbox(
                "Payment frequency",
                options=payment_freq_options,
                index=payment_freq_index,
                key="edit_payment_frequency"
            )

    # Initialize variables
    free_months_input = ""
    advance_months_input = ""
    rent_per_year_json = ""
    advance_payment = 0.0
    increase_mode_code_existing = str(contract_row.get('increase_by_period_mode', 'legacy') or 'legacy').strip().lower()
    if increase_mode_code_existing not in ("legacy", "all", "specific", "year_rules"):
        increase_mode_code_existing = "legacy"
    increase_mode_label_map = {
        "all": "All periods",
        "specific": "By contract years",
        "year_rules": "By contract years",
        "legacy": "All periods",
    }
    increase_mode = increase_mode_label_map.get(increase_mode_code_existing, "All periods")
    try:
        increase_all_pct = float(contract_row.get('increase_by_period_all_pct', 0) or 0)
    except Exception:
        increase_all_pct = 0.0
    increase_map_input = ""
    increase_value_type = "Percent (%)"
    existing_year_rules = []
    try:
        map_raw = str(contract_row.get('increase_by_period_map', '') or '').strip()
        map_dict = json.loads(map_raw) if map_raw else {}
        if isinstance(map_dict, dict):
            if "year_rules" in map_dict and isinstance(map_dict.get("year_rules"), list):
                existing_year_rules = map_dict.get("year_rules", [])
                if str(map_dict.get("all_value_type", "percent")).strip().lower() == "amount":
                    increase_value_type = "Fixed Amount"
            elif map_dict:
                increase_map_input = ", ".join([f"{k}:{v}" for k, v in sorted(map_dict.items(), key=lambda x: int(x[0]))])
    except Exception:
        increase_map_input = ""

    st.markdown("### Increase by Period")
    mode_options = ["All periods", "By contract years"]
    increase_mode = st.selectbox(
        "Increase mode",
        options=mode_options,
        index=mode_options.index(increase_mode) if increase_mode in mode_options else 0,
        key="edit_increase_mode",
        help="All periods: one increase every period. By contract years: assign increase rules to contract years."
    )
    increase_value_type = st.selectbox(
        "Increase value type",
        options=["Percent (%)", "Fixed Amount"],
        index=0 if increase_value_type == "Percent (%)" else 1,
        key="edit_increase_value_type",
    )
    if increase_mode == "All periods":
        yearly_increase = 0.0
        yearly_increase_fixed_amount = 0.0
        increase_all_pct = st.number_input(
            "Increase value for every period",
            min_value=0.0,
            max_value=1000000.0,
            value=float(increase_all_pct),
            step=0.1,
            key="edit_increase_all_pct",
        )
    else:
        yearly_increase = 0.0
        yearly_increase_fixed_amount = 0.0
        # Contract year count rule:
        # full years + 1 extra year when there are remaining months.
        num_years = max(1, (tenure_months // 12) + (1 if (tenure_months % 12) > 0 else 0))
        year_options = [str(y) for y in range(2, num_years + 1)]
        rules_key = f"increase_year_rules_edit_{contract_id_str}"
        reset_inputs_key = f"reset_inc_rule_inputs_edit_{contract_id_str}"
        if rules_key not in st.session_state:
            st.session_state[rules_key] = existing_year_rules
        years_key = f"edit_inc_rule_years_{contract_id_str}"
        value_key = f"edit_inc_rule_val_{contract_id_str}"
        if st.session_state.get(reset_inputs_key, False):
            st.session_state[years_key] = []
            st.session_state[value_key] = 0.0
            st.session_state[reset_inputs_key] = False
        # Exclude years already assigned to a rule so each year can only be chosen once
        _used_years_edit = {
            str(y)
            for rr in st.session_state.get(rules_key, [])
            for y in rr.get("years", [])
        }
        _available_years_edit = [y for y in year_options if y not in _used_years_edit]
        rc1, rc2, rc3 = st.columns([4, 3, 2])
        with rc1:
            selected_years = st.multiselect("Apply to contract years", options=_available_years_edit, key=years_key)
        with rc2:
            if value_key not in st.session_state:
                st.session_state[value_key] = 0.0
            rule_value = st.number_input("Increase value", min_value=0.0, max_value=1000000.0, step=0.1, key=value_key)
        with rc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Add rule", key=f"edit_btn_add_inc_rule_{contract_id_str}"):
                if not selected_years:
                    st.error("Select at least one contract year.")
                else:
                    st.session_state[rules_key].append({
                        "years": sorted({int(y) for y in selected_years}),
                        "value_type": "percent" if increase_value_type == "Percent (%)" else "amount",
                        "value": float(rule_value),
                    })
                    # Defer reset to next rerun (before widgets instantiate) to avoid Streamlit key mutation error.
                    st.session_state[reset_inputs_key] = True
                    st.rerun()
        if st.session_state.get(rules_key):
            st.markdown("**Year Rules**")
            for i, rr in enumerate(st.session_state[rules_key].copy()):
                c1, c2 = st.columns([8, 1])
                with c1:
                    st.write(f"Years {rr.get('years', [])} -> {rr.get('value')} ({rr.get('value_type')})")
                with c2:
                    if st.button("Delete", key=f"edit_del_inc_rule_{contract_id_str}_{i}"):
                        st.session_state[rules_key].pop(i)
                        st.rerun()
    
    # ── Type-specific: Free / Advance months, Advance Payment, ROU settings ──
    def _parse_months(raw) -> list[str]:
        s = str(raw or "").strip()
        return sorted([x.strip() for x in s.split(",") if x.strip().isdigit()], key=int)

    _period_options = [str(i) for i in range(1, tenure_months + 1)]
    free_months_input = ""
    advance_months_input = ""
    advance_payment = 0.0
    rev_share_payment_advance = 0.0
    is_tax_added = False
    rent_per_year_json = ""

    if is_rou:
        st.markdown("### ROU Contract Settings")
        col_rou1, col_rou2 = st.columns(2)
        with col_rou1:
            _free_default = _parse_months(contract_row.get("free_months", ""))
            _free_sel = st.multiselect(
                "Free months (select period numbers)",
                options=_period_options,
                default=[p for p in _free_default if p in _period_options],
                key="edit_free_months",
                help="Periods where rent accrues but no cash payment is made.",
            )
            free_months_input = ",".join(sorted(_free_sel, key=int)) if _free_sel else ""
        with col_rou2:
            _adv_default = _parse_months(contract_row.get("advance_months", ""))
            _adv_sel = st.multiselect(
                "Advance months (select period numbers)",
                options=_period_options,
                default=[p for p in _adv_default if p in _period_options],
                key="edit_advance_months",
                help="Periods paid in advance (before commencement).",
            )
            advance_months_input = ",".join(sorted(_adv_sel, key=int)) if _adv_sel else ""
        is_tax_added = st.checkbox(
            "Is tax added (add +1% to ROU rent calculations)",
            value=str(contract_row.get('is_tax_added', 0) or 0).strip().lower() in ["1", "true", "yes", "y"],
            key="edit_is_tax_added",
            help="When enabled, ROU rent used in calculations is increased by 1%."
        )
        # Build rent_per_year for ROU calculation
        rent_per_year_dict = {}
        num_years = (tenure_months // 12) + (1 if (tenure_months % 12) > 0 else 0)
        for year_num in range(1, num_years + 1):
            yearly_rent = rent_amount * 12 * ((1 + yearly_increase / 100) ** (year_num - 1))
            rent_per_year_dict[str(year_num)] = yearly_rent
        rent_per_year_json = json.dumps(rent_per_year_dict)

    elif is_fixed:
        st.markdown("### Free Months (Discount)")
        _free_default = _parse_months(contract_row.get("free_months", ""))
        _free_sel = st.multiselect(
            "Free months (select period numbers)",
            options=_period_options,
            default=[p for p in _free_default if p in _period_options],
            key="edit_free_months",
            help="Rent is set to 0 with a discount applied for the selected periods.",
        )
        free_months_input = ",".join(sorted(_free_sel, key=int)) if _free_sel else ""
        st.markdown("### Advance Payment")
        try:
            advance_payment_val = contract_row.get('advance_payment', '') if hasattr(contract_row, 'get') else ''
        except (KeyError, AttributeError):
            advance_payment_val = ''
        if pd.isna(advance_payment_val) or str(advance_payment_val).strip() in ('', 'None', 'nan'):
            advance_payment_val = 0.0
        else:
            try:
                advance_payment_val = float(str(advance_payment_val).strip())
            except (ValueError, TypeError):
                advance_payment_val = 0.0
        advance_payment = st.number_input(
            "Advance Payment Amount (EGP)",
            min_value=0.0, value=advance_payment_val, step=0.01,
            key="edit_advance_payment",
            help="Bulk advance payment amount. This will be deducted from rent amounts over time until fully consumed."
        )

    elif is_revenue_share:
        st.markdown("### Free Months (Discount)")
        _free_default = _parse_months(contract_row.get("free_months", ""))
        _free_sel = st.multiselect(
            "Free months (select period numbers)",
            options=_period_options,
            default=[p for p in _free_default if p in _period_options],
            key="edit_free_months",
            help="Rent is set to 0 with a discount applied for the selected periods.",
        )
        free_months_input = ",".join(sorted(_free_sel, key=int)) if _free_sel else ""
        st.markdown("### Advance (Revenue Share)")
        _ram = str(contract_row.get("rev_share_advance_mode") or "none").strip().lower() or "none"
        if _ram in ("", "legacy"):
            _ram = "none"
        _mode_opts = ["none", "chronological", "periods", "spread_proportional"]
        _ram_idx = _mode_opts.index(_ram) if _ram in _mode_opts else 0
        rev_share_advance_mode = st.selectbox(
            "How to apply prepaid advance",
            options=_mode_opts,
            format_func=lambda x: {
                "none": "None (or legacy: deduct on payment lines only, not on distribution)",
                "chronological": "Month by month in order (fills Advance column on distribution)",
                "periods": "Only in selected period numbers (1, 2, 3 …)",
                "spread_proportional": "Spread across all months (share of total due after normal calc)",
            }[x],
            index=_ram_idx,
            key="edit_rev_share_advance_mode",
        )
        _adv_default_rs = _parse_months(contract_row.get("advance_months", ""))
        _adv_sel_rs = st.multiselect(
            "Advance months (for “Only in selected periods”)",
            options=_period_options,
            default=[p for p in _adv_default_rs if p in _period_options],
            key="edit_advance_months_rs",
        )
        advance_months_input = ",".join(sorted(_adv_sel_rs, key=int)) if _adv_sel_rs else ""
        try:
            _rsa_val = float(contract_row.get("rev_share_payment_advance", 0) or 0)
        except (TypeError, ValueError):
            _rsa_val = 0.0
        rev_share_payment_advance = st.number_input(
            "Prepaid advance amount (contract currency)",
            min_value=0.0,
            value=_rsa_val,
            step=0.01,
            key="edit_rev_share_payment_advance",
            help="Total prepaid amount. Behaviour depends on the mode above.",
        )
    
    st.markdown("---")
    if st.button("Update Contract", key="update_contract_btn"):
        errors = []
        if not selected_asset_or_store:
            errors.append("Please select an asset or store.")
        if not contract_name.strip():
            errors.append("Contract name required.")
        if tenure_months <= 0:
            errors.append("Tenure must be > 0 months.")
        if not st.session_state[lessors_state_key]:
            errors.append("Add at least one lessor.")
        if abs(total_share - 100.0) > 1e-6:
            errors.append(f"Total lessor shares must be 100% (current: {total_share:.2f}%).")
        if contract_type == "Revenue Share" and category_choice != "Store":
            errors.append("Revenue Share contract type is only available for Store assets.")
        if contract_type != "Revenue Share" and rent_amount <= 0:
            errors.append("Rent amount is required for Fixed and ROU contracts.")
        if contract_type == "ROU" and discount_rate <= 0:
            errors.append("Discount rate is required for ROU contracts.")
        
        if errors:
            for e in errors:
                st.error(e)
        else:
            increase_mode_code = "all"
            increase_all_pct_val = ""
            increase_map_json = ""
            if increase_mode == "All periods":
                increase_all_pct_val = str(float(increase_all_pct))
                increase_map_json = json.dumps({
                    "all_value_type": "percent" if increase_value_type == "Percent (%)" else "amount"
                })
            elif increase_mode == "By contract years":
                increase_mode_code = "year_rules"
                rules_key = f"increase_year_rules_edit_{contract_id_str}"
                rules = st.session_state.get(rules_key, [])
                increase_map_json = json.dumps({
                    "all_value_type": "percent" if increase_value_type == "Percent (%)" else "amount",
                    "year_rules": rules,
                })

            lessors_json = json.dumps(st.session_state[lessors_state_key], ensure_ascii=False)
            contract_data = {
                "contract_name": contract_name.strip(),
                "contract_type": contract_type,
                "currency": currency,
                "asset_category": category_choice,
                "asset_or_store_id": str(selected_asset_or_store['id']),
                "asset_or_store_name": selected_asset_or_store['name'],
                "commencement_date": str(commencement_date),
                "tenure_months": str(tenure_months),
                "end_date": end_date_iso,
                "lessors_json": lessors_json,
                "discount_rate": str(discount_rate),
                "tax": str(tax_per),
                "is_tax_added": "1" if (is_rou and is_tax_added) else "0",
                "payment_frequency": payment_frequency,
                "yearly_increase": str(yearly_increase),
                "yearly_increase_type": yearly_increase_type,
                "yearly_increase_fixed_amount": str(yearly_increase_fixed_amount),
                "rent_amount": str(rent_amount),
                "rev_min": str(rev_min),
                "rev_max": str(rev_max),
                "rev_share_pct": str(rev_share_pct),
                "rev_share_after_max_pc": str(rev_share_after_max_pc),
                "sales_type": sales_type if is_revenue_share else "",
                # Payment date is always set to commencement date
                "first_payment_date": str(commencement_date),
                # ROU fields
                "rent_per_year": rent_per_year_json if is_rou else "",
                "free_months": free_months_input.strip() if is_rou else (free_months_input.strip() if (contract_type == "Fixed" or contract_type == "Revenue Share") else ""),
                "advance_months": advance_months_input.strip() if (is_rou or is_revenue_share) else "",
                "advance_months_count": str(len([x for x in (advance_months_input or '').split(',') if x.strip().isdigit()])) if (is_rou or is_revenue_share) else "",
                "increase_by_period_mode": increase_mode_code,
                "increase_by_period_all_pct": increase_all_pct_val,
                "increase_by_period_map": increase_map_json,
                "advance_payment": str(advance_payment) if contract_type == "Fixed" else "",
                "rev_share_payment_advance": str(rev_share_payment_advance) if is_revenue_share else "",
                "rev_share_advance_mode": rev_share_advance_mode if is_revenue_share else "",
            }
            
            if update_contract(contract_id, contract_data):
                # Update contract-lessor relationships
                delete_contract_lessors(str(contract_id))
                for lessor in st.session_state[lessors_state_key]:
                    insert_contract_lessor(str(contract_id), str(lessor['id']), str(lessor['share']))
                
                # Update contract-service relationships
                delete_contract_services(str(contract_id))
                delete_contract_service_lessors(str(contract_id))
                for service in st.session_state[services_state_key]:
                    insert_contract_service(
                        str(contract_id), 
                        str(service['id']), 
                        str(service['amount']),
                        str(service.get('yearly_increase_pct', 0))
                    )
                    # Persist per-service lessor allocations if defined and valid
                    service_lessors = service.get("lessors", [])
                    total_share = sum(float(sl.get("share", 0) or 0) for sl in service_lessors) if service_lessors else 0.0
                    if service_lessors and abs(total_share - 100.0) <= 1e-6:
                        for sl in service_lessors:
                            insert_contract_service_lessor(
                                str(contract_id),
                                str(service['id']),
                                str(sl['id']),
                                str(sl.get('share', 0) or 0)
                            )
                
                st.success(f"Contract updated (ID {contract_id})")
                st.session_state[lessors_state_key] = []
                st.session_state[services_state_key] = []
                load_all()
                st.session_state.selected_main = "\U0001f4c4 Contracts"
                st.session_state.selected_sub = "Contract Management"
                st.session_state.pop("contracts_edit_target_id", None)
                st.session_state.pop("contracts_editing_id", None)
                if "edit_contract_select" in st.session_state:
                    del st.session_state["edit_contract_select"]
                st.rerun()
            else:
                st.error("Failed to update contract.")

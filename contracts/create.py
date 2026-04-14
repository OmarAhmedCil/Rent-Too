# Contract creation page
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


def render_create_contract():
    require_permission('contracts.create')
    st.header("Create Contract")
    load_all()
    lessors_df = st.session_state.lessors_df.copy()
    assets_df = st.session_state.assets_df.copy()
    stores_df = st.session_state.stores_df.copy()

    # Keep create-page state isolated and avoid reusing stale rules from previous screens/runs.
    if "increase_year_rules_create" not in st.session_state:
        st.session_state.increase_year_rules_create = []
    if "create_last_increase_mode" not in st.session_state:
        st.session_state.create_last_increase_mode = "All periods"

    # First row: Contract name and Currency
    col_name, col_currency = st.columns(2)
    with col_name:
        contract_name = st.text_input("Contract name", key="c_name")
    with col_currency:
        currency = st.selectbox("Currency", options=["EGP", "USD"], index=0, key="currency")
    
    # Second row: Date fields
    col_date1, col_date2, col_date3, col_date4 = st.columns(4)
    with col_date1:
        commencement_date = st.date_input("Commencement date", value=date.today(), key="commencement_date")
    with col_date2:
        tenure_years = st.number_input("Tenure years", min_value=0, value=0, key="tenure_years")
    with col_date3:
        tenure_months_only = st.number_input("Tenure months (0-11)", min_value=0, max_value=11, value=0, key="tenure_months_only")
    with col_date4:
        tenure_months = int(tenure_years)*12 + int(tenure_months_only)
        end_date_iso = calc_end_date_iso(commencement_date, tenure_months)
        st.write("**End date:**")
        st.write(end_date_iso if end_date_iso else "N/A")

    st.subheader("Asset")
    category_choice = st.selectbox("Select category", options=["Store","Other"], index=1, key="category_choice")
    
    # Contract type - Revenue Share only available for Store
    if category_choice == "Store":
        contract_type = st.selectbox("Contract type", options=["Fixed","Revenue Share","ROU"], index=0, key="c_type")
    else:
        contract_type = st.selectbox("Contract type", options=["Fixed","ROU"], index=0, key="c_type")
    selected_asset_or_store = None

    if category_choice == "Store":
        stores_map = {r['id']: r['name'] for _, r in stores_df.iterrows()}
        if not stores_map:
            st.error("Stores master is empty.")
        store_choice = st.selectbox("Select store", options=[""] + list(stores_map.keys()), format_func=lambda x: "" if x=="" else f"{x}  -  {stores_map[x]}")
        if store_choice:
            selected = stores_df[stores_df['id'] == store_choice].iloc[0]
            selected_asset_or_store = {"id": selected['id'], "name": selected['name'], "cost_center": selected['cost_center']}
            st.write(f"Selected store: **{selected['name']}**  -  cost center: **{selected['cost_center']}**")
    else:
        assets_map = {r['id']: r['name'] for _, r in assets_df.iterrows()}
        if not assets_map:
            st.info("No assets available. Create assets in Tab 3.")
        asset_choice = st.selectbox("Select asset", options=[""] + list(assets_map.keys()), format_func=lambda x: "" if x=="" else f"{x}  -  {assets_map[x]}")
        if asset_choice:
            a = assets_df[assets_df['id'] == asset_choice].iloc[0]
            selected_asset_or_store = {"id": a['id'], "name": a['name'], "cost_center": a['cost_center']}
            st.write(f"Selected asset: **{a['name']}**  -  cost center: **{a['cost_center']}**")

    st.markdown("---")
    st.subheader("Lessors")
    lessor_names = lessors_df['name'].tolist()
    if not lessor_names:
        st.warning("No lessors found. Add lessors first.")
    else:
        # Initialize counter for lessor selector reset
        if "lessor_add_counter" not in st.session_state:
            st.session_state.lessor_add_counter = 0
        
        lcol1, lcol2, lcol3 = st.columns([4, 2, 2])
        with lcol1:
            sel_less = st.selectbox("Select lessor (by name)", options=[""] + lessor_names, key=f"sel_less_name_{st.session_state.lessor_add_counter}")
        with lcol2:
            sel_share = st.number_input("Share %", min_value=0.0, max_value=100.0, value=0.0, step=0.1, key=f"sel_share_{st.session_state.lessor_add_counter}")
        with lcol3:
            st.markdown("<br>", unsafe_allow_html=True)  # Spacer to align button with selectbox
            if st.button("Add lessor", key="btn_add_lessor"):
                if not sel_less or sel_share <= 0:
                    st.error("Select lessor and enter share > 0.")
                else:
                    row = lessors_df[lessors_df['name'] == sel_less].iloc[0]
                    if any(str(x['id']) == str(row['id']) for x in st.session_state.contract_lessors):
                        st.warning("This lessor is already added.")
                    else:
                        st.session_state.contract_lessors.append({
                            "id": row['id'], "name": row['name'], "share": float(sel_share), "supplier_code": row.get('supplier_code', '')
                        })
                        # Increment counter to force widget reset
                        st.session_state.lessor_add_counter += 1
                        st.success("Lessor added.")
                        st.rerun()

    if st.session_state.contract_lessors:
        st.markdown("### Assigned Lessors")
        for idx, ls in enumerate(st.session_state.contract_lessors.copy()):
            cols = st.columns([6, 1])
            with cols[0]:
                supplier_code_display = f" ({ls.get('supplier_code', '')})" if ls.get('supplier_code', '').strip() else ""
                st.markdown(f"{ls['name']}{supplier_code_display}  -  {ls['share']}%")
            with cols[1]:
                if st.button("Delete", key=f"del_lessor_{idx}"):
                    st.session_state.contract_lessors.pop(idx)
                    st.rerun()
    else:
        st.info("No lessors added to this contract yet.")

    total_share = sum(float(x['share']) for x in st.session_state.contract_lessors) if st.session_state.contract_lessors else 0.0
    st.markdown(f"**Total lessor shares = {total_share:.2f}%**")
    if abs(total_share - 100.0) > 1e-6:
        st.warning("Total lessor shares must equal 100%.")

    st.markdown("---")
    st.subheader("Services")
    if "contract_services" not in st.session_state:
        st.session_state.contract_services = []
    
    services_df = st.session_state.services_df.copy()
    service_names = services_df['name'].tolist()
    if not service_names:
        st.info("No services available. Add services in Manage Services tab.")
    else:
        # Initialize counter for service selector reset
        if "service_add_counter" not in st.session_state:
            st.session_state.service_add_counter = 0
        
        scol1, scol2, scol3, scol4 = st.columns([3, 2, 2, 1])
        with scol1:
            sel_service = st.selectbox("Select service (by name)", options=[""] + service_names, key=f"sel_service_name_{st.session_state.service_add_counter}")
        with scol2:
            # Get currency from selected service
            service_currency = "EGP"
            if sel_service:
                service_row = services_df[services_df['name'] == sel_service]
                if not service_row.empty:
                    service_currency = service_row.iloc[0].get('currency', 'EGP')
            sel_service_amount = st.number_input(f"Amount ({service_currency})", min_value=0.0, value=0.0, step=0.01, key=f"sel_service_amount_{st.session_state.service_add_counter}")
        with scol3:
            sel_service_yearly_increase = st.number_input("Yearly Increase %", min_value=0.0, max_value=100.0, value=0.0, step=0.1, key=f"sel_service_yearly_increase_{st.session_state.service_add_counter}")
        with scol4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Add service", key="btn_add_service"):
                if not sel_service or sel_service_amount <= 0:
                    st.error("Select service and enter amount > 0.")
                else:
                    row = services_df[services_df['name'] == sel_service].iloc[0]
                    if any(str(x['id']) == str(row['id']) for x in st.session_state.contract_services):
                        st.warning("This service is already added.")
                    else:
                        st.session_state.contract_services.append({
                            "id": row['id'], 
                            "name": row['name'],
                            "currency": row.get('currency', 'EGP'),
                            "amount": float(sel_service_amount),
                            "yearly_increase_pct": float(sel_service_yearly_increase)
                        })
                        # Increment counter to force widget reset
                        st.session_state.service_add_counter += 1
                        st.success("Service added.")
                        st.rerun()
    
    if st.session_state.contract_services:
        st.markdown("### Assigned Services")
        for idx, svc in enumerate(st.session_state.contract_services.copy()):
            # Ensure per-service lessor allocation exists; initialize as empty list
            if "lessors" not in svc or not isinstance(svc["lessors"], list):
                st.session_state.contract_services[idx]["lessors"] = []
                svc = st.session_state.contract_services[idx]

            cols = st.columns([6, 1])
            with cols[0]:
                yearly_inc_text = f" (Yearly Increase: {svc.get('yearly_increase_pct', 0)}%)" if svc.get('yearly_increase_pct', 0) > 0 else ""
                service_currency = svc.get('currency', 'EGP')
                st.markdown(f"**{svc['name']}**  -  {svc['amount']} {service_currency}{yearly_inc_text}")

                # Per-service lessor allocation UI - always visible, no expander
                st.markdown("**Assign lessors for this service:**")
                
                # Initialize counter for service lessor selector reset
                svc_lessor_counter_key = f"svc_{svc['id']}_lessor_counter"
                if svc_lessor_counter_key not in st.session_state:
                    st.session_state[svc_lessor_counter_key] = 0
                
                # Add new lessor for this service - allow selecting ANY lessor
                all_lessor_names = lessors_df['name'].tolist()
                sl_col1, sl_col2, sl_col3 = st.columns([4, 2, 1])
                with sl_col1:
                    sel_service_lessor = st.selectbox(
                        "Select lessor (by name)",
                        options=[""] + all_lessor_names,
                        key=f"svc_{svc['id']}_sel_lessor_{st.session_state[svc_lessor_counter_key]}"
                    )
                with sl_col2:
                    sel_service_share = st.number_input(
                        "Share %",
                        min_value=0.0,
                        max_value=100.0,
                        value=0.0,
                        step=0.1,
                        key=f"svc_{svc['id']}_sel_share_{st.session_state[svc_lessor_counter_key]}"
                    )
                with sl_col3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("Add", key=f"svc_{svc['id']}_btn_add_lessor"):
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
                                    st.session_state.contract_services[idx]["lessors"].append({
                                        "id": str(src_ls['id']),
                                        "name": src_ls['name'],
                                        "share": float(sel_service_share)
                                    })
                                    # Increment counter to force widget reset
                                    st.session_state[svc_lessor_counter_key] += 1
                                    st.success("Service lessor added.")
                                    st.rerun()

                # List assigned lessors for this service
                svc_lessors = st.session_state.contract_services[idx]["lessors"]
                if svc_lessors:
                    st.markdown("**Assigned Service Lessors:**")
                    for li, ls in enumerate(svc_lessors.copy()):
                        lcols = st.columns([6, 1])
                        with lcols[0]:
                            st.markdown(f"{ls['name']}  -  {ls.get('share', 0)}%")
                        with lcols[1]:
                            if st.button("Delete", key=f"svc_{svc['id']}_del_lessor_{li}"):
                                st.session_state.contract_services[idx]["lessors"].pop(li)
                                st.rerun()

                    total_service_share = sum(float(x.get("share", 0) or 0) for x in svc_lessors)
                    st.markdown(f"**Total service lessor shares = {total_service_share:.2f}%**")
                    if abs(total_service_share - 100.0) > 1e-6:
                        st.warning("For this service, total lessor shares should equal 100%.")
                else:
                    st.info("No lessors assigned to this service yet. Add at least one.")
                
                st.markdown("---")  # Separator between services

            with cols[1]:
                if st.button("Delete", key=f"del_service_{idx}"):
                    st.session_state.contract_services.pop(idx)
                    st.rerun()
    else:
        st.info("No services added to this contract yet.")

    st.markdown("---")
    st.subheader("Special Conditions")
    
    is_rou = (contract_type == "ROU")
    is_revenue_share = (contract_type == "Revenue Share")
    is_fixed = (contract_type == "Fixed")
    
    # Initialize variables
    free_months_input = ""
    advance_months_input = ""
    rent_per_year_json = ""
    increase_mode = "Use current yearly increase"
    increase_all_pct = 0.0
    increase_map_input = ""
    
    # First Payment Date is automatically set to Commencement Date
    first_payment_date = commencement_date
    
    # Safe defaults — always defined so the save block always has values
    discount_rate = 0.0
    tax_per = 0.0
    payment_frequency = "Yearly"
    rent_amount = 0.0
    rev_min = 0.0
    rev_max = 0.0
    rev_share_pct = 0.0
    rev_share_after_max_pc = 0.0
    sales_type = "Net"
    yearly_increase = 0.0
    yearly_increase_fixed_amount = 0.0
    yearly_increase_type = "Increased %"

    if is_fixed:
        # ── Fixed: Rent, Tax, Payment Frequency ───────────────
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            rent_amount = st.number_input(
                "Rent Amount (EGP/month)",
                min_value=0.0, value=0.0, key="rent_amount",
                help="Monthly rent amount"
            )
            tax_per = st.number_input(
                "Tax (%)", min_value=0.0, max_value=100.0, value=0.0, key="tax_per"
            )
        with col_f2:
            payment_frequency = st.selectbox(
                "Payment frequency",
                options=["Yearly", "2 Months", "Monthly", "Quarter"],
                index=0, key="payment_frequency"
            )

    elif is_revenue_share:
        # ── Revenue Share: Tax, Frequency, Revenue fields, Sales Type ──
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            tax_per = st.number_input(
                "Tax (%)", min_value=0.0, max_value=100.0, value=0.0, key="tax_per"
            )
            rev_min = st.number_input(
                "Revenue minimum (EGP)", min_value=0.0, value=0.0, key="rev_min"
            )
            rev_share_pct = st.number_input(
                "Revenue share %", min_value=0.0, max_value=100.0, value=0.0, key="rev_share_pct"
            )
        with col_r2:
            payment_frequency = st.selectbox(
                "Payment frequency",
                options=["Yearly", "2 Months", "Monthly", "Quarter"],
                index=0, key="payment_frequency"
            )
            rev_max = st.number_input(
                "Revenue maximum (EGP)", min_value=0.0, value=0.0, key="rev_max"
            )
            rev_share_after_max_pc = st.number_input(
                "Share % after maximum", min_value=0.0, max_value=100.0, value=0.0, key="rev_share_after_max_pc"
            )
        sales_type = st.selectbox(
            "Sales Type",
            options=["Net", "Total without discount"],
            index=0, key="sales_type"
        )

    elif is_rou:
        # ── ROU: Rent, Discount Rate, Tax, Payment Frequency ──
        col_o1, col_o2 = st.columns(2)
        with col_o1:
            rent_amount = st.number_input(
                "Rent Amount (EGP/month)",
                min_value=0.0, value=0.0, key="rent_amount",
                help="Monthly rent amount"
            )
            tax_per = st.number_input(
                "Tax (%)", min_value=0.0, max_value=100.0, value=0.0, key="tax_per"
            )
        with col_o2:
            discount_rate = st.number_input(
                "Discount rate (%)",
                min_value=0.0, max_value=100.0, value=10.0,
                key="discount_rate",
                help="Annual discount rate (required for ROU contracts)"
            )
            payment_frequency = st.selectbox(
                "Payment frequency",
                options=["Yearly", "2 Months", "Monthly", "Quarter"],
                index=2,
                key="payment_frequency"
            )

    st.markdown("### Increase by Period")
    increase_mode = st.selectbox(
        "Increase mode",
        options=["All periods", "By contract years"],
        index=0,
        key="increase_mode",
        help="All periods: one increase every period. By contract years: assign increase rules to contract years."
    )
    if increase_mode != st.session_state.get("create_last_increase_mode", "All periods"):
        if increase_mode == "By contract years":
            # Reset stale defaults when user switches into year-rules mode.
            st.session_state.increase_year_rules_create = []
        st.session_state.create_last_increase_mode = increase_mode
    increase_value_type = st.selectbox(
        "Increase value type",
        options=["Percent (%)", "Fixed Amount"],
        index=0,
        key="increase_value_type",
    )
    if increase_mode == "All periods":
        increase_all_pct = st.number_input(
            "Increase value for every period",
            min_value=0.0,
            max_value=1000000.0,
            value=0.0,
            step=0.1,
            key="increase_all_pct",
        )
    else:
        # Contract year count rule:
        # full years + 1 extra year when there are remaining months.
        num_years = max(1, (tenure_months // 12) + (1 if (tenure_months % 12) > 0 else 0))
        year_options = [str(y) for y in range(2, num_years + 1)]
        if "increase_year_rules_create" not in st.session_state:
            st.session_state.increase_year_rules_create = []
        if st.session_state.get("reset_increase_rule_inputs_create", False):
            st.session_state["increase_rule_years_create"] = []
            st.session_state["increase_rule_value_create"] = 0.0
            st.session_state["reset_increase_rule_inputs_create"] = False
        # Exclude years already assigned to a rule so each year can only be chosen once
        _used_years_create = {
            str(y)
            for rr in st.session_state.increase_year_rules_create
            for y in rr.get("years", [])
        }
        _available_years_create = [y for y in year_options if y not in _used_years_create]
        rc1, rc2, rc3 = st.columns([4, 3, 2])
        with rc1:
            selected_years = st.multiselect("Apply to contract years", options=_available_years_create, key="increase_rule_years_create")
        with rc2:
            if "increase_rule_value_create" not in st.session_state:
                st.session_state["increase_rule_value_create"] = 0.0
            rule_value = st.number_input("Increase value", min_value=0.0, max_value=1000000.0, step=0.1, key="increase_rule_value_create")
        with rc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Add rule", key="btn_add_increase_rule_create"):
                if not selected_years:
                    st.error("Select at least one contract year.")
                else:
                    st.session_state.increase_year_rules_create.append({
                        "years": sorted({int(y) for y in selected_years}),
                        "value_type": "percent" if increase_value_type == "Percent (%)" else "amount",
                        "value": float(rule_value),
                    })
                    # Defer reset to next rerun (before widgets instantiate) to avoid Streamlit key mutation error.
                    st.session_state["reset_increase_rule_inputs_create"] = True
                    st.rerun()
        if st.session_state.increase_year_rules_create:
            st.markdown("**Year Rules**")
            for i, rr in enumerate(st.session_state.increase_year_rules_create.copy()):
                c1, c2 = st.columns([8, 1])
                with c1:
                    st.write(f"Years {rr.get('years', [])} -> {rr.get('value')} ({rr.get('value_type')})")
                with c2:
                    if st.button("Delete", key=f"del_inc_rule_create_{i}"):
                        st.session_state.increase_year_rules_create.pop(i)
                        st.rerun()
    
    # ── Type-specific: Free / Advance months, Advance Payment, ROU settings ──
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
            _free_sel = st.multiselect(
                "Free months (select period numbers)",
                options=_period_options, default=[],
                key="free_months",
                help="Periods where rent accrues but no cash payment is made.",
            )
            free_months_input = ",".join(sorted(_free_sel, key=int)) if _free_sel else ""
        with col_rou2:
            _adv_sel = st.multiselect(
                "Advance months (select period numbers)",
                options=_period_options, default=[],
                key="advance_months",
                help="Periods paid in advance (before commencement).",
            )
            advance_months_input = ",".join(sorted(_adv_sel, key=int)) if _adv_sel else ""
        is_tax_added = st.checkbox(
            "Is tax added (add +1% to ROU rent calculations)",
            value=False, key="is_tax_added",
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
        _free_sel = st.multiselect(
            "Free months (select period numbers)",
            options=_period_options, default=[],
            key="free_months",
            help="Rent is set to 0 with a discount applied for the selected periods.",
        )
        free_months_input = ",".join(sorted(_free_sel, key=int)) if _free_sel else ""
        st.markdown("### Advance Payment")
        advance_payment = st.number_input(
            "Advance Payment Amount (EGP)",
            min_value=0.0, value=0.0, step=0.01, key="advance_payment",
            help="Bulk advance payment amount. This will be deducted from rent amounts over time until fully consumed."
        )

    elif is_revenue_share:
        st.markdown("### Free Months (Discount)")
        _free_sel = st.multiselect(
            "Free months (select period numbers)",
            options=_period_options, default=[],
            key="free_months",
            help="Rent is set to 0 with a discount applied for the selected periods.",
        )
        free_months_input = ",".join(sorted(_free_sel, key=int)) if _free_sel else ""
        st.markdown("### Advance (Revenue Share)")
        rev_share_advance_mode = st.selectbox(
            "How to apply prepaid advance",
            options=[
                "none",
                "chronological",
                "periods",
                "spread_proportional",
            ],
            format_func=lambda x: {
                "none": "None (or legacy: deduct on payment lines only, not on distribution)",
                "chronological": "Month by month in order (same idea as Fixed bulk advance — fills Advance column)",
                "periods": "Only in selected period numbers (1, 2, 3 …)",
                "spread_proportional": "Spread across all months (share of total due after normal calc)",
            }[x],
            index=0,
            key="rev_share_advance_mode",
        )
        _adv_sel_rs = st.multiselect(
            "Advance months (period numbers, for “Only in selected periods”)",
            options=_period_options,
            default=[],
            key="advance_months_rs",
            help="Used when mode is “Only in selected periods”. Prepaid is applied in chronological order but only in these periods.",
        )
        advance_months_input = ",".join(sorted(_adv_sel_rs, key=int)) if _adv_sel_rs else ""
        rev_share_payment_advance = st.number_input(
            "Prepaid advance amount (contract currency)",
            min_value=0.0,
            value=0.0,
            step=0.01,
            key="rev_share_payment_advance",
            help="Total prepaid amount. Behaviour depends on the mode above (distribution Advance column and due).",
        )

    st.markdown("---")
    if st.button("Save Contract"):
        errors = []
        if not selected_asset_or_store:
            errors.append("Please select an asset or store.")
        if not contract_name.strip():
            errors.append("Contract name required.")
        if tenure_months <= 0:
            errors.append("Tenure must be > 0 months.")
        if not st.session_state.contract_lessors:
            errors.append("Add at least one lessor.")
        if abs(total_share - 100.0) > 1e-6:
            errors.append(f"Total lessor shares must be 100% (current: {total_share:.2f}%).")
        if contract_type == "Revenue Share" and category_choice != "Store":
            errors.append("Revenue Share contract type is only available for Store assets.")
        if contract_type != "Revenue Share" and rent_amount <= 0:
            errors.append("Rent amount is required for Fixed and ROU contracts.")
        if contract_type == "ROU":
            if discount_rate <= 0:
                errors.append("Discount rate is required for ROU contracts.")
            if rent_amount <= 0:
                errors.append("Rent amount is required for ROU contracts.")

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
                rules = st.session_state.get("increase_year_rules_create", [])
                increase_map_json = json.dumps({
                    "all_value_type": "percent" if increase_value_type == "Percent (%)" else "amount",
                    "year_rules": rules,
                })

            nid = next_int_id(st.session_state.contracts_df, 1001)
            lessors_json = json.dumps(st.session_state.contract_lessors, ensure_ascii=False)
            contract_row = {
                "id": str(nid),
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
                "rent_per_year": rent_per_year_json if is_rou else "",
                "first_payment_date": str(commencement_date),
                "free_months": free_months_input.strip() if is_rou else (free_months_input.strip() if (contract_type == "Fixed" or contract_type == "Revenue Share") else ""),
                "advance_months": advance_months_input.strip() if (is_rou or is_revenue_share) else "",
                "advance_months_count": str(len([x for x in (advance_months_input or '').split(',') if x.strip().isdigit()])) if (is_rou or is_revenue_share) else "",
                "increase_by_period_mode": increase_mode_code,
                "increase_by_period_all_pct": increase_all_pct_val,
                "increase_by_period_map": increase_map_json,
                "advance_payment": str(advance_payment) if contract_type == "Fixed" else "",
                "rev_share_payment_advance": str(rev_share_payment_advance) if is_revenue_share else "",
                "rev_share_advance_mode": rev_share_advance_mode if is_revenue_share else "",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }

                # Use direct database insert instead of save_df
            if insert_contract(contract_row):
                # Log action
                current_user = get_current_user()
                log_action(
                    user_id=current_user['id'] if current_user else None,
                    user_name=current_user['name'] if current_user else 'System',
                    action_type='create',
                    entity_type='contract',
                    entity_id=str(nid),
                    entity_name=contract_name.strip(),
                    action_details=f"Created {contract_type} contract: {contract_name}",
                    ip_address=get_user_ip()
                )
                # Delete existing contract-lessor relationships and add new ones
                delete_contract_lessors(str(nid))
                
                # Save contract-lessor relationships
                for lessor in st.session_state.contract_lessors:
                    insert_contract_lessor(str(nid), str(lessor['id']), str(lessor['share']))
                
                # Delete existing contract-service relationships and add new ones
                delete_contract_services(str(nid))
                # Also delete any existing service-lessor allocations for this contract
                delete_contract_service_lessors(str(nid))
                
                # Save contract-service relationships
                for service in st.session_state.contract_services:
                    insert_contract_service(
                        str(nid), 
                        str(service['id']), 
                        str(service['amount']),
                        str(service.get('yearly_increase_pct', 0))
                    )
                    # Save per-service lessor allocations (if defined)
                    service_lessors = service.get("lessors", [])
                    total_share = sum(float(sl.get("share", 0) or 0) for sl in service_lessors) if service_lessors else 0.0
                    # Only persist if shares sum reasonably to 100%
                    if service_lessors and abs(total_share - 100.0) <= 1e-6:
                        for sl in service_lessors:
                            insert_contract_service_lessor(
                                str(nid),
                                str(service['id']),
                                str(sl['id']),
                                str(sl.get('share', 0) or 0)
                            )
                
                st.success(f"Contract saved (ID {nid})")
                st.session_state.contract_lessors = []
                st.session_state.contract_services = []
                st.session_state.increase_year_rules_create = []
                st.session_state.create_last_increase_mode = "All periods"
                load_all()
                # Return to contract management hub after save
                st.session_state.selected_main = "\U0001f4c4 Contracts"
                st.session_state.selected_sub = "Contract Management"
                st.session_state.pop("edit_contract_select_id", None)
                if "edit_contract_select" in st.session_state:
                    del st.session_state["edit_contract_select"]
                st.rerun()
            else:
                st.error("Failed to save contract.")


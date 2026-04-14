# tab_download_data.py
# Download data tab
from __future__ import annotations

import json
import streamlit as st
import pandas as pd
import time
from core.utils import *
from conf.constants import *
from core.db import execute_query
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission

DOWNLOAD_NAV_MAIN = "\U0001f4e5 Download Data"

# Download Payment Data: display names (preview only; CSV keeps DB column names)
_PAYMENT_PREVIEW_COL_LABELS = {
    "contract_name": "Contract name",
    "contract_type": "Contract type",
    "lessor_name": "Lessor name",
    "lessor_iban": "Lessor IBAN",
    "payment_date": "Payment date",
    "rent_month": "Rent month",
    "amount": "Gross amount (before discount/advance)",
    "month_year": "Month",
    "year": "Year",
    "due_amount": "Due amount",
    "tax_pct": "Tax %",
    "tax_amount": "Tax amount",
    "withholding_amount": "Withholding amount",
    "payment_amount": "Payment amount",
    "currency": "Currency",
    "payment_type": "Payment type",
    "service_name": "Service name",
    "lessor_share_pct": "Lessor share %",
}

_DISTRIBUTION_PREVIEW_COL_LABELS = {
    "contract_name": "Contract name",
    "contract_type": "Contract type",
    "rent_date": "Rent date (month)",
    "lessor_name": "Lessor name",
    "asset_or_store_id": "Asset / store ID",
    "asset_or_store_name": "Asset / store name",
    "rent_amount": "Rent amount",
    "lessor_share_pct": "Lessor share %",
    "lessor_due_amount": "Lessor due amount",
    "yearly_increase_amount": "Yearly increase (amount)",
    "discount_amount": "Discount amount",
    "advanced_amount": "Advance amount",
    "revenue_min": "Revenue min",
    "revenue_max": "Revenue max",
    "revenue_share_pct": "Revenue share %",
    "revenue_share_after_max_pct": "Revenue share after max %",
    "revenue_amount": "Revenue amount",
    "opening_liability": "Opening liability",
    "interest": "Interest",
    "closing_liability": "Closing liability",
    "principal": "Principal",
    "rou_depreciation": "ROU depreciation",
    "period": "Period",
    "lease_accrual": "Lease accrual",
    "pv_of_lease_payment": "PV of lease payment",
    "advance_coverage_flag": "Advance coverage flag",
    "due_amount": "Due amount (contract month)",
    "cost_center": "Cost center",
}

# Global ordering for multiselect (matches conf.constants per-type COLS + expanded lessor fields).
_DIST_DOWNLOAD_COLUMN_ORDER = [
    "contract_name",
    "contract_type",
    "rent_date",
    "lessor_name",
    "asset_or_store_id",
    "asset_or_store_name",
    "rent_amount",
    "lessor_share_pct",
    "lessor_due_amount",
    "yearly_increase_amount",
    "discount_amount",
    "advanced_amount",
    "due_amount",
    "revenue_min",
    "revenue_max",
    "revenue_share_pct",
    "revenue_share_after_max_pct",
    "revenue_amount",
    "opening_liability",
    "interest",
    "closing_liability",
    "principal",
    "rou_depreciation",
    "period",
    "lease_accrual",
    "pv_of_lease_payment",
    "advance_coverage_flag",
    "cost_center",
]

# Never offer these in Download Distribution Data multiselect (still in DataFrame for filters/sort).
_DL_DIST_COLUMNS_EXCLUDE_FROM_PICKER = frozenset(
    {"lessor_id", "year", "month", "month_year"}
)

# Defaults after contract-type filter — keep in sync with CONTRACT_DISTRIBUTION_*_COLS (+ lessor expansion).
_DL_DIST_COMMON_HEAD = [
    "contract_name",
    "contract_type",
    "rent_date",
    "lessor_name",
    "asset_or_store_name",
    "rent_amount",
    "lessor_share_pct",
    "lessor_due_amount",
]
_DL_DIST_FIXED_TAIL = [
    "yearly_increase_amount",
    "discount_amount",
    "advanced_amount",
    "due_amount",
]
_DL_DIST_REVSHARE_TAIL = [
    "yearly_increase_amount",
    "revenue_min",
    "revenue_max",
    "revenue_share_pct",
    "revenue_share_after_max_pct",
    "revenue_amount",
    "discount_amount",
    "advanced_amount",
    "due_amount",
]
_DL_DIST_ROU_TAIL = [
    "yearly_increase_amount",
    "opening_liability",
    "interest",
    "closing_liability",
    "principal",
    "rou_depreciation",
    "period",
    "lease_accrual",
    "pv_of_lease_payment",
    "discount_amount",
    "advanced_amount",
    "advance_coverage_flag",
    "due_amount",
]

# Contract-month export: no per-lessor columns in the picker.
_DL_DIST_LESSOR_LEVEL_ONLY_COLS = frozenset(
    {"lessor_name", "lessor_share_pct", "lessor_due_amount"}
)
_DIST_DOWNLOAD_CONTRACT_LEVEL_COLUMN_ORDER = [
    c for c in _DIST_DOWNLOAD_COLUMN_ORDER if c not in _DL_DIST_LESSOR_LEVEL_ONLY_COLS
]
_DL_DIST_CONTRACT_LEVEL_HEAD = [
    "contract_name",
    "contract_type",
    "rent_date",
    "asset_or_store_name",
    "rent_amount",
]

_SERVICE_DIST_PREVIEW_COL_LABELS = {
    "contract_name": "Contract name",
    "contract_type": "Contract type",
    "store_name": "Store name",
    "rent_date": "Rent date",
    "month_year": "Month",
    "year": "Year",
    "month": "Month #",
    "service_id": "Service ID",
    "service_name": "Service name",
    "amount": "Amount",
    "discount_amount": "Discount amount",
    "due_amount": "Due amount",
    "currency": "Currency",
}

_PAYMENT_TOTAL_LABELS = {
    "due_amount": "Due amount",
    "tax_amount": "Tax amount",
    "withholding_amount": "Withholding amount",
    "payment_amount": "Payment amount",
}


def _render_payment_totals_cards(totals: dict) -> None:
    """Totals as readable cards (avoids st.metric label clipping in narrow columns)."""
    if not totals:
        return
    st.markdown(
        '<p style="margin:16px 0 10px 0;font-size:1rem;font-weight:600;color:#0f172a;">'
        "Totals (filtered)</p>",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(totals))
    for col_el, (key, raw_val) in zip(cols, totals.items()):
        val = float(raw_val) if raw_val == raw_val else 0.0  # NaN -> 0
        lbl = _PAYMENT_TOTAL_LABELS.get(
            key, key.replace("_", " ").title()
        )
        with col_el:
            st.markdown(
                f"""
<div style="
 background:#f8fafc;
  border:1px solid #e2e8f0;
  border-radius:10px;
  padding:14px 12px;
  min-height:88px;
  box-sizing:border-box;
">
  <div style="
    font-size:0.8125rem;
    font-weight:600;
    color:#475569;
    line-height:1.35;
    word-wrap:break-word;
    overflow-wrap:break-word;
    white-space:normal;
    margin-bottom:8px;
  ">{lbl}</div>
  <div style="
    font-size:1.2rem;
    font-weight:700;
    color:#0f172a;
    font-variant-numeric:tabular-nums;
    letter-spacing:-0.02em;
  ">{val:,.2f}</div>
</div>
""",
                unsafe_allow_html=True,
            )


def _download_nav_back(button_key: str) -> None:
    c1, _ = st.columns([1, 4])
    with c1:
        if st.button("\u2190 Reports Center", key=button_key):
            st.session_state.selected_main = DOWNLOAD_NAV_MAIN
            st.session_state.selected_sub = "Reports Center"
            st.rerun()


def render_download_data_tab():
    require_permission('download.view')
    # Create tabs only for downloads user has permission for
    from core.permissions import has_permission
    tabs = []
    tab_functions = []
    
    if has_permission('download.contracts'):
        tabs.append("Download Contracts")
        tab_functions.append(render_download_contracts)
    
    if has_permission('download.lessors'):
        tabs.append("Download Lessors")
        tab_functions.append(render_download_lessors)
    
    if has_permission('download.assets'):
        tabs.append("Download Assets")
        tab_functions.append(render_download_assets)

    if has_permission("download.services"):
        tabs.append("Download Services")
        tab_functions.append(render_download_services)

    if has_permission('download.distribution'):
        tabs.append("Download Distribution")
        tab_functions.append(render_download_distribution)
        tabs.append("Download Distribution (contract month)")
        tab_functions.append(render_download_distribution_contract_level)

    if has_permission('download.service_distribution'):
        tabs.append("Download Service Distribution")
        tab_functions.append(render_download_service_distribution)

    if has_permission('download.payments'):
        tabs.append("Download Payments")
        tab_functions.append(render_download_payments)

    if not tabs:
        st.info("You don't have permission to download any data.")
        return
    
    # Create tabs dynamically
    created_tabs = st.tabs(tabs)
    for i, tab in enumerate(created_tabs):
        with tab:
            tab_functions[i]()

def render_download_contracts():
    require_permission('download.contracts')
    _download_nav_back("dl_back_contracts")
    st.header("Download Contract Data")
    load_all()
    contracts_df = st.session_state.contracts_df.copy()
    
    if contracts_df.empty:
        st.info("No contract data available.")
    else:
        st.subheader("Filters")
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)

            with col1:
                filter_contract_name = st.text_input("Filter by Contract Name", value="", key="filter_contract_name")
                filter_contract_type = st.selectbox(
                    "Filter by Contract Type",
                    options=["All"] + contracts_df['contract_type'].unique().tolist(),
                    key="filter_contract_type"
                )

            with col2:
                filter_asset_name = st.text_input("Filter by Asset/Store Name", value="", key="filter_asset_name")
                filter_asset_category = st.selectbox(
                    "Filter by Asset Category",
                    options=["All"] + contracts_df['asset_category'].unique().tolist(),
                    key="filter_asset_category"
                )

            with col3:
                filter_payment_freq = st.selectbox(
                    "Filter by Payment Frequency",
                    options=["All"] + contracts_df['payment_frequency'].unique().tolist(),
                    key="filter_payment_freq"
                )
                date_from = st.date_input("Commencement Date From", value=None, key="date_from")
                date_to = st.date_input("Commencement Date To", value=None, key="date_to")

        # Apply filters
        filtered_df = contracts_df.copy()
        
        if filter_contract_name.strip():
            filtered_df = filtered_df[
                filtered_df['contract_name'].str.contains(filter_contract_name.strip(), case=False, na=False)
            ]
        
        
        if filter_contract_type != "All":
            filtered_df = filtered_df[filtered_df['contract_type'] == filter_contract_type]
        
        if filter_asset_name.strip():
            filtered_df = filtered_df[
                filtered_df['asset_or_store_name'].str.contains(filter_asset_name.strip(), case=False, na=False)
            ]
        
        if filter_asset_category != "All":
            filtered_df = filtered_df[filtered_df['asset_category'] == filter_asset_category]
        
        if filter_payment_freq != "All":
            filtered_df = filtered_df[filtered_df['payment_frequency'] == filter_payment_freq]
        
        if date_from:
            filtered_df = filtered_df[
                pd.to_datetime(filtered_df['commencement_date'], errors='coerce') >= pd.Timestamp(date_from)
            ]
        
        if date_to:
            filtered_df = filtered_df[
                pd.to_datetime(filtered_df['commencement_date'], errors='coerce') <= pd.Timestamp(date_to)
            ]
        
        st.markdown("---")
        st.subheader("Filtered Results")
        
        if filtered_df.empty:
            st.info("No contracts match the filters.")
        else:
            # Show ALL contract fields, but choose defaults based on contract type filter (like Distribution tab).
            available_cols = list(filtered_df.columns)
            # Keep stable ordering (id first if exists, then the rest)
            if 'id' in available_cols:
                available_cols = ['id'] + [c for c in available_cols if c != 'id']
            
            st.write("**Select columns to include in download:**")
            base_default_cols = [
                'id', 'contract_name', 'contract_type', 'currency',
                'asset_category', 'asset_or_store_id', 'asset_or_store_name',
                'commencement_date', 'tenure_months', 'end_date',
                'payment_frequency', 'yearly_increase', 'rent_amount',
                'tax', 'created_at',
            ]
            rou_default_cols = base_default_cols + [
                'discount_rate', 'first_payment_date', 'free_months', 'advance_months',
            ]
            revshare_default_cols = base_default_cols + [
                'rev_min', 'rev_max', 'rev_share_pct', 'rev_share_after_max_pc', 'sales_type',
            ]
            # Default: common + type-specific
            if filter_contract_type == "ROU":
                default_cols = rou_default_cols
            elif filter_contract_type == "Revenue Share":
                default_cols = revshare_default_cols
            else:
                default_cols = base_default_cols

            default_cols = [c for c in default_cols if c in available_cols]
            selected_cols = st.multiselect(
                "Columns",
                options=available_cols,
                default=default_cols,
                key=f"select_contract_cols_{filter_contract_type}"
            )
            
            if selected_cols:
                display_df = filtered_df[selected_cols]
                st.dataframe(display_df, use_container_width=True)
                st.write(f"**Total records: {len(filtered_df)}**")
                
                # Download button
                csv = filtered_df[selected_cols].to_csv(index=False)
                if st.download_button(
                    label="📥 Download Contract Data (CSV)",
                    data=csv,
                    file_name=f"contracts_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_contracts"
                ):
                    # Log action
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='download',
                        entity_type='contract',
                        entity_id=None,
                        entity_name=None,
                        action_details=f"Downloaded {len(filtered_df)} contract records",
                        ip_address=get_user_ip()
                    )
            else:
                st.warning("Please select at least one column to download.")

def render_download_lessors():
    require_permission('download.lessors')
    _download_nav_back("dl_back_lessors")
    st.header("Download Lessor Data")
    load_all()
    lessors_df = st.session_state.lessors_df.copy()
    
    if lessors_df.empty:
        st.info("No lessor data available.")
    else:
        st.subheader("Filters")
        with st.container(border=True):
            col1, col2 = st.columns(2)

            with col1:
                filter_name = st.text_input("Filter by Lessor Name", value="", key="filter_lessor_name")
                filter_tax_id = st.text_input("Filter by Tax ID", value="", key="filter_lessor_tax_id")

            with col2:
                filter_supplier_code = st.text_input("Filter by Supplier Code", value="", key="filter_lessor_supplier_code")
                filter_description = st.text_input("Filter by Description", value="", key="filter_lessor_desc")

        # Apply filters
        filtered_df = lessors_df.copy()
        
        if filter_name.strip():
            filtered_df = filtered_df[
                filtered_df['name'].str.contains(filter_name.strip(), case=False, na=False)
            ]
        
        if filter_tax_id.strip():
            filtered_df = filtered_df[
                filtered_df['tax_id'].str.contains(filter_tax_id.strip(), case=False, na=False)
            ]
        
        if filter_supplier_code.strip():
            filtered_df = filtered_df[
                filtered_df['supplier_code'].str.contains(filter_supplier_code.strip(), case=False, na=False)
            ]
        
        if filter_description.strip():
            filtered_df = filtered_df[
                filtered_df['description'].str.contains(filter_description.strip(), case=False, na=False)
            ]
        
        st.markdown("---")
        st.subheader("Filtered Results")
        
        if filtered_df.empty:
            st.info("No lessors match the filters.")
        else:
            # Select columns to display/download
            available_cols = ['name', 'description', 'tax_id', 'supplier_code', 'iban']
            
            st.write("**Select columns to include in download:**")
            selected_cols = st.multiselect(
                "Columns",
                options=available_cols,
                default=available_cols,
                key="select_lessor_cols"
            )
            
            if selected_cols:
                display_df = filtered_df[selected_cols]
                st.dataframe(display_df, use_container_width=True)
                st.write(f"**Total records: {len(filtered_df)}**")
                
                # Download button
                csv = filtered_df[selected_cols].to_csv(index=False)
                if st.download_button(
                    label="📥 Download Lessor Data (CSV)",
                    data=csv,
                    file_name=f"lessors_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_lessors"
                ):
                    # Log action
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='download',
                        entity_type='lessor',
                        entity_id=None,
                        entity_name=None,
                        action_details=f"Downloaded {len(filtered_df)} lessor records",
                        ip_address=get_user_ip()
                    )
            else:
                st.warning("Please select at least one column to download.")

def render_download_assets():
    require_permission('download.assets')
    _download_nav_back("dl_back_assets")
    st.header("Download Asset Data")
    load_all()
    assets_df = st.session_state.assets_df.copy()
    
    if assets_df.empty:
        st.info("No asset data available.")
    else:
        st.subheader("Filters")
        with st.container(border=True):
            col1, col2 = st.columns(2)

            with col1:
                filter_name = st.text_input("Filter by Asset Name", value="", key="filter_asset_name_dl")

            with col2:
                filter_cost_center = st.text_input("Filter by Cost Center", value="", key="filter_asset_cost_center")

        # Apply filters
        filtered_df = assets_df.copy()
        
        if filter_name.strip():
            filtered_df = filtered_df[
                filtered_df['name'].str.contains(filter_name.strip(), case=False, na=False)
            ]
        
        if filter_cost_center.strip():
            filtered_df = filtered_df[
                filtered_df['cost_center'].str.contains(filter_cost_center.strip(), case=False, na=False)
            ]
        
        st.markdown("---")
        st.subheader("Filtered Results")
        
        if filtered_df.empty:
            st.info("No assets match the filters.")
        else:
            # Select columns to display/download
            available_cols = ['name', 'cost_center']
            
            st.write("**Select columns to include in download:**")
            selected_cols = st.multiselect(
                "Columns",
                options=available_cols,
                default=available_cols,
                key="select_asset_cols"
            )
            
            if selected_cols:
                display_df = filtered_df[selected_cols]
                st.dataframe(display_df, use_container_width=True)
                st.write(f"**Total records: {len(filtered_df)}**")
                
                # Download button
                csv = filtered_df[selected_cols].to_csv(index=False)
                if st.download_button(
                    label="📥 Download Asset Data (CSV)",
                    data=csv,
                    file_name=f"assets_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_assets"
                ):
                    # Log action
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='download',
                        entity_type='asset',
                        entity_id=None,
                        entity_name=None,
                        action_details=f"Downloaded {len(filtered_df)} asset records",
                        ip_address=get_user_ip()
                    )
            else:
                st.warning("Please select at least one column to download.")


def render_download_services():
    require_permission("download.services")
    _download_nav_back("dl_back_services")
    st.header("Download Service Data")
    load_all()
    services_df = st.session_state.services_df.copy()

    if services_df.empty:
        st.info("No service data available.")
        return

    st.subheader("Filters")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            f_name = st.text_input("Service name contains", value="", key="dl_svc_master_name")
            f_desc = st.text_input("Description contains", value="", key="dl_svc_master_desc")
        with c2:
            f_currency = st.text_input("Currency contains", value="", key="dl_svc_master_currency")

    filtered_df = services_df.copy()

    if f_name.strip():
        filtered_df = filtered_df[
            filtered_df["name"].str.contains(f_name.strip(), case=False, na=False)
        ]
    if f_desc.strip():
        filtered_df = filtered_df[
            filtered_df["description"].str.contains(f_desc.strip(), case=False, na=False)
        ]
    if f_currency.strip():
        filtered_df = filtered_df[
            filtered_df["currency"].str.contains(f_currency.strip(), case=False, na=False)
        ]

    st.markdown("---")
    st.subheader("Filtered Results")

    if filtered_df.empty:
        st.info("No services match the filters.")
        return

    available_cols = [c for c in SERVICES_COLS if c in filtered_df.columns]
    st.write("**Select columns to include in download:**")
    selected_cols = st.multiselect(
        "Columns",
        options=available_cols,
        default=available_cols,
        key="dl_svc_master_cols",
    )

    if not selected_cols:
        st.warning("Please select at least one column to download.")
        return

    display_df = filtered_df[selected_cols]
    st.dataframe(display_df, use_container_width=True)
    st.write(f"**Total records: {len(filtered_df)}**")

    csv = display_df.to_csv(index=False)
    if st.download_button(
        label="📥 Download Service Data (CSV)",
        data=csv,
        file_name=f"services_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="download_services_master",
    ):
        current_user = get_current_user()
        log_action(
            user_id=current_user["id"] if current_user else None,
            user_name=current_user["name"] if current_user else "System",
            action_type="download",
            entity_type="service",
            entity_id=None,
            entity_name=None,
            action_details=f"Downloaded {len(filtered_df)} service record(s)",
            ip_address=get_user_ip(),
        )


def _expand_contract_distribution_download_df(raw: pd.DataFrame, contract_lessors_df=None) -> pd.DataFrame:
    """Expand monthly rows: legacy lessors_json, legacy per-lessor rows, or contract-level + contract_lessors."""
    from core.utils import expand_distribution_for_per_lessor_ui

    out_rows = []
    contract_level_accum = []
    for _, r in raw.iterrows():
        row_dict = r.to_dict()
        lj = row_dict.get("lessors_json")
        lid = str(row_dict.get("lessor_id") or "").strip()
        parsed = None
        if lj is not None and str(lj).strip():
            try:
                parsed = json.loads(lj)
            except (json.JSONDecodeError, TypeError):
                parsed = None
        base = {k: v for k, v in row_dict.items() if k != "lessors_json"}
        if isinstance(parsed, list) and len(parsed) > 0:
            for p in parsed:
                if not isinstance(p, dict):
                    continue
                out_rows.append({**base, **p})
        elif lid:
            out_rows.append(base)
        else:
            contract_level_accum.append(base)

    if contract_level_accum and contract_lessors_df is not None and not contract_lessors_df.empty:
        clf = pd.DataFrame(contract_level_accum)
        for cid, grp in clf.groupby("contract_id"):
            cid_s = str(cid)
            ctype = (
                str(grp["contract_type"].iloc[0])
                if "contract_type" in grp.columns and pd.notna(grp["contract_type"].iloc[0])
                else "Fixed"
            )
            exp = expand_distribution_for_per_lessor_ui(
                grp.copy(), cid_s, contract_lessors_df, ctype
            )
            if exp is not None and not exp.empty:
                out_rows.extend(exp.to_dict("records"))
    elif contract_level_accum:
        out_rows.extend(contract_level_accum)

    df = pd.DataFrame(out_rows)
    if df.empty:
        return df
    sort_cols = [c for c in ("contract_name", "rent_date", "lessor_id") if c in df.columns]
    if sort_cols:
        df = df.sort_values(by=sort_cols, kind="mergesort").reset_index(drop=True)
    return df


def _enrich_dist_lessor_names(df: pd.DataFrame, lessors_df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or lessors_df is None or lessors_df.empty:
        return df
    if "lessor_id" not in df.columns:
        return df
    df = df.copy()
    m = dict(zip(lessors_df["id"].astype(str), lessors_df["name"].astype(str)))
    from_id = df["lessor_id"].astype(str).map(m)
    if "lessor_name" in df.columns:
        df["lessor_name"] = from_id.fillna(df["lessor_name"]).fillna("")
    else:
        df["lessor_name"] = from_id.fillna("")
    return df


def _load_concat_contract_distribution_df() -> pd.DataFrame:
    """Load fixed + revenue share + ROU distribution with aligned columns (before lessor expansion)."""
    from conf.constants import (
        CONTRACT_DISTRIBUTION_FIXED_COLS,
        CONTRACT_DISTRIBUTION_FIXED_TABLE,
        CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS,
        CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE,
        CONTRACT_DISTRIBUTION_ROU_COLS,
        CONTRACT_DISTRIBUTION_ROU_TABLE,
    )
    from core.utils import load_df

    fixed_df = load_df(CONTRACT_DISTRIBUTION_FIXED_TABLE, CONTRACT_DISTRIBUTION_FIXED_COLS)
    revenue_share_df = load_df(
        CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE, CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS
    )
    rou_df = load_df(CONTRACT_DISTRIBUTION_ROU_TABLE, CONTRACT_DISTRIBUTION_ROU_COLS)

    all_columns: set = set()
    all_dfs = []
    for df in (fixed_df, revenue_share_df, rou_df):
        if df is not None and not df.empty:
            all_columns.update(df.columns)
            all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame()

    for df in all_dfs:
        for col in all_columns:
            if col not in df.columns:
                df[col] = ""

    dist_df = pd.concat(all_dfs, ignore_index=True, sort=False)
    return dist_df.fillna("")


def _dedupe_distribution_contract_month(dist_df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per contract per rent month (stored grain; collapses legacy duplicates)."""
    if dist_df.empty:
        return dist_df
    subset = ["contract_id", "rent_date"]
    if not all(c in dist_df.columns for c in subset):
        subset = ["contract_name", "rent_date"]
    if not all(c in dist_df.columns for c in subset):
        return dist_df
    d = dist_df.copy()
    d["_rt_sort"] = pd.to_datetime(d["rent_date"], errors="coerce")
    d = d.sort_values(by=[*subset, "_rt_sort"], kind="mergesort")
    d = d.drop_duplicates(subset=subset, keep="last")
    return d.drop(columns=["_rt_sort"], errors="ignore")


def _contract_level_download_allowed_colnames(contract_type_filter: str) -> frozenset | None:
    """Columns allowed in the contract-month picker for a single type; None = all types (union)."""
    from conf.constants import (
        CONTRACT_DISTRIBUTION_FIXED_COLS,
        CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS,
        CONTRACT_DISTRIBUTION_ROU_COLS,
    )

    extras = frozenset({"id", "contract_id", "asset_or_store_id", "cost_center"})
    hidden = _DL_DIST_COLUMNS_EXCLUDE_FROM_PICKER | _DL_DIST_LESSOR_LEVEL_ONLY_COLS

    def pack(cols: list) -> frozenset:
        return frozenset(cols) | extras - hidden

    if contract_type_filter == "Fixed":
        return pack(CONTRACT_DISTRIBUTION_FIXED_COLS)
    if contract_type_filter == "Revenue Share":
        return pack(CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS)
    if contract_type_filter == "ROU":
        return pack(CONTRACT_DISTRIBUTION_ROU_COLS)
    return None


def _lessor_level_download_allowed_colnames(contract_type_filter: str) -> frozenset | None:
    """Columns allowed in the per-lessor picker for a single type; None = all types."""
    from conf.constants import (
        CONTRACT_DISTRIBUTION_FIXED_COLS,
        CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS,
        CONTRACT_DISTRIBUTION_ROU_COLS,
    )

    lessor = frozenset({"lessor_name", "lessor_share_pct", "lessor_due_amount"})
    extras = frozenset({"id", "contract_id", "asset_or_store_id", "asset_or_store_name", "cost_center"})
    hidden = _DL_DIST_COLUMNS_EXCLUDE_FROM_PICKER

    def pack(cols: list) -> frozenset:
        return frozenset(cols) | lessor | extras - hidden

    if contract_type_filter == "Fixed":
        return pack(CONTRACT_DISTRIBUTION_FIXED_COLS)
    if contract_type_filter == "Revenue Share":
        return pack(CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS)
    if contract_type_filter == "ROU":
        return pack(CONTRACT_DISTRIBUTION_ROU_COLS)
    return None


def render_download_distribution():
    require_permission('download.distribution')
    _download_nav_back("dl_back_distribution")
    st.header("Download Distribution Data")
    st.caption(
        "Per-lessor rows: each contract month is split using **contract lessors** when the stored row is contract-level."
    )
    load_all()

    dist_df = _load_concat_contract_distribution_df()
    if dist_df.empty:
        st.info("No distribution data available. Generate distribution for a contract first.")
        return

    dist_df = _expand_contract_distribution_download_df(
        dist_df, st.session_state.get("contract_lessors_df")
    )
    dist_df = _enrich_dist_lessor_names(
        dist_df, st.session_state.get("lessors_df", pd.DataFrame(columns=["id", "name"]))
    )
    dist_df = dist_df.fillna("")

    st.subheader("Filters")
    with st.container(border=True):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            f_contract = st.text_input(
                "Contract name contains",
                value="",
                key="dl_dist_contract",
            )
            f_lessor = st.text_input(
                "Lessor name contains",
                value="",
                key="dl_dist_lessor",
            )
        with fc2:
            ctype_opts = ["All"] + sorted(
                {
                    str(x).strip()
                    for x in dist_df["contract_type"].dropna().unique()
                    if str(x).strip()
                },
                key=str.lower,
            )
            f_ctype = st.selectbox("Contract type", ctype_opts, key="dl_dist_ctype")
        with fc3:
            f_asset = st.text_input(
                "Asset / store name contains",
                value="",
                key="dl_dist_asset",
            )
            f_from = st.date_input("Rent date from", value=None, key="dl_dist_from")
            f_to = st.date_input("Rent date to", value=None, key="dl_dist_to")

    filtered = dist_df.copy()
    filtered["rent_date"] = pd.to_datetime(filtered["rent_date"], errors="coerce")

    if f_contract.strip():
        filtered = filtered[
            filtered["contract_name"].str.contains(
                f_contract.strip(), case=False, na=False
            )
        ]
    if f_lessor.strip():
        filtered = filtered[
            filtered["lessor_name"].str.contains(
                f_lessor.strip(), case=False, na=False
            )
        ]
    if f_ctype != "All":
        filtered = filtered[filtered["contract_type"] == f_ctype]
    if f_asset.strip():
        filtered = filtered[
            filtered["asset_or_store_name"].str.contains(
                f_asset.strip(), case=False, na=False
            )
        ]
    if f_from:
        filtered = filtered[filtered["rent_date"] >= pd.Timestamp(f_from)]
    if f_to:
        filtered = filtered[filtered["rent_date"] <= pd.Timestamp(f_to)]

    st.markdown("---")
    st.subheader("Results")

    if filtered.empty:
        st.info("No distribution records match the filters.")
        return

    filtered = filtered.copy()
    filtered["rent_date"] = filtered["rent_date"].dt.strftime("%Y-%m-%d")

    _allowed_l = _lessor_level_download_allowed_colnames(f_ctype)

    def _include_lessor_download_col(c: str) -> bool:
        if c in _DL_DIST_COLUMNS_EXCLUDE_FROM_PICKER:
            return False
        if c not in filtered.columns:
            return False
        if _allowed_l is None:
            return True
        return c in _allowed_l

    extra = [
        c
        for c in sorted(filtered.columns)
        if c not in _DIST_DOWNLOAD_COLUMN_ORDER
        and c not in ("id", "contract_id", "lessors_json")
        and c not in _DL_DIST_COLUMNS_EXCLUDE_FROM_PICKER
        and _include_lessor_download_col(c)
    ]
    available_cols = [
        c
        for c in _DIST_DOWNLOAD_COLUMN_ORDER
        if c in filtered.columns and _include_lessor_download_col(c)
    ] + extra
    for tail in ("contract_id", "id"):
        if tail in filtered.columns and tail not in available_cols and _include_lessor_download_col(tail):
            available_cols.append(tail)
    available_cols = [
        c
        for c in available_cols
        if c != "lessors_json" and c not in _DL_DIST_COLUMNS_EXCLUDE_FROM_PICKER
    ]

    fixed_default = _DL_DIST_COMMON_HEAD + _DL_DIST_FIXED_TAIL
    revshare_default = _DL_DIST_COMMON_HEAD + _DL_DIST_REVSHARE_TAIL
    rou_default = _DL_DIST_COMMON_HEAD + _DL_DIST_ROU_TAIL

    if f_ctype == "ROU":
        default_cols = rou_default
    elif f_ctype == "Revenue Share":
        default_cols = revshare_default
    elif f_ctype == "Fixed":
        default_cols = fixed_default
    else:
        # All types: core identity + amounts many rows share; omit type-specific tails from defaults.
        default_cols = [
            c
            for c in (
                _DL_DIST_COMMON_HEAD
                + [
                    "yearly_increase_amount",
                    "discount_amount",
                    "advanced_amount",
                    "due_amount",
                ]
            )
            if c in available_cols
        ]

    default_cols = [c for c in default_cols if c in available_cols]

    st.write("**Select columns to include in download:**")
    _ctype_slug = f_ctype.replace(" ", "_")
    selected_cols = st.multiselect(
        "Columns",
        options=available_cols,
        default=default_cols,
        key=f"dl_dist_cols__{_ctype_slug}",
    )

    if not selected_cols:
        st.warning("Please select at least one column to download.")
        return

    display = filtered[selected_cols]
    _dist_rename = {
        c: _DISTRIBUTION_PREVIEW_COL_LABELS.get(
            c, c.replace("_", " ").title()
        )
        for c in display.columns
    }
    st.dataframe(
        display.rename(columns=_dist_rename),
        use_container_width=True,
        hide_index=True,
    )
    st.write(
        f"**Total records: {len(filtered)}** (one row per contract month per lessor where applicable; contract-level rows expanded via `contract_lessors`)"
    )

    csv = display.to_csv(index=False)
    if st.download_button(
        label="📥 Download Distribution Data (CSV)",
        data=csv,
        file_name=f"contract_distribution_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="download_distribution",
    ):
        current_user = get_current_user()
        log_action(
            user_id=current_user["id"] if current_user else None,
            user_name=current_user["name"] if current_user else "System",
            action_type="download",
            entity_type="distribution",
            entity_id=None,
            entity_name=None,
            action_details=f"Downloaded {len(filtered)} distribution line(s)",
            ip_address=get_user_ip(),
        )


def render_download_distribution_contract_level():
    require_permission("download.distribution")
    _download_nav_back("dl_back_distribution_contract")
    st.header("Download Distribution Data (contract month)")
    st.caption(
        "One row per **contract** per **rent month** (same grain as stored distribution). "
        "No per-lessor split — use **Download Distribution** for lessor-level lines."
    )
    load_all()

    dist_df = _load_concat_contract_distribution_df()
    if dist_df.empty:
        st.info("No distribution data available. Generate distribution for a contract first.")
        return

    dist_df = dist_df.drop(columns=["lessors_json"], errors="ignore")
    n_before = len(dist_df)
    dist_df = _dedupe_distribution_contract_month(dist_df)
    if len(dist_df) < n_before:
        st.caption(
            f"Collapsed **{n_before - len(dist_df)}** duplicate row(s) for the same contract month (e.g. legacy data)."
        )
    dist_df = dist_df.fillna("")

    st.subheader("Filters")
    with st.container(border=True):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            f_contract = st.text_input(
                "Contract name contains",
                value="",
                key="dl_dist_cl_contract",
            )
        with fc2:
            ctype_opts = ["All"] + sorted(
                {
                    str(x).strip()
                    for x in dist_df["contract_type"].dropna().unique()
                    if str(x).strip()
                },
                key=str.lower,
            )
            f_ctype = st.selectbox("Contract type", ctype_opts, key="dl_dist_cl_ctype")
        with fc3:
            f_asset = st.text_input(
                "Asset / store name contains",
                value="",
                key="dl_dist_cl_asset",
            )
            f_from = st.date_input("Rent date from", value=None, key="dl_dist_cl_from")
            f_to = st.date_input("Rent date to", value=None, key="dl_dist_cl_to")

    filtered = dist_df.copy()
    filtered["rent_date"] = pd.to_datetime(filtered["rent_date"], errors="coerce")

    if f_contract.strip():
        filtered = filtered[
            filtered["contract_name"].str.contains(
                f_contract.strip(), case=False, na=False
            )
        ]
    if f_ctype != "All":
        filtered = filtered[filtered["contract_type"] == f_ctype]
    if f_asset.strip():
        filtered = filtered[
            filtered["asset_or_store_name"].str.contains(
                f_asset.strip(), case=False, na=False
            )
        ]
    if f_from:
        filtered = filtered[filtered["rent_date"] >= pd.Timestamp(f_from)]
    if f_to:
        filtered = filtered[filtered["rent_date"] <= pd.Timestamp(f_to)]

    st.markdown("---")
    st.subheader("Results")

    if filtered.empty:
        st.info("No distribution records match the filters.")
        return

    filtered = filtered.copy()
    filtered["rent_date"] = filtered["rent_date"].dt.strftime("%Y-%m-%d")

    _exclude_cl = _DL_DIST_COLUMNS_EXCLUDE_FROM_PICKER | _DL_DIST_LESSOR_LEVEL_ONLY_COLS
    _allowed_cl = _contract_level_download_allowed_colnames(f_ctype)

    def _include_contract_month_col(c: str) -> bool:
        if c in _exclude_cl:
            return False
        if c not in filtered.columns:
            return False
        if _allowed_cl is None:
            return True
        return c in _allowed_cl

    extra = [
        c
        for c in sorted(filtered.columns)
        if c not in _DIST_DOWNLOAD_CONTRACT_LEVEL_COLUMN_ORDER
        and c not in ("id", "contract_id", "lessors_json")
        and c not in _exclude_cl
        and _include_contract_month_col(c)
    ]
    available_cols = [
        c
        for c in _DIST_DOWNLOAD_CONTRACT_LEVEL_COLUMN_ORDER
        if c in filtered.columns and _include_contract_month_col(c)
    ] + extra
    for tail in ("contract_id", "id"):
        if tail in filtered.columns and tail not in available_cols and _include_contract_month_col(tail):
            available_cols.append(tail)
    available_cols = [
        c for c in available_cols if c != "lessors_json" and c not in _exclude_cl
    ]

    fixed_default = _DL_DIST_CONTRACT_LEVEL_HEAD + _DL_DIST_FIXED_TAIL
    revshare_default = _DL_DIST_CONTRACT_LEVEL_HEAD + _DL_DIST_REVSHARE_TAIL
    rou_default = _DL_DIST_CONTRACT_LEVEL_HEAD + _DL_DIST_ROU_TAIL

    if f_ctype == "ROU":
        default_cols = rou_default
    elif f_ctype == "Revenue Share":
        default_cols = revshare_default
    elif f_ctype == "Fixed":
        default_cols = fixed_default
    else:
        default_cols = [
            c
            for c in (
                _DL_DIST_CONTRACT_LEVEL_HEAD
                + [
                    "yearly_increase_amount",
                    "discount_amount",
                    "advanced_amount",
                    "due_amount",
                ]
            )
            if c in available_cols
        ]

    default_cols = [c for c in default_cols if c in available_cols]

    st.write("**Select columns to include in download:**")
    _cl_ctype_slug = f_ctype.replace(" ", "_")
    selected_cols = st.multiselect(
        "Columns",
        options=available_cols,
        default=default_cols,
        key=f"dl_dist_cl_cols__{_cl_ctype_slug}",
    )

    if not selected_cols:
        st.warning("Please select at least one column to download.")
        return

    display = filtered[selected_cols]
    _dist_rename = {
        c: _DISTRIBUTION_PREVIEW_COL_LABELS.get(
            c, c.replace("_", " ").title()
        )
        for c in display.columns
    }
    st.dataframe(
        display.rename(columns=_dist_rename),
        use_container_width=True,
        hide_index=True,
    )
    st.write(
        f"**Total records: {len(filtered)}** (one row per contract per rent month)"
    )

    csv = display.to_csv(index=False)
    if st.download_button(
        label="\U0001f4e5 Download Distribution Data — contract month (CSV)",
        data=csv,
        file_name=f"contract_distribution_contract_month_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="download_distribution_contract_month",
    ):
        current_user = get_current_user()
        log_action(
            user_id=current_user["id"] if current_user else None,
            user_name=current_user["name"] if current_user else "System",
            action_type="download",
            entity_type="distribution",
            entity_id=None,
            entity_name=None,
            action_details=f"Downloaded {len(filtered)} contract-month distribution row(s)",
            ip_address=get_user_ip(),
        )


def render_download_payments():
    require_permission('download.payments')
    _download_nav_back("dl_back_payments")
    st.header("Download Payment Data")

    query = """
        SELECT
            c.contract_name,
            c.contract_type,
            l.name              AS lessor_name,
            l.iban              AS lessor_iban,
            p.payment_date,
            p.rent_month,
            p.amount,
            DATE_FORMAT(COALESCE(p.rent_month, p.payment_date), '%Y-%m') AS month_year,
            YEAR(COALESCE(p.rent_month, p.payment_date))                  AS year,
            p.due_amount,
            p.tax_pct,
            p.tax_amount,
            p.withholding_amount,
            p.payment_amount,
            COALESCE(NULLIF(TRIM(c.currency), ''), '') AS currency,
            CASE
                WHEN p.service_id IS NOT NULL AND TRIM(COALESCE(p.service_id, '')) != ''
                THEN 'Service Payment'
                ELSE 'Contract Payment'
            END AS payment_type,
            p.lessor_share_pct,
            sv.name             AS service_name
        FROM payments p
        JOIN contracts c ON c.id = p.contract_id
        JOIN lessors   l ON l.id = p.lessor_id
        LEFT JOIN services sv ON sv.id = p.service_id
        ORDER BY p.payment_date, c.contract_name, l.name
    """
    result = execute_query(query, fetch=True)

    if not result:
        st.info("No payment data available. Generate distribution for contracts first.")
        return

    pay_df = pd.DataFrame(result)

    if pay_df.empty:
        st.info("No payment data available.")
        return

    st.subheader("Filters")
    with st.container(border=True):
        fc1, fc2, fc3 = st.columns(3)

        with fc1:
            f_contract = st.text_input("Contract name contains", key="dl_pay_contract")
            f_lessor = st.text_input("Lessor name contains", key="dl_pay_lessor")

        with fc2:
            contract_types = ["All"] + sorted(
                {
                    str(x).strip()
                    for x in pay_df["contract_type"].dropna().unique()
                    if str(x).strip()
                },
                key=str.lower,
            )
            f_type = st.selectbox("Contract type", contract_types, key="dl_pay_ctype")
            payment_types = ["All"] + sorted(
                {
                    str(x).strip()
                    for x in pay_df["payment_type"].dropna().unique()
                    if str(x).strip()
                },
                key=str.lower,
            )
            f_pay_type = st.selectbox("Payment type", payment_types, key="dl_pay_ptype")

        with fc3:
            f_date_from = st.date_input("Payment date from", value=None, key="dl_pay_date_from")
            f_date_to = st.date_input("Payment date to", value=None, key="dl_pay_date_to")

    # Apply filters
    filtered = pay_df.copy()
    filtered["payment_date"] = pd.to_datetime(filtered["payment_date"], errors="coerce")

    if f_contract.strip():
        filtered = filtered[
            filtered["contract_name"].str.contains(f_contract.strip(), case=False, na=False)
        ]
    if f_lessor.strip():
        filtered = filtered[
            filtered["lessor_name"].str.contains(f_lessor.strip(), case=False, na=False)
        ]
    if f_type != "All":
        filtered = filtered[filtered["contract_type"] == f_type]
    if f_pay_type != "All":
        filtered = filtered[filtered["payment_type"] == f_pay_type]
    if f_date_from:
        filtered = filtered[filtered["payment_date"] >= pd.Timestamp(f_date_from)]
    if f_date_to:
        filtered = filtered[filtered["payment_date"] <= pd.Timestamp(f_date_to)]

    st.markdown("---")
    st.subheader("Results")

    if filtered.empty:
        st.info("No payment records match the filters.")
        return

    # Format date for display & download
    filtered["payment_date"] = filtered["payment_date"].dt.strftime("%Y-%m-%d")

    # ── Column selector ────────────────────────────────────────────────────────
    available_cols = [
        "contract_name",
        "contract_type",
        "lessor_name",
        "lessor_iban",
        "payment_date",
        "rent_month",
        "amount",
        "month_year",
        "year",
        "due_amount",
        "tax_pct",
        "tax_amount",
        "withholding_amount",
        "payment_amount",
        "currency",
        "payment_type",
        "service_name",
        "lessor_share_pct",
    ]
    available_cols = [c for c in available_cols if c in filtered.columns]

    default_cols = [
        "contract_name",
        "contract_type",
        "lessor_name",
        "lessor_iban",
        "payment_date",
        "rent_month",
        "amount",
        "due_amount",
        "tax_amount",
        "withholding_amount",
        "payment_amount",
        "lessor_share_pct",
        "currency",
        "payment_type",
        "service_name",
    ]
    default_cols = [c for c in default_cols if c in available_cols]

    st.write("**Select columns to include in download:**")
    selected_cols = st.multiselect(
        "Columns",
        options=available_cols,
        default=default_cols,
        key="dl_pay_cols",
    )

    if not selected_cols:
        st.warning("Please select at least one column.")
        return

    display = filtered[selected_cols]
    _preview_rename = {
        c: _PAYMENT_PREVIEW_COL_LABELS.get(
            c, c.replace("_", " ").title()
        )
        for c in display.columns
    }
    st.dataframe(
        display.rename(columns=_preview_rename),
        use_container_width=True,
        hide_index=True,
    )

    # ── Totals ─────────────────────────────────────────────────────────────────
    num_cols = ["due_amount", "amount", "tax_amount", "withholding_amount", "payment_amount"]
    totals = {
        c: pd.to_numeric(filtered[c], errors="coerce").sum()
        for c in num_cols
        if c in filtered.columns
    }
    _render_payment_totals_cards(totals)

    st.write(f"**Total records: {len(filtered)}**")

    # ── Download button ────────────────────────────────────────────────────────
    csv = display.to_csv(index=False)
    if st.download_button(
        label="📥 Download Payment Data (CSV)",
        data=csv,
        file_name=f"payments_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="dl_pay_btn",
    ):
        current_user = get_current_user()
        log_action(
            user_id=current_user["id"] if current_user else None,
            user_name=current_user["name"] if current_user else "System",
            action_type="download",
            entity_type="payment",
            entity_id=None,
            entity_name=None,
            action_details=f"Downloaded {len(filtered)} payment records",
            ip_address=get_user_ip(),
        )


def _expand_service_distribution_download_df(raw: pd.DataFrame) -> pd.DataFrame:
    """Expand monthly rollup rows: line items live in services_json (legacy); V2 is one row per line in DB."""
    out_rows = []
    for _, r in raw.iterrows():
        base = {
            "contract_name": r.get("contract_name"),
            "contract_type": r.get("contract_type"),
            "store_name": r.get("store_name"),
            "rent_date": r.get("rent_date"),
            "month_year": r.get("month_year"),
            "year": r.get("year"),
            "month": r.get("month"),
            "discount_amount": r.get("discount_amount"),
            "due_amount": r.get("due_amount"),
        }
        sj = r.get("services_json") if "services_json" in raw.columns else None
        parsed = None
        if sj is not None and str(sj).strip():
            try:
                parsed = json.loads(sj)
            except (json.JSONDecodeError, TypeError):
                parsed = None
        if isinstance(parsed, list) and len(parsed) > 0:
            for it in parsed:
                if not isinstance(it, dict):
                    continue
                out_rows.append(
                    {
                        **base,
                        "service_id": str(it.get("service_id", "") or ""),
                        "service_name": str(it.get("service_name", "") or ""),
                        "amount": it.get("amount", "") if it.get("amount") is not None else "",
                        "currency": str(
                            it.get("currency")
                            or r.get("currency")
                            or "EGP"
                        ),
                    }
                )
        else:
            out_rows.append(
                {
                    **base,
                    "service_id": str(r.get("service_id", "") or ""),
                    "service_name": str(r.get("service_name", "") or ""),
                    "amount": r.get("amount", "") if r.get("amount") is not None else "",
                    "currency": str(r.get("currency") or "EGP"),
                }
            )
    df = pd.DataFrame(out_rows)
    if df.empty:
        return df
    sort_cols = [c for c in ("contract_name", "store_name", "rent_date", "service_name") if c in df.columns]
    if sort_cols:
        df = df.sort_values(by=sort_cols, kind="mergesort").reset_index(drop=True)
    return df


def _service_distribution_table_columns() -> set:
    rows = execute_query(
        """
        SELECT COLUMN_NAME AS cn
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'service_distribution'
        """,
        fetch=True,
    )
    if rows is None or not rows:
        return set()
    return {str(r.get("cn") or "") for r in rows if r.get("cn")}


def _service_distribution_download_sql(sd_cols: set) -> str:
    discount_expr = "sd.discount_amount" if "discount_amount" in sd_cols else "NULL AS discount_amount"
    due_expr = "sd.due_amount" if "due_amount" in sd_cols else "NULL AS due_amount"
    json_expr = "sd.services_json" if "services_json" in sd_cols else "NULL AS services_json"
    return f"""
        SELECT
            c.contract_name,
            c.contract_type,
            COALESCE(ast.name, sto.name) AS store_name,
            sd.rent_date,
            DATE_FORMAT(sd.rent_date, '%Y-%m') AS month_year,
            YEAR(sd.rent_date) AS year,
            MONTH(sd.rent_date) AS month,
            sd.service_id,
            sv.name AS service_name,
            sd.amount,
            {discount_expr},
            {due_expr},
            COALESCE(sv.currency, 'EGP') AS currency,
            {json_expr}
        FROM service_distribution sd
        LEFT JOIN contracts c ON sd.contract_id = c.id
        LEFT JOIN assets ast ON c.asset_or_store_id = ast.id
        LEFT JOIN stores sto ON c.asset_or_store_id = sto.id
        LEFT JOIN services sv ON sd.service_id = sv.id
        ORDER BY c.contract_name, sd.rent_date, service_name
    """


def render_download_service_distribution():
    require_permission("download.service_distribution")
    _download_nav_back("dl_back_service_dist")
    st.header("Download Service Distribution Data")
    load_all()

    sd_cols = _service_distribution_table_columns()
    query = _service_distribution_download_sql(sd_cols)
    result = execute_query(query, fetch=True)

    if result is None:
        st.error(
            "Could not load service distribution from the database. "
            "If the problem continues, check the connection and server logs."
        )
        return

    raw_df = pd.DataFrame(result)
    if raw_df.empty:
        st.info(
            "No service distribution data available. Generate distribution for contracts with services first."
        )
        return

    svc_df = _expand_service_distribution_download_df(raw_df)
    if svc_df.empty:
        st.info("No service distribution rows after expanding stored data.")
        return

    for col in ("contract_name", "contract_type", "store_name", "service_name", "service_id", "currency"):
        if col in svc_df.columns:
            svc_df[col] = svc_df[col].fillna("").astype(str)

    st.subheader("Filters")
    with st.container(border=True):
        fc1, fc2, fc3 = st.columns(3)

        with fc1:
            f_contract = st.text_input(
                "Contract name contains",
                value="",
                key="dl_svc_contract",
            )
            f_store = st.text_input(
                "Store name contains",
                value="",
                key="dl_svc_store",
            )
            f_service_contains = st.text_input(
                "Service name contains",
                value="",
                key="dl_svc_service_contains",
            )

        with fc2:
            ctype_opts = ["All"] + sorted(
                {
                    str(x).strip()
                    for x in svc_df["contract_type"].dropna().unique()
                    if str(x).strip()
                },
                key=str.lower,
            )
            f_ctype = st.selectbox("Contract type", ctype_opts, key="dl_svc_ctype")
            svc_names_sorted = sorted(
                {
                    str(x).strip()
                    for x in svc_df["service_name"].unique()
                    if str(x).strip()
                },
                key=str.lower,
            )
            f_service = st.selectbox(
                "Service name",
                ["All"] + svc_names_sorted,
                key="dl_svc_service",
            )

        with fc3:
            f_date_from = st.date_input("Rent date from", value=None, key="dl_svc_date_from")
            f_date_to = st.date_input("Rent date to", value=None, key="dl_svc_date_to")

    filtered = svc_df.copy()
    filtered["rent_date"] = pd.to_datetime(filtered["rent_date"], errors="coerce")

    if f_contract.strip():
        filtered = filtered[
            filtered["contract_name"].str.contains(f_contract.strip(), case=False, na=False)
        ]
    if f_store.strip():
        filtered = filtered[
            filtered["store_name"].str.contains(f_store.strip(), case=False, na=False)
        ]
    if f_ctype != "All":
        filtered = filtered[filtered["contract_type"] == f_ctype]
    if f_service != "All":
        filtered = filtered[filtered["service_name"] == f_service]
    if f_service_contains.strip():
        filtered = filtered[
            filtered["service_name"].str.contains(
                f_service_contains.strip(), case=False, na=False
            )
        ]
    if f_date_from:
        filtered = filtered[filtered["rent_date"] >= pd.Timestamp(f_date_from)]
    if f_date_to:
        filtered = filtered[filtered["rent_date"] <= pd.Timestamp(f_date_to)]

    st.markdown("---")
    st.subheader("Results")

    if filtered.empty:
        st.info("No service distribution records match the filters.")
        return

    filtered = filtered.copy()
    filtered["rent_date"] = filtered["rent_date"].dt.strftime("%Y-%m-%d")

    available_cols = [
        "contract_name",
        "contract_type",
        "store_name",
        "rent_date",
        "month_year",
        "year",
        "month",
        "service_id",
        "service_name",
        "amount",
        "discount_amount",
        "due_amount",
        "currency",
    ]
    available_cols = [c for c in available_cols if c in filtered.columns]

    default_cols = [
        "contract_name",
        "contract_type",
        "store_name",
        "month_year",
        "service_name",
        "amount",
        "currency",
    ]
    default_cols = [c for c in default_cols if c in available_cols]

    st.write("**Select columns to include in download:**")
    selected_cols = st.multiselect(
        "Columns",
        options=available_cols,
        default=default_cols,
        key="dl_svc_cols",
    )

    if not selected_cols:
        st.warning("Please select at least one column.")
        return

    display = filtered[selected_cols]
    st.dataframe(
        display.rename(
            columns={
                c: _SERVICE_DIST_PREVIEW_COL_LABELS.get(
                    c, c.replace("_", " ").title()
                )
                for c in display.columns
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.write(f"**Total records: {len(filtered)}**")

    csv = display.to_csv(index=False)
    if st.download_button(
        label="\U0001f4e5 Download Service Distribution Data (CSV)",
        data=csv,
        file_name=f"service_distribution_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="download_service_distribution",
    ):
        current_user = get_current_user()
        log_action(
            user_id=current_user["id"] if current_user else None,
            user_name=current_user["name"] if current_user else "System",
            action_type="download",
            entity_type="service_distribution",
            entity_id=None,
            entity_name=None,
            action_details=f"Downloaded {len(filtered)} service distribution line(s)",
            ip_address=get_user_ip(),
        )


# tab_weekly_payments.py
# Payments tab - Download payment data from contract and service distribution with filters
import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
from core.utils import *
from conf.constants import *
from core.db import execute_query, update_row_in_table
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission
from weekly_payments_ui.management import PAYMENTS_MAIN

def render_weekly_payments_tab():
    require_permission('payments.view')
    st.header("Payments")
    load_all()
    
    # Load payments data (both contract and service) and join names via IDs
    # Also join with distribution tables to get tax_amount and withholding_amount
    # Join on contract_id, lessor_id, and month_year (derived from payment_date) for reliability
    
    # Check if tax columns exist in payments table
    from core.db import get_db_connection
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SHOW COLUMNS FROM payments LIKE 'tax_pct'")
            has_tax_columns = cursor.fetchone() is not None
            cursor.close()
            conn.close()
        else:
            has_tax_columns = False
    except Exception:
        has_tax_columns = False
    
    # Build tax columns part of query based on schema version
    if has_tax_columns:
        tax_columns_sql = """
            -- Get tax_amount and withholding_amount from payments table (stored when payment was created)
            CAST(COALESCE(NULLIF(p.tax_amount, ''), NULLIF(p.tax_amount, '0'), 0) AS DECIMAL(10,2)) AS tax_amount,
            CAST(COALESCE(NULLIF(p.withholding_amount, ''), NULLIF(p.withholding_amount, '0'), 0) AS DECIMAL(10,2)) AS withholding_amount,
            -- Also get tax_pct for reference
            CAST(COALESCE(NULLIF(p.tax_pct, ''), NULLIF(p.tax_pct, '0'), 0) AS DECIMAL(10,2)) AS tax_pct,
        """
    else:
        # Old schema - calculate tax from contract tax % and due_amount
        tax_columns_sql = """
            -- Calculate tax_amount: due_amount * tax_pct / 100 (old schema - tax not stored in payments)
            CAST(p.due_amount AS DECIMAL(10,2)) * CAST(COALESCE(NULLIF(c.tax, ''), 0) AS DECIMAL(10,2)) / 100.0 AS tax_amount,
            -- Calculate withholding_amount: due_amount + tax_amount - payment_amount (old schema)
            CAST(p.due_amount AS DECIMAL(10,2)) + 
            (CAST(p.due_amount AS DECIMAL(10,2)) * CAST(COALESCE(NULLIF(c.tax, ''), 0) AS DECIMAL(10,2)) / 100.0) - 
            CAST(p.payment_amount AS DECIMAL(10,2)) AS withholding_amount,
            -- Get tax_pct from contract
            CAST(COALESCE(NULLIF(c.tax, ''), 0) AS DECIMAL(10,2)) AS tax_pct,
        """
    
    payments_query = f"""
        SELECT
            p.id,
            p.contract_id,
            c.contract_name,
            c.contract_type,
            c.payment_frequency,
            p.payment_date,
            p.rent_month,
            p.amount,
            p.due_amount,
            p.payment_amount,
            COALESCE(NULLIF(TRIM(c.currency), ''), '') AS currency,
            CASE
                WHEN p.service_id IS NOT NULL AND TRIM(COALESCE(p.service_id, '')) != '' THEN 'Service Payment'
                ELSE 'Contract Payment'
            END AS payment_type,
            p.lessor_id,
            l.name AS lessor_name,
            l.iban AS lessor_iban,
            p.service_id,
            s.name AS service_name,
            CAST(COALESCE(
                NULLIF(TRIM(COALESCE(p.lessor_share_pct, '')), ''),
                NULLIF(TRIM(COALESCE(csl.share_pct, cl.share_pct, '')), ''),
                '0'
            ) AS DECIMAL(12,4)) AS payment_lessor_share_pct,
            DATE_FORMAT(p.payment_date, '%Y-%m') AS month_year,
            YEAR(COALESCE(p.rent_month, p.payment_date)) AS year,
            CASE
                WHEN p.service_id IS NOT NULL AND TRIM(COALESCE(p.service_id, '')) != '' THEN
                    COALESCE(sd.rent_date, p.rent_month, DATE_FORMAT(p.payment_date, '%Y-%m-01'))
                ELSE
                    COALESCE(df.rent_date, drs.rent_date, drou.rent_date, p.rent_month, DATE_FORMAT(p.payment_date, '%Y-%m-01'))
            END AS rent_date,
            {tax_columns_sql}
            CASE
                WHEN p.service_id IS NOT NULL AND TRIM(COALESCE(p.service_id, '')) != '' THEN
                    CAST(COALESCE(NULLIF(sd.discount_amount, ''), '0') AS DECIMAL(10,2))
                WHEN c.contract_type = 'Fixed' AND df.id IS NOT NULL THEN
                    CAST(COALESCE(NULLIF(df.discount_amount, ''), '0') AS DECIMAL(10,2))
                WHEN c.contract_type = 'Revenue Share' AND drs.id IS NOT NULL THEN
                    CAST(COALESCE(NULLIF(drs.discount_amount, ''), '0') AS DECIMAL(10,2))
                WHEN c.contract_type = 'ROU' AND drou.id IS NOT NULL THEN
                    CAST(COALESCE(NULLIF(drou.discount_amount, ''), '0') AS DECIMAL(10,2))
                ELSE 0.0
            END AS discount_amount,
            CASE
                WHEN p.service_id IS NOT NULL AND TRIM(COALESCE(p.service_id, '')) != '' THEN 0.0
                WHEN c.contract_type = 'Fixed' AND df.id IS NOT NULL THEN
                    CAST(COALESCE(NULLIF(df.advanced_amount, ''), '0') AS DECIMAL(10,2))
                WHEN c.contract_type = 'Revenue Share' AND drs.id IS NOT NULL THEN
                    CAST(COALESCE(NULLIF(drs.advanced_amount, ''), '0') AS DECIMAL(10,2))
                WHEN c.contract_type = 'ROU' AND drou.id IS NOT NULL THEN
                    CAST(COALESCE(NULLIF(drou.advanced_amount, ''), '0') AS DECIMAL(10,2))
                ELSE 0.0
            END AS advanced_amount
        FROM payments p
        LEFT JOIN contracts c ON p.contract_id = c.id
        LEFT JOIN lessors l ON p.lessor_id = l.id
        LEFT JOIN services s ON p.service_id = s.id
        LEFT JOIN contract_lessors cl ON
            cl.contract_id = p.contract_id
            AND cl.lessor_id = p.lessor_id
            AND (p.service_id IS NULL OR TRIM(COALESCE(p.service_id, '')) = '')
        LEFT JOIN contract_service_lessors csl ON
            csl.contract_id = p.contract_id
            AND csl.lessor_id = p.lessor_id
            AND csl.service_id = p.service_id
            AND (p.service_id IS NOT NULL AND TRIM(COALESCE(p.service_id, '')) != '')
        LEFT JOIN service_distribution sd ON
            p.service_id IS NOT NULL AND TRIM(COALESCE(p.service_id, '')) != ''
            AND sd.contract_id = p.contract_id
            AND sd.service_id = p.service_id
            AND sd.rent_date = COALESCE(p.rent_month, DATE_FORMAT(p.payment_date, '%Y-%m-01'))
        LEFT JOIN contract_distribution_fixed df ON
            c.contract_type = 'Fixed'
            AND (p.service_id IS NULL OR TRIM(COALESCE(p.service_id, '')) = '')
            AND df.contract_id = p.contract_id
            AND df.rent_date = COALESCE(p.rent_month, DATE_FORMAT(p.payment_date, '%Y-%m-01'))
        LEFT JOIN contract_distribution_revenue_share drs ON
            c.contract_type = 'Revenue Share'
            AND (p.service_id IS NULL OR TRIM(COALESCE(p.service_id, '')) = '')
            AND drs.contract_id = p.contract_id
            AND drs.rent_date = COALESCE(p.rent_month, DATE_FORMAT(p.payment_date, '%Y-%m-01'))
        LEFT JOIN contract_distribution_rou drou ON
            c.contract_type = 'ROU'
            AND (p.service_id IS NULL OR TRIM(COALESCE(p.service_id, '')) = '')
            AND drou.contract_id = p.contract_id
            AND drou.rent_date = COALESCE(p.rent_month, DATE_FORMAT(p.payment_date, '%Y-%m-01'))
        WHERE p.payment_date IS NOT NULL
        ORDER BY p.payment_date ASC, p.contract_id ASC, p.lessor_id ASC, p.service_id ASC
    """
    try:
        payments_result = execute_query(payments_query, fetch=True)
        payments_df = pd.DataFrame(payments_result) if payments_result else pd.DataFrame()
        
        # Debug: Check if query returned data
        if payments_result is None:
            st.warning("Query returned None. Checking database connection...")
            # Try a simple query to verify connection
            from core.db import get_db_connection
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT COUNT(*) as count FROM payments")
                result = cursor.fetchone()
                count = result.get('count', 0) if result else 0
                cursor.close()
                conn.close()
                if count > 0:
                    st.error(f"Found {count} payment(s) in database, but query returned no results. This may indicate a query issue.")
                    st.code(payments_query[:500] + "...", language="sql")
                else:
                    st.info("No payments found in database. Generate distribution for contracts first.")
                return
            else:
                st.error("Could not connect to database.")
                return
    except Exception as query_error:
        st.error(f"Error loading payments: {query_error}")
        import traceback
        st.code(traceback.format_exc(), language="text")
        st.warning("**Note:** If you see a column error, please run the migration script `migration_move_tax_to_payments.sql` to update your database schema.")
        
        # Try a simpler query to check if payments exist
        try:
            from core.db import get_db_connection
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT COUNT(*) as count FROM payments WHERE payment_date IS NOT NULL")
                result = cursor.fetchone()
                count = result.get('count', 0) if result else 0
                cursor.close()
                conn.close()
                if count > 0:
                    st.warning(f"Found {count} payment(s) in database. The query may have a syntax error. Check the error above.")
        except Exception as check_err:
            st.error(f"Could not check database: {check_err}")
        return

    if payments_df.empty:
        # Check if payments actually exist in DB
        try:
            from core.db import get_db_connection
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT COUNT(*) as count FROM payments WHERE payment_date IS NOT NULL")
                result = cursor.fetchone()
                count = result.get('count', 0) if result else 0
                cursor.close()
                conn.close()
                
                if count > 0:
                    st.error(f"Found {count} payment(s) in database, but query returned no results.")
                    st.warning("This may be due to:")
                    st.write("1. GROUP BY clause causing issues - try removing it")
                    st.write("2. JOIN conditions too restrictive")
                    st.write("3. Column name mismatches")
                    # Show a simpler query result
                    with st.expander("Debug: Try simpler query"):
                        try:
                            simple_query = "SELECT p.id, p.contract_id, p.payment_date, p.payment_type, p.service_id FROM payments p WHERE p.payment_date IS NOT NULL LIMIT 10"
                            simple_result = execute_query(simple_query, fetch=True)
                            if simple_result:
                                st.dataframe(pd.DataFrame(simple_result))
                            else:
                                st.write("Simple query also returned no results")
                        except Exception as simple_err:
                            st.error(f"Simple query error: {simple_err}")
                else:
                    st.info("No payment data available. Generate distribution for contracts first.")
                    st.info("**Note:** After generating distribution, payments are created automatically. If payments still don't appear, check that the migration script `migration_move_tax_to_payments.sql` has been run.")
        except Exception as check_err:
            st.error(f"Could not check database: {check_err}")
        return
    
    # Debug: Check if tax_amount and withholding_amount are being populated
    # Show a sample of the data to verify joins are working
    if st.session_state.get('debug_payments', False):
        st.write("**Debug Info:**")
        st.write(f"Total payments: {len(payments_df)}")
        st.write(f"Payments with tax_amount > 0: {len(payments_df[pd.to_numeric(payments_df['tax_amount'], errors='coerce') > 0])}")
        st.write(f"Payments with withholding_amount > 0: {len(payments_df[pd.to_numeric(payments_df['withholding_amount'], errors='coerce') > 0])}")
        # Show sample rows where tax_amount or withholding_amount should be > 0
        sample_df = payments_df[
            (payments_df['payment_type'] == 'Contract Payment') & 
            (pd.to_numeric(payments_df['due_amount'], errors='coerce') > 0)
        ].head(5)
        if not sample_df.empty:
            st.write("Sample contract payments:")
            st.dataframe(sample_df[['contract_name', 'payment_date', 'due_amount', 'tax_amount', 'withholding_amount', 'payment_amount']])

    # Ensure payment_date and rent_date are datetime
    if not payments_df.empty:
        payments_df['payment_date'] = pd.to_datetime(payments_df['payment_date'], errors='coerce')
        payments_df = payments_df[payments_df['payment_date'].notna()]
        
        # For service payments, ensure rent_date is correctly set from service_distribution
        if 'rent_date' in payments_df.columns:
            # Convert rent_date to datetime, handling various formats
            payments_df['rent_date'] = pd.to_datetime(payments_df['rent_date'], errors='coerce')
            
            # For service payments with null rent_date, use payment_date as fallback
            service_payments_mask = payments_df['payment_type'] == 'Service Payment'
            if service_payments_mask.any():
                null_rent_date_mask = payments_df['rent_date'].isna() & service_payments_mask
                if null_rent_date_mask.any():
                    # Use payment_date to derive rent_date (first day of month)
                    payments_df.loc[null_rent_date_mask, 'rent_date'] = pd.to_datetime(
                        payments_df.loc[null_rent_date_mask, 'payment_date']
                    ).dt.to_period('M').dt.to_timestamp()
        else:
            # Fallback if rent_date column doesn't exist - derive from payment_date
            payments_df['rent_date'] = pd.to_datetime(payments_df['payment_date'], errors='coerce').dt.to_period('M').dt.to_timestamp()

    
    st.subheader("Filters")

    # Get unique values for filters from the combined data
    contracts_list = sorted(payments_df['contract_name'].dropna().unique().tolist())
    lessors_list = sorted(payments_df['lessor_name'].dropna().unique().tolist())
    contract_types_list = sorted(payments_df['contract_type'].dropna().unique().tolist())
    currencies_list = sorted(payments_df['currency'].dropna().unique().tolist())

    with st.container(border=True):
        col_date1, col_date2 = st.columns(2)
        with col_date1:
            min_date = payments_df['payment_date'].min().date() if not payments_df.empty else datetime.now().date()
            max_date = payments_df['payment_date'].max().date() if not payments_df.empty else datetime.now().date()
            date_from = st.date_input(
                "Payment Date From",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                key="payment_date_from"
            )

        with col_date2:
            date_to = st.date_input(
                "Payment Date To",
                value=max_date,
                min_value=min_date,
                max_value=max_date,
                key="payment_date_to"
            )

        col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4)

        with col_filter1:
            filter_contract_name = st.selectbox(
                "Filter by Contract Name",
                options=["All"] + contracts_list,
                key="filter_contract_name_payments"
            )
            filter_lessor_name = st.selectbox(
                "Filter by Lessor Name",
                options=["All"] + lessors_list,
                key="filter_lessor_name_payments"
            )

        with col_filter2:
            filter_contract_type = st.selectbox(
                "Filter by Contract Type",
                options=["All"] + contract_types_list,
                key="filter_contract_type_payments"
            )
            filter_payment_type = st.selectbox(
                "Filter by Payment Type",
                options=["All", "Contract Payment", "Service Payment"],
                key="filter_payment_type"
            )

        with col_filter3:
            filter_currency = st.selectbox(
                "Filter by Currency",
                options=["All"] + currencies_list,
                key="filter_currency_payments"
            )

        with col_filter4:
            filter_month_year = st.text_input(
                "Filter by Month-Year (YYYY-MM)",
                value="",
                key="filter_month_year_payments"
            )
            filter_year = st.text_input(
                "Filter by Year",
                value="",
                key="filter_year_payments"
            )

    # Apply filters
    filtered_df = payments_df.copy()
    
    # Date range filter
    if date_from:
        filtered_df = filtered_df[
            filtered_df['payment_date'].dt.date >= date_from
        ]
    
    if date_to:
        filtered_df = filtered_df[
            filtered_df['payment_date'].dt.date <= date_to
        ]
    
    # Contract name filter
    if filter_contract_name != "All":
        filtered_df = filtered_df[
            filtered_df['contract_name'] == filter_contract_name
        ]
    
    # Lessor filter
    if filter_lessor_name != "All":
        filtered_df = filtered_df[
            filtered_df['lessor_name'] == filter_lessor_name
        ]
    
    # Contract type filter
    if filter_contract_type != "All":
        filtered_df = filtered_df[
            filtered_df['contract_type'] == filter_contract_type
        ]
    
    # Payment type filter
    if filter_payment_type != "All":
        filtered_df = filtered_df[
            filtered_df['payment_type'] == filter_payment_type
        ]

    # Currency filter
    if filter_currency != "All":
        filtered_df = filtered_df[
            filtered_df['currency'] == filter_currency
        ]
    
    # Month-Year filter
    if filter_month_year.strip():
        filtered_df = filtered_df[
            filtered_df['month_year'].astype(str).str.contains(
                filter_month_year.strip(), case=False, na=False
            )
        ]
    
    # Year filter
    if filter_year.strip():
        filtered_df = filtered_df[
            filtered_df['year'].astype(str) == filter_year.strip()
        ]
    
    st.markdown("---")
    st.subheader("Payment Records")
    
    if filtered_df.empty:
        st.info("No payment records match the filters.")
    else:
        # Display payment records with required columns
        # Order: rent_date (from distribution), payment_frequency, payment_date, then other columns
        display_cols = [
            'contract_name', 'rent_date', 'payment_frequency', 'payment_date',
            'due_amount', 'discount_amount', 'advanced_amount', 
            'tax_amount', 'withholding_amount', 'payment_amount', 
            'currency', 'lessor_name', 'lessor_iban'
        ]
        
        # Add optional columns if they exist
        optional_cols = ['contract_type', 'payment_type', 'service_name']
        for col in optional_cols:
            if col in filtered_df.columns:
                display_cols.append(col)
        
        # Sort by payment_date
        display_df = filtered_df[display_cols].sort_values('payment_date', ascending=True)
        if "payment_type" in display_df.columns:
            display_df = display_df.rename(columns={"payment_type": "Payment type"})
        
        # Format rent_date for display (if present)
        if 'rent_date' in display_df.columns:
            display_df['rent_date'] = pd.to_datetime(display_df['rent_date'], errors='coerce').dt.strftime('%Y-%m-%d')
        
        # Format payment_date for display
        display_df['payment_date'] = display_df['payment_date'].dt.strftime('%Y-%m-%d')
        
        # Ensure numeric columns are numeric, then format to 2 decimal places
        for col in ['due_amount', 'discount_amount', 'advanced_amount', 'tax_amount', 'withholding_amount', 'payment_amount']:
            if col in display_df.columns:
                display_df[col] = pd.to_numeric(display_df[col], errors='coerce')
                display_df[col] = display_df[col].apply(
                    lambda x: f"{x:.2f}" if pd.notna(x) else "0.00"
                )
        
        st.dataframe(display_df, use_container_width=True)
        st.write(f"**Total payment records: {len(filtered_df)}**")
        
        # Calculate totals (ensure numeric)
        total_due = pd.to_numeric(filtered_df.get('due_amount', 0), errors='coerce').sum()
        total_discount = pd.to_numeric(filtered_df.get('discount_amount', 0), errors='coerce').sum()
        total_advance = pd.to_numeric(filtered_df.get('advanced_amount', 0), errors='coerce').sum()
        total_tax = pd.to_numeric(filtered_df.get('tax_amount', 0), errors='coerce').sum()
        total_withholding = pd.to_numeric(filtered_df.get('withholding_amount', 0), errors='coerce').sum()
        total_payment = pd.to_numeric(filtered_df.get('payment_amount', 0), errors='coerce').sum()

        st.write(f"**Total Due Amount: {total_due:,.2f}**")
        st.write(f"**Total Discount Amount: {total_discount:,.2f}**")
        st.write(f"**Total Advance Amount: {total_advance:,.2f}**")
        st.write(f"**Total Tax Amount: {total_tax:,.2f}**")
        st.write(f"**Total Withholding Amount: {total_withholding:,.2f}**")
        st.write(f"**Total Payment Amount: {total_payment:,.2f}**")
        
        # Download button
        # Prepare download data with all columns
        download_df = filtered_df.copy()
        download_df['payment_date'] = download_df['payment_date'].dt.strftime('%Y-%m-%d')
        # Format rent_date for download
        if 'rent_date' in download_df.columns:
            download_df['rent_date'] = pd.to_datetime(download_df['rent_date'], errors='coerce').dt.strftime('%Y-%m-%d')
        
        # Reorder columns for download: required columns first
        download_cols = [
            'contract_name', 'rent_date', 'payment_frequency', 'payment_date',
            'due_amount', 'discount_amount', 'advanced_amount', 
            'tax_amount', 'withholding_amount', 'payment_amount', 
            'currency', 'lessor_name', 'lessor_iban'
        ]
        for col in download_cols:
            if col not in download_df.columns:
                download_cols.remove(col)
        
        # Add remaining columns
        for col in download_df.columns:
            if col not in download_cols:
                download_cols.append(col)
        
        download_df = download_df[download_cols]
        
        csv = download_df.to_csv(index=False)
        if st.download_button(
            label="📥 Download Payment Data (CSV)",
            data=csv,
            file_name=f"payments_{time.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="download_payments"
        ):
            require_permission('payments.export')
            # Log action
            current_user = get_current_user()
            log_action(
                user_id=current_user['id'] if current_user else None,
                user_name=current_user['name'] if current_user else 'System',
                action_type='download',
                entity_type='weekly_payments',
                entity_id=None,
                entity_name=None,
                action_details=f"Downloaded {len(download_df)} payment records",
                ip_address=get_user_ip()
            )

_PAYMENT_EDIT_FILTER_KEYS = (
    "contract_search_name_payment_edit",
    "contract_filter_type_payment_edit",
    "contract_filter_asset_store_payment_edit",
)


def get_contract_selection_for_payment():
    """Contract for payment editing: focused contract (from management) or filters + selectbox (picker)."""
    load_all()
    contracts_df = st.session_state.contracts_df.copy()

    if contracts_df.empty:
        st.info("No contracts available. Please create contracts first.")
        return None, None

    focus_id = st.session_state.get("payments_editing_id")

    if focus_id:
        match = contracts_df[contracts_df["id"].astype(str) == str(focus_id)]
        if match.empty:
            st.error("Contract not found or was removed.")
            st.session_state.pop("payments_editing_id", None)
            return None, None
        contract_row = match.iloc[0]
        nm = str(contract_row.get("contract_name", "") or "")
        st.caption(f"Editing **{nm}** · contract ID `{focus_id}`")
        return contract_row, nm

    # Picker mode: filters + selectbox (sidebar "Edit Payment" without management)
    st.subheader("Filters")
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        search_name = st.text_input(
            "🔍 Search by Contract Name", key="contract_search_name_payment_edit"
        )

    with filter_col2:
        contract_types = ["All"] + sorted(
            contracts_df["contract_type"].dropna().unique().tolist()
        )
        filter_type = st.selectbox(
            "Filter by Contract Type",
            options=contract_types,
            key="contract_filter_type_payment_edit",
        )

    with filter_col3:
        asset_store_names = ["All"] + sorted(
            contracts_df["asset_or_store_name"].dropna().unique().tolist()
        )
        filter_asset_store = st.selectbox(
            "Filter by Asset/Store",
            options=asset_store_names,
            key="contract_filter_asset_store_payment_edit",
        )

    filtered_df = contracts_df.copy()

    if search_name:
        filtered_df = filtered_df[
            filtered_df["contract_name"].str.contains(search_name, case=False, na=False)
        ]

    if filter_type != "All":
        filtered_df = filtered_df[filtered_df["contract_type"] == filter_type]

    if filter_asset_store != "All":
        filtered_df = filtered_df[
            filtered_df["asset_or_store_name"] == filter_asset_store
        ]

    if filtered_df.empty:
        st.info("No contracts match the selected filters.")
        return None, None

    filtered_df = filtered_df.sort_values("contract_name")

    st.caption(f"Showing {len(filtered_df)} of {len(contracts_df)} contract(s)")

    contract_options = [""] + filtered_df["contract_name"].tolist()
    selected_contract_name = st.selectbox(
        "Select Contract",
        options=contract_options,
        key="select_contract_for_payment_edit",
    )

    if not selected_contract_name:
        st.info("Select a contract to proceed.")
        return None, None

    contract_row = filtered_df[
        filtered_df["contract_name"] == selected_contract_name
    ].iloc[0]

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


def _format_df_for_st_table(df: pd.DataFrame) -> pd.DataFrame:
    """Format a DataFrame for ``st.table`` (static HTML): datetimes to strings, no interactive grid."""
    display = df.copy()
    for col in display.columns:
        s = display[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            display[col] = pd.to_datetime(s, errors="coerce").dt.strftime("%Y-%m-%d")
            continue
        if s.dtype == object:

            def _fmt_one(x):
                if pd.isna(x):
                    return x
                if hasattr(x, "strftime"):
                    try:
                        return x.strftime("%Y-%m-%d")
                    except Exception:
                        return str(x)
                return x

            display[col] = s.map(_fmt_one)
    return display


def render_edit_payment():
    """Render edit payment tab — discount/advance only; due, tax, withholding recalc on save."""
    require_permission("payments.edit")

    if "payments_edit_target_id" in st.session_state:
        st.session_state["payments_editing_id"] = str(
            st.session_state.pop("payments_edit_target_id")
        )
        for key in _PAYMENT_EDIT_FILTER_KEYS:
            st.session_state.pop(key, None)
        st.session_state.pop("select_contract_for_payment_edit", None)
    elif "pay_edit_contract_id" in st.session_state:
        st.session_state["payments_editing_id"] = str(
            st.session_state.pop("pay_edit_contract_id")
        )
        for key in _PAYMENT_EDIT_FILTER_KEYS:
            st.session_state.pop(key, None)
        st.session_state.pop("select_contract_for_payment_edit", None)

    focused = bool(st.session_state.get("payments_editing_id"))

    st.header("Edit Payment")
    if focused:
        st.markdown(
            """
            <style>
            [class*="st-key-payments_edit_back_mgmt"] button {
                width: auto !important;
                min-width: 0 !important;
                padding: 0.35rem 1rem !important;
                font-size: 0.875rem !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        if st.button("← Payment Center", key="payments_edit_back_mgmt"):
            st.session_state.pop("payments_editing_id", None)
            st.session_state.selected_main = PAYMENTS_MAIN
            st.session_state.selected_sub = "Payment Center"
            st.rerun()

    contract_row, selected_contract_name = get_contract_selection_for_payment()

    if contract_row is None:
        return

    load_all()

    contract_type = str(contract_row.get("contract_type", "") or "").strip()
    is_fixed = contract_type == "Fixed"
    dist_df_full = load_distribution_for_contract(
        contract_row["id"], contract_type, per_lessor_view=True
    )

    if dist_df_full.empty:
        st.info(
            "No distribution data available yet for this contract. Generate distribution first."
        )
        return

    if "rent_date" in dist_df_full.columns:
        dist_df_full["rent_date"] = pd.to_datetime(
            dist_df_full["rent_date"], errors="coerce"
        )
        dist_df_full["year"] = dist_df_full["rent_date"].dt.year
        dist_df_full["month_year"] = dist_df_full["rent_date"].dt.strftime("%Y-%m")

    if focused:
        filtered_df = dist_df_full.copy()
    else:
        years = (
            sorted(dist_df_full["year"].dropna().unique().astype(int).tolist())
            if "year" in dist_df_full.columns
            else []
        )
        selected_year = st.selectbox(
            "Filter by year",
            options=["All"] + [str(y) for y in years],
            key="edit_payment_year_filter",
        )

        filtered_df = dist_df_full.copy()
        if selected_year != "All" and "year" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["year"] == int(selected_year)]

        month_year_values = (
            sorted(filtered_df["month_year"].dropna().unique().tolist())
            if "month_year" in filtered_df.columns
            else []
        )
        selected_month_year = st.selectbox(
            "Filter by month (YYYY-MM)",
            options=["All"] + month_year_values,
            key="edit_payment_month_filter",
        )

        if selected_month_year != "All" and "month_year" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["month_year"] == selected_month_year]

    if filtered_df.empty:
        st.info("No rows match the selected filters.")
        return

    st.caption(
        "Edit **Discount** or **Advance** per row — their combined total must not exceed the rent amount. "
        "Lessor due amount, tax, and withholding are recalculated on save."
    )

    if "rent_date" in filtered_df.columns:
        filtered_df["month_year"] = pd.to_datetime(
            filtered_df["rent_date"], errors="coerce"
        ).dt.strftime("%Y-%m")

    edit_cols = [
        "rent_date" if "rent_date" in filtered_df.columns else "month_year",
        "lessor_name",
        "rent_amount",
        "lessor_share_pct",
        "lessor_due_amount",
    ]
    if "discount_amount" in filtered_df.columns:
        edit_cols.append("discount_amount")
    if "advanced_amount" in filtered_df.columns:
        edit_cols.append("advanced_amount")

    edit_cols = [col for col in edit_cols if col in filtered_df.columns]
    filtered_aligned = filtered_df.reset_index(drop=True)
    edit_df = filtered_aligned[edit_cols].copy()

    # If the distribution table for this contract type carries discount/advance columns,
    # ensure they exist in edit_df (they may be absent when all values are NULL/missing).
    dist_cols_for_type = get_distribution_cols(contract_type)
    if "discount_amount" in dist_cols_for_type and "discount_amount" not in edit_df.columns:
        edit_df["discount_amount"] = 0.0
    if "advanced_amount" in dist_cols_for_type and "advanced_amount" not in edit_df.columns:
        edit_df["advanced_amount"] = 0.0

    numeric_cols = [
        "rent_amount",
        "discount_amount",
        "advanced_amount",
        "lessor_share_pct",
        "lessor_due_amount",
    ]
    for col in numeric_cols:
        if col in edit_df.columns:
            edit_df[col] = pd.to_numeric(edit_df[col], errors="coerce").fillna(0.0)

    edit_df = edit_df.reset_index(drop=True)

    # Editable if the distribution table for this contract type supports discount/advance
    can_edit = (
        "discount_amount" in edit_df.columns
        and "advanced_amount" in edit_df.columns
    )

    _cid = str(contract_row["id"])

    # ── Inline table header ────────────────────────────────────────────────────
    # Columns: Date | Lessor | Rent Amt | Discount | Advance | Lessor Due | ✓
    _COL_W = [1.2, 1.5, 1.0, 1.0, 1.0, 1.0, 0.4]

    def _cell(text: str) -> None:
        st.markdown(
            f'<div style="font-size:0.82rem;padding:4px 0;white-space:nowrap;'
            f'overflow:hidden;text-overflow:ellipsis;color:#111827">{text}</div>',
            unsafe_allow_html=True,
        )

    _HDR_STYLE = (
        "font-size:0.78rem;font-weight:700;color:#374151;"
        "border-bottom:2px solid #d1d5db;padding-bottom:4px;margin-bottom:2px"
    )
    hdr = st.columns(_COL_W)
    for col_el, label in zip(
        hdr,
        ["Date", "Lessor", "Rent Amount", "Discount", "Advance", "Lessor Due", ""],
    ):
        with col_el:
            st.markdown(f'<div style="{_HDR_STYLE}">{label}</div>', unsafe_allow_html=True)

    submitted = False

    if can_edit:
        with st.form(f"pay_edit_save_form_{_cid}"):
            validation_errors: list[str] = []
            for i in range(len(edit_df)):
                r = edit_df.iloc[i]
                rent_amt = float(r.get("rent_amount", 0) or 0)
                try:
                    sh = float(str(r.get("lessor_share_pct", 0) or 0))
                except Exception:
                    sh = 0.0
                lessor_slice = rent_amt * sh / 100.0 if rent_amt > 0 else 0.0
                lessor_due = float(r.get("lessor_due_amount", 0) or 0)

                rd = r.get("rent_date", "")
                if hasattr(rd, "strftime"):
                    rd = rd.strftime("%Y-%m-%d")
                elif not rd and "month_year" in r:
                    rd = str(r["month_year"])

                lessor = str(r.get("lessor_name", "—") or "—")

                cols = st.columns(_COL_W)
                with cols[0]:
                    _cell(rd)
                with cols[1]:
                    _cell(lessor)
                with cols[2]:
                    _cell(f"{rent_amt:,.2f}")
                with cols[3]:
                    st.number_input(
                        "Discount",
                        label_visibility="collapsed",
                        min_value=0.0,
                        max_value=float(lessor_slice),
                        step=0.01,
                        value=float(r.get("discount_amount", 0) or 0),
                        key=f"pay_edit_disc_{_cid}_{i}",
                        format="%.2f",
                    )
                with cols[4]:
                    st.number_input(
                        "Advance",
                        label_visibility="collapsed",
                        min_value=0.0,
                        max_value=float(lessor_slice),
                        step=0.01,
                        value=float(r.get("advanced_amount", 0) or 0),
                        key=f"pay_edit_adv_{_cid}_{i}",
                        format="%.2f",
                    )
                with cols[5]:
                    _cell(f"{lessor_due:,.2f}")
                # live combined-total indicator
                disc_live = float(st.session_state.get(f"pay_edit_disc_{_cid}_{i}", 0) or 0)
                adv_live = float(st.session_state.get(f"pay_edit_adv_{_cid}_{i}", 0) or 0)
                combined = disc_live + adv_live
                with cols[6]:
                    if lessor_slice > 0 and combined > lessor_slice + 1e-9:
                        st.markdown("🔴")
                        validation_errors.append(
                            f"Row {i+1} ({lessor} / {rd}): discount + advance "
                            f"({combined:,.2f}) exceeds this lessor's rent share ({lessor_slice:,.2f})."
                        )
                    elif combined > 0:
                        st.markdown("🟢")

                st.markdown(
                    '<hr style="margin:2px 0;border:none;border-top:1px solid #e5e7eb">',
                    unsafe_allow_html=True,
                )

            if validation_errors:
                for err in validation_errors:
                    st.warning(err)

            st.markdown(
                """
                <style>
                [class*="st-key-pay_edit_save_form_"] [data-testid="stFormSubmitButton"] button {
                    width: auto !important;
                    min-width: 0 !important;
                    padding: 0.4rem 1.6rem !important;
                    font-size: 0.9rem !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            submitted = st.form_submit_button(
                "Save Edited Payments",
                type="primary",
                disabled=bool(validation_errors),
            )
    else:
        # Revenue Share or other types without discount/advance columns — read-only
        for i in range(len(edit_df)):
            r = edit_df.iloc[i]
            rd = r.get("rent_date", "")
            if hasattr(rd, "strftime"):
                rd = rd.strftime("%Y-%m-%d")
            elif not rd and "month_year" in r:
                rd = str(r["month_year"])
            cols = st.columns(_COL_W)
            with cols[0]:
                _cell(rd)
            with cols[1]:
                _cell(str(r.get("lessor_name", "—") or "—"))
            with cols[2]:
                _cell(f"{float(r.get('rent_amount', 0) or 0):,.2f}")
            with cols[3]:
                _cell(f"{float(r.get('discount_amount', 0) or 0):,.2f}")
            with cols[4]:
                _cell(f"{float(r.get('advanced_amount', 0) or 0):,.2f}")
            with cols[5]:
                _cell(f"{float(r.get('lessor_due_amount', 0) or 0):,.2f}")
            st.markdown(
                '<hr style="margin:2px 0;border:none;border-top:1px solid #e5e7eb">',
                unsafe_allow_html=True,
            )
        st.caption(
            f"This contract type ({contract_type}) does not support discount / advance editing."
        )

    if submitted:
        try:
            if not can_edit:
                st.info(
                    f"This contract type ({contract_type}) does not support discount / advance editing."
                )
                return

            # Server-side guard: re-validate totals before writing to DB
            _cid_save = str(contract_row["id"])
            over_limit_rows = []
            for i in range(len(edit_df)):
                _orig = edit_df.iloc[i]
                _disc = float(st.session_state.get(f"pay_edit_disc_{_cid_save}_{i}", 0) or 0)
                _adv = float(st.session_state.get(f"pay_edit_adv_{_cid_save}_{i}", 0) or 0)
                _rent = float(_orig.get("rent_amount", 0) or 0)
                try:
                    _sh = float(str(_orig.get("lessor_share_pct", 0) or 0))
                except Exception:
                    _sh = 0.0
                _slice = _rent * _sh / 100.0 if _rent > 0 else 0.0
                if _slice > 0 and (_disc + _adv) > _slice + 1e-9:
                    over_limit_rows.append(i + 1)
            if over_limit_rows:
                st.error(
                    f"Cannot save: discount + advance exceeds rent amount on row(s): "
                    f"{', '.join(str(r) for r in over_limit_rows)}. Correct the values and try again."
                )
                return

            from collections import defaultdict

            def _row_rent_date_key(i: int) -> str:
                src = filtered_aligned.iloc[i]
                rent_date = src.get("rent_date", "")
                if not rent_date and "month_year" in src:
                    rent_date = pd.to_datetime(f"{src['month_year']}-01").date()
                elif rent_date:
                    if isinstance(rent_date, str):
                        rent_date = pd.to_datetime(rent_date).date()
                    elif hasattr(rent_date, "date"):
                        rent_date = rent_date.date()
                return str(rent_date)

            month_rows = defaultdict(list)
            for i in range(len(edit_df)):
                try:
                    month_rows[_row_rent_date_key(i)].append(i)
                except Exception:
                    st.error(f"Could not parse rent_date for row {i}")
                    return

            changed_count = 0
            ct = contract_type
            dist_table = get_distribution_table(ct)

            if dist_table == CONTRACT_DISTRIBUTION_TABLE:
                st.error(f"Invalid contract type: {ct}. Cannot determine distribution table.")
                return

            contract_id = str(contract_row["id"])
            for rd_key, indices in month_rows.items():
                total_disc = 0.0
                total_adv = 0.0
                rent = 0.0
                dirty = False
                for i in indices:
                    original = edit_df.iloc[i]
                    d_key = f"pay_edit_disc_{_cid_save}_{i}"
                    a_key = f"pay_edit_adv_{_cid_save}_{i}"
                    new_discount = float(
                        st.session_state.get(
                            d_key, float(original.get("discount_amount", 0) or 0)
                        )
                    )
                    new_advance = float(
                        st.session_state.get(
                            a_key, float(original.get("advanced_amount", 0) or 0)
                        )
                    )
                    old_discount = float(original.get("discount_amount", 0) or 0)
                    old_advance = float(original.get("advanced_amount", 0) or 0)
                    if (
                        abs(new_discount - old_discount) > 1e-9
                        or abs(new_advance - old_advance) > 1e-9
                    ):
                        dirty = True
                    total_disc += new_discount
                    total_adv += new_advance
                    rent = (
                        float(original["rent_amount"])
                        if pd.notna(original.get("rent_amount"))
                        else rent
                    )
                if not dirty:
                    continue
                due = max(0.0, rent - total_disc - total_adv)
                update_row_in_table(
                    dist_table,
                    {
                        "discount_amount": str(total_disc),
                        "advanced_amount": str(total_adv),
                        "due_amount": str(due),
                    },
                    "contract_id = %s AND rent_date = %s",
                    (contract_id, rd_key),
                )
                changed_count += 1

            if changed_count > 0:
                from core.utils import create_payment_records_from_distribution

                create_payment_records_from_distribution(
                    contract_row["id"],
                    ct,
                    contract_row,
                    distribution_rows=None,
                    service_distribution_rows=None,
                )

                current_user = get_current_user()
                log_action(
                    user_id=current_user["id"] if current_user else None,
                    user_name=current_user["name"] if current_user else "System",
                    action_type="edit",
                    entity_type="payment",
                    entity_id=contract_row["id"],
                    entity_name=contract_row.get("contract_name", ""),
                    action_details=f"Edited payment: {changed_count} row(s) updated",
                    ip_address=get_user_ip(),
                )
                st.success(
                    f"✅ Saved {changed_count} edited payment row(s). Payment records have been updated."
                )
                time.sleep(0.5)
                st.session_state.pop("payments_editing_id", None)
                st.session_state.selected_main = PAYMENTS_MAIN
                st.session_state.selected_sub = "Payment Center"
                st.rerun()
            else:
                st.info("No changes detected to save.")
        except Exception as e:
            st.error(f"Error saving edited payments: {str(e)}")
            import traceback

            st.error(traceback.format_exc())

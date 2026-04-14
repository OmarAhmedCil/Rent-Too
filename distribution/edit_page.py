import streamlit as st
import pandas as pd
import time
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission

from .helpers import get_contract_selection


def render_edit_distribution():
    """Render edit distribution tab"""
    require_permission('distribution.edit')
    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("← Contracts Distribution", key="dist_edit_back_mgmt"):
            st.session_state.selected_main = "\U0001f4ca Distribution"
            st.session_state.selected_sub = "Contracts Distribution"
            st.rerun()
    st.header("Edit Distribution")
    contract_row, selected_contract_name = get_contract_selection()

    if contract_row is None:
        return

    load_all()

    contract_type = contract_row.get('contract_type', '')
    dist_df_full = load_distribution_for_contract(contract_row["id"], contract_type)

    if dist_df_full.empty:
        st.info("No distribution data available yet for this contract. Generate distribution first.")
    else:
        if 'rent_date' in dist_df_full.columns:
            dist_df_full['rent_date'] = pd.to_datetime(dist_df_full['rent_date'], errors='coerce')
            dist_df_full['year'] = dist_df_full['rent_date'].dt.year
            dist_df_full['month_year'] = dist_df_full['rent_date'].dt.strftime('%Y-%m')

        years = sorted(dist_df_full["year"].dropna().unique().astype(int).tolist()) if 'year' in dist_df_full.columns else []
        selected_year = st.selectbox(
            "Filter by year",
            options=["All"] + [str(y) for y in years],
            key="edit_dist_year_filter",
        )

        filtered_df = dist_df_full.copy()
        if selected_year != "All" and 'year' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["year"] == int(selected_year)]

        month_year_values = sorted(filtered_df["month_year"].dropna().unique().tolist()) if 'month_year' in filtered_df.columns else []
        selected_month_year = st.selectbox(
            "Filter by month (YYYY-MM)",
            options=["All"] + month_year_values,
            key="edit_dist_month_filter",
        )

        if selected_month_year != "All" and 'month_year' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["month_year"] == selected_month_year]

        if filtered_df.empty:
            st.info("No rows match the selected filters.")
        else:
            st.write(
                "Edit **contract rent** per month (one row per month). "
                "Totals (due, discount, advance) scale proportionally; payments are rebuilt from the same engine math."
            )

            if 'rent_date' in filtered_df.columns:
                filtered_df['month_year'] = pd.to_datetime(filtered_df['rent_date'], errors='coerce').dt.strftime('%Y-%m')

            edit_cols = [
                "rent_date" if "rent_date" in filtered_df.columns else "month_year",
                "rent_amount",
            ]
            edit_cols = [col for col in edit_cols if col in filtered_df.columns]
            edit_df = filtered_df[edit_cols].copy()

            for col in ["rent_amount"]:
                if col in edit_df.columns:
                    edit_df[col] = pd.to_numeric(edit_df[col], errors="coerce")

            column_config = {}
            if "rent_date" in edit_df.columns:
                column_config["rent_date"] = st.column_config.DateColumn(disabled=True, format="YYYY-MM-DD")
            elif "month_year" in edit_df.columns:
                column_config["month_year"] = st.column_config.TextColumn(disabled=True)
            column_config.update({
                "rent_amount": st.column_config.NumberColumn(label="Rent Amount", step=0.01),
            })

            edited_df = st.data_editor(
                edit_df,
                num_rows="fixed",
                key="edit_distribution_editor",
                column_config=column_config,
            )

            if st.button("Save Edited Rents", key="btn_save_edited_rents", type="primary"):
                try:
                    changed_count = 0
                    contract_type = contract_row.get("contract_type", "")
                    dist_table = get_distribution_table(contract_type)

                    if dist_table == CONTRACT_DISTRIBUTION_TABLE:
                        st.error(f"Invalid contract type: {contract_type}. Cannot determine distribution table.")
                        return

                    for idx, row in edited_df.iterrows():
                        original = edit_df.loc[idx]
                        new_rent = float(row["rent_amount"]) if pd.notna(row["rent_amount"]) else 0.0
                        old_rent = float(original["rent_amount"]) if pd.notna(original["rent_amount"]) else 0.0

                        if abs(new_rent - old_rent) < 1e-9:
                            continue

                        src = filtered_df.iloc[idx]
                        contract_id = src["contract_id"]
                        rent_date = src.get("rent_date", "")
                        if not rent_date and "month_year" in src:
                            try:
                                rent_date = pd.to_datetime(f"{src['month_year']}-01").date()
                            except Exception:
                                st.error(f"Could not parse rent_date for row {idx}")
                                continue
                        elif rent_date:
                            if isinstance(rent_date, str):
                                rent_date = pd.to_datetime(rent_date).date()
                            elif hasattr(rent_date, "date"):
                                rent_date = rent_date.date()

                        ratio = (new_rent / old_rent) if old_rent else 1.0

                        def _scale_field(key):
                            try:
                                v = float(str(src.get(key) or 0) or 0)
                                return str(v * ratio)
                            except Exception:
                                return str(src.get(key) or "")

                        update_data = {
                            "rent_amount": str(new_rent),
                            "due_amount": _scale_field("due_amount"),
                            "discount_amount": _scale_field("discount_amount"),
                            "advanced_amount": _scale_field("advanced_amount"),
                            "yearly_increase_amount": _scale_field("yearly_increase_amount"),
                        }

                        update_row_in_table(
                            dist_table,
                            update_data,
                            "contract_id = %s AND rent_date = %s",
                            (str(contract_id), str(rent_date)),
                        )
                        changed_count += 1

                    if changed_count > 0:
                        from core.utils import create_payment_records_from_distribution
                        create_payment_records_from_distribution(
                            contract_row['id'],
                            contract_type,
                            contract_row,
                            distribution_rows=None,
                            service_distribution_rows=None
                        )

                        current_user = get_current_user()
                        log_action(
                            user_id=current_user['id'] if current_user else None,
                            user_name=current_user['name'] if current_user else 'System',
                            action_type='edit',
                            entity_type='distribution',
                            entity_id=contract_row['id'],
                            entity_name=contract_row.get('contract_name', ''),
                            action_details=f"Edited distribution: {changed_count} row(s) updated",
                            ip_address=get_user_ip()
                        )
                        st.success(f"Saved {changed_count} edited row(s).")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.info("No changes detected to save.")
                except Exception as e:
                    st.error(f"Error saving edited rents: {str(e)}")

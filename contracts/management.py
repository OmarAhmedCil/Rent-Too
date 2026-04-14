# Contract management hub: filters, table, and per-row edit/delete.
import html
import streamlit as st
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.permissions import require_permission, has_permission
from mgmt_ui.delete_dialog import (
    render_contract_delete_dialog_if_pending,
    show_mgmt_success_flash,
)
from mgmt_ui.hub_ui import render_hub_create_button

CONTRACTS_NAV_MAIN = "\U0001f4c4 Contracts"
CONTRACTS_NAV_EDIT = "Edit Contract"

# Five top-level columns: four data fields + one “Actions” (Edit | Delete inside)
_MGMT_TABLE_COLS = [3.0, 1.35, 3.2, 1.45, 2.15]
_MGMT_TABLE_HEADERS = [
    "Contract Name",
    "Contract Type",
    "Asset Or Store Name",
    "Contract date",
]


def _mgmt_contract_cell(row: pd.Series, key: str) -> str:
    v = row.get(key, "")
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = str(v).strip()
    return s if s else "—"


def _mgmt_hdr_html(label: str) -> None:
    esc = html.escape(label)
    st.markdown(
        f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
        f"color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em\">{esc}</div>",
        unsafe_allow_html=True,
    )


def _mgmt_cell_html(text: str, *, nowrap: bool) -> None:
    esc = html.escape(text)
    ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
    st.markdown(
        f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">{esc}</div>',
        unsafe_allow_html=True,
    )


def render_contract_management():
    require_permission("contracts.view")
    show_mgmt_success_flash()
    # Slightly wider right column so “➕ Create contract” stays one line (narrow [4,1] wraps in Streamlit)
    h1, h2 = st.columns([2.85, 1.35])
    with h1:
        st.markdown("## Contract management")
    with h2:
        render_hub_create_button(
            permission="contracts.create",
            button_key="mgmt_hub_create_contract",
            label="➕ Create contract",
            nav_main=CONTRACTS_NAV_MAIN,
            nav_sub="Create Contract",
        )
    st.caption("Filter the list, review the table, then use **Edit** or **Delete** on a row.")

    load_all()
    contracts_df = st.session_state.contracts_df.copy()

    render_contract_delete_dialog_if_pending()

    if contracts_df.empty:
        st.info("No contracts yet. Use **Create contract** above.")
        return

    st.subheader("Filters")
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        filter_contract_name = st.text_input(
            "Contract name contains", value="", key="mgmt_filter_contract_name"
        )
        filter_contract_type = st.selectbox(
            "Contract type",
            options=["All"] + contracts_df["contract_type"].dropna().unique().tolist(),
            key="mgmt_filter_contract_type",
        )
    with fc2:
        filter_asset_name = st.text_input(
            "Asset / store name contains", value="", key="mgmt_filter_asset_name"
        )
        filter_asset_category = st.selectbox(
            "Asset category",
            options=["All"] + contracts_df["asset_category"].dropna().unique().tolist(),
            key="mgmt_filter_asset_category",
        )
    with fc3:
        filter_payment_freq = st.selectbox(
            "Payment frequency",
            options=["All"] + contracts_df["payment_frequency"].dropna().unique().tolist(),
            key="mgmt_filter_payment_freq",
        )

    filtered = contracts_df.copy()
    if filter_contract_name.strip():
        filtered = filtered[
            filtered["contract_name"].str.contains(
                filter_contract_name.strip(), case=False, na=False
            )
        ]
    if filter_contract_type != "All":
        filtered = filtered[filtered["contract_type"] == filter_contract_type]
    if filter_asset_name.strip():
        filtered = filtered[
            filtered["asset_or_store_name"].str.contains(
                filter_asset_name.strip(), case=False, na=False
            )
        ]
    if filter_asset_category != "All":
        filtered = filtered[filtered["asset_category"] == filter_asset_category]
    if filter_payment_freq != "All":
        filtered = filtered[filtered["payment_frequency"] == filter_payment_freq]

    if filtered.empty:
        st.info("No contracts match these filters.")
        return

    st.subheader("Contracts")
    _hr = (
        "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #e5e7eb'>"
    )

    hdr = st.columns(_MGMT_TABLE_COLS)
    for i, title in enumerate(_MGMT_TABLE_HEADERS):
        with hdr[i]:
            _mgmt_hdr_html(title)
    with hdr[4]:
        h_e, h_d = st.columns(2)
        with h_e:
            _mgmt_hdr_html("Edit")
        with h_d:
            _mgmt_hdr_html("Delete")

    st.markdown(_hr, unsafe_allow_html=True)

    data_rows = list(filtered.iterrows())
    for idx, (_, row) in enumerate(data_rows):
        cid = str(row["id"])
        c = st.columns(_MGMT_TABLE_COLS)
        with c[0]:
            _mgmt_cell_html(_mgmt_contract_cell(row, "contract_name"), nowrap=False)
        with c[1]:
            _mgmt_cell_html(_mgmt_contract_cell(row, "contract_type"), nowrap=True)
        with c[2]:
            _mgmt_cell_html(_mgmt_contract_cell(row, "asset_or_store_name"), nowrap=False)
        with c[3]:
            _mgmt_cell_html(_mgmt_contract_cell(row, "commencement_date"), nowrap=True)
        with c[4]:
            b_e, b_d = st.columns(2)
            with b_e:
                if has_permission("contracts.edit") and st.button(
                    "Edit",
                    key=f"mgmt_edit_{cid}",
                    use_container_width=True,
                ):
                    st.session_state.contracts_edit_target_id = cid
                    st.session_state.selected_main = CONTRACTS_NAV_MAIN
                    st.session_state.selected_sub = CONTRACTS_NAV_EDIT
                    st.rerun()
            with b_d:
                if has_permission("contracts.delete") and st.button(
                    "Delete",
                    key=f"mgmt_del_{cid}",
                    use_container_width=True,
                ):
                    st.session_state.contracts_mgmt_pending_delete = cid
                    st.rerun()

        if idx < len(data_rows) - 1:
            st.markdown(_hr, unsafe_allow_html=True)

# Payment management hub: contract table + row Edit (same layout as distribution hub).
import html

import pandas as pd
import streamlit as st

from core.permissions import require_permission, has_permission

from core.utils import load_all

PAYMENTS_MAIN = "💳 Payments"

_PAY_TABLE_COLS = [2.5, 1.15, 1.45, 1.25, 0.85]
_PAY_HEADERS = [
    "Contract name",
    "Contract type",
    "Asset or store name",
    "Contract date",
]


def _hdr_html(label: str) -> None:
    esc = html.escape(label)
    st.markdown(
        f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
        f"color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em\">{esc}</div>",
        unsafe_allow_html=True,
    )


def _cell_html(text: str, *, nowrap: bool) -> None:
    esc = html.escape(text)
    ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
    st.markdown(
        f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">{esc}</div>',
        unsafe_allow_html=True,
    )


def _fmt_contract_date(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        return str(pd.to_datetime(val, errors="coerce").date())
    except Exception:
        return str(val)


def render_payment_management():
    require_permission("payments.view")
    st.markdown("## Payment management")

    load_all()
    contracts_df = st.session_state.contracts_df.copy()

    if contracts_df.empty:
        st.info("No contracts yet. Create a contract first.")
        return

    st.subheader("Filters")
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        search_name = st.text_input(
            "Contract name contains", value="", key="pay_mgmt_filter_name"
        )
    with filter_col2:
        contract_types = ["All"] + sorted(contracts_df["contract_type"].dropna().unique().tolist())
        filter_type = st.selectbox(
            "Contract type", options=contract_types, key="pay_mgmt_filter_type"
        )
    with filter_col3:
        asset_store_names = ["All"] + sorted(
            contracts_df["asset_or_store_name"].dropna().unique().tolist()
        )
        filter_asset_store = st.selectbox(
            "Asset / store", options=asset_store_names, key="pay_mgmt_filter_asset"
        )

    filtered_df = contracts_df.copy()
    if search_name.strip():
        filtered_df = filtered_df[
            filtered_df["contract_name"].str.contains(
                search_name.strip(), case=False, na=False
            )
        ]
    if filter_type != "All":
        filtered_df = filtered_df[filtered_df["contract_type"] == filter_type]
    if filter_asset_store != "All":
        filtered_df = filtered_df[filtered_df["asset_or_store_name"] == filter_asset_store]

    if filtered_df.empty:
        st.info("No contracts match these filters.")
        return

    filtered_df = filtered_df.sort_values("contract_name")

    st.subheader("Contracts")
    _hr = (
        "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #e5e7eb'>"
    )

    hdr = st.columns(_PAY_TABLE_COLS)
    for i, title in enumerate(_PAY_HEADERS):
        with hdr[i]:
            _hdr_html(title)
    with hdr[4]:
        _hdr_html("Edit")

    st.markdown(_hr, unsafe_allow_html=True)

    rows_list = list(filtered_df.iterrows())
    for idx, (_, row) in enumerate(rows_list):
        cid = str(row["id"])
        c = st.columns(_PAY_TABLE_COLS)
        with c[0]:
            _cell_html(str(row.get("contract_name", "") or "—"), nowrap=False)
        with c[1]:
            _cell_html(str(row.get("contract_type", "") or "—"), nowrap=True)
        with c[2]:
            _cell_html(str(row.get("asset_or_store_name", "") or "—"), nowrap=False)
        with c[3]:
            _cell_html(_fmt_contract_date(row.get("commencement_date")), nowrap=True)
        with c[4]:
            if has_permission("payments.edit"):
                if st.button(
                    "Edit",
                    key=f"pay_mgmt_edit_{cid}",
                    use_container_width=True,
                ):
                    st.session_state["payments_edit_target_id"] = str(cid)
                    st.session_state.selected_main = PAYMENTS_MAIN
                    st.session_state.selected_sub = "Edit Payment"
                    st.rerun()
            else:
                _cell_html("—", nowrap=True)

        if idx < len(rows_list) - 1:
            st.markdown(_hr, unsafe_allow_html=True)

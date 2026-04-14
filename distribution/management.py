# Distribution management hub: contract table + row Delete / Generate / Regenerate + bulk action dialog.
import html

import streamlit as st

from core.permissions import require_permission, has_permission

from core.utils import *
from conf.constants import *

from .bulk_action_dialog import (
    open_distribution_bulk_action_dialog,
    render_distribution_bulk_action_dialog,
)
from .delete_dialog import render_distribution_delete_dialog_if_pending
from .dist_work_modal import render_distribution_work_modal, start_distribution_work_modal

DIST_MAIN = "📊 Distribution"

_DIST_TABLE_COLS = [2.75, 1.15, 0.9, 3.25]
_DIST_HEADERS = [
    "Contract name",
    "Contract type",
    "Has distribution",
]


def _dist_hdr_html(label: str) -> None:
    esc = html.escape(label)
    st.markdown(
        f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
        f"color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em\">{esc}</div>",
        unsafe_allow_html=True,
    )


def _dist_cell_html(text: str, *, nowrap: bool) -> None:
    esc = html.escape(text)
    ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
    st.markdown(
        f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">{esc}</div>',
        unsafe_allow_html=True,
    )


def render_distribution_management():
    require_permission("distribution.view")
    st.markdown("## Contracts Distribution")
    st.caption(
        "Filter contracts, review **Has distribution**, use row actions, or open **Bulk action** to run on a whole group."
    )

    load_all()
    contracts_df = st.session_state.contracts_df.copy()

    render_distribution_delete_dialog_if_pending()
    render_distribution_bulk_action_dialog()
    render_distribution_work_modal()

    if contracts_df.empty:
        st.info("No contracts yet. Create a contract first, then generate distribution.")
        return

    can_bulk = (
        has_permission("distribution.generate")
        or has_permission("distribution.regenerate")
        or has_permission("distribution.delete")
    )
    if can_bulk and st.button("Bulk action", key="dist_mgmt_open_bulk"):
        open_distribution_bulk_action_dialog()
        st.rerun()

    st.subheader("Filters")
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        search_name = st.text_input(
            "Contract name contains", value="", key="dist_mgmt_filter_name"
        )
    with filter_col2:
        contract_types = ["All"] + sorted(contracts_df["contract_type"].dropna().unique().tolist())
        filter_type = st.selectbox(
            "Contract type", options=contract_types, key="dist_mgmt_filter_type"
        )
    with filter_col3:
        asset_store_names = ["All"] + sorted(
            contracts_df["asset_or_store_name"].dropna().unique().tolist()
        )
        filter_asset_store = st.selectbox(
            "Asset / store", options=asset_store_names, key="dist_mgmt_filter_asset"
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

    hdr = st.columns(_DIST_TABLE_COLS)
    for i, title in enumerate(_DIST_HEADERS):
        with hdr[i]:
            _dist_hdr_html(title)
    with hdr[3]:
        hb, hg, hr = st.columns(3)
        with hb:
            _dist_hdr_html("Delete")
        with hg:
            _dist_hdr_html("Generate")
        with hr:
            _dist_hdr_html("Regenerate")

    st.markdown(_hr, unsafe_allow_html=True)

    rows_list = list(filtered_df.iterrows())
    for idx, (_, row) in enumerate(rows_list):
        cid = str(row["id"])
        ct = row.get("contract_type", "") or ""
        has_d = "Yes" if check_distribution_exists(row["id"], ct) else "No"

        c = st.columns(_DIST_TABLE_COLS)
        with c[0]:
            _dist_cell_html(str(row.get("contract_name", "") or "—"), nowrap=False)
        with c[1]:
            _dist_cell_html(str(ct or "—"), nowrap=True)
        with c[2]:
            _dist_cell_html(has_d, nowrap=True)
        with c[3]:
            b_del, b_gen, b_reg = st.columns(3)
            with b_del:
                _can_del = has_d == "Yes"
                if has_permission("distribution.delete") and st.button(
                    "Delete",
                    key=f"dist_mgmt_del_{cid}",
                    use_container_width=True,
                    disabled=not _can_del,
                ):
                    st.session_state.dist_mgmt_pending_delete = cid
                    st.rerun()
            with b_gen:
                _can_gen = has_d != "Yes"
                if has_permission("distribution.generate") and st.button(
                    "Generate",
                    key=f"dist_mgmt_gen_{cid}",
                    use_container_width=True,
                    disabled=not _can_gen,
                ):
                    start_distribution_work_modal(op="generate", contract_id=cid)
                    st.rerun()
            with b_reg:
                if has_permission("distribution.regenerate"):
                    _can_regen = has_d == "Yes"
                    if st.button(
                        "Regenerate",
                        key=f"dist_mgmt_regen_{cid}",
                        use_container_width=True,
                        disabled=not _can_regen,
                    ):
                        start_distribution_work_modal(op="regenerate", contract_id=cid)
                        st.rerun()

        if idx < len(rows_list) - 1:
            st.markdown(_hr, unsafe_allow_html=True)

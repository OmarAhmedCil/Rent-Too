# Asset management hub: filters, table-style rows (Name, Cost center), Edit / Delete.
import html
import streamlit as st
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.permissions import require_permission, has_permission
from mgmt_ui.delete_dialog import (
    render_asset_delete_dialog_if_pending,
    show_mgmt_success_flash,
)
from mgmt_ui.hub_ui import render_hub_create_button

ASSETS_MAIN = "🏢 Assets"
ASSET_EDIT = "Edit Asset"

# Two data columns + actions (Edit | Delete)
_ASSET_TABLE_COLS = [3.2, 2.0, 2.1]
_ASSET_TABLE_HEADERS = [
    "Name",
    "Cost center",
]


def _asset_cell(row: pd.Series, key: str) -> str:
    v = row.get(key, "")
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = str(v).strip()
    return s if s else "—"


def _asset_hdr_html(label: str) -> None:
    esc = html.escape(label)
    st.markdown(
        f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
        f"color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em\">{esc}</div>",
        unsafe_allow_html=True,
    )


def _asset_cell_html(text: str, *, nowrap: bool) -> None:
    esc = html.escape(text)
    ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
    st.markdown(
        f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">{esc}</div>',
        unsafe_allow_html=True,
    )


def render_asset_management():
    require_permission("assets.view")
    show_mgmt_success_flash()
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown("## Asset management")
    with h2:
        render_hub_create_button(
            permission="assets.create",
            button_key="mgmt_hub_create_asset",
            label="➕ Create asset",
            nav_main=ASSETS_MAIN,
            nav_sub="Create Asset",
        )
    st.caption("Filter the list, review the table, then use **Edit** or **Delete** on a row.")

    load_all()
    assets_df = st.session_state.assets_df.copy()

    render_asset_delete_dialog_if_pending()

    if assets_df.empty:
        st.info("No assets yet. Use **Create asset** above.")
        return

    st.subheader("Filters")
    c1, c2 = st.columns(2)
    with c1:
        f_name = st.text_input("Name contains", "", key="mgmt_asset_filter_name")
    with c2:
        f_cc = st.text_input("Cost center contains", "", key="mgmt_asset_filter_cc")

    filtered = assets_df.copy()
    if f_name.strip():
        filtered = filtered[
            filtered["name"].str.contains(f_name.strip(), case=False, na=False)
        ]
    if f_cc.strip():
        filtered = filtered[
            filtered["cost_center"]
            .astype(str)
            .str.contains(f_cc.strip(), case=False, na=False)
        ]

    if filtered.empty:
        st.info("No assets match these filters.")
        return

    st.subheader("Assets")
    _hr = (
        "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #e5e7eb'>"
    )

    hdr = st.columns(_ASSET_TABLE_COLS)
    for i, title in enumerate(_ASSET_TABLE_HEADERS):
        with hdr[i]:
            _asset_hdr_html(title)
    with hdr[2]:
        he, hd = st.columns(2)
        with he:
            _asset_hdr_html("Edit")
        with hd:
            _asset_hdr_html("Delete")

    st.markdown(_hr, unsafe_allow_html=True)

    data_rows = list(filtered.iterrows())
    for idx, (_, row) in enumerate(data_rows):
        aid = str(row["id"])
        c = st.columns(_ASSET_TABLE_COLS)
        with c[0]:
            _asset_cell_html(_asset_cell(row, "name"), nowrap=False)
        with c[1]:
            _asset_cell_html(_asset_cell(row, "cost_center"), nowrap=True)
        with c[2]:
            be, bd = st.columns(2)
            with be:
                if has_permission("assets.edit") and st.button(
                    "Edit",
                    key=f"asset_mgmt_edit_{aid}",
                    use_container_width=True,
                ):
                    st.session_state.assets_edit_target_id = aid
                    st.session_state.selected_main = ASSETS_MAIN
                    st.session_state.selected_sub = ASSET_EDIT
                    st.rerun()
            with bd:
                if has_permission("assets.delete") and st.button(
                    "Delete",
                    key=f"asset_mgmt_del_{aid}",
                    use_container_width=True,
                ):
                    st.session_state.assets_mgmt_pending_delete = aid
                    st.rerun()

        if idx < len(data_rows) - 1:
            st.markdown(_hr, unsafe_allow_html=True)

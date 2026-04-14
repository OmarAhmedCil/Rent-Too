# Service management hub: filters, table-style rows (Name, Currency), Edit / Delete.
import html
import streamlit as st
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.permissions import require_permission, has_permission
from mgmt_ui.delete_dialog import (
    render_service_delete_dialog_if_pending,
    show_mgmt_success_flash,
)
from mgmt_ui.hub_ui import render_hub_create_button

SERVICES_MAIN = "🔧 Services"
SERVICE_EDIT = "Edit Service"

# Two data columns + actions (Edit | Delete)
_SERVICE_TABLE_COLS = [3.2, 1.8, 2.1]
_SERVICE_TABLE_HEADERS = [
    "Name",
    "Currency",
]


def _service_cell(row: pd.Series, key: str) -> str:
    v = row.get(key, "")
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = str(v).strip()
    return s if s else "—"


def _service_hdr_html(label: str) -> None:
    esc = html.escape(label)
    st.markdown(
        f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
        f"color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em\">{esc}</div>",
        unsafe_allow_html=True,
    )


def _service_cell_html(text: str, *, nowrap: bool) -> None:
    esc = html.escape(text)
    ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
    st.markdown(
        f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">{esc}</div>',
        unsafe_allow_html=True,
    )


def render_service_management():
    require_permission("services.view")
    show_mgmt_success_flash()
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown("## Service management")
    with h2:
        render_hub_create_button(
            permission="services.create",
            button_key="mgmt_hub_create_service",
            label="➕ Create service",
            nav_main=SERVICES_MAIN,
            nav_sub="Create Service",
        )
    st.caption("Filter the list, review the table, then use **Edit** or **Delete** on a row.")

    load_all()
    services_df = st.session_state.services_df.copy()

    render_service_delete_dialog_if_pending()

    if services_df.empty:
        st.info("No services yet. Use **Create service** above.")
        return

    st.subheader("Filters")
    c1, c2 = st.columns(2)
    with c1:
        f_name = st.text_input("Name contains", "", key="mgmt_svc_filter_name")
    with c2:
        cur_opts = ["All"] + sorted(services_df["currency"].dropna().unique().tolist())
        f_cur = st.selectbox("Currency", cur_opts, key="mgmt_svc_filter_currency")

    filtered = services_df.copy()
    if f_name.strip():
        filtered = filtered[
            filtered["name"].str.contains(f_name.strip(), case=False, na=False)
        ]
    if f_cur != "All":
        filtered = filtered[filtered["currency"] == f_cur]

    if filtered.empty:
        st.info("No services match these filters.")
        return

    st.subheader("Services")
    _hr = (
        "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #e5e7eb'>"
    )

    hdr = st.columns(_SERVICE_TABLE_COLS)
    for i, title in enumerate(_SERVICE_TABLE_HEADERS):
        with hdr[i]:
            _service_hdr_html(title)
    with hdr[2]:
        he, hd = st.columns(2)
        with he:
            _service_hdr_html("Edit")
        with hd:
            _service_hdr_html("Delete")

    st.markdown(_hr, unsafe_allow_html=True)

    data_rows = list(filtered.iterrows())
    for idx, (_, row) in enumerate(data_rows):
        sid = str(row["id"])
        c = st.columns(_SERVICE_TABLE_COLS)
        with c[0]:
            _service_cell_html(_service_cell(row, "name"), nowrap=False)
        with c[1]:
            _service_cell_html(_service_cell(row, "currency"), nowrap=True)
        with c[2]:
            be, bd = st.columns(2)
            with be:
                if has_permission("services.edit") and st.button(
                    "Edit",
                    key=f"svc_mgmt_edit_{sid}",
                    use_container_width=True,
                ):
                    st.session_state.services_edit_target_id = sid
                    st.session_state.selected_main = SERVICES_MAIN
                    st.session_state.selected_sub = SERVICE_EDIT
                    st.rerun()
            with bd:
                if has_permission("services.delete") and st.button(
                    "Delete",
                    key=f"svc_mgmt_del_{sid}",
                    use_container_width=True,
                ):
                    st.session_state.services_mgmt_pending_delete = sid
                    st.rerun()

        if idx < len(data_rows) - 1:
            st.markdown(_hr, unsafe_allow_html=True)

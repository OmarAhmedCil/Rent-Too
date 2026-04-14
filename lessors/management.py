# Lessor management hub: filters, table-style rows (Name, Supplier code), Edit / Delete.
import html
import streamlit as st
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.permissions import require_permission, has_permission
from mgmt_ui.delete_dialog import (
    render_lessor_delete_dialog_if_pending,
    show_mgmt_success_flash,
)
from mgmt_ui.hub_ui import render_hub_create_button

LESSORS_MAIN = "👥 Lessors"
LESSOR_EDIT = "Edit Lessor"

# Two data columns + actions (Edit | Delete)
_LESSOR_TABLE_COLS = [3.2, 2.2, 2.1]
_LESSOR_TABLE_HEADERS = [
    "Name",
    "Supplier code",
]


def _lessor_cell(row: pd.Series, key: str) -> str:
    v = row.get(key, "")
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = str(v).strip()
    return s if s else "—"


def _lessor_hdr_html(label: str) -> None:
    esc = html.escape(label)
    st.markdown(
        f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
        f"color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em\">{esc}</div>",
        unsafe_allow_html=True,
    )


def _lessor_cell_html(text: str, *, nowrap: bool) -> None:
    esc = html.escape(text)
    ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
    st.markdown(
        f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">{esc}</div>',
        unsafe_allow_html=True,
    )


def render_lessor_management():
    require_permission("lessors.view")
    show_mgmt_success_flash()
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown("## Lessor management")
    with h2:
        render_hub_create_button(
            permission="lessors.create",
            button_key="mgmt_hub_create_lessor",
            label="➕ Add lessor",
            nav_main=LESSORS_MAIN,
            nav_sub="Create Lessor",
        )
    st.caption("Filter the list, review the table, then use **Edit** or **Delete** on a row.")

    load_all()
    lessors_df = st.session_state.lessors_df.copy()

    render_lessor_delete_dialog_if_pending()

    if lessors_df.empty:
        st.info("No lessors yet. Use **Add lessor** above.")
        return

    st.subheader("Filters")
    c1, c2, c3 = st.columns(3)
    with c1:
        f_name = st.text_input("Name contains", "", key="mgmt_lessor_filter_name")
        f_tax = st.text_input("Tax ID contains", "", key="mgmt_lessor_filter_tax")
    with c2:
        f_sup = st.text_input("Supplier code contains", "", key="mgmt_lessor_filter_sup")
        f_iban = st.text_input("IBAN contains", "", key="mgmt_lessor_filter_iban")
    with c3:
        f_periods = st.selectbox(
            "With exempt periods",
            ["All", "Yes", "No"],
            key="mgmt_lessor_filter_periods",
        )

    filtered = lessors_df.copy()
    if f_name.strip():
        filtered = filtered[
            filtered["name"].str.contains(f_name.strip(), case=False, na=False)
        ]
    if f_tax.strip():
        filtered = filtered[
            filtered["tax_id"].astype(str).str.contains(f_tax.strip(), case=False, na=False)
        ]
    if f_sup.strip():
        filtered = filtered[
            filtered["supplier_code"]
            .astype(str)
            .str.contains(f_sup.strip(), case=False, na=False)
        ]
    if f_iban.strip():
        filtered = filtered[
            filtered["iban"].astype(str).str.contains(f_iban.strip(), case=False, na=False)
        ]

    if f_periods == "Yes":
        lwp_df = st.session_state.get(
            "lessor_withholding_periods_df",
            pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS),
        )
        if not lwp_df.empty:
            lids = lwp_df["lessor_id"].unique().tolist()
            filtered = filtered[filtered["id"].isin(lids)]
        else:
            filtered = pd.DataFrame(columns=filtered.columns)
    elif f_periods == "No":
        lwp_df = st.session_state.get(
            "lessor_withholding_periods_df",
            pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS),
        )
        if not lwp_df.empty:
            lids = lwp_df["lessor_id"].unique().tolist()
            filtered = filtered[~filtered["id"].isin(lids)]

    if filtered.empty:
        st.info("No lessors match these filters.")
        return

    st.subheader("Lessors")
    _hr = (
        "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #e5e7eb'>"
    )

    hdr = st.columns(_LESSOR_TABLE_COLS)
    for i, title in enumerate(_LESSOR_TABLE_HEADERS):
        with hdr[i]:
            _lessor_hdr_html(title)
    with hdr[2]:
        he, hd = st.columns(2)
        with he:
            _lessor_hdr_html("Edit")
        with hd:
            _lessor_hdr_html("Delete")

    st.markdown(_hr, unsafe_allow_html=True)

    data_rows = list(filtered.iterrows())
    for idx, (_, row) in enumerate(data_rows):
        lid = str(row["id"])
        c = st.columns(_LESSOR_TABLE_COLS)
        with c[0]:
            _lessor_cell_html(_lessor_cell(row, "name"), nowrap=False)
        with c[1]:
            _lessor_cell_html(_lessor_cell(row, "supplier_code"), nowrap=True)
        with c[2]:
            be, bd = st.columns(2)
            with be:
                if has_permission("lessors.edit") and st.button(
                    "Edit",
                    key=f"lessor_mgmt_edit_{lid}",
                    use_container_width=True,
                ):
                    st.session_state.lessors_edit_target_id = lid
                    st.session_state.selected_main = LESSORS_MAIN
                    st.session_state.selected_sub = LESSOR_EDIT
                    st.rerun()
            with bd:
                if has_permission("lessors.delete") and st.button(
                    "Delete",
                    key=f"lessor_mgmt_del_{lid}",
                    use_container_width=True,
                ):
                    st.session_state.lessors_mgmt_pending_delete = lid
                    st.rerun()

        if idx < len(data_rows) - 1:
            st.markdown(_hr, unsafe_allow_html=True)

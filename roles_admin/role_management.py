# Role management hub: filters, table (name, description, # perms), Edit / Delete.
import html
import streamlit as st
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.permissions import require_permission, has_permission
from mgmt_ui.delete_dialog import (
    render_role_delete_dialog_if_pending,
    show_mgmt_success_flash,
)
from mgmt_ui.hub_ui import render_hub_create_button
from .management import ROLES_MAIN

ROLE_SUB_MGMT = "Role Management"
ROLE_CREATE = "Create Role"
ROLE_EDIT = "Edit Role"

_ROLE_TABLE_COLS = [2.0, 2.6, 1.0, 2.4]
_ROLE_TABLE_HEADERS = ["Role name", "Description", "Perms"]


def _perm_count(role_id: str, role_permissions_df: pd.DataFrame) -> int:
    if role_permissions_df is None or role_permissions_df.empty:
        return 0
    return len(role_permissions_df[role_permissions_df["role_id"].astype(str) == str(role_id)])


def _role_cell(row: pd.Series, key: str) -> str:
    v = row.get(key, "")
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = str(v).strip()
    return s if s else "—"


def _role_hdr_html(label: str) -> None:
    esc = html.escape(label)
    st.markdown(
        f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
        f"color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em\">{esc}</div>",
        unsafe_allow_html=True,
    )


def _role_cell_html(text: str, *, nowrap: bool) -> None:
    esc = html.escape(text)
    ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
    st.markdown(
        f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">{esc}</div>',
        unsafe_allow_html=True,
    )


def render_role_management():
    require_permission("roles.view")
    show_mgmt_success_flash()
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown("## Role management")
    with h2:
        render_hub_create_button(
            permission="roles.create",
            button_key="mgmt_hub_create_role",
            label="\u2795 Create role",
            nav_main=ROLES_MAIN,
            nav_sub=ROLE_CREATE,
        )
    st.caption("Filter the list, then use **Edit** or **Delete** on a row. Permissions are set on **Create role** / **Edit role**.")

    load_all()
    roles_df = st.session_state.roles_df.copy()
    role_permissions_df = st.session_state.get(
        "role_permissions_df",
        pd.DataFrame(columns=ROLE_PERMISSIONS_COLS),
    )

    render_role_delete_dialog_if_pending()

    if roles_df.empty:
        st.info("No roles yet. Use **Create role** above.")
        return

    st.subheader("Filters")
    f1, f2 = st.columns(2)
    with f1:
        f_name = st.text_input("Role name contains", "", key="mgmt_role_filter_name")
    with f2:
        f_desc = st.text_input("Description contains", "", key="mgmt_role_filter_desc")

    filtered = roles_df.copy()
    if f_name.strip():
        filtered = filtered[
            filtered["role_name"].str.contains(f_name.strip(), case=False, na=False)
        ]
    if f_desc.strip():
        filtered = filtered[
            filtered["description"].astype(str).str.contains(f_desc.strip(), case=False, na=False)
        ]

    if filtered.empty:
        st.info("No roles match these filters.")
        return

    st.subheader("Roles")
    _hr = "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #e5e7eb'>"

    hdr = st.columns(_ROLE_TABLE_COLS)
    for i, title in enumerate(_ROLE_TABLE_HEADERS):
        with hdr[i]:
            _role_hdr_html(title)
    with hdr[3]:
        he, hd = st.columns(2)
        with he:
            _role_hdr_html("Edit")
        with hd:
            _role_hdr_html("Delete")

    st.markdown(_hr, unsafe_allow_html=True)

    data_rows = list(filtered.iterrows())
    for idx, (_, row) in enumerate(data_rows):
        rid = str(row["id"])
        c = st.columns(_ROLE_TABLE_COLS)
        with c[0]:
            _role_cell_html(_role_cell(row, "role_name"), nowrap=False)
        with c[1]:
            _role_cell_html(_role_cell(row, "description"), nowrap=False)
        with c[2]:
            n = _perm_count(rid, role_permissions_df)
            _role_cell_html(str(n), nowrap=True)
        with c[3]:
            be, bd = st.columns(2)
            with be:
                if has_permission("roles.edit") and st.button(
                    "Edit",
                    key=f"role_mgmt_edit_{rid}",
                    use_container_width=True,
                ):
                    st.session_state.roles_edit_target_id = rid
                    st.session_state.selected_main = ROLES_MAIN
                    st.session_state.selected_sub = ROLE_EDIT
                    st.rerun()
            with bd:
                if has_permission("roles.delete") and st.button(
                    "Delete",
                    key=f"role_mgmt_del_{rid}",
                    use_container_width=True,
                ):
                    st.session_state.roles_mgmt_pending_delete = rid
                    st.rerun()

        if idx < len(data_rows) - 1:
            st.markdown(_hr, unsafe_allow_html=True)

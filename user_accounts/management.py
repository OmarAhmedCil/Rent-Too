# User management hub: filters, table-style rows (Name, Email, Role), Edit / Delete.
import html
import streamlit as st
import pandas as pd
from core.utils import *
from conf.constants import *
from core.db import *
from core.permissions import require_permission, has_permission
from mgmt_ui.delete_dialog import (
    render_user_delete_dialog_if_pending,
    show_mgmt_success_flash,
)
from mgmt_ui.hub_ui import render_hub_create_button

USERS_MAIN = "\U0001f464 Users"
USER_SUB_MGMT = "User Management"
USER_EDIT = "Edit User"

# Name, Email, Role + actions (Edit / Roles / Delete — depends on permissions)
_USER_TABLE_COLS = [2.2, 2.35, 2.0, 2.45]
_USER_TABLE_HEADERS = [
    "Name",
    "Email",
    "Role",
]


def _user_row_action_specs():
    """Order: Edit (if), Roles (assign without edit), Delete (if)."""
    specs = []
    if has_permission("users.edit"):
        specs.append("edit")
    if has_permission("roles.assign") and not has_permission("users.edit"):
        specs.append("roles")
    if has_permission("users.delete"):
        specs.append("delete")
    return specs


def _user_roles_label(user_id, user_roles_df: pd.DataFrame, roles_df: pd.DataFrame) -> str:
    uid = str(user_id)
    if user_roles_df is None or user_roles_df.empty or roles_df is None or roles_df.empty:
        return "—"
    rids = user_roles_df[user_roles_df["user_id"].astype(str) == uid]["role_id"].astype(str).tolist()
    if not rids:
        return "—"
    names: list[str] = []
    for rid in rids:
        m = roles_df[roles_df["id"].astype(str) == rid]
        if not m.empty:
            names.append(str(m.iloc[0].get("role_name", "") or "").strip())
    names = sorted({n for n in names if n})
    return ", ".join(names) if names else "—"


def _user_cell(row: pd.Series, key: str) -> str:
    v = row.get(key, "")
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = str(v).strip()
    return s if s else "—"


def _user_hdr_html(label: str) -> None:
    esc = html.escape(label)
    st.markdown(
        f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
        f"color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em\">{esc}</div>",
        unsafe_allow_html=True,
    )


def _user_cell_html(text: str, *, nowrap: bool) -> None:
    esc = html.escape(text)
    ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
    st.markdown(
        f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">{esc}</div>',
        unsafe_allow_html=True,
    )


def render_user_management():
    require_permission("users.view")
    show_mgmt_success_flash()
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown("## User management")
    with h2:
        render_hub_create_button(
            permission="users.create",
            button_key="mgmt_hub_create_user",
            label="\u2795 Create user",
            nav_main=USERS_MAIN,
            nav_sub="Create User",
        )
    st.caption("Filter the list, review the table, then use **Edit** or **Delete** on a row.")

    load_all()
    users_df = st.session_state.users_df.copy()
    user_roles_df = st.session_state.get(
        "user_roles_df",
        pd.DataFrame(columns=USER_ROLES_COLS),
    )
    roles_df = st.session_state.get(
        "roles_df",
        pd.DataFrame(columns=ROLES_COLS),
    )

    render_user_delete_dialog_if_pending()

    if users_df.empty:
        st.info("No users yet. Use **Create user** above.")
        return

    st.subheader("Filters")
    c1, c2 = st.columns(2)
    with c1:
        f_name = st.text_input("Name contains", "", key="mgmt_user_filter_name")
        f_email = st.text_input("Email contains", "", key="mgmt_user_filter_email")
    with c2:
        f_active = st.selectbox("Active", ["All", "Yes", "No"], key="mgmt_user_filter_active")

    filtered = users_df.copy()
    if f_name.strip():
        filtered = filtered[
            filtered["name"].str.contains(f_name.strip(), case=False, na=False)
        ]
    if f_email.strip():
        filtered = filtered[
            filtered["email"].str.contains(f_email.strip(), case=False, na=False)
        ]
    if f_active == "Yes":
        filtered = filtered[filtered["is_active"].astype(int) == 1]
    elif f_active == "No":
        filtered = filtered[filtered["is_active"].astype(int) == 0]

    if filtered.empty:
        st.info("No users match these filters.")
        return

    st.subheader("Users")
    _hr = (
        "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #e5e7eb'>"
    )

    hdr = st.columns(_USER_TABLE_COLS)
    for i, title in enumerate(_USER_TABLE_HEADERS):
        with hdr[i]:
            _user_hdr_html(title)
    _acts = _user_row_action_specs()
    _act_labels = {"edit": "Edit", "roles": "Roles", "delete": "Delete"}
    with hdr[3]:
        if _acts:
            _hs = st.columns([1] * len(_acts))
            for _i, _a in enumerate(_acts):
                with _hs[_i]:
                    _user_hdr_html(_act_labels[_a])
        else:
            _user_hdr_html("—")

    st.markdown(_hr, unsafe_allow_html=True)

    data_rows = list(filtered.iterrows())
    for idx, (_, row) in enumerate(data_rows):
        uid = str(row["id"])
        c = st.columns(_USER_TABLE_COLS)
        with c[0]:
            _user_cell_html(_user_cell(row, "name"), nowrap=False)
        with c[1]:
            _user_cell_html(_user_cell(row, "email"), nowrap=False)
        with c[2]:
            role_txt = _user_roles_label(uid, user_roles_df, roles_df)
            _user_cell_html(role_txt, nowrap=False)
        with c[3]:
            if _acts:
                _bs = st.columns([1] * len(_acts))
                for _i, _a in enumerate(_acts):
                    with _bs[_i]:
                        if _a == "edit":
                            if st.button(
                                "Edit",
                                key=f"user_mgmt_edit_{uid}",
                                use_container_width=True,
                            ):
                                st.session_state.pop("users_editing_roles_only", None)
                                st.session_state.users_edit_target_id = uid
                                st.session_state.selected_main = USERS_MAIN
                                st.session_state.selected_sub = USER_EDIT
                                st.rerun()
                        elif _a == "roles":
                            if st.button(
                                "Roles",
                                key=f"user_mgmt_roles_{uid}",
                                use_container_width=True,
                            ):
                                st.session_state["users_editing_roles_only"] = True
                                st.session_state.users_edit_target_id = uid
                                st.session_state.selected_main = USERS_MAIN
                                st.session_state.selected_sub = USER_EDIT
                                st.rerun()
                        elif _a == "delete":
                            if st.button(
                                "Delete",
                                key=f"user_mgmt_del_{uid}",
                                use_container_width=True,
                            ):
                                st.session_state.users_mgmt_pending_delete = uid
                                st.rerun()
            else:
                _user_cell_html("—", nowrap=True)

        if idx < len(data_rows) - 1:
            st.markdown(_hr, unsafe_allow_html=True)

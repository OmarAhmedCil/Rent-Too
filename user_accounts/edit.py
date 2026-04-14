import streamlit as st
import time
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import hash_password, get_current_user, get_user_ip
from core.permissions import require_permission, has_permission
from .management import USERS_MAIN, USER_SUB_MGMT
from .user_roles_ui import render_roles_section_for_user


def render_edit_user():
    """Edit user form, or roles-only view when opened via **Roles** (assign without edit)."""
    st.markdown(
        """<style>
        [class*="st-key-user_edit_back_mgmt"] button,
        [class*="st-key-user_edit_back_mgmt"] button p,
        [class*="st-key-user_edit_back_mgmt"] button span {
            white-space: nowrap !important;
        }
        [class*="st-key-user_edit_no_target_back"] button,
        [class*="st-key-user_edit_no_target_back"] button p,
        [class*="st-key-user_edit_no_target_back"] button span {
            white-space: nowrap !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    load_all()
    users_df = st.session_state.users_df.copy()

    if users_df.empty:
        st.info("No users available to edit.")
        return

    if "users_edit_target_id" in st.session_state:
        st.session_state["users_editing_id"] = str(
            st.session_state.pop("users_edit_target_id")
        )

    ueid = st.session_state.get("users_editing_id")
    roles_only = bool(st.session_state.get("users_editing_roles_only"))

    if roles_only:
        require_permission("roles.assign")
    else:
        require_permission("users.edit")

    if not ueid:
        st.warning("Open **User management** and choose **Edit** or **Roles** on a row.")
        if st.button("← User management", key="user_edit_no_target_back", use_container_width=False):
            st.session_state.pop("users_editing_roles_only", None)
            st.session_state.selected_main = USERS_MAIN
            st.session_state.selected_sub = USER_SUB_MGMT
            st.rerun()
        return

    if st.button("← User management", key="user_edit_back_mgmt", use_container_width=False):
        st.session_state.pop("users_edit_target_id", None)
        st.session_state.pop("users_editing_id", None)
        st.session_state.pop("users_editing_roles_only", None)
        st.session_state.selected_main = USERS_MAIN
        st.session_state.selected_sub = USER_SUB_MGMT
        st.rerun()

    st.header("Assign roles" if roles_only else "Edit User")

    _m = users_df[users_df["id"].astype(str) == str(ueid)]
    if _m.empty:
        st.error("User not found or was removed.")
        st.session_state.pop("users_editing_id", None)
        st.session_state.pop("users_editing_roles_only", None)
        return
    row = _m.iloc[0]
    uname = str(row.get("name", "") or "")
    uemail = str(row.get("email", "") or "")
    st.caption(f"**{uname}** · {uemail}")

    if roles_only:
        render_roles_section_for_user(
            str(row["id"]),
            uname,
            key_prefix="user_edit_roles",
        )
        return

    edit_name = st.text_input("Name", value=row.get("name", ""), key="edit_u_name")
    edit_email = st.text_input("Email", value=row.get("email", ""), key="edit_u_email")
    edit_is_active = st.checkbox(
        "Active", value=bool(int(row.get("is_active", 1) or 1)), key="edit_u_active"
    )

    st.markdown("### Change Password (Optional)")
    new_password = st.text_input("New Password", type="password", key="edit_u_password")
    new_password_confirm = st.text_input(
        "Confirm New Password", type="password", key="edit_u_password_confirm"
    )

    if st.button("Save changes", key="save_user_btn"):
        errors = []
        if not edit_name.strip():
            errors.append("Name cannot be empty.")
        if not edit_email.strip():
            errors.append("Email cannot be empty.")
        elif "@" not in edit_email:
            errors.append("Invalid email format.")
        else:
            other_users = users_df[
                users_df["email"].str.strip().str.lower() == edit_email.strip().lower()
            ]
            if not other_users.empty and other_users.iloc[0]["id"] != row["id"]:
                errors.append("Email already taken by another user.")

        if new_password:
            if len(new_password) < 6:
                errors.append("Password must be at least 6 characters.")
            elif new_password != new_password_confirm:
                errors.append("Passwords do not match.")

        if errors:
            for error in errors:
                st.error(error)
        else:
            user_data = {
                "name": edit_name.strip(),
                "email": edit_email.strip().lower(),
                "is_active": 1 if edit_is_active else 0,
            }
            if new_password:
                user_data["password_hash"] = hash_password(new_password)

            if update_user(row["id"], user_data):
                current_user = get_current_user()
                log_action(
                    user_id=current_user["id"] if current_user else None,
                    user_name=current_user["name"] if current_user else "System",
                    action_type="edit",
                    entity_type="user",
                    entity_id=row["id"],
                    entity_name=edit_name.strip(),
                    action_details=f"Updated user: {edit_email}",
                    ip_address=get_user_ip(),
                )
                st.success("User updated.")
                load_all()
                st.session_state.selected_main = USERS_MAIN
                st.session_state.selected_sub = USER_SUB_MGMT
                st.session_state.pop("users_editing_id", None)
                st.session_state.pop("users_editing_roles_only", None)
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("Failed to update user.")

    if has_permission("roles.assign"):
        st.markdown("---")
        render_roles_section_for_user(
            str(row["id"]),
            (edit_name or "").strip() or uname,
            key_prefix="user_edit_roles",
        )

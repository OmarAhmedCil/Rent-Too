import streamlit as st
import time
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission, has_permission
from mgmt_ui.delete_dialog import MGMT_SUCCESS_FLASH
from .management import ROLES_MAIN
from .role_management import ROLE_SUB_MGMT
from .role_permissions_ui import render_permissions_section_for_role


def render_edit_role():
    load_all()
    roles_df = st.session_state.roles_df.copy()

    if roles_df.empty:
        st.info("No roles available.")
        return

    if "roles_edit_target_id" in st.session_state:
        st.session_state["roles_editing_id"] = str(st.session_state.pop("roles_edit_target_id"))

    reid = st.session_state.get("roles_editing_id")
    require_permission("roles.edit")

    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("← Role management", key="role_edit_back_mgmt"):
            st.session_state.pop("roles_editing_id", None)
            st.session_state.selected_main = ROLES_MAIN
            st.session_state.selected_sub = ROLE_SUB_MGMT
            st.rerun()

    if not reid:
        st.warning("Open **Role management** and choose **Edit** on a row.")
        return

    st.header("Edit role")
    _m = roles_df[roles_df["id"].astype(str) == str(reid)]
    if _m.empty:
        st.error("Role not found or was removed.")
        st.session_state.pop("roles_editing_id", None)
        return
    row = _m.iloc[0]
    rname = str(row.get("role_name", "") or "")
    st.caption(f"**{rname}** · ID `{row['id']}`")

    edit_role_name = st.text_input("Role name", value=row.get("role_name", ""), key="edit_role_name_mgmt")
    edit_role_desc = st.text_area(
        "Description",
        value=str(row.get("description", "") or ""),
        key="edit_role_desc_mgmt",
        height=100,
    )

    if st.button("Save changes", key="save_role_mgmt_btn"):
        if not edit_role_name.strip():
            st.error("Role name cannot be empty.")
        else:
            other = roles_df[
                roles_df["role_name"].str.strip().str.lower() == edit_role_name.strip().lower()
            ]
            if not other.empty and str(other.iloc[0]["id"]) != str(row["id"]):
                st.error("Another role already uses this name.")
            else:
                role_data = {
                    "role_name": edit_role_name.strip(),
                    "description": (edit_role_desc or "").strip(),
                }
                if update_role(row["id"], role_data):
                    cur = get_current_user()
                    log_action(
                        user_id=cur["id"] if cur else None,
                        user_name=cur["name"] if cur else "System",
                        action_type="edit",
                        entity_type="role",
                        entity_id=str(row["id"]),
                        entity_name=edit_role_name.strip(),
                        action_details=f"Updated role: {edit_role_name.strip()}",
                        ip_address=get_user_ip(),
                    )
                    load_all()
                    st.session_state.selected_main = ROLES_MAIN
                    st.session_state.selected_sub = ROLE_SUB_MGMT
                    st.session_state.pop("roles_editing_id", None)
                    st.session_state[MGMT_SUCCESS_FLASH] = "Role updated."
                    time.sleep(0.25)
                    st.rerun()
                else:
                    st.error("Failed to update role.")

    st.markdown("---")
    render_permissions_section_for_role(
        str(row["id"]),
        (edit_role_name or "").strip() or rname,
        key_prefix="role_edit",
    )

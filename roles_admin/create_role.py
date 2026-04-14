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
from .role_permissions_ui import _perm_label_row


def render_create_role():
    require_permission("roles.create")
    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("← Role management", key="role_create_back_mgmt"):
            st.session_state.selected_main = ROLES_MAIN
            st.session_state.selected_sub = ROLE_SUB_MGMT
            st.rerun()
    st.header("Create role")
    load_all()
    roles_df = st.session_state.roles_df.copy()
    permissions_df = st.session_state.permissions_df.copy()

    with st.form("form_add_role_mgmt", clear_on_submit=False):
        st.subheader("New role")
        new_role_name = st.text_input("Role name*")
        new_role_desc = st.text_area("Description", height=100)

        picked_perm_ids: list[str] = []
        if has_permission("roles.edit") and permissions_df is not None and not permissions_df.empty:
            labels: list[str] = []
            id_by_label: dict[str, str] = {}
            for _, p in permissions_df.iterrows():
                lbl = _perm_label_row(p)
                if lbl in id_by_label:
                    lbl = f"{lbl} [{p['id']}]"
                labels.append(lbl)
                id_by_label[lbl] = str(p["id"])
            picked_labels = st.multiselect(
                "Initial permissions (optional)",
                options=sorted(labels),
                key="create_role_perms_ms",
                help="You can add or change permissions later on **Edit role**.",
            )
            picked_perm_ids = [id_by_label[x] for x in picked_labels if x in id_by_label]

        submitted = st.form_submit_button("Create role")

    if not submitted:
        return

    if not new_role_name.strip():
        st.error("Role name is required.")
        return
    if not roles_df[roles_df["role_name"].str.strip().str.lower() == new_role_name.strip().lower()].empty:
        st.error("A role with this name already exists.")
        return

    nid = next_int_id(roles_df, 1)
    role_data = {
        "id": str(nid),
        "role_name": new_role_name.strip(),
        "description": (new_role_desc or "").strip(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not insert_role(role_data):
        st.error("Failed to create role.")
        return

    cur = get_current_user()
    log_action(
        user_id=cur["id"] if cur else None,
        user_name=cur["name"] if cur else "System",
        action_type="create",
        entity_type="role",
        entity_id=str(nid),
        entity_name=new_role_name.strip(),
        action_details=f"Created role: {new_role_name.strip()}",
        ip_address=get_user_ip(),
    )

    if picked_perm_ids and has_permission("roles.edit"):
        if insert_role_permissions_bulk(str(nid), picked_perm_ids):
            log_action(
                user_id=cur["id"] if cur else None,
                user_name=cur["name"] if cur else "System",
                action_type="edit",
                entity_type="role",
                entity_id=str(nid),
                entity_name=new_role_name.strip(),
                action_details=f"Set initial permissions on new role ({len(picked_perm_ids)} items)",
                ip_address=get_user_ip(),
            )
        else:
            st.warning("Role was created but assigning initial permissions failed. Add them from **Edit role**.")

    load_all()
    st.session_state.selected_main = ROLES_MAIN
    st.session_state.selected_sub = ROLE_SUB_MGMT
    st.session_state[MGMT_SUCCESS_FLASH] = "Role created."
    time.sleep(0.25)
    st.rerun()

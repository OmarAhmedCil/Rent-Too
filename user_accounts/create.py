import streamlit as st
import time
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import hash_password, get_current_user, get_user_ip
from core.permissions import require_permission, has_permission
from .management import USERS_MAIN, USER_SUB_MGMT
from .user_roles_ui import apply_role_assignments_after_create, role_name_to_id_map


def render_create_user():
    """Render create user form"""
    require_permission('users.create')
    bc1, bc2 = st.columns([1, 4])
    with bc1:
        if st.button("← User management", key="user_create_back_mgmt"):
            st.session_state.selected_main = USERS_MAIN
            st.session_state.selected_sub = USER_SUB_MGMT
            st.rerun()
    st.header("Create User")
    load_all()
    users_df = st.session_state.users_df.copy()
    
    with st.form("form_add_user", clear_on_submit=True):
        st.subheader("Add new user")
        new_email = st.text_input("Email*")
        new_name = st.text_input("Name*")
        new_password = st.text_input("Password*", type="password")
        new_password_confirm = st.text_input("Confirm Password*", type="password")
        is_active = st.checkbox("Active", value=True)

        picked_role_names: list[str] = []
        if has_permission("roles.assign"):
            _rdf = st.session_state.get("roles_df", None)
            if _rdf is not None and not _rdf.empty:
                _role_opts = sorted(
                    _rdf["role_name"].dropna().astype(str).str.strip().unique().tolist()
                )
                picked_role_names = st.multiselect(
                    "Roles (optional)",
                    options=_role_opts,
                    key="create_user_roles_ms",
                    help="These roles are applied right after the account is created.",
                )

        if st.form_submit_button("Add User"):
            errors = []
            if not new_email.strip():
                errors.append("Email is required.")
            elif not '@' in new_email:
                errors.append("Invalid email format.")
            elif not users_df[users_df['email'].str.strip().str.lower() == new_email.strip().lower()].empty:
                errors.append("Email already exists.")
            
            if not new_name.strip():
                errors.append("Name is required.")
            
            if not new_password:
                errors.append("Password is required.")
            elif len(new_password) < 6:
                errors.append("Password must be at least 6 characters.")
            elif new_password != new_password_confirm:
                errors.append("Passwords do not match.")
            
            if errors:
                for error in errors:
                    st.error(error)
            else:
                nid = next_int_id(users_df, 1)
                user_data = {
                    "id": str(nid),
                    "email": new_email.strip().lower(),
                    "password_hash": hash_password(new_password),
                    "name": new_name.strip(),
                    "is_active": 1 if is_active else 0,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                if insert_user(user_data):
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='create',
                        entity_type='user',
                        entity_id=str(nid),
                        entity_name=new_name.strip(),
                        action_details=f"Created user: {new_email}",
                        ip_address=get_user_ip()
                    )
                    load_all()
                    if picked_role_names and has_permission("roles.assign"):
                        nm_map = role_name_to_id_map(st.session_state.roles_df.copy())
                        rids = [nm_map[n] for n in picked_role_names if n in nm_map]
                        if rids:
                            apply_role_assignments_after_create(
                                str(nid),
                                rids,
                                new_name.strip(),
                                new_email.strip().lower(),
                            )
                    load_all()
                    st.success(f"Added user: {new_name} (ID {nid})")
                    st.session_state.selected_main = USERS_MAIN
                    st.session_state.selected_sub = USER_SUB_MGMT
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.error("Failed to add user.")

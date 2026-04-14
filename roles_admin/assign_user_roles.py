"""Deprecated: use Create user / Edit user / User management → Roles."""

import streamlit as st
from user_accounts.management import USERS_MAIN, USER_SUB_MGMT


def render_assign_user_roles():
    st.session_state.selected_main = USERS_MAIN
    st.session_state.selected_sub = USER_SUB_MGMT
    st.rerun()

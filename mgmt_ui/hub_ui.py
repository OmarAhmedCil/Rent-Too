# Shared controls for management hub pages (e.g. Create → full create flow).
import streamlit as st


def render_hub_create_button(
    *,
    permission: str,
    button_key: str,
    label: str,
    nav_main: str,
    nav_sub: str,
) -> None:
    """Green-styled Create on hub pages; navigates via session state (keys: mgmt_hub_create_* in style.css)."""
    from core.permissions import has_permission

    if not has_permission(permission):
        return
    if st.button(label, key=button_key, use_container_width=True):
        st.session_state.selected_main = nav_main
        st.session_state.selected_sub = nav_sub
        st.rerun()

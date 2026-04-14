# Action logs: management entry.
import streamlit as st
from core.permissions import require_permission


def render_log_management():
    require_permission("logs.view")
    from tabs.action_logs import render_action_logs_tab

    render_action_logs_tab()

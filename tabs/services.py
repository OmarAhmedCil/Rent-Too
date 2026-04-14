# Services router (implementation in `services/` package).
import streamlit as st
from core.permissions import require_permission
from services import render_service_management


def render_services_tab():
    require_permission("services.view")
    render_service_management()

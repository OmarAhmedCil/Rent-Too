# Lessors router (implementation in `lessors/` package).
import streamlit as st
from core.permissions import require_permission
from lessors import render_lessor_management


def render_lessors_tab():
    require_permission("lessors.view")
    render_lessor_management()

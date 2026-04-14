# Contracts router (thin wrapper around `contracts/` package).
import streamlit as st
from core.permissions import require_permission, has_permission
from contracts import render_contract_management


def render_contracts_tab():
    """Default contracts area: open management hub."""
    require_permission("contracts.view")
    render_contract_management()

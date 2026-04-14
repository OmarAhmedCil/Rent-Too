# Bulk import: management entry (same workflow as legacy single page).
import streamlit as st
from core.permissions import require_permission


def render_bulk_import_management():
    require_permission("bulk_import.view")
    from .bulk_import import render_bulk_import_tab

    render_bulk_import_tab()

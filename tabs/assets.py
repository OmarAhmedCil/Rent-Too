# Assets router (implementation in `assets/` package).
import streamlit as st
from core.permissions import require_permission
from assets import render_asset_management


def render_assets_tab():
    require_permission("assets.view")
    render_asset_management()

# app.py
# Main application file
import re
import streamlit as st
import os
from core.utils import *
from conf.constants import *
from core.paths import resolve_static_logo_path
from core.auth import require_login, get_current_user, logout_user
from tabs.lessors import render_lessors_tab
from tabs.assets import render_assets_tab
from tabs.services import render_services_tab
from tabs.contracts import render_contracts_tab
from tabs.users import render_users_tab
from tabs.roles import render_roles_tab
from mgmt_ui.button_styles import inject_bulk_action_button_css, inject_management_hub_button_css


def _streamlit_key_css_class(button_key: str) -> str:
    """Class Streamlit adds to keyed widgets: st-key-<sanitized> (same rule as frontend convertKeyToClassName)."""
    return "st-key-" + re.sub(r"[^a-zA-Z0-9_-]", "-", button_key.strip())


def _nav_sub_button_key(parent_label: str, sub_item: str) -> str:
    """Stable keys for Create-* nav items so CSS can target st-key-<key> (see style.css)."""
    _create = {
        "Create Contract": "nav_create_contract",
        "Create Lessor": "nav_create_lessor",
        "Create Asset": "nav_create_asset",
        "Create Service": "nav_create_service",
        "Create User": "nav_create_user",
        "Create Role": "nav_create_role",
    }
    if sub_item in _create:
        return _create[sub_item]
    return f"nav_{parent_label}_{sub_item}"


# ---------------------------
# Initialize Database (default data)
# ---------------------------
initialize_database()

# ---------------------------
# Page Config & CSS
# ---------------------------
st.set_page_config(page_title="Contract Tool", layout="wide")

# Load external CSS
_APP_DIR = os.path.dirname(os.path.abspath(__file__))


def local_css(file_name):
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        st.warning(f"⚠️ `{file_name}` not found — using default styling.")

local_css(os.path.join(_APP_DIR, "static", "style.css"))
inject_management_hub_button_css()
inject_bulk_action_button_css()

# ---------------------------
# Authentication Check
# ---------------------------
require_login()

# ---------------------------
# Load DataFrames
# ---------------------------
load_all()

# ---------------------------
# Sidebar Navigation
# ---------------------------
with st.sidebar:
    # Custom CSS for professional sidebar
    st.markdown("""
    <style>
    /* Sidebar shell — white + divider (dashboard / MDB-style) */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div,
    [data-testid="stSidebarContent"] {
        background: #ffffff !important;
        background-image: none !important;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid #e5e7eb !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h4 {
        color: #111827 !important;
    }
    /* Inset rows + light horizontal dividers */
    [data-testid="stSidebar"] .stButton {
        margin-left: 12px !important;
        margin-right: 12px !important;
        width: calc(100% - 24px) !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
        padding-bottom: 6px !important;
        margin-bottom: 6px !important;
        border-bottom: 1px solid #eef0f2 !important;
    }
    [data-testid="stSidebar"] .streamlit-expander {
        margin-left: 12px !important;
        margin-right: 12px !important;
        width: calc(100% - 24px) !important;
        box-sizing: border-box !important;
        padding-bottom: 4px !important;
        margin-bottom: 6px !important;
        border-bottom: 1px solid #eef0f2 !important;
    }
    [data-testid="stSidebar"] .streamlit-expander .stButton {
        margin-left: 0 !important;
        margin-right: 0 !important;
        width: 100% !important;
    }
    [data-testid="stSidebar"] .streamlit-expander .stButton:last-child {
        border-bottom: none !important;
        margin-bottom: 0 !important;
        padding-bottom: 2px !important;
    }
    /* Nav pills: default yellow (gold); hover lighter */
    [data-testid="stSidebar"] .stButton > button,
    [data-testid="stSidebar"] .stButton button {
        background-color: #FFD700 !important;
        background-image: none !important;
        color: #111827 !important;
        border: 1px solid #b59b00 !important;
        border-radius: 8px !important;
        transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, color 0.2s ease !important;
        width: 100% !important;
        font-weight: 500 !important;
        padding: 10px 14px !important;
        font-size: 0.9rem !important;
        min-height: 42px !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] .stButton > button p, [data-testid="stSidebar"] .stButton > button span,
    [data-testid="stSidebar"] .stButton button p, [data-testid="stSidebar"] .stButton button span {
        color: inherit !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover, [data-testid="stSidebar"] .stButton button:hover {
        background-color: #FFEB5A !important;
        border-color: #c4a600 !important;
        color: #111827 !important;
        box-shadow: none !important;
    }
    /* Logout only — Streamlit 1.52+ defaults st.button to type=secondary; do NOT style all secondary buttons or every nav row looks pink */
    [data-testid="stSidebar"] .st-key-logout_btn > button,
    [data-testid="stSidebar"] .st-key-logout_btn button {
        background-color: rgba(231, 76, 60, 0.08) !important;
        border-color: rgba(231, 76, 60, 0.35) !important;
        color: #991b1b !important;
    }
    [data-testid="stSidebar"] .st-key-logout_btn > button:hover,
    [data-testid="stSidebar"] .st-key-logout_btn button:hover {
        background-color: rgba(231, 76, 60, 0.15) !important;
        color: #7f1d1d !important;
    }
    [data-testid="stSidebar"] .stButton > button:focus-visible,
    [data-testid="stSidebar"] .stButton button:focus-visible {
        background-color: #FFEB5A !important;
        border-color: #c4a600 !important;
        color: #111827 !important;
        outline: none !important;
        box-shadow: 0 0 0 2px rgba(255, 215, 0, 0.55) !important;
    }
    [data-testid="stSidebar"] .st-key-logout_btn > button:focus-visible,
    [data-testid="stSidebar"] .st-key-logout_btn button:focus-visible {
        background-color: rgba(231, 76, 60, 0.15) !important;
        border-color: rgba(231, 76, 60, 0.5) !important;
        color: #7f1d1d !important;
        box-shadow: 0 0 0 2px rgba(231, 76, 60, 0.25) !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] {
        background-color: #f9fafb !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderHeader {
        color: #6b7280 !important;
        font-weight: 500 !important;
        background-color: transparent !important;
        background-image: none !important;
        border-radius: 8px !important;
        padding: 10px 14px !important;
        margin: 0 !important;
        font-size: 0.9rem !important;
        border: 1px solid transparent !important;
        transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderHeader p,
    [data-testid="stSidebar"] .streamlit-expanderHeader span {
        color: #6b7280 !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderHeader:hover p,
    [data-testid="stSidebar"] .streamlit-expanderHeader:hover span {
        color: #111827 !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderHeader svg {
        color: #6b7280 !important;
        fill: #6b7280 !important;
        stroke: #6b7280 !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderHeader:hover {
        background-color: #FFF3CD !important;
        border-color: #e6d08c !important;
        color: #111827 !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderHeader:hover svg {
        color: #111827 !important;
        fill: #111827 !important;
        stroke: #111827 !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderContent {
        padding-left: 6px !important;
        padding-top: 4px !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderContent .stButton > button,
    [data-testid="stSidebar"] .streamlit-expanderContent .stButton button {
        background-color: transparent !important;
        font-size: 0.88rem !important;
        padding: 8px 12px !important;
        min-height: 38px !important;
        line-height: 1.3 !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderContent .stButton > button:hover,
    [data-testid="stSidebar"] .streamlit-expanderContent .stButton button:hover {
        background-color: #FFEB5A !important;
        border-color: #c4a600 !important;
        color: #111827 !important;
    }
    [data-testid="stSidebar"] [class*="st-key-nav_create_"] button {
        background-color: #82e0aa !important;
        color: #ffffff !important;
        border: 1px solid #58d68d !important;
    }
    [data-testid="stSidebar"] [class*="st-key-nav_create_"] button:hover {
        background-color: #58d68d !important;
        border-color: #48c774 !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] [class*="st-key-nav_create_"] button p,
    [data-testid="stSidebar"] [class*="st-key-nav_create_"] button span {
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] .streamlit-expanderContent .stButton > button:focus-visible,
    [data-testid="stSidebar"] .streamlit-expanderContent .stButton button:focus-visible {
        background-color: #FFEB5A !important;
        border-color: #c4a600 !important;
        color: #111827 !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: #e5e7eb !important;
        margin: 12px 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Logo Section (static/logo.png|.jpg|.jpeg|.svg)
    st.markdown("<div style='text-align: center; padding: 20px 0;'>", unsafe_allow_html=True)
    logo_path = resolve_static_logo_path()
    if logo_path:
        st.image(logo_path, width=180)
    else:
        st.markdown("<h2 style='color: #111827; text-align: center;'>Contract Tool</h2>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<hr style='border-color: #e5e7eb; margin-left: 12px; margin-right: 12px;'>", unsafe_allow_html=True)
    
    # User Info Section
    current_user = get_current_user()
    if current_user:
        st.markdown(f"""
        <div style='background-color: #f3f4f6; padding: 15px; border-radius: 8px; margin: 10px 12px; border: 1px solid #e5e7eb;'>
            <p style='color: #111827; margin: 0; font-weight: bold;'>👤 {current_user['name']}</p>
            <p style='color: #4b5563; margin: 5px 0 0 0; font-size: 0.9em;'>{current_user['email']}</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚪 Logout", key="logout_btn", use_container_width=True, type="secondary"):
            logout_user()
        
        st.markdown("<hr style='border-color: #e5e7eb; margin: 20px 12px;'>", unsafe_allow_html=True)
    
    # Navigation Menu
    st.markdown("<h3 style='color: #111827; margin: 0 12px 15px 12px;'>📋 Navigation</h3>", unsafe_allow_html=True)
    
    # Initialize session state for navigation
    if 'selected_main' not in st.session_state:
        st.session_state.selected_main = "🏠 Home"
    if 'selected_sub' not in st.session_state:
        st.session_state.selected_sub = None
    
    # Import permission checker
    from core.permissions import has_permission
    
    # Main Navigation Sections - filter based on permissions
    main_sections = {}
    
    # Home/Dashboard
    if has_permission('dashboard.view'):
        main_sections["🏠 Home"] = None
    
    # Contracts: Create is on Contract Management page (sidebar Create only if user can create but not view hub)
    contract_sub_items = []
    if has_permission("contracts.view"):
        contract_sub_items.append("Contract Management")
    elif has_permission("contracts.create"):
        contract_sub_items.append("Create Contract")
    if contract_sub_items:
        main_sections["📄 Contracts"] = contract_sub_items
    
    # Lessors — Create on Lessor Management when user can view
    if has_permission('lessors.view'):
        main_sections["👥 Lessors"] = ["Lessor Management"]
    elif has_permission('lessors.create'):
        main_sections["👥 Lessors"] = ["Create Lessor"]
    
    # Assets — Create on Asset Management when user can view
    if has_permission('assets.view'):
        main_sections["🏢 Assets"] = ["Asset Management"]
    elif has_permission('assets.create'):
        main_sections["🏢 Assets"] = ["Create Asset"]
    
    # Services — Create on Service Management when user can view
    if has_permission('services.view'):
        main_sections["🔧 Services"] = ["Service Management"]
    elif has_permission('services.create'):
        main_sections["🔧 Services"] = ["Create Service"]
    
    # Distribution — single hub (generate / regenerate / delete per contract on management page)
    if has_permission('distribution.view'):
        main_sections["📊 Distribution"] = ["Contracts Distribution"]
    
    # Payments — hub only (Edit Payment is accessed via row button in Payment Center)
    if has_permission('payments.view'):
        main_sections["💳 Payments"] = ["Payment Center"]
    
    # Email Notifications — hub only; create/edit flows open from Notifications Center
    if has_permission('email.view'):
        main_sections["📧 Email Notifications"] = ["Notifications Center"]
    
    # Download Data — hub only; exports open from Reports Center
    if has_permission('download.view'):
        main_sections["📥 Download Data"] = ["Reports Center"]
    
    # Bulk Import — management entry in sidebar
    if has_permission('bulk_import.view'):
        main_sections["📤 Bulk Import"] = ["Data Upload"]
    
    # Admin sections (check permissions)
    admin_sections = {}
    if has_permission('users.view'):
        admin_sections["👤 Users"] = ["User Management"]
    elif has_permission('users.create'):
        admin_sections["👤 Users"] = ["Create User"]
    
    if has_permission('roles.view'):
        role_sub_items = ["Role Management", "Manage Permissions"]
        admin_sections["🔐 Roles"] = role_sub_items
    
    if has_permission('logs.view'):
        admin_sections["📝 Action Logs"] = ["Log Report"]
    
    if admin_sections:
        main_sections["⚙️ Administration"] = admin_sections
    
    # Render navigation
    selected_main = st.session_state.selected_main
    selected_sub = st.session_state.selected_sub
    
    for section_name, sub_items in main_sections.items():
        if section_name == "⚙️ Administration":
            st.markdown("<h4 style='color: #111827; margin: 20px 12px 8px 12px; font-size: 1em;'>⚙️ Administration</h4>", unsafe_allow_html=True)
            for admin_name, admin_sub in admin_sections.items():
                if admin_sub:
                    st.markdown(
                        f"<p style='color: #6b7280; font-size: 0.85rem; font-weight: 600; margin: 12px 12px 4px 12px;'>{admin_name}</p>",
                        unsafe_allow_html=True,
                    )
                    for sub_item in admin_sub:
                        is_selected = (selected_main == admin_name and selected_sub == sub_item)
                        button_key = _nav_sub_button_key(admin_name, sub_item)
                        button_class = "nav-selected" if is_selected else ""
                        if st.button(
                            f"  {sub_item}",
                            key=button_key,
                            use_container_width=True,
                        ):
                            st.session_state.selected_main = admin_name
                            st.session_state.selected_sub = sub_item
                            st.rerun()
                        if is_selected:
                            st.markdown(f"""
                            <style>
                            [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button {{
                                background-color: #FFE082 !important;
                                color: #111827 !important;
                                border: 1px solid #d4a017 !important;
                                border-radius: 8px !important;
                                font-weight: 600 !important;
                                box-shadow: 0 6px 18px rgba(255, 193, 7, 0.45), 0 2px 6px rgba(212, 160, 23, 0.25) !important;
                            }}
                            [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button p,
                            [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button span {{
                                color: #111827 !important;
                            }}
                            </style>
                            """, unsafe_allow_html=True)
                else:
                    is_selected = (selected_main == admin_name)
                    button_key = f"nav_{admin_name}"
                    if st.button(f"  {admin_name}", key=button_key, use_container_width=True):
                        st.session_state.selected_main = admin_name
                        st.session_state.selected_sub = None
                        st.rerun()
                    if is_selected:
                        st.markdown(f"""
                        <style>
                        [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button {{
                            background-color: #FFE082 !important;
                            color: #111827 !important;
                            border: 1px solid #d4a017 !important;
                            border-radius: 8px !important;
                            font-weight: 600 !important;
                            box-shadow: 0 6px 18px rgba(255, 193, 7, 0.45), 0 2px 6px rgba(212, 160, 23, 0.25) !important;
                        }}
                        [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button p,
                        [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button span {{
                            color: #111827 !important;
                        }}
                        </style>
                        """, unsafe_allow_html=True)
        elif sub_items is None:
            # No sub-items, direct button
            is_selected = (selected_main == section_name)
            button_key = f"nav_{section_name}"
            if st.button(section_name, key=button_key, use_container_width=True):
                st.session_state.selected_main = section_name
                st.session_state.selected_sub = None
                st.rerun()
            # Add custom styling for selected button - highlight style
            if is_selected:
                st.markdown(f"""
                <style>
                [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button {{
                    background-color: #FFE082 !important;
                    color: #111827 !important;
                    border: 1px solid #d4a017 !important;
                    border-radius: 8px !important;
                    font-weight: 600 !important;
                    box-shadow: 0 6px 18px rgba(255, 193, 7, 0.45), 0 2px 6px rgba(212, 160, 23, 0.25) !important;
                }}
                [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button p,
                [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button span {{
                    color: #111827 !important;
                }}
                </style>
                """, unsafe_allow_html=True)
        else:
            # Has sub-items — flat list (no expander / collapse)
            st.markdown(
                f"<p style='color: #6b7280; font-size: 0.85rem; font-weight: 600; margin: 14px 12px 6px 12px;'>{section_name}</p>",
                unsafe_allow_html=True,
            )
            for sub_item in sub_items:
                is_selected = (selected_main == section_name and selected_sub == sub_item)
                button_key = _nav_sub_button_key(section_name, sub_item)
                if st.button(
                    f"  {sub_item}",
                    key=button_key,
                    use_container_width=True,
                ):
                    st.session_state.selected_main = section_name
                    st.session_state.selected_sub = sub_item
                    st.rerun()
                if is_selected:
                    st.markdown(f"""
                    <style>
                    [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button {{
                        background-color: #FFE082 !important;
                        color: #111827 !important;
                        border: 1px solid #d4a017 !important;
                        border-radius: 8px !important;
                        font-weight: 600 !important;
                        box-shadow: 0 6px 18px rgba(255, 193, 7, 0.45), 0 2px 6px rgba(212, 160, 23, 0.25) !important;
                    }}
                    [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button p,
                    [data-testid="stSidebar"] .{_streamlit_key_css_class(button_key)} button span {{
                        color: #111827 !important;
                    }}
                    </style>
                    """, unsafe_allow_html=True)
    
    # Get current selection
    selected_main = st.session_state.selected_main
    selected_sub = st.session_state.selected_sub

# ---------------------------
# Main Content Area
# ---------------------------
# Header
st.markdown("<h2 style='text-align: center; margin-bottom: 30px;'>Contract Management Tool</h2>", unsafe_allow_html=True)

# Render selected page based on navigation
selected_main = st.session_state.get('selected_main', '🏠 Home')
selected_sub = st.session_state.get('selected_sub', None)

if selected_main == "🏠 Home":
    from dashboard import render_dashboard
    render_dashboard()

elif selected_main == "📄 Contracts":
    from core.permissions import has_permission as _has_contract_page

    _contract_pages = []
    if _has_contract_page("contracts.view"):
        _contract_pages.append("Contract Management")
    if _has_contract_page("contracts.create"):
        _contract_pages.append("Create Contract")
    if _has_contract_page("contracts.edit"):
        _contract_pages.append("Edit Contract")
    if _has_contract_page("contracts.delete"):
        _contract_pages.append("Delete Contract")

    if _contract_pages and (
        selected_sub is None or selected_sub not in _contract_pages
    ):
        st.session_state.selected_sub = _contract_pages[0]
        st.rerun()

    if selected_sub == "Contract Management":
        from contracts import render_contract_management

        render_contract_management()
    elif selected_sub == "Create Contract":
        from contracts import render_create_contract

        render_create_contract()
    elif selected_sub == "Edit Contract":
        from contracts import render_edit_contract

        render_edit_contract()
    elif selected_sub == "Delete Contract":
        from contracts import render_delete_contract

        render_delete_contract()
    else:
        render_contracts_tab()

elif selected_main == "👥 Lessors":
    from core.permissions import has_permission as _has_lessor_page

    _lessor_pages = []
    if _has_lessor_page("lessors.view"):
        _lessor_pages.append("Lessor Management")
    if _has_lessor_page("lessors.create"):
        _lessor_pages.append("Create Lessor")
    if _has_lessor_page("lessors.edit"):
        _lessor_pages.append("Edit Lessor")
    if _has_lessor_page("lessors.delete"):
        _lessor_pages.append("Delete Lessor")

    if _lessor_pages and (
        selected_sub is None or selected_sub not in _lessor_pages
    ):
        st.session_state.selected_sub = _lessor_pages[0]
        st.rerun()

    if selected_sub == "Lessor Management":
        from lessors import render_lessor_management

        render_lessor_management()
    elif selected_sub == "Create Lessor":
        from lessors import render_create_lessor

        render_create_lessor()
    elif selected_sub == "Edit Lessor":
        from lessors import render_edit_lessor

        render_edit_lessor()
    elif selected_sub == "Delete Lessor":
        from lessors import render_delete_lessor

        render_delete_lessor()
    else:
        render_lessors_tab()

elif selected_main == "🏢 Assets":
    from core.permissions import has_permission as _has_asset_page

    _asset_pages = []
    if _has_asset_page("assets.view"):
        _asset_pages.append("Asset Management")
    if _has_asset_page("assets.create"):
        _asset_pages.append("Create Asset")
    if _has_asset_page("assets.edit"):
        _asset_pages.append("Edit Asset")
    if _has_asset_page("assets.delete"):
        _asset_pages.append("Delete Asset")

    if _asset_pages and (
        selected_sub is None or selected_sub not in _asset_pages
    ):
        st.session_state.selected_sub = _asset_pages[0]
        st.rerun()

    if selected_sub == "Asset Management":
        from assets import render_asset_management

        render_asset_management()
    elif selected_sub == "Create Asset":
        from assets import render_create_asset

        render_create_asset()
    elif selected_sub == "Edit Asset":
        from assets import render_edit_asset

        render_edit_asset()
    elif selected_sub == "Delete Asset":
        from assets import render_delete_asset

        render_delete_asset()
    else:
        render_assets_tab()

elif selected_main == "🔧 Services":
    from core.permissions import has_permission as _has_service_page

    _service_pages = []
    if _has_service_page("services.view"):
        _service_pages.append("Service Management")
    if _has_service_page("services.create"):
        _service_pages.append("Create Service")
    if _has_service_page("services.edit"):
        _service_pages.append("Edit Service")
    if _has_service_page("services.delete"):
        _service_pages.append("Delete Service")

    if _service_pages and (
        selected_sub is None or selected_sub not in _service_pages
    ):
        st.session_state.selected_sub = _service_pages[0]
        st.rerun()

    if selected_sub == "Service Management":
        from services import render_service_management

        render_service_management()
    elif selected_sub == "Create Service":
        from services import render_create_service

        render_create_service()
    elif selected_sub == "Edit Service":
        from services import render_edit_service

        render_edit_service()
    elif selected_sub == "Delete Service":
        from services import render_delete_service

        render_delete_service()
    else:
        render_services_tab()

elif selected_main == "📊 Distribution":
    from core.permissions import has_permission as _has_dist_page

    if not _has_dist_page("distribution.view"):
        st.error("You do not have permission to view distribution.")
    else:
        if selected_sub != "Contracts Distribution":
            st.session_state.selected_sub = "Contracts Distribution"
            st.rerun()

        from distribution import render_distribution_management

        render_distribution_management()

elif selected_main == "💳 Payments":
    from core.permissions import has_permission as _has_pay_page

    # "Edit Payment" is not in the sidebar but is a valid programmatic destination
    _pay_pages = ["Payment Center", "Edit Payment"]

    if selected_sub is None or selected_sub not in _pay_pages:
        st.session_state.selected_sub = "Payment Center"
        st.rerun()

    if selected_sub == "Payment Center":
        from weekly_payments_ui import render_payment_management

        render_payment_management()
    elif selected_sub == "Edit Payment":
        from tabs.weekly_payments import render_edit_payment

        render_edit_payment()

elif selected_main == "📧 Email Notifications":
    _email_pages = [
        "Notifications Center",
        "Create Weekly Payment Notification",
        "Create Contract Reminder",
        "Edit Email Notification",
    ]

    if selected_sub is None or selected_sub not in _email_pages:
        st.session_state.selected_sub = _email_pages[0]
        st.rerun()

    if selected_sub == "Notifications Center":
        from tabs.email_notifications import render_notification_management
        render_notification_management()
    elif selected_sub == "Create Weekly Payment Notification":
        from tabs.email_notifications import render_create_weekly_payment_notification
        render_create_weekly_payment_notification()
    elif selected_sub == "Create Contract Reminder":
        from tabs.email_notifications import render_create_contract_reminder_notification
        render_create_contract_reminder_notification()
    elif selected_sub == "Edit Email Notification":
        from tabs.email_notifications import render_edit_email_notification
        render_edit_email_notification()
    else:
        from tabs.email_notifications import render_notification_management
        render_notification_management()

elif selected_main == "📥 Download Data":
    from core.permissions import has_permission as _has_dl_page

    _dl_pages = ["Reports Center"]
    if _has_dl_page("download.contracts"):
        _dl_pages.append("Download Contracts")
    if _has_dl_page("download.lessors"):
        _dl_pages.append("Download Lessors")
    if _has_dl_page("download.assets"):
        _dl_pages.append("Download Assets")
    if _has_dl_page("download.services"):
        _dl_pages.append("Download Services")
    if _has_dl_page("download.distribution"):
        _dl_pages.append("Download Distribution")
        _dl_pages.append("Download Distribution (contract month)")
    if _has_dl_page("download.service_distribution"):
        _dl_pages.append("Download Service Distribution")
    if _has_dl_page("download.payments"):
        _dl_pages.append("Download Payments")

    if selected_sub is None or selected_sub not in _dl_pages:
        st.session_state.selected_sub = _dl_pages[0]
        st.rerun()

    if selected_sub == "Reports Center":
        from download_center import render_download_management

        render_download_management()
    elif selected_sub == "Download Contracts":
        from tabs.download_data import render_download_contracts

        render_download_contracts()
    elif selected_sub == "Download Lessors":
        from tabs.download_data import render_download_lessors

        render_download_lessors()
    elif selected_sub == "Download Assets":
        from tabs.download_data import render_download_assets

        render_download_assets()
    elif selected_sub == "Download Services":
        from tabs.download_data import render_download_services

        render_download_services()
    elif selected_sub == "Download Distribution":
        from tabs.download_data import render_download_distribution

        render_download_distribution()
    elif selected_sub == "Download Distribution (contract month)":
        from tabs.download_data import render_download_distribution_contract_level

        render_download_distribution_contract_level()
    elif selected_sub == "Download Service Distribution":
        from tabs.download_data import render_download_service_distribution

        render_download_service_distribution()
    elif selected_sub == "Download Payments":
        from tabs.download_data import render_download_payments

        render_download_payments()
    else:
        from download_center import render_download_management

        render_download_management()

elif selected_main == "📤 Bulk Import":
    if selected_sub is None or selected_sub != "Data Upload":
        st.session_state.selected_sub = "Data Upload"
        st.rerun()
    from bulk_import_ui import render_bulk_import_management

    render_bulk_import_management()

elif selected_main == "👤 Users":
    from core.permissions import has_permission as _has_user_page

    _user_pages = []
    if _has_user_page("users.view"):
        _user_pages.append("User Management")
    if _has_user_page("users.create"):
        _user_pages.append("Create User")
    if _has_user_page("users.edit") or _has_user_page("roles.assign"):
        _user_pages.append("Edit User")

    if _user_pages and (
        selected_sub is None or selected_sub not in _user_pages
    ):
        st.session_state.selected_sub = _user_pages[0]
        st.rerun()

    if selected_sub == "User Management":
        from user_accounts import render_user_management

        render_user_management()
    elif selected_sub == "Create User":
        from user_accounts import render_create_user

        render_create_user()
    elif selected_sub == "Edit User":
        from user_accounts import render_edit_user

        render_edit_user()
    else:
        from tabs.users import render_users_tab

        render_users_tab()

elif selected_main == "🔐 Roles":
    from core.permissions import has_permission as _has_role_page

    _role_pages = []
    if _has_role_page("roles.view"):
        _role_pages.append("Role Management")
    if _has_role_page("roles.create"):
        _role_pages.append("Create Role")
    if _has_role_page("roles.view"):
        _role_pages.append("Manage Permissions")
    if _has_role_page("roles.edit"):
        _role_pages.append("Edit Role")

    if not _role_pages:
        from tabs.roles import render_roles_tab

        render_roles_tab()
    elif selected_sub is None or selected_sub not in _role_pages:
        st.session_state.selected_sub = _role_pages[0]
        st.rerun()
    elif selected_sub == "Role Management":
        from roles_admin import render_roles_management

        render_roles_management()
    elif selected_sub == "Create Role":
        from roles_admin import render_create_role

        render_create_role()
    elif selected_sub == "Manage Permissions":
        from roles_admin import render_manage_permissions

        render_manage_permissions()
    elif selected_sub == "Edit Role":
        from roles_admin import render_edit_role

        render_edit_role()
    else:
        from tabs.roles import render_roles_tab

        render_roles_tab()

elif selected_main == "📝 Action Logs":
    if selected_sub is None or selected_sub != "Log Report":
        st.session_state.selected_sub = "Log Report"
        st.rerun()
    from audit_logs import render_log_management

    render_log_management()

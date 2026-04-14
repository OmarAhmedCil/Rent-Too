# tab_roles.py — re-exports (implementation in roles_admin/)
from roles_admin import (
    ROLES_MAIN,
    ROLE_CREATE,
    ROLE_EDIT,
    ROLE_SUB_MGMT,
    render_assign_user_roles,
    render_create_role,
    render_edit_role,
    render_manage_permissions,
    render_role_management,
    render_roles_management,
    render_roles_tab,
)

__all__ = [
    "ROLES_MAIN",
    "ROLE_SUB_MGMT",
    "ROLE_CREATE",
    "ROLE_EDIT",
    "render_roles_management",
    "render_role_management",
    "render_create_role",
    "render_edit_role",
    "render_assign_user_roles",
    "render_manage_permissions",
    "render_roles_tab",
]

from .management import render_roles_management, ROLES_MAIN
from .role_management import (
    ROLE_CREATE,
    ROLE_EDIT,
    ROLE_SUB_MGMT,
    render_role_management,
)
from .create_role import render_create_role
from .edit_role import render_edit_role
from .assign_user_roles import render_assign_user_roles
from .manage_permissions import render_manage_permissions


def render_roles_tab():
    """Backward compatibility: open role management hub."""
    render_roles_management()


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

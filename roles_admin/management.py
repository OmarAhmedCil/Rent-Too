# Roles section main nav target; hub UI lives in role_management.
ROLES_MAIN = "\U0001f510 Roles"


def render_roles_management():
    from .role_management import render_role_management

    render_role_management()

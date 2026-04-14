from .management import render_user_management
from .create import render_create_user
from .edit import render_edit_user


def render_users_tab():
    """Backward compatibility: old tab UI ? management hub."""
    render_user_management()


__all__ = [
    "render_user_management",
    "render_create_user",
    "render_edit_user",
    "render_users_tab",
]

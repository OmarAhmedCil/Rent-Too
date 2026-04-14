from .management import render_distribution_management
from .generate_page import render_generate_distribution
from .regenerate_page import render_regenerate_distribution
from .edit_page import render_edit_distribution
from .delete_page import render_delete_distribution


def render_distribution_tab():
    """Backward compatibility: default tab was generate."""
    render_generate_distribution()


__all__ = [
    "render_distribution_management",
    "render_generate_distribution",
    "render_regenerate_distribution",
    "render_edit_distribution",
    "render_delete_distribution",
    "render_distribution_tab",
]

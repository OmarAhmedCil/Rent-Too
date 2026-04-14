# Project paths (cwd-independent).
import os


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def resolve_static_logo_path(basename: str = "logo") -> str | None:
    """First matching static/<basename>.(png|jpg|jpeg|svg), or None."""
    d = os.path.join(project_root(), "static")
    for ext in (".png", ".jpg", ".jpeg", ".svg"):
        p = os.path.join(d, basename + ext)
        if os.path.isfile(p):
            return p
    return None

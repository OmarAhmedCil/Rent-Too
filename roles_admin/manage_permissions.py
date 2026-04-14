import streamlit as st
from core.permissions import PERMISSIONS, require_permission, initialize_permissions


def render_manage_permissions():
    """Render the permissions catalogue (read-only) grouped by module."""
    require_permission('roles.view')

    st.header("Available Permissions")
    st.caption(
        "All permissions registered in the system. "
        "Assign them to roles on **Role management** → **Edit** (or when **Create role**)."
    )

    # Sync any new / updated permissions from code → DB
    if st.button("🔄 Sync permissions from code", key="sync_perms_btn"):
        if initialize_permissions():
            st.success("Permissions synced successfully.")
            st.rerun()
        else:
            st.error("Failed to sync permissions — check database connection.")

    st.markdown("---")

    # Build display from the in-code PERMISSIONS dict (always up-to-date)
    # Group by module prefix (part before the first '.')
    from collections import defaultdict
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, description in PERMISSIONS.items():
        module = key.split('.')[0]
        grouped[module].append((key, description))

    module_labels = {
        "dashboard":    "🏠 Dashboard",
        "contracts":    "📄 Contracts",
        "lessors":      "👥 Lessors",
        "assets":       "🏢 Assets",
        "stores":       "🏪 Stores",
        "services":     "🛠️ Services",
        "distribution": "📊 Distribution",
        "payments":     "💳 Payments",
        "download":     "📥 Download Data",
        "bulk_import":  "📤 Bulk Import",
        "email":        "📧 Email Notifications",
        "users":        "👤 Users",
        "roles":        "🔐 Roles & Permissions",
        "logs":         "📋 Action Logs",
        "admin":        "⚙️ Admin",
    }

    for module in sorted(grouped.keys()):
        label = module_labels.get(module, f"🔹 {module.title()}")
        perms = grouped[module]
        with st.expander(label, expanded=False):
            rows = [
                {"Permission key": k, "Description": d}
                for k, d in sorted(perms, key=lambda x: x[0])
            ]
            import pandas as pd
            st.table(pd.DataFrame(rows))

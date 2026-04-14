# Permissions catalog UI for a single role (create / edit flows).
import time
import streamlit as st
import pandas as pd
from core.utils import load_all
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import has_permission


def _perm_label_row(row: pd.Series) -> str:
    pn = str(row.get("permission_name", "") or "").strip()
    desc = str(row.get("description", "") or "").strip()
    if pn and desc:
        return f"{pn}: {desc}"
    return pn or desc or "—"


def render_permissions_section_for_role(
    role_id: str,
    role_display_name: str,
    *,
    key_prefix: str,
) -> None:
    """List assigned permissions, remove, multiselect add — requires roles.edit (catalog edit)."""
    if not has_permission("roles.edit"):
        return

    load_all()
    permissions_df = st.session_state.permissions_df.copy()
    role_permissions_df = st.session_state.role_permissions_df.copy()
    rid = str(role_id)

    st.markdown("### Permissions")
    if permissions_df.empty:
        st.info("No permissions in the catalog yet.")
        return

    current_pids = (
        role_permissions_df[role_permissions_df["role_id"].astype(str) == rid][
            "permission_id"
        ]
        .astype(str)
        .tolist()
    )

    if current_pids:
        for pid in current_pids:
            pr = permissions_df[permissions_df["id"].astype(str) == str(pid)]
            if pr.empty:
                continue
            perm = pr.iloc[0]
            col1, col2 = st.columns([6, 1])
            with col1:
                st.write(f"• {_perm_label_row(perm)}")
            with col2:
                if st.button(
                    "Remove",
                    key=f"{key_prefix}_prm_rm_{rid}_{pid}",
                    use_container_width=True,
                ):
                    if delete_role_permission(rid, pid):
                        cur = get_current_user()
                        log_action(
                            user_id=cur["id"] if cur else None,
                            user_name=cur["name"] if cur else "System",
                            action_type="edit",
                            entity_type="role",
                            entity_id=rid,
                            entity_name=role_display_name,
                            action_details=f"Removed permission {perm.get('permission_name', pid)} from role",
                            ip_address=get_user_ip(),
                        )
                        st.success("Permission removed.")
                        load_all()
                        time.sleep(0.35)
                        st.rerun()
                    else:
                        st.error("Could not remove permission.")
    else:
        st.info("No permissions assigned to this role yet.")

    available = permissions_df[~permissions_df["id"].astype(str).isin(current_pids)]
    if available.empty:
        st.caption("All catalog permissions are already assigned.")
        return

    labels: list[str] = []
    id_by_label: dict[str, str] = {}
    for _, p in available.iterrows():
        lbl = _perm_label_row(p)
        if lbl in id_by_label:
            lbl = f"{lbl} [{p['id']}]"
        labels.append(lbl)
        id_by_label[lbl] = str(p["id"])

    st.markdown("**Add permissions**")
    sel = st.multiselect(
        "Select permissions to add",
        options=sorted(labels),
        key=f"{key_prefix}_prm_add_ms_{rid}",
        label_visibility="collapsed",
    )
    if sel and st.button("Add selected", key=f"{key_prefix}_prm_add_btn_{rid}"):
        pids = [id_by_label[x] for x in sel if x in id_by_label]
        if not pids:
            st.error("Nothing to add.")
        elif insert_role_permissions_bulk(rid, pids):
            cur = get_current_user()
            names = []
            for pid in pids:
                m = permissions_df[permissions_df["id"].astype(str) == str(pid)]
                if not m.empty:
                    names.append(str(m.iloc[0].get("permission_name", pid)))
            log_action(
                user_id=cur["id"] if cur else None,
                user_name=cur["name"] if cur else "System",
                action_type="edit",
                entity_type="role",
                entity_id=rid,
                entity_name=role_display_name,
                action_details=f"Added permissions to role: {', '.join(names)}",
                ip_address=get_user_ip(),
            )
            st.success(f"Added {len(pids)} permission(s).")
            load_all()
            time.sleep(0.35)
            st.rerun()
        else:
            st.error("Failed to add permissions.")

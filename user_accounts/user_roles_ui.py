# Shared role assignment UI for create / edit user flows.
import time
import streamlit as st
import pandas as pd
from core.utils import load_all
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import has_permission


def role_name_to_id_map(roles_df: pd.DataFrame) -> dict[str, str]:
    if roles_df is None or roles_df.empty:
        return {}
    out: dict[str, str] = {}
    for _, r in roles_df.iterrows():
        nm = str(r.get("role_name", "") or "").strip()
        if nm:
            out[nm] = str(r["id"])
    return out


def apply_role_assignments_after_create(user_id: str, role_ids: list[str], user_name: str, email_hint: str) -> None:
    """Insert user_roles for a newly created user; log once per success."""
    if not role_ids:
        return
    cur = get_current_user()
    for rid in role_ids:
        rid = str(rid).strip()
        if not rid:
            continue
        if insert_user_role(str(user_id), rid):
            roles_df = st.session_state.get("roles_df", pd.DataFrame(columns=ROLES_COLS))
            rn = "—"
            if not roles_df.empty:
                m = roles_df[roles_df["id"].astype(str) == rid]
                if not m.empty:
                    rn = str(m.iloc[0].get("role_name", rid))
            log_action(
                user_id=cur["id"] if cur else None,
                user_name=cur["name"] if cur else "System",
                action_type="edit",
                entity_type="user_role",
                entity_id=str(user_id),
                entity_name=user_name,
                action_details=f"Assigned role {rn} to new user ({email_hint})",
                ip_address=get_user_ip(),
            )


def render_roles_section_for_user(
    user_id: str,
    user_display_name: str,
    *,
    key_prefix: str,
) -> None:
    """List assigned roles, remove, assign new — same behavior as old hub page."""
    if not has_permission("roles.assign"):
        return

    load_all()
    roles_df = st.session_state.get("roles_df", pd.DataFrame(columns=ROLES_COLS)).copy()
    user_roles_df = st.session_state.get(
        "user_roles_df", pd.DataFrame(columns=USER_ROLES_COLS)
    ).copy()

    uid = str(user_id)
    st.markdown("### Roles")
    if roles_df.empty:
        st.info("No roles defined yet. Create roles under **Roles → Manage roles**.")
        return

    current_role_ids = (
        user_roles_df[user_roles_df["user_id"].astype(str) == uid]["role_id"].astype(str).tolist()
    )

    st.caption("Roles control what this user can access.")
    if current_role_ids:
        for rid in current_role_ids:
            role_row = roles_df[roles_df["id"].astype(str) == str(rid)]
            if role_row.empty:
                continue
            rname = str(role_row.iloc[0].get("role_name", ""))
            col1, col2 = st.columns([6, 1])
            with col1:
                st.write(f"• {rname}")
            with col2:
                if st.button(
                    "Remove",
                    key=f"{key_prefix}_rm_{uid}_{rid}",
                    use_container_width=True,
                ):
                    if delete_user_role(uid, rid):
                        cur = get_current_user()
                        log_action(
                            user_id=cur["id"] if cur else None,
                            user_name=cur["name"] if cur else "System",
                            action_type="edit",
                            entity_type="user_role",
                            entity_id=uid,
                            entity_name=user_display_name,
                            action_details=f"Removed role {rname} from user",
                            ip_address=get_user_ip(),
                        )
                        st.success("Role removed.")
                        load_all()
                        time.sleep(0.35)
                        st.rerun()
                    else:
                        st.error("Could not remove role.")
    else:
        st.info("No roles assigned yet.")

    available = roles_df[~roles_df["id"].astype(str).isin(current_role_ids)]
    if available.empty:
        st.caption("All roles are already assigned.")
        return

    opts = [""] + available["role_name"].astype(str).tolist()
    sel = st.selectbox(
        "Add role",
        options=opts,
        key=f"{key_prefix}_add_sel_{uid}",
    )
    if sel and st.button("Assign role", key=f"{key_prefix}_add_btn_{uid}"):
        role_row = roles_df[roles_df["role_name"] == sel]
        if role_row.empty:
            st.error("Invalid role.")
        elif insert_user_role(uid, str(role_row.iloc[0]["id"])):
            cur = get_current_user()
            log_action(
                user_id=cur["id"] if cur else None,
                user_name=cur["name"] if cur else "System",
                action_type="edit",
                entity_type="user_role",
                entity_id=uid,
                entity_name=user_display_name,
                action_details=f"Assigned role {sel} to user",
                ip_address=get_user_ip(),
            )
            st.success(f"Role **{sel}** assigned.")
            load_all()
            time.sleep(0.35)
            st.rerun()
        else:
            st.error("Failed to assign role.")

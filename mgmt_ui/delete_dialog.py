# Modal-style delete confirmations for management hubs (Streamlit st.dialog + fallback).
import streamlit as st
from core.utils import load_all
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
def _dialog(title: str):
    """Return st.dialog decorator, or None if unavailable. Uses small width (~500px max)."""
    if not hasattr(st, "dialog"):
        return None
    try:
        return st.dialog(title, width="small")
    except TypeError:
        return st.dialog(title)


MGMT_SUCCESS_FLASH = "_mgmt_flash_success"


def show_mgmt_success_flash() -> None:
    msg = st.session_state.pop(MGMT_SUCCESS_FLASH, None)
    if msg:
        st.success(msg)


def _open_or_fallback(title: str, body_fn):
    """Run body_fn inside a dialog, or in a bordered container if dialogs are not supported."""
    dec = _dialog(title)
    if dec is not None:

        def _dlg():
            body_fn()

        dec(_dlg)()
    else:
        # Narrow centered panel when st.dialog is not available
        _c1, _c2, _c3 = st.columns([2, 1.35, 2])
        with _c2:
            try:
                with st.container(border=True):
                    st.markdown(f"### {title}")
                    body_fn()
            except TypeError:
                st.warning(f"### {title}")
                body_fn()


def render_contract_delete_dialog_if_pending() -> None:
    pending = st.session_state.get("contracts_mgmt_pending_delete")
    if pending is None or str(pending).strip() == "":
        return
    pid = str(pending).strip()
    load_all()
    cdf = st.session_state.contracts_df.copy()
    m = cdf[cdf["id"].astype(str) == pid]
    if m.empty:
        st.session_state.pop("contracts_mgmt_pending_delete", None)
        return
    prow = m.iloc[0]
    nm = str(prow.get("contract_name", ""))

    def body():
        st.markdown("**Delete this contract?** This cannot be undone.")
        st.write(f"**Contract:** {nm}")
        st.write(f"**ID:** `{pid}`")
        st.write(f"**Type:** {prow.get('contract_type', '') or '—'}")
        st.write(f"**Asset / store:** {prow.get('asset_or_store_name', '') or '—'}")
        st.caption("Related distribution data and links will be removed.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Yes, delete",
                type="primary",
                use_container_width=True,
                key=f"dlg_ctr_y_{pid}",
            ):
                if delete_contract(pid):
                    u = get_current_user()
                    log_action(
                        user_id=u["id"] if u else None,
                        user_name=u["name"] if u else "System",
                        action_type="delete",
                        entity_type="contract",
                        entity_id=pid,
                        entity_name=nm,
                        action_details=f"Deleted contract: {nm}",
                        ip_address=get_user_ip(),
                    )
                    st.session_state.pop("contracts_mgmt_pending_delete", None)
                    load_all()
                    st.session_state[MGMT_SUCCESS_FLASH] = "Contract deleted."
                    st.rerun()
                else:
                    st.error("Delete failed.")
        with c2:
            if st.button(
                "Cancel",
                use_container_width=True,
                key=f"dlg_ctr_n_{pid}",
            ):
                st.session_state.pop("contracts_mgmt_pending_delete", None)
                st.rerun()

    _open_or_fallback("Confirm deletion", body)


def render_lessor_delete_dialog_if_pending() -> None:
    pending = st.session_state.get("lessors_mgmt_pending_delete")
    if pending is None or str(pending).strip() == "":
        return
    pid = str(pending).strip()
    load_all()
    df = st.session_state.lessors_df.copy()
    m = df[df["id"].astype(str) == pid]
    if m.empty:
        st.session_state.pop("lessors_mgmt_pending_delete", None)
        return
    prow = m.iloc[0]
    nm = str(prow.get("name", ""))

    def body():
        st.markdown("**Delete this lessor?**")
        st.write(f"**Name:** {nm}")
        st.write(f"**ID:** `{pid}`")
        st.caption("Related withholding period rows are removed.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Yes, delete",
                type="primary",
                use_container_width=True,
                key=f"dlg_lss_y_{pid}",
            ):
                if delete_lessor(pid):
                    u = get_current_user()
                    log_action(
                        user_id=u["id"] if u else None,
                        user_name=u["name"] if u else "System",
                        action_type="delete",
                        entity_type="lessor",
                        entity_id=pid,
                        entity_name=nm,
                        action_details=f"Deleted lessor: {nm}",
                        ip_address=get_user_ip(),
                    )
                    st.session_state.pop("lessors_mgmt_pending_delete", None)
                    load_all()
                    st.session_state[MGMT_SUCCESS_FLASH] = "Lessor deleted."
                    st.rerun()
                else:
                    st.error("Delete failed.")
        with c2:
            if st.button(
                "Cancel",
                use_container_width=True,
                key=f"dlg_lss_n_{pid}",
            ):
                st.session_state.pop("lessors_mgmt_pending_delete", None)
                st.rerun()

    _open_or_fallback("Confirm deletion", body)


def render_asset_delete_dialog_if_pending() -> None:
    pending = st.session_state.get("assets_mgmt_pending_delete")
    if pending is None or str(pending).strip() == "":
        return
    pid = str(pending).strip()
    load_all()
    df = st.session_state.assets_df.copy()
    m = df[df["id"].astype(str) == pid]
    if m.empty:
        st.session_state.pop("assets_mgmt_pending_delete", None)
        return
    prow = m.iloc[0]
    nm = str(prow.get("name", ""))

    def body():
        st.markdown("**Delete this asset?**")
        st.write(f"**Name:** {nm}")
        st.write(f"**ID:** `{pid}`")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Yes, delete",
                type="primary",
                use_container_width=True,
                key=f"dlg_ast_y_{pid}",
            ):
                if delete_asset(pid):
                    u = get_current_user()
                    log_action(
                        user_id=u["id"] if u else None,
                        user_name=u["name"] if u else "System",
                        action_type="delete",
                        entity_type="asset",
                        entity_id=pid,
                        entity_name=nm,
                        action_details=f"Deleted asset: {nm}",
                        ip_address=get_user_ip(),
                    )
                    st.session_state.pop("assets_mgmt_pending_delete", None)
                    load_all()
                    st.session_state[MGMT_SUCCESS_FLASH] = "Asset deleted."
                    st.rerun()
                else:
                    st.error("Delete failed.")
        with c2:
            if st.button(
                "Cancel",
                use_container_width=True,
                key=f"dlg_ast_n_{pid}",
            ):
                st.session_state.pop("assets_mgmt_pending_delete", None)
                st.rerun()

    _open_or_fallback("Confirm deletion", body)


def render_service_delete_dialog_if_pending() -> None:
    pending = st.session_state.get("services_mgmt_pending_delete")
    if pending is None or str(pending).strip() == "":
        return
    pid = str(pending).strip()
    load_all()
    df = st.session_state.services_df.copy()
    m = df[df["id"].astype(str) == pid]
    if m.empty:
        st.session_state.pop("services_mgmt_pending_delete", None)
        return
    prow = m.iloc[0]
    nm = str(prow.get("name", ""))

    def body():
        st.markdown("**Delete this service?**")
        st.write(f"**Name:** {nm}")
        st.write(f"**ID:** `{pid}`")
        st.caption("Contract–service links are removed.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Yes, delete",
                type="primary",
                use_container_width=True,
                key=f"dlg_svc_y_{pid}",
            ):
                if delete_service(pid):
                    u = get_current_user()
                    log_action(
                        user_id=u["id"] if u else None,
                        user_name=u["name"] if u else "System",
                        action_type="delete",
                        entity_type="service",
                        entity_id=pid,
                        entity_name=nm,
                        action_details=f"Deleted service: {nm}",
                        ip_address=get_user_ip(),
                    )
                    st.session_state.pop("services_mgmt_pending_delete", None)
                    load_all()
                    st.rerun()
                else:
                    st.error("Delete failed.")
        with c2:
            if st.button(
                "Cancel",
                use_container_width=True,
                key=f"dlg_svc_n_{pid}",
            ):
                st.session_state.pop("services_mgmt_pending_delete", None)
                st.rerun()

    _open_or_fallback("Confirm deletion", body)


def render_user_delete_dialog_if_pending() -> None:
    pending = st.session_state.get("users_mgmt_pending_delete")
    if pending is None or str(pending).strip() == "":
        return
    pid = str(pending).strip()
    load_all()
    df = st.session_state.users_df.copy()
    m = df[df["id"].astype(str) == pid]
    if m.empty:
        st.session_state.pop("users_mgmt_pending_delete", None)
        return
    prow = m.iloc[0]
    nm = str(prow.get("name", ""))
    em = str(prow.get("email", ""))
    cur = get_current_user()

    def body():
        if cur and str(prow["id"]) == str(cur["id"]):
            st.error("You cannot delete your own account.")
            if st.button(
                "Close",
                use_container_width=True,
                key=f"dlg_usr_self_{pid}",
            ):
                st.session_state.pop("users_mgmt_pending_delete", None)
                st.rerun()
            return
        st.markdown("**Delete this user?**")
        st.write(f"**Name:** {nm}")
        st.write(f"**Email:** {em}")
        st.caption("Role assignments for this user will be removed.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Yes, delete",
                type="primary",
                use_container_width=True,
                key=f"dlg_usr_y_{pid}",
            ):
                if delete_user(pid):
                    log_action(
                        user_id=cur["id"] if cur else None,
                        user_name=cur["name"] if cur else "System",
                        action_type="delete",
                        entity_type="user",
                        entity_id=pid,
                        entity_name=nm,
                        action_details=f"Deleted user: {em}",
                        ip_address=get_user_ip(),
                    )
                    st.session_state.pop("users_mgmt_pending_delete", None)
                    load_all()
                    st.session_state[MGMT_SUCCESS_FLASH] = "User deleted."
                    st.rerun()
                else:
                    st.error("Delete failed.")
        with c2:
            if st.button(
                "Cancel",
                use_container_width=True,
                key=f"dlg_usr_n_{pid}",
            ):
                st.session_state.pop("users_mgmt_pending_delete", None)
                st.rerun()

    _open_or_fallback("Confirm deletion", body)


def render_role_delete_dialog_if_pending() -> None:
    pending = st.session_state.get("roles_mgmt_pending_delete")
    if pending is None or str(pending).strip() == "":
        return
    pid = str(pending).strip()
    load_all()
    df = st.session_state.roles_df.copy()
    m = df[df["id"].astype(str) == pid]
    if m.empty:
        st.session_state.pop("roles_mgmt_pending_delete", None)
        return
    prow = m.iloc[0]
    nm = str(prow.get("role_name", ""))

    def body():
        st.markdown("**Delete this role?**")
        st.write(f"**Name:** {nm}")
        st.write(f"**ID:** `{pid}`")
        st.caption("User–role and role–permission links for this role will be removed.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Yes, delete",
                type="primary",
                use_container_width=True,
                key=f"dlg_rle_y_{pid}",
            ):
                if delete_role(pid):
                    u = get_current_user()
                    log_action(
                        user_id=u["id"] if u else None,
                        user_name=u["name"] if u else "System",
                        action_type="delete",
                        entity_type="role",
                        entity_id=pid,
                        entity_name=nm,
                        action_details=f"Deleted role: {nm}",
                        ip_address=get_user_ip(),
                    )
                    st.session_state.pop("roles_mgmt_pending_delete", None)
                    load_all()
                    st.session_state[MGMT_SUCCESS_FLASH] = "Role deleted."
                    st.rerun()
                else:
                    st.error("Delete failed.")
        with c2:
            if st.button(
                "Cancel",
                use_container_width=True,
                key=f"dlg_rle_n_{pid}",
            ):
                st.session_state.pop("roles_mgmt_pending_delete", None)
                st.rerun()

    _open_or_fallback("Confirm deletion", body)


def render_email_delete_dialog_if_pending() -> None:
    """Confirm deletion of an email schedule (Notifications Center hub)."""
    from core.db import get_email_schedules, delete_email_schedule

    pending = st.session_state.get("email_mgmt_pending_delete")
    if pending is None or str(pending).strip() == "":
        return
    sid = str(pending).strip()
    schedules = get_email_schedules() or []
    sch = next((s for s in schedules if str(s.get("id")) == sid), None)
    if sch is None:
        st.session_state.pop("email_mgmt_pending_delete", None)
        return
    nm = str(sch.get("name", "") or "")
    stype = str(sch.get("schedule_type", "") or "")
    type_label = {"weekly_payment": "Weekly Payment", "contract_reminder": "Contract Reminder"}.get(
        stype, stype or "—"
    )

    def body():
        st.markdown("**Delete this email notification?** This cannot be undone.")
        st.write(f"**Name:** {nm}")
        st.write(f"**Type:** {type_label}")
        st.caption("Scheduled sends for this configuration will stop.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Yes, delete",
                type="primary",
                use_container_width=True,
                key=f"dlg_email_y_{sid}",
            ):
                if delete_email_schedule(sid):
                    u = get_current_user()
                    log_action(
                        user_id=u["id"] if u else None,
                        user_name=u["name"] if u else "System",
                        action_type="delete",
                        entity_type="email_schedule",
                        entity_id=sid,
                        entity_name=nm,
                        action_details=f"Deleted email schedule: {stype}",
                        ip_address=get_user_ip(),
                    )
                    st.session_state.pop("email_mgmt_pending_delete", None)
                    st.session_state[MGMT_SUCCESS_FLASH] = "Email notification deleted."
                    st.rerun()
                else:
                    st.error("Delete failed.")
        with c2:
            if st.button(
                "Cancel",
                use_container_width=True,
                key=f"dlg_email_n_{sid}",
            ):
                st.session_state.pop("email_mgmt_pending_delete", None)
                st.rerun()

    _open_or_fallback("Confirm deletion", body)

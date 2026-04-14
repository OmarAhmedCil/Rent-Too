# Confirm delete distribution from Distribution management hub (per contract).
import time

import streamlit as st

from core.utils import load_all

from .run_workflow import execute_delete_all_distribution_for_contract


def _dialog(title: str):
    if not hasattr(st, "dialog"):
        return None
    try:
        return st.dialog(title, width="medium")
    except TypeError:
        return st.dialog(title)


def _open_or_fallback(title: str, body_fn):
    dec = _dialog(title)
    if dec is not None:

        def _dlg():
            body_fn()

        dec(_dlg)()
    else:
        _c1, _c2, _c3 = st.columns([1, 3.2, 1])
        with _c2:
            try:
                with st.container(border=True):
                    st.markdown(f"### {title}")
                    body_fn()
            except TypeError:
                st.warning(f"### {title}")
                body_fn()


def render_distribution_delete_dialog_if_pending() -> None:
    pending = st.session_state.get("dist_mgmt_pending_delete")
    if pending is None or str(pending).strip() == "":
        return
    pid = str(pending).strip()
    load_all()
    cdf = st.session_state.contracts_df.copy()
    m = cdf[cdf["id"].astype(str) == pid]
    if m.empty:
        st.session_state.pop("dist_mgmt_pending_delete", None)
        return
    row = m.iloc[0]
    nm = str(row.get("contract_name", ""))
    ct = str(row.get("contract_type", "") or "")

    def body():
        st.markdown("**Delete all distribution for this contract?**")
        st.write(f"**Contract:** {nm}")
        st.write(f"**Type:** {ct or '—'}")
        st.caption("Removes contract distribution, service distribution, and related payments (per system rules).")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Yes, delete", type="primary", use_container_width=True, key=f"dist_dlg_y_{pid}"):
                ok, msg = execute_delete_all_distribution_for_contract(row)
                st.session_state.pop("dist_mgmt_pending_delete", None)
                load_all()
                if ok:
                    st.success(msg)
                    time.sleep(0.6)
                    st.rerun()
                else:
                    st.error(msg)
        with c2:
            if st.button("Cancel", use_container_width=True, key=f"dist_dlg_n_{pid}"):
                st.session_state.pop("dist_mgmt_pending_delete", None)
                st.rerun()

    _open_or_fallback("Confirm delete distribution", body)

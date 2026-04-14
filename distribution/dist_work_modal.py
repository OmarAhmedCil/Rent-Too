# Generate/Regenerate: single-contract modal with spinner, result, auto-close.
import html
import time
from datetime import timedelta

import streamlit as st

from core.utils import load_all

from .run_workflow import execute_generate_distribution, execute_regenerate_distribution

DIST_MGMT_WORK_MODAL_KEY = "dist_mgmt_work_modal"
_AUTO_CLOSE_SECONDS = 5.0


def _dialog(title: str):
    if not hasattr(st, "dialog"):
        return None
    try:
        return st.dialog(title, width="medium")
    except TypeError:
        return st.dialog(title)


def _open_work_modal(title: str, body_fn):
    dec = _dialog(title)
    if dec is not None:

        def _dlg():
            body_fn()

        dec(_dlg)()
    else:
        _c1, _c2, _c3 = st.columns([1.5, 2.2, 1.5])
        with _c2:
            try:
                with st.container(border=True):
                    st.markdown(f"### {html.escape(title)}")
                    body_fn()
            except TypeError:
                st.warning(f"### {title}")
                body_fn()


def _work_modal_body() -> None:
    m = st.session_state.get(DIST_MGMT_WORK_MODAL_KEY)
    if not m:
        return

    if m.get("phase") == "pending":
        load_all()
        cdf = st.session_state.contracts_df.copy()
        cid = str(m.get("contract_id") or "")
        op = m.get("op")
        match = cdf[cdf["id"].astype(str) == cid]
        if match.empty:
            st.error("Contract not found. It may have been removed.")
            st.session_state.pop(DIST_MGMT_WORK_MODAL_KEY, None)
            return
        row = match.iloc[0]
        label = (
            "Generating distribution…"
            if op == "generate"
            else "Regenerating distribution…"
        )
        with st.spinner(label):
            if op == "generate":
                res = execute_generate_distribution(row)
            else:
                res = execute_regenerate_distribution(row)
        st.session_state[DIST_MGMT_WORK_MODAL_KEY] = {
            "phase": "done",
            "op": op,
            "contract_id": cid,
            "result": res,
            "close_at": time.time() + _AUTO_CLOSE_SECONDS,
        }
        st.rerun()
        return

    r = m.get("result") or {}
    cn = str(r.get("contract_name") or "").strip()
    if cn:
        st.markdown(f"**Contract:** {html.escape(cn)}")

    if r.get("ok"):
        st.success("Completed successfully.")
        for line in r.get("lines") or []:
            st.markdown(f"- {html.escape(str(line))}")
    else:
        st.error("Operation failed.")
        if r.get("error"):
            st.caption(str(r["error"]))

    st.caption(
        f"This window will close automatically in **{_AUTO_CLOSE_SECONDS:.0f}** seconds."
    )


@st.fragment(run_every=timedelta(seconds=1))
def _dist_work_modal_auto_close_fragment() -> None:
    m = st.session_state.get(DIST_MGMT_WORK_MODAL_KEY)
    if not m or m.get("phase") != "done":
        return
    if time.time() >= float(m.get("close_at") or 0):
        st.session_state.pop(DIST_MGMT_WORK_MODAL_KEY, None)
        st.rerun()


def render_distribution_work_modal() -> None:
    """Register auto-close timer; open modal when a row Generate/Regenerate is pending or showing result."""
    _dist_work_modal_auto_close_fragment()

    m = st.session_state.get(DIST_MGMT_WORK_MODAL_KEY)
    if not m:
        return

    _open_work_modal("Distribution", _work_modal_body)


def start_distribution_work_modal(*, op: str, contract_id: str) -> None:
    """Called from row button: op is 'generate' or 'regenerate'."""
    st.session_state[DIST_MGMT_WORK_MODAL_KEY] = {
        "phase": "pending",
        "op": op,
        "contract_id": str(contract_id),
    }

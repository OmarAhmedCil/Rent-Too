# Bulk distribution actions: scope (all / ROU / Fixed / Revenue Share) + generate / regenerate / delete in one dialog.
import html

import streamlit as st

from conf.constants import SERVICE_DISTRIBUTION_COLS, SERVICE_DISTRIBUTION_TABLE
from core.permissions import has_permission
from core.utils import check_distribution_exists, load_all, load_df

from .run_workflow import (
    execute_delete_all_distribution_for_contract,
    execute_generate_distribution,
    execute_regenerate_distribution,
)

DIST_BULK_UI_KEY = "dist_bulk_ui"

_SCOPE_OPTIONS: list[tuple[str, str]] = [
    ("all", "All contracts"),
    ("rou", "All ROU"),
    ("fixed", "All Fixed"),
    ("revenue_share", "All Revenue Share"),
]

_ACTION_LABELS = {
    "generate": "Generate",
    "regenerate": "Regenerate",
    "delete": "Delete distribution",
}


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
        _c1, _c2, _c3 = st.columns([1.4, 1.6, 1.4])
        with _c2:
            try:
                with st.container(border=True):
                    st.markdown(f"### {html.escape(title)}")
                    body_fn()
            except TypeError:
                st.warning(f"### {title}")
                body_fn()


def _contracts_for_scope(contracts_df, scope_key: str):
    if contracts_df.empty:
        return contracts_df
    if scope_key == "all":
        return contracts_df
    if scope_key == "rou":
        return contracts_df[contracts_df["contract_type"] == "ROU"]
    if scope_key == "fixed":
        return contracts_df[contracts_df["contract_type"] == "Fixed"]
    if scope_key == "revenue_share":
        return contracts_df[contracts_df["contract_type"] == "Revenue Share"]
    return contracts_df


def _has_service_distribution_for_contract(contract_id) -> bool:
    df = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
    if df.empty:
        return False
    cid = str(contract_id)
    return (df["contract_id"].astype(str) == cid).any()


def _has_any_distribution(row) -> bool:
    cid = row["id"]
    ct = row.get("contract_type", "") or ""
    if check_distribution_exists(cid, ct):
        return True
    return _has_service_distribution_for_contract(cid)


def _eligible_ids(sub_df, action: str) -> tuple[list[str], int]:
    """Return (contract_ids_to_process, skipped_ineligible_count)."""
    ids: list[str] = []
    skipped = 0
    for _, row in sub_df.iterrows():
        cid = str(row["id"])
        ct = row.get("contract_type", "") or ""
        has_c = check_distribution_exists(row["id"], ct)
        if action == "generate":
            if has_c:
                skipped += 1
            else:
                ids.append(cid)
        elif action == "regenerate":
            if not has_c:
                skipped += 1
            else:
                ids.append(cid)
        else:  # delete
            if not _has_any_distribution(row):
                skipped += 1
            else:
                ids.append(cid)
    return ids, skipped


def _run_bulk(action: str, contract_ids: list[str]) -> list[dict]:
    results: list[dict] = []
    for cid in contract_ids:
        load_all()
        cdf = st.session_state.contracts_df.copy()
        m = cdf[cdf["id"].astype(str) == str(cid)]
        if m.empty:
            results.append(
                {
                    "contract_id": cid,
                    "contract_name": "",
                    "ok": False,
                    "error": "Contract not found.",
                }
            )
            continue
        row = m.iloc[0]
        nm = str(row.get("contract_name", "") or "")
        if action == "generate":
            res = execute_generate_distribution(row)
            results.append(
                {
                    "contract_id": cid,
                    "contract_name": nm or res.get("contract_name", ""),
                    "ok": bool(res.get("ok")),
                    "error": str(res.get("error") or ""),
                }
            )
        elif action == "regenerate":
            res = execute_regenerate_distribution(row)
            results.append(
                {
                    "contract_id": cid,
                    "contract_name": nm or res.get("contract_name", ""),
                    "ok": bool(res.get("ok")),
                    "error": str(res.get("error") or ""),
                }
            )
        else:
            ok, msg = execute_delete_all_distribution_for_contract(row)
            err = "" if ok else str(msg)
            if not ok and "No distribution data" in msg:
                results.append(
                    {
                        "contract_id": cid,
                        "contract_name": nm,
                        "ok": False,
                        "error": err,
                        "skip": True,
                    }
                )
            else:
                results.append(
                    {
                        "contract_id": cid,
                        "contract_name": nm,
                        "ok": ok,
                        "error": err,
                        "skip": False,
                    }
                )
    return results


def open_distribution_bulk_action_dialog() -> None:
    st.session_state[DIST_BULK_UI_KEY] = {
        "open": True,
        "stage": "pick",
    }


def render_distribution_bulk_action_dialog() -> None:
    ui = st.session_state.get(DIST_BULK_UI_KEY)
    if not ui or not ui.get("open"):
        return

    def body():
        stage = ui.get("stage", "pick")

        if stage == "pick":
            st.markdown("Choose a **group**, an **action**, then run. Loading and results stay in this window.")
            scope_keys = [k for k, _ in _SCOPE_OPTIONS]
            scope_labels = [lbl for _, lbl in _SCOPE_OPTIONS]
            ix = 0
            cur = ui.get("scope_key")
            if cur in scope_keys:
                ix = scope_keys.index(cur)
            choice = st.selectbox(
                "Apply to",
                options=scope_labels,
                index=ix,
                key="dist_bulk_scope_select",
            )
            scope_key = scope_keys[scope_labels.index(choice)]

            action_options: list[str] = []
            if has_permission("distribution.generate"):
                action_options.append("generate")
            if has_permission("distribution.regenerate"):
                action_options.append("regenerate")
            if has_permission("distribution.delete"):
                action_options.append("delete")

            if not action_options:
                st.warning("You do not have permission for bulk distribution actions.")
                if st.button("Close", key="dist_bulk_close_noperm"):
                    st.session_state.pop(DIST_BULK_UI_KEY, None)
                    st.rerun()
                return

            default_action = ui.get("action") if ui.get("action") in action_options else action_options[0]
            action_idx = action_options.index(default_action)
            action = st.radio(
                "Action",
                options=action_options,
                format_func=lambda a: _ACTION_LABELS.get(a, a),
                index=action_idx,
                key="dist_bulk_action_radio",
                horizontal=True,
            )

            load_all()
            cdf = st.session_state.contracts_df.copy()
            sub = _contracts_for_scope(cdf, scope_key)
            st.caption(f"**{len(sub)}** contract(s) in this group (before eligibility for the action).")

            if st.button("Run bulk action", type="primary", key="dist_bulk_run"):
                if sub.empty:
                    st.warning("No contracts in this group.")
                else:
                    ids, skipped_pre = _eligible_ids(sub, action)
                    if not ids:
                        st.session_state[DIST_BULK_UI_KEY] = {
                            "open": True,
                            "stage": "done",
                            "scope_key": scope_key,
                            "group_label": choice,
                            "action": action,
                            "results": [],
                            "skipped_ineligible": skipped_pre,
                            "skipped_note": "No contracts were eligible for this action.",
                        }
                        st.rerun()
                    else:
                        st.session_state[DIST_BULK_UI_KEY] = {
                            "open": True,
                            "stage": "work",
                            "scope_key": scope_key,
                            "group_label": choice,
                            "action": action,
                            "ids": ids,
                            "skipped_ineligible": skipped_pre,
                        }
                        st.rerun()

            if st.button("Close", key="dist_bulk_close_pick"):
                st.session_state.pop(DIST_BULK_UI_KEY, None)
                st.rerun()
            return

        if stage == "work":
            action = str(ui.get("action") or "generate")
            ids = list(ui.get("ids") or [])
            group_label = str(ui.get("group_label") or "")
            verb = {
                "generate": "Generating distribution…",
                "regenerate": "Regenerating distribution…",
                "delete": "Deleting distribution data…",
            }.get(action, "Working…")
            with st.spinner(f"{verb} ({len(ids)} contract(s))"):
                results = _run_bulk(action, ids)
            st.session_state[DIST_BULK_UI_KEY] = {
                "open": True,
                "stage": "done",
                "scope_key": ui.get("scope_key"),
                "group_label": group_label,
                "action": action,
                "results": results,
                "skipped_ineligible": int(ui.get("skipped_ineligible") or 0),
            }
            st.rerun()
            return

        # stage == "done"
        group_label = str(ui.get("group_label") or "—")
        action = str(ui.get("action") or "")
        action_disp = _ACTION_LABELS.get(action, action)
        results = list(ui.get("results") or [])
        skipped_ineligible = int(ui.get("skipped_ineligible") or 0)
        skipped_note = str(ui.get("skipped_note") or "")

        if skipped_note:
            st.markdown(
                f"**Action:** {html.escape(action_disp)}  \n"
                f"**Group:** {html.escape(group_label)}"
            )
            st.info(skipped_note)
            if st.button("Close", key="dist_bulk_close_done_empty"):
                st.session_state.pop(DIST_BULK_UI_KEY, None)
                st.rerun()
            return

        ok_n = sum(1 for r in results if r.get("ok"))
        fail_n = sum(
            1 for r in results if not r.get("ok") and not r.get("skip")
        )
        skip_n = sum(1 for r in results if r.get("skip"))
        affected = ok_n

        st.markdown(
            f"**Action:** {html.escape(action_disp)}  \n"
            f"**Group:** {html.escape(group_label)}  \n"
            f"**Contracts affected (success):** {affected}"
        )
        if skipped_ineligible:
            st.caption(
                f"{skipped_ineligible} contract(s) in the group were skipped (not eligible for this action)."
            )

        if fail_n == 0 and skip_n == 0:
            st.success(
                f"Completed successfully for **{affected}** contract(s)."
            )
        elif ok_n == 0 and fail_n > 0:
            st.error(
                f"No successful runs. **{fail_n}** contract(s) failed."
            )
        elif fail_n or skip_n:
            st.warning(
                f"**{ok_n}** succeeded, **{fail_n}** failed"
                + (f", **{skip_n}** skipped" if skip_n else "")
                + "."
            )

        errors_list = [
            r
            for r in results
            if not r.get("ok") and not r.get("skip") and r.get("error")
        ]
        if errors_list:
            with st.expander("Errors", expanded=len(errors_list) <= 8):
                for r in errors_list:
                    nm = str(r.get("contract_name") or "").strip() or r.get(
                        "contract_id", "—"
                    )
                    err = str(r.get("error") or "Unknown error.")
                    st.markdown(
                        f"- **{html.escape(nm)}:** {html.escape(err)}"
                    )

        if st.button("Close", key="dist_bulk_close_done"):
            st.session_state.pop(DIST_BULK_UI_KEY, None)
            st.rerun()

    _open_or_fallback("Bulk action", body)

# Shared generate / regenerate / delete distribution logic for management hub row actions.
import pandas as pd

from core.auth import get_current_user, get_user_ip
from conf.constants import *
from core.db import *
from core.utils import *


def _dist_fail(dialog_title: str, error: str, contract_name: str = "") -> dict:
    return {
        "ok": False,
        "error": error,
        "contract_name": contract_name or "",
        "lines": [],
        "dialog_title": dialog_title,
    }


def _dist_ok_generate(contract_name: str, had_service_distribution: bool) -> dict:
    lines = ["Contract distribution data created."]
    if had_service_distribution:
        lines.append("Service distribution data created.")
    lines.append("Payment data created.")
    return {
        "ok": True,
        "error": None,
        "contract_name": contract_name or "",
        "lines": lines,
        "dialog_title": "Distribution generated",
    }


def _dist_ok_regenerate(contract_name: str, had_service_distribution: bool) -> dict:
    lines = ["Contract distribution data updated."]
    if had_service_distribution:
        lines.append("Service distribution data updated.")
    lines.append("Payment data updated.")
    return {
        "ok": True,
        "error": None,
        "contract_name": contract_name or "",
        "lines": lines,
        "dialog_title": "Distribution regenerated",
    }


def execute_generate_distribution(contract_row) -> dict:
    """Generate distribution for one contract. Returns dict for UI popup."""
    nm = str(contract_row.get("contract_name", "") or "")
    contract_type = contract_row.get("contract_type", "")
    if not contract_type:
        return _dist_fail("Generate failed", "Contract type is missing.", nm)

    if check_distribution_exists(contract_row["id"], contract_type):
        return _dist_fail(
            "Generate failed",
            "Distribution already exists. Use Regenerate.",
            nm,
        )

    load_all()
    lessors_df = st.session_state.lessors_df.copy()
    store_monthly_sales_df = load_df(STORE_MONTHLY_SALES_TABLE, STORE_MONTHLY_SALES_COLS)
    services_df = st.session_state.services_df.copy()
    contract_services_df = st.session_state.contract_services_df.copy()

    distribution_rows = generate_contract_distribution(
        contract_row, lessors_df, store_monthly_sales_df, services_df, contract_services_df
    )
    service_distribution_rows = generate_service_distribution(
        contract_row, services_df, contract_services_df
    )

    if not distribution_rows:
        return _dist_fail(
            "Generate failed",
            "Could not build distribution from this contract. Check contract details.",
            nm,
        )

    try:
        dist_table = get_distribution_table(contract_type)
        dist_cols = get_distribution_storage_cols(contract_type)

        if dist_table == CONTRACT_DISTRIBUTION_TABLE:
            return _dist_fail("Generate failed", "Invalid contract type for distribution tables.", nm)

        agg_dist = aggregate_distribution_rows_for_db(contract_type, distribution_rows)
        dist_df = pd.DataFrame(agg_dist)
        for col in dist_cols:
            if col not in dist_df.columns:
                dist_df[col] = None if "_date" in col.lower() else ""
        dist_df = dist_df[dist_cols]

        existing_dist_df_local = load_df(dist_table, dist_cols)
        new_dist_df = pd.concat([existing_dist_df_local, dist_df], ignore_index=True)

        if not save_df(new_dist_df, dist_table):
            return _dist_fail("Generate failed", "Could not save contract distribution to the database.", nm)
    except Exception as e:
        return _dist_fail(
            "Generate failed",
            f"Could not save distribution: {str(e)}",
            nm,
        )

    had_svc = bool(service_distribution_rows)
    if service_distribution_rows:
        service_dist_df = pd.DataFrame(
            aggregate_service_distribution_for_db(service_distribution_rows)
        )
        existing_service_dist_df_local = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
        _cid = str(contract_row["id"])
        if not existing_service_dist_df_local.empty:
            existing_service_dist_df_local = existing_service_dist_df_local[
                existing_service_dist_df_local["contract_id"].astype(str) != _cid
            ]
        new_service_dist_df = pd.concat([existing_service_dist_df_local, service_dist_df], ignore_index=True)
        if not save_df(new_service_dist_df, SERVICE_DISTRIBUTION_TABLE):
            return _dist_fail("Generate failed", "Could not save service distribution to the database.", nm)

    create_payment_records_from_distribution(
        contract_row["id"],
        contract_type,
        contract_row,
        distribution_rows=distribution_rows,
        service_distribution_rows=service_distribution_rows,
    )

    u = get_current_user()
    log_action(
        user_id=u["id"] if u else None,
        user_name=u["name"] if u else "System",
        action_type="generate",
        entity_type="distribution",
        entity_id=contract_row["id"],
        entity_name=contract_row.get("contract_name", ""),
        action_details=(
            f"Generated distribution: {len(distribution_rows)} contract rows, "
            f"{len(service_distribution_rows)} service rows; payments refreshed"
        ),
        ip_address=get_user_ip(),
    )

    return _dist_ok_generate(nm, had_svc)


def execute_regenerate_distribution(contract_row) -> dict:
    """Regenerate distribution for one contract. Returns dict for UI popup."""
    nm = str(contract_row.get("contract_name", "") or "")
    contract_type = contract_row.get("contract_type", "")
    if not check_distribution_exists(contract_row["id"], contract_type):
        return _dist_fail(
            "Regenerate failed",
            "No distribution exists yet. Use Generate first.",
            nm,
        )

    load_all()
    lessors_df = st.session_state.lessors_df.copy()
    store_monthly_sales_df = load_df(STORE_MONTHLY_SALES_TABLE, STORE_MONTHLY_SALES_COLS)
    services_df = st.session_state.services_df.copy()
    contract_services_df = st.session_state.contract_services_df.copy()

    distribution_rows = generate_contract_distribution(
        contract_row, lessors_df, store_monthly_sales_df, services_df, contract_services_df
    )
    service_distribution_rows = generate_service_distribution(
        contract_row, services_df, contract_services_df
    )

    if not distribution_rows:
        return _dist_fail(
            "Regenerate failed",
            "Could not rebuild distribution. Check contract details.",
            nm,
        )

    try:
        dist_table = get_distribution_table(contract_type)
        dist_cols = get_distribution_storage_cols(contract_type)

        agg_dist = aggregate_distribution_rows_for_db(contract_type, distribution_rows)
        dist_df = pd.DataFrame(agg_dist)
        for col in dist_cols:
            if col not in dist_df.columns:
                dist_df[col] = None if "_date" in col.lower() else ""
        dist_df = dist_df[dist_cols]

        existing_dist_df_local = load_df(dist_table, dist_cols)
        existing_dist_df_local = existing_dist_df_local[
            existing_dist_df_local["contract_id"] != contract_row["id"]
        ]
        new_dist_df = pd.concat([existing_dist_df_local, dist_df], ignore_index=True)

        if not save_df(new_dist_df, dist_table):
            return _dist_fail("Regenerate failed", "Could not save contract distribution to the database.", nm)
    except Exception as e:
        return _dist_fail(
            "Regenerate failed",
            f"Could not save distribution: {str(e)}",
            nm,
        )

    had_svc = bool(service_distribution_rows)
    _cid = str(contract_row["id"])
    if service_distribution_rows:
        service_dist_df = pd.DataFrame(
            aggregate_service_distribution_for_db(service_distribution_rows)
        )
        existing_service_dist_df_local = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
        if not existing_service_dist_df_local.empty:
            existing_service_dist_df_local = existing_service_dist_df_local[
                existing_service_dist_df_local["contract_id"].astype(str) != _cid
            ]
        new_service_dist_df = pd.concat([existing_service_dist_df_local, service_dist_df], ignore_index=True)
        if not save_df(new_service_dist_df, SERVICE_DISTRIBUTION_TABLE):
            return _dist_fail("Regenerate failed", "Could not save service distribution to the database.", nm)
    else:
        existing_service_dist_df_local = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
        if not existing_service_dist_df_local.empty:
            trimmed = existing_service_dist_df_local[
                existing_service_dist_df_local["contract_id"].astype(str) != _cid
            ]
            if len(trimmed) != len(existing_service_dist_df_local) and not save_df(
                trimmed, SERVICE_DISTRIBUTION_TABLE
            ):
                return _dist_fail(
                    "Regenerate failed",
                    "Could not clear service distribution for this contract.",
                    nm,
                )

    create_payment_records_from_distribution(
        contract_row["id"],
        contract_type,
        contract_row,
        distribution_rows=distribution_rows,
        service_distribution_rows=service_distribution_rows,
    )

    u = get_current_user()
    log_action(
        user_id=u["id"] if u else None,
        user_name=u["name"] if u else "System",
        action_type="regenerate",
        entity_type="distribution",
        entity_id=contract_row["id"],
        entity_name=contract_row.get("contract_name", ""),
        action_details=(
            f"Regenerated distribution: {len(distribution_rows)} contract rows, "
            f"{len(service_distribution_rows)} service rows; payments refreshed"
        ),
        ip_address=get_user_ip(),
    )

    return _dist_ok_regenerate(nm, had_svc)


def execute_delete_all_distribution_for_contract(contract_row) -> tuple[bool, str]:
    """Delete contract + service distribution for one contract (and payments via DB helper)."""
    cid = contract_row["id"]
    contract_type = contract_row.get("contract_type", "")
    nm = contract_row.get("contract_name", "")

    has_c = check_distribution_exists(cid, contract_type)
    existing_service_dist_df = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
    _scid = str(cid)
    has_s = False
    if not existing_service_dist_df.empty:
        has_s = (
            existing_service_dist_df["contract_id"].astype(str) == _scid
        ).any()

    if not has_c and not has_s:
        return False, "No distribution data to delete for this contract."

    deleted_contract = False
    deleted_service = False
    if has_c:
        dist_df = load_distribution_for_contract(cid, contract_type)
        dist_count = len(dist_df) if dist_df is not None and not dist_df.empty else 0
        if delete_contract_distribution(cid, contract_type):
            u = get_current_user()
            log_action(
                user_id=u["id"] if u else None,
                user_name=u["name"] if u else "System",
                action_type="delete",
                entity_type="distribution",
                entity_id=cid,
                entity_name=nm,
                action_details=f"Deleted contract distribution: {dist_count} records",
                ip_address=get_user_ip(),
            )
            deleted_contract = True
        else:
            return False, "Failed to delete contract distribution."

    if has_s:
        svc_n = int((existing_service_dist_df["contract_id"].astype(str) == _scid).sum())
        if delete_service_distribution(cid):
            u = get_current_user()
            log_action(
                user_id=u["id"] if u else None,
                user_name=u["name"] if u else "System",
                action_type="delete",
                entity_type="service_distribution",
                entity_id=cid,
                entity_name=nm,
                action_details=f"Deleted service distribution: {svc_n} records",
                ip_address=get_user_ip(),
            )
            deleted_service = True
        else:
            return False, "Failed to delete service distribution."

    nm_disp = str(nm or "this contract").strip() or "this contract"
    if deleted_contract and deleted_service:
        msg = f"Contract and service distribution data deleted successfully for **{nm_disp}**."
    elif deleted_contract:
        msg = f"Contract distribution data deleted successfully for **{nm_disp}**."
    else:
        msg = f"Service distribution data deleted successfully for **{nm_disp}**."

    return True, msg

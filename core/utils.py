# core/utils.py
# Utility functions
import pandas as pd
import os
import json
import streamlit as st
import time
import uuid
from datetime import datetime, timedelta
import calendar
from conf.constants import *
from core.db import *


def _norm_rent_date_str(val):
    if val is None or val == "":
        return ""
    try:
        if hasattr(val, "strftime"):
            return val.strftime("%Y-%m-%d")
        return pd.to_datetime(val).strftime("%Y-%m-%d")
    except Exception:
        s = str(val).strip()
        return s[:10] if len(s) >= 10 else s


def compute_distribution_yearly_increase_amount(
    contract_type: str,
    yearly_increase_type: str,
    yearly_increase_pct: float,
    yearly_increase_fixed_amount: float,
    contract_rent_amount: float,
    rev_min: float,
    years_passed_float: float,
    inc_mode: str,
    apply_period_override_fn,
    period_num: int,
) -> float:
    """Currency step added per contract year on monthly base rent (Fixed/ROU) or rev_min (Revenue Share)."""
    iy = int(years_passed_float)
    if iy < 1:
        return 0.0
    base = float(contract_rent_amount) if contract_type in ("Fixed", "ROU") else float(rev_min)

    if str(yearly_increase_type or "").strip() == "Fixed Amount Increased":
        return float(round(float(yearly_increase_fixed_amount or 0), 2))

    if inc_mode in ("all", "specific", "year_rules") and apply_period_override_fn is not None:
        curr = float(apply_period_override_fn(base, period_num, iy + 1))
        prev = float(apply_period_override_fn(base, period_num, iy))
        return float(round(max(0.0, curr - prev), 2))

    pct = float(yearly_increase_pct or 0)
    curr = base * ((1.0 + pct / 100.0) ** iy)
    prev = base * ((1.0 + pct / 100.0) ** (iy - 1))
    return float(round(max(0.0, curr - prev), 2))


def rou_legacy_distribution_yearly_increase_amount(
    p: int,
    fp: int,
    free_months: set,
    coverage_periods: set,
    yearly_increase_type: str,
    yearly_increase_fixed_amount: float,
    yearly_increase_pct: float,
    base_monthly_rent: float,
    inc_mode: str,
) -> float:
    """ROU legacy cash-rent tiers: monthly increase between anniversary bands (no mid-step blend)."""
    if p < fp or p in free_months or p in coverage_periods:
        return 0.0
    k = p - fp
    b = k // 12
    if b < 1:
        return 0.0
    if inc_mode in ("all", "specific", "year_rules"):
        return 0.0
    if str(yearly_increase_type or "").strip() == "Fixed Amount Increased":
        return float(round(float(yearly_increase_fixed_amount or 0), 2))
    er = float(yearly_increase_pct or 0) / 100.0
    r_curr = float(base_monthly_rent) * ((1.0 + er) ** b)
    r_prev = float(base_monthly_rent) * ((1.0 + er) ** (b - 1))
    return float(round(max(0.0, r_curr - r_prev), 2))


def aggregate_distribution_rows_for_db(contract_type, rows):
    """One persisted row per (contract_id, rent_date); contract-level amounts = sums of per-lessor generator rows."""
    if not rows:
        return []
    from collections import defaultdict

    def sumf(key, grp):
        t = 0.0
        for x in grp:
            try:
                t += float(str(x.get(key) or 0) or 0)
            except Exception:
                pass
        return t

    groups = defaultdict(list)
    for r in rows:
        groups[(str(r.get("contract_id", "")), _norm_rent_date_str(r.get("rent_date")))].append(r)
    out = []
    for (_, _), grp in sorted(groups.items(), key=lambda x: x[0]):
        first = grp[0]
        due_sum = sumf("lessor_due_amount", grp)
        disc_sum = sumf("discount_amount", grp)
        adv_sum = sumf("advanced_amount", grp)

        if contract_type == "Fixed":
            out.append(
                {
                    "contract_id": first.get("contract_id", ""),
                    "rent_date": first.get("rent_date", ""),
                    "rent_amount": first.get("rent_amount", ""),
                    "yearly_increase_amount": first.get("yearly_increase_amount", ""),
                    "discount_amount": str(disc_sum),
                    "advanced_amount": str(adv_sum),
                    "due_amount": str(due_sum),
                }
            )
        elif contract_type == "Revenue Share":
            out.append(
                {
                    "contract_id": first.get("contract_id", ""),
                    "rent_date": first.get("rent_date", ""),
                    "rent_amount": first.get("rent_amount", ""),
                    "yearly_increase_amount": first.get("yearly_increase_amount", ""),
                    "revenue_min": first.get("revenue_min", ""),
                    "revenue_max": first.get("revenue_max", ""),
                    "revenue_amount": first.get("revenue_amount", ""),
                    "discount_amount": str(disc_sum),
                    "advanced_amount": str(adv_sum),
                    "due_amount": str(due_sum),
                }
            )
        elif contract_type == "ROU":
            out.append(
                {
                    "contract_id": first.get("contract_id", ""),
                    "rent_date": first.get("rent_date", ""),
                    "rent_amount": first.get("rent_amount", ""),
                    "yearly_increase_amount": first.get("yearly_increase_amount", ""),
                    "opening_liability": first.get("opening_liability", ""),
                    "interest": first.get("interest", ""),
                    "closing_liability": first.get("closing_liability", ""),
                    "rou_depreciation": first.get("rou_depreciation", ""),
                    "period": first.get("period", ""),
                    "principal": first.get("principal", ""),
                    "lease_accrual": first.get("lease_accrual", ""),
                    "pv_of_lease_payment": first.get("pv_of_lease_payment", ""),
                    "discount_amount": str(disc_sum),
                    "advanced_amount": str(adv_sum),
                    "advance_coverage_flag": first.get("advance_coverage_flag", ""),
                    "due_amount": str(due_sum),
                }
            )
        else:
            out.append(
                {
                    "contract_id": first.get("contract_id", ""),
                    "rent_date": first.get("rent_date", ""),
                    "rent_amount": first.get("rent_amount", ""),
                    "yearly_increase_amount": first.get("yearly_increase_amount", ""),
                    "discount_amount": str(disc_sum),
                    "advanced_amount": str(adv_sum),
                    "due_amount": str(due_sum),
                }
            )
    return out


def aggregate_service_distribution_for_db(rows):
    """One row per (contract_id, service_id, rent_date)."""
    if not rows:
        return []
    out = []
    for r in rows:
        try:
            amt = float(str(r.get("amount") or 0) or 0)
        except Exception:
            amt = 0.0
        try:
            disc = float(str(r.get("discount_amount") or 0) or 0)
        except Exception:
            disc = 0.0
        due = amt - disc
        out.append(
            {
                "contract_id": str(r.get("contract_id", "")),
                "service_id": str(r.get("service_id", "")),
                "rent_date": r.get("rent_date", ""),
                "amount": str(amt),
                "discount_amount": str(disc),
                "due_amount": str(due),
            }
        )
    return out


# Helper functions to get distribution table and columns based on contract type
def get_distribution_table(contract_type):
    """Get the distribution table name for a contract type"""
    if contract_type == "Fixed":
        return CONTRACT_DISTRIBUTION_FIXED_TABLE
    elif contract_type == "Revenue Share":
        return CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE
    elif contract_type == "ROU":
        return CONTRACT_DISTRIBUTION_ROU_TABLE
    else:
        # No fallback - raise error for invalid contract type
        raise ValueError(f"Invalid contract type: {contract_type}. Must be 'Fixed', 'Revenue Share', or 'ROU'.")

def get_distribution_cols(contract_type):
    """Get the distribution columns for a contract type"""
    if contract_type == "Fixed":
        return CONTRACT_DISTRIBUTION_FIXED_COLS
    elif contract_type == "Revenue Share":
        return CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS
    elif contract_type == "ROU":
        return CONTRACT_DISTRIBUTION_ROU_COLS
    else:
        return CONTRACT_DISTRIBUTION_COLS  # Fallback


def get_distribution_storage_cols(contract_type):
    """Columns persisted on MySQL for a contract type (no JOIN-only fields)."""
    if contract_type == "Fixed":
        return list(CONTRACT_DISTRIBUTION_FIXED_STORAGE_COLS)
    if contract_type == "Revenue Share":
        return list(CONTRACT_DISTRIBUTION_REVENUE_SHARE_STORAGE_COLS)
    if contract_type == "ROU":
        return list(CONTRACT_DISTRIBUTION_ROU_STORAGE_COLS)
    return list(CONTRACT_DISTRIBUTION_FIXED_STORAGE_COLS)


def _rent_month_first_day(rent_date_val):
    s = _norm_rent_date_str(rent_date_val)
    if not s:
        return None
    try:
        d = pd.to_datetime(s).date()
        return d.replace(day=1)
    except Exception:
        return None


def expand_distribution_for_per_lessor_ui(dist_df, contract_id, contract_lessors_df, contract_type):
    """Explode contract-month rows to per-lessor rows for UI (proportional discount/advance split)."""
    if dist_df is None or dist_df.empty:
        return dist_df
    if contract_lessors_df is None or contract_lessors_df.empty:
        return dist_df
    if "lessor_id" in dist_df.columns:
        try:
            if dist_df["lessor_id"].astype(str).str.strip().ne("").any():
                return dist_df
        except Exception:
            pass
    cid = str(contract_id)
    cls = contract_lessors_df[contract_lessors_df["contract_id"].astype(str) == cid]
    if cls.empty:
        return dist_df
    rows = []
    for _, d in dist_df.iterrows():
        try:
            rent = float(str(d.get("rent_amount") or 0) or 0)
        except Exception:
            rent = 0.0
        try:
            disc_t = float(str(d.get("discount_amount") or 0) or 0)
        except Exception:
            disc_t = 0.0
        try:
            adv_t = float(str(d.get("advanced_amount") or 0) or 0)
        except Exception:
            adv_t = 0.0
        for _, lr in cls.iterrows():
            try:
                sp = float(str(lr.get("share_pct") or 0) or 0)
            except Exception:
                sp = 0.0
            lid = str(lr.get("lessor_id", "") or "")
            gross = rent * sp / 100.0
            ld = gross - disc_t * sp / 100.0 - adv_t * sp / 100.0
            row = d.to_dict()
            row["lessor_id"] = lid
            row["lessor_share_pct"] = str(sp)
            row["lessor_due_amount"] = str(round(ld, 2))
            row["discount_amount"] = str(round(disc_t * sp / 100.0, 2))
            row["advanced_amount"] = str(round(adv_t * sp / 100.0, 2))
            rows.append(row)
    out = pd.DataFrame(rows)
    if not out.empty and "lessor_id" in out.columns:
        ld = st.session_state.get("lessors_df", pd.DataFrame())
        if ld is not None and not ld.empty:
            m = dict(zip(ld["id"].astype(str), ld["name"].astype(str)))
            out["lessor_name"] = out["lessor_id"].astype(str).map(m).fillna("")
        elif "lessor_name" not in out.columns:
            out["lessor_name"] = ""
    return out


def rebuild_distribution_rows_for_payments(contract_id, contract_type, contract_row, cursor):
    """Regenerate per-lessor rows from contract math, then scale to match saved contract-month DB totals."""
    lessors_df = st.session_state.lessors_df.copy()
    store_df = st.session_state.get("store_monthly_sales_df")
    if store_df is None or (hasattr(store_df, "empty") and store_df.empty):
        store_df = load_df(STORE_MONTHLY_SALES_TABLE, STORE_MONTHLY_SALES_COLS)
    services_df = st.session_state.services_df.copy()
    cs_df = st.session_state.contract_services_df.copy()

    raw = generate_contract_distribution(contract_row, lessors_df, store_df, services_df, cs_df)
    dist_table = get_distribution_table(contract_type)
    cursor.execute(
        f"SELECT * FROM `{dist_table}` WHERE contract_id = %s ORDER BY rent_date",
        (str(contract_id),),
    )
    db_rows = cursor.fetchall() or []
    if not db_rows:
        return raw

    db_by_date = {_norm_rent_date_str(r.get("rent_date")): r for r in db_rows}
    from collections import defaultdict

    g = defaultdict(list)
    for r in raw:
        g[_norm_rent_date_str(r.get("rent_date"))].append(r)

    out = []
    for rd in sorted(g.keys()):
        grp = g[rd]
        db_row = db_by_date.get(rd)
        if not db_row:
            continue
        try:
            gen_rent = float(str(grp[0].get("rent_amount") or 0) or 0)
        except Exception:
            gen_rent = 0.0
        try:
            db_rent = float(str(db_row.get("rent_amount") or 0) or 0)
        except Exception:
            db_rent = gen_rent
        sf = (db_rent / gen_rent) if abs(gen_rent) > 1e-12 else 1.0

        for r in grp:
            r2 = dict(r)
            for k in ("lessor_due_amount", "discount_amount", "advanced_amount", "yearly_increase_amount"):
                if k in r2 and r2[k] not in (None, "", "None"):
                    try:
                        r2[k] = str(float(str(r2[k])) * sf)
                    except Exception:
                        pass
            if contract_type == "Revenue Share" and db_row.get("revenue_amount") not in (None, "", "None"):
                try:
                    grv = float(str(grp[0].get("revenue_amount") or 0) or 0)
                    drv = float(str(db_row.get("revenue_amount") or 0) or 0)
                    if abs(grv) > 1e-12 and abs(drv - grv) > 1e-9:
                        rv_sf = drv / grv
                        if str(r2.get("revenue_amount") or "").strip():
                            try:
                                r2["revenue_amount"] = str(float(str(r2["revenue_amount"])) * rv_sf)
                            except Exception:
                                pass
                except Exception:
                    pass
            r2["rent_amount"] = str(db_rent)
            out.append(r2)
    return out


def load_distribution_for_contract(contract_id, contract_type=None, per_lessor_view=False):
    """Load distribution data for a specific contract from the appropriate table."""
    if contract_type:
        table = get_distribution_table(contract_type)
        cols = get_distribution_cols(contract_type)
        dist_df = load_df(table, cols)
        filtered = dist_df[dist_df["contract_id"] == contract_id] if not dist_df.empty else pd.DataFrame(columns=cols)
        if per_lessor_view and contract_type and not filtered.empty:
            cl = st.session_state.get("contract_lessors_df", pd.DataFrame())
            filtered = expand_distribution_for_per_lessor_ui(filtered, contract_id, cl, contract_type)
        return filtered
    all_dfs = []
    for table, cols in [
        (CONTRACT_DISTRIBUTION_FIXED_TABLE, CONTRACT_DISTRIBUTION_FIXED_COLS),
        (CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE, CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS),
        (CONTRACT_DISTRIBUTION_ROU_TABLE, CONTRACT_DISTRIBUTION_ROU_COLS),
    ]:
        try:
            dist_df = load_df(table, cols)
            if not dist_df.empty:
                filtered = dist_df[dist_df["contract_id"] == contract_id]
                if not filtered.empty:
                    all_dfs.append(filtered)
        except Exception:
            continue
    if all_dfs:
        return pd.concat(all_dfs, ignore_index=True)
    return pd.DataFrame()

def check_distribution_exists(contract_id, contract_type=None):
    """Check if distribution exists for a contract"""
    dist_df = load_distribution_for_contract(contract_id, contract_type)
    return not dist_df.empty

# Table name mappings
TABLE_MAPPINGS = {
    LESSORS_TABLE: 'lessors',
    ASSETS_TABLE: 'assets',
    STORES_TABLE: 'stores',
    CONTRACTS_TABLE: 'contracts',
    CONTRACT_LESSORS_TABLE: 'contract_lessors',
    # CONTRACT_DISTRIBUTION_TABLE removed - using separate tables per contract type
    CONTRACT_DISTRIBUTION_FIXED_TABLE: 'contract_distribution_fixed',
    CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE: 'contract_distribution_revenue_share',
    CONTRACT_DISTRIBUTION_ROU_TABLE: 'contract_distribution_rou',
    STORE_MONTHLY_SALES_TABLE: 'store_monthly_sales',
    SERVICES_TABLE: 'services',
    CONTRACT_SERVICES_TABLE: 'contract_services',
    CONTRACT_SERVICE_LESSORS_TABLE: 'contract_service_lessors',
    SERVICE_DISTRIBUTION_TABLE: 'service_distribution',
    USERS_TABLE: 'users',
    ROLES_TABLE: 'roles',
    PERMISSIONS_TABLE: 'permissions',
    ROLE_PERMISSIONS_TABLE: 'role_permissions',
    USER_ROLES_TABLE: 'user_roles',
    ACTION_LOGS_TABLE: 'action_logs',
}

def get_table_name(table_key):
    """Get MySQL table name from table key"""
    if table_key in TABLE_MAPPINGS:
        return TABLE_MAPPINGS[table_key]
    # Fallback: try to extract from key
    for key, table in TABLE_MAPPINGS.items():
        if key in table_key or table_key in key:
            return table
    # If it's already a table name, return as-is
    return table_key.lower()

def load_df(table_key, columns):
    """Load data from MySQL table into DataFrame"""
    table_name = get_table_name(table_key)
    return load_table_to_df(table_name, columns)

def save_df(df, path_or_key):
    """Save DataFrame to MySQL table"""
    table_name = get_table_name(path_or_key)
    # Get columns from config based on path_or_key
    if path_or_key == LESSORS_TABLE:
        cols = LESSORS_COLS
    elif path_or_key == ASSETS_TABLE:
        cols = ASSETS_COLS
    elif path_or_key == STORES_TABLE:
        cols = STORES_COLS
    elif path_or_key == CONTRACTS_TABLE:
        cols = CONTRACTS_COLS
    elif path_or_key == CONTRACT_LESSORS_TABLE:
        cols = CONTRACT_LESSORS_COLS
    elif path_or_key == CONTRACT_DISTRIBUTION_FIXED_TABLE:
        cols = CONTRACT_DISTRIBUTION_FIXED_STORAGE_COLS
    elif path_or_key == CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE:
        cols = CONTRACT_DISTRIBUTION_REVENUE_SHARE_STORAGE_COLS
    elif path_or_key == CONTRACT_DISTRIBUTION_ROU_TABLE:
        cols = CONTRACT_DISTRIBUTION_ROU_STORAGE_COLS
    # Old CONTRACT_DISTRIBUTION_TABLE removed - use specific tables instead
    elif path_or_key == STORE_MONTHLY_SALES_TABLE:
        cols = STORE_MONTHLY_SALES_COLS
    elif path_or_key == SERVICES_TABLE:
        cols = SERVICES_COLS
    elif path_or_key == CONTRACT_SERVICES_TABLE:
        cols = CONTRACT_SERVICES_COLS
    elif path_or_key == SERVICE_DISTRIBUTION_TABLE:
        cols = SERVICE_DISTRIBUTION_STORAGE_COLS
    elif path_or_key == CONTRACT_SERVICE_LESSORS_TABLE:
        cols = CONTRACT_SERVICE_LESSORS_COLS
    elif path_or_key == USERS_TABLE:
        cols = USERS_COLS
    elif path_or_key == ROLES_TABLE:
        cols = ROLES_COLS
    elif path_or_key == PERMISSIONS_TABLE:
        cols = PERMISSIONS_COLS
    elif path_or_key == ROLE_PERMISSIONS_TABLE:
        cols = ROLE_PERMISSIONS_COLS
    elif path_or_key == USER_ROLES_TABLE:
        cols = USER_ROLES_COLS
    elif path_or_key == ACTION_LOGS_TABLE:
        cols = ACTION_LOGS_COLS
    else:
        cols = list(df.columns)
    
    return save_df_to_table(df, table_name, cols)

def next_int_id(df, start=1):
    """Get next integer ID from table"""
    if df is None or df.empty:
        return start
    try:
        # Try to get table name from df if possible, otherwise use default
        # For now, we'll use the df approach as fallback
        nums = [int(x) for x in df['id'].tolist() if str(x).isdigit()]
        return max(nums) + 1 if nums else start
    except Exception:
        return start

def next_int_id_from_table(table_name, start=1):
    """Get next integer ID directly from MySQL table"""
    return get_max_id(table_name, 'id', start)

def calc_end_date_iso(commencement_date, tenure_months):
    if not commencement_date or tenure_months is None:
        return ""
    try:
        dt = pd.to_datetime(commencement_date)
        ed = dt + pd.DateOffset(months=int(tenure_months)) - pd.DateOffset(days=1)
        return ed.date().isoformat()
    except Exception:
        return ""

def generate_rou_distribution_enhanced(contract_row, lessors_df, services_df=None, contract_services_df=None, contract_service_lessors_df=None):
    """
    Generate the legacy-template-matching IFRS-16 ROU lease schedule (free months flat, period-based PV,
    and advance-months behavior) and return list of distribution rows.
    
    If lessors are assigned to services, service amounts are added to the base rent.
    """
    distribution_rows = []
    
    try:
        import json
        from datetime import timedelta
        
        contract_id = contract_row['id']
        contract_name = contract_row['contract_name']
        asset_or_store_id = contract_row.get('asset_or_store_id', '')
        asset_or_store_name = contract_row.get('asset_or_store_name', '')
        cost_center = ""
        
        # Get cost center from asset/store
        if asset_or_store_id:
            from core.db import get_db_connection
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                # Try assets first
                cursor.execute("SELECT cost_center FROM assets WHERE id = %s", (asset_or_store_id,))
                result = cursor.fetchone()
                if not result:
                    # Try stores
                    cursor.execute("SELECT cost_center FROM stores WHERE id = %s", (asset_or_store_id,))
                    result = cursor.fetchone()
                if result:
                    cost_center = result.get('cost_center', '')
                cursor.close()
                connection.close()
        
        commencement_date = pd.to_datetime(contract_row['commencement_date'])
        first_payment_date = pd.to_datetime(contract_row.get('first_payment_date', contract_row['commencement_date']))
        end_date = pd.to_datetime(contract_row['end_date'])
        tenure_months = int(contract_row.get('tenure_months', 0) or 0)
        
        # Get base monthly rent and yearly increase
        base_monthly_rent = float(contract_row.get('rent_amount', 0) or 0)
        _is_tax_val = str(contract_row.get('is_tax_added', 0) or 0).strip().lower()
        is_tax_added = _is_tax_val in ("1", "true", "yes", "y")
        if is_tax_added:
            base_monthly_rent *= 1.01
        yearly_increase_pct = float(contract_row.get('yearly_increase', 0) or 0)
        yearly_increase_type = contract_row.get('yearly_increase_type', 'Increased %')
        yearly_increase_fixed_amount = float(contract_row.get('yearly_increase_fixed_amount', 0) or 0)
        inc_mode = str(contract_row.get("increase_by_period_mode", "legacy") or "legacy").strip().lower()
        try:
            inc_all_pct = float(contract_row.get("increase_by_period_all_pct", 0) or 0)
        except Exception:
            inc_all_pct = 0.0
        inc_period_map = {}
        inc_year_rules = []
        inc_all_value_type = "percent"
        try:
            raw_map = str(contract_row.get("increase_by_period_map", "") or "").strip()
            parsed_map = json.loads(raw_map) if raw_map else {}
            if isinstance(parsed_map, dict):
                if isinstance(parsed_map.get("year_rules"), list):
                    inc_year_rules = parsed_map.get("year_rules", [])
                inc_all_value_type = str(parsed_map.get("all_value_type", "percent") or "percent").strip().lower()
                for k, v in parsed_map.items():
                    if k in ("year_rules", "all_value_type"):
                        continue
                    p = int(str(k).strip())
                    if p >= 1:
                        inc_period_map[p] = float(v)
        except Exception:
            inc_period_map = {}
            inc_year_rules = []
            inc_all_value_type = "percent"
        inc_mode = str(contract_row.get("increase_by_period_mode", "legacy") or "legacy").strip().lower()
        try:
            inc_all_pct = float(contract_row.get("increase_by_period_all_pct", 0) or 0)
        except Exception:
            inc_all_pct = 0.0
        inc_period_map = {}
        inc_year_rules = []
        inc_all_value_type = "percent"
        try:
            raw_map = str(contract_row.get("increase_by_period_map", "") or "").strip()
            parsed_map = json.loads(raw_map) if raw_map else {}
            if isinstance(parsed_map, dict):
                if isinstance(parsed_map.get("year_rules"), list):
                    inc_year_rules = parsed_map.get("year_rules", [])
                inc_all_value_type = str(parsed_map.get("all_value_type", "percent") or "percent").strip().lower()
                for k, v in parsed_map.items():
                    if k in ("year_rules", "all_value_type"):
                        continue
                    p = int(str(k).strip())
                    if p >= 1:
                        inc_period_map[p] = float(v)
        except Exception:
            inc_period_map = {}
            inc_year_rules = []
            inc_all_value_type = "percent"

        def apply_period_override(base_value: float, period_num: int, contract_year_num: int = 1) -> float:
            p = max(int(period_num), 1)
            y = max(int(contract_year_num), 1)
            if inc_mode == "all" and inc_all_pct > 0:
                if inc_all_value_type == "amount":
                    return float(base_value + (inc_all_pct * (p - 1)))
                return float(base_value * ((1.0 + inc_all_pct / 100.0) ** (p - 1)))
            if inc_mode == "year_rules" and inc_year_rules:
                factor = 1.0
                add_amount = 0.0
                for yy in range(1, y + 1):
                    for rr in inc_year_rules:
                        years = rr.get("years", []) if isinstance(rr, dict) else []
                        if yy in years:
                            rv = float(rr.get("value", 0) or 0)
                            rt = str(rr.get("value_type", "percent") or "percent").strip().lower()
                            if rt == "amount":
                                add_amount += rv
                            else:
                                factor *= (1.0 + rv / 100.0)
                return float((base_value * factor) + add_amount)
            if inc_mode == "specific" and inc_period_map:
                factor = 1.0
                for k in sorted(inc_period_map.keys()):
                    if k <= p:
                        factor *= (1.0 + (inc_period_map[k] / 100.0))
                return float(base_value * factor)
            return float(base_value)

        # Validate inputs
        if base_monthly_rent <= 0:
            st.error("Rent amount must be greater than 0 for ROU contracts.")
            return []
        
        if tenure_months <= 0:
            st.error("Tenure months must be greater than 0.")
            return []
        
        # Get service amounts for this contract if lessors are in services
        contract_service_amounts = {}  # {service_id: {amount, yearly_increase_pct}}
        lessors_in_services = set()  # Track which lessors are assigned to services
        
        if services_df is not None and contract_services_df is not None and contract_service_lessors_df is not None:
            # Get all services for this contract
            contract_services_list = contract_services_df[contract_services_df['contract_id'] == contract_id]
            
            for _, cs_row in contract_services_list.iterrows():
                service_id = cs_row['service_id']
                base_service_amount = float(cs_row.get('amount', 0) or 0)
                service_yearly_increase = float(cs_row.get('yearly_increase_pct', 0) or 0)
                
                if base_service_amount > 0:
                    # Check if any lessors are assigned to this service
                    service_lessors = contract_service_lessors_df[
                        (contract_service_lessors_df['contract_id'] == contract_id) &
                        (contract_service_lessors_df['service_id'] == service_id)
                    ]
                    
                    if not service_lessors.empty:
                        # At least one lessor is assigned to this service
                        contract_service_amounts[service_id] = {
                            'amount': base_service_amount,
                            'yearly_increase_pct': service_yearly_increase
                        }
                        # Track which lessors are in services
                        lessors_in_services.update(service_lessors['lessor_id'].astype(str).tolist())
                        print(f"[DEBUG ROU Enhanced] Service {service_id} with amount {base_service_amount} assigned to lessors: {service_lessors['lessor_id'].tolist()}")
        
        # Calculate total monthly service amount (will be added to base rent)
        def get_total_service_amount_for_period(period_num: int) -> float:
            """Calculate total service amount for a period with yearly increases"""
            total_service = 0.0
            for service_id, service_data in contract_service_amounts.items():
                base_amount = service_data['amount']
                yearly_increase = service_data['yearly_increase_pct']
                year_num = ((period_num - 1) // 12) + 1
                
                if yearly_increase > 0:
                    # Apply yearly increase
                    service_amount = base_amount * ((1 + yearly_increase / 100.0) ** (year_num - 1))
                else:
                    service_amount = base_amount
                
                total_service += service_amount
            return total_service
        
        # Parse free and advance months (comma-separated, e.g., "1,2,3" for first 3 months)
        free_months_str = contract_row.get('free_months', '')
        free_months = [int(x.strip()) for x in free_months_str.split(',') if x.strip().isdigit()] if free_months_str else []
        
        advance_months_str = contract_row.get('advance_months', '')
        advance_months = [int(x.strip()) for x in advance_months_str.split(',') if x.strip().isdigit()] if advance_months_str else []
        
        # Discount rate — use effective compounding, not simple annual/12 division
        discount_rate_annual = float(contract_row.get('discount_rate', 0) or 0)
        annual_rate = discount_rate_annual / 100.0 if discount_rate_annual > 0 else 0.0
        monthly_effective_rate = (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0 if annual_rate > 0.0 else 0.0
        
        # Parse lessors
        lessors = json.loads(contract_row['lessors_json']) if contract_row.get('lessors_json') else []
        
        if not lessors:
            st.error("No lessors found for this contract. Please add at least one lessor.")
            return []
        
        # Step 1: Build lease payment schedule with escalating rent
        lease_schedule = []
        current_date = commencement_date
        period_num = 0
        paid_count = 0  # Counts only periods where rent accrues (excludes free months)

        while current_date <= end_date and period_num < tenure_months:
            period_num += 1

            # Determine free/advance status before computing rent (needed for year_num)
            is_free_month = period_num in free_months
            is_advance_month = period_num in advance_months

            # Escalation year is based on paid periods only; free months do not advance the year
            if not is_free_month:
                paid_count += 1
            year_num = ((paid_count - 1) // 12) + 1 if paid_count > 0 else 1

            # Calculate monthly rent with yearly increase
            if yearly_increase_type == "Fixed Amount Increased":
                # Fixed amount: add fixed_amount * (year_num - 1)
                monthly_rent = base_monthly_rent + (yearly_increase_fixed_amount * (year_num - 1))
            else:
                # Percentage: compounded annually
                if inc_mode in ("all", "specific", "year_rules"):
                    monthly_rent = apply_period_override(base_monthly_rent, period_num, year_num)
                else:
                    monthly_rent = base_monthly_rent * ((1 + yearly_increase_pct / 100) ** (year_num - 1))

            # Add service amounts if any lessors are in services
            if contract_service_amounts:
                service_amount = get_total_service_amount_for_period(period_num)
                monthly_rent += service_amount
                print(f"[DEBUG ROU Enhanced] Period {period_num}: Base rent={base_monthly_rent}, Service amount={service_amount}, Total rent={monthly_rent}")
            
            # Calculate payment date (first payment date + period offset)
            payment_frequency = str(contract_row.get('payment_frequency', 'Monthly') or 'Monthly').strip()
            if payment_frequency == "Yearly":
                months_from_first_payment = 12 * ((period_num - 1) // 12)
            elif payment_frequency == "Quarter":
                months_from_first_payment = 3 * ((period_num - 1) // 3)
            elif payment_frequency == "2 Months":
                months_from_first_payment = 2 * ((period_num - 1) // 2)
            else:
                months_from_first_payment = (period_num - 1)
            payment_date = first_payment_date + pd.DateOffset(months=months_from_first_payment)
            
            # Original rent (lease accrual) - always accrues regardless of payment timing
            lease_accrual = monthly_rent
            
            # For free months: accrues but no payment
            # For advance months: payment happens but accrual is normal
            # Cash flow (actual payment timing)
            if is_free_month:
                cash_flow = 0  # No payment in free months
            elif is_advance_month:
                cash_flow = monthly_rent  # Payment happens in advance month
            else:
                cash_flow = monthly_rent  # Normal payment
            
            rd_first = pd.Timestamp(current_date.year, current_date.month, 1).date()
            lease_schedule.append({
                'period': period_num,
                'year_num': year_num,
                'month_year': f"{current_date.year}-{int(current_date.month):02d}",
                'rent_date': rd_first,
                'payment_date': payment_date,
                'lease_accrual': lease_accrual,
                'lease_payment': cash_flow,
                'cash_flow': cash_flow,  # Store cash_flow for NPV calculation
            })
            
            current_date = current_date + pd.DateOffset(months=1)
        
        if not lease_schedule:
            st.error("Failed to generate lease schedule. Check contract dates and tenure.")
            return []
        
        # Step 2: Handle advance payments
        # Advance payments are paid early, but the accrual happens in the normal period
        # We need to track when the actual accrual period is vs when payment happens
        # For now, we'll keep accrual in the normal period and payment in advance period
        # The cash_flow represents when payment actually happens
        
        # Step 3: Calculate NPV of all lease payments
        # NPV should be based on payment dates, not accrual dates
        total_pv = 0
        for schedule_item in lease_schedule:
            # Use cash flow (actual payment) for NPV calculation
            cash_flow_val = schedule_item['cash_flow']
            period = schedule_item['period']
            
            # Calculate months from commencement to payment date
            payment_date = schedule_item['payment_date']
            months_from_commencement = (payment_date.year - commencement_date.year) * 12 + \
                                      (payment_date.month - commencement_date.month)
            
            if annual_rate > 0.0 and months_from_commencement >= 0:
                time_factor = (months_from_commencement + 1) / 12.0
                pv = cash_flow_val / ((1.0 + annual_rate) ** time_factor)
            else:
                pv = cash_flow_val if months_from_commencement >= 0 else 0
            
            schedule_item['pv_of_lease_payment'] = pv
            total_pv += pv
        
        initial_rou_asset = total_pv
        initial_lease_liability = total_pv
        monthly_depreciation = initial_rou_asset / tenure_months if tenure_months > 0 else 0
        
        # Step 4: Generate IFRS-16 schedule month by month
        lease_liability = initial_lease_liability
        
        print(f"[DEBUG ROU Enhanced] Starting distribution generation: contract_id={contract_id}, commencement={commencement_date}, end_date={end_date}")
        print(f"[DEBUG ROU Enhanced] Total lessors: {len(lessors)}, Total periods in schedule: {len(lease_schedule)}")
        
        for idx, schedule_item in enumerate(lease_schedule):
            period = schedule_item['period']
            rent_date = schedule_item['rent_date']
            payment_date = schedule_item['payment_date']
            lease_accrual = schedule_item['lease_accrual']
            lease_payment = schedule_item['lease_payment']
            pv_of_payment = schedule_item['pv_of_lease_payment']
            cash_flow = schedule_item['lease_payment']
            
            # Opening liability
            opening_liability = lease_liability
            
            # Interest expense (calculated on opening liability from the 1st month)
            # Interest should be calculated from month 1 regardless of discounts or free months
            interest_expense = opening_liability * monthly_effective_rate if monthly_effective_rate > 0.0 else 0.0
            
            # Principal reduction = actual cash payment - interest
            # For free months: no payment, so principal = -interest (liability increases)
            # For normal/advance months: payment reduces principal
            if lease_payment > 0:
                principal = lease_payment - interest_expense
            else:
                # Free month: no payment, interest accrues (increases liability)
                principal = -interest_expense
            
            # Closing liability
            closing_liability = opening_liability - principal
            
            # Ensure closing liability doesn't go negative (shouldn't happen, but safety check)
            if closing_liability < 0:
                closing_liability = 0
                principal = opening_liability
            
            # Depreciation
            depreciation = monthly_depreciation
            
            # ROU NBV
            months_passed = period
            rou_nbv = initial_rou_asset - (depreciation * months_passed)
            
            # Update lease liability for next period
            lease_liability = closing_liability
            
            # Create distribution row for each lessor
            print(f"[DEBUG ROU Enhanced] Processing period {period}, month_year={schedule_item['month_year']}, payment_date={payment_date}")
            
            for lessor in lessors:
                lessor_id = lessor.get('id', '')
                lessor_name = lessor.get('name', '')
                lessor_share_pct = float(lessor.get('share', 0) or 0)
                
                # Get lessor name from lessors_df if available and check tax_exempted status
                if lessor_id:
                    lessor_row = lessors_df[lessors_df['id'] == str(lessor_id)]
                    if not lessor_row.empty:
                        lessor_name = lessor_row.iloc[0].get('name', lessor_name)

                # Holding tax per lessor is now applied at payment level, not stored as holding_tax_amount in distribution
                # Note: ROU contracts don't check exemption in distribution - it's handled at payment level
                print(f"[DEBUG ROU Enhanced] Creating row for period {period}, lessor {lessor_id}, month_year={schedule_item['month_year']}")
                
                # Single distribution row with all columns (only IDs, names will be retrieved via JOINs)
                # rent_date is the first day of the month
                rent_date_obj = schedule_item["rent_date"]
                if not hasattr(rent_date_obj, "year"):
                    rent_date_obj = pd.Timestamp(rent_date_obj).date()
                yn_enh = int(schedule_item.get("year_num") or 1)
                y_enh_amt = compute_distribution_yearly_increase_amount(
                    "ROU",
                    yearly_increase_type,
                    yearly_increase_pct,
                    yearly_increase_fixed_amount,
                    base_monthly_rent,
                    0.0,
                    float(yn_enh - 1),
                    inc_mode,
                    apply_period_override,
                    period,
                )
                dist_row = {
                    "contract_id": contract_id,
                    "period": str(period),
                    "rent_date": rent_date_obj.strftime('%Y-%m-%d'),  # First day of month
                    "lessor_id": lessor_id,
                    "asset_or_store_id": asset_or_store_id,
                    "rent_amount": str(lease_accrual),  # Use lease_accrual as rent_amount
                    "lessor_share_pct": str(lessor_share_pct),
                    "lessor_due_amount": str(lease_accrual * lessor_share_pct / 100),  # Calculate lessor due
                    # tax_pct, tax_amount, amount_after_tax removed from distribution - now stored in payments table
                    "yearly_increase_amount": str(y_enh_amt),
                    # ROU specific columns
                    "rent_date": rent_date.strftime('%Y-%m-%d'),
                    "payment_date": payment_date.strftime('%Y-%m-%d'),
                    "lease_accrual": str(lease_accrual),
                    "lease_payment": str(lease_payment),
                    "pv_of_lease_payment": str(pv_of_payment),
                    "opening_liability": str(opening_liability),
                    "interest": str(interest_expense),
                    "closing_liability": str(closing_liability),
                    "rou_depreciation": str(depreciation),
                    "discount_amount": str(round(lease_accrual * lessor_share_pct / 100, 2)) if period in free_months else "",
                    "advanced_amount": str(round(lease_accrual * lessor_share_pct / 100, 2)) if period in advance_months else "",
                    "cost_center": cost_center,
                    # Revenue Share columns (empty for ROU)
                    "revenue_min": "",
                    "revenue_max": "",
                    "revenue_share_pct": "",
                    "revenue_share_after_max_pct": "",
                    "revenue_amount": ""
                }
                
                distribution_rows.append(dist_row)
            
            print(f"[DEBUG ROU Enhanced] Period {period}: Created {len(lessors)} row(s) for {len(lessors)} lessor(s)")
        
        print(f"[DEBUG ROU Enhanced] Finished distribution generation: Total rows created={len(distribution_rows)}")
        
    except Exception as e:
        st.error(f"Error generating enhanced ROU distribution: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return ([], [])  # Return empty tuples on error
    
    # Debug: Check if we have rows
    if not distribution_rows:
        st.warning(f"Enhanced ROU distribution generated 0 rows. Contract: {contract_row.get('contract_name', 'Unknown')}, Lessors: {len(lessors)}")
    
    return distribution_rows if distribution_rows else []

def generate_rou_distribution_legacy_template(contract_row, lessors_df, services_df=None, contract_services_df=None, contract_service_lessors_df=None):
    """
    Excel-style ROU: periods 0..tenure_months; PV = accrual / (1 + r/12)**period (period 0 undiscounted).
    Advance in period 0; free months and next A advance-covered periods have zero accrual (A = advance count).
    Escalation from the first payment period: every 12 payment months, a mid-step month uses 1.05× prior tier
    (average of consecutive escalation steps), matching nominal annual steps from commencement of paid rent.
    Last period uses contract end_date and prorated rent when end aligns day-before commencement (0.5×) or by
    calendar days in the end month. Opening = sum(PV); period-0 interest on PV of periods 1..N only; final
    period interest 0 and closing 0.
    """
    distribution_rows = []

    def round2(x):
        try:
            return round(float(x), 2)
        except Exception:
            return 0.0

    contract_id = contract_row['id']
    contract_name = contract_row['contract_name']
    asset_or_store_id = contract_row.get('asset_or_store_id', '')
    asset_or_store_name = contract_row.get('asset_or_store_name', '')

    commencement_date = pd.to_datetime(contract_row['commencement_date'])
    tenure_months = int(contract_row.get('tenure_months', 0) or 0)

    base_monthly_rent = float(contract_row.get('rent_amount', 0) or 0)
    _is_tax_val = str(contract_row.get('is_tax_added', 0) or 0).strip().lower()
    is_tax_added = _is_tax_val in ("1", "true", "yes", "y")
    if is_tax_added:
        base_monthly_rent *= 1.01
    yearly_increase_pct = float(contract_row.get('yearly_increase', 0) or 0)
    yearly_increase_type = contract_row.get('yearly_increase_type', 'Increased %')
    yearly_increase_fixed_amount = float(contract_row.get('yearly_increase_fixed_amount', 0) or 0)
    if base_monthly_rent <= 0 or tenure_months <= 0:
        return []

    contract_service_amounts = {}
    lessors_in_services = set()

    if services_df is not None and contract_services_df is not None and contract_service_lessors_df is not None:
        contract_services_list = contract_services_df[contract_services_df['contract_id'] == contract_id]

        for _, cs_row in contract_services_list.iterrows():
            service_id = cs_row['service_id']
            base_service_amount = float(cs_row.get('amount', 0) or 0)
            service_yearly_increase = float(cs_row.get('yearly_increase_pct', 0) or 0)

            if base_service_amount > 0:
                service_lessors = contract_service_lessors_df[
                    (contract_service_lessors_df['contract_id'] == contract_id) &
                    (contract_service_lessors_df['service_id'] == service_id)
                ]

                if not service_lessors.empty:
                    contract_service_amounts[service_id] = {
                        'amount': base_service_amount,
                        'yearly_increase_pct': service_yearly_increase
                    }
                    lessors_in_services.update(service_lessors['lessor_id'].astype(str).tolist())
                    print(f"[DEBUG ROU] Service {service_id} with amount {base_service_amount} assigned to lessors: {service_lessors['lessor_id'].tolist()}")

    def get_total_service_amount_for_period(period_num: int) -> float:
        total_service = 0.0
        for service_id, service_data in contract_service_amounts.items():
            base_amount = service_data['amount']
            yearly_increase = service_data['yearly_increase_pct']
            year_num = ((period_num - 1) // 12) + 1

            if yearly_increase > 0:
                service_amount = base_amount * ((1 + yearly_increase / 100.0) ** (year_num - 1))
            else:
                service_amount = base_amount

            total_service += service_amount
        return total_service

    free_months_str = contract_row.get('free_months', '') or ''
    free_months = sorted({int(x.strip()) for x in free_months_str.split(',') if x.strip().isdigit()})

    advance_months_str = contract_row.get('advance_months', '') or ''
    advance_months = sorted({int(x.strip()) for x in advance_months_str.split(',') if x.strip().isdigit()})
    A = int(contract_row.get('advance_months_count', 0) or 0)
    if A <= 0:
        A = int(len(advance_months) or 0)

    dr_raw = float(contract_row.get('discount_rate', 0) or 0)
    annual_rate = (dr_raw / 100.0) if dr_raw > 1.0 else dr_raw
    monthly_rate_simple = annual_rate / 12.0 if annual_rate > 0.0 else 0.0

    # Optional contract-wide period increase overrides (separate section in contract form).
    inc_mode = str(contract_row.get("increase_by_period_mode", "legacy") or "legacy").strip().lower()
    try:
        inc_all_pct = float(contract_row.get("increase_by_period_all_pct", 0) or 0)
    except Exception:
        inc_all_pct = 0.0
    inc_period_map = {}
    inc_year_rules = []
    inc_all_value_type = "percent"
    try:
        raw_map = str(contract_row.get("increase_by_period_map", "") or "").strip()
        parsed_map = json.loads(raw_map) if raw_map else {}
        if isinstance(parsed_map, dict):
            if isinstance(parsed_map.get("year_rules"), list):
                inc_year_rules = parsed_map.get("year_rules", [])
            inc_all_value_type = str(parsed_map.get("all_value_type", "percent") or "percent").strip().lower()
            for k, v in parsed_map.items():
                if k in ("year_rules", "all_value_type"):
                    continue
                p = int(str(k).strip())
                if p >= 1:
                    inc_period_map[p] = float(v)
    except Exception:
        inc_period_map = {}
        inc_year_rules = []
        inc_all_value_type = "percent"

    def apply_period_override(base_value: float, period_num: int, contract_year_num: int = 1) -> float:
        p = max(int(period_num), 1)
        y = max(int(contract_year_num), 1)
        if inc_mode == "all" and inc_all_pct > 0:
            if inc_all_value_type == "amount":
                return float(base_value + (inc_all_pct * (p - 1)))
            return float(base_value * ((1.0 + inc_all_pct / 100.0) ** (p - 1)))
        if inc_mode == "year_rules" and inc_year_rules:
            factor = 1.0
            add_amount = 0.0
            for yy in range(1, y + 1):
                for rr in inc_year_rules:
                    years = rr.get("years", []) if isinstance(rr, dict) else []
                    if yy in years:
                        rv = float(rr.get("value", 0) or 0)
                        rt = str(rr.get("value_type", "percent") or "percent").strip().lower()
                        if rt == "amount":
                            add_amount += rv
                        else:
                            factor *= (1.0 + rv / 100.0)
            return float((base_value * factor) + add_amount)
        if inc_mode == "specific" and inc_period_map:
            factor = 1.0
            for k in sorted(inc_period_map.keys()):
                if k <= p:
                    factor *= (1.0 + (inc_period_map[k] / 100.0))
            return float(base_value * factor)
        return float(base_value)

    lessors = json.loads(contract_row.get('lessors_json') or "[]")
    if not lessors:
        return []

    end_date = pd.to_datetime(contract_row.get('end_date') or commencement_date)

    def schedule_ts(p: int) -> pd.Timestamp:
        comm = pd.Timestamp(commencement_date).normalize()
        end = pd.Timestamp(end_date).normalize()
        if p == 0:
            return comm
        first_sched = pd.Timestamp(comm.year, comm.month, 1) + pd.DateOffset(months=1)
        if p < tenure_months:
            return first_sched + pd.DateOffset(months=p - 1)
        return end

    def stub_fraction(comm_dt, end_dt) -> float:
        comm_dt = pd.Timestamp(comm_dt)
        end_dt = pd.Timestamp(end_dt)
        cd = int(comm_dt.day)
        ed = int(end_dt.day)
        if cd > 1 and ed == cd - 1:
            return 0.5
        ms = pd.Timestamp(end_dt.year, end_dt.month, 1)
        dim = calendar.monthrange(int(end_dt.year), int(end_dt.month))[1]
        return min(1.0, max(0.0, (end_dt - ms).days + 1) / dim)

    def month_year_for_period(p: int) -> str:
        rd = schedule_ts(p)
        return f"{rd.year}-{rd.month:02d}"

    coverage_periods = set()
    if A > 0:
        covered = 0
        # One advance month is already consumed at period 0 as upfront payment.
        # Coverage on timeline periods 1..N therefore uses the remaining advance count.
        coverage_target = max(A - 1, 0)
        for _p in range(1, tenure_months + 1):
            if covered >= coverage_target:
                break
            if _p in free_months:
                continue
            coverage_periods.add(_p)
            covered += 1

    first_pay_period = None
    for _p in range(1, tenure_months + 1):
        if _p in free_months or _p in coverage_periods:
            continue
        first_pay_period = _p
        break
    if first_pay_period is None:
        first_pay_period = tenure_months
    fp = int(first_pay_period)

    def full_rent_payment_period(p: int) -> float:
        if p < fp or p in free_months or p in coverage_periods:
            return 0.0
        k = p - fp
        b = k // 12
        m = k % 12
        svc = get_total_service_amount_for_period(p) if contract_service_amounts else 0.0
        if yearly_increase_type == "Fixed Amount Increased":
            R_curr = float(base_monthly_rent + yearly_increase_fixed_amount * float(b))
            R_next = float(base_monthly_rent + yearly_increase_fixed_amount * float(b + 1))
            if m == 6:
                R_mid = (R_curr + R_next) / 2.0
            elif m > 6:
                R_mid = R_next
            else:
                R_mid = R_curr
        else:
            er = yearly_increase_pct / 100.0
            R_curr = float(base_monthly_rent * ((1.0 + er) ** b))
            if m == 6:
                R_mid = R_curr * (1.0 + er / 2.0)
            elif m > 6:
                R_mid = R_curr * (1.0 + er)
            else:
                R_mid = R_curr
        if contract_service_amounts and svc:
            print(f"[DEBUG ROU] Period {p}: Base rent component, Service={svc}, Total={R_mid + svc}")
        return float(apply_period_override((R_mid + svc), p, (b + 1)))

    def payment_type_for(p: int) -> str:
        if p == 0 and A > 0:
            return "advance"
        if p in free_months:
            return "free"
        if p in coverage_periods:
            return "coverage"
        return "normal"

    def lease_accrual_for(p: int) -> float:
        pt = payment_type_for(p)
        if pt == "advance":
            return float(A * full_rent_payment_period(fp))
        if pt in ("free", "coverage"):
            return 0.0
        if p == 0:
            return 0.0
        if p == tenure_months:
            k = p - fp
            m = k % 12
            # Excel stub: prorate the regular monthly amount (e.g. same coupon as prior month),
            # not the 1.05× mid-step blend row used when a full blend month is paid in full.
            base_stub = (
                full_rent_payment_period(p - 1) if (m == 6 and p > fp) else full_rent_payment_period(p)
            )
            return float(base_stub * stub_fraction(commencement_date, end_date))
        return float(full_rent_payment_period(p))

    def pv_for_period(p: int, accrual: float) -> float:
        if p == 0:
            return float(accrual)
        if annual_rate > 0.0 and accrual != 0.0:
            return float(accrual / ((1.0 + monthly_rate_simple) ** p))
        return float(accrual)

    def npv(rate: float, cashflows):
        """
        Excel-style NPV:
        - cashflows start at period 1 (not period 0)
        - first cashflow discounted by (1 + rate)^1
        """
        if rate <= 0:
            return float(sum(float(cf) for cf in cashflows))
        return float(
            sum(float(cf) / ((1.0 + rate) ** i) for i, cf in enumerate(cashflows, start=1))
        )

    accrual_by_p = {p: lease_accrual_for(p) for p in range(0, tenure_months + 1)}
    # Excel convention: NPV uses periods 1..N only, then period 0 is added manually.
    future_cashflows = [accrual_by_p[t] for t in range(1, tenure_months + 1)]
    npv_future = npv(monthly_rate_simple, future_cashflows)
    lease_accrual_period_0 = float(accrual_by_p.get(0, 0.0))
    opening_liability_initial = float(npv_future + lease_accrual_period_0)

    # Keep an explicit PV schedule stream (including period 0) for reporting/debug parity.
    pv_schedule_total = float(
        sum(pv_for_period(t, accrual_by_p[t]) for t in range(0, tenure_months + 1))
    )
    pv_liability_base_future = float(npv_future)

    initial_rou_asset = opening_liability_initial
    monthly_depreciation = initial_rou_asset / tenure_months if tenure_months > 0 else 0.0
    debt_balance_open = float(opening_liability_initial)

    def display_rent_for_row(p: int) -> float:
        if p == 0:
            return float(full_rent_payment_period(fp))
        if p in free_months or p in coverage_periods:
            return float(full_rent_payment_period(fp))
        if p == tenure_months:
            return float(full_rent_payment_period(tenure_months))
        return float(full_rent_payment_period(p))

    print(f"[DEBUG ROU Legacy] Starting distribution generation: contract_id={contract_id}, commencement={commencement_date}, tenure_months={tenure_months}")
    print(f"[DEBUG ROU Legacy] Total lessors: {len(lessors)}")

    paid_period_index = 0
    for p in range(0, tenure_months + 1):
        sd = schedule_ts(p)
        rent_date = sd.to_pydatetime()
        month_year = month_year_for_period(p)
        payment_type = payment_type_for(p)
        is_free = payment_type == "free"
        is_coverage = payment_type == "coverage"
        is_normal = payment_type == "normal"
        R = float(display_rent_for_row(p))

        prev_paid_period_index = paid_period_index
        if is_normal:
            paid_period_index += 1

        lease_payment = float(accrual_by_p[p])
        pv_of_payment = float(pv_for_period(p, lease_payment))

        r_discount = float(-display_rent_for_row(p)) if is_free else 0.0
        r_advance = float(-display_rent_for_row(p)) if (p in advance_months and p > 0) else 0.0

        lease_accrual = lease_payment

        opening_liability = float(debt_balance_open)
        if p == tenure_months:
            interest = 0.0
        elif p == 0 and payment_type == "advance" and lease_payment > 0:
            # Opening is full PV column total; advance is not in the interest base (Excel).
            interest = (
                pv_liability_base_future * monthly_rate_simple if monthly_rate_simple > 0.0 else 0.0
            )
        elif lease_payment <= 0 or payment_type in ("free", "coverage"):
            interest = opening_liability * monthly_rate_simple if monthly_rate_simple > 0.0 else 0.0
        else:
            # Normal payment periods: interest is calculated on full opening balance.
            interest = opening_liability * monthly_rate_simple if monthly_rate_simple > 0.0 else 0.0

        closing_liability = opening_liability + interest - lease_payment
        if p == tenure_months:
            closing_liability = 0.0
        elif closing_liability < 0:
            closing_liability = 0.0
        principal = lease_payment - interest
        debt_balance_open = closing_liability

        if p <= 10:
            print(
                f"[DEBUG ROU Legacy Check] p={p}, payment_type={payment_type}, rent={round2(R)}, "
                f"paid_period_index={paid_period_index}, opening_balance={round2(opening_liability)}, "
                f"closing_balance={round2(closing_liability)}"
            )
            if payment_type in ("free", "advance", "coverage") and paid_period_index != prev_paid_period_index:
                print(f"[ERROR ROU Legacy] Period {p}: paid_period_index incremented on {payment_type}.")
            if payment_type == "free" and closing_liability <= opening_liability:
                print(
                    f"[ERROR ROU Legacy] Period {p}: free period liability must increase "
                    f"(open={opening_liability}, close={closing_liability})."
                )

        rou_depreciation = float(monthly_depreciation)

        print(f"[DEBUG ROU Legacy] Processing period {p}, month_year={month_year}")

        for lessor in lessors:
            lessor_id = lessor.get('id', '')
            lessor_name = lessor.get('name', '')
            lessor_share_pct = float(lessor.get('share', 0) or 0)
            if lessor_id:
                lessor_row = lessors_df[lessors_df['id'] == str(lessor_id)]
                if not lessor_row.empty:
                    lessor_name = lessor_row.iloc[0].get('name', lessor_name)

            print(f"[DEBUG ROU Legacy] Creating row for period {p}, lessor {lessor_id}, month_year={month_year}")

            rent_date_iso = pd.Timestamp(rent_date).strftime('%Y-%m-%d')
            y_la = rou_legacy_distribution_yearly_increase_amount(
                p,
                fp,
                set(free_months),
                coverage_periods,
                yearly_increase_type,
                yearly_increase_fixed_amount,
                yearly_increase_pct,
                base_monthly_rent,
                inc_mode,
            )
            distribution_rows.append({
                "contract_id": contract_id,
                "contract_name": contract_name,
                "contract_type": "ROU",
                "lessor_name": lessor_name,
                "asset_or_store_name": asset_or_store_name,
                "lessor_id": lessor_id,
                "asset_or_store_id": asset_or_store_id,
                "rent_amount": str(round2(R)),
                "lessor_share_pct": str(lessor_share_pct),
                "lessor_due_amount": "" if lease_accrual == 0 else str(round2(lease_accrual * lessor_share_pct / 100)),
                "yearly_increase_amount": str(y_la),
                "revenue_min": "",
                "revenue_max": "",
                "revenue_share_pct": "",
                "revenue_share_after_max_pct": "",
                "revenue_amount": "",
                "opening_liability": str(round2(opening_liability)),
                "interest": str(round2(interest)),
                "closing_liability": str(round2(closing_liability)),
                "principal": str(round2(principal)),
                "rou_depreciation": str(round2(rou_depreciation)),
                "period": str(p),
                "rent_date": rent_date_iso,
                "lease_accrual": "" if lease_accrual == 0 else str(round2(lease_accrual)),
                "pv_of_lease_payment": "" if pv_of_payment == 0 else str(round2(pv_of_payment)),
                "discount_amount": "" if r_discount == 0 else str(round2(abs(r_discount) * lessor_share_pct / 100)),
                "advanced_amount": "" if r_advance == 0 else str(round2(abs(r_advance) * lessor_share_pct / 100)),
                "advance_coverage_flag": "1" if is_coverage else "0",
            })

        print(f"[DEBUG ROU Legacy] Period {p}: Created {len(lessors)} row(s) for {len(lessors)} lessor(s)")

    # After full ROU schedule: advance contracts show no cash due in period 0 (due_amount aggregate = 0).
    if A > 0:
        for r in distribution_rows:
            if str(r.get("period", "")).strip() == "0":
                r["lessor_due_amount"] = ""

    print(f"[DEBUG ROU Legacy] Finished distribution generation: Total rows created={len(distribution_rows)}, periods processed={tenure_months + 1}")
    return distribution_rows

def generate_contract_distribution(contract_row, lessors_df, store_monthly_sales_df=None, services_df=None, contract_services_df=None):
    """Generate monthly distribution data for a contract"""
    contract_type = contract_row.get('contract_type', '')
    if contract_type == "ROU":
        # Get contract_service_lessors_df from session state if available
        contract_service_lessors_df = None
        try:
            contract_service_lessors_df = st.session_state.get('contract_service_lessors_df', None)
        except:
            pass
        
        result = generate_rou_distribution_legacy_template(
            contract_row, 
            lessors_df, 
            services_df=services_df, 
            contract_services_df=contract_services_df,
            contract_service_lessors_df=contract_service_lessors_df
        )
        if not result:
            st.warning("ROU distribution returned empty. Check contract parameters.")
        return result if result else []
    
    # Continue with original logic for other contract types
    distribution_rows = []
    
    try:
        contract_id = contract_row['id']
        contract_name = contract_row['contract_name']
        contract_type = contract_row['contract_type']
        commencement_date = pd.to_datetime(contract_row['commencement_date'])
        end_date = pd.to_datetime(contract_row['end_date'])
        lessors_json = contract_row['lessors_json']
        tax_pct = float(contract_row.get('tax', 0) or 0)
        # Holding tax is no longer configured per contract.
        # Withholding is now controlled per lessor via lessor_withholding_periods.
        # Default withholding rate when not exempt is 3%.
        default_withholding_pct = 3.0
        yearly_increase_pct = float(contract_row.get('yearly_increase', 0) or 0)
        yearly_increase_type = contract_row.get('yearly_increase_type', 'Increased %')
        yearly_increase_fixed_amount = float(contract_row.get('yearly_increase_fixed_amount', 0) or 0)
        asset_or_store_id = contract_row.get('asset_or_store_id', '')
        asset_or_store_name = contract_row.get('asset_or_store_name', '')
        rev_min = float(contract_row.get('rev_min', 0) or 0)
        rev_max = float(contract_row.get('rev_max', 0) or 0)
        rev_share_pct = float(contract_row.get('rev_share_pct', 0) or 0)
        rev_share_after_max_pct = float(contract_row.get('rev_share_after_max_pc', 0) or 0)

        # Optional contract-wide period increase overrides.
        inc_mode = str(contract_row.get("increase_by_period_mode", "all") or "all").strip().lower()
        try:
            inc_all_pct = float(contract_row.get("increase_by_period_all_pct", 0) or 0)
        except Exception:
            inc_all_pct = 0.0
        inc_period_map = {}
        inc_year_rules = []
        inc_all_value_type = "percent"
        try:
            raw_map = str(contract_row.get("increase_by_period_map", "") or "").strip()
            parsed_map = json.loads(raw_map) if raw_map else {}
            if isinstance(parsed_map, dict):
                if isinstance(parsed_map.get("year_rules"), list):
                    inc_year_rules = parsed_map.get("year_rules", [])
                inc_all_value_type = str(parsed_map.get("all_value_type", "percent") or "percent").strip().lower()
                for k, v in parsed_map.items():
                    if k in ("year_rules", "all_value_type"):
                        continue
                    p = int(str(k).strip())
                    if p >= 1:
                        inc_period_map[p] = float(v)
        except Exception:
            inc_period_map = {}
            inc_year_rules = []
            inc_all_value_type = "percent"

        def apply_period_override(base_value: float, period_num: int, contract_year_num: int) -> float:
            p = max(int(period_num), 1)
            y = max(int(contract_year_num), 1)
            if inc_mode == "all" and inc_all_pct > 0:
                if inc_all_value_type == "amount":
                    return float(base_value + (inc_all_pct * (p - 1)))
                return float(base_value * ((1.0 + inc_all_pct / 100.0) ** (p - 1)))
            if inc_mode == "year_rules" and inc_year_rules:
                factor = 1.0
                add_amount = 0.0
                for yy in range(1, y + 1):
                    for rr in inc_year_rules:
                        years = rr.get("years", []) if isinstance(rr, dict) else []
                        if yy in years:
                            rv = float(rr.get("value", 0) or 0)
                            rt = str(rr.get("value_type", "percent") or "percent").strip().lower()
                            if rt == "amount":
                                add_amount += rv
                            else:
                                factor *= (1.0 + rv / 100.0)
                return float((base_value * factor) + add_amount)
            if inc_mode == "specific" and inc_period_map:
                mult = 1.0
                for k in sorted(inc_period_map.keys()):
                    if k <= p:
                        mult *= (1.0 + (inc_period_map[k] / 100.0))
                return float(base_value * mult)
            return float(base_value)
        
        # Parse lessors
        lessors = json.loads(lessors_json) if lessors_json else []
        
        # Get services for this contract
        contract_services = {}
        if services_df is not None and contract_services_df is not None:
            cs_list = contract_services_df[contract_services_df['contract_id'] == contract_id]
            for _, cs_row in cs_list.iterrows():
                service_id = cs_row['service_id']
                service_row = services_df[services_df['id'] == service_id]
                if not service_row.empty:
                    contract_services[service_row.iloc[0]['name']] = {
                        'id': service_id,
                        'amount': float(cs_row.get('amount', 0) or 0),
                        'yearly_increase_pct': float(cs_row.get('yearly_increase_pct', 0) or 0)
                    }
        
        # Check if this is an enhanced ROU contract (has rent_per_year)
        is_enhanced_rou = (contract_type == "ROU" and contract_row.get('rent_per_year'))
        
        if is_enhanced_rou:
            # Use enhanced ROU calculation
            # Get contract_service_lessors_df from session state if available
            contract_service_lessors_df = None
            try:
                contract_service_lessors_df = st.session_state.get('contract_service_lessors_df', None)
            except:
                pass
            
            return generate_rou_distribution_enhanced(
                contract_row, 
                lessors_df,
                services_df=services_df,
                contract_services_df=contract_services_df,
                contract_service_lessors_df=contract_service_lessors_df
            )
        
        # Legacy ROU or other contract types - use original logic
        # ROU-specific calculations (calculate once at the start)
        rou_initial_pv = None
        rou_monthly_depreciation = None
        rou_monthly_discount_rate = None
        lease_liability = None
        
        if contract_type == "ROU":
            # Get discount rate and tenure
            discount_rate_annual = float(contract_row.get('discount_rate', 0) or 0)
            tenure_months = int(contract_row.get('tenure_months', 0) or 0)
            base_rent_amount = float(contract_row.get('rent_amount', 0) or 0)
            
            if discount_rate_annual > 0 and tenure_months > 0 and base_rent_amount > 0:
                # Effective monthly rate via annual compounding
                rou_annual_rate = discount_rate_annual / 100.0
                rou_monthly_discount_rate = (1.0 + rou_annual_rate) ** (1.0 / 12.0) - 1.0
                
                # Present Value using effective monthly rate
                # PV = P × (1 - (1 + r)^(-n)) / r
                if rou_monthly_discount_rate > 0:
                    pv_factor = (1 - (1 + rou_monthly_discount_rate) ** (-tenure_months)) / rou_monthly_discount_rate
                    rou_initial_pv = base_rent_amount * pv_factor
                else:
                    # If discount rate is 0, PV is just sum of payments
                    rou_initial_pv = base_rent_amount * tenure_months
                
                # Calculate monthly depreciation (straight-line over lease term)
                rou_monthly_depreciation = rou_initial_pv / tenure_months if tenure_months > 0 else 0
                
                # Initialize lease liability (starts at PV)
                lease_liability = rou_initial_pv
        
        # Get first_payment_date (defaults to commencement_date if not set)
        first_payment_date = pd.to_datetime(contract_row.get('first_payment_date') or contract_row['commencement_date'])
        payment_frequency = str(contract_row.get('payment_frequency', 'Monthly') or 'Monthly').strip()
        
        # Parse free_months for Fixed and Revenue Share contracts
        free_months = []
        if contract_type == "Fixed" or contract_type == "Revenue Share":
            free_months_str = contract_row.get('free_months', '') or ''
            if free_months_str:
                free_months = sorted({int(x.strip()) for x in free_months_str.split(',') if x.strip().isdigit()})
        
        # Get advance_payment for Fixed contracts
        advance_payment_remaining = 0.0
        if contract_type == "Fixed":
            advance_payment_remaining = float(contract_row.get('advance_payment', 0) or 0)
        
        # Revenue Share: how prepaid advance is reflected on distribution (and payment dates = month-end)
        rs_mode = "none"
        advance_months_rs = set()
        rs_advance_remaining = 0.0
        if contract_type == "Revenue Share":
            rs_mode = str(contract_row.get("rev_share_advance_mode") or "none").strip().lower()
            if rs_mode in ("", "legacy"):
                rs_mode = "none"
            ams_raw = str(contract_row.get("advance_months", "") or "").strip()
            if ams_raw:
                try:
                    advance_months_rs = {int(x.strip()) for x in ams_raw.split(",") if x.strip().isdigit()}
                except Exception:
                    advance_months_rs = set()
            if rs_mode in ("chronological", "periods"):
                try:
                    rs_advance_remaining = float(contract_row.get("rev_share_payment_advance") or 0)
                except (TypeError, ValueError):
                    rs_advance_remaining = 0.0
        
        # Helper function to calculate payment_date for a given period
        def calculate_payment_date(period_num):
            """Calculate payment date based on first_payment_date and payment_frequency"""
            if payment_frequency == "Yearly":
                months = 12 * ((period_num - 1) // 12)
            elif payment_frequency == "Quarter":
                months = 3 * ((period_num - 1) // 3)
            elif payment_frequency == "2 Months":
                months = 2 * ((period_num - 1) // 2)
            else:
                # Monthly (default)
                months = (period_num - 1)
            ts = pd.Timestamp(first_payment_date) + pd.DateOffset(months=months)
            if contract_type == "Revenue Share":
                # Due on last calendar day of the payment month (not 1st like Fixed/ROU)
                month_end = pd.Timestamp(ts.year, ts.month, 1) + pd.offsets.MonthEnd(0)
                return month_end.to_pydatetime()
            return ts.replace(day=1).to_pydatetime()
        
        # Generate monthly periods
        # CRITICAL: This loop MUST continue until end_date regardless of:
        # - Exemption status
        # - Whether periods exist or not
        # - Any errors in exemption checking
        # - Any errors processing lessors
        # The loop should NEVER stop early based on exemption or period status
        current_date = commencement_date
        month_num = 0
        
        print(f"[DEBUG] Starting distribution generation: contract_id={contract_id}, contract_type={contract_type}")
        print(f"[DEBUG] Commencement: {commencement_date}, End: {end_date}, Total lessors: {len(lessors)}")
        
        # Calculate expected number of months
        expected_months = ((end_date.year - commencement_date.year) * 12) + (end_date.month - commencement_date.month) + 1
        print(f"[DEBUG] Expected months to generate: {expected_months}")
        
        while current_date <= end_date:
            print(f"[DEBUG] Processing month {month_num + 1}: current_date={current_date}, month_year={current_date.year}-{current_date.month:02d}")
            month = current_date.month
            year = current_date.year
            # rent_date is the first day of each month
            rent_date = pd.Timestamp(year, month, 1).date()
            month_year = f"{year}-{month:02d}"  # Keep for backward compatibility in some places
            
            # Calculate payment_date based on first_payment_date and payment_frequency
            period_num = month_num + 1
            payment_date = calculate_payment_date(period_num)
            
            # Calculate year number (for yearly increase)
            years_passed = (current_date.year - commencement_date.year) + \
                          ((current_date.month - commencement_date.month) / 12.0)
            
            # Get rent_amount from contract (for Fixed and ROU contracts)
            contract_rent_amount = float(contract_row.get('rent_amount', 0) or 0)
            _is_tax_val = str(contract_row.get('is_tax_added', 0) or 0).strip().lower()
            if contract_type == "ROU" and _is_tax_val in ("1", "true", "yes", "y"):
                contract_rent_amount *= 1.01
            
            # For Fixed and ROU contracts, calculate monthly rent amount with yearly increase
            # For Revenue Share contracts, yearly increase is only applied to minimum (rev_min), not to rent_amount
            if contract_type == "Fixed" or contract_type == "ROU":
                if contract_rent_amount > 0:
                    # Apply yearly increase based on type
                    if yearly_increase_type == "Fixed Amount Increased":
                        # Fixed amount: add fixed_amount * years_passed
                        rent_amount = contract_rent_amount + (yearly_increase_fixed_amount * int(years_passed))
                    else:
                        # Percentage increase: default yearly compounding, or optional period-override section.
                        if inc_mode in ("all", "specific", "year_rules"):
                            rent_amount = apply_period_override(contract_rent_amount, period_num, int(years_passed) + 1)
                        else:
                            rent_amount = contract_rent_amount * ((1 + yearly_increase_pct / 100) ** int(years_passed))
                else:
                    # If no rent_amount set, use 0
                    rent_amount = 0
            else:
                # For Revenue Share contracts, rent_amount will be calculated from revenue (no yearly increase on rent_amount)
                rent_amount = None
            
            # For Revenue Share contracts, apply yearly increase ONLY to rev_min (not to rent_amount)
            if contract_type == "Revenue Share":
                if rev_min > 0:
                    # Apply yearly increase based on type
                    if yearly_increase_type == "Fixed Amount Increased":
                        # Fixed amount: add fixed_amount * years_passed
                        rev_min_with_increase = rev_min + (yearly_increase_fixed_amount * int(years_passed))
                    else:
                        # Percentage increase: default yearly compounding, or optional period-override section.
                        if inc_mode in ("all", "specific", "year_rules"):
                            rev_min_with_increase = apply_period_override(rev_min, period_num, int(years_passed) + 1)
                        else:
                            rev_min_with_increase = rev_min * ((1 + yearly_increase_pct / 100) ** int(years_passed))
                else:
                    rev_min_with_increase = rev_min
            else:
                # For Fixed and ROU contracts, use original rev_min (yearly increase is on rent_amount, not rev_min)
                rev_min_with_increase = rev_min
            
            # Get sales amount from store_monthly_sales_df if available (join by store_id and month)
            # Use net_sales or total_sales based on contract's sales_type field
            revenue_amount = ""
            actual_revenue = None
            sales_type = str(contract_row.get('sales_type', 'Net') or 'Net').strip()
            use_net_sales = (sales_type.lower() == 'net')
            
            if store_monthly_sales_df is not None and not store_monthly_sales_df.empty and asset_or_store_id:
                # Match by store_id and rent_date (first day of month, same format as distribution tables)
                revenue_match = store_monthly_sales_df[
                    (store_monthly_sales_df['store_id'] == str(asset_or_store_id)) & 
                    (pd.to_datetime(store_monthly_sales_df['rent_date'], errors='coerce').dt.date == rent_date)
                ]
                if not revenue_match.empty:
                    # Use net_sales or total_sales based on sales_type
                    if use_net_sales:
                        revenue_amount = str(revenue_match.iloc[0].get('net_sales', ''))
                    else:
                        revenue_amount = str(revenue_match.iloc[0].get('total_sales', ''))
                    try:
                        actual_revenue = float(revenue_amount) if revenue_amount else None
                    except (ValueError, TypeError):
                        actual_revenue = None
            
            # For Revenue Share contracts, calculate rent based on revenue
            # IMPORTANT: Calculate rent_amount regardless of free months - free months will apply discount later
            if contract_type == "Revenue Share":
                if actual_revenue is not None and actual_revenue > 0:
                    # Step 1: Calculate base revenue share as percentage of sales
                    base_share = actual_revenue * (rev_share_pct / 100)
                    
                    # Step 2: Apply minimum guarantee
                    # If calculated share is below minimum, use minimum amount
                    if base_share < rev_min_with_increase:
                        rent_amount = rev_min_with_increase
                    # Step 3: Apply maximum threshold rule
                    elif base_share <= rev_max:
                        # If calculated share is between min and max, use calculated share
                        rent_amount = base_share
                    else:
                        # If calculated share exceeds maximum threshold, apply tiered calculation:
                        # - The maximum threshold amount remains fixed
                        # - Calculate remaining sales above the sales equivalent of the threshold
                        # - Apply reduced percentage to remaining sales
                        # - Final = max + (remaining_sales * reduced_pct)
                        
                        # Calculate the sales amount that corresponds to the maximum threshold
                        sales_at_max = rev_max / (rev_share_pct / 100) if rev_share_pct > 0 else rev_max
                        
                        # Calculate remaining sales above the threshold
                        remaining_sales = actual_revenue - sales_at_max
                        
                        # Apply reduced percentage to remaining sales
                        additional_share = remaining_sales * (rev_share_after_max_pct / 100)
                        
                        # Final revenue share = max threshold + additional share from remaining sales
                        rent_amount = rev_max + additional_share
                else:
                    # No revenue data available, use minimum guarantee
                    rent_amount = rev_min_with_increase if rev_min_with_increase > 0 else 0
            else:
                # For Fixed contracts, rent_amount is already calculated above
                pass
            
            # Store original rent_amount before any modifications (for discount calculation)
            original_rent_amount = rent_amount if rent_amount is not None else 0

            yearly_increase_amt = compute_distribution_yearly_increase_amount(
                contract_type,
                yearly_increase_type,
                yearly_increase_pct,
                yearly_increase_fixed_amount,
                contract_rent_amount,
                rev_min,
                years_passed,
                inc_mode,
                apply_period_override,
                period_num,
            )
            
            # Calculate discount_amount (for free months) - applies to both Fixed and Revenue Share
            # Free months apply to the specified period_num regardless of revenue or rent calculation
            discount = 0.0
            discount_amount_per_month = 0.0
            if (contract_type == "Fixed" or contract_type == "Revenue Share") and period_num in free_months:
                # This is a free month: discount equals the original rent amount (makes rent = 0)
                # This applies regardless of whether revenue exists or rent is min/max
                discount = -original_rent_amount
                discount_amount_per_month = original_rent_amount
            
            # Calculate advanced_amount used this month (for Fixed contracts)
            advanced_amount_per_month = 0.0
            # IMPORTANT: advance is only applied in NON-free months
            if contract_type == "Fixed" and period_num not in free_months and advance_payment_remaining > 0 and original_rent_amount > 0:
                # Calculate how much advance payment is used this month
                if advance_payment_remaining >= original_rent_amount:
                    # Advance payment covers full rent
                    advanced_amount_per_month = original_rent_amount
                    advance_payment_remaining -= original_rent_amount
                else:
                    # Advance payment partially covers rent
                    advanced_amount_per_month = advance_payment_remaining
                    advance_payment_remaining = 0
            
            # Revenue Share: prepaid advance in distribution (chronological or selected periods only)
            advanced_amount_per_month_rs = 0.0
            if (
                contract_type == "Revenue Share"
                and rs_mode in ("chronological", "periods")
                and period_num not in free_months
                and original_rent_amount > 0
                and rs_advance_remaining > 0
            ):
                if rs_mode == "periods" and period_num not in advance_months_rs:
                    pass
                else:
                    if rs_advance_remaining >= original_rent_amount:
                        advanced_amount_per_month_rs = original_rent_amount
                        rs_advance_remaining -= original_rent_amount
                    else:
                        advanced_amount_per_month_rs = rs_advance_remaining
                        rs_advance_remaining = 0.0
            
            # ROU-specific calculations (per month, before lessor loop)
            rou_opening_liability = None
            rou_interest = None
            rou_principal_reduction = None
            rou_closing_liability = None
            rou_depreciation = None
            rou_nbv = None
            
            if contract_type == "ROU":
                # Calculate ROU values for this month
                rou_opening_liability = lease_liability if lease_liability is not None else 0
                
                # Calculate monthly interest on lease liability
                rou_interest = rou_opening_liability * rou_monthly_discount_rate if rou_monthly_discount_rate else 0
                
                # Payment is the rent_amount for this month
                payment = rent_amount if rent_amount else 0
                
                # Principal reduction = payment - interest
                rou_principal_reduction = payment - rou_interest
                
                # Closing liability = opening - principal reduction
                rou_closing_liability = rou_opening_liability - rou_principal_reduction
                
                # Calculate months passed for ROU NBV (month_num is 0-indexed, so add 1)
                months_passed = month_num + 1
                rou_nbv = rou_initial_pv - (rou_monthly_depreciation * months_passed) if rou_initial_pv else 0
                rou_depreciation = rou_monthly_depreciation
                
                # Update lease liability for next month
                lease_liability = rou_closing_liability
            
            # Create row for each lessor
            # Wrap each lessor iteration in try-except to ensure one lessor's error doesn't stop the month
            for lessor in lessors:
                try:
                    lessor_id = lessor.get('id', '')
                    lessor_name = lessor.get('name', '')
                    lessor_share_pct = float(lessor.get('share', 0) or 0)
                    
                    # Get lessor name from lessors_df if available and check tax_exempted status
                    lessor_tax_exempted = False
                    if lessor_id:
                        lessor_row = lessors_df[lessors_df['id'] == str(lessor_id)]
                        if not lessor_row.empty:
                            lessor_name = lessor_row.iloc[0].get('name', lessor_name)
                            lessor_tax_exempted = bool(int(lessor_row.iloc[0].get('tax_exempted', 0) or 0))
                    
                    # Initialize variables for all contract types
                    lessor_discount_amount = 0.0
                    lessor_discount = 0.0  # Revenue Share: negative adjustment to due; storage uses positive waiver in discount_amount
                    lessor_advanced_amount = 0.0  # Fixed / Revenue Share advance column
                    withholding = 0.0
                    # holding_tax_amount removed from distribution; withholding now handled via payments
                    
                    # Determine withholding exemption based on lessor withholding periods.
                    # IMPORTANT: exemption is evaluated per payment period, not only at commencement.
                    # This check happens for EACH month independently - it does NOT stop generation early.
                    # CRITICAL: This logic must NEVER cause the loop to stop - it only sets withholding percentage.
                    withholding_pct_for_lessor = 0.0
                    
                    # Always initialize to default withholding first (will be overridden if exempt)
                    if lessor_id:
                        withholding_pct_for_lessor = default_withholding_pct
                    
                    try:
                        # Ensure payment_date is valid - use current_date as fallback if needed
                        payment_date_for_check = payment_date if payment_date is not None else current_date
                        
                        # Safely get periods dataframe - handle case where it doesn't exist
                        try:
                            lwp_df = st.session_state.get(
                                "lessor_withholding_periods_df",
                                pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS),
                            )
                        except Exception:
                            lwp_df = pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS)
                        
                        # LOG: Check if periods dataframe exists and has data
                        lwp_df_exists = lwp_df is not None
                        lwp_df_has_rows = not lwp_df.empty if lwp_df_exists else False
                        print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: lwp_df_exists={lwp_df_exists}, lwp_df_has_rows={lwp_df_has_rows}")
                        
                        # Only check exemption if we have a lessor_id AND periods dataframe has data
                        if lessor_id and lwp_df_exists and lwp_df_has_rows:
                            try:
                                periods = lwp_df[lwp_df["lessor_id"] == str(lessor_id)]
                                period_count = len(periods)
                                print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: Found {period_count} exempt period(s) in dataframe")
                                
                                exempt = False
                                
                                # Only check periods if we found any for this lessor
                                if period_count > 0:
                                    # Convert payment_date to date for comparison
                                    try:
                                        payment_date_as_date = pd.to_datetime(payment_date_for_check).date()
                                        print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: Checking payment_date={payment_date_as_date}")
                                    except Exception:
                                        # If conversion fails, use current_date as fallback
                                        payment_date_as_date = pd.to_datetime(current_date).date()
                                        print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: Using fallback payment_date={payment_date_as_date}")
                                    
                                    # Check each period
                                    # CRITICAL: Use period_start_date and period_end_date to avoid shadowing the outer end_date variable
                                    for idx, p in periods.iterrows():
                                        try:
                                            period_start_date = pd.to_datetime(p.get("start_date"))
                                            period_end_date = pd.to_datetime(p.get("end_date"))
                                            if pd.notna(period_start_date) and pd.notna(period_end_date):
                                                # Use the calculated payment_date for this period when checking exemption
                                                # Convert all to date objects for consistent comparison
                                                period_start_date_as_date = period_start_date.date()
                                                period_end_date_as_date = period_end_date.date()
                                                
                                                # LOG: Each period being checked
                                                print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: Checking period {period_start_date_as_date} to {period_end_date_as_date}")
                                                
                                                if period_start_date_as_date <= payment_date_as_date <= period_end_date_as_date:
                                                    exempt = True
                                                    print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: EXEMPT (payment_date {payment_date_as_date} is within period)")
                                                    break
                                                else:
                                                    print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: NOT exempt for this period (payment_date {payment_date_as_date} not in {period_start_date_as_date} to {period_end_date_as_date})")
                                        except Exception as period_err:
                                            # Skip this period if there's an error parsing dates
                                            print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: Error parsing period dates: {period_err}")
                                            continue
                                    
                                    # Update withholding based on exemption status
                                    if exempt:
                                        withholding_pct_for_lessor = 0.0
                                        print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: EXEMPT, withholding=0%")
                                    else:
                                        withholding_pct_for_lessor = default_withholding_pct
                                        print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: NOT exempt, applying {default_withholding_pct}% withholding")
                                else:
                                    # No periods found for this lessor - use default withholding
                                    withholding_pct_for_lessor = default_withholding_pct
                                    print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: No periods found for this lessor, applying default {default_withholding_pct}% withholding")
                            except Exception as period_lookup_err:
                                # Error looking up periods - use default withholding
                                print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: Error looking up periods: {period_lookup_err}")
                                withholding_pct_for_lessor = default_withholding_pct
                        else:
                            # No periods dataframe or no lessor_id - use default withholding
                            if lessor_id:
                                withholding_pct_for_lessor = default_withholding_pct
                                print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: No periods dataframe or empty, applying default {default_withholding_pct}% withholding")
                            else:
                                withholding_pct_for_lessor = 0.0
                                print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: No lessor_id, withholding=0%")
                    except Exception as e:
                        # Fallback to default if anything goes wrong - DO NOT stop generation
                        # Log error but continue - this is critical to ensure loop continues
                        print(f"[DEBUG] ERROR: Month {month_year}, Lessor {lessor_id}: Exception in exemption check: {e}")
                        import traceback
                        print(traceback.format_exc())
                        # Always set a safe default - never leave it unset
                        if lessor_id:
                            withholding_pct_for_lessor = default_withholding_pct
                        else:
                            withholding_pct_for_lessor = 0.0
                        print(f"[DEBUG] Month {month_year}, Lessor {lessor_id}: Using fallback withholding={withholding_pct_for_lessor}%")

                    if contract_type == "Fixed":
                        # For Fixed contracts:
                        # 1. Calculate discount_amount per lessor (from free months)
                        lessor_discount_amount = (discount_amount_per_month * lessor_share_pct / 100) if discount_amount_per_month > 0 else 0.0
                        
                        # 2. Calculate advanced_amount per lessor (from advance payment)
                        lessor_advanced_amount = (advanced_amount_per_month * lessor_share_pct / 100) if advanced_amount_per_month > 0 else 0.0
                        
                        # 3. Calculate lessor_due_amount = (original_rent * share_pct) - discount_amount - advanced_amount
                        lessor_original_rent = (original_rent_amount * lessor_share_pct / 100)
                        lessor_due_amount = lessor_original_rent - lessor_discount_amount - lessor_advanced_amount
                        
                        # 4. Calculate withholding on lessor's share of original rent (based on per-lessor periods)
                        # IMPORTANT: If lessor_due_amount is 0, withholding must be 0
                        if lessor_due_amount <= 0:
                            withholding = 0.0
                        elif withholding_pct_for_lessor > 0 and original_rent_amount > 0:
                            withholding = lessor_original_rent * (withholding_pct_for_lessor / 100)
                        else:
                            withholding = 0.0
                        
                        # 5. Calculate tax amount (on the due amount after discount and advance)
                        tax_amount = (lessor_due_amount * tax_pct / 100) if lessor_due_amount > 0 else 0
                        
                        # 6. Amount after tax = due_amount + tax - withholding
                        amount_after_tax = lessor_due_amount + tax_amount - withholding
                    elif contract_type == "Revenue Share":
                        # Revenue Share - calculate based on rent_amount (which is now calculated from revenue)
                        lessor_due_amount_base = (rent_amount * lessor_share_pct / 100) if rent_amount else 0
                        # Apply free-month waiver (same as Fixed: discount is -original_rent_amount at contract level)
                        lessor_discount = (discount * lessor_share_pct / 100)
                        lessor_advanced_amount = (
                            (advanced_amount_per_month_rs * lessor_share_pct / 100.0)
                            if advanced_amount_per_month_rs > 0
                            else 0.0
                        )
                        lessor_due_amount = lessor_due_amount_base + lessor_discount - lessor_advanced_amount
                        
                        # Calculate tax amount (on the base amount before discount)
                        tax_amount = (lessor_due_amount_base * tax_pct / 100) if lessor_due_amount_base else 0
                        
                        # Amount after tax = due_amount (which includes discount) + tax
                        amount_after_tax = lessor_due_amount + tax_amount
                    elif contract_type == "ROU":
                        # For ROU, lessor amounts are typically not calculated the same way
                        # But we'll keep the structure for consistency
                        lessor_due_amount = None
                        tax_amount = None
                        amount_after_tax = None
                    else:
                        # Other types - amounts are empty
                        lessor_due_amount = None
                        tax_amount = None
                        amount_after_tax = None
                    
                    # Calculate service amounts for this month (with yearly increase if applicable)
                    service_amounts = {}
                    for service_name, service_data in contract_services.items():
                        base_amount = service_data['amount']
                        service_yearly_increase = service_data['yearly_increase_pct']
                        if service_yearly_increase > 0 and base_amount > 0:
                            service_amount = base_amount * ((1 + service_yearly_increase / 100) ** int(years_passed))
                        else:
                            service_amount = base_amount
                        service_amounts[service_name] = service_amount
                    
                    _disc_for_storage = 0.0
                    if contract_type == "Fixed":
                        _disc_for_storage = lessor_discount_amount
                    elif contract_type == "Revenue Share":
                        _disc_for_storage = max(0.0, -lessor_discount)

                    # Build distribution row (only IDs, names will be retrieved via JOINs)
                    dist_row = {
                        "contract_id": contract_id,
                        "rent_date": rent_date.strftime('%Y-%m-%d'),  # First day of month - always set
                        "lessor_id": lessor_id,
                        "asset_or_store_id": asset_or_store_id,
                        "rent_amount": str(round(original_rent_amount, 2)) if contract_type == "Fixed" else (str(round(rent_amount, 2)) if rent_amount is not None else ""),
                        "lessor_share_pct": str(lessor_share_pct),
                        "lessor_due_amount": str(round(lessor_due_amount, 2)) if lessor_due_amount is not None else "",
                        # tax_pct, tax_amount, amount_after_tax removed from distribution - now stored in payments table
                        "yearly_increase_amount": str(yearly_increase_amt),
                        "discount_amount": str(round(_disc_for_storage, 2)) if contract_type in ("Fixed", "Revenue Share") else "",
                        "advanced_amount": str(round(lessor_advanced_amount, 2)) if contract_type in ("Fixed", "Revenue Share") else "",
                        # withholding removed from distribution - now stored in payments table
                        "revenue_min": str(rev_min_with_increase),
                        "revenue_max": str(rev_max),
                        "revenue_amount": revenue_amount
                    }
                    
                    # Add ROU-specific columns (only for ROU contracts)
                    if contract_type == "ROU":
                        dist_row["opening_liability"] = str(rou_opening_liability) if rou_opening_liability is not None else ""
                        dist_row["interest"] = str(rou_interest) if rou_interest is not None else ""
                        dist_row["closing_liability"] = str(rou_closing_liability) if rou_closing_liability is not None else ""
                        dist_row["rou_depreciation"] = str(rou_depreciation) if rou_depreciation is not None else ""
                        # ROU date columns - rent_date is already set above, keep it
                        dist_row["period"] = ""
                        # rent_date is already set in dist_row above, don't overwrite it
                        if "rent_date" not in dist_row or not dist_row["rent_date"]:
                            dist_row["rent_date"] = rent_date.strftime('%Y-%m-%d') if rent_date else ""
                        dist_row["lease_accrual"] = ""
                        dist_row["pv_of_lease_payment"] = ""
                        dist_row["cost_center"] = ""
                    else:
                        dist_row["opening_liability"] = ""
                        dist_row["interest"] = ""
                        dist_row["closing_liability"] = ""
                        dist_row["rou_depreciation"] = ""
                        dist_row["period"] = ""
                        # rent_date is already set in dist_row above, don't overwrite it
                        if "rent_date" not in dist_row or not dist_row["rent_date"]:
                            dist_row["rent_date"] = rent_date.strftime('%Y-%m-%d') if rent_date else ""
                        dist_row["lease_accrual"] = ""
                        dist_row["pv_of_lease_payment"] = ""
                        dist_row["cost_center"] = ""
                    
                    # Add service amounts as columns
                    for service_name, service_amount in service_amounts.items():
                        # Sanitize service name for column name (replace spaces with underscores, remove special chars)
                        col_name = f"service_{service_name.replace(' ', '_').replace('-', '_')}"
                        dist_row[col_name] = str(service_amount)
                    
                    distribution_rows.append(dist_row)
                except Exception as lessor_error:
                    # If ANY error occurs for this lessor, log it but continue to next lessor
                    # This ensures one lessor's error doesn't stop the entire month from being generated
                    print(f"Warning: Error processing lessor {lessor_id} for month {month_year}: {lessor_error}")
                    import traceback
                    print(traceback.format_exc())
                    # Continue to next lessor - do NOT break or return
                    continue
            
            # LOG: How many rows created for this month
            rent_date_str = rent_date.strftime('%Y-%m-%d')
            rows_this_month = len([r for r in distribution_rows if r.get('rent_date') == rent_date_str])
            print(f"[DEBUG] Month {month_year}: Created {rows_this_month} distribution row(s) for {len(lessors)} lessor(s)")
            
            # CRITICAL: Move to next month - ALWAYS execute this, regardless of:
            # - Exemption status
            # - Whether periods exist
            # - Any errors in processing
            # - Number of rows created
            # This ensures the loop continues until end_date
            try:
                current_date = current_date + pd.DateOffset(months=1)
                month_num += 1
                print(f"[DEBUG] Advanced to next month: new current_date={current_date}, month_num={month_num}, still <= end_date? {current_date <= end_date}")
            except Exception as date_err:
                # If date advancement fails, log and break to avoid infinite loop
                print(f"[DEBUG] ERROR: Failed to advance date: {date_err}")
                break
        
        # Final summary
        actual_months_generated = month_num
        print(f"[DEBUG] ===== FINISHED DISTRIBUTION GENERATION =====")
        print(f"[DEBUG] Contract: {contract_id}, Type: {contract_type}")
        print(f"[DEBUG] Expected months: {expected_months}, Actual months generated: {actual_months_generated}")
        print(f"[DEBUG] Total rows created: {len(distribution_rows)}")
        print(f"[DEBUG] Final current_date: {current_date}, End date: {end_date}")
        if actual_months_generated < expected_months:
            print(f"[DEBUG] WARNING: Generated fewer months than expected! This may indicate an early stop.")
        else:
            print(f"[DEBUG] SUCCESS: Generated all expected months.")
        
        # Revenue Share: spread prepaid advance across all months proportional to calculated due
        if contract_type == "Revenue Share" and rs_mode == "spread_proportional":
            try:
                adv_total = float(contract_row.get("rev_share_payment_advance") or 0)
            except (TypeError, ValueError):
                adv_total = 0.0
            if adv_total > 0 and distribution_rows:
                total_due = 0.0
                for r in distribution_rows:
                    try:
                        total_due += float(r.get("lessor_due_amount") or 0)
                    except (TypeError, ValueError):
                        pass
                if total_due > 0:
                    for r in distribution_rows:
                        try:
                            d = float(r.get("lessor_due_amount") or 0)
                        except (TypeError, ValueError):
                            d = 0.0
                        share_adv = adv_total * (d / total_due)
                        r["advanced_amount"] = str(round(share_adv, 2))
                        r["lessor_due_amount"] = str(round(d - share_adv, 2))
            
    except Exception as e:
        st.error(f"Error generating distribution: {str(e)}")
    
    return distribution_rows

def create_payment_records_from_distribution(contract_id, contract_type, contract_row, distribution_rows=None, service_distribution_rows=None):
    """Create payment records in the payments table for a contract.
    
    Prefer using in-memory distribution rows when provided (from generate/regenerate),
    otherwise fall back to loading from the DB tables.
    """
    from core.db import insert_payment, get_db_connection, execute_query
    from mysql.connector import Error
    import pandas as pd
    
    try:
        # Get DB connection (for optional DB loads and service distributions)
        connection = get_db_connection()
        if connection is None:
            return False
        cursor = connection.cursor(dictionary=True)
        
        # Get distribution table name
        dist_table = get_distribution_table(contract_type)

        time.sleep(0.5)
        use_memory = distribution_rows is not None and len(distribution_rows) > 0
        if use_memory:
            dist_records = list(distribution_rows)
            print(f"[DEBUG] Using in-memory distribution_rows ({len(dist_records)} records) for contract {contract_id}")
        else:
            dist_records = []
            try:
                cursor.execute(
                    f"SELECT * FROM `{dist_table}` WHERE contract_id = %s ORDER BY rent_date, id",
                    (str(contract_id),),
                )
                raw_recs = cursor.fetchall() or []
                if raw_recs:
                    sample = raw_recs[0]
                    if sample.get("lessors_json"):
                        for rec in raw_recs:
                            lj = rec.get("lessors_json")
                            if lj:
                                try:
                                    base = {k: v for k, v in rec.items() if k != "lessors_json"}
                                    for p in json.loads(lj):
                                        dist_records.append({**base, **p})
                                except Exception:
                                    dist_records.append(rec)
                            else:
                                dist_records.append(rec)
                    elif str(sample.get("lessor_id") or "").strip():
                        dist_records = list(raw_recs)
                    else:
                        dist_records = rebuild_distribution_rows_for_payments(
                            contract_id, contract_type, contract_row, cursor
                        )
                print(f"[DEBUG] Loaded {len(dist_records)} distribution line(s) for contract {contract_id}")
            except Exception as reload_err:
                print(f"[ERROR] Could not load distributions from DB: {reload_err}")
                import traceback
                traceback.print_exc()
                dist_records = []

        # Get contract details for payment date calculation and tax
        first_payment_date = pd.to_datetime(contract_row.get('first_payment_date') or contract_row['commencement_date'])
        payment_frequency = str(contract_row.get('payment_frequency', 'Monthly') or 'Monthly').strip()
        tax_pct = float(contract_row.get('tax', 0) or 0)
        
        # Helper function to calculate payment_date for a given period
        def calculate_payment_date(period_num):
            """Calculate payment date based on first_payment_date and payment_frequency"""
            if payment_frequency == "Yearly":
                months = 12 * ((period_num - 1) // 12)
            elif payment_frequency == "Quarter":
                months = 3 * ((period_num - 1) // 3)
            elif payment_frequency == "2 Months":
                months = 2 * ((period_num - 1) // 2)
            else:
                # Monthly (default)
                months = (period_num - 1)
            ts = pd.Timestamp(first_payment_date) + pd.DateOffset(months=months)
            if str(contract_type).strip() == "Revenue Share":
                month_end = pd.Timestamp(ts.year, ts.month, 1) + pd.offsets.MonthEnd(0)
                return month_end.to_pydatetime()
            return ts.replace(day=1).to_pydatetime()
        
        # Delete existing payment records for this contract first (for regenerate)
        delete_query = "DELETE FROM payments WHERE contract_id = %s"
        cursor.execute(delete_query, (str(contract_id),))
        connection.commit()

        # Pre-load lessor withholding periods
        lwp_df = st.session_state.get(
            "lessor_withholding_periods_df",
            pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS),
        )
        default_withholding_pct = 3.0

        # Parse free months for this contract (used for service payments, distribution already reflects this for Fixed)
        free_months = set()
        free_months_str = str(contract_row.get("free_months", "") or "").strip()
        if free_months_str:
            try:
                free_months = {
                    int(x.strip())
                    for x in free_months_str.split(",")
                    if x.strip().isdigit()
                }
            except Exception:
                free_months = set()

        # Revenue Share: prepaid advance — only deduct at payment layer if mode is "none" (legacy payment-only).
        rs_mode_pay = "none"
        if str(contract_type).strip() == "Revenue Share":
            rs_mode_pay = str(contract_row.get("rev_share_advance_mode") or "none").strip().lower()
            if rs_mode_pay in ("", "legacy"):
                rs_mode_pay = "none"
        rs_pay_advance_remaining = 0.0
        dist_iter = dist_records
        if str(contract_type).strip() == "Revenue Share":
            if rs_mode_pay == "none":
                try:
                    rs_pay_advance_remaining = max(
                        0.0,
                        float(contract_row.get("rev_share_payment_advance") or 0),
                    )
                except (TypeError, ValueError):
                    rs_pay_advance_remaining = 0.0
            if rs_pay_advance_remaining > 0:

                def _rs_pay_adv_sort_key(rec):
                    rd = rec.get("rent_date")
                    try:
                        if rd is None or str(rd).strip() == "":
                            return ("9999-12-31", str(rec.get("lessor_id") or ""))
                        if hasattr(rd, "strftime"):
                            ds = rd.strftime("%Y-%m-%d")
                        else:
                            ds = pd.to_datetime(rd).strftime("%Y-%m-%d")
                    except Exception:
                        ds = "9999-12-31"
                    return (ds, str(rec.get("lessor_id") or ""))

                dist_iter = sorted(dist_records, key=_rs_pay_adv_sort_key)

        # Create payment records for each contract distribution record
        payment_count = 0
        for dist_record in dist_iter:
            lessor_id = dist_record.get('lessor_id', '')
            lessor_due_amount_str = dist_record.get('lessor_due_amount', '')
            rent_date_val = dist_record.get('rent_date', '')
            
            # Skip if no lessor; amount can be zero or empty (we still create a payment row)
            if not lessor_id:
                continue
            
            # Normalize rent_date to string format (YYYY-MM-DD) for lookup
            try:
                if rent_date_val:
                    if isinstance(rent_date_val, str):
                        rent_date_str = rent_date_val.strip()
                    elif hasattr(rent_date_val, 'strftime'):  # date or datetime object
                        rent_date_str = rent_date_val.strftime('%Y-%m-%d')
                    elif hasattr(rent_date_val, 'date'):  # datetime object
                        rent_date_str = rent_date_val.date().strftime('%Y-%m-%d')
                    else:
                        try:
                            rent_date_str = pd.to_datetime(rent_date_val).strftime('%Y-%m-%d')
                        except:
                            rent_date_str = str(rent_date_val).strip()
                else:
                    print(f"[ERROR] rent_date is empty for contract {contract_id}, lessor {lessor_id}")
                    continue
            except Exception as date_err:
                print(f"[ERROR] Could not normalize rent_date_val {rent_date_val} (type: {type(rent_date_val)}): {date_err}")
                continue
            
            # Parse numeric base values from distribution row
            try:
                lessor_due = float(lessor_due_amount_str) if (lessor_due_amount_str is not None and lessor_due_amount_str != "") else 0.0
            except (ValueError, TypeError):
                # If cannot parse, skip this record
                continue

            discount_amount = 0.0
            advance_amount = 0.0
            try:
                if 'discount_amount' in dist_record and dist_record.get('discount_amount') not in (None, "", "None"):
                    discount_amount = float(dist_record.get('discount_amount') or 0.0)
            except (ValueError, TypeError):
                discount_amount = 0.0
            try:
                if 'advanced_amount' in dist_record and dist_record.get('advanced_amount') not in (None, "", "None"):
                    advance_amount = float(dist_record.get('advanced_amount') or 0.0)
            except (ValueError, TypeError):
                advance_amount = 0.0

            pay_adv_deduct = 0.0
            if rs_pay_advance_remaining > 0 and lessor_due > 0:
                pay_adv_deduct = min(lessor_due, rs_pay_advance_remaining)
                rs_pay_advance_remaining -= pay_adv_deduct
            lessor_due_for_payment = max(0.0, lessor_due - pay_adv_deduct)

            # Due / tax / withholding use payment-layer amounts (includes RS payment advance).
            due_amount = lessor_due_for_payment

            # Calculate payment date from rent_date (rent_date is first day of month)
            try:
                rent_date_obj = pd.to_datetime(rent_date_str)
                # Calculate period number from rent_date
                period_num = (rent_date_obj.year - first_payment_date.year) * 12 + (rent_date_obj.month - first_payment_date.month) + 1
                payment_date = calculate_payment_date(period_num)
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not parse rent_date '{rent_date_str}': {e}")
                continue

            # Effective base for tax/withholding and net cash (after dist discount/advance + RS payment advance)
            effective_base = lessor_due_for_payment
            if effective_base < 0:
                effective_base = 0.0

            # Compute tax and withholding based on payment date and lessor periods
            # Tax is calculated in payments table, not from distribution
            tax_amount = effective_base * tax_pct / 100.0 if effective_base > 0 and tax_pct > 0 else 0.0
            withholding_pct_for_lessor = 0.0
            
            # Determine withholding exemption based on lessor withholding periods
            # IMPORTANT: exemption is evaluated per payment period, not only at commencement.
            # This check happens for EACH payment independently - it does NOT stop generation early.
            # CRITICAL: This logic must NEVER cause the loop to stop - it only sets withholding percentage.
            
            # Always initialize to default withholding first (will be overridden if exempt)
            if lessor_id:
                withholding_pct_for_lessor = default_withholding_pct
                
                try:
                    # Ensure payment_date is valid - convert to date for comparison
                    try:
                        if isinstance(payment_date, pd.Timestamp):
                            payment_date_as_date = payment_date.date()
                        elif hasattr(payment_date, 'date'):
                            payment_date_as_date = payment_date.date()
                        elif isinstance(payment_date, str):
                            payment_date_as_date = pd.to_datetime(payment_date).date()
                        else:
                            payment_date_as_date = pd.to_datetime(payment_date).date()
                    except Exception:
                        # If conversion fails, use rent_date as fallback
                        try:
                            payment_date_as_date = pd.to_datetime(rent_date_str).date()
                        except:
                            print(f"[WARNING] Could not convert payment_date or rent_date to date for exemption check")
                            payment_date_as_date = None
                    
                    # Safely get periods dataframe - handle case where it doesn't exist
                    try:
                        lwp_df = st.session_state.get(
                            "lessor_withholding_periods_df",
                            pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS),
                        )
                    except Exception:
                        lwp_df = pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS)
                    
                    # LOG: Check if periods dataframe exists and has data
                    lwp_df_exists = lwp_df is not None
                    lwp_df_has_rows = not lwp_df.empty if lwp_df_exists else False
                    print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}, Payment date {payment_date_as_date}: lwp_df_exists={lwp_df_exists}, lwp_df_has_rows={lwp_df_has_rows}")
                    
                    # Only check exemption if we have a lessor_id AND periods dataframe has data AND valid payment_date
                    if payment_date_as_date and lwp_df_exists and lwp_df_has_rows:
                        try:
                            periods = lwp_df[lwp_df["lessor_id"] == str(lessor_id)]
                            period_count = len(periods)
                            print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: Found {period_count} exempt period(s) in dataframe")
                            
                            exempt = False
                            
                            # Only check periods if we found any for this lessor
                            if period_count > 0:
                                # Check each period
                                for _, p in periods.iterrows():
                                    try:
                                        # CRITICAL: Use period_start_date and period_end_date to avoid shadowing any outer variables
                                        period_start_date_str = p.get("start_date")
                                        period_end_date_str = p.get("end_date")
                                        
                                        if period_start_date_str and period_end_date_str:
                                            # Convert to date objects for comparison
                                            period_start_date_as_date = pd.to_datetime(period_start_date_str).date()
                                            period_end_date_as_date = pd.to_datetime(period_end_date_str).date()
                                            
                                            # Check if payment_date falls within this exemption period
                                            if period_start_date_as_date <= payment_date_as_date <= period_end_date_as_date:
                                                exempt = True
                                                print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: EXEMPT (payment_date {payment_date_as_date} is within period {period_start_date_as_date} to {period_end_date_as_date})")
                                                break
                                            else:
                                                print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: NOT exempt for this period (payment_date {payment_date_as_date} not in {period_start_date_as_date} to {period_end_date_as_date})")
                                    except Exception as period_err:
                                        # Skip this period if there's an error parsing dates
                                        print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: Error parsing period dates: {period_err}")
                                        continue
                                
                                # Update withholding based on exemption status
                                if exempt:
                                    withholding_pct_for_lessor = 0.0
                                    print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: EXEMPT, withholding=0%")
                                else:
                                    withholding_pct_for_lessor = default_withholding_pct
                                    print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: NOT exempt, applying {default_withholding_pct}% withholding")
                            else:
                                # No periods found for this lessor - use default withholding
                                withholding_pct_for_lessor = default_withholding_pct
                                print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: No periods found for this lessor, applying default {default_withholding_pct}% withholding")
                        except Exception as period_lookup_err:
                            # Error looking up periods - use default withholding
                            print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: Error looking up periods: {period_lookup_err}")
                            withholding_pct_for_lessor = default_withholding_pct
                    else:
                        # No periods dataframe or no lessor_id or invalid payment_date - use default withholding
                        if payment_date_as_date:
                            withholding_pct_for_lessor = default_withholding_pct
                            print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: No periods dataframe or empty, applying default {default_withholding_pct}% withholding")
                        else:
                            withholding_pct_for_lessor = default_withholding_pct
                            print(f"[WARNING] Payment creation - Contract {contract_id}, Lessor {lessor_id}: Invalid payment_date, applying default {default_withholding_pct}% withholding")
                except Exception as e:
                    # Fallback to default if anything goes wrong - DO NOT stop payment creation
                    # Log error but continue - this is critical to ensure payments are created
                    print(f"[DEBUG] ERROR: Payment creation - Contract {contract_id}, Lessor {lessor_id}: Exception in exemption check: {e}")
                    import traceback
                    print(traceback.format_exc())
                    # Always set a safe default - never leave it unset
                    withholding_pct_for_lessor = default_withholding_pct
                    print(f"[DEBUG] Payment creation - Contract {contract_id}, Lessor {lessor_id}: Using fallback withholding={withholding_pct_for_lessor}%")
            else:
                # No lessor_id - withholding is 0
                withholding_pct_for_lessor = 0.0
                print(f"[DEBUG] Payment creation - Contract {contract_id}: No lessor_id, withholding=0%")

            # IMPORTANT: If effective_base (lessor due amount) is 0, withholding must be 0
            if effective_base <= 0:
                withholding_amount = 0.0
            else:
                withholding_amount = effective_base * (withholding_pct_for_lessor / 100.0)
            payment_amount = effective_base + tax_amount - withholding_amount

            gross_line = lessor_due_for_payment + discount_amount + advance_amount
            rent_month_date = _rent_month_first_day(rent_date_str)

            if insert_payment(
                contract_id=contract_id,
                lessor_id=lessor_id,
                payment_date=payment_date,
                due_amount=effective_base,
                payment_amount=payment_amount,
                rent_month=rent_month_date,
                amount=gross_line,
                service_id=None,
                tax_pct=tax_pct,
                tax_amount=tax_amount,
                withholding_amount=withholding_amount,
                lessor_share_pct=dist_record.get("lessor_share_pct"),
            ):
                payment_count += 1

        # ------------------------------------------------------------------
        # Also create payment records for SERVICE distributions
        # ------------------------------------------------------------------
        time.sleep(0.5)
        use_svc_memory = service_distribution_rows is not None and len(service_distribution_rows) > 0
        if use_svc_memory:
            svc_records = list(service_distribution_rows)
            print(f"[DEBUG] Using in-memory service_distribution_rows ({len(svc_records)}) for contract {contract_id}")
        else:
            try:
                cursor.execute(
                    "SELECT * FROM service_distribution WHERE contract_id = %s ORDER BY rent_date, id",
                    (str(contract_id),),
                )
                raw_svc = cursor.fetchall()
                svc_records = []
                for rec in raw_svc:
                    sj = rec.get("services_json")
                    if sj:
                        try:
                            for item in json.loads(sj):
                                svc_records.append(
                                    {
                                        "contract_id": rec.get("contract_id"),
                                        "store_id": item.get("store_id", rec.get("store_id")),
                                        "store_name": item.get("store_name", rec.get("store_name")),
                                        "rent_date": rec.get("rent_date"),
                                        "service_id": item.get("service_id", ""),
                                        "service_name": item.get("service_name", ""),
                                        "amount": item.get("amount", "0"),
                                        "currency": item.get("currency") or rec.get("currency") or "",
                                    }
                                )
                        except Exception:
                            svc_records.append(rec)
                    else:
                        svc_records.append(rec)
                print(f"[DEBUG] Expanded {len(svc_records)} service distribution line(s) from DB for contract {contract_id}")
            except Exception as svc_reload_err:
                print(f"[ERROR] Could not load service_distribution from DB: {svc_reload_err}")
                import traceback
                traceback.print_exc()
                svc_records = []

        try:

            if svc_records:
                # Load service-lessor allocations for this contract
                svc_lessor_query = """
                    SELECT service_id, lessor_id, share_pct
                    FROM contract_service_lessors
                    WHERE contract_id = %s
                """
                cursor.execute(svc_lessor_query, (str(contract_id),))
                svc_lessor_rows = cursor.fetchall()

                # Group allocations by service_id
                svc_lessor_map = {}
                for r in svc_lessor_rows:
                    sid = str(r.get("service_id"))
                    if not sid:
                        continue
                    svc_lessor_map.setdefault(sid, []).append(r)

                for svc in svc_records:
                    service_id = str(svc.get("service_id", ""))
                    svc_amount_raw = svc.get("amount", "0")
                    try:
                        svc_amount = float(svc_amount_raw or 0)
                    except (ValueError, TypeError):
                        continue

                    if svc_amount <= 0:
                        continue

                    svc_rent_date = svc.get("rent_date", "")

                    # Calculate period number for this service row from rent_date
                    try:
                        if svc_rent_date:
                            # Parse rent_date (YYYY-MM-DD format)
                            if isinstance(svc_rent_date, str):
                                rent_date_parsed = pd.to_datetime(svc_rent_date)
                            elif hasattr(svc_rent_date, 'year'):
                                rent_date_parsed = pd.to_datetime(svc_rent_date)
                            else:
                                rent_date_parsed = pd.to_datetime(svc_rent_date)
                            
                            # Calculate period number: months from first_payment_date
                            period_num = (rent_date_parsed.year - first_payment_date.year) * 12 + (rent_date_parsed.month - first_payment_date.month) + 1
                        else:
                            continue
                    except (ValueError, TypeError) as e:
                        print(f"[ERROR] Could not parse rent_date {svc_rent_date} for service payment: {e}")
                        continue

                    svc_payment_date = calculate_payment_date(period_num)

                    # Get lessor allocations for this service
                    allocations = svc_lessor_map.get(service_id, [])
                    if not allocations:
                        # If no explicit service allocations, skip service payments for this row
                        continue

                    for alloc in allocations:
                        svc_lessor_id = alloc.get("lessor_id", "")
                        try:
                            svc_share_pct = float(alloc.get("share_pct", 0) or 0)
                        except (ValueError, TypeError):
                            svc_share_pct = 0

                        if not svc_lessor_id or svc_share_pct <= 0:
                            continue

                        svc_lessor_amount = svc_amount * (svc_share_pct / 100.0)
                        if svc_lessor_amount <= 0:
                            continue

                        # Compute tax/withholding/payment for service payments
                        svc_due_amount = float(svc_lessor_amount)

                        # Handle free months for services (Fixed contracts only):
                        # - In a free month, the entire service due is treated as discount, so payment = 0.
                        svc_discount_amount = 0.0
                        svc_advance_amount = 0.0
                        if contract_type == "Fixed" and period_num in free_months:
                            svc_discount_amount = svc_due_amount

                        svc_effective_base = svc_due_amount - svc_discount_amount - svc_advance_amount
                        if svc_effective_base < 0:
                            svc_effective_base = 0.0

                        # Tax on effective base
                        svc_tax_amount = svc_effective_base * tax_pct / 100.0 if svc_effective_base > 0 and tax_pct > 0 else 0.0

                        # Withholding is NOT applied for service payments (per requirement)
                        svc_withholding_amount = 0.0
                        svc_payment_amount = svc_effective_base + svc_tax_amount - svc_withholding_amount

                        svc_rent_month = _rent_month_first_day(svc_rent_date)
                        svc_gross_line = float(svc_lessor_amount)

                        payment_inserted = insert_payment(
                            contract_id=contract_id,
                            lessor_id=svc_lessor_id,
                            payment_date=svc_payment_date,
                            due_amount=svc_effective_base,
                            payment_amount=svc_payment_amount,
                            rent_month=svc_rent_month,
                            amount=svc_gross_line,
                            service_id=service_id,
                            tax_pct=tax_pct,
                            tax_amount=svc_tax_amount,
                            withholding_amount=svc_withholding_amount,
                            lessor_share_pct=str(svc_share_pct),
                        )
                        if payment_inserted:
                            print(f"[DEBUG] Created service payment: contract_id={contract_id}, service_id={service_id}, lessor_id={svc_lessor_id}, rent_month={svc_rent_month}, amount={svc_payment_amount}")
                        else:
                            print(f"[ERROR] Failed to insert service payment: contract_id={contract_id}, service_id={service_id}, lessor_id={svc_lessor_id}")
        except Exception as svc_e:
            # Log but don't fail the whole contract payments creation
            print(f"Error creating service payment records: {svc_e}")

        cursor.close()
        connection.close()
        return True
    except Exception as e:
        print(f"Error creating payment records: {e}")
        import traceback
        traceback.print_exc()
        if connection:
            try:
                connection.close()
            except:
                pass
        return False

def generate_service_distribution(contract_row, services_df, contract_services_df):
    """Generate monthly service distribution data for a contract"""
    service_distribution_rows = []
    
    try:
        contract_id = contract_row['id']
        asset_or_store_id = contract_row.get('asset_or_store_id', '')
        asset_or_store_name = contract_row.get('asset_or_store_name', '')
        commencement_date = pd.to_datetime(contract_row['commencement_date'])
        end_date = pd.to_datetime(contract_row['end_date'])
        
        # Get services for this contract
        contract_services = contract_services_df[contract_services_df['contract_id'] == contract_id]
        
        if contract_services.empty:
            return service_distribution_rows
        
        # Generate monthly periods
        current_date = commencement_date
        
        while current_date <= end_date:
            # rent_date is the first day of each month
            rent_date = pd.Timestamp(current_date.year, current_date.month, 1).date()
            
            # Calculate year number (for yearly increase)
            years_passed = (current_date.year - commencement_date.year) + \
                          ((current_date.month - commencement_date.month) / 12.0)
            
            # Process each service
            for _, cs_row in contract_services.iterrows():
                service_id = cs_row['service_id']
                base_amount = float(cs_row.get('amount', 0) or 0)
                yearly_increase_pct = float(cs_row.get('yearly_increase_pct', 0) or 0)
                
                # Get service name and currency
                service_row = services_df[services_df['id'] == service_id]
                if service_row.empty:
                    continue
                service_name = service_row.iloc[0]['name']
                service_currency = service_row.iloc[0].get('currency', 'EGP')
                
                # Apply yearly increase if configured
                if yearly_increase_pct > 0 and base_amount > 0:
                    service_amount = base_amount * ((1 + yearly_increase_pct / 100) ** int(years_passed))
                else:
                    service_amount = base_amount
                
                service_distribution_rows.append({
                    "contract_id": contract_id,
                    "store_id": asset_or_store_id,
                    "store_name": asset_or_store_name,
                    "rent_date": rent_date.strftime('%Y-%m-%d'),  # First day of month
                    "service_id": service_id,
                    "service_name": service_name,
                    "amount": str(service_amount),
                    "currency": service_currency
                })
            
            # Move to next month
            current_date = current_date + pd.DateOffset(months=1)
            
    except Exception as e:
        st.error(f"Error generating service distribution: {str(e)}")
    
    return service_distribution_rows

#
# Authentication/authorization removed from this tool.
#

#
# (auth removed)
#

def load_all():
    """Load all dataframes into session state"""
    st.session_state.lessors_df = load_df(LESSORS_TABLE, LESSORS_COLS)
    st.session_state.assets_df = load_df(ASSETS_TABLE, ASSETS_COLS)
    st.session_state.stores_df = load_df(STORES_TABLE, STORES_COLS)
    st.session_state.contracts_df = load_df(CONTRACTS_TABLE, CONTRACTS_COLS)
    st.session_state.contract_lessors_df = load_df(CONTRACT_LESSORS_TABLE, CONTRACT_LESSORS_COLS)
    st.session_state.services_df = load_df(SERVICES_TABLE, SERVICES_COLS)
    st.session_state.contract_services_df = load_df(CONTRACT_SERVICES_TABLE, CONTRACT_SERVICES_COLS)
    # Optional: contract-level service lessor allocations
    try:
        st.session_state.contract_service_lessors_df = load_df(CONTRACT_SERVICE_LESSORS_TABLE, CONTRACT_SERVICE_LESSORS_COLS)
    except Exception:
        # Older databases may not have this table yet; fail silently
        st.session_state.contract_service_lessors_df = pd.DataFrame(columns=CONTRACT_SERVICE_LESSORS_COLS)
    # Optional: lessor withholding periods
    try:
        st.session_state.lessor_withholding_periods_df = load_df(
            LESSOR_WITHHOLDING_PERIODS_TABLE, LESSOR_WITHHOLDING_PERIODS_COLS
        )
    except Exception:
        st.session_state.lessor_withholding_periods_df = pd.DataFrame(columns=LESSOR_WITHHOLDING_PERIODS_COLS)
    # Load distribution data from all contract type tables
    fixed_dist_df = load_df(CONTRACT_DISTRIBUTION_FIXED_TABLE, CONTRACT_DISTRIBUTION_FIXED_COLS)
    revenue_share_dist_df = load_df(CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE, CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS)
    rou_dist_df = load_df(CONTRACT_DISTRIBUTION_ROU_TABLE, CONTRACT_DISTRIBUTION_ROU_COLS)
    
    # Combine all distribution dataframes for backward compatibility
    all_dist_dfs = []
    if not fixed_dist_df.empty:
        all_dist_dfs.append(fixed_dist_df)
    if not revenue_share_dist_df.empty:
        all_dist_dfs.append(revenue_share_dist_df)
    if not rou_dist_df.empty:
        all_dist_dfs.append(rou_dist_df)
    
    if all_dist_dfs:
        st.session_state.contract_distribution_df = pd.concat(all_dist_dfs, ignore_index=True)
    else:
        st.session_state.contract_distribution_df = pd.DataFrame(columns=CONTRACT_DISTRIBUTION_COLS)
    st.session_state.store_monthly_sales_df = load_df(STORE_MONTHLY_SALES_TABLE, STORE_MONTHLY_SALES_COLS)
    st.session_state.service_distribution_df = load_df(SERVICE_DISTRIBUTION_TABLE, SERVICE_DISTRIBUTION_COLS)
    
    # Load authentication tables (optional - may not exist in older databases)
    try:
        st.session_state.users_df = load_df(USERS_TABLE, USERS_COLS)
    except Exception:
        st.session_state.users_df = pd.DataFrame(columns=USERS_COLS)
    try:
        st.session_state.roles_df = load_df(ROLES_TABLE, ROLES_COLS)
    except Exception:
        st.session_state.roles_df = pd.DataFrame(columns=ROLES_COLS)
    try:
        st.session_state.permissions_df = load_df(PERMISSIONS_TABLE, PERMISSIONS_COLS)
    except Exception:
        st.session_state.permissions_df = pd.DataFrame(columns=PERMISSIONS_COLS)
    try:
        st.session_state.role_permissions_df = load_df(ROLE_PERMISSIONS_TABLE, ROLE_PERMISSIONS_COLS)
    except Exception:
        st.session_state.role_permissions_df = pd.DataFrame(columns=ROLE_PERMISSIONS_COLS)
    try:
        st.session_state.user_roles_df = load_df(USER_ROLES_TABLE, USER_ROLES_COLS)
    except Exception:
        st.session_state.user_roles_df = pd.DataFrame(columns=USER_ROLES_COLS)
    try:
        st.session_state.action_logs_df = load_df(ACTION_LOGS_TABLE, ACTION_LOGS_COLS)
    except Exception:
        st.session_state.action_logs_df = pd.DataFrame(columns=ACTION_LOGS_COLS)
    
    if "contract_lessors" not in st.session_state:
        st.session_state.contract_lessors = []


def initialize_database():
    """Initialize database with default admin user and permissions"""
    try:
        # Import here to avoid circular imports
        from core.permissions import initialize_permissions
        from core.auth import hash_password
        import time
        
        # Initialize permissions
        initialize_permissions()
        
        # Check if admin user exists, if not create one
        try:
            users_df = load_df(USERS_TABLE, USERS_COLS)
            roles_df = load_df(ROLES_TABLE, ROLES_COLS)
            user_roles_df = load_df(USER_ROLES_TABLE, USER_ROLES_COLS)
            role_permissions_df = load_df(ROLE_PERMISSIONS_TABLE, ROLE_PERMISSIONS_COLS)
            
            # Create admin user if it doesn't exist
            admin_user_exists = not users_df.empty and not users_df[users_df['id'] == '1'].empty
            if not admin_user_exists:
                admin_data = {
                    'id': '1',
                    'email': 'admin@contracttool.com',
                    'password_hash': hash_password('admin123'),
                    'name': 'Administrator',
                    'is_active': 1,
                    'created_at': time.strftime("%Y-%m-%d %H:%M:%S")
                }
                insert_user(admin_data)
            
            # Create admin role if it doesn't exist
            admin_role_exists = not roles_df.empty and not roles_df[roles_df['id'] == '1'].empty
            if not admin_role_exists:
                admin_role_data = {
                    'id': '1',
                    'role_name': 'Administrator',
                    'description': 'Full system access',
                    'created_at': time.strftime("%Y-%m-%d %H:%M:%S")
                }
                insert_role(admin_role_data)
            
            # Assign admin.all permission to admin role if not already assigned
            admin_perm_exists = not role_permissions_df.empty and not role_permissions_df[
                (role_permissions_df['role_id'] == '1') & (role_permissions_df['permission_id'] == 'admin.all')
            ].empty
            if not admin_perm_exists:
                insert_role_permission('1', 'admin.all')
            
            # Assign admin role to admin user if not already assigned
            admin_user_role_exists = not user_roles_df.empty and not user_roles_df[
                (user_roles_df['user_id'] == '1') & (user_roles_df['role_id'] == '1')
            ].empty
            if not admin_user_role_exists:
                insert_user_role('1', '1')
        except Exception as e:
            # Table might not exist yet, that's okay
            print(f"Note: Could not initialize admin user (tables may not exist yet): {e}")

        try:
            from core.db import ensure_v2_distribution_payment_schema

            ensure_v2_distribution_payment_schema()
        except Exception as e:
            print(f"Note: Could not apply distribution/payment schema upgrades: {e}")
    except Exception as e:
        print(f"Error initializing database: {e}")

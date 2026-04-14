# dashboard.py
# Dashboard/home page with statistics
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from core.utils import *
from conf.constants import *
from core.db import *
from core.permissions import require_permission, has_permission

# Must match app.py sidebar / routing exactly (avoid encoding drift in editors)
_NAV_CONTRACTS = "\U0001f4c4 Contracts"
_NAV_LESSORS = "\U0001f465 Lessors"
_NAV_DISTRIBUTION = "\U0001f4ca Distribution"


def _parse_amount(val) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0.0
    s = str(val).strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _normalize_currency(c) -> str:
    if c is None or (isinstance(c, float) and np.isnan(c)):
        return ""
    s = str(c).strip().upper()
    if s in ("EGP", "E£", "LE", "L.E.", "L.E"):
        return "EGP"
    if s in ("USD", "US$", "US DOLLAR"):
        return "USD"
    return s


def _distribution_due_amount_column(distribution_df: pd.DataFrame) -> str | None:
    """V2 tables use contract-level ``due_amount``; legacy / expanded rows may use ``lessor_due_amount``."""
    if "lessor_due_amount" in distribution_df.columns:
        return "lessor_due_amount"
    if "due_amount" in distribution_df.columns:
        return "due_amount"
    return None


def _due_totals_egp_usd(
    distribution_df: pd.DataFrame,
    contracts_df: pd.DataFrame,
    *,
    today_ts: pd.Timestamp,
) -> tuple[float, float, float, float, float, float]:
    """
    Returns (overall_egp, overall_usd, month_egp, month_usd, year_egp, year_usd)
    for schedule rows from the **start of the current month** onward (includes the active month),
    split by contract currency. Blank currency is treated as EGP.
    """
    if distribution_df is None or distribution_df.empty:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    if "rent_date" not in distribution_df.columns:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    amt_col = _distribution_due_amount_column(distribution_df)
    if not amt_col:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    d = distribution_df.copy()
    d["_rent_dt"] = pd.to_datetime(d["rent_date"], errors="coerce")
    d = d[d["_rent_dt"].notna()]
    if d.empty:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    d["_amt"] = d[amt_col].map(_parse_amount)
    d["contract_id"] = d["contract_id"].astype(str)

    if contracts_df is not None and not contracts_df.empty and "currency" in contracts_df.columns:
        cmap = contracts_df[["id", "currency"]].copy()
        cmap["id"] = cmap["id"].astype(str)
        d = d.merge(cmap, left_on="contract_id", right_on="id", how="left")
    else:
        d["currency"] = ""

    d["_cur"] = d["currency"].map(_normalize_currency)
    d["_cur"] = d["_cur"].replace("", np.nan).fillna("EGP")
    # From first day of current month (not "today") so mid-month still counts this month's due rows
    month_start = pd.Timestamp(today_ts.year, today_ts.month, 1)
    fwd = d[d["_rent_dt"] >= month_start]
    if fwd.empty:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    y, m = today_ts.year, today_ts.month

    def sum_pair(frame: pd.DataFrame) -> tuple[float, float]:
        egp = frame.loc[frame["_cur"] == "EGP", "_amt"].sum()
        usd = frame.loc[frame["_cur"] == "USD", "_amt"].sum()
        return (float(egp), float(usd))

    o_e, o_u = sum_pair(fwd)
    m_mask = (fwd["_rent_dt"].dt.year == y) & (fwd["_rent_dt"].dt.month == m)
    mo_e, mo_u = sum_pair(fwd[m_mask])
    y_mask = fwd["_rent_dt"].dt.year == y
    ye_e, ye_u = sum_pair(fwd[y_mask])
    return (o_e, o_u, mo_e, mo_u, ye_e, ye_u)


def render_dashboard():
    """Render the main dashboard with statistics"""
    require_permission("dashboard.view")
    st.title("Dashboard")
    st.markdown("---")

    load_all()

    current_date = datetime.now()
    today_ts = pd.Timestamp(current_date.date())

    contracts_df = st.session_state.contracts_df.copy()
    lessors_df = st.session_state.lessors_df.copy()
    assets_df = st.session_state.assets_df.copy()
    stores_df = st.session_state.stores_df.copy()
    services_df = st.session_state.services_df.copy()
    distribution_df = st.session_state.contract_distribution_df.copy()

    total_contracts = len(contracts_df) if not contracts_df.empty else 0
    total_lessors = len(lessors_df) if not lessors_df.empty else 0
    total_assets = len(assets_df) if not assets_df.empty else 0
    total_stores = len(stores_df) if not stores_df.empty else 0
    total_services = len(services_df) if not services_df.empty else 0

    if not contracts_df.empty and "contract_type" in contracts_df.columns:
        contract_types = contracts_df["contract_type"].value_counts().to_dict()
        fixed_contracts = contract_types.get("Fixed", 0)
        revenue_share_contracts = contract_types.get("Revenue Share", 0)
        rou_contracts = contract_types.get("ROU", 0)
    else:
        fixed_contracts = 0
        revenue_share_contracts = 0
        rou_contracts = 0

    def format_money(num: float, curr: str) -> str:
        if num == 0:
            return "0"
        abs_n = abs(num)
        if abs_n >= 1_000_000:
            return f"{num / 1_000_000:.2f}M {curr}"
        if abs_n >= 1_000:
            return f"{num / 1_000:.2f}K {curr}"
        return f"{num:,.2f} {curr}"

    def format_number(num):
        if num == 0:
            return "0"
        abs_num = abs(num)
        if abs_num >= 1_000_000:
            return f"{num / 1_000_000:.2f}M"
        if abs_num >= 1_000:
            return f"{num / 1_000:.2f}K"
        return f"{num:,.0f}"

    o_egp, o_usd, m_egp, m_usd, y_egp, y_usd = _due_totals_egp_usd(
        distribution_df, contracts_df, today_ts=today_ts
    )

    active_contracts = 0
    if not contracts_df.empty and "end_date" in contracts_df.columns:
        try:
            contracts_df = contracts_df.copy()
            contracts_df["end_date_parsed"] = pd.to_datetime(contracts_df["end_date"], errors="coerce")
            active_contracts = len(contracts_df[contracts_df["end_date_parsed"] >= pd.Timestamp.now()])
        except Exception:
            active_contracts = total_contracts

    # Light, high-contrast metric card (pro / readable)
    def kpi_card(value_html: str, label: str, *, accent: str = "#0f766e") -> str:
        return f"""
        <div style="
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 18px 16px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            border-left: 4px solid {accent};
        ">
            <div style="font-size: 1.75rem; font-weight: 700; color: #0f172a; line-height: 1.2; letter-spacing: -0.02em;">
                {value_html}
            </div>
            <div style="margin-top: 8px; font-size: 0.875rem; font-weight: 500; color: #64748b;">
                {label}
            </div>
        </div>
        """

    st.markdown("### Due Amounts")

    egp1, egp2, egp3 = st.columns(3)
    with egp1:
        st.markdown(
            kpi_card(format_money(o_egp, "EGP"), "Total upcoming due (EGP)", accent="#0369a1"),
            unsafe_allow_html=True,
        )
    with egp2:
        st.markdown(
            kpi_card(
                format_money(y_egp, "EGP"),
                f"This year due (EGP) · {current_date.year}",
                accent="#7c3aed",
            ),
            unsafe_allow_html=True,
        )
    with egp3:
        st.markdown(
            kpi_card(
                format_money(m_egp, "EGP"),
                f"This month due (EGP) · {current_date.strftime('%B %Y')}",
                accent="#0d9488",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    usd1, usd2, usd3 = st.columns(3)
    with usd1:
        st.markdown(
            kpi_card(format_money(o_usd, "USD"), "Total upcoming due (USD)", accent="#0369a1"),
            unsafe_allow_html=True,
        )
    with usd2:
        st.markdown(
            kpi_card(
                format_money(y_usd, "USD"),
                f"This year due (USD) · {current_date.year}",
                accent="#7c3aed",
            ),
            unsafe_allow_html=True,
        )
    with usd3:
        st.markdown(
            kpi_card(
                format_money(m_usd, "USD"),
                f"This month due (USD) · {current_date.strftime('%B %Y')}",
                accent="#0d9488",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Portfolio")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            kpi_card(format_number(total_contracts), "Total contracts", accent="#2563eb"),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            kpi_card(format_number(active_contracts), "Active contracts", accent="#059669"),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            kpi_card(format_number(total_lessors), "Lessors", accent="#4f46e5"),
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            kpi_card(format_number(total_assets), "Assets", accent="#0ea5e9"),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    col5, col6 = st.columns(2)
    with col5:
        st.markdown(
            kpi_card(format_number(total_stores), "Stores", accent="#0284c7"),
            unsafe_allow_html=True,
        )
    with col6:
        st.markdown(
            kpi_card(format_number(total_services), "Services", accent="#65a30d"),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Contract type breakdown")
    col_type1, col_type2, col_type3 = st.columns(3)

    with col_type1:
        st.markdown(
            f"""
            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px;border-left:4px solid #2563eb;">
                <h3 style="margin:0;color:#1e293b;font-size:1.35rem;">{fixed_contracts}</h3>
                <p style="margin:6px 0 0 0;color:#64748b;font-size:0.9rem;">Fixed</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_type2:
        st.markdown(
            f"""
            <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px;border-left:4px solid #d97706;">
                <h3 style="margin:0;color:#1e293b;font-size:1.35rem;">{revenue_share_contracts}</h3>
                <p style="margin:6px 0 0 0;color:#64748b;font-size:0.9rem;">Revenue share</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_type3:
        st.markdown(
            f"""
            <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:10px;padding:14px;border-left:4px solid #059669;">
                <h3 style="margin:0;color:#1e293b;font-size:1.35rem;">{rou_contracts}</h3>
                <p style="margin:6px 0 0 0;color:#64748b;font-size:0.9rem;">ROU</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Quick actions")
    st.caption("Each action opens the matching screen if your role allows it.")

    can_contract_create = has_permission("contracts.create")
    can_contract_view = has_permission("contracts.view")
    can_lessor_create = has_permission("lessors.create")
    can_lessor_view = has_permission("lessors.view")
    can_distribution = has_permission("distribution.view")

    col_action1, col_action2, col_action3 = st.columns(3)

    with col_action1:
        if can_contract_create:
            c_label, c_sub, c_primary = "Create new contract", "Create Contract", True
        elif can_contract_view:
            c_label, c_sub, c_primary = "Contract management", "Contract Management", False
        else:
            c_label, c_sub, c_primary = "Contracts", "", False
        c_ok = can_contract_create or can_contract_view
        if st.button(
            c_label,
            key="dash_qact_new_contract",
            use_container_width=True,
            type="primary" if c_primary else "secondary",
            disabled=not c_ok,
            help=None
            if c_ok
            else "You need contracts.view or contracts.create to open Contracts.",
        ):
            st.session_state.selected_main = _NAV_CONTRACTS
            st.session_state.selected_sub = c_sub
            st.rerun()

    with col_action2:
        if can_lessor_create:
            l_label, l_sub, l_primary = "Add new lessor", "Create Lessor", True
        elif can_lessor_view:
            l_label, l_sub, l_primary = "Lessor management", "Lessor Management", False
        else:
            l_label, l_sub, l_primary = "Lessors", "", False
        l_ok = can_lessor_create or can_lessor_view
        if st.button(
            l_label,
            key="dash_qact_new_lessor",
            use_container_width=True,
            type="primary" if l_primary else "secondary",
            disabled=not l_ok,
            help=None
            if l_ok
            else "You need lessors.view or lessors.create to open Lessors.",
        ):
            st.session_state.selected_main = _NAV_LESSORS
            st.session_state.selected_sub = l_sub
            st.rerun()

    with col_action3:
        if st.button(
            "Distribution",
            key="dash_qact_distribution",
            use_container_width=True,
            type="secondary",
            disabled=not can_distribution,
            help=None
            if can_distribution
            else "You need distribution.view to open Distribution.",
        ):
            st.session_state.selected_main = _NAV_DISTRIBUTION
            st.session_state.selected_sub = "Contracts Distribution"
            st.rerun()

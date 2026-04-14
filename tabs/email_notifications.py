# tab_email_notifications.py
# Email notifications tab - Weekly payment emails and payment-date reminders
import html as _html
import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import os
from core.utils import *
from conf.constants import *
from core.db import *
from core.auth import get_current_user, get_user_ip
from core.permissions import require_permission

# Default Office 365 sender (overridden by EMAIL_* / SMTP_* env vars or .env)
SENDER_EMAIL = "data@cilantrocafe.net"
SENDER_PASSWORD = "Gre@T#D@t$CiL%2024"
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", SMTP_SERVER)
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", str(SMTP_PORT)))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", SENDER_EMAIL)
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", SENDER_PASSWORD)
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Contract Management System")

# Weekly + reminder email attachments share the same CSV layout (human-readable headers).
_EMAIL_PAYMENTS_CSV_SPECS = [
    ("contract_name", "Contract name"),
    ("contract_type", "Contract type"),
    ("lessor_name", "Lessor name"),
    ("lessor_iban", "Lessor IBAN"),
    ("payment_date", "Payment date"),
    ("rent_month", "Rent month"),
    ("amount", "Gross amount (before discount/advance)"),
    ("due_amount", "Due amount"),
    ("tax_amount", "Tax amount"),
    ("withholding_amount", "Withholding amount"),
    ("payment_amount", "Payment amount"),
    ("lessor_share_pct", "Lessor share %"),
    ("currency", "Currency"),
    ("payment_type", "Payment type"),
    ("service_name", "Service name"),
    ("tax_pct", "Tax %"),
]


def _email_payments_csv_headers_only() -> str:
    return pd.DataFrame(columns=[h for _, h in _EMAIL_PAYMENTS_CSV_SPECS]).to_csv(index=False)


def _normalize_export_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase / decode column names so SQL/driver aliases always match export keys."""
    d = df.copy()
    new_cols = []
    for c in d.columns:
        if isinstance(c, bytes):
            new_cols.append(c.decode("utf-8", errors="replace").strip().lower())
        else:
            new_cols.append(str(c).strip().lower())
    d.columns = new_cols
    return d


def _calendar_week_range_containing(day):
    """Monday–Sunday week that contains ``day`` (inclusive)."""
    start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return start, end


def _dataframe_to_email_payments_csv(df: pd.DataFrame) -> str:
    """Build attachment CSV with display headers; empty df → header row only."""
    if df.empty:
        return _email_payments_csv_headers_only()
    d = _normalize_export_df_columns(df)
    keys = [k for k, _ in _EMAIL_PAYMENTS_CSV_SPECS]
    for k in keys:
        if k not in d.columns:
            d[k] = ""
    if "payment_date" in d.columns:
        _pd = pd.to_datetime(d["payment_date"], errors="coerce")
        d["payment_date"] = _pd.dt.strftime("%Y-%m-%d").where(_pd.notna(), "")
    if "rent_month" in d.columns:
        _rm = pd.to_datetime(d["rent_month"], errors="coerce")
        d["rent_month"] = _rm.dt.strftime("%Y-%m-%d").where(_rm.notna(), "")
    for col in ("amount", "due_amount", "tax_amount", "withholding_amount", "payment_amount"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    for col in ("lessor_name", "lessor_iban", "service_name", "currency", "payment_type", "lessor_share_pct", "tax_pct"):
        if col in d.columns:
            d[col] = d[col].fillna("").astype(str).replace("nan", "")
    out = d[keys].copy()
    out = out.rename(columns={k: h for k, h in _EMAIL_PAYMENTS_CSV_SPECS})
    return out.to_csv(index=False)


def _reminder_payments_export_csv(df: pd.DataFrame) -> str:
    return _dataframe_to_email_payments_csv(df)


def _email_payments_base_sql(where_fragment: str) -> str:
    """Shared SELECT for weekly + reminder exports; where_fragment starts with AND or is empty."""
    return f"""
            SELECT
                p.contract_id,
                COALESCE(NULLIF(TRIM(c.asset_or_store_id), ''), '') AS asset_or_store_id,
                COALESCE(NULLIF(TRIM(c.asset_category), ''), '') AS asset_category,
                c.contract_name,
                c.contract_type,
                p.lessor_id,
                COALESCE(l.name, '') AS lessor_name,
                COALESCE(l.iban, '') AS lessor_iban,
                p.payment_date,
                p.rent_month,
                p.amount,
                p.due_amount,
                CAST(COALESCE(NULLIF(p.tax_amount, ''), '0') AS DECIMAL(10,2)) AS tax_amount,
                CAST(COALESCE(NULLIF(p.withholding_amount, ''), '0') AS DECIMAL(10,2)) AS withholding_amount,
                p.payment_amount,
                p.lessor_share_pct,
                COALESCE(NULLIF(TRIM(c.currency), ''), '') AS currency,
                CASE
                    WHEN p.service_id IS NOT NULL AND TRIM(COALESCE(p.service_id, '')) != '' THEN 'Service Payment'
                    ELSE 'Contract Payment'
                END AS payment_type,
                COALESCE(s.name, '') AS service_name,
                p.tax_pct
            FROM payments p
            LEFT JOIN contracts c ON p.contract_id = c.id
            LEFT JOIN lessors l ON p.lessor_id = l.id
            LEFT JOIN services s ON p.service_id = s.id
            WHERE p.payment_date IS NOT NULL {where_fragment}
            ORDER BY p.payment_date ASC, c.contract_name ASC, l.name ASC
        """


def _html_include_contracts_scope(
    contract_selection: str,
    contracts_df: pd.DataFrame,
    selected_contract_ids: list | None,
    selected_contract_types: list | None,
) -> str:
    """HTML paragraph describing which contracts are included (matches form scope)."""
    if contract_selection == "All Contracts":
        text = "All contracts"
    elif contract_selection == "Select Contracts":
        ids = list(selected_contract_ids or [])
        if not ids:
            text = "Selected contracts (none chosen)"
        elif contracts_df is None or getattr(contracts_df, "empty", True):
            text = "Selected contracts (see configuration)"
        else:
            id_set = {str(i) for i in ids}
            mask = contracts_df["id"].astype(str).isin(id_set)
            names = contracts_df.loc[mask, "contract_name"].tolist()
            if names:
                text = ", ".join(_html.escape(str(n)) for n in names)
            else:
                text = ", ".join(_html.escape(str(i)) for i in ids)
    else:
        types = list(selected_contract_types or [])
        if not types:
            text = "Filter by contract type (none chosen)"
        else:
            text = "Types: " + ", ".join(_html.escape(str(t)) for t in types)
    return f"<p><strong>Include contracts:</strong> {text}</p>"


def _normalize_currency_reminder(c) -> str:
    """Align with dashboard: blank and common aliases → EGP/USD; other codes unchanged."""
    if c is None or (isinstance(c, float) and pd.isna(c)):
        return ""
    s = str(c).strip().upper()
    if s in ("EGP", "E£", "LE", "L.E.", "L.E"):
        return "EGP"
    if s in ("USD", "US$", "US DOLLAR"):
        return "USD"
    return s


def _nunique_nonempty_ids(series: pd.Series | None) -> int:
    if series is None or len(series) == 0:
        return 0
    s = series.astype(str).str.strip()
    s = s[(s != "") & (s.str.lower() != "nan") & (s.str.lower() != "none")]
    return int(s.nunique())


def _reminder_sheet_unique_counts(df: pd.DataFrame) -> dict:
    """Unique branches, assets, lessors, and contracts-by-type among rows in the sheet only."""
    out = {
        "stores": 0,
        "assets": 0,
        "lessors": 0,
        "fixed": 0,
        "revenue_share": 0,
        "rou": 0,
    }
    if df is None or df.empty:
        return out
    d = _normalize_export_df_columns(df)

    ac = d.get("asset_category")
    if ac is not None:
        ac_norm = ac.astype(str).str.strip().str.lower()
        store_mask = ac_norm == "store"
        asset_mask = ac_norm == "other"
        # Legacy / blank / unknown label: treat as store location (not asset).
        unknown_loc_mask = (ac_norm == "") | (~store_mask & ~asset_mask)
    else:
        store_mask = pd.Series([False] * len(d), index=d.index)
        asset_mask = pd.Series([False] * len(d), index=d.index)
        unknown_loc_mask = pd.Series([True] * len(d), index=d.index)

    if "asset_or_store_id" in d.columns:
        loc = d["asset_or_store_id"]
        has_loc = loc.astype(str).str.strip().replace("", pd.NA).notna()
        has_loc = has_loc & (loc.astype(str).str.strip().str.lower() != "nan")
        branch_mask = (store_mask | unknown_loc_mask) & ~asset_mask & has_loc
        out["stores"] = _nunique_nonempty_ids(d.loc[branch_mask, "asset_or_store_id"])
        out["assets"] = _nunique_nonempty_ids(d.loc[asset_mask & has_loc, "asset_or_store_id"])

    if "lessor_id" in d.columns:
        lid = d["lessor_id"]
        mask = lid.notna() & (lid.astype(str).str.strip() != "") & (
            lid.astype(str).str.strip().str.lower() != "nan"
        )
        if mask.any():
            out["lessors"] = int(lid[mask].astype(str).nunique())
    if out["lessors"] == 0 and "lessor_name" in d.columns:
        nm = d["lessor_name"].astype(str).str.strip()
        ib = (
            d["lessor_iban"].astype(str).str.strip()
            if "lessor_iban" in d.columns
            else pd.Series([""] * len(d), index=d.index)
        )
        valid = (nm != "") | (ib != "")
        if valid.any():
            out["lessors"] = int((nm[valid] + "|" + ib[valid]).nunique())

    ct = d.get("contract_type")
    cid = d.get("contract_id")
    if ct is not None and cid is not None:
        ct_s = ct.astype(str).str.strip()
        for label, key in (
            ("Fixed", "fixed"),
            ("Revenue Share", "revenue_share"),
            ("ROU", "rou"),
        ):
            m = ct_s == label
            if m.any():
                out[key] = _nunique_nonempty_ids(cid[m])

    return out


def _reminder_payments_summary_html(upcoming: pd.DataFrame) -> str:
    """Summary from the same rows as the attachment: totals + unique entities in that set only."""
    rent_egp = rent_usd = 0.0
    svc_egp = svc_usd = 0.0
    tot_egp = tot_usd = 0.0
    pc = _reminder_sheet_unique_counts(
        upcoming if upcoming is not None else pd.DataFrame()
    )

    if upcoming is not None and not upcoming.empty:
        d = _normalize_export_df_columns(upcoming.copy())
        due = pd.to_numeric(d.get("due_amount"), errors="coerce").fillna(0)
        if "currency" in d.columns:
            cur = d["currency"].map(_normalize_currency_reminder)
            cur = cur.replace("", pd.NA).fillna("EGP")
        else:
            cur = pd.Series(["EGP"] * len(d), index=d.index)
        pt = d.get("payment_type")
        if pt is not None:
            is_svc = pt.astype(str).str.strip().eq("Service Payment")
        else:
            is_svc = pd.Series([False] * len(d), index=d.index)

        def sums(mask: pd.Series) -> tuple[float, float]:
            m = mask.fillna(False)
            eg = float(due[m & (cur == "EGP")].sum())
            us = float(due[m & (cur == "USD")].sum())
            return eg, us

        rent_egp, rent_usd = sums(~is_svc)
        svc_egp, svc_usd = sums(is_svc)
        tot_egp, tot_usd = sums(pd.Series([True] * len(d), index=d.index))

    lines = [
        "<p><strong>Below is summary:</strong></p>",
        "<ul>",
        f"<li><strong>Total rent</strong> — EGP: {rent_egp:,.2f}; USD: {rent_usd:,.2f}</li>",
        f"<li><strong>Total services</strong> — EGP: {svc_egp:,.2f}; USD: {svc_usd:,.2f}</li>",
        f"<li><strong>No. of branches (stores)</strong>: {pc['stores']}</li>",
        f"<li><strong>No. of assets</strong>: {pc['assets']}</li>",
        f"<li><strong>No. of ROU contracts</strong>: {pc['rou']}</li>",
        f"<li><strong>No. of Revenue Share contracts</strong>: {pc['revenue_share']}</li>",
        f"<li><strong>No. of Fixed contracts</strong>: {pc['fixed']}</li>",
        f"<li><strong>No. of lessors</strong>: {pc['lessors']}</li>",
        f"<li><strong>Total in EGP</strong> (all lines in window): {tot_egp:,.2f}</li>",
        f"<li><strong>TOTAL IN USD</strong> (all lines in window): {tot_usd:,.2f}</li>",
        "</ul>",
    ]
    return "\n".join(lines)


def _email_html_weekly_body(
    next_week_start,
    next_week_end,
    *,
    is_test: bool = False,
    include_contracts_html: str = "",
) -> str:
    test_note = "<p><em>This is a test email.</em></p>" if is_test else ""
    inc = include_contracts_html or ""
    return f"""<html>
<body>
<p>Hello Dear,</p>
<p>Please find the attached sheet for the payment lines in the period <strong>{next_week_start}</strong> to <strong>{next_week_end}</strong>.</p>
{inc}
{test_note}
<p>Best regards,<br>Contract Management System</p>
</body>
</html>"""


def _email_html_reminder_body(
    reminder_days: int,
    *,
    is_test: bool = False,
    summary_html: str = "",
) -> str:
    test_note = "<p><em>This is a test email.</em></p>" if is_test else ""
    summ = summary_html or ""
    return f"""<html>
<body>
<p>Hello Team!,</p>
<p>Please find the attached sheet for the upcoming payments (payment dates in the next <strong>{reminder_days}</strong> days).</p>
{summ}
{test_note}
<p>Best regards,<br>Contract Management System</p>
</body>
</html>"""


def send_email_via_smtp(to_emails, subject, body, csv_data=None, csv_filename=None):
    """Send email via SMTP (Office 365)"""
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_FROM_NAME} <{EMAIL_USERNAME}>"
        msg['To'] = ', '.join(to_emails) if isinstance(to_emails, list) else to_emails
        msg['Subject'] = subject
        
        # Add body
        msg.attach(MIMEText(body, 'html'))
        
        # Add CSV attachment when filename is set (allows header-only / empty data file)
        if csv_filename:
            attachment = MIMEBase('application', 'octet-stream')
            payload = csv_data if isinstance(csv_data, str) else ("" if csv_data is None else str(csv_data))
            attachment.set_payload(payload.encode("utf-8"))
            encoders.encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename= {csv_filename}'
            )
            msg.attach(attachment)
        
        # Connect to SMTP server and send
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_USERNAME, to_emails, text)
        server.quit()
        
        return True
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            st.error(f"Error sending email: {str(e)}")
            st.error(tb)
        except Exception:
            pass
        print(f"Error sending email: {e}\n{tb}")
        return False

def get_payments_csv_for_week(start_date, end_date, contract_ids=None, contract_types=None):
    """Payments in date range as CSV (same columns as reminder emails)."""
    try:
        from core.db import execute_query

        extra_where = []
        params = []
        if start_date:
            extra_where.append("p.payment_date >= %s")
            params.append(start_date)
        if end_date:
            extra_where.append("p.payment_date <= %s")
            params.append(end_date)
        if contract_ids:
            extra_where.append("p.contract_id IN (" + ",".join(["%s"] * len(contract_ids)) + ")")
            params.extend(contract_ids)
        if contract_types:
            extra_where.append("c.contract_type IN (" + ",".join(["%s"] * len(contract_types)) + ")")
            params.extend(contract_types)
        where_fragment = (" AND " + " AND ".join(extra_where)) if extra_where else ""
        payments_query = _email_payments_base_sql(where_fragment)
        payments_result = execute_query(payments_query, params=params, fetch=True)
        payments_df = pd.DataFrame(payments_result) if payments_result else pd.DataFrame()
        if payments_df.empty:
            return _email_payments_csv_headers_only()
        return _dataframe_to_email_payments_csv(payments_df)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            st.error(f"Error generating payments CSV: {str(e)}")
            st.error(tb)
        except Exception:
            pass
        print(f"Error generating payments CSV: {e}\n{tb}")
        return None


def get_upcoming_payments_for_reminder_window(
    reminder_days: int,
    contract_ids=None,
    contract_types=None,
):
    """
    Payment rows from `payments` where payment_date is between today and
    today + reminder_days (inclusive). Joins contracts and lessors for labels.
    contract_ids / contract_types: pass None to skip that filter; pass [] for
    empty selection (returns no rows).
    """
    from core.db import execute_query

    try:
        window = max(1, int(reminder_days))
    except (TypeError, ValueError):
        window = 30
    if contract_ids is not None and len(contract_ids) == 0:
        return pd.DataFrame()
    if contract_types is not None and len(contract_types) == 0:
        return pd.DataFrame()

    today = datetime.now().date()
    end_d = today + timedelta(days=window)
    extra = ["DATE(p.payment_date) >= %s", "DATE(p.payment_date) <= %s"]
    params = [today, end_d]
    if contract_ids:
        clean = [str(i) for i in contract_ids if i is not None and str(i).strip() != ""]
        if clean:
            extra.append("p.contract_id IN (" + ",".join(["%s"] * len(clean)) + ")")
            params.extend(clean)
    if contract_types:
        clean_t = [str(t) for t in contract_types if t is not None and str(t).strip() != ""]
        if clean_t:
            extra.append("c.contract_type IN (" + ",".join(["%s"] * len(clean_t)) + ")")
            params.extend(clean_t)
    where_fragment = " AND " + " AND ".join(extra)
    query = _email_payments_base_sql(where_fragment)
    rows = execute_query(query, tuple(params), fetch=True)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def render_email_notifications_tab():
    """Render email notifications tab (default view)"""
    require_permission('email.view')
    # Default to Weekly Payment Emails
    render_weekly_payment_emails()

def render_weekly_payment_emails():
    """Render weekly payment emails configuration"""
    st.subheader("Weekly Payment Emails")
    st.caption("Configure automated weekly emails with payment due amounts and CSV attachments")
    
    load_all()
    contracts_df = st.session_state.contracts_df.copy()
    
    if contracts_df.empty:
        st.info("No contracts available. Please create contracts first.")
        return
    
    # Email recipients
    st.markdown("### Email Recipients")
    recipient_input = st.text_area(
        "Enter email addresses (one per line or comma-separated)",
        key="weekly_email_recipients",
        help="Enter email addresses separated by commas or new lines"
    )
    
    # Parse recipients
    recipients = []
    valid_recipients = []
    if recipient_input:
        # Split by comma or newline
        recipients = [email.strip() for email in recipient_input.replace('\n', ',').split(',') if email.strip()]
        # Basic email validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        valid_recipients = [email for email in recipients if re.match(email_pattern, email)]
        invalid_recipients = [email for email in recipients if not re.match(email_pattern, email)]
        
        if invalid_recipients:
            st.warning(f"Invalid email addresses: {', '.join(invalid_recipients)}")
        
        if valid_recipients:
            st.success(f"Valid recipients: {len(valid_recipients)}")
            st.write(", ".join(valid_recipients))
    
    st.markdown("---")
    
    # Contract selection
    st.markdown("### Contract Selection")
    contract_selection = st.radio(
        "Select contracts to include",
        options=["All Contracts", "Select Contracts", "Filter by Type"],
        key="weekly_contract_selection"
    )
    
    selected_contract_ids = []
    selected_contract_types = []
    
    if contract_selection == "Select Contracts":
        contract_options = contracts_df['contract_name'].tolist()
        selected_contracts = st.multiselect(
            "Choose contracts",
            options=contract_options,
            key="weekly_selected_contracts"
        )
        if selected_contracts:
            selected_contract_ids = contracts_df[contracts_df['contract_name'].isin(selected_contracts)]['id'].tolist()
    
    elif contract_selection == "Filter by Type":
        contract_types = contracts_df['contract_type'].unique().tolist()
        selected_types = st.multiselect(
            "Choose contract types",
            options=contract_types,
            key="weekly_selected_types"
        )
        if selected_types:
            selected_contract_types = selected_types
    
    st.markdown("---")
    
    # Schedule configuration
    st.markdown("### Schedule Configuration")
    col_day, col_time = st.columns(2)
    
    with col_day:
        day_of_week = st.selectbox(
            "Day of week",
            options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            index=0,
            key="weekly_day_of_week"
        )
    
    with col_time:
        send_time = st.time_input(
            "Send time",
            value=datetime.strptime("09:00", "%H:%M").time(),
            key="weekly_send_time"
        )
    
    st.markdown("---")
    
    # Email preview and test
    st.markdown("### Preview & Test")
    
    # Calendar week (Mon–Sun) containing today — matches typical due-date reporting
    today = datetime.now().date()
    next_week_start, next_week_end = _calendar_week_range_containing(today)
    
    col_preview1, col_preview2 = st.columns(2)
    with col_preview1:
        st.write(
            f"**Report week (Mon–Sun) containing today:** {next_week_start} to {next_week_end}"
        )
    
    with col_preview2:
        if st.button("📧 Send Test Email", key="btn_test_weekly_email"):
            if not valid_recipients:
                st.error("Please add at least one valid email address")
            else:
                with st.spinner("Sending test email..."):
                    # Get payments in that calendar week
                    csv_data = get_payments_csv_for_week(
                        next_week_start,
                        next_week_end,
                        contract_ids=selected_contract_ids if selected_contract_ids else None,
                        contract_types=selected_contract_types if selected_contract_types else None
                    )
                    
                    if csv_data is None:
                        st.error("Could not build the payment export. Check the database connection.")
                    else:
                        subject = f"Weekly Payment Report - {next_week_start} to {next_week_end}"
                        body = _email_html_weekly_body(
                            next_week_start,
                            next_week_end,
                            is_test=True,
                            include_contracts_html=_html_include_contracts_scope(
                                contract_selection,
                                contracts_df,
                                selected_contract_ids,
                                selected_contract_types,
                            ),
                        )
                        
                        if send_email_via_smtp(
                            valid_recipients,
                            subject,
                            body,
                            csv_data=csv_data,
                            csv_filename=f"payments_{next_week_start}_{next_week_end}.csv"
                        ):
                            st.success("✅ Test email sent successfully!")
                            # Log action
                            current_user = get_current_user()
                            log_action(
                                user_id=current_user['id'] if current_user else None,
                                user_name=current_user['name'] if current_user else 'System',
                                action_type='test_email',
                                entity_type='weekly_payment_email',
                                entity_id=None,
                                entity_name=None,
                                action_details=f"Sent test weekly payment email to {len(valid_recipients)} recipient(s)",
                                ip_address=get_user_ip()
                            )
                        else:
                            st.error("Failed to send test email. Check email configuration.")
    
    st.markdown("---")
    
    # Save configuration
    st.markdown("### Save Configuration")
    config_name = st.text_input(
        "Configuration name",
        value="Weekly Payment Report",
        key="weekly_config_name"
    )
    
    if st.button("💾 Save Weekly Email Configuration", key="btn_save_weekly_config", type="primary"):
        if not valid_recipients:
            st.error("Please add at least one valid email address")
        elif not config_name.strip():
            st.error("Please enter a configuration name")
        else:
            try:
                from core.db import save_email_schedule
                
                contract_selection_type = 'all'
                if contract_selection == "Select Contracts":
                    contract_selection_type = 'selected'
                elif contract_selection == "Filter by Type":
                    contract_selection_type = 'filtered'
                
                schedule_id = save_email_schedule(
                    schedule_type='weekly_payment',
                    name=config_name.strip(),
                    recipients=valid_recipients,
                    day_of_week=day_of_week,
                    send_time=send_time,
                    reminder_days_before=None,
                    contract_selection_type=contract_selection_type,
                    selected_contract_ids=selected_contract_ids if selected_contract_ids else None,
                    contract_types=selected_contract_types if selected_contract_types else None,
                    is_active=True
                )
                
                if schedule_id:
                    st.success(f"✅ Weekly email configuration saved successfully! (ID: {schedule_id})")
                    # Log action
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='create',
                        entity_type='email_schedule',
                        entity_id=str(schedule_id),
                        entity_name=config_name.strip(),
                        action_details=f"Created weekly payment email schedule: {len(valid_recipients)} recipient(s)",
                        ip_address=get_user_ip()
                    )
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Failed to save configuration. Please check database connection.")
            except Exception as e:
                st.error(f"Error saving configuration: {str(e)}")
                import traceback
                st.error(traceback.format_exc())

def render_contract_due_date_reminders():
    """Render payment-based reminder configuration (uses payments.payment_date)."""
    st.subheader("Payment Reminders")
    st.caption(
        "Configure automated emails for **payment dates** from the payments table "
        "(not contract end dates)."
    )
    
    load_all()
    contracts_df = st.session_state.contracts_df.copy()
    
    if contracts_df.empty:
        st.info("No contracts available. Please create contracts first.")
        return
    
    # Email recipients
    st.markdown("### Email Recipients")
    recipient_input = st.text_area(
        "Enter email addresses (one per line or comma-separated)",
        key="reminder_email_recipients",
        help="Enter email addresses separated by commas or new lines"
    )
    
    # Parse recipients
    recipients = []
    valid_recipients = []
    if recipient_input:
        recipients = [email.strip() for email in recipient_input.replace('\n', ',').split(',') if email.strip()]
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        valid_recipients = [email for email in recipients if re.match(email_pattern, email)]
        invalid_recipients = [email for email in recipients if not re.match(email_pattern, email)]
        
        if invalid_recipients:
            st.warning(f"Invalid email addresses: {', '.join(invalid_recipients)}")
        
        if valid_recipients:
            st.success(f"Valid recipients: {len(valid_recipients)}")
            st.write(", ".join(valid_recipients))
    
    st.markdown("---")
    
    # Reminder period
    st.markdown("### Reminder Period")
    rp1, rp2 = st.columns(2)
    with rp1:
        reminder_days = st.number_input(
            "Include payments with payment date in the next X days (from today)",
            min_value=1,
            max_value=365,
            value=30,
            key="reminder_days_before",
        )
    with rp2:
        reminder_send_time = st.time_input(
            "Send time",
            value=datetime.strptime("09:00", "%H:%M").time(),
            key="reminder_send_time",
        )
    
    st.markdown("---")
    
    # Contract selection
    st.markdown("### Contract Selection")
    contract_selection = st.radio(
        "Select contracts to monitor",
        options=["All Contracts", "Select Contracts", "Filter by Type"],
        key="reminder_contract_selection"
    )
    
    selected_contract_ids = []
    selected_contract_types = []
    
    if contract_selection == "Select Contracts":
        contract_options = contracts_df['contract_name'].tolist()
        selected_contracts = st.multiselect(
            "Choose contracts",
            options=contract_options,
            key="reminder_selected_contracts"
        )
        if selected_contracts:
            selected_contract_ids = contracts_df[contracts_df['contract_name'].isin(selected_contracts)]['id'].tolist()
    
    elif contract_selection == "Filter by Type":
        contract_types = contracts_df['contract_type'].unique().tolist()
        selected_types = st.multiselect(
            "Choose contract types",
            options=contract_types,
            key="reminder_selected_types"
        )
        if selected_types:
            selected_contract_types = selected_types
    
    st.markdown("---")
    
    # Preview payments in window (payments.payment_date)
    st.markdown("### Upcoming payments (preview)")
    if contract_selection == "Select Contracts" and not selected_contract_ids:
        st.warning("Select at least one contract, or choose **All Contracts**.")
        upcoming_payments = pd.DataFrame()
    elif contract_selection == "Filter by Type" and not selected_contract_types:
        st.warning("Select at least one contract type, or choose **All Contracts**.")
        upcoming_payments = pd.DataFrame()
    else:
        cids = ctypes = None
        if contract_selection == "Select Contracts":
            cids = [str(x) for x in selected_contract_ids]
        elif contract_selection == "Filter by Type":
            ctypes = list(selected_contract_types)
        upcoming_payments = get_upcoming_payments_for_reminder_window(
            reminder_days, cids, ctypes
        )

    if not upcoming_payments.empty:
        disp = upcoming_payments.copy()
        disp["payment_date"] = pd.to_datetime(disp["payment_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        cols = [c for c in ("contract_name", "contract_type", "payment_date", "due_amount", "lessor_name") if c in disp.columns]
        st.dataframe(disp[cols], use_container_width=True, hide_index=True)
        st.info(
            f"Found **{len(upcoming_payments)}** payment line(s) with payment date in the next **{reminder_days}** days."
        )
    elif contract_selection == "All Contracts" or (
        contract_selection == "Select Contracts" and selected_contract_ids
    ) or (contract_selection == "Filter by Type" and selected_contract_types):
        end_d = datetime.now().date() + timedelta(days=reminder_days)
        st.info(
            f"No payments with payment date between today and **{end_d}** for the current filters."
        )
    
    st.markdown("---")
    
    # Test email
    if st.button("📧 Send Test Reminder Email", key="btn_test_reminder_email"):
        if not valid_recipients:
            st.error("Please add at least one valid email address")
        else:
            with st.spinner("Sending test reminder email..."):
                rem_csv = _reminder_payments_export_csv(upcoming_payments)
                subject = f"Payment Reminder - next {reminder_days} days"
                body = _email_html_reminder_body(
                    reminder_days,
                    is_test=True,
                    summary_html=_reminder_payments_summary_html(upcoming_payments),
                )
                if send_email_via_smtp(
                    valid_recipients,
                    subject,
                    body,
                    csv_data=rem_csv,
                    csv_filename=f"payment_reminder_{reminder_days}d.csv",
                ):
                    st.success("Test reminder email sent successfully!")
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='test_email',
                        entity_type='contract_reminder',
                        entity_id=None,
                        entity_name=None,
                        action_details=(
                            f"Sent test payment reminder to {len(valid_recipients)} recipient(s), "
                            f"{len(upcoming_payments)} payment line(s)"
                        ),
                        ip_address=get_user_ip(),
                    )
                else:
                    st.error("Failed to send test email. Check email configuration.")
    
    st.markdown("---")
    
    # Save configuration
    st.markdown("### Save Configuration")
    config_name = st.text_input(
        "Configuration name",
        value="Payment Reminders",
        key="reminder_config_name"
    )
    
    if st.button("💾 Save Reminder Configuration", key="btn_save_reminder_config", type="primary"):
        if not valid_recipients:
            st.error("Please add at least one valid email address")
        elif not config_name.strip():
            st.error("Please enter a configuration name")
        else:
            try:
                from core.db import save_email_schedule
                
                contract_selection_type = 'all'
                if contract_selection == "Select Contracts":
                    contract_selection_type = 'selected'
                elif contract_selection == "Filter by Type":
                    contract_selection_type = 'filtered'
                
                schedule_id = save_email_schedule(
                    schedule_type='contract_reminder',
                    name=config_name.strip(),
                    recipients=valid_recipients,
                    day_of_week=None,
                    send_time=reminder_send_time,
                    reminder_days_before=reminder_days,
                    contract_selection_type=contract_selection_type,
                    selected_contract_ids=selected_contract_ids if selected_contract_ids else None,
                    contract_types=selected_contract_types if selected_contract_types else None,
                    is_active=True
                )
                
                if schedule_id:
                    st.success(f"✅ Reminder configuration saved successfully! (ID: {schedule_id})")
                    # Log action
                    current_user = get_current_user()
                    log_action(
                        user_id=current_user['id'] if current_user else None,
                        user_name=current_user['name'] if current_user else 'System',
                        action_type='create',
                        entity_type='email_schedule',
                        entity_id=str(schedule_id),
                        entity_name=config_name.strip(),
                        action_details=f"Created contract reminder email schedule: {len(valid_recipients)} recipient(s), {reminder_days} days before",
                        ip_address=get_user_ip()
                    )
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Failed to save configuration. Please check database connection.")
            except Exception as e:
                st.error(f"Error saving configuration: {str(e)}")
                import traceback
                st.error(traceback.format_exc())

# ─────────────────────────────────────────────────────────────────────────────
# Notifications Center — central hub (table + separate create/edit pages)
# ─────────────────────────────────────────────────────────────────────────────

_TYPE_LABELS = {
    "weekly_payment": "Weekly Payment",
    "contract_reminder": "Contract Reminder",
}
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _parse_send_time(raw):
    """Safely convert MySQL TIME / timedelta / str to a Python time object."""
    if raw is None:
        return datetime.strptime("09:00", "%H:%M").time()
    try:
        if isinstance(raw, timedelta):
            total = int(raw.total_seconds())
            return datetime.strptime(f"{(total//3600)%24:02d}:{(total//60)%60:02d}", "%H:%M").time()
        if hasattr(raw, "hour"):
            return raw
        raw = str(raw).strip()
        for fmt in ["%H:%M:%S", "%H:%M", "%H:%M:%S.%f"]:
            try:
                return datetime.strptime(raw, fmt).time()
            except ValueError:
                pass
    except Exception:
        pass
    return datetime.strptime("09:00", "%H:%M").time()


def _parse_recipients(raw: str) -> list[str]:
    import re
    items = [e.strip() for e in raw.replace("\n", ",").split(",") if e.strip()]
    pat = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return [e for e in items if re.match(pat, e)]


def _schedule_summary(s: dict) -> str:
    if s.get("schedule_type") == "weekly_payment":
        t = _parse_send_time(s.get("send_time"))
        return f"{s.get('day_of_week', '—')}  {t.strftime('%H:%M')}"
    days = s.get("reminder_days_before")
    t = _parse_send_time(s.get("send_time"))
    if days:
        return f"{days}d payment window · {t.strftime('%H:%M')}"
    return t.strftime("%H:%M")


def _notification_form(
    schedule: dict | None,
    key_prefix: str,
    contracts_df,
    *,
    fixed_schedule_type: str | None = None,
) -> dict | None:
    """
    Render the create / edit form fields.
    When fixed_schedule_type is set on create, the type selector is hidden.
    """
    is_edit = schedule is not None
    stype_options = ["weekly_payment", "contract_reminder"]
    stype_labels = [_TYPE_LABELS[t] for t in stype_options]

    if fixed_schedule_type and not is_edit:
        schedule_type = fixed_schedule_type
        st.markdown(f"**Type:** {_TYPE_LABELS.get(schedule_type, schedule_type)}")
    else:
        current_type = schedule.get("schedule_type", "weekly_payment") if is_edit else "weekly_payment"
        type_idx = stype_options.index(current_type) if current_type in stype_options else 0
        chosen_label = st.selectbox(
            "Notification type",
            options=stype_labels,
            index=type_idx,
            key=f"{key_prefix}_type",
            disabled=is_edit,
        )
        schedule_type = stype_options[stype_labels.index(chosen_label)]

    name_val = schedule.get("name", "") if is_edit else ""
    name = st.text_input("Configuration name", value=name_val, key=f"{key_prefix}_name")

    # Recipients
    cur_recip = schedule.get("recipients", "") if is_edit else ""
    recip_input = st.text_area(
        "Email recipients (one per line or comma-separated)",
        value=cur_recip,
        key=f"{key_prefix}_recipients",
    )
    valid_recipients = _parse_recipients(recip_input)
    invalid = [e.strip() for e in recip_input.replace("\n", ",").split(",")
               if e.strip() and e.strip() not in valid_recipients]
    if invalid:
        st.warning(f"Invalid addresses skipped: {', '.join(invalid)}")
    if valid_recipients:
        st.caption(f"{len(valid_recipients)} valid recipient(s): {', '.join(valid_recipients)}")

    # Schedule-specific fields
    day_of_week = None
    send_time = None
    reminder_days = None

    if schedule_type == "weekly_payment":
        c1, c2 = st.columns(2)
        with c1:
            cur_day = schedule.get("day_of_week", "Monday") if is_edit else "Monday"
            day_idx = _DAYS.index(cur_day) if cur_day in _DAYS else 0
            day_of_week = st.selectbox("Day of week", options=_DAYS, index=day_idx, key=f"{key_prefix}_day")
        with c2:
            parsed_t = _parse_send_time(schedule.get("send_time")) if is_edit else datetime.strptime("09:00", "%H:%M").time()
            send_time = st.time_input("Send time", value=parsed_t, key=f"{key_prefix}_time")
    else:
        cr1, cr2 = st.columns(2)
        with cr1:
            cur_days = int(schedule.get("reminder_days_before", 30) or 30) if is_edit else 30
            reminder_days = st.number_input(
                "Include payments with payment date in the next X days (from today)",
                min_value=1,
                max_value=365,
                value=cur_days,
                key=f"{key_prefix}_reminder_days",
            )
        with cr2:
            parsed_tr = _parse_send_time(schedule.get("send_time")) if is_edit else datetime.strptime("09:00", "%H:%M").time()
            send_time = st.time_input(
                "Send time",
                value=parsed_tr,
                key=f"{key_prefix}_reminder_time",
            )

    # Contract selection
    st.markdown("**Contract selection**")
    sel_type_map = {"all": "All Contracts", "selected": "Select Contracts", "filtered": "Filter by Type"}
    cur_sel = sel_type_map.get(schedule.get("contract_selection_type", "all") if is_edit else "all", "All Contracts")
    contract_selection = st.radio(
        "Include contracts",
        options=["All Contracts", "Select Contracts", "Filter by Type"],
        index=["All Contracts", "Select Contracts", "Filter by Type"].index(cur_sel),
        key=f"{key_prefix}_contract_sel",
        horizontal=True,
    )

    selected_contract_ids = []
    selected_contract_types = []

    if contract_selection == "Select Contracts" and not contracts_df.empty:
        cur_ids = [c.strip() for c in (schedule.get("selected_contract_ids") or "").split(",") if c.strip()] if is_edit else []
        cur_names = contracts_df[contracts_df["id"].isin(cur_ids)]["contract_name"].tolist()
        sel = st.multiselect("Choose contracts", options=contracts_df["contract_name"].tolist(),
                             default=cur_names, key=f"{key_prefix}_contracts")
        selected_contract_ids = contracts_df[contracts_df["contract_name"].isin(sel)]["id"].tolist()

    elif contract_selection == "Filter by Type" and not contracts_df.empty:
        cur_types = [t.strip() for t in (schedule.get("contract_types") or "").split(",") if t.strip()] if is_edit else []
        all_types = contracts_df["contract_type"].unique().tolist()
        sel_types = st.multiselect("Choose contract types", options=all_types,
                                   default=[t for t in cur_types if t in all_types],
                                   key=f"{key_prefix}_ctypes")
        selected_contract_types = sel_types

    # Active toggle (edit only)
    is_active = True
    if is_edit:
        is_active = st.checkbox("Active", value=bool(schedule.get("is_active", True)), key=f"{key_prefix}_active")

    # Collect and validate on save
    return {
        "name": name.strip(),
        "schedule_type": schedule_type,
        "recipients": valid_recipients,
        "day_of_week": day_of_week,
        "send_time": send_time,
        "reminder_days": reminder_days,
        "contract_selection": contract_selection,
        "selected_contract_ids": selected_contract_ids,
        "selected_contract_types": selected_contract_types,
        "is_active": is_active,
        "valid_recipients": valid_recipients,
    }


EMAIL_NAV_MAIN = "\U0001f4e7 Email Notifications"
EMAIL_NAV_SUB_MGMT = "Notifications Center"


def render_notification_management():
    """Central management hub — same style as contract management page."""
    require_permission("email.view")
    from core.db import get_email_schedules
    from core.permissions import has_permission
    from mgmt_ui.delete_dialog import render_email_delete_dialog_if_pending, show_mgmt_success_flash

    show_mgmt_success_flash()
    render_email_delete_dialog_if_pending()

    load_all()
    can_configure = has_permission("email.configure")

    # ── Header + two create buttons (green, mgmt_hub_create_* keys) ─────────────
    h1, h2a, h2b = st.columns([2.2, 1.4, 1.4])
    with h1:
        st.markdown("## Notifications Center")
    st.caption(
        "**Automated sends:** The app saves schedules only. To deliver at the configured day/time, run "
        "`python -m core.email_schedule_runner` on this machine (e.g. every 5 minutes via Windows Task Scheduler), "
        "from the project folder, with the same `.env` / MySQL settings as the app."
    )
    if can_configure:
        with h2a:
            if st.button(
                "Create weekly payment",
                key="mgmt_hub_create_email_weekly",
                use_container_width=True,
            ):
                st.session_state.selected_main = EMAIL_NAV_MAIN
                st.session_state.selected_sub = "Create Weekly Payment Notification"
                st.rerun()
        with h2b:
            if st.button(
                "Create contract reminder",
                key="mgmt_hub_create_email_reminder",
                use_container_width=True,
            ):
                st.session_state.selected_main = EMAIL_NAV_MAIN
                st.session_state.selected_sub = "Create Contract Reminder"
                st.rerun()
    st.caption("Review the table, then use **Edit** or **Delete** on a row.")

    schedules = get_email_schedules() or []

    def _hdr(label: str) -> None:
        st.markdown(
            f'<div style="white-space:nowrap;font-size:0.8rem;font-weight:700;'
            f'color:#1f2937;margin:0 0 4px 0;line-height:1.2;letter-spacing:0.01em">'
            f'{_html.escape(label)}</div>',
            unsafe_allow_html=True,
        )

    def _cell(text: str, *, nowrap: bool = True) -> None:
        ws = "white-space:nowrap;" if nowrap else "white-space:normal;word-break:break-word;"
        st.markdown(
            f'<div style="{ws}font-size:0.875rem;color:#111827;margin:0;line-height:1.35">'
            f'{_html.escape(str(text))}</div>',
            unsafe_allow_html=True,
        )

    _HR = "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #e5e7eb'>"
    _COLS = [2.6, 1.5, 1.0, 1.8, 1.0, 0.9, 0.9]

    if not schedules:
        st.info("No email notifications configured yet. Use the create buttons above.")
    else:
        hdr = st.columns(_COLS)
        for col, label in zip(hdr[:5], ["Name", "Type", "Recipients", "Schedule", "Status"]):
            with col:
                _hdr(label)
        if can_configure:
            with hdr[5]:
                _hdr("Edit")
            with hdr[6]:
                _hdr("Delete")

        st.markdown(_HR, unsafe_allow_html=True)

        for idx, s in enumerate(schedules):
            sid = s["id"]
            recipients = [r for r in (s.get("recipients") or "").split(",") if r.strip()]
            status_txt = "Active" if s.get("is_active", True) else "Inactive"

            row = st.columns(_COLS)
            with row[0]:
                _cell(s.get("name", "—"), nowrap=False)
            with row[1]:
                _cell(_TYPE_LABELS.get(s.get("schedule_type", ""), "—"))
            with row[2]:
                _cell(str(len(recipients)))
            with row[3]:
                _cell(_schedule_summary(s))
            with row[4]:
                _cell(status_txt)
            if can_configure:
                with row[5]:
                    if st.button("Edit", key=f"email_mgmt_edit_{sid}", use_container_width=True):
                        st.session_state.email_notification_edit_id = sid
                        st.session_state.selected_main = EMAIL_NAV_MAIN
                        st.session_state.selected_sub = "Edit Email Notification"
                        st.rerun()
                with row[6]:
                    if st.button("Delete", key=f"email_mgmt_del_{sid}", use_container_width=True):
                        st.session_state.email_mgmt_pending_delete = sid
                        st.rerun()

            if idx < len(schedules) - 1:
                st.markdown(_HR, unsafe_allow_html=True)


# ── Save helpers (extracted to keep render function readable) ─────────────────

def _sel_type_code(contract_selection: str) -> str:
    if contract_selection == "Select Contracts":
        return "selected"
    if contract_selection == "Filter by Type":
        return "filtered"
    return "all"


def _save_notification_create(form_data: dict) -> None:
    from core.db import save_email_schedule
    from mgmt_ui.delete_dialog import MGMT_SUCCESS_FLASH

    errors = []
    if not form_data["name"]:
        errors.append("Configuration name is required.")
    if not form_data["valid_recipients"]:
        errors.append("At least one valid email address is required.")
    if errors:
        for e in errors:
            st.error(e)
        return
    try:
        schedule_id = save_email_schedule(
            schedule_type=form_data["schedule_type"],
            name=form_data["name"],
            recipients=form_data["valid_recipients"],
            day_of_week=form_data["day_of_week"],
            send_time=form_data["send_time"],
            reminder_days_before=form_data["reminder_days"],
            contract_selection_type=_sel_type_code(form_data["contract_selection"]),
            selected_contract_ids=form_data["selected_contract_ids"] or None,
            contract_types=form_data["selected_contract_types"] or None,
            is_active=True,
        )
        if schedule_id:
            current_user = get_current_user()
            log_action(
                user_id=current_user["id"] if current_user else None,
                user_name=current_user["name"] if current_user else "System",
                action_type="create", entity_type="email_schedule",
                entity_id=str(schedule_id), entity_name=form_data["name"],
                action_details=f"Created {form_data['schedule_type']} email schedule",
                ip_address=get_user_ip(),
            )
            st.session_state[MGMT_SUCCESS_FLASH] = (
                f"Notification '{form_data['name']}' created successfully."
            )
            st.session_state.selected_main = EMAIL_NAV_MAIN
            st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
            time.sleep(0.35)
            st.rerun()
        else:
            st.error("Failed to save. Check database connection.")
    except Exception as exc:
        st.error(f"Error saving notification: {exc}")


def _save_notification_edit(form_data: dict, edit_id) -> None:
    from core.db import update_email_schedule
    from mgmt_ui.delete_dialog import MGMT_SUCCESS_FLASH

    errors = []
    if not form_data["name"]:
        errors.append("Configuration name is required.")
    if not form_data["valid_recipients"]:
        errors.append("At least one valid email address is required.")
    if errors:
        for e in errors:
            st.error(e)
        return
    try:
        if update_email_schedule(
            schedule_id=edit_id,
            name=form_data["name"],
            recipients=form_data["valid_recipients"],
            day_of_week=form_data["day_of_week"],
            send_time=form_data["send_time"],
            reminder_days_before=form_data["reminder_days"],
            contract_selection_type=_sel_type_code(form_data["contract_selection"]),
            selected_contract_ids=form_data["selected_contract_ids"] or None,
            contract_types=form_data["selected_contract_types"] or None,
            is_active=form_data["is_active"],
        ):
            current_user = get_current_user()
            log_action(
                user_id=current_user["id"] if current_user else None,
                user_name=current_user["name"] if current_user else "System",
                action_type="edit", entity_type="email_schedule",
                entity_id=str(edit_id), entity_name=form_data["name"],
                action_details=f"Updated email schedule: {len(form_data['valid_recipients'])} recipient(s)",
                ip_address=get_user_ip(),
            )
            st.session_state[MGMT_SUCCESS_FLASH] = "Notification updated successfully."
            st.session_state.pop("email_notification_edit_id", None)
            st.session_state.selected_main = EMAIL_NAV_MAIN
            st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
            time.sleep(0.35)
            st.rerun()
        else:
            st.error("Failed to update. Check database connection.")
    except Exception as exc:
        st.error(f"Error updating notification: {exc}")


def _contract_scope_for_test_queries(form_data: dict):
    """(contract_ids, contract_types) for payment queries: None = no filter (all); [] = empty pick (no rows)."""
    cs = form_data.get("contract_selection")
    if cs == "Select Contracts":
        ids = form_data.get("selected_contract_ids") or []
        if not ids:
            return ([], None)
        return ([str(i) for i in ids], None)
    if cs == "Filter by Type":
        types = form_data.get("selected_contract_types") or []
        if not types:
            return (None, [])
        return (None, list(types))
    return (None, None)


def _send_test_weekly_from_form(form_data: dict) -> None:
    """Send one sample weekly payment email (CSV) using current form filters."""
    recipients = form_data.get("valid_recipients") or []
    if not recipients:
        st.error("Add at least one valid email address.")
        return
    today = datetime.now().date()
    next_week_start, next_week_end = _calendar_week_range_containing(today)
    cids, ctypes = _contract_scope_for_test_queries(form_data)
    if cids is not None and len(cids) == 0:
        st.warning("Select at least one contract, or choose **All Contracts**.")
        return
    if ctypes is not None and len(ctypes) == 0:
        st.warning("Select at least one contract type, or choose **All Contracts**.")
        return
    with st.spinner("Building payment sample and sending..."):
        csv_data = get_payments_csv_for_week(
            next_week_start,
            next_week_end,
            contract_ids=cids,
            contract_types=ctypes,
        )
    if csv_data is None:
        st.error("Could not build the payment export. Check the database connection.")
        return
    subject = f"[TEST] Weekly Payment Report - {next_week_start} to {next_week_end}"
    contracts_df = (
        st.session_state.contracts_df.copy()
        if hasattr(st.session_state, "contracts_df")
        else pd.DataFrame()
    )
    body = _email_html_weekly_body(
        next_week_start,
        next_week_end,
        is_test=True,
        include_contracts_html=_html_include_contracts_scope(
            form_data.get("contract_selection") or "All Contracts",
            contracts_df,
            form_data.get("selected_contract_ids"),
            form_data.get("selected_contract_types"),
        ),
    )
    if send_email_via_smtp(
        recipients,
        subject,
        body,
        csv_data=csv_data,
        csv_filename=f"payments_{next_week_start}_{next_week_end}.csv",
    ):
        st.success("Sample weekly email sent.")
        current_user = get_current_user()
        log_action(
            user_id=current_user["id"] if current_user else None,
            user_name=current_user["name"] if current_user else "System",
            action_type="test_email",
            entity_type="weekly_payment_email",
            entity_id=None,
            entity_name=None,
            action_details=f"Test weekly notification email to {len(recipients)} recipient(s)",
            ip_address=get_user_ip(),
        )


def _send_test_reminder_from_form(form_data: dict) -> None:
    """Send one sample payment reminder email using payments.payment_date in the look-ahead window."""
    recipients = form_data.get("valid_recipients") or []
    if not recipients:
        st.error("Add at least one valid email address.")
        return
    try:
        reminder_days = int(form_data.get("reminder_days") or 30)
    except (TypeError, ValueError):
        reminder_days = 30
    cids, ctypes = _contract_scope_for_test_queries(form_data)
    if cids is not None and len(cids) == 0:
        st.warning("Select at least one contract, or choose **All Contracts**.")
        return
    if ctypes is not None and len(ctypes) == 0:
        st.warning("Select at least one contract type, or choose **All Contracts**.")
        return
    with st.spinner("Loading payments and sending..."):
        upcoming = get_upcoming_payments_for_reminder_window(reminder_days, cids, ctypes)
    rem_csv = _reminder_payments_export_csv(upcoming)
    subject = f"[TEST] Payment Reminder - next {reminder_days} days"
    body = _email_html_reminder_body(
        reminder_days,
        is_test=True,
        summary_html=_reminder_payments_summary_html(upcoming),
    )
    if send_email_via_smtp(
        recipients,
        subject,
        body,
        csv_data=rem_csv,
        csv_filename=f"payment_reminder_{reminder_days}d.csv",
    ):
        st.success("Sample reminder email sent.")
        current_user = get_current_user()
        log_action(
            user_id=current_user["id"] if current_user else None,
            user_name=current_user["name"] if current_user else "System",
            action_type="test_email",
            entity_type="contract_reminder",
            entity_id=None,
            entity_name=None,
            action_details=(
                f"Test payment reminder email to {len(recipients)} recipient(s), "
                f"{len(upcoming)} payment line(s) in sample"
            ),
            ip_address=get_user_ip(),
        )


def render_create_weekly_payment_notification():
    """Full-page create flow for weekly payment email schedules."""
    require_permission("email.configure")
    load_all()
    contracts_df = (
        st.session_state.contracts_df.copy()
        if hasattr(st.session_state, "contracts_df")
        else pd.DataFrame()
    )
    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("\u2190 Notifications Center", key="email_create_weekly_back"):
            st.session_state.selected_main = EMAIL_NAV_MAIN
            st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
            st.rerun()
    st.header("Create Weekly Payment Notification")
    form_data = _notification_form(
        None, "create_email_weekly", contracts_df, fixed_schedule_type="weekly_payment"
    )
    st.markdown("---")
    st.caption(
        "**Send test email** — one-off sample using the **calendar week (Mon–Sun) that contains today** "
        "and current contract filters. Does not save this notification."
    )
    tcol, sv, cn = st.columns([1.15, 1, 3.85])
    with tcol:
        if st.button("Send test email", key="btn_email_create_weekly_test"):
            _send_test_weekly_from_form(form_data)
    with sv:
        if st.button("Save", key="btn_email_create_weekly_save", type="primary"):
            _save_notification_create(form_data)
    with cn:
        if st.button("Cancel", key="btn_email_create_weekly_cancel"):
            st.session_state.selected_main = EMAIL_NAV_MAIN
            st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
            st.rerun()


def render_create_contract_reminder_notification():
    """Full-page create flow for contract reminder email schedules."""
    require_permission("email.configure")
    load_all()
    contracts_df = (
        st.session_state.contracts_df.copy()
        if hasattr(st.session_state, "contracts_df")
        else pd.DataFrame()
    )
    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("\u2190 Notifications Center", key="email_create_reminder_back"):
            st.session_state.selected_main = EMAIL_NAV_MAIN
            st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
            st.rerun()
    st.header("Create Contract Reminder")
    form_data = _notification_form(
        None, "create_email_reminder", contracts_df, fixed_schedule_type="contract_reminder"
    )
    st.markdown("---")
    st.caption(
        "**Send test email** — sample listing **payment lines** from the payments table whose "
        "**payment date** falls in the next X days (and current contract filters). Does not save."
    )
    tcol, sv, cn = st.columns([1.15, 1, 3.85])
    with tcol:
        if st.button("Send test email", key="btn_email_create_reminder_test"):
            _send_test_reminder_from_form(form_data)
    with sv:
        if st.button("Save", key="btn_email_create_reminder_save", type="primary"):
            _save_notification_create(form_data)
    with cn:
        if st.button("Cancel", key="btn_email_create_reminder_cancel"):
            st.session_state.selected_main = EMAIL_NAV_MAIN
            st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
            st.rerun()


def render_edit_email_notification():
    """Full-page edit flow; target id from session ``email_notification_edit_id``."""
    require_permission("email.configure")
    load_all()
    from core.db import get_email_schedules

    eid = st.session_state.get("email_notification_edit_id")
    if not eid:
        st.session_state.selected_main = EMAIL_NAV_MAIN
        st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
        st.rerun()
        return

    schedules = get_email_schedules() or []
    schedule = next((s for s in schedules if str(s.get("id")) == str(eid)), None)
    if not schedule:
        st.error("Notification not found.")
        st.session_state.pop("email_notification_edit_id", None)
        st.session_state.selected_main = EMAIL_NAV_MAIN
        st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
        st.rerun()
        return

    contracts_df = (
        st.session_state.contracts_df.copy()
        if hasattr(st.session_state, "contracts_df")
        else pd.DataFrame()
    )
    bc1, _ = st.columns([1, 4])
    with bc1:
        if st.button("\u2190 Notifications Center", key="email_edit_back"):
            st.session_state.pop("email_notification_edit_id", None)
            st.session_state.selected_main = EMAIL_NAV_MAIN
            st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
            st.rerun()

    st.header(f"Edit: {schedule.get('name', '')}")
    form_data = _notification_form(schedule, f"edit_email_{eid}", contracts_df)
    st.markdown("---")
    st.caption(
        "**Send test email** — weekly: current calendar week + CSV; reminder: payments with **payment date** "
        "in the look-ahead window. Does not save changes."
    )
    tcol, sv, cn = st.columns([1.15, 1, 3.85])
    with tcol:
        if st.button("Send test email", key=f"btn_email_edit_test_{eid}"):
            if form_data.get("schedule_type") == "weekly_payment":
                _send_test_weekly_from_form(form_data)
            else:
                _send_test_reminder_from_form(form_data)
    with sv:
        if st.button("Save changes", key="btn_email_edit_page_save", type="primary"):
            _save_notification_edit(form_data, eid)
    with cn:
        if st.button("Cancel", key="btn_email_edit_page_cancel"):
            st.session_state.pop("email_notification_edit_id", None)
            st.session_state.selected_main = EMAIL_NAV_MAIN
            st.session_state.selected_sub = EMAIL_NAV_SUB_MGMT
            st.rerun()


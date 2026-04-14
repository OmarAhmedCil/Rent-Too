# Contract Management Tool — Technical Team Documentation

**Last Updated:** April 2026

---

## Table of Contents
1. [Technology Stack](#technology-stack)
2. [Installation & Setup](#installation--setup)
3. [Configuration](#configuration)
4. [Application Architecture](#application-architecture)
5. [Database Management](#database-management)
6. [Security](#security)
7. [Deployment](#deployment)
8. [Performance](#performance)
9. [Maintenance & Troubleshooting](#maintenance--troubleshooting)
10. [Development Guidelines](#development-guidelines)

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend / Server | Streamlit (Python) |
| Language | Python 3.10+ |
| Database | MySQL 8.x |
| Auth | bcrypt password hashing, custom RBAC |
| Data processing | Pandas |
| Excel export | OpenPyXL |
| Email | smtplib / schedule |
| CSS theming | Custom `style.css` + `.streamlit/config.toml` |

---

## Installation & Setup

### Prerequisites
- Python 3.10+
- MySQL 8.x
- pip

### Steps

```bash
# 1. Clone / copy the project
cd "Contract tool"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create the database
mysql -u root -p -e "CREATE DATABASE contract_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 4. Run the schema (from project root)
mysql -u omar -p contract_db < database/schema.sql

# 5. Start the app
streamlit run app.py
```

### Default Admin Account
- **Email:** `admin@contracttool.com`
- **Password:** `admin123`
- Change immediately after first login.

---

## Configuration

### Database — `conf/database.py` (`DB_CONFIG`)
Connection settings are built from environment variables (see `.env.example`). Defaults exist for local dev only — override in production via `MYSQL_*`.

### Streamlit Theme — `.streamlit/config.toml`
```toml
[theme]
primaryColor     = "#FFD700"
backgroundColor  = "#ffffff"
secondaryBackgroundColor = "#f9f9f9"
textColor        = "#111111"
```

### Table Names & Columns — `conf/constants.py`
All DB table names and their column lists are defined here. Changing a table name requires updating `conf/constants.py` **and** `database/schema.sql`, plus your own upgrade path for existing databases (see `database/migrations/README.md`).

---

## Application Architecture

### Routing (`app.py`)
`app.py` reads `st.session_state.selected_main` and `selected_sub` to route to the correct page module. Each section is a conditional block:

```python
elif selected_main == "💳 Payments":
    if selected_sub == "Payment Center":
        render_payment_management()
    elif selected_sub == "Edit Payment":
        render_edit_payment()
```

"Edit Payment" is not shown in the sidebar but is a valid programmatic destination set by the Payment Center row's Edit button.

### Session State
Key session state variables:

| Key | Set by | Consumed by |
|---|---|---|
| `selected_main`, `selected_sub` | Sidebar nav | app.py router |
| `payments_edit_target_id` | Payment Center Edit button | render_edit_payment (consumed on first run) |
| `payments_editing_id` | render_edit_payment | render_edit_payment, get_contract_selection_for_payment |
| `contracts_df`, `lessors_df`, … | `load_all()` in `core/utils.py` | All pages |
| `lessor_withholding_periods_df` | `load_all()` | Payment save logic |

### Distribution Tables
Three separate tables — one per contract type:

| Contract Type | Table |
|---|---|
| Fixed | `contract_distribution_fixed` |
| Revenue Share | `contract_distribution_revenue_share` |
| ROU | `contract_distribution_rou` |

`get_distribution_table(contract_type)` in `core/utils.py` returns the correct table name. It raises `ValueError` for unrecognised types.

### Payment Records
Contract distribution is **one row per contract per month** in the type-specific table (**contract-level** amounts; no `lessors_json`). After distribution is generated or edited, `create_payment_records_from_distribution()` in `core/utils.py` rebuilds **`payments`**: **one row per lessor** (and service splits) per payment date, with **`rent_month`** (first of rent month), **`amount`** (gross line), **`due_amount`** (net), and **`lessor_share_pct`**. When loading from DB only, **`rebuild_distribution_rows_for_payments()`** regenerates per-lessor lines from the same engine and scales to saved month rows.

### Withholding Tax Logic
- Default: 3% of `lessor_due_amount`
- Exempt if payment date falls within any row in `lessor_withholding_periods` for that `lessor_id`
- Applied during distribution generation and on Edit Payment save

---

## Database Management

### Schema Updates
1. Edit `database/schema.sql` for **new installs** and extend **`ensure_v2_distribution_payment_schema()`** / related helpers in `core/db.py` when you need **additive** upgrades on existing databases.
2. For non-additive changes, plan manual `ALTER` / rebuild steps per environment (see `database/migrations/README.md`); numbered repo migrations are no longer maintained here.
3. Commit updated `database/schema.sql` and `core/db.py` (and docs) to source control.

### Backup
```bash
# Full backup
mysqldump -u omar -p contract_db > backup_$(date +%Y%m%d).sql

# Restore
mysql -u omar -p contract_db < backup_YYYYMMDD.sql
```

### Indexes
Key indexes (defined in `database/schema.sql`):
- `contract_distribution_*`: **unique** `(contract_id, rent_date)` for contract-month grain
- `payments`: `(contract_id)`, `(payment_date)`, `(rent_month)`, `(contract_id, lessor_id, rent_month)`
- `action_logs`: `(user_id, action_type, created_at)`

---

## Security

### Authentication
- Passwords hashed with **bcrypt** (12 rounds)
- Sessions managed by Streamlit session state
- Inactive users (`is_active = 0`) cannot log in

### Authorization (RBAC)
- Every page starts with `require_permission("module.action")`
- Permissions are stored in the DB in the `permissions`, `role_permissions`, `user_roles` tables
- `admin.all` grants all permissions

### Credential Management
- DB settings are built in `conf/database.py` from `MYSQL_*` env vars — do not commit production passwords to source control
- Use environment variables or a secrets manager in production (see `.env.example`)

---

## Deployment

### Local Development
```bash
streamlit run app.py
```

### Production (Linux / systemd)
```ini
# /etc/systemd/system/contract-tool.service
[Unit]
Description=Contract Management Tool
After=network.target mysql.service

[Service]
User=www-data
WorkingDirectory=/opt/contract-tool
ExecStart=/usr/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
systemctl enable contract-tool
systemctl start contract-tool
```

### Reverse Proxy (nginx)
```nginx
server {
    listen 80;
    server_name contracts.yourcompany.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## Performance

- **Session state caching**: `load_all()` loads master dataframes once per session; subsequent calls are no-ops unless explicitly cleared.
- **Distribution tables**: monthly contract rows plus optional legacy per-lessor rows — indexes on `(contract_id, rent_date)` and `(contract_id, rent_date, lessor_id)` support both shapes.
- **`st.table` vs `st.dataframe`**: The app uses `st.table` for display-only data (no interactive Glide grid overhead). Interactive `st.dataframe` is used only where needed (main payments download view).
- **CSS**: Heavy use of `!important` overrides in `style.css` can slow style recalculation on very large pages — keep selector specificity as targeted as possible.

---

## Maintenance & Troubleshooting

### App won't start
- Check Python version: `python --version` (need 3.10+)
- Check dependencies: `pip install -r requirements.txt`
- Check DB connection: verify MySQL is running and `MYSQL_*` / `conf/database.py` settings are correct

### Streamlit theme not applying
- Requires full **restart** of the Streamlit process when `.streamlit/config.toml` changes

### Payments not generated after distribution
- Ensure the `payments` table matches `database/schema.sql` (including `tax_*`, `withholding_amount`, and `lessor_share_pct`)
- Then regenerate distribution for the affected contract

### "Invalid contract type" error on save
- Contract type must be exactly `"Fixed"`, `"Revenue Share"`, or `"ROU"` — check for trailing spaces or casing issues

---

## Development Guidelines

### Adding a New Page
1. Create a render function in the appropriate subpackage (e.g. `weekly_payments_ui/new_page.py`)
2. Export it from the package `__init__.py`
3. Add the page name to `main_sections` in `app.py` (sidebar) if it should be directly navigable
4. Add the routing `elif selected_sub == "New Page"` block in `app.py`
5. Add `require_permission("module.action")` as the first line of the render function

### Adding a New Permission
1. Add the permission string to `core/permissions.py` `PERMISSIONS` dict
2. Seed the row in the `permissions` table (via UI admin flows or `INSERT` as appropriate for your environment)
3. Assign the permission to appropriate roles via the UI

### CSS Conventions
- Global styles: `style.css`
- Scoped button overrides: keyed selectors `[class*="st-key-<key>"] button`
- Number input steppers: `.stNumberInput button` — background `#f0f0f0`, no full border
- Never set `use_container_width=True` on action buttons — use scoped CSS `width: auto`

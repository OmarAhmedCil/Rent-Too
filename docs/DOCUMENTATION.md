# Contract Management Tool — Complete Documentation

**Last Updated:** April 2026  
**Version:** 3.0

---

## Table of Contents
1. [Overview](#overview)
2. [Application Structure](#application-structure)
3. [Database Schema](#database-schema)
4. [Contract Types & Calculations](#contract-types--calculations)
5. [Navigation & Pages](#navigation--pages)
6. [Technical Details](#technical-details)
7. [Calculation Logic](#calculation-logic)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The **Contract Management Tool** is a Streamlit + MySQL web application for managing lease contracts, lessors, assets, stores, and services. It supports Fixed, Revenue Share, and ROU (IFRS 16) contract types with full financial calculation, payment tracking, and audit logging.

### Key Capabilities
- Contract lifecycle management (create / edit / delete) with multi-lessor support
- Automated monthly distribution calculation for all contract types
- Payment management with per-row discount and advance editing
- Per-lessor withholding tax exemption periods
- Bulk import of contracts via Excel template
- Email scheduling for weekly payment reports and payment-date reminders (upcoming `payments.payment_date` window)
- Role-based access control (RBAC) and full audit trail
- Excel / CSV data export

---

## Application Structure

```
Contract Tool/
├── app.py                          # Main entry point, routing, sidebar nav
├── conf/                           # constants.py (tables/columns), database.py (MySQL + whitelist)
├── core/                           # db.py, utils.py, auth.py, permissions.py, paths.py
├── static/
│   └── style.css                   # Global CSS theme
├── requirements.txt                # Python dependencies
├── database/
│   ├── schema.sql                  # MySQL schema (CREATE TABLE) for new installs
│   └── migrations/
│       └── README.md               # Upgrade policy (numbered SQL scripts removed; use schema.sql + startup DDL)
├── bulk_import_ui/               # bulk_import.py — bulk contract import logic
├── dashboard/                      # Dashboard widgets (package)
│   └── __init__.py
├── mgmt_ui/                        # Shared management UI (dialogs, hub buttons, scoped CSS)
│   ├── hub_ui.py
│   ├── button_styles.py
│   └── delete_dialog.py
│
├── .streamlit/
│   └── config.toml                 # Theme (primaryColor, fonts, etc.)
│
├── docs/                           # ← All documentation lives here
│   ├── DOCUMENTATION.md            # This file — full technical reference
│   ├── DOCUMENTATION_END_USER.md   # End-user guide
│   ├── DOCUMENTATION_TECH_TEAM.md  # Ops / deployment guide
│   └── DOCUMENTATION_DATA_ENGINEER.md  # DB schema & integration guide
│
├── contracts/                      # Contract management pages
│   ├── create.py
│   ├── edit.py
│   ├── delete_page.py
│   └── management.py
│
├── lessors/                        # Lessor management pages
│   ├── create.py, edit.py, delete_page.py, management.py
│
├── assets/                         # Asset management pages
│   ├── create.py, edit.py, delete_page.py, management.py
│
├── services/                       # Service management pages
│   ├── create.py, edit.py, delete_page.py, management.py
│
├── user_accounts/                  # User management pages
│   ├── create.py, edit.py, delete_page.py, management.py
│
├── roles_admin/                    # Role & permission management
│   ├── management.py, role_management.py, manage_permissions.py
│   ├── role_permissions_ui.py, assign_user_roles.py, create_role.py, edit_role.py
│
├── distribution/                   # Distribution generation pages
│   ├── management.py               # Contracts Distribution hub
│   ├── generate_page.py
│   ├── regenerate_page.py
│   ├── edit_page.py
│   ├── delete_page.py
│   ├── delete_dialog.py
│   ├── bulk_action_dialog.py
│   ├── dist_work_modal.py
│   ├── run_workflow.py
│   └── helpers.py
│
├── weekly_payments_ui/             # Payment management pages
│   ├── management.py               # Payment Center hub (contract list + Edit button)
│   └── __init__.py
│
├── audit_logs/
│   └── management.py
├── bulk_import_ui/
│   └── management.py
├── email_center/
│   └── management.py
├── download_center/
│   └── management.py
│
└── tabs/                           # Tab routers (sidebar sections / re-exports)
    ├── contracts.py, lessors.py, assets.py, services.py
    ├── users.py, roles.py, action_logs.py
    ├── download_data.py, email_notifications.py, weekly_payments.py
    └── __init__.py
```

---

## Database Schema

### Schema upgrades

- **New database:** apply `database/schema.sql` (creates `contract_db` and all tables).
- **Existing database:** see `database/migrations/README.md`. Numbered migration `.sql` files are no longer shipped in this repo; use **`initialize_database()`** for **additive** sync (`ensure_v2_distribution_payment_schema()` via `ensure_monthly_distribution_and_payment_schema()` in `core/db.py`) and align remaining differences with **`database/schema.sql`** using your own DBA process (or recover old scripts from git history if needed).

### Tables

#### `lessors`
| Column | Type | Notes |
|---|---|---|
| id | VARCHAR(50) PK | UUID |
| name | VARCHAR(255) | Required |
| description | TEXT | Optional |
| tax_id | VARCHAR(100) | |
| supplier_code | VARCHAR(100) | |
| iban | VARCHAR(100) | Bank account for payments |

#### `lessor_withholding_periods`
Per-lessor windows during which withholding tax is **not** deducted.
| Column | Type | Notes |
|---|---|---|
| id | INT AUTO_INCREMENT PK | |
| lessor_id | VARCHAR(50) | FK → lessors |
| start_date | DATE | Exemption window start |
| end_date | DATE | Exemption window end |

#### `assets`
| Column | Type |
|---|---|
| id | VARCHAR(50) PK |
| name | VARCHAR(255) |
| cost_center | VARCHAR(100) |

#### `stores`
| Column | Type |
|---|---|
| id | VARCHAR(50) PK |
| name | VARCHAR(255) |
| cost_center | VARCHAR(100) |

#### `contracts`
| Column | Type | Notes |
|---|---|---|
| id | VARCHAR(50) PK | |
| contract_name | VARCHAR(255) | |
| contract_type | VARCHAR(50) | Fixed / Revenue Share / ROU |
| currency | VARCHAR(10) | EGP / USD |
| asset_category | VARCHAR(50) | Store / Other |
| asset_or_store_id | VARCHAR(50) | |
| asset_or_store_name | VARCHAR(255) | |
| commencement_date | DATE | |
| tenure_months | VARCHAR(50) | Total contract months |
| end_date | DATE | |
| discount_rate | VARCHAR(50) | Annual % — ROU only |
| tax | VARCHAR(50) | Tax % |
| is_tax_added | TINYINT(1) | Tax on top vs included |
| payment_frequency | VARCHAR(50) | Monthly / Quarter / Yearly |
| yearly_increase | VARCHAR(50) | Annual increase % |
| yearly_increase_type | VARCHAR(50) | Percentage / Fixed Amount |
| yearly_increase_fixed_amount | VARCHAR(50) | Fixed increase amount |
| increase_by_period_mode | VARCHAR(30) | Custom per-period increase mode |
| increase_by_period_all_pct | VARCHAR(50) | Applied to all periods |
| increase_by_period_map | TEXT | JSON map of period→pct |
| rent_amount | VARCHAR(50) | Monthly rent — Fixed & ROU |
| rev_min | VARCHAR(50) | Revenue minimum — RevShare |
| rev_max | VARCHAR(50) | Revenue maximum — RevShare |
| rev_share_pct | VARCHAR(50) | Share % — RevShare |
| rev_share_after_max_pc | VARCHAR(50) | Share % above max — RevShare |
| sales_type | VARCHAR(50) | Net / Total without discount |
| rent_per_year | TEXT | JSON rent schedule — ROU |
| first_payment_date | DATE | First payment date |
| free_months | VARCHAR(255) | Comma-separated period numbers |
| advance_months | VARCHAR(255) | Comma-separated period numbers (ROU) |
| advance_months_count | VARCHAR(50) | Count of advance periods |
| advance_payment | VARCHAR(50) | Advance payment amount |
| lessors_json | TEXT | JSON payload for lessors attached to the contract (shares and related fields; app-defined format) |
| created_at | DATETIME | |

#### `contract_lessors`
| Column | Type |
|---|---|
| contract_id | VARCHAR(50) FK |
| lessor_id | VARCHAR(50) FK |
| share_pct | VARCHAR(50) |
| PK | (contract_id, lessor_id) |

#### `contract_distribution_fixed`
One **monthly** row per **contract** (`rent_date` = first of month). **Contract-level** amounts only (no lessor columns, no `lessors_json`). Tax and withholding are in `payments`. UI joins `contracts` / assets / stores for names.
| Column | Type |
|---|---|
| id | INT AUTO_INCREMENT PK |
| contract_id | VARCHAR(50) |
| rent_date | DATE |
| rent_amount | VARCHAR(50) |
| yearly_increase_amount | VARCHAR(50) | Currency added per contract year on monthly rent (from % or fixed-amount rules) |
| discount_amount | VARCHAR(50) | Contract-month discount / free-month waiver total; Payment Center edits roll up here |
| advanced_amount | VARCHAR(50) | Same |
| due_amount | VARCHAR(50) | Contract-month total due (sum of lessor lines in the engine) |
| created_at | TIMESTAMP |

#### `contract_distribution_revenue_share`
Same **monthly** grain as Fixed; adds revenue-band columns; still **one row per contract per month**. Revenue share **percentages** are not stored here — they come from **`contracts`** (`rev_share_pct`, `rev_share_after_max_pc`) and appear in grids/exports as **`revenue_share_pct`** / **`revenue_share_after_max_pct`** via **`JOIN`** when loading the table.
| Column | Type |
|---|---|
| id | INT AUTO_INCREMENT PK |
| contract_id, rent_date | — |
| rent_amount | VARCHAR(50) |
| yearly_increase_amount | — |
| revenue_min, revenue_max | — |
| revenue_amount | VARCHAR(50) |
| discount_amount, advanced_amount, due_amount | VARCHAR(50) |
| created_at | TIMESTAMP |

#### `contract_distribution_rou`
One row per **contract** per **month**; ROU (IFRS 16) schedule columns at contract-month level; **`due_amount`** holds rolled-up lessor due for the month.
| Column | Type |
|---|---|
| id | INT AUTO_INCREMENT PK |
| contract_id, rent_date | — |
| rent_amount | VARCHAR(50) |
| yearly_increase_amount | — |
| opening_liability, interest, closing_liability | IFRS 16 liability schedule |
| principal, rou_depreciation | — |
| period | VARCHAR(50) |
| lease_accrual, pv_of_lease_payment | — |
| discount_amount, advanced_amount | VARCHAR(50) |
| advance_coverage_flag | VARCHAR(10) |
| due_amount | VARCHAR(50) |
| created_at | TIMESTAMP |

#### `payments`
One row per **lessor line** (or **service** split) per **payment date**. **`rent_month`** = first day of the rent month. **`amount`** = gross line before discount/advance; **`due_amount`** = net after discount/advance. **`lessor_id`** is required on new rows. Contract currency comes from **`contracts.currency`** (no `currency` column on new schema). **`payment_type`** is not stored on new schema (derive: service line if `service_id` set). **`lessor_share_pct`** stores the line’s share % when the payment is created.
| Column | Type |
|---|---|
| id | INT AUTO_INCREMENT PK |
| contract_id | VARCHAR(50) |
| lessor_id | VARCHAR(50) NOT NULL |
| rent_month | DATE | First day of rent month |
| payment_date | DATE |
| amount | VARCHAR(50) | Gross before discount/advance |
| due_amount | VARCHAR(50) | Net due for the line |
| payment_amount | VARCHAR(50) |
| service_id | VARCHAR(50) NULL |
| tax_pct | VARCHAR(50) |
| tax_amount | VARCHAR(50) |
| withholding_amount | VARCHAR(50) |
| lessor_share_pct | VARCHAR(50) NULL | Lessor share % for the line |
| created_at | TIMESTAMP |

#### `store_monthly_sales`
| Column | Type |
|---|---|
| id | INT PK |
| store_id | VARCHAR(50) FK → stores |
| rent_date | DATE |
| net_sales, total_sales | VARCHAR(50) |

#### `services`
| Column | Type |
|---|---|
| id | VARCHAR(50) PK |
| name | VARCHAR(255) |
| description | TEXT |
| currency | VARCHAR(10) |

#### `contract_services`
| Column | Type |
|---|---|
| contract_id | FK → contracts |
| service_id | FK → services |
| amount | VARCHAR(50) |
| yearly_increase_pct | VARCHAR(50) |

#### `contract_service_lessors`
| Column | Type |
|---|---|
| contract_id, service_id, lessor_id | Composite PK |
| share_pct | VARCHAR(50) |

#### `service_distribution`
One row per **`(contract_id, service_id, rent_date)`**. **`amount`**, **`discount_amount`**, **`due_amount`** at line level (no `services_json`). Service name comes from JOIN to **`services`** in the app.
| Column | Type |
|---|---|
| id | INT PK |
| contract_id | VARCHAR(50) |
| service_id | VARCHAR(50) |
| rent_date | DATE |
| amount | VARCHAR(50) |
| discount_amount | VARCHAR(50) |
| due_amount | VARCHAR(50) |
| created_at | TIMESTAMP |

#### `users`, `roles`, `permissions`, `role_permissions`, `user_roles`
Standard RBAC tables — see `database/schema.sql` for full DDL.

#### `action_logs`
| Column | Type |
|---|---|
| id | INT PK |
| user_id, user_name | Who |
| action_type | create / edit / delete / generate / regenerate / download / login / logout / bulk_import |
| entity_type, entity_id, entity_name | What |
| action_details | TEXT |
| ip_address, created_at | — |

#### `email_schedules`
| Column | Type |
|---|---|
| id | INT PK |
| schedule_type | weekly_payment / contract_reminder |
| name | VARCHAR(255) |
| recipients | TEXT (comma-separated emails) |
| day_of_week, send_time | Schedule |
| reminder_days_before | INT |
| contract_selection_type | all / selected / filtered |
| selected_contract_ids, contract_types | TEXT |
| is_active | BOOLEAN |
| last_sent_at, created_at, updated_at | DATETIME |

---

## Contract Types & Calculations

### Fixed Contracts
Standard lease with fixed monthly rent.

- Yearly increase compounded annually from commencement date
- Free months: rent = 0, discount applied (negative discount value)
- `lessor_due_amount = rent × share_pct/100 − discount_amount − advanced_amount`
- Tax and withholding calculated and stored in `payments` table

### Revenue Share Contracts
Rent derived from actual store revenue.

- `rent = max(rev_min, actual_revenue) × rev_share_pct / 100`
- Above `rev_max`: `rent = rev_max + (excess × rev_share_after_max_pct / 100)`
- Revenue sourced from `store_monthly_sales` table
- Discount/advance columns exist on the table but Payment Center editing is read-only for this type in the UI

### ROU Contracts (IFRS 16)
Full right-of-use lease accounting.

- Initial ROU asset = PV of all lease payments at commencement
- Monthly: interest on opening liability, principal reduction, closing liability
- Straight-line depreciation over tenure
- `discount_amount` and `advanced_amount` editable via Payment Center

### Withholding Tax
- Default withholding rate: **3%** on `lessor_due_amount`
- Exempted if payment date falls within a `lessor_withholding_periods` window for that lessor
- Applies to Fixed and ROU contracts; stored in `payments.withholding_amount`

---

## Navigation & Pages

### Sidebar Sections

| Section | Sub-pages | Permission |
|---|---|---|
| 🏠 Dashboard | — | `contracts.view` |
| 📄 Contracts | Contract Management | `contracts.view` |
| 👥 Lessors | Lessor Management | `lessors.view` |
| 🏢 Assets | Asset Management | `assets.view` |
| 🛠️ Services | Service Management | `services.view` |
| 📊 Distribution | Contracts Distribution | `distribution.view` |
| 💳 Payments | Payment Center | `payments.view` |
| 📧 Email Notifications | Notifications Center, Weekly Payment Emails, Payment Reminders | `email.view` |
| 📥 Bulk Import | Data Upload | `bulk_import.view` |
| 📤 Download Data | Reports Center | `download.view` |
| 👤 Users | User Management | `users.view` |
| 🔐 Roles | Role Management | `roles.view` |
| 📋 Action Logs | Log Report | `logs.view` |

### Payment Center Flow
1. **💳 Payments → Payment Center**: table of all contracts with an **Edit** button per row
2. Clicking **Edit** sets `payments_edit_target_id` in session state and navigates to **Edit Payment** (not shown in sidebar)
3. **Edit Payment** page shows an inline table with read-only columns (Date, Lessor, Rent Amount, Lessor Due) and editable inputs (Discount, Advance) — editable for Fixed and ROU contracts
4. Validation: `discount + advance ≤ rent_amount` enforced per row (widget max + server-side check)
5. On save: `lessor_due_amount`, `discount_amount`, `advanced_amount` written to the appropriate distribution table; payments regenerated; redirected back to Payment Center
6. **← Payment Center** button returns to Payment Center without saving

### Dashboard

- **Entity counts** (contracts, lessors, assets, stores, services) and contract-type breakdowns.
- **Due Amounts** — KPI cards for distribution **due** totals (EGP and USD): upcoming (from the start of the current month forward), this calendar month, and this calendar year, using contract currency (blank → EGP).

### Payment reminder emails (`tabs/email_notifications.py`, `core/email_schedule_runner.py`)

- **Window:** `payments.payment_date` from **today** through **today + N days** (inclusive), with the same contract scope as the saved schedule (all / selected IDs / filtered types).
- **Attachment:** CSV of payment lines (same column layout as weekly payment exports).
- **HTML body:** Short greeting + **summary only**: total rent vs **service** payments in EGP/USD, grand totals for the window, and **unique counts** (branches/stores, assets, contracts by type, lessors) computed **only from rows in that attachment** (e.g. one lessor with five lines counts once). No per-line list and no “Include contracts” block in the email.

---

## Technical Details

### Session State Keys (key subset)
| Key | Purpose |
|---|---|
| `payments_editing_id` | Contract ID currently being edited in Edit Payment |
| `payments_edit_target_id` | Transient: set by management row, consumed by Edit Payment |
| `selected_main`, `selected_sub` | Current sidebar navigation state |
| `contracts_df`, `lessors_df`, … | Cached DataFrames for all master tables |
| `lessor_withholding_periods_df` | Cached withholding periods |

### Permissions Reference
| Module | Permissions |
|---|---|
| contracts | view, create, edit, delete |
| lessors | view, create, edit, delete |
| assets | view, create, edit, delete |
| stores | view, create, edit, delete |
| services | view, create, edit, delete |
| distribution | view, generate, edit, delete |
| payments | view, edit, export |
| download | view, export |
| bulk_import | view, import |
| users | view, create, edit, delete |
| roles | view, create, edit, delete, assign |
| logs | view |
| email | view, configure, send |
| admin | all |

### Theme
Configured in `.streamlit/config.toml`:
- `primaryColor = "#FFD700"` — yellow (matches button palette)
- `backgroundColor = "#ffffff"`
- `textColor = "#111111"`

---

## Calculation Logic

### Lessor Due Amount (Fixed / ROU)
```
lessor_due = rent_amount × (share_pct / 100) − discount_amount − advanced_amount
lessor_due = max(0, lessor_due)
```

### Withholding Amount
```
if payment_date within any lessor_withholding_periods row for lessor:
    withholding = 0
else:
    withholding = lessor_due × 0.03  # 3% default
```

### Payment Date
```
if frequency == "Yearly":   months_offset = 12 × ((period - 1) // 12)
if frequency == "Quarter":  months_offset = 3  × ((period - 1) // 3)
if frequency == "Monthly":  months_offset = (period - 1)
payment_date = (first_payment_date + months_offset).replace(day=1)
```

### ROU Present Value
```
r = annual_discount_rate / 12 / 100
PV = Σ ( rent_i / (1 + r)^(i-1) )   for i in non-free, non-advance periods
initial_rou_asset = PV + advance_months × rent_period_1
monthly_depreciation = initial_rou_asset / tenure_months
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Payments not appearing | Schema missing columns on `payments` or distribution tables | Align DB with `database/schema.sql`, or start the app once so `initialize_database()` applies additive DDL; see `database/migrations/README.md` |
| Edit Payment shows read-only table | Contract type = Revenue Share (no discount/advance columns) | Expected behaviour |
| Distribution not generating | Missing lessors, invalid dates, missing revenue data | Validate contract fields |
| ROU calculations wrong | discount_rate = 0, free_months format wrong | Verify comma-separated period numbers |
| DB connection error | MySQL not running / wrong credentials | Check `conf/database.py` (`DB_CONFIG`) and MySQL |
| "Total lessor shares must equal 100%" | Rounding in share percentages | Adjust shares to exactly 100.0 |

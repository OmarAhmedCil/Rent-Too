# Developer guide — Contract Tool

Quick orientation for anyone continuing work on this application: **where code lives**, **how navigation works**, and **what to touch** for common changes.

---

## 1. Start here

| Item | Location |
|------|----------|
| **App entrypoint** | `app.py` — Streamlit loads this file; it calls `initialize_database()`, `require_login()`, builds the sidebar, and routes `selected_main` / `selected_sub` to the right screen. |
| **Run locally** | `streamlit run app.py` (from project root). Dependencies: `requirements.txt`. |
| **Global styling** | `static/style.css` (injected in `app.py` via `local_css`). Extra button/dialog CSS: `mgmt_ui/button_styles.py`. |
| **Constants & table/column names** | `conf/constants.py` — DB table keys, `*_COLS` lists used across `core/db.py` / `core/utils.py`. |
| **Database access** | `core/db.py` — connections, CRUD helpers, `load_table_to_df`, `initialize_database` (runs additive schema sync). Env-driven `DB_CONFIG` / table whitelist: `conf/database.py`. Canonical DDL: `database/schema.sql`; upgrade notes: `database/migrations/README.md`. See `.env.example` and `docs/DEPLOYMENT.md`. |
| **Business logic (contracts / distribution / payments)** | `core/utils.py` — large file: distribution generation, ROU schedules, payment creation from distribution, helpers `get_distribution_table`, `load_distribution_for_contract`, etc. |
| **Auth** | `core/auth.py` — login, session user, `require_login`. |
| **Permissions** | `core/permissions.py` — `PERMISSIONS` dict (keys like `contracts.view`), `has_permission`, `require_permission`. |

---

## 2. Repository layout (by folder)

```
Project root/
├── app.py                 # Main Streamlit app + routing
├── conf/                  # `constants.py` (tables/columns), `database.py` (MySQL env + whitelist)
├── core/                  # db, utils, auth, permissions, paths (project root resolution)
├── bulk_import_ui/        # `bulk_import.py` — Excel bulk import (contracts + master data)
├── static/style.css       # Global CSS
├── database/
│   ├── schema.sql         # Full DDL for new databases
│   └── migrations/        # README (upgrade policy; numbered SQL removed)
├── dashboard/             # Home dashboard
├── contracts/             # Contract CRUD + management hub
├── lessors/               # Lessor CRUD, withholding UI helper
├── assets/
├── services/
├── distribution/          # Generate / regenerate / delete / bulk actions, modals
├── tabs/                  # Legacy/alternate tab renderers + heavy features
│   ├── contracts.py, lessors.py, assets.py, services.py # fallback routes
│   ├── weekly_payments.py   # payment table + edit payment flow
│   ├── download_data.py     # CSV/Excel export implementations
│   ├── email_notifications.py
│   └── ...
├── weekly_payments_ui/    # Payment Center hub
├── download_center/       # Reports Center hub
├── email_center/          # Notifications Center hub
├── user_accounts/         # Users create/edit/management
├── roles_admin/           # Roles, permissions matrix, assign roles
├── audit_logs/            # Action log report
├── mgmt_ui/               # Shared hub/delete dialog CSS helpers
└── docs/                  # DEPLOYMENT.md, CONTRACT_TOOL_CONFLUENCE.md, this file
```

---

## 3. How navigation works

The sidebar sets **`st.session_state.selected_main`** (section label — must match the string literals in `app.py`, including any emoji prefix) and **`st.session_state.selected_sub`** (page name, e.g. `Contract Management`, `Create Contract`).

**Routing** is a long `if / elif` chain at the bottom of **`app.py`** (search for `selected_main ==`). Examples:

- Contracts section + sub `Contract Management` → `contracts.render_contract_management`
- Distribution section + sub `Contracts Distribution` → `distribution.render_distribution_management`
- Payments section + sub `Payment Center` → `weekly_payments_ui.render_payment_management`

**Adding a new sidebar page**

1. Add the button / label in the sidebar construction block in `app.py` (and permission check if needed).
2. Add a matching `elif selected_main == ...` branch that imports and calls your `render_*` function.
3. If the page needs RBAC, add a permission in `core/permissions.py` and wire checks with `has_permission` / `require_permission`.

**Programmatic navigation** (e.g. after save): set `st.session_state.selected_main` / `selected_sub` then `st.rerun()`. Some flows use extra keys (e.g. `lessors_editing_id`, contract edit target) — grep `session_state` in the feature you are extending.

---

## 4. Feature → files map

### Contracts

| What | Where |
|------|--------|
| List / filters / open edit | `contracts/management.py` |
| Create form | `contracts/create.py` |
| Edit form | `contracts/edit.py` |
| Delete | `contracts/delete_page.py` |
| Package exports | `contracts/__init__.py` |

### Lessors, assets, services

Same pattern: `management.py`, `create.py`, `edit.py`, `delete_page.py`, `__init__.py` under `lessors/`, `assets/`, `services/`.

**Withholding tax exempt periods (UI only):** `lessors/withholding_periods_ui.py` — used by `lessors/create.py` and `lessors/edit.py`.

### Distribution (rent schedules)

| What | Where |
|------|--------|
| Hub (table, filters, row actions) | `distribution/management.py` |
| Generate / regenerate pages | `distribution/generate_page.py`, `distribution/regenerate_page.py` |
| Delete distribution | `distribution/delete_page.py`, `distribution/delete_dialog.py` |
| Edit distribution grid | `distribution/edit_page.py` |
| Bulk action modal | `distribution/bulk_action_dialog.py` |
| Row modal / workflow glue | `distribution/dist_work_modal.py`, `distribution/run_workflow.py` |
| Small shared helpers | `distribution/helpers.py` |

Core math for schedules lives in **`core/utils.py`** (`generate_contract_distribution`, ROU functions, etc.), not in `distribution/` UI files.

### Payments

| What | Where |
|------|--------|
| Payment Center hub | `weekly_payments_ui/management.py` |
| Table, filters, export, edit navigation | `tabs/weekly_payments.py` (`render_edit_payment` for edit screen) |

Payment rows are created in **`core/utils.py`** (`create_payment_records_from_distribution`).

### Downloads / exports

| What | Where |
|------|--------|
| Reports Center hub | `download_center/management.py` |
| Each download implementation | `tabs/download_data.py` (e.g. `render_download_payments`) |

### Bulk import

| What | Where |
|------|--------|
| UI entry | `bulk_import_ui/management.py` → `bulk_import_ui.bulk_import.render_bulk_import_tab` |
| Templates, validation, import processors | `bulk_import_ui/bulk_import.py` |

### Email notifications

| What | Where |
|------|--------|
| Notifications hub | `email_center/management.py` (if used) + routes in `app.py` under the Email Notifications section |
| SMTP, schedules, forms | `tabs/email_notifications.py` — env overrides: `EMAIL_*` (see `.env.example`). Weekly CSV emails + **payment reminders** (upcoming `payment_date` window); reminder body = short HTML summary from attachment rows only; runner: `core/email_schedule_runner.py` |

### Users & roles

| What | Where |
|------|--------|
| Users | `user_accounts/*.py`, routed from `app.py` under **Administration → Users** |
| Roles | `roles_admin/*.py`, routed under **Administration → Roles** |
| Permission definitions | `core/permissions.py` → `PERMISSIONS` |

### Audit logs

| What | Where |
|------|--------|
| Log report | `audit_logs/management.py` — **Administration → Action Logs → Log Report** |

### Dashboard

| What | Where |
|------|--------|
| Home | `dashboard/__init__.py` (imported as `from dashboard import render_dashboard`) |

---

## 5. Data layer conventions

- **Table/column names** — Prefer `conf/constants.py` constants (`CONTRACTS_COLS`, `CONTRACT_DISTRIBUTION_FIXED_COLS`, etc.) so inserts and DataFrames stay aligned.
- **Allowed tables** — Inserts/loads go through helpers that use `ALLOWED_TABLES` in `conf/database.py`. Adding a table requires updating the whitelist and usually `initialize_database()` in `core/db.py`.
- **Session DataFrames** — `load_all()` in `core/utils.py` populates `st.session_state.*_df` for many entities. Grep `load_all` and `session_state` when adding a new entity.
- **Distribution tables** — One physical table per contract type: Fixed / Revenue Share / ROU (`get_distribution_table` in `core/utils.py`).

---

## 6. Common tasks — where to edit

| Task | Likely files |
|------|----------------|
| Change rent / ROU / revenue-share **calculation** | `core/utils.py` |
| New **contract field** (DB + form) | `core/db.py` (schema/init), `contracts/create.py` & `edit.py`, possibly `bulk_import_ui/bulk_import.py`, `conf/constants.py` `CONTRACTS_COLS` |
| New **permission** | `core/permissions.py`, seed in DB if needed, sidebar + route in `app.py` |
| New **sidebar section** | `app.py` (sidebar + `elif` router) |
| **Export** column / CSV | `tabs/download_data.py` |
| **Bulk import** column | `bulk_import_ui/bulk_import.py` (template + validation + `process_*`) |
| **Login / session** | `core/auth.py` |
| **Branding / layout** | `static/style.css`, `app.py` header/sidebar markdown, `mgmt_ui/button_styles.py` |
| **Deploy / env** | `docs/DEPLOYMENT.md`, `Dockerfile`, `docker-compose.yml` |
| **Business formulas doc** (Confluence) | `docs/CONTRACT_TOOL_CONFLUENCE.md` |

---

## 7. Patterns and pitfalls

- **Streamlit reruns** — The whole script reruns on each interaction; use `st.session_state` for multi-step wizards and selected IDs.
- **Keys** — Widget `key=` must be unique across the app; dialogs sometimes need prefixed keys (see `distribution/bulk_action_dialog.py`).
- **Imports** — Feature packages expose `render_*` from `__init__.py` where present; `app.py` often imports directly from submodules (e.g. `contracts.management`).
- **ROU** — Entry point is `generate_contract_distribution` → `generate_rou_distribution_legacy_template` in `core/utils.py` (large, Excel-aligned schedule).

---

## 8. Related documentation

| Document | Purpose |
|----------|---------|
| `docs/DEPLOYMENT.md` | Requirements, Docker, cloud, env vars |
| `docs/CONTRACT_TOOL_CONFLUENCE.md` | Contract types, columns, calculation rules (business reference) |

---

## 9. Quick grep recipes

```bash
# Find where a permission is checked
rg "contracts.edit" --glob "*.py"

# Find session_state keys for a flow
rg "session_state.*contract" --glob "*.py"

# Find DB table usage
rg "contract_distribution_fixed" --glob "*.py"
```

---

*Update this file when you add major modules or change routing so the next developer stays oriented.*

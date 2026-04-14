# Contract Management Tool — Data Engineer & Integration Guide

**Last Updated:** April 2026

---

## Table of Contents
1. [Overview](#overview)
2. [Database Connection](#database-connection)
3. [Table Reference](#table-reference)
4. [Key Relationships & ER Summary](#key-relationships--er-summary)
5. [Distribution Tables Detail](#distribution-tables-detail)
6. [Payments Table](#payments-table)
7. [Withholding Tax Logic](#withholding-tax-logic)
8. [Data Export Formats](#data-export-formats)
9. [Bulk Import Format](#bulk-import-format)
10. [Useful Queries](#useful-queries)
11. [Data Dictionary](#data-dictionary)

---

## Overview

The system uses **MySQL 8.x** as its sole data store. There are no REST APIs — data is accessed directly via MySQL. Exports are produced as Excel (XLSX) or CSV files through the application UI.

- **Schema (new installs)**: `database/schema.sql`
- **Existing DBs**: `database/migrations/README.md` — numbered `.sql` scripts are **not** shipped in this repo; use **`initialize_database()`** → **`ensure_v2_distribution_payment_schema()`** (additive), align with **`database/schema.sql`**, or recover historical scripts from git.
- **Config/constants**: `conf/constants.py` (table names, column lists); MySQL env in `conf/database.py`

---

## Database Connection

```
Host:     localhost (or configured server)
Database: contract_db
Charset:  utf8mb4 / utf8mb4_unicode_ci
```

Credentials are built in `conf/database.py` → `DB_CONFIG`. For integration, use a read-only MySQL user for safety.

---

## Table Reference

| Table | Purpose |
|---|---|
| `lessors` | Landlord / vendor master |
| `lessor_withholding_periods` | Per-lessor withholding tax exemption windows |
| `assets` | Non-store asset master |
| `stores` | Store master |
| `contracts` | Contract header |
| `contract_lessors` | Contract ↔ Lessor share assignments |
| `contract_distribution_fixed` | Monthly distribution — Fixed (one row/contract/month; detail in `lessors_json`) |
| `contract_distribution_revenue_share` | Monthly distribution — Revenue Share (`lessors_json`) |
| `contract_distribution_rou` | Monthly distribution — ROU (`lessors_json`) |
| `payments` | Payment records (one row per lessor / service split per payment date; `distribution_id` → monthly row) |
| `services` | Service master |
| `contract_services` | Contract ↔ Service assignments |
| `contract_service_lessors` | Per-service lessor share assignments |
| `service_distribution` | Monthly service charge distribution (`services_json`, rolled-up `amount`) |
| `store_monthly_sales` | Monthly sales revenue per store (used for Revenue Share) |
| `users` | User accounts |
| `roles`, `permissions`, `role_permissions`, `user_roles` | RBAC |
| `action_logs` | Audit trail |
| `email_schedules` | Email automation schedules |

---

## Key Relationships & ER Summary

```
lessors ──< contract_lessors >── contracts
lessors ──< lessor_withholding_periods
contracts ──< contract_lessors
contracts ──< contract_distribution_fixed
contracts ──< contract_distribution_revenue_share
contracts ──< contract_distribution_rou
contracts ──< payments
contracts ──< contract_services >── services
contracts ──< contract_service_lessors >── lessors >── services
contracts ──< service_distribution
stores ──< store_monthly_sales
stores ──< contracts  (via asset_or_store_id where asset_category='Store')
```

There are **no foreign keys** between distribution tables and `payments`. **`distribution_id`** on `payments` stores the **monthly** distribution row’s `id` (as string). Logical matching for legacy rows may still use `contract_id` + `rent_date` + `lessor_id` where `lessor_id` is populated.

---

## Distribution Tables Detail

Three tables hold **monthly** distribution data (one row per contract per month, `rent_date` = first of month), one table per contract type. Per-lessor breakdown is in **`lessors_json`**; top-level `lessor_id` / `lessor_share_pct` / `lessor_due_amount` may reflect rolled-up or first-line values depending on generation version.

### `contract_distribution_fixed`

| Column | Type | Notes |
|---|---|---|
| id | INT PK | |
| contract_id | VARCHAR(50) | FK → contracts.id |
| rent_date | DATE | First day of each month |
| lessor_id | VARCHAR(50) NULL | May be NULL when only `lessors_json` is used |
| asset_or_store_id | VARCHAR(50) | |
| rent_amount | VARCHAR(50) | Monthly rent for the month (contract level) |
| lessor_share_pct | VARCHAR(50) | Often rolled-up or representative share |
| lessor_due_amount | VARCHAR(50) | Often rolled-up total due for the month |
| yearly_increase_amount | VARCHAR(50) | Currency step per contract year (from contract % / fixed rules) |
| discount_amount | VARCHAR(50) | Free-month / waiver amount (positive); rolled contract-month total |
| advanced_amount | VARCHAR(50) | Manual advance (Payment Center) |
| lessors_json | TEXT | JSON array: per-lessor amounts/shares for the month |

> **Note:** `contract_name`, `contract_type`, `lessor_name`, `asset_or_store_name` returned by the application are joined at query time, not stored in this table.

### `contract_distribution_revenue_share`

Same monthly grain as fixed, plus revenue columns: `revenue_min`, `revenue_max`, `revenue_amount`, and `discount_amount` / `advanced_amount`. Revenue share **%** values are on **`contracts`** (`rev_share_pct`, `rev_share_after_max_pc`); the app aliases them as `revenue_share_pct` / `revenue_share_after_max_pct` when loading distribution via **`JOIN`**.

### `contract_distribution_rou`

Same base columns as fixed plus:
- `opening_liability`, `interest`, `closing_liability`, `principal` — IFRS 16 lease liability schedule
- `rou_depreciation`, `period`, `lease_accrual`
- `pv_of_lease_payment`
- `discount_amount`, `advanced_amount` — editable via Payment Center
- `advance_coverage_flag`
- `lessors_json` — per-lessor lines for the month

### `service_distribution`

| Column | Type | Notes |
|---|---|---|
| contract_id, store_id, rent_date | | One row per contract per month (typical) |
| service_id | VARCHAR(50) NULL | NULL possible on rolled-up rows |
| amount | VARCHAR(50) | Rolled-up total when `services_json` holds detail |
| services_json | TEXT | JSON: per-service lines for the month |

---

## Payments Table

```sql
SELECT * FROM payments LIMIT 5;
```

| Column | Type | Notes |
|---|---|---|
| id | INT PK | |
| contract_id | VARCHAR(50) | |
| lessor_id | VARCHAR(50) | |
| distribution_id | VARCHAR(50) | Monthly distribution row id (contract dist or service dist, as string) |
| payment_date | DATE | Calculated from first_payment_date + frequency offset |
| due_amount | VARCHAR(50) | Lessor line due (from distribution / JSON expansion) |
| payment_amount | VARCHAR(50) | = due_amount + tax_amount − withholding_amount |
| currency | VARCHAR(10) | |
| payment_type | VARCHAR(50) | `Contract Payment` or `Service Payment` |
| service_id | VARCHAR(50) | NULL for contract payments |
| tax_pct | VARCHAR(50) | |
| tax_amount | VARCHAR(50) | |
| withholding_amount | VARCHAR(50) | 3% of due_amount unless exempted |
| lessor_share_pct | VARCHAR(50) NULL | Lessor share % for the payment line |
| created_at | TIMESTAMP | |

> Tax and withholding are stored **only** in `payments`, not in the distribution tables.

---

## Withholding Tax Logic

```sql
-- Find exemption periods for a lessor
SELECT * FROM lessor_withholding_periods
WHERE lessor_id = '<id>'
  AND start_date <= '<payment_date>'
  AND end_date   >= '<payment_date>';

-- If any row is returned → withholding = 0
-- Otherwise            → withholding = lessor_due_amount × 0.03
```

---

## Data Export Formats

### Via Application UI (📤 Download Data)
| Export Type | Format | Key Columns |
|---|---|---|
| Contracts | Excel | All `contracts` columns + lessor list |
| Distribution | Excel | All distribution columns for selected type |
| Payments | Excel / CSV | All `payments` columns with joined names |
| Services | Excel | `services` + `contract_services` |
| Revenue Share | Excel | `store_monthly_sales` |

### Direct DB Query (for ETL)

```sql
-- All contract payments with names
SELECT
    p.id,
    c.contract_name,
    c.contract_type,
    l.name  AS lessor_name,
    l.iban  AS lessor_iban,
    p.payment_date,
    p.due_amount,
    p.tax_amount,
    p.withholding_amount,
    p.payment_amount,
    p.currency,
    p.payment_type
FROM payments p
JOIN contracts c ON c.id = p.contract_id
JOIN lessors   l ON l.id = p.lessor_id
WHERE p.payment_type = 'Contract Payment'
ORDER BY p.payment_date;
```

```sql
-- Fixed distribution monthly rows (legacy rows may join lessor; new rows use lessors_json)
SELECT
    cdf.rent_date,
    c.contract_name,
    l.name AS lessor_name,
    cdf.rent_amount,
    cdf.lessor_share_pct,
    cdf.discount_amount,
    cdf.advanced_amount,
    cdf.lessor_due_amount,
    cdf.lessors_json
FROM contract_distribution_fixed cdf
JOIN contracts c ON c.id = cdf.contract_id
LEFT JOIN lessors l ON l.id = cdf.lessor_id
ORDER BY c.contract_name, cdf.rent_date;
```

---

## Bulk Import Format

The bulk import template (downloaded from 📥 Bulk Import) is an Excel file with the following sheets:

| Sheet | Purpose |
|---|---|
| Contracts | One row per contract header — includes **Advance Payment (Fixed only)**, **Revenue Share Payment Advance**, yearly increase columns mapped to Create Contract’s **All periods** mode (`increase_by_period_*` on insert), **Free Months**, **Advance Months (ROU)** |
| Lessors | Lessor assignments (contract_name, lessor_name, share_pct) |
| Services | Service assignments (contract_name, service_name, amount, currency, yearly_increase_pct) |
| Service Lessors | Optional per-service lessor shares |

Download the latest template from the app so headers match `bulk_import_ui/bulk_import.py`.

---

## Useful Queries

### Contracts with no distribution
```sql
SELECT c.id, c.contract_name, c.contract_type
FROM contracts c
WHERE NOT EXISTS (
    SELECT 1 FROM contract_distribution_fixed    WHERE contract_id = c.id
    UNION ALL
    SELECT 1 FROM contract_distribution_revenue_share WHERE contract_id = c.id
    UNION ALL
    SELECT 1 FROM contract_distribution_rou      WHERE contract_id = c.id
);
```

### Payments due in the next 30 days
```sql
SELECT
    c.contract_name,
    l.name  AS lessor_name,
    l.iban  AS lessor_iban,
    p.payment_date,
    p.due_amount,
    p.withholding_amount,
    p.payment_amount,
    p.currency
FROM payments p
JOIN contracts c ON c.id = p.contract_id
JOIN lessors   l ON l.id = p.lessor_id
WHERE p.payment_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
ORDER BY p.payment_date;
```

### Lessor totals by contract (Fixed)
Works when `lessor_id` is populated on distribution rows (legacy). For monthly + `lessors_json` rows, aggregate from **`payments`** (`payment_type = 'Contract Payment'`) or parse `lessors_json` with `JSON_TABLE` (MySQL 8+).
```sql
SELECT
    c.contract_name,
    l.name  AS lessor_name,
    SUM(CAST(cdf.lessor_due_amount AS DECIMAL(15,2))) AS total_due
FROM contract_distribution_fixed cdf
JOIN contracts c ON c.id = cdf.contract_id
JOIN lessors   l ON l.id = cdf.lessor_id
WHERE cdf.lessor_id IS NOT NULL AND cdf.lessor_id != ''
GROUP BY c.contract_name, l.name
ORDER BY c.contract_name;
```

### Audit trail for a contract
```sql
SELECT user_name, action_type, action_details, created_at
FROM action_logs
WHERE entity_type = 'contract'
  AND entity_id = '<contract_id>'
ORDER BY created_at DESC;
```

---

## Data Dictionary

### Amounts
All monetary columns use `VARCHAR(50)` in MySQL (not DECIMAL). Cast when aggregating:
```sql
CAST(column AS DECIMAL(15,2))
```

### Dates
- All date columns are `DATE` type in MySQL.
- `rent_date` = first day of the billing month (e.g. `2024-01-01`).
- `payment_date` = actual payment date (calculated from `first_payment_date` + frequency offset, set to 1st of month).

### Contract Type Values
Exact string values used throughout the system:
- `"Fixed"`
- `"Revenue Share"`
- `"ROU"`

### Payment Type Values
- `"Contract Payment"` — from distribution tables
- `"Service Payment"` — from service_distribution table

### free_months / advance_months
Stored as comma-separated period numbers (1-indexed), e.g. `"1,2,3"` means periods 1, 2, 3 are free/advance months.

# Contract Tool — Technical & Business Reference (Confluence-ready)

This document describes **contract types**, **calculations**, **data columns**, and **conditions** implemented in the Contract Tool application. It is intended to be **copied into Confluence** (Markdown-compatible pages) or exported to PDF.

**Scope:** Behaviour reflects the current application logic (primarily `core/utils.py`, `conf/constants.py`, `core/db.py`). If code changes, validate formulas against the repository.

---

## 1. Overview

| Item | Description |
|------|-------------|
| **Supported contract types** | **Fixed**, **Revenue Share**, **ROU** (right-of-use / IFRS-style lease schedule) |
| **Distribution storage** | Separate tables per type (`contract_distribution_fixed`, `contract_distribution_revenue_share`, `contract_distribution_rou`). **One row per contract per month** (`rent_date`); per-lessor detail in **`lessors_json`**. **`service_distribution`**: one row per contract per month with **`services_json`** and rolled-up **`amount`**. |
| **Tax (VAT-style)** | Stored on the **contract** as `tax` (%). Applied when building **payment** rows (`payments.tax_pct`, `payments.tax_amount`), not in distribution tables. |
| **Withholding** | **Not** on the contract. Default **3%** on the payment base unless the **lessor** has a **withholding tax exempt period** that covers the **payment date** (inclusive). |
| **Payment date** | Derived from **first payment date**, **payment frequency**, and calendar position of the distribution month (first of month convention). |
| **Rent date (`rent_date`)** | First day of the calendar month for that schedule row (`YYYY-MM-DD`). Used to align months, sales data, and period indexing. |
| **Lessor shares** | Each lessor has a **share %** on the contract; shares must total **100%**. Amounts are allocated **pro rata** unless otherwise stated. |

---

## 2. Shared concepts

### 2.1 Payment frequency

`payment_frequency` drives how often a “period” advances for **payment_date** calculation:

| Value | Meaning for `payment_date` step |
|--------|----------------------------------|
| **Monthly** | Each contract month advances by 1 month from `first_payment_date`. |
| **2 Months** | Every 2 contract periods → +2 months per step. |
| **Quarter** | Every 3 contract periods → +3 months per step. |
| **Yearly** | Every 12 contract periods → +12 months per step. |

`payment_date` is normalized to the **1st of the month** in code.

### 2.2 Yearly increase (Fixed & ROU rent; Revenue Share minimum only)

Contract fields:

| Field | Role |
|--------|------|
| `yearly_increase_type` | **Increased %** (compound by year) or **Fixed Amount Increased** (add fixed amount × full years elapsed). |
| `yearly_increase` | Percentage (when type is percentage-based and overrides are not used). |
| `yearly_increase_fixed_amount` | Fixed amount added per year (when type is fixed amount). |
| `increase_by_period_mode` | Optional: **all**, **specific**, **year_rules** (and **legacy** in ROU template paths) — see §7. |
| `increase_by_period_all_pct` | Used when mode is **all**. |
| `increase_by_period_map` | JSON map: per-period % multipliers, optional **year_rules**, **all_value_type** (`percent` or `amount`). |

**Rules:**

- **Fixed** and **ROU:** yearly increase applies to **`rent_amount`** (monthly rent base).
- **Revenue Share:** yearly increase applies **only** to **`rev_min`** (minimum guarantee), **not** to the revenue-derived rent.

### 2.3 Free months (Fixed & Revenue Share)

- `free_months`: comma-separated **1-based period indices** (e.g. `1,2,3`).
- In those periods, the tool applies a **full discount** equal to the calculated rent for that month so **cash rent after discount is zero** (per lessor after share split for Fixed).

### 2.4 Advance payment (Fixed only)

- `advance_payment`: bulk amount consumed **month by month** against **non–free-month** rent until exhausted.
- Applied **after** rent is known; reduces **lessor due** pro rata by share.

### 2.5 ROU-only: advance months & coverage

- **`advance_months`**: comma-separated period indices (schedule position).
- **`advance_months_count`**: count of advance months (if not set, derived from length of `advance_months`).
- **Coverage periods**: algorithm may mark periods with `advance_coverage_flag = 1` where advance “covers” a month without a full cash coupon (see ROU engine).
- **Free months** on ROU: accrual behaviour follows the dedicated ROU schedule (interest still accrues on liability in free/coverage-style rows per engine rules).

### 2.6 Store sales (Revenue Share)

- Table **`store_monthly_sales`**: `store_id`, `rent_date`, `net_sales`, `total_sales`.
- Contract field **`sales_type`**: **Net** → use `net_sales`; otherwise **Total** → use `total_sales`.
- Match key: **store_id** + **rent_date** (same month as distribution row).

---

## 3. Contract master data (`contracts` table / `CONTRACTS_COLS`)

| Column | Meaning / use |
|--------|----------------|
| `id` | Primary key. |
| `contract_name` | Display name. |
| `contract_type` | **Fixed**, **Revenue Share**, or **ROU**. |
| `currency` | E.g. EGP, USD. |
| `asset_category` | **Asset** or **Store** (links to asset or store master). |
| `asset_or_store_id` | FK to asset or store. |
| `asset_or_store_name` | Denormalized name. |
| `commencement_date` | Lease / contract start. |
| `tenure_months` | Term length in months (ROU schedule length). |
| `end_date` | Contract end (inclusive logic in monthly loop). |
| `lessors_json` | JSON list of `{id, name, share}` — shares must sum to 100. |
| `discount_rate` | **ROU:** annual discount rate (%) for IFRS-16 style interest (see §5). |
| `tax` | Tax **percentage** applied on payment base when creating payments. |
| `is_tax_added` | **ROU:** when truthy, base monthly rent is multiplied by **1.01** before increases (1% uplift in code). |
| `payment_frequency` | Monthly / 2 Months / Quarter / Yearly. |
| `yearly_increase` | % increase (default path). |
| `yearly_increase_type` | Increased % vs Fixed Amount Increased. |
| `yearly_increase_fixed_amount` | Fixed amount per year for Fixed Amount path. |
| `rent_amount` | **Fixed / ROU:** monthly rent base. **Revenue Share:** not used as primary rent (rent from sales). |
| `rev_min` | Revenue share: **minimum** rent (with yearly increase on this field only). |
| `rev_max` | Revenue share: **cap** on the primary % share band. |
| `rev_share_pct` | % of actual revenue for the main band. |
| `rev_share_after_max_pc` | % applied to **remaining sales** above the sales level that corresponds to `rev_max`. |
| `sales_type` | **Net** or **Total** (which sales column to read). |
| `rent_per_year` | Present in schema; **enhanced** ROU path exists in code but **standard generation** for ROU uses the **legacy ROU template** from `generate_contract_distribution` (see §5 note). |
| `first_payment_date` | Anchor for payment schedule (defaults to commencement if empty). |
| `free_months` | Comma-separated period numbers (Fixed, Revenue Share, ROU as applicable). |
| `advance_months` | ROU: periods with advance behaviour. |
| `advance_months_count` | ROU: number of advance months. |
| `increase_by_period_mode` | Override mode for increases (`all`, `specific`, `year_rules`, `legacy`). |
| `increase_by_period_all_pct` | Global per-period driver when mode = all. |
| `increase_by_period_map` | JSON configuration for specific periods / year rules. |
| `advance_payment` | **Fixed:** prepaid rent pool. |
| `created_at` | Audit timestamp. |

---

## 4. Fixed contracts

### 4.1 Rent for the month

1. Start from `rent_amount` (after optional ROU-style tax flag — **not** used for Fixed; only ROU applies `is_tax_added` in the shared loop; Fixed uses raw `rent_amount`).
2. Apply **yearly increase** to get **monthly rent** for that calendar month:
   - **Fixed Amount Increased:**  
     `rent = rent_amount + yearly_increase_fixed_amount * floor(years_passed)`
   - **Increased %** with optional period overrides: use `apply_period_override` or compound:  
     `rent = rent_amount * (1 + yearly_increase/100) ** floor(years_passed)`
3. **Free month:** discount = full rent → net cash rent **0** for that period (before advance).

### 4.2 Advance payment consumption

- Only in **non–free** months, while `advance_payment_remaining > 0`.
- `advanced_amount_per_month = min(remaining, monthly_rent)` then reduce remaining.

### 4.3 Per lessor (distribution)

Let `R = original_rent_amount` (monthly rent before discount), `s = lessor_share_pct / 100`.

| Derived field | Formula / rule |
|---------------|----------------|
| `lessor_discount_amount` | `(discount_amount_per_month * s)` — discount_amount_per_month = R in free months, else 0. |
| `lessor_advanced_amount` | `(advanced_amount_per_month * s)` |
| `lessor_original_rent` | `R * s` |
| **`lessor_due_amount`** | `lessor_original_rent - lessor_discount_amount - lessor_advanced_amount` |

**Withholding (in distribution generation path):** computed for diagnostics; **authoritative withholding** is on **`payments`** (see §8).

**Tax in distribution loop:** legacy calculations exist in code for Fixed; **persisted tax** for reporting is on **payments**.

### 4.4 Fixed distribution columns (`CONTRACT_DISTRIBUTION_FIXED_COLS`)

Persisted shape: **one DB row per month per contract**; per-lessor values are in **`lessors_json`**. Top-level `lessor_id` / names may be empty on new saves; UI and exports join from JSON or legacy columns.

| Column | Meaning |
|--------|---------|
| `contract_id`, `contract_name`, `contract_type` | Identity. |
| `rent_date` | First day of month. |
| `lessor_id`, `lessor_name` | Legacy / optional; prefer **`lessors_json`** for lessor lines. |
| `asset_or_store_id`, `asset_or_store_name` | Location. |
| `rent_amount` | Monthly rent for the month (before lessor split / discount / advance at contract level). |
| `lessor_share_pct` | Rolled or first-line share % when present. |
| `lessor_due_amount` | Rolled or aggregate due when present; line detail in **`lessors_json`**. |
| `yearly_increase_amount` | Currency added per contract year on the monthly base (from % or fixed-amount rules). |
| `discount_amount` | Discount / free-month waiver for the month (stored as a positive amount at contract-month level). |
| `advanced_amount` | Advance applied for the month. |
| `lessors_json` | JSON array of per-lessor lines (share, due, discount, advance, etc.). |

---

## 5. Revenue Share contracts

### 5.1 Minimum with increase

`rev_min_with_increase` = `rev_min` adjusted by the same yearly rules as §2.2 (applied **only** to `rev_min`).

### 5.2 Rent from actual revenue

Let `A` = actual revenue for the month (from sales file), `r = rev_share_pct/100`, `m = rev_min_with_increase`, `cap = rev_max`, `r2 = rev_share_after_max_pct/100`.

| Condition | Rent for the month |
|-----------|-------------------|
| No sales / zero revenue | `rent = m` (or 0 if m is 0). |
| `A * r < m` | `rent = m` (minimum guarantee). |
| `A * r ≤ cap` | `rent = A * r` |
| `A * r > cap` | Tiered: sales at cap threshold `sales_at_max = cap / r` (if r>0); `remaining = A - sales_at_max`; `rent = cap + remaining * r2` |

### 5.3 Free month

Same as Fixed: **discount** wipes that month’s **pre-discount** rent allocation (applied via negative discount and lessor due adjustment).

### 5.4 Per lessor (distribution)

Let `s = lessor_share_pct/100`.

| Field | Formula |
|--------|---------|
| `lessor_due_amount_base` | `rent * s` |
| `lessor_discount` | `discount * s` (discount is negative full rent in free month) |
| **`lessor_due_amount`** | `lessor_due_amount_base + lessor_discount` |

Tax / withholding in payment file: see §8.

### 5.5 Revenue Share distribution columns

All **Fixed** columns **plus** (V2: one row per contract-month; no `lessors_json` on the fact table):

| Column | Meaning |
|--------|---------|
| `revenue_min` | Minimum for that month (after yearly increase). |
| `revenue_max` | Cap on primary % band. |
| `revenue_amount` | Actual sales used (string from DB/store row). |

**Percentages** (`revenue_share_pct`, `revenue_share_after_max_pct` in the UI) are read from **`contracts`** (`rev_share_pct`, `rev_share_after_max_pc`) via **`JOIN`** when loading distribution — they are not stored on **`contract_distribution_revenue_share`**.

---

## 6. ROU contracts (legacy schedule engine)

**Entry point:** `generate_contract_distribution` calls **`generate_rou_distribution_legacy_template`** for type **ROU** (Excel-aligned schedule).

### 6.1 Key inputs

- `rent_amount`: base monthly rent (with yearly increase logic inside ROU template).
- `discount_rate`: treated as **annual**; **simple monthly rate** = annual/12 in template (see code for exact convention when rate entered as decimal vs percent).
- `tenure_months`, `commencement_date`, `end_date`.
- `free_months`, `advance_months`, `advance_months_count`.
- Contract services may **add** to rent for periods where lessors participate in services.

### 6.2 Schedule concepts

- **Period index** `p = 0 … tenure_months` (inclusive endpoints per implementation).
- **Lease accrual** per period from `lease_accrual_for(p)` (handles advance at p=0, free, coverage, stub at end).
- **Present value** of each accrual: `pv_for_period(p, accrual)` discounting by monthly rate.
- **Opening lease liability** (initial): NPV of future cashflows + period 0 (Excel NPV convention in code).

### 6.3 Interest, principal, closing

For each period:

- `opening_liability` = liability at start of period.
- `interest` = f(opening, payment type, monthly rate) — **zero** in final period; special case for period 0 advance.
- `principal` = `lease_payment - interest` (lease_payment = accrual for the row).
- `closing_liability` = `opening + interest - lease_payment` (clamped, forced to 0 at end).

### 6.4 Depreciation

- Straight-line: `rou_depreciation = initial_PV / tenure_months` (approximation in template; see code for `initial_rou_asset` / opening liability alignment).

### 6.5 Per lessor row

- `rent_amount` **R**: display / cash rent helper for that row.
- `lessor_due_amount`: `lease_accrual * lessor_share_pct / 100` when accrual ≠ 0.
- `discount_amount` / `advanced_amount`: lessor share of **free** and **advance-month** adjustments.

### 6.6 ROU distribution columns

| Column | Meaning |
|--------|---------|
| Core identity | Same as Fixed (`contract_id`, `rent_date`, asset, etc.); **`lessors_json`** for lessor lines. |
| `opening_liability` | Lease liability at period start. |
| `interest` | Accretion expense for the period. |
| `closing_liability` | Liability at period end. |
| `principal` | Principal portion of accrual. |
| `rou_depreciation` | Right-of-use asset depreciation. |
| `period` | Schedule period index. |
| `lease_accrual` | Accounting accrual for the period. |
| `pv_of_lease_payment` | PV of that period’s accrual. |
| `discount_amount`, `advanced_amount` | Lessor share of discounts/advances. |
| `advance_coverage_flag` | `1` if period is “coverage” type, else `0`. |

### 6.7 Note on “enhanced” ROU

`generate_rou_distribution_enhanced` exists for schedules with **`rent_per_year`** and detailed cash-flow NPV, but the **default** `generate_contract_distribution` path for **ROU** returns the **legacy template** first. If your deployment switches to enhanced ROU, reconcile this document with that function.

---

## 7. Period increase overrides (`increase_by_period_map`)

JSON structure (simplified):

- **`all_value_type`**: `percent` or `amount` (for mode **all**).
- **`year_rules`**: list of `{ "years": [1,2], "value": 5, "value_type": "percent" }` — applies increases by contract year.
- Other keys: period numbers as strings → **percentage** step multiplier for mode **specific**.

**Modes:**

- **all:** apply uniform compounding or amount step each period.
- **specific:** multiply by `(1 + map[k]/100)` for all configured periods `k <= current period`.
- **year_rules:** combine factors per calendar year bucket.

(Revenue Share uses the same helper for **rev_min** only.)

---

## 8. Payments (`payments` table)

Created from distribution after save (regenerate / generate flow). **One row per lessor** (or service split) per payment date; source month is the **monthly** distribution row.

| Column | Meaning |
|--------|---------|
| `contract_id` | Contract. |
| `lessor_id` | Payee lessor. |
| `distribution_id` | Id of the **monthly** row in the type-specific **contract** distribution table (or service distribution for service payments), stored as string. |
| `payment_date` | Scheduled payment date (§2.1). |
| `due_amount` | From the lessor line (`lessor_due_amount` in JSON expansion or legacy row). |
| `payment_amount` | **Net cash:** `effective_base + tax_amount - withholding_amount`, where `effective_base = max(due_amount, 0)`. |
| `currency` | From contract. |
| `payment_type` | e.g. **Contract Payment** vs service payment. |
| `service_id` | Set for service payments. |
| `tax_pct`, `tax_amount` | `tax_amount = effective_base * tax_pct/100` if base > 0. |
| `withholding_amount` | `effective_base * withholding_pct/100` if base > 0; **0%** if lessor exempt on `payment_date`. |
| `lessor_share_pct` | Lessor share % stored on the payment line when created. |

**Withholding exemption:** compare **`payment_date`** (date only) to each **lessor** row in **`lessor_withholding_periods`** (`start_date`–`end_date`, inclusive).

**Default withholding:** **3%** if not exempt.

**Service payments:** withholding logic in code is **not** applied the same way as contract rent (services treated separately).

---

## 9. Service distribution (`service_distribution`)

| Column | Meaning |
|--------|---------|
| `contract_id` | Contract. |
| `store_id`, `store_name` | Store context (for revenue-linked services). |
| `rent_date` | Month anchor (one row per contract per month when rolled up). |
| `service_id`, `service_name` | Service master; **`service_id`** may be NULL when only **`services_json`** holds line detail. |
| `amount` | Rolled-up service amount for the month (with contract service yearly increase applied in generation). |
| `services_json` | JSON array of per-service lines for the month. |
| `currency` | Service currency. |

Linked to **contract_services** (amount, yearly_increase_pct) and optional **contract_service_lessors** shares.

---

## 10. Lessor withholding exempt periods

Table **`lessor_withholding_periods`**: `lessor_id`, `start_date`, `end_date` (inclusive).

- If **payment_date** falls in any period for that lessor → **withholding_amount = 0** for that payment.
- Does **not** remove VAT/tax unless contract **tax** is zero; only **withholding** is suppressed.

---

## 11. Conditions checklist (validation & business rules)

| Rule | Applies to |
|------|------------|
| Contract type ∈ {Fixed, Revenue Share, ROU} | All |
| Lessor shares sum to **100%** | All |
| **Fixed / ROU:** `rent_amount` > 0 | Creation / import |
| **ROU:** `discount_rate` > 0 | Typical ROU validation |
| **Revenue Share:** revenue fields and store sales for rent | Runtime |
| Free month indices are **1-based** period numbers | Fixed, Revenue Share, ROU (ROU engine) |
| Exempt periods **must not overlap** (lessor UI / import) | Master data |
| **Revenue Share** tier: `rev_share_pct` = 0 → cap math guarded in code | Edge case |
| Payment frequency drives **payment_date**, not necessarily `rent_date` | All |
| Regenerate **deletes** existing payments for contract then rebuilds | Operations |

---

## 12. Bulk import (contracts) — column hints

Template columns include (among others): **Contract Name**, **Contract Type**, **Currency**, **Asset/Store**, **Commencement**, **Tenure**, **Discount Rate (ROU)**, **Tax**, **Payment Frequency**, **Yearly Increase** (type / % / fixed per period), **Rent Amount**, **Revenue** fields, **Sales Type**, **Advance Payment (Fixed only)**, **Revenue Share Payment Advance**, **Free Months**, **Advance Months (ROU)**, plus **Lessors**, **Services**, and **Service Lessors** sheets — see `bulk_import_ui/bulk_import.py` (import writes `increase_by_period_mode=all` and `advance_payment` / `rev_share_payment_advance` like Create Contract).

---

## 13. Implementation map (for maintainers)

| Topic | Primary code |
|--------|--------------|
| Fixed / Revenue Share monthly loop | `generate_contract_distribution` in `core/utils.py` |
| ROU legacy schedule | `generate_rou_distribution_legacy_template` in `core/utils.py` |
| ROU enhanced (optional) | `generate_rou_distribution_enhanced` in `core/utils.py` |
| Payments | `create_payment_records_from_distribution` in `core/utils.py`; `insert_payment` in `core/db.py` |
| Column constants | `conf/constants.py` |

---

*End of document. Import into Confluence via Markdown macro or paste and convert; adjust heading levels if your space uses a fixed page tree.*

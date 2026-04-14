# Database migrations

Numbered SQL upgrade scripts that used to live in this folder have been **removed** from the repository.

## What to use instead

| Situation | Approach |
|-----------|----------|
| **New database** | Load **`database/schema.sql`** (creates `contract_db` and all tables). |
| **Existing database** | Start the application so **`initialize_database()`** in `core/db.py` can apply **additive** DDL (`ensure_v2_distribution_payment_schema()` via `ensure_monthly_distribution_and_payment_schema()`), and align any remaining gaps with **`database/schema.sql`** using your own DBA process (compare, `mysqldump` structure, manual `ALTER`, regenerate distribution/payments as needed). |

If you need a one-off upgrade script for production, maintain it in your deployment pipeline or recover historical `.sql` files from **git history** for this repo.

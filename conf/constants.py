# conf/constants.py — table/column identifiers and app constants (no secrets).

# Branding: place logo image as static/logo.png (or .jpg / .jpeg / .svg); see core.paths.resolve_static_logo_path.

# Database table keys (used as identifiers, not actual CSV files)
LESSORS_TABLE = "lessors"
ASSETS_TABLE = "assets"
STORES_TABLE = "stores"
CONTRACTS_TABLE = "contracts"
CONTRACT_LESSORS_TABLE = "contract_lessors"
CONTRACT_DISTRIBUTION_TABLE = "contract_distribution"  # Legacy - kept for backward compatibility
CONTRACT_DISTRIBUTION_FIXED_TABLE = "contract_distribution_fixed"
CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE = "contract_distribution_revenue_share"
CONTRACT_DISTRIBUTION_ROU_TABLE = "contract_distribution_rou"
PAYMENTS_TABLE = "payments"
STORE_MONTHLY_SALES_TABLE = "store_monthly_sales"
SERVICES_TABLE = "services"
CONTRACT_SERVICES_TABLE = "contract_services"
CONTRACT_SERVICE_LESSORS_TABLE = "contract_service_lessors"
SERVICE_DISTRIBUTION_TABLE = "service_distribution"
USERS_TABLE = "users"
ROLES_TABLE = "roles"
PERMISSIONS_TABLE = "permissions"
ROLE_PERMISSIONS_TABLE = "role_permissions"
USER_ROLES_TABLE = "user_roles"
ACTION_LOGS_TABLE = "action_logs"
EMAIL_SCHEDULES_TABLE = "email_schedules"


# Columns definitions
LESSORS_COLS = ["id", "name", "description", "tax_id", "supplier_code", "iban"]
ASSETS_COLS = ["id", "name", "cost_center"]
STORES_COLS = ["id", "name", "cost_center"]
CONTRACTS_COLS = [
    "id", "contract_name", "contract_type", "currency",
    "asset_category", "asset_or_store_id", "asset_or_store_name",
    "commencement_date", "tenure_months", "end_date",
    "lessors_json", "discount_rate", "tax", "is_tax_added", "payment_frequency", "yearly_increase",
    "yearly_increase_type", "yearly_increase_fixed_amount",
    "rent_amount", "rev_min", "rev_max", "rev_share_pct", "rev_share_after_max_pc", "sales_type",
    "rent_per_year", "first_payment_date", "free_months", "advance_months", "advance_months_count",
    "increase_by_period_mode", "increase_by_period_all_pct", "increase_by_period_map",
    "advance_payment", "rev_share_payment_advance", "rev_share_advance_mode", "created_at"
]

CONTRACT_LESSORS_COLS = [
    "contract_id", "lessor_id", "share_pct"
]

# Lessor withholding periods (per-lessor exemption periods for withholding tax)
LESSOR_WITHHOLDING_PERIODS_TABLE = "lessor_withholding_periods"
LESSOR_WITHHOLDING_PERIODS_COLS = [
    "id", "lessor_id", "start_date", "end_date"
]

# Fixed: persisted columns + JOIN-derived columns for UI (contract_name, asset_or_store_name, month_year, etc.)
CONTRACT_DISTRIBUTION_FIXED_COLS = [
    "contract_id", "contract_name", "contract_type", "rent_date",
    "asset_or_store_name",
    "rent_amount", "yearly_increase_amount",
    "discount_amount", "advanced_amount", "due_amount",
    "month_year", "year", "month",
]

# Revenue share: contract-level month row + JOINs
CONTRACT_DISTRIBUTION_REVENUE_SHARE_COLS = [
    "contract_id", "contract_name", "contract_type", "rent_date",
    "asset_or_store_name",
    "rent_amount", "yearly_increase_amount",
    "revenue_min", "revenue_max", "revenue_share_pct", "revenue_share_after_max_pct", "revenue_amount",
    "discount_amount", "advanced_amount", "due_amount",
    "month_year", "year", "month",
]

# ROU: contract-level month row + JOINs
CONTRACT_DISTRIBUTION_ROU_COLS = [
    "contract_id", "contract_name", "contract_type", "rent_date",
    "asset_or_store_name",
    "rent_amount", "yearly_increase_amount",
    "opening_liability", "interest",
    "closing_liability", "principal", "rou_depreciation",
    "period", "lease_accrual",
    "pv_of_lease_payment",
    "discount_amount", "advanced_amount",
    "advance_coverage_flag",
    "due_amount",
    "month_year", "year", "month",
]

# Legacy - kept for backward compatibility (will use appropriate table based on contract type)
CONTRACT_DISTRIBUTION_COLS = CONTRACT_DISTRIBUTION_FIXED_COLS

# Columns persisted to MySQL (no JOIN-only fields)
CONTRACT_DISTRIBUTION_FIXED_STORAGE_COLS = [
    "contract_id", "rent_date", "rent_amount", "yearly_increase_amount",
    "discount_amount", "advanced_amount", "due_amount",
]
CONTRACT_DISTRIBUTION_REVENUE_SHARE_STORAGE_COLS = [
    "contract_id", "rent_date", "rent_amount", "yearly_increase_amount",
    "revenue_min", "revenue_max", "revenue_amount",
    "discount_amount", "advanced_amount", "due_amount",
]
CONTRACT_DISTRIBUTION_ROU_STORAGE_COLS = [
    "contract_id", "rent_date", "rent_amount", "yearly_increase_amount",
    "opening_liability", "interest", "closing_liability", "principal", "rou_depreciation",
    "period", "lease_accrual", "pv_of_lease_payment",
    "discount_amount", "advanced_amount", "advance_coverage_flag", "due_amount",
]
SERVICE_DISTRIBUTION_STORAGE_COLS = [
    "contract_id", "service_id", "rent_date", "amount", "discount_amount", "due_amount",
]

STORE_MONTHLY_SALES_COLS = [
    "store_id", "rent_date", "net_sales", "total_sales"
]

SERVICES_COLS = ["id", "name", "description", "currency"]
CONTRACT_SERVICES_COLS = [
    "contract_id", "service_id", "amount", "yearly_increase_pct"
]
CONTRACT_SERVICE_LESSORS_COLS = [
    "contract_id", "service_id", "lessor_id", "share_pct"
]
SERVICE_DISTRIBUTION_COLS = [
    "contract_id", "contract_name", "contract_type", "rent_date",
    "service_id", "service_name",
    "amount", "discount_amount", "due_amount",
    "month_year", "year", "month",
]

# Payments table (for queries that load into DataFrames)
PAYMENTS_COLS = [
    "id", "contract_id", "lessor_id", "rent_month", "payment_date",
    "amount", "due_amount", "payment_amount",
    "service_id",
    "tax_pct", "tax_amount", "withholding_amount",
    "lessor_share_pct",
    "created_at",
]

# Authentication and authorization columns
USERS_COLS = ["id", "email", "password_hash", "name", "is_active", "created_at", "last_login"]
ROLES_COLS = ["id", "role_name", "description", "created_at"]
PERMISSIONS_COLS = ["id", "permission_name", "description", "module", "created_at"]
ROLE_PERMISSIONS_COLS = ["role_id", "permission_id"]
USER_ROLES_COLS = ["user_id", "role_id"]
ACTION_LOGS_COLS = [
    "id", "user_id", "user_name", "action_type", "entity_type", "entity_id",
    "entity_name", "action_details", "ip_address", "created_at"
]

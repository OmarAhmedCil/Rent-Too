# conf/database.py — MySQL connection settings and table whitelist (from env / defaults).
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _build_db_config():
    """Build MySQL config from environment (cloud) with local defaults."""
    cfg = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "omar"),
        "password": os.getenv("MYSQL_PASSWORD", "Password@123"),
        "database": os.getenv("MYSQL_DATABASE", "contract_db"),
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
    }
    ssl_ca = os.getenv("MYSQL_SSL_CA", "").strip()
    if ssl_ca:
        cfg["ssl_ca"] = ssl_ca
    elif os.getenv("MYSQL_SSL_DISABLED", "").lower() in ("1", "true", "yes"):
        cfg["ssl_disabled"] = True
    return cfg


DB_CONFIG = _build_db_config()

ALLOWED_TABLES = {
    "lessors",
    "assets",
    "stores",
    "contracts",
    "contract_lessors",
    "contract_distribution",
    "contract_distribution_fixed",
    "contract_distribution_revenue_share",
    "contract_distribution_rou",
    "payments",
    "store_monthly_sales",
    "services",
    "contract_services",
    "contract_service_lessors",
    "service_distribution",
    "lessor_withholding_periods",
    "users",
    "roles",
    "permissions",
    "role_permissions",
    "user_roles",
    "action_logs",
    "email_schedules",
}


def validate_table_name(table_name):
    """Validate that table name is in whitelist."""
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Table name '{table_name}' is not in allowed list")
    return table_name

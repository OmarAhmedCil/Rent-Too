-- MySQL Schema for Contract Management Tool
-- Database: contract_db
-- Last Updated: April 2026
--
-- Notes:
--   • Distribution tables: contract_id + month only (no lessor_id, lessors_json, or asset denormalization).
--     Labels come from JOINs (contracts, lessors, assets, stores).
--   • Tax and withholding are in `payments`, not in distribution tables.
--   • Three tables: contract_distribution_fixed, contract_distribution_revenue_share, contract_distribution_rou —
--     one row per (contract_id, rent_date).
--   • service_distribution: one row per (contract_id, service_id, rent_date); amount, discount_amount, due_amount.
--   • payments: rent_month (first of rent month), amount (gross line before discount/advance), due_amount (net line);
--     lessor_id NOT NULL; lessor_share_pct optional; no distribution_id, payment_type, or currency.
--   • Upgrade: align with this file and/or app startup `ensure_v2_distribution_payment_schema()` (see `core/db.py`).

-- Create database if not exists
CREATE DATABASE IF NOT EXISTS contract_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE contract_db;

-- Table: lessors
CREATE TABLE IF NOT EXISTS lessors (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    tax_id VARCHAR(100),
    supplier_code VARCHAR(100),
    iban VARCHAR(100),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: lessor_withholding_periods (per-lessor withholding exemption periods)
CREATE TABLE IF NOT EXISTS lessor_withholding_periods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lessor_id VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    INDEX idx_lessor_id (lessor_id),
    INDEX idx_period (start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: assets
CREATE TABLE IF NOT EXISTS assets (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    cost_center VARCHAR(100),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: stores
CREATE TABLE IF NOT EXISTS stores (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    cost_center VARCHAR(100),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: contracts
CREATE TABLE IF NOT EXISTS contracts (
    id VARCHAR(50) PRIMARY KEY,
    contract_name VARCHAR(255) NOT NULL,
    contract_type VARCHAR(50) NOT NULL,
    currency VARCHAR(10),
    asset_category VARCHAR(50),
    asset_or_store_id VARCHAR(50),
    asset_or_store_name VARCHAR(255),
    commencement_date DATE,
    tenure_months VARCHAR(50),
    end_date DATE,
    lessors_json TEXT,
    discount_rate VARCHAR(50),
    tax VARCHAR(50),
    is_tax_added TINYINT(1) DEFAULT 0,
    payment_frequency VARCHAR(50),
    yearly_increase VARCHAR(50),
    yearly_increase_type VARCHAR(50),
    yearly_increase_fixed_amount VARCHAR(50),
    rent_amount VARCHAR(50),
    rev_min VARCHAR(50),
    rev_max VARCHAR(50),
    rev_share_pct VARCHAR(50),
    rev_share_after_max_pc VARCHAR(50),
    sales_type VARCHAR(50),
    rent_per_year TEXT,
    first_payment_date DATE,
    free_months VARCHAR(255),
    advance_months VARCHAR(255),
    advance_months_count VARCHAR(50),
    increase_by_period_mode VARCHAR(30),
    increase_by_period_all_pct VARCHAR(50),
    increase_by_period_map TEXT,
    advance_payment VARCHAR(50),
    rev_share_payment_advance VARCHAR(50),
    rev_share_advance_mode VARCHAR(50),
    created_at DATETIME,
    INDEX idx_contract_name (contract_name),
    INDEX idx_contract_type (contract_type),
    INDEX idx_commencement_date (commencement_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: contract_lessors
CREATE TABLE IF NOT EXISTS contract_lessors (
    contract_id VARCHAR(50) NOT NULL,
    lessor_id VARCHAR(50) NOT NULL,
    share_pct VARCHAR(50) NOT NULL,
    PRIMARY KEY (contract_id, lessor_id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
    FOREIGN KEY (lessor_id) REFERENCES lessors(id) ON DELETE CASCADE,
    INDEX idx_contract_id (contract_id),
    INDEX idx_lessor_id (lessor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: contract_distribution_fixed (one row per contract per month)
CREATE TABLE IF NOT EXISTS contract_distribution_fixed (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contract_id VARCHAR(50) NOT NULL,
    rent_date DATE NOT NULL,
    rent_amount VARCHAR(50),
    yearly_increase_amount VARCHAR(50),
    discount_amount VARCHAR(50),
    advanced_amount VARCHAR(50),
    due_amount VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_cdf_contract_month (contract_id, rent_date),
    INDEX idx_contract_id (contract_id),
    INDEX idx_rent_date (rent_date),
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: contract_distribution_revenue_share (one row per contract per month)
CREATE TABLE IF NOT EXISTS contract_distribution_revenue_share (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contract_id VARCHAR(50) NOT NULL,
    rent_date DATE NOT NULL,
    rent_amount VARCHAR(50),
    yearly_increase_amount VARCHAR(50),
    revenue_min VARCHAR(50),
    revenue_max VARCHAR(50),
    revenue_amount VARCHAR(50),
    discount_amount VARCHAR(50),
    advanced_amount VARCHAR(50),
    due_amount VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_cdrs_contract_month (contract_id, rent_date),
    INDEX idx_contract_id (contract_id),
    INDEX idx_rent_date (rent_date),
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: contract_distribution_rou (one row per contract per month)
CREATE TABLE IF NOT EXISTS contract_distribution_rou (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contract_id VARCHAR(50) NOT NULL,
    rent_date DATE NOT NULL,
    rent_amount VARCHAR(50),
    yearly_increase_amount VARCHAR(50),
    opening_liability VARCHAR(50),
    interest VARCHAR(50),
    closing_liability VARCHAR(50),
    rou_depreciation VARCHAR(50),
    period VARCHAR(50),
    principal VARCHAR(50),
    lease_accrual VARCHAR(50),
    pv_of_lease_payment VARCHAR(50),
    discount_amount VARCHAR(50),
    advanced_amount VARCHAR(50),
    advance_coverage_flag VARCHAR(10),
    due_amount VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_cdrou_contract_month (contract_id, rent_date),
    INDEX idx_contract_id (contract_id),
    INDEX idx_rent_date (rent_date),
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: payments (per lessor payment line)
CREATE TABLE IF NOT EXISTS payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contract_id VARCHAR(50),
    lessor_id VARCHAR(50) NOT NULL,
    rent_month DATE,
    payment_date DATE,
    amount VARCHAR(50),
    due_amount VARCHAR(50),
    payment_amount VARCHAR(50),
    service_id VARCHAR(50) NULL,
    tax_pct VARCHAR(50),
    tax_amount VARCHAR(50),
    withholding_amount VARCHAR(50),
    lessor_share_pct VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_contract_id (contract_id),
    INDEX idx_lessor_id (lessor_id),
    INDEX idx_payment_date (payment_date),
    INDEX idx_rent_month (rent_month),
    INDEX idx_contract_lessor_rent_month (contract_id, lessor_id, rent_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: store_monthly_sales
CREATE TABLE IF NOT EXISTS store_monthly_sales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    store_id VARCHAR(50),
    rent_date DATE,
    net_sales VARCHAR(50),
    total_sales VARCHAR(50),
    INDEX idx_store_id (store_id),
    INDEX idx_rent_date (rent_date),
    INDEX idx_store_rent_date (store_id, rent_date),
    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: services
CREATE TABLE IF NOT EXISTS services (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    currency VARCHAR(10) DEFAULT 'EGP',
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: contract_services
CREATE TABLE IF NOT EXISTS contract_services (
    contract_id VARCHAR(50) NOT NULL,
    service_id VARCHAR(50) NOT NULL,
    amount VARCHAR(50) NOT NULL,
    yearly_increase_pct VARCHAR(50) DEFAULT '0',
    PRIMARY KEY (contract_id, service_id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    INDEX idx_contract_id (contract_id),
    INDEX idx_service_id (service_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: contract_service_lessors
CREATE TABLE IF NOT EXISTS contract_service_lessors (
    contract_id VARCHAR(50) NOT NULL,
    service_id VARCHAR(50) NOT NULL,
    lessor_id VARCHAR(50) NOT NULL,
    share_pct VARCHAR(50) NOT NULL,
    PRIMARY KEY (contract_id, service_id, lessor_id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    FOREIGN KEY (lessor_id) REFERENCES lessors(id) ON DELETE CASCADE,
    INDEX idx_csl_contract (contract_id),
    INDEX idx_csl_service (service_id),
    INDEX idx_csl_lessor (lessor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: service_distribution (one row per contract, service, month)
CREATE TABLE IF NOT EXISTS service_distribution (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contract_id VARCHAR(50) NOT NULL,
    service_id VARCHAR(50) NOT NULL,
    rent_date DATE NOT NULL,
    amount VARCHAR(50),
    discount_amount VARCHAR(50) DEFAULT '0',
    due_amount VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_service_dist_line (contract_id, service_id, rent_date),
    INDEX idx_contract_id (contract_id),
    INDEX idx_service_id (service_id),
    INDEX idx_rent_date (rent_date),
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: users
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(50) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    is_active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME,
    INDEX idx_email (email),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: roles
CREATE TABLE IF NOT EXISTS roles (
    id VARCHAR(50) PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_role_name (role_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: permissions
CREATE TABLE IF NOT EXISTS permissions (
    id VARCHAR(50) PRIMARY KEY,
    permission_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    module VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_permission_name (permission_name),
    INDEX idx_module (module)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: role_permissions
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id VARCHAR(50) NOT NULL,
    permission_id VARCHAR(50) NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
    INDEX idx_role_id (role_id),
    INDEX idx_permission_id (permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: user_roles
CREATE TABLE IF NOT EXISTS user_roles (
    user_id VARCHAR(50) NOT NULL,
    role_id VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: action_logs
CREATE TABLE IF NOT EXISTS action_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50),
    user_name VARCHAR(255),
    action_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id VARCHAR(50),
    entity_name VARCHAR(255),
    action_details TEXT,
    ip_address VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_action_type (action_type),
    INDEX idx_entity_type (entity_type),
    INDEX idx_created_at (created_at),
    INDEX idx_user_action (user_id, action_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: email_schedules (for weekly payment emails and contract reminders)
CREATE TABLE IF NOT EXISTS email_schedules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    schedule_type ENUM('weekly_payment', 'contract_reminder') NOT NULL,
    name VARCHAR(255) NOT NULL,
    recipients TEXT NOT NULL,
    day_of_week VARCHAR(20),
    send_time TIME,
    reminder_days_before INT,
    contract_selection_type ENUM('all', 'selected', 'filtered') DEFAULT 'all',
    selected_contract_ids TEXT,
    contract_types TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_sent_at DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_schedule_type (schedule_type),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


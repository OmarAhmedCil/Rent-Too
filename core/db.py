# core/db.py
# Database connection and utility functions
import os
import mysql.connector
from mysql.connector import Error
import pandas as pd

from conf.constants import *
from conf.database import DB_CONFIG, validate_table_name


def _ensure_contract_optional_columns(cursor):
    """Best-effort schema sync for optional contracts columns."""
    try:
        cursor.execute("SHOW COLUMNS FROM contracts")
        existing_cols = {row[0] for row in cursor.fetchall()}
    except Exception:
        return

    # Keep this small and safe: only additive columns needed by current app flows.
    optional_cols = {
        "advance_payment": "VARCHAR(50) DEFAULT NULL",
        "rev_share_payment_advance": "VARCHAR(50) DEFAULT NULL",
        "rev_share_advance_mode": "VARCHAR(50) DEFAULT NULL",
        "advance_months_count": "VARCHAR(20) DEFAULT NULL",
        "increase_by_period_mode": "VARCHAR(30) DEFAULT NULL",
        "increase_by_period_all_pct": "VARCHAR(50) DEFAULT NULL",
        "increase_by_period_map": "TEXT",
    }
    for col_name, col_def in optional_cols.items():
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE contracts ADD COLUMN `{col_name}` {col_def}")
            except Exception:
                # Non-fatal: app still has dynamic insert/update fallback.
                pass


def ensure_monthly_distribution_and_payment_schema():
    """Backward-compatible name: applies V2 additive schema (rent_month, amount, due_amount, service line cols).

    For structural upgrades beyond additive columns, align the database with
    `database/schema.sql` using your own DBA process (or recover old scripts from git history).
    """
    ensure_v2_distribution_payment_schema()


def ensure_v2_distribution_payment_schema():
    """Additive migrations for contract-level distribution + payment line columns (safe on older DBs)."""
    connection = get_db_connection()
    if connection is None:
        return
    cursor = connection.cursor()
    try:

        def add_col(table: str, col: str, ddl: str) -> None:
            try:
                cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,))
                if cursor.fetchone():
                    return
                cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {ddl}")
            except Exception as e:
                print(f"Schema note {table}.{col}: {e}")

        for dist_table in (
            "contract_distribution_fixed",
            "contract_distribution_revenue_share",
            "contract_distribution_rou",
        ):
            add_col(dist_table, "due_amount", "VARCHAR(50) NULL")
            add_col(dist_table, "yearly_increase_amount", "VARCHAR(50) NULL")

        add_col("service_distribution", "discount_amount", "VARCHAR(50) NULL DEFAULT '0'")
        add_col("service_distribution", "due_amount", "VARCHAR(50) NULL")

        add_col("payments", "rent_month", "DATE NULL")
        add_col("payments", "amount", "VARCHAR(50) NULL")
        add_col("payments", "lessor_share_pct", "VARCHAR(50) NULL")

        connection.commit()
    except Exception as e:
        print(f"ensure_v2_distribution_payment_schema: {e}")
        try:
            connection.rollback()
        except Exception:
            pass
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        connection.close()


def get_db_connection():
    """Create and return a database connection"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def execute_query(query, params=None, fetch=True):
    """Execute a query and return results"""
    connection = get_db_connection()
    if connection is None:
        return None
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        
        if fetch:
            result = cursor.fetchall()
            cursor.close()
            connection.close()
            return result
        else:
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error executing query: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return None

def load_table_to_df(table_name, columns):
    """Load a table into a pandas DataFrame"""
    try:
        table_name = validate_table_name(table_name)
        connection = get_db_connection()
        if connection is None:
            return pd.DataFrame(columns=columns)
        
        # Special handling for contract distribution tables - use JOINs to get names
        if table_name == "contract_distribution_revenue_share":
            # Revenue share % fields live on `contracts` only; expose UI column names via JOIN.
            query = """
                SELECT 
                    d.id,
                    d.contract_id,
                    d.rent_date,
                    d.rent_amount,
                    d.yearly_increase_amount,
                    d.revenue_min,
                    d.revenue_max,
                    d.revenue_amount,
                    d.discount_amount,
                    d.advanced_amount,
                    d.due_amount,
                    d.created_at,
                    DATE_FORMAT(d.rent_date, '%Y-%m') AS month_year,
                    YEAR(d.rent_date) AS year,
                    MONTH(d.rent_date) AS month,
                    c.contract_name,
                    c.contract_type,
                    COALESCE(ast.name, sto.name) AS asset_or_store_name,
                    c.rev_share_pct AS revenue_share_pct,
                    c.rev_share_after_max_pc AS revenue_share_after_max_pct
                FROM `contract_distribution_revenue_share` d
                LEFT JOIN contracts c ON d.contract_id = c.id
                LEFT JOIN assets ast ON c.asset_or_store_id = ast.id
                LEFT JOIN stores sto ON c.asset_or_store_id = sto.id
            """
        elif table_name in ["contract_distribution", "contract_distribution_fixed", "contract_distribution_rou"]:
            query = f"""
                SELECT 
                    d.*,
                    DATE_FORMAT(d.rent_date, '%Y-%m') AS month_year,
                    YEAR(d.rent_date) AS year,
                    MONTH(d.rent_date) AS month,
                    c.contract_name,
                    c.contract_type,
                    COALESCE(ast.name, sto.name) AS asset_or_store_name
                FROM `{table_name}` d
                LEFT JOIN contracts c ON d.contract_id = c.id
                LEFT JOIN assets ast ON c.asset_or_store_id = ast.id
                LEFT JOIN stores sto ON c.asset_or_store_id = sto.id
            """
        elif table_name == "service_distribution":
            query = """
                SELECT 
                    sd.*,
                    DATE_FORMAT(sd.rent_date, '%Y-%m') AS month_year,
                    YEAR(sd.rent_date) AS year,
                    MONTH(sd.rent_date) AS month,
                    c.contract_name,
                    c.contract_type,
                    sv.name AS service_name
                FROM service_distribution sd
                LEFT JOIN contracts c ON sd.contract_id = c.id
                LEFT JOIN services sv ON sd.service_id = sv.id
            """
        elif table_name == "store_monthly_sales":
            # Special handling for store_monthly_sales - derive year/month/month_year from rent_date for UI compatibility
            query = """
                SELECT 
                    sms.*,
                    DATE_FORMAT(sms.rent_date, '%Y-%m') AS month_year,
                    YEAR(sms.rent_date) AS year,
                    MONTH(sms.rent_date) AS month,
                    s.name AS store_name
                FROM store_monthly_sales sms
                LEFT JOIN stores s ON sms.store_id = s.id
            """
        else:
            query = f"SELECT * FROM `{table_name}`"
        
        # Suppress pandas warning about mysql.connector - it works fine
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=UserWarning)
            df = pd.read_sql(query, connection)
        connection.close()

        # JOIN + sd.* / d.* can produce duplicate SQL column labels (e.g. legacy
        # columns on the fact table matching joined names). Non-unique columns
        # break pd.concat and other ops — keep the first occurrence.
        if not df.empty and df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()].copy()
        
        # Ensure all columns exist
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        
        # Select only the columns we want (in the correct order)
        df = df[columns]
        return df.fillna("")
    except Exception as e:
        print(f"Error loading table {table_name}: {e}")
        return pd.DataFrame(columns=columns)

def save_df_to_table(df, table_name, columns):
    """Save a DataFrame to a table (replace all data for non-critical, insert/update for critical)"""
    try:
        table_name = validate_table_name(table_name)
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()

        # --- Schema drift + DATE safety ---
        # - Drop columns that don't exist in MySQL (avoids 1054).
        # - Treat ALL DATE columns as None when empty (avoids 1292 Incorrect date value '').
        date_columns_from_db = set()
        try:
            cursor_cols = connection.cursor()
            cursor_cols.execute(f"SHOW COLUMNS FROM `{table_name}`")
            cols_info = cursor_cols.fetchall()  # (Field, Type, Null, Key, Default, Extra)
            cursor_cols.close()
            existing_cols = {row[0] for row in cols_info}
            date_columns_from_db = {row[0] for row in cols_info if isinstance(row[1], str) and row[1].lower().startswith("date")}
            columns = [c for c in columns if c in existing_cols]
        except Exception:
            pass
        
        # For critical tables (user_roles, role_permissions), use INSERT/UPDATE instead of DELETE ALL
        # This prevents accidental deletion of data not in the DataFrame
        critical_tables = {'user_roles', 'role_permissions', 'contract_lessors'}
        is_critical = table_name in critical_tables
        
        if is_critical:
            # For critical tables, use INSERT ... ON DUPLICATE KEY UPDATE
            # This way we only update/add records in the DataFrame, not delete others
            if df.empty:
                # Don't do anything if DataFrame is empty - this is likely an error
                print(f"Warning: Attempted to save empty DataFrame to critical table {table_name}. Skipping.")
                cursor.close()
                connection.close()
                return False
            
            # Ensure all columns exist
            date_columns = set(date_columns_from_db) or {
                col for col in columns
                if '_date' in col.lower() or col.lower() in ['rent_date', 'payment_date', 'commencement_date', 'end_date', 'first_payment_date']
            }
            
            for col in columns:
                if col not in df.columns:
                    # Use None for date columns, empty string for others
                    if col in date_columns:
                        df[col] = None
                    else:
                        df[col] = ""
            
            # Select only the columns we want
            df = df[columns]
            
            # Prepare insert statement with ON DUPLICATE KEY UPDATE
            placeholders = ', '.join(['%s'] * len(columns))
            columns_str = ', '.join([f"`{col}`" for col in columns])
            
            if table_name in {'user_roles', 'contract_lessors'}:
                # These tables have composite primary keys
                # Use INSERT ... ON DUPLICATE KEY UPDATE
                update_clause = ', '.join([f"`{col}` = VALUES(`{col}`)" for col in columns[1:]])  # Skip first column (part of PK)
                insert_query = f"INSERT INTO `{table_name}` ({columns_str}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
            else:
                # role_permissions also has composite PK
                update_clause = ', '.join([f"`{col}` = VALUES(`{col}`)" for col in columns[1:]])
                insert_query = f"INSERT INTO `{table_name}` ({columns_str}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
            
            # Convert DataFrame to list of tuples
            # Handle NaN values and empty strings for date columns
            import numpy as np
            df = df.replace({np.nan: None})
            
            date_columns = set(date_columns_from_db) or {
                col for col in columns
                if '_date' in col.lower() or col.lower() in ['rent_date', 'payment_date', 'commencement_date', 'end_date', 'first_payment_date']
            }
            
            # Convert empty strings to None for date columns
            for col in date_columns:
                if col in df.columns:
                    df[col] = df[col].replace('', None)
                    # Also handle string 'None' or 'nan'
                    df[col] = df[col].replace('None', None)
                    df[col] = df[col].replace('nan', None)
            
            values = [tuple(row) for row in df.values]
            
            if values:
                cursor.executemany(insert_query, values)
            else:
                print(f"Warning: No values to insert for table {table_name}")
        else:
            # For non-critical tables, use DELETE ALL then INSERT (original behavior)
            cursor.execute(f"DELETE FROM `{table_name}`")
            
            # Insert new records
            if not df.empty:
                # Ensure all columns exist
                date_columns = set(date_columns_from_db) or {
                    col for col in columns
                    if '_date' in col.lower() or col.lower() in ['rent_date', 'payment_date', 'commencement_date', 'end_date', 'first_payment_date']
                }
                
                for col in columns:
                    if col not in df.columns:
                        # Use None for date columns, empty string for others
                        if col in date_columns:
                            df[col] = None
                        else:
                            df[col] = ""
                
                # Select only the columns we want
                df = df[columns]
                
                # Prepare insert statement
                placeholders = ', '.join(['%s'] * len(columns))
                columns_str = ', '.join([f"`{col}`" for col in columns])
                insert_query = f"INSERT INTO `{table_name}` ({columns_str}) VALUES ({placeholders})"
                
                # Convert DataFrame to list of tuples
                # Handle NaN values and empty strings for date columns
                import numpy as np
                df = df.replace({np.nan: None})
                
                date_columns = set(date_columns_from_db) or {
                    col for col in columns
                    if '_date' in col.lower() or col.lower() in ['rent_date', 'payment_date', 'commencement_date', 'end_date', 'first_payment_date']
                }
                
                # Convert empty strings to None for date columns
                for col in date_columns:
                    if col in df.columns:
                        df[col] = df[col].replace('', None)
                        # Also handle string 'None' or 'nan'
                        df[col] = df[col].replace('None', None)
                        df[col] = df[col].replace('nan', None)
                
                values = [tuple(row) for row in df.values]
                
                if values:
                    cursor.executemany(insert_query, values)
                else:
                    print(f"Warning: No values to insert for table {table_name}")
        
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        error_msg = f"Database error saving to table {table_name}: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        try:
            import streamlit as st
            st.error(error_msg)
            st.error(f"Full error: {traceback.format_exc()}")
        except:
            pass
        if connection:
            try:
                connection.rollback()
                connection.close()
            except:
                pass
        return False
    except Exception as e:
        error_msg = f"Unexpected error saving to table {table_name}: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        try:
            import streamlit as st
            st.error(error_msg)
            st.error(f"Full error: {traceback.format_exc()}")
        except:
            pass
        if connection:
            try:
                connection.rollback()
                connection.close()
            except:
                pass
        return False

def insert_row_to_table(table_name, row_dict):
    """Insert a single row into a table"""
    try:
        table_name = validate_table_name(table_name)
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        columns = list(row_dict.keys())
        values = list(row_dict.values())
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join([f"`{col}`" for col in columns])
        insert_query = f"INSERT INTO `{table_name}` ({columns_str}) VALUES ({placeholders})"
        
        cursor.execute(insert_query, values)
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting row to {table_name}: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_user(user_data):
    """Insert a new user directly to database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        # Use INSERT IGNORE or ON DUPLICATE KEY UPDATE to handle duplicates gracefully
        insert_query = """
            INSERT INTO users (id, email, password_hash, name, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                email = VALUES(email),
                name = VALUES(name),
                is_active = VALUES(is_active)
        """
        cursor.execute(insert_query, (
            str(user_data['id']),
            user_data['email'],
            user_data['password_hash'],
            user_data['name'],
            user_data['is_active'],
            user_data['created_at']
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting user: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def get_user_by_id(user_id):
    """Return active user row as dict (id, email, name, is_active) or None."""
    try:
        rows = execute_query(
            "SELECT id, email, name, is_active FROM users WHERE id = %s LIMIT 1",
            (str(user_id),),
        )
        if not rows:
            return None
        return rows[0]
    except Exception as e:
        print(f"Error fetching user by id: {e}")
        return None

def update_user(user_id, user_data):
    """Update a user in database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        update_query = """
            UPDATE users 
            SET email = %s, name = %s, is_active = %s
            WHERE id = %s
        """
        cursor.execute(update_query, (
            user_data.get('email'),
            user_data.get('name'),
            user_data.get('is_active'),
            str(user_id)
        ))
        
        # Update password if provided
        if 'password_hash' in user_data and user_data['password_hash']:
            password_query = "UPDATE users SET password_hash = %s WHERE id = %s"
            cursor.execute(password_query, (user_data['password_hash'], str(user_id)))
        
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating user: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_user(user_id):
    """Delete a user from database (cascade will handle user_roles)"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM users WHERE id = %s"
        cursor.execute(delete_query, (str(user_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting user: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_role(role_data):
    """Insert a new role directly to database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        # Use INSERT IGNORE or ON DUPLICATE KEY UPDATE to handle duplicates gracefully
        insert_query = """
            INSERT INTO roles (id, role_name, description, created_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                role_name = VALUES(role_name),
                description = VALUES(description)
        """
        cursor.execute(insert_query, (
            str(role_data['id']),
            role_data['role_name'],
            role_data['description'],
            role_data['created_at']
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting role: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def update_role(role_id, role_data):
    """Update a role in database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        update_query = """
            UPDATE roles 
            SET role_name = %s, description = %s
            WHERE id = %s
        """
        cursor.execute(update_query, (
            role_data.get('role_name'),
            role_data.get('description'),
            str(role_id)
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating role: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_role(role_id):
    """Delete a role from database (cascade will handle user_roles and role_permissions)"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM roles WHERE id = %s"
        cursor.execute(delete_query, (str(role_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting role: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_user_role(user_id, role_id):
    """Insert a user-role assignment"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO user_roles (user_id, role_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE user_id = user_id
        """
        cursor.execute(insert_query, (str(user_id), str(role_id)))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting user role: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_role_permission(role_id, permission_id):
    """Insert a role-permission assignment"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE role_id = role_id
        """
        cursor.execute(insert_query, (str(role_id), str(permission_id)))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting role permission: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_role_permission(role_id, permission_id):
    """Delete a role-permission assignment"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM role_permissions WHERE role_id = %s AND permission_id = %s"
        cursor.execute(delete_query, (str(role_id), str(permission_id)))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting role permission: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_role_permissions_bulk(role_id, permission_ids):
    """Insert multiple role-permission assignments at once"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE role_id = role_id
        """
        values = [(str(role_id), str(perm_id)) for perm_id in permission_ids]
        cursor.executemany(insert_query, values)
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting role permissions bulk: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_contract(contract_data):
    """Insert a new contract directly to database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        _ensure_contract_optional_columns(cursor)

        # MySQL DATE columns cannot accept empty string '' (will raise 1292).
        # Normalize any empty/falsey date values to None so they are stored as NULL.
        commencement_date = contract_data.get('commencement_date') or None
        end_date = contract_data.get('end_date') or None
        first_payment_date = contract_data.get('first_payment_date') or None

        cursor.execute("SHOW COLUMNS FROM contracts")
        existing_cols = {row[0] for row in cursor.fetchall()}

        contract_row = {
            "id": str(contract_data["id"]),
            "contract_name": contract_data["contract_name"],
            "contract_type": contract_data["contract_type"],
            "currency": contract_data["currency"],
            "asset_category": contract_data["asset_category"],
            "asset_or_store_id": contract_data["asset_or_store_id"],
            "asset_or_store_name": contract_data["asset_or_store_name"],
            "commencement_date": commencement_date,
            "tenure_months": contract_data["tenure_months"],
            "end_date": end_date,
            "lessors_json": contract_data["lessors_json"],
            "discount_rate": contract_data["discount_rate"],
            "tax": contract_data["tax"],
            "is_tax_added": int(contract_data.get("is_tax_added", 0) or 0),
            "payment_frequency": contract_data["payment_frequency"],
            "yearly_increase": contract_data["yearly_increase"],
            "yearly_increase_type": contract_data.get("yearly_increase_type", ""),
            "yearly_increase_fixed_amount": contract_data.get("yearly_increase_fixed_amount", ""),
            "rent_amount": contract_data["rent_amount"],
            "rev_min": contract_data["rev_min"],
            "rev_max": contract_data["rev_max"],
            "rev_share_pct": contract_data["rev_share_pct"],
            "rev_share_after_max_pc": contract_data["rev_share_after_max_pc"],
            "sales_type": contract_data.get("sales_type", ""),
            "rent_per_year": contract_data.get("rent_per_year", ""),
            "first_payment_date": first_payment_date,
            "free_months": contract_data.get("free_months", ""),
            "advance_months": contract_data.get("advance_months", ""),
            "advance_months_count": contract_data.get("advance_months_count", ""),
            "increase_by_period_mode": contract_data.get("increase_by_period_mode", "all"),
            "increase_by_period_all_pct": contract_data.get("increase_by_period_all_pct", ""),
            "increase_by_period_map": contract_data.get("increase_by_period_map", ""),
            "advance_payment": contract_data.get("advance_payment", ""),
            "rev_share_payment_advance": contract_data.get("rev_share_payment_advance", ""),
            "rev_share_advance_mode": contract_data.get("rev_share_advance_mode", ""),
            "created_at": contract_data["created_at"],
        }
        filtered_items = [(k, v) for k, v in contract_row.items() if k in existing_cols]
        insert_cols = [k for k, _ in filtered_items]
        insert_vals = [v for _, v in filtered_items]
        placeholders = ", ".join(["%s"] * len(insert_cols))
        cols_sql = ", ".join([f"`{c}`" for c in insert_cols])
        insert_query = f"INSERT INTO contracts ({cols_sql}) VALUES ({placeholders})"
        cursor.execute(insert_query, insert_vals)
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting contract: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def update_contract(contract_id, contract_data):
    """Update a contract in database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        _ensure_contract_optional_columns(cursor)

        # Normalize DATE fields (avoid MySQL 1292 Incorrect date value '')
        commencement_date = contract_data.get('commencement_date') or None
        end_date = contract_data.get('end_date') or None
        first_payment_date = contract_data.get('first_payment_date') or None

        cursor.execute("SHOW COLUMNS FROM contracts")
        existing_cols = {row[0] for row in cursor.fetchall()}

        update_row = {
            "contract_name": contract_data["contract_name"],
            "contract_type": contract_data["contract_type"],
            "currency": contract_data["currency"],
            "asset_category": contract_data["asset_category"],
            "asset_or_store_id": contract_data["asset_or_store_id"],
            "asset_or_store_name": contract_data["asset_or_store_name"],
            "commencement_date": commencement_date,
            "tenure_months": contract_data["tenure_months"],
            "end_date": end_date,
            "lessors_json": contract_data["lessors_json"],
            "discount_rate": contract_data["discount_rate"],
            "tax": contract_data["tax"],
            "is_tax_added": int(contract_data.get("is_tax_added", 0) or 0),
            "payment_frequency": contract_data["payment_frequency"],
            "yearly_increase": contract_data["yearly_increase"],
            "yearly_increase_type": contract_data.get("yearly_increase_type", ""),
            "yearly_increase_fixed_amount": contract_data.get("yearly_increase_fixed_amount", ""),
            "rent_amount": contract_data["rent_amount"],
            "rev_min": contract_data["rev_min"],
            "rev_max": contract_data["rev_max"],
            "rev_share_pct": contract_data["rev_share_pct"],
            "rev_share_after_max_pc": contract_data["rev_share_after_max_pc"],
            "sales_type": contract_data.get("sales_type", ""),
            "rent_per_year": contract_data.get("rent_per_year", ""),
            "first_payment_date": first_payment_date,
            "free_months": contract_data.get("free_months", ""),
            "advance_months": contract_data.get("advance_months", ""),
            "advance_months_count": contract_data.get("advance_months_count", ""),
            "increase_by_period_mode": contract_data.get("increase_by_period_mode", "all"),
            "increase_by_period_all_pct": contract_data.get("increase_by_period_all_pct", ""),
            "increase_by_period_map": contract_data.get("increase_by_period_map", ""),
            "advance_payment": contract_data.get("advance_payment", ""),
            "rev_share_payment_advance": contract_data.get("rev_share_payment_advance", ""),
            "rev_share_advance_mode": contract_data.get("rev_share_advance_mode", ""),
        }
        filtered_items = [(k, v) for k, v in update_row.items() if k in existing_cols]
        set_clause = ", ".join([f"`{k}` = %s" for k, _ in filtered_items])
        update_vals = [v for _, v in filtered_items]
        update_query = f"UPDATE contracts SET {set_clause} WHERE id = %s"
        cursor.execute(update_query, update_vals + [str(contract_id)])
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating contract: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_contract(contract_id):
    """Delete a contract from database and all related data (payments, distribution, logs)"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        contract_id_str = str(contract_id)
        
        # 1. Delete payments (both contract and service payments)
        try:
            delete_payments_query = "DELETE FROM payments WHERE contract_id = %s"
            cursor.execute(delete_payments_query, (contract_id_str,))
            print(f"Deleted payments for contract {contract_id_str}")
        except Error as e:
            print(f"Warning: Error deleting payments for contract {contract_id_str}: {e}")
        
        # 2. Delete distribution data from all three distribution tables
        from conf.constants import CONTRACT_DISTRIBUTION_FIXED_TABLE, CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE, CONTRACT_DISTRIBUTION_ROU_TABLE
        distribution_tables = [
            CONTRACT_DISTRIBUTION_FIXED_TABLE,
            CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE,
            CONTRACT_DISTRIBUTION_ROU_TABLE
        ]
        for table in distribution_tables:
            try:
                delete_dist_query = f"DELETE FROM `{table}` WHERE contract_id = %s"
                cursor.execute(delete_dist_query, (contract_id_str,))
                print(f"Deleted distribution data from {table} for contract {contract_id_str}")
            except Error as e:
                print(f"Warning: Error deleting distribution from {table} for contract {contract_id_str}: {e}")
        
        # 3. Delete service distribution
        try:
            delete_service_dist_query = "DELETE FROM service_distribution WHERE contract_id = %s"
            cursor.execute(delete_service_dist_query, (contract_id_str,))
            print(f"Deleted service distribution for contract {contract_id_str}")
        except Error as e:
            print(f"Warning: Error deleting service distribution for contract {contract_id_str}: {e}")
        
        # 4. Delete contract services and service lessors (cascade may handle this, but explicit is safer)
        try:
            delete_service_lessors_query = "DELETE FROM contract_service_lessors WHERE contract_id = %s"
            cursor.execute(delete_service_lessors_query, (contract_id_str,))
            delete_services_query = "DELETE FROM contract_services WHERE contract_id = %s"
            cursor.execute(delete_services_query, (contract_id_str,))
            print(f"Deleted contract services and service lessors for contract {contract_id_str}")
        except Error as e:
            print(f"Warning: Error deleting contract services for contract {contract_id_str}: {e}")
        
        # 5. Delete contract lessors (cascade may handle this, but explicit is safer)
        try:
            delete_lessors_query = "DELETE FROM contract_lessors WHERE contract_id = %s"
            cursor.execute(delete_lessors_query, (contract_id_str,))
            print(f"Deleted contract lessors for contract {contract_id_str}")
        except Error as e:
            print(f"Warning: Error deleting contract lessors for contract {contract_id_str}: {e}")
        
        # 6. Delete action logs related to this contract (before deleting contract so we can use contract_id)
        try:
            delete_logs_query = "DELETE FROM action_logs WHERE entity_type = 'contract' AND entity_id = %s"
            cursor.execute(delete_logs_query, (contract_id_str,))
            print(f"Deleted action logs for contract {contract_id_str}")
        except Error as e:
            print(f"Warning: Error deleting action logs for contract {contract_id_str}: {e}")
        
        # 7. Finally, delete the contract itself
        delete_query = "DELETE FROM contracts WHERE id = %s"
        cursor.execute(delete_query, (contract_id_str,))
        
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting contract: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_contract_lessors(contract_id):
    """Delete all contract-lessor relationships for a contract"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM contract_lessors WHERE contract_id = %s"
        cursor.execute(delete_query, (str(contract_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting contract lessors: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_contract_lessor(contract_id, lessor_id, share_pct):
    """Insert a contract-lessor relationship"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO contract_lessors (contract_id, lessor_id, share_pct)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE share_pct = VALUES(share_pct)
        """
        cursor.execute(insert_query, (str(contract_id), str(lessor_id), str(share_pct)))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting contract lessor: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_lessor(lessor_data):
    """Insert a new lessor directly to database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO lessors (id, name, description, tax_id, supplier_code, iban)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            str(lessor_data['id']),
            lessor_data['name'],
            lessor_data.get('description', ''),
            lessor_data.get('tax_id', ''),
            lessor_data.get('supplier_code', ''),
            lessor_data.get('iban', '')
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting lessor: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def update_lessor(lessor_id, lessor_data):
    """Update a lessor in database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        update_query = """
            UPDATE lessors SET
                name = %s, description = %s, tax_id = %s, supplier_code = %s, iban = %s
            WHERE id = %s
        """
        cursor.execute(update_query, (
            lessor_data['name'],
            lessor_data.get('description', ''),
            lessor_data.get('tax_id', ''),
            lessor_data.get('supplier_code', ''),
            lessor_data.get('iban', ''),
            str(lessor_id)
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating lessor: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_lessor(lessor_id):
    """Delete a lessor from database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM lessors WHERE id = %s"
        cursor.execute(delete_query, (str(lessor_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting lessor: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

# Service CRUD functions
def insert_service(service_data):
    """Insert a new service directly to database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO services (id, name, description, currency)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            str(service_data['id']),
            service_data['name'],
            service_data.get('description', ''),
            service_data.get('currency', 'EGP')
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting service: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def update_service(service_id, service_data):
    """Update a service in database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        update_query = """
            UPDATE services SET
                name = %s, description = %s, currency = %s
            WHERE id = %s
        """
        cursor.execute(update_query, (
            service_data['name'],
            service_data.get('description', ''),
            service_data.get('currency', 'EGP'),
            str(service_id)
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating service: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_service(service_id):
    """Delete a service from database (cascade will handle contract_services)"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM services WHERE id = %s"
        cursor.execute(delete_query, (str(service_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting service: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_contract_service(contract_id, service_id, amount, yearly_increase_pct):
    """Insert a contract-service relationship"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO contract_services (contract_id, service_id, amount, yearly_increase_pct)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE amount = VALUES(amount), yearly_increase_pct = VALUES(yearly_increase_pct)
        """
        cursor.execute(insert_query, (
            str(contract_id),
            str(service_id),
            str(amount),
            str(yearly_increase_pct)
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting contract service: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_contract_service(contract_id, service_id):
    """Delete a contract-service relationship"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM contract_services WHERE contract_id = %s AND service_id = %s"
        cursor.execute(delete_query, (str(contract_id), str(service_id)))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting contract service: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_contract_services(contract_id):
    """Delete all services for a contract"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM contract_services WHERE contract_id = %s"
        cursor.execute(delete_query, (str(contract_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting contract services: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_contract_service_lessors(contract_id):
    """Delete all service-lessor relationships for a contract"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM contract_service_lessors WHERE contract_id = %s"
        cursor.execute(delete_query, (str(contract_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting contract service lessors: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_payment(
    contract_id,
    lessor_id,
    payment_date,
    due_amount,
    payment_amount,
    rent_month=None,
    amount=None,
    service_id=None,
    tax_pct=None,
    tax_amount=None,
    withholding_amount=None,
    lessor_share_pct=None,
):
    """Insert a payment row. Supports V2 (rent_month, amount) and legacy extra columns if still present."""
    connection = None
    try:
        connection = get_db_connection()
        if connection is None:
            return False

        cursor = connection.cursor()
        cursor.execute("SHOW COLUMNS FROM payments")
        pay_col_set = {row[0] for row in cursor.fetchall()}

        values = {
            "contract_id": str(contract_id),
            "lessor_id": str(lessor_id) if lessor_id is not None else None,
            "rent_month": rent_month if rent_month else None,
            "payment_date": payment_date if payment_date else None,
            "amount": str(amount) if amount is not None else None,
            "due_amount": str(due_amount) if due_amount is not None else None,
            "payment_amount": str(payment_amount) if payment_amount is not None else None,
            "service_id": str(service_id) if service_id else None,
            "tax_pct": str(tax_pct) if tax_pct is not None else None,
            "tax_amount": str(tax_amount) if tax_amount is not None else None,
            "withholding_amount": str(withholding_amount) if withholding_amount is not None else None,
            "lessor_share_pct": str(lessor_share_pct) if lessor_share_pct is not None else None,
            "distribution_id": None,
            "currency": "",
            "payment_type": "Service Payment" if service_id else "Contract Payment",
        }

        preferred_order = [
            "contract_id",
            "lessor_id",
            "distribution_id",
            "rent_month",
            "payment_date",
            "amount",
            "due_amount",
            "payment_amount",
            "currency",
            "payment_type",
            "service_id",
            "tax_pct",
            "tax_amount",
            "withholding_amount",
            "lessor_share_pct",
        ]
        cols = [c for c in preferred_order if c in pay_col_set]
        vals = [values[c] for c in cols]

        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(f"`{c}`" for c in cols)
        insert_query = f"INSERT INTO payments ({col_sql}) VALUES ({placeholders})"
        cursor.execute(insert_query, tuple(vals))

        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting payment: {e}")
        if connection:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass
        return False

def insert_contract_service_lessor(contract_id, service_id, lessor_id, share_pct):
    """Insert a contract-service-lessor relationship"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO contract_service_lessors (contract_id, service_id, lessor_id, share_pct)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE share_pct = VALUES(share_pct)
        """
        cursor.execute(insert_query, (
            str(contract_id),
            str(service_id),
            str(lessor_id),
            str(share_pct)
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting contract service lessor: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_contract_distribution(contract_id, contract_type=None):
    """Delete all distribution data for a contract from the appropriate table(s)"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        
        if contract_type:
            # Delete from specific table based on contract type
            from conf.constants import CONTRACT_DISTRIBUTION_FIXED_TABLE, CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE, CONTRACT_DISTRIBUTION_ROU_TABLE
            
            if contract_type == "Fixed":
                table = CONTRACT_DISTRIBUTION_FIXED_TABLE
            elif contract_type == "Revenue Share":
                table = CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE
            elif contract_type == "ROU":
                table = CONTRACT_DISTRIBUTION_ROU_TABLE
            else:
                # Invalid contract type, try all tables
                tables = [CONTRACT_DISTRIBUTION_FIXED_TABLE, CONTRACT_DISTRIBUTION_REVENUE_SHARE_TABLE, CONTRACT_DISTRIBUTION_ROU_TABLE]
                for table in tables:
                    delete_query = f"DELETE FROM `{table}` WHERE contract_id = %s"
                    cursor.execute(delete_query, (str(contract_id),))
                connection.commit()
                cursor.close()
                connection.close()
                # Also delete payment records
                delete_payments_connection = get_db_connection()
                if delete_payments_connection:
                    delete_payments_cursor = delete_payments_connection.cursor()
                    delete_payments_query = "DELETE FROM payments WHERE contract_id = %s"
                    delete_payments_cursor.execute(delete_payments_query, (str(contract_id),))
                    delete_payments_connection.commit()
                    delete_payments_cursor.close()
                    delete_payments_connection.close()
                return True
            
            delete_query = f"DELETE FROM `{table}` WHERE contract_id = %s"
            cursor.execute(delete_query, (str(contract_id),))
        else:
            # Delete from all distribution tables
            tables = [
                'contract_distribution_fixed',
                'contract_distribution_revenue_share',
                'contract_distribution_rou'
            ]
            for table in tables:
                delete_query = f"DELETE FROM `{table}` WHERE contract_id = %s"
                cursor.execute(delete_query, (str(contract_id),))
        
        # Also delete payment records for this contract
        delete_payments_query = "DELETE FROM payments WHERE contract_id = %s"
        cursor.execute(delete_payments_query, (str(contract_id),))
        
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting contract distribution: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def get_lessor_withholding_periods(lessor_id):
    """Get withholding periods for a lessor"""
    try:
        connection = get_db_connection()
        if connection is None:
            return []
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT id, lessor_id, start_date, end_date
            FROM lessor_withholding_periods
            WHERE lessor_id = %s
            ORDER BY start_date
        """
        cursor.execute(query, (str(lessor_id),))
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return rows
    except Error as e:
        print(f"Error fetching lessor withholding periods: {e}")
        if connection:
            connection.close()
        return []

def upsert_lessor_withholding_periods(lessor_id, periods):
    """
    Replace all withholding periods for a lessor with the provided list.
    periods: list of dicts with keys: start_date (date), end_date (date)
    """
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        cursor = connection.cursor()
        # Delete existing periods
        cursor.execute("DELETE FROM lessor_withholding_periods WHERE lessor_id = %s", (str(lessor_id),))
        # Helper to normalize various pandas/numpy/py types to 'YYYY-MM-DD' strings
        def _normalize_date_value(val):
            import pandas as pd
            try:
                import numpy as np
            except ImportError:
                np = None

            # Unwrap common container types (Index, ndarray, list, tuple) by taking first element
            if np is not None and isinstance(val, (np.ndarray, pd.Index)):
                if len(val) == 0:
                    return None
                val = val[0]
            if isinstance(val, (list, tuple)) and val:
                val = val[0]

            # Pandas Timestamp or datetime/date objects
            if isinstance(val, pd.Timestamp):
                return val.strftime("%Y-%m-%d")
            if hasattr(val, "strftime"):
                return val.strftime("%Y-%m-%d")

            # Already a string; let MySQL parse it or fail
            return str(val) if val is not None else None

        # Insert new periods
        insert_query = """
            INSERT INTO lessor_withholding_periods (lessor_id, start_date, end_date)
            VALUES (%s, %s, %s)
        """
        for p in periods:
            # p is expected to be a dict with normalized date-like values
            if isinstance(p, dict):
                start_val = p.get("start_date")
                end_val = p.get("end_date")
            else:
                # Fallback for unexpected types (e.g., Series); try attribute access
                start_val = getattr(p, "start_date", None)
                end_val = getattr(p, "end_date", None)

            start_str = _normalize_date_value(start_val)
            end_str = _normalize_date_value(end_val)

            cursor.execute(
                insert_query,
                (str(lessor_id), start_str, end_str),
            )
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error upserting lessor withholding periods: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_service_distribution(contract_id):
    """Delete all service distribution data for a contract"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM service_distribution WHERE contract_id = %s"
        cursor.execute(delete_query, (str(contract_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting service distribution: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def insert_asset(asset_data):
    """Insert a new asset directly to database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO assets (id, name, cost_center)
            VALUES (%s, %s, %s)
        """
        cursor.execute(insert_query, (
            str(asset_data['id']),
            asset_data['name'],
            asset_data.get('cost_center', '')
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error inserting asset: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def update_asset(asset_id, asset_data):
    """Update an asset in database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        update_query = """
            UPDATE assets SET
                name = %s, cost_center = %s
            WHERE id = %s
        """
        cursor.execute(update_query, (
            asset_data['name'],
            asset_data.get('cost_center', ''),
            str(asset_id)
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating asset: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_asset(asset_id):
    """Delete an asset from database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM assets WHERE id = %s"
        cursor.execute(delete_query, (str(asset_id),))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting asset: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def update_row_in_table(table_name, row_dict, where_clause, where_params):
    """Update a row in a table"""
    try:
        table_name = validate_table_name(table_name)
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        set_clause = ', '.join([f"`{col}` = %s" for col in row_dict.keys()])
        values = list(row_dict.values()) + list(where_params)
        update_query = f"UPDATE `{table_name}` SET {set_clause} WHERE {where_clause}"
        
        cursor.execute(update_query, values)
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating row in {table_name}: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_row_from_table(table_name, where_clause, where_params):
    """Delete a row from a table"""
    try:
        table_name = validate_table_name(table_name)
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = f"DELETE FROM `{table_name}` WHERE {where_clause}"
        
        cursor.execute(delete_query, where_params)
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting row from {table_name}: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_user_role(user_id, role_id):
    """Delete a specific user-role assignment"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM `user_roles` WHERE `user_id` = %s AND `role_id` = %s"
        cursor.execute(delete_query, (str(user_id), str(role_id)))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting user role: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def get_max_id(table_name, id_column='id', start=1):
    """Get the maximum ID from a table"""
    try:
        table_name = validate_table_name(table_name)
        connection = get_db_connection()
        if connection is None:
            return start
        
        cursor = connection.cursor()
        query = f"SELECT MAX(CAST(`{id_column}` AS UNSIGNED)) as max_id FROM `{table_name}` WHERE `{id_column}` REGEXP '^[0-9]+$'"
        cursor.execute(query)
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if result and result[0] is not None:
            return int(result[0]) + 1
        return start
    except Error as e:
        print(f"Error getting max ID from {table_name}: {e}")
        if connection:
            connection.close()
        return start

def log_action(user_id, user_name, action_type, entity_type=None, entity_id=None, entity_name=None, action_details=None, ip_address=None):
    """Log an action to action_logs table"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        insert_query = """
            INSERT INTO action_logs (user_id, user_name, action_type, entity_type, entity_id, entity_name, action_details, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            str(user_id) if user_id else None,
            user_name or '',
            action_type,
            entity_type,
            str(entity_id) if entity_id else None,
            entity_name,
            action_details,
            ip_address
        ))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error logging action: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_user_role(user_id, role_id):
    """Delete a specific user-role assignment"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        delete_query = "DELETE FROM user_roles WHERE user_id = %s AND role_id = %s"
        cursor.execute(delete_query, (str(user_id), str(role_id)))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting user role: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False



# Email Schedule Functions
def save_email_schedule(schedule_type, name, recipients, day_of_week=None, send_time=None, reminder_days_before=None, contract_selection_type='all', selected_contract_ids=None, contract_types=None, is_active=True):
    """Save email schedule to database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        cursor = connection.cursor()
        recipients_str = ','.join(recipients) if isinstance(recipients, list) else recipients
        contract_ids_str = ','.join(selected_contract_ids) if selected_contract_ids and isinstance(selected_contract_ids, list) else (selected_contract_ids or '')
        contract_types_str = ','.join(contract_types) if contract_types and isinstance(contract_types, list) else (contract_types or '')
        insert_query = """INSERT INTO email_schedules (schedule_type, name, recipients, day_of_week, send_time, reminder_days_before, contract_selection_type, selected_contract_ids, contract_types, is_active) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(insert_query, (schedule_type, name, recipients_str, day_of_week, send_time, reminder_days_before, contract_selection_type, contract_ids_str, contract_types_str, is_active))
        connection.commit()
        schedule_id = cursor.lastrowid
        cursor.close()
        connection.close()
        return schedule_id
    except Error as e:
        print(f"Error saving email schedule: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def get_email_schedules(schedule_type=None, is_active=None):
    """Get email schedules from database"""
    try:
        connection = get_db_connection()
        if connection is None:
            return []
        cursor = connection.cursor(dictionary=True)
        where_clauses = []
        params = []
        if schedule_type:
            where_clauses.append("schedule_type = %s")
            params.append(schedule_type)
        if is_active is not None:
            where_clauses.append("is_active = %s")
            params.append(is_active)
        query = "SELECT * FROM email_schedules"
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return rows
    except Error as e:
        print(f"Error fetching email schedules: {e}")
        if connection:
            connection.close()
        return []

def update_email_schedule(schedule_id, name=None, recipients=None, day_of_week=None, send_time=None, reminder_days_before=None, contract_selection_type=None, selected_contract_ids=None, contract_types=None, is_active=None):
    """Update email schedule"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        cursor = connection.cursor()
        update_fields = []
        params = []
        if name is not None:
            update_fields.append("name = %s")
            params.append(name)
        if recipients is not None:
            recipients_str = ','.join(recipients) if isinstance(recipients, list) else recipients
            update_fields.append("recipients = %s")
            params.append(recipients_str)
        if day_of_week is not None:
            update_fields.append("day_of_week = %s")
            params.append(day_of_week)
        if send_time is not None:
            update_fields.append("send_time = %s")
            params.append(send_time)
        if reminder_days_before is not None:
            update_fields.append("reminder_days_before = %s")
            params.append(reminder_days_before)
        if contract_selection_type is not None:
            update_fields.append("contract_selection_type = %s")
            params.append(contract_selection_type)
        if selected_contract_ids is not None:
            contract_ids_str = ','.join(selected_contract_ids) if isinstance(selected_contract_ids, list) else (selected_contract_ids or '')
            update_fields.append("selected_contract_ids = %s")
            params.append(contract_ids_str)
        if contract_types is not None:
            contract_types_str = ','.join(contract_types) if isinstance(contract_types, list) else (contract_types or '')
            update_fields.append("contract_types = %s")
            params.append(contract_types_str)
        if is_active is not None:
            update_fields.append("is_active = %s")
            params.append(is_active)
        if not update_fields:
            return False
        params.append(schedule_id)
        update_query = f"UPDATE email_schedules SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(update_query, params)
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating email schedule: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False

def delete_email_schedule(schedule_id):
    """Delete email schedule"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        cursor = connection.cursor()
        cursor.execute("DELETE FROM email_schedules WHERE id = %s", (schedule_id,))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error deleting email schedule: {e}")
        if connection:
            connection.rollback()
            connection.close()
        return False


def mark_email_schedule_sent(schedule_id):
    """Set last_sent_at = NOW() after a successful automated send."""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE email_schedules SET last_sent_at = NOW() WHERE id = %s",
            (int(schedule_id),),
        )
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Error as e:
        print(f"Error updating last_sent_at for schedule {schedule_id}: {e}")
        if connection:
            try:
                connection.rollback()
            except Exception:
                pass
            connection.close()
        return False

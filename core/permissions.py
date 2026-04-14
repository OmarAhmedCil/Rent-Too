# core/permissions.py
# Permission checking and role management
import streamlit as st
from core.db import *
from core.auth import get_current_user

# Permission constants
# Key format:  "<module>.<action>"
# Module is auto-derived from the key prefix in initialize_permissions().
PERMISSIONS = {
    # ── Dashboard ────────────────────────────────────────────────────────────
    'dashboard.view': 'View Dashboard',

    # ── Contracts ────────────────────────────────────────────────────────────
    'contracts.view':   'View Contracts',
    'contracts.create': 'Create Contracts',
    'contracts.edit':   'Edit Contracts',
    'contracts.delete': 'Delete Contracts',

    # ── Lessors ──────────────────────────────────────────────────────────────
    'lessors.view':   'View Lessors',
    'lessors.create': 'Create Lessors',
    'lessors.edit':   'Edit Lessors',
    'lessors.delete': 'Delete Lessors',

    # ── Assets ───────────────────────────────────────────────────────────────
    'assets.view':   'View Assets',
    'assets.create': 'Create Assets',
    'assets.edit':   'Edit Assets',
    'assets.delete': 'Delete Assets',

    # ── Stores ───────────────────────────────────────────────────────────────
    'stores.view':   'View Stores',
    'stores.create': 'Create Stores',
    'stores.edit':   'Edit Stores',
    'stores.delete': 'Delete Stores',

    # ── Services ─────────────────────────────────────────────────────────────
    'services.view':   'View Services',
    'services.create': 'Create Services',
    'services.edit':   'Edit Services',
    'services.delete': 'Delete Services',

    # ── Distribution ─────────────────────────────────────────────────────────
    'distribution.view':       'View Distribution',
    'distribution.generate':   'Generate Distribution',
    'distribution.regenerate': 'Regenerate Distribution',
    'distribution.edit':       'Edit Distribution',
    'distribution.delete':     'Delete Distribution',

    # ── Payments ─────────────────────────────────────────────────────────────
    'payments.view':   'View Payment Center',
    'payments.edit':   'Edit Payments (discount & advance)',
    'payments.export': 'Export Payment Data',

    # ── Download Data ────────────────────────────────────────────────────────
    'download.view':                 'View Download Data section',
    'download.contracts':            'Download Contracts',
    'download.lessors':              'Download Lessors',
    'download.assets':               'Download Assets',
    'download.services':             'Download Services',
    'download.distribution':         'Download Distribution',
    'download.service_distribution': 'Download Service Distribution',
    'download.payments':             'Download Payment Data',

    # ── Bulk Import ──────────────────────────────────────────────────────────
    'bulk_import.view':   'View Bulk Import',
    'bulk_import.import': 'Import via Bulk Import (contracts, lessors, assets, services)',

    # ── Email Notifications ──────────────────────────────────────────────────
    'email.view':      'View Email Notifications',
    'email.configure': 'Configure & Schedule Email Notifications',

    # ── Users ────────────────────────────────────────────────────────────────
    'users.view':   'View Users',
    'users.create': 'Create Users',
    'users.edit':   'Edit Users',
    'users.delete': 'Delete Users',

    # ── Roles & Permissions ──────────────────────────────────────────────────
    'roles.view':   'View Roles & Permissions',
    'roles.create': 'Create Roles',
    'roles.edit':   'Edit Role Permissions',
    'roles.delete': 'Delete Roles',
    'roles.assign': 'Assign Roles to Users',

    # ── Action Logs ──────────────────────────────────────────────────────────
    'logs.view': 'View Action Logs',

    # ── Admin ────────────────────────────────────────────────────────────────
    'admin.all': 'Full Admin Access (bypasses all permission checks)',
}

def has_permission(permission_name):
    """Check if current user has a specific permission"""
    user = get_current_user()
    if not user:
        return False
    
    # Check if user has admin permission
    if check_user_permission(user['id'], 'admin.all'):
        return True
    
    # Check specific permission
    return check_user_permission(user['id'], permission_name)

def check_user_permission(user_id, permission_name):
    """Check if user has permission via their roles"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False
        
        cursor = connection.cursor()
        query = """
            SELECT COUNT(*) as count
            FROM user_roles ur
            INNER JOIN role_permissions rp ON ur.role_id = rp.role_id
            INNER JOIN permissions p ON rp.permission_id = p.id
            WHERE ur.user_id = %s AND p.permission_name = %s
        """
        cursor.execute(query, (user_id, permission_name))
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        return result[0] > 0 if result else False
    except Exception as e:
        print(f"Error checking permission: {e}")
        return False

def require_permission(permission_name):
    """Decorator/function to require permission, show error if not"""
    if not has_permission(permission_name):
        st.error("❌ You do not have permission to access this feature.")
        st.info("Please contact your administrator to request access.")
        st.stop()

def get_user_permissions(user_id):
    """Get all permissions for a user"""
    try:
        connection = get_db_connection()
        if connection is None:
            return []
        
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT DISTINCT p.permission_name, p.description, p.module
            FROM user_roles ur
            INNER JOIN role_permissions rp ON ur.role_id = rp.role_id
            INNER JOIN permissions p ON rp.permission_id = p.id
            WHERE ur.user_id = %s
            ORDER BY p.module, p.permission_name
        """
        cursor.execute(query, (user_id,))
        permissions = cursor.fetchall()
        cursor.close()
        connection.close()
        
        return permissions
    except Exception as e:
        print(f"Error getting user permissions: {e}")
        return []

def get_user_roles(user_id):
    """Get all roles for a user"""
    try:
        connection = get_db_connection()
        if connection is None:
            return []
        
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT r.id, r.role_name, r.description
            FROM user_roles ur
            INNER JOIN roles r ON ur.role_id = r.id
            WHERE ur.user_id = %s
        """
        cursor.execute(query, (user_id,))
        roles = cursor.fetchall()
        cursor.close()
        connection.close()
        
        return roles
    except Exception as e:
        print(f"Error getting user roles: {e}")
        return []

def initialize_permissions():
    """Initialize / sync permissions in the database from the PERMISSIONS dict."""
    try:
        connection = get_db_connection()
        if connection is None:
            return False

        cursor = connection.cursor()

        for perm_id, description in PERMISSIONS.items():
            # Derive module from the key prefix (e.g. "contracts.view" → "contracts")
            module = perm_id.split('.')[0]

            insert_query = """
                INSERT INTO permissions (id, permission_name, description, module)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    description = VALUES(description),
                    module      = VALUES(module)
            """
            cursor.execute(insert_query, (perm_id, perm_id, description, module))

        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Exception as e:
        print(f"Error initializing permissions: {e}")
        return False


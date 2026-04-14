# core/auth.py
# Authentication and session management (Streamlit session_state +8h signed browser cookie for reload persistence)
import os
import bcrypt
import time
from datetime import datetime, timedelta
from typing import Optional

import streamlit as st
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from core.db import *
from core.paths import resolve_static_logo_path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

SESSION_COOKIE_NAME = "contract_tool_session"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60  # 8 hours
SESSION_SERIALIZER_SALT = "contract-tool-auth-v1"
_COOKIE_MANAGER_KEY = "contract_tool_cookie_manager_v1"


def _session_secret() -> str:
    return os.getenv(
        "SESSION_SECRET",
        os.getenv(
            "STREAMLIT_SESSION_SECRET",
            "dev-insecure-session-secret-change-with-SESSION_SECRET-env",
        ),
    )


def _session_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_session_secret(), salt=SESSION_SERIALIZER_SALT)


def _create_session_token(user_id: str) -> str:
    return _session_serializer().dumps({"uid": str(user_id)})


def _verify_session_token(token: str) -> Optional[str]:
    if not token or not isinstance(token, str):
        return None
    try:
        data = _session_serializer().loads(
            token, max_age=SESSION_MAX_AGE_SECONDS
        )
        uid = data.get("uid")
        return str(uid) if uid is not None else None
    except (SignatureExpired, BadSignature, TypeError, ValueError):
        return None


def _get_cookie_manager():
    # CookieManager is a widget; must not be created inside @st.cache_resource.
    import extra_streamlit_components as stx

    return stx.CookieManager(key=_COOKIE_MANAGER_KEY)


def _persist_session_cookie(user_id: str) -> None:
    try:
        cm = _get_cookie_manager()
        token = _create_session_token(user_id)
        expires = datetime.now() + timedelta(seconds=SESSION_MAX_AGE_SECONDS)
        cm.set(
            SESSION_COOKIE_NAME,
            token,
            key=f"set_{SESSION_COOKIE_NAME}",
            path="/",
            expires_at=expires,
            secure=False,
            same_site="lax",
        )
    except Exception as e:
        print(f"Could not set session cookie: {e}")


def _clear_session_cookie() -> None:
    try:
        cm = _get_cookie_manager()
        cm.delete(SESSION_COOKIE_NAME, key=f"del_{SESSION_COOKIE_NAME}")
    except Exception as e:
        print(f"Could not clear session cookie: {e}")


def _read_session_cookie_value() -> Optional[str]:
    try:
        cm = _get_cookie_manager()
        val = cm.get(SESSION_COOKIE_NAME)
        if val:
            return val
        time.sleep(0.12)
        val = cm.get(SESSION_COOKIE_NAME)
        if val:
            return val
        allc = cm.get_all()
        if isinstance(allc, dict):
            return allc.get(SESSION_COOKIE_NAME)
        return None
    except Exception as e:
        print(f"Could not read session cookie: {e}")
        return None


def _apply_user_session(user: dict) -> None:
    st.session_state["authenticated"] = True
    st.session_state["user_id"] = user["id"]
    st.session_state["user_name"] = user["name"]
    st.session_state["user_email"] = user["email"]


def try_restore_session_from_cookie() -> bool:
    """If Streamlit session was reset (e.g. F5), restore from signed cookie."""
    if st.session_state.get("authenticated"):
        return True
    token = _read_session_cookie_value()
    if not token:
        return False
    user_id = _verify_session_token(token)
    if not user_id:
        _clear_session_cookie()
        return False
    user = get_user_by_id(user_id)
    if not user:
        _clear_session_cookie()
        return False
    try:
        active = int(user.get("is_active", 0) or 0)
    except (TypeError, ValueError):
        active = 0
    if not active:
        _clear_session_cookie()
        return False
    _apply_user_session(user)
    return True


def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, password_hash):
    """Verify a password against a hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except:
        return False

def login_user(email, password):
    """Authenticate user and create session"""
    try:
        connection = get_db_connection()
        if connection is None:
            return False, "Database connection error"
        
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM users WHERE email = %s AND is_active = 1"
        cursor.execute(query, (email,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if not user:
            return False, "Invalid email or password"
        
        if not verify_password(password, user['password_hash']):
            return False, "Invalid email or password"
        
        # Update last login
        update_query = "UPDATE users SET last_login = %s WHERE id = %s"
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute(update_query, (datetime.now(), user['id']))
            connection.commit()
            cursor.close()
            connection.close()
        
        _apply_user_session(user)
        _persist_session_cookie(str(user['id']))
        
        # Log login action
        log_action(
            user_id=user['id'],
            user_name=user['name'],
            action_type='login',
            entity_type='user',
            entity_id=user['id'],
            entity_name=user['name'],
            action_details=f"User logged in: {email}",
            ip_address=get_user_ip()
        )
        
        return True, "Login successful"
    except Exception as e:
        return False, f"Login error: {str(e)}"

def logout_user():
    """Logout user and clear session"""
    if 'user_id' in st.session_state:
        # Log logout action
        log_action(
            user_id=st.session_state.get('user_id'),
            user_name=st.session_state.get('user_name', ''),
            action_type='logout',
            entity_type='user',
            entity_id=st.session_state.get('user_id', ''),
            entity_name=st.session_state.get('user_name', ''),
            action_details="User logged out",
            ip_address=get_user_ip()
        )
    
    for key in ['authenticated', 'user_id', 'user_name', 'user_email']:
        if key in st.session_state:
            del st.session_state[key]

    _clear_session_cookie()
    st.rerun()

def require_login():
    """Require login: use session_state or restore from8h signed cookie after reload."""
    try:
        _get_cookie_manager()
    except Exception as e:
        st.error(
            f"Session cookie support failed to load ({e}). "
            "Install dependencies: pip install extra-streamlit-components itsdangerous"
        )
        st.stop()

    if st.session_state.get("authenticated"):
        return

    if try_restore_session_from_cookie():
        return

    render_login_page()
    st.stop()

def render_login_page():
    """Render optimized login page"""
    # Custom CSS for login page
    st.markdown("""
    <style>
    .main {
        padding-top: 2rem;
    }
    .login-title {
        text-align: center;
        color: #2c3e50;
        font-size: 2.5em;
        margin-bottom: 10px;
        font-weight: bold;
    }
    .login-subtitle {
        text-align: center;
        color: #7f8c8d;
        font-size: 1.1em;
        margin-bottom: 30px;
    }
    .stTextInput > div > div > input {
        background-color: rgba(255,255,255,0.95);
        border-radius: 10px;
        padding: 12px;
        border: 2px solid rgba(0,0,0,0.1);
    }
    .stTextInput > div > div > input:focus {
        border-color: #3498db;
        box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.2);
    }
    .stButton > button {
        width: 100%;
        background: #3498db;
        color: white;
        font-weight: bold;
        padding: 12px;
        border-radius: 10px;
        border: none;
        font-size: 1.1em;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        background: #2980b9;
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Centered login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        logo_path = resolve_static_logo_path()
        if logo_path:
            st.image(logo_path, width=200)

        st.markdown("""
        <h2 class="login-title">Contract Management</h2>
        <p class="login-subtitle">Sign in to your account</p>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email address", key="login_email", placeholder="Enter your email")
            password = st.text_input("Password", type="password", key="login_password", placeholder="Enter your password")
            submit = st.form_submit_button("Login", type="primary", use_container_width=True)

            if submit:
                if not email or not password:
                    st.error("Please enter both email and password")
                else:
                    success, message = login_user(email, password)
                    if success:
                        st.success(message)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(message)

def get_current_user():
    """Get current logged-in user info"""
    if st.session_state.get('authenticated'):
        return {
            'id': st.session_state.get('user_id'),
            'name': st.session_state.get('user_name'),
            'email': st.session_state.get('user_email')
        }
    return None

def get_user_ip():
    """Get user's IP address (for logging)"""
    try:
        # Streamlit doesn't provide direct access to request headers
        # This is a placeholder - in production, you might need to use a different approach
        # For now, return a placeholder
        return "127.0.0.1"
    except:
        return "Unknown"

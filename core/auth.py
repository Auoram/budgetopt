"""
core/auth.py
────────────
Simple authentication system for BudgetOpt.

Users are stored in feedback.db (users table).
Passwords are hashed with SHA-256 + a random salt.

Usage — add these two lines at the top of EVERY page file,
before any other st.* call:

    from core.auth import require_login
    require_login()

This shows the login form and blocks the page if not authenticated.
The sidebar is hidden until login succeeds.
"""

import sqlite3
import hashlib
import os
import streamlit as st
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "feedback.db"


# ─────────────────────────────────────────
# DB SETUP
# ─────────────────────────────────────────

def init_auth_tables():
    """
    Creates the users table if it doesn't exist.
    Seeds two default accounts on first run:
        admin    / admin123
        employee / employee123
    Change these after first login.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            display_name  TEXT    NOT NULL,
            password_hash TEXT    NOT NULL,
            salt          TEXT    NOT NULL,
            role          TEXT    DEFAULT 'employee',
            created_at    TEXT,
            last_login    TEXT
        )
    """)
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        _create_user(conn, "admin",    "Admin",    "admin123",    role="admin")
        _create_user(conn, "employee", "Employee", "employee123", role="employee")

    conn.close()


# ─────────────────────────────────────────
# PASSWORD HELPERS
# ─────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()

def _make_salt() -> str:
    return os.urandom(16).hex()


# ─────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────

def _create_user(conn, username, display_name, password, role="employee"):
    salt          = _make_salt()
    password_hash = _hash_password(password, salt)
    conn.execute("""
        INSERT OR IGNORE INTO users
          (username, display_name, password_hash, salt, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        username.strip().lower(),
        display_name.strip(),
        password_hash,
        salt,
        role,
        datetime.now().isoformat(),
    ))
    conn.commit()


def create_user(
    username:     str,
    display_name: str,
    password:     str,
    role:         str = "employee",
) -> bool:
    """Creates a new user. Returns True on success, False if username taken."""
    conn = sqlite3.connect(DB_PATH)
    try:
        _create_user(conn, username, display_name, password, role)
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success


def verify_user(username: str, password: str) -> dict | None:
    """Returns user dict on success, None on failure."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        (username.strip().lower(),)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    if _hash_password(password, row["salt"]) != row["password_hash"]:
        return None
    return dict(row)


def update_last_login(username: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE users SET last_login = ? WHERE username = ?",
        (datetime.now().isoformat(), username.strip().lower())
    )
    conn.commit()
    conn.close()


def change_password(username: str, new_password: str):
    """Updates a user's password."""
    salt          = _make_salt()
    password_hash = _hash_password(new_password, salt)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
        (password_hash, salt, username.strip().lower())
    )
    conn.commit()
    conn.close()


def get_all_users() -> list[dict]:
    """Returns all users without password fields."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, username, display_name, role, created_at, last_login
        FROM users ORDER BY id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(username: str) -> bool:
    """Deletes a user (cannot delete admins). Returns True if deleted."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute(
        "DELETE FROM users WHERE username = ? AND role != 'admin'",
        (username.strip().lower(),)
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ─────────────────────────────────────────
# SESSION HELPERS
# ─────────────────────────────────────────

def is_logged_in() -> bool:
    return st.session_state.get("auth_logged_in", False)

def current_user() -> dict | None:
    return st.session_state.get("auth_user", None)

def current_username() -> str:
    user = current_user()
    return user["display_name"] if user else "Guest"

def is_admin() -> bool:
    user = current_user()
    return user["role"] == "admin" if user else False

def _do_login(user: dict):
    st.session_state["auth_logged_in"] = True
    st.session_state["auth_user"]      = user
    update_last_login(user["username"])

def logout():
    for key in ["auth_logged_in", "auth_user"]:
        st.session_state.pop(key, None)
    st.rerun()


# ─────────────────────────────────────────
# CSS — hide sidebar on login screen
# ─────────────────────────────────────────

def _hide_sidebar():
    """
    Injects CSS that completely hides the sidebar
    and its toggle — used only on the login screen
    so users can't navigate to other pages before logging in.
    """
    st.markdown("""
    <style>
        [data-testid="stSidebar"]         { display: none !important; }
        [data-testid="collapsedControl"]  { display: none !important; }
        [data-testid="stSidebarNavItems"] { display: none !important; }
        .main .block-container {
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────
# LOGIN UI
# ─────────────────────────────────────────

def _show_login_page():
    """
    Renders the full-screen centered login form.
    Sidebar is completely hidden.
    """
    _hide_sidebar()

    st.markdown("<br><br><br>", unsafe_allow_html=True)

    _, center, _ = st.columns([1, 1.2, 1])

    with center:

        # Logo + app name
        st.markdown("""
        <div style='text-align:center; margin-bottom:2rem;'>
            <div style='font-size:3.5rem;'>📊</div>
            <div style='font-size:2rem; font-weight:700; color:#111;
                        margin-top:0.3rem;'>BudgetOpt</div>
            <div style='font-size:0.95rem; color:#6b7280; margin-top:0.4rem;'>
                AI-powered marketing budget allocation
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Login card
        with st.container(border=True):
            st.markdown(
                "<p style='font-weight:600; font-size:1.05rem;"
                " margin-bottom:0.5rem;'>Sign in to your account</p>",
                unsafe_allow_html=True,
            )

            with st.form("login_form", clear_on_submit=False):
                username = st.text_input(
                    "Username",
                    placeholder  = "Enter your username",
                    autocomplete = "username",
                )
                password = st.text_input(
                    "Password",
                    type         = "password",
                    placeholder  = "Enter your password",
                    autocomplete = "current-password",
                )
                submitted = st.form_submit_button(
                    "Sign in →",
                    type                = "primary",
                    use_container_width = True,
                )

            if submitted:
                if not username.strip() or not password.strip():
                    st.error("Please enter both username and password.")
                else:
                    user = verify_user(username.strip(), password.strip())
                    if user:
                        _do_login(user)
                        st.rerun()
                    else:
                        st.error("Incorrect username or password.")

        st.markdown(
            "<p style='text-align:center; color:#9ca3af; font-size:0.8rem;"
            " margin-top:1rem;'>"
            "Contact your administrator if you need access.</p>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────
# MAIN GUARD — call at top of every page
# ─────────────────────────────────────────

def require_login():
    """
    Call this at the very top of every page file,
    immediately after imports, before any other st.* call.

    - Not logged in → shows login form, hides sidebar, stops page.
    - Logged in     → returns normally, page renders as usual.
    """
    init_auth_tables()

    if not is_logged_in():
        st.set_page_config(
            page_title            = "BudgetOpt — Sign in",
            page_icon             = "📊",
            layout                = "centered",
            initial_sidebar_state = "collapsed",
        )
        _show_login_page()
        st.stop()
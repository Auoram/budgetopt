"""
core/auth_ui.py
───────────────
Reusable sidebar component showing the logged-in user
and a logout button. Call show_user_sidebar() inside
every page's `with st.sidebar:` block.
"""

import base64
import streamlit as st
from pathlib import Path
from core.auth import current_username, current_user, is_admin, logout, COMPANY_NAME

LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo.png"


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _logo_base64() -> str | None:
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return None


def _avatar_color(name: str) -> str:
    """Picks one of 8 consistent colors based on the first letter."""
    colors = [
        "#6366f1",  # indigo
        "#0ea5e9",  # sky
        "#10b981",  # emerald
        "#f59e0b",  # amber
        "#ef4444",  # red
        "#8b5cf6",  # violet
        "#ec4899",  # pink
        "#14b8a6",  # teal
    ]
    return colors[ord(name[0].upper()) % len(colors)] if name else colors[0]


# ─────────────────────────────────────────
# SIDEBAR COMPONENT
# ─────────────────────────────────────────

def show_user_sidebar():
    """
    Renders in the sidebar:
      - Company logo (if assets/logo.png exists) or company name text
      - Letter-circle avatar + username + role badge
      - Sign out button
    Call this inside `with st.sidebar:` at the top of every page.
    """

    # ── Company logo / name ───────────────────────────────
    logo_b64 = _logo_base64()
    if logo_b64:
        st.sidebar.markdown(
            f"<div style='text-align:center; padding: 0.6rem 0 0.4rem;'>"
            f"<img src='data:image/png;base64,{logo_b64}' "
            f"style='max-height:52px; max-width:160px; object-fit:contain;'>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        # Fallback: styled company name text
        st.sidebar.markdown(
            f"<div style='text-align:center; padding:0.6rem 0 0.2rem;'>"
            f"<span style='font-size:1.1rem; font-weight:800; "
            f"letter-spacing:-0.3px; color:var(--text-color);'>"
            f"{COMPANY_NAME}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.sidebar.divider()

    # ── User avatar + info ────────────────────────────────
    name   = current_username()
    user   = current_user()
    letter = name[0].upper() if name else "?"
    color  = _avatar_color(name)
    role   = user["role"].title() if user else ""

    st.sidebar.markdown(
        f"""
        <div style='display:flex; align-items:center; gap:0.7rem;
                    padding:0.4rem 0 0.6rem;'>
            <!-- Letter circle avatar -->
            <div style='
                width:38px; height:38px; border-radius:50%;
                background:{color};
                display:flex; align-items:center; justify-content:center;
                font-size:1.1rem; font-weight:700; color:#fff;
                flex-shrink:0;
            '>{letter}</div>
            <!-- Name + role -->
            <div style='line-height:1.3;'>
                <div style='font-weight:600; font-size:0.95rem;
                            color:var(--text-color);'>{name}</div>
                <div style='font-size:0.75rem; color:#9ca3af;'>{role}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sign out button ───────────────────────────────────
    if st.sidebar.button("🚪 Sign out", use_container_width=True, key="signout_btn"):
        logout()
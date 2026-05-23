"""
core/auth_ui.py
───────────────
Reusable sidebar component showing the logged-in user
and a logout button. Call show_user_sidebar() inside
every page's `with st.sidebar:` block.
"""

import streamlit as st
from core.auth import current_username, current_user, is_admin, logout, COMPANY_NAME


def _avatar_color(name: str) -> str:
    colors = [
        "#6366f1", "#0ea5e9", "#10b981", "#f59e0b",
        "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6",
    ]
    return colors[ord(name[0].upper()) % len(colors)] if name else colors[0]


def show_user_sidebar():
    """
    Renders in the sidebar:
      - Company name in large bold style (above page nav links)
      - Letter-circle avatar + username + role
      - Sign out button
    Call inside `with st.sidebar:` at the top of every page.
    """

    # ── Company name — first thing in sidebar ─────────────
    st.sidebar.markdown(
        f"""
        <div style="padding:1rem 0.8rem 0.4rem;">
            <div style="
                font-size:1.35rem;
                font-weight:800;
                letter-spacing:-0.4px;
                color:var(--text-color);
                line-height:1.2;
            ">{COMPANY_NAME}</div>
        </div>
        """,
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
        <div style="display:flex; align-items:center; gap:0.65rem;
                    padding:0.7rem 0;">
            <div style="
                width:36px; height:36px; border-radius:50%;
                background:{color};
                display:flex; align-items:center; justify-content:center;
                font-size:1rem; font-weight:700; color:#fff;
                flex-shrink:0;
            ">{letter}</div>
            <div style="line-height:1.3;">
                <div style="font-weight:600; font-size:0.9rem;
                            color:var(--text-color);">{name}</div>
                <div style="font-size:0.73rem; opacity:0.48;">{role}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Sign out", use_container_width=True, key="signout_btn"):
        logout()
"""
core/auth_ui.py
───────────────
Reusable sidebar component showing the logged-in user
and a logout button. Call show_user_sidebar() inside
every page's `with st.sidebar:` block.
"""

import streamlit as st
from core.auth import current_username, is_admin, logout


def show_user_sidebar():
    """
    Renders user info + logout button in the sidebar.
    Call this inside `with st.sidebar:` at the top of every page.
    """
    user_label = f"👤 {current_username()}"
    if is_admin():
        user_label += " · Admin"

    st.sidebar.markdown(f"**{user_label}**")
    st.sidebar.divider()

    if st.sidebar.button("🚪 Sign out", use_container_width=True, key="signout_btn"):
        logout()
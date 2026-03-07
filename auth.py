"""
Authentication UI and session management.
Provides login/register UI, session gate, and test-user seeding.

Import DAG (no circular imports): auth → sync → database
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from data import database as db


def seed_test_user() -> None:
    """Ensure the 'test' demo account exists (no data seeded — user loads demo data manually)."""
    existing = db.get_user("test")
    if not existing:
        db.create_user(
            username="test",
            plain_password="test",
            email="ahmed.bawla@gmail.com",
            restaurant_name="The Brass Fork (Demo)",
            use_simulated_data=False,
        )
    else:
        # Always clear the test account's data on startup.
        # It's a shared demo account — demo data is reloaded on demand.
        db.clear_user_data("test")


def require_auth() -> dict:
    """Return the current user dict, or show auth UI and stop."""
    if "user" not in st.session_state:
        _show_auth_ui()
        st.stop()
    return st.session_state["user"]


def render_sidebar_logout() -> None:
    """Display restaurant name, username, and logout button in the sidebar."""
    with st.sidebar:
        user = st.session_state.get("user", {})
        st.write(f"**{user.get('restaurant_name', '')}**")
        st.caption(f"Logged in as `{user.get('username', '')}`")
        if st.button("Logout", use_container_width=True):
            del st.session_state["user"]
            st.rerun()


def _show_auth_ui() -> None:
    # Completely hide the sidebar before login
    st.markdown("""
    <style>
    [data-testid="stSidebar"]        { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

    st.title("🍽️ Restaurant BI Dashboard")
    st.caption("Demo: username `test` / password `test`")

    login_tab, register_tab = st.tabs(["Login", "Create Account"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("Please enter your username and password.")
            else:
                user = db.authenticate_user(username, password)
                if user:
                    st.session_state["user"] = dict(user)
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    with register_tab:
        with st.form("register_form"):
            new_username = st.text_input("Username")
            new_password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            restaurant_name = st.text_input("Restaurant Name")
            email = st.text_input("Email Address", help="Used to send PDF reports")

            with st.expander("Toast POS API Keys (optional)"):
                toast_api_key = st.text_input("Toast API Key")
                toast_guid = st.text_input("Restaurant GUID")

            with st.expander("Paychex API Keys (optional)"):
                paychex_client_id = st.text_input("Client ID")
                paychex_client_secret = st.text_input("Client Secret", type="password")
                paychex_company_id = st.text_input("Company ID")

            with st.expander("QuickBooks API Keys (optional)"):
                qb_client_id = st.text_input("QB Client ID")
                qb_client_secret = st.text_input("QB Client Secret", type="password")
                qb_realm_id = st.text_input("Realm ID")
                qb_refresh_token = st.text_input("Refresh Token", type="password")

            register_submitted = st.form_submit_button(
                "Create Account", use_container_width=True
            )

        if register_submitted:
            if not new_username or not new_password or not restaurant_name:
                st.error("Username, password, and restaurant name are required.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            else:
                has_toast = bool(toast_api_key and toast_guid)
                has_paychex = bool(
                    paychex_client_id and paychex_client_secret and paychex_company_id
                )
                has_qb = bool(
                    qb_client_id and qb_client_secret and qb_realm_id and qb_refresh_token
                )
                use_sim = not (has_toast or has_paychex or has_qb)

                try:
                    db.create_user(
                        username=new_username,
                        plain_password=new_password,
                        email=email or None,
                        restaurant_name=restaurant_name,
                        use_simulated_data=use_sim,
                        toast_api_key=toast_api_key or None,
                        toast_guid=toast_guid or None,
                        paychex_client_id=paychex_client_id or None,
                        paychex_client_secret=paychex_client_secret or None,
                        paychex_company_id=paychex_company_id or None,
                        qb_client_id=qb_client_id or None,
                        qb_client_secret=qb_client_secret or None,
                        qb_realm_id=qb_realm_id or None,
                        qb_refresh_token=qb_refresh_token or None,
                    )
                    new_user = db.get_user(new_username)
                    st.session_state["user"] = dict(new_user)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

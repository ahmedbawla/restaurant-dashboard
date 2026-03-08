"""
Authentication UI and session management for TableMetrics.

Flow:
  Landing page → "Log In"         → username + password → logged in
  Landing page → "Create Account" → fill form → auto-logged in

SMS 2FA and remember-me cookies are not yet enabled.

Import DAG (no circular imports): auth → database
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from data import database as db


_HIDE_SIDEBAR = """
<style>
[data-testid="stSidebar"]        { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
</style>
"""

_BRAND_CSS = """
<style>
.tm-title {
    font-size: 3rem; font-weight: 800; letter-spacing: -1px;
    background: linear-gradient(135deg, #FF4B4B 0%, #FF8C42 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; text-align: center; margin-bottom: 0.1rem;
}
.tm-sub {
    text-align: center; color: rgba(255,255,255,0.45);
    font-size: 1.05rem; margin-bottom: 2.5rem;
}
.tm-step-title {
    font-size: 1.5rem; font-weight: 700; margin-bottom: 1rem;
}
</style>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def seed_test_user() -> None:
    """Ensure the 'test' demo account exists."""
    if not db.get_user("test"):
        db.create_user(
            username="test",
            plain_password="test",
            email="ahmed.bawla@gmail.com",
            phone_number=None,
            restaurant_name="The Daily Grind (Demo)",
            use_simulated_data=False,
        )
    else:
        db.update_user("test", restaurant_name="The Daily Grind (Demo)")


def require_auth() -> dict:
    """Return the current user dict, or show auth UI and st.stop()."""
    if "user" in st.session_state:
        return st.session_state["user"]

    st.markdown(_HIDE_SIDEBAR, unsafe_allow_html=True)
    st.markdown(_BRAND_CSS,    unsafe_allow_html=True)

    screen = st.session_state.get("_auth_screen", "landing")

    if screen == "landing":
        _landing()
    elif screen == "login":
        _login()
    elif screen == "register":
        _register()

    st.stop()


def render_sidebar_logout() -> None:
    """Display restaurant name, username, and logout button in the sidebar."""
    with st.sidebar:
        user = st.session_state.get("user", {})
        st.write(f"**{user.get('restaurant_name', '')}**")
        st.caption(f"Logged in as `{user.get('username', '')}`")
        if st.button("Logout", use_container_width=True):
            for k in ["user", "_auth_screen"]:
                st.session_state.pop(k, None)
            st.rerun()


# ---------------------------------------------------------------------------
# Screen renderers
# ---------------------------------------------------------------------------

def _center():
    """Return the center column of a [1, 1.4, 1] layout."""
    _, col, _ = st.columns([1, 1.4, 1])
    return col


def _landing():
    st.markdown("<div style='height:12vh'></div>", unsafe_allow_html=True)
    with _center():
        st.markdown('<p class="tm-title">TableMetrics</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="tm-sub">Restaurant intelligence, simplified.</p>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Log In", use_container_width=True, type="primary"):
                st.session_state["_auth_screen"] = "login"
                st.rerun()
        with c2:
            if st.button("Create Account", use_container_width=True):
                st.session_state["_auth_screen"] = "register"
                st.rerun()


def _login():
    with _center():
        st.markdown('<p class="tm-title" style="font-size:2rem">TableMetrics</p>',
                    unsafe_allow_html=True)
        st.markdown('<p class="tm-step-title">Log In</p>', unsafe_allow_html=True)

        with st.form("login_form"):
            username  = st.text_input("Username")
            password  = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In", use_container_width=True)

        if st.button("← Back", key="login_back"):
            st.session_state["_auth_screen"] = "landing"
            st.rerun()

    if not submitted:
        return

    if not username or not password:
        st.error("Please enter your username and password.")
        return

    user = db.authenticate_user(username, password)
    if not user:
        st.error("Invalid username or password.")
        return

    st.session_state.pop("_auth_screen", None)
    st.session_state["user"] = dict(user)
    st.rerun()


def _register():
    with _center():
        st.markdown('<p class="tm-title" style="font-size:2rem">TableMetrics</p>',
                    unsafe_allow_html=True)
        st.markdown('<p class="tm-step-title">Create Account</p>', unsafe_allow_html=True)

        with st.form("register_form"):
            restaurant = st.text_input("Restaurant Name")
            username   = st.text_input("Username")
            email      = st.text_input("Email Address")
            phone      = st.text_input(
                "Phone Number",
                help="Include country code, e.g. +12125551234.",
            )
            password   = st.text_input("Password", type="password")
            confirm    = st.text_input("Confirm Password", type="password")
            submitted  = st.form_submit_button("Create Account", use_container_width=True)

        if st.button("← Back", key="register_back"):
            st.session_state["_auth_screen"] = "landing"
            st.rerun()

    if not submitted:
        return

    if not restaurant.strip() or not username.strip() or not password:
        st.error("Restaurant name, username, and password are required.")
        return
    if password != confirm:
        st.error("Passwords do not match.")
        return
    if len(password) < 6:
        st.error("Password must be at least 6 characters.")
        return

    try:
        db.create_user(
            username        = username.strip(),
            plain_password  = password,
            restaurant_name = restaurant.strip(),
            email           = email.strip() or None,
            phone_number    = phone.strip() or None,
            use_simulated_data = False,
        )
        new_user = db.get_user(username.strip())
        st.session_state.pop("_auth_screen", None)
        st.session_state["user"] = dict(new_user)
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))

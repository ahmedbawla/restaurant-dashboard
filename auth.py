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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

/* ── Global page background ── */
[data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse 80% 60% at 50% -10%, rgba(255,100,60,0.18) 0%, transparent 70%),
                radial-gradient(ellipse 60% 50% at 80% 80%, rgba(255,75,75,0.10) 0%, transparent 60%),
                #0e0e10 !important;
    font-family: 'Inter', sans-serif;
}
[data-testid="stMain"] { background: transparent !important; }
[data-testid="stHeader"] { background: transparent !important; }
.main .block-container { padding-top: 0 !important; max-width: 100% !important; }

/* ── Logo ── */
.tm-logo {
    font-size: 5rem; font-weight: 900; letter-spacing: -3px; line-height: 1;
    background: linear-gradient(135deg, #FF6B35 0%, #FF4B4B 45%, #FF8C42 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; text-align: center;
    margin-bottom: 0.5rem;
    filter: drop-shadow(0 0 60px rgba(255,75,75,0.5));
}
.tm-tagline {
    text-align: center; color: rgba(255,255,255,0.5);
    font-size: 1.1rem; font-weight: 400; letter-spacing: 0.01em;
    margin-bottom: 0.1rem;
}
.tm-eyebrow {
    text-align: center;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 3px;
    text-transform: uppercase;
    color: rgba(255,107,53,0.75);
    margin-bottom: 0.9rem;
}

/* ── Feature chips ── */
.tm-chips {
    display: flex; flex-wrap: wrap; justify-content: center;
    gap: 0.5rem; margin: 1.6rem 0 1.8rem 0;
}
.tm-chip {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 999px;
    padding: 0.3rem 0.85rem;
    font-size: 0.78rem; font-weight: 500;
    color: rgba(255,255,255,0.65);
    white-space: nowrap;
}
.tm-chip span { margin-right: 0.3rem; }

/* ── Integration badges ── */
.tm-integrations {
    text-align: center; margin-bottom: 0.5rem;
}
.tm-int-label {
    font-size: 0.68rem; font-weight: 600; letter-spacing: 2px;
    text-transform: uppercase; color: rgba(255,255,255,0.28);
    margin-bottom: 0.55rem;
}
.tm-badges {
    display: flex; flex-wrap: wrap; justify-content: center; gap: 0.5rem;
}
.tm-badge {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 6px;
    padding: 0.25rem 0.7rem;
    font-size: 0.73rem; font-weight: 500;
    color: rgba(255,255,255,0.4);
}

/* ── Divider ── */
.tm-divider {
    width: 48px; height: 2px; margin: 2rem auto 0 auto;
    background: linear-gradient(90deg, transparent, rgba(255,107,53,0.5), transparent);
    border-radius: 999px;
}

/* ── Form card ── */
.tm-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 16px;
    padding: 2rem 2rem 1.6rem 2rem;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    margin-bottom: 1rem;
}
.tm-form-logo {
    font-size: 1.6rem; font-weight: 900; letter-spacing: -0.5px;
    background: linear-gradient(135deg, #FF6B35 0%, #FF4B4B 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; text-align: center;
    margin-bottom: 0.2rem;
}
.tm-form-title {
    font-size: 1.4rem; font-weight: 700;
    color: rgba(255,255,255,0.9); margin-bottom: 1.2rem;
    letter-spacing: -0.3px;
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
    st.markdown("<div style='height:9vh'></div>", unsafe_allow_html=True)
    with _center():
        st.markdown('<div class="tm-eyebrow">Restaurant Intelligence Platform</div>', unsafe_allow_html=True)
        st.markdown('<p class="tm-logo">TableMetrics</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="tm-tagline">Your numbers, at a glance. Every shift, every day.</p>',
            unsafe_allow_html=True,
        )
        st.markdown("""
        <div class="tm-chips">
            <div class="tm-chip"><span>📈</span>Revenue Trends</div>
            <div class="tm-chip"><span>🧑‍🍳</span>Labour Costs</div>
            <div class="tm-chip"><span>🧾</span>Expense Tracking</div>
            <div class="tm-chip"><span>⚡</span>Live Sync</div>
            <div class="tm-chip"><span>📊</span>Health Score</div>
        </div>
        <div class="tm-integrations">
            <div class="tm-int-label">Integrates with</div>
            <div class="tm-badges">
                <div class="tm-badge">Toast POS</div>
                <div class="tm-badge">Paychex</div>
                <div class="tm-badge">QuickBooks</div>
            </div>
        </div>
        <div class="tm-divider"></div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)
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
    st.markdown("<div style='height:9vh'></div>", unsafe_allow_html=True)
    with _center():
        st.markdown('<div class="tm-card">', unsafe_allow_html=True)
        st.markdown('<p class="tm-form-logo">TableMetrics</p>', unsafe_allow_html=True)
        st.markdown('<p class="tm-form-title">Welcome back</p>', unsafe_allow_html=True)

        with st.form("login_form"):
            username  = st.text_input("Username")
            password  = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In →", use_container_width=True)

        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("← Back to home", key="login_back", use_container_width=True):
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
    st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
    with _center():
        st.markdown('<div class="tm-card">', unsafe_allow_html=True)
        st.markdown('<p class="tm-form-logo">TableMetrics</p>', unsafe_allow_html=True)
        st.markdown('<p class="tm-form-title">Create your account</p>', unsafe_allow_html=True)

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
            submitted  = st.form_submit_button("Create Account →", use_container_width=True)

        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("← Back to home", key="register_back", use_container_width=True):
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

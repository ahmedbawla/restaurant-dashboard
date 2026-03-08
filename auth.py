"""
Authentication UI and session management for TableMetrics.

Flow:
  Landing page → "Log In"        → username + password → SMS code → logged in
  Landing page → "Create Account" → fill form → auto-logged in (no SMS)

  Remember me: after SMS verification with the checkbox ticked, a 30-day
  browser cookie is set. On the next visit the user is auto-logged in without
  re-entering their password or code.

Import DAG (no circular imports): auth → database
"""

import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from data import database as db
from utils.sms import send_verification_code

_COOKIE_USER  = "tm_remember_user"
_COOKIE_TOKEN = "tm_remember_token"
_REMEMBER_DAYS = 30

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

    # CookieManager must be instantiated before any columns so cookies load
    # reliably on the first render pass.
    cm = _get_cm()

    # Auto-login via valid remember-me cookie
    if cm is not None:
        _rem_user  = cm.get(_COOKIE_USER)
        _rem_token = cm.get(_COOKIE_TOKEN)
        if _rem_user and _rem_token and db.verify_remember_token(_rem_user, _rem_token):
            user = db.get_user(_rem_user)
            if user:
                st.session_state["user"] = dict(user)
                st.rerun()

    screen = st.session_state.get("_auth_screen", "landing")

    if screen == "landing":
        _landing()
    elif screen == "login":
        _login()
    elif screen == "verify":
        _verify(cm)
    elif screen == "register":
        _register()

    st.stop()


def render_sidebar_logout() -> None:
    """Display restaurant name, username, and logout button in the sidebar."""
    cm = _get_cm()
    with st.sidebar:
        user = st.session_state.get("user", {})
        st.write(f"**{user.get('restaurant_name', '')}**")
        st.caption(f"Logged in as `{user.get('username', '')}`")
        if st.button("Logout", use_container_width=True):
            uname = user.get("username")
            if uname:
                db.update_user(uname, remember_token=None, remember_token_expires=None)
            if cm is not None:
                try:
                    cm.delete(_COOKIE_USER)
                    cm.delete(_COOKIE_TOKEN)
                except Exception:
                    pass
            for k in ["user", "_auth_screen", "_auth_pending"]:
                st.session_state.pop(k, None)
            st.rerun()


# ---------------------------------------------------------------------------
# Cookie helper
# ---------------------------------------------------------------------------

def _get_cm():
    """Return a CookieManager instance, or None if the package is unavailable."""
    try:
        import extra_streamlit_components as stx
        return stx.CookieManager(key="tm_auth")
    except Exception:
        return None


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
            remember  = st.checkbox("Remember me for 30 days")
            submitted = st.form_submit_button("Continue →", use_container_width=True)

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

    # Generate code and attempt SMS delivery
    code = _new_code()
    sent = send_verification_code(user.get("phone_number"), code)

    st.session_state["_auth_pending"] = {
        "username": username,
        "remember": remember,
        "code":     code,
        "dev_mode": not sent,   # True = show code on screen (Twilio not configured)
    }
    st.session_state["_auth_screen"] = "verify"
    st.rerun()


def _verify(cm):
    pending = st.session_state.get("_auth_pending")
    if not pending:
        st.session_state["_auth_screen"] = "login"
        st.rerun()
        return

    with _center():
        st.markdown('<p class="tm-title" style="font-size:2rem">TableMetrics</p>',
                    unsafe_allow_html=True)
        st.markdown('<p class="tm-step-title">Verify Your Identity</p>',
                    unsafe_allow_html=True)

        if pending["dev_mode"]:
            st.warning(
                f"**Dev mode** — SMS not configured or no phone on file.  \n"
                f"Your code is: **{pending['code']}**"
            )
        else:
            user = db.get_user(pending["username"])
            phone = user.get("phone_number", "") if user else ""
            masked = f"···-···-{phone[-4:]}" if len(phone or "") >= 4 else "your phone"
            st.info(f"A 6-digit code was sent to **{masked}**.")

        with st.form("verify_form"):
            entered  = st.text_input("Verification Code", max_chars=6)
            verified = st.form_submit_button("Verify →", use_container_width=True)

        col_back, col_resend = st.columns(2)
        with col_back:
            if st.button("← Back", key="verify_back"):
                st.session_state.pop("_auth_pending", None)
                st.session_state["_auth_screen"] = "login"
                st.rerun()
        with col_resend:
            if st.button("Resend Code", key="resend"):
                new_code = _new_code()
                user     = db.get_user(pending["username"])
                sent     = send_verification_code(user.get("phone_number"), new_code)
                pending["code"]     = new_code
                pending["dev_mode"] = not sent
                st.session_state["_auth_pending"] = pending
                st.success("New code sent." if sent else "Code refreshed (dev mode).")
                st.rerun()

    if not verified:
        return

    if entered.strip() != str(pending["code"]):
        st.error("Incorrect code. Please try again.")
        return

    username = pending["username"]
    user     = db.get_user(username)

    if pending["remember"] and cm is not None:
        token   = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=_REMEMBER_DAYS)
        db.update_user(username, remember_token=token, remember_token_expires=expires)
        try:
            cm.set(_COOKIE_USER,  username, expires_at=expires)
            cm.set(_COOKIE_TOKEN, token,    expires_at=expires)
        except Exception:
            pass

    st.session_state.pop("_auth_pending", None)
    st.session_state.pop("_auth_screen",  None)
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
                help="Include country code, e.g. +12125551234. Used for login verification codes.",
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


def _new_code() -> str:
    """Return a random 6-digit verification code."""
    return str(secrets.randbelow(900_000) + 100_000)

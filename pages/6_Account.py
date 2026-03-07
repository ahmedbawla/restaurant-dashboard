"""
Account Settings — manage email, restaurant name, password, and integrations.
"""

import streamlit as st

from components.theme import page_header
from data import database as db
from utils.oauth_quickbooks import is_configured as qb_secrets_configured


def _any_real_connector(u: dict) -> bool:
    """True if at least one integration still has live credentials."""
    return bool(
        (u.get("toast_api_key") and u.get("toast_client_secret") and u.get("toast_guid")) or
        (u.get("paychex_client_id") and u.get("paychex_client_secret") and u.get("paychex_company_id")) or
        (u.get("qb_realm_id") and u.get("qb_refresh_token"))
    )

user     = st.session_state["user"]
username = user["username"]

# ── Surface any OAuth result messages ────────────────────────────────────────
if st.session_state.pop("qb_just_connected", False):
    st.success("QuickBooks connected successfully. Your data will sync shortly.")
if "oauth_error" in st.session_state:
    st.error(st.session_state.pop("oauth_error"))

page_header(
    "⚙️ Account Settings",
    subtitle=f"Manage your profile and security settings for account '{username}'.",
    eyebrow="Account",
)
st.divider()

# ── Restaurant Profile ────────────────────────────────────────────────────────
st.subheader("Restaurant Profile")
with st.form("profile_form"):
    new_name = st.text_input(
        "Restaurant Name",
        value=user.get("restaurant_name") or "",
        help="This name appears on all reports and dashboard headers.",
    )
    new_email = st.text_input(
        "Email Address",
        value=user.get("email") or "",
        help="Used when sending reports. Leave blank to disable email delivery.",
    )
    save_profile = st.form_submit_button("Save Profile", use_container_width=False)

if save_profile:
    if not new_name.strip():
        st.error("Restaurant name cannot be empty.")
    else:
        db.update_user(username, restaurant_name=new_name.strip(), email=new_email.strip() or None)
        user["restaurant_name"] = new_name.strip()
        user["email"]           = new_email.strip() or None
        st.session_state["user"] = user
        st.success("Profile updated.")

st.divider()

# ── Change Password ───────────────────────────────────────────────────────────
st.subheader("Change Password")
with st.form("password_form"):
    current_pw  = st.text_input("Current Password", type="password")
    new_pw      = st.text_input("New Password",      type="password")
    confirm_pw  = st.text_input("Confirm New Password", type="password")
    save_pw     = st.form_submit_button("Update Password", use_container_width=False)

if save_pw:
    if not db.verify_password(current_pw, user["password_hash"]):
        st.error("Current password is incorrect.")
    elif new_pw != confirm_pw:
        st.error("Passwords do not match.")
    elif len(new_pw) < 6:
        st.error("New password must be at least 6 characters.")
    else:
        new_hash = db.hash_password(new_pw)
        db.update_user(username, password_hash=new_hash)
        refreshed = db.get_user(username)
        st.session_state["user"] = dict(refreshed)
        st.success("Password updated successfully.")

st.divider()

# ── Integrations ──────────────────────────────────────────────────────────────
st.subheader("Integrations")

qb_connected = bool(user.get("qb_realm_id") and user.get("qb_refresh_token"))

# API keys = verified (server-to-server); portal credentials = saved but unverified until first sync
toast_has_api_creds    = bool(user.get("toast_api_key") and user.get("toast_client_secret") and user.get("toast_guid"))
toast_has_portal_creds = bool(user.get("toast_username") and user.get("toast_password_enc"))
toast_connected        = toast_has_api_creds or toast_has_portal_creds

px_has_api_creds    = bool(user.get("paychex_client_id") and user.get("paychex_client_secret") and user.get("paychex_company_id"))
px_has_portal_creds = bool(user.get("paychex_username") and user.get("paychex_password_enc"))
px_connected        = px_has_api_creds or px_has_portal_creds

# ── QuickBooks Online ─────────────────────────────────────────────────────────
with st.container(border=True):
    col_logo, col_status, col_action = st.columns([1, 3, 2])
    with col_logo:
        st.markdown("**QuickBooks Online**")
        st.caption("Expenses & Cash Flow")
    with col_status:
        if qb_connected:
            st.success(f"Connected — Company ID: `{user['qb_realm_id']}`")
        else:
            st.warning("Not connected")
    with col_action:
        if qb_connected:
            if st.button("Disconnect", key="qb_disconnect", use_container_width=True):
                db.update_user(username, qb_realm_id=None, qb_refresh_token=None)
                user.update({"qb_realm_id": None, "qb_refresh_token": None})
                if not _any_real_connector(user):
                    db.update_user(username, use_simulated_data=True)
                    user["use_simulated_data"] = True
                st.session_state["user"] = user
                st.rerun()
        else:
            if not qb_secrets_configured():
                st.info("App credentials not configured in secrets.toml.")
            else:
                from utils.oauth_quickbooks import generate_nonce, get_auth_url as qb_auth_url
                if "qb_connect_nonce" not in st.session_state:
                    _nonce = generate_nonce()
                    db.update_user(username, oauth_state=_nonce)
                    st.session_state["qb_connect_nonce"] = _nonce
                st.markdown(
                    f'<a href="{qb_auth_url(username, st.session_state["qb_connect_nonce"])}" '
                    f'target="_blank" rel="noopener noreferrer">'
                    f'<button style="width:100%;background:#FF4B4B;color:white;border:none;'
                    f'padding:0.45rem 1rem;border-radius:0.5rem;font-weight:600;'
                    f'font-size:0.9rem;cursor:pointer;">Connect QuickBooks ↗</button></a>',
                    unsafe_allow_html=True,
                )

# ── Toast POS ─────────────────────────────────────────────────────────────────
with st.container(border=True):
    col_logo, col_status, col_action = st.columns([1, 3, 2])
    with col_logo:
        st.markdown("**Toast POS**")
        st.caption("Sales & Labor")
    with col_status:
        if toast_has_api_creds:
            st.success(f"Connected — {user.get('toast_guid')}")
        elif toast_has_portal_creds:
            st.info(f"Credentials saved — {user.get('toast_username')}  ·  Not yet verified (syncs nightly)")
        else:
            st.warning("Not connected")
    with col_action:
        if toast_connected:
            if st.button("Disconnect", key="toast_disconnect", use_container_width=True):
                db.update_user(
                    username,
                    toast_username=None, toast_password_enc=None,
                    toast_api_key=None, toast_client_secret=None, toast_guid=None,
                )
                user.update({
                    "toast_username": None, "toast_password_enc": None,
                    "toast_api_key": None, "toast_client_secret": None, "toast_guid": None,
                })
                if not _any_real_connector(user):
                    db.update_user(username, use_simulated_data=True)
                    user["use_simulated_data"] = True
                st.session_state["user"] = user
                st.rerun()

    if not toast_connected:
        with st.form("toast_connect_form"):
            st.caption(
                "Enter your **Toast POS login** (the same email and password you use "
                "at pos.toasttab.com). Your password is stored encrypted."
            )
            t_col1, t_col2 = st.columns(2)
            t_email    = t_col1.text_input("Toast Email")
            t_password = t_col2.text_input("Toast Password", type="password")
            toast_submit = st.form_submit_button("Connect Toast POS", use_container_width=True)

        if toast_submit:
            if not (t_email.strip() and t_password.strip()):
                st.error("Email and password are required.")
            else:
                from utils.encryption import encrypt
                db.update_user(
                    username,
                    toast_username=t_email.strip(),
                    toast_password_enc=encrypt(t_password),
                    use_simulated_data=False,
                )
                user.update({
                    "toast_username":     t_email.strip(),
                    "toast_password_enc": encrypt(t_password),
                    "use_simulated_data": False,
                })
                st.session_state["user"] = user
                st.info("Toast credentials saved. They will be verified and data pulled at the next scheduled sync (nightly 6 AM). If the login fails, you will remain on simulated data.")
                st.rerun()

# ── Paychex Flex ──────────────────────────────────────────────────────────────
with st.container(border=True):
    col_logo, col_status, col_action = st.columns([1, 3, 2])
    with col_logo:
        st.markdown("**Paychex Flex**")
        st.caption("Payroll & Labor")
    with col_status:
        if px_has_api_creds:
            st.success(f"Connected — {user.get('paychex_company_id')}")
        elif px_has_portal_creds:
            st.info(f"Credentials saved — {user.get('paychex_username')}  ·  Not yet verified (syncs nightly)")
        else:
            st.warning("Not connected")
    with col_action:
        if px_connected:
            if st.button("Disconnect", key="paychex_disconnect", use_container_width=True):
                db.update_user(
                    username,
                    paychex_username=None, paychex_password_enc=None,
                    paychex_client_id=None, paychex_client_secret=None, paychex_company_id=None,
                )
                user.update({
                    "paychex_username": None, "paychex_password_enc": None,
                    "paychex_client_id": None, "paychex_client_secret": None, "paychex_company_id": None,
                })
                if not _any_real_connector(user):
                    db.update_user(username, use_simulated_data=True)
                    user["use_simulated_data"] = True
                st.session_state["user"] = user
                st.rerun()

    if not px_connected:
        with st.form("paychex_connect_form"):
            st.caption(
                "Enter your **Paychex Flex login** (the same username and password you use "
                "at myapps.paychex.com). Your password is stored encrypted."
            )
            p_col1, p_col2 = st.columns(2)
            p_user     = p_col1.text_input("Paychex Username")
            p_password = p_col2.text_input("Paychex Password", type="password")
            paychex_submit = st.form_submit_button("Connect Paychex Flex", use_container_width=True)

        if paychex_submit:
            if not (p_user.strip() and p_password.strip()):
                st.error("Username and password are required.")
            else:
                from utils.encryption import encrypt
                db.update_user(
                    username,
                    paychex_username=p_user.strip(),
                    paychex_password_enc=encrypt(p_password),
                    use_simulated_data=False,
                )
                user.update({
                    "paychex_username":     p_user.strip(),
                    "paychex_password_enc": encrypt(p_password),
                    "use_simulated_data":   False,
                })
                st.session_state["user"] = user
                st.info("Paychex credentials saved. They will be verified and data pulled at the next scheduled sync (nightly 6 AM). If the login fails, you will remain on simulated data.")
                st.rerun()

st.caption(
    "After connecting, click **Sync Now** on the Summary page or wait for the "
    "next scheduled sync to pull your live data."
)

if not qb_connected and "qb_connect_nonce" in st.session_state:
    with st.expander("Debug: view QB auth URL", expanded=False):
        from utils.oauth_quickbooks import get_auth_url as qb_auth_url
        st.code(qb_auth_url(username, st.session_state["qb_connect_nonce"]) if qb_secrets_configured() else "Secrets not configured")

st.divider()

# ── Account Info ──────────────────────────────────────────────────────────────
st.subheader("Account Information")
c1, c2, c3 = st.columns(3)
c1.metric("Username",      username)
c2.metric("Data Mode",     "Live API" if not user.get("use_simulated_data") else "Simulated")
c3.metric("Email on File", user.get("email") or "Not set")

st.divider()
st.caption("🔒 All changes are saved immediately and reflected across the dashboard.")

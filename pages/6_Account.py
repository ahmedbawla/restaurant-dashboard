"""
Account Settings — manage restaurant profile and password.
"""

import streamlit as st

from components.theme import page_header
from data import database as db

user     = st.session_state["user"]
username = user["username"]

# ── Trigger QB sync immediately after OAuth redirect ─────────────────────────
if st.session_state.pop("qb_just_connected", False):
    from data.sync import sync_all as _sync_all
    with st.spinner("QuickBooks connected — syncing your data now…"):
        _qb_res = _sync_all(db.get_user(username))
    _qb_err  = _qb_res.get("quickbooks", {}).get("error")
    _qb_rows = _qb_res.get("quickbooks", {}).get("rows", 0)
    if _qb_err:
        st.session_state["_acct_flash"] = [
            {"type": "error",   "text": f"QuickBooks sync failed: {_qb_err}"},
            {"type": "warning", "text": "Connection saved but no data was imported. Check your QuickBooks permissions."},
        ]
    elif _qb_rows == 0:
        st.session_state["_acct_flash"] = [
            {"type": "warning", "text": "QuickBooks connected but no data was returned. Ensure your QB account has transactions in the selected date range."},
        ]
    else:
        st.session_state["_acct_flash"] = [
            {"type": "success", "text": f"QuickBooks connected and synced {_qb_rows} rows."},
        ]
    st.session_state["user"] = db.get_user(username)
    st.cache_data.clear()
    st.rerun()

if "oauth_error" in st.session_state:
    st.error(st.session_state.pop("oauth_error"))

for _msg in st.session_state.pop("_acct_flash", []):
    getattr(st, _msg["type"])(_msg["text"])

page_header(
    "⚙️ Account Settings",
    subtitle=f"Manage your profile and security settings for account '{username}'.",
    eyebrow="Account",
)
st.divider()

# ── Restaurant Profile + Change Password ──────────────────────────────────────
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
    _b1, _b2 = st.columns(2)
    save_profile = _b1.form_submit_button("Save Profile", use_container_width=True)
    open_pw      = _b2.form_submit_button("Change Password", use_container_width=True)

if save_profile:
    if not new_name.strip():
        st.error("Restaurant name cannot be empty.")
    else:
        db.update_user(username, restaurant_name=new_name.strip(), email=new_email.strip() or None)
        user["restaurant_name"] = new_name.strip()
        user["email"]           = new_email.strip() or None
        st.session_state["user"] = user
        st.success("Profile updated.")

if open_pw:
    st.session_state["_show_pw"] = not st.session_state.get("_show_pw", False)

if st.session_state.get("_show_pw"):
    with st.form("password_form"):
        st.markdown("**Change Password**")
        current_pw = st.text_input("Current Password", type="password")
        new_pw     = st.text_input("New Password",     type="password")
        confirm_pw = st.text_input("Confirm New Password", type="password")
        save_pw    = st.form_submit_button("Update Password", use_container_width=False)

    if save_pw:
        if not db.verify_password(current_pw, user["password_hash"]):
            st.error("Current password is incorrect.")
        elif new_pw != confirm_pw:
            st.error("Passwords do not match.")
        elif len(new_pw) < 6:
            st.error("New password must be at least 6 characters.")
        else:
            db.update_user(username, password_hash=db.hash_password(new_pw))
            st.session_state["user"] = dict(db.get_user(username))
            st.session_state["_show_pw"] = False
            st.success("Password updated successfully.")

st.divider()

# ── Paychex API ───────────────────────────────────────────────────────────────
st.subheader("Paychex Integration")

_px_connected = bool(user.get("paychex_client_id") and user.get("paychex_client_secret"))

if _px_connected:
    st.success(f"Connected — Company ID: `{user.get('paychex_company_id', '—')}`")
    _d1, _d2 = st.columns([1, 4])
    if _d1.button("Disconnect Paychex", key="px_disconnect"):
        db.update_user(username,
                       paychex_client_id=None,
                       paychex_client_secret=None,
                       paychex_company_id=None)
        st.session_state["user"] = db.get_user(username)
        st.cache_data.clear()
        st.rerun()
else:
    st.caption("Enter your Paychex Developer App credentials. These are stored encrypted and are only accessible to this account.")
    with st.form("paychex_api_form"):
        px_id     = st.text_input("Client ID",     placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        px_secret = st.text_input("Client Secret", type="password", placeholder="your client secret")
        px_submit = st.form_submit_button("Connect & Verify", use_container_width=False)

    if px_submit:
        if not (px_id.strip() and px_secret.strip()):
            st.error("Both Client ID and Client Secret are required.")
        else:
            from utils.oauth_paychex import connect as px_connect
            from utils.encryption import encrypt
            with st.spinner("Verifying credentials with Paychex…"):
                ok, companies, err = px_connect(px_id.strip(), px_secret.strip())
            if not ok:
                st.error(f"Connection failed: {err}")
            else:
                # Auto-select company (most accounts have exactly one)
                if len(companies) == 1:
                    company_id = companies[0].get("companyId") or companies[0].get("id", "")
                    db.update_user(
                        username,
                        paychex_client_id     = px_id.strip(),
                        paychex_client_secret = encrypt(px_secret.strip()),
                        paychex_company_id    = company_id,
                        use_simulated_data    = False,
                    )
                    st.session_state["user"] = db.get_user(username)
                    st.cache_data.clear()
                    st.success(f"Connected! Company: {companies[0].get('legalName', company_id)}")
                    st.rerun()
                elif len(companies) > 1:
                    # Multiple companies — store credentials, let user pick
                    st.session_state["_px_companies"] = companies
                    st.session_state["_px_id"]        = px_id.strip()
                    st.session_state["_px_secret"]    = px_secret.strip()
                    st.rerun()
                else:
                    st.error("Credentials valid but no companies found. Check your Paychex app scopes include 'companies'.")

# Multi-company picker (shown after successful auth if >1 company)
if st.session_state.get("_px_companies"):
    _companies = st.session_state["_px_companies"]
    _options   = {c.get("legalName", c.get("companyId", "")): c for c in _companies}
    _picked    = st.selectbox("Select Company", list(_options.keys()), key="px_company_pick")
    if st.button("Confirm Company", key="px_company_confirm"):
        from utils.encryption import encrypt
        _c = _options[_picked]
        db.update_user(
            username,
            paychex_client_id     = st.session_state["_px_id"],
            paychex_client_secret = encrypt(st.session_state["_px_secret"]),
            paychex_company_id    = _c.get("companyId") or _c.get("id", ""),
            use_simulated_data    = False,
        )
        st.session_state["user"] = db.get_user(username)
        st.cache_data.clear()
        for k in ("_px_companies", "_px_id", "_px_secret"):
            st.session_state.pop(k, None)
        st.success(f"Connected to {_picked}.")
        st.rerun()

st.divider()

# ── Account Info ──────────────────────────────────────────────────────────────
st.subheader("Account Information")
c1, c2, c3 = st.columns(3)
c1.metric("Username",      username)
c2.metric("Data Mode",     "Live" if not user.get("use_simulated_data") else "Simulated")
c3.metric("Email on File", user.get("email") or "Not set")

st.divider()
st.caption("🔒 All changes are saved immediately and reflected across the dashboard.")

"""
Account Settings — manage email, restaurant name, password, and integrations.
"""

import streamlit as st

from components.theme import page_header
from data import database as db
from utils.oauth_quickbooks import is_configured as qb_secrets_configured


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

# ── Display persistent flash messages (survive rerun) ─────────────────────────
for _msg in st.session_state.pop("_acct_flash", []):
    getattr(st, _msg["type"])(_msg["text"])

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

qb_connected   = bool(user.get("qb_realm_id") and user.get("qb_refresh_token"))
qb_has_banking = bool(user.get("qb_banking_scope"))

# ── QuickBooks Online ─────────────────────────────────────────────────────────
with st.container(border=True):
    col_logo, col_status, col_action = st.columns([1, 3, 2])
    with col_logo:
        st.markdown("**QuickBooks Online**")
        st.caption("Expenses & Cash Flow")
    with col_status:
        if qb_connected:
            st.success(f"Connected — Company ID: `{user['qb_realm_id']}`")
            if not qb_has_banking:
                st.caption("⚠️ Bank feed access not enabled — click **Add Bank Feed Access** to include pending transactions.")
        else:
            st.warning("Not connected")
    with col_action:
        if qb_connected:
            if st.button("Disconnect", key="qb_disconnect", use_container_width=True):
                db.update_user(username, qb_realm_id=None, qb_refresh_token=None,
                               qb_banking_scope=False)
                user.update({"qb_realm_id": None, "qb_refresh_token": None,
                             "qb_banking_scope": False})
                st.session_state["user"] = user
                st.cache_data.clear()
                st.rerun()
            if not qb_has_banking and qb_secrets_configured():
                from utils.oauth_quickbooks import generate_nonce, get_auth_url as qb_auth_url
                if "qb_upgrade_nonce" not in st.session_state:
                    _upg_nonce = generate_nonce()
                    db.update_user(username, oauth_state=_upg_nonce)
                    st.session_state["qb_upgrade_nonce"] = _upg_nonce
                st.markdown(
                    f'<a href="{qb_auth_url(username, st.session_state["qb_upgrade_nonce"])}" '
                    f'target="_blank" rel="noopener noreferrer">'
                    f'<button style="width:100%;background:#2ecc71;color:white;border:none;'
                    f'padding:0.45rem 1rem;border-radius:0.5rem;font-weight:600;'
                    f'font-size:0.9rem;cursor:pointer;margin-top:0.4rem;">Add Bank Feed Access ↗</button></a>',
                    unsafe_allow_html=True,
                )
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
    st.markdown("**Toast POS** — Sales & Menu Data")
    st.caption(
        "Upload Toast CSV exports directly on the **Sales** and **Inventory** pages "
        "using the '📤 Update' buttons at the top of each page."
    )
    tc1, tc2 = st.columns(2)
    tc1.info("Sales data → **Sales** page")
    tc2.info("Menu data → **Inventory** page")

# ── Paychex Flex ──────────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("**Paychex Flex** — Payroll & Labour Data")
    st.caption(
        "Upload Paychex CSV exports directly on the **Payroll** page "
        "using the '📤 Update Paychex Data' button at the top of that page."
    )
    st.info("Payroll & labour data → **Payroll** page")

if not qb_connected and "qb_connect_nonce" in st.session_state:
    with st.expander("Debug: view QB auth URL", expanded=False):
        from utils.oauth_quickbooks import get_auth_url as qb_auth_url
        st.code(qb_auth_url(username, st.session_state["qb_connect_nonce"]) if qb_secrets_configured() else "Secrets not configured")

if qb_connected:
    with st.expander("QuickBooks Diagnostics", expanded=False):
        st.caption(
            "Queries QuickBooks directly and shows how many transactions and what "
            "total dollar amount each source returned for the last 90 days. "
            "Use this to identify where data is missing."
        )
        if st.button("Run QB Diagnostics", key="qb_diag"):
            from datetime import date, timedelta
            from data.connectors.quickbooks_connector import QuickBooksConnector
            _diag_conn = QuickBooksConnector({
                "realm_id":      user["qb_realm_id"],
                "refresh_token": user["qb_refresh_token"],
                "username":      username,
            })
            _diag_end   = date.today()
            _diag_start = _diag_end - timedelta(days=90)
            _sd, _ed    = _diag_start.isoformat(), _diag_end.isoformat()

            _diag_results = []

            for _label, _sql in [
                ("Purchase (credit card / check / cash)",
                 f"SELECT * FROM Purchase WHERE TxnDate >= '{_sd}' AND TxnDate <= '{_ed}'"),
                ("Bill (accounts payable invoices)",
                 f"SELECT * FROM Bill WHERE TxnDate >= '{_sd}' AND TxnDate <= '{_ed}'"),
                ("JournalEntry (payroll, depreciation, accruals)",
                 f"SELECT * FROM JournalEntry WHERE TxnDate >= '{_sd}' AND TxnDate <= '{_ed}'"),
            ]:
                try:
                    _txns  = _diag_conn._query_all(_sql)
                    _count = len(_txns)
                    _total = sum(float(t.get("TotalAmt", 0)) for t in _txns)
                    _diag_results.append({
                        "Source": _label,
                        "Transactions": _count,
                        "Total ($)": f"${_total:,.2f}",
                    })
                except Exception as _e:
                    _diag_results.append({
                        "Source": _label,
                        "Transactions": "ERROR",
                        "Total ($)": str(_e),
                    })

            # Pending bank feed (requires banking scope)
            try:
                _pending_df = _diag_conn.get_pending_bank_transactions(_diag_start, _diag_end)
                _diag_results.append({
                    "Source":        "Pending bank feed (For Review)",
                    "Transactions":  len(_pending_df),
                    "Total ($)":     f"${_pending_df['amount'].sum():,.2f}" if not _pending_df.empty else "$0.00",
                })
            except Exception as _e:
                _diag_results.append({
                    "Source":       "Pending bank feed (For Review)",
                    "Transactions": "ERROR",
                    "Total ($)":    str(_e),
                })

            import pandas as _dpd
            st.dataframe(_dpd.DataFrame(_diag_results), use_container_width=True, hide_index=True)
            st.caption(f"Date range: {_sd} → {_ed}  ·  TotalAmt is the transaction-level total, not line-item sum.")

st.divider()

# ── Account Info ──────────────────────────────────────────────────────────────
st.subheader("Account Information")
c1, c2, c3 = st.columns(3)
c1.metric("Username",      username)
c2.metric("Data Mode",     "Live API" if not user.get("use_simulated_data") else "Simulated")
c3.metric("Email on File", user.get("email") or "Not set")

st.divider()
st.caption("🔒 All changes are saved immediately and reflected across the dashboard.")

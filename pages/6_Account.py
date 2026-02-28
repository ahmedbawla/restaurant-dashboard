"""
Account Settings — manage email, restaurant name, and password.
"""

import streamlit as st

from components.theme import page_header
from data import database as db

user     = st.session_state["user"]
username = user["username"]

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

# ── Account Info ──────────────────────────────────────────────────────────────
st.subheader("Account Information")
c1, c2, c3 = st.columns(3)
c1.metric("Username",        username)
c2.metric("Data Mode",       "Simulated" if user.get("use_simulated_data") else "Live API")
c3.metric("Email on File",   user.get("email") or "Not set")

st.divider()
st.caption("🔒 All changes are saved immediately and reflected across the dashboard.")

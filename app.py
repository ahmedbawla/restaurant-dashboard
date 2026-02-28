"""
Entry point — handles auth, global date range, and page routing.
Run with: python -m streamlit run app.py
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from auth import require_auth, render_sidebar_logout, seed_test_user
from components.theme import apply_professional_theme
from data import database as db

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Restaurant BI Dashboard",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_professional_theme()

# ── Run DB migrations on every startup (idempotent) ──────────────────────────
db.init_db()

# ── Seed demo account once per session ───────────────────────────────────────
if "seeded" not in st.session_state:
    seed_test_user()
    st.session_state["seeded"] = True

# ── Auth gate ─────────────────────────────────────────────────────────────────
user     = require_auth()
username = user["username"]
render_sidebar_logout()

# ── Global date range selector ────────────────────────────────────────────────
min_str, max_str = db.get_date_range(username)
min_d = date.fromisoformat(min_str)
max_d = date.fromisoformat(max_str)

with st.sidebar:
    st.divider()
    st.caption("ANALYSIS PERIOD")
    default_start = max(min_d, max_d - timedelta(days=89))
    picked = st.date_input(
        "Date Range",
        value=(default_start, max_d),
        min_value=min_d,
        max_value=max_d,
        key="global_date_range",
    )
    if isinstance(picked, (list, tuple)) and len(picked) == 2:
        st.session_state["start_date"] = picked[0].isoformat()
        st.session_state["end_date"]   = picked[1].isoformat()
    else:
        st.session_state["start_date"] = default_start.isoformat()
        st.session_state["end_date"]   = max_d.isoformat()

# ── Navigation ────────────────────────────────────────────────────────────────
pg = st.navigation([
    st.Page("pages/summary.py",      title="Summary",          icon="🏠"),
    st.Page("pages/1_Spending.py",   title="Spending",         icon="💳"),
    st.Page("pages/2_Payroll.py",    title="Payroll",          icon="👥"),
    st.Page("pages/3_Inventory.py",  title="Inventory",        icon="🥩"),
    st.Page("pages/4_Sales.py",      title="Sales",            icon="📈"),
    st.Page("pages/5_Reports.py",    title="Reports",          icon="📄"),
    st.Page("pages/6_Account.py",    title="Account Settings", icon="⚙️"),
])
pg.run()

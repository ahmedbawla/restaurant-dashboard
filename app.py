"""
Overview page — Streamlit entry point.
Run with: streamlit run app.py
"""

import json
import sys
from pathlib import Path

# Ensure project root is on the path so all imports work
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from auth import require_auth, render_sidebar_logout, seed_test_user
from components.kpi_card import kpi_card, format_currency, format_pct, threshold_badge
from components.charts import revenue_trend
from data import database as db

# ── Config (thresholds only — restaurant name comes from user) ───────────────
with open(Path(__file__).parent / "config.json") as f:
    CONFIG = json.load(f)

THRESHOLDS = CONFIG.get("thresholds", {})

st.set_page_config(
    page_title="Restaurant BI Dashboard",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark theme tweak ─────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
    [data-testid="stMetricDelta"] { font-size: 0.85rem !important; }
    .block-container { padding-top: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Auth gate ────────────────────────────────────────────────────────────────
seed_test_user()
user = require_auth()
render_sidebar_logout()

RESTAURANT_NAME = user["restaurant_name"]
username = user["username"]

# ── Header ───────────────────────────────────────────────────────────────────
st.title(f"🍽️ {RESTAURANT_NAME} — Business Intelligence Dashboard")
st.caption(
    "Data refreshed daily · Simulated data mode"
    if user.get("use_simulated_data")
    else "Data refreshed daily"
)

st.divider()

# ── Load data ────────────────────────────────────────────────────────────────
kpi = db.get_kpi_today(username)
daily_sales = db.get_daily_sales(username, days=90)

if not kpi:
    st.error("No data found. Run `python data/sync.py` to populate the database.")
    st.stop()

# ── KPI Row ──────────────────────────────────────────────────────────────────
st.subheader("Today's Performance")
c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    kpi_card("Daily Revenue", format_currency(kpi["revenue"]))
with c2:
    kpi_card("Net Profit", format_currency(kpi["net_profit"]))
with c3:
    prime = kpi["prime_cost_pct"]
    kpi_card(
        "Prime Cost %",
        threshold_badge(prime, THRESHOLDS.get("prime_cost_pct_target", 60), THRESHOLDS.get("prime_cost_pct_warning", 65)),
    )
with c4:
    food = kpi["food_cost_pct"]
    kpi_card(
        "Food Cost %",
        threshold_badge(food, THRESHOLDS.get("food_cost_pct_target", 30), THRESHOLDS.get("food_cost_pct_warning", 33)),
    )
with c5:
    labor = kpi["labor_cost_pct"]
    kpi_card(
        "Labor Cost %",
        threshold_badge(labor, THRESHOLDS.get("labor_cost_pct_target", 30), THRESHOLDS.get("labor_cost_pct_warning", 33)),
    )
with c6:
    kpi_card("Avg Check", format_currency(kpi["avg_check"]))

st.divider()

# ── Revenue Chart ─────────────────────────────────────────────────────────────
st.subheader("30-Day Revenue Trend")
st.plotly_chart(revenue_trend(daily_sales, days=30), use_container_width=True)

st.divider()

# ── Quick Snapshot ────────────────────────────────────────────────────────────
st.subheader("Quick Snapshot")
s1, s2, s3, s4 = st.columns(4)

with s1:
    st.metric("Covers Today", f"{kpi['covers']:,}")
with s2:
    st.metric("Food Cost Today", format_currency(kpi["food_cost"]))
with s3:
    st.metric("Labor Cost Today", format_currency(kpi["labor_cost"]))
with s4:
    rev_7 = daily_sales.tail(7)["revenue"].sum()
    st.metric("Revenue (Last 7 Days)", format_currency(rev_7))

# ── 90-day summary stats ──────────────────────────────────────────────────────
st.divider()
st.subheader("90-Day Summary")
t1, t2, t3 = st.columns(3)

with t1:
    total_rev = daily_sales["revenue"].sum()
    avg_daily = daily_sales["revenue"].mean()
    st.metric("Total Revenue (90d)", format_currency(total_rev))
    st.metric("Avg Daily Revenue", format_currency(avg_daily))

with t2:
    avg_food_pct = daily_sales["food_cost_pct"].mean()
    st.metric("Avg Food Cost %", format_pct(avg_food_pct))
    st.metric("Avg Covers/Day", f"{daily_sales['covers'].mean():.0f}")

with t3:
    peak_day = daily_sales.loc[daily_sales["revenue"].idxmax()]
    st.metric("Best Sales Day", peak_day["date"])
    st.metric("Best Day Revenue", format_currency(peak_day["revenue"]))

"""
Summary — business overview dashboard.
"""

import json
from pathlib import Path

import streamlit as st

from components.kpi_card import kpi_card, format_currency, format_pct, threshold_badge
from components.charts import revenue_trend
from components.theme import page_header
from data import database as db

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)
THRESHOLDS = CONFIG.get("thresholds", {})

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    f"🍽️ {user['restaurant_name']}",
    subtitle=(
        "Business Intelligence Dashboard  ·  Simulated data mode"
        if user.get("use_simulated_data")
        else f"Business Intelligence Dashboard  ·  {start_date} – {end_date}"
    ),
    eyebrow="Shareholder Overview",
)
st.divider()

# ── Load data ─────────────────────────────────────────────────────────────────
kpi         = db.get_kpi_today(username, as_of_date=end_date)
daily_sales = db.get_daily_sales(username, start_date=start_date, end_date=end_date)

if not kpi or daily_sales.empty:
    st.warning("No data found for the selected period. Adjust the date range in the sidebar.")
    st.stop()

# ── Period-over-period deltas ──────────────────────────────────────────────────
# Compare first half vs second half of the selected window
mid = len(daily_sales) // 2
rev_recent = daily_sales.iloc[mid:]["revenue"].sum()
rev_prior  = daily_sales.iloc[:mid]["revenue"].sum()
rev_delta  = (
    f"{(rev_recent / rev_prior - 1) * 100:+.1f}% vs. prior period"
    if rev_prior else None
)
covers_recent = daily_sales.iloc[mid:]["covers"].sum()
covers_prior  = daily_sales.iloc[:mid]["covers"].sum()
covers_delta  = (
    f"{(covers_recent / covers_prior - 1) * 100:+.1f}% vs. prior period"
    if covers_prior else None
)

# ── Today's KPIs ──────────────────────────────────────────────────────────────
st.subheader(f"Most Recent Day on Record — {kpi['date']}")
c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    kpi_card("Daily Revenue", format_currency(kpi["revenue"]),
             help_text="Total revenue for the most recent day in the selected period.")
with c2:
    kpi_card("Net Profit", format_currency(kpi["net_profit"]),
             help_text="Revenue minus food cost and labour cost.")
with c3:
    prime = kpi["prime_cost_pct"]
    kpi_card("Prime Cost %",
             threshold_badge(prime, THRESHOLDS.get("prime_cost_pct_target", 60),
                             THRESHOLDS.get("prime_cost_pct_warning", 65)),
             help_text="Food cost % + labour cost %. Target: ≤60%.")
with c4:
    food = kpi["food_cost_pct"]
    kpi_card("Food Cost %",
             threshold_badge(food, THRESHOLDS.get("food_cost_pct_target", 30),
                             THRESHOLDS.get("food_cost_pct_warning", 33)),
             help_text="Cost of goods as a percentage of revenue. Target: ≤30%.")
with c5:
    labor = kpi["labor_cost_pct"]
    kpi_card("Labour Cost %",
             threshold_badge(labor, THRESHOLDS.get("labor_cost_pct_target", 30),
                             THRESHOLDS.get("labor_cost_pct_warning", 33)),
             help_text="Labour cost as a percentage of revenue. Target: ≤30%.")
with c6:
    kpi_card("Avg. Check Size", format_currency(kpi["avg_check"]),
             help_text="Average revenue per guest cover.")

st.divider()

# ── Revenue trend ─────────────────────────────────────────────────────────────
st.subheader("Revenue Trend")
days_shown = len(daily_sales)
st.plotly_chart(revenue_trend(daily_sales, days=days_shown), use_container_width=True)

st.divider()

# ── Period performance ────────────────────────────────────────────────────────
st.subheader("Period Performance")
s1, s2, s3, s4 = st.columns(4)
with s1:
    st.metric("Total Revenue", format_currency(daily_sales["revenue"].sum()),
              delta=rev_delta)
with s2:
    st.metric("Total Guest Covers", f"{int(daily_sales['covers'].sum()):,}",
              delta=covers_delta)
with s3:
    st.metric("Avg. Check Size", format_currency(daily_sales["avg_check"].mean()))
with s4:
    st.metric("Total Food Cost", format_currency(daily_sales["food_cost"].sum()))

st.divider()

# ── Operating summary ─────────────────────────────────────────────────────────
st.subheader("Operating Summary")
t1, t2, t3, t4 = st.columns(4)

with t1:
    st.metric("Avg. Daily Revenue",  format_currency(daily_sales["revenue"].mean()))
    st.metric("Avg. Covers / Day",   f"{daily_sales['covers'].mean():.0f}")
with t2:
    st.metric("Avg. Food Cost %",    format_pct(daily_sales["food_cost_pct"].mean()))
    total_rev = daily_sales["revenue"].sum()
    food_pct_actual = daily_sales["food_cost"].sum() / total_rev * 100 if total_rev else 0
    st.metric("Actual Food Cost %",  format_pct(food_pct_actual))
with t3:
    peak = daily_sales.loc[daily_sales["revenue"].idxmax()]
    st.metric("Best Revenue Day",    peak["date"])
    st.metric("Best Day Revenue",    format_currency(peak["revenue"]))
with t4:
    low = daily_sales.loc[daily_sales["revenue"].idxmin()]
    st.metric("Lowest Revenue Day",  low["date"])
    st.metric("Lowest Day Revenue",  format_currency(low["revenue"]))

st.divider()
st.caption(
    f"🔒 Confidential  ·  For authorised recipients only  ·  "
    f"{user['restaurant_name']} Business Intelligence Dashboard"
)

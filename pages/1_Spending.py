"""
Spending & Expenses — QuickBooks Online data.
"""

import streamlit as st
import pandas as pd

from components.charts import expense_pie, top_vendors_bar, expense_trend_weekly
from components.kpi_card import format_currency
from components.theme import page_header
from data import database as db

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "💳 Spending & Expenses",
    subtitle="Operating expense breakdown sourced from QuickBooks Online.",
    eyebrow="Financial Analysis",
)
st.divider()

# ── Data ─────────────────────────────────────────────────────────────────────
expenses = db.get_expenses(username, start_date=start_date, end_date=end_date)

if expenses.empty:
    st.warning("No expense data found for the selected period.")
    st.stop()

expenses["date"] = pd.to_datetime(expenses["date"])

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    all_cats = sorted(expenses["category"].unique())
    selected_cats = st.multiselect("Category", all_cats, default=all_cats)

filtered = expenses[expenses["category"].isin(selected_cats)]

if filtered.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

# ── KPI row ───────────────────────────────────────────────────────────────────
total_spend = filtered["amount"].sum()
daily_avg   = filtered.groupby(filtered["date"].dt.date)["amount"].sum().mean()

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total Spend (Period)", format_currency(total_spend))
with k2:
    st.metric("Avg. Daily Spend", format_currency(daily_avg))
with k3:
    top_cat = filtered.groupby("category")["amount"].sum().idxmax()
    st.metric("Largest Expense Category", top_cat)
with k4:
    top_vendor = filtered.groupby("vendor")["amount"].sum().idxmax()
    st.metric("Top Vendor", top_vendor)

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(expense_pie(filtered), use_container_width=True)
with col2:
    st.plotly_chart(top_vendors_bar(filtered), use_container_width=True)

st.plotly_chart(expense_trend_weekly(filtered), use_container_width=True)

# ── Transaction detail ────────────────────────────────────────────────────────
st.divider()
st.subheader("Transaction Detail")
display = filtered.copy()
display["date"]   = display["date"].dt.strftime("%Y-%m-%d")
display["amount"] = display["amount"].apply(lambda x: f"${x:,.2f}")
display = display[["date","category","vendor","amount","description"]].sort_values("date", ascending=False)
display.columns = ["Date","Category","Vendor","Amount","Description"]
st.dataframe(display, use_container_width=True, height=420, hide_index=True)

st.divider()
st.caption("🔒 Confidential  ·  For authorised recipients only")

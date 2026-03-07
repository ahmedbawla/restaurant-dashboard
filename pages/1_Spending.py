"""
Spending & Expenses — QuickBooks Online data.
"""

import streamlit as st
import pandas as pd

from components.charts import expense_pie, top_vendors_bar, expense_trend_weekly
from components.kpi_card import format_currency
from components.theme import page_header, section_header
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

# ── Data ─────────────────────────────────────────────────────────────────────
expenses = db.get_expenses(username, start_date=start_date, end_date=end_date)

if expenses.empty:
    st.warning("No expense data found for the selected period.")
    st.stop()

expenses["date"] = pd.to_datetime(expenses["date"])

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    all_cats      = sorted(expenses["category"].unique())
    selected_cats = st.multiselect("Category", all_cats, default=all_cats)

filtered = expenses[expenses["category"].isin(selected_cats)]

if filtered.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

# ── Period-over-period ────────────────────────────────────────────────────────
filtered_sorted = filtered.sort_values("date")
mid = len(filtered_sorted) // 2
spend_recent = filtered_sorted.iloc[mid:]["amount"].sum()
spend_prior  = filtered_sorted.iloc[:mid]["amount"].sum()
spend_delta  = f"{(spend_recent/spend_prior - 1)*100:+.1f}% vs prior period" if spend_prior else None

# ── KPI strip ─────────────────────────────────────────────────────────────────
section_header("Expense Overview", help="Operating expenses from QuickBooks Online for the selected period. Delta compares the second half of the period to the first.")
total_spend  = filtered["amount"].sum()
daily_avg    = filtered.groupby(filtered["date"].dt.date)["amount"].sum().mean()
top_cat      = filtered.groupby("category")["amount"].sum().idxmax()
top_vendor   = filtered.groupby("vendor")["amount"].sum().idxmax()
cat_totals   = filtered.groupby("category")["amount"].sum()
top_cat_pct  = cat_totals.max() / cat_totals.sum() * 100

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Total Spend",      format_currency(total_spend), delta=spend_delta)
with k2:
    st.metric("Avg. Daily Spend", format_currency(daily_avg))
with k3:
    st.metric("Largest Category", top_cat,
              help=f"{top_cat_pct:.1f}% of total spend")
with k4:
    st.metric("Top Vendor",       top_vendor)
with k5:
    n_vendors = filtered["vendor"].nunique()
    st.metric("Unique Vendors",   str(n_vendors))

st.divider()

# ── Charts row ────────────────────────────────────────────────────────────────
section_header("Breakdown", help="Left: each expense category as a share of total spend. Right: your top vendors by total amount paid in the period.")
col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(expense_pie(filtered), use_container_width=True)
with col2:
    st.plotly_chart(top_vendors_bar(filtered), use_container_width=True)

st.divider()

# ── Weekly trend with rolling avg ─────────────────────────────────────────────
section_header("Weekly Trend", help="Total spend per week. The dotted line is a 4-week rolling average to show the underlying trend.")
st.plotly_chart(expense_trend_weekly(filtered), use_container_width=True)

# ── Category breakdown table ──────────────────────────────────────────────────
st.divider()
section_header("Category Summary", help="Total spend, number of transactions, and average transaction size for each expense category in the selected period.")
cat_summary = filtered.groupby("category")["amount"].agg(
    Total="sum", Count="count", Average="mean"
).reset_index().sort_values("Total", ascending=False)
cat_summary["Total"]   = cat_summary["Total"].apply(lambda x: f"${x:,.2f}")
cat_summary["Average"] = cat_summary["Average"].apply(lambda x: f"${x:,.2f}")
cat_summary.columns    = ["Category", "Total Spend", "# Transactions", "Avg Transaction"]
st.dataframe(cat_summary, use_container_width=True, hide_index=True)

# ── Transaction detail ────────────────────────────────────────────────────────
st.divider()
section_header("Transaction Detail", help="Individual expense line items from QuickBooks, sorted by most recent first. Use the Category filter in the sidebar to narrow results.")
display = filtered.copy()
display["date"]   = display["date"].dt.strftime("%Y-%m-%d")
display["amount"] = display["amount"].apply(lambda x: f"${x:,.2f}")
display = display[["date","category","vendor","amount","description"]].sort_values("date", ascending=False)
display.columns = ["Date","Category","Vendor","Amount","Description"]
st.dataframe(display, use_container_width=True, height=400, hide_index=True)

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

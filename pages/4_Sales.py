"""
Sales Analysis — Toast POS sales data.
"""

import streamlit as st
import pandas as pd

from components.charts import hourly_heatmap, top_items_bar, avg_check_trend, covers_by_dow
from components.kpi_card import format_currency
from components.theme import page_header
from data import database as db

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "📈 Sales Analysis",
    subtitle="Revenue, guest covers, and check-size trends sourced from Toast POS.",
    eyebrow="Revenue Analytics",
)
st.divider()

# ── Data ─────────────────────────────────────────────────────────────────────
daily_sales  = db.get_daily_sales(username,  start_date=start_date, end_date=end_date)
hourly_sales = db.get_hourly_sales(username, start_date=start_date, end_date=end_date)
menu_items   = db.get_menu_items(username)

if daily_sales.empty:
    st.warning("No sales data found for the selected period.")
    st.stop()

# ── KPI row ───────────────────────────────────────────────────────────────────
total_rev    = daily_sales["revenue"].sum()
total_covers = daily_sales["covers"].sum()
avg_check    = daily_sales["avg_check"].mean()
best_idx     = daily_sales["revenue"].idxmax()
best_rev     = daily_sales.loc[best_idx, "revenue"]
best_date    = daily_sales.loc[best_idx, "date"]

# Period-over-period (first half vs second half of selected window)
mid = len(daily_sales) // 2
rev_recent = daily_sales.iloc[mid:]["revenue"].sum()
rev_prior  = daily_sales.iloc[:mid]["revenue"].sum()
rev_delta  = (f"{(rev_recent/rev_prior - 1)*100:+.1f}% vs. prior period"
              if rev_prior else None)

chk_recent = daily_sales.iloc[mid:]["avg_check"].mean()
chk_prior  = daily_sales.iloc[:mid]["avg_check"].mean()
chk_delta  = (f"{(chk_recent/chk_prior - 1)*100:+.1f}% vs. prior period"
              if chk_prior else None)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total Revenue (Period)", format_currency(total_rev), delta=rev_delta)
with k2:
    st.metric("Total Guest Covers", f"{int(total_covers):,}")
with k3:
    st.metric("Avg. Check Size", format_currency(avg_check), delta=chk_delta)
with k4:
    st.metric("Best Single-Day Revenue", format_currency(best_rev),
              help=f"Recorded on {best_date}.")

st.divider()

# ── Hourly heatmap ────────────────────────────────────────────────────────────
if not hourly_sales.empty:
    st.plotly_chart(hourly_heatmap(hourly_sales), use_container_width=True)
else:
    st.info("Hourly sales data is not available for the selected period.")

st.divider()

# ── Top-performing menu items ─────────────────────────────────────────────────
st.subheader("Top-Performing Menu Items")
col1, col2 = st.columns(2)
with col1:
    if not menu_items.empty:
        st.plotly_chart(top_items_bar(menu_items, metric="total_revenue"), use_container_width=True)
with col2:
    if not menu_items.empty:
        st.plotly_chart(top_items_bar(menu_items, metric="quantity_sold"), use_container_width=True)

# ── Trend charts ──────────────────────────────────────────────────────────────
st.subheader("Sales Trends")
col3, col4 = st.columns(2)
with col3:
    st.plotly_chart(avg_check_trend(daily_sales), use_container_width=True)
with col4:
    st.plotly_chart(covers_by_dow(daily_sales), use_container_width=True)

# ── Daily sales table ─────────────────────────────────────────────────────────
st.divider()
st.subheader("Daily Sales Detail")
table = daily_sales[["date","covers","revenue","avg_check","food_cost","food_cost_pct"]].copy()
table["revenue"]       = table["revenue"].apply(lambda x: f"${x:,.0f}")
table["avg_check"]     = table["avg_check"].apply(lambda x: f"${x:.2f}")
table["food_cost"]     = table["food_cost"].apply(lambda x: f"${x:,.0f}")
table["food_cost_pct"] = table["food_cost_pct"].apply(lambda x: f"{x:.1f}%")
table = table.sort_values("date", ascending=False)
table.columns = ["Date","Covers","Revenue","Avg. Check","Food Cost","Food Cost %"]
st.dataframe(table, use_container_width=True, height=420, hide_index=True)

st.divider()
st.caption("🔒 Confidential  ·  For authorised recipients only")

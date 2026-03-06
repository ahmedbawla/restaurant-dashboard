"""
Sales Analysis — Toast POS sales data.
"""

import streamlit as st
import pandas as pd

from components.charts import (
    hourly_heatmap, top_items_bar, avg_check_trend,
    covers_by_dow, revenue_trend, revenue_by_dow, revenue_per_cover_trend,
)
from components.kpi_card import format_currency, format_pct
from components.theme import page_header, section_header
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

# ── Data ─────────────────────────────────────────────────────────────────────
daily_sales  = db.get_daily_sales(username,  start_date=start_date, end_date=end_date)
hourly_sales = db.get_hourly_sales(username, start_date=start_date, end_date=end_date)
menu_items   = db.get_menu_items(username)

if daily_sales.empty:
    st.warning("No sales data found for the selected period.")
    st.stop()

# ── Period-over-period ────────────────────────────────────────────────────────
mid = len(daily_sales) // 2
rev_recent = daily_sales.iloc[mid:]["revenue"].sum()
rev_prior  = daily_sales.iloc[:mid]["revenue"].sum()
rev_delta  = f"{(rev_recent/rev_prior - 1)*100:+.1f}% vs prior period" if rev_prior else None
chk_recent = daily_sales.iloc[mid:]["avg_check"].mean()
chk_prior  = daily_sales.iloc[:mid]["avg_check"].mean()
chk_delta  = f"{(chk_recent/chk_prior - 1)*100:+.1f}% vs prior period" if chk_prior else None
cvr_recent = daily_sales.iloc[mid:]["covers"].sum()
cvr_prior  = daily_sales.iloc[:mid]["covers"].sum()
cvr_delta  = f"{(cvr_recent/cvr_prior - 1)*100:+.1f}% vs prior period" if cvr_prior else None

total_rev    = daily_sales["revenue"].sum()
total_covers = daily_sales["covers"].sum()
best_idx     = daily_sales["revenue"].idxmax()

# ── KPI strip ─────────────────────────────────────────────────────────────────
section_header("Period KPIs")
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Total Revenue",       format_currency(total_rev), delta=rev_delta)
with k2:
    st.metric("Total Covers",        f"{int(total_covers):,}", delta=cvr_delta)
with k3:
    st.metric("Avg. Check Size",     format_currency(daily_sales["avg_check"].mean()), delta=chk_delta)
with k4:
    st.metric("Best Day Revenue",    format_currency(daily_sales.loc[best_idx, "revenue"]),
              help=f"Recorded on {daily_sales.loc[best_idx, 'date']}.")
with k5:
    rpc = total_rev / total_covers if total_covers else 0
    st.metric("Rev per Cover",       format_currency(rpc),
              help="Average revenue generated per guest cover.")

st.divider()

# ── Revenue trend with 7-day rolling avg ─────────────────────────────────────
section_header("Revenue Trend")
st.plotly_chart(revenue_trend(daily_sales, days=len(daily_sales)), use_container_width=True)

st.divider()

# ── Peak hours heatmap ────────────────────────────────────────────────────────
section_header("Peak Hours Heatmap")
if not hourly_sales.empty:
    st.plotly_chart(hourly_heatmap(hourly_sales), use_container_width=True)
else:
    st.info("Hourly data not available for this period.")

st.divider()

# ── Day-of-week & spend-per-head ──────────────────────────────────────────────
section_header("Traffic Patterns")
col_a, col_b = st.columns(2)
with col_a:
    st.plotly_chart(revenue_by_dow(daily_sales), use_container_width=True)
with col_b:
    st.plotly_chart(covers_by_dow(daily_sales), use_container_width=True)

st.divider()

# ── Check size & spend per head trends ───────────────────────────────────────
section_header("Spend Trends")
col_c, col_d = st.columns(2)
with col_c:
    st.plotly_chart(avg_check_trend(daily_sales), use_container_width=True)
with col_d:
    st.plotly_chart(revenue_per_cover_trend(daily_sales), use_container_width=True)

st.divider()

# ── Top menu items ────────────────────────────────────────────────────────────
if not menu_items.empty:
    section_header("Top-Performing Menu Items")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(top_items_bar(menu_items, metric="total_revenue"), use_container_width=True)
    with col2:
        st.plotly_chart(top_items_bar(menu_items, metric="quantity_sold"), use_container_width=True)
    st.divider()

# ── Daily detail table ────────────────────────────────────────────────────────
section_header("Daily Sales Detail")
table = daily_sales[["date","covers","revenue","avg_check","food_cost","food_cost_pct"]].copy()
table["revenue"]       = table["revenue"].apply(lambda x: f"${x:,.0f}")
table["avg_check"]     = table["avg_check"].apply(lambda x: f"${x:.2f}")
table["food_cost"]     = table["food_cost"].apply(lambda x: f"${x:,.0f}")
table["food_cost_pct"] = table["food_cost_pct"].apply(lambda x: f"{x:.1f}%")
table = table.sort_values("date", ascending=False)
table.columns = ["Date", "Covers", "Revenue", "Avg. Check", "Food Cost", "Food Cost %"]
st.dataframe(table, use_container_width=True, height=400, hide_index=True)

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

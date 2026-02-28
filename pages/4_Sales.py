"""
Sales page — Toast POS sales breakdown.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from auth import require_auth, render_sidebar_logout
from components.charts import (
    hourly_heatmap,
    top_items_bar,
    avg_check_trend,
    covers_by_dow,
)
from components.kpi_card import format_currency
from data import database as db

st.set_page_config(page_title="Sales — BI Dashboard", layout="wide")

user = require_auth()
render_sidebar_logout()
username = user["username"]

st.title("📈 Sales")
st.caption("Source: Toast POS")
st.divider()

# ── Data ─────────────────────────────────────────────────────────────────────
daily_sales = db.get_daily_sales(username, days=90)
hourly_sales = db.get_hourly_sales(username, days=60)
menu_items = db.get_menu_items(username)

if daily_sales.empty:
    st.error("No sales data. Run `python data/sync.py` first.")
    st.stop()

# ── Date filter ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    daily_sales["date_dt"] = pd.to_datetime(daily_sales["date"])
    min_d = daily_sales["date_dt"].min().date()
    max_d = daily_sales["date_dt"].max().date()
    date_range = st.date_input("Date Range", value=(min_d, max_d), min_value=min_d, max_value=max_d)

start_d, end_d = (date_range[0], date_range[1]) if len(date_range) == 2 else (min_d, max_d)
filtered = daily_sales[
    (daily_sales["date_dt"].dt.date >= start_d)
    & (daily_sales["date_dt"].dt.date <= end_d)
]

# ── KPIs ─────────────────────────────────────────────────────────────────────
total_rev = filtered["revenue"].sum()
total_covers = filtered["covers"].sum()
avg_check = filtered["avg_check"].mean()
best_day_rev = filtered["revenue"].max()
best_day_date = filtered.loc[filtered["revenue"].idxmax(), "date"]

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total Revenue", format_currency(total_rev))
with k2:
    st.metric("Total Covers", f"{total_covers:,}")
with k3:
    st.metric("Avg Check Size", format_currency(avg_check))
with k4:
    st.metric("Best Sales Day", f"{best_day_date} · {format_currency(best_day_rev)}")

st.divider()

# ── Heatmap ───────────────────────────────────────────────────────────────────
if not hourly_sales.empty:
    st.plotly_chart(hourly_heatmap(hourly_sales), use_container_width=True)
else:
    st.info("No hourly data available.")

st.divider()

# ── Top items ─────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    if not menu_items.empty:
        st.plotly_chart(top_items_bar(menu_items, metric="total_revenue"), use_container_width=True)
with col2:
    if not menu_items.empty:
        st.plotly_chart(top_items_bar(menu_items, metric="quantity_sold"), use_container_width=True)

# ── Trend charts ──────────────────────────────────────────────────────────────
col3, col4 = st.columns(2)
with col3:
    st.plotly_chart(avg_check_trend(filtered), use_container_width=True)
with col4:
    st.plotly_chart(covers_by_dow(filtered), use_container_width=True)

# ── Daily sales table ─────────────────────────────────────────────────────────
st.divider()
st.subheader("Daily Sales Detail")
table = filtered[["date", "covers", "revenue", "avg_check", "food_cost", "food_cost_pct"]].copy()
table["revenue"] = table["revenue"].apply(lambda x: f"${x:,.0f}")
table["avg_check"] = table["avg_check"].apply(lambda x: f"${x:.2f}")
table["food_cost"] = table["food_cost"].apply(lambda x: f"${x:,.0f}")
table["food_cost_pct"] = table["food_cost_pct"].apply(lambda x: f"{x:.1f}%")
table = table.sort_values("date", ascending=False)
st.dataframe(table, use_container_width=True, height=400)

"""
Spending page — QuickBooks expense breakdown.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import streamlit as st
import pandas as pd

from components.charts import expense_pie, top_vendors_bar, expense_trend_weekly
from components.kpi_card import format_currency
from data import database as db

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)

st.set_page_config(page_title="Spending — BI Dashboard", layout="wide")
st.title("💳 Spending & Expenses")
st.caption("Source: QuickBooks Online")
st.divider()

# ── Data ─────────────────────────────────────────────────────────────────────
expenses = db.get_expenses(days=90)

if expenses.empty:
    st.error("No expense data. Run `python data/sync.py` first.")
    st.stop()

expenses["date"] = pd.to_datetime(expenses["date"])

# ── Filters ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    all_cats = sorted(expenses["category"].unique())
    selected_cats = st.multiselect("Category", all_cats, default=all_cats)
    date_min = expenses["date"].min().date()
    date_max = expenses["date"].max().date()
    date_range = st.date_input("Date Range", value=(date_min, date_max), min_value=date_min, max_value=date_max)

start_d, end_d = (date_range[0], date_range[1]) if len(date_range) == 2 else (date_min, date_max)
filtered = expenses[
    (expenses["category"].isin(selected_cats))
    & (expenses["date"].dt.date >= start_d)
    & (expenses["date"].dt.date <= end_d)
]

# ── KPI row ──────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total Spend (Period)", format_currency(filtered["amount"].sum()))
with k2:
    daily_avg = filtered.groupby(filtered["date"].dt.date)["amount"].sum().mean()
    st.metric("Avg Daily Spend", format_currency(daily_avg))
with k3:
    top_cat = filtered.groupby("category")["amount"].sum().idxmax()
    st.metric("Largest Category", top_cat)
with k4:
    top_vendor = filtered.groupby("vendor")["amount"].sum().idxmax()
    st.metric("Top Vendor", top_vendor)

st.divider()

# ── Charts ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(expense_pie(filtered), use_container_width=True)
with col2:
    st.plotly_chart(top_vendors_bar(filtered), use_container_width=True)

st.plotly_chart(expense_trend_weekly(filtered), use_container_width=True)

# ── Expense table ─────────────────────────────────────────────────────────────
st.subheader("Transaction Detail")
display = filtered.copy()
display["date"] = display["date"].dt.strftime("%Y-%m-%d")
display["amount"] = display["amount"].apply(lambda x: f"${x:,.2f}")
display = display[["date", "category", "vendor", "amount", "description"]].sort_values("date", ascending=False)
st.dataframe(display, use_container_width=True, height=400)

"""
Inventory / Food Cost page — Toast POS menu & cost data.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import streamlit as st
import pandas as pd

from auth import require_auth, render_sidebar_logout
from components.charts import food_cost_trend, menu_profitability_scatter, top_items_bar
from components.kpi_card import format_currency, format_pct, threshold_badge
from data import database as db

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)

THRESHOLDS = CONFIG.get("thresholds", {})
FOOD_TARGET = THRESHOLDS.get("food_cost_pct_target", 30.0)
FOOD_WARNING = THRESHOLDS.get("food_cost_pct_warning", 33.0)

st.set_page_config(page_title="Inventory — BI Dashboard", layout="wide")

user = require_auth()
render_sidebar_logout()
username = user["username"]

st.title("🥩 Inventory & Food Cost")
st.caption("Source: Toast POS")
st.divider()

# ── Data ─────────────────────────────────────────────────────────────────────
daily_sales = db.get_daily_sales(username, days=90)
menu_items = db.get_menu_items(username)

if daily_sales.empty or menu_items.empty:
    st.error("No data. Run `python data/sync.py` first.")
    st.stop()

# ── KPIs ─────────────────────────────────────────────────────────────────────
avg_food_pct = daily_sales["food_cost_pct"].mean()
total_food_cost = daily_sales["food_cost"].sum()
total_revenue = daily_sales["revenue"].sum()
actual_food_pct = total_food_cost / total_revenue * 100

theoretical_cost = menu_items["total_cost"].sum()
theoretical_revenue = menu_items["total_revenue"].sum()
theoretical_pct = theoretical_cost / theoretical_revenue * 100 if theoretical_revenue > 0 else 0
variance = actual_food_pct - theoretical_pct

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric(
        "Avg Food Cost %",
        threshold_badge(avg_food_pct, FOOD_TARGET, FOOD_WARNING),
    )
with k2:
    st.metric("Total Food Cost (90d)", format_currency(total_food_cost))
with k3:
    st.metric("Theoretical Food Cost %", f"{theoretical_pct:.1f}%")
with k4:
    delta_color = "inverse" if variance > 2 else "normal"
    st.metric("Actual vs Theoretical Variance", f"+{variance:.1f}%" if variance >= 0 else f"{variance:.1f}%",
              delta_color=delta_color)

st.divider()

# ── Charts ───────────────────────────────────────────────────────────────────
st.plotly_chart(food_cost_trend(daily_sales), use_container_width=True)

col1, col2 = st.columns(2)
with col1:
    top_cost = menu_items.nlargest(10, "total_cost")[["name", "total_cost"]].sort_values("total_cost")
    import plotly.express as px
    fig_cost = px.bar(
        top_cost,
        x="total_cost",
        y="name",
        orientation="h",
        title="Top 10 Items by Total Cost",
        labels={"total_cost": "Total Cost ($)", "name": ""},
        color_discrete_sequence=["#e74c3c"],
    )
    fig_cost.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickprefix="$", gridcolor="#2a2a2a"),
    )
    st.plotly_chart(fig_cost, use_container_width=True)

with col2:
    best_margin = menu_items.nlargest(10, "margin_pct")[["name", "margin_pct"]].sort_values("margin_pct")
    fig_margin = px.bar(
        best_margin,
        x="margin_pct",
        y="name",
        orientation="h",
        title="Top 10 Items by Margin %",
        labels={"margin_pct": "Margin %", "name": ""},
        color_discrete_sequence=["#2ecc71"],
    )
    fig_margin.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(ticksuffix="%", gridcolor="#2a2a2a"),
    )
    st.plotly_chart(fig_margin, use_container_width=True)

st.plotly_chart(menu_profitability_scatter(menu_items), use_container_width=True)

# ── Menu table ─────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Menu Item Profitability Detail")

with st.sidebar:
    st.header("Filters")
    categories = sorted(menu_items["category"].unique())
    selected_cats = st.multiselect("Category", categories, default=categories)

display = menu_items[menu_items["category"].isin(selected_cats)].copy()
display["price"] = display["price"].apply(lambda x: f"${x:.2f}")
display["cost"] = display["cost"].apply(lambda x: f"${x:.2f}")
display["total_revenue"] = display["total_revenue"].apply(lambda x: f"${x:,.0f}")
display["total_cost"] = display["total_cost"].apply(lambda x: f"${x:,.0f}")
display["gross_profit"] = display["gross_profit"].apply(lambda x: f"${x:,.0f}")
display["margin_pct"] = display["margin_pct"].apply(lambda x: f"{x:.1f}%")
st.dataframe(
    display[["name", "category", "price", "cost", "margin_pct", "quantity_sold", "total_revenue", "total_cost", "gross_profit"]],
    use_container_width=True,
    height=450,
)

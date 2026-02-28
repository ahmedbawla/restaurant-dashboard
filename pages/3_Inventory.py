"""
Inventory & Food Cost — Toast POS menu and cost data.
"""

import json
from pathlib import Path

import plotly.express as px
import streamlit as st

from components.charts import food_cost_trend, menu_profitability_scatter, top_items_bar
from components.kpi_card import format_currency, format_pct, threshold_badge
from components.theme import page_header
from data import database as db

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)
THRESHOLDS   = CONFIG.get("thresholds", {})
FOOD_TARGET  = THRESHOLDS.get("food_cost_pct_target",  30.0)
FOOD_WARNING = THRESHOLDS.get("food_cost_pct_warning", 33.0)

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "🥩 Inventory & Food Cost",
    subtitle="Food cost analysis and menu profitability sourced from Toast POS.",
    eyebrow="Cost of Goods Analysis",
)
st.divider()

# ── Data ─────────────────────────────────────────────────────────────────────
daily_sales = db.get_daily_sales(username, start_date=start_date, end_date=end_date)
menu_items  = db.get_menu_items(username)

if daily_sales.empty or menu_items.empty:
    st.warning("No data found for the selected period.")
    st.stop()

# ── Computed metrics ──────────────────────────────────────────────────────────
avg_food_pct    = daily_sales["food_cost_pct"].mean()
total_food_cost = daily_sales["food_cost"].sum()
total_revenue   = daily_sales["revenue"].sum()
actual_food_pct = total_food_cost / total_revenue * 100 if total_revenue else 0.0

theoretical_cost    = menu_items["total_cost"].sum()
theoretical_revenue = menu_items["total_revenue"].sum()
theoretical_pct     = theoretical_cost / theoretical_revenue * 100 if theoretical_revenue else 0.0
variance            = actual_food_pct - theoretical_pct

# ── KPI row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Avg. Food Cost % (Period)",
              threshold_badge(avg_food_pct, FOOD_TARGET, FOOD_WARNING),
              help=f"Target: ≤{FOOD_TARGET:.0f}%  |  Warning: >{FOOD_WARNING:.0f}%")
with k2:
    st.metric("Total Food Cost (Period)", format_currency(total_food_cost))
with k3:
    st.metric("Theoretical Food Cost %", f"{theoretical_pct:.1f}%",
              help="Ideal food cost based on menu costs and quantities sold.")
with k4:
    delta_color = "inverse" if variance > 2 else "normal"
    st.metric("Actual vs. Theoretical Variance", f"{variance:+.1f}%",
              delta_color=delta_color,
              help="Positive variance indicates waste, theft, or portioning issues.")

st.divider()

# ── Food cost trend ───────────────────────────────────────────────────────────
st.plotly_chart(food_cost_trend(daily_sales), use_container_width=True)

# ── Top items by cost & margin ────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    top_cost = menu_items.nlargest(10, "total_cost")[["name","total_cost"]].sort_values("total_cost")
    fig = px.bar(top_cost, x="total_cost", y="name", orientation="h",
                 title="Top 10 Items by Total Cost",
                 labels={"total_cost": "Total Cost ($)", "name": ""},
                 color_discrete_sequence=["#E74C3C"])
    fig.update_layout(margin=dict(l=0,r=0,t=40,b=0), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(tickprefix="$", gridcolor="rgba(128,128,128,0.2)"))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    best = menu_items.nlargest(10, "margin_pct")[["name","margin_pct"]].sort_values("margin_pct")
    fig2 = px.bar(best, x="margin_pct", y="name", orientation="h",
                  title="Top 10 Items by Gross Margin %",
                  labels={"margin_pct": "Margin %", "name": ""},
                  color_discrete_sequence=["#27AE60"])
    fig2.update_layout(margin=dict(l=0,r=0,t=40,b=0), plot_bgcolor="rgba(0,0,0,0)",
                       paper_bgcolor="rgba(0,0,0,0)",
                       xaxis=dict(ticksuffix="%", gridcolor="rgba(128,128,128,0.2)"))
    st.plotly_chart(fig2, use_container_width=True)

st.plotly_chart(menu_profitability_scatter(menu_items), use_container_width=True)

# ── Menu item detail ──────────────────────────────────────────────────────────
st.divider()
st.subheader("Menu Item Profitability Detail")

with st.sidebar:
    st.header("Filters")
    categories    = sorted(menu_items["category"].unique())
    selected_cats = st.multiselect("Category", categories, default=categories)

display = menu_items[menu_items["category"].isin(selected_cats)].copy()
display["price"]         = display["price"].apply(lambda x: f"${x:.2f}")
display["cost"]          = display["cost"].apply(lambda x: f"${x:.2f}")
display["total_revenue"] = display["total_revenue"].apply(lambda x: f"${x:,.0f}")
display["total_cost"]    = display["total_cost"].apply(lambda x: f"${x:,.0f}")
display["gross_profit"]  = display["gross_profit"].apply(lambda x: f"${x:,.0f}")
display["margin_pct"]    = display["margin_pct"].apply(lambda x: f"{x:.1f}%")
display = display[["name","category","price","cost","margin_pct","quantity_sold","total_revenue","total_cost","gross_profit"]]
display.columns = ["Item","Category","Price","Unit Cost","Margin %","Qty Sold","Total Revenue","Total Cost","Gross Profit"]
st.dataframe(display, use_container_width=True, height=450, hide_index=True)

st.divider()
st.caption("🔒 Confidential  ·  For authorised recipients only")

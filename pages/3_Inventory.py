"""
Inventory & Food Cost — Toast POS menu and cost data.
"""

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from components.charts import food_cost_trend, menu_profitability_scatter, menu_engineering_quadrant
from components.kpi_card import format_currency, threshold_badge
from components.theme import page_header, section_header
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

# ── Data ─────────────────────────────────────────────────────────────────────
daily_sales = db.get_daily_sales(username, start_date=start_date, end_date=end_date)
menu_items  = db.get_menu_items(username)

if daily_sales.empty or menu_items.empty:
    st.warning("No data found for the selected period.")
    st.stop()

# ── Computed metrics ──────────────────────────────────────────────────────────
avg_food_pct        = daily_sales["food_cost_pct"].mean()
total_food_cost     = daily_sales["food_cost"].sum()
total_revenue       = daily_sales["revenue"].sum()
actual_food_pct     = total_food_cost / total_revenue * 100 if total_revenue else 0.0
theoretical_cost    = menu_items["total_cost"].sum()
theoretical_revenue = menu_items["total_revenue"].sum()
theoretical_pct     = theoretical_cost / theoretical_revenue * 100 if theoretical_revenue else 0.0
variance            = actual_food_pct - theoretical_pct

# ── Variance alert banner ─────────────────────────────────────────────────────
if variance > 4:
    st.error(
        f"**High Variance Alert** — Actual food cost is **{variance:+.1f}%** above theoretical. "
        "This may indicate waste, spoilage, theft, or portioning inconsistencies. Immediate review recommended."
    )
elif variance > 2:
    st.warning(
        f"**Variance Notice** — Actual food cost is **{variance:+.1f}%** above theoretical. "
        "Monitor portioning and receiving accuracy."
    )

# ── KPI strip ─────────────────────────────────────────────────────────────────
section_header("Cost Overview", help="Food/beverage cost metrics for the selected period. Variance = actual food cost % minus the theoretical cost % based on menu item costs × quantities sold.")
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Avg. Food Cost %",
              threshold_badge(avg_food_pct, FOOD_TARGET, FOOD_WARNING),
              help=f"Target ≤{FOOD_TARGET:.0f}%  |  Warning >{FOOD_WARNING:.0f}%")
with k2:
    st.metric("Total Food Cost",     format_currency(total_food_cost))
with k3:
    st.metric("Total Revenue",       format_currency(total_revenue))
with k4:
    st.metric("Theoretical Cost %",  f"{theoretical_pct:.1f}%",
              help="Ideal food cost based on menu item costs × quantity sold.")
with k5:
    delta_color = "inverse" if variance > 2 else "normal"
    st.metric("Actual vs Theoretical", f"{variance:+.1f}%",
              delta_color=delta_color,
              help="Positive = waste/theft/portioning issues.")

st.divider()

# ── Food cost trend ───────────────────────────────────────────────────────────
section_header("Food Cost % Trend", help="Daily food/beverage cost as a % of revenue. A rising trend may indicate waste, price increases from suppliers, or portioning issues.")
st.plotly_chart(food_cost_trend(daily_sales), use_container_width=True)

st.divider()

# ── Menu Engineering Matrix ───────────────────────────────────────────────────
section_header("Menu Engineering Matrix", help="Each item is plotted by popularity (units sold) and profitability (gross margin %). Stars = promote these. Plowhorses = high volume but low margin — consider price increase. Puzzles = high margin but low volume — improve visibility. Dogs = low on both — candidates for removal.")
st.caption(
    "**Stars** = high margin + high popularity  ·  "
    "**Plowhorses** = high popularity, low margin  ·  "
    "**Puzzles** = high margin, low popularity  ·  "
    "**Dogs** = low margin + low popularity"
)
st.plotly_chart(menu_engineering_quadrant(menu_items), use_container_width=True)

st.divider()

# ── Profitability scatter & top cost items ────────────────────────────────────
section_header("Item-Level Profitability", help="Left: items with the highest total cost to produce — these drive your COGS the most. Right: items with the best gross margin % — your most profitable items per sale.")
col1, col2 = st.columns(2)

_LAYOUT_MINI = dict(
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="rgba(240,242,246,0.7)"),
    margin=dict(l=0, r=0, t=38, b=0),
    title_font=dict(size=13, color="rgba(240,242,246,0.6)"),
)
_GRID_MINI = dict(gridcolor="rgba(255,255,255,0.06)")

with col1:
    top_cost = menu_items.nlargest(10, "total_cost")[["name","total_cost"]].sort_values("total_cost")
    fig = go.Figure(go.Bar(
        x=top_cost["total_cost"], y=top_cost["name"],
        orientation="h", marker_color="#e74c3c", marker_line_width=0,
    ))
    fig.update_layout(title="Top 10 Items by Total Cost",
                      xaxis=dict(tickprefix="$", **_GRID_MINI), **_LAYOUT_MINI)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    best = menu_items.nlargest(10, "margin_pct")[["name","margin_pct"]].sort_values("margin_pct")
    fig2 = go.Figure(go.Bar(
        x=best["margin_pct"], y=best["name"],
        orientation="h", marker_color="#27ae60", marker_line_width=0,
    ))
    fig2.update_layout(title="Top 10 Items by Gross Margin %",
                       xaxis=dict(ticksuffix="%", **_GRID_MINI), **_LAYOUT_MINI)
    st.plotly_chart(fig2, use_container_width=True)

st.plotly_chart(menu_profitability_scatter(menu_items), use_container_width=True)

# ── Sidebar filter ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    categories    = sorted(menu_items["category"].unique())
    selected_cats = st.multiselect("Category", categories, default=categories)

# ── Menu detail table ─────────────────────────────────────────────────────────
st.divider()
section_header("Menu Item Profitability Detail", help="Full breakdown per menu item: unit price, unit cost, gross margin %, total quantity sold, and total revenue and profit generated in the period.")
display = menu_items[menu_items["category"].isin(selected_cats)].copy()
display["price"]         = display["price"].apply(lambda x: f"${x:.2f}")
display["cost"]          = display["cost"].apply(lambda x: f"${x:.2f}")
display["total_revenue"] = display["total_revenue"].apply(lambda x: f"${x:,.0f}")
display["total_cost"]    = display["total_cost"].apply(lambda x: f"${x:,.0f}")
display["gross_profit"]  = display["gross_profit"].apply(lambda x: f"${x:,.0f}")
display["margin_pct"]    = display["margin_pct"].apply(lambda x: f"{x:.1f}%")
display = display[["name","category","price","cost","margin_pct","quantity_sold",
                    "total_revenue","total_cost","gross_profit"]]
display.columns = ["Item","Category","Price","Unit Cost","Margin %","Qty Sold",
                   "Total Revenue","Total Cost","Gross Profit"]
st.dataframe(display, use_container_width=True, height=420, hide_index=True)

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

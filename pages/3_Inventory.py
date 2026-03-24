"""
Menu Mix & Sales Analytics — item-level performance from Toast POS data.
"""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.theme import page_header, section_header
from components.kpi_card import format_currency
from data import database as db

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "🥩 Menu Mix & Item Performance",
    subtitle="Item-level sales analytics sourced from Toast POS.",
    eyebrow="Menu Analytics",
    start_date=start_date,
    end_date=end_date,
)

# ── Data ──────────────────────────────────────────────────────────────────────
menu_items = db.get_menu_items(username)

# ── Toast menu upload ─────────────────────────────────────────────────────────
def _render_toast_menu_upload():
    from utils.csv_importer import parse_item_selections
    st.markdown("**Upload Toast Item Selections CSV**")
    st.caption(
        "In Toast: Reports → Menu → Item Selections → Export → 'All levels.csv'. "
        "Re-upload at any time to refresh item data."
    )
    uploaded = st.file_uploader(
        "Item Selections CSV / Excel", type=["csv", "xlsx"],
        key="menu_upload", label_visibility="collapsed",
    )
    if uploaded:
        try:
            df = parse_item_selections(uploaded.getvalue(), uploaded.name)
            st.success(f"Parsed {len(df)} menu items across {df['category'].nunique()} categories.")
            if st.button("Import to Dashboard", key="menu_import_btn", type="primary"):
                rows = db.merge_df(df, "menu_items", username, date_col=None)
                db.update_user(username, use_simulated_data=False)
                st.session_state["user"] = db.get_user(username)
                st.cache_data.clear()
                st.success(f"Imported {rows} items. Refreshing…")
                st.rerun()
        except Exception as e:
            st.error(f"Could not parse file: {e}")

if menu_items.empty:
    st.info("No menu data yet. Upload a Toast Item Selections export to get started.")
    _render_toast_menu_upload()
    st.stop()

with st.expander("Update Toast Menu Data", expanded=False):
    _render_toast_menu_upload()

# ── KPI strip ─────────────────────────────────────────────────────────────────
section_header("Menu Overview")

total_items    = len(menu_items)
total_qty      = menu_items["quantity_sold"].sum()
total_revenue  = menu_items["total_revenue"].sum()
avg_item_price = menu_items["price"].mean()
top_category   = (
    menu_items.groupby("category")["total_revenue"].sum().idxmax()
    if not menu_items.empty else "—"
)

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Total Menu Items", f"{total_items:,}")
with k2:
    st.metric("Total Qty Sold", f"{total_qty:,}")
with k3:
    st.metric("Total Menu Revenue", format_currency(total_revenue))
with k4:
    st.metric("Avg Menu Price", format_currency(avg_item_price))
with k5:
    st.metric("Top Category", top_category)

st.divider()

# ── Revenue & quantity by category ────────────────────────────────────────────
section_header("Sales by Category", help="Revenue and quantity sold broken down by menu category.")

cat_df = (
    menu_items.groupby("category", as_index=False)
    .agg(total_revenue=("total_revenue", "sum"), quantity_sold=("quantity_sold", "sum"))
    .sort_values("total_revenue", ascending=False)
)
cat_df["revenue_pct"] = (cat_df["total_revenue"] / cat_df["total_revenue"].sum() * 100).round(1)

col_bar, col_pie = st.columns(2)

_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="rgba(240,242,246,0.75)"),
    margin=dict(l=0, r=0, t=38, b=0),
    title_font=dict(size=13, color="rgba(240,242,246,0.6)"),
)

with col_bar:
    fig = px.bar(
        cat_df.sort_values("total_revenue"),
        x="total_revenue", y="category", orientation="h",
        color="total_revenue",
        color_continuous_scale=["#3a1a0a", "#FF6B35"],
        labels={"total_revenue": "Revenue", "category": ""},
        title="Revenue by Category",
        text=cat_df.sort_values("total_revenue")["revenue_pct"].apply(lambda v: f"{v:.1f}%"),
    )
    fig.update_traces(textposition="outside")
    fig.update_coloraxes(showscale=False)
    fig.update_xaxes(tickprefix="$", gridcolor="rgba(255,255,255,0.06)")
    fig.update_layout(**_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

with col_pie:
    fig2 = px.pie(
        cat_df, values="total_revenue", names="category",
        title="Revenue Share by Category",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig2.update_traces(textposition="inside", textinfo="percent+label")
    fig2.update_layout(**_LAYOUT)
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Top items by revenue & quantity ──────────────────────────────────────────
section_header("Top Performers", help="Items ranked by total revenue (left) and quantity sold (right).")

col_rev, col_qty = st.columns(2)

_MINI = dict(
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="rgba(240,242,246,0.7)"),
    margin=dict(l=0, r=0, t=38, b=0),
    title_font=dict(size=13, color="rgba(240,242,246,0.6)"),
)
_GRID = dict(gridcolor="rgba(255,255,255,0.06)")

with col_rev:
    top_rev = menu_items.nlargest(10, "total_revenue")[["name", "total_revenue"]].sort_values("total_revenue")
    fig3 = go.Figure(go.Bar(
        x=top_rev["total_revenue"], y=top_rev["name"],
        orientation="h", marker_color="#FF6B35", marker_line_width=0,
    ))
    fig3.update_layout(title="Top 10 by Revenue", xaxis=dict(tickprefix="$", **_GRID), **_MINI)
    st.plotly_chart(fig3, use_container_width=True)

with col_qty:
    top_qty = menu_items.nlargest(10, "quantity_sold")[["name", "quantity_sold"]].sort_values("quantity_sold")
    fig4 = go.Figure(go.Bar(
        x=top_qty["quantity_sold"], y=top_qty["name"],
        orientation="h", marker_color="#27ae60", marker_line_width=0,
    ))
    fig4.update_layout(title="Top 10 by Qty Sold", xaxis=dict(**_GRID), **_MINI)
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── Category performance table ─────────────────────────────────────────────────
section_header("Category Summary", help="Aggregate performance per category — items, revenue, and quantity sold.")

cat_summary = (
    menu_items.groupby("category", as_index=False)
    .agg(
        items=("name", "count"),
        qty_sold=("quantity_sold", "sum"),
        total_revenue=("total_revenue", "sum"),
        avg_price=("price", "mean"),
    )
    .sort_values("total_revenue", ascending=False)
)
cat_summary["revenue_share"] = (cat_summary["total_revenue"] / cat_summary["total_revenue"].sum() * 100).round(1)
cat_display = cat_summary.copy()
cat_display["total_revenue"] = cat_display["total_revenue"].apply(lambda x: f"${x:,.0f}")
cat_display["avg_price"]     = cat_display["avg_price"].apply(lambda x: f"${x:.2f}")
cat_display["revenue_share"] = cat_display["revenue_share"].apply(lambda x: f"{x:.1f}%")
cat_display["qty_sold"]      = cat_display["qty_sold"].apply(lambda x: f"{x:,}")
cat_display.columns = ["Category", "# Items", "Qty Sold", "Total Revenue", "Avg Price", "Revenue Share"]
st.dataframe(cat_display, use_container_width=True, hide_index=True)

st.divider()

# ── Pareto / concentration ─────────────────────────────────────────────────────
section_header("Revenue Concentration", help="Cumulative revenue share by item — shows how many items drive most of your sales.")

pareto = menu_items[["name", "total_revenue"]].sort_values("total_revenue", ascending=False).reset_index(drop=True)
pareto["cumulative_pct"] = (pareto["total_revenue"].cumsum() / pareto["total_revenue"].sum() * 100).round(1)
pareto["rank"] = range(1, len(pareto) + 1)

fig5 = go.Figure()
fig5.add_trace(go.Bar(
    x=pareto["rank"], y=pareto["total_revenue"],
    name="Item Revenue", marker_color="#3498db", marker_line_width=0,
))
fig5.add_trace(go.Scatter(
    x=pareto["rank"], y=pareto["cumulative_pct"],
    name="Cumulative %", yaxis="y2",
    line=dict(color="#FF6B35", width=2), mode="lines",
))
fig5.update_layout(
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="rgba(240,242,246,0.75)"),
    margin=dict(l=0, r=0, t=20, b=0),
    legend=dict(orientation="h", y=1.08),
    xaxis=dict(title="Item Rank", gridcolor="rgba(255,255,255,0.06)"),
    yaxis=dict(title="Revenue ($)", tickprefix="$", gridcolor="rgba(255,255,255,0.06)"),
    yaxis2=dict(title="Cumulative %", ticksuffix="%", overlaying="y", side="right",
                range=[0, 105], showgrid=False),
    shapes=[dict(type="line", x0=0, x1=len(pareto), y0=80, y1=80,
                 yref="y2", line=dict(color="rgba(255,107,53,0.4)", width=1, dash="dash"))],
)
st.plotly_chart(fig5, use_container_width=True)
st.caption("Dashed line = 80% revenue threshold (Pareto principle).")

st.divider()

# ── Sidebar filter ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    categories    = sorted(menu_items["category"].unique())
    selected_cats = st.multiselect("Category", categories, default=categories)

# ── Full item detail table ─────────────────────────────────────────────────────
section_header("Item Detail", help="Full item list — filter by category in the sidebar. Click column headers to sort.")

display = menu_items[menu_items["category"].isin(selected_cats)].copy()
display["revenue_rank"] = display["total_revenue"].rank(ascending=False, method="min").astype(int)
display["qty_rank"]     = display["quantity_sold"].rank(ascending=False, method="min").astype(int)
display["rev_share"]    = (display["total_revenue"] / menu_items["total_revenue"].sum() * 100).round(2)

display_fmt = display[["name", "category", "price", "quantity_sold", "total_revenue", "rev_share", "revenue_rank"]].copy()
display_fmt["price"]         = display_fmt["price"].apply(lambda x: f"${x:.2f}")
display_fmt["total_revenue"] = display_fmt["total_revenue"].apply(lambda x: f"${x:,.0f}")
display_fmt["rev_share"]     = display_fmt["rev_share"].apply(lambda x: f"{x:.2f}%")
display_fmt["quantity_sold"] = display_fmt["quantity_sold"].apply(lambda x: f"{x:,}")
display_fmt.columns = ["Item", "Category", "Price", "Qty Sold", "Total Revenue", "Rev Share", "Rev Rank"]
display_fmt = display_fmt.sort_values("Rev Rank")

st.dataframe(display_fmt, use_container_width=True, height=480, hide_index=True)

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

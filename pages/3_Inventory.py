"""
Menu Mix & Sales Analytics — item-level performance from Toast POS data.
"""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.theme import page_header, section_header
from components.kpi_card import format_currency
from data import database as db

user     = st.session_state["user"]
username = user["username"]

page_header(
    "🥩 Menu Mix & Item Performance",
    subtitle="Item-level sales analytics sourced from Toast POS.",
    eyebrow="Menu Analytics",
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

# ── Menu Engineering Matrix (test account only) ───────────────────────────────
if username == "test":
    section_header(
        "Menu Engineering Matrix",
        help=(
            "Classifies every menu item into one of four quadrants based on "
            "**popularity** (qty sold vs average) and **profitability** (margin % vs average). "
            "**Stars** → high popularity + high margin: promote and protect. "
            "**Plowhorses** → high popularity + low margin: reprice or reduce cost. "
            "**Puzzles** → low popularity + high margin: improve visibility or placement. "
            "**Dogs** → low popularity + low margin: consider removing from menu."
        ),
    )

    _me = menu_items.copy()

    # Require at least margin_pct and quantity_sold columns
    if "margin_pct" in _me.columns and "quantity_sold" in _me.columns:
        # Use median as the cut-off (more robust than mean for skewed menus)
        _qty_median    = _me["quantity_sold"].median()
        _margin_median = _me["margin_pct"].median()

        def _classify(row):
            high_pop    = row["quantity_sold"] >= _qty_median
            high_margin = row["margin_pct"]    >= _margin_median
            if high_pop and high_margin:
                return "⭐ Star"
            elif high_pop and not high_margin:
                return "🐎 Plowhorse"
            elif not high_pop and high_margin:
                return "🧩 Puzzle"
            else:
                return "🐶 Dog"

        _me["quadrant"] = _me.apply(_classify, axis=1)

        _QUAD_COLORS = {
            "⭐ Star":       "#2ecc71",   # green
            "🐎 Plowhorse":  "#D4A84B",   # gold
            "🧩 Puzzle":     "#5b9bd5",   # blue
            "🐶 Dog":        "#e74c3c",   # red
        }
        _QUAD_COLOR_LIST = [_QUAD_COLORS.get(q, "#888") for q in _me["quadrant"]]

        # Summary counts
        _quad_counts = _me["quadrant"].value_counts()
        qc1, qc2, qc3, qc4 = st.columns(4)
        for _col, _label in zip(
            [qc1, qc2, qc3, qc4],
            ["⭐ Star", "🐎 Plowhorse", "🧩 Puzzle", "🐶 Dog"],
        ):
            _count    = int(_quad_counts.get(_label, 0))
            _quad_rev = _me[_me["quadrant"] == _label]["total_revenue"].sum()
            _col.metric(
                _label,
                f"{_count} items",
                delta=format_currency(_quad_rev),
                delta_color="off",
            )

        # Scatter plot: qty sold vs margin %
        _LAYOUT_ME = dict(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="rgba(240,242,246,0.75)", size=11),
            title_font=dict(size=13, color="rgba(240,242,246,0.6)"),
            margin=dict(l=0, r=0, t=48, b=0),
            legend=dict(bgcolor="rgba(0,0,0,0)",
                        bordercolor="rgba(255,255,255,0.1)", borderwidth=1),
        )
        _GRID_ME = dict(gridcolor="rgba(255,255,255,0.06)",
                        zerolinecolor="rgba(255,255,255,0.1)")

        fig_me = go.Figure()
        for _q, _color in _QUAD_COLORS.items():
            _subset = _me[_me["quadrant"] == _q]
            if _subset.empty:
                continue
            fig_me.add_trace(go.Scatter(
                x=_subset["quantity_sold"],
                y=_subset["margin_pct"],
                mode="markers",
                name=_q,
                marker=dict(
                    color=_color,
                    size=_subset["total_revenue"].apply(
                        lambda v: max(8, min(30, v / (_me["total_revenue"].max() or 1) * 30))
                    ),
                    opacity=0.82,
                    line=dict(width=0.5, color="rgba(0,0,0,0.3)"),
                ),
                text=_subset["name"],
                customdata=_subset[["category", "price", "total_revenue"]].values,
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Category: %{customdata[0]}<br>"
                    "Price: $%{customdata[1]:.2f}<br>"
                    "Qty Sold: %{x:,}<br>"
                    "Margin: %{y:.1f}%<br>"
                    "Revenue: $%{customdata[2]:,.0f}"
                    "<extra></extra>"
                ),
            ))

        # Crosshair lines at medians
        fig_me.add_vline(x=_qty_median, line_dash="dash",
                         line_color="rgba(255,255,255,0.25)",
                         annotation_text=f"Median qty: {_qty_median:,.0f}",
                         annotation_font_color="rgba(240,242,246,0.5)")
        fig_me.add_hline(y=_margin_median, line_dash="dash",
                         line_color="rgba(255,255,255,0.25)",
                         annotation_text=f"Median margin: {_margin_median:.1f}%",
                         annotation_font_color="rgba(240,242,246,0.5)")

        fig_me.update_layout(
            title="Popularity vs Profitability  (bubble size = total revenue)",
            xaxis=dict(title="Quantity Sold", **_GRID_ME),
            yaxis=dict(title="Margin %", ticksuffix="%", **_GRID_ME),
            **_LAYOUT_ME,
        )
        st.plotly_chart(fig_me, use_container_width=True)

        # Actionable insight callout
        _stars      = _me[_me["quadrant"] == "⭐ Star"]
        _dogs       = _me[_me["quadrant"] == "🐶 Dog"]
        _plowhorses = _me[_me["quadrant"] == "🐎 Plowhorse"]
        _puzzles    = _me[_me["quadrant"] == "🧩 Puzzle"]

        _insight_rows = []
        if not _stars.empty:
            _top_star = _stars.loc[_stars["total_revenue"].idxmax(), "name"]
            _insight_rows.append(
                ("⭐", f"<strong>{len(_stars)} Star item{'s' if len(_stars) != 1 else ''}</strong> — "
                 f"protect these on the menu. Top star: <strong>{_top_star}</strong> "
                 f"({format_currency(_stars['total_revenue'].max())} revenue).")
            )
        if not _plowhorses.empty:
            _top_ph = _plowhorses.loc[_plowhorses["quantity_sold"].idxmax(), "name"]
            _insight_rows.append(
                ("🐎", f"<strong>{len(_plowhorses)} Plowhorse item{'s' if len(_plowhorses) != 1 else ''}</strong> — "
                 f"popular but low margin. Consider raising the price of "
                 f"<strong>{_top_ph}</strong> (your highest-volume plowhorse) by $0.50–$1 "
                 f"or reducing its ingredient cost.")
            )
        if not _puzzles.empty:
            _top_pz = _puzzles.loc[_puzzles["margin_pct"].idxmax(), "name"]
            _insight_rows.append(
                ("🧩", f"<strong>{len(_puzzles)} Puzzle item{'s' if len(_puzzles) != 1 else ''}</strong> — "
                 f"high margin but low volume. Move <strong>{_top_pz}</strong> to a "
                 f"more prominent menu position or feature it as a daily special.")
            )
        if not _dogs.empty:
            _insight_rows.append(
                ("🐶", f"<strong>{len(_dogs)} Dog item{'s' if len(_dogs) != 1 else ''}</strong> — "
                 f"low popularity and low margin. Evaluate whether each earns its place "
                 f"on the menu or can be removed to simplify operations.")
            )

        if _insight_rows:
            rows_html = "".join(
                f"<div style='margin-bottom:0.4rem;'>"
                f"<span style='margin-right:0.45rem;font-size:1rem;'>{icon}</span>{text}</div>"
                for icon, text in _insight_rows
            )
            st.markdown(
                f"<div style='background:rgba(212,168,75,0.07);"
                f"border:1px solid rgba(212,168,75,0.22);border-radius:10px;"
                f"padding:0.85rem 1.15rem;margin:0.5rem 0 1rem 0;font-size:0.87rem;"
                f"color:rgba(240,242,246,0.85);line-height:1.75;'>{rows_html}</div>",
                unsafe_allow_html=True,
            )

        # Per-quadrant detail tables
        with st.expander("View full quadrant breakdown →", expanded=False):
            for _q, _color in _QUAD_COLORS.items():
                _subset = _me[_me["quadrant"] == _q].copy()
                if _subset.empty:
                    continue
                _subset = _subset.sort_values("total_revenue", ascending=False)
                _disp = _subset[["name", "category", "price", "quantity_sold",
                                  "margin_pct", "total_revenue"]].copy()
                _disp["price"]         = _disp["price"].apply(lambda x: f"${x:.2f}")
                _disp["total_revenue"] = _disp["total_revenue"].apply(lambda x: f"${x:,.0f}")
                _disp["margin_pct"]    = _disp["margin_pct"].apply(lambda x: f"{x:.1f}%")
                _disp["quantity_sold"] = _disp["quantity_sold"].apply(lambda x: f"{x:,}")
                _disp.columns = ["Item", "Category", "Price", "Qty Sold", "Margin %", "Revenue"]
                st.markdown(f"**{_q}** — {len(_subset)} item{'s' if len(_subset) != 1 else ''}")
                st.dataframe(_disp, use_container_width=True, hide_index=True)
    else:
        st.info(
            "Menu Engineering Matrix requires **margin_pct** and **quantity_sold** columns. "
            "Upload a Toast Item Selections export to enable this analysis."
        )

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

"""
Reusable Plotly chart builders.
All functions return a plotly.graph_objects.Figure — callers use st.plotly_chart().
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


_BRAND_COLOR = "#FF6B35"        # vibrant orange — unified theme accent
_PALETTE = px.colors.qualitative.Set2

# Shared layout defaults for a clean dark look
_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="rgba(240,242,246,0.75)", size=12),
    title_font=dict(size=13, color="rgba(240,242,246,0.6)", family="sans-serif"),
    margin=dict(l=0, r=0, t=38, b=0),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(255,255,255,0.08)",
        borderwidth=1,
    ),
)
_GRID = dict(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.08)")


def revenue_trend(df: pd.DataFrame, days: int = 30) -> go.Figure:
    """Area chart of daily revenue with 7-day rolling average overlay."""
    data = df.tail(days).copy()
    data["date"] = pd.to_datetime(data["date"])
    data["rolling_7"] = data["revenue"].rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["date"], y=data["revenue"],
        name="Daily Revenue",
        fill="tozeroy",
        line=dict(color=_BRAND_COLOR, width=2),
        fillcolor="rgba(255,107,53,0.10)",
    ))
    fig.add_trace(go.Scatter(
        x=data["date"], y=data["rolling_7"],
        name="7-Day Avg",
        line=dict(color="#3498db", width=2, dash="dot"),
    ))
    fig.update_layout(
        title=f"Daily Revenue — Last {days} Days",
        yaxis=dict(tickprefix="$", **_GRID),
        xaxis=dict(**_GRID),
        **_LAYOUT,
    )
    return fig


def expense_pie(df: pd.DataFrame) -> go.Figure:
    """Donut chart of expenses by category."""
    cat_totals = df.groupby("category")["amount"].sum().reset_index()
    fig = px.pie(
        cat_totals,
        names="category",
        values="amount",
        title="Expense Breakdown by Category",
        color_discrete_sequence=_PALETTE,
        hole=0.5,
    )
    fig.update_traces(
        textposition="outside",
        textinfo="percent+label",
        marker=dict(line=dict(color="#0f1117", width=2)),
    )
    fig.update_layout(**_LAYOUT)
    return fig


def top_vendors_bar(df: pd.DataFrame, n: int = 10) -> go.Figure:
    """Horizontal bar — top N vendors by total spend."""
    vendor_totals = (
        df.groupby("vendor")["amount"].sum()
        .sort_values(ascending=False)
        .head(n)
        .reset_index()
    )
    fig = px.bar(
        vendor_totals.sort_values("amount"),
        x="amount",
        y="vendor",
        orientation="h",
        title=f"Top {n} Vendors by Spend",
        labels={"amount": "Total Spend ($)", "vendor": ""},
        color_discrete_sequence=[_BRAND_COLOR],
    )
    fig.update_traces(marker_line_width=0)
    fig.update_layout(xaxis=dict(tickprefix="$", **_GRID), **_LAYOUT)
    return fig


def expense_trend_weekly(df: pd.DataFrame) -> go.Figure:
    """Bar chart of weekly expenses with MoM comparison line."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.to_period("W").dt.start_time
    weekly = df.groupby("week")["amount"].sum().reset_index()
    weekly["rolling_4w"] = weekly["amount"].rolling(4, min_periods=1).mean()
    weekly["week_label"] = weekly["week"].dt.strftime("%b %d")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=weekly["week_label"], y=weekly["amount"],
        name="Weekly Spend", marker_color="#5b9bd5", marker_line_width=0,
    ))
    fig.add_trace(go.Scatter(
        x=weekly["week_label"], y=weekly["rolling_4w"],
        name="4-Wk Avg", line=dict(color=_BRAND_COLOR, width=2, dash="dot"),
    ))
    fig.update_layout(
        title="Weekly Expense Trend",
        yaxis=dict(tickprefix="$", **_GRID),
        xaxis=dict(title=""),
        barmode="group",
        **_LAYOUT,
    )
    return fig


def labor_cost_gauge(labor_pct: float, target: float = 30.0, warning: float = 33.0) -> go.Figure:
    """Gauge chart for labor cost %."""
    color = "#2ecc71" if labor_pct <= target else ("#f39c12" if labor_pct <= warning else "#e74c3c")
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=labor_pct,
        number={"suffix": "%", "font": {"size": 36, "color": "#f0f2f6"}},
        delta={"reference": target, "suffix": "%"},
        title={"text": "Labor Cost %", "font": {"color": "rgba(240,242,246,0.6)", "size": 13}},
        gauge={
            "axis": {"range": [0, 50], "ticksuffix": "%",
                     "tickfont": {"color": "rgba(240,242,246,0.5)"}},
            "bar": {"color": color},
            "bgcolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0, target],  "color": "rgba(46,204,113,0.12)"},
                {"range": [target, warning], "color": "rgba(243,156,18,0.12)"},
                {"range": [warning, 50], "color": "rgba(231,76,60,0.12)"},
            ],
            "threshold": {
                "line": {"color": "rgba(255,255,255,0.4)", "width": 2},
                "thickness": 0.75,
                "value": target,
            },
        },
    ))
    fig.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        height=260,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def labor_trend(daily_labor: pd.DataFrame, daily_sales: pd.DataFrame) -> go.Figure:
    """Dual-axis: labor cost % (line) and revenue (bars) over time."""
    labor_by_day = daily_labor.groupby("date")["labor_cost"].sum().reset_index()
    merged = labor_by_day.merge(daily_sales[["date", "revenue"]], on="date", how="inner")
    merged["labor_pct"] = merged["labor_cost"] / merged["revenue"] * 100
    merged["date"] = pd.to_datetime(merged["date"])
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=merged["date"], y=merged["revenue"],
        name="Revenue", marker_color="rgba(52,152,219,0.25)",
        marker_line_width=0, yaxis="y2",
    ))
    fig.add_trace(go.Scatter(
        x=merged["date"], y=merged["labor_pct"],
        name="Labor %", line=dict(color="#e74c3c", width=2),
    ))
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(255,255,255,0.25)",
                  annotation_text="Target 30%",
                  annotation_font_color="rgba(255,255,255,0.4)")
    fig.update_layout(
        title="Labor Cost % vs. Revenue Trend",
        yaxis=dict(ticksuffix="%", **_GRID, title="Labor %"),
        yaxis2=dict(tickprefix="$", overlaying="y", side="right",
                    showgrid=False, title="Revenue"),
        **_LAYOUT,
    )
    return fig


def hours_by_dept(payroll: pd.DataFrame, week: str | None = None) -> go.Figure:
    """Grouped bar: hours and labor cost by department for a given week."""
    if week:
        data = payroll[payroll["week_start"] == week]
    else:
        latest = payroll["week_start"].max()
        data = payroll[payroll["week_start"] == latest]
    week_label = data["week_start"].iloc[0] if not data.empty else "N/A"
    dept = data.groupby("dept").agg(total_hours=("total_hours", "sum"),
                                     gross_pay=("gross_pay", "sum")).reset_index()
    fig = go.Figure()
    for i, (col, name, color) in enumerate([
        ("total_hours", "Total Hours", "#3498db"),
        ("gross_pay",   "Gross Pay ($)", _BRAND_COLOR),
    ]):
        fig.add_trace(go.Bar(
            x=dept["dept"], y=dept[col], name=name,
            marker_color=color, marker_line_width=0,
            yaxis="y" if i == 0 else "y2",
        ))
    fig.update_layout(
        title=f"Dept Hours & Pay — Week of {week_label}",
        yaxis=dict(title="Hours", **_GRID),
        yaxis2=dict(title="Pay ($)", tickprefix="$", overlaying="y",
                    side="right", showgrid=False),
        barmode="group",
        showlegend=True,
        **_LAYOUT,
    )
    return fig


def food_cost_trend(daily_sales: pd.DataFrame) -> go.Figure:
    """Area chart of food cost % with target/warning bands."""
    ds = daily_sales.copy()
    ds["date"] = pd.to_datetime(ds["date"])
    ds["rolling_7"] = ds["food_cost_pct"].rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ds["date"], y=ds["food_cost_pct"],
        name="Food Cost %", fill="tozeroy",
        line=dict(color="#3498db", width=1.5),
        fillcolor="rgba(52,152,219,0.10)",
    ))
    fig.add_trace(go.Scatter(
        x=ds["date"], y=ds["rolling_7"],
        name="7-Day Avg", line=dict(color=_BRAND_COLOR, width=2, dash="dot"),
    ))
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(46,204,113,0.6)",
                  annotation_text="Target 30%", annotation_font_color="rgba(46,204,113,0.8)")
    fig.add_hline(y=33, line_dash="dot", line_color="rgba(231,76,60,0.5)",
                  annotation_text="Warning 33%", annotation_font_color="rgba(231,76,60,0.7)")
    fig.update_layout(
        title="Food Cost % Trend",
        yaxis=dict(ticksuffix="%", range=[20, 42], **_GRID),
        xaxis=dict(**_GRID),
        **_LAYOUT,
    )
    return fig


def menu_profitability_scatter(menu_items: pd.DataFrame) -> go.Figure:
    """Scatter: price vs margin % — bubble size = quantity sold."""
    fig = px.scatter(
        menu_items,
        x="price",
        y="margin_pct",
        size="quantity_sold",
        color="category",
        hover_name="name",
        title="Menu Profitability Matrix",
        labels={"price": "Menu Price ($)", "margin_pct": "Margin %"},
        color_discrete_sequence=_PALETTE,
        size_max=55,
    )
    fig.add_hline(y=65, line_dash="dash", line_color="rgba(255,255,255,0.25)",
                  annotation_text="Target 65% margin",
                  annotation_font_color="rgba(255,255,255,0.4)")
    fig.update_layout(
        yaxis=dict(ticksuffix="%", **_GRID),
        xaxis=dict(tickprefix="$", **_GRID),
        **_LAYOUT,
    )
    return fig


def hourly_heatmap(hourly_sales: pd.DataFrame) -> go.Figure:
    """Heatmap: day-of-week × hour for covers."""
    df = hourly_sales.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["day_name"] = df["date"].dt.day_name()
    df["day_num"] = df["date"].dt.dayofweek

    pivot = df.groupby(["day_name", "day_num", "hour"])["covers"].mean().reset_index()
    pivot = pivot.groupby(["day_name", "day_num", "hour"])["covers"].mean().unstack("hour").fillna(0)
    pivot = pivot.sort_index(level="day_num")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot.index = pivot.index.get_level_values("day_name")
    pivot = pivot.reindex([d for d in day_order if d in pivot.index])

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h}:00" for h in pivot.columns],
        y=pivot.index.tolist(),
        colorscale=[[0, "#13151f"], [0.5, "#FF6B35"], [1, "#e74c3c"]],
        colorbar=dict(title="Avg Covers", tickfont=dict(color="rgba(240,242,246,0.6)")),
    ))
    fig.update_layout(
        title="Peak Hours Heatmap — Average Covers by Day & Hour",
        xaxis_title="Hour of Day",
        yaxis_title="",
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(240,242,246,0.7)"),
        margin=dict(l=0, r=0, t=38, b=0),
    )
    return fig


def top_items_bar(menu_items: pd.DataFrame, metric: str = "total_revenue", n: int = 10) -> go.Figure:
    """Horizontal bar — top N menu items by revenue or quantity."""
    is_rev = metric == "total_revenue"
    label = "Revenue ($)" if is_rev else "Quantity Sold"
    title = f"Top {n} Items by {'Revenue' if is_rev else 'Volume'}"
    data = menu_items.nlargest(n, metric).sort_values(metric)
    color = _BRAND_COLOR if is_rev else "#9b59b6"
    fig = px.bar(
        data, x=metric, y="name", orientation="h",
        title=title, labels={metric: label, "name": ""},
        color_discrete_sequence=[color],
    )
    fig.update_traces(marker_line_width=0)
    xaxis = dict(tickprefix="$", **_GRID) if is_rev else dict(**_GRID)
    fig.update_layout(xaxis=xaxis, **_LAYOUT)
    return fig


def avg_check_trend(daily_sales: pd.DataFrame) -> go.Figure:
    """Line chart of average check size with rolling average."""
    ds = daily_sales.copy()
    ds["date"] = pd.to_datetime(ds["date"])
    ds["rolling_7"] = ds["avg_check"].rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ds["date"], y=ds["avg_check"],
        name="Avg Check", line=dict(color=_BRAND_COLOR, width=2),
        fill="tozeroy", fillcolor="rgba(255,107,53,0.07)",
    ))
    fig.add_trace(go.Scatter(
        x=ds["date"], y=ds["rolling_7"],
        name="7-Day Avg", line=dict(color="#3498db", width=1.5, dash="dot"),
    ))
    fig.update_layout(
        title="Average Check Size Trend",
        yaxis=dict(tickprefix="$", **_GRID),
        xaxis=dict(**_GRID),
        **_LAYOUT,
    )
    return fig


def covers_by_dow(daily_sales: pd.DataFrame) -> go.Figure:
    """Grouped bar: avg covers AND avg revenue by day of week."""
    df = daily_sales.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["day"] = df["date"].dt.day_name()
    df["day_num"] = df["date"].dt.dayofweek
    day_avg = df.groupby(["day", "day_num"]).agg(
        covers=("covers", "mean"), revenue=("revenue", "mean")
    ).reset_index().sort_values("day_num")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=day_avg["day"], y=day_avg["covers"],
        name="Avg Covers", marker_color="#9b59b6", marker_line_width=0,
    ))
    fig.add_trace(go.Scatter(
        x=day_avg["day"], y=day_avg["revenue"],
        name="Avg Revenue ($)", line=dict(color=_BRAND_COLOR, width=2),
        yaxis="y2",
    ))
    fig.update_layout(
        title="Performance by Day of Week",
        yaxis=dict(title="Avg Covers", **_GRID),
        yaxis2=dict(title="Avg Revenue ($)", tickprefix="$",
                    overlaying="y", side="right", showgrid=False),
        **_LAYOUT,
    )
    return fig


def revenue_by_dow(daily_sales: pd.DataFrame) -> go.Figure:
    """Colored bar chart of total revenue by day of week."""
    df = daily_sales.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["day"] = df["date"].dt.day_name()
    df["day_num"] = df["date"].dt.dayofweek
    day_sum = df.groupby(["day", "day_num"])["revenue"].sum().reset_index().sort_values("day_num")
    colors = [_BRAND_COLOR if v == day_sum["revenue"].max() else "rgba(255,107,53,0.4)"
              for v in day_sum["revenue"]]
    fig = go.Figure(go.Bar(
        x=day_sum["day"], y=day_sum["revenue"],
        marker_color=colors, marker_line_width=0,
        text=day_sum["revenue"].apply(lambda x: f"${x:,.0f}"),
        textposition="outside", textfont=dict(size=11),
    ))
    fig.update_layout(
        title="Total Revenue by Day of Week",
        yaxis=dict(tickprefix="$", **_GRID),
        xaxis=dict(**_GRID),
        **_LAYOUT,
    )
    return fig


def revenue_per_cover_trend(daily_sales: pd.DataFrame) -> go.Figure:
    """Line chart of revenue per cover (spend-per-head) over time."""
    ds = daily_sales.copy()
    ds["date"] = pd.to_datetime(ds["date"])
    ds["rev_per_cover"] = ds["revenue"] / ds["covers"].replace(0, float("nan"))
    ds["rolling_7"] = ds["rev_per_cover"].rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ds["date"], y=ds["rev_per_cover"],
        name="Rev / Cover", line=dict(color="#2ecc71", width=1.5),
        fill="tozeroy", fillcolor="rgba(46,204,113,0.07)",
    ))
    fig.add_trace(go.Scatter(
        x=ds["date"], y=ds["rolling_7"],
        name="7-Day Avg", line=dict(color=_BRAND_COLOR, width=2, dash="dot"),
    ))
    fig.update_layout(
        title="Revenue per Cover (Spend-per-Head)",
        yaxis=dict(tickprefix="$", **_GRID),
        xaxis=dict(**_GRID),
        **_LAYOUT,
    )
    return fig


def labor_pct_by_dept(weekly_payroll: pd.DataFrame, daily_sales: pd.DataFrame) -> go.Figure:
    """Horizontal bar of average labor cost % per department."""
    if weekly_payroll.empty or daily_sales.empty:
        return go.Figure()
    total_rev = daily_sales["revenue"].sum()
    dept_pay = weekly_payroll.groupby("dept")["gross_pay"].sum().reset_index()
    dept_pay["labor_pct"] = dept_pay["gross_pay"] / total_rev * 100
    dept_pay = dept_pay.sort_values("labor_pct")
    colors = [
        "#27ae60" if v <= 10 else ("#f39c12" if v <= 15 else "#e74c3c")
        for v in dept_pay["labor_pct"]
    ]
    fig = go.Figure(go.Bar(
        x=dept_pay["labor_pct"], y=dept_pay["dept"],
        orientation="h", marker_color=colors, marker_line_width=0,
        text=dept_pay["labor_pct"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside",
    ))
    fig.update_layout(
        title="Labor Cost % of Revenue by Department",
        xaxis=dict(ticksuffix="%", **_GRID),
        **_LAYOUT,
    )
    return fig

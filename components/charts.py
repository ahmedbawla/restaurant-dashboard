"""
Reusable Plotly chart builders.
All functions return a plotly.graph_objects.Figure — callers use st.plotly_chart().
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


_BRAND_COLOR = "#D4A84B"        # warm gold
_PALETTE = px.colors.qualitative.Set2


def revenue_trend(df: pd.DataFrame, days: int = 30) -> go.Figure:
    """Line chart of daily revenue over `days` most recent days."""
    data = df.tail(days).copy()
    fig = px.area(
        data,
        x="date",
        y="revenue",
        title=f"Daily Revenue — Last {days} Days",
        labels={"date": "", "revenue": "Revenue ($)"},
        color_discrete_sequence=[_BRAND_COLOR],
    )
    fig.update_traces(line_width=2, fillcolor="rgba(212,168,75,0.15)")
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="$", gridcolor="#2a2a2a"),
        xaxis=dict(gridcolor="#2a2a2a"),
    )
    return fig


def expense_pie(df: pd.DataFrame) -> go.Figure:
    """Pie chart of expenses by category."""
    cat_totals = df.groupby("category")["amount"].sum().reset_index()
    fig = px.pie(
        cat_totals,
        names="category",
        values="amount",
        title="Expense Breakdown by Category",
        color_discrete_sequence=_PALETTE,
        hole=0.4,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))
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
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickprefix="$", gridcolor="#2a2a2a"),
    )
    return fig


def expense_trend_weekly(df: pd.DataFrame) -> go.Figure:
    """Bar chart of total weekly expenses."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.to_period("W").dt.start_time
    weekly = df.groupby("week")["amount"].sum().reset_index()
    weekly["week"] = weekly["week"].dt.strftime("%b %d")
    fig = px.bar(
        weekly,
        x="week",
        y="amount",
        title="Weekly Expense Trend",
        labels={"week": "", "amount": "Total Spend ($)"},
        color_discrete_sequence=["#5b9bd5"],
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="$", gridcolor="#2a2a2a"),
    )
    return fig


def labor_cost_gauge(labor_pct: float, target: float = 30.0, warning: float = 33.0) -> go.Figure:
    """Gauge chart for labor cost %."""
    color = "#2ecc71" if labor_pct <= target else ("#f39c12" if labor_pct <= warning else "#e74c3c")
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=labor_pct,
            number={"suffix": "%", "font": {"size": 36}},
            delta={"reference": target, "suffix": "%"},
            title={"text": "Labor Cost %"},
            gauge={
                "axis": {"range": [0, 50], "ticksuffix": "%"},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, target], "color": "rgba(46,204,113,0.2)"},
                    {"range": [target, warning], "color": "rgba(243,156,18,0.2)"},
                    {"range": [warning, 50], "color": "rgba(231,76,60,0.2)"},
                ],
                "threshold": {
                    "line": {"color": "white", "width": 3},
                    "thickness": 0.75,
                    "value": target,
                },
            },
        )
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=260)
    return fig


def labor_trend(daily_labor: pd.DataFrame, daily_sales: pd.DataFrame) -> go.Figure:
    """Dual-line: labor cost % and revenue over time."""
    labor_by_day = daily_labor.groupby("date")["labor_cost"].sum().reset_index()
    merged = labor_by_day.merge(daily_sales[["date", "revenue"]], on="date", how="inner")
    merged["labor_pct"] = merged["labor_cost"] / merged["revenue"] * 100
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=merged["date"],
            y=merged["labor_pct"],
            name="Labor %",
            line=dict(color="#e74c3c", width=2),
        )
    )
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(255,255,255,0.3)", annotation_text="Target 30%")
    fig.update_layout(
        title="Labor Cost % Trend",
        yaxis=dict(ticksuffix="%", gridcolor="#2a2a2a"),
        xaxis=dict(gridcolor="#2a2a2a"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def hours_by_dept(payroll: pd.DataFrame, week: str | None = None) -> go.Figure:
    """Bar chart of total hours by department for a given week."""
    if week:
        data = payroll[payroll["week_start"] == week]
    else:
        latest = payroll["week_start"].max()
        data = payroll[payroll["week_start"] == latest]
    dept_hours = data.groupby("dept")["total_hours"].sum().reset_index()
    fig = px.bar(
        dept_hours,
        x="dept",
        y="total_hours",
        title=f"Hours by Department — Week of {data['week_start'].iloc[0] if not data.empty else 'N/A'}",
        labels={"dept": "Department", "total_hours": "Total Hours"},
        color="dept",
        color_discrete_sequence=_PALETTE,
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(gridcolor="#2a2a2a"),
    )
    return fig


def food_cost_trend(daily_sales: pd.DataFrame) -> go.Figure:
    """Area chart of food cost % with target line."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily_sales["date"],
            y=daily_sales["food_cost_pct"],
            name="Food Cost %",
            fill="tozeroy",
            line=dict(color="#3498db", width=2),
            fillcolor="rgba(52,152,219,0.15)",
        )
    )
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(46,204,113,0.7)", annotation_text="Target 30%")
    fig.add_hline(y=33, line_dash="dot", line_color="rgba(231,76,60,0.5)", annotation_text="Warning 33%")
    fig.update_layout(
        title="Food Cost % Trend",
        yaxis=dict(ticksuffix="%", range=[20, 40], gridcolor="#2a2a2a"),
        xaxis=dict(gridcolor="#2a2a2a"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=40, b=0),
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
        title="Menu Item Profitability Matrix",
        labels={"price": "Menu Price ($)", "margin_pct": "Margin %"},
        color_discrete_sequence=_PALETTE,
        size_max=60,
    )
    fig.add_hline(y=65, line_dash="dash", line_color="rgba(255,255,255,0.3)", annotation_text="Target 65% margin")
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(ticksuffix="%", gridcolor="#2a2a2a"),
        xaxis=dict(tickprefix="$", gridcolor="#2a2a2a"),
    )
    return fig


def hourly_heatmap(hourly_sales: pd.DataFrame) -> go.Figure:
    """Heatmap: day-of-week × hour for covers or revenue."""
    df = hourly_sales.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["day_name"] = df["date"].dt.day_name()
    df["day_num"] = df["date"].dt.dayofweek  # 0=Mon

    pivot = df.groupby(["day_name", "day_num", "hour"])["covers"].mean().reset_index()
    pivot = pivot.groupby(["day_name", "day_num", "hour"])["covers"].mean().unstack("hour").fillna(0)
    pivot = pivot.sort_index(level="day_num")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot.index = pivot.index.get_level_values("day_name")
    pivot = pivot.reindex([d for d in day_order if d in pivot.index])

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=[f"{h}:00" for h in pivot.columns],
            y=pivot.index.tolist(),
            colorscale="YlOrRd",
            colorbar=dict(title="Avg Covers"),
        )
    )
    fig.update_layout(
        title="Average Covers by Day & Hour",
        xaxis_title="Hour",
        yaxis_title="",
        margin=dict(l=0, r=0, t=40, b=0),
        height=340,
    )
    return fig


def top_items_bar(menu_items: pd.DataFrame, metric: str = "total_revenue", n: int = 10) -> go.Figure:
    """Horizontal bar — top N menu items by revenue or quantity."""
    label = "Revenue ($)" if metric == "total_revenue" else "Quantity Sold"
    title = f"Top {n} Items by {'Revenue' if metric == 'total_revenue' else 'Quantity'}"
    data = menu_items.nlargest(n, metric).sort_values(metric)
    fig = px.bar(
        data,
        x=metric,
        y="name",
        orientation="h",
        title=title,
        labels={metric: label, "name": ""},
        color_discrete_sequence=[_BRAND_COLOR],
    )
    if metric == "total_revenue":
        fig.update_xaxes(tickprefix="$")
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#2a2a2a"),
    )
    return fig


def avg_check_trend(daily_sales: pd.DataFrame) -> go.Figure:
    """Line chart of average check size trend."""
    fig = px.line(
        daily_sales,
        x="date",
        y="avg_check",
        title="Average Check Size Trend",
        labels={"date": "", "avg_check": "Avg Check ($)"},
        color_discrete_sequence=[_BRAND_COLOR],
    )
    fig.update_traces(line_width=2)
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="$", gridcolor="#2a2a2a"),
        xaxis=dict(gridcolor="#2a2a2a"),
    )
    return fig


def covers_by_dow(daily_sales: pd.DataFrame) -> go.Figure:
    """Bar chart of average covers by day of week."""
    df = daily_sales.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["day"] = df["date"].dt.day_name()
    df["day_num"] = df["date"].dt.dayofweek
    day_avg = df.groupby(["day", "day_num"])["covers"].mean().reset_index()
    day_avg = day_avg.sort_values("day_num")
    fig = px.bar(
        day_avg,
        x="day",
        y="covers",
        title="Average Covers by Day of Week",
        labels={"day": "", "covers": "Avg Covers"},
        color_discrete_sequence=["#9b59b6"],
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(gridcolor="#2a2a2a"),
    )
    return fig

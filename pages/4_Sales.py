"""
Sales Analysis — Toast POS sales data.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.charts import (
    hourly_heatmap, top_items_bar, avg_check_trend,
    covers_by_dow, revenue_trend, revenue_by_dow, revenue_per_cover_trend,
)
from components.kpi_card import format_currency
from components.theme import page_header, section_header
from data import database as db

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "📈 Sales Analysis",
    subtitle="Revenue, guest covers, and check-size trends from your uploaded sales data.",
    eyebrow="Revenue Analytics",
    start_date=start_date,
    end_date=end_date,
)

# ── Data ─────────────────────────────────────────────────────────────────────
daily_sales  = db.get_daily_sales(username,  start_date=start_date, end_date=end_date)
hourly_sales = db.get_hourly_sales(username, start_date=start_date, end_date=end_date)
menu_items   = db.get_menu_items(username)

# ── Toast upload ──────────────────────────────────────────────────────────────
def _render_toast_sales_upload():
    from utils.csv_importer import parse_sales_summary
    st.markdown("**Upload Toast Sales Summary CSV**")
    st.caption(
        "In Toast: Reports → Sales → Sales Summary → Export. "
        "You can upload multiple files (e.g. one per month) and data will be merged."
    )
    uploaded = st.file_uploader(
        "Sales Summary CSV / Excel", type=["csv", "xlsx"],
        key="sales_upload", label_visibility="collapsed",
    )
    if uploaded:
        try:
            df = parse_sales_summary(uploaded.getvalue(), uploaded.name)
            st.success(f"Parsed {len(df)} rows ({df['date'].min()} → {df['date'].max()})")
            if st.button("Import to Dashboard", key="sales_import_btn", type="primary"):
                rows = db.merge_df(df, "daily_sales", username, date_col="date")
                db.update_user(username, use_simulated_data=False)
                st.session_state["user"] = db.get_user(username)
                st.cache_data.clear()
                st.success(f"Imported {rows} rows. Refreshing…")
                st.rerun()
        except Exception as e:
            st.error(f"Could not parse file: {e}")

if daily_sales.empty:
    with st.container():
        st.info("No sales data yet. Upload a Toast Sales Summary export to get started.")
        _render_toast_sales_upload()
    st.stop()

with st.expander("Update Toast Sales Data", expanded=False):
    _render_toast_sales_upload()

# ── Week-over-Week Comparison ─────────────────────────────────────────────────
# Load all sales (unfiltered by period) to compute trailing 7 vs prior 7 days
_all_sales = db.get_daily_sales(username)
if not _all_sales.empty:
    _all_sales = _all_sales.copy()
    _all_sales["date"] = pd.to_datetime(_all_sales["date"])
    _all_sales = _all_sales.sort_values("date")

    _max_date   = _all_sales["date"].max()
    _cur_start  = _max_date - pd.Timedelta(days=6)
    _prev_start = _cur_start - pd.Timedelta(days=7)
    _prev_end   = _cur_start - pd.Timedelta(days=1)

    _cur_week  = _all_sales[_all_sales["date"] >= _cur_start]
    _prev_week = _all_sales[
        (_all_sales["date"] >= _prev_start) & (_all_sales["date"] <= _prev_end)
    ]

    if not _cur_week.empty and not _prev_week.empty:
        _cw_rev   = _cur_week["revenue"].sum()
        _pw_rev   = _prev_week["revenue"].sum()
        _cw_cov   = _cur_week["covers"].sum()
        _pw_cov   = _prev_week["covers"].sum()
        _cw_chk   = _cur_week["avg_check"].mean()
        _pw_chk   = _prev_week["avg_check"].mean()
        _cw_days  = len(_cur_week)
        _pw_days  = len(_prev_week)

        def _delta_str(cur, prev):
            if prev == 0:
                return None
            return f"{(cur / prev - 1) * 100:+.1f}% vs prior week"

        section_header(
            "Week-over-Week Snapshot",
            help=(
                f"Trailing 7 days ({_cur_start.strftime('%b %d')} – {_max_date.strftime('%b %d')}) "
                f"compared to the previous 7 days "
                f"({_prev_start.strftime('%b %d')} – {_prev_end.strftime('%b %d')}). "
                "Based on available data regardless of the period selector above."
            ),
        )

        # Period labels
        _lbl_cur  = f"{_cur_start.strftime('%b %d')} – {_max_date.strftime('%b %d')}"
        _lbl_prev = f"{_prev_start.strftime('%b %d')} – {_prev_end.strftime('%b %d')}"

        _wow_cols = st.columns(5)

        with _wow_cols[0]:
            st.metric(
                "Revenue (This Week)",
                format_currency(_cw_rev),
                delta=_delta_str(_cw_rev, _pw_rev),
                help=f"Total revenue {_lbl_cur}.",
            )
        with _wow_cols[1]:
            st.metric(
                "Revenue (Prior Week)",
                format_currency(_pw_rev),
                help=f"Total revenue {_lbl_prev}.",
            )
        with _wow_cols[2]:
            st.metric(
                "Covers (This Week)",
                f"{int(_cw_cov):,}",
                delta=_delta_str(_cw_cov, _pw_cov),
                help=f"Guest covers {_lbl_cur}.",
            )
        with _wow_cols[3]:
            st.metric(
                "Avg Check (This Week)",
                format_currency(_cw_chk),
                delta=_delta_str(_cw_chk, _pw_chk),
                help=f"Average check size {_lbl_cur}.",
            )
        with _wow_cols[4]:
            # Daily run-rate: current week days vs prior week days
            _cw_daily = _cw_rev / _cw_days if _cw_days else 0
            _pw_daily = _pw_rev / _pw_days if _pw_days else 0
            st.metric(
                "Daily Run-Rate",
                format_currency(_cw_daily),
                delta=_delta_str(_cw_daily, _pw_daily),
                help=(
                    f"Average daily revenue this week ({_cw_days} day{'s' if _cw_days != 1 else ''} of data). "
                    f"Prior week: {format_currency(_pw_daily)}/day."
                ),
            )

        # Mini bar chart: daily revenue for both weeks side by side
        _LAYOUT_WOW = dict(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="rgba(240,242,246,0.75)", size=11),
            title_font=dict(size=13, color="rgba(240,242,246,0.6)"),
            margin=dict(l=0, r=0, t=38, b=0),
            legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(255,255,255,0.08)", borderwidth=1),
        )
        _GRID_WOW = dict(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.08)")

        # Align by day-of-week label (Mon … Sun) for easy comparison
        _cur_df  = _cur_week[["date", "revenue", "covers"]].copy()
        _prev_df = _prev_week[["date", "revenue", "covers"]].copy()
        _cur_df["dow"]  = _cur_df["date"].dt.strftime("%a")
        _prev_df["dow"] = _prev_df["date"].dt.strftime("%a")

        _fig_wow = go.Figure()
        _fig_wow.add_trace(go.Bar(
            x=_prev_df["dow"],
            y=_prev_df["revenue"],
            name=f"Prior ({_lbl_prev})",
            marker_color="rgba(212,168,75,0.35)",
            marker_line_width=0,
        ))
        _fig_wow.add_trace(go.Bar(
            x=_cur_df["dow"],
            y=_cur_df["revenue"],
            name=f"This Week ({_lbl_cur})",
            marker_color="#D4A84B",
            marker_line_width=0,
            text=_cur_df["revenue"].apply(lambda x: f"${x:,.0f}"),
            textposition="outside",
            textfont=dict(size=10),
        ))
        _fig_wow.update_layout(
            title="Daily Revenue — This Week vs Prior Week",
            barmode="group",
            yaxis=dict(tickprefix="$", **_GRID_WOW),
            xaxis=dict(**_GRID_WOW),
            **_LAYOUT_WOW,
        )
        st.plotly_chart(_fig_wow, use_container_width=True)

        # Insight callout
        _wow_rev_pct = (_cw_rev / _pw_rev - 1) * 100 if _pw_rev else 0
        if abs(_wow_rev_pct) >= 3:
            _dir  = "up" if _wow_rev_pct > 0 else "down"
            _icon = "📈" if _wow_rev_pct > 0 else "📉"
            _diff = format_currency(abs(_cw_rev - _pw_rev))
            st.markdown(
                f"<div style='background:rgba(212,168,75,0.07);"
                f"border:1px solid rgba(212,168,75,0.22);border-radius:10px;"
                f"padding:0.7rem 1rem;margin:0.3rem 0 0.8rem 0;font-size:0.87rem;"
                f"color:rgba(240,242,246,0.85);'>"
                f"{_icon} Revenue is <strong>{_dir} {abs(_wow_rev_pct):.1f}%</strong> "
                f"({_diff} {'more' if _wow_rev_pct > 0 else 'less'}) vs the same 7 days last week "
                f"({format_currency(_pw_rev)} → {format_currency(_cw_rev)})."
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='background:rgba(212,168,75,0.07);"
                f"border:1px solid rgba(212,168,75,0.22);border-radius:10px;"
                f"padding:0.7rem 1rem;margin:0.3rem 0 0.8rem 0;font-size:0.87rem;"
                f"color:rgba(240,242,246,0.85);'>"
                f"➡️ Revenue is <strong>on pace with last week</strong> "
                f"({_wow_rev_pct:+.1f}%): {format_currency(_pw_rev)} → {format_currency(_cw_rev)}."
                f"</div>",
                unsafe_allow_html=True,
            )

        st.divider()

# ── Daily Revenue Goal Tracker (test account only) ───────────────────────────
if username == "test":
    # Default goal = 5 % above the period average (round to nearest $50)
    _avg_rev = daily_sales["revenue"].mean() if not daily_sales.empty else 5000.0
    _default_goal = max(500.0, round(_avg_rev * 1.05 / 50) * 50)

    # Persist goal in session_state across reruns
    if "daily_revenue_goal" not in st.session_state:
        st.session_state["daily_revenue_goal"] = _default_goal

    section_header(
        "Daily Revenue Goal Tracker",
        help=(
            "Set a daily revenue target and see how each day in the selected period "
            "measured up. The default goal is 5% above your period average, "
            "rounded to the nearest $50."
        ),
    )

    # Goal input row
    _goal_col, _spacer = st.columns([1, 3])
    with _goal_col:
        _goal = st.number_input(
            "Daily Revenue Goal ($)",
            min_value=100.0,
            max_value=500_000.0,
            value=float(st.session_state["daily_revenue_goal"]),
            step=50.0,
            format="%.0f",
            key="goal_input",
            help="Adjust your daily revenue target. The tracker updates immediately.",
        )
        st.session_state["daily_revenue_goal"] = _goal

    # ── KPI summary row ───────────────────────────────────────────────────────
    _ds_goal = daily_sales.copy()
    _ds_goal["hit_goal"] = _ds_goal["revenue"] >= _goal
    _days_total  = len(_ds_goal)
    _days_hit    = int(_ds_goal["hit_goal"].sum())
    _days_missed = _days_total - _days_hit
    _hit_pct     = _days_hit / _days_total * 100 if _days_total else 0.0

    # Revenue on goal days vs miss days
    _rev_on_hit   = _ds_goal.loc[_ds_goal["hit_goal"],  "revenue"].sum()
    _rev_on_miss  = _ds_goal.loc[~_ds_goal["hit_goal"], "revenue"].sum()
    _avg_shortfall = (
        (_goal - _ds_goal.loc[~_ds_goal["hit_goal"], "revenue"]).mean()
        if _days_missed > 0 else 0.0
    )

    _g1, _g2, _g3, _g4, _g5 = st.columns(5)
    with _g1:
        st.metric(
            "Days Hit Goal",
            f"{_days_hit} / {_days_total}",
            delta=f"{_hit_pct:.0f}% attainment",
            delta_color="normal" if _hit_pct >= 50 else "inverse",
            help="Number of days where revenue met or exceeded your goal.",
        )
    with _g2:
        st.metric(
            "Days Missed Goal",
            f"{_days_missed}",
            delta=f"-{100 - _hit_pct:.0f}% of days" if _days_missed else "0 misses",
            delta_color="inverse" if _days_missed else "off",
            help="Number of days where revenue fell short of your goal.",
        )
    with _g3:
        st.metric(
            "Avg Shortfall on Miss Days",
            format_currency(_avg_shortfall) if _days_missed else "—",
            help="Average gap between goal and actual revenue on days that missed target.",
        )
    with _g4:
        _best_above = (_ds_goal["revenue"] - _goal).max()
        st.metric(
            "Best Day Above Goal",
            format_currency(_best_above) if _best_above > 0 else "—",
            help="Largest single-day surplus above the goal in the selected period.",
        )
    with _g5:
        _potential_gained = _avg_shortfall * _days_missed
        st.metric(
            "Potential Revenue Gap",
            format_currency(_potential_gained) if _days_missed else format_currency(0),
            help=(
                "Total estimated revenue gap on miss days "
                "(average shortfall × number of miss days). "
                "Closing even half this gap represents a meaningful revenue uplift."
            ),
        )

    # ── Goal attainment bar chart ─────────────────────────────────────────────
    _ds_goal_sorted = _ds_goal.sort_values("date")
    _colors_goal = [
        "#2ecc71" if hit else "#e74c3c"
        for hit in _ds_goal_sorted["hit_goal"]
    ]
    _LAYOUT_GOAL = dict(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(240,242,246,0.75)", size=11),
        title_font=dict(size=13, color="rgba(240,242,246,0.6)"),
        margin=dict(l=0, r=0, t=42, b=0),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(255,255,255,0.08)", borderwidth=1),
        showlegend=True,
    )
    _GRID_GOAL = dict(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.08)")

    _fig_goal = go.Figure()

    # Bars coloured green/red by goal attainment
    _fig_goal.add_trace(go.Bar(
        x=_ds_goal_sorted["date"],
        y=_ds_goal_sorted["revenue"],
        marker_color=_colors_goal,
        marker_line_width=0,
        name="Daily Revenue",
        customdata=(_ds_goal_sorted["revenue"] - _goal).values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Revenue: $%{y:,.0f}<br>"
            "vs Goal: %{customdata:+,.0f}"
            "<extra></extra>"
        ),
    ))

    # Goal line
    _fig_goal.add_hline(
        y=_goal,
        line_dash="dash",
        line_color="rgba(212,168,75,0.85)",
        line_width=2,
        annotation_text=f"Goal: {format_currency(_goal)}",
        annotation_font_color="rgba(212,168,75,0.9)",
        annotation_position="top right",
    )

    # Period average line
    _fig_goal.add_hline(
        y=_avg_rev,
        line_dash="dot",
        line_color="rgba(91,155,213,0.6)",
        line_width=1.5,
        annotation_text=f"Avg: {format_currency(_avg_rev)}",
        annotation_font_color="rgba(91,155,213,0.8)",
        annotation_position="bottom right",
    )

    # Invisible traces for legend
    _fig_goal.add_trace(go.Bar(
        x=[None], y=[None],
        marker_color="#2ecc71",
        name="✓ Hit Goal",
        showlegend=True,
    ))
    _fig_goal.add_trace(go.Bar(
        x=[None], y=[None],
        marker_color="#e74c3c",
        name="✗ Missed Goal",
        showlegend=True,
    ))

    _fig_goal.update_layout(
        title="Daily Revenue vs Goal",
        xaxis=dict(**_GRID_GOAL),
        yaxis=dict(tickprefix="$", **_GRID_GOAL),
        barmode="overlay",
        **_LAYOUT_GOAL,
    )
    st.plotly_chart(_fig_goal, use_container_width=True)

    # ── Insight callout ───────────────────────────────────────────────────────
    if _hit_pct >= 70:
        _insight_icon, _insight_color = "🏆", "rgba(46,204,113,0.12)"
        _insight_border = "rgba(46,204,113,0.3)"
        _insight_msg = (
            f"Strong performance — revenue hit the <strong>{format_currency(_goal)}</strong> daily goal "
            f"on <strong>{_days_hit} of {_days_total} days ({_hit_pct:.0f}%)</strong>. "
            f"Keep momentum by protecting staffing and marketing on your strongest days."
        )
    elif _hit_pct >= 40:
        _insight_icon, _insight_color = "⚠️", "rgba(212,168,75,0.10)"
        _insight_border = "rgba(212,168,75,0.3)"
        _insight_msg = (
            f"Goal was reached on <strong>{_days_hit} of {_days_total} days ({_hit_pct:.0f}%)</strong>. "
            f"Average shortfall on miss days: <strong>{format_currency(_avg_shortfall)}</strong>. "
            f"Investigate whether missed days cluster on specific days of the week or times of month."
        )
    else:
        _insight_icon, _insight_color = "📉", "rgba(231,76,60,0.10)"
        _insight_border = "rgba(231,76,60,0.3)"
        _insight_msg = (
            f"Goal was reached on only <strong>{_days_hit} of {_days_total} days ({_hit_pct:.0f}%)</strong>. "
            f"Consider whether the <strong>{format_currency(_goal)}</strong> target is calibrated correctly, "
            f"or whether pricing, covers, or marketing need adjustment to close the "
            f"<strong>{format_currency(_potential_gained)}</strong> total gap."
        )

    st.markdown(
        f"<div style='background:{_insight_color};"
        f"border:1px solid {_insight_border};border-radius:10px;"
        f"padding:0.75rem 1.1rem;margin:0.2rem 0 0.5rem 0;font-size:0.87rem;"
        f"color:rgba(240,242,246,0.85);'>"
        f"{_insight_icon} {_insight_msg}"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.divider()

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
section_header("Period KPIs", help="Key revenue and guest metrics for the selected date range. Deltas compare the second half of the period against the first half.")
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
section_header("Revenue Trend", help="Daily revenue over the selected period with a 7-day rolling average overlay to show the underlying trend.")
st.plotly_chart(revenue_trend(daily_sales, days=len(daily_sales)), use_container_width=True)

st.divider()

# ── Peak hours heatmap ────────────────────────────────────────────────────────
section_header("Peak Hours Heatmap", help="Average revenue by hour of day and day of week. Darker cells = higher revenue. Use this to plan staffing and identify under-performing slots.")
if not hourly_sales.empty:
    st.plotly_chart(hourly_heatmap(hourly_sales), use_container_width=True)
else:
    st.info("Hourly data not available for this period.")

st.divider()

# ── Day-of-week & spend-per-head ──────────────────────────────────────────────
section_header("Traffic Patterns", help="Left: average revenue by day of week — shows your most and least profitable days. Right: average guest covers by day of week.")
col_a, col_b = st.columns(2)
with col_a:
    st.plotly_chart(revenue_by_dow(daily_sales), use_container_width=True)
with col_b:
    st.plotly_chart(covers_by_dow(daily_sales), use_container_width=True)

st.divider()

# ── Check size & spend per head trends ───────────────────────────────────────
section_header("Spend Trends", help="Left: average check size per day over time — a rising trend means guests are spending more per visit. Right: revenue per guest cover.")
col_c, col_d = st.columns(2)
with col_c:
    st.plotly_chart(avg_check_trend(daily_sales), use_container_width=True)
with col_d:
    st.plotly_chart(revenue_per_cover_trend(daily_sales), use_container_width=True)

st.divider()

# ── Top menu items ────────────────────────────────────────────────────────────
if not menu_items.empty:
    section_header("Top-Performing Menu Items", help="Left: top items by total revenue generated in the period. Right: top items by number of units sold.")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(top_items_bar(menu_items, metric="total_revenue"), use_container_width=True)
    with col2:
        st.plotly_chart(top_items_bar(menu_items, metric="quantity_sold"), use_container_width=True)
    st.divider()

# ── Daily detail table ────────────────────────────────────────────────────────
section_header("Daily Sales Detail", help="Day-by-day breakdown of guest covers, revenue, and average check size. Sorted most recent first.")
table = daily_sales[["date", "covers", "revenue", "avg_check"]].copy()
table["revenue"]   = table["revenue"].apply(lambda x: f"${x:,.0f}")
table["avg_check"] = table["avg_check"].apply(lambda x: f"${x:.2f}")
table = table.sort_values("date", ascending=False)
table.columns = ["Date", "Covers", "Revenue", "Avg. Check"]
st.dataframe(table, use_container_width=True, height=400, hide_index=True)

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

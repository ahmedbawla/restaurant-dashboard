"""
Summary — business overview dashboard.
Shows whatever data sources are connected; never stops if only some are synced.
"""

import json
from pathlib import Path

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from components.kpi_card import format_currency, threshold_badge
from components.charts import revenue_trend, revenue_by_dow, revenue_per_cover_trend
from components.theme import page_header, section_header, health_badge
from data import database as db

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)
THRESHOLDS = CONFIG.get("thresholds", {})
LABOR_TARGET  = THRESHOLDS.get("labor_cost_pct_target",  30.0)
LABOR_WARNING = THRESHOLDS.get("labor_cost_pct_warning", 33.0)

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

last_status = user.get("last_sync_status") or ""
page_header(
    f"🍽️ {user['restaurant_name']}",
    subtitle=(
        "Business Intelligence Dashboard  ·  Demo data"
        if last_status == "demo"
        else f"Business Intelligence Dashboard  ·  {start_date} – {end_date}"
    ),
    eyebrow="Shareholder Overview",
)

# ── Load all data ─────────────────────────────────────────────────────────────
kpi         = db.get_kpi_today(username, as_of_date=end_date)
daily_sales    = db.get_daily_sales(username,    start_date=start_date, end_date=end_date)
daily_labor    = db.get_daily_labor(username,    start_date=start_date, end_date=end_date)
weekly_payroll = db.get_weekly_payroll(username, start_date=start_date, end_date=end_date)
expenses       = db.get_expenses(username,       start_date=start_date, end_date=end_date)
menu_items     = db.get_menu_items(username)

has_sales    = not daily_sales.empty
has_labor    = not daily_labor.empty
has_expenses = not expenses.empty
has_menu     = not menu_items.empty
has_any      = has_sales or has_labor or has_expenses or has_menu

if not has_any:
    st.warning(
        "No data found for the selected period. "
        "Upload data on the Sales or Payroll tabs, or connect QuickBooks on the Spending tab."
    )
    st.stop()

# ── Source banner ─────────────────────────────────────────────────────────────
_connected = []
_missing   = []
if has_sales:    _connected.append("Sales")
else:            _missing.append("Sales (upload on Sales tab)")
if has_labor:    _connected.append("Payroll")
else:            _missing.append("Payroll (upload on Payroll tab)")
if has_expenses: _connected.append("QuickBooks Expenses")
else:            _missing.append("Expenses (connect QuickBooks on Spending tab)")
if _missing:
    st.info(
        f"Showing data from: **{', '.join(_connected)}**.  "
        f"Missing: **{', '.join(_missing)}**."
    )

# ── Pre-compute cross-source metrics ──────────────────────────────────────────
period_rev          = daily_sales["revenue"].sum()                  if has_sales    else 0.0
period_labor_cost   = daily_labor["labor_cost"].sum()               if has_labor    else 0.0
period_labor_hrs    = daily_labor["hours"].sum()                    if has_labor    else 0.0
period_expense_tot  = expenses["amount"].sum()                      if has_expenses else 0.0
period_labor_pct    = period_labor_cost / period_rev * 100          if (period_rev and has_labor)    else None
period_expense_pct  = period_expense_tot / period_rev * 100         if (period_rev and has_expenses) else None
period_total_costs  = period_labor_cost + period_expense_tot
period_cost_pct     = period_total_costs / period_rev * 100         if period_rev else None
period_rev_per_hr   = period_rev / period_labor_hrs                 if period_labor_hrs else None

# ── Business Health Score ─────────────────────────────────────────────────────
if has_sales and kpi:
    _alerts = _warnings = 0
    if period_labor_pct is not None:
        if period_labor_pct > LABOR_WARNING:  _alerts   += 1
        elif period_labor_pct > LABOR_TARGET: _warnings += 1

    if _alerts:
        hs_status, hs_label = "alert",   f"Needs Attention — {_alerts} alert{'s' if _alerts > 1 else ''}"
    elif _warnings:
        hs_status, hs_label = "warning", f"Watch Closely — {_warnings} warning{'s' if _warnings > 1 else ''}"
    else:
        hs_status, hs_label = "good",    "All Systems Healthy"

    if not has_labor:
        hs_status, hs_label = "good", "Sales Tracking Active — connect Payroll for full health score"

    st.markdown(
        f'<div style="margin:0.6rem 0 0.5rem 0">'
        f'<span style="font-size:0.65rem;text-transform:uppercase;letter-spacing:2px;'
        f'color:rgba(212,168,75,0.7);font-weight:700;">Business Health</span>&nbsp;&nbsp;'
        f'{health_badge(hs_label, hs_status)}</div>',
        unsafe_allow_html=True,
    )

    if has_labor and (_alerts or _warnings):
        with st.expander("View issues →", expanded=True):
            if period_labor_pct is not None and period_labor_pct > LABOR_TARGET:
                _is_alert = period_labor_pct > LABOR_WARNING
                (st.error if _is_alert else st.warning)(
                    f"**Labour Cost %: {period_labor_pct:.1f}%** — "
                    f"{'above alert threshold' if _is_alert else 'above target'} "
                    f"(target ≤{LABOR_TARGET:.0f}%, alert >{LABOR_WARNING:.0f}%)  \n"
                    "Adjust shift schedules to align staff hours with your busiest trading windows."
                )

# ── Most Recent Day ───────────────────────────────────────────────────────────
if has_sales and kpi:
    _kpi_date      = kpi["date"]
    _kpi_rev       = kpi["revenue"]
    _kpi_covers    = kpi["covers"]
    _kpi_avg_check = kpi["avg_check"]

    # Only use day-level labour if that specific date has actual data (hours > 0)
    _day_labor_row = daily_labor[daily_labor["date"] == _kpi_date] if has_labor else None
    _kpi_labor_hrs  = float(_day_labor_row["hours"].sum())      if (_day_labor_row is not None and not _day_labor_row.empty) else 0.0
    _kpi_labor_cost = float(_day_labor_row["labor_cost"].sum()) if (_day_labor_row is not None and not _day_labor_row.empty) else 0.0
    _kpi_has_day_labor = _kpi_labor_hrs > 0

    _kpi_labor_pct  = _kpi_labor_cost / _kpi_rev * 100 if (_kpi_has_day_labor and _kpi_rev) else None
    _kpi_rev_per_hr = _kpi_rev / _kpi_labor_hrs         if _kpi_has_day_labor else None

    section_header(
        f"Most Recent Day — {_kpi_date}",
        help="KPIs for the most recent date in your dataset.",
    )

    if _kpi_has_day_labor:
        c1, c2, c3, c4, c5 = st.columns(5)
        with c4:
            st.metric("Labour %",
                      threshold_badge(_kpi_labor_pct, LABOR_TARGET, LABOR_WARNING),
                      help="Labour cost as % of revenue for the day.")
        with c5:
            st.metric("Rev / Labour Hr", format_currency(_kpi_rev_per_hr),
                      help="Revenue generated per hour worked on this day.")
    else:
        c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Daily Revenue", format_currency(_kpi_rev))
    with c2:
        st.metric("Guest Covers",  f"{_kpi_covers:,}")
    with c3:
        st.metric("Avg. Check",    format_currency(_kpi_avg_check))

    st.divider()

# ── Period Summary ────────────────────────────────────────────────────────────
if has_sales:
    mid           = len(daily_sales) // 2
    rev_recent    = daily_sales.iloc[mid:]["revenue"].sum()
    rev_prior     = daily_sales.iloc[:mid]["revenue"].sum()
    rev_delta     = f"{(rev_recent/rev_prior - 1)*100:+.1f}% vs prior period" if rev_prior else None
    total_covers  = daily_sales["covers"].sum()
    cvr_recent    = daily_sales.iloc[mid:]["covers"].sum()
    cvr_prior     = daily_sales.iloc[:mid]["covers"].sum()
    cvr_delta     = f"{(cvr_recent/cvr_prior - 1)*100:+.1f}% vs prior period" if cvr_prior else None
    chk_recent    = daily_sales.iloc[mid:]["avg_check"].mean()
    chk_prior     = daily_sales.iloc[:mid]["avg_check"].mean()
    chk_delta     = f"{(chk_recent/chk_prior - 1)*100:+.1f}% vs prior period" if chk_prior else None

    section_header(
        "Period Summary",
        help="Totals and averages across the entire selected date range. Deltas compare second half vs first half of the period.",
    )
    s1, s2, s3, s4, s5 = st.columns(5)
    with s1:
        st.metric("Total Revenue",    format_currency(period_rev), delta=rev_delta)
    with s2:
        st.metric("Total Covers",     f"{int(total_covers):,}", delta=cvr_delta)
    with s3:
        st.metric("Avg. Check Size",  format_currency(daily_sales["avg_check"].mean()), delta=chk_delta)
    with s4:
        if has_labor:
            st.metric("Total Labour Cost", format_currency(period_labor_cost),
                      delta=f"{period_labor_pct:.1f}% of revenue" if period_labor_pct else None,
                      delta_color="off")
        else:
            st.metric("Avg. Daily Revenue", format_currency(daily_sales["revenue"].mean()))
    with s5:
        if has_expenses:
            st.metric("Total QB Expenses", format_currency(period_expense_tot),
                      delta=f"{period_expense_pct:.1f}% of revenue" if period_expense_pct else None,
                      delta_color="off")
        elif period_rev_per_hr:
            st.metric("Rev / Labour Hr", format_currency(period_rev_per_hr),
                      help="Period revenue divided by total hours worked.")
        else:
            rpc = period_rev / total_covers if total_covers else 0
            st.metric("Rev per Cover", format_currency(rpc))

    st.divider()

    # Revenue trend
    section_header("Revenue Trend", help="Daily revenue over the selected period with a 7-day rolling average.")
    st.plotly_chart(revenue_trend(daily_sales, days=len(daily_sales)), use_container_width=True)
    st.divider()

    # Traffic patterns
    section_header("Traffic & Spend Analysis", help="Left: average revenue by day of week. Right: revenue per guest cover over time.")
    col_dow, col_rpc = st.columns(2)
    with col_dow: st.plotly_chart(revenue_by_dow(daily_sales), use_container_width=True)
    with col_rpc: st.plotly_chart(revenue_per_cover_trend(daily_sales), use_container_width=True)
    st.divider()

    # Performance extremes
    section_header("Performance Extremes", help="Best and worst revenue days in the selected period.")
    e1, e2, e3, e4 = st.columns(4)
    _peak = daily_sales.loc[daily_sales["revenue"].idxmax()]
    _low  = daily_sales.loc[daily_sales["revenue"].idxmin()]
    _high_chk = daily_sales.loc[daily_sales["avg_check"].idxmax()]
    with e1:
        st.metric("Best Day",          _peak["date"])
        st.metric("Best Day Revenue",  format_currency(_peak["revenue"]))
    with e2:
        st.metric("Avg. Daily Revenue", format_currency(daily_sales["revenue"].mean()))
        st.metric("Avg. Covers / Day",  f"{daily_sales['covers'].mean():.0f}")
    with e3:
        st.metric("Lowest Day",         _low["date"])
        st.metric("Lowest Day Revenue", format_currency(_low["revenue"]))
    with e4:
        st.metric("Highest Avg Check",  format_currency(_high_chk["avg_check"]))
        st.metric("On Date",            _high_chk["date"])
    st.divider()

# ── Labour Efficiency ─────────────────────────────────────────────────────────
if has_labor:
    section_header(
        "Labour Efficiency",
        help="Payroll cost metrics for the selected period. Labour % = total labour cost ÷ total revenue.",
    )
    l1, l2, l3, l4 = st.columns(4)
    with l1:
        st.metric("Total Labour Cost", format_currency(period_labor_cost))
    with l2:
        if period_labor_pct is not None:
            st.metric("Labour % of Revenue",
                      threshold_badge(period_labor_pct, LABOR_TARGET, LABOR_WARNING))
        else:
            st.metric("Labour % of Revenue", "—", help="Connect Sales data to calculate.")
    with l3:
        st.metric("Total Hours Worked", f"{period_labor_hrs:,.0f} hrs")
    with l4:
        if period_rev_per_hr:
            st.metric("Rev / Labour Hr", format_currency(period_rev_per_hr),
                      help="Period revenue divided by total hours worked.")
        else:
            avg_cost_hr = period_labor_cost / period_labor_hrs if period_labor_hrs else 0
            st.metric("Avg. Labour Cost / Hr", format_currency(avg_cost_hr))

    # Labour % trend (only when sales available for context)
    if has_sales and period_labor_pct is not None:
        import pandas as _pd
        _labor_by_day = daily_labor.groupby("date")["labor_cost"].sum().reset_index()
        _merged = _labor_by_day.merge(daily_sales[["date", "revenue"]], on="date", how="inner")
        if not _merged.empty:
            _merged["labor_pct"] = _merged["labor_cost"] / _merged["revenue"] * 100
            _merged["date"] = _pd.to_datetime(_merged["date"])
            _LAYOUT = dict(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="rgba(240,242,246,0.75)"),
                margin=dict(l=0, r=0, t=20, b=0),
                showlegend=False,
            )
            fig_lp = go.Figure()
            fig_lp.add_trace(go.Scatter(
                x=_merged["date"], y=_merged["labor_pct"],
                mode="lines", line=dict(color="#FF6B35", width=2),
                name="Labour %",
            ))
            fig_lp.add_hline(y=LABOR_TARGET, line_dash="dash",
                             line_color="rgba(46,204,113,0.6)", annotation_text=f"Target {LABOR_TARGET:.0f}%")
            fig_lp.add_hline(y=LABOR_WARNING, line_dash="dot",
                             line_color="rgba(231,76,60,0.6)", annotation_text=f"Warning {LABOR_WARNING:.0f}%")
            fig_lp.update_yaxes(ticksuffix="%", gridcolor="rgba(255,255,255,0.06)")
            fig_lp.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
            fig_lp.update_layout(**_LAYOUT, title="Daily Labour % of Revenue")
            st.plotly_chart(fig_lp, use_container_width=True)

    # Payroll summary table
    if not weekly_payroll.empty:
        _wp_cols = [c for c in ["employee_name", "dept", "role", "employment_type",
                                 "regular_hours", "overtime_hours", "total_hours", "gross_pay"]
                    if c in weekly_payroll.columns]
        _wp_sum = (
            weekly_payroll[_wp_cols]
            .groupby(["employee_name", "dept", "role", "employment_type"], as_index=False)
            .agg(
                regular_hours =("regular_hours",  "sum"),
                overtime_hours=("overtime_hours", "sum"),
                total_hours   =("total_hours",    "sum"),
                gross_pay     =("gross_pay",      "sum"),
            )
            if all(c in weekly_payroll.columns for c in ["regular_hours", "overtime_hours", "total_hours", "gross_pay"])
            else weekly_payroll[_wp_cols].copy()
        )
        _wp_sum = _wp_sum.sort_values(["dept", "employee_name"])
        _wp_display = _wp_sum.copy()
        if "gross_pay"      in _wp_display.columns: _wp_display["gross_pay"]      = _wp_display["gross_pay"].apply(lambda x: f"${x:,.2f}")
        if "regular_hours"  in _wp_display.columns: _wp_display["regular_hours"]  = _wp_display["regular_hours"].apply(lambda x: f"{x:.1f}")
        if "overtime_hours" in _wp_display.columns: _wp_display["overtime_hours"] = _wp_display["overtime_hours"].apply(lambda x: f"{x:.1f}")
        if "total_hours"    in _wp_display.columns: _wp_display["total_hours"]    = _wp_display["total_hours"].apply(lambda x: f"{x:.1f}")
        _col_rename = {
            "employee_name": "Employee", "dept": "Department", "role": "Role",
            "employment_type": "Type", "regular_hours": "Reg Hrs",
            "overtime_hours": "OT Hrs", "total_hours": "Total Hrs", "gross_pay": "Gross Pay",
        }
        _wp_display = _wp_display.rename(columns={k: v for k, v in _col_rename.items() if k in _wp_display.columns})
        st.caption("**Payroll Summary — all weeks in selected period**")
        st.dataframe(_wp_display, use_container_width=True, hide_index=True)

    st.divider()

# ── Cost Breakdown (when multiple sources connected) ──────────────────────────
if has_sales and has_labor and has_expenses:
    section_header(
        "Revenue Breakdown",
        help="How each dollar of revenue is allocated: labour, operating expenses, and remainder. This is not accounting profit — food/COGS not included.",
    )
    _remainder = max(0.0, period_rev - period_total_costs)
    _labels = ["Labour Cost", "Operating Expenses", "Remaining"]
    _values = [period_labor_cost, period_expense_tot, _remainder]
    _colors = ["#FF6B35", "#e74c3c", "#2ecc71"]

    rb1, rb2, rb3, rb4 = st.columns(4)
    with rb1:
        st.metric("Labour", format_currency(period_labor_cost),
                  delta=f"{period_labor_pct:.1f}% of revenue", delta_color="off")
    with rb2:
        st.metric("Operating Expenses", format_currency(period_expense_tot),
                  delta=f"{period_expense_pct:.1f}% of revenue", delta_color="off")
    with rb3:
        st.metric("Total Tracked Costs", format_currency(period_total_costs),
                  delta=f"{period_cost_pct:.1f}% of revenue", delta_color="off")
    with rb4:
        st.metric("Revenue After Costs", format_currency(_remainder),
                  help="Revenue minus labour and operating expenses. Food/COGS not included.")

    _fig_rb = go.Figure(go.Bar(
        x=_values, y=_labels, orientation="h",
        marker_color=_colors,
        text=[f"${v:,.0f}" for v in _values],
        textposition="auto",
    ))
    _fig_rb.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(240,242,246,0.75)"),
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(tickprefix="$", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0)"),
        showlegend=False,
    )
    st.plotly_chart(_fig_rb, use_container_width=True)
    st.divider()

# ── Spending Overview (QuickBooks) ────────────────────────────────────────────
if has_expenses:
    _cat_exp     = expenses[expenses["category"] != "Pending Review"]
    _pending_amt = expenses[expenses["category"] == "Pending Review"]["amount"].sum()
    _total_spend = expenses["amount"].sum()

    section_header(
        "Spending Overview",
        help="Operating expenses from QuickBooks for the selected period.",
    )
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.metric("Total Spend", format_currency(_total_spend))
    with e2:
        if not _cat_exp.empty:
            st.metric("Largest Category", _cat_exp.groupby("category")["amount"].sum().idxmax())
        else:
            st.metric("Largest Category", "—")
    with e3:
        st.metric("Pending Review", format_currency(_pending_amt),
                  help="Unreviewed bank feed transactions — categorise in QBO to see full breakdown.")
    with e4:
        st.metric("Unique Vendors", str(expenses["vendor"].nunique()))

    if not _cat_exp.empty:
        _top5 = (
            _cat_exp.groupby("category")["amount"].sum()
            .nlargest(5).reset_index()
        )
        _top5.columns = ["Category", "Amount"]
        _top5["Amount"] = _top5["Amount"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(_top5, use_container_width=True, hide_index=True)

    st.divider()

# ── Labour-only (no sales) ────────────────────────────────────────────────────
if has_labor and not has_sales:
    section_header("Labour Overview", help="Payroll data from Paychex for the selected period.")
    l1, l2, l3 = st.columns(3)
    with l1: st.metric("Total Labour Cost",   format_currency(period_labor_cost))
    with l2: st.metric("Total Hours Worked",  f"{period_labor_hrs:,.0f} hrs")
    with l3:
        avg_hr = period_labor_cost / period_labor_hrs if period_labor_hrs else 0
        st.metric("Avg. Cost per Hour", format_currency(avg_hr))
    st.divider()

# ── Menu Mix Snapshot ─────────────────────────────────────────────────────────
if has_menu:
    section_header(
        "Menu Mix Snapshot",
        help="Category revenue split and top items from your uploaded menu data.",
    )
    _cat_rev = (
        menu_items.groupby("category", as_index=False)["total_revenue"]
        .sum().sort_values("total_revenue", ascending=False)
    )
    _top5_items = menu_items.nlargest(5, "total_revenue")[
        ["name", "category", "quantity_sold", "total_revenue"]
    ].copy()
    _top5_items["total_revenue"] = _top5_items["total_revenue"].apply(lambda x: f"${x:,.0f}")
    _top5_items["quantity_sold"] = _top5_items["quantity_sold"].apply(lambda x: f"{x:,}")
    _top5_items.columns = ["Item", "Category", "Qty Sold", "Revenue"]

    _LM = dict(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(240,242,246,0.75)"),
        margin=dict(l=0, r=0, t=10, b=0),
    )
    mc1, mc2 = st.columns([1.2, 1])
    with mc1:
        fig_menu = px.bar(
            _cat_rev.sort_values("total_revenue"),
            x="total_revenue", y="category", orientation="h",
            color="total_revenue",
            color_continuous_scale=["#3a1a0a", "#FF6B35"],
            labels={"total_revenue": "Revenue", "category": ""},
        )
        fig_menu.update_coloraxes(showscale=False)
        fig_menu.update_xaxes(tickprefix="$", gridcolor="rgba(255,255,255,0.06)")
        fig_menu.update_layout(**_LM)
        st.plotly_chart(fig_menu, use_container_width=True)
    with mc2:
        st.caption("**Top 5 Items by Revenue**")
        st.dataframe(_top5_items, use_container_width=True, hide_index=True)
    st.divider()

st.caption(
    f"Confidential  ·  For authorised recipients only  ·  "
    f"{user['restaurant_name']} Business Intelligence Dashboard"
)

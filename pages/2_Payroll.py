"""
Payroll & Labour — Paychex data.
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.kpi_card import format_currency
from components.theme import page_header, section_header
from data import database as db

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "👥 Payroll & Labour",
    subtitle="Payroll summary and workforce breakdown from your Paychex data.",
    eyebrow="Workforce Analytics",
)

# ── Chart style constants ─────────────────────────────────────────────────────
_BRAND  = "#D4A84B"
_BLUE   = "#5b9bd5"
_LAYOUT = dict(
    plot_bgcolor  = "rgba(0,0,0,0)",
    paper_bgcolor = "rgba(0,0,0,0)",
    font          = dict(color="rgba(240,242,246,0.75)", size=12),
    title_font    = dict(size=13, color="rgba(240,242,246,0.6)", family="sans-serif"),
    margin        = dict(l=0, r=0, t=38, b=0),
    legend        = dict(bgcolor="rgba(0,0,0,0)",
                         bordercolor="rgba(255,255,255,0.08)", borderwidth=1),
)
_GRID = dict(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.08)")

# ── Data ─────────────────────────────────────────────────────────────────────
weekly_payroll = db.get_weekly_payroll(username)

# Filter to pay periods that overlap with the selected date range
if start_date:
    weekly_payroll = weekly_payroll[weekly_payroll["week_end"] >= start_date]
if end_date:
    weekly_payroll = weekly_payroll[weekly_payroll["week_start"] <= end_date]

# ── Paychex upload ────────────────────────────────────────────────────────────
def _render_paychex_upload():
    from utils.csv_importer import parse_paychex_labor_cost
    st.markdown("**Upload Paychex Payroll Labor Cost CSV**")
    st.caption(
        "In Paychex Flex: Reports → Payroll → Payroll Labor Cost → Download (CSV). "
        "Export as wide a date range as you have — data is merged, nothing gets overwritten."
    )
    uploaded = st.file_uploader(
        "Payroll Labor Cost CSV", type=["csv", "xlsx"],
        key="paychex_upload", label_visibility="collapsed",
    )
    if uploaded:
        try:
            wp_df, dl_df = parse_paychex_labor_cost(uploaded.getvalue(), uploaded.name)
            st.success(
                f"Parsed **{len(wp_df)} employee-week rows** across "
                f"**{wp_df['week_start'].nunique()} pay periods** "
                f"({wp_df['week_start'].min()} → {wp_df['week_end'].max()})  ·  "
                f"{wp_df['employee_name'].nunique()} employees"
            )
            if st.button("Import to Dashboard", key="paychex_import_btn", type="primary"):
                db.merge_df(dl_df, "daily_labor",    username, date_col="date")
                db.merge_df(wp_df, "weekly_payroll", username, date_col="week_start")
                db.update_user(username, use_simulated_data=False)
                st.session_state["user"] = db.get_user(username)
                st.cache_data.clear()
                st.success("Paychex data imported. Refreshing…")
                st.rerun()
        except Exception as e:
            st.error(f"Could not parse file: {e}")

if weekly_payroll.empty:
    all_payroll = db.get_weekly_payroll(username)
    if not all_payroll.empty:
        st.warning(
            f"No payroll data in the selected date range. "
            f"Your data covers **{all_payroll['week_start'].min()}** → **{all_payroll['week_end'].max()}** — "
            f"try widening the date range in the sidebar (e.g. switch to **Annual**)."
        )
        with st.expander("Update Paychex Data", expanded=False):
            _render_paychex_upload()
    else:
        st.info("No payroll data yet. Upload your Paychex exports to get started.")
        _render_paychex_upload()
    st.stop()

with st.expander("Update Paychex Data", expanded=False):
    _render_paychex_upload()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    available_weeks = sorted(weekly_payroll["week_start"].unique(), reverse=True)
    selected_week   = st.selectbox("Payroll Week", available_weeks)

week_data = weekly_payroll[weekly_payroll["week_start"] == selected_week]

# ── Period-level metrics ──────────────────────────────────────────────────────
period_payroll = weekly_payroll["gross_pay"].sum()
period_hours   = weekly_payroll["total_hours"].sum()
headcount      = weekly_payroll["employee_name"].nunique()
avg_hourly     = period_payroll / period_hours if period_hours else 0.0
weeks_covered  = weekly_payroll["week_start"].nunique()

# ── KPI strip ─────────────────────────────────────────────────────────────────
section_header("Period Overview", help="Payroll totals across the selected date range.")
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Total Payroll", format_currency(period_payroll),
              help="Sum of gross pay across all weeks in the selected period.")
with k2:
    st.metric("Total Hours", f"{period_hours:,.0f} hrs",
              help="Total hours worked across the selected period.")
with k3:
    st.metric("Headcount", f"{headcount}",
              help="Unique employees with payroll in the selected period.")
with k4:
    st.metric("Avg Hourly Rate", format_currency(avg_hourly),
              help="Total gross pay ÷ total hours for the period.")
with k5:
    st.metric("Pay Periods", f"{weeks_covered}",
              help="Number of weekly pay periods in the selected range.")

st.divider()

# ── Weekly payroll trend ──────────────────────────────────────────────────────
section_header("Weekly Payroll Trend", help="Total gross pay per pay period across the selected range.")
weekly_totals = (
    weekly_payroll.groupby("week_start")["gross_pay"]
    .sum().reset_index().sort_values("week_start")
)
weekly_totals["week_label"] = pd.to_datetime(weekly_totals["week_start"]).dt.strftime("%b %d")
weekly_totals["rolling_4"]  = weekly_totals["gross_pay"].rolling(4, min_periods=1).mean()

fig_trend = go.Figure()
fig_trend.add_trace(go.Bar(
    x=weekly_totals["week_label"], y=weekly_totals["gross_pay"],
    name="Weekly Payroll",
    marker_color=_BLUE, marker_line_width=0,
    text=weekly_totals["gross_pay"].apply(lambda x: f"${x:,.0f}"),
    textposition="outside", textfont=dict(size=10),
))
fig_trend.add_trace(go.Scatter(
    x=weekly_totals["week_label"], y=weekly_totals["rolling_4"],
    name="4-Wk Avg", line=dict(color=_BRAND, width=2, dash="dot"),
))
fig_trend.update_layout(
    yaxis=dict(tickprefix="$", **_GRID),
    xaxis=dict(title="", **_GRID),
    **_LAYOUT,
)
st.plotly_chart(fig_trend, use_container_width=True)

st.divider()

# ── Selected week breakdown ───────────────────────────────────────────────────
section_header(
    f"Week of {selected_week} — Breakdown",
    help="Pay and hours breakdown for the selected payroll week.",
)
wk1, wk2, wk3 = st.columns(3)
with wk1:
    st.metric("Weekly Payroll", format_currency(week_data["gross_pay"].sum()))
with wk2:
    st.metric("Hours Worked", f"{week_data['total_hours'].sum():,.0f} hrs")
with wk3:
    st.metric("Employees", f"{week_data['employee_name'].nunique()}")

# Top earners & hours side by side
c1, c2 = st.columns(2)

top_earn = week_data.nlargest(15, "gross_pay")[["employee_name", "gross_pay", "role"]].copy()
top_earn = top_earn.sort_values("gross_pay")
fig_earn = go.Figure(go.Bar(
    x=top_earn["gross_pay"], y=top_earn["employee_name"],
    orientation="h",
    marker_color=_BRAND, marker_line_width=0,
    text=top_earn["gross_pay"].apply(lambda x: f"${x:,.0f}"),
    textposition="outside", textfont=dict(size=10),
    customdata=top_earn["role"],
    hovertemplate="%{y}<br>%{customdata}<br>$%{x:,.2f}<extra></extra>",
))
fig_earn.update_layout(
    title="Top Earners — Gross Pay",
    xaxis=dict(tickprefix="$", **_GRID),
    yaxis=dict(automargin=True),
    **_LAYOUT,
)
with c1:
    st.plotly_chart(fig_earn, use_container_width=True)

top_hrs = week_data.nlargest(15, "total_hours")[["employee_name", "total_hours", "role"]].copy()
top_hrs = top_hrs.sort_values("total_hours")
fig_hrs = go.Figure(go.Bar(
    x=top_hrs["total_hours"], y=top_hrs["employee_name"],
    orientation="h",
    marker_color=_BLUE, marker_line_width=0,
    text=top_hrs["total_hours"].apply(lambda x: f"{x:.1f} hrs"),
    textposition="outside", textfont=dict(size=10),
    customdata=top_hrs["role"],
    hovertemplate="%{y}<br>%{customdata}<br>%{x:.1f} hrs<extra></extra>",
))
fig_hrs.update_layout(
    title="Hours Worked by Employee",
    xaxis=dict(title="Hours", **_GRID),
    yaxis=dict(automargin=True),
    **_LAYOUT,
)
with c2:
    st.plotly_chart(fig_hrs, use_container_width=True)

st.divider()

# ── Pay by role ───────────────────────────────────────────────────────────────
section_header(
    "Pay & Hours by Role",
    help="Total gross pay and hours grouped by job role for the selected week.",
)
role_data = (
    week_data.groupby("role")
    .agg(gross_pay=("gross_pay", "sum"), total_hours=("total_hours", "sum"))
    .reset_index().sort_values("gross_pay", ascending=False)
)
if not role_data.empty:
    fig_role = go.Figure()
    fig_role.add_trace(go.Bar(
        x=role_data["role"], y=role_data["gross_pay"],
        name="Gross Pay",
        marker_color=_BRAND, marker_line_width=0,
        text=role_data["gross_pay"].apply(lambda x: f"${x:,.0f}"),
        textposition="outside", textfont=dict(size=10),
    ))
    fig_role.add_trace(go.Scatter(
        x=role_data["role"], y=role_data["total_hours"],
        name="Total Hours", line=dict(color=_BLUE, width=2),
        yaxis="y2",
    ))
    fig_role.update_layout(
        yaxis=dict(tickprefix="$", title="Gross Pay", **_GRID),
        yaxis2=dict(title="Hours", overlaying="y", side="right", showgrid=False),
        **_LAYOUT,
    )
    st.plotly_chart(fig_role, use_container_width=True)

st.divider()

# ── Payroll detail ────────────────────────────────────────────────────────────
section_header(
    f"Payroll Detail — Week of {selected_week}",
    help="Full payroll breakdown per employee for the selected week.",
)
pd_ = week_data[["employee_name", "dept", "role", "employment_type",
                  "regular_hours", "total_hours", "gross_pay"]].copy()
pd_["gross_pay"]     = pd_["gross_pay"].apply(lambda x: f"${x:,.2f}")
pd_["regular_hours"] = pd_["regular_hours"].apply(lambda x: f"{x:.1f}")
pd_["total_hours"]   = pd_["total_hours"].apply(lambda x: f"{x:.1f}")
pd_ = pd_.sort_values(["dept", "employee_name"])
pd_.columns = ["Employee", "Department", "Role", "Employment Type",
               "Regular Hrs", "Total Hrs", "Gross Pay"]
st.dataframe(pd_, use_container_width=True, height=480, hide_index=True)

st.divider()

# ── All imported payroll data ─────────────────────────────────────────────────
with st.expander("View All Imported Payroll Data", expanded=False):
    st.caption(
        "All payroll records currently stored in the system, regardless of the selected "
        "date range. Use the download button to export as CSV."
    )
    all_payroll = db.get_weekly_payroll(username)
    if all_payroll.empty:
        st.info("No payroll data imported yet.")
    else:
        export_df = all_payroll[[
            "week_start", "week_end", "employee_id", "employee_name",
            "dept", "role", "employment_type",
            "hourly_rate", "regular_hours", "overtime_hours", "total_hours", "gross_pay",
        ]].copy().sort_values(["week_start", "employee_name"])
        export_df.columns = [
            "Week Start", "Week End", "Employee ID", "Employee Name",
            "Department", "Role", "Employment Type",
            "Hourly Rate", "Regular Hours", "Overtime Hours", "Total Hours", "Gross Pay",
        ]
        st.dataframe(export_df, use_container_width=True, hide_index=True)
        st.caption(
            f"{len(export_df):,} records · "
            f"{export_df['Employee Name'].nunique()} employees · "
            f"{export_df['Week Start'].nunique()} pay periods "
            f"({export_df['Week Start'].min()} → {export_df['Week End'].max()})"
        )
        st.download_button(
            "Download as CSV",
            data=export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"payroll_{username}.csv",
            mime="text/csv",
        )

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

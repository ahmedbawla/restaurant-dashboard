"""
Payroll & Labour — Paychex data.
"""

import json
from pathlib import Path

import streamlit as st

from components.charts import labor_cost_gauge, labor_trend, hours_by_dept, labor_pct_by_dept
from components.kpi_card import format_currency, format_pct
from components.theme import page_header, section_header
from data import database as db

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)
THRESHOLDS    = CONFIG.get("thresholds", {})
OT_THRESHOLD  = THRESHOLDS.get("overtime_hours_weekly", 40)
LABOR_TARGET  = THRESHOLDS.get("labor_cost_pct_target",  30.0)
LABOR_WARNING = THRESHOLDS.get("labor_cost_pct_warning", 33.0)

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "👥 Payroll & Labour",
    subtitle="Labour cost analysis and payroll summary sourced from Paychex.",
    eyebrow="Workforce Analytics",
)

# ── Data ─────────────────────────────────────────────────────────────────────
daily_labor    = db.get_daily_labor(username,    start_date=start_date, end_date=end_date)
weekly_payroll = db.get_weekly_payroll(username, start_date=start_date, end_date=end_date)
daily_sales    = db.get_daily_sales(username,    start_date=start_date, end_date=end_date)

if daily_labor.empty or weekly_payroll.empty:
    st.warning("No labour data found for the selected period.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    available_weeks = sorted(weekly_payroll["week_start"].unique(), reverse=True)
    selected_week   = st.selectbox("Payroll Week", available_weeks)

week_data = weekly_payroll[weekly_payroll["week_start"] == selected_week]

# ── Computed metrics ──────────────────────────────────────────────────────────
recent_date      = daily_labor.sort_values("date")["date"].iloc[-1]
recent_day_labor = daily_labor[daily_labor["date"] == recent_date]["labor_cost"].sum()
rev_row          = daily_sales[daily_sales["date"] == recent_date]["revenue"]
recent_revenue   = float(rev_row.iloc[0]) if not rev_row.empty else 1.0
labor_pct        = recent_day_labor / recent_revenue * 100

labor_by_day = daily_labor.groupby("date")["labor_cost"].sum().reset_index()
merged       = labor_by_day.merge(daily_sales[["date","revenue"]], on="date", how="inner")
merged["labor_pct"] = merged["labor_cost"] / merged["revenue"] * 100
avg_lp = merged["labor_pct"].mean() if not merged.empty else 0.0

weekly_total = week_data["gross_pay"].sum()
total_hours  = week_data["total_hours"].sum()
ot_employees = week_data[week_data["overtime_hours"] > 0]
rev_per_lhr  = recent_revenue / max(1, daily_labor[daily_labor["date"] == recent_date]["hours"].sum())
period_labor_total = daily_labor["labor_cost"].sum()
period_revenue     = daily_sales["revenue"].sum()
period_labor_pct   = period_labor_total / period_revenue * 100 if period_revenue else 0.0

# ── Overtime alert banner ─────────────────────────────────────────────────────
if not ot_employees.empty:
    n_ot = len(ot_employees)
    st.warning(
        f"**{n_ot} employee{'s' if n_ot > 1 else ''}** logged overtime in the selected week. "
        "Review the Overtime Alerts section below."
    )

# ── KPI strip ─────────────────────────────────────────────────────────────────
section_header("Labour Overview")
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Labor % (Latest Day)", f"{labor_pct:.1f}%",
              delta=f"Avg: {avg_lp:.1f}%", delta_color="off")
with k2:
    st.metric("Period Labor %",       f"{period_labor_pct:.1f}%",
              help="Total labor cost as % of total revenue for the selected period.")
with k3:
    st.metric(f"Weekly Payroll",      format_currency(weekly_total),
              help=f"Week of {selected_week}")
with k4:
    st.metric("Total Hours (Week)",   f"{total_hours:,.0f} hrs")
with k5:
    st.metric("Rev per Labor Hour",   format_currency(rev_per_lhr),
              help="Latest day revenue divided by hours worked.")

st.divider()

# ── Gauge + Dept hours/pay ────────────────────────────────────────────────────
section_header("Cost Gauges")
col1, col2 = st.columns([1, 2])
with col1:
    st.plotly_chart(
        labor_cost_gauge(labor_pct, target=LABOR_TARGET, warning=LABOR_WARNING),
        use_container_width=True,
    )
with col2:
    st.plotly_chart(hours_by_dept(weekly_payroll, week=selected_week), use_container_width=True)

st.divider()

# ── Labor % by department ─────────────────────────────────────────────────────
section_header("Labor Cost % by Department")
col_dept, col_trend = st.columns(2)
with col_dept:
    st.plotly_chart(labor_pct_by_dept(weekly_payroll, daily_sales), use_container_width=True)
with col_trend:
    st.plotly_chart(labor_trend(daily_labor, daily_sales), use_container_width=True)

st.divider()

# ── Overtime alerts ───────────────────────────────────────────────────────────
section_header("Overtime Alerts")
if ot_employees.empty:
    st.success(f"No employees exceeded {OT_THRESHOLD} hours during the selected week.")
else:
    ot = ot_employees[["employee_name","dept","role","regular_hours","overtime_hours","total_hours","gross_pay"]].copy()
    ot["gross_pay"]      = ot["gross_pay"].apply(lambda x: f"${x:,.2f}")
    ot["overtime_hours"] = ot["overtime_hours"].apply(lambda x: f"{x:.1f} hrs")
    ot["regular_hours"]  = ot["regular_hours"].apply(lambda x: f"{x:.1f} hrs")
    ot["total_hours"]    = ot["total_hours"].apply(lambda x: f"{x:.1f} hrs")
    ot.columns = ["Employee","Department","Role","Regular Hours","Overtime Hours","Total Hours","Gross Pay"]
    st.dataframe(ot, use_container_width=True, hide_index=True)

# ── Payroll detail ────────────────────────────────────────────────────────────
st.divider()
section_header(f"Payroll Detail — Week of {selected_week}")
pd_ = week_data[["employee_name","dept","role","employment_type","regular_hours",
                  "overtime_hours","total_hours","gross_pay"]].copy()
pd_["gross_pay"]      = pd_["gross_pay"].apply(lambda x: f"${x:,.2f}")
pd_["regular_hours"]  = pd_["regular_hours"].apply(lambda x: f"{x:.1f}")
pd_["overtime_hours"] = pd_["overtime_hours"].apply(lambda x: f"{x:.1f}")
pd_["total_hours"]    = pd_["total_hours"].apply(lambda x: f"{x:.1f}")
pd_ = pd_.sort_values(["dept","employee_name"])
pd_.columns = ["Employee","Department","Role","Employment Type","Regular Hrs","Overtime Hrs","Total Hrs","Gross Pay"]
st.dataframe(pd_, use_container_width=True, height=480, hide_index=True)

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

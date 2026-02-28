"""
Payroll page — Paychex labor data.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import streamlit as st
import pandas as pd

from components.charts import labor_cost_gauge, labor_trend, hours_by_dept
from components.kpi_card import format_currency, format_pct
from data import database as db

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)

THRESHOLDS = CONFIG.get("thresholds", {})
OT_THRESHOLD = THRESHOLDS.get("overtime_hours_weekly", 40)

st.set_page_config(page_title="Payroll — BI Dashboard", layout="wide")
st.title("👥 Payroll & Labor")
st.caption("Source: Paychex")
st.divider()

# ── Data ─────────────────────────────────────────────────────────────────────
daily_labor = db.get_daily_labor(days=90)
weekly_payroll = db.get_weekly_payroll(weeks=13)
daily_sales = db.get_daily_sales(days=90)

if daily_labor.empty or weekly_payroll.empty:
    st.error("No labor data. Run `python data/sync.py` first.")
    st.stop()

# ── Week selector ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    available_weeks = sorted(weekly_payroll["week_start"].unique(), reverse=True)
    selected_week = st.selectbox("Payroll Week", available_weeks)

week_data = weekly_payroll[weekly_payroll["week_start"] == selected_week]

# ── KPIs ─────────────────────────────────────────────────────────────────────
# Labor cost % for most recent day
recent_labor = daily_labor.sort_values("date").tail(4)
recent_date = recent_labor["date"].iloc[-1]
recent_day_labor = daily_labor[daily_labor["date"] == recent_date]["labor_cost"].sum()
recent_day_sales = daily_sales[daily_sales["date"] == recent_date]["revenue"]
recent_revenue = float(recent_day_sales.iloc[0]) if not recent_day_sales.empty else 1
labor_pct = recent_day_labor / recent_revenue * 100

weekly_total = week_data["gross_pay"].sum()
total_hours = week_data["total_hours"].sum()
ot_employees = week_data[week_data["overtime_hours"] > 0]
rev_per_labor_hr = recent_revenue / max(1, recent_labor["hours"].sum())

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Labor Cost % (Today)", f"{labor_pct:.1f}%",
              delta=f"Target: {THRESHOLDS.get('labor_cost_pct_target', 30)}%",
              delta_color="off")
with k2:
    st.metric(f"Weekly Payroll ({selected_week})", format_currency(weekly_total))
with k3:
    st.metric("Total Hours (Week)", f"{total_hours:,.1f} hrs")
with k4:
    st.metric("Revenue per Labor Hour", format_currency(rev_per_labor_hr))

st.divider()

# ── Gauge + Hours by dept ────────────────────────────────────────────────────
col1, col2 = st.columns([1, 2])
with col1:
    st.plotly_chart(
        labor_cost_gauge(
            labor_pct,
            target=THRESHOLDS.get("labor_cost_pct_target", 30),
            warning=THRESHOLDS.get("labor_cost_pct_warning", 33),
        ),
        use_container_width=True,
    )
with col2:
    st.plotly_chart(hours_by_dept(weekly_payroll, week=selected_week), use_container_width=True)

# ── Labor trend ───────────────────────────────────────────────────────────────
st.plotly_chart(labor_trend(daily_labor, daily_sales), use_container_width=True)

st.divider()

# ── Overtime alerts ───────────────────────────────────────────────────────────
st.subheader("⚠️ Overtime Alerts")
if ot_employees.empty:
    st.success(f"No employees exceeded {OT_THRESHOLD} hours this week.")
else:
    ot_display = ot_employees[["employee_name", "dept", "role", "regular_hours", "overtime_hours", "total_hours", "gross_pay"]].copy()
    ot_display["gross_pay"] = ot_display["gross_pay"].apply(lambda x: f"${x:,.2f}")
    ot_display["overtime_hours"] = ot_display["overtime_hours"].apply(lambda x: f"⚠️ {x:.1f}")
    st.dataframe(ot_display, use_container_width=True)

# ── Full payroll table ────────────────────────────────────────────────────────
st.divider()
st.subheader("Weekly Payroll Detail")
payroll_display = week_data[["employee_name", "dept", "role", "employment_type",
                              "regular_hours", "overtime_hours", "total_hours", "gross_pay"]].copy()
payroll_display["gross_pay"] = payroll_display["gross_pay"].apply(lambda x: f"${x:,.2f}")
payroll_display = payroll_display.sort_values(["dept", "employee_name"])
st.dataframe(payroll_display, use_container_width=True, height=500)

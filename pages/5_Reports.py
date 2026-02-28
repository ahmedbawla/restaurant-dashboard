"""
Reports — generate, download, and email performance reports.
"""

import json
from datetime import date
from pathlib import Path

import streamlit as st

from components.kpi_card import format_currency, format_pct, threshold_badge
from components.charts import (
    revenue_trend, food_cost_trend, labor_trend,
    expense_pie, top_vendors_bar, top_items_bar,
)
from components.theme import page_header
from data import database as db
from utils.pdf_generator import generate_pdf
from utils.report_generator import send_email_report, generate_html_report

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)
THRESHOLDS = CONFIG.get("thresholds", {})

user       = st.session_state["user"]
username   = user["username"]
user_email = user.get("email") or ""
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "📄 Reports & Analytics",
    subtitle=f"Generate, export, and distribute performance reports for {user['restaurant_name']}.",
    eyebrow="Reporting",
)
st.divider()

# ── Section selection ─────────────────────────────────────────────────────────
st.subheader("Report Sections")
st.caption("Select the sections to include in this report.")

col_a, col_b, col_c = st.columns(3)
with col_a:
    inc_exec     = st.checkbox("Executive Summary",        value=True)
    inc_revenue  = st.checkbox("Revenue & Sales",          value=True)
with col_b:
    inc_labor    = st.checkbox("Labour & Payroll",         value=True)
    inc_food     = st.checkbox("Food Cost & Inventory",    value=True)
with col_c:
    inc_expenses = st.checkbox("Expense Analysis",         value=True)
    inc_cf       = st.checkbox("Cash Flow",                value=True)

selected = [k for k, v in [
    ("executive", inc_exec), ("revenue", inc_revenue), ("labor", inc_labor),
    ("food_cost", inc_food), ("expenses", inc_expenses), ("cash_flow", inc_cf),
] if v]

st.divider()

# ── Action bar ────────────────────────────────────────────────────────────────
st.subheader("Export")
b1, b2, b3, _ = st.columns([1, 1, 1, 2])
gen     = b1.button("🔄 Preview Report",  use_container_width=True)
dl_pdf  = b2.button("📥 Download PDF",    use_container_width=True)
do_email = b3.button(
    f"📧 Email to {user_email}" if user_email else "📧 Email Report",
    use_container_width=True,
    disabled=not user_email,
)

if not user_email:
    st.caption("⚠️ No email on file. Add one in Account Settings.")

# ── Load data (shared) ────────────────────────────────────────────────────────
if gen or dl_pdf or (do_email and user_email):
    if not selected:
        st.warning("Select at least one section.")
        st.stop()

    with st.spinner("Loading data…"):
        ds  = db.get_daily_sales(username,    start_date=start_date, end_date=end_date)
        dl_ = db.get_daily_labor(username,    start_date=start_date, end_date=end_date)
        wp  = db.get_weekly_payroll(username, start_date=start_date, end_date=end_date)
        exp = db.get_expenses(username,       start_date=start_date, end_date=end_date)
        cf  = db.get_cash_flow(username,      start_date=start_date, end_date=end_date)
        mi  = db.get_menu_items(username)

    kwargs = dict(
        user=user, daily_sales=ds, daily_labor=dl_, weekly_payroll=wp,
        expenses=exp, cash_flow=cf, menu_items=mi,
        sections=selected, thresholds=THRESHOLDS,
        start_date=start_date or "", end_date=end_date or "",
    )

    # ── PDF download ──────────────────────────────────────────────────────────
    if dl_pdf:
        with st.spinner("Generating PDF…"):
            pdf_bytes = generate_pdf(**kwargs)
        fname = f"{user['restaurant_name'].replace(' ', '_')}_Report_{date.today()}.pdf"
        st.download_button(
            "⬇️ Save PDF",
            data=pdf_bytes,
            file_name=fname,
            mime="application/pdf",
        )

    # ── Email ─────────────────────────────────────────────────────────────────
    if do_email and user_email:
        with st.spinner(f"Sending report to {user_email}…"):
            html = generate_html_report(**{
                k: v for k, v in kwargs.items()
                if k not in ("start_date", "end_date")
            })
            err = send_email_report(
                user_email,
                f"{user['restaurant_name']} — Performance Report ({date.today().strftime('%B %Y')})",
                html,
            )
        if err:
            st.error(f"Email failed: {err}")
        else:
            st.success(f"Report sent to {user_email}")

    # ── Preview ───────────────────────────────────────────────────────────────
    if gen:
        st.divider()
        st.subheader("Report Preview")

        food_target  = THRESHOLDS.get("food_cost_pct_target",  30.0)
        food_warning = THRESHOLDS.get("food_cost_pct_warning", 33.0)
        labor_target  = THRESHOLDS.get("labor_cost_pct_target",  30.0)
        labor_warning = THRESHOLDS.get("labor_cost_pct_warning", 33.0)

        import pandas as pd

        if "executive" in selected and not ds.empty:
            st.markdown("## Executive Summary")
            labor_by_day = dl_.groupby("date")["labor_cost"].sum().reset_index() if not dl_.empty else pd.DataFrame(columns=["date","labor_cost"])
            merged = labor_by_day.merge(ds[["date","revenue"]], on="date", how="inner") if not ds.empty else pd.DataFrame()
            avg_lp = float((merged["labor_cost"]/merged["revenue"]*100).mean()) if not merged.empty else 0.0
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Total Revenue",     format_currency(ds["revenue"].sum()))
            c2.metric("Avg. Daily Revenue",format_currency(ds["revenue"].mean()))
            c3.metric("Avg. Food Cost %",  threshold_badge(ds["food_cost_pct"].mean(), food_target, food_warning))
            c4.metric("Avg. Labour Cost %",threshold_badge(avg_lp, labor_target, labor_warning))

        if "revenue" in selected and not ds.empty:
            st.markdown("## Revenue & Sales Analysis")
            st.plotly_chart(revenue_trend(ds, days=len(ds)), use_container_width=True)
            ds_m = ds.copy()
            ds_m["month"] = pd.to_datetime(ds_m["date"]).dt.to_period("M").astype(str)
            m = ds_m.groupby("month").agg(Revenue=("revenue","sum"),Covers=("covers","sum"),Avg_Check=("avg_check","mean"),Food_Pct=("food_cost_pct","mean")).reset_index().sort_values("month",ascending=False)
            m["Revenue"]   = m["Revenue"].apply(format_currency)
            m["Avg_Check"] = m["Avg_Check"].apply(format_currency)
            m["Food_Pct"]  = m["Food_Pct"].apply(format_pct)
            m["Covers"]    = m["Covers"].apply(lambda x: f"{x:,.0f}")
            m.columns = ["Month","Revenue","Covers","Avg. Check","Food Cost %"]
            st.dataframe(m, use_container_width=True, hide_index=True)

        if "labor" in selected and not dl_.empty:
            st.markdown("## Labour & Payroll")
            if not ds.empty: st.plotly_chart(labor_trend(dl_, ds), use_container_width=True)
            if not wp.empty:
                dept = wp.groupby("dept").agg(Employees=("employee_id","nunique"),Total_Hours=("total_hours","sum"),Gross_Pay=("gross_pay","sum")).reset_index().sort_values("Gross_Pay",ascending=False)
                dept["Gross_Pay"]   = dept["Gross_Pay"].apply(format_currency)
                dept["Total_Hours"] = dept["Total_Hours"].apply(lambda x: f"{x:,.1f} hrs")
                dept.columns = ["Department","Employees","Total Hours","Gross Pay"]
                st.dataframe(dept, use_container_width=True, hide_index=True)

        if "food_cost" in selected and not ds.empty:
            st.markdown("## Food Cost & Inventory")
            st.plotly_chart(food_cost_trend(ds), use_container_width=True)
            if not mi.empty: st.plotly_chart(top_items_bar(mi, metric="total_revenue"), use_container_width=True)

        if "expenses" in selected and not exp.empty:
            st.markdown("## Expense Analysis")
            c1,c2 = st.columns(2)
            with c1: st.plotly_chart(expense_pie(exp), use_container_width=True)
            with c2: st.plotly_chart(top_vendors_bar(exp), use_container_width=True)

        if "cash_flow" in selected and not cf.empty:
            st.markdown("## Cash Flow")
            c1,c2,c3 = st.columns(3)
            c1.metric("Total Inflows",  format_currency(cf["inflow"].sum()))
            c2.metric("Total Outflows", format_currency(cf["outflow"].sum()))
            c3.metric("Net Position",   format_currency(cf["net"].sum()))

        st.divider()
        st.caption(
            f"🔒 Confidential  ·  {user['restaurant_name']}  ·  "
            f"Period: {start_date} – {end_date}  ·  "
            f"Generated {date.today().strftime('%B %d, %Y')}"
        )

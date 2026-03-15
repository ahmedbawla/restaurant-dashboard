"""
Reports — generate, download, and analyse performance reports.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from components.kpi_card import format_currency, format_pct, threshold_badge
from components.charts import (
    revenue_trend, food_cost_trend, labor_trend,
    expense_pie, top_vendors_bar, top_items_bar,
)
from components.theme import page_header
from data import database as db
from utils.pdf_generator import generate_pdf

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)
THRESHOLDS = CONFIG.get("thresholds", {})

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "📄 Reports & Analytics",
    subtitle=f"Generate and export performance reports for {user['restaurant_name']}.",
    eyebrow="Reporting",
)
st.divider()

# ── NL report trigger (test account only) ────────────────────────────────────
_nl_gen   = False
_nl_start = _nl_end = _nl_secs = None

if username == "test":
    with st.expander("💬 Generate with natural language", expanded=False):
        st.caption("Describe the report you want — include a date range and optionally a topic.")
        _rq = st.text_input(
            "What report?",
            placeholder='e.g. "q1 2025 payroll", "revenue for february 2025", "all sections last month"',
            key="nl_report_query",
            label_visibility="collapsed",
        )
        if _rq.strip():
            import re as _rre, calendar as _rrc
            from datetime import timedelta as _rtd
            _rqt    = _rq.strip().lower()
            _rtoday = date.today()
            _MNLM   = {
                "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
                "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
                "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
                "sep":9,"oct":10,"nov":11,"dec":12,
            }
            # Sections from keywords
            _skw = {
                "executive": any(w in _rqt for w in ("exec","summary","overview","all","full")),
                "revenue":   any(w in _rqt for w in ("revenue","sales","income","all","full")),
                "labor":     any(w in _rqt for w in ("payroll","labor","labour","staff","wages","hours","all","full")),
                "food_cost": any(w in _rqt for w in ("food","inventory","all","full")),
                "expenses":  any(w in _rqt for w in ("expense","spend","spending","all","full")),
                "cash_flow": any(w in _rqt for w in ("cash","flow","all","full")),
            }
            _nl_secs = [k for k, v in _skw.items() if v] or list(_skw.keys())
            # Date parse
            if "last month" in _rqt:
                _prev = _rtoday.replace(day=1) - _rtd(days=1)
                _nl_start, _nl_end = date(_prev.year, _prev.month, 1), _prev
            elif "this month" in _rqt:
                _nl_start = _rtoday.replace(day=1)
                _nl_end   = date(_rtoday.year, _rtoday.month, _rrc.monthrange(_rtoday.year, _rtoday.month)[1])
            elif "last year" in _rqt:
                _nl_start, _nl_end = date(_rtoday.year-1, 1, 1), date(_rtoday.year-1, 12, 31)
            elif "this year" in _rqt:
                _nl_start, _nl_end = date(_rtoday.year, 1, 1), _rtoday
            else:
                _qm2 = _rre.search(r"q([1-4])\s*(\d{4})", _rqt) or _rre.search(r"(\d{4})\s*q([1-4])", _rqt)
                if _qm2:
                    _g2 = _qm2.groups()
                    _q2, _y2 = (int(_g2[0]), int(_g2[1])) if len(_g2[0]) == 1 else (int(_g2[1]), int(_g2[0]))
                    _sm2, _em2 = (_q2-1)*3+1, _q2*3
                    _nl_start = date(_y2, _sm2, 1)
                    _nl_end   = date(_y2, _em2, _rrc.monthrange(_y2, _em2)[1])
                else:
                    for _mn, _mnum in _MNLM.items():
                        if _rre.search(r"\b" + _mn + r"\b", _rqt):
                            _ym2 = _rre.search(r"\b(\d{4})\b", _rqt)
                            _y2  = int(_ym2.group(1)) if _ym2 else _rtoday.year
                            _nl_start = date(_y2, _mnum, 1)
                            _nl_end   = date(_y2, _mnum, _rrc.monthrange(_y2, _mnum)[1])
                            break
                    if _nl_start is None:
                        _ym2 = _rre.search(r"\b(20\d{2}|19\d{2})\b", _rqt)
                        if _ym2:
                            _y2 = int(_ym2.group(1))
                            _nl_start, _nl_end = date(_y2, 1, 1), date(_y2, 12, 31)
            _SL = {
                "executive":"Executive Summary","revenue":"Revenue & Sales",
                "labor":"Labour & Payroll","food_cost":"Food Cost & Inventory",
                "expenses":"Expense Analysis","cash_flow":"Cash Flow",
            }
            if _nl_start and _nl_end:
                st.info(
                    f"**{' · '.join(_SL[s] for s in _nl_secs)}**  \n"
                    f"📅 {_nl_start.strftime('%b %d, %Y')} → {_nl_end.strftime('%b %d, %Y')}"
                )
                _nl_gen = st.button("▶ Generate Report", key="nl_gen_btn", type="primary")
            else:
                st.warning("Couldn't find a date range. Try: *q1 2025*, *february 2025*, *last month*, *2024*")

st.divider()


# ── Insight card helper ───────────────────────────────────────────────────────
def _insights(items: list[tuple[str, str]]) -> None:
    """Render a styled insight card. Each item is (icon, html-safe text)."""
    if not items:
        return
    rows = "".join(
        f"<div style='margin-bottom:0.38rem;'>"
        f"<span style='margin-right:0.45rem;'>{icon}</span>{text}</div>"
        for icon, text in items
    )
    st.markdown(
        f"<div style='background:rgba(212,168,75,0.07);"
        f"border:1px solid rgba(212,168,75,0.22);border-radius:10px;"
        f"padding:0.85rem 1.15rem;margin:0.5rem 0 1rem 0;font-size:0.87rem;"
        f"color:rgba(240,242,246,0.85);line-height:1.7;'>{rows}</div>",
        unsafe_allow_html=True,
    )


# ── Section selection ─────────────────────────────────────────────────────────
st.subheader("Report Sections")
st.caption("Select the sections to include in this report.")

col_a, col_b, col_c = st.columns(3)
with col_a:
    inc_exec     = st.checkbox("Executive Summary",     value=True)
    inc_revenue  = st.checkbox("Revenue & Sales",       value=True)
with col_b:
    inc_labor    = st.checkbox("Labour & Payroll",      value=True)
    inc_food     = st.checkbox("Food Cost & Inventory", value=True)
with col_c:
    inc_expenses = st.checkbox("Expense Analysis",      value=True)
    inc_cf       = st.checkbox("Cash Flow",             value=True)

selected = [k for k, v in [
    ("executive", inc_exec), ("revenue", inc_revenue), ("labor", inc_labor),
    ("food_cost", inc_food), ("expenses", inc_expenses), ("cash_flow", inc_cf),
] if v]

# NL override (must come after checkboxes so selected/dates are defined)
if _nl_gen and _nl_start and _nl_end:
    start_date = _nl_start.isoformat()
    end_date   = _nl_end.isoformat()
    selected   = _nl_secs

st.divider()

# ── Action bar ────────────────────────────────────────────────────────────────
st.subheader("Export")
b1, b2, _ = st.columns([1, 1, 3])
gen    = b1.button("🔄 Preview Report", use_container_width=True)
dl_pdf = b2.button("📥 Download PDF",   use_container_width=True)

# ── Load data (shared) ────────────────────────────────────────────────────────
if gen or dl_pdf or _nl_gen:
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

    # ── Preview ───────────────────────────────────────────────────────────────
    if gen:
        food_target   = THRESHOLDS.get("food_cost_pct_target",  30.0)
        food_warning  = THRESHOLDS.get("food_cost_pct_warning", 33.0)
        labor_target  = THRESHOLDS.get("labor_cost_pct_target",  30.0)
        labor_warning = THRESHOLDS.get("labor_cost_pct_warning", 33.0)

        st.divider()
        st.subheader("Report Preview")

        # ── Executive Summary ─────────────────────────────────────────────────
        if "executive" in selected and not ds.empty:
            st.markdown("## Executive Summary")

            labor_by_day = (
                dl_.groupby("date")["labor_cost"].sum().reset_index()
                if not dl_.empty
                else pd.DataFrame(columns=["date", "labor_cost"])
            )
            merged_exec = (
                labor_by_day.merge(ds[["date", "revenue"]], on="date", how="inner")
                if not ds.empty else pd.DataFrame()
            )
            avg_lp = float(
                (merged_exec["labor_cost"] / merged_exec["revenue"] * 100).mean()
            ) if not merged_exec.empty else 0.0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Revenue",      format_currency(ds["revenue"].sum()))
            c2.metric("Avg. Daily Revenue", format_currency(ds["revenue"].mean()))
            c3.metric("Avg. Food Cost %",   threshold_badge(ds["food_cost_pct"].mean(), food_target, food_warning))
            c4.metric("Avg. Labour Cost %", threshold_badge(avg_lp, labor_target, labor_warning))

            # ── Insights ──────────────────────────────────────────────────────
            exec_ins = []

            # Revenue trend: first half vs second half
            if len(ds) >= 4:
                mid = len(ds) // 2
                fh_avg = ds["revenue"].iloc[:mid].mean()
                sh_avg = ds["revenue"].iloc[mid:].mean()
                pct_chg = (sh_avg - fh_avg) / fh_avg * 100
                if pct_chg >= 5:
                    exec_ins.append(("📈", f"Revenue trended <strong>up {pct_chg:.1f}%</strong> in the second half of the period vs the first half ({format_currency(fh_avg)}/day → {format_currency(sh_avg)}/day)."))
                elif pct_chg <= -5:
                    exec_ins.append(("📉", f"Revenue trended <strong>down {abs(pct_chg):.1f}%</strong> in the second half of the period ({format_currency(fh_avg)}/day → {format_currency(sh_avg)}/day). Investigate what changed mid-period."))
                else:
                    exec_ins.append(("➡️", f"Revenue was <strong>relatively stable</strong> across the period ({pct_chg:+.1f}% half-over-half), averaging {format_currency(ds['revenue'].mean())}/day."))

            # Food cost status
            avg_fc = ds["food_cost_pct"].mean()
            days_above_warn = int((ds["food_cost_pct"] > food_warning).sum())
            days_above_tgt  = int((ds["food_cost_pct"] > food_target).sum())
            if days_above_warn > 0:
                exec_ins.append(("🔴", f"Food cost exceeded the <strong>{food_warning}% warning level on {days_above_warn} day{'s' if days_above_warn != 1 else ''}</strong>. Average for the period: {avg_fc:.1f}%."))
            elif days_above_tgt > 0:
                exec_ins.append(("🟡", f"Food cost averaged <strong>{avg_fc:.1f}%</strong> — above the {food_target}% target on {days_above_tgt} day{'s' if days_above_tgt != 1 else ''} this period."))
            else:
                exec_ins.append(("🟢", f"Food cost averaged <strong>{avg_fc:.1f}%</strong> — within the {food_target}% target throughout the period."))

            # Best revenue day of week
            ds_dow = ds.copy()
            ds_dow["day"] = pd.to_datetime(ds_dow["date"]).dt.day_name()
            ds_dow["day_num"] = pd.to_datetime(ds_dow["date"]).dt.dayofweek
            dow_avg = ds_dow.groupby(["day", "day_num"])["revenue"].mean()
            best_day = dow_avg.idxmax()[0]
            worst_day = dow_avg.idxmin()[0]
            exec_ins.append(("🏆", f"<strong>{best_day}</strong> is your strongest day (avg {format_currency(dow_avg.max())}); <strong>{worst_day}</strong> is the weakest (avg {format_currency(dow_avg.min())})."))

            _insights(exec_ins)

        # ── Revenue & Sales ───────────────────────────────────────────────────
        if "revenue" in selected and not ds.empty:
            st.markdown("## Revenue & Sales Analysis")
            st.plotly_chart(revenue_trend(ds, days=len(ds)), use_container_width=True)

            ds_m = ds.copy()
            ds_m["month"] = pd.to_datetime(ds_m["date"]).dt.to_period("M").astype(str)
            m = (
                ds_m.groupby("month")
                .agg(Revenue=("revenue","sum"), Covers=("covers","sum"),
                     Avg_Check=("avg_check","mean"), Food_Pct=("food_cost_pct","mean"))
                .reset_index().sort_values("month", ascending=False)
            )
            m["Revenue"]   = m["Revenue"].apply(format_currency)
            m["Avg_Check"] = m["Avg_Check"].apply(format_currency)
            m["Food_Pct"]  = m["Food_Pct"].apply(format_pct)
            m["Covers"]    = m["Covers"].apply(lambda x: f"{x:,.0f}")
            m.columns = ["Month", "Revenue", "Covers", "Avg. Check", "Food Cost %"]
            st.dataframe(m, use_container_width=True, hide_index=True)

            # ── Insights ──────────────────────────────────────────────────────
            rev_ins = []

            ds2 = ds.copy()
            ds2["day"]     = pd.to_datetime(ds2["date"]).dt.day_name()
            ds2["day_num"] = pd.to_datetime(ds2["date"]).dt.dayofweek
            dow_rev = ds2.groupby(["day", "day_num"])["revenue"].mean()
            best_d  = dow_rev.idxmax()[0]
            worst_d = dow_rev.idxmin()[0]
            rev_ins.append(("📅", f"By day of week, <strong>{best_d}</strong> averages the most revenue ({format_currency(dow_rev.max())}) and <strong>{worst_d}</strong> the least ({format_currency(dow_rev.min())})."))

            # Average check trend
            if len(ds) >= 14:
                mid = len(ds) // 2
                fh_check = ds["avg_check"].iloc[:mid].mean()
                sh_check = ds["avg_check"].iloc[mid:].mean()
                chk_chg  = (sh_check - fh_check) / fh_check * 100
                if chk_chg >= 2:
                    rev_ins.append(("💳", f"Average check size grew <strong>{chk_chg:.1f}%</strong> across the period ({format_currency(fh_check)} → {format_currency(sh_check)}), indicating stronger spend per guest."))
                elif chk_chg <= -2:
                    rev_ins.append(("💳", f"Average check size declined <strong>{abs(chk_chg):.1f}%</strong> ({format_currency(fh_check)} → {format_currency(sh_check)}). Review menu mix or whether discounting increased."))
                else:
                    rev_ins.append(("💳", f"Average check size held steady at approximately {format_currency(ds['avg_check'].mean())} throughout the period."))

            # Cover count context
            total_covers = int(ds["covers"].sum())
            avg_covers   = ds["covers"].mean()
            rev_ins.append(("👥", f"<strong>{total_covers:,} covers</strong> served during the period, averaging <strong>{avg_covers:,.0f}/day</strong>."))

            # Low-day recommendation
            rev_ins.append(("💡", f"<strong>{worst_d}</strong> consistently underperforms — consider targeted promotions, prix-fixe specials, or adjusted staffing to improve contribution on that day."))

            _insights(rev_ins)

        # ── Labour & Payroll ──────────────────────────────────────────────────
        if "labor" in selected and not dl_.empty:
            st.markdown("## Labour & Payroll")
            if not ds.empty:
                st.plotly_chart(labor_trend(dl_, ds), use_container_width=True)
            if not wp.empty:
                dept = (
                    wp.groupby("dept")
                    .agg(Employees=("employee_id", "nunique"),
                         Total_Hours=("total_hours", "sum"),
                         Gross_Pay=("gross_pay", "sum"))
                    .reset_index().sort_values("Gross_Pay", ascending=False)
                )
                dept["Gross_Pay"]   = dept["Gross_Pay"].apply(format_currency)
                dept["Total_Hours"] = dept["Total_Hours"].apply(lambda x: f"{x:,.1f} hrs")
                dept.columns = ["Department", "Employees", "Total Hours", "Gross Pay"]
                st.dataframe(dept, use_container_width=True, hide_index=True)

            # ── Insights ──────────────────────────────────────────────────────
            labor_ins = []
            if not wp.empty:
                total_pay = wp["gross_pay"].sum()
                total_hrs = wp["total_hours"].sum()
                avg_rate  = total_pay / total_hrs if total_hrs else 0.0
                labor_ins.append(("⏱️", f"Total payroll for the period: <strong>{format_currency(total_pay)}</strong> across <strong>{total_hrs:,.0f} hours</strong> — blended rate of <strong>{format_currency(avg_rate)}/hr</strong>."))

                # Highest-cost department
                dept_pay = wp.groupby("dept")["gross_pay"].sum()
                top_dept     = dept_pay.idxmax()
                top_dept_pct = dept_pay[top_dept] / dept_pay.sum() * 100
                labor_ins.append(("💼", f"<strong>{top_dept}</strong> is the highest payroll department, representing <strong>{top_dept_pct:.1f}%</strong> of total payroll spend ({format_currency(dept_pay[top_dept])})."))

                # Payroll trend across weeks
                wk_totals = wp.groupby("week_start")["gross_pay"].sum().sort_index()
                if len(wk_totals) >= 4:
                    mid = len(wk_totals) // 2
                    fh_pay = wk_totals.iloc[:mid].mean()
                    sh_pay = wk_totals.iloc[mid:].mean()
                    pay_chg = (sh_pay - fh_pay) / fh_pay * 100
                    if pay_chg >= 5:
                        labor_ins.append(("📈", f"Weekly payroll averaged <strong>{format_currency(fh_pay)}</strong> in the first half of the period and <strong>{format_currency(sh_pay)}</strong> in the second half (+{pay_chg:.1f}%). Review whether the increase is from scheduled raises, new hires, or increased hours."))
                    elif pay_chg <= -5:
                        labor_ins.append(("📉", f"Weekly payroll decreased <strong>{abs(pay_chg):.1f}%</strong> across the period ({format_currency(fh_pay)} → {format_currency(sh_pay)}/week)."))
                    else:
                        labor_ins.append(("➡️", f"Weekly payroll was consistent across the period, averaging <strong>{format_currency(wk_totals.mean())}/week</strong>."))

                # Highest earner context
                top_earner_row = wp.groupby("employee_name")["gross_pay"].sum().idxmax()
                top_earner_pay = wp.groupby("employee_name")["gross_pay"].sum().max()
                labor_ins.append(("👤", f"Highest total earner for the period: <strong>{top_earner_row}</strong> at <strong>{format_currency(top_earner_pay)}</strong>."))

            _insights(labor_ins)

        # ── Food Cost & Inventory ─────────────────────────────────────────────
        if "food_cost" in selected and not ds.empty:
            st.markdown("## Food Cost & Inventory")
            st.plotly_chart(food_cost_trend(ds), use_container_width=True)
            if not mi.empty:
                st.plotly_chart(top_items_bar(mi, metric="total_revenue"), use_container_width=True)

            # ── Insights ──────────────────────────────────────────────────────
            food_ins = []
            avg_fc         = ds["food_cost_pct"].mean()
            days_above_tgt = int((ds["food_cost_pct"] > food_target).sum())
            days_above_wn  = int((ds["food_cost_pct"] > food_warning).sum())
            total_days     = len(ds)

            if days_above_wn > 0:
                food_ins.append(("🔴", f"Food cost exceeded the <strong>{food_warning}% warning threshold on {days_above_wn} of {total_days} days</strong>. Pinpoint those specific dates and review purchasing volume, waste logs, or spoilage."))
            elif days_above_tgt > 0:
                food_ins.append(("🟡", f"Food cost averaged <strong>{avg_fc:.1f}%</strong> and was above the {food_target}% target on <strong>{days_above_tgt} of {total_days} days</strong> ({days_above_tgt/total_days*100:.0f}% of the period). Consistent monitoring of high-cost days is advised."))
            else:
                food_ins.append(("🟢", f"Food cost averaged <strong>{avg_fc:.1f}%</strong> and stayed within the {food_target}% target on every day in the period."))

            # Worst food cost day
            worst_row = ds.loc[ds["food_cost_pct"].idxmax()]
            food_ins.append(("📍", f"Highest food cost day: <strong>{worst_row['date']}</strong> at <strong>{worst_row['food_cost_pct']:.1f}%</strong> on revenue of {format_currency(worst_row['revenue'])}. Investigate purchasing or waste events on that date."))

            # Food cost trend direction
            if len(ds) >= 14:
                mid = len(ds) // 2
                fh_fc = ds["food_cost_pct"].iloc[:mid].mean()
                sh_fc = ds["food_cost_pct"].iloc[mid:].mean()
                fc_chg = sh_fc - fh_fc
                if fc_chg >= 1.0:
                    food_ins.append(("📈", f"Food cost trended <strong>higher</strong> in the second half of the period ({fh_fc:.1f}% → {sh_fc:.1f}%). Review whether input costs rose or portion control slipped."))
                elif fc_chg <= -1.0:
                    food_ins.append(("📉", f"Food cost improved in the second half of the period ({fh_fc:.1f}% → {sh_fc:.1f}%), suggesting purchasing or waste controls are working."))

            # Top menu item
            if not mi.empty:
                top_item = mi.loc[mi["total_revenue"].idxmax()]
                low_margin = mi[mi["margin_pct"] < mi["margin_pct"].median()]
                food_ins.append(("🍽️", f"Top revenue item: <strong>{top_item['name']}</strong> ({format_currency(top_item['total_revenue'])}, {int(top_item['quantity_sold']):,} sold)."))
                if not low_margin.empty:
                    food_ins.append(("💡", f"<strong>{len(low_margin)} menu item{'s' if len(low_margin) != 1 else ''}</strong> are below the median margin. Review pricing or ingredient costs on those items to improve overall food cost."))

            _insights(food_ins)

        # ── Expense Analysis ──────────────────────────────────────────────────
        if "expenses" in selected and not exp.empty:
            st.markdown("## Expense Analysis")
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(expense_pie(exp), use_container_width=True)
            with c2:
                st.plotly_chart(top_vendors_bar(exp), use_container_width=True)

            # ── Insights ──────────────────────────────────────────────────────
            exp_ins = []
            total_exp   = exp["amount"].sum()
            cat_totals  = exp.groupby("category")["amount"].sum().sort_values(ascending=False)
            top_cat     = cat_totals.index[0]
            top_cat_pct = cat_totals.iloc[0] / total_exp * 100
            exp_ins.append(("📦", f"<strong>{top_cat}</strong> is the largest expense category at <strong>{format_currency(cat_totals.iloc[0])}</strong> ({top_cat_pct:.1f}% of total spend for the period)."))

            vendor_totals = exp.groupby("vendor")["amount"].sum().sort_values(ascending=False)
            top_vendor    = vendor_totals.index[0]
            exp_ins.append(("🏪", f"<strong>{top_vendor}</strong> is your largest vendor at <strong>{format_currency(vendor_totals.iloc[0])}</strong>. If you have multiple vendors in {top_cat}, consider whether consolidation could improve pricing."))

            # Month-over-month expense trend
            exp_copy = exp.copy()
            exp_copy["month"] = pd.to_datetime(exp_copy["date"]).dt.to_period("M").astype(str)
            monthly_exp = exp_copy.groupby("month")["amount"].sum().sort_index()
            if len(monthly_exp) >= 2:
                fh_exp  = monthly_exp.iloc[0]
                sh_exp  = monthly_exp.iloc[-1]
                exp_chg = (sh_exp - fh_exp) / fh_exp * 100
                if exp_chg >= 5:
                    exp_ins.append(("📈", f"Expenses rose <strong>{exp_chg:.1f}%</strong> from {monthly_exp.index[0]} ({format_currency(fh_exp)}) to {monthly_exp.index[-1]} ({format_currency(sh_exp)}). Verify this aligns with revenue growth; if revenue did not grow proportionally, review discretionary spend."))
                elif exp_chg <= -5:
                    exp_ins.append(("📉", f"Expenses decreased <strong>{abs(exp_chg):.1f}%</strong> from {monthly_exp.index[0]} to {monthly_exp.index[-1]} — a positive efficiency trend."))

            # Concentration risk: if top 2 categories > 70%
            if len(cat_totals) >= 2:
                top2_pct = (cat_totals.iloc[0] + cat_totals.iloc[1]) / total_exp * 100
                if top2_pct > 70:
                    exp_ins.append(("⚠️", f"Your top 2 categories (<strong>{cat_totals.index[0]}</strong> and <strong>{cat_totals.index[1]}</strong>) account for <strong>{top2_pct:.0f}%</strong> of all expenses. High concentration means cost shocks in these areas have an outsized impact."))

            _insights(exp_ins)

        # ── Cash Flow ─────────────────────────────────────────────────────────
        if "cash_flow" in selected and not cf.empty:
            st.markdown("## Cash Flow")
            c1, c2, c3 = st.columns(3)
            total_in  = cf["inflow"].sum()
            total_out = cf["outflow"].sum()
            net_total = cf["net"].sum()
            c1.metric("Total Inflows",  format_currency(total_in))
            c2.metric("Total Outflows", format_currency(total_out))
            c3.metric("Net Position",   format_currency(net_total))

            # ── Insights ──────────────────────────────────────────────────────
            cf_ins = []
            neg_days   = int((cf["net"] < 0).sum())
            total_days = len(cf)
            ratio      = total_out / total_in * 100 if total_in else 0.0

            if net_total >= 0:
                cf_ins.append(("🟢", f"Net cash position for the period is <strong>{format_currency(net_total)}</strong> — positive overall. Outflows represent <strong>{ratio:.1f}%</strong> of inflows."))
            else:
                cf_ins.append(("🔴", f"Net cash position is <strong>{format_currency(net_total)}</strong> — <strong>negative for the period</strong>. Outflows exceeded inflows by {format_currency(abs(net_total))}. Review the largest outflow categories to identify reductions."))

            if neg_days > 0:
                cf_ins.append(("⚠️", f"Cash flow was negative on <strong>{neg_days} of {total_days} days</strong> ({neg_days/total_days*100:.0f}% of the period). Identify whether these cluster around specific days of the week or month-end payment cycles."))
            else:
                cf_ins.append(("✅", f"Cash flow was positive on every day in the period — no negative-net days recorded."))

            # Trend: first half vs second half
            if len(cf) >= 14:
                mid = len(cf) // 2
                fh_net = cf["net"].iloc[:mid].mean()
                sh_net = cf["net"].iloc[mid:].mean()
                if sh_net > fh_net * 1.10:
                    cf_ins.append(("📈", f"Daily net cash improved from an average of <strong>{format_currency(fh_net)}</strong> in the first half to <strong>{format_currency(sh_net)}</strong> in the second half."))
                elif sh_net < fh_net * 0.90:
                    cf_ins.append(("📉", f"Daily net cash declined from <strong>{format_currency(fh_net)}</strong> (first half) to <strong>{format_currency(sh_net)}</strong> (second half). Monitor whether this is a seasonal pattern or a structural shift."))

            _insights(cf_ins)

        st.divider()
        st.caption(
            f"🔒 Confidential  ·  {user['restaurant_name']}  ·  "
            f"Period: {start_date} – {end_date}  ·  "
            f"Generated {date.today().strftime('%B %d, %Y')}"
        )

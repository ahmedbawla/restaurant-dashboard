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

# Filter by pay date (day after week_end) — a period ending 03/04 is paid 03/05
# so it belongs to March, not February.
if not weekly_payroll.empty:
    weekly_payroll["pay_date"] = (
        pd.to_datetime(weekly_payroll["week_end"]) + pd.Timedelta(days=1)
    ).dt.strftime("%Y-%m-%d")
    if start_date:
        weekly_payroll = weekly_payroll[weekly_payroll["pay_date"] >= start_date]
    if end_date:
        weekly_payroll = weekly_payroll[weekly_payroll["pay_date"] <= end_date]

# ── Paychex upload ────────────────────────────────────────────────────────────
def _render_paychex_upload():
    from utils.csv_importer import parse_paychex_labor_cost, parse_paychex_pdf_journal
    st.markdown("**Upload Paychex Payroll Data**")
    st.caption(
        "Accepted formats:  \n"
        "• **PDF** — Paychex Payroll Journal (recommended): Payroll → Reports → Payroll Journal → Download PDF  \n"
        "• **CSV/XLSX** — Payroll Labor Cost export: Reports → Payroll → Payroll Labor Cost → Download CSV  \n"
        "Export as wide a date range as you have — data is merged, nothing gets overwritten."
    )
    uploaded = st.file_uploader(
        "Payroll file", type=["csv", "xlsx", "pdf"],
        key="paychex_upload", label_visibility="collapsed",
    )
    if uploaded:
        try:
            if uploaded.name.lower().endswith(".pdf"):
                wp_df, dl_df, _summary = parse_paychex_pdf_journal(uploaded.getvalue(), uploaded.name)
            else:
                wp_df, dl_df = parse_paychex_labor_cost(uploaded.getvalue(), uploaded.name)
                _summary = None
            st.success(
                f"Parsed **{len(wp_df)} employee-week rows** across "
                f"**{wp_df['week_start'].nunique()} pay periods** "
                f"({wp_df['week_start'].min()} → {wp_df['week_end'].max()})  ·  "
                f"{wp_df['employee_name'].nunique()} employees  ·  "
                f"Total gross pay: **${wp_df['gross_pay'].sum():,.2f}**"
            )
            if st.button("Import to Dashboard", key="paychex_import_btn", type="primary"):
                # Replace all existing payroll data — avoids double-counting when
                # switching between CSV and PDF imports (they use different employee_id formats)
                from sqlalchemy import text as _text
                with db.get_engine().begin() as _conn:
                    _conn.execute(_text("DELETE FROM weekly_payroll WHERE username=:u"), {"u": username})
                    _conn.execute(_text("DELETE FROM daily_labor    WHERE username=:u"), {"u": username})
                db.upsert_df(dl_df, "daily_labor",    username)
                db.upsert_df(wp_df, "weekly_payroll", username)
                if _summary:
                    db.save_payroll_summary(username, _summary)
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
        _min_pay = (pd.to_datetime(all_payroll["week_end"].min()) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        _max_pay = (pd.to_datetime(all_payroll["week_end"].max()) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        st.warning(
            f"No payroll data in the selected date range. "
            f"Your pay dates cover **{_min_pay}** → **{_max_pay}** — "
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
    available_paydates = sorted(weekly_payroll["pay_date"].unique(), reverse=True)
    selected_paydate   = st.selectbox(
        "Check Date",
        available_paydates,
        format_func=lambda d: pd.to_datetime(d).strftime("%b %d, %Y"),
    )

_check_label_short = pd.to_datetime(selected_paydate).strftime("%b %d, %Y")
week_data = weekly_payroll[weekly_payroll["pay_date"] == selected_paydate]

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

# ── Paychex Payroll Journal Summary ──────────────────────────────────────────
_pjs = db.get_payroll_summary(username)
if _pjs:
    _fmt_date  = lambda d: pd.to_datetime(d, format="%m/%d/%y").strftime("%b %d, %Y") if d else "—"
    _full_gross = float(_pjs.get("gross_earnings") or 0)
    # Scale all summary values to the selected period via gross-pay ratio
    _ratio      = (period_payroll / _full_gross) if _full_gross > 0 else 0
    _is_full    = abs(_ratio - 1.0) < 0.01
    def _sc(key):
        return float(_pjs.get(key) or 0) * _ratio

    _period_note = (
        "Full report period"
        if _is_full
        else f"Estimated for selected period ({_ratio*100:.0f}% of full report)"
    )

    section_header(
        "Payroll Journal Report",
        help=(
            "Withholding and liability figures are prorated from the full Paychex PDF "
            "using the ratio of selected-period gross wages to total report gross wages."
        ),
    )
    st.caption(
        f"Report covers: **{_fmt_date(_pjs.get('period_start'))} – {_fmt_date(_pjs.get('period_end'))}**"
        f"  ·  {_period_note}"
    )

    _sc_net = period_payroll - _sc("total_ee_withholdings")
    j1, j2, j3, j4, j5 = st.columns(5)
    with j1:
        st.metric("Employees", f"{headcount}")
    with j2:
        st.metric("Transactions", f"{len(weekly_payroll)}")
    with j3:
        st.metric("Total Hours", f"{period_hours:,.1f}")
    with j4:
        st.metric("Gross Earnings", format_currency(period_payroll))
    with j5:
        st.metric("Est. Net Pay", format_currency(_sc_net),
                  help="Gross earnings minus estimated employee withholdings for the period.")

    _wh_col, _er_col = st.columns(2)
    with _wh_col:
        st.caption("**Employee Withholdings**")
        _wh_rows = [
            ("Social Security",  _sc("ee_social_security")),
            ("Medicare",         _sc("ee_medicare")),
            ("Fed Income Tax",   _sc("ee_fed_income_tax")),
            ("State Income Tax", _sc("ee_state_income_tax")),
            ("State Disability", _sc("ee_state_disability")),
            ("State PFL",        _sc("ee_state_pfl")),
        ]
        if _sc("ee_other"):
            _wh_rows.append(("Other", _sc("ee_other")))
        _wh_rows.append(("**Total Withheld**", _sc("total_ee_withholdings")))
        _wh_df = pd.DataFrame(_wh_rows, columns=["Withholding", "Amount"])
        _wh_df["Amount"] = _wh_df["Amount"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(_wh_df, use_container_width=True, hide_index=True)

    with _er_col:
        st.caption("**Employer Liabilities**")
        _er_rows = [
            ("Social Security",    _sc("er_social_security")),
            ("Medicare",           _sc("er_medicare")),
            ("Fed Unemployment",   _sc("er_fed_unemployment")),
            ("State Unemployment", _sc("er_state_unemployment")),
        ]
        if _sc("er_other"):
            _er_rows.append(("Other", _sc("er_other")))
        _er_rows.append(("**Total ER Liability**", _sc("total_er_liability")))
        _er_df = pd.DataFrame(_er_rows, columns=["Liability", "Amount"])
        _er_df["Amount"] = _er_df["Amount"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(_er_df, use_container_width=True, hide_index=True)
        st.caption(f"Est. Total Tax Liability (EE + ER): **{format_currency(_sc('total_tax_liability'))}**")

    st.divider()

# ── Payroll cost breakdown (QB reconciliation) ────────────────────────────────
_qb_expenses = db.get_expenses(username, start_date=start_date, end_date=end_date)
_qb_payroll  = _qb_expenses[
    _qb_expenses["category"].str.contains(
        "payroll|salary|salaries|wages|contract labor", case=False, na=False
    )
].copy()

if not _qb_payroll.empty:
    def _qb_type(row):
        desc = str(row.get("description", "")).upper()
        cat  = str(row.get("category",    "")).lower()
        if "eib/invoice" in desc or "invoice" in desc:
            return "Processing Fees"
        elif "contract" in cat:
            return "Contract Labor"
        else:
            return "Net Employee Pay"

    _qb_payroll["_type"] = _qb_payroll.apply(_qb_type, axis=1)
    _net_pay  = _qb_payroll[_qb_payroll["_type"] == "Net Employee Pay"]["amount"].sum()
    _fees     = _qb_payroll[_qb_payroll["_type"] == "Processing Fees"]["amount"].sum()
    _contract = _qb_payroll[_qb_payroll["_type"] == "Contract Labor"]["amount"].sum()
    _withheld = max(period_payroll - _net_pay, 0)

    # Labor cost % — gross wages as a share of revenue for the same period
    _sales_df   = db.get_daily_sales(username, start_date=start_date, end_date=end_date)
    _period_rev = _sales_df["revenue"].sum() if not _sales_df.empty else 0
    _labor_pct  = (period_payroll / _period_rev * 100) if _period_rev > 0 else None

    section_header(
        "Payroll Cost Breakdown",
        help=(
            "Gross wages from Paychex vs. actual cash out from QuickBooks. "
            "Employee withholdings are estimated as gross wages minus net employee pay — "
            "they are collected by Paychex and remitted directly to the IRS, "
            "so they do not appear as an expense in QuickBooks."
        ),
    )

    b1, b2, b3, b4, b5 = st.columns(5)
    with b1:
        st.metric(
            "Gross Wages",
            format_currency(period_payroll),
            help="Total gross pay per Paychex records (before any deductions).",
        )
    with b2:
        st.metric(
            "Employee Withholdings",
            format_currency(_withheld),
            help=(
                f"Estimated taxes withheld from employees' pay "
                f"({_withheld/period_payroll*100:.1f}% of gross). "
                "Remitted to IRS by Paychex — not an expense in QuickBooks."
            ) if period_payroll else "N/A",
        )
    with b3:
        st.metric(
            "Net Employee Pay",
            format_currency(_net_pay),
            help="Actual cash paid to employees (direct deposits + manual checks) per QuickBooks.",
        )
    with b4:
        st.metric(
            "Labor Cost %",
            f"{_labor_pct:.1f}%" if _labor_pct is not None else "N/A",
            help=(
                "Gross payroll as a percentage of revenue for the selected period. "
                "Industry target for restaurants is typically 25–35%."
                + (f" Revenue used: {format_currency(_period_rev)}." if _period_rev else "")
            ),
        )
    with b5:
        if _contract:
            st.metric(
                "Contract Labor",
                format_currency(_contract),
                help="Payments to contractors recorded in QuickBooks (not in Paychex).",
            )
        else:
            st.metric(
                "Processing Fees",
                format_currency(_fees),
                help="Paychex service charges per QuickBooks.",
            )

    with st.expander("QuickBooks Payroll Detail", expanded=False):
        _disp = _qb_payroll[["date", "_type", "vendor", "amount", "description"]].copy()
        _disp["amount"] = _disp["amount"].apply(lambda x: f"${x:,.2f}")
        _disp = _disp.sort_values("date")
        _disp.columns = ["Date", "Type", "Vendor", "Amount", "Description"]
        st.dataframe(_disp, use_container_width=True, hide_index=True)

    st.divider()

# ── Weekly payroll trend ──────────────────────────────────────────────────────
section_header("Weekly Payroll Trend", help="Total gross pay per pay period across the selected range.")
weekly_totals = (
    weekly_payroll.groupby("pay_date")["gross_pay"]
    .sum().reset_index().sort_values("pay_date")
)
weekly_totals["week_label"] = pd.to_datetime(weekly_totals["pay_date"]).dt.strftime("%b %d")
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
    f"Check Date {_check_label_short} — Breakdown",
    help="Pay and hours breakdown for the selected check date.",
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

top_earn = week_data.nlargest(15, "gross_pay")[["employee_name", "gross_pay", "role", "total_hours"]].copy()
top_earn = top_earn.sort_values("gross_pay")
top_earn["_hourly"] = (top_earn["gross_pay"] / top_earn["total_hours"].replace(0, float("nan"))).round(2)
fig_earn = go.Figure(go.Bar(
    x=top_earn["gross_pay"], y=top_earn["employee_name"],
    orientation="h",
    marker_color=_BRAND, marker_line_width=0,
    text=top_earn["gross_pay"].apply(lambda x: f"${x:,.0f}"),
    textposition="outside", textfont=dict(size=10),
    customdata=top_earn[["role", "total_hours", "_hourly"]].values,
    hovertemplate=(
        "%{y}<br>"
        "Role: %{customdata[0]}<br>"
        "Gross Pay: $%{x:,.2f}<br>"
        "Hours: %{customdata[1]:.1f}<br>"
        "Avg Hourly: $%{customdata[2]:.2f}"
        "<extra></extra>"
    ),
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
    help="Total gross pay and hours grouped by job role for the selected period.",
)
role_data = (
    weekly_payroll.groupby("role")
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
    "Payroll Detail — Selected Period",
    help="Payroll totals per employee aggregated across the selected date range.",
)
pd_ = (
    weekly_payroll.groupby(["employee_name", "dept", "role", "employment_type"])
    .agg(regular_hours=("regular_hours", "sum"),
         total_hours=("total_hours", "sum"),
         gross_pay=("gross_pay", "sum"))
    .reset_index()
)
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
            f"({export_df['Week Start'].min()} → {export_df['Week End'].max()}) · "
            f"**Total Gross Pay: {format_currency(all_payroll['gross_pay'].sum())}**"
        )
        st.download_button(
            "Download as CSV",
            data=export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"payroll_{username}.csv",
            mime="text/csv",
        )

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

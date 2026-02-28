"""
Report generation and email delivery utilities.

Generates self-contained HTML reports from dashboard data.
Sends reports via SMTP — configure credentials in .streamlit/secrets.toml:

    [email]
    smtp_host     = "smtp.gmail.com"
    smtp_port     = 587
    smtp_user     = "sender@gmail.com"
    smtp_password = "your-app-password"
"""

import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd


# ---------------------------------------------------------------------------
# SMTP helpers
# ---------------------------------------------------------------------------

def _get_smtp_config() -> dict | None:
    """Read SMTP credentials from Streamlit secrets. Returns None if not set."""
    try:
        import streamlit as st
        cfg = st.secrets.get("email", {})
        if cfg.get("smtp_host") and cfg.get("smtp_user") and cfg.get("smtp_password"):
            return {
                "host":     cfg["smtp_host"],
                "port":     int(cfg.get("smtp_port", 587)),
                "user":     cfg["smtp_user"],
                "password": cfg["smtp_password"],
            }
    except Exception:
        pass
    return None


def send_email_report(to_email: str, subject: str, html_body: str) -> str:
    """
    Send an HTML email.  Returns '' on success, error message on failure.
    """
    cfg = _get_smtp_config()
    if cfg is None:
        return (
            "SMTP credentials are not configured. "
            "Add [email] section to .streamlit/secrets.toml."
        )
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["user"]
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], to_email, msg.as_string())
        return ""
    except Exception as exc:
        return str(exc)


# ---------------------------------------------------------------------------
# HTML report builder
# ---------------------------------------------------------------------------

_CSS = """
<style>
  * { box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #F0F3F7;
    margin: 0; padding: 24px;
    color: #1a1a2a;
    font-size: 13px;
  }
  .report-wrap { max-width: 900px; margin: 0 auto; }

  /* Header */
  .report-header {
    background: linear-gradient(135deg, #1B4F72 0%, #154360 100%);
    color: white;
    padding: 32px 36px;
    border-radius: 10px;
    margin-bottom: 24px;
  }
  .report-header h1 {
    margin: 0 0 6px;
    font-size: 26px;
    letter-spacing: -0.5px;
  }
  .report-header .meta { opacity: 0.7; font-size: 12px; letter-spacing: 1px; text-transform: uppercase; }
  .report-header .period { margin-top: 12px; font-size: 14px; opacity: 0.9; }
  .gold-bar { height: 3px; background: #D4A84B; border-radius: 2px; margin: 14px 0 0; }

  /* Sections */
  .section {
    background: white;
    border-radius: 10px;
    padding: 24px 28px;
    margin-bottom: 16px;
    border-top: 3px solid #D4A84B;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }
  .section h2 {
    margin: 0 0 16px;
    font-size: 15px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #1B4F72;
  }

  /* KPI grid */
  .kpi-grid { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .kpi-card {
    flex: 1; min-width: 130px;
    background: #F8F9FA;
    border-radius: 8px;
    padding: 16px;
    border-left: 3px solid #D4A84B;
  }
  .kpi-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: #717D7E; font-weight: 700; }
  .kpi-value { font-size: 22px; font-weight: 700; color: #1B4F72; margin: 4px 0 2px; }
  .kpi-delta { font-size: 11px; }
  .up   { color: #1E8449; }
  .down { color: #C0392B; }
  .flat { color: #717D7E; }

  /* Insights */
  .insight-list { list-style: none; padding: 0; margin: 0; }
  .insight-list li {
    padding: 8px 0;
    border-bottom: 1px solid #ECF0F1;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    font-size: 13px;
    line-height: 1.5;
  }
  .insight-list li:last-child { border-bottom: none; }
  .insight-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }

  /* Tables */
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 10px; }
  th {
    background: #1B4F72;
    color: white;
    padding: 9px 12px;
    text-align: left;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 700;
  }
  td { padding: 9px 12px; border-bottom: 1px solid #ECF0F1; }
  tr:nth-child(even) td { background: #F8F9FA; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  th.num { text-align: right; }

  /* Status badges */
  .badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
  }
  .badge-green  { background: #D5F5E3; color: #1E8449; }
  .badge-amber  { background: #FEF9E7; color: #D68910; }
  .badge-red    { background: #FDEDEC; color: #C0392B; }

  /* Footer */
  .report-footer {
    text-align: center;
    font-size: 10px;
    color: #AEB6BF;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid #E8E8E8;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
</style>
"""


def _fmt_currency(v: float) -> str:
    return f"${v:,.0f}"


def _fmt_pct(v: float) -> str:
    return f"{v:.1f}%"


def _delta_class(v: float) -> str:
    if v > 0.5:   return "up"
    if v < -0.5:  return "down"
    return "flat"


def _delta_arrow(v: float) -> str:
    if v > 0.5:   return "▲"
    if v < -0.5:  return "▼"
    return "—"


def _kpi(label: str, value: str, delta: str = "", delta_class: str = "flat") -> str:
    delta_html = f'<div class="kpi-delta {delta_class}">{delta}</div>' if delta else ""
    return f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {delta_html}
    </div>"""


def _badge(value: float, target: float, warning: float) -> str:
    if value <= target:
        cls, label = "badge-green", "On Target"
    elif value <= warning:
        cls, label = "badge-amber", "Attention"
    else:
        cls, label = "badge-red", "Off Target"
    return f'<span class="badge {cls}">{label}</span>'


def _period_delta(current: float, prior: float) -> tuple[str, str]:
    """Returns (formatted delta string, css class)."""
    if not prior:
        return "—", "flat"
    pct = (current / prior - 1) * 100
    cls = _delta_class(pct)
    arrow = _delta_arrow(pct)
    return f"{arrow} {abs(pct):.1f}% vs. prior period", cls


def generate_html_report(
    user: dict,
    daily_sales: pd.DataFrame,
    daily_labor: pd.DataFrame,
    weekly_payroll: pd.DataFrame,
    expenses: pd.DataFrame,
    cash_flow: pd.DataFrame,
    menu_items: pd.DataFrame,
    sections: list[str],
    thresholds: dict,
) -> str:
    """
    Build a self-contained HTML performance report.

    Parameters
    ----------
    sections : list of section keys to include —
               "executive", "revenue", "labor", "food_cost", "expenses", "cash_flow"
    """
    today       = date.today()
    report_date = today.strftime("%B %d, %Y")
    period_end  = today.strftime("%b %d, %Y")
    period_start_90 = (today - __import__("datetime").timedelta(days=90)).strftime("%b %d, %Y")

    rest_name = user.get("restaurant_name", "Restaurant")

    # ── Compute headline KPIs ─────────────────────────────────────────────────
    ds = daily_sales.copy() if not daily_sales.empty else pd.DataFrame()

    rev_90   = float(ds["revenue"].sum())           if not ds.empty else 0.0
    rev_30   = float(ds.tail(30)["revenue"].sum())  if not ds.empty else 0.0
    rev_p30  = float(ds.iloc[-60:-30]["revenue"].sum()) if len(ds) >= 60 else 0.0

    covers_30  = int(ds.tail(30)["covers"].sum()) if not ds.empty else 0
    covers_p30 = int(ds.iloc[-60:-30]["covers"].sum()) if len(ds) >= 60 else 0

    avg_check_30 = float(ds.tail(30)["avg_check"].mean()) if not ds.empty else 0.0
    avg_food_pct = float(ds["food_cost_pct"].mean())      if not ds.empty else 0.0
    total_food_cost = float(ds["food_cost"].sum())        if not ds.empty else 0.0

    labor_df = daily_labor.copy() if not daily_labor.empty else pd.DataFrame()
    labor_by_day = (
        labor_df.groupby("date")["labor_cost"].sum().reset_index()
        if not labor_df.empty else pd.DataFrame(columns=["date", "labor_cost"])
    )
    merged = labor_by_day.merge(ds[["date", "revenue"]], on="date", how="inner") if not ds.empty else pd.DataFrame()
    avg_labor_pct = float((merged["labor_cost"] / merged["revenue"] * 100).mean()) if not merged.empty else 0.0
    labor_90 = float(labor_by_day["labor_cost"].sum()) if not labor_by_day.empty else 0.0

    exp_df   = expenses.copy() if not expenses.empty else pd.DataFrame()
    exp_90   = float(exp_df["amount"].sum()) if not exp_df.empty else 0.0

    cf_df    = cash_flow.copy() if not cash_flow.empty else pd.DataFrame()
    net_cash = float(cf_df["net"].sum()) if not cf_df.empty else 0.0

    payroll_total = float(weekly_payroll["gross_pay"].sum()) if not weekly_payroll.empty else 0.0

    food_target  = thresholds.get("food_cost_pct_target",  30.0)
    food_warning = thresholds.get("food_cost_pct_warning", 33.0)
    labor_target  = thresholds.get("labor_cost_pct_target",  30.0)
    labor_warning = thresholds.get("labor_cost_pct_warning", 33.0)
    prime_target  = thresholds.get("prime_cost_pct_target",  60.0)
    prime_warning = thresholds.get("prime_cost_pct_warning", 65.0)
    prime_cost_pct = avg_food_pct + avg_labor_pct

    # ── Build sections ────────────────────────────────────────────────────────
    body_parts = []

    # --- Executive Summary ---
    if "executive" in sections:
        rev_delta, rev_cls = _period_delta(rev_30, rev_p30)
        cov_delta, cov_cls = _period_delta(covers_30, covers_p30)

        food_status = "tracking above target" if avg_food_pct > food_warning else (
            "within warning range" if avg_food_pct > food_target else "on target")
        labor_status = "tracking above target" if avg_labor_pct > labor_warning else (
            "within warning range" if avg_labor_pct > labor_target else "on target")

        insights = [
            ("📈", f"Revenue for the trailing 30 days totalled <strong>{_fmt_currency(rev_30)}</strong> ({rev_delta})."),
            ("🍽️", f"Guest covers for the same period were <strong>{covers_30:,}</strong> ({cov_delta}) with an average check size of <strong>{_fmt_currency(avg_check_30)}</strong>."),
            ("🥩", f"Food cost averaged <strong>{_fmt_pct(avg_food_pct)}</strong> over the 90-day period — {food_status} (target: {food_target}%)."),
            ("👥", f"Labour cost averaged <strong>{_fmt_pct(avg_labor_pct)}</strong> — {labor_status} (target: {labor_target}%)."),
            ("💰", f"Net cash position for the period: <strong>{_fmt_currency(net_cash)}</strong>."),
        ]
        rows = "".join(
            f'<li><span class="insight-icon">{icon}</span><span>{text}</span></li>'
            for icon, text in insights
        )
        body_parts.append(f"""
        <div class="section">
          <h2>Executive Summary</h2>
          <ul class="insight-list">{rows}</ul>
        </div>""")

    # --- Revenue & Sales ---
    if "revenue" in sections and not ds.empty:
        rev_delta, rev_cls = _period_delta(rev_30, rev_p30)
        cov_delta, cov_cls = _period_delta(covers_30, covers_p30)

        kpis = (
            _kpi("Revenue (90 Days)", _fmt_currency(rev_90)) +
            _kpi("Revenue (30 Days)", _fmt_currency(rev_30), rev_delta, rev_cls) +
            _kpi("Covers (30 Days)",  f"{covers_30:,}", cov_delta, cov_cls) +
            _kpi("Avg. Check Size",   _fmt_currency(avg_check_30))
        )

        # Monthly revenue table
        ds_copy = ds.copy()
        ds_copy["month"] = pd.to_datetime(ds_copy["date"]).dt.to_period("M").astype(str)
        monthly = ds_copy.groupby("month").agg(
            Revenue=("revenue", "sum"),
            Covers=("covers", "sum"),
            Avg_Check=("avg_check", "mean"),
            Food_Cost_Pct=("food_cost_pct", "mean"),
        ).reset_index().sort_values("month", ascending=False)

        rows_html = "".join(
            f"""<tr>
              <td>{r.month}</td>
              <td class="num">{_fmt_currency(r.Revenue)}</td>
              <td class="num">{r.Covers:,.0f}</td>
              <td class="num">{_fmt_currency(r.Avg_Check)}</td>
              <td class="num">{_fmt_pct(r.Food_Cost_Pct)}</td>
            </tr>"""
            for _, r in monthly.iterrows()
        )
        body_parts.append(f"""
        <div class="section">
          <h2>Revenue &amp; Sales Analysis</h2>
          <div class="kpi-grid">{kpis}</div>
          <table>
            <thead><tr>
              <th>Month</th><th class="num">Revenue</th>
              <th class="num">Covers</th><th class="num">Avg. Check</th>
              <th class="num">Food Cost %</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>""")

    # --- Labor & Payroll ---
    if "labor" in sections and not labor_df.empty:
        kpis = (
            _kpi("Labour Cost (90 Days)", _fmt_currency(labor_90)) +
            _kpi("Avg. Labour Cost %",    _fmt_pct(avg_labor_pct)) +
            _kpi("Total Payroll (Period)", _fmt_currency(payroll_total))
        )
        # Department summary
        dept_summary = (
            weekly_payroll.groupby("dept")
            .agg(Employees=("employee_id", "nunique"), Total_Hours=("total_hours", "sum"), Gross_Pay=("gross_pay", "sum"))
            .reset_index().sort_values("Gross_Pay", ascending=False)
        ) if not weekly_payroll.empty else pd.DataFrame()

        dept_rows = "".join(
            f"""<tr>
              <td>{r.dept}</td>
              <td class="num">{r.Employees}</td>
              <td class="num">{r.Total_Hours:,.1f}</td>
              <td class="num">{_fmt_currency(r.Gross_Pay)}</td>
            </tr>"""
            for _, r in dept_summary.iterrows()
        )
        body_parts.append(f"""
        <div class="section">
          <h2>Labour &amp; Payroll</h2>
          <div class="kpi-grid">{kpis}</div>
          {'<table><thead><tr><th>Department</th><th class="num">Employees</th><th class="num">Total Hours</th><th class="num">Gross Pay</th></tr></thead><tbody>' + dept_rows + '</tbody></table>' if dept_rows else ''}
        </div>""")

    # --- Food Cost & Inventory ---
    if "food_cost" in sections and not ds.empty:
        kpis = (
            _kpi("Avg. Food Cost %", f"{_fmt_pct(avg_food_pct)} {_badge(avg_food_pct, food_target, food_warning)}") +
            _kpi("Total Food Cost (90 Days)", _fmt_currency(total_food_cost)) +
            _kpi("Prime Cost %", f"{_fmt_pct(prime_cost_pct)} {_badge(prime_cost_pct, prime_target, prime_warning)}")
        )
        top_items_rows = ""
        if not menu_items.empty:
            top = menu_items.nlargest(10, "total_revenue")
            top_items_rows = "".join(
                f"""<tr>
                  <td>{r["name"]}</td><td>{r["category"]}</td>
                  <td class="num">{r["quantity_sold"]:,}</td>
                  <td class="num">{_fmt_currency(r["total_revenue"])}</td>
                  <td class="num">{_fmt_pct(r["margin_pct"])}</td>
                </tr>"""
                for _, r in top.iterrows()
            )
        body_parts.append(f"""
        <div class="section">
          <h2>Food Cost &amp; Inventory</h2>
          <div class="kpi-grid">{kpis}</div>
          {'<table><thead><tr><th>Item</th><th>Category</th><th class="num">Qty Sold</th><th class="num">Revenue</th><th class="num">Margin %</th></tr></thead><tbody>' + top_items_rows + '</tbody></table>' if top_items_rows else ''}
        </div>""")

    # --- Expense Analysis ---
    if "expenses" in sections and not exp_df.empty:
        kpis = _kpi("Total Operating Expenses (90 Days)", _fmt_currency(exp_90))
        cat_totals = (
            exp_df.groupby("category")["amount"].sum()
            .reset_index().sort_values("amount", ascending=False)
        )
        cat_rows = "".join(
            f"""<tr>
              <td>{r["category"]}</td>
              <td class="num">{_fmt_currency(r["amount"])}</td>
              <td class="num">{r["amount"]/exp_90*100:.1f}%</td>
            </tr>"""
            for _, r in cat_totals.iterrows()
        )
        body_parts.append(f"""
        <div class="section">
          <h2>Expense Analysis</h2>
          <div class="kpi-grid">{kpis}</div>
          <table>
            <thead><tr><th>Category</th><th class="num">Total</th><th class="num">% of Spend</th></tr></thead>
            <tbody>{cat_rows}</tbody>
          </table>
        </div>""")

    # --- Cash Flow ---
    if "cash_flow" in sections and not cf_df.empty:
        inflow  = float(cf_df["inflow"].sum())
        outflow = float(cf_df["outflow"].sum())
        kpis = (
            _kpi("Total Inflows (90 Days)",  _fmt_currency(inflow)) +
            _kpi("Total Outflows (90 Days)", _fmt_currency(outflow)) +
            _kpi("Net Cash Position",        _fmt_currency(net_cash),
                 delta_class="up" if net_cash >= 0 else "down")
        )
        body_parts.append(f"""
        <div class="section">
          <h2>Cash Flow</h2>
          <div class="kpi-grid">{kpis}</div>
        </div>""")

    sections_html = "\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{rest_name} — Performance Report</title>
  {_CSS}
</head>
<body>
<div class="report-wrap">

  <div class="report-header">
    <div class="meta">Confidential — Prepared for Authorised Recipients Only</div>
    <h1>{rest_name}</h1>
    <div class="period">Performance Report &nbsp;|&nbsp; {period_start_90} – {period_end}</div>
    <div class="gold-bar"></div>
  </div>

  {sections_html}

  <div class="report-footer">
    Generated on {report_date} &nbsp;·&nbsp; {rest_name} Business Intelligence Dashboard
    &nbsp;·&nbsp; Confidential
  </div>

</div>
</body>
</html>"""

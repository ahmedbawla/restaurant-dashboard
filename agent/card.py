"""
Self-contained daily card generator for the BART Telegram bot.

Uses psycopg2 directly (no SQLAlchemy / no parent-project imports)
so it works when Railway deploys only the agent/ directory.
"""

import asyncio
import os
from datetime import date, timedelta


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _conn():
    import psycopg2
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # psycopg2 accepts postgresql:// URIs
    return psycopg2.connect(url)


# ── Data fetch ─────────────────────────────────────────────────────────────────

def fetch_card_data(username: str) -> dict:
    today     = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    d7        = (today - timedelta(days=7)).isoformat()
    d14       = (today - timedelta(days=14)).isoformat()

    with _conn() as db:
        with db.cursor() as cur:
            # Last 14 days of sales, capped at yesterday so today's
            # incomplete data is never included regardless of run time
            cur.execute("""
                SELECT date, revenue, covers, avg_check
                FROM daily_sales
                WHERE username = %s AND date >= %s AND date <= %s
                ORDER BY date DESC
            """, (username, d14, yesterday))
            all_sales = [
                {"date": str(r[0]), "revenue": float(r[1] or 0),
                 "covers": int(r[2] or 0), "avg_check": float(r[3] or 0)}
                for r in cur.fetchall()
            ]

            # Labor — 7-day window
            cur.execute("""
                SELECT COALESCE(SUM(labor_cost), 0)
                FROM daily_labor
                WHERE username = %s AND date >= %s
            """, (username, d7))
            labor_total = float(cur.fetchone()[0] or 0)

            # Expenses — 7-day window
            cur.execute("""
                SELECT COALESCE(SUM(amount), 0)
                FROM expenses
                WHERE username = %s AND date >= %s
            """, (username, d7))
            expenses_week = float(cur.fetchone()[0] or 0)

            # User info
            cur.execute(
                "SELECT restaurant_name, email FROM users WHERE username = %s",
                (username,)
            )
            row = cur.fetchone()
            restaurant_name = row[0] if row else username
            email           = row[1] if row else None

    sales       = [r for r in all_sales if r["date"] >= d7]
    prior_sales = [r for r in all_sales if r["date"] <  d7]

    return {
        "username":        username,
        "restaurant_name": restaurant_name,
        "email":           email,
        "sales":           sales,
        "prior_sales":     prior_sales,
        "labor_total":     labor_total,
        "expenses_week":   expenses_week,
        "today":           today,
    }


# ── Alerts ─────────────────────────────────────────────────────────────────────

def _build_alerts(data: dict) -> list:
    alerts = []
    sales  = data["sales"]
    prior  = data.get("prior_sales", [])

    if not sales:
        return ["No sales data yet."]

    yesterday = sales[0]
    yest_rev  = yesterday.get("revenue") or 0
    if yest_rev == 0:
        alerts.append("No sales recorded yesterday — check your Toast sync.")

    wtd_rev   = sum(r.get("revenue") or 0 for r in sales)
    prior_rev = sum(r.get("revenue") or 0 for r in prior)
    if prior_rev > 0 and wtd_rev > 0:
        wow_pct = (wtd_rev - prior_rev) / prior_rev * 100
        if wow_pct <= -10:
            alerts.append(f"Revenue is {abs(wow_pct):.0f}% below last week — review recent trends.")
        elif wow_pct >= 10:
            alerts.append(f"Revenue up {wow_pct:.0f}% vs last week — great momentum!")

    if data["expenses_week"] > 0 and wtd_rev > 0:
        exp_ratio = data["expenses_week"] / wtd_rev * 100
        if exp_ratio > 45:
            alerts.append(f"Expenses at {exp_ratio:.0f}% of revenue this week — review your spend.")

    yest_avg = yesterday.get("avg_check") or (yest_rev / yesterday["covers"] if yesterday.get("covers") else 0)
    if len(sales) >= 4 and yest_avg > 0:
        recent_avg = sum(
            r.get("avg_check") or (r.get("revenue", 0) / r["covers"] if r.get("covers") else 0)
            for r in sales[1:4]
        ) / 3
        if recent_avg > 0 and yest_avg < recent_avg * 0.92:
            alerts.append(f"Avg check dropped to ${yest_avg:.0f} — down from ${recent_avg:.0f} recent average.")

    labor = data["labor_total"]
    if labor > 0 and wtd_rev > 0:
        lp = labor / wtd_rev * 100
        if lp > 35:
            alerts.append(f"Labour at {lp:.0f}% of revenue this week — target under 35%.")

    if not alerts:
        alerts.append("All metrics look healthy today. Keep it up!")
    return alerts


# ── HTML card ──────────────────────────────────────────────────────────────────

def generate_card_html(data: dict) -> str:
    sales           = data["sales"]
    prior_sales     = data.get("prior_sales", [])
    restaurant_name = data["restaurant_name"]
    today           = data["today"]
    alerts          = _build_alerts(data)

    yest        = sales[0] if sales else {}
    yest_rev    = yest.get("revenue") or 0
    yest_covers = yest.get("covers") or 0
    yest_avg    = yest.get("avg_check") or (yest_rev / yest_covers if yest_covers else 0)

    wtd_rev   = sum(r.get("revenue") or 0 for r in sales)
    prior_rev = sum(r.get("revenue") or 0 for r in prior_sales)

    if prior_rev > 0 and wtd_rev > 0:
        wow_pct = (wtd_rev - prior_rev) / prior_rev * 100
        wow_str = f"{'+' if wow_pct >= 0 else ''}{wow_pct:.0f}%"
        wow_cls = "ok" if wow_pct >= 0 else "warn"
    else:
        wow_str, wow_cls = "—", ""

    exp_ratio     = data["expenses_week"] / wtd_rev * 100 if wtd_rev > 0 and data["expenses_week"] > 0 else 0
    exp_ratio_cls = "warn" if exp_ratio > 45 else ("ok" if exp_ratio > 0 else "")
    exp_ratio_val = f"{exp_ratio:.0f}%" if exp_ratio > 0 else "—"

    labor_total = data["labor_total"]
    labor_pct   = labor_total / wtd_rev * 100 if labor_total > 0 and wtd_rev > 0 else 0

    day_cards = list(reversed(sales[:7]))

    def fmt(v): return f"${v:,.0f}"

    def day_label(d):
        try:
            dt = date.fromisoformat(str(d))
            return dt.strftime("%a") + " " + str(dt.day)
        except Exception:
            return str(d)[-5:]

    days_html = "".join(f"""
        <div class="day-card">
          <div class="day-label">{day_label(r.get('date',''))}</div>
          <div class="day-rev">{fmt(r.get('revenue') or 0)}</div>
          <div class="day-meta">{r.get('covers') or 0} covers &nbsp;·&nbsp; {fmt(r.get('avg_check') or 0)} avg</div>
        </div>""" for r in day_cards) or '<div class="day-card" style="opacity:.4">No data yet</div>'

    alerts_html = "".join(
        f'<div class="alert-item">{"⚠" if any(w in a for w in ["%","drop","below","No sales"]) else "✓"} {a}</div>'
        for a in alerts
    )

    labor_kpi = ""
    if labor_pct > 0:
        lc = "warn" if labor_pct > 35 else "ok"
        labor_kpi = f"""
    <div class="kpi {lc}">
      <div class="val">{labor_pct:.0f}%</div>
      <div class="lbl">Labour 7 Days</div>
    </div>"""

    today_str = today.strftime("%A, %B") + " " + str(today.day) + " " + str(today.year)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:#0e0e10;color:#f0f0f0;width:780px;padding:0;}}
  .card{{width:780px;background:#0e0e10;padding:28px 28px 24px;}}
  .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;}}
  .brand{{font-size:15px;font-weight:800;letter-spacing:-0.3px;background:linear-gradient(135deg,#FF6B35,#FF4B4B);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
  .header-right{{font-size:11px;color:#666;text-align:right;}}
  .restaurant{{font-size:12px;color:#aaa;margin-top:1px;font-weight:600;}}
  .hero{{background:#1a1a1d;border-radius:10px;padding:20px 22px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:flex-start;}}
  .hero-rev{{font-size:38px;font-weight:800;letter-spacing:-1px;color:#fff;line-height:1;}}
  .hero-label{{font-size:11px;color:#666;margin-top:4px;text-transform:uppercase;letter-spacing:1px;}}
  .hero-stats{{display:flex;gap:24px;margin-top:4px;}}
  .hero-stat{{text-align:right;}}
  .hero-stat .val{{font-size:18px;font-weight:700;color:#fff;}}
  .hero-stat .lbl{{font-size:10px;color:#666;text-transform:uppercase;letter-spacing:0.8px;}}
  .alerts{{background:rgba(255,107,53,0.10);border:1px solid rgba(255,107,53,0.25);border-radius:8px;padding:12px 16px;margin-bottom:14px;}}
  .alerts-title{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#FF6B35;margin-bottom:6px;}}
  .alert-item{{font-size:12px;color:#ddd;padding:3px 0;line-height:1.5;}}
  .kpi-row{{display:flex;gap:10px;margin-bottom:14px;}}
  .kpi{{flex:1;background:#1a1a1d;border-radius:8px;padding:14px 16px;text-align:center;}}
  .kpi .val{{font-size:20px;font-weight:800;color:#fff;}}
  .kpi .lbl{{font-size:10px;color:#666;text-transform:uppercase;letter-spacing:0.8px;margin-top:3px;}}
  .kpi.warn .val{{color:#e74c3c;}} .kpi.ok .val{{color:#2ecc71;}}
  .days-title{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#555;margin-bottom:8px;}}
  .days{{display:flex;gap:8px;}}
  .day-card{{flex:1;background:#1a1a1d;border-radius:8px;padding:12px 10px;text-align:center;}}
  .day-label{{font-size:10px;color:#666;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:5px;}}
  .day-rev{{font-size:15px;font-weight:800;color:#fff;margin-bottom:3px;}}
  .day-meta{{font-size:9.5px;color:#555;}}
  .footer{{margin-top:18px;display:flex;justify-content:space-between;align-items:center;border-top:1px solid #1e1e22;padding-top:12px;}}
  .footer p{{font-size:10px;color:#444;}} .footer a{{color:#FF6B35;text-decoration:none;font-size:10px;}}
</style></head><body>
<div class="card">
  <div class="header">
    <div><div class="brand">TableMetrics</div><div class="restaurant">{restaurant_name}</div></div>
    <div class="header-right">Daily Intelligence Report<br>{today_str}</div>
  </div>
  <div class="hero">
    <div>
      <div class="hero-rev">{fmt(yest_rev)}</div>
      <div class="hero-label">Yesterday's Revenue</div>
    </div>
    <div class="hero-stats">
      <div class="hero-stat"><div class="val">{yest_covers}</div><div class="lbl">Covers</div></div>
      <div class="hero-stat"><div class="val">{fmt(yest_avg)}</div><div class="lbl">Avg Check</div></div>
      <div class="hero-stat"><div class="val">{fmt(wtd_rev)}</div><div class="lbl">7-Day Total</div></div>
    </div>
  </div>
  <div class="alerts">
    <div class="alerts-title">Today's Alerts</div>
    {alerts_html}
  </div>
  <div class="kpi-row">
    <div class="kpi {wow_cls}"><div class="val">{wow_str}</div><div class="lbl">vs Last Week</div></div>
    <div class="kpi {exp_ratio_cls}"><div class="val">{exp_ratio_val}</div><div class="lbl">Expense Ratio</div></div>
    <div class="kpi"><div class="val">{fmt(data['expenses_week'])}</div><div class="lbl">Expenses 7 Days</div></div>
    <div class="kpi"><div class="val">{fmt(wtd_rev)}</div><div class="lbl">Revenue 7 Days</div></div>
    {labor_kpi}
  </div>
  <div class="days-title">Last 7 Days</div>
  <div class="days">{days_html}</div>
  <div class="footer">
    <p>TableMetrics · Sent every morning at 7 AM</p>
    <a href="#">Open full dashboard →</a>
  </div>
</div>
</body></html>"""


# ── PNG rendering ──────────────────────────────────────────────────────────────

async def render_png_async(html: str, out_path: str) -> None:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page    = await browser.new_page(viewport={"width": 780, "height": 600})
        await page.set_content(html, wait_until="domcontentloaded")
        height = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size({"width": 780, "height": height})
        await page.screenshot(path=out_path, full_page=True)
        await browser.close()

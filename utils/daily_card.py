"""
Daily morning card generator for TableMetrics.

Usage:
    from utils.daily_card import generate_card_html, send_daily_card

    html = generate_card_html(username, restaurant_name, data)
    send_daily_card(username)          # queries DB + sends via Telegram

Delivery is driven by APScheduler in agent/bot.py (7 AM daily).
PNG rendering requires playwright:  pip install playwright && playwright install chromium
"""

import asyncio
import os
from datetime import date, timedelta

from sqlalchemy import text


# ── Data fetch ────────────────────────────────────────────────────────────────

def fetch_card_data(username: str) -> dict:
    """Pull the last 7 days of data needed for the morning card."""
    from data.database import get_engine
    engine = get_engine()
    today  = date.today()
    d7     = (today - timedelta(days=7)).isoformat()

    with engine.connect() as conn:
        # Last 7 days of sales
        rows = conn.execute(text("""
            SELECT date, revenue, covers, avg_check, food_cost_pct
            FROM daily_sales
            WHERE username = :u AND date >= :d
            ORDER BY date DESC
        """), {"u": username, "d": d7}).fetchall()
        sales = [dict(r._mapping) for r in rows]

        # Yesterday's labor cost %
        yesterday = (today - timedelta(days=1)).isoformat()
        labor_row = conn.execute(text("""
            SELECT COALESCE(SUM(labor_cost), 0) as total_labor
            FROM daily_labor
            WHERE username = :u AND date = :d
        """), {"u": username, "d": yesterday}).fetchone()
        labor_total = float(labor_row[0]) if labor_row else 0

        # This week's expenses total
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        exp_row = conn.execute(text("""
            SELECT COALESCE(SUM(amount), 0) as total_exp
            FROM expenses
            WHERE username = :u AND date >= :d
        """), {"u": username, "d": week_start}).fetchone()
        expenses_week = float(exp_row[0]) if exp_row else 0

        # User info
        user_row = conn.execute(text(
            "SELECT restaurant_name, email FROM users WHERE username = :u"
        ), {"u": username}).fetchone()
        restaurant_name = user_row[0] if user_row else username
        email           = user_row[1] if user_row else None

    return {
        "username":        username,
        "restaurant_name": restaurant_name,
        "email":           email,
        "sales":           sales,          # list of dicts, newest first
        "labor_total":     labor_total,
        "expenses_week":   expenses_week,
        "today":           today,
    }


# ── Alerts ────────────────────────────────────────────────────────────────────

def _build_alerts(data: dict) -> list[str]:
    alerts = []
    sales  = data["sales"]
    if not sales:
        return ["No sales data yet — connect your Toast POS to get started."]

    yesterday = sales[0] if sales else None
    if yesterday:
        fc = yesterday.get("food_cost_pct") or 0
        if fc > 32:
            alerts.append(f"Food cost at {fc:.0f}% yesterday — target is under 32%.")
        rev = yesterday.get("revenue") or 0
        if rev == 0:
            alerts.append("No sales recorded yesterday — check your Toast sync.")

    labor = data["labor_total"]
    if labor > 0 and yesterday and yesterday.get("revenue", 0) > 0:
        labor_pct = labor / yesterday["revenue"] * 100
        if labor_pct > 35:
            alerts.append(f"Labour cost at {labor_pct:.0f}% of revenue yesterday — target under 35%.")

    if not alerts:
        alerts.append("All metrics look healthy today. Keep it up!")
    return alerts


# ── HTML card ─────────────────────────────────────────────────────────────────

def generate_card_html(data: dict) -> str:
    sales            = data["sales"]
    restaurant_name  = data["restaurant_name"]
    today            = data["today"]
    alerts           = _build_alerts(data)

    # Yesterday summary
    yest             = sales[0] if sales else {}
    yest_rev         = yest.get("revenue") or 0
    yest_covers      = yest.get("covers")  or 0
    yest_avg         = yest.get("avg_check") or (yest_rev / yest_covers if yest_covers else 0)
    yest_fc          = yest.get("food_cost_pct") or 0

    # Week-to-date
    wtd_rev = sum(r.get("revenue") or 0 for r in sales)

    # 7-day cards (oldest → newest)
    day_cards = list(reversed(sales[:7]))

    def fmt_money(v):
        return f"${v:,.0f}"

    def day_card_html(row):
        d    = row.get("date", "")
        rev  = row.get("revenue") or 0
        cov  = row.get("covers")  or 0
        avg  = row.get("avg_check") or (rev / cov if cov else 0)
        fc   = row.get("food_cost_pct") or 0
        # Parse date label
        try:
            dt    = date.fromisoformat(str(d))
            label = dt.strftime("%a %-d")
        except Exception:
            label = str(d)[-5:]

        fc_color = "#e74c3c" if fc > 32 else "#27ae60"
        return f"""
        <div class="day-card">
          <div class="day-label">{label}</div>
          <div class="day-rev">{fmt_money(rev)}</div>
          <div class="day-meta">{cov} covers &nbsp;·&nbsp; {fmt_money(avg)} avg</div>
          <div class="day-fc" style="color:{fc_color}">Food cost {fc:.0f}%</div>
        </div>"""

    day_cards_html = "".join(day_card_html(r) for r in day_cards) if day_cards else \
        '<div class="day-card" style="opacity:.4">No data yet</div>'

    alerts_html = "".join(f'<div class="alert-item">⚠ {a}</div>' for a in alerts)

    labor_pct = 0
    if data["labor_total"] > 0 and yest_rev > 0:
        labor_pct = data["labor_total"] / yest_rev * 100

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    background: #0e0e10;
    color: #f0f0f0;
    width: 780px;
    padding: 0;
  }}
  .card {{
    width: 780px;
    background: #0e0e10;
    padding: 28px 28px 24px;
  }}

  /* Header */
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
  }}
  .brand {{
    font-size: 15px;
    font-weight: 800;
    letter-spacing: -0.3px;
    background: linear-gradient(135deg, #FF6B35, #FF4B4B);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}
  .header-right {{
    font-size: 11px;
    color: #666;
    text-align: right;
  }}
  .restaurant {{
    font-size: 12px;
    color: #aaa;
    margin-top: 1px;
    font-weight: 600;
  }}

  /* Hero */
  .hero {{
    background: #1a1a1d;
    border-radius: 10px;
    padding: 20px 22px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .hero-rev {{
    font-size: 38px;
    font-weight: 800;
    letter-spacing: -1px;
    color: #fff;
    line-height: 1;
  }}
  .hero-label {{
    font-size: 11px;
    color: #666;
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }}
  .hero-stats {{
    display: flex;
    gap: 24px;
    margin-top: 4px;
  }}
  .hero-stat {{
    text-align: right;
  }}
  .hero-stat .val {{
    font-size: 18px;
    font-weight: 700;
    color: #fff;
  }}
  .hero-stat .lbl {{
    font-size: 10px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }}

  /* Alerts */
  .alerts {{
    background: rgba(255,107,53,0.10);
    border: 1px solid rgba(255,107,53,0.25);
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 14px;
  }}
  .alerts-title {{
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #FF6B35;
    margin-bottom: 6px;
  }}
  .alert-item {{
    font-size: 12px;
    color: #ddd;
    padding: 3px 0;
    line-height: 1.5;
  }}

  /* KPI row */
  .kpi-row {{
    display: flex;
    gap: 10px;
    margin-bottom: 14px;
  }}
  .kpi {{
    flex: 1;
    background: #1a1a1d;
    border-radius: 8px;
    padding: 14px 16px;
    text-align: center;
  }}
  .kpi .val {{
    font-size: 20px;
    font-weight: 800;
    color: #fff;
  }}
  .kpi .lbl {{
    font-size: 10px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-top: 3px;
  }}
  .kpi.warn .val {{ color: #e74c3c; }}
  .kpi.ok   .val {{ color: #2ecc71; }}

  /* Day cards */
  .days-title {{
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #555;
    margin-bottom: 8px;
  }}
  .days {{
    display: flex;
    gap: 8px;
  }}
  .day-card {{
    flex: 1;
    background: #1a1a1d;
    border-radius: 8px;
    padding: 12px 10px;
    text-align: center;
  }}
  .day-label {{
    font-size: 10px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 5px;
  }}
  .day-rev {{
    font-size: 15px;
    font-weight: 800;
    color: #fff;
    margin-bottom: 3px;
  }}
  .day-meta {{
    font-size: 9.5px;
    color: #555;
    margin-bottom: 3px;
  }}
  .day-fc {{
    font-size: 9.5px;
    font-weight: 600;
  }}

  /* Footer */
  .footer {{
    margin-top: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid #1e1e22;
    padding-top: 12px;
  }}
  .footer p {{ font-size: 10px; color: #444; }}
  .footer a {{ color: #FF6B35; text-decoration: none; font-size: 10px; }}
</style>
</head>
<body>
<div class="card">

  <!-- Header -->
  <div class="header">
    <div>
      <div class="brand">TableMetrics</div>
      <div class="restaurant">{restaurant_name}</div>
    </div>
    <div class="header-right">
      Daily Intelligence Report<br>
      {today.strftime("%A, %B") + " " + str(today.day) + " " + str(today.year)}
    </div>
  </div>

  <!-- Hero: yesterday's revenue -->
  <div class="hero">
    <div>
      <div class="hero-rev">{fmt_money(yest_rev)}</div>
      <div class="hero-label">Yesterday's Revenue</div>
    </div>
    <div class="hero-stats">
      <div class="hero-stat">
        <div class="val">{yest_covers}</div>
        <div class="lbl">Covers</div>
      </div>
      <div class="hero-stat">
        <div class="val">{fmt_money(yest_avg)}</div>
        <div class="lbl">Avg Check</div>
      </div>
      <div class="hero-stat">
        <div class="val">{fmt_money(wtd_rev)}</div>
        <div class="lbl">7-Day Total</div>
      </div>
    </div>
  </div>

  <!-- Alerts -->
  <div class="alerts">
    <div class="alerts-title">Today's Alerts</div>
    {alerts_html}
  </div>

  <!-- KPIs -->
  <div class="kpi-row">
    <div class="kpi {'warn' if yest_fc > 32 else 'ok'}">
      <div class="val">{yest_fc:.0f}%</div>
      <div class="lbl">Food Cost</div>
    </div>
    <div class="kpi {'warn' if labor_pct > 35 else 'ok'}">
      <div class="val">{labor_pct:.0f}%</div>
      <div class="lbl">Labour %</div>
    </div>
    <div class="kpi">
      <div class="val">{fmt_money(data['expenses_week'])}</div>
      <div class="lbl">Expenses This Week</div>
    </div>
    <div class="kpi">
      <div class="val">{fmt_money(wtd_rev)}</div>
      <div class="lbl">Revenue 7 Days</div>
    </div>
  </div>

  <!-- 7-day breakdown -->
  <div class="days-title">Last 7 Days</div>
  <div class="days">
    {day_cards_html}
  </div>

  <!-- Footer -->
  <div class="footer">
    <p>TableMetrics · Sent every morning at 7 AM</p>
    <a href="#">Open full dashboard →</a>
  </div>

</div>
</body>
</html>"""


# ── PNG rendering ─────────────────────────────────────────────────────────────

async def _render_png(html: str, out_path: str) -> None:
    """Render HTML card to PNG using playwright headless Chrome."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page    = await browser.new_page(viewport={"width": 780, "height": 600})
        await page.set_content(html, wait_until="domcontentloaded")
        # Let the card dictate height
        height = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size({"width": 780, "height": height})
        await page.screenshot(path=out_path, full_page=True)
        await browser.close()


def render_png(html: str, out_path: str) -> None:
    asyncio.run(_render_png(html, out_path))


# ── Telegram delivery ─────────────────────────────────────────────────────────

def _get_telegram_cfg(username: str) -> dict | None:
    """Return {bot_token, chat_id} for a user, or None if not configured."""
    from data.database import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT telegram_bot_token, telegram_chat_id FROM users WHERE username = :u"
        ), {"u": username}).fetchone()
        if row and row[0] and row[1]:
            return {"bot_token": row[0], "chat_id": row[1]}
    return None


def send_daily_card(username: str, out_dir: str = "/tmp") -> bool:
    """
    Full pipeline: fetch data → build HTML → render PNG → send via Telegram.
    Returns True on success.
    """
    import requests as _req

    data     = fetch_card_data(username)
    html     = generate_card_html(data)
    png_path = f"{out_dir}/daily_card_{username}.png"

    try:
        render_png(html, png_path)
    except Exception as e:
        # Playwright not available — fall back to sending HTML link or text
        print(f"PNG render failed ({e}), skipping image send.")
        return False

    # Delivery: use the owner's bot token + chat_id stored per user,
    # or fall back to the global TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars.
    cfg = _get_telegram_cfg(username)
    bot_token = (cfg or {}).get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id   = (cfg or {}).get("chat_id")   or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        print(f"No Telegram config for {username}")
        return False

    with open(png_path, "rb") as f:
        resp = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendPhoto",
            data={"chat_id": chat_id, "caption": f"Good morning! Here's your daily report for {data['restaurant_name']}."},
            files={"photo": f},
            timeout=15,
        )
    return resp.status_code == 200

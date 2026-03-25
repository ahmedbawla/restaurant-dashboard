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
    """Pull the last 14 days of data needed for the morning card."""
    from data.database import get_engine
    engine = get_engine()
    today = date.today()
    d7    = (today - timedelta(days=7)).isoformat()
    d14   = (today - timedelta(days=14)).isoformat()

    with engine.connect() as conn:
        # Last 14 days of sales (7 for this week, 7 for WoW comparison)
        rows = conn.execute(text("""
            SELECT date, revenue, covers, avg_check
            FROM daily_sales
            WHERE username = :u AND date >= :d
            ORDER BY date DESC
        """), {"u": username, "d": d14}).fetchall()
        all_sales = [dict(r._mapping) for r in rows]

        # Split: this week vs prior week
        sales       = [r for r in all_sales if str(r["date"]) >= d7]
        prior_sales = [r for r in all_sales if str(r["date"]) <  d7]

        # Labor cost over the same 7-day window as sales.
        # Paychex pay periods don't align with single days, so we sum the
        # whole window — whatever completed periods fall within it count.
        labor_row = conn.execute(text("""
            SELECT COALESCE(SUM(labor_cost), 0) as total_labor
            FROM daily_labor
            WHERE username = :u AND date >= :d
        """), {"u": username, "d": d7}).fetchone()
        labor_total = float(labor_row[0]) if labor_row else 0

        # Expenses over the same 7-day window
        exp_row = conn.execute(text("""
            SELECT COALESCE(SUM(amount), 0) as total_exp
            FROM expenses
            WHERE username = :u AND date >= :d
        """), {"u": username, "d": d7}).fetchone()
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
        "sales":           sales,         # newest first, last 7 days
        "prior_sales":     prior_sales,   # prior 7 days for WoW
        "labor_total":     labor_total,
        "expenses_week":   expenses_week,
        "today":           today,
    }


# ── Alerts ────────────────────────────────────────────────────────────────────

def _build_alerts(data: dict) -> list[str]:
    alerts = []
    sales  = data["sales"]
    prior  = data.get("prior_sales", [])

    if not sales:
        return ["No sales data yet — connect your Toast POS to get started."]

    yesterday = sales[0]
    yest_rev  = yesterday.get("revenue") or 0
    if yest_rev == 0:
        alerts.append("No sales recorded yesterday — check your Toast sync.")

    # Week-over-week revenue
    wtd_rev   = sum(r.get("revenue") or 0 for r in sales)
    prior_rev = sum(r.get("revenue") or 0 for r in prior)
    if prior_rev > 0 and wtd_rev > 0:
        wow_pct = (wtd_rev - prior_rev) / prior_rev * 100
        if wow_pct <= -10:
            alerts.append(f"Revenue is {abs(wow_pct):.0f}% below last week — review recent trends.")
        elif wow_pct >= 10:
            alerts.append(f"Revenue up {wow_pct:.0f}% vs last week — great momentum!")

    # Expense ratio alert
    if data["expenses_week"] > 0 and wtd_rev > 0:
        exp_ratio = data["expenses_week"] / wtd_rev * 100
        if exp_ratio > 45:
            alerts.append(f"Expenses at {exp_ratio:.0f}% of revenue this week — review your spend.")

    # Avg check dip
    yest_avg = yesterday.get("avg_check") or (yest_rev / yesterday["covers"] if yesterday.get("covers") else 0)
    if len(sales) >= 4 and yest_avg > 0:
        recent_avg = sum(
            r.get("avg_check") or (r.get("revenue", 0) / r["covers"] if r.get("covers") else 0)
            for r in sales[1:4]
        ) / 3
        if recent_avg > 0 and yest_avg < recent_avg * 0.92:
            alerts.append(f"Avg check dropped to ${yest_avg:.0f} — down from ${recent_avg:.0f} recent average.")

    # Labour (only if Paychex data exists)
    labor  = data["labor_total"]
    wtd_rv = sum(r.get("revenue") or 0 for r in sales)
    if labor > 0 and wtd_rv > 0:
        labor_pct_alert = labor / wtd_rv * 100
        if labor_pct_alert > 35:
            alerts.append(f"Labour at {labor_pct_alert:.0f}% of revenue this week — target under 35%.")

    if not alerts:
        alerts.append("All metrics look healthy today. Keep it up!")
    return alerts


# ── HTML card ─────────────────────────────────────────────────────────────────

def generate_card_html(data: dict) -> str:
    sales           = data["sales"]
    prior_sales     = data.get("prior_sales", [])
    restaurant_name = data["restaurant_name"]
    today           = data["today"]
    alerts          = _build_alerts(data)

    # Yesterday summary
    yest       = sales[0] if sales else {}
    yest_rev   = yest.get("revenue") or 0
    yest_covers = yest.get("covers") or 0
    yest_avg   = yest.get("avg_check") or (yest_rev / yest_covers if yest_covers else 0)

    # Week totals
    wtd_rev   = sum(r.get("revenue") or 0 for r in sales)
    prior_rev = sum(r.get("revenue") or 0 for r in prior_sales)

    # Week-over-week %
    if prior_rev > 0 and wtd_rev > 0:
        wow_pct  = (wtd_rev - prior_rev) / prior_rev * 100
        wow_str  = f"{'+' if wow_pct >= 0 else ''}{wow_pct:.0f}%"
        wow_cls  = "ok" if wow_pct >= 0 else "warn"
    else:
        wow_str = "—"
        wow_cls = ""

    # Expense ratio
    exp_ratio     = data["expenses_week"] / wtd_rev * 100 if wtd_rev > 0 and data["expenses_week"] > 0 else 0
    exp_ratio_cls = "warn" if exp_ratio > 45 else ("" if exp_ratio == 0 else "ok")

    # Labour % — compared against 7-day revenue so the window matches
    labor_total = data["labor_total"]
    labor_pct   = labor_total / wtd_rev * 100 if labor_total > 0 and wtd_rev > 0 else 0

    # 7-day cards (oldest → newest)
    day_cards = list(reversed(sales[:7]))

    def fmt_money(v):
        return f"${v:,.0f}"

    def _day_label(d):
        try:
            dt = date.fromisoformat(str(d))
            return dt.strftime("%a") + " " + str(dt.day)
        except Exception:
            return str(d)[-5:]

    def day_card_html(row):
        rev  = row.get("revenue") or 0
        cov  = row.get("covers")  or 0
        avg  = row.get("avg_check") or (rev / cov if cov else 0)
        label = _day_label(row.get("date", ""))
        return f"""
        <div class="day-card">
          <div class="day-label">{label}</div>
          <div class="day-rev">{fmt_money(rev)}</div>
          <div class="day-meta">{cov} covers &nbsp;·&nbsp; {fmt_money(avg)} avg</div>
        </div>"""

    day_cards_html = "".join(day_card_html(r) for r in day_cards) if day_cards else \
        '<div class="day-card" style="opacity:.4">No data yet</div>'

    alerts_html = "".join(f'<div class="alert-item">{"⚠" if "%" in a or "drop" in a or "below" in a or "No sales" in a else "✓"} {a}</div>' for a in alerts)

    # Build KPI row — Labour only if we have data
    kpi_labor_html = ""
    if labor_pct > 0:
        labor_cls = "warn" if labor_pct > 35 else "ok"
        kpi_labor_html = f"""
    <div class="kpi {labor_cls}">
      <div class="val">{labor_pct:.0f}%</div>
      <div class="lbl">Labour 7 Days</div>
    </div>"""

    exp_ratio_val = f"{exp_ratio:.0f}%" if exp_ratio > 0 else "—"

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
  .hero-stats {{ display: flex; gap: 24px; margin-top: 4px; }}
  .hero-stat {{ text-align: right; }}
  .hero-stat .val {{ font-size: 18px; font-weight: 700; color: #fff; }}
  .hero-stat .lbl {{ font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 0.8px; }}

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
  .alert-item {{ font-size: 12px; color: #ddd; padding: 3px 0; line-height: 1.5; }}

  /* KPI row */
  .kpi-row {{ display: flex; gap: 10px; margin-bottom: 14px; }}
  .kpi {{
    flex: 1;
    background: #1a1a1d;
    border-radius: 8px;
    padding: 14px 16px;
    text-align: center;
  }}
  .kpi .val {{ font-size: 20px; font-weight: 800; color: #fff; }}
  .kpi .lbl {{ font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 0.8px; margin-top: 3px; }}
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
  .days {{ display: flex; gap: 8px; }}
  .day-card {{
    flex: 1;
    background: #1a1a1d;
    border-radius: 8px;
    padding: 12px 10px;
    text-align: center;
  }}
  .day-label {{ font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 5px; }}
  .day-rev   {{ font-size: 15px; font-weight: 800; color: #fff; margin-bottom: 3px; }}
  .day-meta  {{ font-size: 9.5px; color: #555; }}

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
    <div class="kpi {wow_cls}">
      <div class="val">{wow_str}</div>
      <div class="lbl">vs Last Week</div>
    </div>
    <div class="kpi {exp_ratio_cls}">
      <div class="val">{exp_ratio_val}</div>
      <div class="lbl">Expense Ratio</div>
    </div>
    <div class="kpi">
      <div class="val">{fmt_money(data['expenses_week'])}</div>
      <div class="lbl">Expenses 7 Days</div>
    </div>
    <div class="kpi">
      <div class="val">{fmt_money(wtd_rev)}</div>
      <div class="lbl">Revenue 7 Days</div>
    </div>{kpi_labor_html}
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


# ── PNG / PDF rendering ───────────────────────────────────────────────────────

async def _render_png(html: str, out_path: str) -> None:
    """Render HTML card to PNG using playwright headless Chrome."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page    = await browser.new_page(viewport={"width": 780, "height": 600})
        await page.set_content(html, wait_until="domcontentloaded")
        height = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size({"width": 780, "height": height})
        await page.screenshot(path=out_path, full_page=True)
        await browser.close()


async def _render_pdf(html: str, out_path: str) -> None:
    """Render HTML card to PDF using playwright headless Chrome."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page    = await browser.new_page(viewport={"width": 780, "height": 600})
        await page.set_content(html, wait_until="domcontentloaded")
        await page.pdf(
            path=out_path,
            width="780px",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        await browser.close()


def render_png(html: str, out_path: str) -> None:
    asyncio.run(_render_png(html, out_path))


def render_pdf(html: str, out_path: str) -> None:
    asyncio.run(_render_pdf(html, out_path))


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
        print(f"PNG render failed ({e}), skipping image send.")
        return False

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


# ── Email delivery ─────────────────────────────────────────────────────────────

def send_daily_card_email(username: str, out_dir: str = "/tmp") -> bool:
    """
    Full pipeline: fetch data → build HTML → render PDF → send via email.

    Required env vars (set in Railway or Streamlit secrets):
        EMAIL_FROM      — sender address  (e.g. reports@tablemetrics.io)
        EMAIL_PASSWORD  — SMTP password / app-password
        EMAIL_SMTP_HOST — defaults to smtp.gmail.com
        EMAIL_SMTP_PORT — defaults to 587

    The recipient is the email stored in the users table for this username.
    Returns True on success.
    """
    import smtplib
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    smtp_host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    from_addr = os.environ.get("EMAIL_FROM", "")
    password  = os.environ.get("EMAIL_PASSWORD", "")

    if not from_addr or not password:
        print("EMAIL_FROM / EMAIL_PASSWORD not configured — skipping email send.")
        return False

    data     = fetch_card_data(username)
    to_addr  = data.get("email")
    if not to_addr:
        print(f"No email on file for {username}")
        return False

    html     = generate_card_html(data)
    pdf_path = f"{out_dir}/daily_card_{username}.pdf"

    try:
        render_pdf(html, pdf_path)
    except Exception as e:
        print(f"PDF render failed ({e}), skipping email send.")
        return False

    # Build the email
    restaurant = data["restaurant_name"]
    today_str  = data["today"].strftime("%B") + " " + str(data["today"].day) + ", " + str(data["today"].year)
    subject    = f"Your Daily Report — {restaurant} — {today_str}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"TableMetrics <{from_addr}>"
    msg["To"]      = to_addr

    # Plain-text body
    body_text = (
        f"Good morning!\n\n"
        f"Your daily performance report for {restaurant} is attached.\n\n"
        f"— TableMetrics"
    )
    msg.attach(MIMEText(body_text, "plain"))

    # PDF attachment
    with open(pdf_path, "rb") as f:
        pdf_part = MIMEApplication(f.read(), _subtype="pdf")
        pdf_part.add_header(
            "Content-Disposition", "attachment",
            filename=f"daily_report_{data['today'].isoformat()}.pdf",
        )
        msg.attach(pdf_part)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(from_addr, password)
            server.sendmail(from_addr, to_addr, msg.as_string())
        print(f"Email sent to {to_addr}")
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False


def send_all_daily_cards(out_dir: str = "/tmp") -> None:
    """Send morning cards (Telegram + email) to every user who has a recipient configured."""
    from data.database import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT username FROM users WHERE username IS NOT NULL"
        )).fetchall()
    for row in rows:
        uname = row[0]
        try:
            send_daily_card(uname, out_dir=out_dir)
        except Exception as e:
            print(f"Telegram card failed for {uname}: {e}")
        try:
            send_daily_card_email(uname, out_dir=out_dir)
        except Exception as e:
            print(f"Email card failed for {uname}: {e}")

"""
Summary — business overview dashboard.
"""

import json
from pathlib import Path

import streamlit as st

from components.kpi_card import format_currency, format_pct, threshold_badge
from components.charts import revenue_trend, revenue_by_dow, revenue_per_cover_trend
from components.theme import page_header, section_header, health_badge
from data import database as db
from data.loader import _has_toast_scraper_creds, _has_paychex_scraper_creds

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)
THRESHOLDS = CONFIG.get("thresholds", {})

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    f"🍽️ {user['restaurant_name']}",
    subtitle=(
        "Business Intelligence Dashboard  ·  Simulated data mode"
        if user.get("use_simulated_data")
        else f"Business Intelligence Dashboard  ·  {start_date} – {end_date}"
    ),
    eyebrow="Shareholder Overview",
)

# ── Sync Now panel ────────────────────────────────────────────────────────────
_uses_scraper = (
    not user.get("use_simulated_data") and
    (_has_toast_scraper_creds(user) or _has_paychex_scraper_creds(user))
)

with st.sidebar:
    st.divider()
    last_sync = user.get("last_sync_at")
    last_status = user.get("last_sync_status") or ""
    if last_sync:
        st.caption(f"Last sync: {str(last_sync)[:16]} UTC")
        if last_status and last_status != "ok":
            st.warning(f"Last sync had errors — check Account settings.")
        else:
            st.caption("Status: OK")
    else:
        st.caption("Never synced from live sources.")

    if _uses_scraper:
        st.info(
            "Portal sync (Toast / Paychex login) runs automatically via "
            "GitHub Actions nightly at 6 AM UTC. It cannot run in the browser."
        )
    else:
        if st.button("Sync Now", use_container_width=True):
            from data.sync import sync_all
            with st.spinner("Syncing data…"):
                _results = sync_all(user)
            _errors = {s: r["error"] for s, r in _results.items() if r["error"]}
            if _errors:
                for src, err in _errors.items():
                    st.error(f"{src}: {err}")
            else:
                total = sum(r["rows"] for r in _results.values())
                st.success(f"Sync complete — {total} rows updated.")
            st.session_state["user"] = db.get_user(username)
            st.rerun()

# ── Load data ─────────────────────────────────────────────────────────────────
kpi         = db.get_kpi_today(username, as_of_date=end_date)
daily_sales = db.get_daily_sales(username, start_date=start_date, end_date=end_date)

if not kpi or daily_sales.empty:
    st.warning("No data found for the selected period. Adjust the date range in the sidebar.")
    st.stop()

# ── Period-over-period deltas (first half vs second half) ─────────────────────
mid = len(daily_sales) // 2
rev_recent    = daily_sales.iloc[mid:]["revenue"].sum()
rev_prior     = daily_sales.iloc[:mid]["revenue"].sum()
rev_delta     = f"{(rev_recent/rev_prior - 1)*100:+.1f}% vs prior period" if rev_prior else None
covers_recent = daily_sales.iloc[mid:]["covers"].sum()
covers_prior  = daily_sales.iloc[:mid]["covers"].sum()
covers_delta  = f"{(covers_recent/covers_prior - 1)*100:+.1f}% vs prior period" if covers_prior else None
chk_recent    = daily_sales.iloc[mid:]["avg_check"].mean()
chk_prior     = daily_sales.iloc[:mid]["avg_check"].mean()
chk_delta     = f"{(chk_recent/chk_prior - 1)*100:+.1f}% vs prior period" if chk_prior else None

# ── Business Health Score ─────────────────────────────────────────────────────
prime    = kpi["prime_cost_pct"]
food_pct = kpi["food_cost_pct"]
labor    = kpi["labor_cost_pct"]
prime_t  = THRESHOLDS.get("prime_cost_pct_target", 60)
prime_w  = THRESHOLDS.get("prime_cost_pct_warning", 65)
food_t   = THRESHOLDS.get("food_cost_pct_target", 30)
food_w   = THRESHOLDS.get("food_cost_pct_warning", 33)
labor_t  = THRESHOLDS.get("labor_cost_pct_target", 30)
labor_w  = THRESHOLDS.get("labor_cost_pct_warning", 33)

alerts = sum([
    prime > prime_w,
    food_pct > food_w,
    labor > labor_w,
])
warnings = sum([
    prime_t < prime <= prime_w,
    food_t < food_pct <= food_w,
    labor_t < labor <= labor_w,
])

if alerts:
    hs_status, hs_label = "alert", f"Needs Attention — {alerts} alert{'s' if alerts > 1 else ''}"
elif warnings:
    hs_status, hs_label = "warning", f"Watch Closely — {warnings} warning{'s' if warnings > 1 else ''}"
else:
    hs_status, hs_label = "good", "All Systems Healthy"

st.markdown(
    f'<div style="margin:0.6rem 0 1.2rem 0">'
    f'<span style="font-size:0.65rem;text-transform:uppercase;letter-spacing:2px;'
    f'color:rgba(212,168,75,0.7);font-weight:700;">Business Health</span>&nbsp;&nbsp;'
    f'{health_badge(hs_label, hs_status)}</div>',
    unsafe_allow_html=True,
)

# ── Most-recent-day KPI strip ──────────────────────────────────────────────────
section_header(f"Most Recent Day — {kpi['date']}")
c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    st.metric("Daily Revenue",    format_currency(kpi["revenue"]),
              help="Total revenue for the most recent day.")
with c2:
    st.metric("Net Profit",       format_currency(kpi["net_profit"]),
              help="Revenue minus food cost and labour cost.")
with c3:
    st.metric("Prime Cost %",
              threshold_badge(prime, prime_t, prime_w),
              help=f"Food + labour cost %. Target ≤{prime_t:.0f}%.")
with c4:
    st.metric("Food Cost %",
              threshold_badge(food_pct, food_t, food_w),
              help=f"COGS as % of revenue. Target ≤{food_t:.0f}%.")
with c5:
    st.metric("Labour Cost %",
              threshold_badge(labor, labor_t, labor_w),
              help=f"Labour as % of revenue. Target ≤{labor_t:.0f}%.")
with c6:
    st.metric("Avg. Check",       format_currency(kpi["avg_check"]),
              help="Average revenue per guest cover.")

st.divider()

# ── Period summary strip ───────────────────────────────────────────────────────
section_header("Period Summary")
s1, s2, s3, s4, s5 = st.columns(5)
total_rev = daily_sales["revenue"].sum()
with s1:
    st.metric("Total Revenue",      format_currency(total_rev), delta=rev_delta)
with s2:
    st.metric("Total Covers",       f"{int(daily_sales['covers'].sum()):,}", delta=covers_delta)
with s3:
    st.metric("Avg. Check Size",    format_currency(daily_sales["avg_check"].mean()), delta=chk_delta)
with s4:
    food_pct_period = daily_sales["food_cost"].sum() / total_rev * 100 if total_rev else 0
    st.metric("Avg. Food Cost %",   format_pct(food_pct_period))
with s5:
    rev_per_cover = total_rev / daily_sales["covers"].sum() if daily_sales["covers"].sum() else 0
    st.metric("Rev per Cover",      format_currency(rev_per_cover),
              help="Total revenue divided by total guest covers for the period.")

st.divider()

# ── Revenue trend ─────────────────────────────────────────────────────────────
section_header("Revenue Trend")
st.plotly_chart(revenue_trend(daily_sales, days=len(daily_sales)), use_container_width=True)

st.divider()

# ── Day-of-week & spend-per-head ──────────────────────────────────────────────
section_header("Traffic & Spend Analysis")
col_dow, col_sph = st.columns(2)
with col_dow:
    st.plotly_chart(revenue_by_dow(daily_sales), use_container_width=True)
with col_sph:
    st.plotly_chart(revenue_per_cover_trend(daily_sales), use_container_width=True)

st.divider()

# ── Best / worst days ─────────────────────────────────────────────────────────
section_header("Performance Extremes")
t1, t2, t3, t4 = st.columns(4)
peak = daily_sales.loc[daily_sales["revenue"].idxmax()]
low  = daily_sales.loc[daily_sales["revenue"].idxmin()]
with t1:
    st.metric("Best Day",          peak["date"])
    st.metric("Best Day Revenue",  format_currency(peak["revenue"]))
with t2:
    st.metric("Avg. Daily Revenue", format_currency(daily_sales["revenue"].mean()))
    st.metric("Avg. Covers / Day",  f"{daily_sales['covers'].mean():.0f}")
with t3:
    st.metric("Lowest Day",         low["date"])
    st.metric("Lowest Day Revenue", format_currency(low["revenue"]))
with t4:
    high_chk = daily_sales.loc[daily_sales["avg_check"].idxmax()]
    st.metric("Highest Avg Check",  format_currency(high_chk["avg_check"]))
    st.metric("On Date",            high_chk["date"])

st.divider()
st.caption(
    f"Confidential  ·  For authorised recipients only  ·  "
    f"{user['restaurant_name']} Business Intelligence Dashboard"
)

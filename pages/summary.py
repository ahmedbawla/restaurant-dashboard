"""
Summary — business overview dashboard.
Shows whatever data sources are connected; never stops if only some are synced.
"""

import json
from pathlib import Path

import streamlit as st

from components.kpi_card import format_currency, format_pct, threshold_badge
from components.charts import revenue_trend, revenue_by_dow, revenue_per_cover_trend
from components.theme import page_header, section_header, health_badge
from data import database as db
import plotly.express as px

with open(Path(__file__).parent.parent / "config.json") as f:
    CONFIG = json.load(f)
THRESHOLDS = CONFIG.get("thresholds", {})

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

last_status = user.get("last_sync_status") or ""
page_header(
    f"🍽️ {user['restaurant_name']}",
    subtitle=(
        "Business Intelligence Dashboard  ·  Demo data"
        if last_status == "demo"
        else f"Business Intelligence Dashboard  ·  {start_date} – {end_date}"
    ),
    eyebrow="Shareholder Overview",
)

# ── Load all data sources ─────────────────────────────────────────────────────
kpi          = db.get_kpi_today(username, as_of_date=end_date)
daily_sales  = db.get_daily_sales(username,  start_date=start_date, end_date=end_date)
daily_labor  = db.get_daily_labor(username,  start_date=start_date, end_date=end_date)
expenses     = db.get_expenses(username,     start_date=start_date, end_date=end_date)
menu_items   = db.get_menu_items(username)

has_sales    = not daily_sales.empty
has_labor    = not daily_labor.empty
has_expenses = not expenses.empty
has_menu     = not menu_items.empty
has_any      = has_sales or has_labor or has_expenses or has_menu

# ── Gate: nothing at all ──────────────────────────────────────────────────────
if not has_any:
    st.warning(
        "No data found for the selected period. "
        "Connect an integration in **Account Settings** or adjust the date range."
    )
    st.stop()

# ── Connected-source banner ───────────────────────────────────────────────────
_connected = []
_missing   = []
if has_sales:    _connected.append("Toast POS")
else:            _missing.append("Toast POS (Sales)")
if has_labor:   _connected.append("Paychex")
else:            _missing.append("Paychex (Payroll & Labour)")
if has_expenses: _connected.append("QuickBooks")
else:            _missing.append("QuickBooks (Expenses)")

if _missing:
    st.info(
        f"Showing data from: **{', '.join(_connected)}**. "
        f"Connect **{', '.join(_missing)}** in Account Settings for a complete picture."
    )

# ── Business Health Score (requires sales; labour optional) ───────────────────
if has_sales and kpi:
    prime_t = THRESHOLDS.get("prime_cost_pct_target", 60)
    prime_w = THRESHOLDS.get("prime_cost_pct_warning", 65)
    labor_t = THRESHOLDS.get("labor_cost_pct_target", 30)
    labor_w = THRESHOLDS.get("labor_cost_pct_warning", 33)

    prime = kpi["prime_cost_pct"]
    labor = kpi["labor_cost_pct"]

    if has_labor:
        alerts   = sum([prime > prime_w, labor > labor_w])
        warnings = sum([prime_t < prime <= prime_w, labor_t < labor <= labor_w])
        if alerts:
            hs_status, hs_label = "alert", f"Needs Attention — {alerts} alert{'s' if alerts > 1 else ''}"
        elif warnings:
            hs_status, hs_label = "warning", f"Watch Closely — {warnings} warning{'s' if warnings > 1 else ''}"
        else:
            hs_status, hs_label = "good", "All Systems Healthy"
    else:
        hs_status, hs_label = "good", "Sales Tracking Active (Payroll not connected)"

    st.markdown(
        f'<div style="margin:0.6rem 0 0.5rem 0">'
        f'<span style="font-size:0.65rem;text-transform:uppercase;letter-spacing:2px;'
        f'color:rgba(212,168,75,0.7);font-weight:700;">Business Health</span>&nbsp;&nbsp;'
        f'{health_badge(hs_label, hs_status)}</div>',
        unsafe_allow_html=True,
    )

    if has_labor and (alerts or warnings):
        _advice = {
            "Prime Cost %":  "Prime cost = food + labour combined. Reduce by aligning staff hours with peak trading windows and reviewing supplier pricing.",
            "Labour Cost %": "Labour as a % of revenue. Adjust shift schedules to better match your busy and quiet periods.",
        }
        _issues = []
        for _name, _val, _tgt, _wrn in [
            ("Prime Cost %",  prime, prime_t, prime_w),
            ("Labour Cost %", labor, labor_t, labor_w),
        ]:
            if _val > _tgt:
                _issues.append((_name, _val, _tgt, _wrn, _val > _wrn))
        with st.expander("View issues →", expanded=True):
            for _name, _val, _tgt, _wrn, _is_alert in _issues:
                (st.error if _is_alert else st.warning)(
                    f"**{_name}: {_val:.1f}%** — "
                    f"{'above alert threshold' if _is_alert else 'above target'} "
                    f"(target ≤{_tgt:.0f}%, alert >{_wrn:.0f}%)  \n"
                    f"{_advice[_name]}"
                )

# ── Sales KPIs (Toast) ────────────────────────────────────────────────────────
if has_sales and kpi:
    mid           = len(daily_sales) // 2
    rev_recent    = daily_sales.iloc[mid:]["revenue"].sum()
    rev_prior     = daily_sales.iloc[:mid]["revenue"].sum()
    rev_delta     = f"{(rev_recent/rev_prior - 1)*100:+.1f}% vs prior period" if rev_prior else None
    covers_recent = daily_sales.iloc[mid:]["covers"].sum()
    covers_prior  = daily_sales.iloc[:mid]["covers"].sum()
    covers_delta  = f"{(covers_recent/covers_prior - 1)*100:+.1f}% vs prior period" if covers_prior else None
    chk_recent    = daily_sales.iloc[mid:]["avg_check"].mean()
    chk_prior     = daily_sales.iloc[:mid]["avg_check"].mean()
    chk_delta     = f"{(chk_recent/chk_prior - 1)*100:+.1f}% vs prior period" if chk_prior else None
    total_rev     = daily_sales["revenue"].sum()

    section_header(f"Most Recent Day — {kpi['date']}", help="KPIs for the most recent date in your dataset.")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Daily Revenue",  format_currency(kpi["revenue"]))
    with c2: st.metric("Net Profit",     format_currency(kpi["net_profit"]))
    with c3:
        if has_labor:
            st.metric("Prime Cost %",    threshold_badge(kpi["prime_cost_pct"], prime_t, prime_w),
                      help="Food + Labour as a % of revenue.")
        else:
            st.metric("Prime Cost %",    "—", help="Connect Paychex to calculate prime cost.")
    with c4:
        if has_labor:
            st.metric("Labour Cost %",   threshold_badge(kpi["labor_cost_pct"], labor_t, labor_w))
        else:
            st.metric("Labour Cost %",   "—", help="Connect Paychex to see labour cost.")
    with c5: st.metric("Avg. Check",     format_currency(kpi["avg_check"]))

    st.divider()

    section_header("Period Summary", help="Totals and averages across the entire selected date range.")
    s1, s2, s3, s4, s5 = st.columns(5)
    with s1: st.metric("Total Revenue",      format_currency(total_rev), delta=rev_delta)
    with s2: st.metric("Total Covers",       f"{int(daily_sales['covers'].sum()):,}", delta=covers_delta)
    with s3: st.metric("Avg. Check Size",    format_currency(daily_sales["avg_check"].mean()), delta=chk_delta)
    with s4: st.metric("Avg. Daily Revenue", format_currency(daily_sales["revenue"].mean()))
    with s5:
        rpc = total_rev / daily_sales["covers"].sum() if daily_sales["covers"].sum() else 0
        st.metric("Rev per Cover",    format_currency(rpc))

    st.divider()

    section_header("Revenue Trend", help="Daily revenue over the selected period with a 7-day rolling average.")
    st.plotly_chart(revenue_trend(daily_sales, days=len(daily_sales)), use_container_width=True)

    st.divider()

    section_header("Traffic & Spend Analysis", help="Left: average revenue by day of week. Right: revenue per guest transaction over time.")
    col_dow, col_sph = st.columns(2)
    with col_dow: st.plotly_chart(revenue_by_dow(daily_sales), use_container_width=True)
    with col_sph: st.plotly_chart(revenue_per_cover_trend(daily_sales), use_container_width=True)

    st.divider()

    section_header("Performance Extremes", help="Best and worst revenue days in the period.")
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

# ── Spending Overview (QuickBooks) ────────────────────────────────────────────
if has_expenses:
    # Filter out pending so category totals are meaningful
    _cat_expenses = expenses[expenses["category"] != "Pending Review"]
    _pending      = expenses[expenses["category"] == "Pending Review"]
    _total_spend  = expenses["amount"].sum()
    _pending_amt  = _pending["amount"].sum()

    section_header("Spending Overview", help="Operating expenses from QuickBooks for the selected period. Pending = unreviewed bank feed transactions.")
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.metric("Total Spend", format_currency(_total_spend))
    with e2:
        if not _cat_expenses.empty:
            _top_cat = _cat_expenses.groupby("category")["amount"].sum().idxmax()
            st.metric("Largest Category", _top_cat)
        else:
            st.metric("Largest Category", "—")
    with e3:
        st.metric("Pending Review", format_currency(_pending_amt),
                  help="Unreviewed bank feed transactions — categorise in QBO to see full breakdown.")
    with e4:
        st.metric("Unique Vendors", str(expenses["vendor"].nunique()))

    if not _cat_expenses.empty:
        _top3 = (
            _cat_expenses.groupby("category")["amount"]
            .sum()
            .nlargest(5)
            .reset_index()
        )
        _top3.columns = ["Category", "Amount"]
        _top3["Amount"] = _top3["Amount"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(_top3, use_container_width=True, hide_index=True)

    st.divider()

# ── Labour Overview (Paychex, only when no sales to avoid duplication) ────────
if has_labor and not has_sales:
    _labor_total = daily_labor["labor_cost"].sum()
    _hours_total = daily_labor["hours"].sum()

    section_header("Labour Overview", help="Payroll and labour data from Paychex for the selected period.")
    l1, l2, l3 = st.columns(3)
    with l1: st.metric("Total Labour Cost", format_currency(_labor_total))
    with l2: st.metric("Total Hours",       f"{_hours_total:,.0f} hrs")
    with l3: st.metric("Avg. Hourly Cost",  format_currency(_labor_total / _hours_total) if _hours_total else "—")

    st.divider()

# ── Menu Mix Snapshot (Toast item data) ──────────────────────────────────────
if has_menu:
    section_header("Menu Mix Snapshot", help="Top items and category revenue split from your uploaded Toast item data.")

    _cat_rev = (
        menu_items.groupby("category", as_index=False)["total_revenue"]
        .sum()
        .sort_values("total_revenue", ascending=False)
    )
    _top5_items = menu_items.nlargest(5, "total_revenue")[["name", "category", "quantity_sold", "total_revenue"]].copy()
    _top5_items["total_revenue"] = _top5_items["total_revenue"].apply(lambda x: f"${x:,.0f}")
    _top5_items["quantity_sold"] = _top5_items["quantity_sold"].apply(lambda x: f"{x:,}")
    _top5_items.columns = ["Item", "Category", "Qty Sold", "Revenue"]

    _LAYOUT_M = dict(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(240,242,246,0.75)"),
        margin=dict(l=0, r=0, t=10, b=0),
    )

    mc1, mc2 = st.columns([1.2, 1])
    with mc1:
        fig_menu = px.bar(
            _cat_rev.sort_values("total_revenue"),
            x="total_revenue", y="category", orientation="h",
            color="total_revenue",
            color_continuous_scale=["#3a1a0a", "#FF6B35"],
            labels={"total_revenue": "Revenue", "category": ""},
        )
        fig_menu.update_coloraxes(showscale=False)
        fig_menu.update_xaxes(tickprefix="$", gridcolor="rgba(255,255,255,0.06)")
        fig_menu.update_layout(**_LAYOUT_M)
        st.plotly_chart(fig_menu, use_container_width=True)

    with mc2:
        st.caption("**Top 5 Items by Revenue**")
        st.dataframe(_top5_items, use_container_width=True, hide_index=True)

    st.divider()

st.caption(
    f"Confidential  ·  For authorised recipients only  ·  "
    f"{user['restaurant_name']} Business Intelligence Dashboard"
)

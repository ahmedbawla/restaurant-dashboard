"""
Spending & Expenses — QuickBooks Online data.
"""

import streamlit as st
import pandas as pd

from components.charts import expense_pie, top_vendors_bar, expense_trend_weekly
from components.kpi_card import format_currency
from components.theme import page_header, section_header
from data import database as db
from utils.oauth_quickbooks import is_configured as qb_secrets_configured

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

_qb_connected = bool(user.get("qb_realm_id") and user.get("qb_refresh_token"))

# ── Header + QuickBooks connection panel (top-right) ──────────────────────────
_hdr_col, _qb_col = st.columns([3, 1])
with _hdr_col:
    page_header(
        "💳 Spending & Expenses",
        subtitle="Operating expense breakdown sourced from QuickBooks Online.",
        eyebrow="Financial Analysis",
    )

with _qb_col:
    st.markdown("<div style='height:1.4rem'></div>", unsafe_allow_html=True)
    if _qb_connected:
        st.markdown(
            "<span style='background:rgba(39,174,96,0.15);border:1px solid rgba(39,174,96,0.4);"
            "border-radius:20px;padding:4px 12px;font-size:0.75rem;color:#2ecc71;"
            "font-weight:600;white-space:nowrap;display:inline-block;margin-bottom:6px;"
            "'>● QuickBooks Connected</span>",
            unsafe_allow_html=True,
        )
        _rc1, _rc2 = st.columns(2)
        if _rc1.button("Reconnect", key="qb_reconnect", use_container_width=True):
            st.session_state["_qb_action"] = "reconnect"
        if _rc2.button("Disconnect", key="qb_disconnect", use_container_width=True):
            st.session_state["_qb_action"] = "disconnect"
    else:
        st.markdown(
            "<span style='background:rgba(231,76,60,0.12);border:1px solid rgba(231,76,60,0.35);"
            "border-radius:20px;padding:4px 12px;font-size:0.75rem;color:#e74c3c;"
            "font-weight:600;white-space:nowrap;display:inline-block;margin-bottom:6px;"
            "'>○ Not Connected</span>",
            unsafe_allow_html=True,
        )
        if qb_secrets_configured():
            if st.button("Connect QuickBooks", key="qb_connect", use_container_width=True):
                st.session_state["_qb_action"] = "connect"

# ── Handle QB actions ─────────────────────────────────────────────────────────
_qb_action = st.session_state.pop("_qb_action", None)

if _qb_action == "disconnect":
    db.update_user(username, qb_realm_id=None, qb_refresh_token=None, qb_banking_scope=False)
    st.session_state["user"] = db.get_user(username)
    st.cache_data.clear()
    st.rerun()

if _qb_action in ("connect", "reconnect"):
    if qb_secrets_configured():
        from utils.oauth_quickbooks import generate_nonce, get_auth_url as qb_auth_url
        _nonce = generate_nonce()
        db.update_user(username, oauth_state=_nonce)
        _auth_url = qb_auth_url(username, _nonce)
        st.markdown(
            f'<a href="{_auth_url}" target="_blank" rel="noopener noreferrer">'
            f'<button style="background:#2da44e;color:white;border:none;padding:0.5rem 1.2rem;'
            f'border-radius:0.5rem;font-weight:600;font-size:0.9rem;cursor:pointer;width:100%;">'
            f'Open QuickBooks ↗</button></a>',
            unsafe_allow_html=True,
        )
        st.caption("A new tab will open. After authorising, you'll be redirected back.")

# ── Data ─────────────────────────────────────────────────────────────────────
expenses = db.get_expenses(username, start_date=start_date, end_date=end_date)

if expenses.empty:
    if not _qb_connected:
        st.warning(
            "QuickBooks is not connected. Use the **Connect QuickBooks** button above "
            "to start pulling your expense data automatically."
        )
    else:
        st.warning("No expense data found for the selected period.")
    st.stop()

expenses["date"] = pd.to_datetime(expenses["date"])

# ── Pending review notice ──────────────────────────────────────────────────────
_pending_mask = expenses["category"] == "Pending Review"
if _pending_mask.any():
    _p_count  = int(_pending_mask.sum())
    _p_amount = expenses.loc[_pending_mask, "amount"].sum()
    st.info(
        f"**{_p_count:,} unreviewed transaction{'s' if _p_count != 1 else ''}** "
        f"({format_currency(_p_amount)}) have not yet been categorised in QuickBooks "
        f"and are labelled **'Pending Review'**. They are included in all totals. "
        f"To categorise them, go to **QBO → Banking → For Review**."
    )

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    all_cats      = sorted(expenses["category"].unique())
    selected_cats = st.multiselect("Category", all_cats, default=all_cats)

filtered = expenses[expenses["category"].isin(selected_cats)]

if filtered.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

# ── Period-over-period ────────────────────────────────────────────────────────
filtered_sorted = filtered.sort_values("date")
mid = len(filtered_sorted) // 2
spend_recent = filtered_sorted.iloc[mid:]["amount"].sum()
spend_prior  = filtered_sorted.iloc[:mid]["amount"].sum()
spend_delta  = f"{(spend_recent/spend_prior - 1)*100:+.1f}% vs prior period" if spend_prior else None

# ── KPI strip ─────────────────────────────────────────────────────────────────
section_header("Expense Overview", help="Operating expenses from QuickBooks Online for the selected period. Delta compares the second half of the period to the first.")
total_spend  = filtered["amount"].sum()
daily_avg    = filtered.groupby(filtered["date"].dt.date)["amount"].sum().mean()
top_cat      = filtered.groupby("category")["amount"].sum().idxmax()
top_vendor   = filtered.groupby("vendor")["amount"].sum().idxmax()
cat_totals   = filtered.groupby("category")["amount"].sum()
top_cat_pct  = cat_totals.max() / cat_totals.sum() * 100

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Total Spend",      format_currency(total_spend), delta=spend_delta)
with k2:
    st.metric("Avg. Daily Spend", format_currency(daily_avg))
with k3:
    st.metric("Largest Category", top_cat,
              help=f"{top_cat_pct:.1f}% of total spend")
with k4:
    st.metric("Top Vendor",       top_vendor)
with k5:
    st.metric("Unique Vendors",   str(filtered["vendor"].nunique()))

st.divider()

# ── Charts row ────────────────────────────────────────────────────────────────
section_header("Breakdown", help="Left: each expense category as a share of total spend. Right: your top vendors by total amount paid in the period.")
col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(expense_pie(filtered), use_container_width=True)
with col2:
    st.plotly_chart(top_vendors_bar(filtered), use_container_width=True)

st.divider()

# ── Weekly trend with rolling avg ─────────────────────────────────────────────
section_header("Weekly Trend", help="Total spend per week. The dotted line is a 4-week rolling average to show the underlying trend.")
st.plotly_chart(expense_trend_weekly(filtered), use_container_width=True)

# ── Category breakdown table ──────────────────────────────────────────────────
st.divider()
section_header("Category Summary", help="Total spend, number of transactions, and average transaction size for each expense category in the selected period.")
cat_summary = filtered.groupby("category")["amount"].agg(
    Total="sum", Count="count", Average="mean"
).reset_index().sort_values("Total", ascending=False)
cat_summary["Total"]   = cat_summary["Total"].apply(lambda x: f"${x:,.2f}")
cat_summary["Average"] = cat_summary["Average"].apply(lambda x: f"${x:,.2f}")
cat_summary.columns    = ["Category", "Total Spend", "# Transactions", "Avg Transaction"]
st.dataframe(cat_summary, use_container_width=True, hide_index=True)

# ── Transaction detail ────────────────────────────────────────────────────────
st.divider()
section_header("Transaction Detail", help="Individual expense line items from QuickBooks, sorted by most recent first. Use the Category filter in the sidebar to narrow results.")
display = filtered.copy()
display["date"]   = display["date"].dt.strftime("%Y-%m-%d")
display["amount"] = display["amount"].apply(lambda x: f"${x:,.2f}")
display = display[["date","category","vendor","amount","description"]].sort_values("date", ascending=False)
display.columns = ["Date","Category","Vendor","Amount","Description"]
st.dataframe(display, use_container_width=True, height=400, hide_index=True)

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

# ── QuickBooks Diagnostics ────────────────────────────────────────────────────
if _qb_connected:
    st.divider()
    with st.expander("QuickBooks Diagnostics", expanded=False):
        st.caption(
            "Queries QuickBooks directly and shows how many transactions and what "
            "total dollar amount each source returned for the last 90 days. "
            "Use this to identify where data is missing."
        )
        if st.button("Run Diagnostics", key="qb_diag"):
            from datetime import date, timedelta
            from data.connectors.quickbooks_connector import QuickBooksConnector
            _diag_conn = QuickBooksConnector({
                "realm_id":      user["qb_realm_id"],
                "refresh_token": user["qb_refresh_token"],
                "username":      username,
            })
            _diag_end   = date.today()
            _diag_start = _diag_end - timedelta(days=90)
            _sd, _ed    = _diag_start.isoformat(), _diag_end.isoformat()
            _diag_results = []

            for _label, _sql in [
                ("Purchase (credit card / check / cash)",
                 f"SELECT * FROM Purchase WHERE TxnDate >= '{_sd}' AND TxnDate <= '{_ed}'"),
                ("Bill (accounts payable invoices)",
                 f"SELECT * FROM Bill WHERE TxnDate >= '{_sd}' AND TxnDate <= '{_ed}'"),
                ("JournalEntry (payroll, depreciation, accruals)",
                 f"SELECT * FROM JournalEntry WHERE TxnDate >= '{_sd}' AND TxnDate <= '{_ed}'"),
            ]:
                try:
                    _txns  = _diag_conn._query_all(_sql)
                    _total = sum(float(t.get("TotalAmt", 0)) for t in _txns)
                    _diag_results.append({"Source": _label, "Transactions": len(_txns), "Total ($)": f"${_total:,.2f}"})
                except Exception as _e:
                    _diag_results.append({"Source": _label, "Transactions": "ERROR", "Total ($)": str(_e)})

            import pandas as _dpd
            st.dataframe(_dpd.DataFrame(_diag_results), use_container_width=True, hide_index=True)
            st.caption(f"Date range: {_sd} → {_ed}")

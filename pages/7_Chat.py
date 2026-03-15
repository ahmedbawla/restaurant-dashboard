"""
AI Data Assistant — natural language Q&A over restaurant data.
Only available on the test account.
"""

import os

import pandas as pd
import streamlit as st

from components.kpi_card import format_currency
from components.theme import page_header
from data import database as db

user     = st.session_state["user"]
username = user["username"]

if username != "test":
    st.warning("The AI Assistant is only available on the test account.")
    st.stop()

# ── API key ───────────────────────────────────────────────────────────────────
_api_key = None
try:
    _api_key = st.secrets["minimax"]["api_key"]
except Exception:
    pass
if not _api_key:
    _api_key = os.environ.get("MINIMAX_API_KEY")

if not _api_key:
    st.error(
        "MiniMax API key not configured. "
        "Add a `[minimax]` section with `api_key` to your Streamlit secrets."
    )
    st.stop()

start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "🤖 AI Data Assistant",
    subtitle="Ask anything about your restaurant data in plain English.",
    eyebrow="AI Analytics",
)

# ── Build data context (cached) ───────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _build_context(username, start_date, end_date, restaurant_name):
    lines = [
        f"RESTAURANT: {restaurant_name}",
        f"ANALYSIS PERIOD: {start_date} to {end_date}",
    ]

    ds = db.get_daily_sales(username, start_date=start_date, end_date=end_date)
    if not ds.empty:
        ds["_date"] = pd.to_datetime(ds["date"])
        lines.append("\nSALES & REVENUE:")
        lines.append(f"  Total Revenue: {format_currency(ds['revenue'].sum())}")
        lines.append(f"  Daily Average: {format_currency(ds['revenue'].mean())}")
        lines.append(f"  Total Covers: {int(ds['covers'].sum()):,}")
        lines.append(f"  Avg Check Size: {format_currency(ds['avg_check'].mean())}")
        lines.append(f"  Avg Food Cost %: {ds['food_cost_pct'].mean():.1f}%")
        dow = ds.groupby(ds["_date"].dt.day_name())["revenue"].mean().sort_values(ascending=False)
        lines.append(f"  Best Day of Week: {dow.index[0]} (avg {format_currency(dow.iloc[0])})")
        lines.append(f"  Weakest Day of Week: {dow.index[-1]} (avg {format_currency(dow.iloc[-1])})")
        ds["_month"] = ds["_date"].dt.to_period("M").astype(str)
        for m, v in ds.groupby("_month")["revenue"].sum().items():
            lines.append(f"  {m}: {format_currency(v)}")

    wp = db.get_weekly_payroll(username, start_date=start_date, end_date=end_date)
    if not wp.empty:
        total_pay = wp["gross_pay"].sum()
        total_hrs = wp["total_hours"].sum()
        lines.append("\nPAYROLL:")
        lines.append(f"  Total Gross Pay: {format_currency(total_pay)}")
        lines.append(f"  Total Hours: {total_hrs:,.0f}")
        lines.append(f"  Headcount: {wp['employee_name'].nunique()} employees")
        lines.append(f"  Avg Hourly Rate: {format_currency(total_pay / total_hrs if total_hrs else 0)}")
        for dept, row in wp.groupby("dept")[["gross_pay", "total_hours"]].sum().iterrows():
            lines.append(f"  {dept}: {format_currency(row['gross_pay'])} ({row['total_hours']:.0f} hrs)")
        lines.append("  Top 5 Earners:")
        for name, pay in wp.groupby("employee_name")["gross_pay"].sum().nlargest(5).items():
            lines.append(f"    {name}: {format_currency(pay)}")
        if not ds.empty and ds["revenue"].sum() > 0:
            lines.append(f"\nLABOR COST %: {total_pay / ds['revenue'].sum() * 100:.1f}%")

    exp = db.get_expenses(username, start_date=start_date, end_date=end_date)
    if not exp.empty:
        lines.append("\nEXPENSES:")
        lines.append(f"  Total: {format_currency(exp['amount'].sum())}")
        for cat, amt in exp.groupby("category")["amount"].sum().sort_values(ascending=False).items():
            lines.append(f"  {cat}: {format_currency(amt)}")
        lines.append("  Top 5 Vendors:")
        for v, amt in exp.groupby("vendor")["amount"].sum().nlargest(5).items():
            lines.append(f"    {v}: {format_currency(amt)}")

    return "\n".join(lines)


_context = _build_context(username, start_date, end_date, user["restaurant_name"])

_system = f"""You are an AI analytics assistant for a restaurant owner. \
Answer questions clearly and concisely using the data below. \
Be specific — use real numbers from the data. \
If something can't be answered from the data, say so honestly. \
Keep responses brief and actionable.

{_context}"""

# ── Chat UI ───────────────────────────────────────────────────────────────────
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = []

_, _clear_col = st.columns([8, 1])
with _clear_col:
    if st.button("Clear", use_container_width=True):
        st.session_state["chat_messages"] = []
        st.rerun()

for msg in st.session_state["chat_messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if not st.session_state["chat_messages"]:
    st.caption(
        "Try asking: *What was my best month for revenue?* · "
        "*Who worked the most hours?* · "
        "*What's my labor cost %?* · "
        "*What are my top expense categories?*"
    )

if prompt := st.chat_input("Ask about your data…"):
    st.session_state["chat_messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    import requests as _requests

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            _resp = _requests.post(
                "https://api.minimaxi.chat/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "MiniMax-Text-01",
                    "max_tokens": 1024,
                    "messages": [{"role": "system", "content": _system}]
                               + st.session_state["chat_messages"],
                },
                timeout=60,
            )
        if _resp.status_code != 200:
            st.error(f"MiniMax API error {_resp.status_code}: {_resp.text}")
            st.stop()
        _response = _resp.json()["choices"][0]["message"]["content"]
        st.markdown(_response)

    st.session_state["chat_messages"].append({"role": "assistant", "content": _response})

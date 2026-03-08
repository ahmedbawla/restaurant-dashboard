"""
Sales Analysis — Toast POS sales data.
"""

import streamlit as st

from components.charts import (
    hourly_heatmap, top_items_bar, avg_check_trend,
    covers_by_dow, revenue_trend, revenue_by_dow, revenue_per_cover_trend,
)
from components.kpi_card import format_currency
from components.theme import page_header, section_header
from data import database as db

user       = st.session_state["user"]
username   = user["username"]
start_date = st.session_state.get("start_date")
end_date   = st.session_state.get("end_date")

page_header(
    "📈 Sales Analysis",
    subtitle="Revenue, guest covers, and check-size trends from your uploaded sales data.",
    eyebrow="Revenue Analytics",
)

# ── Data ─────────────────────────────────────────────────────────────────────
daily_sales  = db.get_daily_sales(username,  start_date=start_date, end_date=end_date)
hourly_sales = db.get_hourly_sales(username, start_date=start_date, end_date=end_date)
menu_items   = db.get_menu_items(username)

# ── Toast upload ──────────────────────────────────────────────────────────────
def _render_toast_sales_upload():
    from utils.csv_importer import parse_sales_summary
    st.markdown("**Upload Toast Sales Summary CSV**")
    st.caption(
        "In Toast: Reports → Sales → Sales Summary → Export. "
        "You can upload multiple files (e.g. one per month) and data will be merged."
    )
    uploaded = st.file_uploader(
        "Sales Summary CSV / Excel", type=["csv", "xlsx"],
        key="sales_upload", label_visibility="collapsed",
    )
    if uploaded:
        try:
            df = parse_sales_summary(uploaded.getvalue(), uploaded.name)
            st.success(f"Parsed {len(df)} rows ({df['date'].min()} → {df['date'].max()})")
            if st.button("Import to Dashboard", key="sales_import_btn", type="primary"):
                rows = db.merge_df(df, "daily_sales", username, date_col="date")
                db.update_user(username, use_simulated_data=False)
                st.session_state["user"] = db.get_user(username)
                st.cache_data.clear()
                st.success(f"Imported {rows} rows. Refreshing…")
                st.rerun()
        except Exception as e:
            st.error(f"Could not parse file: {e}")

if daily_sales.empty:
    with st.container():
        st.info("No sales data yet. Upload a Toast Sales Summary export to get started.")
        _render_toast_sales_upload()
    st.stop()

with st.expander("Update Toast Sales Data", expanded=False):
    _render_toast_sales_upload()

# ── Period-over-period ────────────────────────────────────────────────────────
mid = len(daily_sales) // 2
rev_recent = daily_sales.iloc[mid:]["revenue"].sum()
rev_prior  = daily_sales.iloc[:mid]["revenue"].sum()
rev_delta  = f"{(rev_recent/rev_prior - 1)*100:+.1f}% vs prior period" if rev_prior else None
chk_recent = daily_sales.iloc[mid:]["avg_check"].mean()
chk_prior  = daily_sales.iloc[:mid]["avg_check"].mean()
chk_delta  = f"{(chk_recent/chk_prior - 1)*100:+.1f}% vs prior period" if chk_prior else None
cvr_recent = daily_sales.iloc[mid:]["covers"].sum()
cvr_prior  = daily_sales.iloc[:mid]["covers"].sum()
cvr_delta  = f"{(cvr_recent/cvr_prior - 1)*100:+.1f}% vs prior period" if cvr_prior else None

total_rev    = daily_sales["revenue"].sum()
total_covers = daily_sales["covers"].sum()
best_idx     = daily_sales["revenue"].idxmax()

# ── KPI strip ─────────────────────────────────────────────────────────────────
section_header("Period KPIs", help="Key revenue and guest metrics for the selected date range. Deltas compare the second half of the period against the first half.")
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Total Revenue",       format_currency(total_rev), delta=rev_delta)
with k2:
    st.metric("Total Covers",        f"{int(total_covers):,}", delta=cvr_delta)
with k3:
    st.metric("Avg. Check Size",     format_currency(daily_sales["avg_check"].mean()), delta=chk_delta)
with k4:
    st.metric("Best Day Revenue",    format_currency(daily_sales.loc[best_idx, "revenue"]),
              help=f"Recorded on {daily_sales.loc[best_idx, 'date']}.")
with k5:
    rpc = total_rev / total_covers if total_covers else 0
    st.metric("Rev per Cover",       format_currency(rpc),
              help="Average revenue generated per guest cover.")

st.divider()

# ── Revenue trend with 7-day rolling avg ─────────────────────────────────────
section_header("Revenue Trend", help="Daily revenue over the selected period with a 7-day rolling average overlay to show the underlying trend.")
st.plotly_chart(revenue_trend(daily_sales, days=len(daily_sales)), use_container_width=True)

st.divider()

# ── Peak hours heatmap ────────────────────────────────────────────────────────
section_header("Peak Hours Heatmap", help="Average revenue by hour of day and day of week. Darker cells = higher revenue. Use this to plan staffing and identify under-performing slots.")
if not hourly_sales.empty:
    st.plotly_chart(hourly_heatmap(hourly_sales), use_container_width=True)
else:
    st.info("Hourly data not available for this period.")

st.divider()

# ── Day-of-week & spend-per-head ──────────────────────────────────────────────
section_header("Traffic Patterns", help="Left: average revenue by day of week — shows your most and least profitable days. Right: average guest covers by day of week.")
col_a, col_b = st.columns(2)
with col_a:
    st.plotly_chart(revenue_by_dow(daily_sales), use_container_width=True)
with col_b:
    st.plotly_chart(covers_by_dow(daily_sales), use_container_width=True)

st.divider()

# ── Check size & spend per head trends ───────────────────────────────────────
section_header("Spend Trends", help="Left: average check size per day over time — a rising trend means guests are spending more per visit. Right: revenue per guest cover.")
col_c, col_d = st.columns(2)
with col_c:
    st.plotly_chart(avg_check_trend(daily_sales), use_container_width=True)
with col_d:
    st.plotly_chart(revenue_per_cover_trend(daily_sales), use_container_width=True)

st.divider()

# ── Top menu items ────────────────────────────────────────────────────────────
if not menu_items.empty:
    section_header("Top-Performing Menu Items", help="Left: top items by total revenue generated in the period. Right: top items by number of units sold.")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(top_items_bar(menu_items, metric="total_revenue"), use_container_width=True)
    with col2:
        st.plotly_chart(top_items_bar(menu_items, metric="quantity_sold"), use_container_width=True)
    st.divider()

# ── Daily detail table ────────────────────────────────────────────────────────
section_header("Daily Sales Detail", help="Day-by-day breakdown of guest covers, revenue, and average check size. Sorted most recent first.")
table = daily_sales[["date", "covers", "revenue", "avg_check"]].copy()
table["revenue"]   = table["revenue"].apply(lambda x: f"${x:,.0f}")
table["avg_check"] = table["avg_check"].apply(lambda x: f"${x:.2f}")
table = table.sort_values("date", ascending=False)
table.columns = ["Date", "Covers", "Revenue", "Avg. Check"]
st.dataframe(table, use_container_width=True, height=400, hide_index=True)

st.divider()
st.caption("Confidential  ·  For authorised recipients only")

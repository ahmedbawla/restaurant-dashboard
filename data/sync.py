"""
Sync script — run once daily (via GitHub Actions) to populate PostgreSQL from connectors.
Usage:
  DATABASE_URL=postgresql://... python data/sync.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from data.database import init_db, upsert_df
from data.loader import get_connector


def sync_all(days_back: int = 90) -> None:
    print("[sync] Initializing database...")
    init_db()

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    print(f"[sync] Date range: {start_date} to {end_date}")

    # ---- Toast POS ----
    print("[sync] Fetching Toast POS data...")
    toast = get_connector("toast")

    sales = toast["get_sales"](start_date, end_date)
    upsert_df(sales, "daily_sales")
    print(f"  daily_sales: {len(sales)} rows")

    hourly = toast["get_hourly_sales"](start_date, end_date)
    upsert_df(hourly, "hourly_sales")
    print(f"  hourly_sales: {len(hourly)} rows")

    item_sales = toast["get_menu_item_sales"](start_date, end_date)
    upsert_df(item_sales, "menu_items")
    print(f"  menu_items: {len(item_sales)} rows")

    # ---- Paychex Payroll ----
    print("[sync] Fetching Paychex payroll data...")
    paychex = get_connector("paychex")

    labor = paychex["get_labor"](start_date, end_date)
    upsert_df(labor, "daily_labor")
    print(f"  daily_labor: {len(labor)} rows")

    payroll = paychex["get_payroll"](start_date, end_date)
    upsert_df(payroll, "weekly_payroll")
    print(f"  weekly_payroll: {len(payroll)} rows")

    # ---- QuickBooks ----
    print("[sync] Fetching QuickBooks data...")
    qb = get_connector("quickbooks")

    expenses = qb["get_expenses"](start_date, end_date)
    upsert_df(expenses, "expenses")
    print(f"  expenses: {len(expenses)} rows")

    cash_flow = qb["get_cash_flow"](start_date, end_date)
    upsert_df(cash_flow, "cash_flow")
    print(f"  cash_flow: {len(cash_flow)} rows")

    print("[sync] Done.")


if __name__ == "__main__":
    sync_all()

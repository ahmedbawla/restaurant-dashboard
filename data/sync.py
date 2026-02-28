"""
Sync script — run once daily (via GitHub Actions) to populate PostgreSQL from connectors.
Usage:
  DATABASE_URL=postgresql://... python data/sync.py [username]
  Defaults to username "test" if not specified.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from data.database import init_db, upsert_df, get_user
from data.loader import get_connector


def sync_all(user: dict, days_back: int = 90) -> None:
    username = user["username"]
    print(f"[sync] Initializing database for user '{username}'...")
    init_db()

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    print(f"[sync] Date range: {start_date} to {end_date}")

    # ---- Toast POS ----
    print("[sync] Fetching Toast POS data...")
    toast = get_connector("toast", user)

    sales = toast["get_sales"](start_date, end_date)
    upsert_df(sales, "daily_sales", username)
    print(f"  daily_sales: {len(sales)} rows")

    hourly = toast["get_hourly_sales"](start_date, end_date)
    upsert_df(hourly, "hourly_sales", username)
    print(f"  hourly_sales: {len(hourly)} rows")

    item_sales = toast["get_menu_item_sales"](start_date, end_date)
    upsert_df(item_sales, "menu_items", username)
    print(f"  menu_items: {len(item_sales)} rows")

    # ---- Paychex Payroll ----
    print("[sync] Fetching Paychex payroll data...")
    paychex = get_connector("paychex", user)

    labor = paychex["get_labor"](start_date, end_date)
    upsert_df(labor, "daily_labor", username)
    print(f"  daily_labor: {len(labor)} rows")

    payroll = paychex["get_payroll"](start_date, end_date)
    upsert_df(payroll, "weekly_payroll", username)
    print(f"  weekly_payroll: {len(payroll)} rows")

    # ---- QuickBooks ----
    print("[sync] Fetching QuickBooks data...")
    qb = get_connector("quickbooks", user)

    expenses = qb["get_expenses"](start_date, end_date)
    upsert_df(expenses, "expenses", username)
    print(f"  expenses: {len(expenses)} rows")

    cash_flow = qb["get_cash_flow"](start_date, end_date)
    upsert_df(cash_flow, "cash_flow", username)
    print(f"  cash_flow: {len(cash_flow)} rows")

    print("[sync] Done.")


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "test"
    user = get_user(username)
    if user is None:
        print(f"[sync] Error: user '{username}' not found in database.")
        sys.exit(1)
    sync_all(user)

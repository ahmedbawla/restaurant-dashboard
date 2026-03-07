"""
Sync script — run once daily (via GitHub Actions) to populate PostgreSQL from connectors.
Usage:
  DATABASE_URL=postgresql://... python data/sync.py [username]
  Defaults to username "test" if not specified.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from data.database import init_db, upsert_df, get_user, update_user
from data.loader import get_connector


def sync_all(user: dict, days_back: int = 90) -> dict:
    """
    Sync all data sources for a user.

    Returns a results dict:
      {
        "toast":     {"rows": int, "error": str | None},
        "paychex":   {"rows": int, "error": str | None},
        "quickbooks":{"rows": int, "error": str | None},
      }
    Always records last_sync_at and last_sync_status back to the database.
    """
    username = user["username"]
    print(f"[sync] Initializing database for user '{username}'...")
    init_db()

    end_date   = date.today()
    start_date = end_date - timedelta(days=days_back)
    print(f"[sync] Date range: {start_date} to {end_date}")

    results = {}

    # ---- Toast POS ----
    print("[sync] Fetching Toast POS data...")
    try:
        toast = get_connector("toast", user)
        rows = 0
        sales = toast["get_sales"](start_date, end_date)
        upsert_df(sales, "daily_sales", username)
        rows += len(sales)

        hourly = toast["get_hourly_sales"](start_date, end_date)
        upsert_df(hourly, "hourly_sales", username)
        rows += len(hourly)

        item_sales = toast["get_menu_item_sales"](start_date, end_date)
        upsert_df(item_sales, "menu_items", username)
        rows += len(item_sales)

        results["toast"] = {"rows": rows, "error": None}
        print(f"  toast: {rows} rows total")
    except Exception as exc:
        results["toast"] = {"rows": 0, "error": str(exc)}
        print(f"  toast ERROR: {exc}")

    # ---- Paychex Payroll ----
    print("[sync] Fetching Paychex payroll data...")
    try:
        paychex = get_connector("paychex", user)
        rows = 0
        labor = paychex["get_labor"](start_date, end_date)
        upsert_df(labor, "daily_labor", username)
        rows += len(labor)

        payroll = paychex["get_payroll"](start_date, end_date)
        upsert_df(payroll, "weekly_payroll", username)
        rows += len(payroll)

        results["paychex"] = {"rows": rows, "error": None}
        print(f"  paychex: {rows} rows total")
    except Exception as exc:
        results["paychex"] = {"rows": 0, "error": str(exc)}
        print(f"  paychex ERROR: {exc}")

    # ---- QuickBooks ----
    print("[sync] Fetching QuickBooks data...")
    try:
        qb = get_connector("quickbooks", user)
        rows = 0
        expenses = qb["get_expenses"](start_date, end_date)
        upsert_df(expenses, "expenses", username)
        rows += len(expenses)

        cash_flow = qb["get_cash_flow"](start_date, end_date)
        upsert_df(cash_flow, "cash_flow", username)
        rows += len(cash_flow)

        results["quickbooks"] = {"rows": rows, "error": None}
        print(f"  quickbooks: {rows} rows total")
    except Exception as exc:
        results["quickbooks"] = {"rows": 0, "error": str(exc)}
        print(f"  quickbooks ERROR: {exc}")

    # ---- Record sync outcome ----
    errors = [f"{src}: {r['error']}" for src, r in results.items() if r["error"]]
    status = "errors: " + " | ".join(errors) if errors else "ok"
    update_user(username,
                last_sync_at=datetime.now(timezone.utc),
                last_sync_status=status)

    print(f"[sync] Done. Status: {status}")
    return results


def sync_simulated(user: dict, days_back: int = 90) -> dict:
    """
    Force-load simulated (demo) data for a user, ignoring any real credentials.
    Used by the 'Load Demo Data' button so the app owner can demonstrate the
    product to prospective clients.
    """
    from data.simulated.toast_simulated import (
        get_sales, get_hourly_sales, get_menu_item_sales,
    )
    from data.simulated.paychex_simulated import get_labor, get_payroll
    from data.simulated.quickbooks_simulated import get_expenses, get_cash_flow

    username = user["username"]
    init_db()
    end_date   = date.today()
    start_date = end_date - timedelta(days=days_back)
    results    = {}

    try:
        rows  = 0
        rows += upsert_df(get_sales(start_date, end_date),           "daily_sales",    username)
        rows += upsert_df(get_hourly_sales(start_date, end_date),    "hourly_sales",   username)
        rows += upsert_df(get_menu_item_sales(start_date, end_date), "menu_items",     username)
        results["toast"] = {"rows": rows, "error": None}
    except Exception as exc:
        results["toast"] = {"rows": 0, "error": str(exc)}

    try:
        rows  = 0
        rows += upsert_df(get_labor(start_date, end_date),   "daily_labor",    username)
        rows += upsert_df(get_payroll(start_date, end_date), "weekly_payroll", username)
        results["paychex"] = {"rows": rows, "error": None}
    except Exception as exc:
        results["paychex"] = {"rows": 0, "error": str(exc)}

    try:
        rows  = 0
        rows += upsert_df(get_expenses(start_date, end_date),  "expenses",  username)
        rows += upsert_df(get_cash_flow(start_date, end_date), "cash_flow", username)
        results["quickbooks"] = {"rows": rows, "error": None}
    except Exception as exc:
        results["quickbooks"] = {"rows": 0, "error": str(exc)}

    update_user(username,
                last_sync_at=datetime.now(timezone.utc),
                last_sync_status="demo")
    return results


def get_all_users() -> list[dict]:
    """Return all users who have real credentials (not simulated-only)."""
    from sqlalchemy import create_engine, text as _text
    from data.database import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(_text(
            "SELECT * FROM users WHERE use_simulated_data = FALSE"
        )).mappings().all()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    if "--all-users" in sys.argv:
        init_db()
        users = get_all_users()
        if not users:
            print("[sync] No users with live credentials found. Syncing demo user.")
            users = [get_user("test")]
            users = [u for u in users if u]
        for u in users:
            print(f"\n[sync] ══ Syncing user: {u['username']} ══")
            try:
                sync_all(u)
            except Exception as exc:
                print(f"[sync] ERROR for {u['username']}: {exc}")
    else:
        username = sys.argv[1] if len(sys.argv) > 1 else "test"
        user = get_user(username)
        if user is None:
            print(f"[sync] Error: user '{username}' not found in database.")
            sys.exit(1)
        sync_all(user)

"""
Simulated QuickBooks Online data generator.
Produces realistic expense and cash flow data for a restaurant.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

EXPENSE_CATEGORIES = {
    "Food & Beverage": 0.30,   # ~30% of revenue
    "Labor":           0.30,   # handled by payroll — included for QB completeness
    "Rent & Occupancy": 0.06,
    "Utilities":        0.02,
    "Supplies":         0.02,
    "Marketing":        0.01,
    "Repairs & Maint":  0.01,
    "Insurance":        0.01,
    "Other":            0.01,
}

VENDORS = {
    "Food & Beverage": [
        "Sysco Foods", "US Foods", "Local Farms Co.", "Premium Meats Inc.",
        "Ocean Fresh Seafood", "Produce Direct", "Dairy Wholesale",
    ],
    "Rent & Occupancy": ["Main St. Properties LLC"],
    "Utilities":        ["City Electric Co.", "Gas & Water Utility"],
    "Supplies":         ["Restaurant Depot", "WebstaurantStore"],
    "Marketing":        ["Social Media Agency", "Local Print Co."],
    "Repairs & Maint":  ["HVAC Solutions", "Plumbing Pros"],
    "Insurance":        ["Restaurant Guard Insurance"],
    "Other":            ["Office Supplies Inc.", "Miscellaneous"],
}


def _daily_revenue_approx(d: date, rng: np.random.Generator) -> float:
    """Rough daily revenue estimate for expense scaling."""
    base = 20000 if d.weekday() >= 4 else 17000
    return float(rng.normal(base, 1500))


def get_expenses(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns individual expense transactions line-by-line."""
    rng = np.random.default_rng(seed=55)
    rows = []
    current = start_date
    while current <= end_date:
        revenue_est = _daily_revenue_approx(current, rng)
        for category, pct in EXPENSE_CATEGORIES.items():
            if category == "Labor":
                continue  # Labor in Paychex, not QB expenses
            daily_target = revenue_est * pct
            # Not every category has daily transactions — scatter them
            if category in ("Rent & Occupancy", "Insurance"):
                if current.day != 1:
                    continue
                amount = daily_target * 30
            elif category in ("Repairs & Maint",):
                if rng.random() > 0.15:
                    continue
                amount = rng.uniform(150, 800)
            else:
                if rng.random() > 0.6:
                    continue
                amount = rng.uniform(daily_target * 0.4, daily_target * 1.6)

            vendors = VENDORS.get(category, ["Unknown Vendor"])
            vendor = vendors[rng.integers(0, len(vendors))]
            rows.append({
                "date": current.isoformat(),
                "category": category,
                "vendor": vendor,
                "amount": round(float(amount), 2),
                "description": f"{category} purchase",
            })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def get_cash_flow(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns daily inflow (revenue) and outflow (expenses) summary."""
    rng = np.random.default_rng(seed=88)
    expenses = get_expenses(start_date, end_date)
    rows = []
    current = start_date
    while current <= end_date:
        inflow = _daily_revenue_approx(current, rng)
        day_expenses = expenses[expenses["date"] == current.isoformat()]
        outflow = float(day_expenses["amount"].sum()) if not day_expenses.empty else 0.0
        # Add estimated daily labor cost separately
        labor_pct = rng.uniform(0.28, 0.33)
        outflow += inflow * labor_pct
        rows.append({
            "date": current.isoformat(),
            "inflow": round(inflow, 2),
            "outflow": round(outflow, 2),
            "net": round(inflow - outflow, 2),
        })
        current += timedelta(days=1)
    return pd.DataFrame(rows)

"""
Simulated QuickBooks Online data generator.
Produces realistic expense and cash flow data for a coffee shop.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

# Approximate % of daily revenue per expense category
EXPENSE_CATEGORIES = {
    "Coffee & Beverages":   0.18,  # beans, syrups, teas, alt milks
    "Dairy & Alternatives": 0.08,  # whole milk, oat milk, almond milk, cream
    "Food & Pastries":      0.05,  # wholesale from bakery supplier
    "Packaging & Supplies": 0.04,  # cups, lids, sleeves, bags, straws
    "Rent & Occupancy":     0.09,  # monthly lease (booked day 1 of month)
    "Utilities":            0.03,  # electricity, water, gas
    "Equipment & Maint.":   0.02,  # espresso machine service, grinder calibration
    "Marketing":            0.01,
    "Insurance":            0.01,
    "Other":                0.01,
}

VENDORS = {
    "Coffee & Beverages": [
        "Counter Culture Coffee", "Intelligentsia Coffee",
        "Local Roasters Co.", "Royal Cup Coffee", "Monin Syrups",
    ],
    "Dairy & Alternatives": [
        "Dairy Fresh Wholesale", "Oatly Direct",
        "Califia Farms B2B", "Local Dairy Farm",
    ],
    "Food & Pastries": [
        "City Bakery Co.", "Morning Glory Bakery", "ACE Bakery Wholesale",
    ],
    "Packaging & Supplies": [
        "Eco-Products", "WebstaurantStore", "Restaurant Depot",
    ],
    "Rent & Occupancy": ["Main St. Properties LLC"],
    "Utilities":        ["City Electric Co.", "Gas & Water Utility"],
    "Equipment & Maint.": ["La Marzocco Service", "Espresso Parts & Repair", "HVAC Solutions"],
    "Marketing":        ["Social Media Agency", "Local Print Co."],
    "Insurance":        ["CafeGuard Business Insurance"],
    "Other":            ["Office Supplies Inc.", "Miscellaneous"],
}


def _daily_revenue_approx(d: date, rng: np.random.Generator) -> float:
    is_weekend = d.weekday() >= 5
    base = 2600 if is_weekend else 2100
    return float(rng.normal(base, 200))


def get_expenses(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns individual expense transactions line-by-line."""
    rng = np.random.default_rng(seed=55)
    rows = []
    current = start_date
    while current <= end_date:
        revenue_est = _daily_revenue_approx(current, rng)
        for category, pct in EXPENSE_CATEGORIES.items():
            daily_target = revenue_est * pct

            if category in ("Rent & Occupancy", "Insurance"):
                # Single monthly charge on the 1st
                if current.day != 1:
                    continue
                amount = daily_target * 30
            elif category == "Equipment & Maint.":
                # Occasional — espresso machine service, grinder calibration
                if rng.random() > 0.12:
                    continue
                amount = rng.uniform(120, 600)
            elif category in ("Coffee & Beverages", "Dairy & Alternatives"):
                # Ordered multiple times per week
                if rng.random() > 0.65:
                    continue
                amount = rng.uniform(daily_target * 0.5, daily_target * 1.8)
            elif category == "Food & Pastries":
                # Bakery delivery 3-4x per week
                if rng.random() > 0.55:
                    continue
                amount = rng.uniform(daily_target * 0.5, daily_target * 1.6)
            else:
                if rng.random() > 0.5:
                    continue
                amount = rng.uniform(daily_target * 0.4, daily_target * 1.6)

            vendors = VENDORS.get(category, ["Unknown Vendor"])
            vendor  = vendors[rng.integers(0, len(vendors))]
            rows.append({
                "date":        current.isoformat(),
                "category":    category,
                "vendor":      vendor,
                "amount":      round(float(amount), 2),
                "description": f"{category} purchase",
            })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def get_cash_flow(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns daily inflow (revenue) and outflow (expenses + labor) summary."""
    rng = np.random.default_rng(seed=88)
    expenses = get_expenses(start_date, end_date)
    rows = []
    current = start_date
    while current <= end_date:
        inflow = _daily_revenue_approx(current, rng)
        day_expenses = expenses[expenses["date"] == current.isoformat()]
        cogs_outflow = float(day_expenses["amount"].sum()) if not day_expenses.empty else 0.0
        # Add estimated daily labor cost (~37% of revenue)
        labor_pct = rng.uniform(0.34, 0.40)
        outflow = cogs_outflow + inflow * labor_pct
        rows.append({
            "date":    current.isoformat(),
            "inflow":  round(inflow, 2),
            "outflow": round(outflow, 2),
            "net":     round(inflow - outflow, 2),
        })
        current += timedelta(days=1)
    return pd.DataFrame(rows)

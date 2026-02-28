"""
Simulated Toast POS data generator.
Produces realistic sales, menu item, and hourly breakdown data
for a mid-size single-location restaurant over 90 days.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

MENU_ITEMS = [
    {"name": "Wagyu Burger",        "category": "Entree",   "price": 22.00, "cost": 7.50},
    {"name": "Grilled Salmon",      "category": "Entree",   "price": 28.00, "cost": 9.80},
    {"name": "Caesar Salad",        "category": "Salad",    "price": 14.00, "cost": 3.20},
    {"name": "Ribeye Steak",        "category": "Entree",   "price": 42.00, "cost": 16.00},
    {"name": "Pasta Carbonara",     "category": "Entree",   "price": 19.00, "cost": 5.50},
    {"name": "Truffle Fries",       "category": "Sides",    "price": 9.00,  "cost": 2.10},
    {"name": "Chicken Sandwich",    "category": "Entree",   "price": 17.00, "cost": 5.20},
    {"name": "Lobster Bisque",      "category": "Soup",     "price": 12.00, "cost": 4.00},
    {"name": "Charcuterie Board",   "category": "Apps",     "price": 18.00, "cost": 6.50},
    {"name": "Craft Beer (draft)",  "category": "Beverage", "price": 8.00,  "cost": 1.80},
    {"name": "House Wine",          "category": "Beverage", "price": 10.00, "cost": 2.50},
    {"name": "Cocktail",            "category": "Beverage", "price": 13.00, "cost": 3.50},
    {"name": "Soft Drink",          "category": "Beverage", "price": 4.00,  "cost": 0.40},
    {"name": "Cheesecake",          "category": "Dessert",  "price": 10.00, "cost": 2.80},
    {"name": "Chocolate Lava Cake", "category": "Dessert",  "price": 11.00, "cost": 3.00},
    {"name": "Kids Pasta",          "category": "Kids",     "price": 9.00,  "cost": 2.00},
    {"name": "Brunch Eggs Benny",   "category": "Brunch",   "price": 16.00, "cost": 4.50},
    {"name": "Avocado Toast",       "category": "Brunch",   "price": 14.00, "cost": 3.80},
    {"name": "Soup of the Day",     "category": "Soup",     "price": 8.00,  "cost": 2.20},
    {"name": "Mixed Green Salad",   "category": "Salad",    "price": 11.00, "cost": 2.50},
]

# Item popularity weights (higher = more ordered)
ITEM_WEIGHTS = [
    0.10, 0.09, 0.08, 0.06, 0.08,
    0.09, 0.09, 0.04, 0.05, 0.07,
    0.05, 0.05, 0.06, 0.03, 0.03,
    0.02, 0.03, 0.03, 0.02, 0.02,
]

# Hourly traffic distribution (11am–10pm = hours 11–22)
HOUR_WEIGHTS = {
    11: 0.04, 12: 0.12, 13: 0.14, 14: 0.08,
    15: 0.03, 16: 0.03, 17: 0.06, 18: 0.14,
    19: 0.16, 20: 0.12, 21: 0.06, 22: 0.02,
}


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 4  # Friday, Saturday, Sunday


def _daily_covers(d: date, rng: np.random.Generator) -> int:
    base = 210 if _is_weekend(d) else 170
    noise = int(rng.normal(0, 15))
    return max(100, base + noise)


def get_sales(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns daily sales summary rows."""
    rng = np.random.default_rng(seed=42)
    rows = []
    current = start_date
    while current <= end_date:
        covers = _daily_covers(current, rng)
        avg_check = rng.uniform(68, 88) if _is_weekend(current) else rng.uniform(58, 78)
        revenue = round(covers * avg_check, 2)
        food_cost_pct = rng.uniform(0.28, 0.34)
        rows.append({
            "date": current.isoformat(),
            "covers": covers,
            "revenue": revenue,
            "avg_check": round(avg_check, 2),
            "food_cost": round(revenue * food_cost_pct, 2),
            "food_cost_pct": round(food_cost_pct * 100, 2),
        })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def get_hourly_sales(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns hourly sales breakdown per day."""
    rng = np.random.default_rng(seed=7)
    rows = []
    current = start_date
    while current <= end_date:
        covers = _daily_covers(current, rng)
        avg_check = rng.uniform(68, 88) if _is_weekend(current) else rng.uniform(58, 78)
        hours = list(HOUR_WEIGHTS.keys())
        weights = list(HOUR_WEIGHTS.values())
        cover_split = rng.multinomial(covers, weights)
        for hour, c in zip(hours, cover_split):
            rows.append({
                "date": current.isoformat(),
                "hour": hour,
                "covers": int(c),
                "revenue": round(c * avg_check * rng.uniform(0.9, 1.1), 2),
            })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def get_menu_items() -> pd.DataFrame:
    """Returns static menu item catalogue with cost data."""
    return pd.DataFrame(MENU_ITEMS)


def get_menu_item_sales(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns per-item sales quantities and revenue aggregated over date range."""
    rng = np.random.default_rng(seed=99)
    days = (end_date - start_date).days + 1
    items = get_menu_items()
    rows = []
    for idx, item in items.iterrows():
        # Expected daily orders based on weight
        weight = ITEM_WEIGHTS[idx]
        avg_daily_orders = 170 * weight * 1.5  # ~170 avg covers, 1.5 items/cover
        total_qty = int(rng.normal(avg_daily_orders * days, avg_daily_orders * days * 0.1))
        total_qty = max(0, total_qty)
        total_revenue = round(total_qty * item["price"], 2)
        total_cost = round(total_qty * item["cost"], 2)
        rows.append({
            "name": item["name"],
            "category": item["category"],
            "price": item["price"],
            "cost": item["cost"],
            "quantity_sold": total_qty,
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "gross_profit": round(total_revenue - total_cost, 2),
            "margin_pct": round((item["price"] - item["cost"]) / item["price"] * 100, 1),
        })
    return pd.DataFrame(rows).sort_values("total_revenue", ascending=False).reset_index(drop=True)

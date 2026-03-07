"""
Simulated Toast POS data generator.
Produces realistic sales, menu item, and hourly breakdown data
for a single-location coffee shop over 90 days.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

MENU_ITEMS = [
    # Hot espresso drinks
    {"name": "Latte",                  "category": "Hot Drinks",  "price": 5.50, "cost": 1.40},
    {"name": "Cappuccino",             "category": "Hot Drinks",  "price": 5.00, "cost": 1.20},
    {"name": "Flat White",             "category": "Hot Drinks",  "price": 5.00, "cost": 1.20},
    {"name": "Americano",              "category": "Hot Drinks",  "price": 4.00, "cost": 0.85},
    {"name": "Espresso",               "category": "Hot Drinks",  "price": 3.50, "cost": 0.75},
    {"name": "Drip Coffee",            "category": "Hot Drinks",  "price": 3.00, "cost": 0.55},
    {"name": "Chai Latte",             "category": "Hot Drinks",  "price": 5.50, "cost": 1.60},
    {"name": "Matcha Latte",           "category": "Hot Drinks",  "price": 6.00, "cost": 1.90},
    # Cold & iced drinks
    {"name": "Iced Latte",             "category": "Cold Drinks", "price": 6.00, "cost": 1.50},
    {"name": "Cold Brew",              "category": "Cold Drinks", "price": 5.00, "cost": 1.10},
    {"name": "Iced Americano",         "category": "Cold Drinks", "price": 4.50, "cost": 0.90},
    {"name": "Blended Frappuccino",    "category": "Cold Drinks", "price": 6.50, "cost": 1.85},
    {"name": "Iced Matcha",            "category": "Cold Drinks", "price": 6.50, "cost": 2.00},
    {"name": "Oat Milk Latte",         "category": "Cold Drinks", "price": 6.50, "cost": 1.80},
    # Pastries
    {"name": "Butter Croissant",       "category": "Pastries",   "price": 4.00, "cost": 1.40},
    {"name": "Blueberry Muffin",       "category": "Pastries",   "price": 3.75, "cost": 1.20},
    {"name": "Banana Bread",           "category": "Pastries",   "price": 3.50, "cost": 1.00},
    {"name": "Chocolate Chip Cookie",  "category": "Pastries",   "price": 2.75, "cost": 0.70},
    # Food
    {"name": "Breakfast Sandwich",     "category": "Food",        "price": 8.50, "cost": 2.80},
    {"name": "Avocado Toast",          "category": "Food",        "price": 9.00, "cost": 3.00},
]

# Item popularity weights (proportional — higher = more sold)
ITEM_WEIGHTS = [
    0.12, 0.08, 0.05, 0.08, 0.04,   # hot: latte, cap, flat, ameri, esp
    0.07, 0.04, 0.03,                # hot: drip, chai, matcha
    0.10, 0.08, 0.05, 0.04, 0.03, 0.06,  # cold: iced latte, cold brew, etc.
    0.05, 0.04, 0.03, 0.04,          # pastries
    0.04, 0.03,                      # food
]

# Coffee shop hourly traffic — strong morning peak, lunch bump, quiet afternoon
HOUR_WEIGHTS = {
    6: 0.05, 7: 0.14, 8: 0.20, 9: 0.17,
    10: 0.11, 11: 0.08, 12: 0.10, 13: 0.07,
    14: 0.05, 15: 0.02, 16: 0.01,
}


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # Saturday, Sunday


def _daily_covers(d: date, rng: np.random.Generator) -> int:
    # Weekdays: commuter-driven morning rush; weekends: leisurely brunch crowd
    base = 240 if _is_weekend(d) else 210
    noise = int(rng.normal(0, 18))
    return max(80, base + noise)


def get_sales(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns daily sales summary rows."""
    rng = np.random.default_rng(seed=42)
    rows = []
    current = start_date
    while current <= end_date:
        covers = _daily_covers(current, rng)
        # Weekend = slightly higher avg check (people buy food + drinks)
        avg_check = rng.uniform(10.50, 13.00) if _is_weekend(current) else rng.uniform(8.50, 11.00)
        revenue = round(covers * avg_check, 2)
        food_cost_pct = rng.uniform(0.26, 0.31)  # coffee margins are good
        rows.append({
            "date":          current.isoformat(),
            "covers":        covers,
            "revenue":       revenue,
            "avg_check":     round(avg_check, 2),
            "food_cost":     round(revenue * food_cost_pct, 2),
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
        avg_check = rng.uniform(10.50, 13.00) if _is_weekend(current) else rng.uniform(8.50, 11.00)
        hours = list(HOUR_WEIGHTS.keys())
        weights = list(HOUR_WEIGHTS.values())
        cover_split = rng.multinomial(covers, weights)
        for hour, c in zip(hours, cover_split):
            rows.append({
                "date":    current.isoformat(),
                "hour":    hour,
                "covers":  int(c),
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
        weight = ITEM_WEIGHTS[idx]
        # ~210 avg daily transactions, ~1.3 items per transaction
        avg_daily_orders = 210 * weight * 1.3
        total_qty = int(rng.normal(avg_daily_orders * days, avg_daily_orders * days * 0.1))
        total_qty = max(0, total_qty)
        total_revenue = round(total_qty * item["price"], 2)
        total_cost    = round(total_qty * item["cost"],  2)
        rows.append({
            "name":          item["name"],
            "category":      item["category"],
            "price":         item["price"],
            "cost":          item["cost"],
            "quantity_sold": total_qty,
            "total_revenue": total_revenue,
            "total_cost":    total_cost,
            "gross_profit":  round(total_revenue - total_cost, 2),
            "margin_pct":    round((item["price"] - item["cost"]) / item["price"] * 100, 1),
        })
    return pd.DataFrame(rows).sort_values("total_revenue", ascending=False).reset_index(drop=True)

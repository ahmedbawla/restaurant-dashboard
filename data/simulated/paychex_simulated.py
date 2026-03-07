"""
Simulated Paychex payroll data generator.
Produces realistic labor data for a coffee shop with ~8 staff
across Bar, Counter, and Management departments.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

EMPLOYEES = [
    # Bar — espresso bar (baristas & shift leads)
    {"id": "E001", "name": "Sofia Reyes",      "dept": "Bar",        "role": "Shift Lead",   "hourly_rate": 19.00, "type": "hourly"},
    {"id": "E002", "name": "Marcus Webb",       "dept": "Bar",        "role": "Shift Lead",   "hourly_rate": 18.50, "type": "hourly"},
    {"id": "E003", "name": "Priya Kapoor",      "dept": "Bar",        "role": "Barista",      "hourly_rate": 15.00, "type": "hourly"},
    {"id": "E004", "name": "James Okafor",      "dept": "Bar",        "role": "Barista",      "hourly_rate": 14.50, "type": "hourly"},
    {"id": "E005", "name": "Aiden Cruz",        "dept": "Bar",        "role": "Barista",      "hourly_rate": 14.50, "type": "hourly"},
    {"id": "E006", "name": "Lily Chen",         "dept": "Bar",        "role": "Barista (PT)", "hourly_rate": 13.75, "type": "hourly"},
    # Counter — register & customer service
    {"id": "E007", "name": "Noah Williams",     "dept": "Counter",    "role": "Counter Staff","hourly_rate": 14.00, "type": "hourly"},
    {"id": "E008", "name": "Zara Ahmed",        "dept": "Counter",    "role": "Counter Staff","hourly_rate": 14.00, "type": "hourly"},
    # Management
    {"id": "E009", "name": "Rachel Torres",     "dept": "Management", "role": "Store Manager","hourly_rate": 52000 / 52 / 40, "type": "salary"},
    {"id": "E010", "name": "Daniel Park",       "dept": "Management", "role": "Asst. Manager","hourly_rate": 40000 / 52 / 40, "type": "salary"},
]


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def get_labor(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns daily labor cost summary by department."""
    rng = np.random.default_rng(seed=13)
    rows = []
    current = start_date
    while current <= end_date:
        is_weekend = current.weekday() >= 5
        for dept in ["Bar", "Counter", "Management"]:
            dept_emps = [e for e in EMPLOYEES if e["dept"] == dept]
            if dept == "Management":
                hours = sum(8.0 for _ in dept_emps)
                cost  = sum(e["hourly_rate"] * 8 for e in dept_emps)
            elif dept == "Bar":
                # Shift leads work longer; baristas vary by demand
                hours = 0.0
                cost  = 0.0
                for e in dept_emps:
                    if e["role"] == "Shift Lead":
                        base = 8.5 if is_weekend else 8.0
                    elif "PT" in e["role"]:
                        base = 5.0 if is_weekend else 4.5
                    else:
                        base = 7.0 if is_weekend else 6.5
                    h = max(0, float(rng.normal(base, 0.5)))
                    hours += h
                    cost  += h * e["hourly_rate"]
            else:  # Counter
                base = 7.0 if is_weekend else 6.5
                hours = sum(max(0, float(rng.normal(base, 0.5))) for _ in dept_emps)
                cost  = sum(
                    max(0, float(rng.normal(base, 0.5))) * e["hourly_rate"]
                    for e in dept_emps
                )
            rows.append({
                "date":       current.isoformat(),
                "dept":       dept,
                "hours":      round(hours, 2),
                "labor_cost": round(cost, 2),
            })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def get_payroll(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns weekly payroll per employee within date range."""
    rng = np.random.default_rng(seed=17)
    rows = []
    week = _week_start(start_date)
    while week <= end_date:
        week_end = week + timedelta(days=6)
        for emp in EMPLOYEES:
            if emp["type"] == "salary":
                regular_hours  = 40.0
                overtime_hours = 0.0
                gross_pay      = emp["hourly_rate"] * 40
            else:
                if emp["role"] == "Shift Lead":
                    regular_hours = float(min(40, max(30, rng.normal(38, 2))))
                elif "PT" in emp["role"]:
                    regular_hours = float(min(25, max(10, rng.normal(20, 3))))
                else:
                    regular_hours = float(min(40, max(25, rng.normal(34, 3))))
                overtime_hours = float(max(0, rng.normal(-1, 2)))
                gross_pay = (
                    regular_hours * emp["hourly_rate"] +
                    overtime_hours * emp["hourly_rate"] * 1.5
                )
            rows.append({
                "week_start":      week.isoformat(),
                "week_end":        week_end.isoformat(),
                "employee_id":     emp["id"],
                "employee_name":   emp["name"],
                "dept":            emp["dept"],
                "role":            emp["role"],
                "hourly_rate":     round(emp["hourly_rate"], 2),
                "employment_type": emp["type"],
                "regular_hours":   round(regular_hours, 2),
                "overtime_hours":  round(overtime_hours, 2),
                "total_hours":     round(regular_hours + overtime_hours, 2),
                "gross_pay":       round(gross_pay, 2),
            })
        week += timedelta(weeks=1)
    return pd.DataFrame(rows)


def get_employees() -> pd.DataFrame:
    return pd.DataFrame(EMPLOYEES)

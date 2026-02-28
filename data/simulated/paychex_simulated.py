"""
Simulated Paychex payroll data generator.
Produces realistic labor data for ~25 employees across FOH, BOH, Management, Bar.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

EMPLOYEES = [
    # FOH (Front of House)
    {"id": "E001", "name": "Maria Santos",    "dept": "FOH", "role": "Server",     "hourly_rate": 4.00,  "type": "hourly"},
    {"id": "E002", "name": "James Cooper",    "dept": "FOH", "role": "Server",     "hourly_rate": 4.00,  "type": "hourly"},
    {"id": "E003", "name": "Priya Nair",      "dept": "FOH", "role": "Server",     "hourly_rate": 4.00,  "type": "hourly"},
    {"id": "E004", "name": "Liam O'Brien",    "dept": "FOH", "role": "Server",     "hourly_rate": 4.00,  "type": "hourly"},
    {"id": "E005", "name": "Ava Thompson",    "dept": "FOH", "role": "Host",       "hourly_rate": 14.00, "type": "hourly"},
    {"id": "E006", "name": "Noah Williams",   "dept": "FOH", "role": "Busser",     "hourly_rate": 13.00, "type": "hourly"},
    {"id": "E007", "name": "Sophia Martinez", "dept": "FOH", "role": "Busser",     "hourly_rate": 13.00, "type": "hourly"},
    {"id": "E008", "name": "Ethan Brown",     "dept": "FOH", "role": "Food Runner", "hourly_rate": 13.50, "type": "hourly"},
    # BOH (Back of House)
    {"id": "E009", "name": "Carlos Vega",     "dept": "BOH", "role": "Sous Chef",  "hourly_rate": 24.00, "type": "hourly"},
    {"id": "E010", "name": "Aisha Patel",     "dept": "BOH", "role": "Line Cook",  "hourly_rate": 18.00, "type": "hourly"},
    {"id": "E011", "name": "Derek Stone",     "dept": "BOH", "role": "Line Cook",  "hourly_rate": 18.00, "type": "hourly"},
    {"id": "E012", "name": "Fatima Hassan",   "dept": "BOH", "role": "Line Cook",  "hourly_rate": 17.50, "type": "hourly"},
    {"id": "E013", "name": "Ryan Nguyen",     "dept": "BOH", "role": "Line Cook",  "hourly_rate": 17.00, "type": "hourly"},
    {"id": "E014", "name": "Jasmine Lee",     "dept": "BOH", "role": "Prep Cook",  "hourly_rate": 15.00, "type": "hourly"},
    {"id": "E015", "name": "Marcus Davis",    "dept": "BOH", "role": "Prep Cook",  "hourly_rate": 15.00, "type": "hourly"},
    {"id": "E016", "name": "Elena Rivera",    "dept": "BOH", "role": "Prep Cook",  "hourly_rate": 14.50, "type": "hourly"},
    {"id": "E017", "name": "Tony Walsh",      "dept": "BOH", "role": "Dishwasher", "hourly_rate": 13.00, "type": "hourly"},
    {"id": "E018", "name": "Sara Kim",        "dept": "BOH", "role": "Dishwasher", "hourly_rate": 13.00, "type": "hourly"},
    {"id": "E019", "name": "Ben Okafor",      "dept": "BOH", "role": "Dishwasher", "hourly_rate": 13.00, "type": "hourly"},
    {"id": "E020", "name": "Hana Sato",       "dept": "BOH", "role": "Pastry Cook", "hourly_rate": 19.00, "type": "hourly"},
    # Management
    {"id": "E021", "name": "Victor Reyes",    "dept": "Management", "role": "Executive Chef", "hourly_rate": 80769.23 / 52 / 40, "type": "salary"},
    {"id": "E022", "name": "Linda Park",      "dept": "Management", "role": "GM",             "hourly_rate": 72000.00 / 52 / 40, "type": "salary"},
    {"id": "E023", "name": "Tom Garrett",     "dept": "Management", "role": "Asst. GM",       "hourly_rate": 58000.00 / 52 / 40, "type": "salary"},
    # Bar
    {"id": "E024", "name": "Kayla Reed",      "dept": "Bar", "role": "Bartender",  "hourly_rate": 4.00, "type": "hourly"},
    {"id": "E025", "name": "Sam Torres",      "dept": "Bar", "role": "Bartender",  "hourly_rate": 4.00, "type": "hourly"},
]


def _week_start(d: date) -> date:
    """Return Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def get_labor(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns daily labor cost summary by department."""
    rng = np.random.default_rng(seed=13)
    rows = []
    current = start_date
    while current <= end_date:
        is_weekend = current.weekday() >= 4
        for dept in ["FOH", "BOH", "Management", "Bar"]:
            dept_emps = [e for e in EMPLOYEES if e["dept"] == dept]
            if dept == "Management":
                # Salaried — constant daily cost
                hours = sum(8.0 for _ in dept_emps)
                cost = sum(e["hourly_rate"] * 8 for e in dept_emps)
            else:
                # Hourly — fluctuates by demand
                base_hours_per_emp = 7.5 if is_weekend else 6.5
                hours = sum(
                    max(0, rng.normal(base_hours_per_emp, 1.0))
                    for _ in dept_emps
                )
                cost = sum(
                    max(0, rng.normal(base_hours_per_emp, 1.0)) * e["hourly_rate"]
                    for e in dept_emps
                )
            rows.append({
                "date": current.isoformat(),
                "dept": dept,
                "hours": round(hours, 2),
                "labor_cost": round(cost, 2),
            })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def get_payroll(start_date: date, end_date: date) -> pd.DataFrame:
    """Returns weekly payroll per employee within date range."""
    rng = np.random.default_rng(seed=17)
    rows = []
    # Iterate by week
    week = _week_start(start_date)
    while week <= end_date:
        week_end = week + timedelta(days=6)
        for emp in EMPLOYEES:
            if emp["type"] == "salary":
                regular_hours = 40.0
                overtime_hours = 0.0
                regular_pay = emp["hourly_rate"] * 40
            else:
                regular_hours = float(min(40, max(20, rng.normal(35, 5))))
                overtime_hours = float(max(0, rng.normal(-2, 3)))  # occasionally OT
                regular_pay = regular_hours * emp["hourly_rate"]
                overtime_pay = overtime_hours * emp["hourly_rate"] * 1.5
                regular_pay += overtime_pay
            rows.append({
                "week_start": week.isoformat(),
                "week_end": week_end.isoformat(),
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "dept": emp["dept"],
                "role": emp["role"],
                "hourly_rate": round(emp["hourly_rate"], 2),
                "employment_type": emp["type"],
                "regular_hours": round(regular_hours, 2),
                "overtime_hours": round(overtime_hours, 2),
                "total_hours": round(regular_hours + overtime_hours, 2),
                "gross_pay": round(regular_pay, 2),
            })
        week += timedelta(weeks=1)
    return pd.DataFrame(rows)


def get_employees() -> pd.DataFrame:
    return pd.DataFrame(EMPLOYEES)

"""
Toast POS and Paychex CSV import helpers.

Accepts raw bytes from st.file_uploader (CSV or Excel) and returns
clean DataFrames matching the DB schema.  Column names are normalised
from all known export variants so uploads work regardless of
which version or report template the user has.
"""

import io
import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_raw(raw: bytes, filename: str = "") -> pd.DataFrame:
    """Parse CSV or Excel bytes into a raw DataFrame."""
    try:
        if filename.endswith(".xlsx") or raw[:4] == b"PK\x03\x04":
            return pd.read_excel(io.BytesIO(raw))
        # Try UTF-8 first, fall back to latin-1 for older Toast exports
        try:
            return pd.read_csv(io.BytesIO(raw), encoding="utf-8")
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(raw), encoding="latin-1")
    except Exception as exc:
        raise ValueError(f"Could not read file: {exc}")


def _clean_currency(series: pd.Series) -> pd.Series:
    """Strip $, commas, % and convert to float."""
    return (
        series.astype(str)
        .str.replace(r"[\$,]", "", regex=True)
        .str.replace(r"%", "", regex=True)
        .str.strip()
        .replace("", "0")
        .replace("nan", "0")
        .astype(float)
    )


def _normalise(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """Rename columns using the first matching alias found."""
    rename = {}
    for target, aliases in col_map.items():
        for alias in aliases:
            if alias in df.columns:
                rename[alias] = target
                break
    return df.rename(columns=rename)


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------

def parse_sales_summary(raw: bytes, filename: str = "") -> pd.DataFrame:
    """
    Parse a Toast Sales Summary export.

    Returns DataFrame with columns:
        date, covers, revenue, avg_check, food_cost, food_cost_pct
    """
    df = _read_raw(raw, filename)

    # Drop completely empty rows / summary footer rows
    df = df.dropna(how="all")

    col_map = {
        "date":          ["yyyyMMdd", "Date", "Business Date", "date", "business_date"],
        "covers":        ["Total guests", "Covers", "Guests", "Guest Count",
                          "covers", "guests", "total_guests"],
        "revenue":       ["Net sales", "Net Sales", "Gross Sales", "Total Net Sales",
                          "Net Revenue", "revenue", "net_sales"],
        "avg_check":     ["Average Check", "Avg Check", "Check Average",
                          "avg_check", "average_check"],
        "food_cost":     ["Food Cost", "Cost of Goods", "COGS", "food_cost"],
        "food_cost_pct": ["Food Cost %", "Food Cost Pct", "COGS %",
                          "food_cost_pct", "food_cost_%"],
    }
    df = _normalise(df, col_map)

    needed = ["date", "covers", "revenue", "avg_check", "food_cost", "food_cost_pct"]
    for col in needed:
        if col not in df.columns:
            df[col] = 0

    df = df[needed].copy()

    # Parse date — handles YYYYMMDD (Toast default), MM/DD/YYYY, ISO, etc.
    def _parse_date(val):
        s = str(val).strip()
        # Toast yyyyMMdd integer format
        if s.isdigit() and len(s) == 8:
            return pd.to_datetime(s, format="%Y%m%d", errors="coerce")
        return pd.to_datetime(s, infer_datetime_format=True, errors="coerce")

    df["date"]          = df["date"].apply(_parse_date).dt.strftime("%Y-%m-%d")
    df["covers"]        = _clean_currency(df["covers"]).astype(int)
    df["revenue"]       = _clean_currency(df["revenue"])
    df["avg_check"]     = _clean_currency(df["avg_check"])
    df["food_cost"]     = _clean_currency(df["food_cost"])
    df["food_cost_pct"] = _clean_currency(df["food_cost_pct"])

    # Drop rows where date couldn't be parsed (totals rows, blank rows, etc.)
    df = df[df["date"].notna() & (df["date"] != "NaT")]

    # If food_cost_pct looks like a fraction (e.g. 0.253) convert to percentage
    if df["food_cost_pct"].max() <= 1.0 and df["food_cost_pct"].max() > 0:
        df["food_cost_pct"] = df["food_cost_pct"] * 100

    # Derive avg_check from revenue/covers if missing
    mask = (df["avg_check"] == 0) & (df["covers"] > 0)
    df.loc[mask, "avg_check"] = df.loc[mask, "revenue"] / df.loc[mask, "covers"]

    return df.reset_index(drop=True)


def parse_item_selections(raw: bytes, filename: str = "") -> pd.DataFrame:
    """
    Parse a Toast Item Selections export.

    Returns DataFrame with columns:
        name, category, price, quantity_sold, total_revenue,
        total_cost, gross_profit, margin_pct
    """
    df = _read_raw(raw, filename)
    df = df.dropna(how="all")

    col_map = {
        "name":          ["Item, open item", "Menu Item", "Item Name", "Item",
                          "name", "menu_item"],
        "category":      ["Menu group", "Menu Group", "Category", "Menu Category",
                          "Subgroup", "category", "menu_group"],
        "price":         ["Avg. price", "Price", "Menu Item Price", "Unit Price",
                          "price", "avg_price"],
        "quantity_sold": ["Qty sold", "Quantity", "Qty", "Qty Sold", "Count",
                          "quantity_sold", "qty_sold"],
        "total_revenue": ["Net sales", "Net Sales", "Gross Sales", "Total Sales",
                          "total_revenue", "net_sales"],
        "total_cost":    ["Item COGS", "Total Cost", "Food Cost", "COGS", "total_cost"],
        "gross_profit":  ["Gross profit", "Gross Profit", "gross_profit"],
        "margin_pct":    ["Gross margin (%)", "Gross Margin %", "Margin %", "margin_pct"],
    }
    df = _normalise(df, col_map)

    # For All levels.csv: keep only item-level rows (name is populated, qty > 0)
    if "name" in df.columns:
        df = df[df["name"].astype(str).str.strip().str.len() > 0]
        df = df[df["name"].astype(str).str.strip() != "nan"]

    for col in ["name", "category", "price", "quantity_sold", "total_revenue",
                "total_cost", "gross_profit", "margin_pct"]:
        if col not in df.columns:
            df[col] = 0 if col not in ("name", "category") else "Unknown"

    df["name"]          = df["name"].astype(str).str.strip()
    df["category"]      = df["category"].astype(str).str.strip().replace("nan", "Uncategorised")
    df["price"]         = _clean_currency(df["price"])
    df["quantity_sold"] = _clean_currency(df["quantity_sold"]).astype(int)
    df["total_revenue"] = _clean_currency(df["total_revenue"])
    df["total_cost"]    = _clean_currency(df["total_cost"])
    df["gross_profit"]  = _clean_currency(df["gross_profit"])
    df["margin_pct"]    = _clean_currency(df["margin_pct"])

    # Derive gross_profit / margin if not supplied
    mask = df["gross_profit"] == 0
    df.loc[mask, "gross_profit"] = df.loc[mask, "total_revenue"] - df.loc[mask, "total_cost"]
    mask2 = (df["margin_pct"] == 0) & (df["total_revenue"] > 0)
    df.loc[mask2, "margin_pct"] = (
        df.loc[mask2, "gross_profit"] / df.loc[mask2, "total_revenue"] * 100
    ).round(2)

    # Aggregate: one row per item name (sum quantities/revenue across all categories/sizes)
    # Category = the one with highest revenue for that item
    cat_df = (
        df.groupby(["name", "category"], as_index=False)["total_revenue"].sum()
    )
    cat_df = cat_df.sort_values("total_revenue", ascending=False).drop_duplicates("name")[["name", "category"]]

    agg_df = (
        df.groupby("name", as_index=False)
        .agg(
            price=("price", "mean"),
            quantity_sold=("quantity_sold", "sum"),
            total_revenue=("total_revenue", "sum"),
            total_cost=("total_cost", "sum"),
            gross_profit=("gross_profit", "sum"),
        )
    )
    df = agg_df.merge(cat_df, on="name", how="left")
    df["category"] = df["category"].fillna("Uncategorised")

    df["margin_pct"] = (
        df["gross_profit"] / df["total_revenue"] * 100
    ).where(df["total_revenue"] > 0, 0).round(2)

    # Drop header/total rows (qty = 0)
    df = df[df["quantity_sold"] > 0]

    return df[["name", "category", "price", "quantity_sold",
               "total_revenue", "total_cost", "gross_profit", "margin_pct"]].reset_index(drop=True)


def parse_hourly_sales(raw: bytes, filename: str = "") -> pd.DataFrame:
    """
    Parse a Toast Sales by Hour export.

    Returns DataFrame with columns:
        date, hour, covers, revenue
    """
    df = _read_raw(raw, filename)
    df = df.dropna(how="all")

    col_map = {
        "date":    ["Date", "Business Date", "date", "business_date"],
        "hour":    ["Hour", "Time", "Hour of Day", "Hour of day",
                    "hour", "time", "hour_of_day"],
        "covers":  ["Total guests", "Covers", "Guests", "covers", "guests"],
        "revenue": ["Net sales", "Net Sales", "Gross Sales", "revenue", "net_sales"],
    }
    df = _normalise(df, col_map)

    for col in ["date", "hour", "covers", "revenue"]:
        if col not in df.columns:
            df[col] = 0

    df["date"]    = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["covers"]  = _clean_currency(df["covers"]).astype(int)
    df["revenue"] = _clean_currency(df["revenue"])

    # Normalise hour: "2:00 PM" → 14, "14" → 14
    def _parse_hour(val):
        try:
            v = str(val).strip()
            if ":" in v:
                return pd.to_datetime(v, format="%I:%M %p", errors="coerce").hour
            return int(float(v))
        except Exception:
            return 0

    df["hour"] = df["hour"].apply(_parse_hour)
    df = df[df["date"].notna() & (df["date"] != "NaT")]

    return df[["date", "hour", "covers", "revenue"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Paychex parsers
# ---------------------------------------------------------------------------

def parse_time_attendance(raw: bytes, filename: str = "") -> pd.DataFrame:
    """
    Parse a Paychex Time & Attendance export.

    Returns DataFrame with columns:
        date, dept, hours, labor_cost
    """
    df = _read_raw(raw, filename)
    df = df.dropna(how="all")

    col_map = {
        "date":       ["Date", "Work Date", "Business Date", "Pay Date",
                       "date", "work_date", "business_date"],
        "dept":       ["Department", "Dept", "Job", "Job Title", "Cost Center",
                       "department", "dept", "job"],
        "hours":      ["Hours", "Total Hours", "Regular Hours", "Reg Hours",
                       "Hrs Worked", "hours", "total_hours", "reg_hours"],
        "labor_cost": ["Labor Cost", "Total Cost", "Gross Pay", "Amount",
                       "Wages", "Total Wages", "labor_cost", "gross_pay"],
    }
    df = _normalise(df, col_map)

    for col in ["date", "dept", "hours", "labor_cost"]:
        if col not in df.columns:
            df[col] = 0 if col in ("hours", "labor_cost") else "General"

    df["date"]       = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["dept"]       = df["dept"].astype(str).str.strip().replace("nan", "General")
    df["hours"]      = _clean_currency(df["hours"])
    df["labor_cost"] = _clean_currency(df["labor_cost"])

    df = df[df["date"].notna() & (df["date"] != "NaT")]
    df = df[df["hours"] > 0]

    # Aggregate to one row per date+dept
    df = df.groupby(["date", "dept"], as_index=False).agg(
        hours=("hours", "sum"),
        labor_cost=("labor_cost", "sum"),
    )

    return df[["date", "dept", "hours", "labor_cost"]].reset_index(drop=True)


def parse_payroll_register(raw: bytes, filename: str = "") -> pd.DataFrame:
    """
    Parse a Paychex Payroll Register export.

    Returns DataFrame with columns:
        week_start, week_end, employee_id, employee_name, dept, role,
        employment_type, hourly_rate, regular_hours, overtime_hours,
        total_hours, gross_pay
    """
    df = _read_raw(raw, filename)
    df = df.dropna(how="all")

    col_map = {
        "employee_name":   ["Employee Name", "Employee", "Name", "Full Name",
                            "employee_name", "employee"],
        "employee_id":     ["Employee ID", "EE ID", "ID", "Emp ID", "Badge",
                            "employee_id", "ee_id"],
        "dept":            ["Department", "Dept", "Job", "Cost Center",
                            "department", "dept"],
        "role":            ["Title", "Position", "Job Title", "Role",
                            "title", "role", "job_title"],
        "employment_type": ["Pay Type", "Employment Type", "EE Type", "Type",
                            "employment_type", "pay_type"],
        "hourly_rate":     ["Hourly Rate", "Rate", "Pay Rate", "Base Rate",
                            "hourly_rate", "rate"],
        "regular_hours":   ["Regular Hours", "Reg Hours", "Reg Hrs",
                            "regular_hours", "reg_hours"],
        "overtime_hours":  ["Overtime Hours", "OT Hours", "OT Hrs",
                            "overtime_hours", "ot_hours"],
        "total_hours":     ["Total Hours", "Gross Hours", "Hrs Worked",
                            "total_hours"],
        "gross_pay":       ["Gross Pay", "Total Pay", "Gross Wages", "Gross Earnings",
                            "gross_pay", "total_pay"],
        "week_start":      ["Period Begin", "Period Start", "Week Begin",
                            "Check Date", "Pay Date", "Pay Period Begin",
                            "week_start", "period_begin"],
        "week_end":        ["Period End", "Period Stop", "Week End",
                            "Pay Period End", "week_end", "period_end"],
    }
    df = _normalise(df, col_map)

    defaults = {
        "employee_id":    "UNKNOWN",
        "employee_name":  "Unknown",
        "dept":           "General",
        "role":           "Employee",
        "employment_type":"Hourly",
        "hourly_rate":    0.0,
        "regular_hours":  0.0,
        "overtime_hours": 0.0,
        "total_hours":    0.0,
        "gross_pay":      0.0,
        "week_start":     "",
        "week_end":       "",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    # Parse dates
    df["week_start"] = pd.to_datetime(df["week_start"], errors="coerce").dt.strftime("%Y-%m-%d")
    if (df["week_end"] == "").all() or df["week_end"].isna().all():
        df["week_end"] = (
            pd.to_datetime(df["week_start"], errors="coerce") + pd.Timedelta(days=6)
        ).dt.strftime("%Y-%m-%d")
    else:
        df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce").dt.strftime("%Y-%m-%d")

    df["employee_id"]    = df["employee_id"].astype(str).str.strip()
    df["employee_name"]  = df["employee_name"].astype(str).str.strip()
    df["dept"]           = df["dept"].astype(str).str.strip().replace("nan", "General")
    df["role"]           = df["role"].astype(str).str.strip().replace("nan", "Employee")
    df["employment_type"]= df["employment_type"].astype(str).str.strip().replace("nan", "Hourly")
    df["hourly_rate"]    = _clean_currency(df["hourly_rate"])
    df["regular_hours"]  = _clean_currency(df["regular_hours"])
    df["overtime_hours"] = _clean_currency(df["overtime_hours"])
    df["total_hours"]    = _clean_currency(df["total_hours"])
    df["gross_pay"]      = _clean_currency(df["gross_pay"])

    # Derive total_hours if missing
    mask = df["total_hours"] == 0
    df.loc[mask, "total_hours"] = df.loc[mask, "regular_hours"] + df.loc[mask, "overtime_hours"]

    # Drop rows with no employee name or no pay
    df = df[df["employee_name"].str.len() > 0]
    df = df[df["employee_name"] != "Unknown"]
    df = df[df["week_start"].notna() & (df["week_start"] != "NaT")]

    cols = ["week_start", "week_end", "employee_id", "employee_name", "dept", "role",
            "employment_type", "hourly_rate", "regular_hours", "overtime_hours",
            "total_hours", "gross_pay"]
    return df[cols].reset_index(drop=True)

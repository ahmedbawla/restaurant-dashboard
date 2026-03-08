"""
Toast POS CSV import helpers.

Accepts raw bytes from st.file_uploader (CSV or Excel) and returns
clean DataFrames matching the DB schema.  Column names are normalised
from all known Toast export variants so uploads work regardless of
which Toast version or report template the user has.
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

    # Aggregate: one row per item name (sum quantities/revenue across sizes/modifiers)
    df = (
        df.groupby(["name", "category"], as_index=False)
        .agg(
            price=("price", "mean"),
            quantity_sold=("quantity_sold", "sum"),
            total_revenue=("total_revenue", "sum"),
            total_cost=("total_cost", "sum"),
            gross_profit=("gross_profit", "sum"),
        )
    )
    df["margin_pct"] = (
        df["gross_profit"] / df["total_revenue"] * 100
    ).where(df["total_revenue"] > 0, 0).round(2)

    # Drop header/total rows (qty = 0 and no real name)
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

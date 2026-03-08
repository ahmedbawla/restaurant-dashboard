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
        "date":          ["Date", "Business Date", "date", "business_date"],
        "covers":        ["Covers", "Guests", "Guest Count", "covers", "guests"],
        "revenue":       ["Net Sales", "Gross Sales", "Total Net Sales",
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

    # Coerce types
    df["date"]          = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
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
        "name":          ["Menu Item", "Item Name", "Item", "name", "menu_item"],
        "category":      ["Menu Group", "Category", "Menu Category",
                          "category", "menu_group"],
        "price":         ["Price", "Menu Item Price", "Unit Price",
                          "price", "menu_price"],
        "quantity_sold": ["Quantity", "Qty", "Qty Sold", "Count",
                          "quantity_sold", "quantity"],
        "total_revenue": ["Gross Sales", "Net Sales", "Total Sales",
                          "Total Net Sales", "total_revenue", "gross_sales"],
        "total_cost":    ["Total Cost", "Food Cost", "COGS", "total_cost"],
    }
    df = _normalise(df, col_map)

    for col in ["name", "category", "price", "quantity_sold", "total_revenue", "total_cost"]:
        if col not in df.columns:
            df[col] = 0 if col not in ("name", "category") else "Unknown"

    df["name"]          = df["name"].astype(str).str.strip()
    df["category"]      = df["category"].astype(str).str.strip()
    df["price"]         = _clean_currency(df["price"])
    df["quantity_sold"] = _clean_currency(df["quantity_sold"]).astype(int)
    df["total_revenue"] = _clean_currency(df["total_revenue"])
    df["total_cost"]    = _clean_currency(df["total_cost"])

    df["gross_profit"] = df["total_revenue"] - df["total_cost"]
    df["margin_pct"]   = (
        df["gross_profit"] / df["total_revenue"] * 100
    ).where(df["total_revenue"] > 0, 0).round(2)

    # Aggregate duplicate items (same name across multiple rows)
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

    # Drop rows with no name
    df = df[df["name"].str.len() > 0]

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
        "hour":    ["Hour", "Time", "Hour of Day", "hour", "time"],
        "covers":  ["Covers", "Guests", "covers", "guests"],
        "revenue": ["Net Sales", "Gross Sales", "revenue", "net_sales"],
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

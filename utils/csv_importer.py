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

def _read_raw(raw: bytes, filename: str = "", sheet_hint: str | None = None) -> pd.DataFrame:
    """Parse CSV or Excel bytes into a raw DataFrame.

    For multi-sheet Toast Sales Summary exports, pass sheet_hint to target
    a specific sheet (e.g. 'Sales by day').  Falls back to first sheet if
    the hint doesn't match.
    """
    try:
        if filename.lower().endswith(".xlsx") or raw[:4] == b"PK\x03\x04":
            xf = pd.ExcelFile(io.BytesIO(raw))
            # If a hint is provided and the sheet exists, use it
            if sheet_hint and sheet_hint in xf.sheet_names:
                return xf.parse(sheet_hint)
            # Auto-detect Toast Sales Summary multi-sheet exports
            for preferred in ("Sales by day", "Daily Sales", "sales_by_day"):
                if preferred in xf.sheet_names:
                    return xf.parse(preferred)
            # Fall back to first sheet
            return xf.parse(0)
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

def parse_paychex_labor_cost(raw: bytes, filename: str = "") -> tuple:
    """
    Parse the Paychex 'Payroll Labor Cost' CSV export (no header row).

    Column layout (0-indexed):
        0  company_name
        1  company_id
        2  flag (N / blank)
        3  employee_name  (Last, First M)
        4  employee_seq_id
        5  hire_date
        6  blank
        7  pay_frequency
        8  employment_type  (Part Time / blank=Full Time)
        9  hourly_rate
        10 state
        11 scheduled_hours  (may be blank)
        12 regular_hours    (may be blank)
        13 total_hours_worked
        14 pay_date  (MM/DD/YYYY — the check/Wednesday date)
        15 period_number
        16 year

    Returns (weekly_payroll_df, daily_labor_df).
    """
    from datetime import timedelta

    df = _read_raw(raw, filename)
    df = df.dropna(how="all")

    # Assign explicit column names
    col_names = [
        "company_name", "company_id", "flag", "employee_name",
        "employee_seq_id", "hire_date", "blank", "pay_frequency",
        "employment_type", "hourly_rate", "state",
        "scheduled_hours", "regular_hours", "total_hours", "pay_date",
        "period_number", "year",
    ]
    # Pad or trim to match actual column count
    actual_cols = len(df.columns)
    df.columns = col_names[:actual_cols] + [f"extra_{i}" for i in range(max(0, actual_cols - len(col_names)))]

    # Clean numeric columns
    df["hourly_rate"]  = _clean_currency(df["hourly_rate"].fillna(0))
    df["total_hours"]  = _clean_currency(df["total_hours"].fillna(0))
    df["regular_hours"]= _clean_currency(df.get("regular_hours", pd.Series([0]*len(df))).fillna(0))

    # Parse pay date
    df["pay_date"] = pd.to_datetime(df["pay_date"], format="%m/%d/%Y", errors="coerce")
    df = df[df["pay_date"].notna() & (df["total_hours"] > 0)]

    # Derive gross pay from hourly rate × hours
    df["gross_pay"] = (df["hourly_rate"] * df["total_hours"]).round(2)

    # Week end = pay_date, week start = pay_date - 6 days
    df["week_end"]   = df["pay_date"].dt.strftime("%Y-%m-%d")
    df["week_start"] = (df["pay_date"] - pd.Timedelta(days=6)).dt.strftime("%Y-%m-%d")

    # Employment type — blank means Full Time
    df["employment_type"] = df["employment_type"].fillna("").astype(str).str.strip()
    df["employment_type"] = df["employment_type"].replace({"": "Full Time", "nan": "Full Time"})

    # Employee name cleanup
    df["employee_name"] = df["employee_name"].astype(str).str.strip()

    # Overtime: hours > 40 in a week = overtime
    df["overtime_hours"] = (df["total_hours"] - 40).clip(lower=0).round(4)
    df["regular_hours"]  = (df["total_hours"] - df["overtime_hours"]).round(4)

    # ── weekly_payroll ────────────────────────────────────────────────────────
    wp = df[[
        "week_start", "week_end", "employee_seq_id", "employee_name",
        "employment_type", "hourly_rate", "regular_hours", "overtime_hours",
        "total_hours", "gross_pay",
    ]].copy()
    wp["employee_id"] = wp["employee_seq_id"].astype(str).str.strip()
    wp["dept"]        = "General"
    wp["role"]        = wp["employment_type"]
    wp = wp[[
        "week_start", "week_end", "employee_id", "employee_name", "dept", "role",
        "employment_type", "hourly_rate", "regular_hours", "overtime_hours",
        "total_hours", "gross_pay",
    ]].reset_index(drop=True)

    # ── daily_labor ───────────────────────────────────────────────────────────
    daily_rows = []
    for _, row in df.iterrows():
        try:
            ps = pd.to_datetime(row["week_start"]).date()
            pe = pd.to_datetime(row["week_end"]).date()
        except Exception:
            continue
        n_days      = (pe - ps).days + 1
        daily_hrs   = row["total_hours"] / n_days if n_days else 0
        daily_cost  = row["gross_pay"]   / n_days if n_days else 0
        for i in range(n_days):
            day = ps + timedelta(days=i)
            daily_rows.append({
                "date":       day.isoformat(),
                "dept":       "General",
                "hours":      round(daily_hrs,  4),
                "labor_cost": round(daily_cost, 4),
            })

    dl = pd.DataFrame(daily_rows) if daily_rows else pd.DataFrame(
        columns=["date", "dept", "hours", "labor_cost"]
    )
    if not dl.empty:
        dl = dl.groupby(["date", "dept"], as_index=False).agg(
            hours=("hours", "sum"),
            labor_cost=("labor_cost", "sum"),
        )

    return wp, dl


def parse_paychex_pdf_journal(raw: bytes, filename: str = "") -> tuple:
    """
    Parse a Paychex Payroll Journal PDF export.

    Supports the standard Paychex Flex 'Payroll Journal' PDF report.
    Extracts one row per employee-check record.

    Returns (weekly_payroll_df, daily_labor_df) in the same schema as
    parse_paychex_labor_cost.
    """
    import re
    from datetime import timedelta

    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is required for PDF payroll imports. "
            "It has been added to requirements.txt — redeploy the app to install it."
        )

    # ── Extract all text lines from the PDF ──────────────────────────────────
    lines = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.splitlines())

    # ── Regex patterns ────────────────────────────────────────────────────────
    # Employee name + first Hourly line: "Lastname,Firstname Hourly 16.0000 18.2500 292.00 ..."
    # Note: Paychex PDF has no space after the comma in the name field.
    RE_EMP = re.compile(
        r"^([A-Z][A-Za-z'\-]+,[A-Za-z\s\.]+?)\s+Hourly\s+([\d.]+)\s+([\d.]+)\s+([\d,.]+)"
    )
    # Continuation Hourly line for next check of same employee: "Hourly 16.75 25.0000 418.75 ..."
    RE_HOURLY = re.compile(
        r"^Hourly\s+([\d.]+)\s+([\d.]+)\s+([\d,.]+)"
    )
    # Check summary (no space between CHECK and DATE in Paychex PDF):
    # "CHECKDATE03/13/26 18.2500 292.00 30.03 NetPay 261.97"
    RE_CHECK = re.compile(
        r"CHECKDATE(\d{2}/\d{2}/\d{2})\s+([\d.]+)\s+([\d,.]+)\s+([\d,.]+)"
    )

    def _f(s: str) -> float:
        return float(str(s).replace(",", "").strip() or 0)

    # ── Parse ─────────────────────────────────────────────────────────────────
    records  = []
    cur_name  = None
    cur_rate  = 0.0
    cur_hours = 0.0
    cur_gross = 0.0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m_emp = RE_EMP.match(line)
        if m_emp:
            # New employee — update name and start accumulating this check
            cur_name  = m_emp.group(1).replace(",", ", ", 1).strip()
            cur_rate  = _f(m_emp.group(2))
            cur_hours = _f(m_emp.group(3))
            cur_gross = _f(m_emp.group(4))
            continue

        if cur_name:
            m_hourly = RE_HOURLY.match(line)
            if m_hourly:
                # Next check period for the same employee
                cur_hours += _f(m_hourly.group(2))
                cur_gross += _f(m_hourly.group(3))
                rate = _f(m_hourly.group(1))
                if rate > cur_rate:
                    cur_rate = rate
                continue

            m_check = RE_CHECK.search(line)
            if m_check:
                check_date_str = m_check.group(1)   # MM/DD/YY
                hours_check    = _f(m_check.group(2))
                gross_check    = _f(m_check.group(3))

                try:
                    check_dt = pd.to_datetime(check_date_str, format="%m/%d/%y")
                except Exception:
                    check_dt = pd.to_datetime(check_date_str, errors="coerce")

                if pd.isna(check_dt):
                    cur_hours = 0.0
                    cur_gross = 0.0
                    continue

                total_hours = hours_check if hours_check > 0 else cur_hours
                gross_pay   = gross_check if gross_check > 0 else cur_gross

                # week_end = day before check date; week_start = 6 days before that
                week_end_dt   = check_dt - pd.Timedelta(days=1)
                week_start_dt = check_dt - pd.Timedelta(days=7)

                records.append({
                    "employee_name": cur_name,
                    "hourly_rate":   cur_rate,
                    "total_hours":   total_hours,
                    "gross_pay":     gross_pay,
                    "week_end":      week_end_dt.strftime("%Y-%m-%d"),
                    "week_start":    week_start_dt.strftime("%Y-%m-%d"),
                })

                # Keep cur_name — same employee may have more checks on next lines
                cur_rate  = 0.0
                cur_hours = 0.0
                cur_gross = 0.0

    if not records:
        raise ValueError(
            "No employee check records found in the PDF. "
            "Please make sure this is a Paychex Payroll Journal report."
        )

    df = pd.DataFrame(records)

    # ── Build weekly_payroll ──────────────────────────────────────────────────
    df["employee_id"]     = df["employee_name"].str.replace(r"\s+", "", regex=True).str[:12]
    df["dept"]            = "General"
    df["role"]            = "Hourly"
    df["employment_type"] = "Hourly"
    df["overtime_hours"]  = (df["total_hours"] - 40).clip(lower=0).round(4)
    df["regular_hours"]   = (df["total_hours"] - df["overtime_hours"]).round(4)

    wp = df[[
        "week_start", "week_end", "employee_id", "employee_name", "dept", "role",
        "employment_type", "hourly_rate", "regular_hours", "overtime_hours",
        "total_hours", "gross_pay",
    ]].reset_index(drop=True)

    # ── Build daily_labor ─────────────────────────────────────────────────────
    daily_rows = []
    for _, row in df.iterrows():
        try:
            ps = pd.to_datetime(row["week_start"]).date()
            pe = pd.to_datetime(row["week_end"]).date()
        except Exception:
            continue
        n_days     = (pe - ps).days + 1
        daily_hrs  = row["total_hours"] / n_days if n_days else 0
        daily_cost = row["gross_pay"]   / n_days if n_days else 0
        for i in range(n_days):
            day = ps + timedelta(days=i)
            daily_rows.append({
                "date":       day.isoformat(),
                "dept":       "General",
                "hours":      round(daily_hrs,  4),
                "labor_cost": round(daily_cost, 4),
            })

    dl = pd.DataFrame(daily_rows) if daily_rows else pd.DataFrame(
        columns=["date", "dept", "hours", "labor_cost"]
    )
    if not dl.empty:
        dl = dl.groupby(["date", "dept"], as_index=False).agg(
            hours=("hours", "sum"),
            labor_cost=("labor_cost", "sum"),
        )

    # ── Parse Company Totals summary (last page) ──────────────────────────────
    summary = {
        "period_start": None,       "period_end": None,
        "check_date_start": None,   "check_date_end": None,
        "headcount": 0,             "transactions": 0,
        "total_hours": 0.0,         "gross_earnings": 0.0,
        "ee_social_security": 0.0,  "ee_medicare": 0.0,
        "ee_fed_income_tax": 0.0,   "ee_state_income_tax": 0.0,
        "ee_state_disability": 0.0, "ee_state_pfl": 0.0,
        "ee_other": 0.0,            "total_ee_withholdings": 0.0,
        "net_pay": 0.0,             "check_amt": 0.0,
        "direct_deposit_amt": 0.0,
        "er_social_security": 0.0,  "er_medicare": 0.0,
        "er_fed_unemployment": 0.0, "er_state_unemployment": 0.0,
        "er_other": 0.0,
        "total_er_liability": 0.0,  "total_tax_liability": 0.0,
    }

    RE_PERIOD = re.compile(
        r"PeriodStart-EndDates\s+(\d{2}/\d{2}/\d{2})-\s*(\d{2}/\d{2}/\d{2})",
        re.IGNORECASE,
    )
    RE_CHKDTS = re.compile(
        r"CheckDates\s+(\d{2}/\d{2}/\d{2})-\s*(\d{2}/\d{2}/\d{2})",
        re.IGNORECASE,
    )

    in_totals   = False
    in_employer = False

    for line in lines:
        s = line.strip()

        # Period / check-date range from any page footer
        m = RE_PERIOD.search(s)
        if m:
            summary["period_start"] = m.group(1)
            summary["period_end"]   = m.group(2)
        m = RE_CHKDTS.search(s)
        if m:
            summary["check_date_start"] = m.group(1)
            summary["check_date_end"]   = m.group(2)

        if "COMPANYTOTALS" in s.replace(" ", "").upper():
            in_totals   = True
            in_employer = False
            continue

        if not in_totals:
            continue

        if "EMPLOYERLIABILITIES" in s.replace(" ", "").upper():
            in_employer = True
            continue

        if not in_employer:
            # "18Person(s) Hourly 2,055.2000 37,810.63 Social Security 2,344.26 CheckAmt 12,870.82"
            m = re.match(
                r"(\d+)Person\(s\)\s+Hourly\s+([\d,.]+)\s+([\d,.]+)"
                r"\s+Social Security\s+([\d,.]+)\s+CheckAmt\s+([\d,.]+)",
                s, re.IGNORECASE,
            )
            if m:
                summary["headcount"]          = int(m.group(1))
                summary["total_hours"]        = _f(m.group(2))
                summary["gross_earnings"]     = _f(m.group(3))
                summary["ee_social_security"] = _f(m.group(4))
                summary["check_amt"]          = _f(m.group(5))
                continue

            # "79Transaction(s) Medicare 548.28 DirDep** 18,859.14"
            m = re.match(r"(\d+)Transaction\(s\)\s+Medicare\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["transactions"] = int(m.group(1))
                summary["ee_medicare"]  = _f(m.group(2))
                m2 = re.search(r"DirDep\S*\s+([\d,.]+)", s, re.IGNORECASE)
                if m2:
                    summary["direct_deposit_amt"] = _f(m2.group(1))
                continue

            m = re.match(r"Fed\s+Income\s+Tax\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["ee_fed_income_tax"] = _f(m.group(1))
                continue

            # State income tax — any "XX Income Tax NNN" that isn't Federal
            m = re.match(r"\S+\s+Income\s+Tax\s+([\d,.]+)", s, re.IGNORECASE)
            if m and "fed" not in s[:5].lower():
                summary["ee_state_income_tax"] = _f(m.group(1))
                continue

            m = re.match(r"\S+\s+Disability\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["ee_state_disability"] = _f(m.group(1))
                continue

            m = re.match(r"\S+\s+PFL\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["ee_state_pfl"] = _f(m.group(1))
                continue

            # "THIS PERIOD TOTAL 2,055.2000 37,810.63 6,080.67 NetPay 31,729.96"
            m = re.match(
                r"THIS\s+PERIOD\s+TOTAL\s+[\d,.]+\s+[\d,.]+\s+([\d,.]+)\s+NetPay\s+([\d,.]+)",
                s, re.IGNORECASE,
            )
            if m:
                summary["total_ee_withholdings"] = _f(m.group(1))
                summary["net_pay"]               = _f(m.group(2))
                continue

        else:  # employer liabilities section
            m = re.match(r"Social\s+Security\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["er_social_security"] = _f(m.group(1))
                continue

            m = re.match(r"Medicare\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["er_medicare"] = _f(m.group(1))
                continue

            m = re.match(r"Fed\s+Unemploy\S*\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["er_fed_unemployment"] = _f(m.group(1))
                continue

            # State unemployment — any "XX Unemploy NNN" that isn't Federal
            m = re.match(r"\S+\s+Unemploy\S*\s+([\d,.]+)", s, re.IGNORECASE)
            if m and "fed" not in s[:5].lower():
                summary["er_state_unemployment"] = _f(m.group(1))
                continue

            # Other employer costs (Re-empl Svc, etc.)
            m = re.match(r"TOTAL\s+EMPLOYER\s+LIABILITY\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["total_er_liability"] = _f(m.group(1))
                # Back-fill er_other = total - known items
                summary["er_other"] = max(
                    round(summary["total_er_liability"]
                          - summary["er_social_security"]
                          - summary["er_medicare"]
                          - summary["er_fed_unemployment"]
                          - summary["er_state_unemployment"], 2),
                    0.0,
                )
                continue

            m = re.match(r"TOTAL\s+TAX\s+LIABILITY\s+([\d,.]+)", s, re.IGNORECASE)
            if m:
                summary["total_tax_liability"] = _f(m.group(1))
                in_totals = False
                continue

    return wp, dl, summary


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

"""
Toast POS portal scraper — logs in as the restaurant owner and downloads reports.

Uses Playwright (headless Chromium) to drive the Toast management console at
https://pos.toasttab.com, download CSV/Excel exports, and parse them into
DataFrames matching the schema expected by sync.py.

Usage from sync.py:
    scraper = ToastScraper({"username": "...", "password": "..."})
    sales   = scraper.get_sales(start_date, end_date)
    labor   = scraper.get_labor(start_date, end_date)
    items   = scraper.get_menu_item_sales(start_date, end_date)
    scraper.close()
"""

import io
from datetime import date

import pandas as pd

PORTAL_URL  = "https://pos.toasttab.com"
LOGIN_PATH  = "/login"
TIMEOUT_MS  = 20_000   # 20 s for page actions


class ToastScraper:
    """
    Headless browser scraper for the Toast management console.

    All report methods share one browser session (opened on first call,
    closed via .close()).  The data is fetched once and cached so repeated
    calls within the same sync run don't re-download.
    """

    def __init__(self, config: dict):
        self.username = config["username"]
        self.password = config["password"]
        self._pw      = None
        self._browser = None
        self._page    = None
        self._cache: dict | None = None   # populated by _fetch_all()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _start(self):
        from playwright.sync_api import sync_playwright
        self._pw      = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(headless=True)
        ctx           = self._browser.new_context(accept_downloads=True)
        self._page    = ctx.new_page()
        self._login()

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.__exit__(None, None, None)
        self._browser = self._page = self._pw = None

    def _login(self):
        page = self._page
        page.goto(PORTAL_URL + LOGIN_PATH, wait_until="networkidle")

        # Fill credentials — selectors verified against Toast's login page
        page.get_by_placeholder("Email").fill(self.username)
        page.get_by_placeholder("Password").fill(self.password)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

        if "login" in page.url:
            raise RuntimeError(
                "Toast login failed — check credentials or disable 2FA for this account."
            )

    # ------------------------------------------------------------------
    # Internal: download all reports in one session
    # ------------------------------------------------------------------

    def _fetch_all(self, start_date: date, end_date: date) -> None:
        """Log in once, download every needed report, populate self._cache."""
        self._start()
        try:
            self._cache = {
                "sales":  self._download_sales(start_date, end_date),
                "hourly": self._download_hourly_sales(start_date, end_date),
                "items":  self._download_menu_items(start_date, end_date),
                "labor":  self._download_labor(start_date, end_date),
            }
        finally:
            self.close()

    def _ensure(self, start_date: date, end_date: date) -> None:
        if self._cache is None:
            self._fetch_all(start_date, end_date)

    # ------------------------------------------------------------------
    # Report downloaders
    # ------------------------------------------------------------------

    def _nav_to_reports(self) -> None:
        """Open the Reports section of the Toast management console."""
        page = self._page
        # Try sidebar navigation link
        try:
            page.get_by_role("link", name="Reports").click()
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
        except Exception:
            # Fallback: direct URL
            page.goto(PORTAL_URL + "/reports", wait_until="networkidle")

    def _date_str(self, d: date) -> str:
        return d.strftime("%m/%d/%Y")

    def _download_csv(self, start_date: date, end_date: date, report_name: str) -> bytes | None:
        """
        Navigate to a named report, set the date range, and download the CSV.
        Returns raw bytes or None on failure.
        """
        page = self._page
        try:
            self._nav_to_reports()

            # Click the specific report
            page.get_by_text(report_name, exact=False).first.click()
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

            # Set date range — Toast uses from/to date pickers
            for placeholder, d in [("Start date", start_date), ("End date", end_date)]:
                try:
                    field = page.get_by_placeholder(placeholder)
                    field.fill(self._date_str(d))
                except Exception:
                    pass

            # Apply / Run report button
            try:
                page.get_by_role("button", name="Run report").click()
                page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
            except Exception:
                pass

            # Download
            with page.expect_download(timeout=TIMEOUT_MS) as dl:
                try:
                    page.get_by_role("button", name="Export").click()
                except Exception:
                    page.get_by_text("Download", exact=False).first.click()

            download = dl.value
            path     = download.path()
            with open(path, "rb") as f:
                return f.read()

        except Exception as exc:
            print(f"[toast_scraper] Download failed for '{report_name}': {exc}")
            return None

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_bytes(self, raw: bytes | None, filename_hint: str = "") -> pd.DataFrame:
        """Parse CSV or Excel bytes into a DataFrame."""
        if not raw:
            return pd.DataFrame()
        try:
            if filename_hint.endswith(".xlsx") or raw[:4] == b"PK\x03\x04":
                return pd.read_excel(io.BytesIO(raw))
            return pd.read_csv(io.BytesIO(raw))
        except Exception as exc:
            print(f"[toast_scraper] Parse error: {exc}")
            return pd.DataFrame()

    def _download_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        raw = self._download_csv(start_date, end_date, "Sales Summary")
        df  = self._parse_bytes(raw)
        if df.empty:
            return df
        # Normalize column names to match schema:
        # date, covers, revenue, avg_check, food_cost, food_cost_pct
        col_map = {
            # Common Toast export column names → our schema
            "Date":                      "date",
            "Business Date":             "date",
            "Covers":                    "covers",
            "Guests":                    "covers",
            "Net Sales":                 "revenue",
            "Gross Sales":               "revenue",
            "Average Check":             "avg_check",
            "Avg Check":                 "avg_check",
            "Food Cost":                 "food_cost",
            "Food Cost %":               "food_cost_pct",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        needed = ["date", "covers", "revenue", "avg_check", "food_cost", "food_cost_pct"]
        for col in needed:
            if col not in df.columns:
                df[col] = 0
        return df[needed].copy()

    def _download_hourly_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        raw = self._download_csv(start_date, end_date, "Sales by Hour")
        df  = self._parse_bytes(raw)
        if df.empty:
            return df
        col_map = {
            "Date": "date", "Business Date": "date",
            "Hour": "hour", "Time": "hour",
            "Covers": "covers", "Guests": "covers",
            "Net Sales": "revenue", "Gross Sales": "revenue",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        for col in ["date", "hour", "covers", "revenue"]:
            if col not in df.columns:
                df[col] = 0
        return df[["date", "hour", "covers", "revenue"]].copy()

    def _download_menu_items(self, start_date: date, end_date: date) -> pd.DataFrame:
        raw = self._download_csv(start_date, end_date, "Item Selections")
        df  = self._parse_bytes(raw)
        if df.empty:
            return df
        col_map = {
            "Menu Item":       "name",
            "Item":            "name",
            "Menu Group":      "category",
            "Category":        "category",
            "Price":           "price",
            "Menu Item Price": "price",
            "Quantity":        "quantity_sold",
            "Qty":             "quantity_sold",
            "Gross Sales":     "total_revenue",
            "Net Sales":       "total_revenue",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        for col in ["name", "category", "price", "quantity_sold", "total_revenue"]:
            if col not in df.columns:
                df[col] = 0 if col != "name" and col != "category" else "Unknown"
        df["total_cost"]    = 0.0
        df["gross_profit"]  = df["total_revenue"]
        df["margin_pct"]    = 0.0
        needed = ["name", "category", "price", "quantity_sold",
                  "total_revenue", "total_cost", "gross_profit", "margin_pct"]
        return df[needed].copy()

    def _download_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        raw = self._download_csv(start_date, end_date, "Labor Summary")
        df  = self._parse_bytes(raw)
        if df.empty:
            return df
        col_map = {
            "Date":          "date",
            "Business Date": "date",
            "Job":           "dept",
            "Department":    "dept",
            "Hours":         "hours",
            "Regular Hours": "hours",
            "Labor Cost":    "labor_cost",
            "Total Cost":    "labor_cost",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        for col in ["date", "dept", "hours", "labor_cost"]:
            if col not in df.columns:
                df[col] = 0 if col != "date" and col != "dept" else "Unknown"
        return df[["date", "dept", "hours", "labor_cost"]].copy()

    # ------------------------------------------------------------------
    # Public interface (matches loader.py get_connector dict shape)
    # ------------------------------------------------------------------

    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            self._ensure(start_date, end_date)
            return self._cache.get("sales", pd.DataFrame())
        except Exception as exc:
            print(f"[toast_scraper] get_sales error: {exc}")
            return pd.DataFrame()

    def get_hourly_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            self._ensure(start_date, end_date)
            return self._cache.get("hourly", pd.DataFrame())
        except Exception as exc:
            print(f"[toast_scraper] get_hourly_sales error: {exc}")
            return pd.DataFrame()

    def get_menu_items(self, *_) -> pd.DataFrame:
        try:
            if self._cache is None:
                return pd.DataFrame()
            return self._cache.get("items", pd.DataFrame())
        except Exception as exc:
            print(f"[toast_scraper] get_menu_items error: {exc}")
            return pd.DataFrame()

    def get_menu_item_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            self._ensure(start_date, end_date)
            return self._cache.get("items", pd.DataFrame())
        except Exception as exc:
            print(f"[toast_scraper] get_menu_item_sales error: {exc}")
            return pd.DataFrame()

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            self._ensure(start_date, end_date)
            return self._cache.get("labor", pd.DataFrame())
        except Exception as exc:
            print(f"[toast_scraper] get_labor error: {exc}")
            return pd.DataFrame()

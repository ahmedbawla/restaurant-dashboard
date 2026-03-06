"""
Paychex Flex portal scraper — logs in as the payroll admin and downloads reports.

Uses Playwright (headless Chromium) to drive the Paychex Flex portal at
https://myapps.paychex.com, download CSV/Excel payroll exports, and parse them
into DataFrames matching the schema expected by sync.py.

Usage from sync.py:
    scraper = PaychexScraper({"username": "...", "password": "..."})
    labor   = scraper.get_labor(start_date, end_date)
    payroll = scraper.get_payroll(start_date, end_date)
    scraper.close()
"""

import io
from datetime import date

import pandas as pd

PORTAL_URL = "https://myapps.paychex.com"
LOGIN_PATH = "/"
TIMEOUT_MS = 20_000


class PaychexScraper:
    """
    Headless browser scraper for the Paychex Flex portal.

    All report methods share one browser session and cache results so the
    portal is only logged into once per sync run.
    """

    def __init__(self, config: dict):
        self.username = config["username"]
        self.password = config["password"]
        self._pw      = None
        self._browser = None
        self._page    = None
        self._cache: dict | None = None

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

        # Paychex login — enters username, clicks Next, then password
        try:
            page.get_by_placeholder("Username ID").fill(self.username)
        except Exception:
            page.get_by_label("Username").fill(self.username)

        try:
            page.get_by_role("button", name="Next").click()
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
        except Exception:
            pass

        try:
            page.get_by_placeholder("Password").fill(self.password)
        except Exception:
            page.get_by_label("Password").fill(self.password)

        page.get_by_role("button", name="Sign In").click()
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

        if "login" in page.url or "signin" in page.url:
            raise RuntimeError(
                "Paychex login failed — check credentials or disable 2FA for this account."
            )

    # ------------------------------------------------------------------
    # Internal: download all reports in one session
    # ------------------------------------------------------------------

    def _fetch_all(self, start_date: date, end_date: date) -> None:
        self._start()
        try:
            self._cache = {
                "payroll": self._download_payroll(start_date, end_date),
                "labor":   self._download_labor(start_date, end_date),
            }
        finally:
            self.close()

    def _ensure(self, start_date: date, end_date: date) -> None:
        if self._cache is None:
            self._fetch_all(start_date, end_date)

    # ------------------------------------------------------------------
    # Report downloaders
    # ------------------------------------------------------------------

    def _date_str(self, d: date) -> str:
        return d.strftime("%m/%d/%Y")

    def _nav_to_reports(self) -> None:
        page = self._page
        try:
            page.get_by_role("link", name="Reports").click()
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
        except Exception:
            page.goto(PORTAL_URL + "/reports", wait_until="networkidle")

    def _download_report(self, report_label: str, start_date: date, end_date: date) -> bytes | None:
        page = self._page
        try:
            self._nav_to_reports()

            # Click the report type
            page.get_by_text(report_label, exact=False).first.click()
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

            # Set date range
            for label, d in [("Start", start_date), ("End", end_date),
                              ("From", start_date), ("To", end_date)]:
                try:
                    page.get_by_label(label, exact=False).fill(self._date_str(d))
                except Exception:
                    pass

            # Run / Generate button
            for btn_name in ("Run Report", "Generate", "View Report"):
                try:
                    page.get_by_role("button", name=btn_name).click()
                    page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
                    break
                except Exception:
                    continue

            # Download
            with page.expect_download(timeout=TIMEOUT_MS) as dl:
                for btn in ("Export to Excel", "Export", "Download", "Export to CSV"):
                    try:
                        page.get_by_role("button", name=btn).click()
                        break
                    except Exception:
                        continue

            download = dl.value
            with open(download.path(), "rb") as f:
                return f.read()

        except Exception as exc:
            print(f"[paychex_scraper] Download failed for '{report_label}': {exc}")
            return None

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_bytes(self, raw: bytes | None) -> pd.DataFrame:
        if not raw:
            return pd.DataFrame()
        try:
            if raw[:4] == b"PK\x03\x04":
                return pd.read_excel(io.BytesIO(raw))
            return pd.read_csv(io.BytesIO(raw))
        except Exception as exc:
            print(f"[paychex_scraper] Parse error: {exc}")
            return pd.DataFrame()

    def _download_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        raw = self._download_report("Payroll Register", start_date, end_date)
        df  = self._parse_bytes(raw)
        if df.empty:
            return df
        col_map = {
            "Employee":          "employee_name",
            "Employee Name":     "employee_name",
            "Employee ID":       "employee_id",
            "EE ID":             "employee_id",
            "Department":        "dept",
            "Job":               "dept",
            "Title":             "role",
            "Position":          "role",
            "Hourly Rate":       "hourly_rate",
            "Rate":              "hourly_rate",
            "Pay Type":          "employment_type",
            "Employment Type":   "employment_type",
            "Regular Hours":     "regular_hours",
            "Reg Hours":         "regular_hours",
            "Overtime Hours":    "overtime_hours",
            "OT Hours":          "overtime_hours",
            "Total Hours":       "total_hours",
            "Gross Pay":         "gross_pay",
            "Period Begin":      "week_start",
            "Check Date":        "week_start",
            "Period End":        "week_end",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Derive week_end from week_start if missing
        if "week_start" in df.columns and "week_end" not in df.columns:
            df["week_end"] = pd.to_datetime(df["week_start"], errors="coerce") + pd.Timedelta(days=6)
            df["week_end"] = df["week_end"].dt.strftime("%Y-%m-%d")

        defaults = {
            "employee_id": "UNKNOWN", "employee_name": "Unknown",
            "dept": "General", "role": "Employee",
            "hourly_rate": 0.0, "employment_type": "Hourly",
            "regular_hours": 0.0, "overtime_hours": 0.0,
            "total_hours": 0.0, "gross_pay": 0.0,
            "week_start": start_date.isoformat(), "week_end": end_date.isoformat(),
        }
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default

        needed = list(defaults.keys())
        return df[needed].copy()

    def _download_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        raw = self._download_report("Time and Attendance", start_date, end_date)
        df  = self._parse_bytes(raw)
        if df.empty:
            return df
        col_map = {
            "Date":          "date",
            "Work Date":     "date",
            "Department":    "dept",
            "Job":           "dept",
            "Hours":         "hours",
            "Regular Hours": "hours",
            "Labor Cost":    "labor_cost",
            "Total Cost":    "labor_cost",
            "Gross Pay":     "labor_cost",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Aggregate to daily by dept if not already
        if "date" in df.columns and "dept" in df.columns:
            num_cols = [c for c in ["hours", "labor_cost"] if c in df.columns]
            df = df.groupby(["date", "dept"])[num_cols].sum().reset_index()

        for col in ["date", "dept", "hours", "labor_cost"]:
            if col not in df.columns:
                df[col] = 0 if col in ("hours", "labor_cost") else "Unknown"

        return df[["date", "dept", "hours", "labor_cost"]].copy()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            self._ensure(start_date, end_date)
            return self._cache.get("payroll", pd.DataFrame())
        except Exception as exc:
            print(f"[paychex_scraper] get_payroll error: {exc}")
            return pd.DataFrame()

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            self._ensure(start_date, end_date)
            return self._cache.get("labor", pd.DataFrame())
        except Exception as exc:
            print(f"[paychex_scraper] get_labor error: {exc}")
            return pd.DataFrame()

    def get_employees(self, *_) -> pd.DataFrame:
        try:
            if self._cache is None:
                return pd.DataFrame()
            return self._cache.get("payroll", pd.DataFrame())
        except Exception:
            return pd.DataFrame()

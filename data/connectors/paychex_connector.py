"""
Paychex Flex REST API connector.

Uses clientId + clientSecret (stored encrypted per user in DB) with the
OAuth 2.0 client_credentials grant to pull payroll and worker data.

Paychex API docs: https://developer.paychex.com/
"""

from datetime import date, timedelta

import pandas as pd
import requests

from data.connectors.base import BaseConnector


class PaychexConnector(BaseConnector):
    """
    Connects to the Paychex Flex REST API.

    Config keys:
        client_id     : Paychex OAuth client ID
        client_secret : Paychex OAuth client secret (decrypted)
        company_id    : Paychex company ID
    """

    BASE_URL = "https://api.paychex.com"

    def __init__(self, config: dict):
        self.client_id     = config["client_id"]
        self.client_secret = config["client_secret"]
        self.company_id    = config["company_id"]

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        from utils.oauth_paychex import get_access_token
        return get_access_token(self.client_id, self.client_secret)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict = None) -> dict:
        url  = f"{self.BASE_URL}{path}"
        resp = requests.get(url, headers=self._headers(), params=params or {}, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _get_all(self, path: str, params: dict = None) -> list:
        """Fetch all pages from a Paychex paginated endpoint."""
        params = dict(params or {})
        results = []
        while True:
            data = self._get(path, params)
            # Paychex wraps lists in "content"
            page = data.get("content", data if isinstance(data, list) else [])
            results.extend(page)
            # Pagination via "offset" + "limit"
            total  = data.get("total", len(results))
            offset = params.get("offset", 0) + len(page)
            if offset >= total or not page:
                break
            params["offset"] = offset
        return results

    # ── Worker lookup ─────────────────────────────────────────────────────────

    def _get_workers(self) -> dict:
        """Return dict: workerId → {name, dept, role, hourly_rate, employment_type, employee_id}"""
        try:
            workers = self._get_all(f"/companies/{self.company_id}/workers")
        except Exception:
            return {}

        lookup = {}
        for w in workers:
            wid  = w.get("workerId") or w.get("id", "")
            name_obj = w.get("name", {})
            given    = name_obj.get("givenName", "")
            family   = name_obj.get("familyName", "")
            name     = f"{given} {family}".strip() or "Unknown"

            # Try to get job / department info
            dept = "General"
            role = "Employee"
            try:
                jobs = self._get_all(f"/companies/{self.company_id}/workers/{wid}/jobs")
                if jobs:
                    j    = jobs[0]
                    role = j.get("jobTitle") or j.get("title") or "Employee"
                    dept = (
                        j.get("laborAssignment", {}).get("name") or
                        j.get("department", {}).get("name") or
                        j.get("workerLocation", {}).get("name") or
                        "General"
                    )
            except Exception:
                pass

            lookup[wid] = {
                "employee_id":     w.get("employeeId") or w.get("displayId") or wid,
                "employee_name":   name,
                "dept":            str(dept).strip() or "General",
                "role":            str(role).strip() or "Employee",
                "employment_type": w.get("employmentType") or w.get("payType") or "Hourly",
                "hourly_rate":     float(w.get("primaryPayRate", {}).get("payRate") or 0),
            }
        return lookup

    # ── Payroll fetching ──────────────────────────────────────────────────────

    def _get_payrolls_in_range(self, start_date: date, end_date: date) -> list:
        """Return list of payroll objects whose check date falls in [start_date, end_date]."""
        try:
            payrolls = self._get_all(
                f"/companies/{self.company_id}/payrolls",
                {"startdate": start_date.isoformat(), "enddate": end_date.isoformat()},
            )
            return payrolls
        except Exception:
            return []

    def _get_checks(self, payroll_id: str) -> list:
        """Return list of check objects for a payroll run."""
        try:
            return self._get_all(
                f"/companies/{self.company_id}/payrolls/{payroll_id}/checks"
            )
        except Exception:
            return []

    # ── Public interface ──────────────────────────────────────────────────────

    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_menu_items(self) -> pd.DataFrame:
        return pd.DataFrame()

    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_employees(self, *_) -> pd.DataFrame:
        workers = self._get_workers()
        if not workers:
            return pd.DataFrame()
        return pd.DataFrame(list(workers.values()))

    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Return weekly_payroll rows: one row per employee per pay period.

        Columns: week_start, week_end, employee_id, employee_name, dept, role,
                 employment_type, hourly_rate, regular_hours, overtime_hours,
                 total_hours, gross_pay
        """
        workers  = self._get_workers()
        payrolls = self._get_payrolls_in_range(start_date, end_date)

        rows = []
        for pr in payrolls:
            pr_id  = pr.get("payrollId") or pr.get("id", "")
            checks = self._get_checks(pr_id)
            for chk in checks:
                wid = chk.get("workerId") or chk.get("employeeId", "")
                w   = workers.get(wid, {
                    "employee_id": wid, "employee_name": "Unknown",
                    "dept": "General", "role": "Employee",
                    "employment_type": "Hourly", "hourly_rate": 0.0,
                })

                # Period dates
                period_start = (
                    chk.get("periodStartDate") or
                    pr.get("startDate") or
                    pr.get("periodStartDate") or
                    start_date.isoformat()
                )
                period_end = (
                    chk.get("periodEndDate") or
                    pr.get("endDate") or
                    pr.get("periodEndDate") or
                    end_date.isoformat()
                )

                # Earnings summary — handle both flat and nested formats
                earn = chk.get("earningsSummary") or chk.get("earnings") or {}
                if isinstance(earn, list):
                    # List of earnings lines — aggregate
                    reg_hrs = sum(float(e.get("hours") or 0) for e in earn
                                  if "overtime" not in str(e.get("earnCode", "")).lower() and
                                     "ot" not in str(e.get("earnCode", "")).lower())
                    ot_hrs  = sum(float(e.get("hours") or 0) for e in earn
                                  if "overtime" in str(e.get("earnCode", "")).lower() or
                                     str(e.get("earnCode", "")).lower() == "ot")
                    gross   = sum(float(e.get("amount") or e.get("value") or 0) for e in earn)
                else:
                    reg_hrs = float(earn.get("regularHours") or earn.get("regular_hours") or 0)
                    ot_hrs  = float(earn.get("overtimeHours") or earn.get("overtime_hours") or 0)
                    gross   = float(
                        earn.get("grossPay") or earn.get("gross_pay") or
                        chk.get("grossPay") or chk.get("netPay") or 0
                    )

                total_hrs = reg_hrs + ot_hrs or float(earn.get("totalHours") or 0)

                rows.append({
                    "week_start":       period_start[:10],
                    "week_end":         period_end[:10],
                    "employee_id":      w["employee_id"],
                    "employee_name":    w["employee_name"],
                    "dept":             w["dept"],
                    "role":             w["role"],
                    "employment_type":  w["employment_type"],
                    "hourly_rate":      w["hourly_rate"],
                    "regular_hours":    reg_hrs,
                    "overtime_hours":   ot_hrs,
                    "total_hours":      total_hrs,
                    "gross_pay":        gross,
                })

        if not rows:
            return pd.DataFrame(columns=[
                "week_start", "week_end", "employee_id", "employee_name", "dept", "role",
                "employment_type", "hourly_rate", "regular_hours", "overtime_hours",
                "total_hours", "gross_pay",
            ])

        return pd.DataFrame(rows)

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Derive daily_labor by spreading each employee's gross pay evenly
        across the calendar days in their pay period, grouped by dept.

        Columns: date, dept, hours, labor_cost
        """
        payroll_df = self.get_payroll(start_date, end_date)
        if payroll_df.empty:
            return pd.DataFrame(columns=["date", "dept", "hours", "labor_cost"])

        daily_rows = []
        for _, row in payroll_df.iterrows():
            try:
                ps = date.fromisoformat(str(row["week_start"])[:10])
                pe = date.fromisoformat(str(row["week_end"])[:10])
            except Exception:
                continue

            # Clamp to requested range
            ps = max(ps, start_date)
            pe = min(pe, end_date)
            if ps > pe:
                continue

            n_days = (pe - ps).days + 1
            daily_pay   = row["gross_pay"]   / n_days if n_days else 0
            daily_hours = row["total_hours"] / n_days if n_days else 0

            for i in range(n_days):
                day = ps + timedelta(days=i)
                daily_rows.append({
                    "date":       day.isoformat(),
                    "dept":       row["dept"],
                    "hours":      round(daily_hours, 4),
                    "labor_cost": round(daily_pay, 4),
                })

        if not daily_rows:
            return pd.DataFrame(columns=["date", "dept", "hours", "labor_cost"])

        df = pd.DataFrame(daily_rows)
        # Aggregate by date + dept (multiple employees same dept same day)
        df = df.groupby(["date", "dept"], as_index=False).agg(
            hours=("hours", "sum"),
            labor_cost=("labor_cost", "sum"),
        )
        return df[["date", "dept", "hours", "labor_cost"]].reset_index(drop=True)

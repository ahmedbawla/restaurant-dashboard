"""
QuickBooks Online connector — OAuth 2.0.

Uses the QBO v3 REST API (Query API).
Access tokens are short-lived (1 hr); refresh tokens last 100 days and
are automatically rotated and persisted on each use.
"""

from datetime import date

import pandas as pd
import requests

from utils.oauth_quickbooks import refresh_access_token


class QuickBooksConnector:
    BASE_URL = "https://quickbooks.api.intuit.com/v3/company"

    def __init__(self, config: dict):
        self.realm_id      = config["realm_id"]
        self.refresh_token = config["refresh_token"]
        self._db_username  = config.get("username")  # to persist rotated refresh tokens
        self._access_token: str | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if not yet obtained."""
        if self._access_token:
            return self._access_token
        tokens = refresh_access_token(self.refresh_token)
        self._access_token = tokens["access_token"]
        # Persist rotated refresh token if Intuit issues a new one
        new_rt = tokens.get("refresh_token")
        if new_rt and new_rt != self.refresh_token and self._db_username:
            try:
                from data.database import update_user
                update_user(self._db_username, qb_refresh_token=new_rt)
                self.refresh_token = new_rt
            except Exception:
                pass
        return self._access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Accept":        "application/json",
        }

    def _query(self, sql: str) -> list[dict]:
        """Execute a QBO query and return the list of entity dicts."""
        resp = requests.get(
            f"{self.BASE_URL}/{self.realm_id}/query",
            headers=self._headers(),
            params={"query": sql, "minorversion": "65"},
            timeout=30,
        )
        resp.raise_for_status()
        qr = resp.json().get("QueryResponse", {})
        for key in ("Purchase", "Bill", "Payment", "BillPayment", "SalesReceipt"):
            if key in qr:
                return qr[key]
        return []

    # ------------------------------------------------------------------
    # Public data methods
    # ------------------------------------------------------------------

    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Return DataFrame(date, category, vendor, amount, description).
        Combines QBO Purchase (credit card / check / cash) and Bill transactions.
        """
        sd, ed = start_date.isoformat(), end_date.isoformat()
        rows: list[dict] = []

        # Purchases — paid immediately (credit card, check, cash)
        for p in self._query(
            f"SELECT * FROM Purchase WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}' MAXRESULTS 1000"
        ):
            vendor = (
                (p.get("EntityRef") or {}).get("name") or
                (p.get("VendorRef") or {}).get("name") or
                "Unknown Vendor"
            )
            for line in p.get("Line", []):
                detail   = line.get("AccountBasedExpenseLineDetail") or {}
                category = (detail.get("AccountRef") or {}).get("name") or "Uncategorized"
                amount   = float(line.get("Amount", 0))
                if amount > 0:
                    rows.append({
                        "date":        p.get("TxnDate", sd),
                        "category":    category,
                        "vendor":      vendor,
                        "amount":      amount,
                        "description": p.get("PrivateNote") or p.get("DocNumber") or "",
                    })

        # Bills — accounts payable
        for b in self._query(
            f"SELECT * FROM Bill WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}' MAXRESULTS 1000"
        ):
            vendor = (b.get("VendorRef") or {}).get("name") or "Unknown Vendor"
            for line in b.get("Line", []):
                detail   = line.get("AccountBasedExpenseLineDetail") or {}
                category = (detail.get("AccountRef") or {}).get("name") or "Uncategorized"
                amount   = float(line.get("Amount", 0))
                if amount > 0:
                    rows.append({
                        "date":        b.get("TxnDate", sd),
                        "category":    category,
                        "vendor":      vendor,
                        "amount":      amount,
                        "description": (b.get("VendorRef") or {}).get("name") or "",
                    })

        if not rows:
            return pd.DataFrame(columns=["date", "category", "vendor", "amount", "description"])
        return pd.DataFrame(rows)

    def get_cash_flow(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Return DataFrame(date, inflow, outflow, net) aggregated by day.
        Inflows  = customer payments (Payment + SalesReceipt).
        Outflows = vendor purchases + bill payments.
        """
        sd, ed = start_date.isoformat(), end_date.isoformat()
        inflow_by_date:  dict[str, float] = {}
        outflow_by_date: dict[str, float] = {}

        for txn_type in ("Payment", "SalesReceipt"):
            for t in self._query(
                f"SELECT * FROM {txn_type} WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}' MAXRESULTS 1000"
            ):
                d = t.get("TxnDate", sd)
                inflow_by_date[d] = inflow_by_date.get(d, 0.0) + float(t.get("TotalAmt", 0))

        for p in self._query(
            f"SELECT * FROM Purchase WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}' MAXRESULTS 1000"
        ):
            d = p.get("TxnDate", sd)
            outflow_by_date[d] = outflow_by_date.get(d, 0.0) + float(p.get("TotalAmt", 0))

        for bp in self._query(
            f"SELECT * FROM BillPayment WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}' MAXRESULTS 1000"
        ):
            d = bp.get("TxnDate", sd)
            outflow_by_date[d] = outflow_by_date.get(d, 0.0) + float(bp.get("TotalAmt", 0))

        all_dates = sorted(set(list(inflow_by_date) + list(outflow_by_date)))
        if not all_dates:
            return pd.DataFrame(columns=["date", "inflow", "outflow", "net"])

        rows = []
        for d in all_dates:
            inf = inflow_by_date.get(d, 0.0)
            out = outflow_by_date.get(d, 0.0)
            rows.append({"date": d, "inflow": inf, "outflow": out, "net": inf - out})
        return pd.DataFrame(rows)

    # QBO does not provide POS sales, labour, or payroll data
    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_menu_items(self) -> pd.DataFrame:
        return pd.DataFrame()

    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

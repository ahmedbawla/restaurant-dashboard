"""
QuickBooks Online connector — OAuth 2.0.

Uses the QBO v3 REST API (Query API).
Access tokens are short-lived (1 hr); refresh tokens last 100 days and
are automatically rotated and persisted on each use.

Transaction types fetched for expenses:
  - Purchase  : credit card / check / cash paid immediately
  - Bill      : accounts-payable vendor invoices
  - JournalEntry : payroll, depreciation, accruals, rent-by-ACH, etc.
    (only debit-side lines are captured so credits are never double-counted)
All queries are paginated to avoid the QBO 1 000-row MAXRESULTS hard cap.
"""

from datetime import date

import pandas as pd
import requests

from utils.oauth_quickbooks import refresh_access_token

_PAGE_SIZE = 1000  # QBO maximum per request


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

    def _query_page(self, sql: str) -> list[dict]:
        """Execute a single QBO query page and return the entity list."""
        resp = requests.get(
            f"{self.BASE_URL}/{self.realm_id}/query",
            headers=self._headers(),
            params={"query": sql, "minorversion": "65"},
            timeout=30,
        )
        resp.raise_for_status()
        qr = resp.json().get("QueryResponse", {})
        for key in (
            "Purchase", "Bill", "JournalEntry",
            "Payment", "BillPayment", "SalesReceipt",
        ):
            if key in qr:
                return qr[key]
        return []

    def _query_all(self, sql_base: str) -> list[dict]:
        """
        Paginate through all results for a query.
        sql_base must NOT include STARTPOSITION or MAXRESULTS — they are appended here.
        """
        results: list[dict] = []
        start = 1
        while True:
            page = self._query_page(
                f"{sql_base} STARTPOSITION {start} MAXRESULTS {_PAGE_SIZE}"
            )
            results.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            start += _PAGE_SIZE
        return results

    # ------------------------------------------------------------------
    # Public data methods
    # ------------------------------------------------------------------

    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Return DataFrame(date, category, vendor, amount, description).

        Sources:
          • Purchase  — credit card / check / cash paid immediately
          • Bill      — vendor invoices (accounts payable)
          • JournalEntry — payroll, depreciation, accruals (debit lines only)
        """
        sd, ed = start_date.isoformat(), end_date.isoformat()
        rows: list[dict] = []

        # ── Purchases — paid immediately ──────────────────────────────
        for p in self._query_all(
            f"SELECT * FROM Purchase WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}'"
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

        # ── Bills — accounts payable ──────────────────────────────────
        for b in self._query_all(
            f"SELECT * FROM Bill WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}'"
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

        # ── Journal Entries — payroll, depreciation, accruals ─────────
        # Only capture DEBIT lines (expense side). Credits are the offsetting
        # bank/liability entries and must not be double-counted.
        for je in self._query_all(
            f"SELECT * FROM JournalEntry WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}'"
        ):
            memo = je.get("PrivateNote") or je.get("DocNumber") or ""
            for line in je.get("Line", []):
                detail = line.get("JournalEntryLineDetail") or {}
                if detail.get("PostingType") != "Debit":
                    continue  # skip credit lines — those are balance-sheet / cash entries
                category = (detail.get("AccountRef") or {}).get("name") or "Uncategorized"
                amount   = float(line.get("Amount", 0))
                if amount > 0:
                    rows.append({
                        "date":        je.get("TxnDate", sd),
                        "category":    category,
                        "vendor":      "Journal Entry",
                        "amount":      amount,
                        "description": line.get("Description") or memo,
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
            for t in self._query_all(
                f"SELECT * FROM {txn_type} WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}'"
            ):
                d = t.get("TxnDate", sd)
                inflow_by_date[d] = inflow_by_date.get(d, 0.0) + float(t.get("TotalAmt", 0))

        for p in self._query_all(
            f"SELECT * FROM Purchase WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}'"
        ):
            d = p.get("TxnDate", sd)
            outflow_by_date[d] = outflow_by_date.get(d, 0.0) + float(p.get("TotalAmt", 0))

        for bp in self._query_all(
            f"SELECT * FROM BillPayment WHERE TxnDate >= '{sd}' AND TxnDate <= '{ed}'"
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

    def get_pending_bank_transactions(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Fetch unreviewed bank feed transactions via the QBO Banking API.
        Requires the com.intuit.quickbooks.banking OAuth scope — returns an
        empty DataFrame gracefully if the scope has not been granted yet
        (user needs to disconnect and reconnect QuickBooks).

        Only DEBIT (outflow) transactions with status PENDING are returned.
        Matched / approved / excluded items are already captured by get_expenses().

        Returns the same schema as get_expenses() with category='Pending Review'
        so the spending page can display totals and label them appropriately.
        """
        sd, ed = start_date.isoformat(), end_date.isoformat()
        _empty = pd.DataFrame(columns=["date", "category", "vendor", "amount", "description"])

        try:
            resp = requests.get(
                f"{self.BASE_URL}/{self.realm_id}/bankfeeds/transactions",
                headers=self._headers(),
                params={"startdate": sd, "enddate": ed, "minorversion": "65"},
                timeout=30,
            )
            if resp.status_code in (401, 403):
                # Banking scope not yet granted — fail silently
                return _empty
            resp.raise_for_status()
        except requests.HTTPError:
            return _empty
        except Exception:
            return _empty

        data = resp.json()
        raw  = (data.get("BankFeedTransactionList") or {}).get("BankFeedTransaction") or []
        # QBO returns a single dict instead of a list when there is exactly one result
        if isinstance(raw, dict):
            raw = [raw]

        rows: list[dict] = []
        for t in raw:
            # Skip anything that has already been reviewed / matched / excluded —
            # those are already in the ledger as Purchase / Bill / JournalEntry.
            status = (t.get("Status") or "").upper()
            if status in ("MATCHED", "APPROVED", "EXCLUDED", "DELETED"):
                continue

            # Only outflows (money leaving the account) are expenses.
            txn_type = (t.get("TransactionType") or "").upper()
            if txn_type == "CREDIT":
                continue

            amount = float(t.get("Amount") or 0)
            if amount <= 0:
                continue

            description = t.get("Description") or t.get("Memo") or ""
            rows.append({
                "date":        t.get("TxnDate", sd),
                "category":    "Pending Review",
                "vendor":      description or "Unknown",
                "amount":      amount,
                "description": description,
            })

        if not rows:
            return _empty
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

"""
Real QuickBooks Online connector — placeholder.
Replace the stub methods below with actual QBO REST API calls.
QBO API docs: https://developer.intuit.com/app/developer/qbo/docs/api/accounting/most-commonly-used/account
"""

from datetime import date

import pandas as pd

from data.connectors.base import BaseConnector


class QuickBooksConnector(BaseConnector):
    """
    Connects to the QuickBooks Online REST API (OAuth2).

    Config keys expected:
        client_id     : Intuit OAuth2 client ID
        client_secret : Intuit OAuth2 client secret
        realm_id      : QBO company realm ID
        refresh_token : Long-lived refresh token (obtained via OAuth2 flow)
    """

    TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    BASE_URL = "https://quickbooks.api.intuit.com"

    def __init__(self, config: dict):
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.realm_id = config.get("realm_id", "")
        self.refresh_token = config.get("refresh_token", "")
        self._access_token: str | None = None

    def _refresh_access_token(self) -> str:
        # TODO: POST to TOKEN_URL with grant_type=refresh_token
        raise NotImplementedError("QuickBooks OAuth2 token refresh not yet implemented.")

    def _headers(self) -> dict:
        token = self._access_token or self._refresh_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # TODO: implement each method with real QBO API calls
    # ------------------------------------------------------------------

    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        # QBO handles expenses, not POS sales
        return pd.DataFrame()

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_menu_items(self) -> pd.DataFrame:
        return pd.DataFrame()

    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("QuickBooks real connector not yet implemented. Set use_simulated_data=true in config.json.")

    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

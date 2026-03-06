"""
Real Toast POS connector — OAuth 2.0 client_credentials.

Uses clientId + clientSecret (stored per user in DB) to obtain a short-lived
Bearer token on demand.  Tokens are cached in-process by oauth_toast.
Toast API docs: https://doc.toasttab.com/
"""

from datetime import date

import pandas as pd

from data.connectors.base import BaseConnector


class ToastConnector(BaseConnector):
    """
    Connects to the Toast POS REST API.

    Config keys expected:
        client_id       : Toast OAuth client ID  (stored in toast_api_key column)
        client_secret   : Toast OAuth client secret
        restaurant_guid : GUID of the restaurant location (auto-fetched on connect)
    """

    BASE_URL = "https://ws-api.toasttab.com"

    def __init__(self, config: dict):
        self.client_id       = config["client_id"]
        self.client_secret   = config["client_secret"]
        self.restaurant_guid = config["restaurant_guid"]

    def _headers(self) -> dict:
        from utils.oauth_toast import get_access_token
        token = get_access_token(self.client_id, self.client_secret)
        return {
            "Toast-Restaurant-External-ID": self.restaurant_guid,
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }

    # ------------------------------------------------------------------
    # TODO: implement each method with real Toast API calls
    # ------------------------------------------------------------------

    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("Toast real connector not yet implemented.")

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("Toast real connector not yet implemented.")

    def get_menu_items(self) -> pd.DataFrame:
        raise NotImplementedError("Toast real connector not yet implemented.")

    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

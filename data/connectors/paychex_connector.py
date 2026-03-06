"""
Real Paychex connector — OAuth 2.0 client_credentials.

Uses clientId + clientSecret (stored per user in DB) to obtain a short-lived
Bearer token on demand.  Tokens are cached in-process by oauth_paychex.
Paychex API docs: https://developer.paychex.com/
"""

from datetime import date

import pandas as pd

from data.connectors.base import BaseConnector


class PaychexConnector(BaseConnector):
    """
    Connects to the Paychex Flex REST API.

    Config keys expected:
        client_id     : Paychex OAuth client ID
        client_secret : Paychex OAuth client secret
        company_id    : Paychex company ID (auto-fetched on connect)
    """

    BASE_URL = "https://api.paychex.com"

    def __init__(self, config: dict):
        self.client_id     = config["client_id"]
        self.client_secret = config["client_secret"]
        self.company_id    = config["company_id"]

    def _get_token(self) -> str:
        from utils.oauth_paychex import get_access_token
        return get_access_token(self.client_id, self.client_secret)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    # ------------------------------------------------------------------
    # TODO: implement each method with real Paychex API calls
    # ------------------------------------------------------------------

    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("Paychex real connector not yet implemented.")

    def get_menu_items(self) -> pd.DataFrame:
        return pd.DataFrame()

    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("Paychex real connector not yet implemented.")

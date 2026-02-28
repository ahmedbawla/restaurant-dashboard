"""
Real Paychex connector — placeholder.
Replace the stub methods below with actual Paychex Flex API calls.
Paychex API docs: https://developer.paychex.com/
"""

from datetime import date

import pandas as pd

from data.connectors.base import BaseConnector


class PaychexConnector(BaseConnector):
    """
    Connects to the Paychex Flex REST API (OAuth2).

    Config keys expected:
        client_id     : Paychex OAuth2 client ID
        client_secret : Paychex OAuth2 client secret
        company_id    : Paychex company ID
    """

    AUTH_URL = "https://iam.paychex.com/security/oauth2/v2/token"
    BASE_URL = "https://api.paychex.com"

    def __init__(self, config: dict):
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.company_id = config.get("company_id", "")
        self._access_token: str | None = None

    def _get_token(self) -> str:
        # TODO: implement OAuth2 client_credentials grant
        raise NotImplementedError("Paychex OAuth2 not yet implemented.")

    # ------------------------------------------------------------------
    # TODO: implement each method with real Paychex API calls
    # ------------------------------------------------------------------

    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        # Paychex handles payroll, not sales
        return pd.DataFrame()

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("Paychex real connector not yet implemented. Set use_simulated_data=true in config.json.")

    def get_menu_items(self) -> pd.DataFrame:
        return pd.DataFrame()

    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("Paychex real connector not yet implemented.")

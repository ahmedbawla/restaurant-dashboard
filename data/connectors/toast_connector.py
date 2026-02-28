"""
Real Toast POS connector — placeholder.
Replace the stub methods below with actual Toast API calls.
Toast API docs: https://doc.toasttab.com/
"""

from datetime import date

import pandas as pd

from data.connectors.base import BaseConnector


class ToastConnector(BaseConnector):
    """
    Connects to the Toast POS REST API.

    Config keys expected:
        api_key         : Toast API access token
        restaurant_guid : GUID of the restaurant location
    """

    BASE_URL = "https://ws-api.toasttab.com"

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.restaurant_guid = config.get("restaurant_guid", "")

    def _headers(self) -> dict:
        return {
            "Toast-Restaurant-External-ID": self.restaurant_guid,
            "Authorization": f"Bearer {self.api_key}",
        }

    # ------------------------------------------------------------------
    # TODO: implement each method with real Toast API calls
    # ------------------------------------------------------------------

    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("Toast real connector not yet implemented. Set use_simulated_data=true in config.json.")

    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        raise NotImplementedError("Toast real connector not yet implemented.")

    def get_menu_items(self) -> pd.DataFrame:
        raise NotImplementedError("Toast real connector not yet implemented.")

    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        # Toast handles sales, not expenses — delegate to QuickBooks
        return pd.DataFrame()

    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        # Toast handles sales, not payroll — delegate to Paychex
        return pd.DataFrame()

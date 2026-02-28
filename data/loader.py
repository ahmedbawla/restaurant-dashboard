"""
Connector factory.
Reads config.json and returns simulated or real connector instances.
"""

import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        return json.load(f)


def get_connector(source: str):
    """
    Returns the appropriate connector for `source` (toast / paychex / quickbooks).
    Controlled by config.json `use_simulated_data` flag.
    """
    config = _load_config()
    use_sim = config.get("use_simulated_data", True)

    if source == "toast":
        if use_sim:
            from data.simulated.toast_simulated import (
                get_sales,
                get_hourly_sales,
                get_menu_items,
                get_menu_item_sales,
            )
            return {
                "get_sales": get_sales,
                "get_hourly_sales": get_hourly_sales,
                "get_menu_items": get_menu_items,
                "get_menu_item_sales": get_menu_item_sales,
            }
        else:
            from data.connectors.toast_connector import ToastConnector
            return ToastConnector(config["connectors"]["toast"])

    elif source == "paychex":
        if use_sim:
            from data.simulated.paychex_simulated import (
                get_labor,
                get_payroll,
                get_employees,
            )
            return {
                "get_labor": get_labor,
                "get_payroll": get_payroll,
                "get_employees": get_employees,
            }
        else:
            from data.connectors.paychex_connector import PaychexConnector
            return PaychexConnector(config["connectors"]["paychex"])

    elif source == "quickbooks":
        if use_sim:
            from data.simulated.quickbooks_simulated import get_expenses, get_cash_flow
            return {
                "get_expenses": get_expenses,
                "get_cash_flow": get_cash_flow,
            }
        else:
            from data.connectors.quickbooks_connector import QuickBooksConnector
            return QuickBooksConnector(config["connectors"]["quickbooks"])

    else:
        raise ValueError(f"Unknown source: {source}")

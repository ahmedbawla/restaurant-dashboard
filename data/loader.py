"""
Connector factory.
Returns simulated or real connector instances based on the user's settings.
"""


def get_connector(source: str, user: dict):
    """
    Returns the appropriate connector for `source` (toast / paychex / quickbooks).
    Controlled by user["use_simulated_data"].
    """
    use_sim = user.get("use_simulated_data", True)

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
            return ToastConnector({
                "api_key": user.get("toast_api_key", ""),
                "restaurant_guid": user.get("toast_guid", ""),
            })

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
            return PaychexConnector({
                "client_id": user.get("paychex_client_id", ""),
                "client_secret": user.get("paychex_client_secret", ""),
                "company_id": user.get("paychex_company_id", ""),
            })

    elif source == "quickbooks":
        if use_sim:
            from data.simulated.quickbooks_simulated import get_expenses, get_cash_flow
            return {
                "get_expenses": get_expenses,
                "get_cash_flow": get_cash_flow,
            }
        else:
            from data.connectors.quickbooks_connector import QuickBooksConnector
            return QuickBooksConnector({
                "client_id": user.get("qb_client_id", ""),
                "client_secret": user.get("qb_client_secret", ""),
                "realm_id": user.get("qb_realm_id", ""),
                "refresh_token": user.get("qb_refresh_token", ""),
            })

    else:
        raise ValueError(f"Unknown source: {source}")

"""
Connector factory.

Rules:
- If use_simulated_data=True → always return simulated connector (demo mode).
- If use_simulated_data=False → use real connector IF the required credentials
  exist for that source, otherwise fall back to simulated.

This means a real user can connect QuickBooks without breaking Toast/Paychex
(those will keep using simulated data until their own credentials are added).
"""


def _has_toast_creds(user: dict) -> bool:
    return bool(user.get("toast_api_key") and user.get("toast_guid"))


def _has_paychex_creds(user: dict) -> bool:
    return bool(
        user.get("paychex_client_id") and
        user.get("paychex_client_secret") and
        user.get("paychex_company_id")
    )


def _has_qb_creds(user: dict) -> bool:
    return bool(user.get("qb_realm_id") and user.get("qb_refresh_token"))


def get_connector(source: str, user: dict):
    """
    Returns the appropriate connector for `source` (toast / paychex / quickbooks).
    Always returns a dict of callables so sync.py can use connector["method"](args).
    """
    use_sim = user.get("use_simulated_data", True)

    if source == "toast":
        if not use_sim and _has_toast_creds(user):
            from data.connectors.toast_connector import ToastConnector
            conn = ToastConnector({
                "api_key":         user["toast_api_key"],
                "restaurant_guid": user["toast_guid"],
            })
            return {
                "get_sales":           conn.get_sales,
                "get_hourly_sales":    conn.get_hourly_sales,
                "get_menu_items":      conn.get_menu_items,
                "get_menu_item_sales": conn.get_menu_item_sales,
            }
        from data.simulated.toast_simulated import (
            get_sales, get_hourly_sales, get_menu_items, get_menu_item_sales,
        )
        return {
            "get_sales":           get_sales,
            "get_hourly_sales":    get_hourly_sales,
            "get_menu_items":      get_menu_items,
            "get_menu_item_sales": get_menu_item_sales,
        }

    elif source == "paychex":
        if not use_sim and _has_paychex_creds(user):
            from data.connectors.paychex_connector import PaychexConnector
            conn = PaychexConnector({
                "client_id":     user["paychex_client_id"],
                "client_secret": user["paychex_client_secret"],
                "company_id":    user["paychex_company_id"],
            })
            return {
                "get_labor":     conn.get_labor,
                "get_payroll":   conn.get_payroll,
                "get_employees": conn.get_employees,
            }
        from data.simulated.paychex_simulated import get_labor, get_payroll, get_employees
        return {
            "get_labor":     get_labor,
            "get_payroll":   get_payroll,
            "get_employees": get_employees,
        }

    elif source == "quickbooks":
        if not use_sim and _has_qb_creds(user):
            from data.connectors.quickbooks_connector import QuickBooksConnector
            conn = QuickBooksConnector({
                "realm_id":      user["qb_realm_id"],
                "refresh_token": user["qb_refresh_token"],
                "username":      user.get("username"),
            })
            return {
                "get_expenses":  conn.get_expenses,
                "get_cash_flow": conn.get_cash_flow,
            }
        from data.simulated.quickbooks_simulated import get_expenses, get_cash_flow
        return {
            "get_expenses":  get_expenses,
            "get_cash_flow": get_cash_flow,
        }

    else:
        raise ValueError(f"Unknown source: {source}")

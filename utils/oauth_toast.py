"""
Toast POS authentication — OAuth 2.0 client_credentials grant.

Toast does NOT use an authorization-code / redirect flow.
The restaurant owner obtains a clientId + clientSecret from the Toast developer
portal and enters them once.  This module exchanges those credentials for an
access token (cached in-process) and can auto-discover the restaurant GUID so
the user never has to find or copy it.

Toast auth docs: https://doc.toasttab.com/doc/devguide/authentication.html
"""

import time

import requests

AUTH_URL        = "https://ws-api.toasttab.com/authentication/v1/authentication/login"
RESTAURANTS_URL = "https://ws-api.toasttab.com/restaurants/v1/restaurants"

# In-process token cache: client_id → (token, expires_at)
_CACHE: dict[str, tuple[str, float]] = {}


def get_access_token(client_id: str, client_secret: str) -> str:
    """Return a valid access token, fetching a fresh one when needed."""
    cached = _CACHE.get(client_id)
    if cached and time.time() < cached[1] - 60:
        return cached[0]

    resp = requests.post(
        AUTH_URL,
        json={
            "clientId":       client_id,
            "clientSecret":   client_secret,
            "userAccessType": "TOAST_MACHINE_CLIENT",
        },
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "SUCCESS":
        raise RuntimeError(f"Toast auth failed: {data.get('message', data)}")

    token      = data["token"]["accessToken"]
    expires_in = data["token"].get("expiresIn", 86400)
    _CACHE[client_id] = (token, time.time() + expires_in)
    return token


def get_restaurants(client_id: str, client_secret: str) -> list[dict]:
    """
    Return the list of restaurants accessible to these credentials.
    Each dict has at minimum: restaurantGuid, restaurantName.
    """
    token = get_access_token(client_id, client_secret)
    resp = requests.get(
        RESTAURANTS_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    # Response is either a list or wrapped in a key
    if isinstance(data, list):
        return data
    return data.get("restaurants", data.get("results", []))


def connect(client_id: str, client_secret: str) -> tuple[bool, list[dict], str]:
    """
    Validate credentials and fetch accessible restaurants.
    Returns (success, restaurants_list, error_message).
    restaurants_list entries: {"restaurantGuid": "...", "restaurantName": "..."}
    """
    try:
        restaurants = get_restaurants(client_id, client_secret)
        return True, restaurants, ""
    except requests.HTTPError as exc:
        return False, [], f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        return False, [], str(exc)

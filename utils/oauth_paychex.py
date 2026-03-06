"""
Paychex Flex authentication — OAuth 2.0 client_credentials grant.

Paychex does NOT use an authorization-code / redirect flow for API access.
The company admin obtains a clientId + clientSecret from the Paychex developer
portal and enters them once.  This module exchanges those for an access token
(cached in-process) and can auto-discover the company ID so the user never has
to find or copy it.

Paychex auth docs: https://developer.paychex.com/documentation#section/Authentication
"""

import time

import requests

TOKEN_URL    = "https://iam.paychex.com/security/oauth2/v2/token"
COMPANIES_URL = "https://api.paychex.com/companies"

# In-process token cache: client_id → (token, expires_at)
_CACHE: dict[str, tuple[str, float]] = {}


def get_access_token(client_id: str, client_secret: str) -> str:
    """Return a valid access token, fetching a fresh one when needed."""
    cached = _CACHE.get(client_id)
    if cached and time.time() < cached[1] - 60:
        return cached[0]

    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    token      = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    _CACHE[client_id] = (token, time.time() + expires_in)
    return token


def get_companies(client_id: str, client_secret: str) -> list[dict]:
    """
    Return the list of companies accessible to these credentials.
    Each dict has at minimum: companyId, displayId, legalName.
    """
    token = get_access_token(client_id, client_secret)
    resp = requests.get(
        COMPANIES_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    # Response is either a list or wrapped in a key
    if isinstance(data, list):
        return data
    return data.get("content", data.get("companies", []))


def connect(client_id: str, client_secret: str) -> tuple[bool, list[dict], str]:
    """
    Validate credentials and fetch accessible companies.
    Returns (success, companies_list, error_message).
    companies_list entries: {"companyId": "...", "legalName": "..."}
    """
    try:
        companies = get_companies(client_id, client_secret)
        return True, companies, ""
    except requests.HTTPError as exc:
        return False, [], f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        return False, [], str(exc)

"""
QuickBooks Online OAuth 2.0 helpers.

Add to .streamlit/secrets.toml:

    [quickbooks]
    client_id     = "ABCdef..."
    client_secret = "XYZabc..."
    redirect_uri  = "https://your-app.streamlit.app"

The redirect_uri must exactly match what is registered in the Intuit developer portal.
"""

import base64
import secrets as _secrets
import urllib.parse

import requests

AUTH_ENDPOINT  = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_ENDPOINT = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SCOPES         = "com.intuit.quickbooks.accounting com.intuit.quickbooks.banking"


def _get_secrets() -> dict:
    try:
        import streamlit as st
        cfg = st.secrets.get("quickbooks", {})
        return {
            "client_id":     cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri":  cfg["redirect_uri"],
        }
    except Exception as exc:
        raise RuntimeError(
            "QuickBooks secrets not configured. "
            "Add [quickbooks] section to .streamlit/secrets.toml."
        ) from exc


def is_configured() -> bool:
    """True if QuickBooks OAuth app credentials are present in Streamlit secrets."""
    try:
        _get_secrets()
        return True
    except Exception:
        return False


def generate_nonce() -> str:
    """Return a cryptographically random nonce string."""
    return _secrets.token_urlsafe(32)


def get_auth_url(username: str, nonce: str) -> str:
    """Build the Intuit authorization URL for the given user."""
    cfg = _get_secrets()
    state = base64.urlsafe_b64encode(f"{username}:{nonce}".encode()).decode().rstrip("=")
    params = {
        "client_id":     cfg["client_id"],
        "response_type": "code",
        "scope":         SCOPES,
        "redirect_uri":  cfg["redirect_uri"],
        "state":         state,
    }
    return AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params)


def decode_state(state: str) -> tuple[str, str]:
    """Decode the OAuth state parameter → (username, nonce)."""
    padded = state + "=" * (-len(state) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode()).decode()
    username, nonce = decoded.split(":", 1)
    return username, nonce


def exchange_code(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    cfg = _get_secrets()
    resp = requests.post(
        TOKEN_ENDPOINT,
        auth=(cfg["client_id"], cfg["client_secret"]),
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": cfg["redirect_uri"],
        },
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if not resp.ok:
        try:
            _body = resp.json()
        except Exception:
            _body = resp.text
        raise RuntimeError(
            f"Intuit returned HTTP {resp.status_code} — {_body}. "
            f"redirect_uri used: {cfg['redirect_uri']}"
        )
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    """
    Obtain a new access token (and possibly a rotated refresh token).
    Returns the full token response dict with keys:
        access_token, refresh_token, expires_in, x_refresh_token_expires_in, token_type
    """
    cfg = _get_secrets()
    resp = requests.post(
        TOKEN_ENDPOINT,
        auth=(cfg["client_id"], cfg["client_secret"]),
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

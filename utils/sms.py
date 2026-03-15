"""
Twilio SMS helper for sending verification codes.

Configure in .streamlit/secrets.toml:

    [twilio]
    account_sid = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    auth_token  = "your_auth_token"
    from_number = "+15550001234"

If the [twilio] section is absent or the user has no phone number,
send_verification_code() returns False and auth.py surfaces the code
in a Dev mode warning box.
"""


def _get_config() -> dict | None:
    try:
        import streamlit as st
        cfg = st.secrets.get("twilio", {})
        sid   = cfg.get("account_sid", "")
        token = cfg.get("auth_token", "")
        from_ = cfg.get("from_number", "")
        if sid and token and from_:
            return {"account_sid": sid, "auth_token": token, "from_number": from_}
    except Exception:
        pass
    return None


def send_login_notification(username: str, restaurant_name: str, is_new_user: bool = False) -> bool:
    """
    Notify the owner via Telegram when someone logs in or signs up.
    Reads bot_token and owner_chat_id from st.secrets["telegram"].
    Silently no-ops if not configured.
    """
    try:
        import streamlit as st
        cfg = st.secrets.get("telegram", {})
        token   = cfg.get("bot_token", "")
        chat_id = cfg.get("owner_chat_id", "")
    except Exception:
        return False
    if not token or not chat_id:
        return False
    try:
        import requests as _req
        action = "signed up 🆕" if is_new_user else "logged in 👤"
        text = f"TableMetrics: *{username}* ({restaurant_name}) just {action}."
        _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=5,
        )
        return True
    except Exception:
        return False


def send_verification_code(phone_number: str | None, code: str) -> bool:
    """
    Send `code` to `phone_number` via Twilio SMS.

    Returns True on success.
    Returns False if Twilio is not configured or phone_number is empty/None.
    Callers should show the code in a warning box when this returns False.
    """
    if not phone_number:
        return False
    config = _get_config()
    if not config:
        return False
    try:
        from twilio.rest import Client
        client = Client(config["account_sid"], config["auth_token"])
        client.messages.create(
            body=f"Your TableMetrics verification code is: {code}",
            from_=config["from_number"],
            to=phone_number,
        )
        return True
    except Exception:
        return False

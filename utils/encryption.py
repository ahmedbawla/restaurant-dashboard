"""
Symmetric encryption for sensitive credentials stored in the database.
Uses Fernet (AES-128-CBC + HMAC-SHA256).

Setup — generate a key once and add to .streamlit/secrets.toml:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    [encryption]
    key = "the-generated-key-here"
"""

import os

from cryptography.fernet import Fernet


def _get_key() -> bytes:
    # 1. Streamlit secrets (cloud / local)
    try:
        import streamlit as st
        key = st.secrets.get("encryption", {}).get("key", "")
        if key:
            return key.encode() if isinstance(key, str) else key
    except Exception:
        pass
    # 2. Environment variable (GitHub Actions)
    key = os.environ.get("ENCRYPTION_KEY", "")
    if key:
        return key.encode()
    raise RuntimeError(
        "Encryption key not configured. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
        "then add it to .streamlit/secrets.toml under [encryption] key = '...'"
    )


def encrypt(plaintext: str) -> str:
    """Encrypt a plain-text string. Returns a URL-safe base64 token."""
    return Fernet(_get_key()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a token produced by encrypt(). Returns the original string."""
    return Fernet(_get_key()).decrypt(ciphertext.encode()).decode()

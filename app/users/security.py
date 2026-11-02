"""Security utilities for user password hashing and JWT/session tokens.

Uses standard library hashlib.pbkdf2_hmac and hmac to provide cryptographically
strong password hashing without requiring external C-extension libraries.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.core.config import get_settings

PBKDF2_ITERATIONS = 100_000
TOKEN_EXPIRY_SECONDS = 30 * 24 * 3600  # 30 days


def _get_secret_key() -> str:
    s = get_settings()
    # Use database URL or app_name as base salt if dedicated secret not configured
    return getattr(s, "app_secret_key", None) or s.app_name + "_kunal_secret_key_2026"


def hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with a random 16-byte salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"{salt}:{key.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored salt:key hash string."""
    try:
        parts = hashed_password.split(":", 1)
        if len(parts) != 2:
            return False
        salt, expected_hex = parts
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ITERATIONS,
        )
        return hmac.compare_digest(computed.hex(), expected_hex)
    except Exception:
        return False


def create_access_token(user_id: int, username: str, role: str) -> str:
    """Create a signed, base64-encoded bearer token."""
    payload: dict[str, Any] = {
        "user_id": user_id,
        "username": username.strip().lower(),
        "role": role,
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
        "nonce": secrets.token_hex(4),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
    
    secret = _get_secret_key().encode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a signed bearer token, returning its payload dict or None."""
    if not token or "." not in token:
        return None
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        
        # Verify signature
        secret = _get_secret_key().encode("utf-8")
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        
        # Add padding back if necessary
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
        
        if not isinstance(payload, dict):
            return None
            
        exp = payload.get("exp")
        if exp and exp < time.time():
            return None
            
        return payload
    except Exception:
        return None

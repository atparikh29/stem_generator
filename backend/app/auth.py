"""Password hashing for username/password login.

Uses PBKDF2-HMAC-SHA256 from the standard library (no extra dependency, offline).
Passwords are never stored in plaintext; only a salted, iterated hash is kept.
Stored format: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(dk.hex(), expected)  # constant-time compare
    except (ValueError, AttributeError):
        return False


def new_reset_token() -> str:
    """A short-lived, URL-safe secret for a password reset. Only its hash (via
    hash_password) is persisted; the raw token is shown to the user once."""
    return secrets.token_urlsafe(24)

"""
JWT access token creation and verification.

INVARIANTS:
  - tokens contain only: sub (username), user_id, exp — no password_hash, no secrets
  - expired tokens raise TokenExpiredError (subclass of TokenError)
  - malformed tokens raise TokenError
  - the secret key is never included in token payloads or error messages
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from backend.core.config import settings


class TokenError(Exception):
    """Token is invalid, malformed, or cannot be verified."""


class TokenExpiredError(TokenError):
    """Token is structurally valid but past its expiry."""


def create_access_token(*, username: str, user_id: str) -> str:
    """Return a signed JWT for the given user identity."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": username,
        "user_id": user_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode and verify *token*.

    Returns the payload dict on success.
    Raises TokenExpiredError if expired, TokenError for any other failure.
    """
    try:
        return jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=[settings.auth_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid access token") from exc

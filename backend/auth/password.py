"""
Password hashing and verification using bcrypt.

INVARIANTS:
  - plaintext passwords MUST NOT be logged, stored, or propagated
  - hash_password() always returns a fresh bcrypt hash (never deterministic)
  - verify_password() is timing-safe via bcrypt's constant-time compare
"""
from __future__ import annotations

import bcrypt


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash of *plaintext*. Never store or log the input."""
    if not plaintext:
        raise ValueError("Password must not be empty")
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True iff *plaintext* matches *hashed*. Timing-safe."""
    if not plaintext or not hashed:
        return False
    return bcrypt.checkpw(plaintext.encode(), hashed.encode())

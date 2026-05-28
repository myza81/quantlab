"""
Vault secret encryption/decryption using Fernet (AES-128-CBC + HMAC-SHA256).

INVARIANTS:
  - raw secret values exist only transiently during encrypt/decrypt calls
  - raw secrets must never appear in repr, str, logs, or exception messages
  - the encryption key is derived from settings.vault_encryption_key via SHA-256
  - a fresh IV is generated on every encrypt call (non-deterministic ciphertext)
  - decryption failure raises VaultCryptoError — message never contains secret value
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import settings


class VaultCryptoError(Exception):
    """Encryption or decryption failure. Message never contains secret material."""


def _derive_fernet_key(raw_key: str) -> bytes:
    """Derive a 32-byte Fernet-compatible key from an arbitrary string via SHA-256."""
    digest = hashlib.sha256(raw_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    key = _derive_fernet_key(settings.vault_encryption_key)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """
    Encrypt *plaintext* with the vault key.

    Returns a URL-safe base64-encoded Fernet token (safe to store in JSON).
    The return value is the ciphertext — it is safe to store but must not be
    included in API responses or logs.
    """
    if not plaintext:
        raise VaultCryptoError("Cannot encrypt an empty secret")
    try:
        token = _get_fernet().encrypt(plaintext.encode())
        return token.decode()
    except Exception as exc:
        raise VaultCryptoError("Encryption failed") from exc


def decrypt_secret(ciphertext: str) -> str:
    """
    Decrypt *ciphertext* with the vault key.

    Returns the plaintext secret string.

    INVARIANT: never log, print, or propagate the return value.
    """
    if not ciphertext:
        raise VaultCryptoError("Cannot decrypt an empty ciphertext")
    try:
        plaintext = _get_fernet().decrypt(ciphertext.encode())
        return plaintext.decode()
    except InvalidToken as exc:
        raise VaultCryptoError(
            "Decryption failed: token invalid or vault key mismatch"
        ) from exc
    except Exception as exc:
        raise VaultCryptoError("Decryption failed") from exc

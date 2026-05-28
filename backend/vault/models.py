"""
ProviderCredential domain model — user-owned provider API credential record.

INVARIANTS:
  - `encrypted_secret` stores only ciphertext produced by vault/crypto.py
  - raw secret values must NEVER be stored in this model
  - `to_dict()` serializes encrypted_secret only — never plaintext
  - `__repr__` and `__str__` must not expose encrypted_secret
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass(frozen=True)
class ProviderCredential:
    credential_id: str
    user_id: str
    provider_name: str
    credential_label: str
    encrypted_secret: str   # Fernet ciphertext — never expose raw value
    active: bool
    created_at: str         # UTC ISO-8601
    updated_at: str         # UTC ISO-8601

    def __repr__(self) -> str:
        return (
            f"ProviderCredential(credential_id={self.credential_id!r}, "
            f"user_id={self.user_id!r}, provider_name={self.provider_name!r}, "
            f"credential_label={self.credential_label!r}, active={self.active})"
        )

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        provider_name: str,
        credential_label: str,
        encrypted_secret: str,
    ) -> "ProviderCredential":
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            credential_id=str(uuid.uuid4()),
            user_id=user_id,
            provider_name=provider_name.strip().lower(),
            credential_label=credential_label.strip(),
            encrypted_secret=encrypted_secret,
            active=True,
            created_at=now,
            updated_at=now,
        )

    def with_active(self, active: bool) -> "ProviderCredential":
        """Return a new instance with `active` set to *active* and `updated_at` refreshed."""
        now = datetime.now(timezone.utc).isoformat()
        return ProviderCredential(
            credential_id=self.credential_id,
            user_id=self.user_id,
            provider_name=self.provider_name,
            credential_label=self.credential_label,
            encrypted_secret=self.encrypted_secret,
            active=active,
            created_at=self.created_at,
            updated_at=now,
        )

    def to_dict(self) -> dict:
        return {
            "credential_id": self.credential_id,
            "user_id": self.user_id,
            "provider_name": self.provider_name,
            "credential_label": self.credential_label,
            "encrypted_secret": self.encrypted_secret,
            "active": self.active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderCredential":
        return cls(
            credential_id=data["credential_id"],
            user_id=data["user_id"],
            provider_name=data["provider_name"],
            credential_label=data["credential_label"],
            encrypted_secret=data["encrypted_secret"],
            active=data["active"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

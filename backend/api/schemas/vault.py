"""
Vault API schemas — request/response models for provider credential endpoints.

INVARIANTS:
  - encrypted_secret and raw secret values are NEVER included in any response schema
  - secret_value is write-only (registration request only, never returned)
  - all response schemas expose metadata only
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class RegisterCredentialRequest(BaseModel):
    provider_name: str
    credential_label: str
    secret_value: str   # write-only — never appears in any response

    @field_validator("provider_name")
    @classmethod
    def provider_name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("provider_name must not be empty")
        return v.strip().lower()

    @field_validator("credential_label")
    @classmethod
    def label_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("credential_label must not be empty")
        return v.strip()

    @field_validator("secret_value")
    @classmethod
    def secret_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("secret_value must not be empty")
        return v  # do NOT strip — preserve exact secret


class CredentialMetadataResponse(BaseModel):
    credential_id: str
    provider_name: str
    credential_label: str
    active: bool
    created_at: str
    updated_at: str
    # user_id intentionally omitted — the authenticated user already knows their identity
    # encrypted_secret intentionally omitted — raw secrets must never leave the vault


class CredentialListResponse(BaseModel):
    credentials: list[CredentialMetadataResponse]
    total: int

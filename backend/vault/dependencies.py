"""
FastAPI dependency factory for VaultService.

Kept separate so tests can override via Depends() without touching service logic.
"""
from __future__ import annotations

from fastapi import Depends

from backend.core.config import settings
from backend.vault.repository import CredentialRepository
from backend.vault.service import VaultService


def get_credential_repository() -> CredentialRepository:
    return CredentialRepository(settings.credentials_file_path)


def get_vault_service(
    repo: CredentialRepository = Depends(get_credential_repository),
) -> VaultService:
    return VaultService(repo)

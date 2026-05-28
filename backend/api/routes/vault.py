"""
Provider credential vault routes.

All endpoints require an authenticated user (via get_current_user).
No endpoint exposes raw secret values — responses contain metadata only.

Routes:
  POST   /provider-credentials                         — register new credential
  GET    /provider-credentials                         — list own credentials
  GET    /provider-credentials/{credential_id}         — get own credential metadata
  PATCH  /provider-credentials/{credential_id}/disable — disable credential
  DELETE /provider-credentials/{credential_id}         — delete credential
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.schemas.vault import (
    CredentialListResponse,
    CredentialMetadataResponse,
    RegisterCredentialRequest,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.vault.dependencies import get_vault_service
from backend.vault.models import ProviderCredential
from backend.vault.service import (
    CredentialAccessDeniedError,
    CredentialRegistrationError,
    VaultService,
)

router = APIRouter(prefix="/provider-credentials", tags=["vault"])


def _to_response(c: ProviderCredential) -> CredentialMetadataResponse:
    return CredentialMetadataResponse(
        credential_id=c.credential_id,
        provider_name=c.provider_name,
        credential_label=c.credential_label,
        active=c.active,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.post("", response_model=CredentialMetadataResponse, status_code=status.HTTP_201_CREATED)
def register_credential(
    body: RegisterCredentialRequest,
    current_user: User = Depends(require_active_subscription),
    service: VaultService = Depends(get_vault_service),
) -> CredentialMetadataResponse:
    try:
        credential = service.register_credential(
            user_id=current_user.user_id,
            provider_name=body.provider_name,
            credential_label=body.credential_label,
            raw_secret=body.secret_value,
        )
    except CredentialRegistrationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _to_response(credential)


@router.get("", response_model=CredentialListResponse)
def list_credentials(
    current_user: User = Depends(require_active_subscription),
    service: VaultService = Depends(get_vault_service),
) -> CredentialListResponse:
    credentials = service.list_credentials(user_id=current_user.user_id)
    return CredentialListResponse(
        credentials=[_to_response(c) for c in credentials],
        total=len(credentials),
    )


@router.get("/{credential_id}", response_model=CredentialMetadataResponse)
def get_credential(
    credential_id: str,
    current_user: User = Depends(require_active_subscription),
    service: VaultService = Depends(get_vault_service),
) -> CredentialMetadataResponse:
    try:
        credential = service.get_credential(
            credential_id=credential_id,
            requesting_user_id=current_user.user_id,
        )
    except CredentialAccessDeniedError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    return _to_response(credential)


@router.patch("/{credential_id}/disable", response_model=CredentialMetadataResponse)
def disable_credential(
    credential_id: str,
    current_user: User = Depends(require_active_subscription),
    service: VaultService = Depends(get_vault_service),
) -> CredentialMetadataResponse:
    try:
        credential = service.disable_credential(
            credential_id=credential_id,
            requesting_user_id=current_user.user_id,
        )
    except CredentialAccessDeniedError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    return _to_response(credential)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    credential_id: str,
    current_user: User = Depends(require_active_subscription),
    service: VaultService = Depends(get_vault_service),
) -> None:
    try:
        service.delete_credential(
            credential_id=credential_id,
            requesting_user_id=current_user.user_id,
        )
    except CredentialAccessDeniedError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

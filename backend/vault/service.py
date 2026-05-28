"""
VaultService — application-layer credential vault logic.

Orchestrates: CredentialRepository + crypto + audit events.

INVARIANTS:
  - raw secret values exist only transiently within register_credential()
    and resolve_secret(); they are never stored in instance state
  - all service methods scope by user_id; cross-user access raises
    CredentialAccessDeniedError with a generic message (information hiding)
  - CredentialAccessDeniedError is returned for BOTH not-found AND wrong-owner
    so callers cannot enumerate whether a credential_id exists for another user
  - audit events NEVER include raw secret values
"""
from __future__ import annotations

from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.vault.crypto import VaultCryptoError, decrypt_secret, encrypt_secret
from backend.vault.models import ProviderCredential
from backend.vault.repository import CredentialRepository


# ---------------------------------------------------------------------------
# Vault errors
# ---------------------------------------------------------------------------

class VaultError(Exception):
    """Base vault error."""


class CredentialAccessDeniedError(VaultError):
    """
    Credential not found OR requesting user is not the owner.
    Intentionally generic message — callers cannot distinguish between
    not-found and wrong-owner.
    """


class CredentialDisabledError(VaultError):
    """Credential exists but is not active."""


class CredentialProviderMismatchError(VaultError):
    """Credential is registered to a different provider than requested."""


class CredentialRegistrationError(VaultError):
    """Credential registration failed due to validation or other error."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class VaultService:
    def __init__(self, repository: CredentialRepository) -> None:
        self._repo = repository

    def register_credential(
        self,
        *,
        user_id: str,
        provider_name: str,
        credential_label: str,
        raw_secret: str,
    ) -> ProviderCredential:
        """
        Register a new provider credential for *user_id*.

        *raw_secret* is encrypted before any persistence call; the plaintext
        value is never stored in the model or repository.

        Returns a ProviderCredential with only metadata (no raw secret).
        """
        provider_name = provider_name.strip().lower()
        credential_label = credential_label.strip()

        if not provider_name:
            raise CredentialRegistrationError("provider_name must not be empty")
        if not credential_label:
            raise CredentialRegistrationError("credential_label must not be empty")
        if not raw_secret:
            raise CredentialRegistrationError("secret_value must not be empty")

        try:
            encrypted = encrypt_secret(raw_secret)
        except VaultCryptoError as exc:
            raise CredentialRegistrationError("Failed to protect credential") from exc

        credential = ProviderCredential.create(
            user_id=user_id,
            provider_name=provider_name,
            credential_label=credential_label,
            encrypted_secret=encrypted,
        )
        self._repo.save(credential)

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.VAULT_CREDENTIAL_REGISTERED,
            details={
                "user_id": user_id,
                "credential_id": credential.credential_id,
                "provider_name": provider_name,
            },
        ))
        return credential

    def list_credentials(self, *, user_id: str) -> list[ProviderCredential]:
        """Return all credentials owned by *user_id* (metadata only)."""
        records = self._repo.list_by_user(user_id)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.VAULT_CREDENTIAL_LISTED,
            details={"user_id": user_id, "count": len(records)},
        ))
        return records

    def get_credential(self, *, credential_id: str, requesting_user_id: str) -> ProviderCredential:
        """
        Return credential metadata for *credential_id*.

        Raises CredentialAccessDeniedError if not found or wrong owner.
        """
        credential = self._repo.get_by_id(credential_id)
        if credential is None or credential.user_id != requesting_user_id:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.VAULT_CREDENTIAL_ACCESS_DENIED,
                details={"user_id": requesting_user_id, "credential_id": credential_id},
            ))
            raise CredentialAccessDeniedError("Credential not found or access denied")
        return credential

    def disable_credential(
        self, *, credential_id: str, requesting_user_id: str
    ) -> ProviderCredential:
        """
        Mark credential as inactive.

        Raises CredentialAccessDeniedError if not found or wrong owner.
        """
        credential = self._repo.get_by_id(credential_id)
        if credential is None or credential.user_id != requesting_user_id:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.VAULT_CREDENTIAL_ACCESS_DENIED,
                details={"user_id": requesting_user_id, "credential_id": credential_id},
            ))
            raise CredentialAccessDeniedError("Credential not found or access denied")
        updated = credential.with_active(False)
        self._repo.update(updated)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.VAULT_CREDENTIAL_DISABLED,
            details={
                "user_id": requesting_user_id,
                "credential_id": credential_id,
                "provider_name": credential.provider_name,
            },
        ))
        return updated

    def delete_credential(self, *, credential_id: str, requesting_user_id: str) -> None:
        """
        Permanently delete a credential.

        Raises CredentialAccessDeniedError if not found or wrong owner.
        """
        credential = self._repo.get_by_id(credential_id)
        if credential is None or credential.user_id != requesting_user_id:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.VAULT_CREDENTIAL_ACCESS_DENIED,
                details={"user_id": requesting_user_id, "credential_id": credential_id},
            ))
            raise CredentialAccessDeniedError("Credential not found or access denied")
        self._repo.delete(credential_id)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.VAULT_CREDENTIAL_DELETED,
            details={
                "user_id": requesting_user_id,
                "credential_id": credential_id,
                "provider_name": credential.provider_name,
            },
        ))

    def resolve_secret(
        self,
        *,
        credential_id: str,
        requesting_user_id: str,
        provider_name: str,
    ) -> str:
        """
        Resolve and return the raw decrypted secret for internal provider use.

        INVARIANT: the return value is the raw secret string — caller must not
        log, propagate to API responses, or store it.

        Raises:
            CredentialAccessDeniedError — not found or wrong owner
            CredentialDisabledError — credential is inactive
            CredentialProviderMismatchError — credential belongs to a different provider
            VaultCryptoError — decryption failure
        """
        credential = self._repo.get_by_id(credential_id)
        if credential is None or credential.user_id != requesting_user_id:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.VAULT_CREDENTIAL_ACCESS_DENIED,
                details={"user_id": requesting_user_id, "credential_id": credential_id},
            ))
            raise CredentialAccessDeniedError("Credential not found or access denied")

        if not credential.active:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.VAULT_CREDENTIAL_RESOLUTION_FAILED,
                details={
                    "user_id": requesting_user_id,
                    "credential_id": credential_id,
                    "reason": "disabled",
                },
            ))
            raise CredentialDisabledError("Credential is disabled")

        if credential.provider_name != provider_name.strip().lower():
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.VAULT_CREDENTIAL_RESOLUTION_FAILED,
                details={
                    "user_id": requesting_user_id,
                    "credential_id": credential_id,
                    "reason": "provider_mismatch",
                },
            ))
            raise CredentialProviderMismatchError(
                "Credential is registered for a different provider"
            )

        try:
            raw_secret = decrypt_secret(credential.encrypted_secret)
        except VaultCryptoError:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.VAULT_CREDENTIAL_RESOLUTION_FAILED,
                details={
                    "user_id": requesting_user_id,
                    "credential_id": credential_id,
                    "reason": "decryption_failure",
                },
            ))
            raise

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.VAULT_CREDENTIAL_RESOLVED,
            details={
                "user_id": requesting_user_id,
                "credential_id": credential_id,
                "provider_name": credential.provider_name,
            },
        ))
        return raw_secret

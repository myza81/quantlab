"""
Provider credential contract — backend-only.

Defines the contract for provider credentials and a simple environment-based
resolver.  Raw secret values must never leave this module:

  - never in exception messages visible to API callers
  - never in structured log output
  - never in API schemas or response bodies
  - never in dataset catalog storage
  - never accessible from strategy modules

Usage pattern (future external provider adapters):

    from backend.core.credentials import CredentialSpec, EnvironmentCredentialResolver

    _SPEC = CredentialSpec(
        provider_name="binance",
        credential_key="BINANCE_API_KEY",
        description="Binance REST API key for market data",
    )
    _RESOLVER = EnvironmentCredentialResolver()

    # Inside provider adapter __init__ or build():
    api_key = _RESOLVER.resolve(_SPEC)  # raises MissingCredentialError if absent

The resolved string is the raw secret — keep it private.
"""
from __future__ import annotations

import logging
import os
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Credential source types
# ---------------------------------------------------------------------------

class CredentialSource(str, Enum):
    """Where a credential is read from."""
    ENV_VAR = "env_var"
    VAULT = "vault"  # Phase 3I+ — user-owned credential vault


# ---------------------------------------------------------------------------
# Credential specification
# ---------------------------------------------------------------------------

class CredentialSpec(BaseModel):
    """
    Immutable descriptor for a provider credential.

    `credential_key` is the name of the environment variable (not its value).
    The spec is safe to log, serialize, or pass around — it contains no secrets.
    """
    model_config = ConfigDict(frozen=True)

    provider_name: str
    credential_key: str      # env var name — NOT the secret value
    source_type: CredentialSource = CredentialSource.ENV_VAR
    description: str = ""    # human-readable context, e.g. "Binance API key"

    @field_validator("provider_name", "credential_key")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace")
        return stripped


# ---------------------------------------------------------------------------
# Error hierarchy — safe messages only
# ---------------------------------------------------------------------------

class CredentialResolutionError(Exception):
    """
    Base error for all credential resolution failures.

    INVARIANT: messages must NEVER contain raw secret values.
    """


class MissingCredentialError(CredentialResolutionError):
    """
    A required provider credential is not present in the environment.

    The message is intentionally vague — it does not reveal which environment
    variable is missing or what value was expected.
    """


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class EnvironmentCredentialResolver:
    """
    Resolves a CredentialSpec to its secret value from environment variables.

    The caller receives the raw secret string and is responsible for keeping
    it private (not logging it, not passing it to API layers, etc.).

    Raises MissingCredentialError — never ValueError — so callers can
    distinguish "not configured" from "wrong arguments."
    """

    def resolve(self, spec: CredentialSpec) -> str:
        """
        Read and return the credential value.

        Emits audit events for both the resolution attempt and any failure.
        Never includes the secret value in logs or exception messages.

        Args:
            spec: CredentialSpec describing which env var to read.

        Returns:
            The raw secret string.

        Raises:
            MissingCredentialError: env var not set or empty.
        """
        from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.CREDENTIAL_RESOLUTION_ATTEMPT,
            provider_name=spec.provider_name,
            details={"source_type": spec.source_type.value},
        ))

        value = os.environ.get(spec.credential_key)
        if not value:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.CREDENTIAL_MISSING,
                provider_name=spec.provider_name,
                details={"source_type": spec.source_type.value},
            ))
            logger.warning(
                "credentials: missing credential for provider '%s' (source_type=%s)",
                spec.provider_name,
                spec.source_type.value,
            )
            raise MissingCredentialError(
                f"Provider '{spec.provider_name}' requires credentials that are not "
                "configured. Set the required environment variable and restart the service."
            )

        logger.debug(
            "credentials: resolved credential for provider '%s'", spec.provider_name
        )
        return value

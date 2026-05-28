"""
Lightweight audit event logging for security-sensitive actions.

Emits structured JSON log records to the "quantlab.audit" logger.
Any log handler attached to that logger (file, stdout, SIEM) receives
the events.

CRITICAL — audit records MUST NOT contain:
  - raw API keys, tokens, or credentials
  - raw filesystem paths (catalog_id is the safe reference)
  - user session data not relevant to the event

Intended consumers: future audit storage, SIEM integration, monitoring.
For now, records flow through Python's standard logging infrastructure.

Usage:

    from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event

    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.DATASET_REGISTERED,
        provider_name="csv",
        details={"catalog_id": entry.catalog_id, "symbol": entry.symbol},
    ))
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

_AUDIT_LOGGER = logging.getLogger("quantlab.audit")


# ---------------------------------------------------------------------------
# Event kinds
# ---------------------------------------------------------------------------

class AuditEventKind(str, Enum):
    """Enumeration of security-relevant actions that produce audit records."""
    CREDENTIAL_RESOLUTION_ATTEMPT = "credential_resolution_attempt"
    CREDENTIAL_MISSING = "credential_missing"
    DATASET_REGISTERED = "dataset_registered"
    DATASET_REMOVED = "dataset_removed"
    PROVIDER_FETCH_REQUEST = "provider_fetch_request"
    CATALOG_OHLCV_FETCH = "catalog_ohlcv_fetch"
    # Auth events
    USER_REGISTERED = "user_registered"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    INVALID_TOKEN = "invalid_token"
    PROTECTED_ROUTE_DENIED = "protected_route_denied"
    # Vault events
    VAULT_CREDENTIAL_REGISTERED = "vault_credential_registered"
    VAULT_CREDENTIAL_RESOLVED = "vault_credential_resolved"
    VAULT_CREDENTIAL_LISTED = "vault_credential_listed"
    VAULT_CREDENTIAL_DISABLED = "vault_credential_disabled"
    VAULT_CREDENTIAL_DELETED = "vault_credential_deleted"
    VAULT_CREDENTIAL_ACCESS_DENIED = "vault_credential_access_denied"
    VAULT_CREDENTIAL_RESOLUTION_FAILED = "vault_credential_resolution_failed"
    # Phase 3L — ownership
    DRAFT_CREATED = "draft_created"
    DRAFT_UPDATED = "draft_updated"
    DRAFT_DELETED = "draft_deleted"
    DRAFT_ARCHIVED = "draft_archived"
    DRAFT_OWNERSHIP_DENIED = "draft_ownership_denied"
    DATASET_OWNERSHIP_DENIED = "dataset_ownership_denied"
    BACKTEST_OWNERSHIP_DENIED = "backtest_ownership_denied"
    # Phase 3P-A — subscription / entitlement
    USER_APPROVED = "user_approved"
    SUBSCRIPTION_ACTIVATED = "subscription_activated"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    SUBSCRIPTION_SUSPENDED = "subscription_suspended"
    ENTITLEMENT_DENIED = "entitlement_denied"


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEvent:
    """
    Immutable audit record.

    `details` must contain only safe metadata — no paths, secrets, or tokens.
    `provider_name` is safe (it is a registered provider id like "csv", "yahoo").
    """
    event_kind: AuditEventKind
    provider_name: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------

def emit_audit_event(event: AuditEvent) -> None:
    """
    Emit a structured audit record to the "quantlab.audit" logger at INFO level.

    Never call this function with raw secret values inside `details`.
    Use catalog_id, provider_name, symbol, asset_class — never file_path or api_key.
    """
    record = {
        "audit_event": event.event_kind.value,
        "provider": event.provider_name,
        "timestamp": event.timestamp.isoformat(),
    }
    record.update(event.details)
    _AUDIT_LOGGER.info(json.dumps(record))

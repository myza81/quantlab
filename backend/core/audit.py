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
    # Phase 3P-B.1 — governance safety
    EXPIRY_UPDATED = "expiry_updated"
    ADMIN_SELF_SUSPENSION_DENIED = "admin_self_suspension_denied"
    LAST_ADMIN_SUSPENSION_DENIED = "last_admin_suspension_denied"
    # Phase 3P-D — superadmin & role management
    ROLE_PROMOTED = "role_promoted"
    ROLE_DEMOTED = "role_demoted"
    LAST_SUPERADMIN_PROTECTION_DENIED = "last_superadmin_protection_denied"
    UNAUTHORIZED_ROLE_CHANGE_ATTEMPT = "unauthorized_role_change_attempt"
    # Phase 3S-B — hardening
    OVERSIZED_PAYLOAD_REJECTED = "oversized_payload_rejected"
    LIFECYCLE_TRANSITION_DENIED = "lifecycle_transition_denied"
    POLYGON_ENV_FALLBACK_USED = "polygon_env_fallback_used"
    # Phase 4C.2 — Forward Testing session lifecycle events (FT_)
    # Taxonomy defined in docs/EXECUTION_AUDIT_MODEL.md §5.
    # Events are defined here for taxonomy completeness; emission is Phase 4C.4.
    FT_SESSION_CREATED              = "ft_session_created"
    FT_SESSION_ACTIVATED            = "ft_session_activated"
    FT_ACTIVATION_DENIED            = "ft_activation_denied"
    FT_SESSION_PAUSED               = "ft_session_paused"
    FT_SESSION_PAUSED_PROVIDER_FAILURE = "ft_session_paused_provider_failure"
    FT_SESSION_RESUMED              = "ft_session_resumed"
    FT_SESSION_COMPLETED            = "ft_session_completed"
    FT_SESSION_FAILED               = "ft_session_failed"
    FT_SESSION_TERMINATED           = "ft_session_terminated"
    FT_INVALID_TRANSITION_DENIED    = "ft_invalid_transition_denied"
    FT_SIGNAL_GENERATED             = "ft_signal_generated"
    FT_SIGNAL_SUPPRESSED            = "ft_signal_suppressed"
    FT_POLL_COMPLETED               = "ft_poll_completed"
    FT_PROVIDER_FAILURE             = "ft_provider_failure"
    FT_GAP_DETECTED                 = "ft_gap_detected"
    FT_CATCHUP_STARTED              = "ft_catchup_started"
    FT_CATCHUP_THRESHOLD_EXCEEDED   = "ft_catchup_threshold_exceeded"
    FT_SESSION_EXPORTED             = "ft_session_exported"
    FT_SESSION_REVIEWED             = "ft_session_reviewed"
    # Phase 4C.2 — Governance promotion events (GOV_)
    # Taxonomy defined in docs/EXECUTION_AUDIT_MODEL.md §8.
    # Note: GOV_LIFECYCLE_TRANSITION_DENIED is the taxonomy-correct name for
    #       LIFECYCLE_TRANSITION_DENIED (kept above for backward compatibility).
    GOV_PROMOTION_REQUESTED         = "gov_promotion_requested"
    GOV_PROMOTION_REVIEW_STARTED    = "gov_promotion_review_started"
    GOV_PROMOTION_APPROVED          = "gov_promotion_approved"
    GOV_PROMOTION_REJECTED          = "gov_promotion_rejected"
    GOV_PROMOTION_REVOKED           = "gov_promotion_revoked"
    GOV_SESSION_REVIEWED            = "gov_session_reviewed"
    GOV_STRATEGY_APPROVED_FOR_PAPER = "gov_strategy_approved_for_paper"
    GOV_STRATEGY_APPROVED_FOR_LIVE  = "gov_strategy_approved_for_live"
    GOV_LIFECYCLE_TRANSITION_DENIED = "gov_lifecycle_transition_denied"
    # Phase 4E.1 — Paper Trading session lifecycle events (PT_)
    # Taxonomy defined in docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md §12.
    # Session lifecycle (10)
    PT_SESSION_CREATED                  = "pt_session_created"
    PT_SESSION_ACTIVATED                = "pt_session_activated"
    PT_SESSION_PAUSED                   = "pt_session_paused"
    PT_SESSION_PAUSED_DRAWDOWN_STOP     = "pt_session_paused_drawdown_stop"
    PT_SESSION_PAUSED_PROVIDER_FAILURE  = "pt_session_paused_provider_failure"
    PT_SESSION_RESUMED                  = "pt_session_resumed"
    PT_SESSION_COMPLETED                = "pt_session_completed"
    PT_SESSION_FAILED                   = "pt_session_failed"
    PT_SESSION_TERMINATED               = "pt_session_terminated"
    PT_SESSION_INVALID_TRANSITION_DENIED = "pt_session_invalid_transition_denied"
    # Activation gate (2)
    PT_ACTIVATION_DENIED                = "pt_activation_denied"
    PT_ACTIVATION_APPROVED              = "pt_activation_approved"
    # Order lifecycle (3)
    PT_ORDER_CREATED                    = "pt_order_created"
    PT_ORDER_REJECTED                   = "pt_order_rejected"
    PT_ORDER_CANCELLED                  = "pt_order_cancelled"
    # Fill (1)
    PT_FILL_GENERATED                   = "pt_fill_generated"
    # Position (4)
    PT_POSITION_OPENED                  = "pt_position_opened"
    PT_POSITION_SCALED                  = "pt_position_scaled"
    PT_POSITION_CLOSED                  = "pt_position_closed"
    PT_POSITION_FORCE_CLOSED            = "pt_position_force_closed"
    # Account (3)
    PT_ACCOUNT_UPDATED                  = "pt_account_updated"
    PT_DRAWDOWN_THRESHOLD_WARNING       = "pt_drawdown_threshold_warning"
    PT_DRAWDOWN_STOP_TRIGGERED          = "pt_drawdown_stop_triggered"
    # Data / polling (5)
    PT_POLL_COMPLETED                   = "pt_poll_completed"
    PT_PROVIDER_FAILURE                 = "pt_provider_failure"
    PT_GAP_DETECTED                     = "pt_gap_detected"
    PT_CATCHUP_STARTED                  = "pt_catchup_started"
    PT_CATCHUP_THRESHOLD_EXCEEDED       = "pt_catchup_threshold_exceeded"
    # Access / governance (2)
    PT_SESSION_EXPORTED                 = "pt_session_exported"
    PT_SESSION_REVIEWED                 = "pt_session_reviewed"


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEvent:
    """
    Immutable audit record.

    `details` must contain only safe metadata — no paths, secrets, or tokens.
    `provider_name` is safe (it is a registered provider id like "csv", "yahoo").
    `correlation_id` links related execution events (signal → order → fill →
    position → account update).  Optional; safe to omit for non-execution events.
    Must not contain secrets or filesystem paths.
    """
    event_kind: AuditEventKind
    provider_name: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    correlation_id: str | None = None


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
    if event.correlation_id is not None:
        record["correlation_id"] = event.correlation_id
    record.update(event.details)
    _AUDIT_LOGGER.info(json.dumps(record))

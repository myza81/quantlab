"""
Tests for Phase 4C.2 — Forward Testing Lifecycle & Audit Taxonomy Integration.

Covers:
  Lifecycle:
    - forward_tested state exists in StrategyLifecycleStatus
    - canonical path: backtested → forward_tested → paper_tested
    - backtested → forward_tested is valid
    - forward_tested → paper_tested is valid
    - forward_tested → backtested (rollback) is valid
    - forward_tested → archived is valid
    - forward_tested cannot skip to approved_for_live
    - forward_tested cannot regress to draft or validated
    - archived remains terminal (forward_tested included)
    - draft cannot shortcut to forward_tested
    - validated cannot shortcut to forward_tested
    - Option B: backtested → paper_tested still allowed (deprecated transitional)

  Audit taxonomy:
    - All FT_* event kinds defined
    - All GOV_* event kinds defined
    - Existing pre-4C.2 event kinds still present (no removals)

  correlation_id on AuditEvent:
    - AuditEvent accepts optional correlation_id
    - correlation_id absent by default (backward-compatible)
    - correlation_id serializes in emitted JSON when present
    - correlation_id absent from emitted JSON when not set
    - existing emit_audit_event() call style (no correlation_id) still works

  ForwardTestSession status vocabulary:
    - ForwardTestSessionStatus values cover both the implementation naming
      and the architecture vocabulary mapping
"""
from __future__ import annotations

import json
import logging

import pytest

from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.forward_testing.models import ForwardTestSessionStatus
from backend.strategy_registry.lifecycle import (
    StrategyLifecycleStatus,
    validate_lifecycle_transition,
)

S = StrategyLifecycleStatus


# ---------------------------------------------------------------------------
# Lifecycle — forward_tested state
# ---------------------------------------------------------------------------

class TestForwardTestedStateExists:
    def test_forward_tested_member_exists(self) -> None:
        assert S.FORWARD_TESTED == "forward_tested"

    def test_forward_tested_is_str_enum(self) -> None:
        assert isinstance(S.FORWARD_TESTED, str)
        assert S.FORWARD_TESTED.value == "forward_tested"

    def test_forward_tested_in_all_statuses(self) -> None:
        assert S.FORWARD_TESTED in list(S)


# ---------------------------------------------------------------------------
# Lifecycle — canonical forward-tested path
# ---------------------------------------------------------------------------

class TestForwardTestedTransitions:
    def test_backtested_to_forward_tested_is_valid(self) -> None:
        validate_lifecycle_transition(S.BACKTESTED, S.FORWARD_TESTED)

    def test_forward_tested_to_paper_tested_is_valid(self) -> None:
        validate_lifecycle_transition(S.FORWARD_TESTED, S.PAPER_TESTED)

    def test_forward_tested_to_backtested_rollback_is_valid(self) -> None:
        validate_lifecycle_transition(S.FORWARD_TESTED, S.BACKTESTED)

    def test_forward_tested_to_archived_is_valid(self) -> None:
        validate_lifecycle_transition(S.FORWARD_TESTED, S.ARCHIVED)

    def test_forward_tested_noop_is_allowed(self) -> None:
        validate_lifecycle_transition(S.FORWARD_TESTED, S.FORWARD_TESTED)


# ---------------------------------------------------------------------------
# Lifecycle — invalid shortcuts from / to forward_tested
# ---------------------------------------------------------------------------

class TestForwardTestedInvalidTransitions:
    def test_forward_tested_cannot_advance_to_approved_for_live(self) -> None:
        with pytest.raises(ValueError):
            validate_lifecycle_transition(S.FORWARD_TESTED, S.APPROVED_FOR_LIVE)

    def test_forward_tested_cannot_regress_to_draft(self) -> None:
        with pytest.raises(ValueError):
            validate_lifecycle_transition(S.FORWARD_TESTED, S.DRAFT)

    def test_forward_tested_cannot_regress_to_validated(self) -> None:
        with pytest.raises(ValueError):
            validate_lifecycle_transition(S.FORWARD_TESTED, S.VALIDATED)

    def test_draft_cannot_shortcut_to_forward_tested(self) -> None:
        with pytest.raises(ValueError):
            validate_lifecycle_transition(S.DRAFT, S.FORWARD_TESTED)

    def test_validated_cannot_shortcut_to_forward_tested(self) -> None:
        with pytest.raises(ValueError):
            validate_lifecycle_transition(S.VALIDATED, S.FORWARD_TESTED)

    def test_paper_tested_cannot_roll_back_to_forward_tested(self) -> None:
        with pytest.raises(ValueError):
            validate_lifecycle_transition(S.PAPER_TESTED, S.FORWARD_TESTED)

    def test_approved_for_live_cannot_roll_back_to_forward_tested(self) -> None:
        with pytest.raises(ValueError):
            validate_lifecycle_transition(S.APPROVED_FOR_LIVE, S.FORWARD_TESTED)


# ---------------------------------------------------------------------------
# Lifecycle — archived remains terminal (including forward_tested)
# ---------------------------------------------------------------------------

class TestArchivedRemainsTerminalWithForwardTested:
    def test_archived_cannot_reach_forward_tested(self) -> None:
        with pytest.raises(ValueError, match="terminal"):
            validate_lifecycle_transition(S.ARCHIVED, S.FORWARD_TESTED)


# ---------------------------------------------------------------------------
# Lifecycle — Option B: backtested → paper_tested deprecated compat
# ---------------------------------------------------------------------------

class TestBacktestedToPaperTestedDeprecatedCompat:
    def test_backtested_to_paper_tested_still_allowed(self) -> None:
        """
        Option B: backtested → paper_tested remains allowed for backward
        compatibility.  These sessions are exploratory — they do not satisfy
        the PAPER_TESTED promotion gate per docs/STRATEGY_PROMOTION_LIFECYCLE.md §5.
        """
        validate_lifecycle_transition(S.BACKTESTED, S.PAPER_TESTED)

    def test_canonical_path_also_available(self) -> None:
        validate_lifecycle_transition(S.BACKTESTED, S.FORWARD_TESTED)
        validate_lifecycle_transition(S.FORWARD_TESTED, S.PAPER_TESTED)


# ---------------------------------------------------------------------------
# Audit taxonomy — FT_* event kinds
# ---------------------------------------------------------------------------

_REQUIRED_FT_KINDS = {
    "ft_session_created",
    "ft_session_activated",
    "ft_activation_denied",
    "ft_session_paused",
    "ft_session_paused_provider_failure",
    "ft_session_resumed",
    "ft_session_completed",
    "ft_session_failed",
    "ft_session_terminated",
    "ft_invalid_transition_denied",
    "ft_signal_generated",
    "ft_signal_suppressed",
    "ft_poll_completed",
    "ft_provider_failure",
    "ft_gap_detected",
    "ft_catchup_started",
    "ft_catchup_threshold_exceeded",
    "ft_session_exported",
    "ft_session_reviewed",
}

_REQUIRED_GOV_KINDS = {
    "gov_promotion_requested",
    "gov_promotion_review_started",
    "gov_promotion_approved",
    "gov_promotion_rejected",
    "gov_promotion_revoked",
    "gov_session_reviewed",
    "gov_strategy_approved_for_paper",
    "gov_strategy_approved_for_live",
    "gov_lifecycle_transition_denied",
}

_EXISTING_KINDS_SAMPLE = {
    "credential_resolution_attempt",
    "dataset_registered",
    "user_registered",
    "login_success",
    "vault_credential_registered",
    "draft_created",
    "user_approved",
    "oversized_payload_rejected",
    "lifecycle_transition_denied",
    "polygon_env_fallback_used",
}


class TestFTAuditEventKinds:
    def test_all_ft_kinds_present(self) -> None:
        actual = {e.value for e in AuditEventKind}
        missing = _REQUIRED_FT_KINDS - actual
        assert not missing, f"Missing FT_ event kinds: {sorted(missing)}"

    @pytest.mark.parametrize("kind_value", sorted(_REQUIRED_FT_KINDS))
    def test_ft_kind_accessible_by_name(self, kind_value: str) -> None:
        enum_name = kind_value.upper()
        member = AuditEventKind[enum_name]
        assert member.value == kind_value


class TestGOVAuditEventKinds:
    def test_all_gov_kinds_present(self) -> None:
        actual = {e.value for e in AuditEventKind}
        missing = _REQUIRED_GOV_KINDS - actual
        assert not missing, f"Missing GOV_ event kinds: {sorted(missing)}"

    @pytest.mark.parametrize("kind_value", sorted(_REQUIRED_GOV_KINDS))
    def test_gov_kind_accessible_by_name(self, kind_value: str) -> None:
        enum_name = kind_value.upper()
        member = AuditEventKind[enum_name]
        assert member.value == kind_value


class TestExistingEventKindsPreserved:
    @pytest.mark.parametrize("kind_value", sorted(_EXISTING_KINDS_SAMPLE))
    def test_pre_4c2_event_kind_still_present(self, kind_value: str) -> None:
        actual = {e.value for e in AuditEventKind}
        assert kind_value in actual, f"Pre-4C.2 event kind removed: {kind_value!r}"


# ---------------------------------------------------------------------------
# AuditEvent — correlation_id
# ---------------------------------------------------------------------------

class TestAuditEventCorrelationId:
    def test_correlation_id_absent_by_default(self) -> None:
        event = AuditEvent(event_kind=AuditEventKind.FT_SIGNAL_GENERATED)
        assert event.correlation_id is None

    def test_correlation_id_accepted_when_provided(self) -> None:
        cid = "corr-abc-123"
        event = AuditEvent(
            event_kind=AuditEventKind.FT_SIGNAL_GENERATED,
            correlation_id=cid,
        )
        assert event.correlation_id == cid

    def test_existing_call_style_without_correlation_id_still_works(self) -> None:
        event = AuditEvent(
            event_kind=AuditEventKind.DATASET_REGISTERED,
            provider_name="csv",
            details={"catalog_id": "abc"},
        )
        assert event.correlation_id is None
        assert event.event_kind == AuditEventKind.DATASET_REGISTERED

    def test_audit_event_is_still_frozen(self) -> None:
        event = AuditEvent(event_kind=AuditEventKind.FT_SESSION_CREATED)
        with pytest.raises(Exception):
            event.correlation_id = "something"  # type: ignore[misc]

    def test_correlation_id_serializes_in_json_when_present(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        cid = "ft-session-xyz"
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.FT_SESSION_ACTIVATED,
                details={"session_id": "s1"},
                correlation_id=cid,
            ))
        ft_records = [
            r for r in caplog.records if "ft_session_activated" in r.message
        ]
        assert ft_records, "No ft_session_activated log record found"
        parsed = json.loads(ft_records[0].message)
        assert parsed.get("correlation_id") == cid

    def test_correlation_id_absent_from_json_when_not_set(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.DATASET_REGISTERED,
                provider_name="csv",
                details={"catalog_id": "abc"},
            ))
        for record in caplog.records:
            if "dataset_registered" in record.message:
                parsed = json.loads(record.message)
                assert "correlation_id" not in parsed
                break

    def test_existing_emit_audit_event_call_unaffected(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Existing callers that don't pass correlation_id continue to work."""
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.LIFECYCLE_TRANSITION_DENIED,
                details={"strategy_id": "d1", "from": "draft", "to": "approved_for_live"},
            ))
        records = [r for r in caplog.records if "lifecycle_transition_denied" in r.message]
        assert records
        parsed = json.loads(records[0].message)
        assert parsed["audit_event"] == "lifecycle_transition_denied"
        assert "correlation_id" not in parsed


# ---------------------------------------------------------------------------
# ForwardTestSession status vocabulary note
# ---------------------------------------------------------------------------

class TestForwardTestSessionStatusVocabulary:
    """
    Documents the mapping between implementation status names and the
    vocabulary used in architecture documents.

    Architecture docs used:  created, running, paused, stopped, failed, completed
    Implementation uses:     pending, running, paused, terminated, failed, completed

    Mapping:
      pending    = pre-start created state (session exists but not yet activated)
      terminated = user/system stopped final state (forcible stop, distinct from completed)
    """

    def test_pending_exists_as_pre_start_state(self) -> None:
        assert ForwardTestSessionStatus.PENDING == "pending"

    def test_running_exists(self) -> None:
        assert ForwardTestSessionStatus.RUNNING == "running"

    def test_paused_exists(self) -> None:
        assert ForwardTestSessionStatus.PAUSED == "paused"

    def test_completed_exists(self) -> None:
        assert ForwardTestSessionStatus.COMPLETED == "completed"

    def test_failed_exists(self) -> None:
        assert ForwardTestSessionStatus.FAILED == "failed"

    def test_terminated_exists_as_stopped_state(self) -> None:
        """terminated maps to 'stopped' in architecture vocabulary."""
        assert ForwardTestSessionStatus.TERMINATED == "terminated"

    def test_six_statuses_total(self) -> None:
        assert len(list(ForwardTestSessionStatus)) == 6

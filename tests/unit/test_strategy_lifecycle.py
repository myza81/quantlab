"""
Phase 3S-B — Strategy Lifecycle State Machine Tests.

Verifies StrategyLifecycleStatus enum and validate_lifecycle_transition:
    1. Default lifecycle_status on StrategyDraft is DRAFT
    2. Valid transitions succeed (no exception)
    3. Invalid transitions raise ValueError with helpful detail
    4. ARCHIVED is terminal — no transitions allowed
    5. No-op (same → same) is allowed
    6. Serialisation roundtrip preserves lifecycle_status
    7. Schema roundtrip: DraftResponse carries lifecycle_status
"""
from __future__ import annotations

import pytest

from datetime import datetime, timezone

from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.lifecycle import (
    StrategyLifecycleStatus,
    validate_lifecycle_transition,
)
from backend.tools.toolset import StrategyToolSet

_NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)
_EMPTY_TOOLSET = StrategyToolSet(toolset_id="ts-1", tools=())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

S = StrategyLifecycleStatus

_ALL_STATUSES = list(S)

_VALID_TRANSITIONS = [
    (S.DRAFT,             S.VALIDATED),
    (S.DRAFT,             S.ARCHIVED),
    (S.VALIDATED,         S.BACKTESTED),
    (S.VALIDATED,         S.DRAFT),
    (S.VALIDATED,         S.ARCHIVED),
    # canonical path through forward testing
    (S.BACKTESTED,        S.FORWARD_TESTED),
    (S.BACKTESTED,        S.VALIDATED),
    (S.BACKTESTED,        S.ARCHIVED),
    # deprecated transitional: backtested → paper_tested (exploratory, not promotion-eligible)
    (S.BACKTESTED,        S.PAPER_TESTED),
    (S.FORWARD_TESTED,    S.PAPER_TESTED),
    (S.FORWARD_TESTED,    S.BACKTESTED),    # rollback
    (S.FORWARD_TESTED,    S.ARCHIVED),
    (S.PAPER_TESTED,      S.APPROVED_FOR_LIVE),
    (S.PAPER_TESTED,      S.BACKTESTED),
    (S.PAPER_TESTED,      S.ARCHIVED),
    (S.APPROVED_FOR_LIVE, S.ARCHIVED),
]

_INVALID_TRANSITIONS = [
    (S.DRAFT,             S.BACKTESTED),
    (S.DRAFT,             S.FORWARD_TESTED),
    (S.DRAFT,             S.PAPER_TESTED),
    (S.DRAFT,             S.APPROVED_FOR_LIVE),
    (S.VALIDATED,         S.FORWARD_TESTED),
    (S.VALIDATED,         S.PAPER_TESTED),
    (S.VALIDATED,         S.APPROVED_FOR_LIVE),
    (S.BACKTESTED,        S.DRAFT),
    (S.BACKTESTED,        S.APPROVED_FOR_LIVE),
    (S.FORWARD_TESTED,    S.DRAFT),
    (S.FORWARD_TESTED,    S.VALIDATED),
    (S.FORWARD_TESTED,    S.APPROVED_FOR_LIVE),
    (S.PAPER_TESTED,      S.DRAFT),
    (S.PAPER_TESTED,      S.VALIDATED),
    (S.PAPER_TESTED,      S.FORWARD_TESTED),
    (S.APPROVED_FOR_LIVE, S.DRAFT),
    (S.APPROVED_FOR_LIVE, S.VALIDATED),
    (S.APPROVED_FOR_LIVE, S.BACKTESTED),
    (S.APPROVED_FOR_LIVE, S.FORWARD_TESTED),
    (S.APPROVED_FOR_LIVE, S.PAPER_TESTED),
]


def _minimal_draft(**kwargs) -> StrategyDraft:
    defaults = dict(
        draft_id="d1",
        display_name="Test Draft",
        toolset=_EMPTY_TOOLSET,
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kwargs)
    return StrategyDraft(**defaults)


# ---------------------------------------------------------------------------
# Default lifecycle_status
# ---------------------------------------------------------------------------

class TestLifecycleDefault:
    def test_draft_default_is_draft_status(self):
        draft = _minimal_draft()
        assert draft.lifecycle_status == S.DRAFT

    def test_draft_accepts_explicit_status(self):
        draft = _minimal_draft(lifecycle_status=S.VALIDATED)
        assert draft.lifecycle_status == S.VALIDATED


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

class TestValidTransitions:
    @pytest.mark.parametrize("current,target", _VALID_TRANSITIONS)
    def test_valid_transition_does_not_raise(self, current, target):
        validate_lifecycle_transition(current, target)  # must not raise

    @pytest.mark.parametrize("status", _ALL_STATUSES)
    def test_noop_transition_is_allowed(self, status):
        validate_lifecycle_transition(status, status)  # same → same must not raise


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    @pytest.mark.parametrize("current,target", _INVALID_TRANSITIONS)
    def test_invalid_transition_raises_value_error(self, current, target):
        with pytest.raises(ValueError):
            validate_lifecycle_transition(current, target)

    @pytest.mark.parametrize("current,target", _INVALID_TRANSITIONS)
    def test_error_message_mentions_states(self, current, target):
        with pytest.raises(ValueError, match=current.value):
            validate_lifecycle_transition(current, target)


# ---------------------------------------------------------------------------
# ARCHIVED is terminal
# ---------------------------------------------------------------------------

class TestArchivedIsTerminal:
    @pytest.mark.parametrize("target", [s for s in S if s != S.ARCHIVED])
    def test_archived_cannot_transition_to_any_other_state(self, target):
        with pytest.raises(ValueError, match="terminal"):
            validate_lifecycle_transition(S.ARCHIVED, target)

    def test_archived_noop_is_allowed(self):
        validate_lifecycle_transition(S.ARCHIVED, S.ARCHIVED)


# ---------------------------------------------------------------------------
# Serialisation roundtrip
# ---------------------------------------------------------------------------

class TestSerialisation:
    @pytest.mark.parametrize("status", _ALL_STATUSES)
    def test_serialises_to_string_value(self, status):
        assert status.value == status  # str Enum: value equality

    @pytest.mark.parametrize("status", _ALL_STATUSES)
    def test_draft_serialisation_roundtrip(self, status):
        draft = _minimal_draft(lifecycle_status=status)
        data = draft.model_dump()
        assert data["lifecycle_status"] == status.value

    @pytest.mark.parametrize("status", _ALL_STATUSES)
    def test_draft_deserialisation_roundtrip(self, status):
        draft = _minimal_draft(lifecycle_status=status)
        data = draft.model_dump()
        restored = StrategyDraft(**data)
        assert restored.lifecycle_status == status


# ---------------------------------------------------------------------------
# Schema: DraftResponse carries lifecycle_status
# ---------------------------------------------------------------------------

class TestDraftResponseSchema:
    def test_draft_response_has_lifecycle_status_field(self):
        from backend.api.schemas.drafts import DraftResponse
        fields = DraftResponse.model_fields
        assert "lifecycle_status" in fields

    def test_draft_response_default_is_draft(self):
        from backend.api.schemas.drafts import DraftResponse
        field = DraftResponse.model_fields["lifecycle_status"]
        assert field.default == S.DRAFT

    def test_draft_update_request_lifecycle_status_is_absent(self):
        # P0.2: lifecycle_status must NOT be a field on DraftUpdateRequest.
        # Lifecycle transitions are evidence-gated and happen through dedicated
        # service methods only — never through a free PUT body field.
        from backend.api.schemas.drafts import DraftUpdateRequest
        assert "lifecycle_status" not in DraftUpdateRequest.model_fields

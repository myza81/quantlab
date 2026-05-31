"""
Strategy lifecycle state machine — Phase 3S-B / Phase 4C.2.

Defines the valid lifecycle states for a StrategyDraft and the allowed
transitions between them.  Lifecycle is informational metadata only;
it does not gate API access or trigger execution.

Canonical promotion path (Phase 4C.2+):
    draft         → validated
    validated     → backtested, draft, archived
    backtested    → forward_tested, validated, archived
    forward_tested → paper_tested, backtested, archived
    paper_tested  → approved_for_live, backtested, archived
    approved_for_live → archived
    archived      → (terminal — no transitions allowed)

Transitional compatibility note:
    backtested → paper_tested remains allowed for backward compatibility.
    Per docs/STRATEGY_PROMOTION_LIFECYCLE.md §5, paper trading sessions
    conducted before reaching forward_tested are exploratory and do NOT
    satisfy the PAPER_TESTED promotion gate.  The canonical path requires
    backtested → forward_tested → paper_tested.
"""
from __future__ import annotations

from enum import Enum


class StrategyLifecycleStatus(str, Enum):
    DRAFT             = "draft"
    VALIDATED         = "validated"
    BACKTESTED        = "backtested"
    FORWARD_TESTED    = "forward_tested"
    PAPER_TESTED      = "paper_tested"
    APPROVED_FOR_LIVE = "approved_for_live"
    ARCHIVED          = "archived"


# Allowed forward (and safe rollback) transitions per state.
# Empty set = terminal state.
_ALLOWED_TRANSITIONS: dict[StrategyLifecycleStatus, frozenset[StrategyLifecycleStatus]] = {
    StrategyLifecycleStatus.DRAFT: frozenset({
        StrategyLifecycleStatus.VALIDATED,
        StrategyLifecycleStatus.ARCHIVED,
    }),
    StrategyLifecycleStatus.VALIDATED: frozenset({
        StrategyLifecycleStatus.BACKTESTED,
        StrategyLifecycleStatus.DRAFT,
        StrategyLifecycleStatus.ARCHIVED,
    }),
    StrategyLifecycleStatus.BACKTESTED: frozenset({
        StrategyLifecycleStatus.FORWARD_TESTED,    # canonical path
        StrategyLifecycleStatus.PAPER_TESTED,       # deprecated: exploratory only, not promotion-eligible
        StrategyLifecycleStatus.VALIDATED,
        StrategyLifecycleStatus.ARCHIVED,
    }),
    StrategyLifecycleStatus.FORWARD_TESTED: frozenset({
        StrategyLifecycleStatus.PAPER_TESTED,
        StrategyLifecycleStatus.BACKTESTED,         # rollback
        StrategyLifecycleStatus.ARCHIVED,
    }),
    StrategyLifecycleStatus.PAPER_TESTED: frozenset({
        StrategyLifecycleStatus.APPROVED_FOR_LIVE,
        StrategyLifecycleStatus.BACKTESTED,
        StrategyLifecycleStatus.ARCHIVED,
    }),
    StrategyLifecycleStatus.APPROVED_FOR_LIVE: frozenset({
        StrategyLifecycleStatus.ARCHIVED,
    }),
    StrategyLifecycleStatus.ARCHIVED: frozenset(),
}


def validate_lifecycle_transition(
    current: StrategyLifecycleStatus,
    target: StrategyLifecycleStatus,
) -> None:
    """
    Assert that a lifecycle transition from *current* to *target* is permitted.

    Raises:
        ValueError: with a safe message if the transition is not allowed.
    """
    if current == target:
        return
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ValueError(
            f"Lifecycle transition from {current.value!r} to {target.value!r} "
            f"is not permitted. "
            + (
                f"Allowed targets: {sorted(s.value for s in allowed)}"
                if allowed
                else f"State {current.value!r} is terminal — no transitions allowed."
            )
        )

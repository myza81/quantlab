"""
Forward-test promotion evidence assessment — FT-2B.

Provides assess_ft_promotion_readiness() — a pure, stateless function that
evaluates whether a forward-test session has accumulated enough evidence to
be considered promotion-eligible.

Two gates must both pass:
  1. Minimum signal-eligible bars processed.
  2. Minimum distinct UTC calendar dates among those bars.

Both thresholds are configurable through settings.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone

from backend.forward_testing.models import ForwardTestSession
from backend.forward_testing.stores import ForwardTestBarStore


@dataclass(frozen=True)
class FTEvidenceReadiness:
    """
    Result of a forward-test promotion readiness assessment.

    eligible:               True when all gates pass and promotion is allowed.
    eligible_bars:          Number of signal-eligible bars currently processed.
    calendar_days:          Number of distinct UTC dates among those bars.
    min_eligible_bars:      Threshold that must be met.
    min_calendar_days:      Threshold that must be met.
    blocker:                Human-readable reason promotion is blocked, or None
                            when eligible is True.
    """
    eligible:          bool
    eligible_bars:     int
    calendar_days:     int
    min_eligible_bars: int
    min_calendar_days: int
    blocker:           str | None


def assess_ft_promotion_readiness(
    session: ForwardTestSession,
    bar_store: ForwardTestBarStore,
    *,
    min_eligible_bars: int,
    min_calendar_days: int,
) -> FTEvidenceReadiness:
    """
    Evaluate whether a forward-test session has enough evidence for promotion.

    Counts:
      - signal-eligible bars: stored bars with is_warmup_bar=False.
      - calendar days: distinct dates (UTC) of those bars' bar_timestamp values.

    Both counts must reach their respective thresholds for eligible=True.

    Args:
        session:           The forward-test session to assess.
        bar_store:         Bar store to read bar timestamps from.
        min_eligible_bars: Minimum eligible bars gate (from settings).
        min_calendar_days: Minimum calendar days gate (from settings).

    Returns:
        FTEvidenceReadiness with eligible=True when all gates pass, or
        eligible=False with a descriptive blocker message.
    """
    all_bars = bar_store.list_bars(session.session_id)
    eligible_bars = [b for b in all_bars if not b.is_warmup_bar]
    eligible_count = len(eligible_bars)

    # Count distinct UTC calendar dates among signal-eligible bars
    calendar_dates = {
        b.bar_timestamp.astimezone(timezone.utc).date()
        for b in eligible_bars
    }
    calendar_day_count = len(calendar_dates)

    # Evaluate gates in a consistent order for deterministic blocker messages
    if eligible_count < min_eligible_bars:
        blocker = (
            f"Insufficient eligible bars: {eligible_count} processed, "
            f"{min_eligible_bars} required. "
            f"Continue running forward-test cycles to accumulate evidence."
        )
        return FTEvidenceReadiness(
            eligible=False,
            eligible_bars=eligible_count,
            calendar_days=calendar_day_count,
            min_eligible_bars=min_eligible_bars,
            min_calendar_days=min_calendar_days,
            blocker=blocker,
        )

    if calendar_day_count < min_calendar_days:
        blocker = (
            f"Insufficient calendar days observed: {calendar_day_count} distinct "
            f"day{'' if calendar_day_count == 1 else 's'} observed, "
            f"{min_calendar_days} required. "
            f"The strategy must be evaluated across more trading days."
        )
        return FTEvidenceReadiness(
            eligible=False,
            eligible_bars=eligible_count,
            calendar_days=calendar_day_count,
            min_eligible_bars=min_eligible_bars,
            min_calendar_days=min_calendar_days,
            blocker=blocker,
        )

    return FTEvidenceReadiness(
        eligible=True,
        eligible_bars=eligible_count,
        calendar_days=calendar_day_count,
        min_eligible_bars=min_eligible_bars,
        min_calendar_days=min_calendar_days,
        blocker=None,
    )

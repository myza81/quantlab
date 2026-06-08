"""
FT-2B — Forward-test promotion evidence assessment unit tests.

Covers assess_ft_promotion_readiness() for all gate combinations,
edge cases, and the new promotion path in draft_service.

Tests:
  1.  0 eligible bars → blocked (bar gate)
  2.  1 eligible bar → blocked (bar gate, below min)
  3.  Enough bars, all same calendar day → blocked (day gate)
  4.  Enough bars, enough calendar days → eligible
  5.  Exactly at bar threshold + exactly at day threshold → eligible
  6.  Bar threshold = 1, day threshold = 1, 1 bar → eligible
  7.  Bar threshold configurable: override to 2, 1 bar → blocked
  8.  Day threshold configurable: override to 1, many bars same day → eligible
  9.  Bars across multiple days counted correctly
 10.  Warmup bars are excluded from both counts
 11.  Mixed warmup + eligible bars — only eligible bars count
 12.  blocker message contains bar count and threshold (bar gate)
 13.  blocker message contains day count and threshold (day gate)
 14.  eligible result has blocker=None
 15.  Promotion service: 0 bars → ForwardTestPromotionError
 16.  Promotion service: 1 bar → ForwardTestPromotionError (below min_eligible_bars=20)
 17.  Promotion service: enough bars but same day → ForwardTestPromotionError (day gate)
 18.  Promotion service: both gates satisfied → succeeds
 19.  Promotion service: configurable threshold via settings patch
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.forward_testing.evidence import (
    FTEvidenceReadiness,
    assess_ft_promotion_readiness,
)
from backend.forward_testing.models import ForwardTestBar, ForwardTestSession, StrategySnapshot
from backend.forward_testing.stores import ForwardTestBarStore

_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(_UTC)


def _make_snapshot() -> StrategySnapshot:
    return StrategySnapshot(
        draft_id="aaaaaaaa-0001-4001-8001-aaaaaaaaaaaa",
        display_name="Test",
        lifecycle_status="backtested",
        snapshot_hash="abc",
        captured_at=_now(),
        strategy_json='{"draft_id":"aaaaaaaa-0001-4001-8001-aaaaaaaaaaaa"}',
    )


def _make_session() -> ForwardTestSession:
    now = _now()
    return ForwardTestSession(
        session_id="bbbbbbbb-0002-4002-8002-bbbbbbbbbbbb",
        user_id="cccccccc-0003-4003-8003-cccccccccccc",
        draft_id="aaaaaaaa-0001-4001-8001-aaaaaaaaaaaa",
        strategy_snapshot=_make_snapshot(),
        lifecycle_status_at_activation="backtested",
        source_mode="provider",
        provider_name="yahoo",
        symbol="AAPL",
        timeframe="1d",
        warmup_bars_required=0,
        created_at=now,
        updated_at=now,
    )


SESSION_ID = "bbbbbbbb-0002-4002-8002-bbbbbbbbbbbb"


def _make_bar(
    store_path: Path,
    session_id: str,
    bar_index: int,
    bar_date: datetime,
    is_warmup: bool = False,
) -> None:
    """Write a ForwardTestBar directly into the store's bars dir."""
    bars_dir = store_path / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    bar_file = bars_dir / f"{session_id}.json"

    bar = ForwardTestBar(
        session_id=session_id,
        bar_index=bar_index,
        bar_timestamp=bar_date,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1_000_000.0,
        source_mode="provider",
        provider_name="yahoo",
        is_warmup_bar=is_warmup,
        processed_at=_now(),
    )

    if bar_file.exists():
        existing = json.loads(bar_file.read_text(encoding="utf-8"))
    else:
        existing = []
    existing.append(json.loads(bar.model_dump_json()))
    bar_file.write_text(json.dumps(existing), encoding="utf-8")


def _dates_from(start: datetime, n: int) -> list[datetime]:
    """Return n UTC datetimes on consecutive days starting at start."""
    return [start + timedelta(days=i) for i in range(n)]


# ---------------------------------------------------------------------------
# 1–9. assess_ft_promotion_readiness — gate logic
# ---------------------------------------------------------------------------

class TestEvidenceGates:
    def test_zero_bars_blocked_bar_gate(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=20, min_calendar_days=5
        )
        assert result.eligible is False
        assert result.eligible_bars == 0
        assert result.calendar_days == 0
        assert "0" in result.blocker
        assert "20" in result.blocker

    def test_one_bar_blocked_bar_gate(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        _make_bar(tmp_path, SESSION_ID, 0, _now(), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=20, min_calendar_days=5
        )
        assert result.eligible is False
        assert result.eligible_bars == 1
        assert "1" in result.blocker
        assert "20" in result.blocker

    def test_enough_bars_same_day_blocked_day_gate(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        base = datetime(2026, 1, 2, 16, 0, 0, tzinfo=_UTC)
        for i in range(20):
            # All on the same UTC calendar date — day gate should fail
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(minutes=i), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=20, min_calendar_days=5
        )
        assert result.eligible is False
        assert result.eligible_bars == 20
        assert result.calendar_days == 1
        assert "1" in result.blocker
        assert "5" in result.blocker

    def test_enough_bars_enough_days_eligible(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        base = datetime(2026, 1, 2, 12, 0, 0, tzinfo=_UTC)
        dates = _dates_from(base, 20)  # 20 bars on 20 consecutive days
        for i, d in enumerate(dates):
            _make_bar(tmp_path, SESSION_ID, i, d, is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=20, min_calendar_days=5
        )
        assert result.eligible is True
        assert result.eligible_bars == 20
        assert result.calendar_days == 20
        assert result.blocker is None

    def test_exactly_at_both_thresholds(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        # 5 bars on 5 different days; thresholds set to match exactly
        base = datetime(2026, 3, 1, 10, 0, 0, tzinfo=_UTC)
        for i in range(5):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(days=i), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=5, min_calendar_days=5
        )
        assert result.eligible is True

    def test_threshold_1_bar_1_day_eligible(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        _make_bar(tmp_path, SESSION_ID, 0, _now(), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=1, min_calendar_days=1
        )
        assert result.eligible is True

    def test_configurable_bar_threshold_override(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        _make_bar(tmp_path, SESSION_ID, 0, _now(), is_warmup=False)
        # Require 2 bars; have 1
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=2, min_calendar_days=1
        )
        assert result.eligible is False

    def test_configurable_day_threshold_override(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        base = datetime(2026, 6, 1, 12, 0, 0, tzinfo=_UTC)
        # 5 bars all on same day; require only 1 day
        for i in range(5):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(minutes=i), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=5, min_calendar_days=1
        )
        assert result.eligible is True

    def test_bars_across_multiple_days_counted(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        base = datetime(2026, 1, 2, 9, 0, 0, tzinfo=_UTC)
        # 4 bars on day 1, 3 bars on day 2, 5 bars on day 3
        for i in range(4):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(minutes=i * 30), is_warmup=False)
        day2 = base + timedelta(days=1)
        for i in range(3):
            _make_bar(tmp_path, SESSION_ID, 4 + i, day2 + timedelta(minutes=i * 30), is_warmup=False)
        day3 = base + timedelta(days=2)
        for i in range(5):
            _make_bar(tmp_path, SESSION_ID, 7 + i, day3 + timedelta(minutes=i * 30), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=10, min_calendar_days=3
        )
        assert result.eligible_bars == 12
        assert result.calendar_days == 3
        assert result.eligible is True


# ---------------------------------------------------------------------------
# 10–11. Warmup bar exclusion
# ---------------------------------------------------------------------------

class TestWarmupExclusion:
    def test_warmup_bars_not_counted_as_eligible(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        base = datetime(2026, 1, 2, 12, 0, 0, tzinfo=_UTC)
        # 25 warmup bars — should NOT count
        for i in range(25):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(days=i), is_warmup=True)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=1, min_calendar_days=1
        )
        assert result.eligible_bars == 0
        assert result.eligible is False

    def test_mixed_warmup_and_eligible_counts_only_eligible(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        base = datetime(2026, 1, 2, 12, 0, 0, tzinfo=_UTC)
        # 5 warmup bars
        for i in range(5):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(days=i), is_warmup=True)
        # 3 eligible bars on 3 different days
        for i in range(3):
            _make_bar(
                tmp_path, SESSION_ID, 5 + i,
                base + timedelta(days=5 + i),
                is_warmup=False,
            )
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=3, min_calendar_days=3
        )
        assert result.eligible_bars == 3
        assert result.calendar_days == 3
        assert result.eligible is True


# ---------------------------------------------------------------------------
# 12–14. Blocker message content
# ---------------------------------------------------------------------------

class TestBlockerMessages:
    def test_bar_gate_blocker_contains_counts_and_threshold(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        _make_bar(tmp_path, SESSION_ID, 0, _now(), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=10, min_calendar_days=3
        )
        assert result.eligible is False
        assert "1" in result.blocker      # current count
        assert "10" in result.blocker     # threshold

    def test_day_gate_blocker_contains_counts_and_threshold(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        base = datetime(2026, 2, 1, 12, 0, 0, tzinfo=_UTC)
        # 10 bars on same day → fails day gate, not bar gate
        for i in range(10):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(hours=i), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=10, min_calendar_days=5
        )
        assert result.eligible is False
        assert "1" in result.blocker      # calendar days observed
        assert "5" in result.blocker      # threshold

    def test_eligible_result_has_no_blocker(self, tmp_path: Path):
        store = ForwardTestBarStore(tmp_path)
        session = _make_session()
        base = datetime(2026, 1, 2, 12, 0, 0, tzinfo=_UTC)
        for i in range(5):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(days=i), is_warmup=False)
        result = assess_ft_promotion_readiness(
            session=session, bar_store=store, min_eligible_bars=5, min_calendar_days=5
        )
        assert result.eligible is True
        assert result.blocker is None


# ---------------------------------------------------------------------------
# 15–19. promote_draft_to_forward_tested — integration with evidence gates
# ---------------------------------------------------------------------------

class TestPromotionServiceGates:
    """
    Test that the draft_service promotion function enforces FT-2B gates.
    Uses a real ForwardTestBarStore (tmp_path) and mock repository/session.
    """

    def _make_ft_session(
        self,
        session_id: str = SESSION_ID,
        draft_id: str = "aaaaaaaa-0001-4001-8001-aaaaaaaaaaaa",
        user_id: str = "cccccccc-0003-4003-8003-cccccccccccc",
    ) -> ForwardTestSession:
        return _make_session()

    def _run_promote(
        self,
        tmp_path: Path,
        session: ForwardTestSession,
        draft_status: str = "backtested",
        min_eligible_bars: int = 20,
        min_calendar_days: int = 5,
    ):
        from backend.api.services.draft_service import (
            ForwardTestPromotionError,
            promote_draft_to_forward_tested,
        )
        from backend.forward_testing.stores import ForwardTestBarStore
        from backend.strategy_registry.drafts import StrategyDraft
        from backend.strategy_registry.lifecycle import StrategyLifecycleStatus

        mock_ft_repo = MagicMock()
        mock_ft_repo.load.return_value = session

        now = _now()
        draft_data = {
            "draft_id": session.draft_id,
            "display_name": "Test Draft",
            "description": None,
            "toolset": {"toolset_id": "t1", "tools": []},
            "created_at": now,
            "updated_at": now,
            "enabled": True,
            "tags": [],
            "notes": None,
            "lifecycle_status": StrategyLifecycleStatus(draft_status),
            "semantics": None,
            "user_id": session.user_id,
        }
        mock_draft_repo = MagicMock()
        mock_draft_repo.load.return_value = StrategyDraft.model_validate(draft_data)
        mock_draft_repo.update.return_value = None

        bar_store = ForwardTestBarStore(tmp_path)

        with patch("backend.core.config.settings.ft_min_eligible_bars", min_eligible_bars), \
             patch("backend.core.config.settings.ft_min_calendar_days", min_calendar_days):
            return promote_draft_to_forward_tested(
                session_id=session.session_id,
                draft_id=session.draft_id,
                ft_repository=mock_ft_repo,
                draft_repository=mock_draft_repo,
                owner_id=session.user_id,
                ft_bar_store=bar_store,
            )

    def test_zero_bars_raises_promotion_error(self, tmp_path: Path):
        from backend.api.services.draft_service import ForwardTestPromotionError

        session = _make_session()
        with pytest.raises(ForwardTestPromotionError) as exc_info:
            self._run_promote(tmp_path, session)
        assert "0" in str(exc_info.value)

    def test_one_bar_below_threshold_raises(self, tmp_path: Path):
        from backend.api.services.draft_service import ForwardTestPromotionError

        session = _make_session()
        _make_bar(tmp_path, SESSION_ID, 0, _now(), is_warmup=False)
        with pytest.raises(ForwardTestPromotionError):
            self._run_promote(tmp_path, session, min_eligible_bars=20)

    def test_enough_bars_but_same_day_raises(self, tmp_path: Path):
        from backend.api.services.draft_service import ForwardTestPromotionError

        session = _make_session()
        base = datetime(2026, 4, 1, 12, 0, 0, tzinfo=_UTC)
        for i in range(20):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(minutes=i), is_warmup=False)
        with pytest.raises(ForwardTestPromotionError) as exc_info:
            self._run_promote(tmp_path, session, min_eligible_bars=20, min_calendar_days=5)
        assert "day" in str(exc_info.value).lower()

    def test_both_gates_satisfied_promotes(self, tmp_path: Path):
        session = _make_session()
        base = datetime(2026, 4, 1, 12, 0, 0, tzinfo=_UTC)
        for i in range(20):
            _make_bar(tmp_path, SESSION_ID, i, base + timedelta(days=i), is_warmup=False)
        result = self._run_promote(tmp_path, session, min_eligible_bars=20, min_calendar_days=5)
        assert result.lifecycle_status == "forward_tested"

    def test_configurable_threshold_low_passes(self, tmp_path: Path):
        """With thresholds overridden to 1/1, a single bar is enough."""
        session = _make_session()
        _make_bar(tmp_path, SESSION_ID, 0, _now(), is_warmup=False)
        result = self._run_promote(tmp_path, session, min_eligible_bars=1, min_calendar_days=1)
        assert result.lifecycle_status == "forward_tested"

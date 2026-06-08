"""
FT-2 — ForwardTestSchedulerJob unit tests.

Covers:
  1.  run_tick — disabled by settings → no repository access
  2.  run_tick — no running sessions → tick completes cleanly
  3.  run_tick — RUNNING session → run_cycle called
  4.  run_tick — PAUSED session → skipped (not_running)
  5.  run_tick — TERMINATED session → skipped (not_running)
  6.  run_tick — interval not elapsed → skipped (interval_not_elapsed)
  7.  run_tick — interval elapsed → run_cycle called
  8.  run_tick — provider build failure → failure counter incremented
  9.  run_tick — run_cycle raises → failure counter incremented
 10.  run_tick — N consecutive failures → session auto-paused
 11.  run_tick — success after failures → failure counter reset
 12.  run_tick — list_all_running_globally raises → tick logs error, does not crash
 13.  run_tick — repository update failure for last_cycle_attempted_at → non-fatal
 14.  list_all_running_globally — returns only RUNNING sessions
 15.  list_all_running_globally — empty directory → empty list
 16.  ForwardTestSession — new scheduler fields have correct defaults
 17.  ForwardTestSession — last_cycle_attempted_at validator enforces UTC-aware
 18.  Settings — new scheduler settings have correct defaults
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import settings
from backend.forward_testing.models import (
    ForwardTestSession,
    ForwardTestSessionStatus,
    StrategySnapshot,
)
from backend.forward_testing.repository import ForwardTestRepository
from backend.jobs.ft_scheduler import ForwardTestSchedulerJob, _build_provider_for_session

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(_UTC)


def _make_snapshot() -> StrategySnapshot:
    return StrategySnapshot(
        draft_id="aaaaaaaa-0001-4001-8001-aaaaaaaaaaaa",
        display_name="Test Strategy",
        lifecycle_status="backtested",
        snapshot_hash="abc123",
        captured_at=_now(),
        strategy_json='{"draft_id": "aaaaaaaa-0001-4001-8001-aaaaaaaaaaaa"}',
    )


def _make_session(
    status: ForwardTestSessionStatus = ForwardTestSessionStatus.RUNNING,
    consecutive_provider_failures: int = 0,
    last_cycle_attempted_at: datetime | None = None,
    cycle_interval_seconds: int = 300,
) -> ForwardTestSession:
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
        exchange="NASDAQ",
        asset_class="equity",
        warmup_bars_required=0,
        status=status,
        created_at=now,
        updated_at=now,
        consecutive_provider_failures=consecutive_provider_failures,
        last_cycle_attempted_at=last_cycle_attempted_at,
        cycle_interval_seconds=cycle_interval_seconds,
    )


def _make_job(
    running_sessions: list | None = None,
    cycle_result: MagicMock | None = None,
) -> tuple[ForwardTestSchedulerJob, MagicMock, MagicMock]:
    """Return (job, mock_repository, mock_service_class)."""
    if running_sessions is None:
        running_sessions = []

    mock_repo = MagicMock()
    mock_repo.list_all_running_globally.return_value = running_sessions
    mock_repo.update.return_value = None

    if cycle_result is None:
        cycle_result = MagicMock()
        cycle_result.status = "running"
        cycle_result.bars_processed = 1
        cycle_result.signals_generated = 0
        cycle_result.gap_detected = False
        cycle_result.provider_failure = False
        cycle_result.activated = False
        cycle_result.message = None

    mock_service_instance = MagicMock()
    mock_service_instance.run_cycle.return_value = cycle_result

    job = ForwardTestSchedulerJob(
        repository=mock_repo,
        bar_store=MagicMock(),
        signal_store=MagicMock(),
        ohlcv_service=MagicMock(),
        tool_registry=MagicMock(),
        provider_factory=MagicMock(),
    )

    return job, mock_repo, mock_service_instance


# ---------------------------------------------------------------------------
# 1. Disabled by settings
# ---------------------------------------------------------------------------

class TestSchedulerDisabled:
    def test_run_tick_disabled_skips_repository(self, tmp_path):
        job, mock_repo, _ = _make_job()
        with patch.object(settings, "ft_scheduler_enabled", False):
            job.run_tick()
        mock_repo.list_all_running_globally.assert_not_called()

    def test_run_tick_enabled_by_default(self):
        assert settings.ft_scheduler_enabled is True


# ---------------------------------------------------------------------------
# 2–3. Clean tick / RUNNING session evaluated
# ---------------------------------------------------------------------------

class TestRunTick:
    def test_empty_sessions_completes_cleanly(self):
        job, mock_repo, _ = _make_job(running_sessions=[])
        job.run_tick()
        mock_repo.list_all_running_globally.assert_called_once()

    def test_running_session_calls_run_cycle(self):
        session = _make_session()
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ), patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            return_value=MagicMock(),
        ):
            job.run_tick()

        mock_svc.run_cycle.assert_called_once()
        call_kwargs = mock_svc.run_cycle.call_args
        assert call_kwargs.kwargs.get("session_id") == session.session_id or \
               call_kwargs.args[0] == session.session_id


# ---------------------------------------------------------------------------
# 4–5. Non-RUNNING sessions skipped
# ---------------------------------------------------------------------------

class TestSessionSkipping:
    @pytest.mark.parametrize("status", [
        ForwardTestSessionStatus.PAUSED,
        ForwardTestSessionStatus.COMPLETED,
        ForwardTestSessionStatus.FAILED,
        ForwardTestSessionStatus.TERMINATED,
    ])
    def test_non_running_session_skipped(self, status):
        session = _make_session(status=status)
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ):
            job.run_tick()

        mock_svc.run_cycle.assert_not_called()


# ---------------------------------------------------------------------------
# 6–7. Interval-based skip
# ---------------------------------------------------------------------------

class TestIntervalSkip:
    def test_interval_not_elapsed_skips_session(self):
        recent = _now() - timedelta(seconds=10)
        session = _make_session(
            last_cycle_attempted_at=recent,
            cycle_interval_seconds=300,  # 5 minutes — 10 seconds not enough
        )
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ):
            job.run_tick()

        mock_svc.run_cycle.assert_not_called()

    def test_interval_elapsed_runs_session(self):
        old_attempt = _now() - timedelta(seconds=400)
        session = _make_session(
            last_cycle_attempted_at=old_attempt,
            cycle_interval_seconds=300,
        )
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ), patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            return_value=MagicMock(),
        ):
            job.run_tick()

        mock_svc.run_cycle.assert_called_once()

    def test_no_previous_attempt_runs_session(self):
        # last_cycle_attempted_at=None means never run — should always evaluate
        session = _make_session(last_cycle_attempted_at=None)
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ), patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            return_value=MagicMock(),
        ):
            job.run_tick()

        mock_svc.run_cycle.assert_called_once()


# ---------------------------------------------------------------------------
# 8–9. Provider / run_cycle failures
# ---------------------------------------------------------------------------

class TestFailureHandling:
    def test_provider_build_failure_increments_counter(self):
        session = _make_session(consecutive_provider_failures=0)
        job, mock_repo, _ = _make_job(running_sessions=[session])

        with patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            side_effect=Exception("Connection refused"),
        ):
            job.run_tick()

        # repository.update should have been called to persist the incremented counter
        assert mock_repo.update.call_count >= 1
        # Check the updated session has consecutive_provider_failures incremented
        updated_session = mock_repo.update.call_args_list[-1].args[0]
        assert updated_session.consecutive_provider_failures == 1

    def test_run_cycle_exception_increments_counter(self):
        session = _make_session(consecutive_provider_failures=1)
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])
        mock_svc.run_cycle.side_effect = Exception("Timeout")

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ), patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            return_value=MagicMock(),
        ):
            job.run_tick()

        updated_session = mock_repo.update.call_args_list[-1].args[0]
        assert updated_session.consecutive_provider_failures == 2

    def test_provider_failure_result_increments_counter(self):
        session = _make_session(consecutive_provider_failures=2)
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        failure_result = MagicMock()
        failure_result.provider_failure = True
        failure_result.status = "running"
        failure_result.bars_processed = 0
        failure_result.signals_generated = 0
        failure_result.gap_detected = False
        failure_result.activated = False
        failure_result.message = "provider error"
        mock_svc.run_cycle.return_value = failure_result

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ), patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            return_value=MagicMock(),
        ):
            job.run_tick()

        # Should have incremented from 2 to 3
        updated_session = mock_repo.update.call_args_list[-1].args[0]
        assert updated_session.consecutive_provider_failures == 3


# ---------------------------------------------------------------------------
# 10. Auto-pause after N failures
# ---------------------------------------------------------------------------

class TestAutoPause:
    def test_auto_pause_at_threshold(self):
        threshold = settings.ft_scheduler_max_consecutive_failures
        # Already at threshold - 1, so next failure triggers pause
        session = _make_session(
            consecutive_provider_failures=threshold - 1,
        )
        job, mock_repo, _ = _make_job(running_sessions=[session])

        with patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            side_effect=Exception("Timeout"),
        ):
            job.run_tick()

        # Find the update call that set status to PAUSED
        paused_calls = [
            call for call in mock_repo.update.call_args_list
            if call.args[0].status == ForwardTestSessionStatus.PAUSED
        ]
        assert len(paused_calls) == 1
        paused_session = paused_calls[0].args[0]
        assert paused_session.failure_reason is not None
        assert "auto_pause" in paused_session.failure_reason

    def test_below_threshold_does_not_pause(self):
        threshold = settings.ft_scheduler_max_consecutive_failures
        session = _make_session(
            consecutive_provider_failures=threshold - 2,
        )
        job, mock_repo, _ = _make_job(running_sessions=[session])

        with patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            side_effect=Exception("Timeout"),
        ):
            job.run_tick()

        paused_calls = [
            call for call in mock_repo.update.call_args_list
            if call.args[0].status == ForwardTestSessionStatus.PAUSED
        ]
        assert len(paused_calls) == 0


# ---------------------------------------------------------------------------
# 11. Counter reset on success
# ---------------------------------------------------------------------------

class TestCounterReset:
    def test_successful_cycle_resets_failure_counter(self):
        session = _make_session(consecutive_provider_failures=3)
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        success_result = MagicMock()
        success_result.provider_failure = False
        success_result.status = "running"
        success_result.bars_processed = 1
        success_result.signals_generated = 0
        success_result.gap_detected = False
        success_result.activated = False
        success_result.message = None
        mock_svc.run_cycle.return_value = success_result

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ), patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            return_value=MagicMock(),
        ):
            job.run_tick()

        # Last update should reset failures to 0
        reset_calls = [
            call for call in mock_repo.update.call_args_list
            if call.args[0].consecutive_provider_failures == 0
        ]
        assert len(reset_calls) >= 1

    def test_counter_zero_skips_reset_write(self):
        # If counter is already 0, no extra write should happen for reset
        session = _make_session(consecutive_provider_failures=0)
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        success_result = MagicMock()
        success_result.provider_failure = False
        success_result.status = "running"
        success_result.bars_processed = 1
        success_result.signals_generated = 0
        success_result.gap_detected = False
        success_result.activated = False
        success_result.message = None
        mock_svc.run_cycle.return_value = success_result

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ), patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            return_value=MagicMock(),
        ):
            job.run_tick()

        # 0 update calls expected: no pre-cycle write (FT-3A removed it) and
        # no reset write when consecutive_provider_failures is already 0.
        assert mock_repo.update.call_count == 0


# ---------------------------------------------------------------------------
# 12. Repository scan failure — non-fatal
# ---------------------------------------------------------------------------

class TestRepositoryScanFailure:
    def test_list_failure_does_not_crash_tick(self):
        job, mock_repo, _ = _make_job()
        mock_repo.list_all_running_globally.side_effect = Exception("disk error")

        # Should not raise
        job.run_tick()

        mock_repo.list_all_running_globally.assert_called_once()


# ---------------------------------------------------------------------------
# 13. Non-fatal update failure for last_cycle_attempted_at
# ---------------------------------------------------------------------------

class TestUpdateFailureNonFatal:
    def test_post_cycle_update_failure_is_nonfatal(self):
        """Post-cycle repository.update() failure must not crash the scheduler tick."""
        # Session has failures so _handle_provider_failure will attempt an update
        session = _make_session(consecutive_provider_failures=2)
        job, mock_repo, mock_svc = _make_job(running_sessions=[session])

        failure_result = MagicMock()
        failure_result.provider_failure = True
        failure_result.status = "running"
        failure_result.bars_processed = 0
        failure_result.signals_generated = 0
        failure_result.gap_detected = False
        failure_result.activated = False
        failure_result.message = "provider error"
        mock_svc.run_cycle.return_value = failure_result

        # Post-cycle update fails — tick must not raise
        mock_repo.update.side_effect = Exception("IO error")

        with patch(
            "backend.jobs.ft_scheduler.ForwardTestService",
            return_value=mock_svc,
        ), patch(
            "backend.jobs.ft_scheduler._build_provider_for_session",
            return_value=MagicMock(),
        ):
            job.run_tick()  # must not raise

        mock_svc.run_cycle.assert_called_once()


# ---------------------------------------------------------------------------
# 14–15. Repository: list_all_running_globally
# ---------------------------------------------------------------------------

class TestListAllRunningGlobally:
    def test_returns_only_running_sessions(self, tmp_path: Path):
        repo = ForwardTestRepository(tmp_path)
        repo._ensure_dirs()
        now = _now()

        def _save(session_id: str, status: ForwardTestSessionStatus) -> None:
            sess = ForwardTestSession(
                session_id=session_id,
                user_id="cccccccc-0003-4003-8003-cccccccccccc",
                draft_id="aaaaaaaa-0001-4001-8001-aaaaaaaaaaaa",
                strategy_snapshot=_make_snapshot(),
                lifecycle_status_at_activation="backtested",
                source_mode="provider",
                provider_name="yahoo",
                symbol="AAPL",
                timeframe="1d",
                warmup_bars_required=0,
                status=status,
                created_at=now,
                updated_at=now,
            )
            (tmp_path / "sessions" / f"{session_id}.json").write_text(
                sess.model_dump_json() + "\n", encoding="utf-8"
            )

        _save("11111111-0001-4001-8001-111111111111", ForwardTestSessionStatus.RUNNING)
        _save("22222222-0002-4002-8002-222222222222", ForwardTestSessionStatus.PAUSED)
        _save("33333333-0003-4003-8003-333333333333", ForwardTestSessionStatus.RUNNING)
        _save("44444444-0004-4004-8004-444444444444", ForwardTestSessionStatus.TERMINATED)

        running = repo.list_all_running_globally()
        ids = {s.session_id for s in running}

        assert ids == {
            "11111111-0001-4001-8001-111111111111",
            "33333333-0003-4003-8003-333333333333",
        }

    def test_empty_directory_returns_empty_list(self, tmp_path: Path):
        repo = ForwardTestRepository(tmp_path)
        result = repo.list_all_running_globally()
        assert result == []


# ---------------------------------------------------------------------------
# 16–17. ForwardTestSession scheduler fields
# ---------------------------------------------------------------------------

class TestSessionSchedulerFields:
    def test_new_session_has_correct_defaults(self):
        session = _make_session()
        assert session.cycle_interval_seconds == 300
        assert session.consecutive_provider_failures == 0
        assert session.last_cycle_attempted_at is None

    def test_last_cycle_attempted_at_validator_accepts_utc(self):
        now = _now()
        session = _make_session(last_cycle_attempted_at=now)
        assert session.last_cycle_attempted_at == now

    def test_last_cycle_attempted_at_validator_rejects_naive(self):
        naive_dt = datetime(2026, 1, 1, 12, 0, 0)  # no tzinfo
        with pytest.raises(Exception):
            _make_session(last_cycle_attempted_at=naive_dt)


# ---------------------------------------------------------------------------
# 18. Settings defaults
# ---------------------------------------------------------------------------

class TestSchedulerSettings:
    def test_ft_scheduler_enabled_default(self):
        assert settings.ft_scheduler_enabled is True

    def test_ft_scheduler_interval_seconds_default(self):
        assert settings.ft_scheduler_interval_seconds == 60

    def test_ft_scheduler_max_consecutive_failures_default(self):
        assert settings.ft_scheduler_max_consecutive_failures == 5

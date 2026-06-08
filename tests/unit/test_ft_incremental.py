"""
FT-3B — Incremental Tool Computation tests.

Verifies watermark-based evaluation skipping in ForwardTestService._poll_cycle().

Coverage:
  1.  Legacy session (last_computed_bar_index=None) is accepted by model validator
  2.  Model validator rejects negative last_computed_bar_index
  3.  First cycle sets watermark to max bar_index of new bars
  4.  Second cycle with no new bars: watermark unchanged, counters unchanged
  5.  New bars after watermark are evaluated; already-evaluated bars are skipped
  6.  Watermark advances on each successful cycle
  7.  Warmup bars: bar_index < warmup_bars_required never counted as eligible
  8.  Watermark inconsistency (watermark > max stored index) is reset safely
  9.  Repeated identical run-cycle calls do not duplicate signals (idempotency)
 10.  Repeated identical run-cycle calls do not inflate signal_eligible_bars_processed
 11.  Manual /run-cycle route: watermark advances after HTTP-triggered cycle
 12.  Watermark written atomically with session counters in same update call
 13.  Session with watermark=None processes all indexed_new_bars as new for evaluation
 14.  Zero new bars: watermark not changed, counters not incremented
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from backend.forward_testing.models import (
    ForwardTestSession,
    ForwardTestSessionStatus,
    StrategySnapshot,
)
from backend.forward_testing.service import ForwardTestService
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore

_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(_UTC)


def _ts(days: int = 0, hours: int = 0) -> datetime:
    base = datetime(2024, 1, 2, tzinfo=_UTC)
    return base + timedelta(days=days, hours=hours)


_SESSION_ID = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
_USER_ID    = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"
_DRAFT_ID   = "cccccccc-3333-4333-8333-cccccccccccc"


def _make_snapshot() -> StrategySnapshot:
    return StrategySnapshot(
        draft_id=_DRAFT_ID,
        display_name="Test",
        lifecycle_status="backtested",
        snapshot_hash="abc",
        captured_at=_ts(),
        strategy_json='{"draft_id":"cccccccc-3333-4333-8333-cccccccccccc"}',
    )


def _make_session(
    warmup: int = 0,
    watermark: int | None = None,
    status: ForwardTestSessionStatus = ForwardTestSessionStatus.RUNNING,
    bars_evaluated: int = 0,
    signal_eligible_bars_processed: int = 0,
    signals_recorded: int = 0,
    last_processed_bar_timestamp: datetime | None = None,
) -> ForwardTestSession:
    now = _ts()
    return ForwardTestSession(
        session_id=_SESSION_ID,
        user_id=_USER_ID,
        draft_id=_DRAFT_ID,
        strategy_snapshot=_make_snapshot(),
        lifecycle_status_at_activation="backtested",
        source_mode="provider",
        provider_name="yahoo",
        symbol="AAPL",
        timeframe="1d",
        warmup_bars_required=warmup,
        status=status,
        created_at=now,
        updated_at=now,
        activation_timestamp=_ts(days=-5),
        last_processed_bar_timestamp=last_processed_bar_timestamp,
        bars_evaluated=bars_evaluated,
        signal_eligible_bars_processed=signal_eligible_bars_processed,
        signals_recorded=signals_recorded,
        last_computed_bar_index=watermark,
    )


def _make_ohlcv_bar(ts: datetime) -> MagicMock:
    bar = MagicMock()
    bar.timestamp = ts
    bar.open  = 100.0
    bar.high  = 105.0
    bar.low   = 95.0
    bar.close = 102.0
    bar.volume = 1_000_000.0
    return bar


def _make_service(session: ForwardTestSession, bar_store: ForwardTestBarStore) -> tuple[
    ForwardTestService, MagicMock, MagicMock, MagicMock
]:
    """Build a ForwardTestService with mocked dependencies."""
    mock_repo = MagicMock()
    mock_repo.load.return_value = session
    mock_repo.update.return_value = None

    mock_signal_store = MagicMock(spec=ForwardTestSignalStore)
    mock_signal_store.append_signal.return_value = True

    mock_ohlcv   = MagicMock()
    mock_registry = MagicMock()

    svc = ForwardTestService(
        repository=mock_repo,
        bar_store=bar_store,
        signal_store=mock_signal_store,
        ohlcv_service=mock_ohlcv,
        tool_registry=mock_registry,
    )
    return svc, mock_repo, mock_signal_store, mock_ohlcv


def _build_identity() -> MagicMock:
    return MagicMock()


def _build_provider() -> MagicMock:
    return MagicMock()


def _run_poll(
    svc: ForwardTestService,
    session: ForwardTestSession,
    mock_ohlcv: MagicMock,
    new_bar_timestamps: list[datetime],
    *,
    mock_eval_result: MagicMock | None = None,
    mock_tool_result: MagicMock | None = None,
) -> MagicMock:
    """
    Helper: configure ohlcv mock to return bars, run _poll_cycle, return result.

    Tool computation and strategy evaluation are patched to return empty results
    unless overridden.
    """
    mock_ohlcv.get_bars_since.return_value = [
        _make_ohlcv_bar(ts) for ts in new_bar_timestamps
    ]

    if mock_tool_result is None:
        mock_tool_result = MagicMock()
        mock_tool_result.tool_results = []

    if mock_eval_result is None:
        mock_eval_result = MagicMock()
        mock_eval_result.bar_results = []

    plan   = MagicMock()
    draft  = MagicMock(); draft.toolset = []
    calendar = MagicMock()
    calendar.is_expected_bar = MagicMock(return_value=False)

    with patch(
        "backend.forward_testing.service.compute_tool_outputs_for_history",
        return_value=mock_tool_result,
    ), patch(
        "backend.forward_testing.service.build_bar_tool_outputs",
        return_value={},
    ), patch(
        "backend.forward_testing.service.evaluate_history",
        return_value=mock_eval_result,
    ):
        return svc._poll_cycle(
            session=session,
            owner_id=_USER_ID,
            identity=_build_identity(),
            provider=_build_provider(),
            plan=plan,
            draft=draft,
            calendar=calendar,
            now_utc=_now(),
        )


# ---------------------------------------------------------------------------
# 1–2. Model field
# ---------------------------------------------------------------------------

class TestWatermarkModelField:
    def test_legacy_session_with_none_watermark(self):
        s = _make_session(watermark=None)
        assert s.last_computed_bar_index is None

    def test_session_with_set_watermark(self):
        s = _make_session(watermark=42)
        assert s.last_computed_bar_index == 42

    def test_negative_watermark_rejected(self):
        with pytest.raises(Exception):
            _make_session(watermark=-1)

    def test_zero_watermark_accepted(self):
        s = _make_session(watermark=0)
        assert s.last_computed_bar_index == 0


# ---------------------------------------------------------------------------
# 3. First cycle sets watermark
# ---------------------------------------------------------------------------

class TestFirstCycleSetsWatermark:
    def test_watermark_set_after_first_cycle(self, tmp_path):
        session = _make_session(watermark=None)
        bar_store = ForwardTestBarStore(tmp_path)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        _run_poll(svc, session, mock_ohlcv, [_ts(days=1), _ts(days=2)])

        update_call = mock_repo.update.call_args
        written: ForwardTestSession = update_call.args[0]
        # Two new bars (index 0, 1) — watermark must be 1
        assert written.last_computed_bar_index == 1

    def test_watermark_set_to_max_bar_index_of_new_bars(self, tmp_path):
        session = _make_session(watermark=None)
        bar_store = ForwardTestBarStore(tmp_path)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        _run_poll(svc, session, mock_ohlcv, [_ts(days=1), _ts(days=2), _ts(days=3)])

        written: ForwardTestSession = mock_repo.update.call_args.args[0]
        assert written.last_computed_bar_index == 2  # indices 0, 1, 2


# ---------------------------------------------------------------------------
# 4. No new bars: watermark unchanged, counters unchanged
# ---------------------------------------------------------------------------

class TestNoNewBars:
    def test_no_new_bars_does_not_change_watermark(self, tmp_path):
        session = _make_session(watermark=5, bars_evaluated=6)
        bar_store = ForwardTestBarStore(tmp_path)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        # Empty provider response
        _run_poll(svc, session, mock_ohlcv, [])

        # repository.update must NOT be called when there are no new bars
        mock_repo.update.assert_not_called()

    def test_no_new_bars_signal_eligible_count_unchanged(self, tmp_path):
        session = _make_session(watermark=5, signal_eligible_bars_processed=5)
        bar_store = ForwardTestBarStore(tmp_path)
        svc, _, _, mock_ohlcv = _make_service(session, bar_store)
        result = _run_poll(svc, session, mock_ohlcv, [])
        assert result.signal_eligible_bars_processed == 0


# ---------------------------------------------------------------------------
# 5–6. New bars after watermark: only those above watermark counted
# ---------------------------------------------------------------------------

class TestIncrementalEvaluation:
    def test_bars_above_watermark_counted_as_eligible(self, tmp_path):
        """Bars with bar_index > watermark are the only ones counted."""
        bar_store = ForwardTestBarStore(tmp_path)
        # Pre-populate bar store with 3 bars (index 0, 1, 2)
        from backend.forward_testing.models import ForwardTestBar
        base_ts = _ts()
        for i in range(3):
            bar_store.append_bar(ForwardTestBar(
                session_id=_SESSION_ID,
                bar_index=i,
                bar_timestamp=base_ts + timedelta(days=i),
                open=100.0, high=105.0, low=95.0, close=102.0, volume=1e6,
                source_mode="provider",
                provider_name="yahoo",
                is_warmup_bar=False,
                processed_at=_now(),
            ))

        # Watermark is at 2 (all 3 stored bars already evaluated)
        session = _make_session(
            watermark=2,
            bars_evaluated=3,
            signal_eligible_bars_processed=3,
            last_processed_bar_timestamp=base_ts + timedelta(days=2),
        )
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        # Provide one genuinely new bar (index 3)
        new_ts = base_ts + timedelta(days=3)
        _run_poll(svc, session, mock_ohlcv, [new_ts])

        written: ForwardTestSession = mock_repo.update.call_args.args[0]
        # Only 1 new bar → signal_eligible_bars_processed incremented by 1
        assert written.signal_eligible_bars_processed == 4  # 3 + 1
        # Watermark advances to 3
        assert written.last_computed_bar_index == 3

    def test_already_stored_duplicate_bars_not_counted(self, tmp_path):
        """Bars already in the bar store (duplicate timestamps) are not counted again."""
        bar_store = ForwardTestBarStore(tmp_path)
        from backend.forward_testing.models import ForwardTestBar
        ts1 = _ts(days=1)
        # Pre-populate with ts1
        bar_store.append_bar(ForwardTestBar(
            session_id=_SESSION_ID, bar_index=0, bar_timestamp=ts1,
            open=100.0, high=105.0, low=95.0, close=102.0, volume=1e6,
            source_mode="provider", provider_name="yahoo",
            is_warmup_bar=False, processed_at=_now(),
        ))

        session = _make_session(watermark=0, bars_evaluated=1,
                                signal_eligible_bars_processed=1,
                                last_processed_bar_timestamp=ts1)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        # Provider returns the same ts1 bar again (provider re-delivered)
        result = _run_poll(svc, session, mock_ohlcv, [ts1])

        # All incoming bars were duplicates → early return, no session update
        mock_repo.update.assert_not_called()
        assert result.bars_processed == 0
        assert result.signal_eligible_bars_processed == 0

    def test_watermark_advances_on_each_cycle(self, tmp_path):
        bar_store = ForwardTestBarStore(tmp_path)
        session = _make_session(watermark=None)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        # Cycle 1: 2 bars
        _run_poll(svc, session, mock_ohlcv, [_ts(days=1), _ts(days=2)])
        w1: int | None = mock_repo.update.call_args.args[0].last_computed_bar_index
        assert w1 == 1

        # Cycle 2: 1 more bar; update session watermark for second call
        session2 = _make_session(
            watermark=w1,
            bars_evaluated=2,
            signal_eligible_bars_processed=2,
            last_processed_bar_timestamp=_ts(days=2),
        )
        _run_poll(svc, session2, mock_ohlcv, [_ts(days=3)])
        w2: int | None = mock_repo.update.call_args.args[0].last_computed_bar_index
        assert w2 == 2  # index of the 3rd bar (0-indexed)


# ---------------------------------------------------------------------------
# 7. Warmup bars not counted as eligible
# ---------------------------------------------------------------------------

class TestWarmupBarNotCountedAsEligible:
    def test_warmup_bars_not_in_eligible_count(self, tmp_path):
        """Bars with bar_index < warmup_bars_required are never counted as eligible."""
        bar_store = ForwardTestBarStore(tmp_path)
        session = _make_session(warmup=2, watermark=None)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        # 2 warmup bars + 1 eligible bar
        _run_poll(svc, session, mock_ohlcv, [_ts(days=1), _ts(days=2), _ts(days=3)])

        written: ForwardTestSession = mock_repo.update.call_args.args[0]
        # bars 0 and 1 are warmup (bar_index < 2); bar 2 is eligible
        assert written.signal_eligible_bars_processed == 1

    def test_warmup_bars_do_not_advance_eligible_count_with_watermark(self, tmp_path):
        """Watermark skipping still counts warmup correctly."""
        bar_store = ForwardTestBarStore(tmp_path)
        from backend.forward_testing.models import ForwardTestBar
        base = _ts()
        # Pre-populate 3 warmup bars (warmup_bars_required=5)
        for i in range(3):
            bar_store.append_bar(ForwardTestBar(
                session_id=_SESSION_ID, bar_index=i,
                bar_timestamp=base + timedelta(days=i),
                open=100.0, high=105.0, low=95.0, close=102.0, volume=1e6,
                source_mode="provider", provider_name="yahoo",
                is_warmup_bar=True, processed_at=_now(),
            ))

        session = _make_session(
            warmup=5, watermark=2,
            bars_evaluated=3, signal_eligible_bars_processed=0,
            last_processed_bar_timestamp=base + timedelta(days=2),
        )
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        # One new bar at index 3 — still inside warmup window
        _run_poll(svc, session, mock_ohlcv, [base + timedelta(days=3)])

        written: ForwardTestSession = mock_repo.update.call_args.args[0]
        # Still in warmup; no eligible bars
        assert written.signal_eligible_bars_processed == 0


# ---------------------------------------------------------------------------
# 8. Watermark inconsistency: watermark > max stored bar_index
# ---------------------------------------------------------------------------

class TestWatermarkInconsistencyReset:
    def test_watermark_greater_than_max_stored_resets_and_recomputes(self, tmp_path):
        """If watermark > max stored bar_index, it is reset so bars are re-evaluated."""
        bar_store = ForwardTestBarStore(tmp_path)
        from backend.forward_testing.models import ForwardTestBar
        ts1 = _ts(days=1)
        bar_store.append_bar(ForwardTestBar(
            session_id=_SESSION_ID, bar_index=0, bar_timestamp=ts1,
            open=100.0, high=105.0, low=95.0, close=102.0, volume=1e6,
            source_mode="provider", provider_name="yahoo",
            is_warmup_bar=False, processed_at=_now(),
        ))

        # Watermark claims bar_index=99 but only index 0 is stored — inconsistency
        session = _make_session(
            watermark=99,
            bars_evaluated=1,
            signal_eligible_bars_processed=0,
            last_processed_bar_timestamp=ts1,
        )
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        # One new bar (index 1) arrives
        ts2 = _ts(days=2)
        _run_poll(svc, session, mock_ohlcv, [ts2])

        written: ForwardTestSession = mock_repo.update.call_args.args[0]
        # Watermark was reset (99 > 0), so bar at index 1 is treated as new_for_evaluation
        assert written.signal_eligible_bars_processed >= 1
        assert written.last_computed_bar_index == 1

    def test_watermark_equals_max_stored_no_reset(self, tmp_path):
        """Watermark at exact max stored index is valid — no reset, new bars counted."""
        bar_store = ForwardTestBarStore(tmp_path)
        from backend.forward_testing.models import ForwardTestBar
        ts1 = _ts(days=1)
        bar_store.append_bar(ForwardTestBar(
            session_id=_SESSION_ID, bar_index=0, bar_timestamp=ts1,
            open=100.0, high=105.0, low=95.0, close=102.0, volume=1e6,
            source_mode="provider", provider_name="yahoo",
            is_warmup_bar=False, processed_at=_now(),
        ))

        session = _make_session(
            watermark=0,
            bars_evaluated=1, signal_eligible_bars_processed=1,
            last_processed_bar_timestamp=ts1,
        )
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        ts2 = _ts(days=2)
        _run_poll(svc, session, mock_ohlcv, [ts2])

        written: ForwardTestSession = mock_repo.update.call_args.args[0]
        # Only the new bar (index 1) is above watermark=0 → eligible count +1
        assert written.signal_eligible_bars_processed == 2
        assert written.last_computed_bar_index == 1


# ---------------------------------------------------------------------------
# 9–10. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_repeated_cycle_no_duplicate_signals(self, tmp_path):
        """
        Calling _poll_cycle twice with the same bar does not duplicate records.

        First call: bar stored → signal emitted via signal_store mock.
        Second call: provider re-delivers same bar → bar_store deduplicates →
                     early return → signal_store.append_signal NOT called again.
        """
        from backend.forward_testing.stores import ForwardTestSignalStore
        bar_store      = ForwardTestBarStore(tmp_path)
        real_sig_store = ForwardTestSignalStore(tmp_path)
        mock_repo = MagicMock()
        session = _make_session(watermark=None)
        mock_repo.load.return_value = session
        mock_repo.update.return_value = None

        svc = ForwardTestService(
            repository=mock_repo,
            bar_store=bar_store,
            signal_store=real_sig_store,
            ohlcv_service=MagicMock(),
            tool_registry=MagicMock(),
        )

        ts1 = _ts(days=1)

        # eval result with entry triggered; patch HistoricalEvaluationInput as well
        # so Pydantic validation doesn't block the evaluate_history mock from firing.
        bar_res = MagicMock()
        bar_res.bar_index = 0
        bar_res.entry_triggered = True
        bar_res.exit_triggered  = False
        bar_res.signals = []
        mock_eval = MagicMock()
        mock_eval.bar_results = [bar_res]

        def _run(bars):
            ohlcv_mock = MagicMock()
            ohlcv_mock.get_bars_since.return_value = [_make_ohlcv_bar(b) for b in bars]
            svc._ohlcv_service = ohlcv_mock
            plan = MagicMock(); draft = MagicMock(); draft.toolset = []
            with patch("backend.forward_testing.service.compute_tool_outputs_for_history",
                       return_value=MagicMock(tool_results=[])), \
                 patch("backend.forward_testing.service.build_bar_tool_outputs",
                       return_value={}), \
                 patch("backend.forward_testing.service.HistoricalEvaluationInput",
                       return_value=MagicMock()), \
                 patch("backend.forward_testing.service.evaluate_history",
                       return_value=mock_eval):
                return svc._poll_cycle(
                    session=session, owner_id=_USER_ID,
                    identity=_build_identity(), provider=_build_provider(),
                    plan=plan, draft=draft, calendar=MagicMock(), now_utc=_now(),
                )

        r1 = _run([ts1])
        assert r1.signals_generated == 1
        assert real_sig_store.count_signals(_SESSION_ID) == 1

        # Second call: provider re-delivers ts1 → early return, no new signal
        r2 = _run([ts1])
        assert r2.signals_generated == 0
        assert real_sig_store.count_signals(_SESSION_ID) == 1  # unchanged

    def test_repeated_cycle_does_not_inflate_eligible_count(self, tmp_path):
        """signal_eligible_bars_processed must not increase when no new bars arrive."""
        bar_store = ForwardTestBarStore(tmp_path)
        session = _make_session(watermark=None, signal_eligible_bars_processed=0)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        ts1 = _ts(days=1)
        # First call: 1 new bar
        _run_poll(svc, session, mock_ohlcv, [ts1])
        first_written: ForwardTestSession = mock_repo.update.call_args.args[0]
        assert first_written.signal_eligible_bars_processed == 1

        # Second call: same bar from provider (deduped); session now has watermark=0
        session2 = _make_session(watermark=0, signal_eligible_bars_processed=1,
                                 bars_evaluated=1, last_processed_bar_timestamp=ts1)
        mock_repo.reset_mock()
        # Provider re-delivers ts1 — all-duplicates early return, no update
        _run_poll(svc, session2, mock_ohlcv, [ts1])
        mock_repo.update.assert_not_called()


# ---------------------------------------------------------------------------
# 11. Manual /run-cycle route: watermark advances
# ---------------------------------------------------------------------------

class TestManualRunCycleCompatibility:
    def test_watermark_advances_after_poll_cycle(self, tmp_path):
        """
        _poll_cycle() (invoked by both run_cycle HTTP route and scheduler) must
        write last_computed_bar_index in repository.update().
        """
        bar_store = ForwardTestBarStore(tmp_path)
        session   = _make_session(status=ForwardTestSessionStatus.RUNNING, watermark=None)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        _run_poll(svc, session, mock_ohlcv, [_ts(days=1)])

        update_calls = mock_repo.update.call_args_list
        assert len(update_calls) == 1
        written: ForwardTestSession = update_calls[0].args[0]
        assert written.last_computed_bar_index is not None
        assert written.last_computed_bar_index == 0  # first bar, index 0


# ---------------------------------------------------------------------------
# 12. Watermark written atomically with counters
# ---------------------------------------------------------------------------

class TestWatermarkAtomicUpdate:
    def test_watermark_and_counters_written_in_single_update_call(self, tmp_path):
        """last_computed_bar_index and session counters must be in ONE update() call."""
        bar_store = ForwardTestBarStore(tmp_path)
        session = _make_session(watermark=None)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        _run_poll(svc, session, mock_ohlcv, [_ts(days=1)])

        # Exactly one update call for session counters + watermark
        assert mock_repo.update.call_count == 1
        written: ForwardTestSession = mock_repo.update.call_args.args[0]
        assert written.last_computed_bar_index is not None
        assert written.bars_evaluated >= 1


# ---------------------------------------------------------------------------
# 13. None watermark processes all indexed_new_bars
# ---------------------------------------------------------------------------

class TestNoneWatermarkProcessesAll:
    def test_none_watermark_all_new_bars_evaluated(self, tmp_path):
        bar_store = ForwardTestBarStore(tmp_path)
        session = _make_session(watermark=None)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        _run_poll(svc, session, mock_ohlcv, [_ts(days=1), _ts(days=2), _ts(days=3)])

        written: ForwardTestSession = mock_repo.update.call_args.args[0]
        # All 3 bars are signal-eligible (no warmup)
        assert written.signal_eligible_bars_processed == 3


# ---------------------------------------------------------------------------
# 14. Zero new bars from provider: no counters, no watermark change
# ---------------------------------------------------------------------------

class TestZeroNewBars:
    def test_zero_new_bars_no_update(self, tmp_path):
        bar_store = ForwardTestBarStore(tmp_path)
        session = _make_session(watermark=5, bars_evaluated=6,
                                signal_eligible_bars_processed=6)
        svc, mock_repo, _, mock_ohlcv = _make_service(session, bar_store)

        _run_poll(svc, session, mock_ohlcv, [])
        mock_repo.update.assert_not_called()

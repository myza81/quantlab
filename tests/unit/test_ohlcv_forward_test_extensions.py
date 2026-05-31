"""
Tests for Phase 4C.3 — OHLCVService forward-testing data-access primitives.

Covers:
  timeframe_to_timedelta():
    - correct durations for all canonical timeframes
    - raises ValueError for unsupported timeframe

  is_bar_finalized():
    - True when candle period + buffer has elapsed
    - False when bar is currently forming (period not started)
    - False when candle closed but buffer has not elapsed
    - False when candle period not yet elapsed
    - raises ValueError for naive bar_timestamp
    - raises ValueError for naive current_time
    - buffer_seconds=0 edge case (exactly at close)

  OHLCVService.get_recent_bars():
    - returns latest N finalized bars in ascending order
    - excludes the currently forming bar
    - returns fewer than limit when fewer finalized bars exist
    - empty provider response returns []
    - limit=0 raises ValueError
    - negative limit raises ValueError
    - naive reference_time raises ValueError
    - uses BYPASS_CACHE (no storage written)
    - unsupported timeframe raises ValueError

  OHLCVService.get_bars_since():
    - returns only finalized bars strictly after since_timestamp
    - bar exactly at since_timestamp is excluded
    - excludes forming bar (not finalized)
    - empty provider response returns []
    - naive since_timestamp raises ValueError
    - returns all qualifying bars (not capped)
    - uses BYPASS_CACHE (no storage written)

  UTC correctness:
    - UTC-aware timestamps are handled correctly throughout
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.range_provider import RangeProviderAdapter
from backend.services.ohlcv_service import (
    OHLCVService,
    is_bar_finalized,
    timeframe_to_timedelta,
)

_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bar(
    timestamp: datetime,
    symbol: str = "AAPL",
    timeframe: str = "1d",
) -> NormalizedOHLCV:
    return NormalizedOHLCV(
        symbol=symbol,
        asset_class="equity",
        venue="NASDAQ",
        timeframe=timeframe,
        source="yahoo",
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1_000_000.0,
    )


def _identity(timeframe: str = "1d", symbol: str = "AAPL") -> DatasetIdentity:
    instrument = Instrument(
        symbol=symbol,
        asset_class="equity",
        exchange="NASDAQ",
    )
    return DatasetIdentity(
        instrument=instrument,
        provider="yahoo",
        timeframe=timeframe,
        adjustment_mode=AdjustmentMode.ADJUSTED,
    )


class _StubProvider(RangeProviderAdapter):
    """Stub that returns a pre-configured list of bars filtered to [start, end]."""

    def __init__(self, bars: list[NormalizedOHLCV]) -> None:
        self._bars = bars
        self.fetch_calls: list[tuple[datetime, datetime]] = []

    @property
    def provider_name(self) -> str:
        return "stub"

    def load(self, **kwargs: object) -> list[NormalizedOHLCV]:
        return self._bars

    def fetch(self, start: datetime, end: datetime, **kwargs: object) -> list[NormalizedOHLCV]:
        self.fetch_calls.append((start, end))
        return [b for b in self._bars if start <= b.timestamp <= end]


def _service(tmp_path: Path) -> OHLCVService:
    return OHLCVService(tmp_path)


# ---------------------------------------------------------------------------
# timeframe_to_timedelta
# ---------------------------------------------------------------------------

class TestTimeframeToTimedelta:
    def test_1m(self) -> None:
        assert timeframe_to_timedelta("1m") == timedelta(minutes=1)

    def test_5m(self) -> None:
        assert timeframe_to_timedelta("5m") == timedelta(minutes=5)

    def test_15m(self) -> None:
        assert timeframe_to_timedelta("15m") == timedelta(minutes=15)

    def test_30m(self) -> None:
        assert timeframe_to_timedelta("30m") == timedelta(minutes=30)

    def test_1h(self) -> None:
        assert timeframe_to_timedelta("1h") == timedelta(hours=1)

    def test_4h(self) -> None:
        assert timeframe_to_timedelta("4h") == timedelta(hours=4)

    def test_1d(self) -> None:
        assert timeframe_to_timedelta("1d") == timedelta(days=1)

    def test_1w(self) -> None:
        assert timeframe_to_timedelta("1w") == timedelta(weeks=1)

    def test_1M_approximation(self) -> None:
        assert timeframe_to_timedelta("1M") == timedelta(days=30)

    def test_unsupported_timeframe_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            timeframe_to_timedelta("2w")

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            timeframe_to_timedelta("")

    def test_mixed_case_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            timeframe_to_timedelta("1D")


# ---------------------------------------------------------------------------
# is_bar_finalized
# ---------------------------------------------------------------------------

class TestIsBarFinalized:
    # Reference: 2026-05-29 14:00:00 UTC is "now"
    _NOW = datetime(2026, 5, 29, 14, 0, 0, tzinfo=_UTC)

    def test_1d_bar_finalized_well_past_close(self) -> None:
        # Bar open 2026-05-28 00:00, closes 2026-05-29 00:00, buffer 60s → finalizes 00:01
        bar_ts = datetime(2026, 5, 28, 0, 0, 0, tzinfo=_UTC)
        assert is_bar_finalized(bar_ts, "1d", current_time=self._NOW, buffer_seconds=60)

    def test_1h_bar_finalized_one_hour_ago(self) -> None:
        # Bar open 13:00, closes 14:00, NOW is 14:01 → 60s buffer satisfied exactly
        bar_ts = datetime(2026, 5, 29, 12, 0, 0, tzinfo=_UTC)  # 12:00 bar, closes 13:00
        assert is_bar_finalized(bar_ts, "1h", current_time=self._NOW, buffer_seconds=60)

    def test_1h_forming_bar_not_finalized(self) -> None:
        # Bar open 14:00, closes 15:00, NOW is 14:00 → not finalized
        bar_ts = datetime(2026, 5, 29, 14, 0, 0, tzinfo=_UTC)
        assert not is_bar_finalized(bar_ts, "1h", current_time=self._NOW, buffer_seconds=60)

    def test_1h_bar_closed_but_buffer_not_elapsed(self) -> None:
        # Bar open 13:00, closes 14:00, buffer 120s → finalizes at 14:02
        # NOW is 14:00 → buffer not elapsed
        bar_ts = datetime(2026, 5, 29, 13, 0, 0, tzinfo=_UTC)
        assert not is_bar_finalized(bar_ts, "1h", current_time=self._NOW, buffer_seconds=120)

    def test_1h_bar_exactly_at_close_plus_buffer(self) -> None:
        # Bar open 13:00, closes 14:00, buffer 0 → exact close time is finalized
        bar_ts = datetime(2026, 5, 29, 13, 0, 0, tzinfo=_UTC)
        current = datetime(2026, 5, 29, 14, 0, 0, tzinfo=_UTC)
        assert is_bar_finalized(bar_ts, "1h", current_time=current, buffer_seconds=0)

    def test_1h_bar_one_second_before_finalization(self) -> None:
        # Bar open 13:00, closes 14:00, buffer 60s → finalizes at 14:01:00
        # current is 14:00:59 → not yet finalized
        bar_ts = datetime(2026, 5, 29, 13, 0, 0, tzinfo=_UTC)
        current = datetime(2026, 5, 29, 14, 0, 59, tzinfo=_UTC)
        assert not is_bar_finalized(bar_ts, "1h", current_time=current, buffer_seconds=60)

    def test_1h_bar_exactly_at_finalization_boundary(self) -> None:
        # Bar open 13:00, closes 14:00, buffer 60s → finalizes at 14:01:00
        # current is exactly 14:01:00 → finalized
        bar_ts = datetime(2026, 5, 29, 13, 0, 0, tzinfo=_UTC)
        current = datetime(2026, 5, 29, 14, 1, 0, tzinfo=_UTC)
        assert is_bar_finalized(bar_ts, "1h", current_time=current, buffer_seconds=60)

    def test_naive_bar_timestamp_raises(self) -> None:
        naive_ts = datetime(2026, 5, 28, 0, 0, 0)  # no tzinfo
        with pytest.raises(ValueError, match="UTC-aware"):
            is_bar_finalized(naive_ts, "1d", current_time=self._NOW, buffer_seconds=60)

    def test_naive_current_time_raises(self) -> None:
        bar_ts = datetime(2026, 5, 28, 0, 0, 0, tzinfo=_UTC)
        naive_now = datetime(2026, 5, 29, 14, 0, 0)  # no tzinfo
        with pytest.raises(ValueError, match="UTC-aware"):
            is_bar_finalized(bar_ts, "1d", current_time=naive_now, buffer_seconds=60)

    def test_15m_bar_finalized(self) -> None:
        # Bar 13:45, closes 14:00, buffer 60s → finalizes at 14:01
        bar_ts = datetime(2026, 5, 29, 13, 45, 0, tzinfo=_UTC)
        current = datetime(2026, 5, 29, 14, 2, 0, tzinfo=_UTC)
        assert is_bar_finalized(bar_ts, "15m", current_time=current, buffer_seconds=60)

    def test_15m_forming_bar_not_finalized(self) -> None:
        # Bar 13:45, closes 14:00, buffer 60s, current is 13:59
        bar_ts = datetime(2026, 5, 29, 13, 45, 0, tzinfo=_UTC)
        current = datetime(2026, 5, 29, 13, 59, 0, tzinfo=_UTC)
        assert not is_bar_finalized(bar_ts, "15m", current_time=current, buffer_seconds=60)


# ---------------------------------------------------------------------------
# OHLCVService.get_recent_bars
# ---------------------------------------------------------------------------

class TestGetRecentBars:
    # Reference: 2026-05-29 15:00 UTC (market session well underway)
    _NOW = datetime(2026, 5, 29, 15, 0, 0, tzinfo=_UTC)

    def _make_daily_bars(self, dates: list[str]) -> list[NormalizedOHLCV]:
        return [
            _bar(datetime.fromisoformat(f"{d}T00:00:00+00:00"), timeframe="1d")
            for d in dates
        ]

    def test_returns_latest_n_finalized_bars_ascending(self, tmp_path: Path) -> None:
        bars = self._make_daily_bars([
            "2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28",
        ])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_recent_bars(
            _identity("1d"), limit=3, provider=provider,
            reference_time=self._NOW, bar_finalization_buffer_seconds=60,
        )
        assert len(result) == 3
        timestamps = [r.timestamp for r in result]
        assert timestamps == sorted(timestamps)
        # most recent 3 of 4 finalized bars
        assert result[-1].timestamp == datetime(2026, 5, 28, 0, 0, 0, tzinfo=_UTC)

    def test_excludes_forming_bar(self, tmp_path: Path) -> None:
        # 2026-05-29 bar opened at 00:00, closes tomorrow — still forming at 15:00
        bars = self._make_daily_bars(["2026-05-27", "2026-05-28", "2026-05-29"])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_recent_bars(
            _identity("1d"), limit=10, provider=provider,
            reference_time=self._NOW, bar_finalization_buffer_seconds=60,
        )
        timestamps = [r.timestamp for r in result]
        assert datetime(2026, 5, 29, 0, 0, 0, tzinfo=_UTC) not in timestamps

    def test_returns_fewer_than_limit_when_not_enough_finalized(
        self, tmp_path: Path
    ) -> None:
        bars = self._make_daily_bars(["2026-05-27", "2026-05-28"])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_recent_bars(
            _identity("1d"), limit=10, provider=provider,
            reference_time=self._NOW, bar_finalization_buffer_seconds=60,
        )
        assert len(result) == 2

    def test_empty_provider_returns_empty_list(self, tmp_path: Path) -> None:
        provider = _StubProvider([])
        svc = _service(tmp_path)
        result = svc.get_recent_bars(
            _identity("1d"), limit=5, provider=provider,
            reference_time=self._NOW,
        )
        assert result == []

    def test_limit_zero_raises_value_error(self, tmp_path: Path) -> None:
        provider = _StubProvider([])
        svc = _service(tmp_path)
        with pytest.raises(ValueError, match="limit"):
            svc.get_recent_bars(
                _identity("1d"), limit=0, provider=provider,
                reference_time=self._NOW,
            )

    def test_negative_limit_raises_value_error(self, tmp_path: Path) -> None:
        provider = _StubProvider([])
        svc = _service(tmp_path)
        with pytest.raises(ValueError, match="limit"):
            svc.get_recent_bars(
                _identity("1d"), limit=-1, provider=provider,
                reference_time=self._NOW,
            )

    def test_naive_reference_time_raises_value_error(self, tmp_path: Path) -> None:
        provider = _StubProvider([])
        svc = _service(tmp_path)
        naive_now = datetime(2026, 5, 29, 15, 0, 0)
        with pytest.raises(ValueError, match="UTC-aware"):
            svc.get_recent_bars(
                _identity("1d"), limit=5, provider=provider,
                reference_time=naive_now,
            )

    def test_uses_bypass_cache_no_storage_written(self, tmp_path: Path) -> None:
        bars = self._make_daily_bars(["2026-05-27", "2026-05-28"])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        svc.get_recent_bars(
            _identity("1d"), limit=2, provider=provider,
            reference_time=self._NOW,
        )
        # BYPASS_CACHE means no Parquet file should have been written
        parquet_files = list(tmp_path.rglob("*.parquet"))
        assert parquet_files == []

    def test_unsupported_timeframe_caught_by_helper(self, tmp_path: Path) -> None:
        # DatasetIdentity validates timeframes at construction; unsupported values
        # never reach OHLCVService.  This test verifies the helper directly.
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            timeframe_to_timedelta("2w")

    def test_hourly_bars_exclude_forming_and_just_closed_bar(
        self, tmp_path: Path
    ) -> None:
        # reference_time = 15:00 UTC
        # 12:00 bar: closes 13:00, finalized at 13:01 → included
        # 13:00 bar: closes 14:00, finalized at 14:01 → included
        # 14:00 bar: closes 15:00, +60s buffer → finalized at 15:01 > 15:00 → excluded
        # 15:00 bar: currently forming → excluded
        bars = [
            _bar(datetime(2026, 5, 29, h, 0, 0, tzinfo=_UTC), timeframe="1h")
            for h in [12, 13, 14, 15]
        ]
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_recent_bars(
            _identity("1h"), limit=10, provider=provider,
            reference_time=self._NOW, bar_finalization_buffer_seconds=60,
        )
        result_hours = [r.timestamp.hour for r in result]
        assert 15 not in result_hours  # forming
        assert 14 not in result_hours  # buffer not elapsed (closes at 15:00, +60s = 15:01)
        assert 13 in result_hours      # finalized at 14:01 < 15:00
        assert 12 in result_hours      # finalized at 13:01 < 15:00

    def test_safety_buffer_zero_includes_just_closed_bar(
        self, tmp_path: Path
    ) -> None:
        # Bar opens 14:00, closes 15:00, reference_time is exactly 15:00, buffer 0
        bar_ts = datetime(2026, 5, 29, 14, 0, 0, tzinfo=_UTC)
        provider = _StubProvider([_bar(bar_ts, timeframe="1h")])
        svc = _service(tmp_path)
        result = svc.get_recent_bars(
            _identity("1h"), limit=5, provider=provider,
            reference_time=self._NOW, bar_finalization_buffer_seconds=0,
        )
        # 14:00 bar closes at 15:00 + 0s = 15:00 <= reference_time 15:00 → finalized
        assert len(result) == 1
        assert result[0].timestamp == bar_ts


# ---------------------------------------------------------------------------
# OHLCVService.get_bars_since
# ---------------------------------------------------------------------------

class TestGetBarsSince:
    _NOW = datetime(2026, 5, 29, 15, 0, 0, tzinfo=_UTC)
    _CURSOR = datetime(2026, 5, 28, 0, 0, 0, tzinfo=_UTC)  # last processed bar

    def _make_daily_bars(self, dates: list[str]) -> list[NormalizedOHLCV]:
        return [
            _bar(datetime.fromisoformat(f"{d}T00:00:00+00:00"), timeframe="1d")
            for d in dates
        ]

    def test_returns_bars_strictly_after_cursor(self, tmp_path: Path) -> None:
        bars = self._make_daily_bars([
            "2026-05-27", "2026-05-28", "2026-05-29",
        ])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_bars_since(
            _identity("1d"), since_timestamp=self._CURSOR,
            provider=provider, reference_time=self._NOW,
            bar_finalization_buffer_seconds=60,
        )
        timestamps = [r.timestamp for r in result]
        # 2026-05-28 is the cursor — excluded; 2026-05-29 is forming — excluded
        assert datetime(2026, 5, 28, 0, 0, 0, tzinfo=_UTC) not in timestamps
        assert datetime(2026, 5, 27, 0, 0, 0, tzinfo=_UTC) not in timestamps

    def test_bar_at_exactly_cursor_timestamp_excluded(self, tmp_path: Path) -> None:
        cursor = datetime(2026, 5, 28, 0, 0, 0, tzinfo=_UTC)
        bar_at_cursor = _bar(cursor, timeframe="1d")
        provider = _StubProvider([bar_at_cursor])
        svc = _service(tmp_path)
        result = svc.get_bars_since(
            _identity("1d"), since_timestamp=cursor,
            provider=provider, reference_time=self._NOW,
        )
        assert result == []

    def test_excludes_forming_bar(self, tmp_path: Path) -> None:
        bars = self._make_daily_bars(["2026-05-29"])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_bars_since(
            _identity("1d"), since_timestamp=self._CURSOR,
            provider=provider, reference_time=self._NOW,
            bar_finalization_buffer_seconds=60,
        )
        # 2026-05-29 00:00 bar closes on 2026-05-30 00:00 — not yet finalized
        assert result == []

    def test_empty_provider_returns_empty_list(self, tmp_path: Path) -> None:
        provider = _StubProvider([])
        svc = _service(tmp_path)
        result = svc.get_bars_since(
            _identity("1d"), since_timestamp=self._CURSOR,
            provider=provider, reference_time=self._NOW,
        )
        assert result == []

    def test_naive_since_timestamp_raises_value_error(self, tmp_path: Path) -> None:
        provider = _StubProvider([])
        svc = _service(tmp_path)
        naive_ts = datetime(2026, 5, 28, 0, 0, 0)
        with pytest.raises(ValueError, match="UTC-aware"):
            svc.get_bars_since(
                _identity("1d"), since_timestamp=naive_ts,
                provider=provider, reference_time=self._NOW,
            )

    def test_naive_reference_time_raises_value_error(self, tmp_path: Path) -> None:
        provider = _StubProvider([])
        svc = _service(tmp_path)
        naive_now = datetime(2026, 5, 29, 15, 0, 0)
        with pytest.raises(ValueError, match="UTC-aware"):
            svc.get_bars_since(
                _identity("1d"), since_timestamp=self._CURSOR,
                provider=provider, reference_time=naive_now,
            )

    def test_uses_bypass_cache_no_storage_written(self, tmp_path: Path) -> None:
        bars = self._make_daily_bars(["2026-05-27"])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        svc.get_bars_since(
            _identity("1d"), since_timestamp=self._CURSOR,
            provider=provider, reference_time=self._NOW,
        )
        parquet_files = list(tmp_path.rglob("*.parquet"))
        assert parquet_files == []

    def test_returns_all_qualifying_bars_not_just_one(self, tmp_path: Path) -> None:
        # Create 3 finalized bars after cursor: 2026-05-25, 2026-05-26, 2026-05-27
        cursor = datetime(2026, 5, 24, 0, 0, 0, tzinfo=_UTC)
        bars = self._make_daily_bars(["2026-05-25", "2026-05-26", "2026-05-27"])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_bars_since(
            _identity("1d"), since_timestamp=cursor,
            provider=provider, reference_time=self._NOW,
            bar_finalization_buffer_seconds=60,
        )
        assert len(result) == 3

    def test_result_is_ascending(self, tmp_path: Path) -> None:
        # Provider returns bars in ascending order (normalizer enforces monotonicity).
        # Verify get_bars_since preserves ascending order from the normalized output.
        cursor = datetime(2026, 5, 24, 0, 0, 0, tzinfo=_UTC)
        bars = self._make_daily_bars(["2026-05-25", "2026-05-26", "2026-05-27"])
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_bars_since(
            _identity("1d"), since_timestamp=cursor,
            provider=provider, reference_time=self._NOW,
            bar_finalization_buffer_seconds=60,
        )
        timestamps = [r.timestamp for r in result]
        assert timestamps == sorted(timestamps)

    def test_hourly_catchup_multiple_finalized_bars(self, tmp_path: Path) -> None:
        # Cursor at 10:00; 1h bars at 11:00, 12:00, 13:00 are finalized by 15:00
        cursor = datetime(2026, 5, 29, 10, 0, 0, tzinfo=_UTC)
        bars = [
            _bar(datetime(2026, 5, 29, h, 0, 0, tzinfo=_UTC), timeframe="1h")
            for h in [10, 11, 12, 13, 14, 15]
        ]
        provider = _StubProvider(bars)
        svc = _service(tmp_path)
        result = svc.get_bars_since(
            _identity("1h"), since_timestamp=cursor,
            provider=provider, reference_time=self._NOW,
            bar_finalization_buffer_seconds=60,
        )
        result_hours = [r.timestamp.hour for r in result]
        assert 10 not in result_hours   # cursor — excluded
        assert 11 in result_hours       # 11:00 closes 12:00, finalized at 12:01
        assert 12 in result_hours       # 12:00 closes 13:00, finalized at 13:01
        assert 13 in result_hours       # 13:00 closes 14:00, finalized at 14:01
        assert 14 not in result_hours   # 14:00 closes 15:00 + 60s = 15:01 > 15:00 — not finalized
        assert 15 not in result_hours   # forming bar

"""
Tests for OHLCVService.get_ohlcv_by_provider_name (registry integration).

Covers:
- Resolving an adapter from registry and delegating to get_ohlcv()
- ProviderNotFoundError propagates when provider name is not registered
- Registered provider produces correct candles
- Registry isolation: only the named provider is called
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.data.models.dataset import DatasetIdentity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.provider_registry import (
    ProviderNotFoundError,
    ProviderRegistry,
)
from backend.data_providers.range_provider import RangeProviderAdapter
from backend.services.ohlcv_service import OHLCVService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _identity(provider: str = "testprovider") -> DatasetIdentity:
    inst = Instrument(
        symbol="AAPL",
        asset_class="equity",
        exchange="NASDAQ",
        currency="USD",
    )
    return DatasetIdentity(
        instrument=inst,
        provider=provider,
        timeframe="1d",
        adjustment_mode=AdjustmentMode.ADJUSTED,
    )


def _candle(ts: datetime, source: str = "stub") -> NormalizedOHLCV:
    return NormalizedOHLCV(
        symbol="AAPL",
        asset_class="equity",
        venue="NASDAQ",
        timeframe="1d",
        source=source,
        timestamp=ts,
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1_000_000.0,
    )


class _StubRangeAdapter(RangeProviderAdapter):
    """Returns a fixed list of candles regardless of input range."""

    def __init__(self, candles: list[NormalizedOHLCV]) -> None:
        self._candles = candles

    @property
    def provider_name(self) -> str:
        return "stub"

    def load(self, **kwargs: object) -> list[NormalizedOHLCV]:
        return self._candles

    def fetch(
        self, start: datetime, end: datetime, **kwargs: object
    ) -> list[NormalizedOHLCV]:
        return [c for c in self._candles if start <= c.timestamp <= end]


# ---------------------------------------------------------------------------
# TestGetOHLCVByProviderName
# ---------------------------------------------------------------------------

class TestGetOHLCVByProviderName:
    def test_resolves_from_registry_and_returns_candles(self, tmp_path: Path) -> None:
        start = _utc(2023, 1, 1)
        end = _utc(2023, 1, 5)
        candles = [_candle(_utc(2023, 1, d), source="stub") for d in range(2, 6)]

        adapter = _StubRangeAdapter(candles)
        registry = ProviderRegistry()
        registry.register("stub", adapter)

        service = OHLCVService(tmp_path)
        identity = _identity("stub")

        result = service.get_ohlcv_by_provider_name(identity, start, end, "stub", registry)
        assert len(result) == 4

    def test_missing_provider_name_raises(self, tmp_path: Path) -> None:
        registry = ProviderRegistry()
        service = OHLCVService(tmp_path)
        identity = _identity("notregistered")

        with pytest.raises(ProviderNotFoundError, match="notregistered"):
            service.get_ohlcv_by_provider_name(
                identity, _utc(2023, 1, 1), _utc(2023, 1, 5),
                "notregistered", registry,
            )

    def test_correct_provider_is_called_not_other(self, tmp_path: Path) -> None:
        alpha_calls: list[int] = []
        beta_calls: list[int] = []

        class _AlphaAdapter(_StubRangeAdapter):
            @property
            def provider_name(self) -> str:
                return "alpha"
            def fetch(self, start: datetime, end: datetime, **kw: object) -> list[NormalizedOHLCV]:
                alpha_calls.append(1)
                return super().fetch(start, end, **kw)

        class _BetaAdapter(_StubRangeAdapter):
            @property
            def provider_name(self) -> str:
                return "beta"
            def fetch(self, start: datetime, end: datetime, **kw: object) -> list[NormalizedOHLCV]:
                beta_calls.append(1)
                return super().fetch(start, end, **kw)

        candles = [_candle(_utc(2023, 1, 3), source="alpha")]
        alpha = _AlphaAdapter(candles)
        beta = _BetaAdapter([])

        registry = ProviderRegistry()
        registry.register("alpha", alpha)
        registry.register("beta", beta)

        service = OHLCVService(tmp_path)
        identity = _identity("alpha")
        service.get_ohlcv_by_provider_name(
            identity, _utc(2023, 1, 1), _utc(2023, 1, 5), "alpha", registry
        )

        assert len(alpha_calls) > 0
        assert len(beta_calls) == 0

    def test_provider_name_case_insensitive(self, tmp_path: Path) -> None:
        candles = [_candle(_utc(2023, 1, 3), source="stub")]
        adapter = _StubRangeAdapter(candles)

        registry = ProviderRegistry()
        registry.register("Stub", adapter)

        service = OHLCVService(tmp_path)
        identity = _identity("stub")

        # Should resolve even with different case
        result = service.get_ohlcv_by_provider_name(
            identity, _utc(2023, 1, 1), _utc(2023, 1, 5), "STUB", registry
        )
        assert len(result) == 1

    def test_naive_start_still_raises(self, tmp_path: Path) -> None:
        registry = ProviderRegistry()
        registry.register("stub", _StubRangeAdapter([]))
        service = OHLCVService(tmp_path)
        identity = _identity("stub")

        with pytest.raises(ValueError, match="timezone-aware"):
            service.get_ohlcv_by_provider_name(
                identity, datetime(2023, 1, 1), _utc(2023, 1, 5), "stub", registry
            )


# ---------------------------------------------------------------------------
# TestProviderIsolationViaRegistry
# ---------------------------------------------------------------------------

class TestProviderIsolationViaRegistry:
    def test_two_providers_write_independent_datasets(self, tmp_path: Path) -> None:
        """Confirm registry-routed ingestion respects provider-aware storage."""
        yahoo_candles = [_candle(_utc(2023, 1, 3), source="yahoo")]
        polygon_candles = [
            NormalizedOHLCV(
                symbol="AAPL", asset_class="equity", venue="NASDAQ",
                timeframe="1d", source="polygon",
                timestamp=_utc(2023, 1, 3),
                open=101.0, high=106.0, low=100.0, close=104.0, volume=2_000_000.0,
            )
        ]

        yahoo_adapter = _StubRangeAdapter(yahoo_candles)
        polygon_adapter = _StubRangeAdapter(polygon_candles)

        registry = ProviderRegistry()
        registry.register("yahoo", yahoo_adapter)
        registry.register("polygon", polygon_adapter)

        inst = Instrument(symbol="AAPL", asset_class="equity", exchange="NASDAQ", currency="USD")
        yahoo_identity = DatasetIdentity(instrument=inst, provider="yahoo", timeframe="1d", adjustment_mode=AdjustmentMode.ADJUSTED)
        polygon_identity = DatasetIdentity(instrument=inst, provider="polygon", timeframe="1d", adjustment_mode=AdjustmentMode.ADJUSTED)

        service = OHLCVService(tmp_path)
        start, end = _utc(2023, 1, 1), _utc(2023, 1, 5)

        yahoo_result = service.get_ohlcv_by_provider_name(yahoo_identity, start, end, "yahoo", registry)
        polygon_result = service.get_ohlcv_by_provider_name(polygon_identity, start, end, "polygon", registry)

        assert len(yahoo_result) == 1
        assert len(polygon_result) == 1
        assert yahoo_result[0].source == "yahoo"
        assert polygon_result[0].source == "polygon"
        # Prices differ — confirming they are independent datasets
        assert yahoo_result[0].close != polygon_result[0].close

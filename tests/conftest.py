from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.data.schemas import NormalizedOHLCV

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_ohlcv(**overrides: object) -> NormalizedOHLCV:
    """Factory for NormalizedOHLCV with sensible defaults."""
    defaults: dict[str, object] = dict(
        symbol="BTCUSDT",
        asset_class="crypto",
        venue="binance",
        timeframe="1h",
        source="csv",
        timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        open=42000.0,
        high=42500.0,
        low=41800.0,
        close=42200.0,
        volume=1250.5,
    )
    defaults.update(overrides)
    return NormalizedOHLCV(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def sample_record() -> NormalizedOHLCV:
    return make_ohlcv()


@pytest.fixture
def sample_series() -> list[NormalizedOHLCV]:
    return [
        make_ohlcv(timestamp=datetime(2024, 1, 1, i, 0, 0, tzinfo=timezone.utc))
        for i in range(5)
    ]


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR

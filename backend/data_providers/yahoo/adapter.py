"""
Yahoo Finance provider adapter.

Fetches historical OHLCV data via yfinance and converts it to the
canonical NormalizedOHLCV schema.

Isolation contract:
- yfinance is imported ONLY inside this module
- No yfinance objects leave this module (DataFrame, Ticker, etc.)
- NormalizedOHLCV is the only output type
- Strategies must never import from this module

Supported timeframes (maps to yfinance interval parameter):
    1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M

Unsupported timeframes raise ValueError at construction time.

End date handling:
    yfinance treats `end` as exclusive. This adapter adds 1 day to the
    requested end for daily/weekly/monthly intervals so the end date candle
    is included in the result, honouring the RangeProviderAdapter contract
    (both bounds inclusive).

Empty result:
    An invalid or unrecognised ticker symbol causes yfinance to return an
    empty DataFrame. The adapter returns [] rather than raising, consistent
    with the RangeProviderAdapter contract.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import yfinance as yf  # type: ignore[import-untyped]

from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.range_provider import RangeProviderAdapter

logger = logging.getLogger(__name__)

# Maps canonical QuantLab timeframe → yfinance interval string
SUPPORTED_TIMEFRAMES: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mo",
}

# Intervals where end is bumped +1 day so end-date candle is included
_DAILY_PLUS_INTERVALS: frozenset[str] = frozenset({"1d", "1wk", "1mo"})


class YahooAdapterError(Exception):
    """Raised when yfinance returns an unexpected transport or schema error."""


class YahooFinanceAdapter(RangeProviderAdapter):
    """
    RangeProviderAdapter backed by Yahoo Finance via yfinance.

    Responsibilities:
    - Accept per-request fetch(start, end) calls
    - Translate to yfinance Ticker.history() call
    - Convert the returned DataFrame to list[NormalizedOHLCV]
    - Absorb SDK-level objects; never expose them upstream

    Not responsible for:
    - Normalization (DataNormalizer is called by OHLCVService after fetch)
    - Storage writes
    - Coverage tracking
    - Live / streaming data
    """

    def __init__(
        self,
        symbol: str,
        asset_class: str,
        venue: str,
        timeframe: str,
        adjustment_mode: str = "adjusted",
    ) -> None:
        """
        Args:
            symbol:          Internal canonical symbol (e.g. "AAPL", "1155.KL").
            asset_class:     e.g. "equity", "crypto", "fx"
            venue:           Exchange or venue name (e.g. "NASDAQ", "KLSE")
            timeframe:       Canonical QuantLab timeframe (must be in SUPPORTED_TIMEFRAMES)
            adjustment_mode: "adjusted" (default) or "raw". Controls yfinance auto_adjust.
        """
        if not symbol.strip():
            raise ValueError("symbol must not be empty")
        if not asset_class.strip():
            raise ValueError("asset_class must not be empty")

        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"timeframe '{timeframe}' is not supported by YahooFinanceAdapter. "
                f"Supported: {sorted(SUPPORTED_TIMEFRAMES)}"
            )

        self._symbol = symbol.strip()
        self._asset_class = asset_class.strip()
        self._venue = venue.strip()
        self._timeframe = timeframe
        self._interval = SUPPORTED_TIMEFRAMES[timeframe]
        self._adjustment_mode = adjustment_mode
        self._auto_adjust = adjustment_mode != "raw"

    @property
    def provider_name(self) -> str:
        return "yahoo"

    def load(self, **kwargs: object) -> list[NormalizedOHLCV]:
        """Not implemented — use fetch(start, end) for range-based retrieval."""
        raise NotImplementedError(
            "YahooFinanceAdapter.load() is not supported. "
            "Use fetch(start, end) for range-based retrieval."
        )

    def fetch(
        self,
        start: datetime,
        end: datetime,
        **kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Fetch historical OHLCV from Yahoo Finance for [start, end] inclusive.

        Args:
            start: UTC-aware datetime (lower bound, inclusive).
            end:   UTC-aware datetime (upper bound, inclusive).

        Returns:
            list[NormalizedOHLCV] — may be empty for invalid symbols or empty ranges.

        Raises:
            ValueError:        if start or end are timezone-naive.
            YahooAdapterError: if yfinance raises an unexpected exception.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be UTC-aware datetimes")

        fetch_end = _inclusive_end(end, self._interval)

        history_start, history_end = _history_bounds(start, fetch_end, self._interval)

        logger.debug(
            "YahooFinanceAdapter: fetching %s %s [%s → %s]",
            self._symbol,
            self._interval,
            history_start,
            history_end,
        )

        try:
            ticker = yf.Ticker(self._symbol)
            df = ticker.history(
                start=history_start,
                end=history_end,
                interval=self._interval,
                auto_adjust=self._auto_adjust,
                prepost=False,
            )
        except Exception as exc:
            raise YahooAdapterError(
                f"yfinance fetch failed for '{self._symbol}' "
                f"({self._interval}, {history_start}→{history_end}): {exc}"
            ) from exc

        if df is None or df.empty:
            logger.debug(
                "YahooFinanceAdapter: empty response for '%s' [%s→%s]",
                self._symbol,
                history_start,
                history_end,
            )
            return []

        return self._convert(df)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _convert(self, df: Any) -> list[NormalizedOHLCV]:
        """Convert a yfinance history DataFrame to list[NormalizedOHLCV]."""
        records: list[NormalizedOHLCV] = []

        for ts, row in df.iterrows():
            try:
                # ts is a pd.Timestamp; convert to UTC-aware datetime
                if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                    timestamp = ts.to_pydatetime().astimezone(timezone.utc)
                else:
                    timestamp = ts.to_pydatetime().replace(tzinfo=timezone.utc)

                record = NormalizedOHLCV(
                    symbol=self._symbol,
                    asset_class=self._asset_class,
                    venue=self._venue,
                    timeframe=self._timeframe,
                    source="yahoo",
                    timestamp=timestamp,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
                records.append(record)
            except Exception as exc:
                logger.warning(
                    "YahooFinanceAdapter: skipping malformed row for '%s' at %s — %s",
                    self._symbol,
                    ts,
                    exc,
                )

        logger.debug(
            "YahooFinanceAdapter: converted %d records for '%s'",
            len(records),
            self._symbol,
        )
        return records


def _inclusive_end(end: datetime, interval: str) -> datetime:
    """
    Adjust end datetime so yfinance includes the end-date candle.

    yfinance's `end` parameter is exclusive for daily/weekly/monthly intervals.
    Adding 1 day ensures the requested end-date candle appears in the result.
    """
    if interval in _DAILY_PLUS_INTERVALS:
        return end + timedelta(days=1)
    return end


def _history_bounds(start: datetime, end: datetime, interval: str) -> tuple[datetime | str, datetime | str]:
    """
    Return yfinance-compatible start/end values without dropping needed precision.

    Daily/weekly/monthly intervals use YYYY-MM-DD strings.
    Intraday intervals keep UTC-aware datetimes so hour/minute precision is preserved.
    """
    if interval in _DAILY_PLUS_INTERVALS:
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    return start, end

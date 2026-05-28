"""
Polygon.io market data provider adapter.

Fetches historical OHLCV aggregates via the Polygon REST API v2 and converts
them to the canonical NormalizedOHLCV schema.

Isolation contract:
    - All Polygon REST API calls are confined to this module
    - No Polygon-specific response structures leave this module
    - NormalizedOHLCV is the only output type
    - Strategies must never import from this module
    - The API key is resolved at construction time and never logged or
      included in exception messages

Credential requirement:
    POLYGON_API_KEY environment variable must be set.
    The builder (provider_factory._build_polygon_adapter) resolves this via
    EnvironmentCredentialResolver and passes the value as the `api_key` kwarg.

Supported timeframes (all 15 canonical QuantLab timeframes):
    1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M

Unsupported timeframes raise ValueError at construction time.

Pagination:
    Polygon may return up to _PAGE_LIMIT records per response and include a
    next_url for subsequent pages.  This adapter follows up to _MAX_PAGES
    pages automatically.

Error sanitization:
    HTTP 401  → PolygonAdapterError  (no key or key name in message)
    HTTP 429  → PolygonRateLimitError
    HTTP 404  → [] (empty result — treat as unknown symbol per adapter contract)
    HTTP 5xx  → PolygonAdapterError
    Bad JSON  → PolygonAdapterError
    Network   → PolygonAdapterError
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from backend.data.schemas import NormalizedOHLCV
from backend.data_providers.base import ProviderCapabilities, ProviderFetchError
from backend.data_providers.range_provider import RangeProviderAdapter

logger = logging.getLogger(__name__)

_POLYGON_BASE_URL = "https://api.polygon.io"
_AGGS_PATH = "/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_ts}/{to_ts}"

# Pagination limits
_MAX_PAGES = 50        # 50 pages × 50 000 records = 2.5 M records maximum
_PAGE_LIMIT = 50_000   # maximum records Polygon returns per page

# Polygon timespans that accept YYYY-MM-DD date strings (not milliseconds)
_DATE_STRING_TIMESPANS: frozenset[str] = frozenset({"day", "week", "month"})


# ---------------------------------------------------------------------------
# Timeframe mapping
# ---------------------------------------------------------------------------

# All 15 canonical QuantLab timeframes mapped to (multiplier, timespan)
SUPPORTED_TIMEFRAMES: dict[str, tuple[int, str]] = {
    "1m":  (1,   "minute"),
    "3m":  (3,   "minute"),
    "5m":  (5,   "minute"),
    "15m": (15,  "minute"),
    "30m": (30,  "minute"),
    "1h":  (1,   "hour"),
    "2h":  (2,   "hour"),
    "4h":  (4,   "hour"),
    "6h":  (6,   "hour"),
    "8h":  (8,   "hour"),
    "12h": (12,  "hour"),
    "1d":  (1,   "day"),
    "3d":  (3,   "day"),
    "1w":  (1,   "week"),
    "1M":  (1,   "month"),
}


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------

class PolygonAdapterError(ProviderFetchError):
    """
    Raised on Polygon API transport, authentication, or parsing failures.

    INVARIANT: messages must NEVER contain raw API key values or names.
    """


class PolygonRateLimitError(PolygonAdapterError):
    """Raised when Polygon returns HTTP 429 (rate limit exceeded)."""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class PolygonProviderAdapter(RangeProviderAdapter):
    """
    RangeProviderAdapter backed by the Polygon.io REST API (v2 aggregates).

    The API key is accepted as a constructor argument — the factory builder
    is responsible for resolving it via EnvironmentCredentialResolver before
    constructing this object.  The key is held privately and never logged,
    propagated, or included in exception messages.

    Correct usage via factory:
        factory.build("polygon", symbol="AAPL", timeframe="1d", ...)
        → _build_polygon_adapter resolves POLYGON_API_KEY
        → PolygonProviderAdapter(api_key=<secret>, ...)
        → OHLCVService.get_ohlcv()

    Not responsible for:
        - DataNormalizer (called by OHLCVService after fetch)
        - Storage writes
        - Coverage tracking
        - Streaming / websocket / live data
    """

    def __init__(
        self,
        *,
        symbol: str,
        asset_class: str,
        venue: str,
        timeframe: str,
        adjustment_mode: str = "adjusted",
        api_key: str,
    ) -> None:
        if not symbol.strip():
            raise ValueError("symbol must not be empty")
        if not asset_class.strip():
            raise ValueError("asset_class must not be empty")
        if not venue.strip():
            raise ValueError("venue must not be empty")
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"timeframe '{timeframe}' is not supported by PolygonProviderAdapter. "
                f"Supported: {sorted(SUPPORTED_TIMEFRAMES)}"
            )
        if not api_key:
            raise ValueError("api_key must not be empty")

        self._symbol = symbol.strip()
        self._asset_class = asset_class.strip()
        self._venue = venue.strip()
        self._timeframe = timeframe
        self._multiplier, self._timespan = SUPPORTED_TIMEFRAMES[timeframe]
        self._adjustment_mode = adjustment_mode
        self._adjusted = adjustment_mode != "raw"
        self._api_key = api_key   # private — never log, never propagate

    @property
    def provider_name(self) -> str:
        return "polygon"

    def supported_timeframes(self) -> tuple[str, ...]:
        return tuple(sorted(SUPPORTED_TIMEFRAMES.keys()))

    def supported_asset_classes(self) -> tuple[str, ...]:
        return ("crypto", "equity", "etf", "fx", "index")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id="polygon",
            display_name="Polygon.io",
            supported_timeframes=self.supported_timeframes(),
            supported_asset_classes=self.supported_asset_classes(),
        )

    def load(self, **_kwargs: object) -> list[NormalizedOHLCV]:
        """Not implemented — use fetch(start, end) for range-based retrieval."""
        raise NotImplementedError(
            "PolygonProviderAdapter.load() is not supported. "
            "Use fetch(start, end) for range-based retrieval."
        )

    def fetch(
        self,
        start: datetime,
        end: datetime,
        **_kwargs: object,
    ) -> list[NormalizedOHLCV]:
        """
        Fetch historical OHLCV aggregates from Polygon for [start, end] inclusive.

        Args:
            start: UTC-aware datetime (lower bound, inclusive).
            end:   UTC-aware datetime (upper bound, inclusive).

        Returns:
            list[NormalizedOHLCV] — may be empty for unknown symbols or empty windows.

        Raises:
            ValueError:            if start or end are timezone-naive.
            PolygonAdapterError:   on authentication, server, or parse errors.
            PolygonRateLimitError: on HTTP 429 (rate limit exceeded).
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be UTC-aware datetimes")

        from_ts, to_ts = _format_date_params(start, end, self._timespan)
        first_url = self._build_url(from_ts, to_ts)

        logger.debug(
            "PolygonProviderAdapter: fetching %s %s×%s [%s → %s]",
            self._symbol,
            self._multiplier,
            self._timespan,
            start.isoformat(),
            end.isoformat(),
        )

        raw_results = self._fetch_all_pages(first_url)
        records = self._convert(raw_results)

        # Enforce inclusive window bounds after conversion
        filtered = [r for r in records if start <= r.timestamp <= end]

        logger.debug(
            "PolygonProviderAdapter: %d records for '%s' (after [start,end] filter)",
            len(filtered),
            self._symbol,
        )
        return filtered

    # ------------------------------------------------------------------
    # Internal helpers — HTTP
    # ------------------------------------------------------------------

    def _build_url(self, from_ts: str, to_ts: str) -> str:
        path = _AGGS_PATH.format(
            ticker=urllib.parse.quote(self._symbol, safe=""),
            multiplier=self._multiplier,
            timespan=self._timespan,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        params = {
            "adjusted": str(self._adjusted).lower(),
            "sort": "asc",
            "limit": str(_PAGE_LIMIT),
        }
        return _POLYGON_BASE_URL + path + "?" + urllib.parse.urlencode(params)

    def _fetch_all_pages(self, first_url: str) -> list[dict[str, Any]]:
        """Follow Polygon pagination and accumulate all result dicts."""
        all_results: list[dict[str, Any]] = []
        url: str | None = first_url
        page = 0
        while url and page < _MAX_PAGES:
            data = self._fetch_page(url)
            results = data.get("results")
            if results:
                all_results.extend(results)
            url = data.get("next_url")
            if url:
                logger.debug(
                    "PolygonProviderAdapter: following next_url (page %d)", page + 1
                )
            page += 1
        return all_results

    def _fetch_page(self, url: str) -> dict[str, Any]:
        """
        Perform a single authenticated GET to the Polygon API.

        Returns the parsed JSON body as a dict.

        Raises:
            PolygonRateLimitError: HTTP 429
            PolygonAdapterError:   HTTP 401, other 4xx (except 404), 5xx, bad JSON,
                                   network failures
        Returns {} on HTTP 404 (treat as no data — unknown symbol).
        """
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return self._handle_http_error(exc)
        except urllib.error.URLError as exc:
            raise PolygonAdapterError(
                f"Polygon API connection failed for symbol '{self._symbol}': "
                f"network error ({type(exc.reason).__name__})"
            ) from exc
        except Exception as exc:
            raise PolygonAdapterError(
                f"Polygon API request failed for symbol '{self._symbol}': "
                f"{type(exc).__name__}"
            ) from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise PolygonAdapterError(
                f"Polygon API returned non-JSON response for symbol '{self._symbol}'."
            ) from exc

    def _handle_http_error(self, exc: urllib.error.HTTPError) -> dict[str, Any]:
        if exc.code == 404:
            logger.debug(
                "PolygonProviderAdapter: HTTP 404 for '%s' — treating as empty result",
                self._symbol,
            )
            return {}
        if exc.code == 429:
            raise PolygonRateLimitError(
                "Polygon API rate limit exceeded. Reduce request frequency and retry."
            ) from exc
        if exc.code == 401:
            raise PolygonAdapterError(
                "Polygon API authentication failed. "
                "Verify that the API key for provider 'polygon' is correctly configured."
            ) from exc
        raise PolygonAdapterError(
            f"Polygon API returned HTTP {exc.code} for symbol '{self._symbol}'."
        ) from exc

    # ------------------------------------------------------------------
    # Internal helpers — conversion
    # ------------------------------------------------------------------

    def _convert(self, raw_results: list[dict[str, Any]]) -> list[NormalizedOHLCV]:
        """Convert Polygon aggregate result dicts to list[NormalizedOHLCV]."""
        records: list[NormalizedOHLCV] = []
        for item in raw_results:
            try:
                records.append(self._parse_result(item))
            except Exception as exc:
                logger.warning(
                    "PolygonProviderAdapter: skipping malformed result for '%s' — %s: %s",
                    self._symbol,
                    type(exc).__name__,
                    exc,
                )
        return records

    def _parse_result(self, item: dict[str, Any]) -> NormalizedOHLCV:
        """Parse a single Polygon aggregate dict to NormalizedOHLCV."""
        # 't' is Unix millisecond timestamp
        timestamp = datetime.fromtimestamp(item["t"] / 1000.0, tz=timezone.utc)

        return NormalizedOHLCV(
            symbol=self._symbol,
            asset_class=self._asset_class,
            venue=self._venue,
            timeframe=self._timeframe,
            source="polygon",
            timestamp=timestamp,
            open=float(item["o"]),
            high=float(item["h"]),
            low=float(item["l"]),
            close=float(item["c"]),
            volume=float(item.get("v", 0.0)),
            vwap=float(item["vw"]) if "vw" in item else None,
            trade_count=int(item["n"]) if "n" in item else None,
        )


# ---------------------------------------------------------------------------
# Date parameter helpers
# ---------------------------------------------------------------------------

def _format_date_params(
    start: datetime,
    end: datetime,
    timespan: str,
) -> tuple[str, str]:
    """
    Format start/end datetimes as Polygon API 'from'/'to' parameter strings.

    Daily, weekly, and monthly timespans use "YYYY-MM-DD" date strings per
    Polygon convention.  Intraday timespans use Unix millisecond timestamps
    to preserve hour/minute precision.
    """
    if timespan in _DATE_STRING_TIMESPANS:
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    from_ms = int(start.timestamp() * 1000)
    to_ms = int(end.timestamp() * 1000)
    return str(from_ms), str(to_ms)

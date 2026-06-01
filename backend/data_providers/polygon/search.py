"""
Polygon.io asset search.

Uses the Polygon /v3/reference/tickers endpoint to resolve user queries
(ticker symbol or company name) to structured asset metadata.

Architecture boundary:
    This module must NOT be imported from API routes or services directly.
    Route → asset_search_service → ProviderAdapterFactory.search() → this module.

Credential:
    Requires a valid Polygon API key passed as ``api_key``.
    - Primary path: pre-resolved from the vault by the service layer and
      forwarded via factory.search(api_key=...).
    - ENV fallback: when api_key is None and
      settings.polygon_allow_env_fallback is True, reads POLYGON_API_KEY
      from the environment (same gate as the OHLCV adapter).
    - No key + fallback disabled: raises PolygonSearchError (surfaces as
      "Search failed" in the frontend — the user needs to supply a key).

Error handling:
    HTTP 401  → PolygonSearchError ("authentication failed" — surfaces to user)
    HTTP 429  → returns []          (rate limit — retry later, no crash)
    HTTP 404  → returns []          (no results for this query)
    HTTP 5xx  → PolygonSearchError  (server-side issue)
    Network   → PolygonSearchError  (surfaces to user)
    No key    → PolygonSearchError  (surfaces to user)
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_REFERENCE_TICKERS_URL = "https://api.polygon.io/v3/reference/tickers"

# Maps Polygon type codes to QuantLab canonical asset_class strings.
# https://polygon.io/docs/stocks/get_v3_reference_tickers
_TYPE_MAP: dict[str, str] = {
    "CS":     "equity",    # Common Stock
    "PFD":    "equity",    # Preferred Stock
    "ADRC":   "equity",    # American Depositary Receipt (Common)
    "ADRP":   "equity",    # American Depositary Receipt (Preferred)
    "ADRW":   "equity",    # American Depositary Receipt (Warrant)
    "ADRT":   "equity",    # American Depositary Receipt (Term)
    "UNIT":   "equity",    # Unit
    "RIGHT":  "equity",    # Rights Offering
    "WARRANT":"equity",    # Warrant
    "BOND":   "equity",    # Corporate Bond
    "SP":     "equity",    # Structured Product
    "ETF":    "etf",       # Exchange-Traded Fund
    "ETN":    "etf",       # Exchange-Traded Note
    "ETV":    "etf",       # Exchange-Traded Vehicle
    "FUND":   "fund",      # Closed-End Fund
    "MF":     "fund",      # Mutual Fund
    "OEF":    "fund",      # Open-End Fund
    "ETS":    "fund",      # Single-Security ETF
    "INDEX":  "index",     # Index
    "CRYPTOCURRENCIES": "crypto",
    "FX":     "fx",        # Forex pair
    "FOREX":  "fx",
}

# Polygon MIC codes → display names
_EXCHANGE_MAP: dict[str, str] = {
    "XNAS": "NASDAQ",
    "XNYS": "NYSE",
    "BATS": "CBOE BZX",
    "ARCX": "NYSE ARCA",
    "XASE": "NYSE American",
    "IEXG": "IEX",
    "XPHL": "NASDAQ PHLX",
    "XBOS": "NASDAQ BX",
    "EDGA": "CBOE EDGA",
    "EDGX": "CBOE EDGX",
    "XCBO": "CBOE Options",
}

# Human-readable labels for Polygon type codes
_TYPE_LABEL_MAP: dict[str, str] = {
    "CS":    "Equity",
    "PFD":   "Preferred Stock",
    "ADRC":  "ADR",
    "UNIT":  "Unit",
    "RIGHT": "Rights",
    "WARRANT": "Warrant",
    "BOND":  "Bond",
    "SP":    "Structured Product",
    "ETF":   "ETF",
    "ETN":   "ETN",
    "ETV":   "ETV",
    "FUND":  "Fund",
    "MF":    "Mutual Fund",
    "INDEX": "Index",
    "CRYPTOCURRENCIES": "Cryptocurrency",
    "FX":    "Forex",
    "FOREX": "Forex",
}


class PolygonSearchError(Exception):
    """
    Raised on Polygon search transport, authentication, or parsing failures.

    INVARIANT: messages must NEVER contain raw API key values or names.
    """


def search_polygon(
    *,
    query: str,
    limit: int = 10,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search Polygon.io for assets matching *query*.

    Supports ticker prefix matching and company name search via the
    Polygon /v3/reference/tickers endpoint.

    Args:
        query:   User-supplied search string (ticker or company name).
        limit:   Maximum number of results (applied after normalization).
        api_key: Pre-resolved Polygon API key.  When None, the ENV fallback
                 path is tried (requires polygon_allow_env_fallback=True).

    Returns:
        List of normalized asset dicts with keys:
        symbol, name, exchange, asset_class, currency, type_label.

    Raises:
        PolygonSearchError: on authentication failure, network error, or
                            missing API key.  HTTP 404 and 429 return []
                            without raising.
    """
    resolved_key = _resolve_key(api_key)

    params = urllib.parse.urlencode({
        "search":  query,
        "active":  "true",
        "limit":   min(limit, 50),     # Polygon max per page for reference
        "apiKey":  resolved_key,
    })
    url = f"{_REFERENCE_TICKERS_URL}?{params}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
            raw = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return _handle_http_error(exc, query)
    except OSError as exc:
        raise PolygonSearchError(
            "Polygon asset search network error. Check your connection and retry."
        ) from exc
    except Exception as exc:
        raise PolygonSearchError(
            f"Polygon asset search failed: {type(exc).__name__}"
        ) from exc

    raw_results: list[dict[str, Any]] = raw.get("results") or []
    if not raw_results:
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_results:
        try:
            norm = _normalize(item)
            if norm:
                normalized.append(norm)
                if len(normalized) >= limit:
                    break
        except Exception as exc:
            logger.debug("PolygonSearch: skipping malformed result: %s", exc)

    return normalized


def _resolve_key(api_key: str | None) -> str:
    """Resolve the Polygon API key from kwarg or ENV fallback."""
    if api_key:
        return api_key

    from backend.core.config import settings
    if settings.polygon_allow_env_fallback:
        import os
        env_key = os.environ.get("POLYGON_API_KEY", "")
        if env_key:
            return env_key

    raise PolygonSearchError(
        "Polygon asset search requires an API key. "
        "Add a Polygon credential in the Credentials tab."
    )


def _handle_http_error(
    exc: urllib.error.HTTPError, query: str
) -> list[dict[str, Any]]:
    if exc.code == 401:
        raise PolygonSearchError(
            "Polygon API authentication failed. "
            "Verify that your Polygon credential is active and correct."
        ) from exc
    if exc.code in (404, 429):
        logger.debug(
            "PolygonSearch: HTTP %d for query %r — returning empty", exc.code, query
        )
        return []
    if exc.code >= 500:
        raise PolygonSearchError(
            f"Polygon API server error (HTTP {exc.code}). Retry later."
        ) from exc
    logger.debug(
        "PolygonSearch: HTTP %d for query %r — returning empty", exc.code, query
    )
    return []


def _normalize(item: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one Polygon ticker reference result to a QuantLab asset dict."""
    symbol = (item.get("ticker") or "").strip()
    if not symbol:
        return None

    raw_type = (item.get("type") or "").upper()
    asset_class = _TYPE_MAP.get(raw_type, "equity")
    type_label = _TYPE_LABEL_MAP.get(raw_type, raw_type.title() or "Equity")

    name = (item.get("name") or symbol).strip()

    raw_exchange = (item.get("primary_exchange") or "").strip()
    exchange = _EXCHANGE_MAP.get(raw_exchange, raw_exchange) or "Unknown"

    raw_currency = (item.get("currency_name") or "usd").strip()
    currency = raw_currency.upper() or "USD"

    return {
        "symbol":      symbol,
        "name":        name,
        "exchange":    exchange,
        "asset_class": asset_class,
        "currency":    currency,
        "type_label":  type_label,
    }

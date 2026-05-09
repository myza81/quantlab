"""
Basic instrument metadata resolution via Yahoo Finance.

Provides a lightweight model and resolver for provider-side instrument
metadata — exchange, currency, timezone, and asset class inference.

This is NOT a full instrument master database. It provides enough metadata
to populate DatasetIdentity fields when constructing provider-specific
dataset identities for Yahoo Finance instruments.

Provider-specific metadata must not leak into:
- strategies
- storage contracts
- runtime runner
- frontend contracts

Usage:
    meta = resolve_yahoo_metadata("AAPL")
    # meta.exchange → "NMS"
    # meta.currency → "USD"
    # meta.timezone → "America/New_York"
"""
import logging
from typing import Any

import yfinance as yf  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# Yahoo Finance quoteType values → QuantLab asset_class
_QUOTE_TYPE_TO_ASSET_CLASS: dict[str, str] = {
    "EQUITY": "equity",
    "ETF": "etf",
    "MUTUALFUND": "fund",
    "CRYPTOCURRENCY": "crypto",
    "CURRENCY": "fx",
    "FUTURE": "future",
    "INDEX": "index",
    "OPTION": "option",
}


class YahooMetadataError(Exception):
    """Raised when metadata resolution fails for a Yahoo Finance symbol."""


class YahooInstrumentMetadata(BaseModel):
    """
    Provider-side instrument metadata retrieved from Yahoo Finance.

    All fields are optional — yfinance may not return all fields for all
    symbols (e.g. crypto tickers have no exchange timezone).

    This model is provider-specific and must not be exposed to strategies
    or storage contracts. Use it only to populate DatasetIdentity or
    for diagnostic/informational purposes.
    """

    model_config = ConfigDict(frozen=True)

    provider_symbol: str
    exchange: str | None = None
    currency: str | None = None
    timezone: str | None = None
    asset_class: str | None = None
    short_name: str | None = None


def resolve_yahoo_metadata(provider_symbol: str) -> YahooInstrumentMetadata:
    """
    Resolve basic instrument metadata for a Yahoo Finance symbol.

    Uses yfinance fast_info (lightweight endpoint) with a fallback to the
    full .info dict when fast_info does not provide all fields.

    Args:
        provider_symbol: Yahoo Finance ticker symbol (e.g. "AAPL", "1155.KL").

    Returns:
        YahooInstrumentMetadata with available fields populated.

    Raises:
        YahooMetadataError: if yfinance raises an unexpected error.
    """
    try:
        ticker = yf.Ticker(provider_symbol)
        fast_info: Any = ticker.fast_info
    except Exception as exc:
        raise YahooMetadataError(
            f"Failed to fetch metadata for '{provider_symbol}': {exc}"
        ) from exc

    exchange: str | None = _safe_get(fast_info, "exchange")
    currency: str | None = _safe_get(fast_info, "currency")
    timezone: str | None = _safe_get(fast_info, "timezone")
    asset_class: str | None = None
    short_name: str | None = None

    # Attempt full .info for richer fields (best-effort, may be slow or fail)
    try:
        info = ticker.info or {}
        if not exchange:
            exchange = info.get("exchange")
        if not currency:
            currency = info.get("currency")
        if not timezone:
            timezone = info.get("exchangeTimezoneName")
        quote_type: str | None = info.get("quoteType")
        if quote_type:
            asset_class = _QUOTE_TYPE_TO_ASSET_CLASS.get(quote_type.upper())
        short_name = info.get("shortName")
    except Exception:
        logger.debug(
            "resolve_yahoo_metadata: full .info fetch failed for '%s' — using fast_info only",
            provider_symbol,
        )

    return YahooInstrumentMetadata(
        provider_symbol=provider_symbol,
        exchange=exchange or None,
        currency=currency or None,
        timezone=timezone or None,
        asset_class=asset_class,
        short_name=short_name,
    )


def _safe_get(obj: Any, attr: str) -> str | None:
    """Safely read an attribute from fast_info without raising."""
    try:
        val = getattr(obj, attr, None)
        return str(val) if val is not None else None
    except Exception:
        return None

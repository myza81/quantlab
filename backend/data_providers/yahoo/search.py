"""
Yahoo Finance asset search.

Uses yfinance.Search to resolve user queries (ticker, company name, fuzzy)
to structured asset metadata. Results are normalized to QuantLab's canonical
asset schema — no yfinance types leave this module.

Architecture boundary:
    This module must NOT be imported from API routes or services directly.
    Route → asset_search_service → ProviderAdapterFactory.search() → this module.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maps Yahoo Finance quoteType to QuantLab canonical asset_class strings.
_QUOTE_TYPE_MAP: dict[str, str] = {
    "EQUITY":         "equity",
    "ETF":            "etf",
    "FUTURE":         "future",
    "INDEX":          "index",
    "CRYPTOCURRENCY": "crypto",
    "CURRENCY":       "fx",
    "MUTUALFUND":     "fund",
    "OPTION":         "option",
}


def _normalize_quote(quote: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a raw Yahoo Finance quote dict to a QuantLab asset dict."""
    symbol = (quote.get("symbol") or "").strip()
    if not symbol:
        return None

    quote_type = (quote.get("quoteType") or "").upper()
    asset_class = _QUOTE_TYPE_MAP.get(quote_type, "equity")

    name = (
        quote.get("longname")
        or quote.get("shortname")
        or symbol
    ).strip()

    exchange = (
        quote.get("exchDisp")
        or quote.get("exchange")
        or "Unknown"
    ).strip()

    currency = (quote.get("currency") or "USD").strip() or "USD"
    type_label = (quote.get("typeDisp") or quote_type.title() or "Equity").strip()

    return {
        "symbol":      symbol,
        "name":        name,
        "exchange":    exchange,
        "asset_class": asset_class,
        "currency":    currency,
        "type_label":  type_label,
    }


def search_yahoo(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Search Yahoo Finance for assets matching *query*.

    Supports:
    - Exact ticker matching ("KO", "AAPL")
    - Ticker prefix matching ("APP" → Apple, Appian, …)
    - Company name prefix and fuzzy matching ("Coca-Cola", "Tenaga")
    - Multi-market results (KLSE, NYSE, NASDAQ, Crypto, …)

    Args:
        query: User-supplied search string (ticker or company name).
        limit: Maximum number of results to return (applied after normalization).

    Returns:
        List of normalized asset dicts with keys:
        symbol, name, exchange, asset_class, currency, type_label.
        Returns [] on any error — callers must handle empty gracefully.
    """
    try:
        import yfinance as yf  # type: ignore[import-untyped]
        raw_quotes: list[dict[str, Any]] = yf.Search(
            query,
            max_results=limit,
            enable_fuzzy_query=True,
        ).quotes
    except Exception as exc:
        logger.warning("Yahoo asset search failed for %r: %s", query, exc)
        return []

    results: list[dict[str, Any]] = []
    for quote in raw_quotes:
        try:
            norm = _normalize_quote(quote)
            if norm:
                results.append(norm)
                if len(results) >= limit:
                    break
        except Exception as exc:
            logger.debug("Skipping malformed Yahoo quote: %s", exc)

    return results

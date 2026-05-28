# Polygon.io Provider

## Overview

`PolygonProviderAdapter` is the Phase 3G external API-key-based market data provider. It fetches historical OHLCV aggregates from the Polygon.io REST API v2 and delivers them as canonical `NormalizedOHLCV` records — indistinguishable from Yahoo, CSV, or Parquet data downstream.

---

## Architecture Position

```
API Route
→ OHLCVService
→ ProviderAdapterFactory.build("polygon", ...)
→ PolygonProviderAdapter
→ Polygon REST API (v2/aggs)
→ NormalizedOHLCV[]
→ DataNormalizer
→ cache/storage layer
→ API response
```

Polygon is **just another provider adapter**. No service, route, or strategy layer knows or cares that data came from Polygon.

---

## Credential Setup

Set the `POLYGON_API_KEY` environment variable before starting the server:

```bash
export POLYGON_API_KEY=your_polygon_api_key_here
```

The key is resolved at build time via `EnvironmentCredentialResolver` in `_build_polygon_adapter()` (inside `provider_factory.py`). It is:
- never logged
- never included in exception messages
- never propagated to API responses or schemas
- never stored in `DatasetFetchIdentity` or `DatasetCatalog`

A missing or empty key raises `ProviderBuildError` at request time (HTTP 400/503 depending on route error handling). The error message names the provider (`"polygon"`) but not the key name or value.

---

## Supported Timeframes

All 15 canonical QuantLab timeframes are supported:

| QuantLab | Polygon multiplier | Polygon timespan |
|----------|-------------------|-----------------|
| `1m`     | 1                 | minute          |
| `3m`     | 3                 | minute          |
| `5m`     | 5                 | minute          |
| `15m`    | 15                | minute          |
| `30m`    | 30                | minute          |
| `1h`     | 1                 | hour            |
| `2h`     | 2                 | hour            |
| `4h`     | 4                 | hour            |
| `6h`     | 6                 | hour            |
| `8h`     | 8                 | hour            |
| `12h`    | 12                | hour            |
| `1d`     | 1                 | day             |
| `3d`     | 3                 | day             |
| `1w`     | 1                 | week            |
| `1M`     | 1                 | month           |

Unsupported timeframes raise `ValueError` at construction time (before any API call).

---

## Supported Asset Classes

`crypto`, `equity`, `etf`, `fx`, `index`

---

## Pagination

Polygon caps results at 50 000 records per response. For large date ranges, the adapter follows `next_url` automatically for up to 50 pages (2.5M records maximum). No caller changes needed.

---

## Date Parameter Format

- **Daily, weekly, monthly:** `YYYY-MM-DD` strings (Polygon convention)
- **Intraday (hour/minute):** Unix millisecond timestamps for hour/minute precision

---

## Error Handling

| HTTP status | Behavior |
|-------------|----------|
| 200         | Parse and return `NormalizedOHLCV[]` |
| 404         | Return `[]` — treat as unknown symbol |
| 401         | Raise `PolygonAdapterError` (no key in message) |
| 429         | Raise `PolygonRateLimitError` |
| 4xx other   | Raise `PolygonAdapterError` |
| 5xx         | Raise `PolygonAdapterError` |
| Bad JSON    | Raise `PolygonAdapterError` |
| Network     | Raise `PolygonAdapterError` |

Malformed individual candles within a valid response are silently skipped (logged at WARNING). The remaining valid candles are returned.

All `PolygonAdapterError` and `PolygonRateLimitError` subclass `ProviderFetchError`, allowing service layers to catch the generic type without importing polygon-specific exceptions.

---

## NormalizedOHLCV Fields

| Polygon field | NormalizedOHLCV field | Notes |
|--------------|----------------------|-------|
| `t` (ms)     | `timestamp`          | UTC datetime from millisecond epoch |
| `o`          | `open`               | float |
| `h`          | `high`               | float |
| `l`          | `low`                | float |
| `c`          | `close`              | float |
| `v`          | `volume`             | float (0.0 if absent) |
| `vw`         | `vwap`               | Optional float |
| `n`          | `trade_count`        | Optional int |
| —            | `source`             | `"polygon"` (hardcoded) |

---

## Cache Policy Compatibility

All four `DatasetCachePolicy` values work without modification:

| Policy            | Behavior |
|-------------------|----------|
| `FETCH_AND_STORE` | Fetch from Polygon, merge into Parquet, update coverage + cache metadata |
| `READ_ONLY`       | Read from stored Parquet; Polygon is never called |
| `FORCE_REFRESH`   | Fetch full range from Polygon, overwrite storage |
| `BYPASS_CACHE`    | Fetch from Polygon, return directly; no storage read or write |

---

## Architecture Boundaries

The adapter module (`backend/data_providers/polygon/adapter.py`) enforces:

- No imports of `yahoo`, `csv_provider`, `parquet_provider`
- No imports of `backend.api.routes`
- No imports of `backend.strategy_runtime`
- No imports of `backend.core.credentials` (credential resolution is the factory builder's responsibility)

Credential resolution lives in `provider_factory._build_polygon_adapter()` — the one place that knows both the secret and the adapter interface.

---

## Usage via Factory

```python
from backend.data_providers.provider_factory import create_default_factory_registry

factory = create_default_factory_registry()

# POLYGON_API_KEY must be set in environment
adapter = factory.build(
    "polygon",
    symbol="AAPL",
    asset_class="equity",
    venue="NASDAQ",
    timeframe="1d",
    adjustment_mode="adjusted",
)
```

---

## Known Limitations

- REST only — no WebSocket, tick streaming, or live subscriptions
- `adjustment_mode="raw"` passes `adjusted=false` to Polygon; split adjustments are Polygon's responsibility
- No symbol validation at construction time — HTTP 404 at fetch time means the symbol is unknown (returns `[]`)
- Rate limits are not auto-retried — callers that need retry logic should wrap in an application-layer retry policy
- No Polygon-specific instrument search or metadata endpoints

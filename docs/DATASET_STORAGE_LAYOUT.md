# DATASET_STORAGE_LAYOUT.md

## Purpose

Defines the canonical on-disk storage layout for normalized OHLCV datasets in QuantLab.

All data files written by `OHLCVService` follow this layout.  Future providers, research datasets, and dataset archives must use the same convention so that tooling, cache lookups, and audit trails remain consistent.

---

## Directory Tree

```
{storage_base_path}/
  {provider}/
    {asset_class}/
      {exchange}/
        {symbol}/
          {timeframe}/
            {adjustment_mode}/
              data.parquet          ← normalized OHLCV records (Parquet)
              coverage.json         ← boundary coverage metadata
              cache_metadata.json   ← rich cache metadata + fingerprint lineage
```

### Field values

| Segment           | Example values                                  |
|-------------------|-------------------------------------------------|
| `provider`        | `yahoo`, `polygon`, `ibkr`, `csv`, `parquet`   |
| `asset_class`     | `equity`, `crypto`, `etf`, `fx`, `futures`     |
| `exchange`        | `NASDAQ`, `NYSE`, `BINANCE`, `CME`             |
| `symbol`          | `AAPL`, `BTCUSDT`, `ES`                        |
| `timeframe`       | `1m`, `5m`, `15m`, `30m`, `1h`, `1d`, `1w`, `1M` |
| `adjustment_mode` | `raw`, `adjusted`, `split_adjusted`            |

### Configuration

`storage_base_path` is set in `backend/core/config.py` as `settings.storage_base_path` (default: `datasets/normalized`).

---

## File Contracts

### `data.parquet`

Canonical Parquet file containing `NormalizedOHLCV` records.

- Schema: defined in `backend/storage/parquet_store.py` (`SCHEMA`)
- Records are sorted ascending by `timestamp` on every write
- Deduplication: incoming records overwrite existing records at the same timestamp
- Append behavior: `ohlcv_store.write(merge=True)` (default) preserves prior records
- Overwrite behavior: `ohlcv_store.write(merge=False)` — used by `FORCE_REFRESH` policy

### `coverage.json`

Boundary-level coverage metadata.  Tracks the earliest and latest stored timestamp for fast coverage queries without reading the full Parquet file.

Managed by: `backend/storage/coverage_registry.py` (`CoverageRegistry`)

### `cache_metadata.json`

Rich dataset metadata for cache state classification, lineage tracking, and reproducibility.

Contains:
- `dataset_id` — canonical composite key (from `DatasetIdentity.dataset_id`)
- `storage_path` — path to `data.parquet`
- `record_count` — number of stored records
- `earliest_ts` / `latest_ts` — boundary timestamps (ISO 8601 UTC)
- `created_at` — UTC timestamp of first write
- `last_refreshed_at` — UTC timestamp of most recent provider fetch
- `last_fetch_fingerprint` — SHA-256 fingerprint of most recent fetch request
- `fetch_fingerprints` — rolling list of the last 10 fetch fingerprints (newest first)

Managed by: `backend/storage/dataset_cache.py` (`DatasetCacheRegistry`)

---

## Dataset Identity Key

The `dataset_id` (from `DatasetIdentity.dataset_id`) provides a stable composite key:

```
{asset_class}__{exchange}__{symbol}__{provider}__{timeframe}__{adjustment_mode}
```

Example: `equity__NASDAQ__AAPL__yahoo__1d__adjusted`

The storage path encodes the same identity in directory form for filesystem navigation.

---

## Fetch Fingerprint Lineage

Every OHLCV fetch request produces a deterministic `DatasetFetchIdentity.fingerprint` (SHA-256 of normalized request parameters).  This fingerprint is stored in `cache_metadata.json` for reproducibility auditing:

- Identify which fetch parameters produced which stored records
- Detect if a dataset was refreshed with different parameters
- Enable reproducible backtest validation

See `backend/data/models/fetch_identity.py` for the fingerprint contract.

---

## Cache Policy Behavior

`OHLCVService.get_ohlcv()` accepts a `DatasetCachePolicy` that governs how the above files are used:

| Policy            | Reads Parquet | Calls Provider | Writes Parquet | Updates Metadata |
|-------------------|:---:|:---:|:---:|:---:|
| `FETCH_AND_STORE` | ✓ (gaps only) | Only for gaps  | ✓ (merge)     | ✓                |
| `READ_ONLY`       | ✓             | ✗              | ✗              | ✗                |
| `FORCE_REFRESH`   | ✓ (return)    | ✓ (full range) | ✓ (overwrite) | ✓                |
| `BYPASS_CACHE`    | ✗             | ✓ (full range) | ✗              | ✗                |

---

## Extensibility

Adding a new provider:
1. Register it in `create_default_factory_registry()` — `backend/data_providers/provider_factory.py`
2. Files are stored automatically under `{storage_base_path}/{new_provider}/...`
3. No storage or cache code changes needed

Adding a new asset class, exchange, or timeframe:
- No code changes needed; the path is constructed dynamically from `DatasetIdentity` fields

---

## Architecture Boundaries

- Storage modules (`ohlcv_store`, `coverage_registry`, `dataset_cache`) MUST NOT import from provider adapter modules
- Providers MUST NOT write directly to storage — all writes go through `OHLCVService`
- Strategy runtime and backtest engine MUST NOT read from `data.parquet` directly — use `OHLCVService.get_ohlcv()`

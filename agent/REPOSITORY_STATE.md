# REPOSITORY_STATE.md

## Current Branch
main

## Current Phase
PHASE 2J — First Real Historical Provider + Provider Registry Foundation (complete)

---

## Backend Status

OPERATIONAL

- FastAPI app + `GET /health` — validated ✓
- `backend/data/` — normalization layer complete and contract-hardened ✓
- `backend/data_providers/` — CSV adapter + RangeProviderAdapter ABC complete ✓
- `backend/storage/` — Parquet write/read + DuckDB query helper complete and UTC/consistency-hardened ✓
- `backend/strategy_registry/` — strategy registry foundation complete ✓
  - `StrategyLifecycleStage`, `RuntimeMode`, `StrategyManifest` models
  - `load_manifest()`, `ManifestLoadError`
  - `validate_strategy_files()`, `StrategyValidationError`
  - `StrategyRegistry`, `StrategyRegistryEntry`, `StrategyRegistryError`
- `backend/strategy_runtime/` — strategy runtime interface + contract hardening complete ✓
  - `SignalType`, `StrategySignal` (frozen Pydantic v2, UTC-enforced timestamp)
  - `REQUIRED_CALLABLES`, `CALLABLE_MODULE_MAP`, `RuntimeInterfaceError`, `validate_strategy_interface()`
  - `StrategyLoadError`, `StrategyRuntimeReference`, `load_strategy_runtime()`
  - `CALLABLE_EXPECTED_PARAM_COUNTS`, `CALLABLE_EXPECTED_RETURN_TYPES`, `IMPORT_SAFETY_RULES`
  - `CallableSignatureError`, `validate_callable_signatures()`, `validate_return_annotations()`
  - Registry remains metadata-only — no runtime module loading in registry
  - Loader validation pipeline: presence → signature → return annotation
- `backend/api/` — Dataset API layer complete ✓
  - `POST /datasets/import/csv` — CSV upload → normalize → Parquet
  - `GET /datasets` — list stored datasets
  - `GET /datasets/{dataset_id}/ohlcv` — read normalized candles
  - Routes thin; business logic in `backend/api/services/dataset_service.py`
  - `get_storage_path` Depends injectable for test isolation
- `backend/core/config.py` — DEBUG parsing hardened ✓
  - boolean-like values accepted
  - non-boolean values such as `release` safely treated as `False`
- `backend/strategy_runtime/` — runtime orchestration foundation complete ✓
  - `StrategyExecutionContext` — frozen Pydantic v2; UTC-enforced; optional placeholders for portfolio/research context
  - `StrategyForecast`, `ForecastDirection` — structured forecast output; frontend-ready annotation model
  - `RunStatus`, `StrategyRunResult` — structured run output; reusable across all execution modes
  - `StrategyRuntimeRunner.run()` — full-window pipeline; never raises to caller; exceptions → `RunStatus.failed` with failed-stage diagnostics
  - `StrategyRuntimeRunner.run_bar_by_bar()` — skeleton; raises `NotImplementedError`
- `backend/services/` — OHLCVService orchestration layer complete ✓
  - `OHLCVService.get_ohlcv()` — inspect coverage → fetch missing → normalize → persist → return slice
  - `OHLCVService.get_ohlcv_by_provider_name()` — resolves adapter from `ProviderRegistry` then delegates
  - `OHLCVIngestionError` — wraps normalization and storage write failures at service boundary
  - `calculate_missing_ranges()`, `refresh_coverage()` — public utility methods
- `backend/data_providers/` — provider registry + Yahoo Finance adapter complete ✓
  - `ProviderRegistry` — in-process adapter store; register/get/deregister/list by lowercase provider name
  - `ProviderSymbolMapping`, `SymbolMapService` — symbol mapping foundation; identity fallback with normalized lookup/remove paths
  - `backend/data_providers/yahoo/` — `YahooFinanceAdapter(RangeProviderAdapter)`, `YahooInstrumentMetadata`, `resolve_yahoo_metadata()`
  - yfinance SDK isolated inside adapter; no SDK objects escape to services or strategies; intraday fetch bounds preserve time precision
- All other modules: empty stubs (backtesting, forward_testing, execution, etc.)
- No PostgreSQL integration yet

## Frontend Status

SCAFFOLD ONLY — not validated end-to-end

- Vite + React 18 + TypeScript skeleton present
- `npm install` not yet confirmed in current environment

## Installed Packages (backend `.venv`)

```
fastapi             0.136.1
uvicorn             0.46.0
pydantic            2.13.4
pydantic-settings   2.14.0
pydantic_core       2.46.4
starlette           1.0.0
anyio               4.13.0
pyarrow             24.0.0
duckdb              1.5.2
pyyaml              6.0.3
python-multipart    0.0.20   (required for UploadFile + Form)
yfinance            1.3.0    (Yahoo Finance adapter)
httpx               0.28.1   (dev)
pytest              9.0.3    (dev)
```

Python: 3.13 | venv: `.venv/` at repo root

## Completed Modules

- `backend/api/main.py` + `routes/health.py`
- `backend/api/schemas/dataset.py` — `DatasetInfo`, `DatasetListResponse`, `ImportCSVResponse`, `OHLCVCandle`, `DatasetOHLCVResponse`
- `backend/api/services/dataset_service.py` — `import_csv`, `list_datasets`, `read_ohlcv`, `make_dataset_id`, `parse_dataset_id`, `DatasetImportError`, `DatasetNotFoundError`
- `backend/api/routes/datasets.py` — `POST /datasets/import/csv`, `GET /datasets`, `GET /datasets/{dataset_id}/ohlcv`
- `backend/core/config.py` — `storage_base_path: Path` added, `logging.py`
- `backend/data/schemas.py` — `NormalizedOHLCV` (`extra="forbid"`, UTC-aware)
- `backend/data/validators.py` — `validate_ohlcv_record`, `validate_ohlcv_series`
- `backend/data/normalizer.py` — `DataNormalizer`, `NormalizationError`
- `backend/data_providers/base.py` — `BaseDataAdapter`
- `backend/data_providers/range_provider.py` — `RangeProviderAdapter` ABC with `fetch(start, end, **kwargs)`
- `backend/data_providers/csv_adapter.py` — `CSVAdapter(RangeProviderAdapter)`, `CSVAdapterConfig`, `CSVColumnMap`; implements `fetch()` via filter over full CSV load
- `backend/data/models/instrument.py` — `Instrument` (provider-independent identity), `AdjustmentMode`
- `backend/data/models/dataset.py` — `DatasetIdentity` (provider-specific, separates Yahoo/Polygon/IBKR)
- `backend/storage/parquet_store.py` — `write`, `read`, `dataset_path`, `StorageError`; `SCHEMA`, `records_to_table`, `table_to_records` (now public)
- `backend/storage/ohlcv_store.py` — provider-aware path builder + dedup/merge write service
- `backend/storage/coverage_registry.py` — file-based coverage metadata (earliest/latest/count per dataset)
- `backend/storage/duckdb_query.py` — `query_parquet`, `query_ohlcv`
- `backend/strategy_registry/models.py` — `StrategyLifecycleStage`, `RuntimeMode`, `StrategyManifest`
- `backend/strategy_registry/manifest.py` — `load_manifest`, `ManifestLoadError`
- `backend/strategy_registry/validator.py` — `validate_strategy_files`, `StrategyValidationError`
- `backend/strategy_registry/registry.py` — `StrategyRegistry`, `StrategyRegistryEntry`, `StrategyRegistryError`
- `backend/strategy_runtime/models.py` — `SignalType`, `StrategySignal`
- `backend/strategy_runtime/interface.py` — `REQUIRED_CALLABLES`, `CALLABLE_MODULE_MAP`, `RuntimeInterfaceError`, `validate_strategy_interface()`
- `backend/strategy_runtime/loader.py` — `StrategyLoadError`, `StrategyRuntimeReference`, `load_strategy_runtime()`
- `backend/strategy_runtime/signature_validator.py` — `CALLABLE_EXPECTED_PARAM_COUNTS`, `CALLABLE_EXPECTED_RETURN_TYPES`, `IMPORT_SAFETY_RULES`, `CallableSignatureError`, `validate_callable_signatures()`, `validate_return_annotations()`
- `strategies/example_strategy/` — all 8 required files present, callables conform to contract
- `backend/services/ohlcv_service.py` — `OHLCVService`, `OHLCVIngestionError`
- `backend/services/__init__.py` — public service exports
- `backend/strategy_runtime/execution_context.py` — `StrategyExecutionContext`
- `backend/strategy_runtime/forecast.py` — `ForecastDirection`, `StrategyForecast`
- `backend/strategy_runtime/run_result.py` — `RunStatus`, `StrategyRunResult`
- `backend/strategy_runtime/runner.py` — `StrategyRuntimeRunner`
- `backend/data_providers/provider_registry.py` — `ProviderRegistry`, `ProviderNotFoundError`, `DuplicateProviderError`
- `backend/data_providers/provider_symbol_map.py` — `ProviderSymbolMapping`, `SymbolMapService`, `ProviderSymbolMapError`
- `backend/data_providers/yahoo/__init__.py` — Yahoo provider package
- `backend/data_providers/yahoo/adapter.py` — `YahooFinanceAdapter`, `YahooAdapterError`, `SUPPORTED_TIMEFRAMES`
- `backend/data_providers/yahoo/metadata.py` — `YahooInstrumentMetadata`, `resolve_yahoo_metadata`, `YahooMetadataError`
- `tests/unit/` — full-suite snapshot after Phase 2J validation hardening: 526 passing
- `tests/fixtures/strategies/` — 7 fixture strategy folders

## Pending Modules

- `backend/strategy_runtime/` — bar-by-bar execution beyond current full-window foundation (skeleton present; backtesting integration deferred)
- `backend/backtesting/` — simulation engine
- `backend/forward_testing/`, `backend/execution/` — deferred
- `backend/services/` — additional service modules as needed
- First real strategy (consuming `NormalizedOHLCV` via `YahooFinanceAdapter` + `OHLCVService`)
- Frontend end-to-end validation

## Validation Status

| Check | Status |
|---|---|
| `GET /health` endpoint | PASS |
| `NormalizedOHLCV` schema validation | PASS (14 tests) |
| OHLCV numerical validators | PASS (15 tests) |
| CSV adapter + timestamp parsing | PASS (20 tests) |
| Normalization pipeline + integration | PASS (10 tests) |
| Instrument + DatasetIdentity models | PASS (22 tests) |
| OHLCVStore provider-aware write/read/merge/dedup | PASS (28 tests) |
| CoverageRegistry file-based tracking | PASS (20 tests) |
| OHLCVService orchestration (missing-range fetch, normalize, persist, slice) | PASS (34 tests) |
| StrategyExecutionContext + StrategyForecast + StrategyRunResult models | PASS (30 tests) |
| StrategyRuntimeRunner full-window + empty + failure + signal/forecast extraction | PASS (48 tests) |
| Parquet write/read round-trip | PASS (20 tests) |
| DuckDB query helper | PASS (18 tests) |
| Strategy manifest loading + validation | PASS (49 tests) |
| Strategy runtime interface + loader | PASS (40 tests) |
| Strategy callable signature validation | PASS (32 tests) |
| Dataset API — CSV import | PASS (11 tests) |
| Dataset API — list datasets | PASS (5 tests) |
| Dataset API — OHLCV read | PASS (9 tests) |
| Dataset API — id helpers | PASS (6 tests) |
| Settings / DEBUG parsing | PASS (11 tests) |
| ProviderRegistry — registration, resolution, deregistration | PASS (21 tests) |
| ProviderSymbolMapping + SymbolMapService | PASS (24 tests) |
| YahooFinanceAdapter — fetch, conversion, error handling (mocked) | PASS (26 tests) |
| OHLCVService registry integration (get_ohlcv_by_provider_name) | PASS (9 tests) |
| Architecture guardrails | PASS |
| Frontend build | NOT YET VALIDATED |

Full suite rerun (2026-05-09, Phase 2J validation hardening):
526 passed (1.05s) — 6 provider-validation tests added; zero regressions from prior 520.

Targeted provider-layer rerun (2026-05-09):
`test_provider_registry.py`, `test_provider_symbol_map.py`, `test_yahoo_adapter.py`, `test_ohlcv_service.py`, `test_ohlcv_service_registry.py` → 114 passed (0.81s)

Full suite rerun (2026-05-09, Phase 2I validation hardening):
446 passed (0.66s) — 6 runner-validation tests added; zero regressions from prior 440.

Targeted strategy runtime rerun (2026-05-09):
`test_strategy_runtime.py`, `test_strategy_runtime_runner.py` → 151 passed (0.11s)

Full suite rerun (2026-05-09, Phase 2H):
368 passed (0.58s) — 34 new tests added, zero regressions from prior 334.

Targeted post-validation rerun (2026-05-09, Phase 2G.5):
`test_instrument_models.py`, `test_ohlcv_store.py`, `test_coverage_registry.py`, `test_parquet_store.py`, `test_duckdb_query.py` → 109 passed (0.28s)

## Known Issues / Blockers

- `docker-compose.yml` at root is empty
- `directives/` undocumented in `docs/REPOSITORY_STRUCTURE.md`
- `ARCHITECTURE_GUARDRAILS.md` references "Edgelab" on line 4 (old name)
- Frontend `npm install` not yet run
- DuckDB 1.5.2 requires `pytz` for Python-side TIMESTAMPTZ conversion via `fetchall()` — storage layer avoids this by using `arrow().read_all()` (pyarrow path)
- Import-time side-effect detection is documentation-only — silent side effects (prints, env reads) cannot be statically enforced without running module code

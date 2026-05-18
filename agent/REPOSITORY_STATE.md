# REPOSITORY_STATE.md

## Current Branch
main

## Current Phase
PHASE 2N.12 — Browser-Level Draft Workspace Validation & Runtime Stabilization (complete)

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
- `backend/api/` — Dataset API + Market Data API + Strategy Runs API + Tools Discovery API complete ✓
  - `GET /market-data/ohlcv` — provider-based OHLCV fetch via YahooFinanceAdapter + OHLCVService
  - `GET /tools` — read-only tool metadata discovery via default tool registry
  - `POST /tools/validate-toolset` — validates submitted `StrategyToolSet` against registry; returns `{valid, errors}`
  - `POST /datasets/import/csv` — CSV upload → normalize → Parquet
  - `GET /datasets` — list stored datasets
  - `GET /datasets/{dataset_id}/ohlcv` — read normalized candles
  - Routes thin; business logic in `backend/api/services/dataset_service.py`
  - `get_storage_path` Depends injectable for test isolation
- `backend/tools/` — tool foundation + configuration contracts complete ✓
  - `ToolMetadata`, `ParameterSpec`, enums for category/status/visualization
  - `ToolRegistry` with default factory and SMA registration
  - `ToolConfiguration` — frozen Pydantic v2 model; instance_id + tool_id + parameters + enabled + display hints
  - `validate_tool_configuration()` — checks required params, type compatibility, min/max, unknown params; full error collection
  - `ConfigurationValidationError` — carries `.errors: list[str]`
  - discovery path remains execution-free; `compute_sma()` not used by API
- `backend/core/config.py` — DEBUG parsing hardened ✓
  - boolean-like values accepted
  - non-boolean values such as `release` safely treated as `False`
  - `strategies_base_path` — repo-root-relative, derived from `__file__` (launch-directory-independent)
- `backend/strategy_runtime/visualization.py` — visualization artifact contracts complete ✓
  - `IndicatorPoint` (frozen, UTC-enforced timestamp + value)
  - `IndicatorSeries` (name, kind, pane, color, points — frozen, strategy-agnostic)
  - `IndicatorSeriesKind` enum: `line` (future: histogram, area)
  - `IndicatorPane` enum: `price` (future: oscillator, separate)
- `backend/strategy_runtime/` — runtime orchestration foundation complete ✓
  - `StrategyExecutionContext` — frozen Pydantic v2; UTC-enforced; optional placeholders for portfolio/research context
  - `StrategyForecast`, `ForecastDirection` — structured forecast output; frontend-ready annotation model
  - `RunStatus`, `StrategyRunResult` — structured run output; includes `artifacts: list[IndicatorSeries]`
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
- Browser validation pass confirmed draft workflow remains metadata/composition only; no execution coupling added

## Frontend Status

OPERATIONAL — build + browser workflow validated

- Vite + React 18 + TypeScript
- `npm install` confirmed ✓
- `npm run build` passes with zero errors ✓
- `lightweight-charts` 5.2.0 installed (TradingView Lightweight Charts)
- Candlestick chart component (`Chart.tsx`) — renders via lightweight-charts v5 `CandlestickSeries`
- Controls component (`Controls.tsx`) — provider/symbol/asset_class/exchange/timeframe/start/end + Fetch button
- `frontend/src/api/marketData.ts` — typed client for `GET /market-data/ohlcv`
- `frontend/src/types/strategy.ts` — `StrategySignalOverlay`, `StrategyForecastOverlay`, `StrategyOverlay` types
- `frontend/vite.config.ts` — proxy: `/health`, `/market-data`, `/datasets`, `/strategy-runs`, `/tools`, `/drafts` → backend at :8000
- `frontend/src/types/tools.ts` — `ToolConfigurationInstance` interface (mirrors backend ToolConfiguration)
- `frontend/src/api/tools.ts` — typed `fetchTools()` client; `ToolListResponse`, `ToolMetadataResponse`, `ToolParameterResponse`
- `frontend/src/components/ToolPanel.tsx` — collapsible tool discovery cards; loads from `GET /tools`
- `frontend/src/components/ConfiguredToolList.tsx` — passive read-only display of `ToolConfigurationInstance[]`
- `frontend/src/components/DraftWorkspace.tsx` — list/detail synchronization hardened after patch/reorder/toggle responses
- `frontend/src/components/DraftDetailView.tsx` — per-draft validation/action state reset + lightweight request disabling
- Draft Workspace browser workflow validated end-to-end via live frontend/backend session

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
lightweight-charts  5.2.0    (frontend — TradingView candlestick chart)
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
- `backend/api/schemas/market_data.py` — `OHLCVCandleResponse`, `MarketDataOHLCVResponse`
- `backend/api/services/market_data_service.py` — `fetch_ohlcv`, `MarketDataError`, `UnsupportedProviderError`
- `backend/api/routes/market_data.py` — `GET /market-data/ohlcv`
- `backend/strategy_runtime/visualization.py` — `IndicatorPoint`, `IndicatorSeries`, `IndicatorSeriesKind`, `IndicatorPane`
- `backend/api/schemas/strategy_runs.py` — `StrategyRunRequest`, `SignalResponse`, `ForecastResponse`, `IndicatorPointResponse`, `IndicatorSeriesResponse`, `StrategyRunResponse`
- `backend/api/services/strategy_run_service.py` — `run_strategy`, `StrategyRunError`, `StrategyNotFoundError`; serializes `artifacts → indicators`
- `backend/api/routes/strategy_runs.py` — `POST /strategy-runs/run`
- `backend/tools/configuration.py` — `ToolConfiguration` (frozen Pydantic v2; instance_id, tool_id, parameters, enabled, display_name, color)
- `backend/tools/validation.py` — `ConfigurationValidationError`, `validate_tool_configuration()`, `ToolSetValidationResult`, `validate_strategy_toolset_against_registry()`, `_check_type_compatibility()`
- `backend/tools/toolset.py` — `StrategyToolSet` (frozen Pydantic v2; ordered tuple, duplicate instance_id rejection, get_tool/instance_ids/enabled_tools/__len__/__contains__)
- `frontend/src/types/tools.ts` — `ToolConfigurationInstance` + `StrategyToolSetData` interfaces
- `frontend/src/components/ConfiguredToolList.tsx` — passive configured-instance display component
- `frontend/src/components/ToolSetPanel.tsx` — passive ordered toolset display with position numbers, color accents, param chips
- `backend/strategy_registry/drafts.py` — `StrategyDraft` (frozen Pydantic v2; draft_id, display_name, toolset, created_at/updated_at UTC-enforced, enabled, tags, notes; `validate_against_registry()`)
- `backend/strategy_registry/draft_repository.py` — `DraftRepository` (filesystem JSON; save/load/update/archive/delete/list_all; `DraftNotFoundError`, `DraftAlreadyExistsError`, `DraftPersistenceError`)
- `backend/api/schemas/draft_composition.py` — `AddToolRequest`, `ReorderToolsRequest`, `PatchToolRequest`, `CompositionValidationResponse`
- `backend/api/services/draft_composition_service.py` — `add_tool`, `remove_tool`, `reorder_tools`, `patch_tool`, `validate_draft`; typed errors: `DraftCompositionError`, `ToolInstanceNotFoundError`, `ToolOrderError`, `ToolPatchError`
- `backend/api/routes/draft_composition.py` — 5 composition endpoints under `/drafts` prefix
- `backend/api/schemas/drafts.py` — `DraftCreateRequest`, `DraftUpdateRequest`, `DraftResponse`, `DraftListResponse`
- `backend/api/services/draft_service.py` — `create_draft`, `get_draft`, `list_drafts`, `update_draft`, `archive_draft`, `delete_draft`
- `backend/api/routes/drafts.py` — `GET/POST /drafts`, `GET/PUT/DELETE /drafts/{id}`, `POST /drafts/{id}/archive`
  - `backend/api/routes/draft_composition.py` — `POST /drafts/{id}/tools`, `DELETE /drafts/{id}/tools/{iid}`, `POST /drafts/{id}/tools/reorder`, `PATCH /drafts/{id}/tools/{iid}`, `POST /drafts/{id}/validate`
- `backend/api/schemas/tools.py` — `ToolParameterResponse`, `ToolMetadataResponse`, `ToolListResponse`, `ToolSetValidationResponse`
- `backend/api/services/tool_service.py` — `list_tools()` serialization + `validate_toolset()` delegation wrapper
- `backend/api/routes/tools.py` — `GET /tools`, `POST /tools/validate-toolset`
- `tests/unit/test_tools_api.py` — tool discovery API coverage (7 tests)
- `tests/unit/test_validate_toolset_api.py` — toolset validation API coverage (31 tests)
- `tests/unit/test_strategy_draft.py` — StrategyDraft model + validation + serialization + layer separation (45 tests)
- `frontend/src/types/drafts.ts` — `StrategyDraftData` interface
- `frontend/src/components/StrategyDraftCard.tsx` — passive draft display component
- `frontend/src/api/drafts.ts` — typed client: fetchDrafts/fetchDraft/createDraft/updateDraft/deleteDraft/archiveDraft + composition ops
- `frontend/src/components/DraftWorkspace.tsx` — 2-column workspace: draft list + detail/composition panes
- `frontend/src/components/DraftListPanel.tsx` — draft list with inline create form; clickable selection
- `frontend/src/components/DraftDetailView.tsx` — draft metadata + validate/archive/delete actions; validation result display
- `frontend/src/components/ToolCompositionPanel.tsx` — editable ordered toolset: reorder/enable/remove/patch params per tool
- `frontend/src/components/AddToolForm.tsx` — inline add-tool form: tool picker, dynamic param inputs, coercion, backend error display
- `frontend/src/api/marketData.ts` — typed `fetchOHLCV()` client
- `frontend/src/api/strategyRuns.ts` — typed `runStrategy()` client; `IndicatorPoint`, `IndicatorSeries`, `StrategyRunResponse` with `indicators`
- `frontend/src/types/strategy.ts` — `StrategySignalOverlay`, `StrategyForecastOverlay`, `StrategyOverlay` (includes `indicators`)
- `frontend/src/components/Chart.tsx` — generic artifact renderer: candlestick + indicator line series (lifecycle-managed Map) + signal markers + forecast line
- `frontend/src/components/Controls.tsx` — provider/symbol/timeframe/date-range controls
- `tests/unit/` — full-suite snapshot at Phase 2M completion: 576 passing
- `tests/unit/test_visualization_artifacts.py` — IndicatorPoint, IndicatorSeries, runner extraction
- `tests/fixtures/strategies/` — 7 fixture strategy folders

## Pending Modules

- `backend/strategy_runtime/` — bar-by-bar execution beyond current full-window foundation (skeleton present; backtesting integration deferred)
- `backend/backtesting/` — simulation engine
- `backend/forward_testing/`, `backend/execution/` — deferred
- `backend/services/` — additional service modules as needed
- First real strategy (consuming `NormalizedOHLCV` via `YahooFinanceAdapter` + `OHLCVService`)
- Optional targeted frontend tests for draft selection/synchronization

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
| Market data API — GET /market-data/ohlcv | PASS (11 tests) |
| Strategy runs API — POST /strategy-runs/run | PASS (19 tests) |
| Tools discovery API — GET /tools | PASS (7 tests) |
| Tool configuration model + validation | PASS (48 tests) |
| StrategyToolSet model + ordering + duplicate protection | PASS (43 tests) |
| Registry-backed toolset validation + ToolSetValidationResult | PASS (31 tests) |
| Toolset validation API — POST /tools/validate-toolset | PASS (31 tests) |
| StrategyDraft model + validation + serialization | PASS (45 tests) |
| DraftRepository filesystem persistence + errors | PASS (42 tests) |
| /drafts REST API — CRUD + archive + execution independence | PASS (27 tests) |
| Draft composition service — add/remove/reorder/patch/validate + immutability | PASS (44 tests) |
| Draft composition API — all 5 endpoints + regression + execution independence | PASS (36 tests) |
| Visualization artifact models + runner extraction | PASS (21 tests) |
| Architecture guardrails | PASS |
| Frontend npm install | PASS |
| Frontend build (tsc + vite build) | PASS |
| Draft Workspace browser workflow | PASS (live create/add/edit/reorder/toggle/validate/delete/archive/reload/restart) |

Browser validation rerun (2026-05-18, Phase 2N.12):
live frontend/backend + headless Chrome DevTools → PASS
* startup clean; `/drafts` + `/tools` reachable
* create draft → persisted and selectable
* add SMA tools → persisted and rendered
* patch/reorder/toggle → UI and backend stayed synchronized
* validate draft → `✓ valid` displayed
* seeded invalid draft → `✗ invalid` with backend error text displayed
* delete + archive → list/selection reset safely
* refresh + frontend/backend restart → persistence confirmed

Full suite rerun (2026-05-18, Phase 2N.11):
999 passed (1.62s) — no backend changes; frontend build 49 modules (clean).

Full suite rerun (2026-05-18, Phase 2N.10):
999 passed (1.47s) — 80 new draft composition tests added; zero regressions.

Full suite rerun (2026-05-18, Phase 2N.9):
919 passed (1.31s) — 69 new draft persistence + API tests added; zero regressions.

Full suite rerun (2026-05-18, Phase 2N.8):
850 passed (1.19s) — 45 new StrategyDraft tests added; zero regressions.

Full suite rerun (2026-05-18, Phase 2N.7):
805 passed (1.18s) — 31 new toolset validation API tests added; zero regressions.

Full suite rerun (2026-05-17, Phase 2N.6):
774 passed (1.25s) — 31 new registry-backed validation tests added; zero regressions.

Full suite rerun (2026-05-17, Phase 2N.5):
743 passed (1.22s) — 43 new StrategyToolSet tests added; zero regressions.

Full suite rerun (2026-05-17, Phase 2N.4):
700 passed (1.26s) — 48 new tool configuration tests added; zero regressions.

Full suite rerun (2026-05-17, Phase 2N.2):
652 passed (1.21s) — 7 new tool discovery API tests added; zero regressions.

Targeted tool rerun (2026-05-17, Phase 2N.2):
`test_tools.py`, `test_tools_api.py` → 76 passed (0.68s)

Full suite rerun (2026-05-09, Phase 2M):
576 passed (1.21s) — 24 new tests added, zero regressions from prior 552.

Full suite rerun (2026-05-09, Phase 2L):
552 passed (1.02s) — 15 new tests added, zero regressions from prior 537.

Full suite rerun (2026-05-09, Phase 2K):
537 passed (1.09s) — 11 new backend tests added, zero regressions from prior 526.

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
- DuckDB 1.5.2 requires `pytz` for Python-side TIMESTAMPTZ conversion via `fetchall()` — storage layer avoids this by using `arrow().read_all()` (pyarrow path)
- Import-time side-effect detection is documentation-only — silent side effects (prints, env reads) cannot be statically enforced without running module code

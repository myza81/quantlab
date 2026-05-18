# TASKS.md

## Purpose

This document manages implementation coordination, execution sequencing, repository maturity progression, and active development priorities for QuantLab.

This is not a simple TODO list.

The purpose of this document is to:

* coordinate implementation phases
* preserve architectural sequencing
* prevent premature implementation
* manage repository maturity evolution
* identify active priorities
* track dependencies and blockers
* maintain implementation continuity across AI sessions

This document should remain:
* operational
* structured
* high-signal
* modular
* current
* flexible

Avoid converting this file into:
* long-form project documentation
* architecture explanations
* implementation logs
* research notes
* bloated historical status records

TASKS.md is a living operational document.

It should be updated when priorities, blockers, active work, or repository maturity changes.

However, it must not become a full historical archive. Completed or obsolete details should be summarized, compressed, or moved out when they no longer help current execution.

---

# Current Repository Phase

## Active Phase

PHASE 2N.12 — BROWSER-LEVEL DRAFT WORKSPACE VALIDATION & RUNTIME STABILIZATION COMPLETE

Current repository focus:
* base scaffold established (backend, frontend, strategies, datasets)
* normalization layer complete (`backend/data/`, `backend/data_providers/`)
* storage layer hardened (`backend/storage/` — Parquet, DuckDB, provider-aware OHLCVStore, coverage registry)
* data models layer added (`backend/data/models/` — `Instrument`, `DatasetIdentity`, `AdjustmentMode`)
* strategy registry foundation complete (`backend/strategy_registry/`)
* strategy runtime interface + contract hardening complete (`backend/strategy_runtime/`)
* strategy runtime orchestration foundation complete (`backend/strategy_runtime/` — runner, context, forecast, result)
* OHLCV retrieval orchestration complete (`backend/services/` — `OHLCVService`)
* dataset API layer complete (`backend/api/routes/datasets.py`, `backend/api/services/dataset_service.py`, `backend/api/schemas/dataset.py`)
* DEBUG config parsing hardened (`backend/core/config.py`)
* provider registry foundation complete (`backend/data_providers/provider_registry.py`)
* provider symbol mapping foundation complete (`backend/data_providers/provider_symbol_map.py`)
* Yahoo Finance provider adapter complete (`backend/data_providers/yahoo/` — adapter + metadata)
* OHLCVService extended with registry integration method
* market data API route added (`GET /market-data/ohlcv`)
* tool registry foundation complete (`backend/tools/`)
* tool discovery API complete (`GET /tools`)
* frontend dynamic tool discovery complete (ToolPanel, tools.ts, vite proxy)
* tool configuration contracts complete (ToolConfiguration, validate_tool_configuration, ConfiguredToolList)
* strategy toolset contracts complete (StrategyToolSet, ToolSetPanel, duplicate protection, ordered collection)
* registry-backed toolset validation complete (ToolSetValidationResult, validate_strategy_toolset_against_registry)
* toolset validation API complete (`POST /tools/validate-toolset`, ToolSetValidationResponse, validate_toolset service)
* strategy draft contracts complete (StrategyDraft model, validate_against_registry, StrategyDraftCard component, StrategyDraftData type)
* strategy draft persistence complete (DraftRepository, draft service, /drafts REST API with CRUD + archive)
* strategy draft composition complete (add/remove/reorder/patch tool, validate endpoint, typed errors, immutable updates)
* frontend draft workspace complete (DraftWorkspace, DraftListPanel, DraftDetailView, ToolCompositionPanel, AddToolForm, drafts API client)
* browser-level Draft Workspace validation complete (startup, create, add tool, edit, reorder, toggle, validate, delete, archive, refresh, restart persistence)
* runtime stabilization complete for draft list synchronization and per-draft UI state reset
* frontend npm install confirmed, `tsc && vite build` passes
* candlestick chart component (lightweight-charts v5)
* provider/symbol/timeframe/date-range controls
* strategy overlay type placeholders
* 999 tests passing

Real historical data ingestion and frontend chart visualization now possible end-to-end via Yahoo Finance adapter through ProviderRegistry → OHLCVService → API → React chart pipeline.

Tool discovery metadata is now available to the frontend via a read-only backend endpoint, without introducing tool execution behavior.

Draft Workspace browser behavior is now validated end-to-end with backend authority preserved and no execution-layer expansion.

---

# Current Primary Objective

Establish a scalable and disciplined AI-assisted engineering foundation for QuantLab before major system implementation begins.

Priority focus:
* modularity
* architecture definition
* repository governance
* workflow structure
* system boundaries
* strategy portability
* execution isolation
* data abstraction

---

# Execution Domains

QuantLab currently operates through two separate execution domains:

ORCHESTRATION DOMAIN
→ architecture
→ governance
→ planning
→ blueprinting
→ workflow design
→ system decomposition
→ AI coordination

IMPLEMENTATION DOMAIN
→ coding
→ module implementation
→ frontend/backend systems
→ data pipelines
→ charting
→ strategy engine development
→ infrastructure execution

The orchestration domain is currently handled primarily by:

human operator
+ ChatGPT orchestration layer

The implementation domain will later be handled primarily by:

Claude
Codex
other implementation agents

TASKS.md must preserve this separation.

---

# Orchestration Layer Tasks

These tasks belong primarily to:

human operator
+ orchestration AI

These are architecture and governance activities — not implementation execution tasks.

---

## Orchestration Priority 1 — Governance Foundation

### Status

IN PROGRESS

### Objectives

Establish core governance and orchestration documents.

### Current Tasks

* [x] ARCHITECTURE_GUARDRAILS.md
* [x] WORKFLOW_GOVERNANCE.md
* [x] WORKFLOW_AGENT.md
* [x] PROMPT_RULES.md
* [x] HANDOFF.md
* [x] TASKS.md
* [x] SYSTEM_OVERVIEW.md
* [x] ARCHITECTURE.md
* [x] REPOSITORY_STRUCTURE.md
* [x] README.md (root)
* [x] STRATEGY_DEFINITION_ARCHITECTURE.md — formal vocabulary and composition model for strategy definitions
* [x] TOOL_REGISTRY_CONTRACT.md — governance and discovery contract for the Strategy Tools Builder ecosystem
* [x] FRONTEND_COMPOSITION_INTERFACE_CONTRACT.md — architectural bridge between frontend composition and backend validation/execution
* [x] BACKTESTING_ENGINE_CONTRACT.md — deterministic historical simulation architecture; reproducibility, audit, and lookahead-bias governance

### Notes

Governance quality currently takes priority over implementation speed.

Repository scaffolding session (2026-05-08) completed:
* README.md created at root
* .gitignore refactored for FastAPI, React/TS, DuckDB, Parquet, Redis, Celery/RQ stack
* Structural gap flagged: `directives/` folder is undocumented in `REPOSITORY_STRUCTURE.md` — recommend adding it to the structure doc under `agent/` or as a top-level entry

---

## Orchestration Priority 2 — Repository Structure Blueprint

### Status

PENDING

### Objectives

Define scalable repository structure for:

* backend
* frontend
* datasets
* strategy modules
* research modules
* execution systems
* infrastructure
* AI orchestration layers

### Key Requirements

* modular boundaries
* strategy portability
* execution isolation
* scalable research workflows
* AI-friendly organization
* low context fragmentation

---

## Orchestration Priority 3 — System Architecture Blueprint

### Status

PENDING

### Objectives

Define high-level QuantLab system architecture.

### Expected Scope

* backend domain structure
* frontend architecture
* strategy engine boundaries
* data pipeline flow
* execution layer separation
* storage architecture
* adapter architecture
* orchestration flow

### Deliverables

* SYSTEM_OVERVIEW.md
* ARCHITECTURE.md
* module relationship mapping

---

# Implementation Layer Tasks

These tasks belong primarily to implementation agents.

Implementation work should begin only after sufficient architectural clarity exists.

However, controlled validation-oriented detours are allowed earlier if they support foundational verification.

---

## Implementation Priority 0 — Base Scaffold

### Status

COMPLETED (2026-05-08)

### Deliverables

* `pyproject.toml` — Python project with FastAPI, uvicorn, pydantic-settings
* `backend/api/main.py` — FastAPI app
* `backend/api/routes/health.py` — GET /health endpoint
* `backend/core/config.py` — Pydantic settings
* `backend/core/logging.py` — structured logging setup
* `backend/data/`, `data_providers/`, `strategy_registry/`, `strategy_runtime/`, `backtesting/`, `forward_testing/`, `execution/`, `storage/`, `jobs/` — empty module stubs
* `frontend/` — Vite + React + TypeScript skeleton with health status display
* `strategies/example_strategy/` — placeholder strategy (parameters, features, signals, risk, validate_config)
* `datasets/` — folder structure (raw, normalized, processed, features, alternative, astronomical, metadata, cache)
* `.env.example` — updated with environment variable template

---

## Implementation Priority 1 — Data Architecture Layer

### Status

COMPLETED (2026-05-08)

### Objectives

Define normalized market and research data architecture.

### Deliverables

* `backend/data/schemas.py` — `NormalizedOHLCV` (immutable Pydantic model, UTC enforcement, canonical timeframes)
* `backend/data/validators.py` — `validate_ohlcv_record`, `validate_ohlcv_series` (numerical + time-series integrity)
* Validation sweep completed on 2026-05-08:
  `backend/data/` + `backend/data_providers/` reviewed against `docs/DATA_CONTRACT.md`
* Hardening applied:
  `NormalizedOHLCV` rejects unexpected extra fields; CSV Unix timestamp parsing handles out-of-range numeric values consistently
* Current verification status:
  backend unit suite in `.venv` passing at `59 tests`

---

## Implementation Priority 2 — Storage Layer

### Status

COMPLETED (2026-05-08)

### Deliverables

* `backend/storage/parquet_store.py` — canonical Parquet persistence for `NormalizedOHLCV`
* `backend/storage/duckdb_query.py` — DuckDB analytical query helpers returning dict rows or validated `NormalizedOHLCV`
* Dependencies added and recorded in `pyproject.toml`:
  `pyarrow`, `duckdb`
* Validation sweep completed on 2026-05-08:
  `backend/storage/` reviewed against `docs/DATA_CONTRACT.md` and architecture guardrails
* Hardening applied:
  `write()` now enforces venue consistency; `query_ohlcv()` now rejects naive `start`/`end` datetimes
* Current verification status:
  backend unit suite in `.venv` passing at `98 tests`
  `backend/data/` + `backend/data_providers/` + `tests/unit/` reviewed against `docs/DATA_CONTRACT.md`
* Hardening applied:
  `NormalizedOHLCV` rejects unexpected extra fields; CSV Unix timestamp parsing now handles out-of-range numeric values consistently
* Current verification status:
  backend unit suite in `.venv` passing at `59 tests`
* `backend/data/normalizer.py` — `DataNormalizer` + `NormalizationError`
* `backend/data_providers/base.py` — `BaseDataAdapter` abstract class
* `backend/data_providers/csv_adapter.py` — `CSVAdapter` with configurable column map + timestamp parsing
* `tests/unit/test_data_schemas.py`, `test_validators.py`, `test_csv_adapter.py`, `test_normalizer.py` — 56 tests, all passing
* `tests/fixtures/` — 5 CSV fixture files (valid, naive timestamps, unix timestamps, duplicate, malformed)

### Phase 2C additions (2026-05-08)

* `backend/storage/parquet_store.py` — `write`, `read`, `dataset_path`, `StorageError`
* `backend/storage/duckdb_query.py` — `query_parquet`, `query_ohlcv`
* `tests/unit/test_parquet_store.py` — 19 tests
* `tests/unit/test_duckdb_query.py` — 16 tests
* `pyproject.toml` updated: `pyarrow>=15.0.0`, `duckdb>=0.10.0`

### Deferred from Phase 2 data layer

* feature engineering pipeline
* alternative dataset support
* metadata storage (PostgreSQL)

### Important Constraints

Strategies must never directly consume raw provider schemas.

---

## Implementation Priority 2 — Minimal Validation Tooling

### Status

OPTIONAL / VALIDATION-DRIVEN

### Objectives

Allow early validation of foundational assumptions before major platform development.

### Possible Scope

* minimal OHLCV chart viewer
* temporary data inspection UI
* lightweight API validation endpoint
* normalization verification tooling
* dataset inspection utilities

### Notes

This work is allowed early when it helps validate:

* data correctness
* normalization quality
* ingestion flow
* frontend/backend contracts
* candlestick rendering assumptions

This does NOT imply that the full frontend research terminal is prioritized ahead of the core architecture.

---

## Implementation Priority 2D — Strategy Registry Foundation

### Status

COMPLETED (2026-05-08)

### Deliverables

* `backend/strategy_registry/models.py` — `StrategyLifecycleStage`, `RuntimeMode`, `StrategyManifest`
* `backend/strategy_registry/manifest.py` — `load_manifest`, `ManifestLoadError`
* `backend/strategy_registry/validator.py` — `validate_strategy_files`, `StrategyValidationError`, `REQUIRED_STRATEGY_FILES`
* `backend/strategy_registry/registry.py` — `StrategyRegistry`, `StrategyRegistryEntry`, `StrategyRegistryError`
* `strategies/example_strategy/strategy.yaml` — updated to conform to `StrategyManifest` contract
* `tests/unit/test_strategy_registry.py` — 49 tests, all passing
* `tests/fixtures/strategies/` — 5 fixture strategy folders
* `pyproject.toml` — added `pyyaml>=6.0`
* Current verification: `147 tests` passing

---

## Implementation Priority 2E — Strategy Runtime Interface

### Status

COMPLETED (2026-05-08)

### Deliverables

* `backend/strategy_runtime/models.py` — `SignalType`, `StrategySignal` (frozen Pydantic v2, UTC-enforced)
* `backend/strategy_runtime/interface.py` — `REQUIRED_CALLABLES`, `CALLABLE_MODULE_MAP`, `RuntimeInterfaceError`, `validate_strategy_interface()`
* `backend/strategy_runtime/loader.py` — `StrategyLoadError`, `StrategyRuntimeReference`, `load_strategy_runtime()`
* `strategies/example_strategy/` — `validate_config` moved to `validators.py`, `risk.py` contains only `apply_risk_rules`
* `tests/fixtures/strategies/missing_callable_strategy/` — new fixture
* `tests/unit/test_strategy_runtime.py` — 38 tests, all passing
* Current verification: `187 tests` passing

---

## Implementation Priority 2K — Minimal OHLCV + Strategy Visualization Foundation

### Status

COMPLETED (2026-05-09)

### Deliverables

* `backend/api/schemas/market_data.py` — `OHLCVCandleResponse`, `MarketDataOHLCVResponse`
* `backend/api/services/market_data_service.py` — `fetch_ohlcv`, `MarketDataError`, `UnsupportedProviderError`
* `backend/api/routes/market_data.py` — `GET /market-data/ohlcv`
* `backend/api/main.py` — market_data router registered
* `frontend/package.json` — `lightweight-charts@^5.2.0` added
* `frontend/vite.config.ts` — proxy extended to `/market-data`, `/datasets`
* `frontend/src/api/marketData.ts` — `fetchOHLCV()` typed API client
* `frontend/src/types/strategy.ts` — `StrategySignalOverlay`, `StrategyForecastOverlay` placeholder interfaces
* `frontend/src/components/Chart.tsx` — candlestick chart via lightweight-charts v5 `CandlestickSeries`
* `frontend/src/components/Controls.tsx` — provider/symbol/asset_class/exchange/timeframe/start/end controls + Fetch button
* `frontend/src/App.tsx` — updated with Controls + Chart + idle/loading/error/empty states
* `tests/unit/test_market_data_api.py` — 11 tests: happy path, field values, empty result, validation errors, 422 missing params, default values
* Current verification: `537 tests` passing (backend); `tsc && vite build` passes (frontend)

### Key Behaviour

* `GET /market-data/ohlcv` accepts provider, symbol, timeframe, start, end (required) + asset_class, exchange, adjustment_mode, currency (optional)
* Naive datetime query params treated as UTC at the route boundary
* Currently only `yahoo` provider supported; extend by adding to `_SUPPORTED_PROVIDERS` and wiring adapter in service
* Frontend chart uses `UTCTimestamp` (epoch seconds) for all timeframes including intraday
* Strategy overlay types are placeholders only — no rendering wired yet

### Deferred

* Manual end-to-end validation (backend + frontend running simultaneously)
* Volume panel on chart
* Strategy signal/forecast overlay rendering
* Additional provider support (Polygon, IBKR, Binance)
* Frontend component unit tests (no Vitest setup yet)

---

## Implementation Priority 2J — First Real Historical Provider + Provider Registry Foundation

### Status

COMPLETED (2026-05-09)

### Deliverables

* `backend/data_providers/provider_registry.py` — `ProviderRegistry`, `ProviderNotFoundError`, `DuplicateProviderError`
* `backend/data_providers/provider_symbol_map.py` — `ProviderSymbolMapping`, `SymbolMapService`, `ProviderSymbolMapError`; lookup/remove/filter normalization hardened
* `backend/data_providers/yahoo/adapter.py` — `YahooFinanceAdapter`, `YahooAdapterError`, `SUPPORTED_TIMEFRAMES`; intraday fetch-bounds precision hardened
* `backend/data_providers/yahoo/metadata.py` — `YahooInstrumentMetadata`, `resolve_yahoo_metadata`, `YahooMetadataError`
* `backend/data_providers/yahoo/__init__.py` — package exports
* `backend/data_providers/__init__.py` — updated with registry + symbol map exports
* `backend/services/ohlcv_service.py` — `get_ohlcv_by_provider_name()` registry integration method added
* `pyproject.toml` — `yfinance>=0.2.0` added (1.3.0 installed)
* `tests/unit/test_provider_registry.py` — 21 tests
* `tests/unit/test_provider_symbol_map.py` — 24 tests
* `tests/unit/test_yahoo_adapter.py` — 26 tests (all mocked, no network calls)
* `tests/unit/test_ohlcv_service_registry.py` — 9 tests
* Current verification: `526 tests` passing

### Key Behaviour

* yfinance isolated to `backend/data_providers/yahoo/adapter.py` — no SDK objects escape the adapter layer
* `ProviderRegistry` resolves adapters by lowercase name; existing `OHLCVService.get_ohlcv()` unchanged
* `SymbolMapService` defaults to identity when no explicit mapping — zero-config for providers using same symbol format; lookup paths now normalize surrounding whitespace consistently
* Yahoo adapter adds 1 day to `end` for daily/weekly/monthly (yfinance end is exclusive) and preserves intraday hour/minute precision
* `YahooFinanceAdapter.load()` raises `NotImplementedError` — network providers are range-only

### Deferred

* Polygon, IBKR, Binance, Bursa provider adapters
* Per-candle gap detection within coverage window
* Known-empty-range marker
* Provider arbitration / automatic fallback
* Full instrument master database

---

## Implementation Priority 2I — Strategy Runtime Orchestration Foundation

### Status

COMPLETED (2026-05-09)

### Deliverables

* `backend/strategy_runtime/execution_context.py` — `StrategyExecutionContext` (frozen Pydantic v2; UTC-enforced datetimes; optional placeholders for future portfolio/research context)
* `backend/strategy_runtime/forecast.py` — `ForecastDirection`, `StrategyForecast` (frozen Pydantic v2; confidence ∈ [0,1]; future frontend annotation model)
* `backend/strategy_runtime/run_result.py` — `RunStatus`, `StrategyRunResult` (frozen Pydantic v2; reusable across all execution modes)
* `backend/strategy_runtime/runner.py` — `StrategyRuntimeRunner`; full-window `run()` + bar-by-bar skeleton (`NotImplementedError`); failed-stage diagnostics + malformed reserved-payload warnings hardened in validation pass
* `backend/strategy_runtime/__init__.py` — updated with all new exports
* `tests/unit/test_strategy_runtime_runner.py` — 78 tests: context, forecast, result, runner success/empty/failure, call order, signal extraction, forecast extraction, validate_config warning, bar-by-bar skeleton, example_strategy integration
* Current verification: `446 tests` passing

### Key Behaviour

* `run()` always returns `StrategyRunResult` — never raises to caller; callable exceptions → `RunStatus.failed`
* Forecast support is optional — strategies with plain dict returns produce `forecasts=[]` without error
* Malformed reserved `"signals"` / `"forecasts"` payloads do not fail the run but now emit warnings for traceability
* `validate_config(False)` adds a warning but does not abort execution
* Empty candle input → `RunStatus.empty` without invoking any callables
* `run_bar_by_bar()` raises `NotImplementedError` — reserved for backtesting integration

### Deferred

* Bar-by-bar execution (backtesting integration)
* Portfolio context (initial_capital, instrument_id propagation) — placeholder fields present
* Result persistence / run log storage

---

## Implementation Priority 2H — OHLCV Retrieval Orchestration

### Status

COMPLETED (2026-05-09)

### Deliverables

* `backend/data_providers/range_provider.py` — `RangeProviderAdapter` ABC
* `backend/data_providers/csv_adapter.py` — `CSVAdapter` now implements `RangeProviderAdapter`; `fetch()` added
* `backend/services/ohlcv_service.py` — `OHLCVService`, `OHLCVIngestionError`
* `tests/unit/test_ohlcv_service.py` — 34 tests: full miss, full overlap, partial overlap ×2, empty provider, dedup, provider isolation, coverage sync, normalization error, input validation, missing-range calc, CSVAdapter.fetch()
* Current verification: `368 tests` passing

### Key Behaviour

* Provider called only for missing ranges — not for already-covered windows
* Incremental merge: new records merged with existing via `ohlcv_store.write(merge=True)`
* Coverage updated from full stored dataset after each successful ingestion batch
* Returned slice is bounded to requested `[start, end]` window only

### Deferred

* Per-candle gap detection
* Network-backed provider adapters
* Known-empty-range marker (avoid re-fetching confirmed-empty windows)

---

## Implementation Priority 2G.5 — Data Storage Architecture Hardening

### Status

COMPLETED (2026-05-09)

### Deliverables

* `backend/data/models/instrument.py` — `Instrument` (provider-independent), `AdjustmentMode`
* `backend/data/models/dataset.py` — `DatasetIdentity` (provider-specific, separation enforced)
* `backend/storage/ohlcv_store.py` — provider-aware path builder + write with dedup/merge + read/read_range; now rejects venue/provider mismatches before write
* `backend/storage/coverage_registry.py` — file-based coverage metadata (JSON per dataset); now rejects venue/provider mismatches before coverage update
* `backend/storage/parquet_store.py` — `SCHEMA`, `records_to_table`, `table_to_records` made public
* `tests/unit/test_instrument_models.py` — 22 tests
* `tests/unit/test_ohlcv_store.py` — 28 tests
* `tests/unit/test_coverage_registry.py` — 20 tests
* Current targeted verification: `109 tests` passing across Phase 2G.5 storage modules (`instrument_models`, `ohlcv_store`, `coverage_registry`, `parquet_store`, `duckdb_query`)

### Deferred

* Per-candle gap detection within coverage window
* PostgreSQL-backed coverage registry
* Updating `dataset_service.py` to use `ohlcv_store` (API layer change, out of phase scope)
* Provider reconciliation / arbitration

---

## Implementation Priority 2G — Dataset API Layer

### Status

COMPLETED (2026-05-08)

### Deliverables

* `backend/core/config.py` — added `storage_base_path: Path` (default `datasets/normalized`)
* `backend/api/schemas/dataset.py` — `DatasetInfo`, `DatasetListResponse`, `ImportCSVResponse`, `OHLCVCandle`, `DatasetOHLCVResponse`
* `backend/api/services/dataset_service.py` — `import_csv`, `list_datasets`, `read_ohlcv`, `make_dataset_id`, `parse_dataset_id`, `DatasetImportError`, `DatasetNotFoundError`
* `backend/api/routes/datasets.py` — `POST /datasets/import/csv`, `GET /datasets`, `GET /datasets/{dataset_id}/ohlcv`; `get_storage_path` Depends for testability
* `backend/api/main.py` — datasets router registered
* `pyproject.toml` — `python-multipart>=0.0.9` added
* `tests/unit/test_api_datasets.py` — 29 tests, all passing
* Current verification: `264 tests` passing

---

## Implementation Priority 2F — Strategy Runtime Contract Hardening

### Status

COMPLETED (2026-05-08)

### Deliverables

* `backend/strategy_runtime/signature_validator.py` — `CALLABLE_EXPECTED_PARAM_COUNTS`, `CALLABLE_EXPECTED_RETURN_TYPES`, `IMPORT_SAFETY_RULES`, `CallableSignatureError`, `validate_callable_signatures()`, `validate_return_annotations()`
* `backend/strategy_runtime/loader.py` — updated to call `validate_callable_signatures` and `validate_return_annotations` after interface check
* `backend/strategy_runtime/__init__.py` — all new symbols exported
* `tests/fixtures/strategies/wrong_signature_strategy/` — new fixture (wrong `build_features` param count)
* `tests/unit/test_strategy_runtime.py` — 32 new tests (72 total); full suite `221 tests` passing

---

## Implementation Priority 3 — Strategy Engine Foundation

### Status

PENDING

### Objectives

Define portable strategy architecture.

### Expected Scope

* strategy interfaces
* signal contracts
* feature contracts
* strategy lifecycle
* runtime isolation
* execution independence
* research workflow integration

### Important Constraints

Strategies must remain portable across:

* research
* backtesting
* forward testing
* paper trading
* future live trading

---

## Implementation Priority 4 — Research Environment Layer

### Status

PENDING

### Objectives

Design research-first workflows and experimentation infrastructure.

### Expected Scope

* feature experimentation
* cycle analysis workflows
* planetary/astronomical research support
* hypothesis testing workflows
* strategy comparison workflows
* research artifact management
* manual intervention support

### Important Constraints

Experimental research logic must remain isolated from production-grade execution systems.

---

## Implementation Priority 5 — Frontend Research Terminal

### Status

DEFERRED / INCREMENTAL

### Objectives

Design advanced research visualization environment.

### Expected Scope

* charting platform
* multi-pane synchronization
* drawing tools
* overlays
* signal inspection
* waveform-style rendering concepts
* annotation systems
* high-performance rendering
* research workflow UX

### Notes

Frontend capabilities may evolve incrementally.

Minimal validation-oriented charting work may occur much earlier.

### Important Constraints

Frontend must remain free from core business logic.

---

## Implementation Priority 5B — Strategy Tools Builder Layer (Permanent Evolving Capability)

### Status

PENDING — FOUNDATIONAL DIRECTION

### Context

The Strategy Tools Builder Layer is a permanent architectural direction formally established in Phase 2M documentation.

It is not a one-time feature. It is the evolving ecosystem through which users compose strategies from reusable tools.

### Objectives

Establish the foundational infrastructure for the Strategy Tools Builder Layer:

* reusable indicator and analytical tool modules (backend)
* tool registry and discovery
* parameterized tool contracts
* frontend composition interface for tool selection, configuration, and strategy authoring
* strategy definition schema that captures tool orchestration
* backend validation of tool-assembled strategy definitions

### Expected Tool Categories (Phase 1 foundation)

* classical indicators: MA, EMA, RSI, MACD, ATR
* volatility modules
* harmonic formula modules (later)
* planetary/astronomical cycle modules (later)

### Important Constraints

* All tools must be modular, reusable, and independently testable
* Frontend must orchestrate — backend must validate and execute
* No one-off tightly-coupled indicators
* Tools must be portable across all runtime modes

---

## Implementation Priority 6 — Backtesting Framework

### Status
DEFERRED


### Objectives

Develop deterministic and reproducible backtesting systems.

### Important Requirements

* deterministic results
* reproducibility
* parameter traceability
* dataset versioning
* execution assumptions
* slippage modeling
* auditability

---

## Implementation Priority 7 — Forward Testing & Paper Trading

### Status
DEFERRED

### Objectives

Establish runtime evaluation environments using real-time or near-real-time market data.

### Important Constraints

Forward testing and paper trading must use the same core strategy logic as backtesting.

---

## Implementation Priority 8 — Execution & Broker Layer

### Status
DEFERRED

### Objectives

Design isolated execution infrastructure.

### Expected Scope

* execution engine
* broker adapters
* portfolio constraints
* risk layer
* routing systems
* execution lifecycle

### Important Constraints

Execution systems must remain isolated from strategies.

---

## Implementation Priority 9 — Live Trading Infrastructure

### Status
LONG-TERM DEFERRED

### Objectives

Support future controlled live trading capability.

### Important Constraints

Live trading is NOT current priority.

No uncontrolled execution behavior should exist.

---

# Current Architectural Constraints

The following principles currently take highest priority:

* strategy portability
* modular boundaries
* data abstraction
* execution isolation
* AI orchestration discipline
* low token waste
* deterministic workflows
* incremental evolution

Avoid premature optimization and speculative infrastructure.

---

# Controlled Detour Rules

QuantLab development must remain flexible.

The task sequence is a recommended execution path, not a rigid waterfall plan.

Controlled detours are allowed when they support current learning, validation, or architectural confidence.

Examples of valid detours:
early charting canvas to validate OHLCV normalization
temporary data viewer to inspect ingestion quality
minimal API endpoint to test frontend/backend integration
prototype research screen to validate workflow assumptions
small visualization tool to expose data contract issues

A detour is valid only if it has a clear purpose and does not violate architecture guardrails.

Before starting a detour, agents should record:
why the detour is needed
what phase it supports
which modules are affected
what must remain out of scope
whether the work is prototype, temporary, or production-intended

Detours must not become uncontrolled scope expansion.

A minimal frontend chart may be introduced early to validate OHLCV data and normalization quality, even if the full research terminal and drawing tools remain deferred.

Such work should be treated as:
validation-supporting implementation

not as full frontend platform completion.

---

# Current Known Risks

## Governance Drift

As repository complexity increases, governance structures may require refactoring.

Agents should monitor:

* document scope quality
* operational clarity
* duplicated governance responsibilities
* oversized context documents
* stale workflows
* architecture fragmentation

---

## Premature Complexity

There is significant risk of:

* overengineering
* unnecessary abstractions
* speculative infrastructure
* infrastructure-first development

Current priority is:
small deterministic foundations

---

## AI Context Explosion

Large uncontrolled prompts and oversized documentation can degrade:
* reasoning quality
* implementation quality
* token efficiency
* operational consistency

Repository structure should remain modular and retrievable.

---

# Current Recommended Workflow

Preferred implementation flow:

architecture definition
→ repository structure
→ data contracts
→ strategy contracts
→ core engines
→ visualization systems
→ execution systems
→ runtime environments
→ future live infrastructure

Avoid skipping architectural sequencing.

However, tactical validation work may occur earlier when it helps prove or inspect foundational assumptions.

Example:
minimal OHLCV charting view

may be built early to validate:
* data ingestion
* normalization correctness
* timeframe handling
* candlestick rendering
* frontend/backend contract clarity

This does not mean the full frontend research terminal is promoted ahead of the data and strategy layers.

---

# Deferred Systems

The following systems are intentionally deferred until earlier architectural layers stabilize:
* live trading
* broker-specific optimization
* multi-user infrastructure
* distributed execution
* microservices architecture
* cloud orchestration
* advanced deployment automation
* high-frequency execution systems

QuantLab should evolve incrementally.

---

# Repository Maturity Direction

QuantLab is expected to evolve through increasing architectural maturity.

Governance structures, workflows, repository organization, and documentation boundaries are expected to evolve together with repository complexity.

Agents should recommend governance evolution and operational refactoring when repository maturity significantly increases.

---

# TASKS.md Maintenance Rules

TASKS.md must be actively maintained, but not endlessly expanded.

Agents should update TASKS.md when:
* new active work starts
* priority changes
* controlled detours are introduced
* blockers appear
* major tasks are completed
* maturity phase changes
* scope is intentionally deferred

Agents should avoid adding excessive historical details.

Completed work should be summarized under completed milestones or compressed into a short state note.

Detailed implementation history should live in:
* HANDOFF.md for recent session continuity
* commit messages for code-level history
* module documentation for durable design decisions

TASKS.md should answer:
* what should happen next?
* what is active now?
* what is blocked?
* what is intentionally deferred?
* what maturity phase are we in?

TASKS.md should not attempt to answer:
* everything that has ever happened
* all implementation details
* all design explanations
* all historical decisions

---

# Current Immediate Next Recommended Actions

Recommended next sequence:
1. Browser-level chart render validation (start both servers, open http://localhost:3000, fetch AAPL/yahoo/1d)
2. First real strategy consuming `NormalizedOHLCV` via `YahooFinanceAdapter` + `OHLCVService` + `StrategyRuntimeRunner`
3. Strategy run API endpoint + signal/forecast overlay rendering on chart
4. Update `dataset_service.py` to use `ohlcv_store` (provider-aware paths) when API layer changes are scoped
5. Fix "Edgelab" → "QuantLab" in `ARCHITECTURE_GUARDRAILS.md` (cosmetic)
6. `backend/backtesting/` — simulation engine (deferred until first strategy stable)

# REPOSITORY_STATE.md

## Current Branch
main

## Current Phase
PHASE 2R.1 — EMA Tool + Multi-Tool Computation Proof (complete)

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
- `backend/backtesting/` — simulation layer complete ✓
  - `models.py` — `PositionSizeMode` (FIXED_QUANTITY, EQUITY_FRACTION), `BacktestSimulationConfig`, `SimulationPriceBar`, `SimulatedTrade` (with sizing audit fields), `BacktestEquityPoint`, `BacktestRejection` (6 reasons incl. ZERO_QUANTITY), `BacktestSimulationResult`, `BacktestSimulationSummary`
  - `cost_model.py` — `CommissionMode`, `SlippageMode`, `TradeCostBreakdown`, compute helpers
  - `position_tracker.py` — `PositionState`, `resolve_position_quantity()`, `process_intent()`
  - `simulator.py` — `run_simulation()` — sequential, deterministic, long-only, single position
- All other modules: empty stubs (forward_testing, execution, etc.)
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
- `backend/strategy_registry/semantics.py` — all frozen Pydantic v2 semantic domain models; `condition_id`, `group_id`, `rule_id` stable IDs added (2O.3)
- `backend/strategy_registry/semantic_validator.py` — `validate_semantics_structure()` + `validate_semantic_identity_integrity()` — structural + ID uniqueness
- `backend/strategy_registry/semantic_identity.py` — `generate_id()`, `inject_ids()` — stable ID injection; idempotent; preserves existing IDs
- `backend/strategy_registry/semantic_plan.py` — `ConditionPlanNode`, `ConditionGroupPlanNode`, `RulePlanNode`, `DependencySet`, `CompilationDiagnostic`, `EvaluationPlan`, `CompilationResult` — passive evaluation plan contracts (2O.4)
- `backend/strategy_registry/semantic_compiler.py` — `compile_semantics()` — tree-walking structural compiler; no execution; preserves semantic IDs; extracts dependencies (2O.4)
- `backend/strategy_registry/drafts.py` — extended: `semantics: StrategySemantics | None = None` (backward-compatible)
- `backend/api/schemas/semantics.py` — `SemanticsUpdateRequest`, `SemanticsValidateRequest`, `SemanticsValidationResponse`, `SemanticsResponse`
- `backend/api/schemas/drafts.py` — `DraftResponse` now includes `semantics` field
- `backend/api/schemas/semantic_compilation.py` — `CompileRequest`, `CompilationResponse` (2O.4)
- `backend/api/services/semantic_service.py` — `get_semantics`, `set_semantics` (injects IDs), `validate_draft_semantics`, `validate_semantics_payload`
- `backend/api/services/semantic_compilation_service.py` — `compile_draft_semantics`, `compile_semantics_payload` (2O.4)
- `backend/api/routes/semantics.py` — `draft_router` (GET/PUT/POST `/drafts/{id}/semantics`) + `payload_router` (POST `/semantics/validate`)
- `backend/api/routes/semantic_compilation.py` — `draft_router` (POST `/drafts/{id}/semantics/compile`) + `payload_router` (POST `/semantics/compile`) (2O.4)
- `frontend/src/types/semantics.ts` — TypeScript mirrors including `condition_id?`, `group_id?`, `rule_id?`
- `frontend/src/types/semanticCompilation.ts` — TypeScript mirrors of compilation plan types (2O.4)
- `tests/unit/test_strategy_semantics.py` — 48 tests
- `tests/unit/test_semantic_validator.py` — 22 tests
- `tests/unit/test_semantics_api.py` — 20 tests
- `tests/unit/test_semantic_identity.py` — 30 tests (2O.3)
- `backend/strategy_registry/semantic_binding_validator.py` — `BindingDiagnostic`, `DependencySummary`, `BindingValidationResult`, `validate_semantic_bindings()` (2O.5)
- `backend/api/schemas/semantic_binding.py` — `BindingValidationResponse` (2O.5)
- `backend/api/services/semantic_binding_service.py` — `validate_draft_bindings()` (2O.5)
- `backend/api/routes/semantic_binding.py` — `POST /drafts/{id}/semantics/validate-bindings` (2O.5)
- `backend/api/schemas/semantic_compilation.py` — extended with `binding_valid`, `binding_diagnostics`, `dependency_summary` (2O.5)
- `tests/unit/test_semantic_compiler.py` — 54 tests (2O.4)
- `tests/unit/test_semantic_compilation_api.py` — 28 tests (2O.4)
- `tests/unit/test_semantic_binding_validator.py` — 25 tests (2O.5)
- `tests/unit/test_semantic_binding_api.py` — 21 tests (2O.5)
- `backend/strategy_registry/evaluator_contracts.py` — `EvaluationDiagnostic`, `ConditionEvaluationResult`, `GroupEvaluationResult`, `RuleEvaluationResult`, `EvaluationTrace`, `ResolvedValue`, `EvaluationContext`, `OperandResolver`, `OperatorEvaluator`, `ConditionEvaluator`, `GroupEvaluator`, `RuleEvaluator`, `EvaluationEngineContract` (2O.6)
- `backend/strategy_registry/evaluation_context.py` — `EvaluationContextDescriptor`, `EvaluationRequirements`, `ContextSatisfactionReport`, `extract_requirements()`, `check_context_satisfaction()` (2O.6)
- `backend/strategy_registry/plan_visitor.py` — `TraversalContext`, `PlanNodeVisitor`, `traverse_plan()` (2O.6)
- `docs/EVALUATION_CONTRACT_ARCHITECTURE.md` — evaluator architecture documentation (2O.6)
- `tests/unit/test_evaluator_contracts.py` — 71 tests (2O.6)
- `backend/strategy_registry/plan_inspector.py` — `ConditionNodeSummary`, `RuleNodeSummary`, `TopologySummary`, `DependencyInspectionSummary`, `DiagnosticsSummary`, `EvaluationPlanSummary`, `inspect_plan()` (2O.7)
- `backend/api/schemas/plan_inspection.py` — `PlanInspectionRequest`, `PlanInspectionResponse` (2O.7)
- `backend/api/services/plan_inspection_service.py` — `inspect_draft_plan()`, `inspect_semantics_payload()` (2O.7)
- `backend/api/routes/plan_inspection.py` — `GET /drafts/{id}/semantics/plan`, `POST /semantics/plan` (2O.7)
- `frontend/src/types/planInspection.ts` — TypeScript mirrors of all plan inspection types (2O.7)
- `tests/unit/test_plan_inspector.py` — 42 tests (2O.7)
- `tests/unit/test_plan_inspection_api.py` — 40 tests (2O.7)
- `frontend/src/api/planInspection.ts` — `fetchDraftPlanInspection()` + `fetchDraftReadiness()` (2O.8/2O.9)
- `frontend/src/components/PlanInspectionPanel.tsx` — read-only inspection + readiness badge/issues panel (2O.8/2O.9)
- `backend/strategy_registry/evaluation_readiness.py` — `ReadinessIssue`, `ReadinessSummary`, `EvaluationReadinessReport`, `check_readiness()`, 12 lint rules (2O.9)
- `backend/api/schemas/evaluation_readiness.py` — `EvaluationReadinessRequest`, `EvaluationReadinessResponse` (2O.9)
- `backend/api/services/evaluation_readiness_service.py` — `check_draft_readiness()`, `check_semantics_payload_readiness()` (2O.9)
- `backend/api/routes/evaluation_readiness.py` — `GET /drafts/{id}/semantics/readiness`, `POST /semantics/readiness` (2O.9)
- `tests/unit/test_evaluation_readiness.py` — 83 domain tests (2O.9)
- `tests/unit/test_evaluation_readiness_api.py` — 40 API tests (2O.9)
- `backend/strategy_registry/scalar_evaluation_context.py` — `ScalarContextError`, `ScalarEvaluationContext` (2P.1)
- `backend/strategy_registry/scalar_evaluator.py` — `UnsupportedOperatorError`, `SCALAR_OPERATORS`, `ScalarOperandResolver`, `ScalarOperatorEvaluator`, `ScalarConditionEvaluator`, `ScalarGroupEvaluator`, `ScalarRuleEvaluator`, `ScalarEvaluationEngine` (2P.1)
- `backend/api/schemas/scalar_evaluation.py` — `ScalarEvaluationRequest` (2P.1)
- `backend/api/services/scalar_evaluation_service.py` — `ScalarEvaluationError`, `evaluate_semantics_scalar()` (2P.1)
- `backend/api/routes/scalar_evaluation.py` — `POST /semantics/evaluate-scalar` (2P.1)
- `docs/SCALAR_EVALUATOR_FOUNDATION.md` — evaluator design, constraints, extension path (2P.1)
- `tests/unit/test_scalar_evaluator.py` — 97 unit tests (2P.1)
- `tests/unit/test_scalar_evaluation_api.py` — 21 API tests (2P.1)
- `backend/strategy_registry/historical_evaluator.py` — `HistoricalBarContext`, `HistoricalEvaluationInput`, `BarEvaluationResult`, `HistoricalEvaluationResult`, `_build_scalar_context()`, `evaluate_history()` (2P.2)
- `backend/api/schemas/historical_evaluation.py` — `HistoricalBarPayload`, `HistoricalEvaluationRequest` (2P.2)
- `backend/api/services/historical_evaluation_service.py` — `HistoricalEvaluationError`, `evaluate_history_from_payload()` (2P.2)
- `backend/api/routes/historical_evaluation.py` — `POST /semantics/evaluate-history` (2P.2)
- `docs/HISTORICAL_EVALUATION_ITERATOR.md` — iterator design, non-backtesting boundary documentation (2P.2)
- `tests/unit/test_historical_evaluator.py` — 62 unit tests (2P.2)
- `tests/unit/test_historical_evaluation_api.py` — 21 API tests (2P.2)
- `backend/strategy_registry/two_bar_context.py` — `PreviousBarMissingError`, `TwoBarEvaluationContext` (2P.3)
- `backend/strategy_registry/crossover_evaluator.py` — `CROSSOVER_OPERATORS`, `ALL_TWO_BAR_OPERATORS`, `CrossoverConditionEvaluator`, `TwoBarScalarEngine` (2P.3)
- `backend/strategy_registry/historical_evaluator.py` — updated: `_build_scalar_values()`, `TwoBarEvaluationContext` context, `TwoBarScalarEngine`, previous-bar propagation (2P.3)
- `docs/PREVIOUS_BAR_EVALUATION.md` — crossover semantics, first-bar behavior, example (2P.3)
- `tests/unit/test_crossover_evaluator.py` — 87 unit tests (2P.3)
- `backend/strategy_registry/signal_events.py` — `SignalEventKind`, `SignalEventSource`, `SignalEvent`, `SignalEventSummary`, `SignalEventBatch` (2P.4)
- `backend/strategy_registry/signal_event_extractor.py` — `extract_signal_events()`, deterministic ordering, summary computation (2P.4)
- `backend/api/services/signal_event_service.py` — `SignalEventExtractionError`, `extract_signal_events_from_payload()` (2P.4)
- `backend/api/routes/signal_events.py` — `POST /semantics/extract-signal-events` (2P.4)
- `docs/SIGNAL_EVENT_CONTRACTS.md` — signal event meaning, traceability, forbidden assumptions, future backtesting relationship (2P.4)
- `tests/unit/test_signal_events.py` — 88 unit + API tests (2P.4)
- `backend/strategy_registry/trade_intents.py` — `TradeIntentAction`, `TradeIntentSource`, `TradeIntent`, `TradeIntentSummary`, `TradeIntentBatch` (2P.5)
- `backend/strategy_registry/trade_intent_extractor.py` — `extract_trade_intents()`, `_ACTION_MAP`, `_make_intent_id()` (2P.5)
- `backend/api/services/trade_intent_service.py` — `extract_trade_intents_from_batch()` (2P.5)
- `backend/api/routes/trade_intents.py` — `POST /semantics/extract-trade-intents` (2P.5)
- `docs/TRADE_INTENT_CONTRACTS.md` — intent meaning, halal action minimalism, future execution relationship (2P.5)
- `tests/unit/test_trade_intents.py` — 86 unit + API tests (2P.5)
- `backend/backtesting/models.py` — `BacktestSimulationConfig`, `SimulationPriceBar`, `BacktestRejectionReason`, `BacktestRejection`, `SimulatedTrade`, `BacktestEquityPoint`, `BacktestSimulationSummary`, `BacktestSimulationResult` (2P.6)
- `backend/backtesting/position_tracker.py` — `PositionState`, `process_intent()` (2P.6)
- `backend/backtesting/simulator.py` — `run_simulation()` (2P.6)
- `backend/api/schemas/backtest_simulation.py` — `BacktestSimulationRequest` (2P.6)
- `backend/api/services/backtest_simulation_service.py` — `simulate_backtest()` (2P.6)
- `backend/api/routes/backtest_simulation.py` — `POST /backtests/simulate` (2P.6)
- `docs/BACKTEST_SIMULATION_FOUNDATION.md` — long-only scope, close-price assumption, halal constraints, extension path (2P.6)
- `tests/unit/test_backtest_simulation.py` — 95 unit + API + architecture guard tests (2P.6; updated 2P.7)
- `backend/backtesting/cost_model.py` — `CommissionMode`, `SlippageMode`, `TradeCostBreakdown`, compute helpers (2P.7)
- `docs/BACKTEST_COST_MODEL_FOUNDATION.md` — cost philosophy, execution price rules, PnL definition (2P.7)
- `tests/unit/test_backtest_cost_model.py` — 86 unit + API + architecture guard tests (2P.7)
- `tests/unit/test_backtest_position_sizing.py` — 83 unit + integration + architecture guard tests (2P.8)
- `docs/BACKTEST_POSITION_SIZING.md` — sizing modes, quantity formula, rejection reasons, audit fields, extension path (2P.8)
- `backend/tools/computation_models.py` — `ToolOutputPoint`, `ToolOutputSeries` (with `output_ref` property), `ToolComputationResult`; frozen Pydantic v2 (2R.0)
- `backend/tools/historical_computation.py` — `ToolComputationBarInput`, `ToolComputationError`, `compute_tool_outputs_for_history()`, `build_bar_tool_outputs()`, `_compute_sma_series()`, `_TOOL_DISPATCHERS` (2R.0)
- `backend/api/schemas/historical_evaluation.py` — `HistoricalEvaluationRequest.toolset: StrategyToolSet | None` field added (2R.0)
- `backend/api/services/historical_evaluation_service.py` — `evaluate_history_from_payload()` extended with toolset path + ambiguity rejection (2R.0)
- `docs/HISTORICAL_TOOL_COMPUTATION_PIPELINE.md` — architecture, warmup rules, output ref format, ambiguity rule, dispatcher, SMA details (2R.0)
- `tests/unit/test_historical_tool_computation.py` — 52 tests: output models, SMA correctness, warmup, no-lookahead, multi-instance, service integration, API integration, backward compat, crossover (2R.0)
- `backend/tools/ema.py` — `EMA_METADATA` (`tool_id="ema"`, `output_feature_names=("ema",)`, `stateful=True`), `compute_ema()` standalone visualization path; SMA-seed + recursive formula (2R.1)
- `backend/tools/historical_computation.py` — `_compute_ema_series()` + `_TOOL_DISPATCHERS["ema"]` registration (2R.1)
- `docs/EMA_TOOL_ARCHITECTURE.md` — formula, seed, warmup, dispatcher, multi-tool proof, semantic integration, extensibility (2R.1)
- `tests/unit/test_ema_tool.py` — 71 tests: metadata, standalone compute, pipeline correctness, warmup, no-lookahead, multi-instance, multi-tool (SMA+EMA), semantic integration, API, validation, error cases, architecture guards (2R.1)
- `create_default_registry()` now registers both SMA and EMA (2R.1)
- Total test suite: 2330 passing
- `frontend/src/api/semantics.ts` — `getSemantics`, `setSemantics`, `validateDraftSemantics`, `validateSemanticsPayload`
- `frontend/src/components/SemanticEditorPanel.tsx` — recursive condition group editor; operand widget; validate + save; ID-preserving spreads
- `frontend/src/types/drafts.ts` — `StrategyDraftData.semantics` field added
- `frontend/vite.config.ts` — `/semantics` proxy added
- Frontend build: 51 modules, `tsc && vite build` clean

## Pending Modules

- `backend/strategy_runtime/` — bar-by-bar execution beyond current full-window foundation (skeleton present; backtesting integration deferred)
- `backend/backtesting/` — simulation engine (foundation complete; slippage/fees/multi-asset deferred)
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
| Semantic compilation (EvaluationPlan IR) | PASS (54 tests) |
| Semantic binding validation | PASS (25 tests) |
| Evaluator contracts + plan visitor | PASS (71 tests) |
| Plan inspector + inspection API | PASS (82 tests) |
| Evaluation readiness + linting (12 rules) | PASS (123 tests) |
| Scalar evaluator (context, resolver, operator, condition, group, rule, engine) | PASS (97 tests) |
| Scalar evaluation API — POST /semantics/evaluate-scalar | PASS (21 tests) |
| Historical evaluation iterator (bar iteration, context build, traces, counts) | PASS (62 tests) |
| Historical evaluation API — POST /semantics/evaluate-history | PASS (21 tests) |
| Backtest position sizing — PositionSizeMode, resolve_position_quantity, ZERO_QUANTITY | PASS (83 tests) |
| Historical tool computation — ToolOutputPoint/Series/Result, SMA, warmup, no-lookahead | PASS (52 tests) |
| EMA tool — metadata, compute_ema, pipeline dispatch, warmup, no-lookahead, multi-tool proof | PASS (71 tests) |
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

Full suite rerun (2026-05-21, Phase 2O.9):
1483 passed — 83 new tests (readiness domain + API); zero regressions; frontend build clean (53 modules).

Full suite rerun (2026-05-21, Phase 2O.8):
1400 passed — zero regressions; frontend build clean (53 modules).

Targeted rerun (2026-05-19, Phase 2O.7):
82 passed — 42 (plan_inspector) + 40 (plan_inspection_api); new files only.

Full suite rerun (2026-05-23, Phase 2R.1):
2330 passed — 71 new tests (EMA metadata, computation, multi-tool proof, semantic integration); zero regressions.

Full suite rerun (2026-05-23, Phase 2R.0):
2259 passed — 52 new tests (historical tool computation pipeline, SMA dispatch, warmup, service/API integration); zero regressions; frontend build clean (53 modules).

Full suite rerun (2026-05-22, Phase 2P.8):
2207 passed — 83 new tests (position sizing, equity fraction, ZERO_QUANTITY, audit fields); zero regressions.

Full suite rerun (2026-05-21, Phase 2O.6):
1318 passed — 71 new tests (evaluator contracts, context satisfaction, plan visitor); zero regressions.

Full suite rerun (2026-05-19, Phase 2O.5):
1247 passed — 46 new tests (semantic binding validator + binding API); zero regressions.

Full suite rerun (2026-05-19, Phase 2O.4):
1201 passed (1.88s) — 82 new tests (semantic compiler + compilation API); zero regressions.

Full suite rerun (2026-05-19, Phase 2O.3):
1119 passed (1.64s) — 30 new semantic identity tests; zero regressions.

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

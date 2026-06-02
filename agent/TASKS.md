# TASKS.md

Active implementation coordination for QuantLab. Answers: what's next, what's active, what's blocked, what's deferred.
Not a historical archive — completed phase detail lives in `agent/archive/HANDOFF_HISTORY.md`.

---

# Current Phase Status

**Phase Chart-UX-3C.1 — Indicator Workspace Refinement — COMPLETE**
(backend: 4 847 ✓ unchanged | frontend: 471 ✓ | +5 new tests | frontend-only phase)
- **`frontend/src/types/chartIndicators.ts`** — `IndicatorInstance` interface extended with three new fields: `instanceLabel` (compact label derived from tool abbreviation + parameters, e.g. "SMA (20)"), `instanceColor` (palette-assigned hex color string, set by ChartIndicatorPanel), `visible` (boolean flag for hide/show, default true)
- **`frontend/src/components/ChartIndicatorPanel.tsx`** (rewritten, ~500 lines) — Complete UI overhaul to compact sidebar format:
  - **Header**: "Indicators (N)" title + "Add Indicator" button (opens picker)
  - **Picker dropdown**: Category groups (Trend/Momentum/Volatility/etc) + search by tool_id/display_name/description (reuses metadata)
  - **Instance rows**: Compact display (swatch · label · eye/settings/remove actions) — one row per instance, no expansion
  - **Collapsed editor**: Settings button opens parameter editor inline below row; Apply/Cancel buttons close editor; parameter changes trigger `computeArtifact` and update instanceLabel
  - **Color palette**: `const INSTANCE_PALETTE = [10 distinct hex colors]`; `nextPaletteColor()` assigns sequentially; each new instance gets unique color
  - **Clear All footer**: Removes all instances at once
  - **State**: `[instances, showPicker, searchQuery, editingId, editedParams, metaLoading, metaError]`
  - **Key functions**: `handleAddIndicator()` (adds instance with default params + calls computeArtifact), `handleToggleVisible()` (flip visible flag), `handleRemove()` (remove single), `handleClearAll()` (remove all), `handleApply()` (recompute + update label), `handleCancel()` (discard edits), `computeArtifact()` (call POST endpoint, store artifact in instance), `makeInstanceLabel()` (derive compact label from display_name abbrev + editable_parameters)
  - **Helper**: `makeInstanceLabel()` — reads parameters from `editedParams[instanceId]`, formats as e.g. "SMA (20)" or "EMA (20, alpha=0.1)"
  - **Reason**: Solves space consumption (forms → rows), visual distinctness (unique colors), and parameter persistence (artifacts stored per instance, not global)
- **`frontend/src/components/Chart.tsx`** (modified from Chart-UX-3C) — Multi-oscillator pane rendering + color override:
  - **New OscPane component** (~150 lines): Renders one pane per oscillator tool group (MACD, RSI, etc); filters null values (warmup bars); syncs time-scale bi-directionally with price chart; props: label, artifacts, instanceColors, priceChart
  - **Updated main Chart component**: New props `instanceColors: Map<string, string>` (instance_id → hex color) and `indicatorArtifacts` (pre-filtered for visible+non-null). New state: `oscArtifactGroups` (useMemo, grouped by tool_id, filtered for oscillator_pane series). Multiple OscPane renders (one per group). Color override: single-series overlays (SMA20/50/200) use instanceColor from palette, overriding backend default_color (enables visual distinctness).
  - **Artifact series lifecycle**: Separate map from strategy overlay (`artifactOscSeriesMapRef`); no interference with chart overlay pane oscillators
  - **Null warmup handling**: Preserved through entire pipeline (artifact → OscPane → renderer); never rendered as zero
  - **Reason**: Supports multi-instance indicator rendering with visual distinction; preserves oscillator pane visibility
- **`frontend/src/App.tsx`** (integrated) — Sidebar layout + parent state:
  - **Layout shift**: ChartIndicatorPanel moved from chart-area into left sidebar (alongside other controls)
  - **State management**: Changed from `indicatorArtifacts: IndicatorArtifactResponse[]` to `indicatorInstances: IndicatorInstance[]` (holds full instance lifecycle)
  - **Data derivation at Chart call-site**: `visibleArtifacts = indicatorInstances.filter(i => i.visible && i.artifact !== null).map(i => i.artifact!)` ; `instanceColors = new Map(indicatorInstances.map(i => [i.instanceId, i.instanceColor]))`
  - **Reset on context change**: `setIndicatorInstances([])` on `handleFetch` / `handleCatalogLoad` (keyed reset behavior)
  - **Sidebar style**: `overflow: 'auto'` allows vertical scrolling when many instances added
  - **Reason**: Parents owns instances; derives filtered data via side effects at render boundary
- **`frontend/src/components/__tests__/ChartIndicatorPanel.test.tsx`** — Comprehensive test suite (25 tests):
  - **Render/load** (tests 1-3): Component renders, Add button present, metadata loads without error
  - **Picker** (tests 4-7): Opens on Add click, category groups rendered, search by tool_id filters list, no-results state
  - **Add flow** (tests 8-10): Calls computeArtifact with instance+params, compact row appears, no expanded editor on add
  - **Editor** (tests 11-13): Settings opens editor inline, Cancel closes without recomputing, Apply recomputes and updates label
  - **Multi-instance** (tests 14-16): Multiple instances have distinct labels and colors, visibility toggle works, hidden instances excluded from onInstancesChange
  - **Removal** (tests 17-19): Remove single instance, others preserved, Clear All removes all
  - **Integration** (tests 20-25): onInstancesChange called on add/remove/apply, error state during compute, catalog notice displayed, disabled state when meta loading, null warmup values preserved, metadata fetch error handled
  - **Helper**: `renderPanel()` (accepts overrides for props/state, preserves null params via 'in' operator), `openPicker()` (waits for picker to open), `addIndicator()` (self-contained, clicks Add and waits for picker close)
  - **Reason**: Ensures all UX flows are testable and reproducible; guides future maintenance
- **TypeScript**: `tsc --noEmit` clean (removed unused `groupKey` parameter from OscPane signature and `currentInstances` parameter from computeArtifact function)
- **All 466 existing tests remain green** (471 total including 5 from Chart-UX-3C API tests)

**Phase Chart-UX-3B.1 — Metadata Consolidation — COMPLETE**
(backend: 4 847 ✓ | +31 new tests | frontend: 437 ✓ unchanged | backend-only phase)
- **`backend/tools/models.py`** — `ChartSeriesSpec` model added (frozen, extra=forbid; 5 required fields: series_id/label/pane/render_type/default_color); 9 new fields on `ToolMetadata` (all with safe defaults — backward-compatible): `chart_pane`, `chart_render_type`, `chart_series_kind`, `chart_category`, `chart_subcategory`, `chart_search_keywords`, `chart_display_order`, `chart_editable_parameters`, `chart_output_series`; `@model_validator(mode="after")` validates completeness for any `visible_on_chart=True` tool: (1) category must be indicator, (2) chart_pane/chart_render_type/chart_series_kind/chart_category/chart_output_series must all be non-None/non-empty — any violation raises ValueError at model construction time
- **`backend/tools/sma.py`, `ema.py`, `rsi.py`, `macd.py`, `atr.py`, `bollinger_bands.py`** — all 6 tools declare full chart metadata inline in ToolMetadata: chart_pane, chart_render_type, chart_series_kind, chart_category, chart_subcategory, chart_search_keywords, chart_display_order, chart_editable_parameters, chart_output_series (with ChartSeriesSpec instances); import `ChartSeriesSpec` added to each tool file
- **`backend/tools/__init__.py`** — `ChartSeriesSpec` exported from tools package
- **`backend/api/services/chart_indicator_service.py`** — `_CHART_DISPLAY_METADATA` static dict removed entirely; `list_chart_indicators()` rebuilt to read only from ToolMetadata fields (no secondary dict); `compute_indicator_artifact()` reads `metadata.chart_pane`, `metadata.chart_output_series`, `metadata.name` etc. directly; `_empty_artifact` and `_build_artifact_response` refactored to accept `metadata: ToolMetadata` instead of `display: dict`; chart is now fully registry-driven — adding a new tool never requires modifying this file
- **`tests/unit/test_chart_indicator_api.py`** — 31 new tests: `TestChartMetadataMigration` (11 — parametrized pane+category check for 6 tools; completeness check for all 6; MACD 3-series IDs in metadata; MACD histogram render_type; BB 3-series IDs; series_ids align with output_feature_names; subcategory for SMA+EMA; display_order ordering), `TestRegistryDrivenDiscovery` (3 — no static dict in service module; new custom tool appears automatically in GET /chart/indicators; response fields reflect ToolMetadata not external dict), `TestChartMetadataValidation` (4 — missing chart_pane raises; missing output_series raises; wrong category raises; False bypasses all validation), `TestChartSeriesSpec` (4 — creation/frozen/extra-forbidden/exported)
- **All 54 original Chart-UX-3B tests remain green**

**Phase Chart-UX-3B — Backend Indicator Artifact Endpoint — COMPLETE**
(backend: 4 816 ✓ | +54 new tests | frontend: 437 ✓ unchanged | backend-only phase)
- **`backend/tools/models.py`** — `visible_on_chart: bool = False` added to `ToolMetadata` (optional field with default, backward-compatible with all existing test fixtures and tool registrations)
- **`backend/tools/sma.py`, `ema.py`, `rsi.py`, `macd.py`, `atr.py`, `bollinger_bands.py`** — all 6 built-in tools set `visible_on_chart=True`
- **`backend/api/schemas/chart.py`** (NEW): `IndicatorArtifactRequest` (tool_id, instance_id, symbol, provider, timeframe, date_range, parameters, asset_class, exchange, credential_id); `IndicatorSeriesPoint` (timestamp str + Optional[float] value); `IndicatorArtifactSeries` (series_id, label, pane, render_type, default_color, values); `IndicatorArtifactResponse` (tool_id, instance_id, display_name, pane, render_type, parameters, series, warmup_bars, diagnostics); `ChartIndicatorMetadata` + `ChartIndicatorsListResponse` for picker
- **`backend/api/services/chart_indicator_service.py`** (NEW): `ToolNotChartVisibleError`, `IndicatorArtifactError`, `IndicatorParameterError` exceptions; `_CHART_DISPLAY_METADATA` static dict (6 tools — bridges gap until Chart-UX-3D migrates into ToolMetadata); `list_chart_indicators(registry)` (filters `visible_on_chart=True` AND `category=indicator`, stable sort by category+tool_id); `compute_indicator_artifact(...)` (14-arg function: validates visibility, resolves vault API key via existing `_resolve_provider_api_key`, builds OHLCVService adapter, fetches candles, converts to `ToolComputationBarInput`, creates single-tool `StrategyToolSet`, calls `compute_tool_outputs_for_history`, builds timestamp-aligned response with null for warmup bars); `_build_artifact_response` (max warmup across all series; per-bar null/value mapping using output_name → {bar_index: value} dict)
- **`backend/api/routes/chart.py`** (NEW): `router = APIRouter(prefix="/chart")`; `GET /chart/indicators` (intentionally public, no auth); `POST /chart/indicator-artifact` (`require_active_subscription`); exception mapping: `ToolNotFoundError→404`, `ToolNotChartVisibleError→400`, `IndicatorParameterError→422`, `IndicatorArtifactError→400`
- **`backend/api/main.py`** — `chart.router` imported and registered
- **`tests/unit/test_chart_indicator_api.py`** (NEW, 54 tests): indicator list (9 tests), artifact auth/validation (3), SMA (8 incl. warmup null, timestamp presence, count alignment), EMA (3), RSI (3), MACD (5 incl. 3-series, histogram render_type, max warmup), Bollinger (3), ATR (3), no-data (2), computation consistency (4 — SMA/EMA/MACD/Bollinger chart values == `compute_tool_outputs_for_history` direct call for identical bars), `visible_on_chart` field tests (7 — default False, all 6 builtins True)
- **Pre-existing unrelated failure**: 6 tests in `test_polygon_provider.py::TestPolygonArchitectureBoundary` fail due to stale `/Volumes/externalDrive/...` path on this machine; not introduced by this phase

**Phase Chart-UX-3A.1 — Chart Indicator Tool Contract Hardening — COMPLETE**
(backend: 4 762 ✓ unchanged | frontend: 437 ✓ unchanged | no code changes — governance/documentation phase)
- **`docs/CHART_INDICATOR_TOOL_CONTRACT.md`** updated from 15 sections to 20 sections:
  - **§4 Tool-Type Taxonomy** (NEW): `indicator` / `strategy_helper` / `risk_helper` / `portfolio_helper` / `execution_helper` / `analysis_helper`; only `tool_type=indicator` may declare `visible_on_chart=true`; §4.7 enforcement rule: registry validation must reject chart-visibility for non-indicator types
  - **§5** (was §4): renamed "Chart Rendering Classification" to clarify it governs HOW chart-visible tools render, not WHAT tool type they are; §5.6 "Non-Visual Indicator" clarified as an indicator that elects not to be chart-visible (distinct from non-indicator tool types)
  - **§6** (was §5): added `tool_type` as first required field in table; updated §6.3 reference metadata to include discovery fields for all 6 tools
  - **§7 Tool Discovery Metadata** (NEW): `category`, `subcategory`, `search_keywords`, `display_order`; category enum (Trend/Momentum/Volatility/Volume/Market Structure/Pattern Recognition/Risk/Custom); picker must be fully metadata-driven; §7.4 category assignment table for all 6 existing tools
  - **§8** (was §6): unchanged, renumbered
  - **§9 Multiple Indicator Instance Support** (NEW): `tool_id` vs `instance_id` separation; same tool, multiple independent concurrent instances (e.g. ema_20 + ema_50 + ema_200); instance isolation rules; instance_id assignment patterns; indicator lifecycle; alignment with `ToolConfiguration.instance_id` in Strategy Builder
  - **§10 Indicator Presets** (NEW): `preset_id`/`name`/`tool_id`/`parameters`; 9 built-in platform presets (EMA 20/50/200, SMA 20/50/200, RSI 14, MACD Standard, BB 20,2); presets are convenience wrappers only — no separate computation; user-defined presets deferred to Chart-UX-3E
  - **§11–§13** (were §7–§9): renumbered; §12.1 updated to reference `instance_id` per §9; §13.1 updated to clarify `instance_id` echo in response
  - **§14** (was §10): extended onboarding checklist by 6 new items (tool_type, discovery metadata fields, multi-instance isolation, preset registration)
  - **§15 Experimental Indicator Promotion Lifecycle** (NEW): Research Sandbox → Experimental → Validated → Registry Tool → Chart-Visible → Strategy Usage → Backtest/FT/PT; promotion gates for each transition; demotion requires deprecation, not silent rollback
  - **§16** (was §11): §16.4 updated (covers both `tool_type` and `visible_on_chart`); §16.7 (NEW — non-indicator tools cannot be chart-visible without explicit contract revision); §16.8 (NEW — hardcoded indicator picker UI forbidden)
  - **§17** (was §12): §17.7 (NEW — tool-type taxonomy tests); §17.8 (NEW — discovery metadata tests); §17.9 (NEW — multi-instance isolation tests); §17.10 (NEW — preset tests)
  - **§18** (was §13): roadmap updated — 3B now includes `GET /chart/indicators` endpoint and tool_type enforcement; 3C now includes multi-instance and preset picker
  - **§19–§20** (were §14–§15): renumbered; §20 added new alignment notes for `_TOOL_DISPATCHERS` tool_type enforcement gap and missing `tool_type` field in existing tool metadata objects

**Phase Chart-UX-3A — Chart Indicator Tool Contract — COMPLETE**
(backend: 4 762 ✓ unchanged | frontend: 437 ✓ unchanged | no code changes — architecture/documentation phase)
- **`docs/CHART_INDICATOR_TOOL_CONTRACT.md`** (NEW) — 15-section architecture contract:
  - §1 Purpose: extends `TOOL_REGISTRY_CONTRACT.md` for chart-visible tools
  - §2 Problem statement: tools usable in Strategy Builder but not on Chart page; Bollinger Bands backend complete but frontend not wired
  - §3 Design principle: one tool, one computation, multiple consumers (Chart / Strategy Builder / Backtest / Forward Test / Paper Trading)
  - §4 Tool classification: 6 categories — overlay indicator, oscillator/separate-pane, multi-series, event/marker, drawing object (out of scope), non-visual/internal helper
  - §5 Visualization metadata contract: 9 required fields (`visible_on_chart`, `chart_pane`, `render_type`, `series_kind`, `default_parameters`, `editable_parameters`, `source_field`, `warmup_bars_required`, `output_series`, `display_name`, `description`); `OutputSeriesSpec` sub-schema; non-normative reference metadata for all 6 existing tools (sma/ema/rsi/macd/bollinger_bands/atr)
  - §6 Overlay vs pane behavior: price overlay / oscillator pane / event markers / multi-pane rules
  - §7 Parameter editing rules: editable_parameters must be subset of tool's registered schema; chart and Strategy Builder share same schema; parameter changes trigger backend recomputation
  - §8 Backend computation rule: frontend sends (tool_id, instance_id, symbol, timeframe, provider, date_range, parameters); backend computes via existing `_TOOL_DISPATCHERS`
  - §9 Indicator artifact response contract: conceptual shape with timestamps/values/null warmup/diagnostics; series alignment requirement
  - §10 Future custom tool onboarding: 10-item checklist; non-visual tools must declare `visible_on_chart: false`
  - §11 Forbidden patterns: 6 explicit violations — frontend-only official computation, duplicate formulas, hardcoded tool-specific rendering, missing `visible_on_chart`, bypassing normalized data, strategy-identity-aware chart rendering
  - §12 Testing expectations: 6 test categories — metadata registration, parameter schema mapping, backend computation consistency, chart artifact rendering, warmup/null behavior, overlay vs pane classification
  - §13 Phased roadmap: Chart-UX-3B (backend endpoint) → Chart-UX-3C (frontend panel) → Chart-UX-3D (onboard 6 tools) → Chart-UX-3E (promotion workflow)
  - §14 Architectural alignment: references §9, §3/4, §27 of ARCHITECTURE_GUARDRAILS.md
  - §15 Existing code alignment notes: Chart.tsx overlay wiring, toolVisualization.ts types, `_TOOL_DISPATCHERS` integration point, Bollinger Bands backend-complete status, /chart/ route prefix needed

**Phase Chart-UX-2 — Provider Search Capability & Polygon Resolver — COMPLETE**
(backend: 4 762 ✓ | frontend: 437 ✓ | `npm run build` ✓)
- **`backend/data_providers/base.py`** — `ProviderCapabilities.supports_search: bool = False` field added
- **`backend/data_providers/polygon/search.py`** (NEW) — `search_polygon(*, query, limit, api_key)` via Polygon `/v3/reference/tickers`; `_resolve_key()` (vault→ENV fallback); HTTP 401/500 → raise `PolygonSearchError`; HTTP 404/429 → `[]`; `_normalize()` maps type codes → asset_class + MIC codes → display names; `_TYPE_MAP`, `_EXCHANGE_MAP`, `_TYPE_LABEL_MAP`
- **`backend/data_providers/provider_factory.py`** — `register_searcher()` now sets `supports_search=True` via `model_copy`; `search()` stops swallowing exceptions, adds `api_key: str | None = None` forwarding; `_search_yahoo()` updated for `api_key` kwarg; `_search_polygon()` lazy-import wrapper added; `create_default_factory_registry()` registers polygon searcher
- **`backend/api/services/asset_search_service.py`** — `ProviderSearchNotSupported` exception added; `search_assets()` checks `caps.supports_search` before dispatch; wraps searcher errors as `AssetSearchError("Search failed...")`; accepts `api_key: Optional[str] = None`
- **`backend/api/schemas/market_data.py`** — `supports_search: bool = False` added to `ProviderCapabilitiesResponse`
- **`backend/api/services/market_data_service.py`** — `list_providers()` passes `supports_search=c.supports_search`
- **`backend/api/routes/market_data.py`** — `GET /market-data/search` adds `credential_id` param; resolves API key via `_resolve_provider_api_key`; handles `ProviderSearchNotSupported` → 400
- **`frontend/src/types/assetSearch.ts`** — `SearchErrorKind` type + `AssetSearchError` class added
- **`frontend/src/api/assetSearch.ts`** — `searchAssets()` adds `credentialId?` param; classifies HTTP errors by message pattern → typed `AssetSearchError`
- **`frontend/src/components/AssetResolverInput.tsx`** — `credentialId?` prop; `searchError: SearchErrorKind | null` state; shows `asset-resolver-unsupported`, `asset-resolver-error`, `asset-resolver-unknown_provider` messages instead of generic "No results"; old `emptyMsg` → `statusMsg` style (reused for all status messages)
- **`frontend/src/components/Controls.tsx`** — passes `credentialId` to `AssetResolverInput` when Polygon is selected
- **Tests**: `test_polygon_search.py` (NEW — 18 tests: normalize unit + HTTP mocks + auth/rate-limit/error paths + architecture boundary); `test_market_data_api.py` `TestSearchCapability` (9 tests: capability matrix, unsupported 400, unknown 400, searcher-raise 400, Polygon dispatch, schema consistency); `AssetResolverInput.test.tsx` (+7 error-state + credentialId tests, 19 total)
- **Provider search matrix**: yahoo ✓ | polygon ✓ | csv ✗ | parquet ✗

**Phase MD-1 — Historical OHLCV Cache Policy Hardening — COMPLETE**
(backend: 4 734 ✓ | frontend: 430 ✓ unchanged | `npm run build` ✓ unchanged)
- **`backend/services/ohlcv_service.py`** — two MD-1 hardening additions:
  1. `_EmptyResponseGuard` class — file-backed (JSON sidecar) 15-min negative cache; prevents repeated provider calls for ranges known to return 0 records; per-gap key = `start_iso|end_iso`; expired entries pruned lazily on every write; corrupt/missing sidecar treated as no guard (safe fallback)
  2. `_trailing_edge_is_stale(identity, latest_ts, *, _now=None)` — returns True when the latest stored bar hasn't yet been finalized (candle period + 60s buffer not elapsed); deterministic via `_now` parameter for testing
  3. `_fetch_and_store()` modified — after full boundary coverage confirmed, if trailing bar is stale AND trail_start <= end, re-fetches trailing edge; in gap loop, checks guard before calling provider and records guard when empty
  4. `_EMPTY_RESPONSE_TTL_SECONDS = 900` module constant
- **`tests/unit/test_ohlcv_service.py`** — 15 new tests in two classes:
  - `TestEmptyResponseGuard` (7 tests): unguarded/guarded/different-gap/expired/corrupt-sidecar/TTL-constant/prevents-double-call
  - `TestTrailingEdgeFreshness` (8 tests): finalized-bar-not-stale/unfinalized-is-stale/exactly-at-close-plus-buffer/naive-ts-defensive; integration: finalized-no-refetch/unfinalized-triggers-refetch/stale-beyond-requested-end-skipped
- **`tests/unit/test_market_data_api.py`** — 4 new tests in `TestCacheRegression`:
  - repeated identical request calls provider only once (boundary-exact candles)
  - second request served from cache despite provider going offline
  - partial range extension fetches only missing gap (Jan–Mar cached → Jan–Apr request → 2 total calls, 4 candles)
  - backward-compat: explicit exchange= still works
- **Identity decisions (MD-1 §6)**:
  - **Currency** excluded from storage identity: same data regardless of display currency; normalization pipeline does not transform currency; safe to keep excluded
  - **Credential_id** excluded from storage identity: selects API key, not data; two fetches for same symbol via different credentials produce identical normalized OHLCV; safe to keep excluded
- **Default exchange decision (MD-1 §7)**: `"unknown"` is the correct behavior when exchange is omitted; provider-agnostic; `test_default_asset_class_and_exchange` was renamed to `test_default_asset_class` (exchange assertion removed) + `test_omitted_exchange_defaults_to_unknown` added in previous session
- **Coverage integrity (MD-1 §5)**: per-candle gap detection not implemented — boundary-only coverage is the established contract; internal gaps (e.g. market holidays) are not detectable without calendar-aware logic; documented as limitation; TODO added in HANDOFF

**Phase Chart-UX — Asset Resolver + Exchange Optional — COMPLETE**
(backend: 4 716 ✓ | frontend: 430 ✓ | `npm run build` ✓)
- **`backend/data_providers/yahoo/search.py`** (new) — `search_yahoo(query, limit)` via `yfinance.Search`; maps `quoteType→asset_class`; returns `[]` on any error (graceful)
- **`backend/api/schemas/market_data.py`** — added `AssetSearchResult` + `AssetSearchResponse` schemas
- **`backend/data_providers/provider_factory.py`** — added `_searchers` dict, `register_searcher()`, `search()` methods; `create_default_factory_registry()` registers yahoo searcher
- **`backend/api/services/asset_search_service.py`** (new) — `search_assets(query, provider, limit, factory)`; validates 2–100 char query; dispatches via factory; returns `AssetSearchResponse`
- **`backend/api/routes/market_data.py`** — added `GET /market-data/search` (q, provider, limit); changed `exchange` default `"NASDAQ"→""` on `/ohlcv`
- **`backend/api/services/market_data_service.py`** — `exchange: str = ""`; `effective_exchange = exchange.strip() or "unknown"` (normalises missing exchange)
- **`frontend/src/types/assetSearch.ts`** (new) — `AssetSearchResult` + `AssetSearchResponse` types
- **`frontend/src/api/assetSearch.ts`** (new) — `searchAssets(query, provider, limit)` → `GET /market-data/search`
- **`frontend/src/components/AssetResolverInput.tsx`** (new) — TradingView-style autocomplete; 300ms debounce; keyboard nav (Arrow/Enter/Escape); selected chip + clear button; testids: `asset-resolver-input/selected/clear/dropdown/result-{i}/loading/empty`
- **`frontend/src/components/Controls.tsx`** — replaced Symbol/Exchange/AssetClass fields with `AssetResolverInput`; `selectedAsset: SelectedAsset | null` state; `canFetch` requires `!!selectedAsset`
- **`frontend/src/api/marketData.ts`** — `exchange?: string` (optional); only included in URL when truthy
- **Tests**: `test_market_data_api.py` (+7: search happy path, empty results, short query 400, multiple results, yfinance error, omitted exchange defaults to unknown, default asset class); `AssetResolverInput.test.tsx` (12 new tests)

**Phase UX-5 — Evidence Readiness Panels — COMPLETE**
(backend: 4 710 ✓ unchanged | frontend: 418 ✓ | `npm run build` ✓)
- **`frontend/src/components/EvidenceReadinessPanel.tsx`** (already existed from prior session) — display-only shared component; `EvidenceItem { label, complete, explanation }`; testids: `erp-panel`, `erp-title`, `erp-item` (with `data-complete`), `erp-ready`, `erp-blocked`, `erp-empty`; no lifecycle decisions made inside component
- **`frontend/src/components/BacktestReportPage.tsx`** — `btEvidenceItems` computed for `lifecycleAtRun ∈ {draft, validated}`; `bt-evidence-panel` wrapper div; 3 evidence items: Strategy Draft Exists (always true), Draft Validated (`lifecycleAtRun !== 'draft'`), Backtest Completed (`run.status === 'completed'`); panel hidden for `backtested+` lifecycle
- **`frontend/src/components/ForwardTestPanel.tsx`** — `ft-evidence-panel` wrapper added inside `ft-promotion-panel`; 2 evidence items: Forward-Test Session Exists (always true when panel shows), Live Bars Evaluated After Warmup (`signal_eligible_bars_processed > 0`); panel only rendered when `lifecycle_status_at_activation === 'backtested'`
- **`frontend/src/components/PaperTradingPanel.tsx`** — `pt-evidence-panel` wrapper added inside `pt-promote-panel`; 3 evidence items: Market Data Processed (`last_processed_bar_timestamp !== null`), Session Finalized (`status ∈ {terminated, completed}`), Equity Snapshot Recorded (`equityCurve.length > 0`); panel only rendered when `lifecycle_status_at_activation === 'forward_tested'`
- **`frontend/src/components/StrategyLifecycleDashboard.tsx`** — `evidenceReadinessItems` IIFE derivation (stage-specific for validated/backtested/forward_tested); `EvidenceReadinessPanel` inserted between evidence summaries and quick navigation when items non-empty
- **Tests**: `EvidenceReadinessPanel.test.tsx` (14 unit tests); `BacktestReportPage.test.tsx` (+5 BT evidence tests); `ForwardTestPanel.test.tsx` (+4 FT evidence tests); `PaperTradingPanel.test.tsx` (+4 PT evidence tests); `StrategyLifecycleDashboard.test.tsx` (+4 LCD readiness tests); total 35 new tests
- **No backend changes**: backend enum values unchanged; API contracts unchanged; backend remains lifecycle authority

**Phase UX-4 — Terminology & Copy Cleanup — COMPLETE**
(backend: 4 710 ✓ unchanged | frontend: 383 ✓ | `npm run build` ✓)
- **`frontend/src/lib/lifecycleGuidance.ts`** — `STAGE_LABELS` updated: `backtested→'Backtest Complete'`, `forward_tested→'Forward Test Complete'`, `paper_tested→'Paper Trading Evidence Complete'`, `approved_for_live→'Approved for Live Review'`; `computeGuidance` action text updated consistently (`'Promote to Backtest Complete'`, `'Promote to Forward Test Complete'`, `'Promote to Paper Trading Evidence Complete'`); `whyItMatters` references updated to match
- **`frontend/src/App.tsx`** — nav labels updated: `Composer→Strategy Builder`, `History→Backtest History`, `Forward Test→Forward Testing`, `Lifecycle→Lifecycle Dashboard`
- **`frontend/src/components/LifecycleBadge.tsx`** — `STATUS_META` labels updated to match STAGE_LABELS; `next` hint strings updated for new terminology (e.g. `'Backtest Complete'`, `'Strategy Builder'`, `'Forward Testing session'`)
- **`frontend/src/components/StrategyLifecycleDashboard.tsx`** — `STAGE_LABELS` now imported from `lifecycleGuidance`; `LIFECYCLE_STAGES` labels derived from `STAGE_LABELS` instead of hardcoded strings
- **`frontend/src/components/ForwardTestPanel.tsx`** — `STAGE_LABELS` added to import; `'Run Cycle'→'Process Next Bar'` button text; `Provider→Market Data Source` (form + config panel); `Lifecycle at Activation→Strategy Stage at Start` with value mapped through `STAGE_LABELS`; `Signal-Eligible Bars→Live Bars Evaluated After Warmup`; `Lifecycle Promotion→Advance Stage` heading; `forward_tested` raw enum replaced with `'Forward Test Complete'` in promotion success + body text
- **`frontend/src/components/PaperTradingPanel.tsx`** — `STAGE_LABELS` added to import; `'Run Cycle'→'Process Next Bar'`; `Lifecycle Promotion→Advance Stage` heading; `paper_tested` raw enum replaced with `'Paper Trading Evidence Complete'` in success text; `'Promote to paper_tested'→'Advance to Paper Trading Evidence Complete'` button text; `Provider→Market Data Source`; `Lifecycle at Activation→Strategy Stage at Start` with value mapped through STAGE_LABELS; `'forward_tested'` in no-eligible-drafts notice replaced with user-facing label
- **`frontend/src/components/BacktestHistoryPanel.tsx`** — imports `STAGE_LABELS`; `lifecycle_status_at_run` badge display mapped through `STAGE_LABELS` (with raw fallback)
- **Tests updated**: `LifecycleGuidanceCard.test.tsx` — all `computeGuidance` label assertions updated (`'Backtest Complete'`, `'Forward Test Complete'`, `'Paper Trading Evidence Complete'`, `'Approved for Live Review'`, and promote action text); `StrategyLifecycleDashboard.test.tsx` — 3 assertions updated (`'Forward Test Complete'`, `'Promote to Paper Trading Evidence Complete'`, `'Promote to Backtest Complete'`); `ForwardTestPanel.test.tsx` — `'Run Cycle'→'Process Next Bar'` in 2 test assertions
- **No backend changes**: backend enum values (`backtested`, `forward_tested`, etc.) unchanged; all API contracts unchanged; backend remains lifecycle authority

**Phase UX-3 — Guided Next-Step Layer — COMPLETE**
(backend: 4 710 ✓ unchanged | frontend: 383 ✓ | `npm run build` ✓)
- **`frontend/src/lib/lifecycleGuidance.ts`** (new) — shared guidance computation module; single source of truth for lifecycle stage display, next recommended action, why it matters, blockers, and navigation target; exports `GuidanceContext`, `GuidanceResult`, `NavigateTarget`, `STAGE_LABELS`, `computeGuidance`; all evidence flags optional-boolean with false defaults; navigation target is a string enum (`'composer' | 'history' | 'forward-test' | 'paper-trading'`), never a callback — each panel maps to its own nav
- **`frontend/src/components/LifecycleGuidanceCard.tsx`** (new) — display-only reusable guidance card; answers "Where am I? What should I do next? Why does it matter? What is blocking me?" for any lifecycle screen; props: `currentStageLabel`, `nextAction`, `whyItMatters`, `blockers?`, `onNavigate?`, `navigateLabel?`, `navigateLocked?`; testids: `lgc-card`, `lgc-current-stage`, `lgc-next-action`, `lgc-why`, `lgc-blockers`, `lgc-blocker-item`, `lgc-no-blockers`, `lgc-navigate-btn`, `lgc-navigate-locked`; no lifecycle decisions made inside component
- **`frontend/src/components/StrategyLifecycleDashboard.tsx`** (modified) — refactored to use shared `computeGuidance` + `resolveNav`; removed local `computeNextAction` / `computeBlockers`; added `resolveNav(target, nav)` helper to map `NavigateTarget` to actual callback props; all LCD testids preserved; existing 34 tests updated (one assertion text updated: `'Validate in Composer'` → `'Validate Strategy Setup'`)
- **`frontend/src/components/DraftWorkspace.tsx`** (modified) — `LifecycleGuidanceCard` inserted above `DraftDetailView` when a draft is selected; `computeGuidance({ lifecycleStatus: selectedDraft.lifecycle_status ?? 'draft' })` — no evidence data (conservative guidance); no navigate button (already in Composer)
- **`frontend/src/components/BacktestReportPage.tsx`** (modified) — `LifecycleGuidanceCard` inserted before metrics grid when run is completed and `lifecycleAtRun` is known; `computeGuidance({ lifecycleStatus: lifecycleAtRun })`; navigate button wired to `onNavigateToComposer` when `navigateTarget === 'composer'`
- **`frontend/src/components/ForwardTestPanel.tsx`** (modified) — `LifecycleGuidanceCard` inserted in `SessionOperatorView` between `session-state-banner` and `config-panel`; `computeGuidance({ lifecycleStatus: session.lifecycle_status_at_activation, hasFtSession: true, hasFtEvidenceBars: session.signal_eligible_bars_processed > 0 })`
- **`frontend/src/components/PaperTradingPanel.tsx`** (modified) — `LifecycleGuidanceCard` inserted in `SessionDetailView` after action feedback and before P7 promotion panel; `computeGuidance({ lifecycleStatus: detail.lifecycle_status_at_activation, hasPtSession: true, ptIsFinalized, ptHasBarEvidence })`
- **`frontend/src/components/__tests__/LifecycleGuidanceCard.test.tsx`** (new) — 29 tests: card render, all testids, blockers/no-blockers, navigate button and click, navigateLocked state, navigateLabel override, `computeGuidance` for all 8 lifecycle statuses (draft/validated×2/backtested×3/forward_tested×4/paper_tested/approved_for_live/archived/unknown)
- **No lifecycle authority moved to frontend** — backend remains authoritative for all promotion decisions; guidance cards are display-only

**Phase UX-2 — Strategy Lifecycle Dashboard — COMPLETE**
(backend: 4 710 ✓ unchanged | frontend: 354 ✓ | `npm run build` ✓)
- **`frontend/src/components/StrategyLifecycleDashboard.tsx`** (new) — central command center for strategy lifecycle progression; key features:
  - Draft picker (`lcd-draft-select`) with auto-select on load; `lcd-no-drafts` empty state
  - Lifecycle stage track — 6 stage nodes (`lcd-stage-{key}`) each with `data-state=complete|current|locked`
  - Current stage card (`lcd-current-stage`) — human-readable label for active stage
  - Next-action card (`lcd-next-action`) — shows `lcd-next-action-btn` (deep-link to relevant tab) or `lcd-next-action-locked` when prerequisites unmet
  - Blockers section (`lcd-blockers`, `lcd-blocker-item`, `lcd-no-blockers`) — lists missing evidence gates
  - Evidence summaries: `lcd-evidence-backtest`, `lcd-evidence-ft`, `lcd-evidence-pt` (with `*-empty` variants when no records)
  - Quick navigation: `lcd-nav-composer`, `lcd-nav-history`, `lcd-nav-forward-test`, `lcd-nav-paper-trading`
  - Collapsible technical details (`lcd-tech-toggle`, `lcd-tech-details`) — draft ID, lifecycle enum, session IDs
  - All data from existing list APIs; `draft_id` filtering client-side (direct field for BT runs; `strategy_snapshot.draft_id` for FT/PT sessions)
  - Lifecycle authority stays backend-authoritative; frontend never decides promotion eligibility
- **`frontend/src/App.tsx`** (modified) — added `StrategyLifecycleDashboard` import; `'lifecycle'` added to `ActiveView` union; "Lifecycle" nav tab; render block wired with `onNavigate*` props
- **`frontend/src/components/__tests__/StrategyLifecycleDashboard.test.tsx`** (new) — 34 tests:
  - Loading/error states, draft picker render, auto-select first draft
  - Stage track: all 6 stages rendered, correct `data-state` for complete/current/locked
  - Next action: button shown for early stages, locked for approved/archived
  - Blockers: shown when missing evidence, none when complete
  - Evidence sections: BT/FT/PT counts, empty states
  - Navigation buttons: all 4 present and call correct prop
  - Technical details: toggle expand/collapse, shows draft ID and session IDs
  - Empty draft list: `lcd-no-drafts` shown
- **No lifecycle authority moved to frontend** — all promotion buttons link to the relevant operator panels (Paper Trading, Forward Test) which enforce backend gates

**Phase P8C — Paper Evidence Hardening — COMPLETE**
(backend: 4 710 ✓ | frontend: 320 ✓ | `npm run build` ✓)
- **`promote_draft_to_paper_tested()` evidence gate hardened** — 3 required gates now enforced (up from 1):
  1. `session.last_processed_bar_timestamp is not None` — at least one bar processed
  2. `session.status in {TERMINATED, COMPLETED}` — session must be in a finalized terminal state; FAILED excluded
  3. `snapshot_store.count(session_id) >= 1` — at least one equity snapshot recorded
- **`snapshot_store: AccountStateSnapshotStore`** added as parameter to `promote_draft_to_paper_tested()` in `backend/api/services/draft_service.py`
- **Audit metadata enriched** — `GOV_PROMOTION_REQUESTED` event now includes `session_status`, `last_bar_timestamp`, and `equity_snapshot_count`
- **`promote_draft` route** in `backend/api/routes/paper_trading.py` — `snapshot_store` dependency injected via `get_account_state_snapshot_store`; route comment updated to reflect P8C gates
- **Backend tests** — 10 original P7 tests updated; 5 new P8C tests added (`TestPromoteDraftToPaperTested`): running session → 422, paused session → 422, failed session → 422, no snapshots → 422, completed session → 200; total 15 tests in class
- **Frontend promotion panel updated** — added `pt-promotion-not-finalized` state (shown when bar evidence exists but session not yet terminated/completed); promote button only shown when status is `terminated` or `completed`; evidence summary text mentions session finalization status
- **Frontend tests** — 4 P7 tests updated to use `status: 'terminated'`; 3 new P8C tests: running session shows not-finalized, paused session shows not-finalized, completed session shows promote button

**Phase P8B — Terminal Session Integrity — COMPLETE**
(backend: 4 710 ✓ | `npm run build` ✓)
- **`backend/paper_trading/terminal.py`** (new) — `apply_terminal_cleanup(session_id, account_id, owner_id, order_store, position_store, account_store, snapshot_store, now_utc)` function: (1) cancels all PENDING_FILL orders with `cancellation_reason="session_terminated"`, (2) closes all open positions at last-known mark price (no fill generated), (3) finalizes account — cash recovered from position market values, realized P&L accumulated, status→CLOSED, (4) appends final equity snapshot with `open_position_count=0`, `unrealized_pnl=0.0`. All steps individually idempotent. Architecture boundary enforced (no imports from strategy_runtime/execution/backtesting/api/data_providers).
- **`terminate_session` route** updated — injects `order_store`, `position_store`, `account_store`, `snapshot_store` as Depends(); calls `apply_terminal_cleanup()` before session status flip; cleanup happens atomically before the TERMINATED record is written
- **Unit tests** — `tests/unit/test_paper_trading_terminal.py` (new): 23 tests covering all 4 steps + idempotency (TestPendingOrderCancellation×5, TestOpenPositionClosure×5, TestAccountFinalization×7, TestFinalEquitySnapshot×5, TestIdempotency×1)
- **Route integration tests** — `TestTerminateTerminalCleanup` class added to `test_paper_trading_routes.py` (6 tests): pending orders cancelled, positions closed, account status CLOSED, equity snapshot written, graceful degradation when no account, session status terminated in response

**Phase P8A — Paper Trading Cleanup — COMPLETE**
(backend: 4 676 ✓ | frontend: 317 ✓ | `npm run build` ✓)
- **Promotion panel refresh fix**: `PaperTradingPanel` detail view now loads current draft lifecycle with session detail and only shows the paper-tested promotion panel when the current draft is still `forward_tested` (or immediately after a local success state). A refreshed already-`paper_tested` draft no longer shows a misleading "Promote to paper_tested" action.
- **Forward-test picker/schema fix**: `ForwardTestSessionSummaryResponse` and `ForwardTestSessionSummary` now include `signal_eligible_bars_processed`; `paper` create-form FT picker filters with typed `s.signal_eligible_bars_processed > 0`, so zero-evidence sessions are not selectable.
- **Paper API client tests**: `frontend/src/api/__tests__/paperTrading.test.ts` added for create/list/detail/account/run/pause/resume/terminate/orders/fills/positions/equity/promote/error/header behavior; PaperTradingPanel tests strengthened for zero-evidence FT filtering and already-paper-tested refresh state.
- **Cleanup**: removed unused `derive_warmup_bars_required` import from paper route; paper route/API client comments now include equity-curve and promote-draft endpoints; HANDOFF/TASKS/REPOSITORY_STATE refreshed.
- **No behavior expansion**: no paper execution changes, lifecycle rule changes, approved-for-live work, or live trading.

**Phase P7 — Paper-Tested Lifecycle Promotion — COMPLETE**
(backend: 4 676 ✓ | frontend: 309 ✓ | `npm run build` ✓)
- **`PromoteDraftToPaperTestedRequest`** schema added to `backend/api/schemas/paper_trading.py` — `draft_id`, `notes?: str | None`, `extra="forbid"`.
- **`PaperTestPromotionError`** exception class added to `backend/api/services/draft_service.py`.
- **`promote_draft_to_paper_tested(session_id, draft_id, pt_repository, draft_repository, owner_id, *, notes)`** added to `draft_service.py`: loads session (raises `PaperTradingSessionNotFoundError`), loads draft (raises `DraftNotFoundError`), checks `session.draft_id == draft_id` (raises `PaperTestPromotionError`), checks `draft.lifecycle_status == FORWARD_TESTED` (raises `PaperTestPromotionError`), checks `session.last_processed_bar_timestamp is not None` (raises `PaperTestPromotionError`), calls `validate_lifecycle_transition(FORWARD_TESTED, PAPER_TESTED)`, mutates/persists, emits `GOV_PROMOTION_REQUESTED` audit event.
- **`POST /paper-trading/sessions/{session_id}/promote-draft`** route added to `backend/api/routes/paper_trading.py`: UUID validation on both `session_id` and `draft_id`; maps `PaperTradingSessionNotFoundError`/`DraftNotFoundError` → 404, `PaperTestPromotionError`/`ValueError` → 422; returns `DraftResponse` (no `strategy_json`).
- **Backend tests**: 10 new tests in `TestPromoteDraftToPaperTested` class — happy path (200, `paper_tested`), no evidence (422), draft not found (404), wrong draft owner (404), draft not forward_tested (422), draft already paper_tested (422), session wrong owner (404), session/draft mismatch (422), notes stored, no strategy_json in response. `_make_pt_session` extended with optional `last_processed_bar_timestamp` param (default `None`).
- **`promoteDraftToPaperTested(sessionId, draftId, notes?)`** API client function added to `frontend/src/api/paperTrading.ts`; imports `StrategyDraftData` type from `types/drafts`.
- **Promotion panel** added to `SessionDetailView` in `frontend/src/components/PaperTradingPanel.tsx`: visible only when `detail.lifecycle_status_at_activation === 'forward_tested'`; shows `pt-promotion-no-evidence` when `last_processed_bar_timestamp === null`; shows `promote-to-paper-tested-btn` when evidence present; `pt-promotion-success` after successful promotion; `pt-promotion-error` on failure; button disabled while promoting.
- **Frontend tests**: 8 new P7 tests in `PaperTradingPanel — P7: paper-tested promotion panel` describe block — panel hidden for non-forward_tested activation, no-evidence state, promote button with evidence, API call args, success state, error state, disabled during promotion, panel shown for terminated session with evidence. `promoteDraftToPaperTested` added to vi.mock factory + imports + `mockPromote` const + `beforeEach` default.

**Phase P6 — Paper Trading Equity Curve & Performance Analytics — COMPLETE**
(backend: 4 666 ✓ unchanged | frontend: 301 ✓ | `npm run build` ✓)
- **`EquityCurveChart`** (`pt-equity-curve`): SVG polyline — equity line (green) + cash line (blue dashed); Y-scale covers both equity and cash; area fill below equity line; date range label; insufficient-data state (`pt-equity-curve-insufficient`, < 2 snapshots); error state (`pt-equity-curve-error`); no external charting dependency added.
- **`DrawdownSummary`** (`pt-drawdown-summary`): Current drawdown %, max session drawdown (derived from snapshots), peak equity, latest equity; color-coded thresholds (>15% red, >5% amber, otherwise gray); returns null when account is null.
- **`ReturnSummary`** (`pt-return-summary`): Initial (starting_cash), Latest (equity), Absolute Return, Return % (with + prefix for gains); color-coded; returns null when account is null.
- **`TradeOutcomeSummary`** (`pt-trade-outcome`): Total Orders, Filled, Rejected, Total Fills, Open/Closed Positions; `pt-no-completed-trades` shown when fills is empty.
- **Performance Analytics section** added to `SessionDetailView` above MetricsSummary: `EquityCurveChart` (full width) + 3 summary cards in flex row.
- **Tests**: 14 new P6 tests — 4 equity curve (renders, insufficient×2, error), 7 analytics cards (drawdown renders+value, return renders+%, trade outcome renders, no-completed-trades present/absent), 3 regression (P5 ledger, P4 run-cycle, P3 create form). Total: 301 frontend tests.
- **No backend changes**: all analytics derived from existing `getEquityCurve` + `getPaperTradingAccount` + `listPaperTradingOrders/Fills/Positions` responses. No new endpoints. No new dependencies. No lifecycle promotion. No live trading.

**Phase P5 — Paper Trading Metrics, Trade Ledger & Equity History — COMPLETE**
(backend: 4 666 ✓ unchanged | frontend: 287 ✓ | `npm run build` ✓)
- **`PaperEquitySnapshot`** type added to `frontend/src/types/paperTrading.ts`; `getEquityCurve(sessionId)` added to `frontend/src/api/paperTrading.ts`.
- **`MetricsSummary`** (`pt-metrics`): 10-cell grid — total orders, filled/rejected/cancelled counts, total fills, open positions, equity, cash, realized P&L, unrealized P&L (derived from orders/fills/positions/account; no backend round-trip).
- **Trade Ledger** (`pt-trade-ledger`): orders joined with fills by `order_id`; symbol filter (`pt-ledger-symbol-filter`), status filter (`pt-ledger-status-filter`), newest/oldest sort (`pt-ledger-sort`); per-row `pt-ledger-row-{order_id}`; `pt-ledger-empty` for empty-orders or no-match.
- **Equity History** (`pt-equity-history-table`): newest-first equity snapshots with bar timestamp, equity, cash, realized P&L, unrealized P&L, drawdown %, open position count; `pt-equity-history-empty` / `pt-equity-history-error`.
- **`SessionDetailView`** `load()` extended: now fetches 6 APIs in `Promise.allSettled` (adds `getEquityCurve`); `equityCurve` / `equityCurveError` state added.
- **Tests** (`frontend/src/components/__tests__/PaperTradingPanel.test.tsx`): 11 new P5 tests — `pt-metrics` renders, order counts, realized P&L in metrics; `pt-trade-ledger` renders, `pt-ledger-empty`, symbol filter no-match, status filter, fill price in row; `pt-equity-history-empty`, `pt-equity-history-table`, `pt-equity-history-error`; `getEquityCurve` mock added to vi.mock factory + beforeEach default. Total: 287 frontend tests.
- **P4 test fixes**: two tests (`account detail card` + `equity and drawdown fields`) updated to use `card.textContent` scoped assertions instead of `screen.getByText` — avoids duplicate-match failures introduced by `MetricsSummary` showing the same values.

**Phase P4 — Paper Trading Operator View — COMPLETE**
(backend: 4 601 ✓ unchanged | frontend: 276 ✓ | `npm run build` ✓)
- **Types** (`frontend/src/types/paperTrading.ts`): `PaperOrder`, `PaperFill`, `PaperPosition`, `PaperCycleResult` added — mirror backend `paper_trading.py` schemas; no `strategy_json`; no secrets; no `user_id`.
- **API client** (`frontend/src/api/paperTrading.ts`): 7 new functions — `listPaperTradingOrders`, `listPaperTradingFills`, `listPaperTradingPositions`, `runPaperTradingCycle`, `pausePaperTradingSession`, `resumePaperTradingSession`, `terminatePaperTradingSession`; all `authedFetch`; no `setInterval`.
- **Panel** (`frontend/src/components/PaperTradingPanel.tsx`): `SessionDetailView` completely rewritten — prop changed from `session: PaperTradingSessionSummary` to `sessionId: string`; loads 5 APIs in `Promise.allSettled` on mount; `AccountDetailCard` (`pt-account-detail`) with all 11 account fields; Orders/Fills/Positions tables with per-section empty/error states; action buttons shown conditionally by status (run-cycle for running/pending, pause for running, resume for paused, terminate for running/paused/pending); `pt-cycle-result` on run-cycle success; `pt-action-error` on failure; `pt-refresh-btn` for manual reload; `PaperTradingPanel` root: `selectedSession` replaced by `selectedSessionId: string | null`.
- **Tests** (`frontend/src/components/__tests__/PaperTradingPanel.test.tsx`): 8 new P4 tests — account detail renders, equity+drawdown fields, orders table, orders empty state, fills table, positions table, run-cycle API call + cycle result, action error; P3 account-summary test updated (`pt-account-summary` → `pt-account-detail`); total 276 frontend tests.
- **Invariants preserved**: no auto-polling; no analytics; no equity curves; no paper-tested promotion; no live trading; backend is authoritative; `user_id` always from JWT; no secrets in responses.

**Phase P3 — Paper Trading UX Foundation — COMPLETE**
(backend: 4 601 ✓ unchanged | frontend: 268 ✓ | `npm run build` ✓)
- **Types** (`frontend/src/types/paperTrading.ts`): `PaperTradingSessionStatus`, `PaperSimulationAssumptions`, `PaperStrategySnapshot`, `PaperTradingSessionSummary`, `PaperTradingSessionDetail`, `PaperAccount`, `CreatePaperTradingSessionRequest` — mirrors backend schemas; no `strategy_json`; no `user_id` in summary types.
- **API client** (`frontend/src/api/paperTrading.ts`): `createPaperTradingSession`, `listPaperTradingSessions`, `getPaperTradingSession`, `getPaperTradingAccount`; all use `authedFetch`; no `setInterval`; no auto-polling.
- **Panel** (`frontend/src/components/PaperTradingPanel.tsx`): `ELIGIBLE_PT_STATUSES = new Set(['forward_tested','paper_tested','approved_for_live'])` — mirrors backend gate exactly; `PaperTradingPanel` (root) → `SessionList` → `CreateForm` / `SessionDetailView`; draft picker filtered to eligible statuses; optional FT session picker filtered by `strategy_snapshot.draft_id` match; lifecycle notice always visible in create form; no scheduler, no setInterval, no trade ledger, no positions, no orders, no fills, no performance analytics, no equity chart.
- **App.tsx**: `'paper-trading'` added to `ActiveView` union; `PaperTradingPanel` imported; "Paper Trading" `NavTab` added.
- **Tests**: 11 tests — panel renders, eligible draft picker, ineligible drafts excluded, FT session picker, create session API call, session list, account detail, empty states, lifecycle notice, list error banner.
- **Invariants preserved**: no `user_id` in types; no `strategy_json`; no `file_path`; `authedFetch` only; backend is lifecycle authority.

**Phase P2 — Paper-Trading API Hardening — COMPLETE**
(backend: 4 601 ✓ | frontend: unchanged 257 ✓ | no frontend build needed)
- **P2.2**: `_PT_ELIGIBLE_STATUSES` in `backend/api/routes/paper_trading.py` narrowed to `{FORWARD_TESTED, PAPER_TESTED, APPROVED_FOR_LIVE}`. `BACKTESTED` removed. Error message now reads: "Draft must be forward-tested before paper trading. Current lifecycle status is '{status}'; complete forward testing and promote the draft to 'forward_tested' first."
- **P2.1/P2.3/P2.4**: `forward_test_session_id` validation added to `create_session` route. When provided: UUID format check (400) → existence + ownership via `ForwardTestRepository.load(owner_id)` (404, information hiding) → `ft_session.draft_id == request.draft_id` linkage (422 "does not reference this draft") → `ft_session.signal_eligible_bars_processed >= 1` evidence (422). `get_forward_test_repository` DI dependency injected into route. `ForwardTestSessionNotFoundError` imported from `backend.forward_testing.exceptions`. `ForwardTestRepository` imported from `backend.forward_testing.repository`.
- **P2.5**: Atomicity fix — account saved before session. If account save fails, 500 is raised and session write is never attempted → no orphan session. Previous order (session first, account second) left orphan sessions on account save failure. Audit event extended with `forward_test_session_id` field.
- **P2.6**: All error messages are actionable, permission-safe, and consistent with existing route patterns.
- **Tests added**: `TestCreateSessionP2` class (10 tests: ft_session_not_found_404, ft_session_wrong_owner_404, ft_session_draft_mismatch_422, ft_session_no_evidence_422, ft_session_valid_creates_session, ft_session_id_optional_none_still_creates, ft_session_id_stored_in_detail_response, atomicity_account_save_failure_no_orphan_session, lifecycle_error_message_mentions_forward_tested, cross_user_draft_returns_404_not_422) + `test_create_lifecycle_too_low_backtested` added to `TestCreateSession`. Total new: 11 backend tests. No frontend tests added (no frontend changes).
- **Fixtures updated**: `stores` and `client` fixtures extended with `ForwardTestRepository`; `_ft_repo()` helper added; `_make_ft_session()` builder added; `_make_draft` default lifecycle changed from `BACKTESTED` to `FORWARD_TESTED`.

**Phase P1 — Forward-Test Evidence Promotion — COMPLETE**
(backend: 4 590 ✓ | frontend: build ✓ | full Vitest 257 ✓)
- **Service**: `promote_draft_to_forward_tested()` added to `backend/api/services/draft_service.py`. Evidence rule: `signal_eligible_bars_processed > 0` (at least one live bar evaluated post-warmup, even if no signals generated). Checks session→draft binding, draft must be BACKTESTED, `validate_lifecycle_transition(BACKTESTED, FORWARD_TESTED)`, mutates + persists draft, emits `GOV_PROMOTION_REQUESTED` with `bars_evaluated`/`signals_recorded` in audit details. `ForwardTestPromotionError` exception class added.
- **Schema**: `PromoteDraftToForwardTestedRequest(BaseModel, extra="forbid")` with `draft_id: str` + `notes: str | None` added to `backend/api/schemas/forward_testing.py`.
- **Route**: `POST /forward-tests/{session_id}/promote-draft` added to `backend/api/routes/forward_testing.py`. UUID validation → service call → `ForwardTestSessionNotFoundError`→404, `DraftNotFoundError`→404, `ForwardTestPromotionError`→422, `ValueError`→422.
- **Frontend API**: `promoteDraftToForwardTested(sessionId, draftId, notes?) → Promise<StrategyDraftData>` added to `frontend/src/api/forwardTests.ts`.
- **Promotion panel** in `SessionOperatorView` (`ForwardTestPanel.tsx`): `ft-promotion-panel` shown when `lifecycle_status_at_activation === 'backtested'`; `ft-promotion-no-evidence` when 0 eligible bars; `promote-to-forward-tested-btn` when evidence present; `ft-promotion-success` on success; `ft-promotion-error` surfaces backend error; `ft-promotion-ineligible` when draft was already beyond backtested at activation. No paper-trading UI added.
- **Tests added**: 9 backend tests in `TestPromoteDraftToForwardTested` class (`test_forward_testing_routes.py`): happy path, 0-evidence reject, validated-not-backtested reject, already-forward-tested reject, cross-user 404, session/draft mismatch, PUT /drafts cannot set forward_tested, audit event with evidence metadata, notes passed through. 7 frontend tests in "ForwardTestPanel — forward-test promotion panel (Phase P1)" describe block.

**Phase P0 — Lifecycle Integrity Repair — COMPLETE**
(backend: 4 581 ✓ | frontend: build ✓ | full Vitest 250 ✓)
- **P0.1**: `validate_draft()` in `draft_composition_service.py` now promotes `DRAFT→VALIDATED` on valid toolset — persists to repository, emits `GOV_PROMOTION_REQUESTED` audit, returns `lifecycle_promoted=True` in `CompositionValidationResponse`. Drafts already VALIDATED or beyond are left unchanged. Failed validation never promotes.
- **P0.2**: `lifecycle_status` field removed from both `DraftCreateRequest` and `DraftUpdateRequest`. Both schemas have `extra="forbid"`, so any client passing `lifecycle_status` on create/update → HTTP 422 automatically. Dead lifecycle-bypass block removed from `update_draft()`. `create_draft()` now hardcodes `lifecycle_status=StrategyLifecycleStatus.DRAFT`. Stale test `test_draft_update_request_lifecycle_status_is_optional` updated to verify field is absent.
- **P0.3**: `BacktestReportPage` promotion panel condition changed from `!BACKTESTED_OR_BEYOND.has(lifecycleAtRun)` to `lifecycleAtRun === 'validated'` — eliminates bug where `'draft'` status incorrectly showed an active Promote button. Added `draft-prerequisite-notice` panel (shown when `lifecycleAtRun === 'draft'` + run completed) with guidance to validate the draft first.
- **P0.4**: `/forward-tests` and `/paper-trading` added to `frontend/vite.config.ts` proxy.
- **P0.5**: `agent/REPOSITORY_STATE.md` cleaned — removed references to deleted R8 files (`ToolPanel.tsx`, `ConfiguredToolList.tsx`, `ToolSetPanel.tsx`, `BacktestPanel.tsx`, etc.); vite proxy list updated; current phase updated.
- **Tests added**: 6 backend `TestValidateDraftLifecyclePromotion` tests; 5 backend `TestLifecycleIntegrity` API tests; 5 frontend `BacktestReportPage — draft prerequisite notice` tests.

**Phase R8 — Legacy Frontend Cleanup Audit — COMPLETE**
(frontend: build ✓ | full Vitest 245 ✓ | backend unchanged)
- Audited suspected legacy paths after R1–R7 lifecycle repair.
- Active flow confirmed: `App.tsx` uses `StrategyTestPanel` → `compositionRun` for chart overlays, `backtestRuns` for persisted backtests, `BacktestReportPage`/`BacktestHistoryPanel` for report/history, and `ForwardTestPanel` for forward-test workflow.
- Removed confidently dead files: `frontend/src/components/BacktestPanel.tsx`, `frontend/src/api/backtest.ts`, `frontend/src/types/backtest.ts`, `frontend/src/api/strategyRuns.ts`, `frontend/src/components/ToolPanel.tsx`, `frontend/src/components/ToolSetPanel.tsx`, `frontend/src/components/ConfiguredToolList.tsx`.
- Retained active files: `compositionRun.ts`, `backtestRuns.ts`, `StrategyTestPanel.tsx`, `BacktestReportPage.tsx`, `BacktestHistoryPanel.tsx`, `ForwardTestPanel.tsx`, `DraftWorkspace.tsx`.
- Type cleanup: chart overlay indicator typing now uses `types/toolVisualization.ts`; active `compositionRun` response typing was narrowed to that contract.
- Import checks clean for removed paths (`BacktestPanel`, old `api/backtest`, `strategyRuns`, old tool display panels); `backtestRuns` references remain expected and active.
- Behavior unchanged: no backend, lifecycle, forward-test behavior, paper-trading UI, or active app navigation changes.

**Phase R7 — Forward Test Operator View — COMPLETE**
(frontend: build ✓ | 245 tests | 20 new tests added; backend unchanged)
- `SignalList` component replaced by comprehensive `SessionOperatorView` in `ForwardTestPanel.tsx`.
- `SessionOperatorView` fetches `getForwardTestSession` + `listForwardTestSignals` + `listForwardTestBars` in parallel (`Promise.all`) on mount.
- **Panels rendered** (`data-testid` anchors): `config-panel` (draft name, symbol, timeframe, provider, exchange, asset class, lifecycle at activation, snapshot hash), `cycle-panel` (last bar processed, total bars evaluated, warmup progress N/M, signal-eligible bars, signals recorded), `provenance-panel` (full session ID, draft ID, snapshot hash, created timestamp), `signals-panel` (signal trace table with feature values), `bars-panel` (recent bars table, newest-first, capped at 50, WARMUP/SIGNAL type label), `failure-panel` (only when `failure_reason` present).
- **Session state messaging**: `data-testid="session-state-banner"` + `data-testid="session-state-message"` shows human-readable status for all 6 states.
- **No-signal explanations** (`data-testid="no-signal-explanation"`): actionable text derived from `ForwardTestSessionDetail` fields — pending → "No cycle has run yet"; paused → "Resume to continue"; failed → failure_reason; terminated → terminated; running+warmup → warmup progress N/M; running+eligible → "N eligible bars evaluated — no conditions met".
- **Signal trace** enhanced: adds `Features` column displaying `feature_values_at_signal` key:value pairs from backend; `—` when empty.
- **Recent bars table**: shows `bar_index`, timestamp, OHLCV, bar type (WARMUP/SIGNAL); most recent 50 bars shown newest-first.
- Internal state renamed `signalView` → `detailView` (no external API change).
- Existing "signal view" tests updated: test 13 description and assertion updated from "No signals recorded yet" to actionable pending-state message.
- New `makeSessionDetail()`, `makeBar()`, `makeSignal()` fixtures added to test file; `mockGetSession`, `mockListBars` added with safe `beforeEach` defaults.
- Tests: 20 new tests in "ForwardTestPanel — operator view (Phase R7)": config panel, config values, cycle metrics, warmup progress, signals count, provenance, state banner, 6 no-signal explanation variants, signal trace with features, bars table, empty bars message, failure panel.
- No backend changes required — all data available via existing endpoints.
- Files: `frontend/src/components/ForwardTestPanel.tsx`, `frontend/src/components/__tests__/ForwardTestPanel.test.tsx`.

**Phase R6 — Forward Test Form Upgrade — COMPLETE**
(frontend: build ✓ | 225 tests | 9 new tests added in `ForwardTestPanel.test.tsx`; backend unchanged)
- `CreateForm` in `ForwardTestPanel.tsx` upgraded: credential picker (`ft-credential-select`) replaces raw UUID text input; draft field is now context-aware — read-only display (`ft-draft-display`) in prefill mode, `<select>` picker (`ft-draft-select`) when eligible drafts available, raw UUID input as fallback.
- New state: `credentials: CredentialMetadata[]`, `eligibleDrafts: StrategyDraftData[]`, `loadingMeta: boolean` — loaded on form mount via `fetchCredentials()` + `fetchDrafts()` (drafts skipped when prefill already sets draft_id); failures silently degrade to raw inputs.
- `filteredCredentials`: credentials filtered case-insensitively by current `providerName` field value; `no-credentials-notice` (`data-testid="no-credentials-notice"`) shown when filtered list is empty.
- `ELIGIBLE_FT_STATUSES`: `new Set(['backtested', 'forward_tested', 'paper_tested', 'approved_for_live'])` — only these lifecycle statuses appear in draft select.
- New styles: `select`, `draftDisplay`, `draftName`, `draftUuid`, `noCredNotice`, `metaLoading`.
- Tests: `vi.mock('../../api/credentials')` + `vi.mock('../../api/drafts')` added; `beforeEach` defaults both to empty lists (safe degradation); 9 new tests in describe block "ForwardTestPanel — credential and draft pickers (Phase R6)".
- R5 backward compatibility preserved: prefill mode shows hidden `<input type="hidden" data-testid="ft-draft-id-input">` so existing R5 tests (`prefills draft_id field from prefill prop`) still pass.
- Constraints respected: no backend changes, no auto-create, no auto-promote, no new dependencies, no live-trading.
- Files: `frontend/src/components/ForwardTestPanel.tsx`, `frontend/src/components/__tests__/ForwardTestPanel.test.tsx`.

**Phase R5 — Backtest → Forward Test Transition UI — COMPLETE**
(frontend: build ✓ | 216 tests | 13 new tests added: 5 BacktestReportPage + 8 ForwardTestPanel; backend unchanged)
- `ForwardTestPrefill` type added to `frontend/src/types/forwardTesting.ts` — `{ draft_id, draft_name?, symbol?, timeframe?, provider_name?, exchange?, asset_class? }`.
- `BacktestReportPage`: `onStartForwardTest?: (prefill) => void` prop added; `forward-test-hint-btn` now enabled (not disabled) when prop provided; `buildPrefillFromRun()` extracts draft_id/name/symbol/timeframe/provider_name from `BacktestRunSummary`; `start-forward-test-btn` added to promotion-success section (visible when `onStartForwardTest` + promotion succeeded).
- `ForwardTestPanel`: accepts `prefill?` + `onPrefillConsumed?` props (both optional — no breaking change); `showCreate` initialized from `prefill != null`; `useEffect` opens form if prefill set while panel already mounted; `CreateForm` accepts `initialValues?` — pre-populates all fields from prefill; `data-testid="ft-draft-id-input"` + `"ft-symbol-input"` + `"prefill-notice"` + `"ft-create-form"` added; `onPrefillConsumed?.()` called on cancel or successful session creation; `prefillNotice` style added.
- `App.tsx`: `forwardTestPrefill` state; `handleStartForwardTest(prefill)` → set prefill + navigate to forward-test; `handlePrefillConsumed()` → clear prefill; both wired to `ForwardTestPanel` and `BacktestReportPage`.
- Stale prefill not restored: `forwardTestPrefill` is never written to `useSessionPersistence`; cleared after cancel/create via `onPrefillConsumed`.
- Constraints respected: no auto-session creation, backend lifecycle gate unaffected, no paper-trading, no new dependencies.
- Files: `frontend/src/types/forwardTesting.ts`, `frontend/src/components/BacktestReportPage.tsx`, `frontend/src/components/ForwardTestPanel.tsx`, `frontend/src/App.tsx`, two test files updated.

**Phase R4 — UI Lifecycle Visibility — COMPLETE**
(frontend: build ✓ | 203 tests | 19 new tests added: 7 API + 10 component + 2 DraftDetailView badge tests existing; backend unchanged)
- New component: `frontend/src/components/LifecycleBadge.tsx` — reusable status badge; `data-testid="lifecycle-badge"` + `data-status={status}`; 7 statuses with distinct colors; optional `showNextStep` next-action hint below badge.
- Type extension: `lifecycle_status?: string` added to `StrategyDraftData` in `frontend/src/types/drafts.ts` (optional, backward-compatible).
- New API client: `promoteDraftToBacktested(runId, draftId, notes?)` in `frontend/src/api/backtestRuns.ts`; calls `POST /backtests/runs/{runId}/promote-draft`; throws descriptive `Error` on non-2xx using backend `detail` field.
- `DraftDetailView`: `LifecycleBadge` shown in header row with `showNextStep` prop.
- `BacktestReportPage`: Run Provenance section shows `LifecycleBadge` for `draft_provenance.lifecycle_status_at_run`; conditional promotion panel rendered when `status === "completed"` AND `lifecycle_status_at_run === "validated"` AND `onPromoteDraft` prop present; `already-eligible-notice` + `forward-test-hint-btn` (disabled) shown when draft was `backtested` or beyond; promotion state machine: `idle → promoting → success/error`; after success panel replaced by `promotion-success` message; error shown inline with retry allowed.
- `App.tsx`: `handlePromoteDraft(runId, draftId)` wires `promoteDraftToBacktested`; passed as `onPromoteDraft` prop to `BacktestReportPage`.
- Tests: `frontend/src/api/__tests__/backtestRuns.test.ts` (7 tests), `frontend/src/components/__tests__/BacktestReportPage.test.tsx` (10 tests).
- Lifecycle authority unchanged: frontend calls backend endpoint; frontend never decides lifecycle validity unilaterally.
- Forbidden respected: no forward-test session creation, no auto-promotion, no bypass of backend endpoint, no unrelated UI refactors.

**Phase R3 — Backend Lifecycle Promotion Repair — COMPLETE**
(backend: 17 tests added; 4 635 total; no frontend changes)
- Audit finding: `PATCH /drafts/{id}` accepted `lifecycle_status` changes without backtest evidence; a user could self-promote to `backtested` without any run.
- Fix: `promote_draft_to_backtested(draft_id, run_id, repository, storage, owner_id, *, notes)` added to `backend/api/services/draft_service.py`; validates draft ownership, loads backtest report (validates run ownership, `run.draft_id == draft_id`, `run.status == "completed"`), calls `validate_lifecycle_transition(current, BACKTESTED)`, persists update, emits `GOV_PROMOTION_REQUESTED`.
- New route: `POST /backtests/runs/{run_id}/promote-draft` (thin route → service; `PromoteDraftRequest` schema: `draft_id` + optional `notes`; returns `DraftResponse`).
- `LifecyclePromotionError` maps to 422; `DraftNotFoundError`/`BacktestAccessDeniedError`/`BacktestRunError` map to 404; invalid `run_id` format → 400.
- `PATCH /drafts/{id}` still exists but does NOT gate on backtest evidence; the new route is the only evidence-gated promotion path.
- Forward-test lifecycle gate unmodified: VALIDATED→FORWARD_TESTED still forbidden (test explicitly asserts this).
- Files: `backend/api/services/draft_service.py` (service + exception), `backend/api/schemas/backtest_runs.py` (`PromoteDraftRequest`), `backend/api/routes/backtest_runs.py` (route + imports), `tests/unit/test_lifecycle_promotion.py` (17 tests: 9 service + 8 route).

**Phase R2 — Composer Tool Selection Repair — COMPLETE**
(frontend: build ✓ | focused DraftWorkspace regression 1 ✓ | full Vitest 184 ✓ | relevant backend 79 ✓)
- Root cause: New Draft UI accepted friendly IDs such as `test1`, but draft path routes now require UUIDs. After create, `DraftWorkspace` immediately loaded `/drafts/{id}` with the friendly ID, received 400, and never mounted the Toolset/Add Tool selector.
- Confirmed tool registry/API were not the failing layer: registered tools returned `atr`, `bollinger_bands`, `ema`, `macd`, `rsi`, `sma`.
- Fix: `DraftWorkspace` now preserves valid UUID inputs and generates a UUID-backed draft/toolset ID for non-UUID composer creation inputs before create/select.
- Regression: `DraftWorkspace.test.tsx` verifies a `test1` input creates a path-safe draft, loads it by UUID, and exposes the registered SMA option in Add Tool.
- Behavior unchanged outside new composer creation: no backend, public API contract, auth/subscription, execution, or paper-trading internals changed.

**Phase R1 — Frontend Production Build Repair — COMPLETE**
(frontend: build ✓ | focused forward-test tests 28 ✓ | full Vitest 183 ✓)
- Root cause: production `tsc` compiled `src/**/*.test.*` files because `frontend/tsconfig.json` included all of `src`.
- Fix: production TypeScript excludes test/spec fixtures; `npm test` runs the existing Vitest runner; forward-test/auth test fixtures now match current types without broad `any` or test deletion.
- Files touched: `frontend/tsconfig.json`, `frontend/package.json`, `frontend/src/api/__tests__/forwardTests.test.ts`, `frontend/src/components/__tests__/ForwardTestPanel.test.tsx`, `agent/HANDOFF.md`, `agent/TASKS.md`, `agent/REPOSITORY_STATE.md`.
- Behavior unchanged: no backend, API contract, auth/subscription, lifecycle, routing, or paper-trading internals changed.

**Phase 4E.1 — Paper Trading Foundation — COMPLETE**
(backend: 4 329 tests | 141 new tests added; superseded by Phase 4E.2)
- `backend/paper_trading/__init__.py` — package established; architecture boundary comment; storage layout documentation
- `backend/paper_trading/exceptions.py` — 6 typed exceptions: `PaperTradingSessionNotFoundError` (wrong-owner = not-found), `PaperTradingSessionAlreadyExistsError`, `PaperTradingPersistenceError`, `PaperTradingInvalidTransitionError`, `PaperAccountNotFoundError`, `PaperAccountAlreadyExistsError`
- `backend/paper_trading/models.py` — `PaperTradingSessionStatus` 6-state enum + transition table + `validate_pt_session_transition()` + `is_pt_terminal_status()`; `FillTimingModel` / `FeeMode` / `SlippageMode` / `PositionSizeMode` enums; `SimulationAssumptions` (frozen, 11 fields, declared execution mechanics incl. starting_cash, currency, fee/slippage/sizing, drawdown stop, short-selling); `PaperStrategySnapshot` (frozen, independent from `forward_testing`, sealed at session creation); `PaperTradingSession` (frozen, source_mode consistency + snapshot_hash consistency validators, UUID field guards, UTC enforcement, lifecycle_status validator with lazy FT import); `PaperAccount` (frozen, 1:1 session binding, currency safe-string, balances non-negative, drawdown [0,100]); `AccountStateSnapshot` (frozen, append-only equity curve point)
- `backend/paper_trading/repository.py` — `PaperTradingRepository` (JSON-backed, ownership enforcement, wrong-owner → `PaperTradingSessionNotFoundError`, UUID path guard, `save`/`load`/`update`/`list_all`/`list_active`/`exists`)
- `backend/paper_trading/stores.py` — `PaperAccountStore` (1:1 enforcement on save, `save`/`load_by_session_id`/`update`/`exists_for_session`/`load_by_account_id`); `AccountStateSnapshotStore` (append-only, dedup by bar_timestamp, `append`→bool/`list_snapshots`/`count`)
- `backend/core/config.py` — `paper_trading_storage_path: Path = _REPO_ROOT / "storage" / "paper_trading"` added
- `backend/api/dependencies.py` — `get_paper_trading_repository()`, `get_paper_account_store()`, `get_account_state_snapshot_store()` added
- `backend/core/audit.py` — 30 `PT_*` audit event kinds added (10 session lifecycle + 2 activation gate + 3 order + 1 fill + 4 position + 3 account + 5 data + 2 access/governance)
- `tests/unit/test_security_baseline.py` — `test_all_event_kinds_defined` updated with all 30 PT_* values
- `tests/unit/test_paper_trading_models.py` — 55 tests (session status state machine + helpers, SimulationAssumptions validation, PaperStrategySnapshot, PaperTradingSession, PaperAccount, AccountStateSnapshot, frozen behavior)
- `tests/unit/test_paper_trading_repository.py` — 46 tests (save, load, update, list_all, list_active, exists; ownership isolation; UUID guard; wrong-owner info hiding)
- `tests/unit/test_paper_trading_stores.py` — 40 tests (PaperAccountStore: save/load/update/exists/load_by_account_id; AccountStateSnapshotStore: append/dedup/list/count; UUID guard)

**Phase 4E.2 — Paper Order, Fill, Position & Broker Adapter Foundation — COMPLETE**
(backend: 4 504 tests | 175 new tests added)
- `backend/paper_trading/exceptions.py` — 3 new exceptions: `PaperOrderNotFoundError`, `PaperPositionNotFoundError`, `PaperPositionAlreadyExistsError`
- `backend/paper_trading/execution_models.py` — 4 enums: `OrderDirection` (BUY/SELL), `PaperOrderStatus` (PENDING_FILL/FILLED/CANCELLED/REJECTED), `ExecutionReason` (SIGNAL_ENTRY/SIGNAL_EXIT/SESSION_END_CLOSE/DRAWDOWN_STOP_CLOSE), `RejectionReason` (INSUFFICIENT_CASH/MAX_POSITIONS_EXCEEDED/NO_POSITION_TO_CLOSE/SHORT_SELLING_DISABLED); 3 frozen models: `PaperOrder` (UUID guards for 4 ID fields + optional signal_id, UTC enforcement, symbol uppercase, quantity>0), `PaperFill` (gross_price/slippage/fill_price/gross_value/fee/net_value all ≥0, self-documenting fill record), `PaperPosition` (quantity≥0, is_open invariants: open→quantity>0+closed_at=None, closed→closed_at must be set)
- `backend/paper_trading/execution_stores.py` — `PaperOrderStore` (4 files per session: `pending.json` mutable, `filled/cancelled/rejected.json` append-only; `save_pending`, `load_pending` owner-filtered, `mark_filled` removes from pending + appends to filled + writes fill inline with dedup, `mark_cancelled`, `mark_rejected`, `list_filled/cancelled/rejected` owner-filtered; UUID guard on all paths); `PaperFillStore` (append-only, dedup by fill_id returns bool, `list_fills` with optional owner filter, `count`); `PaperPositionStore` (one file per position, `save` raises `PaperPositionAlreadyExistsError` on duplicate, `update` raises `PaperPositionNotFoundError` if missing, `load`, `list_positions` + `list_open_positions` with owner filter, `count_open`)
- `backend/paper_trading/broker_adapter.py` — `PaperBrokerAdapter` (all @staticmethod; `compute_fill_price(direction, gross_price, assumptions)` → (net_price, slippage) — adverse: BUY↑ SELL↓ floored at 0; NONE/FIXED/PERCENTAGE modes; `compute_fee(qty, gross_price, assumptions)` → float — NONE/FLAT/PERCENTAGE modes; `compute_quantity(assumptions, fill_price, equity)` → int — FIXED_QUANTITY/EQUITY_FRACTION/FIXED_CASH, returns 0 when result<1 or fill_price=0; `create_pending_order(...)` → PENDING_FILL order; `build_fill(order, gross_price, fill_bar_timestamp, assumptions, ...)` → (FILLED order, PaperFill); `reject_order(...)` → REJECTED order with `max(quantity, 1)` guard; no instance state, no store mutation, no account mutation)
- `backend/api/dependencies.py` — `get_paper_order_store()`, `get_paper_fill_store()`, `get_paper_position_store()` added
- `tests/unit/test_paper_trading_execution_models.py` — 57 tests (4 enums + PaperOrder + PaperFill + PaperPosition: UUID guards, UTC enforcement, symbol normalization, frozen behavior, model_copy transitions, open/closed invariants)
- `tests/unit/test_paper_trading_execution_stores.py` — 63 tests (PaperOrderStore: save/load/mark_filled/mark_cancelled/mark_rejected/list_*, owner isolation, append-only behavior; PaperFillStore: append/dedup/list/count/UUID guard; PaperPositionStore: save/update/load/list/list_open/count_open/session isolation)
- `tests/unit/test_paper_broker_adapter.py` — 55 tests (compute_fill_price all modes + adverse direction; compute_fee all modes; compute_quantity all modes + zero guards; create_pending_order; build_fill with/without slippage/fee; reject_order quantity guard; stateless invariant)
- Architecture boundary enforced: `backend/paper_trading/` imports nothing from strategy_runtime/execution/backtesting/api/data_providers
- NO PaperTradingService, NO account mutation, NO position update in service layer, NO API routes, NO frontend, NO scheduler

**Phase 4D — Paper Trading Architecture Review — COMPLETE**
(no code changes; architecture-only phase)
- `docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md` — 18 sections: purpose/scope, architecture docs reviewed, directly reusable components (10), missing components (18), account/order/fill/position/portfolio/session model recommendations, promotion lifecycle, audit taxonomy (29 PT_* events), storage assessment, workflow design (14 routes + UI), risks (6 risks + 2 open questions), implementation roadmap (4E.1–4E.6), readiness assessment, recommended next phase
- Architecture documents reviewed: `PAPER_TRADING_ARCHITECTURE.md`, `EXECUTION_CONTRACT.md`, `EXECUTION_AUDIT_MODEL.md`, `STRATEGY_PROMOTION_LIFECYCLE.md`, `FORWARD_TESTING_IMPLEMENTATION_REVIEW.md`
- Codebase surveyed: `backend/forward_testing/`, `backend/strategy_registry/`, `backend/execution/`, `backend/core/audit.py`, `backend/api/routes/forward_tests.py`
- Readiness rating: **A−** — all architecture documents complete; implementation complexity manageable; `next_bar_open` cross-bar state concern requires explicit design before Phase 4E.3; `PAPER_TESTED` enum presence requires pre-start verification

**Phase 4C.6 — Integration Validation — COMPLETE**
(backend: 4 188 tests | 65 new tests added)
- `tests/integration/__init__.py` — new integration test package
- `tests/integration/test_forward_testing_integration.py` — 65 tests across 10 sections (A: service E2E, B: signal idempotency, C: calendar gap detection, D: ownership isolation, E: lifecycle gate, F: entitlement gate, G: lifecycle transitions HTTP, H: audit event emission, I: API security invariants, J: full workflow HTTP)
- All 13 validation objectives PASSED: end-to-end workflow, ownership isolation, lifecycle gate, entitlement gate, warmup bar correctness, signal generation, signal idempotency, calendar gap detection, audit taxonomy, API security, UUID validation, terminal state guards, resume pre-check
- 4 test defects fixed: sessions missing `semantics=` in poll-path tests caused `_prepare_strategy()` early return; no production code defects
- Forward testing integration readiness rating: **B** — all Phase 4C objectives met; known limitations: log-only audit, JSON-backed storage, no holiday calendar, no FT_SESSION_COMPLETED route in Phase 4C scope

**Phase 4C.5 — Forward Testing API Routes + Frontend Panel — COMPLETE**
(backend: 4 123 tests | 37 new tests added | frontend: 183 tests | 28 new tests added)
- `backend/api/schemas/forward_testing.py` — 7 request/response schemas; no `strategy_json`, no `user_id` in list/summary responses; no `file_path`
- `backend/api/routes/forward_testing.py` — 9 routes under `/forward-tests`; all require `require_active_subscription`; `user_id` always from JWT; wrong-owner→404; session creation: lifecycle gate (>=backtested) + snapshot seal + SHA-256 hash + warmup derivation; run-cycle: catalog rejection (422) + vault credential resolution + provider build + `DatasetIdentity` + `ForwardTestService.run_cycle()`; resume pre-check (PAUSED only); pause/terminate; signals; bars
- `backend/api/dependencies.py` — `get_ohlcv_service()`, `get_tool_registry()`, `get_provider_factory()` added
- `backend/forward_testing/models.py` — `ForwardTestSession` extended: `credential_id`, `exchange="NASDAQ"`, `asset_class="equity"` (defaulted, backward-compatible)
- `tests/unit/test_forward_testing_routes.py` — 37 tests: create (7), list (5), get (3), run-cycle (4), pause (3), resume (3), terminate (4), signals (3), bars (3), auth (1)
- `frontend/src/types/forwardTesting.ts` — TypeScript types mirror backend schemas
- `frontend/src/api/forwardTests.ts` — 9 API functions; all use `authedFetch`; no `setInterval` auto-polling
- `frontend/src/components/ForwardTestPanel.tsx` — session list + status badges + contextual action buttons + create form + signal history drill-in
- `frontend/src/App.tsx` — "Forward Test" nav tab added; `ActiveView` type extended
- `frontend/src/api/__tests__/forwardTests.test.ts` — 13 API client tests
- `frontend/src/components/__tests__/ForwardTestPanel.test.tsx` — 15 component tests

**Phase 4C.4 — ForwardTestService Single-Cycle Evaluation Engine — COMPLETE**
(backend: 4 086 tests | 41 new tests added)
- `backend/forward_testing/service.py` — `CycleResult` frozen dataclass (13 fields); `ForwardTestService` with `run_cycle(session_id, owner_id, identity, provider, *, now_utc)`; `_activate()` (warmup bars via `get_recent_bars()`, `is_warmup_bar=True`, cursor = last warmup ts or `now_utc`, PENDING→RUNNING transition, `FT_SESSION_ACTIVATED`); `_poll_cycle()` (`get_bars_since(cursor)`, gap detection via `_calendar_is_bar_expected`, full-window recomputation via `compute_tool_outputs_for_history()`, `evaluate_history()`, idempotent bar/signal persistence, cursor advance, `FT_POLL_COMPLETED` / `FT_GAP_DETECTED` / `FT_SIGNAL_GENERATED` / `FT_SIGNAL_SUPPRESSED`); `_prepare_strategy()` (`StrategyDraft.model_validate_json` + `compile_semantics`); PAUSED/terminal → no-op; `RangeProviderAdapter` under `TYPE_CHECKING` guard only (boundary: `forward_testing` ≠ `data_providers`)
- `tests/unit/test_forward_test_service.py` — 41 tests: `TestActivation` (11), `TestPollCycle` (17), `TestStatusGuards` (6), `TestStrategyErrors` (2), `TestOwnership` (2), `TestSignalFields` (3)

**Phase 4C.3A — Exchange Calendar & Market Session Finalization Policy — COMPLETE**
(backend: 4 045 tests | 60 new tests added)
- `backend/market_calendar/base.py` — `TradingCalendar` ABC (UTC-only, `is_session_open`, `is_bar_expected`)
- `backend/market_calendar/calendars.py` — `TwentyFourSevenCalendar` (24/7, crypto); `WeekdayMarketCalendar` (Mon–Fri, equity); `DefaultCalendar` (conservative fallback = weekday)
- `backend/market_calendar/registry.py` — `get_calendar(asset_class, *, provider_name, exchange, symbol)` resolver; crypto→24/7; equity/stock/etf/fund→weekday; unknown→default; case-insensitive; reserved params for future exchange routing
- `backend/market_calendar/policy.py` — `is_bar_expected(bar_timestamp, timeframe, calendar) → bool`; `is_bar_finalized(bar_timestamp, timeframe, now_utc, calendar, safety_buffer=60) → bool` (wraps Phase 4C.3 time-check + calendar gate; Saturday equity bar always False)
- `backend/market_calendar/__init__.py` — public exports
- `tests/unit/test_market_calendar.py` — 60 tests (24/7 + weekday + default calendars, registry routing, is_bar_expected, is_bar_finalized, UTC enforcement, safety buffer, no-false-gap architectural rule)
- `docs/MARKET_CALENDAR.md` — minimal calendar architecture, limitations, UTC policy, future expansion path
- Key constraint: `is_bar_finalized` in policy.py returns False for unexpected bars regardless of time; ForwardTestService uses this to distinguish market closure from provider failure

**Phase 4C.3 — OHLCVService Extensions for Forward Testing — COMPLETE**
(backend: 3 985 tests | 44 new tests added)
- `backend/services/ohlcv_service.py` — `timeframe_to_timedelta()` (all 15 canonical TFs; "1M"=30d); `is_bar_finalized()` (UTC-aware, buffer_seconds=60, raises on naive dt); `OHLCVService.get_recent_bars()` (limit, reference_time, lookback_multiplier=2, BYPASS_CACHE); `OHLCVService.get_bars_since()` (strict `>` cursor, BYPASS_CACHE); no session coupling; no storage writes
- `backend/core/config.py` — `forward_test_bar_finalization_buffer_seconds = 60`
- `tests/unit/test_ohlcv_forward_test_extensions.py` — 44 tests (timeframe utilities, finalization logic, get_recent_bars, get_bars_since, UTC safety, BYPASS_CACHE verification)
- Key constraint: DataNormalizer enforces monotonic ascending timestamps; stub providers must return bars in ascending order

**Phase 4C.2 — Forward Testing Lifecycle & Audit Taxonomy Integration — COMPLETE**
(backend: 3 941 tests | 95 new tests added)
- `backend/strategy_registry/lifecycle.py` — `StrategyLifecycleStatus.FORWARD_TESTED` added; canonical path `backtested→forward_tested→paper_tested`; `backtested→paper_tested` retained (deprecated transitional); `forward_tested→backtested` rollback; invalid shortcuts rejected; docstring updated
- `backend/core/audit.py` — 19 FT_* event kinds added (FT_SESSION_CREATED through FT_SESSION_REVIEWED); 9 GOV_* event kinds added (GOV_PROMOTION_REQUESTED through GOV_LIFECYCLE_TRANSITION_DENIED); `AuditEvent.correlation_id: str | None = None` (optional, backward-compat); `emit_audit_event()` serializes correlation_id when present
- `tests/unit/test_strategy_lifecycle.py` — updated _VALID_TRANSITIONS + _INVALID_TRANSITIONS for forward_tested
- `tests/unit/test_security_baseline.py` — updated `test_all_event_kinds_defined` with all new FT_* + GOV_* values
- `tests/unit/test_forward_testing_lifecycle_audit.py` — new test file: lifecycle transitions, audit taxonomy, correlation_id, status vocabulary mapping

**Phase 4C.1 — Forward Testing Foundation — COMPLETE**
(backend: 3 846 tests | 125 new tests added)
- `backend/forward_testing/__init__.py` — package established
- `backend/forward_testing/exceptions.py` — `ForwardTestSessionNotFoundError`, `ForwardTestSessionAlreadyExistsError`, `ForwardTestPersistenceError`, `ForwardTestInvalidTransitionError`
- `backend/forward_testing/models.py` — `ForwardTestSessionStatus` (6-state enum + transition table + terminal detection), `StrategySnapshot`, `ForwardTestSession` (frozen, UUID guards, UTC enforcement, source_mode consistency), `ForwardTestSignal` (immutable, no fills/P&L), `ForwardTestBar` (warmup flag, bar_index)
- `backend/forward_testing/repository.py` — `ForwardTestRepository` (JSON-backed, ownership enforcement, UUID path guard, wrong-owner → same exception as not-found)
- `backend/forward_testing/stores.py` — `ForwardTestSignalStore` (idempotency: bar_timestamp + signal_direction), `ForwardTestBarStore` (idempotency: bar_timestamp; last-timestamp queries; warmup/signal-eligible counts)
- `backend/core/config.py` — `forward_test_sessions_storage_path` added
- `backend/api/dependencies.py` — `get_forward_test_repository()`, `get_forward_test_signal_store()`, `get_forward_test_bar_store()`
- `tests/unit/test_forward_test_models.py` — 51 tests
- `tests/unit/test_forward_test_repository.py` — 30 tests
- `tests/unit/test_forward_test_stores.py` — 29 tests (+ idempotency datetime fix: Pydantic `Z` vs `.isoformat()` `+00:00`)

**Phase 4B — Forward Testing Runtime Architecture Review & Implementation Planning — COMPLETE**
(`docs/FORWARD_TESTING_IMPLEMENTATION_REVIEW.md` created; no code changes; review and planning only)

**Phase 4A.5 — STRATEGY_PROMOTION_LIFECYCLE.md — COMPLETE**
(`docs/STRATEGY_PROMOTION_LIFECYCLE.md` established; no code changes; architecture-only)

**Phase 4A.4 — EXECUTION_AUDIT_MODEL.md — COMPLETE**
(`docs/EXECUTION_AUDIT_MODEL.md` established; no code changes; architecture-only)

**Phase 4A.3 — PAPER_TRADING_ARCHITECTURE.md — COMPLETE**
(`docs/PAPER_TRADING_ARCHITECTURE.md` established; no code changes; architecture-only)

**Phase 4A.2 — FORWARD_TESTING_ARCHITECTURE.md — COMPLETE**
(`docs/FORWARD_TESTING_ARCHITECTURE.md` established; no code changes; architecture-only)

**Phase 4A.1 — EXECUTION_CONTRACT.md — COMPLETE**
(`docs/EXECUTION_CONTRACT.md` established; no code changes; architecture-only)

**Phase 3S-D — Legacy Route Decommissioning & Path Safety Hardening — COMPLETE**
(backend: 3 721 tests | frontend: 155 tests | tsc clean)

**Phase 3S-C — Research Provenance & Workflow Continuity — COMPLETE**

**Phase 3S-B — Critical Security & Runtime Boundary Fixes — COMPLETE**

Completed phases: Chart-UX-3C, Chart-UX-3B.1, Chart-UX-3B, Chart-UX-3A.1, Chart-UX-3A, UX-4, UX-3, UX-2, P8C, P8B, P8A, P7, P6, P5, P4, P3, P2, P1, P0, R8, R7, R6, R5, R4, R3, R2, R1, 4E.4, 4E.3, 4E.2, 4E.1, 4D, 4C.6, 4C.5, 4C.4, 4C.3A, 4C.3, 4C.2, 4C.1, 4B, 4A.5, 4A.4, 4A.3, 4A.2, 4A.1, 3S-D, 3S-C, 3S-B, 3P-E, 3P-D, 3P-C, 3P-B.1, 3P-B, 3P-A.1, 3P-A, 3O, 3N, 3M.1, 3M, 3L, 3J, 3I, 3H, 3G, 3F, 3E, 3D, 3C, 3B, 3A, 2T–2U, 2N–2S, 2J–2M, 2D–2I, 2A–2C

---

# Immediate Active Roadmap

## Phase Chart-UX-3 — Chart Indicator Tool Implementation

**Implementation authority:** `docs/CHART_INDICATOR_TOOL_CONTRACT.md`

### Phase Chart-UX-3A — Contract and Architecture
**Status:** COMPLETE (architecture/doc phase; no code changes)
- `docs/CHART_INDICATOR_TOOL_CONTRACT.md` created; full contract for how tools become chart indicators

### Phase Chart-UX-3B — Backend Indicator Artifact Endpoint
**Status:** COMPLETE (54 tests; 4 816 backend total)
**Scope:** `IndicatorArtifactRequest` / `IndicatorArtifactResponse` schemas; `POST /chart/indicator-artifact` route; OHLCVService data resolution; `_TOOL_DISPATCHERS` dispatch; warmup null values; auth: `require_active_subscription`; backend unit tests

### Phase Chart-UX-3C — Frontend Indicator Panel and Parameter Editor
**Status:** COMPLETE (29 new tests; 466 frontend total)
**Scope:** Chart indicator picker (tool discovery from backend); parameter editor driven by tool metadata; indicator artifact fetch on add/change; overlay rendering for price-pane indicators; oscillator pane rendering; null gap handling; no in-browser computation; frontend tests

### Phase Chart-UX-3D — Onboard Existing Tools
**Status:** PENDING (depends on 3C)
**Scope:** Add `visible_on_chart: true` + full visualization metadata to sma/ema/rsi/macd/bollinger_bands/atr; Bollinger Bands 3-series overlay wiring; MACD 3-series oscillator wiring; backend computation consistency tests; frontend rendering tests

### Phase Chart-UX-3E — Custom Indicator Promotion Workflow
**Status:** PENDING (depends on 3D)
**Scope:** Promotion checklist UI; backend metadata validation (chart-visible = must have complete output_series); backend series_id ↔ strategy output reference consistency check; developer guide for adding new chart-visible tools

---

## Phase 4E — Paper Trading Implementation

**Status:** IN PROGRESS (4E.1, 4E.2, 4E.3, 4E.4 complete; R3 complete)

**Implementation authority:** `docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md`

### Phase 4E.1 — Foundation

**Status:** COMPLETE (141 tests added; 4 329 total)
- Package: `backend/paper_trading/` with exceptions, models, repository, stores
- Config: `paper_trading_storage_path`
- DI: 3 factory functions in `dependencies.py`
- Audit: 30 `PT_*` event kinds

### Phase 4E.2 — PaperBrokerAdapter + Fill Simulation

**Status:** COMPLETE (175 tests added; 4 504 total)
**Scope:**
- `PaperOrder`, `PaperFill`, `PaperPosition` models (frozen, UUID guards, UTC enforcement)
- `PaperBrokerAdapter.submit_order()` — fill simulation with fee/slippage/sizing per `SimulationAssumptions`
- Both fill timing modes: `SIGNAL_BAR_CLOSE` and `NEXT_BAR_OPEN`
- Drawdown stop trigger (compares `current_drawdown_pct` against `max_drawdown_stop_pct`)
- No service layer, no API routes, no frontend

**Requires resolution before start:**
- Design `next_bar_open` pending order persistence (cross-bar state between poll cycles) — must be explicit before 4E.3 service implementation

### Phase 4E.3 — PaperTradingService Execution Engine

**Status:** COMPLETE (69 tests added; 4 508 total)
- `backend/paper_trading/service.py` — `PaperCycleResult` frozen dataclass (21 fields); `PaperTradingService` (10-dependency DI); `run_cycle()` dispatches PENDING→`_activate()` / RUNNING→`_poll_cycle()` / PAUSED/terminal→no-op; `_activate()` derives warmup from toolset, stores warmup bars, PENDING→RUNNING; `_poll_cycle()` mandatory order: resolve pending orders at bar.open FIRST, then evaluate signal; entry/exit signal processing (long-only; SBC immediate fill / NBO pending order); `_apply_buy_fill` (open/scale; deduct cash); `_apply_sell_fill` (close/reduce; add cash; realize PnL); `_mark_to_market` (all open positions; equity + drawdown recalculation); drawdown stop check per bar; `AccountStateSnapshot` per signal-eligible bar; all PT_* audit events emitted; no routes, no frontend, no scheduler
- `tests/unit/test_paper_trading_service.py` — 69 tests: routing (terminal/paused/pending/running), activation, poll-cycle (no bars, 1 bar, snapshot, warmup flag), entry/exit signal unit tests, buy/sell fill unit tests, mark-to-market unit tests, resolve-pending-order unit tests, drawdown stop, module helpers (`_compute_drawdown`, `_get_triggered_rule_id`)

### Phase 4E.4 — API Routes + Schemas

**Status:** COMPLETE (45 tests added; 4 618 total → 4 635 after Phase R3)
- `backend/api/schemas/paper_trading.py` — `SimulationAssumptionsRequest/Response`, `CreatePaperTradingSessionRequest`, `PaperStrategySnapshotResponse`, `PaperTradingSessionSummaryResponse`/`DetailResponse` (no `strategy_json`, no `user_id`, no `file_path`), `PaperCycleResultResponse` (21 fields incl. `drawdown_stop_triggered`), `PaperOrderResponse`, `PaperFillResponse`, `PaperPositionResponse`, `PaperAccountResponse`, `AccountStateSnapshotResponse`, `PaperBarResponse`, `PaperSignalResponse`
- `backend/api/routes/paper_trading.py` — 14 routes under `/paper-trading/sessions`; all require `require_active_subscription`; `user_id` always from JWT; wrong-owner → 404; session creation: draft ownership + lifecycle gate (>= backtested) + snapshot seal + SHA-256 hash + `PaperAccount` created atomically + `PT_SESSION_CREATED` audit; run-cycle: catalog rejection (422) + vault credential resolution + provider build + `DatasetIdentity` + `PaperTradingService.run_cycle()` dispatch; lifecycle transitions validated via `validate_pt_session_transition()`; execution data endpoints: signals/orders/fills/positions/account/equity-curve/bars
- `backend/api/main.py` — `paper_trading.router` registered
- `tests/unit/test_paper_trading_routes.py` — 45 tests: create (8), list (4), detail (4), run-cycle (4), pause/resume/terminate (9), sub-resource endpoints (14), security (2)

### Phase 4E.5 — Frontend Panel

**Status:** COMPLETE (Phase P3/P4/P5; 287 frontend tests; frontend 287 ✓)
- `frontend/src/types/paperTrading.ts` — 8 types mirroring backend schemas (incl. `PaperEquitySnapshot`)
- `frontend/src/api/paperTrading.ts` — 12 API functions (incl. `getEquityCurve`); `authedFetch` only; no auto-polling
- `frontend/src/components/PaperTradingPanel.tsx` — full operator view: session list + create form + `MetricsSummary` + `AccountDetailCard` + Trade Ledger (with filters/sort) + Equity History table + Positions/Orders/Fills raw tables + action buttons; all `pt-*` testids
- `frontend/src/App.tsx` — `'paper-trading'` added to `ActiveView`, nav tab, render block

### Phase 4E.6 — Integration Validation

**Status:** PENDING
**Scope:** End-to-end test; ownership isolation; lifecycle gate; drawdown stop; account state progression; audit taxonomy

---

## Phase 4C — Forward Testing Runtime Implementation

**Status:** COMPLETE (all 6 sub-phases)

**Implementation authority:** `docs/FORWARD_TESTING_IMPLEMENTATION_REVIEW.md`

### Phase 4C.1 — Foundation

**Status:** COMPLETE (125 tests added; 3 846 total)

### Phase 4C.2 — Lifecycle and Audit Extension

**Status:** COMPLETE (95 tests added; 3 941 total)

### Phase 4C.3 — OHLCVService Extension

**Status:** COMPLETE (44 tests added; 3 985 total)

### Phase 4C.3A — Exchange Calendar & Market Session Finalization Policy

**Status:** COMPLETE (60 tests added; 4 045 total)

### Phase 4C.4 — ForwardTestService

**Status:** COMPLETE (41 tests added; 4 086 total)

### Phase 4C.5 — API Routes + Frontend

**Status:** COMPLETE (37 backend + 28 frontend tests added)

### Phase 4C.6 — Integration Validation

**Status:** COMPLETE (65 tests added; 4 188 total)  
**Scope:** End-to-end test (create → start → poll → signals); ownership isolation; update HANDOFF.md + TASKS.md

---

## Phase 2V — Custom Research Tools

**Status:** PENDING

**Objective:** First non-standard indicator — marks start of the QuantLab-specific research tool layer.

**Expected scope:** Swing high/low detector, or divergence signal, or custom feature computation tool. Must register in `_TOOL_DISPATCHERS`, expose `output_feature_names`, respect warmup/lookahead enforcement.

---

# Near-Term Roadmap

| Phase | Objective | Dependency |
|-------|-----------|------------|
| **Phase 4C.1 — FT Foundation** | ✓ COMPLETE — 125 tests; session model, repository, stores, settings path | 4B complete |
| **Phase 4C.2 — Lifecycle + Audit** | ✓ COMPLETE — 95 tests; forward_tested state, FT_/GOV_ events, correlation_id | 4C.1 complete |
| **Phase 4C.3 — OHLCVService** | ✓ COMPLETE — 44 tests; get_recent_bars, get_bars_since, bar finalization | 4C.1 complete |
| **Phase 4C.3A — Market Calendar** | ✓ COMPLETE — 60 tests; TradingCalendar, 24/7 + weekday calendars, registry, is_bar_expected, is_bar_finalized (calendar-aware) | 4C.3 complete |
| **Phase 4C.4 — ForwardTestService** | ✓ COMPLETE — 41 tests; single-cycle engine, PENDING activation, RUNNING poll, audit emission | 4C.2 + 4C.3 + 4C.3A complete |
| **Phase 4C.5 — Routes + Frontend** | ✓ COMPLETE — 9 routes, ForwardTestPanel, nav tab | 4C.4 complete |
| **Phase 4C.6 — Integration** | ✓ COMPLETE — 65 tests; all 13 objectives passed; readiness rating B | 4C.5 complete |
| **Phase 4D — Paper Trading Review** | ✓ COMPLETE — `docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md`; 18 sections; readiness rating A− | 4C.6 complete |
| **Phase 4E.1 — PT Foundation** | ✓ COMPLETE — 141 tests; package, models, repository, stores, config, DI, 30 PT_* audit events | 4D complete |
| **Phase 4E.2 — PT Broker Adapter** | PENDING — `PaperOrder`/`PaperFill`/`PaperPosition` models; `PaperBrokerAdapter`; fill simulation; drawdown stop | 4E.1 complete |
| **Phase 4E.3 — PT Service** | ✓ COMPLETE — 69 tests; `PaperTradingService.run_cycle()`; activation; poll-cycle; fill application; mark-to-market; drawdown stop; audit emission | 4E.2 complete |
| **Phase 4E.4 — PT Routes** | ✓ COMPLETE — 45 tests; 14 routes; schemas; router registered | 4E.3 complete |
| **Phase R3 — Lifecycle Promotion** | ✓ COMPLETE — 17 tests; `promote_draft_to_backtested()`; `POST /backtests/runs/{run_id}/promote-draft`; evidence gate; forward-test gate unmodified | 4E.4 complete |
| **Phase 4E.5 — PT Frontend** | ✓ COMPLETE (Phase P3) — `PaperTradingPanel.tsx`; session list + create form + account summary; 11 tests | 4E.4 complete |
| **Phase 4E.6 — PT Integration** | PENDING — end-to-end validation; ownership isolation; drawdown stop; audit taxonomy | 4E.5 complete |
| 2V — Custom Research Tools | Swing high/low or divergence indicator | None |
| Payment / Subscription | Webhook-driven approval, connect `approve_user` to payment provider | 3R complete |
| PostgreSQL migration | Replace JSON-backed repositories (User, Credential, Draft, Catalog) | Durability need |
| Bollinger Bands visualization | Wire 3-series band overlay to frontend chart (backend already complete) | None |
| Provider expansion | Binance, IBKR adapters in `ProviderAdapterFactory` | 3A architecture ready |

---

# Planned Future Phases

## Phase 4H — Intraday Engine Optimization

**Status:** PLANNED
**Dependency:** After Paper Trading maturity (Phase 4D+)

**Objective:** Enable production-grade 5-minute strategy support.

Required: ToolStateSnapshot architecture; incremental indicator computation; incremental evaluator execution; session pagination; provider polling optimization; long-running session validation.

**Outcome:** 5m forward testing; 5m paper trading

## Phase 5A — Realtime Streaming Architecture

**Status:** PLANNED
**Dependency:** After Phase 4H

**Objective:** Enable production-grade 1-minute strategy support.

Required: WebSocket ingestion layer; event-driven market data pipeline; reconnect/recovery logic; event deduplication; late-bar handling; persistent event storage; streaming audit integration.

**Outcome:** 1m forward testing; 1m paper trading; foundation for live execution

---

# Deferred / Long-Term Infrastructure

- **Live trading**: WebSocket streaming, tick-to-candle aggregation, broker execution, risk layer — **NOT current priority**
- **Distributed execution**: microservices, Celery/RQ workers, cloud orchestration — deferred until multi-strategy / live trading need
- **Per-candle gap detection**: `OHLCVService` currently uses coverage windows; intra-window gaps not detected
- **Instrument master database**: no centralized symbol/exchange registry; each provider resolves symbols independently
- **Alternative / astronomical datasets**: research layer deferred until core strategy loop is stable
- **Audit persistence**: `emit_audit_event()` is log-only; no DB or audit store yet
- **Credential rotation**: `EnvironmentCredentialResolver` reads env var statically per request; no rotation detection

---

# Architectural Constraints (non-negotiable)

| Constraint | Why |
|------------|-----|
| `user_id` always from JWT | No client-controlled ownership |
| Wrong-owner → HTTP 404 | Information hiding (same as not-found) |
| `require_admin_role` never depends on `require_active_subscription` | Admins must manage users even after own expiry |
| `file_path` never in any API response | Prevents filesystem path leakage |
| `encrypted_secret` never in any API response | Defense-in-depth on vault responses |
| `password_hash` never in any API response | Auth schema invariant |
| Strategies import nothing from api/provider/storage/frontend | Portability across all runtime modes |
| `resolve_secret()` internal to VaultService only | Route layer never handles raw secrets |
| Backtest results must be reproducible | Deterministic candle+config inputs required |

---

# Governance Foundation Status

All governance documents established:

| Document | Status |
|----------|--------|
| `ARCHITECTURE_GUARDRAILS.md` | ✓ complete |
| `WORKFLOW_GOVERNANCE.md` | ✓ complete |
| `WORKFLOW_AGENT.md` | ✓ complete |
| `PROMPT_RULES.md` | ✓ complete |
| `ARCHITECTURE.md` | ✓ complete |
| `docs/ADMIN_GOVERNANCE.md` | ✓ complete |
| `docs/OWNERSHIP_SCOPING.md` | ✓ complete |
| `docs/ADMIN_ENTITLEMENT_SEPARATION.md` | ✓ complete |
| `docs/SUBSCRIPTION_EXPIRY_ENFORCEMENT.md` | ✓ complete |
| `docs/BACKTESTING_ENGINE_CONTRACT.md` | ✓ complete |

Minor outstanding note: `directives/` folder not yet documented in `REPOSITORY_STRUCTURE.md` (non-blocking).

---

# Execution Domain Notes

**Orchestration domain** (human + ChatGPT): architecture decisions, governance, phase planning, scope definition.
**Implementation domain** (Claude, Codex): coding, module implementation, testing, documentation updates.

Implementation work originates from structured directives only. Do not invent scope.

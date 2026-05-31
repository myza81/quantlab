# HANDOFF_HISTORY.md — Phase Implementation Archive

This file is the permanent historical record of QuantLab implementation phases.

Active operational state lives in `agent/HANDOFF.md` and `agent/TASKS.md`.
Full implementation detail (diffs, test output) lives in git history.
This file preserves high-level phase summaries for reference without polluting active docs.

---

## Completed Phases (reverse chronological)

### Phase 3R — End-to-End Research Workflow UX
`ResearchSession` interface + `SourceMode` type (`types/researchSession.ts`). `SessionProvenanceStrip.tsx` — persistent strip below nav showing active source/symbol/timeframe/candle-count + latest draft name + "view last report" shortcut; renders nothing when no data loaded; no `file_path` ever. `StrategyTestPanel.tsx` — new `sessionContext?: ResearchSession` prop (data source context display), `onNavigateToComposer?: () => void` prop ("+ Composer" shortcut button), improved no-data hint. `BacktestReportPage.tsx` — new `sourceLabel?: string | null` prop (source provenance in header), `onNavigateToComposer?: () => void` prop ("Edit Strategy" button). `App.tsx` — derived `session` object + `sourceLabel`, `SessionProvenanceStrip` wired, "Report" nav tab appears once a backtest report exists, all new props threaded to StrategyTestPanel + BacktestReportPage. `ResearchSessionFlow.test.tsx` (19 tests). 155 frontend / 3523 backend tests.

### Phase 3Q — Operational Documentation Refactor
HANDOFF.md compressed from 4000 lines → 170 lines. TASKS.md compressed from ~1100 lines → 125 lines. `agent/archive/HANDOFF_HISTORY.md` created (all phase summaries + key architecture decisions). No code changes.

### Phase 3P-E — Dataset Catalog Integration UX
Frontend UX for user-owned local dataset catalog (Source Mode B). New files: `types/catalog.ts`, `api/catalog.ts`, `CatalogManager.tsx` (17 tests), `CatalogManager.test.tsx`. App.tsx wired: datasets view, `handleCatalogLoad`, `CatalogMetaBadge`, superadmin admin tab. `file_path` cleared after submit, never rendered. authedFetch throughout. 136 frontend / 3523 backend tests.

### Phase 3P-D — Superadmin & Admin Role Management
`UserRole.superadmin` tier added above admin. `require_superadmin_role` dep. `promote_to_admin` / `demote_to_user` routes (superadmin-only). 4 new AuditEventKind values. Guard 2 in `suspend_user` (admin cannot act on superadmin). Bootstrap now produces `role=superadmin`. Migration script: `backend/scripts/promote_superadmin.py`. `test_superadmin_governance.py` (33 tests). Frontend: types/api/AdminConsole/tests all updated. 119 frontend / 3523 backend.

### Phase 3P-C — Lazy Subscription Expiry Enforcement
Request-driven `active → expired` transition via `evaluate_subscription_expiry()`. No scheduler. `backend/auth/expiry.py`. `User.with_expired()`. `get_user_repository` public dep. `require_active_subscription` lazy-evaluates expiry on every protected request. Frontend: `SubscriptionExpiredError` + 403 detection + `refreshUser()` in AuthContext. 111 frontend / 3481 backend.

### Phase 3P-B.1 — Governance Safety & Subscription Expiry Refinement
`validate_future_expiry` module-level helper. `AdminSelfSuspensionError` + `LastAdminProtectionError`. `POST /admin/users/{id}/update-expiry`. AdminConsole.tsx rewrite: expiry inputs, self-badge, no delete, expiry-gated buttons. `test_admin_governance.py` (28 tests). `docs/ADMIN_GOVERNANCE.md`. 100 frontend / 3462 backend.

### Phase 3P-B — Admin Console Foundation
`frontend/src/types/admin.ts`, `api/admin.ts`, `AdminConsole.tsx`. Browser-based user lifecycle management (approve/suspend/reactivate). Admin NavTab hidden from non-admins. `AdminConsole.test.tsx` (10 tests). 92 frontend / 3434 backend.

### Phase 3P-A.1 — Admin Entitlement Separation Refinement
`User.has_platform_access` property: admin = role-based (always True), user = subscription-based. `require_active_subscription` calls `has_platform_access`. Bootstrap sets `role=admin` + `subscription_status=pending`. `SubscriptionGate` admin passthrough. `docs/ADMIN_ENTITLEMENT_SEPARATION.md`. `SubscriptionGate.test.tsx` (11 tests). 82 frontend / 3434 backend.

### Phase 3P-A — Subscription Eligibility & Admin Approval Foundation
`UserRole` + `SubscriptionStatus` enums. New registrations default to `subscription_status=pending`. Admin approval workflow. `require_active_subscription` + `require_admin_role` entitlement deps. `AdminService` + 5 admin routes. `admin_bootstrap_email` config. `SubscriptionGate.tsx`. 5 new AuditEventKind values. 71 frontend / 3415 backend.

### Phase 3O — Credential-Aware Market Data Workflow UX
`Controls.tsx` polygon provider + credential selector. `App.tsx` `DatasetMetaBadge` + `fetchMetadata` state. `fetchOHLCV` credential_id + authedFetch path. `marketDataCredential.test.ts` (12 tests). 60 frontend.

### Phase 3N — Frontend Provider Credential Management UI
`CredentialManager.tsx`. `types/credentials.ts`, `api/credentials.ts`. Secret cleared from state after API call. Credentials NavTab. `credentialClient.test.ts` (16 tests). 48 frontend.

### Phase 3M.1 — Browser-Level Authentication & Ownership Validation
4 bugs fixed: AuthGuard blank screen, `/catalog` missing from Vite proxy, composition/backtest run 422→404 for wrong-owner. `TestCompositionAndBacktestRunOwnership` added (3 tests). `docs/VALIDATION_3M1.md`. 53 ownership tests.

### Phase 3M — Frontend Ownership Integration
`AuthError` class + `isAuthError` + `authedFetch` throws on 401. All ownership-scoped clients migrated. `authClients.test.ts` (17 tests). 32 frontend.

### Phase 3L — User Ownership & Resource Scoping
Drafts, catalog entries, backtest runs are user-owned. `user_id` always from JWT. Wrong-owner → HTTP 404 (information hiding). `test_ownership.py` (50 tests). `docs/OWNERSHIP_SCOPING.md`. 3379 backend.

### Phase 3J — Provider Credential Resolver Refactor
`get_optional_current_user` dep. `_build_polygon_adapter` accepts `api_key` kwarg. `_resolve_provider_api_key` service helper. `/market-data/ohlcv` accepts optional `credential_id`. `test_market_data_credential.py` (33 tests). 3329 backend.

### Phase 3I — User Provider Credential Vault
`backend/vault/` — `ProviderCredential`, Fernet crypto, `CredentialRepository`, `VaultService` (ownership-enforced), `get_vault_service`. POST/GET/PATCH/DELETE `/provider-credentials`. No `encrypted_secret` in any response. `test_vault.py` (88 tests). `docs/PROVIDER_CREDENTIAL_VAULT.md`. 3296 backend.

### Phase 3H — Authentication & User Identity Foundation
`backend/auth/` — User, bcrypt, JWT, `UserRepository`, `AuthService`, `get_current_user`. POST `/auth/register`, POST `/auth/login`, GET `/auth/me`. No `password_hash` in any response. `test_auth.py` (83 tests). `docs/AUTH_FOUNDATION.md`. 3208 backend.

### Phase 3G — Polygon Market Data Provider Integration
`PolygonProviderAdapter` — all 15 canonical timeframes, pagination (50 pages), sanitized errors. `_build_polygon_adapter` factory builder. Factory len=4 (yahoo/csv/parquet/polygon). `test_polygon_provider.py` (85 tests). `docs/POLYGON_PROVIDER.md`. 3125 backend.

### Phase 3F — Security Baseline
`CredentialSpec` + `EnvironmentCredentialResolver`. `AuditEvent` + `emit_audit_event`. Request validation (`validate_date_range`, `validate_provider_type`, `validate_symbol`, `validate_catalog_id_format`). Sanitized provider errors (no file paths in HTTP responses). Audit hooks in catalog_service. `test_security_baseline.py` (62 tests). 3040 backend.

### Phase 3E — Dataset Catalog & File Path Resolution
`LocalDatasetEntry` (file_path backend-only). `DatasetCatalog` (JSON registry). `catalog_service` (file_path resolved internally, never propagated). 5 HTTP endpoints under `/catalog`. All response schemas file_path-free. `test_dataset_catalog.py` (72 tests). 2978 backend.

### Phase 3D — Local CSV/Parquet Providers
`LocalCSVProvider` + `LocalParquetProvider` — both implement `RangeProviderAdapter`. Registered in factory (len=3: yahoo, csv, parquet). `test_local_providers.py` (80 tests). 2906 backend.

### Phase 3C — Dataset Cache & Storage Architecture
`DatasetCachePolicy` (4 policies). `DatasetCacheState`. `DatasetCacheRegistry`. `OHLCVService.get_ohlcv()` extended with `cache_policy`. `docs/DATASET_STORAGE_LAYOUT.md`. `test_dataset_cache.py` (64 tests). 2826 backend.

### Phase 3B — Dataset Fetch Identity
`DatasetFetchParameters` (frozen, UTC-enforced). `compute_fetch_fingerprint` (SHA-256 canonical). `DatasetFetchIdentity`. `build_fetch_identity()`. `fetch_metadata` in market data response. `test_fetch_identity.py` (65 tests). 2762 backend.

### Phase 3A — Provider Abstraction Layer
`ProviderFetchError` + `ProviderCapabilities`. `ProviderAdapterFactory` + `create_default_factory_registry()`. `market_data_service.py` routes via factory. GET `/market-data/providers`. `test_provider_abstraction.py` (55 tests). 2697 backend.

### Phases 2T–2U — Tool Output Visualization + Standard Indicators
Two-pane chart architecture (lightweight-charts v5): price pane + oscillator pane. `IndicatorSeriesKind.histogram` for MACD histogram. RSI reference lines (70/50/30). Overlay lifecycle cleanup (`setMarkers([])`). ATR (Wilder's smoothing, oscillator pane). Bollinger Bands (3 price-pane overlays). 6-tool registry finalized: SMA, EMA, RSI, MACD, ATR, Bollinger Bands.

### Phases 2N–2S — Backtest Pipeline
Simulation (`run_simulation`, long-only position tracker). Cost model (commission + slippage, direction-aware). Position sizing (`EQUITY_FRACTION`). Historical tool computation pipeline (SMA/EMA/RSI/MACD dispatch, warmup/lookahead enforcement). `BacktestReport` + export routes (CSV trades, CSV equity, JSON report). `BacktestReportPage.tsx`. Strategy Test Panel wired to backtest.

### Phases 2J–2M — Strategy Semantic & Evaluation Engine
`StrategySemantics` (ConditionGroup recursive, entry/exit rules). Semantic compiler → `EvaluationPlan`. `ScalarEvaluationEngine` (6 operators). `TwoBarEvaluationContext` (crossover). `HistoricalBarContext` + `evaluate_history`. Signal events + trade intents. `PlanInspectionPanel.tsx`. Readiness layer (12 lint rules). `SemanticEditorPanel.tsx`.

### Phases 2D–2I — Strategy Tools Builder Layer
Tool registry (`/tools` endpoint). `StrategyDraft` model + `DraftRepository`. `/drafts` CRUD + archive API. `DraftWorkspace.tsx`, `AddToolForm.tsx`, `ToolCompositionPanel.tsx`. Toolset validation (`/tools/validate-toolset`). Semantic authoring UI. Binding validation. Plan inspection UI.

### Phases 2A–2C, 2G, 2H — Core Data + Storage + Services
`NormalizedOHLCV` (Pydantic, UTC-enforced). `OHLCVStore` (provider-aware Parquet). `CoverageRegistry`. `OHLCVService` (coverage-based incremental fetch). `DatasetIdentity` + `Instrument` models. Strategy registry, runtime interface, loader, runner. Visualization artifacts.

---

## Key Architecture Decisions (historical context)

- **Why `has_platform_access` is a property not a method**: extractable for future `SubscriptionService` without API changes
- **Why `evaluate_subscription_expiry` is module-level not a class method**: same extractability rationale
- **Why wrong-owner returns HTTP 404 not 403**: information hiding — attacker cannot distinguish "does not exist" from "you don't own it"
- **Why `require_admin_role` does not depend on `require_active_subscription`**: admins must retain management access even if their own subscription expires
- **Why `file_path` is absent from all catalog response schemas**: prevents leaking server filesystem structure; backend-only storage resolution
- **Why `encrypted_secret` is absent from all vault response schemas**: defense-in-depth even if response logging is misconfigured
- **Why legacy resources (user_id=None) are inaccessible to authenticated users**: forcing clean ownership state; legacy resources accessible only via admin-level tooling
- **Why no scheduler for subscription expiry**: avoids background process complexity at this maturity level; request-driven expiry is idempotent and auditable

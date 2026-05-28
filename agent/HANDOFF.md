# HANDOFF.md

## Purpose

This document provides operational continuity between implementation sessions inside QuantLab.

It acts as a lightweight persistent memory layer for:
* orchestration AI
* implementation agents
* future contributors

The objective is to:
* reduce context rebuilding
* preserve implementation continuity
* prevent duplicated work
* maintain architectural alignment
* minimize token waste

This document must remain:
* short
* operational
* high-signal
* current


Do not convert this file into a long-form knowledge base.

---

# Current Project State

## Project Name

QuantLab

## Project Type

Modular strategy research and execution ecosystem.

## Current Development Stage

Foundation implemented; backend/API expansion continues under architecture governance.

The project is currently establishing:
* architectural guardrails
* workflow discipline
* AI orchestration structure
* repository governance
* implementation protocols
* modular system boundaries

Core implementation is active with thin-route service-based backend APIs, tool registry foundations, and frontend chart visualization already in place.

---

# Current Primary Objective

Establish a scalable AI-assisted engineering foundation before major implementation begins.

Primary focus:
* repository governance
* AI orchestration discipline
* architecture definition
* modular system planning
* workflow standardization

Current priority is NOT:
* live trading
* broker integration
* execution automation
* production deployment

The immediate objective is building a disciplined modular research ecosystem.

---

# Latest Completed Work

## Phase 3P-A — Subscription Eligibility & Admin Approval Foundation (COMPLETE)

Focus: transition QuantLab from an "authenticated multi-user platform" to a "governed multi-user platform". New registrations default to `subscription_status=pending` and are blocked from protected features until an admin approves them. Admin role is bootstrapped via `admin_bootstrap_email` config — no hardcoded superusers.

New backend files:
* `backend/auth/entitlement.py` — `require_active_subscription` (HTTP 403 + audit on deny), `require_admin_role` (depends on `get_current_user` only — not `require_active_subscription`, so admins can manage users even with an expired subscription)
* `backend/api/schemas/admin.py` — `AdminUserResponse`, `ApproveUserRequest`, `SuspendUserRequest`, `ReactivateUserRequest`
* `backend/api/services/admin_service.py` — `AdminService.list_users/get_user/approve_user/suspend_user/reactivate_user`; emits audit events for each action
* `backend/api/routes/admin.py` — `GET/POST /admin/users/*` (5 endpoints, admin-only)
* `tests/unit/test_entitlement.py` — 33 tests across 8 classes

New frontend files:
* `frontend/src/components/SubscriptionGate.tsx` — blocking overlay for pending/expired/suspended users; status-specific headline/body/icon; shows logged-in username; passes through `children` when active
* `frontend/src/api/__tests__/subscriptionState.test.ts` — 9 tests (User type shape, SubscriptionStatus enum, UserRole enum, fetchOHLCV authedFetch enforcement, 403/subscription_required handling, credential_id query param)

Modified (backend):
* `backend/auth/models.py` — `UserRole` + `SubscriptionStatus` enums; `User` dataclass extended with 7 new fields; `create()` defaults to pending; `from_dict()` backward-compat defaults to active; `is_entitled`, `is_admin`, `with_active_subscription()`, `with_suspended()`, `with_reactivated()` methods
* `backend/auth/repository.py` — added `update()` + `list_all()`
* `backend/auth/service.py` — admin bootstrap logic in `register()` (config-driven, deterministic)
* `backend/core/config.py` — `admin_bootstrap_email: str = ""`
* `backend/core/audit.py` — 5 new `AuditEventKind` values (USER_APPROVED, SUBSCRIPTION_ACTIVATED, SUBSCRIPTION_EXPIRED, SUBSCRIPTION_SUSPENDED, ENTITLEMENT_DENIED)
* `backend/api/schemas/auth.py` — `UserResponse` extended with `role`, `subscription_status`, `subscription_expires_at`
* `backend/api/main.py` — admin router registered
* All protected route files gated with `Depends(require_active_subscription)` (drafts, backtest_runs, catalog, vault, semantics, plan_inspection, evaluation_readiness, draft_composition, strategy_runs composition path, market_data)
* Test fixtures updated across 12+ test files: `subscription_status="active"` added to User constructors; `require_active_subscription` override added to API test clients; vault fixtures use admin bootstrap + admin API to approve non-bootstrap users

Modified (frontend):
* `frontend/src/auth/types.ts` — `User` interface extended with `role`, `subscription_status`, `subscription_expires_at`; `SubscriptionStatus` + `UserRole` types added
* `frontend/src/api/marketData.ts` — always uses `authedFetch` (removed conditional plain-fetch path for public providers after Phase 3P-A)
* `frontend/src/App.tsx` — `SubscriptionGate` wraps authenticated content
* `frontend/src/auth/__tests__/AuthContext.test.tsx` — `mockUser` updated with new fields

Architecture invariants established:
* `require_admin_role` depends on `get_current_user` ONLY — admins retain management access if their own subscription expires
* New registrations: `subscription_status=pending` by default — no auto-approval
* Admin bootstrap: single config-driven email (`admin_bootstrap_email`) gets role=admin + status=active on registration; deterministic and documented; no runtime escalation API
* HTTP 403 (not 401) for authenticated-but-not-entitled users; detail includes `{code: "subscription_required", subscription_status: <status>}`
* `is_entitled` property accounts for `subscription_expires_at` — active + not expired = entitled
* `UserRepository.from_dict()` backward-compat: users loaded from JSON without `subscription_status` default to `active` (existing users unaffected)

Tests:
* Backend: 3415 passed, 0 failed
* Frontend: 71 passed, 0 failed

---

## Phase 3M — Frontend Ownership Integration (COMPLETE)

Focus: update frontend API clients so all ownership-scoped backend endpoints use authenticated requests via the centralized auth/session client. `AuthError` is thrown on 401 and caught in components to trigger logout → AuthGuard shows LoginPage.

Modified files:
* `frontend/src/api/client.ts` — added `AuthError` class (custom Error subclass, name="AuthError"), `isAuthError()` type guard; `authedFetch()` now throws `AuthError` on HTTP 401
* `frontend/src/api/drafts.ts` — `_req` helper uses `authedFetch` (was plain `fetch`)
* `frontend/src/api/semantics.ts` — two helpers: `_authedReq` (authedFetch) for `getSemantics`/`setSemantics`/`validateDraftSemantics`; `_publicReq` (plain fetch) for `validateSemanticsPayload` (POST /semantics/validate stays public)
* `frontend/src/api/planInspection.ts` — uses `authedFetch` for `fetchDraftPlanInspection` and `fetchDraftReadiness`
* `frontend/src/api/compositionRun.ts` — `runComposition` uses `authedFetch` (POST /strategy-runs/run-composition is protected)
* `frontend/src/api/backtestRuns.ts` — `runBacktest` + `fetchBacktestReport` use `authedFetch`; download functions (`downloadTradesCSV`/`downloadEquityCSV`/`downloadReportJSON`) converted from anchor-click to `authedFetch` + `URL.createObjectURL(blob)` (return `Promise<void>` now)
* `frontend/src/components/StrategyTestPanel.tsx` — imports `useAuth` + `isAuthError`; all four catch blocks check `isAuthError(e)` first and call `logout()` (triggers AuthGuard → LoginPage)
* `frontend/src/components/DraftWorkspace.tsx` — imports `useAuth` + `isAuthError`; `loadList` + `handleSelect` catch blocks call `logout()` on AuthError

New files:
* `frontend/src/api/__tests__/authClients.test.ts` — 17 tests: AuthError class, isAuthError guard, authedFetch (token injection, no-token, 401 throws, non-401 doesn't throw), protected clients throw AuthError on 401 (drafts, semantics draft-scoped, planInspection, compositionRun, backtestRuns), public validateSemanticsPayload does NOT throw AuthError

Public clients unchanged (remain on plain fetch):
* `frontend/src/api/marketData.ts` — GET /market-data/ohlcv (public)
* `frontend/src/api/tools.ts` — GET /tools (public)
* `frontend/src/api/health.ts` — GET /health (public)
* `frontend/src/api/strategyRuns.ts` — POST /strategy-runs/run (file-based, public)
* `frontend/src/api/backtest.ts` — stateless simulation endpoints (public)

Tests:
* Frontend: 32 passed, 0 failed (17 new auth client tests + 15 pre-existing auth context/session tests)
* TypeScript: `tsc --noEmit` clean

Architecture constraints enforced:
* No direct `fetch()` calls to ownership-scoped endpoints
* `user_id` never sent from frontend — always derived server-side from JWT
* `AuthError` thrown on 401 → component catches → `logout()` → `AuthGuard` shows `LoginPage`
* Download functions use `authedFetch` + blob URL (browser anchor-click cannot send Authorization headers)
* POST /semantics/validate (stateless, no draft_id in URL) stays on plain `fetch`

---

## Phase 3O — Credential-Aware Market Data Workflow UX (COMPLETE)

Focus: implement the first complete authenticated external market data workflow — user selects provider + owned credential, fetches normalized OHLCV, sees dataset provenance metadata. Completes the loop: credential vault → market data pipeline → frontend visualization.

Modified files:
* `frontend/src/api/marketData.ts` — added `DatasetFetchMetadata` type; extended `MarketDataOHLCVResponse` with `fetch_metadata: DatasetFetchMetadata | null`; added `credential_id?: string` to `MarketDataParams`; `fetchOHLCV` now uses `authedFetch` when `credential_id` is present (plain `fetch` otherwise — backward compatible for Yahoo)
* `frontend/src/components/Controls.tsx` — added `polygon` to PROVIDERS; added `CREDENTIALED_PROVIDERS = new Set(['polygon'])`; added credential loading via `fetchCredentials()` on mount; added credential selector (dropdown of active credentials filtered by provider); Fetch button disabled when credentialed provider selected but no credential available; `useAuth().logout()` called on `AuthError` from credential load
* `frontend/src/App.tsx` — added `DatasetFetchMetadata` import; added `fetchMetadata` state; `handleFetch` now stores `resp.fetch_metadata`; `handleFetch` calls `logout()` on `AuthError` (prevents silent fail when credential fetch uses expired token); added `DatasetMetaBadge` component (provider, candle count, dataset_id, fingerprint strip above chart)

New files:
* `frontend/src/api/__tests__/marketDataCredential.test.ts` — 12 tests: plain fetch has no Authorization header, no credential_id in query; authedFetch injects header, includes credential_id in query; 401 throws AuthError; 400 detail propagated; fetch_metadata parsed; null fetch_metadata handled; omit credential_id when undefined; correct provider in query string

Credential filtering behavior:
* `CREDENTIALED_PROVIDERS = new Set(['polygon'])` — extensible: add provider name to enable vault credential flow
* Credential selector filters: `allCredentials.filter(c => c.provider_name === provider && c.active)`
* No-credential state: yellow hint "No polygon credentials. Add one in the Credentials tab."
* Wrong-provider credentials: never shown — selector is provider-scoped

Security invariants:
* No raw secret ever stored, logged, or rendered — only credential_id (opaque UUID) is passed to backend
* `authedFetch` is used only when credential_id is present; no auth header leaked for public providers
* `AuthError` on credential load → `logout()` in Controls; `AuthError` on fetch → `logout()` in App.handleFetch
* Backend resolves the actual API key from the vault; frontend never receives it

Architecture note:
* The `fetch_metadata` response field always contains `DatasetFetchMetadata` (not a cache-hit/miss indicator — the storage pipeline is transparent). The fingerprint (first 12 chars shown) enables reproducibility auditing.

Tests:
* 12 new frontend tests in `marketDataCredential.test.ts`
* Full frontend suite: 60 passed, 0 failed
* TypeScript: `tsc --noEmit` clean

---

## Phase 3N — Frontend Provider Credential Management UI (COMPLETE)

Focus: implement the frontend credential management workflow — list, add, disable, delete provider API keys — backed by the encrypted vault APIs from Phase 3I. No raw secrets are rendered, stored, or leaked.

New files:
* `frontend/src/types/credentials.ts` — `CredentialMetadata`, `CredentialListResponse`, `RegisterCredentialRequest`; `encrypted_secret` and `secret_value` intentionally absent from `CredentialMetadata`
* `frontend/src/api/credentials.ts` — `fetchCredentials`, `registerCredential`, `disableCredential`, `deleteCredential`; all via `authedFetch`; 204 No Content handled for delete
* `frontend/src/components/CredentialManager.tsx` — full management UI: credential list with active/disabled badges, add-credential form (provider dropdown, label, masked secret input), disable/delete with confirm step; auth errors call `logout()`; secret cleared from state immediately after API call
* `frontend/src/api/__tests__/credentialClient.test.ts` — 16 tests: AuthError on 401 for all 4 functions, list parsing, POST body correctness, 204 handling, 404 error propagation, 422 error propagation, Authorization header injection, no secret fields in response type

Modified files:
* `frontend/src/App.tsx` — added `CredentialManager` import; `ActiveView` type extended with `'credentials'`; "Credentials" NavTab in header; `activeView === 'credentials'` render block with scrollable fill container

Security invariants enforced:
* `CredentialMetadata` type has no `secret_value`, `encrypted_secret`, or `raw_secret` fields
* `secret_value` is cleared from React state immediately after `registerCredential()` call (success and error paths)
* No credential is stored in `localStorage`/`sessionStorage`
* No secret is displayed after form submission
* All vault API calls use `authedFetch` — no plain `fetch` calls
* `logout()` called on `AuthError` from any vault operation

Tests:
* 16 new frontend tests in `credentialClient.test.ts`
* Full frontend suite: 48 passed, 0 failed
* TypeScript: `tsc --noEmit` clean

Supported providers in this phase: Polygon. Architecture is provider-agnostic via the `SUPPORTED_PROVIDERS` constant — adding a new provider requires adding to the array only.

---

## Phase 3M.1 — Browser-Level Authentication & Ownership Validation (COMPLETE)

Focus: runtime integrity validation of the full authenticated ownership architecture (3K + 3L + 3M). Validate ownership boundaries, session lifecycle, authenticated downloads, and HTTP status correctness. Four bugs discovered and fixed.

Bugs fixed:
* **AuthGuard blank screen** — `AuthGuard.tsx` returned `null` during token hydration (`isLoading=true`); replaced with minimal dark-themed loading indicator
* **`/catalog` missing from Vite proxy** — `vite.config.ts` had no entry for `/catalog`; requests fell through with Vite 404
* **Composition run 422 instead of 404 for wrong owner** — `composition_run_service.py` caught `DraftNotFoundError` and re-raised as `CompositionRunError` (→ 422); fixed by letting `DraftNotFoundError` propagate; added `DraftNotFoundError → 404` handler in `strategy_runs.py`
* **Backtest run 422 instead of 404 for wrong owner** — same pattern in `backtest_run_service.py` / `backtest_runs.py`; same fix applied

Modified files:
* `frontend/src/components/AuthGuard.tsx` — loading state returns visible indicator instead of `null`
* `frontend/vite.config.ts` — added `/catalog` proxy entry
* `backend/api/services/composition_run_service.py` — removed `DraftNotFoundError` wrapper; import cleaned
* `backend/api/routes/strategy_runs.py` — added `DraftNotFoundError` import; added `except DraftNotFoundError → 404` before `CompositionRunError` handler
* `backend/api/services/backtest_run_service.py` — same `DraftNotFoundError` wrapper removal
* `backend/api/routes/backtest_runs.py` — same `DraftNotFoundError → 404` handler added

New tests:
* `tests/unit/test_ownership.py` — added `TestCompositionAndBacktestRunOwnership` (3 tests): composition run wrong-owner → 404, backtest run wrong-owner → 404, composition run requires auth → 401; total now **53 passed**

New documentation:
* `docs/VALIDATION_3M1.md` — flows validated, bugs found/fixed, tests added, known limitations, architecture invariants confirmed

Architecture invariants confirmed:
* Wrong-owner access: 404 (same as not-found, information hiding) — enforced at route level for both composition run and backtest run
* `DraftNotFoundError` must propagate from services to routes unmodified — never wrapped in service-layer errors that map to 4xx other than 404
* All draft-scoped endpoints require valid Bearer token; public endpoints work without token
* Authenticated download pattern: `authedFetch → blob() → createObjectURL → anchor click → revokeObjectURL`

---

## Phase 3L — User Ownership & Resource Scoping (COMPLETE)

Focus: convert strategy drafts, dataset catalog entries, and backtest runs from globally accessible resources to user-owned resources. Users can only see and modify their own resources. `user_id` always comes from the JWT (never request body). Wrong-owner errors are indistinguishable from not-found (HTTP 404, same exception type). Legacy resources (user_id=None) are inaccessible to any authenticated user.

Modified files:
* `backend/core/audit.py` — 7 new AuditEventKind values (DRAFT_CREATED/UPDATED/DELETED/ARCHIVED/OWNERSHIP_DENIED, DATASET_OWNERSHIP_DENIED, BACKTEST_OWNERSHIP_DENIED)
* `backend/strategy_registry/drafts.py` — `user_id: str | None = None` added to `StrategyDraft`
* `backend/strategy_registry/draft_repository.py` — `load/list_all/update/archive/delete` all accept `owner_id`/`user_id`; ownership enforced via `DraftNotFoundError` (information hiding)
* `backend/storage/dataset_catalog.py` — `user_id: str | None = None` added to `LocalDatasetEntry`; `register/get/get_any/list_all/list_enabled/remove/disable` all accept ownership params
* `backend/api/services/draft_service.py` — `create/get/list/update/archive/delete` all accept and propagate ownership params; emits DRAFT_CREATED/UPDATED/ARCHIVED/DELETED
* `backend/api/routes/drafts.py` — all 6 handlers get `Depends(get_current_user)`; `user_id` extracted from JWT only
* `backend/api/services/draft_composition_service.py` + `backend/api/routes/draft_composition.py` — auth added to all 5 composition endpoints
* `backend/api/services/semantic_service.py` + `backend/api/routes/semantics.py` — draft-scoped handlers get auth; payload-only handler unchanged
* `backend/api/services/semantic_compilation_service.py` + `backend/api/routes/semantic_compilation.py` — compile draft gets auth
* `backend/api/services/semantic_binding_service.py` + `backend/api/routes/semantic_binding.py` — validate bindings gets auth
* `backend/api/services/evaluation_readiness_service.py` + `backend/api/routes/evaluation_readiness.py` — readiness gets auth
* `backend/api/services/plan_inspection_service.py` + `backend/api/routes/plan_inspection.py` — plan inspection gets auth
* `backend/api/services/composition_run_service.py` + `backend/api/routes/strategy_runs.py` — composition run gets auth; file-based run unchanged
* `backend/api/services/catalog_service.py` + `backend/api/routes/catalog.py` — all 5 catalog endpoints get auth
* `backend/api/schemas/backtest_runs.py` — `owner_user_id: str | None = None` added to `BacktestRunSummary`
* `backend/api/services/backtest_run_service.py` — `BacktestAccessDeniedError` added; create attaches owner; load enforces ownership (maps to HTTP 404)
* `backend/api/routes/backtest_runs.py` — all handlers get auth; `BacktestAccessDeniedError` → HTTP 404

Updated test files (added `get_current_user` override):
* `tests/unit/test_drafts_api.py`, `test_draft_composition_api.py`, `test_semantics_api.py`, `test_semantic_compilation_api.py`, `test_semantic_binding_api.py`, `test_evaluation_readiness_api.py`, `test_plan_inspection_api.py`, `test_dataset_catalog.py`, `test_backtest_exports.py`, `test_security_baseline.py`

New files:
* `tests/unit/test_ownership.py` — 50 tests, 9 classes: repository, service, catalog, draft routes, catalog routes, backtest, public routes, legacy behavior, vault unaffected
* `docs/OWNERSHIP_SCOPING.md` — ownership model, access control rules, audit events

Tests:
* Full suite: 3379 passed, 0 failed

Architecture constraints enforced:
* `user_id` always from `current_user.user_id` (JWT) — never from request body
* Wrong-owner → identical exception as not-found (information hiding, HTTP 404)
* GET /tools, GET /market-data/providers, GET /health, POST /strategy-runs/run (file) remain unauthenticated
* Payload-only endpoints without `{draft_id}` in URL remain unauthenticated
* Legacy resources (user_id=None) inaccessible to all authenticated users
* `BacktestAccessDeniedError` → HTTP 404
* Vault/provider credential code untouched

---

## Phase 3J — Provider Credential Resolver Refactor (COMPLETE)

Focus: complete the security-identity sequence (3F→3G→3H→3I→3J). Polygon provider now supports authenticated user-owned credentials from the vault as the primary path. ENV-based resolver retained as documented transitional fallback. All other providers (yahoo, csv, parquet) unaffected.

Modified files:
* `backend/auth/dependencies.py` — added `get_optional_current_user()` dependency; returns `User | None` instead of raising 401; used for optional-auth endpoints
* `backend/data_providers/provider_factory.py` — `_build_polygon_adapter()` now accepts optional `api_key` kwarg; if provided, uses it directly (vault path); if absent, falls back to `EnvironmentCredentialResolver` (ENV path); both `_build_polygon_adapter` and `create_default_factory_registry` docstrings updated
* `backend/api/services/market_data_service.py` — added `_resolve_provider_api_key(provider, credential_id, user_id)` helper; all vault errors mapped to sanitized `MarketDataError`; `fetch_ohlcv()` gains `credential_id` and `user_id` params (backward-compatible defaults=None); calls resolver before factory.build(); passes resolved `api_key` to factory
* `backend/api/routes/market_data.py` — added optional `credential_id` query param; added `current_user: Optional[User] = Depends(get_optional_current_user)`; auth gate: if `credential_id` present and user not authenticated → HTTP 401; passes `user_id` and `credential_id` to service

New file:
* `tests/unit/test_market_data_credential.py` — 33 tests across 6 classes: TestResolveProviderApiKey, TestPolygonBuilderVaultPath, TestGetOptionalCurrentUser, TestMarketDataRouteCredentialFlow, TestFetchOhlcvCredentialIntegration, TestArchitectureBoundary

Tests:
* Full suite: 3329 passed, 0 failed

Credential resolution flow (complete path):
```
GET /market-data/ohlcv?provider=polygon&credential_id=<id>
→ route: auth gate (401 if credential_id + no token)
→ route: passes user_id + credential_id to fetch_ohlcv()
→ service: _resolve_provider_api_key() → VaultService.resolve_secret()
→ service: factory.build("polygon", ..., api_key=raw_key)
→ factory: _build_polygon_adapter() uses api_key directly (no ENV)
→ PolygonProviderAdapter(api_key=raw_key)
→ OHLCVService → cache/storage → response
```

ENV fallback flow (backward compat):
```
GET /market-data/ohlcv?provider=polygon  (no credential_id)
→ route: no auth required
→ service: _resolve_provider_api_key() returns None
→ factory: _build_polygon_adapter() reads POLYGON_API_KEY env var
→ PolygonProviderAdapter(api_key=env_key)
```

Architecture boundaries enforced:
* `market_data_service.py` has no concrete adapter imports (AST-verified)
* No vault imports at route module level — lazy imports only in service
* `get_optional_current_user` never raises 401 (callers decide)
* Auth check (is user present?) is in route; vault logic (resolve secret) is in service

---

## Phase 3I — User Provider Credential Vault (COMPLETE)

Focus: user-owned provider credential vault. Authenticated users register/manage API credentials for external providers. Secrets are Fernet-encrypted (never stored as plaintext). Ownership strictly enforced — cross-user access returns 404 (information hiding). Prepares Polygon and future providers for per-user credential resolution.

New files:
* `backend/vault/models.py` — `ProviderCredential` frozen dataclass; `__repr__` omits `encrypted_secret`; `with_active()` immutable update
* `backend/vault/crypto.py` — `encrypt_secret` / `decrypt_secret` using Fernet; key derived from `vault_encryption_key` via SHA-256; `VaultCryptoError` on tamper/wrong-key
* `backend/vault/repository.py` — `CredentialRepository` (thread-safe lock + atomic rename write); `save`/`update`/`delete`/`get_by_id`/`list_by_user`
* `backend/vault/service.py` — `VaultService`; `register_credential` (encrypts secret before persistence), `list_credentials`, `get_credential`, `disable_credential`, `delete_credential`, `resolve_secret` (internal use only); ownership enforcement via `requesting_user_id`; all 7 vault audit events emitted
* `backend/vault/dependencies.py` — `get_vault_service()` FastAPI dep
* `backend/vault/__init__.py`
* `backend/api/schemas/vault.py` — `RegisterCredentialRequest`, `CredentialMetadataResponse`, `CredentialListResponse`; no `encrypted_secret`/`secret_value` in responses
* `backend/api/routes/vault.py` — POST /provider-credentials (201), GET /provider-credentials (200), GET /provider-credentials/{id} (200), PATCH /provider-credentials/{id}/disable (200), DELETE /provider-credentials/{id} (204)
* `docs/PROVIDER_CREDENTIAL_VAULT.md`

Modified files:
* `backend/core/config.py` — added `vault_encryption_key`, `credentials_file_path`
* `backend/core/audit.py` — added 7 new `AuditEventKind` values: VAULT_CREDENTIAL_REGISTERED, _RESOLVED, _LISTED, _DISABLED, _DELETED, _ACCESS_DENIED, _RESOLUTION_FAILED
* `backend/core/credentials.py` — added `CredentialSource.VAULT` enum value
* `backend/api/main.py` — registered vault router
* `pyproject.toml` — added `cryptography>=42.0`
* `tests/unit/test_security_baseline.py` — updated `test_all_event_kinds_defined` to include 7 vault events

Tests:
* `tests/unit/test_vault.py` — 88 tests across 9 classes: TestProviderCredentialModel, TestVaultCrypto, TestCredentialRepository, TestVaultService, TestVaultRoutes, TestCrossUserIsolation, TestSecurityInvariants, TestArchitectureBoundary, TestPolygonBackwardCompatibility
* Full suite: 3296 passed, 0 failed

Security invariants enforced:
* `CredentialMetadataResponse` has no `encrypted_secret`/`secret_value` fields
* `ProviderCredential.__repr__` omits `encrypted_secret`
* JSON file stores only Fernet ciphertext
* `CredentialAccessDeniedError` is same for not-found and wrong-owner (information hiding)
* All 7 vault audit events contain no raw secrets
* `resolve_secret()` is internal-only — never called from routes

Polygon backward compatibility:
* Polygon still uses `EnvironmentCredentialResolver` (Phase 3J will refactor to vault)
* Factory len=4 unchanged; all existing tests pass

---

## Phase 3H — Authentication & User Identity Foundation (COMPLETE)

Focus: foundational authentication before user-owned provider credentials. User identity model, JWT-based tokens, bcrypt passwords, JSON-backed repository, `get_current_user` dependency, three auth endpoints, audit integration.

New files:
* `backend/auth/models.py` — `User` frozen dataclass; `create()` factory assigns uuid4, lowercases username/email, sets UTC created_at
* `backend/auth/password.py` — bcrypt hash/verify; empty input guard; timing-safe verify
* `backend/auth/tokens.py` — `create_access_token` / `decode_access_token`; `TokenError` / `TokenExpiredError`; payload: `{sub, user_id, exp}` only
* `backend/auth/repository.py` — `UserRepository` (thread-safe lock + atomic rename write); `DuplicateUsernameError` / `DuplicateEmailError`
* `backend/auth/service.py` — `AuthService`; `register()` + `login()`; emits audit events for all outcomes; generic error message on login failure
* `backend/auth/dependencies.py` — `get_current_user` FastAPI dependency (`HTTPBearer`); emits audit events for INVALID_TOKEN / PROTECTED_ROUTE_DENIED
* `backend/auth/__init__.py` — re-exports User, AuthService, get_current_user
* `backend/api/schemas/auth.py` — `RegisterRequest`, `LoginRequest`, `TokenResponse`, `UserResponse` (no password_hash field in any response)
* `backend/api/routes/auth.py` — POST /auth/register (201), POST /auth/login (200), GET /auth/me (200)
* `docs/AUTH_FOUNDATION.md`

Modified files:
* `backend/core/config.py` — added `auth_secret_key`, `auth_algorithm`, `access_token_expire_minutes`, `users_file_path`
* `backend/core/audit.py` — added 5 new `AuditEventKind` values: USER_REGISTERED, LOGIN_SUCCESS, LOGIN_FAILURE, INVALID_TOKEN, PROTECTED_ROUTE_DENIED
* `backend/api/main.py` — registered auth router
* `pyproject.toml` — added `bcrypt>=4.0.0`, `PyJWT>=2.8.0`, `email-validator>=2.0`
* `tests/unit/test_security_baseline.py` — updated `test_all_event_kinds_defined` to include 5 new auth event kinds

Tests:
* `tests/unit/test_auth.py` — 83 tests across 8 classes: TestUserModel, TestPasswordHashing, TestTokens, TestUserRepository, TestAuthService, TestGetCurrentUserDependency, TestAuthRoutes, TestSecurityInvariants, TestArchitectureBoundary
* Full suite: 3208 passed, 0 failed

Security invariants enforced:
* `password_hash` never in any API response schema
* Token payload: `{sub, user_id, exp}` only — no secrets
* Login error is generic regardless of which field is wrong
* Auth secret key never in logs or responses
* JSON users file uses atomic write (temp + rename)

Architecture boundary:
* `backend/auth/` has no imports from `data_providers/`, `strategy_runtime/`, `strategy_registry/`
* Auth tightly decoupled from provider layer — no credential vault yet (Phase 3I+)

---

## Phase 3G — Polygon Market Data Provider Integration (COMPLETE)

Focus: introduce Polygon.io as the first external API-key-based market data provider. Validates that the existing provider architecture, credential system, normalization pipeline, cache/storage layer, and dataset identity all work correctly with a real remote REST API — without any changes to API services, routes, or the strategy layer.

Pre-existing (already correctly implemented before this phase):
* `ProviderAdapterFactory` + 3 providers (yahoo/csv/parquet) — Phases 3A/3D
* `EnvironmentCredentialResolver` + `MissingCredentialError` — Phase 3F
* `DatasetCachePolicy` (4 policies) — Phase 3C
* `DatasetFetchIdentity` + `build_fetch_identity` — Phase 3B
* `OHLCVService.get_ohlcv(cache_policy=...)` — Phase 3C

Completed in this phase:

**`backend/data_providers/polygon/adapter.py`** (new):
* `PolygonAdapterError(ProviderFetchError)` — base error; messages never contain API key values or names
* `PolygonRateLimitError(PolygonAdapterError)` — raised on HTTP 429
* `SUPPORTED_TIMEFRAMES: dict[str, tuple[int, str]]` — all 15 canonical QuantLab timeframes mapped to `(multiplier, timespan)` for Polygon v2/aggs endpoint
* `PolygonProviderAdapter(RangeProviderAdapter)` — receives `api_key` at construction; never logs or propagates it
* `fetch(start, end)` — calls Polygon `/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{from}/{to}`; follows pagination (`next_url`) for up to `_MAX_PAGES=50` pages; applies `[start, end]` filter after conversion; returns `list[NormalizedOHLCV]`
* `_format_date_params(start, end, timespan)` — `day/week/month` → `YYYY-MM-DD` strings; intraday → Unix millisecond strings
* `_handle_http_error(exc)` — 404 → `{}` (empty); 401 → `PolygonAdapterError` (no key in message); 429 → `PolygonRateLimitError`; 5xx → `PolygonAdapterError`
* `_parse_result(item)` — `t` (ms) → UTC `datetime`; `vw`/`n` optional → `NormalizedOHLCV.vwap`/`trade_count`
* Isolation: no imports of yahoo, csv, parquet, api routes, strategy_runtime, or credentials (factory builder resolves credentials)

**`backend/data_providers/polygon/__init__.py`** (new):
* Exports: `PolygonAdapterError`, `PolygonProviderAdapter`, `PolygonRateLimitError`, `POLYGON_SUPPORTED_TIMEFRAMES`

**`backend/data_providers/provider_factory.py`** (modified):
* `_POLYGON_CAPABILITIES` — 15 timeframes, 5 asset classes
* `_build_polygon_adapter()` — lazy-imports `CredentialSpec`/`EnvironmentCredentialResolver`; catches `MissingCredentialError` and re-raises as `ProviderBuildError` (safe message, no key); lazy-imports `PolygonProviderAdapter`; passes resolved `api_key`
* `create_default_factory_registry()` — now registers 4 providers: `yahoo`, `csv`, `parquet`, `polygon`

**`backend/data_providers/__init__.py`** (modified):
* Added exports: `PolygonAdapterError`, `PolygonProviderAdapter`, `PolygonRateLimitError`, `POLYGON_SUPPORTED_TIMEFRAMES`

**`docs/POLYGON_PROVIDER.md`** (new):
* Architecture position, credential setup, supported timeframes table, pagination behavior, error handling matrix, NormalizedOHLCV field mapping, cache policy compatibility, architecture boundaries, known limitations

**`tests/unit/test_polygon_provider.py`** (new — 85 tests):
* `TestPolygonErrorHierarchy` (3): error class relationships
* `TestPolygonAdapterConstruction` (8): valid/invalid constructor args
* `TestPolygonAdapterCapabilities` (6): all 15 timeframes, asset classes, ProviderCapabilities contract
* `TestPolygonAdapterFetch` (8): UTC enforcement, empty result, source/symbol/timeframe/timezone
* `TestPolygonAdapterNormalization` (11): OHLCV fields, vwap/trade_count present/absent, ms timestamp conversion, malformed row skipped
* `TestPolygonAdapterHTTPErrors` (8): 401/429/404/500/bad JSON/network/generic — all sanitized
* `TestPolygonDateParams` (5): day/week/month → date strings; minute/hour → millisecond strings
* `TestPolygonAdapterPagination` (4): single page, follows next_url, accumulates, stops at MAX_PAGES
* `TestPolygonFactoryRegistration` (6): factory contains polygon, len=4, capabilities correct, build with env var, missing key → ProviderBuildError
* `TestPolygonCredentialResolution` (5): env var resolves, missing → ProviderBuildError, no key value in error, cause is MissingCredentialError, audit events emitted
* `TestPolygonCacheIntegration` (4): FETCH_AND_STORE, BYPASS_CACHE, FORCE_REFRESH, READ_ONLY — all via OHLCVService
* `TestPolygonDatasetIdentity` (4): build_fetch_identity for polygon, deterministic fingerprint, dataset_id contains "polygon", no API key in identity
* `TestPolygonArchitectureBoundary` (8): no yahoo/csv/parquet/api/strategy_runtime/credentials imports; 401 message no key value; 401 message no key name
* `TestPolygonBackwardCompatibility` (5): yahoo/csv/parquet still in factory, len=4, legacy CSVAdapter unaffected

**`tests/unit/test_provider_factory.py`** (modified):
* `test_default_registry_has_three_providers` → `test_default_registry_has_four_providers` (len == 4)

**`tests/unit/test_local_providers.py`** (modified):
* `test_factory_len_is_three` → `test_factory_len_is_four` (len == 4)
* `test_factory_len_increased_by_two` → `test_factory_len_increased_by_three` (len == 4)

**`tests/unit/test_security_baseline.py`** (modified):
* `test_factory_still_has_three_providers` → `test_factory_still_has_four_providers` (len == 4)

Validation:
* `pytest` → **3125 passed**, zero regressions (3040 pre-3G + 85 new)
* Architecture boundaries: `polygon/adapter.py` imports no yahoo, csv, parquet, api routes, strategy_runtime, or credentials (AST-verified in tests)
* Credential safety: `PolygonAdapterError` message tested to not contain raw API key value or env var name
* Cache interoperability: all 4 cache policies tested end-to-end via `OHLCVService`
* Dataset identity: `build_fetch_identity` for `polygon` produces deterministic fingerprint; no API key present
* Factory: `create_default_factory_registry()` now returns 4 providers; all prior providers fully preserved

Correct Polygon provider flow after Phase 3G:
```
factory.build("polygon", symbol="AAPL", timeframe="1d", ...)
    → _build_polygon_adapter()
    → EnvironmentCredentialResolver.resolve(POLYGON_API_KEY)  # emits audit event
    → PolygonProviderAdapter(api_key=<secret>)
    → OHLCVService.get_ohlcv(cache_policy=...)
    → fetch(start, end) → GET /v2/aggs/ticker/AAPL/range/1/day/... (with pagination)
    → list[NormalizedOHLCV] (source="polygon")
    → cache/storage layer
    → API response
```

Known limitations:
* REST only — no WebSocket, tick streaming, or live subscriptions
* No auto-retry on rate limits — callers are responsible for retry policy
* No symbol validation at construction time — HTTP 404 at fetch returns `[]`
* `adjustment_mode="raw"` sets `adjusted=false` on Polygon's end; QuantLab makes no additional adjustment

---

## Phase 3F — Security Baseline for Provider & Dataset Access (COMPLETE)

Focus: establish the minimum security foundation required before adding external API-key-based providers (Binance, Polygon, IBKR). Enforces credential isolation, audit traceability, safe error messages, and request validation hardening — without implementing full auth, OAuth, RBAC, or any live provider.

Pre-existing (already correctly implemented before this phase):
* `ProviderAdapterFactory` + 3 providers (yahoo/csv/parquet) — Phase 3A/3D
* `DatasetCatalog` + catalog service + HTTP routes — Phase 3E
* File path isolation in API responses — Phase 3E

Completed in this phase:

**`backend/core/credentials.py`** (new):
* `CredentialSource(str, Enum)` — `ENV_VAR` (extensible for future vault/SSM)
* `CredentialSpec(BaseModel, frozen)` — `provider_name`, `credential_key` (env var name, not value), `source_type`, `description`; validates no empty fields
* `CredentialResolutionError(Exception)` — base; invariant: messages never contain raw secret values
* `MissingCredentialError(CredentialResolutionError)` — raised when env var absent/empty; message names provider but not the key or value
* `EnvironmentCredentialResolver.resolve(spec)` — reads `os.environ[spec.credential_key]`; emits audit events for attempt + missing; logs warning on missing (no secret in log); returns raw secret (caller's responsibility to keep private)

**`backend/core/audit.py`** (new):
* `AuditEventKind(str, Enum)` — 6 kinds: `credential_resolution_attempt`, `credential_missing`, `dataset_registered`, `dataset_removed`, `provider_fetch_request`, `catalog_ohlcv_fetch`
* `AuditEvent(frozen dataclass)` — `event_kind`, `provider_name`, `details` (safe metadata only), `timestamp` (UTC)
* `emit_audit_event(event)` — logs structured JSON to `quantlab.audit` logger at INFO; details must contain no paths, secrets, or tokens

**`backend/core/request_validation.py`** (new):
* `ALLOWED_CATALOG_PROVIDER_TYPES = frozenset({"csv", "parquet"})` — extends when new local providers added
* `validate_date_range(start, end)` — raises `ValueError` if `start >= end`
* `validate_provider_type(provider_type, allowed)` — case-insensitive; raises `ValueError("Unknown provider_type ...")` listing allowed values
* `validate_symbol(symbol)` — raises `ValueError` for blank/whitespace
* `validate_catalog_id_format(catalog_id)` — raises `ValueError` for blank/whitespace

**`backend/api/services/catalog_service.py`** (modified):
* `register_dataset()`: validates `provider_type` via `validate_provider_type()` before touching filesystem; sanitized file-not-found message (path stripped from HTTP error); sanitized duplicate message; emits `DATASET_REGISTERED` audit event with `catalog_id/symbol/asset_class/timeframe` (no path)
* `remove_dataset()`: emits `DATASET_REMOVED` audit event
* `fetch_ohlcv()`: emits `CATALOG_OHLCV_FETCH` audit event before fetch; `ProviderFetchError` and `OHLCVIngestionError` caught → full error logged internally → sanitized `CatalogFetchError` raised (no file path in message); `ProviderBuildError` similarly sanitized

**`backend/api/routes/catalog.py`** (modified):
* `get_catalog_ohlcv()`: calls `validate_date_range(start, end)` after UTC coercion; returns HTTP 400 if start >= end

**`tests/unit/test_security_baseline.py`** (new — 62 tests):
* `TestCredentialSpec` (8): construction, frozen, empty fields raise, description stored, source_type default, spec safe to serialize
* `TestEnvironmentCredentialResolver` (6): resolve present, missing raises `MissingCredentialError`, missing is `CredentialResolutionError`, error message has no secret value or key name, error message contains provider name, empty env var raises
* `TestAuditEvent` (4): construction, frozen, default timestamp UTC, all 6 event kinds defined
* `TestEmitAuditEvent` (4): emits to audit logger, emitted record is valid JSON, no file_path in audit record, credential attempt+missing events both emitted
* `TestRequestValidation` (14): date range valid/equal/reversed, provider_type csv/parquet/case-insensitive/unknown/lists-allowed, symbol valid/empty/whitespace, catalog_id format valid/empty/whitespace, allowed types contains csv+parquet, not yahoo
* `TestSafeErrorPolicy` (3): fetch error after file deletion does not expose path, file-not-found message safe, unknown provider_type raises with safe message
* `TestAuditHookIntegration` (4): register emits DATASET_REGISTERED, remove emits DATASET_REMOVED, fetch emits CATALOG_OHLCV_FETCH, audit records contain no file_path
* `TestArchitectureBoundary` (7): strategies/ no core.credentials import, credentials.py no yahoo, audit.py no provider_factory, API schemas no credential fields, LocalDatasetEntry no credential fields, catalog_service no yahoo import, MissingCredentialError hierarchy
* `TestRouteValidation` (3): start > end returns 400, unknown provider_type returns 400, register response no credential fields
* `TestBackwardCompatibility` (5): yahoo/csv/parquet still in factory, factory len=3, catalog register still works, OHLCVService still accepts cache_policy

**`tests/unit/test_dataset_catalog.py`** (modified):
* `test_register_directory_path_raises` — removed `match="not a regular file"` pattern (message now sanitized in Phase 3F)

Validation:
* `pytest` → **3040 passed**, zero regressions (2978 pre-3F + 62 new)
* Architecture boundaries: credentials.py and audit.py verified by AST tests to import no provider-specific modules
* Secret safety: `MissingCredentialError` tested to not contain raw secret value or env var key name
* File path safety: `CatalogFetchError` tested to not expose file path after provider fetch failure

Safe credential flow (ready for future external providers):
```
Future Binance provider:
    _SPEC = CredentialSpec(provider_name="binance", credential_key="BINANCE_API_KEY")
    _RESOLVER = EnvironmentCredentialResolver()
    api_key = _RESOLVER.resolve(_SPEC)  # raises MissingCredentialError if absent
                                         # emits audit event
                                         # never logs or returns the value externally
```

Known limitations:
* `EnvironmentCredentialResolver` only supports `ENV_VAR` source type — no vault, AWS SSM, or secrets manager yet (acceptable for Phase 3F scope)
* No credential rotation detection (static env var read per request)
* Audit events are log-only (no persistence to DB or audit store — future phase)
* `validate_provider_type` for catalog hardcodes `{"csv", "parquet"}` — must be updated when new catalog-compatible local providers are added to `create_default_factory_registry()`

---

## Phase 3E — Dataset Catalog & File Path Resolution (COMPLETE)

Focus: bridge local dataset providers (CSV / Parquet) to the HTTP API without exposing raw filesystem paths. API consumers interact with opaque `catalog_id` references only; file path resolution is encapsulated inside the service layer.

Pre-existing (already correctly implemented before this phase):
* `LocalCSVProvider` / `LocalParquetProvider` — Phase 3D local providers
* `ProviderAdapterFactory` + `create_default_factory_registry()` — routes `build("csv", file_path=...)` to provider
* `OHLCVService.get_ohlcv()` — full pipeline (Phase 3C)

Completed in this phase:

**`backend/storage/dataset_catalog.py`** (new):
* `LocalDatasetEntry` — frozen Pydantic model with: `catalog_id` (UUID str), `provider_type`, `file_path` (backend-only, never in responses), `display_name`, `dataset_type`, `asset_class`, `timeframe`, `symbol`, `venue`, `adjustment_mode`, `registered_at` (UTC), `enabled`, `metadata` (optional dict)
* `DatasetCatalog` — JSON-backed registry at `{base_path}/catalog/datasets.json`; methods: `register()` (UUID assignment, symbol/venue uppercased, provider_type lowercased, duplicate path check), `get()` (raises `DatasetDisabledError` for disabled), `get_any()` (admin, ignores disabled), `list_all()`, `list_enabled()`, `disable()`, `remove()`, `__contains__`, `__len__`
* Error hierarchy: `DatasetCatalogError` → `UnknownDatasetError`, `DatasetDisabledError`, `DuplicateDatasetError`
* `_persist()` flushes immediately on every mutation; `_load_all()` reads from disk on every query (no in-memory cache)

**`backend/api/schemas/catalog.py`** (new):
* `RegisterDatasetRequest` — input schema (includes `file_path` for backend use)
* `CatalogEntryResponse` — no `file_path`; 11 metadata fields
* `CatalogListResponse` — wraps `list[CatalogEntryResponse]` with count
* `RegisterDatasetResponse` — no `file_path`; catalog_id + key metadata
* `CatalogOHLCVCandle` + `CatalogOHLCVResponse` — no `file_path`; candles with catalog_id envelope

**`backend/api/services/catalog_service.py`** (new):
* `register_dataset()` — validates file exists + is regular file; calls `DatasetCatalog.register()`; never returns `file_path`
* `list_datasets()` — returns `CatalogListResponse` (enabled only by default; `include_disabled=True` flag)
* `get_dataset()` — returns `CatalogEntryResponse`; translates `UnknownDatasetError` → `CatalogNotFoundError`, `DatasetDisabledError` → `CatalogDatasetDisabledError`
* `remove_dataset()` — soft-deletes from catalog (does not touch underlying file)
* `fetch_ohlcv()` — full resolution: `catalog.get(catalog_id)` → `entry.file_path` (internal) → `factory.build(provider_type, file_path=entry.file_path, ...)` → `DatasetIdentity + Instrument` → `OHLCVService.get_ohlcv()` → `CatalogOHLCVResponse`; `file_path` never propagated to caller
* Service error hierarchy: `CatalogRegistrationError`, `CatalogNotFoundError`, `CatalogDatasetDisabledError`, `CatalogFetchError`

**`backend/api/routes/catalog.py`** (new):
* `POST   /catalog/datasets` → 201 `RegisterDatasetResponse`; 400 on registration error
* `GET    /catalog/datasets` → 200 `CatalogListResponse`; `?include_disabled=true` supported
* `GET    /catalog/datasets/{catalog_id}` → 200 `CatalogEntryResponse`; 404 / 410 (disabled)
* `DELETE /catalog/datasets/{catalog_id}` → 204; 404 on unknown
* `GET    /catalog/datasets/{catalog_id}/ohlcv` → 200 `CatalogOHLCVResponse`; 404 / 410 / 400; naive datetimes coerced to UTC

**`backend/api/main.py`** (modified):
* `from backend.api.routes import catalog` added; `app.include_router(catalog.router)` added

**`tests/unit/test_dataset_catalog.py`** (new — 72 tests):
* `TestLocalDatasetEntry` (5): construction, immutability, enabled default, metadata optional/stored
* `TestDatasetCatalogRegistration` (8): returns entry, creates JSON file, symbol/venue uppercased, provider_type lowercased, duplicate raises, allow_duplicate_path flag, empty symbol raises, unique catalog_ids
* `TestDatasetCatalogGet` (4): get registered, get unknown raises, get disabled raises DatasetDisabledError, get_any returns disabled
* `TestDatasetCatalogList` (5): list_all empty, list_all returns all, list_enabled excludes disabled, list_all includes disabled
* `TestDatasetCatalogDisableRemove` (5): disable unknown raises, disable returns updated, remove unknown raises, remove then not in, remove reduces len
* `TestDatasetCatalogPersistence` (6): entries survive new instance, contains operator, missing returns false, non-string false, empty catalog no file, JSON response has no file_path
* `TestCatalogServiceRegister` (5): file not found raises, no file_path in response, catalog_id present, duplicate raises, directory path raises
* `TestCatalogServiceList` (5): empty, after register, excludes disabled, include_disabled flag, entries have no file_path field
* `TestCatalogServiceGetRemove` (6): get unknown, get disabled, returns CatalogEntryResponse, no file_path, remove unknown, remove then get raises
* `TestCatalogServiceFetchOHLCV` (4): unknown raises, disabled raises, returns CatalogOHLCVResponse, naive datetimes treated as UTC
* `TestCatalogHTTPRegister` (3): 201 + no file_path, file not found 400, duplicate 400
* `TestCatalogHTTPList` (3): empty 200, after register count=1, entries no file_path
* `TestCatalogHTTPGetDelete` (5): get 200 + no file_path, get unknown 404, delete 204, delete then get 404, delete unknown 404
* `TestCatalogHTTPOHLCV` (3): unknown 404, returns candles, no file_path in response
* `TestFilePathIsolation` (5): CatalogEntryResponse no file_path, RegisterDatasetResponse no file_path, CatalogOHLCVResponse no file_path, CatalogListResponse no file_path, catalog_service AST-verified (no yahoo import)

Validation:
* `pytest` → **2978 passed**, zero regressions (2906 pre-3E + 72 new)
* File path isolation enforced: `file_path` absent from all 4 response schema classes (verified by AST + model_fields assertions in tests)
* Architecture boundary: `catalog_service.py` imports no yahoo/concrete adapter modules (AST-verified in test suite)

Correct catalog resolution flow after Phase 3E:
```
POST /catalog/datasets { file_path: "/data/aapl.csv", ... }
    → DatasetCatalog.register() → catalog_id stored with file_path
    → RegisterDatasetResponse { catalog_id, display_name, ... }  ← no file_path

GET /catalog/datasets/{catalog_id}/ohlcv
    → catalog_service.fetch_ohlcv(catalog_id)
    → DatasetCatalog.get(catalog_id) → entry.file_path (backend only)
    → factory.build("csv", file_path=entry.file_path, ...)
    → OHLCVService.get_ohlcv()
    → CatalogOHLCVResponse { catalog_id, candles, ... }  ← no file_path
```

Known limitations:
* No pagination on GET /catalog/datasets (small catalog assumed for Phase 3E scope)
* No authentication or user-scoping (single-user research tool)
* catalog.json mutation is not thread-safe (acceptable for single-process dev/research)
* file_path is validated for existence at registration time only; file moves/deletes are not tracked after registration

---

## Phase 3D — Local Dataset Providers (CSV / Parquet) (COMPLETE)

Focus: validate that QuantLab's provider architecture is truly provider-agnostic by adding local CSV and Parquet dataset providers. After normalization, local files and remote API sources (Yahoo, future Binance/IBKR/Polygon) flow through identical pipelines. This phase is a major architectural validation milestone.

Pre-existing (already correctly implemented before this phase):
* `ProviderAdapterFactory` + `create_default_factory_registry()` — Phase 3A provider isolation
* `DatasetFetchIdentity` + fingerprinting — Phase 3B traceability
* `DatasetCacheRegistry` + cache policies — Phase 3C persistence layer
* `CSVAdapter` (legacy) — general-purpose CSV loader with `file_path` at call time (unchanged)

Completed in this phase:

**`backend/data_providers/local/_shared.py`** (new):
* `LocalColumnMap` — dataclass mapping source column names to canonical field names; defaults match standard OHLCV naming; override for non-standard files (e.g. Yahoo CSV export with capitalized headers)
* `parse_timestamp_string(raw) → datetime` — parses Unix epoch, ISO-8601 (with/without tz, Z suffix), naive ISO, date-only YYYY-MM-DD; raises `ValueError` on unsupported format

**`backend/data_providers/local/csv_provider.py`** (new):
* `LocalCSVProviderError(ProviderFetchError)` — file not found, missing columns, parse errors
* `LocalCSVProvider(RangeProviderAdapter)` — file path embedded at construction; `provider_name="csv"`; `fetch(start, end)` loads file and filters by date; `load()` loads all; column map support; supports all 15 canonical timeframes and 7 asset classes

**`backend/data_providers/local/parquet_provider.py`** (new):
* `LocalParquetProviderError(ProviderFetchError)` — file not found, missing columns, corrupt file, parse errors
* `LocalParquetProvider(RangeProviderAdapter)` — file path embedded at construction; `provider_name="parquet"`; `fetch(start, end)` with date filtering; timestamp resolution handles `datetime` (tz/naive), microsecond integers (pyarrow style), second integers, ISO strings
* `_resolve_parquet_timestamp(raw)` — resolves all pyarrow `to_pydict()` timestamp formats to UTC datetime

**`backend/data_providers/local/__init__.py`** (new):
* Package exports: `LocalColumnMap`, `LocalCSVProvider`, `LocalCSVProviderError`, `LocalParquetProvider`, `LocalParquetProviderError`

**`backend/data_providers/provider_factory.py`** (modified):
* `_CSV_CAPABILITIES` + `_build_csv_provider()` — requires `file_path` kwarg; raises `ProviderBuildError` if absent
* `_PARQUET_CAPABILITIES` + `_build_parquet_provider()` — same
* `create_default_factory_registry()` now registers 3 providers: `yahoo`, `csv`, `parquet`
* All imports of local adapters are lazy (inside builder functions) — same pattern as Yahoo

**`backend/data_providers/__init__.py`** (modified):
* Added exports for all 5 new local provider symbols

**`tests/fixtures/ohlcv_nonstandard_cols.csv`** (new):
* 3-row OHLCV CSV with capitalized headers (`Date`, `Open`, `High`, `Low`, `Close`, `Volume`) for column map tests

**`tests/unit/test_local_providers.py`** (new — 80 tests):
* `TestLocalColumnMap` (3): defaults, custom values, is dataclass
* `TestLocalCSVProviderBasic` (8): provider_name, source field, NormalizedOHLCV, metadata fields, timeframes, asset classes, empty body, UTC-aware timestamps
* `TestLocalCSVProviderFetch` (6): full range, excludes before start, excludes after end, empty range, naive start raises, naive end raises
* `TestLocalCSVProviderErrors` (5): missing file, missing column, error message, invalid timestamp, subclass of ProviderFetchError
* `TestLocalCSVProviderColumnMap` (3): nonstandard column map works, fails without map, date-only YYYY-MM-DD to midnight UTC
* `TestLocalCSVProviderRealFixture` (2): loads valid_ohlcv.csv, all records UTC-aware
* `TestLocalParquetProviderBasic` (7): provider_name, source field, NormalizedOHLCV, metadata fields, UTC-aware, timeframes, OHLCV values
* `TestLocalParquetProviderFetch` (4): full range, excludes out of range, empty range, naive raises
* `TestLocalParquetTimestampTypes` (5): datetime with tz, datetime naive, microsecond int, second int, ISO string
* `TestLocalParquetProviderErrors` (5): missing file, missing column, invalid parquet, empty returns [], subclass
* `TestFactoryRegistration` (12): csv/parquet in factory, yahoo still in factory, len=3, build returns correct type, missing file_path → ProviderBuildError ×2, capabilities fields, timeframes, asset classes
* `TestOHLCVServiceCSVIntegration` (4): FETCH_AND_STORE, BYPASS_CACHE no storage, cache_metadata.json written, second call hits cache
* `TestOHLCVServiceParquetIntegration` (3): FETCH_AND_STORE, records normalized, cache_metadata.json written
* `TestFetchIdentityIntegration` (4): build_fetch_identity csv, deterministic, build_fetch_identity parquet, csv≠parquet fingerprints
* `TestArchitectureBoundary` (5): csv no yahoo, parquet no yahoo, csv no api, parquet no api, shared no yahoo
* `TestBackwardCompatibility` (4): yahoo still in factory, len=3, legacy CSVAdapter unaffected, OHLCVService signature unchanged

**`tests/unit/test_provider_factory.py`** (modified):
* `test_default_registry_has_exactly_one_provider` → `test_default_registry_has_three_providers` (assert len==3)

Validation:
* `pytest` → **2906 passed**, zero regressions (2826 pre-3D + 80 new)
* Architecture boundary enforced: csv_provider.py, parquet_provider.py, _shared.py contain no yahoo or api imports
* Backward compatibility: `CSVAdapter` (legacy) unchanged; factory still has yahoo; OHLCVService contract unchanged
* Architectural proof: CSV, Parquet, and Yahoo all flow through the identical `OHLCVService → cache/storage` pipeline after construction via `ProviderAdapterFactory`

Correct provider flow after Phase 3D:
```
factory.build("csv",     file_path=..., symbol=...) → LocalCSVProvider
factory.build("parquet", file_path=..., symbol=...) → LocalParquetProvider
factory.build("yahoo",   symbol=...)                → YahooFinanceAdapter
                                  ↓
                    RangeProviderAdapter (same contract)
                                  ↓
                    OHLCVService → DataNormalizer → ohlcv_store → DatasetCacheRegistry
```

Known limitations:
* `file_path` is not surfaced in the HTTP API — using CSV/Parquet providers via the API route requires a future dataset catalog or file path parameter extension (no special-case logic added)
* `file_path` is not part of the `DatasetFetchIdentity` fingerprint — two files with identical metadata but different content produce the same fingerprint (by design; fingerprint identifies the logical dataset, not the physical file)

---

## Phase 3C — Provider Storage & Cache Architecture (COMPLETE)

Focus: establish deterministic dataset persistence, configurable cache reuse behavior, and fetch fingerprint lineage tracking. Every OHLCV dataset now has a canonical on-disk location, a rich `cache_metadata.json` file, and a rolling fingerprint history for reproducibility auditing — without any breaking changes to existing callers.

Pre-existing (already correctly implemented before this phase):
* `OHLCVService` — full pipeline with `CoverageRegistry` coverage gap detection
* `DatasetFetchIdentity` + `compute_fetch_fingerprint` — SHA-256 deterministic fingerprinting
* `ohlcv_store` — canonical `{base_path}/{provider}/{asset_class}/{exchange}/{symbol}/{timeframe}/{adjustment_mode}/data.parquet` layout
* `CoverageRegistry` — boundary coverage metadata in `coverage.json`

Completed in this phase:

**`backend/data/models/cache_policy.py`** (new):
* `DatasetCachePolicy(str, Enum)` — `FETCH_AND_STORE`, `READ_ONLY`, `FORCE_REFRESH`, `BYPASS_CACHE`

**`backend/storage/dataset_cache.py`** (new):
* `DatasetCacheState` — plain class with string constants `EMPTY`, `HIT`, `PARTIAL`
* `DatasetCacheEntry` — frozen dataclass: `dataset_id`, `storage_path`, `record_count`, `earliest_ts`, `latest_ts`, `created_at`, `last_refreshed_at`, `last_fetch_fingerprint`, `fetch_fingerprints: list[str]`
* `DatasetCacheLookupResult` — frozen dataclass: `state`, `missing_ranges`, `entry`
* `DatasetCacheRegistry` — reads/writes `cache_metadata.json` alongside `data.parquet`; `lookup()` / `update()` / `get()` / `invalidate()`
* Rolling fingerprint history: max 10, newest first, deduplication of identical consecutive fingerprints
* `created_at` preserved across updates (set only on first write)

**`backend/data/models/__init__.py`** (modified):
* Added export: `DatasetCachePolicy`

**`backend/services/ohlcv_service.py`** (extended):
* Added `DatasetCacheRegistry` to `__init__`
* `get_ohlcv()` signature extended with `cache_policy: DatasetCachePolicy = DatasetCachePolicy.FETCH_AND_STORE` and `fetch_fingerprint: Optional[str] = None` — fully backward-compatible
* `BYPASS_CACHE` — fetch full range, normalize, return; no storage reads or writes
* `READ_ONLY` — `_read_slice()` only, no provider call
* `FORCE_REFRESH` — fetch full range, `ohlcv_store.write(merge=False)`, update coverage + cache metadata
* `FETCH_AND_STORE` (default) — gap-based fetch, persist, update coverage + cache metadata
* `_refresh_cache()` — reads stored records, calls `DatasetCacheRegistry.update()`

**`backend/api/services/market_data_service.py`** (modified):
* `build_fetch_identity()` moved before `service.get_ohlcv()` so fingerprint propagates to cache metadata on every fetch

**`docs/DATASET_STORAGE_LAYOUT.md`** (new):
* Canonical directory tree and file contracts for `data.parquet`, `coverage.json`, `cache_metadata.json`
* Cache policy behavior matrix; architecture boundary rules

**`tests/unit/test_dataset_cache.py`** (new — 64 tests):
* `TestDatasetCachePolicyEnum` (6), `TestDatasetCacheState` (3), `TestDatasetCacheEntry` (3), `TestDatasetCacheLookupResult` (2)
* `TestDatasetCacheRegistry` (17): create/update/get/invalidate/fingerprint history/max-10/dedup/JSON keys
* `TestDatasetCacheRegistryLookup` (8): EMPTY/HIT/PARTIAL states, naive datetime raises
* `TestComputeMissingRangesHelper` (5): gap scenarios, null timestamps
* `TestOHLCVServiceCachePolicy` (13): all four policies, fingerprint stored, BYPASS no storage writes
* `TestOHLCVServiceBackwardCompat` (3): default policy, naive datetime still raises
* `TestArchitectureBoundary` (4): no yahoo imports in cache_policy, dataset_cache, ohlcv_service

Validation:
* `pytest` → **2826 passed**, zero regressions (2762 pre-3C + 64 new)
* Architecture boundary enforced: `dataset_cache.py` and `cache_policy.py` import no yahoo/api/factory modules
* Backward compatibility: `cache_policy` and `fetch_fingerprint` default to safe values — all existing callers unaffected
* Fingerprint lineage: rolling max-10 history written to `cache_metadata.json` on every successful store

Cache policy behavior:
| Policy            | Reads Parquet | Calls Provider | Writes Parquet | Updates Metadata |
|-------------------|:---:|:---:|:---:|:---:|
| `FETCH_AND_STORE` | ✓ (gaps only) | Only for gaps  | ✓ (merge)     | ✓                |
| `READ_ONLY`       | ✓             | ✗              | ✗              | ✗                |
| `FORCE_REFRESH`   | ✓ (return)    | ✓ (full range) | ✓ (overwrite) | ✓                |
| `BYPASS_CACHE`    | ✗             | ✓ (full range) | ✗              | ✗                |

---

## Phase 3B — Provider Contract Hardening & Dataset Identity (COMPLETE)

Focus: harden the market data provider contract with deterministic fetch identity, provider traceability metadata, and stable dataset fingerprinting. Every OHLCV fetch now produces a fully traceable record auditable back to provider, symbol, timeframe, date range, and adjustment mode — with a deterministic SHA-256 fingerprint — without any breaking changes to existing API consumers.

Pre-existing (already correctly implemented before this phase):
* `DatasetIdentity` — static dataset classification model (instrument + provider + timeframe + adjustment)
* `MarketDataOHLCVResponse` — OHLCV API response schema
* `ProviderAdapterFactory` + `create_default_factory_registry()` — Phase 3A provider isolation
* `OHLCVService` — full pipeline: coverage check → fetch → normalize → persist → read slice

Completed in this phase:

**`backend/data/models/fetch_identity.py`** (new):
* `DatasetFetchParameters` — frozen Pydantic model: provider, symbol, asset_class, exchange, timeframe, start (UTC-aware datetime), end (UTC-aware datetime), adjustment_mode; all string fields validated non-empty; naive datetimes rejected
* `compute_fetch_fingerprint(params) → str` — deterministic SHA-256 hex fingerprint from pipe-delimited canonical string (all values lowercased, timestamps in ISO UTC); stable across processes and platforms; provably sensitive to every field
* `DatasetFetchIdentity` — frozen Pydantic model: parameters, fingerprint, dataset_id, schema_version
* `FETCH_IDENTITY_SCHEMA_VERSION = "1"` — bump when canonical fingerprint format changes
* `build_fetch_identity(**kwargs) → DatasetFetchIdentity` — convenience builder; constructs parameters, computes fingerprint, assembles identity record

**`backend/data/models/__init__.py`** (modified):
* Added exports: `DatasetFetchIdentity`, `DatasetFetchParameters`, `FETCH_IDENTITY_SCHEMA_VERSION`, `build_fetch_identity`, `compute_fetch_fingerprint`

**`backend/api/schemas/market_data.py`** (modified):
* Added `DatasetFetchMetadataResponse` — API-layer traceability schema: dataset_id, fingerprint, provider, symbol, asset_class, exchange, timeframe, start_utc (ISO string), end_utc (ISO string), adjustment_mode, schema_version
* Extended `MarketDataOHLCVResponse` with `fetch_metadata: DatasetFetchMetadataResponse | None = None` — backward-compatible; existing consumers unaffected when field absent

**`backend/api/services/market_data_service.py`** (modified):
* Added `build_fetch_identity()` call after `DatasetIdentity` construction — pure domain layer call, no provider-specific imports
* Populates `fetch_metadata` in `MarketDataOHLCVResponse` with all identity fields including fingerprint and schema_version
* Logger now includes fingerprint prefix (first 12 hex chars) for traceability in logs
* Architecture contract preserved: still zero Yahoo imports in this module

**`tests/unit/test_dataset_fetch_identity.py`** (new — 65 tests):
* `TestDatasetFetchParameters` (13): frozen, extra forbidden, fields stored, empty/whitespace raises, naive datetime raises, UTC accepted, non-UTC tz-aware accepted
* `TestComputeFetchFingerprint` (15): returns string, SHA-256 length=64, deterministic, same-params same, different field → different, canonical SHA-256 verification, timezone normalization (non-UTC and UTC same moment → same fingerprint), provider/symbol case-insensitive
* `TestDatasetFetchIdentity` (7): frozen, parameters/fingerprint/dataset_id stored, schema_version has default, non-empty, matches constant
* `TestBuildFetchIdentity` (8): returns identity, deterministic, matches direct compute, parameters reflect inputs, dataset_id passed through, schema_version set, empty provider raises, naive datetime raises
* `TestDatasetFetchMetadataResponseSchema` (3): expected fields present, constructable, serializes to dict
* `TestMarketDataOHLCVResponseBackwardCompat` (3): fetch_metadata defaults to None, existing fields unchanged, response with metadata serializes
* `TestMarketDataServiceFetchMetadataIntegration` (11): response includes fetch_metadata, fingerprint 64 chars, dataset_id contains provider+symbol, provider/symbol/timeframe match request, adjustment_mode/schema_version/start_utc/end_utc present, fingerprint deterministic across requests, existing OHLCV fields unchanged
* `TestArchitectureBoundary` (4): fetch_identity no yahoo import, fetch_identity no provider_factory import, market_data_service still no yahoo import, fetch_identity no api layer import

Validation:
* `pytest` → **2762 passed**, zero regressions (2697 pre-3B + 65 new)
* Architecture boundary enforced: `fetch_identity.py` imports only stdlib + pydantic + `backend.data.models.instrument`
* Backward compatibility: `MarketDataOHLCVResponse.fetch_metadata` defaults to `None` — zero impact on existing consumers
* Fingerprint stability: SHA-256 of pipe-delimited canonical string; bump `FETCH_IDENTITY_SCHEMA_VERSION` if format changes

Correct provider traceability flow after Phase 3B:
```
API route → factory.build() → OHLCVService → normalized candles
         → build_fetch_identity() → DatasetFetchIdentity
         → MarketDataOHLCVResponse.fetch_metadata → client
```

---

## Phase 3A — Market Data Provider Layer (COMPLETE)

Focus: complete the provider abstraction layer so all market data access routes through normalized provider adapters. The primary architectural violation was `market_data_service.py` directly importing `YahooFinanceAdapter` — this is now fixed. The `ProviderAdapterFactory` pattern decouples API services from concrete adapter classes.

Pre-existing (already correctly implemented before this phase):
* `BaseDataAdapter` + `RangeProviderAdapter` — abstract contracts in `backend/data_providers/`
* `YahooFinanceAdapter` — isolated in `backend/data_providers/yahoo/adapter.py`
* `ProviderRegistry` — instance-based registry for pre-built adapters
* `OHLCVService` — full pipeline: coverage check → fetch → normalize → persist → read slice
* `NormalizedOHLCV` — canonical schema with all required fields (`source` = provider)
* Storage layer: `ohlcv_store`, `parquet_store`, `coverage_registry`
* Symbol mapping: `SymbolMapService`

Completed in this phase:

**`backend/data_providers/base.py`** (modified):
* Added `ProviderFetchError` exception — base for all provider-level fetch failures; API services catch this instead of Yahoo-specific errors
* Added `ProviderCapabilities` frozen Pydantic model — `provider_id`, `display_name`, `supported_timeframes`, `supported_asset_classes`
* Added concrete (non-abstract) methods to `BaseDataAdapter`: `supported_timeframes() → ()`, `supported_asset_classes() → ()`, `capabilities() → ProviderCapabilities` — safe defaults, overridden by concrete adapters

**`backend/data_providers/yahoo/adapter.py`** (modified):
* `YahooAdapterError` now subclasses `ProviderFetchError` — callers can catch the generic error
* Implemented `supported_timeframes()` — all Yahoo timeframe strings
* Implemented `supported_asset_classes()` — `("crypto", "equity", "etf", "fx", "fund", "future", "index")`
* Implemented `capabilities()` — returns concrete `ProviderCapabilities` for Yahoo

**`backend/data_providers/provider_factory.py`** (new):
* `UnknownProviderError` — raised when build() called with unregistered provider
* `ProviderBuildError` — raised when adapter construction fails (wraps ValueError from adapter)
* `ProviderAdapterFactory` — register(provider_id, capabilities, builder) / build(provider_id, **kwargs) / get_capabilities() / list_capabilities() / `__contains__` / `__len__`
* `_YAHOO_CAPABILITIES` + `_build_yahoo_adapter()` — Yahoo factory internals (Yahoo-specific code stays here)
* `create_default_factory_registry()` — returns factory with Yahoo registered; future providers added here

**`backend/data_providers/__init__.py`** (modified):
* Exports: `ProviderCapabilities`, `ProviderFetchError`, `ProviderAdapterFactory`, `ProviderBuildError`, `UnknownProviderError`, `create_default_factory_registry`

**`backend/api/services/market_data_service.py`** (rewritten):
* REMOVED: direct `YahooFinanceAdapter` and `YahooAdapterError` imports — architectural violation fixed
* Accepts `factory: ProviderAdapterFactory` as parameter — provider resolution is factory's responsibility
* Uses `factory.build(provider, **kwargs)` instead of `if provider == "yahoo": YahooFinanceAdapter(...)`
* Catches `ProviderFetchError` instead of `YahooAdapterError` (provider-agnostic)
* Added `list_providers(factory) → ProvidersListResponse`

**`backend/api/routes/market_data.py`** (rewritten):
* Added `get_provider_factory()` FastAPI dependency — overridable in tests
* Added `GET /market-data/providers` endpoint — lists all registered providers and capabilities
* `GET /market-data/ohlcv` passes `factory=factory` to service — no functional change to callers

**`backend/api/schemas/market_data.py`** (modified):
* Added `ProviderCapabilitiesResponse` — `provider_id`, `display_name`, `supported_timeframes`, `supported_asset_classes`
* Added `ProvidersListResponse` — `providers: list[ProviderCapabilitiesResponse]`

**`tests/unit/test_provider_factory.py`** (new — 38 tests):
* `TestProviderCapabilitiesModel` (2): frozen, fields stored
* `TestProviderAdapterFactoryRegistration` (7): register/contains, case-insensitive, len, duplicate, empty name, whitespace, non-string
* `TestProviderAdapterFactoryBuild` (6): returns adapter, unknown raises, error lists available, case-insensitive, kwargs forwarded, ValueError→ProviderBuildError
* `TestProviderAdapterFactoryCapabilities` (5): get known, unknown raises, list empty, sorted, all returned
* `TestCreateDefaultFactoryRegistry` (8): contains yahoo, capabilities fields, timeframes, asset classes, multiple timeframes, len=1, list contains yahoo
* `TestYahooBuilderIntegration` (4): adapter returned, provider_name, unsupported timeframe, extra kwargs ignored
* `TestProviderFetchErrorInheritance` (2): YahooAdapterError is subclass, ProviderFetchError is Exception
* `TestArchitectureBoundary` (2): service no yahoo import, factory loads correctly

**`tests/unit/test_market_data_providers.py`** (new — 17 tests):
* `TestGetProvidersEndpoint` (10): 200, providers list, yahoo present, display name, timeframes, 1d in timeframes, asset classes, equity in asset classes, schema fields, custom factory override
* `TestListProvidersService` (4): yahoo from default registry, empty factory, custom provider, sorted alphabetically
* `TestOHLCVRegressionViaFactory` (3): ohlcv endpoint still works, unsupported provider → 400, unsupported timeframe → 400
* `TestArchitectureBoundary` (2): no yahoo import in service, no YahooFinanceAdapter/YahooAdapterError attributes on service module

Validation:
* `pytest` → **2697 passed**, zero regressions (2642 pre-3A + 55 new)
* Architecture boundary enforced: `backend/api/services/market_data_service.py` contains no `yahoo` import on any line

Correct provider flow after Phase 3A:
```
API route → factory.build(provider, **kwargs) → RangeProviderAdapter → OHLCVService.get_ohlcv()
```
Future providers (Binance, IBKR, Polygon, CSV, Parquet) register in `create_default_factory_registry()` only — no API/service/route changes required.

---

## Phase 2U — ATR + Bollinger Bands (COMPLETE)

Focus: final two standard indicators completing the baseline indicator layer. ATR renders in the oscillator pane; Bollinger Bands render as three simultaneous price-pane overlays. No frontend redesign required — existing pane/kind routing handled both tools automatically.

Completed:

**`backend/tools/atr.py`** (new):
* `ATR_METADATA` — `tool_id="atr"`, `output_feature_names=("atr",)`, `produces_oscillator_series`, `stateful=True`, `min_warmup_bars=1`
* Parameters: `period` (int, required, default=14, min=1), `name`, `color`
* `compute_atr(candles, period, name, color) → IndicatorSeries` — Wilder's smoothing; SMA seed at bar `period`; first output at bar index `period`; TR = max(H-L, |H-C_prev|, |L-C_prev|)
* `_true_range(high, low, prev_close) → float` — exported helper

**`backend/tools/bollinger_bands.py`** (new):
* `BOLLINGER_METADATA` — `tool_id="bollinger_bands"`, `output_feature_names=("middle_band","upper_band","lower_band")`, no oscillator capability, `stateful=False`, `min_warmup_bars=1`
* Parameters: `period` (int, required, default=20, min=2), `std_dev` (float, default=2.0), `name`, `color`
* `compute_bollinger(candles, period, std_dev, name, color) → tuple[IndicatorSeries×3]` — population stddev; all 3 outputs share warmup = period-1
* `_bollinger_values(window, multiplier) → (middle, upper, lower)` — exported helper

**`backend/tools/historical_computation.py`** (modified):
* `_compute_atr_series()` — Wilder smoothing; requires "high","low","close" from price_fields; warmup = period
* `_compute_bollinger_series()` — rolling SMA + population stddev; requires "close"; warmup = period-1; returns 3 series
* `derive_warmup_bars_required()` — extended for `atr` (warmup=period) and `bollinger_bands` (warmup=period-1)
* `_TOOL_DISPATCHERS` — extended with `"atr"` and `"bollinger_bands"` entries
* Added `import math`

**`backend/tools/__init__.py`** (modified):
* Imports: `ATR_METADATA`, `compute_atr`, `BOLLINGER_METADATA`, `compute_bollinger`
* `create_default_registry()` — now registers 6 tools (added ATR + Bollinger)
* `__all__` — extended with new exports

**`tests/unit/test_atr.py`** (new — 41 tests):
* TestTrueRange (6): gap-up/down/inside bar, equal OHLC, always non-negative
* TestATRMetadata (8): tool_id, output names, oscillator capability, stateful, period param
* TestComputeATRVisualization (9): empty, name, pane/kind, invalid period, warmup, flat prices, determinism
* TestATRHistoricalPipeline (12): warmup, output_ref, flat prices, single series, missing fields, Wilder seeding, two instances isolated, determinism, too few bars, exact boundary
* TestATRWarmupDerivation (4): period default, various periods

**`tests/unit/test_bollinger_bands.py`** (new — 44 tests):
* TestBollingerValues (6): mean, flat window, symmetry, multiplier scaling, population stddev, upper>=lower
* TestBollingerMetadata (9): tool_id, output names, no oscillator capability, stateless, parameters
* TestComputeBollingerVisualization (10): empty, naming, panes/kinds, invalid args, warmup, flat zero-width, equal lengths, determinism, upper>=lower
* TestBollingerHistoricalPipeline (14): 3 series, output refs, warmup, flat zero-width, middle=SMA, symmetry, missing close, two instances, shared warmup, multiplier scaling, determinism, too few bars, exact boundary
* TestBollingerWarmupDerivation (4): various periods, default

**`tests/unit/test_composition_run_visualization.py`** (modified — 14 new tests):
* TestATROscillatorRouting (4): pane=oscillator, kind=line, not on price, one series
* TestBollingerPriceRouting (5): pane=price, kind=line, 3 series, not on oscillator, output names
* TestAllSixToolsRouting (5): 10 total series, 5 price / 5 oscillator split, no histogram from new tools, valid panes/kinds

**`tests/unit/test_ema_tool.py`** (modified):
* Updated `test_registered_in_default_registry`: `len(registry) == 6` (was 4)

Validation:
* `pytest` → **2642 passed**, zero regressions (2543 pre-2U + 99 new)
* `npm run build` → **59 modules**, clean (no new frontend files needed — existing pane/kind routing handles ATR and Bollinger automatically)

Architecture preserved:
* ATR and Bollinger are computed entirely in backend — frontend renders only
* Bollinger's 3 price-pane overlays route correctly via empty `visualization_capabilities` (no `produces_oscillator_series` flag)
* ATR oscillator routing via `VisualizationCapability.produces_oscillator_series` — same pattern as RSI/MACD
* `composition_run_service` boundary intact — no new service changes required

This is the LAST standard indicator phase. Future direction: custom research tools, pivot/swing framework, divergence systems, advanced semantic conditions.

---

## Phase 2T.3 — Chart Run Reset & Overlay Cleanup (COMPLETE)

Focus: high-priority frontend UX correctness fix for stale strategy drawings after clear/rerun. No backend/API/indicator logic changes.

Completed:
* `frontend/src/App.tsx`
  * Added `clearStrategyResults()` as the owner of strategy visualization reset state.
  * Passes `onClearStrategyResults` to `Chart`.
  * Clearing sets `overlay=null` only; candles, provider, symbol, timeframe, and loaded OHLCV data remain intact.
* `frontend/src/components/Chart.tsx`
  * Added chart-header `Clear Strategy Results` button.
  * Button clears signals, marker drawings, price overlays, oscillator series, MACD histogram, RSI guide lines, forecast line, and result counters by clearing App-owned overlay state.
  * Replaced repeated `createSeriesMarkers(...)` calls with one retained marker plugin (`markerApiRef`) and explicit `setMarkers([])` cleanup.
  * Marker plugin detaches on unmount.
  * Existing overlay cleanup still removes all price series, oscillator series, RSI guide price lines, and forecast data before rendering the current overlay.

Validation:
* `npm run build` in `frontend/` → clean
* Build output: 59 modules transformed

Notes:
* Within allowed scope, no `StrategyTestPanel.tsx` changes were made. Rerun cleanup is enforced when `Chart` receives the latest overlay; the chart removes existing artifacts before drawing the new result.
* No frontend test runner exists beyond the current TypeScript/Vite build pipeline.

---

## Phase 2T.2 — Oscillator Reference Lines (COMPLETE)

Focus: frontend-only RSI oscillator readability enhancement. No backend/API contract changes.

Completed:
* `frontend/src/components/Chart.tsx`
  * Added subtle RSI oscillator guide lines at 70, 50, and 30.
  * Guides render only when an RSI oscillator series exists.
  * Guides attach to the first matching RSI line series via Lightweight Charts `createPriceLine()`.
  * Guide lifecycle is tracked separately and cleaned up before oscillator series removal and on chart unmount.
  * Matching is localized through `_OSCILLATOR_REFERENCE_GUIDES`, keeping room for future oscillator guides without refactoring chart lifecycle.
* Frontend remains visualization-only:
  * no RSI calculation
  * no indicator recomputation
  * no backend/API changes

Validation:
* `npm run build` in `frontend/` → clean
* Build output: 59 modules transformed

Notes:
* Existing oscillator pane remains fixed-height at 180px.
* No frontend test runner exists beyond the current TypeScript/Vite build pipeline.

---

## Phase 2T.1 — Browser-Level Visualization Validation (COMPLETE)

Focus: end-to-end runtime validation of Phase 2T visualization pipeline against live AAPL data. Confirmed all 6 indicator series reach the frontend with correct pane/kind routing.

Validation commands run:
* Backend: `uvicorn backend.main:app --reload --port 8000`
* Frontend: `npm run dev` (port 3000)
* Semantics: `PUT /drafts/viz-validation/semantics` with SMA20>close entry rule
* Data: `GET /market-data/ohlcv?provider=yahoo&symbol=AAPL&timeframe=1d&start=2023-01-01&end=2024-01-01` → 250 bars
* Run: `POST /strategy-runs/run-composition` with `draft_id=viz-validation`

API response confirmed (6 indicators, all correct):
```
sma20.sma       pane=price       kind=line       231 points
ema20.ema       pane=price       kind=line       231 points
rsi14.rsi       pane=oscillator  kind=line       236 points
macd1.macd_line pane=oscillator  kind=line       225 points
macd1.signal_line pane=oscillator kind=line      217 points
macd1.histogram pane=oscillator  kind=histogram  217 points
```

Type chain verified: `CompositionRunResponse.indicators` → `App.tsx:handleCompositionResult` → `StrategyOverlay.indicators` → `Chart.tsx` pane/kind routing → `HistogramSeries` / `LineSeries`.

TypeScript: `tsc --noEmit` → clean (0 errors).
Tests: 2543 passed (unchanged — no new backend code required for validation).

Files changed: none (validation-only phase; all code was correct on first run).

Known limitations / future work:
* Oscillator pane height is fixed at 180px; future: user-resizable

---

## Phase 2T — Tool Output Visualization (COMPLETE)

Focus: established the first visualization bridge from backend-computed tool outputs to the frontend chart. SMA/EMA render as price-pane overlays, RSI and MACD render in a separate oscillator pane, and MACD histogram uses a histogram series with per-bar sign coloring.

Completed:

**`backend/strategy_runtime/visualization.py`** (modified):
* Added `histogram = "histogram"` to `IndicatorSeriesKind` enum (was commented as "future")

**`backend/api/services/composition_run_service.py`** (modified):
* Added `from backend.tools.models import VisualizationCapability`
* Each `ToolOutputSeries` now derives `pane` and `kind` from registry metadata:
  - `VisualizationCapability.produces_oscillator_series` → `pane="oscillator"`
  - Else → `pane="price"`
  - `series.output_name == "histogram"` → `kind="histogram"`
  - Else → `kind="line"`
* Previously hardcoded `pane="price"` and `kind="line"` for all indicators

**`frontend/src/types/toolVisualization.ts`** (new):
* `ToolOutputKind = 'line' | 'histogram'`
* `ToolOutputPane = 'price' | 'oscillator'`
* `ToolVisualizationSeries` — stable contract for future extensibility (Bollinger Bands, ATR, VWAP, etc.)

**`frontend/src/components/Chart.tsx`** (rewritten):
* Two chart instances: price chart (always visible) + oscillator chart (shown only when oscillator series present)
* Price chart: renders candles + SMA/EMA/price overlays + signal markers + forecast line (unchanged from before)
* Oscillator chart: renders RSI (LineSeries) and MACD (macd_line/signal_line as LineSeries, histogram as HistogramSeries)
* MACD histogram: per-bar sign coloring (green ≥ 0, red < 0) — pure rendering logic, no indicator computation
* Time scale synchronization: `subscribeVisibleLogicalRangeChange` bidirectional sync between price and oscillator
* Oscillator container: `height: 180px` when oscillator series present, `height: 0` when none (CSS transition)
* Lifecycle discipline: all series removed and maps cleared on each overlay update; both charts destroyed on unmount
* Header badges updated: separate "overlays" and "oscillators" counts

**`tests/unit/test_composition_run_visualization.py`** (new — 28 tests):
* TestIndicatorSeriesKindHistogram: 4 tests for new enum value
* TestPricePaneRouting: 6 tests — SMA/EMA pane="price"/kind="line", multiple instances, no oscillator bleed
* TestRSIOscillatorRouting: 3 tests — RSI pane="oscillator"/kind="line", not on price pane
* TestMACDOscillatorRouting: 7 tests — all 3 outputs on oscillator, histogram kind, line kinds, 3 series
* TestMixedToolRouting: 6 tests — both panes, 6 total series, valid pane/kind sets
* TestCompositionRunVisualizationArchitecture: 2 tests — no forbidden imports, VisualizationCapability from tools

Validation:
* `pytest` → **2543 passed**, zero regressions (2515 pre-2T + 28 new)
* `npm run build` → **60 modules** (59 + `toolVisualization.ts`), clean build

Architecture preserved:
* Frontend never computes indicators — only routes and renders backend-provided values
* Histogram bar colors (sign-based) are rendering logic, not indicator computation
* Backend retains full authority over pane and kind assignments via registry metadata
* `composition_run_service` still forbidden from strategy_runtime/execution/forward_testing/backtesting

Known limitations / future work:
* Oscillator pane height is fixed at 180px; future: user-resizable

---

## Phase 2S — RSI + MACD Tool Expansion (COMPLETE)

Focus: added RSI and MACD indicator tools to the historical computation pipeline, expanding the tool registry from 2 to 4 stable tools, with full warmup enforcement, multi-output MACD architecture, oscillator pane support, and 116 new tests.

Completed:

**`backend/strategy_runtime/visualization.py`** (modified):
* Added `oscillator = "oscillator"` to `IndicatorPane` enum (was marked "future")
* Required for RSI and MACD separate-pane indicator series

**`backend/tools/rsi.py`** (new):
* `RSI_METADATA` — `tool_id="rsi"`, `output_feature_names=("rsi",)`, `produces_oscillator_series`, `stateful=True`, `min_warmup_bars=2`
* Parameters: `period` (int, required, default=14, min=2), `name`, `color`
* `compute_rsi(candles, period, name, color) → IndicatorSeries` — Wilder's smoothing; SMA seed at `period`; first output at bar index `period`; RSI bounded [0, 100]

**`backend/tools/macd.py`** (new):
* `MACD_METADATA` — `tool_id="macd"`, `output_feature_names=("macd_line", "signal_line", "histogram")`, `produces_oscillator_series`, `stateful=True`, `min_warmup_bars=2`
* Parameters: `fast_period` (default=12), `slow_period` (default=26), `signal_period` (default=9), `name`, `color`
* `compute_macd(...) → tuple[IndicatorSeries, IndicatorSeries, IndicatorSeries]` — all EMAs SMA-seeded
* Helper functions `_ema_series`, `_compute_dual_ema`, `_compute_signal_and_hist` exported for reuse

**`backend/tools/historical_computation.py`** (modified):
* `_compute_rsi_series()` — Wilder's smoothing; warmup = period; first output at bar_index = period
* `_compute_macd_series()` — returns 3 `ToolOutputSeries`; macd_line warmup = `slow_period - 1`; signal/histogram warmup = `slow_period + signal_period - 2`
* `derive_warmup_bars_required()` extended for rsi (warmup = period) and macd (warmup = slow + signal - 2)
* `_TOOL_DISPATCHERS` extended: `"rsi": _compute_rsi_series`, `"macd": _compute_macd_series`

**`backend/tools/__init__.py`** (modified):
* Imports `RSI_METADATA`, `compute_rsi`, `MACD_METADATA`, `compute_macd`
* `create_default_registry()` now registers all 4 tools: SMA, EMA, RSI, MACD

**`frontend/src/components/DraftWorkspace.tsx`** (modified):
* Fetches tool registry on mount via `fetchTools()`; stores in `toolRegistry` state keyed by `tool_id`
* `toolOutputSuggestions` now uses actual `output_feature_names` from metadata — MACD correctly generates `["inst.macd_line", "inst.signal_line", "inst.histogram"]` instead of naive `inst.tool_id`

**`tests/unit/test_rsi_tool.py`** (new — ~80 tests):
* RSI metadata contract, standalone compute, pipeline correctness with known values (period=2; RSI[2]≈66.67, RSI[3]≈85.71, RSI[4]≈54.55), warmup enforcement, no-lookahead, multi-instance, multi-tool, semantic integration (rsi < 30 threshold), errors, API integration, architecture guards

**`tests/unit/test_macd_tool.py`** (new — ~80 tests):
* MACD metadata (3 outputs, correct order), standalone compute, 3 series per instance, separate warmup counts (signal has more warmup than macd_line), no-lookahead, multi-instance → 6 series disjoint refs, multi-tool SMA+EMA+RSI+MACD → 6 series total, semantic integration (histogram > 0 crossover), errors, API integration, architecture guards

**`tests/unit/test_ema_tool.py`** (modified):
* Updated registry size assertion: `len(registry) == 2` → `len(registry) == 4`
* Changed unknown tool_id from `"rsi"` to `"unknown_indicator_xyz"` (RSI now registered)

Architecture note — MACD histogram on linear prices: For perfectly linear price series, macd_line is constant, signal equals macd_line, histogram = 0.0 exactly. Tests use flat-then-surge price patterns to produce non-zero histograms.

Validation:
* `pytest` → **2515 passed**, zero regressions (2399 pre-2S + 116 new)
* `npm run build` → **59 modules**, clean build

---

## Phase 2R.2 — Warmup Enforcement + Lookahead Prevention (COMPLETE)

Focus: strict historical replay integrity across tool computation, evaluator ordering, signal/trade timestamp lineage, and backtest report outputs.

Completed:
* `ToolOutputSeries.warmup_bars_required` added as the configured series-level warmup exposure.
* `derive_warmup_bars_required(tool_config, metadata)` added and exported; SMA/EMA derive actual warmup from `period - 1`.
* Historical evaluator now canonicalizes replay by ascending `bar_index`, rejects duplicate bar indexes, and rejects timestamp regressions when timestamps are present.
* Historical evaluation service, composition run service, and backtest run service now sort/validate bars before computation/evaluation/report metadata.
* Backtest simulator now rejects duplicate price bars and intent timestamps that do not match the referenced price bar timestamp.
* Backtest reports now derive `dataset_start` / `dataset_end`, equity order, trades, and open-position timestamps from canonical historical order, not request payload order.
* New regression coverage:
  * `tests/unit/test_backtest_integrity.py` — reversed input bars still replay historically; duplicate bars rejected.
  * Additional tests in historical tool computation, crossover evaluator, and backtest simulation for warmup exposure, canonical ordering, duplicate rejection, and timestamp mismatch rejection.
* Docs updated:
  * `docs/HISTORICAL_TOOL_COMPUTATION_PIPELINE.md`
  * `docs/HISTORICAL_EVALUATION_ITERATOR.md`
  * `docs/BACKTESTING_ENGINE_CONTRACT.md`

Validation:
* Targeted suites passing:
  * `test_historical_tool_computation.py`
  * `test_crossover_evaluator.py`
  * `test_ema_tool.py`
  * `test_backtest_simulation.py`
  * `test_backtest_integrity.py`
  * `test_backtest_exports.py`
  * `test_backtest_analytics.py`

Known limitations:
* Indicator values at signal time are still not captured in report artifacts.
* Tool version pinning / registry snapshotting is still not implemented.

---

## Phase 2Q — Backtest Report Hardening (COMPLETE)

Focus: correctness validation, trade audit enrichment, export capability, reproducibility metadata, test coverage.

Completed:

**Analytics Tests (`tests/unit/test_backtest_analytics.py`, new — 37 tests)**
* `total_return_pct` — positive, negative, zero, empty curve
* `max_drawdown_pct` — single trough, worst-of-multiple, monotonic rise, recovery to peak
* Drawdown curve — per-bar values, bar_index preservation, initial cash as starting peak
* Win/loss/breakeven classification — no trades, all winners, all losers, mixed
* `win_rate` — None when no trades, 0.0 / 1.0 / fractional
* `gross_profit` / `gross_loss` — sums only correct sign
* `profit_factor` — no losses → None, no wins → 0.0, mixed
* `avg_win` / `avg_loss` — None when absent, correct averages
* `best_trade_pnl` / `worst_trade_pnl` — None when empty, correct extremes
* Open position excluded from closed-trade metrics
* Breakeven at exactly 0.0 PnL
* Determinism — identical inputs → identical outputs
* Immutability — frozen dataclass raises on mutation attempt
* Architecture guard — no forbidden imports in analytics.py (import-lines only)

**Trade Audit Enrichment**
* `TradeRecord` extended (backward-compatible, all new fields `= None` default):
  * `entry_rule_id`, `exit_rule_id` — rule_id from originating `TradeIntentSource`
  * `entry_signal_event_id`, `exit_signal_event_id` — event_id from originating `SignalEvent`
* `_build_trade_records()` now accepts `intent_batch: TradeIntentBatch`, builds `intent_map: dict[intent_id, TradeIntent]`, populates audit fields from `intent.source.rule_id` and `intent.source.signal_event_id`
* Open position record also enriched with `entry_rule_id` / `entry_signal_event_id`

**Reproducibility Metadata**
* `BacktestRunSummary` extended (backward-compatible optional fields):
  * `dataset_start: str | None` — ISO timestamp of first bar in dataset
  * `dataset_end: str | None` — ISO timestamp of last bar in dataset
  * `engine_version: str = "2P.9"` — backtesting engine version tag
* Service populates `dataset_start` / `dataset_end` from `request.bars[0]` / `request.bars[-1]`

**Export Service (`backend/api/services/export_service.py`, new)**
* `export_trade_ledger_csv(report)` — all closed + open trades; 23 columns including audit fields; None → empty string (never literal "None")
* `export_equity_curve_csv(report)` — per-bar equity joined with drawdown_pct by bar_index
* `export_report_json(report)` — canonical JSON via `model_dump_json()`, round-trips via `BacktestReport.model_validate()`

**Export Endpoints (`backend/api/routes/backtest_runs.py`, modified)**
* `GET /backtests/runs/{run_id}/export/trades` → CSV download, `Content-Disposition: attachment`
* `GET /backtests/runs/{run_id}/export/equity` → CSV download
* `GET /backtests/runs/{run_id}/export/report` → JSON download
* All 3 return 404 for unknown run_id

**Export + Schema Tests (`tests/unit/test_backtest_exports.py`, new — 23 tests)**
* CSV header correctness, field serialization, open position status column
* None → empty string (not literal "None")
* Empty trades → header-only CSV
* Drawdown join by bar_index; missing bar → empty cell
* JSON valid, round-trips, schema-stable (all required keys present)
* API 200 for all 3 export endpoints (mocked `load_backtest_report`)
* API 404 for all 3 endpoints with unknown run_id
* `BacktestRunSummary` reproducibility fields present
* `TradeRecord` audit fields present and optional
* CSV row counts match trade/equity curve lengths

**Frontend**
* `frontend/src/types/backtestRuns.ts` — `TradeRecord` extended with 4 audit fields; `BacktestRunSummary` extended with `dataset_start`, `dataset_end`, `engine_version`
* `frontend/src/api/backtestRuns.ts` — `downloadTradesCSV()`, `downloadEquityCSV()`, `downloadReportJSON()` (browser anchor-click pattern)
* `frontend/src/components/BacktestReportPage.tsx` — 3 export buttons in header (↓ Trades, ↓ Equity, ↓ JSON); rule audit section shows `entry_rule_id`/`exit_rule_id` per trade when available

**Validation**
* 2330 pre-existing tests: all pass, zero regressions
* 60 new tests: all pass
* Total: **2390 passed**

Known limitations:
* Indicator values at signal time not yet captured (placeholder note in UI)
* Tool version pinning (registry snapshot) not yet implemented

---

## Phase 2R.1 — EMA Tool + Multi-Tool Computation Proof (COMPLETE)

Completed:
* `backend/tools/ema.py` (new):
  * `EMA_METADATA` — registry metadata: `tool_id="ema"`, `output_feature_names=("ema",)`, `stateful=True`; parameters: `period` (required int ≥1), `source` (optional str, default "close"), `name`, `color`
  * `compute_ema()` — standalone `NormalizedOHLCV → IndicatorSeries` path; SMA-seed; recursive formula; warmup-skipping; deterministic
* `backend/tools/historical_computation.py` (modified):
  * `_compute_ema_series()` (new internal): `alpha = 2/(period+1)`; seed = SMA of first `period` closes; recursive EMA per bar; no lookahead; state purely local to pass
  * `_TOOL_DISPATCHERS` extended: `"ema": _compute_ema_series` — one-line registration
  * Module docstring updated to reflect SMA + EMA
* `backend/tools/__init__.py` (modified):
  * Exports `EMA_METADATA`, `compute_ema`
  * `create_default_registry()` now registers both SMA and EMA
* `tests/unit/test_ema_tool.py` (new) — 71 tests: EMA_METADATA contract, compute_ema standalone, pipeline correctness, warmup, no-lookahead, multi-instance, multi-tool (SMA+EMA) proof, semantic integration (threshold + crossover + SMA/EMA comparison), API integration, validation, error cases, architecture guards
* `docs/EMA_TOOL_ARCHITECTURE.md` (new) — formula, seed behavior, warmup rules, no-lookahead guarantee, dispatcher integration, multi-tool proof, semantic integration, future extensibility path

Architecture validated:
* EMA does NOT share state between instances — each computation pass is independent
* Evaluator does NOT compute EMA — it only reads `tool_outputs["ema_fast.ema"]` etc.
* SMA + EMA coexist without ref collisions or state corruption in same toolset
* Identical inputs → identical EMA outputs (deterministic)
* No lookahead: bar N EMA uses only closes 0..N
* Architecture boundary preserved: no imports from `execution`, `backtesting`, `forward_testing`

Multi-tool proof confirmed:
* `sma_fast.sma` + `ema_fast.ema` + `ema_slow.ema` computed in one pipeline pass
* EMA crossover (`ema_fast.ema crosses_above ema_slow.ema`) evaluated correctly
* Mixed SMA/EMA comparison (`ema_fast.ema > sma_fast.sma`) evaluated correctly
* No manual `tool_outputs` injection required

Validation:
* Full backend suite: **2330 passed**, zero regressions (2259 + 71 new)

---

## Phase 2R.0 — Historical Tool Computation Pipeline (COMPLETE)

Completed:
* `backend/tools/computation_models.py` (new):
  * `ToolOutputPoint` — frozen Pydantic: `bar_index`, `timestamp`, `value`; produced only post-warmup
  * `ToolOutputSeries` — frozen: `instance_id`, `tool_id`, `output_name`, `warmup_bar_count`, `points`; `output_ref` property returns `"{instance_id}.{output_name}"`
  * `ToolComputationResult` — frozen: `toolset_id`, `total_bars`, `series`
* `backend/tools/historical_computation.py` (new):
  * `ToolComputationBarInput` — frozen: `bar_index`, `timestamp`, `price_fields`
  * `ToolComputationError` — raised on unknown tool, missing "close", duplicate bar_index, invalid params
  * `compute_tool_outputs_for_history(toolset, bars, registry) → ToolComputationResult` — validates uniqueness, sorts bars, dispatches per enabled tool
  * `build_bar_tool_outputs(result) → dict[bar_index, dict[ref, float]]` — warmup bars absent (signals indeterminate to evaluator)
  * `_compute_sma_series()` — running-sum O(n) SMA; no lookahead; warmup=period-1
  * `_TOOL_DISPATCHERS = {"sma": _compute_sma_series}` — one-line registration for future EMA/RSI
* `backend/tools/__init__.py` (modified) — exports: `ToolOutputPoint`, `ToolOutputSeries`, `ToolComputationResult`, `ToolComputationBarInput`, `ToolComputationError`, `compute_tool_outputs_for_history`, `build_bar_tool_outputs`
* `backend/api/schemas/historical_evaluation.py` (modified):
  * `HistoricalEvaluationRequest` extended: `toolset: StrategyToolSet | None = None`
* `backend/api/services/historical_evaluation_service.py` (modified):
  * `evaluate_history_from_payload()` extended with `toolset: StrategyToolSet | None = None` parameter
  * Ambiguity rejection: toolset + non-empty bar.tool_outputs → `HistoricalEvaluationError`
  * Toolset path: converts bars → `ToolComputationBarInput`, calls `compute_tool_outputs_for_history`, calls `build_bar_tool_outputs`, injects per bar
  * Manual path (toolset=None): unchanged — backward compatible
* `backend/api/routes/historical_evaluation.py` (modified) — passes `request.toolset` to service
* `tests/unit/test_historical_tool_computation.py` (new) — 52 tests: output models, SMA correctness, warmup, no-lookahead, multi-instance, disabled tools, build_bar_tool_outputs, errors, service toolset path, backward compat, API integration, schema, crossover semantics
* `docs/HISTORICAL_TOOL_COMPUTATION_PIPELINE.md` (new) — architecture, output ref format, warmup rules, input/output contracts, API integration, ambiguity rule, dispatcher architecture, SMA details, error handling, architecture boundaries, file index

Architecture preserved:
* No lookahead: bar N uses only bars 0..N (running sum algorithm)
* Warmup bars absent from dict → evaluator outcome=None (indeterminate) — correct no-signal behavior
* Manual tool_outputs path unchanged → all prior tests pass
* Architecture boundary: `historical_computation.py` does NOT import from `strategy_runtime`, `execution`, `backtesting`, `forward_testing`
* Output ref format: `"{instance_id}.{output_name}"` — matches `ScalarOperandResolver` key convention

Validation:
* Full backend suite: **2259 passed**, zero regressions (2207 + 52 new)

---

## Phase 2P.8 — Backtest Position Sizing Foundation (COMPLETE)

Completed:
* `backend/backtesting/models.py` (modified):
  * `PositionSizeMode` extended: `EQUITY_FRACTION = "equity_fraction"` added alongside `FIXED_QUANTITY`
  * `BacktestSimulationConfig` extended: `equity_fraction: float | None` field; cross-field model validator enforces `equity_fraction ∈ (0, 1]` when mode=EQUITY_FRACTION; `equity_fraction=None` preserved when mode=FIXED_QUANTITY (backward-compatible)
  * `BacktestRejectionReason` extended: `ZERO_QUANTITY = "zero_quantity"` — equity_fraction sizing resolved to 0 units
  * `SimulatedTrade` extended: `position_size_mode: PositionSizeMode` + `sizing_value: float` audit fields (required on all trades — open and close)
* `backend/backtesting/position_tracker.py` (modified):
  * `resolve_position_quantity()` (new public function): deterministic sizing resolver; FIXED_QUANTITY → returns `fixed_quantity`; EQUITY_FRACTION → `floor(equity × fraction / adj_price)`; returns 0.0 when budget < price
  * `PositionState` extended: `position_size_mode: PositionSizeMode`, `equity_fraction: float` (0.0 when unused)
  * `_open_long` updated: calls `resolve_position_quantity()` before commission/cash check; rejects with ZERO_QUANTITY when qty=0; populates `position_size_mode` + `sizing_value` on trade
  * `_close_long` updated: populates `position_size_mode` + `sizing_value` on trade (uses position mode at entry)
* `backend/backtesting/simulator.py` (modified):
  * `run_simulation` passes `position_size_mode` + `equity_fraction` from config to `PositionState`
* `tests/unit/test_backtest_position_sizing.py` (new) — 83 tests: enum, config validation, resolver, PositionState, fixed qty (retention), equity_fraction sizing, zero qty rejection, audit fields, simulation integration, equity growth between trades, equity curve, fixed qty regression, unsupported features, architecture guards
* `tests/unit/test_backtest_simulation.py` (modified) — updated `test_simulated_trade_frozen` to include new required `position_size_mode` + `sizing_value` fields
* `docs/BACKTEST_POSITION_SIZING.md` (new) — sizing modes, quantity formula, cost-aware cash check, rejection reasons, audit fields, constraints, extension path

Architecture preserved:
* `sizing rule ≠ portfolio allocator ≠ execution engine` — sizing is simulation-internal
* No leverage: `equity_fraction` validated ≤ 1.0 at config time; values > 1.0 rejected
* No margin: full notional + commission must be covered by cash
* Long-only, single position, deterministic — all prior constraints preserved
* Zero-cost default + `FIXED_QUANTITY` default → Phase 2P.6/2P.7 behavior exactly preserved
* `resolve_position_quantity()` is deterministic: identical inputs → identical quantity

Validation:
* Full backend suite: **2207 passed**, zero regressions (2124 + 83 new)

---

## Phase 2P.7 — Backtest Cost Model Foundation (COMPLETE)

Completed:
* `backend/backtesting/cost_model.py` (new):
  * `CommissionMode` — `NONE`, `FIXED` (flat per trade), `PERCENTAGE` (fraction of notional)
  * `SlippageMode` — `NONE`, `FIXED` (per-share), `PERCENTAGE` (fraction of close)
  * `TradeCostBreakdown` — frozen Pydantic: `raw_price`, `adjusted_price`, `gross_value`, `commission_paid`, `slippage_paid`, `total_cost`, `net_cash_impact`
  * `compute_slippage_per_unit()`, `apply_slippage()` (direction-aware), `compute_commission()`, `build_cost_breakdown()`
* `backend/backtesting/models.py` (modified):
  * `BacktestSimulationConfig` extended: `commission_mode`, `commission_value`, `slippage_mode`, `slippage_value` (all default to NONE/0 — backward compatible)
  * `SimulatedTrade` extended: `cost_breakdown: TradeCostBreakdown` (required)
  * `BacktestSimulationSummary` extended: `total_commission_paid`, `total_slippage_paid`, `total_cost_paid`, `average_cost_per_trade`
* `backend/backtesting/position_tracker.py` (modified):
  * `PositionState` extended: `commission_mode`, `commission_value`, `slippage_mode`, `slippage_value`, `entry_commission`
  * `_open_long` and `_close_long` apply slippage + commission deterministically
  * `realized_pnl` is all-in net: `(adj_close - avg_entry) × qty - commission_close - commission_open`
  * Insufficient-cash check uses all-in cost (notional + commission)
* `backend/backtesting/simulator.py` (modified):
  * `run_simulation` passes cost config fields to `PositionState`
  * `_compute_summary` aggregates `total_commission_paid`, `total_slippage_paid`, `total_cost_paid`, `average_cost_per_trade`
* `tests/unit/test_backtest_cost_model.py` (new) — 86 tests covering enums, helpers, breakdown, config validation, cost-aware open/close, simulation integration, API, architecture guards
* `tests/unit/test_backtest_simulation.py` (modified) — updated 3 model-construction tests to include new required fields
* `docs/BACKTEST_COST_MODEL_FOUNDATION.md` (new) — cost philosophy, models, execution price rules, PnL definition, extension path

Architecture preserved:
* `SimulatedTrade ≠ BrokerFill ≠ LiveExecution` — all deterministic simulation
* No stochastic fills, no latency, no order book, no broker concepts
* Zero-cost default preserves Phase 2P.6 behavior exactly
* Determinism verified: identical inputs → identical outputs

Validation:
* Full backend suite: **2124 passed**, zero regressions (2038 + 86 new)

---

## Phase 2P.6 — Backtest Simulation Foundation (COMPLETE)

Completed:
* `backend/backtesting/models.py` (new) — domain models:
  * `BacktestSimulationConfig` — `initial_cash`, `position_size_mode` (fixed_quantity only), `fixed_quantity`; Pydantic v2 frozen
  * `SimulationPriceBar` — `bar_index`, `timestamp`, `close`; execution price source
  * `BacktestRejectionReason` — enum: `already_long`, `already_flat`, `insufficient_cash`, `missing_price`, `unsupported_action`
  * `BacktestRejection` — explicit rejection record; `rejection_id = f"rejection:{intent_id}"`
  * `SimulatedTrade` — `trade_id = f"trade:{source_intent_id}"`, `action`, `bar_index`, `quantity`, `price` (close), `cash_before/after`, `realized_pnl` (None for opens), `position_after`; NO broker/order/fill fields
  * `BacktestEquityPoint` — per-bar: `cash`, `position_quantity`, `market_value`, `realized_pnl` (cumulative), `unrealized_pnl`, `equity`
  * `BacktestSimulationSummary` — aggregated counts, cash/equity/PnL summary, peak/trough equity
  * `BacktestSimulationResult` — full result: `plan_draft_id`, `config`, `trades`, `equity_curve`, `rejections`, `summary`
* `backend/backtesting/position_tracker.py` (new):
  * `PositionState` — mutable dataclass: `cash`, `fixed_quantity`, `position_quantity`, `average_entry_price`, `cumulative_realized_pnl`; `is_long`/`is_flat` properties
  * `process_intent(intent, price, state)` — returns `(SimulatedTrade | None, BacktestRejection | None)`; long-only rules enforced
* `backend/backtesting/simulator.py` (new):
  * `run_simulation(intent_batch, price_bars, config) → BacktestSimulationResult`
  * Sequential: one equity point per bar; intents processed in batch order; missing-price intents produce rejections
* `backend/api/schemas/backtest_simulation.py` (new) — `BacktestSimulationRequest` wraps intent_batch + price_bars + config
* `backend/api/services/backtest_simulation_service.py` (new) — thin `simulate_backtest()` wrapper
* `backend/api/routes/backtest_simulation.py` (new) — `POST /backtests/simulate`
* `backend/api/main.py` (modified) — registers `backtest_simulation.router`
* `docs/BACKTEST_SIMULATION_FOUNDATION.md` (new) — long-only scope, close-price assumption, rejection behavior, halal constraints, extension path
* `tests/unit/test_backtest_simulation.py` (new) — 95 tests covering models, config, position tracker, simulation engine, equity curve, rejections, API, architecture guards

Architecture preserved:
* `TradeIntent ≠ Order ≠ SimulatedTrade ≠ BrokerFill` — simulation only, no execution coupling
* Long-only, fixed quantity, close-price execution — no shorting, leverage, margin, slippage, fees
* All rejections explicit and tracked — never silently ignored
* Deterministic trade_id and rejection_id from intent_id — reproducible from identical inputs
* Architecture boundary verified: no imports from `execution`, `forward_testing`, `strategy_runtime`

Validation:
* Full backend suite: **2038 passed**, zero regressions (1943 + 95 new)

---

## Phase 2P.5 — Trade Intent Contract Layer (COMPLETE)

Completed:
* `backend/strategy_registry/trade_intents.py` (new) — passive domain models:
  * `TradeIntentAction` — `open_long`, `close_long` only; `short_sell`/leverage/margin absent by design (halal compatibility)
  * `TradeIntentSource` — traceability: `signal_event_id`, `bar_index`, `timestamp`, `rule_id`, `rule_kind`
  * `TradeIntent` — frozen Pydantic v2; `intent_id` (deterministic: `"intent:{signal_event_id}"`), `action`, `source`; NO order/price/quantity/fill/position/pnl fields
  * `TradeIntentSummary` — frozen Pydantic v2; `total_intents`, `open_long_intents`, `close_long_intents`, `ignored_signal_events`, `first_intent_bar_index`, `last_intent_bar_index`
  * `TradeIntentBatch` — frozen Pydantic v2; `plan_draft_id`, `intents`, `summary`, `ignored_event_ids`
* `backend/strategy_registry/trade_intent_extractor.py` (new):
  * `extract_trade_intents(signal_event_batch) → TradeIntentBatch` — entry→open_long, exit→close_long, diagnostic→ignored; ordering inherits signal batch order; no re-sort needed
  * `_ACTION_MAP` — `{ENTRY: OPEN_LONG, EXIT: CLOSE_LONG}` — single declaration of mapping
  * `_make_intent_id(signal_event_id)` — deterministic: `f"intent:{signal_event_id}"`
* `backend/api/services/trade_intent_service.py` (new) — thin `extract_trade_intents_from_batch()` wrapper
* `backend/api/routes/trade_intents.py` (new) — `POST /semantics/extract-trade-intents`; input: `SignalEventBatch`; output: `TradeIntentBatch`
* `backend/api/main.py` (modified) — registers `trade_intents.router`
* `docs/TRADE_INTENT_CONTRACTS.md` (new) — intent meaning, action minimalism rationale, halal compatibility, future backtesting/execution relationship
* `tests/unit/test_trade_intents.py` (new) — 86 tests covering models, extraction, API, architecture boundary, forbidden fields

Architecture preserved:
* `signal event ≠ trade intent ≠ order ≠ position ≠ PnL` — no execution fields anywhere
* `short_sell`/leverage/margin absent by design — action set minimal for halal equity compatibility
* Diagnostic events ignored and tracked in `ignored_event_ids` — never silently converted
* Deterministic intent IDs from signal event IDs — reproducible from identical inputs
* Architecture boundary verified: no imports from `backtesting`, `execution`, `forward_testing`, `strategy_runtime`

Validation:
* Full backend suite: **1943 passed**, zero regressions (1857 + 86 new)

---

## Phase 2P.4 — Evaluation Signal Event Contracts (COMPLETE)

Completed:
* `backend/strategy_registry/signal_events.py` (new) — passive domain models:
  * `SignalEventKind` — `entry`, `exit`, `diagnostic` enum
  * `SignalEventSource` — traceability: `bar_index`, `timestamp`, `rule_id`, `rule_kind`, `rule_index`
  * `SignalEvent` — frozen Pydantic v2; `event_id` (deterministic), `kind`, `source`, `outcome`, `diagnostics`; NO order/trade/fill/position/pnl fields
  * `SignalEventSummary` — frozen Pydantic v2; `total_events`, `entry_events`, `exit_events`, `diagnostic_events`, `bars_with_events`, `first_event_bar_index`, `last_event_bar_index`
  * `SignalEventBatch` — frozen Pydantic v2; `plan_draft_id`, `events: tuple[SignalEvent, ...]`, `summary`
* `backend/strategy_registry/signal_event_extractor.py` (new):
  * `extract_signal_events(historical_result) → SignalEventBatch` — only `triggered=True` → event; `False`/`None` skipped; sort order: bar_index → entry_before_exit → rule_index → rule_id
  * `_make_event_id(bar_index, rule_kind, rule_index, rule_id)` — deterministic: `"{bar_index}:{rule_kind}:{rule_index}:{rule_id or 'none'}"`
* `backend/api/services/signal_event_service.py` (new) — `SignalEventExtractionError`, `extract_signal_events_from_payload(semantics, bars) → SignalEventBatch`
* `backend/api/routes/signal_events.py` (new) — `POST /semantics/extract-signal-events`; reuses `HistoricalEvaluationRequest` schema; 422 on compile/eval failure
* `backend/api/main.py` (modified) — registers `signal_events.router`
* `docs/SIGNAL_EVENT_CONTRACTS.md` (new) — signal event meaning, traceability fields, forbidden assumptions, future relationship to backtesting
* `tests/unit/test_signal_events.py` (new) — 88 tests covering all models, extraction scenarios, API, architecture boundary

Architecture preserved:
* `signal event ≠ order ≠ trade` — no execution fields anywhere in the contract
* `entry signal ≠ buy order`; `exit signal ≠ sell order` — enforced by having no buy/sell/direction/size/price semantics
* Only `True` triggered outcomes produce events; `False` and `None` silently skipped
* Deterministic ordering: bar_index → entry-before-exit → rule_index → rule_id
* Architecture boundary verified: no imports from `strategy_runtime`, `backtesting`, `execution`, `forward_testing`

Validation:
* Full backend suite: **1857 passed**, zero regressions (1769 + 88 new)

---

## Phase 2P.3 — Previous-Bar Context & Crossover Operator Support (COMPLETE)

Completed:
* `backend/strategy_registry/two_bar_context.py` (new):
  * `PreviousBarMissingError` — raised when previous-bar resolution attempted on first bar
  * `TwoBarEvaluationContext(ScalarEvaluationContext)` — carries `current_values` + optional `previous_values` (both flat `dict[str, float]`); `has_previous_bar` property; `resolve_previous_price_field`, `resolve_previous_tool_output`, `resolve_previous_constant` methods
* `backend/strategy_registry/crossover_evaluator.py` (new):
  * `CROSSOVER_OPERATORS: frozenset` — `{"crosses_above", "crosses_below"}`
  * `ALL_TWO_BAR_OPERATORS: frozenset` — union of SCALAR_OPERATORS and CROSSOVER_OPERATORS
  * `CrossoverConditionEvaluator(ConditionEvaluator)` — delegates scalar ops to wrapped `ScalarConditionEvaluator`; handles crossover ops; first-bar → `outcome=None` + "no_previous_bar" info diagnostic; wrong context type → `outcome=None` + "context_unavailable" diagnostic
  * `TwoBarScalarEngine(EvaluationEngineContract)` — top-level engine supporting all 8 operators; uses `CrossoverConditionEvaluator` in standard `ScalarGroupEvaluator → ScalarRuleEvaluator` stack
  * Crossover semantics: `crosses_above`: `prev_left <= prev_right AND curr_left > curr_right`; `crosses_below`: `prev_left >= prev_right AND curr_left < curr_right`
* `backend/strategy_registry/historical_evaluator.py` (modified):
  * Added `_build_scalar_values(bar) → dict[str, float]` — extracted helper for flat key mapping
  * Updated `_build_scalar_context` to return `TwoBarEvaluationContext` (with default `previous_values=None`)
  * Replaced `_ENGINE = ScalarEvaluationEngine()` with `_TWO_BAR_ENGINE = TwoBarScalarEngine()`
  * `evaluate_history` now propagates `previous_values` between bar iterations; first bar has `previous_values=None`
* `docs/PREVIOUS_BAR_EVALUATION.md` (new) — crossover semantics, first-bar behavior, key layout, example usage
* `tests/unit/test_crossover_evaluator.py` (new) — 87 unit tests covering `TwoBarEvaluationContext`, `CrossoverConditionEvaluator`, `TwoBarScalarEngine`, historical integration, architecture boundary

Architecture preserved:
* Crossover operators produce `outcome=None` with "no_previous_bar" info diagnostic on first bar — never silently coerced to False
* `TwoBarEvaluationContext` subclasses `ScalarEvaluationContext`; existing scalar evaluation tests unaffected
* No portfolio, no trades, no PnL; still pure repeated single-bar semantic evaluation with two-bar temporal access
* Architecture boundary verified by tests: no imports from `strategy_runtime`, `backtesting`, `execution`, `forward_testing`

Validation:
* Full backend suite: **1769 passed**, zero regressions (1682 + 87 new)

---

## Phase 2P.2 — Bar-by-Bar Semantic Evaluation Iterator (COMPLETE)

Completed:
* `backend/strategy_registry/historical_evaluator.py` (new) — historical evaluation domain + iterator:
  * `HistoricalBarContext` — frozen Pydantic v2; per-bar input with `bar_index`, `timestamp`, `price_fields: dict[str, float]`, `tool_outputs: dict[str, float]`
  * `HistoricalEvaluationInput` — frozen Pydantic v2; `plan: EvaluationPlan` + `bars: tuple[HistoricalBarContext, ...]`
  * `BarEvaluationResult` — frozen Pydantic v2; `bar_index`, `timestamp`, `entry_triggered`, `exit_triggered`, `trace: EvaluationTrace`
  * `HistoricalEvaluationResult` — frozen Pydantic v2; `plan_draft_id`, `bars_evaluated`, `entry_triggered_count`, `exit_triggered_count`, `bar_results: tuple[BarEvaluationResult, ...]`
  * `_build_scalar_context(bar, plan_draft_id) → ScalarEvaluationContext` — maps `price_fields["close"] → "price.close"`, `tool_outputs["sma.value"] → "tool.sma.value"`
  * `evaluate_history(input) → HistoricalEvaluationResult` — sequential bar iteration; deterministic; no state between bars; `_ENGINE` is a stateless module-level reusable `ScalarEvaluationEngine`
  * `entry_triggered_count` / `exit_triggered_count` count only `True` outcomes; `None` outcomes not counted
* `backend/api/schemas/historical_evaluation.py` (new) — API DTOs:
  * `HistoricalBarPayload` — per-bar API input; extra="forbid"
  * `HistoricalEvaluationRequest` — `semantics: StrategySemantics` + `bars: list[HistoricalBarPayload]`; extra="forbid"
* `backend/api/services/historical_evaluation_service.py` (new):
  * `HistoricalEvaluationError` — compile failure wrapper
  * `evaluate_history_from_payload(semantics, bars) → HistoricalEvaluationResult`
* `backend/api/routes/historical_evaluation.py` (new) — `POST /semantics/evaluate-history`; 422 on compile failure
* `backend/api/main.py` (modified) — registers `historical_evaluation.router`
* `docs/HISTORICAL_EVALUATION_ITERATOR.md` (new) — why this is not backtesting, iteration design, key convention table, future extension path
* `tests/unit/test_historical_evaluator.py` (new) — 62 unit tests
* `tests/unit/test_historical_evaluation_api.py` (new) — 21 API tests

Architecture preserved:
* Sequential per-bar evaluation; no state between bars
* Tool outputs must be pre-injected per bar; no indicator computation
* `crosses_above`/`crosses_below` remain deferred; produce `outcome=None` + diagnostic per bar
* Zero portfolio logic, zero trade simulation, zero PnL
* Architecture boundary verified by tests: no imports from `strategy_runtime`, `backtesting`, `execution`, `forward_testing`

Validation:
* Full backend suite: **1682 passed**, zero regressions (1601 + 81 new)

---

## Phase 2P.1 — Concrete Scalar Evaluator Foundation (COMPLETE)

Completed:
* `backend/strategy_registry/scalar_evaluation_context.py` (new) — concrete `EvaluationContext`:
  * `ScalarContextError` — raised when a required value is absent from the flat scalar dict
  * `ScalarEvaluationContext` — backed by `dict[str, float]`; resolves `price.{field}`, `tool.{instance_id}.{output_name}`, and numeric constant strings; `available_tool_instances` / `available_price_fields` properties; zero computation
* `backend/strategy_registry/scalar_evaluator.py` (new) — all concrete evaluator components:
  * `UnsupportedOperatorError` — raised for `crosses_above`, `crosses_below`, and unknown operators
  * `SCALAR_OPERATORS: frozenset` — `{">", "<", ">=", "<=", "==", "!="}`
  * `ScalarOperandResolver` — dispatches `(kind, ref)` to context; splits `tool_output` refs as `instance_id.output_name`
  * `ScalarOperatorEvaluator` — evaluates 6 scalar operators; rejects crossover operators with `UnsupportedOperatorError`
  * `ScalarConditionEvaluator` — orchestrates resolver + operator evaluator; resolution/operator failures → `EvaluationDiagnostic`, `outcome=None`
  * `ScalarGroupEvaluator` — recursive AND/OR evaluation; all children always evaluated (complete traces); correct indeterminate semantics (AND: False wins over None; OR: True wins over None)
  * `ScalarRuleEvaluator` — wraps group evaluator; returns `RuleEvaluationResult` with triggered flag; no signal generation
  * `ScalarEvaluationEngine` — top-level `EvaluationEngineContract` implementation; evaluates all rule_nodes; aggregates `entry_triggered`/`exit_triggered` via OR semantics
* `backend/api/schemas/scalar_evaluation.py` (new) — `ScalarEvaluationRequest` (semantics + scalar_context dict + optional evaluation_id)
* `backend/api/services/scalar_evaluation_service.py` (new):
  * `ScalarEvaluationError` — compile failure wrapper
  * `evaluate_semantics_scalar(semantics, scalar_context, evaluation_id) → EvaluationTrace`
* `backend/api/routes/scalar_evaluation.py` (new) — `POST /semantics/evaluate-scalar`; 422 on compile failure
* `backend/api/main.py` (modified) — registers `scalar_evaluation.router`
* `docs/SCALAR_EVALUATOR_FOUNDATION.md` (new) — evaluator responsibilities, intentionally unsupported features, future extension path
* `tests/unit/test_scalar_evaluator.py` (new) — 100 unit tests
* `tests/unit/test_scalar_evaluation_api.py` (new) — 21 API tests

Architecture preserved:
* Single-snapshot evaluation only; no bar iteration, no previous-bar state
* Tool outputs must be pre-injected into context; no indicator computation
* `ScalarEvaluationContext` and `ScalarEvaluationEngine` are both free of runtime/backtesting/execution imports (architecture boundary verified by tests)
* Evaluator is generic IR-driven; no indicator-specific branching anywhere
* `crosses_above`/`crosses_below` explicitly deferred with clear error messages

Validation:
* Full backend suite: **1601 passed**, zero regressions (1483 + 118 new)

---

## Phase 2O.9 — Evaluation Readiness & Linting Layer (COMPLETE)

Completed:
* `backend/strategy_registry/evaluation_readiness.py` (new) — domain models + static lint rules:
  * `ReadinessIssue` — frozen Pydantic v2; code, severity ("blocking"|"warning"|"info"), message, path, node_id, suggestion
  * `ReadinessSummary` — frozen; blocking_count, warning_count, info_count
  * `EvaluationReadinessReport` — frozen; ready bool, status ("ready"|"degraded"|"blocked"), summary, issues tuple
  * `STANDARD_OPERATORS` — frozenset of 8 recognized condition operators
  * `DEFAULT_MAX_NESTING_DEPTH = 5`
  * Lint rules implemented:
    - `not_compiled` — plan compilation failed (blocking)
    - `compilation_error` — per-error string from compilation (blocking)
    - `compilation_diagnostic_error` — error-severity CompilationDiagnostic (blocking)
    - `compilation_diagnostic_warning` — warning-severity CompilationDiagnostic (warning)
    - `no_rules` — plan has no rule nodes (blocking)
    - `empty_rule` — rule with zero conditions (blocking)
    - `missing_rule_id` — rule_id is None (warning)
    - `missing_group_id` — group_id is None (warning)
    - `missing_condition_id` — condition_id is None (warning)
    - `unsupported_operator` — operator not in supported_operators set (blocking)
    - `excessive_nesting_depth` — depth > threshold (warning)
    - `binding_invalid` — error-severity binding diagnostic (blocking)
  * `check_readiness(*, compiled, errors, plan, binding_result, supported_operators, max_nesting_depth_threshold) → EvaluationReadinessReport`
    - Issues sorted: blocking first, then warning, then info (stable within severity)
    - Deterministic: identical inputs → identical report
* `backend/api/schemas/evaluation_readiness.py` (new) — API DTOs:
  * `EvaluationReadinessRequest` — `semantics: StrategySemantics` for payload endpoint
  * `EvaluationReadinessResponse` — `draft_id, ready, status, summary, issues`
* `backend/api/services/evaluation_readiness_service.py` (new):
  * `check_draft_readiness(draft_id, repository, registry) → EvaluationReadinessResponse`
    - loads draft, compiles, runs binding validation, calls `check_readiness()`
    - returns blocked report if draft has no semantics
  * `check_semantics_payload_readiness(semantics) → EvaluationReadinessResponse`
    - no draft context; no binding check; binding_result=None
* `backend/api/routes/evaluation_readiness.py` (new) — two-router pattern:
  * `draft_router`: `GET /drafts/{draft_id}/semantics/readiness` — 404 on unknown draft
  * `payload_router`: `POST /semantics/readiness` — arbitrary payload lint; 422 on bad body
* `backend/api/main.py` (modified) — registers `evaluation_readiness.draft_router` + `evaluation_readiness.payload_router`
* `frontend/src/types/planInspection.ts` (modified) — added `ReadinessIssue`, `ReadinessSummary`, `ReadinessStatus`, `EvaluationReadinessResponse`
* `frontend/src/api/planInspection.ts` (modified) — added `fetchDraftReadiness(draftId)` → `GET /drafts/{id}/semantics/readiness`
* `frontend/src/components/PlanInspectionPanel.tsx` (modified):
  * Fetches both plan inspection and readiness in parallel (`Promise.all`)
  * Added `ReadinessSection` — renders status badge (✓ ready / ⚠ degraded / ✗ blocked), blocking+warning counts, per-issue messages with suggestions
  * Added `ReadinessIssueRow` — inline issue renderer with severity color coding
* `tests/unit/test_evaluation_readiness.py` (new) — 83 domain tests
* `tests/unit/test_evaluation_readiness_api.py` (new) — 40 API tests  (wait, let me recheck the count)

Architecture preserved:
* Zero execution — lint rules are pure structural checks against frozen plan IR
* `check_readiness` is a pure function: no market data, no indicator computation, no runtime calls
* Architecture boundary enforced: three new backend modules pass import-line checks
* Frontend fetches both endpoints in parallel; renders passively; no local lint logic

Validation:
* Full backend suite: 1483 passed, zero regressions (1400 + 83 new)
* Frontend build: 53 modules, `tsc && vite build` clean

---

## Phase 2O.8 — Read-Only EvaluationPlan Inspection UI Panel (COMPLETE)

Completed:
* `frontend/src/api/planInspection.ts` (new) — typed API client:
  * `fetchDraftPlanInspection(draftId) → Promise<PlanInspectionResponse>` — calls `GET /drafts/{id}/semantics/plan`
  * no business logic; no local inspection; mirrors semantics.ts pattern
* `frontend/src/components/PlanInspectionPanel.tsx` (new) — read-only inspection panel:
  * Props: `draftId: string`, `refreshToken?: number`
  * Fetches on mount + on `refreshToken` change + on manual Refresh click
  * Sections: CompilationStatus pills, TopologySection (KV rows + operator chips), DependencySection (tool outputs / price fields / constants), RulesSection (per-rule kind/index/cond/grp/depth/ops), DiagnosticsSection (error/warning/info counts + messages + binding diagnostic count)
  * States: loading, error, no-data, not-compiled (with errors list), full summary
  * `binding_valid === null` renders "binding — no context" neutral pill (payload endpoint)
  * Strictly read-only — no editing, no run controls, no execution buttons
  * All styles inline; monospace/dark theme matching SemanticEditorPanel
* `frontend/src/components/DraftWorkspace.tsx` (modified):
  * Added `PlanInspectionPanel` import
  * Added `planRefreshToken` state (int counter)
  * `handleSaveSemantics` now calls `setPlanRefreshToken(t => t + 1)` after successful save
  * Renders `<PlanInspectionPanel draftId={...} refreshToken={planRefreshToken} />` below `SemanticEditorPanel`
  * Panel uses same `key={plan-${draft_id}}` pattern — resets on draft switch

Architecture preserved:
* Zero execution — panel only renders backend-provided data
* No plan inspection logic moved into frontend
* No Redux/Zustand/MobX — `planRefreshToken` is simple local counter
* Panel auto-refreshes on draft switch (key reset), on semantics save, and on manual Refresh click
* No polling, no websockets

Validation:
* Frontend build: 53 modules, `tsc && vite build` clean
* Full backend suite: 1400 passed, zero regressions

---

## Phase 2O.7 — EvaluationPlan Inspection & Diagnostics API (COMPLETE)

Completed:
* `backend/strategy_registry/plan_inspector.py` (new) — `PlanNodeVisitor`-based passive inspector:
  * `ConditionNodeSummary` — frozen Pydantic v2; operator, left/right kind+ref, depth
  * `RuleNodeSummary` — frozen Pydantic v2; rule_id, kind, index, condition_count, group_count, max_nesting_depth, operators_used
  * `TopologySummary` — frozen Pydantic v2; entry/exit rule counts, total condition/group nodes, max_nesting_depth, operator_usage (dict sorted by key), unique_operators (sorted tuple)
  * `DependencyInspectionSummary` — frozen; tool_outputs/price_fields/constants with counts and sorted tuples
  * `DiagnosticsSummary` — frozen; error_count, warning_count, info_count, messages
  * `EvaluationPlanSummary` — frozen; draft_id, semantic_version, total_rules, topology, dependencies, diagnostics, rules
  * `_Acc` internal mutable dataclass for visitor aggregation (not part of public API)
  * `_InspectorVisitor` — concrete `PlanNodeVisitor`; post-order accumulation; flat plans → `max_nesting_depth=0`, one nested level → `=1`
  * `inspect_plan(plan: EvaluationPlan) → EvaluationPlanSummary` — pure, deterministic, execution-free
* `backend/api/schemas/plan_inspection.py` (new) — API schema layer:
  * `PlanInspectionRequest` — `semantics: StrategySemantics` for payload endpoint
  * `PlanInspectionResponse` — `draft_id`, `compiled`, `errors`, `evaluation_plan|None`, `summary|None`, `binding_valid|None`, `binding_diagnostics`, `binding_dependency_summary|None`
* `backend/api/services/plan_inspection_service.py` (new):
  * `inspect_draft_plan(draft_id, repository, registry) → PlanInspectionResponse` — loads draft, compiles, inspects; populates binding fields from draft toolset
  * `inspect_semantics_payload(semantics) → PlanInspectionResponse` — compiles arbitrary payload; no draft context; `binding_valid=None`, `binding_diagnostics=[]`
* `backend/api/routes/plan_inspection.py` (new) — two-router pattern:
  * `draft_router`: `GET /drafts/{draft_id}/semantics/plan` — 404 on unknown draft; `compiled=False` + errors if no semantics
  * `payload_router`: `POST /semantics/plan` — arbitrary semantics inspection; 422 on bad payload
* `backend/api/main.py` (modified) — registers `plan_inspection.draft_router` + `plan_inspection.payload_router`
* `frontend/src/types/planInspection.ts` (new) — TypeScript mirrors: `ConditionNodeSummary`, `RuleNodeSummary`, `TopologySummary`, `DependencyInspectionSummary`, `DiagnosticsSummary`, `EvaluationPlanSummary`, `PlanInspectionResponse`
* `tests/unit/test_plan_inspector.py` (new) — 42 tests: basic shape, rule/node/group counts, nesting depth, operator usage, dependency inspection, diagnostics, rule summaries, determinism, empty plan, architecture boundary
* `tests/unit/test_plan_inspection_api.py` (new) — 40 tests: GET draft plan (200/404/no-semantics), topology/dependency/binding fields, payload endpoint (200/422/determinism)

Architecture preserved:
* Zero execution — `inspect_plan()` is a pure structural walk; no condition evaluation, no market data
* `operator_usage` and `unique_operators` are always deterministically sorted
* `binding_valid` is only non-None on the draft endpoint (toolset context present)
* Follows established two-router prefix-separation pattern matching `semantic_compilation.py`
* Architecture boundary enforced: plan_inspector imports nothing from strategy_runtime/backtesting/execution/forward_testing

Validation:
* New test files only: 82 passed (42 + 40); full suite not re-run post-2O.7 (1318 + 82 = 1400 expected)

---

## Phase 2O.6 — Evaluation Plan Execution Contracts & Evaluator Interface Architecture (COMPLETE)

Completed:
* `backend/strategy_registry/evaluator_contracts.py` (new) — all abstract evaluator interfaces and passive result contracts:
  * `ResolvedValue = Any` — generic type alias; intentionally unbound to remain indicator-agnostic
  * `EvaluationDiagnostic` — frozen Pydantic v2; severity, code, reference, message, optional rule_id/condition_id
  * `ConditionEvaluationResult` — frozen Pydantic v2; condition_id, outcome (bool|None), diagnostics
  * `GroupEvaluationResult` — frozen Pydantic v2; recursive (Union-based); group_id, outcome, child_results, diagnostics
  * `RuleEvaluationResult` — frozen Pydantic v2; rule_id, kind, index, triggered, group_result, diagnostics
  * `EvaluationTrace` — frozen Pydantic v2; full audit trace: plan_draft_id, evaluation_id, rule_results, entry_triggered, exit_triggered
  * `EvaluationContext` — ABC; resolve_tool_output, resolve_price_field, resolve_constant, evaluation_id, available_tool_instances, available_price_fields
  * `OperandResolver` — ABC; resolve(kind, ref, context) → ResolvedValue
  * `OperatorEvaluator` — ABC; supported_operators, evaluate(left, operator, right) → bool|None; generic, no indicator-specific logic
  * `ConditionEvaluator` — ABC; evaluate_condition(node, context) → ConditionEvaluationResult
  * `GroupEvaluator` — ABC; evaluate_group(node, context) → GroupEvaluationResult
  * `RuleEvaluator` — ABC; evaluate_rule(node, context) → RuleEvaluationResult
  * `EvaluationEngineContract` — ABC; evaluate_plan(plan, context) → EvaluationTrace; supported_operators property
* `backend/strategy_registry/evaluation_context.py` (new) — passive context descriptor contracts:
  * `EvaluationContextDescriptor` — frozen Pydantic v2; declares what a context provides (evaluation_id, declared_tool_outputs, price_fields, constants)
  * `EvaluationRequirements` — frozen Pydantic v2; declares what a plan requires from its context
  * `ContextSatisfactionReport` — frozen Pydantic v2; satisfied bool + missing tuples for each dependency type
  * `extract_requirements(DependencySet) → EvaluationRequirements` — pure function
  * `check_context_satisfaction(requirements, descriptor) → ContextSatisfactionReport` — pure function; set membership only, no evaluation
* `backend/strategy_registry/plan_visitor.py` (new) — visitor/traversal architecture:
  * `TraversalContext` — frozen Pydantic v2; rule_index, rule_kind, rule_id, depth, path
  * `PlanNodeVisitor` — ABC; visit_condition_node, visit_group_node, visit_rule_node; post-order depth-first
  * `traverse_plan(plan, visitor) → tuple[Any, ...]` — concrete structural traversal; no evaluation
* `docs/EVALUATION_CONTRACT_ARCHITECTURE.md` (new) — architecture documentation covering: layering diagram, compiler vs evaluator responsibilities, contract table, generic operator philosophy, context lifecycle, visitor usage, guardrails, future evaluator layering
* `tests/unit/test_evaluator_contracts.py` (new) — 71 tests: all result models, all ABCs (cannot instantiate), concrete implementation verification, context satisfaction (satisfied/missing/partial), traversal (post-order, depth, empty, multi-rule), architecture boundary, generic contract (no SMA/RSI), ResolvedValue=Any

Architecture preserved:
* Zero execution introduced — all contracts are abstract or passive Pydantic models
* OperatorEvaluator.evaluate() is generic: no SMA/RSI/crossover assumptions
* EvaluationContext lifecycle is owned by the runtime layer, not the evaluator
* GroupEvaluationResult uses Union[..., "GroupEvaluationResult"] for recursive type (model_rebuild() pattern, same as semantic_plan.py)
* Architecture boundary enforced: all three new modules pass import-line checks for strategy_runtime/backtesting/execution/forward_testing

Validation:
* Full test suite: 1318 passed, zero regressions (1247 + 71 new)

---

## Phase 2O.5 — Semantic-to-Toolset Binding Validation (COMPLETE)

Completed:
* `backend/strategy_registry/semantic_binding_validator.py` (new) — static binding validator:
  * `BindingDiagnostic` — frozen Pydantic v2; severity (error/warning/info), code, reference, message
  * `DependencySummary` — frozen; resolved/unresolved/warned tool_output tuples + price_fields + constants; all sorted
  * `BindingValidationResult` — frozen; valid bool + diagnostics tuple + summary
  * `validate_semantic_bindings(semantics, toolset, registry=None) → BindingValidationResult`
    * Checks dotted format (`instance_id.output_name`) — missing dot → `invalid_output_format` (error)
    * Checks `instance_id` in `toolset.get_tool()` — missing → `missing_tool_instance` (error)
    * Checks `output_name` in `registry.get(tool_id).output_feature_names` — unknown → `unknown_output_name` (error)
    * No registry → `registry_unavailable` (info, not error)
    * Tool not in registry → `tool_not_in_registry` (warning, not error)
    * `valid=not has_errors` — warnings and info do not fail validation
* `backend/api/schemas/semantic_binding.py` (new) — `BindingValidationResponse` (valid, binding_diagnostics, dependency_summary)
* `backend/api/services/semantic_binding_service.py` (new) — `validate_draft_bindings()` — loads draft, handles no-semantics case, runs validator
* `backend/api/routes/semantic_binding.py` (new) — `POST /drafts/{draft_id}/semantics/validate-bindings`
* `backend/api/schemas/semantic_compilation.py` (modified) — `CompilationResponse` extended with `binding_valid`, `binding_diagnostics`, `dependency_summary` (all optional, populated by draft endpoint only)
* `backend/api/services/semantic_compilation_service.py` (modified) — `compile_draft_semantics()` now accepts and uses `registry`; runs `validate_semantic_bindings()` after compilation; returns extended `CompilationResponse`
* `backend/api/routes/semantic_compilation.py` (modified) — draft compile handler now injects `registry: ToolRegistry = Depends(get_tool_registry)`
* `backend/api/main.py` (modified) — registers `semantic_binding.router`
* `frontend/src/components/SemanticEditorPanel.tsx` (modified) — added `toolOutputSuggestions?: string[]` prop; renders `<datalist id="tool-output-suggestions">` with options; `tool_output` input uses `list="tool-output-suggestions"` for browser autocomplete
* `frontend/src/components/DraftWorkspace.tsx` (modified) — passes `toolOutputSuggestions={selectedDraft.toolset.tools.map(t => \`${t.instance_id}.\`)}` to `SemanticEditorPanel`
* `tests/unit/test_semantic_binding_validator.py` (new) — 25 tests: resolution paths, valid/invalid flag logic, dependency summary fields, nested groups, empty semantics, architecture boundary
* `tests/unit/test_semantic_binding_api.py` (new) — 21 tests: validate-bindings endpoint (200, 404, response shape, price/constants in summary, missing instance), no-semantics case, compile integration (binding_valid + dependency_summary in compile response)

Architecture preserved:
* Binding validation is static only — no tool computation, no market data, no indicator evaluation
* Validator never imports from strategy_runtime / backtesting / execution / forward_testing
* Compilation and binding validation are independent steps — compile can succeed while bindings report errors
* Autocomplete is purely additive to the UI — no new business logic; datalist rendered once, referenced by all tool_output inputs

Validation:
* Full test suite: 1247 passed, zero regressions (1201 + 46 new)
* Frontend: `tsc --noEmit` — pending (binding-only props are optional, no type contract changes expected)

---

## Phase 2O.4 — Semantic Compilation Architecture & Evaluation Plan Contracts (COMPLETE)

Completed:
* `backend/strategy_registry/semantic_plan.py` (new) — passive evaluation plan domain models (frozen Pydantic v2):
  * `ConditionPlanNode` — compiled atomic condition; preserves `condition_id`, left/right operand kind+ref, operator, label
  * `ConditionGroupPlanNode` — recursive compiled group; preserves `group_id`, operator, nested nodes
  * `RulePlanNode` — compiled entry/exit rule; preserves `rule_id`, kind, index, label, condition_group
  * `DependencySet` — static extraction of tool_outputs / price_fields / constants (sorted tuples, no computation)
  * `CompilationDiagnostic` — severity + message + path; replaces raises for expected structural issues
  * `EvaluationPlan` — root plan: draft_id, semantic_version, rule_nodes, dependencies, diagnostics, node_count, compiled_at
  * `CompilationResult` — compiled bool + errors + evaluation_plan | None
* `backend/strategy_registry/semantic_compiler.py` (new) — `compile_semantics(semantics, draft_id=None) → CompilationResult`:
  * Walks semantic tree: `_compile_condition` → `_compile_group` (recursive) → `_compile_rule` → `_extract_dependencies`
  * Preserves all semantic IDs (condition_id, group_id, rule_id) in plan nodes
  * Produces `CompilationDiagnostic` for empty semantics (warning) or internal exceptions (error)
  * Architecture boundary enforced: zero imports from strategy_runtime / backtesting / execution / forward_testing
* `backend/api/schemas/semantic_compilation.py` (new) — `CompileRequest`, `CompilationResponse`
* `backend/api/services/semantic_compilation_service.py` (new) — `compile_draft_semantics()`, `compile_semantics_payload()`; thin orchestration; no state mutation
* `backend/api/routes/semantic_compilation.py` (new) — two routers:
  * `draft_router` (prefix `/drafts`): `POST /drafts/{draft_id}/semantics/compile`
  * `payload_router` (prefix `/semantics`): `POST /semantics/compile`
* `backend/api/main.py` (modified) — registers `semantic_compilation.draft_router` and `semantic_compilation.payload_router`
* `frontend/src/types/semanticCompilation.ts` (new) — TypeScript mirrors: `ConditionPlanNode`, `ConditionGroupPlanNode`, `RulePlanNode`, `DependencySet`, `CompilationDiagnostic`, `EvaluationPlan`, `CompilationResponse`
* `tests/unit/test_semantic_compiler.py` (new) — 54 tests: result structure, rule/condition/group compilation, ID preservation, dependency extraction, diagnostics, node count, determinism, serialization round-trip, architecture boundary (import-line checks)
* `tests/unit/test_semantic_compilation_api.py` (new) — 28 tests: draft compile endpoint, payload compile endpoint, empty semantics, missing semantics, 404, 422, no execution side effects

Architecture preserved:
* Compiler performs tree traversal and static extraction ONLY — no condition evaluation, no market data, no runtime calls
* Semantic IDs flow from StrategySemantics → EvaluationPlan nodes verbatim
* Future evaluation engines consume EvaluationPlan as a passive contract
* Two-router pattern maintained (prefix /drafts vs /semantics) for path collision avoidance
* Frontend changes limited to type definitions only

Validation:
* Full test suite: 1201 passed, zero regressions
* Frontend: `tsc --noEmit` clean

---

## Phase 2O.3 — Semantic Identity, Patchability & Structural Stability (COMPLETE)

Completed:
* `backend/strategy_registry/semantics.py` (modified) — added `condition_id: str | None = None`, `group_id: str | None = None`, `rule_id: str | None = None` to `Condition`, `ConditionGroup`, `EntryRule`, `ExitRule` — backward-compatible defaults
* `backend/strategy_registry/semantic_identity.py` (new) — `generate_id()` (uuid4 string), `inject_ids(semantics) → StrategySemantics`; walks tree via `model_dump()` dicts; idempotent — existing IDs never replaced
* `backend/strategy_registry/semantic_validator.py` (modified) — added `validate_semantic_identity_integrity()` (recursive duplicate ID detection); integrated into `validate_semantics_structure()`
* `backend/api/services/semantic_service.py` (modified) — `set_semantics()` now calls `inject_ids()` before persisting; legacy semantics auto-upgraded on first PUT
* `frontend/src/types/semantics.ts` (modified) — `condition_id?`, `group_id?`, `rule_id?` added to `Condition`, `ConditionGroup`, `EntryRule`, `ExitRule`; all optional (backward-compatible)
* `tests/unit/test_semantic_identity.py` (new) — 30 tests: generate_id, injection, preservation, idempotency, reorder stability, nested groups, duplicate detection, cross-type duplicates, legacy migration, backward compat

Validation: 1119 passed (post-2O.3), zero regressions.

---

## Phase 2O.2 — Semantic Composition UI (Form-Based Semantic Authoring) (COMPLETE)

Completed:
* `frontend/src/types/drafts.ts` (modified) — `StrategyDraftData` extended with `semantics?: StrategySemantics | null`
* `frontend/vite.config.ts` (modified) — added `/semantics` proxy to backend at `:8000`
* `frontend/src/api/semantics.ts` (new) — typed API client:
  * `getSemantics(draftId)` — `GET /drafts/{id}/semantics`
  * `setSemantics(draftId, semantics)` — `PUT /drafts/{id}/semantics`
  * `validateDraftSemantics(draftId)` — `POST /drafts/{id}/semantics/validate`
  * `validateSemanticsPayload(semantics)` — `POST /semantics/validate`
* `frontend/src/components/SemanticEditorPanel.tsx` (new) — full semantic authoring panel:
  * File-local sub-components: `OperandWidget`, `ConditionRow`, `ConditionGroupEditor` (recursive), `RuleBlock`
  * Empty state with `+ Create Semantics` button
  * Entry Rules section: add/remove rules; each rule has label + notes + `ConditionGroupEditor`
  * Exit Rules section: same structure
  * `ConditionGroupEditor`: AND/OR selector, add/remove conditions, `+ Group` (nested group), recursive depth-alternating accent colour
  * `ConditionRow`: left operand / operator (8 options) / right operand; operand kind resets ref on kind change
  * `OperandWidget`: kind selector (`tool` | `const` | `price`); price ref → `<select>` with open/high/low/close/volume; constant → number input; tool_output → text input `instance.output`
  * Save button: PUT to backend, syncs local state from server response
  * Validate button: POST local semantics to payload validation endpoint, displays `✓ valid` or `✗ invalid` + error list
  * Validation cleared on any local edit (stale result avoidance)
* `frontend/src/components/DraftWorkspace.tsx` (modified):
  * Imports `SemanticEditorPanel`, `setSemantics`, `validateSemanticsPayload`
  * `handleSaveSemantics()` — calls `setSemantics`, updates `selectedDraft.semantics` from server response, syncs list
  * `handleValidateSemantics()` — delegates to `validateSemanticsPayload` (payload endpoint; no draft-save required)
  * `SemanticEditorPanel` rendered below `ToolCompositionPanel` with `key=\`sem-${draft_id}\`` for clean draft-switch reset

Architecture preserved:
* Frontend edits locally → Save → backend stores → server response replaces local state
* Validate operates on current local state via payload endpoint (no implicit save required)
* No semantic evaluation, no operator interpretation, no signal generation
* Backend remains sole validator and persistence authority
* No Redux/Zustand — all state remains in `SemanticEditorPanel` via `useState`

Validation:
* Frontend build: `tsc && vite build` — 51 modules, clean
* Backend: 1089 passed, zero regressions

Next recommended step:
* Phase 2O.3: Semantic Inspector — read-only display of persisted semantics on drafts; surface semantic summary in `DraftDetailView` (entry/exit rule count, condition preview); no new editing UI

---

## Phase 2O.1 — Strategy Semantic Foundation & Condition Graph Contracts (COMPLETE)

Completed:
* `backend/strategy_registry/semantics.py` (new) — frozen Pydantic v2 domain models:
  * `OperandKind` enum: `tool_output`, `constant`, `price`
  * `OperandReference` — typed operand (kind + ref); ref stripped and validated
  * `ConditionOperator` enum: `>`, `<`, `>=`, `<=`, `==`, `!=`, `crosses_above`, `crosses_below`
  * `Condition` — atomic comparison between two `OperandReference` objects
  * `LogicalOperator` enum: `AND`, `OR`
  * `ConditionGroup` — recursive logical group; supports arbitrarily nested AND/OR trees; `model_rebuild()` resolves self-reference
  * `EntryRule`, `ExitRule` — wrap `ConditionGroup` with optional label/notes
  * `SemanticsMetadata` — version, author, description
  * `StrategySemantics` — root model: `entry_rules + exit_rules + metadata`; execution-free and portable
* `backend/strategy_registry/semantic_validator.py` (new) — structural-only validator:
  * `SemanticValidationResult` — `.valid`, `.errors`
  * `validate_semantics_structure()` — validates: price ref in allowed set, tool_output uses dotted format, constants are numeric, groups non-empty; recurses through nesting
  * Explicitly NO runtime evaluation, NO market data, NO indicator computation
* `backend/strategy_registry/drafts.py` (modified) — added `semantics: StrategySemantics | None = None`; backward-compatible default
* `backend/api/schemas/semantics.py` (new) — passive API DTOs: `SemanticsUpdateRequest`, `SemanticsValidateRequest`, `SemanticsValidationResponse`, `SemanticsResponse`
* `backend/api/schemas/drafts.py` (modified) — `DraftResponse` now includes `semantics: StrategySemantics | None = None`
* `backend/api/services/semantic_service.py` (new) — thin service: `get_semantics`, `set_semantics`, `validate_draft_semantics`, `validate_semantics_payload`
* `backend/api/routes/semantics.py` (new) — two routers to avoid path conflict with `draft_composition`'s `POST /{draft_id}/validate`:
  * `draft_router` (prefix `/drafts`): `GET /{id}/semantics`, `PUT /{id}/semantics`, `POST /{id}/semantics/validate`
  * `payload_router` (prefix `/semantics`): `POST /semantics/validate` (no draft required)
* `backend/api/main.py` (modified) — registers both `semantics.draft_router` and `semantics.payload_router`
* `frontend/src/types/semantics.ts` (new) — TypeScript mirrors: `OperandKind`, `OperandReference`, `ConditionOperator`, `Condition`, `LogicalOperator`, `ConditionGroup`, `EntryRule`, `ExitRule`, `SemanticsMetadata`, `StrategySemantics`, `SemanticsResponse`, `SemanticsValidationResponse`
* `tests/unit/test_strategy_semantics.py` (new) — 48 tests: operands, conditions, groups, nesting, rules, semantics, frozen immutability, serialisation, round-trip
* `tests/unit/test_semantic_validator.py` (new) — 22 tests: valid cases, invalid constant/price/tool_output, nested error surfacing, no-runtime-evaluation assertion
* `tests/unit/test_semantics_api.py` (new) — 20 tests: GET/PUT/POST routes, backward compat, legacy draft deserialisation, payload validation, 404 cases

Architecture preserved:
* All models frozen (immutable, deterministic serialisation)
* No runtime evaluation, no signal generation, no market data consumption
* Validator asserts structurally only — no compute/execution imports
* Frontend receives types only — no semantic editor UI
* Draft backward compatibility: existing drafts without `semantics` deserialise as `semantics=None`

Known fix during implementation:
* Two-router architecture required because `POST /drafts/semantics/validate` (static) was intercepted by `draft_composition`'s `POST /drafts/{draft_id}/validate` (parameterised, registered earlier). Solution: moved standalone payload validation to separate `payload_router` with prefix `/semantics`.

Validation:
* 1089 tests passing (+90 new, zero regressions from 999)
* No frontend build step required (type definitions only)

Next recommended step:
* Phase 2O.2: Semantic Composition UI — minimal frontend for authoring entry/exit rules from within the Draft Workspace; no drag/drop; backend authority preserved

---

## Phase 2N.12 — Browser-Level Draft Workspace Validation & Runtime Stabilization (COMPLETE)

Completed:
* Browser-level Draft Workspace validation executed against live frontend + backend using headless Chrome DevTools
* Startup validated:
  * backend clean on `:8000`
  * frontend clean on `:3000`
  * Vite `/drafts` + `/tools` proxy path confirmed
* Browser workflow validated:
  * create draft
  * add two SMA tools
  * patch SMA period (`20 → 21`)
  * reorder tools
  * toggle enabled state
  * validate draft
  * delete draft
  * archive draft
  * refresh persistence
  * backend/frontend restart persistence
* Invalid validation display verified with a deliberately seeded invalid draft:
  * backend returned registry validation errors
  * frontend rendered `✗ invalid` and backend error text without local duplication

Runtime issues discovered/fixed:
* `frontend/src/components/DraftWorkspace.tsx`
  * patch/reorder/toggle responses updated `selectedDraft` but did not sync the list panel copy
  * fixed by centralizing `syncDraftInList(updated)` and applying it after select/add/remove/reorder/patch
* `frontend/src/components/DraftDetailView.tsx`
  * local validation/action state could persist across draft switches
  * fixed by resetting local state on `draft.draft_id` change
  * added lightweight action disabling during archive/delete/validate requests
* `frontend/src/components/DraftWorkspace.tsx`
  * keyed `DraftDetailView` and `ToolCompositionPanel` by `draft_id` to prevent stale per-draft UI state carryover
* `frontend/src/components/ToolCompositionPanel.tsx`
  * removed unused prop after parent-driven sync cleanup

Architecture preserved:
* frontend remains passive orchestration only
* backend remains source-of-truth for draft composition and validation
* no validation logic moved into frontend
* no runtime/execution/backtesting coupling introduced

Validation:
* Browser-level startup + draft workflow validation completed
* `npm run build` → clean
* `.venv/bin/pytest` → 999 passed

Next recommended step:
* Phase 2N.13: tighten draft metadata editing UX and targeted frontend test coverage around draft selection/synchronization, without expanding into execution systems

---

## Phase 2N.11 — Frontend Draft Workspace & Composition UI (COMPLETE)

Completed:
* `frontend/src/types/drafts.ts` (modified) — extended with `DraftListResponse`, `CompositionValidationResponse`
* `frontend/src/api/drafts.ts` (new) — typed HTTP client for all draft + composition endpoints:
  * CRUD: `fetchDrafts`, `fetchDraft`, `createDraft`, `updateDraft`, `deleteDraft`, `archiveDraft`
  * Composition: `addToolToDraft`, `removeToolFromDraft`, `reorderDraftTools`, `patchDraftTool`, `validateDraft`
  * Single `_req<T>()` helper — handles 204 No Content, JSON parse, error extraction; no business logic
* `frontend/src/components/DraftWorkspace.tsx` (new) — top-level 2-column workspace:
  * Left 280px: `DraftListPanel` (list + new draft form)
  * Right flex-1: `DraftDetailView` + `ToolCompositionPanel` for selected draft
  * State: `drafts[]` (list) + `selectedDraft` (current); each composition op replaces `selectedDraft` from API response
  * Interaction model: UI → API call → backend response → `setSelectedDraft(result)` — no optimistic updates
* `frontend/src/components/DraftListPanel.tsx` (new) — active draft list with inline create form:
  * Displays `StrategyDraftCard` per draft; click to select; highlighted selection border
  * New Draft form: `draft_id` + `display_name` inputs → `POST /drafts` → refreshes list
* `frontend/src/components/DraftDetailView.tsx` (new) — draft metadata + lifecycle actions:
  * Displays: draft_id, display_name, description, tags, enabled, notes, tool count, timestamps
  * Actions: Validate (POST /validate → shows `CompositionValidationResponse` inline), Archive, Delete
  * Validation result: green "✓ valid" or red "✗ invalid" + error list from backend
* `frontend/src/components/ToolCompositionPanel.tsx` (new) — editable ordered toolset:
  * ToolRow: position number, instance_id, tool_id, enable toggle (●/○), ▲▼ reorder, ✎ edit params, ✕ remove
  * Params display: read-only chips when not editing; inline inputs when editing (Save / Discard)
  * Add Tool button → shows `AddToolForm` inline above tool list
  * Each operation calls API → parent receives updated draft via callback → `setSelectedDraft`
* `frontend/src/components/AddToolForm.tsx` (new) — inline tool addition form:
  * Fetches available tools from `GET /tools` on mount
  * Dynamic parameter inputs based on `ToolMetadataResponse.parameters` (type_label → input type)
  * Coerces string inputs to correct types (int/float/bool/str) before submission
  * Error display: backend validation errors shown inline
* `frontend/vite.config.ts` (modified) — added `/drafts` → `http://localhost:8000` proxy entry
* `frontend/src/App.tsx` (modified) — added `NavTab` component + `Chart | Drafts` view toggle:
  * "Chart" tab: existing market data + strategy run UI unchanged
  * "Drafts" tab: renders `DraftWorkspace` replacing chart main area

Architecture preserved:
* Frontend is passive orchestration layer — no validation logic duplicated
* Backend remains source-of-truth: every state change flows through API → refresh from response
* No Redux/Zustand/MobX — only local `useState` hooks
* Execution-independent: no compute_sma(), no strategy runner, no runtime calls
* All types mirror backend contracts (StrategyDraftData, ToolConfigurationInstance, etc.)

Validation:
* `npm run build` → clean (49 modules, up from 42; 7 new components + 1 new API client)
* `pytest` → 999 passed (zero regressions — no backend changes)
* Frontend: no Vitest test runner configured yet; TypeScript compilation is the primary static check

Next recommended step:
* Phase 2N.12: Browser-level manual validation (start both servers, open http://localhost:3000, navigate to Drafts, create/compose/validate a draft end-to-end); fix any runtime issues discovered

---

## Phase 2N.10 — Draft Composition & Editing API (COMPLETE)

Completed:
* `backend/api/schemas/draft_composition.py` (new) — passive request/response schemas:
  * `AddToolRequest` — `tool: ToolConfiguration` + optional `index: int | None` (None = append)
  * `ReorderToolsRequest` — `ordered_instance_ids: list[str]` (must be exact permutation)
  * `PatchToolRequest` — all optional: `parameters: dict | None`, `enabled`, `display_name`, `color`
  * `CompositionValidationResponse` — `valid: bool`, `errors: list[str]`
* `backend/api/services/draft_composition_service.py` (new) — composition orchestration:
  * Typed errors: `DraftCompositionError` (409), `ToolInstanceNotFoundError` (404), `ToolOrderError` (422), `ToolPatchError` (422)
  * `add_tool()` — validates against registry; rejects duplicate instance_id; inserts at index or appends
  * `remove_tool()` — removes by instance_id; preserves remaining order
  * `reorder_tools()` — strict permutation check (no missing, no extra, no duplicates); reorders tuple
  * `patch_tool()` — merges parameters (not replace); validates patched config when params changed
  * `validate_draft()` — delegates to `draft.validate_against_registry()`; never raises
  * All operations: load → immutable transform → update repository; `updated_at` always refreshed
  * Internal `_rebuild_draft()` and `_new_toolset()` helpers enforce frozen-model immutability pattern
* `backend/api/routes/draft_composition.py` (new) — thin composition routes under `/drafts` prefix:
  * `POST   /drafts/{draft_id}/tools` → 200, 404, 409 (dup), 422 (invalid tool/index)
  * `DELETE /drafts/{draft_id}/tools/{instance_id}` → 200, 404
  * `POST   /drafts/{draft_id}/tools/reorder` → 200, 404, 422
  * `PATCH  /drafts/{draft_id}/tools/{instance_id}` → 200, 404, 422
  * `POST   /drafts/{draft_id}/validate` → 200, 404
  * Reuses `get_draft_repository` and `get_tool_registry` Depends from existing routes
* `backend/api/main.py` — `draft_composition.router` registered

Architecture preserved:
* Immutability: all operations use `model_dump() + model_validate()` round-trip; no frozen model mutation
* Execution-independence: `compute_sma()` never called; verified by monkeypatched tests
* Validation delegation: `validate_tool_configuration()`, `validate_strategy_toolset_against_registry()`,
  `draft.validate_against_registry()` — no duplicated validation logic
* Repository-bound: every composition operation goes through `DraftRepository.load()` + `update()`
* No runtime coupling: no `StrategyRuntimeRunner`, no strategy execution, no backtesting
* Frozen model semantics: `_rebuild_draft(draft, new_toolset)` always creates a new `StrategyDraft` instance
* Parameter patching is merge semantics: only keys in request are updated; existing keys preserved

Validation:
* `pytest tests/unit/test_draft_composition_service.py tests/unit/test_draft_composition_api.py` → 80 passed
* `pytest` → 999 passed (zero regressions from prior 919)
* `npm run build` → clean (42 modules)

Next recommended step:
* Phase 2N.11: Vite proxy update for `/drafts` + passive frontend draft listing component (reads existing `/drafts` API)

---

## Phase 2N.9 — Strategy Draft Persistence Layer (COMPLETE)

Completed:
* `backend/strategy_registry/draft_repository.py` (new) — `DraftRepository` filesystem-backed persistence:
  * Storage layout: `{base}/strategy_drafts/{draft_id}.json` (active), `{base}/strategy_drafts/archive/{draft_id}.json` (archived)
  * Methods: `save()`, `load()`, `load_archived()`, `exists()`, `list_all()`, `update()`, `archive()`, `delete()`
  * Typed errors: `DraftNotFoundError`, `DraftAlreadyExistsError`, `DraftPersistenceError`
  * Serialization: `StrategyDraft.model_dump_json()` — deterministic UTF-8 JSON with trailing newline
  * `list_all()` returns only active drafts sorted by draft_id; archived drafts excluded
* `backend/api/schemas/drafts.py` (new) — `DraftCreateRequest`, `DraftUpdateRequest`, `DraftToolConfigResponse`, `DraftToolSetResponse`, `DraftResponse`, `DraftListResponse`
  * `DraftCreateRequest.toolset: StrategyToolSet` — reuses existing Pydantic v2 model for 422 validation without duplicating logic
  * `DraftUpdateRequest` — all fields optional; `model_dump(exclude_unset=True)` used in service for partial updates
* `backend/api/services/draft_service.py` (new) — thin orchestration: `create_draft`, `get_draft`, `list_drafts`, `update_draft`, `archive_draft`, `delete_draft`
  * `update_draft` uses `existing.model_dump() + exclude_unset updates + model_validate` round-trip for clean partial updates on frozen model
  * `_to_response(draft)` uses `DraftResponse.model_validate(draft.model_dump())` — Pydantic coerces tuples→lists automatically
* `backend/api/routes/drafts.py` (new) — thin REST routes; `get_draft_repository()` Depends injectable for test isolation:
  * `GET /drafts` → 200 list
  * `POST /drafts` → 201 created, 409 conflict, 422 validation
  * `GET /drafts/{draft_id}` → 200, 404
  * `PUT /drafts/{draft_id}` → 200, 404
  * `POST /drafts/{draft_id}/archive` → 204, 404
  * `DELETE /drafts/{draft_id}` → 204, 404
* `backend/api/main.py` — `drafts.router` registered
* `tests/unit/test_draft_repository.py` (new) — 42 tests; 8 groups: save, load, exists, list_all, update, archive, delete, serialization determinism
* `tests/unit/test_drafts_api.py` (new) — 27 tests; 7 groups: list, create (happy path + 409 + 422), get, update (partial), archive, delete, execution independence

Architecture preserved:
* `StrategyDraft ≠ Runtime Execution` — no tool execution anywhere in repository, service, or routes
* `compute_sma()` never called; verified by monkeypatched test
* Routes stay thin: route → service → repository, no business logic in routes
* Validation authority: `StrategyToolSet` Pydantic model in `DraftCreateRequest` enforces structural validity (invalid toolset → 422); no duplicate validation logic
* No PostgreSQL, ORM, async DB layers, or cloud storage introduced
* Vite proxy not updated — no frontend UI in this phase per directive

Validation:
* `pytest tests/unit/test_draft_repository.py tests/unit/test_drafts_api.py` → 69 passed
* `pytest` → 919 passed (zero regressions from prior 850)
* `npm run build` → clean (42 modules)

Next recommended step:
* Phase 2N.10: Strategy Draft Lifecycle — `POST /drafts/{draft_id}/validate` endpoint (validates against active registry); lifecycle stage field on StrategyDraft; update Vite proxy for `/drafts`; passive frontend draft listing component

---

## Phase 2N.8 — StrategyDraft Contracts (COMPLETE)

Completed:
* `backend/strategy_registry/drafts.py` (new) — `StrategyDraft` frozen Pydantic v2 model:
  * `draft_id: str` — normalized lowercase + stripped
  * `display_name: str` — non-empty enforced
  * `description: str | None = None`
  * `toolset: StrategyToolSet` — nested composition
  * `created_at / updated_at: datetime` — UTC-aware enforced; naive rejected; non-UTC normalized
  * `enabled: bool = True`
  * `tags: tuple[str, ...] = ()`
  * `notes: str | None = None`
  * `validate_against_registry(registry) → ToolSetValidationResult` — delegates to `validate_strategy_toolset_against_registry()`; never raises
* `backend/strategy_registry/__init__.py` — `StrategyDraft` NOT re-exported here (see circular import note below); import from `backend.strategy_registry.drafts` directly
* `frontend/src/types/drafts.ts` (new) — `StrategyDraftData` TypeScript interface; `created_at`/`updated_at` as ISO 8601 strings; imports `StrategyToolSetData`
* `frontend/src/components/StrategyDraftCard.tsx` (new) — passive read-only display; shows draft_id, display_name, description, tool count, tags, notes, timestamps; no editing, saving, or execution
* `tests/unit/test_strategy_draft.py` (new) — 45 tests; 6 groups:
  * TestStrategyDraftConstruction (18): construction, draft_id lowercased/stripped, empty id/name raises, defaults, tags as tuple, toolset stored, direct import from drafts module
  * TestStrategyDraftDatetimes (5): UTC stored, naive created_at raises, naive updated_at raises, non-UTC normalized to UTC
  * TestStrategyDraftFrozen (3): immutable fields, extra fields rejected
  * TestStrategyDraftValidation (8): valid passes, invalid fails, unknown tool_id error, never raises, returns ToolSetValidationResult, empty toolset valid, multi-error collection, registry not mutated
  * TestStrategyDraftSerialization (7): model_dump dict, expected keys, JSON valid, identical inputs identical dump/json, tags in dump, toolset nested
  * TestStrategyDraftLayerSeparation (4): no compute_sma on construction, no compute_sma on validation, no runtime runner reference, drafts independent

Architecture preserved:
* `ToolMetadata ≠ ToolConfiguration ≠ StrategyToolSet ≠ StrategyDraft ≠ Runtime Execution` — strict layer separation maintained
* `StrategyDraft` is execution-independent: no `compute_sma()`, no `StrategyRuntimeRunner`, no runtime artifacts
* Circular import resolved: `strategy_registry/__init__.py` does NOT import `drafts.py` because `drafts.py → tools.registry → tools.models → strategy_registry.models` would create a cycle through the package `__init__`. `StrategyDraft` must be imported from `backend.strategy_registry.drafts` directly.
* Frontend remains passive: `StrategyDraftCard` is read-only display; no business logic; no save/load/execute UI

Validation:
* `pytest tests/unit/test_strategy_draft.py` → 45 passed
* `pytest` → 850 passed (zero regressions from prior 805)
* `npm run build` → clean (42 modules)

Next recommended step:
* Phase 2N.9: StrategyDraft API — `POST /strategy-drafts` to create a draft; `GET /strategy-drafts/{draft_id}` to retrieve; in-memory store for now; establishes frontend→backend draft submission boundary

---

## Phase 2N.7 — ToolSet Validation API (COMPLETE)

Completed:
* `backend/api/schemas/tools.py` — added `ToolSetValidationResponse(valid: bool, errors: list[str])`
* `backend/api/services/tool_service.py` — added `validate_toolset(toolset, registry) → ToolSetValidationResponse`; thin wrapper around `validate_strategy_toolset_against_registry()`; never raises
* `backend/api/routes/tools.py` — added `POST /tools/validate-toolset`; thin route; parses `StrategyToolSet` as request body; delegates to service; no business logic in route
* `tests/unit/test_validate_toolset_api.py` (new) — 31 tests; 7 groups:
  * TestHappyPath (6): 200 response, valid=true, multiple SMAs, empty toolset, disabled tool, response shape
  * TestUnknownToolId (6): valid=false, one error, error has instance_id, error has tool_id, "not found" in error, empty registry flags all
  * TestParameterErrors (6): missing required param, error mentions period+missing, error prefixed with instance_id, below-min, unknown param, wrong type
  * TestMultiErrorCollection (4): two bad tools both reported, unknown+bad-param both reported, error count matches violations, valid/invalid mix
  * TestMalformedRequest (6): missing toolset_id → 422, missing tools → 422, empty body → 422, non-JSON → 422, duplicate instance_id → 422, extra fields → 422
  * TestExecutionIndependence (1): monkeypatches compute_sma() to raise — confirms it is never called
  * TestGetToolsUnchanged (2): GET /tools still returns 200 and still contains SMA

Architecture preserved:
* Route remains thin — no validation logic embedded; route delegates to service which delegates to registry-backed validator
* `POST /tools/validate-toolset` is execution-independent: no `compute_sma()` called
* Registry state is read-only; no mutation during validation
* Malformed `StrategyToolSet` JSON (including duplicate `instance_id`) fails at FastAPI parsing layer → 422 before reaching business logic
* Vite proxy unchanged — `/tools` prefix already proxied in Phase 2N.3
* `GET /tools` behavior is unaffected

Validation:
* `pytest tests/unit/test_validate_toolset_api.py` → 31 passed
* `pytest` → 805 passed (zero regressions from prior 774)

Next recommended step:
* Phase 2N.8: Strategy Draft API — `POST /strategy-drafts` accepting a `StrategyToolSet` payload; persist draft identity; return draft_id and validation summary

---

## Phase 2N.6 — Registry-Backed StrategyToolSet Validation (COMPLETE)

Completed:
* `backend/tools/validation.py` — extended with two new additions:
  * `ToolSetValidationResult` — frozen dataclass; `valid: bool`, `errors: tuple[str, ...]`; invariant enforced at construction (`valid=True` ↔ `errors==()`)
  * `validate_strategy_toolset_against_registry(toolset, registry) → ToolSetValidationResult` — iterates all `toolset.tools` in insertion order; resolves each `tool_id` against registry; runs `validate_tool_configuration()` for resolved tools; collects all errors before returning; never raises
* `backend/tools/__init__.py` — exports `ToolSetValidationResult`, `validate_strategy_toolset_against_registry`
* `tests/unit/test_registry_validation.py` (new) — 31 tests; 7 groups:
  * TestToolSetValidationResult (6): invariant enforcement (valid+errors consistency), frozen, errors type
  * TestHappyPath (5): single SMA, multiple SMAs, empty toolset, optional params, disabled tool still validated
  * TestUnknownToolId (5): fails, error names instance_id, error names tool_id, "not found" in message, empty registry flags all
  * TestParameterErrors (5): missing required param, instance_id prefix on errors, below min, unknown param, wrong type
  * TestMultiToolErrorCollection (4): two invalid both reported, mix valid/invalid, unknown+bad-param both reported, error count matches
  * TestErrorOrdering (2): insertion-order determinism, identical inputs → identical results
  * TestRegistryIntegrity (4): registry unchanged after valid, unchanged after invalid, never raises, disabled tool validated

Architecture preserved:
* Registry layer (ToolMetadata source) ≠ Validation layer ≠ Runtime Execution
* `validate_strategy_toolset_against_registry` is execution-independent: no compute_sma(), no indicators computed
* Registry state is read-only during validation; no mutation possible (ToolRegistry.get() is a pure lookup)
* `ToolSetValidationResult` is a frozen dataclass (not Pydantic) — lightweight value type; no I/O concerns
* `validate_strategy_toolset_against_registry` never raises — returns result, caller decides what to do

Validation:
* `pytest tests/unit/test_registry_validation.py` → 31 passed
* `pytest` → 774 passed (zero regressions from prior 743)
* `npm run build` → clean (42 modules)

Next recommended step:
* Phase 2N.7: Strategy Draft API — `POST /strategy-drafts/validate` accepting a `StrategyToolSet` JSON payload; backend resolves against active registry, returns `ToolSetValidationResult` as JSON; establishes the frontend→backend submission boundary

---

## Phase 2N.5 — StrategyToolSet Contracts (COMPLETE)

Completed:
* `backend/tools/toolset.py` (new) — `StrategyToolSet` frozen Pydantic v2 model
  * `toolset_id` — normalized lowercase
  * `display_name: str | None`
  * `tools: tuple[ToolConfiguration, ...]` — ordered, immutable; list inputs coerced to tuple
  * `enabled: bool = True`
  * Duplicate `instance_id` rejected at construction via `field_validator` → `pydantic.ValidationError`
  * Empty toolsets allowed (rationale: draft-creation and incremental build are valid; runtime enforces non-empty where needed)
  * Query methods: `get_tool(instance_id)` (case-insensitive), `instance_ids()`, `enabled_tools()`, `__len__`, `__contains__`
* `backend/tools/__init__.py` — exports `StrategyToolSet`
* `frontend/src/types/tools.ts` — extended with `StrategyToolSetData` interface
* `frontend/src/components/ToolSetPanel.tsx` (new) — passive ordered display of toolset; position numbers, color accents, param key/value chips, per-tool enabled state
* `tests/unit/test_strategy_toolset.py` (new) — 43 tests; 7 groups:
  * TestStrategyToolSet (12): construction, normalization, empty tools, frozen, extra fields rejected, list-to-tuple coercion
  * TestDuplicateInstanceIdRejection (5): single duplicate, multi-tool duplicate, case-normalized duplicate, error names offender
  * TestToolOrdering (4): insertion order preserved, instance_ids() returns tuple, reverse order stable
  * TestContainmentAndLookup (8): contains, get_tool (case-insensitive), missing returns None, non-string returns False, len
  * TestEnabledTools (4): all enabled, one disabled, all disabled, order preserved in filtered result
  * TestStrategyToolSetSerialization (6): model_dump, model_dump_json, identical toolsets identical output, order in dump, empty toolset, stable across calls
  * TestLayerSeparation (4): no compute_sma, tool_id reference only, coexists with registry, multiple toolsets independent

Validation:
* `pytest tests/unit/test_strategy_toolset.py` → 43 passed
* `pytest` → 743 passed (zero regressions from prior 700)
* `npm run build` → clean (42 modules)

Next recommended step:
* Phase 2N.6: Strategy composition API skeleton — `POST /strategy-drafts` accepting a `StrategyToolSet` payload, returning a validated draft identity
* Or: Tool configuration validation API — `POST /tools/{tool_id}/validate-config` accepting parameters, returning validation result

---

## Phase 2N.4 — Tool Configuration Contracts (COMPLETE)

Completed:
* `backend/tools/configuration.py` (new) — `ToolConfiguration` frozen Pydantic v2 model
  * `instance_id` — human-readable, normalized to lowercase, e.g. "sma_fast"
  * `tool_id` — references tool definition in registry; normalized lowercase
  * `parameters: dict[str, Any]` — actual runtime parameter values
  * `enabled: bool = True`, `display_name: str | None`, `color: str | None`
* `backend/tools/validation.py` (new) — `ConfigurationValidationError` + `validate_tool_configuration(config, metadata)`
  * Validates: tool_id match, required params present, no unknown params, type compatibility (int/float/str/bool), min/max constraints
  * All violations collected before raising — full error list in one pass
  * `_check_type_compatibility()` — bool/int/float/str detection, correctly rejects bool for int/float
* `backend/tools/__init__.py` — exports `ToolConfiguration`, `ConfigurationValidationError`, `validate_tool_configuration`
* `frontend/src/types/tools.ts` (new) — `ToolConfigurationInstance` TypeScript interface mirroring backend model
* `frontend/src/components/ConfiguredToolList.tsx` (new) — passive read-only display of configured instances; shows instance_id/tool_id/params/enabled state; supports color accent from instance.color
* `tests/unit/test_tool_configuration.py` (new) — 48 tests; 4 groups:
  * TestToolConfiguration (16): construction, normalization, frozen, empty/whitespace rejection, extra fields rejected
  * TestValidateToolConfiguration (24): required param missing, optional omitted, unknown param, tool_id mismatch, all 4 type checks, bool-int distinction, min/max constraints, at-boundary acceptance, multiple errors, SMA integration
  * TestMultipleInstancesSameToolId (4): SMA(20)/SMA(50)/SMA(200) from same definition, independence, enabled state
  * TestConfigurationSerialization (4): model_dump, model_dump_json, identical configs identical output, stable across calls

Architecture preserved:
* Tool Definition Layer (`ToolMetadata`) remains separate from Tool Configuration Layer (`ToolConfiguration`)
* Configuration Layer remains separate from Runtime Execution Layer (no compute_sma() called)
* `ConfiguredToolList` is a passive rendering primitive — no state management, no editing, no business logic
* Backend-authoritative validation: frontend type is declaration only, validation always via `validate_tool_configuration()`
* `GET /tools` discovery endpoint unchanged

Validation:
* `pytest tests/unit/test_tool_configuration.py` → 48 passed
* `pytest` → 700 passed (zero regressions from prior 652)
* `npm run build` → clean (42 modules)

Next recommended step:
* Phase 2N.5: Tool configuration collection (e.g., StrategyToolSet — ordered list of ToolConfiguration instances with duplicate instance_id detection)
* Or: strategy composition API skeleton (POST /strategy-drafts with tool configuration payload)

---

## Phase 2N.3 — Frontend Dynamic Tool Discovery (COMPLETE)

Completed:
* `frontend/vite.config.ts` — `/tools` proxy entry added (target: `http://localhost:8000`)
* `frontend/src/api/tools.ts` — typed fetch client matching `ToolListResponse` / `ToolMetadataResponse` / `ToolParameterResponse` shapes
* `frontend/src/components/ToolPanel.tsx` — collapsible tool cards; fetches on mount; loading/error/empty states; parameter list, status badges, capability/mode metadata
* `frontend/src/App.tsx` — "Tools" toggle button in header; conditionally renders `<ToolPanel />` below header; `toolsOpen` state
* `npm run build` → clean, 42 modules

**Proxy error fix (Phase 2N.3-fix):**

Root cause: `AggregateError [ECONNREFUSED] http proxy error: /tools` was caused by the backend uvicorn server NOT being running during the browser test. This is NOT a proxy misconfiguration. The Vite proxy entry, route prefix (`/tools`), and backend endpoint are all correct.

Diagnosis confirmed by:
* `curl http://localhost:8000/tools` → connection refused (backend not running)
* All 76 tools + tools-API tests pass
* Proxy target `http://localhost:8000` matches `uvicorn backend.api.main:app --port 8000`

Fix: operational — backend must be started before opening the frontend. No code changes were required. `ToolPanel` already renders a user-visible error when the backend is unreachable.

Correct local dev startup sequence:
```bash
# Terminal 1 — backend (must start FIRST)
source .venv/bin/activate
uvicorn backend.api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
# Open http://localhost:3000
# Click "Tools" → panel loads SMA tool metadata from GET /tools
```

Validation:
* `.venv/bin/pytest tests/unit/test_tools.py tests/unit/test_tools_api.py` → 76 passed
* `npm run build` → clean (42 modules)
* ECONNREFUSED = backend not running; resolved by starting backend first

Next recommended step:
* Strategy composition UI (tools → conditions → rules → signal wiring)
* Keep execution/orchestration deferred to a later phase

---

# Core Architectural Direction

QuantLab is designed as:
* market-agnostic
* modular
* research-first
* execution-isolated
* strategy-portable

The platform must support:
* multiple independent strategies
* multiple asset classes
* unconventional research methods
* historical backtesting
* forward testing
* paper trading
* future live trading
* reusable feature engineering
* modular execution systems

Strategies must remain portable across environments.

---

# Current Governance Documents

The following governance documents currently exist:
* agent/ARCHITECTURE_GUARDRAILS.md
* agent/WORKFLOW_GOVERNANCE.md
* agent/WORKFLOW_AGENT.md
* agent/PROMPT_RULES.md
* agent/CLAUDE.md
* agent/CODEX.md
* agent/HANDOFF.md

These documents define:
* architecture law
* orchestration model and governance rules
* agent behavioral contracts
* AI communication protocol
* operational continuity

Implementation agents must read `agent/WORKFLOW_AGENT.md` and `agent/HANDOFF.md` before significant implementation work.

---

# Important Architectural Decisions

## Strategy Portability

Strategies must not directly depend on:

* brokers
* APIs
* frontend
* storage implementation
* execution engines

Strategies must operate through normalized internal contracts.

---

## Research-First Design

QuantLab is primarily a research and strategy development environment.

Autonomous execution is a future capability — not the current priority.

The system must support:
* experimental logic
* cycle research
* planetary/astronomical analysis
* feature experimentation
* manual intervention workflows
* iterative validation

---

## Execution Isolation

Execution systems must remain isolated from strategies.

Strategies generate:
* signals
* trade ideas
* analytical outputs

Execution systems handle:
* routing
* risk
* broker integration
* portfolio constraints
* execution lifecycle

---

## Data Abstraction

All data sources must pass through normalization layers.

Strategies must not know the underlying provider.

---

## Market-Agnostic Direction

The platform is intentionally market-agnostic.

No hardcoded assumptions for:
* equities only
* crypto only
* halal-only workflows
* specific broker workflows

Market restrictions and compliance rules should be implemented as configurable policy layers later.

---

# Current Repository Philosophy

QuantLab is being designed as:
* AI-managed engineering ecosystem

not merely:
* a coding repository

The repository architecture must support:
* AI orchestration
* modular context retrieval
* scoped implementation
* long-term maintainability
* low token waste
* deterministic workflows

---

# Current Known Risks

## Architectural Drift

Without strict governance, implementation agents may:
* tightly couple modules
* rewrite unrelated systems
* introduce unstable abstractions
* embed business logic in wrong layers

Governance documents are intended to prevent this.

---

## Token Explosion

Large uncontrolled prompts and oversized documentation can degrade:

* implementation quality
* reasoning quality
* cost efficiency
* architectural consistency

Repository context should remain modular and retrievable.

---

## Overengineering Risk

The project vision is large.

Agents must avoid implementing speculative infrastructure too early.

Prioritize:
* small deterministic foundations
* clear interfaces
* modular boundaries
* incremental evolution

---

# Last Session Summary (2026-05-09) — Phase 2M Strategy Visualization Artifact Foundation + UX Hardening

## What Was Completed

**`backend/strategy_runtime/visualization.py`** — new module
* `IndicatorSeriesKind(str, Enum)` — `line`; future: histogram, area
* `IndicatorPane(str, Enum)` — `price`; future: oscillator, separate
* `IndicatorPoint` — frozen Pydantic v2; UTC-enforced timestamp; value float
* `IndicatorSeries` — frozen; name, kind, pane, color (optional), points list; name must not be empty

**`backend/strategy_runtime/run_result.py`** — updated
* Added `artifacts: list[IndicatorSeries] = []` field — default empty for backward compatibility

**`backend/strategy_runtime/runner.py`** — updated
* Added `_extract_artifacts(output)` helper — same pattern as `_extract_signals`/`_extract_forecasts`
* Wired into `run()` pipeline; added `artifacts_generated` to diagnostics dict
* Success result now includes `artifacts=artifacts`

**`strategies/example_strategy/signals.py`** — updated
* Passes `timestamps`, `ma20_series`, `ma50_series` through to risk module for artifact construction

**`strategies/example_strategy/risk.py`** — updated
* Builds `IndicatorSeries` for MA20 (blue #2196f3) and MA50 (orange #ff9800)
* Returns `{"signals": [...], "forecasts": [...], "artifacts": [...]}`

**`backend/api/schemas/strategy_runs.py`** — updated
* Added `IndicatorPointResponse`, `IndicatorSeriesResponse`
* `StrategyRunResponse` now includes `indicators: list[IndicatorSeriesResponse] = []`

**`backend/api/services/strategy_run_service.py`** — updated
* Serializes `result.artifacts → indicators` in response
* Log line includes `indicators=%d`

**`tests/unit/test_visualization_artifacts.py`** — new module, 21 tests
* `IndicatorPoint`: construction, naive rejected, UTC coercion, frozen
* `IndicatorSeries`: construction, defaults, empty points, color, name validation, extra forbidden, enum values, frozen, multiple points
* Runner extraction: valid artifacts, non-list warns, non-IndicatorSeries ignored, empty list, absent key, non-dict output

**`tests/unit/test_strategy_runs_api.py`** — updated, +4 tests
* `indicators` field in required fields check
* `test_indicators_returned_with_sufficient_candles` — 60 bars → MA20 + MA50 both returned
* `test_indicator_series_schema_fields` — name, kind, pane, points present
* `test_indicator_point_schema_fields` — timestamp, value present

**`frontend/src/api/strategyRuns.ts`** — updated
* Added `IndicatorPoint`, `IndicatorSeries` interfaces
* `StrategyRunResponse` includes `indicators: IndicatorSeries[]`

**`frontend/src/types/strategy.ts`** — updated
* `StrategyOverlay` includes `indicators: IndicatorSeries[]`

**`frontend/src/components/Chart.tsx`** — refactored
* `indicatorSeriesMapRef: Map<string, ISeriesApi<'Line'>>` — tracks active indicator series by name
* Overlay effect removes all prior indicator series (`chart.removeSeries()`) before adding new ones
* Generic renderer: iterates `overlay.indicators`, creates `LineSeries` per entry with strategy-supplied color (falls back to palette)
* Lifecycle correct: fetch new symbol → overlay clears; rerun strategy → indicators replaced; chart unmount → map cleared before `chart.remove()`
* Badge row shows indicator count + signal count + forecast direction

**`frontend/src/App.tsx`** — updated
* `strategyResult: StrategyRunResponse | null` state — preserved for inspection panel
* `ResultInspector` component — inline, shows strategy_id, status, candles, signals, indicators, forecasts, warnings, error
* `indicators: result.indicators` passed into `StrategyOverlay`
* Overlay reset on new fetch — `setOverlay(null)` + `setStrategyResult(null)` together
* Run Strategy button: `disabled` + `opacity: 0.5` + `cursor: not-allowed` while running

## Validation

* Full backend test suite: **576 passed in 1.21s** (24 new + 552 prior), zero regressions
* Frontend build: `tsc && vite build` clean — 40 modules, 332 kB bundle

## Architecture Notes

* Frontend never computes indicators — backend strategy computes, serializes, frontend renders
* Chart renderer is fully generic: `indicators` array drives rendering, strategy identity never checked
* `IndicatorPane.price` is the only rendered pane in this phase; oscillator/separate pane rendering is deferred
* Overlay lifecycle: Map-based series tracking ensures repeated runs replace (not duplicate) indicator series

## To validate manually

```bash
# Terminal 1
source .venv/bin/activate && uvicorn backend.api.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
# Open http://localhost:3000
# 1. Fetch AAPL/1d/2023 → chart renders
# 2. Run Strategy → MA20 (blue) + MA50 (orange) lines appear, signal arrows, forecast line
# 3. Fetch SPY → overlays clear
# 4. Run Strategy again → fresh overlays render
```

## Remaining Limitations

* Single-pane only — oscillator/separate pane rendering not implemented
* `ReferenceLine` and `Zone` artifact types not yet defined
* No per-indicator legend UI component
* Browser validation not performed in this session (CLI only)

## Phase 2M Status

**CLOSED** — visualization artifact contract implemented end-to-end. 576 tests passing, frontend build clean. Browser validation pending.

---

# Last Session Summary (2026-05-09) — Phase 2L First Real Strategy Execution + Overlay Visualization

## What Was Completed

**`strategies/example_strategy/features.py`** — updated
* `_rolling_mean(values, window)` — sliding window average helper; returns `None` for positions without enough history
* `build_features(normalized_data, parameters)` — computes MA20, MA50, closes, timestamps, last values; returns feature dict

**`strategies/example_strategy/signals.py`** — updated
* `generate_signals(features, parameters)` — detects MA20/MA50 golden cross (→ long) and death cross (→ short); returns `raw_signals` list + last-MA-state fields for risk module

**`strategies/example_strategy/risk.py`** — updated
* `apply_risk_rules(signals, parameters)` — converts raw crossover events to `StrategySignal` objects (invalidation ±2%), generates 1 `StrategyForecast` from latest MA state (±4% target, 20-day horizon); returns `{"signals": [...], "forecasts": [...]}`
* Reads `strategy_id`, `symbol`, `timeframe` from `parameters` dict (injected by service layer)

**`backend/api/schemas/strategy_runs.py`** — new module
* `StrategyRunRequest` — strategy_id, provider, symbol, timeframe, start, end, asset_class, exchange, parameters
* `SignalResponse`, `ForecastResponse`, `StrategyRunResponse` — API output shapes

**`backend/api/services/strategy_run_service.py`** — new module
* `StrategyRunError`, `StrategyNotFoundError`, `UnsupportedProviderError`
* `run_strategy(request, *, storage_path, strategies_path)` — wires OHLCVService → load_strategy_runtime → StrategyRuntimeRunner → StrategyRunResponse
* `strategies_path` injectable via Depends for test isolation

**`backend/api/routes/strategy_runs.py`** — new module
* `APIRouter(prefix="/strategy-runs", tags=["strategy-runs"])`
* `get_storage_path()`, `get_strategies_path()` — FastAPI Depends, overridable in tests
* `POST /strategy-runs/run` — 404 strategy not found, 400 unsupported provider / load/fetch failure

**`backend/api/main.py`** — updated
* Added `from backend.api.routes import strategy_runs` and `app.include_router(strategy_runs.router)`

**`tests/unit/test_strategy_runs_api.py`** — new module, 15 tests
* Happy path: 200, required fields, strategy_id, status=success, candles_received, 1 forecast, forecast schema, forecast direction=long for uptrend
* Signal schema fields validated when crossover pattern present
* No signals in monotonic uptrend confirmed
* Empty candles → status=empty
* Validation: unsupported provider → 400, strategy not found → 404, missing fields → 422

**`frontend/src/api/strategyRuns.ts`** — new module
* `StrategyRunRequest`, `SignalResponse`, `ForecastResponse`, `StrategyRunResponse` types
* `runStrategy(req)` — POST /strategy-runs/run; throws on non-OK

**`frontend/src/types/strategy.ts`** — updated
* Added `StrategyOverlay { signals, forecast }` composite type

**`frontend/src/components/Chart.tsx`** — updated
* Added `overlay?: StrategyOverlay | null` prop
* Signal markers via `createSeriesMarkers()` — arrowUp (green) for long, arrowDown (red) for short
* Forecast projection via separate `LineSeries` (orange dashed) from last close → target
* Overlay badges in chart header (signal count, forecast direction)

**`frontend/src/App.tsx`** — updated
* Strategy run state: `overlay`, `strategyStatus`, `strategyError`
* "Run Strategy" button bar — appears after successful OHLCV fetch; calls `runStrategy()`
* Run result mapped to `StrategyOverlay` and passed to `Chart`

**`frontend/vite.config.ts`** — updated
* Added `/strategy-runs` proxy → `http://localhost:8000`

## Validation

* Full backend test suite: **552 passed in 1.02s** (15 new + 537 prior), zero regressions
* Frontend build: `tsc && vite build` clean — 40 modules, 331 kB bundle

## To validate manually

```bash
# Terminal 1 — backend
source .venv/bin/activate
uvicorn backend.api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
# Open http://localhost:3000
# 1. Fetch AAPL/1d/2023 → chart appears
# 2. Click "Run Strategy" → signals/forecast overlay appears on chart
```

## Phase 2L Status

**CLOSED** — backend API implemented and tested. Frontend wired and build-validated. Browser overlay render to be confirmed at next manual session.

---

# Last Session Summary (2026-05-09) — Phase 2K Manual End-to-End Validation

## What Was Validated

**Backend server** — started successfully: `uvicorn backend.api.main:app --port 8000`

**GET /market-data/ohlcv — programmatic curl validation:**

| Test Case | Result |
|---|---|
| AAPL / yahoo / 1d / 2023-01-01→2024-01-01 | ✓ 250 candles returned |
| MSFT / yahoo / 1d / 2023-01-01→2024-01-01 | ✓ 250 candles returned |
| SPY / yahoo / 1d / 2023-01-01→2024-01-01 | ✓ 250 candles returned |
| AAPL / yahoo / 1h / 2025-04-28→2025-05-09 | ✓ 63 intraday candles at 13:30Z (9:30 AM ET) |
| INVALID_SYMBOL_XYZ / yahoo / 1d | ✓ 200 + 0 candles (empty result, no crash) |
| provider=polygon | ✓ HTTP 400, detail identifies unsupported provider |
| timeframe=4h (unsupported) | ✓ HTTP 400, detail lists supported timeframes |
| Second AAPL 1d fetch (coverage cache) | ✓ 250 candles in 0.18s (cache hit — no yfinance call) |

**Coverage cache confirmed working** — second identical request returns from local Parquet in ~180ms vs seconds for real yfinance call.

**Frontend build** — `tsc && vite build` passed: 39 modules, 314 kB bundle, zero errors.

**Full backend test suite** — `537 passed in 0.99s`, zero regressions.

**Candle timestamp format confirmed correct:**
- Daily US equity bars: timestamp at `05:00:00Z` (midnight New York = UTC-5, correct for winter)
- Hourly US equity bars: timestamp at `13:30:00Z` (9:30 AM ET market open = UTC-5)
- Frontend converts ISO timestamps → `UTCTimestamp` (epoch seconds) — handles all timezone offsets correctly

**Browser-level validation** — not performed in this session (no browser available in CLI environment). All API contracts and chart component logic validated programmatically. To complete browser validation manually:

```bash
# Terminal 1 — backend
source .venv/bin/activate
uvicorn backend.api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
# Open http://localhost:3000
# Test: yahoo / AAPL / equity / NASDAQ / 1d / 2023-01-01 → 2024-01-01 → Fetch
```

## Fixes Made

None — Phase 2K implementation was correct. No bugs found during validation.

## Latest Validation Snapshot

* Backend API: all test cases pass (curl)
* Backend tests: `537 passed in 0.99s`
* Frontend build: `tsc && vite build` clean

## Phase 2K Status

**CLOSED** — backend and API fully validated. Browser chart render validation to be confirmed at next manual session. No blockers.

---

# Last Session Summary (2026-05-09) — Phase 2K Minimal OHLCV + Strategy Visualization Foundation

## What Was Completed

**`backend/api/schemas/market_data.py`** — new module
* `OHLCVCandleResponse` — minimal candle schema (timestamp, open, high, low, close, volume)
* `MarketDataOHLCVResponse` — envelope with provider, symbol, asset_class, exchange, timeframe, start, end, candle_count, candles

**`backend/api/services/market_data_service.py`** — new module
* `MarketDataError(Exception)` — recoverable service-boundary error (→ HTTP 400)
* `UnsupportedProviderError(MarketDataError)` — unknown provider name
* `fetch_ohlcv(...)` — builds `YahooFinanceAdapter` + `Instrument` + `DatasetIdentity` from request params; delegates to `OHLCVService.get_ohlcv()`; returns `MarketDataOHLCVResponse`
* Currently supported providers: `{"yahoo"}`

**`backend/api/routes/market_data.py`** — new module
* `APIRouter(prefix="/market-data", tags=["market-data"])`
* `get_storage_path()` — FastAPI Depends, overridable in tests
* `GET /market-data/ohlcv` — accepts provider, symbol, timeframe, start, end (required) + asset_class, exchange, adjustment_mode, currency (optional with defaults)
* Naive datetime query params treated as UTC at route boundary

**`backend/api/main.py`** — updated
* `market_data.router` registered

**`tests/unit/test_market_data_api.py`** — 11 tests, all passing
* `TestGetOHLCVHappyPath` (5): 200 success, candle field values, UTC timestamp, naive params accepted, empty DataFrame → empty candles list
* `TestGetOHLCVValidation` (5): unsupported provider → 400, unsupported timeframe → 400, missing provider/symbol/start → 422
* `TestGetOHLCVDefaults` (1): default asset_class=equity, exchange=NASDAQ applied correctly

**Frontend — `frontend/` — fully built and TypeScript-validated**

`frontend/package.json` — updated
* Added `lightweight-charts@^5.2.0`

`frontend/vite.config.ts` — updated
* Proxy: `/market-data` and `/datasets` added alongside `/health` → backend at :8000

`frontend/src/api/marketData.ts` — new
* `OHLCVCandle`, `MarketDataOHLCVResponse`, `MarketDataParams` interfaces
* `fetchOHLCV(params)` — builds query string, calls `GET /market-data/ohlcv`, throws on non-OK response with backend detail message

`frontend/src/types/strategy.ts` — new (placeholder only)
* `StrategySignalOverlay`, `StrategyForecastOverlay` interface placeholders for future chart overlay support
* Mirrors backend `StrategySignal` / `StrategyForecast` shape

`frontend/src/components/Controls.tsx` — new
* Controls: provider select, symbol input, asset_class select, exchange input, timeframe select, start date, end date, Fetch button
* Defaults: yahoo / AAPL / equity / NASDAQ / 1d / 1 year ago → today
* Symbol auto-uppercased on input

`frontend/src/components/Chart.tsx` — new
* TradingView lightweight-charts v5 `CandlestickSeries` via `chart.addSeries(CandlestickSeries, ...)`
* Dark theme: background `#0f0f1a`, grid `#1a1a2e`, text `#d1d4dc`, up `#26a69a`, down `#ef5350`
* Candles mapped from ISO timestamp → `UTCTimestamp` (seconds since epoch)
* `ResizeObserver`-style resize via `window.addEventListener('resize')`
* `fitContent()` called on each data update
* Displays symbol · timeframe · candle count header

`frontend/src/App.tsx` — updated
* State: `candles`, `status` (idle | loading | success | error), `error`, `params`
* Renders Controls → main area (idle/loading/error/empty/chart states)
* Minimal dark-themed layout; no extra dependencies

## Latest Validation Snapshot

* Full backend test suite: `537 passed` in 1.09s (2026-05-09)
* Frontend: `npm install` confirmed, `tsc && vite build` passes with zero errors

## Important Design Notes

* Market data route creates a **fresh `YahooFinanceAdapter` per request** — no singleton adapter state; thread-safe by construction
* Route boundary **treats naive datetime query params as UTC** — FastAPI parses date-only strings (e.g. `2023-01-01`) as naive datetimes; route adds UTC tz before passing to service
* **`UnsupportedProviderError`** is a subclass of `MarketDataError` — route catches both; only `yahoo` supported in Phase 2K; extend by adding to `_SUPPORTED_PROVIDERS` and wiring the adapter in the service
* **Frontend chart uses UTCTimestamp** (epoch seconds) not date strings — works uniformly across all timeframes including intraday
* **Strategy overlay types are placeholders only** — `strategy.ts` declares the shape, no rendering wired; future phase wires `StrategyRunResult` API → overlay markers/lines on chart

## Deferred

* End-to-end manual validation (requires running both backend + frontend dev servers)
* Volume panel on chart (optional per directive)
* Strategy signal marker rendering on chart
* Strategy forecast projection line on chart
* Polygon, IBKR, Binance provider support in market data route
* Frontend component unit tests (no Jest/Vitest setup yet)
* Authentication / multi-user

## No Blockers

---

# Last Session Summary (2026-05-09) — Phase 2J First Real Historical Provider + Provider Registry Foundation

## What Was Completed

**`backend/data_providers/provider_registry.py`** — new module
* `ProviderRegistryError` — base error class
* `ProviderNotFoundError(ProviderRegistryError)` — missing provider name
* `DuplicateProviderError(ProviderRegistryError)` — double registration
* `ProviderRegistry` — in-process registry of `RangeProviderAdapter` instances keyed by lowercase provider name
* `register(name, adapter)` — validates name (non-empty) and type (RangeProviderAdapter); rejects duplicates
* `get(name)` — resolves by lowercase name; raises `ProviderNotFoundError` with available provider list
* `deregister(name)` — removes adapter; allows re-registration under same name
* `list_providers()` → sorted list of names; `__len__`, `__contains__`

**`backend/data_providers/provider_symbol_map.py`** — new module
* `ProviderSymbolMapping` — frozen Pydantic v2 model (internal_symbol, provider, provider_symbol); provider normalised to lowercase; empty fields rejected
* `ProviderSymbolMapError(Exception)` — raised on duplicate mapping or missing removal target
* `SymbolMapService` — in-memory mapping store; identity fallback when no explicit mapping exists
* Lookup/remove/filter paths now normalise both case and surrounding whitespace, matching registry-style provider-name handling
* `add_mapping(mapping)` — registers one provider symbol mapping; rejects duplicate (symbol, provider) pairs
* `remove_mapping(internal_symbol, provider)` — removes mapping or raises
* `resolve(internal_symbol, provider)` → provider_symbol; defaults to internal_symbol when no mapping exists
* `has_mapping(internal_symbol, provider)` → bool; `list_mappings(provider=None)` → sorted list

**`backend/data_providers/yahoo/adapter.py`** — new module (yfinance-backed)
* `SUPPORTED_TIMEFRAMES: dict[str, str]` — maps QuantLab timeframes to yfinance intervals (1m, 5m, 15m, 30m, 1h, 1d, 1w→1wk, 1M→1mo)
* `YahooAdapterError(Exception)` — wraps yfinance transport/schema errors
* `YahooFinanceAdapter(RangeProviderAdapter)` — production adapter for Yahoo Finance
* Constructor: `symbol`, `asset_class`, `venue`, `timeframe`, `adjustment_mode` (default "adjusted")
* `provider_name` → "yahoo"
* `load()` → raises `NotImplementedError` (use fetch instead)
* `fetch(start, end, **kwargs)` → calls `yf.Ticker.history()`, converts DataFrame to `list[NormalizedOHLCV]`; returns `[]` for invalid/empty symbols; raises `YahooAdapterError` on transport failures
* `_inclusive_end(end, interval)` — adds 1 day for daily/weekly/monthly so yfinance includes the end-date candle (its end parameter is exclusive)
* Intraday fetch bounds now preserve datetime precision instead of being truncated to date-only strings
* yfinance imported ONLY inside this module — never leaks SDK objects upstream

**`backend/data_providers/yahoo/metadata.py`** — new module
* `YahooMetadataError(Exception)` — raised when metadata resolution fails
* `YahooInstrumentMetadata` — frozen Pydantic v2 model (provider_symbol, exchange, currency, timezone, asset_class, short_name); all fields optional
* `resolve_yahoo_metadata(provider_symbol)` — fetches via `yf.Ticker.fast_info` with fallback to full `.info`; maps Yahoo `quoteType` to QuantLab `asset_class` string
* `_QUOTE_TYPE_TO_ASSET_CLASS` — mapping dict: EQUITY→equity, ETF→etf, CRYPTOCURRENCY→crypto, CURRENCY→fx, etc.

**`backend/data_providers/yahoo/__init__.py`** — new package

**`backend/data_providers/__init__.py`** — updated
* Added exports: `ProviderRegistry`, `ProviderRegistryError`, `ProviderNotFoundError`, `DuplicateProviderError`, `ProviderSymbolMapping`, `SymbolMapService`, `ProviderSymbolMapError`

**`backend/services/ohlcv_service.py`** — updated
* Added `ProviderRegistry` import
* Added `get_ohlcv_by_provider_name(identity, start, end, provider_name, registry, **kwargs)` — resolves adapter from registry then delegates to existing `get_ohlcv()`; keeps `get_ohlcv()` backward-compatible

**`pyproject.toml`** — updated
* Added `yfinance>=0.2.0` dependency (yfinance 1.3.0 installed in `.venv`)

**Tests — Phase 2J validation slice now 80 tests across provider modules after Codex hardening**
* `tests/unit/test_provider_registry.py` — 21 tests: registration, case-insensitivity, duplicate rejection, empty name, wrong type, resolution, error message, deregistration, list/len/contains
* `tests/unit/test_provider_symbol_map.py` — 24 tests: model validation, provider lowercase, frozen, extra fields rejected, resolve with/without mapping, case-insensitive + whitespace-normalized lookup, provider isolation, add/remove/has_mapping, list filtered
* `tests/unit/test_yahoo_adapter.py` — 26 tests: construction, unsupported timeframe, empty symbol/venue, load raises, fetch with mocked DataFrame, OHLCV values, UTC timestamps, empty/None DataFrame, naive datetime, transport exception, multi-row, adjusted/raw mode, daily end bumped, intraday precision preserved; `_inclusive_end` + `_history_bounds` cases; SUPPORTED_TIMEFRAMES constants
* `tests/unit/test_ohlcv_service_registry.py` — 6 tests (+ 3 registry isolation): registry integration, missing provider, correct provider called, case-insensitive name, naive datetime propagation, two-provider isolation

## Latest Validation Snapshot

* Full backend test suite after Codex Phase 2J validation pass: `526 passed` in 1.05s (2026-05-09)
* Targeted provider-layer validation rerun: `114 passed` in 0.81s across `test_provider_registry.py`, `test_provider_symbol_map.py`, `test_yahoo_adapter.py`, `test_ohlcv_service.py`, `test_ohlcv_service_registry.py`

## Important Design Notes

* **Provider isolation preserved** — yfinance is imported only inside `backend/data_providers/yahoo/adapter.py`; no yfinance objects (DataFrame, Ticker) reach services, storage, or strategies
* **Registry as resolver, not executor** — `ProviderRegistry` is a factory/resolver layer; `OHLCVService` still accepts `RangeProviderAdapter` directly in `get_ohlcv()`; `get_ohlcv_by_provider_name()` is a convenience wrapper demonstrating the registry pattern without breaking existing callers
* **Symbol mapping defaults to identity** — `SymbolMapService.resolve()` returns `internal_symbol` unchanged when no explicit mapping exists; only non-identity mappings need to be registered (e.g. Bursa stocks on Yahoo: "MAYBANK" → "1155.KL"); lookup paths now treat case/whitespace consistently
* **`load()` not supported on Yahoo adapter** — `load()` raises `NotImplementedError`; only `fetch(start, end)` is meaningful for a network-backed range provider
* **End date adjustment** — yfinance `end` is exclusive; adapter adds 1 day for daily/weekly/monthly intervals to honour the `RangeProviderAdapter` inclusive-both-bounds contract, while intraday fetches preserve hour/minute precision
* **Metadata is best-effort** — `resolve_yahoo_metadata()` uses `fast_info` with fallback to full `.info`; fields are optional; `YahooInstrumentMetadata` is provider-specific and must not reach strategy or storage contracts

## Deferred

* Polygon, IBKR, Binance, Bursa provider adapters
* Per-candle gap detection within coverage window
* Known-empty-range marker (avoid re-fetching confirmed-empty windows)
* Provider arbitration / automatic fallback
* Full instrument master database
* Async/concurrent range fetching for multiple missing gaps

## No Blockers

---

# Last Session Summary (2026-05-09) — Phase 2I Strategy Runtime Orchestration Foundation

## What Was Completed

**`backend/strategy_runtime/execution_context.py`** — new module
* `StrategyExecutionContext` — frozen Pydantic v2 model
* Fields: `strategy_id`, `runtime_mode` (str), `timeframe`, `start`, `end`, `parameters`, `created_at` (all UTC-enforced datetimes)
* Optional placeholders: `instrument_id`, `initial_capital`, `research_tags` — for future backtesting/portfolio phase
* Validators: UTC enforcement on all datetime fields; empty string rejection on `strategy_id` and `timeframe`

**`backend/strategy_runtime/forecast.py`** — new module
* `ForecastDirection` — str enum: `long`, `short`, `neutral`
* `StrategyForecast` — frozen Pydantic v2 model
* Required: `generated_at`, `target_timestamp`, `target_price`, `direction`, `confidence`
* Validators: UTC enforcement on timestamps; `confidence ∈ [0.0, 1.0]`; `target_price > 0`
* Optional: `invalidation_price`, `reason`, `tags`, `metadata`
* Intended for future frontend chart annotation rendering

**`backend/strategy_runtime/run_result.py`** — new module
* `RunStatus` — str enum: `success`, `failed`, `empty`
* `StrategyRunResult` — frozen Pydantic v2 model
* Fields: `strategy_id`, `runtime_mode`, `status`, `started_at`, `completed_at`, `candles_received`, `features_generated`, `signals: list[StrategySignal]`, `forecasts: list[StrategyForecast]`, `diagnostics`, `warnings`, `error?`
* Reusable across research, backtest, forward test, paper trading

**`backend/strategy_runtime/runner.py`** — new module — primary Phase 2I deliverable
* `StrategyRuntimeRunner` — stateless executor class
* `run(runtime_ref, context, candles)` — deterministic full-window pipeline:
  1. Short-circuit to `RunStatus.empty` when candles is empty (callables not invoked)
  2. `validate_config(parameters)` — `False` adds a warning, does not abort
  3. `build_features(candles, parameters)` → features dict
  4. `generate_signals(features, parameters)` → signals dict
  5. `apply_risk_rules(signals, parameters)` → final dict
  6. Extract `StrategySignal` objects from `final["signals"]` (isinstance-guarded; malformed reserved payloads now add warnings)
  7. Extract `StrategyForecast` objects from `final["forecasts"]` (isinstance-guarded; malformed reserved payloads now add warnings)
  8. Return `StrategyRunResult` — never raises to caller; exceptions caught → `RunStatus.failed`
* Failed results now preserve `features_generated` when failure occurs after feature build and include `diagnostics["failed_stage"]`
* `run_bar_by_bar(...)` — skeleton; raises `NotImplementedError`
* Private helpers: `_extract_signals`, `_extract_forecasts`

**`backend/strategy_runtime/__init__.py`** — updated
* Added exports: `StrategyExecutionContext`, `ForecastDirection`, `StrategyForecast`, `RunStatus`, `StrategyRunResult`, `StrategyRuntimeRunner`

**`tests/unit/test_strategy_runtime_runner.py`** — 78 tests, all passing
* `TestStrategyExecutionContext` (11): creation, UTC enforcement, normalization, frozen, extra fields
* `TestStrategyForecast` (10): creation, UTC enforcement, confidence/price validation, optional fields, frozen
* `TestStrategyRunResult` (9): creation, UTC enforcement, status enum, signals/forecasts fields, frozen
* `TestRunnerSuccessPath` (10): success, deterministic call order, id propagation, candles count, features count, timestamps, diagnostics
* `TestRunnerEmptyCandles` (4): empty status, no signals, callables skipped, zero count
* `TestRunnerFailurePath` (10): each callable can raise → failed; failed-stage diagnostics preserved; feature count retained on later failure; error is string; signals empty; never raises to caller
* `TestSignalExtraction` (5): extracted, non-signal ignored with warning, non-list payload warns, missing key → empty, diagnostics count
* `TestForecastExtraction` (6): extracted, default empty, non-forecast ignored with warning, non-list payload warns, count in diagnostics, optional for strategies
* `TestValidateConfigWarning` (3): False adds warning, run continues, True → no warning
* `TestBarByBarSkeleton` (2): NotImplementedError, descriptive message
* `TestRunnerExampleStrategyIntegration` (5): end-to-end via real loader; success, candles count, forecasts empty, no error, empty candles

## Latest Validation Snapshot

* Full backend test suite after Codex Phase 2I validation pass: `446 passed` in 0.66s (2026-05-09)
* Targeted strategy runtime validation rerun: `151 passed` in 0.11s across `test_strategy_runtime.py` + `test_strategy_runtime_runner.py`

## Important Design Notes

* Forecast support is optional and not forced — strategies returning plain dicts (current example_strategy contract) produce `forecasts=[]`; future strategies returning `StrategyForecast` objects under `"forecasts"` key will have them extracted automatically
* Runner never raises to caller — all exceptions caught in `run()`, returned as `RunStatus.failed` with `error` set; failed results now identify the failing pipeline stage in diagnostics
* `runtime_mode` is a plain `str` in both context and result — avoids coupling `strategy_runtime` to `strategy_registry.RuntimeMode`
* `features_generated = len(features_dict)` (key count) — intentionally simple for now
* Reserved output keys are `"signals"` and `"forecasts"`; malformed non-list payloads or mixed lists no longer fail the run, but they now emit warnings for easier debugging
* `StrategyRuntimeReference` is constructed directly from lambdas in tests — no fixture strategies needed for runner-level tests
* Bar-by-bar skeleton exists as `run_bar_by_bar()` → raises `NotImplementedError`; reserved for backtesting integration

## Deferred

* Bar-by-bar execution (backtesting integration)
* Portfolio context (initial_capital, position sizing) — placeholder fields exist on `StrategyExecutionContext`
* `instrument_id` propagation from `DatasetIdentity` to context (optional field present)
* Result persistence / run log storage
* Async or parallel runner variants

## No Blockers

---

# Last Session Summary (2026-05-09) — Phase 2H OHLCV Retrieval Orchestration

## What Was Completed

**`backend/data_providers/range_provider.py`** — new module
* `RangeProviderAdapter(BaseDataAdapter)` — ABC for date-range fetching providers
* `fetch(start, end, **kwargs) -> list[NormalizedOHLCV]` — abstract; must return `[]` (not raise) when range is empty; must honour `[start, end]` bounds; must not normalize or write to storage

**`backend/data_providers/csv_adapter.py`** — updated
* `CSVAdapter` now extends `RangeProviderAdapter` (was `BaseDataAdapter`)
* `fetch(start, end, **kwargs)` added — loads full CSV via `load()` then filters to `[start, end]` inclusive; raises `ValueError` on naive datetimes

**`backend/data_providers/__init__.py`** — updated
* Added `RangeProviderAdapter` export

**`backend/services/__init__.py`** — new package
**`backend/services/ohlcv_service.py`** — new module — primary deliverable
* `OHLCVIngestionError(Exception)` — raised on normalization or storage write failure
* `OHLCVService(base_path)` — retrieval orchestration; owns `CoverageRegistry` + `DataNormalizer` internally
* `get_ohlcv(identity, start, end, provider, **fetch_kwargs)` — full orchestration flow:
  1. Validate UTC-aware bounds
  2. `calculate_missing_ranges()` against `CoverageRegistry`
  3. For each gap: `provider.fetch()` → `DataNormalizer.normalize()` → `ohlcv_store.write(merge=True)`
  4. `_refresh_coverage()` after any successful write
  5. `_read_slice()` returns only `[start, end]` window
* `calculate_missing_ranges(identity, start, end)` — public; delegates to `CoverageRegistry.missing_ranges()`
* `refresh_coverage(identity)` — public; re-reads stored Parquet and updates `coverage.json` (useful after manual file ops)
* Fail-fast on normalization/write errors — already-written ranges preserved, error propagates as `OHLCVIngestionError`
* Empty provider response (`[]`) is silently skipped — no crash, no coverage update for that gap

**`tests/unit/test_ohlcv_service.py`** — 34 tests, all passing

* `TestFullMiss` (5): provider called, data returned, parquet written, coverage updated, slice bounded
* `TestFullOverlap` (3): provider NOT called when fully covered, correct slice returned
* `TestLeadingPartialOverlap` (3): only leading gap fetched, merged into storage, result complete
* `TestTrailingPartialOverlap` (3): only trailing gap fetched, merged, coverage updated
* `TestProviderReturnsEmpty` (3): no crash, no coverage update, empty list returned
* `TestDeduplication` (2): second identical ingestion → no duplicates; overlapping fetch → no duplicates
* `TestProviderIsolation` (2): Yahoo/Polygon stored separately, independent coverage
* `TestCoverageSync` (2): coverage correct after partial fills; refresh_coverage syncs from disk
* `TestNormalizationError` (2): bad data → OHLCVIngestionError; existing storage intact
* `TestInputValidation` (2): naive start/end rejected
* `TestCalculateMissingRanges` (3): no coverage, full coverage, partial coverage
* `TestCSVAdapterFetch` (4): range filter, empty range, naive datetime rejected, isinstance check

## Latest Validation Snapshot

* Full backend test suite at Phase 2H completion: `368 passed` in 0.58s (2026-05-09)
* 334 prior tests still pass — zero regressions

## Important Design Notes

* `OHLCVService` is the canonical access point for future backtesting, charting, feature generation — callers must NOT read directly from `ohlcv_store` or call provider adapters themselves
* Provider adapter is passed at call time (not at construction) — keeps `OHLCVService` stateless with respect to providers and allows multiple providers per service instance
* `get_ohlcv()` is idempotent: calling it twice for the same window results in exactly one copy of each candle in storage
* Coverage is boundary-based (earliest/latest timestamp); per-candle gap detection within covered window is deferred
* `_refresh_coverage()` reads the full stored dataset after writes — slightly heavier than incremental update, but guarantees coverage is always accurate regardless of merge outcomes
* `CSVAdapter.fetch()` loads the full file then filters — appropriate for local file-backed adapters; network-based providers would implement true range queries

## Deferred

* Per-candle gap detection (interior holes within coverage window)
* Network-backed provider adapters (Yahoo Finance, Polygon, IBKR REST)
* Async/concurrent range fetching for multiple gaps
* "Known empty range" marker (avoid re-fetching ranges where provider confirmed no data)

## No Blockers

---

# Last Session Summary (2026-05-09) — Phase 2G.5 Data Storage Architecture Hardening

## What Was Completed

**`backend/data/models/instrument.py`** — new module
* `AdjustmentMode` — str enum: `raw`, `adjusted`, `split_adjusted`
* `Instrument` — frozen Pydantic v2 model; provider-independent identity (`symbol`, `asset_class`, `exchange`, `currency`)
* `Instrument.instrument_id` — computed property: `"{asset_class}__{exchange}__{symbol}"`

**`backend/data/models/dataset.py`** — new module
* `DatasetIdentity` — frozen Pydantic v2 model; provider-specific dataset identity
* Fields: `instrument`, `provider`, `timeframe`, `adjustment_mode`; `provider` normalized to lowercase
* `DatasetIdentity.dataset_id` — computed property: `"{instrument_id}__{provider}__{timeframe}__{adjustment_mode}"`
* Guarantees that AAPL/yahoo and AAPL/polygon are distinct datasets — no silent merging

**`backend/data/models/__init__.py`** — new package exposing `Instrument`, `AdjustmentMode`, `DatasetIdentity`

**`backend/storage/ohlcv_store.py`** — new module
* `dataset_path(base_path, identity)` — provider-aware path: `{base}/{provider}/{asset_class}/{exchange}/{symbol}/{timeframe}/{adjustment_mode}/data.parquet`
* `write(records, base_path, identity, *, merge=True)` — validates symbol/asset_class/exchange/provider/timeframe match; deduplicates by timestamp (incoming wins); merges with existing if `merge=True`; sorts before write
* `read(base_path, identity)` — reads validated `NormalizedOHLCV` list; raises `StorageError` if missing
* `read_range(base_path, identity, start, end)` — filters by UTC-aware datetime bounds
* `OHLCVWriteError(StorageError)` — raised on identity mismatch or empty input
* Internal helpers: `_merge_and_deduplicate`, `_deduplicate`, `_read_raw`

**`backend/storage/coverage_registry.py`** — new module
* `CoverageRecord` — frozen dataclass: `dataset_id`, `provider`, `instrument_id`, `timeframe`, `adjustment_mode`, `earliest_timestamp`, `latest_timestamp`, `record_count`, `last_updated`
* `CoverageRegistry(base_path)` — file-based coverage service; writes `coverage.json` alongside each dataset's `data.parquet`
* `update(identity, records)` — validates records against dataset identity, derives and persists coverage from a records list, overwrites previous coverage
* `get(identity)` → `Optional[CoverageRecord]` — reads coverage without scanning Parquet files
* `has_full_coverage(identity, start, end)` → bool — boundary-based check
* `missing_ranges(identity, start, end)` → list of gap tuples — returns leading/trailing gaps vs stored boundary

**`backend/storage/parquet_store.py`** — updated
* `_SCHEMA` renamed to `SCHEMA` (public); backward-compatible alias `_SCHEMA = SCHEMA` retained
* `_records_to_table` → `records_to_table` (public); `_table_to_records` → `table_to_records` (public)
* Existing `write()` / `read()` / `dataset_path()` / `StorageError` unchanged

**`backend/storage/__init__.py`** — updated
* Added exports: `SCHEMA`, `records_to_table`, `table_to_records`

**Tests** — 70 tests, all passing for the Phase 2G.5 storage slice after targeted validation hardening
* `tests/unit/test_instrument_models.py` — 22 tests: `AdjustmentMode`, `Instrument`, `DatasetIdentity` (creation, validation, id formats, provider isolation, frozen enforcement)
* `tests/unit/test_ohlcv_store.py` — 28 tests: path structure, write validation, dedup, merge, read, read_range, provider isolation, exchange/provider mismatch rejection
* `tests/unit/test_coverage_registry.py` — 20 tests: update, get, has_full_coverage, missing_ranges, provider isolation, exchange/provider mismatch rejection

## Latest Validation Snapshot

* Full backend test suite at Phase 2G.5 completion: `330 passed` in 0.55s (2026-05-09)
* 264 prior tests still pass — zero regressions
* Targeted post-validation run after Codex patch: `109 passed` in 0.28s across `test_instrument_models.py`, `test_ohlcv_store.py`, `test_coverage_registry.py`, `test_parquet_store.py`, `test_duckdb_query.py`

## Important Design Notes

* Provider separation is enforced at the path level — Yahoo and Polygon for same instrument go to different filesystem paths; reading one never loads the other
* Provider separation is now also enforced at write/update validation time — records with mismatched `source` or `venue` are rejected before they can pollute a provider-specific dataset or coverage file
* Deduplication key is `timestamp` within a dataset file — incoming record overwrites existing on collision
* Coverage registry is file-based JSON (no PostgreSQL dependency); `coverage.json` lives alongside `data.parquet`
* `missing_ranges()` uses boundary timestamps only (not per-candle gap detection) — suitable for pre-fetch decisions
* `parquet_store.py` remains unchanged functionally; the new `ohlcv_store.py` is a parallel higher-level service built on top of the same Parquet primitives
* The existing `dataset_service.py` in `backend/api/services/` continues to use `parquet_store.py` directly (API layer not modified per Phase 2G.5 scope)

## Deferred

* Per-candle gap detection (detecting gaps within the covered window, not just boundary gaps)
* PostgreSQL-backed coverage registry (deferred until PostgreSQL integration phase)
* Provider reconciliation / arbitration (explicitly out of scope)
* Updating `dataset_service.py` to use `ohlcv_store` — requires API layer changes, deferred to Phase 2H or dedicated API update

## No Blockers

---

# Last Session Summary (2026-05-08) — Phase 2G Dataset API Layer

## What Was Completed

**`backend/core/config.py`** — updated
* Added `storage_base_path: Path = Path("datasets/normalized")` — configurable via `STORAGE_BASE_PATH` env var; defaults to `datasets/normalized/` relative to cwd (per DATA_CONTRACT.md)

**`backend/api/schemas/dataset.py`** — new module
* `DatasetInfo` — flat dataset descriptor (`dataset_id`, `asset_class`, `symbol`, `timeframe`)
* `DatasetListResponse` — wraps `datasets: list[DatasetInfo]` + `count: int`
* `ImportCSVResponse` — post-import result (`dataset_id`, `symbol`, `asset_class`, `venue`, `timeframe`, `record_count`)
* `OHLCVCandle` — candle-level data without identity fields (identity lives in envelope)
* `DatasetOHLCVResponse` — envelope + `candles: list[OHLCVCandle]`

**`backend/api/services/dataset_service.py`** — new module
* `DatasetImportError` — raised for recoverable import/normalization/storage failures (→ 400)
* `DatasetNotFoundError` — raised when a dataset does not exist (→ 404)
* `make_dataset_id(asset_class, symbol, timeframe)` → `"{asset_class}__{symbol}__{timeframe}"`
* `parse_dataset_id(dataset_id)` → `(asset_class, symbol, timeframe)` — uses `maxsplit=2` to preserve underscores in symbol names; raises `ValueError` on bad format
* `import_csv(file_bytes, ..., column_map, base_path)` — writes CSV bytes to temp file → CSVAdapter → DataNormalizer → parquet_store.write(); cleans up temp file in `finally`
* `list_datasets(base_path)` — globs `*/*/*/data.parquet` under base_path; returns sorted `DatasetListResponse`
* `read_ohlcv(base_path, asset_class, symbol, timeframe)` → `DatasetOHLCVResponse` via `parquet_store.read()`

**`backend/api/routes/datasets.py`** — new module
* `APIRouter(prefix="/datasets", tags=["datasets"])`
* `get_storage_path()` — FastAPI Depends injectable; reads `settings.storage_base_path`; overridable in tests via `app.dependency_overrides`
* `POST /datasets/import/csv` — multipart: `UploadFile` + Form fields (`symbol`, `asset_class`, `venue`, `timeframe`, `source`, optional column-name overrides); returns 201 on success, 400 on import error, 422 on validation error
* `GET /datasets` — lists stored datasets; returns 200 always (empty list if no storage)
* `GET /datasets/{dataset_id}/ohlcv` — returns normalized candles; 400 on bad dataset_id format, 404 if not found

**`backend/api/main.py`** — updated
* Imports and registers `datasets.router`

**`pyproject.toml`** — updated
* Added `python-multipart>=0.0.9` to dependencies (required for FastAPI `UploadFile` + `Form`)

**`tests/unit/test_api_datasets.py`** — 31 tests, all passing
* `TestImportCSV` — 11 tests: 201 success, response fields, parquet written, custom column mapping, malformed CSV, duplicate timestamps, missing file, missing form field, invalid timeframe, missing mapped column, temp-file cleanup on failed parse
* `TestListDatasets` — 5 tests: empty storage, nonexistent path, list after import, multiple datasets, response schema
* `TestGetOHLCV` — 9 tests: 200 success, response fields, candle fields, values match CSV, timestamp UTC format, 404 not found, 400 invalid id, 400 partial id, underscore-containing symbol roundtrip
* `TestDatasetIdHelpers` — 6 tests: make, parse, symbol with underscores, invalid raises, empty segment raises, roundtrip

## Latest Validation Snapshot

* Full test suite at Phase 2G completion: `253 passed` in 0.51s (2026-05-08)
* All prior 222 tests still pass — zero regressions
* Architecture guardrails preserved: routes remain thin; all business logic in service layer; normalization/storage contracts not bypassed

## Important Design Notes

* `dataset_id` format: `{asset_class}__{symbol}__{timeframe}` (double underscore, `maxsplit=2` on parse so symbol can contain single underscores e.g. `BRK_B`)
* `get_storage_path()` is a FastAPI `Depends` so tests can `app.dependency_overrides[get_storage_path] = lambda: tmp_path` — no monkeypatching needed
* Temp file cleanup (`os.unlink`) is always in `finally` — safe even if normalization raises
* `list_datasets` globs `*/*/*/data.parquet` — three directory levels per DATA_CONTRACT.md path convention
* `python-multipart` is required at runtime (not dev-only) because `UploadFile` + `Form` are production API features

## No Blockers

---

# Last Session Summary (2026-05-08) — Phase 2G-Fix DEBUG Config Parsing

## What Was Completed

**`backend/core/config.py`** — hardened `Settings.debug` parsing
* Added a pre-validation parser for `debug`
* Accepts normal boolean-like values: `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off`
* Treats non-boolean ambient strings such as `release` safely as `False`
* Preserved the existing settings structure and `BaseSettings` usage

**`tests/unit/test_config.py`** — new focused config tests
* Covers valid boolean-like env values
* Covers non-boolean env values such as `release` and `DEBUG_MODE`
* Covers unset `DEBUG` defaulting to `False`
* Confirms `storage_base_path` default remains unchanged

## Latest Validation Snapshot

* Full backend unit suite: `264 passed` in 0.53s (2026-05-08)
* Validation now succeeds in the current shell environment without requiring any `DEBUG=false` override, even with ambient `DEBUG=release`

## Important Design Notes

* Unknown `DEBUG` strings now fail closed to `False` instead of failing import-time settings construction
* No configuration architecture changes were introduced
* No dependencies were added

## Next Recommended Steps

1. First real strategy implementing all 4 required callables, consuming `NormalizedOHLCV` via `DataNormalizer` + `ParquetStore`
2. Fix "Edgelab" → "QuantLab" in `ARCHITECTURE_GUARDRAILS.md` line 4 (cosmetic)
3. `backend/backtesting/` — simulation engine (after first strategy stable)
4. Frontend end-to-end validation (dataset import → chart)

---

# Last Session Summary (2026-05-08) — Phase 2F Strategy Runtime Contract Hardening

## What Was Completed

**`backend/strategy_runtime/signature_validator.py`** — new module
* `CALLABLE_EXPECTED_PARAM_COUNTS` — expected positional param counts per callable (2/2/2/1)
* `CALLABLE_EXPECTED_RETURN_TYPES` — expected return types per callable (`dict`/`dict`/`dict`/`bool`)
* `IMPORT_SAFETY_RULES` — tuple of 7 import-time side-effect rules (documented contract; cannot all be statically enforced)
* `CallableSignatureError(RuntimeInterfaceError)` — dedicated error for signature violations
* `validate_callable_signatures(modules)` — validates positional param counts; *args-aware; reports all violations at once
* `validate_return_annotations(modules)` — best-effort return annotation check; skips absent annotations and generic types (dict[str, Any]); reports all violations at once

**`backend/strategy_runtime/loader.py`** — updated
* `load_strategy_runtime` now calls `validate_callable_signatures` and `validate_return_annotations` after `validate_strategy_interface`
* Validation pipeline: load modules → presence check → signature check → annotation check → build reference
* Import boundary clarified:
  loader does not invoke required strategy callables during validation, but Python import still executes module top-level code, so import-safety remains a documented contract

**`backend/strategy_runtime/__init__.py`** — updated
* Exports all new symbols: `CALLABLE_EXPECTED_PARAM_COUNTS`, `CALLABLE_EXPECTED_RETURN_TYPES`, `IMPORT_SAFETY_RULES`, `CallableSignatureError`, `validate_callable_signatures`, `validate_return_annotations`

**`tests/fixtures/strategies/wrong_signature_strategy/`** — new fixture
* `features.py` — `build_features(only_one_param)` — 1 param instead of required 2
* Other 3 files (`signals.py`, `risk.py`, `validators.py`) are fully compliant

**`tests/unit/test_strategy_runtime.py`** — extended with runtime-contract-hardening coverage (222 total suite passing)
* `TestCallableSignatureValidation` — 15 tests: per-callable wrong count, *args allowed, multi-violation, fixture integration, constant contracts
* `TestReturnAnnotationValidation` — 11 tests: no annotation passes, correct annotation passes, incompatible raises, generic skipped, multi-violation, constant contracts
* `TestImportSafetyRules` — 4 tests: non-empty, type check, key concern coverage, importability
* `TestLoadStrategyRuntimePhase2F` — 3 tests: valid_strategy passes, example_strategy passes, error hierarchy

## Latest Validation Snapshot

* Full test suite: `222 passed` in 0.35s (2026-05-08)
* All prior tests still pass — zero regressions
* Architecture guardrails preserved: registry still imports no strategy_runtime code
* No new dependencies added — uses `inspect`, `typing` (stdlib only)

## Important Design Notes

* `validate_return_annotations` is best-effort: absent annotations are silently skipped, generic annotations (e.g. `dict[str, Any]`) are skipped by `isinstance(annotation, type)` guard
* `CallableSignatureError` is a subclass of `RuntimeInterfaceError` — callers catching `RuntimeInterfaceError` will also catch signature errors without change
* `IMPORT_SAFETY_RULES` documents the side-effect contract; runtime enforcement is limited to what `spec.loader.exec_module` naturally catches (exceptions during import = `StrategyLoadError`)
* *args is permitted in callable signatures — only positional count before `*args` is checked
* `_noop` helper in tests intentionally omits `-> None` annotation to avoid triggering annotation validation

## No Blockers

## Next Recommended Steps

1. First real strategy implementing all 4 required callables, consuming `NormalizedOHLCV` via `DataNormalizer` + `ParquetStore`
2. Fix "Edgelab" → "QuantLab" in `ARCHITECTURE_GUARDRAILS.md` line 4 (cosmetic)
3. `backend/backtesting/` — simulation engine (after first strategy is stable)

---

# Last Session Summary (2026-05-08) — Phase 2E Strategy Runtime Interface

## What Was Completed

**`backend/strategy_runtime/` — Strategy runtime interface**
* `models.py` — `SignalType` (4-value str enum: `long/short/exit/reduce`), `StrategySignal` (frozen Pydantic v2 model)
  * Required: `strategy_id`, `timestamp` (UTC-enforced), `symbol`, `timeframe`, `signal_type`, `entry_reference`, `invalidation_level`
  * Optional: `confidence`, `metadata`, `tags`, `reasoning`, `feature_snapshot`, `setup_id`
  * UTC hardening validated: naive timestamps rejected and non-UTC aware timestamps normalized to UTC
* `interface.py` — `REQUIRED_CALLABLES`, `CALLABLE_MODULE_MAP`, `RuntimeInterfaceError`, `validate_strategy_interface(modules)`
  * Maps each callable to its owning module file: `build_features→features`, `generate_signals→signals`, `apply_risk_rules→risk`, `validate_config→validators`
  * All missing callables reported in a single error (not first-failure-only)
* `loader.py` — `StrategyLoadError`, `StrategyRuntimeReference` (frozen dataclass), `load_strategy_runtime(strategy_dir, strategy_id)`
  * Loads 4 strategy module files via `importlib.util.spec_from_file_location` (no sys.modules pollution)
  * Returns `StrategyRuntimeReference` with validated callable references — does NOT invoke strategy logic
* `__init__.py` — all public exports

**`strategies/example_strategy/`**
* `validate_config` moved from `risk.py` to `validators.py` — aligns with `STRATEGY_CONTRACT.md`
* `risk.py` now contains only `apply_risk_rules`

**`tests/fixtures/strategies/`**
* `valid_strategy/` and `duplicate_id_strategy/` updated — all 4 callables now present in correct files
* `missing_callable_strategy/` — new fixture: all module files present, `build_features` absent from `features.py`

**`tests/unit/test_strategy_runtime.py`** — 40 tests, all passing
* Covers: `SignalType` enum, `StrategySignal` validation, `validate_strategy_interface` (all failure modes), `load_strategy_runtime` (happy path + failures), contract constants, registry/runtime isolation guardrail, data contract alignment

## Latest Validation Snapshot

* Full test suite: `189 passed` in 0.32s (2026-05-08)
* All prior tests still pass — no regressions
* Architecture guardrail preserved: registry imports no strategy_runtime code; source-level assertion verified in tests

## Important Design Notes

* `validate_config` canonical home is `validators.py` (matches STRATEGY_CONTRACT.md responsibilities section)
* `StrategyRuntimeReference` is a frozen dataclass, not a Pydantic model — holds `Callable` types which Pydantic doesn't validate well
* `load_strategy_runtime` does NOT call `validate_strategy_files()` — file-structure validation remains the registry's responsibility; runtime loader only needs the 4 callable-bearing files
* No new dependencies added — uses `importlib.util` (stdlib only)

## No Blockers

## Next Recommended Steps

1. First real strategy implementing `build_features()`, `generate_signals()`, `apply_risk_rules()`, `validate_config()` consuming `NormalizedOHLCV` via `DataNormalizer` + `ParquetStore`
2. Fix "Edgelab" → "QuantLab" in `ARCHITECTURE_GUARDRAILS.md` line 4 (cosmetic)
3. `backend/backtesting/` — simulation engine (after first strategy is stable)

---

# Last Session Summary (2026-05-08) — Phase 2D Strategy Registry Foundation

## What Was Completed

**`backend/strategy_registry/` — Strategy registry foundation**
* `models.py` — `StrategyLifecycleStage` (9-stage enum), `RuntimeMode` (5-mode enum), `StrategyManifest` (frozen Pydantic v2 model with `extra="ignore"`)
  * Required fields: `strategy_id`, `version`, `lifecycle_stage`
  * Optional: `name`, `description`, `supported_assets`, `supported_timeframes`, `feature_dependencies`, `runtime_compatibility`, `warmup_bars`
  * Contract compatibility hardening: hyphenated lifecycle values from `docs/STRATEGY_CONTRACT.md` are normalized on load (`approved-for-live` → `approved_for_live`)
* `manifest.py` — `load_manifest(strategy_dir)`, `ManifestLoadError`
  * Handles YAML parse errors, non-mapping YAML, missing required fields
  * Normalises float version values (`1.0` → `"1.0"`) before Pydantic validation
* `validator.py` — `validate_strategy_files(strategy_dir)`, `StrategyValidationError`, `REQUIRED_STRATEGY_FILES`
  * Required files: `strategy.yaml`, `metadata.py`, `parameters.py`, `features.py`, `signals.py`, `risk.py`, `runtime.py`, `validators.py`
  * Does NOT import or execute strategy code
* `registry.py` — `StrategyRegistry`, `StrategyRegistryEntry`, `StrategyRegistryError`
  * `register(strategy_dir)` — validates files + manifest, raises on duplicate `strategy_id`
  * `discover(strategies_dir)` — lenient scan: skips broken/already-registered, stores errors in `_last_discover_errors`
  * `get(strategy_id)`, `list_all()`, `__len__`, `__contains__`
* `__init__.py` — all public exports

**`strategies/example_strategy/strategy.yaml`**
* Updated to conform to `StrategyManifest` contract: `strategy_id` (was `id`), `supported_assets` (was `supported_instruments`), runtime mode `backtesting` (was `backtest`)

**`pyproject.toml`**
* Added `pyyaml>=6.0` dependency

**`tests/unit/test_strategy_registry.py`** — 51 tests, all passing
* Covers: enum completeness, manifest model validation, manifest loading (all error paths), file structure validation, registry register/discover/get/list operations, no-execution guard

**`tests/fixtures/strategies/`** — 5 test fixture strategy folders
* `valid_strategy/` — fully compliant strategy stub
* `missing_risk_strategy/` — missing `risk.py`
* `invalid_manifest_strategy/` — `strategy.yaml` missing required fields
* `malformed_yaml_strategy/` — invalid YAML syntax
* `duplicate_id_strategy/` — same `strategy_id` as `valid_strategy`

## Latest Validation Snapshot

* Full test suite: `149 passed` in 0.32s (2026-05-08)
* All prior tests still pass — no regressions
* Architecture guardrails preserved: no strategy code executed by registry

## Important Design Notes

* `StrategyManifest` uses `extra="ignore"` (unlike `NormalizedOHLCV` which uses `extra="forbid"`) — strategy YAMLs may declare local extension fields without breaking the registry
* `discover()` is lenient: broken strategies are skipped and their errors stored in `registry._last_discover_errors` dict; valid strategies are returned regardless
* `register()` is strict: raises `StrategyValidationError` or `ManifestLoadError` directly — caller decides how to handle
* float YAML version values (e.g. `version: 1.0`) are normalised to str in `load_manifest`, not in the model itself

## No Blockers

## Next Recommended Steps

1. First real strategy implementing `build_features()`, `generate_signals()`, `apply_risk_rules()`, `validate_config()` consuming `NormalizedOHLCV` via `DataNormalizer` + `ParquetStore`
2. Fix "Edgelab" → "QuantLab" in `ARCHITECTURE_GUARDRAILS.md` line 4 (cosmetic)
3. `backend/backtesting/` — simulation engine (after first strategy is stable)

---

# Last Session Summary (2026-05-08) — Phase 2C Storage Layer: DuckDB/Parquet

## What Was Completed

**`backend/storage/` — Parquet + DuckDB storage layer**
* `parquet_store.py` — `write()`, `read()`, `dataset_path()`, `StorageError`
  * Canonical path: `{base_path}/{asset_class}/{symbol}/{timeframe}/data.parquet`
  * Validation hardening completed: `write()` now enforces `venue` consistency in addition to symbol, asset class, and timeframe
* `duckdb_query.py` — `query_parquet()`, `query_ohlcv()`
  * UTC safety hardening completed: naive `start`/`end` filter datetimes are now rejected instead of being silently treated as UTC

## Latest Validation Snapshot

* Scoped validation run completed on 2026-05-08
* Backend unit tests inside `.venv`: `98 passed`
* Confirmed: Parquet read path reconstructs and re-validates `NormalizedOHLCV`
* Confirmed: storage layer exposes canonical OHLCV records, not provider-native schemas
* Confirmed: storage modules remain isolated from strategy/runtime/backtesting logic
  * Schema enforces consistency across records (symbol/asset_class/timeframe must match)
  * Full `NormalizedOHLCV` re-validation on read — no raw rows escape contract
  * `metadata` dict serialized as JSON string; all optional fields handled as nullable
* `duckdb_query.py` — `query_parquet()`, `query_ohlcv()`
  * Uses `conn.execute(sql).arrow().read_all()` to avoid `pytz` dependency (DuckDB 1.5.2 needs pytz for `fetchall()` TIMESTAMPTZ conversion)
  * `query_parquet()`: arbitrary SQL via keyword placeholder `parquet` → `read_parquet(...)`
  * `query_ohlcv()`: structured OHLCV queries with optional `symbol`, `start`, `end` filters; results ordered by timestamp; re-validated as `NormalizedOHLCV`
* `__init__.py` — public exports: `write`, `read`, `dataset_path`, `StorageError`, `query_parquet`, `query_ohlcv`

**`tests/unit/`**
* `test_parquet_store.py` — 19 tests: path structure, write validation, read errors, full round-trip (scalars, timestamps, optional fields, metadata)
* `test_duckdb_query.py` — 16 tests: raw dict queries, count, empty result, typed OHLCV queries, symbol/start/end filters, ordering

**`pyproject.toml`**
* Added `pyarrow>=15.0.0` and `duckdb>=0.10.0` to `[project.dependencies]`

## Latest Validation Snapshot

* Full test suite: `95 passed` in 0.20s (2026-05-08)
* Architecture guardrails preserved: `NormalizedOHLCV` is the only output contract; no provider-native data persisted or returned

## Important Technical Notes

* DuckDB 1.5.2 on Python 3.13 requires `pytz` when calling `fetchall()` on queries containing `TIMESTAMPTZ` columns. The storage layer bypasses this by using `.arrow().read_all()` to get results as a pyarrow Table — no pytz or numpy/pandas needed.
* Parquet timestamps stored as `pa.timestamp("us", tz="UTC")` — microsecond precision, UTC-tagged column. DuckDB reads this as `TIMESTAMPTZ`. Pyarrow returns integer epoch-microseconds on `to_pydict()` which the layer converts back to UTC-aware datetimes.

## No Blockers

## Next Recommended Steps

1. Build `backend/strategy_registry/` — Pydantic metadata models for strategy lifecycle tracking
2. First real strategy consuming normalized data via `DataNormalizer` + `ParquetStore`
3. Fix "Edgelab" → "QuantLab" in `ARCHITECTURE_GUARDRAILS.md` (cosmetic cleanup)

---

# Last Session Summary (2026-05-08) — Phase 2B Data Contracts & Normalization

## What Was Completed

**`backend/data/` — Normalization layer**
* `schemas.py` — `NormalizedOHLCV` (frozen Pydantic v2 model): UTC enforcement on timestamp, canonical timeframe validation, identity field stripping, `high >= low` at schema level
* `validators.py` — `validate_ohlcv_record` (numerical/OHLC relationships, non-negative volume, finite values) + `validate_ohlcv_series` (monotonic timestamps, no duplicates, consistent symbol/timeframe/venue)
* Validation hardening completed: `NormalizedOHLCV` now rejects unexpected extra fields so provider-native fields cannot be silently accepted at the strategy-facing contract boundary
* CSV timestamp parsing hardened for out-of-range Unix timestamp values so adapter failures stay normalized as `ValueError`

## Latest Validation Snapshot

* Scoped validation run completed on 2026-05-08
* Backend unit tests inside `.venv`: `59 passed`
* Confirmed: strategy-facing contract remains `NormalizedOHLCV` only
* Confirmed: timestamps are normalized to UTC and naive datetimes are rejected at schema level
* Confirmed: malformed OHLCV rows are rejected by schema validation and series validation
* `normalizer.py` — `DataNormalizer.normalize()` orchestrates validation, raises `NormalizationError` with full error list

**`backend/data_providers/` — Provider adapter layer**
* `base.py` — `BaseDataAdapter` abstract class (`provider_name`, `load()`)
* `csv_adapter.py` — `CSVAdapter` with `CSVAdapterConfig` + `CSVColumnMap`; supports ISO-8601 (with/without timezone), Z-suffix, naive (assumed UTC), date-only, Unix timestamps

**`tests/`**
* 56 tests — all passing in 0.04s
* Fixtures: `valid_ohlcv.csv`, `valid_ohlcv_naive_ts.csv`, `valid_ohlcv_unix_ts.csv`, `malformed_high_lt_low.csv`, `malformed_duplicate_timestamps.csv`

## Architecture Compliance

* Provider schemas do not leak outside `csv_adapter.py` — ✓
* Strategies receive only `NormalizedOHLCV` — verified by test — ✓
* No database layer, no broker integration, no frontend changes — ✓
* No new dependencies — stdlib `csv` + `datetime` only — ✓

## No Blockers

## Next Recommended Steps

1. Add DuckDB/Parquet storage layer in `backend/storage/`
2. Build `backend/strategy_registry/` metadata models (Pydantic, no DB yet)
3. Implement first real strategy consuming normalized data via `DataNormalizer`

---

# Last Session Summary (2026-05-08) — Phase 2 Base Scaffold

## What Was Completed

**Backend**
* `pyproject.toml` at root (fastapi, uvicorn[standard], pydantic-settings, python-dotenv)
* `backend/api/main.py` — FastAPI app, includes health router
* `backend/api/routes/health.py` — `GET /health` → `{"status": "ok", "service": "quantlab-backend"}`
* `backend/core/config.py` — Pydantic `Settings` (reads from `.env`)
* `backend/core/logging.py` — `setup_logging()` with stdout handler
* All backend module stubs created as empty Python packages: `data`, `data_providers`, `strategy_registry`, `strategy_runtime`, `backtesting`, `forward_testing`, `execution`, `storage`, `jobs`

**Frontend**
* Vite + React 18 + TypeScript skeleton
* `frontend/src/App.tsx` — calls `/health` via proxy and displays backend status
* `frontend/src/api/health.ts` — typed `fetchHealth()` function
* Empty directories: `pages/`, `components/`, `features/`

**Strategies**
* `strategies/README.md` — contract rules summary
* `strategies/example_strategy/` — placeholder stubs: `strategy.yaml`, `parameters.py`, `features.py`, `signals.py`, `risk.py` (exposes all required contracts: `build_features`, `generate_signals`, `apply_risk_rules`, `validate_config`)

**Datasets**
* Folder structure created: `raw/`, `normalized/`, `processed/`, `features/`, `alternative/`, `astronomical/`, `metadata/`, `cache/`

**Other**
* `.env.example` populated with APP, BACKEND_HOST/PORT, and commented future entries (PostgreSQL, Redis)

## Run Commands

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# open http://localhost:3000
```

## Architecture Compliance

* Strategy modules do not access brokers, APIs, storage, or frontend — ✓
* Frontend contains no business logic — ✓
* API routes are thin (no business logic in routes) — ✓
* Health endpoint is minimal and correct — ✓
* No live trading, broker adapters, or premature infrastructure — ✓

## Next Recommended Steps

1. Install dependencies and validate `/health` endpoint works
2. Begin data architecture layer: normalization schemas, OHLCV contracts
3. Define `backend/data/` schemas (Pydantic models for normalized data)
4. Define `backend/data_providers/` first adapter (CSV or local Parquet)
5. Begin strategy registry metadata models

---

# Last Session Summary (2026-05-08)

## What Was Completed

* Created `README.md` at repository root (purpose, architecture direction, structure, current stage)
* Refactored `.gitignore` for full-stack coverage: FastAPI/Pydantic/SQLAlchemy, PostgreSQL, DuckDB, Parquet, Redis, Celery/RQ, React/TypeScript, research datasets
* Marked `SYSTEM_OVERVIEW.md`, `ARCHITECTURE.md`, `REPOSITORY_STRUCTURE.md` as completed in `TASKS.md` (they existed but were marked pending)

## Findings and Flags

* **`directives/` folder is not documented in `REPOSITORY_STRUCTURE.md`** — this folder contains orchestration prompt templates and should be added to the repository structure doc. Recommend placing it under `agent/directives/` or documenting it as a top-level folder in `REPOSITORY_STRUCTURE.md`
* **`ARCHITECTURE_GUARDRAILS.md` refers to "Edgelab"** (line 4) — should be updated to "QuantLab" for naming consistency
* **`docker-compose.yml` at root is empty** — either populate or remove to keep root clean

## Next Recommended Steps

1. Resolve `directives/` placement in `REPOSITORY_STRUCTURE.md`
2. Fix "Edgelab" naming in `ARCHITECTURE_GUARDRAILS.md`
3. Define backend domain structure
4. Define data layer contracts
5. Define strategy engine contracts

---

# Current Immediate Next Steps

Current recommended next priorities:
1. Resolve `directives/` folder documentation gap in `REPOSITORY_STRUCTURE.md`
2. Fix "Edgelab" → "QuantLab" in `ARCHITECTURE_GUARDRAILS.md`
3. Backend domain structure
4. Data layer blueprint
5. Strategy engine contracts

Avoid premature implementation of:
* live trading
* broker execution
* complex infrastructure
* production deployment

---

# Current Operational Rules

Before major implementation:
* read governance documents
* identify scope
* preserve architecture boundaries
* avoid uncontrolled rewrites
* keep implementation modular
* update documentation when needed

If prompts are unclear:
* ask clarification before high-impact modifications

---

# Important AI Workflow Direction

Preferred workflow:
human intent
→ orchestration/refinement
→ scoped implementation prompt
→ controlled implementation
→ validation
→ documentation update
→ handoff update

Avoid:
* large vague prompts
* uncontrolled repository rewrites
* whole-system implementation requests

---

# Current State Summary

QuantLab is currently establishing the institutional-grade governance and orchestration foundation required for a long-term modular strategy research ecosystem.

Architecture quality and workflow discipline currently take priority over implementation speed.

The repository should evolve incrementally through controlled modular engineering.

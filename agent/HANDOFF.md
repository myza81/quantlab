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

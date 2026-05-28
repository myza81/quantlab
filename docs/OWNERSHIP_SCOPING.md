# Ownership & Resource Scoping (Phase 3L)

## Overview

Phase 3L converts strategy drafts, dataset catalog entries, and backtest runs from globally accessible resources into user-owned resources. Every resource carries a `user_id` field that is set by the backend at creation time from the authenticated user's JWT — it can never be supplied by the client in a request body.

## Ownership Model

Each resource type stores the owner identifier differently:

| Resource | Model Field | Set By |
|---|---|---|
| `StrategyDraft` | `user_id: str | None` | `DraftService.create_draft()` |
| `LocalDatasetEntry` | `user_id: str | None` | `DatasetCatalog.register()` |
| `BacktestRunSummary` | `owner_user_id: str | None` | `BacktestRunService.create_backtest_run()` |

All ownership fields default to `None` for backward compatibility. Resources with `user_id=None` (legacy resources) are treated as inaccessible to any authenticated user — they are excluded from list results and raise not-found errors on direct access. This is intentional: it prevents accidental cross-user data exposure without requiring a migration.

## Access Control Rules

**Information hiding**: wrong-owner errors are indistinguishable from not-found errors. The repository layer raises `DraftNotFoundError` (or `UnknownDatasetError`) regardless of whether a draft truly doesn't exist or belongs to a different user. Routes return HTTP 404 in both cases. `BacktestAccessDeniedError` also maps to HTTP 404.

**Public endpoints**: `GET /tools`, `GET /market-data/providers`, `GET /health`, and `POST /strategy-runs/run` (file-based) do not require authentication and remain unchanged. Payload-only endpoints without a `{draft_id}` in the URL (e.g. `POST /semantics/validate`) also do not require auth.

**All other draft, catalog, composition, semantics, backtest, and run-by-draft endpoints** require a valid JWT. The `user_id` is extracted from `current_user.user_id` via FastAPI's `Depends(get_current_user)` — it is never read from the request body or query string.

## Audit Events

The following `AuditEventKind` values are emitted for ownership-sensitive actions:

- `DRAFT_CREATED`, `DRAFT_UPDATED`, `DRAFT_DELETED`, `DRAFT_ARCHIVED` — emitted by `DraftService`
- `DRAFT_OWNERSHIP_DENIED`, `DATASET_OWNERSHIP_DENIED`, `BACKTEST_OWNERSHIP_DENIED` — reserved for future use (currently not emitted on denial; denial surfaces as a 404 to avoid leaking information)

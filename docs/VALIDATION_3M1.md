# Phase 3M.1 — Browser-Level Authentication & Ownership Validation

## Objective

Runtime integrity validation of the complete authenticated ownership architecture
introduced across Phases 3K (auth backend), 3L (ownership scoping), and 3M
(frontend ownership integration). Validate ownership boundaries, session lifecycle,
authenticated downloads, and network header correctness. Fix any integration bugs
discovered.

---

## Flows Validated

### 1. Session lifecycle

| Flow | Result |
|------|--------|
| Page refresh → AuthGuard hydrates token via `GET /auth/me` → user remains logged in | PASS |
| Expired / invalid token → `/auth/me` returns 401 → AuthGuard shows LoginPage | PASS |
| AuthGuard loading state no longer shows blank screen (was `null`, now shows loading indicator) | FIXED |
| `logout()` clears token → all subsequent authedFetch calls receive 401 → redirect to LoginPage | PASS |

### 2. Multi-user ownership isolation (DraftWorkspace)

| Flow | Result |
|------|--------|
| User A creates draft — user B cannot see it in list | PASS |
| User A creates draft — user B `GET /drafts/{id}` returns 404 | PASS |
| User B `PUT /drafts/{id}/semantics` on user A's draft returns 404 | PASS |
| User B `POST /strategy-runs/run-composition` on user A's draft returns 404 | PASS (after fix) |
| User B `POST /backtests/runs` on user A's draft returns 404 | PASS (after fix) |

### 3. Authenticated downloads

| Flow | Result |
|------|--------|
| `downloadTradesCSV` injects Authorization header, receives CSV blob | PASS |
| `downloadEquityCSV` injects Authorization header, receives CSV blob | PASS |
| `downloadReportJSON` injects Authorization header, receives JSON blob | PASS |
| Download endpoints without valid token return 401 | PASS |

### 4. Network header correctness

| Check | Result |
|-------|--------|
| `authedFetch` sends `Authorization: Bearer <token>` on all protected routes | PASS |
| Public endpoints (`GET /tools`, `GET /health`, `POST /semantics/validate`, `POST /backtests/simulate`) work without Authorization header | PASS |
| `/catalog` proxy route present in Vite config | FIXED |

---

## Bugs Found and Fixed

### Bug 1: AuthGuard blank screen during token hydration

**Symptom:** On page refresh, AuthGuard returned `null` while `isLoading=true`,
producing a blank white screen for ~200 ms.

**Root cause:** `AuthGuard.tsx` had `if (isLoading) return null`.

**Fix:** Replaced `null` with a minimal dark-themed loading div:
```tsx
if (isLoading) return (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
                height: '100vh', background: '#0f0f1a', color: '#2a3040',
                fontFamily: 'monospace', fontSize: 12 }}>
    Loading…
  </div>
)
```

**File:** `frontend/src/components/AuthGuard.tsx`

---

### Bug 2: `/catalog` missing from Vite dev proxy

**Symptom:** Frontend API calls to `/catalog/...` did not reach the backend in
development; requests fell through with `404 Cannot GET /catalog/...` from Vite.

**Root cause:** `vite.config.ts` proxy block listed `'/drafts'`, `'/strategy-runs'`,
etc., but omitted `'/catalog'`.

**Fix:** Added `'/catalog': 'http://localhost:8000'` to the proxy map.

**File:** `frontend/vite.config.ts`

---

### Bug 3: Composition run returns 422 instead of 404 for wrong-owner draft

**Symptom:** `POST /strategy-runs/run-composition` with a draft owned by user A,
called as user B, returned HTTP 422. Expected: 404 (information hiding).

**Root cause:** `composition_run_service.py` was catching `DraftNotFoundError` and
re-raising it as `CompositionRunError`. The route mapped `CompositionRunError` → 422.

**Fix:**
- Removed the `try/except DraftNotFoundError` wrapper in the service; let the
  exception propagate directly to the route.
- Added `DraftNotFoundError` import and `except DraftNotFoundError → 404` handler
  in `backend/api/routes/strategy_runs.py`.

**Files:** `backend/api/services/composition_run_service.py`,
`backend/api/routes/strategy_runs.py`

---

### Bug 4: Backtest run returns 422 instead of 404 for wrong-owner draft

**Symptom:** Same as Bug 3 but for `POST /backtests/runs`.

**Root cause:** Same pattern — `backtest_run_service.py` wrapped `DraftNotFoundError`
inside `BacktestRunError`; route mapped `BacktestRunError` → 422.

**Fix:** Same approach — removed wrapper in service, added 404 handler in route.

**Files:** `backend/api/services/backtest_run_service.py`,
`backend/api/routes/backtest_runs.py`

---

## Tests Added / Updated

### New: `TestCompositionAndBacktestRunOwnership` (Phase 3M.1)

Added to `tests/unit/test_ownership.py` as section 10. Regression guards for Bugs 3 and 4.

| Test | Validates |
|------|-----------|
| `test_composition_run_wrong_owner_returns_404` | Wrong-owner draft → 404 from `POST /strategy-runs/run-composition` |
| `test_backtest_run_wrong_owner_returns_404` | Wrong-owner draft → 404 from `POST /backtests/runs` |
| `test_composition_run_requires_auth` | No token → 401 from `POST /strategy-runs/run-composition` |

Total `test_ownership.py` tests after addition: **53 passed**.

### New: `frontend/src/api/__tests__/authClients.test.ts` (Phase 3M)

17 tests covering:
- `AuthError` class and `isAuthError` type guard
- `authedFetch` header injection and 401 → `AuthError` propagation
- Protected clients all throw `AuthError` on 401 (drafts, semantics, composition run,
  backtest run, backtest report, plan inspection)
- `validateSemanticsPayload` does NOT throw `AuthError` on 401 (public endpoint)

---

## Known Limitations

- **Manual runtime browser testing only.** End-to-end tests with a real browser driver
  (Playwright / Cypress) are out of scope for this phase.
- **Single-user session only.** Multi-tab / multi-window session sharing not validated.
- **Token refresh not implemented.** Expired tokens require full re-login; there is no
  silent refresh mechanism.
- **Blob URL leak on download error.** If `resp.blob()` throws after `authedFetch`
  succeeds, `URL.revokeObjectURL` is not called. Low risk (browser cleans up on
  navigation), but noted.

---

## Architecture Invariants Enforced

These were confirmed to hold after all fixes:

1. Wrong-owner resource access returns the same HTTP 404 as not-found (information hiding).
2. All draft-scoped API endpoints require a valid Bearer token.
3. Public endpoints (`/health`, `/tools`, `/market-data/providers`,
   `POST /semantics/validate`, `POST /backtests/simulate`) require no token.
4. `DraftNotFoundError` must never be swallowed by service-layer errors that
   map to 422 — it must propagate to the route where it becomes 404.
5. Download endpoints use authenticated blob-URL pattern; no plain anchor-href
   downloads for protected resources.

# Subscription Expiry Enforcement

## Overview

Phase 3P-C implements **lazy subscription expiry enforcement**: expired subscriptions are detected and transitioned automatically when a user attempts protected platform access — no background scheduler required.

---

## Lazy Enforcement Philosophy

Subscription enforcement is **request-driven**, not timer-driven.

When a regular user makes a request to a protected endpoint:

```
request
  → get_current_user (reads current DB state)
  → require_active_subscription
      → evaluate_subscription_expiry(user, repo)   ← Phase 3P-C
          - if active + expires_at in past → transition to expired + persist + audit
          - all other cases → no-op
      → has_platform_access check
      → allow or deny
```

The transition happens **once**, on the first request after expiry. Subsequent requests see `subscription_status=expired` in the DB and skip the evaluation entirely (idempotent).

### Why not a scheduler?

- Zero infrastructure: no Celery, APScheduler, cron, or daemon required.
- Deterministic: transitions occur at a known, observable point (the protected request).
- Auditable: the exact request that triggered expiry is captured by the audit event timestamp.
- Sufficient for this phase: the current subscription lifecycle is admin-managed. Automated renewal systems belong to a future payment integration phase.

---

## Admin Bypass

Admin users are **never auto-expired**. The `is_admin` check in `evaluate_subscription_expiry` is the first guard — admin users return immediately without any evaluation. This preserves the admin = role-based, subscriber = subscription-based separation defined in Phase 3P-A.1.

---

## Automatic active → expired Transition

Conditions for auto-expiry:
1. `role != admin`
2. `subscription_status == active`
3. `subscription_expires_at is not None`
4. `subscription_expires_at <= now (UTC)`

When all four conditions are met:
1. `User.with_expired()` creates an immutable updated user object
2. `UserRepository.update(expired_user)` persists the change atomically
3. `emit_audit_event(SUBSCRIPTION_EXPIRED, {user_id, subscription_expires_at})` records the transition
4. `require_active_subscription` denies the request with HTTP 403

### UTC handling

`subscription_expires_at` is stored as an ISO-8601 string. If no timezone is present (naive datetime), it is treated as UTC. All comparisons use `datetime.now(timezone.utc)`.

### Malformed expiry dates

If `subscription_expires_at` cannot be parsed, the user is left unchanged and no transition occurs. The admin must correct the field manually.

---

## No Repeated Audit Spam

`SUBSCRIPTION_EXPIRED` is emitted exactly once per user per expiry cycle:
- First request after expiry: `active` → `expired` + emit
- All subsequent requests: status is already `expired` → evaluation skipped

If a user is reactivated and expires again, the cycle repeats once.

---

## Frontend Behavior

When a protected API call returns 403 with `subscription_required`:
1. `authedFetch` detects `detail.code === 'subscription_required'` in the response body
2. Throws `SubscriptionExpiredError`
3. `App.tsx` catches `SubscriptionExpiredError` and calls `refreshUser()`
4. `refreshUser()` calls `GET /auth/me` and updates the auth context with the new `subscription_status=expired`
5. `SubscriptionGate` detects `subscription_status=expired` and shows the expired screen

The user sees the "Subscription Expired" blocking screen without requiring a page refresh.

---

## Future Scheduler/Payment Roadmap

This phase is intentionally limited to the lazy-enforcement model. Future phases will extend it:

**Phase 3P-D (suggested): Scheduled Expiry Sweep**
- Periodic background task (Celery or APScheduler)
- Calls `evaluate_subscription_expiry` for all active users with past `subscription_expires_at`
- Sends expiry notification emails
- Useful for: cleaning up stale active records, triggering emails at exact expiry time

**Future: Payment Renewal Integration**
```
payment success / renewal webhook
  → SubscriptionService.extend(user_id, new_expires_at)
      → validate_future_expiry(new_expires_at)
      → UserRepository.update(user with new expiry)
      → emit EXPIRY_UPDATED
  → lazy enforcement on next request: new expiry is in the future → no-op
```

`evaluate_subscription_expiry` in `backend/auth/expiry.py` is a module-level function (not a class method) — intentionally extractable for use by a future `SubscriptionService` without importing any admin-layer infrastructure.

---

## Files Introduced / Modified

| File | Change |
|---|---|
| `backend/auth/expiry.py` | New — `evaluate_subscription_expiry()` |
| `backend/auth/models.py` | `User.with_expired()` state transition |
| `backend/auth/dependencies.py` | `_get_user_repository` renamed to public `get_user_repository` |
| `backend/auth/entitlement.py` | `require_active_subscription` injects repo + calls expiry evaluation |
| `frontend/src/api/client.ts` | `SubscriptionExpiredError` + 403 detection in `authedFetch` |
| `frontend/src/auth/AuthContext.tsx` | `refreshUser()` function |
| `frontend/src/App.tsx` | Catches `SubscriptionExpiredError` → `refreshUser()` |

# Admin Governance

## Overview

QuantLab uses a three-tier access model (Phase 3P-D):

| Role | Access Model | Who can promote/demote |
|---|---|---|
| `user` | Subscription-based (requires `active` status) | Superadmin can promote to `admin` |
| `admin` | Role-based (subscription irrelevant) | Superadmin can demote to `user` |
| `superadmin` | Role-based, platform owner | No demotion path via API |

See `docs/ADMIN_ENTITLEMENT_SEPARATION.md` for the subscription separation model.

---

## Role Hierarchy (Phase 3P-D)

```
superadmin
    ├── is_admin = True
    ├── is_superadmin = True
    ├── has_platform_access = True (unconditional)
    └── can: promote user→admin, demote admin→user, act on any user

admin
    ├── is_admin = True
    ├── is_superadmin = False
    ├── has_platform_access = True (unconditional)
    └── can: subscription management; cannot act on superadmin accounts

user
    ├── is_admin = False
    ├── is_superadmin = False
    └── has_platform_access = is_entitled (subscription-based)
```

`is_admin` is True for **both** `admin` and `superadmin`. All routes protected by `require_admin_role` accept either. Routes that require superadmin-exclusive operations use `require_superadmin_role`.

---

## Admin Lifecycle

```
bootstrap email registration → role=superadmin, subscription_status=pending
                             → has_platform_access = True (role-based; subscription irrelevant)

accounts created before Phase 3P-D → role=admin
one-time migration: .venv/bin/python backend/scripts/promote_superadmin.py
```

Admin accounts are bootstrapped via `admin_bootstrap_email` in `core/config.py`. Since Phase 3P-D, the bootstrap produces `role=superadmin`. Accounts registered before this change have `role=admin` and must be migrated using the promotion script.

Admins are not subject to subscription lifecycle enforcement. `require_admin_role` depends only on `get_current_user` — never on `require_active_subscription`. This means admins can continue to manage user subscriptions even if their own subscription_expires_at lapses.

---

## Subscriber Lifecycle

```
register → subscription_status=pending
         → admin approves (sets subscription_expires_at) → status=active
         → expiry reached or admin suspends → status=expired / suspended
         → admin reactivates (sets new subscription_expires_at) → status=active
```

New user registrations always default to `pending`. No user gains active access without explicit admin approval. There is no self-service subscription activation path.

---

## Expiry Governance

### Phase 3P-B.1 (Current): Admin Manual Override

`subscription_expires_at` is set manually by an admin at:

- approval time (`POST /admin/users/{id}/approve`)
- reactivation time (`POST /admin/users/{id}/reactivate`)
- update time (`POST /admin/users/{id}/update-expiry`)

All three paths call `validate_future_expiry()` before writing. Expiry must be a valid ISO-8601 datetime strictly in the future.

### Future: Automated Subscription Service

`subscription_expires_at` is intentionally not hardcoded to manual admin control. The field is designed to accept writes from a future `SubscriptionService`:

```
payment success / renewal webhook
    → SubscriptionService.extend(user_id, new_expires_at)
        → validate_future_expiry(new_expires_at)
        → UserRepository.update(user)
        → emit_audit_event(EXPIRY_UPDATED, ...)
```

The admin update-expiry path remains available as a support/override tool.

`validate_future_expiry()` is a module-level function in `admin_service.py` — not a class method — so it can be extracted into a shared module without coupling the future `SubscriptionService` to `AdminService`.

---

## Admin Self-Suspension Prevention

An admin cannot suspend their own account. If `admin_user_id == target_user_id`, the suspend endpoint raises `AdminSelfSuspensionError` (HTTP 403, code `admin_self_suspension`) and emits an `ADMIN_SELF_SUSPENSION_DENIED` audit event.

This check fires before any database reads.

---

## Last-Admin Protection

If the target user is the sole remaining admin, the suspend endpoint raises `LastAdminProtectionError` (HTTP 403, code `last_admin_protection`) and emits a `LAST_ADMIN_SUSPENSION_DENIED` audit event.

This prevents platform lockout. The check counts all users where `u.is_admin` in the repository. If exactly one admin exists, suspension is rejected regardless of who is requesting it.

The self-suspension check fires first. The last-admin check applies when a different admin (or an automated actor) attempts to suspend the last admin account.

---

## User Deletion Policy

Hard user deletion is not supported. There is no `DELETE /admin/users/{id}` endpoint, and no soft-delete flag. The Admin Console exposes no delete button.

The rationale: subscription and audit history must remain intact for governance traceability. User lifecycle is managed exclusively through status transitions (pending → active → suspended/expired → active).

---

## Superadmin Role Management (Phase 3P-D)

Superadmins can promote regular users to admin and demote regular admins back to user:

| Endpoint | Requires | Action |
|---|---|---|
| `POST /admin/users/{id}/promote-to-admin` | `superadmin` | `role=user → role=admin` |
| `POST /admin/users/{id}/demote-to-user` | `superadmin` | `role=admin → role=user` |

### Guards enforced at the service layer

- Self-modification: superadmin cannot promote/demote their own account.
- Target validation: promote only accepts `role=user`; demote only accepts `role=admin`.
- Superadmin accounts cannot be demoted via these endpoints (backend raises `UnauthorizedRoleChangeError`).
- Regular admins cannot access these endpoints (FastAPI `require_superadmin_role` returns HTTP 403).
- Regular admins cannot suspend superadmin accounts (Guard 2 in `suspend_user`).

### Frontend defence-in-depth

- Promote/Demote buttons are only rendered when the viewer has `role=superadmin`.
- Regular admin viewers see no action buttons on superadmin rows.
- All role changes are sent to the backend; the frontend holds no authority.

---

## Admin Role Lifecycle Safety

- No public promote-to-admin endpoint exists.
- Admin role cannot be self-assigned through any API.
- Frontend-only role changes are not honoured — backend is the authority.
- `require_admin_role` is enforced on every admin route via FastAPI `Depends`.
- `require_superadmin_role` is enforced on promote/demote routes.
- The admin nav tab in the frontend is hidden for non-admin users (defence-in-depth; backend enforces the role check independently).

---

## Audit Integration

All governance actions emit structured audit events via `emit_audit_event`.

| Event kind | Trigger |
|---|---|
| `USER_APPROVED` | Admin approves a pending user |
| `SUBSCRIPTION_ACTIVATED` | User subscription set to active |
| `SUBSCRIPTION_SUSPENDED` | User subscription suspended |
| `SUBSCRIPTION_EXPIRED` | User subscription expired |
| `ENTITLEMENT_DENIED` | Non-admin user blocked by `require_active_subscription` |
| `EXPIRY_UPDATED` | Admin updates `subscription_expires_at` for an active user |
| `ADMIN_SELF_SUSPENSION_DENIED` | Admin attempted to suspend their own account |
| `LAST_ADMIN_SUSPENSION_DENIED` | Suspension of last admin blocked |
| `ROLE_PROMOTED` | Superadmin promotes a user to admin |
| `ROLE_DEMOTED` | Superadmin demotes an admin to user |
| `UNAUTHORIZED_ROLE_CHANGE_ATTEMPT` | Self-modification or role change blocked |
| `LAST_SUPERADMIN_PROTECTION_DENIED` | Reserved for future last-superadmin guard |

---

## Admin Console Design Constraints

The Admin Console (`frontend/src/components/AdminConsole.tsx`) is a support/override tool. It must not become the primary billing or subscription management engine. Constraints:

- No delete button for any user.
- Admin cannot act on their own row (own row shows "You" label; action buttons are hidden).
- Expiry input is required before Approve/Update/Reactivate — buttons are disabled if the input is empty or not a future date.
- All mutations are sent to the backend; frontend holds no authority.
- No password_hash, credential secret, or provider key is rendered anywhere in the console.

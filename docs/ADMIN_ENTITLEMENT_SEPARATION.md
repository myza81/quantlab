# Admin / Subscriber Entitlement Separation (Phase 3P-A.1)

## Architectural Rule

```
Identity  ≠  Subscription Entitlement  ≠  Governance Authority
```

QuantLab has two distinct access models. They must not be conflated.

---

## Admin / Governance Account

| Attribute | Value |
|---|---|
| `role` | `admin` |
| `subscription_status` | Not evaluated for platform access |
| `subscription_expires_at` | Not evaluated for platform access |
| Access gate | `User.is_admin == True` → `has_platform_access == True` |
| Blocked by subscription expiry | **No** |
| Can manage users | Yes — via `/admin/users/*` routes |
| Can access all app features | Yes |

Admin accounts are **platform governance identities**. They exist to approve, suspend, and manage subscriber accounts. Their access is role-based and does not participate in the subscription lifecycle.

An admin with `subscription_status=pending` and an expired `subscription_expires_at` still has full platform and admin access.

---

## Subscriber Account

| Attribute | Value |
|---|---|
| `role` | `user` |
| `subscription_status` | Must be `active` |
| `subscription_expires_at` | If set, must be in the future |
| Access gate | `User.is_entitled == True` → `has_platform_access == True` |
| Blocked when | `pending`, `expired`, `suspended`, or past expiry |
| Can manage users | No |

Regular users are **commercial entitlement identities**. They must be approved by an admin before accessing protected features. Their access is subscription-based and passes through the full lifecycle:

```
pending → active → expired / suspended
```

---

## Implementation

### `User.has_platform_access` (backend/auth/models.py)

```python
@property
def has_platform_access(self) -> bool:
    if self.is_admin:
        return True          # role-based — subscription_status irrelevant
    return self.is_entitled  # subscription-based
```

### `require_active_subscription` (backend/auth/entitlement.py)

All protected routes use `Depends(require_active_subscription)`. This dependency calls `has_platform_access`:

- Admins → pass unconditionally
- Active subscribers → pass
- Pending / expired / suspended regular users → HTTP 403 with `{"code": "subscription_required"}`

### `require_admin_role` (backend/auth/entitlement.py)

Admin-only routes use `Depends(require_admin_role)`. This dependency checks `is_admin` only — it does **not** call `require_active_subscription`. This means admins can manage users even if their own subscription lapses.

### `SubscriptionGate` (frontend/src/components/SubscriptionGate.tsx)

The frontend gate mirrors the backend rule:

```tsx
if (user.role === 'admin') return <>{children}</>   // governance — always pass
if (status === 'active')   return <>{children}</>   // subscriber — pass if active
// else: show status-specific blocking screen
```

Admin users never see the pending/expired/suspended blocking screens.

---

## Admin Bootstrap

The first admin account is created by registering with the email configured in `ADMIN_BOOTSTRAP_EMAIL`. The bootstrap sets **only `role=admin`**:

```python
user = replace(user, role=UserRole.admin, approved_by_user_id="bootstrap")
# subscription_status stays pending — irrelevant for admins
```

`subscription_status=pending` is the correct state for a bootstrap admin. Platform access is granted by role, not by subscription status. Forcing `subscription_status=active` would incorrectly imply the admin is a paid subscriber.

---

## Lifecycle Diagram

```
Registration:
  any email     → role=user,  subscription_status=pending  → blocked until approved
  bootstrap email → role=admin, subscription_status=pending  → platform access by role

Admin action:
  /admin/users/{id}/approve   → subscription_status=active   → subscriber unlocked
  /admin/users/{id}/suspend   → subscription_status=suspended → subscriber blocked
  /admin/users/{id}/reactivate→ subscription_status=active   → subscriber unlocked

Entitlement check (require_active_subscription):
  role=admin  →  has_platform_access=True  (role bypasses subscription)
  role=user + status=active + not expired  →  has_platform_access=True
  role=user + status=pending/expired/suspended  →  HTTP 403
```

---

## What Must NOT Happen

- Admin accounts must not be forced into `subscription_status=active` to gain access
- The frontend must not show admins as blocked subscribers
- `require_admin_role` must never depend on `require_active_subscription`
- There must be no public API endpoint to set `role=admin`
- Subscription enforcement for regular users must not be weakened

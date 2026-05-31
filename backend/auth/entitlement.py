"""
Entitlement dependencies for FastAPI route protection.

Two dependency functions:
  - require_active_subscription: platform access gate — passes admins (role-based)
    and active subscribers (entitlement-based); blocks pending/expired/suspended users.
    Phase 3P-C: also performs lazy subscription expiry enforcement on every request.
  - require_admin_role: governance gate — passes only admin-role users, regardless
    of subscription status.

Separation of concerns:
  Admin accounts are platform governance identities — access is determined by role.
  Subscriber accounts are commercial entitlement identities — access requires an
  active, unexpired subscription.
  require_active_subscription enforces BOTH paths via User.has_platform_access.

Lazy expiry enforcement (Phase 3P-C):
  When a normal user's subscription_expires_at is in the past and their status is
  still active, require_active_subscription automatically transitions them to
  expired, persists the change, and emits SUBSCRIPTION_EXPIRED — all within the
  request that triggered the check.  No scheduler or background job is needed.

HTTP 403 is returned for authenticated-but-not-permitted users.
HTTP 401 is returned by get_current_user for unauthenticated requests.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from backend.auth.dependencies import get_current_user, get_user_repository
from backend.auth.expiry import evaluate_subscription_expiry
from backend.auth.models import User, UserRole
from backend.auth.repository import UserRepository
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event


def require_active_subscription(
    current_user: User = Depends(get_current_user),
    repository: UserRepository = Depends(get_user_repository),
) -> User:
    """
    Gate a route to users with platform access.

    Passes:
      - Admin users unconditionally (role-based governance access).
      - Regular users with subscription_status=active and a non-expired
        subscription_expires_at.

    Performs lazy expiry enforcement: if a regular user's active subscription
    has passed its expiry date, transitions them to expired before evaluating
    access.  The transition is persisted and audited exactly once.

    Raises HTTP 403 for regular users that are pending, expired, or suspended.
    Emits ENTITLEMENT_DENIED audit event only for non-admin rejections.
    """
    current_user = evaluate_subscription_expiry(current_user, repository)

    if not current_user.has_platform_access:
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.ENTITLEMENT_DENIED,
            details={
                "user_id": current_user.user_id,
                "subscription_status": current_user.subscription_status,
            },
        ))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "subscription_required",
                "subscription_status": current_user.subscription_status,
            },
        )
    return current_user


def require_admin_role(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Gate a route to admin or superadmin users.

    Intentionally depends on get_current_user, NOT require_active_subscription,
    so admins retain management access even if their subscription lapses.

    Raises HTTP 403 if the user does not hold the admin or superadmin role.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_required"},
        )
    return current_user


def require_superadmin_role(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Gate a route to superadmin users only.

    Used for role management operations (promote/demote) that must be restricted
    to the platform owner. Regular admins are rejected.

    Raises HTTP 403 if the user does not hold the superadmin role.
    """
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "superadmin_required"},
        )
    return current_user

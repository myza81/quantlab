"""
Entitlement dependencies for FastAPI route protection.

Two dependency functions:
  - require_active_subscription: authenticated + entitled (active, unexpired)
  - require_admin_role: authenticated + admin role (does NOT require active subscription,
    so admins can manage users even if their own subscription lapses)

HTTP 403 is returned for authenticated-but-not-entitled users.
HTTP 401 is returned by get_current_user for unauthenticated requests.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from backend.auth.dependencies import get_current_user
from backend.auth.models import User, UserRole
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event


def require_active_subscription(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Gate a route to active, entitled users only.

    Raises HTTP 403 if the user is pending, expired, or suspended.
    Emits ENTITLEMENT_DENIED audit event on rejection.
    """
    if not current_user.is_entitled:
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
    Gate a route to admin users only.

    Intentionally depends on get_current_user, NOT require_active_subscription,
    so admins retain management access even if their subscription lapses.

    Raises HTTP 403 if the user does not hold the admin role.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_required"},
        )
    return current_user

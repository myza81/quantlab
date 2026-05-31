"""
Lazy subscription expiry enforcement — Phase 3P-C.

evaluate_subscription_expiry() is the single authoritative path for
automatic active → expired transitions.  It is called by
require_active_subscription on every protected request, so no background
scheduler is needed.

Design intent:
  - Admin users are NEVER auto-expired (role-based access, subscription irrelevant).
  - Only subscription_status == active users are evaluated.
  - If subscription_expires_at is in the past, the user is transitioned to
    expired, persisted, and audited in a single call.
  - Idempotent: if status is already expired/suspended/pending the function
    returns immediately without any write.
  - Malformed expiry dates are left unchanged and deferred to admin intervention.

Future reuse:
  This function is intentionally module-level (not a class method) so a future
  SubscriptionService can import it without depending on AdminService or any
  admin-layer infrastructure.

  Future path:
    payment renewal webhook
      → SubscriptionService.extend(user_id, new_expires_at)
          → validate_future_expiry(new_expires_at)   [from admin_service.py]
          → UserRepository.update(user)
          → evaluate_subscription_expiry is NOT called here (renewal extends, not expires)
      → lazy enforcement remains request-driven only
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.auth.models import SubscriptionStatus, User
from backend.auth.repository import UserRepository
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event


def evaluate_subscription_expiry(user: User, repo: UserRepository) -> User:
    """
    Check whether a user's active subscription has passed its expiry date.

    If so: transition to expired, persist, emit SUBSCRIPTION_EXPIRED, and
    return the updated User object.  In all other cases return the original
    user unchanged.

    This function is idempotent — calling it on a user whose status is already
    expired/suspended/pending is a no-op.
    """
    # Admins are governed by role, not subscription lifecycle.
    if user.is_admin:
        return user

    # Only active subscriptions can lapse — already-expired/suspended/pending skip.
    if user.subscription_status != SubscriptionStatus.active:
        return user

    # No expiry date set — subscription has no time limit; still valid.
    if user.subscription_expires_at is None:
        return user

    try:
        expires_at = datetime.fromisoformat(user.subscription_expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        # Malformed date — cannot evaluate; leave as-is, defer to admin.
        return user

    if datetime.now(timezone.utc) < expires_at:
        return user  # still within the active window

    expired_user = user.with_expired()
    repo.update(expired_user)
    emit_audit_event(AuditEvent(
        event_kind=AuditEventKind.SUBSCRIPTION_EXPIRED,
        details={
            "user_id": user.user_id,
            "subscription_expires_at": user.subscription_expires_at,
        },
    ))
    return expired_user

"""
AdminService — user subscription management operations.

All state transitions produce immutable new User instances and persist via
UserRepository.update(). Audit events are emitted for every action.

Design note — subscription_expires_at is service-agnostic:
  The User.subscription_expires_at field and UserRepository.update() are not
  coupled to this admin service. They are the same primitives that a future
  SubscriptionService (payment / renewal webhook path) will write through:

      payment success → SubscriptionService.process_renewal(user_id, new_expiry)
                      → UserRepository.update(replace(user, subscription_expires_at=...))
                      → AuditEvent(SUBSCRIPTION_ACTIVATED, ...)

  AdminService is the manual-override path for this phase only. The data model
  and persistence layer are forward-compatible with automated subscription
  lifecycle management without any changes to UserRepository or User.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from backend.auth.models import User, UserRole
from backend.auth.repository import UserRepository
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event


# ---------------------------------------------------------------------------
# Service errors
# ---------------------------------------------------------------------------

class UserNotFoundError(Exception):
    pass


class InvalidExpiryError(Exception):
    """Expiry date is in the past, malformed, or otherwise invalid.

    Designed as a shared validation primitive — future SubscriptionService and
    payment webhook handlers should reuse or import this error class rather than
    defining their own.
    """


class AdminSelfSuspensionError(Exception):
    """Admin attempted to suspend their own account."""


class LastAdminProtectionError(Exception):
    """Suspension would remove the last admin account from the platform."""


class UnauthorizedRoleChangeError(Exception):
    """Operation is not permitted for the calling role or target state."""


# ---------------------------------------------------------------------------
# Shared validation helper
# ---------------------------------------------------------------------------

def validate_future_expiry(expiry_str: str | None) -> None:
    """Validate that expiry_str, if provided, is a future UTC datetime.

    Raises InvalidExpiryError if the value is present but invalid or in the past.
    Passes silently for None (no-expiry / lifetime subscription).

    This function is intentionally module-level (not a method) so it can be
    imported by future service layers (e.g. SubscriptionService) without
    pulling in AdminService.
    """
    if expiry_str is None:
        return
    try:
        expiry = datetime.fromisoformat(expiry_str)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise InvalidExpiryError("Subscription expiry must be in the future")
    except (ValueError, TypeError) as exc:
        raise InvalidExpiryError(f"Invalid expiry date format: {expiry_str!r}") from exc


# ---------------------------------------------------------------------------
# Admin service
# ---------------------------------------------------------------------------

class AdminService:
    def __init__(self, repository: UserRepository) -> None:
        self._repo = repository

    def list_users(self) -> list[User]:
        return self._repo.list_all()

    def get_user(self, user_id: str) -> User:
        user = self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    def approve_user(
        self,
        *,
        target_user_id: str,
        admin_user_id: str,
        subscription_expires_at: str | None = None,
        notes: str | None = None,
    ) -> User:
        validate_future_expiry(subscription_expires_at)
        user = self.get_user(target_user_id)
        updated = user.with_active_subscription(
            approved_by_user_id=admin_user_id,
            subscription_expires_at=subscription_expires_at,
            notes=notes,
        )
        self._repo.update(updated)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.USER_APPROVED,
            details={
                "target_user_id": target_user_id,
                "approved_by": admin_user_id,
                "subscription_expires_at": subscription_expires_at,
            },
        ))
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.SUBSCRIPTION_ACTIVATED,
            details={"user_id": target_user_id},
        ))
        return updated

    def suspend_user(
        self,
        *,
        target_user_id: str,
        admin_user_id: str,
        admin_is_superadmin: bool = False,
        reason: str | None = None,
    ) -> User:
        # Guard 1: admin cannot suspend themselves
        if admin_user_id == target_user_id:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.ADMIN_SELF_SUSPENSION_DENIED,
                details={"user_id": admin_user_id},
            ))
            raise AdminSelfSuspensionError("Admin cannot suspend their own account")

        target = self.get_user(target_user_id)

        # Guard 2: regular admins cannot act on superadmin accounts
        if target.is_superadmin and not admin_is_superadmin:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.UNAUTHORIZED_ROLE_CHANGE_ATTEMPT,
                details={
                    "target_user_id": target_user_id,
                    "admin_user_id": admin_user_id,
                    "reason": "admin_cannot_modify_superadmin",
                },
            ))
            raise UnauthorizedRoleChangeError(
                "Admins cannot act on superadmin accounts"
            )

        # Guard 3: cannot suspend the last remaining admin-level user
        if target.is_admin:
            all_admins = [u for u in self._repo.list_all() if u.is_admin]
            if len(all_admins) <= 1:
                emit_audit_event(AuditEvent(
                    event_kind=AuditEventKind.LAST_ADMIN_SUSPENSION_DENIED,
                    details={
                        "target_user_id": target_user_id,
                        "admin_user_id": admin_user_id,
                    },
                ))
                raise LastAdminProtectionError(
                    "Cannot suspend the last admin account — platform would lose governance access"
                )

        updated = target.with_suspended(reason=reason)
        self._repo.update(updated)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.SUBSCRIPTION_SUSPENDED,
            details={
                "user_id": target_user_id,
                "suspended_by": admin_user_id,
                "reason": reason,
            },
        ))
        return updated

    def promote_to_admin(
        self,
        *,
        target_user_id: str,
        superadmin_user_id: str,
    ) -> User:
        """Promote a normal user (role=user) to role=admin.

        Only callable by a superadmin (enforced at the route level via
        require_superadmin_role; this service adds defence-in-depth checks).
        """
        if target_user_id == superadmin_user_id:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.UNAUTHORIZED_ROLE_CHANGE_ATTEMPT,
                details={
                    "target_user_id": target_user_id,
                    "superadmin_user_id": superadmin_user_id,
                    "reason": "self_role_change",
                },
            ))
            raise UnauthorizedRoleChangeError("Cannot modify your own role")

        target = self.get_user(target_user_id)
        if target.role != UserRole.user:
            raise UnauthorizedRoleChangeError(
                f"Can only promote role=user to admin; target has role={target.role}"
            )

        updated = target.with_admin_role()
        self._repo.update(updated)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.ROLE_PROMOTED,
            details={
                "target_user_id": target_user_id,
                "promoted_by": superadmin_user_id,
                "new_role": UserRole.admin,
            },
        ))
        return updated

    def demote_to_user(
        self,
        *,
        target_user_id: str,
        superadmin_user_id: str,
    ) -> User:
        """Demote a regular admin (role=admin) back to role=user.

        Superadmin accounts cannot be demoted via this endpoint — use a dedicated
        superadmin demotion workflow if needed (not in scope for Phase 3P-D).
        """
        if target_user_id == superadmin_user_id:
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.UNAUTHORIZED_ROLE_CHANGE_ATTEMPT,
                details={
                    "target_user_id": target_user_id,
                    "superadmin_user_id": superadmin_user_id,
                    "reason": "self_role_change",
                },
            ))
            raise UnauthorizedRoleChangeError("Cannot modify your own role")

        target = self.get_user(target_user_id)
        if target.role != UserRole.admin:
            raise UnauthorizedRoleChangeError(
                f"Can only demote role=admin to user; target has role={target.role}"
            )

        updated = target.with_user_role()
        self._repo.update(updated)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.ROLE_DEMOTED,
            details={
                "target_user_id": target_user_id,
                "demoted_by": superadmin_user_id,
                "previous_role": UserRole.admin,
            },
        ))
        return updated

    def reactivate_user(
        self,
        *,
        target_user_id: str,
        admin_user_id: str,
        subscription_expires_at: str | None = None,
    ) -> User:
        validate_future_expiry(subscription_expires_at)
        user = self.get_user(target_user_id)
        updated = user.with_reactivated(subscription_expires_at=subscription_expires_at)
        self._repo.update(updated)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.SUBSCRIPTION_ACTIVATED,
            details={
                "user_id": target_user_id,
                "reactivated_by": admin_user_id,
                "subscription_expires_at": subscription_expires_at,
            },
        ))
        return updated

    def update_expiry(
        self,
        *,
        target_user_id: str,
        admin_user_id: str,
        subscription_expires_at: str,
    ) -> User:
        """Update the subscription expiry for an existing user (admin override path).

        This is the manual admin override for this phase. When automated payment
        processing is introduced, it will write to the same subscription_expires_at
        field via SubscriptionService → UserRepository.update(), bypassing this method.
        """
        validate_future_expiry(subscription_expires_at)
        user = self.get_user(target_user_id)
        updated = replace(user, subscription_expires_at=subscription_expires_at)
        self._repo.update(updated)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.EXPIRY_UPDATED,
            details={
                "target_user_id": target_user_id,
                "updated_by": admin_user_id,
                "subscription_expires_at": subscription_expires_at,
            },
        ))
        return updated

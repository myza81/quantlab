"""
AdminService — user subscription management operations.

All state transitions produce immutable new User instances and persist via
UserRepository.update(). Audit events are emitted for every action.
"""
from __future__ import annotations

from backend.auth.models import User
from backend.auth.repository import UserRepository
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event


class UserNotFoundError(Exception):
    pass


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
        reason: str | None = None,
    ) -> User:
        user = self.get_user(target_user_id)
        updated = user.with_suspended(reason=reason)
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

    def reactivate_user(
        self,
        *,
        target_user_id: str,
        admin_user_id: str,
        subscription_expires_at: str | None = None,
    ) -> User:
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

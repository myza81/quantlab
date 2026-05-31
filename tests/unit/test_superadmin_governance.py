"""
Phase 3P-D — Superadmin & Admin Role Management

Tests cover:
  - UserRole.superadmin model: is_admin, is_superadmin, has_platform_access
  - require_superadmin_role: superadmin passes, admin rejected, user rejected
  - AdminService.promote_to_admin: happy path, target must be role=user, self-promotion blocked,
    not-found error, audit event emitted
  - AdminService.demote_to_user: happy path, target must be role=admin (not superadmin), self-demotion
    blocked, not-found error, audit event emitted
  - suspend_user guard: regular admin cannot act on superadmin target
  - AuthService.migrate_to_superadmin: promotes role=admin, idempotent for superadmin,
    returns None for non-admin, returns None for missing email
  - Bootstrap registration: superadmin role produced for bootstrap email
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import HTTPException

from backend.auth.models import SubscriptionStatus, User, UserRole
from backend.auth.repository import UserRepository
from backend.auth.service import AuthService
from backend.core.audit import AuditEventKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(
    user_id: str = "u1",
    username: str = "user",
    role: UserRole = UserRole.user,
    subscription_status: SubscriptionStatus = SubscriptionStatus.active,
    **kwargs,
) -> User:
    email = kwargs.pop("email", f"{username}@example.com")
    return User(
        user_id=user_id,
        username=username,
        email=email,
        password_hash="$2b$12$hash",
        created_at="2025-01-01T00:00:00+00:00",
        role=role,
        subscription_status=subscription_status,
        **kwargs,
    )


def _superadmin(**kwargs) -> User:
    return _make_user(user_id="sa1", username="superadmin", role=UserRole.superadmin, **kwargs)


def _admin(**kwargs) -> User:
    return _make_user(user_id="adm1", username="admin", role=UserRole.admin, **kwargs)


def _user(**kwargs) -> User:
    return _make_user(user_id="usr1", username="user", role=UserRole.user, **kwargs)


def _make_repo(tmp_path: Path) -> UserRepository:
    return UserRepository(tmp_path / "users.json")


def _make_service(users: list[User], tmp_path: Path) -> "AdminService":
    from backend.api.services.admin_service import AdminService

    repo = _make_repo(tmp_path)
    for u in users:
        repo.save(u)
    return AdminService(repo)


# ---------------------------------------------------------------------------
# TestSuperadminRoleModel
# ---------------------------------------------------------------------------

class TestSuperadminRoleModel:
    def test_is_superadmin_true_for_superadmin(self):
        assert _superadmin().is_superadmin is True

    def test_is_superadmin_false_for_admin(self):
        assert _admin().is_superadmin is False

    def test_is_superadmin_false_for_user(self):
        assert _user().is_superadmin is False

    def test_is_admin_true_for_superadmin(self):
        # Superadmin satisfies is_admin (admin-level access or above)
        assert _superadmin().is_admin is True

    def test_is_admin_true_for_admin(self):
        assert _admin().is_admin is True

    def test_is_admin_false_for_user(self):
        assert _user().is_admin is False

    def test_superadmin_has_platform_access_regardless_of_subscription(self):
        for status in SubscriptionStatus:
            sa = _superadmin(subscription_status=status)
            assert sa.has_platform_access is True, f"failed for status={status}"

    def test_with_admin_role_sets_admin(self):
        u = _user()
        upgraded = u.with_admin_role()
        assert upgraded.role == UserRole.admin
        assert u.role == UserRole.user  # original unchanged

    def test_with_user_role_sets_user(self):
        a = _admin()
        downgraded = a.with_user_role()
        assert downgraded.role == UserRole.user
        assert a.role == UserRole.admin  # original unchanged


# ---------------------------------------------------------------------------
# TestRequireSuperadminRoleDependency
# ---------------------------------------------------------------------------

class TestRequireSuperadminRoleDependency:
    def _invoke(self, user: User) -> User:
        from backend.auth.entitlement import require_superadmin_role
        return require_superadmin_role(current_user=user)

    def test_superadmin_passes(self):
        result = self._invoke(_superadmin())
        assert result.is_superadmin is True

    def test_admin_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            self._invoke(_admin())
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "superadmin_required"

    def test_user_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            self._invoke(_user())
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# TestPromoteToAdmin
# ---------------------------------------------------------------------------

class TestPromoteToAdmin:
    def test_promotes_user_to_admin(self, tmp_path):
        sa = _superadmin()
        target = _user()
        svc = _make_service([sa, target], tmp_path)
        result = svc.promote_to_admin(
            target_user_id=target.user_id,
            superadmin_user_id=sa.user_id,
        )
        assert result.role == UserRole.admin

    def test_non_user_role_raises(self, tmp_path):
        from backend.api.services.admin_service import UnauthorizedRoleChangeError
        sa = _superadmin()
        existing_admin = _admin()
        svc = _make_service([sa, existing_admin], tmp_path)
        with pytest.raises(UnauthorizedRoleChangeError):
            svc.promote_to_admin(
                target_user_id=existing_admin.user_id,
                superadmin_user_id=sa.user_id,
            )

    def test_self_promotion_raises(self, tmp_path):
        from backend.api.services.admin_service import UnauthorizedRoleChangeError
        sa = _superadmin()
        svc = _make_service([sa], tmp_path)
        with pytest.raises(UnauthorizedRoleChangeError, match="own role"):
            svc.promote_to_admin(
                target_user_id=sa.user_id,
                superadmin_user_id=sa.user_id,
            )

    def test_not_found_raises(self, tmp_path):
        from backend.api.services.admin_service import UserNotFoundError
        sa = _superadmin()
        svc = _make_service([sa], tmp_path)
        with pytest.raises(UserNotFoundError):
            svc.promote_to_admin(
                target_user_id="nonexistent",
                superadmin_user_id=sa.user_id,
            )

    def test_emits_role_promoted_audit_event(self, tmp_path):
        sa = _superadmin()
        target = _user()
        svc = _make_service([sa, target], tmp_path)
        with patch("backend.api.services.admin_service.emit_audit_event") as mock_emit:
            svc.promote_to_admin(
                target_user_id=target.user_id,
                superadmin_user_id=sa.user_id,
            )
        kinds = [c.args[0].event_kind for c in mock_emit.call_args_list]
        assert AuditEventKind.ROLE_PROMOTED in kinds

    def test_self_promotion_emits_unauthorized_audit_event(self, tmp_path):
        from backend.api.services.admin_service import UnauthorizedRoleChangeError
        sa = _superadmin()
        svc = _make_service([sa], tmp_path)
        with patch("backend.api.services.admin_service.emit_audit_event") as mock_emit:
            with pytest.raises(UnauthorizedRoleChangeError):
                svc.promote_to_admin(
                    target_user_id=sa.user_id,
                    superadmin_user_id=sa.user_id,
                )
        kinds = [c.args[0].event_kind for c in mock_emit.call_args_list]
        assert AuditEventKind.UNAUTHORIZED_ROLE_CHANGE_ATTEMPT in kinds


# ---------------------------------------------------------------------------
# TestDemoteToUser
# ---------------------------------------------------------------------------

class TestDemoteToUser:
    def test_demotes_admin_to_user(self, tmp_path):
        sa = _superadmin()
        target = _admin()
        svc = _make_service([sa, target], tmp_path)
        result = svc.demote_to_user(
            target_user_id=target.user_id,
            superadmin_user_id=sa.user_id,
        )
        assert result.role == UserRole.user

    def test_cannot_demote_superadmin(self, tmp_path):
        from backend.api.services.admin_service import UnauthorizedRoleChangeError
        sa = _superadmin()
        target_sa = _make_user(user_id="sa2", username="sa2", role=UserRole.superadmin)
        svc = _make_service([sa, target_sa], tmp_path)
        with pytest.raises(UnauthorizedRoleChangeError):
            svc.demote_to_user(
                target_user_id=target_sa.user_id,
                superadmin_user_id=sa.user_id,
            )

    def test_cannot_demote_plain_user(self, tmp_path):
        from backend.api.services.admin_service import UnauthorizedRoleChangeError
        sa = _superadmin()
        target = _user()
        svc = _make_service([sa, target], tmp_path)
        with pytest.raises(UnauthorizedRoleChangeError):
            svc.demote_to_user(
                target_user_id=target.user_id,
                superadmin_user_id=sa.user_id,
            )

    def test_self_demotion_raises(self, tmp_path):
        from backend.api.services.admin_service import UnauthorizedRoleChangeError
        sa = _superadmin()
        svc = _make_service([sa], tmp_path)
        with pytest.raises(UnauthorizedRoleChangeError, match="own role"):
            svc.demote_to_user(
                target_user_id=sa.user_id,
                superadmin_user_id=sa.user_id,
            )

    def test_not_found_raises(self, tmp_path):
        from backend.api.services.admin_service import UserNotFoundError
        sa = _superadmin()
        svc = _make_service([sa], tmp_path)
        with pytest.raises(UserNotFoundError):
            svc.demote_to_user(
                target_user_id="nonexistent",
                superadmin_user_id=sa.user_id,
            )

    def test_emits_role_demoted_audit_event(self, tmp_path):
        sa = _superadmin()
        target = _admin()
        svc = _make_service([sa, target], tmp_path)
        with patch("backend.api.services.admin_service.emit_audit_event") as mock_emit:
            svc.demote_to_user(
                target_user_id=target.user_id,
                superadmin_user_id=sa.user_id,
            )
        kinds = [c.args[0].event_kind for c in mock_emit.call_args_list]
        assert AuditEventKind.ROLE_DEMOTED in kinds


# ---------------------------------------------------------------------------
# TestAdminCannotActOnSuperadmin
# ---------------------------------------------------------------------------

class TestAdminCannotActOnSuperadmin:
    def test_regular_admin_cannot_suspend_superadmin(self, tmp_path):
        from backend.api.services.admin_service import UnauthorizedRoleChangeError
        sa = _superadmin()
        admin = _admin()
        svc = _make_service([sa, admin], tmp_path)
        with pytest.raises(UnauthorizedRoleChangeError):
            svc.suspend_user(
                target_user_id=sa.user_id,
                admin_user_id=admin.user_id,
                admin_is_superadmin=False,
            )

    def test_superadmin_can_suspend_superadmin(self, tmp_path):
        # Superadmin can act on another superadmin (two superadmins exist)
        sa1 = _superadmin()
        sa2 = _make_user(user_id="sa2", username="sa2", role=UserRole.superadmin)
        svc = _make_service([sa1, sa2], tmp_path)
        result = svc.suspend_user(
            target_user_id=sa2.user_id,
            admin_user_id=sa1.user_id,
            admin_is_superadmin=True,
        )
        assert result.subscription_status == SubscriptionStatus.suspended

    def test_admin_cannot_act_on_superadmin_emits_unauthorized_event(self, tmp_path):
        from backend.api.services.admin_service import UnauthorizedRoleChangeError
        sa = _superadmin()
        admin = _admin()
        svc = _make_service([sa, admin], tmp_path)
        with patch("backend.api.services.admin_service.emit_audit_event") as mock_emit:
            with pytest.raises(UnauthorizedRoleChangeError):
                svc.suspend_user(
                    target_user_id=sa.user_id,
                    admin_user_id=admin.user_id,
                    admin_is_superadmin=False,
                )
        kinds = [c.args[0].event_kind for c in mock_emit.call_args_list]
        assert AuditEventKind.UNAUTHORIZED_ROLE_CHANGE_ATTEMPT in kinds


# ---------------------------------------------------------------------------
# TestLastAdminProtectionWithSuperadmin
# ---------------------------------------------------------------------------

class TestLastAdminProtectionWithSuperadmin:
    def test_two_admins_suspension_succeeds(self, tmp_path):
        """With two admin-level users, suspending one is permitted."""
        sa1 = _superadmin()
        sa2 = _make_user(user_id="sa2", username="sa2", role=UserRole.superadmin)
        svc = _make_service([sa1, sa2], tmp_path)
        result = svc.suspend_user(
            target_user_id=sa2.user_id,
            admin_user_id=sa1.user_id,
            admin_is_superadmin=True,
        )
        assert result.subscription_status == SubscriptionStatus.suspended

    def test_last_admin_suspension_blocked(self, tmp_path):
        """With exactly one admin-level user, attempting to suspend them is blocked."""
        from backend.api.services.admin_service import LastAdminProtectionError
        sa = _superadmin()
        regular = _user()
        svc = _make_service([sa, regular], tmp_path)
        # Use a different actor_id so self-suspension guard doesn't fire first.
        # The service trusts the caller has validated the actor's auth — it only checks
        # the target is the last admin, not whether the actor_id is valid or admin-level.
        with pytest.raises(LastAdminProtectionError):
            svc.suspend_user(
                target_user_id=sa.user_id,
                admin_user_id="other-actor",
                admin_is_superadmin=True,
            )


# ---------------------------------------------------------------------------
# TestMigrateToSuperadmin
# ---------------------------------------------------------------------------

class TestMigrateToSuperadmin:
    def test_promotes_admin_to_superadmin(self, tmp_path):
        repo = _make_repo(tmp_path)
        admin = _admin(email="admin@example.com")
        repo.save(admin)
        svc = AuthService(repo)
        result = svc.migrate_to_superadmin("admin@example.com")
        assert result is not None
        assert result.role == UserRole.superadmin

    def test_already_superadmin_is_idempotent(self, tmp_path):
        repo = _make_repo(tmp_path)
        sa = _superadmin(email="sa@example.com")
        repo.save(sa)
        svc = AuthService(repo)
        result = svc.migrate_to_superadmin("sa@example.com")
        assert result is not None
        assert result.role == UserRole.superadmin

    def test_plain_user_not_eligible(self, tmp_path):
        repo = _make_repo(tmp_path)
        u = _user(email="user@example.com")
        repo.save(u)
        svc = AuthService(repo)
        result = svc.migrate_to_superadmin("user@example.com")
        assert result is None

    def test_missing_email_returns_none(self, tmp_path):
        repo = _make_repo(tmp_path)
        svc = AuthService(repo)
        result = svc.migrate_to_superadmin("nobody@example.com")
        assert result is None

    def test_email_case_insensitive(self, tmp_path):
        # Stored email is lowercase (as AuthService.register normalises it).
        # The migration input is normalised to lowercase, so it matches.
        repo = _make_repo(tmp_path)
        admin = _admin(email="admin@example.com")
        repo.save(admin)
        svc = AuthService(repo)
        result = svc.migrate_to_superadmin("  Admin@Example.COM  ")  # input with whitespace+case
        assert result is not None
        assert result.role == UserRole.superadmin


# ---------------------------------------------------------------------------
# TestBootstrapRegistration
# ---------------------------------------------------------------------------

class TestBootstrapRegistration:
    def test_bootstrap_email_produces_superadmin(self, tmp_path):
        repo = _make_repo(tmp_path)
        svc = AuthService(repo)
        with patch("backend.auth.service.settings") as mock_settings:
            mock_settings.admin_bootstrap_email = "owner@example.com"
            user = svc.register(
                username="owner",
                email="owner@example.com",
                password="password123",
            )
        assert user.role == UserRole.superadmin
        assert user.approved_by_user_id == "bootstrap"

    def test_bootstrap_superadmin_has_platform_access(self, tmp_path):
        repo = _make_repo(tmp_path)
        svc = AuthService(repo)
        with patch("backend.auth.service.settings") as mock_settings:
            mock_settings.admin_bootstrap_email = "owner@example.com"
            user = svc.register(
                username="owner",
                email="owner@example.com",
                password="password123",
            )
        assert user.has_platform_access is True

    def test_non_bootstrap_email_gets_user_role(self, tmp_path):
        repo = _make_repo(tmp_path)
        svc = AuthService(repo)
        with patch("backend.auth.service.settings") as mock_settings:
            mock_settings.admin_bootstrap_email = "owner@example.com"
            user = svc.register(
                username="alice",
                email="alice@example.com",
                password="password123",
            )
        assert user.role == UserRole.user
        assert user.subscription_status == SubscriptionStatus.pending

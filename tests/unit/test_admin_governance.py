"""
Phase 3P-B.1 — Admin governance safety tests.

Covers:
  - Expiry validation (future / past / None / malformed)
  - Approval stores expiry correctly
  - Reactivation validates expiry
  - Expiry update (admin override path)
  - Admin self-suspension prevention
  - Last-admin protection
  - Normal user lifecycle remains enforced
  - Admin bypass remains intact after governance changes
  - Audit events emitted for denial scenarios
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import call, patch

import pytest

from backend.api.services.admin_service import (
    AdminService,
    AdminSelfSuspensionError,
    InvalidExpiryError,
    LastAdminProtectionError,
    UserNotFoundError,
    validate_future_expiry,
)
from backend.auth.models import User, UserRole, SubscriptionStatus
from backend.auth.repository import UserRepository
from backend.core.audit import AuditEventKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FUTURE_EXPIRY = "2040-01-01T00:00:00+00:00"
PAST_EXPIRY   = "2020-01-01T00:00:00+00:00"
FAKE_HASH     = "$2b$12$fakehashvalue000000000000000000000000000000000000000000"


def _make_user(**kwargs) -> User:
    defaults: dict = dict(
        user_id="u-1",
        username="alice",
        email="alice@test.com",
        password_hash=FAKE_HASH,
        created_at="2025-01-01T00:00:00Z",
        role=UserRole.user,
        subscription_status=SubscriptionStatus.pending,
    )
    defaults.update(kwargs)
    return User(**defaults)


def _make_admin(**kwargs) -> User:
    defaults: dict = dict(
        user_id="admin-1",
        username="admin",
        email="admin@test.com",
        password_hash=FAKE_HASH,
        created_at="2025-01-01T00:00:00Z",
        role=UserRole.admin,
        subscription_status=SubscriptionStatus.pending,
    )
    defaults.update(kwargs)
    return User(**defaults)


def _setup(tmp_path: Path, users: list[User]) -> AdminService:
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps([u.to_dict() for u in users]),
        encoding="utf-8",
    )
    return AdminService(UserRepository(path))


# ---------------------------------------------------------------------------
# validate_future_expiry — standalone helper
# ---------------------------------------------------------------------------

class TestValidateFutureExpiry:
    def test_none_is_allowed(self):
        validate_future_expiry(None)  # must not raise

    def test_future_date_is_allowed(self):
        validate_future_expiry(FUTURE_EXPIRY)  # must not raise

    def test_past_date_raises(self):
        with pytest.raises(InvalidExpiryError):
            validate_future_expiry(PAST_EXPIRY)

    def test_malformed_string_raises(self):
        with pytest.raises(InvalidExpiryError):
            validate_future_expiry("not-a-date")

    def test_naive_datetime_treated_as_utc_and_validated(self):
        # A naive past datetime should still be rejected
        with pytest.raises(InvalidExpiryError):
            validate_future_expiry("2020-06-01T12:00:00")

    def test_naive_future_datetime_passes(self):
        validate_future_expiry("2040-06-01T12:00:00")  # treated as UTC, in future


# ---------------------------------------------------------------------------
# Approval with expiry
# ---------------------------------------------------------------------------

class TestApprovalExpiry:
    def test_approve_with_future_expiry_succeeds(self, tmp_path):
        admin = _make_admin()
        user  = _make_user()
        svc   = _setup(tmp_path, [admin, user])

        updated = svc.approve_user(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=FUTURE_EXPIRY,
        )

        assert updated.subscription_status == SubscriptionStatus.active
        assert updated.subscription_expires_at == FUTURE_EXPIRY

    def test_approve_without_expiry_succeeds(self, tmp_path):
        admin = _make_admin()
        user  = _make_user()
        svc   = _setup(tmp_path, [admin, user])

        updated = svc.approve_user(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=None,
        )

        assert updated.subscription_status == SubscriptionStatus.active
        assert updated.subscription_expires_at is None

    def test_approve_with_past_expiry_raises(self, tmp_path):
        admin = _make_admin()
        user  = _make_user()
        svc   = _setup(tmp_path, [admin, user])

        with pytest.raises(InvalidExpiryError):
            svc.approve_user(
                target_user_id=user.user_id,
                admin_user_id=admin.user_id,
                subscription_expires_at=PAST_EXPIRY,
            )

    def test_approve_stores_expiry_in_repo(self, tmp_path):
        admin = _make_admin()
        user  = _make_user()
        svc   = _setup(tmp_path, [admin, user])

        svc.approve_user(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=FUTURE_EXPIRY,
        )

        persisted = svc.get_user(user.user_id)
        assert persisted.subscription_expires_at == FUTURE_EXPIRY


# ---------------------------------------------------------------------------
# Reactivation with expiry
# ---------------------------------------------------------------------------

class TestReactivationExpiry:
    def test_reactivate_with_future_expiry_succeeds(self, tmp_path):
        admin      = _make_admin()
        suspended  = _make_user(subscription_status=SubscriptionStatus.suspended)
        svc        = _setup(tmp_path, [admin, suspended])

        updated = svc.reactivate_user(
            target_user_id=suspended.user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=FUTURE_EXPIRY,
        )

        assert updated.subscription_status == SubscriptionStatus.active
        assert updated.subscription_expires_at == FUTURE_EXPIRY

    def test_reactivate_with_past_expiry_raises(self, tmp_path):
        admin     = _make_admin()
        suspended = _make_user(subscription_status=SubscriptionStatus.suspended)
        svc       = _setup(tmp_path, [admin, suspended])

        with pytest.raises(InvalidExpiryError):
            svc.reactivate_user(
                target_user_id=suspended.user_id,
                admin_user_id=admin.user_id,
                subscription_expires_at=PAST_EXPIRY,
            )


# ---------------------------------------------------------------------------
# Expiry update (admin override path)
# ---------------------------------------------------------------------------

class TestUpdateExpiry:
    def test_update_expiry_sets_new_date(self, tmp_path):
        admin  = _make_admin()
        user   = _make_user(subscription_status=SubscriptionStatus.active)
        svc    = _setup(tmp_path, [admin, user])

        new_expiry = "2035-06-01T00:00:00+00:00"
        updated = svc.update_expiry(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=new_expiry,
        )

        assert updated.subscription_expires_at == new_expiry

    def test_update_expiry_persists_to_repo(self, tmp_path):
        admin  = _make_admin()
        user   = _make_user(subscription_status=SubscriptionStatus.active)
        svc    = _setup(tmp_path, [admin, user])

        new_expiry = "2035-06-01T00:00:00+00:00"
        svc.update_expiry(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=new_expiry,
        )
        persisted = svc.get_user(user.user_id)
        assert persisted.subscription_expires_at == new_expiry

    def test_update_expiry_with_past_date_raises(self, tmp_path):
        admin  = _make_admin()
        user   = _make_user(subscription_status=SubscriptionStatus.active)
        svc    = _setup(tmp_path, [admin, user])

        with pytest.raises(InvalidExpiryError):
            svc.update_expiry(
                target_user_id=user.user_id,
                admin_user_id=admin.user_id,
                subscription_expires_at=PAST_EXPIRY,
            )

    def test_update_expiry_does_not_change_subscription_status(self, tmp_path):
        admin  = _make_admin()
        user   = _make_user(subscription_status=SubscriptionStatus.active)
        svc    = _setup(tmp_path, [admin, user])

        updated = svc.update_expiry(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=FUTURE_EXPIRY,
        )
        assert updated.subscription_status == SubscriptionStatus.active


# ---------------------------------------------------------------------------
# Admin self-suspension prevention
# ---------------------------------------------------------------------------

class TestAdminSelfSuspension:
    def test_admin_cannot_suspend_self(self, tmp_path):
        admin = _make_admin()
        svc   = _setup(tmp_path, [admin])

        with pytest.raises(AdminSelfSuspensionError):
            svc.suspend_user(
                target_user_id=admin.user_id,
                admin_user_id=admin.user_id,
            )

    def test_self_suspension_denied_audit_event_emitted(self, tmp_path):
        admin = _make_admin()
        svc   = _setup(tmp_path, [admin])

        with patch("backend.api.services.admin_service.emit_audit_event") as mock_audit:
            with pytest.raises(AdminSelfSuspensionError):
                svc.suspend_user(
                    target_user_id=admin.user_id,
                    admin_user_id=admin.user_id,
                )

        emitted_kinds = [c.args[0].event_kind for c in mock_audit.call_args_list]
        assert AuditEventKind.ADMIN_SELF_SUSPENSION_DENIED in emitted_kinds

    def test_self_suspension_does_not_modify_user(self, tmp_path):
        admin = _make_admin()
        svc   = _setup(tmp_path, [admin])

        with pytest.raises(AdminSelfSuspensionError):
            svc.suspend_user(
                target_user_id=admin.user_id,
                admin_user_id=admin.user_id,
            )

        # Admin must remain unchanged in the repository
        persisted = svc.get_user(admin.user_id)
        assert persisted.subscription_status == admin.subscription_status


# ---------------------------------------------------------------------------
# Last-admin protection
# ---------------------------------------------------------------------------

class TestLastAdminProtection:
    def test_cannot_suspend_sole_admin(self, tmp_path):
        admin      = _make_admin()
        other_user = _make_user()
        svc        = _setup(tmp_path, [admin, other_user])

        # Different actor (not self) tries to suspend the sole admin
        with pytest.raises(LastAdminProtectionError):
            svc.suspend_user(
                target_user_id=admin.user_id,
                admin_user_id="other-actor-id",
            )

    def test_last_admin_denied_audit_event_emitted(self, tmp_path):
        admin = _make_admin()
        svc   = _setup(tmp_path, [admin])

        with patch("backend.api.services.admin_service.emit_audit_event") as mock_audit:
            with pytest.raises(LastAdminProtectionError):
                svc.suspend_user(
                    target_user_id=admin.user_id,
                    admin_user_id="other-actor-id",
                )

        emitted_kinds = [c.args[0].event_kind for c in mock_audit.call_args_list]
        assert AuditEventKind.LAST_ADMIN_SUSPENSION_DENIED in emitted_kinds

    def test_can_suspend_non_last_admin(self, tmp_path):
        admin_a = _make_admin(user_id="admin-a", username="admin_a", email="a@test.com")
        admin_b = _make_admin(
            user_id="admin-b", username="admin_b", email="b@test.com",
            subscription_status=SubscriptionStatus.active,
        )
        svc = _setup(tmp_path, [admin_a, admin_b])

        # admin-a suspends admin-b — two admins exist so protection does not fire
        updated = svc.suspend_user(
            target_user_id="admin-b",
            admin_user_id="admin-a",
        )
        assert updated.subscription_status == SubscriptionStatus.suspended

    def test_last_admin_protection_does_not_modify_user(self, tmp_path):
        admin      = _make_admin()
        other_user = _make_user()
        svc        = _setup(tmp_path, [admin, other_user])

        with pytest.raises(LastAdminProtectionError):
            svc.suspend_user(
                target_user_id=admin.user_id,
                admin_user_id="other-actor-id",
            )

        persisted = svc.get_user(admin.user_id)
        assert persisted.subscription_status == admin.subscription_status


# ---------------------------------------------------------------------------
# Normal user lifecycle remains enforced
# ---------------------------------------------------------------------------

class TestNormalUserLifecycleIntact:
    def test_pending_user_can_be_approved(self, tmp_path):
        admin = _make_admin()
        user  = _make_user()
        svc   = _setup(tmp_path, [admin, user])

        updated = svc.approve_user(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
        )
        assert updated.subscription_status == SubscriptionStatus.active

    def test_active_user_can_be_suspended(self, tmp_path):
        admin = _make_admin()
        user  = _make_user(subscription_status=SubscriptionStatus.active)
        svc   = _setup(tmp_path, [admin, user])

        updated = svc.suspend_user(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
        )
        assert updated.subscription_status == SubscriptionStatus.suspended

    def test_suspended_user_can_be_reactivated(self, tmp_path):
        admin = _make_admin()
        user  = _make_user(subscription_status=SubscriptionStatus.suspended)
        svc   = _setup(tmp_path, [admin, user])

        updated = svc.reactivate_user(
            target_user_id=user.user_id,
            admin_user_id=admin.user_id,
        )
        assert updated.subscription_status == SubscriptionStatus.active


# ---------------------------------------------------------------------------
# Admin platform access bypass remains intact
# ---------------------------------------------------------------------------

class TestAdminBypassIntact:
    def test_admin_has_platform_access_regardless_of_subscription_status(self):
        for status in [
            SubscriptionStatus.pending,
            SubscriptionStatus.active,
            SubscriptionStatus.expired,
            SubscriptionStatus.suspended,
        ]:
            admin = _make_admin(subscription_status=status)
            assert admin.has_platform_access is True, f"Failed for status={status}"

    def test_regular_user_requires_active_subscription(self):
        active    = _make_user(subscription_status=SubscriptionStatus.active)
        pending   = _make_user(subscription_status=SubscriptionStatus.pending)
        expired   = _make_user(subscription_status=SubscriptionStatus.expired)
        suspended = _make_user(subscription_status=SubscriptionStatus.suspended)

        assert active.has_platform_access is True
        assert pending.has_platform_access is False
        assert expired.has_platform_access is False
        assert suspended.has_platform_access is False

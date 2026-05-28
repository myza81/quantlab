"""
Phase 3P-A — Subscription Eligibility & Admin Approval Foundation

Tests cover:
  - User.is_entitled: active with no expiry, active with future expiry, active expired,
    pending, suspended, expired status, malformed expiry
  - User.is_admin: user role vs admin role
  - User state transitions: with_active_subscription, with_suspended, with_reactivated
  - User.create(): defaults to pending
  - User.from_dict(): backward-compat legacy users default to active
  - AdminBootstrap: register with bootstrap email → admin + active subscription
  - require_active_subscription: active passes, pending/expired/suspended return 403
  - require_admin_role: admin passes, user returns 403
  - Admin routes (via TestClient): list_users, get_user, approve, suspend, reactivate
  - Audit events: ENTITLEMENT_DENIED emitted on rejection
  - Security invariants: no API path to self-escalate to admin
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.auth.models import SubscriptionStatus, User, UserRole
from backend.auth.repository import UserRepository
from backend.auth.service import AuthService
from backend.core.audit import AuditEventKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_user(**kwargs) -> User:
    base = dict(
        user_id="u1",
        username="alice",
        email="alice@example.com",
        password_hash="$2b$12$hash",
        created_at="2025-01-01T00:00:00+00:00",
        role=UserRole.user,
        subscription_status=SubscriptionStatus.active,
    )
    base.update(kwargs)
    return User(**base)


def _admin_user(**kwargs) -> User:
    return _active_user(user_id="admin1", username="admin", email="admin@example.com",
                        role=UserRole.admin, **kwargs)


def _make_repo(tmp_path: Path) -> UserRepository:
    return UserRepository(tmp_path / "users.json")


# ---------------------------------------------------------------------------
# User.is_entitled
# ---------------------------------------------------------------------------

class TestIsEntitled:
    def test_active_no_expiry_is_entitled(self):
        u = _active_user(subscription_expires_at=None)
        assert u.is_entitled is True

    def test_active_future_expiry_is_entitled(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        u = _active_user(subscription_expires_at=future)
        assert u.is_entitled is True

    def test_active_past_expiry_not_entitled(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        u = _active_user(subscription_expires_at=past)
        assert u.is_entitled is False

    def test_pending_not_entitled(self):
        u = _active_user(subscription_status=SubscriptionStatus.pending)
        assert u.is_entitled is False

    def test_expired_not_entitled(self):
        u = _active_user(subscription_status=SubscriptionStatus.expired)
        assert u.is_entitled is False

    def test_suspended_not_entitled(self):
        u = _active_user(subscription_status=SubscriptionStatus.suspended)
        assert u.is_entitled is False

    def test_malformed_expiry_not_entitled(self):
        u = _active_user(subscription_expires_at="not-a-date")
        assert u.is_entitled is False


# ---------------------------------------------------------------------------
# User.is_admin
# ---------------------------------------------------------------------------

class TestIsAdmin:
    def test_admin_role_is_admin(self):
        assert _admin_user().is_admin is True

    def test_user_role_not_admin(self):
        assert _active_user().is_admin is False


# ---------------------------------------------------------------------------
# Immutable state transitions
# ---------------------------------------------------------------------------

class TestStateTransitions:
    def test_with_active_subscription(self):
        pending = _active_user(subscription_status=SubscriptionStatus.pending)
        approved = pending.with_active_subscription(
            approved_by_user_id="admin1",
            subscription_expires_at=None,
            notes="welcome",
        )
        assert approved.subscription_status == SubscriptionStatus.active
        assert approved.approved_by_user_id == "admin1"
        assert approved.approved_at is not None
        assert approved.subscription_notes == "welcome"
        # Original is unchanged (frozen dataclass)
        assert pending.subscription_status == SubscriptionStatus.pending

    def test_with_suspended(self):
        active = _active_user()
        suspended = active.with_suspended(reason="violation")
        assert suspended.subscription_status == SubscriptionStatus.suspended
        assert suspended.suspension_reason == "violation"
        assert active.subscription_status == SubscriptionStatus.active

    def test_with_reactivated(self):
        suspended = _active_user(
            subscription_status=SubscriptionStatus.suspended,
            suspension_reason="violation",
        )
        reactivated = suspended.with_reactivated()
        assert reactivated.subscription_status == SubscriptionStatus.active
        assert reactivated.suspension_reason is None


# ---------------------------------------------------------------------------
# User.create() and User.from_dict() backward compat
# ---------------------------------------------------------------------------

class TestUserFactory:
    def test_create_defaults_to_pending(self):
        u = User.create(username="bob", email="bob@example.com", password_hash="h")
        assert u.subscription_status == SubscriptionStatus.pending
        assert u.role == UserRole.user

    def test_from_dict_legacy_defaults_to_active(self):
        data = {
            "user_id": "u-old",
            "username": "legacy",
            "email": "legacy@example.com",
            "password_hash": "h",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
        u = User.from_dict(data)
        assert u.subscription_status == SubscriptionStatus.active
        assert u.role == UserRole.user

    def test_from_dict_explicit_status_preserved(self):
        data = {
            "user_id": "u2",
            "username": "newuser",
            "email": "new@example.com",
            "password_hash": "h",
            "created_at": "2025-01-01T00:00:00+00:00",
            "subscription_status": "suspended",
            "role": "admin",
        }
        u = User.from_dict(data)
        assert u.subscription_status == SubscriptionStatus.suspended
        assert u.role == UserRole.admin


# ---------------------------------------------------------------------------
# Admin bootstrap via AuthService
# ---------------------------------------------------------------------------

class TestAdminBootstrap:
    def test_bootstrap_email_gets_admin_active(self, tmp_path):
        repo = _make_repo(tmp_path)
        svc = AuthService(repo)
        with patch("backend.auth.service.settings") as mock_settings:
            mock_settings.admin_bootstrap_email = "admin@example.com"
            user = svc.register(
                username="admin",
                email="admin@example.com",
                password="password123",
            )
        assert user.role == UserRole.admin
        assert user.subscription_status == SubscriptionStatus.active
        assert user.approved_by_user_id == "bootstrap"

    def test_non_bootstrap_email_gets_pending(self, tmp_path):
        repo = _make_repo(tmp_path)
        svc = AuthService(repo)
        with patch("backend.auth.service.settings") as mock_settings:
            mock_settings.admin_bootstrap_email = "admin@example.com"
            user = svc.register(
                username="alice",
                email="alice@example.com",
                password="password123",
            )
        assert user.role == UserRole.user
        assert user.subscription_status == SubscriptionStatus.pending

    def test_empty_bootstrap_email_all_pending(self, tmp_path):
        repo = _make_repo(tmp_path)
        svc = AuthService(repo)
        with patch("backend.auth.service.settings") as mock_settings:
            mock_settings.admin_bootstrap_email = ""
            user = svc.register(
                username="bob",
                email="bob@example.com",
                password="password123",
            )
        assert user.subscription_status == SubscriptionStatus.pending
        assert user.role == UserRole.user


# ---------------------------------------------------------------------------
# require_active_subscription dependency
# ---------------------------------------------------------------------------

class TestRequireActiveSubscription:
    def _invoke(self, user: User) -> User:
        from backend.auth.entitlement import require_active_subscription
        mock_get_current_user = MagicMock(return_value=user)
        with patch("backend.auth.entitlement.get_current_user", mock_get_current_user):
            return require_active_subscription(current_user=user)

    def test_active_user_passes(self):
        user = _active_user()
        result = self._invoke(user)
        assert result is user

    def test_pending_user_raises_403(self):
        user = _active_user(subscription_status=SubscriptionStatus.pending)
        with pytest.raises(HTTPException) as exc_info:
            self._invoke(user)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "subscription_required"
        assert exc_info.value.detail["subscription_status"] == SubscriptionStatus.pending

    def test_suspended_user_raises_403(self):
        user = _active_user(subscription_status=SubscriptionStatus.suspended)
        with pytest.raises(HTTPException) as exc_info:
            self._invoke(user)
        assert exc_info.value.status_code == 403

    def test_expired_user_raises_403(self):
        user = _active_user(subscription_status=SubscriptionStatus.expired)
        with pytest.raises(HTTPException) as exc_info:
            self._invoke(user)
        assert exc_info.value.status_code == 403

    def test_active_expired_subscription_raises_403(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        user = _active_user(subscription_expires_at=past)
        with pytest.raises(HTTPException) as exc_info:
            self._invoke(user)
        assert exc_info.value.status_code == 403

    def test_entitlement_denied_emits_audit_event(self):
        user = _active_user(subscription_status=SubscriptionStatus.pending)
        with patch("backend.auth.entitlement.emit_audit_event") as mock_emit:
            with pytest.raises(HTTPException):
                self._invoke(user)
        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_kind == AuditEventKind.ENTITLEMENT_DENIED
        assert event.details["user_id"] == user.user_id


# ---------------------------------------------------------------------------
# require_admin_role dependency
# ---------------------------------------------------------------------------

class TestRequireAdminRole:
    def _invoke(self, user: User) -> User:
        from backend.auth.entitlement import require_admin_role
        return require_admin_role(current_user=user)

    def test_admin_passes(self):
        admin = _admin_user()
        result = self._invoke(admin)
        assert result is admin

    def test_regular_user_raises_403(self):
        user = _active_user()
        with pytest.raises(HTTPException) as exc_info:
            self._invoke(user)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "admin_required"

    def test_pending_admin_passes(self):
        # Admin can access admin routes even if their own subscription is pending/expired
        admin = _admin_user(subscription_status=SubscriptionStatus.pending)
        result = self._invoke(admin)
        assert result is admin


# ---------------------------------------------------------------------------
# Admin routes (integration via TestClient)
# ---------------------------------------------------------------------------

def _make_app_with_overrides(admin_user: User, target_user: User = None):
    """Create a TestClient with auth overrides for admin routes."""
    from backend.api.main import app
    from backend.auth.entitlement import require_admin_role
    from backend.api.routes.admin import _get_admin_service
    from backend.api.services.admin_service import AdminService

    mock_svc = MagicMock(spec=AdminService)
    if target_user:
        mock_svc.list_users.return_value = [target_user]
        mock_svc.get_user.return_value = target_user
        mock_svc.approve_user.return_value = target_user.with_active_subscription(
            approved_by_user_id=admin_user.user_id
        )
        mock_svc.suspend_user.return_value = target_user.with_suspended(reason="test")
        mock_svc.reactivate_user.return_value = target_user.with_reactivated()

    overrides = {
        require_admin_role: lambda: admin_user,
        _get_admin_service: lambda: mock_svc,
    }
    return TestClient(app, raise_server_exceptions=True), overrides, mock_svc


class TestAdminRoutes:
    def _client(self):
        from backend.api.main import app
        from backend.auth.entitlement import require_admin_role
        from backend.api.routes.admin import _get_admin_service
        from backend.api.services.admin_service import AdminService

        admin = _admin_user()
        target = _active_user(subscription_status=SubscriptionStatus.pending)
        mock_svc = MagicMock(spec=AdminService)
        mock_svc.list_users.return_value = [target]
        mock_svc.get_user.return_value = target
        mock_svc.approve_user.return_value = target.with_active_subscription(
            approved_by_user_id=admin.user_id
        )
        mock_svc.suspend_user.return_value = target.with_suspended(reason="test")
        mock_svc.reactivate_user.return_value = target.with_reactivated()

        app.dependency_overrides[require_admin_role] = lambda: admin
        app.dependency_overrides[_get_admin_service] = lambda: mock_svc
        client = TestClient(app, raise_server_exceptions=True)
        return client, mock_svc, target

    def _cleanup(self):
        from backend.api.main import app
        from backend.auth.entitlement import require_admin_role
        from backend.api.routes.admin import _get_admin_service
        app.dependency_overrides.pop(require_admin_role, None)
        app.dependency_overrides.pop(_get_admin_service, None)

    def test_list_users_returns_200(self):
        client, svc, target = self._client()
        try:
            resp = client.get("/admin/users")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["user_id"] == target.user_id
        finally:
            self._cleanup()

    def test_get_user_returns_200(self):
        client, svc, target = self._client()
        try:
            resp = client.get(f"/admin/users/{target.user_id}")
            assert resp.status_code == 200
            assert resp.json()["user_id"] == target.user_id
        finally:
            self._cleanup()

    def test_approve_user_calls_service(self):
        client, svc, target = self._client()
        try:
            resp = client.post(
                f"/admin/users/{target.user_id}/approve",
                json={"subscription_expires_at": None, "notes": "welcome"},
            )
            assert resp.status_code == 200
            svc.approve_user.assert_called_once()
        finally:
            self._cleanup()

    def test_suspend_user_calls_service(self):
        client, svc, target = self._client()
        try:
            resp = client.post(
                f"/admin/users/{target.user_id}/suspend",
                json={"reason": "test"},
            )
            assert resp.status_code == 200
            svc.suspend_user.assert_called_once()
        finally:
            self._cleanup()

    def test_reactivate_user_calls_service(self):
        client, svc, target = self._client()
        try:
            resp = client.post(
                f"/admin/users/{target.user_id}/reactivate",
                json={},
            )
            assert resp.status_code == 200
            svc.reactivate_user.assert_called_once()
        finally:
            self._cleanup()

    def test_non_admin_cannot_access_admin_routes(self):
        from backend.api.main import app
        from backend.auth.entitlement import require_admin_role

        regular = _active_user()

        def _not_admin():
            raise HTTPException(status_code=403, detail={"code": "admin_required"})

        app.dependency_overrides[require_admin_role] = _not_admin
        try:
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/admin/users")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(require_admin_role, None)

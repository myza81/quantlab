"""
Phase 3P-C — Lazy Subscription Expiry Enforcement

Tests cover:
  - evaluate_subscription_expiry():
    - active + no expiry → no transition (still valid)
    - active + future expiry → no transition (still within window)
    - active + past expiry → auto-transitions to expired, repo updated, SUBSCRIPTION_EXPIRED emitted
    - expired status → idempotent, no second write
    - suspended status → no transition
    - pending status → no transition
    - admin + past expiry → never auto-expired (role-based bypass)
    - malformed expiry string → no transition (deferred to admin)
    - naive datetime → treated as UTC (auto-expires correctly)
  - User.with_expired():
    - transitions status to expired, preserves all other fields
  - require_active_subscription integration:
    - active user with past expiry → auto-transitions + 403 returned with subscription_status=expired
    - SUBSCRIPTION_EXPIRED emitted before ENTITLEMENT_DENIED on auto-expiry
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import HTTPException

from backend.auth.expiry import evaluate_subscription_expiry
from backend.auth.models import SubscriptionStatus, User, UserRole
from backend.auth.repository import UserRepository
from backend.core.audit import AuditEventKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(**kwargs) -> User:
    base = dict(
        user_id="u-1",
        username="alice",
        email="alice@example.com",
        password_hash="$2b$12$hash",
        created_at="2025-01-01T00:00:00+00:00",
        role=UserRole.user,
        subscription_status=SubscriptionStatus.active,
        subscription_expires_at=None,
    )
    base.update(kwargs)
    return User(**base)


def _admin(**kwargs) -> User:
    return _user(
        user_id="admin-1",
        username="admin",
        email="admin@example.com",
        role=UserRole.admin,
        **kwargs,
    )


def _future(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _make_repo(tmp_path: Path, users: list[User]) -> UserRepository:
    path = tmp_path / "users.json"
    path.write_text(json.dumps([u.to_dict() for u in users]), encoding="utf-8")
    return UserRepository(path)


# ---------------------------------------------------------------------------
# User.with_expired()
# ---------------------------------------------------------------------------

class TestWithExpired:
    def test_transitions_status_to_expired(self):
        u = _user(subscription_status=SubscriptionStatus.active)
        expired = u.with_expired()
        assert expired.subscription_status == SubscriptionStatus.expired

    def test_preserves_all_other_fields(self):
        u = _user(
            subscription_status=SubscriptionStatus.active,
            subscription_expires_at=_past(),
            approved_by_user_id="admin-1",
            subscription_notes="welcome",
        )
        expired = u.with_expired()
        assert expired.user_id == u.user_id
        assert expired.username == u.username
        assert expired.email == u.email
        assert expired.subscription_expires_at == u.subscription_expires_at
        assert expired.approved_by_user_id == u.approved_by_user_id
        assert expired.subscription_notes == u.subscription_notes

    def test_original_is_unchanged(self):
        u = _user(subscription_status=SubscriptionStatus.active)
        _ = u.with_expired()
        assert u.subscription_status == SubscriptionStatus.active


# ---------------------------------------------------------------------------
# evaluate_subscription_expiry — no-op cases
# ---------------------------------------------------------------------------

class TestEvaluateNoOp:
    def test_active_no_expiry_returns_unchanged(self, tmp_path):
        u = _user(subscription_expires_at=None)
        repo = _make_repo(tmp_path, [u])
        result = evaluate_subscription_expiry(u, repo)
        assert result is u
        assert repo.get_by_id(u.user_id).subscription_status == SubscriptionStatus.active

    def test_active_future_expiry_returns_unchanged(self, tmp_path):
        u = _user(subscription_expires_at=_future(30))
        repo = _make_repo(tmp_path, [u])
        result = evaluate_subscription_expiry(u, repo)
        assert result is u
        assert repo.get_by_id(u.user_id).subscription_status == SubscriptionStatus.active

    def test_already_expired_is_idempotent(self, tmp_path):
        u = _user(
            subscription_status=SubscriptionStatus.expired,
            subscription_expires_at=_past(),
        )
        repo = _make_repo(tmp_path, [u])
        with patch("backend.auth.expiry.emit_audit_event") as mock_emit:
            result = evaluate_subscription_expiry(u, repo)
        assert result is u
        mock_emit.assert_not_called()

    def test_suspended_not_evaluated(self, tmp_path):
        u = _user(
            subscription_status=SubscriptionStatus.suspended,
            subscription_expires_at=_past(),
        )
        repo = _make_repo(tmp_path, [u])
        with patch("backend.auth.expiry.emit_audit_event") as mock_emit:
            result = evaluate_subscription_expiry(u, repo)
        assert result is u
        mock_emit.assert_not_called()

    def test_pending_not_evaluated(self, tmp_path):
        u = _user(
            subscription_status=SubscriptionStatus.pending,
            subscription_expires_at=_past(),
        )
        repo = _make_repo(tmp_path, [u])
        with patch("backend.auth.expiry.emit_audit_event") as mock_emit:
            result = evaluate_subscription_expiry(u, repo)
        assert result is u
        mock_emit.assert_not_called()

    def test_malformed_expiry_returns_unchanged(self, tmp_path):
        u = _user(subscription_expires_at="not-a-date")
        repo = _make_repo(tmp_path, [u])
        with patch("backend.auth.expiry.emit_audit_event") as mock_emit:
            result = evaluate_subscription_expiry(u, repo)
        assert result is u
        mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# evaluate_subscription_expiry — auto-expiry
# ---------------------------------------------------------------------------

class TestEvaluateAutoExpiry:
    def test_active_past_expiry_transitions_to_expired(self, tmp_path):
        u = _user(subscription_expires_at=_past(1))
        repo = _make_repo(tmp_path, [u])
        result = evaluate_subscription_expiry(u, repo)
        assert result.subscription_status == SubscriptionStatus.expired

    def test_auto_expiry_persists_to_repo(self, tmp_path):
        u = _user(subscription_expires_at=_past(1))
        repo = _make_repo(tmp_path, [u])
        evaluate_subscription_expiry(u, repo)
        persisted = repo.get_by_id(u.user_id)
        assert persisted.subscription_status == SubscriptionStatus.expired

    def test_auto_expiry_emits_subscription_expired_event(self, tmp_path):
        u = _user(subscription_expires_at=_past(1))
        repo = _make_repo(tmp_path, [u])
        with patch("backend.auth.expiry.emit_audit_event") as mock_emit:
            evaluate_subscription_expiry(u, repo)
        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_kind == AuditEventKind.SUBSCRIPTION_EXPIRED
        assert event.details["user_id"] == u.user_id

    def test_auto_expiry_not_repeated_on_second_call(self, tmp_path):
        u = _user(subscription_expires_at=_past(1))
        repo = _make_repo(tmp_path, [u])
        with patch("backend.auth.expiry.emit_audit_event") as mock_emit:
            # First call: transitions + emits
            result1 = evaluate_subscription_expiry(u, repo)
            # Second call: already expired → no-op
            result2 = evaluate_subscription_expiry(result1, repo)
        assert mock_emit.call_count == 1

    def test_naive_datetime_treated_as_utc(self, tmp_path):
        # Naive ISO datetime (no tzinfo) in the past should still trigger expiry
        naive_past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        u = _user(subscription_expires_at=naive_past)
        repo = _make_repo(tmp_path, [u])
        result = evaluate_subscription_expiry(u, repo)
        assert result.subscription_status == SubscriptionStatus.expired


# ---------------------------------------------------------------------------
# evaluate_subscription_expiry — admin bypass
# ---------------------------------------------------------------------------

class TestEvaluateAdminBypass:
    def test_admin_with_past_expiry_never_auto_expired(self, tmp_path):
        a = _admin(
            subscription_status=SubscriptionStatus.active,
            subscription_expires_at=_past(365),
        )
        repo = _make_repo(tmp_path, [a])
        with patch("backend.auth.expiry.emit_audit_event") as mock_emit:
            result = evaluate_subscription_expiry(a, repo)
        assert result is a
        assert result.subscription_status == SubscriptionStatus.active
        mock_emit.assert_not_called()

    def test_admin_with_expired_status_unchanged(self, tmp_path):
        a = _admin(
            subscription_status=SubscriptionStatus.expired,
            subscription_expires_at=_past(365),
        )
        repo = _make_repo(tmp_path, [a])
        with patch("backend.auth.expiry.emit_audit_event") as mock_emit:
            result = evaluate_subscription_expiry(a, repo)
        assert result is a
        mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# require_active_subscription integration (lazy expiry in request path)
# ---------------------------------------------------------------------------

class TestRequireActiveSubscriptionLazyExpiry:
    def _invoke(self, user: User, repo) -> User:
        from backend.auth.entitlement import require_active_subscription
        return require_active_subscription(current_user=user, repository=repo)

    def test_active_past_expiry_returns_403_with_expired_status(self, tmp_path):
        u = _user(subscription_expires_at=_past(1))
        repo = _make_repo(tmp_path, [u])
        with pytest.raises(HTTPException) as exc_info:
            self._invoke(u, repo)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "subscription_required"
        assert exc_info.value.detail["subscription_status"] == SubscriptionStatus.expired

    def test_auto_expiry_persists_before_denial(self, tmp_path):
        u = _user(subscription_expires_at=_past(1))
        repo = _make_repo(tmp_path, [u])
        with pytest.raises(HTTPException):
            self._invoke(u, repo)
        persisted = repo.get_by_id(u.user_id)
        assert persisted.subscription_status == SubscriptionStatus.expired

    def test_subscription_expired_emitted_before_entitlement_denied(self, tmp_path):
        u = _user(subscription_expires_at=_past(1))
        repo = _make_repo(tmp_path, [u])
        emitted_kinds = []
        def capture(event):
            emitted_kinds.append(event.event_kind)
        with patch("backend.auth.expiry.emit_audit_event", side_effect=capture):
            with patch("backend.auth.entitlement.emit_audit_event", side_effect=capture):
                with pytest.raises(HTTPException):
                    self._invoke(u, repo)
        assert AuditEventKind.SUBSCRIPTION_EXPIRED in emitted_kinds
        assert AuditEventKind.ENTITLEMENT_DENIED in emitted_kinds
        assert emitted_kinds.index(AuditEventKind.SUBSCRIPTION_EXPIRED) < \
               emitted_kinds.index(AuditEventKind.ENTITLEMENT_DENIED)

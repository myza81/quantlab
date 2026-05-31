"""
Phase 3S-B — Evaluation Route Authentication Tests.

Verifies that all 5 compute-heavy endpoints now require require_active_subscription:
    POST /semantics/evaluate-history
    POST /semantics/evaluate-scalar
    POST /semantics/extract-signal-events
    POST /semantics/extract-trade-intents
    POST /backtests/simulate

Scenarios:
    1. No auth → 401
    2. Active user → allowed through (200 or 422 — not 401/403)
    3. Expired subscription → 403
    4. Suspended subscription → 403
    5. Admin always passes
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.auth.dependencies import get_current_user, get_user_repository
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User


def _user(
    *,
    user_id: str = "test-user",
    subscription_status: str = "active",
    role: str = "user",
) -> User:
    return User(
        user_id=user_id,
        username="testuser",
        email="test@example.com",
        password_hash="x",
        created_at="2024-01-01T00:00:00Z",
        role=role,
        subscription_status=subscription_status,
    )


_ACTIVE_USER    = _user(subscription_status="active")
_EXPIRED_USER   = _user(subscription_status="expired")
_SUSPENDED_USER = _user(subscription_status="suspended")
_ADMIN_USER     = _user(subscription_status="active", role="admin")

_CLIENT_NO_AUTH = TestClient(app)

_MINIMAL_SEMANTICS = {
    "entry_rules": [{"rule_id": "r1", "lhs": "price.close", "operator": ">", "rhs": 0.0}],
    "exit_rules":  [],
}
_MINIMAL_BARS = [{"bar_index": 0, "price_fields": {"close": 100.0}, "tool_outputs": {}}]
_SCALAR_CONTEXT = {"price.close": 100.0}

_SIMULATE_BODY = {
    "intent_batch": {
        "intents": [],
        "summary": {"total_intents": 0, "open_long_count": 0, "close_long_count": 0,
                    "diagnostic_count": 0, "ignored_count": 0},
        "ignored_event_ids": [],
    },
    "price_bars": [],
    "config": {"initial_cash": 10000.0, "fixed_quantity": 1.0},
}

_SIGNAL_EVENT_BATCH = {
    "events": [],
    "summary": {"total_events": 0, "entry_count": 0, "exit_count": 0, "diagnostic_count": 0},
    "ignored_bar_indices": [],
}


def _override(user: User | None):
    if user is None:
        app.dependency_overrides.pop(require_active_subscription, None)
    else:
        app.dependency_overrides[require_active_subscription] = lambda: user


# ---------------------------------------------------------------------------
# Parametrized endpoint/body table
# ---------------------------------------------------------------------------

_ENDPOINTS = [
    ("POST", "/semantics/evaluate-history",
     {"semantics": _MINIMAL_SEMANTICS, "bars": _MINIMAL_BARS}),
    ("POST", "/semantics/evaluate-scalar",
     {"semantics": _MINIMAL_SEMANTICS, "scalar_context": _SCALAR_CONTEXT}),
    ("POST", "/semantics/extract-signal-events",
     {"semantics": _MINIMAL_SEMANTICS, "bars": _MINIMAL_BARS}),
    ("POST", "/semantics/extract-trade-intents", _SIGNAL_EVENT_BATCH),
    ("POST", "/backtests/simulate", _SIMULATE_BODY),
]


class TestEvaluationRouteNoAuth:
    def setup_method(self):
        _override(None)

    def teardown_method(self):
        app.dependency_overrides.pop(require_active_subscription, None)

    @pytest.mark.parametrize("method,path,body", _ENDPOINTS)
    def test_unauthenticated_returns_401(self, method, path, body):
        resp = _CLIENT_NO_AUTH.post(path, json=body)
        assert resp.status_code == 401, (
            f"{path}: expected 401, got {resp.status_code} — {resp.text[:200]}"
        )


class TestEvaluationRouteActiveUser:
    def setup_method(self):
        _override(_ACTIVE_USER)

    def teardown_method(self):
        app.dependency_overrides.pop(require_active_subscription, None)

    @pytest.mark.parametrize("method,path,body", _ENDPOINTS)
    def test_active_user_is_not_401_or_403(self, method, path, body):
        resp = _CLIENT_NO_AUTH.post(path, json=body)
        assert resp.status_code not in (401, 403), (
            f"{path}: active user should not get {resp.status_code}"
        )


def _override_current_user(user: User) -> None:
    """Override get_current_user so require_active_subscription runs its real logic."""
    from unittest.mock import MagicMock
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_user_repository] = lambda: MagicMock()


def _clear_current_user_override() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_user_repository, None)


class TestEvaluationRouteExpiredUser:
    def setup_method(self):
        from unittest.mock import patch as _patch
        self._patcher = _patch(
            "backend.auth.expiry.evaluate_subscription_expiry",
            side_effect=lambda u, r: u,
        )
        self._patcher.start()
        app.dependency_overrides.pop(require_active_subscription, None)
        _override_current_user(_EXPIRED_USER)

    def teardown_method(self):
        self._patcher.stop()
        _clear_current_user_override()

    @pytest.mark.parametrize("method,path,body", _ENDPOINTS)
    def test_expired_subscription_returns_403(self, method, path, body):
        resp = _CLIENT_NO_AUTH.post(path, json=body)
        assert resp.status_code == 403, (
            f"{path}: expired user should get 403, got {resp.status_code}"
        )


class TestEvaluationRouteSuspendedUser:
    def setup_method(self):
        from unittest.mock import patch as _patch
        self._patcher = _patch(
            "backend.auth.expiry.evaluate_subscription_expiry",
            side_effect=lambda u, r: u,
        )
        self._patcher.start()
        app.dependency_overrides.pop(require_active_subscription, None)
        _override_current_user(_SUSPENDED_USER)

    def teardown_method(self):
        self._patcher.stop()
        _clear_current_user_override()

    @pytest.mark.parametrize("method,path,body", _ENDPOINTS)
    def test_suspended_subscription_returns_403(self, method, path, body):
        resp = _CLIENT_NO_AUTH.post(path, json=body)
        assert resp.status_code == 403, (
            f"{path}: suspended user should get 403, got {resp.status_code}"
        )


class TestEvaluationRouteAdmin:
    def setup_method(self):
        _override(_ADMIN_USER)

    def teardown_method(self):
        app.dependency_overrides.pop(require_active_subscription, None)

    @pytest.mark.parametrize("method,path,body", _ENDPOINTS)
    def test_admin_is_not_401_or_403(self, method, path, body):
        resp = _CLIENT_NO_AUTH.post(path, json=body)
        assert resp.status_code not in (401, 403), (
            f"{path}: admin should not get {resp.status_code}"
        )

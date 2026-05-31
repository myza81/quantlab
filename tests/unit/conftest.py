"""
Unit test configuration — Phase 3S-B.

Provides a default active-user dependency override for all unit tests that
call compute endpoints (which now require require_active_subscription).

Tests that explicitly test auth/entitlement behavior override this themselves
in their own setup_method / teardown_method.
"""
from __future__ import annotations

import pytest

from backend.api.main import app
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User

_DEFAULT_TEST_USER = User(
    user_id="unit-test-user",
    username="unittestuser",
    email="unittest@example.com",
    password_hash="x",
    created_at="2024-01-01T00:00:00Z",
    role="user",
    subscription_status="active",
)


@pytest.fixture(autouse=True)
def _default_active_user_override():
    """
    Set require_active_subscription to return a default active user for every
    unit test.  Tests that check auth behaviour are responsible for overriding
    or clearing this themselves in their own setup/teardown.
    """
    prev = app.dependency_overrides.get(require_active_subscription)
    app.dependency_overrides[require_active_subscription] = lambda: _DEFAULT_TEST_USER
    yield
    if prev is None:
        app.dependency_overrides.pop(require_active_subscription, None)
    else:
        app.dependency_overrides[require_active_subscription] = prev

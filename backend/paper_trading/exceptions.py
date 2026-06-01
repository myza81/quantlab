"""
Typed exceptions for the Paper Trading subsystem — Phase 4E.1.

Information hiding: PaperTradingSessionNotFoundError is raised for both
missing sessions AND wrong-owner access — callers (routes) map it to HTTP 404
regardless of the actual cause, preventing existence leakage.
"""
from __future__ import annotations


class PaperTradingSessionNotFoundError(Exception):
    """
    Raised when a session does not exist at the expected path,
    OR when the requesting user does not own the session.

    These two cases are intentionally indistinguishable to callers.
    """


class PaperTradingSessionAlreadyExistsError(Exception):
    """Raised when creating a session whose session_id already exists."""


class PaperTradingPersistenceError(Exception):
    """Raised on unexpected I/O or deserialization failures."""


class PaperTradingInvalidTransitionError(Exception):
    """
    Raised when an invalid session status transition is attempted.

    Includes both the current and target states in the message.
    """


class PaperAccountNotFoundError(Exception):
    """
    Raised when a PaperAccount does not exist for a given session,
    OR when the session does not belong to the requesting user.

    These two cases are intentionally indistinguishable to callers.
    """


class PaperAccountAlreadyExistsError(Exception):
    """Raised when creating an account for a session that already has one."""


# ---------------------------------------------------------------------------
# Phase 4E.2 — execution layer exceptions
# ---------------------------------------------------------------------------

class PaperOrderNotFoundError(Exception):
    """
    Raised when a PaperOrder does not exist at the expected path,
    OR when a mark_* operation targets an order_id not found in pending storage.
    """


class PaperPositionNotFoundError(Exception):
    """
    Raised when a PaperPosition does not exist at the expected path.
    Used by update() and load() when the position file is absent.
    """


class PaperPositionAlreadyExistsError(Exception):
    """Raised when saving a PaperPosition whose position_id already exists."""

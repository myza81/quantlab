"""
Typed exceptions for the Forward Testing subsystem — Phase 4C.1.

Information hiding: ForwardTestSessionNotFoundError is raised for both
missing sessions AND wrong-owner access — callers (routes) map it to HTTP 404
regardless of the actual cause, preventing existence leakage.
"""
from __future__ import annotations


class ForwardTestSessionNotFoundError(Exception):
    """
    Raised when a session does not exist at the expected path,
    OR when the requesting user does not own the session.

    These two cases are intentionally indistinguishable to callers.
    """


class ForwardTestSessionAlreadyExistsError(Exception):
    """Raised when creating a session whose session_id already exists."""


class ForwardTestPersistenceError(Exception):
    """Raised on unexpected I/O or deserialization failures."""


class ForwardTestInvalidTransitionError(Exception):
    """
    Raised when an invalid session status transition is attempted.

    Includes both the current and target states in the message.
    """

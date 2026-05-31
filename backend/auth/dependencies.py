"""
FastAPI dependency: get_current_user

Extracts the Bearer token from the Authorization header, verifies it,
and returns the authenticated User or raises HTTP 401.

Audit events are emitted for INVALID_TOKEN and PROTECTED_ROUTE_DENIED.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.models import User
from backend.auth.repository import UserRepository
from backend.auth.tokens import TokenError, TokenExpiredError, decode_access_token
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository() -> UserRepository:
    """FastAPI dependency: returns a UserRepository backed by the configured users file."""
    return UserRepository(settings.users_file_path)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    repository: UserRepository = Depends(get_user_repository),
) -> User | None:
    """
    FastAPI dependency. Returns the authenticated User or None.

    Does NOT raise 401 — callers decide how to handle unauthenticated access.
    Useful for optional-auth endpoints where some operations require identity
    and others do not (e.g. public providers vs vault-backed providers).
    """
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except (TokenError, TokenExpiredError):
        return None
    user_id: str = payload.get("user_id", "")
    return repository.get_by_id(user_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    repository: UserRepository = Depends(get_user_repository),
) -> User:
    """
    FastAPI dependency. Returns the authenticated User.
    Raises HTTP 401 for missing, expired, or invalid tokens.
    """
    if credentials is None:
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PROTECTED_ROUTE_DENIED,
            details={"reason": "no_token"},
        ))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.INVALID_TOKEN,
            details={"reason": "expired"},
        ))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenError:
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.INVALID_TOKEN,
            details={"reason": "invalid"},
        ))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("user_id", "")
    user = repository.get_by_id(user_id)
    if user is None:
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.PROTECTED_ROUTE_DENIED,
            details={"reason": "user_not_found", "user_id": user_id},
        ))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

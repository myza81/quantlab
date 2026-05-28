"""
AuthService — application-layer auth logic.

Orchestrates: UserRepository + password hashing + token creation + audit events.

INVARIANTS:
  - passwords are hashed before any persistence call
  - plaintext passwords are never passed to audit or logging
  - audit events are emitted for every register, login success, and login failure
"""
from __future__ import annotations

from dataclasses import replace

from backend.auth.models import User, UserRole, SubscriptionStatus
from backend.auth.password import hash_password, verify_password
from backend.auth.repository import DuplicateEmailError, DuplicateUsernameError, UserRepository
from backend.auth.tokens import create_access_token
from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.config import settings


class RegistrationError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self._repo = repository

    def register(self, *, username: str, email: str, password: str) -> User:
        """
        Create a new user account.

        Raises RegistrationError if username or email is already taken,
        or if input validation fails.
        """
        username = username.strip().lower()
        email = email.strip().lower()

        if not username:
            raise RegistrationError("Username must not be empty")
        if not email or "@" not in email:
            raise RegistrationError("Email is invalid")
        if not password or len(password) < 8:
            raise RegistrationError("Password must be at least 8 characters")

        hashed = hash_password(password)
        user = User.create(username=username, email=email, password_hash=hashed)

        # Admin bootstrap: if this email matches the configured bootstrap address,
        # auto-promote to admin with an active subscription. This only applies at
        # registration time — there is no API path to self-escalate to admin.
        bootstrap_email = (settings.admin_bootstrap_email or "").strip().lower()
        if bootstrap_email and email == bootstrap_email:
            user = replace(
                user,
                role=UserRole.admin,
                subscription_status=SubscriptionStatus.active,
                approved_by_user_id="bootstrap",
            )

        try:
            self._repo.save(user)
        except DuplicateUsernameError:
            raise RegistrationError("Username already taken")
        except DuplicateEmailError:
            raise RegistrationError("Email already registered")

        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.USER_REGISTERED,
            details={"username": username, "user_id": user.user_id, "role": user.role},
        ))
        return user

    def login(self, *, username: str, password: str) -> str:
        """
        Authenticate user and return a JWT access token.

        Raises AuthenticationError on bad credentials.
        INVARIANT: error message does not reveal whether username or password is wrong.
        """
        username = username.strip().lower()
        user = self._repo.get_by_username(username)

        if user is None or not verify_password(password, user.password_hash):
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.LOGIN_FAILURE,
                details={"username": username},
            ))
            raise AuthenticationError("Invalid credentials")

        token = create_access_token(username=user.username, user_id=user.user_id)
        emit_audit_event(AuditEvent(
            event_kind=AuditEventKind.LOGIN_SUCCESS,
            details={"username": username, "user_id": user.user_id},
        ))
        return token

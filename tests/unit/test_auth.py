"""
Phase 3H — Authentication & User Identity Foundation

Tests cover:
  - User model: creation, serialization round-trip, immutability
  - Password: hashing, verification, empty input rejection
  - Tokens: creation, decode, expiry, tampering
  - UserRepository: save, duplicate detection, lookup, thread-safety, persistence
  - AuthService: register, login, error cases, audit emission
  - get_current_user dependency: valid token, missing token, expired token, unknown user
  - Auth routes (via TestClient): register, login, /me
  - Security invariants: no plaintext password in token payload, no hash in responses
  - Architecture boundary: no password_hash in UserResponse schema
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.auth.models import User
from backend.auth.password import hash_password, verify_password
from backend.auth.repository import DuplicateEmailError, DuplicateUsernameError, UserRepository
from backend.auth.service import AuthService, AuthenticationError, RegistrationError
from backend.auth.tokens import (
    TokenError,
    TokenExpiredError,
    create_access_token,
    decode_access_token,
)
from backend.core.audit import AuditEventKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(tmp_path: Path) -> UserRepository:
    return UserRepository(tmp_path / "users.json")


def _make_service(tmp_path: Path) -> AuthService:
    return AuthService(_make_repo(tmp_path))


def _register_alice(service: AuthService) -> User:
    return service.register(username="alice", email="alice@example.com", password="securepass1")


# ---------------------------------------------------------------------------
# TestUserModel
# ---------------------------------------------------------------------------

class TestUserModel:
    def test_create_assigns_user_id(self) -> None:
        user = User.create(username="alice", email="a@b.com", password_hash="hash")
        assert user.user_id != ""

    def test_create_lowercases_username(self) -> None:
        user = User.create(username="ALICE", email="a@b.com", password_hash="hash")
        assert user.username == "alice"

    def test_create_lowercases_email(self) -> None:
        user = User.create(username="alice", email="A@B.COM", password_hash="hash")
        assert user.email == "a@b.com"

    def test_create_sets_created_at(self) -> None:
        user = User.create(username="alice", email="a@b.com", password_hash="hash")
        assert "T" in user.created_at  # ISO-8601

    def test_unique_ids_each_create(self) -> None:
        u1 = User.create(username="a", email="a@b.com", password_hash="h")
        u2 = User.create(username="b", email="b@b.com", password_hash="h")
        assert u1.user_id != u2.user_id

    def test_frozen(self) -> None:
        user = User.create(username="alice", email="a@b.com", password_hash="hash")
        with pytest.raises(Exception):
            user.username = "bob"  # type: ignore[misc]

    def test_round_trip_dict(self) -> None:
        user = User.create(username="alice", email="a@b.com", password_hash="hash")
        restored = User.from_dict(user.to_dict())
        assert restored == user

    def test_to_dict_has_all_fields(self) -> None:
        user = User.create(username="alice", email="a@b.com", password_hash="hash")
        d = user.to_dict()
        assert set(d.keys()) == {
            "user_id", "username", "email", "password_hash", "created_at",
            "role", "subscription_status", "subscription_expires_at",
            "approved_by_user_id", "approved_at", "subscription_notes", "suspension_reason",
        }


# ---------------------------------------------------------------------------
# TestPasswordHashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_returns_string(self) -> None:
        assert isinstance(hash_password("secret"), str)

    def test_hash_starts_with_bcrypt_prefix(self) -> None:
        assert hash_password("secret").startswith("$2")

    def test_hash_is_not_plaintext(self) -> None:
        assert hash_password("secret") != "secret"

    def test_verify_correct_password(self) -> None:
        h = hash_password("mypassword")
        assert verify_password("mypassword", h) is True

    def test_verify_wrong_password(self) -> None:
        h = hash_password("mypassword")
        assert verify_password("wrongpassword", h) is False

    def test_two_hashes_differ(self) -> None:
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # different salts

    def test_empty_password_raises(self) -> None:
        with pytest.raises(ValueError):
            hash_password("")

    def test_verify_empty_plaintext_returns_false(self) -> None:
        h = hash_password("secret")
        assert verify_password("", h) is False

    def test_verify_empty_hash_returns_false(self) -> None:
        assert verify_password("secret", "") is False


# ---------------------------------------------------------------------------
# TestTokens
# ---------------------------------------------------------------------------

class TestTokens:
    def test_create_returns_string(self) -> None:
        token = create_access_token(username="alice", user_id="uid-1")
        assert isinstance(token, str)
        assert len(token) > 10

    def test_decode_valid_token(self) -> None:
        token = create_access_token(username="alice", user_id="uid-1")
        payload = decode_access_token(token)
        assert payload["sub"] == "alice"
        assert payload["user_id"] == "uid-1"

    def test_decode_expired_raises_token_expired_error(self) -> None:
        from backend.core.config import settings
        payload = {"sub": "alice", "user_id": "uid-1",
                   "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}
        token = jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm)
        with pytest.raises(TokenExpiredError):
            decode_access_token(token)

    def test_decode_tampered_raises_token_error(self) -> None:
        token = create_access_token(username="alice", user_id="uid-1")
        tampered = token[:-4] + "xxxx"
        with pytest.raises(TokenError):
            decode_access_token(tampered)

    def test_decode_wrong_secret_raises_token_error(self) -> None:
        payload = {"sub": "alice", "user_id": "uid-1",
                   "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(TokenError):
            decode_access_token(token)

    def test_token_payload_does_not_contain_password_hash(self) -> None:
        token = create_access_token(username="alice", user_id="uid-1")
        payload = decode_access_token(token)
        assert "password_hash" not in payload
        assert "password" not in payload

    def test_token_payload_contains_only_allowed_keys(self) -> None:
        token = create_access_token(username="alice", user_id="uid-1")
        payload = decode_access_token(token)
        allowed = {"sub", "user_id", "exp"}
        assert set(payload.keys()) <= allowed

    def test_token_expired_error_is_token_error(self) -> None:
        assert issubclass(TokenExpiredError, TokenError)


# ---------------------------------------------------------------------------
# TestUserRepository
# ---------------------------------------------------------------------------

class TestUserRepository:
    def test_empty_on_fresh_file(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.count() == 0

    def test_save_and_retrieve_by_username(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        user = User.create(username="alice", email="a@b.com", password_hash="h")
        repo.save(user)
        found = repo.get_by_username("alice")
        assert found is not None
        assert found.user_id == user.user_id

    def test_username_lookup_case_insensitive(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        user = User.create(username="alice", email="a@b.com", password_hash="h")
        repo.save(user)
        assert repo.get_by_username("ALICE") is not None

    def test_save_and_retrieve_by_email(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        user = User.create(username="alice", email="a@b.com", password_hash="h")
        repo.save(user)
        assert repo.get_by_email("a@b.com") is not None

    def test_save_and_retrieve_by_id(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        user = User.create(username="alice", email="a@b.com", password_hash="h")
        repo.save(user)
        assert repo.get_by_id(user.user_id) is not None

    def test_get_by_username_missing_returns_none(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.get_by_username("nobody") is None

    def test_get_by_email_missing_returns_none(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.get_by_email("nobody@x.com") is None

    def test_get_by_id_missing_returns_none(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.get_by_id("nonexistent-id") is None

    def test_duplicate_username_raises(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        u1 = User.create(username="alice", email="a@b.com", password_hash="h")
        u2 = User.create(username="alice", email="b@b.com", password_hash="h")
        repo.save(u1)
        with pytest.raises(DuplicateUsernameError):
            repo.save(u2)

    def test_duplicate_email_raises(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        u1 = User.create(username="alice", email="same@b.com", password_hash="h")
        u2 = User.create(username="bob", email="same@b.com", password_hash="h")
        repo.save(u1)
        with pytest.raises(DuplicateEmailError):
            repo.save(u2)

    def test_persistence_across_reload(self, tmp_path: Path) -> None:
        repo1 = _make_repo(tmp_path)
        user = User.create(username="alice", email="a@b.com", password_hash="h")
        repo1.save(user)
        repo2 = _make_repo(tmp_path)
        found = repo2.get_by_username("alice")
        assert found is not None
        assert found.user_id == user.user_id

    def test_count_increments_on_save(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.count() == 0
        repo.save(User.create(username="a", email="a@b.com", password_hash="h"))
        assert repo.count() == 1
        repo.save(User.create(username="b", email="b@b.com", password_hash="h"))
        assert repo.count() == 2

    def test_json_file_created_after_save(self, tmp_path: Path) -> None:
        json_path = tmp_path / "users.json"
        repo = UserRepository(json_path)
        repo.save(User.create(username="alice", email="a@b.com", password_hash="h"))
        assert json_path.exists()

    def test_json_file_is_valid_json(self, tmp_path: Path) -> None:
        json_path = tmp_path / "users.json"
        repo = UserRepository(json_path)
        repo.save(User.create(username="alice", email="a@b.com", password_hash="h"))
        data = json.loads(json_path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1

    def test_concurrent_saves_no_data_loss(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        errors: list = []

        def save_user(i: int) -> None:
            try:
                user = User.create(username=f"user{i}", email=f"u{i}@b.com", password_hash="h")
                repo.save(user)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=save_user, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert repo.count() == 10


# ---------------------------------------------------------------------------
# TestAuthService
# ---------------------------------------------------------------------------

class TestAuthService:
    def test_register_returns_user(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        user = service.register(username="alice", email="alice@example.com", password="securepass1")
        assert user.username == "alice"
        assert user.email == "alice@example.com"

    def test_register_password_not_stored_plaintext(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        user = service.register(username="alice", email="a@b.com", password="securepass1")
        assert user.password_hash != "securepass1"
        assert user.password_hash.startswith("$2")

    def test_register_duplicate_username_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        service.register(username="alice", email="a@b.com", password="securepass1")
        with pytest.raises(RegistrationError, match="Username"):
            service.register(username="alice", email="b@b.com", password="securepass1")

    def test_register_duplicate_email_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        service.register(username="alice", email="same@b.com", password="securepass1")
        with pytest.raises(RegistrationError, match="Email"):
            service.register(username="bob", email="same@b.com", password="securepass1")

    def test_register_short_password_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        with pytest.raises(RegistrationError, match="8"):
            service.register(username="alice", email="a@b.com", password="short")

    def test_register_empty_username_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        with pytest.raises(RegistrationError):
            service.register(username="  ", email="a@b.com", password="securepass1")

    def test_register_emits_audit_event(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        emitted: list = []
        with patch("backend.auth.service.emit_audit_event", side_effect=emitted.append):
            service.register(username="alice", email="a@b.com", password="securepass1")
        assert any(e.event_kind == AuditEventKind.USER_REGISTERED for e in emitted)

    def test_login_returns_token(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        _register_alice(service)
        token = service.login(username="alice", password="securepass1")
        assert isinstance(token, str)
        assert len(token) > 10

    def test_login_token_is_valid_jwt(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        _register_alice(service)
        token = service.login(username="alice", password="securepass1")
        payload = decode_access_token(token)
        assert payload["sub"] == "alice"

    def test_login_wrong_password_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        _register_alice(service)
        with pytest.raises(AuthenticationError):
            service.login(username="alice", password="wrongpassword")

    def test_login_unknown_user_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        with pytest.raises(AuthenticationError):
            service.login(username="ghost", password="securepass1")

    def test_login_error_message_generic(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            service.login(username="ghost", password="x")

    def test_login_success_emits_audit_event(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        _register_alice(service)
        emitted: list = []
        with patch("backend.auth.service.emit_audit_event", side_effect=emitted.append):
            service.login(username="alice", password="securepass1")
        assert any(e.event_kind == AuditEventKind.LOGIN_SUCCESS for e in emitted)

    def test_login_failure_emits_audit_event(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        _register_alice(service)
        emitted: list = []
        with patch("backend.auth.service.emit_audit_event", side_effect=emitted.append):
            with pytest.raises(AuthenticationError):
                service.login(username="alice", password="bad")
        assert any(e.event_kind == AuditEventKind.LOGIN_FAILURE for e in emitted)


# ---------------------------------------------------------------------------
# TestGetCurrentUserDependency
# ---------------------------------------------------------------------------

class TestGetCurrentUserDependency:
    def _call_dep(self, token: str | None, repo: UserRepository):
        from fastapi.security import HTTPAuthorizationCredentials
        from backend.auth.dependencies import get_current_user

        if token is not None:
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        else:
            creds = None
        return get_current_user(credentials=creds, repository=repo)

    def test_valid_token_returns_user(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        user = User.create(username="alice", email="a@b.com", password_hash=hash_password("pw"))
        repo.save(user)
        token = create_access_token(username="alice", user_id=user.user_id)
        result = self._call_dep(token, repo)
        assert result.username == "alice"

    def test_no_credentials_raises_401(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        with pytest.raises(HTTPException) as exc_info:
            self._call_dep(None, repo)
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self, tmp_path: Path) -> None:
        from backend.core.config import settings
        repo = _make_repo(tmp_path)
        payload = {"sub": "alice", "user_id": "uid-x",
                   "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}
        expired_token = jwt.encode(payload, settings.auth_secret_key,
                                   algorithm=settings.auth_algorithm)
        with pytest.raises(HTTPException) as exc_info:
            self._call_dep(expired_token, repo)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_tampered_token_raises_401(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        token = create_access_token(username="alice", user_id="uid-x")
        tampered = token[:-4] + "xxxx"
        with pytest.raises(HTTPException) as exc_info:
            self._call_dep(tampered, repo)
        assert exc_info.value.status_code == 401

    def test_user_not_in_repo_raises_401(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        token = create_access_token(username="ghost", user_id="nonexistent-id")
        with pytest.raises(HTTPException) as exc_info:
            self._call_dep(token, repo)
        assert exc_info.value.status_code == 401

    def test_invalid_token_emits_audit_event(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        emitted: list = []
        with patch("backend.auth.dependencies.emit_audit_event", side_effect=emitted.append):
            with pytest.raises(HTTPException):
                self._call_dep("not.a.jwt", repo)
        assert any(e.event_kind == AuditEventKind.INVALID_TOKEN for e in emitted)

    def test_no_token_emits_audit_event(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        emitted: list = []
        with patch("backend.auth.dependencies.emit_audit_event", side_effect=emitted.append):
            with pytest.raises(HTTPException):
                self._call_dep(None, repo)
        assert any(e.event_kind == AuditEventKind.PROTECTED_ROUTE_DENIED for e in emitted)


# ---------------------------------------------------------------------------
# TestAuthRoutes
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path):
    from backend.api.main import app
    from backend.core.config import settings
    # Override users_file_path so tests use tmp dir
    settings.users_file_path = tmp_path / "users.json"
    with TestClient(app) as c:
        yield c


class TestAuthRoutes:
    def test_register_returns_201(self, client) -> None:
        resp = client.post("/auth/register", json={
            "username": "alice", "email": "alice@example.com", "password": "securepass1"
        })
        assert resp.status_code == 201

    def test_register_response_contains_user_id(self, client) -> None:
        resp = client.post("/auth/register", json={
            "username": "alice", "email": "alice@example.com", "password": "securepass1"
        })
        body = resp.json()
        assert "user_id" in body
        assert len(body["user_id"]) > 0

    def test_register_response_no_password_hash(self, client) -> None:
        resp = client.post("/auth/register", json={
            "username": "alice", "email": "alice@example.com", "password": "securepass1"
        })
        body = resp.json()
        assert "password_hash" not in body
        assert "password" not in body

    def test_register_duplicate_username_returns_409(self, client) -> None:
        payload = {"username": "alice", "email": "alice@example.com", "password": "securepass1"}
        client.post("/auth/register", json=payload)
        resp = client.post("/auth/register", json={
            "username": "alice", "email": "other@example.com", "password": "securepass1"
        })
        assert resp.status_code == 409

    def test_register_invalid_email_returns_422(self, client) -> None:
        resp = client.post("/auth/register", json={
            "username": "alice", "email": "not-an-email", "password": "securepass1"
        })
        assert resp.status_code == 422

    def test_register_short_password_returns_422(self, client) -> None:
        resp = client.post("/auth/register", json={
            "username": "alice", "email": "a@b.com", "password": "short"
        })
        assert resp.status_code == 422

    def test_login_returns_200_and_token(self, client) -> None:
        client.post("/auth/register", json={
            "username": "alice", "email": "alice@example.com", "password": "securepass1"
        })
        resp = client.post("/auth/login", json={"username": "alice", "password": "securepass1"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_token_type_is_bearer(self, client) -> None:
        client.post("/auth/register", json={
            "username": "alice", "email": "alice@example.com", "password": "securepass1"
        })
        resp = client.post("/auth/login", json={"username": "alice", "password": "securepass1"})
        assert resp.json()["token_type"] == "bearer"

    def test_login_wrong_password_returns_401(self, client) -> None:
        client.post("/auth/register", json={
            "username": "alice", "email": "alice@example.com", "password": "securepass1"
        })
        resp = client.post("/auth/login", json={"username": "alice", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_unknown_user_returns_401(self, client) -> None:
        resp = client.post("/auth/login", json={"username": "ghost", "password": "securepass1"})
        assert resp.status_code == 401

    def test_me_returns_user_info(self, client) -> None:
        client.post("/auth/register", json={
            "username": "alice", "email": "alice@example.com", "password": "securepass1"
        })
        login_resp = client.post("/auth/login", json={"username": "alice", "password": "securepass1"})
        token = login_resp.json()["access_token"]
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"

    def test_me_no_token_returns_401(self, client) -> None:
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_bad_token_returns_401(self, client) -> None:
        resp = client.get("/auth/me", headers={"Authorization": "Bearer notavalidtoken"})
        assert resp.status_code == 401

    def test_me_response_no_password_hash(self, client) -> None:
        client.post("/auth/register", json={
            "username": "alice", "email": "alice@example.com", "password": "securepass1"
        })
        login_resp = client.post("/auth/login", json={"username": "alice", "password": "securepass1"})
        token = login_resp.json()["access_token"]
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        body = resp.json()
        assert "password_hash" not in body
        assert "password" not in body


# ---------------------------------------------------------------------------
# TestSecurityInvariants
# ---------------------------------------------------------------------------

class TestSecurityInvariants:
    def test_user_response_schema_has_no_password_hash_field(self) -> None:
        from backend.api.schemas.auth import UserResponse
        assert "password_hash" not in UserResponse.model_fields
        assert "password" not in UserResponse.model_fields

    def test_token_response_schema_has_no_password_field(self) -> None:
        from backend.api.schemas.auth import TokenResponse
        assert "password" not in TokenResponse.model_fields
        assert "password_hash" not in TokenResponse.model_fields

    def test_token_payload_never_contains_secret_key(self) -> None:
        from backend.core.config import settings
        token = create_access_token(username="alice", user_id="uid-1")
        # The raw token string must not contain the secret
        assert settings.auth_secret_key not in token

    def test_login_failure_message_does_not_reveal_which_field_is_wrong(
        self, tmp_path: Path
    ) -> None:
        service = _make_service(tmp_path)
        _register_alice(service)
        try:
            service.login(username="alice", password="wrongpw")
        except AuthenticationError as exc:
            msg = str(exc).lower()
            assert "password" not in msg or "invalid" in msg
            assert "username" not in msg or "invalid" in msg


# ---------------------------------------------------------------------------
# TestArchitectureBoundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def test_auth_routes_does_not_import_strategy_runtime(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/api/routes/auth.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "strategy_runtime" not in node.module
                assert "strategy_registry" not in node.module

    def test_auth_models_does_not_import_data_providers(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/auth/models.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "data_providers" not in node.module

    def test_auth_service_does_not_import_data_providers(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/auth/service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "data_providers" not in node.module

    def test_password_module_only_imports_bcrypt(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("backend/auth/password.py").read_text()
        tree = ast.parse(src)
        external_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    external_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                external_imports.append(node.module)
        # Only bcrypt and __future__ allowed as non-stdlib imports
        for imp in external_imports:
            assert imp in ("bcrypt", "__future__"), f"unexpected import: {imp}"

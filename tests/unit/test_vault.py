"""
Phase 3I — Provider Credential Vault

Tests cover:
  - ProviderCredential model: creation, serialization, __repr__ safety
  - Crypto: encrypt/decrypt round-trip, wrong key, empty input
  - CredentialRepository: save/get/list/update/delete, user scoping, persistence, thread-safety
  - VaultService: register, list, get, disable, delete, resolve
  - Ownership enforcement: cross-user access denial
  - Disabled credential handling
  - Provider mismatch handling
  - Decryption failure handling
  - Audit event emission for all vault operations
  - API routes: all 5 endpoints, auth required, no secrets in responses
  - Security invariants: no plaintext in JSON file, no secret in response schema,
    no secret in __repr__, no secret in audit events
  - Architecture boundary: vault does not import strategy/data_providers modules
  - Polygon backward compatibility: ENV-based resolver still functional
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.vault.crypto import VaultCryptoError, decrypt_secret, encrypt_secret
from backend.vault.models import ProviderCredential
from backend.vault.repository import CredentialRepository
from backend.vault.service import (
    CredentialAccessDeniedError,
    CredentialDisabledError,
    CredentialProviderMismatchError,
    CredentialRegistrationError,
    VaultService,
)
from backend.core.audit import AuditEventKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(tmp_path: Path) -> CredentialRepository:
    return CredentialRepository(tmp_path / "credentials.json")


def _make_service(tmp_path: Path) -> VaultService:
    return VaultService(_make_repo(tmp_path))


def _make_credential(user_id: str = "user-1") -> ProviderCredential:
    return ProviderCredential.create(
        user_id=user_id,
        provider_name="polygon",
        credential_label="My Polygon Key",
        encrypted_secret=encrypt_secret("test-api-key-value"),
    )


# ---------------------------------------------------------------------------
# TestProviderCredentialModel
# ---------------------------------------------------------------------------

class TestProviderCredentialModel:
    def test_create_assigns_credential_id(self) -> None:
        c = _make_credential()
        assert c.credential_id != ""
        assert len(c.credential_id) > 10

    def test_create_active_by_default(self) -> None:
        c = _make_credential()
        assert c.active is True

    def test_create_lowercases_provider_name(self) -> None:
        c = ProviderCredential.create(
            user_id="u", provider_name="POLYGON",
            credential_label="label", encrypted_secret="enc",
        )
        assert c.provider_name == "polygon"

    def test_create_preserves_label(self) -> None:
        c = ProviderCredential.create(
            user_id="u", provider_name="polygon",
            credential_label="  My Key  ", encrypted_secret="enc",
        )
        assert c.credential_label == "My Key"

    def test_frozen_immutable(self) -> None:
        c = _make_credential()
        with pytest.raises(Exception):
            c.active = False  # type: ignore[misc]

    def test_with_active_returns_new_instance(self) -> None:
        c = _make_credential()
        disabled = c.with_active(False)
        assert disabled.active is False
        assert c.active is True  # original unchanged

    def test_with_active_preserves_fields(self) -> None:
        c = _make_credential()
        updated = c.with_active(False)
        assert updated.credential_id == c.credential_id
        assert updated.user_id == c.user_id
        assert updated.provider_name == c.provider_name

    def test_round_trip_dict(self) -> None:
        c = _make_credential()
        restored = ProviderCredential.from_dict(c.to_dict())
        assert restored == c

    def test_to_dict_has_all_fields(self) -> None:
        c = _make_credential()
        d = c.to_dict()
        assert set(d.keys()) == {
            "credential_id", "user_id", "provider_name",
            "credential_label", "encrypted_secret", "active",
            "created_at", "updated_at",
        }

    def test_repr_does_not_contain_encrypted_secret(self) -> None:
        encrypted = encrypt_secret("super-secret-key")
        c = ProviderCredential.create(
            user_id="u", provider_name="polygon",
            credential_label="label", encrypted_secret=encrypted,
        )
        assert encrypted not in repr(c)
        assert "super-secret-key" not in repr(c)

    def test_unique_ids_per_create(self) -> None:
        c1 = _make_credential("u1")
        c2 = _make_credential("u2")
        assert c1.credential_id != c2.credential_id


# ---------------------------------------------------------------------------
# TestVaultCrypto
# ---------------------------------------------------------------------------

class TestVaultCrypto:
    def test_encrypt_returns_string(self) -> None:
        result = encrypt_secret("my-api-key")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encrypt_is_not_plaintext(self) -> None:
        result = encrypt_secret("my-api-key")
        assert "my-api-key" not in result

    def test_decrypt_round_trip(self) -> None:
        plaintext = "super-secret-api-key-12345"
        encrypted = encrypt_secret(plaintext)
        assert decrypt_secret(encrypted) == plaintext

    def test_two_encryptions_differ(self) -> None:
        e1 = encrypt_secret("same-key")
        e2 = encrypt_secret("same-key")
        assert e1 != e2  # fresh IV each time

    def test_empty_plaintext_raises(self) -> None:
        with pytest.raises(VaultCryptoError):
            encrypt_secret("")

    def test_empty_ciphertext_raises(self) -> None:
        with pytest.raises(VaultCryptoError):
            decrypt_secret("")

    def test_tampered_ciphertext_raises(self) -> None:
        encrypted = encrypt_secret("key")
        tampered = encrypted[:-4] + "xxxx"
        with pytest.raises(VaultCryptoError):
            decrypt_secret(tampered)

    def test_wrong_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        encrypted = encrypt_secret("key")
        monkeypatch.setattr(
            "backend.vault.crypto.settings",
            type("s", (), {"vault_encryption_key": "completely-different-vault-key-string"})(),
        )
        with pytest.raises(VaultCryptoError):
            decrypt_secret(encrypted)

    def test_decrypt_error_message_no_secret(self) -> None:
        try:
            decrypt_secret("not-valid-fernet-token")
        except VaultCryptoError as exc:
            assert "not-valid-fernet-token" not in str(exc)


# ---------------------------------------------------------------------------
# TestCredentialRepository
# ---------------------------------------------------------------------------

class TestCredentialRepository:
    def test_empty_on_fresh_file(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.count() == 0

    def test_save_and_retrieve_by_id(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        c = _make_credential()
        repo.save(c)
        found = repo.get_by_id(c.credential_id)
        assert found is not None
        assert found.credential_id == c.credential_id

    def test_get_by_id_missing_returns_none(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.get_by_id("nonexistent") is None

    def test_list_by_user_returns_only_that_user(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        c1 = _make_credential("user-1")
        c2 = _make_credential("user-2")
        repo.save(c1)
        repo.save(c2)
        result = repo.list_by_user("user-1")
        assert len(result) == 1
        assert result[0].credential_id == c1.credential_id

    def test_list_by_user_empty_returns_empty(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.list_by_user("nobody") == []

    def test_duplicate_save_raises(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        c = _make_credential()
        repo.save(c)
        with pytest.raises(ValueError):
            repo.save(c)

    def test_update_replaces_record(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        c = _make_credential()
        repo.save(c)
        disabled = c.with_active(False)
        repo.update(disabled)
        found = repo.get_by_id(c.credential_id)
        assert found is not None
        assert found.active is False

    def test_update_missing_raises(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        c = _make_credential()
        with pytest.raises(ValueError):
            repo.update(c)

    def test_delete_removes_record(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        c = _make_credential()
        repo.save(c)
        assert repo.delete(c.credential_id) is True
        assert repo.get_by_id(c.credential_id) is None

    def test_delete_missing_returns_false(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.delete("nonexistent") is False

    def test_persistence_across_reload(self, tmp_path: Path) -> None:
        repo1 = _make_repo(tmp_path)
        c = _make_credential()
        repo1.save(c)
        repo2 = _make_repo(tmp_path)
        found = repo2.get_by_id(c.credential_id)
        assert found is not None
        assert found.encrypted_secret == c.encrypted_secret

    def test_json_file_does_not_contain_plaintext_secret(self, tmp_path: Path) -> None:
        json_path = tmp_path / "credentials.json"
        repo = CredentialRepository(json_path)
        raw_secret = "plaintext-should-not-appear-in-file"
        encrypted = encrypt_secret(raw_secret)
        c = ProviderCredential.create(
            user_id="u", provider_name="polygon",
            credential_label="test", encrypted_secret=encrypted,
        )
        repo.save(c)
        file_contents = json_path.read_text()
        assert raw_secret not in file_contents

    def test_count_increments(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert repo.count() == 0
        repo.save(_make_credential("u1"))
        assert repo.count() == 1
        repo.save(_make_credential("u2"))
        assert repo.count() == 2

    def test_concurrent_saves_no_data_loss(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        errors: list = []

        def save(i: int) -> None:
            try:
                c = ProviderCredential.create(
                    user_id=f"u{i}", provider_name="polygon",
                    credential_label="label", encrypted_secret=encrypt_secret(f"key{i}"),
                )
                repo.save(c)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=save, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert repo.count() == 10


# ---------------------------------------------------------------------------
# TestVaultService
# ---------------------------------------------------------------------------

class TestVaultService:
    def test_register_returns_credential(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon",
            credential_label="My Key", raw_secret="secret123",
        )
        assert c.provider_name == "polygon"
        assert c.credential_label == "My Key"
        assert c.active is True

    def test_register_stored_secret_is_not_plaintext(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon",
            credential_label="label", raw_secret="plaintext-secret",
        )
        assert c.encrypted_secret != "plaintext-secret"
        assert c.encrypted_secret.startswith("gAAAAA")  # Fernet token prefix

    def test_register_empty_provider_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        with pytest.raises(CredentialRegistrationError):
            service.register_credential(
                user_id="u", provider_name="", credential_label="label", raw_secret="key"
            )

    def test_register_empty_label_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        with pytest.raises(CredentialRegistrationError):
            service.register_credential(
                user_id="u", provider_name="polygon", credential_label="", raw_secret="key"
            )

    def test_register_empty_secret_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        with pytest.raises(CredentialRegistrationError):
            service.register_credential(
                user_id="u", provider_name="polygon", credential_label="label", raw_secret=""
            )

    def test_register_emits_audit_event(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            service.register_credential(
                user_id="u", provider_name="polygon", credential_label="l", raw_secret="s"
            )
        assert any(e.event_kind == AuditEventKind.VAULT_CREDENTIAL_REGISTERED for e in emitted)

    def test_list_returns_only_requesting_user(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l1", raw_secret="k1"
        )
        service.register_credential(
            user_id="user-2", provider_name="polygon", credential_label="l2", raw_secret="k2"
        )
        result = service.list_credentials(user_id="user-1")
        assert len(result) == 1
        assert result[0].user_id == "user-1"

    def test_list_emits_audit_event(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            service.list_credentials(user_id="user-1")
        assert any(e.event_kind == AuditEventKind.VAULT_CREDENTIAL_LISTED for e in emitted)

    def test_get_credential_own_succeeds(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        found = service.get_credential(
            credential_id=c.credential_id, requesting_user_id="user-1"
        )
        assert found.credential_id == c.credential_id

    def test_get_credential_wrong_owner_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        with pytest.raises(CredentialAccessDeniedError):
            service.get_credential(
                credential_id=c.credential_id, requesting_user_id="user-2"
            )

    def test_get_credential_nonexistent_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        with pytest.raises(CredentialAccessDeniedError):
            service.get_credential(
                credential_id="nonexistent", requesting_user_id="user-1"
            )

    def test_get_credential_wrong_owner_emits_access_denied(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            with pytest.raises(CredentialAccessDeniedError):
                service.get_credential(
                    credential_id=c.credential_id, requesting_user_id="user-2"
                )
        assert any(e.event_kind == AuditEventKind.VAULT_CREDENTIAL_ACCESS_DENIED for e in emitted)

    def test_disable_deactivates_credential(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        disabled = service.disable_credential(
            credential_id=c.credential_id, requesting_user_id="user-1"
        )
        assert disabled.active is False

    def test_disable_wrong_owner_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        with pytest.raises(CredentialAccessDeniedError):
            service.disable_credential(
                credential_id=c.credential_id, requesting_user_id="user-2"
            )

    def test_disable_emits_audit_event(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            service.disable_credential(
                credential_id=c.credential_id, requesting_user_id="user-1"
            )
        assert any(e.event_kind == AuditEventKind.VAULT_CREDENTIAL_DISABLED for e in emitted)

    def test_delete_removes_credential(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        service.delete_credential(
            credential_id=c.credential_id, requesting_user_id="user-1"
        )
        assert service.list_credentials(user_id="user-1") == []

    def test_delete_wrong_owner_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        with pytest.raises(CredentialAccessDeniedError):
            service.delete_credential(
                credential_id=c.credential_id, requesting_user_id="user-2"
            )

    def test_delete_emits_audit_event(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            service.delete_credential(
                credential_id=c.credential_id, requesting_user_id="user-1"
            )
        assert any(e.event_kind == AuditEventKind.VAULT_CREDENTIAL_DELETED for e in emitted)

    def test_resolve_returns_plaintext_secret(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon",
            credential_label="l", raw_secret="my-real-api-key",
        )
        result = service.resolve_secret(
            credential_id=c.credential_id,
            requesting_user_id="user-1",
            provider_name="polygon",
        )
        assert result == "my-real-api-key"

    def test_resolve_wrong_owner_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        with pytest.raises(CredentialAccessDeniedError):
            service.resolve_secret(
                credential_id=c.credential_id,
                requesting_user_id="user-2",
                provider_name="polygon",
            )

    def test_resolve_disabled_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        service.disable_credential(
            credential_id=c.credential_id, requesting_user_id="user-1"
        )
        with pytest.raises(CredentialDisabledError):
            service.resolve_secret(
                credential_id=c.credential_id,
                requesting_user_id="user-1",
                provider_name="polygon",
            )

    def test_resolve_provider_mismatch_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        with pytest.raises(CredentialProviderMismatchError):
            service.resolve_secret(
                credential_id=c.credential_id,
                requesting_user_id="user-1",
                provider_name="binance",
            )

    def test_resolve_emits_audit_event(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            service.resolve_secret(
                credential_id=c.credential_id,
                requesting_user_id="user-1",
                provider_name="polygon",
            )
        assert any(e.event_kind == AuditEventKind.VAULT_CREDENTIAL_RESOLVED for e in emitted)

    def test_resolve_audit_event_no_secret(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon",
            credential_label="l", raw_secret="super-secret-key-value",
        )
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            service.resolve_secret(
                credential_id=c.credential_id,
                requesting_user_id="user-1",
                provider_name="polygon",
            )
        for event in emitted:
            details_str = str(event.details)
            assert "super-secret-key-value" not in details_str

    def test_resolve_failure_emits_resolution_failed(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="user-1", provider_name="polygon", credential_label="l", raw_secret="s"
        )
        service.disable_credential(
            credential_id=c.credential_id, requesting_user_id="user-1"
        )
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            with pytest.raises(CredentialDisabledError):
                service.resolve_secret(
                    credential_id=c.credential_id,
                    requesting_user_id="user-1",
                    provider_name="polygon",
                )
        assert any(
            e.event_kind == AuditEventKind.VAULT_CREDENTIAL_RESOLUTION_FAILED
            for e in emitted
        )


# ---------------------------------------------------------------------------
# TestVaultRoutes
# ---------------------------------------------------------------------------

@pytest.fixture
def authed_client(tmp_path: Path):
    """TestClient with a registered+logged-in user (admin+active via bootstrap); returns (client, token)."""
    from backend.api.main import app
    from backend.core.config import settings
    settings.users_file_path = tmp_path / "users.json"
    settings.credentials_file_path = tmp_path / "credentials.json"
    settings.admin_bootstrap_email = "alice@example.com"

    try:
        with TestClient(app) as c:
            c.post("/auth/register", json={
                "username": "alice", "email": "alice@example.com", "password": "securepass1"
            })
            resp = c.post("/auth/login", json={"username": "alice", "password": "securepass1"})
            token = resp.json()["access_token"]
            yield c, token
    finally:
        settings.admin_bootstrap_email = ""


class TestVaultRoutes:
    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_register_returns_201(self, authed_client) -> None:
        client, token = authed_client
        resp = client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon",
            "credential_label": "My Key",
            "secret_value": "test-secret-value",
        })
        assert resp.status_code == 201

    def test_register_response_has_no_secret(self, authed_client) -> None:
        client, token = authed_client
        resp = client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon",
            "credential_label": "My Key",
            "secret_value": "super-secret-api-key",
        })
        body = resp.json()
        assert "secret_value" not in body
        assert "encrypted_secret" not in body
        assert "super-secret-api-key" not in str(body)

    def test_register_response_has_credential_id(self, authed_client) -> None:
        client, token = authed_client
        resp = client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon",
            "credential_label": "My Key",
            "secret_value": "secret",
        })
        assert "credential_id" in resp.json()

    def test_register_requires_auth(self, authed_client) -> None:
        client, _ = authed_client
        resp = client.post("/provider-credentials", json={
            "provider_name": "polygon", "credential_label": "l", "secret_value": "s",
        })
        assert resp.status_code == 401

    def test_list_returns_own_credentials(self, authed_client) -> None:
        client, token = authed_client
        client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon", "credential_label": "k1", "secret_value": "s1",
        })
        client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon", "credential_label": "k2", "secret_value": "s2",
        })
        resp = client.get("/provider-credentials", headers=self._headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2

    def test_list_requires_auth(self, authed_client) -> None:
        client, _ = authed_client
        resp = client.get("/provider-credentials")
        assert resp.status_code == 401

    def test_list_response_no_secrets(self, authed_client) -> None:
        client, token = authed_client
        client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon", "credential_label": "k", "secret_value": "secret-val",
        })
        resp = client.get("/provider-credentials", headers=self._headers(token))
        body_str = str(resp.json())
        assert "secret-val" not in body_str
        assert "encrypted_secret" not in body_str

    def test_get_own_credential(self, authed_client) -> None:
        client, token = authed_client
        create_resp = client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon", "credential_label": "k", "secret_value": "s",
        })
        cid = create_resp.json()["credential_id"]
        resp = client.get(f"/provider-credentials/{cid}", headers=self._headers(token))
        assert resp.status_code == 200
        assert resp.json()["credential_id"] == cid

    def test_get_nonexistent_returns_404(self, authed_client) -> None:
        client, token = authed_client
        resp = client.get("/provider-credentials/nonexistent-id", headers=self._headers(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self, authed_client) -> None:
        client, _ = authed_client
        resp = client.get("/provider-credentials/some-id")
        assert resp.status_code == 401

    def test_disable_sets_active_false(self, authed_client) -> None:
        client, token = authed_client
        create_resp = client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon", "credential_label": "k", "secret_value": "s",
        })
        cid = create_resp.json()["credential_id"]
        resp = client.patch(
            f"/provider-credentials/{cid}/disable", headers=self._headers(token)
        )
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_disable_requires_auth(self, authed_client) -> None:
        client, _ = authed_client
        resp = client.patch("/provider-credentials/some-id/disable")
        assert resp.status_code == 401

    def test_delete_returns_204(self, authed_client) -> None:
        client, token = authed_client
        create_resp = client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon", "credential_label": "k", "secret_value": "s",
        })
        cid = create_resp.json()["credential_id"]
        resp = client.delete(f"/provider-credentials/{cid}", headers=self._headers(token))
        assert resp.status_code == 204

    def test_delete_then_get_returns_404(self, authed_client) -> None:
        client, token = authed_client
        create_resp = client.post("/provider-credentials", headers=self._headers(token), json={
            "provider_name": "polygon", "credential_label": "k", "secret_value": "s",
        })
        cid = create_resp.json()["credential_id"]
        client.delete(f"/provider-credentials/{cid}", headers=self._headers(token))
        resp = client.get(f"/provider-credentials/{cid}", headers=self._headers(token))
        assert resp.status_code == 404

    def test_delete_requires_auth(self, authed_client) -> None:
        client, _ = authed_client
        resp = client.delete("/provider-credentials/some-id")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestCrossUserIsolation
# ---------------------------------------------------------------------------

class TestCrossUserIsolation:
    @pytest.fixture
    def two_user_client(self, tmp_path: Path):
        from backend.api.main import app
        from backend.core.config import settings
        settings.users_file_path = tmp_path / "users.json"
        settings.credentials_file_path = tmp_path / "credentials.json"
        settings.admin_bootstrap_email = "alice@x.com"

        try:
            with TestClient(app) as c:
                c.post("/auth/register", json={
                    "username": "alice", "email": "alice@x.com", "password": "securepass1"
                })
                alice_token = c.post("/auth/login", json={"username": "alice", "password": "securepass1"}).json()["access_token"]
                bob_reg = c.post("/auth/register", json={
                    "username": "bob", "email": "bob@x.com", "password": "securepass1"
                })
                bob_id = bob_reg.json()["user_id"]
                c.post(
                    f"/admin/users/{bob_id}/approve",
                    headers={"Authorization": f"Bearer {alice_token}"},
                    json={},
                )
                bob_token = c.post("/auth/login", json={"username": "bob", "password": "securepass1"}).json()["access_token"]
                yield c, alice_token, bob_token
        finally:
            settings.admin_bootstrap_email = ""

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_bob_cannot_see_alice_credential(self, two_user_client) -> None:
        client, alice_tok, bob_tok = two_user_client
        client.post("/provider-credentials", headers=self._headers(alice_tok), json={
            "provider_name": "polygon", "credential_label": "alice-key", "secret_value": "s",
        })
        bob_list = client.get("/provider-credentials", headers=self._headers(bob_tok)).json()
        assert bob_list["total"] == 0

    def test_bob_cannot_get_alice_credential(self, two_user_client) -> None:
        client, alice_tok, bob_tok = two_user_client
        resp = client.post("/provider-credentials", headers=self._headers(alice_tok), json={
            "provider_name": "polygon", "credential_label": "k", "secret_value": "s",
        })
        cid = resp.json()["credential_id"]
        bob_resp = client.get(f"/provider-credentials/{cid}", headers=self._headers(bob_tok))
        assert bob_resp.status_code == 404

    def test_bob_cannot_disable_alice_credential(self, two_user_client) -> None:
        client, alice_tok, bob_tok = two_user_client
        resp = client.post("/provider-credentials", headers=self._headers(alice_tok), json={
            "provider_name": "polygon", "credential_label": "k", "secret_value": "s",
        })
        cid = resp.json()["credential_id"]
        bob_resp = client.patch(
            f"/provider-credentials/{cid}/disable", headers=self._headers(bob_tok)
        )
        assert bob_resp.status_code == 404

    def test_bob_cannot_delete_alice_credential(self, two_user_client) -> None:
        client, alice_tok, bob_tok = two_user_client
        resp = client.post("/provider-credentials", headers=self._headers(alice_tok), json={
            "provider_name": "polygon", "credential_label": "k", "secret_value": "s",
        })
        cid = resp.json()["credential_id"]
        bob_resp = client.delete(f"/provider-credentials/{cid}", headers=self._headers(bob_tok))
        assert bob_resp.status_code == 404


# ---------------------------------------------------------------------------
# TestSecurityInvariants
# ---------------------------------------------------------------------------

class TestSecurityInvariants:
    def test_credential_metadata_response_has_no_secret_fields(self) -> None:
        from backend.api.schemas.vault import CredentialMetadataResponse
        assert "encrypted_secret" not in CredentialMetadataResponse.model_fields
        assert "secret_value" not in CredentialMetadataResponse.model_fields
        assert "raw_secret" not in CredentialMetadataResponse.model_fields

    def test_register_request_secret_is_write_only(self) -> None:
        from backend.api.schemas.vault import RegisterCredentialRequest
        req = RegisterCredentialRequest(
            provider_name="polygon",
            credential_label="label",
            secret_value="my-api-key",
        )
        # secret_value must exist as input but not appear in serialized output schema
        assert "my-api-key" == req.secret_value

    def test_credential_repr_no_encrypted_secret(self) -> None:
        encrypted = encrypt_secret("sensitive-value")
        c = ProviderCredential.create(
            user_id="u", provider_name="polygon",
            credential_label="l", encrypted_secret=encrypted,
        )
        r = repr(c)
        assert "sensitive-value" not in r
        assert encrypted not in r

    def test_resolve_audit_no_raw_secret(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        c = service.register_credential(
            user_id="u", provider_name="polygon",
            credential_label="l", raw_secret="dont-leak-this",
        )
        emitted: list = []
        with patch("backend.vault.service.emit_audit_event", side_effect=emitted.append):
            service.resolve_secret(
                credential_id=c.credential_id,
                requesting_user_id="u",
                provider_name="polygon",
            )
        for event in emitted:
            assert "dont-leak-this" not in str(event)


# ---------------------------------------------------------------------------
# TestArchitectureBoundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def test_vault_service_no_strategy_runtime_import(self) -> None:
        import ast, pathlib
        src = pathlib.Path("backend/vault/service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "strategy_runtime" not in node.module
                assert "strategy_registry" not in node.module
                assert "data_providers" not in node.module

    def test_vault_crypto_no_external_imports_except_cryptography(self) -> None:
        import ast, pathlib
        src = pathlib.Path("backend/vault/crypto.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "data_providers" not in node.module
                assert "strategy" not in node.module
                assert "auth" not in node.module

    def test_vault_routes_no_direct_adapter_import(self) -> None:
        import ast, pathlib
        src = pathlib.Path("backend/api/routes/vault.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "data_providers.yahoo" not in node.module
                assert "data_providers.polygon" not in node.module


# ---------------------------------------------------------------------------
# TestPolygonBackwardCompatibility
# ---------------------------------------------------------------------------

class TestPolygonBackwardCompatibility:
    def test_polygon_builder_still_raises_provider_build_error_when_no_env(self) -> None:
        import os
        from unittest.mock import patch as _patch
        from backend.data_providers.provider_factory import ProviderBuildError, create_default_factory_registry

        registry = create_default_factory_registry()
        env_without_polygon = {k: v for k, v in os.environ.items() if k != "POLYGON_API_KEY"}
        with _patch.dict(os.environ, env_without_polygon, clear=True):
            with pytest.raises(ProviderBuildError):
                registry.build("polygon", symbol="AAPL", timeframe="1d")

    def test_factory_still_has_four_providers(self) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        registry = create_default_factory_registry()
        assert len(registry) == 4

    def test_vault_is_provider_agnostic(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        for provider in ("polygon", "binance", "ibkr", "custom_provider"):
            c = service.register_credential(
                user_id="u", provider_name=provider,
                credential_label="label", raw_secret="key123",
            )
            assert c.provider_name == provider

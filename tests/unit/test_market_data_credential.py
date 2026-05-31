"""
Phase 3J — Provider Credential Resolver Refactor (Polygon → User-Owned Credentials)

Tests cover:
  - _resolve_provider_api_key(): vault path, None path, auth missing, access denied,
    disabled, provider mismatch, decryption failure
  - _build_polygon_adapter(): accepts api_key kwarg (vault path), falls back to ENV
  - fetch_ohlcv(): credential_id + user_id forwarded; credential errors → MarketDataError
  - Route GET /market-data/ohlcv:
      - credential_id without auth → 401
      - credential_id with auth + vault success → provider build called correctly
      - no credential_id → backward compat (no auth required)
      - wrong-user credential → 400
      - disabled credential → 400
      - provider mismatch → 400
  - Ownership enforcement: cross-user credential denial at the market data layer
  - No raw secret in route responses or error details
  - Backward compatibility: yahoo, csv, parquet unaffected
  - Architecture boundary: market_data_service does not import concrete adapters
  - get_optional_current_user: returns None when no token; returns User when valid
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.services.market_data_service import (
    MarketDataError,
    _resolve_provider_api_key,
)
from backend.auth.entitlement import require_active_subscription
from backend.vault.crypto import encrypt_secret
from backend.vault.models import ProviderCredential
from backend.vault.repository import CredentialRepository
from backend.vault.service import VaultService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault_service(tmp_path: Path) -> VaultService:
    return VaultService(CredentialRepository(tmp_path / "creds.json"))


def _register_polygon_cred(
    service: VaultService, user_id: str = "user-1", raw_secret: str = "my-polygon-key"
) -> ProviderCredential:
    return service.register_credential(
        user_id=user_id,
        provider_name="polygon",
        credential_label="Test Key",
        raw_secret=raw_secret,
    )


# ---------------------------------------------------------------------------
# TestResolveProviderApiKey
# ---------------------------------------------------------------------------

class TestResolveProviderApiKey:
    """
    These tests exercise _resolve_provider_api_key() through the real vault stack
    by pointing settings.credentials_file_path at a tmp directory.  This gives
    accurate coverage of the full lazy-import chain without fighting Mock.
    """

    @pytest.fixture(autouse=True)
    def _point_vault_to_tmp(self, tmp_path: Path):
        from backend.core.config import settings
        settings.credentials_file_path = tmp_path / "creds.json"
        yield

    def _setup(self, tmp_path: Path, raw_secret: str = "my-polygon-key", user_id: str = "user-1"):
        from backend.core.config import settings
        service = _make_vault_service(tmp_path)
        # Point settings to the same file the service writes to
        settings.credentials_file_path = tmp_path / "creds.json"
        return service, _register_polygon_cred(service, user_id=user_id, raw_secret=raw_secret)

    def test_no_credential_id_returns_none(self) -> None:
        result = _resolve_provider_api_key(
            provider="polygon", credential_id=None, user_id="u"
        )
        assert result is None

    def test_empty_credential_id_returns_none(self) -> None:
        result = _resolve_provider_api_key(
            provider="polygon", credential_id="", user_id="u"
        )
        assert result is None

    def test_credential_id_no_user_raises(self) -> None:
        with pytest.raises(MarketDataError, match="Authentication required"):
            _resolve_provider_api_key(
                provider="polygon", credential_id="some-cred-id", user_id=None
            )

    def test_vault_path_returns_plaintext(self, tmp_path: Path) -> None:
        service, cred = self._setup(tmp_path, raw_secret="actual-api-key")
        result = _resolve_provider_api_key(
            provider="polygon",
            credential_id=cred.credential_id,
            user_id="user-1",
        )
        assert result == "actual-api-key"

    def test_wrong_user_raises_market_data_error(self, tmp_path: Path) -> None:
        service, cred = self._setup(tmp_path, user_id="user-1")
        with pytest.raises(MarketDataError, match="not found or access denied"):
            _resolve_provider_api_key(
                provider="polygon",
                credential_id=cred.credential_id,
                user_id="user-2",
            )

    def test_disabled_credential_raises(self, tmp_path: Path) -> None:
        service, cred = self._setup(tmp_path)
        service.disable_credential(
            credential_id=cred.credential_id, requesting_user_id="user-1"
        )
        with pytest.raises(MarketDataError, match="disabled"):
            _resolve_provider_api_key(
                provider="polygon",
                credential_id=cred.credential_id,
                user_id="user-1",
            )

    def test_provider_mismatch_raises(self, tmp_path: Path) -> None:
        service, cred = self._setup(tmp_path)
        with pytest.raises(MarketDataError, match="not registered for this provider"):
            _resolve_provider_api_key(
                provider="binance",  # mismatch — cred is for polygon
                credential_id=cred.credential_id,
                user_id="user-1",
            )

    def test_crypto_failure_raises(self, tmp_path: Path) -> None:
        from backend.vault.crypto import VaultCryptoError
        service, cred = self._setup(tmp_path)
        # Patch decrypt at the call site inside vault/service.py
        with patch("backend.vault.service.decrypt_secret", side_effect=VaultCryptoError("bad")):
            with pytest.raises(MarketDataError, match="could not be resolved"):
                _resolve_provider_api_key(
                    provider="polygon",
                    credential_id=cred.credential_id,
                    user_id="user-1",
                )

    def test_error_message_no_secret(self, tmp_path: Path) -> None:
        service, cred = self._setup(tmp_path)
        try:
            _resolve_provider_api_key(
                provider="polygon",
                credential_id=cred.credential_id,
                user_id="wrong-user",
            )
        except MarketDataError as exc:
            assert "my-polygon-key" not in str(exc)
            assert cred.encrypted_secret not in str(exc)


# ---------------------------------------------------------------------------
# TestPolygonBuilderVaultPath
# ---------------------------------------------------------------------------

class TestPolygonBuilderVaultPath:
    def test_api_key_kwarg_bypasses_env(self) -> None:
        from backend.data_providers.provider_factory import _build_polygon_adapter

        with patch("backend.data_providers.polygon.adapter.PolygonProviderAdapter") as mock_cls:
            mock_cls.return_value = MagicMock()
            # No POLYGON_API_KEY in env — but api_key is provided directly
            env_without_key = {k: v for k, v in os.environ.items() if k != "POLYGON_API_KEY"}
            with patch.dict(os.environ, env_without_key, clear=True):
                result = _build_polygon_adapter(
                    symbol="AAPL",
                    timeframe="1d",
                    api_key="pre-resolved-secret",
                )
            # Verify PolygonProviderAdapter was constructed with the provided key
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["api_key"] == "pre-resolved-secret"

    def test_no_api_key_falls_back_to_env(self) -> None:
        from backend.data_providers.provider_factory import ProviderBuildError, _build_polygon_adapter

        env_without_key = {k: v for k, v in os.environ.items() if k != "POLYGON_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            with pytest.raises(ProviderBuildError):
                _build_polygon_adapter(symbol="AAPL", timeframe="1d")

    def test_env_fallback_disabled_by_default(self) -> None:
        from backend.data_providers.provider_factory import ProviderBuildError, _build_polygon_adapter

        with patch.dict(os.environ, {"POLYGON_API_KEY": "env-api-key"}):
            with pytest.raises(ProviderBuildError, match="ENV fallback is disabled"):
                _build_polygon_adapter(symbol="AAPL", timeframe="1d")

    def test_env_fallback_uses_env_key_when_enabled(self) -> None:
        from backend.data_providers.provider_factory import _build_polygon_adapter

        with patch("backend.data_providers.provider_factory.settings") as mock_settings:
            mock_settings.polygon_allow_env_fallback = True
            with patch("backend.data_providers.polygon.adapter.PolygonProviderAdapter") as mock_cls:
                mock_cls.return_value = MagicMock()
                with patch.dict(os.environ, {"POLYGON_API_KEY": "env-api-key"}):
                    _build_polygon_adapter(symbol="AAPL", timeframe="1d")
                call_kwargs = mock_cls.call_args.kwargs
                assert call_kwargs["api_key"] == "env-api-key"

    def test_factory_build_forwards_api_key(self) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry

        registry = create_default_factory_registry()
        with patch("backend.data_providers.polygon.adapter.PolygonProviderAdapter") as mock_cls:
            mock_cls.return_value = MagicMock(provider_name="polygon")
            with patch.dict(os.environ, {"POLYGON_API_KEY": "env-key"}):
                adapter = registry.build(
                    "polygon",
                    symbol="AAPL",
                    timeframe="1d",
                    api_key="vault-resolved-key",
                )
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["api_key"] == "vault-resolved-key"

    def test_other_providers_ignore_api_key_kwarg(self) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry

        registry = create_default_factory_registry()
        # Yahoo adapter accepts **_ignored — passing api_key must not break it
        adapter = registry.build(
            "yahoo",
            symbol="AAPL",
            timeframe="1d",
            api_key="should-be-ignored",
        )
        assert adapter.provider_name == "yahoo"


# ---------------------------------------------------------------------------
# TestGetOptionalCurrentUser
# ---------------------------------------------------------------------------

class TestGetOptionalCurrentUser:
    def test_no_token_returns_none(self, tmp_path: Path) -> None:
        from backend.auth.dependencies import get_optional_current_user
        result = get_optional_current_user(credentials=None, repository=MagicMock(return_value=None))
        assert result is None

    def test_valid_token_returns_user(self, tmp_path: Path) -> None:
        from backend.auth.dependencies import get_optional_current_user
        from backend.auth.tokens import create_access_token
        from backend.auth.models import User
        from backend.auth.password import hash_password
        from fastapi.security import HTTPAuthorizationCredentials

        user = User.create(username="alice", email="a@b.com", password_hash=hash_password("pw"))
        repo = CredentialRepository.__new__(CredentialRepository)  # skip __init__
        from backend.auth.repository import UserRepository
        user_repo = UserRepository.__new__(UserRepository)
        user_repo._users = {user.user_id: user}
        user_repo._lock = __import__("threading").Lock()

        token = create_access_token(username="alice", user_id=user.user_id)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        result = get_optional_current_user(credentials=creds, repository=user_repo)
        assert result is not None
        assert result.username == "alice"

    def test_expired_token_returns_none(self, tmp_path: Path) -> None:
        from backend.auth.dependencies import get_optional_current_user
        from backend.auth.repository import UserRepository
        from backend.core.config import settings
        from datetime import timedelta
        import jwt
        from fastapi.security import HTTPAuthorizationCredentials

        payload = {
            "sub": "alice", "user_id": "uid-x",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired = jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired)
        result = get_optional_current_user(credentials=creds, repository=MagicMock())
        assert result is None

    def test_tampered_token_returns_none(self) -> None:
        from backend.auth.dependencies import get_optional_current_user
        from backend.auth.tokens import create_access_token
        from fastapi.security import HTTPAuthorizationCredentials

        token = create_access_token(username="alice", user_id="uid-x")
        tampered = token[:-4] + "xxxx"
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=tampered)
        result = get_optional_current_user(credentials=creds, repository=MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# TestMarketDataRouteCredentialFlow
# ---------------------------------------------------------------------------

@pytest.fixture
def market_client(tmp_path: Path):
    """TestClient with registered/logged-in user (auto-promoted to admin+active via bootstrap)
    and vault credential store isolated to tmp_path."""
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
            login_resp = c.post("/auth/login", json={"username": "alice", "password": "securepass1"})
            token = login_resp.json()["access_token"]
            yield c, token, tmp_path
    finally:
        settings.admin_bootstrap_email = ""


class TestMarketDataRouteCredentialFlow:
    _BASE = "/market-data/ohlcv"
    _PARAMS = "?provider=polygon&symbol=AAPL&timeframe=1d&start=2024-01-01T00:00:00Z&end=2024-01-31T00:00:00Z"

    def setup_method(self):
        # Remove the default active-user conftest override so real auth runs.
        # Tests that supply a valid Bearer token will still authenticate correctly;
        # tests that send no token will receive 401 as expected.
        app.dependency_overrides.pop(require_active_subscription, None)

    def teardown_method(self):
        app.dependency_overrides.pop(require_active_subscription, None)

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_credential_id_without_auth_returns_401(self, market_client) -> None:
        client, _, _ = market_client
        resp = client.get(f"{self._BASE}{self._PARAMS}&credential_id=some-id")
        assert resp.status_code == 401

    def test_no_auth_ohlcv_returns_401(self, market_client) -> None:
        client, _, _ = market_client
        # Phase 3P-A: all OHLCV fetches require active subscription
        resp = client.get(
            "/market-data/ohlcv?provider=yahoo&symbol=AAPL&timeframe=1d"
            "&start=2024-01-01T00:00:00Z&end=2024-01-31T00:00:00Z"
        )
        assert resp.status_code == 401

    def test_credential_id_with_valid_auth_and_vault_credential(self, market_client) -> None:
        client, token, tmp_path = market_client
        # Register a vault credential
        cred_resp = client.post(
            "/provider-credentials",
            headers=self._headers(token),
            json={"provider_name": "polygon", "credential_label": "key", "secret_value": "test-api-key"},
        )
        cred_id = cred_resp.json()["credential_id"]

        # Mock the Polygon adapter fetch so we don't need a real API key
        with patch("backend.data_providers.polygon.adapter.PolygonProviderAdapter.fetch", return_value=[]):
            resp = client.get(
                f"{self._BASE}{self._PARAMS}&credential_id={cred_id}",
                headers=self._headers(token),
            )
        assert resp.status_code == 200
        assert resp.json()["candle_count"] == 0

    def test_credential_id_vault_path_no_raw_secret_in_response(self, market_client) -> None:
        client, token, tmp_path = market_client
        raw_secret = "super-secret-polygon-key"
        cred_resp = client.post(
            "/provider-credentials",
            headers=self._headers(token),
            json={"provider_name": "polygon", "credential_label": "k", "secret_value": raw_secret},
        )
        cred_id = cred_resp.json()["credential_id"]

        with patch("backend.data_providers.polygon.adapter.PolygonProviderAdapter.fetch", return_value=[]):
            resp = client.get(
                f"{self._BASE}{self._PARAMS}&credential_id={cred_id}",
                headers=self._headers(token),
            )
        assert raw_secret not in str(resp.json())

    def test_wrong_user_credential_returns_400(self, market_client) -> None:
        client, alice_token, tmp_path = market_client
        # Register bob (pending by default)
        bob_reg = client.post("/auth/register", json={
            "username": "bob", "email": "bob@example.com", "password": "securepass1"
        })
        bob_id = bob_reg.json()["user_id"]
        bob_token = client.post("/auth/login", json={"username": "bob", "password": "securepass1"}).json()["access_token"]

        # Alice (admin) approves Bob so he can use vault
        client.post(
            f"/admin/users/{bob_id}/approve",
            headers=self._headers(alice_token),
            json={},
        )

        # Bob registers a credential
        cred_resp = client.post(
            "/provider-credentials",
            headers={"Authorization": f"Bearer {bob_token}"},
            json={"provider_name": "polygon", "credential_label": "k", "secret_value": "s"},
        )
        bob_cred_id = cred_resp.json()["credential_id"]

        # Alice tries to use Bob's credential — should be denied
        resp = client.get(
            f"{self._BASE}{self._PARAMS}&credential_id={bob_cred_id}",
            headers=self._headers(alice_token),
        )
        assert resp.status_code == 400
        assert "access denied" in resp.json()["detail"].lower() or "not found" in resp.json()["detail"].lower()

    def test_disabled_credential_returns_400(self, market_client) -> None:
        client, token, tmp_path = market_client
        cred_resp = client.post(
            "/provider-credentials",
            headers=self._headers(token),
            json={"provider_name": "polygon", "credential_label": "k", "secret_value": "s"},
        )
        cred_id = cred_resp.json()["credential_id"]
        client.patch(f"/provider-credentials/{cred_id}/disable", headers=self._headers(token))

        resp = client.get(
            f"{self._BASE}{self._PARAMS}&credential_id={cred_id}",
            headers=self._headers(token),
        )
        assert resp.status_code == 400
        assert "disabled" in resp.json()["detail"].lower()

    def test_wrong_provider_credential_returns_400(self, market_client) -> None:
        client, token, tmp_path = market_client
        # Register a binance credential, try to use for polygon
        cred_resp = client.post(
            "/provider-credentials",
            headers=self._headers(token),
            json={"provider_name": "binance", "credential_label": "k", "secret_value": "s"},
        )
        cred_id = cred_resp.json()["credential_id"]

        resp = client.get(
            f"{self._BASE}{self._PARAMS}&credential_id={cred_id}",
            headers=self._headers(token),
        )
        assert resp.status_code == 400
        assert "not registered for this provider" in resp.json()["detail"].lower()

    def test_polygon_env_fallback_works_when_enabled(self, market_client) -> None:
        """No credential_id + polygon_allow_env_fallback=True → factory uses ENV resolver."""
        client, token, _ = market_client
        with patch("backend.data_providers.provider_factory.settings") as mock_settings:
            mock_settings.polygon_allow_env_fallback = True
            with patch(
                "backend.data_providers.polygon.adapter.PolygonProviderAdapter.fetch",
                return_value=[],
            ), patch.dict(os.environ, {"POLYGON_API_KEY": "env-test-key"}):
                resp = client.get(f"{self._BASE}{self._PARAMS}", headers=self._headers(token))
        assert resp.status_code == 200

    def test_polygon_env_fallback_disabled_by_default(self, market_client) -> None:
        """No credential_id + polygon_allow_env_fallback=False (default) → 400."""
        client, token, _ = market_client
        with patch.dict(os.environ, {"POLYGON_API_KEY": "env-test-key"}):
            resp = client.get(f"{self._BASE}{self._PARAMS}", headers=self._headers(token))
        assert resp.status_code == 400

    def test_ohlcv_without_auth_returns_401(self, market_client) -> None:
        """Phase 3P-A: all OHLCV fetches require active subscription; unauthenticated → 401."""
        client, _, _ = market_client
        with patch(
            "backend.data_providers.polygon.adapter.PolygonProviderAdapter.fetch",
            return_value=[],
        ), patch.dict(os.environ, {"POLYGON_API_KEY": "env-test-key"}):
            resp = client.get(f"{self._BASE}{self._PARAMS}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestFetchOhlcvCredentialIntegration
# ---------------------------------------------------------------------------

class TestFetchOhlcvCredentialIntegration:
    """Unit-level tests for market_data_service.fetch_ohlcv() credential forwarding."""

    def _make_mock_factory(self, api_key_received: list) -> MagicMock:
        factory = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.fetch.return_value = []

        def capturing_build(provider_name, **kwargs):
            api_key_received.append(kwargs.get("api_key"))
            return mock_adapter

        factory.build.side_effect = capturing_build
        return factory

    def test_fetch_ohlcv_passes_api_key_to_factory(self, tmp_path: Path) -> None:
        from backend.api.services.market_data_service import fetch_ohlcv
        from backend.core.config import settings

        settings.credentials_file_path = tmp_path / "creds.json"
        service = _make_vault_service(tmp_path)
        cred = _register_polygon_cred(service, raw_secret="resolved-key")

        received: list = []
        factory = self._make_mock_factory(received)

        with patch("backend.api.services.market_data_service.OHLCVService") as mock_ohlcv_svc:
            mock_ohlcv_svc.return_value.get_ohlcv.return_value = []
            fetch_ohlcv(
                provider="polygon",
                symbol="AAPL",
                asset_class="equity",
                exchange="NASDAQ",
                timeframe="1d",
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 31, tzinfo=timezone.utc),
                storage_path=tmp_path,
                factory=factory,
                credential_id=cred.credential_id,
                user_id="user-1",
            )

        assert received == ["resolved-key"]

    def test_fetch_ohlcv_no_credential_passes_none_api_key(self, tmp_path: Path) -> None:
        from backend.api.services.market_data_service import fetch_ohlcv

        received: list = []
        factory = self._make_mock_factory(received)

        with patch("backend.api.services.market_data_service.OHLCVService") as mock_svc:
            mock_svc.return_value.get_ohlcv.return_value = []
            fetch_ohlcv(
                provider="yahoo",
                symbol="AAPL",
                asset_class="equity",
                exchange="NASDAQ",
                timeframe="1d",
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 31, tzinfo=timezone.utc),
                storage_path=tmp_path,
                factory=factory,
            )

        assert received == [None]


# ---------------------------------------------------------------------------
# TestArchitectureBoundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def test_market_data_service_no_concrete_adapter_import(self) -> None:
        import ast, pathlib
        src = pathlib.Path("backend/api/services/market_data_service.py").read_text()
        tree = ast.parse(src)
        forbidden = "data_providers.yahoo"
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert forbidden not in node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert forbidden not in alias.name

    def test_market_data_service_no_polygon_adapter_import(self) -> None:
        import ast, pathlib
        src = pathlib.Path("backend/api/services/market_data_service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "data_providers.polygon" not in node.module

    def test_market_data_route_no_vault_import_at_module_level(self) -> None:
        import ast, pathlib
        src = pathlib.Path("backend/api/routes/market_data.py").read_text()
        tree = ast.parse(src)
        # Vault should not appear in top-level imports (it's fine inside functions)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module is None or "vault" not in node.module

    def test_backward_compat_factory_len_unchanged(self) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        assert len(create_default_factory_registry()) == 4

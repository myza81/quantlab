"""
Tests for Phase 3F — Security Baseline.

Covers:
  - CredentialSpec: construction, frozen, validation
  - EnvironmentCredentialResolver: resolve present/missing, safe error messages
  - MissingCredentialError: safe message invariant (no raw secret)
  - AuditEvent: construction, frozen, defaults
  - emit_audit_event: structured log output, no secrets in payload
  - Request validation: validate_date_range, validate_provider_type, validate_catalog_id_format
  - Safe error policy: CatalogFetchError messages do not expose file paths
  - Audit hook integration: catalog_service emits audit events on register/remove/fetch
  - Architecture boundaries:
      - strategies/ directory does not import backend.core.credentials
      - API schemas contain no credential fields
      - LocalDatasetEntry (catalog) stores no raw credentials
      - catalog_service.py imports no yahoo adapter
      - credentials.py and audit.py import no provider-specific modules
  - Backward compatibility: existing providers still work
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.core.audit import AuditEvent, AuditEventKind, emit_audit_event
from backend.core.credentials import (
    CredentialResolutionError,
    CredentialSource,
    CredentialSpec,
    EnvironmentCredentialResolver,
    MissingCredentialError,
)
from backend.core.request_validation import (
    ALLOWED_CATALOG_PROVIDER_TYPES,
    validate_catalog_id_format,
    validate_date_range,
    validate_provider_type,
    validate_symbol,
)


# ---------------------------------------------------------------------------
# TestCredentialSpec
# ---------------------------------------------------------------------------

class TestCredentialSpec:
    def test_construction(self) -> None:
        spec = CredentialSpec(
            provider_name="binance",
            credential_key="BINANCE_API_KEY",
        )
        assert spec.provider_name == "binance"
        assert spec.credential_key == "BINANCE_API_KEY"
        assert spec.source_type == CredentialSource.ENV_VAR

    def test_frozen(self) -> None:
        spec = CredentialSpec(
            provider_name="binance",
            credential_key="BINANCE_API_KEY",
        )
        with pytest.raises(Exception):
            spec.provider_name = "other"  # type: ignore[misc]

    def test_empty_provider_name_raises(self) -> None:
        with pytest.raises(ValueError):
            CredentialSpec(provider_name="", credential_key="KEY")

    def test_empty_credential_key_raises(self) -> None:
        with pytest.raises(ValueError):
            CredentialSpec(provider_name="binance", credential_key="")

    def test_whitespace_provider_name_raises(self) -> None:
        with pytest.raises(ValueError):
            CredentialSpec(provider_name="  ", credential_key="KEY")

    def test_description_default_empty(self) -> None:
        spec = CredentialSpec(provider_name="p", credential_key="K")
        assert spec.description == ""

    def test_description_stored(self) -> None:
        spec = CredentialSpec(
            provider_name="p", credential_key="K", description="API key"
        )
        assert spec.description == "API key"

    def test_source_type_default_env_var(self) -> None:
        spec = CredentialSpec(provider_name="p", credential_key="K")
        assert spec.source_type == CredentialSource.ENV_VAR

    def test_spec_safe_to_serialize(self) -> None:
        spec = CredentialSpec(provider_name="binance", credential_key="BINANCE_API_KEY")
        dumped = spec.model_dump()
        assert "provider_name" in dumped
        assert "credential_key" in dumped
        assert "BINANCE_SECRET_VALUE" not in str(dumped)


# ---------------------------------------------------------------------------
# TestEnvironmentCredentialResolver
# ---------------------------------------------------------------------------

class TestEnvironmentCredentialResolver:
    def test_resolve_present_env_var(self) -> None:
        spec = CredentialSpec(provider_name="test_prov", credential_key="TEST_SECRET_KEY")
        resolver = EnvironmentCredentialResolver()
        with patch.dict(os.environ, {"TEST_SECRET_KEY": "super_secret_value_xyz"}):
            value = resolver.resolve(spec)
        assert value == "super_secret_value_xyz"

    def test_resolve_missing_raises_missing_credential_error(self) -> None:
        spec = CredentialSpec(provider_name="test_prov", credential_key="NONEXISTENT_KEY_ABC")
        resolver = EnvironmentCredentialResolver()
        env_without_key = {k: v for k, v in os.environ.items() if k != "NONEXISTENT_KEY_ABC"}
        with patch.dict(os.environ, env_without_key, clear=True):
            with pytest.raises(MissingCredentialError):
                resolver.resolve(spec)

    def test_missing_error_is_credential_resolution_error(self) -> None:
        spec = CredentialSpec(provider_name="test_prov", credential_key="NONEXISTENT_KEY_ABC")
        resolver = EnvironmentCredentialResolver()
        env_without_key = {k: v for k, v in os.environ.items() if k != "NONEXISTENT_KEY_ABC"}
        with patch.dict(os.environ, env_without_key, clear=True):
            with pytest.raises(CredentialResolutionError):
                resolver.resolve(spec)

    def test_missing_error_message_does_not_contain_secret(self) -> None:
        secret_value = "VERY_SECRET_PASSWORD_12345"
        spec = CredentialSpec(provider_name="test_prov", credential_key="TEST_SECRET_KEY_B")
        resolver = EnvironmentCredentialResolver()
        with patch.dict(os.environ, {"TEST_SECRET_KEY_B": secret_value}):
            value = resolver.resolve(spec)
        assert value == secret_value

        env_without_key = {k: v for k, v in os.environ.items() if k != "TEST_SECRET_KEY_B"}
        with patch.dict(os.environ, env_without_key, clear=True):
            try:
                resolver.resolve(spec)
            except MissingCredentialError as exc:
                assert secret_value not in str(exc)
                assert "TEST_SECRET_KEY_B" not in str(exc)

    def test_missing_error_message_contains_provider_name(self) -> None:
        spec = CredentialSpec(provider_name="binance", credential_key="NONEXISTENT_KEY_ABC")
        resolver = EnvironmentCredentialResolver()
        env_without_key = {k: v for k, v in os.environ.items() if k != "NONEXISTENT_KEY_ABC"}
        with patch.dict(os.environ, env_without_key, clear=True):
            with pytest.raises(MissingCredentialError, match="binance"):
                resolver.resolve(spec)

    def test_empty_env_var_raises(self) -> None:
        spec = CredentialSpec(provider_name="test_prov", credential_key="EMPTY_KEY_TEST")
        resolver = EnvironmentCredentialResolver()
        with patch.dict(os.environ, {"EMPTY_KEY_TEST": ""}):
            with pytest.raises(MissingCredentialError):
                resolver.resolve(spec)


# ---------------------------------------------------------------------------
# TestAuditEvent
# ---------------------------------------------------------------------------

class TestAuditEvent:
    def test_construction(self) -> None:
        event = AuditEvent(
            event_kind=AuditEventKind.DATASET_REGISTERED,
            provider_name="csv",
            details={"catalog_id": "abc"},
        )
        assert event.event_kind == AuditEventKind.DATASET_REGISTERED
        assert event.provider_name == "csv"
        assert event.details["catalog_id"] == "abc"

    def test_frozen(self) -> None:
        event = AuditEvent(event_kind=AuditEventKind.CREDENTIAL_MISSING)
        with pytest.raises(Exception):
            event.provider_name = "other"  # type: ignore[misc]

    def test_default_timestamp_utc(self) -> None:
        event = AuditEvent(event_kind=AuditEventKind.DATASET_REGISTERED)
        assert event.timestamp.tzinfo is not None

    def test_all_event_kinds_defined(self) -> None:
        expected = {
            "credential_resolution_attempt",
            "credential_missing",
            "dataset_registered",
            "dataset_removed",
            "provider_fetch_request",
            "catalog_ohlcv_fetch",
            # Phase 3H auth events
            "user_registered",
            "login_success",
            "login_failure",
            "invalid_token",
            "protected_route_denied",
            # Phase 3I vault events
            "vault_credential_registered",
            "vault_credential_resolved",
            "vault_credential_listed",
            "vault_credential_disabled",
            "vault_credential_deleted",
            "vault_credential_access_denied",
            "vault_credential_resolution_failed",
            # Phase 3L ownership events
            "draft_created",
            "draft_updated",
            "draft_deleted",
            "draft_archived",
            "draft_ownership_denied",
            "dataset_ownership_denied",
            "backtest_ownership_denied",
            # Phase 3P-A subscription / entitlement events
            "user_approved",
            "subscription_activated",
            "subscription_expired",
            "subscription_suspended",
            "entitlement_denied",
            # Phase 3P-B.1 governance safety events
            "expiry_updated",
            "admin_self_suspension_denied",
            "last_admin_suspension_denied",
            # Phase 3P-D superadmin & role management events
            "role_promoted",
            "role_demoted",
            "last_superadmin_protection_denied",
            "unauthorized_role_change_attempt",
            # Phase 3S-B hardening events
            "oversized_payload_rejected",
            "lifecycle_transition_denied",
            "polygon_env_fallback_used",
            # Phase 4C.2 — Forward Testing session lifecycle events (FT_)
            "ft_session_created",
            "ft_session_activated",
            "ft_activation_denied",
            "ft_session_paused",
            "ft_session_paused_provider_failure",
            "ft_session_resumed",
            "ft_session_completed",
            "ft_session_failed",
            "ft_session_terminated",
            "ft_invalid_transition_denied",
            "ft_signal_generated",
            "ft_signal_suppressed",
            "ft_poll_completed",
            "ft_provider_failure",
            "ft_gap_detected",
            "ft_catchup_started",
            "ft_catchup_threshold_exceeded",
            "ft_session_exported",
            "ft_session_reviewed",
            # Phase 4C.2 — Governance promotion events (GOV_)
            "gov_promotion_requested",
            "gov_promotion_review_started",
            "gov_promotion_approved",
            "gov_promotion_rejected",
            "gov_promotion_revoked",
            "gov_session_reviewed",
            "gov_strategy_approved_for_paper",
            "gov_strategy_approved_for_live",
            "gov_lifecycle_transition_denied",
            # Phase 4E.1 — Paper Trading session lifecycle events (PT_)
            "pt_session_created",
            "pt_session_activated",
            "pt_session_paused",
            "pt_session_paused_drawdown_stop",
            "pt_session_paused_provider_failure",
            "pt_session_resumed",
            "pt_session_completed",
            "pt_session_failed",
            "pt_session_terminated",
            "pt_session_invalid_transition_denied",
            "pt_activation_denied",
            "pt_activation_approved",
            "pt_order_created",
            "pt_order_rejected",
            "pt_order_cancelled",
            "pt_fill_generated",
            "pt_position_opened",
            "pt_position_scaled",
            "pt_position_closed",
            "pt_position_force_closed",
            "pt_account_updated",
            "pt_drawdown_threshold_warning",
            "pt_drawdown_stop_triggered",
            "pt_poll_completed",
            "pt_provider_failure",
            "pt_gap_detected",
            "pt_catchup_started",
            "pt_catchup_threshold_exceeded",
            "pt_session_exported",
            "pt_session_reviewed",
            # FT-2 — Forward Test Scheduler events
            "ft_scheduler_tick_started",
            "ft_scheduler_tick_completed",
            "ft_scheduler_session_evaluated",
            "ft_scheduler_session_skipped",
            "ft_scheduler_session_auto_paused",
            "ft_scheduler_recovery",
        }
        actual = {e.value for e in AuditEventKind}
        assert expected == actual


# ---------------------------------------------------------------------------
# TestEmitAuditEvent
# ---------------------------------------------------------------------------

class TestEmitAuditEvent:
    def test_emits_to_audit_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.DATASET_REGISTERED,
                provider_name="csv",
                details={"catalog_id": "test-123", "symbol": "AAPL"},
            ))
        assert any("dataset_registered" in r.message for r in caplog.records)

    def test_emitted_record_is_valid_json(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.CATALOG_OHLCV_FETCH,
                provider_name="parquet",
                details={"catalog_id": "xyz-456"},
            ))
        for record in caplog.records:
            if "catalog_ohlcv_fetch" in record.message:
                parsed = json.loads(record.message)
                assert parsed["audit_event"] == "catalog_ohlcv_fetch"
                assert parsed["provider"] == "parquet"
                break

    def test_emitted_record_contains_no_file_path(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            emit_audit_event(AuditEvent(
                event_kind=AuditEventKind.DATASET_REGISTERED,
                provider_name="csv",
                details={"catalog_id": "abc", "symbol": "AAPL"},
            ))
        for record in caplog.records:
            assert "/data/" not in record.message
            assert "file_path" not in record.message

    def test_credential_resolution_attempt_emitted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        spec = CredentialSpec(provider_name="test_prov", credential_key="TEST_CRED_KEY_X")
        resolver = EnvironmentCredentialResolver()
        env_without_key = {k: v for k, v in os.environ.items() if k != "TEST_CRED_KEY_X"}
        with patch.dict(os.environ, env_without_key, clear=True):
            with caplog.at_level(logging.INFO, logger="quantlab.audit"):
                with pytest.raises(MissingCredentialError):
                    resolver.resolve(spec)

        messages = [r.message for r in caplog.records if "quantlab.audit" in r.name]
        kinds = []
        for msg in messages:
            try:
                kinds.append(json.loads(msg)["audit_event"])
            except (json.JSONDecodeError, KeyError):
                pass
        assert "credential_resolution_attempt" in kinds
        assert "credential_missing" in kinds


# ---------------------------------------------------------------------------
# TestRequestValidation
# ---------------------------------------------------------------------------

class TestRequestValidation:
    def test_validate_date_range_valid(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 12, 31, tzinfo=timezone.utc)
        validate_date_range(start, end)  # must not raise

    def test_validate_date_range_equal_raises(self) -> None:
        dt = datetime(2024, 6, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="start must be before end"):
            validate_date_range(dt, dt)

    def test_validate_date_range_reversed_raises(self) -> None:
        start = datetime(2024, 12, 31, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="start must be before end"):
            validate_date_range(start, end)

    def test_validate_provider_type_csv(self) -> None:
        validate_provider_type("csv")  # must not raise

    def test_validate_provider_type_parquet(self) -> None:
        validate_provider_type("parquet")  # must not raise

    def test_validate_provider_type_case_insensitive(self) -> None:
        validate_provider_type("CSV")   # must not raise
        validate_provider_type("Parquet")  # must not raise

    def test_validate_provider_type_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider_type"):
            validate_provider_type("yahoo")  # yahoo is not a catalog provider type

    def test_validate_provider_type_unknown_lists_allowed(self) -> None:
        with pytest.raises(ValueError, match="csv"):
            validate_provider_type("bad_type")

    def test_validate_symbol_valid(self) -> None:
        validate_symbol("AAPL")  # must not raise

    def test_validate_symbol_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_symbol("")

    def test_validate_symbol_whitespace_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_symbol("   ")

    def test_validate_catalog_id_format_valid(self) -> None:
        validate_catalog_id_format("abc-123-def")  # must not raise

    def test_validate_catalog_id_format_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_catalog_id_format("")

    def test_validate_catalog_id_format_whitespace_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_catalog_id_format("   ")

    def test_allowed_catalog_provider_types_contains_csv_parquet(self) -> None:
        assert "csv" in ALLOWED_CATALOG_PROVIDER_TYPES
        assert "parquet" in ALLOWED_CATALOG_PROVIDER_TYPES

    def test_allowed_catalog_provider_types_does_not_contain_yahoo(self) -> None:
        assert "yahoo" not in ALLOWED_CATALOG_PROVIDER_TYPES


# ---------------------------------------------------------------------------
# TestSafeErrorPolicy
# ---------------------------------------------------------------------------

class TestSafeErrorPolicy:
    def test_catalog_fetch_error_does_not_expose_file_path(
        self, tmp_path: Path, tmp_csv_with_data: Path
    ) -> None:
        from backend.api.schemas.catalog import RegisterDatasetRequest
        from backend.api.services.catalog_service import (
            CatalogFetchError,
            fetch_ohlcv,
            register_dataset,
        )
        from backend.data_providers.provider_factory import create_default_factory_registry

        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=str(tmp_csv_with_data),
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        reg_resp = register_dataset(request, tmp_path)

        # Now delete the file to trigger a provider fetch error with path in message
        tmp_csv_with_data.unlink()

        factory = create_default_factory_registry()
        try:
            fetch_ohlcv(
                catalog_id=reg_resp.catalog_id,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 12, 31, tzinfo=timezone.utc),
                base_path=tmp_path,
                factory=factory,
            )
        except CatalogFetchError as exc:
            error_msg = str(exc)
            assert str(tmp_csv_with_data) not in error_msg
            assert "/tmp/" not in error_msg or "file" not in error_msg.lower()

    def test_catalog_registration_file_not_found_message_safe(
        self, tmp_path: Path
    ) -> None:
        from backend.api.schemas.catalog import RegisterDatasetRequest
        from backend.api.services.catalog_service import (
            CatalogRegistrationError,
            register_dataset,
        )

        hidden_path = "/internal/secret/data/aapl.csv"
        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=hidden_path,
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        try:
            register_dataset(request, tmp_path)
        except CatalogRegistrationError as exc:
            assert hidden_path not in str(exc)

    def test_catalog_registration_unknown_provider_type_raises(
        self, tmp_path: Path, tmp_csv: Path
    ) -> None:
        from backend.api.schemas.catalog import RegisterDatasetRequest
        from backend.api.services.catalog_service import (
            CatalogRegistrationError,
            register_dataset,
        )

        request = RegisterDatasetRequest(
            provider_type="binance",  # not a valid catalog provider type
            file_path=str(tmp_csv),
            display_name="Test",
            symbol="BTCUSDT",
            asset_class="crypto",
            venue="BINANCE",
            timeframe="1d",
        )
        with pytest.raises(CatalogRegistrationError, match="Unknown provider_type"):
            register_dataset(request, tmp_path)


# ---------------------------------------------------------------------------
# TestAuditHookIntegration
# ---------------------------------------------------------------------------

class TestAuditHookIntegration:
    def test_register_emits_dataset_registered(
        self, tmp_path: Path, tmp_csv: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from backend.api.schemas.catalog import RegisterDatasetRequest
        from backend.api.services.catalog_service import register_dataset

        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="AAPL Daily",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            register_dataset(request, tmp_path)

        messages = [r.message for r in caplog.records if "quantlab.audit" in r.name]
        kinds = [json.loads(m)["audit_event"] for m in messages]
        assert "dataset_registered" in kinds

    def test_remove_emits_dataset_removed(
        self, tmp_path: Path, tmp_csv: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from backend.api.schemas.catalog import RegisterDatasetRequest
        from backend.api.services.catalog_service import register_dataset, remove_dataset

        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        reg = register_dataset(request, tmp_path)
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            remove_dataset(reg.catalog_id, tmp_path)

        messages = [r.message for r in caplog.records if "quantlab.audit" in r.name]
        kinds = [json.loads(m)["audit_event"] for m in messages]
        assert "dataset_removed" in kinds

    def test_fetch_ohlcv_emits_catalog_ohlcv_fetch(
        self,
        tmp_path: Path,
        tmp_csv_with_data: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from backend.api.schemas.catalog import RegisterDatasetRequest
        from backend.api.services.catalog_service import fetch_ohlcv, register_dataset
        from backend.data_providers.provider_factory import create_default_factory_registry

        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=str(tmp_csv_with_data),
            display_name="AAPL Daily",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        reg = register_dataset(request, tmp_path)
        factory = create_default_factory_registry()

        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            fetch_ohlcv(
                catalog_id=reg.catalog_id,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 12, 31, tzinfo=timezone.utc),
                base_path=tmp_path,
                factory=factory,
            )

        messages = [r.message for r in caplog.records if "quantlab.audit" in r.name]
        kinds = [json.loads(m)["audit_event"] for m in messages]
        assert "catalog_ohlcv_fetch" in kinds

    def test_audit_records_contain_no_file_path(
        self, tmp_path: Path, tmp_csv: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from backend.api.schemas.catalog import RegisterDatasetRequest
        from backend.api.services.catalog_service import register_dataset

        request = RegisterDatasetRequest(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        with caplog.at_level(logging.INFO, logger="quantlab.audit"):
            register_dataset(request, tmp_path)

        for record in caplog.records:
            if "quantlab.audit" in record.name:
                assert str(tmp_csv) not in record.message


# ---------------------------------------------------------------------------
# TestArchitectureBoundary
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def test_strategies_do_not_import_credentials(self) -> None:
        import ast
        import pathlib

        strategies_root = pathlib.Path("strategies")
        if not strategies_root.exists():
            pytest.skip("strategies/ directory not found")

        for py_file in strategies_root.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module = ""
                    if isinstance(node, ast.ImportFrom) and node.module:
                        module = node.module
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            module = alias.name
                    assert "core.credentials" not in module, (
                        f"Strategy file {py_file} must not import backend.core.credentials; "
                        f"strategies must remain credential-free."
                    )

    def test_credentials_module_does_not_import_yahoo(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path("backend/core/credentials.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                assert "data_providers.yahoo" not in module

    def test_audit_module_does_not_import_provider_factory(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path("backend/core/audit.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                assert "provider_factory" not in module
                assert "data_providers" not in module

    def test_api_schemas_no_credential_fields(self) -> None:
        from backend.api.schemas.catalog import (
            CatalogEntryResponse,
            CatalogListResponse,
            CatalogOHLCVResponse,
            RegisterDatasetResponse,
        )
        from backend.api.schemas.market_data import (
            MarketDataOHLCVResponse,
            ProvidersListResponse,
        )

        credential_like = {"api_key", "secret", "token", "password", "credential"}
        for schema_cls in [
            CatalogEntryResponse,
            CatalogListResponse,
            CatalogOHLCVResponse,
            RegisterDatasetResponse,
            MarketDataOHLCVResponse,
            ProvidersListResponse,
        ]:
            for field_name in schema_cls.model_fields:
                for c in credential_like:
                    assert c not in field_name.lower(), (
                        f"{schema_cls.__name__}.{field_name} looks like a credential field"
                    )

    def test_local_dataset_entry_no_credential_fields(self) -> None:
        from backend.storage.dataset_catalog import LocalDatasetEntry

        credential_like = {"api_key", "secret", "token", "password", "credential"}
        for field_name in LocalDatasetEntry.model_fields:
            for c in credential_like:
                assert c not in field_name.lower(), (
                    f"LocalDatasetEntry.{field_name} looks like a credential field"
                )

    def test_catalog_service_no_yahoo_import(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path("backend/api/services/catalog_service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                assert "data_providers.yahoo" not in module

    def test_missing_credential_error_hierarchy(self) -> None:
        assert issubclass(MissingCredentialError, CredentialResolutionError)
        assert issubclass(CredentialResolutionError, Exception)


# ---------------------------------------------------------------------------
# TestRouteValidation (HTTP-level)
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_client(tmp_path: Path) -> "TestClient":
    from fastapi.testclient import TestClient

    from backend.api.main import app
    from backend.api.routes.catalog import get_storage_path, get_provider_factory
    from backend.auth.dependencies import get_current_user
    from backend.auth.models import User
    from backend.data_providers.provider_factory import create_default_factory_registry

    _test_user = User(
        user_id="test-user-id",
        username="testuser",
        email="test@example.com",
        password_hash="hash",
        created_at="2026-01-01T00:00:00+00:00",
        subscription_status="active",
    )

    app.dependency_overrides[get_storage_path] = lambda: tmp_path
    app.dependency_overrides[get_provider_factory] = create_default_factory_registry
    app.dependency_overrides[get_current_user] = lambda: _test_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestRouteValidation:
    def test_ohlcv_start_after_end_returns_400(
        self, test_client: "TestClient", tmp_csv_with_data: Path, tmp_path: Path
    ) -> None:
        from fastapi.testclient import TestClient
        from backend.api.main import app
        from backend.api.routes.catalog import get_storage_path, get_provider_factory
        from backend.auth.dependencies import get_current_user
        from backend.auth.models import User
        from backend.data_providers.provider_factory import create_default_factory_registry

        _test_user = User(
            user_id="test-user-id",
            username="testuser",
            email="test@example.com",
            password_hash="hash",
            created_at="2026-01-01T00:00:00+00:00",
            subscription_status="active",
        )

        app.dependency_overrides[get_storage_path] = lambda: tmp_path
        app.dependency_overrides[get_provider_factory] = create_default_factory_registry
        app.dependency_overrides[get_current_user] = lambda: _test_user

        reg = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv_with_data),
                "display_name": "AAPL",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        ).json()

        resp = test_client.get(
            f"/catalog/datasets/{reg['catalog_id']}/ohlcv",
            params={
                "start": "2024-12-31T00:00:00Z",
                "end": "2024-01-01T00:00:00Z",  # end before start
            },
        )
        assert resp.status_code == 400

    def test_register_unknown_provider_type_returns_400(
        self, test_client: "TestClient", tmp_csv: Path
    ) -> None:
        resp = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "binance",  # not a valid local catalog provider
                "file_path": str(tmp_csv),
                "display_name": "Test",
                "symbol": "BTCUSDT",
                "asset_class": "crypto",
                "venue": "BINANCE",
                "timeframe": "1d",
            },
        )
        assert resp.status_code == 400
        assert "file_path" not in resp.json().get("detail", "")

    def test_register_response_no_credential_fields(
        self, test_client: "TestClient", tmp_csv: Path
    ) -> None:
        resp = test_client.post(
            "/catalog/datasets",
            json={
                "provider_type": "csv",
                "file_path": str(tmp_csv),
                "display_name": "AAPL",
                "symbol": "AAPL",
                "asset_class": "equity",
                "venue": "NASDAQ",
                "timeframe": "1d",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        for key in body:
            assert "secret" not in key.lower()
            assert "api_key" not in key.lower()
            assert "token" not in key.lower()
            assert "credential" not in key.lower()


# ---------------------------------------------------------------------------
# TestBackwardCompatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_yahoo_still_in_factory(self) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        registry = create_default_factory_registry()
        assert "yahoo" in registry

    def test_csv_still_in_factory(self) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        registry = create_default_factory_registry()
        assert "csv" in registry

    def test_parquet_still_in_factory(self) -> None:
        from backend.data_providers.provider_factory import create_default_factory_registry
        registry = create_default_factory_registry()
        assert "parquet" in registry

    def test_factory_still_has_four_providers(self) -> None:
        # Phase 3G added polygon; total is now yahoo + csv + parquet + polygon = 4
        from backend.data_providers.provider_factory import create_default_factory_registry
        registry = create_default_factory_registry()
        assert len(registry) == 4

    def test_catalog_register_still_works(self, tmp_path: Path, tmp_csv: Path) -> None:
        from backend.storage.dataset_catalog import DatasetCatalog
        catalog = DatasetCatalog(tmp_path)
        entry = catalog.register(
            provider_type="csv",
            file_path=str(tmp_csv),
            display_name="Test",
            symbol="AAPL",
            asset_class="equity",
            venue="NASDAQ",
            timeframe="1d",
        )
        assert entry.catalog_id

    def test_ohlcv_service_still_accepts_cache_policy(self, tmp_path: Path) -> None:
        from backend.data.models.cache_policy import DatasetCachePolicy
        from backend.services.ohlcv_service import OHLCVService
        svc = OHLCVService(tmp_path)
        assert svc is not None
        assert DatasetCachePolicy.FETCH_AND_STORE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_csv(tmp_path: Path) -> Path:
    p = tmp_path / "empty.csv"
    p.write_text("timestamp,open,high,low,close,volume\n")
    return p


@pytest.fixture()
def tmp_csv_with_data(tmp_path: Path) -> Path:
    p = tmp_path / "aapl_1d.csv"
    p.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-02,185.0,186.5,184.2,185.9,55000000\n"
        "2024-01-03,185.9,187.0,185.1,186.5,48000000\n"
        "2024-01-04,186.5,188.0,186.0,187.1,62000000\n"
    )
    return p

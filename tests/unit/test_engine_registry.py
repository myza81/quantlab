"""
Research Engine Registry tests — Phase 1b.

Coverage:

Registry loader (engine_registry_service):
  - Registry YAML loads successfully
  - Registry contains minor_structure_v1
  - Registry contains main_structure_v1
  - All required metadata fields are present on minor_structure_v1
  - All required metadata fields are present on main_structure_v1
  - Engines with production status are correct
  - Missing registry file raises EngineRegistryError
  - Malformed YAML raises EngineRegistryError
  - Missing top-level engines key raises EngineRegistryError
  - get_engine_by_id returns the correct record
  - get_engine_by_id raises EngineNotFoundError for unknown id

API endpoints (GET /research-engines, GET /research-engines/{technical_id}):
  - List endpoint returns 200
  - List endpoint returns both engines
  - List endpoint count matches engines list length
  - Detail endpoint returns 200 for minor_structure_v1
  - Detail endpoint returns 200 for main_structure_v1
  - Detail endpoint returns correct technical_id in response
  - Detail endpoint returns 404 for unknown technical_id
  - No POST endpoint exists (read-only)
  - No PUT endpoint exists (read-only)
  - No DELETE endpoint exists (read-only)
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.engine_registry import get_registry
from backend.api.services.engine_registry_service import (
    EngineNotFoundError,
    EngineRecord,
    EngineRegistryError,
    get_engine_by_id,
    load_registry,
)

client = TestClient(app)

_REQUIRED_FIELDS = [
    "human_name",
    "technical_id",
    "engine_type",
    "lifecycle_status",
    "rulebook_status",
    "purpose",
    "key_characteristics",
    "input_contract",
    "output_contract",
    "dependencies",
    "validation_status",
    "change_log",
]


# ---------------------------------------------------------------------------
# Registry loader unit tests
# ---------------------------------------------------------------------------

class TestRegistryLoader:

    def test_registry_loads_successfully(self) -> None:
        records = load_registry()
        assert isinstance(records, list)
        assert len(records) >= 2

    def test_registry_contains_minor_structure_v1(self) -> None:
        records = load_registry()
        ids = [r.technical_id for r in records]
        assert "minor_structure_v1" in ids

    def test_registry_contains_main_structure_v1(self) -> None:
        records = load_registry()
        ids = [r.technical_id for r in records]
        assert "main_structure_v1" in ids

    def test_minor_structure_v1_required_fields(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "minor_structure_v1")
        data = record.model_dump()
        for field in _REQUIRED_FIELDS:
            assert field in data, f"Missing field: {field}"
            assert data[field] not in (None, "", [], {}), f"Empty field: {field}"

    def test_main_structure_v1_required_fields(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "main_structure_v1")
        data = record.model_dump()
        for field in _REQUIRED_FIELDS:
            assert field in data, f"Missing field: {field}"
            assert data[field] not in (None, "", [], {}), f"Empty field: {field}"

    def test_minor_structure_v1_is_production(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "minor_structure_v1")
        assert record.lifecycle_status == "production"

    def test_main_structure_v1_is_production(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "main_structure_v1")
        assert record.lifecycle_status == "production"

    def test_minor_structure_v1_rulebook_frozen(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "minor_structure_v1")
        assert record.rulebook_status == "frozen"

    def test_main_structure_v1_rulebook_frozen(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "main_structure_v1")
        assert record.rulebook_status == "frozen"

    def test_minor_structure_v1_has_change_log(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "minor_structure_v1")
        assert len(record.change_log) >= 1

    def test_minor_structure_v1_input_contract_fields(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "minor_structure_v1")
        assert record.input_contract.type != ""
        assert len(record.input_contract.fields) >= 1

    def test_minor_structure_v1_output_contract_fields(self) -> None:
        records = load_registry()
        record = next(r for r in records if r.technical_id == "minor_structure_v1")
        assert record.output_contract.type != ""
        assert len(record.output_contract.fields) >= 1

    def test_missing_registry_file_raises_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(EngineRegistryError, match="not found"):
            load_registry(missing)

    def test_malformed_yaml_raises_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("engines: [: invalid", encoding="utf-8")
        with pytest.raises(EngineRegistryError):
            load_registry(bad)

    def test_missing_engines_key_raises_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "no_engines_key.yaml"
        bad.write_text("something_else: []", encoding="utf-8")
        with pytest.raises(EngineRegistryError, match="'engines'"):
            load_registry(bad)

    def test_get_engine_by_id_returns_correct_record(self) -> None:
        record = get_engine_by_id("minor_structure_v1")
        assert record.technical_id == "minor_structure_v1"
        assert record.human_name == "Classic Minor Structure"

    def test_get_engine_by_id_unknown_raises_error(self) -> None:
        with pytest.raises(EngineNotFoundError):
            get_engine_by_id("nonexistent_engine_xyz")


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestEngineRegistryAPI:

    def test_list_returns_200(self) -> None:
        response = client.get("/research-engines")
        assert response.status_code == 200

    def test_list_response_shape(self) -> None:
        response = client.get("/research-engines")
        body = response.json()
        assert "engines" in body
        assert "count" in body
        assert isinstance(body["engines"], list)

    def test_list_contains_both_engines(self) -> None:
        response = client.get("/research-engines")
        ids = [e["technical_id"] for e in response.json()["engines"]]
        assert "minor_structure_v1" in ids
        assert "main_structure_v1" in ids

    def test_list_count_matches_engines_length(self) -> None:
        body = client.get("/research-engines").json()
        assert body["count"] == len(body["engines"])

    def test_list_engines_have_required_fields(self) -> None:
        body = client.get("/research-engines").json()
        for engine in body["engines"]:
            for field in _REQUIRED_FIELDS:
                assert field in engine, f"Missing field '{field}' in engine {engine.get('technical_id')}"

    def test_detail_minor_structure_v1_returns_200(self) -> None:
        response = client.get("/research-engines/minor_structure_v1")
        assert response.status_code == 200

    def test_detail_main_structure_v1_returns_200(self) -> None:
        response = client.get("/research-engines/main_structure_v1")
        assert response.status_code == 200

    def test_detail_returns_correct_technical_id(self) -> None:
        response = client.get("/research-engines/minor_structure_v1")
        assert response.json()["technical_id"] == "minor_structure_v1"

    def test_detail_returns_correct_human_name(self) -> None:
        response = client.get("/research-engines/minor_structure_v1")
        assert response.json()["human_name"] == "Classic Minor Structure"

    def test_detail_returns_correct_lifecycle_status(self) -> None:
        response = client.get("/research-engines/minor_structure_v1")
        assert response.json()["lifecycle_status"] == "production"

    def test_detail_returns_correct_rulebook_status(self) -> None:
        response = client.get("/research-engines/minor_structure_v1")
        assert response.json()["rulebook_status"] == "frozen"

    def test_detail_unknown_engine_returns_404(self) -> None:
        response = client.get("/research-engines/nonexistent_engine_xyz")
        assert response.status_code == 404

    def test_detail_404_body_mentions_technical_id(self) -> None:
        response = client.get("/research-engines/nonexistent_engine_xyz")
        assert "nonexistent_engine_xyz" in response.json()["detail"]

    def test_detail_returns_change_log(self) -> None:
        body = client.get("/research-engines/minor_structure_v1").json()
        assert isinstance(body["change_log"], list)
        assert len(body["change_log"]) >= 1

    def test_detail_returns_input_contract(self) -> None:
        body = client.get("/research-engines/minor_structure_v1").json()
        assert "input_contract" in body
        assert "type" in body["input_contract"]
        assert "fields" in body["input_contract"]

    def test_detail_returns_key_characteristics(self) -> None:
        body = client.get("/research-engines/minor_structure_v1").json()
        assert isinstance(body["key_characteristics"], list)
        assert len(body["key_characteristics"]) >= 1

    def test_api_has_no_post_endpoint(self) -> None:
        response = client.post("/research-engines", json={})
        assert response.status_code == 405

    def test_api_has_no_put_endpoint(self) -> None:
        response = client.put("/research-engines/minor_structure_v1", json={})
        assert response.status_code == 405

    def test_api_has_no_delete_endpoint(self) -> None:
        response = client.delete("/research-engines/minor_structure_v1")
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# Dependency override tests (isolated from real YAML)
# ---------------------------------------------------------------------------

class TestEngineRegistryDependencyOverride:
    """Verify the registry dependency is properly overridable for downstream tests."""

    def setup_method(self) -> None:
        self._minimal_record = EngineRecord(
            human_name="Test Engine",
            technical_id="test_engine_v1",
            engine_type="test_type",
            lifecycle_status="experimental",
            rulebook_status="active",
            purpose="Test engine for dependency override validation.",
            key_characteristics=["deterministic"],
            input_contract={"type": "list[X]", "fields": ["a"]},
            output_contract={"type": "Y", "fields": ["b"]},
            dependencies=["X"],
            validation_status="not_validated",
            change_log=[{"date": "2026-01-01", "description": "initial"}],
        )
        app.dependency_overrides[get_registry] = lambda: [self._minimal_record]

    def teardown_method(self) -> None:
        app.dependency_overrides.pop(get_registry, None)

    def test_override_is_applied(self) -> None:
        body = client.get("/research-engines").json()
        assert body["count"] == 1
        assert body["engines"][0]["technical_id"] == "test_engine_v1"

    def test_detail_uses_overridden_registry(self) -> None:
        response = client.get("/research-engines/test_engine_v1")
        assert response.status_code == 200
        assert response.json()["human_name"] == "Test Engine"

    def test_real_engines_not_present_when_overridden(self) -> None:
        body = client.get("/research-engines").json()
        ids = [e["technical_id"] for e in body["engines"]]
        assert "minor_structure_v1" not in ids

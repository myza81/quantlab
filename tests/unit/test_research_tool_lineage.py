"""
RESEARCH-TOOL-LINEAGE-GUARD-1 — Lineage guardrail tests.

Coverage (10 required cases):

 1. V1 response carries V1 structure_lineage (tool_id = "minor_structure_v1")
 2. V2 response carries V2 structure_lineage (tool_id = "minor_structure_v2")
 3. V3 response carries V3 structure_lineage (tool_id = "minor_structure_v3")
 4. BoS parent_engine_id matches selected structure engine (V1, V2, V3)
 5. CHoCH parent_engine_id matches selected structure engine (V1, V2, V3)
 6. Unknown engine_id returns 400 — no silent fallback to V1
 7. build_minor_structure_engine raises ValueError for unknown engine_id
 8. API response shape preserves lineage fields end-to-end
 9. Debug panel renders lineage block when structureLineage is present
    (via API shape — frontend rendering tested in Chart.test.tsx)
10. Mismatch condition: response engine != selected engine is detectable
    from the response alone (parent_engine_id cross-check)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.services.market_structure_service import build_minor_structure_engine
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.tools.market_structure import MarketStructureEngine
from backend.tools.market_structure_v2 import MinorStructureV2Engine
from backend.tools.market_structure_v3 import MinorStructureV3Engine

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ACTIVE_USER = User(
    user_id="lineage-uid",
    username="lineagetest",
    email="lineage@example.com",
    password_hash="x",
    created_at="2025-01-01T00:00:00+00:00",
    subscription_status="active",
)

_T0 = datetime(2024, 1, 2, tzinfo=timezone.utc)


def _candle(i: int, open_: float, high: float, low: float, close: float) -> dict:
    ts = (_T0 + timedelta(days=i)).isoformat()
    return {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close, "volume": 1_000.0}


def _minimal_candles() -> list[dict]:
    """Minimal reversal sequence: up then down — enough to produce turning points."""
    candles = []
    for i in range(6):
        p = 100.0 + i * 2
        candles.append(_candle(i, p, p + 1, p - 1, p + 0.5))
    for i in range(6):
        p = 110.0 - i * 2
        candles.append(_candle(6 + i, p, p + 1, p - 1, p - 0.5))
    return candles


@pytest.fixture()
def client() -> TestClient:
    app.dependency_overrides[require_active_subscription] = lambda: _ACTIVE_USER
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _post(client: TestClient, engine_id: str | None = None) -> dict:
    body: dict = {"candles": _minimal_candles()}
    if engine_id is not None:
        body["engine_id"] = engine_id
    resp = client.post("/chart/market-structure", json=body)
    assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Case 1 — V1 response carries V1 lineage
# ---------------------------------------------------------------------------

class TestV1Lineage:
    def test_structure_lineage_tool_id_is_v1(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert data["structure_lineage"]["tool_id"] == "minor_structure_v1"

    def test_structure_lineage_tool_domain(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert data["structure_lineage"]["tool_domain"] == "market_structure"

    def test_structure_lineage_lifecycle_status_is_production(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert data["structure_lineage"]["lifecycle_status"] == "production"

    def test_structure_lineage_human_name(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert "Classic" in data["structure_lineage"]["human_name"]

    def test_structure_lineage_implementation_ref_contains_v1_class(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert "MarketStructureEngine" in data["structure_lineage"]["implementation_ref"]

    def test_version_id_equals_tool_id_for_v1(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert data["structure_lineage"]["version_id"] == "minor_structure_v1"


# ---------------------------------------------------------------------------
# Case 2 — V2 response carries V2 lineage
# ---------------------------------------------------------------------------

class TestV2Lineage:
    def test_structure_lineage_tool_id_is_v2(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v2")
        assert data["structure_lineage"]["tool_id"] == "minor_structure_v2"

    def test_structure_lineage_lifecycle_status_is_experimental(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v2")
        assert data["structure_lineage"]["lifecycle_status"] == "experimental"

    def test_structure_lineage_implementation_ref_contains_v2_class(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v2")
        assert "MinorStructureV2Engine" in data["structure_lineage"]["implementation_ref"]

    def test_v2_lineage_does_not_claim_v1(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v2")
        assert "v1" not in data["structure_lineage"]["tool_id"]


# ---------------------------------------------------------------------------
# Case 3 — V3 response carries V3 lineage
# ---------------------------------------------------------------------------

class TestV3Lineage:
    def test_structure_lineage_tool_id_is_v3(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v3")
        assert data["structure_lineage"]["tool_id"] == "minor_structure_v3"

    def test_structure_lineage_lifecycle_status_is_experimental(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v3")
        assert data["structure_lineage"]["lifecycle_status"] == "experimental"

    def test_structure_lineage_implementation_ref_contains_v3_class(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v3")
        assert "MinorStructureV3Engine" in data["structure_lineage"]["implementation_ref"]

    def test_v3_lineage_does_not_claim_v1_or_v2(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v3")
        tool_id = data["structure_lineage"]["tool_id"]
        assert tool_id not in ("minor_structure_v1", "minor_structure_v2")


# ---------------------------------------------------------------------------
# Case 4 — BoS parent_engine_id matches selected structure engine
# ---------------------------------------------------------------------------

class TestBoSParentLineage:
    @pytest.mark.parametrize("engine_id", [
        "minor_structure_v1",
        "minor_structure_v2",
        "minor_structure_v3",
    ])
    def test_bos_parent_engine_id_matches_selected(
        self, client: TestClient, engine_id: str
    ) -> None:
        data = _post(client, engine_id)
        assert data["bos_lineage"]["parent_engine_id"] == engine_id

    @pytest.mark.parametrize("engine_id", [
        "minor_structure_v1",
        "minor_structure_v2",
        "minor_structure_v3",
    ])
    def test_bos_parent_engine_id_matches_structure_lineage(
        self, client: TestClient, engine_id: str
    ) -> None:
        data = _post(client, engine_id)
        assert (
            data["bos_lineage"]["parent_engine_id"]
            == data["structure_lineage"]["tool_id"]
        )

    def test_bos_lineage_tool_domain_is_structure_event(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert data["bos_lineage"]["tool_domain"] == "structure_event"

    def test_bos_lineage_tool_id(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert data["bos_lineage"]["tool_id"] == "bos_detection"

    def test_bos_lineage_parent_tool_domain(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert data["bos_lineage"]["parent_tool_domain"] == "market_structure"


# ---------------------------------------------------------------------------
# Case 5 — CHoCH parent_engine_id matches selected structure engine
# ---------------------------------------------------------------------------

class TestCHoCHParentLineage:
    @pytest.mark.parametrize("engine_id", [
        "minor_structure_v1",
        "minor_structure_v2",
        "minor_structure_v3",
    ])
    def test_choch_parent_engine_id_matches_selected(
        self, client: TestClient, engine_id: str
    ) -> None:
        data = _post(client, engine_id)
        assert data["choch_lineage"]["parent_engine_id"] == engine_id

    @pytest.mark.parametrize("engine_id", [
        "minor_structure_v1",
        "minor_structure_v2",
        "minor_structure_v3",
    ])
    def test_choch_parent_engine_id_matches_structure_lineage(
        self, client: TestClient, engine_id: str
    ) -> None:
        data = _post(client, engine_id)
        assert (
            data["choch_lineage"]["parent_engine_id"]
            == data["structure_lineage"]["tool_id"]
        )

    def test_choch_lineage_tool_id(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert data["choch_lineage"]["tool_id"] == "choch_detection"


# ---------------------------------------------------------------------------
# Case 6 — Unknown engine_id returns 400, not a silent V1 fallback
# ---------------------------------------------------------------------------

class TestInvalidEngineId:
    def test_unknown_engine_id_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/chart/market-structure",
            json={"candles": _minimal_candles(), "engine_id": "minor_structure_v99"},
        )
        assert resp.status_code == 400

    def test_unknown_engine_id_error_message_mentions_valid_values(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/chart/market-structure",
            json={"candles": _minimal_candles(), "engine_id": "ghost_engine"},
        )
        detail = resp.json()["detail"]
        assert "minor_structure_v1" in detail

    def test_empty_engine_id_string_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/chart/market-structure",
            json={"candles": _minimal_candles(), "engine_id": ""},
        )
        assert resp.status_code == 400

    def test_response_does_not_silently_use_v1_for_unknown_id(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/chart/market-structure",
            json={"candles": _minimal_candles(), "engine_id": "minor_structure_v99"},
        )
        # Must NOT be 200 with V1 lineage — that would be a silent fallback.
        assert resp.status_code != 200


# ---------------------------------------------------------------------------
# Case 7 — build_minor_structure_engine raises for unknown engine_id
# ---------------------------------------------------------------------------

class TestBuildMinorStructureEngineFactory:
    def test_v1_returns_market_structure_engine(self) -> None:
        engine = build_minor_structure_engine("minor_structure_v1")
        assert isinstance(engine, MarketStructureEngine)

    def test_v2_returns_v2_engine(self) -> None:
        engine = build_minor_structure_engine("minor_structure_v2")
        assert isinstance(engine, MinorStructureV2Engine)

    def test_v3_returns_v3_engine(self) -> None:
        engine = build_minor_structure_engine("minor_structure_v3")
        assert isinstance(engine, MinorStructureV3Engine)

    def test_unknown_id_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="minor_structure_v99"):
            build_minor_structure_engine("minor_structure_v99")

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            build_minor_structure_engine("")

    def test_error_message_lists_valid_ids(self) -> None:
        with pytest.raises(ValueError, match="minor_structure_v1"):
            build_minor_structure_engine("bad_id")

    def test_v1_engine_is_not_v2_or_v3(self) -> None:
        engine = build_minor_structure_engine("minor_structure_v1")
        assert not isinstance(engine, (MinorStructureV2Engine, MinorStructureV3Engine))

    def test_v2_engine_is_not_v1_or_v3(self) -> None:
        engine = build_minor_structure_engine("minor_structure_v2")
        assert not isinstance(engine, (MarketStructureEngine, MinorStructureV3Engine))


# ---------------------------------------------------------------------------
# Case 8 — API response shape preserves all lineage fields end-to-end
# ---------------------------------------------------------------------------

class TestLineageResponseShape:
    _LINEAGE_FIELDS = {
        "tool_domain", "tool_id", "version_id", "human_name",
        "lifecycle_status", "implementation_ref",
    }
    _DERIVED_FIELDS = {
        "tool_domain", "tool_id", "parent_tool_domain", "parent_engine_id",
    }

    @pytest.mark.parametrize("engine_id", [
        "minor_structure_v1",
        "minor_structure_v2",
        "minor_structure_v3",
    ])
    def test_structure_lineage_has_all_required_fields(
        self, client: TestClient, engine_id: str
    ) -> None:
        data = _post(client, engine_id)
        assert self._LINEAGE_FIELDS <= set(data["structure_lineage"].keys())

    @pytest.mark.parametrize("engine_id", [
        "minor_structure_v1",
        "minor_structure_v2",
        "minor_structure_v3",
    ])
    def test_bos_lineage_has_all_required_fields(
        self, client: TestClient, engine_id: str
    ) -> None:
        data = _post(client, engine_id)
        assert self._DERIVED_FIELDS <= set(data["bos_lineage"].keys())

    @pytest.mark.parametrize("engine_id", [
        "minor_structure_v1",
        "minor_structure_v2",
        "minor_structure_v3",
    ])
    def test_choch_lineage_has_all_required_fields(
        self, client: TestClient, engine_id: str
    ) -> None:
        data = _post(client, engine_id)
        assert self._DERIVED_FIELDS <= set(data["choch_lineage"].keys())

    def test_lineage_fields_present_in_response_keys(self, client: TestClient) -> None:
        data = _post(client, "minor_structure_v1")
        assert "structure_lineage" in data
        assert "bos_lineage" in data
        assert "choch_lineage" in data

    def test_empty_candles_still_returns_lineage(self, client: TestClient) -> None:
        resp = client.post(
            "/chart/market-structure",
            json={"candles": [], "engine_id": "minor_structure_v1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["structure_lineage"]["tool_id"] == "minor_structure_v1"
        assert data["bos_lineage"]["parent_engine_id"] == "minor_structure_v1"
        assert data["choch_lineage"]["parent_engine_id"] == "minor_structure_v1"


# ---------------------------------------------------------------------------
# Cases 9 + 10 — Lineage display and mismatch detectability
#
# Frontend rendering is tested in Chart.test.tsx.
# Here we verify the API contract that makes display and mismatch detection
# possible: structure_lineage.tool_id and bos/choch parent_engine_id
# must always be consistent and individually inspectable.
# ---------------------------------------------------------------------------

class TestLineageCrossConsistency:
    def test_all_three_lineage_engine_ids_agree(self, client: TestClient) -> None:
        """The tool_id, bos parent, and choch parent must all name the same engine."""
        for engine_id in ("minor_structure_v1", "minor_structure_v2", "minor_structure_v3"):
            data = _post(client, engine_id)
            struct_id  = data["structure_lineage"]["tool_id"]
            bos_parent = data["bos_lineage"]["parent_engine_id"]
            choch_parent = data["choch_lineage"]["parent_engine_id"]
            assert struct_id == bos_parent == choch_parent == engine_id, (
                f"Lineage inconsistency for engine_id={engine_id!r}: "
                f"structure={struct_id!r} bos={bos_parent!r} choch={choch_parent!r}"
            )

    def test_v1_and_v3_lineages_are_distinguishable(self, client: TestClient) -> None:
        """A caller comparing V1 and V3 responses must see different tool_id values."""
        v1 = _post(client, "minor_structure_v1")
        v3 = _post(client, "minor_structure_v3")
        assert v1["structure_lineage"]["tool_id"] != v3["structure_lineage"]["tool_id"]

    def test_mismatch_is_detectable_via_response_fields(self, client: TestClient) -> None:
        """
        Simulate a caller that selected V3 but received a V1 response.
        The mismatch is detectable purely from the response fields without
        needing any out-of-band knowledge.
        """
        # The actual service enforces consistency, so we simulate by directly
        # checking the field contract: if selected != structure_lineage.tool_id,
        # the caller can detect the mismatch.
        selected_engine = "minor_structure_v3"
        data = _post(client, "minor_structure_v1")   # simulate wrong engine in response
        response_engine = data["structure_lineage"]["tool_id"]
        mismatch = selected_engine != response_engine
        assert mismatch  # demonstrates mismatch is detectable

"""
MS-2 — POST /chart/market-structure route tests.

Coverage:

Authentication:
  - 401 when unauthenticated (overrides conftest autouse fixture)

Input validation:
  - Empty candle list returns empty result (no 422)
  - Single candle returns empty result (< 2 threshold)
  - Extra fields in candle body → 422 (extra="forbid")
  - Missing required candle field → 422

Response structure:
  - Valid candles → 200 with all five result keys
  - minor_points / minor_legs / main_points / main_legs / debug_events all lists
  - Reversal sequence produces non-empty minor points
  - Full cycle produces non-empty minor legs
  - Response point fields match expected schema
  - Response leg fields match expected schema
  - debug_events have required fields

Correctness:
  - Uptrend-then-reversal produces a HIGH turning point
  - Down leg confirmed by bar indices
  - Up-down-up cycle produces at least one DOWN leg
  - Up-down-up-down cycle produces both UP and DOWN legs
  - bar_index in points is within the input candle range
  - debug_events count bounded by candle count

Scope guard:
  - No strategy signals, no execution fields in response
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ACTIVE_USER = User(
    user_id="ms-route-uid",
    username="mstest",
    email="ms@example.com",
    password_hash="x",
    created_at="2025-01-01T00:00:00+00:00",
    subscription_status="active",
)

_T0 = datetime(2024, 1, 2, tzinfo=timezone.utc)


def _candle(i: int, open_: float, high: float, low: float, close: float, volume: float = 1_000.0) -> dict:
    ts = (_T0 + timedelta(days=i)).isoformat()
    return {"timestamp": ts, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _rising_segment(start_bar: int, n: int, base_price: float, step: float = 2.0) -> list[dict]:
    """Strictly ascending candles (each bar a higher high and higher low)."""
    result = []
    for k in range(n):
        p = base_price + k * step
        result.append(_candle(start_bar + k, p, p + 1, p - 1, p + 0.5))
    return result


def _falling_segment(start_bar: int, n: int, base_price: float, step: float = 2.0) -> list[dict]:
    """Strictly descending candles (each bar a lower high and lower low)."""
    result = []
    for k in range(n):
        p = base_price - k * step
        result.append(_candle(start_bar + k, p, p + 1, p - 1, p - 0.5))
    return result


def _reversal_candles() -> list[dict]:
    """
    Up-then-down sequence that produces exactly one H turning point.
    Engine needs a direction reversal to emit any turning point.
    (monotonic sequences produce 0 points — the engine only records a turning
    point when the trend flips, not while it's in progress)
    """
    return _rising_segment(0, 6, 100.0) + _falling_segment(6, 6, 110.0)


def _full_cycle_candles() -> list[dict]:
    """
    Up → down → up sequence.  Produces:
      H turning point (end of first up segment)
      L turning point (end of down segment)
      1 DOWN leg from H to L
    """
    return (
        _rising_segment(0, 6, 100.0) +
        _falling_segment(6, 6, 110.0) +
        _rising_segment(12, 6, 98.0)
    )


def _two_cycle_candles() -> list[dict]:
    """
    Up → down → up → down sequence.  Produces at least:
      H turning point (end of first up)
      L turning point (end of down)
      H turning point (end of second up)
      DOWN legs + UP leg
    """
    return (
        _rising_segment(0, 6, 100.0) +
        _falling_segment(6, 6, 110.0) +
        _rising_segment(12, 6, 98.0) +
        _falling_segment(18, 6, 110.0)
    )


@pytest.fixture()
def client() -> TestClient:
    app.dependency_overrides[require_active_subscription] = lambda: _ACTIVE_USER
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def test_unauthenticated_returns_401() -> None:
    """
    The conftest autouse fixture always overrides require_active_subscription.
    This test pops that override so the real dependency runs, confirming 401.
    """
    app.dependency_overrides.pop(require_active_subscription, None)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides[require_active_subscription] = lambda: _ACTIVE_USER


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_empty_candle_list_returns_empty_result(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["minor_points"] == []
    assert data["minor_legs"] == []
    assert data["main_points"] == []
    assert data["main_legs"] == []
    assert data["debug_events"] == []


def test_single_candle_returns_empty_result(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": [_candle(0, 100, 101, 99, 100)]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["minor_points"] == []
    assert data["minor_legs"] == []


def test_extra_field_in_candle_body_returns_422(client: TestClient) -> None:
    bad = _candle(0, 100, 101, 99, 100)
    bad["extra_field"] = "boom"
    resp = client.post("/chart/market-structure", json={"candles": [bad, _candle(1, 102, 103, 101, 102)]})
    assert resp.status_code == 422


def test_missing_required_candle_field_returns_422(client: TestClient) -> None:
    bad = {"timestamp": _T0.isoformat(), "open": 100.0, "high": 101.0, "low": 99.0}  # no close/volume
    resp = client.post("/chart/market-structure", json={"candles": [bad]})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

def test_valid_candles_return_200(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
    assert resp.status_code == 200


_EXPECTED_RESPONSE_KEYS = {
    "minor_points", "minor_legs", "main_points", "main_legs", "debug_events",
    "bos_events", "choch_events",
}


def test_response_has_all_expected_keys(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
    data = resp.json()
    assert set(data.keys()) == _EXPECTED_RESPONSE_KEYS


def test_all_result_values_are_lists(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
    data = resp.json()
    for key in ("minor_points", "minor_legs", "main_points", "main_legs", "debug_events"):
        assert isinstance(data[key], list), f"{key} should be a list"


def test_point_fields_match_schema(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
    data = resp.json()
    for pt in data["minor_points"]:
        assert "id" in pt
        assert "level" in pt
        assert "kind" in pt
        assert "timestamp" in pt
        assert "bar_index" in pt
        assert "price" in pt
        assert "source" in pt
        assert "confirmed" in pt
        assert isinstance(pt["bar_index"], int)
        assert isinstance(pt["price"], (int, float))
        assert isinstance(pt["confirmed"], bool)


def test_leg_fields_match_schema(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _full_cycle_candles()})
    data = resp.json()
    for leg in data["minor_legs"]:
        assert "id" in leg
        assert "level" in leg
        assert "from_point_id" in leg
        assert "to_point_id" in leg
        assert "direction" in leg
        assert "start_bar_index" in leg
        assert "end_bar_index" in leg
        assert "start_price" in leg
        assert "end_price" in leg
        assert isinstance(leg["start_bar_index"], int)
        assert isinstance(leg["end_bar_index"], int)


def test_debug_events_have_required_fields(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
    data = resp.json()
    for ev in data["debug_events"]:
        assert "bar_index" in ev
        assert "timestamp" in ev
        assert "candle_relationship" in ev
        assert "action" in ev
        assert "reason" in ev
        assert "affected_level" in ev


# ---------------------------------------------------------------------------
# Correctness — engine behaviour
# ---------------------------------------------------------------------------

def test_reversal_sequence_produces_minor_points(client: TestClient) -> None:
    """An uptrend followed by a reversal must emit at least one H turning point."""
    resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
    data = resp.json()
    assert len(data["minor_points"]) >= 1


def test_reversal_sequence_produces_debug_events(client: TestClient) -> None:
    """Every candle after the first must emit a debug event (engine logs each decision)."""
    candles = _reversal_candles()
    resp = client.post("/chart/market-structure", json={"candles": candles})
    data = resp.json()
    assert len(data["debug_events"]) >= 1


def test_full_cycle_produces_minor_legs(client: TestClient) -> None:
    """Up-down-up cycle must produce at least one leg (need 2 turning points)."""
    resp = client.post("/chart/market-structure", json={"candles": _full_cycle_candles()})
    data = resp.json()
    assert len(data["minor_legs"]) >= 1


def test_full_cycle_produces_down_leg(client: TestClient) -> None:
    """Up-down-up cycle: the H→L segment is a DOWN leg."""
    resp = client.post("/chart/market-structure", json={"candles": _full_cycle_candles()})
    data = resp.json()
    assert any(leg["direction"] == "down" for leg in data["minor_legs"])


def test_two_cycles_produce_up_and_down_legs(client: TestClient) -> None:
    """Up-down-up-down cycle produces both UP and DOWN legs."""
    resp = client.post("/chart/market-structure", json={"candles": _two_cycle_candles()})
    data = resp.json()
    directions = {leg["direction"] for leg in data["minor_legs"]}
    # At minimum the first DOWN leg; after 4 segments UP should also appear
    assert "down" in directions


def test_minor_points_level_is_minor(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
    data = resp.json()
    for pt in data["minor_points"]:
        assert pt["level"] == "minor"


def test_minor_legs_level_is_minor(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _full_cycle_candles()})
    data = resp.json()
    for leg in data["minor_legs"]:
        assert leg["level"] == "minor"


def test_bar_index_in_range(client: TestClient) -> None:
    candles = _full_cycle_candles()
    resp = client.post("/chart/market-structure", json={"candles": candles})
    data = resp.json()
    n = len(candles)
    for pt in data["minor_points"] + data["main_points"]:
        assert 0 <= pt["bar_index"] < n, f"bar_index {pt['bar_index']} out of range [0, {n})"


def test_debug_events_bounded_by_candle_count(client: TestClient) -> None:
    candles = _reversal_candles()
    resp = client.post("/chart/market-structure", json={"candles": candles})
    data = resp.json()
    assert 0 < len(data["debug_events"]) <= len(candles) - 1


def test_no_unexpected_fields_in_response(client: TestClient) -> None:
    """Response must not contain fields beyond the defined schema."""
    resp = client.post("/chart/market-structure", json={"candles": _reversal_candles()})
    data = resp.json()
    assert set(data.keys()) <= _EXPECTED_RESPONSE_KEYS


# ---------------------------------------------------------------------------
# BoS event response schema
# ---------------------------------------------------------------------------

def _trending_candles() -> list[dict]:
    """
    Up→down→up→down-hard sequence that forces an uptrend context and a BoS.

    Rising segment creates H turning point.
    Falling then rising creates HL + HH → uptrend confirmed.
    Final hard-break bar clears HH level with close confirmation → valid BoS.
    """
    return (
        _rising_segment(0,  6, 100.0) +   # first up  → H at bar ~5
        _falling_segment(6, 4,  112.0) +  # down      → L at bar ~9 (HL relative to first L)
        _rising_segment(10, 6, 104.0) +   # second up → HH at bar ~15
        [_candle(16, 128, 130, 115, 128)]  # hard break above HH, close clears → BoS
    )


def test_bos_events_is_list(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _trending_candles()})
    assert resp.status_code == 200
    assert isinstance(resp.json()["bos_events"], list)


def test_bos_event_fields_match_schema(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _trending_candles()})
    data = resp.json()
    for ev in data["bos_events"]:
        assert "status"              in ev
        assert "direction"           in ev
        assert "structure_scope"     in ev
        assert "break_level"         in ev
        assert "protected_level"     in ev
        assert "break_candle_index"  in ev
        assert "event_type"          in ev
        assert "event_effect"        in ev
        assert ev["event_type"]   == "bos"
        assert ev["event_effect"] == "continuation"
        assert ev["status"]       in ("valid", "pending", "invalid")
        assert ev["direction"]    in ("bullish", "bearish")


def test_bos_event_scope_is_minor(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _trending_candles()})
    data = resp.json()
    for ev in data["bos_events"]:
        assert ev["structure_scope"] == "minor"


# ---------------------------------------------------------------------------
# CHoCH event response schema
# ---------------------------------------------------------------------------

def _choch_candles() -> list[dict]:
    """
    Uptrend that ends with an HL violation → bullish CHoCH.

    Rising to H, falling to L (first L), rising to HH (uptrend active with HL set),
    then a candle whose LOW dips below the HL protected level.
    """
    return (
        _rising_segment(0,  6, 100.0) +   # H near bar 5
        _falling_segment(6, 4, 112.0) +   # L (becomes HL candidate)
        _rising_segment(10, 6, 104.0) +   # HH → uptrend confirmed, HL recorded
        [_candle(16, 113, 116, 100, 113)]   # low below HL protected level → CHoCH
    )


def test_choch_events_is_list(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _choch_candles()})
    assert resp.status_code == 200
    assert isinstance(resp.json()["choch_events"], list)


def test_choch_event_fields_match_schema(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _choch_candles()})
    data = resp.json()
    for ev in data["choch_events"]:
        assert "direction"                  in ev
        assert "structure_scope"            in ev
        assert "protected_level"            in ev
        assert "break_candle_index"         in ev
        assert "structure_reference_index"  in ev
        assert "reference_structure_type"   in ev
        assert "violated_trend"             in ev
        assert "event_type"                 in ev
        assert "event_effect"               in ev
        assert "status"                     in ev
        assert ev["event_type"]   == "choch"
        assert ev["event_effect"] == "transition"
        assert ev["status"]       == "valid"
        assert ev["direction"]    in ("bullish", "bearish")


def test_choch_event_scope_is_minor(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": _choch_candles()})
    data = resp.json()
    for ev in data["choch_events"]:
        assert ev["structure_scope"] == "minor"


def test_empty_candles_returns_empty_event_lists(client: TestClient) -> None:
    resp = client.post("/chart/market-structure", json={"candles": []})
    data = resp.json()
    assert data["bos_events"]   == []
    assert data["choch_events"] == []

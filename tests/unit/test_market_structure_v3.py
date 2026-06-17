"""
Unit tests for MinorStructureV3Engine — minor_structure_v3 experimental engine.

Scenarios covered:
  1.  Inside-container candle: no pivot, no state change, no container reset
  2.  Outside-container candle: maintains previous state, no pivot, container resets
  3.  Bullish breakout: sets state high, resets container
  4.  Bearish breakout: sets state low, resets container
  5.  State change high → low: emits swing high at true highest high of completed leg
  6.  State change low → high: emits swing low at true lowest low of completed leg
  7.  Equal boundary: treated as inside container (not a breakout)
  8.  Default API request still uses minor_structure_v1
  9.  Explicit V3 API request returns V3 output (200)
  10. Unknown engine_id returns HTTP 400
"""
import pytest

from backend.tools.market_structure import OHLCVCandle, PointKind
from backend.tools.market_structure_v3 import MinorStructureV3Engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_candle(bar_index: int, high: float, low: float, close: float | None = None) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=f"2024-01-{bar_index + 1:02d}T00:00:00Z",
        bar_index=bar_index,
        open=(high + low) / 2,
        high=high,
        low=low,
        close=close if close is not None else (high + low) / 2,
        volume=1000.0,
    )


def compute(candles: list[OHLCVCandle]):
    return MinorStructureV3Engine().compute_structure(candles)


def debug_actions(result) -> list[str]:
    return [e.action for e in result.debug_events]


# ---------------------------------------------------------------------------
# 1. Inside-container candle
# ---------------------------------------------------------------------------

def test_inside_container_no_pivot_no_reset():
    """
    After a bullish breakout establishes the container, an inside candle
    produces no pivot, no state change, and does not reset the container.
    """
    candles = [
        make_candle(0, high=100, low=90),   # init: R=100, S=90
        make_candle(1, high=110, low=92),   # bullish breakout (110>100, 92>=90)
        make_candle(2, high=108, low=93),   # inside (108<=110, 93>=92)
        make_candle(3, high=107, low=93),   # inside
        make_candle(4, high=105, low=91),   # bearish breakout (91<92) → emits H
    ]
    result = compute(candles)

    actions = debug_actions(result)
    assert "inside_container" in actions

    # Candles 2 and 3 are inside — no pivot emitted until bearish breakout at 4
    # Only one H emitted when high→low transition at bar 4
    assert len(result.minor_points) == 1
    h = result.minor_points[0]
    assert h.kind == PointKind.H
    # H must be at bar 1 (high=110) — the true highest of the high leg
    assert h.price == 110.0
    assert h.bar_index == 1


def test_inside_container_does_not_reset_container():
    """
    Container stays unchanged after inside candles.
    A subsequent breakout still uses the original container boundaries.
    """
    candles = [
        make_candle(0, high=100, low=90),   # init R=100, S=90
        make_candle(1, high=110, low=92),   # bullish: state=high, R=110, S=92
        make_candle(2, high=108, low=93),   # inside — R stays 110
        # If container had been reset to [93,108], bar 3 would be bullish;
        # with unchanged container [92,110], bar 3 is still inside.
        make_candle(3, high=109, low=93),   # inside (109<=110, 93>=92)
    ]
    result = compute(candles)

    inside_events = [e for e in result.debug_events if e.action == "inside_container"]
    assert len(inside_events) == 2  # bars 2 and 3

    # No pivot yet
    assert len(result.minor_points) == 0


# ---------------------------------------------------------------------------
# 2. Outside-container candle
# ---------------------------------------------------------------------------

def test_outside_container_no_pivot_maintains_state():
    """
    Outside candle: high > R AND low < S.
    State is maintained (no pivot), container resets.
    """
    candles = [
        make_candle(0, high=100, low=90),   # init R=100, S=90
        make_candle(1, high=110, low=92),   # bullish: state=high, R=110, S=92
        make_candle(2, high=115, low=88),   # outside (115>110 AND 88<92)
        make_candle(3, high=113, low=90),   # bearish vs new R=115? No: 113<=115, 90>=88 → inside
        make_candle(4, high=120, low=91),   # bullish vs [88,115]: 120>115, 91>=88 → continue high
        make_candle(5, high=118, low=85),   # bearish vs [91,120]: 85<91, 118<=120 → emit H at true high
    ]
    result = compute(candles)

    outside_events = [e for e in result.debug_events if e.action == "outside_container"]
    assert len(outside_events) == 1  # bar 2

    # State was 'high' throughout; H emitted at bar 4 (high=120 > bar1 high=110 and bar2 high=115)
    assert len(result.minor_points) == 1
    h = result.minor_points[0]
    assert h.kind == PointKind.H
    assert h.price == 120.0
    assert h.bar_index == 4


def test_outside_container_resets_container():
    """
    After an outside candle, the container is the outside candle's range.
    The next inside check uses the new container.
    """
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=92),   # bullish: R=110, S=92
        make_candle(2, high=115, low=88),   # outside: R resets to 115, S resets to 88
        # Now inside the new container [88, 115]:
        make_candle(3, high=114, low=89),   # inside (114<=115, 89>=88)
    ]
    result = compute(candles)

    events_by_bar = {e.bar_index: e for e in result.debug_events}
    assert events_by_bar[3].action == "inside_container"


# ---------------------------------------------------------------------------
# 3. Bullish breakout
# ---------------------------------------------------------------------------

def test_bullish_breakout_sets_state_high():
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=92),   # bullish (110>100, 92>=90)
    ]
    result = compute(candles)

    events = [e for e in result.debug_events if e.action == "bullish_breakout"]
    assert len(events) == 1
    assert events[0].bar_index == 1
    assert events[0].new_direction is not None
    # Direction UP corresponds to 'high' state
    from backend.tools.market_structure import Direction
    assert events[0].new_direction == Direction.UP


def test_bullish_breakout_resets_container():
    """After bullish breakout, container = current candle's high/low."""
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=92),   # bullish → R=110, S=92
        make_candle(2, high=109, low=93),   # inside [92,110]
    ]
    result = compute(candles)

    # bar 2 inside confirms that container was reset to [92,110] by bar 1
    events_by_bar = {e.bar_index: e for e in result.debug_events}
    assert events_by_bar[2].action == "inside_container"


# ---------------------------------------------------------------------------
# 4. Bearish breakout
# ---------------------------------------------------------------------------

def test_bearish_breakout_sets_state_low():
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=95, low=82),    # bearish (82<90, 95<=100)
    ]
    result = compute(candles)

    events = [e for e in result.debug_events if e.action == "bearish_breakout"]
    assert len(events) == 1
    assert events[0].bar_index == 1
    from backend.tools.market_structure import Direction
    assert events[0].new_direction == Direction.DOWN


def test_bearish_breakout_resets_container():
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=95, low=82),    # bearish → R=95, S=82
        make_candle(2, high=94, low=83),    # inside [82,95]
    ]
    result = compute(candles)

    events_by_bar = {e.bar_index: e for e in result.debug_events}
    assert events_by_bar[2].action == "inside_container"


# ---------------------------------------------------------------------------
# 5. State change high → low: swing high at true highest high
# ---------------------------------------------------------------------------

def test_high_to_low_emits_h_at_true_extreme():
    """
    Three successive bullish breakouts extend the high leg.
    Bearish breakout triggers H at the true highest candle.
    """
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=92),   # bullish: state=high, highest=bar1(110)
        make_candle(2, high=115, low=93),   # bullish (115>110): highest=bar2(115)
        make_candle(3, high=112, low=94),   # inside (112<=115)
        make_candle(4, high=118, low=95),   # bullish (118>115): highest=bar4(118)
        make_candle(5, high=116, low=91),   # bearish (91<95): emit H at bar4(118)
    ]
    result = compute(candles)

    assert len(result.minor_points) == 1
    h = result.minor_points[0]
    assert h.kind == PointKind.H
    assert h.price == 118.0
    assert h.bar_index == 4


def test_high_to_low_outside_candle_updates_tracker():
    """
    Outside candle during high leg updates highest_high_candle if it makes a new high.
    """
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=92),   # bullish: state=high, highest=bar1(110)
        make_candle(2, high=120, low=88),   # outside (120>110, 88<92): highest=bar2(120), state stays high
        make_candle(3, high=118, low=91),   # bearish (91<88)? No: 88 was reset. R=120, S=88. 91>=88, 118<=120 → inside
        make_candle(4, high=116, low=87),   # bearish (87<88, 116<=120): emit H at bar2(120)
    ]
    result = compute(candles)

    assert len(result.minor_points) == 1
    h = result.minor_points[0]
    assert h.price == 120.0
    assert h.bar_index == 2


# ---------------------------------------------------------------------------
# 6. State change low → high: swing low at true lowest low
# ---------------------------------------------------------------------------

def test_low_to_high_emits_l_at_true_extreme():
    """
    Three successive bearish breakouts extend the low leg.
    Bullish breakout triggers L at the true lowest candle.
    """
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=95, low=80),    # bearish: state=low, lowest=bar1(80)
        make_candle(2, high=93, low=75),    # bearish (75<80): lowest=bar2(75)
        make_candle(3, high=91, low=77),    # inside (91<=93, 77>=75)
        make_candle(4, high=90, low=72),    # bearish (72<75): lowest=bar4(72)
        make_candle(5, high=96, low=73),    # bullish (96>90, 73>=72): emit L at bar4(72)
    ]
    result = compute(candles)

    assert len(result.minor_points) == 1
    l = result.minor_points[0]
    assert l.kind == PointKind.L
    assert l.price == 72.0
    assert l.bar_index == 4


# ---------------------------------------------------------------------------
# 7. Equal boundary: inside container (not a breakout)
# ---------------------------------------------------------------------------

def test_equal_high_boundary_is_inside():
    """high == temp_resistance is inside_container, not bullish_breakout."""
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=92),   # bullish: R=110, S=92
        make_candle(2, high=110, low=93),   # high==R, low>S → inside (<=, >=)
    ]
    result = compute(candles)

    events_by_bar = {e.bar_index: e for e in result.debug_events}
    assert events_by_bar[2].action == "inside_container"


def test_equal_low_boundary_is_inside():
    """low == temp_support is inside_container, not bearish_breakout."""
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=95, low=82),    # bearish: R=95, S=82
        make_candle(2, high=94, low=82),    # low==S, high<R → inside
    ]
    result = compute(candles)

    events_by_bar = {e.bar_index: e for e in result.debug_events}
    assert events_by_bar[2].action == "inside_container"


# ---------------------------------------------------------------------------
# 8 & 9 & 10. API integration: default V1, explicit V3, unknown → 400
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient
from backend.api.main import app
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User

_ACTIVE_USER = User(
    user_id="test-user-v3",
    username="v3tester",
    email="v3test@example.com",
    password_hash="x",
    created_at="2025-01-01T00:00:00+00:00",
    subscription_status="active",
)


@pytest.fixture()
def auth_client():
    app.dependency_overrides[require_active_subscription] = lambda: _ACTIVE_USER
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _candle_payload() -> list[dict]:
    prices = [
        (100, 90), (110, 92), (108, 80), (115, 82), (112, 70),
        (120, 75), (115, 65), (125, 68), (122, 60), (130, 63),
    ]
    return [
        {
            "timestamp": f"2024-01-{i + 1:02d}T00:00:00Z",
            "open": (h + l) / 2,
            "high": h,
            "low": l,
            "close": (h + l) / 2,
            "volume": 1000.0,
        }
        for i, (h, l) in enumerate(prices)
    ]


def _post_structure(client, engine_id=None):
    body: dict = {"candles": _candle_payload()}
    if engine_id is not None:
        body["engine_id"] = engine_id
    return client.post("/chart/market-structure", json=body)


def test_default_engine_is_v1(auth_client):
    """Omitting engine_id uses minor_structure_v1 (200, valid structure)."""
    r = _post_structure(auth_client)
    assert r.status_code == 200
    data = r.json()
    assert "minor_points" in data
    assert "minor_legs" in data


def test_explicit_v3_returns_200(auth_client):
    """engine_id=minor_structure_v3 returns 200 with valid structure."""
    r = _post_structure(auth_client, engine_id="minor_structure_v3")
    assert r.status_code == 200
    data = r.json()
    assert "minor_points" in data
    assert "minor_legs" in data
    assert "debug_events" in data


def test_v3_debug_events_contain_container_actions(auth_client):
    """V3 debug events use container classification action names."""
    r = _post_structure(auth_client, engine_id="minor_structure_v3")
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()["debug_events"]}
    v3_actions = {"startup", "inside_container", "outside_container",
                  "bullish_breakout", "bearish_breakout"}
    assert actions & v3_actions, f"No V3 actions found; got {actions}"


def test_unknown_engine_id_returns_400(auth_client):
    """Unknown engine_id returns HTTP 400 with descriptive error."""
    r = _post_structure(auth_client, engine_id="minor_structure_v999")
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "minor_structure_v999" in detail or "Unknown" in detail

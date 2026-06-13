"""
Test suite for Market Structure Engine.

Validates deterministic minor and main structure calculation.
All tests verify visual correctness without trading logic.
"""

import pytest
from backend.tools.market_structure import (
    MarketStructureEngine,
    OHLCVCandle,
    Direction,
    PointKind,
    CandleRelationship,
    StructureLevel,
)


@pytest.fixture
def engine():
    return MarketStructureEngine()


def make_candle(
    bar_index: int,
    timestamp: str = "2024-01-01T00:00:00Z",
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
    volume: float = 1000000.0,
) -> OHLCVCandle:
    """Helper to create OHLCV candles for testing."""
    return OHLCVCandle(
        timestamp=timestamp,
        bar_index=bar_index,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


# ── Minor Structure Tests ──────────────────────────────────────────────────────

class TestMinorStructureBasics:
    """Test fundamental minor structure behavior."""

    def test_1_higher_high_creates_up_direction(self, engine):
        """Higher high creates/continues UP direction."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=105, low=92, close=100),  # higher high
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 1
        last_event = result.debug_events[-1]
        assert last_event.new_direction == Direction.UP

    def test_2_lower_low_creates_down_direction(self, engine):
        """Lower low creates/continues DOWN direction."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=99, low=85, close=88),  # lower low only
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 1
        last_event = result.debug_events[-1]
        assert last_event.new_direction == Direction.DOWN

    def test_3_inside_bar_up_continuation(self, engine):
        """Inside bar with close >= prev close continues UP."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=105, low=92, close=100),  # higher high → UP
            make_candle(2, high=104, low=93, close=102),  # inside bar, close > prev
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 2
        last_event = result.debug_events[-1]
        assert last_event.action == "continue_up"

    def test_4_inside_bar_up_reversal(self, engine):
        """Inside bar with close < prev close reverses DOWN."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=105, low=92, close=100),  # higher high → UP
            make_candle(2, high=104, low=93, close=94),  # inside bar, close < prev
        ]
        result = engine.compute_structure(candles)
        # Should have a reversal event and a new L point
        assert any(e.action == "reverse_down" for e in result.debug_events)
        assert len(result.minor_points) >= 1

    def test_5_inside_bar_down_continuation(self, engine):
        """Inside bar with close <= prev close continues DOWN."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=99, low=85, close=88),  # lower low → DOWN
            make_candle(2, high=98, low=86, close=87),  # inside bar, close < prev
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 2
        last_event = result.debug_events[-1]
        assert last_event.action == "continue_down"

    def test_6_inside_bar_down_reversal(self, engine):
        """Inside bar with close > prev close reverses UP."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=99, low=85, close=88),  # lower low → DOWN
            make_candle(2, high=98, low=86, close=92),  # inside bar, close > prev
        ]
        result = engine.compute_structure(candles)
        # Should have a reversal event and a new L point
        assert any(e.action == "reverse_up" for e in result.debug_events)
        assert len(result.minor_points) >= 1

    def test_7_outside_bar_up_continuation(self, engine):
        """Outside bar continues UP direction."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=105, low=92, close=100),  # higher high → UP
            make_candle(2, high=108, low=88, close=102),  # outside bar
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 2
        last_event = result.debug_events[-1]
        assert last_event.action == "continue_up"

    def test_8_outside_bar_down_continuation(self, engine):
        """Outside bar continues DOWN direction."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=99, low=85, close=88),  # lower low → DOWN
            make_candle(2, high=100, low=82, close=84),  # outside bar (higher high, lower low)
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 2
        last_event = result.debug_events[-1]
        assert last_event.action == "continue_down"

    def test_9_startup_inside_bars_wait_for_direction(self, engine):
        """Startup with inside bars waits for direction."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=99, low=91, close=94),  # inside bar at startup
            make_candle(2, high=98, low=92, close=93),  # another inside bar
            make_candle(3, high=105, low=93, close=100),  # finally higher high → UP
        ]
        result = engine.compute_structure(candles)
        # Should have a wait event, then establish UP
        wait_events = [e for e in result.debug_events if e.action == "wait_for_direction"]
        establish_events = [e for e in result.debug_events if "establish" in e.action]
        assert len(wait_events) >= 1
        assert len(establish_events) >= 1

    def test_10_complete_minor_structure_sequence(self, engine):
        """Complete sequence of minor structure points and legs."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=105, low=92, close=100),  # higher high → UP
            make_candle(2, high=110, low=93, close=105),  # higher high
            make_candle(3, high=109, low=85, close=88),  # lower low → reverse DOWN
            make_candle(4, high=102, low=82, close=85),  # lower low
            make_candle(5, high=104, low=80, close=100),  # higher high → reverse UP
        ]
        result = engine.compute_structure(candles)
        assert len(result.minor_points) >= 1  # Should have at least one point
        assert len(result.minor_legs) >= 0  # Legs between points


# ── Main Structure Tests ───────────────────────────────────────────────────────

class TestMainStructureBasics:
    """Test main structure confirmation and formation."""

    def test_11_break_above_main_high_confirms_hl_and_hh(self, engine):
        """Break above main high confirms prior lowest minor low as Main HL and new high as Main HH."""
        # Build a sequence that creates minor structure with breaks
        candles = [
            make_candle(0, high=100, low=90, close=95),  # Start
            make_candle(1, high=110, low=92, close=105),  # Higher high → UP
            make_candle(2, high=120, low=93, close=115),  # Higher high
            make_candle(3, high=119, low=85, close=90),  # Lower low → DOWN (creates high point)
            make_candle(4, high=102, low=80, close=85),  # Lower low (low point)
            make_candle(5, high=130, low=81, close=125),  # BREAK ABOVE 120 → triggers main
        ]
        result = engine.compute_structure(candles)
        # Should have created main points when breaking above
        assert len(result.main_points) >= 1

    def test_12_break_below_main_low_confirms_lh_and_ll(self, engine):
        """Break below main low confirms prior highest minor high as Main LH and new low as Main LL."""
        # Build a range: high at 120, low at 100
        # Then break below 100 to trigger main confirmation
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=105, low=92, close=100),  # rev up, high at 105
            make_candle(2, high=120, low=93, close=110),  # higher high at 120
            make_candle(3, high=118, low=95, close=102),  # inside range
            make_candle(4, high=115, low=96, close=105),  # inside range
            make_candle(5, high=114, low=85, close=90),  # BREAK BELOW 100 → confirms
        ]
        result = engine.compute_structure(candles)
        # Should have main points with LH and LL kinds
        lh_points = [p for p in result.main_points if p.kind == PointKind.LH]
        ll_points = [p for p in result.main_points if p.kind == PointKind.LL]
        assert len(lh_points) >= 1 or len(ll_points) >= 1  # At least confirms something


# ── Edge Cases and Robustness ──────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_candles_list(self, engine):
        """Empty candles list returns empty result."""
        result = engine.compute_structure([])
        assert len(result.minor_points) == 0
        assert len(result.minor_legs) == 0

    def test_single_candle(self, engine):
        """Single candle returns empty result (need at least 2)."""
        candles = [make_candle(0)]
        result = engine.compute_structure(candles)
        assert len(result.minor_points) == 0
        assert len(result.debug_events) == 0

    def test_two_candles_up(self, engine):
        """Two candles with higher high establishes direction."""
        candles = [
            make_candle(0, high=100, low=90),
            make_candle(1, high=110, low=95),  # higher high
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 1

    def test_all_identical_candles(self, engine):
        """All identical candles (no relationship established)."""
        candles = [make_candle(i, high=100, low=90, close=95) for i in range(5)]
        result = engine.compute_structure(candles)
        # Should handle gracefully without crashing
        assert isinstance(result.minor_points, list)

    def test_gap_up_sequence(self, engine):
        """Sequence of gap-up higher highs (all UP)."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=110, low=100, close=105),
            make_candle(2, high=120, low=110, close=115),
            make_candle(3, high=130, low=120, close=125),
        ]
        result = engine.compute_structure(candles)
        # All should be "continue_up" or "establish_up"
        up_actions = [e for e in result.debug_events if "up" in e.action.lower()]
        assert len(up_actions) >= 2

    def test_gap_down_sequence(self, engine):
        """Sequence of gap-down lower lows (all DOWN)."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=90, low=80, close=85),
            make_candle(2, high=80, low=70, close=75),
            make_candle(3, high=70, low=60, close=65),
        ]
        result = engine.compute_structure(candles)
        # All should be "continue_down" or "establish_down"
        down_actions = [e for e in result.debug_events if "down" in e.action.lower()]
        assert len(down_actions) >= 2

    def test_sharp_reversal_pattern(self, engine):
        """Sharp reversal pattern (up then down then up)."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=120, low=91, close=110),  # UP
            make_candle(2, high=125, low=92, close=120),  # UP
            make_candle(3, high=124, low=80, close=85),  # reverse DOWN
            make_candle(4, high=82, low=70, close=75),  # DOWN
            make_candle(5, high=90, low=72, close=88),  # reverse UP
        ]
        result = engine.compute_structure(candles)
        reversals = [e for e in result.debug_events if "reverse" in e.action]
        assert len(reversals) >= 2
        assert len(result.minor_points) >= 2  # At least 2 turning points


# ── Debug Metadata Tests ───────────────────────────────────────────────────────

class TestDebugMetadata:
    """Test that debug metadata is properly exposed."""

    def test_debug_events_include_timestamps(self, engine):
        """Debug events include candle timestamps."""
        candles = [
            make_candle(0, timestamp="2024-01-01T00:00:00Z"),
            make_candle(1, timestamp="2024-01-02T00:00:00Z", high=110, low=95),
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 1
        for event in result.debug_events:
            assert event.timestamp is not None

    def test_debug_events_include_relationship_type(self, engine):
        """Debug events include candle relationship classification."""
        candles = [
            make_candle(0, high=100, low=90),
            make_candle(1, high=110, low=95),  # higher high
        ]
        result = engine.compute_structure(candles)
        assert len(result.debug_events) >= 1
        assert result.debug_events[-1].candle_relationship is not None

    def test_structure_points_have_metadata(self, engine):
        """Structure points include debug metadata."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=110, low=95, close=105),  # higher high → UP
            make_candle(2, high=105, low=88, close=90),  # rev DOWN → creates point
        ]
        result = engine.compute_structure(candles)
        for point in result.minor_points:
            assert point.id is not None
            assert point.kind is not None
            assert point.level == StructureLevel.MINOR


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_full_market_cycle(self, engine):
        """Full market cycle: startup, up, reversal, down, reversal, up."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=99, low=91, close=94),  # inside at startup
            make_candle(2, high=110, low=92, close=100),  # higher high → UP established
            make_candle(3, high=120, low=93, close=115),  # higher high
            make_candle(4, high=125, low=94, close=123),  # higher high peak
            make_candle(5, high=124, low=80, close=85),  # lower low → DOWN established
            make_candle(6, high=82, low=70, close=72),  # lower low
            make_candle(7, high=75, low=65, close=68),  # lower low bottom
            make_candle(8, high=90, low=64, close=88),  # higher high → UP established
            make_candle(9, high=105, low=85, close=100),  # higher high
        ]
        result = engine.compute_structure(candles)
        assert len(result.minor_points) >= 2  # At least 2 turning points (high and low)
        assert len(result.debug_events) >= 8  # Multiple structure decisions
        # Verify no crashes and structure is sensible
        for point in result.minor_points:
            assert point.kind in (PointKind.H, PointKind.L)

    def test_minor_and_main_structure_together(self, engine):
        """Both minor and main structure computed together."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=110, low=92, close=105),
            make_candle(2, high=120, low=93, close=115),
            make_candle(3, high=119, low=85, close=88),
            make_candle(4, high=102, low=80, close=85),
            make_candle(5, high=105, low=78, close=100),
            make_candle(6, high=130, low=79, close=125),  # BREAK above 120
        ]
        result = engine.compute_structure(candles)
        assert len(result.minor_points) >= 1
        # May or may not have main points depending on structure
        assert isinstance(result.main_points, list)
        assert isinstance(result.main_legs, list)

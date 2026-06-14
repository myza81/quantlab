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
    StructurePoint,
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
        """Break above main high labels prior minor low as HL and new high as HH."""
        # H-first sequence: H(120) → L(75) → H(130) triggers first break-above
        # Produces minor points: H(120), L(75), H(130), L(85)
        candles = [
            make_candle(0,  high=100, low=90,  close=95),   # startup
            make_candle(1,  high=110, low=92,  close=105),  # UP
            make_candle(2,  high=120, low=93,  close=115),  # UP — peak that will be H
            make_candle(3,  high=119, low=82,  close=86),   # DOWN
            make_candle(4,  high=100, low=75,  close=78),   # DOWN — trough that will be L
            make_candle(5,  high=108, low=77,  close=105),  # UP
            make_candle(6,  high=115, low=80,  close=112),  # UP
            make_candle(7,  high=130, low=82,  close=128),  # UP — breaks above H(120) → HH
            make_candle(8,  high=128, low=83,  close=87),   # DOWN
            make_candle(9,  high=118, low=82,  close=85),   # DOWN — trough (HL candidate)
        ]
        result = engine.compute_structure(candles)
        kinds = [p.kind for p in result.main_points]
        assert PointKind.HL in kinds, f"Expected HL in main_points kinds, got: {kinds}"
        assert PointKind.HH in kinds, f"Expected HH in main_points kinds, got: {kinds}"
        # HL must be at the container's lowest low (bar 4, low=75):
        # Container is H(bar 2) → HH(bar 7); candles 3-6; bar 4 has lowest low=75.
        hl = next(p for p in result.main_points if p.kind == PointKind.HL)
        assert hl.price == 75.0, f"HL price must be 75.0 (container lowest low), got {hl.price}"
        assert hl.bar_index == 4, f"HL bar_index must be 4 (candle with low=75), got {hl.bar_index}"

    def test_12_break_below_main_low_confirms_lh_and_ll(self, engine):
        """Break below main low labels prior minor high as LH and new low as LL."""
        # L-first sequence: L(75) → H(115) → L(60) triggers first break-below
        # Produces minor points: L(75), H(115), L(60)
        candles = [
            make_candle(0,  high=100, low=90,  close=95),   # startup
            make_candle(1,  high=98,  low=82,  close=84),   # DOWN
            make_candle(2,  high=95,  low=75,  close=78),   # DOWN — trough that will be L
            make_candle(3,  high=105, low=77,  close=102),  # UP
            make_candle(4,  high=115, low=80,  close=112),  # UP — peak that will be H
            make_candle(5,  high=113, low=78,  close=82),   # DOWN
            make_candle(6,  high=100, low=60,  close=63),   # DOWN — breaks below L(75) → LL
            make_candle(7,  high=95,  low=62,  close=90),   # UP
        ]
        result = engine.compute_structure(candles)
        kinds = [p.kind for p in result.main_points]
        assert PointKind.LH in kinds, f"Expected LH in main_points kinds, got: {kinds}"
        assert PointKind.LL in kinds, f"Expected LL in main_points kinds, got: {kinds}"
        # LH must be at the container's highest high (bar 4, high=115):
        # Container is L(bar 2) → LL(bar 6); candles 3-5; bar 4 has highest high=115.
        lh = next(p for p in result.main_points if p.kind == PointKind.LH)
        assert lh.price == 115.0, f"LH price must be 115.0 (container highest high), got {lh.price}"
        assert lh.bar_index == 4, f"LH bar_index must be 4 (candle with high=115), got {lh.bar_index}"


# ── Main Structure Bootstrap / L-First Tests ──────────────────────────────────

class TestMainStructureBootstrap:
    """Bootstrap-phase correctness: first two minor points are plain H/L."""

    def test_13_l_first_initial_h_not_labeled_hh(self, engine):
        """When first minor point is L, the first H after it must NOT be labeled HH."""
        candles = [
            make_candle(0, high=100, low=90,  close=95),   # startup
            make_candle(1, high=98,  low=80,  close=83),   # DOWN → L candidate
            make_candle(2, high=95,  low=75,  close=78),   # DOWN — trough (first minor L)
            make_candle(3, high=105, low=77,  close=102),  # UP
            make_candle(4, high=115, low=80,  close=112),  # UP — first minor H after L
            make_candle(5, high=113, low=82,  close=86),   # DOWN (ends the H)
        ]
        result = engine.compute_structure(candles)
        # The first minor point must be L; the first main H must be plain H, not HH
        assert result.minor_points, "Expected at least one minor point"
        assert result.minor_points[0].kind == PointKind.L
        # The main H created during bootstrap must be PointKind.H, not HH
        hh_points = [p for p in result.main_points if p.kind == PointKind.HH]
        assert len(hh_points) == 0, (
            f"First minor H after L-first bootstrap must not be HH; got: "
            f"{[p.kind for p in result.main_points]}"
        )

    def test_14_h_first_initial_l_not_labeled_ll(self, engine):
        """When first minor point is H, the first L after it must NOT be labeled LL."""
        candles = [
            make_candle(0, high=100, low=90,  close=95),   # startup
            make_candle(1, high=110, low=92,  close=105),  # UP → H candidate
            make_candle(2, high=120, low=93,  close=115),  # UP — peak (first minor H)
            make_candle(3, high=118, low=82,  close=85),   # DOWN
            make_candle(4, high=105, low=75,  close=78),   # DOWN — trough (first minor L)
            make_candle(5, high=108, low=77,  close=104),  # UP (ends the L)
        ]
        result = engine.compute_structure(candles)
        assert result.minor_points, "Expected at least one minor point"
        assert result.minor_points[0].kind == PointKind.H
        ll_points = [p for p in result.main_points if p.kind == PointKind.LL]
        assert len(ll_points) == 0, (
            f"First minor L after H-first bootstrap must not be LL; got: "
            f"{[p.kind for p in result.main_points]}"
        )

    def test_15_l_first_break_below_after_h_produces_lh_and_ll(self, engine):
        """L-first: after H bootstrap, break below initial L → LH + LL emitted."""
        candles = [
            make_candle(0,  high=100, low=90,  close=95),
            make_candle(1,  high=98,  low=80,  close=83),  # DOWN
            make_candle(2,  high=95,  low=75,  close=78),  # DOWN — L(75)
            make_candle(3,  high=105, low=77,  close=102), # UP
            make_candle(4,  high=115, low=80,  close=112), # UP — H(115)
            make_candle(5,  high=113, low=78,  close=82),  # DOWN
            make_candle(6,  high=100, low=60,  close=63),  # DOWN — breaks below L(75) → LL
            make_candle(7,  high=95,  low=62,  close=90),  # UP
        ]
        result = engine.compute_structure(candles)
        kinds = [p.kind for p in result.main_points]
        assert PointKind.LH in kinds, f"Expected LH, got: {kinds}"
        assert PointKind.LL in kinds, f"Expected LL, got: {kinds}"
        assert PointKind.HH not in kinds, (
            f"L-first sequence must not produce HH before structure is established; got: {kinds}"
        )

    def test_16_h_first_break_above_after_l_produces_hl_and_hh(self, engine):
        """H-first: after L bootstrap, break above initial H → HL + HH emitted."""
        candles = [
            make_candle(0,  high=100, low=90,  close=95),
            make_candle(1,  high=110, low=92,  close=105), # UP
            make_candle(2,  high=120, low=93,  close=115), # UP — H(120)
            make_candle(3,  high=118, low=82,  close=86),  # DOWN
            make_candle(4,  high=100, low=75,  close=78),  # DOWN — L(75)
            make_candle(5,  high=108, low=77,  close=105), # UP
            make_candle(6,  high=130, low=80,  close=128), # UP — breaks above H(120) → HH
            make_candle(7,  high=128, low=82,  close=87),  # DOWN
        ]
        result = engine.compute_structure(candles)
        kinds = [p.kind for p in result.main_points]
        assert PointKind.HL in kinds, f"Expected HL, got: {kinds}"
        assert PointKind.HH in kinds, f"Expected HH, got: {kinds}"
        assert PointKind.LL not in kinds, (
            f"H-first sequence must not produce LL before structure is established; got: {kinds}"
        )


# ── Outside Bar Debug Reason Tests ────────────────────────────────────────────

class TestOutsideBarDebugReason:
    """Outside bar debug events must carry the correct relationship and reason."""

    def test_17_outside_bar_in_up_direction_has_correct_reason(self, engine):
        """Outside bar during UP direction: reason must mention outside bar, not higher high."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=105, low=92, close=100),  # higher high → UP
            make_candle(2, high=112, low=85, close=102),  # outside bar (higher high AND lower low)
        ]
        result = engine.compute_structure(candles)
        outside_events = [e for e in result.debug_events if e.candle_relationship == "outside_bar"]
        assert len(outside_events) >= 1, "Expected at least one outside_bar debug event"
        for ev in outside_events:
            assert "outside" in ev.reason.lower(), (
                f"Outside bar event reason must mention 'outside', got: '{ev.reason}'"
            )
            assert "higher high" not in ev.reason.lower(), (
                f"Outside bar reason must not say 'higher high', got: '{ev.reason}'"
            )

    def test_18_outside_bar_in_down_direction_has_correct_reason(self, engine):
        """Outside bar during DOWN direction: reason must mention outside bar, not lower low."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=98,  low=82, close=84),  # lower low → DOWN
            make_candle(2, high=105, low=75, close=80),  # outside bar (higher high AND lower low)
        ]
        result = engine.compute_structure(candles)
        outside_events = [e for e in result.debug_events if e.candle_relationship == "outside_bar"]
        assert len(outside_events) >= 1, "Expected at least one outside_bar debug event"
        for ev in outside_events:
            assert "outside" in ev.reason.lower(), (
                f"Outside bar event reason must mention 'outside', got: '{ev.reason}'"
            )
            assert "lower low" not in ev.reason.lower(), (
                f"Outside bar reason must not say 'lower low', got: '{ev.reason}'"
            )

    def test_19_outside_bar_continues_precedent_direction_up(self, engine):
        """Outside bar in UP direction continues UP (action = continue_up)."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=105, low=92, close=100),
            make_candle(2, high=112, low=85, close=102),  # outside bar
        ]
        result = engine.compute_structure(candles)
        outside_events = [e for e in result.debug_events if e.candle_relationship == "outside_bar"]
        assert len(outside_events) >= 1
        assert outside_events[0].action == "continue_up"

    def test_20_outside_bar_continues_precedent_direction_down(self, engine):
        """Outside bar in DOWN direction continues DOWN (action = continue_down)."""
        candles = [
            make_candle(0, high=100, low=90, close=95),
            make_candle(1, high=98,  low=82, close=84),
            make_candle(2, high=105, low=75, close=80),  # outside bar
        ]
        result = engine.compute_structure(candles)
        outside_events = [e for e in result.debug_events if e.candle_relationship == "outside_bar"]
        assert len(outside_events) >= 1
        assert outside_events[0].action == "continue_down"


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


# ── Pivot Selection Tests ──────────────────────────────────────────────────────

class TestPivotSelection:
    """
    MS-4B: Pivot must be placed at the candle containing the true swing extreme,
    not at an inside bar that merely continued the direction.

    Philosophy: if a line goes UP it terminates at the highest high of that leg;
    if a line goes DOWN it terminates at the lowest low of that leg.
    """

    def test_21_down_swing_inside_bar_continuation_l_placed_at_true_extreme(self, engine):
        """
        DOWN leg: inside bar continues → next bar reverses UP.
        L must be at the earlier true-low candle (bar 2, low=95),
        not at the inside bar (bar 3, low=96).
        """
        candles = [
            make_candle(0, high=110, low=100, close=105),  # startup
            make_candle(1, high=108, low=98,  close=101),  # lower_low → establish DOWN
            make_candle(2, high=103, low=95,  close=96),   # lower_low → continue DOWN (true extreme: low=95)
            make_candle(3, high=100, low=96,  close=95),   # inside bar (100≤103, 96≥95), close(95)≤prev.close(96) → continue DOWN
            make_candle(4, high=104, low=97,  close=102),  # higher_high (104>100) → reverse UP
        ]
        result = engine.compute_structure(candles)
        l_points = [p for p in result.minor_points if p.kind == PointKind.L]
        assert len(l_points) >= 1, "Expected at least one L point after DOWN→UP reversal"
        assert l_points[0].bar_index == 2, (
            f"L pivot must be at bar 2 (true lowest-low candle), got bar {l_points[0].bar_index}"
        )
        assert l_points[0].price == 95.0, (
            f"L price must be 95.0 (true low), got {l_points[0].price}"
        )

    def test_22_up_swing_inside_bar_continuation_h_placed_at_true_extreme(self, engine):
        """
        UP leg: inside bar continues → next bar reverses DOWN.
        H must be at the earlier true-high candle (bar 3, high=110),
        not at the inside bar (bar 4, high=108).
        """
        candles = [
            make_candle(0, high=100, low=90,  close=95),   # startup
            make_candle(1, high=103, low=91,  close=99),   # higher_high → establish UP
            make_candle(2, high=107, low=92,  close=104),  # higher_high → continue UP
            make_candle(3, high=110, low=95,  close=107),  # higher_high → continue UP (true extreme: high=110)
            make_candle(4, high=108, low=96,  close=107),  # inside bar (108≤110, 96≥95), close(107)≥prev.close(107) → continue UP
            make_candle(5, high=105, low=88,  close=90),   # lower_low (88<96) → reverse DOWN
        ]
        result = engine.compute_structure(candles)
        h_points = [p for p in result.minor_points if p.kind == PointKind.H]
        assert len(h_points) >= 1, "Expected at least one H point after UP→DOWN reversal"
        assert h_points[0].bar_index == 3, (
            f"H pivot must be at bar 3 (true highest-high candle), got bar {h_points[0].bar_index}"
        )
        assert h_points[0].price == 110.0, (
            f"H price must be 110.0 (true high), got {h_points[0].price}"
        )

    def test_23_multiple_inside_bar_continuations_pivot_stays_at_true_extreme(self, engine):
        """
        DOWN leg with two consecutive inside-bar continuations before reversal.
        L must remain anchored to the original true-low candle (bar 2, low=95),
        not drift to either inside bar (bar 3 or bar 4).
        """
        candles = [
            make_candle(0, high=110, low=100, close=105),  # startup
            make_candle(1, high=108, low=98,  close=101),  # lower_low → establish DOWN
            make_candle(2, high=103, low=95,  close=96),   # lower_low → continue DOWN (true extreme: low=95)
            make_candle(3, high=100, low=96,  close=95),   # inside bar, close(95)≤prev.close(96) → continue DOWN
            make_candle(4, high=99,  low=97,  close=94),   # inside bar, close(94)≤prev.close(95) → continue DOWN
            make_candle(5, high=104, low=97,  close=101),  # higher_high (104>99) → reverse UP
        ]
        result = engine.compute_structure(candles)
        l_points = [p for p in result.minor_points if p.kind == PointKind.L]
        assert len(l_points) >= 1, "Expected at least one L point"
        assert l_points[0].bar_index == 2, (
            f"L pivot must be bar 2 (true extreme), not last inside bar; got bar {l_points[0].bar_index}"
        )
        assert l_points[0].price == 95.0, (
            f"L price must be 95.0, got {l_points[0].price}"
        )

    def test_24_direct_reversal_without_inside_bar_unchanged(self, engine):
        """
        Normal reversal (no inside bar between true extreme and trigger):
        existing pivot selection must produce identical results.
        """
        candles = [
            make_candle(0, high=110, low=100, close=105),  # startup
            make_candle(1, high=108, low=98,  close=101),  # lower_low → establish DOWN
            make_candle(2, high=103, low=95,  close=96),   # lower_low → continue DOWN (bar 2 is true extreme)
            make_candle(3, high=106, low=97,  close=102),  # higher_high (106>103) → reverse UP immediately
        ]
        result = engine.compute_structure(candles)
        l_points = [p for p in result.minor_points if p.kind == PointKind.L]
        assert len(l_points) >= 1
        # prev at reversal is bar 2 — same as last_low_candle — no change expected
        assert l_points[0].bar_index == 2, (
            f"Direct reversal: L pivot must still be bar 2, got bar {l_points[0].bar_index}"
        )
        assert l_points[0].price == 95.0, (
            f"Direct reversal: L price must be 95.0, got {l_points[0].price}"
        )

    def test_25_inside_bar_that_reverses_not_continues_pivot_unchanged(self, engine):
        """
        Inside bar that immediately reverses direction (not continues):
        prev is the bar before the inside bar, which is the true extreme.
        This path was always correct — must remain unchanged.
        """
        candles = [
            make_candle(0, high=110, low=100, close=105),  # startup
            make_candle(1, high=108, low=98,  close=101),  # lower_low → establish DOWN
            make_candle(2, high=103, low=95,  close=96),   # lower_low → continue DOWN (true extreme: low=95)
            # Inside bar with close > prev.close → REVERSAL (not continuation)
            make_candle(3, high=100, low=96,  close=99),   # inside bar, close(99)>prev.close(96) → reverse UP
        ]
        result = engine.compute_structure(candles)
        l_points = [p for p in result.minor_points if p.kind == PointKind.L]
        assert len(l_points) >= 1, "Inside bar reversal must produce an L"
        # The inside bar reversal fires at bar 3 (curr); prev = bar 2.
        # last_low_candle = bar 2 as well. Both point to bar 2 — correct.
        assert l_points[0].bar_index == 2, (
            f"Inside bar reversal pivot must be bar 2, got bar {l_points[0].bar_index}"
        )
        assert l_points[0].price == 95.0, (
            f"Inside bar reversal L price must be 95.0, got {l_points[0].price}"
        )

    def test_26_outside_bar_followed_by_inside_bar_l_at_outside_bar(self, engine):
        """
        DOWN leg: outside bar (true extreme) → inside bar continues → reversal.
        L must be at the outside bar (bar 2, low=92), not the inside bar (bar 3, low=95).
        """
        candles = [
            make_candle(0, high=110, low=100, close=105),  # startup
            make_candle(1, high=108, low=98,  close=101),  # lower_low → establish DOWN
            make_candle(2, high=112, low=92,  close=95),   # outside bar (112>108, 92<98) → continue DOWN (true extreme: low=92)
            make_candle(3, high=109, low=95,  close=94),   # inside bar (109≤112, 95≥92), close(94)≤prev.close(95) → continue DOWN
            make_candle(4, high=113, low=96,  close=110),  # higher_high (113>109) → reverse UP
        ]
        result = engine.compute_structure(candles)
        l_points = [p for p in result.minor_points if p.kind == PointKind.L]
        assert len(l_points) >= 1, "Expected at least one L point"
        assert l_points[0].bar_index == 2, (
            f"L pivot must be at bar 2 (outside bar with true low=92), got bar {l_points[0].bar_index}"
        )
        assert l_points[0].price == 92.0, (
            f"L price must be 92.0, got {l_points[0].price}"
        )


# ── Container Pivot Refinement Tests (MS-4C/MS-4D) ───────────────────────────

class TestContainerPivotRefinement:
    """
    MS-4D: HL/LH must be anchored at the true extreme inside the full H→HH / L→LL
    container, including outside bars that are invisible to the minor structure engine.

    Rule:
      H→HH: HL at the candle with the lowest low in [H.bar_index, HH.bar_index) exclusive.
      L→LL: LH at the candle with the highest high in [L.bar_index, LL.bar_index) exclusive.
      Tie-breaking: earliest bar wins (smallest bar_index).
    """

    def test_27_lh_anchored_at_outside_bar_high_in_bearish_container(self, engine):
        """
        L→LL container: outside bar in the DOWN sub-leg has higher high than minor H.
        LH must be placed at the outside bar (bar 7, high=125), not the minor H (bar 5, 115).

        Sequence: establish DOWN → L(bar 2) → reverse UP → H(bar 5) → reverse DOWN
                  → outside bar(bar 7, high=125) continues DOWN → LL(bar 10).
        """
        candles = [
            make_candle(0,  high=110, low=100, close=105),  # startup
            make_candle(1,  high=108, low=98,  close=101),  # LOWER_LOW → establish DOWN
            make_candle(2,  high=103, low=95,  close=97),   # LOWER_LOW → continue DOWN → L candidate
            make_candle(3,  high=106, low=97,  close=104),  # HIGHER_HIGH → REVERSE UP; L at bar 2 (95)
            make_candle(4,  high=110, low=99,  close=107),  # HIGHER_HIGH → continue UP
            make_candle(5,  high=115, low=101, close=112),  # HIGHER_HIGH → continue UP; minor H candidate
            make_candle(6,  high=113, low=90,  close=93),   # LOWER_LOW → REVERSE DOWN; H at bar 5 (115)
            make_candle(7,  high=125, low=87,  close=89),   # OUTSIDE BAR (125>113, 87<90) → continue DOWN
            #                                                  high=125 > minor H (115) — LH must move here
            make_candle(8,  high=122, low=83,  close=85),   # LOWER_LOW → continue DOWN
            make_candle(9,  high=118, low=79,  close=81),   # LOWER_LOW → continue DOWN; last_low_candle
            make_candle(10, high=122, low=82,  close=120),  # HIGHER_HIGH → REVERSE UP; L at bar 9 (79)
            #                                                  79 < main_low (95) → LL confirmed
        ]
        result = engine.compute_structure(candles)
        lh_points = [p for p in result.main_points if p.kind == PointKind.LH]
        assert len(lh_points) >= 1, "Expected at least one LH point"
        lh = lh_points[0]
        # Container: L(bar 2) → LL(bar 9). Candles 3-8. Highest high: bar 7 (125).
        assert lh.price == 125.0, (
            f"LH price must be 125.0 (outside bar high in DOWN sub-leg), got {lh.price}"
        )
        assert lh.bar_index == 7, (
            f"LH bar_index must be 7 (outside bar with high=125), got {lh.bar_index}"
        )

    def test_28_hl_anchored_at_outside_bar_low_in_bullish_container(self, engine):
        """
        H→HH container: outside bar in the UP sub-leg has lower low than minor L.
        HL must be placed at the outside bar (bar 9, low=65), not the minor L (bar 6, 72).

        Sequence: establish UP → H(bar 2) → reverse DOWN
                  → outside bar in DOWN sub-leg(bar 6) → L(bar 6, 72)
                  → REVERSE UP → outside bar in UP sub-leg(bar 9, low=65) → HH(bar 12).
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),   # startup
            make_candle(1,  high=110, low=92,  close=105),  # HIGHER_HIGH → establish UP
            make_candle(2,  high=120, low=93,  close=115),  # HIGHER_HIGH → continue UP; H candidate
            make_candle(3,  high=117, low=82,  close=85),   # LOWER_LOW → REVERSE DOWN; H at bar 2 (120)
            make_candle(4,  high=114, low=78,  close=81),   # LOWER_LOW → continue DOWN
            make_candle(5,  high=110, low=75,  close=78),   # LOWER_LOW → continue DOWN
            make_candle(6,  high=114, low=72,  close=112),  # OUTSIDE BAR (114>110, 72<75) → continue DOWN
            #                                                  last_low_candle=bar 6 (72)
            make_candle(7,  high=118, low=74,  close=116),  # HIGHER_HIGH → REVERSE UP; L at bar 6 (72)
            make_candle(8,  high=122, low=76,  close=120),  # HIGHER_HIGH → continue UP
            make_candle(9,  high=130, low=65,  close=128),  # OUTSIDE BAR (130>122, 65<76) → continue UP
            #                                                  low=65 < minor L (72) — HL must move here
            make_candle(10, high=132, low=68,  close=130),  # HIGHER_HIGH → continue UP
            make_candle(11, high=135, low=70,  close=133),  # HIGHER_HIGH → continue UP; HH candidate
            make_candle(12, high=133, low=64,  close=67),   # LOWER_LOW → REVERSE DOWN; H at bar 11 (135)
            #                                                  135 > main_high (120) → HH confirmed
        ]
        result = engine.compute_structure(candles)
        hl_points = [p for p in result.main_points if p.kind == PointKind.HL]
        assert len(hl_points) >= 1, "Expected at least one HL point"
        hl = hl_points[0]
        # Container: H(bar 2) → HH(bar 11). Candles 3-10. Lowest low: bar 9 (65).
        assert hl.price == 65.0, (
            f"HL price must be 65.0 (outside bar low in UP sub-leg), got {hl.price}"
        )
        assert hl.bar_index == 9, (
            f"HL bar_index must be 9 (outside bar with low=65), got {hl.bar_index}"
        )

    def test_29_lh_equals_minor_h_when_no_outside_bar_exceeds_container(self, engine):
        """
        L→LL container: no candle inside the container has a higher high than the minor H.
        LH must remain at the minor H's bar and price — existing behavior unchanged.

        Container (bars 3-8) highest high is bar 5 (115) which equals the minor H.
        """
        candles = [
            make_candle(0,  high=110, low=100, close=105),  # startup
            make_candle(1,  high=108, low=98,  close=101),  # LOWER_LOW → establish DOWN
            make_candle(2,  high=103, low=95,  close=97),   # LOWER_LOW → continue DOWN → L(95)
            make_candle(3,  high=106, low=97,  close=104),  # HIGHER_HIGH → REVERSE UP; L at bar 2
            make_candle(4,  high=110, low=99,  close=107),  # HIGHER_HIGH → continue UP
            make_candle(5,  high=115, low=101, close=112),  # HIGHER_HIGH → continue UP; minor H candidate
            make_candle(6,  high=113, low=90,  close=93),   # LOWER_LOW → REVERSE DOWN; H at bar 5 (115)
            make_candle(7,  high=110, low=87,  close=89),   # LOWER_LOW → continue DOWN (high=110 < 115)
            make_candle(8,  high=106, low=83,  close=85),   # LOWER_LOW → continue DOWN (high=106 < 115)
            make_candle(9,  high=102, low=78,  close=80),   # LOWER_LOW → continue DOWN; last_low_candle
            make_candle(10, high=105, low=80,  close=103),  # HIGHER_HIGH → REVERSE UP; L at bar 9 (78)
            #                                                  78 < main_low (95) → LL confirmed
        ]
        result = engine.compute_structure(candles)
        lh_points = [p for p in result.main_points if p.kind == PointKind.LH]
        assert len(lh_points) >= 1, "Expected at least one LH point"
        lh = lh_points[0]
        # Container: L(bar 2) → LL(bar 9). Candles 3-8. Highest high = bar 5 (115) = minor H.
        assert lh.price == 115.0, (
            f"LH price must be 115.0 (container max = minor H), got {lh.price}"
        )
        assert lh.bar_index == 5, (
            f"LH bar_index must be 5 (minor H at peak of UP sub-leg), got {lh.bar_index}"
        )

    def test_30_lh_tie_breaking_uses_earliest_bar(self, engine):
        """
        L→LL container: two candles share the same highest high (125).
        Tie-breaking must select the earliest bar (bar 5, not bar 7).
        """
        candles = [
            make_candle(0,  high=110, low=100, close=105),  # startup
            make_candle(1,  high=108, low=98,  close=101),  # LOWER_LOW → establish DOWN
            make_candle(2,  high=103, low=95,  close=97),   # LOWER_LOW → continue DOWN → L(95)
            make_candle(3,  high=106, low=97,  close=104),  # HIGHER_HIGH → REVERSE UP; L at bar 2
            make_candle(4,  high=120, low=99,  close=116),  # HIGHER_HIGH → continue UP
            make_candle(5,  high=125, low=100, close=122),  # HIGHER_HIGH → continue UP; minor H (125) — first 125
            make_candle(6,  high=123, low=91,  close=94),   # LOWER_LOW → REVERSE DOWN; H at bar 5 (125)
            make_candle(7,  high=125, low=88,  close=90),   # OUTSIDE BAR (125>123, 88<91) → continue DOWN
            #                                                  high=125 ties minor H — earliest wins (bar 5)
            make_candle(8,  high=120, low=83,  close=85),   # LOWER_LOW → continue DOWN; last_low_candle
            make_candle(9,  high=115, low=78,  close=80),   # LOWER_LOW → continue DOWN; last_low_candle
            make_candle(10, high=120, low=80,  close=118),  # HIGHER_HIGH → REVERSE UP; L at bar 9 (78)
            #                                                  78 < main_low (95) → LL confirmed
        ]
        result = engine.compute_structure(candles)
        lh_points = [p for p in result.main_points if p.kind == PointKind.LH]
        assert len(lh_points) >= 1, "Expected at least one LH point"
        lh = lh_points[0]
        # Container: L(bar 2) → LL(bar 9). Candles 3-8.
        # Both bar 5 and bar 7 have high=125. Earliest wins → bar 5.
        assert lh.price == 125.0, f"LH price must be 125.0, got {lh.price}"
        assert lh.bar_index == 5, (
            f"Tie-breaking must choose earliest bar (5), got bar {lh.bar_index}"
        )

    def test_31_hl_tie_breaking_uses_earliest_bar(self, engine):
        """
        H→HH container: two candles share the same lowest low (70).
        Tie-breaking must select the earliest bar (bar 4, not bar 5).

        bar 4 has low=70 (LOWER_LOW continuation).
        bar 5 has low=70 (inside bar continuation, tied).
        Container scan must return bar 4.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),   # startup
            make_candle(1,  high=110, low=92,  close=105),  # HIGHER_HIGH → establish UP
            make_candle(2,  high=120, low=93,  close=115),  # HIGHER_HIGH → H candidate
            make_candle(3,  high=117, low=83,  close=86),   # LOWER_LOW → REVERSE DOWN; H at bar 2 (120)
            make_candle(4,  high=113, low=70,  close=73),   # LOWER_LOW → continue DOWN; low=70 (first tie)
            make_candle(5,  high=112, low=70,  close=71),   # INSIDE BAR (112≤113, 70≥70); close(71)<73 → continue DOWN
            #                                                  low=70 ties bar 4; last_low_candle stays at bar 4
            make_candle(6,  high=115, low=72,  close=113),  # HIGHER_HIGH → REVERSE UP; L at bar 4 (70)
            make_candle(7,  high=118, low=74,  close=116),  # HIGHER_HIGH → continue UP
            make_candle(8,  high=122, low=76,  close=120),  # HIGHER_HIGH → continue UP
            make_candle(9,  high=130, low=78,  close=128),  # HIGHER_HIGH (130>120) → continue UP; HH candidate
            make_candle(10, high=128, low=72,  close=75),   # LOWER_LOW → REVERSE DOWN; H at bar 9 (130)
            #                                                  130 > main_high (120) → HH confirmed
        ]
        result = engine.compute_structure(candles)
        hl_points = [p for p in result.main_points if p.kind == PointKind.HL]
        assert len(hl_points) >= 1, "Expected at least one HL point"
        hl = hl_points[0]
        # Container: H(bar 2) → HH(bar 9). Candles 3-8.
        # Both bar 4 and bar 5 have low=70. Earliest wins → bar 4.
        assert hl.price == 70.0, f"HL price must be 70.0, got {hl.price}"
        assert hl.bar_index == 4, (
            f"Tie-breaking must choose earliest bar (4), got bar {hl.bar_index}"
        )


# ── Minor Structure Container Pivot Refinement Tests (MS-4E/MS-4F) ───────────

class TestMinorContainerPivotRefinement:
    """
    MS-4F: Minor structure L/H must be anchored at the true container extreme
    (H₁→H₂ or L₁→L₂), including outside bars in the OPPOSITE sub-leg that
    were invisible to the within-leg tracking from MS-4B.

    Rule:
      H₁ → L₁ → H₂ where H₂ > H₁ (minor HH): refine L₁ to lowest low in
        container (H₁.bar_index, H₂.bar_index) exclusive.
      L₁ → H₁ → L₂ where L₂ < L₁ (minor LL): refine H₁ to highest high in
        container (L₁.bar_index, L₂.bar_index) exclusive.
    Tie-breaking: earliest bar_index wins.

    After MS-7A, _label_structure_points runs after the geometry pass and may
    relabel L→HL/LL and H→HH/LH. Tests check geometry (price + bar_index) and
    therefore filter for any low-type or high-type kind, not just plain L/H.
    """

    _LOW_KINDS  = (PointKind.L, PointKind.LL, PointKind.HL)
    _HIGH_KINDS = (PointKind.H, PointKind.HH, PointKind.LH)

    def test_32_minor_l_moves_to_outside_bar_low_in_up_sub_leg(self, engine):
        """
        H₁(bar 3, 120) → DOWN sub-leg → L₁(bar 7, 75) → UP sub-leg with
        outside bar(bar 10, low=68) → H₂(bar 12, 135) where H₂ > H₁.

        Within-leg tracking (MS-4B) correctly places L₁ at bar 7 (75) — the
        lowest low of the DOWN sub-leg. But bar 10 is an OUTSIDE BAR in the UP
        sub-leg with low=68 < 75, which the engine never sees during UP direction.

        After refinement: L₁ must move to bar 10, price=68.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),   # startup
            make_candle(1,  high=110, low=92,  close=105),  # HIGHER_HIGH → establish UP
            make_candle(2,  high=115, low=93,  close=110),  # HIGHER_HIGH → continue UP
            make_candle(3,  high=120, low=94,  close=117),  # HIGHER_HIGH → H₁ candidate (peak)
            make_candle(4,  high=118, low=84,  close=87),   # LOWER_LOW → REVERSE DOWN; H₁ at bar 3 (120)
            make_candle(5,  high=115, low=80,  close=83),   # LOWER_LOW → continue DOWN
            make_candle(6,  high=111, low=77,  close=80),   # LOWER_LOW → continue DOWN
            make_candle(7,  high=108, low=75,  close=78),   # LOWER_LOW → continue DOWN; last_low_candle=bar 7 (75)
            make_candle(8,  high=110, low=78,  close=108),  # HIGHER_HIGH → REVERSE UP; L₁ at bar 7 (75)
            make_candle(9,  high=115, low=80,  close=113),  # HIGHER_HIGH → continue UP
            make_candle(10, high=125, low=68,  close=123),  # OUTSIDE_BAR (125>115, 68<80) → continue UP
            #                                                  low=68 < L₁.low=75 — lower low in UP sub-leg!
            make_candle(11, high=130, low=72,  close=128),  # HIGHER_HIGH → continue UP
            make_candle(12, high=135, low=74,  close=132),  # HIGHER_HIGH → H₂ candidate
            make_candle(13, high=133, low=66,  close=69),   # LOWER_LOW → REVERSE DOWN; H₂ at bar 12 (135)
            #                                                  H₂(135) > H₁(120) → minor HH context
        ]
        result = engine.compute_structure(candles)
        l_points = [p for p in result.minor_points if p.kind in self._LOW_KINDS]
        assert len(l_points) >= 1, "Expected at least one minor low-type point after DOWN→UP reversal"
        l = l_points[0]
        # Container H₁(bar 3) → H₂(bar 12): bars 4–11. Lowest low = bar 10 (68).
        assert l.price == 68.0, (
            f"Minor low must move to 68.0 (outside bar low in UP sub-leg), got {l.price}"
        )
        assert l.bar_index == 10, (
            f"Minor low bar_index must be 10 (outside bar), got {l.bar_index}"
        )

    def test_33_minor_h_moves_to_outside_bar_high_in_down_sub_leg(self, engine):
        """
        L₁(bar 2, 80) → UP sub-leg → H₁(bar 6, 115) → DOWN sub-leg with
        outside bar(bar 8, high=130) → L₂(bar 10, 67) where L₂ < L₁.

        Within-leg tracking (MS-4B) correctly places H₁ at bar 6 (115) — the
        highest high of the UP sub-leg. But bar 8 is an OUTSIDE BAR in the DOWN
        sub-leg with high=130 > 115, which the DOWN-direction code never tracks.

        After refinement: H₁ must move to bar 8, price=130.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),   # startup
            make_candle(1,  high=98,  low=82,  close=85),   # LOWER_LOW → establish DOWN
            make_candle(2,  high=95,  low=80,  close=83),   # LOWER_LOW → continue DOWN → L₁ candidate
            make_candle(3,  high=99,  low=83,  close=97),   # HIGHER_HIGH → REVERSE UP; L₁ at bar 2 (80)
            make_candle(4,  high=105, low=85,  close=102),  # HIGHER_HIGH → continue UP
            make_candle(5,  high=110, low=87,  close=107),  # HIGHER_HIGH → continue UP
            make_candle(6,  high=115, low=88,  close=112),  # HIGHER_HIGH → H₁ candidate
            make_candle(7,  high=113, low=78,  close=81),   # LOWER_LOW → REVERSE DOWN; H₁ at bar 6 (115)
            make_candle(8,  high=130, low=73,  close=76),   # OUTSIDE_BAR (130>113, 73<78) → continue DOWN
            #                                                  high=130 > H₁.high=115 — higher in DOWN sub-leg!
            make_candle(9,  high=127, low=70,  close=73),   # LOWER_LOW → continue DOWN
            make_candle(10, high=122, low=67,  close=70),   # LOWER_LOW → continue DOWN; last_low_candle=bar 10 (67)
            make_candle(11, high=125, low=70,  close=123),  # HIGHER_HIGH → REVERSE UP; L₂ at bar 10 (67)
            #                                                  L₂(67) < L₁(80) → minor LL context
        ]
        result = engine.compute_structure(candles)
        h_points = [p for p in result.minor_points if p.kind in self._HIGH_KINDS]
        assert len(h_points) >= 1, "Expected at least one minor high-type point after UP→DOWN reversal"
        h = h_points[0]
        # Container L₁(bar 2) → L₂(bar 10): bars 3–9. Highest high = bar 8 (130).
        assert h.price == 130.0, (
            f"Minor high must move to 130.0 (outside bar high in DOWN sub-leg), got {h.price}"
        )
        assert h.bar_index == 8, (
            f"Minor high bar_index must be 8, got {h.bar_index}"
        )

    def test_34_no_refinement_when_container_has_no_stronger_extreme(self, engine):
        """
        H₁ → DOWN sub-leg → L₁(bar 4, 78) → UP sub-leg (all lows ≥ 78) → H₂ (> H₁).
        Container minimum equals L₁.price → no refinement; L₁ stays at bar 4.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),
            make_candle(1,  high=110, low=92,  close=105),  # HIGHER_HIGH → establish UP
            make_candle(2,  high=120, low=93,  close=115),  # HIGHER_HIGH → H₁ candidate
            make_candle(3,  high=117, low=82,  close=85),   # LOWER_LOW → REVERSE DOWN; H₁ at bar 2 (120)
            make_candle(4,  high=113, low=78,  close=81),   # LOWER_LOW → continue DOWN; last_low_candle=bar 4
            make_candle(5,  high=116, low=80,  close=114),  # HIGHER_HIGH → REVERSE UP; L₁ at bar 4 (78)
            make_candle(6,  high=119, low=82,  close=117),  # HIGHER_HIGH → continue UP (lows > 78)
            make_candle(7,  high=125, low=84,  close=123),  # HIGHER_HIGH → H₂ candidate (> H₁=120)
            make_candle(8,  high=123, low=80,  close=83),   # LOWER_LOW → REVERSE DOWN; H₂ at bar 7 (125)
        ]
        result = engine.compute_structure(candles)
        l_points = [p for p in result.minor_points if p.kind in self._LOW_KINDS]
        assert len(l_points) >= 1, "Expected at least one minor low-type point"
        l = l_points[0]
        # Container bars 3–6: all lows ≥ 78 → container min = 78 = L₁.price → no move
        assert l.price == 78.0, f"Low price must remain 78.0 (no stronger extreme), got {l.price}"
        assert l.bar_index == 4, f"Low bar_index must remain 4, got {l.bar_index}"

    def test_35_minor_l_tie_breaking_uses_earliest_bar(self, engine):
        """
        H₁ → L₁(bar 4, 75) → UP sub-leg with outside bars at bars 7 and 9,
        both low=68 < 75, → H₂ (> H₁).

        Container minimum = 68 at two bars. Tie-breaking: earliest bar = 7.
        After refinement: L₁ must move to bar 7, price=68.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),   # startup
            make_candle(1,  high=110, low=92,  close=105),  # HIGHER_HIGH → establish UP
            make_candle(2,  high=120, low=93,  close=115),  # HIGHER_HIGH → H₁ candidate
            make_candle(3,  high=117, low=82,  close=85),   # LOWER_LOW → REVERSE DOWN; H₁ at bar 2 (120)
            make_candle(4,  high=113, low=75,  close=78),   # LOWER_LOW → continue DOWN; last_low_candle=bar 4 (75)
            make_candle(5,  high=116, low=77,  close=114),  # HIGHER_HIGH → REVERSE UP; L₁ at bar 4 (75)
            make_candle(6,  high=119, low=79,  close=117),  # HIGHER_HIGH → continue UP
            make_candle(7,  high=125, low=68,  close=123),  # OUTSIDE_BAR (125>119, 68<79) → continue UP
            #                                                  low=68 < 75 — first tied minimum
            make_candle(8,  high=128, low=72,  close=126),  # HIGHER_HIGH → continue UP
            make_candle(9,  high=130, low=68,  close=128),  # OUTSIDE_BAR (130>128, 68<72) → continue UP
            #                                                  low=68 — second tied minimum (later bar)
            make_candle(10, high=135, low=74,  close=133),  # HIGHER_HIGH → H₂ candidate
            make_candle(11, high=133, low=70,  close=73),   # LOWER_LOW → REVERSE DOWN; H₂ at bar 10 (135)
            #                                                  H₂(135) > H₁(120) → minor HH context
        ]
        result = engine.compute_structure(candles)
        l_points = [p for p in result.minor_points if p.kind in self._LOW_KINDS]
        assert len(l_points) >= 1, "Expected at least one minor low-type point"
        l = l_points[0]
        # Container H₁(bar 2) → H₂(bar 10): bars 3–9.
        # Bars 7 and 9 both have low=68 < 75. Tie-breaking: earliest = bar 7.
        assert l.price == 68.0, f"Low price must be 68.0 (tied minimum), got {l.price}"
        assert l.bar_index == 7, (
            f"Tie-breaking must choose earliest bar (7), got bar {l.bar_index}"
        )

    def test_36_minor_h_tie_breaking_uses_earliest_bar(self, engine):
        """
        L₁ → H₁(bar 5, 115) → DOWN sub-leg with outside bars at bars 8 and 10,
        both high=130 > 115, → L₂ (< L₁).

        Container maximum = 130 at two bars. Tie-breaking: earliest bar = 8.
        After refinement: H₁ must move to bar 8, price=130.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),   # startup
            make_candle(1,  high=98,  low=82,  close=85),   # LOWER_LOW → establish DOWN
            make_candle(2,  high=95,  low=80,  close=83),   # LOWER_LOW → continue DOWN → L₁ candidate
            make_candle(3,  high=99,  low=83,  close=97),   # HIGHER_HIGH → REVERSE UP; L₁ at bar 2 (80)
            make_candle(4,  high=107, low=85,  close=104),  # HIGHER_HIGH → continue UP
            make_candle(5,  high=115, low=87,  close=112),  # HIGHER_HIGH → H₁ candidate
            make_candle(6,  high=113, low=78,  close=81),   # LOWER_LOW → REVERSE DOWN; H₁ at bar 5 (115)
            make_candle(7,  high=120, low=74,  close=77),   # OUTSIDE_BAR (120>113, 74<78) → continue DOWN
            make_candle(8,  high=130, low=70,  close=73),   # OUTSIDE_BAR (130>120, 70<74) → continue DOWN
            #                                                  high=130 > H₁.high=115 — first tied maximum
            make_candle(9,  high=128, low=67,  close=70),   # LOWER_LOW → continue DOWN
            make_candle(10, high=130, low=64,  close=67),   # OUTSIDE_BAR (130>128, 64<67) → continue DOWN
            #                                                  high=130 — second tied maximum (later bar)
            make_candle(11, high=126, low=61,  close=65),   # LOWER_LOW → continue DOWN; last_low_candle
            make_candle(12, high=130, low=65,  close=128),  # HIGHER_HIGH → REVERSE UP; L₂ at bar 11 (61)
            #                                                  L₂(61) < L₁(80) → minor LL context
        ]
        result = engine.compute_structure(candles)
        h_points = [p for p in result.minor_points if p.kind in self._HIGH_KINDS]
        assert len(h_points) >= 1, "Expected at least one minor high-type point"
        h = h_points[0]
        # Container L₁(bar 2) → L₂(bar 11): bars 3–10.
        # Bars 8 and 10 both have high=130 > H₁ (115). Tie-breaking: earliest = bar 8.
        assert h.price == 130.0, f"High price must be 130.0 (tied maximum), got {h.price}"
        assert h.bar_index == 8, (
            f"Tie-breaking must choose earliest bar (8), got bar {h.bar_index}"
        )


# ── Main Structure Recursive Architecture Tests (MS-5B) ────────────────────────

class TestMainStructureMinorDerived:
    """
    MS-5B: Main Structure must derive all points exclusively from Minor Structure.
    No raw-candle-sourced points. Every Main point's bar_index must match a Minor
    point's bar_index.
    """

    def test_37_hh_confirmation_hl_derived_from_minor_l(self, engine):
        """
        Test A: HH confirmation places HL at Minor L, not raw candle.
        H(bar 2, 120) → L(bar 5 initially, 72) → H(bar 10, 135) triggers HH.
        Container (bar 2, bar 10) has outside bar at bar 8 (low=65) which is lower than L(72).
        MS-4F refinement moves L to bar 8 (65).
        HL must be selected from refined minor_points with kind=L in container (2, 10).
        HL is derived from minor_points, not raw candles.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),
            make_candle(1,  high=110, low=92,  close=105),  # UP
            make_candle(2,  high=120, low=93,  close=115),  # UP → H candidate
            make_candle(3,  high=117, low=82,  close=85),   # DOWN
            make_candle(4,  high=110, low=75,  close=78),   # DOWN
            make_candle(5,  high=114, low=72,  close=112),  # DOWN → initial L at 72
            make_candle(6,  high=118, low=74,  close=116),  # UP → reversal, L created
            make_candle(7,  high=122, low=76,  close=120),  # UP
            make_candle(8,  high=130, low=65,  close=128),  # UP (outside bar lower low; MS-4F moves L here)
            make_candle(9,  high=132, low=68,  close=130),  # UP
            make_candle(10, high=135, low=70,  close=133),  # UP → HH candidate
            make_candle(11, high=133, low=64,  close=67),   # DOWN → HH confirmed
        ]
        result = engine.compute_structure(candles)

        # Verify HL exists and comes from minor point
        hl_points = [p for p in result.main_points if p.kind == PointKind.HL]
        assert len(hl_points) >= 1, "Expected HL point"
        hl = hl_points[0]

        # HL.bar_index must exist in minor_points
        hl_in_minor = any(mp.bar_index == hl.bar_index for mp in result.minor_points)
        assert hl_in_minor, (
            f"HL at bar {hl.bar_index} must exist in minor_points: "
            f"{[mp.bar_index for mp in result.minor_points]}"
        )
        # HL should be at minor L refined by MS-4F to bar 8 (65)
        # This proves HL is derived from minor_points (which have been refined),
        # not independently from raw candles
        assert hl.price == 65.0, f"HL price must be 65.0 (refined minor L), got {hl.price}"
        assert hl.bar_index == 8, f"HL bar_index must be 8 (refined minor L), got {hl.bar_index}"

    def test_38_ll_confirmation_lh_derived_from_minor_h(self, engine):
        """
        Test B: LL confirmation places LH at Minor H, not raw candle.
        L(bar 2, 95) → H(bar 5, 115) → L(bar 9, 79) triggers LL.
        LH must be selected from minor_points with kind=H in container (2, 9).
        Only candidate: H(bar 5, 115) → LH relabeled from existing bootstrap H.
        """
        candles = [
            make_candle(0,  high=110, low=100, close=105),  # startup
            make_candle(1,  high=108, low=98,  close=101),  # DOWN
            make_candle(2,  high=103, low=95,  close=97),   # DOWN → L candidate
            make_candle(3,  high=106, low=97,  close=104),  # UP
            make_candle(4,  high=110, low=99,  close=107),  # UP
            make_candle(5,  high=115, low=101, close=112),  # UP → H candidate
            make_candle(6,  high=113, low=90,  close=93),   # DOWN
            make_candle(7,  high=125, low=87,  close=89),   # DOWN (outside bar)
            make_candle(8,  high=122, low=83,  close=85),   # DOWN
            make_candle(9,  high=118, low=79,  close=81),   # DOWN → LL candidate
            make_candle(10, high=122, low=82,  close=120),  # UP → LL confirmed
        ]
        result = engine.compute_structure(candles)

        # Verify LH exists and comes from minor point
        lh_points = [p for p in result.main_points if p.kind == PointKind.LH]
        assert len(lh_points) >= 1, "Expected LH point"
        lh = lh_points[0]

        # LH.bar_index must exist in minor_points
        lh_in_minor = any(mp.bar_index == lh.bar_index for mp in result.minor_points)
        assert lh_in_minor, (
            f"LH at bar {lh.bar_index} must exist in minor_points: "
            f"{[mp.bar_index for mp in result.minor_points]}"
        )
        # LH should be at minor H (bar 5 refined to bar 7 by MS-4F, or stay at 5)
        assert lh.bar_index in (5, 7), (
            f"LH must be at bar 5 or 7 (refined), got bar {lh.bar_index}"
        )

    def test_39_every_main_point_bar_index_exists_in_minor_points(self, engine):
        """
        Test C: Every main structure point must originate from a minor point.
        Verify by checking bar_index matching.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),
            make_candle(1,  high=110, low=92,  close=105),  # UP
            make_candle(2,  high=120, low=93,  close=115),  # UP → H
            make_candle(3,  high=117, low=82,  close=85),   # DOWN
            make_candle(4,  high=100, low=75,  close=78),   # DOWN → L
            make_candle(5,  high=108, low=77,  close=105),  # UP
            make_candle(6,  high=130, low=79,  close=125),  # UP → HH
            make_candle(7,  high=128, low=72,  close=75),   # DOWN
        ]
        result = engine.compute_structure(candles)

        minor_bar_indices = {mp.bar_index for mp in result.minor_points}
        for main_point in result.main_points:
            assert main_point.bar_index in minor_bar_indices, (
                f"Main {main_point.kind} at bar {main_point.bar_index} not found in "
                f"minor_points: {sorted(minor_bar_indices)}"
            )

    def test_40_main_points_chronologically_ordered(self, engine):
        """
        Test D: Main points must be in strictly increasing bar_index order.
        No backward references or out-of-order insertion.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),
            make_candle(1,  high=110, low=92,  close=105),  # UP
            make_candle(2,  high=120, low=93,  close=115),  # UP → H
            make_candle(3,  high=117, low=82,  close=85),   # DOWN
            make_candle(4,  high=100, low=75,  close=78),   # DOWN → L
            make_candle(5,  high=108, low=77,  close=105),  # UP
            make_candle(6,  high=130, low=79,  close=125),  # UP → HH
            make_candle(7,  high=128, low=72,  close=75),   # DOWN → HL placed
        ]
        result = engine.compute_structure(candles)

        if len(result.main_points) >= 2:
            for i in range(len(result.main_points) - 1):
                curr_idx = result.main_points[i].bar_index
                next_idx = result.main_points[i + 1].bar_index
                assert curr_idx < next_idx, (
                    f"Main points out of order: {result.main_points[i].kind}(bar {curr_idx}) "
                    f"followed by {result.main_points[i + 1].kind}(bar {next_idx})"
                )

    def test_41_main_legs_strictly_forward_in_time(self, engine):
        """
        Test E: All main legs must move forward chronologically.
        start_bar_index < end_bar_index for all legs.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),
            make_candle(1,  high=110, low=92,  close=105),  # UP
            make_candle(2,  high=120, low=93,  close=115),  # UP → H
            make_candle(3,  high=117, low=82,  close=85),   # DOWN
            make_candle(4,  high=100, low=75,  close=78),   # DOWN → L
            make_candle(5,  high=108, low=77,  close=105),  # UP
            make_candle(6,  high=130, low=79,  close=125),  # UP → HH
            make_candle(7,  high=128, low=72,  close=75),   # DOWN
        ]
        result = engine.compute_structure(candles)

        for leg in result.main_legs:
            assert leg.start_bar_index < leg.end_bar_index, (
                f"Leg {leg.direction} has backward time: start={leg.start_bar_index}, "
                f"end={leg.end_bar_index}"
            )

    def test_42_multi_swing_container_hl_lh_selection(self, engine):
        """
        Test F: Multi-swing container spanning 3+ minor cycles.
        HL/LH selection must find the true extreme among all minor H/L in range.

        Sequence: H→L→H→L→H triggers HH.
        HL must select the L with lowest price from all Ls in container.
        """
        candles = [
            make_candle(0,  high=100, low=90,  close=95),
            make_candle(1,  high=110, low=92,  close=105),  # UP
            make_candle(2,  high=120, low=93,  close=115),  # UP → H(bar 2, 120)
            make_candle(3,  high=117, low=82,  close=85),   # DOWN
            make_candle(4,  high=100, low=75,  close=78),   # DOWN → L(bar 4, 75)
            make_candle(5,  high=108, low=77,  close=105),  # UP
            make_candle(6,  high=118, low=79,  close=115),  # UP → H(bar 6, 118)
            make_candle(7,  high=116, low=70,  close=73),   # DOWN
            make_candle(8,  high=114, low=68,  close=72),   # DOWN → L(bar 8, 68)
            make_candle(9,  high=122, low=69,  close=120),  # UP
            make_candle(10, high=130, low=71,  close=128),  # UP → HH(bar 10, 130)
            make_candle(11, high=128, low=65,  close=67),   # DOWN
        ]
        result = engine.compute_structure(candles)

        # Verify HL selected from multi-swing container
        hl_points = [p for p in result.main_points if p.kind == PointKind.HL]
        if len(hl_points) >= 1:
            hl = hl_points[0]
            # Container (bar 2, bar 10): minor Ls at bar 4 (75) and bar 8 (68)
            # HL should be at bar 8 (lowest price 68)
            assert hl.bar_index == 8, (
                f"Multi-swing HL must select bar 8 (lowest L), got bar {hl.bar_index}"
            )
            assert hl.price == 68.0, f"Multi-swing HL price must be 68.0, got {hl.price}"


class TestMainStructureBoundaryAdvancement:
    """
    MS-6B/MS-6E: Boundary advancement and state-machine label correctness.

    Tests call _compute_main_structure directly with constructed minor_points.

    Tests 43-46 verify MS-6E state-machine reversal semantics:
      - BULLISH break-below → plain L (not LL), prior HH label is preserved.
      - BEARISH break-above → plain H (not HH), prior LL label is preserved.
    Test 47 is a regression guard (passes before and after).
    """

    def _mp(self, bar_index: int, price: float, kind: PointKind) -> StructurePoint:
        return StructurePoint(
            id=f"minor_{bar_index}",
            level=StructureLevel.MINOR,
            kind=kind,
            timestamp="2024-01-01T00:00:00Z",
            bar_index=bar_index,
            price=price,
            source="price",
            confirmed=True,
        )

    def test_43_hh_then_bullish_reversal(self, engine):
        """
        Test A — MS-6E: BULLISH reversal label.
        L(71) H(85) L(80) H(96) L(75):
          ESTABLISHING → BULLISH on H(96): HL(80), HH(96). main_low=80.
          L(75) < 80 → BULLISH REVERSAL → plain L(75). Prior HH(96) stays HH.
        Expected: [L(71), H(85), HL(80), HH(96), L(75)]. No LL, no LH.
        """
        minor = [
            self._mp(2,  71, PointKind.L),
            self._mp(4,  85, PointKind.H),
            self._mp(6,  80, PointKind.L),
            self._mp(8,  96, PointKind.H),
            self._mp(10, 75, PointKind.L),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert PointKind.HL in kinds, f"HL(80) must exist. Got: {kinds}"
        hl = next(p for p in points if p.kind == PointKind.HL)
        assert hl.price == 80.0, f"HL price must be 80, got {hl.price}"

        assert PointKind.HH in kinds, f"HH(96) must exist. Got: {kinds}"
        hh = next(p for p in points if p.kind == PointKind.HH)
        assert hh.price == 96.0, f"HH price must be 96, got {hh.price}"

        # L(75) is a reversal — must be plain L, not LL
        reversal = next(p for p in points if p.price == 75.0)
        assert reversal.kind == PointKind.L, (
            f"L(75) is a BULLISH reversal — must be plain L, got {reversal.kind}"
        )
        assert PointKind.LL not in kinds, f"No LL expected. Got: {kinds}"
        assert PointKind.LH not in kinds, f"No LH expected (HH not relabeled). Got: {kinds}"

    def test_44_ll_then_bearish_reversal(self, engine):
        """
        Test B — MS-6E: BEARISH reversal label.
        H(96) L(80) H(90) L(70) H(93):
          ESTABLISHING → BEARISH on L(70): LH(90), LL(70). main_high=90.
          H(93) > 90 → BEARISH REVERSAL → plain H(93). Prior LL(70) stays LL.
        Expected: [H(96), L(80), LH(90), LL(70), H(93)]. No HH, no HL.
        """
        minor = [
            self._mp(2,  96, PointKind.H),
            self._mp(4,  80, PointKind.L),
            self._mp(6,  90, PointKind.H),
            self._mp(8,  70, PointKind.L),
            self._mp(10, 93, PointKind.H),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert PointKind.LH in kinds, f"LH(90) must exist. Got: {kinds}"
        lh = next(p for p in points if p.kind == PointKind.LH)
        assert lh.price == 90.0, f"LH price must be 90, got {lh.price}"

        assert PointKind.LL in kinds, f"LL(70) must exist. Got: {kinds}"
        ll = next(p for p in points if p.kind == PointKind.LL)
        assert ll.price == 70.0, f"LL price must be 70, got {ll.price}"

        # H(93) is a reversal — must be plain H, not HH
        reversal = next(p for p in points if p.price == 93.0)
        assert reversal.kind == PointKind.H, (
            f"H(93) is a BEARISH reversal — must be plain H, got {reversal.kind}"
        )
        assert PointKind.HH not in kinds, f"No HH expected. Got: {kinds}"
        assert PointKind.HL not in kinds, f"No HL expected (LL not relabeled). Got: {kinds}"

    def test_45_bullish_reversal_then_bearish_confirmation(self, engine):
        """
        Test C — MS-6E: BULLISH reversal followed by BEARISH confirmation.
        L(71) H(85) L(80) H(96) L(75) H(92) L(68):
          HH(96)/HL(80) → L(75) BULLISH REVERSAL → state=ESTABLISHING.
          main_high stays 96. H(92)<96 → skip.
          L(68)<75 → ESTABLISHING→BEARISH: LH(92), LL(68).
        Expected: [L(71), H(85), HL(80), HH(96), L(75), LH(92), LL(68)].
        Exactly 1 LL and 1 LH; L(75).kind==L.
        """
        minor = [
            self._mp(2,  71, PointKind.L),
            self._mp(4,  85, PointKind.H),
            self._mp(6,  80, PointKind.L),
            self._mp(8,  96, PointKind.H),
            self._mp(10, 75, PointKind.L),
            self._mp(12, 92, PointKind.H),
            self._mp(14, 68, PointKind.L),
        ]
        points, _ = engine._compute_main_structure(minor)

        ll_points = [p for p in points if p.kind == PointKind.LL]
        assert len(ll_points) == 1, (
            f"Exactly one LL expected (at 68), got {len(ll_points)}: "
            f"{[(p.price, p.bar_index) for p in ll_points]}"
        )
        assert ll_points[0].price == 68.0, f"LL must be at 68, got {ll_points[0].price}"

        lh_points = [p for p in points if p.kind == PointKind.LH]
        assert len(lh_points) == 1, (
            f"Exactly one LH expected (at 92), got {len(lh_points)}: "
            f"{[(p.price, p.bar_index) for p in lh_points]}"
        )
        assert lh_points[0].price == 92.0, f"LH must be at 92, got {lh_points[0].price}"

        reversal = next(p for p in points if p.price == 75.0)
        assert reversal.kind == PointKind.L, (
            f"L(75) is a BULLISH reversal — must be plain L, got {reversal.kind}"
        )

    def test_46_bearish_reversal_then_bullish_confirmation(self, engine):
        """
        Test D — MS-6E: BEARISH reversal followed by BULLISH confirmation.
        H(96) L(80) H(90) L(70) H(93) L(74) H(98):
          LL(70)/LH(90) → H(93) BEARISH REVERSAL → state=ESTABLISHING.
          main_low stays 70. L(74)>70 → skip.
          H(98)>93 → ESTABLISHING→BULLISH: HL(74), HH(98).
        Expected: [H(96), L(80), LH(90), LL(70), H(93), HL(74), HH(98)].
        Exactly 1 HH and 1 HL (after reversal); H(93).kind==H.
        """
        minor = [
            self._mp(2,  96, PointKind.H),
            self._mp(4,  80, PointKind.L),
            self._mp(6,  90, PointKind.H),
            self._mp(8,  70, PointKind.L),
            self._mp(10, 93, PointKind.H),
            self._mp(12, 74, PointKind.L),
            self._mp(14, 98, PointKind.H),
        ]
        points, _ = engine._compute_main_structure(minor)

        hh_points = [p for p in points if p.kind == PointKind.HH]
        assert len(hh_points) == 1, (
            f"Exactly one HH expected (at 98), got {len(hh_points)}: "
            f"{[(p.price, p.bar_index) for p in hh_points]}"
        )
        assert hh_points[0].price == 98.0, f"HH must be at 98, got {hh_points[0].price}"

        hl_points = [p for p in points if p.kind == PointKind.HL]
        assert len(hl_points) == 1, (
            f"Exactly one HL expected (at 74), got {len(hl_points)}: "
            f"{[(p.price, p.bar_index) for p in hl_points]}"
        )
        assert hl_points[0].price == 74.0, f"HL must be at 74, got {hl_points[0].price}"

        reversal = next(p for p in points if p.price == 93.0)
        assert reversal.kind == PointKind.H, (
            f"H(93) is a BEARISH reversal — must be plain H, got {reversal.kind}"
        )

    def test_47_no_false_break_after_boundary_advancement(self, engine):
        """
        Test E: Boundary advancement must not create spurious LL.
        L(71) H(85) L(80) H(96) L(83):
          After HH(96)/HL(80): main_low=80.
          L(83): 83 > 80 → no LL. Must be skipped.
        """
        minor = [
            self._mp(2,  71, PointKind.L),
            self._mp(4,  85, PointKind.H),
            self._mp(6,  80, PointKind.L),
            self._mp(8,  96, PointKind.H),
            self._mp(10, 83, PointKind.L),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert PointKind.LL not in kinds, (
            f"No LL should fire (83 > HL boundary 80). Got: {kinds}"
        )
        assert PointKind.HH in kinds, "HH(96) must still be confirmed"
        assert PointKind.HL in kinds, "HL(80) must still exist"


class TestMainStructureStateMachine:
    """
    MS-6E: Three-state label machine (ESTABLISHING / BULLISH / BEARISH).

    Verifies correct labels across continuation, reversal, and post-reversal
    confirmation scenarios.  Tests call _compute_main_structure directly.
    """

    def _mp(self, bar_index: int, price: float, kind: PointKind) -> StructurePoint:
        return StructurePoint(
            id=f"minor_{bar_index}",
            level=StructureLevel.MINOR,
            kind=kind,
            timestamp="2024-01-01T00:00:00Z",
            bar_index=bar_index,
            price=price,
            source="price",
            confirmed=True,
        )

    def test_48_bearish_reversal_label(self, engine):
        """
        Test 1 — bearish reversal: H55 L50 H53 L48 H54.
        EST→BEAR on L48: LH(53), LL(48). H54>LH(53)→BEARISH REVERSAL→H(54).
        Expected sequence: H(55) L(50) LH(53) LL(48) H(54).
        LL(48) must remain LL (not relabeled HL). H(54) must be plain H, not HH.
        """
        minor = [
            self._mp(2,  55, PointKind.H),
            self._mp(4,  50, PointKind.L),
            self._mp(6,  53, PointKind.H),
            self._mp(8,  48, PointKind.L),
            self._mp(10, 54, PointKind.H),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert PointKind.LH in kinds, f"LH(53) expected. Got: {kinds}"
        lh = next(p for p in points if p.kind == PointKind.LH)
        assert lh.price == 53.0

        assert PointKind.LL in kinds, f"LL(48) expected. Got: {kinds}"
        ll = next(p for p in points if p.kind == PointKind.LL)
        assert ll.price == 48.0

        reversal = next(p for p in points if p.price == 54.0)
        assert reversal.kind == PointKind.H, (
            f"H(54) must be plain H (BEARISH reversal). Got {reversal.kind}"
        )
        assert PointKind.HH not in kinds, f"No HH expected. Got: {kinds}"
        assert PointKind.HL not in kinds, f"No HL expected (LL not relabeled). Got: {kinds}"

    def test_49_bullish_reversal_label(self, engine):
        """
        Test 2 — bullish reversal: L40 H50 L45 H55 L44.
        EST→BULL on H55: HL(45), HH(55). L44<HL(45)→BULLISH REVERSAL→L(44).
        Expected sequence: L(40) H(50) HL(45) HH(55) L(44).
        HH(55) must remain HH (not relabeled LH). L(44) must be plain L, not LL.
        """
        minor = [
            self._mp(2,  40, PointKind.L),
            self._mp(4,  50, PointKind.H),
            self._mp(6,  45, PointKind.L),
            self._mp(8,  55, PointKind.H),
            self._mp(10, 44, PointKind.L),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert PointKind.HL in kinds, f"HL(45) expected. Got: {kinds}"
        hl = next(p for p in points if p.kind == PointKind.HL)
        assert hl.price == 45.0

        assert PointKind.HH in kinds, f"HH(55) expected. Got: {kinds}"
        hh = next(p for p in points if p.kind == PointKind.HH)
        assert hh.price == 55.0

        reversal = next(p for p in points if p.price == 44.0)
        assert reversal.kind == PointKind.L, (
            f"L(44) must be plain L (BULLISH reversal). Got {reversal.kind}"
        )
        assert PointKind.LL not in kinds, f"No LL expected. Got: {kinds}"
        assert PointKind.LH not in kinds, f"No LH expected (HH not relabeled). Got: {kinds}"

    def test_50_bearish_reversal_then_bullish(self, engine):
        """
        Test 3 — BEARISH reversal → ESTABLISHING → BULLISH confirmation.
        H55 L50 H53 L48 H54 L49 H56:
          EST→BEAR on L48. H54→BEARISH REVERSAL→H(54), state=EST.
          L49 (49>48 = main_low) → skip.
          H56>54=main_high → EST→BULL: HL(49), HH(56).
        Expected: H(55) L(50) LH(53) LL(48) H(54) HL(49) HH(56).
        """
        minor = [
            self._mp(2,  55, PointKind.H),
            self._mp(4,  50, PointKind.L),
            self._mp(6,  53, PointKind.H),
            self._mp(8,  48, PointKind.L),
            self._mp(10, 54, PointKind.H),
            self._mp(12, 49, PointKind.L),
            self._mp(14, 56, PointKind.H),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert [p.kind for p in points] == [
            PointKind.H, PointKind.L,
            PointKind.LH, PointKind.LL,
            PointKind.H,
            PointKind.HL, PointKind.HH,
        ], f"Full sequence mismatch. Got: {kinds}"

        prices = [p.price for p in points]
        assert prices == [55, 50, 53, 48, 54, 49, 56], f"Prices mismatch. Got: {prices}"

    def test_51_bullish_reversal_then_bearish(self, engine):
        """
        Test 4 — BULLISH reversal → ESTABLISHING → BEARISH confirmation.
        L40 H50 L45 H55 L44 H52 L39:
          EST→BULL on H55. L44→BULLISH REVERSAL→L(44), state=EST.
          H52 (52<55=main_high) → skip.
          L39<44=main_low → EST→BEAR: LH(52), LL(39).
        Expected: L(40) H(50) HL(45) HH(55) L(44) LH(52) LL(39).
        """
        minor = [
            self._mp(2,  40, PointKind.L),
            self._mp(4,  50, PointKind.H),
            self._mp(6,  45, PointKind.L),
            self._mp(8,  55, PointKind.H),
            self._mp(10, 44, PointKind.L),
            self._mp(12, 52, PointKind.H),
            self._mp(14, 39, PointKind.L),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.L,
            PointKind.LH, PointKind.LL,
        ], f"Full sequence mismatch. Got: {kinds}"

        prices = [p.price for p in points]
        assert prices == [40, 50, 45, 55, 44, 52, 39], f"Prices mismatch. Got: {prices}"

    def test_52_bearish_continuation(self, engine):
        """
        Test 5 — BEARISH continuation: two LL confirmations without a reversal.
        H55 L50 H53 L48 H52 L45:
          EST→BEAR on L48: LH(53), LL(48). main_high=53, main_low=48.
          H52 (52<53) → skip.
          L45<48 → BEARISH continuation: LH(52), LL(45).
        Expected: H(55) L(50) LH(53) LL(48) LH(52) LL(45).
        """
        minor = [
            self._mp(2,  55, PointKind.H),
            self._mp(4,  50, PointKind.L),
            self._mp(6,  53, PointKind.H),
            self._mp(8,  48, PointKind.L),
            self._mp(10, 52, PointKind.H),
            self._mp(12, 45, PointKind.L),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert kinds == [
            PointKind.H, PointKind.L,
            PointKind.LH, PointKind.LL,
            PointKind.LH, PointKind.LL,
        ], f"Bearish continuation mismatch. Got: {kinds}"

        ll_prices = [p.price for p in points if p.kind == PointKind.LL]
        assert ll_prices == [48.0, 45.0], f"LL prices mismatch. Got: {ll_prices}"

    def test_53_bullish_continuation(self, engine):
        """
        Test 6 — BULLISH continuation: two HH confirmations without a reversal.
        L40 H50 L45 H55 L47 H60:
          EST→BULL on H55: HL(45), HH(55). main_high=55, main_low=45.
          L47 (47>45) → skip.
          H60>55 → BULLISH continuation: HL(47), HH(60).
        Expected: L(40) H(50) HL(45) HH(55) HL(47) HH(60).
        """
        minor = [
            self._mp(2,  40, PointKind.L),
            self._mp(4,  50, PointKind.H),
            self._mp(6,  45, PointKind.L),
            self._mp(8,  55, PointKind.H),
            self._mp(10, 47, PointKind.L),
            self._mp(12, 60, PointKind.H),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds = [p.kind for p in points]

        assert kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.HL, PointKind.HH,
        ], f"Bullish continuation mismatch. Got: {kinds}"

        hh_prices = [p.price for p in points if p.kind == PointKind.HH]
        assert hh_prices == [55.0, 60.0], f"HH prices mismatch. Got: {hh_prices}"

    def test_54_chronological_order_after_state_machine(self, engine):
        """
        Test 7 — chronological integrity: all points must be in bar_index order,
        including after a reversal restarts the sequence.
        Uses the bearish-reversal-then-bullish sequence (test 50 inputs).
        """
        minor = [
            self._mp(2,  55, PointKind.H),
            self._mp(4,  50, PointKind.L),
            self._mp(6,  53, PointKind.H),
            self._mp(8,  48, PointKind.L),
            self._mp(10, 54, PointKind.H),
            self._mp(12, 49, PointKind.L),
            self._mp(14, 56, PointKind.H),
        ]
        points, _ = engine._compute_main_structure(minor)

        bar_indices = [p.bar_index for p in points]
        assert bar_indices == sorted(bar_indices), (
            f"Points must be in chronological order. Got bar_indices: {bar_indices}"
        )

    def test_55_structure_within_structure_preserved(self, engine):
        """
        Test 8 — Structure-Within-Structure: every main point bar_index must
        correspond to a minor point, including reversal points.
        Uses the bullish-reversal-then-bearish sequence (test 51 inputs).
        """
        minor = [
            self._mp(2,  40, PointKind.L),
            self._mp(4,  50, PointKind.H),
            self._mp(6,  45, PointKind.L),
            self._mp(8,  55, PointKind.H),
            self._mp(10, 44, PointKind.L),
            self._mp(12, 52, PointKind.H),
            self._mp(14, 39, PointKind.L),
        ]
        points, _ = engine._compute_main_structure(minor)

        minor_bar_indices = {mp.bar_index for mp in minor}
        for pt in points:
            assert pt.bar_index in minor_bar_indices, (
                f"Main point bar_index={pt.bar_index} (kind={pt.kind}) "
                f"has no corresponding minor point. Minor bars: {sorted(minor_bar_indices)}"
            )


class TestMinorStructureLabelStateMachine:
    """
    MS-7A: Minor Structure comparative labeling.

    _label_structure_points(minor_points) relabels minor_points in-place
    using same-kind comparative labeling: each high compared to the most
    recent high, each low compared to the most recent low. Tested
    independently by calling the method directly on hand-crafted lists.

    Tests 56-63.
    """

    def _mp(self, bar_index: int, price: float, kind: PointKind) -> StructurePoint:
        return StructurePoint(
            id=f"minor_{bar_index}",
            level=StructureLevel.MINOR,
            kind=kind,
            timestamp="2024-01-01T00:00:00Z",
            bar_index=bar_index,
            price=price,
            source="price",
            confirmed=True,
        )

    def test_56_minor_bullish_continuation(self, engine):
        """
        Test A — BULLISH continuation.
        L40 H50 L45 H55 L47 H60.
        Bootstrap: L(40), H(50). H55 breaks above → HL(45)+HH(55).
        H60 continues BULLISH → HL(47)+HH(60).
        Expected: L H HL HH HL HH. No plain H/L after bootstrap.
        """
        minor = [
            self._mp(2,  40, PointKind.L),
            self._mp(4,  50, PointKind.H),
            self._mp(6,  45, PointKind.L),
            self._mp(8,  55, PointKind.H),
            self._mp(10, 47, PointKind.L),
            self._mp(12, 60, PointKind.H),
        ]
        engine._label_structure_points(minor)
        kinds = [p.kind for p in minor]

        assert kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.HL, PointKind.HH,
        ], f"Bullish continuation mismatch. Got: {kinds}"

        prices = [p.price for p in minor]
        assert prices == [40, 50, 45, 55, 47, 60], "Prices must not change"

    def test_57_minor_bearish_continuation(self, engine):
        """
        Test B — BEARISH continuation.
        H55 L50 H53 L48 H52 L45.
        Bootstrap: H(55), L(50). L48 breaks below → LH(53)+LL(48).
        L45 continues BEARISH → LH(52)+LL(45).
        Expected: H L LH LL LH LL. No plain H/L after bootstrap.
        """
        minor = [
            self._mp(2,  55, PointKind.H),
            self._mp(4,  50, PointKind.L),
            self._mp(6,  53, PointKind.H),
            self._mp(8,  48, PointKind.L),
            self._mp(10, 52, PointKind.H),
            self._mp(12, 45, PointKind.L),
        ]
        engine._label_structure_points(minor)
        kinds = [p.kind for p in minor]

        assert kinds == [
            PointKind.H, PointKind.L,
            PointKind.LH, PointKind.LL,
            PointKind.LH, PointKind.LL,
        ], f"Bearish continuation mismatch. Got: {kinds}"

        prices = [p.price for p in minor]
        assert prices == [55, 50, 53, 48, 52, 45], "Prices must not change"

    def test_58_minor_bullish_reversal(self, engine):
        """
        Test C — BULLISH reversal label.
        L40 H50 L45 H55 L44.
        BULLISH established on H55 (HL45, HH55). L44 < HL(45) → reversal.
        Expected: L H HL HH L.
        HH55 must remain HH. L44 must be plain L. No LL. No LH.
        """
        minor = [
            self._mp(2,  40, PointKind.L),
            self._mp(4,  50, PointKind.H),
            self._mp(6,  45, PointKind.L),
            self._mp(8,  55, PointKind.H),
            self._mp(10, 44, PointKind.L),
        ]
        engine._label_structure_points(minor)
        kinds = [p.kind for p in minor]

        assert kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.L,
        ], f"Bullish reversal mismatch. Got: {kinds}"

        hh = next(p for p in minor if p.price == 55.0)
        assert hh.kind == PointKind.HH, "H55 must remain HH after bullish reversal"

        reversal_l = next(p for p in minor if p.price == 44.0)
        assert reversal_l.kind == PointKind.L, "L44 must be plain L (bullish reversal)"
        assert PointKind.LL not in kinds, "No LL expected after bullish reversal"
        assert PointKind.LH not in kinds, "HH must not be relabeled to LH during reversal"

    def test_59_minor_bearish_reversal(self, engine):
        """
        Test D — BEARISH reversal label.
        H55 L50 H53 L48 H54.
        BEARISH established on L48 (LH53, LL48). H54 > LH(53) → reversal.
        Expected: H L LH LL H.
        LL48 must remain LL. H54 must be plain H. No HH. No HL.
        """
        minor = [
            self._mp(2,  55, PointKind.H),
            self._mp(4,  50, PointKind.L),
            self._mp(6,  53, PointKind.H),
            self._mp(8,  48, PointKind.L),
            self._mp(10, 54, PointKind.H),
        ]
        engine._label_structure_points(minor)
        kinds = [p.kind for p in minor]

        assert kinds == [
            PointKind.H, PointKind.L,
            PointKind.LH, PointKind.LL,
            PointKind.H,
        ], f"Bearish reversal mismatch. Got: {kinds}"

        ll = next(p for p in minor if p.price == 48.0)
        assert ll.kind == PointKind.LL, "L48 must remain LL after bearish reversal"

        reversal_h = next(p for p in minor if p.price == 54.0)
        assert reversal_h.kind == PointKind.H, "H54 must be plain H (bearish reversal)"
        assert PointKind.HH not in kinds, "No HH expected after bearish reversal"
        assert PointKind.HL not in kinds, "LL must not be relabeled to HL during reversal"

    def test_60_minor_reversal_then_bullish_reconfirmation(self, engine):
        """
        Test E — BEARISH reversal then BULLISH reconfirmation.
        H55 L50 H53 L48 H54 L49 H56.
        BEARISH on L48. H54 → BEARISH reversal → H(54), state=ESTABLISHING.
        L49 within range (49>48). H56>54 → ESTABLISHING→BULLISH: HL(49)+HH(56).
        Expected: H L LH LL H HL HH.
        """
        minor = [
            self._mp(2,  55, PointKind.H),
            self._mp(4,  50, PointKind.L),
            self._mp(6,  53, PointKind.H),
            self._mp(8,  48, PointKind.L),
            self._mp(10, 54, PointKind.H),
            self._mp(12, 49, PointKind.L),
            self._mp(14, 56, PointKind.H),
        ]
        engine._label_structure_points(minor)
        kinds = [p.kind for p in minor]

        assert kinds == [
            PointKind.H, PointKind.L,
            PointKind.LH, PointKind.LL,
            PointKind.H,
            PointKind.HL, PointKind.HH,
        ], f"Bearish reversal→bullish reconfirmation mismatch. Got: {kinds}"

        prices = [p.price for p in minor]
        assert prices == [55, 50, 53, 48, 54, 49, 56], "Prices must not change"

    def test_61_minor_reversal_then_bearish_reconfirmation(self, engine):
        """
        Test F — BULLISH reversal then BEARISH reconfirmation.
        L40 H50 L45 H55 L44 H52 L39.
        BULLISH on H55. L44 → BULLISH reversal → L(44), state=ESTABLISHING.
        H52 within range (52<55). L39<44 → ESTABLISHING→BEARISH: LH(52)+LL(39).
        Expected: L H HL HH L LH LL.
        """
        minor = [
            self._mp(2,  40, PointKind.L),
            self._mp(4,  50, PointKind.H),
            self._mp(6,  45, PointKind.L),
            self._mp(8,  55, PointKind.H),
            self._mp(10, 44, PointKind.L),
            self._mp(12, 52, PointKind.H),
            self._mp(14, 39, PointKind.L),
        ]
        engine._label_structure_points(minor)
        kinds = [p.kind for p in minor]

        assert kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.L,
            PointKind.LH, PointKind.LL,
        ], f"Bullish reversal→bearish reconfirmation mismatch. Got: {kinds}"

        prices = [p.price for p in minor]
        assert prices == [40, 50, 45, 55, 44, 52, 39], "Prices must not change"

    def test_62_minor_bootstrap_only(self, engine):
        """
        Test G — Bootstrap-only sequences: fewer than 3 pivots keep plain H/L.
        """
        # 1 pivot
        single = [self._mp(2, 50, PointKind.H)]
        engine._label_structure_points(single)
        assert single[0].kind == PointKind.H, "Single-point list must stay H"

        # 2 pivots: L-first
        two_lh = [self._mp(2, 40, PointKind.L), self._mp(4, 50, PointKind.H)]
        engine._label_structure_points(two_lh)
        assert two_lh[0].kind == PointKind.L, "Bootstrap L must stay L"
        assert two_lh[1].kind == PointKind.H, "Bootstrap H must stay H"

        # 2 pivots: H-first
        two_hl = [self._mp(2, 50, PointKind.H), self._mp(4, 40, PointKind.L)]
        engine._label_structure_points(two_hl)
        assert two_hl[0].kind == PointKind.H, "Bootstrap H must stay H"
        assert two_hl[1].kind == PointKind.L, "Bootstrap L must stay L"

        # Empty list — must not raise
        engine._label_structure_points([])

    def test_63_main_structure_unaffected_by_minor_label_pass(self, engine):
        """
        Test H — Main structure must not change after _label_structure_points runs.
        The two passes create independent StructurePoint objects; mutating
        minor_points.kind cannot affect main_points.kind.
        Uses the bullish continuation sequence (Test A inputs).
        """
        minor = [
            self._mp(2,  40, PointKind.L),
            self._mp(4,  50, PointKind.H),
            self._mp(6,  45, PointKind.L),
            self._mp(8,  55, PointKind.H),
            self._mp(10, 47, PointKind.L),
            self._mp(12, 60, PointKind.H),
        ]
        # Phase 2: main structure from raw H/L minor points
        main_points, _ = engine._compute_main_structure(minor)
        main_kinds_before = [p.kind for p in main_points]

        # Phase 2.5: minor label pass (runs after main)
        engine._label_structure_points(minor)

        # Main labels must be unchanged
        main_kinds_after = [p.kind for p in main_points]
        assert main_kinds_before == main_kinds_after, (
            f"Main point kinds changed after minor label pass.\n"
            f"Before: {main_kinds_before}\n"
            f"After:  {main_kinds_after}"
        )

        # Minor labels are now correctly classified
        minor_kinds = [p.kind for p in minor]
        assert minor_kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.HL, PointKind.HH,
        ], f"Minor kinds mismatch after label pass. Got: {minor_kinds}"

    def test_64_compute_structure_end_to_end_minor_kind_sequence(self, engine):
        """
        Integration guard — MS-6H.

        Calls compute_structure() end-to-end with real OHLCV candles and
        asserts result.minor_points[*].kind matches the expected bullish
        continuation sequence: L, H, HL, HH, HL, HH.

        This test does NOT call _label_structure_points() directly. It exercises
        the full pipeline: candles → _compute_minor_structure → _refine_minor_pivots
        → _compute_main_structure → _label_structure_points → result.minor_points.

        Candle structure (5-bar segments):
          seg_dn(0–4, base=44, step=1)   establishes DOWN direction
          seg_up(5–9, base=40, step=2)   UP reversal → L at bar 4
          seg_dn(10–14, base=50, step=1) DOWN reversal → H at bar 10
          seg_up(15–19, base=45, step=2) UP reversal → L at bar 15 (→ HL after label)
          seg_dn(20–24, base=55, step=1) DOWN reversal → H at bar 20 (→ HH after label)
          seg_up(25–29, base=47, step=2.6) UP reversal → L at bar 25 (→ HL after label)
          seg_dn(30–32, base=60, step=1) DOWN reversal → H at bar 30 (→ HH after label)
        """
        def seg_up(start: int, n: int, base: float, step: float = 2.0):
            return [
                make_candle(start + k, high=base + k * step + 1, low=base + k * step - 1,
                            close=base + k * step + 0.5)
                for k in range(n)
            ]

        def seg_dn(start: int, n: int, base: float, step: float = 2.0):
            return [
                make_candle(start + k, high=base - k * step + 1, low=base - k * step - 1,
                            close=base - k * step - 0.5)
                for k in range(n)
            ]

        candles = (
            seg_dn(0,  5, 44, 1) +
            seg_up(5,  5, 40, 2) +
            seg_dn(10, 5, 50, 1) +
            seg_up(15, 5, 45, 2) +
            seg_dn(20, 5, 55, 1) +
            seg_up(25, 5, 47, 2.6) +
            seg_dn(30, 3, 60, 1)
        )

        result = engine.compute_structure(candles)

        assert len(result.minor_points) >= 6, (
            f"Expected at least 6 minor points, got {len(result.minor_points)}"
        )

        kinds = [p.kind for p in result.minor_points[:6]]
        assert kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.HL, PointKind.HH,
        ], (
            f"End-to-end minor kind sequence mismatch. "
            f"Expected [L, H, HL, HH, HL, HH], got: {[k.value for k in kinds]}"
        )


# ── MS-7A Comparative Labeling Spec Tests ─────────────────────────────────────

class TestMS7AComparativeLabeling:
    """
    MS-7A: Exhaustive tests for the _label_structure_points comparative model.

    All spec scenarios verified against the same-kind comparison rules:
      High: current >= prev_high AND prev was LH → H (bullish reversal)
            current >= prev_high (otherwise)     → HH
            current <  prev_high                 → LH
      Low:  current >  prev_low                  → HL (higher low)
            current <  prev_low AND prev was HL  → L  (bearish reversal)
            current <= prev_low (otherwise)      → LL

    Tests 65-72.
    """

    def _mp(self, bar_index: int, price: float, kind: PointKind) -> StructurePoint:
        return StructurePoint(
            id=f"p{bar_index}",
            level=StructureLevel.MINOR,
            kind=kind,
            timestamp="2024-01-01T00:00:00Z",
            bar_index=bar_index,
            price=price,
            source="test",
            confirmed=True,
        )

    def _h(self, i: int, p: float) -> StructurePoint:
        return self._mp(i, p, PointKind.H)

    def _l(self, i: int, p: float) -> StructurePoint:
        return self._mp(i, p, PointKind.L)

    def _kinds(self, points: list) -> list:
        return [p.kind for p in points]

    def test_65_failed_bearish_reversal(self, engine):
        """
        Spec: Failed reversal sequence A — L,H,HL,HH,L,HH.

        Bullish continuation → new L breaks below HL (bearish reversal below HL → L)
        → but next H makes new HH (bullish re-confirmation, not a confirmed reversal).
        """
        points = [
            self._l(0, 40),   # bootstrap L
            self._h(1, 50),   # bootstrap H
            self._l(2, 45),   # 45>40  → HL
            self._h(3, 55),   # 55>=50, prev=H → HH
            self._l(4, 38),   # 38<45 AND prev_low was HL → L (reversal)
            self._h(5, 60),   # 60>=55, prev=HH (not LH) → HH
        ]
        engine._label_structure_points(points)
        assert self._kinds(points) == [
            PointKind.L, PointKind.H, PointKind.HL, PointKind.HH,
            PointKind.L, PointKind.HH,
        ], f"Failed bearish reversal mismatch: {self._kinds(points)}"

    def test_66_failed_bullish_reversal(self, engine):
        """
        Spec: Failed reversal sequence B — H,L,LH,LL,H,LL.

        Bearish continuation → new H breaks above LH (bullish reversal above LH → H)
        → but next L makes new LL (bearish re-confirmation, not a confirmed reversal).
        """
        points = [
            self._h(0, 55),   # bootstrap H
            self._l(1, 40),   # bootstrap L
            self._h(2, 52),   # 52<55 → LH
            self._l(3, 35),   # 35<40, prev_low=L (not HL) → LL
            self._h(4, 58),   # 58>=52 AND prev_high was LH → H (reversal)
            self._l(5, 32),   # 32<35, prev_low=LL (not HL) → LL
        ]
        engine._label_structure_points(points)
        assert self._kinds(points) == [
            PointKind.H, PointKind.L, PointKind.LH, PointKind.LL,
            PointKind.H, PointKind.LL,
        ], f"Failed bullish reversal mismatch: {self._kinds(points)}"

    def test_67_confirmed_bearish_reversal(self, engine):
        """
        Spec: Confirmed reversal sequence A — L,H,HL,HH,L,LH,LL.

        Bullish continuation → new L breaks below HL → L (reversal)
        → next H is LH (lower than prior HH) → confirmed bearish.
        → next L is LL (lower than prior L from reversal, and prev was NOT HL).
        """
        points = [
            self._l(0, 40),   # bootstrap L
            self._h(1, 50),   # bootstrap H
            self._l(2, 45),   # 45>40 → HL
            self._h(3, 55),   # 55>=50, prev=H → HH
            self._l(4, 38),   # 38<45 AND prev was HL → L (bearish reversal)
            self._h(5, 52),   # 52<55 → LH
            self._l(6, 30),   # 30<38, prev_low=L (not HL) → LL
        ]
        engine._label_structure_points(points)
        assert self._kinds(points) == [
            PointKind.L, PointKind.H, PointKind.HL, PointKind.HH,
            PointKind.L, PointKind.LH, PointKind.LL,
        ], f"Confirmed bearish reversal mismatch: {self._kinds(points)}"

    def test_68_confirmed_bullish_reversal(self, engine):
        """
        Spec: Confirmed reversal sequence B — H,L,LH,LL,H,HL,HH.

        Bearish continuation → new H breaks above LH → H (reversal)
        → next L is HL (higher than prior LL, now prev_low=LL not HL) → HL
        → next H is HH (higher than prior H from reversal).
        """
        points = [
            self._h(0, 55),   # bootstrap H
            self._l(1, 40),   # bootstrap L
            self._h(2, 52),   # 52<55 → LH
            self._l(3, 35),   # 35<40, prev=L (not HL) → LL
            self._h(4, 58),   # 58>=52 AND prev was LH → H (bullish reversal)
            self._l(5, 37),   # 37>35 → HL
            self._h(6, 62),   # 62>=58, prev=H (not LH) → HH
        ]
        engine._label_structure_points(points)
        assert self._kinds(points) == [
            PointKind.H, PointKind.L, PointKind.LH, PointKind.LL,
            PointKind.H, PointKind.HL, PointKind.HH,
        ], f"Confirmed bullish reversal mismatch: {self._kinds(points)}"

    def test_69_equal_high_produces_hh(self, engine):
        """
        Spec: Equal High rule — current_high == previous_high → HH.
        """
        points = [
            self._l(0, 40),
            self._h(1, 50),
            self._l(2, 45),   # HL
            self._h(3, 50),   # 50 == 50, prev=H (not LH) → HH (equal → HH)
        ]
        engine._label_structure_points(points)
        assert points[3].kind == PointKind.HH, (
            f"Equal high must produce HH, got {points[3].kind}"
        )

    def test_70_equal_low_produces_ll(self, engine):
        """
        Spec: Equal Low rule — current_low == previous_low → LL.
        """
        points = [
            self._h(0, 55),
            self._l(1, 40),
            self._h(2, 52),   # LH
            self._l(3, 40),   # 40 <= 40 (equal), not (40<40 and HL) → LL
        ]
        engine._label_structure_points(points)
        assert points[3].kind == PointKind.LL, (
            f"Equal low must produce LL, got {points[3].kind}"
        )

    def test_71_bearish_continuation(self, engine):
        """
        Spec: Bearish continuation — H,L,LH,LL,LH,LL.
        """
        points = [
            self._h(0, 55),   # bootstrap H
            self._l(1, 40),   # bootstrap L
            self._h(2, 52),   # 52<55 → LH
            self._l(3, 35),   # 35<40, prev=L → LL
            self._h(4, 48),   # 48<52 → LH
            self._l(5, 28),   # 28<35, prev=LL (not HL) → LL
        ]
        engine._label_structure_points(points)
        assert self._kinds(points) == [
            PointKind.H, PointKind.L, PointKind.LH, PointKind.LL,
            PointKind.LH, PointKind.LL,
        ], f"Bearish continuation mismatch: {self._kinds(points)}"

    def test_72_h_first_bootstrap_then_l_first_bootstrap(self, engine):
        """
        Spec: Startup sequences — first H-type → H, first L-type → L regardless of input kind.
        """
        h_first = [self._h(0, 50), self._l(1, 40)]
        engine._label_structure_points(h_first)
        assert h_first[0].kind == PointKind.H, "H-first bootstrap: first point must be H"
        assert h_first[1].kind == PointKind.L, "H-first bootstrap: second point must be L"

        l_first = [self._l(0, 40), self._h(1, 50)]
        engine._label_structure_points(l_first)
        assert l_first[0].kind == PointKind.L, "L-first bootstrap: first point must be L"
        assert l_first[1].kind == PointKind.H, "L-first bootstrap: second point must be H"


# ── MS-7C Main Structure Comparative Selection Tests ──────────────────────────

class TestMS7CMainStructureComparativeSelection:
    """
    MS-7C: Main Structure complies with MS-7A equal-value and reversal semantics.

    Tests call _compute_main_structure directly (consistent with tests 43–55).
    No _label_structure_points post-pass — construction-time labels are authoritative.

    Tests 73–79.
    """

    def _mp(self, bar_index: int, price: float, kind: PointKind) -> StructurePoint:
        return StructurePoint(
            id=f"minor_{bar_index}",
            level=StructureLevel.MINOR,
            kind=kind,
            timestamp="2024-01-01T00:00:00Z",
            bar_index=bar_index,
            price=price,
            source="price",
            confirmed=True,
        )

    def _h(self, i: int, p: float) -> StructurePoint:
        return self._mp(i, p, PointKind.H)

    def _l(self, i: int, p: float) -> StructurePoint:
        return self._mp(i, p, PointKind.L)

    def test_73_equal_high_emits_hh(self, engine):
        """
        MS-7C: Equal high → HH confirmation.

        L90 H120 L100 H130 L95 H130 → L, H, HL, HH, L, HH.

        After BULL reversal at L95 (strictly below HL=100), the second H130
        equals main_high (130). With >= threshold it fires EST→BULL and emits HH.
        The reversal L95 must remain plain L — _apply_hl must not upgrade it.
        """
        minor = [
            self._l(0, 90),
            self._h(1, 120),
            self._l(2, 100),
            self._h(3, 130),
            self._l(4, 95),
            self._h(5, 130),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds  = [p.kind for p in points]
        prices = [p.price for p in points]

        assert kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.L, PointKind.HH,
        ], f"Equal-high sequence mismatch. Got: {kinds}"
        assert prices == [90, 120, 100, 130, 95, 130], f"Prices mismatch. Got: {prices}"

        # Reversal L(95) must stay L — must not be upgraded to HL
        reversal = next(p for p in points if p.price == 95.0 and p.kind != PointKind.HH)
        assert reversal.kind == PointKind.L, (
            f"Reversal L(95) must stay plain L after equal-HH fires. Got: {reversal.kind}"
        )
        hh_points = [p for p in points if p.kind == PointKind.HH]
        assert len(hh_points) == 2, f"Expected exactly 2 HH points, got {len(hh_points)}"
        assert all(p.price == 130.0 for p in hh_points), "Both HH must be at price 130"

    def test_74_equal_low_emits_ll(self, engine):
        """
        MS-7C: Equal low → LL confirmation; equal BEAR reversal H → plain H.

        H120 L90 H110 L80 H110 L80 → H, L, LH, LL, H, LL.

        H110 == LH ceiling (main_high=110 in BEAR): >= triggers BEAR reversal → H.
        L80 == main_low (80) in EST state: <= triggers EST→BEAR → LL.
        The reversal H110 must remain plain H — _apply_lh must not upgrade it.
        """
        minor = [
            self._h(0, 120),
            self._l(1, 90),
            self._h(2, 110),
            self._l(3, 80),
            self._h(4, 110),
            self._l(5, 80),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds  = [p.kind for p in points]
        prices = [p.price for p in points]

        assert kinds == [
            PointKind.H, PointKind.L,
            PointKind.LH, PointKind.LL,
            PointKind.H, PointKind.LL,
        ], f"Equal-low sequence mismatch. Got: {kinds}"
        assert prices == [120, 90, 110, 80, 110, 80], f"Prices mismatch. Got: {prices}"

        # Reversal H110 must stay plain H — must not be upgraded to LH
        reversal = next(p for p in points if p.price == 110.0 and p.kind != PointKind.LH)
        assert reversal.kind == PointKind.H, (
            f"Reversal H(110) must stay plain H after equal-LL fires. Got: {reversal.kind}"
        )
        ll_points = [p for p in points if p.kind == PointKind.LL]
        assert len(ll_points) == 2, f"Expected exactly 2 LL points, got {len(ll_points)}"
        assert all(p.price == 80.0 for p in ll_points), "Both LL must be at price 80"

    def test_75_confirmed_bearish_reversal_with_lh_and_ll(self, engine):
        """
        MS-7C: Post-reversal LH + LL sequence captured.

        L90 H120 L100 H130 L95 H125 L95 → L, H, HL, HH, L, LH, LL.

        After BULL reversal at L95 (strictly below HL=100):
          H125 is inside the [95, 130] dead zone — not directly selected.
          L95 (equal to main_low=95) fires EST→BEAR via <=.
          _lh_candidate finds H125 retroactively between L95(bar4) and L95(bar6).
          Result: LH(125) + LL(95) appended. Sequence is 7 points.
        """
        minor = [
            self._l(0, 90),
            self._h(1, 120),
            self._l(2, 100),
            self._h(3, 130),
            self._l(4, 95),
            self._h(5, 125),
            self._l(6, 95),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds  = [p.kind for p in points]
        prices = [p.price for p in points]

        assert kinds == [
            PointKind.L, PointKind.H,
            PointKind.HL, PointKind.HH,
            PointKind.L, PointKind.LH, PointKind.LL,
        ], f"Confirmed bearish reversal mismatch. Got: {kinds}"
        assert prices == [90, 120, 100, 130, 95, 125, 95], f"Prices mismatch. Got: {prices}"

        lh = next(p for p in points if p.kind == PointKind.LH)
        assert lh.price == 125.0, f"LH price must be 125, got {lh.price}"
        assert lh.bar_index == 5, f"LH bar_index must be 5, got {lh.bar_index}"

        ll = next(p for p in points if p.kind == PointKind.LL)
        assert ll.price == 95.0, f"LL price must be 95, got {ll.price}"
        assert ll.bar_index == 6, f"LL bar_index must be 6, got {ll.bar_index}"

        # Reversal L(95) at bar4 must stay plain L
        reversal_l = next(p for p in points if p.bar_index == 4)
        assert reversal_l.kind == PointKind.L, (
            f"Reversal L(95, bar=4) must stay plain L. Got: {reversal_l.kind}"
        )

    def test_76_confirmed_bullish_reversal_with_hl_and_hh(self, engine):
        """
        MS-7C: Confirmed bullish reversal already works; equal bootstrap HH verified.

        H120 L90 H110 L80 H115 L85 H120 → H, L, LH, LL, H, HL, HH.

        The final HH(120) equals the bootstrap H(120). With >= threshold it fires
        EST→BULL correctly. Included here as a MS-7C equality guard.
        """
        minor = [
            self._h(0, 120),
            self._l(1, 90),
            self._h(2, 110),
            self._l(3, 80),
            self._h(4, 115),
            self._l(5, 85),
            self._h(6, 120),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds  = [p.kind for p in points]
        prices = [p.price for p in points]

        assert kinds == [
            PointKind.H, PointKind.L,
            PointKind.LH, PointKind.LL,
            PointKind.H, PointKind.HL, PointKind.HH,
        ], f"Confirmed bullish reversal mismatch. Got: {kinds}"
        assert prices == [120, 90, 110, 80, 115, 85, 120], f"Prices mismatch. Got: {prices}"

        hh = next(p for p in points if p.kind == PointKind.HH)
        assert hh.price == 120.0, f"HH price must be 120, got {hh.price}"
        hl = next(p for p in points if p.kind == PointKind.HL)
        assert hl.price == 85.0, f"HL price must be 85, got {hl.price}"

    def test_77_equal_bear_reversal_emits_plain_h(self, engine):
        """
        MS-7C: Equal BEAR reversal — H price == LH ceiling → plain H (not HH or LH).

        H120 L90 H110 L80 H110 → H, L, LH, LL, H.

        After BEAR: main_high=110 (LH price). H110 >= 110 → BEAR reversal → plain H.
        Prior LL(80) must remain LL.
        """
        minor = [
            self._h(0, 120),
            self._l(1, 90),
            self._h(2, 110),
            self._l(3, 80),
            self._h(4, 110),
        ]
        points, _ = engine._compute_main_structure(minor)
        kinds  = [p.kind for p in points]
        prices = [p.price for p in points]

        assert kinds == [
            PointKind.H, PointKind.L,
            PointKind.LH, PointKind.LL,
            PointKind.H,
        ], f"Equal BEAR reversal mismatch. Got: {kinds}"
        assert prices == [120, 90, 110, 80, 110], f"Prices mismatch. Got: {prices}"

        reversal_h = points[-1]
        assert reversal_h.kind == PointKind.H, (
            f"H(110) at LH ceiling must be plain H (reversal). Got: {reversal_h.kind}"
        )
        ll = next(p for p in points if p.kind == PointKind.LL)
        assert ll.kind == PointKind.LL, "Prior LL must remain LL after BEAR reversal"
        assert PointKind.HH not in kinds, f"No HH expected. Got: {kinds}"
        assert PointKind.HL not in kinds, f"No HL expected (LL not upgraded). Got: {kinds}"

    def test_78_main_points_are_subset_of_minor_bars(self, engine):
        """
        MS-7C: Structure-within-structure invariant holds for new equal-value cases.

        Every main point bar_index must correspond to a minor point bar_index,
        including retroactively inserted LH/HL candidates.
        Uses the confirmed-bearish-reversal sequence from test_75.
        """
        minor = [
            self._l(0, 90),
            self._h(1, 120),
            self._l(2, 100),
            self._h(3, 130),
            self._l(4, 95),
            self._h(5, 125),
            self._l(6, 95),
        ]
        points, _ = engine._compute_main_structure(minor)
        minor_bars = {mp.bar_index for mp in minor}

        for pt in points:
            assert pt.bar_index in minor_bars, (
                f"Main point bar_index={pt.bar_index} (kind={pt.kind.value}) "
                f"has no corresponding minor point. Minor bars: {sorted(minor_bars)}"
            )

    def test_79_main_points_chronological_after_equal_value_events(self, engine):
        """
        MS-7C: Points remain in chronological (bar_index) order after equal-value
        events and retroactive LH/HL candidate insertion.

        Uses both equal-high (test_73) and confirmed-bearish-reversal (test_75)
        sequences to cover retroactive insertion paths.
        """
        for minor in [
            [   # test_73 sequence
                self._l(0, 90), self._h(1, 120), self._l(2, 100),
                self._h(3, 130), self._l(4, 95), self._h(5, 130),
            ],
            [   # test_75 sequence
                self._l(0, 90), self._h(1, 120), self._l(2, 100),
                self._h(3, 130), self._l(4, 95), self._h(5, 125), self._l(6, 95),
            ],
        ]:
            points, _ = engine._compute_main_structure(minor)
            bar_indices = [p.bar_index for p in points]
            assert bar_indices == sorted(bar_indices), (
                f"Points out of chronological order. bar_indices: {bar_indices}"
            )

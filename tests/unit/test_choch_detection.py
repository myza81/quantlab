"""
CHoCH detection unit tests.

Covers all twelve required scenarios:

  1.  Bullish structure → wick below HL → CHoCH
  2.  Bullish structure → close below HL → CHoCH
  3.  Bullish structure → low == HL → no CHoCH  (equality is not a break)
  4.  Bearish structure → wick above LH → CHoCH
  5.  Bearish structure → close above LH → CHoCH
  6.  Bearish structure → high == LH → no CHoCH (equality is not a break)
  7.  No CHoCH without valid trend structure
  8.  Minor and main scopes isolated
  9.  Pending BoS invalidation can coexist with CHoCH emission
 10.  Structure-point candle cannot be its own CHoCH break
 11.  Existing BoS tests continue passing
 12.  Existing market structure tests continue passing

Structure points are built directly using StructurePoint so tests are
independent of the engine's candle-level detection logic.
"""
from __future__ import annotations

import pytest

from backend.tools.choch_detection import CHoCHDirection, CHoCHEvent, detect_choch
from backend.tools.bos_detection import BoSStatus, detect_bos
from backend.tools.market_structure import (
    MarketStructureEngine,
    OHLCVCandle,
    PointKind,
    StructureLevel,
    StructurePoint,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sp(
    bar: int,
    price: float,
    kind: PointKind,
    level: StructureLevel = StructureLevel.MINOR,
) -> StructurePoint:
    return StructurePoint(
        id=f"sp_{bar}",
        level=level,
        kind=kind,
        timestamp=f"2024-01-01T{bar:02d}:00:00Z",
        bar_index=bar,
        price=price,
        source="price",
        confirmed=True,
    )


def _candle(
    bar: int,
    high: float,
    low: float,
    close: float,
    open_: float | None = None,
) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=f"2024-01-01T{bar:02d}:00:00Z",
        bar_index=bar,
        open=open_ if open_ is not None else close,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
    )


def _flat(bar: int, price: float) -> OHLCVCandle:
    """Neutral candle at a safe price that does not breach any structural level."""
    return _candle(bar, price, price, price)


# ── Shared structure fixtures ─────────────────────────────────────────────────
#
# Uptrend: L(0,90) → H(2,100) → HL(4,95) → HH(6,110)
#   protected_level (HL) = 95
#
# Downtrend: H(0,110) → L(2,90) → LH(4,100) → LL(6,80)
#   protected_level (LH) = 100

_UPTREND_POINTS = [
    _sp(0,  90,  PointKind.L),
    _sp(2, 100,  PointKind.H),
    _sp(4,  95,  PointKind.HL),
    _sp(6, 110,  PointKind.HH),
]

_DOWNTREND_POINTS = [
    _sp(0, 110,  PointKind.H),
    _sp(2,  90,  PointKind.L),
    _sp(4, 100,  PointKind.LH),
    _sp(6,  80,  PointKind.LL),
]

# Safe candles at structure-point bars plus one filler bar in each gap.
# Prices kept inside (96–109) for uptrend, (81–99) for downtrend to avoid
# accidental CHoCH triggers.
_UPTREND_SAFE_CANDLES = [
    _flat(0, 90), _flat(1, 93),
    _flat(2, 100), _flat(3, 97),
    _flat(4, 95), _flat(5, 102),
    _flat(6, 110), _flat(7, 107),
]

_DOWNTREND_SAFE_CANDLES = [
    _flat(0, 110), _flat(1, 105),
    _flat(2, 90), _flat(3, 95),
    _flat(4, 100), _flat(5, 88),
    _flat(6, 80), _flat(7, 83),
]


# ═════════════════════════════════════════════════════════════════════════════
# Test 1 — Bullish CHoCH via wick (close remains above HL)
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHBullishWick:
    """
    Uptrend HL = 95.
    Bar 8: low=93 (< 95), close=106 (> 95) — wick breach only.
    CHoCH must fire immediately; close does NOT prevent it.
    """

    def _events(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=93, close=106),
        ]
        return detect_choch(_UPTREND_POINTS, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_direction_is_bullish(self):
        assert self._events()[0].direction == CHoCHDirection.BULLISH

    def test_contract_markers(self):
        ev = self._events()[0]
        assert ev.event_type == "choch"
        assert ev.status == "valid"
        assert ev.event_effect == "transition"
        assert ev.violated_trend == "uptrend"

    def test_protected_level(self):
        assert self._events()[0].protected_level == 95.0

    def test_break_candle_index(self):
        assert self._events()[0].break_candle_index == 8

    def test_reference_fields(self):
        ev = self._events()[0]
        assert ev.reference_structure_type   == "HL"
        assert ev.structure_reference_index  == 4   # bar of the HL point

    def test_scope_label(self):
        assert self._events()[0].structure_scope == "minor"


# ═════════════════════════════════════════════════════════════════════════════
# Test 2 — Bullish CHoCH via close (both wick and close below HL)
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHBullishClose:
    """
    Uptrend HL = 95.
    Bar 8: low=92, close=92 — both wick and close below HL.
    CHoCH must fire; close position does not change the outcome.
    """

    def _events(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=98, low=92, close=92),
        ]
        return detect_choch(_UPTREND_POINTS, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_direction_is_bullish(self):
        assert self._events()[0].direction == CHoCHDirection.BULLISH

    def test_protected_level_matches_hl(self):
        assert self._events()[0].protected_level == 95.0

    def test_break_candle_index(self):
        assert self._events()[0].break_candle_index == 8


# ═════════════════════════════════════════════════════════════════════════════
# Test 3 — Bullish equality: low == HL → no CHoCH
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHBullishEquality:
    """
    Uptrend HL = 95.
    Bar 8: low=95 — exactly AT the protected level.
    Equality is not a breach. No CHoCH.
    """

    def test_no_choch_when_low_equals_protected(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=95, close=104),  # low == 95, not < 95
        ]
        events = detect_choch(_UPTREND_POINTS, candles, "minor")
        assert events == [], f"Expected no CHoCH, got: {events}"

    def test_one_below_triggers_but_equal_does_not(self):
        """Two bars: first at 95 (no CHoCH), second at 94.99 (CHoCH)."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=95,   close=105),  # equal — no trigger
            _candle(9, high=107, low=94.99, close=106), # strict below — trigger
        ]
        events = detect_choch(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 9


# ═════════════════════════════════════════════════════════════════════════════
# Test 4 — Bearish CHoCH via wick (close remains below LH)
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHBearishWick:
    """
    Downtrend LH = 100.
    Bar 8: high=103 (> 100), close=85 (< 100) — wick breach only.
    CHoCH must fire immediately.
    """

    def _events(self):
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=103, low=82, close=85),
        ]
        return detect_choch(_DOWNTREND_POINTS, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_direction_is_bearish(self):
        assert self._events()[0].direction == CHoCHDirection.BEARISH

    def test_contract_markers(self):
        ev = self._events()[0]
        assert ev.event_type == "choch"
        assert ev.status == "valid"
        assert ev.event_effect == "transition"
        assert ev.violated_trend == "downtrend"

    def test_protected_level(self):
        assert self._events()[0].protected_level == 100.0

    def test_break_candle_index(self):
        assert self._events()[0].break_candle_index == 8

    def test_reference_fields(self):
        ev = self._events()[0]
        assert ev.reference_structure_type   == "LH"
        assert ev.structure_reference_index  == 4   # bar of the LH point

    def test_scope_label(self):
        assert self._events()[0].structure_scope == "minor"


# ═════════════════════════════════════════════════════════════════════════════
# Test 5 — Bearish CHoCH via close (both wick and close above LH)
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHBearishClose:
    """
    Downtrend LH = 100.
    Bar 8: high=103, close=102 — both above LH.
    CHoCH must fire; close position does not change the outcome.
    """

    def _events(self):
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=103, low=89, close=102),
        ]
        return detect_choch(_DOWNTREND_POINTS, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_direction_is_bearish(self):
        assert self._events()[0].direction == CHoCHDirection.BEARISH

    def test_protected_level_matches_lh(self):
        assert self._events()[0].protected_level == 100.0

    def test_break_candle_index(self):
        assert self._events()[0].break_candle_index == 8


# ═════════════════════════════════════════════════════════════════════════════
# Test 6 — Bearish equality: high == LH → no CHoCH
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHBearishEquality:
    """
    Downtrend LH = 100.
    Bar 8: high=100 — exactly AT the protected level.
    Equality is not a breach. No CHoCH.
    """

    def test_no_choch_when_high_equals_protected(self):
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=100, low=82, close=85),  # high == 100, not > 100
        ]
        events = detect_choch(_DOWNTREND_POINTS, candles, "minor")
        assert events == [], f"Expected no CHoCH, got: {events}"

    def test_one_above_triggers_but_equal_does_not(self):
        """Two bars: first at 100 (no CHoCH), second at 100.01 (CHoCH)."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8,  high=100,    low=83, close=85),   # equal — no trigger
            _candle(9,  high=100.01, low=82, close=85),   # strict above — trigger
        ]
        events = detect_choch(_DOWNTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 9


# ═════════════════════════════════════════════════════════════════════════════
# Test 7 — No CHoCH without valid trend structure
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHNoTrend:
    """
    CHoCH requires at least one HL + HH (or LH + LL) in structure_points.
    Without a confirmed trend, no CHoCH can fire.
    """

    def test_bootstrap_only_no_choch(self):
        """L + H only — no HL or HH → no trend → no CHoCH."""
        points = [_sp(0, 90, PointKind.L), _sp(2, 100, PointKind.H)]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100),
                   _candle(3, high=115, low=80, close=82)]  # big breach candle
        assert detect_choch(points, candles, "minor") == []

    def test_partial_bull_hl_only_no_choch(self):
        """L + H + HL but no HH → CHoCH cannot fire yet."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
        ]
        candles = [_flat(i, 97) for i in range(6)] + [
            _candle(6, high=115, low=80, close=82)  # low below HL
        ]
        assert detect_choch(points, candles, "minor") == []

    def test_partial_bear_lh_only_no_choch(self):
        """H + L + LH but no LL → CHoCH cannot fire yet."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4, 100, PointKind.LH),
        ]
        candles = [_flat(i, 95) for i in range(6)] + [
            _candle(6, high=115, low=80, close=82)  # high above LH
        ]
        assert detect_choch(points, candles, "minor") == []

    def test_empty_structure_points(self):
        candles = [_candle(i, high=115, low=80, close=82) for i in range(5)]
        assert detect_choch([], candles, "minor") == []

    def test_empty_candles(self):
        assert detect_choch(_UPTREND_POINTS, [], "minor") == []

    def test_no_hl_in_uptrend_means_no_protected_level(self):
        """HH without a preceding HL → active_protected stays None → no CHoCH."""
        # Unusual bootstrap: H then HH only (no HL)
        points = [
            _sp(0, 100, PointKind.H),
            _sp(2, 120, PointKind.HH),
        ]
        candles = [_flat(0, 100), _flat(1, 110), _flat(2, 120),
                   _candle(3, high=115, low=80, close=82)]
        assert detect_choch(points, candles, "minor") == []

    def test_no_lh_in_downtrend_means_no_protected_level(self):
        """LL without a preceding LH → active_protected stays None → no CHoCH."""
        points = [
            _sp(0, 100, PointKind.L),
            _sp(2,  80, PointKind.LL),
        ]
        candles = [_flat(0, 100), _flat(1, 90), _flat(2, 80),
                   _candle(3, high=120, low=82, close=118)]
        assert detect_choch(points, candles, "minor") == []


# ═════════════════════════════════════════════════════════════════════════════
# Test 8 — Minor and main scope isolation
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHScopeIsolation:
    """
    Scope is stored verbatim; minor and main detectors are completely independent.
    """

    def test_minor_scope_label(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=93, close=106),
        ]
        events = detect_choch(_UPTREND_POINTS, candles, "minor")
        assert all(ev.structure_scope == "minor" for ev in events)

    def test_main_scope_label(self):
        main_points = [
            _sp(0,  90, PointKind.L,  StructureLevel.MAIN),
            _sp(2, 100, PointKind.H,  StructureLevel.MAIN),
            _sp(4,  95, PointKind.HL, StructureLevel.MAIN),
            _sp(6, 110, PointKind.HH, StructureLevel.MAIN),
        ]
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=93, close=106),
        ]
        events = detect_choch(main_points, candles, "main")
        assert all(ev.structure_scope == "main" for ev in events)

    def test_different_protected_levels_are_independent(self):
        """
        Minor HL=95, main HL=85.
        A candle with low=90 breaks minor HL but not main HL.
        """
        minor_points = _UPTREND_POINTS  # HL at 95
        main_points = [
            _sp(0,  90, PointKind.L,  StructureLevel.MAIN),
            _sp(2, 110, PointKind.H,  StructureLevel.MAIN),
            _sp(4,  85, PointKind.HL, StructureLevel.MAIN),
            _sp(6, 130, PointKind.HH, StructureLevel.MAIN),
        ]
        # Bar 8: low=90 — breaks minor HL=95, does NOT break main HL=85
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=112, low=90, close=108),
        ]
        minor_events = detect_choch(minor_points, candles, "minor")
        main_events  = detect_choch(main_points,  candles, "main")

        assert len(minor_events) == 1
        assert minor_events[0].protected_level == 95.0

        assert len(main_events) == 0  # 90 is not < 85

    def test_scope_never_crosses(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=93, close=106),
        ]
        for scope in ("minor", "main"):
            events = detect_choch(_UPTREND_POINTS, candles, scope)
            for ev in events:
                assert ev.structure_scope == scope


# ═════════════════════════════════════════════════════════════════════════════
# Test 9 — Pending BoS invalidation coexists with CHoCH
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHCoexistsWithBoSInvalidation:
    """
    Scenario:
      Uptrend: L(0,90), H(2,100), HL(4,95), HH(6,110)
      Bar 8: high=115, close=109 → BoS PENDING (breaks HH=110, close < 110).
      Bar 10: low=93 → both BoS INVALID and CHoCH BULLISH fire.

    The two detectors are independent.  Run both and verify each
    produces the correct event at bar 10.
    """

    _POINTS = _UPTREND_POINTS

    def _candles(self):
        return _UPTREND_SAFE_CANDLES + [
            _candle(8,  high=115, low=109, close=109),   # BoS pending
            _flat(9, 107),                                # neutral
            _candle(10, high=100, low=93,  close=94),    # breaches HL=95
        ]

    def test_choch_fires_at_bar_10(self):
        events = detect_choch(self._POINTS, self._candles(), "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.direction          == CHoCHDirection.BULLISH
        assert ev.break_candle_index == 10
        assert ev.protected_level    == 95.0

    def test_bos_invalid_fires_at_bar_10(self):
        bos_events = detect_bos(self._POINTS, self._candles(), "minor")
        invalid = [e for e in bos_events if e.status == BoSStatus.INVALID]
        assert len(invalid) == 1
        assert invalid[0].invalidation_candle_index == 10

    def test_choch_and_bos_fire_on_same_candle(self):
        choch_events = detect_choch(self._POINTS, self._candles(), "minor")
        bos_events   = detect_bos(self._POINTS, self._candles(), "minor")

        choch_bars = {ev.break_candle_index for ev in choch_events}
        bos_inv_bars = {
            ev.invalidation_candle_index
            for ev in bos_events
            if ev.status == BoSStatus.INVALID
        }
        assert choch_bars & bos_inv_bars, (
            "CHoCH and BoS INVALID should share the same invalidation bar"
        )

    def test_detectors_do_not_interfere(self):
        """Running both detectors in sequence gives the same results as running each alone."""
        candles = self._candles()
        choch_a = detect_choch(self._POINTS, candles, "minor")
        bos_a   = detect_bos(self._POINTS, candles, "minor")
        choch_b = detect_choch(self._POINTS, candles, "minor")
        bos_b   = detect_bos(self._POINTS, candles, "minor")

        assert [(e.break_candle_index, e.direction) for e in choch_a] == \
               [(e.break_candle_index, e.direction) for e in choch_b]
        assert [(e.status, e.break_candle_index) for e in bos_a] == \
               [(e.status, e.break_candle_index) for e in bos_b]


# ═════════════════════════════════════════════════════════════════════════════
# Test 10 — Structure-point CHoCH behaviour by kind
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHStructurePointBehavior:
    """
    Verifies which structure-point kinds trigger CHoCH and which do not.

    After CHOCH-3 refactor:
      CHoCH is triggered solely by raw candle OHLC breach of the active
      protected level.  Structure-point labels do not determine triggering.

      L (reversal in bull context)  → CHoCH fires when low < HL (unchanged).
      H (reversal in bear context)  → CHoCH fires when high > LH (unchanged).
      LL (in bull context)          → CHoCH fires when low < HL (new in CHOCH-3).
      HH (in bear context)          → CHoCH fires when high > LH (new in CHOCH-3).
      HL / LH (protected-level bars) → cannot self-trigger; context not yet
                                        armed when these bars are processed.
    """

    def test_reversal_l_below_hl_emits_choch(self):
        """
        Reversal L structure point at bar 8 with candle.low=85 < protected HL=95.
        CHoCH fires on the L bar itself.
        """
        points = _UPTREND_POINTS + [_sp(8, 85, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 85)]
        events = detect_choch(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.direction          == CHoCHDirection.BULLISH
        assert ev.break_candle_index == 8
        assert ev.protected_level    == 95.0
        assert ev.structure_reference_index == 4   # the HL at bar 4
        assert ev.reference_structure_type  == "HL"
        assert ev.violated_trend            == "uptrend"

    def test_reversal_l_is_the_choch_bar_not_a_later_bar(self):
        """
        CHoCH fires at the L structure-point bar.  A subsequent candle at bar 9
        (also below the old HL) fires no second CHoCH because state is NO_TREND.
        """
        points = _UPTREND_POINTS + [_sp(8, 85, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [
            _flat(8, 85),
            _candle(9, high=95, low=83, close=88),  # below old HL, but state reset
        ]
        events = detect_choch(points, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 8   # L bar, not bar 9

    def test_hl_sp_itself_cannot_trigger_bullish_choch(self):
        """
        The HL structure point bar (bar 4, price=95) cannot trigger CHoCH.
        HL sets the protected level; the following HH establishes BULL state.
        The HL bar is processed before BULL state exists, so no self-trigger.
        """
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=93, close=106),
        ]
        events = detect_choch(_UPTREND_POINTS, candles, "minor")
        # CHoCH at bar 8, not bar 4
        assert len(events) == 1
        assert events[0].break_candle_index == 8
        assert events[0].structure_reference_index == 4

    def test_lh_sp_itself_cannot_trigger_bearish_choch(self):
        """
        The LH structure point bar (bar 4, price=100) cannot trigger CHoCH.
        """
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=103, low=82, close=85),
        ]
        events = detect_choch(_DOWNTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 8
        assert events[0].structure_reference_index == 4


# ═════════════════════════════════════════════════════════════════════════════
# Test 11 — Existing BoS tests continue passing
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHRegressionBoS:
    """
    Smoke-test that importing choch_detection does not break bos_detection.
    Runs the core BoS scenarios from the original test suite.
    """

    def test_bos_var1_bullish_unaffected(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=112),
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.VALID

    def test_bos_var1_bearish_unaffected(self):
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=83, low=75, close=77),
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.VALID

    def test_bos_invalid_unaffected(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8,  high=115, low=109, close=109),
            _candle(9,  high=113, low=97,  close=110),
            _candle(10, high=100, low=93,  close=94),
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.INVALID

    def test_bos_no_trend_unaffected(self):
        points = [_sp(0, 90, PointKind.L), _sp(2, 100, PointKind.H)]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100),
                   _candle(3, high=115, low=88, close=114)]
        assert detect_bos(points, candles, "minor") == []


# ═════════════════════════════════════════════════════════════════════════════
# Test 12 — Existing market structure tests continue passing
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHRegressionMarketStructure:
    """
    Smoke-test that importing choch_detection does not affect MarketStructureEngine.
    """

    @pytest.fixture
    def engine(self):
        return MarketStructureEngine()

    def _make_candle(self, bar, high, low, close):
        return OHLCVCandle(
            timestamp=f"2024-01-01T{bar:02d}:00:00Z",
            bar_index=bar,
            open=close,
            high=high,
            low=low,
            close=close,
            volume=1_000.0,
        )

    def test_minor_structure_unaffected(self, engine):
        candles = (
            [self._make_candle(i, 100 + i*2, 90 + i, 95 + i) for i in range(6)]
            + [self._make_candle(i+6, 110 - i*2, 80 - i, 85 - i) for i in range(6)]
        )
        result = engine.compute_structure(candles)
        assert len(result.minor_points) >= 1

    def test_main_structure_unaffected(self, engine):
        candles = (
            [self._make_candle(i,     100 + i*3, 90 + i*2, 95 + i*2)  for i in range(8)]
            + [self._make_candle(i+8, 120 - i*3, 100 - i*2, 105 - i*2) for i in range(8)]
            + [self._make_candle(i+16, 90 + i*3, 80 + i*2, 85 + i*2)   for i in range(8)]
        )
        result = engine.compute_structure(candles)
        assert len(result.main_points) >= 2

    def test_import_choch_does_not_alter_labels(self, engine):
        """Importing choch_detection must not alter label assignments."""
        from backend.tools import choch_detection as _ch  # noqa: F401
        candles = (
            [self._make_candle(i, 100 + i*2, 90 + i, 95 + i) for i in range(6)]
            + [self._make_candle(i+6, 110 - i*2, 80 - i, 85 - i) for i in range(6)]
            + [self._make_candle(i+12, 90 + i*2, 78 + i, 83 + i) for i in range(6)]
        )
        result = engine.compute_structure(candles)
        kinds = [p.kind for p in result.minor_points]
        assert kinds, "No minor points — engine broken"
        for k in kinds:
            assert k in list(PointKind)


# ═════════════════════════════════════════════════════════════════════════════
# Additional edge-case tests
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHEdgeCases:
    """Boundary and edge-case behaviour."""

    def test_updated_hl_raises_protected_level(self):
        """
        A new HL structure point tightens the protected level.
        Original HL=95, new HL=100.  CHoCH now requires low < 100.
        Bar 8 (low=98) would be safe under old level (98 > 95)
        but triggers CHoCH under new level (98 < 100).
        """
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
            _sp(6, 110, PointKind.HH),
            _sp(7, 100, PointKind.HL),   # new HL raises protected to 100
        ]
        candles = [
            _flat(0, 90), _flat(1, 93),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 102),
            _flat(6, 110), _flat(7, 100),
            _candle(8, high=108, low=98, close=105),  # low=98 < 100 → CHoCH
        ]
        events = detect_choch(points, candles, "minor")
        assert len(events) == 1
        assert events[0].protected_level    == 100.0
        assert events[0].break_candle_index == 8
        assert events[0].structure_reference_index == 7  # the NEW HL

    def test_choch_fires_on_first_post_hh_candle(self):
        """CHoCH can fire on the very first non-SP candle after HH if it breaks HL."""
        # Structure ends at bar 6 (HH). Bar 7 is not a SP — immediate CHoCH check.
        candles = [
            _flat(0, 90), _flat(1, 93),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 102),
            _flat(6, 110),
            _candle(7, high=108, low=93, close=104),  # bar 7: low=93 < HL=95
        ]
        events = detect_choch(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 7

    def test_choch_resets_state_only_one_event_per_trend(self):
        """
        After CHoCH fires, state resets to no_trend.
        A second breach candle (before any new trend) emits no second CHoCH.
        """
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=93, close=106),  # CHoCH fires; state → no_trend
            _candle(9, high=105, low=88, close=90),   # further breach — state is no_trend
        ]
        events = detect_choch(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1, (
            f"Only one CHoCH per trend window. Got {len(events)}: {events}"
        )

    def test_new_trend_after_choch_can_emit_second_choch(self):
        """
        After CHoCH + trend reset, new structure points can establish a new trend.
        A second breach in the new trend fires a second CHoCH.
        """
        # First bull trend → CHoCH at bar 8 → reset.
        # Then new: HL(10,98), HH(12,120).  Second CHoCH at bar 14.
        points = _UPTREND_POINTS + [
            _sp(10, 98,  PointKind.HL),
            _sp(12, 120, PointKind.HH),
        ]
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8,  high=108, low=93,  close=106),  # first CHoCH
            _flat(9,  105),
            _flat(10, 98),
            _flat(11, 109),
            _flat(12, 120),
            _candle(13, high=115, low=95,  close=112),  # safe (95 < 98? no: 95 < 98 → CHoCH!)
        ]
        # Bar 13: low=95 < new HL=98 → second CHoCH
        events = detect_choch(points, candles, "minor")
        assert len(events) == 2
        assert events[0].break_candle_index == 8
        assert events[1].break_candle_index == 13
        assert events[1].protected_level    == 98.0

    def test_reference_index_matches_most_recent_hl(self):
        """
        structure_reference_index must always point to the MOST RECENT HL,
        not the original one.
        """
        points = _UPTREND_POINTS + [
            _sp(8, 100, PointKind.HL),   # new HL at bar 8 (price=100)
        ]
        candles = _UPTREND_SAFE_CANDLES + [
            _flat(8, 100),
            _candle(9, high=108, low=98, close=105),  # low=98 < 100 → CHoCH
        ]
        events = detect_choch(points, candles, "minor")
        assert len(events) == 1
        # reference should be the NEW HL at bar 8, not the original at bar 4
        assert events[0].structure_reference_index == 8
        assert events[0].protected_level           == 100.0


# ═════════════════════════════════════════════════════════════════════════════
# CHOCH-2A — Reversal structure-point ordering fix
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHOnReversalStructurePoints:
    """
    Regression suite for CHOCH-2A: CHoCH evaluated before state reset on
    reversal structure-point bars (L in bull context, H in bear context).

    Prior to the fix the PointKind.L / PointKind.H handlers cleared state
    before the CHoCH scan executed, silently suppressing valid events.
    """

    # ── Bullish: L structure point ────────────────────────────────────────

    def test_bull_sp_l_emits_choch_direction(self):
        """L(8, 85) in bull trend (HL=95): direction is BULLISH."""
        points  = _UPTREND_POINTS + [_sp(8, 85, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 85)]
        events  = detect_choch(points, candles, "minor")
        assert len(events) == 1
        assert events[0].direction == CHoCHDirection.BULLISH

    def test_bull_sp_l_emits_correct_contract_fields(self):
        """All CHoCH primitive-event-contract fields are correctly populated."""
        points  = _UPTREND_POINTS + [_sp(8, 85, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 85)]
        ev      = detect_choch(points, candles, "minor")[0]
        assert ev.event_type             == "choch"
        assert ev.status                 == "valid"
        assert ev.event_effect           == "transition"
        assert ev.violated_trend         == "uptrend"
        assert ev.reference_structure_type == "HL"
        assert ev.structure_scope        == "minor"

    def test_bull_sp_l_protected_level_and_reference(self):
        """protected_level and structure_reference_index point to the HL."""
        points  = _UPTREND_POINTS + [_sp(8, 85, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 85)]
        ev      = detect_choch(points, candles, "minor")[0]
        assert ev.protected_level           == 95.0   # HL price
        assert ev.structure_reference_index == 4      # HL bar

    def test_bull_sp_l_break_candle_is_the_sp_bar(self):
        """break_candle_index equals the L structure-point bar."""
        points  = _UPTREND_POINTS + [_sp(8, 85, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 85)]
        ev      = detect_choch(points, candles, "minor")[0]
        assert ev.break_candle_index == 8

    def test_bull_sp_l_equality_no_choch(self):
        """L candle.low == protected HL (strict inequality) → no CHoCH."""
        points  = _UPTREND_POINTS + [_sp(8, 95, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 95)]  # low == 95, not < 95
        events  = detect_choch(points, candles, "minor")
        assert events == [], f"Equality must not trigger CHoCH. Got: {events}"

    def test_bull_sp_l_no_choch_without_bull_state(self):
        """L structure point before trend is established → no CHoCH."""
        # Only L + H (no HL, no HH) — state never reaches BULL.
        points  = [_sp(0, 90, PointKind.L), _sp(2, 100, PointKind.H),
                   _sp(4, 85, PointKind.L)]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100),
                   _flat(3, 97), _flat(4, 85)]
        assert detect_choch(points, candles, "minor") == []

    def test_bull_sp_l_state_resets_no_duplicate(self):
        """
        After CHoCH fires on L(8), state resets to NO_TREND.
        A second candle at bar 9 with low=80 (also below old HL) fires no
        further CHoCH because active_protected is now None.
        """
        points  = _UPTREND_POINTS + [_sp(8, 85, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [
            _flat(8, 85),
            _candle(9, high=90, low=80, close=82),  # deep breach, but state=NO_TREND
        ]
        events = detect_choch(points, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 8

    # ── Bearish: H structure point ────────────────────────────────────────

    def test_bear_sp_h_emits_choch_direction(self):
        """H(8, 115) in bear trend (LH=100): direction is BEARISH."""
        points  = _DOWNTREND_POINTS + [_sp(8, 115, PointKind.H)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 115)]
        events  = detect_choch(points, candles, "minor")
        assert len(events) == 1
        assert events[0].direction == CHoCHDirection.BEARISH

    def test_bear_sp_h_emits_correct_contract_fields(self):
        """All CHoCH primitive-event-contract fields are correctly populated."""
        points  = _DOWNTREND_POINTS + [_sp(8, 115, PointKind.H)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 115)]
        ev      = detect_choch(points, candles, "minor")[0]
        assert ev.event_type             == "choch"
        assert ev.status                 == "valid"
        assert ev.event_effect           == "transition"
        assert ev.violated_trend         == "downtrend"
        assert ev.reference_structure_type == "LH"
        assert ev.structure_scope        == "minor"

    def test_bear_sp_h_protected_level_and_reference(self):
        """protected_level and structure_reference_index point to the LH."""
        points  = _DOWNTREND_POINTS + [_sp(8, 115, PointKind.H)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 115)]
        ev      = detect_choch(points, candles, "minor")[0]
        assert ev.protected_level           == 100.0   # LH price
        assert ev.structure_reference_index == 4       # LH bar

    def test_bear_sp_h_break_candle_is_the_sp_bar(self):
        """break_candle_index equals the H structure-point bar."""
        points  = _DOWNTREND_POINTS + [_sp(8, 115, PointKind.H)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 115)]
        ev      = detect_choch(points, candles, "minor")[0]
        assert ev.break_candle_index == 8

    def test_bear_sp_h_equality_no_choch(self):
        """H candle.high == protected LH (strict inequality) → no CHoCH."""
        points  = _DOWNTREND_POINTS + [_sp(8, 100, PointKind.H)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 100)]  # high == 100
        events  = detect_choch(points, candles, "minor")
        assert events == [], f"Equality must not trigger CHoCH. Got: {events}"

    def test_bear_sp_h_no_choch_without_bear_state(self):
        """H structure point before trend is established → no CHoCH."""
        points  = [_sp(0, 110, PointKind.H), _sp(2, 90, PointKind.L),
                   _sp(4, 115, PointKind.H)]
        candles = [_flat(0, 110), _flat(1, 100), _flat(2, 90),
                   _flat(3, 95), _flat(4, 115)]
        assert detect_choch(points, candles, "minor") == []

    def test_bear_sp_h_state_resets_no_duplicate(self):
        """
        After CHoCH fires on H(8), state resets to NO_TREND.
        A second candle at bar 9 with high=120 fires no further CHoCH.
        """
        points  = _DOWNTREND_POINTS + [_sp(8, 115, PointKind.H)]
        candles = _DOWNTREND_SAFE_CANDLES + [
            _flat(8, 115),
            _candle(9, high=120, low=90, close=95),  # above LH, but state=NO_TREND
        ]
        events = detect_choch(points, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 8

    # ── Cross-kind guard: wrong context never fires ───────────────────────

    def test_l_sp_in_bear_context_no_choch(self):
        """L structure point while state=BEAR → no bullish CHoCH (wrong state)."""
        points  = _DOWNTREND_POINTS + [_sp(8, 75, PointKind.L)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 75)]
        assert detect_choch(points, candles, "minor") == []

    def test_h_sp_in_bull_context_no_choch(self):
        """H structure point while state=BULL → no bearish CHoCH (wrong state)."""
        points  = _UPTREND_POINTS + [_sp(8, 120, PointKind.H)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 120)]
        assert detect_choch(points, candles, "minor") == []

    # ── Wick-only non-SP behaviour is unchanged ───────────────────────────

    def test_wick_only_non_sp_bullish_still_fires(self):
        """Non-SP candle wick below HL still triggers CHoCH (unchanged path)."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=108, low=93, close=106),  # low=93 < HL=95
        ]
        events = detect_choch(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 8
        assert events[0].direction          == CHoCHDirection.BULLISH

    def test_wick_only_non_sp_bearish_still_fires(self):
        """Non-SP candle wick above LH still triggers CHoCH (unchanged path)."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=103, low=82, close=85),  # high=103 > LH=100
        ]
        events = detect_choch(_DOWNTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 8
        assert events[0].direction          == CHoCHDirection.BEARISH


# ═════════════════════════════════════════════════════════════════════════════
# CHOCH-3 — Non-reversal structure-point bars as CHoCH triggers
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCH3NonReversalStructurePointBreach:
    """
    CHOCH-3: CHoCH trigger is raw candle OHLC, not structure-point label.

    Non-reversal structure points (LL, HH) were previously skipped for CHoCH
    evaluation due to the 'continue' after the SP block.  The refactored loop
    evaluates breach (step 1) before SP context update (step 2) on every bar,
    so LL and HH bars can now trigger CHoCH when the context is active.
    """

    # ── LL bar in BULL context (spec test 5) ─────────────────────────────

    def test_ll_sp_in_bull_context_emits_bullish_choch(self):
        """
        LL structure point in active BULL context.
        Bar 8: LL SP, candle.low=80 < protected HL=95.
        Step 1 fires bullish CHoCH; step 2 then arms BEAR context.
        """
        points  = _UPTREND_POINTS + [_sp(8, 80, PointKind.LL)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 80)]
        events  = detect_choch(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.direction              == CHoCHDirection.BULLISH
        assert ev.break_candle_index     == 8
        assert ev.protected_level        == 95.0
        assert ev.reference_structure_type == "HL"
        assert ev.structure_reference_index == 4   # the HL at bar 4
        assert ev.violated_trend         == "uptrend"

    def test_ll_sp_bull_choch_contract_fields(self):
        """All primitive-event-contract fields are correctly populated."""
        points  = _UPTREND_POINTS + [_sp(8, 80, PointKind.LL)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 80)]
        ev      = detect_choch(points, candles, "minor")[0]
        assert ev.event_type   == "choch"
        assert ev.status       == "valid"
        assert ev.event_effect == "transition"

    def test_ll_sp_bull_equality_no_choch(self):
        """LL candle.low == protected HL (strict inequality) → no CHoCH."""
        points  = _UPTREND_POINTS + [_sp(8, 95, PointKind.LL)]
        candles = _UPTREND_SAFE_CANDLES + [_flat(8, 95)]   # low == 95, not < 95
        assert detect_choch(points, candles, "minor") == []

    def test_ll_sp_bull_state_resets_no_duplicate(self):
        """
        After CHoCH fires on the LL bar, state resets.
        A subsequent candle below old HL fires no second CHoCH.
        """
        points  = _UPTREND_POINTS + [_sp(8, 80, PointKind.LL)]
        candles = _UPTREND_SAFE_CANDLES + [
            _flat(8, 80),
            _candle(9, high=90, low=78, close=79),  # still below old HL=95
        ]
        events = detect_choch(points, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 8

    # ── HH bar in BEAR context (spec test 7) ─────────────────────────────

    def test_hh_sp_in_bear_context_emits_bearish_choch(self):
        """
        HH structure point in active BEAR context.
        Bar 8: HH SP, candle.high=115 > protected LH=100.
        Step 1 fires bearish CHoCH; step 2 then arms BULL context.
        """
        points  = _DOWNTREND_POINTS + [_sp(8, 115, PointKind.HH)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 115)]
        events  = detect_choch(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.direction              == CHoCHDirection.BEARISH
        assert ev.break_candle_index     == 8
        assert ev.protected_level        == 100.0
        assert ev.reference_structure_type == "LH"
        assert ev.structure_reference_index == 4   # the LH at bar 4
        assert ev.violated_trend         == "downtrend"

    def test_hh_sp_bear_choch_contract_fields(self):
        """All primitive-event-contract fields are correctly populated."""
        points  = _DOWNTREND_POINTS + [_sp(8, 115, PointKind.HH)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 115)]
        ev      = detect_choch(points, candles, "minor")[0]
        assert ev.event_type   == "choch"
        assert ev.status       == "valid"
        assert ev.event_effect == "transition"

    def test_hh_sp_bear_equality_no_choch(self):
        """HH candle.high == protected LH (strict inequality) → no CHoCH."""
        points  = _DOWNTREND_POINTS + [_sp(8, 100, PointKind.HH)]
        candles = _DOWNTREND_SAFE_CANDLES + [_flat(8, 100)]  # high == 100, not > 100
        assert detect_choch(points, candles, "minor") == []

    def test_hh_sp_bear_state_resets_no_duplicate(self):
        """
        After CHoCH fires on the HH bar, state resets.
        A subsequent candle above old LH fires no second CHoCH.
        """
        points  = _DOWNTREND_POINTS + [_sp(8, 115, PointKind.HH)]
        candles = _DOWNTREND_SAFE_CANDLES + [
            _flat(8, 115),
            _candle(9, high=120, low=90, close=95),  # still above old LH=100
        ]
        events = detect_choch(points, candles, "minor")
        assert len(events) == 1
        assert events[0].break_candle_index == 8

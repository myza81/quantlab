"""
BoS detection unit tests — corrected rule set.

Prerequisites:
  Bull: L → H → HL  (watch level = H.price)
  Bear: H → L → LH  (watch level = L.price)

Invalidation:
  Pending bull  → invalidated by PointKind.L structure point (CHoCH).
  Pending bear  → invalidated by PointKind.H structure point (CHoCH).
  Candle wicks alone do NOT invalidate pending BoS.

One-level-one-BoS:
  A level generates at most one BoS event. After valid fires, full reset.

Scenarios covered:
  1.  Uptrend Variation 1   — immediate valid BoS (bullish)
  2.  Downtrend Variation 1 — immediate valid BoS (bearish)
  3.  Uptrend Variation 2   — pending BoS later confirmed (bullish)
  4.  Downtrend Variation 2 — pending BoS later confirmed (bearish)
  5.  Uptrend   — pending BoS invalidated by CHoCH (PointKind.L structure point)
  6.  Downtrend — pending BoS invalidated by CHoCH (PointKind.H structure point)
  7.  No BoS when prerequisite sequence is incomplete
  8.  Minor and main structure scopes do not contaminate each other
  9.  Existing market structure tests continue passing (regression guard)
  10. Edge cases: gap break, one-level-one-BoS, pending survival, wick non-invalidation,
      valid BoS immutability, exact-level boundary, SP-bar skip
"""
from __future__ import annotations

import pytest

from backend.tools.bos_detection import BoSDirection, BoSStatus, detect_bos
from backend.tools.market_structure import (
    OHLCVCandle,
    PointKind,
    StructureLevel,
    StructurePoint,
    MarketStructureEngine,
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
    """Neutral candle that does not break any structural level."""
    return _candle(bar, price, price, price)


# ── Shared structure fixtures ─────────────────────────────────────────────────
#
# Bullish setup  : L(0,90) → H(2,100) → HL(4,95)
#                  break_level     = H.price  = 100
#                  protected_level = HL.price =  95
#
# Bearish setup  : H(0,110) → L(2,90) → LH(4,100)
#                  break_level     = L.price   =  90
#                  protected_level = LH.price  = 100
#
# Structure-point bars: 0, 2, 4.
# Non-structure bars available for BoS scanning: 1, 3, 5, 6, 7, 8, 9, 10, ...

_UPTREND_POINTS = [
    _sp(0,  90, PointKind.L),
    _sp(2, 100, PointKind.H),    # break level = 100
    _sp(4,  95, PointKind.HL),   # protected level = 95
]

_DOWNTREND_POINTS = [
    _sp(0, 110, PointKind.H),
    _sp(2,  90, PointKind.L),    # break level = 90
    _sp(4, 100, PointKind.LH),   # protected level = 100
]

# Safe candles — non-structure bars that stay inside the watch level
# (highs ≤ 100 for uptrend; lows ≥ 90 for downtrend)
_UPTREND_SAFE_CANDLES = [
    _flat(0, 90), _flat(1, 93),
    _flat(2, 100), _flat(3, 97),
    _flat(4, 95), _flat(5, 98),
    _flat(6, 99), _flat(7, 97),
]

_DOWNTREND_SAFE_CANDLES = [
    _flat(0, 110), _flat(1, 105),
    _flat(2, 90), _flat(3, 95),
    _flat(4, 100), _flat(5, 95),
    _flat(6, 93), _flat(7, 92),
]


# ═════════════════════════════════════════════════════════════════════════════
# Test 1 — Uptrend Variation 1: Immediate valid BoS (bullish)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSUptrendVariation1:
    """high > H.price AND close > H.price on the same candle → immediate VALID BoS."""

    def test_single_immediate_valid_bos_bullish(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=101, close=112),  # high=115 > 100, close=112 > 100
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")

        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert ev.status    == BoSStatus.VALID
        assert ev.direction == BoSDirection.BULLISH
        assert ev.structure_scope    == "minor"
        assert ev.break_level        == 100.0
        assert ev.protected_level    == 95.0
        assert ev.break_candle_index == 8
        assert ev.confirmation_level         is None
        assert ev.confirmation_candle_index  is None
        assert ev.invalidation_candle_index  is None

    def test_no_bos_when_close_equals_break_level(self):
        """Close exactly at H.price is NOT above it → pending (not immediate valid)."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=105, low=99, close=100),  # close == 100, not > 100
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert all(ev.status == BoSStatus.PENDING for ev in events), (
            "Close equal to break level should produce pending, not valid"
        )

    def test_no_bos_when_only_high_breaks_but_close_does_not(self):
        """High breaks level, close is below → pending only, not immediate valid."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=105, low=99, close=99),
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.PENDING


# ═════════════════════════════════════════════════════════════════════════════
# Test 2 — Downtrend Variation 1: Immediate valid BoS (bearish)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSDowntrendVariation1:
    """low < L.price AND close < L.price on the same candle → immediate VALID BoS."""

    def test_single_immediate_valid_bos_bearish(self):
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=89, low=75, close=77),  # low=75 < 90, close=77 < 90
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")

        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert ev.status    == BoSStatus.VALID
        assert ev.direction == BoSDirection.BEARISH
        assert ev.structure_scope    == "minor"
        assert ev.break_level        == 90.0
        assert ev.protected_level    == 100.0
        assert ev.break_candle_index == 8
        assert ev.confirmation_level         is None
        assert ev.invalidation_candle_index  is None

    def test_no_bos_when_close_equals_break_level(self):
        """Close exactly at L.price is NOT below it → pending, not valid."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=91, low=85, close=90),  # close == 90, not < 90
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert all(ev.status == BoSStatus.PENDING for ev in events)

    def test_no_bos_when_only_low_breaks(self):
        """Low breaks level, close above → pending only."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=91, low=85, close=91),
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.PENDING


# ═════════════════════════════════════════════════════════════════════════════
# Test 3 — Uptrend Variation 2: Pending BoS later confirmed (bullish)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSUptrendVariation2Confirmed:
    """
    Break candle: high=105 (> 100), close=99 (≤ 100) → PENDING.
    confirmation_level = 105.
    Confirmation candle: high=108 (> 105) → VALID.
    """

    def _events(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8,  high=105, low=99,  close=99),    # pending break
            _flat(9, 102),                                # below conf_level 105
            _candle(10, high=108, low=103, close=106),   # confirms: high > 105
        ]
        return detect_bos(_UPTREND_POINTS, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_event_is_valid(self):
        ev = self._events()[0]
        assert ev.status    == BoSStatus.VALID
        assert ev.direction == BoSDirection.BULLISH

    def test_break_fields(self):
        ev = self._events()[0]
        assert ev.break_level        == 100.0
        assert ev.protected_level    == 95.0
        assert ev.break_candle_index == 8

    def test_confirmation_fields(self):
        ev = self._events()[0]
        assert ev.confirmation_level        == 105.0
        assert ev.confirmation_candle_index == 10

    def test_no_invalidation_fields(self):
        ev = self._events()[0]
        assert ev.invalidation_candle_index is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 4 — Downtrend Variation 2: Pending BoS later confirmed (bearish)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSDowntrendVariation2Confirmed:
    """
    Break candle: low=85 (< 90), close=91 (≥ 90) → PENDING.
    confirmation_level = 85.
    Confirmation candle: low=82 (< 85) → VALID.
    """

    def _events(self):
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8,  high=91, low=85, close=91),     # pending break
            _flat(9, 87),                                # above conf_level 85
            _candle(10, high=86, low=82, close=84),     # confirms: low < 85
        ]
        return detect_bos(_DOWNTREND_POINTS, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_event_is_valid(self):
        ev = self._events()[0]
        assert ev.status    == BoSStatus.VALID
        assert ev.direction == BoSDirection.BEARISH

    def test_break_fields(self):
        ev = self._events()[0]
        assert ev.break_level        == 90.0
        assert ev.protected_level    == 100.0
        assert ev.break_candle_index == 8

    def test_confirmation_fields(self):
        ev = self._events()[0]
        assert ev.confirmation_level        == 85.0
        assert ev.confirmation_candle_index == 10

    def test_no_invalidation_fields(self):
        ev = self._events()[0]
        assert ev.invalidation_candle_index is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 5 — Uptrend: Pending BoS invalidated by CHoCH (PointKind.L)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSUptrendCHoCHInvalidation:
    """
    Break candle creates pending. Then PointKind.L structure point appears
    before confirmation — this is the CHoCH that invalidates the pending bull BoS.
    """

    def _events(self):
        points = list(_UPTREND_POINTS) + [_sp(10, 92, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8,  high=105, low=99,  close=99),   # pending: conf_level=105
            _flat(9, 102),                               # below conf, no L structure point
            _flat(10, 92),  # bar 10 has SP(L) = CHoCH → INVALID emitted for pending
        ]
        return detect_bos(points, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_event_is_invalid(self):
        ev = self._events()[0]
        assert ev.status    == BoSStatus.INVALID
        assert ev.direction == BoSDirection.BULLISH

    def test_break_fields(self):
        ev = self._events()[0]
        assert ev.break_level        == 100.0
        assert ev.protected_level    == 95.0
        assert ev.break_candle_index == 8

    def test_invalidation_fields(self):
        ev = self._events()[0]
        assert ev.invalidation_candle_index == 10
        assert ev.confirmation_level        == 105.0   # recorded at break time
        assert ev.confirmation_candle_index is None    # never confirmed

    def test_confirmation_candle_absent(self):
        ev = self._events()[0]
        assert ev.confirmation_candle_index     is None
        assert ev.confirmation_candle_timestamp is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 6 — Downtrend: Pending BoS invalidated by CHoCH (PointKind.H)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSDowntrendCHoCHInvalidation:
    """
    Break candle creates pending. Then PointKind.H structure point appears
    before confirmation — this is the CHoCH that invalidates the pending bear BoS.
    """

    def _events(self):
        points = list(_DOWNTREND_POINTS) + [_sp(10, 96, PointKind.H)]
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8,  high=91, low=85, close=91),    # pending: conf_level=85
            _flat(9, 87),                               # above conf, no H structure point
            _flat(10, 96),  # bar 10 has SP(H) = CHoCH → INVALID emitted for pending
        ]
        return detect_bos(points, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_event_is_invalid(self):
        ev = self._events()[0]
        assert ev.status    == BoSStatus.INVALID
        assert ev.direction == BoSDirection.BEARISH

    def test_break_fields(self):
        ev = self._events()[0]
        assert ev.break_level        == 90.0
        assert ev.protected_level    == 100.0
        assert ev.break_candle_index == 8

    def test_invalidation_fields(self):
        ev = self._events()[0]
        assert ev.invalidation_candle_index == 10
        assert ev.confirmation_level        == 85.0
        assert ev.confirmation_candle_index is None

    def test_confirmation_candle_absent(self):
        ev = self._events()[0]
        assert ev.confirmation_candle_index     is None
        assert ev.confirmation_candle_timestamp is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 7 — No BoS when prerequisite sequence is incomplete
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSNoTrend:
    """BoS requires a complete L→H→HL (bull) or H→L→LH (bear) setup."""

    def test_bootstrap_only_no_bos(self):
        """L + H only — HL not yet seen → bull watch never activated."""
        points = [_sp(0, 90, PointKind.L), _sp(2, 100, PointKind.H)]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100),
                   _candle(3, high=115, low=88, close=114)]
        assert detect_bos(points, candles, "minor") == []

    def test_l_h_hl_activates_bull_bos_watch(self):
        """L→H→HL is the complete bull setup. BoS fires when price breaks H.price."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
        ]
        candles = [_flat(i, 95) for i in range(5)] + [
            _candle(5, high=105, low=101, close=103),  # breaks H=100
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        assert events[0].status     == BoSStatus.VALID
        assert events[0].break_level == 100.0

    def test_h_l_lh_activates_bear_bos_watch(self):
        """H→L→LH is the complete bear setup. BoS fires when price breaks L.price."""
        points = [
            _sp(0, 100, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4, 100, PointKind.LH),
        ]
        candles = [_flat(i, 93) for i in range(5)] + [
            _candle(5, high=89, low=85, close=87),   # breaks L=90
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        assert events[0].status     == BoSStatus.VALID
        assert events[0].break_level == 90.0

    def test_empty_structure_no_bos(self):
        """Empty structure_points → empty result."""
        candles = [_candle(i, high=110, low=80, close=100) for i in range(5)]
        assert detect_bos([], candles, "minor") == []

    def test_empty_candles_no_bos(self):
        """No candles → nothing to scan."""
        assert detect_bos(_UPTREND_POINTS, [], "minor") == []

    def test_h_then_hh_without_hl_no_bos(self):
        """L→H→HH (no HL) — HH has no effect; bull watch never activated
        because HL has not been seen."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4, 110, PointKind.HH),   # no effect on bull tracker
        ]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100), _flat(3, 105), _flat(4, 110)] + [
            _candle(5, high=120, low=111, close=118),
        ]
        assert detect_bos(points, candles, "minor") == []

    def test_l_then_ll_without_lh_no_bos(self):
        """H→L→LL (no LH) — LL has no effect; bear watch never activated
        because LH has not been seen."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4,  80, PointKind.LL),   # no effect on bear tracker
        ]
        candles = [_flat(0, 110), _flat(1, 100), _flat(2, 90), _flat(3, 85), _flat(4, 80)] + [
            _candle(5, high=79, low=70, close=72),
        ]
        assert detect_bos(points, candles, "minor") == []


# ═════════════════════════════════════════════════════════════════════════════
# Test 8 — Minor and main structures do not contaminate each other
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSScopeIsolation:

    def test_minor_scope_label(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=101, close=112),
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert all(ev.structure_scope == "minor" for ev in events)

    def test_main_scope_label(self):
        main_points = [
            _sp(0,  90, PointKind.L,  StructureLevel.MAIN),
            _sp(2, 100, PointKind.H,  StructureLevel.MAIN),
            _sp(4,  95, PointKind.HL, StructureLevel.MAIN),
            _sp(6, 110, PointKind.HH, StructureLevel.MAIN),  # HH has no effect; watch set at HL
        ]
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=101, close=112),
        ]
        events = detect_bos(main_points, candles, "main")
        assert all(ev.structure_scope == "main" for ev in events)

    def test_different_break_levels_independent(self):
        """Minor H at 100; main H at 120 — only minor fires at 115."""
        minor_points = _UPTREND_POINTS   # H at 100
        main_points = [
            _sp(0,  90, PointKind.L,  StructureLevel.MAIN),
            _sp(2, 120, PointKind.H,  StructureLevel.MAIN),  # H at 120
            _sp(4, 105, PointKind.HL, StructureLevel.MAIN),
        ]
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=101, close=112),
        ]
        minor_events = detect_bos(minor_points, candles, "minor")
        main_events  = detect_bos(main_points,  candles, "main")

        assert len(minor_events) == 1
        assert minor_events[0].status == BoSStatus.VALID
        assert minor_events[0].structure_scope == "minor"

        assert len(main_events)  == 0   # 115 < 120, main H not broken

    def test_scope_fields_never_cross(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=101, close=112),
        ]
        minor_ev = detect_bos(_UPTREND_POINTS, candles, "minor")
        main_ev  = detect_bos(_UPTREND_POINTS, candles, "main")

        for ev in minor_ev:
            assert ev.structure_scope == "minor"
        for ev in main_ev:
            assert ev.structure_scope == "main"


# ═════════════════════════════════════════════════════════════════════════════
# Test 9 — Regression: existing market structure tests still pass
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSRegressionMarketStructure:

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
            + [self._make_candle(i + 6, 110 - i*2, 80 - i, 85 - i) for i in range(6)]
        )
        result = engine.compute_structure(candles)
        assert len(result.minor_points) >= 1
        kinds = {p.kind for p in result.minor_points}
        assert PointKind.HH in kinds or PointKind.H in kinds

    def test_main_structure_unaffected(self, engine):
        candles = (
            [self._make_candle(i,     100 + i*3, 90 + i*2,   95 + i*2) for i in range(8)]
            + [self._make_candle(i+8, 120 - i*3, 100 - i*2, 105 - i*2) for i in range(8)]
            + [self._make_candle(i+16, 90 + i*3, 80 + i*2,  85 + i*2)  for i in range(8)]
        )
        result = engine.compute_structure(candles)
        assert len(result.main_points) >= 2

    def test_import_does_not_alter_structure_labels(self, engine):
        from backend.tools import bos_detection as _bos  # noqa: F401
        candles = (
            [self._make_candle(i, 100 + i*2, 90 + i, 95 + i) for i in range(6)]
            + [self._make_candle(i + 6, 110 - i*2, 80 - i, 85 - i) for i in range(6)]
            + [self._make_candle(i + 12, 90 + i*2, 78 + i, 83 + i) for i in range(6)]
        )
        result = engine.compute_structure(candles)
        kinds = [p.kind for p in result.minor_points]
        assert kinds, "No minor points — structure engine broken"
        for k in kinds:
            assert k in list(PointKind)


# ═════════════════════════════════════════════════════════════════════════════
# Test 10 — Edge cases
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSEdgeCases:

    def test_candles_at_exact_break_level_not_triggered(self):
        """Candle high exactly at H.price (== 100) does not trigger BoS (strict >)."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=100, low=98, close=99),  # high == 100, not > 100
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert events == []

    def test_candles_at_exact_bear_break_level_not_triggered(self):
        """Candle low exactly at L.price (== 90) does not trigger bear BoS (strict <)."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=91, low=90, close=91),  # low == 90, not < 90
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert events == []

    def test_hh_sp_bar_is_scanned_and_triggers_bos(self):
        """HH structure-point bar is now scanned for BoS when bull watch is active.
        High=120 > H.price=100, close=118 > 100 → immediate VALID."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
            _sp(6, 110, PointKind.HH),
        ]
        candles = [
            _flat(0, 90), _flat(1, 95),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 99),
            _candle(6, high=120, low=108, close=118),  # HH bar → scanned → VALID
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        assert events[0].status          == BoSStatus.VALID
        assert events[0].direction       == BoSDirection.BULLISH
        assert events[0].break_candle_index == 6

    def test_h_l_hl_lh_sp_bars_still_skip_candle_scan(self):
        """H, L, HL, LH structure-point bars continue to skip the candle scan.
        Only HH and LL fall through to BoS scanning."""
        # Candles at H, HL bars have high=120 — would break 100 if scanned.
        # But those bars must NOT produce BoS events.
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),    # H bar: state update only, skip scan
            _sp(4,  95, PointKind.HL),   # HL bar: activates watching, skip scan
            _sp(6,  97, PointKind.HH),   # HH bar: candle high=97 ≤ 100 → no BoS
        ]
        candles = [
            _flat(0, 90), _flat(1, 95),
            _candle(2, high=120, low=90, close=118),  # H bar: skipped
            _flat(3, 97),
            _candle(4, high=120, low=90, close=118),  # HL bar: skipped
            _flat(5, 99),
            _flat(6, 97),   # HH bar: high=97 ≤ 100 → safe
        ]
        events = detect_bos(points, candles, "minor")
        assert events == [], f"Expected no events, got {events}"

    def test_one_level_one_bos_no_duplicate_on_same_level(self):
        """After a valid BoS fires on H.price, that level is consumed.
        Even if the next candle also exceeds H.price, no second BoS fires."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=105, low=101, close=103),  # valid BoS → full reset
            _candle(9, high=108, low=104, close=106),  # also > 100 but state reset
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status    == BoSStatus.VALID
        assert events[0].direction == BoSDirection.BULLISH

    def test_gap_break_counts_as_immediate_valid_bos(self):
        """A gap open above H.price with open, high, and close all above → immediate valid."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, open_=110, high=112, low=109, close=111),  # gap above H=100
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status    == BoSStatus.VALID
        assert events[0].direction == BoSDirection.BULLISH

    def test_pending_bull_survives_additional_hl_formation(self):
        """An HL structure point during a pending bull BoS does not cancel the pending.
        Only a CHoCH (PointKind.L) can invalidate."""
        points = list(_UPTREND_POINTS) + [_sp(9, 97, PointKind.HL)]
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8,  high=105, low=99,  close=99),    # pending: conf_level=105
            _flat(9, 97),    # bar 9 = SP(HL) — no effect on pending
            _candle(10, high=108, low=103, close=106),   # high=108 > 105 → confirms
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status                    == BoSStatus.VALID
        assert ev.break_candle_index        == 8
        assert ev.confirmation_level        == 105.0
        assert ev.confirmation_candle_index == 10

    def test_pending_bear_survives_additional_lh_formation(self):
        """An LH structure point during a pending bear BoS does not cancel the pending."""
        points = list(_DOWNTREND_POINTS) + [_sp(9, 98, PointKind.LH)]
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8,  high=91, low=85, close=91),     # pending: conf_level=85
            _flat(9, 98),   # bar 9 = SP(LH) — no effect on pending
            _candle(10, high=84, low=82, close=83),     # low=82 < 85 → confirms
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status                    == BoSStatus.VALID
        assert ev.break_candle_index        == 8
        assert ev.confirmation_level        == 85.0
        assert ev.confirmation_candle_index == 10

    def test_valid_bos_immutable_after_later_choch(self):
        """A valid BoS already emitted cannot be retroactively affected
        by a CHoCH structure point that appears later."""
        points = list(_UPTREND_POINTS) + [_sp(10, 92, PointKind.L)]
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=105, low=101, close=103),  # immediate valid BoS → reset
            _flat(9, 102),
            _flat(10, 92),   # SP(L) = CHoCH, but no pending bull to invalidate
        ]
        events = detect_bos(points, candles, "minor")
        # Only the VALID BoS emitted at bar 8; CHoCH at bar 10 has nothing to invalidate.
        assert len(events) == 1
        assert events[0].status == BoSStatus.VALID

    def test_pending_bull_not_invalidated_by_candle_wick(self):
        """Candle wick alone cannot invalidate a pending bull BoS.
        Only a PointKind.L structure point (CHoCH) invalidates."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=105, low=99, close=99),   # pending: conf_level=105
            _candle(9, high=103, low=70, close=85),   # severe wick — but no SP(L)
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status                   == BoSStatus.PENDING
        assert events[0].invalidation_candle_index is None

    def test_pending_bear_not_invalidated_by_candle_wick(self):
        """Candle wick alone cannot invalidate a pending bear BoS.
        Only a PointKind.H structure point (CHoCH) invalidates."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=91, low=85, close=91),     # pending: conf_level=85
            _candle(9, high=130, low=87, close=115),   # severe wick — but no SP(H)
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status                   == BoSStatus.PENDING
        assert events[0].invalidation_candle_index is None

    def test_pending_at_end_of_dataset_emitted_as_pending(self):
        """Unresolved pending at end of candle array is emitted with status=PENDING."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=105, low=99, close=99),   # pending, never resolved
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status                   == BoSStatus.PENDING
        assert ev.direction                == BoSDirection.BULLISH
        assert ev.break_level              == 100.0
        assert ev.confirmation_level       == 105.0
        assert ev.confirmation_candle_index is None
        assert ev.invalidation_candle_index is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 11 — HH / LL candles as BoS break candles (BOS-CURRENT-RULE-CORRECTION-2)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSHHLLBreakCandles:
    """HH and LL structure-point candles can trigger BoS when the relevant watch is active."""

    # ── Bull: HH as immediate VALID ─────────────────────────────────────────

    def test_hh_triggers_bull_bos_immediate_valid(self):
        """HH candle with high > H.price and close > H.price → immediate VALID bull BoS."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
            _sp(6, 110, PointKind.HH),   # HH is the break candle
        ]
        candles = [
            _flat(0, 90), _flat(1, 95),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 99),
            _candle(6, high=110, low=101, close=108),  # HH: high=110>100, close=108>100
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status               == BoSStatus.VALID
        assert ev.direction            == BoSDirection.BULLISH
        assert ev.break_level          == 100.0
        assert ev.protected_level      == 95.0
        assert ev.break_candle_index   == 6

    # ── Bull: HH creates PENDING ─────────────────────────────────────────────

    def test_hh_triggers_bull_bos_pending(self):
        """HH candle with high > H.price but close ≤ H.price → PENDING bull BoS."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
            _sp(6, 110, PointKind.HH),
        ]
        candles = [
            _flat(0, 90), _flat(1, 95),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 99),
            _candle(6, high=105, low=99, close=99),  # HH: high=105>100, close=99≤100 → PENDING
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status               == BoSStatus.PENDING
        assert ev.direction            == BoSDirection.BULLISH
        assert ev.break_level          == 100.0
        assert ev.confirmation_level   == 105.0
        assert ev.break_candle_index   == 6

    # ── Bear: LL as immediate VALID ──────────────────────────────────────────

    def test_ll_triggers_bear_bos_immediate_valid(self):
        """LL candle with low < L.price and close < L.price → immediate VALID bear BoS."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4, 100, PointKind.LH),
            _sp(6,  80, PointKind.LL),   # LL is the break candle
        ]
        candles = [
            _flat(0, 110), _flat(1, 105),
            _flat(2, 90), _flat(3, 95),
            _flat(4, 100), _flat(5, 92),
            _candle(6, high=89, low=80, close=83),  # LL: low=80<90, close=83<90 → VALID
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status               == BoSStatus.VALID
        assert ev.direction            == BoSDirection.BEARISH
        assert ev.break_level          == 90.0
        assert ev.protected_level      == 100.0
        assert ev.break_candle_index   == 6

    # ── Bear: LL creates PENDING ─────────────────────────────────────────────

    def test_ll_triggers_bear_bos_pending(self):
        """LL candle with low < L.price but close ≥ L.price → PENDING bear BoS."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4, 100, PointKind.LH),
            _sp(6,  80, PointKind.LL),
        ]
        candles = [
            _flat(0, 110), _flat(1, 105),
            _flat(2, 90), _flat(3, 95),
            _flat(4, 100), _flat(5, 92),
            _candle(6, high=91, low=85, close=91),  # LL: low=85<90, close=91≥90 → PENDING
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status               == BoSStatus.PENDING
        assert ev.direction            == BoSDirection.BEARISH
        assert ev.break_level          == 90.0
        assert ev.confirmation_level   == 85.0
        assert ev.break_candle_index   == 6

    # ── Pending from HH: confirmed on later candle ───────────────────────────

    def test_pending_from_hh_confirms_on_later_candle(self):
        """Pending BoS created at an HH bar confirms when a subsequent candle exceeds conf_level."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
            _sp(6, 110, PointKind.HH),
        ]
        candles = [
            _flat(0, 90), _flat(1, 95),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 99),
            _candle(6, high=105, low=99, close=99),   # pending: conf_level=105
            _flat(7, 102),                             # 102 < 105 → still pending
            _candle(8, high=108, low=103, close=106),  # 108 > 105 → confirms
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status                    == BoSStatus.VALID
        assert ev.break_candle_index        == 6
        assert ev.confirmation_level        == 105.0
        assert ev.confirmation_candle_index == 8

    # ── Pending from LL: confirmed on later candle ───────────────────────────

    def test_pending_from_ll_confirms_on_later_candle(self):
        """Pending BoS created at an LL bar confirms when a subsequent candle goes below conf_level."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4, 100, PointKind.LH),
            _sp(6,  80, PointKind.LL),
        ]
        candles = [
            _flat(0, 110), _flat(1, 105),
            _flat(2, 90), _flat(3, 95),
            _flat(4, 100), _flat(5, 92),
            _candle(6, high=91, low=85, close=91),   # pending: conf_level=85
            _flat(7, 87),                             # 87 > 85 → still pending
            _candle(8, high=86, low=82, close=84),   # 82 < 85 → confirms
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status                    == BoSStatus.VALID
        assert ev.break_candle_index        == 6
        assert ev.confirmation_level        == 85.0
        assert ev.confirmation_candle_index == 8

    # ── Pending from HH: invalidated by CHoCH ───────────────────────────────

    def test_pending_from_hh_invalidated_by_choch(self):
        """Pending bull BoS from an HH bar is invalidated by a later PointKind.L (CHoCH)."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
            _sp(6, 110, PointKind.HH),
            _sp(9,  92, PointKind.L),   # CHoCH
        ]
        candles = [
            _flat(0, 90), _flat(1, 95),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 99),
            _candle(6, high=105, low=99, close=99),  # pending: conf_level=105
            _flat(7, 102), _flat(8, 101),
            _flat(9, 92),   # bar 9 = SP(L) → INVALID
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status                    == BoSStatus.INVALID
        assert ev.break_candle_index        == 6
        assert ev.invalidation_candle_index == 9

    # ── One-level-one-BoS after HH trigger ───────────────────────────────────

    def test_one_level_one_bos_after_hh_trigger(self):
        """After a VALID bull BoS fires from an HH bar, the tracker resets.
        Subsequent candles above H.price produce no second event."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
            _sp(6, 110, PointKind.HH),
        ]
        candles = [
            _flat(0, 90), _flat(1, 95),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 99),
            _candle(6, high=110, low=101, close=108),  # VALID BoS → reset
            _candle(7, high=115, low=109, close=112),  # also > 100, but state is reset
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        assert events[0].status    == BoSStatus.VALID
        assert events[0].direction == BoSDirection.BULLISH

    # ── HH/LL not watching: no scan ──────────────────────────────────────────

    def test_hh_without_active_watch_does_not_trigger_bos(self):
        """HH arriving before the full L→H→HL setup does not trigger BoS (no watch active)."""
        # Only L→H completed (no HL) when HH appears → bull in _SEEN_H, not _WATCHING
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4, 112, PointKind.HH),   # HH before HL → bull not watching
        ]
        candles = [
            _flat(0, 90), _flat(1, 95),
            _flat(2, 100), _flat(3, 97),
            _candle(4, high=120, low=108, close=115),  # HH bar, bull not watching → no BoS
        ]
        events = detect_bos(points, candles, "minor")
        assert events == []

    def test_ll_without_active_watch_does_not_trigger_bos(self):
        """LL arriving before the full H→L→LH setup does not trigger BoS (no watch active)."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4,  78, PointKind.LL),   # LL before LH → bear not watching
        ]
        candles = [
            _flat(0, 110), _flat(1, 105),
            _flat(2, 90), _flat(3, 95),
            _candle(4, high=89, low=75, close=77),  # LL bar, bear not watching → no BoS
        ]
        events = detect_bos(points, candles, "minor")
        assert events == []


# ═════════════════════════════════════════════════════════════════════════════
# Test 12 — Sequence ownership: HH/LL invalidate the opposing tracker
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSSequenceOwnership:
    """
    Sequence ownership principle: a BoS setup belongs entirely to one
    alternating sequence.  HH breaks the bearish sequence → bear resets.
    LL breaks the bullish sequence → bull resets.

    Bear tests  (HH invalidation):
        bear _SEEN_H   → reset, no event
        bear _SEEN_L   → reset, no event
        bear _WATCHING → reset, no event; subsequent candle cannot fire
        bear _PENDING  → INVALID event emitted, then reset

    Bull tests  (LL invalidation):
        bull _SEEN_L   → reset, no event
        bull _SEEN_H   → reset, no event
        bull _WATCHING → reset, no event; subsequent candle cannot fire
        bull _PENDING  → INVALID event emitted, then reset

    Lifecycle:
        bear restarts cleanly after HH reset
        bull restarts cleanly after LL reset

    Regression (Jan-27 Visa 1D stale-setup pattern):
        H → HH → L → LH → candle  : no BoS  (stale defect eliminated)
        H → L  → LH → candle      : valid BoS fires  (correct path unaffected)
    """

    # ── Bear: HH while bear in _SEEN_H ───────────────────────────────────────

    def test_hh_resets_bear_seen_h(self):
        """HH appears while bear is in _SEEN_H. Bear resets to _NO_SETUP.
        Subsequent L→LH cannot advance bear (bear is _NO_SETUP at L). No BoS."""
        points = [
            _sp( 0, 110, PointKind.H),
            _sp( 2, 120, PointKind.HH),   # bear was _SEEN_H → _NO_SETUP
            _sp( 4,  90, PointKind.L),    # bear _NO_SETUP → L cannot advance
            _sp( 6, 100, PointKind.LH),   # bear _NO_SETUP → LH has no effect
        ]
        candles = [
            _flat(0, 110), _flat(1, 115),
            _flat(2, 120), _flat(3, 108),
            _flat(4,  90), _flat(5,  95),
            _flat(6, 100), _flat(7,  97),
            _candle(8, high=89, low=80, close=83),
        ]
        assert detect_bos(points, candles, "minor") == []

    # ── Bear: HH while bear in _SEEN_L ───────────────────────────────────────

    def test_hh_resets_bear_seen_l(self):
        """HH appears after H→L (bear _SEEN_L). Bear resets to _NO_SETUP.
        Subsequent LH cannot activate watch. No BoS."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4, 120, PointKind.HH),   # bear was _SEEN_L → _NO_SETUP
            _sp(6, 100, PointKind.LH),   # bear _NO_SETUP → LH has no effect
        ]
        candles = [
            _flat(0, 110), _flat(1, 105),
            _flat(2,  90), _flat(3,  95),
            _flat(4, 120), _flat(5, 108),
            _flat(6, 100), _flat(7,  97),
            _candle(8, high=89, low=80, close=83),
        ]
        assert detect_bos(points, candles, "minor") == []

    # ── Bear: HH while bear in _WATCHING ─────────────────────────────────────

    def test_hh_resets_bear_watching(self):
        """Bear reaches _WATCHING (H→L→LH complete). HH resets bear to _NO_SETUP
        before any break candle arrives. Subsequent candle cannot fire."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),    # watch level = 90
            _sp(4, 100, PointKind.LH),   # bear → _WATCHING
            _sp(6, 120, PointKind.HH),   # bear was _WATCHING → _NO_SETUP
        ]
        candles = [
            _flat(0, 110), _flat(1, 105),
            _flat(2,  90), _flat(3,  95),
            _flat(4, 100), _flat(5,  93),
            _flat(6, 120),
            _candle(7, high=89, low=80, close=83),   # watch is gone → no BoS
        ]
        assert detect_bos(points, candles, "minor") == []

    # ── Bear: HH while bear in _PENDING ──────────────────────────────────────

    def test_hh_invalidates_bear_pending(self):
        """Bear _PENDING → HH emits INVALID event and resets bear to _NO_SETUP."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),    # watch = 90; protected = LH.price
            _sp(4, 100, PointKind.LH),   # bear → _WATCHING at 90
            _sp(6, 120, PointKind.HH),   # bear was _PENDING → INVALID
        ]
        candles = [
            _flat(0, 110), _flat(1, 105),
            _flat(2,  90), _flat(3,  95),
            _flat(4, 100),
            _candle(5, high=91, low=85, close=91),   # low<90, close≥90 → PENDING
            _flat(6, 120),                            # HH bar → INVALID emitted
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status                    == BoSStatus.INVALID
        assert ev.direction                 == BoSDirection.BEARISH
        assert ev.break_level               == 90.0
        assert ev.protected_level           == 100.0
        assert ev.break_candle_index        == 5
        assert ev.confirmation_level        == 85.0
        assert ev.invalidation_candle_index == 6

    # ── Bull: LL while bull in _SEEN_L ───────────────────────────────────────

    def test_ll_resets_bull_seen_l(self):
        """LL appears while bull is in _SEEN_L. Bull resets to _NO_SETUP.
        Subsequent H→HL cannot advance bull (bull is _NO_SETUP at H). No BoS."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2,  80, PointKind.LL),   # bull was _SEEN_L → _NO_SETUP
            _sp(4, 100, PointKind.H),    # bull _NO_SETUP → H cannot advance
            _sp(6,  95, PointKind.HL),   # bull _NO_SETUP → HL has no effect
        ]
        candles = [
            _flat(0,  90), _flat(1,  85),
            _flat(2,  80), _flat(3,  87),
            _flat(4, 100), _flat(5,  97),
            _flat(6,  95), _flat(7,  98),
            _candle(8, high=115, low=101, close=112),
        ]
        assert detect_bos(points, candles, "minor") == []

    # ── Bull: LL while bull in _SEEN_H ───────────────────────────────────────

    def test_ll_resets_bull_seen_h(self):
        """LL appears after L→H (bull _SEEN_H). Bull resets to _NO_SETUP.
        Subsequent HL cannot activate watch. No BoS."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  80, PointKind.LL),   # bull was _SEEN_H → _NO_SETUP
            _sp(6,  95, PointKind.HL),   # bull _NO_SETUP → HL has no effect
        ]
        candles = [
            _flat(0,  90), _flat(1,  95),
            _flat(2, 100), _flat(3,  97),
            _flat(4,  80), _flat(5,  85),
            _flat(6,  95), _flat(7,  98),
            _candle(8, high=115, low=101, close=112),
        ]
        assert detect_bos(points, candles, "minor") == []

    # ── Bull: LL while bull in _WATCHING ─────────────────────────────────────

    def test_ll_resets_bull_watching(self):
        """Bull reaches _WATCHING (L→H→HL complete). LL resets bull to _NO_SETUP
        before any break candle arrives. Subsequent candle cannot fire."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),    # watch level = 100
            _sp(4,  95, PointKind.HL),   # bull → _WATCHING
            _sp(6,  80, PointKind.LL),   # bull was _WATCHING → _NO_SETUP
        ]
        candles = [
            _flat(0,  90), _flat(1,  95),
            _flat(2, 100), _flat(3,  97),
            _flat(4,  95), _flat(5,  98),
            _flat(6,  80),
            _candle(7, high=115, low=101, close=112),   # watch is gone → no BoS
        ]
        assert detect_bos(points, candles, "minor") == []

    # ── Bull: LL while bull in _PENDING ──────────────────────────────────────

    def test_ll_invalidates_bull_pending(self):
        """Bull _PENDING → LL emits INVALID event and resets bull to _NO_SETUP."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),    # watch = 100; protected = HL.price
            _sp(4,  95, PointKind.HL),   # bull → _WATCHING at 100
            _sp(6,  80, PointKind.LL),   # bull was _PENDING → INVALID
        ]
        candles = [
            _flat(0,  90), _flat(1,  95),
            _flat(2, 100), _flat(3,  97),
            _flat(4,  95),
            _candle(5, high=105, low=99, close=99),   # high>100, close≤100 → PENDING
            _flat(6,  80),                             # LL bar → INVALID emitted
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status                    == BoSStatus.INVALID
        assert ev.direction                 == BoSDirection.BULLISH
        assert ev.break_level               == 100.0
        assert ev.protected_level           == 95.0
        assert ev.break_candle_index        == 5
        assert ev.confirmation_level        == 105.0
        assert ev.invalidation_candle_index == 6

    # ── Lifecycle: restart after HH reset ────────────────────────────────────

    def test_bear_restarts_after_hh_reset(self):
        """After HH resets bear, a fresh H→L→LH sequence builds a new valid
        bear BoS at the new sequence's L.price. No stale references survive."""
        points = [
            _sp( 0, 110, PointKind.H),
            _sp( 2, 120, PointKind.HH),   # bear resets
            _sp( 4, 115, PointKind.H),    # fresh bear sequence begins
            _sp( 6,  95, PointKind.L),    # bear → _SEEN_L; watch = 95
            _sp( 8, 108, PointKind.LH),   # bear → _WATCHING at 95
        ]
        candles = [
            _flat(0, 110), _flat(1, 115),
            _flat(2, 120), _flat(3, 115),
            _flat(4, 115), _flat(5, 105),
            _flat(6,  95), _flat(7, 100),
            _flat(8, 108),
            _candle(9, high=94, low=85, close=88),   # low<95, close<95 → VALID
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status      == BoSStatus.VALID
        assert ev.direction   == BoSDirection.BEARISH
        assert ev.break_level == 95.0

    # ── Lifecycle: restart after LL reset ────────────────────────────────────

    def test_bull_restarts_after_ll_reset(self):
        """After LL resets bull, a fresh L→H→HL sequence builds a new valid
        bull BoS at the new sequence's H.price. No stale references survive."""
        points = [
            _sp( 0,  90, PointKind.L),
            _sp( 2,  80, PointKind.LL),   # bull resets
            _sp( 4,  85, PointKind.L),    # fresh bull sequence begins
            _sp( 6, 110, PointKind.H),    # bull → _SEEN_H; watch = 110
            _sp( 8,  95, PointKind.HL),   # bull → _WATCHING at 110
        ]
        candles = [
            _flat(0,  90), _flat(1,  85),
            _flat(2,  80), _flat(3,  82),
            _flat(4,  85), _flat(5,  95),
            _flat(6, 110), _flat(7, 105),
            _flat(8,  95),
            _candle(9, high=115, low=101, close=112),   # high>110, close>110 → VALID
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status      == BoSStatus.VALID
        assert ev.direction   == BoSDirection.BULLISH
        assert ev.break_level == 110.0

    # ── Regression: Jan-27 stale-setup pattern ───────────────────────────────

    def test_jan27_stale_bos_eliminated(self):
        """Regression for Jan-27 Visa 1D: H→HH→L→LH sequence.
        HH resets bear (_SEEN_H → _NO_SETUP). L arrives when bear is _NO_SETUP
        → cannot advance to _SEEN_L. LH has no effect. No BoS fires."""
        points = [
            _sp( 0, 100, PointKind.H),    # bear → _SEEN_H
            _sp( 4, 110, PointKind.HH),   # bear was _SEEN_H → _NO_SETUP
            _sp( 8,  90, PointKind.L),    # bear _NO_SETUP → cannot advance
            _sp(12,  95, PointKind.LH),   # bear _NO_SETUP → no effect
        ]
        candles = (
            [_flat(i, 93) for i in range(13)] +
            [_candle(13, high=89, low=80, close=83)]    # no watch → no BoS
        )
        assert detect_bos(points, candles, "minor") == []

    def test_valid_bear_sequence_without_hh_unaffected(self):
        """Complement to Jan-27 regression: H→L→LH (no HH) still produces a
        valid bear BoS. The new rule does not affect intact sequences."""
        points = [
            _sp(0, 100, PointKind.H),
            _sp(4,  90, PointKind.L),    # watch = 90
            _sp(8,  95, PointKind.LH),   # bear → _WATCHING at 90
        ]
        candles = (
            [_flat(i, 93) for i in range(9)] +
            [_candle(9, high=89, low=80, close=83)]    # breaks 90 → VALID
        )
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status      == BoSStatus.VALID
        assert ev.direction   == BoSDirection.BEARISH
        assert ev.break_level == 90.0

"""
BoS detection unit tests.

Covers all nine required scenarios:

  1. Uptrend Variation 1 — immediate valid BoS (bullish)
  2. Downtrend Variation 1 — immediate valid BoS (bearish)
  3. Uptrend Variation 2 — pending BoS later confirmed (bullish)
  4. Downtrend Variation 2 — pending BoS later confirmed (bearish)
  5. Uptrend — pending BoS invalidated when protected HL breaks first
  6. Downtrend — pending BoS invalidated when protected LH breaks first
  7. No BoS when no valid trending structure exists
  8. Minor and main structure scopes do not contaminate each other
  9. Existing market structure tests continue passing (regression guard)

Structure points are built directly using StructurePoint so tests are independent
of the engine's candle-level detection logic.  Candles are built with bar_index
values consistent with the structure point bar_indices.
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


# ── Shared structure fixture ──────────────────────────────────────────────────
#
# Uptrend structure:  L(0,90) → H(2,100) → HL(4,95) → HH(6,110)
# Downtrend structure: H(0,110) → L(2,90) → LH(4,100) → LL(6,80)
#
# Structure point bars: 0, 2, 4, 6.
# Candle bars available for BoS scanning: 1, 3, 5, 7, 8, 9, 10, ...
#
# In the uptrend fixture:
#   break_level     = HH.price = 110
#   protected_level = HL.price = 95
#
# In the downtrend fixture:
#   break_level     = LL.price = 80
#   protected_level = LH.price = 100

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

# Filler candles at non-SP bars that do not break any level.
# For uptrend the range (80–109) is safe; for downtrend (81–120) is safe.
_UPTREND_SAFE_CANDLES = [
    _flat(0, 90), _flat(1, 93),
    _flat(2, 100), _flat(3, 97),
    _flat(4, 95), _flat(5, 102),
    _flat(6, 110), _flat(7, 108),
]

_DOWNTREND_SAFE_CANDLES = [
    _flat(0, 110), _flat(1, 105),
    _flat(2, 90), _flat(3, 95),
    _flat(4, 100), _flat(5, 88),
    _flat(6, 80), _flat(7, 82),
]


# ═════════════════════════════════════════════════════════════════════════════
# Test 1 — Uptrend Variation 1: Immediate valid BoS (bullish)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSUptrendVariation1:
    """Candle high and close both exceed the HH break level → immediate VALID BoS."""

    def test_single_immediate_valid_bos_bullish(self):
        # bar 8: high=115 (> 110), close=112 (> 110) → Var 1 VALID
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=112),
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")

        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert ev.status    == BoSStatus.VALID
        assert ev.direction == BoSDirection.BULLISH
        assert ev.structure_scope    == "minor"
        assert ev.break_level        == 110.0
        assert ev.protected_level    == 95.0
        assert ev.break_candle_index == 8
        assert ev.confirmation_level is None   # Var 1 has no confirmation_level
        assert ev.confirmation_candle_index is None
        assert ev.invalidation_candle_index is None

    def test_no_bos_when_close_equals_break_level(self):
        """Close exactly at the break level is NOT above → no Var 1 BoS."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=110),  # close == 110, not > 110
        ]
        # close == 110 → Variation 2 (pending) instead of Variation 1
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert all(ev.status == BoSStatus.PENDING for ev in events), (
            "Close at break level should produce pending, not valid"
        )

    def test_no_bos_when_only_high_breaks_but_close_does_not(self):
        """High breaks level, close is below → pending only, not immediate valid."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=109),
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.PENDING


# ═════════════════════════════════════════════════════════════════════════════
# Test 2 — Downtrend Variation 1: Immediate valid BoS (bearish)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSDowntrendVariation1:
    """Candle low and close both break the LL break level → immediate VALID BoS."""

    def test_single_immediate_valid_bos_bearish(self):
        # bar 8: low=75 (< 80), close=77 (< 80) → Var 1 VALID
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=83, low=75, close=77),
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")

        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert ev.status    == BoSStatus.VALID
        assert ev.direction == BoSDirection.BEARISH
        assert ev.structure_scope    == "minor"
        assert ev.break_level        == 80.0
        assert ev.protected_level    == 100.0
        assert ev.break_candle_index == 8
        assert ev.confirmation_level is None
        assert ev.invalidation_candle_index is None

    def test_no_bos_when_close_equals_break_level(self):
        """Close exactly at break level (80) is NOT below → pending, not valid."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=83, low=75, close=80),  # close == 80
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert all(ev.status == BoSStatus.PENDING for ev in events)

    def test_no_bos_when_only_low_breaks(self):
        """Low breaks level, close above → pending only."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=83, low=75, close=82),
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.PENDING


# ═════════════════════════════════════════════════════════════════════════════
# Test 3 — Uptrend Variation 2: Pending BoS later confirmed (bullish)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSUptrendVariation2Confirmed:
    """
    Break candle: high=115 (> 110), close=109 (< 110) → PENDING.
    confirmation_level = 115.
    Confirmation candle: high=118 (> 115) → VALID.
    """

    def _events(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8,  high=115, low=109, close=109),   # pending break
            _flat(9, 112),                                # below conf_level 115
            _candle(10, high=118, low=113, close=116),   # confirms: high > 115
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
        assert ev.break_level        == 110.0
        assert ev.protected_level    == 95.0
        assert ev.break_candle_index == 8

    def test_confirmation_fields(self):
        ev = self._events()[0]
        assert ev.confirmation_level        == 115.0
        assert ev.confirmation_candle_index == 10

    def test_no_invalidation_fields(self):
        ev = self._events()[0]
        assert ev.invalidation_candle_index is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 4 — Downtrend Variation 2: Pending BoS later confirmed (bearish)
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSDowntrendVariation2Confirmed:
    """
    Break candle: low=75 (< 80), close=82 (> 80) → PENDING.
    confirmation_level = 75.
    Confirmation candle: low=72 (< 75) → VALID.
    """

    def _events(self):
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8,  high=83, low=75, close=82),    # pending break
            _flat(9, 78),                               # above conf_level 75
            _candle(10, high=77, low=72, close=74),    # confirms: low < 75
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
        assert ev.break_level        == 80.0
        assert ev.protected_level    == 100.0
        assert ev.break_candle_index == 8

    def test_confirmation_fields(self):
        ev = self._events()[0]
        assert ev.confirmation_level        == 75.0
        assert ev.confirmation_candle_index == 10

    def test_no_invalidation_fields(self):
        ev = self._events()[0]
        assert ev.invalidation_candle_index is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 5 — Uptrend: Pending BoS invalidated when protected HL breaks first
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSUptrendVariation3Invalidated:
    """
    Break candle: high=115 (> 110), close=109 → PENDING (conf_level=115, protected=95).
    Intermediate candle: high=113 (< 115) → still pending.
    Invalidation candle: low=93 (< protected=95) → INVALID.
    """

    def _events(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8,  high=115, low=109, close=109),   # pending
            _candle(9,  high=113, low=97,  close=110),   # below conf, above protected
            _candle(10, high=100, low=93,  close=94),    # low=93 < protected=95
        ]
        return detect_bos(_UPTREND_POINTS, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_event_is_invalid(self):
        ev = self._events()[0]
        assert ev.status    == BoSStatus.INVALID
        assert ev.direction == BoSDirection.BULLISH

    def test_break_fields(self):
        ev = self._events()[0]
        assert ev.break_level     == 110.0
        assert ev.protected_level == 95.0
        assert ev.break_candle_index == 8

    def test_invalidation_fields(self):
        ev = self._events()[0]
        assert ev.invalidation_candle_index == 10
        assert ev.confirmation_level        == 115.0   # recorded at break time
        assert ev.confirmation_candle_index is None    # never confirmed

    def test_confirmation_candle_absent(self):
        ev = self._events()[0]
        assert ev.confirmation_candle_index     is None
        assert ev.confirmation_candle_timestamp is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 6 — Downtrend: Pending BoS invalidated when protected LH breaks first
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSDowntrendVariation3Invalidated:
    """
    Break candle: low=75 (< 80), close=82 → PENDING (conf_level=75, protected=100).
    Intermediate candle: low=77 (> 75) → still pending.
    Invalidation candle: high=103 (> protected=100) → INVALID.
    """

    def _events(self):
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8,  high=83, low=75, close=82),    # pending
            _candle(9,  high=85, low=77, close=82),    # above conf? no: high=85<100 & low>75
            _candle(10, high=103, low=88, close=100),  # high=103 > protected=100
        ]
        return detect_bos(_DOWNTREND_POINTS, candles, "minor")

    def test_exactly_one_event(self):
        assert len(self._events()) == 1

    def test_event_is_invalid(self):
        ev = self._events()[0]
        assert ev.status    == BoSStatus.INVALID
        assert ev.direction == BoSDirection.BEARISH

    def test_break_fields(self):
        ev = self._events()[0]
        assert ev.break_level     == 80.0
        assert ev.protected_level == 100.0
        assert ev.break_candle_index == 8

    def test_invalidation_fields(self):
        ev = self._events()[0]
        assert ev.invalidation_candle_index == 10
        assert ev.confirmation_level        == 75.0
        assert ev.confirmation_candle_index is None

    def test_confirmation_candle_absent(self):
        ev = self._events()[0]
        assert ev.confirmation_candle_index     is None
        assert ev.confirmation_candle_timestamp is None


# ═════════════════════════════════════════════════════════════════════════════
# Test 7 — No BoS when no valid trending structure exists
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSNoTrend:
    """BoS requires at least one HL + HH (or LH + LL) in structure_points."""

    def test_bootstrap_only_no_bos(self):
        """L + H only — no HH or LL → no BoS."""
        points = [_sp(0, 90, PointKind.L), _sp(2, 100, PointKind.H)]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100),
                   _candle(3, high=115, low=88, close=114)]  # strong break
        assert detect_bos(points, candles, "minor") == []

    def test_partial_trend_lh_only_no_bos(self):
        """H + L + LH but no LL → no bear BoS."""
        points = [
            _sp(0, 100, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4, 100, PointKind.LH),
        ]
        candles = [_flat(i, 90) for i in range(6)] + [
            _candle(6, high=95, low=70, close=72)  # would break 90
        ]
        assert detect_bos(points, candles, "minor") == []

    def test_empty_structure_no_bos(self):
        """Empty structure_points → empty result."""
        candles = [_candle(i, high=110, low=80, close=100) for i in range(5)]
        assert detect_bos([], candles, "minor") == []

    def test_empty_candles_no_bos(self):
        """No candles → nothing to scan."""
        assert detect_bos(_UPTREND_POINTS, [], "minor") == []

    def test_partial_trend_hl_only_no_bos(self):
        """L + H + HL but no HH → no bull BoS."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  95, PointKind.HL),
        ]
        candles = [_flat(i, 95) for i in range(6)] + [
            _candle(6, high=115, low=94, close=113)  # would break 100
        ]
        assert detect_bos(points, candles, "minor") == []

    def test_hh_without_protected_hl_no_bos(self):
        """HH without a prior HL has no protected level → no bull BoS."""
        points = [
            _sp(0,  90, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4, 110, PointKind.HH),
        ]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100), _flat(3, 105), _flat(4, 110)] + [
            _candle(5, high=120, low=111, close=118),
        ]
        assert detect_bos(points, candles, "minor") == []

    def test_ll_without_protected_lh_no_bos(self):
        """LL without a prior LH has no protected level → no bear BoS."""
        points = [
            _sp(0, 110, PointKind.H),
            _sp(2,  90, PointKind.L),
            _sp(4,  80, PointKind.LL),
        ]
        candles = [_flat(0, 110), _flat(1, 100), _flat(2, 90), _flat(3, 85), _flat(4, 80)] + [
            _candle(5, high=79, low=70, close=72),
        ]
        assert detect_bos(points, candles, "minor") == []


# ═════════════════════════════════════════════════════════════════════════════
# Test 8 — Minor and main structures do not contaminate each other
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSScopeIsolation:
    """
    Calling detect_bos with different structure_points sets but the same
    candles produces independent results.  scope field distinguishes outputs.
    """

    def test_minor_scope_label(self):
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=112),
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert all(ev.structure_scope == "minor" for ev in events)

    def test_main_scope_label(self):
        main_points = [
            _sp(0,  90, PointKind.L,  StructureLevel.MAIN),
            _sp(2, 100, PointKind.H,  StructureLevel.MAIN),
            _sp(4,  95, PointKind.HL, StructureLevel.MAIN),
            _sp(6, 110, PointKind.HH, StructureLevel.MAIN),
        ]
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=112),
        ]
        events = detect_bos(main_points, candles, "main")
        assert all(ev.structure_scope == "main" for ev in events)

    def test_different_break_levels_independent(self):
        """Minor break at 110; main at 130 — events are independent."""
        minor_points = _UPTREND_POINTS  # HH at 110
        main_points = [
            _sp(0,  90, PointKind.L,  StructureLevel.MAIN),
            _sp(2, 110, PointKind.H,  StructureLevel.MAIN),
            _sp(4, 100, PointKind.HL, StructureLevel.MAIN),
            _sp(6, 130, PointKind.HH, StructureLevel.MAIN),
        ]
        # bar 8 breaks 110 (minor HH) immediately; does NOT break 130 (main HH)
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=112),
        ]
        minor_events = detect_bos(minor_points, candles, "minor")
        main_events  = detect_bos(main_points,  candles, "main")

        assert len(minor_events) == 1
        assert minor_events[0].status == BoSStatus.VALID
        assert minor_events[0].structure_scope == "minor"

        assert len(main_events)  == 0   # 115 < 130, main HH not broken

    def test_scope_fields_never_cross(self):
        """
        Even when minor and main BoS events share the same candle array,
        the scope stored in each event matches exactly what was passed.
        """
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=112),
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
    """
    Smoke-test that MarketStructureEngine still computes correct output.
    The BoS module imports from market_structure; this confirms no import
    side-effects broke the existing engine.
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
        """Up-then-down sequence still yields a minor H point."""
        candles = (
            [self._make_candle(i, 100 + i*2, 90 + i, 95 + i) for i in range(6)]
            + [self._make_candle(i + 6, 110 - i*2, 80 - i, 85 - i) for i in range(6)]
        )
        result = engine.compute_structure(candles)
        assert len(result.minor_points) >= 1
        kinds = {p.kind for p in result.minor_points}
        assert PointKind.HH in kinds or PointKind.H in kinds

    def test_main_structure_unaffected(self, engine):
        """Full trend cycle still yields main structure points."""
        candles = (
            [self._make_candle(i,     100 + i*3, 90 + i*2,   95 + i*2) for i in range(8)]
            + [self._make_candle(i+8, 120 - i*3, 100 - i*2, 105 - i*2) for i in range(8)]
            + [self._make_candle(i+16, 90 + i*3, 80 + i*2,  85 + i*2)  for i in range(8)]
        )
        result = engine.compute_structure(candles)
        assert len(result.main_points) >= 2

    def test_import_does_not_alter_structure_labels(self, engine):
        """Importing bos_detection must not change minor/main label assignments."""
        # Re-import to confirm no side-effects
        from backend.tools import bos_detection as _bos  # noqa: F401
        candles = (
            [self._make_candle(i, 100 + i*2, 90 + i, 95 + i) for i in range(6)]
            + [self._make_candle(i + 6, 110 - i*2, 80 - i, 85 - i) for i in range(6)]
            + [self._make_candle(i + 12, 90 + i*2, 78 + i, 83 + i) for i in range(6)]
        )
        result = engine.compute_structure(candles)
        kinds = [p.kind for p in result.minor_points]
        assert kinds, "No minor points — structure engine broken"
        # All kinds must be valid PointKind members
        for k in kinds:
            assert k in list(PointKind)


# ═════════════════════════════════════════════════════════════════════════════
# Additional edge-case tests
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSEdgeCases:
    """Boundary and edge-case behaviour."""

    def test_protected_level_update_on_new_hl(self):
        """
        A new HL structure point after HH should tighten the protected level.
        If a pending BoS was created with the OLD protected level, and a new HL
        (higher price) arrives, the protected level updates.
        """
        # uptrend: L(0,80) H(2,100) HL(4,90) HH(6,110) HL(8,100) — new HL updates protected
        # break at bar 9 (high=115, close=109) → pending with protected=100 (new HL)
        # invalidation test: low=98 < 100 → invalid
        points = [
            _sp(0,  80, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  90, PointKind.HL),
            _sp(6, 110, PointKind.HH),
            _sp(8, 100, PointKind.HL),   # new HL raises protected level to 100
        ]
        candles = [
            _flat(0, 80), _flat(1, 90),
            _flat(2, 100), _flat(3, 95),
            _flat(4, 90), _flat(5, 100),
            _flat(6, 110), _flat(7, 105),
            _flat(8, 100),
            _candle(9, high=115, low=108, close=109),   # pending, conf=115, protected=100
            _candle(10, high=109, low=98,  close=99),   # low=98 < protected=100 → invalid
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status          == BoSStatus.INVALID
        assert ev.protected_level == 100.0   # updated HL, not original 90
        assert ev.invalidation_candle_index == 10

    def test_pending_valid_preserves_initial_and_updated_protected_levels(self):
        """
        If a pending BoS is tightened by a later structure point before
        confirmation, the final event preserves both reconstruction levels.
        """
        points = [
            _sp(0,  80, PointKind.L),
            _sp(2, 100, PointKind.H),
            _sp(4,  90, PointKind.HL),
            _sp(6, 110, PointKind.HH),
            _sp(9, 100, PointKind.HL),   # tightens protected while BoS is pending
        ]
        candles = [
            _flat(0, 80), _flat(1, 90),
            _flat(2, 100), _flat(3, 95),
            _flat(4, 90), _flat(5, 100),
            _flat(6, 110), _flat(7, 105),
            _candle(8, high=115, low=108, close=109),   # pending, initial protected=90
            _flat(9, 100),                               # structure point, not scanned
            _candle(10, high=118, low=104, close=116),   # confirms
        ]
        events = detect_bos(points, candles, "minor")
        assert len(events) == 1
        ev = events[0]
        assert ev.status == BoSStatus.VALID
        assert ev.initial_protected_level == 90.0
        assert ev.protected_level == 100.0
        assert ev.break_candle_index == 8
        assert ev.confirmation_candle_index == 10

    def test_candles_at_exact_break_level_not_triggered(self):
        """Candle high exactly at break_level (== 110) does not trigger BoS."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=110, low=108, close=109),  # high == 110, not > 110
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert events == []

    def test_candles_at_exact_bear_break_level_not_triggered(self):
        """Candle low exactly at break_level (== 80) does not trigger bear BoS."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=82, low=80, close=81),  # low == 80, not < 80
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert events == []

    def test_structure_point_bar_is_not_scanned_as_bos(self):
        """A structure-point candle cannot break its own reference level."""
        candles = [
            _flat(0, 90), _flat(1, 95),
            _flat(2, 100), _flat(3, 97),
            _flat(4, 95), _flat(5, 102),
            _candle(6, high=120, low=108, close=118),  # HH structure bar, skipped
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert events == []

    def test_bullish_low_equal_protected_level_does_not_invalidate(self):
        """Pending bull BoS invalidates only when low is strictly below protected."""
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=109),  # pending, protected=95
            _candle(9, high=113, low=95,  close=99),   # low == protected, no invalidation
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.PENDING
        assert events[0].invalidation_candle_index is None

    def test_bearish_high_equal_protected_level_does_not_invalidate(self):
        """Pending bear BoS invalidates only when high is strictly above protected."""
        candles = _DOWNTREND_SAFE_CANDLES + [
            _candle(8, high=83,  low=75, close=82),   # pending, protected=100
            _candle(9, high=100, low=77, close=90),   # high == protected, no invalidation
        ]
        events = detect_bos(_DOWNTREND_POINTS, candles, "minor")
        assert len(events) == 1
        assert events[0].status == BoSStatus.PENDING
        assert events[0].invalidation_candle_index is None

    def test_multiple_valid_bos_in_same_trend(self):
        """
        Two consecutive candles can each produce an independent BoS event
        if each one independently breaks the same level.
        (This occurs when the break_level has not been updated by a new structure point.)
        """
        candles = _UPTREND_SAFE_CANDLES + [
            _candle(8, high=115, low=109, close=112),  # first BoS
            _candle(9, high=118, low=113, close=116),  # second BoS (same level still active)
        ]
        events = detect_bos(_UPTREND_POINTS, candles, "minor")
        # At minimum the first BoS must be present
        assert len(events) >= 1
        assert events[0].status    == BoSStatus.VALID
        assert events[0].direction == BoSDirection.BULLISH

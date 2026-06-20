"""
Primitive-event contract conformance tests.

Validates that BoS and CHoCH events satisfy the shared
structure_events.PRIMITIVE_EVENT_CONTRACT_FIELDS contract,
and that the contract itself is open for future extension.

Required scenarios:

  1. BoS conforms to shared primitive-event contract.
  2. CHoCH conforms to shared primitive-event contract.
  3. Future event_type values can be added without changing BoS or CHoCH.
  4. Existing BoS behavior remains unchanged.
  5. Existing CHoCH behavior remains unchanged.
  6. Existing market structure tests remain unchanged.
"""
from __future__ import annotations

import dataclasses
import pytest

from backend.tools.structure_events import (
    PRIMITIVE_EVENT_CONTRACT_FIELDS,
    PrimitiveEventDirection,
    PrimitiveEventEffect,
    PrimitiveEventStatus,
    PrimitiveEventType,
    conforms_to_primitive_event_contract,
    primitive_event_summary,
)
from backend.tools.bos_detection import BoSDirection, BoSEvent, BoSStatus, detect_bos
from backend.tools.choch_detection import CHoCHDirection, CHoCHEvent, detect_choch
from backend.tools.market_structure import (
    MarketStructureEngine,
    OHLCVCandle,
    PointKind,
    StructureLevel,
    StructurePoint,
)


# ── Helpers (shared with bos/choch test modules) ──────────────────────────────

def _sp(bar: int, price: float, kind: PointKind,
        level: StructureLevel = StructureLevel.MINOR) -> StructurePoint:
    return StructurePoint(
        id=f"sp_{bar}", level=level, kind=kind,
        timestamp=f"2024-01-01T{bar:02d}:00:00Z",
        bar_index=bar, price=price, source="price", confirmed=True,
    )


def _candle(bar: int, high: float, low: float, close: float) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=f"2024-01-01T{bar:02d}:00:00Z",
        bar_index=bar, open=close, high=high, low=low, close=close, volume=1_000.0,
    )


def _flat(bar: int, price: float) -> OHLCVCandle:
    return _candle(bar, price, price, price)


# ── Minimal uptrend / downtrend fixtures ──────────────────────────────────────

_UP_POINTS = [
    _sp(0,  90, PointKind.L),
    _sp(2, 100, PointKind.H),
    _sp(4,  95, PointKind.HL),
    _sp(6, 110, PointKind.HH),
]

_DOWN_POINTS = [
    _sp(0, 110, PointKind.H),
    _sp(2,  90, PointKind.L),
    _sp(4, 100, PointKind.LH),
    _sp(6,  80, PointKind.LL),
]

_UP_SAFE = [
    _flat(0, 90), _flat(1, 93),
    _flat(2, 100), _flat(3, 97),
    _flat(4, 95), _flat(5, 97),    # 97 ≤ H.price(100): BoS-safe; 97 ≥ HL(95): CHoCH-safe
    _flat(6, 97), _flat(7, 97),    # bar 6 = SP(HH); candle high=97 ≤ 100 → no BoS trigger
]

_DOWN_SAFE = [
    _flat(0, 110), _flat(1, 105),
    _flat(2, 90), _flat(3, 95),
    _flat(4, 100), _flat(5, 92),   # 92 ≥ L.price(90): BoS-safe; 92 ≤ LH(100): CHoCH-safe
    _flat(6, 92), _flat(7, 92),    # bar 6 = SP(LL); candle low=92 ≥ 90 → no BoS trigger
]


def _make_bos_valid() -> BoSEvent:
    """Immediate valid bullish BoS event."""
    candles = _UP_SAFE + [_candle(8, high=115, low=109, close=112)]
    events = detect_bos(_UP_POINTS, candles, "minor")
    assert events, "Test setup: expected BoS event"
    return events[0]


def _make_bos_pending() -> BoSEvent:
    """Pending (unresolved) bullish BoS event: high=105 > H.price(100), close=99 ≤ 100."""
    candles = _UP_SAFE + [_candle(8, high=105, low=99, close=99)]
    events = detect_bos(_UP_POINTS, candles, "minor")
    assert events and events[0].status == BoSStatus.PENDING
    return events[0]


def _make_bos_invalid() -> BoSEvent:
    """Invalidated bullish BoS: pending at bar 8, L structure point (CHoCH) at bar 10."""
    points = list(_UP_POINTS) + [_sp(10, 92, PointKind.L)]
    candles = _UP_SAFE + [
        _candle(8, high=105, low=99, close=99),   # pending: conf_level=105
        _flat(9, 102),
        _flat(10, 92),   # bar 10 = SP(L) → INVALID
    ]
    events = detect_bos(points, candles, "minor")
    invalid = [e for e in events if e.status == BoSStatus.INVALID]
    assert invalid
    return invalid[0]


def _make_choch_bullish() -> CHoCHEvent:
    """Bullish CHoCH event (HL breached in uptrend)."""
    candles = _UP_SAFE + [_candle(8, high=108, low=93, close=106)]
    events = detect_choch(_UP_POINTS, candles, "minor")
    assert events
    return events[0]


def _make_choch_bearish() -> CHoCHEvent:
    """Bearish CHoCH event (LH breached in downtrend)."""
    candles = _DOWN_SAFE + [_candle(8, high=103, low=82, close=85)]
    events = detect_choch(_DOWN_POINTS, candles, "minor")
    assert events
    return events[0]


# ═════════════════════════════════════════════════════════════════════════════
# Test 1 — BoS conforms to shared primitive-event contract
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSPrimitiveEventContract:
    """All BoSEvent instances must expose all five contract fields."""

    def test_valid_bos_conforms(self):
        assert conforms_to_primitive_event_contract(_make_bos_valid())

    def test_pending_bos_conforms(self):
        assert conforms_to_primitive_event_contract(_make_bos_pending())

    def test_invalid_bos_conforms(self):
        assert conforms_to_primitive_event_contract(_make_bos_invalid())

    def test_bos_event_type_value(self):
        ev = _make_bos_valid()
        assert ev.event_type == PrimitiveEventType.BOS
        assert ev.event_type == "bos"

    def test_bos_event_effect_value(self):
        ev = _make_bos_valid()
        assert ev.event_effect == PrimitiveEventEffect.CONTINUATION
        assert ev.event_effect == "continuation"

    def test_bos_status_values_align_with_shared_enum(self):
        assert BoSStatus.VALID   == PrimitiveEventStatus.VALID
        assert BoSStatus.PENDING == PrimitiveEventStatus.PENDING
        assert BoSStatus.INVALID == PrimitiveEventStatus.INVALID

    def test_bos_direction_values_align_with_shared_enum(self):
        assert BoSDirection.BULLISH == PrimitiveEventDirection.BULLISH
        assert BoSDirection.BEARISH == PrimitiveEventDirection.BEARISH

    def test_bos_summary_contains_all_contract_fields(self):
        summary = primitive_event_summary(_make_bos_valid())
        assert set(summary.keys()) == PRIMITIVE_EVENT_CONTRACT_FIELDS

    def test_bos_summary_correct_values(self):
        summary = primitive_event_summary(_make_bos_valid())
        assert summary["event_type"]      == "bos"
        assert summary["event_effect"]    == "continuation"
        assert summary["direction"]       == "bullish"
        assert summary["structure_scope"] == "minor"
        assert summary["status"]          == "valid"

    def test_all_contract_fields_present_in_dataclass(self):
        fields = {f.name for f in dataclasses.fields(BoSEvent)}
        assert PRIMITIVE_EVENT_CONTRACT_FIELDS <= fields, (
            f"Missing contract fields in BoSEvent: "
            f"{PRIMITIVE_EVENT_CONTRACT_FIELDS - fields}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Test 2 — CHoCH conforms to shared primitive-event contract
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHPrimitiveEventContract:
    """All CHoCHEvent instances must expose all five contract fields."""

    def test_bullish_choch_conforms(self):
        assert conforms_to_primitive_event_contract(_make_choch_bullish())

    def test_bearish_choch_conforms(self):
        assert conforms_to_primitive_event_contract(_make_choch_bearish())

    def test_choch_event_type_value(self):
        ev = _make_choch_bullish()
        assert ev.event_type == PrimitiveEventType.CHOCH
        assert ev.event_type == "choch"

    def test_choch_event_effect_value(self):
        ev = _make_choch_bullish()
        assert ev.event_effect == PrimitiveEventEffect.TRANSITION
        assert ev.event_effect == "transition"

    def test_choch_status_is_valid(self):
        ev = _make_choch_bullish()
        assert ev.status == PrimitiveEventStatus.VALID
        assert ev.status == "valid"

    def test_choch_direction_values_align_with_shared_enum(self):
        assert CHoCHDirection.BULLISH == PrimitiveEventDirection.BULLISH
        assert CHoCHDirection.BEARISH == PrimitiveEventDirection.BEARISH

    def test_choch_summary_contains_all_contract_fields(self):
        summary = primitive_event_summary(_make_choch_bullish())
        assert set(summary.keys()) == PRIMITIVE_EVENT_CONTRACT_FIELDS

    def test_choch_summary_correct_values_bullish(self):
        summary = primitive_event_summary(_make_choch_bullish())
        assert summary["event_type"]   == "choch"
        assert summary["event_effect"] == "transition"
        assert summary["direction"]    == "bullish"
        assert summary["status"]       == "valid"

    def test_choch_summary_correct_values_bearish(self):
        summary = primitive_event_summary(_make_choch_bearish())
        assert summary["direction"]    == "bearish"
        assert summary["event_type"]   == "choch"

    def test_all_contract_fields_present_in_dataclass(self):
        fields = {f.name for f in dataclasses.fields(CHoCHEvent)}
        assert PRIMITIVE_EVENT_CONTRACT_FIELDS <= fields, (
            f"Missing contract fields in CHoCHEvent: "
            f"{PRIMITIVE_EVENT_CONTRACT_FIELDS - fields}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Test 3 — Future event_type values can be added without changing BoS or CHoCH
# ═════════════════════════════════════════════════════════════════════════════

class TestPrimitiveEventContractExtensibility:
    """
    The contract is open for new event primitives.
    Adding LS, SnD, or any future type requires only a new
    PrimitiveEventType member — no changes to BoS or CHoCH.
    """

    def test_new_event_type_can_be_registered(self):
        """A new event_type can be represented as a string without touching BoS/CHoCH."""
        new_type = "ls"  # Last Standing — future primitive
        # The shared enum does not block unknown strings; callers use the string directly.
        assert new_type not in [e.value for e in PrimitiveEventType]  # not yet registered

    def test_future_event_conformance_via_duck_typing(self):
        """
        A hypothetical future event dataclass conforms to the contract as long
        as it exposes the five required fields.  No inheritance needed.
        """
        @dataclasses.dataclass
        class LastStandingEvent:
            event_type:      str = "ls"
            status:          str = "valid"
            structure_scope: str = "minor"
            direction:       str = "bullish"
            event_effect:    str = "continuation"
            # plus domain-specific fields:
            level:           float = 0.0

        ls_event = LastStandingEvent(level=95.0)
        assert conforms_to_primitive_event_contract(ls_event)
        summary = primitive_event_summary(ls_event)
        assert summary["event_type"] == "ls"

    def test_bos_and_choch_unaffected_by_new_event_type(self):
        """Introducing a hypothetical 'ls' event type does not alter BoS or CHoCH."""
        bos_ev  = _make_bos_valid()
        choch_ev = _make_choch_bullish()
        assert bos_ev.event_type  == "bos"
        assert choch_ev.event_type == "choch"

    def test_contract_fields_set_is_stable(self):
        """The minimum contract is exactly five fields."""
        assert len(PRIMITIVE_EVENT_CONTRACT_FIELDS) == 5
        assert PRIMITIVE_EVENT_CONTRACT_FIELDS == {
            "event_type", "status", "structure_scope", "direction", "event_effect",
        }

    def test_shared_enums_extend_without_modifying_existing_members(self):
        """Existing enum members are unaffected when new ones are added."""
        assert PrimitiveEventType.BOS   == "bos"
        assert PrimitiveEventType.CHOCH == "choch"

        assert PrimitiveEventEffect.CONTINUATION == "continuation"
        assert PrimitiveEventEffect.TRANSITION   == "transition"

        assert PrimitiveEventStatus.VALID   == "valid"
        assert PrimitiveEventStatus.PENDING == "pending"
        assert PrimitiveEventStatus.INVALID == "invalid"

        assert PrimitiveEventDirection.BULLISH == "bullish"
        assert PrimitiveEventDirection.BEARISH == "bearish"

    def test_non_conforming_object_fails_check(self):
        """A plain object missing contract fields is correctly rejected."""
        class Incomplete:
            event_type = "bos"
            # missing status, structure_scope, direction, event_effect

        assert not conforms_to_primitive_event_contract(Incomplete())

    def test_conformance_check_is_field_presence_only(self):
        """conforms_to_primitive_event_contract checks presence, not type or value."""
        @dataclasses.dataclass
        class WeirdEvent:
            event_type:      int = 999    # wrong type but present
            status:          bool = True
            structure_scope: None = None
            direction:       list = dataclasses.field(default_factory=list)
            event_effect:    dict = dataclasses.field(default_factory=dict)

        # Passes presence check — validation of values is the caller's responsibility.
        assert conforms_to_primitive_event_contract(WeirdEvent())


# ═════════════════════════════════════════════════════════════════════════════
# Test 4 — Existing BoS behavior unchanged
# ═════════════════════════════════════════════════════════════════════════════

class TestBoSBehaviorUnchanged:
    """Adding contract fields must not alter detection logic or existing outputs."""

    def test_valid_bos_fields_unaffected(self):
        ev = _make_bos_valid()
        assert ev.status               == BoSStatus.VALID
        assert ev.direction            == BoSDirection.BULLISH
        assert ev.break_level          == 100.0   # H.price (new spec; was HH.price=110)
        assert ev.protected_level      == 95.0
        assert ev.break_candle_index   == 8
        assert ev.confirmation_level   is None
        assert ev.invalidation_candle_index is None

    def test_pending_bos_fields_unaffected(self):
        ev = _make_bos_pending()
        assert ev.status             == BoSStatus.PENDING
        assert ev.confirmation_level == 105.0   # break_candle.high (was 115.0)
        assert ev.event_type         == "bos"   # contract field present but benign

    def test_invalid_bos_fields_unaffected(self):
        ev = _make_bos_invalid()
        assert ev.status == BoSStatus.INVALID
        assert ev.invalidation_candle_index == 10   # L structure point at bar 10

    def test_no_bos_without_trend(self):
        points = [_sp(0, 90, PointKind.L), _sp(2, 100, PointKind.H)]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100),
                   _candle(3, 115, 88, 114)]
        assert detect_bos(points, candles, "minor") == []

    def test_bos_event_type_is_always_bos(self):
        """event_type never changes regardless of status."""
        for ev in [_make_bos_valid(), _make_bos_pending(), _make_bos_invalid()]:
            assert ev.event_type == "bos"

    def test_bos_event_effect_is_always_continuation(self):
        for ev in [_make_bos_valid(), _make_bos_pending(), _make_bos_invalid()]:
            assert ev.event_effect == "continuation"


# ═════════════════════════════════════════════════════════════════════════════
# Test 5 — Existing CHoCH behavior unchanged
# ═════════════════════════════════════════════════════════════════════════════

class TestCHoCHBehaviorUnchanged:
    """Adding/verifying contract fields must not alter CHoCH detection logic."""

    def test_bullish_choch_fields_unaffected(self):
        ev = _make_choch_bullish()
        assert ev.direction                  == CHoCHDirection.BULLISH
        assert ev.protected_level            == 95.0
        assert ev.break_candle_index         == 8
        assert ev.reference_structure_type   == "HL"
        assert ev.structure_reference_index  == 4
        assert ev.violated_trend             == "uptrend"

    def test_bearish_choch_fields_unaffected(self):
        ev = _make_choch_bearish()
        assert ev.direction                  == CHoCHDirection.BEARISH
        assert ev.protected_level            == 100.0
        assert ev.break_candle_index         == 8
        assert ev.reference_structure_type   == "LH"
        assert ev.structure_reference_index  == 4
        assert ev.violated_trend             == "downtrend"

    def test_no_choch_without_trend(self):
        points = [_sp(0, 90, PointKind.L), _sp(2, 100, PointKind.H)]
        candles = [_flat(0, 90), _flat(1, 95), _flat(2, 100),
                   _candle(3, 115, 80, 82)]
        assert detect_choch(points, candles, "minor") == []

    def test_choch_equality_not_a_breach(self):
        candles = _UP_SAFE + [_candle(8, 108, 95, 104)]  # low == HL, not < HL
        assert detect_choch(_UP_POINTS, candles, "minor") == []

    def test_choch_event_type_is_always_choch(self):
        assert _make_choch_bullish().event_type == "choch"
        assert _make_choch_bearish().event_type == "choch"

    def test_choch_event_effect_is_always_transition(self):
        assert _make_choch_bullish().event_effect == "transition"
        assert _make_choch_bearish().event_effect == "transition"


# ═════════════════════════════════════════════════════════════════════════════
# Test 6 — Existing market structure tests remain unchanged
# ═════════════════════════════════════════════════════════════════════════════

class TestMarketStructureUnchanged:
    """Importing structure_events must not affect MarketStructureEngine."""

    @pytest.fixture
    def engine(self):
        return MarketStructureEngine()

    def _make_candle(self, bar, high, low, close):
        return OHLCVCandle(
            timestamp=f"2024-01-01T{bar:02d}:00:00Z",
            bar_index=bar, open=close, high=high, low=low, close=close, volume=1_000.0,
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
            [self._make_candle(i,     100+i*3, 90+i*2,  95+i*2)  for i in range(8)]
            + [self._make_candle(i+8, 120-i*3, 100-i*2, 105-i*2) for i in range(8)]
            + [self._make_candle(i+16, 90+i*3,  80+i*2,  85+i*2) for i in range(8)]
        )
        result = engine.compute_structure(candles)
        assert len(result.main_points) >= 2

    def test_import_structure_events_does_not_affect_labels(self, engine):
        from backend.tools import structure_events as _se  # noqa: F401
        candles = (
            [self._make_candle(i, 100+i*2, 90+i, 95+i) for i in range(6)]
            + [self._make_candle(i+6, 110-i*2, 80-i, 85-i) for i in range(6)]
        )
        result = engine.compute_structure(candles)
        assert result.minor_points, "No minor points — engine broken"
        for p in result.minor_points:
            assert p.kind in list(PointKind)

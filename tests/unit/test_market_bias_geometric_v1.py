"""
Unit tests for market_bias_local_v1 (file: market_bias_geometric_v1.py).

Coverage (14 required cases):
  1.  fewer than 5 pivots                    → SIDEWAY / INSUFFICIENT_DATA
  2.  bullish continuation                   → BULLISH / CONTINUATION
  3.  bearish continuation                   → BEARISH / CONTINUATION
  4.  sideway consolidation (no reversal)    → SIDEWAY / CONSOLIDATION
  5.  sideway volatile (no reversal)         → SIDEWAY / VOLATILE
  6.  equality P0 == P2                      → SIDEWAY / CONSOLIDATION (strict_equality)
  7.  equality P1 == P3                      → SIDEWAY / CONSOLIDATION (strict_equality)
  8.  bullish-side reversal                  → SIDEWAY / REVERSAL (bearish_regime_resistance_break)
  9.  bearish-side reversal                  → SIDEWAY / REVERSAL (bullish_regime_support_break)
  10. reversal does not require breaking P4  → REVERSAL fires when P0>P2 only
  11. reversal precedence over consolidation → REVERSAL wins when both conditions met
  12. reversal precedence over volatile      → REVERSAL wins when both conditions met
  13. response shape / API mapping           → condition field, support/resistance keys
  14. main structure is source of truth      → all 5 pivots in pivots_used; last-5 extraction

Additional edge-case coverage:
  15. empty pivot list
  16. exactly 5 pivots (boundary)
  17. more than 5 pivots uses last 5
  18. boundaries for BULLISH / BEARISH
  19. boundaries for REVERSAL states
  20. current_close carried through unchanged
"""
import pytest

from backend.tools.market_bias_geometric_v1 import ENGINE_ID, MarketBiasResult, compute_market_bias

# ---------------------------------------------------------------------------
# Fixtures — verified against the bias model
# ---------------------------------------------------------------------------

# BULLISH: P4=100, P3=90, P2=95, P1=105, P0=98
# P0(98)>P2(95) ✓  P1(105)>P3(90) ✓
_BULL_CONT = [100.0, 90.0, 95.0, 105.0, 98.0]

# BEARISH: P4=110, P3=120, P2=115, P1=105, P0=112
# P0(112)<P2(115) ✓  P1(105)<P3(120) ✓
_BEAR_CONT = [110.0, 120.0, 115.0, 105.0, 112.0]

# CONSOLIDATION: P4=115, P3=80, P2=110, P1=95, P0=105
# P0(105)<P2(110) ✓  P1(95)>P3(80) ✓
# No reversal: P4(115)>P2(110) blocks bullish-side reversal (needs P4<P2)
#              P3(80)<P1(95) blocks bearish-side reversal's P3>P1 requirement (needs P3>P1)
_CONSOL = [115.0, 80.0, 110.0, 95.0, 105.0]

# VOLATILE: P4=90, P3=120, P2=100, P1=85, P0=110
# P0(110)>P2(100) ✓  P1(85)<P3(120) ✓
# No reversal: P4(90)<P2(100) blocks bearish-side reversal (needs P4>P2)
_VOLATILE = [90.0, 120.0, 100.0, 85.0, 110.0]

# REVERSAL bearish→bullish: P4=110, P3=105, P2=100, P1=95, P0=102
# P4(110)>P2(100) ✓  P3(105)>P1(95) ✓  P0(102)>P2(100) ✓
# Not BULLISH: P1(95) < P3(105)
_REV_BEAR_BULL = [110.0, 105.0, 100.0, 95.0, 102.0]

# REVERSAL bullish→bearish: P4=90, P3=95, P2=100, P1=105, P0=98
# P4(90)<P2(100) ✓  P3(95)<P1(105) ✓  P0(98)<P2(100) ✓
# Not BEARISH: P1(105) > P3(95)
_REV_BULL_BEAR = [90.0, 95.0, 100.0, 105.0, 98.0]


# ---------------------------------------------------------------------------
# 1. Insufficient data
# ---------------------------------------------------------------------------

class TestInsufficientData:
    def test_fewer_than_5_pivots(self):
        r = compute_market_bias([100.0, 110.0, 105.0, 112.0], 111.0)
        assert r.engine == ENGINE_ID
        assert r.bias == "SIDEWAY"
        assert r.condition == "INSUFFICIENT_DATA"
        assert r.reason == "insufficient_data"
        assert r.pivots_used == []
        assert r.boundaries == {"support": None, "resistance": None}

    def test_empty_pivot_list(self):
        r = compute_market_bias([], 100.0)
        assert r.bias == "SIDEWAY"
        assert r.condition == "INSUFFICIENT_DATA"
        assert r.pivots_used == []

    def test_exactly_4_pivots_is_insufficient(self):
        r = compute_market_bias([100.0, 110.0, 105.0, 112.0], 111.0)
        assert r.condition == "INSUFFICIENT_DATA"

    def test_current_close_carried_through_on_insufficient(self):
        r = compute_market_bias([100.0], 999.5)
        assert r.current_close == 999.5


# ---------------------------------------------------------------------------
# 2. Bullish continuation
# ---------------------------------------------------------------------------

class TestBullishContinuation:
    def test_bias_and_condition(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert r.bias == "BULLISH"
        assert r.condition == "CONTINUATION"
        assert r.reason == "bullish_continuation"

    def test_engine_id(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert r.engine == "market_bias_local_v1"

    def test_all_five_pivots_in_pivots_used(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert r.pivots_used == _BULL_CONT

    def test_boundaries_support_set_resistance_null(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert r.boundaries["resistance"] is None
        assert r.boundaries["support"] is not None


# ---------------------------------------------------------------------------
# 3. Bearish continuation
# ---------------------------------------------------------------------------

class TestBearishContinuation:
    def test_bias_and_condition(self):
        r = compute_market_bias(_BEAR_CONT, 113.0)
        assert r.bias == "BEARISH"
        assert r.condition == "CONTINUATION"
        assert r.reason == "bearish_continuation"

    def test_boundaries_resistance_set_support_null(self):
        r = compute_market_bias(_BEAR_CONT, 113.0)
        assert r.boundaries["support"] is None
        assert r.boundaries["resistance"] is not None

    def test_pivots_used(self):
        r = compute_market_bias(_BEAR_CONT, 113.0)
        assert r.pivots_used == _BEAR_CONT


# ---------------------------------------------------------------------------
# 4. Sideway consolidation (no reversal)
# ---------------------------------------------------------------------------

class TestSidewayConsolidation:
    def test_bias_condition_reason(self):
        r = compute_market_bias(_CONSOL, 100.0)
        assert r.bias == "SIDEWAY"
        assert r.condition == "CONSOLIDATION"
        assert r.reason == "contracting_sideway_structure"

    def test_boundaries_both_set(self):
        r = compute_market_bias(_CONSOL, 100.0)
        assert r.boundaries["support"] is not None
        assert r.boundaries["resistance"] is not None


# ---------------------------------------------------------------------------
# 5. Sideway volatile (no reversal)
# ---------------------------------------------------------------------------

class TestSidewayVolatile:
    def test_bias_condition_reason(self):
        r = compute_market_bias(_VOLATILE, 105.0)
        assert r.bias == "SIDEWAY"
        assert r.condition == "VOLATILE"
        assert r.reason == "expanding_sideway_structure"

    def test_boundaries_both_set(self):
        r = compute_market_bias(_VOLATILE, 105.0)
        assert r.boundaries["support"] is not None
        assert r.boundaries["resistance"] is not None


# ---------------------------------------------------------------------------
# 6. Equality P0 == P2
# ---------------------------------------------------------------------------

class TestEqualityP0EqualsP2:
    def test_strict_equality_sideway(self):
        # P4=100, P3=90, P2=110, P1=95, P0=110  (P0 == P2)
        r = compute_market_bias([100.0, 90.0, 110.0, 95.0, 110.0], 108.0)
        assert r.bias == "SIDEWAY"
        assert r.condition == "CONSOLIDATION"
        assert r.reason == "strict_equality_sideway_structure"

    def test_equality_p0_p2_with_p1_greater_than_p3(self):
        # P1(95) > P3(90) but P0==P2 → equality wins
        r = compute_market_bias([100.0, 90.0, 110.0, 95.0, 110.0], 108.0)
        assert r.reason == "strict_equality_sideway_structure"

    def test_equality_p0_p2_with_p1_less_than_p3(self):
        # P4=100, P3=120, P2=110, P1=80, P0=110  (P0 == P2, P1<P3)
        r = compute_market_bias([100.0, 120.0, 110.0, 80.0, 110.0], 105.0)
        assert r.reason == "strict_equality_sideway_structure"


# ---------------------------------------------------------------------------
# 7. Equality P1 == P3
# ---------------------------------------------------------------------------

class TestEqualityP1EqualsP3:
    def test_strict_equality_sideway(self):
        # P4=100, P3=90, P2=110, P1=90, P0=105  (P1 == P3)
        r = compute_market_bias([100.0, 90.0, 110.0, 90.0, 105.0], 100.0)
        assert r.bias == "SIDEWAY"
        assert r.condition == "CONSOLIDATION"
        assert r.reason == "strict_equality_sideway_structure"

    def test_equality_p1_p3_does_not_trigger_reversal(self):
        # Reversal needs P3 > P1 or P3 < P1 strictly — equality blocks it
        r = compute_market_bias([100.0, 90.0, 110.0, 90.0, 105.0], 100.0)
        assert r.condition != "REVERSAL"


# ---------------------------------------------------------------------------
# 8. Bullish-side reversal (bearish_regime_resistance_break)
# ---------------------------------------------------------------------------

class TestBullishReversal:
    def test_reversal_fires(self):
        r = compute_market_bias(_REV_BEAR_BULL, 101.0)
        assert r.bias == "SIDEWAY"
        assert r.condition == "REVERSAL"
        assert r.reason == "bearish_regime_resistance_break"

    def test_broken_resistance_becomes_support(self):
        # P2 = 100.0 is the broken resistance level
        r = compute_market_bias(_REV_BEAR_BULL, 101.0)
        assert r.boundaries["support"] == 100.0
        assert r.boundaries["resistance"] is None

    def test_pivots_used_all_five(self):
        r = compute_market_bias(_REV_BEAR_BULL, 101.0)
        assert r.pivots_used == _REV_BEAR_BULL


# ---------------------------------------------------------------------------
# 9. Bearish-side reversal (bullish_regime_support_break)
# ---------------------------------------------------------------------------

class TestBearishReversal:
    def test_reversal_fires(self):
        r = compute_market_bias(_REV_BULL_BEAR, 97.0)
        assert r.bias == "SIDEWAY"
        assert r.condition == "REVERSAL"
        assert r.reason == "bullish_regime_support_break"

    def test_broken_support_becomes_resistance(self):
        # P2 = 100.0 is the broken support level
        r = compute_market_bias(_REV_BULL_BEAR, 97.0)
        assert r.boundaries["resistance"] == 100.0
        assert r.boundaries["support"] is None

    def test_pivots_used_all_five(self):
        r = compute_market_bias(_REV_BULL_BEAR, 97.0)
        assert r.pivots_used == _REV_BULL_BEAR


# ---------------------------------------------------------------------------
# 10. Reversal does not require breaking P4
# ---------------------------------------------------------------------------

class TestReversalDoesNotRequireBreakingP4:
    def test_p0_above_p2_but_below_p4(self):
        # P4=120, P3=115, P2=110, P1=100, P0=112
        # P0(112) > P2(110) ✓ — reversal fires
        # P0(112) < P4(120)   — P4 was NOT broken, but reversal still fires
        pivots = [120.0, 115.0, 110.0, 100.0, 112.0]
        r = compute_market_bias(pivots, 111.0)
        assert r.condition == "REVERSAL"
        assert r.reason == "bearish_regime_resistance_break"

    def test_p0_below_p2_but_above_p4(self):
        # P4=80, P3=85, P2=100, P1=110, P0=95
        # P0(95) < P2(100) ✓ — reversal fires
        # P0(95) > P4(80)   — P4 support NOT broken, but reversal still fires
        pivots = [80.0, 85.0, 100.0, 110.0, 95.0]
        r = compute_market_bias(pivots, 94.0)
        assert r.condition == "REVERSAL"
        assert r.reason == "bullish_regime_support_break"


# ---------------------------------------------------------------------------
# 11. Reversal precedence over consolidation
# ---------------------------------------------------------------------------

class TestReversalPrecedenceOverConsolidation:
    def test_reversal_beats_consolidation_geometry(self):
        # CONSOLIDATION geometry: P0<P2 AND P1>P3
        # Reversal condition also met: P4<P2 AND P3<P1 AND P0<P2
        # P4=95, P3=90, P2=105, P1=100, P0=102
        # P0(102)<P2(105) ✓  P1(100)>P3(90) ✓  → consolidation geometry
        # P4(95)<P2(105) ✓  P3(90)<P1(100) ✓  P0(102)<P2(105) ✓  → reversal also met
        pivots = [95.0, 90.0, 105.0, 100.0, 102.0]
        r = compute_market_bias(pivots, 101.0)
        assert r.condition == "REVERSAL"
        assert r.reason == "bullish_regime_support_break"

    def test_consolidation_without_reversal_trigger(self):
        # Same geometry (P0<P2, P1>P3) but P4 > P2 blocks bullish-regime reversal
        r = compute_market_bias(_CONSOL, 100.0)
        assert r.condition == "CONSOLIDATION"


# ---------------------------------------------------------------------------
# 12. Reversal precedence over volatile
# ---------------------------------------------------------------------------

class TestReversalPrecedenceOverVolatile:
    def test_reversal_beats_volatile_geometry(self):
        # VOLATILE geometry: P0>P2 AND P1<P3
        # Reversal condition also met: P4>P2 AND P3>P1 AND P0>P2
        # P4=110, P3=108, P2=100, P1=85, P0=102
        # P0(102)>P2(100) ✓  P1(85)<P3(108) ✓  → volatile geometry
        # P4(110)>P2(100) ✓  P3(108)>P1(85) ✓  P0(102)>P2(100) ✓  → reversal also met
        pivots = [110.0, 108.0, 100.0, 85.0, 102.0]
        r = compute_market_bias(pivots, 101.0)
        assert r.condition == "REVERSAL"
        assert r.reason == "bearish_regime_resistance_break"

    def test_volatile_without_reversal_trigger(self):
        # Same geometry (P0>P2, P1<P3) but P4 < P2 blocks bearish-regime reversal
        r = compute_market_bias(_VOLATILE, 105.0)
        assert r.condition == "VOLATILE"


# ---------------------------------------------------------------------------
# 13. Response shape / API mapping
# ---------------------------------------------------------------------------

class TestResponseShape:
    def test_has_condition_field_not_base_state(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert hasattr(r, "condition")
        assert not hasattr(r, "base_state")

    def test_boundaries_uses_support_and_resistance_keys(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert "support" in r.boundaries
        assert "resistance" in r.boundaries
        assert "floor" not in r.boundaries
        assert "ceiling" not in r.boundaries

    def test_engine_field_is_market_bias_local_v1(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert r.engine == "market_bias_local_v1"
        assert r.engine == ENGINE_ID

    def test_bias_values_are_bullish_bearish_sideway(self):
        assert compute_market_bias(_BULL_CONT,  97.0).bias == "BULLISH"
        assert compute_market_bias(_BEAR_CONT, 113.0).bias == "BEARISH"
        assert compute_market_bias(_CONSOL,    100.0).bias == "SIDEWAY"

    def test_result_is_marketbiasresult_instance(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert isinstance(r, MarketBiasResult)


# ---------------------------------------------------------------------------
# 14. Main Structure pivots as source of truth
# ---------------------------------------------------------------------------

class TestMainStructureSourceOfTruth:
    def test_all_five_pivots_returned_in_pivots_used(self):
        pivots = [100.0, 90.0, 95.0, 105.0, 98.0]
        r = compute_market_bias(pivots, 97.0)
        assert r.pivots_used == pivots
        assert len(r.pivots_used) == 5

    def test_uses_last_five_when_more_pivots_provided(self):
        # Engine must select the 5 most recent confirmed pivots
        extra = [80.0, 85.0] + _BULL_CONT  # 7 pivots total
        r = compute_market_bias(extra, 97.0)
        assert r.pivots_used == _BULL_CONT  # last 5 only

    def test_engine_id_identifies_main_structure_version(self):
        # ENGINE_ID is the stable identifier for the service integration contract
        assert ENGINE_ID == "market_bias_local_v1"

    def test_current_close_is_not_used_for_bias_classification(self):
        # Same pivots, wildly different close values → same bias/condition
        r1 = compute_market_bias(_BULL_CONT, 0.01)
        r2 = compute_market_bias(_BULL_CONT, 999999.0)
        assert r1.bias == r2.bias
        assert r1.condition == r2.condition
        assert r1.reason == r2.reason


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestAdditionalEdgeCases:
    def test_exactly_5_pivots_processes_correctly(self):
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert r.condition != "INSUFFICIENT_DATA"

    def test_bullish_boundaries_support_is_min_of_p0_p1(self):
        # P4=100, P3=90, P2=95, P1=105, P0=98
        # min(p0=98, p1=105) = 98
        r = compute_market_bias(_BULL_CONT, 97.0)
        assert r.boundaries["support"] == 98.0

    def test_bearish_boundaries_resistance_is_max_of_p0_p1(self):
        # P4=110, P3=120, P2=115, P1=105, P0=112
        # max(p0=112, p1=105) = 112
        r = compute_market_bias(_BEAR_CONT, 113.0)
        assert r.boundaries["resistance"] == 112.0

    def test_reversal_bearish_regime_support_boundary_is_p2(self):
        # _REV_BEAR_BULL: P2=100.0
        r = compute_market_bias(_REV_BEAR_BULL, 101.0)
        assert r.boundaries["support"] == 100.0

    def test_reversal_bullish_regime_resistance_boundary_is_p2(self):
        # _REV_BULL_BEAR: P2=100.0
        r = compute_market_bias(_REV_BULL_BEAR, 97.0)
        assert r.boundaries["resistance"] == 100.0

    def test_current_close_is_preserved_in_result(self):
        r = compute_market_bias(_BULL_CONT, 97.5)
        assert r.current_close == 97.5

    def test_insufficient_data_boundaries_both_null(self):
        r = compute_market_bias([100.0, 110.0], 105.0)
        assert r.boundaries == {"support": None, "resistance": None}

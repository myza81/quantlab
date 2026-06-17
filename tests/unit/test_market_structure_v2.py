"""
Unit tests for MinorStructureV2Engine — minor_structure_v2 experimental engine.

Scenarios covered:
  1. Single inside bar (cluster of 1): no cluster pivot; breakout processed by V1
  2. Cluster of 3: no cluster pivot; breakout processed by V1 reversal
  3. Cluster of 4 in UP, same-direction HH breakout: L at cluster lowest
  4. Cluster of 4 in DOWN, same-direction LL breakout: H at cluster highest
  5. Cluster of 4 in UP, opposite LL breakout: no cluster pivot; V1 reversal creates H
  6. Cluster of 4 in DOWN, opposite HH breakout: no cluster pivot; V1 reversal creates L
  7. V1 regression: sequence with no inside bars produces identical structure
  8. Outside bar (OB) in cluster >= 4: treated as same direction
"""
import pytest

from backend.tools.market_structure import OHLCVCandle, PointKind
from backend.tools.market_structure_v2 import MinorStructureV2Engine


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
    return MinorStructureV2Engine().compute_structure(candles)


# ---------------------------------------------------------------------------
# 1. Single inside bar (cluster of 1) — no cluster pivot; breakout by V1
# ---------------------------------------------------------------------------

def test_single_inside_bar_no_pivot_same_direction():
    """
    UP trend. n1 strictly inside n0. Breakout is HH.
    No cluster pivot (cluster < 4); V1 continues UP.
    """
    candles = [
        make_candle(0, high=100, low=90),   # start
        make_candle(1, high=110, low=95),   # HH → direction UP
        make_candle(2, high=108, low=97),   # strictly inside bar 1 (cluster of 1)
        make_candle(3, high=115, low=100),  # HH breakout — same direction
        make_candle(4, high=105, low=88),   # LL → reverse DOWN; H emitted at bar 3
    ]
    result = compute(candles)
    minor_kinds = [p.kind for p in result.minor_points]
    # Should produce exactly one H (at bar 3 peak) when reversed by bar 4 LL
    assert PointKind.H in minor_kinds
    # No cluster L should appear (cluster was size 1)
    # After bar 4 LL: H emitted. No L emitted yet (no reversal back up).
    assert len(result.minor_points) == 1
    assert result.minor_points[0].kind == PointKind.H
    # H should be at bar 3's high (115)
    h = result.minor_points[0]
    assert h.price == 115.0
    assert h.bar_index == 3


def test_single_inside_bar_no_pivot_v1_reversal():
    """
    UP trend. Single IB. Opposite LL breakout → V1 reversal creates H (not cluster L).
    """
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=95),   # HH → UP
        make_candle(2, high=108, low=97),   # IB (cluster of 1)
        make_candle(3, high=107, low=92),   # LL breakout (strictly outside n0 via low)
        make_candle(4, high=112, low=100),  # HH → reverse to UP; L emitted
    ]
    result = compute(candles)
    # IB cluster size 1 < 4 → no cluster pivot
    # Bar 3 LL → V1 UP+LL reversal: H at last_high_candle (bar 1, high=110)
    # Bar 4 HH → V1 DOWN+HH reversal: L at bar 3 (low=92)
    minor_kinds = [p.kind for p in result.minor_points]
    assert len(result.minor_points) == 2
    h = result.minor_points[0]
    l = result.minor_points[1]
    assert h.kind == PointKind.H
    assert h.price == 110.0
    assert l.kind == PointKind.L
    assert l.price == 92.0


# ---------------------------------------------------------------------------
# 2. Cluster of 3: no cluster pivot; breakout processed by V1
# ---------------------------------------------------------------------------

def test_cluster_of_3_no_pivot():
    """Cluster of exactly 3 (< 4): no cluster pivot regardless of breakout direction."""
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=95),   # HH → UP; n0 candidate
        make_candle(2, high=108, low=97),   # IB1 (inside 110/95)
        make_candle(3, high=107, low=96),   # IB2
        make_candle(4, high=106, low=95.5), # IB3 — cluster size 3
        make_candle(5, high=115, low=100),  # HH breakout (same direction)
        make_candle(6, high=103, low=85),   # LL → H emitted at bar 5
    ]
    result = compute(candles)
    # Cluster size 3 < 4 → no cluster L
    # Bar 5 HH: V1 continues UP
    # Bar 6 LL: V1 reversal → H at bar 5 (high=115)
    assert len(result.minor_points) == 1
    h = result.minor_points[0]
    assert h.kind == PointKind.H
    assert h.price == 115.0
    assert h.bar_index == 5


# ---------------------------------------------------------------------------
# 3. Cluster of 4 in UP, same-direction HH breakout → L at cluster lowest
# ---------------------------------------------------------------------------

def test_cluster_4_up_same_direction_hh():
    """Cluster of 4 in UP trend; HH breakout → L at cluster lowest before V1 continues UP."""
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=95),   # HH → UP; n0 = bar 1
        make_candle(2, high=108, low=97),   # IB1 (low=97)
        make_candle(3, high=107, low=98),   # IB2 (low=98)
        make_candle(4, high=106, low=96),   # IB3 (low=96) ← cluster lowest
        make_candle(5, high=105, low=97),   # IB4 (low=97)
        make_candle(6, high=115, low=100),  # HH breakout — same direction
        make_candle(7, high=112, low=85),   # LL → H emitted at last_high_candle
    ]
    result = compute(candles)
    # Expected points:
    #   L at bar 4 (low=96) — cluster lowest in UP direction
    #   H at bar 6 (high=115) — V1 UP+LL reversal
    assert len(result.minor_points) == 2
    cluster_l = result.minor_points[0]
    reversal_h = result.minor_points[1]
    assert cluster_l.kind == PointKind.L
    assert cluster_l.price == 96.0
    assert cluster_l.bar_index == 4
    assert reversal_h.kind == PointKind.H
    assert reversal_h.price == 115.0
    assert reversal_h.bar_index == 6


# ---------------------------------------------------------------------------
# 4. Cluster of 4 in DOWN, same-direction LL breakout → H at cluster highest
# ---------------------------------------------------------------------------

def test_cluster_4_down_same_direction_ll():
    """Cluster of 4 in DOWN trend; LL breakout → H at cluster highest before V1 continues DOWN."""
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=95, low=80),    # LL → DOWN; n0 = bar 1
        make_candle(2, high=92, low=82),    # IB1 (high=92)
        make_candle(3, high=93, low=83),    # IB2 (high=93) ← cluster highest
        make_candle(4, high=91, low=81),    # IB3 (high=91)
        make_candle(5, high=90, low=82),    # IB4 (high=90)
        make_candle(6, high=88, low=70),    # LL breakout — same direction
        make_candle(7, high=100, low=75),   # HH → L emitted at last_low_candle
    ]
    result = compute(candles)
    # Expected points:
    #   H at bar 3 (high=93) — cluster highest in DOWN direction
    #   L at bar 6 (low=70) — V1 DOWN+HH reversal
    assert len(result.minor_points) == 2
    cluster_h = result.minor_points[0]
    reversal_l = result.minor_points[1]
    assert cluster_h.kind == PointKind.H
    assert cluster_h.price == 93.0
    assert cluster_h.bar_index == 3
    assert reversal_l.kind == PointKind.L
    assert reversal_l.price == 70.0
    assert reversal_l.bar_index == 6


# ---------------------------------------------------------------------------
# 5. Cluster of 4 in UP, opposite LL breakout → no cluster pivot; V1 reversal
# ---------------------------------------------------------------------------

def test_cluster_4_up_opposite_ll():
    """Cluster of 4 in UP; LL-only breakout (opposite) → no cluster pivot; V1 reversal creates H."""
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=95),   # HH → UP; last_high_candle = bar 1
        make_candle(2, high=108, low=97),   # IB1
        make_candle(3, high=107, low=98),   # IB2
        make_candle(4, high=106, low=96),   # IB3
        make_candle(5, high=105, low=97),   # IB4 — cluster of 4
        # LL-only breakout: low < last_cluster.low(97), high <= last_cluster.high(105)
        make_candle(6, high=104, low=91),   # LL vs last cluster (104 <= 105, 91 < 97) → opposite
        make_candle(7, high=112, low=100),  # HH → reversal to UP; L emitted at bar 6
    ]
    result = compute(candles)
    # No cluster pivot (opposite direction)
    # Bar 6 LL → V1 UP+LL: H at last_high_candle (bar 1, high=110)
    # Bar 7 HH → V1 DOWN+HH: L at bar 6 (low=91)
    assert len(result.minor_points) == 2
    h = result.minor_points[0]
    l = result.minor_points[1]
    assert h.kind == PointKind.H
    assert h.price == 110.0
    assert l.kind == PointKind.L
    assert l.price == 91.0


# ---------------------------------------------------------------------------
# 6. Cluster of 4 in DOWN, opposite HH breakout → no cluster pivot; V1 reversal
# ---------------------------------------------------------------------------

def test_cluster_4_down_opposite_hh():
    """Cluster of 4 in DOWN; HH-only breakout (opposite) → no cluster pivot; V1 reversal creates L."""
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=95, low=80),    # LL → DOWN; last_low_candle = bar 1
        make_candle(2, high=92, low=82),    # IB1
        make_candle(3, high=93, low=83),    # IB2
        make_candle(4, high=91, low=81),    # IB3
        make_candle(5, high=90, low=82),    # IB4 — cluster of 4
        # HH-only breakout: high > last_cluster.high(90), low >= last_cluster.low(82)
        make_candle(6, high=96, low=82.5),  # HH vs last cluster → opposite
        make_candle(7, high=88, low=70),    # LL → reversal to DOWN; H emitted at bar 6
    ]
    result = compute(candles)
    # No cluster pivot (opposite direction)
    # Bar 6 HH → V1 DOWN+HH: L at last_low_candle (bar 1, low=80)
    # Bar 7 LL → V1 UP+LL: H at bar 6 (high=96)
    assert len(result.minor_points) == 2
    l = result.minor_points[0]
    h = result.minor_points[1]
    assert l.kind == PointKind.L
    assert l.price == 80.0
    assert h.kind == PointKind.H
    assert h.price == 96.0


# ---------------------------------------------------------------------------
# 7. V1 regression: no inside bars → same pivots as a plain V1-style sequence
# ---------------------------------------------------------------------------

def test_no_inside_bars_same_structure_as_v1():
    """
    A sequence with no inside bars should produce the same structure via V2 as V1 would,
    since all other rules are unchanged.
    """
    from backend.tools.market_structure import MarketStructureEngine

    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=95),  # HH → UP
        make_candle(2, high=108, low=80),  # LL → H at bar 1, DOWN
        make_candle(3, high=120, low=82),  # HH → L at bar 2, UP
        make_candle(4, high=115, low=70),  # LL → H at bar 3, DOWN
    ]
    v1 = MarketStructureEngine().compute_structure(candles)
    v2 = compute(candles)

    assert len(v1.minor_points) == len(v2.minor_points)
    for p1, p2 in zip(v1.minor_points, v2.minor_points):
        assert p1.bar_index == p2.bar_index
        assert p1.price == p2.price


# ---------------------------------------------------------------------------
# 8. Outside bar in cluster >= 4: treated as same-direction
# ---------------------------------------------------------------------------

def test_cluster_4_up_ob_breakout_same_direction():
    """
    Cluster of 4 in UP; breakout candle is OB (HH AND LL vs last cluster candle).
    OB should be treated as same direction → cluster L created; V1 UP OB continues UP.
    """
    candles = [
        make_candle(0, high=100, low=90),
        make_candle(1, high=110, low=95),   # HH → UP; n0 = bar 1
        make_candle(2, high=108, low=97),   # IB1 (low=97)
        make_candle(3, high=107, low=96),   # IB2 (low=96) ← cluster lowest
        make_candle(4, high=106, low=97.5), # IB3
        make_candle(5, high=105, low=98),   # IB4
        # OB: high > last_cluster.high(105) AND low < last_cluster.low(98)
        make_candle(6, high=116, low=93),   # OB breakout
        make_candle(7, high=113, low=85),   # LL → H at last_high (bar 6 high=116)
    ]
    result = compute(candles)
    # OB → same direction → L at cluster lowest (bar 3, low=96)
    # Bar 7 LL → V1 reverse DOWN: H at bar 6 (high=116)
    assert len(result.minor_points) == 2
    cluster_l = result.minor_points[0]
    h = result.minor_points[1]
    assert cluster_l.kind == PointKind.L
    assert cluster_l.price == 96.0
    assert cluster_l.bar_index == 3
    assert h.kind == PointKind.H
    assert h.price == 116.0

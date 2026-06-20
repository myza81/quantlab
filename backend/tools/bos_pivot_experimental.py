"""
Experimental pivot-triplet BoS detector — Scenario 1: Bullish close break.

This is a STANDALONE EXPERIMENTAL MODULE. It shares no code with the
production bos_detection module and must not be imported from any
production pipeline.

Algorithm (bullish only)
------------------------
Scan structure pivots in bar order. Classify each pivot as HIGH or LOW
by its PointKind (no label discrimination — only price-based comparisons):

    HIGH pivots: H, HH, LH
    LOW  pivots: L, LL, HL

Build triplets (P1, P2, P3):
    P1  = LOW pivot
    P2  = next HIGH after P1, with P2.price > P1.price
    P3  = next LOW after P2, with P1.price < P3.price < P2.price

After P3 is confirmed, monitor subsequent candles (bar > P3.bar_index).
If candle.close > P2.price: emit ExperimentalBosEvent.

Reset rule: immediately after a Bullish BoS, new P1 = old P3. Search
restarts from HAVE_P1 state.

Prohibitions (per spec — do NOT add these):
    - No bearish detection
    - No CHoCH
    - No pending states
    - No wick breaks (close only, not high)
    - No protection logic
    - No trend state
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.tools.market_structure import OHLCVCandle, PointKind, StructurePoint

# Pivot classification
_HIGH_KINDS: frozenset[PointKind] = frozenset({PointKind.H, PointKind.HH, PointKind.LH})
_LOW_KINDS:  frozenset[PointKind] = frozenset({PointKind.L, PointKind.LL, PointKind.HL})

# Detector states
_IDLE     = 0   # no P1 yet
_HAVE_P1  = 1   # have P1, searching for P2
_HAVE_P2  = 2   # have P1 + P2, searching for P3
_WATCHING = 3   # have P1 + P2 + P3, scanning candles for break


@dataclass
class ExperimentalBosEvent:
    """
    One experimental bullish Break of Structure event.

    Records the three forming pivots, the break candle, and the broken level.
    """
    direction:             str    # always "bullish" in Scenario 1
    p1_bar_index:          int
    p1_price:              float
    p1_timestamp:          str
    p2_bar_index:          int
    p2_price:              float
    p2_timestamp:          str
    p3_bar_index:          int
    p3_price:              float
    p3_timestamp:          str
    break_candle_index:    int
    break_candle_timestamp: str
    broken_level:          float  # == p2_price


def detect_experimental_bos_bullish(
    structure_points: list[StructurePoint],
    candles: list[OHLCVCandle],
) -> list[ExperimentalBosEvent]:
    """
    Detect bullish BoS events using the pivot-triplet algorithm.

    Parameters
    ----------
    structure_points:
        Labeled structure pivots from the minor structure engine, in bar order.
    candles:
        All OHLCV candles in bar order (bar_index 0 … N-1).

    Returns
    -------
    List of ExperimentalBosEvent, in chronological order.
    """
    # Index structure points by bar_index for O(1) lookup during candle scan.
    sp_by_bar: dict[int, StructurePoint] = {sp.bar_index: sp for sp in structure_points}

    events: list[ExperimentalBosEvent] = []

    state: int = _IDLE
    p1: StructurePoint | None = None
    p2: StructurePoint | None = None
    p3: StructurePoint | None = None

    for candle in candles:
        # ── Process structure point on this bar first ────────────────────────
        sp = sp_by_bar.get(candle.bar_index)
        if sp is not None:
            is_high = sp.kind in _HIGH_KINDS
            is_low  = sp.kind in _LOW_KINDS

            if state == _IDLE:
                if is_low:
                    p1 = sp
                    state = _HAVE_P1

            elif state == _HAVE_P1:
                if is_high and sp.price > p1.price:  # type: ignore[union-attr]
                    p2 = sp
                    state = _HAVE_P2
                elif is_low:
                    p1 = sp  # update to new low, keep searching for P2

            elif state == _HAVE_P2:
                if is_low:
                    if p1.price < sp.price < p2.price:  # type: ignore[union-attr]
                        # Valid P3 found — switch to WATCHING
                        p3 = sp
                        state = _WATCHING
                    elif sp.price <= p1.price:  # type: ignore[union-attr]
                        # New lower low — restart with this as P1
                        p1 = sp
                        p2 = None
                        state = _HAVE_P1
                    # else sp.price >= p2.price: not a valid HL — ignore
                elif is_high and sp.price > p2.price:  # type: ignore[union-attr]
                    p2 = sp  # higher high — update watch level

            elif state == _WATCHING:
                if is_low:
                    if sp.price <= p1.price:  # type: ignore[union-attr]
                        # New lower low invalidates the triplet
                        p1 = sp
                        p2 = None
                        p3 = None
                        state = _HAVE_P1
                    elif p1.price < sp.price < p2.price:  # type: ignore[union-attr]
                        # Better HL — update P3, keep watching same level
                        p3 = sp
                    # else sp.price >= p2.price: above watch level — ignore
                elif is_high and sp.price > p2.price:  # type: ignore[union-attr]
                    p2 = sp  # higher P2 — update watch level

        # ── Check for break candle (close > P2.price, strictly after P3 bar) ─
        if state == _WATCHING and candle.bar_index > p3.bar_index:  # type: ignore[union-attr]
            if candle.close > p2.price:  # type: ignore[union-attr]
                events.append(ExperimentalBosEvent(
                    direction="bullish",
                    p1_bar_index=p1.bar_index,           # type: ignore[union-attr]
                    p1_price=p1.price,                   # type: ignore[union-attr]
                    p1_timestamp=p1.timestamp,            # type: ignore[union-attr]
                    p2_bar_index=p2.bar_index,           # type: ignore[union-attr]
                    p2_price=p2.price,                   # type: ignore[union-attr]
                    p2_timestamp=p2.timestamp,            # type: ignore[union-attr]
                    p3_bar_index=p3.bar_index,           # type: ignore[union-attr]
                    p3_price=p3.price,                   # type: ignore[union-attr]
                    p3_timestamp=p3.timestamp,            # type: ignore[union-attr]
                    break_candle_index=candle.bar_index,
                    break_candle_timestamp=candle.timestamp,
                    broken_level=p2.price,               # type: ignore[union-attr]
                ))
                # Reset: new P1 = old P3
                p1 = p3
                p2 = None
                p3 = None
                state = _HAVE_P1

    return events

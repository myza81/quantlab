"""
Change of Character (CHoCH) detection engine.

CHoCH is an immediate event primitive.  It indicates that the protective
structure of the current trend has been breached.  It carries no implication
about future direction, reversal, continuation, or market bias.

Bullish CHoCH (uptrend, L → H → HL → HH):
    Protective structure: the last confirmed HL.
    Trigger: candle.low < HL  (strict inequality — equality is not a breach).
    Fires immediately on the wick breach; close confirmation is NOT required.

Bearish CHoCH (downtrend, H → L → LH → LL):
    Protective structure: the last confirmed LH.
    Trigger: candle.high > LH  (strict inequality — equality is not a breach).
    Fires immediately on the wick breach; close confirmation is NOT required.

What CHoCH does NOT imply:
    - No market bias determination.
    - No trend reversal confirmation.
    - No continuation signal.
    - No sideways detection.

What CHoCH does NOT have:
    - No pending state.
    - No confirmation step.
    - No delayed validation.
    - No invalidation concept.

Relationship with BoS:
    When a pending BoS exists and the protected level is breached:
      - The BoS detector independently emits an INVALID BoS event.
      - The CHoCH detector independently emits a CHoCH event.
    Both detectors are called separately; neither is aware of the other's state.

Structural requirement:
    CHoCH can only fire when a trending structure is active.  A trend is
    considered active after the first HH (bullish) or LL (bearish) is seen
    in structure_points AND an HL (or LH) has been recorded to act as the
    protected level.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from backend.tools.market_structure import OHLCVCandle, PointKind, StructurePoint


# ── Public enums ──────────────────────────────────────────────────────────────

class CHoCHDirection(str, Enum):
    BULLISH = "bullish"   # CHoCH in uptrend context (HL was breached)
    BEARISH = "bearish"   # CHoCH in downtrend context (LH was breached)


# ── Output model ──────────────────────────────────────────────────────────────

@dataclass
class CHoCHEvent:
    """
    A single Change of Character event.

    All fields are set at emit time and never revised.

    direction:
        BULLISH when an uptrend's HL was breached (candle.low < HL).
        BEARISH when a downtrend's LH was breached (candle.high > LH).

    violated_trend:
        Explicit trend context that was violated. This removes ambiguity for
        future consumers that may otherwise read direction as a resulting bias.

    event_type / status / event_effect:
        Durable event-contract markers. CHoCH has no pending or invalid state;
        every emitted event is a valid transition primitive.

    structure_scope:
        "minor" or "main" — passed through from the detect_choch call.

    protected_level:
        The price of the HL (bull) or LH (bear) that was breached.

    break_candle_index / break_candle_timestamp:
        Identity of the candle whose wick crossed the protected level.

    structure_reference_index / structure_reference_timestamp:
        Identity of the HL or LH structure point that was the protected level.

    reference_structure_type:
        "HL" for bullish CHoCH; "LH" for bearish CHoCH.
    """
    direction:                    CHoCHDirection
    structure_scope:              str    # "minor" | "main"
    protected_level:              float
    break_candle_index:           int
    break_candle_timestamp:       str
    structure_reference_index:    int
    structure_reference_timestamp: str
    reference_structure_type:     str    # "HL" | "LH"
    violated_trend:              str    # "uptrend" | "downtrend"
    event_type:                  str = "choch"
    status:                      str = "valid"
    event_effect:                str = "transition"


# ── Internal state constants ──────────────────────────────────────────────────

_NO_TREND = "no_trend"
_BULL     = "bull"
_BEAR     = "bear"


# ── Detection function ────────────────────────────────────────────────────────

def detect_choch(
    structure_points: list[StructurePoint],
    candles: list[OHLCVCandle],
    scope: str,
) -> list[CHoCHEvent]:
    """
    Detect all CHoCH events visible in the given structure/candle data.

    Args:
        structure_points: Already-labeled structure points (minor OR main — not mixed).
                          Must be in chronological (bar_index) order.
        candles:          Full OHLCV candle array used to produce the structure.
                          Must be in chronological order; bar_index values must be
                          consistent with those in structure_points.
        scope:            "minor" or "main" — stored verbatim in every emitted event.

    Returns:
        List of CHoCHEvent in chronological order. May be empty.

    Algorithm
    ---------
    Walk every bar in chronological order.  Two steps execute per bar:

    Step 1 — CHoCH breach evaluation (candle OHLC is the sole trigger):
      BULL + active_protected set: if candle.low < active_protected → emit
          bullish CHoCH; reset state to NO_TREND.
      BEAR + active_protected set: if candle.high > active_protected → emit
          bearish CHoCH; reset state to NO_TREND.
      This step runs on every bar that has a candle, regardless of whether
      the bar also carries a structure point.

    Step 2 — Structure point context update (for future detection only):
      HL  → record as last_hl; advance active_protected if still in BULL state.
      LH  → record as last_lh; advance active_protected if still in BEAR state.
      HH  → enter BULL; set active_protected = last_hl.price (if available).
      LL  → enter BEAR; set active_protected = last_lh.price (if available).
      L   → reset to NO_TREND; clear active_protected and last_lh.
      H   → reset to NO_TREND; clear active_protected and last_hl.

    Design properties:
      - CHoCH is always triggered by raw candle OHLC, not by the structure
        label.  A bar carrying a LL / HH / HL / LH / L / H SP is no different
        from any other candle for breach-detection purposes.
      - A bar that is both a candle and a structure point (e.g. a LL bar in
        BULL context) evaluates breach first, then applies context updates for
        future detection.
      - HL / LH bars cannot self-trigger CHoCH: the following HH / LL
        establishes the active context; HL / LH bars are always processed
        before that context exists.
    """
    if not structure_points or not candles:
        return []

    candle_by_bar: dict[int, OHLCVCandle]    = {c.bar_index: c for c in candles}
    sp_by_bar:     dict[int, StructurePoint] = {sp.bar_index: sp for sp in structure_points}

    all_bars = sorted(set(candle_by_bar) | set(sp_by_bar))

    state:            str                      = _NO_TREND
    active_protected: Optional[float]          = None
    last_hl:          Optional[StructurePoint] = None
    last_lh:          Optional[StructurePoint] = None
    events:           list[CHoCHEvent]         = []

    for bar_idx in all_bars:
        sp     = sp_by_bar.get(bar_idx)
        candle = candle_by_bar.get(bar_idx)

        # ── Step 1: CHoCH breach evaluation ──────────────────────────────────
        # Raw candle OHLC is the sole trigger.  Runs before any SP context
        # update so that bars carrying a structure-point label are treated
        # identically to plain candle bars.
        if candle is not None:
            if state == _BULL and active_protected is not None:
                if candle.low < active_protected:
                    events.append(CHoCHEvent(
                        direction=CHoCHDirection.BULLISH,
                        structure_scope=scope,
                        protected_level=active_protected,
                        break_candle_index=candle.bar_index,
                        break_candle_timestamp=candle.timestamp,
                        structure_reference_index=last_hl.bar_index,       # type: ignore[union-attr]
                        structure_reference_timestamp=last_hl.timestamp,   # type: ignore[union-attr]
                        reference_structure_type="HL",
                        violated_trend="uptrend",
                    ))
                    state            = _NO_TREND
                    active_protected = None

            elif state == _BEAR and active_protected is not None:
                if candle.high > active_protected:
                    events.append(CHoCHEvent(
                        direction=CHoCHDirection.BEARISH,
                        structure_scope=scope,
                        protected_level=active_protected,
                        break_candle_index=candle.bar_index,
                        break_candle_timestamp=candle.timestamp,
                        structure_reference_index=last_lh.bar_index,       # type: ignore[union-attr]
                        structure_reference_timestamp=last_lh.timestamp,   # type: ignore[union-attr]
                        reference_structure_type="LH",
                        violated_trend="downtrend",
                    ))
                    state            = _NO_TREND
                    active_protected = None

        # ── Step 2: Structure point context update ────────────────────────────
        # Establishes, advances, or resets trend context for future detection.
        # Never emits CHoCH directly.
        if sp is not None:
            kind = sp.kind

            if kind == PointKind.HL:
                last_hl = sp
                if state == _BULL:
                    active_protected = sp.price

            elif kind == PointKind.LH:
                last_lh = sp
                if state == _BEAR:
                    active_protected = sp.price

            elif kind == PointKind.HH:
                active_protected = last_hl.price if last_hl is not None else None
                state = _BULL

            elif kind == PointKind.LL:
                active_protected = last_lh.price if last_lh is not None else None
                state = _BEAR

            elif kind == PointKind.L:
                state            = _NO_TREND
                active_protected = None
                last_lh          = None

            elif kind == PointKind.H:
                state            = _NO_TREND
                active_protected = None
                last_hl          = None

    return events

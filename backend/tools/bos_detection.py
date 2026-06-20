"""
Break of Structure (BoS) detection engine.

Detects BoS events from already-labeled structure points and raw OHLCV candles.
Works independently of the structure labeling engine — consumes its output.

BoS is a continuation event only.

Correct prerequisites
---------------------
Bullish BoS  : L → H → HL sequence in structure points.
               Watch level = H.price (the swing high between L and HL).
Bearish BoS  : H → L → LH sequence in structure points.
               Watch level = L.price (the swing low between H and LH).

Three variations
----------------
Variation 1 — Immediate Valid:
    break candle's HIGH (bull) or LOW (bear) clears the watch level
    AND close also clears the level on the same candle.

Variation 2 — Pending:
    break candle's extreme clears the level but close does not.
    confirmation_level = break candle extreme (high for bull, low for bear).
    Valid if a later candle's extreme clears confirmation_level.
    Pending BoS survives additional HL/LH structure point formation.

Variation 3 — Invalid (outcome of Variation 2):
    A CHoCH structure point appears before confirmation:
      Bull pending → invalidated by a PointKind.L structure point (CHoCH).
      Bear pending → invalidated by a PointKind.H structure point (CHoCH).

One-level-one-BoS
-----------------
A structural level (H for bull, L for bear) generates at most one BoS event.
After any valid BoS fires (immediate or confirmed), the bull/bear tracker
resets completely. A new full L→H→HL or H→L→LH cycle is required before
the next BoS can be set up.

All events are immutable once emitted; the detector never revises past events.
A valid BoS that has already been emitted cannot be invalidated by a later CHoCH.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from backend.tools.market_structure import OHLCVCandle, PointKind, StructurePoint


# ── Public enums ──────────────────────────────────────────────────────────────

class BoSStatus(str, Enum):
    VALID   = "valid"
    PENDING = "pending"
    INVALID = "invalid"


class BoSDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


# ── Output model ──────────────────────────────────────────────────────────────

@dataclass
class BoSEvent:
    """
    A single Break of Structure event.

    Fields present in all statuses:
        status, direction, structure_scope, break_level, protected_level,
        break_candle_index, break_candle_timestamp.

    break_level: the H.price (bull) or L.price (bear) that was broken.
    protected_level: the HL.price (bull) or LH.price (bear) that completed
                     the prerequisite sequence; fixed at setup entry.

    Additional fields for Variation 2 (pending path):
        confirmation_level, confirmation_candle_index,
        confirmation_candle_timestamp (set when VALID via pending).

    Additional field for Variation 3 (invalid):
        invalidation_candle_index, invalidation_candle_timestamp
        (the bar of the CHoCH structure point that invalidated the pending).

    initial_protected_level: reserved for schema compatibility; always None
        in the corrected engine (no protected-level tightening occurs).

    Primitive-event contract fields (shared with CHoCH and future primitives):
        event_type   = "bos"
        event_effect = "continuation"
    """
    status:                        BoSStatus
    direction:                     BoSDirection
    structure_scope:               str
    break_level:                   float
    protected_level:               float
    break_candle_index:            int
    break_candle_timestamp:        str
    initial_protected_level:       Optional[float] = None
    confirmation_level:            Optional[float] = None
    confirmation_candle_index:     Optional[int]   = None
    confirmation_candle_timestamp: Optional[str]   = None
    invalidation_candle_index:     Optional[int]   = None
    invalidation_candle_timestamp: Optional[str]   = None
    event_type:                    str = "bos"
    event_effect:                  str = "continuation"


# ── Phase constants ───────────────────────────────────────────────────────────

_NO_SETUP  = "no_setup"
_SEEN_L    = "seen_l"
_SEEN_H    = "seen_h"
_WATCHING  = "watching"
_PENDING   = "pending"


# ── Detection function ────────────────────────────────────────────────────────

def detect_bos(
    structure_points: list[StructurePoint],
    candles: list[OHLCVCandle],
    scope: str,
) -> list[BoSEvent]:
    """
    Detect all BoS events visible in the given structure/candle data.

    Args:
        structure_points: Already-labeled structure points (minor OR main — not mixed).
                          Must be in chronological (bar_index) order.
        candles:          Full OHLCV candle array used to produce the structure.
                          Must be in chronological order; bar_index values must be
                          consistent with those in structure_points.
        scope:            "minor" or "main" — stored verbatim in every emitted event.

    Returns:
        List of BoSEvent in chronological order. May be empty.

    Algorithm
    ---------
    Two independent trackers (bull and bear) scan every bar in order.

    Structure-point bars update tracker state first.  L, H, HL, LH then skip the
    candle scan (they are state-transition points, not break candidates).  HH and
    LL perform sequence-ownership invalidation then fall through to the candle scan:

      Bull tracker:
        L  → invalidate pending bull (CHoCH); restart bull cycle. skip scan.
        H  → advance bull (seen_l→seen_h or update H); restart bear. skip scan.
        HL → (if bull in seen_h) activate watching at H.price. skip scan.
        HH → no effect on bull; fall through → eligible break candle for bull.
        LL → sequence break: if bull is in any active phase, emit INVALID (if
             pending), clear all bull state → no_setup. fall through → eligible
             break candle for bear.

      Bear tracker:
        H  → invalidate pending bear (CHoCH); restart bear cycle. skip scan.
        L  → advance bear (seen_h→seen_l or update L); restart bull. skip scan.
        LH → (if bear in seen_l) activate watching at L.price. skip scan.
        LL → no effect on bear; fall through → eligible break candle for bear.
        HH → sequence break: if bear is in any active phase, emit INVALID (if
             pending), clear all bear state → no_setup. fall through → eligible
             break candle for bull.

    Sequence ownership: a BoS setup belongs entirely to one alternating sequence
    (H→L→LH for bear; L→H→HL for bull).  HH breaks the bearish alternating
    sequence; LL breaks the bullish alternating sequence.  The tracker resets
    completely — no pivot substitution, no partial state survives.

    Every bar (structure-point or otherwise) is then scanned if candle data exists:
      bull watching : high > break_level → Var 1 or Var 2 depending on close.
      bull pending  : high > conf_level  → Valid (confirmed). Full reset follows.
      bear watching : low  < break_level → Var 1 or Var 2 depending on close.
      bear pending  : low  < conf_level  → Valid (confirmed). Full reset follows.
    """
    if not structure_points or not candles:
        return []

    candle_by_bar: dict[int, OHLCVCandle]    = {c.bar_index: c for c in candles}
    sp_by_bar:     dict[int, StructurePoint] = {sp.bar_index: sp for sp in structure_points}
    all_bars = sorted(set(candle_by_bar) | set(sp_by_bar))

    # ── Bull tracker state ────────────────────────────────────────────────────
    # Sequence: L → H → HL → watch H.price
    bull_phase:   str                         = _NO_SETUP
    bull_last_l:  Optional[StructurePoint]    = None
    bull_last_h:  Optional[StructurePoint]    = None   # H = resistance (break level)
    bull_last_hl: Optional[StructurePoint]    = None   # HL = protected level
    bull_level:   Optional[float]             = None   # H.price being watched
    bull_pending: Optional[dict]              = None

    # ── Bear tracker state ────────────────────────────────────────────────────
    # Sequence: H → L → LH → watch L.price
    bear_phase:   str                         = _NO_SETUP
    bear_last_h:  Optional[StructurePoint]    = None
    bear_last_l:  Optional[StructurePoint]    = None   # L = support (break level)
    bear_last_lh: Optional[StructurePoint]    = None   # LH = protected level
    bear_level:   Optional[float]             = None   # L.price being watched
    bear_pending: Optional[dict]              = None

    events: list[BoSEvent] = []

    for bar_idx in all_bars:
        sp     = sp_by_bar.get(bar_idx)
        candle = candle_by_bar.get(bar_idx)

        # ── Process structure-point bars ──────────────────────────────────────
        if sp is not None:
            kind = sp.kind

            # ── L: CHoCH for bull; step-2 for bear ──────────────────────────
            if kind == PointKind.L:
                # Invalidate any pending bull BoS — this L is a CHoCH.
                if bull_pending is not None:
                    events.append(BoSEvent(
                        status=BoSStatus.INVALID,
                        direction=BoSDirection.BULLISH,
                        structure_scope=scope,
                        break_level=bull_pending["break_level"],
                        protected_level=bull_pending["protected_level"],
                        break_candle_index=bull_pending["break_candle"].bar_index,
                        break_candle_timestamp=bull_pending["break_candle"].timestamp,
                        confirmation_level=bull_pending["confirmation_level"],
                        invalidation_candle_index=sp.bar_index,
                        invalidation_candle_timestamp=sp.timestamp,
                    ))

                # Restart the bull cycle from this L.
                bull_phase   = _SEEN_L
                bull_last_l  = sp
                bull_last_h  = None
                bull_last_hl = None
                bull_level   = None
                bull_pending = None

                # Advance bear tracker: L is step 2 of H→L→LH.
                if bear_phase == _SEEN_H:
                    bear_last_l = sp
                    bear_phase  = _SEEN_L
                elif bear_phase == _SEEN_L:
                    bear_last_l = sp   # update to newer / lower L

                continue   # L cannot be a BoS break candle

            # ── H: CHoCH for bear; step-2 for bull ──────────────────────────
            elif kind == PointKind.H:
                # Invalidate any pending bear BoS — this H is a CHoCH.
                if bear_pending is not None:
                    events.append(BoSEvent(
                        status=BoSStatus.INVALID,
                        direction=BoSDirection.BEARISH,
                        structure_scope=scope,
                        break_level=bear_pending["break_level"],
                        protected_level=bear_pending["protected_level"],
                        break_candle_index=bear_pending["break_candle"].bar_index,
                        break_candle_timestamp=bear_pending["break_candle"].timestamp,
                        confirmation_level=bear_pending["confirmation_level"],
                        invalidation_candle_index=sp.bar_index,
                        invalidation_candle_timestamp=sp.timestamp,
                    ))

                # Restart the bear cycle from this H.
                bear_phase   = _SEEN_H
                bear_last_h  = sp
                bear_last_l  = None
                bear_last_lh = None
                bear_level   = None
                bear_pending = None

                # Advance bull tracker: H is step 2 of L→H→HL.
                if bull_phase == _SEEN_L:
                    bull_last_h = sp
                    bull_phase  = _SEEN_H
                elif bull_phase == _SEEN_H:
                    bull_last_h = sp   # update to newer H (new resistance)

                continue   # H cannot be a BoS break candle

            # ── HL: completes the bull setup ─────────────────────────────────
            elif kind == PointKind.HL:
                if bull_phase == _SEEN_H and bull_last_h is not None:
                    bull_last_hl = sp
                    bull_level   = bull_last_h.price
                    bull_phase   = _WATCHING
                # HL during watching or pending: the first setup owns the level.
                continue   # HL cannot be a BoS break candle

            # ── LH: completes the bear setup ─────────────────────────────────
            elif kind == PointKind.LH:
                if bear_phase == _SEEN_L and bear_last_l is not None:
                    bear_last_lh = sp
                    bear_level   = bear_last_l.price
                    bear_phase   = _WATCHING
                # LH during watching or pending: the first setup owns the level.
                continue   # LH cannot be a BoS break candle

            # ── HH: sequence break for bear; eligible bull break candle ─────
            elif kind == PointKind.HH:
                if bear_phase != _NO_SETUP:
                    if bear_pending is not None:
                        events.append(BoSEvent(
                            status=BoSStatus.INVALID,
                            direction=BoSDirection.BEARISH,
                            structure_scope=scope,
                            break_level=bear_pending["break_level"],
                            protected_level=bear_pending["protected_level"],
                            break_candle_index=bear_pending["break_candle"].bar_index,
                            break_candle_timestamp=bear_pending["break_candle"].timestamp,
                            confirmation_level=bear_pending["confirmation_level"],
                            invalidation_candle_index=sp.bar_index,
                            invalidation_candle_timestamp=sp.timestamp,
                        ))
                    bear_phase   = _NO_SETUP
                    bear_last_h  = None
                    bear_last_l  = None
                    bear_last_lh = None
                    bear_level   = None
                    bear_pending = None
                # No continue — HH falls through to candle scan.

            # ── LL: sequence break for bull; eligible bear break candle ─────
            elif kind == PointKind.LL:
                if bull_phase != _NO_SETUP:
                    if bull_pending is not None:
                        events.append(BoSEvent(
                            status=BoSStatus.INVALID,
                            direction=BoSDirection.BULLISH,
                            structure_scope=scope,
                            break_level=bull_pending["break_level"],
                            protected_level=bull_pending["protected_level"],
                            break_candle_index=bull_pending["break_candle"].bar_index,
                            break_candle_timestamp=bull_pending["break_candle"].timestamp,
                            confirmation_level=bull_pending["confirmation_level"],
                            invalidation_candle_index=sp.bar_index,
                            invalidation_candle_timestamp=sp.timestamp,
                        ))
                    bull_phase   = _NO_SETUP
                    bull_last_l  = None
                    bull_last_h  = None
                    bull_last_hl = None
                    bull_level   = None
                    bull_pending = None
                # No continue — LL falls through to candle scan.

        if candle is None:
            continue

        # ── Scan bull ─────────────────────────────────────────────────────────
        if bull_phase == _WATCHING and bull_level is not None and bull_last_hl is not None:
            if candle.high > bull_level:
                if candle.close > bull_level:
                    events.append(BoSEvent(
                        status=BoSStatus.VALID,
                        direction=BoSDirection.BULLISH,
                        structure_scope=scope,
                        break_level=bull_level,
                        protected_level=bull_last_hl.price,
                        break_candle_index=candle.bar_index,
                        break_candle_timestamp=candle.timestamp,
                    ))
                    bull_phase = _NO_SETUP
                    bull_last_l = bull_last_h = bull_last_hl = None
                    bull_level  = None
                else:
                    bull_pending = {
                        "break_level":        bull_level,
                        "protected_level":    bull_last_hl.price,
                        "break_candle":       candle,
                        "confirmation_level": candle.high,
                    }
                    bull_phase = _PENDING

        elif bull_phase == _PENDING and bull_pending is not None:
            if candle.high > bull_pending["confirmation_level"]:
                events.append(BoSEvent(
                    status=BoSStatus.VALID,
                    direction=BoSDirection.BULLISH,
                    structure_scope=scope,
                    break_level=bull_pending["break_level"],
                    protected_level=bull_pending["protected_level"],
                    break_candle_index=bull_pending["break_candle"].bar_index,
                    break_candle_timestamp=bull_pending["break_candle"].timestamp,
                    confirmation_level=bull_pending["confirmation_level"],
                    confirmation_candle_index=candle.bar_index,
                    confirmation_candle_timestamp=candle.timestamp,
                ))
                bull_phase  = _NO_SETUP
                bull_last_l = bull_last_h = bull_last_hl = None
                bull_level  = None
                bull_pending = None

        # ── Scan bear ─────────────────────────────────────────────────────────
        if bear_phase == _WATCHING and bear_level is not None and bear_last_lh is not None:
            if candle.low < bear_level:
                if candle.close < bear_level:
                    events.append(BoSEvent(
                        status=BoSStatus.VALID,
                        direction=BoSDirection.BEARISH,
                        structure_scope=scope,
                        break_level=bear_level,
                        protected_level=bear_last_lh.price,
                        break_candle_index=candle.bar_index,
                        break_candle_timestamp=candle.timestamp,
                    ))
                    bear_phase  = _NO_SETUP
                    bear_last_h = bear_last_l = bear_last_lh = None
                    bear_level  = None
                else:
                    bear_pending = {
                        "break_level":        bear_level,
                        "protected_level":    bear_last_lh.price,
                        "break_candle":       candle,
                        "confirmation_level": candle.low,
                    }
                    bear_phase = _PENDING

        elif bear_phase == _PENDING and bear_pending is not None:
            if candle.low < bear_pending["confirmation_level"]:
                events.append(BoSEvent(
                    status=BoSStatus.VALID,
                    direction=BoSDirection.BEARISH,
                    structure_scope=scope,
                    break_level=bear_pending["break_level"],
                    protected_level=bear_pending["protected_level"],
                    break_candle_index=bear_pending["break_candle"].bar_index,
                    break_candle_timestamp=bear_pending["break_candle"].timestamp,
                    confirmation_level=bear_pending["confirmation_level"],
                    confirmation_candle_index=candle.bar_index,
                    confirmation_candle_timestamp=candle.timestamp,
                ))
                bear_phase  = _NO_SETUP
                bear_last_h = bear_last_l = bear_last_lh = None
                bear_level  = None
                bear_pending = None

    # ── End-of-scan: emit any unresolved pending ──────────────────────────────
    if bull_pending is not None and bull_phase == _PENDING:
        events.append(BoSEvent(
            status=BoSStatus.PENDING,
            direction=BoSDirection.BULLISH,
            structure_scope=scope,
            break_level=bull_pending["break_level"],
            protected_level=bull_pending["protected_level"],
            break_candle_index=bull_pending["break_candle"].bar_index,
            break_candle_timestamp=bull_pending["break_candle"].timestamp,
            confirmation_level=bull_pending["confirmation_level"],
        ))

    if bear_pending is not None and bear_phase == _PENDING:
        events.append(BoSEvent(
            status=BoSStatus.PENDING,
            direction=BoSDirection.BEARISH,
            structure_scope=scope,
            break_level=bear_pending["break_level"],
            protected_level=bear_pending["protected_level"],
            break_candle_index=bear_pending["break_candle"].bar_index,
            break_candle_timestamp=bear_pending["break_candle"].timestamp,
            confirmation_level=bear_pending["confirmation_level"],
        ))

    return events

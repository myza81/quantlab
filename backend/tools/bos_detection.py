"""
Break of Structure (BoS) detection engine.

Detects BoS events from already-labeled structure points and raw OHLCV candles.
Works independently of the structure labeling engine — consumes its output.

BoS is a continuation event only:
  Bullish BoS: candle breaks above the last confirmed H or HH in an uptrend.
  Bearish BoS: candle breaks below the last confirmed L or LL in a downtrend.

Required structure context:
  Uptrend  : at least one HL + HH sequence visible in structure_points.
  Downtrend: at least one LH + LL sequence visible in structure_points.

Three variations
  Variation 1 — Immediate Valid:
      break candle's HIGH (bull) or LOW (bear) clears the level
      AND close also clears the level on the same candle.

  Variation 2 — Pending:
      break candle's extreme clears the level but close does not.
      confirmation_level = break candle extreme (high for bull, low for bear).
      Valid if a later candle's extreme clears confirmation_level.
      Invalid if protected_level (last HL for bull, last LH for bear) is
      broken by a later candle before confirmation arrives.

  Variation 3 — Invalid (outcome of Variation 2):
      Protected level breaks before confirmation_level is reached.
      CHoCH labeling is out of scope — only the invalidation is recorded.

All events are immutable once emitted; the detector never revises past events.
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

    Additional fields for Variation 2 (pending path):
        initial_protected_level, confirmation_level, confirmation_candle_index,
        confirmation_candle_timestamp (set when VALID via pending).

    Additional field for Variation 3 (invalid):
        invalidation_candle_index, invalidation_candle_timestamp.

    protected_level is the active protected level used for the final outcome.
    initial_protected_level preserves the protected level captured on the
    original pending break candle, before any later structure point tightens it.

    Primitive-event contract fields (shared with CHoCH and future primitives):
        event_type   = "bos"
        event_effect = "continuation"
    """
    status:                        BoSStatus
    direction:                     BoSDirection
    structure_scope:               str          # "minor" | "main"
    break_level:                   float        # H/HH (bull) or L/LL (bear) breached
    protected_level:               float        # last HL (bull) or LH (bear)
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


# ── Internal state constants ──────────────────────────────────────────────────

_NO_TREND     = "no_trend"
_BULL         = "bull"
_BEAR         = "bear"
_PENDING_BULL = "pending_bull"
_PENDING_BEAR = "pending_bear"


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
    Walk every bar in chronological order.

    Structure-point bars update the detector's trend state:
      HL   → record as last_hl; update active protected level in bull watch.
      LH   → record as last_lh; update active protected level in bear watch.
      HH   → enter/continue bull watch; set break_level = HH.price.
      LL   → enter/continue bear watch; set break_level = LL.price.
      L    → bullish reversal detected; reset to no_trend.
      H    → bearish reversal detected; reset to no_trend.

    After updating state, structure-point bars are skipped for BoS scanning.
    The structure point IS the reference level — it cannot be its own break.

    Non-structure-point candles are scanned for BoS conditions:
      bull  : high > break_level → Var 1 or Var 2 depending on close.
      bear  : low  < break_level → Var 1 or Var 2 depending on close.
      pending_bull: high > conf_level → Valid; low  < protected → Invalid.
      pending_bear: low  < conf_level → Valid; high > protected → Invalid.
    """
    if not structure_points or not candles:
        return []

    candle_by_bar: dict[int, OHLCVCandle]    = {c.bar_index: c for c in candles}
    sp_by_bar:     dict[int, StructurePoint] = {sp.bar_index: sp for sp in structure_points}

    all_bars = sorted(set(candle_by_bar) | set(sp_by_bar))

    state:                str                   = _NO_TREND
    active_break_level:   Optional[float]       = None
    active_protected:     Optional[float]       = None
    last_hl:              Optional[StructurePoint] = None
    last_lh:              Optional[StructurePoint] = None
    pending:              Optional[dict]        = None
    events:               list[BoSEvent]        = []

    for bar_idx in all_bars:
        sp     = sp_by_bar.get(bar_idx)
        candle = candle_by_bar.get(bar_idx)

        # ── Process structure-point bars ──────────────────────────────────
        if sp is not None:
            kind = sp.kind

            if kind == PointKind.HL:
                last_hl = sp
                # Tighten protected level while watching bull or pending bull.
                if state in (_BULL, _PENDING_BULL):
                    active_protected = sp.price
                    if pending is not None:
                        pending["protected_level"] = sp.price

            elif kind == PointKind.LH:
                last_lh = sp
                # Tighten protected level while watching bear or pending bear.
                if state in (_BEAR, _PENDING_BEAR):
                    active_protected = sp.price
                    if pending is not None:
                        pending["protected_level"] = sp.price

            elif kind == PointKind.HH:
                active_break_level = sp.price
                active_protected   = last_hl.price if last_hl is not None else None
                state   = _BULL
                pending = None

            elif kind == PointKind.LL:
                active_break_level = sp.price
                active_protected   = last_lh.price if last_lh is not None else None
                state   = _BEAR
                pending = None

            elif kind == PointKind.L:
                # Bullish reversal point (price broke below HL).
                state              = _NO_TREND
                active_break_level = None
                active_protected   = None
                pending            = None
                last_lh            = None   # reset for the next bear sequence

            elif kind == PointKind.H:
                # Bearish reversal point (price broke above LH).
                state              = _NO_TREND
                active_break_level = None
                active_protected   = None
                pending            = None
                last_hl            = None   # reset for the next bull sequence

            # Structure-point bars are never scanned for BoS.
            continue

        # ── Scan non-structure-point candles ──────────────────────────────
        if candle is None:
            continue

        # ── Bullish trend watch ───────────────────────────────────────────
        if (
            state == _BULL
            and active_break_level is not None
            and active_protected is not None
        ):
            if candle.high > active_break_level:
                if candle.close > active_break_level:
                    events.append(BoSEvent(
                        status=BoSStatus.VALID,
                        direction=BoSDirection.BULLISH,
                        structure_scope=scope,
                        break_level=active_break_level,
                        protected_level=active_protected,
                        break_candle_index=candle.bar_index,
                        break_candle_timestamp=candle.timestamp,
                    ))
                else:
                    pending = {
                        "break_level":        active_break_level,
                        "protected_level":    active_protected,
                        "initial_protected_level": active_protected,
                        "break_candle":       candle,
                        "confirmation_level": candle.high,
                    }
                    state = _PENDING_BULL

        # ── Pending bullish confirmation ──────────────────────────────────
        elif state == _PENDING_BULL and pending is not None:
            if candle.high > pending["confirmation_level"]:
                events.append(BoSEvent(
                    status=BoSStatus.VALID,
                    direction=BoSDirection.BULLISH,
                    structure_scope=scope,
                    break_level=pending["break_level"],
                    protected_level=pending["protected_level"],
                    break_candle_index=pending["break_candle"].bar_index,
                    break_candle_timestamp=pending["break_candle"].timestamp,
                    initial_protected_level=pending["initial_protected_level"],
                    confirmation_level=pending["confirmation_level"],
                    confirmation_candle_index=candle.bar_index,
                    confirmation_candle_timestamp=candle.timestamp,
                ))
                pending = None
                state   = _BULL
            elif candle.low < pending["protected_level"]:
                events.append(BoSEvent(
                    status=BoSStatus.INVALID,
                    direction=BoSDirection.BULLISH,
                    structure_scope=scope,
                    break_level=pending["break_level"],
                    protected_level=pending["protected_level"],
                    break_candle_index=pending["break_candle"].bar_index,
                    break_candle_timestamp=pending["break_candle"].timestamp,
                    initial_protected_level=pending["initial_protected_level"],
                    confirmation_level=pending["confirmation_level"],
                    invalidation_candle_index=candle.bar_index,
                    invalidation_candle_timestamp=candle.timestamp,
                ))
                pending = None
                state   = _NO_TREND

        # ── Bearish trend watch ───────────────────────────────────────────
        elif (
            state == _BEAR
            and active_break_level is not None
            and active_protected is not None
        ):
            if candle.low < active_break_level:
                if candle.close < active_break_level:
                    events.append(BoSEvent(
                        status=BoSStatus.VALID,
                        direction=BoSDirection.BEARISH,
                        structure_scope=scope,
                        break_level=active_break_level,
                        protected_level=active_protected,
                        break_candle_index=candle.bar_index,
                        break_candle_timestamp=candle.timestamp,
                    ))
                else:
                    pending = {
                        "break_level":        active_break_level,
                        "protected_level":    active_protected,
                        "initial_protected_level": active_protected,
                        "break_candle":       candle,
                        "confirmation_level": candle.low,
                    }
                    state = _PENDING_BEAR

        # ── Pending bearish confirmation ──────────────────────────────────
        elif state == _PENDING_BEAR and pending is not None:
            if candle.low < pending["confirmation_level"]:
                events.append(BoSEvent(
                    status=BoSStatus.VALID,
                    direction=BoSDirection.BEARISH,
                    structure_scope=scope,
                    break_level=pending["break_level"],
                    protected_level=pending["protected_level"],
                    break_candle_index=pending["break_candle"].bar_index,
                    break_candle_timestamp=pending["break_candle"].timestamp,
                    initial_protected_level=pending["initial_protected_level"],
                    confirmation_level=pending["confirmation_level"],
                    confirmation_candle_index=candle.bar_index,
                    confirmation_candle_timestamp=candle.timestamp,
                ))
                pending = None
                state   = _BEAR
            elif candle.high > pending["protected_level"]:
                events.append(BoSEvent(
                    status=BoSStatus.INVALID,
                    direction=BoSDirection.BEARISH,
                    structure_scope=scope,
                    break_level=pending["break_level"],
                    protected_level=pending["protected_level"],
                    break_candle_index=pending["break_candle"].bar_index,
                    break_candle_timestamp=pending["break_candle"].timestamp,
                    initial_protected_level=pending["initial_protected_level"],
                    confirmation_level=pending["confirmation_level"],
                    invalidation_candle_index=candle.bar_index,
                    invalidation_candle_timestamp=candle.timestamp,
                ))
                pending = None
                state   = _NO_TREND

    # If the scan ends while a BoS is still pending (never confirmed or invalidated),
    # emit the unresolved state so callers can see what is in progress.
    if pending is not None and state in (_PENDING_BULL, _PENDING_BEAR):
        events.append(BoSEvent(
            status=BoSStatus.PENDING,
            direction=BoSDirection.BULLISH if state == _PENDING_BULL else BoSDirection.BEARISH,
            structure_scope=scope,
            break_level=pending["break_level"],
            protected_level=pending["protected_level"],
            break_candle_index=pending["break_candle"].bar_index,
            break_candle_timestamp=pending["break_candle"].timestamp,
            initial_protected_level=pending["initial_protected_level"],
            confirmation_level=pending["confirmation_level"],
        ))

    return events

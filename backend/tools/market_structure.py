"""
Market Structure Engine — deterministic structure analysis for chart verification.

This module provides deterministic market structure calculation for visual verification
on the chart. It is NOT a trading strategy and does NOT generate signals.

Purpose:
- Calculate minor and main structure lines from OHLCV data
- Expose debug metadata for manual verification
- Serve as a foundation for future strategy features

The structure calculation is split into two phases:
1. Minor Structure: Built candle-by-candle from OHLCV data
2. Main Structure: Built from minor structure with confirmation rules

Neither phase performs any trading logic, signal generation, or strategy decisions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CandleRelationship(str, Enum):
    """Candle relationship classification."""
    HIGHER_HIGH = "higher_high"
    LOWER_LOW = "lower_low"
    INSIDE_BAR = "inside_bar"
    OUTSIDE_BAR = "outside_bar"
    AMBIGUOUS_STARTUP = "ambiguous_startup"


class Direction(str, Enum):
    """Structural direction."""
    UP = "up"
    DOWN = "down"


class StructureLevel(str, Enum):
    """Structure level classification."""
    MINOR = "minor"
    MAIN = "main"


class PointKind(str, Enum):
    """Point kind classification — L, H, LL, LH, HH, HL."""
    L = "L"
    H = "H"
    LL = "LL"
    LH = "LH"
    HH = "HH"
    HL = "HL"
    UNKNOWN = "unknown"


@dataclass
class OHLCVCandle:
    """Normalized OHLCV candle."""
    timestamp: str
    bar_index: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class StructurePoint:
    """
    A point in the structure (H, L, HH, HL, LH, LL).

    Attributes:
        id: Unique identifier
        level: minor or main
        kind: L, H, HH, HL, LH, LL, or unknown
        timestamp: ISO 8601 UTC
        bar_index: Index in the candle array
        price: Price level of the point
        source: "price", "minor", or "main" depending on origin
        confirmed: Whether this point is confirmed (or still candidate)
        metadata: Debug/verification metadata
    """
    id: str
    level: StructureLevel
    kind: PointKind
    timestamp: str
    bar_index: int
    price: float
    source: str  # "price", "minor", "main"
    confirmed: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class StructureLeg:
    """
    A leg in the structure — a directional segment between two points.

    Attributes:
        id: Unique identifier
        level: minor or main
        from_point_id: Starting point ID
        to_point_id: Ending point ID
        direction: up or down
        start_bar_index: Index of starting candle
        end_bar_index: Index of ending candle
        start_price: Price at start
        end_price: Price at end
    """
    id: str
    level: StructureLevel
    from_point_id: str
    to_point_id: str
    direction: Direction
    start_bar_index: int
    end_bar_index: int
    start_price: float
    end_price: float


@dataclass
class StructureDebugEvent:
    """
    Debug event for verification and troubleshooting.

    Records the decision-making process at each candle.

    Attributes:
        bar_index: Candle index
        timestamp: ISO 8601 UTC
        candle_relationship: Relationship type (higher_high, lower_low, etc.)
        previous_direction: Direction before this candle (if any)
        new_direction: Direction after this candle (if any)
        action: continue_up, continue_down, reverse_up, reverse_down, wait_for_direction
        reason: Human-readable explanation
        affected_level: minor, main, or both
        candidate_high: Potential main high (if applicable)
        candidate_low: Potential main low (if applicable)
        confirmed_point_id: Point ID if confirmed (if applicable)
    """
    bar_index: int
    timestamp: str
    candle_relationship: str
    previous_direction: Optional[Direction] = None
    new_direction: Optional[Direction] = None
    action: str = ""
    reason: str = ""
    affected_level: str = "minor"
    candidate_high: Optional[float] = None
    candidate_low: Optional[float] = None
    confirmed_point_id: Optional[str] = None


@dataclass
class StructureResult:
    """
    Result of market structure calculation.

    Attributes:
        minor_points: List of minor structure points
        minor_legs: List of minor structure legs
        main_points: List of main structure points
        main_legs: List of main structure legs
        debug_events: Debug events (one per candle or per structure event)
    """
    minor_points: list[StructurePoint] = field(default_factory=list)
    minor_legs: list[StructureLeg] = field(default_factory=list)
    main_points: list[StructurePoint] = field(default_factory=list)
    main_legs: list[StructureLeg] = field(default_factory=list)
    debug_events: list[StructureDebugEvent] = field(default_factory=list)


class MarketStructureEngine:
    """
    Deterministic market structure calculation engine.

    Computes minor and main structure from OHLCV candles.
    All logic is deterministic and exposes debug metadata.
    No trading signals or strategy logic.
    """

    def __init__(self):
        self._point_counter = 0
        self._leg_counter = 0

    def compute_structure(self, candles: list[OHLCVCandle]) -> StructureResult:
        """
        Compute minor and main structure from candles.

        Args:
            candles: List of OHLCV candles in chronological order

        Returns:
            StructureResult containing minor/main points, legs, and debug events
        """
        result = StructureResult()

        if len(candles) < 2:
            return result

        # Phase 1: Compute minor structure (raw turning points)
        minor_points, _, debug_events = self._compute_minor_structure(candles)
        result.debug_events = debug_events

        # Phase 1.5: Refine minor pivot coordinates to container extremes.
        # Scans all candles between consecutive same-direction turning points to
        # find the true lowest low (for L between two Hs where second H > first)
        # or the true highest high (for H between two Ls where second L < first).
        if minor_points:
            self._refine_minor_pivots(minor_points, candles)

        # Build minor legs from the (potentially refined) point coordinates.
        minor_legs = [
            self._create_structure_leg(StructureLevel.MINOR, minor_points[j], minor_points[j + 1])
            for j in range(len(minor_points) - 1)
        ]
        result.minor_points = minor_points
        result.minor_legs = minor_legs

        # Phase 2: Compute main structure from refined minor points.
        # Minor points still carry raw H/L at this stage — _compute_main_structure
        # relies on plain H/L for its container candidate queries.
        if minor_points:
            main_points, main_legs = self._compute_main_structure(minor_points)
            result.main_points = main_points
            result.main_legs = main_legs

        # Phase 2.5: Relabel minor_points with comparative labels (MS-7A).
        # Must run AFTER Phase 2 so the main engine still receives raw H/L input.
        if minor_points:
            self._label_structure_points(minor_points)

        return result

    def _compute_minor_structure(
        self, candles: list[OHLCVCandle]
    ) -> tuple[list[StructurePoint], list[StructureLeg], list[StructureDebugEvent]]:
        """
        Compute minor structure from candles.

        Minor structure is built candle-by-candle using:
        - Higher High → UP
        - Lower Low → DOWN
        - Inside Bar → continuation or reversal based on close
        - Outside Bar → continuation

        Returns:
            (minor_points, minor_legs, debug_events)
        """
        points: list[StructurePoint] = []
        debug_events: list[StructureDebugEvent] = []
        direction: Optional[Direction] = None
        last_high: Optional[float] = None
        last_low: Optional[float] = None
        last_close: Optional[float] = None
        last_high_candle: Optional[OHLCVCandle] = None
        last_low_candle: Optional[OHLCVCandle] = None

        for i in range(1, len(candles)):
            prev = candles[i - 1]
            curr = candles[i]

            # Classify candle relationship
            is_higher_high = curr.high > prev.high
            is_lower_low = curr.low < prev.low
            is_inside_bar = curr.high <= prev.high and curr.low >= prev.low
            is_outside_bar = curr.high > prev.high and curr.low < prev.low

            if is_inside_bar:
                rel = CandleRelationship.INSIDE_BAR
            elif is_outside_bar:
                rel = CandleRelationship.OUTSIDE_BAR
            elif is_higher_high:
                rel = CandleRelationship.HIGHER_HIGH
            elif is_lower_low:
                rel = CandleRelationship.LOWER_LOW
            else:
                rel = CandleRelationship.AMBIGUOUS_STARTUP

            # Update structure based on relationship and current direction
            if direction is None:
                # Startup phase: waiting for initial direction
                if rel == CandleRelationship.HIGHER_HIGH:
                    direction = Direction.UP
                    last_high = curr.high
                    last_low = curr.low
                    last_close = curr.close
                    last_high_candle = curr
                    last_low_candle = curr
                    debug_events.append(
                        StructureDebugEvent(
                            bar_index=i,
                            timestamp=curr.timestamp,
                            candle_relationship=rel.value,
                            new_direction=direction,
                            action="establish_up",
                            reason="Higher high establishes UP direction at startup",
                            affected_level="minor",
                        )
                    )
                elif rel == CandleRelationship.LOWER_LOW:
                    direction = Direction.DOWN
                    last_high = curr.high
                    last_low = curr.low
                    last_close = curr.close
                    last_high_candle = curr
                    last_low_candle = curr
                    debug_events.append(
                        StructureDebugEvent(
                            bar_index=i,
                            timestamp=curr.timestamp,
                            candle_relationship=rel.value,
                            new_direction=direction,
                            action="establish_down",
                            reason="Lower low establishes DOWN direction at startup",
                            affected_level="minor",
                        )
                    )
                else:
                    # Inside/outside/ambiguous at startup — wait for direction
                    last_high = curr.high
                    last_low = curr.low
                    last_close = curr.close
                    last_high_candle = curr
                    last_low_candle = curr
                    debug_events.append(
                        StructureDebugEvent(
                            bar_index=i,
                            timestamp=curr.timestamp,
                            candle_relationship=rel.value,
                            action="wait_for_direction",
                            reason="Ambiguous startup pattern; waiting for clear direction",
                            affected_level="minor",
                        )
                    )
            else:
                # Direction established: handle continuations and reversals
                if direction == Direction.UP:
                    if rel == CandleRelationship.HIGHER_HIGH:
                        # Continue UP
                        last_high = curr.high
                        last_high_candle = curr
                        last_low = curr.low
                        last_close = curr.close
                        debug_events.append(
                            StructureDebugEvent(
                                bar_index=i,
                                timestamp=curr.timestamp,
                                candle_relationship=rel.value,
                                previous_direction=direction,
                                new_direction=direction,
                                action="continue_up",
                                reason=f"Higher high ({curr.high:.2f} > {prev.high:.2f})",
                                affected_level="minor",
                            )
                        )
                    elif rel == CandleRelationship.LOWER_LOW:
                        # Reverse to DOWN
                        new_direction = Direction.DOWN
                        # Record the high point before reversal — use the candle that
                        # established the true highest high of the completed UP leg.
                        point = self._create_structure_point(
                            last_high_candle or prev, StructureLevel.MINOR, PointKind.H, "price"
                        )
                        points.append(point)
                        direction = new_direction
                        last_high = curr.high
                        last_low = curr.low
                        last_close = curr.close
                        last_high_candle = curr
                        last_low_candle = curr
                        debug_events.append(
                            StructureDebugEvent(
                                bar_index=i,
                                timestamp=curr.timestamp,
                                candle_relationship=rel.value,
                                previous_direction=Direction.UP,
                                new_direction=new_direction,
                                action="reverse_down",
                                reason=f"Lower low ({curr.low:.2f} < {prev.low:.2f}) reverses structure",
                                affected_level="minor",
                                confirmed_point_id=point.id,
                            )
                        )
                    elif is_inside_bar:
                        # Inside bar: check close to decide continuation or reversal
                        if curr.close >= prev.close:
                            # Continue UP
                            last_high = max(last_high or curr.high, curr.high)
                            last_close = curr.close
                            debug_events.append(
                                StructureDebugEvent(
                                    bar_index=i,
                                    timestamp=curr.timestamp,
                                    candle_relationship=rel.value,
                                    previous_direction=direction,
                                    new_direction=direction,
                                    action="continue_up",
                                    reason=f"Inside bar with close >= prev close ({curr.close:.2f} >= {prev.close:.2f})",
                                    affected_level="minor",
                                )
                            )
                        else:
                            # Reverse to DOWN — use the candle that established
                            # the true highest high of the completed UP leg.
                            new_direction = Direction.DOWN
                            point = self._create_structure_point(
                                last_high_candle or prev, StructureLevel.MINOR, PointKind.H, "price"
                            )
                            points.append(point)
                            direction = new_direction
                            last_high = curr.high
                            last_low = curr.low
                            last_close = curr.close
                            last_high_candle = curr
                            last_low_candle = curr
                            debug_events.append(
                                StructureDebugEvent(
                                    bar_index=i,
                                    timestamp=curr.timestamp,
                                    candle_relationship=rel.value,
                                    previous_direction=Direction.UP,
                                    new_direction=new_direction,
                                    action="reverse_down",
                                    reason=f"Inside bar with close < prev close ({curr.close:.2f} < {prev.close:.2f})",
                                    affected_level="minor",
                                    confirmed_point_id=point.id,
                                )
                            )
                    else:
                        # Outside bar: continue UP
                        if curr.high > (last_high or 0):
                            last_high_candle = curr
                        last_high = max(last_high or curr.high, curr.high)
                        last_close = curr.close
                        debug_events.append(
                            StructureDebugEvent(
                                bar_index=i,
                                timestamp=curr.timestamp,
                                candle_relationship=rel.value,
                                previous_direction=direction,
                                new_direction=direction,
                                action="continue_up",
                                reason="Outside bar continues UP direction",
                                affected_level="minor",
                            )
                        )

                else:  # direction == Direction.DOWN
                    if rel == CandleRelationship.LOWER_LOW:
                        # Continue DOWN
                        last_low = curr.low
                        last_low_candle = curr
                        last_high = curr.high
                        last_close = curr.close
                        debug_events.append(
                            StructureDebugEvent(
                                bar_index=i,
                                timestamp=curr.timestamp,
                                candle_relationship=rel.value,
                                previous_direction=direction,
                                new_direction=direction,
                                action="continue_down",
                                reason=f"Lower low ({curr.low:.2f} < {prev.low:.2f})",
                                affected_level="minor",
                            )
                        )
                    elif rel == CandleRelationship.HIGHER_HIGH:
                        # Reverse to UP — use the candle that established the true
                        # lowest low of the completed DOWN leg.
                        new_direction = Direction.UP
                        point = self._create_structure_point(
                            last_low_candle or prev, StructureLevel.MINOR, PointKind.L, "price"
                        )
                        points.append(point)
                        direction = new_direction
                        last_high = curr.high
                        last_low = curr.low
                        last_close = curr.close
                        last_high_candle = curr
                        last_low_candle = curr
                        debug_events.append(
                            StructureDebugEvent(
                                bar_index=i,
                                timestamp=curr.timestamp,
                                candle_relationship=rel.value,
                                previous_direction=Direction.DOWN,
                                new_direction=new_direction,
                                action="reverse_up",
                                reason=f"Higher high ({curr.high:.2f} > {prev.high:.2f}) reverses structure",
                                affected_level="minor",
                                confirmed_point_id=point.id,
                            )
                        )
                    elif is_inside_bar:
                        # Inside bar: check close to decide continuation or reversal
                        if curr.close <= prev.close:
                            # Continue DOWN
                            last_low = min(last_low or curr.low, curr.low)
                            last_close = curr.close
                            debug_events.append(
                                StructureDebugEvent(
                                    bar_index=i,
                                    timestamp=curr.timestamp,
                                    candle_relationship=rel.value,
                                    previous_direction=direction,
                                    new_direction=direction,
                                    action="continue_down",
                                    reason=f"Inside bar with close <= prev close ({curr.close:.2f} <= {prev.close:.2f})",
                                    affected_level="minor",
                                )
                            )
                        else:
                            # Reverse to UP — use the candle that established the
                            # true lowest low of the completed DOWN leg.
                            new_direction = Direction.UP
                            point = self._create_structure_point(
                                last_low_candle or prev, StructureLevel.MINOR, PointKind.L, "price"
                            )
                            points.append(point)
                            direction = new_direction
                            last_high = curr.high
                            last_low = curr.low
                            last_close = curr.close
                            last_high_candle = curr
                            last_low_candle = curr
                            debug_events.append(
                                StructureDebugEvent(
                                    bar_index=i,
                                    timestamp=curr.timestamp,
                                    candle_relationship=rel.value,
                                    previous_direction=Direction.DOWN,
                                    new_direction=new_direction,
                                    action="reverse_up",
                                    reason=f"Inside bar with close > prev close ({curr.close:.2f} > {prev.close:.2f})",
                                    affected_level="minor",
                                    confirmed_point_id=point.id,
                                )
                            )
                    else:
                        # Outside bar: continue DOWN
                        if curr.low < (last_low or float('inf')):
                            last_low_candle = curr
                        last_low = min(last_low or curr.low, curr.low)
                        last_close = curr.close
                        debug_events.append(
                            StructureDebugEvent(
                                bar_index=i,
                                timestamp=curr.timestamp,
                                candle_relationship=rel.value,
                                previous_direction=direction,
                                new_direction=direction,
                                action="continue_down",
                                reason="Outside bar continues DOWN direction",
                                affected_level="minor",
                            )
                        )

        # Build minor legs
        legs: list[StructureLeg] = []
        for i in range(len(points) - 1):
            leg = self._create_structure_leg(
                StructureLevel.MINOR, points[i], points[i + 1]
            )
            legs.append(leg)

        return points, legs, debug_events

    def _refine_minor_pivots(
        self,
        minor_points: list[StructurePoint],
        candles: list[OHLCVCandle],
    ) -> None:
        """
        Post-processing pass: refine minor L/H coordinates to container extremes.

        For H₁ → L₁ → H₂ where H₂.price > H₁.price (minor HH context):
          Scan candles in (H₁.bar_index, H₂.bar_index) exclusive.
          If the container's lowest-low candle has a lower low than L₁.price,
          move L₁ to that candle (bar_index, timestamp, low).

        For L₁ → H₁ → L₂ where L₂.price < L₁.price (minor LL context):
          Scan candles in (L₁.bar_index, L₂.bar_index) exclusive.
          If the container's highest-high candle has a higher high than H₁.price,
          move H₁ to that candle (bar_index, timestamp, high).

        Tie-breaking: earliest bar_index for equal lows and equal highs.
        Mutates minor_points in place. Does not change point kinds.
        """
        for i in range(1, len(minor_points) - 1):
            prev_p = minor_points[i - 1]
            curr_p = minor_points[i]
            next_p = minor_points[i + 1]

            if (
                curr_p.kind == PointKind.L
                and prev_p.kind == PointKind.H
                and next_p.kind == PointKind.H
                and next_p.price > prev_p.price
            ):
                # H₁ → L₁ → H₂ where H₂ > H₁: minor HH context — refine L₁
                container = [
                    c for c in candles
                    if prev_p.bar_index < c.bar_index < next_p.bar_index
                ]
                if container:
                    hl_candle = min(container, key=lambda c: (c.low, c.bar_index))
                    if hl_candle.low < curr_p.price:
                        curr_p.bar_index = hl_candle.bar_index
                        curr_p.timestamp = hl_candle.timestamp
                        curr_p.price = hl_candle.low

            elif (
                curr_p.kind == PointKind.H
                and prev_p.kind == PointKind.L
                and next_p.kind == PointKind.L
                and next_p.price < prev_p.price
            ):
                # L₁ → H₁ → L₂ where L₂ < L₁: minor LL context — refine H₁
                container = [
                    c for c in candles
                    if prev_p.bar_index < c.bar_index < next_p.bar_index
                ]
                if container:
                    lh_candle = min(container, key=lambda c: (-c.high, c.bar_index))
                    if lh_candle.high > curr_p.price:
                        curr_p.bar_index = lh_candle.bar_index
                        curr_p.timestamp = lh_candle.timestamp
                        curr_p.price = lh_candle.high

    def _compute_main_structure(
        self, minor_points: list[StructurePoint]
    ) -> tuple[list[StructurePoint], list[StructureLeg]]:
        """
        Compute main structure using a three-state construction machine (MS-7C).

        States
        ------
        ESTABLISHING : bootstrap phase — no confirmed sequence direction yet.
            At-or-above active H → BULLISH (HL + HH emitted).
            At-or-below active L → BEARISH (LH + LL emitted).

        BULLISH : confirmed uptrend (L → H → HL → HH → …).
            At-or-above main_high → HH continuation (HL + HH emitted).
            Strictly-below main_low → reversal (plain L emitted; prior HH is
            immutable). Equal to main_low is not a reversal — not emitted.

        BEARISH : confirmed downtrend (H → L → LH → LL → …).
            At-or-below main_low → LL continuation (LH + LL emitted).
            At-or-above main_high → reversal (plain H emitted; prior LL is
            immutable). Equal triggers reversal (MS-7C: >= LH ceiling → H).

        Threshold mapping (MS-7C):
            HH / BULL confirmation : price >= main_high  (was strict >)
            LL / BEAR confirmation : price <= main_low   (was strict <)
            BULL reversal          : price <  main_low   (stays strict)
            BEAR reversal          : price >= main_high  (was strict >)

        Reversal protection (MS-7C):
            Plain L and H emitted via reversal branches are tracked in
            reversal_bars. _apply_hl / _apply_lh never upgrade a reversal
            point to HL / LH even if a subsequent equal-value confirmation
            finds it as a retroactive candidate.

        All points derive exclusively from minor_points — no raw candle access.
        """
        _EST  = "establishing"
        _BULL = "bullish"
        _BEAR = "bearish"

        points:       list[StructurePoint] = []
        main_low:     Optional[float] = None
        main_high:    Optional[float] = None
        sequence:     str = _EST
        reversal_bars: set[int] = set()  # bar indices of emitted reversal L/H (MS-7C)

        _HIGH_KINDS = (PointKind.H, PointKind.HH, PointKind.LH)
        _LOW_KINDS  = (PointKind.L, PointKind.LL, PointKind.HL)

        def _make(kind: PointKind, src: StructurePoint) -> StructurePoint:
            pt = StructurePoint(
                id=f"main_{self._point_counter}",
                level=StructureLevel.MAIN,
                kind=kind,
                timestamp=src.timestamp,
                bar_index=src.bar_index,
                price=src.price,
                source="minor",
                confirmed=True,
            )
            self._point_counter += 1
            return pt

        def _hl_candidate(after_bar: int, before_bar: int) -> Optional[StructurePoint]:
            """Lowest minor L strictly inside (after_bar, before_bar)."""
            cands = [
                mp for mp in minor_points
                if mp.kind == PointKind.L
                and after_bar < mp.bar_index < before_bar
            ]
            return min(cands, key=lambda p: (p.price, p.bar_index)) if cands else None

        def _lh_candidate(after_bar: int, before_bar: int) -> Optional[StructurePoint]:
            """Highest minor H strictly inside (after_bar, before_bar)."""
            cands = [
                mp for mp in minor_points
                if mp.kind == PointKind.H
                and after_bar < mp.bar_index < before_bar
            ]
            return min(cands, key=lambda p: (-p.price, p.bar_index)) if cands else None

        def _apply_hl(hl: Optional[StructurePoint]) -> None:
            if hl is None:
                return
            existing = next(
                (p for p in points if p.bar_index == hl.bar_index and p.kind in _LOW_KINDS),
                None,
            )
            if existing is not None:
                if existing.bar_index not in reversal_bars:  # MS-7C: never upgrade a reversal L
                    existing.kind = PointKind.HL
            else:
                points.append(_make(PointKind.HL, hl))

        def _apply_lh(lh: Optional[StructurePoint]) -> None:
            if lh is None:
                return
            existing = next(
                (p for p in points if p.bar_index == lh.bar_index and p.kind in _HIGH_KINDS),
                None,
            )
            if existing is not None:
                if existing.bar_index not in reversal_bars:  # MS-7C: never upgrade a reversal H
                    existing.kind = PointKind.LH
            else:
                points.append(_make(PointKind.LH, lh))

        for mp in minor_points:
            # ── Bootstrap: first minor point ─────────────────────────────────
            if main_low is None and main_high is None:
                if mp.kind == PointKind.L:
                    main_low = mp.price
                    points.append(_make(PointKind.L, mp))
                else:
                    main_high = mp.price
                    points.append(_make(PointKind.H, mp))
                continue

            # ── Bootstrap: waiting for the opposite side ──────────────────────
            if main_high is None:
                if mp.kind == PointKind.H:
                    main_high = mp.price
                    points.append(_make(PointKind.H, mp))
                continue

            if main_low is None:
                if mp.kind == PointKind.L:
                    main_low = mp.price
                    points.append(_make(PointKind.L, mp))
                continue

            # ── Confirmation phase (MS-7C thresholds) ────────────────────────
            # Separate flags so each branch gets the correct equality semantics.
            is_at_or_above  = mp.price >= main_high  # confirmation + BEAR reversal
            is_at_or_below  = mp.price <= main_low   # confirmation
            is_strictly_below = mp.price < main_low  # BULL reversal (stays strict)

            if is_at_or_above and sequence != _BEAR:
                # At-or-above active ceiling — HH + HL.
                # Fires in ESTABLISHING (→ BULLISH) and BULLISH continuation.
                # Equal high (price == main_high) is eligible for HH (MS-7C).
                last_h = next((p for p in reversed(points) if p.kind in _HIGH_KINDS), None)
                hl = _hl_candidate(
                    after_bar=last_h.bar_index if last_h else -1,
                    before_bar=mp.bar_index,
                )
                _apply_hl(hl)
                points.append(_make(PointKind.HH, mp))
                main_high = mp.price
                if hl is not None:
                    main_low = hl.price
                sequence = _BULL

            elif is_at_or_below and sequence != _BULL:
                # At-or-below active floor — LL + LH.
                # Fires in ESTABLISHING (→ BEARISH) and BEARISH continuation.
                # Equal low (price == main_low) is eligible for LL (MS-7C).
                last_l = next((p for p in reversed(points) if p.kind in _LOW_KINDS), None)
                lh = _lh_candidate(
                    after_bar=last_l.bar_index if last_l else -1,
                    before_bar=mp.bar_index,
                )
                _apply_lh(lh)
                points.append(_make(PointKind.LL, mp))
                main_low = mp.price
                if lh is not None:
                    main_high = lh.price
                sequence = _BEAR

            elif is_strictly_below and sequence == _BULL:
                # BULLISH reversal: strictly below HL (active floor).
                # Equal to HL is not a reversal and is not emitted (MS-7C).
                # Emit plain L. Prior HH label is immutable. No LH created.
                points.append(_make(PointKind.L, mp))
                reversal_bars.add(mp.bar_index)         # MS-7C: protect from retroactive HL
                main_low = mp.price
                # main_high stays at the prior HH.price (set on last BULL confirmation).
                sequence = _EST

            elif is_at_or_above and sequence == _BEAR:
                # BEARISH reversal: at-or-above LH (active ceiling).
                # Equal to LH triggers reversal (MS-7C: price >= LH ceiling → H).
                # Emit plain H. Prior LL label is immutable. No HL created.
                points.append(_make(PointKind.H, mp))
                reversal_bars.add(mp.bar_index)         # MS-7C: protect from retroactive LH
                main_high = mp.price
                # main_low stays at the prior LL.price (set on last BEAR confirmation).
                sequence = _EST

        # Build main legs
        legs: list[StructureLeg] = []
        for i in range(len(points) - 1):
            legs.append(self._create_structure_leg(StructureLevel.MAIN, points[i], points[i + 1]))

        return points, legs

    def _label_structure_points(self, points: list[StructurePoint]) -> None:
        """
        Relabel structure points in-place using same-kind comparative labeling (MS-7A).

        Rules — High-type pivot (raw kind H / HH / LH):
          current >= prev_high AND prev_high was LH  → H  (bullish reversal above LH)
          current >= prev_high  (otherwise)           → HH (higher high or equal)
          current <  prev_high                        → LH (lower high)

        Rules — Low-type pivot (raw kind L / LL / HL):
          current >  prev_low                         → HL (higher low)
          current <  prev_low  AND prev_low was HL    → L  (bearish reversal below HL)
          current <= prev_low  (otherwise)            → LL (lower low or equal)

        Bootstrap: first high-type pivot → H; first low-type pivot → L.
        Only point.kind is mutated; bar_index, timestamp, and price are unchanged.
        """
        _HIGH_KINDS = (PointKind.H, PointKind.HH, PointKind.LH)
        _LOW_KINDS  = (PointKind.L, PointKind.LL, PointKind.HL)

        prev_high_price: Optional[float] = None
        prev_high_kind:  Optional[PointKind] = None
        prev_low_price:  Optional[float] = None
        prev_low_kind:   Optional[PointKind] = None

        for pt in points:
            if pt.kind in _HIGH_KINDS:
                if prev_high_price is None:
                    pt.kind        = PointKind.H
                    prev_high_price = pt.price
                    prev_high_kind  = PointKind.H
                else:
                    if pt.price >= prev_high_price and prev_high_kind == PointKind.LH:
                        pt.kind = PointKind.H   # bullish reversal: break above prior LH
                    elif pt.price >= prev_high_price:
                        pt.kind = PointKind.HH  # higher high (continuation or EST break)
                    else:
                        pt.kind = PointKind.LH  # lower high
                    prev_high_price = pt.price
                    prev_high_kind  = pt.kind
            else:
                if prev_low_price is None:
                    pt.kind       = PointKind.L
                    prev_low_price = pt.price
                    prev_low_kind  = PointKind.L
                else:
                    if pt.price > prev_low_price:
                        pt.kind = PointKind.HL  # higher low
                    elif pt.price < prev_low_price and prev_low_kind == PointKind.HL:
                        pt.kind = PointKind.L   # bearish reversal: break below prior HL
                    else:
                        pt.kind = PointKind.LL  # lower low (or equal)
                    prev_low_price = pt.price
                    prev_low_kind  = pt.kind

    def _create_structure_point(
        self,
        candle: OHLCVCandle,
        level: StructureLevel,
        kind: PointKind,
        source: str,
    ) -> StructurePoint:
        """Create a structure point from a candle."""
        point_id = f"{level.value}_{self._point_counter}"
        self._point_counter += 1
        return StructurePoint(
            id=point_id,
            level=level,
            kind=kind,
            timestamp=candle.timestamp,
            bar_index=candle.bar_index,
            price=candle.high if kind == PointKind.H else candle.low,
            source=source,
            confirmed=True,
        )

    def _create_structure_leg(
        self,
        level: StructureLevel,
        from_point: StructurePoint,
        to_point: StructurePoint,
    ) -> StructureLeg:
        """Create a structure leg between two points."""
        leg_id = f"{level.value}_leg_{self._leg_counter}"
        self._leg_counter += 1
        direction = Direction.UP if to_point.price > from_point.price else Direction.DOWN
        return StructureLeg(
            id=leg_id,
            level=level,
            from_point_id=from_point.id,
            to_point_id=to_point.id,
            direction=direction,
            start_bar_index=from_point.bar_index,
            end_bar_index=to_point.bar_index,
            start_price=from_point.price,
            end_price=to_point.price,
        )

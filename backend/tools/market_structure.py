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

        # Phase 1: Compute minor structure
        minor_points, minor_legs, debug_events = self._compute_minor_structure(candles)
        result.minor_points = minor_points
        result.minor_legs = minor_legs
        result.debug_events = debug_events

        # Phase 2: Compute main structure
        if minor_points:
            main_points, main_legs = self._compute_main_structure(
                minor_points, candles
            )
            result.main_points = main_points
            result.main_legs = main_legs

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
                    if is_higher_high:
                        # Continue UP
                        last_high = curr.high
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
                    elif is_lower_low:
                        # Reverse to DOWN
                        new_direction = Direction.DOWN
                        # Record the high point before reversal
                        point = self._create_structure_point(
                            prev, StructureLevel.MINOR, PointKind.H, "price"
                        )
                        points.append(point)
                        direction = new_direction
                        last_high = curr.high
                        last_low = curr.low
                        last_close = curr.close
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
                            # Reverse to DOWN
                            new_direction = Direction.DOWN
                            point = self._create_structure_point(
                                prev, StructureLevel.MINOR, PointKind.H, "price"
                            )
                            points.append(point)
                            direction = new_direction
                            last_high = curr.high
                            last_low = curr.low
                            last_close = curr.close
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
                    if is_lower_low:
                        # Continue DOWN
                        last_low = curr.low
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
                    elif is_higher_high:
                        # Reverse to UP
                        new_direction = Direction.UP
                        point = self._create_structure_point(
                            prev, StructureLevel.MINOR, PointKind.L, "price"
                        )
                        points.append(point)
                        direction = new_direction
                        last_high = curr.high
                        last_low = curr.low
                        last_close = curr.close
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
                            # Reverse to UP
                            new_direction = Direction.UP
                            point = self._create_structure_point(
                                prev, StructureLevel.MINOR, PointKind.L, "price"
                            )
                            points.append(point)
                            direction = new_direction
                            last_high = curr.high
                            last_low = curr.low
                            last_close = curr.close
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

    def _compute_main_structure(
        self, minor_points: list[StructurePoint], candles: list[OHLCVCandle]
    ) -> tuple[list[StructurePoint], list[StructureLeg]]:
        """
        Compute main structure from minor structure.

        Main structure is confirmed when minor structure breaks an existing range.
        - If minor breaks above main high, previous lowest minor low becomes Main HL
        - If minor breaks below main low, previous highest minor high becomes Main LH

        Returns:
            (main_points, main_legs)
        """
        points: list[StructurePoint] = []
        main_low: Optional[float] = None
        main_high: Optional[float] = None

        for i, minor_point in enumerate(minor_points):
            if main_low is None and main_high is None:
                # Initialize: first minor point sets the first main range
                if minor_point.kind == PointKind.L:
                    main_low = minor_point.price
                else:
                    main_high = minor_point.price
                # Create a main point from this minor point
                main_point = StructurePoint(
                    id=f"main_{self._point_counter}",
                    level=StructureLevel.MAIN,
                    kind=PointKind.L if minor_point.kind == PointKind.L else PointKind.H,
                    timestamp=minor_point.timestamp,
                    bar_index=minor_point.bar_index,
                    price=minor_point.price,
                    source="minor",
                    confirmed=True,
                )
                self._point_counter += 1
                points.append(main_point)
                continue

            # Check if minor point breaks existing main range
            if minor_point.price > (main_high or 0):
                # Broke above main high
                # Find the lowest minor low before this break
                lowest_before = min(
                    (p.price for j, p in enumerate(minor_points) if j < i and p.kind == PointKind.L),
                    default=None,
                )
                if lowest_before is not None and lowest_before not in [p.price for p in points]:
                    # Add the new HL point
                    hl_point = StructurePoint(
                        id=f"main_{self._point_counter}",
                        level=StructureLevel.MAIN,
                        kind=PointKind.HL,
                        timestamp=minor_points[next(j for j, p in enumerate(minor_points) if p.price == lowest_before and p.kind == PointKind.L)].timestamp,
                        bar_index=minor_points[next(j for j, p in enumerate(minor_points) if p.price == lowest_before and p.kind == PointKind.L)].bar_index,
                        price=lowest_before,
                        source="minor",
                        confirmed=True,
                    )
                    self._point_counter += 1
                    points.append(hl_point)

                # Add the new main high (HH)
                hh_point = StructurePoint(
                    id=f"main_{self._point_counter}",
                    level=StructureLevel.MAIN,
                    kind=PointKind.HH,
                    timestamp=minor_point.timestamp,
                    bar_index=minor_point.bar_index,
                    price=minor_point.price,
                    source="minor",
                    confirmed=True,
                )
                self._point_counter += 1
                points.append(hh_point)
                main_high = minor_point.price

            elif minor_point.price < (main_low or float("inf")):
                # Broke below main low
                # Find the highest minor high before this break
                highest_before = max(
                    (p.price for j, p in enumerate(minor_points) if j < i and p.kind == PointKind.H),
                    default=None,
                )
                if highest_before is not None and highest_before not in [p.price for p in points]:
                    # Add the new LH point
                    lh_point = StructurePoint(
                        id=f"main_{self._point_counter}",
                        level=StructureLevel.MAIN,
                        kind=PointKind.LH,
                        timestamp=minor_points[next(j for j, p in enumerate(minor_points) if p.price == highest_before and p.kind == PointKind.H)].timestamp,
                        bar_index=minor_points[next(j for j, p in enumerate(minor_points) if p.price == highest_before and p.kind == PointKind.H)].bar_index,
                        price=highest_before,
                        source="minor",
                        confirmed=True,
                    )
                    self._point_counter += 1
                    points.append(lh_point)

                # Add the new main low (LL)
                ll_point = StructurePoint(
                    id=f"main_{self._point_counter}",
                    level=StructureLevel.MAIN,
                    kind=PointKind.LL,
                    timestamp=minor_point.timestamp,
                    bar_index=minor_point.bar_index,
                    price=minor_point.price,
                    source="minor",
                    confirmed=True,
                )
                self._point_counter += 1
                points.append(ll_point)
                main_low = minor_point.price

        # Build main legs
        legs: list[StructureLeg] = []
        for i in range(len(points) - 1):
            leg = self._create_structure_leg(
                StructureLevel.MAIN, points[i], points[i + 1]
            )
            legs.append(leg)

        return points, legs

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

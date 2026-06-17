"""
Minor Structure V3 Engine — "Container Breakout Minor Structure" experimental variant.

Independent engine — does NOT import or subclass MarketStructureEngine (V1) or V2.
Only imports shared domain types (enums, dataclasses) from market_structure.py.

Registry: minor_structure_v3 / Experimental
Design record: docs/research_engines/minor_structure_v3.md

Core concept:
    Structure is defined by breakouts from an active temp_resistance/temp_support container.
    A candle is classified as inside-container, outside-container, bullish breakout,
    or bearish breakout relative to the active container (not the immediate previous candle).
    Pivots are emitted only on state transitions (high→low or low→high) and are placed
    at the true extreme candle of the completed leg.
"""

from typing import Optional

from backend.tools.market_structure import (
    Direction,
    OHLCVCandle,
    PointKind,
    StructureDebugEvent,
    StructureLeg,
    StructureLevel,
    StructurePoint,
    StructureResult,
)


class MinorStructureV3Engine:
    """
    Container Breakout minor structure engine.

    Maintains a temp_resistance / temp_support container.
    Classification per candle:
      - inside_container   : high <= R and low >= S → continue, no reset
      - outside_container  : high > R and low < S  → continue, reset container
      - bullish_breakout   : high > R and low >= S → state = high, reset container
      - bearish_breakout   : high <= R and low < S → state = low, reset container

    Pivots are emitted only when state changes (high→low or low→high).
    True-extreme placement: H is emitted at the highest high candle of the completed
    high leg; L is emitted at the lowest low candle of the completed low leg.
    """

    def __init__(self) -> None:
        self._point_counter = 0
        self._leg_counter = 0

    # ── Public entry point ────────────────────────────────────────────────────

    def compute_structure(self, candles: list[OHLCVCandle]) -> StructureResult:
        result = StructureResult()
        if len(candles) < 2:
            return result

        minor_points, _, debug_events = self._compute_minor_structure_v3(candles)
        result.debug_events = debug_events

        if minor_points:
            self._refine_minor_pivots(minor_points, candles)

        minor_legs = [
            self._create_structure_leg(StructureLevel.MINOR, minor_points[j], minor_points[j + 1])
            for j in range(len(minor_points) - 1)
        ]
        result.minor_points = minor_points
        result.minor_legs = minor_legs

        if minor_points:
            main_points, main_legs = self._compute_main_structure(minor_points)
            result.main_points = main_points
            result.main_legs = main_legs

        if minor_points:
            self._label_structure_points(minor_points)

        return result

    # ── V3 minor structure — container breakout algorithm ─────────────────────

    def _compute_minor_structure_v3(
        self, candles: list[OHLCVCandle]
    ) -> tuple[list[StructurePoint], list[StructureLeg], list[StructureDebugEvent]]:
        """
        Container Breakout minor structure.

        Container initialized from candles[0]. Candles are classified each iteration
        against the current [temp_support, temp_resistance] container. Inside-container
        candles do not reset the container. All other classifications reset it to the
        current candle's range.

        Pivots are only emitted when state transitions: high→low emits H at the tracked
        highest-high candle; low→high emits L at the tracked lowest-low candle.
        """
        points:    list[StructurePoint]    = []
        debug_events: list[StructureDebugEvent] = []

        # Container initialised from first candle
        temp_resistance: float = candles[0].high
        temp_support:    float = candles[0].low

        # State: None = no direction yet; 'high' = in up leg; 'low' = in down leg
        state: Optional[str] = None

        # True-extreme trackers
        highest_high_candle: Optional[OHLCVCandle] = None
        lowest_low_candle:   Optional[OHLCVCandle] = None

        debug_events.append(StructureDebugEvent(
            bar_index=0,
            timestamp=candles[0].timestamp,
            candle_relationship="startup",
            action="startup",
            reason=(
                f"Container initialized: resistance={candles[0].high:.2f}, "
                f"support={candles[0].low:.2f}"
            ),
            affected_level="minor",
        ))

        for i in range(1, len(candles)):
            curr = candles[i]

            is_inside  = curr.high <= temp_resistance and curr.low >= temp_support
            is_outside = curr.high >  temp_resistance and curr.low <  temp_support
            is_bullish = curr.high >  temp_resistance and curr.low >= temp_support
            is_bearish = curr.high <= temp_resistance and curr.low <  temp_support

            prev_dir = (
                Direction.UP   if state == "high" else
                Direction.DOWN if state == "low"  else
                None
            )

            # ── Inside container ─────────────────────────────────────────────
            if is_inside:
                debug_events.append(StructureDebugEvent(
                    bar_index=i,
                    timestamp=curr.timestamp,
                    candle_relationship="inside_container",
                    previous_direction=prev_dir,
                    new_direction=prev_dir,
                    action="inside_container",
                    reason=(
                        f"High {curr.high:.2f} <= R {temp_resistance:.2f}, "
                        f"Low {curr.low:.2f} >= S {temp_support:.2f}"
                    ),
                    affected_level="minor",
                ))

            # ── Outside container ─────────────────────────────────────────────
            elif is_outside:
                # Update true-extreme tracker before resetting container
                if state == "high":
                    if highest_high_candle is None or curr.high > highest_high_candle.high:
                        highest_high_candle = curr
                elif state == "low":
                    if lowest_low_candle is None or curr.low < lowest_low_candle.low:
                        lowest_low_candle = curr

                old_r, old_s   = temp_resistance, temp_support
                temp_resistance = curr.high
                temp_support    = curr.low

                debug_events.append(StructureDebugEvent(
                    bar_index=i,
                    timestamp=curr.timestamp,
                    candle_relationship="outside_container",
                    previous_direction=prev_dir,
                    new_direction=prev_dir,
                    action="outside_container",
                    reason=(
                        f"High {curr.high:.2f} > R {old_r:.2f} AND "
                        f"Low {curr.low:.2f} < S {old_s:.2f}; container reset"
                    ),
                    affected_level="minor",
                ))

            # ── Bullish breakout ──────────────────────────────────────────────
            elif is_bullish:
                emitted_id: Optional[str] = None

                if state == "low":
                    # low → high transition: emit swing low at tracked extreme
                    if lowest_low_candle is not None:
                        pt = self._create_structure_point(
                            lowest_low_candle, StructureLevel.MINOR, PointKind.L, "price"
                        )
                        points.append(pt)
                        emitted_id = pt.id
                    lowest_low_candle = None

                old_r, old_s   = temp_resistance, temp_support
                state           = "high"
                temp_resistance = curr.high
                temp_support    = curr.low

                if highest_high_candle is None or curr.high > highest_high_candle.high:
                    highest_high_candle = curr

                debug_events.append(StructureDebugEvent(
                    bar_index=i,
                    timestamp=curr.timestamp,
                    candle_relationship="bullish_breakout",
                    previous_direction=prev_dir,
                    new_direction=Direction.UP,
                    action="bullish_breakout",
                    reason=(
                        f"High {curr.high:.2f} > R {old_r:.2f}, "
                        f"Low {curr.low:.2f} >= S {old_s:.2f}"
                    ),
                    affected_level="minor",
                    confirmed_point_id=emitted_id,
                ))

            # ── Bearish breakout ──────────────────────────────────────────────
            elif is_bearish:
                emitted_id = None

                if state == "high":
                    # high → low transition: emit swing high at tracked extreme
                    if highest_high_candle is not None:
                        pt = self._create_structure_point(
                            highest_high_candle, StructureLevel.MINOR, PointKind.H, "price"
                        )
                        points.append(pt)
                        emitted_id = pt.id
                    highest_high_candle = None

                old_r, old_s   = temp_resistance, temp_support
                state           = "low"
                temp_resistance = curr.high
                temp_support    = curr.low

                if lowest_low_candle is None or curr.low < lowest_low_candle.low:
                    lowest_low_candle = curr

                debug_events.append(StructureDebugEvent(
                    bar_index=i,
                    timestamp=curr.timestamp,
                    candle_relationship="bearish_breakout",
                    previous_direction=prev_dir,
                    new_direction=Direction.DOWN,
                    action="bearish_breakout",
                    reason=(
                        f"Low {curr.low:.2f} < S {old_s:.2f}, "
                        f"High {curr.high:.2f} <= R {old_r:.2f}"
                    ),
                    affected_level="minor",
                    confirmed_point_id=emitted_id,
                ))

        legs: list[StructureLeg] = []
        for j in range(len(points) - 1):
            legs.append(self._create_structure_leg(StructureLevel.MINOR, points[j], points[j + 1]))

        return points, legs, debug_events

    # ── Shared methods (independent copies — no dependency on V1/V2 classes) ──

    def _refine_minor_pivots(
        self,
        minor_points: list[StructurePoint],
        candles: list[OHLCVCandle],
    ) -> None:
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
                container = [c for c in candles if prev_p.bar_index < c.bar_index < next_p.bar_index]
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
                container = [c for c in candles if prev_p.bar_index < c.bar_index < next_p.bar_index]
                if container:
                    lh_candle = min(container, key=lambda c: (-c.high, c.bar_index))
                    if lh_candle.high > curr_p.price:
                        curr_p.bar_index = lh_candle.bar_index
                        curr_p.timestamp = lh_candle.timestamp
                        curr_p.price = lh_candle.high

    def _compute_main_structure(
        self, minor_points: list[StructurePoint]
    ) -> tuple[list[StructurePoint], list[StructureLeg]]:
        _EST  = "establishing"
        _BULL = "bullish"
        _BEAR = "bearish"

        points:        list[StructurePoint] = []
        main_low:      Optional[float] = None
        main_high:     Optional[float] = None
        sequence:      str = _EST
        reversal_bars: set[int] = set()

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
            cands = [
                mp for mp in minor_points
                if mp.kind == PointKind.L and after_bar < mp.bar_index < before_bar
            ]
            return min(cands, key=lambda p: (p.price, p.bar_index)) if cands else None

        def _lh_candidate(after_bar: int, before_bar: int) -> Optional[StructurePoint]:
            cands = [
                mp for mp in minor_points
                if mp.kind == PointKind.H and after_bar < mp.bar_index < before_bar
            ]
            return min(cands, key=lambda p: (-p.price, p.bar_index)) if cands else None

        def _apply_hl(hl: Optional[StructurePoint]) -> None:
            if hl is None:
                return
            existing = next(
                (p for p in points if p.bar_index == hl.bar_index and p.kind in _LOW_KINDS), None
            )
            if existing is not None:
                if existing.bar_index not in reversal_bars:
                    existing.kind = PointKind.HL
            else:
                points.append(_make(PointKind.HL, hl))

        def _apply_lh(lh: Optional[StructurePoint]) -> None:
            if lh is None:
                return
            existing = next(
                (p for p in points if p.bar_index == lh.bar_index and p.kind in _HIGH_KINDS), None
            )
            if existing is not None:
                if existing.bar_index not in reversal_bars:
                    existing.kind = PointKind.LH
            else:
                points.append(_make(PointKind.LH, lh))

        for mp in minor_points:
            if main_low is None and main_high is None:
                if mp.kind == PointKind.L:
                    main_low = mp.price
                    points.append(_make(PointKind.L, mp))
                else:
                    main_high = mp.price
                    points.append(_make(PointKind.H, mp))
                continue

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

            is_at_or_above    = mp.price >= main_high
            is_at_or_below    = mp.price <= main_low
            is_strictly_below = mp.price <  main_low

            if is_at_or_above and sequence != _BEAR:
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
                points.append(_make(PointKind.L, mp))
                reversal_bars.add(mp.bar_index)
                main_low = mp.price
                sequence = _EST

            elif is_at_or_above and sequence == _BEAR:
                points.append(_make(PointKind.H, mp))
                reversal_bars.add(mp.bar_index)
                main_high = mp.price
                sequence = _EST

        legs: list[StructureLeg] = []
        for j in range(len(points) - 1):
            legs.append(self._create_structure_leg(StructureLevel.MAIN, points[j], points[j + 1]))

        return points, legs

    def _label_structure_points(self, points: list[StructurePoint]) -> None:
        _HIGH_KINDS = (PointKind.H, PointKind.HH, PointKind.LH)
        _LOW_KINDS  = (PointKind.L, PointKind.LL, PointKind.HL)

        prev_high_price: Optional[float] = None
        prev_high_kind:  Optional[PointKind] = None
        prev_low_price:  Optional[float] = None
        prev_low_kind:   Optional[PointKind] = None

        for pt in points:
            if pt.kind in _HIGH_KINDS:
                if prev_high_price is None:
                    pt.kind = PointKind.H
                    prev_high_price = pt.price
                    prev_high_kind  = PointKind.H
                else:
                    if pt.price >= prev_high_price and prev_high_kind == PointKind.LH:
                        pt.kind = PointKind.H
                    elif pt.price >= prev_high_price:
                        pt.kind = PointKind.HH
                    else:
                        pt.kind = PointKind.LH
                    prev_high_price = pt.price
                    prev_high_kind  = pt.kind
            else:
                if prev_low_price is None:
                    pt.kind = PointKind.L
                    prev_low_price = pt.price
                    prev_low_kind  = PointKind.L
                else:
                    if pt.price > prev_low_price:
                        pt.kind = PointKind.HL
                    elif pt.price < prev_low_price and prev_low_kind == PointKind.HL:
                        pt.kind = PointKind.L
                    else:
                        pt.kind = PointKind.LL
                    prev_low_price = pt.price
                    prev_low_kind  = pt.kind

    def _create_structure_point(
        self,
        candle: OHLCVCandle,
        level: StructureLevel,
        kind: PointKind,
        source: str,
    ) -> StructurePoint:
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

"""
Minor Structure V2 Engine — "Ignore Inside Bar" experimental variant.

Independent engine — does NOT import or subclass MarketStructureEngine (V1).
Only imports shared domain types (enums, dataclasses) from market_structure.py.

Registry: minor_structure_v2 / Experimental
Design record: docs/research_engines/minor_structure_v2.md
"""

from typing import Optional

from backend.tools.market_structure import (
    CandleRelationship,
    Direction,
    OHLCVCandle,
    PointKind,
    StructureDebugEvent,
    StructureLeg,
    StructureLevel,
    StructurePoint,
    StructureResult,
)


class MinorStructureV2Engine:
    """
    Experimental minor structure engine: inside bars form clusters and are ignored
    unless the cluster reaches 4+ candles, in which case a single pivot is placed
    at the cluster's true price extreme after breakout.

    All other V1 rules are preserved unchanged.
    This engine is independent of MarketStructureEngine (V1).
    """

    def __init__(self) -> None:
        self._point_counter = 0
        self._leg_counter = 0

    # ── Public entry point ────────────────────────────────────────────────────

    def compute_structure(self, candles: list[OHLCVCandle]) -> StructureResult:
        result = StructureResult()
        if len(candles) < 2:
            return result

        minor_points, _, debug_events = self._compute_minor_structure_v2(candles)
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

    # ── V2 minor structure — cluster algorithm ────────────────────────────────

    def _compute_minor_structure_v2(
        self, candles: list[OHLCVCandle]
    ) -> tuple[list[StructurePoint], list[StructureLeg], list[StructureDebugEvent]]:
        """
        V2 minor structure: inside bars form clusters; only clusters of 4+ create a pivot.

        Key differences from V1:
        - Inside bar detected with STRICT inequalities (< and >) against n0 (mother candle).
        - Inside bars do not trigger reversals during the cluster.
        - Clusters < 4: no pivot; breakout candle processed by V1 rules.
        - Clusters >= 4, same-direction breakout: pivot at cluster extreme before V1 processing.
        - Clusters >= 4, opposite-direction breakout: no cluster pivot; V1 reversal handles it.
        """
        points: list[StructurePoint] = []
        debug_events: list[StructureDebugEvent] = []
        direction: Optional[Direction] = None
        last_high: Optional[float] = None
        last_low: Optional[float] = None
        last_close: Optional[float] = None
        last_high_candle: Optional[OHLCVCandle] = None
        last_low_candle: Optional[OHLCVCandle] = None

        mother_candle: Optional[OHLCVCandle] = None  # n0: cluster reference
        cluster_candles: list[OHLCVCandle] = []

        for i in range(1, len(candles)):
            prev = candles[i - 1]
            curr = candles[i]

            is_hh = curr.high > prev.high
            is_ll = curr.low < prev.low
            is_ob = is_hh and is_ll
            is_ib_v1 = curr.high <= prev.high and curr.low >= prev.low

            if is_ib_v1:
                rel = CandleRelationship.INSIDE_BAR
            elif is_ob:
                rel = CandleRelationship.OUTSIDE_BAR
            elif is_hh:
                rel = CandleRelationship.HIGHER_HIGH
            elif is_ll:
                rel = CandleRelationship.LOWER_LOW
            else:
                rel = CandleRelationship.AMBIGUOUS_STARTUP

            # ── STARTUP: no direction yet ─────────────────────────────────────
            if direction is None:
                if rel == CandleRelationship.HIGHER_HIGH:
                    direction = Direction.UP
                    last_high = curr.high
                    last_low = curr.low
                    last_close = curr.close
                    last_high_candle = curr
                    last_low_candle = curr
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value, new_direction=direction,
                        action="establish_up",
                        reason="Higher high establishes UP direction at startup",
                        affected_level="minor",
                    ))
                elif rel == CandleRelationship.LOWER_LOW:
                    direction = Direction.DOWN
                    last_high = curr.high
                    last_low = curr.low
                    last_close = curr.close
                    last_high_candle = curr
                    last_low_candle = curr
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value, new_direction=direction,
                        action="establish_down",
                        reason="Lower low establishes DOWN direction at startup",
                        affected_level="minor",
                    ))
                else:
                    last_high = curr.high
                    last_low = curr.low
                    last_close = curr.close
                    last_high_candle = curr
                    last_low_candle = curr
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        action="wait_for_direction",
                        reason="Ambiguous startup pattern; waiting for clear direction",
                        affected_level="minor",
                    ))
                continue

            # ── CLUSTER ACTIVE: check if still inside n0 ─────────────────────
            if mother_candle is not None:
                still_inside = curr.high < mother_candle.high and curr.low > mother_candle.low
                if still_inside:
                    cluster_candles.append(curr)
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        previous_direction=direction, new_direction=direction,
                        action="cluster_inside",
                        reason=f"Inside n0 (bar {mother_candle.bar_index}); cluster size {len(cluster_candles)}",
                        affected_level="minor",
                    ))
                    continue

                # ── BREAKOUT ──────────────────────────────────────────────────
                cluster_size = len(cluster_candles)
                last_in_cluster = cluster_candles[-1]
                bo_hh = curr.high > last_in_cluster.high
                bo_ll = curr.low < last_in_cluster.low

                if cluster_size >= 4:
                    if direction == Direction.UP and bo_hh:
                        # Same direction (HH or OB): support pivot at cluster lowest
                        extreme = min(cluster_candles, key=lambda c: (c.low, c.bar_index))
                        pt = self._create_structure_point(
                            extreme, StructureLevel.MINOR, PointKind.L, "price"
                        )
                        points.append(pt)
                        debug_events.append(StructureDebugEvent(
                            bar_index=i, timestamp=curr.timestamp,
                            candle_relationship=rel.value,
                            previous_direction=direction, new_direction=direction,
                            action="cluster_breakout_same",
                            reason=(
                                f"Cluster of {cluster_size} (>=4) breaks HH; "
                                f"L pivot at cluster low bar {extreme.bar_index}"
                            ),
                            affected_level="minor", confirmed_point_id=pt.id,
                        ))
                    elif direction == Direction.DOWN and bo_ll:
                        # Same direction (LL or OB): resistance pivot at cluster highest
                        extreme = min(cluster_candles, key=lambda c: (-c.high, c.bar_index))
                        pt = self._create_structure_point(
                            extreme, StructureLevel.MINOR, PointKind.H, "price"
                        )
                        points.append(pt)
                        debug_events.append(StructureDebugEvent(
                            bar_index=i, timestamp=curr.timestamp,
                            candle_relationship=rel.value,
                            previous_direction=direction, new_direction=direction,
                            action="cluster_breakout_same",
                            reason=(
                                f"Cluster of {cluster_size} (>=4) breaks LL; "
                                f"H pivot at cluster high bar {extreme.bar_index}"
                            ),
                            affected_level="minor", confirmed_point_id=pt.id,
                        ))
                    else:
                        # Opposite direction: no cluster pivot; V1 reversal handles it
                        debug_events.append(StructureDebugEvent(
                            bar_index=i, timestamp=curr.timestamp,
                            candle_relationship=rel.value,
                            previous_direction=direction, new_direction=direction,
                            action="cluster_breakout_opposite",
                            reason=(
                                f"Cluster of {cluster_size} (>=4) breaks opposite direction; "
                                "no cluster pivot; V1 reversal applied"
                            ),
                            affected_level="minor",
                        ))
                else:
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        previous_direction=direction, new_direction=direction,
                        action="cluster_discard",
                        reason=f"Cluster of {cluster_size} (<4); no pivot; V1 rules applied",
                        affected_level="minor",
                    ))

                mother_candle = None
                cluster_candles = []
                # Fall through to V1 processing of this breakout candle

            # ── V2 INSIDE BAR CHECK: strict vs prev ──────────────────────────
            is_ib_v2 = curr.high < prev.high and curr.low > prev.low
            if is_ib_v2:
                mother_candle = prev
                cluster_candles = [curr]
                debug_events.append(StructureDebugEvent(
                    bar_index=i, timestamp=curr.timestamp,
                    candle_relationship=rel.value,
                    previous_direction=direction, new_direction=direction,
                    action="cluster_start",
                    reason=f"V2 strict inside bar; n0=bar {prev.bar_index}; cluster started",
                    affected_level="minor",
                ))
                continue

            # ── V1 DIRECTION PROCESSING (no inside-bar branch in V2) ─────────
            if direction == Direction.UP:
                if rel == CandleRelationship.HIGHER_HIGH:
                    last_high = curr.high
                    last_high_candle = curr
                    last_low = curr.low
                    last_close = curr.close
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        previous_direction=direction, new_direction=direction,
                        action="continue_up",
                        reason=f"Higher high ({curr.high:.2f} > {prev.high:.2f})",
                        affected_level="minor",
                    ))
                elif rel == CandleRelationship.LOWER_LOW:
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
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        previous_direction=Direction.UP, new_direction=new_direction,
                        action="reverse_down",
                        reason=f"Lower low ({curr.low:.2f} < {prev.low:.2f}) reverses structure",
                        affected_level="minor", confirmed_point_id=point.id,
                    ))
                else:
                    # Outside bar or ambiguous: continue UP
                    if curr.high > (last_high or 0):
                        last_high_candle = curr
                    last_high = max(last_high or curr.high, curr.high)
                    last_close = curr.close
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        previous_direction=direction, new_direction=direction,
                        action="continue_up",
                        reason="Outside bar continues UP direction",
                        affected_level="minor",
                    ))

            else:  # Direction.DOWN
                if rel == CandleRelationship.LOWER_LOW:
                    last_low = curr.low
                    last_low_candle = curr
                    last_high = curr.high
                    last_close = curr.close
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        previous_direction=direction, new_direction=direction,
                        action="continue_down",
                        reason=f"Lower low ({curr.low:.2f} < {prev.low:.2f})",
                        affected_level="minor",
                    ))
                elif rel == CandleRelationship.HIGHER_HIGH:
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
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        previous_direction=Direction.DOWN, new_direction=new_direction,
                        action="reverse_up",
                        reason=f"Higher high ({curr.high:.2f} > {prev.high:.2f}) reverses structure",
                        affected_level="minor", confirmed_point_id=point.id,
                    ))
                else:
                    # Outside bar or ambiguous: continue DOWN
                    if curr.low < (last_low or float("inf")):
                        last_low_candle = curr
                    last_low = min(last_low or curr.low, curr.low)
                    last_close = curr.close
                    debug_events.append(StructureDebugEvent(
                        bar_index=i, timestamp=curr.timestamp,
                        candle_relationship=rel.value,
                        previous_direction=direction, new_direction=direction,
                        action="continue_down",
                        reason="Outside bar continues DOWN direction",
                        affected_level="minor",
                    ))

        legs: list[StructureLeg] = []
        for j in range(len(points) - 1):
            legs.append(self._create_structure_leg(StructureLevel.MINOR, points[j], points[j + 1]))

        return points, legs, debug_events

    # ── Copied shared methods (independent of V1 engine class) ───────────────

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

            is_at_or_above   = mp.price >= main_high
            is_at_or_below   = mp.price <= main_low
            is_strictly_below = mp.price < main_low

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

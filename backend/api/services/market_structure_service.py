"""
Market structure computation service — MS-2 / VIZ-1.

Computes minor and main market structure, BoS events, and CHoCH events
from a raw OHLCV candle list and returns them as a unified response for
visual verification on the chart.

No strategy logic, no signals, no trading execution.
"""
from backend.api.schemas.chart import (
    BosEventResponse,
    ChochEventResponse,
    MarketStructureRequest,
    MarketStructureResponse,
    StructureDebugEventResponse,
    StructureLegResponse,
    StructurePointResponse,
)
from backend.tools.bos_detection import BoSEvent, detect_bos
from backend.tools.choch_detection import CHoCHEvent, detect_choch
from fastapi import HTTPException
from backend.tools.market_structure import (
    MarketStructureEngine,
    OHLCVCandle,
)
from backend.tools.market_structure_v2 import MinorStructureV2Engine
from backend.tools.market_structure_v3 import MinorStructureV3Engine


def _map_bos(ev: BoSEvent) -> BosEventResponse:
    return BosEventResponse(
        status=str(ev.status.value),
        direction=str(ev.direction.value),
        structure_scope=ev.structure_scope,
        break_level=ev.break_level,
        protected_level=ev.protected_level,
        break_candle_index=ev.break_candle_index,
        break_candle_timestamp=ev.break_candle_timestamp,
        confirmation_level=ev.confirmation_level,
        confirmation_candle_index=ev.confirmation_candle_index,
        confirmation_candle_timestamp=ev.confirmation_candle_timestamp,
        invalidation_candle_index=ev.invalidation_candle_index,
        invalidation_candle_timestamp=ev.invalidation_candle_timestamp,
    )


def _map_choch(ev: CHoCHEvent) -> ChochEventResponse:
    return ChochEventResponse(
        direction=str(ev.direction.value),
        structure_scope=ev.structure_scope,
        protected_level=ev.protected_level,
        break_candle_index=ev.break_candle_index,
        break_candle_timestamp=ev.break_candle_timestamp,
        structure_reference_index=ev.structure_reference_index,
        structure_reference_timestamp=ev.structure_reference_timestamp,
        reference_structure_type=ev.reference_structure_type,
        violated_trend=ev.violated_trend,
    )


def compute_market_structure_from_candles(
    request: MarketStructureRequest,
) -> MarketStructureResponse:
    """
    Compute minor/main market structure plus BoS and CHoCH events from OHLCV candles.

    The candles must be in chronological order; bar_index in the response maps
    directly to the input index (0 = first candle, N-1 = last candle).

    BoS and CHoCH detectors run against already-labeled minor and main structure
    points so all three outputs (structure, BoS, CHoCH) are consistent.
    """
    if request.engine_id == "minor_structure_v2":
        engine: MarketStructureEngine | MinorStructureV2Engine | MinorStructureV3Engine = MinorStructureV2Engine()
    elif request.engine_id == "minor_structure_v3":
        engine = MinorStructureV3Engine()
    elif request.engine_id == "minor_structure_v1":
        engine = MarketStructureEngine()
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown engine_id: {request.engine_id!r}. "
                "Valid values: minor_structure_v1, minor_structure_v2, minor_structure_v3"
            ),
        )

    ohlcv_candles = [
        OHLCVCandle(
            timestamp=c.timestamp,
            bar_index=i,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
        )
        for i, c in enumerate(request.candles)
    ]

    result = engine.compute_structure(ohlcv_candles)

    # BoS and CHoCH are detected from minor structure only.
    minor_bos   = detect_bos(result.minor_points,   ohlcv_candles, "minor")
    minor_choch = detect_choch(result.minor_points, ohlcv_candles, "minor")

    return MarketStructureResponse(
        minor_points=[
            StructurePointResponse(
                id=p.id,
                level=p.level.value,
                kind=p.kind.value,
                timestamp=p.timestamp,
                bar_index=p.bar_index,
                price=p.price,
                source=p.source,
                confirmed=p.confirmed,
            )
            for p in result.minor_points
        ],
        minor_legs=[
            StructureLegResponse(
                id=lg.id,
                level=lg.level.value,
                from_point_id=lg.from_point_id,
                to_point_id=lg.to_point_id,
                direction=lg.direction.value,
                start_bar_index=lg.start_bar_index,
                end_bar_index=lg.end_bar_index,
                start_price=lg.start_price,
                end_price=lg.end_price,
            )
            for lg in result.minor_legs
        ],
        main_points=[
            StructurePointResponse(
                id=p.id,
                level=p.level.value,
                kind=p.kind.value,
                timestamp=p.timestamp,
                bar_index=p.bar_index,
                price=p.price,
                source=p.source,
                confirmed=p.confirmed,
            )
            for p in result.main_points
        ],
        main_legs=[
            StructureLegResponse(
                id=lg.id,
                level=lg.level.value,
                from_point_id=lg.from_point_id,
                to_point_id=lg.to_point_id,
                direction=lg.direction.value,
                start_bar_index=lg.start_bar_index,
                end_bar_index=lg.end_bar_index,
                start_price=lg.start_price,
                end_price=lg.end_price,
            )
            for lg in result.main_legs
        ],
        debug_events=[
            StructureDebugEventResponse(
                bar_index=e.bar_index,
                timestamp=e.timestamp,
                candle_relationship=e.candle_relationship,
                previous_direction=e.previous_direction.value if e.previous_direction else None,
                new_direction=e.new_direction.value if e.new_direction else None,
                action=e.action,
                reason=e.reason,
                affected_level=e.affected_level,
            )
            for e in result.debug_events
        ],
        bos_events=[_map_bos(ev) for ev in minor_bos],
        choch_events=[_map_choch(ev) for ev in minor_choch],
    )

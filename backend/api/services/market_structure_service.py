"""
Market structure computation service — MS-2 / VIZ-1.

Computes minor and main market structure, BoS events, and CHoCH events
from a raw OHLCV candle list and returns them as a unified response for
visual verification on the chart.

No strategy logic, no signals, no trading execution.

Lineage guardrail (RESEARCH-TOOL-LINEAGE-GUARD-1)
--------------------------------------------------
Every response carries explicit lineage metadata so callers can verify
exactly which engine produced the output.  Two invariants are enforced by
assertion before the response is built:

  1. The instantiated engine class must match the requested engine_id.
  2. The parent_engine_id on every derived tool (BoS, CHoCH) must equal
     the structure engine's tool_id.

Any mismatch raises AssertionError, surfacing as a 500 and preventing
silently wrong analysis from reaching the frontend.

Public factory
--------------
build_minor_structure_engine(engine_id) is the canonical, registry-aware
way to instantiate a minor structure engine.  Audit and research scripts
must use this function instead of directly importing and constructing
engine classes, so that engine selection always routes through the registry
and always produces consistent lineage metadata.
"""
from backend.api.schemas.chart import (
    BosEventResponse,
    ChochEventResponse,
    DerivedToolLineageResponse,
    ExperimentalBosEventResponse,
    MarketBiasResponse,
    MarketStructureRequest,
    MarketStructureResponse,
    StructureDebugEventResponse,
    StructureLegResponse,
    StructurePointResponse,
    ToolLineageResponse,
)
from backend.tools.bos_detection import BoSEvent, detect_bos
from backend.tools.bos_pivot_experimental import (
    ExperimentalBosEvent,
    detect_experimental_bos_bullish,
)
from backend.tools.choch_detection import CHoCHEvent, detect_choch
from backend.tools.market_bias_geometric_v1 import MarketBiasResult, compute_market_bias
from fastapi import HTTPException
from backend.tools.market_structure import (
    MarketStructureEngine,
    OHLCVCandle,
)
from backend.tools.market_structure_v2 import MinorStructureV2Engine
from backend.tools.market_structure_v3 import MinorStructureV3Engine

# ---------------------------------------------------------------------------
# Engine registry — single source of truth for lineage metadata
#
# Each entry matches one technical_id in research_engines.yaml.
# implementation_ref encodes "module::class" so any discrepancy between
# this constant and the actual class used is caught by _GUARD_ENGINE_CLASS.
# ---------------------------------------------------------------------------

_ENGINE_METADATA: dict[str, dict[str, str]] = {
    "minor_structure_v1": {
        "tool_domain":        "market_structure",
        "tool_id":            "minor_structure_v1",
        "version_id":         "minor_structure_v1",
        "human_name":         "Classic Minor Structure",
        "lifecycle_status":   "production",
        "implementation_ref": "backend/tools/market_structure.py::MarketStructureEngine",
    },
    "minor_structure_v2": {
        "tool_domain":        "market_structure",
        "tool_id":            "minor_structure_v2",
        "version_id":         "minor_structure_v2",
        "human_name":         "Minor Structure Ignore Inside Bar",
        "lifecycle_status":   "experimental",
        "implementation_ref": "backend/tools/market_structure_v2.py::MinorStructureV2Engine",
    },
    "minor_structure_v3": {
        "tool_domain":        "market_structure",
        "tool_id":            "minor_structure_v3",
        "version_id":         "minor_structure_v3",
        "human_name":         "Container Breakout Minor Structure",
        "lifecycle_status":   "experimental",
        "implementation_ref": "backend/tools/market_structure_v3.py::MinorStructureV3Engine",
    },
}

# Maps each engine_id to the exact class it must produce. Used by the guard.
_ENGINE_EXPECTED_CLASS: dict[str, type] = {
    "minor_structure_v1": MarketStructureEngine,
    "minor_structure_v2": MinorStructureV2Engine,
    "minor_structure_v3": MinorStructureV3Engine,
}

_BOS_METADATA: dict[str, str] = {
    "tool_domain": "structure_event",
    "tool_id":     "bos_detection",
}

_CHOCH_METADATA: dict[str, str] = {
    "tool_domain": "structure_event",
    "tool_id":     "choch_detection",
}


# ---------------------------------------------------------------------------
# Public factory — Phase 5 canonical entry point
# ---------------------------------------------------------------------------

def build_minor_structure_engine(
    engine_id: str,
) -> MarketStructureEngine | MinorStructureV2Engine | MinorStructureV3Engine:
    """
    Return the correct minor structure engine for *engine_id*.

    This is the canonical, registry-aware factory for all code that needs
    a minor structure engine — API service, audit scripts, research notebooks.
    Direct instantiation of MarketStructureEngine / MinorStructureV2Engine /
    MinorStructureV3Engine bypasses the registry and must not be used for
    generic research or audit purposes; use this function instead.

    Raises ValueError for unknown engine_id (never silently falls back to V1).
    """
    if engine_id not in _ENGINE_METADATA:
        raise ValueError(
            f"Unknown minor structure engine_id: {engine_id!r}. "
            f"Valid values: {sorted(_ENGINE_METADATA)}"
        )
    if engine_id == "minor_structure_v2":
        return MinorStructureV2Engine()
    if engine_id == "minor_structure_v3":
        return MinorStructureV3Engine()
    return MarketStructureEngine()


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

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


def _map_market_bias(result: MarketBiasResult) -> MarketBiasResponse:
    return MarketBiasResponse(
        engine=result.engine,
        bias=result.bias,
        condition=result.condition,
        reason=result.reason,
        pivots_used=list(result.pivots_used),
        current_close=result.current_close,
        boundaries=dict(result.boundaries),
    )


def _map_experimental_bos(ev: ExperimentalBosEvent) -> ExperimentalBosEventResponse:
    return ExperimentalBosEventResponse(
        direction=ev.direction,
        p1_bar_index=ev.p1_bar_index,
        p1_price=ev.p1_price,
        p1_timestamp=ev.p1_timestamp,
        p2_bar_index=ev.p2_bar_index,
        p2_price=ev.p2_price,
        p2_timestamp=ev.p2_timestamp,
        p3_bar_index=ev.p3_bar_index,
        p3_price=ev.p3_price,
        p3_timestamp=ev.p3_timestamp,
        break_candle_index=ev.break_candle_index,
        break_candle_timestamp=ev.break_candle_timestamp,
        broken_level=ev.broken_level,
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


# ---------------------------------------------------------------------------
# Service entry point
# ---------------------------------------------------------------------------

def compute_market_structure_from_candles(
    request: MarketStructureRequest,
) -> MarketStructureResponse:
    """
    Compute minor/main market structure plus BoS and CHoCH events from OHLCV candles.

    The candles must be in chronological order; bar_index in the response maps
    directly to the input index (0 = first candle, N-1 = last candle).

    BoS and CHoCH detectors run against already-labeled minor and main structure
    points so all three outputs (structure, BoS, CHoCH) are consistent.

    Lineage metadata is attached to every response.  Two assertions enforce the
    lineage invariants — any violation surfaces as a 500 before bad data escapes.
    """
    engine_id = request.engine_id

    if engine_id not in _ENGINE_METADATA:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown engine_id: {engine_id!r}. "
                f"Valid values: {sorted(_ENGINE_METADATA)}"
            ),
        )

    engine = build_minor_structure_engine(engine_id)

    # ── Guard 1: instantiated class must match the registered expectation ──────
    assert isinstance(engine, _ENGINE_EXPECTED_CLASS[engine_id]), (
        f"LINEAGE ERROR: requested engine_id={engine_id!r} "
        f"but build_minor_structure_engine returned {type(engine).__name__}. "
        f"Expected {_ENGINE_EXPECTED_CLASS[engine_id].__name__}."
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

    # BoS and CHoCH are detected from minor structure only — same result object.
    minor_bos   = detect_bos(result.minor_points,   ohlcv_candles, "minor")
    minor_choch = detect_choch(result.minor_points, ohlcv_candles, "minor")

    # Experimental pivot-triplet BoS detector (bullish Scenario 1 only).
    # Isolated from production pipeline — result is appended separately.
    experimental_bos = detect_experimental_bos_bullish(result.minor_points, ohlcv_candles)

    # Experimental geometric market bias engine (label-free, main pivots only).
    # Returns a populated result for every computation — INSUFFICIENT_DATA,
    # NON_ALTERNATING, and EQUALITY states are valid responses, not failures.
    latest_close = ohlcv_candles[-1].close if ohlcv_candles else 0.0
    market_bias_result = compute_market_bias(
        major_pivots=[p.price for p in result.main_points],
        current_close=latest_close,
    )

    # ── Build lineage ──────────────────────────────────────────────────────────
    structure_lineage = ToolLineageResponse(**_ENGINE_METADATA[engine_id])

    bos_lineage = DerivedToolLineageResponse(
        tool_domain="structure_event",
        tool_id="bos_detection",
        parent_tool_domain="market_structure",
        parent_engine_id=engine_id,
    )

    choch_lineage = DerivedToolLineageResponse(
        tool_domain="structure_event",
        tool_id="choch_detection",
        parent_tool_domain="market_structure",
        parent_engine_id=engine_id,
    )

    # ── Guard 2: derived tool parent must match the structure engine ───────────
    assert bos_lineage.parent_engine_id == structure_lineage.tool_id, (
        f"LINEAGE ERROR: bos_lineage.parent_engine_id={bos_lineage.parent_engine_id!r} "
        f"!= structure_lineage.tool_id={structure_lineage.tool_id!r}"
    )
    assert choch_lineage.parent_engine_id == structure_lineage.tool_id, (
        f"LINEAGE ERROR: choch_lineage.parent_engine_id={choch_lineage.parent_engine_id!r} "
        f"!= structure_lineage.tool_id={structure_lineage.tool_id!r}"
    )

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
        experimental_bos_events=[_map_experimental_bos(ev) for ev in experimental_bos],
        market_bias=_map_market_bias(market_bias_result),
        structure_lineage=structure_lineage,
        bos_lineage=bos_lineage,
        choch_lineage=choch_lineage,
    )

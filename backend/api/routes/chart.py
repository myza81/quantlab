"""
Chart indicator API routes — Chart-UX-3B.

Endpoints:
    GET  /chart/indicators         — list all chart-visible tools (intentionally public)
    POST /chart/indicator-artifact — compute an indicator for one chart instance (auth required)

The indicator list endpoint is intentionally public (read-only metadata, no computation).
The artifact endpoint requires require_active_subscription — it triggers provider fetch
and tool computation.

Architecture:
    - Routes are thin; all logic lives in chart_indicator_service.py
    - No strategy draft required; no composition-run dependency
    - Reuses get_tool_registry() and get_provider_factory() from dependencies.py
    - OHLCVService injected via get_ohlcv_service() from dependencies.py
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import (
    get_ohlcv_service,
    get_provider_factory,
    get_tool_registry,
)
from backend.api.schemas.chart import (
    ChartIndicatorsListResponse,
    IndicatorArtifactRequest,
    IndicatorArtifactResponse,
    MarketStructureRequest,
    MarketStructureResponse,
)
from backend.api.services.chart_indicator_service import (
    IndicatorArtifactError,
    IndicatorParameterError,
    ToolNotChartVisibleError,
    compute_indicator_artifact,
    list_chart_indicators,
)
from backend.api.services.market_structure_service import (
    compute_market_structure_from_candles,
)
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.data_providers.provider_factory import ProviderAdapterFactory
from backend.services.ohlcv_service import OHLCVService
from backend.tools.registry import ToolNotFoundError, ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chart", tags=["chart"])


@router.get("/indicators", response_model=ChartIndicatorsListResponse)
def get_chart_indicators(
    registry: ToolRegistry = Depends(get_tool_registry),
) -> ChartIndicatorsListResponse:
    """
    List all chart-visible indicator tools with full display and parameter metadata.

    Intentionally public — returns read-only registry metadata, no computation.
    Powers the frontend indicator picker without requiring authentication.
    """
    return list_chart_indicators(registry)


@router.post("/indicator-artifact", response_model=IndicatorArtifactResponse)
def post_indicator_artifact(
    request: IndicatorArtifactRequest,
    registry: ToolRegistry = Depends(get_tool_registry),
    factory: ProviderAdapterFactory = Depends(get_provider_factory),
    ohlcv_service: OHLCVService = Depends(get_ohlcv_service),
    current_user: User = Depends(require_active_subscription),
) -> IndicatorArtifactResponse:
    """
    Compute an indicator artifact for one chart instance.

    Fetches the required OHLCV data via the provider pipeline and computes the
    indicator using the same backend tool dispatcher used by Strategy Builder and
    backtesting.  Returns timestamp-aligned series with null values for warmup bars.

    The instance_id from the request is echoed in the response so the frontend can
    route each artifact response to the correct chart indicator instance.
    """
    try:
        return compute_indicator_artifact(
            tool_id=request.tool_id,
            instance_id=request.instance_id,
            symbol=request.symbol,
            provider=request.provider,
            timeframe=request.timeframe,
            date_range_start=request.date_range_start,
            date_range_end=request.date_range_end,
            parameters=request.parameters,
            asset_class=request.asset_class,
            exchange=request.exchange,
            credential_id=request.credential_id,
            user_id=current_user.user_id,
            registry=registry,
            factory=factory,
            ohlcv_service=ohlcv_service,
        )
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolNotChartVisibleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IndicatorParameterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IndicatorArtifactError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/market-structure", response_model=MarketStructureResponse)
def post_market_structure(
    request: MarketStructureRequest,
    current_user: User = Depends(require_active_subscription),
) -> MarketStructureResponse:
    """
    Compute minor and main market structure from a provided OHLCV candle list.

    The frontend sends its already-loaded candles directly so no provider
    re-fetch is needed.  Candles must be in chronological order; bar_index
    in the response maps to the input index (0 = first candle).

    Returns StructureResult with minor/main points, legs, and debug events
    for visual verification on the chart.  No trading signals are generated.
    """
    if len(request.candles) < 2:
        return MarketStructureResponse(
            minor_points=[], minor_legs=[],
            main_points=[], main_legs=[],
            debug_events=[],
        )
    return compute_market_structure_from_candles(request)

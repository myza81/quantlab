"""
Chart indicator service — Chart-UX-3B / Chart-UX-3B.1.

Responsibilities:
    list_chart_indicators()      — enumerate tools with visible_on_chart=True
    compute_indicator_artifact() — fetch OHLCV and compute one tool instance

Architecture (Chart-UX-3B.1):
    All chart metadata is sourced directly from ToolMetadata in the registry.
    No static metadata dictionary.  Adding a new chart-visible tool requires
    only tool registration — no changes to this service.

    The previous _CHART_DISPLAY_METADATA static dict has been eliminated.
    All chart rendering and discovery metadata now lives in:
        ToolMetadata.chart_pane
        ToolMetadata.chart_render_type
        ToolMetadata.chart_series_kind
        ToolMetadata.chart_category
        ToolMetadata.chart_subcategory
        ToolMetadata.chart_search_keywords
        ToolMetadata.chart_display_order
        ToolMetadata.chart_editable_parameters
        ToolMetadata.chart_output_series  (ChartSeriesSpec instances)

    Validation at ToolMetadata construction time (model_validator) guarantees
    that any visible_on_chart=True tool has complete chart metadata.

Computation pipeline:
    - Reuses existing _TOOL_DISPATCHERS via compute_tool_outputs_for_history()
    - Reuses existing OHLCVService and ProviderAdapterFactory
    - No duplicated indicator formulas
    - No Strategy Builder dependency
    - No strategy draft required
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from backend.api.schemas.chart import (
    ChartIndicatorMetadata,
    ChartIndicatorParameterSpec,
    ChartIndicatorSeriesSpec,
    ChartIndicatorsListResponse,
    IndicatorArtifactResponse,
    IndicatorArtifactSeries,
    IndicatorSeriesPoint,
)
from backend.data.models.dataset import DatasetIdentity
from backend.data.models.fetch_identity import build_fetch_identity
from backend.data.models.instrument import AdjustmentMode, Instrument
from backend.data_providers.base import ProviderFetchError
from backend.data_providers.provider_factory import (
    ProviderAdapterFactory,
    ProviderBuildError,
    UnknownProviderError,
)
from backend.services.ohlcv_service import OHLCVIngestionError, OHLCVService
from backend.tools import ToolRegistry
from backend.tools.computation_models import ToolComputationResult
from backend.tools.configuration import ToolConfiguration
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
    compute_tool_outputs_for_history,
)
from backend.tools.models import ToolCategory, ToolMetadata
from backend.tools.registry import ToolNotFoundError
from backend.tools.toolset import StrategyToolSet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ToolNotChartVisibleError(Exception):
    """Raised when the requested tool is not available as a chart indicator."""


class IndicatorArtifactError(Exception):
    """Raised when OHLCV fetch or provider setup fails during artifact computation."""


class IndicatorParameterError(Exception):
    """Raised when the supplied parameters are invalid for the requested tool."""


# ---------------------------------------------------------------------------
# GET /chart/indicators — fully registry-driven listing
# ---------------------------------------------------------------------------

def list_chart_indicators(registry: ToolRegistry) -> ChartIndicatorsListResponse:
    """
    Return metadata for all chart-visible tools in the registry.

    A tool is chart-visible when:
      - metadata.visible_on_chart is True
      - metadata.category is ToolCategory.indicator

    All chart rendering and discovery metadata is read directly from ToolMetadata.
    The ToolMetadata model_validator guarantees completeness for any visible tool,
    so no secondary metadata source is needed.
    """
    indicators: list[ChartIndicatorMetadata] = []

    for tool_id in registry.list_tools():
        metadata = registry.get(tool_id)

        if not metadata.visible_on_chart:
            continue
        if metadata.category != ToolCategory.indicator:
            continue

        # chart_output_series and other chart fields are guaranteed non-empty
        # by ToolMetadata._validate_chart_metadata — no guard needed here.

        param_responses = [
            ChartIndicatorParameterSpec(
                name=p.name,
                description=p.description,
                type_label=p.type_label,
                required=p.required,
                default=p.default,
                min_value=p.min_value,
                max_value=p.max_value,
            )
            for p in metadata.parameters
        ]

        series_specs = [
            ChartIndicatorSeriesSpec(
                series_id=s.series_id,
                label=s.label,
                pane=s.pane,
                render_type=s.render_type,
                default_color=s.default_color,
            )
            for s in metadata.chart_output_series
        ]

        indicators.append(ChartIndicatorMetadata(
            tool_id=tool_id,
            display_name=metadata.name,
            short_name=metadata.short_name,
            description=metadata.description,
            category=metadata.chart_category,      # type: ignore[arg-type]
            chart_pane=metadata.chart_pane,        # type: ignore[arg-type]
            render_type=metadata.chart_render_type,  # type: ignore[arg-type]
            series_kind=metadata.chart_series_kind,  # type: ignore[arg-type]
            output_series=series_specs,
            editable_parameters=list(metadata.chart_editable_parameters),
            parameters=param_responses,
            visible_on_chart=metadata.visible_on_chart,
        ))

    # Stable ordering: chart_category → tool_id
    indicators.sort(key=lambda m: (m.category, m.tool_id))

    return ChartIndicatorsListResponse(indicators=indicators)


# ---------------------------------------------------------------------------
# POST /chart/indicator-artifact — compute one tool instance
# ---------------------------------------------------------------------------

def compute_indicator_artifact(
    *,
    tool_id: str,
    instance_id: str,
    symbol: str,
    provider: str,
    timeframe: str,
    date_range_start: datetime,
    date_range_end: datetime,
    parameters: dict[str, Any],
    asset_class: str = "equity",
    exchange: str = "",
    credential_id: Optional[str] = None,
    user_id: Optional[str] = None,
    registry: ToolRegistry,
    factory: ProviderAdapterFactory,
    ohlcv_service: OHLCVService,
) -> IndicatorArtifactResponse:
    """
    Fetch OHLCV data and compute an indicator artifact for one tool instance.

    All chart rendering metadata is sourced from ToolMetadata in the registry.
    No static metadata dictionary is consulted.

    Flow:
        1. Validate tool exists and is chart-visible (gates via ToolMetadata fields)
        2. Resolve API key for vault-backed providers
        3. Build provider adapter and fetch normalized OHLCV candles
        4. Convert candles → ToolComputationBarInput list
        5. Dispatch to existing _TOOL_DISPATCHERS via compute_tool_outputs_for_history
        6. Build timestamp-aligned artifact response (null for warmup bars)

    Raises:
        ToolNotFoundError:        tool_id not in registry.
        ToolNotChartVisibleError: tool is not available as a chart indicator.
        IndicatorParameterError:  parameters are invalid for the tool.
        IndicatorArtifactError:   OHLCV fetch or provider setup failed.
    """
    # 1. Validate tool existence and chart visibility
    metadata = registry.get(tool_id)  # raises ToolNotFoundError if absent

    if not metadata.visible_on_chart or metadata.category != ToolCategory.indicator:
        raise ToolNotChartVisibleError(
            f"Tool '{tool_id}' is not available as a chart indicator. "
            f"Only tools with visible_on_chart=True and category=indicator "
            f"can be used in the chart indicator panel."
        )

    # chart_output_series completeness is guaranteed by ToolMetadata validation

    # 2. Resolve API key for vault-backed providers (e.g. Polygon)
    api_key: Optional[str] = None
    if credential_id:
        from backend.api.services.market_data_service import (
            MarketDataError,
            _resolve_provider_api_key,
        )
        try:
            api_key = _resolve_provider_api_key(
                provider=provider,
                credential_id=credential_id,
                user_id=user_id,
            )
        except MarketDataError as exc:
            raise IndicatorArtifactError(str(exc)) from exc

    # 3. Build adapter and fetch OHLCV candles
    effective_exchange = exchange.strip() or "unknown"
    start = _ensure_utc(date_range_start)
    end = _ensure_utc(date_range_end)

    try:
        adapter = factory.build(
            provider,
            symbol=symbol,
            asset_class=asset_class,
            venue=effective_exchange,
            timeframe=timeframe,
            adjustment_mode="adjusted",
            api_key=api_key,
        )
    except UnknownProviderError as exc:
        raise IndicatorArtifactError(f"Provider '{provider}' is not registered.") from exc
    except ProviderBuildError as exc:
        raise IndicatorArtifactError(f"Could not build provider adapter: {exc}") from exc

    instrument = Instrument(
        symbol=symbol,
        asset_class=asset_class,
        exchange=effective_exchange,
        currency="USD",
    )
    identity = DatasetIdentity(
        instrument=instrument,
        provider=provider,
        timeframe=timeframe,
        adjustment_mode=AdjustmentMode.ADJUSTED,
    )
    fetch_identity = build_fetch_identity(
        provider=provider,
        symbol=symbol,
        asset_class=asset_class,
        exchange=effective_exchange,
        timeframe=timeframe,
        start=start,
        end=end,
        adjustment_mode=AdjustmentMode.ADJUSTED,
        dataset_id=identity.dataset_id,
    )

    try:
        candles = ohlcv_service.get_ohlcv(
            identity, start, end, adapter,
            fetch_fingerprint=fetch_identity.fingerprint,
        )
    except ProviderFetchError as exc:
        raise IndicatorArtifactError(f"Provider fetch failed: {exc}") from exc
    except OHLCVIngestionError as exc:
        raise IndicatorArtifactError(f"Data ingestion failed: {exc}") from exc

    if not candles:
        return _empty_artifact(
            tool_id=tool_id,
            instance_id=instance_id,
            parameters=parameters,
            metadata=metadata,
        )

    # 4. Convert NormalizedOHLCV → ToolComputationBarInput (sorted by timestamp)
    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    bars: list[ToolComputationBarInput] = [
        ToolComputationBarInput(
            bar_index=i,
            timestamp=c.timestamp,
            price_fields={
                "open":   c.open,
                "high":   c.high,
                "low":    c.low,
                "close":  c.close,
                "volume": c.volume,
            },
        )
        for i, c in enumerate(sorted_candles)
    ]

    # 5. Create single-tool toolset and dispatch to existing computation pipeline
    tool_config = ToolConfiguration(
        instance_id=instance_id,
        tool_id=tool_id,
        parameters=parameters,
    )
    toolset = StrategyToolSet(
        toolset_id=f"chart_{instance_id}",
        tools=(tool_config,),
    )

    try:
        result: ToolComputationResult = compute_tool_outputs_for_history(
            toolset, bars, registry,
        )
    except ToolComputationError as exc:
        err_msg = str(exc)
        if "configuration invalid" in err_msg or "parameter" in err_msg.lower():
            raise IndicatorParameterError(err_msg) from exc
        raise IndicatorArtifactError(f"Indicator computation failed: {exc}") from exc

    # 6. Build timestamp-aligned artifact response
    return _build_artifact_response(
        tool_id=tool_id,
        instance_id=instance_id,
        parameters=parameters,
        metadata=metadata,
        bars=bars,
        result=result,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime, treating naive datetimes as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _empty_artifact(
    *,
    tool_id: str,
    instance_id: str,
    parameters: dict[str, Any],
    metadata: ToolMetadata,
) -> IndicatorArtifactResponse:
    """Return an artifact with empty series when no candles are available."""
    series = [
        IndicatorArtifactSeries(
            series_id=s.series_id,
            label=s.label,
            pane=s.pane,
            render_type=s.render_type,
            default_color=s.default_color,
            values=[],
        )
        for s in metadata.chart_output_series
    ]
    return IndicatorArtifactResponse(
        tool_id=tool_id,
        instance_id=instance_id,
        display_name=metadata.name,
        pane=metadata.chart_pane,          # type: ignore[arg-type]
        render_type=metadata.chart_render_type,  # type: ignore[arg-type]
        parameters=parameters,
        series=series,
        warmup_bars=0,
        diagnostics="No candles available for the requested date range.",
    )


def _build_artifact_response(
    *,
    tool_id: str,
    instance_id: str,
    parameters: dict[str, Any],
    metadata: ToolMetadata,
    bars: list[ToolComputationBarInput],
    result: ToolComputationResult,
) -> IndicatorArtifactResponse:
    """
    Convert ToolComputationResult into a timestamp-aligned IndicatorArtifactResponse.

    All rendering metadata (pane, render_type, series specs) is read from ToolMetadata.
    For each output series: emits null for warmup bars, float for computed bars.
    warmup_bars reports the max warmup across all series.
    """
    # Build map: output_name → {bar_index: value}
    series_map: dict[str, dict[int, float]] = {}
    max_warmup = 0

    for ts in result.series:
        series_map[ts.output_name] = {p.bar_index: p.value for p in ts.points}
        if ts.warmup_bar_count > max_warmup:
            max_warmup = ts.warmup_bar_count

    # Build artifact series using chart_output_series order from metadata
    artifact_series: list[IndicatorArtifactSeries] = []

    for spec in metadata.chart_output_series:
        values_map = series_map.get(spec.series_id, {})

        # Fallback: if no computation produced this series (e.g. the "volume"
        # histogram on volume_ma which is visualization-only, not a strategy
        # output), read directly from bar price_fields so the chart still renders.
        if not values_map and bars:
            values_map = {
                bar.bar_index: bar.price_fields[spec.series_id]
                for bar in bars
                if spec.series_id in bar.price_fields
            }

        points = [
            IndicatorSeriesPoint(
                timestamp=(
                    bar.timestamp.astimezone(timezone.utc).isoformat()
                    if bar.timestamp
                    else ""
                ),
                value=values_map.get(bar.bar_index),  # None for warmup bars
            )
            for bar in bars
        ]

        artifact_series.append(IndicatorArtifactSeries(
            series_id=spec.series_id,
            label=spec.label,
            pane=spec.pane,
            render_type=spec.render_type,
            default_color=spec.default_color,
            values=points,
        ))

    logger.info(
        "chart_indicator_service: computed '%s' instance='%s' bars=%d warmup=%d series=%d",
        tool_id, instance_id, len(bars), max_warmup, len(artifact_series),
    )

    return IndicatorArtifactResponse(
        tool_id=tool_id,
        instance_id=instance_id,
        display_name=metadata.name,
        pane=metadata.chart_pane,            # type: ignore[arg-type]
        render_type=metadata.chart_render_type,  # type: ignore[arg-type]
        parameters=parameters,
        series=artifact_series,
        warmup_bars=max_warmup,
    )

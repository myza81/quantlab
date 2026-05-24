"""
Strategy runs API route — thin layer delegating to strategy_run_service.

Endpoints:
    POST /strategy-runs/run               — execute a file-based strategy over a historical window
    POST /strategy-runs/run-composition   — run a saved Composer draft against chart bars
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas.composition_run import CompositionRunRequest, CompositionRunResponse
from backend.api.schemas.strategy_runs import StrategyRunRequest, StrategyRunResponse
from backend.api.services.composition_run_service import CompositionRunError, run_composition
from backend.api.services.strategy_run_service import (
    StrategyNotFoundError,
    StrategyRunError,
    UnsupportedProviderError,
    run_strategy,
)
from backend.core.config import settings
from backend.strategy_registry.draft_repository import DraftRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy-runs", tags=["strategy-runs"])

_DEFAULT_DRAFT_STORAGE = Path("storage/strategy_drafts")


def get_draft_repository() -> DraftRepository:
    return DraftRepository(_DEFAULT_DRAFT_STORAGE)


def get_storage_path() -> Path:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return settings.storage_base_path


def get_strategies_path() -> Path:
    """Dependency — overridable in tests via app.dependency_overrides."""
    return settings.strategies_base_path


@router.post("/run", response_model=StrategyRunResponse)
def run_strategy_endpoint(
    request: StrategyRunRequest,
    storage_path: Path = Depends(get_storage_path),
    strategies_path: Path = Depends(get_strategies_path),
) -> StrategyRunResponse:
    try:
        return run_strategy(
            request,
            storage_path=storage_path,
            strategies_path=strategies_path,
        )
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StrategyRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run-composition", response_model=CompositionRunResponse)
def run_composition_endpoint(
    request: CompositionRunRequest,
    repository: DraftRepository = Depends(get_draft_repository),
) -> CompositionRunResponse:
    """
    Run a saved Composer draft against OHLCV bars already loaded by the Chart page.

    Returns entry/exit signals and computed indicator series for overlay rendering.
    """
    try:
        return run_composition(
            draft_id=request.draft_id,
            symbol=request.symbol,
            timeframe=request.timeframe,
            bars=request.bars,
            repository=repository,
        )
    except CompositionRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

"""
Strategy runs API route — thin layer delegating to strategy_run_service.

Endpoint:
    POST /strategy-runs/run  — execute a strategy over a historical OHLCV window
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas.strategy_runs import StrategyRunRequest, StrategyRunResponse
from backend.api.services.strategy_run_service import (
    StrategyNotFoundError,
    StrategyRunError,
    UnsupportedProviderError,
    run_strategy,
)
from backend.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy-runs", tags=["strategy-runs"])


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

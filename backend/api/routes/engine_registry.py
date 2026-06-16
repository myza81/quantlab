"""
Research Engine Registry API — thin read-only route layer.

Endpoints:
    GET /research-engines                    — list all engine version metadata
    GET /research-engines/{technical_id}     — detail for one engine version

Intentionally public (no auth required) — returns read-only metadata only.
No engine selection, no mutation, no pipeline configuration.
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas.engine_registry import EngineListResponse, EngineRecordResponse
from backend.api.services.engine_registry_service import (
    EngineNotFoundError,
    EngineRecord,
    EngineRegistryError,
    get_all_engines,
    get_engine_by_id,
)

router = APIRouter(prefix="/research-engines", tags=["research-engines"])


def _to_response(record: EngineRecord) -> EngineRecordResponse:
    return EngineRecordResponse.model_validate(record.model_dump())


def get_registry() -> list[EngineRecord]:
    """Dependency — overridable in tests via app.dependency_overrides."""
    try:
        return get_all_engines()
    except EngineRegistryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("", response_model=EngineListResponse)
def list_engines(
    engines: list[EngineRecord] = Depends(get_registry),
) -> EngineListResponse:
    return EngineListResponse(
        engines=[_to_response(e) for e in engines],
        count=len(engines),
    )


@router.get("/{technical_id}", response_model=EngineRecordResponse)
def get_engine(
    technical_id: str,
    engines: list[EngineRecord] = Depends(get_registry),
) -> EngineRecordResponse:
    for engine in engines:
        if engine.technical_id == technical_id:
            return _to_response(engine)
    raise HTTPException(
        status_code=404,
        detail=f"Engine version not found: '{technical_id}'",
    )

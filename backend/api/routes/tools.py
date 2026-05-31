"""
Tools API route — thin layer delegating to tool_service.

Endpoints:
    GET  /tools                    — discover registered tool metadata (intentionally public; read-only metadata)
    POST /tools/validate-toolset   — validate a StrategyToolSet against the registry (requires auth; performs computation)
"""
from fastapi import APIRouter, Depends

from backend.api.schemas.tools import ToolListResponse, ToolSetValidationResponse
from backend.api.services.tool_service import list_tools, validate_toolset
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.tools import StrategyToolSet, ToolRegistry, create_default_registry

router = APIRouter(prefix="/tools", tags=["tools"])


def get_tool_registry() -> ToolRegistry:
    """Dependency returning the default read-only tool registry."""
    return create_default_registry()


@router.get("", response_model=ToolListResponse)
def get_tools(
    registry: ToolRegistry = Depends(get_tool_registry),
) -> ToolListResponse:
    # Intentionally public — returns read-only registry metadata, no computation.
    return list_tools(registry)


@router.post("/validate-toolset", response_model=ToolSetValidationResponse)
def post_validate_toolset(
    toolset: StrategyToolSet,
    registry: ToolRegistry = Depends(get_tool_registry),
    current_user: User = Depends(require_active_subscription),
) -> ToolSetValidationResponse:
    return validate_toolset(toolset, registry)

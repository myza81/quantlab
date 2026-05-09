from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class StrategyLifecycleStage(str, Enum):
    IDEA = "idea"
    RESEARCH = "research"
    PROTOTYPE = "prototype"
    VALIDATED = "validated"
    BACKTESTED = "backtested"
    FORWARD_TESTED = "forward_tested"
    PAPER_TRADED = "paper_traded"
    APPROVED_FOR_LIVE = "approved_for_live"
    RETIRED = "retired"


class RuntimeMode(str, Enum):
    RESEARCH = "research"
    BACKTESTING = "backtesting"
    FORWARD_TESTING = "forward_testing"
    PAPER_TRADING = "paper_trading"
    LIVE_TRADING = "live_trading"


class StrategyManifest(BaseModel):
    """
    Parsed representation of a strategy's strategy.yaml per STRATEGY_CONTRACT.md.

    Required fields: strategy_id, version, lifecycle_stage.
    Extra fields in the YAML are silently ignored to allow strategy-local extensions.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    strategy_id: str
    version: str
    lifecycle_stage: StrategyLifecycleStage

    # Optional descriptive fields
    name: Optional[str] = None
    description: Optional[str] = None

    # Market / timeframe compatibility
    supported_assets: list[str] = []
    supported_timeframes: list[str] = []

    # Feature and runtime declarations
    feature_dependencies: list[str] = []
    runtime_compatibility: list[RuntimeMode] = []

    # Warmup requirement in bars
    warmup_bars: int = 0

    @field_validator("strategy_id")
    @classmethod
    def _strategy_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("strategy_id must not be empty or whitespace")
        return v

    @field_validator("version")
    @classmethod
    def _version_not_empty(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("version must not be empty or whitespace")
        return v

    @field_validator("lifecycle_stage", mode="before")
    @classmethod
    def _normalise_lifecycle_stage(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().replace("-", "_")
        return v

    @field_validator("warmup_bars")
    @classmethod
    def _warmup_bars_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("warmup_bars must be >= 0")
        return v

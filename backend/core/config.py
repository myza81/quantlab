from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root derived from this file's location: backend/core/config.py → parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "QuantLab"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    # Canonical Parquet storage root for normalized OHLCV datasets (DATA_CONTRACT.md)
    storage_base_path: Path = Path("datasets/normalized")

    # Root directory containing strategy packages — resolved from repo root so it is
    # launch-directory-independent. Override via STRATEGIES_BASE_PATH env var if needed.
    strategies_base_path: Path = _REPO_ROOT / "strategies"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)

        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False

        # Non-boolean environment values such as "release" must not break startup.
        return False


settings = Settings()

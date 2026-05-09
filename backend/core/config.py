from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "QuantLab"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    # Canonical Parquet storage root for normalized OHLCV datasets (DATA_CONTRACT.md)
    storage_base_path: Path = Path("datasets/normalized")

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

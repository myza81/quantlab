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

    # Auth — secret must be overridden via AUTH_SECRET_KEY env var in production.
    # Default is safe only for development/testing; never commit a real key here.
    auth_secret_key: str = "dev-only-insecure-secret-change-in-production"
    auth_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # JSON file path for user persistence (relative to repo root or absolute).
    users_file_path: Path = _REPO_ROOT / "data" / "users.json"

    # Vault — secret key used to encrypt stored provider credentials.
    # Must be overridden via VAULT_ENCRYPTION_KEY env var in production.
    # Default is safe only for development/testing; never commit a real key here.
    vault_encryption_key: str = "dev-only-insecure-vault-key-change-in-production"

    # JSON file path for provider credential storage.
    credentials_file_path: Path = _REPO_ROOT / "data" / "credentials.json"

    # Admin bootstrap: if set, the first registration using this email is auto-promoted
    # to admin role with active subscription. Set via ADMIN_BOOTSTRAP_EMAIL env var.
    # Leave empty to disable bootstrap (production default).
    admin_bootstrap_email: str = ""

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

"""
Research Engine Registry service — Phase 1b.

Loads and validates the static YAML engine registry.
Source of truth: backend/config/research_engines.yaml

This service is read-only metadata visibility only.
It does not select, configure, or control which engine runs at runtime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ValidationError

_REGISTRY_PATH = Path(__file__).parent.parent.parent / "config" / "research_engines.yaml"


class EngineRegistryError(Exception):
    """Raised when the registry file cannot be loaded or is structurally invalid."""


class EngineNotFoundError(Exception):
    """Raised when a requested engine technical_id does not exist in the registry."""


class ChangeLogEntry(BaseModel):
    date: str
    commit: Optional[str] = None
    description: str


class ContractSpec(BaseModel):
    type: str
    fields: list[str]
    notes: Optional[str] = None


class EngineRecord(BaseModel):
    human_name: str
    technical_id: str
    engine_type: str
    lifecycle_status: str
    created_date: Optional[str] = None
    frozen_date: Optional[str] = None
    retired_date: Optional[str] = None
    rulebook_status: str
    purpose: str
    key_characteristics: list[str]
    input_contract: ContractSpec
    output_contract: ContractSpec
    dependencies: list[str]
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    validation_status: str
    notes: Optional[str] = None
    change_log: list[ChangeLogEntry]


def load_registry(registry_path: Path = _REGISTRY_PATH) -> list[EngineRecord]:
    """
    Load and validate the engine registry from the given YAML path.

    Raises EngineRegistryError if the file is missing, unreadable, or fails
    schema validation.  Each record is validated individually so the error
    message names the offending technical_id where possible.
    """
    if not registry_path.exists():
        raise EngineRegistryError(
            f"Engine registry file not found: {registry_path}"
        )

    try:
        raw: Any = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EngineRegistryError(f"Engine registry YAML parse error: {exc}") from exc

    if not isinstance(raw, dict) or "engines" not in raw:
        raise EngineRegistryError(
            "Engine registry file must contain a top-level 'engines' list."
        )

    raw_engines = raw["engines"]
    if not isinstance(raw_engines, list):
        raise EngineRegistryError("'engines' in registry must be a list.")

    records: list[EngineRecord] = []
    for i, entry in enumerate(raw_engines):
        technical_id = entry.get("technical_id", f"<index {i}>") if isinstance(entry, dict) else f"<index {i}>"
        try:
            records.append(EngineRecord.model_validate(entry))
        except ValidationError as exc:
            raise EngineRegistryError(
                f"Engine record '{technical_id}' failed schema validation: {exc}"
            ) from exc

    return records


def get_all_engines(registry_path: Path = _REGISTRY_PATH) -> list[EngineRecord]:
    """Return all engine records from the registry."""
    return load_registry(registry_path)


def get_engine_by_id(
    technical_id: str,
    registry_path: Path = _REGISTRY_PATH,
) -> EngineRecord:
    """
    Return a single engine record by technical_id.

    Raises EngineNotFoundError if no record matches.
    """
    for record in load_registry(registry_path):
        if record.technical_id == technical_id:
            return record
    raise EngineNotFoundError(
        f"Engine version not found: '{technical_id}'"
    )

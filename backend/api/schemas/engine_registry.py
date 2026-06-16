"""
API schemas for the Research Engine Registry endpoints.

Read-only metadata visibility only.
No engine selection, no pipeline configuration, no mutation.
"""
from typing import Optional

from pydantic import BaseModel


class ChangeLogEntry(BaseModel):
    date: str
    commit: Optional[str] = None
    description: str


class ContractSpec(BaseModel):
    type: str
    fields: list[str]
    notes: Optional[str] = None


class EngineRecordResponse(BaseModel):
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


class EngineListResponse(BaseModel):
    engines: list[EngineRecordResponse]
    count: int

"""
Dataset fetch identity — traceability model for OHLCV fetch requests.

Provides deterministic fingerprinting for every OHLCV fetch so that results
can be audited, reproduced, and traced back to a specific provider, symbol,
timeframe, and date range.

Architecture note:
    This module belongs to the data layer. It must not import from provider
    adapters, API routes, or execution layers. It expresses a pure domain
    contract about *what was requested*, not how it was fulfilled.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator

from backend.data.models.instrument import AdjustmentMode

# Bump when the canonical fingerprint format changes.
FETCH_IDENTITY_SCHEMA_VERSION = "1"


class DatasetFetchParameters(BaseModel):
    """
    Normalized, frozen parameters identifying a single OHLCV fetch request.

    All string fields are stored as-supplied (normalization is the caller's
    responsibility or is enforced per field).  Datetimes must be
    timezone-aware; naive datetimes are rejected at construction time so
    that fingerprints are always unambiguous.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    symbol: str
    asset_class: str
    exchange: str
    timeframe: str
    start: datetime
    end: datetime
    adjustment_mode: AdjustmentMode

    @field_validator("provider", "symbol", "asset_class", "exchange", "timeframe")
    @classmethod
    def _must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace")
        return stripped

    @field_validator("start", "end")
    @classmethod
    def _must_be_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware (UTC required)")
        return v


def compute_fetch_fingerprint(params: DatasetFetchParameters) -> str:
    """
    Return a deterministic SHA-256 hex fingerprint for a fetch request.

    Canonical format (pipe-delimited, all values lowercased):
        provider|symbol|asset_class|exchange|timeframe|start_utc|end_utc|adjustment_mode

    Timestamps use ISO 8601 UTC: ``%Y-%m-%dT%H:%M:%S+00:00``.
    The fingerprint is stable across processes and platforms for identical
    inputs — it does not depend on dict ordering, hash seed, or runtime state.
    """
    start_utc = params.start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    end_utc = params.end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    canonical = "|".join([
        params.provider.lower(),
        params.symbol.lower(),
        params.asset_class.lower(),
        params.exchange.lower(),
        params.timeframe.lower(),
        start_utc,
        end_utc,
        params.adjustment_mode.value.lower(),
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DatasetFetchIdentity(BaseModel):
    """
    Complete traceability record for a single OHLCV fetch result.

    Bundles the normalized request parameters with a deterministic fingerprint
    and the static dataset identity key so that any fetch result can be fully
    reproduced and audited.
    """

    model_config = ConfigDict(frozen=True)

    parameters: DatasetFetchParameters
    fingerprint: str
    dataset_id: str
    schema_version: str = FETCH_IDENTITY_SCHEMA_VERSION


def build_fetch_identity(
    *,
    provider: str,
    symbol: str,
    asset_class: str,
    exchange: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    adjustment_mode: AdjustmentMode,
    dataset_id: str,
) -> DatasetFetchIdentity:
    """
    Build a complete DatasetFetchIdentity from raw fetch parameters.

    Constructs and validates DatasetFetchParameters, computes the
    deterministic fingerprint, then assembles the identity record.

    Args:
        provider:        Registered provider name, e.g. "yahoo".
        symbol:          Instrument symbol, e.g. "AAPL".
        asset_class:     e.g. "equity", "crypto".
        exchange:        Exchange/venue, e.g. "NASDAQ".
        timeframe:       Canonical timeframe string, e.g. "1d".
        start:           UTC-aware start datetime (inclusive).
        end:             UTC-aware end datetime (inclusive).
        adjustment_mode: AdjustmentMode enum value.
        dataset_id:      DatasetIdentity.dataset_id from the storage layer.

    Returns:
        DatasetFetchIdentity with deterministic fingerprint and schema version.
    """
    params = DatasetFetchParameters(
        provider=provider,
        symbol=symbol,
        asset_class=asset_class,
        exchange=exchange,
        timeframe=timeframe,
        start=start,
        end=end,
        adjustment_mode=adjustment_mode,
    )
    fingerprint = compute_fetch_fingerprint(params)
    return DatasetFetchIdentity(
        parameters=params,
        fingerprint=fingerprint,
        dataset_id=dataset_id,
        schema_version=FETCH_IDENTITY_SCHEMA_VERSION,
    )

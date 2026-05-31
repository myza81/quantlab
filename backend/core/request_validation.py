"""
Request validation utilities for provider and dataset access.

Provides reusable validators that API routes and services can call to reject
unsafe or malformed inputs before they reach the domain layer.  All raised
errors are ValueError with safe, user-facing messages (no internal paths or
credential names).

Usage:

    from backend.core.request_validation import validate_date_range, validate_provider_type

    validate_date_range(start, end)                    # raises ValueError if start >= end
    validate_provider_type(provider_type, {"csv", "parquet"})  # raises ValueError if unknown
    validate_uuid_id(run_id, "run_id")                 # raises ValueError if not a valid UUID
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import AbstractSet

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Catalog provider types — extend when new local provider types are added
# ---------------------------------------------------------------------------

ALLOWED_CATALOG_PROVIDER_TYPES: frozenset[str] = frozenset({"csv", "parquet"})


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_date_range(start: datetime, end: datetime) -> None:
    """
    Assert that start precedes end.

    Raises:
        ValueError: if start >= end, with a safe message.
    """
    if start >= end:
        raise ValueError(
            f"start must be before end; got start={start.isoformat()!r} "
            f"end={end.isoformat()!r}"
        )


def validate_provider_type(
    provider_type: str,
    allowed: AbstractSet[str] = ALLOWED_CATALOG_PROVIDER_TYPES,
) -> None:
    """
    Assert that provider_type is one of the allowed values.

    Comparison is case-insensitive; the caller is expected to normalise the
    value (lower-case) before storage.

    Raises:
        ValueError: unknown provider_type, listing the allowed values.
    """
    if provider_type.strip().lower() not in {p.lower() for p in allowed}:
        allowed_str = ", ".join(sorted(allowed))
        raise ValueError(
            f"Unknown provider_type {provider_type!r}. "
            f"Allowed values: {allowed_str}"
        )


def validate_symbol(symbol: str) -> None:
    """
    Assert that symbol is a non-empty, printable string.

    Raises:
        ValueError: blank or whitespace-only symbol.
    """
    if not symbol or not symbol.strip():
        raise ValueError("symbol must not be empty or whitespace")


def validate_bar_count(bar_count: int, max_bars: int) -> None:
    """
    Assert that a simulation/backtest bar payload does not exceed the configured limit.

    Called before any computation begins so oversized payloads are rejected
    immediately without allocating computation resources.

    Raises:
        ValueError: if bar_count exceeds max_bars, with a safe message showing
                    both counts (no internal paths, no user data).
    """
    if bar_count > max_bars:
        raise ValueError(
            f"bar count {bar_count:,} exceeds the maximum allowed "
            f"{max_bars:,} bars per request"
        )


def validate_catalog_id_format(catalog_id: str) -> None:
    """
    Assert that catalog_id is a non-empty string (UUID format not strictly enforced).

    Guards against obviously malformed inputs (empty, whitespace).

    Raises:
        ValueError: if catalog_id is blank.
    """
    if not catalog_id or not catalog_id.strip():
        raise ValueError("catalog_id must not be empty or whitespace")


def validate_uuid_id(value: str, field_name: str = "id") -> None:
    """
    Assert that value is a well-formed UUID (8-4-4-4-12 hex, case-insensitive).

    Call this before using any user-supplied ID in a file-path construction to
    prevent path traversal via values like ``../../etc/passwd``.

    Raises:
        ValueError: if value is not a valid UUID, with a safe message that does
                    not echo the raw value back.
    """
    if not value or not _UUID_RE.match(value.strip()):
        raise ValueError(f"{field_name} must be a valid UUID")

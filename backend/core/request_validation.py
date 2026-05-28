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
"""
from __future__ import annotations

from datetime import datetime
from typing import AbstractSet

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


def validate_catalog_id_format(catalog_id: str) -> None:
    """
    Assert that catalog_id is a non-empty string (UUID format not strictly enforced).

    Guards against obviously malformed inputs (empty, whitespace).

    Raises:
        ValueError: if catalog_id is blank.
    """
    if not catalog_id or not catalog_id.strip():
        raise ValueError("catalog_id must not be empty or whitespace")

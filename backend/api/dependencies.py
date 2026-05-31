"""
Shared FastAPI dependency providers — Phase 3S-B / Phase 4C.1 / Phase 4C.5.

All shared Depends() callables that are used across more than one route
module live here.  Route modules import from this module rather than
defining their own copies.

Canonical dependencies:
    get_draft_repository()              — DraftRepository backed by settings.drafts_storage_path
    get_backtest_storage_path()         — Path backed by settings.backtest_runs_storage_path
    get_forward_test_repository()       — ForwardTestRepository backed by settings.forward_test_sessions_storage_path
    get_forward_test_signal_store()     — ForwardTestSignalStore backed by same path
    get_forward_test_bar_store()        — ForwardTestBarStore backed by same path
    get_ohlcv_service()                 — OHLCVService backed by settings.storage_base_path
    get_tool_registry()                 — default ToolRegistry with all built-in tools
    get_provider_factory()              — ProviderAdapterFactory with yahoo + polygon + csv + parquet
"""
from __future__ import annotations

from pathlib import Path

from backend.core.config import settings
from backend.forward_testing.repository import ForwardTestRepository
from backend.forward_testing.stores import ForwardTestBarStore, ForwardTestSignalStore
from backend.strategy_registry.draft_repository import DraftRepository


def get_draft_repository() -> DraftRepository:
    """Return a DraftRepository rooted at the configured drafts storage path."""
    return DraftRepository(settings.drafts_storage_path)


def get_backtest_storage_path() -> Path:
    """Return the configured backtest runs storage directory."""
    return settings.backtest_runs_storage_path


def get_forward_test_repository() -> ForwardTestRepository:
    """Return a ForwardTestRepository rooted at the configured forward tests storage path."""
    return ForwardTestRepository(settings.forward_test_sessions_storage_path)


def get_forward_test_signal_store() -> ForwardTestSignalStore:
    """Return a ForwardTestSignalStore rooted at the configured forward tests storage path."""
    return ForwardTestSignalStore(settings.forward_test_sessions_storage_path)


def get_forward_test_bar_store() -> ForwardTestBarStore:
    """Return a ForwardTestBarStore rooted at the configured forward tests storage path."""
    return ForwardTestBarStore(settings.forward_test_sessions_storage_path)


def get_ohlcv_service():
    """Return an OHLCVService backed by the configured storage base path."""
    from backend.services.ohlcv_service import OHLCVService
    return OHLCVService(settings.storage_base_path)


def get_tool_registry():
    """Return the default ToolRegistry pre-populated with all built-in tools."""
    from backend.tools import create_default_registry
    return create_default_registry()


def get_provider_factory():
    """Return the default ProviderAdapterFactory (yahoo, polygon, csv, parquet)."""
    from backend.data_providers.provider_factory import create_default_factory_registry
    return create_default_factory_registry()

"""
Shared FastAPI dependency providers — Phase 3S-B / Phase 4C.1 / Phase 4C.5 / Phase 4E.1 / Phase 4E.2.

All shared Depends() callables that are used across more than one route
module live here.  Route modules import from this module rather than
defining their own copies.

Canonical dependencies:
    get_draft_repository()              — DraftRepository backed by settings.drafts_storage_path
    get_backtest_storage_path()         — Path backed by settings.backtest_runs_storage_path
    get_forward_test_repository()       — ForwardTestRepository backed by settings.forward_test_sessions_storage_path
    get_forward_test_signal_store()     — ForwardTestSignalStore backed by same path
    get_forward_test_bar_store()        — ForwardTestBarStore backed by same path
    get_paper_trading_repository()      — PaperTradingRepository backed by settings.paper_trading_storage_path
    get_paper_account_store()           — PaperAccountStore backed by same path
    get_account_state_snapshot_store()  — AccountStateSnapshotStore backed by same path
    get_paper_order_store()             — PaperOrderStore backed by settings.paper_trading_storage_path
    get_paper_fill_store()              — PaperFillStore backed by same path
    get_paper_position_store()          — PaperPositionStore backed by same path
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


def get_paper_trading_repository():
    """Return a PaperTradingRepository rooted at the configured paper trading storage path."""
    from backend.paper_trading.repository import PaperTradingRepository
    return PaperTradingRepository(settings.paper_trading_storage_path)


def get_paper_account_store():
    """Return a PaperAccountStore rooted at the configured paper trading storage path."""
    from backend.paper_trading.stores import PaperAccountStore
    return PaperAccountStore(settings.paper_trading_storage_path)


def get_account_state_snapshot_store():
    """Return an AccountStateSnapshotStore rooted at the configured paper trading storage path."""
    from backend.paper_trading.stores import AccountStateSnapshotStore
    return AccountStateSnapshotStore(settings.paper_trading_storage_path)


def get_paper_order_store():
    """Return a PaperOrderStore rooted at the configured paper trading storage path."""
    from backend.paper_trading.execution_stores import PaperOrderStore
    return PaperOrderStore(settings.paper_trading_storage_path)


def get_paper_fill_store():
    """Return a PaperFillStore rooted at the configured paper trading storage path."""
    from backend.paper_trading.execution_stores import PaperFillStore
    return PaperFillStore(settings.paper_trading_storage_path)


def get_paper_position_store():
    """Return a PaperPositionStore rooted at the configured paper trading storage path."""
    from backend.paper_trading.execution_stores import PaperPositionStore
    return PaperPositionStore(settings.paper_trading_storage_path)

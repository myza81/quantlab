"""
Paper Trading subsystem — Phase 4E.1.

Foundation layer: domain models, repository, and stores.

Architecture boundary — this package MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers

Execution logic (PaperBrokerAdapter, PaperTradingService) lives in
Phase 4E.2 and Phase 4E.3 respectively.

Storage layout:
    {paper_trading_storage_path}/
        sessions/   — PaperTradingSession records (one JSON per session)
        accounts/   — PaperAccount records (one JSON per session; 1:1)
        equity/     — AccountStateSnapshot arrays (equity curve per session)
"""

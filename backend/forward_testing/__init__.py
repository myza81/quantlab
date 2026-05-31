"""
Forward Testing — QuantLab Phase 4C.1.

Foundation package: session models, repository, and stores.

Phase 4C.1 scope (this package):
  - ForwardTestSession model with full lifecycle state machine
  - ForwardTestSignal model (immutable signal record)
  - ForwardTestBar model (processed-bar record)
  - StrategySnapshot model (sealed strategy capture)
  - ForwardTestRepository (JSON-backed, ownership-safe)
  - ForwardTestSignalStore (per-session signal persistence)
  - ForwardTestBarStore (per-session bar accumulation)

Not in this phase: strategy evaluation, polling scheduler, API routes, frontend.
"""

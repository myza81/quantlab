# ARCHITECTURE_GUARDRAILS.md

## Purpose

This document defines the non-negotiable architecture rules for the Strategy Research Lab platform or in another name, "Edgelab".

All implementation agents must read and follow this document before modifying, generating, refactoring, or extending any part of the repository.

The purpose of these guardrails is to preserve long-term modularity, prevent architectural drift, and ensure that the platform can evolve from research tooling into a full institutional-grade strategy research, backtesting, forward testing, paper trading, and future live trading ecosystem.

---

## 1. Core Architectural Principle

The platform must be designed as a modular strategy research and execution ecosystem.

Strategies must be portable across:

* research
* historical backtesting
* forward testing
* paper trading
* future live trading

without rewriting the strategy logic.

Any implementation that forces a strategy to depend directly on a broker, frontend component, data vendor, database implementation, or execution engine is architecturally invalid.

---

## 2. Non-Negotiable Separation of Concerns

The system must preserve strict separation between the following layers:

frontend
backend API
application services
strategy engine
data abstraction layer
storage layer
execution layer
broker/provider adapters
infrastructure

Each layer must have a clear responsibility.

No layer should bypass the layer directly below it unless explicitly approved in the architecture documentation.

---

## 3. Strategy Logic Rules

Strategy modules are the most important long-term asset of this platform.

A strategy must contain only trading or research logic.

A strategy must not directly depend on:

* broker APIs
* exchange APIs
* frontend state
* chart components
* database sessions
* web routes
* WebSocket handlers
* file paths
* environment variables
* authentication logic
* order execution implementation
* vendor-specific data formats

Strategies must receive normalized input data through defined interfaces.

Strategies must return structured outputs such as:

* signals
* trade setup candidates
* risk metadata
* entry conditions
* exit conditions
* invalidation levels
* confidence tags
* diagnostic metadata

Strategies must not directly execute trades.

---

## 4. Strategy Portability Requirement

Every strategy must be executable in multiple modes using the same core strategy logic:
research mode
backtest mode
forward-test mode
paper-trading mode
live-trading mode

Mode-specific behavior must be handled outside the strategy module.

Invalid pattern:
strategy directly calls Binance / IBKR / broker API

Valid pattern:
strategy produces signal → execution service interprets signal → broker adapter handles external API

---

## 5. Data Abstraction Rules

All market, alternative, unconventional, astrological, astronomical, sentiment, macro, and custom datasets must pass through normalization before being used by strategies.

Strategies must not know whether data originated from:

* Yahoo Finance
* Binance
* Interactive Brokers
* CSV
* Excel
* Parquet
* DuckDB
* PostgreSQL
* WebSocket stream
* manual upload
* external API
* astronomical calculation engine
* future data provider

All incoming data must be converted into stable internal schemas before reaching the strategy layer.

---

## 6. Market Data Normalization

OHLCV and time-series data must follow consistent internal schemas.

At minimum, normalized market data should preserve:

* symbol
* asset class
* exchange or venue
* timeframe
* timestamp
* open
* high
* low
* close
* volume
* source
* adjustment metadata where applicable

Provider-specific fields must be mapped, not leaked into strategies.

If a provider has unique fields, they must be stored as optional metadata or handled through provider-specific adapters.

---

## 7. Alternative and Unconventional Dataset Rules

The platform is expected to support unconventional strategy research, including planetary movement, cycles, seasonal timing, symbolic relationships, macro relationships, sentiment, and other non-standard datasets.

These datasets must still follow the same discipline:
raw source → ingestion adapter → normalization → feature layer → strategy input

Alternative datasets must not be hardcoded into individual strategies unless the strategy explicitly depends on a normalized feature derived from that dataset.

Planetary, astronomical, or cycle-based features must be exposed as reusable feature modules, not embedded as one-off calculations inside individual strategies.

---

## 8. Storage Architecture Rules

Use PostgreSQL for:

* users
* strategy registry
* strategy metadata
* experiment metadata
* backtest run metadata
* forward test metadata
* paper trading sessions
* execution logs
* audit trails
* configuration metadata

Use DuckDB and Parquet for:

* OHLCV datasets
* large time-series datasets
* historical feature datasets
* research datasets
* derived analytical datasets
* batch backtesting inputs and outputs

Avoid ORM-heavy designs for large market datasets.

Do not store large OHLCV/time-series datasets primarily in PostgreSQL unless there is a specific architectural reason.

---

## 9. Frontend Guardrails

The frontend is a research terminal and visualization layer.

The frontend may handle:

* chart rendering
* drawing tools
* strategy inspection
* backtest result visualization
* trade setup review
* user interaction
* dashboards
* forms
* filters
* UI state

The frontend must not contain:

* strategy logic
* signal generation logic
* backtest calculation logic
* broker execution logic
* risk engine logic
* data normalization logic
* halal compliance logic
* business-critical decision logic

Any calculation required for official strategy evaluation must be performed in the backend or strategy engine, not only in the browser.

Frontend-derived visual annotations may be stored as user research artifacts, but they must not replace validated strategy rules.

---

## 10. Backend API Rules

Backend APIs must expose controlled application operations.

API routes should remain thin.

API routes should not contain core business logic.

Valid backend flow:
API route → application service → domain/engine layer → repository/adapter

Invalid backend flow:
API route → direct strategy calculation → direct database mutation → direct broker call

---

## 11. Execution Layer Rules

The execution layer must be isolated from strategies.

Execution services may handle:

* order intent interpretation
* portfolio constraints
* risk validation
* position sizing
* order routing
* broker adapter selection
* paper trading simulation
* live trading approval gates
* execution audit logs

Strategies must produce signals or trade intents only.

Execution services decide whether and how those intents become orders.

---

## 12. Broker and Provider Adapter Rules

Broker and data provider integrations must be implemented as adapters.

No broker-specific implementation should leak into:

* strategies
* frontend
* core backtest engine
* research notebooks
* generic execution contracts

Broker adapters must convert internal order models into provider-specific API calls.

Data adapters must convert provider-specific market data into internal normalized schemas.

---

## 13. Backtesting Rules

Backtesting must be deterministic, reproducible, and auditable.

Each backtest run should preserve:

* strategy ID and version
* dataset ID and version
* parameter set
* timeframe
* instrument universe
* fees and slippage assumptions
* execution assumptions
* run timestamp
* result metrics
* logs or diagnostics

Backtest logic must not be embedded inside individual strategies.

A strategy defines decision logic.

The backtest engine controls simulation mechanics.

---

## 14. Forward Testing and Paper Trading Rules

Forward testing and paper trading must use the same strategy logic as backtesting.

The difference must be in the runtime environment, not in the strategy code.

Forward testing should evaluate strategies against live or near-live data without real execution.

Paper trading should simulate execution and portfolio behavior without placing real orders.

Manual intervention must be supported because not all strategies are expected to become autonomous trading bots.

---

## 15. Live Trading Guardrails

Live trading is a future capability and must be treated as a controlled extension, not a default behavior.

No code should enable uncontrolled live trading.

Live execution must require explicit approval gates, including:

* strategy validation status
* risk configuration
* portfolio constraints
* halal compliance checks
* broker configuration
* manual enablement
* audit logging
* kill-switch capability

No strategy should be able to directly place a live order.

---

Compliance must be enforceable before execution.

---

## 16. Research Discipline Rules

The platform is intended for rigorous strategy discovery from scratch.

Research workflows must support:

* hypothesis definition
* dataset selection
* feature exploration
* signal testing
* backtest comparison
* forward validation
* manual review
* promotion or rejection of strategies

Research code must not silently become production execution code.

Experimental logic must be clearly marked as experimental until promoted through the strategy lifecycle.

---

## 17. Strategy Lifecycle Rules

Strategies must progress through a controlled lifecycle:
idea
research
prototype
validated
backtested
forward-tested
paper-traded
approved-for-live
retired

A strategy must not skip directly from prototype to live execution.

Each lifecycle transition should be recorded with metadata, review notes, and result evidence.

---

## 18. Configuration Rules

Configuration must be explicit, versioned where appropriate, and environment-aware.

Do not hardcode:

* API keys
* broker credentials
* file paths
* symbols
* timeframes
* strategy parameters
* environment-specific URLs
* execution flags
* risk limits

Use structured configuration files or environment variables through approved configuration modules.

---

## 19. Logging and Audit Rules

The system must support traceability.

Important actions must produce logs or audit records, including:

* strategy runs
* data ingestion
* backtest execution
* forward test sessions
* paper trading orders
* live trading approvals
* live trading orders
* risk rejection events
* compliance rejection events
* system errors

Logs should help reconstruct what happened, why it happened, and which module made the decision.

---

## 20. Testing Requirements

Implementation must include appropriate tests for critical modules.

Required test focus areas:

* data normalization
* strategy input/output contracts
* backtest determinism
* execution safety gates
* halal compliance rules
* broker adapter behavior using mocks
* strategy lifecycle transitions
* API service behavior

Do not rely only on manual UI testing.

---

## 21. Dependency Rules

Dependencies must be added deliberately.

Before adding a dependency, confirm:

* why it is needed
* whether it duplicates existing functionality
* whether it is maintained
* whether it creates licensing or deployment issues
* whether it increases coupling

Avoid unnecessary frameworks that obscure core logic.

Prefer simple, explicit, testable modules.

---

## 22. AI Agent Implementation Rules

Implementation agents must not make broad architectural changes without explicit instruction.

Agents must:

* keep changes scoped
* preserve existing architecture boundaries
* update relevant documentation when changing architecture
* avoid rewriting unrelated modules
* avoid inventing business rules
* avoid silently changing strategy contracts
* explain assumptions before major implementation
* add tests where appropriate

Agents must not treat temporary shortcuts as permanent architecture.

---

## 23. Forbidden Patterns

The following patterns are prohibited:
strategy directly calls broker API
strategy directly reads database
strategy directly reads CSV/file path
frontend calculates official backtest results
frontend generates official trade signals
API route contains complex business logic
broker-specific code inside strategy engine
data vendor schema exposed to strategies
live order placement without approval gate
hardcoded trading symbols inside core engine
hardcoded strategy parameters inside execution code
large OHLCV storage forced into PostgreSQL by default
experimental notebook logic copied directly into production modules

Any implementation containing these patterns must be rejected or refactored.

---

## 24. Required Design Pattern Preference

Prefer the following architecture patterns:
ports and adapters
service layer
repository pattern for metadata
adapter pattern for brokers and providers
strategy interface contracts
schema-based data normalization
event/audit logging for critical actions
configuration-driven execution

Avoid unnecessary enterprise complexity, but preserve clean boundaries.

The goal is practical modularity, not over-engineering.

---

## 25. Agent Review Checklist

Before submitting any implementation, the agent must check:

* Does this preserve strategy portability?
* Does this keep broker logic outside strategies?
* Does this keep frontend free from business logic?
* Does this use normalized data contracts?
* Does this avoid hardcoded provider assumptions?
* Does this support future forward testing and paper trading?
* Does this preserve halal compliance enforcement?
* Does this avoid uncontrolled live trading?
* Does this include tests or clear validation steps?
* Does this update documentation if architecture changed?

If the answer is no to any item, the implementation must be revised.

---

## 26. Architectural Decision Rule

When uncertain, choose the option that maximizes:

* modularity
* testability
* reproducibility
* strategy portability
* auditability
* long-term extensibility

Do not optimize only for the fastest short-term implementation.

This platform is expected to grow into a long-term institutional-grade research and trading ecosystem.

---

## 27. Final Instruction to Agents

Do not treat this repository as a simple trading bot.

This is a modular Strategy Research Lab.

The primary objective is to build a rigorous environment for discovering, testing, validating, and managing strategies before any autonomous trading is allowed.

All code must respect that lifecycle.

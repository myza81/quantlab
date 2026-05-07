# EXECUTION_CONTRACT.md

## Purpose

This document defines the canonical execution contracts for QuantLab.

The purpose of this document is to establish:

* execution isolation rules
* order intent contracts
* execution lifecycle behavior
* risk enforcement boundaries
* compliance policy integration
* broker abstraction rules
* portfolio management boundaries
* paper vs live execution consistency
* execution auditability
* execution safety controls

This document protects one of the most critical architectural boundaries inside QuantLab:

```text id="bqicm6"
strategy
≠
execution
≠
broker
```

Strategies generate intent.

Execution systems decide whether execution is allowed.

---

# Core Execution Philosophy

QuantLab separates:

```text id="k5s07u"
strategy intent
from
execution authority
```

Strategies are NOT execution engines.

Strategies produce:

* signals
* trade ideas
* analytical outputs
* risk metadata

Execution systems are responsible for:

* risk validation
* portfolio constraints
* compliance enforcement
* broker routing
* order lifecycle management
* execution approvals

---

# Execution Isolation Principle

Execution systems must remain isolated from:

* strategy logic
* frontend systems
* provider-specific schemas

Strategies must NEVER directly:

* place orders
* call brokers
* bypass risk systems
* bypass compliance systems

---

# Canonical Execution Flow

All execution workflows must follow this flow.

---

## Execution Pipeline

```text id="pn4lku"
Strategy Signal
    ↓
Signal Validation
    ↓
Risk Validation
    ↓
Portfolio Validation
    ↓
Compliance Validation
    ↓
Execution Approval
    ↓
Order Intent Creation
    ↓
Broker Routing
    ↓
Execution Monitoring
    ↓
Audit Logging
```

No system may bypass validation layers.

---

# Canonical Order Intent Contract

Strategies do NOT produce broker-native orders.

Strategies produce:

```text id="9k74aj"
execution intents
```

Execution systems transform intents into executable orders.

---

## Required Order Intent Fields

| Field              | Description                    |
| ------------------ | ------------------------------ |
| intent_id          | unique intent identifier       |
| strategy_id        | originating strategy           |
| signal_id          | originating signal             |
| timestamp          | intent timestamp               |
| symbol             | target instrument              |
| asset_class        | target asset class             |
| side               | buy / sell / reduce / close    |
| intent_type        | market / limit / stop / reduce |
| reference_price    | strategy reference price       |
| invalidation_level | risk invalidation              |
| confidence         | optional confidence score      |
| metadata           | optional metadata              |

---

## Optional Fields

| Field    | Description         |
| -------- | ------------------- |
| notes    | optional reasoning  |
| tags     | classification tags |
| setup_id | setup grouping      |
| priority | execution priority  |

---

# Canonical Execution State Machine

All execution workflows must follow standardized states.

---

## Allowed Execution States

```text id="ehn6uh"
PENDING
VALIDATED
APPROVED
REJECTED
ROUTED
ACKNOWLEDGED
PARTIALLY_FILLED
FILLED
CANCELLED
FAILED
EXPIRED
```

---

## Important Rule

Execution state transitions must remain traceable and auditable.

Silent state mutation is prohibited.

---

# Execution Environment Modes

Execution behavior differs by environment.

---

## Supported Execution Modes

```text id="p5vflz"
research
backtesting
forward_testing
paper_trading
live_trading
```

---

# Environment Consistency Rule

The same:

* strategy logic
* execution pipeline
* validation pipeline

must operate consistently across all environments.

The only differences should be:

* execution backend
* runtime orchestration
* order destination

---

# Paper Trading Contract

Paper trading must simulate realistic execution behavior.

---

## Paper Trading Responsibilities

* simulated fills
* portfolio simulation
* execution lifecycle simulation
* fee simulation
* slippage simulation

---

## Important Rule

Paper trading must NOT introduce unrealistic execution shortcuts.

---

# Live Trading Contract

Live trading is a controlled future capability.

---

## Live Trading Requirements

Live execution must require:

* explicit enablement
* execution approval
* risk validation
* compliance validation
* audit logging
* kill-switch support

---

## Forbidden Behavior

Live execution must NEVER occur implicitly.

---

# Risk Layer Contract

The risk layer operates independently from strategies.

---

## Risk Responsibilities

* exposure limits
* portfolio constraints
* sizing limits
* leverage constraints
* concentration limits
* drawdown controls
* emergency shutdowns

---

## Important Rule

Strategies may suggest risk metadata.

Execution systems enforce risk authority.

---

# Position Sizing Contract

Position sizing should remain external to strategies unless intentionally strategy-defined.

---

## Preferred Ownership

Execution systems own:

* portfolio sizing
* account sizing
* exposure management

---

## Strategy Responsibility

Strategies may provide:

* invalidation levels
* confidence scores
* preferred risk profiles

---

# Portfolio Management Contract

Portfolio systems remain external to strategies.

---

## Portfolio Responsibilities

* exposure aggregation
* correlation constraints
* cross-strategy coordination
* capital allocation
* portfolio-level risk

---

# Compliance Contract

Compliance systems must remain configurable and isolated.

---

## Compliance Responsibilities

* halal policy enforcement
* jurisdiction rules
* restricted asset handling
* execution restrictions
* broker restrictions
* leverage restrictions

---

## Important Rule

Compliance logic must NOT be hardcoded inside strategies.

---

## Compliance Architecture

Preferred flow:

```text id="rjlwm0"
signal
→ execution intent
→ compliance engine
→ approval/rejection
```

---

# Broker Adapter Contract

Broker integrations must remain isolated through adapters.

---

## Broker Responsibilities

* provider translation
* order translation
* execution communication
* broker-specific retry handling
* broker authentication

---

## Strategies Must NEVER Access

* broker SDKs
* broker APIs
* broker payloads
* broker authentication

---

# Canonical Broker Flow

```text id="gjg9fy"
Internal Order Intent
    ↓
Broker Adapter
    ↓
Broker-Specific Payload
    ↓
Broker API
```

---

# Execution Audit Contract

All execution actions must remain auditable.

---

## Required Audit Areas

* signal origin
* intent origin
* approval decisions
* rejection reasons
* routing decisions
* broker responses
* execution timestamps
* portfolio changes

---

# Required Audit Metadata

| Field          | Description          |
| -------------- | -------------------- |
| execution_id   | execution identifier |
| strategy_id    | originating strategy |
| signal_id      | originating signal   |
| intent_id      | originating intent   |
| broker         | execution provider   |
| execution_mode | runtime mode         |
| timestamp      | execution timestamp  |

---

# Execution Logging Rules

Critical execution actions must generate logs.

---

## Required Logging Areas

* validation failures
* compliance rejection
* routing failures
* broker failures
* fill updates
* position changes
* emergency shutdowns

---

# Execution Retry Rules

Retries must remain controlled and deterministic.

---

## Important Rule

Execution retries must NEVER silently duplicate unintended orders.

Retry logic must remain:

* explicit
* idempotent-aware
* auditable

---

# Kill-Switch Contract

Live systems must support emergency disable capabilities.

---

## Kill-Switch Responsibilities

* stop new execution
* cancel pending orders
* isolate runtime systems
* preserve audit state

---

## Important Rule

Kill-switches must operate independently from strategy systems.

---

# Runtime Execution Contract

Execution systems must remain runtime-compatible.

---

## Supported Runtime Types

* synchronous execution
* asynchronous execution
* simulated execution
* delayed execution
* batch execution

---

# Backtesting Execution Contract

Backtesting execution must remain deterministic.

---

## Backtesting Responsibilities

* deterministic fills
* deterministic slippage
* deterministic fees
* reproducible outcomes

---

## Important Rule

Backtesting execution assumptions must remain versioned and traceable.

---

# Forward Testing Execution Contract

Forward testing should simulate realistic runtime behavior without live capital exposure.

---

## Responsibilities

* signal evaluation
* simulated execution
* runtime validation
* latency observation

---

# Frontend Execution Rules

Frontend systems must NEVER become execution authorities.

---

## Frontend MAY

* display execution status
* display portfolio state
* display audit history

---

## Frontend MUST NOT

* directly place orders
* bypass execution validation
* bypass compliance systems
* bypass risk systems

---

# API Execution Rules

APIs must expose controlled execution operations only.

---

## API Responsibilities

* request validation
* orchestration
* execution coordination

---

## Forbidden API Behavior

* direct broker execution inside routes
* bypassing execution services
* bypassing validation systems

---

# Execution Determinism Rules

Execution workflows must remain reproducible whenever possible.

Critical execution decisions should remain:

* explainable
* traceable
* reconstructable

---

# Multi-Broker Support Contract

QuantLab is designed to support multiple brokers.

---

## Examples

* Interactive Brokers
* Binance
* Alpaca
* MetaTrader
* custom brokers

---

## Important Rule

Execution systems must remain broker-agnostic internally.

---

# Execution Metadata Contract

All execution systems should preserve metadata lineage.

---

## Required Metadata Areas

| Field                  | Description         |
| ---------------------- | ------------------- |
| strategy_version       | strategy version    |
| execution_environment  | runtime environment |
| compliance_version     | compliance rules    |
| risk_version           | risk rules          |
| broker_adapter_version | adapter version     |

---

# Forbidden Execution Patterns

The following patterns are prohibited:

* strategy direct broker access
* hidden live execution
* bypassing risk systems
* bypassing compliance systems
* frontend execution authority
* direct provider payload leakage
* silent retries
* uncontrolled leverage
* hardcoded broker logic inside strategies
* execution logic inside frontend systems

---

# Future Execution Expansion Direction

Future execution systems may include:

* smart routing
* broker redundancy
* execution optimization
* distributed execution
* portfolio-level orchestration
* advanced compliance engines
* execution telemetry systems
* latency-aware routing

These systems must still preserve:

* execution isolation
* auditability
* reproducibility
* safety controls

---

# Final Execution Principle

Execution systems represent the highest operational risk layer inside QuantLab.

The architecture exists to ensure that:

* strategies remain portable
* execution remains controlled
* compliance remains enforceable
* auditability remains preserved
* live trading remains safe

All execution systems must preserve:

* modularity
* isolation
* traceability
* safety
* deterministic behavior
* explicit approval flows

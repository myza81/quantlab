# STRATEGY_CONTRACT.md

## Purpose

This document defines the canonical strategy contracts for QuantLab.

The purpose of this document is to establish:

* standardized strategy structure
* strategy lifecycle requirements
* strategy runtime behavior
* strategy input/output contracts
* feature engineering boundaries
* signal generation standards
* parameter contracts
* validation rules
* runtime compatibility requirements
* execution isolation rules

This document acts as the architectural contract for all strategy systems inside QuantLab.

All strategies must comply with these rules regardless of:

* asset class
* market
* execution mode
* research methodology
* strategy complexity

---

# Core Strategy Philosophy

QuantLab treats strategies as portable pure logic modules.

A strategy is responsible for:

* feature generation
* signal generation
* risk logic
* trade setup logic
* analytical interpretation

A strategy is NOT responsible for:

* broker communication
* order routing
* execution management
* portfolio management
* frontend rendering
* database access
* runtime orchestration

---

# Strategy Tools Philosophy

Strategies in QuantLab are composed from reusable tools and analytical modules.

A "tool" is any reusable, parameterized, independently-testable analytical component that can be used across multiple strategies.

Examples include:

* moving average modules (MA, EMA, WMA)
* momentum indicators (RSI, MACD, Stochastic)
* volatility modules (ATR, Bollinger Bands)
* harmonic formula modules
* astronomical and planetary cycle modules
* sentiment feature modules
* custom research modules

## Tool Design Requirements

All tools and analytical modules must be:

* reusable across multiple strategies
* modular and independently testable
* parameterized — no hidden configuration
* versionable — changes must not silently break existing strategies
* composable — tools may depend on other normalized inputs but not on each other's internals
* backend-validatable — all execution authority belongs to the backend
* frontend-configurable — parameters must be exposable to the frontend composition interface
* portable across all runtime modes

## Forbidden Tool Patterns

* hardcoded indicator logic embedded as one-off code inside a single strategy's features.py or signals.py when a reusable tool module is more appropriate
* tools that embed execution behavior (orders, position sizing)
* tools that access brokers, databases, or APIs directly
* tools that produce different results in different runtime modes given identical inputs

---

# Strategy Portability Principle

Every strategy must operate consistently across:

```text id="h5qjv2"
research
backtesting
forward testing
paper trading
future live trading
```

without rewriting core strategy logic.

Runtime-specific behavior must remain external to the strategy.

---

# Canonical Strategy Structure

Each strategy must follow a standardized structure.

---

## Canonical Folder Structure

```text id="9q5i1o"
strategies/

  strategy_name/

    strategy.yaml
    metadata.py
    parameters.py
    features.py
    signals.py
    risk.py
    runtime.py
    validators.py

    tests/
    research/
```

---

# Strategy File Responsibilities

---

## `strategy.yaml`

### Purpose

Strategy metadata declaration.

### Responsibilities

* strategy ID
* version
* author
* supported markets
* supported timeframes
* runtime compatibility
* lifecycle stage
* feature dependencies

### Example

```yaml id="9tbwe8"
strategy_id: mean_reversion_v1
version: 1.0.0
status: prototype

supported_assets:
  - equities
  - crypto

supported_timeframes:
  - 1h
  - 4h
  - 1d
```

---

## `metadata.py`

### Responsibilities

* strategy metadata models
* compatibility declarations
* strategy descriptors

---

## `parameters.py`

### Responsibilities

* parameter schemas
* parameter validation
* default parameter definitions

### Important Rule

Parameters must remain explicit and typed.

No hidden runtime parameters.

---

## `features.py`

### Responsibilities

* feature engineering
* derived indicators
* analytical transformations
* reusable signal preparation

### Important Rule

Features should remain deterministic and reproducible.

---

## `signals.py`

### Responsibilities

* entry logic
* exit logic
* signal generation
* trade setup logic

### Important Rule

Signals must NOT directly place orders.

---

## `risk.py`

### Responsibilities

* stop logic
* invalidation logic
* exposure constraints
* risk interpretation

### Important Rule

Execution sizing belongs outside the strategy unless explicitly strategy-defined.

---

## `runtime.py`

### Responsibilities

* runtime integration hooks
* runtime metadata exposure
* warmup declarations

### Important Rule

No execution logic allowed.

---

## `validators.py`

### Responsibilities

* parameter validation
* configuration validation
* runtime compatibility validation

---

# Required Strategy Interfaces

Every strategy must expose standardized interfaces.

---

## Required Methods

```python id="u2gr8o"
build_features()
generate_signals()
apply_risk_rules()
validate_config()
```

---

# Interface Responsibilities

---

## `build_features()`

### Responsibilities

* compute derived features
* prepare analytical inputs
* generate reusable feature outputs

### Input

Normalized datasets only.

### Output

Structured feature datasets.

---

## `generate_signals()`

### Responsibilities

* generate entry signals
* generate exit signals
* identify setups
* assign confidence metadata

### Output

Structured signal objects only.

---

## `apply_risk_rules()`

### Responsibilities

* define invalidation logic
* define protective conditions
* define risk metadata

### Important Rule

This method defines risk interpretation.

It does NOT execute risk enforcement.

---

## `validate_config()`

### Responsibilities

* validate parameters
* validate compatibility
* validate runtime assumptions

---

# Strategy Input Contract

Strategies consume only:

```text id="6sax7s"
normalized validated internal datasets
```

Strategies must NEVER directly consume:

* raw provider payloads
* broker payloads
* raw CSV structures
* frontend state
* API responses

---

# Strategy Output Contract

Strategies produce structured outputs only.

---

## Allowed Outputs

* signals
* trade setups
* risk metadata
* invalidation levels
* confidence scores
* analytical tags
* diagnostics
* visualization artifacts (indicator series, reference lines, zones — computed by the strategy, serialized by the backend, rendered generically by the frontend)

---

## Forbidden Outputs

* direct orders
* broker API calls
* execution instructions
* portfolio mutations

---

# Canonical Signal Contract

All signals must follow a standardized schema.

---

## Required Signal Fields

| Field              | Description                  |
| ------------------ | ---------------------------- |
| strategy_id        | strategy identifier          |
| timestamp          | signal timestamp             |
| symbol             | instrument                   |
| timeframe          | timeframe                    |
| signal_type        | long / short / exit / reduce |
| confidence         | optional confidence score    |
| entry_reference    | reference price              |
| invalidation_level | stop/invalidation            |
| metadata           | optional metadata            |

---

## Optional Fields

| Field            | Description               |
| ---------------- | ------------------------- |
| tags             | analytical tags           |
| reasoning        | human-readable reasoning  |
| feature_snapshot | optional feature snapshot |
| setup_id         | setup identifier          |

---

# Strategy Runtime Compatibility

Strategies must declare runtime compatibility.

---

## Supported Runtime Modes

```text id="9z93k8"
research
backtesting
forward_testing
paper_trading
live_trading
```

---

## Important Rule

Unsupported runtime modes must fail explicitly.

Silent fallback behavior is prohibited.

---

# Strategy Lifecycle Contract

Every strategy must belong to a lifecycle stage.

---

## Canonical Lifecycle

```text id="nzhh3u"
idea
→ research
→ prototype
→ validated
→ backtested
→ forward-tested
→ paper-traded
→ approved-for-live
→ retired
```

---

## Lifecycle Rules

Strategies must not bypass lifecycle stages.

Promotion requires:

* validation evidence
* reproducibility
* documented performance
* review approval

---

# Strategy Registration Contract

All strategies must register through the Strategy Registry.

---

## Required Metadata

| Field                 | Description             |
| --------------------- | ----------------------- |
| strategy_id           | unique ID               |
| version               | semantic version        |
| lifecycle_stage       | current maturity        |
| supported_assets      | compatible markets      |
| supported_timeframes  | compatible timeframes   |
| feature_dependencies  | required features       |
| runtime_compatibility | supported runtime modes |

---

# Feature Dependency Contract

Strategies may depend on reusable features.

---

## Important Rule

Reusable features should belong in shared feature pipelines when possible.

Avoid duplicating feature engineering logic across strategies.

---

## Forbidden Pattern

```text id="ukw6h0"
strategy-specific hidden feature logic
embedded inside unrelated modules
```

---

# Strategy Determinism Rule

Strategies must remain deterministic.

Given identical:

* datasets
* parameters
* configurations
* runtime assumptions

the strategy must produce identical outputs.

---

# Backtesting Compatibility Contract

Strategies must remain fully compatible with:

* deterministic replay
* reproducible execution
* parameterized testing

---

## Important Rule

Backtesting logic must remain external to the strategy.

The strategy defines decisions.

The backtesting engine defines simulation mechanics.

---

# Forward Testing Compatibility Contract

Strategies must behave consistently in:

* historical replay
* real-time evaluation

Differences must exist only in:

* runtime orchestration
* data delivery timing

---

# Paper Trading Compatibility Contract

Strategies must remain execution-independent.

Paper trading systems interpret strategy outputs externally.

---

# Live Trading Compatibility Contract

Live execution must remain isolated from strategies.

Strategies must never:

* place live orders
* bypass risk systems
* bypass approval systems

---

# Strategy Validation Rules

All strategies must pass validation before runtime execution.

---

## Validation Areas

### Structural Validation

* required files exist
* required methods exist
* metadata integrity

### Parameter Validation

* type validation
* range validation
* dependency validation

### Runtime Validation

* supported runtime modes
* feature compatibility
* timeframe compatibility

### Determinism Validation

* reproducibility checks
* stable outputs

---

# Parameter Contract

Parameters must remain explicit and versionable.

---

## Required Parameter Properties

| Field       | Description         |
| ----------- | ------------------- |
| name        | parameter name      |
| type        | parameter type      |
| default     | default value       |
| constraints | allowed constraints |
| description | purpose             |

---

## Forbidden Parameter Behavior

* hidden parameters
* implicit runtime mutations
* hardcoded environment assumptions

---

# Research Strategy Rules

Research strategies may include:

* experimental logic
* cycle analysis
* planetary relationships
* unconventional datasets
* exploratory indicators

However:

research logic must remain isolated until validated.

---

# Multi-Asset Strategy Rules

Strategies may support multiple asset classes.

---

## Supported Examples

* equities
* crypto
* futures
* forex
* commodities

---

## Important Rule

Asset-specific behavior must remain configurable.

Avoid hardcoded market assumptions.

---

# Compliance & Policy Rules

Compliance behavior must remain external.

Strategies must NOT hardcode:

* halal restrictions
* jurisdiction restrictions
* broker restrictions
* execution policies

Compliance enforcement belongs to execution/policy layers.

---

# Logging & Diagnostics Contract

Strategies should expose diagnostic metadata when possible.

---

## Examples

* feature snapshots
* signal reasoning
* validation warnings
* confidence metrics

---

# Testing Requirements

All strategies should support:

* unit testing
* deterministic replay validation
* parameter validation testing
* feature validation
* runtime compatibility testing

---

# Forbidden Strategy Patterns

The following patterns are prohibited:

* direct broker access
* direct database access
* frontend coupling
* provider-specific schema usage
* direct file access
* hidden mutable state
* non-deterministic outputs
* hardcoded runtime assumptions
* direct order placement
* execution routing logic
* portfolio mutation logic

---

# Strategy Evolution Rules

Strategies are expected to evolve incrementally.

Experimental strategies must graduate through:

```text id="n14lm8"
research
→ validation
→ backtesting
→ forward testing
→ paper trading
→ future live approval
```

before live deployment.

---

# Final Strategy Principle

Strategies are the core intellectual assets of QuantLab.

The architecture exists to preserve:

* portability
* determinism
* modularity
* reproducibility
* execution independence
* long-term maintainability

All strategy systems must protect these principles.

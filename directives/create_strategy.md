# CREATE_STRATEGY.md

## Purpose

This directive defines the required workflow, architecture boundaries, contracts, and implementation discipline for creating a new strategy inside QuantLab.

This document ensures all strategies remain:

* portable
* reproducible
* modular
* execution-independent
* research-friendly
* lifecycle-compatible

This directive applies to:

* research strategies
* experimental strategies
* prototype strategies
* production-intended strategies

---

# Core Principle

A strategy is a PURE LOGIC MODULE.

A strategy is NOT:

* a broker integration
* an execution engine
* a frontend component
* a database service
* a charting tool
* a live trading bot

A strategy produces:

* signals
* trade setup candidates
* analytical outputs
* risk metadata
* feature outputs

Execution systems decide whether signals become orders.

---

# Strategy Lifecycle

Every strategy must progress through the following lifecycle:

```text
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

A strategy must NOT skip lifecycle stages.

Research-stage strategies must remain isolated from production execution systems.

---

# Objective

When creating a strategy, the implementation agent must:

1. create a modular strategy package
2. preserve strategy portability
3. enforce architecture boundaries
4. define explicit contracts
5. isolate research logic
6. support deterministic execution
7. preserve future compatibility with:
   * backtesting
   * forward testing
   * paper trading
   * future live trading

---

# Required Repository Structure

Minimum required structure:

```text
strategies/
  {strategy_name}/
    strategy.yaml
    strategy.py
    features.py
    signals.py
    risk.py
    parameters.py
    validation.py
    metadata.py
    README.md
    tests/
```

Additional modules are allowed ONLY if justified.

Avoid premature complexity.

---

# Required Strategy Responsibilities

A strategy may contain:

* feature engineering
* signal logic
* entry logic
* exit logic
* setup classification
* risk metadata generation
* confidence scoring
* research calculations

A strategy must NOT contain:

* broker API calls
* exchange API calls
* database access
* frontend rendering logic
* execution routing
* order placement
* WebSocket management
* file-path-specific logic
* environment variable handling
* direct storage logic

---

# Mandatory Strategy Interface

Every strategy must expose:

```python
build_features()
generate_signals()
apply_risk_rules()
validate_config()
```

Optional interfaces:

```python
warmup_period()
metadata()
diagnostics()
```

Interfaces must remain deterministic.

---

# Strategy Portability Requirement

The SAME strategy logic must operate consistently in:

* research mode
* backtest mode
* forward-test mode
* paper-trading mode
* live-trading mode

Mode-specific behavior must NOT exist inside the strategy.

INVALID:

```python
if live_mode:
    place_order()
```

VALID:

```text
strategy → signal
execution engine → order decision
broker adapter → execution
```

---

# Data Contract Rules

Strategies must consume ONLY normalized internal schemas.

Strategies must never depend on raw provider schemas.

INVALID:

```python
binance_kline["close"]
```

VALID:

```python
candle.close
```

Supported normalized inputs may include:

* OHLCV
* derived features
* market structure features
* sentiment features
* planetary features
* cycle features
* macro features
* custom analytical features

All features must pass through normalization pipelines.

---

# Feature Engineering Rules

Feature engineering must remain modular and reusable.

Reusable calculations belong inside:

```text
features.py
```

Avoid embedding feature calculations directly inside signal logic unless:

* trivial
* highly strategy-specific
* non-reusable

---

# Signal Generation Rules

Signal logic belongs inside:

```text
signals.py
```

Signals should produce structured outputs such as:

```python
{
  "signal": "long",
  "confidence": 0.84,
  "entry_zone": ...,
  "invalidation": ...,
  "context": ...
}
```

Avoid raw boolean-only outputs when richer metadata is beneficial.

---

# Risk Rules

Risk logic must remain isolated from execution systems.

Risk modules may produce:

* stop levels
* invalidation levels
* sizing recommendations
* exposure tags
* volatility classifications

Risk modules must NOT:

* place orders
* enforce portfolio exposure
* manage broker positions

Portfolio enforcement belongs to execution systems.

---

# Strategy Configuration Rules

Every strategy must define explicit configuration.

Required configuration areas:

* parameters
* supported instruments
* supported timeframes
* warmup requirements
* feature dependencies
* runtime compatibility

Configuration must be versionable and deterministic.

Avoid hardcoded values inside logic.

---

# Strategy Metadata Requirements

Every strategy must include metadata:

```yaml
name:
version:
author:
status:
lifecycle_stage:
supported_markets:
supported_timeframes:
feature_dependencies:
runtime_compatibility:
research_tags:
```

Lifecycle stage must be explicitly tracked.

---

# Experimental Research Rules

QuantLab supports unconventional and experimental research.

Strategies MAY include:

* planetary analysis
* astronomical relationships
* cyclical analysis
* symbolic relationships
* custom timing models
* unconventional datasets

However:

Experimental calculations must remain modular and reproducible.

Avoid embedding large experimental calculations directly into signal logic.

Reusable experimental logic should become shared feature modules.

---

# Deterministic Execution Rules

Strategies must produce deterministic outputs.

Avoid:

* hidden randomness
* non-versioned calculations
* unstable dynamic behavior
* environment-dependent logic

Backtests using identical:

* datasets
* parameters
* configurations

must produce reproducible outputs.

---

# Testing Requirements

Every strategy must include:

* contract validation tests
* feature validation tests
* signal validation tests
* configuration validation tests

Where appropriate:

* deterministic replay tests
* edge-case tests
* missing-data handling tests

---

# Documentation Requirements

Every strategy must include:

```text
README.md
```

Minimum documentation sections:

* strategy purpose
* hypothesis
* feature dependencies
* signal logic summary
* assumptions
* limitations
* supported markets
* supported timeframes
* lifecycle status

---

# Forbidden Patterns

The following are prohibited:

* direct broker API calls
* direct exchange API calls
* database queries inside strategies
* frontend dependencies
* hardcoded credentials
* execution logic inside strategies
* live order placement
* provider-specific schemas
* hidden environment assumptions
* file-path-specific logic
* strategy-to-strategy direct dependency

---

# Preferred Implementation Workflow

Preferred workflow:

```text
hypothesis
→ feature definition
→ normalized data integration
→ signal logic
→ validation
→ backtesting
→ forward testing
→ paper trading
→ promotion review
```

Avoid:

```text
idea → live trading
```

---

# Deliverables

Minimum required deliverables:

* strategy package structure
* strategy configuration
* feature module
* signal module
* risk module
* validation module
* tests
* README.md
* metadata definition

---

# Validation Checklist

Before completing strategy creation, confirm:

- [ ] strategy is execution-independent
- [ ] no broker logic exists
- [ ] normalized data contracts are used
- [ ] strategy is portable across runtime modes
- [ ] configuration is explicit
- [ ] lifecycle stage is defined
- [ ] tests exist
- [ ] documentation exists
- [ ] no architecture guardrails are violated

---

# Final Instruction

A strategy inside QuantLab is a reusable research and decision engine.

It is NOT a trading bot.

The objective is to preserve long-term:

* modularity
* reproducibility
* portability
* research discipline
* execution safety
* institutional-grade architecture quality
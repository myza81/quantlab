# IMPLEMENT_FEATURE.md

## Purpose

This directive defines the workflow, architecture rules, modularization requirements, and validation standards for implementing reusable features inside QuantLab.

Features are reusable analytical building blocks used by:

* strategies
* research workflows
* backtesting systems
* forward-testing systems
* runtime environments

Features must remain:

* modular
* deterministic
* reusable
* normalized
* execution-independent
* architecture-safe

---

# Core Philosophy

A feature is NOT a strategy.

A feature is a reusable transformation or analytical calculation that produces structured outputs from normalized inputs.

Examples:

* moving averages
* volatility calculations
* market structure metrics
* planetary cycles
* sentiment scores
* timing models
* liquidity metrics
* custom research signals

Features must remain isolated from:

* execution systems
* brokers
* frontend rendering
* runtime side effects

---

# Objective

When implementing a feature, the implementation agent must:

1. preserve modularity
2. preserve deterministic behavior
3. maintain normalized data contracts
4. support reusability
5. maintain reproducibility
6. isolate execution concerns
7. prevent architecture violations

---

# Required Feature Workflow

Minimum required workflow:

```text
define feature objective
→ define inputs
→ validate normalized schemas
→ implement deterministic calculations
→ validate outputs
→ test reproducibility
→ document assumptions
→ register feature metadata
```

---

# Feature Categories

QuantLab features may include:

* technical indicators
* volatility features
* market structure features
* momentum features
* liquidity features
* timing models
* cyclical analysis
* planetary calculations
* astronomical calculations
* macroeconomic features
* sentiment features
* custom analytical transforms

All feature categories must follow architecture discipline.

---

# Feature Isolation Rules

Features must remain execution-independent.

Features must NOT:

* place orders
* access brokers
* access frontend state
* mutate databases directly
* perform execution routing
* depend on runtime mode

VALID:

```text
normalized input
→ feature calculation
→ structured output
```

INVALID:

```python
if signal == "buy":
    broker.place_order()
```

---

# Input Contract Rules

Features must consume ONLY normalized schemas.

Features must never depend on:

* raw API responses
* provider-specific payloads
* exchange-specific structures
* transport-specific formats

VALID:

```python
candle.close
```

INVALID:

```python
binance_payload["close"]
```

---

# Output Contract Rules

Features should produce structured outputs.

Examples:

```python
{
  "volatility": 1.24,
  "regime": "expansion",
  "confidence": 0.88
}
```

or:

```python
{
  "moon_phase": "waxing",
  "cycle_strength": 0.71
}
```

Outputs must remain deterministic and inspectable.

---

# Reusability Rules

Reusable calculations should NOT remain embedded inside:

* strategy modules
* notebooks
* runtime systems
* frontend logic

Reusable logic belongs inside dedicated feature modules.

Avoid duplicated calculations across strategies.

---

# Deterministic Rules

Features must produce reproducible outputs.

Given identical:

* datasets
* parameters
* configurations

feature outputs must remain reproducible.

Avoid:

* hidden randomness
* unstable state mutation
* environment-dependent behavior
* hidden side effects

---

# Parameter Rules

Feature parameters must be explicit.

Avoid hidden constants.

Examples:

```python
window=20
threshold=0.5
```

Parameters should support:

* validation
* versioning
* reproducibility
* inspection

---

# Stateful Feature Rules

Stateful features are allowed when necessary.

Examples:

* rolling calculations
* streaming aggregation
* online learning windows
* session tracking

However:

State handling must remain explicit and deterministic.

Avoid hidden mutable global state.

---

# Alternative Feature Rules

QuantLab fully supports unconventional features.

Examples:

* planetary alignment
* moon cycles
* eclipse timing
* seasonal cycles
* symbolic timing models
* macroeconomic timing
* sentiment-derived regimes

Alternative features must still preserve:

* normalization
* reproducibility
* modularity
* timestamp integrity

---

# Timestamp Rules

Features must preserve correct temporal alignment.

Features must NOT leak:

* future candles
* future labels
* future feature states
* future timestamps

Feature pipelines must preserve causal ordering.

---

# Multi-Timeframe Rules

Features using multiple timeframes must preserve:

* synchronization integrity
* aggregation consistency
* deterministic alignment
* timestamp traceability

Avoid hidden alignment assumptions.

---

# Performance Rules

Features should remain computationally efficient where possible.

Avoid:

* unnecessary recomputation
* hidden expensive loops
* duplicated transforms
* uncontrolled memory growth

Performance optimizations must NOT compromise reproducibility.

---

# Caching Rules

Feature caching is allowed when:

* deterministic
* traceable
* reproducible
* invalidation-safe

Avoid hidden cache mutation behavior.

---

# Feature Metadata Rules

Features should preserve metadata such as:

* feature name
* version
* parameter definitions
* dependencies
* required warmup
* supported datasets
* supported timeframes

Feature metadata should remain inspectable.

---

# Feature Dependency Rules

Features may depend on:

* normalized datasets
* other reusable features

However:

Dependency chains must remain explicit and manageable.

Avoid deeply tangled feature dependency trees.

---

# Validation Rules

Feature validation may include:

* statistical validation
* deterministic replay
* edge-case validation
* missing-data validation
* timestamp integrity validation
* sensitivity testing
* cross-market testing

Validation must remain reproducible.

---

# Research vs Production Rules

Experimental features are allowed.

However:

Experimental features must remain isolated until validated.

Research-stage features must NOT silently enter production runtime systems.

---

# Storage Rules

Features may be:

* computed on demand
* cached
* persisted
* precomputed

Storage decisions must preserve:

* reproducibility
* version traceability
* deterministic behavior

---

# Failure Handling Rules

Feature failures must produce:

* explicit errors
* diagnostics
* validation outputs
* traceable logs

Avoid silent calculation failures.

---

# Promotion Rules

A feature may be promoted to reusable/core status ONLY if:

- [ ] outputs are reproducible
- [ ] normalization is preserved
- [ ] timestamp integrity is preserved
- [ ] validation exists
- [ ] dependencies are explicit
- [ ] metadata exists
- [ ] no architecture violations exist

---

# Forbidden Patterns

The following are prohibited:

* broker access inside features
* provider-specific schema leakage
* frontend dependencies
* hidden mutable state
* future-data leakage
* undocumented transforms
* strategy-specific hacks
* runtime-mode branching
* hidden environment assumptions

---

# Deliverables

Minimum expected deliverables:

* feature implementation
* parameter definition
* metadata definition
* validation outputs
* reproducibility validation
* dependency documentation
* usage examples
* promotion/rejection recommendation

---

# Validation Checklist

Before completing feature implementation, confirm:

- [ ] normalized inputs are used
- [ ] outputs are deterministic
- [ ] no future-data leakage exists
- [ ] timestamp integrity is preserved
- [ ] parameters are explicit
- [ ] metadata exists
- [ ] validation exists
- [ ] dependencies are documented
- [ ] reproducibility is preserved
- [ ] no architecture guardrails were violated

---

# Final Instruction

Features inside QuantLab are reusable analytical building blocks.

Features are NOT:

* strategies
* execution systems
* broker integrations
* frontend business logic

The objective is to create modular, reusable, and deterministic analytical components capable of supporting institutional-grade research and execution workflows while preserving:

* reproducibility
* modularity
* portability
* architecture integrity
* long-term maintainability
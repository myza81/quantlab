# STRATEGY_DEFINITION_ARCHITECTURE.md

## Purpose

This document defines the architectural contract for strategy definitions in QuantLab.

A strategy definition is the formal, portable, backend-executable representation of a trading strategy.

This document establishes:

* the vocabulary of strategy composition
* the components from which strategies are built
* how reusable tools combine into executable logic
* the composition model and dependency chain
* frontend and backend responsibility boundaries
* runtime portability requirements
* serialization and validation philosophy
* extensibility direction

This document is architecture-level.

It is intentionally implementation-agnostic.

Specific schemas, API contracts, runtime implementations, and database models are defined in their respective contract documents.

---

# Why This Document Exists

QuantLab is a modular strategy-building ecosystem.

Users compose strategies from reusable tools — indicators, formulas, analytical modules — through the frontend interface.

These compositions must become deterministic, backend-executable strategy definitions that behave consistently across:

* research
* backtesting
* forward testing
* paper trading
* future live trading

The platform therefore needs a formal language for:

* what a strategy definition is
* what components it contains
* how tools compose into logic
* how that logic becomes a signal
* how signals lead to execution intent

This document provides that language.

---

# The Strategy Composition Vocabulary

QuantLab defines a precise vocabulary for strategy construction.

Each term below has a specific architectural meaning.

Understanding the distinctions between these concepts is required for all architectural and implementation work.

---

## Tool

A Tool is a reusable, parameterized, independently-testable analytical building block.

A Tool is the foundational unit of the strategy-building ecosystem.

Tools are not strategies.

Tools produce Features.

### Examples

* Moving Average (MA) — produces smoothed price series
* Exponential Moving Average (EMA) — produces exponentially weighted price series
* Relative Strength Index (RSI) — produces momentum oscillator values
* MACD — produces momentum and divergence values
* Average True Range (ATR) — produces volatility measurements
* Harmonic engine — produces harmonic ratio and price pattern values
* Planetary cycle module — produces astronomical phase and alignment values
* Sentiment module — produces sentiment score series
* Volatility regime classifier — produces regime labels
* Custom feature generator — produces user-defined derived series

### Requirements

All Tools must be:

* **Reusable** — a single Tool must work correctly across multiple strategies without modification
* **Modular** — a Tool must be independently testable and deployable
* **Parameterized** — all configuration must be explicit and typed; no hidden parameters
* **Composable** — a Tool may receive normalized Features as inputs from other Tools, but must not depend on another Tool's internals
* **Versionable** — changes to a Tool must be versioned to avoid silently breaking dependent strategies
* **Backend-validatable** — Tool behavior must be deterministically reproducible and verifiable by the backend
* **Frontend-configurable** — Tool parameters must be exposable through the frontend composition interface
* **Runtime-portable** — a Tool must produce identical outputs given identical inputs regardless of runtime mode (research, backtest, forward test, paper trade, live)

### Forbidden Tool Patterns

* A Tool that contains order placement or execution logic
* A Tool that directly accesses brokers, exchanges, databases, or file paths
* A Tool that behaves differently in research mode vs. backtest mode given identical inputs
* A Tool whose behavior is only described by one strategy's internal code (one-off embedded indicators)
* A Tool whose parameters are implicitly determined by the runtime environment
* A Tool that is hardcoded to a specific symbol, timeframe, or market

---

## Feature

A Feature is a derived analytical value or series produced by a Tool when applied to normalized input data.

Features are the outputs of Tools.

Strategies do not interact with raw market data directly.

Strategies consume Features.

### Examples

* MA20 series — a moving average series over a 20-period window
* RSI(14) values — RSI oscillator values over a 14-period lookback
* ATR(14) daily series — daily average true range values
* Planetary phase alignment score — a time-series of calculated astronomical alignment values
* Volatility regime label — a time-series of volatility state classifications (low / medium / high)
* Harmonic completion ratio — a computed geometric ratio at a price pattern node

### Clarification

```text
Tool(parameters) applied to NormalizedData → Feature
```

A Feature is not a condition.

A Feature is a computed analytical quantity that conditions may reference.

### Requirements

* Features must be deterministic — identical inputs produce identical Feature values
* Features must remain portable — a Feature computed during backtesting must be identical to a Feature computed during forward testing given the same input data
* Features must not embed runtime-mode-specific logic
* Features must be named and versioned as part of their producing Tool's contract

---

## Condition

A Condition is a logical comparison or state evaluation applied to one or more Features.

A Condition evaluates to true or false.

### Examples

* `MA20 > MA50` — golden cross condition
* `RSI < 30` — oversold condition
* `cycle_phase == "accumulation"` — regime condition
* `price > EMA200` — trend filter condition
* `ATR(14) > ATR_threshold` — volatility condition
* `harmonic_completion_ratio > 0.618` — harmonic structure condition

### Requirements

* Conditions must remain declarative — they describe what to evaluate, not how to execute it
* Conditions must reference named Features, not raw market data
* Conditions must remain portable across runtime modes
* Conditions must be deterministic given identical Feature values

### Forbidden Condition Patterns

* A Condition that embeds execution behavior
* A Condition that directly queries a database or API
* A Condition that references broker state
* A Condition whose evaluation changes based on runtime mode

---

## Rule

A Rule is a structured combination of one or more Conditions using logical operators.

Rules define the full logical structure of an entry, exit, filter, or confirmation requirement.

### Logical Operators

* `AND` — all conditions must be true
* `OR` — at least one condition must be true
* `NOT` — negates a condition
* Grouped logic — nested condition groups with mixed operators

### Examples

* Long entry rule: `MA20 > MA50 AND RSI < 60 AND price > EMA200`
* Exit rule: `RSI > 80 OR price < MA20`
* Volatility filter rule: `ATR(14) > ATR_baseline AND NOT high_volatility_regime`
* Planetary confirmation rule: `cycle_phase == "bullish_alignment" AND harmonic_completion == true`

### Composability Philosophy

Rules must be composable.

A complex rule may be built from simpler sub-rules.

Sub-rules may be reused across different rule groups within the same strategy or across different strategies.

Rules must remain declarative and data-driven, not procedural.

### Requirements

* Rules must only reference Conditions or other Rules — not raw Features or market data directly
* Rules must be deterministic
* Rules must be portable across runtime modes
* Rules must not embed execution logic
* Nested rule depth should remain manageable — excessively deep nesting is an architectural smell

---

## Signal

A Signal is the analytical outcome produced when one or more Rules evaluate to true.

A Signal expresses a directional or positional bias.

A Signal is NOT a broker order.

A Signal is NOT an execution instruction.

### Signal Types

| Type | Meaning |
|---|---|
| `long` | Bullish bias — entry candidate for long exposure |
| `short` | Bearish bias — entry candidate for short exposure |
| `exit` | Neutral — existing exposure should be closed |
| `reduce` | Partial reduction of existing exposure |
| `avoid` | Active indication to not trade this period |
| `watch` | Alert-level observation without action |

### Clarification

```text
Rule(true) → Signal
Signal → Execution Layer interpretation
```

A Signal does not communicate how to execute.

The execution layer interprets signals in the context of portfolio state, risk constraints, and broker capabilities.

### Requirements

* Signals must carry identifying metadata (strategy ID, symbol, timeframe, timestamp)
* Signals should carry confidence context where available
* Signals must not embed broker-specific logic
* Signals must not directly reference portfolio positions
* Signals must be deterministic given identical Rule evaluations

---

## Filter

A Filter is an additional contextual constraint that suppresses or qualifies a Signal.

Filters apply after the primary signal generation rules have been evaluated.

A Filter does not generate signals — it gates or qualifies existing signals.

### Distinction from Rules

| | Rule | Filter |
|---|---|---|
| Purpose | Primary entry/exit logic | Contextual gating and qualification |
| Generates signals | Yes | No — it qualifies or suppresses signals |
| Examples | Golden cross entry rule | Trend filter, session filter, volatility filter |

### Examples

* **Volatility filter** — suppress signals when market volatility exceeds a threshold
* **Trend filter** — suppress counter-trend signals when price is far from a moving average
* **Session filter** — suppress signals outside defined trading hours or market sessions
* **Liquidity filter** — suppress signals when volume falls below a liquidity threshold
* **Planetary regime filter** — suppress signals during adverse astronomical alignment windows
* **Drawdown filter** — suppress new entries when recent drawdown exceeds a tolerance

### Requirements

* Filters must be composable and reusable across strategies
* Filters must reference Features or external context data, not raw market data directly
* Filters must be portable across runtime modes
* Filters must not embed execution behavior

---

## Confirmation

A Confirmation is secondary validation logic that strengthens or qualifies confidence in a Signal.

A Confirmation differs from a primary entry Rule in that it provides supporting evidence for a Signal already generated, rather than being a primary requirement for signal generation.

### Distinction from Filters

| | Filter | Confirmation |
|---|---|---|
| Effect on signal | Can suppress/gate the signal | Adjusts confidence weighting |
| Logic role | Binary gating | Evidence accumulation |
| Examples | Trend filter, session filter | Volume confirmation, secondary indicator alignment |

### Examples

* **Volume confirmation** — signal confidence increases when entry candle volume exceeds the average
* **Multi-timeframe confirmation** — higher timeframe direction aligns with the entry signal
* **Momentum confirmation** — RSI is pointing in the direction of the signal at signal time
* **Planetary alignment confirmation** — secondary astronomical cycle supports the primary signal direction
* **Harmonic confirmation** — price structure aligns with a harmonic completion point

### Requirements

* Confirmations must be optional — a strategy must function without all confirmations
* Confirmations should contribute to confidence scoring where applicable
* Confirmations must not become hard entry requirements without being reclassified as Rules
* Confirmations must remain portable and deterministic

---

## Risk Rule

A Risk Rule defines analytical or strategy-level constraints that bound the validity of a Signal.

Risk Rules define when a signal should be invalidated, when exposure should be limited, and what the trade setup's structural boundaries are.

### Distinction: Strategy Risk vs. Execution Risk

| | Strategy Risk Rule | Execution-Layer Risk Enforcement |
|---|---|---|
| Authority | Strategy module | Execution system |
| Scope | Analytical signal validity, invalidation levels, stop logic | Portfolio constraints, position sizing, broker limits |
| Examples | Invalidation level below key support, max adverse excursion threshold | Maximum position size, portfolio heat limits, margin constraints |

### Examples

* Invalidation level — the price level at which the trade setup's premise is no longer valid
* Protective stop logic — the analytical price zone that defines structural failure
* Max adverse excursion tolerance — the maximum allowable pullback before the setup is abandoned
* Exposure duration constraint — a maximum holding period after which a signal expires
* Signal expiry — a signal that is not executed within N bars is considered stale

### Requirements

* Risk Rules must remain strategy-analytical in nature
* Risk Rules must not embed portfolio management or broker execution logic
* Risk Rules must be deterministic
* Risk Rules must be portable across runtime modes
* Execution-layer risk enforcement belongs outside the strategy

---

## Execution Intent

An Execution Intent is the final output of a strategy: an analytical trade candidate with full contextual metadata.

An Execution Intent is NOT a broker order.

An Execution Intent expresses what the strategy analytically concludes should happen.

The execution layer decides whether and how to act on it.

### Contents

An Execution Intent typically contains:

* Signal type (long / short / exit / reduce)
* Symbol and timeframe context
* Reference price (entry reference level)
* Invalidation level (analytical stop / structural failure point)
* Confidence score (if available)
* Signal reasoning (if available)
* Expiry metadata
* Source strategy ID and version
* Timestamp

### Clarification

```text
Strategy produces Execution Intent
Execution Layer receives Execution Intent
Execution Layer decides: size, timing, broker, compliance check, actual order
```

A strategy never places an order.

A strategy never reads portfolio positions.

A strategy only produces Execution Intents.

---

# Strategy Composition Model

A strategy definition is a structured composition of the above concepts into an executable logic graph.

## Composition Chain

```text
NormalizedData
    ↓
Tool(parameters)
    ↓
Feature(s)
    ↓
Condition(s)
    ↓
Rule(s)
    ↓  ↑ [Filters applied]  ↑ [Confirmations applied]
Signal
    ↓
Risk Rule evaluation
    ↓
Execution Intent
```

## Dependency Relationships

* Tools consume NormalizedData and produce Features
* Conditions reference Features
* Rules combine Conditions
* Filters reference Features or external context data and qualify Signals
* Confirmations reference Features or secondary signals and adjust confidence
* Risk Rules define the invalidation and constraint boundaries for Signals
* Signals become Execution Intents after Risk Rule evaluation

## Cross-Tool References

A Tool may produce Features that depend on Features produced by another Tool, provided:

* the dependency is explicit and named
* the producing Tool is declared as a dependency
* the dependency does not create circular references

Example:

```text
ATR Tool → ATR Feature
Volatility Regime Classifier Tool (consumes ATR Feature) → Volatility Regime Feature
Signal Filter (consumes Volatility Regime Feature) → filters Execution Intent
```

## Multi-Timeframe Relationships

A strategy may reference Features computed on different timeframes.

Multi-timeframe Feature dependencies must be:

* explicitly declared in the strategy definition
* resolved at runtime using the correct data slices for each timeframe
* never implicitly assumed by the execution layer

Example:

```text
Weekly MA Tool(52) → Weekly Trend Feature  [higher timeframe context]
Daily RSI Tool(14) → Daily RSI Feature     [primary entry timeframe]
Rule: Daily RSI < 30 AND Weekly Trend == bullish → Signal
```

## Nested Composition

Strategy definitions may contain nested rule structures.

Complex strategies may include:

* primary entry rule group
* secondary confirmation group
* contextual filter group
* multi-timeframe trend context group

Each group must remain independently validatable.

---

# Frontend and Backend Responsibility Boundaries

The frontend and backend have distinct and non-overlapping authorities in the strategy definition lifecycle.

## Frontend Responsibilities

| Responsibility | Description |
|---|---|
| Tool selection | User selects which Tools to use in the strategy |
| Parameter configuration | User configures Tool parameters (e.g. MA window = 20) |
| Condition authoring | User defines conditions referencing Tool-produced Features |
| Rule composition | User combines conditions using AND / OR / NOT logic |
| Filter assignment | User attaches contextual filters to the strategy |
| Confirmation assignment | User adds confirmations to strengthen signals |
| Risk rule definition | User defines analytical invalidation levels and constraints |
| Strategy inspection | User reviews and edits the composed strategy definition |
| Visualization | User inspects chart overlays, signal markers, and indicator series |
| Research workflow | User iterates, refines, and organizes strategies through the research process |

The frontend produces a structured strategy definition that can be submitted to the backend.

The frontend is the composition interface.

## Backend Responsibilities

| Responsibility | Description |
|---|---|
| Strategy definition validation | Validates that the submitted definition is structurally and semantically correct |
| Tool resolution | Resolves Tool references to registered Tool implementations |
| Feature computation | Executes Tool logic against normalized data to produce Features |
| Condition evaluation | Evaluates declared Conditions against computed Features |
| Rule evaluation | Evaluates the rule logic tree to produce Signal candidates |
| Filter application | Applies Filter logic to qualify or suppress Signals |
| Confirmation evaluation | Computes Confirmation evidence and adjusts confidence |
| Risk rule evaluation | Applies analytical Risk Rules to produce Execution Intents |
| Signal persistence | Stores signals with full traceability metadata |
| Runtime orchestration | Manages strategy execution across all runtime modes |
| Backtesting execution | Replays strategy logic deterministically over historical data |
| Audit logging | Records all strategy executions with reproducible metadata |
| Execution safety | Enforces that no strategy output directly places broker orders |

The backend is the official validation and execution authority.

## The Key Principle

The frontend expresses user intent.

The backend validates it, executes it, and produces the official outputs.

A strategy definition submitted from the frontend has no execution authority until validated and executed by the backend.

---

# Runtime Portability

The same strategy definition must operate consistently across all runtime modes.

## Runtime Modes

| Mode | Description |
|---|---|
| Research | Interactive exploration, single-period or range analysis, signal inspection |
| Backtesting | Deterministic historical replay over defined date ranges |
| Forward Testing | Live or near-live data evaluation without real execution |
| Paper Trading | Simulated execution against live data with portfolio simulation |
| Live Trading | Future real-execution mode (requires explicit approval gates) |

## Portability Requirement

Given identical input data, parameters, and configuration:

* A strategy must produce identical Signals in research mode and backtest mode
* A strategy must produce identical Feature values in all modes
* A strategy must apply identical Rule logic in all modes
* No conditional logic based on runtime mode is permitted inside a strategy definition

## What May Differ Across Modes

The strategy definition itself does not change across modes.

The following may differ — all external to the strategy definition:

* Data delivery mechanism (historical batch vs. live stream)
* Execution interpretation (paper simulation vs. live broker)
* Portfolio context (simulation state vs. real portfolio state)
* Scheduling and event triggers (historical replay vs. real-time ticks)

## Portability Violations

The following are architectural violations:

* A strategy that checks `if mode == "backtest"` and changes behavior
* A strategy that reads real-time data in live mode but historical data in backtest mode without the abstraction being handled externally
* A Tool that produces different Feature values given identical inputs in different modes

---

# Validation Boundaries

Strategy definition validation occurs at multiple layers with distinct responsibilities.

## Structural Validation

Performed by the backend on receiving a strategy definition.

Validates:

* All declared Tools are registered and accessible
* All referenced Features are producible by their declared Tools
* All Conditions reference valid, computable Features
* All Rules are syntactically well-formed
* Required metadata is present (strategy ID, version, parameter declarations)
* No circular Tool dependencies

## Parameter Validation

Performed against each Tool's declared parameter schema.

Validates:

* All required parameters are present
* Parameter types are correct
* Parameter values fall within declared constraints
* Parameter combinations that are mutually exclusive are not both active

## Semantic Validation

Validates that the strategy definition makes logical sense.

Examples:

* A strategy that has Rules but no Signals is incomplete
* A strategy that references a Feature from a Tool not included in its Tool list is invalid
* A Risk Rule that references an invalidation level outside plausible price range may emit a warning

## Runtime Compatibility Validation

Validates that the strategy definition is compatible with the requested runtime mode.

Examples:

* A strategy declaring live-trading incompatibility must not be promoted to paper or live modes
* A strategy requiring a warmup period must have sufficient data available before evaluation begins

## Validation Authority

All official validation belongs to the backend.

Frontend-side validation is advisory only — it helps the user catch obvious errors during composition but does not replace backend validation.

A strategy definition is not considered valid until the backend confirms it.

---

# Serialization Philosophy

This section describes the architectural expectations for strategy definition serialization.

It does not define an implementation schema.

## Core Requirements

A strategy definition must be serializable — it must be expressible as a structured, portable representation that can be:

* stored durably
* transmitted between systems
* versioned
* validated
* reconstructed deterministically

## Versioning

Every strategy definition must carry an explicit version identifier.

When a strategy definition changes — even a parameter value — a new version should be recorded.

The system must be able to reconstruct the exact strategy definition used for any historical run.

## Portability

A serialized strategy definition must be self-contained or fully resolvable through registered Tool and Feature dependencies.

A strategy definition must not reference environment-specific values (absolute file paths, machine-specific IDs, ephemeral session tokens).

## Determinism

Given a serialized strategy definition and a deterministic dataset:

* Feature computation must produce identical results
* Rule evaluation must produce identical results
* Signals must be identical

The serialized definition is the single source of truth for what logic was applied.

## Migration Compatibility

When Tools are updated or versioned, the serialization format must support:

* pinning a strategy to a specific Tool version
* graceful handling of deprecated Tools
* explicit migration pathways when Tool interfaces change

A strategy pinned to Tool version 1.2 must continue to execute correctly even after Tool version 1.3 is released, unless explicitly migrated.

## Future Schema Compatibility

The serialization format must accommodate:

* new Tool categories not yet imagined
* optional and extensible metadata fields
* backward-compatible additions without breaking existing strategy definitions

Avoid designs that hard-code a closed set of Tool types or condition operators in the serialization format itself.

---

# Extensibility Philosophy

The strategy-building ecosystem must remain open to expansion without requiring core architectural rewrites.

## Expanding the Tool Ecosystem

New Tool categories must be addable through the Tool registration system.

Adding a planetary cycle module must not require changes to the core rule evaluation engine.

Adding an AI-generated feature module must not require changes to the serialization format.

The architecture must treat Tool categories as open and extensible.

## Expanding Condition Operators

The core set of logical operators (AND, OR, NOT) is foundational.

Future expansion may include:

* probabilistic operators
* time-weighted conditions
* cross-asset conditions
* multi-timeframe cross-reference operators

Operator expansion must be backward-compatible.

## Expanding Signal Types

The Signal type vocabulary is expected to grow.

Future additions may include:

* `scale_in` — add to existing position
* `scale_out` — partially reduce position
* `flip` — exit current and enter opposite
* `hedge` — add a correlated hedge instrument

New signal types must be addable without invalidating existing strategy definitions.

## Unconventional Dataset Support

The architecture must natively support unconventional data as Tool inputs.

Examples:

* astronomical and planetary cycle datasets
* sentiment and social signal datasets
* macro and alternative economic datasets
* AI-generated synthetic feature datasets
* proprietary custom research datasets

These must flow through the same normalization pipeline as traditional market data.

Strategy Tools that consume them must conform to the same Tool design requirements as classical indicators.

## AI-Generated and Hybrid Systems

Future strategy Tools may include:

* AI-generated feature modules that produce learned embeddings as Features
* hybrid systems combining classical rules with probabilistic AI outputs
* adaptive Tools that update parameters through statistical recalibration

These must remain portable, versioned, and deterministic at execution time.

AI-generated parameters must be captured in the serialized strategy definition before execution.

A strategy must not call an AI model at runtime without the model's outputs being first materialized into a deterministic Feature.

---

# Forbidden Patterns

The following patterns are architectural violations at the strategy definition level:

* A strategy definition that contains broker-specific execution instructions
* A strategy definition that reads live portfolio state during signal evaluation
* A Tool that produces different Feature values given identical inputs in different runtime modes
* A Condition that calls an external API directly
* A Rule that checks the runtime mode and changes its logic
* A strategy definition that is not versioned
* A strategy that bypasses Tool abstraction and computes Features as raw embedded calculations
* A strategy definition serialization format that is not human-readable or inspectable
* Confirmation logic promoted to a hard entry requirement without reclassification as a Rule
* Risk Rules that include position sizing or broker routing logic

---

# Relationship to Other Architecture Documents

| Document | Relationship |
|---|---|
| `docs/STRATEGY_CONTRACT.md` | Defines the strategy module interface contract (the callable API). This document defines what flows through that interface. |
| `docs/ARCHITECTURE.md` | Defines system topology and layers. This document provides the vocabulary used within the Strategy Layer. |
| `docs/SYSTEM_OVERVIEW.md` | High-level platform philosophy. This document provides the formal compositional language for the Strategy Tools Builder Layer described there. |
| `agent/ARCHITECTURE_GUARDRAILS.md` | Enforcement rules for agents. This document provides the conceptual definitions that guardrails reference. |
| `docs/EXECUTION_CONTRACT.md` | Defines how Execution Intents are interpreted by the execution layer. This document defines the boundary up to Execution Intent production. |

---

# Summary of Core Principle

```text
User Idea
    ↓
Tool Selection (frontend orchestration)
    ↓
Feature Production (backend execution)
    ↓
Condition Evaluation (backend)
    ↓
Rule Evaluation (backend)
    ↓
Signal Generation (backend)
    ↓  [Filters]  [Confirmations]
Risk Rule Evaluation (backend)
    ↓
Execution Intent (strategy output boundary)
    ↓
Execution Layer (separate concern)
    ↓
Broker / Paper Simulation / Research Output
```

The strategy definition covers everything from Tool Selection through Execution Intent production.

Everything below Execution Intent is outside the strategy definition boundary.

Everything above User Idea is outside the strategy definition boundary.

The strategy definition is the bridge between human research intent and deterministic computational execution.

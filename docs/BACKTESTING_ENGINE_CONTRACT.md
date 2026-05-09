# BACKTESTING_ENGINE_CONTRACT.md

## Purpose

This document defines the architectural contract for the Backtesting Engine in QuantLab.

The Backtesting Engine is the deterministic historical simulation environment for evaluating validated strategy definitions against historical datasets.

This document establishes:

* what the backtesting engine is and what it is not
* the conceptual input contract
* the validated strategy definition requirement
* dataset traceability expectations
* tool resolution during backtesting
* feature computation philosophy
* rule and signal evaluation flow
* simulated execution layer responsibilities
* portfolio and position state philosophy
* result artifacts and metrics expectations
* the reproducibility contract
* the audit record philosophy
* multi-timeframe backtesting expectations
* lookahead bias prevention as a non-negotiable constraint
* research vs. validation vs. promotion-grade backtesting
* compliance and policy hook philosophy
* the frontend relationship
* forbidden patterns

This document is architecture-level.

It is intentionally implementation-agnostic.

Specific simulation algorithms, metric formulas, database schemas, API routes, and frontend rendering details belong in their respective implementation contracts.

---

# Why This Document Exists

The backtesting engine is the first major consumer of validated strategy definitions produced by the Strategy Tools Builder.

Without a formal contract, the backtesting engine risks:

* silently using wrong tool versions, producing non-reproducible results
* allowing draft strategy definitions to bypass validation
* introducing lookahead bias through careless data windowing
* mixing strategy logic with simulation mechanics
* accumulating hidden execution assumptions that are never audited
* producing results that cannot be traced to their exact inputs

This contract prevents those failures by establishing the architecture before implementation begins.

---

# What the Backtesting Engine Is

The Backtesting Engine is the deterministic historical simulation environment for evaluating validated strategy definitions against historical datasets.

Its responsibilities are:

* **Consuming validated strategy definitions** — it accepts strategy definitions that have passed backend validation
* **Resolving tools from registry snapshots** — it resolves tool references to their exact registered implementations
* **Coordinating feature computation** — it executes tools in dependency order against historical normalized data
* **Evaluating conditions, rules, and signals historically** — it processes the strategy's logic bar by bar over the historical window
* **Managing simulated execution** — it models fills, fees, slippage, and position state without placing real orders
* **Tracking portfolio and position state** — it maintains a simulated account state across the full simulation horizon
* **Computing result metrics** — it aggregates simulation outcomes into analytical metrics
* **Producing result artifacts** — it outputs structured, inspectable backtest results
* **Recording audit metadata** — it persists a complete, immutable record of every run's inputs, assumptions, and outputs

## What the Backtesting Engine Is NOT

| Not this | Why |
|---|---|
| A strategy authoring interface | Strategy composition belongs to the Frontend Composition Interface |
| A live trading engine | Simulated execution is not real execution; the simulation layer is explicitly not connected to brokers |
| A broker adapter | Broker-specific behavior must remain in the Broker Adapter Layer |
| A frontend charting system | The frontend visualizes backtest results; the engine does not render |
| A data provider | The engine consumes normalized data; data ingestion and normalization belong to the Data Layer |
| A strategy itself | The engine is the runtime environment; strategy logic lives in strategy modules |
| A forward testing engine | Forward testing operates against live or near-live data; backtesting operates against historical data exclusively |

---

# Conceptual Execution Flow

The backtesting engine follows a deterministic sequence.

```text
Validated Strategy Definition
    ↓
Backtest Run Request (parameters, dataset identity, assumptions)
    ↓
Registry Snapshot Capture (pin exact tool versions)
    ↓
Dataset Resolution (identify exact dataset version and slice)
    ↓
Dependency Graph Resolution (resolve tool order from registry snapshot)
    ↓
Data Windowing (apply warmup, lookback, and time boundary constraints)
    ↓
Bar-by-Bar Historical Replay:
    ├── Feature Computation (tool execution in dependency order)
    ├── Condition Evaluation
    ├── Rule Evaluation
    ├── Signal Generation
    ├── Filter Evaluation
    ├── Confirmation Evaluation
    ├── Risk Rule Evaluation
    └── Execution Intent Generation
    ↓
Simulated Execution Layer:
    ├── Fill Modeling
    ├── Fee Application
    ├── Slippage Modeling
    └── Order State Management
    ↓
Portfolio and Position State Update
    ↓
Metrics Computation
    ↓
Backtest Result Artifact Assembly
    ↓
Audit Record Persistence
```

Every step in this sequence must be deterministic, traceable, and reproducible.

---

# Input Contract Philosophy

A backtest run is defined by its full set of inputs.

Every input must be explicitly declared, recorded, and resolvable.

## Required Conceptual Inputs

**Validated Strategy Definition**
The strategy definition must have passed backend validation before it can be submitted to the backtesting engine.

See Validated Strategy Definition Requirement.

**Registry Snapshot**
The exact state of the Tool Registry at the time of the backtest run, or an explicit declaration of tool versions to be used.

See Tool Resolution During Backtesting.

**Dataset Identity and Version**
A stable, versioned reference to the exact dataset to be used.

See Dataset Traceability.

**Instrument Universe**
The specific symbol or set of symbols to be evaluated.

For single-instrument strategies, this is a single symbol with its asset class, exchange, and currency context.

For multi-instrument strategies, this is a declared universe with explicit inclusion criteria.

**Timeframe**
The primary evaluation timeframe for the strategy.

Multi-timeframe strategies declare a primary timeframe and secondary timeframe references.

**Parameter Set**
The full parameter set applied to the strategy, including all tool parameters.

The parameter set must be explicitly declared and recorded — not inherited from defaults without explicit confirmation.

**Simulation Assumption Set**
A structured set of simulation mechanics assumptions:

* Fee model (flat, percentage, tiered)
* Fee rate(s)
* Slippage model (none, fixed, proportional, market-impact)
* Slippage value(s)
* Fill timing assumption (signal bar close, next bar open, custom delay)
* Partial fill handling
* Position sizing model (fixed size, fixed risk, percentage equity)
* Position sizing parameters

**Risk Assumption Set**
Analytical constraints applied during the simulation:

* Maximum open positions
* Maximum exposure per instrument
* Maximum drawdown threshold (if used as a simulation stop condition)
* Position holding period constraints

**Run Metadata**
Contextual information about the run:

* Run identifier
* Requested by (user or system)
* Request timestamp
* Intended purpose (research, validation, promotion review)
* Engine version

## Input Completeness Requirement

All inputs must be fully specified before the backtest run begins.

A backtest run must not begin with implicit, assumed, or defaulted inputs that are not explicitly recorded.

If a user does not specify a fee assumption, the system must apply a declared default and record it — not silently apply an undocumented default.

No input may be left undeclared in the audit record.

---

# Validated Strategy Definition Requirement

**Only backend-validated strategy definitions may be submitted to the backtesting engine.**

This is a non-negotiable architectural constraint.

## Why This Constraint Exists

If draft strategy definitions could bypass validation and enter the backtest engine:

* Tool references might not resolve correctly
* Dependency chains might be broken
* Parameter values might be invalid
* The resulting backtest would be based on a semantically invalid strategy definition
* The result would be misleading and potentially harmful to strategy evaluation

## Enforcement Philosophy

The backtesting engine must verify that the strategy definition it receives carries a valid backend validation record before proceeding.

A strategy definition without a current validation record must be rejected with a clear diagnostic message directing the user to submit for validation first.

A strategy definition whose validation record is stale — for example, if the underlying tool versions have been updated since validation — must produce a warning, and the user must explicitly confirm re-validation or proceed with the original validated version.

## Frontend Relationship

The frontend may display a "Run Backtest" action.

That action must verify that the current strategy definition carries a valid backend validation record before allowing submission to the backtesting engine.

The frontend must not expose a path from draft composition state directly to backtest execution.

---

# Dataset Traceability

Backtest results are only as meaningful as the data they were computed against.

Dataset traceability is therefore a first-class architectural requirement.

## Dataset Identity

Every dataset used in a backtest must have a stable identity that includes:

* Provider or source identifier
* Symbol and asset class
* Exchange or venue
* Timeframe
* Adjustment mode (unadjusted, split-adjusted, dividend-adjusted, fully adjusted)
* Currency denomination

## Dataset Versioning

Historical market data may be revised, corrected, or supplemented over time.

Datasets must be versioned so that:

* A backtest run can reference the exact version of the data it used
* Future re-runs can reproduce results against the same data version
* Data updates do not silently change the inputs of previously recorded backtest runs

## Dataset Completeness

Before beginning a backtest run, the engine must verify:

* The dataset covers the full requested date range
* The dataset has no gaps exceeding declared tolerances for the timeframe
* The dataset provides the warmup period required by the tools in the strategy definition

If dataset completeness requirements are not met, the backtest run must not begin. The engine must return a diagnostic indicating which data is missing.

## Missing Data Handling

When gaps exist within the data range (e.g., market holidays, trading halts, data provider outages):

* The gap handling strategy must be explicitly declared (skip, forward-fill, interpolate, or reject)
* The declared strategy must be recorded in the audit record
* The backtest result must note how many gap events occurred and how they were handled

No silent gap handling is permitted.

## Reproducible Dataset References

Audit records must preserve a dataset reference that is sufficient to reconstruct the exact input data used.

This may be a dataset version identifier, a hash of the data, or a stable pointer to the stored dataset snapshot.

The requirement is that a future reader of the audit record must be able to understand exactly what data was used.

---

# Tool Resolution During Backtesting

Tools must be resolved through the registry snapshot, not through the live registry state.

## Registry Snapshot Philosophy

When a backtest run begins, the engine must establish a registry snapshot — a frozen view of the tool versions it will use for the entire run.

The snapshot must record:

* Each tool referenced by the strategy definition
* The exact version of each tool used
* The exact versions of all transitive dependencies

Once the snapshot is established, the run must use those exact versions throughout.

**The backtesting engine must never silently resolve tool references to the latest available version.**

If a strategy definition was composed against Tool version 1.3.0 and the registry now contains version 1.4.0, the backtesting engine must use version 1.3.0 unless the user explicitly requests re-validation and re-runs against 1.4.0.

## Dependency Resolution Order

Tools must be executed in dependency order.

If Tool A produces Feature X, and Tool B requires Feature X, Tool A must execute before Tool B for every bar.

The dependency graph must be resolved once at the start of the run and applied consistently throughout.

Circular dependencies must be detected before the run begins and rejected with a clear diagnostic.

## Resolution Failure

If any tool in the strategy definition cannot be resolved from the registry snapshot — because the version was deprecated, retired, or removed — the backtest run must fail explicitly with a clear message identifying the unresolvable tool.

Silent fallback to alternative tool versions is not permitted.

---

# Feature Computation

Feature computation is the process of executing resolved tools against normalized historical data to produce the feature series consumed by conditions and rules.

## Computation Requirements

**Deterministic**: Given identical inputs (data, parameters, tool version), a tool must always produce identical feature outputs.

**Warmup-aware**: Each tool declares a warmup period. The engine must not evaluate conditions or rules using feature values from within the warmup period. The warmup period must be consumed before the strategy's evaluation window begins.

**Batch-oriented**: Backtesting operates over full historical windows, not bar-by-bar streams. Feature computation may be applied to the full dataset window at once where the tool supports it, provided no lookahead bias is introduced.

**Shared dependency execution**: When multiple tools in the strategy definition share an upstream dependency, the upstream tool must be executed once and its output shared. Recomputing the same upstream tool multiple times is a correctness and efficiency violation.

## Multi-Timeframe Feature Computation

Strategies may reference features computed on timeframes different from the primary evaluation timeframe.

The engine must:

* Compute features on each declared timeframe independently
* Align higher-timeframe feature values to the primary-timeframe bars without lookahead bias
* Apply the correct bar-alignment rule (a weekly feature value is only available to a daily bar after the weekly bar closes; it is not available during the weekly bar's construction)

See Lookahead Bias Prevention for the governing constraint.

## Normalization Requirement

All input data must pass through the normalization layer before reaching feature computation.

Tools must never receive raw provider-native data structures.

The normalized internal schema is the only valid input.

---

# Condition and Rule Evaluation

Conditions and rules are evaluated historically over the feature-computed dataset.

## Evaluation Philosophy

**Bar-by-bar**: Conditions and rules are evaluated at each bar in the historical window, in time order, from oldest to newest.

**No lookahead**: At bar N, the evaluator may only access feature values computed from data up to and including bar N. It may never access data from bars N+1, N+2, or any future bar.

**Deterministic**: Given identical feature values, condition evaluation must produce identical results.

**Complete evaluation**: All conditions in the strategy definition must be evaluated at every bar, not just at bars where a signal was generated. This ensures that signal absence (no signal generated) is also a meaningful and traceable outcome.

## Rule Logic

Logical operators (AND, OR, NOT) must be evaluated correctly over the condition set at each bar.

Nested rule groups must be evaluated with correct precedence.

The evaluation order within a rule group must be deterministic.

## Signal Annotation

When a rule evaluation produces a signal, the bar at which the signal was generated must be recorded:

* The exact timestamp
* The values of the conditions that contributed to the signal
* The feature values at signal time
* The rule or rules that fired

This signal diagnostic information must be available in the result artifact for research inspection.

---

# Simulated Execution Layer

The simulated execution layer interprets execution intents produced by the strategy and models what would have happened under declared execution assumptions.

## Responsibilities

The simulated execution layer is responsible for:

* **Fill modeling** — determining whether and when an intent would have been filled given historical price data
* **Fee application** — applying declared fee assumptions to each trade
* **Slippage modeling** — adjusting fill prices according to the declared slippage model
* **Partial fill handling** — modeling scenarios where full size cannot be filled
* **Order state management** — tracking open, filled, partially filled, expired, and rejected orders
* **Position state** — maintaining the current position state after each fill

## What the Simulated Execution Layer Is NOT

* It is not a live broker connection
* It is not a paper trading engine (paper trading operates against live market data)
* It is not a strategy — the simulated execution layer does not make analytical decisions
* It is not the risk enforcement layer — it applies declared risk assumptions but does not invent them

## Execution Assumption Transparency

All execution mechanics must be governed by declared assumptions from the input contract.

No hidden execution assumptions are permitted.

If the fill timing model assumes fills occur at the open of the bar following the signal, this must be declared and recorded.

If the fill timing model assumes fills occur at the signal bar's close, this must be declared and recorded.

Different fill timing assumptions produce materially different backtest results and must be clearly identified.

## Broker Abstraction

The simulated execution layer must not contain broker-specific logic.

It models generic execution mechanics (fills, fees, slippage, position state).

Broker-specific normalization, order type translation, and margin calculations belong in the Broker Adapter Layer — which the backtesting engine does not interact with directly.

---

# Portfolio and Position State

The backtesting engine must maintain a simulated portfolio and position state throughout the simulation horizon.

## Position Tracking

At every bar, the engine must know:

* Which positions are currently open
* The entry price of each open position
* The current size of each open position
* The current unrealized profit/loss of each open position
* The time elapsed since each position was opened

## Trade Lifecycle

Each trade must have a complete lifecycle record:

* Entry signal timestamp and price
* Entry fill timestamp and price
* Entry fee
* Position size
* Exit signal timestamp and price (if applicable)
* Exit fill timestamp and price (if applicable)
* Exit fee
* Realized profit/loss
* Hold duration
* Exit reason (signal exit, stop, time expiry, end-of-simulation close)

## Cash and Equity State

At every bar, the engine must know:

* Cash balance (available capital)
* Equity value (cash + unrealized position value)
* Net exposure (total long minus total short exposure as a proportion of equity)
* Peak equity (highest equity achieved to date)
* Current drawdown (distance from peak equity to current equity)
* Maximum drawdown (deepest drawdown experienced to date)

## Portfolio-Level Constraints

Declared portfolio constraints must be enforced by the simulated execution layer:

* Maximum number of concurrent open positions
* Maximum exposure per instrument
* Maximum total portfolio exposure

When a constraint would be violated by a new execution intent, the intent must be rejected or queued according to declared handling rules.

---

# Metrics and Result Artifacts

The backtesting engine produces structured result artifacts containing analytical metrics and diagnostic data.

## Conceptual Metric Categories

**Return Metrics**
Measures of overall return performance:

* Total return (percentage and absolute)
* Annualized return
* Return relative to a declared benchmark or baseline

**Risk Metrics**
Measures of downside and variability:

* Maximum drawdown (peak-to-trough)
* Average drawdown
* Drawdown duration
* Volatility of returns
* Value at Risk (conditional, historical)

**Risk-Adjusted Metrics**
Combined return and risk measures:

* Sharpe-style ratio (return / volatility)
* Sortino-style ratio (return / downside deviation)
* Calmar-style ratio (return / maximum drawdown)

**Trade Statistics**
Measures of individual trade performance:

* Total trades
* Win rate (percentage of winning trades)
* Average winning trade return
* Average losing trade return
* Profit factor (total gross profit / total gross loss)
* Average hold duration (winners and losers)
* Maximum consecutive wins
* Maximum consecutive losses

**Signal Diagnostics**
Analytical information about signal generation:

* Total signals generated
* Signal frequency (per period)
* Signal distribution across the time range
* False positive candidates (signals not resulting in trades due to filters or constraints)

**Feature Diagnostics**
Analytical information about feature computation:

* Warmup period consumed
* Any bars excluded due to feature unavailability
* Multi-timeframe alignment events

**Execution Diagnostics**
Information about the simulated execution:

* Total trades attempted vs. filled
* Rejected trades (due to position constraints or portfolio limits)
* Total fees paid
* Total slippage applied

**Warnings and Anomalies**
Non-fatal issues encountered during the run:

* Data gaps encountered and how they were handled
* Bars excluded from evaluation
* Parameters at constraint boundaries
* Tool deprecation warnings
* Any other non-fatal conditions affecting result interpretation

## Equity Curve

The equity curve is a time-series of the simulated portfolio's equity value at each bar throughout the simulation horizon.

The equity curve is a primary result artifact.

It must be available for visualization in the frontend.

## Trade List

The full trade list is a result artifact containing the complete lifecycle record of every trade simulated.

The trade list must be inspectable and exportable for further research analysis.

## Result Artifact Versioning

Result artifacts must be versioned and traceable to their producing run.

A result artifact without a traceable run identifier and input audit record is not a valid backtest result.

---

# The Reproducibility Contract

The reproducibility contract is the most important governance constraint in the backtesting architecture.

## The Requirement

Given identical:

* Strategy definition (same version)
* Registry snapshot (same tool versions)
* Dataset (same version and slice)
* Parameter set
* Simulation assumption set
* Engine version

The backtesting engine must produce **identical results**.

Not approximately identical.

Numerically identical.

Deterministically identical.

## Why Reproducibility Is Non-Negotiable

A backtest result that cannot be reproduced is a research artifact of unknown validity.

If two runs of the same strategy against the same data produce different results, the difference could be due to:

* Different data versions (undocumented)
* Different tool versions (silently resolved to latest)
* Different execution assumptions (implicitly defaulted)
* Non-deterministic computation in a tool
* Engine bugs

Without reproducibility, none of these causes can be identified.

Reproducibility is what transforms a backtest from a number into evidence.

## Reproducibility Threats

The following are explicit threats to reproducibility that the architecture must prevent:

**Silent tool version resolution**: Using the latest tool version instead of the pinned version changes feature computation and invalidates reproducibility.

**Non-deterministic feature computation**: Any tool that uses random number generation, time-of-day-dependent behavior, or external state must be explicitly controlled or excluded.

**Undeclared execution assumptions**: A fill timing model that is not recorded in the audit allows the assumption to change between runs.

**Data mutations**: If the underlying dataset is modified after a backtest run without version tracking, re-running the same backtest will use different data.

**Engine version changes**: A bug fix in the backtesting engine may change results. Engine version must be recorded so that the source of any result difference can be identified.

---

# Audit Record Philosophy

Every backtest run must produce an immutable, complete audit record.

## Required Audit Contents

**Run Identity**

* Unique run identifier
* Run timestamp
* Requested by
* Run purpose (research, validation, promotion review)

**Strategy Definition Reference**

* Strategy definition ID
* Strategy definition version
* Validation record reference

**Tool Resolution Record**

* Each tool ID and version used
* Each dependency resolved
* Registry snapshot reference or hash

**Dataset Record**

* Dataset identity (provider, symbol, timeframe, asset class, exchange)
* Dataset version
* Requested date range
* Actual evaluated date range (excluding warmup)
* Data gap summary

**Parameter Record**

* Full parameter set applied
* Source of each parameter (user-declared, strategy default, system default)

**Simulation Assumption Record**

* Fee model and rate(s)
* Slippage model and value(s)
* Fill timing model
* Position sizing model and parameters
* Portfolio constraint declarations
* Risk assumption declarations

**Engine Record**

* Engine version
* Execution timestamp

**Result Summary**

* Reference to the result artifact
* Key metrics summary (for quick inspection without loading full artifact)
* Warning count
* Error flag (if any non-fatal errors occurred)

## Immutability

Audit records must be immutable after creation.

A backtest run's audit record must not be modified after the run completes.

If a run is re-executed, a new audit record must be created for the new run.

Old audit records must be preserved.

## Audit Record Accessibility

Audit records must be accessible through the platform's inspection interfaces.

A user must be able to review any historical backtest run's full audit record without running the backtest again.

---

# Lookahead Bias Prevention

Lookahead bias is the use of future data in historical evaluation.

It is the single most common cause of backtest results that do not transfer to live trading.

**Lookahead bias prevention is a non-negotiable architectural constraint.**

## What Lookahead Bias Looks Like

* At bar N, using the close price of bar N+1 to generate a signal
* Using a moving average computed over a window that includes future bars
* Using a daily close price to generate an intraday signal at a time before that close is available
* Using an economic report value on the day it was released before its official release time
* Using a higher-timeframe bar value before that bar has closed

## Engine-Level Controls

The backtesting engine must enforce bar-level data access discipline.

At evaluation time T:

* Only data with timestamp ≤ T may be used
* Feature computation must use data slices bounded by T
* No mechanism for accessing future data may be exposed to strategy logic

## Multi-Timeframe Lookahead Rules

Multi-timeframe strategies are a common source of lookahead bias.

When a strategy uses weekly data alongside daily data:

* A weekly bar's close value must not be used in daily evaluation until the weekly bar has closed
* The alignment must be strict: a Monday's daily bar cannot access the weekly bar closing on Friday until the following Monday

The engine must enforce correct bar alignment for all declared timeframe combinations.

## Lookahead Audit

The audit record must note whether any lookahead-prevention violations were detected during the run.

Any detected violation must cause the run to fail with an explicit diagnostic.

Silent toleration of potential lookahead bias is not permitted.

---

# Research vs. Validation vs. Promotion-Grade Backtesting

Not all backtests serve the same purpose.

The backtesting engine must support distinct run modes with different strictness requirements.

## Research-Grade Backtest

**Purpose**: Exploratory analysis, hypothesis testing, parameter exploration.

**Strictness**: Standard reproducibility requirements apply. Warnings do not block the run.

**Constraints**:
* Strategy definition must be validated
* Dataset must be identified
* Assumptions must be declared

**Lifecycle impact**: Research-grade backtest results may be inspected but do not constitute evidence for lifecycle promotion.

## Validation-Grade Backtest

**Purpose**: Confirming that a strategy's behavior is consistent, reproducible, and meets declared performance expectations before lifecycle promotion.

**Strictness**: Higher than research-grade. All warnings must be resolved or explicitly acknowledged.

**Constraints**:
* All research-grade constraints apply
* No deprecated tool versions may be used
* No experimental tools may be referenced
* The dataset must be versioned and complete for the full evaluation period
* Simulation assumptions must be explicitly specified (no defaulting without acknowledgment)

**Lifecycle impact**: Validation-grade backtest results are the primary evidence for promotion from validated to backtested lifecycle state.

## Promotion-Grade Backtest

**Purpose**: Final evaluation before forward testing or paper trading approval.

**Strictness**: Highest. No warnings without explicit override and justification.

**Constraints**:
* All validation-grade constraints apply
* Out-of-sample dataset required (a date range not used in prior validation-grade runs)
* Full audit record review required before promotion is authorized
* Explicit human or authorized system approval required

**Lifecycle impact**: Promotion-grade backtest approval is required for lifecycle advancement to forward testing or paper trading.

---

# Multi-Timeframe Backtesting

Multi-timeframe strategies require special coordination in the backtesting engine.

## Alignment Philosophy

The engine must maintain separate data windows for each declared timeframe.

Feature computation for each timeframe must be independent.

Higher-timeframe feature values must be aligned to primary-timeframe bars without lookahead.

## Warmup Coordination

Each timeframe has independent warmup requirements.

The effective start of the evaluation window is determined by the maximum warmup requirement across all timeframes, converted to the primary timeframe bar count.

The engine must not begin evaluation until all timeframes have completed their warmup periods.

## Timeframe Synchronization

At each primary-timeframe bar:

* Higher-timeframe feature values must be the most recently closed bar of that timeframe
* A weekly feature value on a Wednesday is the feature value from the most recently closed weekly bar (previous Friday)
* The engine must never forward-fill a higher-timeframe value with data not yet available at the evaluation timestamp

---

# Compliance and Policy Hooks

The backtesting engine must support configurable compliance and policy enforcement.

## Philosophy

Compliance rules — including halal constraints, jurisdiction restrictions, instrument restrictions, and broker-specific policies — must not be hardcoded in the core backtest engine.

They must be expressible as configurable policy layers that can be attached to a backtest run.

## Policy Hook Expectations

The backtesting engine architecture must accommodate:

* **Instrument eligibility filters** — policies that prevent evaluation of signals for instruments that do not meet declared criteria
* **Transaction filters** — policies that prevent simulated trades that violate declared rules (e.g., short selling restrictions, leverage restrictions)
* **Exposure policies** — policies that limit exposure to particular sectors, asset classes, or geographies
* **Timing policies** — policies that restrict trading to declared market sessions or calendar periods

## Policy Transparency

All active policy hooks must be declared and recorded in the audit record.

A backtest run with compliance filters applied must distinguish in its results between:

* Signals not executed due to execution assumption constraints
* Signals not executed due to active policy filters

These are analytically different outcomes and must be identifiable separately.

---

# Frontend Relationship

The frontend interacts with the backtesting engine as a requester and result visualizer.

## Frontend Responsibilities

* **Request submission**: The user initiates backtest runs through the frontend composition interface after the strategy definition has been validated
* **Result visualization**: The frontend receives and renders backtest result artifacts — equity curves, trade lists, metric summaries, signal markers on charts
* **Audit inspection**: The user reviews audit records through the frontend
* **Promotion workflow**: The user initiates lifecycle promotion requests through the frontend, which are authorized by the backend

## Frontend Forbidden Responsibilities

* **Official backtest computation**: The frontend must not calculate backtest metrics, simulate trades, or generate performance statistics
* **Result certification**: The frontend must not present frontend-computed analysis as official backtest results
* **Assumption injection**: The frontend must not inject undeclared execution assumptions into the backtest run without recording them
* **Draft strategy execution**: The frontend must not allow a draft (unvalidated) strategy definition to be submitted to the backtesting engine

## Result Visualization Philosophy

Backtest result visualization follows the same generic rendering principle established in the Frontend Composition Interface Contract:

The frontend renders result artifacts based on their declared type — equity curves, trade markers, drawdown series, indicator overlays — without coupling rendering logic to the identity of the strategy or the specific tools used.

---

# Forbidden Patterns

The following patterns are architectural violations in the backtesting system.

Implementations exhibiting these patterns must be identified and refactored.

**Frontend calculating official backtest results**
All simulation mechanics, feature computation, rule evaluation, and metric calculation belong to the backend backtesting engine.

**Draft strategies running without backend validation**
A strategy definition without a current backend validation record must be rejected by the engine before any computation begins.

**Implicit tool version resolution**
Using the latest registered tool version instead of the version declared in the strategy definition or registry snapshot is a reproducibility violation.

**Strategy controlling simulated execution mechanics**
The strategy definition declares what execution intents to produce. The simulated execution layer decides how to fill them. The strategy must not embed fill timing, fee calculation, or slippage logic.

**Provider-native data schemas entering feature computation**
All data must pass through the normalization layer before reaching tools. Raw provider payloads must never reach the strategy layer.

**Lookahead bias**
Any mechanism by which future bar data influences current bar evaluation is an architectural violation. The engine must enforce strict data access discipline.

**Hidden execution assumptions**
Execution assumptions that affect simulation results but are not declared in the input contract or recorded in the audit record are prohibited.

**Unrecorded dataset versions**
A backtest whose dataset cannot be exactly identified and versioned is not a valid research artifact.

**Non-deterministic backtest outputs**
Backtest results that differ between runs given identical declared inputs are an architectural failure and must be investigated and resolved.

**Compliance logic hardcoded in the engine or strategy**
Compliance and policy rules must be implemented as configurable policy hooks, not hardcoded in the core engine or individual strategy definitions.

**Unacknowledged warnings treated as non-warnings**
Warnings in a validation-grade or promotion-grade backtest run must be explicitly acknowledged before the run is considered complete. Silent warning suppression is prohibited.

---

# Governance Relationships

The Backtesting Engine Contract governs the historical simulation layer.

It relates to other platform contracts as follows:

| Contract | Relationship |
|---|---|
| `docs/STRATEGY_DEFINITION_ARCHITECTURE.md` | Defines the vocabulary of strategy definitions. The backtesting engine consumes those definitions as its primary input. |
| `docs/TOOL_REGISTRY_CONTRACT.md` | Defines the Tool Registry and versioning governance. The backtesting engine resolves tools through registry snapshots governed by this contract. |
| `docs/FRONTEND_COMPOSITION_INTERFACE_CONTRACT.md` | Defines the frontend composition workflow. The backtesting engine is the backend consumer of strategy definitions produced by that workflow. |
| `docs/STRATEGY_CONTRACT.md` | Defines the strategy module callable interface. The backtesting engine invokes those callables during bar-by-bar historical replay. |
| `docs/DATA_CONTRACT.md` | Defines normalized data schemas. All data entering the backtesting engine must conform to these schemas. |
| `docs/EXECUTION_CONTRACT.md` | Defines how execution intents are handled. The backtesting engine's simulated execution layer is a simulation of the behavior described in the Execution Contract. |
| `docs/ARCHITECTURE.md` | Defines the Backtesting Layer and its responsibilities. This contract elaborates the Backtesting Layer's internal architecture. |

---

# Summary of Backtesting Engine Responsibilities

```text
INPUT GATE
    → Validate: strategy definition is backend-validated
    → Establish: registry snapshot (pin tool versions)
    → Resolve: dataset identity and version
    → Declare: full simulation assumption set

COMPUTATION LAYER
    → Resolve: tool dependency graph
    → Compute: features across historical window (warmup-aware, lookahead-free)
    → Evaluate: conditions, rules, signals bar by bar
    → Apply: filters and confirmations
    → Evaluate: risk rules
    → Generate: execution intents

SIMULATION LAYER
    → Model: fills (timing, slippage, fees)
    → Manage: position and portfolio state
    → Apply: policy hooks (compliance, exposure limits)
    → Record: trade lifecycle

OUTPUT LAYER
    → Compute: result metrics
    → Assemble: result artifacts (equity curve, trade list, diagnostics)
    → Persist: immutable audit record
    → Return: structured results to calling system

ENFORCEMENT
    → No future data access
    → No implicit tool version resolution
    → No unrecorded assumptions
    → No draft strategy execution
    → Deterministic output guarantee
```

The backtesting engine transforms a validated strategy definition into historical evidence.

That evidence is only as valuable as the engine's commitment to determinism, traceability, and reproducibility.

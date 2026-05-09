# TOOL_REGISTRY_CONTRACT.md

## Purpose

This document defines the architectural contract for the Tool Registry in QuantLab.

The Tool Registry is the authoritative platform index of all recognized analytical tools and modules.

This document establishes:

* what the Tool Registry is and why it exists
* the conceptual identity of a Tool as a registered entity
* tool categorization and discovery philosophy
* tool metadata philosophy
* tool versioning and lifecycle governance
* experimental vs. stable tool governance
* dependency declaration philosophy
* visualization capability metadata philosophy
* runtime compatibility metadata philosophy
* frontend and backend responsibility boundaries
* registry determinism philosophy
* future extensibility direction

This document is architecture-level.

It is intentionally implementation-agnostic.

Specific database schemas, API routes, registry storage implementations, and frontend framework details belong in their respective implementation contracts.

---

# Why the Tool Registry Exists

QuantLab is built on the premise that strategies are composed from reusable tools.

Without a registry, that premise cannot be enforced or governed.

The Tool Registry exists to answer the following questions with authority:

* What tools are available on this platform?
* What does each tool require as input?
* What does each tool produce as output?
* Is this tool ready for production use or still experimental?
* Which version of this tool was used in a given backtest run?
* Does this tool support live streaming or only historical batch computation?
* What visualizations can this tool's output produce?
* What other tools does this tool depend on?

Without a registry, tools become implicit knowledge scattered across the codebase.

With a registry, tools become first-class platform entities — discoverable, governable, versionable, and auditable.

---

# What the Tool Registry Is

The Tool Registry is the authoritative platform index of all recognized analytical tools and modules.

Its responsibilities are:

* **Discovery** — exposing what tools exist and what they can do
* **Metadata governance** — maintaining structured descriptions of each tool's identity, capabilities, and requirements
* **Compatibility tracking** — recording which runtime modes, timeframes, and input types each tool supports
* **Versioning** — tracking tool versions and their compatibility with strategy definitions
* **Dependency management** — declaring and tracing inter-tool dependencies
* **Lifecycle governance** — tracking each tool's maturity status from experimental through stable to deprecated

## What the Tool Registry Is NOT

| Not this | Why |
|---|---|
| A strategy runtime | The registry describes tools; the runtime executes them |
| A broker layer | The registry has no awareness of order routing or execution |
| A frontend component | The registry is backend-authoritative; the frontend queries it |
| A visualization engine | The registry declares visualization capabilities; it does not render |
| An execution authorization system | Registration is governance, not permission to trade |
| A data storage layer | The registry manages metadata; data pipelines store market data |

---

# Tool Identity

Every tool registered in the Tool Registry must have a stable, deterministic identity.

## Core Identity Concepts

**`tool_id`**
A unique, stable, machine-readable identifier for the tool.

Once assigned, a `tool_id` must not change.

A new version of a tool retains the same `tool_id` but increments its version.

A fundamentally different tool must receive a different `tool_id`.

**`tool_name`**
A human-readable canonical name for the tool.

Examples: `moving_average`, `rsi`, `macd`, `planetary_longitude`, `volatility_regime_classifier`

Tool names must be stable. Renaming a tool is a versioning event.

**`tool_category`**
The classification of the tool within the ecosystem's organizational structure.

See Tool Categorization section.

**`tool_version`**
A structured version identifier following a semantic scheme (major.minor.patch or equivalent).

Version must increment whenever the tool's behavior, interface, or outputs change.

**`tool_status`**
The current lifecycle stage of the tool.

See Tool Lifecycle section.

**`feature_outputs`**
A declaration of the named Features this tool produces.

Each declared output must be named and typed so that dependent tools and conditions can reference it.

**`dependency_requirements`**
A declaration of other tools or input feature types this tool requires.

**`runtime_compatibility`**
A declaration of which runtime modes this tool supports.

**`parameter_schema`**
A declaration of the parameters this tool accepts, their types, defaults, and constraints.

The parameter schema is what the frontend composition interface uses to render configuration forms.

## Identity Stability Rules

* `tool_id` must never change after first registration
* `tool_name` must never change without a versioning event
* `feature_outputs` naming must remain stable within a major version
* Parameter removal is a breaking change and requires a major version increment
* Parameter addition with a default is backward-compatible and requires only a minor version increment

---

# Tool Categorization

Tool categories organize the ecosystem for discovery, composition workflows, and validation.

Categories are organizational — they are not rigid inheritance hierarchies.

A tool may belong to one primary category and optionally declare secondary capabilities.

## Primary Categories

**Indicators**
Classical analytical computation modules.

Examples: moving averages, oscillators, momentum indicators, volatility bands, volume-weighted indicators.

These tools transform normalized price and volume data into derived analytical series.

**Feature Generators**
Modules that produce derived features from non-classical or unconventional data sources.

Examples: planetary phase generators, sentiment score generators, harmonic ratio calculators, cycle phase classifiers, macro regime classifiers.

These tools extend the feature space beyond classical market data.

**Filters**
Tools designed to produce boolean or categorical outputs used for signal gating.

Examples: trend filter, volatility regime filter, session filter, liquidity filter, drawdown filter.

Filters are consumed by the Signal filtering layer of a strategy definition.

**Confirmations**
Tools designed to produce confidence-modulating outputs.

Examples: volume confirmation scorer, multi-timeframe alignment scorer, secondary momentum confirmation.

Confirmations are consumed by the Confirmation layer of a strategy definition.

**Risk-Analysis Tools**
Tools that produce analytical risk context.

Examples: invalidation level calculator, volatility-scaled stop estimator, market structure risk classifier.

These tools inform the Risk Rule layer of a strategy definition.

**Transformation Tools**
Tools that transform or normalize features rather than compute new analytical domains.

Examples: z-score normalization, log return transformation, rolling percentile rank, cross-sectional normalization.

**Aggregation Tools**
Tools that aggregate multiple features or signals into composite outputs.

Examples: composite momentum scorer, multi-indicator confluence aggregator, weighted signal combiner.

**Experimental Research Tools**
Tools in early-stage development or hypothesis testing.

These tools may not conform to all standard requirements.

They must be clearly marked experimental and must not be promoted to production strategy definitions without validation.

## Why Categorization Matters

Categories enable:

* **Discovery** — frontend can present tools organized by analytical purpose
* **Composition guidance** — the builder interface can suggest appropriate tools for each strategy layer (entry rules vs. filters vs. confirmations)
* **Validation** — the backend can verify that a tool used in a filter layer is actually a filter-capable tool
* **Governance** — experimental tools can be isolated from production strategy definitions

Categories are a discovery and governance mechanism, not a type system.

---

# Tool Metadata Philosophy

Each registered tool must expose structured metadata.

Metadata exists to support frontend composition, backend validation, runtime orchestration, reproducibility, and auditability.

Metadata must remain deterministic and versioned alongside the tool.

## Parameter Definitions

Each parameter a tool accepts must be declared with:

* a stable name
* a type declaration (numeric, boolean, categorical, timeframe, etc.)
* a default value
* constraints (range limits, valid values, mutual exclusivity with other parameters)
* a description of the parameter's analytical purpose

Parameter declarations are what the frontend uses to render composition forms.

They are also what the backend uses to validate strategy definitions.

## Input Type Declarations

A tool must declare what types of inputs it requires.

Examples of input types:

* normalized OHLCV close prices
* normalized OHLCV volume
* a named Feature produced by another tool
* a non-market dataset (planetary positions, sentiment scores, macro values)

Input declarations enable the backend to verify that all required data is available before executing a tool.

## Feature Output Declarations

A tool must declare the named Features it produces.

Each declared output Feature must have:

* a stable name (e.g., `ma20`, `rsi_14`, `cycle_phase`, `harmonic_completion_ratio`)
* a type declaration (scalar series, categorical series, boolean series, probability series)
* a description of the analytical meaning

Named output Features are what Conditions in a strategy definition reference.

If a tool renames an output Feature, it is a breaking change and requires a major version increment.

## Warmup Requirement Declaration

Many tools require a minimum number of bars before producing meaningful output.

This is the "warmup period."

A tool must declare its warmup requirement so the runtime can:

* ensure sufficient data exists before evaluation begins
* correctly handle the initial bars where output is undefined or unreliable

## Statefulness Declaration

A tool must declare whether it is stateful or stateless.

**Stateless tools** produce outputs from a fixed window of historical data with no internal state carried between bars.

**Stateful tools** maintain internal state that accumulates across bars (examples: certain adaptive moving averages, models with feedback loops, running classifiers).

Statefulness has significant implications for backtesting reproducibility and forward-testing initialization.

## Supported Timeframes

A tool must declare which timeframes it supports.

Some tools are timeframe-agnostic.

Others are designed for specific granularities (e.g., a daily seasonality tool is not meaningful on a 1-minute timeframe).

## Supported Asset Classes

A tool may declare which asset classes it is designed or validated for.

Examples: equities, crypto, forex, futures, commodities.

This declaration is advisory — it informs the composition interface and validation warnings, not hard rejection.

## Visualization Artifact Capabilities

See dedicated section below.

## Runtime Compatibility

See dedicated section below.

---

# Tool Discovery Philosophy

The Tool Registry must support dynamic discovery of available tools.

Discovery must be backend-authoritative.

Frontend systems must not maintain their own hardcoded registry of available tools.

## Discovery Principles

**Metadata-driven**: The frontend discovers tools by querying the registry, not by hardcoding knowledge of specific tools.

**Category-filtered discovery**: The frontend should be able to discover tools filtered by category, runtime mode, status, or asset class.

**Capability-aware discovery**: Strategy composition workflows should be able to discover tools appropriate for a specific layer (e.g., "which tools can be used as filters?").

**Status-filtered discovery**: Production composition workflows should default to discovering only stable or validated tools. Experimental tools should be discoverable only in explicitly research-mode contexts.

## What Discovery Enables

* The frontend strategy builder can render a dynamic tool palette without frontend code changes when new tools are registered.
* Backend validation can verify tool references without maintaining a parallel registry in the execution layer.
* Research workflows can explore available tools and their capabilities without reading source code.

---

# Runtime Resolution Philosophy

Runtime resolution is the process by which a strategy definition's Tool references are translated into executable analytical modules at execution time.

## Core Resolution Principles

**Deterministic**: Given the same registry state and the same strategy definition, resolution must always produce the same result.

**Version-pinned**: A strategy definition should declare the specific versions of its Tools. Resolution must use those exact versions, not the latest versions available.

**Dependency-aware**: If Tool A depends on Tool B, resolution must ensure Tool B is resolved and its output Features are available before Tool A executes.

**Reproducibility-preserving**: Resolution for a historical backtest must use the exact Tool versions that were active at the time of the original run, not the current versions.

## Resolution Order

Tools must be resolved in dependency order.

If Tool A requires Feature X produced by Tool B, Tool B must be resolved and executed before Tool A.

Circular dependencies are architectural violations and must be rejected at validation time.

## Resolution Failure Behavior

Resolution must fail explicitly when:

* A referenced Tool ID is not found in the registry
* A referenced Tool version is not available
* A required dependency cannot be resolved
* A declared input Feature is not available from the resolved dependency chain

Silent fallback to alternative tools is not permitted.

Resolution failures must produce clear, traceable diagnostic messages.

---

# Tool Versioning Governance

## Versioning Philosophy

All tools must be versioned.

Version changes must follow a disciplined policy:

| Change Type | Version Impact | Examples |
|---|---|---|
| Bug fix that does not change outputs | Patch increment | Fix in internal calculation that corrects an existing error |
| New optional parameter added with default | Minor increment | Add optional `smoothing_method` parameter defaulting to existing behavior |
| Behavioral change that changes outputs | Major increment | Change MA calculation method from SMA to EMA within the same tool |
| Output Feature renamed | Major increment | Rename `ma_value` to `ma_line` |
| Required parameter added | Major increment | Add required `window_type` parameter with no default |
| Output Feature removed | Major increment | Remove `signal_line` output from MACD tool |

## Backward Compatibility Expectations

**Minor and patch versions** must remain backward-compatible.

A strategy definition using Tool version 1.3.0 must be resolvable with Tool version 1.4.0 without modification.

**Major versions** break compatibility.

A strategy definition must be explicitly migrated to reference a new major version.

Automatic silent migration is not permitted.

## Version Pinning in Strategy Definitions

Strategy definitions must declare the specific Tool version they were composed against.

A strategy pinned to Tool version 1.3.x must remain resolvable for the lifetime of that version in the registry.

Registry housekeeping must not remove Tool versions that are referenced by existing strategy definitions without a migration plan.

## Deprecation Policy

When a Tool version is deprecated:

* The tool remains in the registry with a `deprecated` status
* Existing strategy definitions referencing the deprecated version continue to resolve
* New strategy composition is warned against using deprecated versions
* A migration path to the replacement version must be documented

When a Tool is retired:

* The tool is marked `retired` in the registry
* The registry retains the metadata for auditability
* Runtime resolution of retired tool versions must fail explicitly with a clear migration message

---

# Tool Lifecycle

Every tool in the registry belongs to a lifecycle stage.

## Lifecycle Stages

**Unregistered**
The tool exists in the codebase but is not yet formally registered.

It has no registry entry.

It is not discoverable through the registry.

It must not be used in strategy definitions.

**Experimental**
The tool is registered but explicitly marked as experimental.

Experimental tools:

* may change interface rapidly
* may produce unstable outputs
* may be used in research-mode strategy definitions
* must not be promoted to backtesting or production strategy definitions without validation
* must be clearly labeled as experimental in discovery responses

**Prototype**
The tool has a stable interface candidate but has not yet been validated against real-world data.

Prototype tools:

* have a declared parameter schema
* have declared output Features
* may still evolve in behavior
* may be used in isolated validation workflows

**Validated**
The tool has been tested against real data and its behavior is confirmed.

Validated tools:

* have a stable interface
* have documented behavior
* may be used in backtesting strategy definitions

**Stable**
The tool is production-ready.

Stable tools:

* preserve compatibility within their major version
* are safe for use in backtesting, forward testing, and paper trading strategy definitions
* have documented warmup requirements, statefulness, and runtime compatibility

**Deprecated**
The tool has been superseded or retired from active development.

Deprecated tools:

* remain resolvable for existing strategy definitions
* must not be used in new strategy composition
* must have a documented migration path

**Retired**
The tool is no longer supported.

Retired tools:

* remain in the registry for auditability
* are not resolvable at runtime
* require explicit migration of any referencing strategy definitions

## Promotion Rules

Promotion between lifecycle stages requires:

* **Experimental → Prototype**: stable parameter schema declared; output Features named
* **Prototype → Validated**: confirmed behavior against real data; warmup and statefulness declared
* **Validated → Stable**: reproducibility confirmed across multiple datasets; no outstanding behavioral issues; runtime compatibility declared
* **Stable → Deprecated**: replacement tool identified; migration path documented
* **Deprecated → Retired**: all referencing strategy definitions have been migrated or archived

---

# Experimental vs. Stable Tool Governance

Experimental research capability is a first-class platform feature.

QuantLab intentionally supports the exploration and integration of unconventional analytical systems — including planetary cycles, harmonic formulas, AI-generated features, and other non-classical research tools.

These tools must remain accessible to researchers without being forced through a premature validation process.

At the same time, production strategy definitions must remain protected from unstable tools.

## The Governance Principle

**Experimental tools are discoverable and usable in research mode.**

**Experimental tools must not contaminate production strategy definitions.**

## Separation Mechanisms

The registry must clearly distinguish experimental from stable tools in all discovery responses.

Strategy definition validation must warn when experimental tools are referenced in a strategy targeting backtesting or production modes.

Strategy definition promotion (from research to backtest to paper trade) must block any strategy that contains unvalidated experimental tool references.

## Why Experimental Tools Are Supported

Not all research needs a production-validated tool.

A researcher exploring planetary cycle relationships needs to run the tool, see the output, iterate on the hypothesis, and draw conclusions — without waiting for the tool to be fully validated.

The registry must support this workflow while ensuring it does not accidentally bleed into production execution.

---

# Tool Dependency Governance

Tools may depend on other tools' output Features.

Dependency declarations must be explicit, stable, and version-aware.

## Dependency Declaration Principles

**Explicit**: If Tool A requires a Feature produced by Tool B, Tool A must explicitly declare that dependency by referencing Tool B's ID, version constraint, and output Feature name.

**No implicit dependencies**: A tool must not silently assume that another tool's output is available. Every required input Feature must be traceable to a declared dependency.

**Version-constrained**: A dependency declaration must specify a minimum compatible version. Example: Tool A requires Tool B version >= 1.2.0.

**Acyclic**: Dependency chains must form a directed acyclic graph. Circular dependencies are prohibited and must be rejected at registration or validation time.

## Dependency Resolution Chain Example

```text
Close Price Series (NormalizedData)
    ↓
EMA Tool (window=20) → ema_20 Feature
    ↓
MACD Tool (depends on ema_20, ema_26, ema_9) → macd_line, signal_line, histogram Features
    ↓
Momentum Confirmation Tool (depends on macd_line, signal_line) → momentum_score Feature
```

Each level of this chain must be explicit in each tool's dependency declaration.

## Shared Dependencies

Multiple tools within the same strategy definition may declare a dependency on the same upstream tool.

The runtime must resolve shared dependencies once and share the output Features, not compute them multiple times.

This is both an efficiency requirement and a correctness requirement — if two tools depend on the same upstream Feature, they must receive the same computed values.

---

# Visualization Capability Metadata

The Tool Registry must declare the visualization artifact types that each tool's output can produce.

This is distinct from rendering.

The registry declares **what can be visualized**.

The frontend decides **how to render it**.

## Visualization Capability Declarations

**`produces_line_overlay`**
The tool produces a continuous series suitable for rendering as a line overlay on a price chart.

Examples: MA, EMA, MACD signal line, Bollinger Band series.

**`produces_oscillator_series`**
The tool produces a bounded or unbounded oscillator series suitable for rendering in a separate pane.

Examples: RSI, MACD histogram, Stochastic oscillator.

**`produces_marker_annotations`**
The tool produces event-level outputs suitable for rendering as point markers on the chart.

Examples: Signal generators, pattern completion markers, harmonic structure points.

**`produces_regime_overlay`**
The tool produces a categorical regime classification suitable for rendering as a background color or zone overlay.

Examples: Volatility regime classifier, trend regime classifier, planetary cycle phase classifier.

**`produces_zone_overlay`**
The tool produces price range boundaries suitable for rendering as horizontal zones.

Examples: Support/resistance calculators, invalidation level calculators, Fibonacci zone generators.

**`produces_heatmap`**
The tool produces two-dimensional intensity data suitable for heatmap rendering.

Examples: Time-of-day seasonality maps, inter-market correlation maps.

**`no_visualization`**
The tool produces outputs that are consumed only by downstream tools or conditions, and have no direct visual representation.

Examples: Intermediate transformation tools, normalization tools, composite scorers.

## Why Visualization Metadata Belongs in the Registry

Frontend rendering must remain generic — it must render based on artifact type declarations, not based on knowledge of specific tool identities.

When the frontend receives output from a tool, it should consult the registry's visualization capability declaration to know what rendering options are available.

This preserves the architecture principle that the frontend must never be strategy-identity-aware or tool-identity-aware in its rendering logic.

---

# Runtime Compatibility Metadata

Each tool must declare which runtime modes it is compatible with.

## Runtime Mode Compatibility Declarations

| Mode | Description |
|---|---|
| `research` | Single-period or range-based evaluation; interactive exploration |
| `backtest` | Deterministic historical replay; bar-by-bar simulation |
| `forward_test` | Live or near-live data evaluation without real execution |
| `paper_trade` | Simulated execution against live data |
| `live_trade` | Future: real-time execution with live broker connectivity |

## Why Runtime Compatibility Matters

Some tools may not be suitable for all runtime modes.

Examples:

* A tool that requires network access to retrieve external data in real-time may not be suitable for a deterministic backtest.
* A tool designed for daily bars may not be suitable for tick-level live trading.
* An experimental AI-generated feature module may not yet support streaming data delivery.

The registry must expose these constraints so that:

* Strategy definition validation can warn when an incompatible tool is used in an incompatible runtime context.
* Runtime orchestration systems can inspect compatibility before execution begins.

## Streaming Compatibility

Live and forward-testing modes require tools that can operate in a streaming context.

A tool is streaming-compatible if it can produce correct output when delivered one bar at a time without requiring re-computation of the entire historical series.

A tool is batch-only if it requires the full historical window to produce output.

Batch-only tools must be clearly declared as incompatible with streaming runtime modes.

---

# Frontend and Backend Responsibility Boundaries

## Frontend Responsibilities

| Responsibility | Description |
|---|---|
| Tool discovery | Query the registry to discover available tools and their metadata |
| Category browsing | Present tools organized by category to the user |
| Parameter configuration | Render parameter input forms based on declared parameter schemas |
| Compatibility filtering | Show only tools compatible with the current strategy's runtime target |
| Status filtering | Default to showing stable tools; show experimental only in research contexts |
| Composition guidance | Suggest appropriate tools for each strategy layer based on category and capabilities |
| Visualization preview | Declare rendering expectations based on tool's visualization capability metadata |

The frontend must not:

* Maintain its own authoritative registry of available tools
* Hardcode tool-specific rendering logic based on tool identity
* Make assumptions about tool behavior beyond what the registry declares

## Backend Responsibilities

| Responsibility | Description |
|---|---|
| Authoritative registry state | The backend is the single source of truth for the registry |
| Tool registration | Tools are registered through backend processes, not through the frontend |
| Metadata validation | The backend validates that registered tools meet the structural requirements of the registry |
| Dependency validation | The backend validates and traces tool dependency graphs |
| Compatibility enforcement | The backend enforces runtime compatibility constraints during strategy validation |
| Version resolution | The backend resolves specific tool versions referenced by strategy definitions |
| Reproducibility tracking | The backend tracks which tool versions were used for each execution run |
| Deprecation enforcement | The backend enforces warnings and blocks on deprecated or retired tool usage |

## The Key Principle

The frontend discovers and presents.

The backend governs and enforces.

The registry is a backend concern.

The frontend is a consumer of registry information, not a maintainer of it.

---

# Registry Determinism Philosophy

Registry determinism is foundational to reproducible backtesting and auditable execution.

## The Requirement

Given:

* an identical strategy definition
* an identical registry state
* identical tool versions

The following must be true:

* Tool resolution produces the same set of resolved modules
* Dependency chains resolve in the same order
* Feature outputs are identical
* Signal outputs are identical

This is not merely a performance requirement.

It is an auditability requirement.

## Why Determinism Is Non-Negotiable

A backtest is only meaningful if it can be reproduced.

If the registry resolved different tool versions for the same strategy definition on different days, the backtest results would not be comparable or trustworthy.

An audit trail of a strategy run must record:

* The exact registry state at execution time
* The exact tool versions resolved
* The exact dependency chain resolved

This metadata is as important as the input data for reproducibility.

## Version-Pinned Execution Records

Every strategy execution — research, backtest, forward test, paper trade, or live — must record:

* The strategy definition version
* The registry snapshot or the specific tool versions resolved
* The timestamp of resolution

This record must be immutable after execution.

It must be possible to reconstruct the exact computational chain used for any historical execution.

## Registry State Snapshots

For long-running forward tests and live trading deployments, the registry must support a stable "snapshot" concept:

* A registry snapshot captures the resolved state of all tools referenced by a strategy definition at a specific point in time.
* The snapshot remains stable even if the live registry continues to evolve.
* A new strategy deployment creates a new snapshot.
* The existing deployment continues against its snapshot.

This prevents a tool update from silently changing the behavior of a running live strategy.

---

# Future Extensibility Philosophy

The Tool Registry architecture must remain open to continuous expansion.

## Expanding Tool Categories

New tool categories must be addable without modifying the core registry architecture.

Adding a "quantum signal analyzer" or a "social sentiment engine" category must not require changes to how existing tool categories function.

Categories are an organizational layer, not a core type system.

## Expanding Metadata Fields

New metadata fields must be addable to tool declarations without breaking existing registered tools.

Existing tools that do not declare new optional fields must continue to function normally.

Avoid designing a rigid closed metadata schema.

## Expanding Visualization Capabilities

New visualization artifact types must be addable as the frontend rendering system evolves.

Existing tools do not need to declare new visualization types unless they produce outputs appropriate to those types.

## Expanding Runtime Modes

When new runtime modes are added to the platform (e.g., a new live trading environment or a new simulation environment), the compatibility metadata system must accommodate them without requiring all existing tools to be re-registered.

Tools should default to compatibility-unknown for new runtime modes until explicitly tested and declared.

## Unconventional and AI-Generated Tools

The registry architecture must natively support unconventional tool types:

* Tools consuming astronomical datasets
* Tools consuming sentiment or alternative data
* Tools whose parameters include model weights or learned embeddings
* Tools that wrap AI-generated feature engines
* Hybrid tools combining classical and AI-generated features

These tools must conform to the same registration contract as classical indicators.

Their unconventional nature is expressed through their input type declarations, feature output declarations, and metadata — not through special registry treatment.

---

# Governance Relationships

The Tool Registry Contract governs the Tool ecosystem.

It interacts with other platform contracts as follows:

| Contract | Relationship |
|---|---|
| `docs/STRATEGY_DEFINITION_ARCHITECTURE.md` | Defines what a Tool is conceptually and how it fits into the composition model. The registry governs the lifecycle of these tools as platform entities. |
| `docs/STRATEGY_CONTRACT.md` | Defines the callable interface a strategy module must expose. Tools registered in the registry feed features into strategies that implement this interface. |
| `docs/ARCHITECTURE.md` | Defines the Strategy Tools Builder Layer as a permanent architectural direction. The registry is the foundational infrastructure for that layer. |
| `docs/EXECUTION_CONTRACT.md` | Defines how execution intents are interpreted. The registry has no direct responsibility beyond the strategy definition boundary. |
| `docs/DATA_CONTRACT.md` | Defines normalized input contracts. Tools declare their required input types, which must conform to data contract schemas. |

---

# Summary of Registry Responsibilities

```text
Tool Registration
    → Identity assignment (tool_id, version, status)
    → Metadata governance (parameters, inputs, outputs, capabilities)
    → Dependency declaration and validation
    → Lifecycle tracking (experimental → stable → deprecated → retired)

Tool Discovery
    → Category-filtered discovery
    → Status-filtered discovery
    → Capability-filtered discovery
    → Runtime-mode-filtered discovery

Tool Resolution
    → Version-pinned resolution
    → Dependency-order resolution
    → Reproducibility-preserving resolution
    → Explicit failure on missing or retired tools

Tool Governance
    → Versioning policy enforcement
    → Compatibility tracking
    → Experimental isolation
    → Deprecation management
    → Execution record tracing
```

The registry does not execute tools.

The registry does not render visualizations.

The registry does not route orders.

The registry governs the identity, metadata, lifecycle, and discovery of tools as first-class platform entities.

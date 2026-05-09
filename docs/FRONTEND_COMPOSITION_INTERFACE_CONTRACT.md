# FRONTEND_COMPOSITION_INTERFACE_CONTRACT.md

## Purpose

This document defines the architectural contract for the Frontend Composition Interface in QuantLab.

The Frontend Composition Interface is the user-facing orchestration environment through which users construct strategy definitions using reusable tools and modules.

This document establishes:

* the role and boundaries of the frontend composition interface
* the authoritative relationship between frontend and backend
* the conceptual composition workflow
* strategy definition payload philosophy
* tool discovery interaction philosophy
* validation interaction philosophy
* composition lifecycle states
* experimental vs. stable tool interaction philosophy
* runtime independence requirements
* visualization interaction philosophy
* composition graph philosophy
* frontend state philosophy
* auditability and inspection expectations
* forbidden patterns
* extensibility direction

This document is architecture-level.

It is intentionally implementation-agnostic.

Specific API routes, database schemas, frontend framework details, and state management library choices belong in their respective implementation contracts.

---

# Why This Document Exists

QuantLab's frontend composition interface is architecturally unusual.

It is not merely a form that collects parameters.

It is a strategy orchestration environment — a workspace where users select tools, compose conditions, build rules, and assemble strategy definitions that the backend will validate and execute.

This creates a clear need for formal architecture defining:

* where the frontend's authority ends
* where the backend's authority begins
* what the frontend sends to the backend and why
* how discovery, validation, and lifecycle workflows interact
* how the interface remains extensible as the tool ecosystem grows

Without this contract, the frontend risks evolving into an execution authority or hardcoding tool knowledge — both of which are architectural violations.

---

# The Frontend Composition Interface Definition

The Frontend Composition Interface is the user-facing orchestration environment for constructing strategy definitions using reusable tools and modules.

Its role is:

* **Orchestration** — guiding users through the composition of tools, conditions, rules, and signals into a coherent strategy definition
* **Composition** — providing the interaction surface for assembling strategy components
* **Parameter editing** — rendering parameter inputs based on tool metadata declarations
* **Visualization** — displaying chart overlays, signal markers, indicator series, and other artifacts produced by backend execution
* **Inspection** — allowing users to review strategy structure, execution history, validation results, and lifecycle state
* **Workflow management** — managing the progression from draft composition through validation to lifecycle promotion

## What the Frontend Composition Interface Is NOT

| Not this | Why |
|---|---|
| The execution authority | The backend validates and executes all strategy logic |
| The strategy runtime | Feature computation, rule evaluation, and signal generation belong to the backend |
| The official validation engine | Frontend validation is advisory; backend validation is authoritative |
| The backtesting engine | Historical simulation is a backend concern |
| The broker execution layer | The frontend has no awareness of order routing or broker state |
| The authoritative registry | The frontend discovers tools from the backend registry; it does not maintain its own |
| The source of truth for strategy definitions | A strategy definition is not valid until the backend confirms it |

---

# Backend Authority Philosophy

This is the most important principle in this document.

**The backend is the official authority for all strategy validation, execution, and signal generation.**

**Frontend-generated strategy definitions are proposals until backend-validated.**

## What This Means in Practice

When a user composes a strategy in the frontend:

1. The frontend assembles a declarative strategy definition payload
2. The payload is submitted to the backend
3. The backend performs authoritative validation
4. The backend resolves tool references, dependency chains, and compatibility requirements
5. The backend returns a validation result — not the frontend's interpretation of one
6. Only a backend-validated strategy definition may progress to execution

The frontend may perform advisory validation to help users catch obvious errors during composition — such as missing required parameters or obviously incompatible tool combinations. But advisory validation is a user experience aid, not an architectural gate.

An advisory validation check that passes does not mean the strategy definition is valid.

An advisory validation check that fails should warn the user but not block submission.

The backend's validation result is the only authoritative verdict.

## Why This Matters

Without this principle, the frontend would gradually accumulate execution logic.

If the frontend can determine whether a strategy definition is valid, the frontend becomes a de facto execution authority — and strategy logic starts living in the browser.

This violates the core principle that strategies must be portable, backend-validated, and reproducible.

---

# The Composition Workflow

The composition workflow is the conceptual sequence of steps through which a user constructs a strategy definition.

## Conceptual Workflow

```text
Tool Discovery
    ↓
Tool Selection (choose which tools to use)
    ↓
Parameter Configuration (set tool parameters)
    ↓
Feature Review (understand what outputs the tools will produce)
    ↓
Condition Construction (define comparisons and evaluations over features)
    ↓
Rule Composition (combine conditions with AND / OR / NOT logic)
    ↓
Signal Definition (declare what signals the rules produce)
    ↓
Filter Attachment (attach contextual filters to gate signals)
    ↓
Confirmation Attachment (attach secondary confirmations to strengthen signals)
    ↓
Risk Rule Definition (define analytical invalidation levels and constraints)
    ↓
Advisory Validation (frontend-side completeness checks)
    ↓
Backend Submission (send strategy definition payload to backend)
    ↓
Backend Validation (authoritative structural, dependency, compatibility validation)
    ↓
Save Draft (persist strategy definition with validation state)
    ↓
Research Execution (run strategy in research mode against selected data)
    ↓
Backtesting (promote to deterministic historical simulation)
    ↓
Lifecycle Promotion (forward test → paper trade → live approval workflow)
```

## Workflow Properties

**Non-linear in practice**: Users may iterate between any step, revising tools, parameters, conditions, and rules before submitting for validation.

**Inspectable at every stage**: The user should be able to inspect the current draft strategy definition — what tools are selected, what conditions are defined, what the rule structure looks like — at any point in the workflow.

**Portable across sessions**: A draft strategy definition must be persistable and resumable. The composition environment should not require the user to rebuild from memory.

**Version-aware**: Every time a validated strategy definition is saved or modified, the version must be tracked.

---

# Strategy Definition Payload Philosophy

The strategy definition payload is the structured representation of a user's composed strategy that the frontend sends to the backend.

## What the Payload Represents

The payload is a **declarative strategy definition**.

It expresses:

* which tools are included, by registry ID and version
* the parameter values for each tool
* the named features referenced in conditions
* the conditions defined
* the rule structures (including logical operators and nesting)
* the signal declarations
* the filter declarations
* the confirmation declarations
* the risk rule declarations
* the strategy's lifecycle metadata (intended runtime target, asset class, timeframe)
* the strategy's version and authorship context

## What the Payload Is NOT

| Not this | Why |
|---|---|
| Broker instructions | The payload produces analytical logic, not execution orders |
| Runtime implementations | The payload describes what to compute, not how to compute it |
| Frontend state snapshots | The payload is a durable semantic definition, not a UI memory |
| Rendering instructions | The payload has no knowledge of how outputs will be visualized |
| Execution-mode-specific | The same payload operates across all runtime modes |

## Declarative Over Procedural

The payload must be declarative.

It must describe *what* the strategy does — what tools, what conditions, what rules, what signals — without embedding *how* those are computed.

The backend resolves the *how* by resolving tool references to registered implementations and executing them.

A procedural payload — one that includes embedded calculation logic — is an architectural violation.

## Portability Requirement

A strategy definition payload must be portable.

Portable means:

* It can be serialized to a durable representation
* It can be transmitted between frontend and backend
* It can be stored and retrieved without loss of meaning
* It can be versioned
* It can be reproduced identically from the same registry state

A payload that depends on frontend-specific state, session context, or ephemeral data is not portable.

## Version References

The payload must reference specific tool versions, not "latest."

The composition interface must make version selection visible and explicit.

When a user composes a strategy, the version of each selected tool must be captured in the payload at composition time.

This ensures that a strategy definition saved today can be reproduced identically in the future, even if the registry evolves.

---

# Tool Discovery Interaction Philosophy

The composition interface must support dynamic tool discovery from the backend registry.

## The Discovery Principle

**The frontend must not hardcode knowledge of specific tools.**

The composition interface must discover:

* available tools
* their categories
* their parameter schemas
* their output feature declarations
* their visualization capabilities
* their runtime compatibility
* their lifecycle status

by querying the backend registry — not by reading from a frontend-maintained list.

## Why Dynamic Discovery Matters

When new tools are registered in the backend registry, they must become available to the composition interface without requiring frontend code changes.

If the frontend maintains a hardcoded list of tools, every new tool requires a frontend deployment.

Dynamic discovery decouples the tool ecosystem's evolution from the frontend's release cycle.

## Discovery Filtering

The composition interface should support filtered discovery:

**By category**: Present tools organized by analytical purpose (indicators, feature generators, filters, confirmations, risk-analysis tools, etc.)

**By lifecycle status**: In research-mode contexts, show all tools including experimental. In production-targeting contexts, default to showing only stable and validated tools.

**By runtime compatibility**: If a user is composing a strategy intended for live trading, show only tools that declare live-runtime compatibility.

**By asset class**: Optionally filter tools by declared asset class compatibility.

**By capability**: When a user is configuring the filter layer of a strategy, surface tools that declare filter capability.

## Discovery State

Discovery state is ephemeral.

The list of available tools is not part of a strategy definition.

The strategy definition captures the specific tool IDs and versions chosen — not the full discovery response.

The discovery response is used to populate the composition interface and then discarded.

---

# Validation Interaction Philosophy

Validation is a two-tier process: advisory frontend validation and authoritative backend validation.

## Advisory Frontend Validation

The composition interface may perform advisory validation checks to help users identify obvious issues before submission.

Advisory validation should check:

* **Completeness**: Are all required parameters of each selected tool filled in?
* **Type conformance**: Do parameter values match their declared types?
* **Obvious incompatibilities**: Is the selected tool declared incompatible with the chosen timeframe or asset class?
* **Missing components**: Does the strategy have conditions defined? Does it have at least one rule?
* **Experimental warnings**: Does the strategy include experimental tools targeted at a production runtime mode?

Advisory validation results should:

* Surface warnings and suggestions to the user in the composition interface
* Not block the user from submitting to the backend for authoritative validation
* Not be presented as official validation results

## Authoritative Backend Validation

The backend performs all authoritative validation.

Backend validation checks:

* **Structural validation**: Is the strategy definition schema well-formed?
* **Tool resolution**: Are all referenced tool IDs and versions present in the registry?
* **Dependency validation**: Can the full dependency chain be resolved without circular references?
* **Feature reference validation**: Do all conditions reference Features that the declared tools actually produce?
* **Compatibility validation**: Is the strategy's runtime target compatible with all declared tools?
* **Lifecycle validation**: Does the strategy contain only tools appropriate for its declared lifecycle stage?
* **Parameter validation**: Do all parameter values pass each tool's declared constraint rules?
* **Warmup validation**: Is sufficient data available given the warmup requirements of all tools?

The backend validation result must be:

* Returned to the frontend in a structured form
* Displayed to the user with clear diagnostic messaging
* Persisted alongside the strategy definition as part of its validation record

## Validation Is Not a Gate on Iteration

Validation is required before execution.

Validation is not required during composition iteration.

Users must be free to compose and edit strategies — including incomplete or invalid strategies — without being blocked by validation requirements.

A draft strategy may exist in an invalid state until the user chooses to submit for validation.

---

# Composition Lifecycle States

A strategy definition in the composition interface progresses through conceptual lifecycle states.

## States

**Draft**
The strategy definition is being composed.

It may be incomplete or contain unresolved issues.

Draft state persists across sessions.

A draft strategy definition may not be executed.

**Incomplete**
The strategy definition has been reviewed by advisory validation and found to be missing required components.

The user must address the flagged issues before the strategy can be submitted for backend validation.

**Submitted**
The strategy definition has been sent to the backend for authoritative validation.

The backend validation result is pending.

**Structurally Invalid**
The backend validation has failed.

The validation result carries diagnostic messages.

The user must address the structural issues and resubmit.

**Validated**
The backend validation has passed.

The strategy definition is confirmed structurally sound and ready for research-mode execution.

**Research-Executed**
The strategy definition has been run in research mode at least once.

Research execution results are available for inspection.

**Backtested**
The strategy definition has been promoted to deterministic historical simulation and at least one backtest run has been completed.

Backtest results and metadata are available.

**Promoted**
The strategy definition has progressed beyond backtesting into forward testing, paper trading, or approval for live trading.

Lifecycle progression is governed by the backend.

**Deprecated**
The strategy definition has been superseded by a newer version or retired from active use.

Deprecated strategy definitions remain inspectable but must not be promoted further.

## Lifecycle State Governance

**Lifecycle state belongs to the backend.**

The frontend reflects lifecycle state — it does not invent it.

The frontend may render lifecycle state in the composition interface (e.g., showing a badge indicating "Validated" or "Draft"), but the source of truth is always the backend's record.

Lifecycle promotion actions — moving from research to backtest, or from backtest to forward test — are backend operations. The frontend initiates them through explicit user actions, but the backend authorizes and records them.

---

# Experimental vs. Stable Tool Interaction

The composition interface must clearly communicate tool lifecycle maturity to the user.

## Stable Tools

Stable tools:

* are prominently featured in the default tool discovery palette
* may be used freely in strategy definitions targeting any runtime mode
* carry no special warnings in the composition interface

## Validated Tools

Validated tools:

* are available for use in research and backtesting contexts
* carry a minor informational note that they are validated but not yet marked fully stable
* must not carry warnings that discourage production-oriented use

## Experimental Tools

Experimental tools:

* are available in the tool discovery palette but clearly marked as experimental
* are accessible in research-mode composition contexts without restriction
* carry an explicit warning when used in strategy definitions targeting backtesting or production modes
* must be visually distinguished from stable and validated tools throughout the composition interface

The composition interface must not prevent users from using experimental tools.

Experimental research is a first-class platform capability.

The interface must inform — not restrict.

## Deprecated Tools

Deprecated tools:

* must remain inspectable in existing strategy definitions that reference them
* must not appear in the default discovery palette for new composition
* must carry an explicit deprecation notice when viewed
* must surface migration guidance toward the replacement tool

## Discovery Defaults

When a user opens the tool discovery palette without filtering:

* Research-mode context: show stable, validated, and experimental tools; clearly distinguish each
* Backtesting context: show stable and validated tools by default; experimental tools available on explicit request with a warning
* Production-target context: show stable tools by default; validated tools on explicit request; experimental tools blocked with a clear explanation

---

# Runtime Independence Philosophy

The composition interface must remain runtime-independent.

## The Requirement

A strategy definition composed in the frontend must operate consistently across all runtime modes:

* research
* backtesting
* forward testing
* paper trading
* future live trading

without requiring frontend-specific modifications.

## What This Means

The composition interface must not:

* Include runtime-mode-specific fields in the strategy definition payload
* Embed mode-specific logic in the condition or rule structure
* Require the user to compose different strategy definitions for different runtime modes
* Store mode-specific rendering assumptions in the strategy definition

## What the Frontend Does Declare

The strategy definition payload includes a declared **target runtime context** — a declaration of the intended deployment mode.

This declaration is used for:

* filtering appropriate tools during discovery
* validation compatibility checks
* lifecycle promotion eligibility checks

It is not embedded in the strategy logic itself.

The strategy's analytical logic — tools, features, conditions, rules, signals — is identical regardless of the declared target runtime.

## Mode-Specific Behavior Is Backend-Handled

Any differences in behavior across runtime modes (data delivery timing, execution simulation mechanics, portfolio state) are handled entirely by the backend runtime layer.

The strategy definition payload is indifferent to these differences.

---

# Visualization Interaction Philosophy

The composition interface is both a composition environment and a visualization terminal.

Visualization and composition are distinct responsibilities that coexist in the same interface.

## Visualization Responsibilities of the Frontend

* Render chart overlays (price chart candles, indicator lines, zone overlays)
* Render signal markers (entry/exit annotations on the chart)
* Render forecast projections
* Render oscillator panes for oscillator-type tool outputs
* Render regime classification backgrounds
* Render research inspection panels (signal details, indicator values, run metadata)

## Generic Rendering Principle

**The frontend must render visualization artifacts generically, based on artifact type — not based on tool identity.**

This is an architectural constraint derived from the Tool Registry Contract.

The frontend receives visualization artifacts from backend execution. Each artifact declares its type (line overlay, oscillator series, marker, regime overlay, zone, etc.).

The frontend renders the artifact according to its declared type.

The frontend must not check which tool produced the artifact and apply tool-specific rendering logic.

### Why This Matters

If the frontend renders `MA20` with a blue line because it knows the tool is a moving average tool, the frontend has embedded tool-specific knowledge.

When a new tool is added to the registry, the frontend requires a code change.

If instead the frontend renders any artifact of type `line_overlay` on the price chart, adding a new tool that produces line overlays requires no frontend code change.

Generic rendering preserves the extensibility of the tool ecosystem.

## Visualization and Composition Remain Distinct

Visualization artifacts are produced by backend execution of a strategy definition.

The composition interface displays them as research context.

Visualization does not affect the strategy definition payload.

A user may inspect the chart, see the indicator overlays, and decide to change a parameter — but that change happens through the composition workflow, not through the visualization.

The chart is a read-only research context.

The composition workspace is the editable context.

## Visualization Capability Awareness

The composition interface may use tool metadata to inform users about what a tool will produce visually — before running it.

For example, when a user selects an RSI tool, the interface may indicate "this tool produces an oscillator series" based on the registry's visualization capability declaration.

This is informational — it helps the user understand what they are adding.

It is not a rendering decision — the actual rendering happens after backend execution when real artifact data is received.

---

# Composition Graph Philosophy

A strategy definition is not a flat list of components.

It is a directed graph of dependencies: tools producing features, features referenced by conditions, conditions composed into rules, rules producing signals, signals filtered and confirmed, signals feeding risk rules and producing execution intents.

## Graph Properties the Architecture Must Support

**Nested conditions**: Conditions may be grouped into nested sub-groups with mixed logical operators.

**Grouped rules**: Rules may be organized into named groups (entry group, exit group, filter group, confirmation group) for organizational clarity.

**Dependency chains**: A tool's output features may depend on another tool's output features, creating explicit computation chains.

**Multi-timeframe relationships**: A strategy may reference features computed on different timeframes. The composition interface must allow the user to declare which timeframe each tool operates on.

**Cross-rule references**: A condition or rule may reference the output of a previously evaluated rule (e.g., a filter that gates based on whether a primary signal rule has fired).

## Graph Representation Philosophy

The composition interface should be designed to accommodate graph-structured strategy definitions.

This does not require implementing a visual graph editor immediately.

It requires that the underlying strategy definition data model is graph-compatible — capable of expressing nested, chained, and cross-referenced structures — so that future visual graph interfaces can be added without rewriting the data model.

A flat list representation of conditions and rules that assumes linear evaluation order will not accommodate multi-timeframe strategies, nested rule groups, or dependency chains.

The composition interface data model must be graph-aware from the start.

---

# Frontend State Philosophy

The composition interface manages multiple categories of state that must be clearly distinguished.

## State Categories

**Transient UI State**
Ephemeral interaction state: which panel is open, cursor position, hover states, scroll position.

This state is local to the session.

It has no relationship to the strategy definition.

It must never be included in the strategy definition payload.

**Draft Composition State**
The in-progress strategy definition: tools selected, parameters entered, conditions defined, rules composed.

This state must be persistable and resumable across sessions.

It is not authoritative — it is the user's working copy of the strategy definition.

Draft composition state becomes a strategy definition payload when the user submits to the backend.

**Validated Strategy State**
The strategy definition as confirmed by the backend.

This state is backend-authoritative.

The frontend reflects it — it does not generate it.

Validated strategy state includes the backend's validation record, version identifier, and lifecycle stage.

**Execution Result State**
The outputs produced by backend execution of a validated strategy definition: signals, indicator series, forecast projections, performance metrics.

This state is ephemeral in the frontend — it is produced by backend execution and displayed to the user.

It must not be embedded in the strategy definition payload.

**Registry Discovery State**
The list of available tools, categories, and metadata returned by the backend registry.

This state is ephemeral — it is fetched on demand and not persisted.

It must not be embedded in the strategy definition payload.

## The Core Principle

Frontend state is not authoritative execution truth.

Only backend-validated strategy definitions and backend-produced execution results are authoritative.

The frontend reflects, displays, and communicates — it does not certify or execute.

---

# Auditability and Inspection Philosophy

Strategy composition must remain auditable and inspectable.

## Strategy Inspection Expectations

A user must be able to inspect any saved strategy definition and understand:

* Which tools are included and at which versions
* What parameters are configured
* What conditions are defined
* How rules are structured
* What signals the strategy produces
* What filters and confirmations are attached
* What the current lifecycle state is
* What validation results have been recorded
* What execution runs have been performed and when

This information must be accessible not just during active composition but for any historical strategy definition version.

## Version-Aware Inspection

Every saved strategy definition must carry a version identifier.

When a strategy definition is modified and saved again, a new version must be created.

Old versions must remain inspectable.

A user must be able to compare two versions of the same strategy definition to understand what changed.

## Execution Record Traceability

Every backend execution of a strategy definition must be traceable:

* Which strategy definition version was used
* Which tool versions were resolved
* Which data range was used
* When the execution occurred
* What outputs were produced

The composition interface must provide access to this execution history for inspection purposes.

## Auditability Is Backend-Governed

The backend is responsible for maintaining the authoritative execution record.

The composition interface surfaces this information — it does not generate or own it.

---

# Forbidden Frontend Patterns

The following patterns are architectural violations in the composition interface.

Implementations that exhibit these patterns must be identified and refactored.

**Frontend executing official strategy logic**
The frontend must not compute Features, evaluate Conditions, evaluate Rules, or generate Signals.

These are backend responsibilities.

**Frontend generating authoritative signals**
Any signal produced only in the frontend — without passing through backend validation and execution — is not an authoritative signal and must not be treated as one.

**Frontend hardcoding tool-specific rendering logic**
The frontend must not check which tool produced a visualization artifact and apply tool-specific rendering.

Rendering must be generic, based on artifact type.

**Frontend maintaining a hardcoded tool registry**
The frontend must not maintain its own list of available tools.

Tool discovery must be dynamic, fetched from the backend registry.

**Frontend storing runtime assumptions in the strategy definition payload**
The strategy definition payload must be runtime-independent.

Mode-specific assumptions (batch vs. streaming, simulation vs. live) must not be embedded in the analytical logic section of the payload.

**Frontend bypassing backend validation**
A strategy definition must not be promoted to execution without passing backend validation.

Frontend advisory validation is not a substitute for authoritative backend validation.

**Frontend becoming the lifecycle authority**
Lifecycle state — whether a strategy is draft, validated, backtested, promoted — belongs to the backend.

The frontend must not invent or override lifecycle state.

**Frontend embedding broker-specific behavior**
The composition interface has no awareness of broker capabilities, order types, or execution constraints.

Broker-specific concerns belong exclusively to the execution layer.

**Frontend coupling visualization to strategy identity**
The composition interface must not render charts or overlays differently based on which strategy is being displayed.

Visualization must be driven by artifact type metadata, not by strategy or tool identity.

**Frontend treating draft composition state as authoritative**
A draft strategy definition in the composition workspace is not a valid, executable strategy.

It becomes authoritative only after backend validation.

---

# Extensibility Philosophy

The composition interface architecture must remain open to continuous expansion.

## Expanding Tool Categories

When new tool categories are added to the registry, the composition interface must surface them without requiring architectural changes.

The composition interface renders tool categories dynamically from registry discovery responses.

Adding a "planetary cycle tools" category to the registry must cause it to appear in the composition interface's tool palette automatically.

## Expanding Composition Workflows

Future composition workflows may include:

* AI-assisted strategy composition suggestions
* Template-based strategy bootstrapping
* Strategy cloning and variation workflows
* Multi-strategy comparison workflows
* Collaborative composition workflows

These must be addable as composition workflow extensions without requiring rewrites of the core strategy definition data model.

## Expanding Visualization Capabilities

New visualization artifact types must appear in the frontend without requiring hardcoded rendering additions for each new tool.

The generic rendering system must accommodate new artifact types by adding a renderer for the artifact type — not by adding tool-specific rendering branches.

## Expanding Runtime Environments

When new runtime modes are added to the platform, the composition interface must accommodate:

* new lifecycle states associated with the new runtime mode
* new discovery filters for tools compatible with the new mode
* new validation checks surfaced from backend responses

These additions must not require core rewrites of the composition workflow.

## AI-Assisted Composition

Future versions of the composition interface may include AI-assisted composition features:

* Suggesting tools based on a user's natural language strategy description
* Flagging potential rule conflicts or redundant conditions
* Recommending confirmations based on selected entry rules

AI-assisted composition features must remain advisory.

They must not generate authoritative strategy definitions.

All AI suggestions must pass through the same composition workflow and backend validation as user-authored definitions.

---

# Governance Relationships

The Frontend Composition Interface Contract governs the composition interaction layer.

It relates to other platform contracts as follows:

| Contract | Relationship |
|---|---|
| `docs/STRATEGY_DEFINITION_ARCHITECTURE.md` | Defines the vocabulary (Tool, Feature, Condition, Rule, Signal, etc.) that the composition interface works with. This document defines how the interface interacts with those concepts. |
| `docs/TOOL_REGISTRY_CONTRACT.md` | Defines the Tool Registry as a backend authority. This document defines how the frontend queries and interacts with that registry. |
| `docs/STRATEGY_CONTRACT.md` | Defines the strategy module callable interface. This document defines the interaction layer upstream of that interface. |
| `docs/ARCHITECTURE.md` | Defines the Frontend Layer's dual role. This document elaborates on the composition role specifically. |
| `docs/EXECUTION_CONTRACT.md` | Defines how Execution Intents are handled downstream. This document defines the composition boundary upstream of Execution Intents. |

---

# Summary of Frontend/Backend Authority Division

```text
FRONTEND AUTHORITY
    ↓
Tool Discovery (from backend registry)
    ↓
Parameter Configuration (rendered from tool metadata)
    ↓
Condition / Rule / Signal Composition (user interaction)
    ↓
Advisory Validation (informational only)
    ↓
Payload Assembly (declarative strategy definition)
    ↓
═══════════════════════════════════════
FRONTEND → BACKEND BOUNDARY
(strategy definition payload submitted)
═══════════════════════════════════════
    ↓
BACKEND AUTHORITY
    ↓
Authoritative Validation
    ↓
Tool Resolution (from registry)
    ↓
Dependency Chain Resolution
    ↓
Feature Computation
    ↓
Rule Evaluation
    ↓
Signal Generation
    ↓
Execution Intent Production
    ↓
Lifecycle State Management
    ↓
Execution Record Persistence
    ↓
Artifact Return to Frontend (for visualization)
```

The frontier between frontend and backend authority is the submission of the strategy definition payload.

Everything above the frontier is frontend orchestration.

Everything below the frontier is backend execution.

The frontend renders the results returned by the backend.

The frontend does not replicate the backend's work.

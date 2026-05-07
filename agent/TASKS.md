# TASKS.md

## Purpose

This document manages implementation coordination, execution sequencing, repository maturity progression, and active development priorities for QuantLab.

This is not a simple TODO list.

The purpose of this document is to:

* coordinate implementation phases
* preserve architectural sequencing
* prevent premature implementation
* manage repository maturity evolution
* identify active priorities
* track dependencies and blockers
* maintain implementation continuity across AI sessions

This document should remain:
* operational
* structured
* high-signal
* modular
* current
* flexible

Avoid converting this file into:
* long-form project documentation
* architecture explanations
* implementation logs
* research notes
* bloated historical status records

TASKS.md is a living operational document.

It should be updated when priorities, blockers, active work, or repository maturity changes.

However, it must not become a full historical archive. Completed or obsolete details should be summarized, compressed, or moved out when they no longer help current execution.

---

# Current Repository Phase

## Active Phase

PHASE 1 — FOUNDATION & GOVERNANCE

Current repository focus:
* architecture governance
* workflow discipline
* AI orchestration structure
* repository organization
* system blueprinting
* implementation sequencing

Major implementation has not started yet.

---

# Current Primary Objective

Establish a scalable and disciplined AI-assisted engineering foundation for QuantLab before major system implementation begins.

Priority focus:
* modularity
* architecture definition
* repository governance
* workflow structure
* system boundaries
* strategy portability
* execution isolation
* data abstraction

---

# Execution Domains

QuantLab currently operates through two separate execution domains:

ORCHESTRATION DOMAIN
→ architecture
→ governance
→ planning
→ blueprinting
→ workflow design
→ system decomposition
→ AI coordination

IMPLEMENTATION DOMAIN
→ coding
→ module implementation
→ frontend/backend systems
→ data pipelines
→ charting
→ strategy engine development
→ infrastructure execution

The orchestration domain is currently handled primarily by:

human operator
+ ChatGPT orchestration layer

The implementation domain will later be handled primarily by:

Claude
Codex
other implementation agents

TASKS.md must preserve this separation.

---

# Orchestration Layer Tasks

These tasks belong primarily to:

human operator
+ orchestration AI

These are architecture and governance activities — not implementation execution tasks.

---

## Orchestration Priority 1 — Governance Foundation

### Status

IN PROGRESS

### Objectives

Establish core governance and orchestration documents.

### Current Tasks

* [x] ARCHITECTURE_GUARDRAILS.md
* [x] WORKFLOW_GOVERNANCE.md
* [x] WORKFLOW_AGENT.md
* [x] PROMPT_RULES.md
* [x] HANDOFF.md
* [x] TASKS.md
* [ ] SYSTEM_OVERVIEW.md
* [ ] ARCHITECTURE.md
* [ ] REPOSITORY_STRUCTURE.md

### Notes

Governance quality currently takes priority over implementation speed.

---

## Orchestration Priority 2 — Repository Structure Blueprint

### Status

PENDING

### Objectives

Define scalable repository structure for:

* backend
* frontend
* datasets
* strategy modules
* research modules
* execution systems
* infrastructure
* AI orchestration layers

### Key Requirements

* modular boundaries
* strategy portability
* execution isolation
* scalable research workflows
* AI-friendly organization
* low context fragmentation

---

## Orchestration Priority 3 — System Architecture Blueprint

### Status

PENDING

### Objectives

Define high-level QuantLab system architecture.

### Expected Scope

* backend domain structure
* frontend architecture
* strategy engine boundaries
* data pipeline flow
* execution layer separation
* storage architecture
* adapter architecture
* orchestration flow

### Deliverables

* SYSTEM_OVERVIEW.md
* ARCHITECTURE.md
* module relationship mapping

---

# Implementation Layer Tasks

These tasks belong primarily to implementation agents.

Implementation work should begin only after sufficient architectural clarity exists.

However, controlled validation-oriented detours are allowed earlier if they support foundational verification.

---

## Implementation Priority 1 — Data Architecture Layer

### Status

PENDING

### Objectives

Define normalized market and research data architecture.

### Expected Scope

* ingestion flow
* normalization contracts
* schema structure
* OHLCV modeling
* alternative dataset support
* feature engineering pipeline
* DuckDB/Parquet strategy
* metadata storage strategy

### Important Constraints

Strategies must never directly consume raw provider schemas.

---

## Implementation Priority 2 — Minimal Validation Tooling

### Status

OPTIONAL / VALIDATION-DRIVEN

### Objectives

Allow early validation of foundational assumptions before major platform development.

### Possible Scope

* minimal OHLCV chart viewer
* temporary data inspection UI
* lightweight API validation endpoint
* normalization verification tooling
* dataset inspection utilities

### Notes

This work is allowed early when it helps validate:

* data correctness
* normalization quality
* ingestion flow
* frontend/backend contracts
* candlestick rendering assumptions

This does NOT imply that the full frontend research terminal is prioritized ahead of the core architecture.

---

## Implementation Priority 3 — Strategy Engine Foundation

### Status

PENDING

### Objectives

Define portable strategy architecture.

### Expected Scope

* strategy interfaces
* signal contracts
* feature contracts
* strategy lifecycle
* runtime isolation
* execution independence
* research workflow integration

### Important Constraints

Strategies must remain portable across:

* research
* backtesting
* forward testing
* paper trading
* future live trading

---

## Implementation Priority 4 — Research Environment Layer

### Status

PENDING

### Objectives

Design research-first workflows and experimentation infrastructure.

### Expected Scope

* feature experimentation
* cycle analysis workflows
* planetary/astronomical research support
* hypothesis testing workflows
* strategy comparison workflows
* research artifact management
* manual intervention support

### Important Constraints

Experimental research logic must remain isolated from production-grade execution systems.

---

## Implementation Priority 5 — Frontend Research Terminal

### Status

DEFERRED / INCREMENTAL

### Objectives

Design advanced research visualization environment.

### Expected Scope

* charting platform
* multi-pane synchronization
* drawing tools
* overlays
* signal inspection
* waveform-style rendering concepts
* annotation systems
* high-performance rendering
* research workflow UX

### Notes

Frontend capabilities may evolve incrementally.

Minimal validation-oriented charting work may occur much earlier.

### Important Constraints

Frontend must remain free from core business logic.

---

## Implementation Priority 6 — Backtesting Framework

### Status
DEFERRED


### Objectives

Develop deterministic and reproducible backtesting systems.

### Important Requirements

* deterministic results
* reproducibility
* parameter traceability
* dataset versioning
* execution assumptions
* slippage modeling
* auditability

---

## Implementation Priority 7 — Forward Testing & Paper Trading

### Status
DEFERRED

### Objectives

Establish runtime evaluation environments using real-time or near-real-time market data.

### Important Constraints

Forward testing and paper trading must use the same core strategy logic as backtesting.

---

## Implementation Priority 8 — Execution & Broker Layer

### Status
DEFERRED

### Objectives

Design isolated execution infrastructure.

### Expected Scope

* execution engine
* broker adapters
* portfolio constraints
* risk layer
* routing systems
* execution lifecycle

### Important Constraints

Execution systems must remain isolated from strategies.

---

## Implementation Priority 9 — Live Trading Infrastructure

### Status
LONG-TERM DEFERRED

### Objectives

Support future controlled live trading capability.

### Important Constraints

Live trading is NOT current priority.

No uncontrolled execution behavior should exist.

---

# Current Architectural Constraints

The following principles currently take highest priority:

* strategy portability
* modular boundaries
* data abstraction
* execution isolation
* AI orchestration discipline
* low token waste
* deterministic workflows
* incremental evolution

Avoid premature optimization and speculative infrastructure.

---

# Controlled Detour Rules

QuantLab development must remain flexible.

The task sequence is a recommended execution path, not a rigid waterfall plan.

Controlled detours are allowed when they support current learning, validation, or architectural confidence.

Examples of valid detours:
early charting canvas to validate OHLCV normalization
temporary data viewer to inspect ingestion quality
minimal API endpoint to test frontend/backend integration
prototype research screen to validate workflow assumptions
small visualization tool to expose data contract issues

A detour is valid only if it has a clear purpose and does not violate architecture guardrails.

Before starting a detour, agents should record:
why the detour is needed
what phase it supports
which modules are affected
what must remain out of scope
whether the work is prototype, temporary, or production-intended

Detours must not become uncontrolled scope expansion.

A minimal frontend chart may be introduced early to validate OHLCV data and normalization quality, even if the full research terminal and drawing tools remain deferred.

Such work should be treated as:
validation-supporting implementation

not as full frontend platform completion.

---

# Current Known Risks

## Governance Drift

As repository complexity increases, governance structures may require refactoring.

Agents should monitor:

* document scope quality
* operational clarity
* duplicated governance responsibilities
* oversized context documents
* stale workflows
* architecture fragmentation

---

## Premature Complexity

There is significant risk of:

* overengineering
* unnecessary abstractions
* speculative infrastructure
* infrastructure-first development

Current priority is:
small deterministic foundations

---

## AI Context Explosion

Large uncontrolled prompts and oversized documentation can degrade:
* reasoning quality
* implementation quality
* token efficiency
* operational consistency

Repository structure should remain modular and retrievable.

---

# Current Recommended Workflow

Preferred implementation flow:

architecture definition
→ repository structure
→ data contracts
→ strategy contracts
→ core engines
→ visualization systems
→ execution systems
→ runtime environments
→ future live infrastructure

Avoid skipping architectural sequencing.

However, tactical validation work may occur earlier when it helps prove or inspect foundational assumptions.

Example:
minimal OHLCV charting view

may be built early to validate:
* data ingestion
* normalization correctness
* timeframe handling
* candlestick rendering
* frontend/backend contract clarity

This does not mean the full frontend research terminal is promoted ahead of the data and strategy layers.

---

# Deferred Systems

The following systems are intentionally deferred until earlier architectural layers stabilize:
* live trading
* broker-specific optimization
* multi-user infrastructure
* distributed execution
* microservices architecture
* cloud orchestration
* advanced deployment automation
* high-frequency execution systems

QuantLab should evolve incrementally.

---

# Repository Maturity Direction

QuantLab is expected to evolve through increasing architectural maturity.

Governance structures, workflows, repository organization, and documentation boundaries are expected to evolve together with repository complexity.

Agents should recommend governance evolution and operational refactoring when repository maturity significantly increases.

---

# TASKS.md Maintenance Rules

TASKS.md must be actively maintained, but not endlessly expanded.

Agents should update TASKS.md when:
* new active work starts
* priority changes
* controlled detours are introduced
* blockers appear
* major tasks are completed
* maturity phase changes
* scope is intentionally deferred

Agents should avoid adding excessive historical details.

Completed work should be summarized under completed milestones or compressed into a short state note.

Detailed implementation history should live in:
* HANDOFF.md for recent session continuity
* commit messages for code-level history
* module documentation for durable design decisions

TASKS.md should answer:
* what should happen next?
* what is active now?
* what is blocked?
* what is intentionally deferred?
* what maturity phase are we in?

TASKS.md should not attempt to answer:
* everything that has ever happened
* all implementation details
* all design explanations
* all historical decisions

---

# Current Immediate Next Recommended Actions

Recommended next sequence:
1. Finalize governance foundation
2. Define repository structure blueprint
3. Create SYSTEM_OVERVIEW.md
4. Create ARCHITECTURE.md
5. Define backend domain structure
6. Define data layer contracts
7. Define strategy engine contracts

Avoid major implementation before architectural boundaries are stabilized.

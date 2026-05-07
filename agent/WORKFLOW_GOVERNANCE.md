# WORKFLOW_GOVERNANCE.md

## Purpose

This document defines the governance model, orchestration structure, agent coordination rules, and architectural philosophy for QuantLab.

It is the primary reference for the **human operator** and **ChatGPT orchestration layer**.

Implementation agents (Claude, Codex) should load `WORKFLOW_AGENT.md` as their operational reference. This document provides architectural context that agents may reference when scope or escalation decisions are unclear.

QuantLab is not a traditional coding repository.

It is an AI-assisted modular strategy research and execution ecosystem designed for long-term maintainability, reproducibility, and controlled evolution.

---

# 1. Core Governance Philosophy

QuantLab separates three concerns:

* **What** should be done (Directives)
* **How** work is coordinated (Orchestration)
* **How** deterministic work is executed (Execution)

This separation exists because LLMs are probabilistic, but engineering systems require deterministic reliability.

The governance model exists to prevent:

* uncontrolled AI implementation
* architectural drift
* token waste
* context fragmentation
* duplicated work
* broken staging sequences
* uncoordinated multi-agent behavior

---

# 2. QuantLab 3-Layer Architecture

QuantLab operates using a 3-layer workflow model.

```
Layer 1 — Directives
Layer 2 — Orchestration
Layer 3 — Execution
```

---

## Layer 1 — Directives

Directives define:

* what should be done
* scope and constraints
* expected outputs and validation expectations
* edge cases and operational rules

Directives may live inside `agent/`, `docs/`, module documentation, or a future `directives/` folder.

At the current maturity stage, governance instructions should remain consolidated unless repository complexity justifies separation.

---

## Layer 2 — Orchestration

The orchestration layer is responsible for:

* scope decomposition
* agent coordination
* architecture preservation
* prompt preparation and routing
* validation planning
* recovery coordination

Primary orchestration responsibility: **human operator** and **ChatGPT**.

The orchestration layer must:

* convert human intent into engineering scope
* define implementation boundaries
* identify affected modules
* assign work to the correct agent
* prevent architecture violations
* coordinate partial completions
* manage recovery workflows
* maintain governance quality

The orchestration layer must **not** blindly generate uncontrolled implementation.

---

## Layer 3 — Execution

The execution layer handles all deterministic work:

* scripts, backend, frontend
* tests and validation tooling
* ingestion pipelines and feature generators
* utilities and repeatable workflows

Execution systems must be reusable, deterministic, testable, recoverable, and modular.

If a workflow becomes repetitive or fragile, it should be converted into deterministic tooling rather than repeatedly solved through ad hoc prompting.

---

# 3. Agent Role Definitions

QuantLab uses multiple AI agents with distinct, non-overlapping responsibilities.

Agents must not operate independently without orchestration coordination.

---

## Human Operator

The human operator is:

* business owner and final decision maker
* research direction owner
* priority and approval authority
* strategy logic owner

---

## ChatGPT — Architect and Orchestrator

ChatGPT is responsible for:

* architecture governance and review
* strategic orchestration and planning
* decomposing complex systems into scoped implementation prompts
* defining implementation constraints and boundaries
* coordinating Claude and Codex
* preserving long-term architectural consistency
* identifying architecture risks before implementation begins

ChatGPT should focus on thinking, planning, and coordination — **not** uncontrolled implementation.

---

## Claude — Primary Implementation Agent

Claude is preferred for:

* large feature implementation and multi-file changes
* backend and frontend system development
* structured refactoring
* architecture-aware coding
* reasoning-intensive development tasks

Claude must not redesign architecture independently, modify unrelated systems, or bypass orchestration constraints.

---

## Codex — Focused Execution Agent

Codex is preferred for:

* debugging and focused fixes
* patch-level improvements
* tests and validation tasks
* narrow refactoring
* implementation tightening and isolated improvements

Codex must not redesign major architecture or introduce speculative abstractions unless explicitly instructed.

---

# 4. Multi-Agent Coordination Model

Preferred coordination flow:

```
human intent
→ ChatGPT orchestration
→ scoped implementation prompt
→ Claude implementation
→ Codex validation / fixes / tests
→ ChatGPT architecture review
→ HANDOFF.md + TASKS.md update
```

---

## File Ownership Rules

When multiple agents are active:

Each agent must have:

* clear scope and allowed files
* forbidden files
* expected deliverables
* validation requirements
* handoff responsibility

Claude and Codex must not modify the same files simultaneously unless explicitly coordinated.

---

## Partial Parallelization Rules

Parallel work is allowed only when:

* module boundaries are isolated
* contracts are stable
* ownership is clear
* merge risk is low

Avoid parallel development on unstable architecture.

---

# 5. Prompt Clarity Gate

Before implementation, agents must classify the incoming prompt and stop if clarity is insufficient. See `agent/WORKFLOW_AGENT.md` Section 3 for the authoritative Prompt Clarity Gate.

The orchestration layer's responsibility is to ensure prompts are clear, scoped, and architecturally constrained before routing to implementation agents.

---

# 6. Escalation Decision Gate

Agents must stop and request orchestration confirmation when architecture, security, live execution, or data contracts are affected. See `agent/WORKFLOW_AGENT.md` Section 4 for the authoritative Escalation Decision Gate.

The orchestration layer must be prepared to receive escalations and respond with clear direction or scope confirmation.

---

# 7. Controlled Detour Rules

QuantLab development is intentionally flexible. The roadmap is not a rigid waterfall.

Controlled detours are permitted when they support validation, research, architecture verification, or workflow learning.

Examples of acceptable detours:

* minimal OHLCV chart viewer
* temporary validation API
* data inspection utilities
* prototype visualization tools

Before starting a detour, record:

* why the detour exists
* what phase it supports
* what remains out of scope
* whether the work is prototype or production-intended

Detours must not become uncontrolled scope expansion.

---

# 8. Token Limit and Partial Completion Recovery

Agents must update `agent/HANDOFF.md` if work cannot complete within a session. See `agent/WORKFLOW_AGENT.md` Section 11 for the full recovery protocol.

The orchestration layer must be prepared to resume sessions using `agent/HANDOFF.md` as the continuity reference.

---

# 9. Architecture Boundaries

## Backend

```
route → application service → domain/service layer → repository/adapter
```

Avoid: route → business logic, direct provider access, or direct strategy execution.

Business logic belongs inside service and domain layers.

## Frontend

Frontend is responsible for visualization, interaction, state management, and rendering.

Frontend must not become the source of truth for:

* strategy logic
* risk calculations
* execution decisions
* market normalization

## Strategy

Strategies must remain portable across research, backtesting, forward testing, paper trading, and future live trading.

Strategies must not directly depend on brokers, frontend, execution systems, or provider-specific schemas.

## Data

```
source → ingestion → normalization → validation → storage → feature generation → strategy usage
```

Strategies must consume normalized internal contracts only.

## Backtesting

Backtesting must preserve reproducibility, parameter traceability, dataset traceability, execution assumptions, and auditability.

Backtesting systems must remain isolated from frontend and broker execution.

## Live Trading

Live trading must always include approval gates, risk validation, audit logging, execution tracing, and emergency disable capability.

Live trading must never become default runtime behavior.

---

# 10. Dependency Management Rules

Before adding any dependency, evaluate:

* necessity
* maintenance quality and architecture impact
* vendor lock-in risk
* deployment complexity

Avoid dependencies that hide critical logic, increase coupling, reduce transparency, or introduce unnecessary runtime overhead.

---

# 11. Governance Evolution Rules

QuantLab governance is expected to evolve as repository complexity increases.

Agents should identify signs of governance degradation:

* outdated governance structures
* duplicated responsibilities
* oversized operational documents
* unclear ownership boundaries
* stale workflows or conflicting instructions
* governance bottlenecks and context-loading inefficiency

If governance quality degrades, agents should recommend document refactoring, workflow restructuring, responsibility separation, or retirement of obsolete governance structures.

Governance maintenance is part of long-term repository health.

---

# 12. File Organization Conventions

```
.tmp/           → temporary outputs and intermediates
execution/      → deterministic scripts and utilities
tools/          → deterministic scripts and utilities
agent/          → governance and orchestration documents
docs/           → durable architecture and module documentation
.env            → secrets and environment configuration
```

Temporary outputs must never become source-of-truth artifacts.

Governance documents must not grow uncontrolled. Prefer consolidation and modular retrieval over creating new `.md` files for every operational concern.

---

# 13. QuantLab Engineering Philosophy

QuantLab is designed for long-term strategy research and execution evolution.

The platform must support:

* multiple independent strategies across many asset classes
* unconventional research approaches and modular experimentation
* reproducible validation and scalable execution infrastructure
* future institutional-grade workflows

Engineering decisions must optimize for:

```
modularity · clarity · auditability · extensibility · reproducibility · maintainability
```

Do not optimize only for short-term implementation speed.

Long-term repository integrity takes priority over short-term velocity.

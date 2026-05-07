# ARCHITECTURE_REVIEW.md

## Purpose

This directive defines the workflow, evaluation criteria, escalation rules, and governance standards for conducting architecture reviews inside QuantLab.

Architecture reviews exist to preserve:

* modularity
* system boundaries
* strategy portability
* execution isolation
* reproducibility
* long-term maintainability
* institutional-grade engineering discipline

Architecture reviews are mandatory for preventing:

* architecture drift
* uncontrolled coupling
* monolithic systems
* hidden dependencies
* unstable abstractions
* short-term implementation shortcuts

---

# Core Philosophy

QuantLab is NOT a simple trading bot repository.

QuantLab is a modular strategy research and execution ecosystem.

Architecture quality takes priority over:

* short-term implementation speed
* convenience abstractions
* uncontrolled feature expansion
* speculative optimization

Every architecture review must optimize for:

```text
modularity
reproducibility
portability
auditability
maintainability
extensibility
```

---

# Objective

When conducting architecture reviews, the implementation agent must:

1. preserve architecture boundaries
2. identify coupling risks
3. validate contract integrity
4. prevent architecture drift
5. maintain deterministic workflows
6. preserve portability
7. identify long-term maintenance risks

---

# Required Review Workflow

Minimum required workflow:

```text
scope identification
→ boundary analysis
→ dependency analysis
→ contract validation
→ architecture risk review
→ implementation review
→ escalation review
→ approval or remediation recommendation
```

---

# Review Scope

Architecture reviews may apply to:

* backend systems
* frontend systems
* strategy modules
* feature pipelines
* execution systems
* runtime systems
* storage systems
* research systems
* data pipelines
* infrastructure modules

All systems must preserve architecture discipline.

---

# Required Architecture Boundaries

The following boundaries must remain protected:

```text
frontend
backend API
application services
strategy engine
data abstraction layer
storage layer
execution layer
broker adapters
provider adapters
research systems
runtime systems
```

No layer should bypass another layer without explicit approval.

---

# Strategy Boundary Rules

Strategies must remain:

* execution-independent
* broker-independent
* provider-independent
* frontend-independent

Strategies must NOT:

* place orders
* call brokers
* read databases directly
* access frontend state
* depend on runtime mode

VALID:

```text
normalized data
→ strategy
→ signal
```

INVALID:

```text
strategy
→ broker
```

---

# Data Layer Review Rules

Architecture reviews must validate:

* normalization pipelines
* schema consistency
* provider isolation
* timestamp integrity
* dataset traceability
* reproducibility

Strategies must consume ONLY normalized internal schemas.

---

# Execution Isolation Rules

Execution systems must remain isolated from:

* strategies
* research systems
* frontend logic

Execution responsibilities include:

* routing
* position sizing
* portfolio management
* broker integration
* compliance enforcement
* order lifecycle handling

Strategies must NOT execute trades directly.

---

# Frontend Review Rules

Frontend systems may contain:

* visualization
* rendering
* interaction
* charting
* dashboards
* state management

Frontend systems must NOT contain:

* official strategy logic
* official backtesting logic
* broker execution logic
* risk engine logic
* normalization logic

Business-critical logic belongs in backend/runtime systems.

---

# API Review Rules

API routes must remain thin.

Preferred flow:

```text
route
→ service layer
→ domain/runtime layer
→ repository/adapter
```

INVALID:

```text
route
→ business logic
→ broker call
```

---

# Dependency Review Rules

Architecture reviews must evaluate dependencies for:

* necessity
* maintainability
* coupling risk
* vendor lock-in
* runtime complexity
* hidden abstractions

Avoid unnecessary framework complexity.

---

# Modularity Review Rules

Reviews should identify:

* oversized modules
* god objects
* hidden shared state
* tangled dependencies
* duplicated logic
* unstable abstractions

Preferred architecture:

```text
small explicit modules
clear contracts
isolated responsibilities
```

---

# Runtime Review Rules

Runtime systems must preserve:

* deterministic behavior
* observability
* traceability
* runtime safety
* reproducibility

Avoid hidden runtime mutation behavior.

---

# Storage Review Rules

Storage architecture should preserve:

* PostgreSQL for metadata
* DuckDB/Parquet for analytical datasets
* deterministic retrieval behavior
* schema traceability

Avoid forcing large time-series datasets into unsuitable storage patterns.

---

# Research Isolation Rules

Experimental research systems must remain isolated from:

* production runtime systems
* approved strategies
* execution systems

Research logic must not silently enter production paths.

---

# Reproducibility Review Rules

Reviews must evaluate whether systems preserve:

* deterministic behavior
* configuration traceability
* dataset traceability
* execution traceability
* reproducible workflows

Systems relying on hidden state or implicit behavior are invalid.

---

# Event-Driven Review Rules

Where appropriate, reviews should encourage:

```text
event-driven architecture
```

especially for:

* streaming systems
* runtime updates
* execution events
* monitoring systems

Avoid tightly coupled runtime polling systems when event-driven architecture is more appropriate.

---

# Observability Rules

Critical systems should expose:

* structured logging
* metrics
* diagnostics
* audit trails
* execution tracing

Systems must remain debuggable.

---

# Security Review Rules

Architecture reviews must evaluate risks involving:

* secrets handling
* runtime permissions
* execution access
* broker credentials
* live trading safeguards
* environment isolation

Avoid hidden security assumptions.

---

# Live Trading Review Rules

Live trading systems must preserve:

* approval gates
* risk controls
* auditability
* kill-switch capability
* compliance enforcement
* execution isolation

No uncontrolled live execution is allowed.

---

# Escalation Rules

Escalation is required if review identifies:

* architecture drift
* contract violations
* uncontrolled coupling
* execution safety risks
* live trading risks
* breaking contract changes
* runtime instability risks

High-impact findings must NOT be silently ignored.

---

# Refactoring Review Rules

Refactoring should be approved ONLY if it improves:

* modularity
* clarity
* maintainability
* reproducibility
* architecture integrity

Avoid speculative refactors without measurable benefit.

---

# Governance Review Rules

Architecture reviews should evaluate governance quality including:

* oversized documents
* duplicated governance responsibilities
* stale workflows
* unclear ownership
* context-loading inefficiency

Governance itself must remain maintainable.

---

# Approval Rules

A system may be approved ONLY if:

- [ ] architecture boundaries are preserved
- [ ] modularity is maintained
- [ ] normalized contracts are preserved
- [ ] execution isolation exists
- [ ] reproducibility is preserved
- [ ] observability exists
- [ ] no hidden coupling exists
- [ ] no forbidden patterns exist

---

# Forbidden Patterns

The following are prohibited:

* strategy-to-broker coupling
* provider-specific schema leakage
* frontend business logic
* API-layer business orchestration
* hidden mutable shared state
* uncontrolled runtime side effects
* live execution shortcuts
* monolithic service layers
* hidden architecture mutation
* undocumented contract changes

---

# Deliverables

Minimum expected deliverables:

* architecture review summary
* boundary analysis
* dependency analysis
* identified risks
* remediation recommendations
* approval/rejection decision
* escalation notes if required

---

# Validation Checklist

Before approving architecture changes, confirm:

- [ ] modularity is preserved
- [ ] contracts remain stable
- [ ] strategy portability exists
- [ ] execution isolation exists
- [ ] normalized data contracts are preserved
- [ ] reproducibility exists
- [ ] observability exists
- [ ] governance consistency is preserved
- [ ] no forbidden patterns exist
- [ ] no architecture guardrails were violated

---

# Final Instruction

Architecture reviews inside QuantLab exist to preserve long-term engineering integrity.

Architecture reviews are NOT:

* cosmetic reviews
* framework preference debates
* uncontrolled redesign opportunities
* convenience-driven shortcuts

The objective is to preserve institutional-grade engineering quality while ensuring the platform remains:

* modular
* reproducible
* extensible
* execution-safe
* maintainable
* architecture-consistent
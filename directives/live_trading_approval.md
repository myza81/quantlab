# LIVE_TRADING_APPROVAL.md

## Purpose

This directive defines the governance requirements, operational safeguards, approval gates, and runtime standards for enabling live trading inside QuantLab.

Live trading is the highest-risk operational stage inside the QuantLab lifecycle.

This directive exists to preserve:

* execution safety
* capital protection
* auditability
* compliance enforcement
* runtime stability
* architecture integrity
* institutional-grade operational discipline

---

# Core Philosophy

Live trading is NOT a default capability.

No strategy should ever transition automatically into live execution.

Live trading approval exists to ensure:

* strategies are validated
* runtime systems are stable
* execution controls exist
* risk controls exist
* auditability exists
* operational oversight exists

Safety takes priority over automation.

---

# Objective

When approving live trading capability, the implementation agent must:

1. preserve execution safety
2. validate operational readiness
3. preserve auditability
4. enforce approval gates
5. validate runtime stability
6. preserve architecture boundaries
7. prevent uncontrolled live execution

---

# Required Approval Workflow

Minimum required workflow:

```text
strategy review
→ validation review
→ runtime review
→ execution review
→ risk review
→ compliance review
→ operational readiness review
→ explicit approval
→ controlled live enablement
```

---

# Mandatory Lifecycle Requirement

A strategy must NOT enter live trading unless it has successfully completed:

```text
research
→ validation
→ backtesting
→ forward testing
→ paper trading
```

Lifecycle shortcuts are prohibited.

---

# Execution Isolation Rules

Strategies must remain execution-independent.

Strategies must NOT:

* place orders directly
* manage broker sessions
* bypass execution systems
* mutate portfolio state directly

VALID:

```text
strategy
→ signal
→ execution engine
→ broker adapter
```

INVALID:

```python
strategy.place_live_order()
```

---

# Approval Gate Rules

Live trading must require explicit approval gates including:

* strategy approval
* runtime approval
* risk approval
* compliance approval
* execution approval
* operational approval

All gates must remain reviewable and auditable.

---

# Runtime Safety Rules

Live trading systems must preserve:

* kill-switch capability
* runtime monitoring
* reconnect handling
* fail-safe behavior
* emergency shutdown capability
* execution throttling
* environment separation

Safety systems must remain active at all times.

---

# Risk Enforcement Rules

Live trading must enforce:

* exposure limits
* leverage limits
* position sizing rules
* drawdown controls
* concentration limits
* symbol restrictions
* portfolio constraints

Risk enforcement belongs to execution systems — not strategies.

---

# Compliance Rules

Compliance systems may enforce:

* halal restrictions
* asset restrictions
* market restrictions
* jurisdiction restrictions
* leverage restrictions
* operational constraints

Compliance must remain configurable and auditable.

Compliance must NOT be hardcoded inside strategies.

---

# Broker Adapter Rules

Live execution must occur ONLY through approved broker adapters.

Broker adapters must preserve:

* execution isolation
* retry handling
* error handling
* audit logging
* deterministic order routing behavior

Strategies must never communicate directly with brokers.

---

# Auditability Rules

Live trading systems must preserve:

* signal history
* order history
* execution logs
* portfolio changes
* approval history
* runtime diagnostics
* timestamps
* configuration snapshots

Live execution must remain reconstructable.

---

# Runtime Monitoring Rules

Live trading systems should expose:

* latency metrics
* execution metrics
* runtime diagnostics
* reconnect diagnostics
* portfolio metrics
* order metrics
* health monitoring
* structured logs

Operational visibility is mandatory.

---

# Deployment Rules

Live deployment must preserve:

* environment separation
* configuration isolation
* reproducible deployments
* rollback capability
* controlled activation

Avoid uncontrolled deployment workflows.

---

# Emergency Control Rules

Live trading systems must support:

* emergency disable
* execution pause
* broker disconnect
* portfolio freeze
* runtime shutdown
* manual intervention

Emergency controls must remain immediately accessible.

---

# Manual Intervention Rules

Manual intervention must remain possible at all times.

Operators must be able to:

* pause execution
* reject orders
* disable strategies
* override runtime behavior
* trigger emergency shutdowns

QuantLab must support human-controlled operation.

---

# Reproducibility Rules

Live systems must preserve:

* strategy version traceability
* runtime configuration traceability
* execution assumption traceability
* portfolio state traceability

Operational decisions must remain reconstructable.

---

# Experimental Strategy Rules

Experimental strategies must NEVER enter live trading environments.

Only approved strategies may become live-enabled.

Experimental runtime behavior must remain isolated.

---

# Operational Readiness Rules

Before enabling live trading, systems should validate:

* runtime stability
* reconnect handling
* latency stability
* execution consistency
* monitoring systems
* audit systems
* compliance systems
* rollback systems

Operational instability blocks approval.

---

# Approval Rules

Live trading may be approved ONLY if:

- [ ] lifecycle progression is complete
- [ ] strategy validation passes
- [ ] runtime stability is acceptable
- [ ] risk controls exist
- [ ] compliance systems exist
- [ ] auditability exists
- [ ] kill-switch capability exists
- [ ] operational monitoring exists
- [ ] execution isolation is preserved
- [ ] explicit approval is granted

---

# Rejection Rules

Live approval must be rejected if:

* runtime instability exists
* auditability is insufficient
* execution isolation is broken
* risk controls are insufficient
* compliance systems are missing
* reproducibility is broken
* emergency controls are missing

Operational safety takes priority over deployment pressure.

---

# Rollback Rules

Live-enabled systems must support:

* strategy disablement
* rollback deployment
* broker disconnection
* runtime shutdown
* configuration rollback

Rollback capability is mandatory.

---

# Forbidden Patterns

The following are prohibited:

* direct strategy-to-broker execution
* uncontrolled automation
* automatic live enablement
* undocumented runtime assumptions
* hidden execution behavior
* bypassing approval gates
* disabling audit logs
* disabling risk enforcement
* experimental strategies in live environments

---

# Deliverables

Minimum expected deliverables:

* approval review summary
* runtime validation summary
* risk validation summary
* compliance validation summary
* operational readiness summary
* deployment plan
* rollback plan
* approval/rejection decision

---

# Validation Checklist

Before approving live trading, confirm:

- [ ] lifecycle progression is complete
- [ ] execution isolation exists
- [ ] runtime stability is validated
- [ ] risk controls exist
- [ ] compliance enforcement exists
- [ ] auditability exists
- [ ] emergency controls exist
- [ ] operational monitoring exists
- [ ] rollback capability exists
- [ ] no architecture guardrails were violated

---

# Final Instruction

Live trading inside QuantLab exists only as a controlled and explicitly governed extension of the research lifecycle.

Live trading is NOT:

* unrestricted automation
* immediate deployment
* strategy-owned execution
* experimentation environment

The objective is to preserve institutional-grade operational safety while enabling controlled live execution workflows that maintain:

* execution safety
* auditability
* runtime stability
* compliance enforcement
* architecture integrity
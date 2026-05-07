# PROMOTE_STRATEGY.md

## Purpose

This directive defines the workflow, governance requirements, approval gates, lifecycle rules, and operational standards for promoting strategies through the QuantLab lifecycle.

Strategy promotion exists to ensure strategies advance through controlled and validated stages before reaching production-capable environments.

Promotion workflows preserve:

* architecture integrity
* execution safety
* reproducibility
* auditability
* lifecycle discipline
* institutional-grade governance

---

# Core Philosophy

Promotion is NOT automatic.

A profitable backtest alone does NOT justify promotion.

Strategy promotion exists to ensure:

* reproducibility
* robustness
* runtime stability
* risk awareness
* architecture compliance
* operational readiness

Every lifecycle transition must be deliberate and reviewable.

---

# Strategy Lifecycle

Strategies progress through:

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

Strategies must NOT skip lifecycle stages.

---

# Objective

When promoting a strategy, the implementation agent must:

1. validate lifecycle readiness
2. preserve auditability
3. validate architecture compliance
4. preserve execution safety
5. ensure reproducibility
6. preserve runtime portability
7. prevent uncontrolled promotion

---

# Required Promotion Workflow

Minimum required workflow:

```text
strategy review
→ validation review
→ reproducibility review
→ robustness review
→ runtime review
→ risk review
→ architecture review
→ approval decision
→ lifecycle transition update
```

---

# Promotion Scope

Promotion workflows may govern transitions between:

```text
research
→ prototype

prototype
→ validated

validated
→ backtested

backtested
→ forward-tested

forward-tested
→ paper-traded

paper-traded
→ approved-for-live
```

Each transition requires explicit approval criteria.

---

# Lifecycle Metadata Rules

Every strategy must preserve metadata including:

```yaml
name:
version:
status:
lifecycle_stage:
validation_status:
runtime_compatibility:
approval_history:
review_notes:
```

Lifecycle state must remain traceable.

---

# Research → Prototype Rules

Promotion from:

```text
research
→ prototype
```

requires:

- [ ] explicit hypothesis exists
- [ ] feature definitions exist
- [ ] normalized datasets are used
- [ ] experimental logic is isolated
- [ ] reproducibility is partially demonstrated

---

# Prototype → Validated Rules

Promotion from:

```text
prototype
→ validated
```

requires:

- [ ] reproducibility exists
- [ ] architecture compliance passes
- [ ] validation workflows exist
- [ ] feature logic is modularized
- [ ] no critical runtime instability exists

---

# Validated → Backtested Rules

Promotion from:

```text
validated
→ backtested
```

requires:

- [ ] deterministic backtesting exists
- [ ] dataset traceability exists
- [ ] no lookahead bias exists
- [ ] execution assumptions are documented
- [ ] reproducibility is validated

---

# Backtested → Forward-Tested Rules

Promotion from:

```text
backtested
→ forward-tested
```

requires:

- [ ] runtime portability exists
- [ ] backtest reproducibility is validated
- [ ] overfitting risk is reviewed
- [ ] runtime assumptions are documented
- [ ] operational stability is acceptable

---

# Forward-Tested → Paper-Traded Rules

Promotion from:

```text
forward-tested
→ paper-traded
```

requires:

- [ ] live data handling is stable
- [ ] signal consistency is acceptable
- [ ] runtime diagnostics are acceptable
- [ ] latency observations are acceptable
- [ ] execution isolation is preserved

---

# Paper-Traded → Approved-for-Live Rules

Promotion from:

```text
paper-traded
→ approved-for-live
```

requires:

- [ ] execution behavior is validated
- [ ] portfolio risk is acceptable
- [ ] compliance policies are validated
- [ ] operational monitoring exists
- [ ] auditability exists
- [ ] emergency controls exist
- [ ] explicit approval is granted

---

# Architecture Compliance Rules

Strategies may NOT be promoted if they violate:

* execution isolation
* strategy portability
* normalized data contracts
* runtime boundaries
* broker isolation
* frontend isolation

Architecture integrity is mandatory.

---

# Runtime Portability Rules

The SAME strategy logic must remain portable across:

* research
* backtesting
* forward testing
* paper trading
* live runtime

Mode-specific strategy branching is prohibited.

---

# Reproducibility Rules

Promotion requires reproducibility.

Identical:

* datasets
* parameters
* configurations

must produce reproducible outputs.

Non-reproducible strategies must not progress.

---

# Overfitting Review Rules

Promotion workflows must evaluate:

* parameter stability
* regime robustness
* sensitivity analysis
* out-of-sample behavior
* cross-market consistency

Curve-fitted strategies must not be promoted.

---

# Risk Review Rules

Promotion must review:

* drawdown behavior
* exposure behavior
* volatility sensitivity
* leverage assumptions
* tail-risk exposure
* concentration risk

Risk must remain explicitly understood.

---

# Runtime Safety Rules

Promotion into live-capable stages requires:

* execution approval gates
* auditability
* runtime monitoring
* kill-switch capability
* compliance enforcement
* execution isolation

No uncontrolled automation is allowed.

---

# Auditability Rules

Promotion workflows must preserve:

* review history
* validation evidence
* runtime evidence
* reproducibility evidence
* reviewer notes
* approval decisions
* rejection rationale
* timestamps

Promotion history must remain reconstructable.

---

# Rejection Rules

Strategies should be rejected or downgraded if:

* architecture violations exist
* reproducibility fails
* overfitting risk is excessive
* runtime instability exists
* operational safety is insufficient
* risk behavior is unacceptable
* validation evidence is insufficient

---

# Rollback Rules

Promoted strategies may be downgraded or retired if:

* runtime degradation appears
* instability emerges
* architecture violations are discovered
* risk behavior changes materially
* validation assumptions fail

Promotion is reversible.

---

# Experimental Strategy Rules

Experimental strategies must remain clearly labeled.

Experimental logic must NOT silently enter approved lifecycle stages.

Research and production systems must remain separated.

---

# Registry Update Rules

Promotion workflows should update:

* strategy registry
* lifecycle metadata
* validation metadata
* approval records
* runtime compatibility metadata

Registry state must remain synchronized with lifecycle state.

---

# Forbidden Patterns

The following are prohibited:

* automatic live approval
* undocumented promotion
* skipped lifecycle stages
* architecture-violating strategies
* non-reproducible promotion
* hidden runtime assumptions
* silent production deployment
* uncontrolled self-modifying behavior

---

# Deliverables

Minimum expected deliverables:

* promotion review summary
* validation evidence
* runtime review
* architecture review
* risk review
* approval/rejection decision
* lifecycle metadata update
* rollback notes if applicable

---

# Validation Checklist

Before approving promotion, confirm:

- [ ] lifecycle criteria are satisfied
- [ ] architecture compliance passes
- [ ] reproducibility exists
- [ ] runtime portability exists
- [ ] validation evidence exists
- [ ] overfitting risk is reviewed
- [ ] operational safety is acceptable
- [ ] auditability is preserved
- [ ] lifecycle metadata is updated
- [ ] no guardrails were violated

---

# Final Instruction

Strategy promotion inside QuantLab exists to preserve disciplined lifecycle governance.

Promotion is NOT:

* automatic progression
* profitability worship
* uncontrolled deployment
* shortcut-based validation

The objective is to ensure only reproducible, robust, architecture-safe, and operationally validated strategies progress through the QuantLab lifecycle while preserving:

* execution safety
* modularity
* reproducibility
* auditability
* institutional-grade governance
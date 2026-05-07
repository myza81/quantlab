# PAPER_TRADING.md

## Purpose

This directive defines the workflow, runtime rules, execution safeguards, and operational standards for paper trading inside QuantLab.

Paper trading exists to simulate realistic execution behavior using live or near-live market conditions without risking real capital.

Paper trading must remain:

* execution-safe
* auditable
* reproducible
* architecture-compliant
* runtime-controlled
* lifecycle-governed

---

# Core Philosophy

Paper trading is NOT live trading.

Paper trading exists to validate:

* execution workflows
* runtime behavior
* portfolio behavior
* operational stability
* signal-to-execution consistency
* risk handling
* monitoring systems

Paper trading must NOT become:

* uncontrolled automation
* hidden live execution
* broker bypass logic
* production deployment shortcut

---

# Objective

When running paper trading workflows, the implementation agent must:

1. preserve execution isolation
2. validate runtime behavior
3. preserve auditability
4. maintain architecture boundaries
5. validate portfolio behavior
6. preserve reproducibility
7. prevent uncontrolled live execution

---

# Required Paper Trading Workflow

Minimum required workflow:

```text
strategy selection
→ runtime initialization
→ live data ingestion
→ signal generation
→ execution simulation
→ portfolio simulation
→ runtime monitoring
→ diagnostics review
→ promotion or rejection
```

---

# Execution Isolation Rules

Strategies must remain execution-independent.

Strategies must NOT:

* place orders directly
* access broker APIs directly
* manage portfolio state directly
* bypass execution services

VALID:

```text
strategy
→ signal
→ execution simulator
→ simulated portfolio update
```

INVALID:

```python
strategy.place_order()
```

---

# Runtime Rules

Paper trading runtimes may include:

* live market feeds
* simulated execution engines
* portfolio tracking
* slippage simulation
* fee simulation
* runtime monitoring
* signal persistence
* diagnostics systems

Paper trading runtimes must remain isolated from live capital execution.

---

# Live Data Rules

Paper trading may use:

* WebSocket feeds
* polling feeds
* real-time OHLCV
* tick streams
* aggregated market streams

All data must pass through normalization pipelines before reaching strategies.

---

# Simulated Execution Rules

Paper trading execution systems should simulate:

* fills
* slippage
* spread effects
* latency
* fees
* partial fills
* execution delays

Simulation assumptions must remain explicit and reproducible.

---

# Portfolio Simulation Rules

Paper trading systems may simulate:

* positions
* cash balances
* leverage
* exposure
* PnL
* portfolio constraints
* risk limits

Portfolio behavior must remain auditable.

---

# Risk Enforcement Rules

Paper trading should validate:

* position sizing
* leverage controls
* exposure controls
* risk rejection behavior
* portfolio constraints
* compliance behavior

Risk enforcement belongs to execution systems — not strategies.

---

# Runtime Monitoring Rules

Paper trading systems should expose:

* signal logs
* order simulation logs
* portfolio logs
* latency metrics
* runtime diagnostics
* reconnect diagnostics
* execution metrics

Runtime behavior must remain observable.

---

# Drift Detection Rules

Paper trading should compare:

* backtest behavior
* forward-testing behavior
* paper execution behavior
* runtime assumptions
* feature distributions

Unexpected drift must be investigated before promotion.

---

# Operational Stability Rules

Paper trading should validate:

* reconnect handling
* runtime recovery
* synchronization stability
* missing-data handling
* execution consistency
* monitoring integrity

Systems must fail predictably.

Avoid silent runtime corruption.

---

# Compliance Rules

Paper trading may enforce:

* compliance policies
* halal constraints
* exposure restrictions
* symbol restrictions
* leverage rules

Compliance systems must remain configurable and isolated from strategies.

---

# Reproducibility Rules

Paper trading workflows must preserve:

* runtime configuration
* strategy version
* execution assumptions
* portfolio assumptions
* fee assumptions
* slippage assumptions

Operational behavior should remain reconstructable.

---

# Auditability Rules

Paper trading systems must preserve:

* signal history
* simulated orders
* fills
* portfolio changes
* runtime logs
* diagnostics
* timestamps
* configuration snapshots

Paper trading sessions must remain reviewable.

---

# Promotion Rules

A strategy may proceed toward:

```text
approved-for-live
```

ONLY if:

- [ ] runtime behavior is stable
- [ ] execution simulation is validated
- [ ] portfolio behavior is acceptable
- [ ] compliance behavior is validated
- [ ] operational monitoring exists
- [ ] runtime diagnostics are acceptable
- [ ] execution isolation is preserved

---

# Runtime Safety Rules

Paper trading systems must preserve:

* live execution disabled by default
* explicit environment separation
* execution safeguards
* runtime approval gates
* emergency shutdown capability

Paper trading must NEVER silently route real orders.

---

# Experimental Strategy Rules

Experimental strategies may use paper trading environments.

However:

Experimental strategies must remain explicitly labeled and isolated from approved production workflows.

---

# Failure Handling Rules

Paper trading failures must produce:

* explicit diagnostics
* runtime logs
* execution logs
* reconnect visibility
* traceable errors

Avoid silent failures.

---

# Forbidden Patterns

The following are prohibited:

* real order placement
* hidden live execution
* direct strategy-to-broker execution
* undocumented runtime assumptions
* uncontrolled automation
* hidden portfolio mutation
* raw provider schema leakage
* runtime-specific strategy hacks

---

# Deliverables

Minimum expected deliverables:

* paper trading configuration
* execution assumptions
* portfolio assumptions
* runtime diagnostics
* execution logs
* portfolio logs
* drift observations
* promotion/rejection recommendation

---

# Validation Checklist

Before approving paper trading workflows, confirm:

- [ ] execution isolation is preserved
- [ ] normalized live data is used
- [ ] execution simulation is validated
- [ ] portfolio behavior is observable
- [ ] runtime monitoring exists
- [ ] compliance behavior is validated
- [ ] auditability is preserved
- [ ] runtime safety exists
- [ ] live execution remains disabled
- [ ] no architecture guardrails were violated

---

# Final Instruction

Paper trading inside QuantLab exists to validate operational behavior in realistic runtime environments without risking real capital.

Paper trading is NOT:

* live trading
* production deployment
* unrestricted automation
* broker bypass execution

The objective is to create a controlled execution-simulation environment capable of supporting institutional-grade lifecycle progression while preserving:

* execution safety
* modularity
* auditability
* runtime stability
* architecture integrity
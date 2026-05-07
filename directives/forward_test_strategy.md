# FORWARD_TEST_STRATEGY.md

## Purpose

This directive defines the workflow, operational boundaries, runtime requirements, and validation discipline for forward testing strategies inside QuantLab.

Forward testing exists to validate strategy behavior using live or near-live market conditions without real capital deployment.

Forward testing must remain:

* deterministic
* reproducible
* execution-isolated
* auditable
* architecture-safe
* lifecycle-controlled

---

# Core Philosophy

Forward testing is a validation stage between:

```text
backtesting
→
paper trading
```

The objective is to evaluate:

* runtime behavior
* signal consistency
* live data handling
* regime adaptation
* timing behavior
* operational stability

Forward testing is NOT:

* live trading
* broker execution
* production deployment
* unrestricted automation

---

# Objective

When running forward tests, the implementation agent must:

1. preserve strategy portability
2. maintain execution isolation
3. preserve deterministic behavior
4. validate runtime stability
5. maintain auditability
6. preserve normalized data contracts
7. prevent uncontrolled live execution

---

# Required Forward Testing Workflow

Minimum required workflow:

```text
strategy selection
→ live data connection
→ normalization
→ runtime execution
→ signal generation
→ signal recording
→ validation review
→ reproducibility review
→ promotion or rejection
```

---

# Runtime Isolation Rules

Strategies must remain execution-independent.

Strategies must NOT:

* place live orders
* call brokers directly
* manage portfolio execution
* bypass runtime systems
* mutate external systems

VALID:

```text
live market data
→ normalization
→ strategy runtime
→ signal generation
→ logging/inspection
```

INVALID:

```python
broker.place_order()
```

---

# Live Data Rules

Forward testing may use:

* WebSocket streams
* polling systems
* live OHLCV feeds
* live tick feeds
* simulated real-time replay

All incoming data must pass through normalization layers.

Strategies must never consume raw provider schemas.

---

# Data Consistency Rules

Forward testing data contracts must match backtesting contracts.

The SAME strategy logic must operate consistently across:

* research
* backtesting
* forward testing
* paper trading

Differences must exist ONLY in runtime environments.

---

# Runtime Environment Rules

Forward testing runtimes may include:

* live market feeds
* event-driven execution
* streaming aggregation
* runtime monitoring
* signal persistence
* diagnostic logging

Forward testing runtimes must NOT include:

* unrestricted live execution
* broker-side portfolio management
* production capital routing

---

# Signal Recording Rules

All generated signals must be recorded.

Recommended metadata:

* timestamp
* instrument
* timeframe
* feature state
* signal type
* confidence
* runtime diagnostics
* latency metrics
* market context

Forward testing must remain inspectable.

---

# Latency Rules

Forward testing should measure:

* signal latency
* data latency
* aggregation latency
* runtime delays
* synchronization issues

Latency measurements should remain observable and reproducible.

---

# Runtime Stability Rules

Forward testing must evaluate runtime stability under:

* reconnect events
* missing data
* delayed data
* partial feeds
* malformed data
* streaming interruptions

Systems must fail predictably.

Avoid silent failures.

---

# Event Handling Rules

Preferred architecture:

```text
market data event
→ normalization
→ feature generation
→ strategy evaluation
→ signal generation
→ persistence/logging
```

Avoid tightly coupled polling loops where event-driven architecture is appropriate.

---

# State Management Rules

Forward testing state must remain explicit.

Runtime systems should preserve:

* warmup state
* active features
* synchronization state
* aggregation state
* signal history
* runtime diagnostics

Avoid hidden global state.

---

# Warmup Rules

Strategies requiring historical warmup must declare:

* warmup periods
* required feature history
* initialization requirements

Strategies must not silently assume fully initialized state.

---

# Runtime Safety Rules

Forward testing must remain operationally safe.

Required protections:

* execution disabled by default
* broker isolation
* signal-only operation
* runtime logging
* audit visibility
* emergency shutdown capability

Forward testing must NEVER silently transition into live trading.

---

# Validation Rules

Forward testing should validate:

* signal consistency
* runtime stability
* feature correctness
* live data behavior
* timing behavior
* synchronization correctness
* regime adaptation
* operational resilience

---

# Drift Detection Rules

Forward testing should compare:

* backtest expectations
* live signal behavior
* feature distributions
* runtime timing
* market regime differences

Unexpected drift should be investigated before promotion.

---

# Promotion Rules

A strategy may proceed toward paper trading ONLY if:

- [ ] runtime behavior is stable
- [ ] signals remain reproducible
- [ ] live data normalization is validated
- [ ] no architecture violations exist
- [ ] runtime diagnostics are acceptable
- [ ] execution isolation is preserved
- [ ] operational stability is validated

---

# Auditability Rules

Every forward-testing session should preserve:

* strategy version
* runtime configuration
* dataset/feed source
* timestamps
* signal history
* diagnostics
* runtime logs
* synchronization state
* latency measurements

Forward testing sessions must remain reconstructable.

---

# Experimental Strategy Rules

Experimental strategies are allowed during forward testing.

However:

Experimental strategies must remain clearly labeled and isolated from approved workflows.

Experimental runtime behavior must not silently become production-approved behavior.

---

# Forbidden Patterns

The following are prohibited:

* live order placement
* direct broker execution
* broker-specific strategy logic
* raw provider schema usage
* hidden runtime assumptions
* silent reconnect failures
* undocumented state mutation
* uncontrolled automation
* strategy-managed execution behavior

---

# Deliverables

Minimum expected deliverables:

* forward-testing configuration
* runtime configuration
* live data source definition
* signal logs
* runtime diagnostics
* latency observations
* validation summary
* promotion/rejection recommendation

---

# Validation Checklist

Before completing forward testing, confirm:

- [ ] strategy remained execution-independent
- [ ] normalized live data was used
- [ ] runtime stability was validated
- [ ] signals were recorded
- [ ] latency visibility exists
- [ ] no uncontrolled execution exists
- [ ] runtime diagnostics were captured
- [ ] drift analysis was reviewed
- [ ] auditability is preserved
- [ ] no architecture guardrails were violated

---

# Final Instruction

Forward testing inside QuantLab exists to validate runtime behavior under real market conditions without enabling uncontrolled execution.

Forward testing is NOT:

* live trading
* autonomous execution
* broker automation
* production deployment

The objective is to create a controlled runtime validation environment capable of supporting institutional-grade strategy lifecycle progression while preserving:

* execution isolation
* modularity
* reproducibility
* runtime safety
* architecture integrity
# VALIDATE_STRATEGY.md

## Purpose

This directive defines the workflow, governance standards, validation requirements, and approval criteria for validating strategies inside QuantLab.

Strategy validation exists to ensure strategies are:

* reproducible
* robust
* portable
* execution-safe
* architecture-compliant
* lifecycle-ready

Validation is required before a strategy may progress through lifecycle stages.

---

# Core Philosophy

Validation is NOT:

* visual confirmation
* isolated profitability review
* single-market optimization
* curve-fitting approval

Validation exists to evaluate whether a strategy is:

* trustworthy
* reproducible
* robust
* architecture-safe
* operationally stable

---

# Objective

When validating a strategy, the implementation agent must:

1. validate reproducibility
2. validate architecture compliance
3. validate runtime stability
4. validate robustness
5. validate risk behavior
6. validate portability
7. prevent premature promotion

---

# Required Validation Workflow

Minimum required workflow:

```text
strategy review
→ feature validation
→ data validation
→ backtest validation
→ robustness testing
→ runtime validation
→ risk review
→ reproducibility review
→ promotion or rejection
```

---

# Validation Scope

Validation may include:

* strategy logic review
* feature integrity review
* dataset validation
* backtest review
* forward-testing review
* runtime review
* drawdown analysis
* risk analysis
* robustness testing
* cross-market evaluation
* sensitivity testing

---

# Strategy Contract Validation

Strategies must expose required interfaces:

```python
build_features()
generate_signals()
apply_risk_rules()
validate_config()
```

Strategies must remain:

* deterministic
* execution-independent
* normalized-data compliant
* runtime-portable

---

# Architecture Compliance Rules

Validation must confirm:

* no broker coupling exists
* no frontend dependencies exist
* no provider-specific schema leakage exists
* no execution logic exists inside strategies
* no runtime-mode branching exists

Strategies violating architecture boundaries are invalid.

---

# Reproducibility Rules

Strategies must produce reproducible outputs.

Repeated execution using identical:

* datasets
* parameters
* configurations

must produce consistent results.

---

# Dataset Validation Rules

Validation must confirm:

* normalized datasets are used
* timestamps are valid
* no future-data leakage exists
* dataset traceability exists
* dataset versions are recorded

---

# Backtest Validation Rules

Validation must review:

* reproducibility
* slippage assumptions
* fee assumptions
* execution assumptions
* lookahead bias
* overfitting risk
* robustness

Backtest profitability alone is insufficient.

---

# Forward Testing Validation Rules

Validation should review:

* runtime stability
* live data handling
* signal consistency
* latency observations
* reconnect behavior
* runtime diagnostics

---

# Robustness Rules

Validation should evaluate:

* multiple market regimes
* multiple instruments
* multiple timeframes
* parameter sensitivity
* stress scenarios
* out-of-sample behavior

Strategies dependent on narrow conditions are high-risk.

---

# Overfitting Review Rules

Validation must identify:

* excessive optimization
* unstable parameters
* unrealistic metrics
* regime fragility
* curve-fitting behavior

Strategies showing overfitting risk should be rejected or downgraded.

---

# Risk Validation Rules

Validation must review:

* drawdown behavior
* volatility exposure
* concentration risk
* leverage assumptions
* trade frequency
* tail-risk behavior

Risk must remain explicitly understood.

---

# Runtime Portability Rules

The SAME strategy logic must function consistently across:

* research
* backtesting
* forward testing
* paper trading
* future live runtime

Mode-specific strategy behavior is prohibited.

---

# Experimental Strategy Rules

Experimental strategies may remain in:

```text
research
prototype
experimental
```

status.

Experimental status must remain explicitly labeled.

Experimental strategies must NOT silently become production-approved.

---

# Validation Metrics Rules

Validation may review:

* Sharpe ratio
* expectancy
* drawdown
* volatility
* exposure
* trade duration
* regime consistency
* stability metrics
* parameter sensitivity

Metrics must remain transparent and reproducible.

---

# Auditability Rules

Validation workflows must preserve:

* strategy version
* dataset version
* parameter configuration
* runtime assumptions
* validation outputs
* diagnostics
* timestamps
* reviewer notes

Validation must remain reconstructable.

---

# Approval Rules

A strategy may be approved ONLY if:

- [ ] strategy is reproducible
- [ ] architecture compliance passes
- [ ] normalized datasets are used
- [ ] no future-data leakage exists
- [ ] robustness is acceptable
- [ ] overfitting risk is acceptable
- [ ] runtime portability exists
- [ ] risk behavior is acceptable
- [ ] auditability is preserved

---

# Rejection Rules

A strategy should be rejected or downgraded if:

* architecture violations exist
* reproducibility fails
* overfitting risk is excessive
* runtime instability exists
* risk behavior is unacceptable
* portability is broken
* validation evidence is insufficient

---

# Forbidden Patterns

The following are prohibited:

* broker-dependent strategies
* provider-specific logic leakage
* execution logic inside strategies
* non-reproducible behavior
* hidden feature calculations
* undocumented assumptions
* future-data leakage
* uncontrolled runtime mutation

---

# Deliverables

Minimum expected deliverables:

* validation summary
* reproducibility review
* robustness review
* risk review
* architecture compliance review
* validation metrics
* approval/rejection recommendation

---

# Validation Checklist

Before approving strategy validation, confirm:

- [ ] strategy is reproducible
- [ ] normalized datasets are used
- [ ] no execution coupling exists
- [ ] runtime portability exists
- [ ] robustness testing exists
- [ ] overfitting risk was reviewed
- [ ] risk behavior is acceptable
- [ ] auditability is preserved
- [ ] architecture compliance passes
- [ ] no guardrails were violated

---

# Final Instruction

Strategy validation inside QuantLab exists to preserve disciplined lifecycle progression.

Validation is NOT:

* profitability worship
* optimization theater
* visual-only confirmation
* uncontrolled experimentation

The objective is to ensure only reproducible, robust, portable, and architecture-safe strategies progress through the QuantLab lifecycle while preserving:

* modularity
* reproducibility
* execution safety
* auditability
* institutional-grade engineering discipline
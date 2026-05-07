# BACKTEST_STRATEGY.md

## Purpose

This directive defines the required workflow, architecture boundaries, reproducibility requirements, and validation standards for running strategy backtests inside QuantLab.

Backtesting inside QuantLab must be:

* deterministic
* reproducible
* auditable
* modular
* execution-independent
* architecture-safe

The purpose of this directive is to prevent:

* lookahead bias
* hidden execution assumptions
* overfitting
* inconsistent datasets
* non-reproducible results
* strategy/runtime coupling
* invalid promotion of strategies

---

# Core Philosophy

Backtesting is NOT proof of profitability.

Backtesting is a controlled simulation environment used to:

* validate hypotheses
* inspect behavior
* measure robustness
* evaluate assumptions
* compare strategies
* identify weaknesses
* support promotion decisions

Backtesting must NOT become:

* a curve-fitting machine
* a visual-only validation process
* an uncontrolled optimization engine
* a hidden execution simulator

---

# Objective

When running a backtest, the implementation agent must:

1. preserve deterministic execution
2. isolate strategy logic from execution systems
3. preserve normalized data contracts
4. maintain auditability
5. preserve reproducibility
6. document assumptions
7. avoid architecture violations

---

# Required Backtest Workflow

Minimum required workflow:

```text
strategy selection
→ dataset selection
→ parameter definition
→ execution assumptions
→ simulation execution
→ result generation
→ validation review
→ reproducibility verification
→ promotion or rejection decision
```

Backtesting must remain structured and reviewable.

---

# Backtesting Scope

Backtesting may evaluate:

* signal quality
* risk behavior
* market regime behavior
* feature effectiveness
* strategy robustness
* timing consistency
* volatility sensitivity
* exposure characteristics
* trade frequency
* drawdown behavior

Backtesting must NOT directly evaluate:

* real broker latency
* live slippage certainty
* guaranteed profitability
* production execution quality

---

# Strategy Isolation Rules

Strategies must remain execution-independent during backtesting.

Strategies must NOT:

* place orders
* access brokers
* access exchanges
* read databases directly
* mutate external state
* know runtime mode

Backtesting engines interpret signals.

Strategies produce decisions only.

VALID:

```text
strategy → signal
backtest engine → simulation
```

INVALID:

```python
strategy.place_order()
```

---

# Deterministic Execution Rules

Backtests must produce reproducible outputs.

Given identical:

* datasets
* parameters
* assumptions
* execution configuration

the results must remain reproducible.

Avoid:

* hidden randomness
* unstable dynamic behavior
* environment-dependent calculations
* implicit data mutations

---

# Dataset Rules

Backtests must use normalized datasets only.

Supported datasets may include:

* OHLCV
* tick data
* alternative datasets
* sentiment datasets
* planetary datasets
* macroeconomic datasets
* derived feature datasets

Raw provider schemas must NOT reach strategies.

INVALID:

```python
binance_kline["close"]
```

VALID:

```python
candle.close
```

---

# Dataset Versioning Rules

Every backtest must preserve dataset traceability.

Required metadata:

* dataset identifier
* dataset version
* timeframe
* instrument universe
* adjustment assumptions
* missing-data handling rules
* preprocessing assumptions

Backtests without dataset traceability are invalid.

---

# Time Alignment Rules

All datasets must maintain correct timestamp alignment.

Special attention required for:

* multi-timeframe strategies
* alternative datasets
* macroeconomic releases
* planetary calculations
* delayed datasets
* cross-market data

Avoid future-data leakage.

---

# Lookahead Bias Rules

Backtests must prevent lookahead bias.

Strategies must never access:

* future candles
* future features
* future signals
* future labels
* future market structure

Feature pipelines must respect causal ordering.

INVALID:

```python
future_close = candles[i + 1]
```

---

# Survivorship Bias Rules

Where applicable, backtests should consider survivorship bias.

Avoid validating strategies only against surviving assets when broader historical universes are required.

---

# Slippage and Fee Rules

Execution assumptions must be explicit.

Backtests should define:

* slippage assumptions
* fee assumptions
* spread assumptions
* execution latency assumptions
* liquidity assumptions

Do NOT silently ignore transaction costs.

---

# Execution Simulation Rules

The backtesting engine is responsible for:

* fill simulation
* position management
* portfolio simulation
* fee modeling
* slippage handling
* trade lifecycle simulation

Strategies must NOT implement simulation mechanics internally.

---

# Position Sizing Rules

Position sizing assumptions must be explicit.

Supported approaches may include:

* fixed sizing
* volatility sizing
* risk-based sizing
* percentage exposure
* portfolio constraints

Sizing logic should remain reproducible and reviewable.

---

# Multi-Asset Rules

Multi-asset strategies must preserve:

* timestamp synchronization
* market session handling
* cross-market consistency
* deterministic aggregation

Avoid hidden synchronization assumptions.

---

# Optimization Rules

Parameter optimization must remain controlled.

Optimization may be used for:

* sensitivity analysis
* robustness analysis
* parameter exploration

Optimization must NOT become:

* blind curve fitting
* overfitting engine
* hidden parameter mining

---

# Overfitting Prevention Rules

Agents must actively guard against overfitting.

Warning signs include:

* extremely narrow parameter sensitivity
* unstable regime behavior
* excessive optimization dependency
* unrealistic win rates
* highly unstable out-of-sample performance

Backtest performance alone does NOT validate a strategy.

---

# Validation Rules

Backtests should support:

* out-of-sample validation
* walk-forward analysis
* regime comparison
* timeframe comparison
* robustness testing
* stress testing
* sensitivity analysis

Avoid relying on a single historical window.

---

# Statistical Evaluation Rules

Backtests may evaluate:

* win rate
* expectancy
* Sharpe ratio
* drawdown
* volatility
* exposure
* trade duration
* profit factor
* regime consistency

Metrics must remain transparent and reproducible.

---

# Research vs Production Rules

Backtesting environments may support experimental strategies.

However:

Experimental backtests must remain isolated from production promotion workflows until validated.

Research logic must NOT silently become approved execution logic.

---

# Auditability Rules

Every backtest should preserve:

* strategy ID
* strategy version
* parameter configuration
* dataset version
* runtime assumptions
* execution assumptions
* timestamp
* generated metrics
* diagnostics
* logs

Backtests must remain reconstructable.

---

# Result Interpretation Rules

Backtest outputs are decision-support tools.

They are NOT guarantees.

Avoid:

* overconfidence
* single-metric evaluation
* visually-biased conclusions
* isolated cherry-picked examples

Backtests must be interpreted critically.

---

# Promotion Rules

A strategy may proceed toward forward testing ONLY if:

- [ ] results are reproducible
- [ ] datasets are traceable
- [ ] execution assumptions are documented
- [ ] no lookahead bias exists
- [ ] no architecture violations exist
- [ ] risk behavior is acceptable
- [ ] validation exists
- [ ] overfitting risk is evaluated

---

# Forbidden Patterns

The following are prohibited:

* direct broker integration
* direct live execution
* strategy-managed orders
* hidden slippage assumptions
* non-versioned datasets
* future-data leakage
* frontend-only calculations
* hardcoded execution assumptions
* uncontrolled parameter mining
* non-reproducible workflows

---

# Deliverables

Minimum expected deliverables:

* backtest configuration
* dataset definition
* parameter definition
* execution assumptions
* reproducible results
* validation outputs
* metrics summary
* diagnostics
* promotion/rejection recommendation

---

# Validation Checklist

Before completing a backtest, confirm:

- [ ] strategy remained execution-independent
- [ ] normalized datasets were used
- [ ] dataset versioning exists
- [ ] results are reproducible
- [ ] no lookahead bias exists
- [ ] slippage assumptions are documented
- [ ] validation exists
- [ ] overfitting risk was reviewed
- [ ] auditability is preserved
- [ ] no architecture guardrails were violated

---

# Final Instruction

Backtesting inside QuantLab exists to support disciplined strategy validation.

Backtesting is NOT:

* proof of future profitability
* unrestricted optimization
* visual storytelling
* uncontrolled experimentation

The objective is to create a deterministic and reproducible simulation environment capable of supporting institutional-grade strategy research and lifecycle progression while preserving:

* modularity
* auditability
* reproducibility
* execution isolation
* architecture integrity
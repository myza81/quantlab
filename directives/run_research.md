# RUN_RESEARCH.md

## Purpose

This directive defines the required workflow, architecture discipline, operational boundaries, and validation standards for conducting research inside QuantLab.

QuantLab is a research-first strategy ecosystem.

The purpose of this directive is to ensure all research activities remain:

* reproducible
* modular
* traceable
* isolated
* hypothesis-driven
* architecture-safe

This directive applies to:

* exploratory research
* experimental feature analysis
* signal discovery
* cyclical research
* planetary/astronomical analysis
* quantitative analysis
* pattern discovery
* prototype strategy validation

---

# Core Philosophy

Research inside QuantLab is NOT random experimentation.

Research must follow disciplined workflows.

Research should produce:

* hypotheses
* observations
* measurable outputs
* reproducible experiments
* reusable features
* strategy insights
* validation evidence

Research must NOT produce:

* uncontrolled production logic
* hidden calculations
* architecture violations
* direct execution behavior
* undocumented assumptions

---

# Research Lifecycle

Every research workflow should progress through:

```text
hypothesis
→ dataset selection
→ feature exploration
→ signal hypothesis
→ validation
→ reproducibility check
→ backtesting candidate
→ forward-testing candidate
→ strategy promotion or rejection
```

Research must remain modular and reviewable.

---

# Objective

When conducting research, the implementation agent must:

1. preserve experimental isolation
2. maintain reproducibility
3. avoid contaminating production systems
4. preserve normalized data contracts
5. support deterministic workflows
6. maintain traceability
7. document assumptions and limitations

---

# Research Categories

QuantLab research may include:

* price action research
* volatility analysis
* cycle analysis
* seasonal analysis
* planetary/astronomical studies
* macroeconomic relationships
* sentiment analysis
* market structure analysis
* pattern discovery
* feature engineering
* intermarket relationships
* timing models
* unconventional datasets

All research categories must still follow architecture discipline.

---

# Research Isolation Rules

Experimental research must remain isolated from production systems.

Research artifacts must NOT directly enter:

* live trading systems
* production execution layers
* broker adapters
* official strategy registries

Research workflows must remain explicitly marked as:

```text
experimental
prototype
validated
```

until formally promoted.

---

# Required Research Workflow

Minimum required workflow:

```text
1. Define hypothesis
2. Identify datasets
3. Normalize datasets
4. Generate features
5. Explore relationships
6. Define measurable conditions
7. Validate findings
8. Record assumptions
9. Evaluate reproducibility
10. Decide promotion or rejection
```

Avoid uncontrolled exploration without measurable objectives.

---

# Hypothesis Rules

Every research workflow must begin with a clear hypothesis.

Good hypothesis examples:

* volatility compression precedes directional expansion
* lunar cycle phase affects intraday volatility
* market structure imbalance predicts reversal probability
* planetary alignment correlates with cycle timing

Bad hypothesis examples:

* find something interesting
* explore random indicators
* test everything

Research objectives must be explicit.

---

# Dataset Rules

All datasets must pass through normalization pipelines.

Research datasets may include:

* OHLCV
* tick data
* order flow
* macroeconomic data
* sentiment data
* astronomical datasets
* planetary datasets
* seasonal datasets
* custom analytical datasets

Research code must NOT consume raw provider schemas directly.

INVALID:

```python
binance_response["kline"]
```

VALID:

```python
normalized_candle.close
```

---

# Alternative Dataset Rules

Alternative and unconventional datasets are fully supported.

Examples:

* planetary position data
* moon phase data
* solar cycle data
* eclipse timing
* seasonal timing
* symbolic cycle datasets
* macroeconomic cycle data

However:

All alternative datasets must follow:

```text
source
→ ingestion
→ normalization
→ feature engineering
→ strategy usage
```

Avoid embedding raw external calculations directly into strategies.

---

# Feature Engineering Rules

Reusable research calculations must be modularized.

Preferred location:

```text
research/features/
```

or:

```text
strategies/{strategy_name}/features.py
```

depending on scope and reusability.

Avoid:

* duplicated calculations
* hidden transformations
* inline feature spaghetti logic

---

# Research Notebook Rules

Research notebooks are allowed for exploration.

However:

Notebooks are NOT production systems.

Notebook logic must not become production code through direct copy-paste.

Validated logic must be migrated into:

* feature modules
* strategy modules
* reusable research services

before promotion.

---

# Reproducibility Rules

Research must be reproducible.

Research artifacts should preserve:

* dataset version
* timeframe
* instrument universe
* parameter sets
* feature definitions
* assumptions
* environment context
* timestamps

Repeated execution with identical inputs should produce consistent outputs.

---

# Experimental Strategy Rules

Experimental strategies must remain isolated from validated systems.

Experimental strategies may:

* fail frequently
* use unstable logic
* contain exploratory calculations
* evolve rapidly

This is acceptable during research.

However:

Experimental strategies must NOT silently enter production workflows.

---

# Research Artifact Rules

Research workflows should produce durable artifacts such as:

* feature definitions
* charts
* experiment summaries
* validation outputs
* statistical observations
* hypothesis evaluations
* reproducibility notes
* rejection rationale

Artifacts should remain reviewable.

---

# Validation Rules

Research findings must be validated before promotion.

Validation may include:

* statistical validation
* historical replay
* cross-market validation
* out-of-sample testing
* regime testing
* timeframe comparison
* robustness testing
* sensitivity testing

Avoid promoting findings based only on visual inspection.

---

# Correlation vs Causation Rules

Research agents must avoid confusing:

```text
correlation
≠
causation
```

Observed relationships must be treated cautiously until validated.

Avoid:

* overfitting
* survivorship bias
* cherry-picking
* hindsight bias
* curve fitting without robustness

---

# Promotion Rules

A research output may be promoted ONLY if:

- [ ] hypothesis is clearly defined
- [ ] results are reproducible
- [ ] datasets are normalized
- [ ] findings are documented
- [ ] validation exists
- [ ] feature logic is modularized
- [ ] no architecture violations exist
- [ ] strategy portability is preserved

Promotion targets may include:

* reusable features
* prototype strategies
* backtesting candidates
* research services
* analytical modules

---

# Forbidden Patterns

The following are prohibited:

* direct broker integration inside research
* production execution shortcuts
* hidden feature calculations
* undocumented assumptions
* direct live trading from notebooks
* raw provider schema leakage
* hardcoded environment assumptions
* non-reproducible workflows
* silent promotion of experimental logic
* mixing experimental and production systems

---

# Research Folder Philosophy

Research environments should remain modular and organized.

Preferred principles:

```text
small experiments
clear hypotheses
isolated datasets
reusable features
deterministic workflows
```

Avoid:

```text
giant unstructured notebook collections
```

---

# Deliverables

Minimum expected deliverables for serious research:

* research hypothesis
* dataset definition
* feature definitions
* experiment workflow
* validation output
* reproducibility notes
* promotion/rejection decision
* documentation summary

---

# Validation Checklist

Before completing research work, confirm:

- [ ] hypothesis is explicit
- [ ] datasets are normalized
- [ ] calculations are reproducible
- [ ] experimental logic is isolated
- [ ] reusable features are modularized
- [ ] validation exists
- [ ] assumptions are documented
- [ ] no execution logic exists
- [ ] no architecture guardrails are violated

---

# Final Instruction

QuantLab research is intended to support rigorous strategy discovery and validation.

Research is NOT:

* random experimentation
* uncontrolled indicator stacking
* immediate live trading generation

The objective is to create a disciplined research ecosystem capable of evolving into institutional-grade strategy discovery infrastructure while preserving:

* reproducibility
* modularity
* portability
* architecture integrity
* long-term maintainability
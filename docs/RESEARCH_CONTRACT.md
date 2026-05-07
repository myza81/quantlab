# RESEARCH_CONTRACT.md

## Purpose

This document defines the canonical research contracts for QuantLab.

The purpose of this document is to establish:

* research workflow discipline
* experimental isolation rules
* research lifecycle standards
* reproducibility requirements
* hypothesis management
* feature experimentation contracts
* notebook governance
* artifact handling
* promotion rules from research to production
* unconventional research integration standards

QuantLab is fundamentally a research-first platform.

This document defines how research systems evolve safely without corrupting production architecture.

---

# Core Research Philosophy

Research is treated as a first-class architectural domain inside QuantLab.

The platform is intentionally designed to support:

* exploratory analysis
* hypothesis testing
* unconventional research
* iterative experimentation
* signal discovery
* cycle analysis
* planetary and astronomical studies
* discretionary workflow support
* semi-systematic strategy development

Research systems prioritize:

* flexibility
* experimentation
* iteration
* exploration

However:

research must still preserve:

* reproducibility
* modularity
* auditability
* deterministic workflows
* architectural discipline

---

# Research Isolation Principle

Research systems must remain isolated from production execution systems.

---

## Research Systems MAY Include

* notebooks
* temporary experiments
* prototype indicators
* experimental feature engineering
* exploratory datasets
* visual analysis
* discretionary workflows
* partially validated logic

---

## Research Systems MUST NOT Directly Become

* live trading systems
* production runtime systems
* official execution systems
* portfolio risk systems

Research outputs must graduate through controlled lifecycle validation before production use.

---

# Canonical Research Lifecycle

All research artifacts should progress through structured maturity stages.

---

## Research Lifecycle

```text id="y84plv"
idea
→ hypothesis
→ exploratory research
→ prototype
→ validation
→ structured testing
→ strategy integration
→ backtesting
→ forward testing
→ paper trading
→ future live approval
```

---

# Research Structure Contract

---

## Canonical Research Structure

```text id="1ep81t"
research/

├── hypotheses/
├── experiments/
├── feature_exploration/
├── cycle_research/
├── planetary/
├── validation/
├── artifacts/
├── notebooks/
├── reports/
└── archived/
```

---

# Research Folder Responsibilities

---

## `hypotheses/`

### Responsibilities

* research ideas
* market assumptions
* exploratory concepts
* theoretical observations

### Examples

* cycle timing hypotheses
* planetary influence assumptions
* volatility regime observations

---

## `experiments/`

### Responsibilities

* isolated experiments
* temporary workflows
* feature trials
* exploratory systems

### Important Rule

Experiments must remain isolated from production runtime systems.

---

## `feature_exploration/`

### Responsibilities

* feature discovery
* indicator experimentation
* transformation testing
* feature comparison workflows

---

## `cycle_research/`

### Responsibilities

* cycle analysis
* timing relationships
* periodicity exploration
* recurrence analysis

---

## `planetary/`

### Responsibilities

* astronomical calculations
* planetary alignment studies
* temporal relationship analysis
* symbolic timing systems

### Important Rule

Planetary systems must still follow:

```text id="0xstpb"
normalization
validation
reproducibility
versioning
```

---

## `validation/`

### Responsibilities

* reproducibility validation
* statistical verification
* experiment comparison
* robustness testing

---

## `artifacts/`

### Responsibilities

* generated research outputs
* snapshots
* charts
* experiment outputs
* reports

### Important Rule

Artifacts are not canonical source-of-truth systems.

---

## `notebooks/`

### Responsibilities

* exploratory workflows
* rapid experimentation
* temporary analytical work

### Important Rule

Notebook logic must NEVER directly become production code.

---

## `reports/`

### Responsibilities

* experiment summaries
* research findings
* validation reports
* promotion recommendations

---

# Research Data Contract

Research systems must consume only normalized datasets.

Research workflows must never directly depend on:

* raw provider payloads
* broker-native schemas
* unstable runtime payloads

All research datasets must follow `DATA_CONTRACT.md`.

---

# Experimental Feature Contract

Experimental features must remain isolated until validated.

---

## Allowed Experimental Features

* prototype indicators
* cycle-derived features
* astronomical relationships
* unconventional transformations
* temporal alignment systems
* exploratory statistical signals

---

## Required Experimental Metadata

| Field                  | Description            |
| ---------------------- | ---------------------- |
| feature_id             | feature identifier     |
| version                | feature version        |
| generation_method      | generation methodology |
| source_dataset         | source dataset         |
| validation_status      | maturity status        |
| reproducibility_status | reproducibility state  |

---

# Hypothesis Contract

All research hypotheses should be explicitly documented.

---

## Required Hypothesis Metadata

| Field              | Description            |
| ------------------ | ---------------------- |
| hypothesis_id      | unique identifier      |
| author             | creator                |
| creation_timestamp | creation time          |
| target_market      | target market          |
| target_timeframe   | target timeframe       |
| assumptions        | underlying assumptions |
| validation_status  | validation stage       |

---

# Research Reproducibility Rules

Research workflows must remain reproducible whenever possible.

---

## Required Reproducibility Areas

* dataset versioning
* feature versioning
* parameter versioning
* experiment metadata
* runtime assumptions

---

## Important Rule

Research conclusions must be traceable to:

```text id="t0e9ev"
dataset
parameter set
feature version
runtime assumptions
```

---

# Notebook Governance Rules

Notebooks are allowed for experimentation only.

---

## Allowed Notebook Usage

* exploratory analysis
* temporary visualization
* feature validation
* prototype logic

---

## Forbidden Notebook Usage

* direct live execution
* production runtime orchestration
* broker integration
* permanent business logic

---

## Notebook Promotion Rule

Notebook logic must be refactored into:

* reusable modules
* validated feature pipelines
* production-grade systems

before entering runtime systems.

---

# Research Artifact Contract

Research artifacts must remain structured and traceable.

---

## Examples

* charts
* feature snapshots
* validation reports
* comparison studies
* experiment outputs

---

## Required Artifact Metadata

| Field                | Description       |
| -------------------- | ----------------- |
| artifact_id          | unique identifier |
| generation_timestamp | creation time     |
| experiment_reference | linked experiment |
| dataset_reference    | linked dataset    |
| feature_reference    | linked features   |

---

# Validation Contract

Research outputs must pass validation before promotion.

---

## Validation Areas

### Statistical Validation

* reproducibility
* robustness
* stability
* sensitivity testing

### Data Validation

* dataset consistency
* normalization integrity
* timeframe consistency

### Runtime Validation

* deterministic behavior
* replay compatibility
* feature stability

---

# Promotion Contract

Research outputs must follow controlled promotion workflows.

---

## Promotion Flow

```text id="kt0p46"
research
→ prototype
→ validation
→ structured testing
→ strategy integration
→ backtesting
→ forward testing
→ paper trading
```

---

## Important Rule

Research systems must not bypass validation stages.

---

# Experimental Isolation Rules

Experimental logic must remain clearly marked.

---

## Experimental Systems MUST NOT

* bypass risk systems
* directly place orders
* bypass validation
* bypass runtime contracts
* directly access execution systems

---

# Research Runtime Rules

Research workflows may support:

* manual intervention
* discretionary analysis
* semi-systematic evaluation

QuantLab intentionally supports both:

* systematic strategies
* discretionary-assisted workflows

---

# Research Metadata Contract

All major experiments should preserve metadata.

---

## Required Metadata

| Field                 | Description             |
| --------------------- | ----------------------- |
| experiment_id         | unique identifier       |
| dataset_version       | dataset used            |
| feature_versions      | feature versions        |
| parameter_set         | parameter configuration |
| runtime_assumptions   | runtime assumptions     |
| execution_environment | runtime environment     |

---

# Alternative Research Support

QuantLab explicitly supports unconventional research.

---

## Examples

* planetary movement analysis
* lunar cycle analysis
* solar timing analysis
* symbolic cycles
* seasonality research
* macro relationships
* sentiment relationships

---

## Important Rule

Unconventional research must still preserve:

* reproducibility
* normalization
* metadata tracking
* deterministic processing

---

# Research vs Production Separation

Research systems prioritize exploration.

Production systems prioritize:

* stability
* reproducibility
* auditability
* operational safety

The transition between research and production must remain controlled.

---

# Forbidden Research Patterns

The following patterns are prohibited:

* notebook-to-live execution shortcuts
* hidden experimental runtime behavior
* direct research-to-broker coupling
* bypassing validation pipelines
* undocumented experimental features
* silent mutation of datasets
* untracked parameter experimentation
* production systems depending on temporary notebooks

---

# AI-Assisted Research Rules

AI-assisted research workflows are allowed.

However:

AI-generated insights must still undergo:

* validation
* reproducibility testing
* structured review
* lifecycle promotion

AI suggestions are not automatically trusted research conclusions.

---

# Research Auditability Principles

Research systems should preserve:

* traceability
* reproducibility
* metadata lineage
* experiment lineage
* feature lineage

Research conclusions should remain explainable and reconstructable.

---

# Future Research Expansion Direction

Future research systems may include:

* advanced experiment orchestration
* automated feature pipelines
* AI-assisted hypothesis generation
* distributed experimentation
* feature marketplaces
* collaborative research workflows
* advanced statistical validation engines

These capabilities must still preserve:

* modularity
* reproducibility
* deterministic workflows
* architecture isolation

---

# Final Research Principle

Research is one of the core identities of QuantLab.

The platform is intentionally designed to support deep experimentation and unconventional exploration while preserving institutional-grade engineering discipline.

All research systems must preserve:

* flexibility
* reproducibility
* modularity
* traceability
* validation discipline
* controlled promotion into production systems

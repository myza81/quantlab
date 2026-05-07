# REPOSITORY_STRUCTURE.md

## Purpose

This document defines the physical repository organization for QuantLab.

The purpose of this structure is to:

* preserve modular boundaries
* reduce architectural drift
* support AI-assisted engineering workflows
* improve repository navigability
* minimize context fragmentation
* support long-term maintainability
* enable scalable system evolution

This document defines:

* repository-level folder responsibilities
* module ownership boundaries
* architectural placement rules
* organizational conventions
* repository governance expectations

This document does NOT define detailed implementation contracts.

Detailed architecture behavior belongs in:

* `ARCHITECTURE.md`
* `DATA_CONTRACT.md`
* `STRATEGY_CONTRACT.md`
* `EXECUTION_CONTRACT.md`
* `API_CONTRACT.md`

---

# Repository Philosophy

QuantLab is not organized as a simple trading bot repository.

The repository is designed as:

* modular research infrastructure
* AI-assisted engineering ecosystem
* scalable experimentation platform
* long-term strategy laboratory

Repository organization prioritizes:

* modularity
* clear ownership boundaries
* deterministic workflows
* scalable orchestration
* architecture preservation
* low context fragmentation

The repository structure must support:

* many independent strategies
* multiple runtime environments
* reusable research tooling
* isolated execution systems
* future institutional-scale evolution

---

# High-Level Repository Structure

```text
quantlab/

├── agent/
├── docs/
├── backend/
├── frontend/
├── strategies/
├── datasets/
├── research/
├── execution/
├── infrastructure/
├── tools/
├── tests/
├── notebooks/
├── scripts/
├── .tmp/
├── docker/
├── configs/
├── .github/
├── pyproject.toml
├── README.md
└── .env
```

---

# Repository Root Responsibilities

---

## `agent/`

### Purpose

AI orchestration and governance layer.

### Responsibilities

* governance documents
* orchestration rules
* workflow discipline
* AI coordination
* handoff continuity
* prompt standards

### Example Files

```text
agent/
  HANDOFF.md
  TASKS.md
  ARCHITECTURE_GUARDRAILS.md
  WORKFLOW_GOVERNANCE.md
  WORKFLOW_AGENT.md
  PROMPT_RULES.md
  CLAUDE.md
  CODEX.md
```

### Important Rule

This folder defines repository governance.

It is NOT application runtime code.

---

## `docs/`

### Purpose

Durable architecture and system documentation.

### Responsibilities

* architecture documentation
* contracts
* system topology
* lifecycle documentation
* operational references

### Example Files

```text
docs/
  SYSTEM_OVERVIEW.md
  ARCHITECTURE.md
  REPOSITORY_STRUCTURE.md
  DATA_CONTRACT.md
  STRATEGY_CONTRACT.md
  EXECUTION_CONTRACT.md
  API_CONTRACT.md
```

### Important Rule

`docs/` contains durable system knowledge.

Avoid temporary implementation notes.

---

# Backend Structure

```text
backend/

├── api/
├── core/
├── services/
├── data/
├── data_providers/
├── strategy_registry/
├── strategy_runtime/
├── backtesting/
├── forward_testing/
├── paper_trading/
├── execution/
├── storage/
├── jobs/
├── events/
├── monitoring/
├── config/
└── shared/
```

---

## `backend/api/`

### Responsibilities

* REST API routes
* WebSocket endpoints
* request validation
* API orchestration
* authentication entrypoints

### Forbidden Responsibilities

* business logic
* strategy execution
* broker logic
* normalization logic

### Preferred Structure

```text
api/
  routes/
  websocket/
  dependencies/
  middleware/
  schemas/
```

---

## `backend/core/`

### Responsibilities

Global backend foundations.

### Examples

* application bootstrap
* logging setup
* exception handling
* runtime initialization
* security foundations

### Important Rule

Keep `core/` small and infrastructure-focused.

Avoid dumping unrelated logic here.

---

## `backend/services/`

### Responsibilities

Application service layer.

### Examples

* orchestration services
* lifecycle coordination
* runtime coordination
* domain workflows

### Important Rule

Business workflows belong here.

NOT inside routes.

---

## `backend/data/`

### Responsibilities

Normalized internal data layer.

### Examples

* schemas
* validators
* transformations
* normalization contracts
* feature pipelines

### Important Rule

Strategies consume ONLY normalized internal contracts from this layer.

---

## `backend/data_providers/`

### Responsibilities

Provider-specific ingestion adapters.

### Examples

* Binance adapter
* Yahoo Finance adapter
* CSV adapter
* Polygon adapter
* astronomical adapter

### Important Rule

Provider-specific schemas must NOT leak outside this layer.

---

## `backend/strategy_registry/`

### Responsibilities

Strategy discovery and metadata management.

### Examples

* lifecycle tracking
* strategy metadata
* versioning
* compatibility tracking

---

## `backend/strategy_runtime/`

### Responsibilities

Strategy execution orchestration.

### Examples

* runtime execution
* signal pipelines
* runtime scheduling
* mode handling

### Important Rule

Strategies remain isolated from execution systems.

---

## `backend/backtesting/`

### Responsibilities

Historical simulation systems.

### Examples

* replay engine
* metrics engine
* slippage models
* fee models
* deterministic replay

---

## `backend/forward_testing/`

### Responsibilities

Real-time validation runtime.

### Examples

* live signal monitoring
* runtime validation
* real-time evaluation

---

## `backend/paper_trading/`

### Responsibilities

Simulated execution systems.

### Examples

* simulated orders
* virtual portfolio tracking
* paper execution workflows

---

## `backend/execution/`

### Responsibilities

Execution orchestration.

### Examples

* risk validation
* portfolio constraints
* routing
* broker execution
* execution approval

### Important Rule

Strategies must NEVER directly place orders.

---

## `backend/storage/`

### Responsibilities

Storage abstraction layer.

### Examples

* PostgreSQL repositories
* DuckDB access
* Parquet handling
* storage adapters

---

## `backend/jobs/`

### Responsibilities

Background workers and scheduled tasks.

### Examples

* ingestion jobs
* feature generation
* dataset updates
* maintenance workflows

---

## `backend/events/`

### Responsibilities

Event-driven runtime infrastructure.

### Examples

* event buses
* runtime events
* signal propagation
* execution events

---

## `backend/monitoring/`

### Responsibilities

Observability and telemetry.

### Examples

* metrics
* tracing
* runtime diagnostics
* structured logging

---

## `backend/config/`

### Responsibilities

Backend configuration systems.

### Examples

* environment configs
* runtime configs
* typed settings

---

## `backend/shared/`

### Responsibilities

Small reusable utilities shared safely across modules.

### Important Rule

Do NOT turn this into a dumping ground.

Shared code must remain:

* generic
* minimal
* reusable
* architecture-safe

---

# Frontend Structure

```text
frontend/

├── app/
├── components/
├── features/
├── charts/
├── hooks/
├── stores/
├── services/
├── layouts/
├── styles/
├── types/
├── utils/
└── public/
```

---

## `frontend/app/`

### Responsibilities

Application routing and app initialization.

---

## `frontend/components/`

### Responsibilities

Reusable UI components.

### Examples

* buttons
* modals
* panels
* tables
* reusable visual blocks

---

## `frontend/features/`

### Responsibilities

Feature-scoped frontend modules.

### Examples

* backtest viewer
* strategy inspector
* research dashboard
* execution monitor

---

## `frontend/charts/`

### Responsibilities

Charting infrastructure.

### Examples

* chart engine
* overlays
* drawing systems
* synchronization
* viewport management

### Important Rule

Charting logic must remain isolated from strategy logic.

---

## `frontend/hooks/`

### Responsibilities

Reusable frontend hooks.

---

## `frontend/stores/`

### Responsibilities

Frontend state management.

### Preferred Stack

* Zustand

---

## `frontend/services/`

### Responsibilities

Frontend API communication layer.

### Important Rule

Do NOT place business logic here.

---

## `frontend/layouts/`

### Responsibilities

Page and workspace layouts.

---

## `frontend/styles/`

### Responsibilities

Styling systems.

### Preferred Stack

* TailwindCSS

---

## `frontend/types/`

### Responsibilities

Frontend type contracts.

---

## `frontend/utils/`

### Responsibilities

Small frontend-safe utilities.

---

# Strategy Structure

```text
strategies/

├── strategy_name/
│   ├── strategy.yaml
│   ├── metadata.py
│   ├── parameters.py
│   ├── features.py
│   ├── signals.py
│   ├── risk.py
│   ├── runtime.py
│   ├── validators.py
│   ├── tests/
│   └── research/
```

---

## Strategy Folder Responsibilities

### `strategy.yaml`

Strategy metadata and configuration.

### `features.py`

Feature generation.

### `signals.py`

Signal generation logic.

### `risk.py`

Risk rules and constraints.

### `runtime.py`

Runtime integration hooks.

### `validators.py`

Strategy validation logic.

### `research/`

Experimental research artifacts specific to the strategy.

---

# Datasets Structure

```text
datasets/

├── raw/
├── normalized/
├── processed/
├── features/
├── alternative/
├── astronomical/
├── metadata/
└── cache/
```

---

## Dataset Rules

### `raw/`

Immutable source datasets.

### `normalized/`

Validated normalized contracts.

### `processed/`

Derived analytical datasets.

### `features/`

Generated feature datasets.

### Important Rule

Raw provider data must never directly reach strategies.

---

# Research Structure

```text
research/

├── experiments/
├── hypotheses/
├── feature_exploration/
├── cycle_research/
├── planetary/
├── validation/
└── artifacts/
```

---

## Purpose

Research-first experimental environment.

### Important Rule

Research systems remain isolated from production execution systems.

---

# Execution Structure

```text
execution/

├── brokers/
├── routing/
├── risk/
├── portfolio/
├── compliance/
├── approvals/
└── audit/
```

---

## Purpose

Execution-specific infrastructure.

### Important Rule

Execution systems remain isolated from strategies.

---

# Infrastructure Structure

```text
infrastructure/

├── docker/
├── monitoring/
├── deployment/
├── observability/
├── networking/
└── provisioning/
```

---

# Tools Structure

```text
tools/

├── ingestion/
├── maintenance/
├── migration/
├── repair/
├── diagnostics/
└── generators/
```

---

# Tests Structure

```text
tests/

├── unit/
├── integration/
├── runtime/
├── backtesting/
├── execution/
├── frontend/
└── fixtures/
```

---

# Notebook Structure

```text
notebooks/

├── experimental/
├── validation/
├── feature_research/
└── archived/
```

---

## Important Rule

Notebook logic must NOT become production code directly.

Production logic must be refactored into proper modules.

---

# Scripts Structure

```text
scripts/

├── setup/
├── bootstrap/
├── local/
├── maintenance/
└── utilities/
```

---

# Temporary Files Structure

```text
.tmp/
```

---

## Purpose

Temporary outputs and intermediates.

### Important Rule

`.tmp/` must never become source-of-truth storage.

---

# Docker Structure

```text
docker/

├── backend/
├── frontend/
├── workers/
└── infrastructure/
```

---

# Config Structure

```text
configs/

├── local/
├── development/
├── staging/
├── production/
└── testing/
```

---

# GitHub Structure

```text
.github/

├── workflows/
├── ISSUE_TEMPLATE/
└── PULL_REQUEST_TEMPLATE/
```

---

# Repository-Wide Rules

---

## 1. Strategy Isolation Rule

Strategies must remain isolated from:

* brokers
* frontend
* provider schemas
* database implementations

---

## 2. Execution Isolation Rule

Execution systems must remain isolated from strategy logic.

---

## 3. Frontend Boundary Rule

Frontend must not become the source of truth for:

* strategy calculations
* execution logic
* normalization logic

---

## 4. Data Normalization Rule

All datasets must pass through normalization before strategy usage.

---

## 5. Experimental Isolation Rule

Research and experimental systems must remain isolated from production runtime systems.

---

# Forbidden Repository Patterns

The following patterns are prohibited:

* monolithic utility folders
* oversized shared modules
* direct strategy-to-broker coupling
* provider-specific schemas outside adapters
* frontend business logic
* uncontrolled notebook-to-production copying
* hardcoded runtime assumptions
* direct live trading shortcuts

---

# Repository Evolution Philosophy

The repository structure is expected to evolve incrementally as QuantLab matures.

The repository should optimize for:

* modular growth
* architecture preservation
* AI-assisted engineering
* scalable experimentation
* long-term maintainability

Avoid premature complexity and speculative infrastructure.

Repository organization should remain:

* explicit
* navigable
* modular
* architecture-aligned
* operationally scalable

---

# Final Repository Principle

The physical repository structure must reflect architectural boundaries.

Folder organization is not merely cosmetic.

Repository structure is part of the architecture itself.

All repository evolution must preserve:

* modularity
* portability
* execution isolation
* reproducibility
* maintainability
* long-term scalability

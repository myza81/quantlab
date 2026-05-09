# QuantLab

A modular, research-first strategy development ecosystem designed to support the full lifecycle of strategy discovery, validation, simulation, and future live deployment.

---

## Purpose

QuantLab is not a trading bot. It is a long-term strategy research laboratory built to support:

- strategy research and hypothesis testing
- feature engineering and cycle analysis
- historical backtesting
- forward testing and paper trading
- future controlled live trading

The platform is intentionally market-agnostic and supports unconventional research methods including planetary, astronomical, and cycle-based analysis.

---

## Architecture Direction

QuantLab follows a strict modular architecture with enforced separation of concerns:

```
Data Provider → Normalization → Data Layer → Strategy Runtime → Execution Layer
```

Core principles:

- **Strategy portability** — strategies run identically across research, backtest, paper, and live modes
- **Execution isolation** — strategies produce signals; execution systems decide what to do with them
- **Data abstraction** — strategies never know the data source or provider
- **Research-first** — experimental logic stays isolated until formally validated
- **Incremental evolution** — no premature infrastructure or speculative complexity

Full architecture documentation: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## Repository Structure

```
quantlab/
├── agent/          # AI governance, orchestration rules, workflow discipline, handoff continuity
├── directives/     # Orchestration prompt templates for structured AI task execution
├── docs/           # Durable architecture documentation and system contracts
├── backend/        # FastAPI application — api, services, data, strategy runtime, execution (planned)
├── frontend/       # React + TypeScript research terminal (planned)
├── strategies/     # Individual portable strategy modules (planned)
├── datasets/       # Raw, normalized, and processed market and research data (planned)
├── research/       # Experimental research, hypotheses, and exploratory notebooks (planned)
├── execution/      # Broker adapters, routing, risk, and compliance (planned)
├── tests/          # Unit, integration, and runtime tests (planned)
├── scripts/        # Setup, bootstrap, and maintenance utilities (planned)
├── configs/        # Environment-aware configuration files (planned)
└── docker/         # Container definitions per service (planned)
```

Detailed structure specification: [`docs/REPOSITORY_STRUCTURE.md`](docs/REPOSITORY_STRUCTURE.md)

---

## Current Development Stage

**Phase 1 — Foundation & Governance**

The repository is currently establishing architectural guardrails, AI orchestration discipline, and modular system blueprints before core implementation begins.

What exists now:
- governance and workflow documents (`agent/`)
- system architecture contracts (`docs/`)
- orchestration directive templates (`directives/`)

What is not yet started:
- backend implementation
- frontend implementation
- strategy modules
- data pipelines
- execution systems

See [`agent/TASKS.md`](agent/TASKS.md) for active priorities and sequencing.

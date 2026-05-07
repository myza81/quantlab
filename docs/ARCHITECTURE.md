# ARCHITECTURE.md

## Purpose

This document defines the technical architecture blueprint for QuantLab.

The purpose of this document is to define:

* architectural layers
* system boundaries
* technology stack decisions
* runtime responsibilities
* data flow direction
* storage responsibilities
* execution isolation
* infrastructure philosophy
* scaling direction
* architectural constraints

This document acts as the primary technical implementation reference for:

* orchestration systems
* implementation agents
* future contributors

This document intentionally focuses on architecture and system topology.

Detailed implementation contracts belong in dedicated contract documents.

---

# Architectural Philosophy

QuantLab is designed as a modular strategy research and execution ecosystem.

The architecture prioritizes:

* strategy portability
* deterministic workflows
* execution isolation
* modular boundaries
* reproducibility
* auditability
* research flexibility
* incremental evolution
* long-term maintainability

The architecture must support the full strategy lifecycle:

```text
research
→ validation
→ backtesting
→ forward testing
→ paper trading
→ future live trading
```

without rewriting strategy logic.

The platform is intentionally research-first.

Execution systems are isolated from research systems.

---

# High-Level System Topology

```text
                    ┌────────────────────┐
                    │   Frontend UI      │
                    │ Research Terminal  │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │    Backend API     │
                    │  Application Layer │
                    └─────────┬──────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼

┌──────────────┐    ┌────────────────┐    ┌────────────────┐
│ Data Layer   │    │ Strategy Layer │    │ Execution Layer│
│ Normalization│    │ Runtime Engine │    │ Routing & Risk │
└──────┬───────┘    └────────┬───────┘    └────────┬───────┘
       │                     │                     │
       ▼                     ▼                     ▼

┌──────────────┐    ┌────────────────┐    ┌────────────────┐
│ DuckDB       │    │ Backtesting    │    │ Broker Adapters│
│ Parquet      │    │ Forward Testing│    │ Paper Trading  │
│ PostgreSQL   │    │ Paper Runtime  │    │ Future Live    │
└──────────────┘    └────────────────┘    └────────────────┘
```

---

# Architectural Layers

QuantLab is organized into isolated architectural layers.

Each layer has a clear responsibility.

Responsibilities must not leak across layers.

---

## 1. Frontend Layer

### Responsibilities

* chart rendering
* visualization
* drawing tools
* annotation systems
* strategy inspection
* dashboards
* interaction workflows
* UI state management

### Forbidden Responsibilities

* strategy calculations
* execution logic
* backtesting calculations
* market normalization
* compliance logic
* broker logic

### Preferred Stack

* React
* Next.js
* TypeScript
* Zustand
* TailwindCSS
* TradingView Lightweight Charts

---

## 2. Backend API Layer

### Responsibilities

* API routing
* authentication
* orchestration entry points
* request validation
* runtime coordination
* service exposure

### Forbidden Responsibilities

* direct strategy calculations inside routes
* direct broker logic
* direct provider logic
* heavy business logic inside controllers/routes

### Preferred Stack

* FastAPI
* Pydantic
* Python

### Preferred Flow

```text
API Route
→ Application Service
→ Domain Service / Runtime
→ Repository / Adapter
```

---

## 3. Data Layer

### Responsibilities

* ingestion
* normalization
* schema validation
* transformation
* feature preparation
* dataset management
* historical storage access

### Core Principle

All datasets must be normalized before entering strategy systems.

Strategies must never consume provider-native schemas.

### Supported Data Sources

* exchange APIs
* brokers
* CSV
* Excel
* WebSocket streams
* alternative datasets
* astronomical datasets
* sentiment datasets
* manually uploaded datasets

### Preferred Stack

* Polars
* PyArrow
* Pandas (limited use)
* DuckDB
* Parquet

---

## 4. Strategy Layer

### Responsibilities

* feature generation
* signal generation
* risk logic
* trade setup generation
* configuration validation

### Core Principle

Strategies are pure logic modules.

Strategies must remain portable across all runtime modes.

### Strategies Must NOT Directly Access

* brokers
* APIs
* databases
* frontend systems
* file systems
* execution engines

### Required Strategy Interfaces

```python
build_features()
generate_signals()
apply_risk_rules()
validate_config()
```

---

## 5. Runtime Layer

### Responsibilities

* runtime orchestration
* mode management
* scheduling
* event coordination
* signal pipelines
* runtime state handling

### Runtime Modes

* research
* backtesting
* forward testing
* paper trading
* future live trading

### Core Principle

Runtime behavior changes by environment.

Strategy logic does not.

---

## 6. Backtesting Layer

### Responsibilities

* historical replay
* deterministic simulation
* slippage modeling
* fee modeling
* execution assumptions
* metrics generation
* reproducibility

### Core Principle

Backtesting must be deterministic and reproducible.

### Required Metadata

* dataset version
* parameter version
* timeframe
* strategy version
* execution assumptions
* timestamp
* run metadata

---

## 7. Forward Testing Layer

### Responsibilities

* live market observation
* runtime validation
* signal monitoring
* simulated execution
* strategy evaluation

### Core Principle

Forward testing uses the same strategy logic as backtesting.

Only runtime environment differs.

---

## 8. Execution Layer

### Responsibilities

* order interpretation
* portfolio constraints
* risk enforcement
* execution approval
* routing
* broker adapter orchestration
* execution logging

### Core Principle

Strategies generate signals only.

Execution systems decide whether signals become executable orders.

### Execution Isolation Rule

Strategies must NEVER directly place orders.

---

## 9. Broker Adapter Layer

### Responsibilities

* provider translation
* broker API isolation
* order mapping
* execution translation
* broker normalization

### Supported Future Providers

* Interactive Brokers
* Binance
* Alpaca
* MetaTrader
* custom providers

### Core Principle

Broker-specific logic must never leak into strategies.

---

## 10. Infrastructure Layer

### Responsibilities

* workers
* scheduling
* observability
* queues
* caching
* deployment systems
* monitoring
* secrets handling

### Preferred Stack

* Redis
* Celery / Dramatiq
* Docker
* Prometheus
* Grafana

---

# Backend Architecture

## Preferred Backend Stack

### Core Backend

* Python
* FastAPI
* Pydantic

### Async & Runtime

* asyncio
* WebSockets

### Task Processing

* Celery or Dramatiq
* Redis

### Validation

* Pydantic schemas
* typed contracts

---

# Frontend Architecture

## Preferred Frontend Stack

### Core Frontend

* React
* Next.js
* TypeScript

### State Management

* Zustand

### Styling

* TailwindCSS

### Charting

* TradingView Lightweight Charts

### Visualization Philosophy

Frontend acts as:

* research terminal
* visualization environment
* interaction layer

NOT as business logic authority.

---

# Data Architecture

## Storage Responsibilities

### PostgreSQL

Used for:

* users
* metadata
* strategy registry
* configurations
* audit logs
* experiment metadata
* runtime metadata
* execution records

### DuckDB + Parquet

Used for:

* OHLCV datasets
* feature datasets
* large time-series datasets
* analytical workloads
* backtesting datasets

### Core Principle

Large analytical datasets should not primarily live inside PostgreSQL.

---

# Data Flow Architecture

All datasets follow:

```text
Provider
→ Ingestion Adapter
→ Normalization
→ Validation
→ Storage
→ Feature Engineering
→ Strategy Runtime
```

No provider schema should bypass normalization.

---

# Event & Streaming Architecture

## Responsibilities

* live market streaming
* runtime event propagation
* signal events
* execution events
* monitoring events

## Preferred Stack

* WebSockets
* Redis Streams
* event-driven services

## Future Expansion

Kafka or NATS may be introduced later if system scale requires distributed streaming infrastructure.

These are NOT current priorities.

---

# Research Architecture

## Responsibilities

* experimental workflows
* feature exploration
* cycle analysis
* planetary analysis
* hypothesis testing
* signal discovery
* research artifact management

## Core Principle

Experimental systems must remain isolated from production execution systems.

Research code must graduate through lifecycle validation before production use.

---

# Strategy Registry Architecture

## Responsibilities

* strategy discovery
* metadata management
* lifecycle tracking
* versioning
* runtime compatibility
* dependency tracking

## Strategy Lifecycle

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

---

# AI Orchestration Architecture

QuantLab uses a multi-agent orchestration model.

---

## Human Operator

Responsible for:

* research direction
* business decisions
* approval authority
* strategic intent

---

## ChatGPT

Responsible for:

* architecture governance
* orchestration
* prompt engineering
* scope decomposition
* system planning
* architecture review

---

## Claude

Responsible for:

* major implementation
* structured development
* architecture-aware coding

---

## Codex

Responsible for:

* focused fixes
* debugging
* testing
* local optimization
* patch-level improvements

---

# Configuration Architecture

## Core Principle

Configuration must remain explicit and environment-aware.

### Never Hardcode

* API keys
* broker credentials
* file paths
* symbols
* strategy parameters
* execution flags
* URLs

### Preferred Systems

* `.env`
* typed configuration modules
* versioned runtime configuration

---

# Observability & Monitoring Architecture

## Required Capabilities

* structured logging
* metrics
* tracing
* runtime diagnostics
* audit visibility
* execution visibility

## Preferred Stack

* Prometheus
* Grafana
* structured Python logging

---

# Security & Secrets Architecture

## Responsibilities

* secrets management
* API protection
* execution safety
* environment isolation

## Core Principle

No secrets may be hardcoded inside repositories.

Live execution systems must require explicit enablement and approval.

---

# Deployment Philosophy

QuantLab currently prioritizes:

* local development
* reproducible environments
* deterministic workflows
* modular infrastructure

## Preferred Stack

* Docker
* docker-compose

## Deferred Infrastructure

The following are intentionally deferred:

* Kubernetes
* distributed orchestration
* large-scale cloud automation
* microservices decomposition

---

# Scaling Philosophy

QuantLab should scale incrementally.

Current priorities:

* modularity
* correctness
* reproducibility
* architecture quality

NOT premature distributed complexity.

Scaling should occur only when justified by:

* dataset scale
* runtime complexity
* execution volume
* multi-user requirements

---

# Dependency Philosophy

Dependencies must be added deliberately.

Before adding a dependency, validate:

* maintenance quality
* architectural necessity
* operational complexity
* licensing
* long-term support

Avoid dependency bloat.

Prefer explicit and understandable systems.

---

# Architectural Boundaries

The following boundaries are mandatory:

```text
Frontend ≠ Strategy Logic
Strategy Logic ≠ Broker Logic
Broker Logic ≠ Provider Schemas
Runtime ≠ Frontend
Execution ≠ Strategy
Research ≠ Production Execution
```

Violation of these boundaries is considered architectural drift.

---

# Forbidden Architectural Patterns

The following are prohibited:

* broker logic inside strategies
* direct provider schemas inside strategies
* frontend-generated official signals
* frontend-generated official backtests
* strategy direct database access
* strategy direct API access
* monolithic service layers
* uncontrolled live execution
* oversized shared utility modules
* hardcoded environment assumptions

---

# Future Evolution Direction

QuantLab is expected to evolve into:

* institutional-grade research infrastructure
* scalable strategy ecosystem
* advanced runtime orchestration platform
* portfolio-level execution environment
* multi-asset research platform
* AI-assisted research environment

Future expansion may include:

* distributed workloads
* advanced orchestration
* multi-user systems
* advanced telemetry
* execution clusters
* cloud-native infrastructure

These capabilities should emerge incrementally through controlled architecture evolution.

---

# Final Architectural Principle

QuantLab is not a simple trading bot.

It is a modular strategy research and execution ecosystem designed for long-term extensibility, controlled evolution, and institutional-grade research discipline.

All implementation decisions must preserve:

* modularity
* reproducibility
* portability
* auditability
* execution safety
* architectural clarity

# API_CONTRACT.md

## Purpose

This document defines the canonical API contracts for QuantLab.

The purpose of this document is to establish:

* backend API design principles
* frontend/backend boundary rules
* REST API conventions
* WebSocket conventions
* request and response standards
* error handling standards
* authentication and authorization boundaries
* pagination conventions
* streaming payload rules
* API versioning principles
* execution safety boundaries

This document ensures that APIs remain stable, predictable, modular, and safe as QuantLab evolves.

---

# Core API Philosophy

QuantLab APIs act as controlled application interfaces.

APIs expose system capabilities without leaking internal implementation details.

API routes should remain thin.

Business logic must live in:

```text
application services
domain services
runtime services
repositories
adapters
```

NOT directly inside API route handlers.

---

# API Boundary Principle

Frontend systems communicate with QuantLab only through approved APIs.

Frontend must not directly access:

* databases
* strategy modules
* execution engines
* broker adapters
* provider adapters
* internal storage layouts

---

# Preferred API Flow

```text
Frontend Request
    ↓
API Route
    ↓
Request Schema Validation
    ↓
Application Service
    ↓
Domain / Runtime / Repository / Adapter
    ↓
Response Schema Serialization
    ↓
Frontend Response
```

---

# API Layer Responsibilities

API layer may handle:

* request validation
* response serialization
* authentication checks
* authorization checks
* routing
* dependency injection
* orchestration entry points

API layer must not handle:

* strategy calculations
* backtest simulation logic
* broker execution logic
* data normalization logic
* official signal generation
* portfolio risk decisions

---

# Preferred Backend API Stack

QuantLab backend API should use:

* FastAPI
* Pydantic
* Python
* OpenAPI-compatible schemas
* WebSocket endpoints for real-time streams

---

# API Versioning Contract

All public API routes should be versioned.

Preferred format:

```text
/api/v1/...
```

Future breaking changes must use a new version.

Do not silently break existing frontend consumers.

---

# REST API Conventions

REST APIs should follow resource-oriented conventions where practical.

---

## Preferred Route Style

```text
GET    /api/v1/strategies
GET    /api/v1/strategies/{strategy_id}
POST   /api/v1/backtests
GET    /api/v1/backtests/{run_id}
POST   /api/v1/research/experiments
GET    /api/v1/datasets
GET    /api/v1/executions/{execution_id}
```

---

# Request Contract

All incoming requests must be validated through typed schemas.

---

## Request Requirements

Requests should define:

* required fields
* optional fields
* field types
* validation constraints
* default behavior

---

## Forbidden Request Behavior

The following are prohibited:

* unvalidated request bodies
* implicit business defaults hidden inside routes
* raw provider payloads accepted directly into runtime systems
* direct broker-native payload execution

---

# Response Contract

All responses should follow stable response structures.

---

## Standard Success Response

```json
{
  "success": true,
  "data": {},
  "metadata": {}
}
```

---

## Standard Error Response

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {}
  },
  "metadata": {}
}
```

---

# Error Handling Contract

API errors must be predictable and structured.

---

## Error Categories

| Category            | Description                     |
| ------------------- | ------------------------------- |
| VALIDATION_ERROR    | invalid request payload         |
| NOT_FOUND           | resource not found              |
| CONFLICT            | conflicting state               |
| UNAUTHORIZED        | authentication required         |
| FORBIDDEN           | permission denied               |
| RUNTIME_ERROR       | runtime failure                 |
| EXECUTION_REJECTED  | execution blocked by validation |
| COMPLIANCE_REJECTED | blocked by compliance policy    |
| RISK_REJECTED       | blocked by risk policy          |

---

# Pagination Contract

List endpoints must support pagination where result sets may grow.

---

## Preferred Pagination Fields

```text
limit
cursor
next_cursor
has_more
```

---

## Example Response Metadata

```json
{
  "success": true,
  "data": [],
  "metadata": {
    "limit": 100,
    "next_cursor": "abc123",
    "has_more": true
  }
}
```

---

# Filtering and Sorting Contract

List endpoints should support explicit filtering and sorting.

---

## Common Query Parameters

```text
symbol
asset_class
timeframe
status
start_time
end_time
sort_by
sort_order
```

---

# Time Handling Contract

All API timestamps must use:

```text
UTC
ISO-8601 format
timezone-aware values
```

APIs must not expose naive datetimes.

---

# Data API Contract

Data APIs expose normalized data only.

---

## Data API Must NOT Expose

* provider-native schemas
* raw broker payloads
* unstable experimental data by default
* internal storage paths

---

## Example Routes

```text
GET /api/v1/datasets
GET /api/v1/datasets/{dataset_id}
GET /api/v1/market-data/ohlcv
GET /api/v1/features
```

---

# Strategy API Contract

Strategy APIs expose strategy registry and strategy runtime operations.

---

## Example Routes

```text
GET  /api/v1/strategies
GET  /api/v1/strategies/{strategy_id}
POST /api/v1/strategies/{strategy_id}/validate
GET  /api/v1/strategies/{strategy_id}/runs
```

---

## Important Rule

Strategy APIs must not allow frontend systems to execute strategy logic directly without runtime service coordination.

---

# Research API Contract

Research APIs expose controlled research operations.

---

## Example Routes

```text
GET  /api/v1/research/hypotheses
POST /api/v1/research/hypotheses
GET  /api/v1/research/experiments
POST /api/v1/research/experiments
GET  /api/v1/research/artifacts
```

---

# Backtesting API Contract

Backtesting APIs must create deterministic backtest jobs.

---

## Example Routes

```text
POST /api/v1/backtests
GET  /api/v1/backtests/{run_id}
GET  /api/v1/backtests/{run_id}/metrics
GET  /api/v1/backtests/{run_id}/trades
```

---

## Required Backtest Request Fields

| Field                 | Description                |
| --------------------- | -------------------------- |
| strategy_id           | strategy identifier        |
| strategy_version      | strategy version           |
| dataset_id            | dataset identifier         |
| timeframe             | timeframe                  |
| parameters            | strategy parameters        |
| execution_assumptions | slippage, fees, fill rules |

---

# Forward Testing API Contract

Forward testing APIs expose runtime validation workflows.

---

## Example Routes

```text
POST /api/v1/forward-tests
GET  /api/v1/forward-tests/{session_id}
GET  /api/v1/forward-tests/{session_id}/signals
```

---

# Paper Trading API Contract

Paper trading APIs expose simulated execution workflows.

---

## Example Routes

```text
POST /api/v1/paper-trading/sessions
GET  /api/v1/paper-trading/sessions/{session_id}
GET  /api/v1/paper-trading/orders
GET  /api/v1/paper-trading/portfolio
```

---

# Execution API Contract

Execution APIs must be strictly controlled.

Execution APIs must never bypass:

* risk validation
* compliance validation
* approval checks
* audit logging

---

## Example Routes

```text
GET  /api/v1/executions
GET  /api/v1/executions/{execution_id}
POST /api/v1/executions/{execution_id}/approve
POST /api/v1/executions/{execution_id}/cancel
```

---

## Important Rule

Live execution endpoints must remain disabled unless explicitly enabled by configuration and approval gates.

---

# WebSocket Contract

WebSockets are used for real-time runtime updates.

---

## WebSocket Responsibilities

* market data updates
* strategy runtime events
* signal updates
* backtest progress
* forward test updates
* paper trading updates
* execution state changes

---

## Example WebSocket Channels

```text
/ws/v1/market-data
/ws/v1/runtime
/ws/v1/backtests/{run_id}
/ws/v1/forward-tests/{session_id}
/ws/v1/paper-trading/{session_id}
/ws/v1/executions
```

---

# WebSocket Message Contract

All WebSocket messages should follow a stable structure.

---

## Standard WebSocket Message

```json
{
  "type": "event.type",
  "timestamp": "2026-01-01T00:00:00Z",
  "payload": {},
  "metadata": {}
}
```

---

# Event Type Naming Contract

Preferred event naming format:

```text
domain.event_name
```

Examples:

```text
market_data.ohlcv_update
strategy.signal_generated
backtest.progress_updated
execution.state_changed
paper_trading.order_filled
```

---

# Authentication Contract

Authentication is required for protected API operations.

---

## Public Operations

May include:

* health checks
* basic system status

---

## Protected Operations

Must include:

* strategy modification
* backtest creation
* paper trading sessions
* execution approvals
* live trading controls
* configuration updates

---

# Authorization Contract

Authorization must control sensitive operations.

---

## Sensitive Operations

* live execution enablement
* execution approval
* broker configuration
* compliance configuration
* risk configuration
* strategy promotion

---

# Live Trading API Guardrails

Live trading APIs are future-facing and must remain disabled by default.

Live trading APIs must require:

* explicit configuration enablement
* authenticated user
* authorization
* approval workflow
* risk validation
* compliance validation
* audit logging

---

# Health Check Contract

Health endpoints should expose system status without leaking sensitive information.

---

## Example Routes

```text
GET /api/v1/health
GET /api/v1/health/dependencies
```

---

# API Security Rules

APIs must never expose:

* secrets
* broker credentials
* environment variables
* internal file paths
* raw stack traces
* unauthorized execution controls

---

# API Observability Contract

APIs should support:

* request logging
* latency metrics
* error metrics
* structured logs
* trace identifiers

---

# Traceability Contract

Important API actions should preserve:

* request ID
* user ID where applicable
* timestamp
* affected resource
* operation result
* error reason if failed

---

# Idempotency Contract

Critical mutating operations should support idempotency where appropriate.

---

## Applies To

* backtest creation
* execution approval
* order cancellation
* paper trading order simulation
* live trading order requests

---

# File Upload Contract

File uploads must be controlled and validated.

---

## Applies To

* CSV datasets
* Excel datasets
* research artifacts
* strategy configuration files

---

## Required Validation

* file type
* size limits
* schema compatibility
* malware/security scanning where applicable later

---

# Frontend/API Boundary Rules

Frontend systems may:

* call APIs
* subscribe to WebSockets
* display data
* submit user instructions
* visualize results

Frontend systems must not:

* bypass APIs
* connect directly to databases
* call broker APIs
* generate official strategy signals
* calculate official backtest results
* enforce final compliance rules

---

# API Documentation Contract

APIs should remain OpenAPI-documentable.

Every stable endpoint should define:

* request schema
* response schema
* error schema
* authentication requirements
* authorization requirements

---

# Forbidden API Patterns

The following patterns are prohibited:

* business logic inside route handlers
* broker execution inside route handlers
* frontend direct database access
* provider-native payload leakage
* unversioned breaking changes
* raw exceptions returned to clients
* hidden live trading endpoints
* unaudited execution mutations
* unvalidated request bodies
* exposing secrets through API responses

---

# Future API Expansion Direction

Future API systems may include:

* GraphQL
* advanced streaming subscriptions
* multi-user authorization
* collaborative research APIs
* strategy marketplace APIs
* broker management APIs
* portfolio-level APIs

These must only be introduced when justified by system maturity.

---

# Final API Principle

APIs are controlled boundaries between user interaction and system capability.

All API systems must preserve:

* validation
* modularity
* safety
* traceability
* frontend/backend separation
* execution protection
* architecture integrity

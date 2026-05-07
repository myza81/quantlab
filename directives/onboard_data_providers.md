# ONBOARD_DATA_PROVIDER.md

## Purpose

This directive defines the workflow, architecture rules, normalization standards, adapter requirements, and validation procedures for onboarding new market data providers and external data sources into QuantLab.

Provider onboarding exists to ensure:

* provider isolation
* normalized data contracts
* reproducibility
* modular ingestion pipelines
* architecture safety
* runtime portability

This directive applies to:

* market data providers
* broker market feeds
* CSV ingestion
* Excel ingestion
* WebSocket feeds
* macroeconomic APIs
* sentiment feeds
* astronomical engines
* planetary datasets
* custom external datasets

---

# Core Philosophy

Providers are external dependencies.

Strategies must NEVER depend directly on provider implementations.

Provider-specific logic must remain isolated inside:

```text
provider adapters
```

The system architecture must preserve:

```text
provider
→ adapter
→ normalization
→ validation
→ storage/runtime
→ strategy usage
```

NOT:

```text
provider
→ strategy
```

---

# Objective

When onboarding a provider, the implementation agent must:

1. isolate provider-specific logic
2. preserve normalized schemas
3. validate timestamps
4. maintain reproducibility
5. preserve runtime portability
6. support observability
7. prevent provider leakage into strategies

---

# Supported Provider Categories

Providers may include:

* exchanges
* brokers
* WebSocket feeds
* REST APIs
* CSV datasets
* Excel datasets
* macroeconomic APIs
* sentiment feeds
* astronomical engines
* planetary calculation engines
* custom research providers

All provider categories must follow architecture discipline.

---

# Required Onboarding Workflow

Minimum required workflow:

```text
provider analysis
→ adapter implementation
→ normalization mapping
→ schema validation
→ timestamp validation
→ ingestion validation
→ runtime validation
→ observability validation
→ approval or rejection
```

---

# Provider Isolation Rules

Provider-specific logic must remain isolated inside:

```text
data_providers/
```

or equivalent adapter layers.

Strategies must NEVER access:

* provider APIs directly
* raw payloads
* provider-specific schemas
* transport-specific structures

VALID:

```text
provider
→ adapter
→ normalized schema
→ strategy
```

INVALID:

```text
strategy
→ provider API
```

---

# Adapter Rules

Every provider must expose stable adapter interfaces.

Adapters should handle:

* authentication
* retries
* reconnect logic
* schema mapping
* rate limiting
* timestamp normalization
* error handling
* transport abstraction

Adapters must remain isolated from strategy logic.

---

# Normalization Rules

All provider data must be normalized before entering runtime systems.

Normalized schemas should preserve:

```text
symbol
asset_class
exchange
timeframe
timestamp
open
high
low
close
volume
source
```

Additional provider-specific fields may be stored as optional metadata.

Provider-specific fields must NOT leak into strategies.

---

# Timestamp Rules

Providers must validate:

* timezone consistency
* timestamp ordering
* session alignment
* aggregation consistency
* duplicate timestamps
* delayed timestamps

Timestamp handling must remain deterministic.

---

# WebSocket Provider Rules

Streaming providers must support:

* reconnect handling
* heartbeat handling
* subscription recovery
* sequence validation
* partial stream recovery
* runtime diagnostics

Avoid hidden reconnect behavior.

---

# Polling Provider Rules

Polling providers should support:

* deterministic scheduling
* retry handling
* rate limiting
* timeout handling
* pagination handling

Polling systems must remain observable.

---

# Rate Limit Rules

Provider integrations must respect:

* API limits
* subscription limits
* concurrency limits
* reconnect limits

Rate-limit handling must remain explicit.

Avoid hidden throttling behavior.

---

# Authentication Rules

Credentials must NEVER be hardcoded.

Use:

* environment variables
* approved configuration systems
* secret management workflows

Provider credentials must remain isolated from strategy logic.

---

# CSV and File Provider Rules

CSV and file-based ingestion must validate:

* schema consistency
* delimiter consistency
* timestamp integrity
* encoding consistency
* missing data
* duplicate rows

File ingestion must remain reproducible.

---

# Alternative Dataset Rules

Alternative providers are fully supported.

Examples:

* planetary APIs
* astronomical engines
* macroeconomic feeds
* sentiment streams
* symbolic datasets

Alternative providers must still preserve:

* normalization
* timestamp integrity
* reproducibility
* traceability

---

# Runtime Compatibility Rules

Provider outputs must remain compatible across:

* research
* backtesting
* forward testing
* paper trading
* live runtime systems

Runtime portability is mandatory.

---

# Data Validation Rules

Provider onboarding must validate:

* schema correctness
* timestamp correctness
* completeness
* duplicate handling
* missing-data handling
* aggregation correctness
* normalization consistency

Invalid data must not silently enter runtime systems.

---

# Observability Rules

Provider systems should expose:

* structured logging
* reconnect diagnostics
* ingestion metrics
* latency observations
* failure metrics
* health monitoring

Provider systems must remain debuggable.

---

# Failure Handling Rules

Provider failures must produce:

* explicit errors
* diagnostics
* retry visibility
* reconnect visibility
* traceable logs

Avoid silent data corruption.

---

# Storage Rules

Provider pipelines may persist data into:

* DuckDB
* Parquet
* PostgreSQL metadata
* streaming caches

Storage decisions must preserve:

* reproducibility
* deterministic retrieval
* traceability

---

# Dataset Versioning Rules

Provider ingestion should preserve:

* provider name
* provider version
* ingestion timestamp
* normalization version
* preprocessing assumptions
* dataset version

Traceability is mandatory.

---

# Runtime Safety Rules

Provider onboarding must avoid:

* uncontrolled live execution coupling
* strategy/provider coupling
* runtime mutation side effects
* hidden provider assumptions

Providers are infrastructure layers — not strategy layers.

---

# Approval Rules

A provider may be approved ONLY if:

- [ ] provider isolation is preserved
- [ ] normalized schemas exist
- [ ] timestamp validation passes
- [ ] retry/reconnect handling exists
- [ ] observability exists
- [ ] reproducibility is preserved
- [ ] no provider leakage exists
- [ ] runtime compatibility is preserved

---

# Forbidden Patterns

The following are prohibited:

* strategy-to-provider direct coupling
* raw provider schema leakage
* hardcoded credentials
* hidden reconnect logic
* undocumented transformations
* runtime-specific provider hacks
* provider-specific strategy logic
* uncontrolled polling loops
* silent ingestion failures

---

# Deliverables

Minimum expected deliverables:

* provider adapter
* normalization mapping
* schema validation report
* timestamp validation report
* runtime validation summary
* observability summary
* approval/rejection recommendation

---

# Validation Checklist

Before approving a provider, confirm:

- [ ] provider isolation exists
- [ ] normalized schemas are used
- [ ] timestamp integrity is preserved
- [ ] retry/reconnect handling exists
- [ ] observability exists
- [ ] reproducibility is preserved
- [ ] credentials are isolated
- [ ] runtime portability exists
- [ ] no provider leakage exists
- [ ] no architecture guardrails were violated

---

# Final Instruction

Provider onboarding inside QuantLab exists to preserve clean architecture and normalized data integrity.

Providers are NOT:

* strategy dependencies
* runtime shortcuts
* direct execution systems
* architecture exceptions

The objective is to create deterministic, observable, modular, and reproducible provider integrations capable of supporting institutional-grade research and execution workflows while preserving:

* modularity
* portability
* reproducibility
* runtime safety
* architecture integrity
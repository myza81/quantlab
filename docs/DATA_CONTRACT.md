# DATA_CONTRACT.md

## Purpose

This document defines the canonical data contracts for QuantLab.

The purpose of this document is to establish:

* normalized internal schemas
* dataset structure standards
* ingestion rules
* validation requirements
* storage contracts
* timestamp conventions
* feature dataset contracts
* live vs historical consistency rules
* provider abstraction rules

This document is one of the most critical architectural contracts in QuantLab.

All strategy systems, runtime systems, backtesting systems, execution systems, APIs, and frontend systems depend on consistent data behavior.

---

# Core Data Philosophy

QuantLab treats data normalization as a mandatory architectural boundary.

Strategies must never directly consume provider-native schemas.

All external data must pass through:

```text
Provider
→ Adapter
→ Normalization
→ Validation
→ Storage
→ Feature Generation
→ Runtime Usage
```

No provider-specific schema may bypass normalization.

---

# Canonical Data Categories

QuantLab organizes datasets into multiple canonical categories.

---

## 1. Raw Datasets

### Purpose

Immutable source data from providers.

### Examples

* exchange candles
* broker data
* CSV imports
* tick streams
* astronomical calculations
* macroeconomic datasets

### Important Rules

* never modified after ingestion
* preserve original provider schema
* preserve provider metadata
* preserve ingestion timestamp

### Storage Location

```text
datasets/raw/
```

---

## 2. Normalized Datasets

### Purpose

Provider-independent internal contracts.

### Examples

* normalized OHLCV
* normalized tick data
* normalized alternative datasets

### Important Rules

* canonical schema only
* validated before runtime usage
* source-independent structure

### Storage Location

```text
datasets/normalized/
```

---

## 3. Processed Datasets

### Purpose

Derived analytical datasets.

### Examples

* resampled datasets
* cleaned datasets
* merged datasets
* enriched datasets

---

## 4. Feature Datasets

### Purpose

Precomputed feature pipelines.

### Examples

* indicators
* rolling statistics
* cycle features
* planetary alignments
* volatility regimes

### Important Rules

Feature datasets must remain reproducible.

---

## 5. Alternative Datasets

### Purpose

Non-standard research datasets.

### Examples

* sentiment
* macroeconomic
* social data
* on-chain metrics
* astronomical datasets
* planetary calculations

---

# Canonical OHLCV Schema

All normalized OHLCV datasets must follow this schema.

---

## Required Fields

| Field       | Type         | Description               |
| ----------- | ------------ | ------------------------- |
| symbol      | string       | Instrument symbol         |
| asset_class | string       | Asset category            |
| venue       | string       | Exchange or trading venue |
| timeframe   | string       | Candle timeframe          |
| timestamp   | datetime UTC | Candle timestamp          |
| open        | float        | Candle open               |
| high        | float        | Candle high               |
| low         | float        | Candle low                |
| close       | float        | Candle close              |
| volume      | float        | Candle volume             |
| source      | string       | Data provider source      |

---

## Optional Fields

| Field             | Type    | Description                         |
| ----------------- | ------- | ----------------------------------- |
| trade_count       | integer | Number of trades                    |
| vwap              | float   | Volume weighted average price       |
| bid               | float   | Bid price                           |
| ask               | float   | Ask price                           |
| spread            | float   | Bid/ask spread                      |
| adjustment_factor | float   | Corporate action adjustment         |
| metadata          | json    | Provider-specific optional metadata |

---

# Timestamp Contract

Timestamp consistency is mandatory.

---

## Canonical Time Standard

ALL normalized timestamps must use:

```text
UTC
ISO-8601 compatible
timezone-aware datetime
```

---

## Canonical Candle Convention

The timestamp represents:

```text
candle OPEN time
```

Example:

```text
1m candle
12:00:00 → represents 12:00:00 until 12:00:59
```

This convention must remain consistent across:

* historical data
* live data
* backtesting
* forward testing
* paper trading

---

## Timestamp Precision

Preferred precision:

```text
milliseconds
```

Nanosecond precision may be supported internally for tick systems if required later.

---

## Forbidden Timestamp Behavior

The following are prohibited:

* naive datetimes
* mixed timezone handling
* provider-local timezone leakage
* inconsistent candle-close conventions

---

# Timeframe Contract

Timeframes must use canonical identifiers.

---

## Allowed Timeframe Format

Examples:

```text
1m
5m
15m
1h
4h
1d
1w
1M
```

---

## Timeframe Ownership Rule

Timeframe aggregation must occur inside:

* normalization layer
* feature layer
* runtime layer

NOT inside individual strategies.

---

# Live vs Historical Data Contract

Live and historical data must expose identical normalized schemas.

The difference must exist only in:

* transport mechanism
* delivery timing
* runtime orchestration

Strategies must not know whether data is:

* historical
* live
* replayed
* simulated

---

# Tick Data Contract

Future tick-level systems should follow normalized schemas.

---

## Canonical Tick Fields

| Field     | Type            |
| --------- | --------------- |
| symbol    | string          |
| timestamp | datetime UTC    |
| price     | float           |
| size      | float           |
| side      | string optional |
| source    | string          |

---

# Order Book Contract

Future order book systems should remain normalized.

---

## Canonical Order Book Structure

```text
symbol
timestamp
bids[]
asks[]
source
```

Each bid/ask level should include:

```text
price
size
```

---

# Missing Data Rules

Data gaps must be handled explicitly.

---

## Missing Candle Policy

Missing candles must NOT silently disappear.

One of the following must occur:

* explicit gap insertion
* validation rejection
* flagged metadata

---

## NaN Policy

NaN handling must be deterministic.

Allowed behaviors:

* explicit filling rules
* explicit rejection
* explicit masking

Silent NaN propagation is prohibited.

---

# Duplicate Timestamp Rules

Duplicate timestamps are prohibited in normalized OHLCV datasets unless explicitly supported by dataset type.

If duplicates occur:

* validation must fail
  OR
* deterministic merge policy must apply

---

# Corporate Action Rules

Adjusted and non-adjusted datasets must remain distinguishable.

Required metadata:

| Field             | Description        |
| ----------------- | ------------------ |
| adjusted          | whether adjusted   |
| adjustment_source | provider/source    |
| adjustment_type   | split/dividend/etc |

---

# Data Validation Rules

All normalized datasets must pass validation before runtime usage.

---

## Validation Areas

### Structural Validation

* required fields
* schema integrity
* type validation

### Time Validation

* monotonic timestamps
* timeframe consistency
* timezone consistency

### Numerical Validation

* OHLC relationships
* non-negative volume
* finite numeric values

### Metadata Validation

* source existence
* symbol integrity
* timeframe validity

---

# Data Normalization Rules

Normalization must isolate provider differences.

---

## Provider Isolation Rule

Strategies must never know:

* provider field names
* provider-specific timestamp formats
* provider-specific enums
* provider-specific quirks

---

## Adapter Responsibility

Adapters are responsible for:

* field mapping
* timestamp conversion
* normalization
* metadata extraction
* validation preparation

---

# Storage Contracts

---

## PostgreSQL Responsibilities

Used for:

* metadata
* dataset registry
* ingestion metadata
* runtime metadata
* experiment tracking

NOT large OHLCV storage.

---

## DuckDB Responsibilities

Used for:

* analytical queries
* historical backtesting
* feature pipelines
* time-series analysis

---

## Parquet Responsibilities

Used for:

* long-term time-series storage
* partitioned datasets
* efficient historical retrieval
* portable analytical storage

---

# Parquet Partitioning Rules

Preferred partitioning structure:

```text
asset_class/
symbol/
timeframe/
year/
month/
```

Example:

```text
equities/AAPL/1d/2026/05/
crypto/BTCUSDT/1m/2026/05/
```

---

# Feature Dataset Contract

Feature datasets must preserve reproducibility.

---

## Required Metadata

| Field                | Description                |
| -------------------- | -------------------------- |
| feature_version      | feature definition version |
| generation_timestamp | generation time            |
| source_dataset       | source dataset ID          |
| timeframe            | timeframe                  |
| parameter_hash       | parameter signature        |

---

## Feature Ownership Rule

Reusable features belong in shared feature pipelines.

NOT embedded directly inside strategies unless strategy-specific.

---

# Alternative Dataset Contract

Alternative datasets must still follow normalization discipline.

---

## Examples

* planetary calculations
* astronomical alignments
* macroeconomic events
* sentiment data
* seasonal cycles

---

## Required Metadata

| Field               | Description         |
| ------------------- | ------------------- |
| source              | provider/source     |
| generation_method   | computation method  |
| timezone_basis      | timezone assumption |
| calculation_version | algorithm version   |

---

# Multi-Timeframe Contract

Strategies may consume multiple timeframes.

However:

* timeframe aggregation must remain centralized
* aggregation logic must remain deterministic

Strategies must not independently implement conflicting aggregation logic.

---

# Candle Aggregation Rules

Canonical aggregation rules:

| Field  | Aggregation |
| ------ | ----------- |
| open   | first       |
| high   | max         |
| low    | min         |
| close  | last        |
| volume | sum         |

---

# Dataset Versioning Rules

Critical datasets must support version tracking.

---

## Dataset Metadata

Required fields:

| Field               | Description       |
| ------------------- | ----------------- |
| dataset_id          | unique identifier |
| dataset_version     | version           |
| source              | source provider   |
| ingestion_timestamp | ingestion time    |
| schema_version      | schema version    |

---

# Runtime Data Contract

Runtime systems must consume only validated normalized contracts.

Runtime systems must never directly access:

* raw provider APIs
* raw CSV schemas
* provider-native payloads

---

# Backtesting Data Contract

Backtesting datasets must remain reproducible.

Backtest runs must record:

* dataset version
* feature version
* parameter set
* execution assumptions
* runtime version

---

# Frontend Data Contract

Frontend systems consume API contracts only.

Frontend systems must not:

* normalize market data
* calculate official backtest metrics
* generate official signals

---

# API Data Contract

APIs must expose stable canonical schemas.

Avoid exposing:

* provider-native payloads
* internal storage layouts
* unstable experimental structures

---

# Data Integrity Principles

QuantLab prioritizes:

* determinism
* reproducibility
* portability
* validation
* auditability
* provider abstraction

All systems depending on data must preserve these principles.

---

# Forbidden Data Patterns

The following patterns are prohibited:

* strategies consuming provider-native schemas
* frontend normalization logic
* mixed timezone handling
* silent NaN propagation
* silent missing candle removal
* provider-specific fields inside strategies
* uncontrolled aggregation logic
* direct raw CSV access inside strategies
* runtime systems bypassing validation

---

# Final Data Principle

Data consistency is one of the foundational architectural pillars of QuantLab.

All higher-level systems depend on stable and deterministic data behavior.

If data contracts become inconsistent:

* strategy portability breaks
* backtesting reproducibility breaks
* runtime consistency breaks
* execution safety degrades

All data systems must preserve:

* normalization discipline
* reproducibility
* provider abstraction
* deterministic behavior
* validation integrity

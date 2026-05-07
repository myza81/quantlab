# VALIDATE_DATASET.md

## Purpose

This directive defines the workflow, validation rules, normalization requirements, and quality assurance standards for validating datasets inside QuantLab.

Dataset validation exists to ensure all research, backtesting, forward testing, and execution systems operate using:

* trustworthy data
* normalized schemas
* reproducible datasets
* traceable transformations
* architecture-safe pipelines

Invalid or inconsistent datasets can corrupt:

* research conclusions
* backtest results
* strategy behavior
* runtime stability
* execution safety

---

# Core Philosophy

Data quality is a first-class system responsibility.

Strategies must trust the internal data contracts.

Dataset validation exists to prevent:

* malformed data
* timestamp corruption
* missing candles
* duplicate records
* future-data leakage
* schema inconsistency
* provider-specific leakage
* silent normalization failures

---

# Objective

When validating datasets, the implementation agent must:

1. validate schema integrity
2. validate timestamp consistency
3. validate normalization correctness
4. validate reproducibility
5. validate data completeness
6. preserve traceability
7. prevent corrupted downstream workflows

---

# Required Validation Workflow

Minimum required workflow:

```text
source ingestion
→ schema validation
→ normalization validation
→ timestamp validation
→ completeness validation
→ anomaly detection
→ storage validation
→ reproducibility validation
→ dataset approval or rejection
```

---

# Supported Dataset Types

Validation workflows may apply to:

* OHLCV datasets
* tick datasets
* order book datasets
* macroeconomic datasets
* sentiment datasets
* planetary datasets
* astronomical datasets
* derived feature datasets
* alternative datasets
* custom research datasets

All dataset categories must follow validation discipline.

---

# Normalization Rules

All datasets must be normalized into stable internal contracts before strategy usage.

Strategies must NOT consume:

* raw API responses
* vendor-specific fields
* exchange-specific payloads
* inconsistent timestamp formats

VALID FLOW:

```text
provider
→ ingestion adapter
→ normalization
→ validation
→ storage
→ strategy/runtime usage
```

INVALID FLOW:

```text
provider
→ strategy
```

---

# Required OHLCV Fields

Normalized OHLCV datasets should minimally preserve:

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

Optional metadata may include:

```text
adjustments
corporate actions
provider metadata
quality scores
```

---

# Timestamp Validation Rules

All timestamps must be validated for:

* timezone consistency
* ordering consistency
* duplicate timestamps
* missing intervals
* session alignment
* daylight saving issues
* aggregation consistency

Datasets with unstable timestamps are invalid.

---

# Missing Data Rules

Validation must detect:

* missing candles
* missing ticks
* null values
* broken sessions
* incomplete ranges
* corrupted records

Missing data handling must be explicit.

Avoid silent interpolation unless intentionally configured.

---

# Duplicate Data Rules

Validation must detect:

* duplicate timestamps
* duplicate trades
* duplicate candles
* duplicate feature rows

Duplicate handling rules must be deterministic and documented.

---

# Future Data Leakage Rules

Validation pipelines must prevent future-data leakage.

Strategies and features must never access:

* future candles
* future labels
* future features
* future macro releases
* future timestamps

Feature generation pipelines must preserve causal ordering.

---

# Timeframe Validation Rules

Aggregated datasets must validate:

* candle boundaries
* aggregation correctness
* timeframe alignment
* session handling
* open/high/low/close integrity

Aggregation pipelines must remain deterministic.

---

# Data Consistency Rules

Validation should detect inconsistencies such as:

* open > high
* low > close
* negative volume
* invalid timestamps
* broken session continuity
* impossible ranges
* invalid feature outputs

Invalid rows should be:

* rejected
* quarantined
* flagged
* corrected through explicit logic

Never silently ignored.

---

# Alternative Dataset Rules

Alternative datasets are fully supported.

Examples:

* moon phase data
* planetary position data
* eclipse timing
* macroeconomic releases
* sentiment streams
* social metrics
* cyclical datasets

However:

Alternative datasets must still preserve:

* timestamps
* normalization
* traceability
* reproducibility
* schema consistency

---

# Feature Dataset Rules

Derived feature datasets must preserve:

* source dataset references
* feature version
* calculation parameters
* timestamps
* feature lineage

Feature generation must remain reproducible.

---

# Storage Validation Rules

Datasets stored in:

* DuckDB
* Parquet
* PostgreSQL

must preserve:

* schema integrity
* deterministic serialization
* reproducible loading behavior

Avoid hidden preprocessing during retrieval.

---

# Dataset Versioning Rules

Every approved dataset should preserve:

* dataset ID
* dataset version
* source provider
* ingestion timestamp
* normalization version
* preprocessing assumptions
* feature generation version

Datasets without traceability are invalid.

---

# Validation Metrics Rules

Validation workflows may produce metrics such as:

* completeness percentage
* duplicate ratio
* timestamp integrity score
* anomaly counts
* missing-data ratio
* session continuity metrics
* feature validity ratios

Metrics should remain reviewable.

---

# Reproducibility Rules

Dataset generation and validation must be reproducible.

Repeated validation using identical:

* source inputs
* normalization logic
* preprocessing configuration

should produce consistent outputs.

---

# Runtime Compatibility Rules

Validated datasets must remain compatible across:

* research
* backtesting
* forward testing
* paper trading
* future live runtime systems

Dataset contracts must remain stable.

---

# Failure Handling Rules

Validation failures must produce:

* explicit errors
* diagnostics
* anomaly reports
* rejection reasons
* traceable logs

Avoid silent corruption.

---

# Dataset Approval Rules

A dataset may be approved ONLY if:

- [ ] schema validation passes
- [ ] timestamps are valid
- [ ] normalization is correct
- [ ] no future-data leakage exists
- [ ] duplicates are handled
- [ ] missing-data handling is defined
- [ ] traceability exists
- [ ] reproducibility is validated

---

# Forbidden Patterns

The following are prohibited:

* raw provider schema leakage
* silent missing-data interpolation
* hidden preprocessing
* non-versioned datasets
* future-data leakage
* inconsistent timestamp formats
* undocumented transformations
* strategy-specific dataset hacks
* runtime-only data mutations

---

# Deliverables

Minimum expected deliverables:

* dataset definition
* normalization definition
* schema validation report
* timestamp validation report
* anomaly report
* reproducibility summary
* dataset version metadata
* approval/rejection recommendation

---

# Validation Checklist

Before approving a dataset, confirm:

- [ ] schema integrity is valid
- [ ] timestamps are valid
- [ ] normalization is validated
- [ ] no future-data leakage exists
- [ ] missing-data handling is documented
- [ ] duplicate handling is deterministic
- [ ] traceability exists
- [ ] reproducibility is validated
- [ ] runtime compatibility is preserved
- [ ] no architecture guardrails were violated

---

# Final Instruction

Dataset validation inside QuantLab exists to preserve the integrity of the entire research and execution ecosystem.

Dataset validation is NOT:

* optional cleanup
* cosmetic preprocessing
* silent correction logic
* provider-dependent behavior

The objective is to create deterministic, normalized, and trustworthy datasets capable of supporting institutional-grade research and execution workflows while preserving:

* reproducibility
* traceability
* modularity
* runtime safety
* architecture integrity
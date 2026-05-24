# Phase 2R.0 — Modular Tool System Architecture

## Objective

Design and establish the scalable architectural foundation for QuantLab’s trading tool ecosystem.

This phase does **NOT** focus on adding many indicators yet.

Instead, it establishes:

```text
how tools are structured
how tools are registered
how tools expose outputs
how tools validate parameters
how tools integrate into:
  - semantics
  - evaluation
  - simulation
  - visualization
```

This phase is foundational because the trading tools subsystem will become one of the largest and most important domains in QuantLab.

The goal is to prevent:

```text
giant monolithic indicator folder
hardcoded strategy logic
tight coupling
unmaintainable growth
```

and instead establish:

```text
modular reusable tool ecosystem
```

---

# Architectural Philosophy

## Core Principle

A tool is:

```text
a reusable computational primitive
```

NOT:

```text
a strategy
```

Examples:

```text
SMA
EMA
RSI
MACD
ATR
Bollinger Bands
Volume MA
```

A strategy consumes tool outputs.

The tool itself never contains:

* trade logic
* portfolio logic
* signal generation
* broker logic
* execution behavior

---

# Architectural Separation

## Correct Layering

```text
Market Data
    ↓
Tool Computation Layer
    ↓
Semantic Rule Layer
    ↓
Evaluation Layer
    ↓
Signal Event Layer
    ↓
Trade Intent Layer
    ↓
Backtest Simulation
    ↓
Future Execution Layer
```

## Critical Rule

```text
Tool calculation ≠ Strategy logic
```

Example:

### BAD

```python
if sma_fast > sma_slow:
    buy()
```

### GOOD

```python
tool outputs:
  sma_fast.value
  sma_slow.value

semantics:
  sma_fast.value crosses_above sma_slow.value
```

---

# Tool System Goals

The tool system must support:

```text
modularity
discoverability
validation
versioning
reusability
frontend configurability
visualization metadata
future expansion
```

---

# High-Level Tool Architecture

## Recommended Structure

```text
backend/tools/

  core/
    registry.py
    metadata.py
    parameters.py
    outputs.py
    validation.py
    contracts.py
    discovery.py

  indicators/

    trend/
      sma/
        tool.py
        metadata.py
        compute.py
        validation.py
        tests/

      ema/
        ...

    momentum/
      rsi/
      macd/

    volatility/
      atr/
      bollinger/

    volume/
      volume_ma/

  transforms/
    crossover/
    rate_of_change/

  tests/
```

---

# Tool Categories

## 1. Indicators

Produce analytical values from market data.

Examples:

```text
SMA
EMA
RSI
MACD
ATR
Bollinger
```

---

## 2. Transforms

Operate on existing tool outputs.

Examples:

```text
crossovers
normalization
difference
rate_of_change
```

---

## 3. Future Statistical Tools

Examples:

```text
zscore
correlation
beta
rolling_std
rolling_mean
```

---

## 4. Future AI / Quant Tools

Examples:

```text
regime classification
pattern detection
ml inference
factor ranking
```

---

# Core Tool Contract

Every tool must expose a deterministic contract.

## Required Metadata

```python
tool_id
name
version
category
description
```

---

## Required Parameters

Example:

```python
period: int
source: str
```

Each parameter requires:

```python
type
default
min/max
validation
ui hints
```

---

## Required Outputs

Examples:

```python
SMA.value
EMA.value
RSI.value
MACD.line
MACD.signal
ATR.value
```

Outputs must be explicitly declared.

---

## Visualization Metadata

Tool declares rendering hints.

Example:

```python
pane = "main"
color = "#ffaa00"
style = "line"
```

Frontend uses hints only.

Frontend must never compute tools.

---

# Tool Registry System

## Purpose

Registry acts as the source of truth.

Responsibilities:

```text
tool discovery
tool lookup
tool validation
metadata exposure
frontend schema exposure
```

---

# Registry Requirements

Registry must support:

```text
register(tool)
get(tool_id)
list()
validate(tool_config)
```

---

# Dynamic Discovery

Future-ready architecture should support:

```text
auto-discovery
plugin loading
third-party tools
```

But Phase 2R.0 may still use static registration initially.

---

# Tool Configuration Contract

## Tool Instance

Example:

```json
{
  "instance_id": "sma_fast",
  "tool_id": "sma",
  "parameters": {
    "period": 20
  }
}
```

---

# Critical Rule

Instance IDs must remain strategy-local.

This enables:

```text
sma_fast.value
sma_slow.value
```

inside semantics.

---

# Computation Philosophy

## Tool Inputs

Tools consume:

```text
normalized market data
or prior tool outputs
```

Never broker APIs.

Never frontend state.

---

# Tool Outputs

Outputs must be:

```text
deterministic
typed
serializable
time-aligned
```

---

# Multi-Output Tool Support

Example:

```text
MACD.line
MACD.signal
MACD.histogram
```

The architecture must support multi-output tools from the beginning.

---

# Time Alignment Philosophy

Future tool computation pipeline must support:

```text
bar-aligned outputs
lookback windows
NaN warmup periods
multi-timeframe later
```

But Phase 2R.0 only establishes architecture contracts.

---

# Frontend Responsibilities

Frontend should ONLY:

```text
display tool metadata
configure parameters
visualize outputs
show tool panels
```

Frontend must NOT:

```text
compute indicators
validate computation logic
generate signals
```

---

# Visualization Philosophy

Each tool may expose visualization hints:

```text
main chart
sub-panel
line
histogram
band
overlay
```

Examples:

## SMA

```text
main chart overlay line
```

## RSI

```text
separate lower panel
```

## Bollinger

```text
3-line overlay band
```

---

# Semantic Integration

Semantics consume tool outputs.

Example:

```text
rsi.value > 70
sma_fast.value crosses_above sma_slow.value
```

Tool layer never knows semantic meaning.

---

# Evaluation Integration

Evaluator resolves:

```text
tool_output references
```

using precomputed tool outputs.

Evaluator never computes indicators.

---

# Backtesting Integration

Backtesting consumes:

```text
TradeIntentBatch
```

generated downstream.

Backtesting must never recompute indicators internally.

---

# Future Tool Computation Pipeline

Future phases will establish:

```text
historical tool computation engine
incremental live updates
dependency graph resolution
tool caching
parallel computation
```

But NOT in Phase 2R.0.

---

# Scalability Philosophy

The system must support:

```text
hundreds of tools
thousands of tool instances
many strategies
```

without:

```text
hardcoded branching
manual frontend wiring
tight coupling
```

---

# Future Tool Dependency Graph

Future architecture may support:

```text
EMA(SMA(close))
RSI(EMA(close))
```

Thus tools should eventually become graph nodes.

But Phase 2R.0 only establishes the contracts.

---

# Testing Philosophy

Every tool must eventually support:

```text
parameter validation tests
output shape tests
determinism tests
warmup tests
edge-case tests
```

---

# Forbidden Architecture

## DO NOT

```text
put strategy logic inside tools
compute indicators in frontend
hardcode indicators into evaluator
mix broker logic into tools
make tools stateful without contract
```

---

# Phase 2R.0 Deliverables

This phase should establish:

## Core Architecture

```text
tool contracts
tool metadata models
tool parameter models
tool output models
registry architecture
validation architecture
visualization metadata contract
```

---

## Initial Registry Infrastructure

```text
ToolRegistry
ToolDefinition
ToolOutputDefinition
ToolParameterDefinition
```

---

## Initial Example Tool(s)

Minimal tools only for proving architecture:

```text
SMA
EMA
```

NOT full indicator pack yet.

---

# NOT Included in Phase 2R.0

## No Large Indicator Expansion Yet

Deferred:

```text
RSI
MACD
ATR
Bollinger
```

until architecture proven.

---

## No Tool Computation Engine Yet

Deferred:

```text
incremental updates
dependency graphs
parallel execution
```

---

## No Live Streaming Yet

Deferred entirely.

---

## No Frontend Chart Rendering Yet

Visualization contracts only.

---

# Recommended Phase Sequence

## Phase 2R.0

```text
Modular Tool System Architecture
```

## Phase 2R.1

```text
Core Indicator Tool Pack
(SMA, EMA, RSI, ATR, MACD)
```

## Phase 2R.2

```text
Historical Tool Computation Pipeline
```

## Phase 2R.3

```text
Tool Output Visualization
```

## Phase 2R.4

```text
Multi-Output + Dependency Graph Tools
```

---

# Final Architectural Principle

QuantLab tools must evolve into:

```text
institution-grade reusable research primitives
```

NOT:

```text
random indicator helper functions
```

# CHART_INDICATOR_TOOL_CONTRACT.md

Architecture contract defining how QuantLab tools become visual chart indicators.

This is a planning and governance document.
It does not constitute a feature implementation.
Implementation phases are defined in §18.

**Revision:** Chart-UX-3A.1 — Hardened to address tool-type taxonomy, tool discovery metadata,
multiple indicator instance support, indicator presets, and experimental promotion lifecycle.

Related contracts:
- `docs/TOOL_REGISTRY_CONTRACT.md` — authoritative tool registry governance
- `docs/ARCHITECTURE_GUARDRAILS.md` — platform-wide non-negotiable rules
- `docs/FRONTEND_COMPOSITION_INTERFACE_CONTRACT.md` — frontend composition rules
- `docs/DATA_CONTRACT.md` — normalized data schema
- `docs/HISTORICAL_TOOL_COMPUTATION_PIPELINE.md` — backend computation pipeline

---

## 1. Purpose

This contract defines how registered QuantLab tools expose themselves as interactive visual
indicators on the Chart page.

A tool that declares itself chart-visible must supply a visualization metadata block and discovery
metadata block that the Chart page and backend endpoint can use to:

- determine how to render the tool's output
- determine which chart pane to use
- determine what parameters are editable
- determine the backend computation contract
- determine how to surface the tool in the indicator picker

This contract does not replace `docs/TOOL_REGISTRY_CONTRACT.md`.
It extends it with the additional obligations required for chart-visible tools.

**Only tools with `tool_type: indicator` (§4) may be declared chart-visible.**
All other tool types default to `visible_on_chart: false` and must not appear in the chart
indicator panel.

---

## 2. Problem Statement

QuantLab currently has a working tool registry with six registered tools: `sma`, `ema`, `rsi`,
`macd`, `bollinger_bands`, `atr`.

These tools are usable in Strategy Builder for composing strategy semantics and running backtests.

They are **not** yet usable interactively on the Chart page.

The Chart page currently renders OHLCV candlestick data. It can overlay indicator series returned
by the composition-run endpoint (`POST /semantics/composition-run`) but this is tightly coupled to
the Strategy Builder flow and does not expose a dedicated, user-interactive chart indicator panel.

The result is that users cannot:

- select an indicator on the Chart page and see it rendered immediately
- adjust indicator parameters interactively on the chart
- visualize an indicator without first building a strategy draft
- apply named presets (e.g., "EMA 20", "MACD Standard") for common configurations
- run multiple instances of the same tool with different parameters simultaneously

This contract defines the architectural foundation that will be implemented across phases
Chart-UX-3B through Chart-UX-3E to close this gap.

---

## 3. Design Principle

**One tool. One computation. Multiple consumers.**

The same registered tool — with the same parameter schema and the same backend computation —
must serve all consumers:

| Consumer | How it uses the tool |
|---|---|
| Chart page | Interactive indicator visualization with user-editable parameters |
| Strategy Builder | Composing strategy semantics and condition rules |
| Backtesting | Deterministic historical simulation |
| Forward Testing | Live bar evaluation |
| Paper Trading | Simulated execution against live data |

There must be no divergence between the indicator a user sees on the Chart page and the indicator
a strategy uses in backtesting or forward testing.

Any implementation that creates a separate, parallel indicator formula for the frontend violates
this principle.

The same tool may appear as multiple independent instances on the chart simultaneously — for
example, EMA-20, EMA-50, and EMA-200. Each instance uses the same tool computation with
different parameters. Instance identity is separate from tool identity (§9).

---

## 4. Tool-Type Taxonomy

Every tool registered in the Tool Registry must declare a `tool_type`.

The `tool_type` field governs whether a tool can be chart-visible, and how it is used across the
platform. This classification is orthogonal to the chart rendering classification (§5), which only
applies to tools that are already confirmed as chart-visible.

**Only tools with `tool_type: indicator` may declare `visible_on_chart: true`.**

All other tool types default to `visible_on_chart: false` and must not appear in the chart
indicator panel. This is enforced at the backend metadata validation layer.

### 4.1 `indicator`

Classical and research analytical computation modules that produce output series meaningful for
direct visualization on a price chart or oscillator pane.

These tools may declare `visible_on_chart: true` if they produce chart-renderable output.

Examples: `sma`, `ema`, `rsi`, `macd`, `bollinger_bands`, `atr`

Future examples: swing high/low detector, divergence indicator, custom research indicator,
planetary cycle phase classifier, volatility regime classifier.

### 4.2 `strategy_helper`

Modules that support strategy composition logic without producing standalone chart-meaningful
output. These tools compute intermediate values consumed by conditions and rules inside a
strategy definition.

`visible_on_chart: false` — cannot be overridden in the current contract version.

Examples: composite signal aggregators, multi-feature confluence scorers, boolean gating modules,
intermediate transformation tools whose output has no standalone chart meaning.

### 4.3 `risk_helper`

Modules that produce analytical risk context consumed by the execution layer or risk rules inside
a strategy.

`visible_on_chart: false`

Examples: position sizing engines, volatility-scaled stop estimators, risk score calculators,
invalidation level calculators.

### 4.4 `portfolio_helper`

Modules producing portfolio-level analytical context.

`visible_on_chart: false`

Examples: portfolio exposure calculators, drawdown estimators, correlation scoring tools,
cross-asset regime classifiers.

### 4.5 `execution_helper`

Modules supporting execution mechanics, not analytical research.

`visible_on_chart: false`

Examples: slippage estimators, fill simulation helpers, market impact models.

### 4.6 `analysis_helper`

General-purpose analytical or data-preparation modules that do not fit other categories and do
not produce standalone chart output.

`visible_on_chart: false` by default. A future contract revision may define conditions under which
an `analysis_helper` can declare chart-visible output.

Examples: data quality checkers, normalization helpers, z-score transformers used as inputs to
downstream indicators.

### 4.7 Taxonomy Enforcement

The registry validation layer must reject any attempt to set `visible_on_chart: true` on a tool
whose `tool_type` is not `indicator`, unless a future contract explicitly permits it.

This rule prevents risk, execution, and portfolio helper tools from contaminating the chart
indicator panel with outputs not designed for chart visualization.

---

## 5. Chart Rendering Classification

Every tool with `tool_type: indicator` and `visible_on_chart: true` must be classified into one
of the following chart rendering categories.

This classification governs how the tool's output is rendered on the chart. It is declared as part
of the tool's visualization metadata (§6). It is distinct from the tool-type taxonomy (§4), which
governs what kind of tool it is.

### 5.1 Overlay Indicator

A continuous series rendered on the same pane as the price chart, sharing the price axis.

The output values are expressed in price units.

The frontend must allocate no additional vertical space for overlay indicators.

Multiple overlays must be composable and renderable simultaneously without visual interference.

Examples: `sma`, `ema`, `bollinger_bands` (middle band, upper band, lower band)

### 5.2 Oscillator / Separate-Pane Indicator

A series rendered in a dedicated panel below the price chart.

The output values are typically bounded or expressed in non-price units.

The frontend must allocate a dedicated vertical region for oscillator panes.

Examples: `rsi` (bounded 0–100), `macd` (MACD line, signal line, histogram), `atr` (absolute
volatility)

### 5.3 Multi-Series Indicator

A tool that produces multiple named output series that may span overlay and oscillator contexts.

Each named series within the tool declares its own pane assignment independently in the
`output_series` list.

Example: `bollinger_bands` — all three bands are price overlays. `macd` — MACD line, signal line,
and histogram are all oscillator pane series.

### 5.4 Event / Marker Indicator

A tool that produces discrete point events suitable for rendering as markers, arrows, or
annotations on the chart.

These are not continuous series; they mark specific bars where a condition or pattern occurred.

They do not occupy a separate pane. They render on the price pane as point annotations.

Examples: signal markers, swing high/low detection, divergence markers, pattern completion points.

### 5.5 Drawing Object / Manual Annotation

User-placed annotations that are not computed by backend tools.

Examples: trend lines, horizontal levels, Fibonacci retracements drawn manually.

These are chart-layer objects and are outside the scope of this contract. This category is
documented here only for completeness of the rendering classification taxonomy.

### 5.6 Non-Visual Indicator

An `indicator`-type tool that produces outputs consumed only by downstream tools or strategy
conditions, with no meaningful direct chart rendering.

These tools have `tool_type: indicator` (they are analytical computation modules) but declare
`visible_on_chart: false` because their output is not designed for standalone chart rendering.

Distinguished from §4.2–§4.6 tool types: a `strategy_helper` is not an indicator; a non-visual
indicator is an indicator that has elected not to expose chart rendering.

Examples: intermediate EMA series consumed only by MACD, running Z-score transformations,
feature outputs used exclusively by downstream rule conditions.

---

## 6. Visualization Metadata Contract

Every tool with `tool_type: indicator` and `visible_on_chart: true` must provide a complete
visualization metadata block.

This metadata is the source of truth for the Chart page and the backend indicator artifact
endpoint. Discovery-specific metadata fields (category, subcategory, search_keywords,
display_order) are defined separately in §7.

### 6.1 Required Fields

| Field | Type | Description |
|---|---|---|
| `tool_type` | `enum` | Must be `"indicator"` for any chart-visible tool. See §4. |
| `visible_on_chart` | `bool` | Whether this tool appears in the chart indicator panel. `false` for non-visual tools. |
| `chart_pane` | `enum` | `"price_overlay"` or `"oscillator_pane"`. Multi-series tools may declare per-series. |
| `render_type` | `enum` | `"line"`, `"area"`, `"histogram"`, `"band"`, `"marker"`. Tells the frontend how to render each output series. |
| `series_kind` | `enum` | `"continuous"` or `"event"`. Continuous series fill every bar; event series mark specific bars only. |
| `default_parameters` | `dict` | The default parameter values matching the tool's registered parameter schema. |
| `editable_parameters` | `list[str]` | The parameter names the user may edit from the chart indicator panel. Must be a subset of the declared parameter schema. |
| `source_field` | `str` | The OHLCV field used as input. Typically `"close"`. Valid values: `"open"`, `"high"`, `"low"`, `"volume"`, `"hl2"`, `"hlc3"`, `"ohlc4"`. |
| `warmup_bars_required` | `int` | Minimum bars required before the first meaningful output. Must match the tool's computation logic. |
| `output_series` | `list[OutputSeriesSpec]` | Ordered list of named output series this tool produces for chart rendering. See §6.2. |
| `display_name` | `str` | Human-readable name for the chart indicator panel. Example: `"Simple Moving Average"`. |
| `description` | `str` | One-sentence description of what this tool computes. Shown in the indicator picker tooltip. |

### 6.2 OutputSeriesSpec

Each entry in `output_series` describes one renderable data series.

| Field | Type | Description |
|---|---|---|
| `series_id` | `str` | Stable internal identifier. Matches the tool output reference used in strategy semantics (e.g., `"sma"`, `"macd_line"`, `"upper_band"`). |
| `label` | `str` | Human-readable label for this series. Shown in the chart legend. |
| `pane` | `enum` | `"price_overlay"` or `"oscillator_pane"`. Overrides tool-level `chart_pane` for multi-series tools. |
| `render_type` | `enum` | `"line"`, `"histogram"`, `"area"`, `"band_fill"`. The visual form for this specific series. |
| `default_color` | `str` | Hex color for the series line or histogram bars. Example: `"#f59e0b"`. |
| `default_line_width` | `int` | Line width in pixels. Default `1`. |

### 6.3 Reference Metadata for Current Tools

The following is a non-normative reference showing how existing registered tools would declare
their full metadata — visualization fields (this section) and discovery fields (§7).

Actual registration is implemented in Phase Chart-UX-3D (§18).

#### `sma` — Simple Moving Average

```
tool_type: indicator
visible_on_chart: true
chart_pane: price_overlay
render_type: line
series_kind: continuous
default_parameters: { period: 20, source: "close" }
editable_parameters: ["period", "source"]
source_field: close
warmup_bars_required: period - 1
output_series:
  - series_id: sma
    label: SMA
    pane: price_overlay
    render_type: line
    default_color: "#f59e0b"
display_name: Simple Moving Average
description: Arithmetic mean of closing prices over N bars.
# discovery fields — see §7
category: Trend
subcategory: Moving Averages
search_keywords: ["simple moving average", "sma", "moving average", "ma", "average"]
display_order: 10
```

#### `ema` — Exponential Moving Average

```
tool_type: indicator
visible_on_chart: true
chart_pane: price_overlay
render_type: line
series_kind: continuous
default_parameters: { period: 20, source: "close" }
editable_parameters: ["period", "source"]
source_field: close
warmup_bars_required: period - 1
output_series:
  - series_id: ema
    label: EMA
    pane: price_overlay
    render_type: line
    default_color: "#3b82f6"
display_name: Exponential Moving Average
description: Exponentially weighted moving average, reactive to recent price changes.
# discovery fields — see §7
category: Trend
subcategory: Moving Averages
search_keywords: ["exponential moving average", "ema", "moving average", "ma", "weighted"]
display_order: 20
```

#### `rsi` — Relative Strength Index

```
tool_type: indicator
visible_on_chart: true
chart_pane: oscillator_pane
render_type: line
series_kind: continuous
default_parameters: { period: 14, source: "close" }
editable_parameters: ["period"]
source_field: close
warmup_bars_required: period
output_series:
  - series_id: rsi
    label: RSI
    pane: oscillator_pane
    render_type: line
    default_color: "#a855f7"
display_name: Relative Strength Index
description: Momentum oscillator measuring the speed and magnitude of recent price changes (0–100).
# discovery fields — see §7
category: Momentum
subcategory: null
search_keywords: ["relative strength index", "rsi", "momentum", "overbought", "oversold"]
display_order: 10
```

#### `macd` — Moving Average Convergence/Divergence

```
tool_type: indicator
visible_on_chart: true
chart_pane: oscillator_pane
render_type: line
series_kind: continuous
default_parameters: { fast_period: 12, slow_period: 26, signal_period: 9, source: "close" }
editable_parameters: ["fast_period", "slow_period", "signal_period"]
source_field: close
warmup_bars_required: slow_period + signal_period - 1
output_series:
  - series_id: macd_line
    label: MACD
    pane: oscillator_pane
    render_type: line
    default_color: "#3b82f6"
  - series_id: signal_line
    label: Signal
    pane: oscillator_pane
    render_type: line
    default_color: "#f97316"
  - series_id: histogram
    label: Histogram
    pane: oscillator_pane
    render_type: histogram
    default_color: "#22c55e"
display_name: MACD
description: Trend-following momentum indicator derived from two EMAs plus a signal line.
# discovery fields — see §7
category: Momentum
subcategory: null
search_keywords: ["macd", "moving average convergence divergence", "histogram", "signal line"]
display_order: 20
```

#### `bollinger_bands` — Bollinger Bands

```
tool_type: indicator
visible_on_chart: true
chart_pane: price_overlay
render_type: band
series_kind: continuous
default_parameters: { period: 20, num_std_dev: 2.0, source: "close" }
editable_parameters: ["period", "num_std_dev"]
source_field: close
warmup_bars_required: period - 1
output_series:
  - series_id: upper_band
    label: Upper Band
    pane: price_overlay
    render_type: line
    default_color: "#94a3b8"
  - series_id: middle_band
    label: Middle Band
    pane: price_overlay
    render_type: line
    default_color: "#f59e0b"
  - series_id: lower_band
    label: Lower Band
    pane: price_overlay
    render_type: line
    default_color: "#94a3b8"
display_name: Bollinger Bands
description: Volatility envelope defined by standard deviation bands around a simple moving average.
# discovery fields — see §7
category: Volatility
subcategory: Bands
search_keywords: ["bollinger bands", "bb", "bands", "volatility", "standard deviation", "envelope"]
display_order: 10
```

#### `atr` — Average True Range

```
tool_type: indicator
visible_on_chart: true
chart_pane: oscillator_pane
render_type: line
series_kind: continuous
default_parameters: { period: 14 }
editable_parameters: ["period"]
source_field: hlc3
warmup_bars_required: period
output_series:
  - series_id: atr
    label: ATR
    pane: oscillator_pane
    render_type: line
    default_color: "#ef4444"
display_name: Average True Range
description: Smoothed average of the true price range, measuring market volatility.
# discovery fields — see §7
category: Volatility
subcategory: null
search_keywords: ["average true range", "atr", "volatility", "range", "true range"]
display_order: 20
```

---

## 7. Tool Discovery Metadata

Every tool with `visible_on_chart: true` must also declare discovery metadata.

Discovery metadata drives how the chart indicator picker presents, groups, and searches available
indicators. The picker must be entirely metadata-driven — it must not contain hardcoded tool lists
or tool-identity-aware branching logic (see §16.8).

### 7.1 Required Discovery Fields

| Field | Type | Description |
|---|---|---|
| `category` | `enum` | Primary grouping for the indicator picker. See §7.2. |
| `subcategory` | `str \| null` | Optional refinement within category. Example: `"Moving Averages"` within `"Trend"`. |
| `search_keywords` | `list[str]` | Free-text terms for the indicator picker search bar. Should not duplicate `display_name` (the picker searches `display_name` automatically). Must include common abbreviations and alternate names. |
| `display_order` | `int` | Preferred sort order within the category group. Lower numbers appear first. Ties are broken alphabetically by `display_name`. |

### 7.2 Category Enumeration

| Category | Description | Examples |
|---|---|---|
| `Trend` | Directional movement indicators | SMA, EMA, DEMA, WMA, ALMA |
| `Momentum` | Rate-of-change and oscillator indicators | RSI, MACD, Stochastic, CCI |
| `Volatility` | Price range and band-based indicators | Bollinger Bands, ATR, Keltner Channels |
| `Volume` | Volume-based analytical tools | OBV, VWAP, Volume Profile |
| `Market Structure` | Price structure and pattern detection | Swing High/Low, Support/Resistance |
| `Pattern Recognition` | Candlestick and chart pattern detectors | Engulfing, Doji, Hammer |
| `Risk` | Risk measurement indicators intended for chart visualization | Risk-scaled stop visualizers |
| `Custom` | User-registered or platform-specific research indicators | QuantLab-specific analytical tools |

### 7.3 Discovery Behavior Rules

**Metadata-driven picker:** The frontend indicator picker must query the backend for the list of
chart-visible tools and render them using the category, subcategory, search_keywords, and
display_order fields. No tool names, categories, or ordering may be hardcoded in the frontend.

**Automatic registration:** When a new tool is registered with `visible_on_chart: true` and
complete discovery metadata, it must appear in the indicator picker automatically — without
requiring a frontend deployment.

**Search behavior:** The picker's search function must match against `display_name`,
`description`, and each entry in `search_keywords`. Matches on `display_name` take priority over
keyword matches.

**Category grouping:** Tools must be grouped under their declared `category`. If no category
filter is active, all chart-visible tools must be shown, sorted by category name and then by
`display_order` within each category.

**Subcategory display:** Subcategories are optional refinements within a category. The picker
may display subcategory headers within a category group if subcategories are present.

### 7.4 Category Assignment for Current Tools

| Tool | Category | Subcategory | display_order |
|---|---|---|---|
| `sma` | Trend | Moving Averages | 10 |
| `ema` | Trend | Moving Averages | 20 |
| `rsi` | Momentum | — | 10 |
| `macd` | Momentum | — | 20 |
| `bollinger_bands` | Volatility | Bands | 10 |
| `atr` | Volatility | — | 20 |

---

## 8. Overlay vs Pane Behavior

### 8.1 Price Overlay

An indicator rendered directly on the candlestick pane, sharing the price axis.

The frontend must allocate no additional vertical space for overlay indicators.

Overlay indicators must be composable: multiple overlays (e.g., SMA-20 + EMA-50) must be
renderable simultaneously without visual interference.

Applicable tools: `sma`, `ema`, all three Bollinger Band series.

### 8.2 Oscillator Pane

An indicator rendered in a separate panel below the price chart.

The frontend must allocate a dedicated vertical region for oscillator panes.

Multiple oscillators may share a single oscillator pane (stacked with independent y-axes) or each
occupy their own pane depending on the implementation decision in Chart-UX-3C.

Applicable tools: `rsi`, `macd`, `atr`.

### 8.3 Event Markers and Overlay Annotations

Point events are rendered on the price chart pane as visual markers (arrows, icons, dots) at
specific bar timestamps.

They do not occupy a separate pane.

They do not produce continuous series — only the bars where the event occurred are annotated.

Examples of future event-type tools: swing high/low detector, signal markers, divergence
indicators.

### 8.4 Multi-Pane Tools

Tools that produce series across multiple panes (overlay + oscillator) must declare the pane
assignment per series in their `output_series` list.

The tool-level `chart_pane` field for multi-pane tools should reflect the primary pane.

---

## 9. Multiple Indicator Instance Support

The chart indicator system must support multiple simultaneous instances of the same tool with
independent parameter sets. Future implementations must never assume a single instance per tool.

### 9.1 Tool Identity vs Instance Identity

**`tool_id`** is the stable identifier for a registered tool in the Tool Registry.

- Assigned once at registration.
- Never changes.
- Refers to the computation module: `"ema"`, `"rsi"`, `"macd"`.

**`instance_id`** is a chart-level identifier for a specific use of a tool on a specific chart.

- Assigned by the frontend when the user adds an indicator instance.
- Unique within the chart session.
- Stable for the lifetime of that indicator instance on the chart.
- Does not carry meaning across sessions or users.

Example with three instances of the same tool:

```
Tool:       ema

Instance A: instance_id = "ema_fast"   parameters = { period: 20 }
Instance B: instance_id = "ema_mid"    parameters = { period: 50 }
Instance C: instance_id = "ema_slow"   parameters = { period: 200 }
```

All three are computed by the same backend dispatcher. They produce three independent series that
can be rendered simultaneously on the price overlay pane.

### 9.2 Instance Isolation Rules

Each instance is fully independent:

- Changing parameters on Instance A does not affect Instance B or C.
- Removing Instance B does not affect Instance A or C.
- Backend computation for each instance uses only that instance's parameters.
- No computation state is shared between instances of the same tool.
- The backend must not cache or reuse computation results between instances, even when parameters
  happen to be identical, unless the caching is transparent and the isolation guarantee is
  preserved.

### 9.3 instance_id Assignment

The frontend may use any stable unique string as an `instance_id`.

Recommended patterns:

- Human-readable with parameters: `"ema_20"`, `"ema_50"`, `"rsi_14"`
- UUID-based: `"ema_3f7a2c1b"`, `"macd_9e4d8f2a"`
- Preset-derived: `"ema_20_preset"` (for instances created from presets, §10)

The `instance_id` is echoed by the backend in the indicator artifact response (§13) so the
frontend can route the response to the correct chart indicator.

### 9.4 Indicator Lifecycle on the Chart

```
User adds indicator
  → Frontend creates instance_id
  → Frontend requests artifact: (tool_id, instance_id, parameters, data_context)
  → Backend computes and returns artifact tagged with instance_id
  → Frontend renders artifact series for that instance_id

User changes parameter
  → Frontend sends new artifact request with same instance_id, updated parameters
  → Backend recomputes and returns updated artifact tagged with instance_id
  → Frontend replaces existing series for that instance_id

User removes indicator
  → Frontend destroys the instance_id
  → No further artifact requests for that instance_id
```

### 9.5 Strategy Builder Alignment

When the user adds a tool to a strategy draft in Strategy Builder, the Strategy Builder uses a
`ToolConfiguration(instance_id=..., tool_id=..., parameters=...)` structure that mirrors this
pattern exactly.

The chart indicator instance model (tool_id + instance_id + parameters) is intentionally aligned
with the existing `ToolConfiguration` contract used in backtesting and strategy semantics.

---

## 10. Indicator Presets

Presets are named, predefined parameter configurations for registered tools.

They allow users to apply commonly-used indicator configurations with a single click, without
manually entering parameter values.

### 10.1 Preset Definition

A preset is defined by:

| Field | Type | Description |
|---|---|---|
| `preset_id` | `str` | Stable identifier for this preset. Must not change after publication. |
| `name` | `str` | Human-readable label shown in the indicator picker. Example: `"EMA 20"`. |
| `tool_id` | `str` | The registered tool this preset configures. Must reference a `visible_on_chart: true` tool. |
| `parameters` | `dict` | The parameter values for this preset. Must conform to the tool's declared parameter schema. |

### 10.2 Built-In Platform Presets

| Preset Name | tool_id | Parameters |
|---|---|---|
| EMA 20 | `ema` | `{ period: 20 }` |
| EMA 50 | `ema` | `{ period: 50 }` |
| EMA 200 | `ema` | `{ period: 200 }` |
| SMA 20 | `sma` | `{ period: 20 }` |
| SMA 50 | `sma` | `{ period: 50 }` |
| SMA 200 | `sma` | `{ period: 200 }` |
| RSI 14 | `rsi` | `{ period: 14 }` |
| MACD Standard | `macd` | `{ fast_period: 12, slow_period: 26, signal_period: 9 }` |
| Bollinger 20,2 | `bollinger_bands` | `{ period: 20, num_std_dev: 2.0 }` |

### 10.3 Preset Rules

**Presets are convenience wrappers.** They pre-fill parameter values when an indicator is added
to the chart. They are not new tools, do not have separate computation logic, and do not bypass
the standard tool parameter schema.

**Presets do not create new tools.** Applying the "EMA 20" preset creates an instance of the
`ema` tool with `period=20`. The computation is identical to manually selecting EMA and entering
20 as the period.

**Parameters are modifiable after preset application.** The user may edit any editable parameter
after applying a preset. The preset only controls the initial values.

**Presets observe the same tool-type rule.** A preset may only reference a tool with
`tool_type: indicator` and `visible_on_chart: true`. Presets cannot be defined for non-indicator
tool types.

**Preset instance_ids.** When a preset is applied, the frontend creates an `instance_id` for the
resulting indicator instance. The preset does not own or persist the `instance_id`.

### 10.4 Future: User-Defined Presets

A future phase may allow users to save their own named configurations as custom presets.

User-defined presets follow the same structural rules as built-in presets. They are not a new
concept — only the source (user-defined vs. platform-defined) differs.

The governance for user-defined presets is deferred to the Chart-UX-3E promotion workflow (§18).

---

## 11. Parameter Editing Rules

### 11.1 User-Editable Parameters

The chart indicator panel must expose a parameter editor for any tool instance added to the chart.

The parameters exposed in the editor must come from the tool's `editable_parameters` list in the
visualization metadata.

The editor must render appropriate input controls based on the tool's declared parameter schema:

- integer period fields → numeric stepper with min/max constraints
- float multipliers → decimal input with step
- source field → dropdown of valid OHLCV source fields

### 11.2 Schema Alignment

The parameter names, types, and constraints used in the chart parameter editor must be identical
to those declared in the tool's parameter schema in the Tool Registry.

There must be no separate parameter model for chart indicators. The chart indicator parameter
editor is a rendering layer over the same parameter schema used by Strategy Builder.

Divergence between the chart parameter model and the Strategy Builder parameter model is an
architectural violation.

### 11.3 Parameter Change Behavior

When the user changes a parameter in the chart indicator panel:

1. The frontend sends a new indicator computation request to the backend with the same
   `instance_id` and updated parameters.
2. The backend recomputes the indicator series.
3. The frontend replaces the old series for that `instance_id` with the newly returned series.

Parameter changes must never trigger in-browser recomputation of indicator formulas.

---

## 12. Backend Computation Rule

The frontend is responsible for:

- rendering the indicator panel UI
- collecting user parameter inputs
- assigning and tracking `instance_id` values (§9)
- sending indicator requests to the backend
- routing indicator artifact responses to the correct chart instance by `instance_id`
- rendering the indicator series returned by the backend

The backend is responsible for:

- all official indicator computation
- validating parameters against the tool's declared schema
- returning normalized indicator artifact responses tagged with the echoed `instance_id`

### 12.1 Indicator Request Shape

When requesting an indicator computation, the frontend sends:

```
tool_id          — the registered tool identifier (e.g., "sma", "macd")
instance_id      — the chart-level stable identifier for this indicator instance (§9)
symbol           — the asset symbol matching the loaded chart data
timeframe        — the timeframe of the loaded chart data
provider         — the data provider resolving the chart data
date_range_start — start of the chart's visible data range
date_range_end   — end of the chart's visible data range
parameters       — the parameter values matching the tool's declared schema
```

The backend resolves the appropriate data, computes the indicator using the registered tool
dispatcher, and returns an indicator artifact response tagged with `instance_id` (§13).

### 12.2 Data Context Alignment

The indicator computation must use the same underlying OHLCV data that the chart is rendering.

The indicator request must carry enough identity context (symbol, timeframe, provider, date range)
for the backend to locate or fetch the correct normalized data.

The backend must not silently substitute different data or a different timeframe from what the
chart is displaying.

---

## 13. Indicator Artifact Response Contract

The backend indicator computation endpoint returns a normalized indicator artifact for each tool
instance request. The `instance_id` is always echoed in the response so the frontend can route
the artifact to the correct chart instance.

### 13.1 Conceptual Response Shape

```
tool_id            — the registered tool identifier
instance_id        — echoes the client-assigned instance identifier (§9)
display_name       — human-readable tool name from visualization metadata
pane               — "price_overlay" or "oscillator_pane"
render_type        — rendering hint from visualization metadata
parameters         — the parameter values used (echoed from request, after validation)
series             — list of named output series
  series_id        — matches the series_id in output_series metadata
  label            — human-readable series label
  render_type      — rendering hint for this specific series
  default_color    — color hint
  values           — ordered list of (timestamp, value) pairs
    timestamp      — UTC bar timestamp in ISO 8601 format
    value          — computed numeric value, or null for warmup bars
warmup_bars        — number of leading bars where value is null
diagnostics        — optional field for error context or computation warnings
```

### 13.2 Warmup and Null Behavior

Bars within the warmup period must return `null` values, not zero, and not be omitted.

The timestamp must still be included for warmup bars so the frontend can align the series
correctly with the chart's time axis.

The frontend must not render null values as zero. Null values indicate no computation was
performed for that bar.

The `warmup_bars` count in the response tells the frontend how many leading null values to expect,
so it can display an appropriate "warming up" annotation if desired.

### 13.3 Series Alignment

All output series within a single indicator artifact response must share the same timestamp
sequence.

The timestamp sequence must align with the OHLCV bar timestamps of the chart's loaded data.

A mismatch between indicator timestamps and chart bar timestamps is a backend error and must be
surfaced through the `diagnostics` field.

---

## 14. Future Custom Tool Onboarding

Every new tool registered in the Tool Registry must declare a `tool_type` (§4) and, if the tool
is chart-visible, a complete visualization metadata block (§6) and discovery metadata block (§7).

### 14.1 Declaration Requirements

The `tool_type` field is not optional. New tools that do not declare `tool_type` must be rejected
at registration time.

The `visible_on_chart` field is not optional. Tools that do not declare this field must be treated
as `visible_on_chart: false` by default.

Only tools with `tool_type: indicator` may declare `visible_on_chart: true`.

Tools that are chart-visible must provide:

- `tool_type: indicator`
- a complete visualization metadata block (§6)
- at least one named output series in `output_series`
- a warmup declaration consistent with the tool's computation logic
- a parameter schema aligned with the Strategy Builder parameter schema
- a complete discovery metadata block (§7)

### 14.2 Onboarding Checklist

When promoting a new tool to chart-visible status, all of the following must be completed:

**Tool-type and visibility:**
- [ ] Declare `tool_type: indicator` (§4)
- [ ] Declare `visible_on_chart: true`

**Visualization metadata (§6):**
- [ ] Assign chart rendering classification (§5): overlay / oscillator / multi-series / event / non-visual
- [ ] Assign `chart_pane` at the tool level
- [ ] Declare `render_type` and `series_kind`
- [ ] Declare `default_parameters` and `editable_parameters`
- [ ] Declare `output_series` list with all named series and `series_id` values
- [ ] Confirm `warmup_bars_required` matches computation logic
- [ ] Confirm `output_series[*].series_id` values match tool output references used in Strategy Builder
- [ ] Confirm backend dispatcher returns null for warmup bars

**Discovery metadata (§7):**
- [ ] Declare `category` from the approved category enumeration (§7.2)
- [ ] Declare `subcategory` if applicable
- [ ] Declare `search_keywords` including abbreviations and alternate names
- [ ] Declare `display_order` within category

**Instance and preset support (§9, §10):**
- [ ] Confirm multi-instance isolation: two instances with different parameters compute independently
- [ ] Register standard presets for commonly-used configurations if applicable (§10.2)

**Implementation phases:**
- [ ] Register tool in the backend indicator artifact endpoint (Chart-UX-3B)
- [ ] Confirm tool appears correctly in the indicator picker search results (Chart-UX-3C)

### 14.3 Non-Visual Indicator Tools

Tools with `tool_type: indicator` that produce outputs consumed only by downstream tools or
strategy conditions may declare `visible_on_chart: false`.

These tools are excluded from the chart indicator panel even though they are indicator-type tools.

They must still declare `tool_type: indicator` and may omit visualization and discovery metadata.

### 14.4 Non-Indicator Tools

Tools with `tool_type` values other than `indicator` (§4.2–§4.6) must never appear in the chart
indicator panel. They declare `visible_on_chart: false` by default and must not be permitted to
override this.

---

## 15. Experimental Indicator Promotion Lifecycle

QuantLab is a strategy research lab, not merely a charting platform. New indicators begin as
research artifacts and may graduate through a governed promotion path before becoming chart-visible
tools available to all users.

Not every research artifact becomes a registry tool.
Not every registry tool becomes chart-visible.

This lifecycle governs the path from experimental research to production chart indicator.

### 15.1 Promotion Path

```
Research Sandbox
      ↓  (researcher decides to formalize the indicator)
Experimental Indicator
      ↓  (computation validated against real data)
Validated Indicator
      ↓  (parameter schema stabilized, version assigned)
Registry Tool
      ↓  (visualization metadata declared, discovery metadata declared)
Chart-Visible Tool
      ↓  (same parameter schema used in both contexts)
Strategy Usage       ← also available in Strategy Builder
      ↓
Backtest / Forward Test / Paper Trading
```

### 15.2 Stage Definitions

**Research Sandbox**

A computation module exists in the codebase or a research notebook but is not registered in the
Tool Registry. It has no governance obligations, no version, no parameter schema declaration.

Research sandbox tools must not be used in strategy definitions or backtesting.

**Experimental Indicator**

The tool is registered in the Tool Registry with `tool_status: experimental`.

Experimental indicators:
- have a declared parameter schema
- declare `tool_type: indicator`
- declare `visible_on_chart: false` (experimental tools do not appear in the chart panel)
- may be used in research-mode strategy definitions
- must not be promoted to backtesting or production strategy definitions without validation
- are clearly labeled as experimental in all discovery responses

**Validated Indicator**

The tool has been tested against real data and its computation is confirmed.

Validated indicators:
- have confirmed warmup behavior
- have declared statefulness
- have documented computation against real datasets
- may declare `visible_on_chart: false` if they do not yet have visualization metadata
- are candidates for chart-visibility promotion

**Registry Tool**

The tool is stable and production-ready.

Registry tools:
- have a stable parameter schema with version assigned
- preserve compatibility within their major version
- may be used in backtesting, forward testing, and paper trading strategy definitions
- may declare `visible_on_chart: true` if visualization metadata is complete

**Chart-Visible Tool**

The tool has complete visualization metadata (§6) and discovery metadata (§7) and declares
`visible_on_chart: true`.

Chart-visible tools:
- appear in the indicator picker on the Chart page
- support user-editable parameters
- may be added as multiple simultaneous instances (§9)
- may have built-in presets registered (§10)
- are automatically available in Strategy Builder (same parameter schema)

**Strategy Usage**

Any tool that is chart-visible is also automatically available in Strategy Builder composition,
since both contexts use the same parameter schema and backend computation.

The transition from Chart-Visible Tool to Strategy Usage is automatic — it does not require a
separate promotion step.

**Backtest / Forward Test / Paper Trading**

Strategy definitions using the tool may be promoted through the strategy lifecycle. The strategy
lifecycle is governed by `docs/STRATEGY_PROMOTION_LIFECYCLE.md`.

### 15.3 Promotion Gates

| Transition | Gate |
|---|---|
| Research Sandbox → Experimental | Registered in Tool Registry with `tool_type: indicator` and `tool_status: experimental` |
| Experimental → Validated | Computation confirmed against real data; warmup declared; statefulness declared |
| Validated → Registry Tool | Parameter schema stable; version assigned; no outstanding behavioral issues; reproducibility confirmed |
| Registry Tool → Chart-Visible | `visible_on_chart: true`; visualization metadata complete (§6); discovery metadata complete (§7); computation consistency test passing; multi-instance isolation confirmed |

### 15.4 Governance Expectations

An experimental indicator must not silently become chart-visible without completing the full
promotion path and passing the §15.3 gates.

Promotion from Registry Tool to Chart-Visible must be explicitly declared by updating the tool's
metadata — it is not automatic.

Demotion (reversing a stage) is not a standard operation. If a chart-visible tool is found to
have computational errors, it must be deprecated in the registry and a corrected version promoted
through the path again. Silently downgrading `visible_on_chart` to false without a deprecation
record is not acceptable governance.

---

## 16. Forbidden Patterns

The following patterns are architectural violations and are explicitly prohibited.

### 16.1 Frontend-Only Official Indicator Computation

**Forbidden:** Implementing EMA, RSI, MACD, or any other official indicator formula in
TypeScript/JavaScript inside the frontend.

**Why:** Guarantees computational divergence from the backend. A user would see different indicator
values on the chart than the values used during backtesting.

**Permitted exception:** Client-side preview or animation effects that use approximate
visualization only — provided the authoritative computation is still fetched from the backend and
overwrites the preview.

### 16.2 Duplicate Formulas Between Frontend and Backend

**Forbidden:** Maintaining two implementations of the same indicator formula — one in Python for
backtesting and one in TypeScript for chart rendering.

**Why:** Formula drift is guaranteed over time. The two implementations will diverge as parameters
or edge cases are handled differently.

### 16.3 Hardcoded Tool-Specific Chart Rendering

**Forbidden:** Writing chart rendering code that checks for specific tool identities (e.g.,
`if tool_id === "rsi" then render in oscillator pane`).

**Why:** Violates the principle that the frontend renders based on artifact type declarations, not
tool identity knowledge. Adding a new tool must not require frontend code changes.

### 16.4 Missing `tool_type` and `visible_on_chart` Declarations

**Forbidden:** Registering a tool as stable and usable in Strategy Builder while omitting the
`tool_type` or `visible_on_chart` declarations.

**Why:** Creates invisible tool classes with no governance over chart visibility eligibility or
tool-type responsibilities.

### 16.5 Chart Indicators Bypassing Normalized Data

**Forbidden:** Computing chart indicator values from un-normalized provider data rather than the
same normalized OHLCV pipeline used by Strategy Builder and backtesting.

**Why:** Breaks the data abstraction contract. Chart rendering must use the same data pipeline as
all other consumers.

### 16.6 Strategy-Identity-Aware Frontend Rendering

**Forbidden:** Rendering chart indicators in a way that hard-codes awareness of specific strategy
identities or strategy drafts in the Chart page component.

**Why:** The Chart page must remain a generic visualization consumer. It renders indicator
artifacts returned by the backend — it does not know or care which strategy is being built.

### 16.7 Making Non-Indicator Tools Chart-Visible

**Forbidden:** Setting `visible_on_chart: true` on a tool with `tool_type` other than `indicator`
(i.e., `strategy_helper`, `risk_helper`, `portfolio_helper`, `execution_helper`,
`analysis_helper`) without an explicit governance decision and a revision to this contract.

**Why:** Risk helpers, execution helpers, and portfolio helpers are not designed to produce
standalone chart visualization artifacts. Allowing them to be chart-visible without governance
risks presenting execution-layer or risk-layer internal values as chart indicators, confusing
users and breaking the architectural separation between analytical indicators and operational
helpers.

### 16.8 Hardcoding the Indicator Picker UI

**Forbidden:** Building the chart indicator picker as a hardcoded list of tool names, categories,
or orderings in the frontend code rather than as a metadata-driven discovery response from the
backend.

**Why:** Every new tool would require a frontend deployment to appear in the picker. New tools
must appear automatically when registered with complete metadata. Hardcoded pickers also break
when tools are deprecated or renamed.

---

## 17. Testing Expectations

Future implementation phases must provide tests covering the following areas.

### 17.1 Metadata Registration Tests

- Each chart-visible tool declares `tool_type: indicator`
- Each chart-visible tool declares `visible_on_chart: true`
- Each chart-visible tool declares at least one named output series
- `warmup_bars_required` value in metadata matches the tool's actual warmup computation behavior
- `output_series[*].series_id` values match the output reference identifiers used in strategy
  semantics

### 17.2 Parameter Schema Mapping Tests

- Parameters exposed in `editable_parameters` are a subset of the tool's declared parameter schema
- Sending a parameter value outside the declared constraints returns a validation error from the
  backend
- Chart indicator parameter names are identical to Strategy Builder parameter names for the same
  tool

### 17.3 Backend Computation Consistency Tests

- Indicator values returned by the chart artifact endpoint match values produced by the historical
  computation pipeline for the same symbol, timeframe, date range, and parameters
- This is the critical consistency test: chart and backtest must produce identical values

### 17.4 Chart Artifact Rendering Tests

- Each output series in the artifact response renders in the correct pane (overlay vs. oscillator)
- Warmup bars render as null gaps, not as zero values
- Multi-series tools render all declared series independently

### 17.5 Warmup and Null Behavior Tests

- Warmup bars return null values in the artifact response
- `warmup_bars` count in the response matches the tool's declared `warmup_bars_required`
- Frontend does not render null as zero

### 17.6 Overlay vs Pane Classification Tests

- SMA, EMA, and Bollinger Band series appear in the price overlay pane
- RSI, MACD, and ATR series appear in the oscillator pane
- A newly registered overlay tool automatically appears in the price overlay pane based on its
  metadata declaration

### 17.7 Tool-Type Taxonomy Tests

- Every registered tool declares a `tool_type` field
- Only tools with `tool_type: indicator` may have `visible_on_chart: true`
- Tools with `tool_type` in {`strategy_helper`, `risk_helper`, `portfolio_helper`,
  `execution_helper`, `analysis_helper`} have `visible_on_chart: false` and cannot override it
- Backend metadata validation rejects `visible_on_chart: true` on non-indicator tool types

### 17.8 Discovery Metadata Tests

- Every chart-visible tool declares `category`, `search_keywords`, and `display_order`
- The indicator picker response includes all chart-visible tools grouped by category
- Searching by a keyword returns tools whose `search_keywords` include that term
- `display_order` governs sort order within a category group
- A tool with a lower `display_order` value appears before one with a higher value in the same
  category

### 17.9 Multiple Instance Tests

- Two instances of the same tool with different parameters return independent series
- `instance_id` is echoed in each artifact response
- Changing parameters on one instance does not affect the response for another instance
- The chart can render EMA-20, EMA-50, and EMA-200 simultaneously as three independent series
- Removing one instance does not affect computation for remaining instances

### 17.10 Preset Tests

- Each defined preset has a valid `tool_id` referencing a registered chart-visible tool
- Applying a preset pre-fills the correct parameter values
- Preset parameters are modifiable after application
- No preset creates computation logic separate from the underlying tool
- Preset-created instances behave identically to manually-created instances with the same
  parameters

---

## 18. Phased Roadmap

### Phase Chart-UX-3B — Backend Indicator Artifact Endpoint

**Scope:**
- Define `IndicatorArtifactRequest` and `IndicatorArtifactResponse` schemas including `instance_id`
- Implement `POST /chart/indicator-artifact` (or equivalent route)
- Route accepts `tool_id`, `instance_id`, `symbol`, `timeframe`, `provider`, `date_range`,
  `parameters`
- Backend fetches/resolves OHLCV data using the existing OHLCVService
- Backend dispatches to existing tool dispatcher (`_TOOL_DISPATCHERS`) to compute the series
- Backend returns normalized indicator artifact response matching §13 with echoed `instance_id`
- Backend enforces `visible_on_chart: true` and `tool_type: indicator` before dispatching
- Auth: `require_active_subscription`
- Warmup bars return null values in the series
- Define `GET /chart/indicators` endpoint returning all chart-visible tools with full metadata
  (visualization + discovery) for the indicator picker
- No frontend changes in this phase

**Deliverables:** Backend route, schemas, service function, indicator list endpoint, unit tests

### Phase Chart-UX-3C — Frontend Indicator Panel and Parameter Editor

**Scope:**
- Implement chart indicator picker driven by `GET /chart/indicators` metadata response
- Category-based grouping and keyword search (all metadata-driven, no hardcoding)
- Implement per-tool parameter editor driven by tool metadata
- Implement indicator artifact fetch on tool add or parameter change
- Support multiple simultaneous instances of the same tool (§9)
- Assign stable `instance_id` values per instance
- Implement overlay rendering for price-pane indicators
- Implement oscillator pane rendering for non-price indicators
- Render warmup null gaps correctly (not as zero)
- Display built-in presets (§10) in the indicator picker for quick application
- No in-browser indicator computation

**Deliverables:** Chart indicator panel component, parameter editor component, preset picker,
multi-instance rendering, overlay and oscillator pane rendering, frontend tests

### Phase Chart-UX-3D — Onboard Existing Tools

**Scope:**
- Add `tool_type: indicator`, `visible_on_chart: true`, full visualization metadata (§6), and
  full discovery metadata (§7) to: `sma`, `ema`, `rsi`, `macd`, `bollinger_bands`, `atr`
- Register built-in presets for all six tools (§10.2)
- Ensure `output_series` declarations match existing Strategy Builder output references
- Confirm backend computation consistency tests pass for all six tools (§17.3)
- Wire Bollinger Bands 3-series overlay rendering (upper, middle, lower)
- Wire MACD 3-series oscillator rendering (MACD line, signal line, histogram)

**Deliverables:** Updated tool metadata for six tools, backend consistency tests, frontend
rendering tests, preset registration

### Phase Chart-UX-3E — Custom Indicator Promotion Workflow

**Scope:**
- Define the promotion checklist UI for registering new tools as chart-visible
- Implement backend validation enforcing `tool_type: indicator` gate for `visible_on_chart: true`
- Implement backend validation that a chart-visible tool has complete visualization metadata
- Implement backend validation that `output_series` `series_id` values match tool output
  references in the strategy semantics layer
- Create developer documentation for the full indicator onboarding checklist (§14.2)
- Define admin or developer endpoint to inspect tool chart-visibility status
- Define governance workflow for the experimental promotion lifecycle (§15)

**Deliverables:** Promotion workflow documentation, backend metadata validation, developer guide,
lifecycle governance documentation

---

## 19. Architectural Alignment

This contract is explicitly aligned with the following QuantLab architecture principles.

### 19.1 Frontend is Visualization and Interaction Only

The frontend may collect user parameters, display indicator series, manage chart pane layout,
assign `instance_id` values, and render preset options.

The frontend must not compute official indicator values.

Source: `agent/ARCHITECTURE_GUARDRAILS.md §9` — frontend must not contain official strategy
calculation logic or signal generation logic.

### 19.2 Backend Owns Official Computation

All indicator computations are authoritative only when performed by the backend using registered
tool dispatchers.

The backend is the single source of truth for indicator output values used in any consumer
context — Chart page, Strategy Builder, backtesting, forward testing, or paper trading.

Source: `agent/ARCHITECTURE_GUARDRAILS.md §9` — any calculation required for official strategy
evaluation must be performed in the backend or strategy engine, not only in the browser.

### 19.3 Strategies Remain Portable

The indicator parameters used on the Chart page are the same parameters available in Strategy
Builder.

No chart-specific parameter model is introduced.

Changing a tool's parameter schema is a versioning event that affects all consumers equally.

Source: `agent/ARCHITECTURE_GUARDRAILS.md §3, §4` — strategies must remain portable across all
runtime modes without rewriting strategy logic.

### 19.4 Tools Are Reusable Across All Lifecycle Modes

The same tool that is visualized on the Chart page is used in backtesting, forward testing, and
paper trading.

No tool behavior changes based on which consumer is requesting the computation.

The `instance_id` model (§9) is consistent with the `ToolConfiguration.instance_id` model already
used in strategy definitions and historical computation.

Source: `agent/ARCHITECTURE_GUARDRAILS.md §27` — all analytical tools must be reusable across
multiple strategies, portable across all runtime modes, and behave consistently across modes.

### 19.5 Data Must Remain Normalized

Indicator computations use normalized OHLCV data flowing through the standard data pipeline.

No provider-specific data schema may reach the indicator computation layer.

Source: `agent/ARCHITECTURE_GUARDRAILS.md §5, §6` — all market data must pass through
normalization before being used by strategies or tools.

---

## 20. Existing Code Alignment Notes

The following observations identify areas in the current codebase that may need future alignment
when Chart-UX-3B through 3E are implemented. These are not blockers for this contract phase.

**`frontend/src/components/Chart.tsx`**
Currently renders overlay series returned by the composition-run endpoint. The indicator panel
implementation (Chart-UX-3C) must extend or refactor this component to accept indicator artifact
series from the new endpoint without breaking the existing composition-run overlay behavior. The
`instance_id` routing model (§9) must be integrated into the overlay lifecycle management.

**`frontend/src/types/toolVisualization.ts`**
Exists from Phase R8 legacy cleanup. This file's current typings were narrowed to the
composition-run response contract. The chart indicator artifact types defined in Chart-UX-3B
should either extend or replace these types — the decision belongs to the Chart-UX-3B/3C
implementation phase.

**`backend/tools/historical_computation.py` — `_TOOL_DISPATCHERS`**
The existing dispatcher dict is the correct integration point for the backend indicator artifact
endpoint. The Chart-UX-3B backend route must call into the same dispatcher rather than
duplicating computation logic. The dispatcher currently does not enforce `tool_type` — this
enforcement belongs at the route/service level.

**`backend/tools/__init__.py` — `create_default_registry()`**
When `tool_type`, `visible_on_chart`, visualization metadata, and discovery metadata fields are
added to tool registrations in Chart-UX-3D, this factory function must be updated. All six
existing tools must receive their complete metadata blocks.

**Bollinger Bands backend**
Bollinger Bands computation is already complete in the backend. The 3-series overlay
visualization is not yet wired to the frontend chart. Chart-UX-3D is the phase that wires this
rendering path.

**`backend/api/routes/`**
No `/chart/` route prefix currently exists. Chart-UX-3B will need to register a new router. The
route prefix and naming are implementation decisions for that phase.

**`backend/tools/` — missing `tool_type` field**
The current tool metadata structures (e.g., `EMA_METADATA` in `backend/tools/ema.py`) do not yet
include a `tool_type` field. Chart-UX-3D must add `tool_type: indicator` to all six existing
tool metadata objects.

# FORWARD_TESTING_ARCHITECTURE.md

## Purpose

This document defines the architecture of the Forward Testing subsystem for QuantLab.

Forward testing is the first execution mode beyond backtesting. It is the mechanism by which a validated strategy is evaluated against market data it has never seen — bars that arrive after the strategy is activated — with the sole purpose of observing whether the strategy generates signals in real market conditions.

This document:

* defines what forward testing is and is not
* establishes the session architecture
* defines the polling-based data acquisition model appropriate to QuantLab's current provider infrastructure
* defines the bar finalization and unseen-bar detection model
* defines the signal recording contract
* defines ownership, persistence, provenance, and audit requirements
* defines the failure model
* establishes the upgrade path from polling to streaming when provider infrastructure allows

This document is architecture-level.

It extends `docs/EXECUTION_CONTRACT.md` and is subordinate to it.

All invariants defined in the Execution Contract apply in full. This document elaborates the forward-testing-specific architecture on top of those invariants.

No implementation. No scheduler code. No database schema. No API routes. No WebSocket protocol. Architecture only.

---

## Why This Document Exists

Backtesting generates historical evidence under controlled, deterministic conditions. It cannot answer whether a strategy will behave as expected when confronted with conditions it has never encountered: live market regimes, real data gaps, unexpected price action, intraday volatility patterns that differ from historical norms.

Forward testing bridges that gap. It exposes the strategy to real market conditions without financial risk, without position management, and without the complexity of a simulated brokerage account.

Without a formal architecture, a forward testing implementation risks:

* blurring the line between signal observation and execution, leading to unintended fills or position tracking
* inventing custom strategy evaluation logic instead of reusing the existing evaluation engine
* producing signal records without sufficient provenance for later promotion review
* building a polling model that cannot be upgraded to streaming without rewriting strategy logic
* creating sessions without ownership, making audit and promotion review impossible

This document prevents those failures.

---

## 1. Purpose of Forward Testing

### Why Forward Testing Exists

Backtesting answers: "Did this strategy work on historical data?"

Forward testing answers: "Does this strategy generate signals as expected in live market conditions?"

These are different questions. Backtesting operates on a fixed, immutable dataset that is fully available before the first bar is evaluated. The strategy processes bars it has "already seen" in the sense that the data exists at computation time.

Forward testing operates on bars that do not exist when the session is activated. Each new bar is genuinely future data relative to the moment the strategy was started. The strategy encounters actual market regime shifts, volatility changes, and data provider behavior in real time.

### Why Backtesting Alone Is Insufficient

Backtesting cannot reveal several classes of strategy failure that forward testing can detect:

**Regime sensitivity**: A strategy that performed well in a historical trending regime may generate excessive noise signals in a ranging regime that the historical dataset did not represent. Forward testing exposes this in real time.

**Data provider behavior**: Historical provider data is clean, gap-filled, and delivery-ordered. Live provider data has latency variation, occasional delayed bars, momentary gaps, and provider-specific quirks. A strategy that assumes clean data may behave unexpectedly when confronted with real feed behavior.

**Warmup quality in real deployment**: The warmup period in backtesting is always satisfied because the full dataset exists. In forward testing, the warmup must be satisfied by a combination of recent historical bars fetched at session activation plus subsequent live bars. Feature values during early live bars may differ from what backtesting computed.

**Signal frequency calibration**: A strategy that generated 3 signals per week historically may generate 0 or 10 signals per week under current market conditions. Forward testing reveals this before capital is committed.

**Strategy stability**: A strategy whose rule thresholds are borderline may fire unpredictably in volatile live conditions. Forward testing surfaces this instability without financial consequence.

### What Risks Forward Testing Reduces

Forward testing reduces — but does not eliminate — the following risks when advancing to paper trading or live trading:

* Deploying a strategy into a market regime it cannot handle
* Committing to a paper trading session with a strategy that immediately generates pathological signal patterns
* Approving a strategy for live trading based solely on historical evidence
* Discovering data provider issues for the first time during a paper trading session

Forward testing is not a guarantee of future performance. It is a controlled observation window between historical evidence and financial commitment.

---

## 2. What Forward Testing Is Not

Forward testing is signal observation only.

The following are architectural exclusions. Implementations exhibiting any of these behaviors are violations.

| Not this | Why it is excluded |
|---|---|
| Paper trading | Paper trading maintains a simulated brokerage account with positions, fills, fees, and equity. Forward testing has none of these. |
| Broker simulation | There is no simulated broker in forward testing. No order routing, no fill modeling, no order state machine. |
| Live trading | No real orders are placed. No broker credentials are used. No real account is affected. |
| Account management | There is no account. No cash balance. No equity. No exposure. |
| Position management | There are no positions. No entry prices. No unrealized P&L. No position sizing. |
| Fill simulation | There are no fills. A signal does not become a trade. |
| P&L tracking | There is no P&L of any kind — realized, unrealized, or hypothetical. |
| A second backtester | Forward testing does not evaluate the strategy against historical bars. It evaluates only bars that arrived after session activation. |
| A strategy test harness | Forward testing is not a development or debugging tool. It is a governance stage in the strategy promotion lifecycle. |

**The single output of a forward testing session is a record of which signals fired, when, and under what conditions.**

Everything else — fills, positions, equity, P&L — belongs to paper trading and must not be implemented in the forward testing subsystem.

---

## 3. Forward Testing Philosophy

Forward testing validates strategy behavior. It does not validate strategy profitability.

Profitability validation is the responsibility of the backtesting and paper trading stages. Forward testing asks a different set of questions:

**Signal quality**: Do the signals that fire make analytical sense given the market conditions at the time they fire? Are entries firing at the beginning of moves or in the middle of noise? Are exits firing near the end of moves or prematurely?

**Signal stability**: Is the signal frequency consistent with what the strategy's rule structure would predict? Are there unexpected clusters of signals (possible indicator sensitivity to current volatility) or unexpected silences (possible indicator regime mismatch)?

**Market regime behavior**: How does the strategy behave during trending periods versus ranging periods? During high-volatility versus low-volatility conditions? Forward testing exposes regime behavior that historical data may not have fully represented.

**Strategy robustness**: Does the strategy evaluate its rules consistently bar by bar? Are there evaluation failures, feature unavailability events, or rule conditions that produce unexpected outcomes?

**Warmup integrity**: Are the first N bars of the session (where N is the strategy's warmup requirement) correctly excluded from signal generation? Are feature values stabilizing as expected as the live window grows?

A forward testing session that generates no signals during a particular market period is not necessarily a failure. It may be a valid observation: the strategy's entry conditions were not met during that period. The absence of signals is itself a meaningful data point.

A forward testing session that generates constant signals may indicate overfitting or indicator sensitivity — also a valid and important observation.

The goal of forward testing is not to produce a P&L. The goal is to accumulate enough signal history to understand how the strategy behaves under live market conditions before committing to paper trading.

---

## 4. Forward Test Session

A `ForwardTestSession` is the durable, ownership-scoped container for all activity in a single forward testing activation.

### Conceptual Fields

**`session_id`**
A unique, stable identifier for this session. Assigned at session creation. Never reused. UUID format required.

**`user_id`**
The owner of this session. Derived from the authenticated user's JWT at session creation. Never accepted from client-supplied payload. Never transferred.

**`strategy_snapshot`**
A complete, immutable copy of the strategy definition as it existed at the moment of session activation. This includes the full tool configuration, rule definitions, semantic structure, parameter set, and lifecycle status.

The snapshot is captured at activation time and sealed. Subsequent changes to the underlying `StrategyDraft` must not affect the active session. The session evaluates the strategy that was activated, not whatever the strategy happens to be now.

**`strategy_version`**
A version identifier derived from the strategy snapshot — either the explicit version from the draft or a hash of the snapshot content. Used for provenance in signal records and audit.

**`lifecycle_status_at_activation`**
The `StrategyLifecycleStatus` of the underlying draft at the moment of activation. Recorded for promotion review. Forward testing requires `lifecycle_status >= validated`; this field records what was actually observed.

**`source_mode`**
`provider` or `catalog`. Determines which data acquisition path is used.

**`provider_name`**
The data provider (e.g., `yahoo`, `polygon`). Populated when `source_mode = provider`. Null when `source_mode = catalog`.

**`catalog_id`**
The catalog entry identity when `source_mode = catalog`. Null when `source_mode = provider`. `file_path` must never appear in session records.

**`symbol`**
The trading symbol being evaluated (e.g., `AAPL`, `BTC-USD`).

**`timeframe`**
The bar timeframe being evaluated (e.g., `1d`, `1h`, `15m`).

**`activation_timestamp`**
The UTC timestamp at which the session was activated and began processing live bars. Distinct from `created_timestamp` — a session may be created but not yet activated.

**`last_processed_bar_timestamp`**
The timestamp of the most recently completed bar that was submitted to the strategy evaluator. Used for unseen-bar detection on the next poll cycle. Null before the first bar is processed.

**`warmup_bars_required`**
The warmup requirement derived from the strategy snapshot at activation time. Determines how many initial bars are ineligible for signal generation.

**`status`**
The current lifecycle status of the session. See §5 for the state machine.

**`error_detail`**
A structured error record if the session entered the `failed` state. Empty or null otherwise. Must not contain raw provider error messages, file paths, API keys, or internal stack traces.

**`created_timestamp`**
UTC timestamp when the session record was first created.

**`updated_timestamp`**
UTC timestamp of the most recent state change or signal recorded.

### What Is NOT in the Session Record

The following must never appear in a `ForwardTestSession` record or any artifact associated with it:

* `file_path` — the catalog ID is the sole durable dataset identity
* `encrypted_secret` — vault credentials used for provider authentication are never stored in session records
* Decrypted credential values
* Raw provider API error messages that might contain internal paths or key hints
* Any fill, position, equity, or P&L fields

---

## 5. Session Lifecycle

### States

```
created
    → pending         (session record created; strategy and source configured; not yet activated)
    → running         (actively polling for new bars and evaluating the strategy)
    → paused          (user-requested pause; polling suspended; session record intact)
    → completed       (session reached natural end or user stopped it gracefully)
    → failed          (session entered an unrecoverable error state)
    → terminated      (session was forcibly terminated by user or administrative action)
```

### Allowed Transitions

| From | To | Trigger |
|---|---|---|
| `pending` | `running` | User activates the session |
| `running` | `paused` | User pauses the session |
| `running` | `completed` | User stops the session gracefully |
| `running` | `failed` | Unrecoverable error (strategy eval failure, persistent provider failure, session corruption) |
| `running` | `terminated` | Administrative termination |
| `paused` | `running` | User resumes the session |
| `paused` | `completed` | User stops the session from paused state |
| `paused` | `terminated` | Administrative termination |

### Invalid Transitions

| From | To | Why Prohibited |
|---|---|---|
| `completed` | `running` | Completed sessions are read-only. A new session must be created. |
| `completed` | `paused` | Same as above. |
| `failed` | `running` | Failed sessions require investigation. A new session must be created after the issue is resolved. |
| `failed` | `paused` | Failed sessions are read-only. |
| `terminated` | Any | Terminated sessions are terminal. |
| `pending` | `paused` | A session that has never run cannot be paused. |
| `pending` | `completed` | A session that has never run cannot be completed without activation. |

### Transition Audit

Every state transition must produce an audit event with:
* Session identity
* Previous state
* New state
* Actor (user ID or system identifier)
* UTC timestamp of transition
* Reason (for `failed` and `terminated` transitions)

No silent state mutations are permitted.

---

## 6. Data Acquisition Model

### Current QuantLab Provider Reality

QuantLab's provider infrastructure is REST-polling-based.

| Provider | Access Model | Streaming |
|---|---|---|
| Yahoo Finance | REST API (via yfinance adapter) | No |
| Polygon.io | REST API | Not yet used |
| Local CSV | File read | No |
| Local Parquet | File read | No |

There is no WebSocket feed. There is no tick-to-candle aggregation pipeline. There is no push-based bar delivery mechanism.

The forward testing data acquisition model is therefore a **scheduled polling architecture**. This is the correct model for QuantLab's current infrastructure. It is not a compromise — it is the appropriate design for REST-based providers. The document defines the upgrade path to streaming in §15.

### Polling-Based Architecture

The forward testing subsystem periodically polls the configured provider for new bar data.

The polling interval is determined by the session's declared timeframe:

| Timeframe | Minimum Polling Interval |
|---|---|
| `1d` (daily) | Once per day, after daily bar close |
| `1h` (hourly) | Once per hour, after hourly bar close |
| `15m` | Once per 15 minutes, after bar close |
| `5m` | Once per 5 minutes, after bar close |
| `1m` | Once per minute, after bar close |

Polling more frequently than the timeframe interval is wasteful and must be avoided. A daily bar is not available before the trading session closes; polling every 5 minutes for daily data serves no purpose.

Polling should incorporate a reasonable buffer after bar close to account for provider data lag. For example, for a 1-day timeframe, polling at market close plus a configurable buffer (e.g., 30 minutes) reduces the probability of receiving a partially-constructed or delayed bar.

The configurable polling delay is a session-level parameter recorded in session provenance.

### Latest Completed Candle Model

The forward testing subsystem operates on **completed bars only**.

A bar is completed when its timestamp period has fully elapsed. For a daily bar timestamped 2025-03-15, the bar is completed at the end of the trading day on 2025-03-15 according to the market's session close time.

The subsystem must never evaluate a bar that is still forming. An in-progress candle is not a complete bar. Evaluating an in-progress candle introduces a form of forward bias: the signal may fire on a partially-formed bar and then be invalidated when the bar closes at a different price.

**The forward testing subsystem must fetch only completed bars and must not evaluate the current (forming) bar.**

Implementation guidance (conceptual): when polling a provider, the request should specify a date range ending at or before the most recently confirmed completed bar. The most recently confirmed completed bar is determined by the current wall clock time relative to the timeframe's bar schedule. For a 1-hour bar, at 14:30 UTC, the most recently completed bar is the 13:00–14:00 bar. The 14:00–15:00 bar is currently forming.

### Unseen-Bar Detection

The subsystem must detect and process only bars that have not been previously evaluated.

The `last_processed_bar_timestamp` field in the session record is the canonical cursor. It records the timestamp of the most recently evaluated bar.

On each poll cycle:
1. Fetch bars from the provider for the declared symbol and timeframe
2. Filter to include only bars whose timestamp is strictly after `last_processed_bar_timestamp`
3. Verify that each candidate bar is a completed bar (its period has elapsed)
4. Process qualifying bars in ascending timestamp order (oldest first)
5. Update `last_processed_bar_timestamp` after each bar is successfully evaluated

If `last_processed_bar_timestamp` is null (first poll cycle), the subsystem must establish an initial cursor. The initial cursor strategy is:

* Fetch the N most recent completed bars, where N satisfies the strategy's warmup requirement plus a small buffer
* Use these bars to satisfy warmup (they are historical bars used for feature computation context, not for signal generation)
* Record the timestamp of the oldest bar in this initial set as the start of the warmup window
* Signal generation begins only after warmup_bars_required bars have been processed

The initial historical bars fetched to satisfy warmup are not "forward test bars" in the signal-generation sense. They are context bars. This distinction must be recorded in the session record.

### Duplicate Bar Handling

A duplicate bar is a bar that has already been evaluated — one whose timestamp is equal to or earlier than `last_processed_bar_timestamp`.

Duplicate bars must be silently discarded. They must not be re-evaluated.

Duplicate bars arise from:
* Provider returning bars that include the last known bar in their response
* A poll cycle that executes shortly after a previous cycle (timing overlap)
* Session resume after pause, where the last processed bar is still in the provider's recent data window

Duplicate detection is performed by comparing bar timestamps to `last_processed_bar_timestamp`. This is a strict equality and ordering check on timestamps. A bar with the same timestamp as a previously evaluated bar is a duplicate regardless of whether its price data is identical or differs (data revisions are handled separately — see Gap Handling).

### Gap Handling

A gap is a missing bar: a bar whose timestamp would be expected given the timeframe schedule, but which is absent from the provider response.

Expected causes of gaps:
* Market holidays (daily bars)
* Trading halts
* Provider data delivery lag
* Low-liquidity symbols with genuinely absent bars

Gap handling strategy for forward testing:

**Acknowledge and continue**: When a gap is detected (expected bar timestamp is absent from provider response), the session records a gap event with the expected timestamp, the actual bar timestamps received around the gap, and the provider that was queried. Evaluation continues with the next available bar. The session does not fail due to a data gap.

**Do not forward-fill**: Forward testing must not invent bars to fill gaps. If a bar is missing, it is missing. Feature computation for bars following a gap must account for the absent bar by resetting or suppressing feature computation where the gap would cause incorrect feature values (e.g., a moving average over a window that includes the gap period may produce unreliable values).

**Gap events are recorded**: Every detected gap is recorded as a session event with timestamp, expected bar identity, and discovery timestamp. These gap events are available for audit and for later analysis of session quality.

**Warmup extension**: If gaps occur during the warmup phase, the warmup requirement must be extended to account for the missing bars. Warmup is measured in valid, complete bars — not in calendar periods.

### Provider Failure Handling

A provider failure is a poll cycle that returns an error (network error, authentication error, rate limit, provider maintenance) or returns no data for a symbol that is expected to have data.

Provider failures must not cause session termination. They must be handled as follows:

**Transient failure (short-duration)**: Record the failure event with timestamp and error category. Skip the current poll cycle. Retry on the next scheduled cycle. No signal generation occurs during a failed poll cycle. The session remains in `running` state.

**Persistent failure (multiple consecutive failures over a declared threshold)**: Record the persistent failure event. Transition the session to `paused` state. Notify the user through the platform's session status interface. The user may resume the session once the provider issue is resolved.

**Unrecoverable failure**: If the session cannot be restored (e.g., the strategy snapshot is corrupted, the source catalog entry has been removed), transition to `failed` state with a structured error record.

Provider error messages must be sanitized before being stored in session records or returned in API responses. Raw provider error text may contain internal details that must not be surfaced. Error records must contain the error category, not the raw provider message.

---

## 7. Evaluation Model

### Reuse of Existing Engine Components

Forward testing must not implement a custom strategy evaluation engine.

Forward testing reuses the existing QuantLab strategy evaluation infrastructure:

* **Tool computation**: the existing tool registry and `_TOOL_DISPATCHERS` infrastructure computes features for each bar
* **Semantic evaluator**: the existing `evaluate_history` / bar-by-bar evaluation path evaluates strategy rules against computed features
* **Readiness validation**: the existing warmup enforcement prevents signals from being generated before the feature computation window is satisfied
* **Dependency resolution**: the existing tool dependency graph resolution determines computation order

The only differences between forward testing evaluation and backtesting evaluation:

| Aspect | Backtesting | Forward Testing |
|---|---|---|
| Bar source | Fixed historical dataset | Live bars from polling |
| Bar delivery | Full window delivered at run start | One or few bars delivered per poll cycle |
| Determinism | Fully deterministic | Non-deterministic (live data) |
| Output | Full result artifact + equity curve | Signal records only |
| Accumulation | All bars processed in one run | Bar window grows over session lifetime |

### Per-Bar Processing Model

For each new bar received from a poll cycle, the forward testing evaluator:

1. Appends the new bar to the session's accumulated bar window
2. Checks whether warmup is satisfied (accumulated bars >= `warmup_bars_required`)
3. If warmup is not satisfied: records the bar as a warmup bar; no signal evaluation; updates `last_processed_bar_timestamp`
4. If warmup is satisfied: executes tool computation for the new bar (using the accumulated window for lookback); evaluates strategy rules; if a rule fires, records a `ForwardTestSignal`; updates `last_processed_bar_timestamp`

This model treats the session's accumulated bar window as a growing historical dataset. Each new bar is appended to the right end of the window. Feature computation always uses the complete window up to and including the current bar.

### Strategy Portability Invariant

The strategy definition evaluated in forward testing must be identical to the strategy definition used in backtesting.

The forward testing evaluator must not introduce:
* Custom signal suppression not in the strategy definition
* Position-awareness (filtering signals based on hypothetical position state)
* Any fill-related logic
* Any account-awareness

The strategy runs in exactly the same way it runs in backtesting, except that bars arrive one at a time from a live source rather than all at once from a historical dataset.

A strategy that cannot run in forward testing without modification is a violation of the portability invariant.

### Warmup at Session Start

When a forward test session is activated for the first time, the strategy requires warmup bars before reliable feature computation is possible.

The warmup strategy at session start:

1. Fetch the N most recent completed historical bars from the provider, where N = `warmup_bars_required + warmup_buffer`
2. `warmup_buffer` is a session-level parameter (default: 20% of `warmup_bars_required`) providing resilience against gaps in recent historical data
3. Process these initial historical bars through the evaluation pipeline in ascending timestamp order
4. Mark each as a warmup bar; no signals are generated
5. Once the warmup requirement is satisfied, begin signal-eligible evaluation with the next new bar

The warmup bars are fetched once at session activation. They are recorded in the session's provenance as "initial warmup context bars" with the timestamp range covered.

When a session resumes from a `paused` state, the warmup context is already satisfied by the accumulated bar window. No additional warmup fetching is required at resume time.

---

## 8. Signal Recording Model

### ForwardTestSignal

A `ForwardTestSignal` is the primary output of forward testing. It records that a strategy's rule logic evaluated to true at a specific bar in a live session.

### Conceptual Fields

**`signal_id`**
A unique, stable identifier for this signal record. UUID format. Assigned at signal recording time.

**`session_id`**
The `ForwardTestSession` that produced this signal.

**`signal_timestamp`**
The UTC timestamp at which this signal record was created (wall clock time of the evaluator processing this bar).

**`bar_timestamp`**
The timestamp of the bar that caused the strategy rule to fire. This is the market data timestamp, not the wall clock time.

**`bar_open`**, **`bar_high`**, **`bar_low`**, **`bar_close`**, **`bar_volume`**
The OHLCV values of the bar at which the signal fired. Recorded for post-hoc analysis of signal quality.

**`signal_direction`**
`entry_long`, `entry_short`, `exit_long`, `exit_short`, or `no_action`. Derived from the rule that fired.

**`rule_id`**
The identifier of the rule (entry rule or exit rule) that produced this signal.

**`feature_values_at_signal`**
A structured snapshot of the relevant feature values computed at the signal bar. Includes at minimum the feature values directly referenced by the firing rule. This enables post-hoc inspection of why the signal fired.

**`warmup_satisfied`**
Boolean. True if the session's warmup requirement was satisfied before this signal was generated. Should always be true for valid signals; included as an explicit integrity check.

**`strategy_snapshot_hash`**
A hash of the strategy snapshot in the owning session. Provides a link from the signal back to the exact strategy definition that produced it.

**`provider_name`**
The provider that supplied the bar data for this signal (e.g., `yahoo`, `polygon`).

**`symbol`**
The symbol being evaluated.

**`timeframe`**
The timeframe of the bar.

### What Is NOT in a Signal Record

* Any fill, order, or execution fields
* Any position state (there is no position in forward testing)
* Any P&L or equity
* `file_path` (the catalog ID or provider name is used)
* Decrypted credential values

### Signal Retention

All `ForwardTestSignal` records must be retained for the full lifetime of their parent `ForwardTestSession`.

Signals must not be deleted, modified, or overwritten after creation.

Signal records form the primary evidence for promotion review. A session without intact signal records is insufficient evidence for lifecycle advancement.

### No-Action Bars

Bars on which no rule fires are not recorded as signals. They are accounted for implicitly by the gap between `session activation timestamp` and the last known signal timestamp, and by the bar count recorded in session metadata.

The session must record the total number of bars evaluated (warmup bars + signal-eligible bars) as a session-level summary field, so that analysts can compute signal frequency without requiring full bar-level logging.

---

## 9. Provenance Requirements

Every `ForwardTestSignal` and every `ForwardTestSession` record must carry provenance sufficient to answer, at any future point in time:

* Which strategy produced this signal?
* What exact version of the strategy was active?
* What was the strategy's lifecycle status when the session was activated?
* What data source supplied the bar?
* What provider, symbol, timeframe, and bar timestamp produced the signal?
* What were the exact feature values at signal time?
* When was this signal generated, and in which session?

### Strategy Provenance

Every signal links to a `strategy_snapshot_hash` and through that to the full strategy snapshot in the session record. No live strategy definition references — only the sealed snapshot.

The underlying `StrategyDraft` may be modified after session activation. The snapshot is immune to those modifications. The signal's lineage to the specific strategy definition it was produced by is preserved permanently.

### Data Source Provenance

For provider-sourced sessions:
* `provider_name`, `symbol`, `timeframe`, `bar_timestamp` are recorded on every signal
* The session record carries `provider_name`, `symbol`, `timeframe`, `activation_timestamp`, `last_processed_bar_timestamp`

For catalog-sourced sessions:
* `catalog_id` is recorded (never `file_path`)
* The session record carries `catalog_id`, `symbol`, `timeframe`

### Session Provenance

Every signal carries `session_id`, linking it to the full session record which contains:
* `user_id` (owner)
* `activation_timestamp`
* `strategy_snapshot` (sealed copy)
* `lifecycle_status_at_activation`
* Warmup context bar range

### Timestamp Provenance

Both `signal_timestamp` (wall clock) and `bar_timestamp` (market data) are recorded on every signal.

These may differ. For a daily bar session, the `bar_timestamp` might be `2025-03-15T00:00:00Z` (the bar date) while `signal_timestamp` is `2025-03-16T02:17:43Z` (the time the evaluator processed the bar after the daily close and polling delay).

Both are meaningful. `bar_timestamp` is the analytical timestamp (when did the market produce this bar). `signal_timestamp` is the operational timestamp (when did the system observe and evaluate this bar).

### Immutability

Provenance records are immutable after creation. Signal records must not be modified after they are written. Session records may only be updated through the defined lifecycle state machine — structural fields like `strategy_snapshot`, `user_id`, `symbol`, and `timeframe` must never change after creation.

---

## 10. Ownership Requirements

Forward test sessions are user-owned resources.

### Ownership Rules

The ownership model follows the same rules established for strategy drafts, backtest runs, and catalog entries:

* Every `ForwardTestSession` is owned by exactly one user
* Ownership is established from the authenticated user's JWT at session creation — never from client-supplied payload
* Session ownership cannot be transferred
* No shared sessions: multiple users do not co-own a forward test session
* No unowned sessions: a session without a valid `user_id` is an architectural defect

### Access Control

* Only the owning user may view, control, export, or review their forward test sessions
* Wrong-owner access returns HTTP 404 — identical to a not-found response. Information hiding is enforced.
* Admins may access sessions through admin-scoped inspection interfaces only, consistent with the admin governance model
* No session data is publicly accessible

### No Shared Execution Environments

Forward test sessions must not share a bar accumulation window, signal history, or any runtime state with sessions owned by other users.

Two users evaluating the same strategy on the same symbol must have fully isolated session records, even if the underlying provider data is identical.

---

## 11. Persistence Model

### What Must Be Persisted

The following must be durably persisted:

**Session metadata**: All fields defined in §4 — `session_id`, `user_id`, `strategy_snapshot`, `strategy_version`, `lifecycle_status_at_activation`, `source_mode`, `provider_name`, `catalog_id`, `symbol`, `timeframe`, `activation_timestamp`, `last_processed_bar_timestamp`, `warmup_bars_required`, `status`, `error_detail`, `created_timestamp`, `updated_timestamp`.

**Signal history**: Every `ForwardTestSignal` record produced during the session. Signals must be written durably before the poll cycle that produced them is considered complete.

**State transitions**: Every transition of the session's `status` field, with timestamp and actor.

**Gap events**: Every detected data gap, with expected timestamp and actual available bar timestamps.

**Provider failure events**: Every detected provider failure, with error category and timestamp.

**Warmup context summary**: The timestamp range of the initial warmup bars fetched at session activation, the count of warmup bars processed, and the timestamp of the first signal-eligible bar.

**Audit references**: References to audit event IDs for all audited session events (see §13).

### What Is NOT Persisted

The following must not be persisted in session records:

* Raw OHLCV bar data beyond what is captured in individual signal records (the bar window used for feature computation is a runtime data structure, not a persistent archive — the provider is the source of truth for historical bar data)
* In-progress feature computation state (this is reconstructed from the bar window on session resume)
* Raw provider API responses
* `file_path` values
* Decrypted credential values or encrypted credential secrets

### Persistence Guarantees

**At minimum**: Signal records must be written before the evaluator processes the next bar. A signal that is generated but not written before the next poll cycle is an acceptable transient risk only if the session can recover and re-evaluate the missed bar on resume. If recovery is not possible, the session must transition to `failed`.

**Session state**: The `last_processed_bar_timestamp` must be updated atomically with the signal write for the bar that was just processed. If a process crash occurs between processing a bar and updating the cursor, the bar will be re-evaluated on the next run. The subsystem must handle duplicate bar re-evaluation gracefully — a signal for a bar that already has a signal record must not create a duplicate.

**Idempotency**: Writing the same signal twice (same `session_id` + `bar_timestamp` + `signal_direction`) must be idempotent — the second write must not produce a duplicate record.

---

## 12. Failure Model

The forward testing subsystem must handle the following failure classes without data loss or session corruption.

### Provider Unavailable

**Definition**: The provider API returns an error, times out, or is unreachable during a poll cycle.

**Handling**:
1. Record a `PROVIDER_POLL_FAILED` event with error category and timestamp
2. Increment a consecutive failure counter
3. Skip this poll cycle (no signal evaluation)
4. If consecutive failures exceed a configurable threshold (e.g., 3 consecutive failures over the timeframe period): transition session to `paused`; record a `SESSION_PAUSED_PROVIDER_FAILURE` audit event
5. If a single failure: retry on next scheduled poll cycle

**Session state**: Remains `running` during transient failures. Transitions to `paused` on persistent failure.

### Empty Data Response

**Definition**: The provider returns a successful response but no bars for the requested symbol and time range.

**Handling**:
1. Check whether empty data is expected (e.g., market holiday, no trading on this symbol)
2. If expected: record the expected gap; continue to next poll cycle
3. If unexpected (market was open; trading hours confirm bars should exist): treat as a gap event; record and continue
4. Do not treat empty data as a provider failure unless it persists across multiple consecutive poll cycles during expected trading hours

### Duplicate Bars

**Definition**: Provider returns a bar whose timestamp is equal to or earlier than `last_processed_bar_timestamp`.

**Handling**: Silently discard. Update no state. No audit event required for normal duplicate bar discard.

If duplicate bars appear consistently (provider appears to be delivering the same bars repeatedly with no new data despite expected bar advancement): treat as a provider anomaly; record a `PROVIDER_ANOMALY_DETECTED` event; evaluate whether to pause the session.

### Late Bars

**Definition**: Provider returns a bar that is significantly later than expected given the timeframe schedule and polling interval. For example, a 1-hour session expected a bar for 14:00 UTC but only received it at 17:00 UTC.

**Handling**:
1. Accept the bar — a late bar is still a valid bar once it is available
2. Record the `bar_timestamp` and `signal_timestamp` accurately — the difference between them captures the latency
3. Do not attempt to infer or reconstruct what happened during the missing period
4. Continue evaluation normally

Late bar detection is informational, not a failure condition. The signal timestamp and bar timestamp pair records the latency transparently.

### Polling Failure (Subsystem Failure)

**Definition**: The polling mechanism itself fails — scheduler crash, process restart, infrastructure failure.

**Handling**:
1. Session state is preserved in durable storage including `last_processed_bar_timestamp`
2. On subsystem restart: identify sessions in `running` state
3. For each running session: check how many bars have been missed since `last_processed_bar_timestamp`
4. If missed bars are within a recoverable window: perform catch-up evaluation (process missed bars in ascending order as if they arrived normally); continue
5. If the missed window exceeds a configurable threshold: record a `SESSION_CATCHUP_THRESHOLD_EXCEEDED` event; pause the session; notify the user

Catch-up evaluation must not produce signals that claim to have been generated at a time earlier than the evaluator actually processed them. The `signal_timestamp` must reflect when the signal was evaluated, not the `bar_timestamp`. This preserves the transparency between analytical time and operational time.

### Session Corruption

**Definition**: Session record is in an inconsistent state — missing required fields, invalid state transition, `last_processed_bar_timestamp` not consistent with signal history.

**Handling**:
1. Detect corruption at session resume time (on activation after pause or restart)
2. Transition session to `failed` with `error_detail` recording the nature of the inconsistency
3. Do not attempt automatic repair of a corrupted session
4. User must create a new session

### Strategy Evaluation Failure

**Definition**: The strategy evaluator raises an unhandled exception for a specific bar (tool computation error, rule evaluation error, feature unavailability).

**Handling**:
1. Record a `STRATEGY_EVALUATION_FAILED` event with bar timestamp and error category (not raw exception message)
2. Skip signal generation for this bar
3. Update `last_processed_bar_timestamp` to this bar's timestamp (do not re-process a failing bar indefinitely)
4. If evaluation failures persist across multiple consecutive bars: pause the session; notify the user

---

## 13. Audit Requirements

All forward testing session events must produce structured audit records through the platform's existing `emit_audit_event()` infrastructure.

### Mandatory Audit Events

**Session Lifecycle**

| Event | Trigger |
|---|---|
| `FORWARD_TEST_SESSION_CREATED` | Session record created |
| `FORWARD_TEST_SESSION_ACTIVATED` | Session transitions to `running` |
| `FORWARD_TEST_SESSION_PAUSED` | Session transitions to `paused` (user-requested) |
| `FORWARD_TEST_SESSION_PAUSED_PROVIDER_FAILURE` | Session transitions to `paused` due to persistent provider failure |
| `FORWARD_TEST_SESSION_RESUMED` | Session transitions from `paused` to `running` |
| `FORWARD_TEST_SESSION_COMPLETED` | Session transitions to `completed` |
| `FORWARD_TEST_SESSION_FAILED` | Session transitions to `failed` |
| `FORWARD_TEST_SESSION_TERMINATED` | Session transitions to `terminated` by admin or system |
| `FORWARD_TEST_INVALID_TRANSITION_DENIED` | Attempted invalid state transition rejected |

**Strategy Activation**

| Event | Trigger |
|---|---|
| `FORWARD_TEST_ACTIVATION_DENIED` | Session activation attempted but strategy lifecycle check failed (strategy not validated) |
| `FORWARD_TEST_ACTIVATION_APPROVED` | Session activated; strategy lifecycle check passed |

**Signal Events**

| Event | Trigger |
|---|---|
| `FORWARD_TEST_SIGNAL_GENERATED` | A rule fired and a `ForwardTestSignal` was recorded |
| `FORWARD_TEST_SIGNAL_SUPPRESSED` | A rule fired but signal was suppressed (evaluation filter, warmup not satisfied, etc.) — with reason |

**Data Events**

| Event | Trigger |
|---|---|
| `FORWARD_TEST_POLL_COMPLETED` | Poll cycle completed successfully (with bar count processed) |
| `FORWARD_TEST_PROVIDER_FAILURE` | Single poll cycle failure |
| `FORWARD_TEST_GAP_DETECTED` | Data gap detected between expected and received bars |
| `FORWARD_TEST_CATCHUP_STARTED` | Catch-up evaluation initiated after missed bars |
| `FORWARD_TEST_CATCHUP_THRESHOLD_EXCEEDED` | Missed bar window too large for catch-up |
| `FORWARD_TEST_PROVIDER_ANOMALY_DETECTED` | Persistent duplicate or stale data from provider |

**Session Data Access**

| Event | Trigger |
|---|---|
| `FORWARD_TEST_SESSION_EXPORTED` | User requested export of session signals or metadata |
| `FORWARD_TEST_SESSION_REVIEWED` | Session accessed for lifecycle promotion review |

### Audit Payload Requirements

Every audit event must include:
* `session_id`
* `user_id` (session owner)
* `event_timestamp` (UTC)
* Event-specific payload fields (e.g., signal ID for signal events; error category for failure events)

Audit events must never include:
* `file_path`
* Decrypted credential values
* Raw provider error messages
* Internal stack traces

---

## 14. UI Workflow Concept

This section describes the conceptual user workflow for the forward testing feature. No UI implementation is specified here.

### User Journey

**1. Session Configuration**
The user selects:
* A strategy from their draft registry (must have `lifecycle_status >= validated`)
* A data source (provider + symbol + timeframe, or catalog entry)

The user reviews:
* The strategy's lifecycle status
* A summary of the strategy's rule structure and tool configuration
* The estimated warmup requirement

**2. Session Activation**
The user activates the session. The platform:
* Creates the `ForwardTestSession` record
* Fetches initial warmup bars
* Transitions the session to `running`
* Begins the polling schedule

**3. Monitoring**
While the session is running, the user can:
* View the signal history as signals accumulate
* View the current session status and last processed bar timestamp
* Review gap events and provider failure events
* See signal frequency statistics (signals per period)

**4. Pause / Resume**
The user may pause the session at any time. While paused:
* No polling occurs
* The signal history is preserved
* The session may be resumed

**5. Stop and Review**
The user stops the session. The platform:
* Transitions the session to `completed`
* Presents the full signal history for review
* Shows session summary statistics (total bars evaluated, warmup bars, signal-eligible bars, signal count, signal frequency)

**6. Promotion Review**
The signal history and session record are used as evidence when the user requests advancement to `paper_tested` lifecycle status. The user or an authorized admin reviews the session before approving promotion.

### What the UI Must Never Do

* Submit orders or fills based on signal events
* Display position state (there is none)
* Display equity, P&L, or account balance (there is none)
* Allow a user to modify the strategy definition during an active session
* Allow a user to backfill signal records manually

---

## 15. Future Upgrade Path: Polling to Streaming

The polling architecture defined in §6 is the correct architecture for QuantLab's current REST-based provider infrastructure. When provider infrastructure expands to include WebSocket-based streaming feeds, the forward testing subsystem can be upgraded without changing strategy logic, strategy definitions, or the execution contract.

### What the Upgrade Changes

| Component | Polling | Streaming |
|---|---|---|
| Data acquisition | REST poll on schedule | WebSocket subscription; bars pushed on close |
| Bar finalization | Clock-based; poll after estimated bar close | Provider-driven; bar marked complete when bar-close event received |
| Polling schedule | Configurable interval + buffer | Not applicable; bar events arrive as they close |
| Missed bar recovery | Catch-up fetch on resume | Gap-fill fetch for missed bars since last session event |

### What the Upgrade Does NOT Change

| Component | Unchanged |
|---|---|
| Strategy evaluation | Identical — same per-bar evaluation model |
| Signal recording | Identical — same `ForwardTestSignal` schema |
| Session lifecycle | Identical — same state machine |
| Ownership model | Identical |
| Provenance model | Identical |
| Audit model | Identical — streaming would add `FORWARD_TEST_STREAM_CONNECTED` and `FORWARD_TEST_STREAM_DISCONNECTED` events |
| Execution invariants | Identical — still signal observation only |

### Upgrade Path

1. Implement a streaming provider adapter conforming to the existing `ProviderAdapterFactory` interface
2. Add a `source_type` field to `ForwardTestSession` (`polling` or `streaming`)
3. The evaluator processes bars from the adapter regardless of whether they arrived via REST or WebSocket
4. Sessions may run in polling mode or streaming mode; the evaluation logic is the same

**Strategy logic is never aware of the data delivery mechanism.** A strategy that runs correctly in polling mode will run correctly in streaming mode without modification.

The polling architecture is the bridge, not the ceiling.

---

## 16. Relationship to Future Documents

### Paper Trading Architecture (`PAPER_TRADING_ARCHITECTURE.md`)

Forward testing is the immediate predecessor to paper trading in the strategy lifecycle.

The paper trading architecture builds directly on the forward testing architecture:
* The `ForwardTestSession` model is extended to add account state, position state, fill simulation, and equity tracking
* The session lifecycle is the same; paper trading adds position management events
* The signal recording model is extended — signals in paper trading become `ExecutionIntent` objects that are routed to the `PaperBrokerAdapter`
* The data acquisition model (polling architecture) is shared

The promotion path from forward testing to paper trading requires a completed `ForwardTestSession` with sufficient signal history. The evidence requirements for this promotion gate are defined in `STRATEGY_PROMOTION_LIFECYCLE.md`.

### Execution Audit Model (`EXECUTION_AUDIT_MODEL.md`)

The audit events defined in §13 must be incorporated into the execution audit taxonomy.

`EXECUTION_AUDIT_MODEL.md` will define:
* The formal `AuditEventKind` enum values for all forward testing events listed in §13
* Required payload fields for each event kind
* Retention policy for forward testing audit records
* Query interface requirements for audit inspection

### Strategy Promotion Lifecycle (`STRATEGY_PROMOTION_LIFECYCLE.md`)

Forward testing is a stage in the strategy promotion lifecycle.

`STRATEGY_PROMOTION_LIFECYCLE.md` must define:
* The minimum evidence requirements for a forward test session to qualify for promotion review (minimum session duration, minimum bars evaluated, minimum signal count threshold, minimum session status of `completed`)
* The promotion gate between `validated` + forward-tested evidence → `backtested` lifecycle status
* Whether a promotion-grade forward test imposes stricter session quality requirements than a research-grade forward test

---

## 17. Non-Negotiable Constraints

The following constraints are absolute. No implementation may violate them.

**No orders**: Forward testing does not generate, route, or record orders of any kind. There is no order object in the forward testing subsystem.

**No positions**: Forward testing does not track, simulate, or record open or closed positions. There is no position state.

**No fills**: Forward testing does not simulate fills, model execution mechanics, or record fill prices. A signal is not a fill.

**No account**: There is no simulated account associated with a forward test session. No cash, no equity, no margin, no account identifier.

**No P&L**: There is no realized P&L, unrealized P&L, or hypothetical P&L in forward testing. The word "profit" must not appear in forward test result artifacts.

**No broker integration**: Forward testing uses only the market data layer. No broker credentials are accessed. No broker adapter is invoked.

**No automatic promotion**: A completed forward test session does not automatically advance the strategy's lifecycle status. Promotion requires explicit human review and authorization.

**No live execution**: Forward testing observations never trigger any real-world financial action.

**Signal observation only**: Forward testing produces one class of output — `ForwardTestSignal` records. Everything else belongs to paper trading, live trading, or a different subsystem.

---

## Summary of Forward Testing Responsibilities

```
SESSION ACTIVATION
    → Verify: strategy lifecycle_status >= validated
    → Snapshot: strategy definition (sealed; immutable)
    → Configure: source (provider/catalog), symbol, timeframe
    → Record: activation provenance
    → Fetch: initial warmup bars from provider
    → Process: warmup bars (no signal generation)
    → Transition: session to 'running'
    → Audit: FORWARD_TEST_SESSION_ACTIVATED

POLL CYCLE (per timeframe period)
    → Poll: provider for completed bars since last_processed_bar_timestamp
    → Filter: discard duplicate bars
    → Detect: gaps; record gap events
    → For each new completed bar (ascending timestamp order):
        → Compute: features using existing tool registry
        → Evaluate: strategy rules using existing semantic evaluator
        → If rule fires AND warmup satisfied:
            → Record: ForwardTestSignal (immutable)
            → Audit: FORWARD_TEST_SIGNAL_GENERATED
        → Update: last_processed_bar_timestamp
    → Audit: FORWARD_TEST_POLL_COMPLETED
    → On provider failure: record failure; retry or pause

SESSION CLOSE
    → Transition: session to 'completed'
    → Record: session summary (total bars, warmup bars, signal count)
    → Audit: FORWARD_TEST_SESSION_COMPLETED
    → Retain: all signal records and session metadata immutably

ENFORCEMENT (invariants that must never be violated)
    → No orders, positions, fills, account, P&L
    → No broker integration
    → No automatic promotion
    → Signal observation only
    → Strategy portability invariant preserved
    → Existing evaluation engine reused unchanged
    → Ownership: JWT-derived, never client-supplied
    → Provenance: sealed snapshot, immutable timestamps
    → file_path never in any record
```

Forward testing is the first step from historical evidence into live market observation.

Its discipline — no fills, no positions, no P&L — is what makes it safe as a governance stage.

# EXECUTION_AUDIT_MODEL.md

## Purpose

This document defines the authoritative execution audit architecture for QuantLab.

It establishes the audit philosophy, the complete event taxonomy, provenance requirements, immutability rules, retention principles, the review model, and the relationship between audit evidence and governance decisions — across all execution modes: forward testing, paper trading, and future live trading.

This document:

* establishes why audit records are authoritative evidence in execution contexts
* defines the taxonomy of events that must be audited across all execution subsystems
* defines the structure every audit record must satisfy
* defines the provenance requirements that make audit records useful as evidence
* defines the retention and review model
* establishes the relationship between this document and the strategy promotion lifecycle

This document is architecture-level.

It is informed by the audit event categories defined in:
* `docs/EXECUTION_CONTRACT.md`
* `docs/FORWARD_TESTING_ARCHITECTURE.md`
* `docs/PAPER_TRADING_ARCHITECTURE.md`
* `docs/BACKTESTING_ENGINE_CONTRACT.md`

It unifies those categories into a single, coherent audit model that all execution subsystems must conform to.

No implementation. No event-store design. No database schema. No retention engine. Architecture only.

---

## Why This Document Exists

Backtesting is deterministic and reproducible. Given identical inputs, it produces identical results. If a backtest result is questioned, the backtest can be re-run to verify. The result itself is not the only evidence — the evidence can be reconstructed.

Execution is not reproducible. A forward test session evaluated bars that arrived at specific times from a specific market state that no longer exists. A paper trading session produced fills from bars that cannot be replicated. A live trading session placed real orders in a live market that has moved on.

When execution is questioned — by a user, a reviewer, a compliance officer, or a governance process — the session record and its audit trail are the only evidence. There is no "re-run" option.

This fundamental asymmetry between backtesting and execution makes the audit model a first-class architectural concern, not an implementation detail. Audit records for execution systems are not logs. They are evidence.

Without a formal audit model, execution subsystems risk:

* building audit records that cannot answer the questions a promotion reviewer must ask
* producing event records with inconsistent structure across subsystems, making unified review impossible
* omitting critical events (order rejections, drawdown warnings, provider failures) that are essential for understanding session quality
* creating mutable audit records that can be altered after the fact, destroying their evidentiary value
* failing to preserve the provenance links that connect a fill back to the strategy rule that originated it

This document prevents those failures.

---

## 1. Purpose of Execution Audit

### Why Execution Audit Exists

Execution audit exists because execution is irreversible and non-reproducible.

In backtesting, reproducibility is the primary quality guarantee. The Backtesting Engine Contract establishes that identical inputs must produce identical results. If there is doubt about a backtest result, the doubt can be resolved by running the same backtest again.

In execution, there is no equivalent guarantee. A forward test session that ran for six weeks observed six weeks of real market data. A paper trading session that produced 47 fills processed 47 real bars at 47 specific moments in time. A live trading session placed real orders in a live market. None of these can be re-run.

When any question arises about what happened — and questions will arise — the answer can only come from the audit record. The audit record is the substitute for reproducibility in the execution domain.

### Why Execution Differs from Backtesting

| Property | Backtesting | Execution |
|---|---|---|
| Data source | Fixed, immutable historical dataset | Live or near-live data; no fixed dataset |
| Determinism | Guaranteed given identical inputs | Not possible; live data is unrepeatable |
| Reproducibility | Full — re-run produces identical results | Not possible |
| Evidence mechanism | Can re-run to verify | Must consult the audit trail |
| Primary output | Research artifact (equity curve, metrics) | Session record + audit trail |
| Failure investigation | Re-run with diagnostics | Consult audit trail |
| Promotion evidence | Backtest run artifact | Session record + audit trail |

This table defines the contract: execution audit records compensate for the absence of reproducibility. They must be complete enough, immutable enough, and detailed enough to answer any question that reproducibility would otherwise resolve.

### Why Audit Records Become Authoritative

An audit record is authoritative because:

1. **It was written at the time the event occurred.** It reflects what actually happened, not a later reconstruction.

2. **It is immutable.** Once written, it cannot be altered. A record that can be edited is not evidence — it is a narrative.

3. **It carries full provenance.** The audit record preserves the strategy version, the bar data source, the declared simulation assumptions, and the user ownership context. A reviewer reading the audit record has everything needed to understand what happened without consulting external systems.

4. **It is complete.** Every significant event in the session lifecycle, from creation through termination, must produce an audit record. A session with gaps in its audit trail is an incomplete record.

Audit records are not logging. Logging is for operational diagnostics — it is expected to be partial, rotated, and filtered. Audit records are for governance — they must be complete, permanent, and independently verifiable.

---

## 2. Audit Philosophy

Six principles govern the QuantLab execution audit model.

### Traceability

Every execution artifact — every signal, every fill, every position — must be traceable back to its origin through an unbroken chain:

```
Strategy Rule
    → ForwardTestSignal
        → ExecutionIntent
            → PaperOrder
                → PaperFill
                    → PaperPosition change
                        → AccountState change
```

Each link in this chain must exist as an audit record. A reviewer must be able to start from any artifact — for example, a specific fill — and trace backward to the strategy rule that produced the originating signal, or forward to the equity effect of the fill.

Traceability is not optional. An audit record that cannot be traced to its origin is not admissible as promotion evidence.

### Ownership

Every audit record must identify who owns the session and who performed the action.

Ownership in audit records follows the same invariant established throughout QuantLab:
* Session ownership is derived from the authenticated user's JWT — never from client-supplied values
* Audit records reflect the ownership at the time the event occurred
* An audit record without an owner identity is structurally incomplete

### Immutability

Audit records are append-only.

After an audit record is written, it must never be edited, overwritten, or silently deleted.

If a record contains an error — for example, if incorrect metadata was recorded — the correct response is to write a correction record, not to edit the original. The correction record references the original and notes the discrepancy. The original remains in the audit trail.

Immutability is the foundation of the audit record's evidentiary value. A mutable audit record is not evidence.

### Reviewability

Audit records must be structured for human review, not only for machine processing.

A promotion reviewer — who may be a user, an admin, or a future automated review system — must be able to read an audit trail and answer:

* What happened during this session?
* Did the strategy behave as expected?
* Were there any anomalies (provider failures, order rejections, drawdown events)?
* Is this session sufficient evidence for the next lifecycle advancement?

Reviewability requires that:
* Event types are human-readable, not opaque codes
* Event payloads contain descriptive context, not only identifiers
* The sequence of events is ordered and timestamped
* Rejections and failures explain their reasons in structured (non-raw) terms

### Governance

Audit records support governance decisions. They do not make them.

The audit trail for a paper trading session provides evidence for a promotion decision. It does not make the promotion decision. The promotion decision requires a human or explicitly authorized system to review the evidence and authorize the advancement.

Audit records are input to governance. They are not governance themselves.

### Accountability

Every action in an execution session is attributed to an actor.

For user-initiated actions (session start, pause, stop): the actor is the authenticated user.

For system-initiated actions (drawdown stop trigger, provider failure pause, strategy evaluation): the actor is the system component responsible for the action, identified by a stable system actor identifier.

Accountability means that for any event in the audit trail, there is a clear answer to: "Who or what caused this?"

---

## 3. Audit Scope

The execution audit model covers all events that affect the lifecycle, content, or governance standing of an execution session or its artifacts.

### What Must Be Audited

**Forward Testing**
* All session lifecycle transitions
* All signal generation and signal suppression events
* All data events (poll completions, gaps, provider failures, catch-up operations)
* All access events (session export, session review for promotion)

**Paper Trading**
* All session lifecycle transitions
* All signal events (inherited from forward testing model)
* All order events (creation, rejection, cancellation)
* All fill events
* All position events (opened, scaled, closed, force-closed)
* All account events (updates, drawdown warnings, drawdown stop triggers)
* All data events (same as forward testing)
* All access events

**Future Live Trading**
* All of the above
* All broker communication events (order submission, acceptance, rejection, fills)
* All connection events (broker connect, disconnect, reconnect)
* All safety events (hard-stop triggers, emergency actions)

**Strategy Governance**
* All promotion requests
* All promotion review activities
* All promotion approvals and rejections
* All lifecycle status changes for strategies involved in execution

**Administrative Actions**
* All user role changes
* All subscription lifecycle events
* All entitlement decisions
* All access denials to execution resources

**Execution Failures**
* All session failures with error category
* All strategy evaluation failures
* All unrecoverable errors

### What Is NOT Within Execution Audit Scope

* Internal computation details (feature values, tool execution logs) — these are captured in the signal record as provenance, not in the audit trail
* Routine poll cycle health-checks that produce no bars and no events — these are operational metrics, not audit events
* Frontend rendering events — the frontend consumes session state; it does not generate auditable execution events

---

## 4. Audit Event Taxonomy

The execution audit model organizes events into six categories.

Every event in the audit system belongs to exactly one category.

| Category | Prefix | Scope |
|---|---|---|
| Forward Testing | `FT_` | Events specific to forward test sessions |
| Paper Trading | `PT_` | Events specific to paper trading sessions |
| Live Trading | `LT_` | Events specific to live trading sessions (future) |
| Governance | `GOV_` | Events related to strategy promotion and lifecycle decisions |
| Administrative | `ADMIN_` | Events related to user, role, and entitlement management |
| Failure | `FAILURE_` | Unrecoverable errors across all execution modes |

The prefix convention is an architecture-level naming guide. It establishes that the taxonomy is unified and queryable by category — a reviewer querying `PT_` events can isolate paper trading events without filtering through unrelated events.

Governance events (`GOV_`) are shared across all execution modes. A promotion review event references a session; the session determines whether it is a forward test, paper trading, or live trading session.

Administrative events (`ADMIN_`) cover the existing platform governance model (user approval, subscription lifecycle, role changes) and extend it to cover execution-resource access.

---

## 5. Forward Testing Audit Events

All forward testing audit events use the `FT_` prefix.

### Session Lifecycle Events

**`FT_SESSION_CREATED`**
Recorded when the `ForwardTestSession` record is first created.

Purpose: Establishes the first entry in the audit trail for this session. Captures who created the session, when, with which strategy, and with which data source. This event is written even if the session is never activated.

Required payload: `session_id`, `user_id`, `strategy_snapshot_hash`, `strategy_version`, `lifecycle_status_at_creation`, `source_mode`, `provider_name_or_catalog_id`, `symbol`, `timeframe`, `created_timestamp`

**`FT_SESSION_ACTIVATED`**
Recorded when the session transitions from `pending` to `running`.

Purpose: Marks the moment the session began processing live bars. The activation timestamp in this event is the canonical start-of-session timestamp for all downstream analysis.

Required payload: `session_id`, `user_id`, `activation_timestamp`, `warmup_bars_required`, `lifecycle_status_at_activation`

**`FT_ACTIVATION_DENIED`**
Recorded when a session activation attempt is rejected because the strategy's lifecycle status is below the required threshold.

Purpose: Governance record. Proves that the lifecycle gate was enforced, and captures what status the strategy held at the time of the denied attempt.

Required payload: `session_id`, `user_id`, `strategy_id`, `strategy_lifecycle_status_at_attempt`, `required_status`, `denial_timestamp`

**`FT_SESSION_PAUSED`**
Recorded when the session transitions to `paused` at user request.

Purpose: Captures the pause point. When combined with `FT_SESSION_RESUMED`, defines the duration of the pause and how many bars were missed.

Required payload: `session_id`, `user_id`, `last_processed_bar_timestamp`, `pause_timestamp`, `reason` (user_requested)

**`FT_SESSION_PAUSED_PROVIDER_FAILURE`**
Recorded when the session transitions to `paused` due to persistent provider failures exceeding the retry threshold.

Purpose: Distinguishes provider-failure pauses from user-requested pauses. Essential for session quality assessment — a session paused due to provider failure may have missed bars that affected signal generation.

Required payload: `session_id`, `consecutive_failure_count`, `last_failure_timestamp`, `last_processed_bar_timestamp`

**`FT_SESSION_RESUMED`**
Recorded when the session transitions from `paused` back to `running`.

Purpose: Marks the resumption point. The gap between `FT_SESSION_PAUSED` and `FT_SESSION_RESUMED` can be used to determine how many bars were missed.

Required payload: `session_id`, `user_id`, `resume_timestamp`, `last_processed_bar_timestamp` (cursor position at resume)

**`FT_SESSION_COMPLETED`**
Recorded when the session transitions to `completed`.

Purpose: Terminal session event. Captures the final session state for review.

Required payload: `session_id`, `user_id`, `completion_timestamp`, `total_bars_evaluated`, `warmup_bars_processed`, `signal_count`, `gap_count`, `provider_failure_count`

**`FT_SESSION_FAILED`**
Recorded when the session transitions to `failed`.

Purpose: Terminal failure record. The structured `error_category` (not raw exception) explains why the session failed without leaking internal implementation details.

Required payload: `session_id`, `user_id`, `failure_timestamp`, `error_category`, `last_processed_bar_timestamp`

**`FT_SESSION_TERMINATED`**
Recorded when the session is forcibly terminated.

Purpose: Administrative or system termination record. The `actor` distinguishes between user termination and admin termination.

Required payload: `session_id`, `actor`, `termination_timestamp`, `reason_category`

**`FT_INVALID_TRANSITION_DENIED`**
Recorded when an invalid state transition is attempted and rejected.

Purpose: Governance record. Proves the state machine is enforced and captures who attempted the invalid transition.

Required payload: `session_id`, `actor`, `attempted_from_state`, `attempted_to_state`, `denial_timestamp`

### Signal Events

**`FT_SIGNAL_GENERATED`**
Recorded when a strategy rule fires at a completed bar during a running session, warmup is satisfied, and a `ForwardTestSignal` record is written.

Purpose: The primary evidence record for forward testing. Each signal event represents one instance of the strategy behaving as designed.

Required payload: `session_id`, `signal_id`, `bar_timestamp`, `signal_direction`, `rule_id`, `feature_values_at_signal` (key values only, not full feature set), `strategy_snapshot_hash`, `signal_timestamp`

**`FT_SIGNAL_SUPPRESSED`**
Recorded when a strategy rule fires but the resulting intent is suppressed — for example, because warmup is not satisfied, or because an evaluation filter blocked the signal.

Purpose: Captures the distinction between "rule did not fire" and "rule fired but signal was blocked." This is analytically important for session quality assessment.

Required payload: `session_id`, `bar_timestamp`, `rule_id`, `suppression_reason`, `signal_timestamp`

### Data Events

**`FT_POLL_COMPLETED`**
Recorded after each successful poll cycle.

Purpose: Operational record of data acquisition. Captures how many new bars were received and processed. Allows reconstruction of the session's data consumption history.

Required payload: `session_id`, `poll_timestamp`, `bars_received`, `bars_processed`, `last_processed_bar_timestamp_after_poll`

**`FT_PROVIDER_FAILURE`**
Recorded for each failed poll cycle.

Purpose: Data quality record. The error category (not raw provider message) explains what kind of failure occurred.

Required payload: `session_id`, `failure_timestamp`, `error_category`, `consecutive_failure_count`

**`FT_GAP_DETECTED`**
Recorded when a data gap is detected — a bar that was expected given the timeframe schedule is absent from the provider response.

Purpose: Data quality record. Gaps may affect feature computation quality and signal generation. Promotion reviewers must know if a session had gaps.

Required payload: `session_id`, `expected_bar_timestamp`, `previous_bar_timestamp`, `next_available_bar_timestamp`, `detection_timestamp`

**`FT_CATCHUP_STARTED`**
Recorded when catch-up evaluation begins after a session restart or resume with missed bars.

Purpose: Session integrity record. Confirms that missed bars were processed after a gap.

Required payload: `session_id`, `catchup_start_timestamp`, `first_missed_bar_timestamp`, `last_missed_bar_timestamp`, `bars_to_process`

**`FT_CATCHUP_THRESHOLD_EXCEEDED`**
Recorded when the catch-up bar count exceeds the configured threshold and the session pauses instead of catching up.

Purpose: Governance record. Documents why the session paused and how many bars were not recovered.

Required payload: `session_id`, `threshold`, `missed_bar_count`, `pause_timestamp`

### Session Access Events

**`FT_SESSION_EXPORTED`**
Recorded when a user requests export of session data.

Required payload: `session_id`, `requester_user_id`, `export_timestamp`, `export_scope` (signals, summary, full)

**`FT_SESSION_REVIEWED`**
Recorded when a session is accessed as part of a governance review.

Required payload: `session_id`, `reviewer_user_id`, `review_timestamp`, `review_context` (promotion review, incident review, research review)

---

## 6. Paper Trading Audit Events

All paper trading audit events use the `PT_` prefix.

Paper trading inherits all forward testing session lifecycle events in spirit (same state machine, same transitions). The `PT_` prefix distinguishes paper trading session events from forward testing session events.

### Session Lifecycle Events

The paper trading session lifecycle events are structurally identical to the forward testing equivalents, with `PT_` prefix and the addition of `account_id` to all payloads:

`PT_SESSION_CREATED`, `PT_SESSION_ACTIVATED`, `PT_ACTIVATION_DENIED`, `PT_SESSION_PAUSED`, `PT_SESSION_PAUSED_DRAWDOWN_STOP`, `PT_SESSION_PAUSED_PROVIDER_FAILURE`, `PT_SESSION_RESUMED`, `PT_SESSION_COMPLETED`, `PT_SESSION_FAILED`, `PT_SESSION_TERMINATED`, `PT_INVALID_TRANSITION_DENIED`

**`PT_SESSION_ACTIVATED`** (extended vs. FT equivalent)
Additional required payload: `account_id`, `starting_equity`, `simulation_assumptions_hash` (a hash of the sealed simulation assumptions for tamper-detection)

**`PT_SESSION_COMPLETED`** (extended vs. FT equivalent)
Additional required payload: `account_id`, `final_equity`, `total_return_pct`, `max_drawdown_pct`, `total_trades`, `win_count`, `loss_count`, `profit_factor`

### Signal Events

Paper trading inherits the signal audit events from forward testing:

`PT_SIGNAL_GENERATED`, `PT_SIGNAL_SUPPRESSED`

These events carry the same payload structure as their `FT_` equivalents.

### Order Events

**`PT_ORDER_CREATED`**
Recorded when the `PaperBrokerAdapter` translates an `ExecutionIntent` into a `PaperOrder`.

Purpose: The first execution-layer record for any trade attempt. Captures the intent-to-order translation before fill simulation.

Required payload: `session_id`, `account_id`, `order_id`, `source_signal_id`, `symbol`, `side`, `quantity`, `order_type`, `created_timestamp`

**`PT_ORDER_REJECTED`**
Recorded when intent validation fails and no order proceeds to fill simulation.

Purpose: Critical governance record. Documents that the execution environment correctly enforced constraints (insufficient cash, max positions exceeded, no position to close). Absence of this event for a rejected intent is an audit gap.

Required payload: `session_id`, `account_id`, `order_id`, `source_signal_id`, `rejection_reason` (structured code: `insufficient_cash`, `max_positions_exceeded`, `no_position_to_close`, `quantity_resolved_to_zero`), `rejection_timestamp`

**`PT_ORDER_CANCELLED`**
Recorded when an order is cancelled before fill (for example, a pending limit order that expires).

Required payload: `session_id`, `account_id`, `order_id`, `cancellation_reason`, `cancellation_timestamp`

### Fill Events

**`PT_FILL_CREATED`**
Recorded when fill simulation produces a `PaperFill`.

Purpose: The primary execution evidence record. Documents exactly how each trade was filled, at what price, with what costs.

Required payload: `session_id`, `account_id`, `fill_id`, `order_id`, `source_signal_id`, `symbol`, `side`, `fill_quantity`, `gross_fill_price`, `slippage_applied`, `net_fill_price`, `fee_applied`, `execution_reason`, `bar_timestamp`, `fill_timestamp`

### Position Events

**`PT_POSITION_OPENED`**
Recorded when a fill opens a new position.

Required payload: `session_id`, `account_id`, `position_id`, `symbol`, `side`, `quantity`, `average_entry_price`, `opening_fill_id`, `opening_signal_id`, `open_timestamp`

**`PT_POSITION_SCALED`**
Recorded when a fill increases the size of an existing open position.

Required payload: `session_id`, `account_id`, `position_id`, `symbol`, `previous_quantity`, `added_quantity`, `new_quantity`, `new_average_entry_price`, `scaling_fill_id`, `timestamp`

**`PT_POSITION_CLOSED`**
Recorded when a fill fully closes a position.

Required payload: `session_id`, `account_id`, `position_id`, `symbol`, `side`, `closed_quantity`, `average_entry_price`, `exit_price`, `realized_pnl`, `closing_fill_id`, `closing_signal_id`, `close_timestamp`, `hold_duration`

**`PT_POSITION_FORCE_CLOSED`**
Recorded when a position is force-closed by `session_end_close` or `drawdown_stop_close`.

Required payload: `session_id`, `account_id`, `position_id`, `symbol`, `closed_quantity`, `exit_price`, `realized_pnl`, `force_close_reason`, `timestamp`

### Account Events

**`PT_ACCOUNT_UPDATED`**
Recorded after each fill updates the account state.

Purpose: Account state audit trail. Combined with `PT_FILL_CREATED` events, allows full reconstruction of the account's cash and equity progression.

Required payload: `session_id`, `account_id`, `trigger_fill_id`, `cash_balance_after`, `equity_after`, `peak_equity_after`, `current_drawdown_pct_after`, `timestamp`

**`PT_DRAWDOWN_WARNING`**
Recorded when equity drawdown exceeds 80% of the configured `max_drawdown_stop_pct` threshold.

Purpose: Advisory governance record. Gives reviewers visibility into drawdown events that approached the stop threshold without triggering it.

Required payload: `session_id`, `account_id`, `current_drawdown_pct`, `stop_threshold_pct`, `warning_threshold_pct`, `timestamp`

**`PT_DRAWDOWN_STOP_TRIGGERED`**
Recorded when equity drawdown exceeds `max_drawdown_stop_pct` and the session transitions to `paused`.

Purpose: Safety governance record. Documents that the declared risk limit was enforced.

Required payload: `session_id`, `account_id`, `peak_equity`, `equity_at_stop`, `drawdown_pct`, `stop_threshold_pct`, `trigger_timestamp`

### Data Events

Paper trading inherits all forward testing data events with `PT_` prefix:

`PT_POLL_COMPLETED`, `PT_PROVIDER_FAILURE`, `PT_GAP_DETECTED`, `PT_CATCHUP_STARTED`, `PT_CATCHUP_THRESHOLD_EXCEEDED`

### Access Events

`PT_SESSION_EXPORTED`, `PT_SESSION_REVIEWED`

Same structure as forward testing equivalents.

---

## 7. Future Live Trading Audit Events

Live trading audit events use the `LT_` prefix.

This section defines the taxonomy conceptually. The detailed payload requirements and specific event parameters will be defined as part of the live trading architecture. This section establishes that these events exist and what they represent, so that the execution audit model is complete as a reference.

### Session Events

`LT_SESSION_CREATED`, `LT_SESSION_ACTIVATED`, `LT_ACTIVATION_DENIED`, `LT_SESSION_PAUSED`, `LT_SESSION_RESUMED`, `LT_SESSION_COMPLETED`, `LT_SESSION_FAILED`, `LT_SESSION_TERMINATED`

Same lifecycle structure as forward testing and paper trading. Additional required payload: `credential_id` (the vault credential used for broker authentication — the ID only, never the secret).

### Broker Communication Events

**`LT_BROKER_ORDER_SUBMITTED`**
Recorded when an order is transmitted to the broker. This is the last internal control point before the order leaves the QuantLab system.

Purpose: Boundary event. Proves that the order was correctly formed and submitted at a specific time. This is the point of no return for live orders.

Required payload (conceptual): `session_id`, `order_id`, `broker_reference`, `symbol`, `side`, `quantity`, `order_type`, `submission_timestamp`

**`LT_BROKER_ORDER_ACCEPTED`**
Recorded when the broker acknowledges the order.

Purpose: Confirms the order entered the broker's system. If `LT_BROKER_ORDER_SUBMITTED` exists but `LT_BROKER_ORDER_ACCEPTED` does not, the order submission failed at the broker boundary.

**`LT_BROKER_ORDER_REJECTED`**
Recorded when the broker rejects the order.

Purpose: Documents the broker-side rejection reason (in structured form). Distinguishes from internal gateway rejections (`PT_ORDER_REJECTED`).

**`LT_BROKER_FILL_RECEIVED`**
Recorded when the broker reports a fill.

Purpose: The authoritative fill record for live trading. Contains the broker fill ID, the exchange-reported fill price, and the fill timestamp from the broker. This event supersedes the fill simulation that paper trading uses.

Required payload (conceptual): `session_id`, `order_id`, `broker_fill_id`, `fill_price`, `fill_quantity`, `fee_from_broker`, `broker_timestamp`, `receipt_timestamp`

**`LT_PARTIAL_FILL_RECEIVED`**
Recorded when a partial fill is received.

Purpose: Documents partial execution. Partial fills change position state in ways that require explicit audit tracking.

### Position Events

`LT_POSITION_OPENED`, `LT_POSITION_SCALED`, `LT_POSITION_CLOSED`, `LT_POSITION_FORCE_CLOSED`

Same structure as paper trading position events. Position state in live trading is authoritative from broker reports, not from internal simulation.

### Safety Events

**`LT_BROKER_CONNECTION_FAILURE`**
Recorded when the broker connection is lost.

Purpose: Safety record. A connection failure during an active session with open positions is a risk event that must be documented.

**`LT_EMERGENCY_STOP_TRIGGERED`**
Recorded when the hard-stop mechanism is activated.

Purpose: The highest-priority safety event. Must be persisted before any other action is taken in response to the stop.

Required payload (conceptual): `session_id`, `trigger_actor`, `trigger_reason`, `open_position_count`, `account_equity_at_stop`, `trigger_timestamp`

**`LT_CREDENTIAL_RESOLVED`**
Recorded when the vault credential is resolved for broker authentication.

Purpose: Security audit record. Proves that credential access for live trading was authorized and attributed to the owning session.

Required payload (conceptual): `session_id`, `credential_id`, `resolution_timestamp` — never the decrypted secret value

---

## 8. Governance Audit Events

Governance audit events use the `GOV_` prefix.

These events document the lifecycle advancement of strategies and the review activities that precede advancement decisions. They are shared across all execution modes — the governance event references the session; the session type (forward test / paper trading / live) contextualizes the event.

**`GOV_PROMOTION_REQUESTED`**
Recorded when a user formally requests advancement of a strategy to the next lifecycle status.

Purpose: Initiates the governance record for a specific promotion attempt. All subsequent review and decision events link back to this record.

Required payload: `strategy_id`, `strategy_version`, `current_lifecycle_status`, `requested_lifecycle_status`, `requester_user_id`, `session_id_as_evidence` (the session whose results constitute the promotion evidence), `request_timestamp`

**`GOV_PROMOTION_REVIEW_STARTED`**
Recorded when a reviewer begins reviewing a promotion request.

Purpose: Documents who reviewed the evidence and when the review began. Required for accountability in the governance process.

Required payload: `promotion_request_id`, `reviewer_user_id`, `session_id`, `review_start_timestamp`

**`GOV_PROMOTION_APPROVED`**
Recorded when a promotion request is authorized and the strategy lifecycle status is advanced.

Purpose: The authoritative record that a governance decision was made. This event is the evidence that promotion was not automatic — it was reviewed and explicitly authorized.

Required payload: `promotion_request_id`, `reviewer_user_id`, `strategy_id`, `previous_lifecycle_status`, `new_lifecycle_status`, `approval_timestamp`, `reviewer_notes` (optional structured field)

**`GOV_PROMOTION_REJECTED`**
Recorded when a promotion request is denied by the reviewer.

Purpose: Documents why promotion was not granted. The structured `rejection_reason` must be meaningful for the strategy author.

Required payload: `promotion_request_id`, `reviewer_user_id`, `strategy_id`, `current_lifecycle_status`, `rejection_reason_category`, `rejection_timestamp`

**`GOV_PROMOTION_REVOKED`**
Recorded when a previously granted lifecycle status is revoked (for example, if a strategy is demoted back from `backtested` to `validated` due to a discovered issue).

Purpose: Documents that lifecycle status is not permanently granted and may be subject to review.

Required payload: `strategy_id`, `revoked_by_user_id`, `previous_lifecycle_status`, `new_lifecycle_status`, `revocation_reason`, `revocation_timestamp`

**`GOV_SESSION_REVIEWED`**
Recorded when a session is accessed specifically for governance review purposes (distinct from general export or casual access).

Purpose: Documents that a reviewer actually inspected the session evidence before a governance decision. This prevents "rubber-stamp" approvals.

Required payload: `session_id`, `reviewer_user_id`, `review_type` (promotion_review, incident_review, compliance_review), `session_type` (forward_test, paper_trading, live_trading), `review_timestamp`

**`GOV_STRATEGY_APPROVED_FOR_PAPER`**
Recorded when a strategy's lifecycle status advances to `backtested` — the status required to enter paper trading.

Purpose: Records the specific moment the paper trading gate was opened for this strategy.

Required payload: `strategy_id`, `approver_user_id`, `evidence_session_ids` (list of sessions reviewed as evidence), `approval_timestamp`

**`GOV_STRATEGY_APPROVED_FOR_LIVE`**
Recorded when a strategy's lifecycle status advances to `approved_for_live`.

Purpose: The highest-stakes governance event in the platform. Records who authorized live trading for a specific strategy, when, and based on what evidence.

Required payload: `strategy_id`, `approver_user_id`, `evidence_session_ids`, `approval_timestamp`, `explicit_acknowledgment_text` (the exact text the approver confirmed — this is a non-repudiation field)

**`GOV_LIFECYCLE_TRANSITION_DENIED`**
Recorded when an invalid lifecycle transition is attempted.

Purpose: Enforces and documents the governance boundary. Captures who attempted the transition and what they attempted.

Required payload: `strategy_id`, `actor_user_id`, `attempted_from_status`, `attempted_to_status`, `denial_timestamp`

---

## 9. Administrative Audit Events

Administrative audit events use the `ADMIN_` prefix.

This category covers user, role, and entitlement management. Many events in this category already exist in the platform's current `emit_audit_event()` infrastructure. This section establishes how those existing events relate to the execution audit model and extends them with execution-specific access events.

### Existing Events (already implemented)

The following `AuditEventKind` values already exist in the platform and are incorporated into this model without modification:

| Existing event | Administrative meaning |
|---|---|
| `USER_APPROVED` | Admin approved a pending user account |
| `SUBSCRIPTION_ACTIVATED` | Subscription set to active |
| `SUBSCRIPTION_SUSPENDED` | Subscription suspended |
| `SUBSCRIPTION_EXPIRED` | Subscription expired (auto-detected) |
| `EXPIRY_UPDATED` | Subscription expiry date updated by admin |
| `ADMIN_SELF_SUSPENSION_DENIED` | Admin attempted to suspend own account |
| `LAST_ADMIN_SUSPENSION_DENIED` | Suspension of last admin blocked |
| `ROLE_PROMOTED` | User promoted to admin role |
| `ROLE_DEMOTED` | Admin demoted to user role |
| `UNAUTHORIZED_ROLE_CHANGE_ATTEMPT` | Self-modification or protected change blocked |
| `ENTITLEMENT_DENIED` | Non-admin user blocked by subscription check |
| `LIFECYCLE_TRANSITION_DENIED` | Invalid strategy lifecycle transition rejected |
| `OVERSIZED_PAYLOAD_REJECTED` | Request payload exceeded declared limit |
| `POLYGON_ENV_FALLBACK_USED` | Polygon ENV key fallback used (requires explicit opt-in) |

These events are part of the unified audit model. They share the audit record structure defined in §10.

### Execution-Specific Access Events

**`ADMIN_EXECUTION_SESSION_ACCESSED`**
Recorded when an admin accesses a user's execution session through an admin-scoped interface.

Purpose: Access audit. Admin access to user execution sessions is legitimate but must be attributed and recorded.

Required payload: `admin_user_id`, `target_session_id`, `target_user_id`, `access_reason_category`, `access_timestamp`

**`ADMIN_SESSION_FORCE_TERMINATED`**
Recorded when an admin force-terminates a user's active session.

Purpose: High-impact administrative action record. Must document why the session was terminated.

Required payload: `admin_user_id`, `target_session_id`, `target_user_id`, `termination_reason`, `termination_timestamp`

---

## 10. Audit Record Structure

Every audit event, regardless of category or type, must conform to the following conceptual structure.

This is the common envelope that all audit records share. Event-specific payload fields are carried in `event_payload`.

### Required Fields

**`audit_id`**
A unique, stable identifier for this audit record. UUID format. Assigned at write time. Never reused.

**`event_type`**
The event type identifier from the taxonomy (e.g., `FT_SIGNAL_GENERATED`, `PT_FILL_CREATED`, `GOV_PROMOTION_APPROVED`). This determines which category the record belongs to and which payload fields are expected.

**`event_timestamp`**
UTC timestamp when the event occurred. This is the time the system processed the event — for bar-based events, this is the wall clock time the evaluator processed the bar, not the bar's market timestamp.

**`actor`**
The entity that caused this event. For user-initiated events: `user_id`. For system-initiated events: a stable system component identifier (e.g., `paper_broker_adapter`, `forward_test_evaluator`, `session_lifecycle_manager`).

**`subject_type`**
The type of the primary subject of this event (e.g., `session`, `strategy`, `user`, `account`, `position`, `order`, `fill`).

**`subject_id`**
The identifier of the primary subject (e.g., the `session_id` for session events, `order_id` for order events).

**`session_id`**
The execution session this event belongs to. Null for events not associated with a specific session (e.g., governance events that precede session creation, administrative events).

**`strategy_id`**
The strategy involved in this event. Null for administrative events not related to a specific strategy.

**`strategy_version`**
The version of the strategy at the time of the event. Null when `strategy_id` is null.

**`user_id`**
The user who owns the session (or is the subject of an administrative event). This is always the owning user — not the actor for administrative events. For example, when an admin terminates a user's session, `user_id` is the session owner and `actor` is the admin.

**`execution_mode`**
The execution mode context: `forward_testing`, `paper_trading`, `live_trading`, or `governance` or `administrative` for non-session events.

**`event_payload`**
A structured object containing event-specific fields. The fields required for each event type are defined in §5–§9. The payload must never contain `file_path`, decrypted secrets, raw provider error messages, or internal stack traces.

**`correlation_id`**
An optional identifier linking related events. For example, `PT_ORDER_CREATED`, `PT_FILL_CREATED`, `PT_POSITION_OPENED`, and `PT_ACCOUNT_UPDATED` events for a single trade share a `correlation_id`, making it possible to retrieve all events for a single trade from the audit log with one query.

### Fields That Must Never Appear in Any Audit Record

* `file_path` — catalog ID is the sole durable dataset identity
* Decrypted credential values — credential ID may appear; the secret must not
* Raw provider API error messages — structured error categories only
* Internal stack traces
* Password hashes
* Raw provider payloads
* Real broker account numbers (for paper trading events)

---

## 11. Provenance Requirements

Every audit record must be sufficient to answer, without consulting any external system, the following questions:

* **Who owns this?** — via `user_id`
* **Who or what caused this?** — via `actor`
* **When did this happen?** — via `event_timestamp`
* **What session was this part of?** — via `session_id`
* **What strategy was involved?** — via `strategy_id` and `strategy_version`
* **What execution mode was active?** — via `execution_mode`
* **What specifically happened?** — via `event_type` and `event_payload`

### Strategy Provenance

Audit records carry `strategy_id` and `strategy_version` at the time of the event.

For session-level events, `strategy_version` is derived from the session's sealed `strategy_snapshot_hash`. This ensures that the audit record references the exact strategy definition that was active — not the current state of the strategy, which may have been modified since session activation.

### Session Provenance

The `session_id` in every audit record links back to the `ForwardTestSession` or `PaperTradingSession` record, which contains the full sealed strategy snapshot, declared assumptions, ownership, and activation provenance.

### Signal Provenance

Fill and position audit records carry `source_signal_id`, preserving the connection from execution artifact back to the signal that originated the trade. A reviewer examining a fill record can retrieve the signal record, which contains the feature values at signal time, the rule that fired, and the strategy version that produced the signal.

### Provider Provenance

Data events (`FT_POLL_COMPLETED`, `PT_GAP_DETECTED`, etc.) carry provider identity and bar timestamps. This establishes the data quality context for the session — a reviewer can see whether the session processed clean data or encountered gaps and provider failures.

### Immutability of Provenance

Audit records must not be retroactively modified to update strategy versions, ownership fields, or session references. The audit record reflects the state at event time. If that state was incorrect, a correction record is written — the original record is preserved as-is.

---

## 12. Immutability Rules

### Audit Records Are Append-Only

After an audit record is written, it must never be edited.

This rule has no exceptions.

The practical consequence: audit records must be written correctly at creation time. There is no "update audit record" operation.

### Corrections Through New Records

If an audit record contains an error — for example, if a system bug caused incorrect metadata to be recorded — the correct response is:

1. Write a new `AUDIT_CORRECTION` record that:
   * References the `audit_id` of the erroneous record
   * Describes the nature of the error
   * Provides the correct values
   * Is itself immutable after creation

2. Leave the original record unchanged in the audit store

The erroneous record and its correction are both part of the audit trail. A reviewer can see the error and the correction.

### Silent Deletion Is Prohibited

Audit records must not be silently deleted — removed without leaving any trace in the audit store.

If records must be removed for legal reasons (right to erasure requests, court orders, compliance requirements), the removal itself must be audited:
* A `AUDIT_RECORDS_REMOVED` record must be written before removal
* The removal record must identify which records were removed, under what authority, and by whom
* The removal record itself is immutable

### Why Immutability Is Non-Negotiable

A mutable audit record is not evidence.

If an audit record can be edited after the fact, it cannot be trusted to reflect what actually happened. A promotion reviewer examining a paper trading session's audit trail must be certain that the fill records, rejection records, and drawdown events they are reading are the actual events, not a curated version of events.

Immutability is what transforms a record from a log (which may be rotated, filtered, or modified) into evidence (which cannot be altered).

---

## 13. Retention Policy

### Architecture Principle

Audit records for execution sessions must be retained for at least as long as the session they document remains in any governance workflow.

This means:

* If a session is under active review for lifecycle promotion, its audit records must be retained
* If a strategy has been `approved_for_live` based on evidence from a session, that session's audit records must be retained for the lifetime of the live trading approval
* If a live trading incident is under investigation, all relevant session audit records must be retained for the duration of the investigation

The practical implication: execution session audit records should be treated as permanent records by default.

### Retention Tiers by Execution Mode

**Forward Testing Audit Records**
Minimum retention: until the strategy's `lifecycle_status` falls below `validated` (archived), plus an archival grace period.

Rationale: Forward testing records are used as evidence for advancement to `backtested` status. Once the strategy is archived and cannot be reactivated, the promotion evidence is no longer needed for forward-looking governance. Historical research value may justify longer retention.

**Paper Trading Audit Records**
Minimum retention: until the strategy's `lifecycle_status` falls below `paper_tested` (revoked or archived), plus an archival grace period.

Rationale: Paper trading records are used as evidence for live trading approval. If live trading approval is ever revoked or a live trading incident occurs, the paper trading audit trail is the pre-approval evidence record.

**Governance Audit Records**
Minimum retention: permanent.

Rationale: Governance decisions — especially `GOV_STRATEGY_APPROVED_FOR_LIVE` — must be permanently retained. These records document who authorized what and when. There is no safe expiry for these records.

**Live Trading Audit Records (future)**
Minimum retention: permanent for all fill, position, and order records. Session lifecycle and data quality records may follow the paper trading retention tier.

Rationale: Real financial transactions produce records with potential regulatory, tax, and legal implications. These records must be treated as permanent.

**Administrative Audit Records**
Minimum retention: permanent for role changes and entitlement decisions. Session-access events follow the session retention policy.

### What Retention Does NOT Define

Retention policy does not specify:
* Storage medium or location
* Database technology
* Archive format
* Encryption at rest requirements
* Cross-region replication

These are implementation concerns addressed in the storage architecture.

---

## 14. Review Model

The execution audit model is designed to support multiple review types, each with different information needs.

### Promotion Review

The most common review type. A reviewer — the strategy author, an admin, or a future automated review system — examines a session's audit trail to determine whether it constitutes sufficient evidence for lifecycle advancement.

**What promotion review requires from the audit trail:**

For forward testing promotion review:
* `FT_SESSION_ACTIVATED` — confirms the strategy's lifecycle status at activation
* `FT_SIGNAL_GENERATED` events — the primary evidence (quantity, direction, timing, feature values)
* `FT_SESSION_COMPLETED` — confirms the session was completed (not failed or terminated mid-session)
* `FT_GAP_DETECTED` and `FT_PROVIDER_FAILURE` events — context for session data quality

For paper trading promotion review:
* All of the above (the signal record)
* `PT_FILL_CREATED` events — execution evidence
* `PT_POSITION_OPENED` and `PT_POSITION_CLOSED` events — trade lifecycle
* `PT_ACCOUNT_UPDATED` events — equity curve evidence
* `PT_DRAWDOWN_WARNING` and `PT_DRAWDOWN_STOP_TRIGGERED` events — risk behavior evidence
* `PT_ORDER_REJECTED` events — capital constraint behavior
* `PT_SESSION_COMPLETED` with final equity metrics

The reviewer must be able to form a judgment about whether the session evidence is adequate, whether the strategy behaved as expected, and whether any anomalies are acceptable.

### Session Quality Review

A review of session quality — not for promotion, but for understanding a specific session's behavior. May be triggered by unusual signal patterns, unexpected drawdown, or provider quality questions.

Session quality review uses data events (`FT_GAP_DETECTED`, `PT_PROVIDER_FAILURE`) alongside signal and fill events to understand whether observed behavior was driven by strategy logic or by data quality issues.

### Incident Review

A review triggered by an unexpected event in an active or completed session. For example: "Why did the paper trading session produce a fill at an unexpected price?"

Incident review traces backward through the audit chain:
* `PT_FILL_CREATED` → fill details
* → `PT_ORDER_CREATED` → order details
* → `source_signal_id` → `FT_SIGNAL_GENERATED` → signal details and feature values
* → `strategy_snapshot_hash` → strategy rule that fired

### Compliance Review

A review focused on governance compliance — did the session activation respect lifecycle requirements? Were promotion decisions made by authorized users? Were risk limits enforced?

Compliance review primarily uses governance events (`GOV_` prefix) and the `FT_ACTIVATION_DENIED` / `PT_ACTIVATION_DENIED` events that prove lifecycle gate enforcement.

---

## 15. Query Requirements

Future audit query systems must support, at minimum, the following access patterns.

### Required Query Capabilities

**Session lookup**: Retrieve all audit records for a given `session_id`, ordered by `event_timestamp`.

**Strategy lookup**: Retrieve all audit records for a given `strategy_id`, across all sessions and governance events.

**User lookup**: Retrieve all audit records where `user_id` matches a given user — all their sessions, governance events, and administrative events.

**Promotion lookup**: Retrieve all governance audit events for a given promotion request or strategy lifecycle advancement.

**Time-range lookup**: Retrieve all audit records within a given UTC timestamp range. Required for incident review covering a specific market period.

**Event-type lookup**: Retrieve all audit records of a given `event_type`. Required for pattern analysis (e.g., "how many `PT_ORDER_REJECTED` events occurred due to `insufficient_cash` across all sessions?").

**Correlation lookup**: Retrieve all audit records sharing a given `correlation_id`. Required for retrieving all events from a single trade without filtering the full session record.

### What Query Requirements Do NOT Define

* Database technology (SQL, document, event store)
* Index structure
* Query language
* API surface
* Pagination approach
* Access control model for the query interface

These are implementation concerns.

### Access Control for Audit Queries

While the query interface implementation is out of scope, the access control model for audit data follows platform invariants:

* Users may query audit records for their own sessions only
* Admins may query audit records for sessions owned by any user under their governance scope
* Governance audit records are accessible to admins and authorized reviewers
* No public access to any audit records
* Query access is itself audited (a query for session audit data produces a `ADMIN_EXECUTION_SESSION_ACCESSED` event)

---

## 16. Relationship to Backtesting

Backtesting and execution serve different evidentiary roles in QuantLab. Both are necessary. Neither substitutes for the other.

### Backtest Artifact

A backtest result artifact is evidence of historical performance under declared simulation assumptions.

Its evidentiary strength comes from reproducibility: given the same inputs (strategy version, dataset, simulation assumptions, engine version), the backtest can be re-run to verify the results. The backtest result is trusted because it can be independently validated.

**Backtest evidence answers**: "How would this strategy have performed on this historical data under these assumptions?"

### Execution Audit Artifact

An execution session audit trail is evidence of live behavior under observed market conditions.

Its evidentiary strength comes from immutability: because the market conditions cannot be replicated, the audit record — which was written at the time the events occurred — is the only available evidence. It is trusted because it cannot be altered after the fact.

**Execution audit evidence answers**: "How did this strategy actually behave when evaluated against this live market data?"

### Why Both Are Required

Backtest evidence is necessary but insufficient for live trading authorization:
* Backtests can be optimized to show favorable historical results
* Historical data does not guarantee future behavior
* Backtests cannot reveal live data quality issues or signal stability under current market regimes

Execution audit evidence (forward testing + paper trading) is necessary but insufficient alone:
* Forward testing evidence does not prove financial viability (no fills, no positions)
* Paper trading simulates execution but does not prove real broker execution quality
* Neither forward testing nor paper trading proves performance across multiple market regimes

Together, backtest results + forward test audit + paper trading audit constitute the three-part evidence base that the strategy promotion lifecycle requires. Each type of evidence answers a different question. The promotion lifecycle document (`STRATEGY_PROMOTION_LIFECYCLE.md`) defines the minimum requirements from each evidence type.

---

## 17. Relationship to Strategy Promotion Lifecycle

The audit model and the promotion lifecycle are distinct but closely related.

### The Audit Model's Role

The audit model defines:
* What events must be recorded
* What those records must contain
* How they must be retained
* How they can be queried

The audit model does not define:
* What constitutes sufficient evidence for promotion
* Who is authorized to review promotion evidence
* How many sessions are required
* What minimum signal count or trade count is required

### The Promotion Lifecycle's Role

`STRATEGY_PROMOTION_LIFECYCLE.md` defines:
* Evidence requirements at each promotion gate
* Who is authorized to review and approve promotion
* The governance workflow for each lifecycle transition
* What minimum audit trail completeness is required before a session can be used as evidence

### The Relationship

The promotion lifecycle is a consumer of audit records. It specifies what audit records must exist and what they must contain before promotion can be considered.

The audit model is a producer. It guarantees that the records the promotion lifecycle requires will exist and will be in the right form.

Critically: **the audit system never decides whether a strategy should be promoted**. That decision belongs to the promotion lifecycle. The audit system only ensures that the evidence the promotion lifecycle needs is available, intact, and immutable.

---

## 18. Future Live Trading Relationship

The execution audit model is designed to accommodate live trading without structural changes.

### What Changes for Live Trading

**Event sources expand**: The `LT_` event category becomes active. The audit infrastructure receives events from the live execution layer — broker communication events, real fill events, broker safety events.

**Payload requirements extend**: Live trading events carry broker-native identifiers (broker order IDs, broker fill IDs, exchange timestamps). These are added to the event payload alongside the existing internal fields.

**Retention requirements strengthen**: Live trading fill records have permanent retention requirements due to potential regulatory and tax implications. The retention policy tiers defined in §13 account for this.

**Security requirements tighten**: The `LT_CREDENTIAL_RESOLVED` event records vault credential access. The audit system must handle live trading events with the same credential-hiding discipline applied to all other events.

### What Does NOT Change

**The audit record structure**: The common envelope defined in §10 (`audit_id`, `event_timestamp`, `actor`, `subject_id`, `session_id`, `strategy_id`, `event_payload`) is unchanged. Live trading events use the same structure.

**The taxonomy categories**: `FT_`, `PT_`, `LT_`, `GOV_`, `ADMIN_`, `FAILURE_` categories continue to serve the same roles. Live trading adds populated `LT_` events.

**The governance events**: `GOV_STRATEGY_APPROVED_FOR_LIVE` already exists in the taxonomy. Live trading activation consumes this existing event.

**The immutability rules**: Audit records for live trading are append-only, just as for all other modes.

**The query requirements**: The six query access patterns defined in §15 work equally for live trading events.

**The ownership model**: `LT_` events carry the same `user_id` (session owner), `actor`, and access control model.

The execution audit model is not a forward-testing-and-paper-trading audit model that will be replaced by a live trading audit model. It is the unified audit model that live trading activates a new event category within.

---

## 19. Non-Negotiable Constraints

The following constraints are absolute.

**No mutable audit history**: Audit records are append-only. No edit, update, or silent delete operations are permitted on audit records after creation. Corrections are new records that reference the original.

**No hidden execution paths**: Every execution action — every signal, every order, every fill, every position change, every account update — must produce an audit record. An execution action that produces no audit record is an architectural violation.

**No unaudited execution activity**: The absence of an audit record means the event either did not occur or was not recorded. Either is auditable — if an event should have occurred but its record is missing, that gap is itself evidence of a problem.

**No strategy promotion without evidence**: Strategy lifecycle advancement requires audit trail evidence. `GOV_STRATEGY_APPROVED_FOR_PAPER` and `GOV_STRATEGY_APPROVED_FOR_LIVE` events must reference the session IDs whose audit trails were reviewed. A promotion decision without referenced evidence is not valid.

**No execution mode bypasses**: The lifecycle gate events (`FT_ACTIVATION_DENIED`, `PT_ACTIVATION_DENIED`, `GOV_LIFECYCLE_TRANSITION_DENIED`) prove that gates were enforced. A promotion record without corresponding gate enforcement records is suspect.

**Credentials never in audit records**: Broker credentials, vault secrets, and API keys must never appear in any audit record, in any field, in any payload.

**`file_path` never in audit records**: The catalog ID is the sole durable dataset identity. `file_path` values must never appear in audit records.

---

## 20. Future Documents

### STRATEGY_PROMOTION_LIFECYCLE.md

This document is the direct consumer of the execution audit model.

It must define, drawing on the audit taxonomy established here:

**Minimum evidence requirements per gate**:
* For `validated → backtested`: minimum forward test session requirements (minimum duration, minimum bars evaluated, minimum signal count, required `FT_SESSION_COMPLETED` event)
* For `backtested → paper_tested`: minimum paper trading session requirements (minimum trade count, minimum session duration, required `PT_SESSION_COMPLETED` with final metrics, acceptable drawdown range)
* For `paper_tested → approved_for_live`: strictest requirements; multiple sessions recommended; explicit acknowledgment required

**Governance workflow**:
* Who may request promotion (the strategy owner)
* Who may review and approve (admin or superadmin role)
* Whether the reviewer must hold `require_admin_role` (consistent with existing admin governance model)
* What the reviewer must explicitly acknowledge before `GOV_STRATEGY_APPROVED_FOR_LIVE` is written

**Evidence completeness requirements**:
* Can a session with detected gaps be used as promotion evidence?
* Can a session with multiple `FT_PROVIDER_FAILURE` events be used as evidence?
* Is a session that ended in `failed` or `terminated` state admissible as evidence?
* What is the minimum gap between session completion and promotion review (to prevent immediate rubber-stamp approvals)?

**Promotion record requirements**:
* The `GOV_STRATEGY_APPROVED_FOR_LIVE` event requires an `explicit_acknowledgment_text` field. The promotion lifecycle document must specify the exact text that constitutes valid acknowledgment — the text that the approver must confirm before the event is written.

---

## Summary

```
AUDIT RECORD AS EVIDENCE
    Backtesting: reproducible → evidence can be re-derived
    Execution: non-reproducible → audit record IS the evidence

AUDIT TAXONOMY (6 categories)
    FT_   Forward testing events
    PT_   Paper trading events
    LT_   Live trading events (future)
    GOV_  Governance and promotion events
    ADMIN_  Administrative events (extending existing governance model)
    FAILURE_  Unrecoverable error events (cross-mode)

AUDIT RECORD STRUCTURE (common envelope)
    audit_id, event_type, event_timestamp, actor,
    subject_type, subject_id, session_id,
    strategy_id, strategy_version, user_id,
    execution_mode, event_payload, correlation_id

IMMUTABILITY
    Append-only. No edits. No silent deletes.
    Corrections are new records referencing the original.

RETENTION
    Governance records: permanent
    Live trading fills: permanent
    Paper trading records: until strategy archived + grace period
    Forward testing records: until strategy archived + grace period

QUERY REQUIREMENTS
    By session_id, strategy_id, user_id,
    promotion request, time range, event type, correlation_id

GOVERNANCE RELATIONSHIP
    Audit produces evidence.
    Promotion lifecycle consumes evidence.
    Audit never decides.

LIVE TRADING EXTENSION
    Same structure. Same taxonomy.
    LT_ events become active.
    No structural changes required.
```

Audit records are the institutional memory of execution.

Their completeness, immutability, and provenance are what make governance decisions trustworthy.

# EXECUTION_CONTRACT.md

## Purpose

This document defines the foundational execution architecture contract for QuantLab.

It is the authoritative reference for every future execution-capable subsystem:

* forward testing
* paper trading
* alert generation
* trade journaling
* broker integration
* live trading

This document establishes what execution is, what it is not, how it relates to the existing backtesting architecture, and the invariants that all future execution subsystems must respect.

This document is architecture-level.

It is intentionally implementation-agnostic.

Database schemas, API routes, broker-specific behavior, scheduler design, and WebSocket protocols belong in their respective implementation contracts. This document defines the conceptual contracts and governance constraints that those implementations must satisfy.

---

## Why This Document Exists

The backtesting engine is QuantLab's first and currently only execution-adjacent subsystem. It is a deterministic historical simulation — not execution. Future subsystems will process live or near-live market data and produce real or simulated actions in real time.

Without a foundational execution contract, those subsystems risk:

* allowing strategy logic to directly interact with broker APIs
* permitting uncontrolled or unaudited execution actions
* conflating execution modes with different safety requirements
* duplicating state management across subsystems without a common model
* bypassing the lifecycle governance that protects users and the platform
* building incompatible provenance records that cannot be inspected uniformly

This contract prevents those failures by establishing the architecture before any execution implementation begins.

---

## 1. What Execution Is — and Is Not

### What Execution Is

Execution is the processing of future market data after a strategy has been activated.

Every execution subsystem shares this property: it receives data that was not available when the strategy was composed, and it produces an action or record in response to that data.

Execution subsystems include:

* **Forward testing** — evaluating strategy signals against a live or near-live data stream, recording what signals would have been generated, taking no real action
* **Paper trading** — simulating order fills, positions, and portfolio state against a live or near-live data stream, in a fully simulated account
* **Live trading** — sending real orders to a real broker or exchange against live market data

All three operate against market data that arrives after strategy activation. All three produce output that must be owned, attributed, audited, and traceable.

### What Execution Is NOT

| Not this | Why |
|---|---|
| Backtesting | Backtesting is deterministic historical simulation over fixed datasets. Execution processes future data in real or near-real time. |
| Strategy authoring | Strategy logic is composed in the Composer layer; the execution layer consumes validated strategy definitions as inputs. |
| A data provider | The execution layer receives normalized market data from the data layer; it does not ingest or normalize raw provider data. |
| A broker | Execution subsystems may communicate with brokers through the Gateway layer; they do not contain broker-specific logic. |
| A frontend system | The frontend observes and controls execution sessions; it does not perform execution mechanics. |
| A risk management system | Risk rules are declared in the strategy definition and enforced by the execution environment; they are not invented by the execution layer. |

### The Critical Distinction from Backtesting

Backtesting:
* operates against historical data
* is deterministic and reproducible given identical inputs
* produces research evidence
* carries no real financial consequence
* failures are analytical failures

Execution:
* operates against future data as it arrives
* is inherently non-deterministic (market data, timing, fills cannot be precisely reproduced)
* produces records with real or simulated financial consequence
* carries governance, audit, and safety obligations that backtesting does not
* failures may carry financial or compliance consequences

This distinction is non-negotiable. Code or architecture that blurs the boundary between backtesting and execution is an architectural violation.

---

## 2. Execution Philosophy

All execution in QuantLab follows the same layered model.

```
Strategy Logic
    ↓
Execution Intent
    ↓
Execution Gateway
    ↓
Execution Environment
```

### Strategy Logic

Strategy logic is pure computation.

A strategy receives normalized market data and resolved feature values.

It produces `ExecutionIntent` objects.

That is the full extent of a strategy's responsibility in the execution context.

A strategy must never:

* communicate with a broker API directly
* communicate with an exchange API directly
* read from or write to an execution account
* query live market data independently
* interact with the frontend or any UI layer
* manage position or cash state
* apply fill mechanics, fees, or slippage

These responsibilities belong to the layers below strategy logic in the execution model.

This constraint is the same portability invariant established for the strategy tools builder layer. Strategy logic must remain portable across all execution modes — research, forward test, paper trading, live trading — without modification. A strategy that can only function in one execution mode is an architectural violation.

### Execution Intent

An `ExecutionIntent` is the output of strategy logic.

It is a declaration of what the strategy wants to happen, expressed independently of how it will be fulfilled.

Examples:
* "Enter long, size determined by declared position sizing, at current market"
* "Exit the current long position"
* "Do not act at this bar"

An `ExecutionIntent` carries no knowledge of the execution environment. It does not know whether it will be forwarded to a paper broker, a real broker, or recorded as a no-op.

### Execution Gateway

The Execution Gateway is the abstraction layer between strategy intents and execution environments.

It receives `ExecutionIntent` objects from the strategy evaluation layer.

It routes each intent to the appropriate execution environment based on the active session's execution mode.

It translates intents into actions appropriate to the environment.

It does not make analytical decisions. It does not modify intent logic. It is a routing and translation layer.

### Execution Environment

The Execution Environment is the layer that fulfills — or records — the intent.

In forward testing, the environment records that a signal was generated; no fill occurs.

In paper trading, the environment simulates fills, fees, slippage, and position state.

In live trading, the environment sends real orders to a real broker through the appropriate adapter.

The environment owns all state: positions, cash, equity, order history, fill history. Strategy logic must never own or manage execution state.

---

## 3. Execution Modes

QuantLab defines five execution modes. Each has a distinct purpose, data source, and safety profile.

### Research (Backtest)

**Purpose**: Exploratory hypothesis testing and strategy evaluation against historical data.

**Data source**: Historical normalized datasets (fixed at run time; immutable during the run).

**Output**: Deterministic, reproducible research artifacts. No real or simulated financial consequence.

**Safety profile**: Governed by the Backtesting Engine Contract. Validated strategy definition required. Full reproducibility contract applies.

**Notes**: Research mode is the only fully deterministic mode. It is not execution in the forward-data sense. It is described here for completeness as the base mode from which all other modes derive.

---

### Forward Test

**Purpose**: Validate that a strategy generates signals as expected on live or near-live data, without simulating fills or positions.

**Data source**: Live or near-live market data feed. Each bar arrives as it closes.

**Output**: Signal event records. No position state. No equity curve. No fills. An auditable record of what the strategy would have signaled.

**Safety profile**:
* No real orders. No simulated fills.
* Strategy activation requires `lifecycle_status >= validated`.
* Forward test sessions are user-owned and auditable.
* Session data is retained for provenance inspection.

**Non-determinism exposure**: Signal generation depends on the exact data received. Identical strategy definitions will not produce identical results across different forward test sessions unless market data is identical. This is expected and documented behavior.

---

### Paper Trading

**Purpose**: Evaluate a strategy under realistic execution mechanics — fills, fees, slippage, position state, equity — without placing real orders.

**Data source**: Live or near-live market data feed.

**Output**: Simulated trades, positions, equity curve, performance metrics — all in a fully simulated account with no real financial consequence.

**Safety profile**:
* No real orders. All fills are simulated.
* Strategy activation requires `lifecycle_status >= backtested`.
* Paper trading sessions are user-owned, ownership-scoped, and fully auditable.
* Simulation assumption set must be declared and recorded before session activation.
* Session data is retained for provenance and promotion review.

**Non-determinism exposure**: Fill timing, slippage, and position state depend on live data arrival and session-level timing. Results cannot be deterministically reproduced. Session records must preserve enough provenance to explain what happened, even if exact reproduction is not possible.

---

### Alert Generation

**Purpose**: A constrained forward-test variant that produces notifications rather than execution records. No position state. No fills. User receives alerts when signals fire.

**Data source**: Live or near-live market data feed.

**Output**: Alert events (signal type, symbol, timestamp, feature values at signal time). No fill simulation.

**Safety profile**: Same lifecycle requirements as forward testing. User-owned. Auditable. Alert delivery mechanism is external to the execution contract.

---

### Live Trading

**Purpose**: Execute real orders against a real broker or exchange.

**Data source**: Live market data feed.

**Output**: Real fills, real positions, real P&L. Broker-acknowledged order records.

**Safety profile** (highest):
* Strategy must be `lifecycle_status = approved_for_live`.
* Explicit user authorization required per session activation.
* No automatic promotion from paper trading to live trading.
* All intents must pass through the Execution Gateway before reaching any broker adapter.
* Every order, fill, and position change must be audited.
* Session-level risk limits must be declared and enforced before the first bar is processed.
* Hard-stop mechanisms must be available and tested before live session activation.
* No live execution without a complete, verified broker credential in the user's vault.

**Non-determinism exposure**: Live trading results depend on broker execution quality, market conditions, latency, and partial fill behavior. Full reproducibility is not possible or expected. Provenance must capture enough context to reconstruct what was intended and what was filled.

---

## 4. Core Execution Objects

The following objects are the conceptual building blocks of the execution architecture. They are defined here as contracts, not implementations. All future execution subsystems must reason in terms of these objects.

---

### ExecutionIntent

**What it is**: The output of strategy logic at a given evaluation step. Declares what the strategy wants to happen.

**Key properties** (conceptual):
* Direction (long entry, long exit, short entry, short exit, no action, close all)
* Intended size basis (percentage of equity, fixed quantity, full position) — not a computed size
* Urgency / order type preference (market, limit, conditional) — advisory; fulfillment is the gateway's responsibility
* Strategy step identity (which bar, which rule fired)
* Timestamp of the evaluation step

**What it is NOT**:
* An order. Orders are created by the gateway.
* A decision about fill price. Fill price is determined by the execution environment.
* A position management command. Position state is owned by the execution environment.

---

### SignalEvent

**What it is**: A record that a strategy's rule logic evaluated to true at a specific bar during an active execution session.

**Key properties** (conceptual):
* Session identity
* Bar timestamp and index
* Rule or rules that fired
* Feature values at signal time
* Direction implied by the signal
* Whether an `ExecutionIntent` was generated from this signal (some signals may be suppressed by filters or risk rules)

**Retention**: Signal events must be retained for the lifetime of the execution session and must be accessible for audit and research inspection.

---

### ExecutionEvent

**What it is**: A record of an action taken by the Execution Gateway in response to an `ExecutionIntent`. One intent may produce zero, one, or multiple execution events (e.g., a partial fill produces multiple fill events).

**Key properties** (conceptual):
* Session identity
* The originating `ExecutionIntent` reference
* Action type (order submitted, fill received, order cancelled, order rejected)
* Execution price (for fills)
* Quantity (for fills)
* Timestamp of the action
* Gateway-assigned identifier (broker order ID for live; simulated ID for paper)
* Fee and slippage applied (for simulated or reported fills)

**Retention**: All execution events must be retained immutably. No execution event may be deleted or modified after creation.

---

### PositionState

**What it is**: The current state of an open position within an execution session.

**Key properties** (conceptual):
* Session identity
* Symbol and instrument context
* Side (long / short)
* Quantity
* Average entry price
* Unrealized P&L at the most recent evaluation bar
* Time in position
* Entry execution event reference

**Ownership**: Owned by the execution environment. Strategy logic never reads or writes position state directly.

---

### AccountState

**What it is**: The simulated or real account state associated with an execution session at a point in time.

**Key properties** (conceptual):
* Session identity
* Cash (available capital excluding open position value)
* Equity (cash + unrealized position value)
* Net exposure
* Peak equity achieved to date in the session
* Current drawdown from peak equity
* Maximum drawdown experienced in the session
* Timestamp of this snapshot

**Ownership**: Owned by the execution environment. Strategy logic never reads or writes account state directly. Account state snapshots must be retained at a cadence sufficient for equity curve reconstruction.

---

### ExecutionRecord

**What it is**: The complete, immutable lifecycle record of a single trade within an execution session — from intent generation through final exit.

**Key properties** (conceptual):
* Session identity
* Entry: signal event reference, execution event reference, fill price, fill quantity, fee, timestamp
* Exit: signal event reference, execution event reference, fill price, fill quantity, fee, timestamp, exit reason
* Realized P&L
* Hold duration
* Strategy evaluation context at entry and exit (feature values, rule that fired)

**Retention**: Execution records are immutable after the trade closes. They form the primary evidence basis for post-session analysis and any lifecycle promotion review.

---

### ExecutionSession

**What it is**: The container for all activity associated with a single activated execution of a strategy in a declared mode.

**Key properties** (conceptual):
* Session identity (unique, stable across the session lifecycle)
* Owner user identity (from JWT at session creation — never from client-supplied payload)
* Execution mode (forward_test, paper_trading, live_trading)
* Strategy identity and version at activation time
* Strategy lifecycle status at activation time
* Data source identity (provider, symbol, timeframe, or catalog reference)
* Simulation assumption set (declared before activation; immutable after activation)
* Session lifecycle status (pending, active, paused, completed, terminated, error)
* Activation timestamp
* Completion or termination timestamp
* All `SignalEvent`, `ExecutionEvent`, `PositionState` snapshots, `AccountState` snapshots, and `ExecutionRecord` objects produced during the session

---

## 5. Execution Session Model

### Purpose

An `ExecutionSession` is the durable, ownership-scoped container for a single execution activation.

Every execution artifact produced — signals, fills, position snapshots, account snapshots, trade records — exists within the context of a session.

A session is the unit of ownership, the unit of auditability, and the unit of lifecycle review.

### Ownership

Every session is owned by a specific user.

Session ownership is established at creation time from the authenticated user's identity (JWT). No client-supplied user ID is accepted. No shared or unowned sessions exist.

Wrong-owner access to a session is indistinguishable from a not-found response. The information-hiding principle established in the ownership model applies to all execution sessions.

A session cannot be transferred between owners.

### Lifecycle

```
created
    → pending     (configured; not yet processing bars)
    → active      (processing live data; intents being evaluated)
    → paused      (temporarily suspended; may be resumed)
    → completed   (session reached its natural end or was gracefully stopped)
    → terminated  (session was forcibly stopped; may be due to error or user request)
    → error       (session entered an unrecoverable error state)
```

State transitions must be validated. Prohibited transitions (e.g., `completed → active`) must be rejected.

All state transitions must be audited.

A completed or terminated session is read-only. No new execution events may be appended to a completed or terminated session.

### Persistence

All execution sessions and their constituent artifacts must be durably persisted.

A session that loses its record due to process restart, storage failure, or application error is an architectural failure.

The current JSON-backed storage model is sufficient for development and early deployment. Migration to a durable relational store is expected as session volume grows.

Live trading sessions have the strictest persistence requirements: every execution event must be persisted before the response to the originating data event is considered complete. Lost fill records in a live session are unacceptable.

### Audit

Every session must produce a complete, immutable audit trail:

* Session creation (who, when, what strategy, what mode, what assumptions)
* Every state transition (with timestamp and actor)
* Every `SignalEvent` generated
* Every `ExecutionEvent` generated
* Every trade opened and closed
* Session completion or termination (with reason)

The audit trail must be retained for the session's full lifetime and must be accessible through the platform's inspection interfaces.

---

## 6. Execution Gateway Contract

The Execution Gateway is the abstraction boundary between strategy intents and execution environments.

### Purpose

The gateway ensures that:

* Strategy logic never communicates directly with any broker or exchange
* Different execution environments are substitutable without changing strategy code
* All intents pass through a single controlled routing layer
* Execution actions can be monitored, filtered, and audited at a single point

### Interface Contract (conceptual)

The gateway accepts `ExecutionIntent` objects from the strategy evaluation layer.

For each intent, it:
1. Validates that the intent conforms to the session's declared constraints (e.g., risk limits)
2. Translates the intent into the appropriate action for the active execution environment
3. Routes the action to the appropriate adapter
4. Receives the result (simulated fill, broker acknowledgment, or record)
5. Produces one or more `ExecutionEvent` objects
6. Updates the session's `PositionState` and `AccountState`
7. Emits the appropriate audit event

### Future Implementations

The gateway architecture is designed to support the following future adapter implementations, each substitutable without changing strategy logic:

**PaperBrokerAdapter**
Simulates fills, fees, and slippage locally. No network calls. Deterministic simulation mechanics. The default adapter for paper trading sessions.

**IBKRAdapter**
Translates execution intents into IBKR-native order types. Handles IBKR-specific margin rules, order acknowledgment, and fill reporting. Credentials resolved through the vault.

**BinanceAdapter**
Translates execution intents into Binance-native order types. Handles Binance-specific precision rules, rate limits, and WebSocket fill streams. Credentials resolved through the vault.

**FutureBrokerAdapters**
The gateway contract is open to additional adapter implementations. Each adapter must implement the same gateway interface contract.

### Gateway Invariants

* Strategy logic must never hold a reference to a gateway adapter.
* The gateway must never expose broker credentials to the strategy layer.
* The gateway must never allow an intent to bypass audit.
* The gateway must never silently discard an intent. Every intent must produce at least one `ExecutionEvent` (even if that event records "intent not acted upon").
* The gateway must respect session-level risk limits before routing any intent. Intents that violate declared risk limits must be rejected with an audit record, not silently dropped.

---

## 7. State Management Principles

Execution state — the current truth about positions, cash, equity, orders, fills, and execution history — is owned exclusively by the execution environment.

### What the Execution Environment Owns

**Positions**: The current set of open positions. Each position's size, entry price, current value, and unrealized P&L.

**Cash**: The available capital not committed to open positions.

**Equity**: Cash plus the current marked value of all open positions.

**Orders**: Any pending orders submitted to a broker but not yet filled or cancelled.

**Fills**: The historical record of every fill received for this session.

**Execution History**: The complete ordered sequence of all `ExecutionEvent` objects for this session.

### What Strategy Logic Must Never Own

Strategy logic must never:

* Read current position state to decide whether to generate an intent
* Read current cash or equity to size a position
* Track open orders
* Modify fill records
* Accumulate its own history of past signals or fills

These are execution environment responsibilities. Strategy logic that incorporates position state into its signal logic is an architectural violation because it breaks the portability invariant: the strategy would behave differently depending on which execution environment is running it.

If a strategy requires access to position context — for example, to generate exit signals based on hold duration — this must be modeled as a declared strategy feature (e.g., a declared maximum hold period in the strategy definition) that the execution environment enforces, not as direct state access by the strategy.

### State Snapshot Requirements

The execution environment must produce state snapshots at a cadence sufficient to reconstruct the equity curve for any session.

Minimum snapshot cadence: one `AccountState` snapshot per bar processed.

For live trading: snapshots must be persisted durably before the next bar is processed.

---

## 8. Determinism Rules

### Backtesting Is Deterministic

The reproducibility contract established in the Backtesting Engine Contract applies in full.

Given identical inputs (strategy definition, tool versions, dataset, parameter set, simulation assumptions, engine version), the backtesting engine produces numerically identical results.

This is a non-negotiable property of research-mode execution.

### Forward Testing, Paper Trading, and Live Trading Are NOT Deterministic

This is expected, documented, and accepted behavior.

**Sources of non-determinism in forward testing:**
* Market data arrives at real time. The exact data received depends on provider latency, feed quality, and the precise moment each bar closes.
* Session timing means two identical strategy definitions activated at different times will evaluate different bars.

**Sources of non-determinism in paper trading:**
* All of the above, plus simulated fill timing and slippage which depend on the real market prices present when each intent is processed.

**Sources of non-determinism in live trading:**
* All of the above, plus real broker execution quality, partial fills, network latency, and order book state at fill time.

### Implications

1. **Session records replace reproducibility as the evidence contract.** Because forward-test and paper-trading results cannot be precisely reproduced, the session record itself — all signal events, execution events, position snapshots, account snapshots — is the authoritative evidence. Sessions must be retained intact.

2. **Comparison between sessions must be done with caution.** Two paper-trading sessions of the same strategy on the same symbol will produce different results because they processed different bars at different times. This is not a defect; it is the nature of live data.

3. **Promotion review must account for non-determinism.** Reviewers evaluating paper-trading results for lifecycle promotion must understand that results reflect one specific session, not a canonical outcome of the strategy.

4. **Non-determinism does not exempt sessions from provenance requirements.** Every session must record enough context to understand what happened, even if what happened cannot be reproduced exactly.

5. **Backtesting remains the vehicle for reproducible strategy evaluation.** Analysts who need reproducible evidence must run backtests, not forward tests or paper trades.

---

## 9. Ownership Requirements

All execution sessions and their constituent artifacts are user-owned resources.

### Ownership Rules

* Every execution session is associated with exactly one user at creation time.
* Ownership is established from the authenticated user's JWT. No client-supplied owner identity is accepted.
* A session's owner cannot be changed after creation.
* No shared execution sessions exist. Multiple users do not co-own a session.
* No unowned sessions exist. A session without a valid owner identity is an architectural defect.

### Access Control

Ownership-scoped access control follows the same model established for strategy drafts, dataset catalog entries, and backtest runs:

* Wrong-owner access produces a not-found response, indistinguishable from a genuinely missing session.
* Only the owning user may view, control, or export a session.
* Admins may access any user's sessions through admin-scoped inspection interfaces only, subject to the existing admin governance model.

### No Shared Execution Environments

A user's execution session must not share position state, account state, order history, or fill records with any other user's session.

Shared execution environments (pool accounts, omnibus accounts, shared paper trading accounts) are not supported. Each session operates in a fully isolated context.

### Legacy Resources

The ownership model established for strategy drafts (resources with `user_id=None` are inaccessible to all authenticated users) applies to execution sessions. Sessions without a valid owner identity are inaccessible through all user-facing interfaces.

---

## 10. Provenance Requirements

Every execution artifact must carry sufficient provenance to answer:

* Which strategy produced this?
* What version of the strategy?
* What was the strategy's lifecycle status at activation?
* What data source was being evaluated?
* What execution mode was active?
* What simulation assumptions were declared?
* What credentials (if any) were used?
* When did this session start and end?
* Who activated this session?

### Mandatory Provenance Fields

All execution sessions must record:

**Strategy Provenance**
* `draft_id` — the strategy draft identity at activation
* `draft_snapshot` — a point-in-time snapshot of the strategy definition as it existed at activation (not a live reference; the definition must not change during a session)
* `strategy_lifecycle_status` — the lifecycle status of the strategy at activation time

**Data Source Provenance**
* `source_mode` — provider or catalog
* `provider_name` — if provider mode
* `symbol`, `timeframe` — instrument and timeframe context
* `catalog_id` — if catalog mode (not `file_path`; the catalog ID is the sole durable identity)

**Session Provenance**
* `execution_mode` — forward_test, paper_trading, live_trading
* `activated_by` — user ID from JWT at session creation
* `activation_timestamp` — UTC timestamp of session activation
* `engine_version` — the version of the execution engine at activation time

**Assumption Provenance**
* Full declared simulation assumption set (for paper trading and live trading)
* Declared risk limits
* Declared position sizing model and parameters

### File Path Never in Provenance

In alignment with the platform-wide invariant: `file_path` must never appear in any execution session record or artifact. The catalog ID is the sole durable identity for catalog-sourced datasets.

### Credential Reference Provenance

For live trading sessions that require broker credentials: the `credential_id` from the user's vault must be recorded in the session provenance. The `encrypted_secret` and decrypted credential value must never appear in any session record.

---

## 11. Audit Requirements

All execution sessions must produce a complete, immutable audit trail through the platform's existing `emit_audit_event()` infrastructure.

### Mandatory Audit Event Categories

**Session Lifecycle**
* Session created
* Session activated (started processing bars)
* Session paused
* Session resumed
* Session completed gracefully
* Session terminated by user
* Session terminated due to error (with error category recorded)
* Session state transition denied (invalid transition attempted)

**Strategy Activation**
* Strategy lifecycle status at activation (for promotion-path review)
* Activation approved (when explicit approval is required)
* Activation denied (with reason)

**Execution Actions**
* Intent generated (signal fired; intent produced)
* Intent suppressed (signal fired; intent blocked by risk rule or filter — with reason)
* Order submitted (for live trading; per order)
* Order filled (per fill; with price, quantity, fee)
* Order partially filled
* Order rejected by broker
* Order cancelled
* Position opened
* Position closed
* Position state snapshot (at declared cadence)

**Risk and Safety**
* Risk limit checked
* Risk limit breach (session-level risk limit exceeded; session stopped)
* Unauthorized execution attempt blocked (strategy not at required lifecycle status)
* Credential resolution used (vault credential accessed for live session)
* Hard-stop activated

**Governance**
* Session exported (user requested session data export)
* Session reviewed for promotion (reviewer accessed session for lifecycle promotion review)

### Reference Document

The complete execution audit schema and event taxonomy will be defined in `EXECUTION_AUDIT_MODEL.md` (see §14). This section defines the mandatory categories. The referenced document defines the specific event kinds and their required payload fields.

---

## 12. Safety Constraints

The following safety constraints are non-negotiable for all execution subsystems.

### No Uncontrolled Live Execution

A live trading session must not be activated without:
* Strategy at `lifecycle_status = approved_for_live`
* Explicit user confirmation of session parameters
* Valid, active broker credential in the user's vault
* Declared and confirmed risk limits
* A hard-stop mechanism that has been verified

Automatic activation of live trading from any other state is prohibited.

### No Direct Strategy-to-Broker Communication

Strategy logic must never communicate with a broker API, exchange API, or any execution account.

The execution model is: strategy produces intents; the gateway routes intents; adapters fulfill intents.

Any code path that allows strategy logic to bypass the gateway is an architectural violation.

### No Automatic Promotion Between Execution Modes

Completing a forward test does not automatically activate paper trading.

Completing a paper-trading session does not automatically activate live trading.

Every advancement along the execution mode path requires explicit human authorization.

### No Bypass of Governance Workflow

The strategy lifecycle governs which execution modes a strategy is eligible for.

The lifecycle state machine defined in `STRATEGY_PROMOTION_LIFECYCLE.md` (see §14) is the authority.

An execution subsystem must not implement a bypass path that allows a strategy to enter an execution mode it has not been explicitly authorized for.

### No Hidden Execution Paths

Every execution session must be visible to the session owner through the platform's inspection interfaces.

No "shadow" execution paths that produce fills, positions, or trades without appearing in the user's session history are permitted.

If an execution action cannot be surfaced in the session record, it must not be taken.

### No Unvalidated Strategies in Forward or Live Execution

The same principle that prevents draft strategies from entering the backtesting engine applies to forward testing and live trading.

A strategy must hold a current backend validation record to enter forward testing or paper trading.

A strategy must be explicitly approved for live trading before any live execution session can be activated.

### No Credential Leakage

Broker credentials stored in the user's vault must never appear in:
* Session records
* Execution event payloads
* Audit logs (credential ID may appear; the secret must not)
* API responses

The vault's `resolve_secret()` internal-only contract applies in full to the execution layer.

---

## 13. Relationship to Existing Architecture

The execution contract relates to every existing layer of the QuantLab architecture.

### StrategyDraft

`StrategyDraft` is the source of strategy definitions consumed by execution sessions.

At session activation, the current `StrategyDraft` definition is snapshotted into the session's provenance. The session's behavior is governed by the snapshotted definition, not the live draft. Changes made to the draft after session activation must not affect the active session.

The draft's `lifecycle_status` is read at activation time to verify execution eligibility. This is an immutable read — session activation does not change the draft's lifecycle status. Lifecycle status changes are governed by the strategy promotion workflow.

### BacktestRun

`BacktestRun` is the primary evidence artifact for lifecycle advancement toward forward testing and paper trading.

The execution contract does not change the structure or behavior of backtest runs.

Backtest results inform but do not automatically authorize execution mode activation. Human review of backtest results and explicit promotion approval remain required.

### Ownership Model

All execution sessions follow the same ownership model as strategy drafts, catalog entries, and backtest runs:

* `user_id` always from JWT — never from client-supplied payload
* Wrong-owner access → HTTP 404 (same as not-found; information hiding)
* Legacy resources with `user_id=None` are inaccessible

This model is extended, not modified, by the execution contract.

### Vault

The vault provides broker credentials for live execution sessions.

Vault access for execution follows the same constraints as vault access for market data:
* `resolve_secret()` is internal to `VaultService`; never called from route handlers
* `credential_id` is the sole execution-layer reference to a credential
* Decrypted credential values never appear in session records, audit events, or API responses

### Admin Governance

Execution sessions are user-owned resources subject to the same admin visibility model as other user resources.

Admin governance defines who can approve strategy lifecycle advancement toward execution modes. The admin tier (admin, superadmin) retains authority to manage user access and strategy promotion regardless of their own subscription status, consistent with the entitlement separation model.

Execution sessions must not bypass admin governance. A user cannot self-approve strategy promotion to live trading.

### Provider Architecture

Execution sessions consume live market data through the provider abstraction layer (`ProviderAdapterFactory`, `OHLCVService`).

The execution layer does not introduce new provider dependencies. It consumes the same normalized data schemas already established.

Live and near-live data ingestion (streaming, tick-to-candle aggregation) will require new provider adapter implementations. Those implementations must conform to the existing provider abstraction contracts — they do not require changes to the execution contract.

### Strategy Lifecycle

The strategy lifecycle state machine governs execution eligibility.

```
draft
    → validated          (backend validation passed)
    → backtested         (promotion-grade backtest completed and reviewed)
    → paper_tested       (paper trading session completed and reviewed)
    → approved_for_live  (explicit promotion approval granted)
    → archived           (terminal; no execution permitted)
```

Eligibility for execution modes:
* Forward testing requires `lifecycle_status >= validated`
* Paper trading requires `lifecycle_status >= backtested`
* Live trading requires `lifecycle_status = approved_for_live`

`archived` is a terminal state. No execution session may be activated for an archived strategy.

---

## 14. Future Documents

The execution contract is the foundational document. The following documents will elaborate specific subsystems and should be written before those subsystems are implemented.

### FORWARD_TESTING_ARCHITECTURE.md

Defines the detailed architecture of the forward testing subsystem.

Must cover:
* The bar arrival model (how live bars are received and normalized)
* Signal event recording schema
* Session lifecycle and persistence model
* No-fill confirmation (enforcement that no fill mechanics exist in forward testing)
* Comparison methodology with backtest results
* Promotion evidence model (what constitutes a sufficient forward test record)

### PAPER_TRADING_ARCHITECTURE.md

Defines the detailed architecture of the paper trading subsystem.

Must cover:
* The paper broker adapter interface
* Fill simulation mechanics and timing model
* Position and account state management
* Equity curve construction
* Session comparison across paper-trading sessions
* Risk limit enforcement
* Promotion evidence model (what constitutes a sufficient paper trading record)

### EXECUTION_AUDIT_MODEL.md

Defines the complete execution audit event taxonomy.

Must cover:
* All `AuditEventKind` values specific to execution
* Required payload fields for each event
* Retention policy for execution audit records
* Query interface requirements (how audit records are accessed for inspection)

### STRATEGY_PROMOTION_LIFECYCLE.md

Defines the complete strategy promotion workflow from draft to approved-for-live.

Must cover:
* Explicit transition table (which states allow which transitions)
* Evidence requirements at each promotion gate
* Human approval workflow and authorization model
* Demotion and archival rules
* Audit requirements for each transition

---

## Summary of Execution Architecture Responsibilities

```
INPUT GATE (session activation)
    → Verify: strategy lifecycle status meets execution mode requirement
    → Snapshot: strategy definition into session provenance
    → Declare: simulation assumptions (paper trading / live trading)
    → Declare: risk limits
    → Resolve: broker credentials through vault (live trading only)
    → Record: full session provenance

SESSION PROCESSING (per bar)
    → Receive: normalized bar from data layer
    → Execute: strategy logic against current bar + resolved features
    → Produce: ExecutionIntent (or no-action)
    → Gate: intent against declared risk limits
    → Route: intent through Execution Gateway
    → Fulfill: intent (signal record / simulated fill / real order)
    → Produce: ExecutionEvent(s)
    → Update: PositionState, AccountState
    → Snapshot: AccountState
    → Audit: all events

SESSION CLOSE
    → Finalize: all open position records
    → Compute: session-level metrics (paper trading / live trading)
    → Produce: session summary artifact
    → Record: terminal audit event
    → Transition: session lifecycle to completed or terminated
    → Retain: full session record immutably

ENFORCEMENT (invariants that must never be violated)
    → No strategy-to-broker direct communication
    → No execution without lifecycle authorization
    → No automatic promotion between execution modes
    → No unowned sessions
    → No credential leakage in any artifact
    → No file_path in any session record
    → No hidden execution paths
    → Non-determinism acknowledged; provenance compensates
```

The execution contract transforms validated strategy definitions into live evidence.

That evidence is only as trustworthy as the platform's commitment to ownership, auditability, and governance discipline.

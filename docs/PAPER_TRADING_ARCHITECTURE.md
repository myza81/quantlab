# PAPER_TRADING_ARCHITECTURE.md

## Purpose

This document defines the architecture of the Paper Trading subsystem for QuantLab.

Paper trading is the second execution mode beyond backtesting and the direct extension of forward testing. It introduces, for the first time in the QuantLab execution model, the concepts of a simulated account, positions, orders, fills, and equity — all operating against live market data without any real financial consequence.

This document:

* defines what paper trading is and is not
* establishes the paper trading session architecture
* defines the paper account model
* defines position, order, and fill contracts
* defines the execution intent flow and the `PaperBrokerAdapter`
* defines the fill simulation philosophy
* defines account state ownership rules
* defines ownership, provenance, persistence, and audit requirements
* defines the failure model
* establishes the relationship to forward testing and to future live trading

This document is architecture-level.

It extends `docs/EXECUTION_CONTRACT.md` and `docs/FORWARD_TESTING_ARCHITECTURE.md` and is subordinate to both.

All invariants defined in the Execution Contract apply in full. All session architecture decisions established in the Forward Testing Architecture are inherited and extended here.

No implementation. No database schema. No broker design. No WebSocket protocol. No alert engine. No trade journal design. Architecture only.

---

## Why This Document Exists

Forward testing validates that a strategy generates signals as expected under live market conditions. It does not validate execution behavior: how the strategy performs when signals are actually acted upon, how position sizing interacts with real equity curves, whether the declared cost model produces realistic results, or how the strategy's risk rules behave when positions are open.

Paper trading fills that gap. It is execution rehearsal — the closest analog to live trading that carries no real financial consequence.

Without a formal architecture, a paper trading implementation risks:

* conflating forward testing's signal records with execution records, producing a hybrid that does neither well
* building position state ownership into strategy logic, violating the portability invariant
* using the backtesting fill model without adapting it to live bar delivery, producing unrealistic or incorrect fills
* allowing fills, positions, and equity to exist without ownership or audit, making promotion review impossible
* creating a paper trading architecture that does not generalize to live trading, requiring a rewrite when the live trading phase arrives

This document prevents those failures by establishing the architecture once, correctly, before implementation begins.

---

## 1. Purpose of Paper Trading

### Why Forward Testing Is Insufficient

Forward testing answers: "Does this strategy generate signals as expected in live conditions?"

Paper trading answers: "Does this strategy behave acceptably when signals are acted upon — in terms of position sizing, capital utilization, equity drawdown, and risk compliance — under live market conditions?"

Forward testing cannot answer the paper trading questions because it produces no fills, no positions, and no equity. Specifically:

**Position sizing under live conditions**: Backtesting evaluates position sizing against a full historical dataset at once. Paper trading evaluates position sizing bar by bar as live bars arrive. The interaction of live volatility, declared position size parameters, and cash balance may produce different outcomes than backtesting projected.

**Equity drawdown in real time**: A backtesting equity curve is computed retrospectively. A paper trading equity curve develops in real time, exposing the strategy to extended drawdown periods that the user must observe and accept before committing real capital.

**Order rejection behavior**: A paper trading session may have insufficient cash to fill an intended position (due to open positions consuming capital). Order rejections under real capital constraints are only observable in execution, not in forward testing.

**Risk rule interaction with position state**: A strategy's exit rules and risk limits are evaluated against actual open positions in paper trading. In forward testing, there are no positions, so risk rules have no open-position context to evaluate against.

**Strategy execution discipline**: Paper trading reveals whether the user and the strategy can tolerate the psychological and operational reality of watching simulated positions open, draw down, and close. This is not measurable in forward testing or backtesting.

### What Paper Trading Validates

Paper trading validates:

* **Execution behavior**: that the strategy's signals translate into reasonable simulated fills under declared execution assumptions
* **Position management**: that the strategy correctly opens, manages, and closes positions; that exit rules fire when expected
* **Capital utilization**: that position sizing leaves adequate cash for subsequent positions; that the declared sizing model interacts correctly with live equity changes
* **Risk behavior**: that declared risk limits (maximum positions, maximum drawdown stop) function correctly when positions are live
* **Strategy execution discipline**: that the strategy performs acceptably across a sustained live observation period before capital is committed

Paper trading does not validate actual broker execution quality, real order routing latency, or slippage under production market conditions. Those can only be observed in live trading.

---

## 2. What Paper Trading Is Not

| Not this | Why it is excluded |
|---|---|
| Live trading | No real orders are placed. No broker credentials are used in order routing. No real account is affected. |
| Broker execution | The `PaperBrokerAdapter` simulates fills locally. It does not communicate with any brokerage, exchange, or clearing system. |
| Exchange execution | There is no exchange connection, no order book, no market microstructure simulation. |
| Account funding | Paper accounts are initialized with a declared starting equity. There is no deposit, withdrawal, or funding mechanism. |
| Production approval | A completed paper trading session is evidence for a promotion review. It is not automatic approval for live trading. |
| Strategy promotion | Strategy lifecycle advancement requires explicit human authorization. Completing a paper trading session does not promote the strategy. |
| Compliance approval | Compliance review is a separate governance stage. Paper trading does not constitute compliance clearance. |
| A second backtester | Paper trading evaluates only bars that arrive after session activation. It does not replay historical data. |
| A live trading simulator | Paper trading does not simulate broker-specific behavior (order types, margin rules, shorting restrictions). It simulates generic fill mechanics. |

---

## 3. Paper Trading Philosophy

Paper trading validates execution behavior. It does not validate real broker performance.

The distinction matters because:

* Real broker performance — fill quality, latency, rejection reasons, partial fills at scale — can only be observed by placing real orders
* Paper trading simulates idealized generic execution: market orders fill at a declared price model (next bar open or current close), fees are declared rates, slippage is a declared value
* The goal is not to predict exact live trading results. The goal is to validate that the strategy's logic, position sizing, and risk rules produce acceptable behavior across a sustained live observation period

**What paper trading is designed to detect:**

**Execution model compatibility**: Does the strategy's signal timing interact correctly with the declared fill timing model? A strategy that assumes immediate fill at signal-bar close but is configured for next-bar-open fill will show a discrepancy between expected and observed entry prices.

**Capital sufficiency**: Does the strategy's position sizing model leave adequate cash for operations? A strategy that sizes positions at 100% of equity will reject all subsequent signals until the first position closes.

**Drawdown tolerance**: Does the simulated equity curve remain within the user's acceptable drawdown range under live conditions? A strategy may have performed acceptably in backtesting but may exhibit sustained drawdown under current market conditions.

**Exit discipline**: Do exit rules fire reliably when positions are open? In backtesting, exits are evaluated over a full historical window; in paper trading, exits must fire at the correct live bar.

**Fill simulation transparency**: The fill simulation must be simple enough that the user can understand exactly why any fill occurred at the price and time it did. Black-box fill simulation produces results that cannot be reasoned about.

Paper trading results are not evidence that the strategy will produce the same results in live trading. They are evidence that the strategy's execution model is coherent, that its risk rules function correctly, and that its capital utilization is reasonable.

---

## 4. Paper Trading Session

A `PaperTradingSession` is the durable, ownership-scoped container for all activity in a single paper trading activation.

`PaperTradingSession` inherits all fields from `ForwardTestSession` and extends them with account, position, order, and fill management.

### Inherited Fields (from ForwardTestSession)

The following fields carry the same definition and the same invariants as defined in `FORWARD_TESTING_ARCHITECTURE.md` §4:

* `session_id`
* `user_id`
* `strategy_snapshot`
* `strategy_version`
* `lifecycle_status_at_activation`
* `source_mode`
* `provider_name`
* `catalog_id`
* `symbol`
* `timeframe`
* `activation_timestamp`
* `last_processed_bar_timestamp`
* `warmup_bars_required`
* `status`
* `error_detail`
* `created_timestamp`
* `updated_timestamp`

### Extended Fields (paper trading additions)

**`account_id`**
The identifier of the `PaperAccount` associated with this session. Established at session creation. A paper account is associated with exactly one session at a time.

**`simulation_assumptions`**
The complete, declared set of execution mechanics assumptions for this session. Must be declared before activation and is immutable after activation.

Includes:
* `fill_timing_model` — when fills are applied relative to the signal bar (`signal_bar_close`, `next_bar_open`)
* `fee_mode` — `none`, `flat`, or `percentage`
* `fee_value` — the declared fee per trade or fee rate
* `slippage_mode` — `none`, `fixed`, or `percentage`
* `slippage_value` — the declared slippage amount or rate
* `position_size_mode` — `equity_fraction`, `fixed_quantity`, or `fixed_cash`
* `position_size_value` — the declared sizing parameter

**`max_concurrent_positions`**
The declared maximum number of simultaneously open positions. Intents that would exceed this limit are rejected.

**`max_drawdown_stop_pct`**
An optional declared session-level drawdown stop threshold. If the session's equity drawdown from its peak exceeds this percentage, the session is paused and the user is notified. Null if no drawdown stop is configured.

**`starting_equity`**
The initial cash balance of the paper account at session activation. Declared at session creation. Immutable after activation.

**`session_type`**
`paper_trading`. Distinguishes paper trading session records from forward test session records in storage.

### Assumption Immutability

`simulation_assumptions` must be declared completely before session activation and must not be modifiable after the session transitions to `running`.

Changing execution assumptions mid-session would make the session's execution record incoherent — fills before and after the change would have been computed under different assumptions, making the trade history uninterpretable as a unified record.

If a user needs to change execution assumptions, they must stop the current session and create a new one.

### What Is NOT in the Session Record

All exclusions from `ForwardTestSession` apply.

Additionally:
* No broker account identifiers (paper accounts are internal to QuantLab)
* No real money amounts
* No broker credential references (paper trading requires no broker credentials)

---

## 5. Session Lifecycle

### States

Paper trading uses the same six-state lifecycle defined for forward testing, with identical state names and transition semantics:

```
created
    → pending         (session and account configured; not yet activated)
    → running         (actively polling; evaluating strategy; routing intents through PaperBrokerAdapter)
    → paused          (polling suspended; open positions frozen in place; session record intact)
    → completed       (session stopped gracefully; all open positions closed at close of last bar)
    → failed          (unrecoverable error; session record preserved)
    → terminated      (forcibly stopped; open positions closed at last known price)
```

### Differences from Forward Testing Lifecycle

**Paused state with open positions**: When a paper trading session is paused, open positions remain in their current state. Their unrealized P&L is frozen at the last processed bar's close. Positions do not automatically close on pause.

**Completed state position closure**: When a session transitions to `completed`, all open positions are force-closed at the close price of the last processed bar. This generates `PaperFill` records with `execution_reason = session_end_close`. Realized P&L from these forced closes is included in the session's final metrics.

**Drawdown stop transition**: If `max_drawdown_stop_pct` is configured and the session equity drawdown exceeds the threshold, the session transitions to `paused` (not `failed`) with `DRAWDOWN_STOP_TRIGGERED` audit event. The user is notified. They may review the situation and resume or stop the session.

### Allowed Transitions

Identical to `ForwardTestSession` allowed transitions (see `FORWARD_TESTING_ARCHITECTURE.md` §5), with the addition:

| From | To | Trigger |
|---|---|---|
| `running` | `paused` | Drawdown stop threshold exceeded |

### Invalid Transitions

Identical to `ForwardTestSession` invalid transitions.

### Transition Audit

All state transitions must produce audit events following the same requirements as forward testing, with the addition of `account_id` and open position count in the event payload.

---

## 6. Paper Account Model

The `PaperAccount` is the simulated financial account associated with a paper trading session.

### Conceptual Fields

**`account_id`**
A unique, stable identifier. Assigned at session creation. UUID format required.

**`owner_user_id`**
The user who owns this account. Derived from the owning session's `user_id`. Never accepted from client-supplied payload. Never transferred.

**`session_id`**
The `PaperTradingSession` this account is associated with. A paper account is associated with exactly one session.

**`currency`**
The declared currency denomination of the account (e.g., `USD`, `EUR`). Declared at session creation. Immutable.

**`starting_cash`**
The initial cash balance at account creation. Equal to the session's `starting_equity` value. Immutable after account creation.

**`cash_balance`**
The current available cash: `starting_cash` minus capital committed to open positions minus fees paid, plus realized gains and minus realized losses from closed trades.

**`equity`**
The current total account value: `cash_balance` plus the current marked value of all open positions at the most recently processed bar's close.

**`peak_equity`**
The highest equity value achieved at any point during the session. Used for drawdown computation.

**`current_drawdown_pct`**
The percentage decline from `peak_equity` to current `equity`. Computed after each bar is processed and after each fill.

**`total_realized_pnl`**
The aggregate realized P&L from all closed trades in this session.

**`total_fees_paid`**
The aggregate fees applied across all fills in this session.

**`total_slippage_applied`**
The aggregate slippage applied across all fills in this session.

**`status`**
`active` or `closed`. An account is `closed` when its owning session reaches `completed`, `failed`, or `terminated`.

**`created_timestamp`**
UTC timestamp of account creation.

**`updated_timestamp`**
UTC timestamp of the most recent account state change.

### Account Rules

**Single ownership**: Every paper account is owned by exactly one user. There are no shared accounts.

**Session coupling**: A paper account is created when its session is created and is closed when its session ends. Paper accounts do not persist between sessions. Each new paper trading session creates a new paper account.

**Isolation**: One paper account's cash, positions, and history must not influence any other paper account.

**Auditable**: Every account state change (cash balance change, equity update, drawdown update) must be traceable to a specific fill or bar evaluation event.

**No real money**: Paper accounts hold no real value. They are arithmetic constructs. There is no mechanism to fund, withdraw from, or link a paper account to any real financial account.

---

## 7. Position Model

A `PaperPosition` represents an open simulated position within a paper trading session.

### Conceptual Fields

**`position_id`**
A unique, stable identifier for this position. UUID format.

**`session_id`**
The session this position belongs to.

**`account_id`**
The paper account that holds this position.

**`symbol`**
The instrument symbol (e.g., `AAPL`, `BTC-USD`).

**`side`**
`long` or `short`.

**`quantity`**
The number of units held. Always positive; side determines direction.

**`average_entry_price`**
The average fill price across all fills that contributed to this position's current size. Adjusted when additional size is added to an existing position (position scaling).

**`current_market_value`**
The current marked value of the position: `quantity × current_close_price`. Updated after each bar is processed.

**`unrealized_pnl`**
The current unrealized profit or loss: `current_market_value − (quantity × average_entry_price)` for long; adjusted for short. Updated after each bar is processed.

**`realized_pnl`**
The cumulative realized profit or loss from partial or full closes of this position. Zero until a portion of the position is closed.

**`open_timestamp`**
The bar timestamp at which the position was first opened (the fill's `bar_timestamp`).

**`close_timestamp`**
The bar timestamp at which the position was fully closed. Null for open positions.

**`status`**
`open` or `closed`.

**`opening_signal_id`**
Reference to the `ForwardTestSignal` record that triggered the `ExecutionIntent` that opened this position. Links position history back to signal history and strategy provenance.

**`closing_signal_id`**
Reference to the signal that triggered the exit. Null for positions closed by `session_end_close` or `drawdown_stop`.

### State Ownership Rules

The execution environment (the paper trading session and its `PaperBrokerAdapter`) owns all position state.

Strategy logic must never:
* Read `PaperPosition` objects to make signal decisions
* Write to `PaperPosition` objects
* Know whether a position is open or closed

The strategy's exit rules must be formulated in terms of market data features (indicator values, price conditions). When those conditions are met at a bar, an `ExecutionIntent` with a close direction is produced. The `PaperBrokerAdapter` then determines whether a position exists to close and produces the corresponding fill.

The strategy is not aware of whether its exit intent is acted upon. The execution environment decides.

---

## 8. Order Model

A `PaperOrder` is the record of an instruction from the `PaperBrokerAdapter` to the fill simulation layer.

`PaperOrder` is an internal execution layer object. It is not produced by strategy logic; it is produced by the `PaperBrokerAdapter` when it translates an `ExecutionIntent` into a simulated order.

### Conceptual Fields

**`order_id`**
A unique, stable identifier. UUID format.

**`session_id`**
The session this order belongs to.

**`account_id`**
The account this order belongs to.

**`created_timestamp`**
Wall clock UTC timestamp when the order was created.

**`bar_timestamp`**
The bar timestamp from the `ExecutionIntent` that originated this order.

**`symbol`**
The instrument symbol.

**`side`**
`buy` or `sell`.

**`quantity`**
The number of units this order requests.

**`order_type`**
`market` (current implementation) or `limit` (future).

**`limit_price`**
Null for market orders. The declared limit price for limit orders.

**`status`**
`pending`, `filled`, `partially_filled`, `rejected`, or `cancelled`.

**`source_intent_id`**
The `ExecutionIntent` identifier that caused this order to be created.

**`source_signal_id`**
The `ForwardTestSignal` identifier that originated the chain. Links the order back through intent to signal to strategy rule.

**`rejection_reason`**
If `status = rejected`: a structured reason code (e.g., `insufficient_cash`, `max_positions_exceeded`, `no_position_to_close`). Not a raw exception message.

**`fills`**
A list of `PaperFill` identifiers that fill this order. For current market order implementation, this is always zero or one fill.

### Supported Order Types

**Market order (current scope)**
A market order is filled immediately at the next available price per the declared `fill_timing_model`:
* `signal_bar_close`: filled at the close of the bar on which the signal fired
* `next_bar_open`: filled at the open of the bar following the signal bar

Market orders must not fail to fill except for explicit rejection reasons (insufficient cash, no position to close, max positions exceeded).

**Limit order (future scope)**
A limit order is filled only when the bar's price range includes the limit price. A buy limit at $100 fills when `bar_low ≤ 100`. A sell limit at $100 fills when `bar_high ≥ 100`.

Limit orders that are not filled during a bar remain `pending` and are re-evaluated on subsequent bars. Limit orders should carry a declared expiry (e.g., `good_for_bars: 5`) to prevent indefinite pending orders from accumulating.

Limit order implementation is deferred. The architecture accommodates it; the current implementation scope is market orders only.

### Order Design Constraint

Do not over-design the order model. The paper trading subsystem simulates generic execution mechanics, not exchange microstructure. Stop orders, trailing stops, bracket orders, and order routing instructions are out of scope for this architecture. Future sessions that require more complex order types should be addressed in a dedicated extension.

---

## 9. Fill Model

A `PaperFill` is the record that an order was executed at a specific price and quantity.

A fill is the atomic unit of execution. When an order is filled, a fill record is created, the owning position is updated, and the paper account's cash balance and equity are updated.

### Conceptual Fields

**`fill_id`**
A unique, stable identifier. UUID format.

**`order_id`**
The `PaperOrder` that this fill completes (partially or fully).

**`session_id`**
The session this fill belongs to.

**`account_id`**
The account this fill belongs to.

**`fill_timestamp`**
Wall clock UTC timestamp when the fill was recorded.

**`bar_timestamp`**
The bar timestamp used to determine the fill price (the bar whose close or next-bar open was used).

**`symbol`**
The instrument symbol.

**`side`**
`buy` or `sell`.

**`fill_quantity`**
The number of units filled.

**`gross_fill_price`**
The price before slippage is applied. For `signal_bar_close` fill timing: the close price of the signal bar. For `next_bar_open` fill timing: the open price of the bar following the signal bar.

**`slippage_applied`**
The slippage amount applied to this fill, in price units. Derived from the session's declared `slippage_mode` and `slippage_value`. Zero if `slippage_mode = none`.

**`net_fill_price`**
`gross_fill_price` adjusted by slippage. For a buy: `gross_fill_price + slippage_applied`. For a sell: `gross_fill_price - slippage_applied`.

**`fee_applied`**
The fee charged for this fill, in currency units. Derived from the session's declared `fee_mode` and `fee_value`.

**`execution_reason`**
`signal_exit`, `signal_entry`, `session_end_close`, `drawdown_stop_close`. Explains why this fill was generated.

**`source_signal_id`**
The originating `ForwardTestSignal`. Links fill → order → intent → signal → strategy rule.

### Fill to Order Relationship

Each `PaperOrder` produces zero or one `PaperFill` in the current market order implementation.

A fill of zero units means the order was rejected before the fill simulation ran (e.g., insufficient cash check failed). This is recorded as order rejection, not a fill.

The relationship is strictly:

```
ForwardTestSignal
    ↓ (fires rule)
ExecutionIntent
    ↓ (PaperBrokerAdapter translates)
PaperOrder
    ↓ (fill simulation)
PaperFill
    ↓ (position update)
PaperPosition updated
    ↓ (account update)
PaperAccount cash/equity updated
```

Each step in this chain must produce an immutable record. No step may be skipped silently.

---

## 10. Execution Intent Flow

Paper trading uses the same execution intent model defined in `EXECUTION_CONTRACT.md` §2 and §4.

### Full Flow

```
Strategy Logic
    (evaluates bar; rules fire)
    ↓
ExecutionIntent
    (declares direction, size basis; no fill knowledge)
    ↓
Execution Gateway
    (routes intent to PaperBrokerAdapter based on session mode)
    ↓
PaperBrokerAdapter
    (validates intent against account state and session constraints;
     rejects or translates to PaperOrder)
    ↓
PaperOrder
    (market order created; pending)
    ↓
Fill Simulation
    (determines fill price from declared fill timing model;
     applies slippage and fee)
    ↓
PaperFill
    (immutable fill record created)
    ↓
Position Update
    (PaperPosition opened, scaled, or closed)
    ↓
Account Update
    (cash_balance, equity, peak_equity, drawdown updated)
    ↓
Signal Record Updated
    (ForwardTestSignal linked to resulting PaperOrder and PaperFill)
```

### Strategy Portability Invariant

The strategy definition evaluated in paper trading is the same sealed snapshot evaluated in forward testing. The strategy is unaware of which execution mode is active.

A strategy that requires knowledge of whether it is in forward test mode or paper trading mode to function correctly is a portability violation.

The strategy produces `ExecutionIntent` objects. The execution environment determines what happens to those intents.

### Intent Validation at the Gateway

Before the `PaperBrokerAdapter` translates an intent into an order, the gateway validates:

* **Sufficient cash**: Does the account have enough `cash_balance` to fill this intent at the expected position size?
* **Max positions check**: Would accepting this intent cause the open position count to exceed `max_concurrent_positions`?
* **Valid close target**: For exit intents — does an open position exist in the expected direction and symbol?

If any check fails:
* The intent is rejected
* A `PaperOrder` with `status = rejected` and structured `rejection_reason` is recorded
* A `PAPER_INTENT_REJECTED` audit event is emitted
* The session continues — intent rejection is not a session failure

---

## 11. PaperBrokerAdapter

The `PaperBrokerAdapter` is the execution environment for paper trading. It is the specific implementation of the Execution Gateway adapter for simulated execution.

### Conceptual Responsibilities

1. **Receive `ExecutionIntent`** from the strategy evaluation layer (delivered by the gateway)
2. **Validate** the intent against account state and session constraints
3. **Translate** the validated intent into a `PaperOrder`
4. **Simulate the fill** according to the declared `simulation_assumptions`
5. **Record** the `PaperFill`
6. **Update** `PaperPosition` state
7. **Update** `PaperAccount` state (cash, equity, drawdown)
8. **Emit** audit events for every action taken

### What PaperBrokerAdapter Does NOT Do

* It does not communicate with any broker, exchange, or external system
* It does not make analytical decisions about whether a signal should be acted upon
* It does not modify the `ExecutionIntent` it receives
* It does not apply risk rules that are not declared in the session's `simulation_assumptions`
* It does not introduce execution behavior not declared in `simulation_assumptions`

### Future Adapter Relationship

`PaperBrokerAdapter` implements the same gateway adapter interface that future broker adapters (`IBKRAdapter`, `BinanceAdapter`) will implement.

The gateway interface contract is:
1. Accept an `ExecutionIntent`
2. Produce an execution result (fill records, rejection records)
3. Return the result to the gateway

The adapter implementation differs:
* `PaperBrokerAdapter`: fills locally using declared price models
* `IBKRAdapter`: translates to IBKR order types and routes to the IBKR API
* `BinanceAdapter`: translates to Binance order types and routes to the Binance API

Strategy logic is unaware of which adapter is active. Switching from paper trading to live trading means substituting the adapter, not modifying the strategy.

---

## 12. Fill Simulation Philosophy

Paper trading fill simulation must be simple, transparent, and auditable.

The goal is not to model exchange microstructure. The goal is to produce fill records that:
* reflect the declared execution assumptions exactly
* can be explained in full to a reviewer without reference to complex models
* are deterministic given the declared assumptions and the bar data
* are consistent with how the backtesting engine computes fills (same declared parameters produce comparable results)

### What Fill Simulation Must Be

**Simple**: A market order fills at one of two prices — the close of the signal bar or the open of the following bar. That is the complete fill timing model for the current scope. No order book. No volume participation. No market impact.

**Transparent**: The `PaperFill` record contains every input used to produce it: `gross_fill_price`, `slippage_applied`, `net_fill_price`, `fee_applied`, `fill_timing_model`. A reviewer can recompute the fill from the `PaperFill` record alone.

**Auditable**: Every fill is linked back through `PaperOrder → ExecutionIntent → ForwardTestSignal → strategy rule`. The complete provenance chain exists.

**Declared**: No fill simulation parameter may be applied unless it was declared in `simulation_assumptions` at session creation. If a fill parameter was not declared, it is zero or none. There are no hidden defaults.

### Fill Timing Models

**`signal_bar_close`**
The fill price is the close price of the bar on which the signal fired.

This model assumes instantaneous execution at bar close — an optimistic assumption that is appropriate when analyzing signal quality but should be noted as potentially unrealistic for intraday timeframes where the close is not accessible until after the bar closes.

**`next_bar_open`**
The fill price is the open price of the bar following the signal bar.

This model assumes the trader observes the signal at bar close, places the order, and receives a fill at the next bar's open. It is generally more conservative than `signal_bar_close` and is the recommended default.

Both models must be available. The user declares one at session creation and it is immutable for the session.

### Slippage

Slippage is applied to the gross fill price after the timing model determines the base price.

**`none`**: No slippage. `net_fill_price = gross_fill_price`.

**`fixed`**: A fixed number of price units added (for buys) or subtracted (for sells). `slippage_value` is in the same units as the instrument's price.

**`percentage`**: A percentage of the gross fill price. `slippage_value` is a decimal fraction (e.g., `0.001` for 0.1%).

No dynamic slippage modeling (volume-dependent, volatility-dependent, market impact). Paper trading uses declared static slippage. The complexity of dynamic slippage modeling belongs to live trading post-mortems, not paper trading simulation.

### Fees

**`none`**: No fees.

**`flat`**: A fixed currency amount per trade. `fee_value` is in the account's declared currency.

**`percentage`**: A percentage of the total fill value (price × quantity). `fee_value` is a decimal fraction.

Fee is applied after slippage. The fill record stores both `gross_fill_price` and `net_fill_price` (post-slippage), and `fee_applied` separately. This allows total cost analysis without conflating slippage and fees.

### Position Sizing

Position sizing translates the `ExecutionIntent`'s declared size basis into a concrete quantity, resolved by the `PaperBrokerAdapter`:

**`equity_fraction`**: The position size is a fraction of current `equity`. `quantity = floor((equity × equity_fraction) / fill_price)`. Uses current equity at the time of intent processing.

**`fixed_quantity`**: The position size is a fixed number of units. `quantity = fixed_quantity_value`.

**`fixed_cash`**: The position size is a fixed cash amount. `quantity = floor(fixed_cash_value / fill_price)`.

Position sizing must produce an integer quantity (whole units). Fractional units are not supported in the current scope.

If the computed quantity resolves to zero (e.g., equity is too small for even one unit at current price), the order is rejected with `rejection_reason = quantity_resolved_to_zero`.

### What Fill Simulation Must NOT Be

* A market microstructure model (no order book, no level 2, no volume participation)
* A broker-specific execution simulator (no IBKR-specific margin rules, no Binance lot sizes)
* A dynamic slippage model (no volume-based, volatility-based, or impact-based slippage)
* A partial fill simulator (market orders either fill fully or are rejected; no partial fills in current scope)
* A source of hidden or undeclared costs

---

## 13. Account State Management

Account state — cash, equity, positions, orders, fills, and execution history — is owned exclusively by the paper trading session and its `PaperBrokerAdapter`.

### What the Execution Environment Owns

**`PaperAccount`**: The current cash balance, equity, peak equity, drawdown, realized P&L, fees paid, slippage applied.

**`PaperPosition` collection**: All open positions and the history of closed positions for this session.

**`PaperOrder` collection**: All orders placed during this session, including rejected orders.

**`PaperFill` collection**: All fills generated during this session.

**Account state snapshots**: A running record of account state after each bar is processed, sufficient to reconstruct the full equity curve.

### What Strategy Logic Must Never Own

Strategy logic must never:
* Read `PaperAccount` to decide whether to generate an entry signal (no "check if I have cash" logic in strategy rules)
* Read `PaperPosition` to decide whether to generate an exit signal based on position state (exit signals must be based on market data features, not position awareness)
* Accumulate its own running P&L
* Apply fees or slippage to its signal logic

If a strategy's entry logic needs to consider capital allocation, that concern must be expressed as a declared position sizing model in `simulation_assumptions`, not as conditional logic in the strategy's rules.

### Account Update Sequence

After each `PaperFill` is recorded:

1. Update `PaperPosition` (open, scale, or close)
2. Update `PaperAccount.cash_balance` (deduct for buys; add for sells, net of fees)
3. Update `PaperAccount.equity` (recalculate from cash + current position values)
4. Update `PaperAccount.total_realized_pnl` (for closes)
5. Update `PaperAccount.total_fees_paid`
6. Update `PaperAccount.total_slippage_applied`
7. Check `max_drawdown_stop_pct` (if configured): if breached, pause session

After each bar is processed (even bars with no fills):
1. Mark all open positions with current close price
2. Recalculate `unrealized_pnl` for each open position
3. Recalculate `PaperAccount.equity`
4. Update `PaperAccount.peak_equity` if current equity exceeds previous peak
5. Update `PaperAccount.current_drawdown_pct`
6. Record `AccountState` snapshot for equity curve

### Equity Curve Construction

The equity curve is constructed from the sequence of `AccountState` snapshots recorded after each bar.

One snapshot per bar is the minimum required cadence for an interpretable equity curve.

The equity curve is a primary result artifact for the paper trading session, analogous to the equity curve in backtesting results.

---

## 14. Provenance Requirements

Every paper trading artifact — signal records, orders, fills, positions, and the session itself — must carry provenance sufficient to answer at any future point:

* Which strategy produced this signal/order/fill?
* What exact version of the strategy?
* What was the lifecycle status at session activation?
* What data source supplied the bar?
* What simulation assumptions governed this fill?
* What were the feature values that caused the signal to fire?
* When did each step in the chain occur?
* Who owns this session?

### Strategy Provenance

Every `PaperFill` links through `source_signal_id → ForwardTestSignal → strategy_snapshot_hash → sealed strategy_snapshot`.

The provenance chain from fill back to strategy rule is complete and immutable.

### Data Source Provenance

Fill records carry `bar_timestamp`, `symbol`, and implicitly inherit `provider_name` and `timeframe` from the session record.

`catalog_id` is used for catalog-sourced sessions. `file_path` never appears.

### Session Provenance

Every artifact carries `session_id`, linking it to the complete session record: owner, strategy snapshot, simulation assumptions, activation timestamp, lifecycle status at activation.

### Simulation Assumption Provenance

Every fill record stores `gross_fill_price`, `net_fill_price`, `slippage_applied`, and `fee_applied`. This makes the fill fully self-documenting — a reviewer can verify the fill was computed correctly from the declared assumptions without external reference.

### Signal Provenance

The `ExecutionIntent → PaperOrder → PaperFill` chain is linked at every step through `source_signal_id` and `source_intent_id`. The feature values at signal time (captured in the `ForwardTestSignal` record) are available for review alongside every fill.

### Immutability

All paper trading artifacts are immutable after creation. No fill, order, position record, or signal record may be modified after it is written. Account state updates follow the defined update sequence — they do not overwrite prior state, they update fields on the mutable account record (which is a running state object, not a historical record).

---

## 15. Audit Requirements

All paper trading session events must produce structured audit records through the platform's existing `emit_audit_event()` infrastructure.

### Mandatory Audit Events

**Session Lifecycle**

| Event | Trigger |
|---|---|
| `PAPER_SESSION_CREATED` | Session record created |
| `PAPER_SESSION_ACTIVATED` | Session transitions to `running` |
| `PAPER_SESSION_PAUSED` | Session transitions to `paused` (user-requested) |
| `PAPER_SESSION_PAUSED_DRAWDOWN_STOP` | Drawdown stop threshold triggered |
| `PAPER_SESSION_PAUSED_PROVIDER_FAILURE` | Persistent provider failure |
| `PAPER_SESSION_RESUMED` | Session transitions from `paused` to `running` |
| `PAPER_SESSION_COMPLETED` | Session transitions to `completed` |
| `PAPER_SESSION_FAILED` | Session transitions to `failed` |
| `PAPER_SESSION_TERMINATED` | Session terminated by admin or system |
| `PAPER_SESSION_INVALID_TRANSITION_DENIED` | Invalid state transition rejected |

**Strategy Activation**

| Event | Trigger |
|---|---|
| `PAPER_ACTIVATION_DENIED` | Strategy lifecycle check failed (requires `lifecycle_status >= backtested`) |
| `PAPER_ACTIVATION_APPROVED` | Session activated; lifecycle check passed |

**Order Events**

| Event | Trigger |
|---|---|
| `PAPER_ORDER_CREATED` | `PaperBrokerAdapter` translates intent to order |
| `PAPER_ORDER_REJECTED` | Intent validation failed (insufficient cash, max positions, etc.) |
| `PAPER_ORDER_CANCELLED` | Order cancelled before fill (limit order expiry, session close) |

**Fill Events**

| Event | Trigger |
|---|---|
| `PAPER_FILL_GENERATED` | Fill simulation produces a fill |

**Position Events**

| Event | Trigger |
|---|---|
| `PAPER_POSITION_OPENED` | New position opened by a buy fill |
| `PAPER_POSITION_SCALED` | Existing position increased by an additional fill |
| `PAPER_POSITION_CLOSED` | Position fully closed by a sell fill |
| `PAPER_POSITION_FORCE_CLOSED` | Position closed by session_end_close or drawdown_stop_close |

**Account Events**

| Event | Trigger |
|---|---|
| `PAPER_ACCOUNT_UPDATED` | Account state updated after a fill |
| `PAPER_DRAWDOWN_THRESHOLD_WARNING` | Drawdown has exceeded 80% of `max_drawdown_stop_pct` (advisory) |
| `PAPER_DRAWDOWN_STOP_TRIGGERED` | Drawdown has exceeded `max_drawdown_stop_pct` |

**Data Events**

Inherits all data events from the Forward Testing audit model:
`PAPER_POLL_COMPLETED`, `PAPER_PROVIDER_FAILURE`, `PAPER_GAP_DETECTED`, `PAPER_CATCHUP_STARTED`, `PAPER_CATCHUP_THRESHOLD_EXCEEDED`

**Session Access**

| Event | Trigger |
|---|---|
| `PAPER_SESSION_EXPORTED` | User requested export of session results |
| `PAPER_SESSION_REVIEWED` | Session accessed for lifecycle promotion review |

### Audit Payload Requirements

Every audit event must include:
* `session_id`
* `user_id` (session owner)
* `account_id`
* `event_timestamp` (UTC)
* Event-specific fields

Audit events must never include:
* `file_path`
* Decrypted credential values
* Raw provider error messages
* Internal stack traces
* Real account identifiers (paper only)

---

## 16. UI Workflow Concept

This section describes the conceptual user workflow for the paper trading feature. No UI implementation is specified here.

### User Journey

**1. Session Configuration**
The user selects:
* A strategy from their draft registry (must have `lifecycle_status >= backtested`)
* A data source (provider + symbol + timeframe, or catalog entry)
* A starting equity amount
* Simulation assumptions (fill timing, fee model, slippage model, position sizing model)
* Optional risk constraints (max concurrent positions, drawdown stop threshold)

The user reviews a summary of the declared assumptions before confirming.

**2. Session Activation**
The user activates the session. The platform:
* Creates the `PaperTradingSession` and `PaperAccount` records
* Fetches initial warmup bars
* Transitions the session to `running`
* Begins the polling schedule

**3. Monitoring**
While the session is running, the user can observe:
* Open positions with current unrealized P&L
* Order history (filled and rejected orders)
* Fill history
* Current equity and drawdown
* Live equity curve (updated after each bar)
* Signal history (which signals fired and which produced fills)

**4. Pause / Resume**
The user may pause the session. Open positions are preserved. No new orders are generated while paused.

**5. Stop and Review**
The user stops the session. Open positions are force-closed. The session transitions to `completed`. The platform presents:
* Full trade history (all fills with entry/exit prices, fees, slippage, P&L per trade)
* Final equity curve
* Session-level metrics (total return, max drawdown, win rate, trade count, profit factor)
* Signal vs. fill comparison (how many signals were generated; how many produced fills; how many were rejected)

**6. Promotion Review**
Session results are used as evidence when requesting advancement to `paper_tested` lifecycle status. A user or authorized admin reviews the session before approving promotion.

### What the UI Must Never Do

* Display positions or fills before the corresponding records are persisted
* Allow modification of `simulation_assumptions` after session activation
* Automatically advance the strategy lifecycle based on session performance
* Display broker account information (there is no broker account)
* Allow the user to manually insert, edit, or delete fill or position records

---

## 17. Relationship to Forward Testing

### What Is Shared

Paper trading inherits the complete forward testing session architecture:

| Component | Status |
|---|---|
| Session field model (`session_id`, `user_id`, strategy snapshot, source provenance) | Fully shared |
| Session lifecycle state machine (6 states, allowed/invalid transitions) | Shared; paper trading extends with drawdown stop transition |
| Data acquisition model (polling, bar finalization, unseen-bar cursor, gap handling) | Fully shared |
| Evaluation model (same tool registry, semantic evaluator, warmup logic) | Fully shared |
| `ForwardTestSignal` recording | Shared; paper trading produces the same signal records as forward testing |
| Ownership model (JWT-sourced, information-hiding access control) | Fully shared |
| Provenance model (sealed snapshot, `file_path` exclusion) | Fully shared |
| Audit model (session lifecycle events, data events) | Extended — paper trading adds order/fill/position/account events |

### What Is Added

Paper trading adds the execution layer that forward testing explicitly excludes:

| Component | Added by Paper Trading |
|---|---|
| `PaperAccount` | Account with cash, equity, drawdown tracking |
| `PaperPosition` | Open and closed position records |
| `PaperOrder` | Order records (market orders in current scope) |
| `PaperFill` | Fill records with price, slippage, fee |
| `PaperBrokerAdapter` | Fill simulation layer; account/position state updates |
| `simulation_assumptions` | Declared execution parameters (fill timing, fees, slippage, sizing) |
| Equity curve | Running account equity snapshot after each bar |
| Session-level metrics | Return, drawdown, win rate, trade count, profit factor |

### The Progression

```
Forward Testing
    → observes: signals
    → produces: ForwardTestSignal records
    → validates: signal quality, signal stability

Paper Trading
    → observes: signals + execution behavior
    → produces: ForwardTestSignal + PaperOrder + PaperFill + PaperPosition + equity curve
    → validates: execution behavior, capital utilization, drawdown profile
```

Every `PaperTradingSession` produces a complete `ForwardTestSignal` record for every signal fired, in addition to its execution artifacts. Paper trading is a strict superset of forward testing's outputs.

---

## 18. Relationship to Future Live Trading

Paper trading is execution rehearsal for live trading.

The transition from paper trading to live trading must require no changes to strategy logic or strategy definitions. The only change is the execution environment: `PaperBrokerAdapter` is replaced by a real broker adapter (`IBKRAdapter`, `BinanceAdapter`, etc.).

### What Live Trading Inherits from Paper Trading

| Component | Live Trading Relationship |
|---|---|
| `PaperTradingSession` structure | `LiveTradingSession` inherits all session fields; adds broker credential reference |
| Session lifecycle | Same 6-state machine; `completed` state may trigger withdrawal/reporting workflows |
| `PaperAccount` model | `BrokerAccount` replaces `PaperAccount`; same fields but backed by real broker state |
| `PaperOrder` model | `LiveOrder` adds broker order ID, exchange acknowledgment timestamp, routing metadata |
| `PaperFill` model | `LiveFill` adds broker fill ID, exchange fill timestamp, actual execution venue |
| `ExecutionIntent` flow | Identical — the same intent objects are produced by strategy logic |
| Execution Gateway | Same gateway; `PaperBrokerAdapter` replaced by real broker adapter |
| Provenance model | Identical — sealed strategy snapshot, signal chain preserved |
| Audit model | Inherited and extended — live trading adds broker acknowledgment events |

### What Live Trading Adds

* Broker credential resolution through the vault
* Real network communication through the broker adapter
* Broker-acknowledged order and fill records
* Real financial consequences requiring enhanced error handling
* Hard-stop mechanisms
* Explicit lifecycle requirement: `lifecycle_status = approved_for_live`

### The Rehearsal Principle

Paper trading's value as rehearsal for live trading depends on its design fidelity:
* The same strategy produces the same `ExecutionIntent` objects in paper and live mode
* The same gateway translates those intents through the same interface
* The same order, fill, and position records are produced (with live broker IDs in live mode)
* The same audit model records all events

A user who has completed paper trading and observed the session behavior — signal frequency, position cycling, equity curve, drawdown profile, capital utilization — can form a realistic expectation of what live trading will look like, modulo real broker execution quality.

That expectation is the value paper trading provides.

---

## 19. Non-Negotiable Constraints

The following constraints are absolute. No implementation may violate them.

**No real broker calls**: The `PaperBrokerAdapter` operates entirely locally. No network request is made to any broker, exchange, or financial data service during fill simulation.

**No real orders**: No `PaperOrder` or `PaperFill` represents a real financial transaction. There is no clearing, no settlement, no real ownership of any security.

**No real money**: Paper accounts hold no real value. The starting equity is an arithmetic initialization. There is no mechanism to link a paper account to a real financial account.

**No automatic promotion**: Completing a paper trading session does not change the strategy's `lifecycle_status`. Promotion to `paper_tested` requires explicit human review and authorization through the governance workflow.

**No bypass of lifecycle governance**: The `lifecycle_status >= backtested` requirement must be enforced at session activation. A strategy that has not been through a promotion-grade backtest review cannot enter paper trading.

**No hidden execution paths**: Every order, fill, and position change must be recorded. There are no "internal" fills that bypass the audit trail.

**No direct strategy-to-broker communication**: Strategy logic never receives a reference to the `PaperBrokerAdapter` or any adapter. The execution gateway is the only path between strategy intents and the execution environment.

**Simulation assumptions are immutable after activation**: Changing `simulation_assumptions` mid-session would produce an incoherent trade history. Once a session is activated, its assumptions are sealed.

**Fills are deterministic given inputs**: Given the same bar data and the same declared `simulation_assumptions`, the fill simulation must always produce the same fill price, slippage, and fee. No randomness. No hidden dynamic factors.

---

## 20. Future Documents

### EXECUTION_AUDIT_MODEL.md

The audit events defined in §15 must be incorporated into the complete execution audit taxonomy.

`EXECUTION_AUDIT_MODEL.md` will define:
* The formal `AuditEventKind` enum values for all paper trading events listed in §15
* Required payload fields for each event kind
* How paper trading audit events relate to forward testing audit events (shared taxonomy, different prefixes)
* Retention policy for paper trading audit records
* Query interface requirements

Paper trading cannot be fully governed without this document. The audit event taxonomy established here should be treated as the paper trading contribution to `EXECUTION_AUDIT_MODEL.md`.

### STRATEGY_PROMOTION_LIFECYCLE.md

Paper trading is the final evidence stage before `approved_for_live`.

`STRATEGY_PROMOTION_LIFECYCLE.md` must define:
* Minimum evidence requirements for a paper trading session to qualify for promotion review (minimum session duration, minimum trade count, minimum bars evaluated, required `status = completed`)
* The evidence relationship between backtesting results and paper trading results (do they need to be consistent? what discrepancies are acceptable?)
* The promotion gate between `backtested + paper-tested evidence → approved_for_live` lifecycle status
* The human approval workflow: who may authorize live promotion, what records they must review, what they must explicitly acknowledge
* Whether a single paper trading session constitutes sufficient evidence or whether multiple sessions are recommended

This document cannot be completed without understanding both the forward testing and paper trading evidence models. Both predecessor documents now exist.

---

## Summary of Paper Trading Responsibilities

```
SESSION ACTIVATION
    → Verify: strategy lifecycle_status >= backtested
    → Snapshot: strategy definition (sealed; immutable)
    → Declare: simulation_assumptions (immutable after activation)
    → Create: PaperAccount (starting_equity, currency)
    → Configure: source (provider/catalog), symbol, timeframe
    → Record: activation provenance
    → Fetch: initial warmup bars
    → Process: warmup bars (no signal evaluation; no fills)
    → Transition: session to 'running'
    → Audit: PAPER_SESSION_ACTIVATED

POLL CYCLE (per timeframe period)
    → Poll: provider for completed bars
    → Filter: duplicate bars; detect gaps
    → For each new completed bar (ascending timestamp):
        → Compute: features (existing tool registry)
        → Evaluate: strategy rules (existing semantic evaluator)
        → If rule fires AND warmup satisfied:
            → Record: ForwardTestSignal
            → Produce: ExecutionIntent
            → Gateway routes intent to PaperBrokerAdapter
            → PaperBrokerAdapter validates (cash, max_positions, close target)
            → If rejected: record PaperOrder(rejected); audit PAPER_ORDER_REJECTED
            → If valid: create PaperOrder(pending)
            → Fill simulation: determine fill price; apply slippage and fee
            → Create PaperFill (immutable)
            → Update PaperPosition (open / scale / close)
            → Update PaperAccount (cash, equity, pnl, fees, slippage)
            → Audit: ORDER_CREATED, FILL_GENERATED, POSITION_OPENED/CLOSED
        → Mark open positions with current close
        → Recalculate equity and drawdown
        → Snapshot AccountState (equity curve point)
        → Check drawdown stop; pause if breached
        → Update last_processed_bar_timestamp
    → Audit: PAPER_POLL_COMPLETED

SESSION CLOSE
    → Force-close all open positions at last bar close
    → Compute: session-level metrics (return, drawdown, win rate, trade count, profit factor)
    → Produce: session summary artifact and equity curve
    → Transition: session to 'completed'
    → Audit: PAPER_SESSION_COMPLETED
    → Retain: all records immutably

ENFORCEMENT (invariants that must never be violated)
    → No real broker calls; no real orders; no real money
    → No automatic promotion
    → Strategy portability invariant preserved
    → Simulation assumptions declared and immutable
    → Every fill is deterministic and fully documented
    → Ownership: JWT-derived, never client-supplied
    → file_path never in any record
    → No hidden execution paths
```

Paper trading transforms signal observation into execution evidence.

That evidence is only as trustworthy as the declared assumptions under which it was produced and the discipline with which fills were recorded.

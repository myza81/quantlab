# STRATEGY_PROMOTION_LIFECYCLE.md

## Purpose

This document defines the authoritative strategy promotion lifecycle for QuantLab.

It establishes how strategies progress from initial composition to live execution authorization, the evidence required at each promotion gate, the review and approval workflow that governs advancement, and the conditions under which approvals may be revoked.

This document is the governance layer above:

* Backtesting (`docs/BACKTESTING_ENGINE_CONTRACT.md`)
* Forward Testing (`docs/FORWARD_TESTING_ARCHITECTURE.md`)
* Paper Trading (`docs/PAPER_TRADING_ARCHITECTURE.md`)
* Execution Audit (`docs/EXECUTION_AUDIT_MODEL.md`)

It draws on the audit event taxonomy, the session models, and the evidence record structures defined in those documents. It consumes them as evidence producers; it defines what that evidence must demonstrate before promotion is granted.

This document is architecture-level.

No implementation. No UI design. No database schema. No reviewer workflow software. No performance thresholds. No numerical approval rules. Architecture only.

---

## Why This Document Exists

The QuantLab platform supports multiple execution modes: backtesting, forward testing, paper trading, and live trading. Each mode introduces progressively higher stakes — forward testing has no financial consequence; paper trading has simulated financial consequence; live trading has real financial consequence.

Without a formal promotion lifecycle, the platform risks:

* allowing strategies to enter live trading without adequate evidence of behavior under live conditions
* permitting promotion based solely on backtest performance, which cannot reveal live market behavior, provider data quality issues, or execution mechanics failures
* enabling self-approvals, where users promote their own strategies without independent review
* creating audit gaps where promotion decisions are made but not recorded
* treating promotion as a technical event (a status flag update) rather than a governance decision (an explicit human authorization with evidence)

The strategy promotion lifecycle exists to enforce the principle that access to each execution mode is earned through evidence and governed through review — not granted automatically or bypassed by any technical path.

---

## 1. Purpose of Promotion Governance

### Why Promotion Governance Exists

A strategy definition is authored in a research environment. It operates on historical data that is clean, ordered, and complete. The author can test hypotheses, adjust parameters, and iterate until the strategy produces favorable historical results.

That historical evidence is valuable, but it is insufficient to authorize live execution.

Promotion governance exists to ensure that a strategy has been observed across progressively higher-stakes conditions before real capital is committed. Each promotion gate requires evidence from a specific mode of observation. Each mode answers questions that previous modes cannot.

### Why Good Backtests Are Insufficient

A backtest answers: "How would this strategy have performed on this specific historical dataset under these simulation assumptions?"

It cannot answer:
* How does this strategy behave when confronted with a market regime it has not encountered in historical data?
* How does this strategy generate signals in real market conditions, with real provider data quality and latency?
* How does position sizing interact with live equity fluctuations?
* Does this strategy's exit logic fire correctly when positions are actually open?
* Are signal patterns consistent with what historical data predicted, or does live behavior diverge?

Each of these questions requires different evidence. Backtesting alone cannot provide it.

### Why Execution Evidence Matters

Execution evidence — from forward testing and paper trading — is the only way to observe a strategy's behavior in live market conditions before real capital is committed.

Forward testing reveals signal behavior under current market regimes. Paper trading reveals execution behavior: how fills interact with declared assumptions, how equity evolves, whether risk rules fire correctly.

Both forms of evidence are non-reproducible. As established in `docs/EXECUTION_AUDIT_MODEL.md`, audit records from these sessions substitute for reproducibility. They are the evidence.

Promotion governance is the mechanism that ensures this evidence exists, is complete, is reviewed, and is explicitly acknowledged before live trading is authorized.

---

## 2. Lifecycle Philosophy

Six principles govern the QuantLab strategy promotion lifecycle.

### Promotion Is Earned

Advancement to each lifecycle state must be earned through evidence. No state is granted automatically. No state can be reached by skipping a preceding evidence-gathering stage.

### Promotion Is Evidence-Driven

Every promotion gate specifies the evidence types that must exist before a promotion can be reviewed. Evidence is defined in terms of artifact types and audit record completeness — not in terms of performance metrics. QuantLab does not define minimum return thresholds, minimum win rates, or maximum drawdown requirements as gates. Performance evaluation is the reviewer's responsibility.

### Promotion Is Review-Driven

Evidence alone is not sufficient. Evidence must be reviewed by an authorized party.

No strategy advances to the next lifecycle state without a human review step. The reviewer does not merely verify that evidence exists. The reviewer evaluates whether the evidence is adequate — whether the strategy demonstrated sufficient behavior quality to justify the next stage.

### Promotion Is Reversible

Lifecycle advancement can be revoked. A strategy that reaches `APPROVED_FOR_LIVE` and subsequently exhibits unexpected behavior may be revoked. The revocation model is defined in §14.

### Promotion Is Never Automatic

No subsystem may automatically advance a strategy's lifecycle status.

Completing a backtest run does not advance the lifecycle status. Completing a forward test session does not advance the lifecycle status. Completing a paper trading session does not advance the lifecycle status.

Advancement is always triggered by:

1. A user submitting a promotion request
2. An authorized reviewer examining the evidence
3. The reviewer explicitly approving the advancement

Any code path that advances lifecycle status without a reviewer approval record is an architectural violation.

### Promotion Is Documented

Every promotion decision — approval, rejection, or revocation — must produce an audit record per the taxonomy defined in `docs/EXECUTION_AUDIT_MODEL.md`. A promotion decision without an audit record did not happen in the governance record.

---

## 3. Lifecycle States

The authoritative lifecycle for QuantLab strategies:

```
DRAFT
    ↓ backend validation passes
VALIDATED
    ↓ promotion-grade backtest reviewed
BACKTESTED
    ↓ forward test session reviewed
FORWARD_TESTED
    ↓ paper trading session reviewed
PAPER_TESTED
    ↓ explicit human authorization
APPROVED_FOR_LIVE
    ↓ live session activated
LIVE
    ↓ all live sessions end normally
APPROVED_FOR_LIVE  (returns; retains eligibility)

From any active state:
    → ARCHIVED  (terminal)

From LIVE, APPROVED_FOR_LIVE, or PAPER_TESTED:
    → REVOKED  (governance-triggered; re-review required before re-advancement)
```

### State Summary

| State | Purpose |
|---|---|
| `DRAFT` | Active composition. No validation, no execution. |
| `VALIDATED` | Definition passes structural and semantic validation. Eligible for backtesting. |
| `BACKTESTED` | Promotion-grade backtest reviewed and approved. Eligible for forward testing. |
| `FORWARD_TESTED` | Forward test session reviewed and approved. Eligible for paper trading. |
| `PAPER_TESTED` | Paper trading session reviewed and approved. Eligible for live authorization review. |
| `APPROVED_FOR_LIVE` | Explicit human authorization granted for live trading. |
| `LIVE` | One or more active live trading sessions exist. Returns to `APPROVED_FOR_LIVE` when all sessions end normally. |
| `REVOKED` | Previously granted authorization explicitly withdrawn. Re-advancement requires new evidence and review. |
| `ARCHIVED` | Terminal. No execution permitted. Preserved for historical reference. |

---

## 4. Lifecycle State Definitions

### DRAFT

**Purpose**: Initial state. Strategy is under active composition. Its tool configuration, rule definitions, and parameter set may be incomplete or semantically invalid.

**Entry requirements**: Created in the Composer. No prior state required.

**Expected artifacts**: `StrategyDraft` record with `lifecycle_status = draft`.

**Allowed actions**: Edit strategy definition; submit for backend validation; archive.

**Disallowed actions**: Forward testing, paper trading, live trading; requesting promotion (advancement to VALIDATED is triggered by passing validation, not a promotion request).

---

### VALIDATED

**Purpose**: Strategy definition has passed backend semantic and structural validation. All tool references resolve. The dependency graph is valid. All parameter values are within declared bounds. This is a technical gate — it establishes that the strategy is correctly formed, not that it is a good strategy.

**Entry requirements**: Successful completion of backend validation; all tool references resolve in the current registry snapshot; no circular dependencies; all required parameters within declared bounds.

**Expected artifacts**: `StrategyDraft` record with `lifecycle_status = validated`; current backend validation record.

**Allowed actions**: Run backtests; run forward test sessions (exploratory only — see note); request promotion to BACKTESTED; re-edit (demotes to DRAFT); archive.

**Disallowed actions**: Paper trading; live trading; promotion to BACKTESTED without reviewed backtest evidence.

**Note on forward testing at VALIDATED**: The platform's technical minimum for forward testing activation is `lifecycle_status >= validated`. However, forward test sessions conducted before reaching BACKTESTED do not constitute promotion-eligible evidence for the FORWARD_TESTED gate. A researcher who runs forward tests on a VALIDATED strategy is conducting exploratory observation, not governance evidence gathering.

---

### BACKTESTED

**Purpose**: Strategy has been subjected to a promotion-grade backtest, reviewed and approved by an authorized party. BACKTESTED is the first governance-gated state — reaching it requires human review.

**Entry requirements**: Strategy at VALIDATED; at least one completed (not failed, not terminated) promotion-grade backtest run; the run reviewed by an authorized party; `GOV_PROMOTION_APPROVED` audit event with `new_lifecycle_status = backtested` must exist. See §7 for detailed evidence requirements.

**Expected artifacts**: All VALIDATED artifacts; completed backtest run records with full audit provenance; `GOV_PROMOTION_REQUESTED`, `GOV_PROMOTION_REVIEW_STARTED`, `GOV_PROMOTION_APPROVED` audit events.

**Allowed actions**: Run additional backtests; run forward test sessions (promotion-eligible evidence gathering begins here); request promotion to FORWARD_TESTED; run paper trading sessions (exploratory only — see note); archive.

**Disallowed actions**: Live trading; promotion to FORWARD_TESTED without a reviewed forward test session.

**Note on paper trading at BACKTESTED**: The current platform allows paper trading at `lifecycle_status >= backtested`. The full governance path requires forward test evidence before paper trading constitutes promotion-eligible evidence. Sessions conducted at this stage before reaching FORWARD_TESTED are exploratory — they do not satisfy the PAPER_TESTED promotion gate.

---

### FORWARD_TESTED

**Future state — not yet in current implementation.**

**Purpose**: Strategy has been evaluated against live market data in a completed forward test session. Its signal behavior under current market conditions has been observed and reviewed.

**Entry requirements**: Strategy at BACKTESTED; at least one completed `ForwardTestSession` (status = `completed`); session has a reviewable signal history; reviewed by an authorized party; `GOV_PROMOTION_APPROVED` audit event with `new_lifecycle_status = forward_tested` must exist. See §8 for detailed evidence requirements.

**Expected artifacts**: All BACKTESTED artifacts; completed `ForwardTestSession` records with intact `ForwardTestSignal` history; complete `FT_` audit trail; `GOV_` promotion audit events.

**Allowed actions**: Run additional forward test sessions; begin promotion-eligible paper trading sessions; request promotion to PAPER_TESTED; archive.

**Disallowed actions**: Live trading; promotion to PAPER_TESTED without a reviewed paper trading session.

---

### PAPER_TESTED

**Purpose**: Strategy has been evaluated in a completed paper trading session. Its execution behavior — fills, positions, capital utilization, equity curve, drawdown — has been observed under live conditions using a simulated account. PAPER_TESTED is the final evidence-gathering state; a strategy here holds all three evidence types required for live authorization review.

**Entry requirements**: Strategy at FORWARD_TESTED (per full governance path); at least one completed `PaperTradingSession` (status = `completed`); session generated fills and an equity curve; reviewed by an authorized party; `GOV_PROMOTION_APPROVED` audit event with `new_lifecycle_status = paper_tested` must exist. See §9 for detailed evidence requirements.

**Expected artifacts**: All FORWARD_TESTED artifacts; completed `PaperTradingSession` records with fills, positions, account history, equity curve; complete `PT_` audit trail; `GOV_` promotion audit events.

**Allowed actions**: Run additional paper trading sessions; run additional forward test sessions; request promotion to APPROVED_FOR_LIVE; archive.

**Disallowed actions**: Live trading without APPROVED_FOR_LIVE.

---

### APPROVED_FOR_LIVE

**Purpose**: Strategy has received explicit human authorization for live trading. An authorized reviewer has examined the complete three-part evidence base and explicitly acknowledged responsibility for the authorization. A strategy here is eligible to have live trading sessions activated.

**Entry requirements**: Strategy at PAPER_TESTED; three-part evidence base exists; reviewer holds admin or superadmin role; reviewer has provided `explicit_acknowledgment_text`; `GOV_STRATEGY_APPROVED_FOR_LIVE` audit event exists. See §12 for detailed approval requirements.

**Expected artifacts**: All PAPER_TESTED artifacts; `GOV_STRATEGY_APPROVED_FOR_LIVE` event with `explicit_acknowledgment_text`; full `GOV_` promotion trail for this gate.

**Allowed actions**: Activate live trading sessions; continue running paper trading sessions; archive.

**Disallowed actions**: No additional governance gate; transition to LIVE is implicit when a live session is activated.

---

### LIVE

**Future state — not yet in current implementation.**

**Purpose**: Strategy has at least one active live trading session. LIVE is a runtime state, not a promotion state — strategies enter LIVE by activating a live session, not through a promotion approval.

**Entry requirements**: Strategy at APPROVED_FOR_LIVE; `LT_SESSION_ACTIVATED` event exists.

**Expected artifacts**: All APPROVED_FOR_LIVE artifacts; active `LiveTradingSession` record(s) with `status = running`.

**Allowed actions**: Monitor live sessions; pause/resume/stop live sessions.

**Disallowed actions**: Archiving while active live sessions exist (sessions must be terminated first).

**Exit behavior**: When all live sessions reach terminal state and no unresolved incidents are flagged, the strategy returns to `APPROVED_FOR_LIVE`. It retains live trading eligibility unless explicitly revoked or archived.

---

### REVOKED

**Purpose**: A governance authority has explicitly withdrawn a previously granted lifecycle authorization. REVOKED indicates that something was discovered — in live behavior, audit review, or governance investigation — that makes the previously granted authorization no longer appropriate.

REVOKED is distinct from ARCHIVED. Archival is user-initiated and preserves historical access. Revocation is governance-initiated and marks that a previously authorized state was explicitly invalidated.

**Entry requirements**: Strategy at LIVE, APPROVED_FOR_LIVE, or PAPER_TESTED; `GOV_PROMOTION_REVOKED` audit event exists with structured revocation reason; revocation authorized by admin or superadmin.

**Expected artifacts**: All artifacts from the preceding state, preserved intact and immutably; `GOV_PROMOTION_REVOKED` event.

**Allowed actions**: Review strategy definition and evidence; run additional research backtests; re-submit for review after the revocation reason is addressed; archive.

**Disallowed actions**: Activating any execution sessions; self-restoration.

**Path back**: A REVOKED strategy must re-enter the evidence and review workflow at the gate preceding the revoked authorization. A strategy revoked from APPROVED_FOR_LIVE must be re-reviewed from PAPER_TESTED with current evidence.

---

### ARCHIVED

**Purpose**: Strategy is no longer active. Preserved for historical reference. No execution of any kind is permitted.

**Entry requirements**: Any authorized user may archive their own strategy from any active state. Admins may archive strategies under their governance scope.

**Expected artifacts**: All artifacts from the preceding state, preserved intact.

**Allowed actions**: Review historical records; export historical data.

**Disallowed actions**: All execution modes; any lifecycle advancement; strategy definition modification.

**Terminal**: Once archived, a strategy cannot return to any active state. Users who wish to continue with a strategy's approach after archiving must create a new strategy draft.

---

## 5. Promotion Path

### Allowed Transitions

| From | To | Required Trigger |
|---|---|---|
| `DRAFT` | `VALIDATED` | Backend validation passes |
| `VALIDATED` | `BACKTESTED` | Reviewed promotion-grade backtest + `GOV_PROMOTION_APPROVED` |
| `BACKTESTED` | `FORWARD_TESTED` | Reviewed completed `ForwardTestSession` + `GOV_PROMOTION_APPROVED` |
| `FORWARD_TESTED` | `PAPER_TESTED` | Reviewed completed `PaperTradingSession` + `GOV_PROMOTION_APPROVED` |
| `PAPER_TESTED` | `APPROVED_FOR_LIVE` | Three-part evidence review + `GOV_STRATEGY_APPROVED_FOR_LIVE` + `explicit_acknowledgment_text` |
| `APPROVED_FOR_LIVE` | `LIVE` | Live trading session activated (`LT_SESSION_ACTIVATED`) |
| `LIVE` | `APPROVED_FOR_LIVE` | All live sessions terminal; no unresolved incidents |
| Any active state | `ARCHIVED` | User request (own strategy) or admin action |
| `LIVE` | `REVOKED` | Governance revocation + `GOV_PROMOTION_REVOKED` |
| `APPROVED_FOR_LIVE` | `REVOKED` | Governance revocation + `GOV_PROMOTION_REVOKED` |
| `PAPER_TESTED` | `REVOKED` | Governance revocation + `GOV_PROMOTION_REVOKED` |
| `REVOKED` | Prior active state | Re-review + new `GOV_PROMOTION_APPROVED` at appropriate gate |

### Invalid Transitions — Absolute Prohibitions

| From | To | Why Prohibited |
|---|---|---|
| `DRAFT` | Any state beyond `VALIDATED` | Unvalidated strategy cannot skip validation |
| `DRAFT` | `LIVE` | The primary governance bypass this lifecycle prevents |
| `VALIDATED` | `LIVE` | No backtest, forward test, paper trade, or review |
| `VALIDATED` | `APPROVED_FOR_LIVE` | Same as above |
| `VALIDATED` | `PAPER_TESTED` | Skips backtesting and forward testing |
| `BACKTESTED` | `LIVE` | No forward test evidence; no paper trade evidence |
| `BACKTESTED` | `APPROVED_FOR_LIVE` | Same as above |
| `FORWARD_TESTED` | `LIVE` | No paper trade evidence; no live authorization review |
| `FORWARD_TESTED` | `APPROVED_FOR_LIVE` | No paper trade evidence |
| `ARCHIVED` | Any state | Terminal — no un-archival path |
| Any state | Self-approval | User may not approve their own promotion |

### Transition Enforcement

All lifecycle transitions must be validated before the status field is updated.

An attempted invalid transition must:
1. Fail with a clear rejection reason
2. Emit a `GOV_LIFECYCLE_TRANSITION_DENIED` audit event with the attempted transition
3. Leave the strategy's lifecycle status unchanged

---

## 6. Evidence Requirements

Evidence requirements are defined by category, not by numerical threshold.

The platform defines what evidence types must exist before a promotion review can begin. The reviewer evaluates what that evidence demonstrates.

### Evidence Categories

**Backtest Evidence**
Historical simulation artifacts from the backtesting engine against versioned datasets under declared, explicit simulation assumptions.

Required form: Completed, non-failed promotion-grade backtest run records with full audit provenance, dataset traceability, tool resolution records, and declared simulation assumption sets.

**Forward Test Evidence**
Signal observation records from forward test sessions against live market data.

Required form: Completed `ForwardTestSession` records with intact `ForwardTestSignal` history; complete `FT_` audit trail (activation, signal events, data events, completion event).

**Paper Trading Evidence**
Execution records from paper trading sessions against live market data with a simulated account.

Required form: Completed `PaperTradingSession` records with fill history, position history, account history, equity curve; complete `PT_` audit trail (activation, order events, fill events, position events, account events, completion event).

**Audit Evidence**
The complete, immutable audit trail for all sessions cited as evidence. Proves that sessions were governed correctly — lifecycle gates enforced, ownership preserved, no bypass of constraints.

Required form: Complete `FT_` and `PT_` audit trails for cited sessions; `FT_ACTIVATION_DENIED` or `PT_ACTIVATION_DENIED` events where applicable (proving gate enforcement).

**Review Evidence**
Documentation that an authorized reviewer actually examined the evidence — not rubber-stamped it.

Required form: `GOV_PROMOTION_REVIEW_STARTED` event (reviewer identity and timestamp); `GOV_SESSION_REVIEWED` events for each session inspected.

**Governance Evidence**
The formal decision record authorizing or rejecting promotion.

Required form: `GOV_PROMOTION_APPROVED` or `GOV_PROMOTION_REJECTED` event with reviewer identity, decision timestamp, and the promotion gate being acted upon.

---

## 7. Backtest Promotion Requirements

### Gate: VALIDATED → BACKTESTED

Promotion to BACKTESTED requires review of backtest evidence demonstrating that the strategy has been evaluated against historical data under declared, explicit simulation assumptions.

### Required Artifacts

**Backtest Report**
At least one completed, non-failed promotion-grade backtest run. The run record must carry:
* Tool resolution record (tool versions, registry snapshot)
* Full simulation assumption set explicitly declared (fee model, slippage model, fill timing, position sizing model)
* Equity curve
* Trade list
* Signal diagnostics
* Warning summary — warnings in a promotion-grade run must be explicitly acknowledged, not suppressed

**Dataset Provenance**
The run references a versioned dataset with stable identity (provider + symbol + timeframe + version, or catalog ID). Dataset covers the full evaluation period plus warmup requirements.

**Strategy Provenance**
The run references the strategy definition by `draft_id` and version. The strategy must have been at `lifecycle_status = validated` at the time of the run.

**Execution Provenance**
The backtest audit record exists in the platform's audit trail, linking the run to its input declaration and output artifact.

**Review Notes**
The reviewer has accessed the backtest result (`GOV_PROMOTION_REVIEW_STARTED`, `GOV_SESSION_REVIEWED`). The `GOV_PROMOTION_APPROVED` event is written by an authorized party after review.

### Evidence Completeness Requirements

A backtest run is not admissible as promotion evidence if:
* Run status is `failed` or `terminated` (completed runs only)
* The tool resolution record references deprecated versions without explicit acknowledgment
* The simulation assumption set contains undeclared or silently defaulted parameters
* Warnings exist in a promotion-grade run that were not explicitly acknowledged

---

## 8. Forward Testing Promotion Requirements

### Gate: BACKTESTED → FORWARD_TESTED

Promotion to FORWARD_TESTED requires review of forward test evidence demonstrating that the strategy generates signals as expected under live market conditions.

### Required Artifacts

**ForwardTestSession History**
At least one completed `ForwardTestSession` (status = `completed`; not `failed` or `terminated`). The session must:
* Have a sealed strategy snapshot with `lifecycle_status_at_activation >= backtested`
* Have processed bars beyond the warmup period (signal-eligible bars were evaluated)

**Signal History**
The session contains `ForwardTestSignal` records. The signal history is intact — no gaps or deletions in the record sequence.

A completed session with zero signals during signal-eligible bars is a meaningful observation but may indicate the strategy was not active in the observed market conditions. The reviewer determines whether this constitutes adequate evidence.

**Session Audit Trail**
The complete `FT_` audit trail must exist:
* `FT_SESSION_ACTIVATED` — strategy lifecycle status at activation
* `FT_SESSION_COMPLETED` — session reached terminal state gracefully
* `FT_SIGNAL_GENERATED` events — the primary evidence
* Any `FT_GAP_DETECTED`, `FT_PROVIDER_FAILURE` events — data quality context

**Failure Records**
Any `FT_SESSION_PAUSED_PROVIDER_FAILURE` or `FT_SESSION_FAILED` events must be disclosed to the reviewer. Sessions with significant provider failure histories may not constitute strong evidence; the reviewer evaluates materiality.

**Review Notes**
The reviewer has accessed the session (`GOV_SESSION_REVIEWED`) before the promotion decision.

### Evidence Completeness Requirements

A forward test session is not admissible as promotion evidence if:
* Session status is `failed` or `terminated`
* The session's audit trail is incomplete (missing required lifecycle events)
* The session's `lifecycle_status_at_activation` was below `backtested`
* The session was activated before the strategy reached `BACKTESTED` status (exploratory forward tests at the VALIDATED stage do not count for this gate)

---

## 9. Paper Trading Promotion Requirements

### Gate: FORWARD_TESTED → PAPER_TESTED

Promotion to PAPER_TESTED requires review of paper trading evidence demonstrating that the strategy's execution behavior — fills, position management, capital utilization, equity curve, drawdown — is coherent and acceptable under live market conditions.

### Required Artifacts

**PaperTradingSession History**
At least one completed `PaperTradingSession` (status = `completed`). The session must:
* Have `lifecycle_status_at_activation >= forward_tested` (per full governance path)
* Have produced fills — a session with zero fills provides no execution evidence

**Order History**
The complete order record including rejected orders. Rejected orders with reason codes (`insufficient_cash`, `max_positions_exceeded`) are part of execution evidence — they demonstrate how signals interacted with capital constraints.

**Fill History**
The complete `PaperFill` record set. Each fill carries `gross_fill_price`, `slippage_applied`, `net_fill_price`, `fee_applied`, and `execution_reason`. Fills must be traceable through `source_signal_id` back to originating signals.

**Position History**
The complete `PaperPosition` record set — open and closed — for the session. Position history enables the reviewer to evaluate trade duration, entry/exit timing, and whether exit rules fired as expected.

**Account History**
The account equity curve and final session metrics: `total_return_pct`, `max_drawdown_pct`, `total_trades`, `win_count`, `loss_count`, `profit_factor`.

**Audit Trail**
The complete `PT_` audit trail:
* `PT_SESSION_ACTIVATED` — strategy lifecycle status and starting equity
* `PT_SESSION_COMPLETED` — final equity metrics
* `PT_FILL_CREATED` events — execution evidence
* `PT_POSITION_OPENED` / `PT_POSITION_CLOSED` — trade lifecycle
* `PT_ACCOUNT_UPDATED` — equity history
* `PT_ORDER_REJECTED` — capital constraint behavior
* `PT_DRAWDOWN_WARNING` / `PT_DRAWDOWN_STOP_TRIGGERED` — risk behavior evidence

**Review Notes**
The reviewer has accessed the session (`GOV_SESSION_REVIEWED`) before the promotion decision.

### Evidence Completeness Requirements

A paper trading session is not admissible as promotion evidence if:
* Session status is `failed` or `terminated`
* `simulation_assumptions` were modified mid-session
* The session produced zero fills
* The session audit trail is missing required events
* The session was activated before the strategy reached `FORWARD_TESTED` status

---

## 10. Review Workflow

Promotion review is the human governance process that transforms evidence into a lifecycle decision.

### Promotion Request

The strategy owner submits a formal promotion request when they believe sufficient evidence exists.

The request:
* Identifies the strategy and the requested target lifecycle status
* References the session(s) or artifact(s) constituting the evidence
* Is recorded as a `GOV_PROMOTION_REQUESTED` audit event

The request does not advance lifecycle status. It initiates the review workflow.

### Promotion Review

An authorized reviewer (admin or superadmin) receives the promotion request and:

1. Accesses the strategy's current lifecycle status and evidence base
2. Reviews each cited evidence artifact (backtest runs, forward test sessions, paper trading sessions)
3. Examines the audit trail for each cited session

Each piece of evidence accessed for review must produce a `GOV_SESSION_REVIEWED` audit event.

Review begins when `GOV_PROMOTION_REVIEW_STARTED` is recorded. This establishes:
* Who is conducting the review
* When the review began
* Which promotion request is under review

### Promotion Decision

After reviewing, the reviewer makes one of two decisions.

**Approve**: The evidence is sufficient for the requested advancement.
* `GOV_PROMOTION_APPROVED` event is recorded
* The strategy's `lifecycle_status` advances
* For `APPROVED_FOR_LIVE`: `explicit_acknowledgment_text` is also required (see §12)

**Reject**: The evidence is insufficient or strategy behavior is not acceptable.
* `GOV_PROMOTION_REJECTED` event is recorded with structured rejection reason
* The strategy's `lifecycle_status` is unchanged
* The user may gather additional evidence and resubmit

### Promotion Documentation

Every promotion decision requires audit events:
* Approval: `GOV_PROMOTION_REVIEW_STARTED` → `GOV_SESSION_REVIEWED` (per session) → `GOV_PROMOTION_APPROVED`
* Rejection: `GOV_PROMOTION_REVIEW_STARTED` → `GOV_PROMOTION_REJECTED`

A promotion that lacks `GOV_PROMOTION_REVIEW_STARTED` is a rubber-stamp approval. It is not valid under this governance model.

### Promotion Audit Record

The audit record for a promotion decision is the permanent evidence that governance was exercised. It must be retained permanently per the retention policy in `docs/EXECUTION_AUDIT_MODEL.md`.

### Promotion Notification

After a decision, the strategy owner is notified:
* On approval: new lifecycle status available; eligible execution modes expanded
* On rejection: structured rejection reason communicated; owner may gather additional evidence and resubmit

Notification mechanism (email, in-platform, API response) is an implementation concern not defined here.

---

## 11. Roles and Responsibilities

### User (Strategy Owner)

**Responsibilities**:
* Authors strategy definitions in the Composer
* Runs backtests, forward test sessions, and paper trading sessions to build evidence
* Submits promotion requests when evidence is believed sufficient
* Responds to promotion rejections (addresses issues, gathers more evidence)

**Capabilities**:
* May request promotion at any gate
* May archive their own strategies at any stage
* May view their own sessions and audit trails

**Restrictions**:
* May not approve their own or any other user's promotion
* May not revoke lifecycle status
* May not access other users' strategies or sessions

### Admin

**Responsibilities**:
* Receives and reviews promotion requests
* Examines evidence artifacts and audit trails
* Makes promotion approval or rejection decisions
* Records the decision in the governance audit trail
* May initiate revocation when evidence of strategy issues emerges

**Capabilities**:
* May approve or reject promotion at any gate
* May initiate revocation from PAPER_TESTED, APPROVED_FOR_LIVE, or LIVE
* May access any user's strategy or sessions through admin-scoped interfaces (access is itself audited)

**Restrictions**:
* May not approve their own strategy promotions (no self-promotion)
* May not approve promotions for strategies lacking required evidence artifacts
* May not modify audit records

**Entitlement invariant**: An admin's review and approval authority must never depend on their own subscription status. `require_admin_role` never depends on `require_active_subscription`. This constraint is non-negotiable and is consistent with the existing platform entitlement model.

### Superadmin

All admin capabilities, plus:

**Responsibilities**:
* Final governance authority for live trading authorization (`PAPER_TESTED → APPROVED_FOR_LIVE`)
* Revocation authority for APPROVED_FOR_LIVE and LIVE strategies

**Notes**: The `APPROVED_FOR_LIVE` gate is the highest-stakes governance decision on the platform. While the architecture permits any admin to authorize live trading per the entitlement model, platforms in regulated environments should consider restricting live trading authorization to superadmin only. This is a deployment-level governance decision.

### Future Reviewer Role (Conceptual)

As the platform scales, a dedicated reviewer role may be introduced. This conceptual role would:

* Hold explicit review authority for specific asset classes, strategy types, or execution modes
* Operate independently of the admin role (not requiring general user management capabilities)
* Have audit access scoped to strategies under their review authority
* Be required to recuse from reviewing strategies they authored or have a conflict of interest in

The Future Reviewer Role is not currently implemented. It is defined here as a governance concept for when the platform requires formal reviewer independence beyond the admin model.

---

## 12. Approval Requirements

### Who May Approve

Promotion approval at all gates requires `require_admin_role`.

Any user holding admin or superadmin role may approve promotion requests.

No regular user may approve any promotion — their own or another's.

No mechanism — technical shortcut, API bypass, direct database update — may substitute for the explicit governance approval workflow.

### Who May Review

Promotion evidence may be reviewed by:
* The strategy owner (to prepare their evidence submission)
* Any admin or superadmin (to evaluate the evidence and make a decision)

The `GOV_PROMOTION_REVIEW_STARTED` event identifies who initiated the formal review session.

### Who May Reject

Any user with `require_admin_role` may reject a promotion request. Rejection must record a structured `rejection_reason_category`. Unexplained rejections are not valid governance decisions.

### Who May Revoke

Revocation requires `require_admin_role`. Revocation of `APPROVED_FOR_LIVE` status should be treated with the same gravity as the original approval — both are high-stakes governance decisions.

### No Self-Promotion

No user may approve the advancement of their own strategy. A user who is also an admin must have a different admin or superadmin review and approve their own strategy's promotion. Platform governance must enforce reviewer independence at all gates, especially at APPROVED_FOR_LIVE.

### Relationship to GOV_* Audit Events

| Decision | Required audit events |
|---|---|
| Approval at any gate | `GOV_PROMOTION_REVIEW_STARTED` + `GOV_SESSION_REVIEWED` (per session) + `GOV_PROMOTION_APPROVED` |
| Rejection at any gate | `GOV_PROMOTION_REVIEW_STARTED` + `GOV_PROMOTION_REJECTED` |
| Approval for paper trading eligibility | `GOV_STRATEGY_APPROVED_FOR_PAPER` |
| Approval for live trading | `GOV_STRATEGY_APPROVED_FOR_LIVE` + `explicit_acknowledgment_text` |
| Revocation | `GOV_PROMOTION_REVOKED` |

A promotion decision without the corresponding audit events did not happen in the governance record.

### Explicit Acknowledgment for Live Trading Authorization

The `GOV_STRATEGY_APPROVED_FOR_LIVE` event requires a non-empty `explicit_acknowledgment_text` field.

This field must contain text that the approver explicitly confirms — not system-generated, not pre-filled, not boilerplate. It is a non-repudiation requirement: the approver's own words, recorded permanently, as evidence that this decision was made knowingly.

The text must at minimum acknowledge:
* The strategy identifier and version being approved
* That the approver has reviewed the three-part evidence base (backtest results, forward test session history, paper trading session history)
* That the approver takes responsibility for this authorization

The specific required phrasing is an operational governance decision. This document specifies the requirement; the exact text template is defined at deployment time.

---

## 13. Promotion Audit Requirements

All promotion governance events must be recorded through the platform's existing `emit_audit_event()` infrastructure, consistent with the taxonomy in `docs/EXECUTION_AUDIT_MODEL.md`.

### Required Events

**`GOV_PROMOTION_REQUESTED`**

Purpose: Initiates the governance chain. All subsequent events link via `promotion_request_id`.

Required payload: `strategy_id`, `strategy_version`, `current_lifecycle_status`, `requested_lifecycle_status`, `requester_user_id`, `session_ids_as_evidence` (list), `request_timestamp`

---

**`GOV_PROMOTION_REVIEW_STARTED`**

Purpose: Establishes accountability for who reviewed the evidence and when. A promotion without this event was not formally reviewed.

Required payload: `promotion_request_id`, `reviewer_user_id`, `review_start_timestamp`

---

**`GOV_PROMOTION_APPROVED`**

Purpose: The authoritative governance decision record. Permanently documents that lifecycle advancement was explicitly authorized, not automatic.

Required payload: `promotion_request_id`, `reviewer_user_id`, `strategy_id`, `previous_lifecycle_status`, `new_lifecycle_status`, `approval_timestamp`, `reviewer_notes` (optional structured field)

---

**`GOV_PROMOTION_REJECTED`**

Purpose: Documents the negative decision. The rejection reason is available to the strategy owner for remediation.

Required payload: `promotion_request_id`, `reviewer_user_id`, `strategy_id`, `current_lifecycle_status`, `rejection_reason_category`, `rejection_timestamp`

---

**`GOV_PROMOTION_REVOKED`**

Purpose: Documents that lifecycle authorization is not permanent and may be explicitly withdrawn.

Required payload: `strategy_id`, `revoked_by_user_id`, `previous_lifecycle_status`, `new_lifecycle_status`, `revocation_reason`, `revocation_timestamp`

---

**`GOV_SESSION_REVIEWED`**

Purpose: Proves that the reviewer actually inspected the evidence before deciding. The primary protection against rubber-stamp approvals.

Required payload: `session_id`, `reviewer_user_id`, `review_type` (`promotion_review`, `incident_review`, `compliance_review`), `session_type` (`forward_test`, `paper_trading`, `live_trading`), `review_timestamp`

---

**`GOV_STRATEGY_APPROVED_FOR_PAPER`**

Purpose: Records the moment the paper trading eligibility gate was formally opened for this strategy.

Required payload: `strategy_id`, `approver_user_id`, `evidence_session_ids`, `approval_timestamp`

---

**`GOV_STRATEGY_APPROVED_FOR_LIVE`**

Purpose: The highest-stakes governance event on the platform. Permanently documents who authorized live trading, when, based on what evidence, and with what explicit acknowledgment.

Required payload: `strategy_id`, `approver_user_id`, `evidence_session_ids`, `approval_timestamp`, `explicit_acknowledgment_text` (non-repudiation; must be non-empty; must be the approver's own confirmed text — not system-generated)

---

### Audit Retention

All promotion governance audit events must be retained permanently, consistent with the `GOV_` event retention tier in `docs/EXECUTION_AUDIT_MODEL.md`.

A promotion decision with missing or expired audit records cannot be verified. Governance audit records must never expire.

---

## 14. Revocation Model

### Why Strategies May Be Revoked

Revocation is triggered by discovering that the conditions under which an authorization was granted no longer hold, or that the strategy has exhibited unacceptable behavior.

**Unexpected behavior in a live session**: Signal patterns, position accumulation, or risk rule behavior that was not observed in paper testing.

**Provider issues discovered post-authorization**: If data quality issues are discovered in the evidence sessions after authorization, the evidence base is compromised.

**Audit concerns**: If a review discovers missing required events, incomplete evidence records, or a review process not properly followed.

**Governance concerns**: If the original promotion review lacked adequate independence (for example, a reviewer approved their own strategy), the authorization is invalid.

**Operational incidents**: A live trading safety event (emergency stop, broker connection failure with open positions) may trigger session termination and revocation pending incident review.

### Revocation from LIVE

When a live trading session is active and revocation is initiated:

1. The live trading session must be safely terminated before revocation takes effect (to address open real positions)
2. Termination produces `LT_SESSION_TERMINATED` and `LT_POSITION_FORCE_CLOSED` audit events
3. `GOV_PROMOTION_REVOKED` is written after session termination
4. The strategy transitions to REVOKED

Revocation must not leave real positions unaddressed.

### Revocation from APPROVED_FOR_LIVE

When no live sessions are active and authorization is revoked:

1. `GOV_PROMOTION_REVOKED` is written immediately
2. The strategy transitions to REVOKED
3. No live sessions can be activated while in REVOKED state

### Revocation from PAPER_TESTED

When a paper-tested strategy is revoked (typically due to governance concern or discovered evidence issue):

1. `GOV_PROMOTION_REVOKED` is written with `new_lifecycle_status = forward_tested` (or lower, depending on the scope of the issue)
2. The strategy is demoted to the appropriate prior state
3. The REVOKED designation applies if the issue affects the evidence base itself, not merely the review process

### Revocation Auditability

Every revocation produces a permanent, immutable audit record: the revocation reason, the revoked-by identity, and the previous state are all preserved.

A revocation cannot be undone. If a strategy is re-promoted after revocation, the revocation audit record remains. The history shows: promoted → revoked → re-promoted. This history is permanent.

### Revocation Does Not Destroy Evidence

When a strategy is revoked, all preceding evidence artifacts are preserved intact and immutably.

The evidence is not invalidated — the authorization is revoked. A future reviewer will see both the historical evidence and the revocation record.

---

## 15. Relationship To Existing Lifecycle Status

### Current Implementation

The current QuantLab implementation enforces the following `StrategyLifecycleStatus` enum values in `validate_lifecycle_transition()`:

```
draft
validated
backtested
paper_tested
approved_for_live
archived
```

These six states are currently implemented and in production.

### What Is Missing From the Current Implementation

The full governance lifecycle defined in this document adds three states:

**`forward_tested`**: Between `backtested` and `paper_tested`.

*When introduced*: When the Forward Testing Runtime is implemented. `forward_tested` will be added to `StrategyLifecycleStatus` and `validate_lifecycle_transition()` will be updated to require forward testing evidence before paper trading qualifies as promotion-eligible.

**`live`**: After `approved_for_live`, indicating an active live trading session.

*When introduced*: When the Live Trading Runtime is implemented.

**`revoked`**: For strategies with explicitly withdrawn authorizations.

*When introduced*: When the governance workflow implementation begins.

### Alignment Table

| Current State | Full Governance State | Status |
|---|---|---|
| `draft` | `DRAFT` | Implemented |
| `validated` | `VALIDATED` | Implemented |
| `backtested` | `BACKTESTED` | Implemented |
| — | `FORWARD_TESTED` | Future state |
| `paper_tested` | `PAPER_TESTED` | Implemented |
| `approved_for_live` | `APPROVED_FOR_LIVE` | Implemented |
| — | `LIVE` | Future state |
| — | `REVOKED` | Future state |
| `archived` | `ARCHIVED` | Implemented |

### Backward Compatibility

When `forward_tested` is introduced, the existing transition `backtested → paper_tested` will require migration consideration. Strategies currently at `paper_tested` that were promoted without a `forward_tested` intermediate stage were promoted under the earlier governance model. These strategies should not be retroactively penalized — their evidence base (backtest + paper trading) is the evidence that existed under the model in which they were promoted. The migration policy for existing strategies is an operational decision to be made at implementation time.

---

## 16. Relationship To Execution Modes

The lifecycle state directly governs which execution modes a strategy is eligible for.

### Eligibility Mapping

| Lifecycle State | Backtesting | Forward Testing | Paper Trading | Live Trading |
|---|---|---|---|---|
| `DRAFT` | No | No | No | No |
| `VALIDATED` | Yes | Yes (exploratory) | No | No |
| `BACKTESTED` | Yes | Yes (promotion-eligible) | Yes (exploratory) | No |
| `FORWARD_TESTED` | Yes | Yes | Yes (promotion-eligible) | No |
| `PAPER_TESTED` | Yes | Yes | Yes | No |
| `APPROVED_FOR_LIVE` | Yes | Yes | Yes | Yes |
| `LIVE` | Yes | Yes | Yes | Yes (active) |
| `REVOKED` | No | No | No | No |
| `ARCHIVED` | No | No | No | No |

### Exploratory vs. Promotion-Eligible

**Exploratory**: The execution mode can be activated at this lifecycle stage, but sessions conducted here do not constitute promotion-eligible evidence for the gate requiring higher lifecycle status.

**Promotion-Eligible**: Sessions conducted at or above this lifecycle stage constitute valid evidence for the corresponding promotion gate.

This distinction prevents researchers from accumulating promotion evidence on under-promoted strategies.

### Enforcement at Session Activation

| Mode | Minimum lifecycle for activation | Denial event |
|---|---|---|
| Backtesting | `validated` | N/A |
| Forward testing | `validated` | `FT_ACTIVATION_DENIED` |
| Paper trading | `backtested` | `PT_ACTIVATION_DENIED` |
| Live trading | `approved_for_live` | `LT_ACTIVATION_DENIED` |

Activation denial events are permanent audit records.

---

## 17. Evidence Preservation Requirements

All evidence artifacts cited in a promotion decision must be preserved intact and immutably for the lifetime of the promotion decision.

### What Must Be Preserved

**Strategy Snapshot**: The sealed `strategy_snapshot` from each cited session must remain intact. The `strategy_snapshot_hash` must remain verifiable.

**Dataset Provenance**: The backtest run's dataset reference must remain resolvable. For catalog-sourced backtests: the `catalog_id` must remain registered. For provider-sourced data: the dataset identity must be preserved in the audit record.

**Audit Records**: All `FT_`, `PT_`, and `GOV_` audit records for sessions cited as evidence must be retained permanently.

**Review Records**: `GOV_PROMOTION_REVIEW_STARTED`, `GOV_SESSION_REVIEWED`, and `GOV_PROMOTION_APPROVED` events must be retained permanently.

**Approval Records**: The `GOV_STRATEGY_APPROVED_FOR_LIVE` event — including the `explicit_acknowledgment_text` — must be retained permanently.

### No Mutable References

Evidence references must point to immutable artifacts, not to live mutable state. This is already satisfied by the session architecture: every session captures a sealed `strategy_snapshot` at activation time.

### No Hidden Evidence

All evidence used to make a promotion decision must be referenced in the `GOV_PROMOTION_APPROVED` event's `evidence_session_ids` field. Evidence that was examined but not cited in the approval record is not part of the governance record. A reviewer may not base a decision on evidence that is not recorded.

---

## 18. Non-Negotiable Constraints

**No automatic promotion**: No system event, session completion, or performance metric may advance lifecycle status. Advancement requires a human approval event.

**No profitability-only promotion**: Profitability in a backtest or paper trading session is not a sufficient basis for promotion. The platform does not define performance thresholds. Performance evaluation is the reviewer's responsibility.

**No bypass of governance review**: A lifecycle status update must not be possible without a corresponding `GOV_PROMOTION_APPROVED` audit event. Direct database updates, API bypasses, or undocumented status changes are architectural violations.

**No direct DRAFT → LIVE path**: A strategy cannot reach any live execution mode without passing through VALIDATED, BACKTESTED, FORWARD_TESTED, PAPER_TESTED, and APPROVED_FOR_LIVE in order.

**No evidence before required predecessor state**: Paper trading sessions used as promotion evidence must have been conducted after the strategy reached FORWARD_TESTED status. Forward test sessions used as promotion evidence must have been conducted after the strategy reached BACKTESTED status.

**No approval without audit records**: A promotion without `GOV_PROMOTION_REVIEW_STARTED`, `GOV_SESSION_REVIEWED`, and `GOV_PROMOTION_APPROVED` events is not a valid promotion under this governance model.

**No self-promotion**: A user may not approve the advancement of their own strategy. No admin may approve a promotion for a strategy they authored without an independent reviewer.

**No live authorization without explicit acknowledgment**: `GOV_STRATEGY_APPROVED_FOR_LIVE` requires a non-empty `explicit_acknowledgment_text`. A live trading authorization without this field is structurally incomplete.

**No post-revocation or post-archival execution**: A strategy in REVOKED or ARCHIVED state must not be eligible for any execution mode. Revocation and archival must be enforced at session activation time.

---

## 19. Future Relationship

### Forward Testing Runtime

When implemented:
* `forward_tested` lifecycle state activates
* `ForwardTestSession` activation enforces `lifecycle_status >= backtested` for promotion-eligible sessions
* `GOV_PROMOTION_APPROVED` with `new_lifecycle_status = forward_tested` becomes available
* Migration consideration required for strategies at `paper_tested` promoted under the interim model

### Paper Trading Runtime

When implemented:
* `PaperTradingSession` activation enforces `lifecycle_status >= forward_tested` for promotion-eligible sessions
* The three-part evidence base (backtest + forward test + paper trading) becomes standard for APPROVED_FOR_LIVE review

### Broker Integration

When IBKR or Binance adapters are implemented:
* `LiveTradingSession` activation requires `lifecycle_status = approved_for_live` with strict enforcement
* `LT_SESSION_ACTIVATED` is the trigger for transitioning to LIVE state
* Broker credential resolution is audited through `LT_CREDENTIAL_RESOLVED`

### Live Trading

When live trading is implemented:
* `live` lifecycle state activates
* `LIVE → APPROVED_FOR_LIVE` transition (on normal session completion) is implemented
* `LIVE → REVOKED` transition with session-safe termination is implemented
* Emergency stop handling integrates with the revocation model

### Reviewer Workflows

When a dedicated reviewer role is introduced:
* `require_reviewer_role` guard created alongside `require_admin_role`
* Independence principle (no self-review) formalized in the role model
* Reviewer authority scoped to strategy types or asset classes as appropriate

### Compliance Workflows

When compliance workflows are introduced:
* A `COMPLIANCE_REVIEW` event type is added to the governance audit taxonomy
* Compliance review becomes a distinct gate from promotion review
* Compliance approval produces its own audit event, distinct from `GOV_STRATEGY_APPROVED_FOR_LIVE`

---

## 20. Promotion Readiness Philosophy

Promotion readiness is not a performance metric. It is a governance confidence threshold.

A strategy is promotion-ready when:
* **Sufficient evidence** exists — the required artifact types are present, complete, and intact
* **Sufficient review** has occurred — an authorized, independent party has examined the evidence
* **Sufficient governance confidence** — the reviewer has concluded the evidence is adequate for the next stage
* **The decision is documented** — the review and decision are permanently recorded in the audit trail

### What Promotion Readiness Is Not

* Achieving a target return
* Reaching a minimum win rate
* Staying within a maximum drawdown
* Generating a minimum number of signals

A strategy that consistently generates expected signals, exhibits coherent position cycling, and demonstrates disciplined capital utilization may be promotion-ready even if paper trading results are not profitable.

A strategy with exceptional paper trading P&L but whose audit trail reveals significant gaps, unaddressed provider failures, or anomalous signal behavior may not be promotion-ready.

### The Three-Party Governance Structure

Promotion governance depends on three distinct parties operating in their defined roles:

**The Platform**: Guarantees the completeness, integrity, and immutability of the evidence. The platform cannot be bypassed. Every execution action is audited. Every lifecycle gate is enforced. The audit trail is the institutional memory.

**The Reviewer**: Evaluates what the evidence demonstrates. The reviewer brings judgment that the platform cannot encode — an understanding of market conditions, strategy design, and risk tolerance that determines whether evidence is adequate. The reviewer takes personal responsibility for the approval decision via the `explicit_acknowledgment_text`.

**The Audit Trail**: Makes the decision permanently accountable. The audit trail exists after the reviewer is gone, after the strategy has been archived, after the platform has been upgraded. It answers, forever: what evidence existed, who reviewed it, and what they decided.

This three-party structure is why promotion governance is not reducible to automated threshold checking. The platform creates the evidence. The reviewer evaluates it. The audit trail remembers the decision.

---

## Summary

```
LIFECYCLE STATES
    DRAFT → VALIDATED → BACKTESTED → FORWARD_TESTED → PAPER_TESTED
        → APPROVED_FOR_LIVE → LIVE → (returns to APPROVED_FOR_LIVE on normal end)
    Any active state → ARCHIVED (terminal)
    LIVE / APPROVED_FOR_LIVE / PAPER_TESTED → REVOKED (re-review required)

PROMOTION PATH (required order; no shortcuts)
    DRAFT → VALIDATED            backend validation passes
    VALIDATED → BACKTESTED       promotion-grade backtest + reviewed
    BACKTESTED → FORWARD_TESTED  completed FT session + reviewed
    FORWARD_TESTED → PAPER_TESTED completed PT session + reviewed
    PAPER_TESTED → APPROVED_FOR_LIVE  three-part evidence + explicit acknowledgment
    APPROVED_FOR_LIVE → LIVE     live session activated (runtime state, not governance gate)

EVIDENCE CATEGORIES (required at appropriate gates)
    Backtest Evidence      completed promotion-grade backtest run
    Forward Test Evidence  completed ForwardTestSession with signal history
    Paper Trading Evidence completed PaperTradingSession with fills and equity
    Audit Evidence         complete FT_/PT_/GOV_ audit trail for cited sessions
    Review Evidence        GOV_PROMOTION_REVIEW_STARTED + GOV_SESSION_REVIEWED
    Governance Evidence    GOV_PROMOTION_APPROVED or GOV_STRATEGY_APPROVED_FOR_LIVE

REVIEW WORKFLOW (all human-governed; no automatic promotion)
    User → GOV_PROMOTION_REQUESTED
    Reviewer → GOV_PROMOTION_REVIEW_STARTED
    Reviewer inspects each session → GOV_SESSION_REVIEWED
    Reviewer decides → GOV_PROMOTION_APPROVED or GOV_PROMOTION_REJECTED
    For live trading → GOV_STRATEGY_APPROVED_FOR_LIVE + explicit_acknowledgment_text

REVOCATION MODEL
    Triggered by: unexpected behavior, audit concern, governance concern, incident
    From: LIVE, APPROVED_FOR_LIVE, PAPER_TESTED
    Produces: GOV_PROMOTION_REVOKED (permanent, immutable)
    Path back: re-evidence and re-review from prior gate
    Evidence preserved: revocation does not destroy preceding artifacts

NON-NEGOTIABLE CONSTRAINTS
    No automatic promotion
    No profitability-only promotion
    No governance bypass
    No DRAFT → LIVE shortcut (or any skip of intermediate states)
    No evidence before required predecessor state
    No approval without audit records
    No self-promotion
    No live authorization without explicit acknowledgment
    No execution in REVOKED or ARCHIVED state

PROMOTION READINESS PHILOSOPHY
    = Sufficient evidence (required artifact types, complete and intact)
    + Sufficient review (authorized independent reviewer examined the evidence)
    + Sufficient governance confidence (reviewer takes responsibility for the decision)
    ≠ Achieving return thresholds
    ≠ Passing numerical performance gates
```

Promotion governance is the mechanism by which QuantLab ensures that live capital is never committed to a strategy that has not earned access through evidence, review, and explicit human accountability.

The audit trail is the institutional memory that makes every promotion decision permanently answerable.

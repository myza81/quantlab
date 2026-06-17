# Engine Record: Minor Structure Ignore Inside Bar

---

| Field | Value |
|---|---|
| **Human-Friendly Name** | Minor Structure Ignore Inside Bar |
| **Technical ID** | `minor_structure_v2` |
| **Engine Type** | Minor Structure |
| **Lifecycle Status** | **Experimental** |
| **Created Date** | 2026-06-16 |
| **Frozen Date** | — |
| **Retired Date** | — |
| **Rulebook Status** | **Active** |
| **Validation Status** | Not validated — no implementation yet |
| **Supersedes** | — |
| **Superseded By** | — |

---

## Purpose

Test whether ignoring inside bars during structure construction produces cleaner and more visually intuitive minor structure.

Inside bars in V1 participate in structure via a close-comparison reversal gate — `close < prev.close` reverses from UP, `close > prev.close` reverses from DOWN. This experimental version removes that gate entirely: inside bars do not define structure and do not trigger reversals. For clusters of 4 or more consecutive inside bars, a single confirmed pivot is created at the cluster's true price extreme after breakout. The hypothesis is that this produces fewer, more meaningful pivots.

---

## Implementation Status

**Design only. No runtime implementation exists.**

This record documents the intended rulebook for `minor_structure_v2`. Runtime code must not be written until this design is reviewed and explicitly approved.

Planned implementation location (when approved):

```
backend/tools/market_structure/
    v1/
        engine.py       ← existing V1 logic extracted here (do not modify V1 behaviour)
    v2/
        engine.py       ← new experimental engine (to be created)
    contract.py         ← shared contract types (input/output schemas)
```

V1 must not be modified during V2 implementation. V2 must be a fully independent module.

---

## Rules

### Baseline

All `minor_structure_v1` rules apply, **except inside-bar handling**. The following are unchanged:

- Candle classification system (HH, LL, IB, OB)
- Direction machine (startup phase, UP continuation, DOWN continuation)
- Tracker-based pivot placement (MS-4B: `last_high_candle` / `last_low_candle`)
- Minor container pivot refinement pass (MS-4F)
- Determinism — no state retained between calls

### Inside-Bar Definition

A candle is inside the mother candle `n0` when **both** conditions hold:

```
current.high < n0.high
current.low  > n0.low
```

The comparison is always against the mother candle `n0`, not against the immediately previous candle. The mother candle `n0` remains the comparison reference for the entire cluster, until breakout.

### Inside-Bar Cluster Rules

**Rule 1 — Single inside bar (`n1` inside `n0`):**

- Continue the previous structure direction.
- Do not create a pivot.
- Do not reverse structure.

**Rule 2 — Cluster continues (subsequent candle also inside `n0`):**

- Continue previous structure direction.
- Do not create a pivot.
- Do not reverse structure.
- `n0` remains the comparison reference for all subsequent inside-bar checks.

**Rule 3 — Cluster of 1, 2, or 3 inside bars (breakout before reaching 4):**

- No inside-bar pivot is created for the cluster.
- When breakout occurs, apply V1 rules to the breakout candle.

**Rule 4 — Cluster of 4 or more consecutive inside bars:**

A pivot is created only after the cluster breaks out. The pivot is not created during the cluster.

When breakout is confirmed:

- If previous structure direction was **UP**:
  - Find the candle with the **lowest low** among all candles inside the cluster.
  - Create a **pivot low** at that candle.
- If previous structure direction was **DOWN**:
  - Find the candle with the **highest high** among all candles inside the cluster.
  - Create a **pivot high** at that candle.

Then apply V1 rules to the breakout candle.

### Important Clarifications

- The mother candle `n0` is the fixed comparison reference for the entire cluster. It does not update as each inside bar is processed.
- Inside bars do not define immediate structure.
- Inside bars do not immediately reverse structure.
- Inside bars continue the previous structure direction throughout the cluster.
- The 4+ cluster pivot is only confirmed after breakout; it does not exist while the cluster is accumulating.
- For clusters of 1, 2, or 3 inside bars, no pivot is created. The breakout candle is processed by V1 rules directly.

---

## V1 vs V2 Comparison

| Behaviour | V1 (Classic Minor Structure) | V2 (Ignore Inside Bar) |
|---|---|---|
| Inside bar in UP direction | `close < prev.close` → reverse to DOWN | Continue UP; track cluster |
| Inside bar in DOWN direction | `close > prev.close` → reverse to UP | Continue DOWN; track cluster |
| Comparison reference | Previous candle | Original mother candle `n0` for full cluster |
| Cluster of 1–3 inside bars | Each bar tested via close gate individually | No pivot; breakout candle processed by V1 rules |
| Cluster of 4+ inside bars | Each bar tested via close gate individually | Confirmed pivot at cluster extreme after breakout |
| Outside bar handling | Always continues current direction | Unchanged — always continues current direction |
| Tracker-based pivots (MS-4B) | Yes | Yes (unchanged) |
| Refinement pass (MS-4F) | Yes | Yes (unchanged) |

---

## Input Contract

Same as `minor_structure_v1`.

```
Input:  list[OHLCVCandle]

OHLCVCandle:
  timestamp:   str          ISO 8601 UTC
  bar_index:   int          Zero-based sequential index
  open:        float
  high:        float
  low:         float
  close:       float
  volume:      float
```

Minimum viable input: 2 candles.

---

## Output Contract

Same as `minor_structure_v1`.

```
Output (minor portion):
  minor_points:  list[StructurePoint]
  minor_legs:    list[StructureLeg]
  debug_events:  list[StructureDebugEvent]
```

The point schema, leg schema, and debug event schema are identical to V1. No new contract types are introduced.

---

## Dependencies

| Dependency | Role |
|---|---|
| `OHLCVCandle` | Input data schema |
| `StructurePoint` | Output point schema |
| `StructureLeg` | Output leg schema |
| `StructureDebugEvent` | Debug output schema |
| `StructureLevel.MINOR` | Level tag applied to all output |
| `PointKind` | Kind enum (H/L at emission; relabelled by MS-7A post-pass) |
| `Direction` (UP/DOWN) | Internal direction state |
| `CandleRelationship` | Internal candle classification enum |

**No dependency on `minor_structure_v1` engine code.** V2 must be an independent unit. All shared types above come from the shared contract layer, not from V1 internals.

---

## Notes

- This engine does not exist as runtime code. This record is a design document only.
- V2 is expected to produce **fewer pivots** than V1 in sequences containing inside bars, because the close-comparison reversal gate is removed entirely.
- A cluster of 4+ inside bars may produce a single pivot at the true cluster extreme. This pivot is placed at the candle holding the extreme price within the cluster, not at the breakout candle.
- V2 does not affect main structure computation. `main_structure_v1` will continue to consume `minor_structure_v1` output. A separate research step will be required to evaluate V2 minor output as input to a main structure engine.
- V1 must not be modified. V2 must not import V1 engine code.
- The close-comparison gate (`close < prev.close`, `close > prev.close`) is removed entirely in V2. There is no partial inside-bar reversal logic.

---

## Change History

| Date | Commit | Change |
|---|---|---|
| 2026-06-16 | — | Design record created — RESEARCH-ENGINE-LOG-3 |

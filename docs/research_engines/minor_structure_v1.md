# Engine Record: Classic Minor Structure

---

| Field | Value |
|---|---|
| **Human-Friendly Name** | Classic Minor Structure |
| **Technical ID** | `minor_structure_v1` |
| **Engine Type** | Minor Structure |
| **Lifecycle Status** | **Production** |
| **Created Date** | 2026-06-13 |
| **Frozen Date** | 2026-06-14 |
| **Retired Date** | — |
| **Rulebook Status** | **Frozen** |
| **Validation Status** | Validated — 91 unit tests pass at frozen commit |
| **Supersedes** | — (first production version) |
| **Superseded By** | — (current production) |

---

## Purpose

Baseline production minor structure engine.

Produces raw swing structure (turning points and directional legs) from OHLCV candle data, candle by candle. Serves as the primary input to the main structure engine and as the benchmark for all future experimental minor structure variants.

---

## Implementation Reference

| Item | Reference |
|---|---|
| Source module | `backend/tools/market_structure.py` |
| Engine class | `MarketStructureEngine` |
| Primary method | `_compute_minor_structure()` |
| Refinement method | `_refine_minor_pivots()` |
| Frozen commit | `de8c4e8` — MARKET-STRUCTURE-CHECKPOINT-1 (2026-06-14) |
| First commit | `28cec617` — MARKET-STRUCTURE-1A (2026-06-13) |
| Rulebook | `docs/MARKET_STRUCTURE_RULEBOOK.md` sections 2–3 |
| Test file | `tests/unit/test_market_structure.py` |
| Test count at freeze | 91 tests (all pass) |

---

## Key Characteristics

**Candle classification**

Every bar after the first is classified into exactly one of four mutually exclusive relationships before any action is taken:

| Class | Condition |
|---|---|
| Inside Bar | `curr.high ≤ prev.high` AND `curr.low ≥ prev.low` |
| Outside Bar | `curr.high > prev.high` AND `curr.low < prev.low` |
| Higher High | `curr.high > prev.high` (not an outside bar) |
| Lower Low | `curr.low < prev.low` (not an outside bar) |

Priority: inside bar and outside bar are checked first. A pure Higher High has `curr.low ≥ prev.low`. A pure Lower Low has `curr.high ≤ prev.high`.

**Direction machine**

Startup phase: engine waits for the first Higher High (→ UP) or Lower Low (→ DOWN). Inside bars, outside bars, and ambiguous bars during startup produce no output.

UP direction: Higher High continues; Lower Low reverses to DOWN; inside bar uses close comparison (close < prev.close → reverse); outside bar continues.

DOWN direction: Lower Low continues; Higher High reverses to UP; inside bar uses close comparison (close > prev.close → reverse); outside bar continues.

**Tracker-based pivot placement (MS-4B)**

The engine continuously tracks:
- `last_high_candle` — the candle holding the highest high seen during the current UP leg
- `last_low_candle` — the candle holding the lowest low seen during the current DOWN leg

When a reversal fires, the emitted pivot is placed at the tracker candle, not the reversal candle. This ensures pivots are anchored to the true swing extreme, not to the candle that triggered the reversal signal.

**Minor container pivot refinement (MS-4F)**

A post-pass scans for cases where the within-leg tracker missed a more extreme candle. This occurs primarily when an outside bar during a leg contains a lower low (UP leg) or higher high (DOWN leg) that the forward scan never recorded as the leg's true extreme. The refinement corrects the pivot placement without altering point kind, count, or any other attribute.

Refinement triggers:
- Minor HH context (`H₁ → L₁ → H₂`, `H₂ > H₁`): scans between H₁ and H₂ for the lowest low; corrects L₁ if a deeper low exists in the container
- Minor LL context (`L₁ → H₁ → L₂`, `L₂ < L₁`): scans between L₁ and L₂ for the highest high; corrects H₁ if a higher high exists in the container

**Determinism**

Fully deterministic. No randomness. No retained state between `compute_structure()` calls. Output is reproducible from identical input.

**Volume**

Volume is stored in OHLCVCandle and included in the input contract. Volume is not used in any minor structure computation in this version.

---

## Input Contract

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

Minimum viable input: 2 candles (first comparison fires on bar index 1).

---

## Output Contract

This engine produces the minor-structure portion of the combined `StructureResult`. The full result is returned by `MarketStructureEngine.compute_structure()`.

```
Output (minor portion):
  minor_points:  list[StructurePoint]
  minor_legs:    list[StructureLeg]
  debug_events:  list[StructureDebugEvent]

StructurePoint:
  id:          str          UUID
  level:       StructureLevel   MINOR
  kind:        PointKind    H | L (raw); relabelled by _label_structure_points() to HH | HL | LH | LL
  timestamp:   str          ISO 8601 UTC (from tracker candle)
  bar_index:   int
  price:       float
  source:      str          "price"
  confirmed:   bool
  metadata:    dict

StructureLeg:
  id:          str          UUID
  level:       StructureLevel   MINOR
  from_point_id: str
  to_point_id:   str
  direction:   Direction    UP | DOWN
  start_bar_index: int
  end_bar_index:   int
  start_price:  float
  end_price:    float

StructureDebugEvent:
  bar_index:           int
  timestamp:           str
  candle_relationship: str
  previous_direction:  Direction | None
  new_direction:       Direction | None
  action:              str
  reason:              str
  affected_level:      str
  candidate_high:      float | None
  candidate_low:       float | None
  confirmed_point_id:  str | None
```

---

## Dependencies

| Dependency | Role |
|---|---|
| `OHLCVCandle` | Input data schema |
| `StructurePoint` | Output point schema (shared with main structure) |
| `StructureLeg` | Output leg schema (shared with main structure) |
| `StructureDebugEvent` | Debug output schema |
| `StructureLevel.MINOR` | Level tag applied to all output points and legs |
| `PointKind` | Kind enum (H/L at emission; relabelled post-pass) |
| `Direction` (UP/DOWN) | Internal direction state |
| `CandleRelationship` | Internal candle classification enum |

---

## Test Coverage at Freeze

| Test Class | Coverage Area |
|---|---|
| `TestMinorStructureBasics` | Core direction sweep and reversal mechanics |
| `TestOutsideBarDebugReason` | Outside bar handling and debug output |
| `TestEdgeCases` | Startup phase, minimal candle sequences |
| `TestDebugMetadata` | Debug event content correctness |
| `TestIntegration` | End-to-end combined minor + main run |
| `TestPivotSelection` | MS-4B tracker-based pivot placement |
| `TestMinorContainerPivotRefinement` | MS-4F refinement (minor HH and minor LL contexts) |
| `TestMinorStructureLabelStateMachine` | MS-7A label state machine |
| `TestMS7AComparativeLabeling` | MS-7A comparative labelling rules |

---

## Notes

- The inside-bar reversal gate is directional: `close < prev.close` triggers DOWN reversal from UP; `close > prev.close` triggers UP reversal from DOWN. This distinguishes a bearish inside bar from a neutral consolidation bar.
- Outside bars unconditionally continue. They cannot trigger a reversal in this version.
- The refinement pass (MS-4F) mutates point `bar_index`, `timestamp`, and `price` in place but never alters `kind`, `level`, or `id`.
- This engine computes single-timeframe structure only. Multi-timeframe relationships are outside scope.
- The Rulebook (`docs/MARKET_STRUCTURE_RULEBOOK.md`) is the authoritative human-readable specification for this engine. The source code is the authoritative implementation. In case of conflict, the source code governs; discrepancies should be documented as Rulebook contradictions (see Rulebook Appendix).

---

## Change History

| Date | Commit | Change |
|---|---|---|
| 2026-06-13 | `28cec617` | Initial production implementation — MARKET-STRUCTURE-1A |
| 2026-06-14 | `de8c4e8` | Frozen as production baseline — MARKET-STRUCTURE-CHECKPOINT-1 |

No changes permitted after 2026-06-14. Future modifications must create `minor_structure_v2` as an independent Experimental engine.

# Engine Record: Classic Main Structure

---

| Field | Value |
|---|---|
| **Human-Friendly Name** | Classic Main Structure |
| **Technical ID** | `main_structure_v1` |
| **Engine Type** | Main Structure |
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

Baseline production main structure engine.

Derives higher-level market structure exclusively from minor structure output — never from raw candles. Produces the labelled HH/HL/LH/LL sequence that represents confirmed trend direction and key structural thresholds. Serves as the benchmark for all future experimental main structure variants.

---

## Implementation Reference

| Item | Reference |
|---|---|
| Source module | `backend/tools/market_structure.py` |
| Engine class | `MarketStructureEngine` |
| Primary method | `_compute_main_structure()` |
| Label pass | `_label_structure_points()` (applies to both minor and main) |
| Frozen commit | `de8c4e8` — MARKET-STRUCTURE-CHECKPOINT-1 (2026-06-14) |
| First commit | `28cec617` — MARKET-STRUCTURE-1A (2026-06-13) |
| Rulebook | `docs/MARKET_STRUCTURE_RULEBOOK.md` sections 4–6 |
| Test file | `tests/unit/test_market_structure.py` |
| Test count at freeze | 91 tests (all pass) |

---

## Key Characteristics

**Derived-only: no raw candle access**

The main structure engine consumes only `minor_points` (the output of minor structure). It never iterates over the raw `candles` list. All `bar_index` and `price` values in main output originate from minor structure points.

**Three-state machine**

| State | Meaning |
|---|---|
| ESTABLISHING | Bootstrap phase: waiting for first confirmed directional sequence |
| BULLISH | Confirmed uptrend — engine producing HH + HL sequences |
| BEARISH | Confirmed downtrend — engine producing LL + LH sequences |

**Bootstrap phase**

The first minor point encountered becomes the opening reference anchor (emitted as plain H or plain L). The engine then waits for the first point of the opposite type. Once both a high-type and low-type reference exist, confirmation thresholds (`main_high`, `main_low`) are established and the engine enters the confirmation phase (still in ESTABLISHING state).

Bootstrap H and L are never labelled HH or LL — they are permanent plain pivots regardless of their relative prices.

**Confirmation thresholds (MS-7C)**

| Trigger | Condition | State restriction | Action |
|---|---|---|---|
| HH | minor H price ≥ `main_high` | state ≠ BEARISH | Emit HL candidate + HH; advance boundaries; → BULLISH |
| LL | minor L price ≤ `main_low` | state ≠ BULLISH | Emit LH candidate + LL; advance boundaries; → BEARISH |

Equal-value semantics: a minor H exactly at `main_high` qualifies as a HH. A minor L exactly at `main_low` qualifies as a LL.

**HL and LH candidate selection**

When a HH is confirmed, the engine scans all minor L-type points strictly between the most recently confirmed high-type point's bar index and the new HH's bar index. The candidate with the lowest price is selected as HL (earliest bar wins on tie). If no candidate exists, no HL is emitted.

When a LL is confirmed, it scans for the highest minor H-type point in the equivalent range. Selected as LH.

**Reversal rules**

| State | Trigger | Action |
|---|---|---|
| BULLISH | minor L price **strictly below** `main_low` | Emit plain L (not LL); → ESTABLISHING; advance `main_low` |
| BEARISH | minor H price **≥** `main_high` | Emit plain H (not HH); → ESTABLISHING; advance `main_high` |

Asymmetry: BULLISH reversal requires strict `<`; BEARISH reversal requires `≥`. This is intentional (MS-7C) and covered explicitly by tests.

**Reversal protection**

Points emitted via the reversal branches are permanently marked. The HL/LH candidate scan routines skip marked reversal points, even if a subsequent confirmation would otherwise select them as candidates.

**Boundary advancement (MS-6B)**

After each confirmation or reversal, the active thresholds advance:

| Event | `main_high` after | `main_low` after |
|---|---|---|
| HH confirmed | Updated to HH price | Updated to selected HL price (if any) |
| LL confirmed | Updated to selected LH price (if any) | Updated to LL price |
| BULLISH reversal | Unchanged (retains prior HH) | Updated to reversal L price |
| BEARISH reversal | Updated to reversal H price | Unchanged (retains prior LL) |

**MS-7A minor label pass**

After main structure is computed, a separate pass labels minor points comparatively (HH/HL/LH/LL). This pass runs after `_compute_main_structure()`. The two label sets are independent — minor labelling cannot affect main point kinds.

---

## Input Contract

```
Input: list[StructurePoint]   (from minor_structure_v1 output)

StructurePoint (at time of consumption):
  id:          str
  level:       StructureLevel   MINOR
  kind:        PointKind        H | L  (raw, before label pass)
  timestamp:   str              ISO 8601 UTC
  bar_index:   int
  price:       float
  source:      str              "price"
  confirmed:   bool
  metadata:    dict
```

Critical ordering dependency: main structure consumes minor points **before** the MS-7A label pass runs. At consumption time, all minor points are plain H or L — never HH, HL, LH, or LL. If this ordering were reversed, the HL/LH candidate queries (which filter on `kind == PointKind.L` and `kind == PointKind.H`) would fail silently. This dependency is documented in Rulebook Appendix item 3.

---

## Output Contract

```
Output (main portion):
  main_points:  list[StructurePoint]
  main_legs:    list[StructureLeg]

StructurePoint:
  id:          str          UUID
  level:       StructureLevel   MAIN
  kind:        PointKind    H | L | HH | HL | LH | LL
  timestamp:   str          ISO 8601 UTC (from source minor point)
  bar_index:   int          (from source minor point)
  price:       float        (from source minor point)
  source:      str          "minor"
  confirmed:   bool
  metadata:    dict

StructureLeg:
  id:          str
  level:       StructureLevel   MAIN
  from_point_id: str
  to_point_id:   str
  direction:   Direction    UP | DOWN
  start_bar_index: int
  end_bar_index:   int
  start_price:  float
  end_price:    float
```

---

## Dependencies

| Dependency | Role |
|---|---|
| `minor_structure_v1` | The sole input source; main structure reads only minor points |
| `StructurePoint` | Input and output point schema |
| `StructureLeg` | Output leg schema |
| `StructureLevel.MAIN` | Level tag applied to all output points and legs |
| `PointKind` | Kind enum for labelling output points |
| `Direction` | Internal direction for leg construction |

---

## Test Coverage at Freeze

| Test Class | Coverage Area |
|---|---|
| `TestMainStructureBasics` | Core confirmation and reversal mechanics |
| `TestMainStructureBootstrap` | Bootstrap plain H/L phase |
| `TestIntegration` | End-to-end combined minor + main run |
| `TestContainerPivotRefinement` | Main container pivot refinement contexts |
| `TestMainStructureMinorDerived` | Derivation from minor points (no raw candle access) |
| `TestMainStructureBoundaryAdvancement` | MS-6B threshold advancement |
| `TestMainStructureStateMachine` | ESTABLISHING → BULLISH → BEARISH transitions |
| `TestMS7CMainStructureComparativeSelection` | MS-7C equal-value semantics and reversal protection |

---

## Notes

- All main structure bar indices and timestamps originate from minor structure points; they are never re-derived from raw candles.
- The plain L and plain H emitted during reversals are permanently protected from being relabelled as HL or LH by subsequent confirmation scans. This prevents a retroactive misclassification of what was a structural break.
- The BULLISH reversal asymmetry (strict `<` vs BEARISH `≥`) is non-obvious. A minor L exactly at `main_low` in BULLISH state is not a reversal; it simply passes through without being emitted. A minor H exactly at `main_high` in BEARISH state is a reversal. This is by design (MS-7C).
- ESTABLISHING state after a reversal retains one boundary from the prior trend (see Section 5 of the Rulebook). This retained boundary becomes the confirmation threshold for the next directional break, implementing "structure continuity" after a trend break.
- This engine produces no trading signals, no market bias assertions, and no BoS/CHoCH events. Those are the responsibility of separate downstream modules.

---

## Change History

| Date | Commit | Change |
|---|---|---|
| 2026-06-13 | `28cec617` | Initial production implementation — MARKET-STRUCTURE-1A |
| 2026-06-14 | `de8c4e8` | Frozen as production baseline — MARKET-STRUCTURE-CHECKPOINT-1 |

No changes permitted after 2026-06-14. Future modifications must create `main_structure_v2` as an independent Experimental engine.

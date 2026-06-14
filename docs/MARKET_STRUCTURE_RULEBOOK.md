# Market Structure Rulebook

_Audience: traders and analysts. No code knowledge assumed._  
_Source of truth: `backend/tools/market_structure.py` as of 2026-06-14._

---

## 1 — Overview

The Market Structure Engine analyses raw OHLCV candles and produces two independent layers of structure:

| Layer | What it is |
|---|---|
| **Minor structure** | Raw turning points — every significant swing high and swing low visible on the price chart |
| **Main structure** | Higher-level structure built exclusively from minor pivots — "structure within structure" |

Each layer produces a set of **structure points** (labelled pivots) and **structure legs** (directional line segments between consecutive points).

The engine is a deterministic visual-verification tool. It has no memory of previous runs, no concept of market bias, and generates no trading signals.

---

## 2 — Minor Structure Detection

Minor structure is built candle by candle. The engine compares each candle to the previous one and classifies the relationship into one of four types.

### 2.1 — Candle Relationship Classification

Every bar after the first is classified before any action is taken:

| Relationship | Condition |
|---|---|
| Higher High | `current.high > prev.high` (regardless of lows) |
| Lower Low | `current.low < prev.low` (regardless of highs) |
| Inside Bar | `current.high ≤ prev.high` AND `current.low ≥ prev.low` |
| Outside Bar | `current.high > prev.high` AND `current.low < prev.low` |

Classification priority: Inside Bar and Outside Bar are checked first. If neither applies, Higher High or Lower Low is checked. If none apply (equal highs and lows), the bar is treated as ambiguous (startup only).

### 2.2 — Startup Phase (No Direction Established)

The engine waits for the first directional signal:

- **Higher High** → establishes UP direction; engine begins tracking
- **Lower Low** → establishes DOWN direction; engine begins tracking
- **Inside Bar, Outside Bar, or ambiguous** → engine waits; no structure is emitted

### 2.3 — UP Direction Rules

| Candle Type | Action |
|---|---|
| Higher High | Continue UP; update the tracked high candle |
| Lower Low | **Reverse to DOWN**; emit an H point at the true swing high; begin DOWN tracking |
| Inside Bar, close ≥ prev close | Continue UP |
| Inside Bar, close < prev close | **Reverse to DOWN**; emit H point; begin DOWN tracking |
| Outside Bar | Continue UP |

### 2.4 — DOWN Direction Rules

| Candle Type | Action |
|---|---|
| Lower Low | Continue DOWN; update the tracked low candle |
| Higher High | **Reverse to UP**; emit an L point at the true swing low; begin UP tracking |
| Inside Bar, close ≤ prev close | Continue DOWN |
| Inside Bar, close > prev close | **Reverse to UP**; emit L point; begin UP tracking |
| Outside Bar | Continue DOWN |

### 2.5 — Pivot Placement (MS-4B)

When a reversal fires, the emitted pivot is placed at the candle that established the **true swing extreme** of the completed leg — not at the reversal candle itself.

During an UP leg, the engine continuously tracks the candle holding the highest high seen since the leg began (`last_high_candle`). When a reversal to DOWN fires, the H point is placed at `last_high_candle`.

During a DOWN leg, the engine tracks the candle holding the lowest low (`last_low_candle`). When a reversal to UP fires, the L point is placed at `last_low_candle`.

**Consequence**: Inside-bar continuations cannot shift the pivot. If bar 2 is the true high and bars 3–5 are inside-bar continuations before bar 6 reverses, the H pivot is at bar 2.

---

## 3 — Minor Structure Refinement (MS-4F)

After the raw pivot list is built, a refinement pass scans for cases where the opposite sub-leg contains a more extreme candle than the one the engine tracked.

### 3.1 — When Refinement Fires

**Minor HH context** — a sequence `H₁ → L₁ → H₂` where `H₂.price > H₁.price`:

The container is every candle strictly between `H₁.bar_index` and `H₂.bar_index`. The engine scans for the candle with the **lowest low** in that container. If that candle's low is strictly less than `L₁.price`, `L₁` is moved to that candle (bar index, timestamp, and price are all updated).

**Minor LL context** — a sequence `L₁ → H₁ → L₂` where `L₂.price < L₁.price`:

The container is every candle strictly between `L₁.bar_index` and `L₂.bar_index`. The engine scans for the candle with the **highest high** in that container. If that candle's high is strictly greater than `H₁.price`, `H₁` is moved to that candle.

### 3.2 — Why This Is Needed

The within-leg tracker (MS-4B) only follows price in its own direction. An outside bar during an UP leg has a lower low than the surrounding bars, but the DOWN-direction logic never runs during an UP leg, so that deeper low is never recorded as the swing pivot. The refinement pass catches these missed extremes.

### 3.3 — Tie-Breaking

When two candles share the same extreme price, the **earliest bar index** wins.

### 3.4 — What Refinement Does NOT Change

- Point kind (H or L) is not altered
- Points that do not satisfy the HH or LL context condition are left untouched
- If the container minimum equals `L₁.price` (no improvement), `L₁` stays in place

---

## 4 — Main Structure Construction

Main structure is derived **exclusively** from minor structure points. No raw candles are accessed. Every main point's bar index corresponds to a minor point.

### 4.1 — The Three States

The main engine runs a three-state machine:

| State | Meaning |
|---|---|
| **ESTABLISHING** | Waiting for the first confirmed sequence direction |
| **BULLISH** | Confirmed uptrend: producing HH + HL sequences |
| **BEARISH** | Confirmed downtrend: producing LL + LH sequences |

### 4.2 — Bootstrap Phase

The first minor point encountered becomes the reference anchor:

- If it is an H-type point → stored as plain **H**; `main_high` is set
- If it is an L-type point → stored as plain **L**; `main_low` is set

The engine then waits for the first point of the **opposite type** (skipping same-type points):

- First L after an opening H → stored as plain **L**; `main_low` is set
- First H after an opening L → stored as plain **H**; `main_high` is set

At this point both `main_high` and `main_low` are defined and the engine enters the confirmation phase (state remains ESTABLISHING).

**Critical rule**: The bootstrap plain H and L are never labelled HH or LL regardless of their relative prices.

### 4.3 — Active Thresholds

After bootstrap, two price levels act as confirmation and reversal thresholds:

| Threshold | Level | Variable |
|---|---|---|
| Ceiling | `main_high` | Set to the latest HH or LH price after each confirmation |
| Floor | `main_low` | Set to the latest LL or HL price after each confirmation |

### 4.4 — Confirmation Rules (MS-7C Thresholds)

| Trigger | Condition | Action |
|---|---|---|
| HH confirmation | minor H price **≥ main_high** AND state ≠ BEARISH | Emit HL + HH; advance boundaries; state → BULLISH |
| LL confirmation | minor L price **≤ main_low** AND state ≠ BULLISH | Emit LH + LL; advance boundaries; state → BEARISH |

**Equal-value semantics**: A price exactly equal to `main_high` qualifies as a HH. A price exactly equal to `main_low` qualifies as a LL. This is the MS-7C rule change from prior strict-inequality behaviour.

### 4.5 — HL and LH Candidate Selection

When a HH is confirmed, the engine must also place an HL (the pullback low before the new high). It scans all minor points of kind **L** (plain L only) strictly between the bar index of the most recent confirmed high-type point and the bar index of the new HH. Among those candidates it selects the one with the **lowest price** (earliest bar wins on tie). If no candidate exists, no HL is emitted.

When a LL is confirmed, the engine scans for the **highest H** strictly between the most recent confirmed low-type point and the new LL. The candidate with the highest price is selected as LH.

### 4.6 — Reversal Rules

| State | Trigger | Action |
|---|---|---|
| BULLISH | minor L price **strictly below** `main_low` | Emit plain **L** (not LL); state → ESTABLISHING; `main_low` advances to this L's price; `main_high` stays at prior HH |
| BEARISH | minor H price **≥ main_high** | Emit plain **H** (not HH); state → ESTABLISHING; `main_high` advances to this H's price; `main_low` stays at prior LL |

**Reversal protection**: Points emitted via the reversal branches are permanently marked. The HL/LH candidate selection routines will never retroactively relabel a reversal L to HL or a reversal H to LH, even if a subsequent equal-value confirmation would otherwise find it as a candidate.

**Equal-value BULLISH reversal**: A minor L exactly at `main_low` in BULLISH state is NOT a reversal (strict less-than required). It is simply not emitted.

**Equal-value BEARISH reversal**: A minor H exactly at `main_high` in BEARISH state IS a reversal (≥ threshold).

---

## 5 — Boundary Advancement (MS-6B)

After each confirmation event, the active thresholds advance so that subsequent tests are relative to the new structure:

| Event | `main_high` after | `main_low` after |
|---|---|---|
| HH confirmed | Updated to HH price | Updated to selected HL price (if any) |
| LL confirmed | Updated to selected LH price (if any) | Updated to LL price |
| BULLISH reversal (plain L emitted) | Unchanged (stays at prior HH) | Updated to reversal L price |
| BEARISH reversal (plain H emitted) | Updated to reversal H price | Unchanged (stays at prior LL) |

After a reversal the engine enters ESTABLISHING. The retained boundary from the prior trend acts as the confirmation threshold for the next directional break.

---

## 6 — Structure Labels (MS-7A / MS-7C)

### 6.1 — Minor Structure Labels (MS-7A)

After the full pipeline runs, minor points receive comparative labels. Each high-type pivot is compared only to the most recent high-type pivot; each low-type pivot only to the most recent low-type pivot. This pass mutates pivot kinds in place but never changes their price, bar index, or timestamp.

**Bootstrap**: The first high-type point encountered → **H**. The first low-type point encountered → **L**.

**High-type labelling rules** (in order of evaluation):

| Condition | Label |
|---|---|
| `current.price ≥ prev_high` AND previous high was **LH** | **H** (bullish reversal: broke above the prior lower high) |
| `current.price ≥ prev_high` (otherwise) | **HH** (higher high, including equal) |
| `current.price < prev_high` | **LH** (lower high) |

**Low-type labelling rules** (in order of evaluation):

| Condition | Label |
|---|---|
| `current.price > prev_low` | **HL** (higher low) |
| `current.price < prev_low` AND previous low was **HL** | **L** (bearish reversal: broke below the prior higher low) |
| `current.price ≤ prev_low` (otherwise) | **LL** (lower low, including equal) |

**Equal-value rules**: An equal high → HH. An equal low → LL. Neither breaks a trend.

**Reversal semantics**: A bearish reversal (new low breaks below prior HL) emits a plain **L** and resets the low comparison baseline. The H that preceded the HL is not relabelled. A bullish reversal (new high breaks above prior LH) emits a plain **H** and resets the high comparison baseline.

### 6.2 — Main Structure Labels (MS-7C)

Main structure points are labelled during construction (not by a post-pass). The same reversal-protection rule applies: a reversal plain L is never upgraded to HL, and a reversal plain H is never upgraded to LH.

Main structure labelling mirrors the MS-7A semantics but the comparison baseline is the active threshold pair (`main_high` / `main_low`) rather than the most recent same-kind point.

### 6.3 — Independence of the Two Label Sets

The minor and main label passes create separate `StructurePoint` objects. After the minor label pass runs, the main point kinds are unchanged. Mutations to minor point kinds cannot affect main point kinds.

---

## 7 — What the Engine Does NOT Do

The following are explicitly outside the engine's scope:

- **Trading signals**: No buy or sell signals of any kind
- **Market bias**: No concept of bullish or bearish market state from the engine's perspective
- **BoS and CHoCH detection**: Break of Structure and Change of Character events are detected by separate modules (`bos_detection.py`, `choch_detection.py`) that consume minor structure points as input; the engine itself emits no such events
- **Multi-timeframe analysis**: All computation is single-timeframe
- **Volume analysis**: Volume is stored in candles but is not used in any structure computation
- **Forward projection**: No predictions or probability estimates
- **Trend direction output**: The engine produces labelled pivot geometry; a trader reads the labels (HH/HL = uptrend, LH/LL = downtrend); the engine never asserts a direction itself
- **Raw-candle access in main structure**: Main structure construction reads only `minor_points`; it never loops over `candles` directly

---

## 8 — Summary: Decision Table Quick Reference

### Minor Structure Reversal Triggers

| Direction | Trigger | Emits |
|---|---|---|
| UP → DOWN | Lower Low OR inside bar with close < prev close | **H** at `last_high_candle` |
| DOWN → UP | Higher High OR inside bar with close > prev close | **L** at `last_low_candle` |
| Either | Outside bar | Continuation only — no pivot emitted |

### Main Structure Confirmation Thresholds

| Confirmation | Required price | State before | Emits |
|---|---|---|---|
| HH | ≥ `main_high` | ESTABLISHING or BULLISH | HL (if candidate found) + **HH** |
| LL | ≤ `main_low` | ESTABLISHING or BEARISH | LH (if candidate found) + **LL** |

### Main Structure Reversal Thresholds

| Reversal | Required price | State before | Emits |
|---|---|---|---|
| BULLISH reversal | **strictly <** `main_low` | BULLISH | Plain **L** |
| BEARISH reversal | ≥ `main_high` | BEARISH | Plain **H** |

---

## Appendix — Contradictions and Mismatches Found

The following discrepancies were identified between implementation and documentation during this audit. No code was changed.

**1 — MS numbering inconsistency in test docstrings**

`TestContainerPivotRefinement` (tests 27–31) carries the header comment `MS-4C/MS-4D`. The neighbouring `TestMinorContainerPivotRefinement` (tests 32–36) uses `MS-4E/MS-4F`. The implementation method `_refine_minor_pivots` is called "Phase 1.5" inline but has no MS number in its own docstring. The spec names used in tests do not map to any external written specification visible in the repository. No functional impact; the behaviour covered by all six tests is consistent with the implementation.

**2 — ESTABLISHING state not mentioned in `compute_structure` orchestration comments**

The top-level `compute_structure` method describes the two phases (minor → main) but does not mention the three-state machine or the ESTABLISHING → BULLISH/BEARISH transition. A reader of only the orchestration comments would not know that main structure has a bootstrap phase. The `_compute_main_structure` docstring covers it correctly.

**3 — Bootstrap H-type pivot query uses broad kind set but minor points are always plain H/L at that point**

`_hl_candidate` and `_lh_candidate` search for `mp.kind == PointKind.L` and `mp.kind == PointKind.H` respectively. At the time these run, minor points are still raw H/L (the comparative label pass runs after main structure). This is correct behaviour. However, if the ordering of phases were ever changed (e.g., label pass before main), the candidate queries would fail silently because they filter for plain H/L only. This is a latent ordering dependency, not a current bug.

**4 — Equal-value BULLISH reversal is asymmetric with BEARISH reversal (by design)**

A minor L exactly at `main_low` in BULLISH state is NOT a reversal (requires strict less-than). A minor H exactly at `main_high` in BEARISH state IS a reversal (≥). This asymmetry is intentional (MS-7C), documented in the `_compute_main_structure` docstring, and covered by tests 73–77. It is noted here because it is non-obvious and could surprise someone reading only the high-level description.

# Engine Record: Container Breakout Minor Structure

---

| Field | Value |
|---|---|
| **Human-Friendly Name** | Container Breakout Minor Structure |
| **Technical ID** | `minor_structure_v3` |
| **Engine Type** | Minor Structure |
| **Lifecycle Status** | **Experimental** |
| **Created Date** | 2026-06-16 |
| **Frozen Date** | — |
| **Retired Date** | — |
| **Rulebook Status** | **Active** |
| **Validation Status** | Not validated |
| **Supersedes** | — |
| **Superseded By** | — |

---

## Purpose

Test whether defining structure exclusively through container breakouts — rather than candle-by-candle comparison — produces cleaner, more durable minor structure pivots.

Instead of comparing each candle to the immediately previous candle (as in V1/V2), V3 maintains an active `temp_resistance` / `temp_support` container. Structure is defined by breakouts from this container. Inside-container candles do not define structure. Outside-container candles reset the container without changing state. Pivots are emitted only on high/low state transitions, placed at the true price extreme of the completed leg.

---

## Implementation Status

**Runtime implementation available.**

Location: `backend/tools/market_structure_v3.py` (`MinorStructureV3Engine`)

---

## Container States

The engine tracks four candle classifications per iteration, relative to the active container `[temp_support, temp_resistance]`:

| Classification | Condition | Action |
|---|---|---|
| Inside container | `high <= R` AND `low >= S` | Continue state; no pivot; no container reset |
| Outside container | `high > R` AND `low < S` | Continue state; no pivot; reset container to current candle |
| Bullish breakout | `high > R` AND `low >= S` | State → high; reset container |
| Bearish breakout | `high <= R` AND `low < S` | State → low; reset container |

Equal boundary values are classified as **inside container** (not a breakout). Rules use strict `>` and `<` for breakout conditions.

---

## Rules

### Rule 1 — Startup

Initialize from the first candle:

```
temp_resistance = candles[0].high
temp_support    = candles[0].low
state           = None
```

Wait for the first valid breakout to establish state.

### Rule 2 — Inside Container

If `current.high <= temp_resistance AND current.low >= temp_support`:

- Continue previous state/direction.
- Do not create pivot.
- Do not reverse structure.
- Do not reset `temp_resistance` / `temp_support`.

### Rule 3 — Outside Container

If `current.high > temp_resistance AND current.low < temp_support`:

- Maintain previous state/direction.
- Do not create pivot.
- Do not reverse structure.
- Reset `temp_resistance = current.high`, `temp_support = current.low`.

### Rule 4 — Bullish Breakout

If `current.high > temp_resistance AND current.low >= temp_support`:

- If previous state was **low**: emit pivot L at `lowest_low_candle` (tracked extreme of the completed down leg). Transition to state **high**.
- If previous state was **high**: update `highest_high_candle` tracker if this candle makes a new high. State remains **high** (no pivot).
- If previous state was **None**: transition to state **high** (no pivot — first breakout establishes direction).
- Reset `temp_resistance = current.high`, `temp_support = current.low`.

### Rule 5 — Bearish Breakout

If `current.low < temp_support AND current.high <= temp_resistance`:

- If previous state was **high**: emit pivot H at `highest_high_candle` (tracked extreme of the completed up leg). Transition to state **low**.
- If previous state was **low**: update `lowest_low_candle` tracker if this candle makes a new low. State remains **low** (no pivot).
- If previous state was **None**: transition to state **low** (no pivot — first breakout establishes direction).
- Reset `temp_resistance = current.high`, `temp_support = current.low`.

### Rule 6 — True Extreme Placement

Pivots are not placed at the state-change candle. They are placed at the candle holding the true extreme of the completed leg:

- During **high** state: track `highest_high_candle` (candle with the highest `high` among all bullish breakout and outside-container candles in the leg).
- When state changes to **low**: emit H at `highest_high_candle`.
- During **low** state: track `lowest_low_candle` (candle with the lowest `low` among all bearish breakout and outside-container candles in the leg).
- When state changes to **high**: emit L at `lowest_low_candle`.

Tie-breaking: earlier bar_index wins for equal extreme prices.

### Rule 7 — Outside Container and Extreme Tracking

Outside-container candles do not change state but DO participate in extreme tracking:

- Outside container during **high** state: if `current.high > highest_high_candle.high`, update `highest_high_candle`.
- Outside container during **low** state: if `current.low < lowest_low_candle.low`, update `lowest_low_candle`.

---

## V1 vs V3 Comparison

| Behaviour | V1 (Classic Minor Structure) | V3 (Container Breakout) |
|---|---|---|
| Candle classification reference | Immediately previous candle | Active container [temp_support, temp_resistance] |
| Inside bar / inside container | Compared against prev; may reverse via close gate | Compared against active container; never reverses |
| Outside bar | Always continues direction | Continues direction; resets container |
| Pivot placement | At candle that triggers reversal (tracker-refined by MS-4F) | At true extreme candle of completed leg |
| State machine | UP / DOWN with inside-bar reversal gate | high / low with container breakout only |
| Direction establishment | First HH or LL vs prev candle | First bullish or bearish breakout vs container |

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

Debug event `candle_relationship` and `action` values used by V3:
`startup`, `inside_container`, `outside_container`, `bullish_breakout`, `bearish_breakout`

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
| `Direction` (UP/DOWN) | Debug event direction field |

**No dependency on `minor_structure_v1` or `minor_structure_v2` engine code.**

---

## Notes

- V3 will typically produce **fewer pivots** than V1 or V2 in ranging markets, because inside-container candles are completely ignored and never trigger reversals.
- V3 will typically produce **more durable pivots** because they require a true container breakout, not just a single candle comparison.
- V3 does not affect main structure computation. A separate research step will evaluate V3 minor output as input to a main structure engine.
- The `close` price is not used in any V3 computation. V3 uses only `high` and `low`.
- V1 and V2 must not be modified.

---

## Change History

| Date | Commit | Change |
|---|---|---|
| 2026-06-16 | — | Design record created and runtime implementation added |

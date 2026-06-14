# Frontend UX Architecture

**Status:** Approved architecture guidance — future direction only.
**Scope:** This document captures approved UX decisions for future frontend development. It does not describe the current implementation and requires no code changes.

---

## UX-1 — Analysis Layers vs Visualization Settings

Analysis Layers and Visualization Settings are distinct concepts and must be treated as separate concerns in the UI.

**Analysis Layers** answer: *"What analytical information is displayed?"*

Examples: Minor Structure, Main Structure, Market Bias, BoS, ChoCH.

**Visualization Settings** answer: *"How should that information be rendered?"*

Examples: colour, line weight, label visibility, opacity, z-order.

These two concerns must not be collapsed into a single flat control surface. A user choosing to display Market Bias is making an analytical decision. A user adjusting the colour of a bias zone is making a rendering decision. The UI must reflect this distinction.

---

## UX-2 — Market Structure is a Framework

Market Structure is not a single toggle. It is a framework composed of multiple independent analytical modules organized into four groups.

```
Market Structure
│
├── Structure
│   ├── Minor Structure
│   ├── Main Structure
│   └── Structure Labels
│
├── Transition
│   ├── Transition Detection
│   ├── Transition Range
│   └── Complete Reversal
│
├── Events
│   ├── BoS (Break of Structure)
│   ├── ChoCH (Change of Character)
│   └── Last Standing
│
└── Bias
    ├── Market Bias
    ├── Bias Labels
    └── Bias Zones
```

Each module is independently toggleable. The grouping reflects logical dependency and conceptual proximity, not rendering order.

---

## UX-3 — Structure Labels and Market Bias are Independent Systems

Structure Labels and Market Bias are separate analytical systems. They must not be coupled in implementation or in the UI.

**Structure Labels** describe pivot geometry:

| Label | Meaning |
|---|---|
| H | High (bootstrap) |
| L | Low (bootstrap) |
| HH | Higher High |
| HL | Higher Low |
| LH | Lower High |
| LL | Lower Low |

**Market Bias** describes market condition:

| State | Meaning |
|---|---|
| Bullish | Sustained upward structure |
| Bearish | Sustained downward structure |
| Transition | Structure shifting between states |
| Sideway | No directional dominance |

Market Bias must not be embedded into the Structure Label Engine. The label engine produces geometric labels from pivot comparisons. Market Bias is derived from a higher-order engine that interprets those labels — it is not an output of the labeling pass itself.

---

## UX-4 — Preferred Future UI Architecture

Avoid a single flat checkbox menu containing every analytical feature. Future UI should reflect the module hierarchy from UX-2.

**Preferred toolbar organization:**

```
Top Toolbar
├── Indicators     (oscillators, overlays)
├── Structure      (market structure modules)
├── Strategy       (signal layers, execution)
└── Settings       (display preferences only)
```

**Structure panel (when opened):**

```
Structure Panel
├── Structure      (Minor Structure, Main Structure, Structure Labels)
├── Transition     (Transition Detection, Transition Range, Complete Reversal)
├── Events         (BoS, ChoCH, Last Standing)
└── Bias           (Market Bias, Bias Labels, Bias Zones)
```

**Settings panel** contains display preferences only — not analytical toggles.

This organization scales as new modules are added without requiring UI restructuring.

---

## UX-5 — Current Implementation Unchanged

This document is guidance for future development. The current implementation is not affected.

No UI refactor is part of this task. Existing components, routes, and API contracts remain as-is until a dedicated UX implementation task is approved.

---

## Future UX Roadmap

**Current:**
- Market Structure Validation (Minor + Main structure, structure labels)

**Planned (not yet implemented):**
- Market Bias Engine
- BoS Engine
- ChoCH Engine
- Transition Range Engine
- Last Standing Engine

Each engine above corresponds to one or more modules in the UX-2 framework. Implementation order and scope will be determined per task.

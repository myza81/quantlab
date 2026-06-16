# Research Engine Versioning Governance

_Audience: implementation agents, architects, researchers. Platform-wide policy._  
_Scope: any analytical engine in QuantLab — market structure, indicators, signals, features, risk models, ML models, or any future research module._

---

## A — Why This Exists

QuantLab is a research-first platform. New analytical approaches are proposed continuously. A market structure engine may be revised. An indicator may be reimplemented under a new hypothesis. A signal generator may have an experimental branch running alongside the production one.

Without explicit governance:

- Production pipelines accidentally absorb unvalidated experimental logic
- Competing implementations develop implicit coupling (shared state, shared imports, shared contracts)
- An engine can never be safely retired because its internal API has leaked into every downstream consumer
- Validation evidence accumulates in scattered notes instead of a formal record
- A reversion to an older engine version becomes impossible because the older version was mutated rather than versioned

Research Engine Versioning solves this by treating every analytical engine as a versioned, lifecycle-governed artifact — not a file that gets edited in place.

**This policy applies to every research engine in the platform** — not only market structure. If a module produces analytical output consumed by other modules or users, it is a research engine and must follow these rules.

---

## B — Engine Lifecycle

Every research engine moves through six defined states. State transitions must be explicit. An engine may not skip states. An engine may be demoted backward in the lifecycle if evidence requirements are not met.

```
Experimental → Validated → Candidate → Production → Deprecated → Retired
```

### State Definitions

**Experimental**

The engine exists as a research artifact. It may be in active development. Its internal contracts are unstable. It is not connected to any production pipeline. It is not consumed by any downstream module unless that module is also Experimental. Tests are encouraged but not required for all cases.

**Validated**

The engine has passed quantitative correctness verification. All unit tests pass. Edge cases are documented and covered. The engine's output schema is frozen — it may not change without a version increment. The engine may now be connected to research pipelines for analytical review. It must not be connected to production pipelines.

**Candidate**

The engine has passed extended validation including comparison against production output (if a prior production version exists), visual verification, and research review. A promotion record exists in the engine's documentation. The engine is being evaluated for production use. It may be connected to staging environments.

**Production**

The engine is the authoritative version for its domain. All production pipelines must consume this version. The prior Production version transitions to Deprecated immediately. Internal implementation details remain private. Only the schema contract is public. Changes to a Production engine must produce a new version at Experimental state; the Production version itself is immutable.

**Deprecated**

The engine has been superseded by a newer Production version. It remains in the repository to support audit trails, historical reproducibility, and rollback capability. No new pipelines may consume a Deprecated engine. Existing consumers of the Deprecated version must be migrated to the Production version as a tracked task. A deprecation date and target retirement date must be recorded.

**Retired**

The engine has been removed from active use. Its code is archived (not deleted if referenced by historical backtest records). No imports, no pipeline references. If a historical backtest record requires a Retired engine to be reproducible, the archive path is documented in the engine's retirement record.

---

## B.1 — Human Name vs Technical ID

Every engine record has two identifying fields with distinct purposes.

**Technical ID** (`technical_id`)

The machine-authoritative reference. Used by code, APIs, configuration files, pipeline specs, and the YAML registry. Never changes once assigned. Format: `<domain>_v<n>` (e.g., `minor_structure_v1`). Any code, config, or log that references an engine must use the technical ID.

**Human Name** (`human_name`)

A mandatory short research label — treated like a git commit message. It names the core research idea or approach being tested, not the software component. It is the primary display identifier in the version log UI and in documentation tables.

**Rules for human names:**

- **Mandatory.** Every engine record must have one.
- **Short.** One to five words. No version numbers in the name itself — the version is encoded in the technical ID.
- **Descriptive.** Names the research hypothesis, not the implementation class.
- **Stable within a version.** Once a Production engine is frozen, its human name must not be changed.

**Good human names:**

| Human Name | What it communicates |
|---|---|
| Classic Minor Structure | Baseline candle-sweep approach — no ML, no lookahead |
| Trend-Filtered Minor Structure | Same sweep but conditional on trend state |
| Momentum-Gated Pivots | Pivot placement with momentum confirmation gate |

**Poor human names (avoid these):**

| Human Name | Problem |
|---|---|
| Minor Structure Engine V2 | Version number belongs in `technical_id`, not the name |
| MarketStructureV2 | Reads like a class name, not a research description |
| Updated Algorithm | Says nothing about what changed or why |
| New Approach | Generic; meaningless as a log entry |

**The distinction in one sentence:** `technical_id` answers "which version of code is running?" — `human_name` answers "what research idea does this version implement?"

---

## C — Engine Independence

Engine versions must be fully independent units. This is non-negotiable.

### Rules

**No cross-version imports.** A V2 engine must not import from V1. A V1 engine must not import from V2. They may share external utility libraries (e.g., a candle normalization helper) if those utilities are not themselves versioned research engines, but they must not share research logic.

**No inheritance across versions.** A new engine version must not subclass or extend a prior version. Code reuse is achieved by copying relevant logic into the new version and then independently evolving it. This preserves the immutability of the prior version.

**No shared mutable state.** Two engine versions must not share dictionaries, caches, registries, or any runtime state. Each version is a closed unit.

**No internal API leakage.** Only the schema contract (see Section D) is public. Helper methods, intermediate data structures, and internal logic are private to the engine version. Downstream modules must not call internal methods, even if Python's scoping does not prevent it.

**Separate namespaces.** Engine versions must be separated by filesystem path and module namespace. Example:

```
backend/tools/market_structure/          ← namespace root
    v1/
        engine.py
        schema.py
    v2/
        engine.py
        schema.py
    contract.py                          ← public schema contract (shared)
```

The exact directory structure is at the implementer's discretion when a versioning need arises; the principle (separate paths, separate imports, shared contract file) is mandatory.

---

## D — Contract-Based Architecture

Downstream modules must consume schema contracts, not concrete engine implementations.

### The Contract

Every engine domain has a single public contract file. The contract defines:

- The output schema: what fields are produced, their types, and their semantics
- Any input schema the engine expects
- The contract version (separate from the engine version)

Example contract excerpt (illustrative, not a code instruction):

```
MarketStructureOutput
  - minor_points: list of StructurePoint
  - main_points: list of StructurePoint
  - legs: list of StructureLeg
  - debug_events: list of StructureDebugEvent (optional)

StructurePoint
  - id: str
  - bar_index: int
  - timestamp: datetime
  - price: float
  - kind: PointKind (H, L, HH, HL, LH, LL)
  - level: StructureLevel (MINOR, MAIN)
```

A downstream module that renders structure on a chart imports only the contract types. It never imports `MarketStructureV1Engine` or `MarketStructureV2Engine` directly.

### Contract Versioning

Contract versions are independent of engine versions. A new engine version does not automatically require a contract version change. A contract version change is required when:

- A field is removed
- A field's type changes in a breaking way
- Field semantics change in a way that changes how downstream consumers must interpret the output

When a contract version changes, all downstream consumers must be updated before the new contract is released to production.

### The Role of the Contract in Promotion

An engine cannot be promoted to Candidate status unless its output fully satisfies the current production contract. If a new engine requires a contract change, the contract change must be proposed, reviewed, and approved separately before the engine's promotion path is evaluated.

---

## E — Pipeline Configuration Concept

A pipeline is any workflow that consumes an engine's output: a backtest, a forward test run, a research notebook, a chart computation, an API request handler.

### Engine Selection

Pipelines must not hardcode engine implementations. A pipeline declares which engine version it requires through configuration or dependency injection. The implementation resolves the correct engine version at runtime.

Illustrative intent (not a code instruction):

```
pipeline_config:
  market_structure_engine: "production"   ← resolves to current Production version
  # or:
  market_structure_engine: "v2"           ← explicitly pinned for research comparison
```

Production pipelines must always resolve to `"production"` — they must never be pinned to a specific version tag, because that would prevent the Production engine from being updated without editing every pipeline's configuration.

Research pipelines used for comparison studies may pin to a specific version to ensure reproducible comparison results.

### Pipeline–Engine Decoupling

A pipeline knows the contract. A pipeline does not know which version implements the contract. When the Production engine is updated (a new version is promoted), no pipeline configuration changes are required for production consumers.

---

## F — Promotion Rules

Promotion from one lifecycle state to the next requires explicit evidence. Promotions must be recorded.

### Experimental → Validated

Required evidence:
- All unit tests pass (100%)
- Edge cases that caused failures in prior engine versions are covered with explicit tests
- Output schema is frozen and documented
- A promotion note is written describing what the engine does differently from any prior version and why

### Validated → Candidate

Required evidence:
- If a Production version exists: a side-by-side comparison of Validated output vs Production output has been run on representative datasets, with discrepancies documented and explained
- Visual verification has been performed (where applicable — e.g., chart-rendered structure)
- All test count from Validated stage is preserved; no tests were removed
- The promotion note describes the comparison methodology and the outcome of the review

### Candidate → Production

Required evidence:
- System Architect sign-off or equivalent governance approval
- The prior Production version's deprecation record is prepared
- All production consumer documentation is updated to reference the new version
- A production promotion timestamp is recorded

### Any Demotion

An engine may be demoted one or more lifecycle states if:
- A test regression is discovered after promotion
- Output discrepancies are found against production ground truth
- The schema contract changes without following the contract versioning process

Demotions must be recorded with a reason. The demotion does not delete any prior promotion records.

---

## G — Retirement Rules

Retirement is the final state. Engines are retired to prevent stale code from being accidentally consumed.

### Conditions for Retirement

A Deprecated engine may be retired when:
- All consumers have migrated to the current Production version
- The deprecation period defined at time of deprecation has elapsed
- No outstanding historical backtest records require the engine for reproducibility without an alternative path

### Retirement Record

Before retiring an engine, a retirement record must be written. It must include:
- Engine version identifier
- Lifecycle dates (created, validated, production, deprecated, retired)
- Reason for retirement
- Archive path (if the code is moved rather than deleted)
- Any known historical records that referenced this engine

### Code Disposition

Retired engine code is not automatically deleted. If any production backtest or forward test record was created using the retired engine, the engine code must remain accessible in an archive path. Deleting code that is needed for audit trail reproduction is prohibited.

If no production records reference the engine (e.g., it was an Experimental engine that never reached production), the code may be deleted after the retirement record is written.

---

## H — Anti-Patterns

The following patterns are prohibited and must be rejected in code review.

**Anti-pattern 1 — In-place mutation of a production engine**

Editing a Production engine's logic directly. Production engines are immutable. If the logic must change, create a new version at Experimental state.

**Anti-pattern 2 — Cross-version import**

```python
# PROHIBITED
from backend.tools.market_structure.v1.engine import V1Helper
class V2Engine:
    def _compute(self):
        return V1Helper.shared_logic(...)
```

**Anti-pattern 3 — Inheritance across versions**

```python
# PROHIBITED
from backend.tools.market_structure.v1.engine import MarketStructureV1Engine
class MarketStructureV2Engine(MarketStructureV1Engine):
    ...
```

**Anti-pattern 4 — Direct engine import in downstream consumers**

```python
# PROHIBITED in a production consumer
from backend.tools.market_structure.v2.engine import MarketStructureV2Engine
result = MarketStructureV2Engine().compute(candles)

# REQUIRED
from backend.tools.market_structure.contract import MarketStructureContract
result: MarketStructureContract = engine_resolver.compute(candles)
```

**Anti-pattern 5 — Skipping lifecycle states**

Promoting directly from Experimental to Production because "we already know it works." Every intermediate state exists to generate evidence. Skipping it means the evidence does not exist.

**Anti-pattern 6 — Unbounded Deprecated engine lifespan**

A Deprecated engine with no migration plan and no retirement date is an orphan. Orphan engines accumulate, create confusion about which version is authoritative, and are eventually imported accidentally.

**Anti-pattern 7 — Shared mutable state between versions**

A module-level cache, registry, or singleton that both V1 and V2 write to. This creates hidden coupling even when the code files are separate.

**Anti-pattern 8 — Contract changes without version increment**

Changing the meaning of a field in the contract without incrementing the contract version. Downstream consumers will silently misinterpret the output.

**Anti-pattern 9 — Research engine logic inside a strategy module**

A strategy that reimplements a portion of a research engine's computation rather than consuming its output through the contract. Research engine logic must live in the engine, not in each consumer.

**Anti-pattern 10 — Experimental engine in a production pipeline**

Wiring an Experimental engine into any production API route, backtest runner, or forward test runner. Experimental engines are research artifacts, not production dependencies.

---

## Summary

| Principle | Rule |
|---|---|
| Lifecycle | Six states: Experimental → Validated → Candidate → Production → Deprecated → Retired |
| Promotion | Requires documented evidence at each step; no state skipping |
| Immutability | Production engines are immutable; changes create a new version |
| Independence | No cross-version imports, no inheritance, no shared state |
| Contracts | Downstream consumers import only contracts, never concrete engine classes |
| Retirement | Retired engines are archived if referenced by historical records; not silently deleted |
| Scope | Platform-wide — applies to every research engine, not only market structure |

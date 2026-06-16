# Research Engine Version Log — Frontend Architecture Design

_Status: Design document. No runtime implementation yet._  
_Audience: architects, implementation agents._  
_This document defines the architecture for making research engine metadata visible in the QuantLab frontend._

---

## Design Goals

1. Researchers and traders can see which engine version is active for each domain without reading source code
2. The history of engine versions — including experimental, deprecated, and retired ones — is visible and auditable
3. The frontend is a read-only viewer of backend-authoritative metadata; it contains no engine business logic
4. The architecture is simple enough to implement correctly without a database in the first phase
5. The metadata API contract is stable enough that the backend implementation can be swapped without touching frontend code

---

## 1. Metadata Source of Truth

### Recommendation: Static Backend Registry File (Phase 1)

At current platform maturity, a static YAML or JSON registry file loaded at application startup is the recommended first approach.

**Why static file first:**

- Zero database migration risk
- The file is version-controlled — every engine status change is a git commit with full history
- Can be loaded at startup and cached in memory; the read-only API becomes trivial
- No dependency on PostgreSQL being available for the metadata subsystem
- Fully testable without a database
- Can be replaced by a database table in Phase 2 without any change to the API contract or the frontend

**Recommended location:**

```
backend/config/research_engines.yaml
```

**Alternative: inline Python dict in a config module**

Also acceptable for Phase 1. Slightly less human-readable than YAML. No parsing library required. Choose YAML if non-engineer stakeholders need to read or audit the file directly.

**What NOT to do in Phase 1:**

- Do not create a runtime engine registry (a live Python registry that engines register into at import time). That is implementation infrastructure, not metadata. The metadata system and the runtime system are separate concerns.
- Do not store metadata in the frontend. The frontend must consume it from an API.
- Do not duplicate the metadata across multiple files. One authoritative source, exposed by one API.

---

## 2. Metadata Schema

Each engine version record contains the following fields. This is the schema for the backend registry and for the API response body.

```yaml
# Schema: one record per engine version
human_name:         string          # Short research label — treated like a git commit message.
                                    # Mandatory. Describes the core idea, not the component name.
                                    # Example: "Classic Minor Structure"
technical_id:       string          # Stable machine reference — used by code, APIs, and configs.
                                    # Never changes once assigned. Format: <domain>_v<n>
                                    # Example: "minor_structure_v1"
engine_type:        string          # "minor_structure" | "main_structure" | etc.
lifecycle_status:   string          # "experimental" | "validated" | "candidate" | "production" | "deprecated" | "retired"
created_date:       date            # ISO 8601 date
frozen_date:        date | null     # ISO 8601 date; null if not yet frozen
retired_date:       date | null     # ISO 8601 date; null if not yet retired
rulebook_status:    string          # "active" | "frozen" | "archived"
purpose:            string          # One-sentence description
key_characteristics: list[string]  # Bullet-point list of distinguishing properties
input_contract:     object          # { type: string, fields: list[string], notes: string }
output_contract:    object          # { type: string, fields: list[string], notes: string }
dependencies:       list[string]    # Other technical_ids or shared schema names this engine depends on
supersedes:         string | null   # technical_id of the version this replaces; null if first version
superseded_by:      string | null   # technical_id of the version that replaced this; null if still active
validation_status:  string          # "not_validated" | "validated" | "production_validated"
notes:              string          # Free-form human notes; prominent non-obvious behaviours
change_log:         list[object]    # [{ date, commit, description }]
```

**Concrete example (minor_structure_v1):**

```yaml
- human_name: "Classic Minor Structure"
  technical_id: "minor_structure_v1"
  engine_type: "minor_structure"
  lifecycle_status: "production"
  created_date: "2026-06-13"
  frozen_date: "2026-06-14"
  retired_date: null
  rulebook_status: "frozen"
  purpose: "Baseline production minor structure engine and benchmark for future experimental versions."
  key_characteristics:
    - "Candle-by-candle sweep with 4 candle relationship classes (HH, LL, IB, OB)"
    - "Inside bar reversal gate: uses close vs prev.close comparison"
    - "Outside bar always continues current direction — never reverses"
    - "Tracker-based pivot placement (MS-4B): last_high_candle / last_low_candle"
    - "Minor container pivot refinement pass (MS-4F)"
    - "Fully deterministic; no state between calls"
  input_contract:
    type: "list[OHLCVCandle]"
    fields: ["timestamp", "bar_index", "open", "high", "low", "close", "volume"]
    notes: "Volume is stored but not used in any computation."
  output_contract:
    type: "StructureResult (minor portion)"
    fields: ["minor_points", "minor_legs", "debug_events"]
    notes: "Points are plain H/L at emission; relabelled by the post-pass."
  dependencies: ["OHLCVCandle", "StructurePoint", "StructureLeg", "StructureDebugEvent"]
  supersedes: null
  superseded_by: null
  validation_status: "production_validated"
  notes: "Frozen at commit de8c4e8. No modifications permitted. Future changes create minor_structure_v2 as Experimental."
  change_log:
    - date: "2026-06-13"
      commit: "28cec617"
      description: "Initial production implementation — MARKET-STRUCTURE-1A"
    - date: "2026-06-14"
      commit: "de8c4e8"
      description: "Frozen as production baseline — MARKET-STRUCTURE-CHECKPOINT-1"
```

---

## 3. Read-Only Backend API Concept

The metadata API is read-only. No mutation endpoints are defined in this design. Engine metadata is managed through the backend registry file (Phase 1) or database (Phase 2), not through an API.

### Endpoints

**List all engine versions**

```
GET /api/research-engines

Response 200:
{
  "engines": [
    { ...engine record... },
    { ...engine record... }
  ]
}
```

Query parameters (future, not required for Phase 1):

- `?engine_type=minor_structure` — filter by type
- `?lifecycle_status=production` — filter by status
- `?domain=market_structure` — filter by domain group

**Get a single engine version by technical ID**

```
GET /api/research-engines/{technical_id}

Example: GET /api/research-engines/minor_structure_v1

Response 200:
{ ...engine record... }

Response 404:
{ "error": "Engine version not found", "technical_id": "minor_structure_v1" }
```

### Service Layer Design (future implementation)

```
API route (thin)
    ↓
EngineRegistryService
    ↓
EngineRegistryRepository
    ↓
Static YAML file (Phase 1)  →  PostgreSQL table (Phase 2)
```

The route knows nothing about where data is stored. The repository is swapped between phases. The API contract (URL, response shape) does not change between Phase 1 and Phase 2.

### What the API does NOT expose

- No mutation endpoints (POST, PUT, DELETE, PATCH)
- No engine runtime controls (start/stop, version selection)
- No internal implementation details beyond what is in the schema

---

## 4. Frontend UX Placement

### Options Evaluated

**Option A: Chart Settings → Research Engines**

A tab within the existing chart settings panel.

- Pros: Contextually close to where engine output is visible
- Cons: Buried inside a tool-specific modal; not discoverable; chart settings implies display preferences, not engine governance; inappropriate for a catalog that spans all research domains, not just charting
- Verdict: Not recommended

**Option B: Admin / Research Settings page**

A dedicated settings area in the main navigation for research configuration and governance.

- Pros: Correct conceptual home; accessible to researchers without being in a user-facing consumer context; scales to all engine domains as the catalog grows; can host other governance views alongside (strategy lifecycle, backtest configuration)
- Cons: Requires a settings/admin section in the nav (may need a new nav item)
- Verdict: Recommended for Phase 1

**Option C: Strategy Lab settings panel**

Inside the existing Strategy Lab or strategy composition interface.

- Pros: Researchers naturally work here
- Cons: Engine versioning is a platform concern, not a strategy-specific concern; embedding it inside a strategy tool misrepresents its scope; would need to be duplicated or linked from other contexts as more domains are added
- Verdict: Not recommended as primary location; a link from Strategy Lab to the Engine Registry page is acceptable

**Option D: Dedicated Engine Registry page**

A standalone top-level page (`/research-engines`) with full catalog, version history, and per-engine detail views.

- Pros: Correct long-term home; most visible; no location ambiguity
- Cons: More frontend work for a first implementation; nav item may feel prominent relative to the value delivered in Phase 1 when only two engines are registered
- Verdict: Recommended long-term target; implement in Phase 3 when the catalog has grown

### Recommendation

**Phase 1**: Implement the version log as a panel within a Research / Admin settings area. A single view showing the engine catalog table (columns: Name, Domain, Status, Frozen Date, Rulebook) with expandable rows for full metadata. No routing complexity. No dedicated page yet.

**Phase 3**: Promote to a dedicated `/research-engines` page with per-engine detail views (`/research-engines/minor_structure_v1`) and a version comparison feature.

---

## 5. Version Log vs Version Selection

These are two distinct concepts. They must not be conflated in the UI or in the data model.

**The Engine Version Log** (this document) is a **read-only metadata viewer**.

It answers: What versions exist? What is each one's status, purpose, and history? It does not change anything. It cannot change which engine runs.

**Engine Version Selection** is a **pipeline configuration capability** that does not yet exist.

When it exists, it will allow authorised researchers to configure which engine version a specific research pipeline uses (e.g., a comparison backtest may pin to `minor_structure_v2` while production continues using `minor_structure_v1`). This is a separate feature with its own governance requirements:

- Selection is only permitted for validated engine versions
- Production pipelines may not be ad hoc reconfigured through the UI
- Engine selection requires explicit save/commit to pipeline configuration
- Changes are auditable

**The frontend must not implement implicit engine selection through the version log UI.** Displaying a list of engines with a "Set as Active" button is prohibited until the full engine selection governance is designed and approved.

---

## 6. Governance Constraints

These constraints apply to all future implementation of the version log system.

**Frontend must not contain engine business logic.**

The frontend renders metadata received from the API. It must not compute derived lifecycle state, infer engine capabilities, or make decisions about which engines are compatible with a given context. All such logic belongs in the backend service layer.

**Frontend must not hardcode available engines.**

The list of engines rendered in the UI must come from `GET /api/research-engines`. Adding a new engine to the catalog must require only: (1) adding the record to the backend registry file, and (2) deploying. No frontend code changes required.

**Frontend must consume backend metadata API.**

No direct file system access, no inline engine lists in frontend config files, no environment variable driven engine lists. The API is the only interface.

**Production engines must remain protected.**

The version log UI must clearly distinguish Production engines from Experimental/Deprecated engines. Styling should make Production status unambiguous. The UI must not present any control that could be misread as allowing modification of a Production engine's configuration.

**Experimental engines must be removable without breaking production.**

If an Experimental engine record is removed from the backend registry (because the experiment was abandoned), the frontend must gracefully handle a catalog response that no longer contains that engine. No hardcoded assumptions about which engines exist.

---

## 7. Future Migration: Static File → PostgreSQL

The migration from Phase 1 (static YAML file) to Phase 2 (PostgreSQL) is a backend-only change.

**What changes:**

1. `EngineRegistryRepository` implementation is replaced: instead of reading a YAML file at startup, it queries a `research_engine_versions` PostgreSQL table
2. A data migration script imports the static file records into the database
3. A governance workflow is implemented for updating engine records (e.g., an admin-only API endpoint, or a CLI migration command, or direct database management with audit logging)

**What does not change:**

- API contract: `GET /api/research-engines` and `GET /api/research-engines/{technical_id}` remain identical
- Frontend code: zero changes
- Response schema: identical JSON shape
- Individual engine record files in `docs/research_engines/`: retained as human-readable documentation regardless of which storage backend is used

**Migration trigger:**

The migration to PostgreSQL should be triggered when at least one of the following conditions is met:

- The catalog contains more than 10 engine versions and manual YAML maintenance becomes error-prone
- Engine promotion workflow automation is being built (automated status transitions requiring database transactions)
- Audit trail requirements mandate database-level change history rather than git history

Until then, the static file approach is preferred for its simplicity and git-native auditability.

---

## 8. Implementation Phases

### Phase 1 — Static Registry + Documentation (current)

- [x] Engine records created for `minor_structure_v1` and `main_structure_v1`
- [x] `ENGINE_CATALOG.md` established as human-readable index
- [ ] `backend/config/research_engines.yaml` — static registry file (future implementation task)
- [ ] `GET /api/research-engines` — thin read-only API route (future implementation task)
- [ ] `GET /api/research-engines/{technical_id}` — single engine endpoint (future implementation task)

### Phase 2 — Frontend Version Log Panel

- [ ] Research / Admin settings area with engine catalog table
- [ ] Expandable row or detail modal per engine (full metadata display)
- [ ] Status badges with clear Production / Experimental / Deprecated styling
- [ ] No engine selection controls in this phase

### Phase 3 — Dedicated Engine Registry Page

- [ ] Standalone `/research-engines` route
- [ ] Per-engine detail page (`/research-engines/{technical_id}`)
- [ ] Version history view per engine (all versions in a domain, with status timeline)
- [ ] Links from chart interface to the engine record for the active production version

### Phase 4 — PostgreSQL Migration

- [ ] `research_engine_versions` table
- [ ] Repository swap in service layer
- [ ] Data migration from YAML
- [ ] API contract unchanged

### Phase 5 — Engine Version Selection (separate governance design required)

- [ ] Pipeline configuration API
- [ ] Research-only version pinning for comparison studies
- [ ] Governance approval workflow for non-production version use
- [ ] Audit trail for version selections

---

## 9. Risks and Guardrails

| Risk | Guardrail |
|---|---|
| Frontend hardcodes engine list | Enforce: engine list must always come from API; frontend code review must reject any inline engine constants |
| Version log UI gains a "Set as Active" button prematurely | Enforce: Phase 2 UI has no mutation controls; any version selection feature requires a separate governance design (Phase 5) |
| Static registry file diverges from individual engine record files in `docs/research_engines/` | Enforce: when adding an engine to the registry file, the corresponding `docs/research_engines/<id>.md` must exist; CI check or agent pre-flight rule |
| Experimental engine accidentally wired into production API route before reaching Production status | Enforce: production routes must reference the `"production"` resolver, never a pinned version string; agent guardrails in `ARCHITECTURE_GUARDRAILS.md` section 29 |
| Migration from YAML to PostgreSQL changes API shape | Guardrail: lock the API response schema before Phase 2 implementation; any schema change is a breaking change requiring frontend update |
| Engine metadata becomes stale after code changes | Guardrail: when modifying an engine's behaviour, the agent must update `docs/research_engines/<id>.md` change_log and (once built) the registry file |

---

## Summary

| Decision | Choice |
|---|---|
| Phase 1 metadata storage | Static YAML file in `backend/config/` |
| API style | Read-only REST; no mutations |
| Frontend placement Phase 1 | Research / Admin settings panel |
| Frontend placement long-term | Dedicated `/research-engines` page (Phase 3) |
| Version selection | Not in scope for this design; separate governance required |
| Migration path | Static YAML → PostgreSQL; API contract unchanged |
| Frontend engine list source | Always from `GET /api/research-engines`; never hardcoded |

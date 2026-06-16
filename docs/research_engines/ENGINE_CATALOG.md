# QuantLab Research Engine Catalog

_Audience: researchers, traders, architects, implementation agents._  
_This catalog is the human-readable index of all versioned research engines across the QuantLab platform._  
_Source of truth for individual engine details: each engine's own record in this directory._

---

## How to Read This Catalog

Each row represents one engine version. Engines are grouped by domain. A domain may have multiple versions in different lifecycle states simultaneously.

**Lifecycle states:**

| Status | Meaning |
|---|---|
| `Experimental` | Under development; contracts may be unstable; not connected to production |
| `Validated` | Tests pass; schema frozen; available for research comparison |
| `Candidate` | Passes side-by-side comparison; under review for production promotion |
| `Production` | Authoritative version; all production pipelines use this |
| `Deprecated` | Superseded; existing consumers must migrate; no new consumers |
| `Retired` | Removed from active use; archived if referenced by historical records |

Full lifecycle governance: `docs/RESEARCH_ENGINE_VERSIONING.md`

---

## Market Structure Domain

### Minor Structure

| Human Name | Technical ID | Status | Frozen | Supersedes | Superseded By | Record |
|---|---|---|---|---|---|---|
| Classic Minor Structure | `minor_structure_v1` | **Production** | 2026-06-14 | — | — | [minor_structure_v1.md](minor_structure_v1.md) |

### Main Structure

| Human Name | Technical ID | Status | Frozen | Supersedes | Superseded By | Record |
|---|---|---|---|---|---|---|
| Classic Main Structure | `main_structure_v1` | **Production** | 2026-06-14 | — | — | [main_structure_v1.md](main_structure_v1.md) |

---

## Other Domains

_No engines registered yet. As new research modules are built and promoted to Experimental or above, they will be recorded here._

Expected future domains (not committed; illustrative only):

- Break of Structure (BoS) detection
- Change of Character (CHoCH) detection
- Volume profile analysis
- Momentum and volatility indicators
- Planetary / cycle research modules
- ML-based signal generators

---

## Quick Reference: Production Engines

| Domain | Human Name | Technical ID | Frozen Date |
|---|---|---|---|
| Minor Structure | Classic Minor Structure | `minor_structure_v1` | 2026-06-14 |
| Main Structure | Classic Main Structure | `main_structure_v1` | 2026-06-14 |

---

## Catalog Maintenance Rules

**Adding a new engine record:**

1. Create a file in `docs/research_engines/` named `<technical_id>.md`
2. Use the metadata template from `docs/RESEARCH_ENGINE_VERSIONING.md` section B
3. Add a row to this catalog under the appropriate domain section
4. Ensure lifecycle status is accurate at the time of addition

**Updating an engine's lifecycle status:**

1. Update the engine's individual record file
2. Update the row in this catalog
3. If an engine is being superseded, update both the outgoing and incoming engine's `Supersedes` / `Superseded By` fields

**Retiring an engine:**

1. Update lifecycle status to `Retired` in the individual record
2. Update the catalog row
3. Move the row to a `## Retired Engines` section (do not delete the row)
4. Do not delete the individual record file if any historical production records reference the engine

**Never:**

- Delete an engine record that was ever promoted to Production
- Promote an engine without creating its individual record first
- Mark an engine as Production without updating this catalog

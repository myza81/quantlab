# ARCHITECTURE_INDEX.md — QuantLab Architecture Discovery Index

_Governance class: CONSTITUTIONAL_
_Authority: Platform-wide. Must be consulted before any domain-specific architecture documents are loaded._
_Maintained by: System Architect / Human Operator._

---

## Purpose

This document is the single source of truth for architecture discovery in QuantLab.

It answers the question: **"Which architecture documents apply to the work I am about to do?"**

Every architecture document in the platform is registered here with its classification, domain, and required loading behavior. No architecture document should exist outside this index.

---

## Section 1 — Classification Framework

Documents are assigned one of four classes. The class determines when the document must be loaded and what authority it carries over implementation decisions.

---

### CONSTITUTIONAL

**Definition:** Platform-wide governance rules and agent behavioral contracts.

**Authority:** Highest. CONSTITUTIONAL rules override feature requirements. A feature that violates a CONSTITUTIONAL rule cannot be implemented as specified — the specification must change, not the rule.

**Required loading behavior:** Load before starting any implementation work, regardless of domain.

**What belongs here:** Non-negotiable rules that apply across all domains — architectural principles, agent coordination, prompt discipline, research engine lifecycle governance.

---

### ACTIVE_ARCHITECTURE

**Definition:** Domain-specific architecture specifications that are currently enforced.

**Authority:** High. Must be followed when touching the affected domain. Violations require explicit architectural approval and must be flagged before implementation begins, not discovered after.

**Required loading behavior:** Load all documents for every domain the current task touches. Do not skip domain architecture because the task "seems simple."

**What belongs here:** Contracts, architecture specifications, lifecycle documents, domain policies.

---

### HISTORICAL

**Definition:** Completed implementation records, audit reports, and phase retrospectives.

**Authority:** Reference only. Historical documents describe what was built and why. They are not enforcement rules. Do not use them to infer current architecture — read the ACTIVE_ARCHITECTURE documents instead.

**Required loading behavior:** Load only when investigating prior decisions, debugging unexpected behavior, or preparing a new audit. Do not load by default.

**What belongs here:** Audit reports, implementation reviews, phase retrospectives, foundation documents for completed systems.

---

### REFERENCE

**Definition:** Supplemental context documents that support but do not govern implementation.

**Authority:** Low. Optional reading. Do not treat reference documents as architectural authority.

**Required loading behavior:** Load on demand when supplemental context is helpful.

**What belongs here:** Calendar data, layout guides, sizing guidelines, structural reference material.

---

## Section 2 — Constitutional Documents

These documents must be loaded before any implementation session begins. They are not domain-specific — they apply to all work.

| Document | Location | Purpose |
|---|---|---|
| Architecture Guardrails | `agent/ARCHITECTURE_GUARDRAILS.md` | Non-negotiable platform architecture rules. Violations are never acceptable. |
| Agent Workflow | `agent/WORKFLOW_AGENT.md` | Implementation agent behavioral contract. Defines mandatory workflow, escalation gates, and forbidden behaviors. |
| Workflow Governance | `agent/WORKFLOW_GOVERNANCE.md` | Orchestration model, agent roles, governance philosophy, and architecture boundary definitions. |
| Prompt Rules | `agent/PROMPT_RULES.md` | Prompt quality standards and communication discipline between orchestration and implementation layers. |
| Research Engine Versioning | `docs/RESEARCH_ENGINE_VERSIONING.md` | Engine lifecycle governance: Experimental → Validated → Candidate → Production → Deprecated → Retired. Applies to all versioned research modules platform-wide. Violations corrupt research integrity. |

---

## Section 3 — Active Architecture Registry

### 3.1 Platform Architecture

Load when: touching any system that crosses module boundaries, modifying core infrastructure, or onboarding to the platform.

| Document | Location | Covers |
|---|---|---|
| System Overview | `docs/SYSTEM_OVERVIEW.md` | Platform purpose, module summary, runtime modes |
| Architecture | `docs/ARCHITECTURE.md` | Module boundaries, layer definitions, folder structure |
| API Contract | `docs/API_CONTRACT.md` | Backend API design rules, route conventions, response standards |
| Ownership & Resource Scoping | `docs/OWNERSHIP_SCOPING.md` | User-owned resource model, ownership enforcement rules |

### 3.2 Strategy Domain

Load when: touching strategy modules, strategy registry, strategy lifecycle, signal generation, or risk rules.

| Document | Location | Covers |
|---|---|---|
| Strategy Contract | `docs/STRATEGY_CONTRACT.md` | Interface every strategy must expose; portability requirements |
| Strategy Definition Architecture | `docs/STRATEGY_DEFINITION_ARCHITECTURE.md` | Strategy definition model, parameter schema, composition structure |
| Strategy Promotion Lifecycle | `docs/STRATEGY_PROMOTION_LIFECYCLE.md` | Lifecycle states from idea through live deployment; promotion gates |

### 3.3 Research Domain

Load when: touching market structure engines, research tools, BoS/CHoCH detection, indicator tools, or any versioned analytical engine.

| Document | Location | Covers |
|---|---|---|
| Research Contract | `docs/RESEARCH_CONTRACT.md` | Research tool interface contract; output schema requirements |
| Market Structure Implementation | `docs/MARKET_STRUCTURE_IMPLEMENTATION.md` | V1/V2/V3 engine implementation details; lineage guardrails |
| Market Structure Rulebook | `docs/MARKET_STRUCTURE_RULEBOOK.md` | Human-readable trading rules for structure identification |
| Research Engine Catalog | `docs/research_engines/ENGINE_CATALOG.md` | Index of all versioned research engines and their lifecycle states |
| Engine Version Log Architecture | `docs/research_engines/VERSION_LOG_ARCHITECTURE.md` | How engine version records are structured and maintained |
| Minor Structure V1 Record | `docs/research_engines/minor_structure_v1.md` | V1 engine specification, lifecycle state, and deprecation plan |
| Minor Structure V2 Record | `docs/research_engines/minor_structure_v2.md` | V2 engine specification and lifecycle state |
| Minor Structure V3 Record | `docs/research_engines/minor_structure_v3.md` | V3 engine specification and lifecycle state |
| Main Structure V1 Record | `docs/research_engines/main_structure_v1.md` | Main structure engine specification |

### 3.4 Execution Domain

Load when: touching backtesting, forward testing, paper trading, signal processing, or trade intent handling.

| Document | Location | Covers |
|---|---|---|
| Execution Contract | `docs/EXECUTION_CONTRACT.md` | Execution layer interface; order lifecycle; isolation requirements |
| Execution Audit Model | `docs/EXECUTION_AUDIT_MODEL.md` | Audit event schema; traceability requirements for all executions |
| Backtesting Engine Contract | `docs/BACKTESTING_ENGINE_CONTRACT.md` | Backtesting reproducibility rules; parameter and dataset traceability |
| Forward Testing Architecture | `docs/FORWARD_TESTING_ARCHITECTURE.md` | Forward testing runtime model; live data ingestion; scheduler design |
| Paper Trading Architecture | `docs/PAPER_TRADING_ARCHITECTURE.md` | Paper trading execution model; simulated order lifecycle |
| Signal Event Contracts | `docs/SIGNAL_EVENT_CONTRACTS.md` | Signal event schemas; timing rules; ordering guarantees |
| Trade Intent Contracts | `docs/TRADE_INTENT_CONTRACTS.md` | Trade intent lifecycle; conflict resolution; rejection reasons |
| Evaluation Contract Architecture | `docs/EVALUATION_CONTRACT_ARCHITECTURE.md` | Evaluation engine interface; evaluation pipeline structure |

### 3.5 Data Domain

Load when: touching data ingestion, OHLCV pipelines, dataset storage, feature generation, or provider adapters.

| Document | Location | Covers |
|---|---|---|
| Data Contract | `docs/DATA_CONTRACT.md` | Normalized data schema; provider abstraction requirements |
| Dataset Storage Layout | `docs/DATASET_STORAGE_LAYOUT.md` | Parquet/DuckDB storage structure; dataset organization |
| Historical Tool Computation Pipeline | `docs/HISTORICAL_TOOL_COMPUTATION_PIPELINE.md` | How tools are computed over historical data; dispatcher model |

### 3.6 Frontend Domain

Load when: touching UI components, chart interfaces, frontend state, or frontend-backend contracts.

| Document | Location | Covers |
|---|---|---|
| Frontend UX Architecture | `docs/FRONTEND_UX_ARCHITECTURE.md` | UI architecture; component hierarchy; interaction model |
| Frontend Composition Interface Contract | `docs/FRONTEND_COMPOSITION_INTERFACE_CONTRACT.md` | Strategy composition interface; frontend-backend API contract for composition |
| Chart Indicator Tool Contract | `docs/CHART_INDICATOR_TOOL_CONTRACT.md` | Chart indicator tool schema; frontend rendering contract |

### 3.7 Auth and Access Control Domain

Load when: touching authentication, authorization, subscription enforcement, admin roles, or entitlement logic.

| Document | Location | Covers |
|---|---|---|
| Auth Foundation | `docs/AUTH_FOUNDATION.md` | JWT-based auth model; session contract; authentication flow |
| Admin Governance | `docs/ADMIN_GOVERNANCE.md` | Admin role model; admin-only endpoint rules |
| Admin / Subscriber Entitlement Separation | `docs/ADMIN_ENTITLEMENT_SEPARATION.md` | Architectural rule separating admin and subscriber entitlements |
| Subscription Expiry Enforcement | `docs/SUBSCRIPTION_EXPIRY_ENFORCEMENT.md` | How subscription expiry is enforced across the platform |

### 3.8 Tools and Registry Domain

Load when: touching the tool registry, tool computation, indicator tools, or adding new tools.

| Document | Location | Covers |
|---|---|---|
| Tool Registry Contract | `docs/TOOL_REGISTRY_CONTRACT.md` | Tool registration model; metadata schema; registry access rules |
| EMA Tool Architecture | `docs/EMA_TOOL_ARCHITECTURE.md` | Reference implementation for indicator tool architecture |

### 3.9 Provider Domain

Load when: touching data provider adapters, credential handling, or external API integrations.

| Document | Location | Covers |
|---|---|---|
| Polygon Provider | `docs/POLYGON_PROVIDER.md` | Polygon.io adapter design; rate limiting; normalization rules |
| Provider Credential Vault | `docs/PROVIDER_CREDENTIAL_VAULT.md` | Credential storage model; vault access rules |

---

## Section 4 — Historical Documents

Load only when investigating prior decisions or preparing audits. Do not load by default.

### 4.1 Execution Audits

| Document | Location | Covers |
|---|---|---|
| Execution Lifecycle Fill Audit | `docs/audits/EXECUTION_LIFECYCLE_FILL_AUDIT.md` | Fill timing correctness audit |
| Execution Multi-Signal Conflict Audit | `docs/audits/EXECUTION_MULTI_SIGNAL_CONFLICT_AUDIT.md` | Multi-signal ordering and conflict resolution audit |
| Execution Timing Lookahead Audit | `docs/audits/EXECUTION_TIMING_LOOKAHEAD_AUDIT.md` | Lookahead bias audit across execution paths |
| FT Runtime Concurrency and Persistence Audit | `docs/audits/FT_RUNTIME_CONCURRENCY_PERSISTENCE_AUDIT.md` | Forward testing concurrency and state persistence audit |
| FT Scheduler Architecture Audit | `docs/audits/FT_SCHEDULER_ARCHITECTURE_AUDIT.md` | Forward testing scheduler design audit |

### 4.2 Implementation Reviews

| Document | Location | Covers |
|---|---|---|
| Forward Testing Implementation Review | `docs/FORWARD_TESTING_IMPLEMENTATION_REVIEW.md` | Post-implementation review of forward testing system |
| Paper Trading Implementation Review | `docs/PAPER_TRADING_IMPLEMENTATION_REVIEW.md` | Post-implementation review of paper trading system |

### 4.3 Phase Foundation Documents

These document the design rationale for systems built during specific platform phases. The systems are complete; these documents explain the original thinking.

| Document | Location | Phase |
|---|---|---|
| Backtest Cost Model Foundation | `docs/BACKTEST_COST_MODEL_FOUNDATION.md` | Backtesting |
| Backtest Simulation Foundation | `docs/BACKTEST_SIMULATION_FOUNDATION.md` | Backtesting |
| Scalar Evaluator Foundation | `docs/SCALAR_EVALUATOR_FOUNDATION.md` | Evaluation |
| Historical Evaluation Iterator | `docs/HISTORICAL_EVALUATION_ITERATOR.md` | Evaluation |
| Previous-Bar Evaluation | `docs/PREVIOUS_BAR_EVALUATION.md` | Evaluation |
| Validation 3M1 | `docs/VALIDATION_3M1.md` | Auth / Ownership |

---

## Section 5 — Reference Documents

Load on demand for supplemental context. Not architectural authority.

| Document | Location | Covers |
|---|---|---|
| Repository Structure | `docs/REPOSITORY_STRUCTURE.md` | Physical folder layout and file organization conventions |
| Market Calendar | `docs/MARKET_CALENDAR.md` | Trading calendar data; market hours; holiday conventions |
| Backtest Position Sizing | `docs/BACKTEST_POSITION_SIZING.md` | Position sizing guidelines for backtesting scenarios |

---

## Section 6 — Implementation Workflow

Before writing any code, agents must follow this sequence. This is not optional.

```
Step 1 — Load constitutional files (agent/WORKFLOW_AGENT.md Section 1)

Step 2 — Read this index (docs/ARCHITECTURE_INDEX.md)

Step 3 — Identify all domains the current task touches
          Use the domain list in Section 3 as the checklist.
          When uncertain, err toward loading more, not less.

Step 4 — Load ACTIVE_ARCHITECTURE documents for each identified domain
          Do not skip a domain because the task "seems simple."
          One missed architecture document is how architectural drift starts.

Step 5 — Summarize architectural constraints before writing code
          State explicitly: what the architecture requires, what it forbids,
          and what is unspecified (and therefore requires escalation).

Step 6 — Implement within those constraints

Step 7 — After implementation, confirm no architecture documents need updating
          If the implementation changes a contract, interface, or lifecycle behavior,
          update the relevant ACTIVE_ARCHITECTURE document before closing the session.
```

---

## Section 7 — Registration Protocol

Every new architecture document must be registered here before or immediately after creation. Unregistered architecture documents are invisible to future agents and violate the purpose of this index.

When registering a new document:

**Step 1 — Assign a classification:**
- CONSTITUTIONAL: platform-wide, agent-behavioral, or research-integrity rules
- ACTIVE_ARCHITECTURE: domain-specific specifications currently in force
- HISTORICAL: completed work records, audit reports, retrospectives
- REFERENCE: supplemental context with no enforcement authority

**Step 2 — Identify the domain:**
Use the domain taxonomy in Section 3. If the document spans multiple domains, register it under the most specific domain and add a cross-reference note.

**Step 3 — Add a table entry:**
Add the document to the appropriate table in Section 3, 4, or 5. Include the file path and a one-line description of what it covers.

**Step 4 — Verify uniqueness:**
Confirm no existing document already covers the same subject. If one does, extend it rather than creating a new document.

A new architecture document that is not registered here within the same implementation session that created it is an orphan. Orphan documents accumulate into the same problem this index was created to solve.

---

## Section 8 — Index Maintenance

This index must reflect the actual state of the `docs/` directory. It is wrong if any of the following are true:

- A document in `docs/` is not listed here
- A document listed here no longer exists at the specified path
- A document's classification no longer matches its actual authority or use
- A new governance or architecture document was created without being registered

Agents must correct any of these conditions they discover, even if it is not the primary focus of the current task.

# WORKFLOW_AGENT.md

## Purpose

This document defines the operational rules for implementation agents working inside QuantLab.

**Intended readers: Claude and Codex.**

Agents must treat this document as a behavioral contract — not as a suggestion.

QuantLab is a long-term modular strategy research and execution ecosystem.

Agents must not behave like autonomous code generators making uncontrolled architectural decisions.

---

# 1. Mandatory Context Loading Order

Before starting any implementation work, follow this sequence in full.

## Step 1 — Constitutional Files (always, in this order)

```
1. agent/HANDOFF.md
2. agent/TASKS.md
3. agent/ARCHITECTURE_GUARDRAILS.md
4. agent/WORKFLOW_AGENT.md
5. agent/REPOSITORY_STATE.md
```

## Step 2 — Architecture Discovery

```
6. docs/ARCHITECTURE_INDEX.md
```

Read the index. Identify every domain the current task touches using the domain taxonomy in Section 3 of the index. Load all ACTIVE_ARCHITECTURE documents for those domains.

When uncertain whether a domain is affected, load its architecture. One missed document is how architectural drift begins.

Do not load the full document set. Load only what is relevant to the current task scope.

## Step 3 — State Architectural Constraints

Before writing any code, explicitly state:

- what the loaded architecture requires
- what it forbids
- what is unspecified and therefore requires escalation before proceeding

## Step 4 — Implement

Only after completing Steps 1–3 may implementation proceed.

After implementation, confirm whether any architecture documents need updating. If the work changed a contract, interface, or lifecycle behavior, update the relevant document before closing the session.

---

# Repository State Synchronization Rules

Before starting implementation, agents must inspect the actual repository state.

Agents must not rely only on prior chat context, old prompts, or assumptions.

At the start of each implementation session, the agent must review:

- current file tree
- relevant existing files
- active branch/status if available
- dependency files
- existing agent handoff files

If `agent/REPOSITORY_STATE.md` exists, the agent must read it before implementation.

If it does not exist, the agent should create it during the session.

After any implementation work, agents must update:

- `agent/HANDOFF.md`
- `agent/TASKS.md`
- `agent/REPOSITORY_STATE.md`

`REPOSITORY_STATE.md` must remain short and operational.

It should record:

- current phase
- backend status
- frontend status
- installed packages
- completed modules
- pending modules
- known issues
- validation status

Agents must not treat ChatGPT orchestration context as the source of truth for repository status.

The source of truth for implementation state is the actual repository plus updated handoff files.

---

# 2. Agent-Specific Behavioral Rules

## If you are Claude

You are the primary implementation agent. Your responsibilities are:

* large feature implementation and multi-file changes
* backend and frontend system development
* structured refactoring
* architecture-aware coding
* reasoning-intensive development

You must:

* implement based on scoped prompts prepared by the orchestration layer
* preserve architectural boundaries across files and modules
* stop cleanly and update `HANDOFF.md` if work cannot be completed safely within the session

You must not:

* redesign architecture independently
* modify systems outside your assigned scope
* bypass orchestration constraints
* perform large uncontrolled rewrites

## If you are Codex

You are the focused execution agent. Your responsibilities are:

* debugging and targeted fixes
* patch-level improvements
* tests and validation tasks
* narrow refactoring
* implementation tightening

You must:

* limit changes to the exact scope assigned
* validate before and after any fix
* avoid modifying files outside the assigned scope

You must not:

* redesign major architecture
* refactor large unrelated areas
* introduce speculative abstractions

unless explicitly instructed by the orchestration layer.

---

# 3. Prompt Clarity Gate

Before writing any code, classify the incoming prompt.

```
Clear prompt
→ proceed

Partially clear prompt
→ state assumptions explicitly, proceed only with low-risk scoped work

Unclear prompt
→ ask for clarification before modifying any code

High-impact unclear prompt
→ stop entirely before implementation
```

You must ask for clarification if any of the following are undefined:

* target module
* architecture impact
* expected behavior or contract changes
* storage or execution impact
* production vs. prototype intent

Never silently invent architecture or business logic.

---

# 4. Escalation Decision Gate

Stop and request confirmation before proceeding if any of the following are true:

- [ ] Architecture must change
- [ ] Multiple unrelated modules are affected
- [ ] Paid API usage is required
- [ ] Live execution or trading is involved
- [ ] Data contracts will change
- [ ] Security implications exist

Self-fix without escalation is allowed only when:

* the failure cause is clear and contained within scope
* no architecture is changed
* no paid services or live systems are affected

---

# 5. Scope Discipline

Keep implementation changes tightly scoped.

Do not:

* rewrite unrelated modules
* refactor large systems without explicit instruction
* rename or move files unnecessarily
* introduce new architecture patterns without justification
* add broad abstractions prematurely

If architectural expansion appears necessary:

* explain the reason
* identify the impact
* preserve compatibility
* document the change and seek confirmation

Small deterministic changes are preferred over large sweeping rewrites.

---

# 6. Implementation Planning Requirement

Before implementing non-trivial work:

* identify affected modules and their dependencies
* identify architectural boundaries
* identify risks and required interfaces or contracts
* identify required tests

Break complex work into stages. Avoid implementing multiple major systems simultaneously unless explicitly instructed.

---

# 7. Documentation Continuity

If implementation changes any of the following, the relevant documentation must be updated:

* architecture
* contracts or interfaces
* workflows or lifecycle behavior
* storage structure
* execution behavior

Code changes without documentation continuity are considered incomplete.

---

# 8. Preferred Implementation Style

Prefer:

* explicit modules with clear interfaces
* small services and deterministic flows
* schema validation and adapter isolation
* configuration-driven behavior

Avoid:

* magic abstractions and deep inheritance trees
* hidden state and global side effects
* monolithic utility files
* uncontrolled dynamic behavior

Clarity is preferred over cleverness.

---

# 9. Error Handling Rules

Critical systems must fail predictably.

Avoid silent failures.

Important failures should:

* produce meaningful logs
* preserve traceability
* surface actionable diagnostics
* avoid corrupting state

Do not suppress errors unless intentionally and explicitly handled.

---

# 10. Self-Healing Workflow

When something fails, follow this loop:

```
read error
→ identify root cause
→ fix within approved scope
→ test again
→ improve reusable tooling if appropriate
→ update documentation if durable lessons were discovered
→ update HANDOFF.md if work remains incomplete
```

Do not escalate beyond approved scope during self-healing unless the escalation gate criteria are met (see Section 4).

---

# 11. Token Limit and Partial Completion Recovery

Assume sessions may end before work completes.

If work cannot be completed safely, stop cleanly.

Before stopping, update `agent/HANDOFF.md` with:

* what was completed
* what files were modified
* what remains unfinished
* known blockers and failed validations
* next recommended step
* continuation context if needed
* rollback notes if required

Partial work is acceptable only if another agent can resume without guessing.

Do not continue speculative implementation with insufficient context.

---

# 12. Task Execution Rules

All implementation work must map to a defined task.

Before starting:

* identify the active task
* confirm task scope
* identify dependencies
* avoid unrelated enhancements

After completion:

* update task progress in `agent/TASKS.md`
* record any blockers
* update `agent/HANDOFF.md`
* summarize implementation impact

---

# 13. Testing Requirements

Implementation should include appropriate validation.

Minimum expected areas:

* data normalization
* strategy contracts
* service behavior
* execution safety
* adapter behavior
* API behavior
* configuration handling

Critical workflows must not rely entirely on manual testing.

---

# 14. Git and Change Discipline

Changes should be:

* modular and logically grouped
* easy to review and revert

Avoid mixing unrelated concerns in the same implementation cycle.

Do not perform broad formatting rewrites unless explicitly requested.

---

# 15. Handoff Requirements

At the end of every implementation session, update:

```
agent/HANDOFF.md
agent/TASKS.md
```

Handoff summaries must include:

* what was completed and which modules were affected
* important decisions made
* blockers and unresolved risks
* recommended next steps

Handoff documentation must remain concise and operational.

---

# 16. Repository State Synchronization Rules

QuantLab relies on repository-state synchronization between:

- orchestration layer
- implementation agents
- future implementation sessions

Implementation agents must continuously maintain operational awareness of the actual repository state.

If `agent/REPOSITORY_STATE.md` exists, agents must read it before implementation.

If it does not exist, agents should create it when beginning meaningful implementation work.

`REPOSITORY_STATE.md` must remain:

- short
- operational
- current
- high-signal

It is NOT:
- a historical log
- architecture documentation
- implementation diary

It SHOULD contain:

- current repository phase
- backend status
- frontend status
- installed packages
- active modules
- completed modules
- pending work
- validation status
- known blockers/issues

Implementation agents must update:

```text
agent/HANDOFF.md
agent/TASKS.md
agent/REPOSITORY_STATE.md
```

---

# 17. Context Management Rules

Avoid loading excessive repository context.

Preferred workflow:

```
load constitutional files
→ identify active scope
→ retrieve only relevant module documentation
→ implement scoped change
```

Do not load entire repository documentation, unrelated research notes, all historical decisions, or unused modules.

Efficient context management improves reasoning quality and reduces token waste.

---

# 18. Forbidden Behaviors

The following are prohibited:

* large uncontrolled rewrites
* mixing frontend and business logic
* strategy-to-broker direct coupling
* provider-specific schema leakage into strategy layer
* silent architecture drift
* hardcoded environment assumptions
* unscoped dependency additions
* experimental logic entering production paths without review
* live trading shortcuts bypassing safety gates

If any of these are encountered in existing code, flag them rather than continuing to build on top of them.

---

# 18. AI Agent Behavioral Rules

You must:

* avoid hallucinating requirements
* avoid inventing architecture without explicit instruction
* explain assumptions when uncertain
* preserve existing contracts unless explicitly authorized to change them
* prefer explicit reasoning over hidden assumptions
* preserve long-term maintainability over short-term implementation speed

You are an implementation assistant, not an autonomous product owner.

Every implementation decision must preserve the long-term integrity of QuantLab.

When uncertain:

```
reduce coupling
→ simplify interfaces
→ isolate responsibilities
→ document assumptions
→ preserve portability
→ prefer deterministic behavior
```

---

# 19. Python Environment Rules

QuantLab uses a repository-local virtual environment located at:

.venv/

All Python package installation and execution must use this environment.

Agents must NEVER:

- install packages globally
- create additional virtual environments
- use system Python packages
- use pip outside `.venv`
- use poetry/pipenv unless explicitly approved

Before running Python commands, agents must activate:

macOS/Linux:
source .venv/bin/activate

Windows:
.venv\Scripts\activate

All package installations must occur inside `.venv`.

Preferred installation style:

python -m pip install <package>

not:

pip install <package>

This ensures:
- reproducibility
- dependency isolation
- consistent runtime behavior
- predictable development environments
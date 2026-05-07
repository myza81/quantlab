# HANDOFF_UPDATE.md

## Purpose

This directive defines the workflow, structure, operational standards, and continuity requirements for updating `HANDOFF.md` inside QuantLab.

`HANDOFF.md` exists to preserve operational continuity between:

* ChatGPT orchestration sessions
* Claude implementation sessions
* Codex validation sessions
* future contributors

Handoff updates are critical for:

* context continuity
* architecture preservation
* implementation recovery
* token efficiency
* governance discipline

---

# Core Philosophy

`HANDOFF.md` is NOT:

* a historical archive
* a changelog dump
* a knowledge base
* long-form documentation

`HANDOFF.md` is an operational continuity layer.

The objective is to preserve:

* current state
* active direction
* unresolved blockers
* next recommended steps
* architectural context

with minimal token overhead.

---

# Objective

When updating `HANDOFF.md`, the implementation agent must:

1. preserve operational clarity
2. preserve continuity
3. avoid unnecessary verbosity
4. maintain architecture context
5. record actionable next steps
6. support session recovery
7. minimize token waste

---

# Required Update Workflow

Minimum required workflow:

```text
review current work
→ identify affected systems
→ summarize completed work
→ summarize remaining work
→ identify blockers
→ identify next actions
→ compress unnecessary details
→ update handoff
```

---

# Required Handoff Sections

`HANDOFF.md` should minimally preserve:

```text
Current Project State
Current Active Work
Completed Work Summary
Known Blockers
Architecture Notes
Next Recommended Actions
Operational Risks
```

---

# Update Timing Rules

`HANDOFF.md` should be updated when:

* implementation work completes
* architecture changes occur
* blockers appear
* priorities change
* runtime issues appear
* sessions end with incomplete work
* major validation work completes

---

# Partial Completion Rules

If work cannot complete safely within a session:

The agent must update:

```text
what was completed
what remains incomplete
affected files/modules
known blockers
validation status
recommended continuation steps
```

Another agent should be able to continue WITHOUT guessing.

---

# Continuity Rules

Handoff updates should preserve:

* implementation continuity
* architecture continuity
* operational continuity
* workflow continuity

Avoid vague summaries such as:

```text
did some backend work
```

Use explicit operational summaries instead.

---

# Token Efficiency Rules

`HANDOFF.md` must remain:

* concise
* operational
* high-signal
* compressed

Avoid:

* long explanations
* implementation tutorials
* duplicated architecture descriptions
* historical storytelling
* unnecessary detail expansion

---

# Architecture Preservation Rules

Handoff updates should explicitly mention if:

* architecture boundaries changed
* contracts changed
* runtime assumptions changed
* new risks appeared
* temporary shortcuts exist
* validation is incomplete

Hidden architecture drift is prohibited.

---

# Blocker Rules

Blockers should clearly identify:

* affected systems
* root issue
* current impact
* recommended next action
* whether escalation is required

Avoid ambiguous blocker descriptions.

---

# Validation Reporting Rules

Handoff updates should record:

* validation completed
* validation pending
* failed validation
* runtime observations
* reproducibility concerns
* unresolved architecture concerns

Validation state must remain visible.

---

# Recovery Rules

Handoff updates should support:

```text
session recovery
```

without requiring:

* re-reading entire repositories
* reconstructing architecture context
* guessing implementation intent

Operational continuity is mandatory.

---

# Task Coordination Rules

Handoff updates should remain synchronized with:

```text
TASKS.md
```

If priorities or active work changed, both documents should remain consistent.

---

# Multi-Agent Coordination Rules

When multiple agents are active, handoff updates should preserve:

* ownership boundaries
* affected modules
* parallel work coordination
* merge-risk visibility
* unresolved conflicts

Avoid ambiguous ownership.

---

# Temporary Work Rules

Temporary implementations must be explicitly labeled.

Examples:

```text
prototype
temporary validation tool
experimental runtime
non-production implementation
```

Temporary work must NOT silently become permanent architecture.

---

# Risk Reporting Rules

Handoff updates should identify risks such as:

* architecture drift
* runtime instability
* reproducibility concerns
* validation gaps
* overengineering risk
* token explosion risk
* hidden coupling risk

Operational risks must remain visible.

---

# Escalation Rules

Escalation should be recorded if:

* architecture changes are required
* contracts are unstable
* runtime safety risks exist
* scope expansion occurred
* implementation assumptions are uncertain

High-impact ambiguity must not remain hidden.

---

# Compression Rules

Completed or obsolete details should be:

* summarized
* compressed
* removed

when they no longer improve operational continuity.

`HANDOFF.md` must remain operationally efficient.

---

# Forbidden Patterns

The following are prohibited:

* turning HANDOFF.md into a wiki
* storing long historical logs
* duplicating architecture documents
* vague incomplete summaries
* hidden blockers
* hidden temporary shortcuts
* undocumented architecture changes
* oversized session dumps

---

# Deliverables

Minimum expected handoff updates:

* completed work summary
* remaining work summary
* blocker summary
* validation summary
* next recommended actions
* architecture-impact notes if applicable

---

# Validation Checklist

Before updating `HANDOFF.md`, confirm:

- [ ] operational continuity is preserved
- [ ] blockers are explicit
- [ ] next actions are actionable
- [ ] validation state is visible
- [ ] architecture-impact notes exist if needed
- [ ] temporary work is labeled
- [ ] token efficiency is preserved
- [ ] unnecessary historical detail is avoided
- [ ] TASKS.md consistency is preserved
- [ ] no governance guardrails were violated

---

# Final Instruction

`HANDOFF.md` inside QuantLab exists to preserve operational continuity across AI-assisted engineering workflows.

Handoff updates are NOT:

* documentation dumps
* session diaries
* architecture replacements
* historical archives

The objective is to create concise, high-signal operational continuity capable of supporting long-term modular development while preserving:

* architecture integrity
* workflow discipline
* implementation continuity
* token efficiency
* institutional-grade governance
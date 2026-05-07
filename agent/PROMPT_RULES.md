# PROMPT_RULES.md

## Purpose

This document defines the communication and prompting rules for implementation agents working inside QuantLab.

QuantLab uses AI-assisted engineering workflows.

Prompts are treated as operational interfaces between:
human operator
→ orchestration AI
→ implementation AI
→ repository

The quality of prompts directly affects:

* implementation quality
* architectural consistency
* token efficiency
* reasoning accuracy
* maintainability
* project scalability

The purpose of this document is to reduce ambiguity, prevent uncontrolled implementation behavior, and establish deterministic AI-assisted engineering workflows.

---

# 1. Core Principle

Prompts must be:
explicit
scoped
architecturally constrained
modular
deterministic

Avoid vague implementation requests.

Avoid open-ended prompts that allow uncontrolled architectural interpretation.

---

# 2. Preferred Prompt Structure

Implementation prompts should follow this structure whenever possible:
Objective
Context
Scope
Requirements
Constraints
Deliverables
Forbidden Actions
Validation Expectations

This structure significantly improves implementation quality and reduces token waste.

---

# 3. Objective Section

The objective should define:

* the actual engineering goal
* the business/technical purpose
* expected outcome

Good objective:
Implement synchronized crosshair movement between chart panes.

Bad objective:
Improve charting.

Objectives must be precise.

---

# 4. Context Section

The context section explains:

* where the feature belongs
* relevant architecture assumptions
* existing systems involved
* operational intent

Context should help the implementation agent understand:
why this exists
how it fits into QuantLab
what must remain unchanged

Avoid excessively broad repository summaries.

Only include relevant context.

---

# 5. Scope Definition Rules

Every implementation request must clearly define scope.

Preferred examples:
frontend/charting/
backend/strategy_engine/
backend/data_pipeline/

If multiple modules are affected, explicitly identify them.

Unscoped prompts frequently cause:

* unrelated rewrites
* token explosion
* architecture drift
* overengineering

---

# 6. Requirements Section

Requirements define what must exist after implementation.

Requirements should be:
specific
testable
observable
implementation-relevant

Good requirement:
Support synchronized zoom across all active chart panes.


Bad requirement:
Make charting better.

Requirements should describe behavior, not vague expectations.

---

# 7. Constraints Section

Constraints are critical.

Constraints define:

* architectural boundaries
* forbidden changes
* technology limitations
* compatibility requirements
* performance considerations

Examples:
- Do not modify backend APIs
- Use existing Zustand store
- No new charting libraries
- Preserve existing data contracts
- Do not refactor unrelated modules

Constraints reduce uncontrolled implementation behavior.

---

# 8. Deliverables Section

Prompts should define expected deliverables.

Examples:
- synchronization service
- event bridge
- cleanup hooks
- integration tests
- updated documentation

This improves completion quality and reduces ambiguity.

---

# 9. Forbidden Actions Section

Prompts should explicitly define forbidden behavior.

Examples:
- Do not rewrite chart renderer
- Do not modify strategy contracts
- Do not introduce broker-specific logic
- Do not add new dependencies
- Do not restructure directories

This is especially important for AI implementation agents.

---

# 10. Validation Expectations

Prompts should define how success is evaluated.

Examples:
- Existing charts continue functioning
- Synchronization works across all panes
- No regression in drawing tools
- Existing tests continue passing

Validation expectations improve implementation reliability.

---

# 11. Preferred Communication Style

Use:
clear engineering language
structured instructions
short deterministic statements
explicit constraints

Avoid:
vague requests
motivational language
conversational ambiguity
high-level abstract wishes

Implementation agents perform better with structured operational instructions.

---

# 12. Prompt Size Discipline

Large prompts are not automatically better.

Prefer:
small scoped prompts
modular implementation tasks
focused context

Avoid:
entire project summaries
large duplicated context
massive architecture dumps
loading unnecessary documentation

Token efficiency is a strategic requirement.

---

# 13. Context Loading Rules

Before implementation:

Load only:
- constitutional files
- active task context
- relevant module documentation

Avoid loading:
- entire repository documentation
- unrelated architecture documents
- old research notes
- inactive modules

More context does not always improve implementation quality.

Irrelevant context frequently degrades reasoning.

---

# 14. Multi-Step Implementation Rules

Complex implementation should be decomposed.

Preferred workflow:
Phase 1 → architecture setup
Phase 2 → interfaces/contracts
Phase 3 → implementation
Phase 4 → validation/testing
Phase 5 → optimization/refinement

Avoid asking agents to build entire complex systems in one step.

Large uncontrolled implementation prompts increase:

* hallucination
* architecture drift
* unstable abstractions
* token consumption

---

# 15. Architectural Preservation Rules

Prompts should preserve:
modularity
strategy portability
layer separation
data abstraction
adapter isolation
execution isolation

Prompts must not encourage shortcuts that violate architecture guardrails.

---

# 16. Frontend Prompt Rules

Frontend prompts should emphasize:
visualization
interaction
state management
rendering behavior
UI workflows
performance

Frontend prompts must avoid:
embedding business logic
strategy calculations
execution logic
market normalization

---

# 17. Backend Prompt Rules

Backend prompts should identify:
API scope
service layer responsibilities
contracts/interfaces
data flow
storage behavior

Avoid prompts that allow:
thin routes becoming business layers
strategy execution inside API routes
direct provider coupling

---

# 18. Strategy Prompt Rules

Strategy-related prompts should clearly distinguish:
strategy logic
feature engineering
execution behavior
risk management
backtest behavior

Strategies should remain portable across:
research
backtesting
forward testing
paper trading
future live execution

Do not tightly couple strategies to brokers or execution engines.

---

# 19. Data Pipeline Prompt Rules

Data prompts should specify:
source
normalization requirements
schema expectations
validation rules
storage targets

Avoid exposing raw provider-specific formats directly to strategy layers.

---

# 20. Research Workflow Prompt Rules

Research prompts may include:
experimental indicators
cycle analysis
planetary features
custom feature engineering
pattern discovery
signal exploration

However:

Research prompts must still preserve:
module isolation
reproducibility
clear contracts
controlled experimentation

Experimental logic should not automatically enter production workflows.

---

# 21. Refactoring Prompt Rules

Refactoring prompts must define:
why refactor is needed
expected improvement
compatibility expectations
scope boundaries

Avoid vague prompts like:
clean up the codebase
optimize everything
modernize architecture

These prompts frequently produce uncontrolled rewrites.

---

# 22. Dependency Addition Rules

Prompts requesting new dependencies must explain:
why dependency is needed
what problem it solves
why existing tooling is insufficient

Avoid casual dependency additions.

Dependencies affect:

* architecture
* deployment
* maintainability
* vendor lock-in
* token complexity

---

# 23. AI Agent Response Expectations

Implementation agents should respond with:
- implementation plan
- identified risks
- assumptions
- architectural considerations
- affected modules
- completion summary

Avoid:
hidden assumptions
silent architecture changes
unexplained rewrites

Transparency improves orchestration quality.

---

# 24. Assumption Handling Rules

If requirements are ambiguous, incomplete, overly broad, or not clearly scoped, agents must not immediately modify the codebase.

Agents must first classify the prompt using the following rule:

Clear prompt → proceed with scoped implementation
Partially clear prompt → state assumptions and proceed only with low-risk, reversible work
Unclear prompt → ask clarification before modifying code
High-impact unclear prompt → stop and request confirmation before any code change

Agents must ask for clarification before implementation if the prompt is missing any critical information such as:

* target module or folder
* expected behavior
* affected system boundary
* data contract impact
* API contract impact
* storage impact
* execution/risk impact
* whether the change is experimental or production-facing

Agents may proceed without clarification only when the task is clearly low-risk, such as:

* fixing obvious typo errors
* formatting documentation
* adding comments
* small isolated bug fixes with clear failure evidence
* updating non-critical text

For unclear prompts, agents should respond with:

I need clarification before modifying the codebase.

Please confirm:
1. Objective
2. Target module/folder
3. Expected behavior
4. Constraints
5. Whether code changes are allowed now

Do not silently invent business logic.

Do not infer critical architecture changes without confirmation.

Do not modify code when the instruction could reasonably affect multiple modules unless the scope is confirmed.

---

# 25. Token Efficiency Rules

Token efficiency is an operational requirement.

Preferred:
small focused prompts
modular context retrieval
incremental implementation

Avoid:
repeating large context blocks
reloading entire repository context
asking for entire-system rewrites
massive multi-domain prompts

Good prompt engineering reduces:

* cost
* hallucination
* implementation instability
* architectural drift

---

# 26. Preferred Prompt Characteristics

Good QuantLab prompts are:
precise
modular
constraint-aware
testable
architecturally aligned

Bad prompts are:
vague
overly broad
unconstrained
speculative
architecture-agnostic

---

# 27. Operational Prompt Philosophy

Prompts are not casual requests.

Inside QuantLab, prompts function as:
operational engineering specifications

The repository depends on deterministic communication between:
human operator
orchestration AI
implementation AI

Poor prompt quality directly degrades engineering quality.

---

# 28. Final Instruction to Agents

Do not interpret prompts as permission for uncontrolled implementation.

When implementing:
preserve architecture
preserve modularity
preserve portability
preserve clarity
preserve scope discipline

If uncertain:

* ask for clarification
* minimize assumptions
* prefer smaller scoped implementation
* preserve existing contracts

QuantLab must evolve through controlled engineering discipline, not uncontrolled AI generation.

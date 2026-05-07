# HANDOFF.md
> Project Handoff & Continuity Reference  
> Purpose: Ensure any AI agent or human developer can immediately continue the project with minimal context loss.

---

# 1. Project Overview

## Project Name
[edgelab]

## Project Type
Rule-based automated trading system with:
- Multi-strategy architecture
- Multi-instrument support
- Backtesting engine
- Live execution engine
- Risk management framework
- Charting & analytics platform
- Agentic-AI-assisted development workflow

## Primary Objective
Build a robust, scalable, modular, production-grade automated trading ecosystem that:
- Eliminates discretionary execution
- Converts strategy logic into deterministic rules
- Supports systematic validation
- Supports continuous improvement & iteration
- Preserves architectural consistency across all future developments

## Core Philosophy
- If it cannot be coded, it does not exist
- Strategy rules must be deterministic
- Risk management overrides strategy logic
- All execution must be traceable and auditable
- No hidden logic
- No magic numbers
- Modular > monolithic
- Reusable components first
- Long-term maintainability over short-term speed

## Compliance Constraint
The trading framework must remain halal-compliant:
- No short-selling
- No interest-based mechanics
- No leverage structures violating Shariah principles
- Strategy validation must include compliance screening

---

# 2. Current Project Status

## Current Development Phase
[CURRENT_PHASE]

Examples:
- Architecture Planning
- Directive Design
- Strategy Framework
- Charting Engine
- Backtesting Engine
- Live Trading Integration
- Risk Engine
- Optimization Engine

## Current Active Branch
[BRANCH_NAME]

## Current Priority Task
[TASK_REFERENCE]

## Completion Status
| Module | Status |
|---|---|
| Project Architecture | COMPLETE |
| Directive System | IN_PROGRESS |
| Strategy Engine | NOT_STARTED |
| Charting Platform | PLANNED |
| Backtesting Engine | PLANNED |
| Live Execution Engine | PLANNED |

---

# 3. Required Reading Order

Every incoming AI agent or developer MUST read the following files in sequence before making any changes.

## Mandatory Reading Sequence
1. `README.md`
2. `CLAUDE.md`
3. `CODEX.md`
4. `docs/architecture/system_architecture.md`
5. `docs/architecture/coding_standards.md`
6. `docs/architecture/project_structure.md`
7. `docs/workflow/development_workflow.md`
8. `TASK.md`
9. `REVIEW_CHECKLIST.md`
10. Relevant directive files

---

# 4. Project Architecture Summary

## Backend Stack
- Python
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery

## Frontend Stack
- React
- TypeScript
- TailwindCSS
- TradingView Lightweight Charts
- Zustand / Redux

## Core Principles
- Modular architecture
- Service-oriented design
- Shared utilities
- Strict separation of concerns
- Strong typing where applicable
- Reusable components
- Minimal coupling

---

# 5. Major Architectural Rules

## DO NOT
- Create business logic inside UI components
- Hardcode trading parameters
- Mix strategy logic with execution logic
- Use hidden global states
- Create duplicate utility functions
- Bypass validation layers
- Modify core engine behavior without review
- Introduce discretionary trading logic

## ALWAYS
- Keep logic deterministic
- Create reusable modules
- Add validation layers
- Handle edge cases
- Add logging
- Add error handling
- Maintain auditability
- Keep functions focused and small
- Preserve backward compatibility where possible

---

# 6. Development Workflow

## Standard Workflow
1. Read TASK.md
2. Understand scope
3. Read related directives
4. Review architecture constraints
5. Plan implementation
6. Implement incrementally
7. Self-review
8. Run checklist validation
9. Update documentation
10. Update TASK.md
11. Update HANDOFF.md

---

# 7. Current Known Constraints

## Technical Constraints
- Frontend rendering must remain performant with large datasets
- Waveform/chart rendering expected at high sample rate
- Backtesting engine must support large historical datasets
- Future multi-strategy concurrent execution expected
- Strategy engine must support parameter optimization

## UI/UX Constraints
- TradingView-like interaction experience
- Professional charting workflow
- Technical analysis drawing tools required
- Responsive performance during zoom/pan
- Component-based frontend design

## Risk Constraints
- Capital preservation prioritized
- Risk engine must override strategy engine
- Exposure limits mandatory
- Daily risk caps mandatory

---

# 8. Current Open Problems

List unresolved issues here.

Example:

## Example
### Charting Engine
- Evaluate best drawing layer architecture
- Determine annotation persistence structure
- Optimize large candle rendering

### Backtesting
- Event-driven vs vectorized architecture decision pending

---

# 9. Pending Decisions

| Topic | Status |
|---|---|
| Database schema finalization | PENDING |
| Broker integration selection | PENDING |
| Optimization framework | PENDING |
| Deployment architecture | PENDING |

---

# 10. Coding Standards Summary

## Naming
- Clear semantic naming
- No abbreviations unless industry-standard

## Function Design
- Single responsibility
- Deterministic output
- Small & composable

## Error Handling
- Explicit
- Logged
- Recoverable where possible

## Logging
- Structured logging only
- No print debugging in production

## Comments
- Explain WHY
- Avoid obvious comments

---

# 11. Testing Philosophy

Every major component must support:
- Unit testing
- Integration testing
- Edge-case testing
- Failure testing
- Performance testing

Trading systems additionally require:
- Backtesting validation
- Walk-forward testing
- Monte Carlo robustness testing
- Slippage simulation
- Latency simulation

---

# 12. Agentic AI Responsibilities

## ChatGPT
Role:
- System architect
- Strategy designer
- Workflow planner
- Risk framework designer
- Technical reviewer

## Claude Code
Role:
- Primary implementation agent
- Refactoring
- Code generation
- Integration
- Documentation support

## Human
Role:
- Final authority
- Strategic validation
- Market understanding
- Risk approval
- Production approval

---

# 13. Before Ending Any Session

ALWAYS:
- Update TASK.md
- Update HANDOFF.md
- Update implementation status
- Record unresolved issues
- Record architectural decisions
- Record blockers
- Record next recommended action

---

# 14. Immediate Next Recommended Action

[NEXT_RECOMMENDED_ACTION]

Example:
"Start building the Directive System framework under `/directives/core/`."

---

# 15. Important Reminder

The goal is NOT merely to make the system work.

The goal is to build:
- A scalable framework
- A reusable ecosystem
- A robust trading infrastructure
- A maintainable long-term platform
- A deterministic execution environment
- A professional institutional-grade architecture

Never sacrifice architecture quality for short-term implementation speed.
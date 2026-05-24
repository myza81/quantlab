"""
Semantic Identity — Phase 2O.3.

Stable ID injection for semantic structures.

Design:
- IDs are assigned once (on first PUT) by the service layer; never by the client
- Already-present IDs are never replaced — preserves frontend cursor state
- Legacy semantics (no IDs) are transparently upgraded on save
- Works entirely on model_dump() dicts to avoid N model_validate calls in recursion;
  validates once at the end of inject_ids()
"""
from __future__ import annotations

import uuid

from backend.strategy_registry.semantics import StrategySemantics


def generate_id() -> str:
    """Return a new stable UUID4 string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Internal dict-level helpers (avoids repeated model_validate in recursion)
# ---------------------------------------------------------------------------

def _ensure_condition_ids(node: dict) -> dict:
    if not node.get("condition_id"):
        node["condition_id"] = generate_id()
    return node


def _ensure_group_ids(group: dict) -> dict:
    if not group.get("group_id"):
        group["group_id"] = generate_id()
    updated: list[dict] = []
    for node in group["conditions"]:
        if "conditions" in node:
            updated.append(_ensure_group_ids(node))
        else:
            updated.append(_ensure_condition_ids(node))
    group["conditions"] = updated
    return group


def _ensure_rule_ids(rule: dict) -> dict:
    if not rule.get("rule_id"):
        rule["rule_id"] = generate_id()
    rule["condition_group"] = _ensure_group_ids(rule["condition_group"])
    return rule


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def inject_ids(semantics: StrategySemantics) -> StrategySemantics:
    """
    Walk the full semantics tree and inject stable IDs where missing.

    Already-present IDs are preserved unchanged (idempotent for fully-ID'd trees).
    Returns a new StrategySemantics with all IDs populated.
    Never raises — only fails if the input itself is structurally invalid.
    """
    data = semantics.model_dump()
    data["entry_rules"] = [_ensure_rule_ids(r) for r in data["entry_rules"]]
    data["exit_rules"]  = [_ensure_rule_ids(r) for r in data["exit_rules"]]
    return StrategySemantics.model_validate(data)

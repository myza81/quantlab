"""
Research tool lineage model — RESEARCH-TOOL-LINEAGE-GUARD-1.

Generic, reusable lineage metadata for any versioned research tool in QuantLab.

Design goals:
  - Lightweight dataclass; no database, no heavy dependencies.
  - Every versioned tool execution must produce a ResearchToolLineage.
  - Derived tools (BoS, CHoCH, indicators derived from structure) must declare
    their parent lineage so no analysis silently inherits a different version.
  - parent_lineage is a flat list; deeply nested chains are not required at this stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ResearchToolLineage:
    """
    Lineage metadata for one versioned research tool execution.

    Fields
    ------
    tool_domain      : High-level domain. Examples: "market_structure",
                       "structure_event", "indicator".
    tool_id          : Version-specific identifier matching the registry
                       technical_id. Examples: "minor_structure_v1",
                       "bos_detection", "rsi".
    version_id       : Explicit version token. For engine-versioned tools
                       (market structure) this equals tool_id. For tools with
                       no engine variants this is the tool_id as well.
    human_name       : Human-readable display name.
    lifecycle_status : "production" | "experimental" | "retired".
    implementation_ref: Module path and class/function. Used to trace exactly
                       which code produced this output.
    parent_lineage   : Lineage of tool(s) whose output was consumed as input.
                       Empty for root tools (e.g. structure engines that consume
                       only raw OHLCV).
    config_hash      : Optional stable hash of engine configuration / parameters.
    input_fingerprint: Optional fingerprint of the input data (e.g. candle range).
    output_fingerprint: Optional fingerprint of the output (e.g. point count hash).
    """

    tool_domain:        str
    tool_id:            str
    version_id:         str
    human_name:         str
    lifecycle_status:   str
    implementation_ref: str
    parent_lineage:     list[ResearchToolLineage] = field(default_factory=list)
    config_hash:        Optional[str] = None
    input_fingerprint:  Optional[str] = None
    output_fingerprint: Optional[str] = None

    def with_parent(self, parent: ResearchToolLineage) -> ResearchToolLineage:
        """Return a copy of self with parent appended to parent_lineage."""
        from dataclasses import replace
        return replace(self, parent_lineage=[*self.parent_lineage, parent])

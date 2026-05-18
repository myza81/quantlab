from pydantic import BaseModel, ConfigDict, field_validator

from backend.tools.configuration import ToolConfiguration


class StrategyToolSet(BaseModel):
    """
    An ordered, deterministic collection of configured tool instances.

    Represents the tool configuration layer for a strategy or research workflow.
    Multiple ToolConfiguration objects are grouped under a stable identity,
    preserving insertion order and enforcing instance_id uniqueness within the set.

    Design decisions:
    - Empty toolsets are allowed — building up a toolset incrementally is valid;
      runtime orchestration must enforce non-empty where required.
    - tools is a tuple — immutable ordering, consistent with ToolMetadata.parameters.
    - toolset_id uniqueness is enforced at the collection level, not globally.

    This is NOT an execution engine. It does not invoke tool logic.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    toolset_id: str
    display_name: str | None = None
    tools: tuple[ToolConfiguration, ...]
    enabled: bool = True

    @field_validator("toolset_id")
    @classmethod
    def toolset_id_must_be_valid(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("toolset_id must not be empty or whitespace")
        return v.strip().lower()

    @field_validator("tools")
    @classmethod
    def tools_must_not_have_duplicate_instance_ids(
        cls, v: tuple[ToolConfiguration, ...]
    ) -> tuple[ToolConfiguration, ...]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for tool in v:
            if tool.instance_id in seen:
                duplicates.append(tool.instance_id)
            else:
                seen.add(tool.instance_id)
        if duplicates:
            raise ValueError(
                f"duplicate instance_id(s) in toolset: {sorted(set(duplicates))}"
            )
        return v

    def get_tool(self, instance_id: str) -> ToolConfiguration | None:
        """Return the ToolConfiguration with the given instance_id, or None."""
        key = instance_id.strip().lower()
        for tool in self.tools:
            if tool.instance_id == key:
                return tool
        return None

    def instance_ids(self) -> tuple[str, ...]:
        """Return the ordered tuple of instance_ids in this toolset."""
        return tuple(t.instance_id for t in self.tools)

    def enabled_tools(self) -> tuple[ToolConfiguration, ...]:
        """Return only the tools with enabled=True, preserving order."""
        return tuple(t for t in self.tools if t.enabled)

    def __len__(self) -> int:
        return len(self.tools)

    def __contains__(self, instance_id: object) -> bool:
        if not isinstance(instance_id, str):
            return False
        key = instance_id.strip().lower()
        return any(t.instance_id == key for t in self.tools)

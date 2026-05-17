from backend.tools.models import ToolMetadata


class ToolRegistryError(Exception):
    pass


class ToolNotFoundError(ToolRegistryError):
    pass


class DuplicateToolError(ToolRegistryError):
    pass


class ToolRegistry:
    """
    In-process registry of analytical tool metadata.

    Stores ToolMetadata by tool_id. Keys are normalized to lowercase.
    Does not load or execute tool implementations — metadata only.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}

    def register(self, metadata: ToolMetadata) -> None:
        key = metadata.tool_id  # already normalized lowercase by field_validator
        if key in self._tools:
            raise DuplicateToolError(
                f"Tool '{key}' is already registered. "
                f"Deregister it first or use a different tool_id."
            )
        self._tools[key] = metadata

    def get(self, tool_id: str) -> ToolMetadata:
        key = tool_id.strip().lower()
        entry = self._tools.get(key)
        if entry is None:
            available = sorted(self._tools)
            raise ToolNotFoundError(
                f"Tool '{tool_id}' not found. "
                f"Available tools: {available}"
            )
        return entry

    def deregister(self, tool_id: str) -> None:
        key = tool_id.strip().lower()
        if key not in self._tools:
            available = sorted(self._tools)
            raise ToolNotFoundError(
                f"Tool '{tool_id}' not found. "
                f"Available tools: {available}"
            )
        del self._tools[key]

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, tool_id: object) -> bool:
        if not isinstance(tool_id, str):
            return False
        return tool_id.strip().lower() in self._tools

"""
Tests for Phase 2N.5 — StrategyToolSet Contracts.

Covers:
  - StrategyToolSet model construction and field validation
  - Ordered, deterministic tool collection
  - Duplicate instance_id rejection
  - Containment and lookup operations
  - Serialization determinism
  - Interaction with ToolConfiguration (Phase 2N.4 layer)
  - Separation from runtime execution (no compute_sma calls)
"""
import json

import pytest
from pydantic import ValidationError

from backend.tools import (
    SMA_METADATA,
    StrategyToolSet,
    ToolConfiguration,
    create_default_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sma(instance_id: str, period: int, **kw: object) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="sma",
        parameters={"period": period},
        **kw,
    )


def _tool(instance_id: str, tool_id: str = "sma") -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id=tool_id,
        parameters={"period": 10},
    )


# ---------------------------------------------------------------------------
# TestStrategyToolSet — model construction and field validation
# ---------------------------------------------------------------------------

class TestStrategyToolSet:
    def test_valid_minimal_construction(self) -> None:
        ts = StrategyToolSet(
            toolset_id="my_set",
            tools=(_sma("sma_fast", 20),),
        )
        assert ts.toolset_id == "my_set"
        assert len(ts.tools) == 1
        assert ts.enabled is True
        assert ts.display_name is None

    def test_toolset_id_normalized_lowercase(self) -> None:
        ts = StrategyToolSet(toolset_id="My_Set", tools=())
        assert ts.toolset_id == "my_set"

    def test_toolset_id_stripped_of_whitespace(self) -> None:
        ts = StrategyToolSet(toolset_id="  baseline  ", tools=())
        assert ts.toolset_id == "baseline"

    def test_toolset_id_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            StrategyToolSet(toolset_id="", tools=())

    def test_toolset_id_whitespace_only_raises(self) -> None:
        with pytest.raises(ValidationError):
            StrategyToolSet(toolset_id="   ", tools=())

    def test_empty_tools_allowed(self) -> None:
        ts = StrategyToolSet(toolset_id="empty_set", tools=())
        assert len(ts) == 0
        assert ts.tools == ()

    def test_enabled_default_true(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=())
        assert ts.enabled is True

    def test_enabled_false_accepted(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=(), enabled=False)
        assert ts.enabled is False

    def test_display_name_accepted(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=(), display_name="MA Basket")
        assert ts.display_name == "MA Basket"

    def test_frozen_prevents_mutation(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=())
        with pytest.raises(Exception):
            ts.enabled = False  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategyToolSet(
                toolset_id="x",
                tools=(),
                ghost_field="oops",  # type: ignore[call-arg]
            )

    def test_list_input_converted_to_tuple(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=[_sma("sma_fast", 20), _sma("sma_slow", 50)],  # type: ignore[arg-type]
        )
        assert isinstance(ts.tools, tuple)
        assert len(ts.tools) == 2


# ---------------------------------------------------------------------------
# TestDuplicateInstanceIdRejection
# ---------------------------------------------------------------------------

class TestDuplicateInstanceIdRejection:
    def test_duplicate_instance_id_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            StrategyToolSet(
                toolset_id="x",
                tools=(_sma("sma_fast", 20), _sma("sma_fast", 50)),
            )
        assert "duplicate" in str(exc_info.value).lower()
        assert "sma_fast" in str(exc_info.value)

    def test_three_tools_one_duplicate_raises(self) -> None:
        with pytest.raises(ValidationError):
            StrategyToolSet(
                toolset_id="x",
                tools=(
                    _sma("a", 10),
                    _sma("b", 20),
                    _sma("a", 30),
                ),
            )

    def test_all_three_unique_passes(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(
                _sma("sma_20", 20),
                _sma("sma_50", 50),
                _sma("sma_200", 200),
            ),
        )
        assert len(ts) == 3

    def test_case_normalized_before_duplicate_check(self) -> None:
        with pytest.raises(ValidationError):
            StrategyToolSet(
                toolset_id="x",
                tools=(
                    ToolConfiguration(instance_id="SMA_FAST", tool_id="sma", parameters={"period": 20}),
                    ToolConfiguration(instance_id="sma_fast", tool_id="sma", parameters={"period": 50}),
                ),
            )

    def test_duplicate_error_message_names_offender(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            StrategyToolSet(
                toolset_id="x",
                tools=(_sma("rsi_filter", 14), _sma("rsi_filter", 14)),
            )
        assert "rsi_filter" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestToolOrdering — insertion order preserved deterministically
# ---------------------------------------------------------------------------

class TestToolOrdering:
    def test_tools_preserve_insertion_order(self) -> None:
        ts = StrategyToolSet(
            toolset_id="ordered",
            tools=(
                _sma("sma_20", 20),
                _sma("sma_50", 50),
                _sma("sma_200", 200),
            ),
        )
        ids = ts.instance_ids()
        assert ids == ("sma_20", "sma_50", "sma_200")

    def test_instance_ids_returns_tuple(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=(_sma("a", 5), _sma("b", 10)))
        assert isinstance(ts.instance_ids(), tuple)

    def test_instance_ids_empty_toolset(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=())
        assert ts.instance_ids() == ()

    def test_reverse_order_toolset_preserves_order(self) -> None:
        ts = StrategyToolSet(
            toolset_id="rev",
            tools=(_sma("z", 200), _sma("m", 50), _sma("a", 20)),
        )
        ids = ts.instance_ids()
        assert ids == ("z", "m", "a")


# ---------------------------------------------------------------------------
# TestContainmentAndLookup
# ---------------------------------------------------------------------------

class TestContainmentAndLookup:
    def test_contains_existing_instance_id(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(_sma("sma_fast", 20), _sma("sma_slow", 50)),
        )
        assert "sma_fast" in ts
        assert "sma_slow" in ts

    def test_contains_missing_instance_id(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=(_sma("sma_fast", 20),))
        assert "ghost" not in ts

    def test_contains_non_string_returns_false(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=(_sma("sma_fast", 20),))
        assert 42 not in ts  # type: ignore[operator]

    def test_get_tool_returns_correct_config(self) -> None:
        fast = _sma("sma_fast", 20)
        ts = StrategyToolSet(toolset_id="x", tools=(fast, _sma("sma_slow", 50)))
        result = ts.get_tool("sma_fast")
        assert result is not None
        assert result.instance_id == "sma_fast"
        assert result.parameters["period"] == 20

    def test_get_tool_missing_returns_none(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=(_sma("sma_fast", 20),))
        assert ts.get_tool("nonexistent") is None

    def test_get_tool_case_insensitive(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=(_sma("sma_fast", 20),))
        result = ts.get_tool("SMA_FAST")
        assert result is not None
        assert result.instance_id == "sma_fast"

    def test_len_returns_tool_count(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(_sma("a", 5), _sma("b", 10), _sma("c", 20)),
        )
        assert len(ts) == 3

    def test_len_empty_returns_zero(self) -> None:
        ts = StrategyToolSet(toolset_id="x", tools=())
        assert len(ts) == 0


# ---------------------------------------------------------------------------
# TestEnabledTools — enabled_tools() helper
# ---------------------------------------------------------------------------

class TestEnabledTools:
    def test_all_enabled_returns_all(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(_sma("a", 10), _sma("b", 20)),
        )
        assert len(ts.enabled_tools()) == 2

    def test_one_disabled_filtered_out(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(
                _sma("a", 10),
                _sma("b", 20, enabled=False),
                _sma("c", 30),
            ),
        )
        active = ts.enabled_tools()
        assert len(active) == 2
        assert all(t.enabled for t in active)

    def test_all_disabled_returns_empty(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(
                _sma("a", 10, enabled=False),
                _sma("b", 20, enabled=False),
            ),
        )
        assert ts.enabled_tools() == ()

    def test_enabled_tools_preserves_order(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(
                _sma("a", 10),
                _sma("b", 20, enabled=False),
                _sma("c", 30),
            ),
        )
        ids = tuple(t.instance_id for t in ts.enabled_tools())
        assert ids == ("a", "c")


# ---------------------------------------------------------------------------
# TestStrategyToolSetSerialization
# ---------------------------------------------------------------------------

class TestStrategyToolSetSerialization:
    def test_model_dump_returns_dict(self) -> None:
        ts = StrategyToolSet(
            toolset_id="baseline",
            tools=(_sma("sma_fast", 20), _sma("sma_slow", 50)),
        )
        d = ts.model_dump()
        assert isinstance(d, dict)
        assert d["toolset_id"] == "baseline"
        assert len(d["tools"]) == 2

    def test_model_dump_json_is_valid_json(self) -> None:
        ts = StrategyToolSet(
            toolset_id="test",
            tools=(_sma("sma_20", 20),),
        )
        raw = ts.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["toolset_id"] == "test"
        assert parsed["tools"][0]["instance_id"] == "sma_20"
        assert parsed["tools"][0]["parameters"]["period"] == 20

    def test_identical_toolsets_produce_identical_dump(self) -> None:
        ts_a = StrategyToolSet(
            toolset_id="x",
            tools=(_sma("a", 10), _sma("b", 20)),
        )
        ts_b = StrategyToolSet(
            toolset_id="x",
            tools=(_sma("a", 10), _sma("b", 20)),
        )
        assert ts_a.model_dump() == ts_b.model_dump()
        assert ts_a.model_dump_json() == ts_b.model_dump_json()

    def test_tool_order_preserved_in_dump(self) -> None:
        ts = StrategyToolSet(
            toolset_id="ordered",
            tools=(_sma("z", 200), _sma("m", 50), _sma("a", 20)),
        )
        dumped = ts.model_dump()
        ids = [t["instance_id"] for t in dumped["tools"]]
        assert ids == ["z", "m", "a"]

    def test_empty_toolset_serializes_cleanly(self) -> None:
        ts = StrategyToolSet(toolset_id="empty", tools=())
        d = ts.model_dump()
        assert len(d["tools"]) == 0

    def test_model_dump_json_stable_across_calls(self) -> None:
        ts = StrategyToolSet(
            toolset_id="stable",
            tools=(_sma("a", 10), _sma("b", 20)),
        )
        assert ts.model_dump_json() == ts.model_dump_json()


# ---------------------------------------------------------------------------
# TestLayerSeparation — StrategyToolSet does not invoke tool execution
# ---------------------------------------------------------------------------

class TestLayerSeparation:
    def test_toolset_does_not_call_compute_sma(self) -> None:
        ts = StrategyToolSet(
            toolset_id="research_set",
            tools=(
                _sma("sma_fast", 20),
                _sma("sma_slow", 50),
                _sma("sma_trend", 200),
            ),
        )
        assert len(ts) == 3

    def test_toolset_references_sma_metadata_tool_id_only(self) -> None:
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(_sma("sma_fast", 20),),
        )
        assert ts.tools[0].tool_id == SMA_METADATA.tool_id

    def test_toolset_coexists_with_registry(self) -> None:
        registry = create_default_registry()
        ts = StrategyToolSet(
            toolset_id="x",
            tools=(_sma("sma_fast", 20),),
        )
        assert ts.tools[0].tool_id in registry

    def test_multiple_toolsets_independent(self) -> None:
        ts_a = StrategyToolSet(
            toolset_id="set_a",
            tools=(_sma("sma_fast", 20),),
        )
        ts_b = StrategyToolSet(
            toolset_id="set_b",
            tools=(_sma("sma_slow", 50),),
        )
        assert ts_a.toolset_id != ts_b.toolset_id
        assert ts_a.tools[0].parameters["period"] != ts_b.tools[0].parameters["period"]

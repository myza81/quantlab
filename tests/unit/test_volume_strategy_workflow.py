"""
End-to-end workflow validation for the volume > volume_ma strategy rule.

Covers:
  1.  Toolset validity — both volume and volume_ma in one toolset
  2.  Semantic binding — volume.volume resolves correctly
  3.  Semantic binding — volume_ma.volume_ma resolves correctly
  4.  Semantic binding — full rule valid=True
  5.  Semantic binding — volume_ma.volume is NOT a declared output (contract clean)
  6.  Historical computation — volume output present in bar_outputs
  7.  Historical computation — volume_ma output present in bar_outputs
  8.  Historical computation — volume_ma.volume is NOT in bar_outputs
  9.  Historical computation — condition evaluates correctly bar-by-bar
 10.  Composition run — rule compiles without error
 11.  Composition run — evaluates without unknown-output errors
 12.  Composition run — produces signals on bars where volume > volume_ma
 13.  Composition run — no signals on bars where volume < volume_ma
 14.  Composition run — signals missing before volume_ma warmup (safe, no crash)
 15.  Strategy-run visualization — volume serialized as kind="histogram"
 16.  Strategy-run visualization — volume serialized as pane="price"
 17.  Strategy-run visualization — volume serialized as price_scale="volume"
 18.  Strategy-run visualization — volume_ma serialized as kind="line"
 19.  Strategy-run visualization — volume_ma serialized as price_scale="volume"
 20.  Strategy-run visualization — EMA price_scale is "default" (control case)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.api.schemas.composition_run import CompositionRunBar
from backend.api.services.composition_run_service import run_composition
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.semantic_binding_validator import validate_semantic_bindings
from backend.strategy_registry.semantics import (
    Condition,
    ConditionGroup,
    ConditionOperator,
    EntryRule,
    LogicalOperator,
    OperandKind,
    OperandReference,
    StrategySemantics,
)
from backend.tools import create_default_registry
from backend.tools.configuration import ToolConfiguration
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    build_bar_tool_outputs,
    compute_tool_outputs_for_history,
)
from backend.tools.toolset import StrategyToolSet

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Instance IDs match rule references: "volume.volume" and "volume_ma.volume_ma"
# ---------------------------------------------------------------------------

_VOLUME_CFG = ToolConfiguration(
    instance_id="volume",
    tool_id="volume",
    parameters={},
)

_VOLUME_MA_CFG = ToolConfiguration(
    instance_id="volume_ma",
    tool_id="volume_ma",
    parameters={"ma_length": 3},
)

_TOOLSET = StrategyToolSet(
    toolset_id="vol-workflow-test",
    tools=(_VOLUME_CFG, _VOLUME_MA_CFG),
)

_REGISTRY = create_default_registry()

# ---------------------------------------------------------------------------
# Semantic rule: volume.volume > volume_ma.volume_ma
# ---------------------------------------------------------------------------

_VOLUME_RULE_CONDITION = Condition(
    left     = OperandReference(kind=OperandKind.TOOL_OUTPUT, ref="volume.volume"),
    operator = ConditionOperator.GT,
    right    = OperandReference(kind=OperandKind.TOOL_OUTPUT, ref="volume_ma.volume_ma"),
)

_VOLUME_RULE_SEMANTICS = StrategySemantics(
    entry_rules=(
        EntryRule(
            condition_group=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=(_VOLUME_RULE_CONDITION,),
            ),
        ),
    ),
    exit_rules=(),
)

# ---------------------------------------------------------------------------
# Bars — volume pattern designed for predictable signal production.
#
# ma_length=3 → MA warmup=2 → first MA value at bar index 2.
#
# Index | volume | vol_MA (SMA3)    | volume > vol_MA?
# ------+--------+------------------+-----------------
#   0   |  1000  | n/a (warmup)     | —
#   1   |  2000  | n/a (warmup)     | —
#   2   |  5000  | (1+2+5)K/3=2667  | TRUE  ← signal
#   3   |  4000  | (2+5+4)K/3=3667  | TRUE  ← signal
#   4   |   100  | (5+4+0.1)K/3=3033| FALSE
#   5   |   200  | (4+0.1+0.2)K/3=1433| FALSE
#   6   |   300  | (0.1+0.2+0.3)K/3=200 | TRUE ← signal
# ---------------------------------------------------------------------------

_VOLUMES = [1000.0, 2000.0, 5000.0, 4000.0, 100.0, 200.0, 300.0]

def _make_computation_bars() -> list[ToolComputationBarInput]:
    return [
        ToolComputationBarInput(
            bar_index=i,
            timestamp=_BASE + timedelta(days=i),
            price_fields={
                "open":   100.0, "high": 105.0, "low": 99.0,
                "close":  102.0, "volume": float(v),
            },
        )
        for i, v in enumerate(_VOLUMES)
    ]


def _make_composition_bars() -> list[CompositionRunBar]:
    return [
        CompositionRunBar(
            bar_index=i,
            timestamp=_BASE + timedelta(days=i),
            open=100.0, high=105.0, low=99.0, close=102.0,
            volume=float(v),
        )
        for i, v in enumerate(_VOLUMES)
    ]


def _make_draft(
    semantics: StrategySemantics | None = None,
    extra_tools: tuple[ToolConfiguration, ...] = (),
) -> StrategyDraft:
    tools = (_VOLUME_CFG, _VOLUME_MA_CFG) + extra_tools
    toolset = StrategyToolSet(toolset_id="vol-wf", tools=tools)
    return StrategyDraft(
        draft_id="vol-wf-draft",
        display_name="Volume Workflow Test",
        toolset=toolset,
        semantics=semantics or _VOLUME_RULE_SEMANTICS,
        created_at=_BASE,
        updated_at=_BASE,
    )


def _mock_repo(draft: StrategyDraft) -> MagicMock:
    repo = MagicMock()
    repo.load.return_value = draft
    return repo


def _run(
    semantics: StrategySemantics | None = None,
    extra_tools: tuple[ToolConfiguration, ...] = (),
):
    draft = _make_draft(semantics=semantics, extra_tools=extra_tools)
    return run_composition(
        draft_id="vol-wf-draft",
        symbol="AAPL",
        timeframe="1d",
        bars=_make_composition_bars(),
        repository=_mock_repo(draft),
    )


# ---------------------------------------------------------------------------
# 1. Toolset validity
# ---------------------------------------------------------------------------

class TestVolumeToolsetValidity:
    def test_1_toolset_contains_both_tools(self) -> None:
        ids = set(_TOOLSET.instance_ids())
        assert "volume"    in ids
        assert "volume_ma" in ids

    def test_1b_volume_instance_has_correct_tool_id(self) -> None:
        cfg = _TOOLSET.get_tool("volume")
        assert cfg is not None
        assert cfg.tool_id == "volume"

    def test_1c_volume_ma_instance_has_correct_tool_id(self) -> None:
        cfg = _TOOLSET.get_tool("volume_ma")
        assert cfg is not None
        assert cfg.tool_id == "volume_ma"

    def test_1d_both_tools_registered_in_default_registry(self) -> None:
        assert "volume"    in _REGISTRY
        assert "volume_ma" in _REGISTRY


# ---------------------------------------------------------------------------
# 2–5. Semantic binding validation
# ---------------------------------------------------------------------------

class TestVolumeSemanticBindingValidation:
    def _validate(self, semantics: StrategySemantics) -> object:
        return validate_semantic_bindings(
            semantics, toolset=_TOOLSET, registry=_REGISTRY
        )

    def test_2_volume_volume_ref_resolves(self) -> None:
        result = self._validate(_VOLUME_RULE_SEMANTICS)
        assert "volume.volume" in result.summary.resolved_tool_outputs

    def test_3_volume_ma_volume_ma_ref_resolves(self) -> None:
        result = self._validate(_VOLUME_RULE_SEMANTICS)
        assert "volume_ma.volume_ma" in result.summary.resolved_tool_outputs

    def test_4_full_rule_is_valid(self) -> None:
        result = self._validate(_VOLUME_RULE_SEMANTICS)
        assert result.valid is True
        assert len([d for d in result.diagnostics if d.severity == "error"]) == 0

    def test_5_volume_ma_dot_volume_is_not_a_valid_output(self) -> None:
        # volume_ma.volume was removed from output_feature_names — must now fail binding.
        bad_semantics = StrategySemantics(
            entry_rules=(
                EntryRule(
                    condition_group=ConditionGroup(
                        operator=LogicalOperator.AND,
                        conditions=(
                            Condition(
                                left     = OperandReference(kind=OperandKind.TOOL_OUTPUT, ref="volume_ma.volume"),
                                operator = ConditionOperator.GT,
                                right    = OperandReference(kind=OperandKind.CONSTANT, ref="0"),
                            ),
                        ),
                    ),
                ),
            ),
            exit_rules=(),
        )
        result = self._validate(bad_semantics)
        assert result.valid is False
        unresolved = result.summary.unresolved_tool_outputs
        assert "volume_ma.volume" in unresolved


# ---------------------------------------------------------------------------
# 6–9. Historical computation
# ---------------------------------------------------------------------------

class TestVolumeHistoricalComputation:
    def _compute(self):
        bars = _make_computation_bars()
        return compute_tool_outputs_for_history(_TOOLSET, bars, _REGISTRY)

    def test_6_volume_output_in_bar_outputs(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        # volume tool emits from bar 0 (warmup=0)
        assert "volume.volume" in bar_outputs[0]

    def test_7_volume_ma_output_in_bar_outputs_after_warmup(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        # volume_ma emits from bar 2 (warmup=ma_length-1=2)
        assert "volume_ma.volume_ma" in bar_outputs[2]

    def test_8_volume_ma_dot_volume_not_in_bar_outputs(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        for bar_idx, outputs in bar_outputs.items():
            assert "volume_ma.volume" not in outputs, (
                f"volume_ma.volume must not be a strategy output "
                f"(found at bar {bar_idx})"
            )

    def test_9_condition_evaluates_correctly_per_bar(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)

        # Bar 2: volume=5000, MA=2667 → 5000>2667 TRUE
        assert bar_outputs[2]["volume.volume"]    == pytest.approx(5000.0)
        assert bar_outputs[2]["volume_ma.volume_ma"] == pytest.approx(8000.0 / 3)
        assert bar_outputs[2]["volume.volume"] > bar_outputs[2]["volume_ma.volume_ma"]

        # Bar 4: volume=100, MA=3033 → 100<3033 FALSE
        assert bar_outputs[4]["volume.volume"]    == pytest.approx(100.0)
        assert bar_outputs[4]["volume.volume"] < bar_outputs[4]["volume_ma.volume_ma"]


# ---------------------------------------------------------------------------
# 10–14. Composition run evaluation
# ---------------------------------------------------------------------------

class TestVolumeCompositionRun:
    def test_10_composition_run_compiles_without_error(self) -> None:
        result = _run()
        assert result.error is None

    def test_11_composition_run_status_is_not_failed(self) -> None:
        result = _run()
        assert result.status in ("success", "empty")

    def test_12_signals_produced_on_bars_where_volume_exceeds_ma(self) -> None:
        result = _run()
        # Bar 2 and Bar 3 satisfy volume > volume_ma → at least one signal
        signal_bars = {s.bar_index for s in result.signals if s.signal_type == "long"}
        assert 2 in signal_bars, f"Expected signal at bar 2; signals at {signal_bars}"
        assert 3 in signal_bars, f"Expected signal at bar 3; signals at {signal_bars}"

    def test_13_no_signals_on_bars_where_volume_below_ma(self) -> None:
        result = _run()
        signal_bars = {s.bar_index for s in result.signals if s.signal_type == "long"}
        # Bar 4 and 5: volume < volume_ma → no entry signal
        assert 4 not in signal_bars, f"Unexpected signal at bar 4"
        assert 5 not in signal_bars, f"Unexpected signal at bar 5"

    def test_14_no_crash_before_warmup_bars(self) -> None:
        # Bars 0 and 1 have no volume_ma output yet; evaluator must handle gracefully.
        result = _run()
        # No error should be present; bars 0-1 simply don't satisfy the condition.
        assert result.error is None
        signal_bars = {s.bar_index for s in result.signals if s.signal_type == "long"}
        assert 0 not in signal_bars
        assert 1 not in signal_bars


# ---------------------------------------------------------------------------
# 15–20. Strategy-run visualization metadata
# ---------------------------------------------------------------------------

class TestVolumeStrategyVisualizationMetadata:
    """
    Verify that the composition run serializes volume tool outputs with the
    correct chart rendering metadata so they render on the volume scale, not
    the OHLC price scale.
    """

    def test_15_volume_indicator_kind_is_histogram(self) -> None:
        result = _run()
        vol = [ind for ind in result.indicators if "volume.volume" in ind.name]
        assert vol, "Expected volume indicator series"
        assert all(s.kind == "histogram" for s in vol)

    def test_16_volume_indicator_pane_is_price(self) -> None:
        result = _run()
        vol = [ind for ind in result.indicators if "volume.volume" in ind.name]
        assert all(s.pane == "price" for s in vol)

    def test_17_volume_indicator_price_scale_is_volume(self) -> None:
        result = _run()
        vol = [ind for ind in result.indicators if "volume.volume" in ind.name]
        assert all(s.price_scale == "volume" for s in vol)

    def test_18_volume_ma_indicator_kind_is_line(self) -> None:
        result = _run()
        vma = [ind for ind in result.indicators if "volume_ma.volume_ma" in ind.name]
        assert vma, "Expected volume_ma indicator series"
        assert all(s.kind == "line" for s in vma)

    def test_19_volume_ma_indicator_price_scale_is_volume(self) -> None:
        result = _run()
        vma = [ind for ind in result.indicators if "volume_ma.volume_ma" in ind.name]
        assert all(s.price_scale == "volume" for s in vma)

    def test_20_ema_indicator_price_scale_is_default(self) -> None:
        """Control: EMA overlay must stay on the default price scale."""
        result = _run(
            extra_tools=(
                ToolConfiguration(
                    instance_id="ema20", tool_id="ema",
                    parameters={"period": 20},
                ),
            ),
        )
        ema = [ind for ind in result.indicators if "ema20" in ind.name]
        assert ema, "Expected EMA indicator series"
        assert all(s.price_scale == "default" for s in ema)

    def test_20b_volume_ma_dot_volume_not_in_indicators(self) -> None:
        """volume_ma.volume must not appear as a strategy indicator output."""
        result = _run()
        indicator_names = {ind.name for ind in result.indicators}
        for name in indicator_names:
            assert not name.endswith("volume_ma.volume"), (
                f"volume_ma.volume must not be a strategy indicator; found '{name}'"
            )

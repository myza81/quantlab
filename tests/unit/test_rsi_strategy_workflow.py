"""
End-to-end workflow validation for RSI family strategy rules.

Covers:
  1.   Toolset validity — rsi, rsi_midline, rsi_smoothing in one toolset
  2.   Semantic binding — rsi.rsi resolves correctly
  3.   Semantic binding — rsi_midline.rsi_midline resolves correctly
  4.   Semantic binding — rsi_smoothing.rsi_smoothing resolves correctly
  5.   Semantic binding — rule rsi.rsi > rsi_midline.rsi_midline is valid
  6.   Semantic binding — rule rsi.rsi > rsi_smoothing.rsi_smoothing is valid
  7.   Semantic binding — invalid cross-tool ref rsi_smoothing.rsi fails binding
  8.   Historical computation — rsi output present in bar_outputs after warmup
  9.   Historical computation — rsi_midline output present in bar_outputs immediately
 10.   Historical computation — rsi_smoothing output present in bar_outputs after warmup
 11.   Historical computation — rsi.rsi > rsi_midline.rsi_midline evaluates bar-by-bar
 12.   Historical computation — rsi.rsi > rsi_smoothing.rsi_smoothing evaluates bar-by-bar
 13.   Composition run — rsi > rsi_midline rule compiles without error
 14.   Composition run — rsi > rsi_midline evaluates without unknown-output errors
 15.   Composition run — rsi > rsi_smoothing (SMA) compiles without error
 16.   Composition run — rsi > rsi_smoothing (SMA) evaluates without errors
 17.   Composition run — rsi > rsi_smoothing (EMA) compiles without error
 18.   Composition run — rsi > rsi_smoothing (EMA) evaluates without errors
 19.   Composition run — no crash before rsi warmup bars
 20.   Composition run — no crash before rsi_smoothing warmup bars
 21.   Strategy-run visualization — rsi serialized as pane="oscillator"
 22.   Strategy-run visualization — rsi serialized as kind="line"
 23.   Strategy-run visualization — rsi_midline serialized as pane="oscillator"
 24.   Strategy-run visualization — rsi_midline serialized as kind="line"
 25.   Strategy-run visualization — rsi_smoothing serialized as pane="oscillator"
 26.   Strategy-run visualization — rsi_smoothing serialized as kind="line"
 27.   Strategy-run visualization — none of RSI family on price pane
 28.   Strategy-run visualization — RSI family price_scale is "default" (not "volume")
 29.   Control: SMA overlay stays on price pane with default price_scale
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
_REGISTRY = create_default_registry()

# ---------------------------------------------------------------------------
# Tool configurations — instance IDs match rule references
# ---------------------------------------------------------------------------

_RSI_CFG = ToolConfiguration(
    instance_id="rsi",
    tool_id="rsi",
    parameters={"period": 14},
)

_RSI_MIDLINE_CFG = ToolConfiguration(
    instance_id="rsi_midline",
    tool_id="rsi_midline",
    parameters={"value": 50},
)

_RSI_SMOOTHING_SMA_CFG = ToolConfiguration(
    instance_id="rsi_smoothing",
    tool_id="rsi_smoothing",
    parameters={"period": 14, "smoothing_type": "SMA", "smoothing_length": 14},
)

_RSI_SMOOTHING_EMA_CFG = ToolConfiguration(
    instance_id="rsi_smoothing",
    tool_id="rsi_smoothing",
    parameters={"period": 14, "smoothing_type": "EMA", "smoothing_length": 14},
)

_FULL_TOOLSET = StrategyToolSet(
    toolset_id="rsi-workflow-test",
    tools=(_RSI_CFG, _RSI_MIDLINE_CFG, _RSI_SMOOTHING_SMA_CFG),
)

_MIDLINE_TOOLSET = StrategyToolSet(
    toolset_id="rsi-midline-test",
    tools=(_RSI_CFG, _RSI_MIDLINE_CFG),
)

# ---------------------------------------------------------------------------
# Semantic rules
# ---------------------------------------------------------------------------

def _cond(left_ref: str, right_ref: str) -> Condition:
    return Condition(
        left=OperandReference(kind=OperandKind.TOOL_OUTPUT, ref=left_ref),
        operator=ConditionOperator.GT,
        right=OperandReference(kind=OperandKind.TOOL_OUTPUT, ref=right_ref),
    )


def _semantics(condition: Condition) -> StrategySemantics:
    return StrategySemantics(
        entry_rules=(
            EntryRule(
                condition_group=ConditionGroup(
                    operator=LogicalOperator.AND,
                    conditions=(condition,),
                ),
            ),
        ),
        exit_rules=(),
    )


_RSI_MIDLINE_SEMANTICS = _semantics(_cond("rsi.rsi", "rsi_midline.rsi_midline"))
_RSI_SMOOTHING_SEMANTICS = _semantics(_cond("rsi.rsi", "rsi_smoothing.rsi_smoothing"))

# ---------------------------------------------------------------------------
# Bars — oscillating prices to produce meaningful RSI values.
#
# Price pattern oscillates to produce RSI values that cross above/below 50.
# 60 bars provides enough warmup for period=14 RSI + SMA(14) smoothing
# (total warmup = 14 + 14 - 1 = 27 bars).
# ---------------------------------------------------------------------------

def _oscillating_closes(n: int = 60) -> list[float]:
    """Generate oscillating close prices centered around 100."""
    closes = []
    for i in range(n):
        # Oscillate between 95 and 105 with a period-8 cycle
        closes.append(100.0 + 5.0 * ((i % 8) - 4) / 4)
    return closes


def _make_computation_bars(n: int = 60) -> list[ToolComputationBarInput]:
    closes = _oscillating_closes(n)
    return [
        ToolComputationBarInput(
            bar_index=i,
            timestamp=_BASE + timedelta(days=i),
            price_fields={
                "open":   close - 0.5,
                "high":   close + 1.0,
                "low":    close - 1.0,
                "close":  close,
                "volume": 1000.0,
            },
        )
        for i, close in enumerate(closes)
    ]


def _make_composition_bars(n: int = 60) -> list[CompositionRunBar]:
    closes = _oscillating_closes(n)
    return [
        CompositionRunBar(
            bar_index=i,
            timestamp=_BASE + timedelta(days=i),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1000.0,
        )
        for i, close in enumerate(closes)
    ]


# ---------------------------------------------------------------------------
# Draft + repo helpers
# ---------------------------------------------------------------------------

def _make_draft(
    toolset: StrategyToolSet,
    semantics: StrategySemantics,
    draft_id: str = "rsi-wf-draft",
) -> StrategyDraft:
    return StrategyDraft(
        draft_id=draft_id,
        display_name="RSI Workflow Test",
        toolset=toolset,
        semantics=semantics,
        created_at=_BASE,
        updated_at=_BASE,
    )


def _mock_repo(draft: StrategyDraft) -> MagicMock:
    repo = MagicMock()
    repo.load.return_value = draft
    return repo


def _run(
    toolset: StrategyToolSet,
    semantics: StrategySemantics,
    n_bars: int = 60,
):
    draft = _make_draft(toolset, semantics)
    return run_composition(
        draft_id="rsi-wf-draft",
        symbol="AAPL",
        timeframe="1d",
        bars=_make_composition_bars(n_bars),
        repository=_mock_repo(draft),
    )


# ===========================================================================
# 1. Toolset validity
# ===========================================================================

class TestRSIToolsetValidity:
    def test_1a_toolset_contains_rsi(self) -> None:
        assert "rsi" in set(_FULL_TOOLSET.instance_ids())

    def test_1b_toolset_contains_rsi_midline(self) -> None:
        assert "rsi_midline" in set(_FULL_TOOLSET.instance_ids())

    def test_1c_toolset_contains_rsi_smoothing(self) -> None:
        assert "rsi_smoothing" in set(_FULL_TOOLSET.instance_ids())

    def test_1d_rsi_instance_has_correct_tool_id(self) -> None:
        cfg = _FULL_TOOLSET.get_tool("rsi")
        assert cfg is not None
        assert cfg.tool_id == "rsi"

    def test_1e_rsi_midline_instance_has_correct_tool_id(self) -> None:
        cfg = _FULL_TOOLSET.get_tool("rsi_midline")
        assert cfg is not None
        assert cfg.tool_id == "rsi_midline"

    def test_1f_rsi_smoothing_instance_has_correct_tool_id(self) -> None:
        cfg = _FULL_TOOLSET.get_tool("rsi_smoothing")
        assert cfg is not None
        assert cfg.tool_id == "rsi_smoothing"

    def test_1g_all_three_registered_in_default_registry(self) -> None:
        assert "rsi" in _REGISTRY
        assert "rsi_midline" in _REGISTRY
        assert "rsi_smoothing" in _REGISTRY


# ===========================================================================
# 2–7. Semantic binding validation
# ===========================================================================

class TestRSISemanticBindingValidation:
    def _validate(
        self,
        semantics: StrategySemantics,
        toolset: StrategyToolSet | None = None,
    ):
        return validate_semantic_bindings(
            semantics,
            toolset=toolset or _FULL_TOOLSET,
            registry=_REGISTRY,
        )

    def test_2_rsi_dot_rsi_ref_resolves(self) -> None:
        result = self._validate(_RSI_MIDLINE_SEMANTICS)
        assert "rsi.rsi" in result.summary.resolved_tool_outputs

    def test_3_rsi_midline_dot_rsi_midline_ref_resolves(self) -> None:
        result = self._validate(_RSI_MIDLINE_SEMANTICS, toolset=_MIDLINE_TOOLSET)
        assert "rsi_midline.rsi_midline" in result.summary.resolved_tool_outputs

    def test_4_rsi_smoothing_dot_rsi_smoothing_ref_resolves(self) -> None:
        result = self._validate(_RSI_SMOOTHING_SEMANTICS)
        assert "rsi_smoothing.rsi_smoothing" in result.summary.resolved_tool_outputs

    def test_5_rsi_midline_full_rule_is_valid(self) -> None:
        result = self._validate(_RSI_MIDLINE_SEMANTICS, toolset=_MIDLINE_TOOLSET)
        assert result.valid is True
        errors = [d for d in result.diagnostics if d.severity == "error"]
        assert len(errors) == 0

    def test_6_rsi_smoothing_full_rule_is_valid(self) -> None:
        result = self._validate(_RSI_SMOOTHING_SEMANTICS)
        assert result.valid is True
        errors = [d for d in result.diagnostics if d.severity == "error"]
        assert len(errors) == 0

    def test_7_invalid_cross_tool_ref_fails_binding(self) -> None:
        # rsi_smoothing has no output named "rsi" — only "rsi_smoothing"
        bad_semantics = _semantics(_cond("rsi_smoothing.rsi", "rsi_midline.rsi_midline"))
        result = self._validate(bad_semantics)
        assert result.valid is False
        assert "rsi_smoothing.rsi" in result.summary.unresolved_tool_outputs


# ===========================================================================
# 8–12. Historical computation
# ===========================================================================

class TestRSIHistoricalComputation:
    def _compute(self, toolset: StrategyToolSet | None = None):
        bars = _make_computation_bars(60)
        ts = toolset or _FULL_TOOLSET
        return compute_tool_outputs_for_history(ts, bars, _REGISTRY)

    def test_8_rsi_output_in_bar_outputs_after_warmup(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        # RSI warmup = period = 14, so output starts at bar 14
        assert "rsi.rsi" in bar_outputs[14]

    def test_8b_rsi_not_in_bar_outputs_before_warmup(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        for i in range(14):
            assert "rsi.rsi" not in bar_outputs.get(i, {})

    def test_9_rsi_midline_output_in_bar_outputs_immediately(self) -> None:
        # rsi_midline is a constant — warmup = 0, output starts at bar 0
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        assert "rsi_midline.rsi_midline" in bar_outputs[0]

    def test_9b_rsi_midline_value_is_configured_constant(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        assert bar_outputs[0]["rsi_midline.rsi_midline"] == pytest.approx(50.0)

    def test_10_rsi_smoothing_output_in_bar_outputs_after_warmup(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        # rsi_smoothing warmup = period + smoothing_length - 1 = 14 + 14 - 1 = 27
        assert "rsi_smoothing.rsi_smoothing" in bar_outputs[27]

    def test_10b_rsi_smoothing_not_in_bar_outputs_before_warmup(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        for i in range(27):
            assert "rsi_smoothing.rsi_smoothing" not in bar_outputs.get(i, {})

    def test_11_rsi_midline_condition_evaluates_per_bar(self) -> None:
        result = self._compute(_MIDLINE_TOOLSET)
        bar_outputs = build_bar_tool_outputs(result)
        # After warmup, every bar should have both refs for evaluation
        for bar_idx in range(14, 60):
            assert "rsi.rsi" in bar_outputs[bar_idx]
            assert "rsi_midline.rsi_midline" in bar_outputs[bar_idx]
            # Condition is evaluatable: rsi > 50 or rsi < 50 — both possible
            rsi_val = bar_outputs[bar_idx]["rsi.rsi"]
            midline_val = bar_outputs[bar_idx]["rsi_midline.rsi_midline"]
            assert 0 <= rsi_val <= 100
            assert midline_val == pytest.approx(50.0)

    def test_12_rsi_smoothing_condition_evaluates_per_bar(self) -> None:
        result = self._compute()
        bar_outputs = build_bar_tool_outputs(result)
        # After warmup, both refs should be available
        for bar_idx in range(27, 60):
            assert "rsi.rsi" in bar_outputs[bar_idx]
            assert "rsi_smoothing.rsi_smoothing" in bar_outputs[bar_idx]
            rsi_val = bar_outputs[bar_idx]["rsi.rsi"]
            smoothed = bar_outputs[bar_idx]["rsi_smoothing.rsi_smoothing"]
            assert 0 <= rsi_val <= 100
            assert 0 <= smoothed <= 100


# ===========================================================================
# 13–20. Composition run evaluation
# ===========================================================================

class TestRSICompositionRun:
    def test_13_rsi_midline_rule_compiles_without_error(self) -> None:
        result = _run(_MIDLINE_TOOLSET, _RSI_MIDLINE_SEMANTICS)
        assert result.error is None

    def test_14_rsi_midline_evaluates_without_unknown_output_errors(self) -> None:
        result = _run(_MIDLINE_TOOLSET, _RSI_MIDLINE_SEMANTICS)
        assert result.status in ("success", "empty")

    def test_15_rsi_smoothing_sma_rule_compiles_without_error(self) -> None:
        result = _run(_FULL_TOOLSET, _RSI_SMOOTHING_SEMANTICS)
        assert result.error is None

    def test_16_rsi_smoothing_sma_evaluates_without_errors(self) -> None:
        result = _run(_FULL_TOOLSET, _RSI_SMOOTHING_SEMANTICS)
        assert result.status in ("success", "empty")

    def test_17_rsi_smoothing_ema_rule_compiles_without_error(self) -> None:
        ema_toolset = StrategyToolSet(
            toolset_id="rsi-ema-test",
            tools=(_RSI_CFG, _RSI_MIDLINE_CFG, _RSI_SMOOTHING_EMA_CFG),
        )
        result = _run(ema_toolset, _RSI_SMOOTHING_SEMANTICS)
        assert result.error is None

    def test_18_rsi_smoothing_ema_evaluates_without_errors(self) -> None:
        ema_toolset = StrategyToolSet(
            toolset_id="rsi-ema-test2",
            tools=(_RSI_CFG, _RSI_MIDLINE_CFG, _RSI_SMOOTHING_EMA_CFG),
        )
        result = _run(ema_toolset, _RSI_SMOOTHING_SEMANTICS)
        assert result.status in ("success", "empty")

    def test_19_no_crash_before_rsi_warmup(self) -> None:
        # Bars 0-13 have no rsi output; evaluator must handle gracefully
        result = _run(_MIDLINE_TOOLSET, _RSI_MIDLINE_SEMANTICS)
        assert result.error is None
        # No signals before warmup (bars 0-13)
        signal_bars = {s.bar_index for s in result.signals if s.signal_type == "long"}
        for i in range(14):
            assert i not in signal_bars, f"Unexpected signal at pre-warmup bar {i}"

    def test_20_no_crash_before_rsi_smoothing_warmup(self) -> None:
        # Bars 0-26 have no rsi_smoothing output; evaluator must handle gracefully
        result = _run(_FULL_TOOLSET, _RSI_SMOOTHING_SEMANTICS)
        assert result.error is None
        signal_bars = {s.bar_index for s in result.signals if s.signal_type == "long"}
        for i in range(27):
            assert i not in signal_bars, f"Unexpected signal at pre-warmup bar {i}"

    def test_20b_rsi_midline_signals_only_after_rsi_warmup(self) -> None:
        result = _run(_MIDLINE_TOOLSET, _RSI_MIDLINE_SEMANTICS)
        signal_bars = {s.bar_index for s in result.signals if s.signal_type == "long"}
        # All signals must be at or after bar 14
        for bar in signal_bars:
            assert bar >= 14, f"Signal at bar {bar} before RSI warmup (bar 14)"


# ===========================================================================
# 21–29. Strategy-run visualization metadata
# ===========================================================================

class TestRSIStrategyVisualizationMetadata:
    def _run_full(self):
        # Include all three RSI-family tools plus an SMA control
        toolset = StrategyToolSet(
            toolset_id="rsi-viz-test",
            tools=(
                _RSI_CFG,
                _RSI_MIDLINE_CFG,
                _RSI_SMOOTHING_SMA_CFG,
                ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20}),
            ),
        )
        # Minimal semantics — sufficient to trigger tool computation
        semantics = StrategySemantics(entry_rules=[], exit_rules=[])
        draft = StrategyDraft(
            draft_id="rsi-viz-draft",
            display_name="RSI Viz Test",
            toolset=toolset,
            semantics=semantics,
            created_at=_BASE,
            updated_at=_BASE,
        )
        repo = MagicMock()
        repo.load.return_value = draft
        return run_composition("rsi-viz-draft", "AAPL", "1d", _make_composition_bars(60), repo)

    def test_21_rsi_indicator_pane_is_oscillator(self) -> None:
        result = self._run_full()
        rsi_series = [ind for ind in result.indicators if "rsi.rsi" in ind.name]
        assert rsi_series, "Expected rsi.rsi indicator series"
        assert all(s.pane == "oscillator" for s in rsi_series)

    def test_22_rsi_indicator_kind_is_line(self) -> None:
        result = self._run_full()
        rsi_series = [ind for ind in result.indicators if "rsi.rsi" in ind.name]
        assert all(s.kind == "line" for s in rsi_series)

    def test_23_rsi_midline_indicator_pane_is_oscillator(self) -> None:
        result = self._run_full()
        midline_series = [ind for ind in result.indicators if "rsi_midline" in ind.name]
        assert midline_series, "Expected rsi_midline indicator series"
        assert all(s.pane == "oscillator" for s in midline_series)

    def test_24_rsi_midline_indicator_kind_is_line(self) -> None:
        result = self._run_full()
        midline_series = [ind for ind in result.indicators if "rsi_midline" in ind.name]
        assert all(s.kind == "line" for s in midline_series)

    def test_25_rsi_smoothing_indicator_pane_is_oscillator(self) -> None:
        result = self._run_full()
        smoothing_series = [ind for ind in result.indicators if "rsi_smoothing" in ind.name]
        assert smoothing_series, "Expected rsi_smoothing indicator series"
        assert all(s.pane == "oscillator" for s in smoothing_series)

    def test_26_rsi_smoothing_indicator_kind_is_line(self) -> None:
        result = self._run_full()
        smoothing_series = [ind for ind in result.indicators if "rsi_smoothing" in ind.name]
        assert all(s.kind == "line" for s in smoothing_series)

    def test_27_none_of_rsi_family_on_price_pane(self) -> None:
        result = self._run_full()
        price_names = {ind.name for ind in result.indicators if ind.pane == "price"}
        assert not any("rsi" in name for name in price_names), (
            f"RSI-family indicator on price pane: "
            f"{[n for n in price_names if 'rsi' in n]}"
        )

    def test_28_rsi_family_price_scale_is_default(self) -> None:
        result = self._run_full()
        rsi_family = [
            ind for ind in result.indicators
            if any(x in ind.name for x in ("rsi.rsi", "rsi_midline", "rsi_smoothing"))
        ]
        assert rsi_family, "Expected RSI-family indicator series"
        for s in rsi_family:
            assert s.price_scale == "default", (
                f"Expected price_scale='default' for {s.name}, got '{s.price_scale}'"
            )

    def test_29_sma_overlay_stays_on_price_pane(self) -> None:
        """Control: SMA overlay must not leak to oscillator pane."""
        result = self._run_full()
        sma_series = [ind for ind in result.indicators if "sma20" in ind.name]
        assert sma_series, "Expected SMA indicator series"
        assert all(s.pane == "price" for s in sma_series), (
            f"SMA leaked to oscillator pane: {[s.pane for s in sma_series]}"
        )

"""
Tests for composition run visualization — pane and kind routing (Phase 2T).

Verifies that run_composition derives correct pane and kind from tool registry
metadata for each tool type:

  SMA / EMA  → pane="price",      kind="line"
  RSI        → pane="oscillator", kind="line"
  MACD line  → pane="oscillator", kind="line"
  MACD hist  → pane="oscillator", kind="histogram"

Also covers the IndicatorSeriesKind.histogram enum value added in Phase 2T.

Architecture boundary enforced: composition_run_service must not import from
backend.strategy_runtime, backend.execution, backend.forward_testing, or
backend.backtesting.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.api.schemas.composition_run import CompositionRunBar
from backend.api.services.composition_run_service import run_composition
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.semantics import StrategySemantics
from backend.strategy_runtime.visualization import IndicatorSeriesKind
from backend.tools.configuration import ToolConfiguration
from backend.tools.toolset import StrategyToolSet

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bars(n: int = 40) -> list[CompositionRunBar]:
    """Build n sequential OHLCV bars with a gentle uptrend."""
    return [
        CompositionRunBar(
            bar_index=i,
            timestamp=_BASE + timedelta(days=i),
            open=100.0 + i * 0.5,
            high=101.0 + i * 0.5,
            low=99.5 + i * 0.5,
            close=100.0 + i * 0.5,
            volume=1_000.0,
        )
        for i in range(n)
    ]


def _make_draft(tools: list[ToolConfiguration]) -> StrategyDraft:
    """Draft with given tools and minimal (empty) semantics."""
    toolset = StrategyToolSet(toolset_id="test-toolset", tools=tuple(tools))
    # Empty entry/exit rules compile successfully (with a diagnostic warning).
    semantics = StrategySemantics(entry_rules=[], exit_rules=[])
    return StrategyDraft(
        draft_id="test-draft",
        display_name="Test Draft",
        toolset=toolset,
        semantics=semantics,
        created_at=_BASE,
        updated_at=_BASE,
    )


def _mock_repo(draft: StrategyDraft) -> MagicMock:
    repo = MagicMock()
    repo.load.return_value = draft
    return repo


def _run(tools: list[ToolConfiguration], n_bars: int = 40):
    draft = _make_draft(tools)
    return run_composition("test-draft", "AAPL", "1d", _make_bars(n_bars), _mock_repo(draft))


# ---------------------------------------------------------------------------
# IndicatorSeriesKind.histogram enum
# ---------------------------------------------------------------------------

class TestIndicatorSeriesKindHistogram:
    def test_histogram_value(self) -> None:
        assert IndicatorSeriesKind.histogram.value == "histogram"

    def test_line_value_unchanged(self) -> None:
        assert IndicatorSeriesKind.line.value == "line"

    def test_histogram_and_line_are_distinct(self) -> None:
        assert IndicatorSeriesKind.histogram != IndicatorSeriesKind.line

    def test_histogram_is_string(self) -> None:
        assert isinstance(IndicatorSeriesKind.histogram.value, str)


# ---------------------------------------------------------------------------
# Price-pane indicators: SMA, EMA
# ---------------------------------------------------------------------------

class TestPricePaneRouting:
    def test_sma_pane_is_price(self) -> None:
        result = _run([ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20})])
        sma = [ind for ind in result.indicators if "sma20" in ind.name]
        assert sma, "Expected SMA indicator series"
        assert all(s.pane == "price" for s in sma)

    def test_sma_kind_is_line(self) -> None:
        result = _run([ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20})])
        sma = [ind for ind in result.indicators if "sma20" in ind.name]
        assert all(s.kind == "line" for s in sma)

    def test_ema_pane_is_price(self) -> None:
        result = _run([ToolConfiguration(instance_id="ema20", tool_id="ema", parameters={"period": 20})])
        ema = [ind for ind in result.indicators if "ema20" in ind.name]
        assert ema, "Expected EMA indicator series"
        assert all(s.pane == "price" for s in ema)

    def test_ema_kind_is_line(self) -> None:
        result = _run([ToolConfiguration(instance_id="ema20", tool_id="ema", parameters={"period": 20})])
        ema = [ind for ind in result.indicators if "ema20" in ind.name]
        assert all(s.kind == "line" for s in ema)

    def test_multiple_sma_instances_all_price(self) -> None:
        result = _run([
            ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20}),
            ToolConfiguration(instance_id="sma50", tool_id="sma", parameters={"period": 50}),
        ], n_bars=60)
        price_inds = [ind for ind in result.indicators if ind.pane == "price"]
        # Two SMA instances → two price series
        assert len(price_inds) == 2

    def test_no_price_indicator_produces_oscillator(self) -> None:
        result = _run([ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20})])
        osc = [ind for ind in result.indicators if ind.pane == "oscillator"]
        assert osc == []


# ---------------------------------------------------------------------------
# Oscillator-pane indicators: RSI
# ---------------------------------------------------------------------------

class TestRSIOscillatorRouting:
    def test_rsi_pane_is_oscillator(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="rsi14", tool_id="rsi", parameters={"period": 14})],
            n_bars=20,
        )
        rsi = [ind for ind in result.indicators if "rsi14" in ind.name]
        assert rsi, "Expected RSI indicator series"
        assert all(s.pane == "oscillator" for s in rsi)

    def test_rsi_kind_is_line(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="rsi14", tool_id="rsi", parameters={"period": 14})],
            n_bars=20,
        )
        rsi = [ind for ind in result.indicators if "rsi14" in ind.name]
        assert all(s.kind == "line" for s in rsi)

    def test_rsi_not_on_price_pane(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="rsi14", tool_id="rsi", parameters={"period": 14})],
            n_bars=20,
        )
        price = [ind for ind in result.indicators if ind.pane == "price"]
        assert price == []


# ---------------------------------------------------------------------------
# Oscillator-pane indicators: MACD — three outputs, two kinds
# ---------------------------------------------------------------------------

class TestMACDOscillatorRouting:
    def _macd_result(self):
        # MACD defaults: fast=12, slow=26, signal=9.
        # Signal warmup = 26 + 9 - 2 = 33. Use 40 bars to get all outputs.
        return _run(
            [ToolConfiguration(instance_id="macd1", tool_id="macd", parameters={})],
            n_bars=40,
        )

    def test_all_macd_outputs_on_oscillator_pane(self) -> None:
        result = self._macd_result()
        macd_series = [ind for ind in result.indicators if "macd1" in ind.name]
        assert macd_series, "Expected MACD indicator series"
        assert all(s.pane == "oscillator" for s in macd_series)

    def test_macd_produces_three_series(self) -> None:
        result = self._macd_result()
        macd_series = [ind for ind in result.indicators if "macd1" in ind.name]
        assert len(macd_series) == 3

    def test_macd_line_kind_is_line(self) -> None:
        result = self._macd_result()
        macd_line = [ind for ind in result.indicators if "macd_line" in ind.name]
        assert macd_line, "Expected macd_line series"
        assert all(s.kind == "line" for s in macd_line)

    def test_macd_signal_kind_is_line(self) -> None:
        result = self._macd_result()
        signal = [ind for ind in result.indicators if "signal_line" in ind.name]
        assert signal, "Expected signal_line series"
        assert all(s.kind == "line" for s in signal)

    def test_macd_histogram_kind_is_histogram(self) -> None:
        result = self._macd_result()
        hist = [ind for ind in result.indicators if "histogram" in ind.name]
        assert hist, "Expected histogram series"
        assert all(s.kind == "histogram" for s in hist)

    def test_macd_not_on_price_pane(self) -> None:
        result = self._macd_result()
        price = [ind for ind in result.indicators if ind.pane == "price"]
        assert price == []

    def test_macd_line_not_histogram_kind(self) -> None:
        result = self._macd_result()
        macd_line = [ind for ind in result.indicators if "macd_line" in ind.name]
        assert all(s.kind != "histogram" for s in macd_line)


# ---------------------------------------------------------------------------
# Mixed-tool routing
# ---------------------------------------------------------------------------

class TestMixedToolRouting:
    def test_sma_and_rsi_produce_both_panes(self) -> None:
        result = _run([
            ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20}),
            ToolConfiguration(instance_id="rsi14", tool_id="rsi", parameters={"period": 14}),
        ], n_bars=30)
        panes = {ind.pane for ind in result.indicators}
        assert "price" in panes
        assert "oscillator" in panes

    def test_all_four_tools_produce_six_series(self) -> None:
        # SMA → 1, EMA → 1, RSI → 1, MACD → 3 = 6 series total
        result = _run([
            ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20}),
            ToolConfiguration(instance_id="ema20", tool_id="ema", parameters={"period": 20}),
            ToolConfiguration(instance_id="rsi14", tool_id="rsi", parameters={"period": 14}),
            ToolConfiguration(instance_id="macd1", tool_id="macd", parameters={}),
        ], n_bars=40)
        assert len(result.indicators) == 6

    def test_price_count_is_two_oscillator_count_is_four(self) -> None:
        result = _run([
            ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20}),
            ToolConfiguration(instance_id="ema20", tool_id="ema", parameters={"period": 20}),
            ToolConfiguration(instance_id="rsi14", tool_id="rsi", parameters={"period": 14}),
            ToolConfiguration(instance_id="macd1", tool_id="macd", parameters={}),
        ], n_bars=40)
        price_inds = [ind for ind in result.indicators if ind.pane == "price"]
        osc_inds   = [ind for ind in result.indicators if ind.pane == "oscillator"]
        assert len(price_inds) == 2   # SMA + EMA
        assert len(osc_inds)   == 4   # RSI + macd_line + signal_line + histogram

    def test_no_tools_produces_no_indicators(self) -> None:
        result = _run([], n_bars=10)
        assert result.indicators == []

    def test_all_indicators_have_valid_pane(self) -> None:
        result = _run([
            ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20}),
            ToolConfiguration(instance_id="rsi14", tool_id="rsi", parameters={"period": 14}),
        ], n_bars=30)
        valid_panes = {"price", "oscillator"}
        assert all(ind.pane in valid_panes for ind in result.indicators)

    def test_all_indicators_have_valid_kind(self) -> None:
        result = _run([
            ToolConfiguration(instance_id="sma20", tool_id="sma", parameters={"period": 20}),
            ToolConfiguration(instance_id="macd1", tool_id="macd", parameters={}),
        ], n_bars=40)
        valid_kinds = {"line", "histogram"}
        assert all(ind.kind in valid_kinds for ind in result.indicators)


# ---------------------------------------------------------------------------
# ATR pane/kind routing (Phase 2U)
# ---------------------------------------------------------------------------

class TestATROscillatorRouting:
    def test_atr_pane_is_oscillator(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="atr14", tool_id="atr", parameters={"period": 14})],
            n_bars=20,
        )
        atr = [ind for ind in result.indicators if "atr14" in ind.name]
        assert atr, "Expected ATR indicator series"
        assert all(s.pane == "oscillator" for s in atr)

    def test_atr_kind_is_line(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="atr14", tool_id="atr", parameters={"period": 14})],
            n_bars=20,
        )
        atr = [ind for ind in result.indicators if "atr14" in ind.name]
        assert all(s.kind == "line" for s in atr)

    def test_atr_not_on_price_pane(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="atr14", tool_id="atr", parameters={"period": 14})],
            n_bars=20,
        )
        price = [ind for ind in result.indicators if ind.pane == "price"]
        assert price == []

    def test_atr_produces_one_series(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="atr14", tool_id="atr", parameters={"period": 14})],
            n_bars=20,
        )
        atr = [ind for ind in result.indicators if "atr14" in ind.name]
        assert len(atr) == 1


# ---------------------------------------------------------------------------
# Bollinger Bands pane/kind routing (Phase 2U)
# ---------------------------------------------------------------------------

class TestBollingerPriceRouting:
    def test_bollinger_all_panes_are_price(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="bb20", tool_id="bollinger_bands",
                               parameters={"period": 20})],
            n_bars=30,
        )
        bb = [ind for ind in result.indicators if "bb20" in ind.name]
        assert bb, "Expected Bollinger indicator series"
        assert all(s.pane == "price" for s in bb)

    def test_bollinger_all_kinds_are_line(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="bb20", tool_id="bollinger_bands",
                               parameters={"period": 20})],
            n_bars=30,
        )
        bb = [ind for ind in result.indicators if "bb20" in ind.name]
        assert all(s.kind == "line" for s in bb)

    def test_bollinger_produces_three_series(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="bb20", tool_id="bollinger_bands",
                               parameters={"period": 20})],
            n_bars=30,
        )
        bb = [ind for ind in result.indicators if "bb20" in ind.name]
        assert len(bb) == 3

    def test_bollinger_not_on_oscillator_pane(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="bb20", tool_id="bollinger_bands",
                               parameters={"period": 20})],
            n_bars=30,
        )
        osc = [ind for ind in result.indicators if ind.pane == "oscillator"]
        assert osc == []

    def test_bollinger_output_names(self) -> None:
        result = _run(
            [ToolConfiguration(instance_id="bb20", tool_id="bollinger_bands",
                               parameters={"period": 20})],
            n_bars=30,
        )
        names = {ind.name for ind in result.indicators}
        assert any("middle_band" in n for n in names)
        assert any("upper_band"  in n for n in names)
        assert any("lower_band"  in n for n in names)


# ---------------------------------------------------------------------------
# All-six-tools routing (Phase 2U complete set)
# ---------------------------------------------------------------------------

class TestAllSixToolsRouting:
    def _all_six_result(self):
        # SMA(1)+EMA(1)+RSI(1)+MACD(3)+ATR(1)+Bollinger(3) = 10 series total
        # Use 50 bars: MACD needs 26+9-2=33, ATR needs 14, Bollinger needs 19
        return _run([
            ToolConfiguration(instance_id="sma20",  tool_id="sma",            parameters={"period": 20}),
            ToolConfiguration(instance_id="ema20",  tool_id="ema",            parameters={"period": 20}),
            ToolConfiguration(instance_id="rsi14",  tool_id="rsi",            parameters={"period": 14}),
            ToolConfiguration(instance_id="macd1",  tool_id="macd",           parameters={}),
            ToolConfiguration(instance_id="atr14",  tool_id="atr",            parameters={"period": 14}),
            ToolConfiguration(instance_id="bb20",   tool_id="bollinger_bands", parameters={"period": 20}),
        ], n_bars=50)

    def test_total_series_count_is_ten(self) -> None:
        result = self._all_six_result()
        assert len(result.indicators) == 10

    def test_price_pane_count_is_five(self) -> None:
        result = self._all_six_result()
        price = [ind for ind in result.indicators if ind.pane == "price"]
        # SMA + EMA + BB(middle+upper+lower) = 5
        assert len(price) == 5

    def test_oscillator_pane_count_is_five(self) -> None:
        result = self._all_six_result()
        osc = [ind for ind in result.indicators if ind.pane == "oscillator"]
        # RSI + MACD(line+signal+hist) + ATR = 5
        assert len(osc) == 5

    def test_no_histogram_kind_from_new_tools(self) -> None:
        result = self._all_six_result()
        # Only MACD histogram is kind="histogram"; ATR and Bollinger are all "line"
        hist = [ind for ind in result.indicators
                if ind.kind == "histogram" and "macd" not in ind.name.lower()]
        assert hist == []

    def test_all_valid_panes_and_kinds(self) -> None:
        result = self._all_six_result()
        valid_panes = {"price", "oscillator"}
        valid_kinds = {"line", "histogram"}
        assert all(ind.pane in valid_panes for ind in result.indicators)
        assert all(ind.kind in valid_kinds for ind in result.indicators)


# ---------------------------------------------------------------------------
# Architecture guard
# ---------------------------------------------------------------------------

class TestCompositionRunVisualizationArchitecture:
    def test_no_forbidden_imports_in_composition_run_service(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path("backend/api/services/composition_run_service.py").read_text()
        tree = ast.parse(src)
        forbidden = {"backend.strategy_runtime", "backend.execution",
                     "backend.forward_testing", "backend.backtesting"}

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = (
                    node.names[0].name if isinstance(node, ast.Import)
                    else (node.module or "")
                )
                for f in forbidden:
                    assert f not in module, (
                        f"Forbidden import '{f}' found in composition_run_service.py"
                    )

    def test_visualization_capability_from_tools_not_strategy_runtime(self) -> None:
        # VisualizationCapability must come from backend.tools.models, not strategy_runtime
        import ast
        import pathlib

        src = pathlib.Path("backend/api/services/composition_run_service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [alias.name for alias in node.names]
                if "VisualizationCapability" in names:
                    assert "tools" in node.module, (
                        "VisualizationCapability must be imported from backend.tools.models"
                    )

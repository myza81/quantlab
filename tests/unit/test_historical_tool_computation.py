"""
Phase 2R.0 — Historical Tool Computation Pipeline tests.

Coverage:
    ToolOutputPoint / ToolOutputSeries / ToolComputationResult — output contracts
    ToolComputationBarInput — input model
    ToolComputationError — error type
    compute_tool_outputs_for_history() — full pipeline
    build_bar_tool_outputs() — bar-indexed dict converter
    SMA computation — correctness, warmup, no-lookahead, multi-instance
    evaluate_history_from_payload() — toolset integration path
    POST /semantics/evaluate-history — API integration with toolset
    Backward compatibility — manual tool_outputs path unchanged
    Ambiguity rejection — toolset + manual tool_outputs
    Architecture boundary — HistoricalEvaluationRequest.toolset field
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.schemas.historical_evaluation import (
    HistoricalBarPayload,
    HistoricalEvaluationRequest,
)
from backend.api.services.historical_evaluation_service import (
    HistoricalEvaluationError,
    evaluate_history_from_payload,
)
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools import (
    ToolComputationResult,
    build_bar_tool_outputs,
    compute_tool_outputs_for_history,
    create_default_registry,
)
from backend.tools.computation_models import (
    ToolComputationResult,
    ToolOutputPoint,
    ToolOutputSeries,
)
from backend.tools.configuration import ToolConfiguration
from backend.tools.historical_computation import (
    ToolComputationBarInput,
    ToolComputationError,
)
from backend.tools.toolset import StrategyToolSet

_CLIENT = TestClient(app)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _sma_config(instance_id: str, period: int, enabled: bool = True) -> ToolConfiguration:
    return ToolConfiguration(
        instance_id=instance_id,
        tool_id="sma",
        parameters={"period": period},
        enabled=enabled,
    )


def _toolset(*configs: ToolConfiguration, toolset_id: str = "ts1") -> StrategyToolSet:
    return StrategyToolSet(toolset_id=toolset_id, tools=tuple(configs))


def _bar_input(bar_index: int, close: float) -> ToolComputationBarInput:
    return ToolComputationBarInput(bar_index=bar_index, price_fields={"close": close})


def _bar_payload(bar_index: int, close: float, tool_outputs: dict | None = None) -> HistoricalBarPayload:
    return HistoricalBarPayload(
        bar_index=bar_index,
        price_fields={"close": close},
        tool_outputs=tool_outputs or {},
    )


_REGISTRY = create_default_registry()

# Simple SMA-above-threshold semantics for integration tests
_SMA_ABOVE_SEMANTICS = {
    "entry_rules": [{
        "rule_id": "r1",
        "label": "SMA above 100",
        "condition_group": {
            "group_id": "g1",
            "operator": "AND",
            "conditions": [{
                "condition_id": "c1",
                "label": None,
                "left":  {"kind": "tool_output", "ref": "sma_fast.sma"},
                "operator": ">",
                "right": {"kind": "constant", "ref": "100"},
            }],
        },
    }],
    "exit_rules": [],
}


# ===========================================================================
# ToolOutputPoint
# ===========================================================================

class TestToolOutputPoint:
    def test_basic_creation(self):
        pt = ToolOutputPoint(bar_index=0, timestamp=None, value=42.5)
        assert pt.bar_index == 0
        assert pt.value == 42.5
        assert pt.timestamp is None

    def test_frozen(self):
        pt = ToolOutputPoint(bar_index=0, timestamp=None, value=1.0)
        with pytest.raises(Exception):
            pt.value = 2.0  # type: ignore[misc]

    def test_negative_value_allowed(self):
        pt = ToolOutputPoint(bar_index=5, timestamp=None, value=-3.14)
        assert pt.value == -3.14


# ===========================================================================
# ToolOutputSeries
# ===========================================================================

class TestToolOutputSeries:
    def _make_series(self, instance_id="sma_fast", output_name="sma"):
        pts = (
            ToolOutputPoint(bar_index=2, timestamp=None, value=101.0),
            ToolOutputPoint(bar_index=3, timestamp=None, value=102.0),
        )
        return ToolOutputSeries(
            instance_id=instance_id,
            tool_id="sma",
            output_name=output_name,
            warmup_bar_count=2,
            points=pts,
        )

    def test_output_ref(self):
        s = self._make_series("sma_fast", "sma")
        assert s.output_ref == "sma_fast.sma"

    def test_output_ref_custom_name(self):
        s = self._make_series("my_tool", "value")
        assert s.output_ref == "my_tool.value"

    def test_warmup_bar_count(self):
        s = self._make_series()
        assert s.warmup_bar_count == 2

    def test_points_ordered_by_construction(self):
        s = self._make_series()
        assert s.points[0].bar_index == 2
        assert s.points[1].bar_index == 3

    def test_frozen(self):
        s = self._make_series()
        with pytest.raises(Exception):
            s.output_name = "other"  # type: ignore[misc]


# ===========================================================================
# ToolComputationResult
# ===========================================================================

class TestToolComputationResult:
    def test_basic(self):
        r = ToolComputationResult(toolset_id="ts1", total_bars=5, series=())
        assert r.toolset_id == "ts1"
        assert r.total_bars == 5
        assert r.series == ()

    def test_frozen(self):
        r = ToolComputationResult(toolset_id="ts1", total_bars=5, series=())
        with pytest.raises(Exception):
            r.total_bars = 10  # type: ignore[misc]


# ===========================================================================
# ToolComputationBarInput
# ===========================================================================

class TestToolComputationBarInput:
    def test_basic(self):
        b = ToolComputationBarInput(bar_index=3, price_fields={"close": 105.0})
        assert b.bar_index == 3
        assert b.price_fields["close"] == 105.0

    def test_frozen(self):
        b = ToolComputationBarInput(bar_index=0, price_fields={"close": 1.0})
        with pytest.raises(Exception):
            b.bar_index = 99  # type: ignore[misc]

    def test_extra_price_fields_allowed(self):
        b = ToolComputationBarInput(
            bar_index=0,
            price_fields={"close": 100.0, "open": 99.0, "high": 101.0}
        )
        assert "open" in b.price_fields


# ===========================================================================
# SMA computation — correctness
# ===========================================================================

class TestSmaComputationCorrectness:
    def _run_sma(self, period: int, closes: list[float]) -> list[float]:
        bars = [_bar_input(i, c) for i, c in enumerate(closes)]
        cfg = _sma_config("s1", period)
        toolset = _toolset(cfg)
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 1
        return [p.value for p in result.series[0].points]

    def test_period_1_returns_each_close(self):
        closes = [10.0, 20.0, 30.0]
        values = self._run_sma(1, closes)
        assert values == pytest.approx([10.0, 20.0, 30.0])

    def test_period_3_warmup_skips_first_2(self):
        closes = [10.0, 20.0, 30.0, 40.0]
        values = self._run_sma(3, closes)
        # bar 0, 1 are warmup; bar 2 → (10+20+30)/3=20; bar 3 → (20+30+40)/3=30
        assert len(values) == 2
        assert values[0] == pytest.approx(20.0)
        assert values[1] == pytest.approx(30.0)

    def test_period_5_on_5_bars(self):
        closes = [100.0, 102.0, 104.0, 106.0, 108.0]
        values = self._run_sma(5, closes)
        assert len(values) == 1
        assert values[0] == pytest.approx(sum(closes) / 5)

    def test_period_2_sliding_window(self):
        closes = [1.0, 3.0, 5.0, 7.0]
        values = self._run_sma(2, closes)
        assert values == pytest.approx([2.0, 4.0, 6.0])

    def test_deterministic_same_result_on_repeat(self):
        closes = [10.0, 20.0, 30.0, 40.0, 50.0]
        v1 = self._run_sma(3, closes)
        v2 = self._run_sma(3, closes)
        assert v1 == v2

    def test_all_identical_closes(self):
        closes = [50.0] * 10
        values = self._run_sma(5, closes)
        assert all(v == pytest.approx(50.0) for v in values)


# ===========================================================================
# SMA warmup behavior
# ===========================================================================

class TestSmaWarmup:
    def test_warmup_count_is_period_minus_1(self):
        bars = [_bar_input(i, float(i + 1)) for i in range(5)]
        result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 3)), bars, _REGISTRY
        )
        assert result.series[0].warmup_bar_count == 2

    def test_warmup_bars_absent_from_build_output(self):
        bars = [_bar_input(i, 100.0) for i in range(5)]
        result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 3)), bars, _REGISTRY
        )
        bar_outputs = build_bar_tool_outputs(result)
        # period=3 → warmup=2, so bars 0,1 must be absent
        assert 0 not in bar_outputs
        assert 1 not in bar_outputs
        # bars 2,3,4 must be present
        assert 2 in bar_outputs
        assert 3 in bar_outputs
        assert 4 in bar_outputs

    def test_period_1_has_zero_warmup(self):
        bars = [_bar_input(i, 100.0) for i in range(3)]
        result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 1)), bars, _REGISTRY
        )
        assert result.series[0].warmup_bar_count == 0
        bar_outputs = build_bar_tool_outputs(result)
        assert 0 in bar_outputs

    def test_only_warmup_bars_gives_empty_bar_outputs(self):
        # period=5 but only 4 bars → all warmup
        bars = [_bar_input(i, 100.0) for i in range(4)]
        result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 5)), bars, _REGISTRY
        )
        bar_outputs = build_bar_tool_outputs(result)
        assert bar_outputs == {}


# ===========================================================================
# No-lookahead guarantee
# ===========================================================================

class TestNoLookahead:
    def test_bar_index_matches_input_bar_index(self):
        # bars with non-sequential indices to confirm mapping
        bars = [
            ToolComputationBarInput(bar_index=10, price_fields={"close": 100.0}),
            ToolComputationBarInput(bar_index=11, price_fields={"close": 102.0}),
            ToolComputationBarInput(bar_index=12, price_fields={"close": 104.0}),
        ]
        result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 2)), bars, _REGISTRY
        )
        bar_outputs = build_bar_tool_outputs(result)
        assert 10 not in bar_outputs       # warmup
        assert bar_outputs[11]["s.sma"] == pytest.approx(101.0)  # (100+102)/2
        assert bar_outputs[12]["s.sma"] == pytest.approx(103.0)  # (102+104)/2

    def test_unsorted_input_gives_same_result_as_sorted(self):
        closes = [10.0, 20.0, 30.0, 40.0]
        bars_sorted   = [_bar_input(i, c) for i, c in enumerate(closes)]
        bars_reversed = list(reversed(bars_sorted))
        toolset = _toolset(_sma_config("s", 2))
        r1 = compute_tool_outputs_for_history(toolset, bars_sorted,   _REGISTRY)
        r2 = compute_tool_outputs_for_history(toolset, bars_reversed, _REGISTRY)
        v1 = [p.value for p in r1.series[0].points]
        v2 = [p.value for p in r2.series[0].points]
        assert v1 == pytest.approx(v2)


# ===========================================================================
# Multi-instance support
# ===========================================================================

class TestMultiInstance:
    def test_two_sma_instances_produce_two_series(self):
        bars = [_bar_input(i, float(100 + i)) for i in range(10)]
        toolset = _toolset(_sma_config("sma_fast", 3), _sma_config("sma_slow", 5))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 2
        refs = {s.output_ref for s in result.series}
        assert "sma_fast.sma" in refs
        assert "sma_slow.sma" in refs

    def test_two_instances_different_warmup(self):
        bars = [_bar_input(i, 100.0) for i in range(10)]
        toolset = _toolset(_sma_config("f", 3), _sma_config("s", 5))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        series_by_id = {s.instance_id: s for s in result.series}
        assert series_by_id["f"].warmup_bar_count == 2
        assert series_by_id["s"].warmup_bar_count == 4

    def test_build_bar_tool_outputs_merges_both_series(self):
        bars = [_bar_input(i, float(100 + i)) for i in range(8)]
        toolset = _toolset(_sma_config("fast", 2), _sma_config("slow", 4))
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        bar_outputs = build_bar_tool_outputs(result)
        # At bar 3, both fast (warmup=1) and slow (warmup=3) should be present
        assert "fast.sma" in bar_outputs[3]
        assert "slow.sma" in bar_outputs[3]

    def test_disabled_tool_excluded(self):
        bars = [_bar_input(i, 100.0) for i in range(5)]
        enabled  = _sma_config("active",   3, enabled=True)
        disabled = _sma_config("inactive", 3, enabled=False)
        toolset = _toolset(enabled, disabled)
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert len(result.series) == 1
        assert result.series[0].instance_id == "active"


# ===========================================================================
# build_bar_tool_outputs
# ===========================================================================

class TestBuildBarToolOutputs:
    def test_ref_key_format(self):
        bars = [_bar_input(i, 100.0) for i in range(3)]
        result = compute_tool_outputs_for_history(
            _toolset(_sma_config("my_sma", 1)), bars, _REGISTRY
        )
        bar_outputs = build_bar_tool_outputs(result)
        assert "my_sma.sma" in bar_outputs[0]

    def test_empty_result_gives_empty_dict(self):
        result = ToolComputationResult(toolset_id="ts", total_bars=0, series=())
        assert build_bar_tool_outputs(result) == {}

    def test_total_bars_reflects_input_count(self):
        bars = [_bar_input(i, 100.0) for i in range(7)]
        result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 2)), bars, _REGISTRY
        )
        assert result.total_bars == 7


# ===========================================================================
# Error cases
# ===========================================================================

class TestComputationErrors:
    def test_duplicate_bar_index_raises(self):
        bars = [
            _bar_input(0, 100.0),
            _bar_input(0, 101.0),
        ]
        with pytest.raises(ToolComputationError, match="duplicate bar_index"):
            compute_tool_outputs_for_history(
                _toolset(_sma_config("s", 2)), bars, _REGISTRY
            )

    def test_unknown_tool_id_raises(self):
        bars = [_bar_input(i, 100.0) for i in range(5)]
        cfg = ToolConfiguration(
            instance_id="bad",
            tool_id="unknown_tool_xyz",
            parameters={"period": 3},
        )
        with pytest.raises(ToolComputationError, match="not found in registry"):
            compute_tool_outputs_for_history(_toolset(cfg), bars, _REGISTRY)

    def test_missing_close_field_raises(self):
        bars = [
            ToolComputationBarInput(bar_index=0, price_fields={"open": 100.0}),
            ToolComputationBarInput(bar_index=1, price_fields={"open": 101.0}),
        ]
        with pytest.raises(ToolComputationError, match="missing 'close'"):
            compute_tool_outputs_for_history(
                _toolset(_sma_config("s", 2)), bars, _REGISTRY
            )

    def test_empty_toolset_returns_empty_result(self):
        bars = [_bar_input(i, 100.0) for i in range(5)]
        toolset = StrategyToolSet(toolset_id="empty", tools=())
        result = compute_tool_outputs_for_history(toolset, bars, _REGISTRY)
        assert result.series == ()
        assert result.total_bars == 5

    def test_empty_bars_returns_zero_total(self):
        result = compute_tool_outputs_for_history(
            _toolset(_sma_config("s", 3)), [], _REGISTRY
        )
        assert result.total_bars == 0
        assert result.series[0].points == ()


# ===========================================================================
# Service layer — toolset integration path
# ===========================================================================

class TestServiceToolsetPath:
    def _semantics(self) -> StrategySemantics:
        from backend.strategy_registry.semantics import StrategySemantics
        import json
        return StrategySemantics.model_validate(_SMA_ABOVE_SEMANTICS)

    def _bars_above(self, n: int = 5) -> list[HistoricalBarPayload]:
        return [_bar_payload(i, 110.0) for i in range(n)]

    def test_toolset_path_resolves_sma(self):
        sem = self._semantics()
        bars = self._bars_above(5)
        toolset = _toolset(_sma_config("sma_fast", 2))
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        # bars 0 is warmup, bars 1-4 should trigger (SMA(110,110)=110 > 100)
        assert result.bars_evaluated == 5

    def test_warmup_bars_produce_none_outcome(self):
        sem = self._semantics()
        bars = [_bar_payload(i, 110.0) for i in range(5)]
        toolset = _toolset(_sma_config("sma_fast", 3))  # warmup=2
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        traces = {t.bar_index: t for t in result.bar_results}
        # bars 0,1 are warmup — entry outcome must be None (indeterminate)
        assert traces[0].entry_triggered is None
        assert traces[1].entry_triggered is None
        # bar 2 onward: SMA(110)=110 > 100 → triggered
        assert traces[2].entry_triggered is True

    def test_sma_below_threshold_not_triggered(self):
        sem = self._semantics()
        bars = [_bar_payload(i, 90.0) for i in range(5)]  # close=90 → SMA=90
        toolset = _toolset(_sma_config("sma_fast", 2))
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        traces = {t.bar_index: t for t in result.bar_results}
        # bar 1+ should be False (90 < 100)
        assert traces[1].entry_triggered is False
        assert traces[4].entry_triggered is False

    def test_ambiguity_rejection_raises(self):
        sem = self._semantics()
        bars = [
            _bar_payload(0, 110.0, tool_outputs={"sma_fast.sma": 110.0}),
            _bar_payload(1, 110.0),
        ]
        toolset = _toolset(_sma_config("sma_fast", 2))
        with pytest.raises(HistoricalEvaluationError, match="Ambiguous"):
            evaluate_history_from_payload(sem, bars, toolset=toolset)


# ===========================================================================
# Backward compatibility — manual tool_outputs path
# ===========================================================================

class TestBackwardCompatibility:
    def _manual_semantics(self) -> dict:
        return {
            "entry_rules": [{
                "rule_id": "r1",
                "label": "SMA above threshold",
                "condition_group": {
                    "group_id": "g1",
                    "operator": "AND",
                    "conditions": [{
                        "condition_id": "c1",
                        "label": None,
                        "left":  {"kind": "tool_output", "ref": "sma_fast.sma"},
                        "operator": ">",
                        "right": {"kind": "constant", "ref": "100"},
                    }],
                },
            }],
            "exit_rules": [],
        }

    def test_manual_tool_outputs_still_work(self):
        sem = StrategySemantics.model_validate(self._manual_semantics())
        bars = [
            _bar_payload(0, 110.0, tool_outputs={"sma_fast.sma": 105.0}),
            _bar_payload(1, 110.0, tool_outputs={"sma_fast.sma": 115.0}),
        ]
        result = evaluate_history_from_payload(sem, bars, toolset=None)
        traces = {t.bar_index: t for t in result.bar_results}
        assert traces[0].entry_triggered is True   # 105 > 100
        assert traces[1].entry_triggered is True   # 115 > 100

    def test_toolset_none_is_default(self):
        sem = StrategySemantics.model_validate({
            "entry_rules": [{
                "rule_id": "r1", "label": "close > 50",
                "condition_group": {"group_id": "g1", "operator": "AND", "conditions": [{
                    "condition_id": "c1", "label": None,
                    "left": {"kind": "price", "ref": "close"},
                    "operator": ">",
                    "right": {"kind": "constant", "ref": "50"},
                }]},
            }],
            "exit_rules": [],
        })
        bars = [_bar_payload(0, 60.0), _bar_payload(1, 40.0)]
        result = evaluate_history_from_payload(sem, bars)  # no toolset kwarg
        traces = {t.bar_index: t for t in result.bar_results}
        assert traces[0].entry_triggered is True
        assert traces[1].entry_triggered is False


# ===========================================================================
# API integration — POST /semantics/evaluate-history with toolset
# ===========================================================================

class TestApiToolsetIntegration:
    def _req(self, bars: list[dict], toolset: dict | None = None) -> dict:
        payload: dict = {"semantics": _SMA_ABOVE_SEMANTICS, "bars": bars}
        if toolset is not None:
            payload["toolset"] = toolset
        return payload

    def _bar(self, idx: int, close: float) -> dict:
        return {"bar_index": idx, "price_fields": {"close": close}, "tool_outputs": {}}

    def _sma_toolset_payload(self, instance_id: str, period: int) -> dict:
        return {
            "toolset_id": "ts1",
            "tools": [{
                "instance_id": instance_id,
                "tool_id": "sma",
                "parameters": {"period": period},
            }],
        }

    def test_toolset_provided_200(self):
        bars = [self._bar(i, 110.0) for i in range(5)]
        payload = self._req(bars, toolset=self._sma_toolset_payload("sma_fast", 2))
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 200

    def test_toolset_warmup_bars_null_outcome(self):
        bars = [self._bar(i, 110.0) for i in range(5)]
        payload = self._req(bars, toolset=self._sma_toolset_payload("sma_fast", 3))
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        by_index = {r["bar_index"]: r for r in data["bar_results"]}
        # warmup bars 0,1 → entry_triggered=None
        assert by_index[0]["entry_triggered"] is None
        assert by_index[1]["entry_triggered"] is None
        assert by_index[2]["entry_triggered"] is True

    def test_toolset_sma_below_threshold_not_triggered(self):
        bars = [self._bar(i, 90.0) for i in range(4)]
        payload = self._req(bars, toolset=self._sma_toolset_payload("sma_fast", 2))
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        by_index = {r["bar_index"]: r for r in data["bar_results"]}
        assert by_index[1]["entry_triggered"] is False
        assert by_index[3]["entry_triggered"] is False

    def test_ambiguity_rejected_422(self):
        bars = [
            {"bar_index": 0, "price_fields": {"close": 110.0}, "tool_outputs": {"sma_fast.sma": 110.0}},
            {"bar_index": 1, "price_fields": {"close": 110.0}, "tool_outputs": {}},
        ]
        payload = self._req(bars, toolset=self._sma_toolset_payload("sma_fast", 2))
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 422

    def test_no_toolset_backward_compat_200(self):
        bars = [
            {"bar_index": 0, "price_fields": {"close": 60.0}, "tool_outputs": {}},
        ]
        payload = {
            "semantics": {
                "entry_rules": [{
                    "rule_id": "r1", "label": "close > 50",
                    "condition_group": {"group_id": "g1", "operator": "AND", "conditions": [{
                        "condition_id": "c1", "label": None,
                        "left": {"kind": "price", "ref": "close"},
                        "operator": ">",
                        "right": {"kind": "constant", "ref": "50"},
                    }]},
                }],
                "exit_rules": [],
            },
            "bars": bars,
        }
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 200

    def test_extra_fields_rejected(self):
        payload = self._req([], toolset=None)
        payload["unknown_field"] = "value"
        resp = _CLIENT.post("/semantics/evaluate-history", json=payload)
        assert resp.status_code == 422


# ===========================================================================
# HistoricalEvaluationRequest schema
# ===========================================================================

class TestHistoricalEvaluationRequestSchema:
    def test_toolset_field_optional_defaults_none(self):
        req = HistoricalEvaluationRequest.model_validate({
            "semantics": _SMA_ABOVE_SEMANTICS,
            "bars": [],
        })
        assert req.toolset is None

    def test_toolset_field_accepted(self):
        req = HistoricalEvaluationRequest.model_validate({
            "semantics": _SMA_ABOVE_SEMANTICS,
            "bars": [],
            "toolset": {
                "toolset_id": "ts",
                "tools": [{"instance_id": "sma_fast", "tool_id": "sma", "parameters": {"period": 3}}],
            },
        })
        assert req.toolset is not None
        assert req.toolset.toolset_id == "ts"


# ===========================================================================
# Crossover SMA semantics — two-instance integration
# ===========================================================================

class TestCrossoverSematicIntegration:
    """Verify that two SMA instances enable crossover semantics evaluation."""

    _CROSSOVER_SEMANTICS = {
        "entry_rules": [{
            "rule_id": "r1",
            "label": "fast crosses above slow",
            "condition_group": {
                "group_id": "g1",
                "operator": "AND",
                "conditions": [{
                    "condition_id": "c1",
                    "label": None,
                    "left":  {"kind": "tool_output", "ref": "sma_fast.sma"},
                    "operator": ">",
                    "right": {"kind": "tool_output", "ref": "sma_slow.sma"},
                }],
            },
        }],
        "exit_rules": [],
    }

    def test_two_sma_instances_resolve_independently(self):
        # 10 bars rising; fast(2) will always >= slow(4) after warmup
        bars = [_bar_payload(i, float(100 + i)) for i in range(10)]
        toolset = _toolset(_sma_config("sma_fast", 2), _sma_config("sma_slow", 4))
        sem = StrategySemantics.model_validate(self._CROSSOVER_SEMANTICS)
        result = evaluate_history_from_payload(sem, bars, toolset=toolset)
        assert result.bars_evaluated == 10
        traces = {t.bar_index: t for t in result.bar_results}
        # bars 0-2 (slow warmup=3) → None
        assert traces[0].entry_triggered is None
        assert traces[1].entry_triggered is None
        assert traces[2].entry_triggered is None
        # bar 3: first bar where slow SMA has data (period=4, warmup=3 done)
        # fast=SMA2(102,103)=102.5, slow=SMA4(100,101,102,103)=101.5 → fast > slow
        assert traces[3].entry_triggered is True
        # bar 4+: fast > slow continues (rising series)
        assert traces[4].entry_triggered is True

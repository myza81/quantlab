"""
Tests for backend/strategy_runtime/visualization.py.

Covers:
- IndicatorPoint: valid construction, UTC enforcement, naive datetime rejected
- IndicatorSeries: valid construction, name validation, defaults
- IndicatorSeries.kind and pane enum values
- Empty points list allowed
- Runner extraction: artifacts extracted from apply_risk_rules output
- Runner extraction: non-list artifacts produce warning + empty result
- Runner extraction: non-IndicatorSeries items ignored with warning
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.strategy_runtime.visualization import (
    IndicatorPane,
    IndicatorPoint,
    IndicatorSeries,
    IndicatorSeriesKind,
)


# ---------------------------------------------------------------------------
# IndicatorPoint
# ---------------------------------------------------------------------------

class TestIndicatorPoint:
    def test_valid_construction(self) -> None:
        pt = IndicatorPoint(timestamp=datetime(2023, 1, 3, tzinfo=timezone.utc), value=150.0)
        assert pt.value == 150.0

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(Exception):
            IndicatorPoint(timestamp=datetime(2023, 1, 3), value=150.0)

    def test_timestamp_coerced_to_utc(self) -> None:
        from datetime import timezone as tz, timedelta
        eastern = timezone(timedelta(hours=-5))
        pt = IndicatorPoint(timestamp=datetime(2023, 1, 3, 0, 0, 0, tzinfo=eastern), value=100.0)
        assert pt.timestamp.tzinfo == timezone.utc

    def test_frozen(self) -> None:
        pt = IndicatorPoint(timestamp=datetime(2023, 1, 3, tzinfo=timezone.utc), value=100.0)
        with pytest.raises(Exception):
            pt.value = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IndicatorSeries
# ---------------------------------------------------------------------------

class TestIndicatorSeries:
    def _point(self, day: int, value: float) -> IndicatorPoint:
        return IndicatorPoint(timestamp=datetime(2023, 1, day, tzinfo=timezone.utc), value=value)

    def test_valid_construction(self) -> None:
        s = IndicatorSeries(name="MA20", points=[self._point(3, 150.0)])
        assert s.name == "MA20"
        assert len(s.points) == 1

    def test_defaults(self) -> None:
        s = IndicatorSeries(name="MA20", points=[])
        assert s.kind == IndicatorSeriesKind.line
        assert s.pane == IndicatorPane.price
        assert s.color is None

    def test_empty_points_allowed(self) -> None:
        s = IndicatorSeries(name="MA20", points=[])
        assert s.points == []

    def test_color_accepted(self) -> None:
        s = IndicatorSeries(name="MA20", color="#2196f3", points=[])
        assert s.color == "#2196f3"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(Exception):
            IndicatorSeries(name="", points=[])

    def test_whitespace_name_rejected(self) -> None:
        with pytest.raises(Exception):
            IndicatorSeries(name="   ", points=[])

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(Exception):
            IndicatorSeries(name="MA20", points=[], unknown_field="x")  # type: ignore[call-arg]

    def test_kind_enum_values(self) -> None:
        assert IndicatorSeriesKind.line.value == "line"

    def test_pane_enum_values(self) -> None:
        assert IndicatorPane.price.value == "price"

    def test_frozen(self) -> None:
        s = IndicatorSeries(name="MA20", points=[])
        with pytest.raises(Exception):
            s.name = "other"  # type: ignore[misc]

    def test_multiple_points(self) -> None:
        points = [self._point(i, float(100 + i)) for i in range(1, 6)]
        s = IndicatorSeries(name="MA20", points=points)
        assert len(s.points) == 5


# ---------------------------------------------------------------------------
# Runner artifact extraction (via StrategyRuntimeRunner internals)
# ---------------------------------------------------------------------------

class TestRunnerArtifactExtraction:
    """Test _extract_artifacts via the public runner interface."""

    def _make_result_with_artifacts(self, artifacts_payload: object) -> object:
        from backend.strategy_runtime.runner import _extract_artifacts
        return _extract_artifacts({"artifacts": artifacts_payload})

    def test_valid_artifacts_extracted(self) -> None:
        series = IndicatorSeries(name="MA20", points=[])
        result, warnings = self._make_result_with_artifacts([series])
        assert len(result) == 1
        assert result[0].name == "MA20"
        assert warnings == []

    def test_non_list_artifacts_warns(self) -> None:
        result, warnings = self._make_result_with_artifacts("not a list")
        assert result == []
        assert len(warnings) == 1
        assert "non-list" in warnings[0]

    def test_non_indicator_series_items_ignored_with_warning(self) -> None:
        series = IndicatorSeries(name="MA20", points=[])
        result, warnings = self._make_result_with_artifacts([series, "bad_item", 42])
        assert len(result) == 1
        assert result[0].name == "MA20"
        assert any("ignored" in w for w in warnings)

    def test_empty_artifacts_list(self) -> None:
        result, warnings = self._make_result_with_artifacts([])
        assert result == []
        assert warnings == []

    def test_absent_artifacts_key_returns_empty(self) -> None:
        from backend.strategy_runtime.runner import _extract_artifacts
        result, warnings = _extract_artifacts({"signals": []})
        assert result == []
        assert warnings == []

    def test_non_dict_output_returns_empty(self) -> None:
        from backend.strategy_runtime.runner import _extract_artifacts
        result, warnings = _extract_artifacts(None)
        assert result == []
        assert warnings == []

"""
Backtest integrity hardening tests.

Focus:
    - canonical historical replay order
    - duplicate bar rejection
    - signal/trade/report timestamp integrity after sorting
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.api.schemas.backtest_runs import BacktestRunRequest
from backend.api.schemas.composition_run import CompositionRunBar
from backend.api.services.backtest_run_service import BacktestRunError, create_backtest_run
from backend.strategy_registry.draft_repository import DraftRepository
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.semantics import StrategySemantics
from backend.tools.toolset import StrategyToolSet


_NOW = datetime(2026, 5, 24, tzinfo=timezone.utc)


def _bar(index: int, close: float) -> CompositionRunBar:
    return CompositionRunBar(
        bar_index=index,
        timestamp=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
    )


def _draft() -> StrategyDraft:
    semantics = StrategySemantics.model_validate({
        "entry_rules": [{
            "rule_id": "entry_cross",
            "label": "close crosses above 50",
            "condition_group": {
                "group_id": "g1",
                "operator": "AND",
                "conditions": [{
                    "condition_id": "c1",
                    "label": None,
                    "left": {"kind": "price", "ref": "close"},
                    "operator": "crosses_above",
                    "right": {"kind": "constant", "ref": "50"},
                }],
            },
        }],
        "exit_rules": [],
    })
    return StrategyDraft(
        draft_id="integrity-draft",
        display_name="Integrity Draft",
        toolset=StrategyToolSet(toolset_id="empty", tools=()),
        created_at=_NOW,
        updated_at=_NOW,
        semantics=semantics,
    )


def _repo(tmp_path: Path) -> DraftRepository:
    repo = DraftRepository(tmp_path)
    repo.save(_draft())
    return repo


class TestBacktestIntegrity:
    def test_unsorted_request_bars_replayed_historically(self, tmp_path: Path):
        # Bar 0 (close=40): below 50, no signal.
        # Bar 1 (close=60): crosses above 50, OPEN_LONG signal fires.
        # Bar 2 (close=65): execution bar — NBO fills open_long at bar 2's open.
        # Bars are intentionally submitted out-of-order to verify canonical replay.
        request = BacktestRunRequest(
            draft_id="integrity-draft",
            symbol="TST",
            timeframe="1d",
            bars=[_bar(1, 60.0), _bar(0, 40.0), _bar(2, 65.0)],
        )

        result = create_backtest_run(
            request=request,
            repository=_repo(tmp_path / "drafts"),
            storage=tmp_path / "runs",
        )

        report = result.report
        assert report.run.dataset_start == "2026-01-01T00:00:00+00:00"
        assert report.run.dataset_end == "2026-01-03T00:00:00+00:00"
        assert [pt.bar_index for pt in report.equity_curve] == [0, 1, 2]
        # NBO: signal on bar 1 → fills at bar 2 open.
        assert report.open_position is not None
        assert report.open_position.entry_bar_index == 2
        assert report.open_position.entry_timestamp == "2026-01-03T00:00:00+00:00"
        assert report.open_position.entry_rule_id == "entry_cross"
        assert report.open_position.entry_signal_event_id == "1:entry:0:entry_cross"

    def test_duplicate_request_bar_index_rejected(self, tmp_path: Path):
        request = BacktestRunRequest(
            draft_id="integrity-draft",
            symbol="TST",
            timeframe="1d",
            bars=[_bar(0, 40.0), _bar(0, 60.0)],
        )

        with pytest.raises(BacktestRunError, match="duplicate bar_index"):
            create_backtest_run(
                request=request,
                repository=_repo(tmp_path / "drafts"),
                storage=tmp_path / "runs",
            )

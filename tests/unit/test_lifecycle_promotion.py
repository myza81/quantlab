"""
Unit tests for Phase R3 — Backend Lifecycle Promotion Repair.

Covers:
  - promote_draft_to_backtested() service (8 scenarios)
  - POST /backtests/runs/{run_id}/promote-draft route (7 scenarios)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.api.services.backtest_run_service import (
    BacktestAccessDeniedError,
    BacktestRunError,
)
from backend.api.services.draft_service import (
    LifecyclePromotionError,
    promote_draft_to_backtested,
)
from backend.strategy_registry.draft_repository import (
    DraftNotFoundError,
    DraftRepository,
)
from backend.strategy_registry.drafts import StrategyDraft
from backend.strategy_registry.lifecycle import StrategyLifecycleStatus
from backend.tools.toolset import StrategyToolSet

_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_draft(
    draft_id: str,
    owner_id: str = "user-1",
    lifecycle_status: StrategyLifecycleStatus = StrategyLifecycleStatus.VALIDATED,
) -> StrategyDraft:
    now = datetime.now(_UTC)
    return StrategyDraft(
        draft_id=draft_id,
        display_name="Test Strategy",
        toolset=StrategyToolSet(toolset_id="default", tools=[]),
        created_at=now,
        updated_at=now,
        user_id=owner_id,
        lifecycle_status=lifecycle_status,
    )


def _minimal_report(
    run_id: str,
    draft_id: str,
    owner_user_id: str = "user-1",
    status: str = "completed",
) -> dict:
    """Minimal valid BacktestReport JSON."""
    return {
        "run": {
            "run_id": run_id,
            "draft_id": draft_id,
            "draft_name": "Test Strategy",
            "symbol": "AAPL",
            "timeframe": "1d",
            "bars_count": 50,
            "run_timestamp": "2026-01-01T00:00:00+00:00",
            "status": status,
            "config": {
                "initial_equity": 10000.0,
                "position_size_mode": "equity_fraction",
                "equity_fraction": 0.95,
                "fixed_quantity": 1.0,
                "commission_mode": "none",
                "commission_value": 0.0,
                "slippage_mode": "none",
                "slippage_value": 0.0,
            },
            "dataset_start": None,
            "dataset_end": None,
            "owner_user_id": owner_user_id,
            "dataset_provenance": None,
            "draft_provenance": {
                "draft_id": draft_id,
                "display_name": "Test Strategy",
                "lifecycle_status_at_run": "validated",
                "semantics_hash": None,
            },
        },
        "metrics": {
            "initial_equity": 10000.0,
            "final_equity": 11000.0,
            "total_net_profit": 1000.0,
            "total_return_pct": 10.0,
            "gross_profit": 1200.0,
            "gross_loss": 200.0,
            "total_commission": 0.0,
            "total_slippage": 0.0,
            "total_cost": 0.0,
            "trade_count": 5,
            "win_count": 4,
            "loss_count": 1,
            "breakeven_count": 0,
            "win_rate": 0.8,
            "avg_win": 300.0,
            "avg_loss": 200.0,
            "profit_factor": 6.0,
            "best_trade_pnl": 400.0,
            "worst_trade_pnl": -200.0,
            "max_drawdown_pct": 5.0,
            "peak_equity": 11200.0,
            "trough_equity": 9800.0,
            "total_bars": 50,
            "total_rejections": 0,
        },
        "equity_curve": [],
        "drawdown_curve": [],
        "trades": [],
        "open_position": None,
        "rejections": [],
    }


def _save_report(storage: Path, run_id: str, data: dict) -> None:
    storage.mkdir(parents=True, exist_ok=True)
    (storage / f"{run_id}.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Service unit tests — 8 required scenarios
# ---------------------------------------------------------------------------

class TestPromoteDraftToBacktested:

    def test_happy_path_validated_to_backtested(self, tmp_path):
        """Valid completed run for correct draft/owner → draft promoted to backtested."""
        repo = DraftRepository(tmp_path)
        draft_id = "draft-promo-1"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id=owner_id))

        result = promote_draft_to_backtested(
            draft_id=draft_id,
            run_id=run_id,
            repository=repo,
            storage=tmp_path,
            owner_id=owner_id,
        )

        assert result.lifecycle_status == StrategyLifecycleStatus.BACKTESTED
        # Verify persisted state
        reloaded = repo.load(draft_id, owner_id=owner_id)
        assert reloaded.lifecycle_status == StrategyLifecycleStatus.BACKTESTED

    def test_notes_are_persisted(self, tmp_path):
        """Optional notes kwarg is written into the updated draft."""
        repo = DraftRepository(tmp_path)
        draft_id = "draft-notes"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id=owner_id))

        result = promote_draft_to_backtested(
            draft_id=draft_id,
            run_id=run_id,
            repository=repo,
            storage=tmp_path,
            owner_id=owner_id,
            notes="Promoted after reviewing equity curve",
        )

        assert result.notes == "Promoted after reviewing equity curve"

    def test_draft_not_found_raises(self, tmp_path):
        """Nonexistent draft → DraftNotFoundError (maps to 404)."""
        repo = DraftRepository(tmp_path)
        run_id = str(uuid.uuid4())
        _save_report(tmp_path, run_id, _minimal_report(run_id, "ghost-draft", owner_user_id="user-1"))

        with pytest.raises(DraftNotFoundError):
            promote_draft_to_backtested(
                draft_id="ghost-draft",
                run_id=run_id,
                repository=repo,
                storage=tmp_path,
                owner_id="user-1",
            )

    def test_draft_wrong_owner_raises(self, tmp_path):
        """Draft owned by user-1; request as user-2 → DraftNotFoundError (information hiding)."""
        repo = DraftRepository(tmp_path)
        draft_id = "draft-owner-check"
        run_id = str(uuid.uuid4())

        repo.save(_make_draft(draft_id, owner_id="user-1", lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id="user-2"))

        with pytest.raises(DraftNotFoundError):
            promote_draft_to_backtested(
                draft_id=draft_id,
                run_id=run_id,
                repository=repo,
                storage=tmp_path,
                owner_id="user-2",  # not the draft owner
            )

    def test_backtest_not_found_raises(self, tmp_path):
        """Run file absent → BacktestRunError (maps to 404)."""
        repo = DraftRepository(tmp_path)
        draft_id = "draft-no-run"
        owner_id = "user-1"

        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.VALIDATED))

        with pytest.raises(BacktestRunError):
            promote_draft_to_backtested(
                draft_id=draft_id,
                run_id=str(uuid.uuid4()),
                repository=repo,
                storage=tmp_path,
                owner_id=owner_id,
            )

    def test_backtest_wrong_owner_raises(self, tmp_path):
        """Run owned by user-2; request as user-1 → BacktestAccessDeniedError (maps to 404)."""
        repo = DraftRepository(tmp_path)
        draft_id = "draft-run-owner"
        run_id = str(uuid.uuid4())

        repo.save(_make_draft(draft_id, owner_id="user-1", lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id="user-2"))

        with pytest.raises(BacktestAccessDeniedError):
            promote_draft_to_backtested(
                draft_id=draft_id,
                run_id=run_id,
                repository=repo,
                storage=tmp_path,
                owner_id="user-1",  # run owned by user-2
            )

    def test_run_not_for_this_draft_raises(self, tmp_path):
        """Run was produced for a different draft → LifecyclePromotionError (maps to 422)."""
        repo = DraftRepository(tmp_path)
        draft_id = "draft-correct"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        # Report references a DIFFERENT draft
        _save_report(tmp_path, run_id, _minimal_report(run_id, "draft-other", owner_user_id=owner_id))

        with pytest.raises(LifecyclePromotionError, match="draft-other"):
            promote_draft_to_backtested(
                draft_id=draft_id,
                run_id=run_id,
                repository=repo,
                storage=tmp_path,
                owner_id=owner_id,
            )

    def test_failed_backtest_raises(self, tmp_path):
        """Run with status != 'completed' → LifecyclePromotionError (maps to 422)."""
        repo = DraftRepository(tmp_path)
        draft_id = "draft-failed-run"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id=owner_id, status="failed"))

        with pytest.raises(LifecyclePromotionError, match="failed"):
            promote_draft_to_backtested(
                draft_id=draft_id,
                run_id=run_id,
                repository=repo,
                storage=tmp_path,
                owner_id=owner_id,
            )

    def test_invalid_lifecycle_transition_raises(self, tmp_path):
        """Draft in DRAFT status cannot skip VALIDATED → BACKTESTED raises ValueError."""
        repo = DraftRepository(tmp_path)
        draft_id = "draft-wrong-state"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        # DRAFT → BACKTESTED is not a permitted transition
        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.DRAFT))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id=owner_id))

        with pytest.raises(ValueError, match="not permitted"):
            promote_draft_to_backtested(
                draft_id=draft_id,
                run_id=run_id,
                repository=repo,
                storage=tmp_path,
                owner_id=owner_id,
            )


# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------

def _make_app(tmp_path: Path):
    """Build a minimal TestClient with real repositories backed by tmp_path."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.dependencies import get_backtest_storage_path, get_draft_repository
    from backend.api.routes import backtest_runs
    from backend.auth.entitlement import require_active_subscription
    from backend.auth.models import User

    app = FastAPI()
    app.include_router(backtest_runs.router)

    fake_user = User(
        user_id="user-1",
        username="testuser",
        email="test@example.com",
        password_hash="x",
        created_at="2024-01-01T00:00:00Z",
        role="user",
        subscription_status="active",
    )
    app.dependency_overrides[require_active_subscription] = lambda: fake_user
    app.dependency_overrides[get_draft_repository] = lambda: DraftRepository(tmp_path)
    app.dependency_overrides[get_backtest_storage_path] = lambda: tmp_path

    return TestClient(app)


class TestPromoteDraftRoute:

    def test_successful_promotion_returns_200(self, tmp_path):
        client = _make_app(tmp_path)
        draft_id = "draft-route-1"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        repo = DraftRepository(tmp_path)
        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id=owner_id))

        resp = client.post(
            f"/backtests/runs/{run_id}/promote-draft",
            json={"draft_id": draft_id},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["lifecycle_status"] == "backtested"
        assert body["draft_id"] == draft_id

    def test_draft_not_found_returns_404(self, tmp_path):
        client = _make_app(tmp_path)
        run_id = str(uuid.uuid4())
        _save_report(tmp_path, run_id, _minimal_report(run_id, "ghost", owner_user_id="user-1"))

        resp = client.post(
            f"/backtests/runs/{run_id}/promote-draft",
            json={"draft_id": "ghost"},
        )

        assert resp.status_code == 404

    def test_run_not_found_returns_404(self, tmp_path):
        client = _make_app(tmp_path)
        draft_id = "draft-exists"
        run_id = str(uuid.uuid4())

        repo = DraftRepository(tmp_path)
        repo.save(_make_draft(draft_id, owner_id="user-1", lifecycle_status=StrategyLifecycleStatus.VALIDATED))

        resp = client.post(
            f"/backtests/runs/{run_id}/promote-draft",
            json={"draft_id": draft_id},
        )

        assert resp.status_code == 404

    def test_run_mismatch_returns_422(self, tmp_path):
        client = _make_app(tmp_path)
        draft_id = "draft-mismatch"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        repo = DraftRepository(tmp_path)
        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        _save_report(tmp_path, run_id, _minimal_report(run_id, "other-draft", owner_user_id=owner_id))

        resp = client.post(
            f"/backtests/runs/{run_id}/promote-draft",
            json={"draft_id": draft_id},
        )

        assert resp.status_code == 422

    def test_failed_run_returns_422(self, tmp_path):
        client = _make_app(tmp_path)
        draft_id = "draft-failed"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        repo = DraftRepository(tmp_path)
        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.VALIDATED))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id=owner_id, status="running"))

        resp = client.post(
            f"/backtests/runs/{run_id}/promote-draft",
            json={"draft_id": draft_id},
        )

        assert resp.status_code == 422

    def test_invalid_lifecycle_state_returns_422(self, tmp_path):
        client = _make_app(tmp_path)
        draft_id = "draft-wrong-lc"
        run_id = str(uuid.uuid4())
        owner_id = "user-1"

        repo = DraftRepository(tmp_path)
        repo.save(_make_draft(draft_id, owner_id=owner_id, lifecycle_status=StrategyLifecycleStatus.DRAFT))
        _save_report(tmp_path, run_id, _minimal_report(run_id, draft_id, owner_user_id=owner_id))

        resp = client.post(
            f"/backtests/runs/{run_id}/promote-draft",
            json={"draft_id": draft_id},
        )

        assert resp.status_code == 422

    def test_malformed_run_id_returns_400(self, tmp_path):
        client = _make_app(tmp_path)

        resp = client.post(
            "/backtests/runs/not-a-uuid/promote-draft",
            json={"draft_id": "some-draft"},
        )

        assert resp.status_code == 400

    def test_forward_test_gate_unaffected(self, tmp_path):
        """Forward-test lifecycle gate: backtested → forward_tested remains intact.

        Ensures Phase R3 did not weaken the existing forward-test gate by verifying
        that a draft still in VALIDATED status cannot start a forward-test session.
        We exercise this by confirming the lifecycle transition is still enforced:
        VALIDATED → FORWARD_TESTED is not an allowed transition.
        """
        from backend.strategy_registry.lifecycle import (
            StrategyLifecycleStatus,
            validate_lifecycle_transition,
        )

        with pytest.raises(ValueError, match="not permitted"):
            validate_lifecycle_transition(
                StrategyLifecycleStatus.VALIDATED,
                StrategyLifecycleStatus.FORWARD_TESTED,
            )

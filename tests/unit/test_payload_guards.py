"""
Phase 3S-B — Payload Bar-Count Guard Tests.

Verifies that both compute endpoints enforce MAX_BACKTEST_BARS:
    POST /backtests/simulate  (price_bars field)
    POST /backtests/runs      (bars field)

Scenarios:
    1. Below limit → not rejected (no 400 from guard)
    2. Exact limit → not rejected (boundary is inclusive)
    3. Above limit → HTTP 400 with "bar count" in detail
    4. Malformed body → HTTP 422 (Pydantic validation, not our guard)

Tests patch settings.max_backtest_bars to a small sentinel value (3) so
we don't have to construct 50,000 bar objects in CI.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app

_CLIENT = TestClient(app)
_TEST_MAX = 3


def _sim_bar(i: int) -> dict:
    return {"bar_index": i, "close": 100.0}


def _run_bar(i: int) -> dict:
    return {"bar_index": i, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1000.0}


_EMPTY_INTENT_BATCH = {
    "plan_draft_id": None,
    "intents": [],
    "summary": {
        "total_intents": 0,
        "open_long_intents": 0,
        "close_long_intents": 0,
        "ignored_signal_events": 0,
        "first_intent_bar_index": None,
        "last_intent_bar_index": None,
    },
    "ignored_event_ids": [],
}

_SIMULATE_CONFIG = {"initial_cash": 10000.0, "fixed_quantity": 1.0}

_RUN_REQUEST_BASE = {
    "draft_id": "nonexistent-draft",
    "symbol": "AAPL",
    "timeframe": "1d",
    "config": {"initial_cash": 10000.0, "fixed_quantity": 1.0},
}


def _simulate_body(n_bars: int) -> dict:
    return {
        "intent_batch": _EMPTY_INTENT_BATCH,
        "price_bars": [_sim_bar(i) for i in range(n_bars)],
        "config": _SIMULATE_CONFIG,
    }


def _run_body(n_bars: int) -> dict:
    return {**_RUN_REQUEST_BASE, "bars": [_run_bar(i) for i in range(n_bars)]}


# ---------------------------------------------------------------------------
# /backtests/simulate — price_bars guard
# ---------------------------------------------------------------------------

class TestSimulateBarCountGuard:
    """Bar-count guard on POST /backtests/simulate."""

    def _post(self, n_bars: int):
        with patch("backend.api.routes.backtest_simulation.settings") as mock_s:
            mock_s.max_backtest_bars = _TEST_MAX
            return _CLIENT.post("/backtests/simulate", json=_simulate_body(n_bars))

    def test_below_limit_is_not_rejected(self):
        resp = self._post(_TEST_MAX - 1)
        assert resp.status_code != 400, (
            f"below-limit simulate should not get 400, got {resp.status_code}"
        )

    def test_exact_limit_is_not_rejected(self):
        resp = self._post(_TEST_MAX)
        assert resp.status_code != 400, (
            f"exact-limit simulate should not get 400, got {resp.status_code}"
        )

    def test_above_limit_returns_400(self):
        resp = self._post(_TEST_MAX + 1)
        assert resp.status_code == 400, (
            f"above-limit simulate should return 400, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_above_limit_detail_mentions_bar_count(self):
        resp = self._post(_TEST_MAX + 1)
        assert "bar count" in resp.text.lower(), (
            f"400 detail should mention 'bar count': {resp.text[:300]}"
        )

    def test_malformed_body_returns_422(self):
        resp = _CLIENT.post("/backtests/simulate", json={"invalid": "body"})
        assert resp.status_code == 422

    def test_zero_bars_is_not_rejected_by_guard(self):
        resp = self._post(0)
        assert resp.status_code != 400, (
            f"zero-bar simulate should not be rejected by guard, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# /backtests/runs — bars guard
# ---------------------------------------------------------------------------

class TestBacktestRunBarCountGuard:
    """Bar-count guard on POST /backtests/runs."""

    def _post(self, n_bars: int):
        with patch("backend.api.routes.backtest_runs.settings") as mock_s:
            mock_s.max_backtest_bars = _TEST_MAX
            return _CLIENT.post("/backtests/runs", json=_run_body(n_bars))

    def test_below_limit_is_not_rejected(self):
        resp = self._post(_TEST_MAX - 1)
        assert resp.status_code != 400, (
            f"below-limit run should not get 400, got {resp.status_code}"
        )

    def test_exact_limit_is_not_rejected(self):
        resp = self._post(_TEST_MAX)
        assert resp.status_code != 400, (
            f"exact-limit run should not get 400, got {resp.status_code}"
        )

    def test_above_limit_returns_400(self):
        resp = self._post(_TEST_MAX + 1)
        assert resp.status_code == 400, (
            f"above-limit run should return 400, got {resp.status_code}: {resp.text[:200]}"
        )

    def test_above_limit_detail_mentions_bar_count(self):
        resp = self._post(_TEST_MAX + 1)
        assert "bar count" in resp.text.lower(), (
            f"400 detail should mention 'bar count': {resp.text[:300]}"
        )

    def test_malformed_body_returns_422(self):
        resp = _CLIENT.post("/backtests/runs", json={"invalid": "body"})
        assert resp.status_code == 422

    def test_zero_bars_is_not_rejected_by_guard(self):
        resp = self._post(0)
        assert resp.status_code != 400, (
            f"zero-bar run should not be rejected by guard, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Guard is checked before business logic (no draft lookup on oversized)
# ---------------------------------------------------------------------------

class TestGuardIsEarlyExit:
    """Oversized payloads are rejected before any storage or draft lookup."""

    def test_simulate_oversized_does_not_reach_simulator(self):
        with patch("backend.api.routes.backtest_simulation.settings") as mock_s, \
             patch("backend.api.routes.backtest_simulation.simulate_backtest") as mock_sim:
            mock_s.max_backtest_bars = _TEST_MAX
            _CLIENT.post("/backtests/simulate", json=_simulate_body(_TEST_MAX + 1))
            mock_sim.assert_not_called()

    def test_run_oversized_does_not_reach_service(self):
        with patch("backend.api.routes.backtest_runs.settings") as mock_s, \
             patch("backend.api.routes.backtest_runs.create_backtest_run") as mock_run:
            mock_s.max_backtest_bars = _TEST_MAX
            _CLIENT.post("/backtests/runs", json=_run_body(_TEST_MAX + 1))
            mock_run.assert_not_called()

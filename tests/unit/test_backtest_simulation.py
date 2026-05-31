"""
Phase 2P.6 — Backtest Simulation Foundation tests.

Coverage areas:
  1.  Domain model construction and serialization
  2.  BacktestSimulationConfig validation
  3.  SimulationPriceBar validation
  4.  PositionState properties
  5.  process_intent — open_long from flat
  6.  process_intent — reject open_long while long
  7.  process_intent — reject open_long insufficient cash
  8.  process_intent — close_long from long
  9.  process_intent — reject close_long while flat
  10. process_intent — missing price
  11. process_intent — unsupported action (via monkeypatch)
  12. run_simulation — single open/close cycle
  13. run_simulation — equity curve correctness
  14. run_simulation — unrealized PnL while open
  15. run_simulation — realized PnL after close
  16. run_simulation — multiple cycles
  17. run_simulation — rejections captured
  18. run_simulation — one equity point per bar
  19. run_simulation — cash exhaustion rejection
  20. run_simulation — intent with missing price bar
  21. run_simulation — empty intent batch
  22. run_simulation — summary correctness
  23. run_simulation — peak and trough equity
  24. API endpoint — valid simulation
  25. API endpoint — invalid config (negative cash)
  26. API endpoint — empty price bars produces no trades
  27. API endpoint — rejection in response
  28. Architecture guard — no forbidden imports in models
  29. Architecture guard — no forbidden imports in position_tracker
  30. Architecture guard — no forbidden imports in simulator
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.backtesting.models import (
    BacktestEquityPoint,
    BacktestRejection,
    BacktestRejectionReason,
    BacktestSimulationConfig,
    BacktestSimulationResult,
    BacktestSimulationSummary,
    PositionSizeMode,
    SimulatedTrade,
    SimulationPriceBar,
)
from backend.backtesting.position_tracker import PositionState, process_intent
from backend.backtesting.simulator import run_simulation
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.strategy_registry.trade_intents import (
    TradeIntent,
    TradeIntentAction,
    TradeIntentBatch,
    TradeIntentSource,
    TradeIntentSummary,
)

_TEST_USER = User(
    user_id="test-user",
    username="testuser",
    email="test@example.com",
    password_hash="x",
    created_at="2024-01-01T00:00:00Z",
    role="user",
    subscription_status="active",
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc


def _ts(bar: int) -> datetime:
    from datetime import timedelta
    return datetime(2024, 1, 1, tzinfo=_UTC) + timedelta(days=bar)


def _price_bar(bar_index: int, close: float) -> SimulationPriceBar:
    return SimulationPriceBar(bar_index=bar_index, timestamp=_ts(bar_index), close=close)


def _intent(
    bar_index: int,
    action: TradeIntentAction,
    rule_kind: str = "entry",
    rule_id: str = "r1",
    rule_index: int = 0,
) -> TradeIntent:
    event_id = f"{bar_index}:{rule_kind}:{rule_index}:{rule_id}"
    source = TradeIntentSource(
        signal_event_id=event_id,
        bar_index=bar_index,
        timestamp=_ts(bar_index),
        rule_id=rule_id,
        rule_kind=rule_kind,
    )
    return TradeIntent(
        intent_id=f"intent:{event_id}",
        action=action,
        source=source,
    )


def _open_intent(bar_index: int) -> TradeIntent:
    return _intent(bar_index, TradeIntentAction.OPEN_LONG, rule_kind="entry")


def _close_intent(bar_index: int) -> TradeIntent:
    return _intent(bar_index, TradeIntentAction.CLOSE_LONG, rule_kind="exit")


def _make_batch(*intents: TradeIntent, draft_id: str | None = "draft-1") -> TradeIntentBatch:
    open_count  = sum(1 for i in intents if i.action == TradeIntentAction.OPEN_LONG)
    close_count = sum(1 for i in intents if i.action == TradeIntentAction.CLOSE_LONG)
    first_bar   = intents[0].source.bar_index if intents else None
    last_bar    = intents[-1].source.bar_index if intents else None
    return TradeIntentBatch(
        plan_draft_id=draft_id,
        intents=tuple(intents),
        summary=TradeIntentSummary(
            total_intents=len(intents),
            open_long_intents=open_count,
            close_long_intents=close_count,
            ignored_signal_events=0,
            first_intent_bar_index=first_bar,
            last_intent_bar_index=last_bar,
        ),
        ignored_event_ids=(),
    )


def _default_config(cash: float = 10_000.0, qty: float = 1.0) -> BacktestSimulationConfig:
    return BacktestSimulationConfig(initial_cash=cash, fixed_quantity=qty)


# ---------------------------------------------------------------------------
# 1. Domain model construction and serialization
# ---------------------------------------------------------------------------

class TestDomainModels:
    def test_simulation_price_bar_frozen(self):
        bar = _price_bar(0, 100.0)
        with pytest.raises(Exception):
            bar.close = 999.0  # type: ignore[misc]

    def test_backtest_rejection_frozen(self):
        r = BacktestRejection(
            rejection_id="rejection:x",
            intent_id="x",
            bar_index=0,
            timestamp=None,
            reason=BacktestRejectionReason.ALREADY_FLAT,
            detail="test",
        )
        with pytest.raises(Exception):
            r.reason = BacktestRejectionReason.ALREADY_LONG  # type: ignore[misc]

    def test_simulated_trade_frozen(self):
        from backend.backtesting.cost_model import TradeCostBreakdown
        from backend.backtesting.models import PositionSizeMode
        t = SimulatedTrade(
            trade_id="trade:x",
            source_intent_id="x",
            action="open_long",
            bar_index=0,
            timestamp=None,
            quantity=1.0,
            price=100.0,
            cash_before=10_000.0,
            cash_after=9_900.0,
            realized_pnl=None,
            position_after=1.0,
            cost_breakdown=TradeCostBreakdown(
                raw_price=100.0,
                adjusted_price=100.0,
                gross_value=100.0,
                commission_paid=0.0,
                slippage_paid=0.0,
                total_cost=0.0,
                net_cash_impact=-100.0,
            ),
            position_size_mode=PositionSizeMode.FIXED_QUANTITY,
            sizing_value=1.0,
        )
        with pytest.raises(Exception):
            t.price = 0.0  # type: ignore[misc]

    def test_equity_point_frozen(self):
        ep = BacktestEquityPoint(
            bar_index=0,
            timestamp=None,
            cash=9_900.0,
            position_quantity=1.0,
            market_value=100.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            equity=10_000.0,
        )
        with pytest.raises(Exception):
            ep.equity = 0.0  # type: ignore[misc]

    def test_summary_frozen(self):
        s = BacktestSimulationSummary(
            total_bars=5,
            total_trades=2,
            open_long_trades=1,
            close_long_trades=1,
            total_rejections=0,
            initial_cash=10_000.0,
            final_cash=10_100.0,
            final_equity=10_100.0,
            total_realized_pnl=100.0,
            final_unrealized_pnl=0.0,
            peak_equity=10_100.0,
            trough_equity=9_900.0,
            total_commission_paid=0.0,
            total_slippage_paid=0.0,
            total_cost_paid=0.0,
            average_cost_per_trade=0.0,
        )
        with pytest.raises(Exception):
            s.total_bars = 99  # type: ignore[misc]

    def test_result_frozen(self):
        result = BacktestSimulationResult(
            plan_draft_id="d1",
            config=_default_config(),
            trades=(),
            equity_curve=(),
            rejections=(),
            summary=BacktestSimulationSummary(
                total_bars=0, total_trades=0, open_long_trades=0,
                close_long_trades=0, total_rejections=0,
                initial_cash=10_000.0, final_cash=10_000.0,
                final_equity=10_000.0, total_realized_pnl=0.0,
                final_unrealized_pnl=0.0, peak_equity=10_000.0,
                trough_equity=10_000.0,
                total_commission_paid=0.0, total_slippage_paid=0.0,
                total_cost_paid=0.0, average_cost_per_trade=0.0,
            ),
        )
        with pytest.raises(Exception):
            result.plan_draft_id = "x"  # type: ignore[misc]

    def test_result_serializes_to_dict(self):
        result = run_simulation(
            intent_batch=_make_batch(),
            price_bars=[_price_bar(0, 100.0)],
            config=_default_config(),
        )
        d = result.model_dump()
        assert "trades" in d
        assert "equity_curve" in d
        assert "rejections" in d
        assert "summary" in d


# ---------------------------------------------------------------------------
# 2. BacktestSimulationConfig validation
# ---------------------------------------------------------------------------

class TestBacktestSimulationConfig:
    def test_defaults(self):
        cfg = BacktestSimulationConfig()
        assert cfg.initial_cash == 10_000.0
        assert cfg.fixed_quantity == 1.0
        assert cfg.position_size_mode == PositionSizeMode.FIXED_QUANTITY

    def test_negative_cash_rejected(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(initial_cash=-100.0)

    def test_zero_cash_rejected(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(initial_cash=0.0)

    def test_negative_quantity_rejected(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(fixed_quantity=-1.0)

    def test_zero_quantity_rejected(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(fixed_quantity=0.0)

    def test_custom_values(self):
        cfg = BacktestSimulationConfig(initial_cash=50_000.0, fixed_quantity=10.0)
        assert cfg.initial_cash == 50_000.0
        assert cfg.fixed_quantity == 10.0


# ---------------------------------------------------------------------------
# 3. SimulationPriceBar validation
# ---------------------------------------------------------------------------

class TestSimulationPriceBar:
    def test_valid_bar(self):
        bar = _price_bar(3, 150.0)
        assert bar.bar_index == 3
        assert bar.close == 150.0

    def test_negative_close_rejected(self):
        with pytest.raises(Exception):
            SimulationPriceBar(bar_index=0, close=-1.0)

    def test_zero_close_rejected(self):
        with pytest.raises(Exception):
            SimulationPriceBar(bar_index=0, close=0.0)

    def test_timestamp_optional(self):
        bar = SimulationPriceBar(bar_index=0, close=100.0)
        assert bar.timestamp is None


# ---------------------------------------------------------------------------
# 4. PositionState properties
# ---------------------------------------------------------------------------

class TestPositionState:
    def test_initial_is_flat(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        assert state.is_flat
        assert not state.is_long

    def test_after_open_is_long(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        state.position_quantity = 1.0
        assert state.is_long
        assert not state.is_flat

    def test_cash_tracked(self):
        state = PositionState(cash=5_000.0, fixed_quantity=2.0)
        assert state.cash == 5_000.0


# ---------------------------------------------------------------------------
# 5. process_intent — open_long from flat
# ---------------------------------------------------------------------------

class TestProcessIntentOpenLong:
    def test_open_long_from_flat_succeeds(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        intent = _open_intent(bar_index=0)
        trade, rejection = process_intent(intent, price=100.0, state=state)
        assert trade is not None
        assert rejection is None

    def test_open_long_deducts_cash(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        trade, _ = process_intent(_open_intent(0), price=100.0, state=state)
        assert state.cash == pytest.approx(9_900.0)
        assert trade.cash_after == pytest.approx(9_900.0)
        assert trade.cash_before == pytest.approx(10_000.0)

    def test_open_long_sets_position(self):
        state = PositionState(cash=10_000.0, fixed_quantity=2.0)
        process_intent(_open_intent(0), price=100.0, state=state)
        assert state.position_quantity == pytest.approx(2.0)
        assert state.average_entry_price == pytest.approx(100.0)

    def test_open_long_trade_fields(self):
        state = PositionState(cash=10_000.0, fixed_quantity=3.0)
        intent = _open_intent(5)
        trade, _ = process_intent(intent, price=200.0, state=state)
        assert trade.trade_id == f"trade:{intent.intent_id}"
        assert trade.source_intent_id == intent.intent_id
        assert trade.action == "open_long"
        assert trade.bar_index == 5
        assert trade.quantity == pytest.approx(3.0)
        assert trade.price == pytest.approx(200.0)
        assert trade.realized_pnl is None
        assert trade.position_after == pytest.approx(3.0)

    def test_open_long_trade_id_deterministic(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        intent = _open_intent(0)
        trade, _ = process_intent(intent, price=100.0, state=state)
        assert trade.trade_id == f"trade:{intent.intent_id}"


# ---------------------------------------------------------------------------
# 6. process_intent — reject open_long while long
# ---------------------------------------------------------------------------

class TestProcessIntentRejectOpenLongWhileLong:
    def test_reject_already_long(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        trade, rejection = process_intent(_open_intent(1), price=110.0, state=state)
        assert trade is None
        assert rejection is not None
        assert rejection.reason == BacktestRejectionReason.ALREADY_LONG

    def test_rejection_id_deterministic(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        intent = _open_intent(1)
        _, rejection = process_intent(intent, price=110.0, state=state)
        assert rejection.rejection_id == f"rejection:{intent.intent_id}"

    def test_already_long_state_unchanged(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        process_intent(_open_intent(1), price=110.0, state=state)
        assert state.cash == pytest.approx(9_000.0)
        assert state.position_quantity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 7. process_intent — reject open_long insufficient cash
# ---------------------------------------------------------------------------

class TestProcessIntentRejectInsufficientCash:
    def test_reject_insufficient_cash(self):
        state = PositionState(cash=50.0, fixed_quantity=1.0)
        trade, rejection = process_intent(_open_intent(0), price=100.0, state=state)
        assert trade is None
        assert rejection is not None
        assert rejection.reason == BacktestRejectionReason.INSUFFICIENT_CASH

    def test_insufficient_cash_state_unchanged(self):
        state = PositionState(cash=50.0, fixed_quantity=1.0)
        process_intent(_open_intent(0), price=100.0, state=state)
        assert state.cash == pytest.approx(50.0)
        assert state.is_flat

    def test_exact_cash_match_succeeds(self):
        state = PositionState(cash=100.0, fixed_quantity=1.0)
        trade, rejection = process_intent(_open_intent(0), price=100.0, state=state)
        assert trade is not None
        assert rejection is None
        assert state.cash == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 8. process_intent — close_long from long
# ---------------------------------------------------------------------------

class TestProcessIntentCloseLong:
    def test_close_long_succeeds(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        trade, rejection = process_intent(_close_intent(1), price=110.0, state=state)
        assert trade is not None
        assert rejection is None

    def test_close_long_returns_cash(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        process_intent(_close_intent(1), price=110.0, state=state)
        assert state.cash == pytest.approx(9_110.0)

    def test_close_long_realized_pnl(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        trade, _ = process_intent(_close_intent(1), price=110.0, state=state)
        assert trade.realized_pnl == pytest.approx(10.0)

    def test_close_long_negative_pnl(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        trade, _ = process_intent(_close_intent(1), price=90.0, state=state)
        assert trade.realized_pnl == pytest.approx(-10.0)

    def test_close_long_clears_position(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        process_intent(_close_intent(1), price=110.0, state=state)
        assert state.is_flat
        assert state.position_quantity == pytest.approx(0.0)
        assert state.average_entry_price == pytest.approx(0.0)

    def test_close_long_position_after_is_zero(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0)
        trade, _ = process_intent(_close_intent(1), price=110.0, state=state)
        assert trade.position_after == pytest.approx(0.0)

    def test_close_long_accumulates_realized_pnl(self):
        state = PositionState(cash=9_000.0, fixed_quantity=1.0,
                              position_quantity=1.0, average_entry_price=100.0,
                              cumulative_realized_pnl=5.0)
        process_intent(_close_intent(1), price=110.0, state=state)
        assert state.cumulative_realized_pnl == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# 9. process_intent — reject close_long while flat
# ---------------------------------------------------------------------------

class TestProcessIntentRejectCloseLongFlat:
    def test_reject_close_while_flat(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        trade, rejection = process_intent(_close_intent(0), price=100.0, state=state)
        assert trade is None
        assert rejection is not None
        assert rejection.reason == BacktestRejectionReason.ALREADY_FLAT

    def test_rejection_id_deterministic(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        intent = _close_intent(0)
        _, rejection = process_intent(intent, price=100.0, state=state)
        assert rejection.rejection_id == f"rejection:{intent.intent_id}"

    def test_close_flat_state_unchanged(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        process_intent(_close_intent(0), price=100.0, state=state)
        assert state.cash == pytest.approx(10_000.0)


# ---------------------------------------------------------------------------
# 10. process_intent — missing price
# ---------------------------------------------------------------------------

class TestProcessIntentMissingPrice:
    def test_missing_price_produces_rejection(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        trade, rejection = process_intent(_open_intent(0), price=None, state=state)
        assert trade is None
        assert rejection is not None
        assert rejection.reason == BacktestRejectionReason.MISSING_PRICE

    def test_missing_price_state_unchanged(self):
        state = PositionState(cash=10_000.0, fixed_quantity=1.0)
        process_intent(_open_intent(0), price=None, state=state)
        assert state.cash == pytest.approx(10_000.0)
        assert state.is_flat


# ---------------------------------------------------------------------------
# 11. run_simulation — single open/close cycle
# ---------------------------------------------------------------------------

class TestRunSimulationBasic:
    def test_single_open_close_produces_two_trades(self):
        batch = _make_batch(_open_intent(0), _close_intent(1))
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, _default_config())
        assert len(result.trades) == 2
        assert result.trades[0].action == "open_long"
        assert result.trades[1].action == "close_long"

    def test_single_cycle_realized_pnl(self):
        batch = _make_batch(_open_intent(0), _close_intent(1))
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, _default_config())
        assert result.summary.total_realized_pnl == pytest.approx(10.0)

    def test_single_cycle_zero_rejections(self):
        batch = _make_batch(_open_intent(0), _close_intent(1))
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, _default_config())
        assert len(result.rejections) == 0

    def test_plan_draft_id_preserved(self):
        batch = _make_batch(_open_intent(0), draft_id="my-draft")
        result = run_simulation(batch, [_price_bar(0, 100.0)], _default_config())
        assert result.plan_draft_id == "my-draft"

    def test_plan_draft_id_none(self):
        batch = _make_batch(_open_intent(0), draft_id=None)
        result = run_simulation(batch, [_price_bar(0, 100.0)], _default_config())
        assert result.plan_draft_id is None

    def test_duplicate_price_bar_index_rejected(self):
        with pytest.raises(ValueError, match="duplicate bar_index"):
            run_simulation(
                _make_batch(),
                [_price_bar(0, 100.0), _price_bar(0, 101.0)],
                _default_config(),
            )

    def test_intent_timestamp_must_match_price_bar_timestamp(self):
        intent = _open_intent(1).model_copy(
            update={
                "source": TradeIntentSource(
                    signal_event_id="1:entry:0:r1",
                    bar_index=1,
                    timestamp=_ts(2),
                    rule_id="r1",
                    rule_kind="entry",
                )
            }
        )
        with pytest.raises(ValueError, match="timestamp does not match"):
            run_simulation(
                _make_batch(intent),
                [_price_bar(1, 100.0)],
                _default_config(),
            )


# ---------------------------------------------------------------------------
# 12. run_simulation — equity curve correctness
# ---------------------------------------------------------------------------

class TestEquityCurve:
    def test_one_point_per_bar(self):
        batch = _make_batch(_open_intent(0))
        bars = [_price_bar(i, 100.0 + i) for i in range(5)]
        result = run_simulation(batch, bars, _default_config())
        assert len(result.equity_curve) == 5

    def test_equity_curve_bar_indices(self):
        batch = _make_batch()
        bars = [_price_bar(i, 100.0) for i in [2, 5, 9]]
        result = run_simulation(batch, bars, _default_config())
        assert [p.bar_index for p in result.equity_curve] == [2, 5, 9]

    def test_equity_equals_cash_when_flat(self):
        batch = _make_batch()
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, _default_config(cash=10_000.0))
        for point in result.equity_curve:
            assert point.equity == pytest.approx(10_000.0)

    def test_equity_includes_position_after_open(self):
        batch = _make_batch(_open_intent(0))
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        cfg = _default_config(cash=10_000.0, qty=1.0)
        result = run_simulation(batch, bars, cfg)
        # Bar 0: open at 100, cash=9900, position=1, market_value=100, equity=10000
        p0 = result.equity_curve[0]
        assert p0.cash == pytest.approx(9_900.0)
        assert p0.position_quantity == pytest.approx(1.0)
        assert p0.market_value == pytest.approx(100.0)
        assert p0.equity == pytest.approx(10_000.0)

    def test_unrealized_pnl_while_open(self):
        batch = _make_batch(_open_intent(0))
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        cfg = _default_config(cash=10_000.0, qty=1.0)
        result = run_simulation(batch, bars, cfg)
        # Bar 1: no new trade, price moved to 110, unrealized = 10
        p1 = result.equity_curve[1]
        assert p1.unrealized_pnl == pytest.approx(10.0)
        assert p1.market_value == pytest.approx(110.0)
        assert p1.equity == pytest.approx(10_010.0)

    def test_unrealized_pnl_zero_when_flat(self):
        batch = _make_batch()
        bars = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, _default_config())
        assert result.equity_curve[0].unrealized_pnl == pytest.approx(0.0)

    def test_realized_pnl_after_close(self):
        batch = _make_batch(_open_intent(0), _close_intent(1))
        bars = [_price_bar(0, 100.0), _price_bar(1, 120.0), _price_bar(2, 115.0)]
        cfg = _default_config(cash=10_000.0, qty=1.0)
        result = run_simulation(batch, bars, cfg)
        # After bar 1 close: realized_pnl = 20
        p1 = result.equity_curve[1]
        assert p1.realized_pnl == pytest.approx(20.0)
        assert p1.unrealized_pnl == pytest.approx(0.0)
        # Bar 2: still flat, equity stays at 10020
        p2 = result.equity_curve[2]
        assert p2.equity == pytest.approx(10_020.0)

    def test_equity_timestamps_match_bars(self):
        batch = _make_batch()
        bars = [SimulationPriceBar(bar_index=i, timestamp=_ts(i), close=100.0)
                for i in range(3)]
        result = run_simulation(batch, bars, _default_config())
        for i, point in enumerate(result.equity_curve):
            assert point.timestamp == _ts(i)


# ---------------------------------------------------------------------------
# 13. run_simulation — multiple cycles
# ---------------------------------------------------------------------------

class TestMultipleCycles:
    def test_two_full_cycles(self):
        batch = _make_batch(
            _open_intent(0),
            _close_intent(1),
            _open_intent(2),
            _close_intent(3),
        )
        bars = [_price_bar(i, 100.0 + i * 5) for i in range(4)]
        cfg = _default_config(cash=10_000.0, qty=1.0)
        result = run_simulation(batch, bars, cfg)
        assert len(result.trades) == 4
        assert result.summary.open_long_trades == 2
        assert result.summary.close_long_trades == 2

    def test_two_cycles_cumulative_pnl(self):
        # Cycle 1: buy 100, sell 110 → +10
        # Cycle 2: buy 110, sell 120 → +10
        batch = _make_batch(
            _open_intent(0),
            _close_intent(1),
            _open_intent(2),
            _close_intent(3),
        )
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0),
                _price_bar(2, 110.0), _price_bar(3, 120.0)]
        cfg = _default_config(cash=10_000.0, qty=1.0)
        result = run_simulation(batch, bars, cfg)
        assert result.summary.total_realized_pnl == pytest.approx(20.0)
        assert result.summary.final_cash == pytest.approx(10_020.0)


# ---------------------------------------------------------------------------
# 14. run_simulation — rejections captured
# ---------------------------------------------------------------------------

class TestRejections:
    def test_double_open_produces_rejection(self):
        batch = _make_batch(_open_intent(0), _open_intent(1))
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, _default_config())
        assert len(result.rejections) == 1
        assert result.rejections[0].reason == BacktestRejectionReason.ALREADY_LONG

    def test_close_while_flat_rejection(self):
        batch = _make_batch(_close_intent(0))
        bars = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, _default_config())
        assert len(result.rejections) == 1
        assert result.rejections[0].reason == BacktestRejectionReason.ALREADY_FLAT

    def test_rejection_does_not_affect_equity(self):
        batch = _make_batch(_close_intent(0))
        bars = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, _default_config(cash=10_000.0))
        assert result.equity_curve[0].equity == pytest.approx(10_000.0)

    def test_intent_with_missing_price_bar_produces_rejection(self):
        batch = _make_batch(_open_intent(99))  # bar_index=99 not in price_bars
        bars = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, _default_config())
        assert len(result.rejections) == 1
        assert result.rejections[0].reason == BacktestRejectionReason.MISSING_PRICE

    def test_rejection_id_format(self):
        intent = _close_intent(0)
        batch = _make_batch(intent)
        bars = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, _default_config())
        assert result.rejections[0].rejection_id == f"rejection:{intent.intent_id}"


# ---------------------------------------------------------------------------
# 15. run_simulation — cash exhaustion
# ---------------------------------------------------------------------------

class TestCashExhaustion:
    def test_insufficient_cash_produces_rejection(self):
        batch = _make_batch(_open_intent(0))
        bars = [_price_bar(0, 10_000.0)]  # price = all cash, qty=2 → needs 20000
        cfg = _default_config(cash=10_000.0, qty=2.0)
        result = run_simulation(batch, bars, cfg)
        assert len(result.rejections) == 1
        assert result.rejections[0].reason == BacktestRejectionReason.INSUFFICIENT_CASH

    def test_cash_exhaustion_equity_unchanged(self):
        batch = _make_batch(_open_intent(0))
        bars = [_price_bar(0, 10_000.0)]
        cfg = _default_config(cash=10_000.0, qty=2.0)
        result = run_simulation(batch, bars, cfg)
        assert result.equity_curve[0].equity == pytest.approx(10_000.0)


# ---------------------------------------------------------------------------
# 16. run_simulation — empty intent batch
# ---------------------------------------------------------------------------

class TestEmptyIntentBatch:
    def test_empty_batch_no_trades(self):
        batch = _make_batch()
        bars = [_price_bar(i, 100.0) for i in range(3)]
        result = run_simulation(batch, bars, _default_config())
        assert len(result.trades) == 0
        assert len(result.rejections) == 0

    def test_empty_batch_equity_curve_length(self):
        batch = _make_batch()
        bars = [_price_bar(i, 100.0) for i in range(5)]
        result = run_simulation(batch, bars, _default_config())
        assert len(result.equity_curve) == 5

    def test_empty_price_bars_no_equity_points(self):
        batch = _make_batch()
        result = run_simulation(batch, [], _default_config())
        assert len(result.equity_curve) == 0


# ---------------------------------------------------------------------------
# 17. run_simulation — summary correctness
# ---------------------------------------------------------------------------

class TestSummaryCorrectness:
    def test_summary_initial_cash(self):
        batch = _make_batch()
        result = run_simulation(batch, [_price_bar(0, 100.0)], _default_config(cash=5_000.0))
        assert result.summary.initial_cash == pytest.approx(5_000.0)

    def test_summary_total_bars(self):
        batch = _make_batch()
        bars = [_price_bar(i, 100.0) for i in range(7)]
        result = run_simulation(batch, bars, _default_config())
        assert result.summary.total_bars == 7

    def test_summary_total_trades(self):
        batch = _make_batch(_open_intent(0), _close_intent(1))
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, _default_config())
        assert result.summary.total_trades == 2
        assert result.summary.open_long_trades == 1
        assert result.summary.close_long_trades == 1

    def test_summary_total_rejections(self):
        batch = _make_batch(_close_intent(0), _close_intent(1))
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, _default_config())
        assert result.summary.total_rejections == 2

    def test_summary_final_cash_no_trades(self):
        batch = _make_batch()
        result = run_simulation(batch, [_price_bar(0, 100.0)], _default_config(cash=8_000.0))
        assert result.summary.final_cash == pytest.approx(8_000.0)

    def test_summary_final_equity_after_profit(self):
        batch = _make_batch(_open_intent(0), _close_intent(1))
        bars = [_price_bar(0, 100.0), _price_bar(1, 150.0)]
        cfg = _default_config(cash=10_000.0, qty=1.0)
        result = run_simulation(batch, bars, cfg)
        assert result.summary.final_equity == pytest.approx(10_050.0)


# ---------------------------------------------------------------------------
# 18. run_simulation — peak and trough equity
# ---------------------------------------------------------------------------

class TestPeakTroughEquity:
    def test_peak_equity_captured(self):
        batch = _make_batch(_open_intent(0))
        bars = [_price_bar(0, 100.0), _price_bar(1, 200.0), _price_bar(2, 50.0)]
        cfg = _default_config(cash=10_000.0, qty=1.0)
        result = run_simulation(batch, bars, cfg)
        # Bar 1: equity = 9900 + 200 = 10100
        # Bar 2: equity = 9900 + 50 = 9950
        assert result.summary.peak_equity == pytest.approx(10_100.0)

    def test_trough_equity_captured(self):
        batch = _make_batch(_open_intent(0))
        bars = [_price_bar(0, 100.0), _price_bar(1, 200.0), _price_bar(2, 50.0)]
        cfg = _default_config(cash=10_000.0, qty=1.0)
        result = run_simulation(batch, bars, cfg)
        # Bar 2: equity = 9900 + 50 = 9950
        assert result.summary.trough_equity == pytest.approx(9_950.0)

    def test_flat_equity_peak_equals_trough(self):
        batch = _make_batch()
        bars = [_price_bar(i, 100.0) for i in range(3)]
        result = run_simulation(batch, bars, _default_config(cash=10_000.0))
        assert result.summary.peak_equity == pytest.approx(10_000.0)
        assert result.summary.trough_equity == pytest.approx(10_000.0)

    def test_empty_bars_peak_trough_equal_initial_cash(self):
        batch = _make_batch()
        result = run_simulation(batch, [], _default_config(cash=5_000.0))
        assert result.summary.peak_equity == pytest.approx(5_000.0)
        assert result.summary.trough_equity == pytest.approx(5_000.0)


# ---------------------------------------------------------------------------
# 19. API endpoint tests
# ---------------------------------------------------------------------------

class TestBacktestSimulationAPI:
    def setup_method(self):
        app.dependency_overrides[require_active_subscription] = lambda: _TEST_USER

    def teardown_method(self):
        app.dependency_overrides.pop(require_active_subscription, None)

    def _build_request(
        self,
        intents: list[TradeIntent] | None = None,
        bars: list[dict] | None = None,
        config: dict | None = None,
    ) -> dict:
        if intents is None:
            intents = [_open_intent(0), _close_intent(1)]
        if bars is None:
            bars = [
                {"bar_index": 0, "timestamp": "2024-01-01T00:00:00Z", "close": 100.0},
                {"bar_index": 1, "timestamp": "2024-01-02T00:00:00Z", "close": 110.0},
            ]
        if config is None:
            config = {"initial_cash": 10000.0, "fixed_quantity": 1.0}
        batch = _make_batch(*intents)
        return {
            "intent_batch": batch.model_dump(mode="json"),
            "price_bars": bars,
            "config": config,
        }

    def test_valid_simulation_returns_200(self):
        resp = client.post("/backtests/simulate", json=self._build_request())
        assert resp.status_code == 200

    def test_response_has_required_fields(self):
        resp = client.post("/backtests/simulate", json=self._build_request())
        data = resp.json()
        assert "trades" in data
        assert "equity_curve" in data
        assert "rejections" in data
        assert "summary" in data
        assert "config" in data

    def test_two_trades_in_response(self):
        resp = client.post("/backtests/simulate", json=self._build_request())
        data = resp.json()
        assert len(data["trades"]) == 2

    def test_realized_pnl_in_summary(self):
        resp = client.post("/backtests/simulate", json=self._build_request())
        data = resp.json()
        assert data["summary"]["total_realized_pnl"] == pytest.approx(10.0)

    def test_invalid_config_negative_cash_returns_422(self):
        req = self._build_request(config={"initial_cash": -100.0, "fixed_quantity": 1.0})
        resp = client.post("/backtests/simulate", json=req)
        assert resp.status_code == 422

    def test_rejection_appears_in_response(self):
        # close while flat → rejection
        req = self._build_request(
            intents=[_close_intent(0)],
            bars=[{"bar_index": 0, "close": 100.0}],
        )
        resp = client.post("/backtests/simulate", json=req)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rejections"]) == 1
        assert data["rejections"][0]["reason"] == "already_flat"

    def test_empty_intents_no_trades(self):
        req = self._build_request(
            intents=[],
            bars=[{"bar_index": 0, "close": 100.0}],
        )
        resp = client.post("/backtests/simulate", json=req)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["trades"]) == 0

    def test_equity_curve_length_matches_bars(self):
        bars = [{"bar_index": i, "close": 100.0 + i} for i in range(5)]
        req = self._build_request(intents=[], bars=bars)
        resp = client.post("/backtests/simulate", json=req)
        data = resp.json()
        assert len(data["equity_curve"]) == 5

    def test_extra_fields_in_request_rejected(self):
        req = self._build_request()
        req["unexpected_field"] = "oops"
        resp = client.post("/backtests/simulate", json=req)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 20. Architecture guard tests
# ---------------------------------------------------------------------------

FORBIDDEN_MODULES = [
    "backend.strategy_runtime",
    "backend.execution",
    "backend.forward_testing",
]


def _get_source(module_path: str) -> str:
    import importlib
    mod = importlib.import_module(module_path)
    return inspect.getsource(mod)


def _assert_no_forbidden_imports(module_path: str) -> None:
    import re
    source = _get_source(module_path)
    import_lines = [
        line for line in source.splitlines()
        if re.match(r"\s*(import|from)\s+", line)
    ]
    for forbidden in FORBIDDEN_MODULES:
        for line in import_lines:
            assert forbidden not in line, (
                f"{module_path} must not import from {forbidden}; found: {line!r}"
            )


class TestArchitectureGuards:
    def test_models_no_forbidden_imports(self):
        _assert_no_forbidden_imports("backend.backtesting.models")

    def test_position_tracker_no_forbidden_imports(self):
        _assert_no_forbidden_imports("backend.backtesting.position_tracker")

    def test_simulator_no_forbidden_imports(self):
        _assert_no_forbidden_imports("backend.backtesting.simulator")

    def test_api_route_no_forbidden_imports(self):
        _assert_no_forbidden_imports("backend.api.routes.backtest_simulation")

    def test_api_service_no_forbidden_imports(self):
        _assert_no_forbidden_imports("backend.api.services.backtest_simulation_service")

    def test_models_no_short_sell_action(self):
        import re
        source = _get_source("backend.backtesting.models")
        code_lines = [
            line for line in source.splitlines()
            if not line.strip().startswith("#") and '"""' not in line and "'''" not in line
        ]
        code = "\n".join(code_lines)
        assert "short_sell" not in code
        assert "open_short" not in code

    def test_position_tracker_no_broker_concepts(self):
        import re
        source = _get_source("backend.backtesting.position_tracker")
        import_lines = [
            line for line in source.splitlines()
            if re.match(r"\s*(import|from)\s+", line)
        ]
        for line in import_lines:
            assert "broker" not in line
            assert "execution" not in line

    def test_simulator_no_execution_imports(self):
        _assert_no_forbidden_imports("backend.backtesting.simulator")

"""
Phase 2P.7 — Backtest Cost Model tests.

Coverage areas:
  1.  CommissionMode enum values
  2.  SlippageMode enum values
  3.  TradeCostBreakdown model (frozen, serializable)
  4.  compute_slippage_per_unit — NONE, FIXED, PERCENTAGE
  5.  apply_slippage — open_long direction (adverse up)
  6.  apply_slippage — close_long direction (adverse down)
  7.  apply_slippage — NONE produces raw close
  8.  compute_commission — NONE, FIXED, PERCENTAGE
  9.  build_cost_breakdown — open_long
  10. build_cost_breakdown — close_long
  11. BacktestSimulationConfig — cost field defaults
  12. BacktestSimulationConfig — cost field validation
  13. PositionState — cost fields initialized from config
  14. process_intent — zero-cost (NONE/NONE) preserved behavior
  15. process_intent — open_long with fixed slippage
  16. process_intent — open_long with percentage slippage
  17. process_intent — open_long with fixed commission
  18. process_intent — open_long with percentage commission
  19. process_intent — open_long insufficient cash after costs
  20. process_intent — close_long with fixed slippage + commission
  21. process_intent — realized PnL includes all costs
  22. process_intent — cost_breakdown fields on trade
  23. run_simulation — fixed slippage affects execution price
  24. run_simulation — percentage slippage affects execution price
  25. run_simulation — fixed commission deducted from cash
  26. run_simulation — percentage commission deducted from cash
  27. run_simulation — combined slippage + commission
  28. run_simulation — equity curve reflects costs
  29. run_simulation — summary cost totals correct
  30. run_simulation — average_cost_per_trade correct
  31. run_simulation — cumulative commission across trades
  32. run_simulation — insufficient cash after costs produces rejection
  33. run_simulation — zero-cost simulation unchanged from Phase 2P.6
  34. run_simulation — deterministic: identical inputs → identical outputs
  35. API endpoint — config with commission accepted
  36. API endpoint — config with slippage accepted
  37. API endpoint — negative commission_value rejected
  38. API endpoint — summary includes cost fields
  39. Architecture guard — cost_model no forbidden imports
  40. Architecture guard — cost model no broker concepts
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.auth.entitlement import require_active_subscription
from backend.auth.models import User
from backend.backtesting.cost_model import (
    CommissionMode,
    SlippageMode,
    TradeCostBreakdown,
    apply_slippage,
    build_cost_breakdown,
    compute_commission,
    compute_slippage_per_unit,
)
from backend.backtesting.models import (
    BacktestSimulationConfig,
    SimulationPriceBar,
)
from backend.backtesting.position_tracker import PositionState, process_intent
from backend.backtesting.simulator import run_simulation
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

_UTC = timezone.utc


def _ts(bar: int) -> datetime:
    return datetime(2024, 1, 1, tzinfo=_UTC) + timedelta(days=bar)


def _price_bar(bar_index: int, close: float) -> SimulationPriceBar:
    return SimulationPriceBar(bar_index=bar_index, timestamp=_ts(bar_index), close=close)


def _intent(bar_index: int, action: TradeIntentAction, rule_kind: str = "entry") -> TradeIntent:
    event_id = f"{bar_index}:{rule_kind}:0:r1"
    return TradeIntent(
        intent_id=f"intent:{event_id}",
        action=action,
        source=TradeIntentSource(
            signal_event_id=event_id,
            bar_index=bar_index,
            timestamp=_ts(bar_index),
            rule_id="r1",
            rule_kind=rule_kind,
        ),
    )


def _open(bar: int) -> TradeIntent:
    return _intent(bar, TradeIntentAction.OPEN_LONG, "entry")


def _close(bar: int) -> TradeIntent:
    return _intent(bar, TradeIntentAction.CLOSE_LONG, "exit")


def _batch(*intents: TradeIntent, draft_id: str | None = "d1") -> TradeIntentBatch:
    oc = sum(1 for i in intents if i.action == TradeIntentAction.OPEN_LONG)
    cc = sum(1 for i in intents if i.action == TradeIntentAction.CLOSE_LONG)
    return TradeIntentBatch(
        plan_draft_id=draft_id,
        intents=tuple(intents),
        summary=TradeIntentSummary(
            total_intents=len(intents), open_long_intents=oc, close_long_intents=cc,
            ignored_signal_events=0,
            first_intent_bar_index=intents[0].source.bar_index if intents else None,
            last_intent_bar_index=intents[-1].source.bar_index if intents else None,
        ),
        ignored_event_ids=(),
    )


def _state(
    cash: float = 10_000.0,
    qty: float = 1.0,
    commission_mode: CommissionMode = CommissionMode.NONE,
    commission_value: float = 0.0,
    slippage_mode: SlippageMode = SlippageMode.NONE,
    slippage_value: float = 0.0,
) -> PositionState:
    return PositionState(
        cash=cash,
        fixed_quantity=qty,
        commission_mode=commission_mode,
        commission_value=commission_value,
        slippage_mode=slippage_mode,
        slippage_value=slippage_value,
    )


def _cfg(
    cash: float = 10_000.0,
    qty: float = 1.0,
    commission_mode: CommissionMode = CommissionMode.NONE,
    commission_value: float = 0.0,
    slippage_mode: SlippageMode = SlippageMode.NONE,
    slippage_value: float = 0.0,
) -> BacktestSimulationConfig:
    return BacktestSimulationConfig(
        initial_cash=cash,
        fixed_quantity=qty,
        commission_mode=commission_mode,
        commission_value=commission_value,
        slippage_mode=slippage_mode,
        slippage_value=slippage_value,
    )


# ---------------------------------------------------------------------------
# 1. CommissionMode and SlippageMode enum values
# ---------------------------------------------------------------------------

class TestEnums:
    def test_commission_mode_values(self):
        assert CommissionMode.NONE == "none"
        assert CommissionMode.FIXED == "fixed"
        assert CommissionMode.PERCENTAGE == "percentage"

    def test_slippage_mode_values(self):
        assert SlippageMode.NONE == "none"
        assert SlippageMode.FIXED == "fixed"
        assert SlippageMode.PERCENTAGE == "percentage"

    def test_commission_mode_is_string_enum(self):
        assert isinstance(CommissionMode.FIXED, str)

    def test_slippage_mode_is_string_enum(self):
        assert isinstance(SlippageMode.PERCENTAGE, str)


# ---------------------------------------------------------------------------
# 2. TradeCostBreakdown model
# ---------------------------------------------------------------------------

class TestTradeCostBreakdown:
    def _make_zero(self) -> TradeCostBreakdown:
        return TradeCostBreakdown(
            raw_price=100.0, adjusted_price=100.0, gross_value=100.0,
            commission_paid=0.0, slippage_paid=0.0, total_cost=0.0,
            net_cash_impact=-100.0,
        )

    def test_frozen(self):
        bd = self._make_zero()
        with pytest.raises(Exception):
            bd.commission_paid = 99.0  # type: ignore[misc]

    def test_serializable(self):
        bd = self._make_zero()
        d = bd.model_dump()
        assert "commission_paid" in d
        assert "slippage_paid" in d
        assert "total_cost" in d
        assert "net_cash_impact" in d


# ---------------------------------------------------------------------------
# 3. compute_slippage_per_unit
# ---------------------------------------------------------------------------

class TestComputeSlippagePerUnit:
    def test_none_returns_zero(self):
        assert compute_slippage_per_unit(SlippageMode.NONE, 0.01, 100.0) == pytest.approx(0.0)

    def test_fixed_returns_value(self):
        assert compute_slippage_per_unit(SlippageMode.FIXED, 0.05, 100.0) == pytest.approx(0.05)

    def test_fixed_ignores_price(self):
        s1 = compute_slippage_per_unit(SlippageMode.FIXED, 0.05, 100.0)
        s2 = compute_slippage_per_unit(SlippageMode.FIXED, 0.05, 200.0)
        assert s1 == pytest.approx(s2)

    def test_percentage_of_price(self):
        slip = compute_slippage_per_unit(SlippageMode.PERCENTAGE, 0.001, 100.0)
        assert slip == pytest.approx(0.1)

    def test_percentage_scales_with_price(self):
        slip = compute_slippage_per_unit(SlippageMode.PERCENTAGE, 0.001, 200.0)
        assert slip == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# 4. apply_slippage — direction-aware
# ---------------------------------------------------------------------------

class TestApplySlippage:
    def test_none_open_long_no_adjustment(self):
        p = apply_slippage("open_long", 100.0, SlippageMode.NONE, 0.0)
        assert p == pytest.approx(100.0)

    def test_none_close_long_no_adjustment(self):
        p = apply_slippage("close_long", 100.0, SlippageMode.NONE, 0.0)
        assert p == pytest.approx(100.0)

    def test_fixed_open_long_price_increases(self):
        p = apply_slippage("open_long", 100.0, SlippageMode.FIXED, 0.05)
        assert p == pytest.approx(100.05)

    def test_fixed_close_long_price_decreases(self):
        p = apply_slippage("close_long", 100.0, SlippageMode.FIXED, 0.05)
        assert p == pytest.approx(99.95)

    def test_percentage_open_long_price_increases(self):
        p = apply_slippage("open_long", 100.0, SlippageMode.PERCENTAGE, 0.001)
        assert p == pytest.approx(100.1)

    def test_percentage_close_long_price_decreases(self):
        p = apply_slippage("close_long", 100.0, SlippageMode.PERCENTAGE, 0.001)
        assert p == pytest.approx(99.9)

    def test_price_floored_at_zero_for_close(self):
        p = apply_slippage("close_long", 0.01, SlippageMode.FIXED, 1.0)
        assert p >= 0.0


# ---------------------------------------------------------------------------
# 5. compute_commission
# ---------------------------------------------------------------------------

class TestComputeCommission:
    def test_none_returns_zero(self):
        assert compute_commission(CommissionMode.NONE, 1.0, 1.0, 100.0) == pytest.approx(0.0)

    def test_fixed_returns_flat_value(self):
        assert compute_commission(CommissionMode.FIXED, 1.50, 1.0, 100.0) == pytest.approx(1.50)

    def test_fixed_independent_of_notional(self):
        c1 = compute_commission(CommissionMode.FIXED, 1.50, 1.0, 100.0)
        c2 = compute_commission(CommissionMode.FIXED, 1.50, 5.0, 500.0)
        assert c1 == pytest.approx(c2)

    def test_percentage_of_notional(self):
        commission = compute_commission(CommissionMode.PERCENTAGE, 0.001, 1.0, 100.0)
        assert commission == pytest.approx(0.1)

    def test_percentage_scales_with_notional(self):
        commission = compute_commission(CommissionMode.PERCENTAGE, 0.001, 5.0, 500.0)
        assert commission == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 6. build_cost_breakdown
# ---------------------------------------------------------------------------

class TestBuildCostBreakdown:
    def test_open_long_net_cash_impact_negative(self):
        bd = build_cost_breakdown("open_long", 1.0, 100.0, 100.1, 1.0)
        assert bd.net_cash_impact < 0

    def test_open_long_net_cash_impact_value(self):
        # gross_value = 1 × 100.1 = 100.1; commission = 1.0; impact = -(100.1 + 1.0) = -101.1
        bd = build_cost_breakdown("open_long", 1.0, 100.0, 100.1, 1.0)
        assert bd.net_cash_impact == pytest.approx(-101.1)

    def test_close_long_net_cash_impact_positive(self):
        bd = build_cost_breakdown("close_long", 1.0, 100.0, 99.9, 1.0)
        assert bd.net_cash_impact > 0

    def test_close_long_net_cash_impact_value(self):
        # gross_value = 1 × 99.9 = 99.9; commission = 1.0; impact = 99.9 - 1.0 = 98.9
        bd = build_cost_breakdown("close_long", 1.0, 100.0, 99.9, 1.0)
        assert bd.net_cash_impact == pytest.approx(98.9)

    def test_slippage_paid_is_absolute_difference(self):
        bd = build_cost_breakdown("open_long", 2.0, 100.0, 100.05, 0.0)
        assert bd.slippage_paid == pytest.approx(2.0 * 0.05)

    def test_total_cost_is_commission_plus_slippage(self):
        bd = build_cost_breakdown("open_long", 1.0, 100.0, 100.1, 1.0)
        assert bd.total_cost == pytest.approx(bd.commission_paid + bd.slippage_paid)

    def test_gross_value_is_qty_times_adjusted(self):
        bd = build_cost_breakdown("open_long", 3.0, 100.0, 100.1, 0.0)
        assert bd.gross_value == pytest.approx(3.0 * 100.1)

    def test_zero_cost_breakdown(self):
        bd = build_cost_breakdown("open_long", 1.0, 100.0, 100.0, 0.0)
        assert bd.commission_paid == pytest.approx(0.0)
        assert bd.slippage_paid == pytest.approx(0.0)
        assert bd.total_cost == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 7. BacktestSimulationConfig cost field defaults and validation
# ---------------------------------------------------------------------------

class TestConfigCostFields:
    def test_defaults_are_none_zero(self):
        cfg = BacktestSimulationConfig()
        assert cfg.commission_mode == CommissionMode.NONE
        assert cfg.commission_value == 0.0
        assert cfg.slippage_mode == SlippageMode.NONE
        assert cfg.slippage_value == 0.0

    def test_fixed_commission_config(self):
        cfg = _cfg(commission_mode=CommissionMode.FIXED, commission_value=1.0)
        assert cfg.commission_mode == CommissionMode.FIXED
        assert cfg.commission_value == pytest.approx(1.0)

    def test_percentage_slippage_config(self):
        cfg = _cfg(slippage_mode=SlippageMode.PERCENTAGE, slippage_value=0.001)
        assert cfg.slippage_mode == SlippageMode.PERCENTAGE
        assert cfg.slippage_value == pytest.approx(0.001)

    def test_negative_commission_value_rejected(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(commission_mode=CommissionMode.FIXED, commission_value=-1.0)

    def test_negative_slippage_value_rejected(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(slippage_mode=SlippageMode.FIXED, slippage_value=-0.01)

    def test_zero_commission_value_allowed(self):
        cfg = BacktestSimulationConfig(commission_mode=CommissionMode.FIXED, commission_value=0.0)
        assert cfg.commission_value == 0.0


# ---------------------------------------------------------------------------
# 8. process_intent — zero-cost (NONE/NONE) preserved behavior
# ---------------------------------------------------------------------------

class TestProcessIntentZeroCost:
    def test_open_long_zero_cost_cash_unchanged_from_phase6(self):
        state = _state(cash=10_000.0, qty=1.0)
        trade, _ = process_intent(_open(0), price=100.0, state=state)
        assert state.cash == pytest.approx(9_900.0)
        assert trade.price == pytest.approx(100.0)

    def test_open_long_zero_cost_breakdown_all_zero(self):
        state = _state(cash=10_000.0, qty=1.0)
        trade, _ = process_intent(_open(0), price=100.0, state=state)
        assert trade.cost_breakdown.commission_paid == pytest.approx(0.0)
        assert trade.cost_breakdown.slippage_paid == pytest.approx(0.0)
        assert trade.cost_breakdown.total_cost == pytest.approx(0.0)

    def test_close_long_zero_cost_realized_pnl(self):
        state = _state(cash=9_000.0, qty=1.0)
        state.position_quantity = 1.0
        state.average_entry_price = 100.0
        trade, _ = process_intent(_close(1), price=110.0, state=state)
        assert trade.realized_pnl == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# 9. process_intent — fixed slippage
# ---------------------------------------------------------------------------

class TestProcessIntentFixedSlippage:
    def test_open_long_adjusted_price_higher(self):
        state = _state(slippage_mode=SlippageMode.FIXED, slippage_value=0.05)
        trade, _ = process_intent(_open(0), price=100.0, state=state)
        assert trade.price == pytest.approx(100.05)

    def test_open_long_cash_deducts_at_adjusted_price(self):
        state = _state(cash=10_000.0, qty=1.0, slippage_mode=SlippageMode.FIXED, slippage_value=0.05)
        process_intent(_open(0), price=100.0, state=state)
        assert state.cash == pytest.approx(9_899.95)

    def test_close_long_adjusted_price_lower(self):
        state = _state(slippage_mode=SlippageMode.FIXED, slippage_value=0.05)
        state.position_quantity = 1.0
        state.average_entry_price = 100.05
        trade, _ = process_intent(_close(1), price=110.0, state=state)
        assert trade.price == pytest.approx(109.95)

    def test_open_long_slippage_paid_is_slip_times_qty(self):
        state = _state(qty=2.0, slippage_mode=SlippageMode.FIXED, slippage_value=0.05)
        trade, _ = process_intent(_open(0), price=100.0, state=state)
        assert trade.cost_breakdown.slippage_paid == pytest.approx(0.05 * 2.0)


# ---------------------------------------------------------------------------
# 10. process_intent — percentage slippage
# ---------------------------------------------------------------------------

class TestProcessIntentPercentageSlippage:
    def test_open_long_adjusted_price(self):
        state = _state(slippage_mode=SlippageMode.PERCENTAGE, slippage_value=0.001)
        trade, _ = process_intent(_open(0), price=100.0, state=state)
        assert trade.price == pytest.approx(100.1)

    def test_close_long_adjusted_price(self):
        state = _state(slippage_mode=SlippageMode.PERCENTAGE, slippage_value=0.001)
        state.position_quantity = 1.0
        state.average_entry_price = 100.1
        trade, _ = process_intent(_close(1), price=100.0, state=state)
        assert trade.price == pytest.approx(99.9)


# ---------------------------------------------------------------------------
# 11. process_intent — fixed commission
# ---------------------------------------------------------------------------

class TestProcessIntentFixedCommission:
    def test_open_long_commission_deducted(self):
        state = _state(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.50)
        process_intent(_open(0), price=100.0, state=state)
        # cash = 10000 - 100 - 1.50 = 9898.50
        assert state.cash == pytest.approx(9_898.50)

    def test_open_long_commission_in_breakdown(self):
        state = _state(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.50)
        trade, _ = process_intent(_open(0), price=100.0, state=state)
        assert trade.cost_breakdown.commission_paid == pytest.approx(1.50)

    def test_close_long_commission_deducted_from_proceeds(self):
        state = _state(cash=9_000.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.0)
        state.position_quantity = 1.0
        state.average_entry_price = 100.0
        state.entry_commission = 1.0
        process_intent(_close(1), price=110.0, state=state)
        # proceeds = 110 - 1 = 109; cash = 9000 + 109 = 9109
        assert state.cash == pytest.approx(9_109.0)

    def test_close_long_realized_pnl_includes_commissions(self):
        state = _state(cash=9_000.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.0)
        state.position_quantity = 1.0
        state.average_entry_price = 100.0
        state.entry_commission = 1.0
        trade, _ = process_intent(_close(1), price=110.0, state=state)
        # pnl = (110 - 100) × 1 - 1 (close_comm) - 1 (entry_comm) = 8
        assert trade.realized_pnl == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# 12. process_intent — percentage commission
# ---------------------------------------------------------------------------

class TestProcessIntentPercentageCommission:
    def test_open_long_percentage_commission(self):
        state = _state(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.PERCENTAGE, commission_value=0.001)
        trade, _ = process_intent(_open(0), price=100.0, state=state)
        # notional = 100; commission = 100 * 0.001 = 0.10
        assert trade.cost_breakdown.commission_paid == pytest.approx(0.10)

    def test_open_long_percentage_commission_cash_deducted(self):
        state = _state(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.PERCENTAGE, commission_value=0.001)
        process_intent(_open(0), price=100.0, state=state)
        assert state.cash == pytest.approx(9_899.90)


# ---------------------------------------------------------------------------
# 13. process_intent — insufficient cash after costs
# ---------------------------------------------------------------------------

class TestProcessIntentInsufficientCashWithCosts:
    def test_insufficient_cash_due_to_commission(self):
        # cash = 100, price = 100, commission = 1.50 → need 101.50
        state = _state(cash=100.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.50)
        trade, rejection = process_intent(_open(0), price=100.0, state=state)
        assert trade is None
        assert rejection is not None
        from backend.backtesting.models import BacktestRejectionReason
        assert rejection.reason == BacktestRejectionReason.INSUFFICIENT_CASH

    def test_insufficient_cash_due_to_slippage(self):
        # cash = 100, price = 100, slippage = 1 → need 101
        state = _state(cash=100.0, qty=1.0, slippage_mode=SlippageMode.FIXED, slippage_value=1.0)
        trade, rejection = process_intent(_open(0), price=100.0, state=state)
        assert trade is None
        assert rejection is not None

    def test_exact_cash_with_costs_succeeds(self):
        # cash = 101.50, price = 100, commission = 1.50 → exact
        state = _state(cash=101.50, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.50)
        trade, rejection = process_intent(_open(0), price=100.0, state=state)
        assert trade is not None
        assert rejection is None


# ---------------------------------------------------------------------------
# 14. run_simulation — slippage integration
# ---------------------------------------------------------------------------

class TestRunSimulationSlippage:
    def test_fixed_slippage_affects_open_price(self):
        cfg = _cfg(slippage_mode=SlippageMode.FIXED, slippage_value=0.05)
        result = run_simulation(_batch(_open(0)), [_price_bar(0, 100.0)], cfg)
        assert result.trades[0].price == pytest.approx(100.05)

    def test_fixed_slippage_affects_close_price(self):
        cfg = _cfg(slippage_mode=SlippageMode.FIXED, slippage_value=0.05)
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        assert result.trades[1].price == pytest.approx(109.95)

    def test_percentage_slippage_open(self):
        cfg = _cfg(slippage_mode=SlippageMode.PERCENTAGE, slippage_value=0.01)
        result = run_simulation(_batch(_open(0)), [_price_bar(0, 200.0)], cfg)
        assert result.trades[0].price == pytest.approx(202.0)

    def test_percentage_slippage_close(self):
        cfg = _cfg(cash=10_000.0, qty=1.0,
                   slippage_mode=SlippageMode.PERCENTAGE, slippage_value=0.01)
        bars = [_price_bar(0, 100.0), _price_bar(1, 200.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        assert result.trades[1].price == pytest.approx(198.0)


# ---------------------------------------------------------------------------
# 15. run_simulation — commission integration
# ---------------------------------------------------------------------------

class TestRunSimulationCommission:
    def test_fixed_commission_deducted_at_open(self):
        cfg = _cfg(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=2.0)
        result = run_simulation(_batch(_open(0)), [_price_bar(0, 100.0)], cfg)
        # cash = 10000 - 100 - 2 = 9898
        assert result.equity_curve[0].cash == pytest.approx(9_898.0)

    def test_fixed_commission_deducted_at_close(self):
        cfg = _cfg(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=2.0)
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        # After open: cash = 9898
        # After close: proceeds = 110 - 2 = 108; cash = 9898 + 108 = 10006
        assert result.equity_curve[1].cash == pytest.approx(10_006.0)

    def test_percentage_commission_affects_cash(self):
        cfg = _cfg(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.PERCENTAGE, commission_value=0.01)
        result = run_simulation(_batch(_open(0)), [_price_bar(0, 100.0)], cfg)
        # commission = 100 * 0.01 = 1.0; cash = 10000 - 100 - 1 = 9899
        assert result.equity_curve[0].cash == pytest.approx(9_899.0)


# ---------------------------------------------------------------------------
# 16. run_simulation — realized PnL with costs
# ---------------------------------------------------------------------------

class TestRunSimulationPnLWithCosts:
    def test_realized_pnl_after_round_trip_with_fixed_commission(self):
        cfg = _cfg(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.0)
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        # pnl = (110 - 100) × 1 - 1 (close) - 1 (open) = 8
        assert result.summary.total_realized_pnl == pytest.approx(8.0)

    def test_realized_pnl_after_round_trip_with_slippage(self):
        cfg = _cfg(cash=10_000.0, qty=1.0, slippage_mode=SlippageMode.FIXED, slippage_value=0.10)
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        # open at 100.10, close at 109.90
        # pnl = (109.90 - 100.10) × 1 = 9.80 (no commission)
        assert result.summary.total_realized_pnl == pytest.approx(9.80)

    def test_realized_pnl_zero_cost_matches_price_diff(self):
        cfg = _cfg(cash=10_000.0, qty=1.0)
        bars = [_price_bar(0, 100.0), _price_bar(1, 115.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        assert result.summary.total_realized_pnl == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# 17. run_simulation — summary cost totals
# ---------------------------------------------------------------------------

class TestRunSimulationSummaryCosts:
    def test_total_commission_paid_two_trades(self):
        cfg = _cfg(commission_mode=CommissionMode.FIXED, commission_value=1.50)
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        assert result.summary.total_commission_paid == pytest.approx(3.0)  # 1.5 + 1.5

    def test_total_slippage_paid_two_trades(self):
        cfg = _cfg(qty=1.0, slippage_mode=SlippageMode.FIXED, slippage_value=0.05)
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        assert result.summary.total_slippage_paid == pytest.approx(0.10)  # 0.05 + 0.05

    def test_total_cost_paid_is_commission_plus_slippage(self):
        cfg = _cfg(
            commission_mode=CommissionMode.FIXED, commission_value=1.0,
            slippage_mode=SlippageMode.FIXED, slippage_value=0.05,
        )
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        s = result.summary
        assert s.total_cost_paid == pytest.approx(s.total_commission_paid + s.total_slippage_paid)

    def test_average_cost_per_trade(self):
        cfg = _cfg(commission_mode=CommissionMode.FIXED, commission_value=2.0)
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, cfg)
        # total_cost = 4.0 (2 × 2.0 commission, 0 slippage); avg = 4.0 / 2 = 2.0
        assert result.summary.average_cost_per_trade == pytest.approx(2.0)

    def test_zero_trades_average_cost_is_zero(self):
        result = run_simulation(_batch(), [_price_bar(0, 100.0)], _cfg())
        assert result.summary.average_cost_per_trade == pytest.approx(0.0)

    def test_zero_cost_config_all_cost_fields_zero(self):
        bars = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(_batch(_open(0), _close(1)), bars, _cfg())
        assert result.summary.total_commission_paid == pytest.approx(0.0)
        assert result.summary.total_slippage_paid == pytest.approx(0.0)
        assert result.summary.total_cost_paid == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 18. run_simulation — equity curve with costs
# ---------------------------------------------------------------------------

class TestRunSimulationEquityWithCosts:
    def test_equity_correct_after_open_with_commission(self):
        cfg = _cfg(cash=10_000.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.0)
        result = run_simulation(_batch(_open(0)), [_price_bar(0, 100.0)], cfg)
        # cash = 10000 - 100 - 1 = 9899; market_value = 1 × 100 = 100; equity = 9999
        p0 = result.equity_curve[0]
        assert p0.cash == pytest.approx(9_899.0)
        assert p0.equity == pytest.approx(9_999.0)  # commission reduces equity

    def test_equity_reflects_slippage_at_open(self):
        cfg = _cfg(cash=10_000.0, qty=1.0, slippage_mode=SlippageMode.FIXED, slippage_value=0.10)
        result = run_simulation(_batch(_open(0)), [_price_bar(0, 100.0)], cfg)
        # open at 100.10; cash = 10000 - 100.10 = 9899.90
        # market_value uses raw close = 100; equity = 9899.90 + 100 = 9999.90
        p0 = result.equity_curve[0]
        assert p0.equity == pytest.approx(9_999.90)

    def test_insufficient_cash_after_costs_produces_rejection(self):
        # cash = 100, price = 100, commission = 1 → need 101
        cfg = _cfg(cash=100.0, qty=1.0, commission_mode=CommissionMode.FIXED, commission_value=1.0)
        result = run_simulation(_batch(_open(0)), [_price_bar(0, 100.0)], cfg)
        assert len(result.trades) == 0
        assert len(result.rejections) == 1


# ---------------------------------------------------------------------------
# 19. run_simulation — determinism
# ---------------------------------------------------------------------------

class TestRunSimulationDeterminism:
    def test_identical_inputs_produce_identical_outputs(self):
        cfg = _cfg(
            commission_mode=CommissionMode.FIXED, commission_value=1.0,
            slippage_mode=SlippageMode.FIXED, slippage_value=0.05,
        )
        bars = [_price_bar(i, 100.0 + i * 2) for i in range(5)]
        batch = _batch(_open(0), _close(2), _open(3), _close(4))
        r1 = run_simulation(batch, bars, cfg)
        r2 = run_simulation(batch, bars, cfg)
        assert r1.model_dump() == r2.model_dump()


# ---------------------------------------------------------------------------
# 20. API endpoint tests
# ---------------------------------------------------------------------------

class TestCostModelAPI:
    def setup_method(self):
        app.dependency_overrides[require_active_subscription] = lambda: _TEST_USER

    def teardown_method(self):
        app.dependency_overrides.pop(require_active_subscription, None)

    def _req(self, intents, bars, config) -> dict:
        batch = _batch(*intents)
        return {
            "intent_batch": batch.model_dump(mode="json"),
            "price_bars": bars,
            "config": config,
        }

    def test_config_with_commission_accepted(self):
        req = self._req(
            intents=[_open(0), _close(1)],
            bars=[{"bar_index": 0, "close": 100.0}, {"bar_index": 1, "close": 110.0}],
            config={"initial_cash": 10000.0, "fixed_quantity": 1.0,
                    "commission_mode": "fixed", "commission_value": 1.0},
        )
        resp = client.post("/backtests/simulate", json=req)
        assert resp.status_code == 200

    def test_config_with_slippage_accepted(self):
        req = self._req(
            intents=[_open(0)],
            bars=[{"bar_index": 0, "close": 100.0}],
            config={"initial_cash": 10000.0, "fixed_quantity": 1.0,
                    "slippage_mode": "fixed", "slippage_value": 0.05},
        )
        resp = client.post("/backtests/simulate", json=req)
        assert resp.status_code == 200

    def test_negative_commission_value_rejected(self):
        req = self._req(
            intents=[],
            bars=[{"bar_index": 0, "close": 100.0}],
            config={"initial_cash": 10000.0, "fixed_quantity": 1.0,
                    "commission_mode": "fixed", "commission_value": -1.0},
        )
        resp = client.post("/backtests/simulate", json=req)
        assert resp.status_code == 422

    def test_summary_includes_cost_fields(self):
        req = self._req(
            intents=[_open(0), _close(1)],
            bars=[{"bar_index": 0, "close": 100.0}, {"bar_index": 1, "close": 110.0}],
            config={"initial_cash": 10000.0, "fixed_quantity": 1.0,
                    "commission_mode": "fixed", "commission_value": 1.0},
        )
        resp = client.post("/backtests/simulate", json=req)
        data = resp.json()
        assert "total_commission_paid" in data["summary"]
        assert "total_slippage_paid" in data["summary"]
        assert "total_cost_paid" in data["summary"]
        assert "average_cost_per_trade" in data["summary"]
        assert data["summary"]["total_commission_paid"] == pytest.approx(2.0)

    def test_trade_includes_cost_breakdown(self):
        req = self._req(
            intents=[_open(0)],
            bars=[{"bar_index": 0, "close": 100.0}],
            config={"initial_cash": 10000.0, "fixed_quantity": 1.0,
                    "commission_mode": "fixed", "commission_value": 1.50},
        )
        resp = client.post("/backtests/simulate", json=req)
        data = resp.json()
        trade = data["trades"][0]
        assert "cost_breakdown" in trade
        assert trade["cost_breakdown"]["commission_paid"] == pytest.approx(1.50)


# ---------------------------------------------------------------------------
# 21. Architecture guard tests
# ---------------------------------------------------------------------------

FORBIDDEN_MODULES = [
    "backend.strategy_runtime",
    "backend.execution",
    "backend.forward_testing",
]


def _import_lines(module_path: str) -> list[str]:
    import re, importlib
    mod = importlib.import_module(module_path)
    source = inspect.getsource(mod)
    return [line for line in source.splitlines() if re.match(r"\s*(import|from)\s+", line)]


class TestCostModelArchitectureGuards:
    def test_cost_model_no_forbidden_imports(self):
        lines = _import_lines("backend.backtesting.cost_model")
        for forbidden in FORBIDDEN_MODULES:
            for line in lines:
                assert forbidden not in line

    def test_cost_model_no_broker_concepts_in_imports(self):
        lines = _import_lines("backend.backtesting.cost_model")
        for line in lines:
            assert "broker" not in line
            assert "execution" not in line

    def test_models_no_forbidden_imports(self):
        lines = _import_lines("backend.backtesting.models")
        for forbidden in FORBIDDEN_MODULES:
            for line in lines:
                assert forbidden not in line

    def test_position_tracker_no_forbidden_imports(self):
        lines = _import_lines("backend.backtesting.position_tracker")
        for forbidden in FORBIDDEN_MODULES:
            for line in lines:
                assert forbidden not in line

    def test_simulator_no_forbidden_imports(self):
        lines = _import_lines("backend.backtesting.simulator")
        for forbidden in FORBIDDEN_MODULES:
            for line in lines:
                assert forbidden not in line

    def test_cost_model_no_stochastic_imports(self):
        lines = _import_lines("backend.backtesting.cost_model")
        for line in lines:
            assert "random" not in line
            assert "numpy" not in line

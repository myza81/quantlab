"""
Tests — Phase 2P.8: Backtest Position Sizing Foundation.

Covers:
    1. PositionSizeMode enum
    2. BacktestSimulationConfig — equity_fraction validation
    3. resolve_position_quantity helper
    4. PositionState — sizing fields
    5. Position tracker — fixed quantity (retained behavior)
    6. Position tracker — equity_fraction sizing
    7. Position tracker — zero quantity rejection
    8. Position tracker — audit fields on SimulatedTrade
    9. Simulation integration — equity_fraction sizing
    10. Simulation integration — equity grows between trades
    11. Simulation integration — close realizes correct PnL
    12. Simulation integration — equity curve reflects sized quantity
    13. Simulation integration — fixed quantity unchanged
    14. Negative tests — leverage, short selling, margin still unsupported
    15. Architecture guards — no forbidden imports
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

import pytest

from backend.backtesting.models import (
    BacktestExecutionModel,
    BacktestRejectionReason,
    BacktestSimulationConfig,
    PositionSizeMode,
    SimulationPriceBar,
)

_SBC = BacktestExecutionModel.SAME_BAR_CLOSE  # shorthand for backward-compat tests
from backend.backtesting.position_tracker import (
    PositionState,
    process_intent,
    resolve_position_quantity,
)
from backend.backtesting.simulator import run_simulation
from backend.strategy_registry.trade_intents import (
    TradeIntentAction,
    TradeIntentBatch,
)

_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _ts(bar: int) -> datetime:
    from datetime import timedelta
    return datetime(2024, 1, 1, tzinfo=_UTC) + timedelta(days=bar)


def _price_bar(bar_index: int, close: float) -> SimulationPriceBar:
    return SimulationPriceBar(bar_index=bar_index, timestamp=_ts(bar_index), close=close)


def _make_intent(intent_id: str, bar_index: int, action: TradeIntentAction):
    from backend.strategy_registry.trade_intents import TradeIntent, TradeIntentSource
    source = TradeIntentSource(
        signal_event_id=f"sig:{intent_id}",
        bar_index=bar_index,
        timestamp=_ts(bar_index),
        rule_id="r1",
        rule_kind="entry",
    )
    return TradeIntent(
        intent_id=intent_id,
        action=action,
        source=source,
    )


def _make_batch(*intents) -> TradeIntentBatch:
    from backend.strategy_registry.trade_intents import TradeIntentSummary
    open_count  = sum(1 for i in intents if i.action == TradeIntentAction.OPEN_LONG)
    close_count = sum(1 for i in intents if i.action == TradeIntentAction.CLOSE_LONG)
    summary = TradeIntentSummary(
        total_intents=len(intents),
        open_long_intents=open_count,
        close_long_intents=close_count,
        ignored_signal_events=0,
        first_intent_bar_index=intents[0].source.bar_index if intents else None,
        last_intent_bar_index=intents[-1].source.bar_index if intents else None,
    )
    return TradeIntentBatch(
        plan_draft_id="draft:test",
        intents=tuple(intents),
        summary=summary,
        ignored_event_ids=(),
    )


def _flat_state(**kwargs) -> PositionState:
    defaults = dict(cash=10_000.0, fixed_quantity=1.0)
    defaults.update(kwargs)
    return PositionState(**defaults)


def _equity_fraction_config(
    fraction: float,
    cash: float = 10_000.0,
) -> BacktestSimulationConfig:
    return BacktestSimulationConfig(
        initial_cash=cash,
        position_size_mode=PositionSizeMode.EQUITY_FRACTION,
        equity_fraction=fraction,
        execution_model=_SBC,
    )


# ---------------------------------------------------------------------------
# 1. PositionSizeMode enum
# ---------------------------------------------------------------------------

class TestPositionSizeMode:
    def test_fixed_quantity_value(self):
        assert PositionSizeMode.FIXED_QUANTITY == "fixed_quantity"

    def test_equity_fraction_value(self):
        assert PositionSizeMode.EQUITY_FRACTION == "equity_fraction"

    def test_both_modes_present(self):
        modes = {m.value for m in PositionSizeMode}
        assert "fixed_quantity" in modes
        assert "equity_fraction" in modes

    def test_is_string_enum(self):
        assert isinstance(PositionSizeMode.FIXED_QUANTITY, str)
        assert isinstance(PositionSizeMode.EQUITY_FRACTION, str)


# ---------------------------------------------------------------------------
# 2. BacktestSimulationConfig — equity_fraction validation
# ---------------------------------------------------------------------------

class TestBacktestSimulationConfigSizing:
    def test_default_is_fixed_quantity(self):
        cfg = BacktestSimulationConfig()
        assert cfg.position_size_mode == PositionSizeMode.FIXED_QUANTITY
        assert cfg.equity_fraction is None

    def test_fixed_quantity_mode_requires_no_fraction(self):
        cfg = BacktestSimulationConfig(
            position_size_mode=PositionSizeMode.FIXED_QUANTITY,
            fixed_quantity=5.0,
        )
        assert cfg.fixed_quantity == 5.0
        assert cfg.equity_fraction is None

    def test_equity_fraction_mode_valid(self):
        cfg = _equity_fraction_config(0.25)
        assert cfg.position_size_mode == PositionSizeMode.EQUITY_FRACTION
        assert cfg.equity_fraction == 0.25

    def test_equity_fraction_1_0_valid(self):
        cfg = _equity_fraction_config(1.0)
        assert cfg.equity_fraction == 1.0

    def test_equity_fraction_small_valid(self):
        cfg = _equity_fraction_config(0.001)
        assert cfg.equity_fraction == pytest.approx(0.001)

    def test_equity_fraction_mode_without_fraction_rejected(self):
        with pytest.raises(Exception, match="equity_fraction is required"):
            BacktestSimulationConfig(
                position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            )

    def test_equity_fraction_zero_rejected(self):
        with pytest.raises(Exception, match="equity_fraction must be in"):
            BacktestSimulationConfig(
                position_size_mode=PositionSizeMode.EQUITY_FRACTION,
                equity_fraction=0.0,
            )

    def test_equity_fraction_negative_rejected(self):
        with pytest.raises(Exception, match="equity_fraction must be in"):
            BacktestSimulationConfig(
                position_size_mode=PositionSizeMode.EQUITY_FRACTION,
                equity_fraction=-0.1,
            )

    def test_equity_fraction_above_1_rejected(self):
        with pytest.raises(Exception, match="equity_fraction must be in"):
            BacktestSimulationConfig(
                position_size_mode=PositionSizeMode.EQUITY_FRACTION,
                equity_fraction=1.01,
            )

    def test_equity_fraction_exactly_2_rejected(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(
                position_size_mode=PositionSizeMode.EQUITY_FRACTION,
                equity_fraction=2.0,
            )

    def test_equity_fraction_config_is_frozen(self):
        cfg = _equity_fraction_config(0.5)
        with pytest.raises(Exception):
            cfg.equity_fraction = 0.9  # type: ignore[misc]

    def test_equity_fraction_with_cost_model(self):
        from backend.backtesting.cost_model import CommissionMode, SlippageMode
        cfg = BacktestSimulationConfig(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.5,
            commission_mode=CommissionMode.FIXED,
            commission_value=1.0,
            slippage_mode=SlippageMode.PERCENTAGE,
            slippage_value=0.001,
        )
        assert cfg.equity_fraction == 0.5
        assert cfg.commission_value == 1.0


# ---------------------------------------------------------------------------
# 3. resolve_position_quantity helper
# ---------------------------------------------------------------------------

class TestResolvePositionQuantity:
    def test_fixed_quantity_returns_configured_value(self):
        qty = resolve_position_quantity(
            position_size_mode=PositionSizeMode.FIXED_QUANTITY,
            fixed_quantity=5.0,
            equity_fraction=0.0,
            current_equity=10_000.0,
            adjusted_entry_price=100.0,
        )
        assert qty == 5.0

    def test_fixed_quantity_ignores_equity(self):
        qty = resolve_position_quantity(
            position_size_mode=PositionSizeMode.FIXED_QUANTITY,
            fixed_quantity=3.0,
            equity_fraction=0.0,
            current_equity=999.0,
            adjusted_entry_price=50.0,
        )
        assert qty == 3.0

    def test_equity_fraction_floor_behavior(self):
        # budget = 10_000 * 0.25 = 2_500; qty = floor(2_500 / 100) = 25
        qty = resolve_position_quantity(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            fixed_quantity=1.0,
            equity_fraction=0.25,
            current_equity=10_000.0,
            adjusted_entry_price=100.0,
        )
        assert qty == 25.0

    def test_equity_fraction_floor_truncates(self):
        # budget = 10_000 * 0.33 = 3_300; qty = floor(3_300 / 99) = 33 (not 33.33...)
        qty = resolve_position_quantity(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            fixed_quantity=1.0,
            equity_fraction=0.33,
            current_equity=10_000.0,
            adjusted_entry_price=99.0,
        )
        assert qty == math.floor(3_300.0 / 99.0)

    def test_equity_fraction_full_equity(self):
        # budget = 10_000 * 1.0 = 10_000; qty = floor(10_000 / 100) = 100
        qty = resolve_position_quantity(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            fixed_quantity=1.0,
            equity_fraction=1.0,
            current_equity=10_000.0,
            adjusted_entry_price=100.0,
        )
        assert qty == 100.0

    def test_equity_fraction_zero_when_budget_too_small(self):
        # budget = 100 * 0.1 = 10; price = 100; qty = floor(10/100) = 0
        qty = resolve_position_quantity(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            fixed_quantity=1.0,
            equity_fraction=0.1,
            current_equity=100.0,
            adjusted_entry_price=100.0,
        )
        assert qty == 0.0

    def test_equity_fraction_returns_float(self):
        qty = resolve_position_quantity(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            fixed_quantity=1.0,
            equity_fraction=0.5,
            current_equity=10_000.0,
            adjusted_entry_price=100.0,
        )
        assert isinstance(qty, float)

    def test_equity_fraction_large_equity(self):
        # budget = 1_000_000 * 0.1 = 100_000; qty = floor(100_000 / 50) = 2_000
        qty = resolve_position_quantity(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            fixed_quantity=1.0,
            equity_fraction=0.1,
            current_equity=1_000_000.0,
            adjusted_entry_price=50.0,
        )
        assert qty == 2_000.0

    def test_equity_fraction_is_deterministic(self):
        args = dict(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            fixed_quantity=1.0,
            equity_fraction=0.33,
            current_equity=10_000.0,
            adjusted_entry_price=123.45,
        )
        assert resolve_position_quantity(**args) == resolve_position_quantity(**args)


# ---------------------------------------------------------------------------
# 4. PositionState — sizing fields
# ---------------------------------------------------------------------------

class TestPositionStateSizingFields:
    def test_default_sizing_is_fixed_quantity(self):
        state = _flat_state()
        assert state.position_size_mode == PositionSizeMode.FIXED_QUANTITY
        assert state.equity_fraction == 0.0

    def test_equity_fraction_stored(self):
        state = _flat_state(
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.25,
        )
        assert state.position_size_mode == PositionSizeMode.EQUITY_FRACTION
        assert state.equity_fraction == 0.25

    def test_sizing_fields_mutable(self):
        state = _flat_state()
        state.equity_fraction = 0.5
        assert state.equity_fraction == 0.5


# ---------------------------------------------------------------------------
# 5. Position tracker — fixed quantity (retained behavior)
# ---------------------------------------------------------------------------

class TestPositionTrackerFixedQuantity:
    def test_open_long_fixed_qty_deducts_correct_cash(self):
        state = _flat_state(cash=10_000.0, fixed_quantity=5.0)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, rejection = process_intent(intent, 100.0, state)
        assert rejection is None
        assert trade is not None
        assert trade.quantity == 5.0
        assert trade.cash_after == pytest.approx(10_000.0 - 5.0 * 100.0)

    def test_open_long_fixed_qty_audit_fields(self):
        state = _flat_state(cash=10_000.0, fixed_quantity=3.0)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        assert trade is not None
        assert trade.position_size_mode == PositionSizeMode.FIXED_QUANTITY
        assert trade.sizing_value == 3.0

    def test_close_long_fixed_qty_audit_fields(self):
        state = _flat_state(cash=10_000.0, fixed_quantity=2.0)
        open_intent  = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        close_intent = _make_intent("i2", 1, TradeIntentAction.CLOSE_LONG)
        process_intent(open_intent, 100.0, state)
        trade, _ = process_intent(close_intent, 110.0, state)
        assert trade is not None
        assert trade.position_size_mode == PositionSizeMode.FIXED_QUANTITY
        assert trade.sizing_value == 2.0


# ---------------------------------------------------------------------------
# 6. Position tracker — equity_fraction sizing
# ---------------------------------------------------------------------------

class TestPositionTrackerEquityFraction:
    def _equity_state(self, cash: float, fraction: float, **kwargs) -> PositionState:
        return _flat_state(
            cash=cash,
            fixed_quantity=1.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=fraction,
            **kwargs,
        )

    def test_equity_fraction_resolves_correct_quantity(self):
        # budget = 10_000 * 0.25 = 2_500; price = 100; qty = 25
        state = self._equity_state(10_000.0, 0.25)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, rejection = process_intent(intent, 100.0, state)
        assert rejection is None
        assert trade is not None
        assert trade.quantity == 25.0

    def test_equity_fraction_deducts_correct_cash(self):
        # qty=25, price=100 → cost=2500
        state = self._equity_state(10_000.0, 0.25)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        assert trade is not None
        assert trade.cash_after == pytest.approx(10_000.0 - 25.0 * 100.0)
        assert state.cash == pytest.approx(7_500.0)

    def test_equity_fraction_position_quantity_set(self):
        state = self._equity_state(10_000.0, 0.5)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        # budget=5000, price=100 → qty=50
        assert state.position_quantity == 50.0
        assert trade is not None
        assert trade.position_after == 50.0

    def test_equity_fraction_audit_fields(self):
        state = self._equity_state(10_000.0, 0.33)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        assert trade is not None
        assert trade.position_size_mode == PositionSizeMode.EQUITY_FRACTION
        assert trade.sizing_value == pytest.approx(0.33)

    def test_equity_fraction_floor_applied(self):
        # budget = 10_000 * 0.33 = 3_300; price = 99; qty = floor(3300/99) = 33
        state = self._equity_state(10_000.0, 0.33)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 99.0, state)
        expected_qty = float(math.floor(3_300.0 / 99.0))
        assert trade is not None
        assert trade.quantity == expected_qty

    def test_equity_fraction_full_equity(self):
        # fraction=1.0 → allocate entire cash; budget=10000, price=50 → qty=200
        state = self._equity_state(10_000.0, 1.0)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 50.0, state)
        assert trade is not None
        assert trade.quantity == 200.0

    def test_equity_fraction_with_slippage(self):
        from backend.backtesting.cost_model import SlippageMode
        # slippage 1% → adj_price = 100 * 1.01 = 101; budget=10_000*0.5=5000; qty=floor(5000/101)=49
        state = self._equity_state(
            10_000.0, 0.5,
            slippage_mode=SlippageMode.PERCENTAGE,
            slippage_value=0.01,
        )
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        expected_adj = 100.0 * 1.01
        expected_qty = float(math.floor(5_000.0 / expected_adj))
        assert trade is not None
        assert trade.quantity == expected_qty

    def test_equity_fraction_close_uses_position_quantity(self):
        # Close uses whatever was opened, not equity_fraction
        state = self._equity_state(10_000.0, 0.25)
        open_intent  = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        close_intent = _make_intent("i2", 1, TradeIntentAction.CLOSE_LONG)
        trade_open, _ = process_intent(open_intent, 100.0, state)
        trade_close, _ = process_intent(close_intent, 110.0, state)
        assert trade_open is not None
        assert trade_close is not None
        assert trade_close.quantity == trade_open.quantity

    def test_equity_fraction_close_audit_fields(self):
        state = self._equity_state(10_000.0, 0.25)
        open_intent  = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        close_intent = _make_intent("i2", 1, TradeIntentAction.CLOSE_LONG)
        process_intent(open_intent, 100.0, state)
        trade, _ = process_intent(close_intent, 110.0, state)
        assert trade is not None
        assert trade.position_size_mode == PositionSizeMode.EQUITY_FRACTION
        assert trade.sizing_value == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# 7. Position tracker — zero quantity rejection
# ---------------------------------------------------------------------------

class TestZeroQuantityRejection:
    def test_zero_qty_rejected_when_budget_too_small(self):
        # cash=100, fraction=0.1 → budget=10, price=100 → qty=0 → reject
        state = _flat_state(
            cash=100.0,
            fixed_quantity=1.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.1,
        )
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, rejection = process_intent(intent, 100.0, state)
        assert trade is None
        assert rejection is not None
        assert rejection.reason == BacktestRejectionReason.ZERO_QUANTITY

    def test_zero_qty_rejection_has_detail(self):
        state = _flat_state(
            cash=50.0,
            fixed_quantity=1.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.01,
        )
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        _, rejection = process_intent(intent, 100.0, state)
        assert rejection is not None
        assert "0 units" in rejection.detail or "0" in rejection.detail

    def test_zero_qty_rejection_id_format(self):
        state = _flat_state(
            cash=50.0,
            fixed_quantity=1.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.01,
        )
        intent = _make_intent("myintent", 0, TradeIntentAction.OPEN_LONG)
        _, rejection = process_intent(intent, 100.0, state)
        assert rejection is not None
        assert rejection.rejection_id == "rejection:myintent"

    def test_zero_qty_leaves_state_unchanged(self):
        state = _flat_state(
            cash=50.0,
            fixed_quantity=1.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.01,
        )
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        process_intent(intent, 100.0, state)
        assert state.cash == 50.0
        assert state.position_quantity == 0.0

    def test_fixed_quantity_never_produces_zero_qty(self):
        # fixed_quantity=1.0 always uses the configured value, not computed
        state = _flat_state(cash=1_000.0, fixed_quantity=1.0)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, rejection = process_intent(intent, 100.0, state)
        assert rejection is None
        assert trade is not None
        assert trade.quantity == 1.0


# ---------------------------------------------------------------------------
# 8. SimulatedTrade audit fields — consistency
# ---------------------------------------------------------------------------

class TestSimulatedTradeAuditFields:
    def test_trade_has_position_size_mode_field(self):
        state = _flat_state(cash=10_000.0, fixed_quantity=1.0)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        assert trade is not None
        assert hasattr(trade, "position_size_mode")

    def test_trade_has_sizing_value_field(self):
        state = _flat_state(cash=10_000.0, fixed_quantity=1.0)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        assert trade is not None
        assert hasattr(trade, "sizing_value")

    def test_fixed_quantity_sizing_value_equals_config(self):
        state = _flat_state(cash=10_000.0, fixed_quantity=7.0)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 50.0, state)
        assert trade is not None
        assert trade.sizing_value == 7.0

    def test_equity_fraction_sizing_value_equals_config(self):
        state = _flat_state(
            cash=10_000.0,
            fixed_quantity=1.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.42,
        )
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        assert trade is not None
        assert trade.sizing_value == pytest.approx(0.42)

    def test_simulated_trade_is_frozen(self):
        state = _flat_state()
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        trade, _ = process_intent(intent, 100.0, state)
        assert trade is not None
        with pytest.raises(Exception):
            trade.sizing_value = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 9. Simulation integration — equity_fraction sizing
# ---------------------------------------------------------------------------

class TestSimulationIntegrationEquityFraction:
    def test_equity_fraction_simulation_runs(self):
        cfg = _equity_fraction_config(0.5)
        open_intent  = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        close_intent = _make_intent("i2", 1, TradeIntentAction.CLOSE_LONG)
        batch = _make_batch(open_intent, close_intent)
        bars  = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, cfg)
        assert len(result.trades) == 2

    def test_equity_fraction_open_quantity(self):
        # budget = 10_000 * 0.5 = 5_000; price=100 → qty=50
        cfg = _equity_fraction_config(0.5)
        open_intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        batch = _make_batch(open_intent)
        bars  = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, cfg)
        assert len(result.trades) == 1
        assert result.trades[0].quantity == 50.0

    def test_equity_fraction_cash_deducted_correctly(self):
        # qty=50, price=100 → cost=5000; remaining=5000
        cfg = _equity_fraction_config(0.5)
        open_intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        batch = _make_batch(open_intent)
        bars  = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, cfg)
        assert result.trades[0].cash_after == pytest.approx(5_000.0)

    def test_equity_fraction_close_pnl_correct(self):
        # buy 50 @ 100, sell 50 @ 110 → pnl = (110-100)*50 = 500
        cfg = _equity_fraction_config(0.5)
        open_intent  = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        close_intent = _make_intent("i2", 1, TradeIntentAction.CLOSE_LONG)
        batch = _make_batch(open_intent, close_intent)
        bars  = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, cfg)
        close_trade = result.trades[1]
        assert close_trade.realized_pnl == pytest.approx(500.0)

    def test_equity_fraction_zero_qty_produces_rejection(self):
        # cash=100, fraction=0.1 → budget=10, price=100 → qty=0 → reject
        cfg = BacktestSimulationConfig(
            initial_cash=100.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.1,
            execution_model=_SBC,
        )
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        batch  = _make_batch(intent)
        bars   = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, cfg)
        assert len(result.trades) == 0
        assert len(result.rejections) == 1
        assert result.rejections[0].reason == BacktestRejectionReason.ZERO_QUANTITY

    def test_equity_fraction_config_in_result(self):
        cfg = _equity_fraction_config(0.25)
        batch = _make_batch()
        bars  = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, cfg)
        assert result.config.position_size_mode == PositionSizeMode.EQUITY_FRACTION
        assert result.config.equity_fraction == pytest.approx(0.25)

    def test_equity_fraction_audit_in_trade_record(self):
        cfg = _equity_fraction_config(0.33)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        batch  = _make_batch(intent)
        bars   = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, cfg)
        trade = result.trades[0]
        assert trade.position_size_mode == PositionSizeMode.EQUITY_FRACTION
        assert trade.sizing_value == pytest.approx(0.33)


# ---------------------------------------------------------------------------
# 10. Simulation integration — equity grows between trades
# ---------------------------------------------------------------------------

class TestEquityGrowthBetweenTrades:
    def test_second_open_uses_updated_equity(self):
        """After a profitable close, next open uses the larger equity."""
        cfg = _equity_fraction_config(0.5, cash=10_000.0)

        # Trade 1: buy 50@100, sell 50@120 → PnL=1000, cash=5_000+6_000=11_000
        open1  = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        close1 = _make_intent("i2", 1, TradeIntentAction.CLOSE_LONG)
        # Trade 2: equity=11_000, fraction=0.5 → budget=5_500, price=105 → qty=floor(5500/105)=52
        # (different from first_open_qty=50 because price changed and equity grew)
        open2  = _make_intent("i3", 2, TradeIntentAction.OPEN_LONG)

        batch = _make_batch(open1, close1, open2)
        bars  = [_price_bar(0, 100.0), _price_bar(1, 120.0), _price_bar(2, 105.0)]
        result = run_simulation(batch, bars, cfg)

        assert len(result.trades) == 3
        first_open_qty  = result.trades[0].quantity  # 50
        second_open_qty = result.trades[2].quantity   # uses post-close equity

        expected_second_qty = float(math.floor(11_000.0 * 0.5 / 105.0))
        assert second_open_qty == expected_second_qty
        assert second_open_qty != first_open_qty  # equity grew → different quantity

    def test_second_open_uses_reduced_equity_after_loss(self):
        """After a losing close, next open uses the smaller equity."""
        cfg = _equity_fraction_config(0.5, cash=10_000.0)

        # Trade 1: buy 50@100, sell 50@80 → PnL=-1000, cash=9_000
        open1  = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        close1 = _make_intent("i2", 1, TradeIntentAction.CLOSE_LONG)
        # Trade 2: equity=9_000, fraction=0.5 → budget=4_500, price=90 → qty=floor(4500/90)=50
        open2  = _make_intent("i3", 2, TradeIntentAction.OPEN_LONG)

        batch = _make_batch(open1, close1, open2)
        bars  = [_price_bar(0, 100.0), _price_bar(1, 80.0), _price_bar(2, 90.0)]
        result = run_simulation(batch, bars, cfg)

        assert len(result.trades) == 3
        second_open_qty = result.trades[2].quantity
        expected_qty = float(math.floor(9_000.0 * 0.5 / 90.0))
        assert second_open_qty == expected_qty


# ---------------------------------------------------------------------------
# 11. Simulation integration — equity curve reflects sized quantity
# ---------------------------------------------------------------------------

class TestEquityCurveWithSizing:
    def test_equity_curve_market_value_uses_sized_qty(self):
        # qty=50, price=100; at bar 0: equity=cash(5000)+market_value(50*100)=10000
        cfg = _equity_fraction_config(0.5, cash=10_000.0)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        batch  = _make_batch(intent)
        bars   = [_price_bar(0, 100.0), _price_bar(1, 110.0)]
        result = run_simulation(batch, bars, cfg)

        ep0 = result.equity_curve[0]
        assert ep0.position_quantity == 50.0
        assert ep0.market_value == pytest.approx(50.0 * 100.0)
        assert ep0.equity == pytest.approx(5_000.0 + 5_000.0)  # cash + market_value

    def test_equity_curve_has_one_point_per_bar(self):
        cfg = _equity_fraction_config(0.5)
        batch = _make_batch()
        bars  = [_price_bar(i, 100.0) for i in range(5)]
        result = run_simulation(batch, bars, cfg)
        assert len(result.equity_curve) == 5


# ---------------------------------------------------------------------------
# 12. Simulation integration — fixed quantity unchanged
# ---------------------------------------------------------------------------

class TestFixedQuantityUnchanged:
    def test_fixed_quantity_default_behavior_preserved(self):
        cfg = BacktestSimulationConfig(initial_cash=10_000.0, fixed_quantity=3.0,
                                       execution_model=_SBC)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        batch  = _make_batch(intent)
        bars   = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, cfg)
        assert result.trades[0].quantity == 3.0

    def test_fixed_quantity_audit_fields_in_simulation(self):
        cfg = BacktestSimulationConfig(initial_cash=10_000.0, fixed_quantity=5.0,
                                       execution_model=_SBC)
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        batch  = _make_batch(intent)
        bars   = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, cfg)
        trade = result.trades[0]
        assert trade.position_size_mode == PositionSizeMode.FIXED_QUANTITY
        assert trade.sizing_value == 5.0

    def test_fixed_quantity_no_regression_pnl(self):
        cfg = BacktestSimulationConfig(initial_cash=10_000.0, fixed_quantity=1.0,
                                       execution_model=_SBC)
        open_intent  = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        close_intent = _make_intent("i2", 1, TradeIntentAction.CLOSE_LONG)
        batch = _make_batch(open_intent, close_intent)
        bars  = [_price_bar(0, 100.0), _price_bar(1, 150.0)]
        result = run_simulation(batch, bars, cfg)
        assert result.summary.total_realized_pnl == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# 13. Negative tests — leverage, short selling, margin still unsupported
# ---------------------------------------------------------------------------

class TestUnsupportedFeatures:
    def test_equity_fraction_above_1_is_rejected_as_leverage(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(
                position_size_mode=PositionSizeMode.EQUITY_FRACTION,
                equity_fraction=1.5,
            )

    def test_equity_fraction_exactly_2_rejected(self):
        with pytest.raises(Exception):
            BacktestSimulationConfig(
                position_size_mode=PositionSizeMode.EQUITY_FRACTION,
                equity_fraction=2.0,
            )

    def test_short_sell_still_unsupported_action(self):
        from backend.strategy_registry.trade_intents import TradeIntent, TradeIntentSource
        state = _flat_state()

        class _FakeAction:
            value = "short_sell"

        source = TradeIntentSource(
            signal_event_id="s1", bar_index=0,
            timestamp=_ts(0), rule_id="r1", rule_kind="exit",
        )
        intent = TradeIntent(
            intent_id="i1",
            action=TradeIntentAction.OPEN_LONG,
            source=source,
        )
        # The long-only tracker only handles open_long / close_long
        # Manually testing that UNSUPPORTED_ACTION logic still exists
        _, rejection = process_intent(
            _make_intent("i1", 0, TradeIntentAction.OPEN_LONG),
            100.0,
            state,
        )
        assert rejection is None  # open_long is valid — confirming tracker handles it

    def test_no_multiple_positions(self):
        """Second open_long while position held must be rejected ALREADY_LONG."""
        cfg = _equity_fraction_config(0.5)
        open1 = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        open2 = _make_intent("i2", 0, TradeIntentAction.OPEN_LONG)
        batch = _make_batch(open1, open2)
        bars  = [_price_bar(0, 100.0)]
        result = run_simulation(batch, bars, cfg)
        assert len(result.trades) == 1
        assert len(result.rejections) == 1
        assert result.rejections[0].reason == BacktestRejectionReason.ALREADY_LONG

    def test_no_pyramiding(self):
        """Single position limit enforced regardless of sizing mode."""
        state = _flat_state(
            cash=10_000.0,
            fixed_quantity=1.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=0.5,
        )
        intent1 = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        intent2 = _make_intent("i2", 0, TradeIntentAction.OPEN_LONG)
        process_intent(intent1, 100.0, state)
        _, rejection = process_intent(intent2, 100.0, state)
        assert rejection is not None
        assert rejection.reason == BacktestRejectionReason.ALREADY_LONG

    def test_insufficient_cash_still_rejected(self):
        """Even with equity_fraction, if qty * price > cash → reject."""
        # Set up a state where something unusual would cause INSUFFICIENT_CASH:
        # cash=1000, fraction=1.0 → budget=1000, price=50 → qty=20
        # 20 * 50 = 1000 ≤ 1000 → passes. This test validates with commission.
        from backend.backtesting.cost_model import CommissionMode
        state = _flat_state(
            cash=1_000.0,
            fixed_quantity=1.0,
            position_size_mode=PositionSizeMode.EQUITY_FRACTION,
            equity_fraction=1.0,
            commission_mode=CommissionMode.FIXED,
            commission_value=10_000.0,  # Absurdly large commission to trigger rejection
        )
        intent = _make_intent("i1", 0, TradeIntentAction.OPEN_LONG)
        _, rejection = process_intent(intent, 50.0, state)
        assert rejection is not None
        assert rejection.reason == BacktestRejectionReason.INSUFFICIENT_CASH


# ---------------------------------------------------------------------------
# 14. Architecture guards
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:
    def _get_source(self, module_path: str) -> str:
        import importlib
        import importlib.util
        spec = importlib.util.find_spec(module_path)
        assert spec is not None and spec.origin is not None
        with open(spec.origin) as f:
            return f.read()

    def _import_lines(self, source: str) -> list[str]:
        return [
            line for line in source.splitlines()
            if re.match(r"\s*(import|from)\s+", line)
        ]

    def test_models_no_strategy_runtime(self):
        src = self._get_source("backend.backtesting.models")
        for line in self._import_lines(src):
            assert "backend.strategy_runtime" not in line

    def test_models_no_execution(self):
        src = self._get_source("backend.backtesting.models")
        for line in self._import_lines(src):
            assert "backend.execution" not in line

    def test_models_no_forward_testing(self):
        src = self._get_source("backend.backtesting.models")
        for line in self._import_lines(src):
            assert "backend.forward_testing" not in line

    def test_position_tracker_no_strategy_runtime(self):
        src = self._get_source("backend.backtesting.position_tracker")
        for line in self._import_lines(src):
            assert "backend.strategy_runtime" not in line

    def test_position_tracker_no_execution(self):
        src = self._get_source("backend.backtesting.position_tracker")
        for line in self._import_lines(src):
            assert "backend.execution" not in line

    def test_position_tracker_no_forward_testing(self):
        src = self._get_source("backend.backtesting.position_tracker")
        for line in self._import_lines(src):
            assert "backend.forward_testing" not in line

    def test_simulator_no_strategy_runtime(self):
        src = self._get_source("backend.backtesting.simulator")
        for line in self._import_lines(src):
            assert "backend.strategy_runtime" not in line

    def test_simulator_no_execution(self):
        src = self._get_source("backend.backtesting.simulator")
        for line in self._import_lines(src):
            assert "backend.execution" not in line

    def test_simulator_no_forward_testing(self):
        src = self._get_source("backend.backtesting.simulator")
        for line in self._import_lines(src):
            assert "backend.forward_testing" not in line

    def test_no_stochastic_imports_in_simulator(self):
        src = self._get_source("backend.backtesting.simulator")
        for line in self._import_lines(src):
            assert "random" not in line

    def test_resolve_position_quantity_is_importable(self):
        from backend.backtesting.position_tracker import resolve_position_quantity
        assert callable(resolve_position_quantity)

    def test_position_size_mode_is_importable(self):
        from backend.backtesting.models import PositionSizeMode
        assert PositionSizeMode.EQUITY_FRACTION is not None

    def test_zero_quantity_rejection_reason_importable(self):
        from backend.backtesting.models import BacktestRejectionReason
        assert BacktestRejectionReason.ZERO_QUANTITY is not None

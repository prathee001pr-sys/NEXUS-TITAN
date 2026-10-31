from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus_titan.data.ohlcv import OHLCVCandle
from nexus_titan.research.backtest_engine import (
    BacktestEngine, ExecutionCostModel, Signal,
)


def bars(prices):
    start = datetime(2026, 1, 1, 3, 45, tzinfo=timezone.utc)
    result = []
    for i, price in enumerate(prices):
        p = Decimal(str(price))
        result.append(OHLCVCandle(
            "NIFTY", "1m", start + timedelta(minutes=i),
            p, p + 1, p - 1, p, 100, "test",
        ))
    return result


class BuyThenHold:
    def on_candle(self, history):
        return Signal(1)


class BuyThenExitOnSecond:
    def on_candle(self, history):
        return Signal(1 if len(history) == 1 else 0)


def test_buy_then_hold_fills_next_open_and_closes_at_last_close():
    result = BacktestEngine(initial_capital=50000, quantity=1).run(
        bars([100, 101, 110]), BuyThenHold()
    )
    assert len(result.trades) == 1
    assert result.trades[0].entry_price == Decimal("101")
    assert result.trades[0].exit_price == Decimal("110")
    assert result.net_pnl == Decimal("9")
    assert result.final_capital == Decimal("50009")


def test_round_trip_charges_and_slippage_reduce_net_profit():
    costs = ExecutionCostModel(
        brokerage_per_order=Decimal("2"),
        stt_sell_rate=Decimal("0.001"),
        exchange_rate=Decimal("0.0005"),
        gst_rate=Decimal("0.18"),
        stamp_buy_rate=Decimal("0.0002"),
        slippage_bps=Decimal("10"),
    )
    result = BacktestEngine(initial_capital=50000, costs=costs).run(
        bars([100, 101, 110]), BuyThenExitOnSecond()
    )
    trade = result.trades[0]
    assert trade.charges > 0
    assert trade.net_pnl < trade.gross_pnl


def test_reports_no_trade_metrics_without_signals():
    class Flat:
        def on_candle(self, history):
            return Signal(0)

    result = BacktestEngine().run(bars([100, 101]), Flat())
    assert result.trades == ()
    assert result.net_pnl == 0
    assert result.profit_factor is None


def test_rejects_unsorted_or_mixed_market_data():
    engine = BacktestEngine()
    with pytest.raises(ValueError, match="strictly increasing"):
        engine.run([bars([100, 101])[1], bars([100, 101])[0]], BuyThenHold())
    mixed = bars([100, 101])
    mixed[1] = OHLCVCandle(
        "BANKNIFTY", "1m", mixed[1].timestamp, 100, 102, 99, 101, 10, "test"
    )
    with pytest.raises(ValueError, match="share symbol"):
        engine.run(mixed, BuyThenHold())


def test_rejects_insufficient_capital_and_invalid_signal():
    class AlwaysBuy:
        def on_candle(self, history):
            return Signal(1)

    with pytest.raises(ValueError, match="insufficient capital"):
        BacktestEngine(initial_capital=50, quantity=1).run(
            bars([100, 101]), AlwaysBuy()
        )
    with pytest.raises(ValueError):
        Signal(2)


def test_validates_cost_model():
    with pytest.raises(ValueError):
        ExecutionCostModel(stt_sell_rate=Decimal("-0.1"))

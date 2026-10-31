from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus_titan.data.ohlcv import OHLCVCandle
from nexus_titan.research.backtest_engine import BacktestEngine
from nexus_titan.research.strategies import MovingAverageCrossover


def candles(closes):
    start = datetime(2026, 1, 1, 3, 45, tzinfo=timezone.utc)
    result = []
    for index, close in enumerate(closes):
        price = Decimal(str(close))
        result.append(OHLCVCandle(
            "NIFTY", "1m", start + timedelta(minutes=index),
            price, price + 1, price - 1, price, 100, "test",
        ))
    return result


def test_waits_until_slow_average_has_enough_completed_candles():
    strategy = MovingAverageCrossover(fast_period=2, slow_period=3)
    history = candles([5, 4])
    assert strategy.on_candle(history).target_position == 0
    assert strategy.on_candle(candles([5, 4, 3])).target_position == 0


def test_enters_long_when_fast_average_is_above_slow_average():
    strategy = MovingAverageCrossover(fast_period=2, slow_period=3)
    assert strategy.on_candle(candles([5, 4, 3, 4])).target_position == 0
    assert strategy.on_candle(candles([5, 4, 3, 4, 8])).target_position == 1


def test_returns_flat_when_fast_average_falls_below_slow_average():
    strategy = MovingAverageCrossover(fast_period=2, slow_period=3)
    assert strategy.on_candle(candles([5, 4, 3, 4, 8, 4, 2])).target_position == 0


def test_signal_for_existing_history_is_not_changed_by_later_candles():
    strategy = MovingAverageCrossover(fast_period=2, slow_period=3)
    history = candles([5, 4, 3, 4, 8])
    original_signal = strategy.on_candle(history)
    future_time = history[-1].timestamp + timedelta(minutes=1)
    future_bars = [
        OHLCVCandle("NIFTY", "1m", future_time, 2, 3, 1, 2, 100, "test"),
        OHLCVCandle("NIFTY", "1m", future_time + timedelta(minutes=1), 2, 3, 1, 2, 100, "test"),
    ]
    extended_history = history + future_bars
    assert original_signal.target_position == 1
    assert strategy.on_candle(history).target_position == original_signal.target_position
    assert strategy.on_candle(extended_history).target_position == 0


def test_engine_executes_strategy_signal_on_next_candle_open():
    history = candles([5, 4, 3, 4, 8, 4, 2, 1])
    result = BacktestEngine(initial_capital=1000).run(
        history, MovingAverageCrossover(fast_period=2, slow_period=3)
    )
    assert len(result.trades) == 1
    assert result.trades[0].entry_time == history[5].timestamp
    assert result.trades[0].entry_price == history[5].open
    assert result.trades[0].exit_time == history[7].timestamp
    assert result.trades[0].exit_price == history[7].open


@pytest.mark.parametrize("fast, slow", [(0, 3), (-1, 3), (2, 2), (3, 2), (True, 3), (1.5, 3)])
def test_rejects_invalid_periods(fast, slow):
    with pytest.raises(ValueError):
        MovingAverageCrossover(fast_period=fast, slow_period=slow)

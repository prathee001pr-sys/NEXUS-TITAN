from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus_titan.data.ohlcv import OHLCVCandle
from nexus_titan.research.backtest_engine import BacktestEngine, Signal
from nexus_titan.research.strategies import MovingAverageCrossover
from nexus_titan.research.validation import evaluate_out_of_sample, split_chronologically


def bars(prices):
    start = datetime(2026, 1, 1, 3, 45, tzinfo=timezone.utc)
    result = []
    for index, price in enumerate(prices):
        value = Decimal(str(price))
        result.append(OHLCVCandle(
            "NIFTY", "1m", start + timedelta(minutes=index),
            value, value + 1, max(value - 1, Decimal("0.1")), value, 100, "test",
        ))
    return result


def test_split_is_chronological_non_overlapping_and_preserves_order():
    source = bars([5, 4, 3, 4, 8, 4, 2, 1])
    split = split_chronologically(source, in_sample_fraction="0.625")
    assert len(split.in_sample) == 5
    assert len(split.out_of_sample) == 3
    assert split.in_sample[-1].timestamp < split.out_of_sample[0].timestamp
    assert split.in_sample + split.out_of_sample == tuple(source)


def test_out_of_sample_runner_uses_training_history_but_trades_only_holdout():
    source = bars([5, 4, 3, 4, 8, 4, 2, 1])
    split = split_chronologically(source, in_sample_fraction="0.625")
    result = evaluate_out_of_sample(
        BacktestEngine(initial_capital=1000),
        MovingAverageCrossover(fast_period=2, slow_period=3),
        split,
    )
    assert len(result.trades) == 1
    assert result.trades[0].entry_time == split.out_of_sample[0].timestamp
    assert result.trades[0].entry_price == split.out_of_sample[0].open
    assert result.trades[0].exit_time == split.out_of_sample[-1].timestamp
    assert result.trades[0].exit_price == split.out_of_sample[-1].close
    assert result.initial_capital == Decimal("1000")


def test_out_of_sample_engine_does_not_trade_before_start_index():
    class BuyAtFirstSignal:
        def on_candle(self, history):
            return Signal(1)

    source = bars([100, 90, 80, 70, 60, 80])
    result = BacktestEngine(initial_capital=1000).run(
        source, BuyAtFirstSignal(), start_index=3
    )
    assert len(result.trades) == 1
    assert result.trades[0].entry_time == source[4].timestamp
    assert result.trades[0].entry_price == source[4].open


@pytest.mark.parametrize("fraction", [0, 1, -0.1, 1.1, "NaN", "not-a-number"])
def test_rejects_invalid_split_fraction(fraction):
    with pytest.raises(ValueError):
        split_chronologically(bars([1, 2, 3, 4]), in_sample_fraction=fraction)


def test_rejects_partitions_with_fewer_than_two_candles():
    with pytest.raises(ValueError, match="at least two candles"):
        split_chronologically(bars([1, 2, 3, 4]), in_sample_fraction="0.25")


def test_rejects_short_unsorted_and_mixed_series():
    with pytest.raises(ValueError, match="at least four"):
        split_chronologically(bars([1, 2, 3]))
    source = bars([1, 2, 3, 4])
    with pytest.raises(ValueError, match="strictly increasing"):
        split_chronologically([source[0], source[2], source[1], source[3]])
    mixed = source.copy()
    mixed[2] = OHLCVCandle(
        "BANKNIFTY", "1m", mixed[2].timestamp, 2, 3, 1, 2, 100, "test"
    )
    with pytest.raises(ValueError, match="share symbol"):
        split_chronologically(mixed)


@pytest.mark.parametrize("start_index", [-1, 4, True, 1.5])
def test_engine_rejects_invalid_start_index(start_index):
    class Flat:
        def on_candle(self, history):
            return Signal(0)

    with pytest.raises(ValueError, match="start_index"):
        BacktestEngine().run(bars([1, 2, 3, 4]), Flat(), start_index=start_index)

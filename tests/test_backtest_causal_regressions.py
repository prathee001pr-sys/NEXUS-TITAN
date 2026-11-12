"""Independent causal execution and train-only fitting regression checks."""
from datetime import datetime, timedelta, timezone

import pytest

from nexus_titan.research.backtest import load_candles, run_backtest
from nexus_titan.research.v6_validation import (
    rolling_walk_forward_validation,
    walk_forward_validation,
)


def bar(n, *, open=100.0, high=100.0, low=100.0, close=100.0):
    return dict(timestamp=str(n), open=open, high=high, low=low,
                close=close, volume=1000.0)


@pytest.mark.parametrize("side", [1, -1])
def test_protective_stop_is_active_on_entry_bar(side):
    candles = [bar(0), bar(1, high=110.0, low=90.0), bar(2)]
    result = run_backtest(
        candles, signal=lambda i, rows: side if i == 0 else 0,
        instrument_type="FUTURES", allow_short=True, stop_loss_pct=5,
    )
    assert result.trade_log[0]["exit_index"] == 1
    assert result.trade_log[0]["exit_reason"] == "STOP_LOSS"
    assert result.net_profit == pytest.approx(-5)


def test_signal_exit_at_open_precedes_later_intrabar_stop():
    candles = [bar(0), bar(1), bar(2, high=101.0, low=90.0)]
    result = run_backtest(candles, stop_loss_pct=5,
                          signal=lambda i, rows: 1 if i == 0 else -1)
    assert result.trade_log[0]["exit_reason"] == "SIGNAL_EXIT"
    assert result.net_profit == pytest.approx(0)


def test_intrabar_stop_cannot_reenter_at_earlier_open():
    candles = [bar(0), bar(1), bar(2, high=101.0, low=90.0),
               bar(3, open=110.0, high=110.0, low=110.0, close=110.0)]
    result = run_backtest(candles, stop_loss_pct=5,
                          signal=lambda i, rows: 1 if i in (0, 1) else 0)
    assert result.total_trades == 1
    assert result.net_profit == pytest.approx(-5)


def test_intraday_position_does_not_earn_overnight_gap():
    candles = [bar(0), bar(1), bar(2, open=150.0, high=150.0,
                                low=150.0, close=150.0)]
    for b, stamp in zip(candles, ("2026-11-02T15:28:00+05:30",
                                 "2026-11-02T15:29:00+05:30",
                                 "2026-11-03T09:15:00+05:30")):
        b["timestamp"] = stamp
    result = run_backtest(candles, instrument_type="EQUITY_INTRADAY",
                          signal=lambda i, rows: 1 if i == 0 else 0)
    assert result.net_profit == pytest.approx(0)
    assert result.trade_log[0]["exit_index"] == 1


@pytest.mark.parametrize("rolling", [False, True])
def test_out_of_sample_factory_never_fits_future_rows(rolling):
    candles = [bar(i) for i in range(60)]
    fit_ends = []

    def factory(training):
        fit_ends.append(int(training[-1]["timestamp"]))
        return lambda i, visible: 0

    if rolling:
        rolling_walk_forward_validation(candles, factory, num_folds=2,
                                         warmup_lookback=5)
        assert fit_ends == [29, 29, 44, 44]
    else:
        walk_forward_validation(candles, factory, train_ratio=0.5)
        assert fit_ends == [29, 29]


def test_first_out_of_sample_bar_is_tradable_after_warmup():
    candles = [bar(i) for i in range(60)]
    results, _ = rolling_walk_forward_validation(
        candles, lambda train: lambda i, rows: 1,
        num_folds=2, warmup_lookback=5, fee_per_side=0,
        slippage_per_side=0,
    )
    assert results[0].trade_log[0]["entry_index"] == 5


@pytest.mark.parametrize("side", [1, -1])
def test_target_can_fill_on_entry_bar(side):
    candles = [bar(0), bar(1, high=110, low=90), bar(2)]
    result = run_backtest(candles, target_pct=5,
                          instrument_type="FUTURES", allow_short=True,
                          signal=lambda i, rows: side if i == 0 else 0)
    assert result.net_profit == pytest.approx(5)
    assert result.trade_log[0]["exit_index"] == 1
    assert result.trade_log[0]["exit_reason"] == "TARGET"


@pytest.mark.parametrize("side", [1, -1])
def test_ambiguous_entry_range_uses_stop_before_target(side):
    candles = [bar(0), bar(1, high=110, low=90), bar(2)]
    result = run_backtest(candles, stop_loss_pct=5, target_pct=5,
                          instrument_type="FUTURES", allow_short=True,
                          signal=lambda i, rows: side if i == 0 else 0)
    assert result.net_profit == pytest.approx(-5)
    assert result.intrabar_stops_hit == 1
    assert result.intrabar_targets_hit == 0


def test_single_split_uses_last_training_close_for_first_oos_open():
    candles = [bar(i) for i in range(60)]
    _, test, report = walk_forward_validation(
        candles, lambda train: lambda i, rows: 1,
        train_ratio=0.5, fee_per_side=0, slippage_per_side=0,
    )
    assert report.folds[0].warmup_bars_used == 1
    assert test.trade_log[0]["entry_index"] == 1


def test_entry_stop_costs_reconcile_to_ending_cash():
    candles = [bar(0), bar(1, high=101, low=90), bar(2)]
    result = run_backtest(candles, stop_loss_pct=5, fee_per_side=1,
                          signal=lambda i, rows: 1 if i == 0 else 0)
    assert result.total_fees == 2
    assert result.net_profit == pytest.approx(-7)
    assert result.ending_capital - result.starting_capital == pytest.approx(
        sum(t["pnl"] for t in result.trade_log))


def test_fixed_quantity_respects_daily_loss_circuit_breaker():
    candles = []
    start = datetime(2026, 11, 2, 9, 15, tzinfo=timezone.utc)
    for i in range(10):
        price = 100.0 if i % 2 else 90.0
        b = bar(i, open=price, high=price, low=price, close=price)
        b["timestamp"] = (start + timedelta(minutes=i)).isoformat()
        candles.append(b)
    result = run_backtest(candles, starting_capital=1000, quantity=5,
                          signal=lambda i, rows: 1 if i % 2 == 0 else -1)
    assert result.total_trades == 1
    assert result.net_profit == pytest.approx(-50)
    assert result.rejected_for_risk_count > 0


@pytest.mark.parametrize("kwargs", [
    {"num_folds": 100}, {"initial_train_ratio": 0},
    {"warmup_lookback": -1}, {"min_trades_gate": 0},
])
def test_invalid_walk_forward_windows_fail_clearly(kwargs):
    with pytest.raises(ValueError):
        rolling_walk_forward_validation(
            [bar(i) for i in range(60)],
            lambda train: lambda i, rows: 0, **kwargs,
        )


def test_backtest_loader_respects_declared_source_timezone(tmp_path):
    csv = tmp_path / "utc.csv"
    csv.write_text("timestamp,open,high,low,close,volume\n"
                   "2026-11-02T09:15:00,100,100,100,100,1000\n"
                   "2026-11-02T09:16:00,100,100,100,100,1000\n")
    candles = load_candles(csv, source_timezone="UTC")
    assert datetime.fromisoformat(candles[0]["timestamp"]) == datetime(
        2026, 11, 2, 9, 15, tzinfo=timezone.utc)


def test_backtest_loader_rejects_unknown_source_timezone(tmp_path):
    with pytest.raises(ValueError, match="timezone"):
        load_candles(tmp_path / "x.csv", source_timezone="Unknown/Nowhere")

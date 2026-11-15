from nexus_titan.research.backtest import BacktestResult
from nexus_titan.research.post_mortem import generate_post_mortem


def make_result(trade_log):
    return BacktestResult(
        starting_capital=50_000, ending_capital=50_150, total_trades=len(trade_log),
        winning_trades=sum(row["pnl"] > 0 for row in trade_log),
        losing_trades=sum(row["pnl"] < 0 for row in trade_log),
        win_rate_percent=66.67, net_profit=sum(row["pnl"] for row in trade_log),
        return_percent=0.3, max_drawdown_percent=1.0, profit_factor=1.5,
        expectancy=50, total_fees=20, trade_log=trade_log,
    )


def test_stage8_post_mortem_adds_side_duration_exit_and_regime_attribution():
    trades = [
        {"side": "LONG", "pnl": 100, "return_pct": 1.0, "quantity": 2,
         "entry_index": 1, "exit_index": 4, "exit_reason": "TARGET"},
        {"side": "SHORT", "pnl": -50, "return_pct": -0.5, "quantity": 1,
         "entry_index": 5, "exit_index": 6, "exit_reason": "STOP_LOSS"},
        {"side": "LONG", "pnl": 100, "return_pct": 1.1, "quantity": 1,
         "entry_index": 7, "exit_index": 9, "exit_reason": "SIGNAL_EXIT"},
    ]
    report = generate_post_mortem("test", make_result(trades), slippage_per_side=1,
                                  regime_by_entry_index={1: "TRENDING", 5: "RANGING", 7: "TRENDING"})
    assert report.long_trades == 2
    assert report.short_trades == 1
    assert report.average_win == 100
    assert report.average_loss == -50
    assert report.best_trade_pnl == 100
    assert report.worst_trade_pnl == -50
    assert report.average_holding_bars == 2
    assert report.stop_loss_exits == 1
    assert report.target_exits == 1
    assert report.signal_exits == 1
    assert dict((item.regime, item.trades) for item in report.regime_attribution) == {"RANGING": 1, "TRENDING": 2}
    assert "Insufficient evidence" in report.evidence_warning
    assert report.attribution_method == "DESCRIPTIVE_TRADE_LOG_NOT_CAUSAL"


def test_post_mortem_no_trades_is_safe_and_explicit():
    report = generate_post_mortem("empty", make_result([]))
    assert report.total_trades == 0
    assert report.primary_leakage_source == "NO_TRADES"
    assert "minimum is 30" in report.evidence_warning


def test_post_mortem_rejects_invalid_slippage():
    import pytest
    with pytest.raises(ValueError):
        generate_post_mortem("test", make_result([]), slippage_per_side=float("nan"))


def test_extended_post_mortem_is_accepted_by_governed_evolve_learning(tmp_path):
    from nexus_titan.self_improvement.engine import LearningStore, TitanEvolveEngine

    result = make_result([{
        "side": "LONG", "pnl": -25, "return_pct": -0.25, "quantity": 1,
        "entry_index": 2, "exit_index": 3, "exit_reason": "STOP_LOSS",
    }])
    report = generate_post_mortem("governed-test", result)
    engine = TitanEvolveEngine(LearningStore(tmp_path / "learning.sqlite3"))
    record = engine.capture_post_mortem(report)
    assert record.source == "post_mortem:governed-test"
    assert record.confidence == 0.60
    assert "Heuristic post-mortem" in record.evidence
    assert "post-mortem" in record.tags

import unittest

from nexus_titan.research.v6_strategies import SMACrossoverStrategy
from nexus_titan.research.v6_validation import (
    MonteCarloReport,
    WalkForwardReport,
    evaluate_strategy_promotion,
    rolling_walk_forward_validation,
    run_monte_carlo_simulation,
    walk_forward_validation,
)
from nexus_titan.research.backtest import BacktestResult, run_backtest


class Phase6ValidationTests(unittest.TestCase):
    def setUp(self):
        self.candles = [
            {
                "timestamp": str(i), "open": 100.0 + i, "high": 102.0 + i,
                "low": 99.0 + i, "close": 101.0 + i, "volume": 1000.0,
            }
            for i in range(100)
        ]

    def test_walk_forward_split(self):
        factory = lambda data: (
            lambda idx, rows: SMACrossoverStrategy(3, 8).get_signal(idx, rows)
        )
        train, test, report = walk_forward_validation(
            self.candles, factory, train_ratio=0.7, starting_capital=100000.0
        )
        self.assertEqual(report.train_candles, 70)
        self.assertEqual(report.test_candles, 30)
        self.assertIsInstance(report, WalkForwardReport)

    def test_rolling_walk_forward_uses_three_folds_and_warmup(self):
        factory = lambda data: (
            lambda idx, rows: SMACrossoverStrategy(3, 8).get_signal(idx, rows)
        )
        results, report = rolling_walk_forward_validation(
            self.candles, factory, num_folds=3, warmup_lookback=10,
            starting_capital=100000.0, fee_per_side=0.0, slippage_per_side=0.0,
        )
        self.assertEqual(report.total_folds, 3)
        self.assertTrue(all(fold.warmup_bars_used == 10 for fold in report.folds))
        self.assertEqual(len(results), 3)

    def test_monte_carlo_drawdown_distribution(self):
        trade_pnls = [500.0, -300.0, 700.0, -400.0, 200.0, -100.0, 600.0]
        report = run_monte_carlo_simulation(
            trade_pnls, starting_capital=50000.0, iterations=500
        )
        self.assertEqual(report.iterations, 500)
        self.assertGreaterEqual(report.percentile_95_max_drawdown_pct, 0.0)
        self.assertGreaterEqual(
            report.worst_case_drawdown_pct, report.median_max_drawdown_pct
        )
        self.assertIsInstance(report, MonteCarloReport)

    def test_monte_carlo_empty_trades(self):
        report = run_monte_carlo_simulation([], starting_capital=50000.0)
        self.assertEqual(report.original_max_drawdown_pct, 0.0)
        self.assertEqual(report.ruin_probability_pct, 0.0)

    def test_monte_carlo_marks_thin_samples_as_exploratory(self):
        report = run_monte_carlo_simulation([100.0, -20.0, 30.0], starting_capital=50000.0)
        self.assertEqual(report.sample_size, 3)
        self.assertFalse(report.sample_adequate)
        self.assertIn("INSUFFICIENT_SAMPLE", report.warning)

    def test_monte_carlo_rejects_invalid_parameters(self):
        with self.assertRaises(ValueError):
            run_monte_carlo_simulation([1.0], iterations=0)
        with self.assertRaises(ValueError):
            run_monte_carlo_simulation([float("nan")])

    def test_promotion_gate_blocks_inadequate_monte_carlo_sample(self):
        backtest = BacktestResult(
            starting_capital=50_000.0, ending_capital=50_100.0,
            total_trades=10, winning_trades=10, losing_trades=0,
            win_rate_percent=100.0, net_profit=100.0, return_percent=0.2,
            max_drawdown_percent=0.0, profit_factor=None, expectancy=10.0,
        )
        walk = WalkForwardReport(
            total_folds=4, folds=[], aggregate_oos_return_pct=1.0,
            compounded_oos_return_pct=1.0, total_oos_trades=30,
            confidence_verdict="ROBUST_CANDIDATE", status_summary="sample fixture",
        )
        mc = run_monte_carlo_simulation([10.0] * 10, starting_capital=50_000.0)
        decision = evaluate_strategy_promotion(
            "sample", backtest, walk, mc, is_verified_dataset=True, min_oos_trades=30,
        )
        self.assertFalse(decision.promoted)
        self.assertTrue(any("Monte Carlo sample inadequate" in reason for reason in decision.reasons))

    def test_promotion_gate_blocks_unverified_dataset(self):
        backtest = run_backtest(
            self.candles, signal=lambda index, rows: 0, fee_per_side=0.0
        )
        _, report = rolling_walk_forward_validation(
            self.candles, lambda rows: (lambda index, data: 0),
            min_trades_gate=1, fee_per_side=0.0, slippage_per_side=0.0,
        )
        monte_carlo = run_monte_carlo_simulation([100.0, 50.0, -20.0])
        decision = evaluate_strategy_promotion(
            "test", backtest, report, monte_carlo, is_verified_dataset=False
        )
        self.assertFalse(decision.promoted)
        self.assertTrue(any("provenance" in reason.lower() for reason in decision.reasons))


if __name__ == "__main__":
    unittest.main()

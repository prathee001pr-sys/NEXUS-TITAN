import unittest

from nexus_titan.research.backtest import run_backtest


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.candles = [
            {"timestamp": "1", "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 1000.0},
            {"timestamp": "2", "open": 101.0, "high": 106.0, "low": 100.0, "close": 104.0, "volume": 1100.0},
            {"timestamp": "3", "open": 105.0, "high": 108.0, "low": 103.0, "close": 107.0, "volume": 1200.0},
        ]

    def test_no_signals_preserves_capital(self):
        result = run_backtest(self.candles, signal=lambda i, c: 0)
        self.assertAlmostEqual(result.ending_capital, 50000.0)
        self.assertEqual(result.total_trades, 0)

    def test_profitable_trade(self):
        def signal(i, candles):
            return 1 if i == 0 else (-1 if i == 1 else 0)
        result = run_backtest(self.candles, signal=signal)
        self.assertAlmostEqual(result.net_profit, 4.0)
        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.winning_trades, 1)

    def test_invalid_capital_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(self.candles, starting_capital=0)

    def test_negative_fees_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(self.candles, fee_per_side=-1)

    def test_too_few_candles_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(self.candles[:1], signal=lambda i, c: 0)

    def test_fees_reduce_net_profit(self):
        result = run_backtest(self.candles, fee_per_side=1.0,
                              signal=lambda i, c: 1 if i == 0 else (-1 if i == 1 else 0))
        self.assertAlmostEqual(result.net_profit, 2.0)
        self.assertEqual(result.total_trades, 1)

    def test_slippage_reduces_net_profit(self):
        result = run_backtest(self.candles, slippage_per_side=1.0,
                              signal=lambda i, c: 1 if i == 0 else (-1 if i == 1 else 0))
        self.assertAlmostEqual(result.net_profit, 2.0)
        self.assertEqual(result.total_trades, 1)

    def test_open_position_is_closed_at_end(self):
        result = run_backtest(self.candles, signal=lambda i, c: 1 if i == 0 else 0)
        self.assertAlmostEqual(result.net_profit, 6.0)
        self.assertEqual(result.total_trades, 1)

    def test_trade_classification_accounts_for_both_fees(self):
        result = run_backtest(self.candles, fee_per_side=3.0,
                              signal=lambda i, c: 1 if i == 0 else (-1 if i == 1 else 0))
        self.assertAlmostEqual(result.net_profit, -2.0)
        self.assertEqual(result.winning_trades, 0)
        self.assertEqual(result.losing_trades, 1)

    def test_final_open_position_drawdown_is_included(self):
        candles = [dict(candle) for candle in self.candles]
        candles[-1].update({"open": 105.0, "high": 108.0, "low": 89.0, "close": 90.0})
        result = run_backtest(candles, signal=lambda index, data: 1 if index == 0 else 0)
        self.assertGreater(result.max_drawdown_percent, 0.0)

    def test_nan_starting_capital_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(self.candles, starting_capital=float("nan"))

    def test_infinite_quantity_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(self.candles, quantity=float("inf"))

    def test_nan_fee_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(self.candles, fee_per_side=float("nan"))

    def test_infinite_slippage_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(self.candles, slippage_per_side=float("inf"))

    def test_profit_factor_and_expectancy_for_mixed_trades(self):
        candles = [
            {"timestamp": "1", "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 1000.0},
            {"timestamp": "2", "open": 101.0, "high": 106.0, "low": 100.0, "close": 104.0, "volume": 1100.0},
            {"timestamp": "3", "open": 105.0, "high": 108.0, "low": 103.0, "close": 107.0, "volume": 1200.0},
            {"timestamp": "4", "open": 110.0, "high": 112.0, "low": 108.0, "close": 109.0, "volume": 1300.0},
            {"timestamp": "5", "open": 100.0, "high": 102.0, "low": 95.0, "close": 99.0, "volume": 1400.0},
        ]
        actions = {0: 1, 1: -1, 2: 1, 3: -1}
        result = run_backtest(candles, signal=lambda index, data: actions.get(index, 0))
        self.assertEqual(result.total_trades, 2)
        self.assertAlmostEqual(result.net_profit, -6.0)
        self.assertAlmostEqual(result.profit_factor, 0.4)
        self.assertAlmostEqual(result.expectancy, -3.0)

    def test_metrics_when_no_trades(self):
        result = run_backtest(self.candles, signal=lambda index, data: 0)
        self.assertIsNone(result.profit_factor)
        self.assertEqual(result.expectancy, 0.0)
        self.assertEqual(result.win_rate_percent, 0.0)

    def test_win_rate_percent_uses_completed_trades(self):
        result = run_backtest(self.candles,
                              signal=lambda i, candles: 1 if i == 0 else (-1 if i == 1 else 0))
        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.winning_trades, 1)
        self.assertAlmostEqual(result.win_rate_percent, 100.0)

    def test_breakeven_trade_not_counted_as_loss(self):
        candles = [
            {"timestamp": "1", "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 1000.0},
            {"timestamp": "2", "open": 100.0, "high": 105.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
            {"timestamp": "3", "open": 100.0, "high": 105.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
        ]
        result = run_backtest(candles, signal=lambda i, c: 1 if i == 0 else (-1 if i == 1 else 0))
        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.winning_trades, 0)
        self.assertEqual(result.losing_trades, 0)
        self.assertAlmostEqual(result.net_profit, 0.0)

    def test_gap_up_entry_no_phantom_drawdown(self):
        candles = [
            {"timestamp": "1", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000.0},
            {"timestamp": "2", "open": 110.0, "high": 115.0, "low": 110.0, "close": 112.0, "volume": 1000.0},
        ]
        result = run_backtest(candles, signal=lambda i, c: 1 if i == 0 else 0)
        self.assertEqual(result.max_drawdown_percent, 0.0)


if __name__ == "__main__":
    unittest.main()

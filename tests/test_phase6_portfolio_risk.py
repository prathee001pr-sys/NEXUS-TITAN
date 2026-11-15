import unittest

from nexus_titan.risk.portfolio_risk import (
    DEFAULT_INSTRUMENT_SPECS,
    PortfolioRiskConfig,
    PortfolioRiskManager,
    round_to_tick,
)


class PortfolioRiskTests(unittest.TestCase):
    def setUp(self):
        self.config = PortfolioRiskConfig(
            max_risk_per_trade_pct=1.0,
            max_portfolio_exposure_pct=50.0,
            max_concurrent_positions=2,
            daily_loss_limit_pct=3.0,
            consecutive_loss_limit=3,
        )
        self.manager = PortfolioRiskManager(self.config)

    def test_round_to_tick(self):
        self.assertAlmostEqual(round_to_tick(100.024, 0.05), 100.0)
        self.assertAlmostEqual(round_to_tick(100.031, 0.05), 100.05)

    def test_nifty_lot_size_rounding(self):
        spec = DEFAULT_INSTRUMENT_SPECS["NIFTY"]
        result = self.manager.evaluate_order(
            capital=1200000.0, current_exposure=0.0, current_open_positions=0,
            realized_daily_loss_pct=0.0, consecutive_losses=0,
            entry_price=22000.0, stop_price=21950.0, spec=spec,
        )
        self.assertTrue(result.approved)
        self.assertEqual(result.quantity % spec.lot_size, 0)
        self.assertEqual(result.quantity, 25)

    def test_daily_loss_lockout(self):
        result = self.manager.evaluate_order(
            capital=100000.0, current_exposure=0.0, current_open_positions=0,
            realized_daily_loss_pct=3.5, consecutive_losses=0,
            entry_price=100.0, stop_price=95.0,
        )
        self.assertFalse(result.approved)
        self.assertIn("Daily loss limit", result.reason)

    def test_consecutive_losses_circuit_breaker(self):
        result = self.manager.evaluate_order(
            capital=100000.0, current_exposure=0.0, current_open_positions=0,
            realized_daily_loss_pct=1.0, consecutive_losses=3,
            entry_price=100.0, stop_price=95.0,
        )
        self.assertFalse(result.approved)
        self.assertIn("Consecutive loss guard", result.reason)

    def test_concurrent_positions_cap(self):
        result = self.manager.evaluate_order(
            capital=100000.0, current_exposure=10000.0, current_open_positions=2,
            realized_daily_loss_pct=0.0, consecutive_losses=0,
            entry_price=100.0, stop_price=95.0,
        )
        self.assertFalse(result.approved)
        self.assertIn("concurrent positions", result.reason)


if __name__ == "__main__":
    unittest.main()

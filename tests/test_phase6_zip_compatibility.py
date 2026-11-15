import tempfile
import unittest
from pathlib import Path

from nexus_titan.dashboard.api_service import DashboardBackendService
from nexus_titan.virtual.order_manager import OrderSide, TradingMode, VirtualAccount


class Phase6ZIPCompatibilityTests(unittest.TestCase):
    def test_partial_fill_must_respect_derivative_lot_multiple(self):
        account = VirtualAccount("LOT-COMPAT", 500000, require_pretrade_risk_check=False)
        order = account.submit_order("NIFTY", OrderSide.BUY, 50, lot_size=25)
        with self.assertRaisesRegex(ValueError, "multiple of instrument lot_size"):
            account.execute_fill(order.order_id, 22000, fill_qty=10)

    def test_manual_approval_snapshot_tampering_invalidates_approval(self):
        account = VirtualAccount(
            "APPROVAL-INTEGRITY", 500000, trading_mode=TradingMode.MANUAL_APPROVAL,
            require_pretrade_risk_check=False,
        )
        order = account.submit_order("TCS", OrderSide.BUY, 10)
        account.approval_authorizer = lambda actor, order_id: actor == "OWNER" and order_id == order.order_id
        account.approve_order(order.order_id, actor="OWNER")
        order.quantity = 50
        with self.assertRaisesRegex(ValueError, "Approval integrity violation"):
            account.execute_fill(order.order_id, 100)

    def test_daily_loss_circuit_breaker_blocks_next_entry(self):
        account = VirtualAccount("DAILY-LOSS-COMPAT", 10000, require_pretrade_risk_check=True)
        entry = account.submit_order("TCS", "BUY", 10, entry_price=100, stop_price=90)
        account.execute_fill(entry.order_id, 100)
        exit_order = account.submit_order("TCS", "SELL", 10)
        account.execute_fill(exit_order.order_id, 60)
        self.assertGreater(account._daily_loss_pct(), 3.0)
        with self.assertRaisesRegex(ValueError, "Daily loss limit"):
            account.submit_order("INFY", "BUY", 1, entry_price=100, stop_price=90)

    def test_dashboard_exposes_full_evolve_capabilities(self):
        with tempfile.TemporaryDirectory() as temp:
            service = DashboardBackendService(
                account=VirtualAccount("DASHBOARD-COMPAT", 50000, require_pretrade_risk_check=False),
                default_csv=Path(temp) / "missing.csv",
            )
            telemetry = service.get_system_telemetry()
        self.assertEqual(telemetry["modules_available"], 15)
        self.assertEqual(telemetry["self_improvement_agents"]["agent_count"], 12)
        self.assertGreaterEqual(len(telemetry["self_improvement_capabilities"]), 8)
        self.assertFalse(telemetry["safety"]["live_trading_enabled"])

    def test_legacy_dashboard_backtest_entry_point_is_available(self):
        service = DashboardBackendService(
            account=VirtualAccount("DASHBOARD-BACKTEST", 100000, require_pretrade_risk_check=False),
            default_csv=Path("data/nifty_daily_sample.csv"),
        )
        result = service.run_live_backtest_suite("bollinger")
        self.assertIn("backtest", result)
        self.assertIn("walk_forward", result)
        self.assertIn("monte_carlo", result)
        self.assertIn("post_mortem", result)
        self.assertIn("warning", result)


if __name__ == "__main__":
    unittest.main()

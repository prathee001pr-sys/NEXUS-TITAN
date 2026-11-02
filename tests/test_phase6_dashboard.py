import tempfile
import unittest
from pathlib import Path

from nexus_titan.dashboard.api_service import DashboardBackendService
from nexus_titan.virtual.order_manager import VirtualAccount


class DashboardBackendTests(unittest.TestCase):
    def test_telemetry_uses_account_state_and_no_fake_market_prices(self):
        with tempfile.TemporaryDirectory() as temp:
            account=VirtualAccount("DASHBOARD",50000,require_pretrade_risk_check=False)
            service=DashboardBackendService(account,Path(temp)/"missing.csv")
            telemetry=service.get_system_telemetry()
            self.assertEqual(telemetry["account"]["current_effective_capital"],50000)
            self.assertFalse(telemetry["safety"]["broker_connected"])
            self.assertFalse(telemetry["safety"]["live_trading_enabled"])
            self.assertEqual(telemetry["market_data"]["status"],"NO_PROVIDER_CONNECTED")
            self.assertEqual(telemetry["options_analytics"]["status"],"WAITING_FOR_MARKET_DATA")

    def test_dashboard_requires_explicit_virtual_capital(self):
        with self.assertRaises(ValueError):
            DashboardBackendService()


    def test_dashboard_exposes_master_integration_health_read_only(self):
        from nexus_titan.core.master_integration import MasterTradingOrchestrator
        with tempfile.TemporaryDirectory() as temp:
            account = VirtualAccount("DASHBOARD-MASTER", 50000, require_pretrade_risk_check=False)
            orchestrator = MasterTradingOrchestrator()
            service = DashboardBackendService(
                account, Path(temp) / "missing.csv", master_orchestrator=orchestrator,
            )
            status = service.get_master_integration_status()
            self.assertTrue(status["connected"])
            self.assertFalse(status["order_submitted"])
            self.assertFalse(status["live_trading_enabled"])
            telemetry = service.get_system_telemetry()
            self.assertTrue(telemetry["master_integration"]["connected"])
            orchestrator.close()


if __name__=="__main__":
    unittest.main()

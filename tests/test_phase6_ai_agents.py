import unittest

from nexus_titan.ai_agents.agent_system import (
    DeterministicRiskVetoAgent,
    MarketAnalystAgent,
    MarketDigitalTwin,
    MetaAgentCoordinator,
)
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig, PortfolioRiskManager


class AIAgentSystemTests(unittest.TestCase):
    def setUp(self):
        self.candles = [
            {"timestamp": str(i), "open": 100.0 + i, "high": 102.0 + i,
             "low": 99.0 + i, "close": 101.0 + i, "volume": 1000.0}
            for i in range(25)
        ]
        self.coordinator = MetaAgentCoordinator()

    def test_analyst_agent_identifies_bull_regime(self):
        assessment = MarketAnalystAgent().analyze(self.candles)
        self.assertEqual(assessment.agent_id, "MARKET_ANALYST")
        self.assertEqual(assessment.decision, "BUY")
        self.assertGreater(assessment.confidence, 0.5)

    def test_deterministic_risk_veto_cannot_be_bypassed(self):
        risk_mgr = PortfolioRiskManager(PortfolioRiskConfig(daily_loss_limit_pct=2.0))
        assessment, result = DeterministicRiskVetoAgent(risk_mgr).evaluate(
            capital=100000.0, current_exposure=0.0, open_positions=0,
            daily_loss_pct=2.5, consecutive_losses=0, entry_price=100.0, stop_price=95.0,
        )
        self.assertEqual(assessment.decision, "VETO")
        self.assertFalse(result.approved)

    def test_digital_twin_flash_crash_stress_test(self):
        stressed = MarketDigitalTwin().run_stress_test(self.candles, scenario="FLASH_CRASH")
        self.assertEqual(len(stressed), len(self.candles) + 1)
        self.assertLess(stressed[-1]["close"], self.candles[-1]["close"] * 0.99)

    def test_meta_agent_orchestration_cycle(self):
        result = self.coordinator.process_cycle(
            candles=self.candles, capital=100000.0, current_exposure=0.0,
            open_positions=0, daily_loss_pct=0.0, consecutive_losses=0, stop_price=120.0,
        )
        self.assertIn(result["action"], ("BUY", "HOLD", "VETO"))


if __name__ == "__main__":
    unittest.main()

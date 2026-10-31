import unittest
from nexus_titan.risk.risk_manager import RiskConfig, calculate_position


class LegacyRiskFacadeTests(unittest.TestCase):
    def test_position_size_respects_risk_and_capital_limits(self):
        result=calculate_position(50000,100,99,RiskConfig())
        self.assertTrue(result.approved)
        self.assertEqual(result.quantity,100)
        self.assertEqual(result.risk_amount,100)

    def test_daily_loss_limit_blocks_trade(self):
        result=calculate_position(50000,100,99,daily_loss_pct=3)
        self.assertFalse(result.approved)
        self.assertEqual(result.quantity,0)

    def test_negative_daily_loss_is_rejected(self):
        result=calculate_position(50000,100,99,daily_loss_pct=-1)
        self.assertFalse(result.approved)
        self.assertEqual(result.quantity,0)

    def test_non_finite_and_invalid_inputs_block(self):
        for values in ((float("nan"),100,99),(50000,100,float("inf")),(50000,100,101)):
            result=calculate_position(*values)
            self.assertFalse(result.approved)


if __name__=="__main__":
    unittest.main()

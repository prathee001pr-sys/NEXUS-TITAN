import unittest
from nexus_titan.derivatives.options_engine import calculate_option_greeks, solve_implied_volatility


class OptionGreeksTests(unittest.TestCase):
    def test_call_and_put_delta_bounds(self):
        call = calculate_option_greeks(24800, 24800, 10, 0.15, option_type="CE")
        put = calculate_option_greeks(24800, 24800, 10, 0.15, option_type="PE")
        self.assertTrue(0 <= call.delta <= 1)
        self.assertTrue(-1 <= put.delta <= 0)
        self.assertGreater(call.theoretical_price, 0)
        self.assertGreater(put.theoretical_price, 0)

    def test_invalid_spot_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_option_greeks(0, 24800, 10)

    def test_implied_volatility_solver(self):
        theoretical = calculate_option_greeks(24800, 24800, 10, 0.2, option_type="CE")
        solved = solve_implied_volatility(theoretical.theoretical_price, 24800, 24800, 10, "CE")
        self.assertAlmostEqual(solved, 0.2, delta=0.03)


if __name__ == "__main__":
    unittest.main()

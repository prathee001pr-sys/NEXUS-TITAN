"""Regression coverage for the isolated crypto virtual account."""
import unittest
from nexus_titan.crypto.crypto_engine import CryptoVirtualAccount, calculate_crypto_trade_costs


class CryptoEngineTests(unittest.TestCase):
    def test_starting_capital_must_be_explicit(self):
        with self.assertRaises(ValueError):
            CryptoVirtualAccount()

    def test_unknown_symbol_is_rejected(self):
        account = CryptoVirtualAccount(starting_capital=1000)
        with self.assertRaises(ValueError):
            account.execute_crypto_order("UNKNOWNUSDT", "BUY", 100, 1)

    def test_buy_rounds_quantity_down_to_exchange_step(self):
        account = CryptoVirtualAccount(starting_capital=1000)
        result = account.execute_crypto_order("BTCUSDT", "BUY", 150000, 0.000123)
        self.assertEqual(result["filled_qty"], 0.0001)

    def test_too_small_notional_is_rejected(self):
        account = CryptoVirtualAccount(starting_capital=1000)
        with self.assertRaises(ValueError):
            account.execute_crypto_order("BTCUSDT", "BUY", 1000, 0.0001)

    def test_exposure_cap_is_enforced(self):
        account = CryptoVirtualAccount(starting_capital=1000, max_portfolio_exposure_pct=10)
        with self.assertRaises(ValueError):
            account.execute_crypto_order("BTCUSDT", "BUY", 50000, 0.01)

    def test_sell_tds_is_included_in_realized_pnl_and_cash(self):
        account = CryptoVirtualAccount(starting_capital=1000, apply_indian_vda_tds=True)
        account.execute_crypto_order("BTCUSDT", "BUY", 50000, 0.001)
        result = account.execute_crypto_order("BTCUSDT", "SELL", 51000, 0.001)
        self.assertGreater(result["tds_withheld"], 0)
        self.assertAlmostEqual(account.realized_pnl,
            (51000 - 50000) * 0.001 - (50000 * 0.001 * 0.001)
            - (51000 * 0.001 * 0.001) - (51000 * 0.001 * 0.01), places=4)
        self.assertAlmostEqual(account.cash_balance, 1000 + account.realized_pnl, places=3)

    def test_sell_cannot_exceed_open_position(self):
        account = CryptoVirtualAccount(starting_capital=1000)
        account.execute_crypto_order("BTCUSDT", "BUY", 50000, 0.001)
        with self.assertRaises(ValueError):
            account.execute_crypto_order("BTCUSDT", "SELL", 50000, 0.002)

    def test_tds_only_applies_to_sell_side(self):
        costs = calculate_crypto_trade_costs(100, 1, side="BUY", apply_indian_vda_tds=True)
        self.assertEqual(costs.tds_tax, 0)


if __name__ == "__main__":
    unittest.main()

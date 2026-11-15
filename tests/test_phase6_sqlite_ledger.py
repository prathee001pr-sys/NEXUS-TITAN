import tempfile
import unittest
from pathlib import Path

from nexus_titan.storage.sqlite_ledger import SQLiteTradeLedger


class SQLiteTradeLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = SQLiteTradeLedger(Path(self.temp.name) / "trades.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_open_and_get_trade(self):
        trade = self.ledger.open_trade("TR-001", "NIFTY", 22000, 50, 21800, fee=20)
        self.assertEqual(trade["status"], "OPEN")
        self.assertEqual(trade["symbol"], "NIFTY")
        self.assertEqual(trade["fees"], 20)

    def test_duplicate_id_rejected(self):
        self.ledger.open_trade("TR-002", "BANKNIFTY", 48000, 15, 47500)
        with self.assertRaises(ValueError):
            self.ledger.open_trade("TR-002", "BANKNIFTY", 48000, 15, 47500)

    def test_invalid_stop_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.open_trade("TR-003", "NIFTY", 22000, 50, 22100)

    def test_close_trade_net_pnl(self):
        self.ledger.open_trade("TR-004", "RELIANCE", 2500, 10, 2400, fee=15)
        closed = self.ledger.close_trade("TR-004", 2600, exit_fee=15)
        self.assertEqual(closed["status"], "CLOSED")
        self.assertEqual(closed["realized_pnl"], 970)
        self.assertEqual(closed["fees"], 30)

    def test_already_closed_trade_cannot_close_twice(self):
        self.ledger.open_trade("TR-005", "INFY", 1500, 10, 1450)
        self.ledger.close_trade("TR-005", 1550)
        with self.assertRaises(ValueError):
            self.ledger.close_trade("TR-005", 1560)

    def test_performance_summary(self):
        self.ledger.open_trade("T1", "NIFTY", 100, 1, 90)
        self.ledger.close_trade("T1", 110)
        self.ledger.open_trade("T2", "NIFTY", 100, 1, 90)
        self.ledger.close_trade("T2", 95)
        summary = self.ledger.get_performance_summary()
        self.assertEqual(summary["total_closed_trades"], 2)
        self.assertEqual(summary["winning_trades"], 1)
        self.assertEqual(summary["losing_trades"], 1)
        self.assertEqual(summary["win_rate_percent"], 50)
        self.assertEqual(summary["total_net_pnl"], 5)
        self.assertEqual(summary["profit_factor"], 2)


if __name__ == "__main__":
    unittest.main()

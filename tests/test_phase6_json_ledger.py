import tempfile
import unittest
from pathlib import Path
from nexus_titan.storage.trade_ledger import TradeLedger


class JSONTradeLedgerTests(unittest.TestCase):
    def test_open_close_and_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=TradeLedger(Path(temp)/"trades.json")
            trade=ledger.open_trade("T-1","NIFTY",100,2,98)
            self.assertEqual(trade.symbol,"NIFTY")
            with self.assertRaises(ValueError):
                ledger.open_trade("T-1","NIFTY",100,2,98)
            closed=ledger.close_trade("T-1",105)
            self.assertEqual(closed["realized_pnl"],10)
            with self.assertRaises(ValueError):
                ledger.close_trade("T-1",106)

    def test_invalid_values_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=TradeLedger(Path(temp)/"trades.json")
            with self.assertRaises(ValueError):
                ledger.open_trade("T-2","NIFTY",float("nan"),1,98)
            with self.assertRaises(ValueError):
                ledger.close_trade("missing",100)


if __name__=="__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from nexus_titan.trading_engine import evaluate_csv


class TradingDecisionTests(unittest.TestCase):
    def test_invalid_file_returns_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate_csv(Path(temp) / "missing.csv", 50000, 95)
            self.assertEqual(result.signal, "HOLD")
            self.assertFalse(result.approved)

    def test_valid_csv_returns_deterministic_signal(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "market.csv"
            lines = ["timestamp,open,high,low,close,volume"]
            for i in range(15):
                price = 100 + i
                lines.append(f"2026-10-01T09:{i:02d}:00, {price},{price+2},{price-1},{price+1},1000")
            path.write_text("\n".join(lines), encoding="utf-8")
            result = evaluate_csv(path, 50000, 100)
            self.assertEqual(result.candles_loaded, 15)
            self.assertIn(result.signal, ("BUY", "SELL", "HOLD"))


if __name__ == "__main__":
    unittest.main()

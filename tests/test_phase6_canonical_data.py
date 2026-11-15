import tempfile
import unittest
from pathlib import Path

from nexus_titan.data.canonical import load_canonical_data


class CanonicalDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_valid_canonical_data(self):
        csv_file = self.tmp_path / "valid.csv"
        csv_file.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-10-26T09:15:00Z,100,105,99,104,1000\n"
            "2026-10-26T09:16:00Z,104,108,103,107,1200\n",
            encoding="utf-8",
        )
        candles, report = load_canonical_data(csv_file, symbol="NIFTY", interval="1m")
        self.assertTrue(report.is_valid)
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].symbol, "NIFTY")
        self.assertEqual(candles[0].open, 100.0)

    def test_missing_required_columns(self):
        csv_file = self.tmp_path / "missing.csv"
        csv_file.write_text("timestamp,open,high,low\n2026-10-26T09:15:00,100,105,99\n")
        candles, report = load_canonical_data(csv_file)
        self.assertFalse(report.is_valid)
        self.assertIn("close", report.missing_columns)
        self.assertIn("volume", report.missing_columns)

    def test_duplicate_and_out_of_order_detection(self):
        csv_file = self.tmp_path / "ordering.csv"
        csv_file.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-10-26T09:16:00,104,108,103,107,1200\n"
            "2026-10-26T09:15:00,100,105,99,104,1000\n",
            encoding="utf-8",
        )
        candles, report = load_canonical_data(csv_file)
        self.assertFalse(report.is_valid)
        self.assertGreater(report.out_of_order_timestamps, 0)


if __name__ == "__main__":
    unittest.main()

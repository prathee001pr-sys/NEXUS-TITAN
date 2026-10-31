import unittest

from nexus_titan.research.indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)


class TechnicalIndicatorTests(unittest.TestCase):
    def test_sma_calculation(self):
        series = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = sma(series, 3)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertAlmostEqual(result[2], 20.0)
        self.assertAlmostEqual(result[3], 30.0)
        self.assertAlmostEqual(result[4], 40.0)

    def test_sma_invalid_period(self):
        with self.assertRaises(ValueError):
            sma([10.0, 20.0], 0)

    def test_ema_calculation(self):
        series = [10.0, 11.0, 12.0, 13.0, 14.0]
        result = ema(series, 3)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertAlmostEqual(result[2], 11.0)
        self.assertAlmostEqual(result[3], 12.0)

    def test_rsi_bounds(self):
        series = [float(i) for i in range(1, 30)]
        result = rsi(series, 14)
        valid_values = [v for v in result if v is not None]
        self.assertTrue(all(0.0 <= v <= 100.0 for v in valid_values))
        self.assertAlmostEqual(valid_values[-1], 100.0)

    def test_macd_calculation(self):
        series = [100.0 + i for i in range(40)]
        macd_line, sig_line, hist = macd(series, 12, 26, 9)
        self.assertEqual(len(macd_line), 40)
        self.assertEqual(len(sig_line), 40)
        self.assertEqual(len(hist), 40)

    def test_atr_calculation(self):
        highs = [110.0, 112.0, 115.0, 114.0, 116.0]
        lows = [100.0, 102.0, 105.0, 103.0, 106.0]
        closes = [105.0, 108.0, 110.0, 109.0, 112.0]
        result = atr(highs, lows, closes, 3)
        valid_values = [v for v in result if v is not None]
        self.assertTrue(valid_values)
        self.assertTrue(all(value > 0 for value in valid_values))

    def test_bollinger_bands(self):
        series = [100.0 + (i % 5) for i in range(30)]
        upper, middle, lower = bollinger_bands(series, 20, 2.0)
        for index in range(20, 30):
            self.assertIsNotNone(upper[index])
            self.assertIsNotNone(middle[index])
            self.assertIsNotNone(lower[index])
            self.assertGreater(upper[index], middle[index])
            self.assertGreater(middle[index], lower[index])


if __name__ == "__main__":
    unittest.main()

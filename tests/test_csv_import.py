from io import StringIO

import pytest

from nexus_titan.data.csv_import import CSVImportError, load_ohlcv_csv


HEADER = "symbol,timeframe,timestamp,open,high,low,close,volume\n"
ROW = "NIFTY,1m,2026-01-01T09:15:00+05:30,100,102,99,101,10\n"


def test_reads_valid_csv_and_normalizes_timestamp_to_utc():
    candles = load_ohlcv_csv(StringIO(HEADER + ROW), source="unit-test")
    assert len(candles) == 1
    assert candles[0].timestamp.isoformat() == "2026-01-01T03:45:00+00:00"
    assert candles[0].source == "unit-test"


@pytest.mark.parametrize("content", [
    "",
    "symbol,timeframe,timestamp\n",
    HEADER + "NIFTY,1m,not-a-date,100,102,99,101,10\n",
    HEADER + "NIFTY,1m,2026-01-01T09:15:00,100,102,99,101,10\n",
    HEADER + "NIFTY,1m,2026-01-01T09:15:00+00:00,100,99,101,101,10\n",
    HEADER + "NIFTY,1m,2026-01-01T09:15:00+00:00,100,102,99,101\n",
])
def test_rejects_malformed_csv(content):
    with pytest.raises(CSVImportError):
        load_ohlcv_csv(StringIO(content), source="unit-test")


def test_rejects_duplicate_header_names():
    with pytest.raises(CSVImportError, match="duplicate"):
        load_ohlcv_csv(StringIO("symbol,symbol\n"), source="unit-test")

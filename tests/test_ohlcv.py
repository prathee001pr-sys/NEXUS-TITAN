from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus_titan.data.ohlcv import CandleQuery, MarketDataSource, OHLCVCandle


def candle(**overrides):
    values = {
        "symbol": "NIFTY",
        "timeframe": "1m",
        "timestamp": datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc),
        "open": "100.0",
        "high": "105.0",
        "low": "99.0",
        "close": "103.0",
        "volume": "1200",
        "source": "test-feed",
    }
    values.update(overrides)
    return OHLCVCandle(**values)


def test_candle_normalizes_numeric_values_and_timestamp_to_utc():
    local = timezone(timedelta(hours=5, minutes=30))
    item = candle(timestamp=datetime(2026, 1, 1, 14, 45, tzinfo=local), open=100.25)
    assert item.timestamp == datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    assert item.open == Decimal("100.25")
    assert item.volume == Decimal("1200")


@pytest.mark.parametrize("field,value", [
    ("symbol", ""), ("timeframe", ""), ("source", ""),
    ("open", 0), ("close", -1), ("volume", -1),
    ("high", 98), ("low", 104), ("open", "NaN"),
])
def test_invalid_candle_values_are_rejected(field, value):
    with pytest.raises(ValueError):
        candle(**{field: value})


def test_candle_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        candle(timestamp=datetime(2026, 1, 1, 9, 15))


def test_candle_is_immutable():
    item = candle()
    with pytest.raises(AttributeError):
        item.close = Decimal("101")


def test_query_normalizes_timezone_and_uses_exclusive_end():
    local = timezone(timedelta(hours=5, minutes=30))
    query = CandleQuery(
        "NIFTY", "1m",
        datetime(2026, 1, 1, 14, 45, tzinfo=local),
        datetime(2026, 1, 1, 14, 46, tzinfo=local),
    )
    assert query.start == datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    assert query.end == datetime(2026, 1, 1, 9, 16, tzinfo=timezone.utc)


def test_query_rejects_invalid_time_range_and_naive_time():
    start = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="earlier"):
        CandleQuery("NIFTY", "1m", start, start)
    with pytest.raises(ValueError, match="timezone-aware"):
        CandleQuery("NIFTY", "1m", datetime(2026, 1, 1), start)


def test_data_source_protocol_is_provider_independent():
    class DemoSource:
        def fetch_candles(self, query):
            return [candle(timestamp=query.start)]

    assert isinstance(DemoSource(), MarketDataSource)

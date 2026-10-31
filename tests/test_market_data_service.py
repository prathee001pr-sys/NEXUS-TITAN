from datetime import datetime, timezone

import pytest

from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle
from nexus_titan.data.service import MarketDataService, MarketDataValidationError


def make_query():
    return CandleQuery(
        "NIFTY", "1m",
        datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
    )


def make_candle(minute, *, symbol="NIFTY"):
    return OHLCVCandle(
        symbol, "1m", datetime(2026, 1, 1, 9, minute, tzinfo=timezone.utc),
        100, 102, 99, 101, 10, "fake-provider",
    )


class FakeSource:
    def __init__(self, candles):
        self.candles = candles
        self.last_query = None

    def fetch_candles(self, query):
        self.last_query = query
        return self.candles


def test_service_returns_validated_immutable_batch():
    source = FakeSource([make_candle(15), make_candle(16), make_candle(17)])
    result = MarketDataService(source).fetch_validated(make_query())
    assert result.candles == tuple(source.candles)
    assert result.report.is_valid
    assert source.last_query == make_query()


def test_service_rejects_provider_identity_mismatch():
    source = FakeSource([make_candle(15), make_candle(16, symbol="BANKNIFTY")])
    with pytest.raises(MarketDataValidationError) as error:
        MarketDataService(source).fetch_validated(make_query())
    assert error.value.report.identity_mismatches == (1,)


def test_service_rejects_out_of_order_provider_results():
    source = FakeSource([make_candle(16), make_candle(15)])
    with pytest.raises(MarketDataValidationError) as error:
        MarketDataService(source).fetch_validated(make_query())
    assert error.value.report.out_of_order_pairs == ((0, 1),)


def test_service_rejects_duplicate_provider_timestamps():
    source = FakeSource([make_candle(15), make_candle(15)])
    with pytest.raises(MarketDataValidationError) as error:
        MarketDataService(source).fetch_validated(make_query())
    assert error.value.report.duplicate_timestamps == (make_candle(15).timestamp,)


def test_service_rejects_out_of_query_provider_results():
    source = FakeSource([make_candle(14)])
    with pytest.raises(MarketDataValidationError) as error:
        MarketDataService(source).fetch_validated(make_query())
    assert error.value.report.outside_query == (make_candle(14).timestamp,)


def test_service_accepts_empty_result_as_valid_empty_batch():
    result = MarketDataService(FakeSource([])).fetch_validated(make_query())
    assert result.candles == ()
    assert result.report.is_valid

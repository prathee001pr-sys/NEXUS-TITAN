from datetime import datetime, timezone
from decimal import Decimal

from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle
from nexus_titan.data.sqlite_store import SQLiteCandleStore


def candle(minute, *, symbol="NIFTY", close=101):
    return OHLCVCandle(
        symbol, "1m", datetime(2026, 1, 1, 9, minute, tzinfo=timezone.utc),
        100, 102, 99, close, 10, "test",
    )


def query():
    return CandleQuery(
        "NIFTY", "1m",
        datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 9, 18, tzinfo=timezone.utc),
    )


def test_stores_and_retrieves_candles_in_time_order(tmp_path):
    store = SQLiteCandleStore(tmp_path / "market.db")
    result = store.store([candle(17), candle(15), candle(16)])
    assert (result.inserted, result.duplicates) == (3, 0)
    rows = store.fetch(query())
    assert [item.timestamp.minute for item in rows] == [15, 16, 17]
    assert rows[0].close == Decimal("101")


def test_prevents_duplicate_records_and_is_idempotent(tmp_path):
    store = SQLiteCandleStore(tmp_path / "market.db")
    first = candle(15)
    assert store.store([first]).inserted == 1
    result = store.store([first, first])
    assert (result.inserted, result.duplicates) == (0, 2)
    assert len(store.fetch(query())) == 1


def test_query_isolates_symbol_and_half_open_time_bounds(tmp_path):
    store = SQLiteCandleStore(tmp_path / "market.db")
    store.store([candle(14), candle(15), candle(17), candle(15, symbol="BANKNIFTY")])
    rows = store.fetch(query())
    assert [(item.symbol, item.timestamp.minute) for item in rows] == [
        ("NIFTY", 15), ("NIFTY", 17)
    ]


def test_rejects_invalid_store_inputs(tmp_path):
    import pytest

    store = SQLiteCandleStore(tmp_path / "market.db")
    with pytest.raises(TypeError):
        store.store([object()])


def test_sqlite_source_works_with_validating_market_data_service(tmp_path):
    from nexus_titan.data.service import MarketDataService
    from nexus_titan.data.sqlite_store import SQLiteMarketDataSource

    store = SQLiteCandleStore(tmp_path / "adapter.db")
    store.store([candle(15), candle(16), candle(17)])
    result = MarketDataService(SQLiteMarketDataSource(store)).fetch_validated(query())
    assert [item.timestamp.minute for item in result.candles] == [15, 16, 17]
    assert result.report.is_valid

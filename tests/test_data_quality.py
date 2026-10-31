from datetime import datetime, timedelta, timezone

import pytest

from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle
from nexus_titan.data.quality import inspect_candle_batch, timeframe_duration


def make_candle(minute, *, symbol="NIFTY", timeframe="1m"):
    return OHLCVCandle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime(2026, 1, 1, 9, minute, tzinfo=timezone.utc),
        open=100, high=102, low=99, close=101, volume=10, source="test",
    )


def query():
    return CandleQuery(
        "NIFTY", "1m",
        datetime(2026, 1, 1, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )


def test_clean_batch_is_valid_and_input_order_is_preserved():
    candles = [make_candle(15), make_candle(16), make_candle(17)]
    report = inspect_candle_batch(candles, query())
    assert report.is_valid
    assert report.candle_count == 3
    assert candles[0].timestamp.minute == 15


def test_detects_duplicate_timestamps():
    report = inspect_candle_batch(
        [make_candle(15), make_candle(15)], query()
    )
    assert report.duplicate_timestamps == (make_candle(15).timestamp,)
    assert not report.is_valid


def test_detects_out_of_order_pair():
    report = inspect_candle_batch(
        [make_candle(16), make_candle(15)], query()
    )
    assert report.out_of_order_pairs == ((0, 1),)


def test_detects_missing_fixed_intervals():
    report = inspect_candle_batch(
        [make_candle(15), make_candle(18)], query()
    )
    assert report.missing_intervals == ((
        datetime(2026, 1, 1, 9, 16, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 9, 18, tzinfo=timezone.utc),
    ),)


def test_detects_query_bounds_and_identity_mismatch():
    outside = make_candle(0)
    wrong_symbol = make_candle(16, symbol="BANKNIFTY")
    report = inspect_candle_batch([outside, wrong_symbol], query())
    assert outside.timestamp in report.outside_query
    assert report.identity_mismatches == (1,)


@pytest.mark.parametrize(("value", "seconds"), [
    ("1m", 60), ("5m", 300), ("1h", 3600), ("1d", 86400),
])
def test_supported_timeframe_durations(value, seconds):
    assert timeframe_duration(value) == timedelta(seconds=seconds)


@pytest.mark.parametrize("value", ["0m", "-1m", "1w", "minute", ""])
def test_rejects_unsupported_timeframes(value):
    with pytest.raises(ValueError):
        timeframe_duration(value)


def test_calendar_aware_inspection_skips_overnight_gap():
    from datetime import date
    from nexus_titan.data.sessions import nse_equity_derivatives_baseline

    calendar = nse_equity_derivatives_baseline()
    first = make_candle(29)
    next_day = OHLCVCandle(
        symbol="NIFTY", timeframe="1m",
        timestamp=datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc),
        open=100, high=102, low=99, close=101, volume=10, source="test",
    )
    report = inspect_candle_batch([first, next_day], query(), calendar=calendar)
    assert report.missing_intervals == ()


def test_calendar_aware_inspection_detects_gap_inside_session():
    from datetime import time
    from nexus_titan.data.sessions import nse_equity_derivatives_baseline

    calendar = nse_equity_derivatives_baseline()
    # UTC 03:45 and 03:48 correspond to 09:15 and 09:18 IST.
    first = OHLCVCandle(
        "NIFTY", "1m", datetime(2026, 1, 1, 3, 45, tzinfo=timezone.utc),
        100, 102, 99, 101, 10, "test",
    )
    later = OHLCVCandle(
        "NIFTY", "1m", datetime(2026, 1, 1, 3, 48, tzinfo=timezone.utc),
        100, 102, 99, 101, 10, "test",
    )
    report = inspect_candle_batch([first, later], query(), calendar=calendar)
    assert report.missing_intervals == ((
        datetime(2026, 1, 1, 3, 46, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 3, 48, tzinfo=timezone.utc),
    ),)


def test_calendar_aware_inspection_skips_gap_on_holiday():
    from datetime import date
    from nexus_titan.data.sessions import nse_equity_derivatives_baseline

    holiday = date(2026, 1, 1)
    calendar = nse_equity_derivatives_baseline(holidays=frozenset({holiday}))
    first = make_candle(15)
    later = make_candle(18)
    report = inspect_candle_batch([first, later], query(), calendar=calendar)
    assert report.missing_intervals == ()

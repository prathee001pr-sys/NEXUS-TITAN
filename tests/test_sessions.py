from datetime import date, datetime, time, timezone, timedelta

import pytest

from nexus_titan.data.sessions import (
    MarketCalendar,
    TradingSession,
    nse_equity_derivatives_baseline,
)


def test_nse_baseline_uses_india_timezone_and_weekday_session():
    calendar = nse_equity_derivatives_baseline()
    assert calendar.timezone_name == "Asia/Kolkata"
    assert calendar.is_trading_day(date(2026, 11, 2))  # Monday
    assert not calendar.is_trading_day(date(2026, 11, 1))  # Sunday


def test_session_open_inclusive_and_close_exclusive():
    calendar = nse_equity_derivatives_baseline()
    ist = timezone(timedelta(hours=5, minutes=30))
    assert calendar.is_open(datetime(2026, 11, 2, 9, 15, tzinfo=ist))
    assert calendar.is_open(datetime(2026, 11, 2, 15, 29, tzinfo=ist))
    assert not calendar.is_open(datetime(2026, 11, 2, 15, 30, tzinfo=ist))
    assert not calendar.is_open(datetime(2026, 11, 2, 9, 14, tzinfo=ist))


def test_holiday_closes_regular_weekday():
    calendar = nse_equity_derivatives_baseline(holidays=frozenset({date(2026, 11, 2)}))
    assert not calendar.is_trading_day(date(2026, 11, 2))


def test_special_session_replaces_weekly_schedule():
    day = date(2026, 11, 1)  # Sunday
    calendar = nse_equity_derivatives_baseline(
        special_sessions={day: (TradingSession(time(18), time(19)),)}
    )
    ist = timezone(timedelta(hours=5, minutes=30))
    assert calendar.is_open(datetime(2026, 11, 1, 18, 30, tzinfo=ist))
    assert not calendar.is_open(datetime(2026, 11, 1, 10, 0, tzinfo=ist))


def test_empty_special_session_closes_a_weekday():
    day = date(2026, 11, 2)
    calendar = nse_equity_derivatives_baseline(special_sessions={day: ()})
    assert not calendar.is_trading_day(day)


def test_rejects_overlapping_or_unsorted_sessions():
    with pytest.raises(ValueError, match="overlap"):
        MarketCalendar(
            "Asia/Kolkata",
            {0: (TradingSession(time(9), time(11)), TradingSession(time(10), time(12)))},
        )
    with pytest.raises(ValueError, match="ordered"):
        MarketCalendar(
            "Asia/Kolkata",
            {0: (TradingSession(time(12), time(13)), TradingSession(time(9), time(10)))},
        )


def test_rejects_naive_timestamp_and_invalid_session():
    calendar = nse_equity_derivatives_baseline()
    with pytest.raises(ValueError, match="timezone-aware"):
        calendar.is_open(datetime(2026, 11, 2, 10))
    with pytest.raises(ValueError, match="earlier"):
        TradingSession(time(15), time(9))

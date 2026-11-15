from dataclasses import replace
from datetime import datetime, timedelta
import pytest

from nexus_titan.operations.stage101_historical_bar_preflight import (
    Stage101Blocked, Stage101SyntheticBar, review_stage101_synthetic_window,
)


def bar(idx=0, **changes):
    stamp = (datetime.fromisoformat("2026-11-10T09:15:00+05:30")
             + timedelta(minutes=idx)).isoformat()
    values = dict(symbol="NIFTY", asof_ist=stamp,
                  open_paise=2500000, high_paise=2500200, low_paise=2499900,
                  close_paise=2500100, volume=100, source="LOCAL_SYNTHETIC_TEST_ONLY")
    values.update(changes)
    return Stage101SyntheticBar(**values)


def test_single_bar_and_deterministic_digest():
    a = review_stage101_synthetic_window([bar()])
    b = review_stage101_synthetic_window((bar(),))
    assert a == b
    assert a.symbol == "NIFTY" and a.currency == "INR"
    assert a.timeframe == "1m" and a.bar_count == 1
    assert len(a.content_sha256) == 64
    assert a.verified_trading_calendar is False
    assert a.independent_market_source_verified is False
    assert a.fifteen_year_history_verified is False
    assert a.live_trading_enabled is False


def test_minute_contiguous_series():
    x = review_stage101_synthetic_window([bar(i) for i in range(3)])
    assert x.bar_count == 3 and x.contiguous_one_minute_bars
    assert x.last_asof_ist.endswith("09:17:00+05:30")


def test_bounded_full_regular_session_375_bars():
    x = review_stage101_synthetic_window([bar(i) for i in range(375)])
    assert x.bar_count == 375
    assert x.first_asof_ist.endswith("09:15:00+05:30")
    assert x.last_asof_ist.endswith("15:29:00+05:30")


@pytest.mark.parametrize("changes", [
    dict(symbol="BTC"), dict(source="NSE_OFFICIAL"), dict(source=""),
    dict(currency="USDT"), dict(live_trading_enabled=True),
    dict(open_paise=0), dict(open_paise=-1), dict(open_paise=True),
    dict(open_paise=1.1), dict(high_paise=-1), dict(low_paise=0),
    dict(close_paise=float("nan")), dict(close_paise=0),
    dict(volume=-1), dict(volume=True), dict(volume=1.2),
    dict(high_paise=2499999), dict(low_paise=2500101),
    dict(asof_ist="2026-11-10T09:15:01+05:30"),
    dict(asof_ist="2026-11-10T09:15:00+00:00"),
    dict(asof_ist="2026-11-10T09:15:00"),
    dict(asof_ist="2026-11-10T09:14:00+05:30"),
    dict(asof_ist="2026-11-10T15:30:00+05:30"),
    dict(asof_ist="2026-11-14T09:15:00+05:30"),
    dict(asof_ist="not-a-date"),
])
def test_invalid_synthetic_bar_rejected(changes):
    with pytest.raises(Stage101Blocked):
        review_stage101_synthetic_window([bar(**changes)])


@pytest.mark.parametrize("bars", [
    [], [bar(1), bar(0)], [bar(), bar()], [bar(), bar(2)],
    [bar(), bar(1, symbol="BANKNIFTY")],
    [bar(), bar(1, asof_ist="2026-11-11T09:16:00+05:30")],
    [bar(0), bar(1), bar(1)],
])
def test_cross_bar_provenance_and_ordering_gates(bars):
    with pytest.raises(Stage101Blocked):
        review_stage101_synthetic_window(bars)


def test_large_collection_bounded():
    with pytest.raises(Stage101Blocked):
        review_stage101_synthetic_window([bar(i) for i in range(376)])


def test_generator_rejected_without_consumption():
    def bomb():
        raise AssertionError("Must never consume untrusted generator")
        yield bar()
    with pytest.raises(Stage101Blocked):
        review_stage101_synthetic_window(bomb())


def test_wrong_row_type_rejected():
    with pytest.raises(Stage101Blocked):
        review_stage101_synthetic_window([object()])


def test_quote_changes_affect_digest():
    a = review_stage101_synthetic_window([bar()])
    b = review_stage101_synthetic_window([bar(volume=101)])
    assert a.content_sha256 != b.content_sha256

from datetime import datetime, timedelta, timezone

import pytest

from nexus_titan.operations.stage141_historical_integrity import (
    HistoricalBar,
    review_historical_bars,
)


START = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)


def bar(timestamp=START, **overrides):
    values = dict(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=100,
    )
    values.update(overrides)
    return HistoricalBar(**values)


def test_valid_bars():
    result = review_historical_bars([
        bar(),
        bar(START + timedelta(minutes=1)),
    ], source="synthetic_test")
    assert result.accepted
    assert not result.research_authorized
    assert not result.live_authorized


def test_duplicate_timestamp():
    result = review_historical_bars(
        [bar(), bar()], source="synthetic_test"
    )
    assert "duplicate_timestamp" in result.reasons


def test_missing_interval():
    result = review_historical_bars(
        [bar(), bar(START + timedelta(minutes=3))],
        source="synthetic_test",
    )
    assert "missing_or_irregular_interval" in result.reasons


def test_invalid_ohlc():
    result = review_historical_bars(
        [bar(high=99)], source="synthetic_test"
    )
    assert "invalid_ohlc" in result.reasons


def test_negative_volume():
    result = review_historical_bars(
        [bar(volume=-1)], source="synthetic_test"
    )
    assert "invalid_volume" in result.reasons


def test_naive_timestamp():
    result = review_historical_bars(
        [bar(timestamp=datetime(2026, 1, 1, 9, 15))],
        source="synthetic_test",
    )
    assert "missing_timezone" in result.reasons


@pytest.mark.parametrize("source,interval", [
    ("", 1),
    ("synthetic", 0),
    ("synthetic", True),
])
def test_invalid_configuration(source, interval):
    with pytest.raises(ValueError):
        review_historical_bars(
            [bar()],
            source=source,
            interval_minutes=interval,
        )

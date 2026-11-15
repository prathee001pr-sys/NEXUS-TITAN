from datetime import datetime, timedelta, timezone
import pytest

from nexus_titan.intelligence import MarketStateBuilder

NOW = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)


def blocks():
    return dict(
        price_volume={"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        regime={"label": "UNKNOWN"}, options_flow={"status": "NOT_APPLICABLE"},
        context={"events": []}, provenance={"source_id": "fixture:unit-test"},
    )


def test_complete_market_state_is_valid_and_normalized():
    state = MarketStateBuilder().build(exchange="nse", symbol="nifty", interval="1m",
        event_time=NOW, ingest_time=NOW, **blocks())
    assert state.quality.valid
    assert state.exchange == "NSE" and state.symbol == "NIFTY"
    assert state.event_time.tzinfo == timezone.utc


def test_missing_blocks_are_not_imputed_and_invalidate_state():
    state = MarketStateBuilder().build(exchange="NSE", symbol="NIFTY", interval="1m",
        event_time=NOW, ingest_time=NOW, price_volume=blocks()["price_volume"])
    assert not state.quality.valid
    assert "regime" in state.quality.missing_blocks


def test_stale_state_is_invalid():
    state = MarketStateBuilder(max_age_seconds=30).build(exchange="NSE", symbol="NIFTY", interval="1m",
        event_time=NOW, ingest_time=NOW + timedelta(seconds=31), **blocks())
    assert state.quality.stale and not state.quality.valid


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketStateBuilder().build(exchange="NSE", symbol="NIFTY", interval="1m",
            event_time=datetime(2026, 11, 1, 9, 30), ingest_time=NOW, **blocks())


def test_bad_ohlcv_invalidates_state():
    data = blocks(); data["price_volume"]["close"] = float("nan")
    state = MarketStateBuilder().build(exchange="NSE", symbol="NIFTY", interval="1m",
        event_time=NOW, ingest_time=NOW, **data)
    assert not state.quality.valid
    assert any("close" in warning for warning in state.quality.warnings)

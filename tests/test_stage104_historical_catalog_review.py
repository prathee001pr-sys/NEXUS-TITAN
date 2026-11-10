"""Synthetic-only Stage104 catalog controls."""
from dataclasses import replace, FrozenInstanceError
from datetime import date, timedelta
import pytest
from nexus_titan.operations.stage101_historical_bar_preflight import Stage101SyntheticBar, review_stage101_synthetic_window
from nexus_titan.operations.stage104_historical_catalog_review import Stage104Blocked, review_stage104_catalog


def window(day='2026-11-10', symbol='NIFTY', count=3):
    bars = []
    for minute in range(count):
        bars.append(Stage101SyntheticBar(symbol, f'{day}T09:{15+minute:02d}:00+05:30',
                         2500000,2500200,2499900,2500100,10))
    return review_stage101_synthetic_window(bars)


def valid():
    return [window('2026-11-09'), window('2026-11-10')]


def test_valid_catalog_no_evidence_promotion():
    a=review_stage104_catalog(valid())
    b=review_stage104_catalog(tuple(valid()))
    assert a==b
    assert a.session_count==2 and a.minute_bar_count==6
    assert a.first_date=='2026-11-09' and a.last_date=='2026-11-10'
    assert len(a.catalog_sha256)==64 and a.currency=='INR'
    assert a.independent_data_provider_verified is False
    assert a.complete_trading_calendar_verified is False
    assert a.historical_15y_coverage_verified is False
    assert a.strategy_signal_authorized is False and a.live_trading_enabled is False


def test_frozen():
    with pytest.raises(FrozenInstanceError):
        review_stage104_catalog(valid()).strategy_signal_authorized=True


@pytest.mark.parametrize('change', [
    dict(symbol='BANKNIFTY'),dict(currency='USDT'),dict(timeframe='5m'),
    dict(contiguous_one_minute_bars=False),dict(verified_trading_calendar=True),
    dict(independent_market_source_verified=True),dict(fifteen_year_history_verified=True),
    dict(live_trading_enabled=True),dict(verdict='READY'),
    dict(content_sha256='wrong'),dict(content_sha256='A'*64),
    dict(bar_count=True),dict(bar_count=0),dict(bar_count=376),
    dict(min_close_paise=0),dict(max_close_paise=-1),
    dict(first_asof_ist='2026-11-10T09:15:00Z'),
    dict(last_asof_ist='2026-11-10T09:17:01+05:30'),
    dict(last_asof_ist='2026-11-10T09:19:00+05:30'),
    dict(first_asof_ist='2026-11-10T08:15:00+05:30'),
    dict(last_asof_ist='2026-11-10T15:30:00+05:30'),
    dict(trading_date='2026-11-11'),dict(trading_date='not-date'),
])
def test_tampered_prior_window_denied(change):
    items=valid()
    items[1]=replace(items[1],**change)
    with pytest.raises(Stage104Blocked):review_stage104_catalog(items)


@pytest.mark.parametrize('bad', [[], (), None, 'abc', {}, [5], [window('2026-11-10')]*2,
                                  list(range(21))])
def test_bounded_type_order_and_duplicates(bad):
    with pytest.raises(Stage104Blocked):review_stage104_catalog(bad)


def test_reversed_and_mixed_underlyings():
    with pytest.raises(Stage104Blocked): review_stage104_catalog(list(reversed(valid())))
    with pytest.raises(Stage104Blocked): review_stage104_catalog([window('2026-11-09'),window('2026-11-10','BANKNIFTY')])


def test_actual_weekends_are_rejected_but_holidays_are_not_claimed():
    # A weekend is structurally invalid, but no official NSE holiday file exists.
    valid_day=window('2026-11-10')
    with pytest.raises(Stage104Blocked):review_stage104_catalog([replace(valid_day,trading_date='2026-11-14',first_asof_ist='2026-11-14T09:15:00+05:30',last_asof_ist='2026-11-14T09:17:00+05:30')])


def test_fingerprint_changes_with_input_data():
    base=review_stage104_catalog(valid())
    alt=review_stage104_catalog([window('2026-11-09'), window('2026-11-10',count=4)])
    assert base.catalog_sha256!=alt.catalog_sha256

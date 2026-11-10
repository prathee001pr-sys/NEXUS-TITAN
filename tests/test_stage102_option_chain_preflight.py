from dataclasses import replace
import pytest

from nexus_titan.operations.stage101_historical_bar_preflight import (
    Stage101SyntheticBar, review_stage101_synthetic_window,
)
from nexus_titan.operations.stage102_option_chain_preflight import (
    Stage102Blocked, Stage102SyntheticQuote, review_stage102_synthetic_chain,
)


def window():
    return review_stage101_synthetic_window([
        Stage101SyntheticBar("NIFTY", "2026-11-10T09:15:00+05:30",
                             2500000, 2500200, 2499900, 2500100, 100)])


def quote(kind="CE", strike=2500000, **changes):
    data = dict(contract_id=f"NIFTY-2026-11-12-{kind}-{strike}",
                underlying="NIFTY", expiry_date="2026-11-12",
                observed_at_ist="2026-11-10T09:15:00+05:30",
                option_type=kind, strike_paise=strike, bid_paise=1000,
                ask_paise=1100, open_interest=100, volume=5, lot_size=25)
    data.update(changes)
    return Stage102SyntheticQuote(**data)


def pair():
    return [quote("CE"), quote("PE")]


def test_paired_chain_fingerprint_and_no_go_flags():
    a = review_stage102_synthetic_chain(window(), pair())
    b = review_stage102_synthetic_chain(window(), tuple(pair()))
    assert a == b
    assert a.quote_count == 2 and a.paired_strike_count == 1
    assert a.paired_strikes_paise == (2500000,)
    assert a.underlying == "NIFTY" and a.currency == "INR"
    assert a.source_window_sha256 == window().content_sha256
    assert a.structural_chain_valid
    assert a.official_option_chain_verified is False
    assert a.executable_liquidity_verified is False
    assert a.live_trading_enabled is False


def test_multiple_strikes_pair_sorted_and_hash_change():
    p = pair() + [quote("CE", 2510000), quote("PE", 2510000)]
    a = review_stage102_synthetic_chain(window(), p)
    assert a.paired_strikes_paise == (2500000, 2510000)
    assert a.chain_sha256 != review_stage102_synthetic_chain(window(), pair()).chain_sha256


@pytest.mark.parametrize("changes", [
    dict(source="OFFICIAL_NSE"), dict(source=""), dict(currency="USDT"),
    dict(live_trading_enabled=True), dict(underlying="BANKNIFTY"),
    dict(contract_id="../bad"), dict(contract_id="NIFTY-2026-11-12-CE-3000000"),
    dict(option_type="PE"), dict(option_type="FUT"),
    dict(strike_paise=0), dict(strike_paise=True), dict(strike_paise=-1),
    dict(bid_paise=-1), dict(bid_paise=True), dict(ask_paise=0),
    dict(ask_paise=True), dict(bid_paise=1200, ask_paise=1100),
    dict(open_interest=0), dict(open_interest=-1), dict(open_interest=True),
    dict(volume=-1), dict(lot_size=0), dict(lot_size=10001),
    dict(observed_at_ist="2026-11-10T09:15:01+05:30"),
    dict(observed_at_ist="2026-11-10T09:14:29+05:30"),
    dict(observed_at_ist="2026-11-10T09:15:00+00:00"),
    dict(observed_at_ist="2026-11-10T09:15:00"),
    dict(observed_at_ist="no-time"),
    dict(expiry_date="2026-11-09", contract_id="NIFTY-2026-11-09-CE-2500000"),
    dict(expiry_date="invalid"),
])
def test_invalid_ce_rejected(changes):
    p = pair()
    p[0] = replace(p[0], **changes)
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), p)


@pytest.mark.parametrize("changes", [
    dict(currency="USDT"), dict(live_trading_enabled=True),
    dict(verified_trading_calendar=True),
    dict(independent_market_source_verified=True),
    dict(fifteen_year_history_verified=True),
    dict(contiguous_one_minute_bars=False), dict(timeframe="5m"),
    dict(content_sha256="bad"), dict(bar_count=400),
])
def test_bad_upstream_window_rejected(changes):
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(replace(window(), **changes), pair())


def test_duplicate_quote_rejected():
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), [quote("CE"), quote("CE")])


def test_missing_pair_rejected():
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), [quote("CE"), quote("PE", 2600000)])


def test_mixed_expiry_rejected():
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), [quote("CE"), quote("PE", expiry_date="2026-11-19", contract_id="NIFTY-2026-11-19-PE-2500000")])


def test_distinct_quote_timestamps_rejected():
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), [quote("CE"), quote("PE", observed_at_ist="2026-11-10T09:14:59+05:30")])


def test_unbounded_collection_rejected():
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), pair() * 60)


def test_generator_rejected_without_consumption():
    def bomb():
        raise RuntimeError("Untrusted generator iterated")
        yield quote()
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), bomb())


@pytest.mark.parametrize("bad", [-1, True, 61, "30"])
def test_quote_age_policy_rejected(bad):
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), pair(), max_quote_age_seconds=bad)


def test_wrong_item_type_rejected():
    with pytest.raises(Stage102Blocked):
        review_stage102_synthetic_chain(window(), [quote(), object()])

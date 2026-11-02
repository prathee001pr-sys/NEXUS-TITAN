"""Focused fail-closed option-chain integrity regression tests (synthetic only)."""
from datetime import date, datetime, timedelta

import pytest

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote
from nexus_titan.derivatives.chain_integrity import inspect_verified_option_chain


def _contract(**changes):
    fields = dict(
        symbol="NIFTYOPT", underlying="NIFTY", exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=1800,
        effective_from=date(2026, 11, 1), effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5), strike_step=50.0,
        source_reference="fixture:requires-independent-source-review",
        source_verified=True,
    )
    fields.update(changes)
    return PointInTimeContractSpec(**fields)


def _quote(option_type="CE", **changes):
    fields = dict(
        timestamp="2026-11-02T09:15:59+05:30",
        symbol="NIFTYOPT", underlying="NIFTY", expiry_date="2026-11-05",
        strike=100.0, option_type=option_type, bid=5.00, ask=5.50,
        ltp=5.25, volume=100, open_interest=1000,
        underlying_spot=100.0, lot_size=25,
    )
    fields.update(changes)
    return OptionChainQuote(**fields)


def _observed():
    return datetime.fromisoformat("2026-11-02T09:16:00+05:30")


_MISSING = object()


def _check(*quotes, contract=None, observed_at=_MISSING, **settings):
    return inspect_verified_option_chain(
        list(quotes), contract or _contract(),
        observed_at=_observed() if observed_at is _MISSING else observed_at,
        **settings
    )


def test_synthetic_matched_call_put_snapshot_is_structurally_acceptable():
    report = _check(_quote(), _quote("PE"))
    assert report.is_valid, report.issues
    assert report.quote_count == 2


def test_empty_and_unverified_metadata_fail_closed():
    assert not _check().is_valid
    issues = _check(_quote(), _quote("PE"), contract=_contract(source_verified=False)).issues
    assert any("Unverified" in issue for issue in issues)


def test_contract_metadata_requires_expiry_and_options_segment():
    without_expiry = _check(_quote(), _quote("PE"), contract=_contract(expiry_date=None))
    assert any("expiry_date is required" in issue for issue in without_expiry.issues)
    wrong_segment = _check(_quote(), _quote("PE"), contract=_contract(segment="FUTURES"))
    assert any("OPTIONS segment" in issue for issue in wrong_segment.issues)


@pytest.mark.parametrize("changes,fragment", [
    ({"symbol": "OTHER"}, "symbol differs"),
    ({"underlying": "BANKNIFTY"}, "underlying differs"),
    ({"expiry_date": "2026-11-06"}, "expiry differs"),
    ({"lot_size": 50}, "lot size differs"),
    ({"strike": 125.0}, "strike not aligned"),
    ({"bid": 5.01}, "bid price not aligned"),
    ({"ask": 5.51}, "ask price not aligned"),
    ({"ltp": 5.26}, "ltp price not aligned"),
])
def test_contract_mismatch_strike_and_tick_grid_are_rejected(changes, fragment):
    report = _check(_quote(**changes), _quote("PE"))
    assert not report.is_valid
    assert any(fragment in issue for issue in report.issues)


def test_duplicate_call_side_cannot_forge_complete_chain():
    report = _check(_quote(), _quote(), _quote("PE"))
    assert any("duplicate contract" in issue for issue in report.issues)


def test_missing_put_pair_is_rejected_by_default_but_configurable():
    report = _check(_quote())
    assert any("Missing CE/PE pair" in issue for issue in report.issues)
    assert _check(_quote(), require_call_put_pairs=False).is_valid


def test_stale_and_future_quotes_fail_closed():
    stale = _check(_quote(), _quote("PE"), observed_at=_observed() + timedelta(minutes=3))
    assert any("stale quote" in issue for issue in stale.issues)
    future = _check(_quote(timestamp="2026-11-02T09:16:05+05:30"), _quote("PE"))
    assert any("timestamp is in the future" in issue for issue in future.issues)


def test_snapshot_timestamps_must_be_synchronized():
    report = _check(_quote(timestamp="2026-11-02T09:15:30+05:30"), _quote("PE"))
    assert any("synchronization window" in issue for issue in report.issues)


def test_inconsistent_spot_and_naive_time_are_rejected():
    bad_spot = _check(_quote(underlying_spot=102.0), _quote("PE"))
    assert any("Inconsistent underlying spot" in issue for issue in bad_spot.issues)
    bad_time = _check(_quote(timestamp="2026-11-02T09:15:59"), _quote("PE"))
    assert any("timezone-naive" in issue for issue in bad_time.issues)


def test_metadata_effective_window_and_expiry_are_checked():
    outside = _check(_quote(), _quote("PE"), contract=_contract(
        effective_from=date(2026, 11, 3)
    ))
    assert any("not effective" in issue for issue in outside.issues)
    late = _check(_quote(), _quote("PE"), observed_at=datetime.fromisoformat("2026-11-06T09:16:00+05:30"))
    assert any("after contract expiry" in issue for issue in late.issues)


def test_quote_trading_date_is_india_local_not_utc_calendar_date():
    # UTC date is Nov 1, but NSE-local date is Nov 2.
    quote_time = "2026-11-01T23:59:59+00:00"
    observed = datetime.fromisoformat("2026-11-02T05:30:00+05:30")
    report = _check(
        _quote(timestamp=quote_time), _quote("PE", timestamp=quote_time),
        observed_at=observed,
    )
    assert report.is_valid, report.issues


@pytest.mark.parametrize("value", [None, datetime(2026, 11, 2, 9, 16), "2026-11-02"])
def test_observed_time_must_be_aware_datetime(value):
    with pytest.raises(ValueError, match="timezone-aware"):
        _check(_quote(), _quote("PE"), observed_at=value)


@pytest.mark.parametrize("settings", [
    {"max_quote_age_seconds": float("nan")},
    {"max_snapshot_skew_seconds": float("inf")},
    {"max_spot_dispersion_pct": -1},
    {"require_call_put_pairs": 1},
])
def test_invalid_limits_are_rejected(settings):
    with pytest.raises(ValueError):
        _check(_quote(), _quote("PE"), **settings)


def test_existing_structural_quote_validation_still_runs():
    report = _check(_quote(bid=7.0, ask=5.5), _quote("PE"))
    assert not report.is_valid
    assert any("crossed market" in issue for issue in report.issues)

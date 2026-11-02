"""Synthetic-only regression tests for bounded historical option-chain continuity."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, time, timezone

import pytest

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_history import (
    OptionChainHistoryError,
    assemble_research_option_chain_history,
    inspect_option_chain_history,
)
from nexus_titan.data.option_chain_ingest import (
    ResearchOptionChainSnapshot, load_research_option_chain_csv,
)
from nexus_titan.data.sessions import (
    TradingSession, nse_equity_derivatives_baseline,
)
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote


def _date(text):
    return datetime.fromisoformat(text)


def _contract():
    return PointInTimeContractSpec(
        symbol="NIFTYOPT", underlying="NIFTY", exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=1800, strike_step=50,
        effective_from=date(2026, 10, 1), effective_to=date(2026, 11, 12),
        expiry_date=date(2026, 11, 12),
        source_reference="test/contract-reviewed-by-operator.csv", source_verified=True,
    )


def _snapshot(timestamp, *, strikes=(100,), provider="test/provider",
              sha=None, quote_timestamp=None):
    observed = _date(timestamp)
    qtime = quote_timestamp if quote_timestamp is not None else timestamp
    quotes = tuple(
        OptionChainQuote(
            timestamp=qtime, symbol="NIFTYOPT", underlying="NIFTY",
            expiry_date="2026-11-12", strike=float(strike), option_type=side,
            bid=5.0, ask=5.5, ltp=5.25, volume=100, open_interest=1000,
            underlying_spot=100.0, lot_size=25,
        ) for strike in strikes for side in ("CE", "PE")
    )
    return ResearchOptionChainSnapshot(
        quotes=quotes,
        sha256=sha if sha is not None else hashlib.sha256(timestamp.encode()).hexdigest(),
        observed_at=observed, provider_reference=provider,
        licence_evidence_reference="test/licence-review",
        calendar_evidence_reference="test/market-calendar",
        contract_evidence_reference="test/contract-reviewed-by-operator.csv",
    )


def _check(*items, calendar=None, **kwargs):
    return inspect_option_chain_history(
        list(items), contract=_contract(),
        calendar=calendar if calendar is not None else nse_equity_derivatives_baseline(),
        **kwargs,
    )


def _assemble(*items, calendar=None, **kwargs):
    return assemble_research_option_chain_history(
        list(items), contract=_contract(),
        calendar=calendar if calendar is not None else nse_equity_derivatives_baseline(),
        **kwargs,
    )


A = "2026-11-02T09:15:00+05:30"
B = "2026-11-02T09:16:00+05:30"
C = "2026-11-02T09:17:00+05:30"


def test_contiguous_minute_snapshots_released_research_only():
    outcome = _assemble(_snapshot(A), _snapshot(B))
    assert outcome.expected_slots == 2
    assert outcome.interval_minutes == 1
    assert len(outcome.snapshots) == 2
    assert outcome.approved_for_strategy_promotion is False


def test_missing_minute_fails_closed_and_returns_exact_utc_example():
    report = _check(_snapshot(A), _snapshot(C))
    assert not report.is_valid and report.expected_slots == 3
    assert report.missing_slots == 1
    assert report.missing_examples == (datetime.fromisoformat(B).astimezone(timezone.utc),)
    with pytest.raises(OptionChainHistoryError, match="Missing 1 expected"):
        _assemble(_snapshot(A), _snapshot(C))


def test_duplicate_timestamp_fails_even_if_same_quotes():
    report = _check(_snapshot(A), _snapshot(A))
    assert any("duplicate observation" in issue for issue in report.issues)


def test_older_snapshot_after_newer_is_not_silently_sorted():
    report = _check(_snapshot(B), _snapshot(A))
    assert any("out of order" in issue for issue in report.issues)


def test_repeated_payload_digest_is_rejected_across_distinct_times():
    first = _snapshot(A)
    report = _check(first, _snapshot(B, sha=first.sha256))
    assert any("replayed" in issue for issue in report.issues)


def test_weekend_overnight_gap_not_reported():
    friday = "2026-10-30T15:29:00+05:30"
    monday = A
    report = _check(_snapshot(friday), _snapshot(monday))
    assert report.is_valid, report.issues
    assert (report.expected_slots, report.missing_slots) == (2, 0)


def test_officially_supplied_holiday_skipped_not_imagined_weekday_candles():
    cal = nse_equity_derivatives_baseline(holidays=frozenset({date(2026, 11, 2)}))
    friday = "2026-10-30T15:29:00+05:30"
    tuesday = "2026-11-03T09:15:00+05:30"
    assert _check(_snapshot(friday), _snapshot(tuesday), calendar=cal).is_valid


def test_unconfigured_holiday_cannot_be_assumed_closed():
    friday = "2026-10-30T15:29:00+05:30"
    tuesday = "2026-11-03T09:15:00+05:30"
    result = _check(_snapshot(friday), _snapshot(tuesday))
    assert result.missing_slots > 0 and not result.is_valid


def test_five_minute_series_uses_session_open_grid():
    report = _check(
        _snapshot("2026-11-02T09:15:00+05:30"),
        _snapshot("2026-11-02T09:20:00+05:30"),
        interval_minutes=5,
    )
    assert report.is_valid and report.expected_slots == 2


def test_wrong_five_minute_alignment_fails():
    report = _check(_snapshot(B), interval_minutes=5)
    assert any("not aligned" in issue for issue in report.issues)


def test_missing_five_minute_slot_is_counted():
    result = _check(_snapshot(A), _snapshot("2026-11-02T09:25:00+05:30"),
                    interval_minutes=5)
    assert result.missing_slots == 1


def test_special_evening_session_is_used_only_if_configured():
    from datetime import date as d
    calendar = nse_equity_derivatives_baseline(special_sessions={
        d(2026, 11, 2): (TradingSession(time(18, 0), time(18, 3)),),
    })
    first = _snapshot("2026-11-02T18:00:00+05:30")
    second = _snapshot("2026-11-02T18:01:00+05:30")
    assert _check(first, second, calendar=calendar).is_valid
    assert not _check(first, second).is_valid


def test_modified_provider_evidence_rejected():
    report = _check(_snapshot(A), _snapshot(B, provider="other/provider"))
    assert any("evidence changed" in issue for issue in report.issues)


def test_contract_reference_mismatch_rejected():
    second = replace(_snapshot(B), contract_evidence_reference="other/contract")
    report = _check(_snapshot(A), second)
    assert any("contract evidence reference mismatch" in issue for issue in report.issues)


def test_missing_reference_rejected():
    bad = replace(_snapshot(A), calendar_evidence_reference="")
    assert any("missing evidence reference" in i for i in _check(bad).issues)


def test_promotion_flag_in_input_rejected():
    bad = replace(_snapshot(A), approved_for_strategy_promotion=True)
    assert any("promotion authorization" in i for i in _check(bad).issues)


def test_modified_or_unverified_quote_rejected_after_import():
    bad = replace(_snapshot(A), quotes=(
        replace(_snapshot(A).quotes[0], bid=10.0, ask=5.50),
        _snapshot(A).quotes[1],
    ))
    assert any("integrity failed" in issue for issue in _check(bad).issues)


def test_out_of_session_quote_rejected_even_if_observation_valid():
    bad = _snapshot(A, quote_timestamp="2026-11-02T08:59:00+05:30")
    assert any("outside configured exchange session" in i for i in _check(bad).issues)


def test_option_strike_universe_retention_threshold():
    first = _snapshot(A, strikes=(100, 150))
    second = _snapshot(B, strikes=(150,))
    report = _check(first, second, min_strike_retention_ratio=0.75)
    assert any("strike coverage" in issue for issue in report.issues)
    assert _check(first, second, min_strike_retention_ratio=0.5).is_valid


def test_snapshot_count_limit_cannot_be_bypassed():
    result = _check(_snapshot(A), _snapshot(B), max_snapshots=1)
    assert any("max_snapshots" in issue for issue in result.issues)


def test_grid_size_guard_bounds_cost_of_gap_detection():
    report = _check(_snapshot(A), _snapshot(C), max_expected_slots=2)
    assert not report.is_valid
    assert any("max_expected_slots" in issue for issue in report.issues)


def test_calendar_days_guard_requires_chunking():
    report = _check(
        _snapshot("2026-10-30T15:29:00+05:30"), _snapshot(A),
        max_calendar_days=1,
    )
    assert any("max_calendar_days" in i for i in report.issues)


@pytest.mark.parametrize("kwargs", [
    {"interval_minutes": 0},
    {"interval_minutes": True},
    {"max_expected_slots": 0},
    {"max_snapshots": -1},
    {"max_calendar_days": False},
    {"max_missing_examples": 0},
    {"max_quote_age_seconds": float("nan")},
    {"max_quote_age_seconds": float("inf")},
    {"min_strike_retention_ratio": -0.1},
    {"min_strike_retention_ratio": float("nan")},
])
def test_invalid_configuration_values_raise(kwargs):
    with pytest.raises(ValueError):
        _check(_snapshot(A), **kwargs)


def test_empty_series_is_invalid_and_never_released():
    assert not _check().is_valid
    with pytest.raises(OptionChainHistoryError):
        _assemble()


def test_non_snapshot_item_reports_invalid():
    assert any("not a validated" in i for i in _check("raw CSV").issues)


def test_naive_or_non_datetime_observation_is_rejected():
    for value in (datetime(2026, 11, 2, 9, 15), "2026-11-02"):
        bad = replace(_snapshot(A), observed_at=value)
        assert any("timezone-aware" in i for i in _check(bad).issues)


def test_snapshot_quote_list_not_accepted_as_immutable_tuple():
    bad = replace(_snapshot(A), quotes=list(_snapshot(A).quotes))
    assert any("immutable quote tuple" in issue for issue in _check(bad).issues)


def test_forged_bad_digest_is_rejected():
    bad = replace(_snapshot(A), sha256="fake")
    assert any("invalid source digest" in issue for issue in _check(bad).issues)


def test_wrong_metadata_type_rejected():
    with pytest.raises(ValueError):
        inspect_option_chain_history([_snapshot(A)], contract="not-a-contract",
                                     calendar=nse_equity_derivatives_baseline())


def test_missing_calendar_rejected():
    with pytest.raises(ValueError):
        inspect_option_chain_history([_snapshot(A)], contract=_contract(), calendar=None)


def test_reimported_csv_snapshots_join_only_after_individual_checks(tmp_path):
    from nexus_titan.data.option_chain_ingest import COLUMNS
    calendar = nse_equity_derivatives_baseline()
    csv_snapshots = []
    for index, ts in enumerate((A, B)):
        lines = [",".join(COLUMNS)]
        for side in ("CE", "PE"):
            record = {
                "timestamp": ts, "symbol": "NIFTYOPT", "underlying": "NIFTY",
                "expiry_date": "2026-11-12", "strike": "100",
                "option_type": side, "bid": "5.00", "ask": "5.50",
                "ltp": "5.25", "volume": "100", "open_interest": "1200",
                "underlying_spot": "100", "lot_size": "25",
            }
            lines.append(",".join(record[field] for field in COLUMNS))
        payload = ("\n".join(lines) + "\n").encode()
        csv_file = tmp_path / f"history_{index}.csv"
        csv_file.write_bytes(payload)
        csv_snapshots.append(load_research_option_chain_csv(
            csv_file, expected_sha256=hashlib.sha256(payload).hexdigest(),
            contract=_contract(), observed_at=_date(ts), calendar=calendar,
            provider_reference="test/provider",
            licence_evidence_reference="test/licence-review",
            calendar_evidence_reference="test/market-calendar",
        ))
    result = _assemble(*csv_snapshots)
    assert result.expected_slots == 2
    assert result.approved_for_strategy_promotion is False

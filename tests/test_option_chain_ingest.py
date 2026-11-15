"""Offline NSE option-chain CSV ingestion tests; fixtures are synthetic."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time
from pathlib import Path

import pytest

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_ingest import (
    COLUMNS, OptionChainIngestionError, load_research_option_chain_csv,
)
from nexus_titan.data.sessions import TradingSession, nse_equity_derivatives_baseline


OBSERVED = datetime.fromisoformat("2026-11-02T09:16:00+05:30")


def _contract(**changes):
    fields = dict(
        symbol="NIFTYOPT", underlying="NIFTY", exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=1800,
        effective_from=date(2026, 11, 1), effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5), strike_step=50,
        source_verified=True, source_reference="research/contract-review.pdf",
    )
    fields.update(changes)
    return PointInTimeContractSpec(**fields)


def _row(side="CE", **changes):
    values = dict(
        timestamp="2026-11-02T09:15:59+05:30",
        symbol="NIFTYOPT", underlying="NIFTY", expiry_date="2026-11-05",
        strike="100", option_type=side, bid="5.00", ask="5.50",
        ltp="5.25", volume="100", open_interest="1200",
        underlying_spot="100", lot_size="25",
    )
    values.update(changes)
    return values


def _csv_bytes(rows=None, columns=COLUMNS):
    rows = [_row(), _row("PE")] if rows is None else rows
    return (",".join(columns) + "\n" + "".join(
        ",".join(str(row.get(column, "")) for column in columns) + "\n"
        for row in rows
    )).encode("utf-8")


def _load(tmp_path, *, payload=None, expected_hash=None, contract=None, calendar=None, **options):
    payload = _csv_bytes() if payload is None else payload
    path = tmp_path / "chain.csv"
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    arguments = dict(
        expected_sha256=digest if expected_hash is None else expected_hash,
        contract=contract if contract is not None else _contract(),
        calendar=calendar if calendar is not None else nse_equity_derivatives_baseline(),
        observed_at=OBSERVED,
        provider_reference="reviewed/provider-evidence.txt",
        licence_evidence_reference="reviewed/licence-evidence.txt",
        calendar_evidence_reference="reviewed/holiday-calendar.csv",
    )
    arguments.update(options)
    return load_research_option_chain_csv(path, **arguments)


def test_valid_synthetic_pair_is_research_only_and_carries_file_hash(tmp_path):
    result = _load(tmp_path)
    assert len(result.quotes) == 2
    assert result.sha256 == hashlib.sha256(_csv_bytes()).hexdigest()
    assert result.contract_evidence_reference == "research/contract-review.pdf"
    assert result.approved_for_strategy_promotion is False
    assert result.quotes[0].option_type == "CE"


def test_header_order_can_change_without_modifying_data(tmp_path):
    fields = tuple(reversed(COLUMNS))
    result = _load(tmp_path, payload=_csv_bytes(columns=fields))
    assert len(result.quotes) == 2


@pytest.mark.parametrize("bad", [
    "0" * 64, "xyz", "0" * 63, "", 123, None,
])
def test_wrong_or_missing_checksum_fails_closed(tmp_path, bad):
    payload = _csv_bytes()
    path = tmp_path / "source.csv"
    path.write_bytes(payload)
    with pytest.raises(OptionChainIngestionError, match="sha256|SHA-256"):
        load_research_option_chain_csv(
            path, expected_sha256=bad, contract=_contract(), calendar=nse_equity_derivatives_baseline(),
            observed_at=OBSERVED, provider_reference="source",
            licence_evidence_reference="licence", calendar_evidence_reference="calendar",
        )


def test_rewritten_file_does_not_match_previous_checksum(tmp_path):
    with pytest.raises(OptionChainIngestionError, match="checksum mismatch"):
        _load(tmp_path, payload=_csv_bytes(rows=[_row(), _row("PE", bid="5.10")]),
              expected_hash=hashlib.sha256(_csv_bytes()).hexdigest())


@pytest.mark.parametrize("payload,fragment", [
    (b"", "header"),
    (b"a,b\n1,2\n", "header"),
    (("timestamp," + ",".join(COLUMNS) + "\n").encode(), "header"),
    ((",".join(COLUMNS) + "\n").encode(), "Empty"),
    (_csv_bytes(rows=[_row(ask="")]), "blank field"),
    (_csv_bytes(rows=[_row(volume="abc")]), "invalid literal"),
    (_csv_bytes(rows=[_row(timestamp="not-a-date"), _row("PE")]), "timestamp"),
    (_csv_bytes(rows=[_row(timestamp="2026-11-02T09:15:59"), _row("PE")]), "timestamp"),
    (_csv_bytes(rows=[_row(volume="-2"), _row("PE")]), "non-negative integer"),
    (_csv_bytes(rows=[_row(bid="NaN"), _row("PE")]), "finite"),
])
def test_invalid_csv_rows_or_schema_are_rejected(tmp_path, payload, fragment):
    with pytest.raises(OptionChainIngestionError, match=fragment):
        _load(tmp_path, payload=payload)


def test_duplicate_header_rejected(tmp_path):
    altered = list(COLUMNS)
    altered[1] = "timestamp"
    with pytest.raises(OptionChainIngestionError, match="header"):
        _load(tmp_path, payload=_csv_bytes(columns=tuple(altered)))


def test_extra_columns_are_not_silently_ignored(tmp_path):
    payload = _csv_bytes().replace(b"100,25\n", b"100,25,EXTRA\n")
    with pytest.raises(OptionChainIngestionError, match="extra columns"):
        _load(tmp_path, payload=payload)


@pytest.mark.parametrize("option", [
    {"max_file_bytes": 8},
    {"max_rows": 1},
])
def test_size_and_row_count_limits(tmp_path, option):
    with pytest.raises(OptionChainIngestionError, match="exceeds"):
        _load(tmp_path, **option)


@pytest.mark.parametrize("option", [
    {"max_file_bytes": True},
    {"max_rows": 0},
])
def test_invalid_limits_rejected(tmp_path, option):
    with pytest.raises(ValueError, match="positive integer"):
        _load(tmp_path, **option)


@pytest.mark.parametrize("option", [
    {"provider_reference": "  "},
    {"licence_evidence_reference": ""},
    {"calendar_evidence_reference": 1},
])
def test_operator_evidence_references_required(tmp_path, option):
    with pytest.raises(OptionChainIngestionError, match="reference"):
        _load(tmp_path, **option)


def test_unverified_contract_rejected_not_treated_as_official(tmp_path):
    with pytest.raises(OptionChainIngestionError, match="Unverified"):
        _load(tmp_path, contract=_contract(source_verified=False))


def test_exchange_and_calendar_must_be_explicitly_compatible(tmp_path):
    with pytest.raises(OptionChainIngestionError, match="NSE"):
        _load(tmp_path, contract=_contract(exchange="BSE"))
    with pytest.raises(OptionChainIngestionError, match="MarketCalendar"):
        _load(tmp_path, calendar="weekday-only")


def test_holiday_calendar_blocks_observation_before_parsing(tmp_path):
    calendar = nse_equity_derivatives_baseline(holidays=frozenset({date(2026, 11, 2)}))
    with pytest.raises(OptionChainIngestionError, match="outside"):
        _load(tmp_path, calendar=calendar)


def test_outside_session_quote_is_rejected_even_if_observation_valid(tmp_path):
    payload = _csv_bytes(rows=[
        _row(timestamp="2026-11-02T08:00:00+05:30"), _row("PE"),
    ])
    with pytest.raises(OptionChainIngestionError, match="outside exchange session"):
        _load(tmp_path, payload=payload)


@pytest.mark.parametrize("changes,reason", [
    ({"lot_size": "50"}, "lot size"),
    ({"strike": "125"}, "strike"),
    ({"option_type": "XX"}, "option_type"),
    ({"underlying": "BANKNIFTY"}, "underlying differs"),
    ({"expiry_date": "2026-11-06"}, "expiry"),
    ({"bid": "5.01"}, "tick_size"),
])
def test_integrity_gate_enforced_after_csv_and_session_validation(tmp_path, changes, reason):
    payload = _csv_bytes(rows=[_row(**changes), _row("PE")])
    with pytest.raises(OptionChainIngestionError, match=reason):
        _load(tmp_path, payload=payload)


def test_absent_file_does_not_release_data(tmp_path):
    with pytest.raises(OptionChainIngestionError, match="missing"):
        load_research_option_chain_csv(
            tmp_path / "missing.csv", expected_sha256="a" * 64, contract=_contract(),
            calendar=nse_equity_derivatives_baseline(), observed_at=OBSERVED,
            provider_reference="provider", licence_evidence_reference="licence",
            calendar_evidence_reference="calendar",
        )


def test_non_utf8_payload_is_rejected(tmp_path):
    with pytest.raises(OptionChainIngestionError, match="UTF-8"):
        _load(tmp_path, payload=b"\xff\xfe\xff")


def test_observation_must_be_timezone_aware(tmp_path):
    with pytest.raises(OptionChainIngestionError, match="timezone-aware"):
        _load(tmp_path, observed_at=datetime(2026, 11, 2, 9, 16))


def test_synchronization_is_mandatory(tmp_path):
    payload = _csv_bytes(rows=[
        _row(timestamp="2026-11-02T09:15:54+05:30"), _row("PE")
    ])
    with pytest.raises(OptionChainIngestionError, match="synchronization"):
        _load(tmp_path, payload=payload)

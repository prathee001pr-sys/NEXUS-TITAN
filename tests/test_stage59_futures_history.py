"""Stage59 futures minute/history data preflight: adversarial local-only fixtures.

All bytes are FABRICATED NIFTY/BANKNIFTY futures candles. A declared
"licensed" claim/contract source flag never proves exchange authenticity.
No vendor, real market data, live feed, broker, order or fill connection.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.ohlcv import CandleQuery, MarketDataSource
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.data.stage59_futures_history import (
    Stage59FuturesCSVDeclaration, Stage59HistoryBlocked,
    preflight_stage59_futures_csv,
)


START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")
FIELDS = (
    "timestamp", "symbol", "exchange", "segment", "expiry_date", "lot_size",
    "open", "high", "low", "close", "volume", "open_interest",
)


def _contract(underlying="NIFTY", **changes):
    p = dict(
        symbol=underlying + "FUT", underlying=underlying, exchange="NSE",
        segment="FUTURES", lot_size=25, tick_size=0.05,
        freeze_quantity=1000, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5),
        source_reference="qa/unverified-contract-claim",
        source_verified=True,
    )
    p.update(changes)
    return PointInTimeContractSpec(**p)


def _fixture(root, *, count=3, interval=1, underlying="NIFTY",
             start=START, coverage="DECLARED_WINDOW", values=None,
             dataset_class="SYNTHETIC_SMOKE_FIXTURE"):
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(count):
        row = dict(
            timestamp=(start + timedelta(minutes=i * interval)).isoformat(),
            symbol=underlying + "FUT",
            exchange="NSE", segment="FUTURES",
            expiry_date="2026-11-05", lot_size="25",
            open="100.00", high="101.00", low="99.00",
            close="100.05", volume="1000", open_interest="2000",
        )
        if values is not None:
            row.update(values)
        rows.append(row)
    name = "future_qa.csv"
    _save(root / name, rows)
    manifest = Stage59FuturesCSVDeclaration(
        dataset_id="qa-synthetic-futures",
        filename=name,
        expected_sha256=hashlib.sha256((root / name).read_bytes()).hexdigest(),
        provider_reference="qa/unverified-synthetic-provider",
        licence_reference="qa/unverified-rights",
        calendar_reference="qa/unverified-holidays",
        contract_reference="qa/unverified-contract-claim",
        expected_first=start,
        expected_last=start + timedelta(minutes=(count - 1) * interval),
        interval_minutes=interval,
        coverage_mode=coverage, dataset_class_claim=dataset_class,
    )
    return manifest, rows


def _save(path, rows, header=FIELDS):
    content = ",".join(header) + "\n"
    for row in rows:
        content += ",".join(str(row.get(k, "")) for k in header) + "\n"
    path.write_bytes(content.encode("utf-8"))


def _replace_rows(root, manifest, rows, header=FIELDS):
    p = root / manifest.filename
    _save(p, rows, header)
    return replace(manifest, expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def _run(root, manifest, *, contract=None, calendar=None, **kwargs):
    return preflight_stage59_futures_csv(
        root, declaration=manifest,
        contract=contract or _contract(), calendar=calendar or nse_equity_derivatives_baseline(),
        **kwargs,
    )


def _assert_not_authoritative(result):
    assert result.vendor_identity_authenticated is False
    assert result.licence_authenticated is False
    assert result.official_contract_master_authenticated is False
    assert result.exchange_calendar_authenticated is False
    assert result.source_is_independently_verified_exchange_history is False
    assert result.full_exchange_universe_coverage_verified is False
    assert result.real_orderbook_depth_present is False
    assert result.fill_or_backtest_performance_verified is False
    assert result.approved_for_strategy_promotion is False
    assert result.live_orders_transmitted == 0
    assert result.production_ready is False


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
@pytest.mark.parametrize("interval", [1, 5, 15, 30])
def test_bounded_per_session_futures_data_with_vendor_independent_adapter(
    tmp_path, underlying, interval,
):
    manifest, rows = _fixture(tmp_path, underlying=underlying, interval=interval)
    result = _run(tmp_path, manifest, contract=_contract(underlying))
    assert result.dataset_id == manifest.dataset_id
    assert result.count == result.expected_slots == 3
    assert result.symbol == underlying + "FUT"
    assert result.underlying == underlying
    assert result.expiry_date == "2026-11-05"
    assert result.timeframe == f"{interval}m"
    assert result.first_observed_at == START.astimezone(result.first_observed_at.tzinfo)
    assert len(result.file_sha256) == 64
    assert len(result.candles) == 3
    assert all(bar.source == manifest.provider_reference for bar in result.candles)
    assert isinstance(result, MarketDataSource)
    query = CandleQuery(
        result.symbol, result.timeframe, manifest.expected_first,
        manifest.expected_last + timedelta(minutes=interval),
    )
    assert result.fetch_candles(query) == result.candles
    assert result.fetch_candles(CandleQuery(
        result.symbol, result.timeframe,
        manifest.expected_first + timedelta(minutes=interval),
        manifest.expected_last + timedelta(minutes=interval),
    )) == result.candles[1:]
    _assert_not_authoritative(result)


@pytest.mark.parametrize("interval,rows", [(1, 375), (5, 75), (15, 25), (30, 13)])
def test_declared_single_full_session_grid_counts_are_exact(tmp_path, interval, rows):
    manifest, _ = _fixture(tmp_path, count=rows, interval=interval,
                           coverage="FULL_SESSION")
    result = _run(tmp_path, manifest, max_rows=1000)
    assert result.declared_full_session is True
    assert result.count == rows
    assert result.expected_slots == rows
    _assert_not_authoritative(result)


def test_partial_history_cannot_claim_full_session(tmp_path):
    manifest, _ = _fixture(tmp_path, count=3, coverage="FULL_SESSION")
    with pytest.raises(Stage59HistoryBlocked, match="FULL_SESSION"):
        _run(tmp_path, manifest)


def test_partial_window_is_not_claimed_as_whole_session(tmp_path):
    manifest, _ = _fixture(tmp_path)
    result = _run(tmp_path, manifest)
    assert result.declared_full_session is False
    assert result.full_exchange_universe_coverage_verified is False


def test_fake_vendor_licensed_claim_or_owner_review_does_not_authenticate(tmp_path):
    manifest, _ = _fixture(tmp_path, dataset_class="LICENSED_EXCHANGE_HISTORY")
    forged = replace(manifest,
        provider_reference="NSE_OFFICIAL_REAL_BROKER",
        licence_reference="REVIEWED_LICENSE_BY_OWNER",
        contract_reference="qa/unverified-contract-claim",
    )
    result = _run(tmp_path, forged)
    assert result.count == 3
    _assert_not_authoritative(result)


def test_original_source_bytes_are_unchanged_after_read(tmp_path):
    manifest, _ = _fixture(tmp_path)
    original = (tmp_path / manifest.filename).read_bytes()
    before = (tmp_path / manifest.filename).stat().st_mtime_ns
    _run(tmp_path, manifest)
    assert (tmp_path / manifest.filename).read_bytes() == original
    assert (tmp_path / manifest.filename).stat().st_mtime_ns == before


def test_modified_csv_bytes_without_declared_digest_change_fail(tmp_path):
    manifest, _ = _fixture(tmp_path)
    path = tmp_path / manifest.filename
    path.write_bytes(path.read_bytes() + b"REPLAY")
    with pytest.raises(Stage59HistoryBlocked, match="checksum"):
        _run(tmp_path, manifest)


def test_file_hash_binds_exact_source_bytes_even_with_same_parsed_rows(tmp_path):
    manifest, _ = _fixture(tmp_path)
    path = tmp_path / manifest.filename
    path.write_bytes(path.read_bytes().replace(b"100.00", b"100.0"))
    with pytest.raises(Stage59HistoryBlocked, match="checksum"):
        _run(tmp_path, manifest)


@pytest.mark.parametrize("field,bad", [
    ("high", "99.00"), ("low", "102.00"),
    ("open", "0"), ("close", "-1"),
    ("high", "NaN"), ("low", "Infinity"),
    ("open", "99.99"), ("close", "100.001"),
    ("volume", "-2"), ("volume", "1.5"),
    ("open_interest", "-1"), ("open_interest", "1.2"),
    ("lot_size", "0"), ("lot_size", "26"), ("lot_size", "025"),
    ("symbol", "BANKNIFTYFUT"), ("exchange", "BSE"),
    ("segment", "OPTIONS"), ("expiry_date", "2026-11-12"),
])
def test_semantic_ohlcv_tick_lot_and_contract_identity_gate_after_valid_hash(tmp_path, field, bad):
    m, rows = _fixture(tmp_path)
    rows[1][field] = bad
    m = _replace_rows(tmp_path, m, rows)
    with pytest.raises(Stage59HistoryBlocked):
        _run(tmp_path, m)


@pytest.mark.parametrize("kind", ["duplicate", "reverse", "missing", "extra", "shifted"])
def test_duplicate_out_of_order_missing_extra_or_off_grid_candles_rejected(tmp_path, kind):
    manifest, rows = _fixture(tmp_path, count=3)
    if kind == "duplicate":
        rows[1]["timestamp"] = rows[0]["timestamp"]
    elif kind == "reverse":
        rows[1], rows[2] = rows[2], rows[1]
    elif kind == "missing":
        rows.pop(1)
    elif kind == "extra":
        rows.append(dict(rows[2], timestamp=(START + timedelta(minutes=3)).isoformat()))
    elif kind == "shifted":
        rows[1]["timestamp"] = (START + timedelta(seconds=30)).isoformat()
    manifest = _replace_rows(tmp_path, manifest, rows)
    with pytest.raises(Stage59HistoryBlocked):
        _run(tmp_path, manifest)


def test_manifest_missing_first_or_last_candle_rejected(tmp_path):
    manifest, rows = _fixture(tmp_path)
    manifest = _replace_rows(tmp_path, manifest, rows[1:])
    with pytest.raises(Stage59HistoryBlocked, match="Missing/extra|grid"):
        _run(tmp_path, manifest)


@pytest.mark.parametrize("offset", ["2026-11-02T09:15:00", "not-a-time"])
def test_naive_or_malformed_raw_csv_timestamp_rejected(tmp_path, offset):
    m, rows = _fixture(tmp_path)
    rows[0]["timestamp"] = offset
    m = _replace_rows(tmp_path, m, rows)
    with pytest.raises(Stage59HistoryBlocked, match="timestamp|timezone"):
        _run(tmp_path, m)


def test_offset_aware_utc_csv_is_accepted_and_utc_normalized(tmp_path):
    m, rows = _fixture(tmp_path)
    for row in rows:
        moment = datetime.fromisoformat(row["timestamp"])
        row["timestamp"] = moment.astimezone(
            __import__("datetime").timezone.utc
        ).isoformat()
    m = _replace_rows(tmp_path, m, rows)
    outcome = _run(tmp_path, m)
    assert outcome.count == 3
    assert all(bar.timestamp.utcoffset() == timedelta(0) for bar in outcome.candles)


@pytest.mark.parametrize("bad_header", [
    ("timestamp", "timestamp", *FIELDS[2:]),
    FIELDS[:-1],
    (*FIELDS, "broker_order_id"),
    ("time", *FIELDS[1:]),
])
def test_exact_header_prevents_duplicate_or_unknown_column_silent_override(tmp_path, bad_header):
    manifest, rows = _fixture(tmp_path)
    manifest = _replace_rows(tmp_path, manifest, rows, header=bad_header)
    with pytest.raises(Stage59HistoryBlocked, match="header"):
        _run(tmp_path, manifest)


def test_unexpected_extra_csv_fields_rejected_even_with_valid_hash(tmp_path):
    manifest, _ = _fixture(tmp_path)
    path = tmp_path / manifest.filename
    text = path.read_text()
    text = text.replace("2000\n", "2000,EXTRA\n")
    path.write_text(text)
    manifest = replace(manifest, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(Stage59HistoryBlocked, match="malformed"):
        _run(tmp_path, manifest)


def test_invalid_utf8_content_rejected_without_data_return(tmp_path):
    manifest, _ = _fixture(tmp_path)
    path = tmp_path / manifest.filename
    path.write_bytes(path.read_bytes() + b"\xff")
    manifest = replace(manifest, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(Stage59HistoryBlocked, match="UTF-8"):
        _run(tmp_path, manifest)


@pytest.mark.parametrize("filename", ["../future_qa.csv", "/tmp/future_qa.csv", "nested/a.csv", "..csv", "abc.csv.bak"])
def test_path_traversal_and_non_csv_names_fail_closed(tmp_path, filename):
    m, _ = _fixture(tmp_path)
    with pytest.raises(Stage59HistoryBlocked, match="basename"):
        _run(tmp_path, replace(m, filename=filename))


def test_symlink_source_and_root_refused(tmp_path):
    main = tmp_path / "data"
    manifest, _ = _fixture(main)
    link = tmp_path / "link.csv"
    try:
        link.symlink_to(main / manifest.filename)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unsupported")
    with pytest.raises(Stage59HistoryBlocked, match="linked"):
        _run(main, replace(manifest, filename="link.csv"))
    folder_link = tmp_path / "folder_link"
    folder_link.symlink_to(main, target_is_directory=True)
    with pytest.raises(Stage59HistoryBlocked, match="root|folder|Unlinked"):
        _run(folder_link, manifest)


def test_missing_file_and_empty_file_refused(tmp_path):
    m, _ = _fixture(tmp_path)
    (tmp_path / m.filename).unlink()
    with pytest.raises(Stage59HistoryBlocked, match="Missing"):
        _run(tmp_path, m)
    (tmp_path / m.filename).write_bytes(b"")
    with pytest.raises(Stage59HistoryBlocked, match="Empty"):
        _run(tmp_path, m)


def test_limited_read_bytes_and_rows_reject_unbounded_data(tmp_path):
    m, _ = _fixture(tmp_path)
    with pytest.raises(Stage59HistoryBlocked, match="oversized"):
        _run(tmp_path, m, max_file_bytes=12)
    with pytest.raises(Stage59HistoryBlocked, match="row cap|grid"):
        _run(tmp_path, m, max_rows=2)


@pytest.mark.parametrize("kw", [
    {"max_rows": True}, {"max_rows": 0}, {"max_file_bytes": None},
    {"max_file_bytes": 0}, {"max_rows": 10001}, {"max_file_bytes": 16_000_001},
])
def test_invalid_resource_caps_rejected(tmp_path, kw):
    m, _ = _fixture(tmp_path)
    with pytest.raises(Stage59HistoryBlocked, match="budget"):
        _run(tmp_path, m, **kw)


@pytest.mark.parametrize("field,bad", [
    ("expected_sha256", "0" * 63), ("dataset_id", ""),
    ("provider_reference", ""), ("licence_reference", ""),
    ("calendar_reference", ""), ("contract_reference", ""),
    ("coverage_mode", "EVERYTHING"), ("dataset_class_claim", "REAL_APPROVED"),
    ("interval_minutes", 60), ("interval_minutes", True),
])
def test_bad_manifest_labels_and_config_refused(tmp_path, field, bad):
    m, _ = _fixture(tmp_path)
    with pytest.raises(Stage59HistoryBlocked):
        _run(tmp_path, replace(m, **{field: bad}))


def test_unverified_contract_source_fails_even_with_valid_file(tmp_path):
    m, _ = _fixture(tmp_path)
    with pytest.raises(Stage59HistoryBlocked, match="contract"):
        _run(tmp_path, m, contract=_contract(source_verified=False))


def test_contract_metadata_must_match_underlying_exchange_segment_and_source(tmp_path):
    m, _ = _fixture(tmp_path)
    for wrong in (
        _contract(underlying="FINNIFTY"),
        _contract(exchange="BSE"), _contract(segment="OPTIONS"),
        _contract(source_reference="other/source"),
    ):
        with pytest.raises(Stage59HistoryBlocked, match="contract"):
            _run(tmp_path, m, contract=wrong)


@pytest.mark.parametrize("contract", [
    _contract(effective_from=date(2026, 11, 3)),
    _contract(effective_to=date(2026, 11, 1)),
    _contract(expiry_date=date(2026, 11, 1)),
])
def test_point_in_time_contract_effective_and_expiry_window(tmp_path, contract):
    m, _ = _fixture(tmp_path)
    with pytest.raises(Stage59HistoryBlocked, match="expiry/effective"):
        _run(tmp_path, m, contract=contract)


def test_calendar_closed_day_does_not_implicitly_open(tmp_path):
    m, _ = _fixture(tmp_path)
    closed = nse_equity_derivatives_baseline(
        holidays=frozenset({date(2026, 11, 2)})
    )
    with pytest.raises(Stage59HistoryBlocked, match="session"):
        _run(tmp_path, m, calendar=closed)


def test_off_session_declared_first_candle_refused(tmp_path):
    after = datetime.fromisoformat("2026-11-02T17:30:00+05:30")
    m, _ = _fixture(tmp_path, start=after)
    with pytest.raises(Stage59HistoryBlocked, match="session"):
        _run(tmp_path, m)


def test_session_relative_half_minute_grid_refused(tmp_path):
    after = datetime.fromisoformat("2026-11-02T09:15:30+05:30")
    m, _ = _fixture(tmp_path, start=after)
    with pytest.raises(Stage59HistoryBlocked, match="aligned"):
        _run(tmp_path, m)


def test_window_crossing_market_close_refused(tmp_path):
    last_open = datetime.fromisoformat("2026-11-02T15:29:00+05:30")
    m, _ = _fixture(tmp_path, start=last_open, count=2)
    with pytest.raises(Stage59HistoryBlocked, match="session"):
        _run(tmp_path, m)


def test_no_multiday_partition_even_when_both_days_are_open(tmp_path):
    m, _ = _fixture(tmp_path)
    m = replace(m, expected_last=START + timedelta(days=1))
    with pytest.raises(Stage59HistoryBlocked, match="multiple India market days"):
        _run(tmp_path, m)


def test_query_cannot_silently_return_incomplete_or_wrong_market_candles(tmp_path):
    m, _ = _fixture(tmp_path)
    r = _run(tmp_path, m)
    t = timedelta(minutes=1)
    for q in (
        CandleQuery("OTHERFUT", "1m", m.expected_first, m.expected_last + t),
        CandleQuery(r.symbol, "5m", m.expected_first, m.expected_last + t),
        CandleQuery(r.symbol, "1m", m.expected_first - t, m.expected_last + t),
        CandleQuery(r.symbol, "1m", m.expected_first, m.expected_last + 2 * t),
        CandleQuery(r.symbol, "1m", m.expected_first + timedelta(seconds=30),
                    m.expected_last + t),
    ):
        with pytest.raises(Stage59HistoryBlocked):
            r.fetch_candles(q)


def test_query_result_has_no_depth_or_verified_vendor_claim(tmp_path):
    m, _ = _fixture(tmp_path)
    r = _run(tmp_path, m)
    assert not hasattr(r, "ask_depth")
    assert not hasattr(r, "live_broker")
    assert not hasattr(r, "submit_order")
    _assert_not_authoritative(r)


def test_stage59_cli_smoke_is_only_synthetic_and_never_promotes():
    import json
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_stage59_futures_history_smoke.py")],
        cwd=root, capture_output=True, text=True, check=False, timeout=35,
    )
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    assert data["mode"] == "STAGE59_SYNTHETIC_FUTURES_HISTORY_PREFLIGHT_ONLY"
    assert data["nifty"]["count"] == 3
    assert data["banknifty"]["count"] == 3
    assert data["tampered_file_denied"] is True
    assert data["missing_minute_denied"] is True
    assert data["nifty"]["licence_authenticated"] is False
    assert data["banknifty"]["real_orderbook_depth_present"] is False
    assert data["nifty"]["approved_for_strategy_promotion"] is False
    assert data["live_orders_transmitted"] == 0
    assert data["production_ready"] is False

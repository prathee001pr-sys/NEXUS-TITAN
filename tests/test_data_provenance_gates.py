from datetime import date
from pathlib import Path

import pytest

from nexus_titan.data.provenance import DatasetManifest, build_manifest_from_csv, verify_dataset_manifest
from nexus_titan.data.quality import inspect_candle_batch
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle
from datetime import datetime, timezone


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text(
        "timestamp,open,high,low,close,volume\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def _promotion_evidence() -> dict[str, str]:
    return {
        "vendor_identity_evidence_ref": "evidence/vendor-contract.pdf#page=1",
        "licence_evidence_ref": "evidence/data-licence.pdf#page=3",
        "coverage_evidence_ref": "evidence/coverage-audit.json",
        "instrument_metadata_evidence_ref": "evidence/nse-contract-master.csv",
        "evidence_reviewed_by": "human-reviewer",
        "evidence_reviewed_at": "2026-11-01T10:00:00+05:30",
    }


def test_calendar_quality_rejects_candle_outside_exchange_session():
    calendar = nse_equity_derivatives_baseline()
    candle = OHLCVCandle(
        "NIFTY", "1m", datetime(2026, 10, 31, 4, 30, tzinfo=timezone.utc),
        100, 101, 99, 100, 10, "test",
    )  # Saturday, 10:00 IST
    query = CandleQuery(
        "NIFTY", "1m", datetime(2026, 10, 31, 4, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 31, 4, 31, tzinfo=timezone.utc),
    )
    report = inspect_candle_batch([candle], query, calendar=calendar)
    assert report.outside_session == (candle.timestamp,)
    assert not report.is_valid


def test_manifest_does_not_assume_missing_bars_are_zero_without_calendar_audit(tmp_path):
    path = tmp_path / "sample.csv"
    _write_csv(path, [
        "2026-10-26T09:15:00+05:30,100,101,99,100,10",
        "2026-10-26T09:16:00+05:30,100,101,99,100,10",
    ])
    manifest = build_manifest_from_csv(path, dataset_id="NO-CALENDAR")
    assert manifest.missing_bars_count is None
    assert not manifest.coverage_verified
    ok, issues = verify_dataset_manifest(manifest, path)
    assert not ok
    assert any("missing-bar count is unknown" in item.lower() for item in issues)


def test_manifest_coverage_audit_blocks_missing_intraday_candle(tmp_path):
    path = tmp_path / "gap.csv"
    _write_csv(path, [
        "2026-10-26T09:15:00+05:30,100,101,99,100,10",
        "2026-10-26T09:17:00+05:30,100,101,99,100,10",
    ])
    manifest = build_manifest_from_csv(
        path, dataset_id="GAP", interval="1m", dataset_class="LICENSED_EXCHANGE_HISTORY",
        vendor_name="ExampleVendor", licence_id="LIC-1", calendar=nse_equity_derivatives_baseline(),
    )
    assert not manifest.coverage_verified
    assert manifest.missing_bars_count is None
    assert "gap span(s)" in manifest.notes


def test_promotion_manifest_requires_independent_evidence_references(tmp_path):
    path = tmp_path / "good.csv"
    _write_csv(path, [
        "2026-10-26T09:15:00+05:30,100,101,99,100,10",
        "2026-10-26T09:16:00+05:30,100,101,99,100,10",
    ])
    with pytest.raises(ValueError, match="explicit evidence"):
        build_manifest_from_csv(
            path, dataset_id="NO-EVIDENCE", interval="1m",
            dataset_class="LICENSED_EXCHANGE_HISTORY", vendor_name="ExampleVendor",
            licence_id="LIC-1", survivorship_bias_free=True,
            allowed_for_strategy_promotion=True, calendar=nse_equity_derivatives_baseline(),
        )


def test_well_evidenced_calendar_audited_manifest_rechecks_successfully(tmp_path):
    path = tmp_path / "good.csv"
    _write_csv(path, [
        "2026-10-26T09:15:00+05:30,100,101,99,100,10",
        "2026-10-26T09:16:00+05:30,100,101,99,100,10",
    ])
    calendar = nse_equity_derivatives_baseline()
    manifest = build_manifest_from_csv(
        path, dataset_id="REVIEWED", interval="1m", dataset_class="LICENSED_EXCHANGE_HISTORY",
        vendor_name="ExampleVendor", licence_id="LIC-1", survivorship_bias_free=True,
        allowed_for_strategy_promotion=True, calendar=calendar, **_promotion_evidence(),
    )
    ok, issues = verify_dataset_manifest(manifest, path, calendar=calendar)
    assert ok, issues


def test_coverage_marked_verified_requires_calendar_recheck(tmp_path):
    path = tmp_path / "good.csv"
    _write_csv(path, [
        "2026-10-26T09:15:00+05:30,100,101,99,100,10",
        "2026-10-26T09:16:00+05:30,100,101,99,100,10",
    ])
    calendar = nse_equity_derivatives_baseline()
    manifest = build_manifest_from_csv(
        path, dataset_id="REVIEWED", interval="1m", dataset_class="LICENSED_EXCHANGE_HISTORY",
        vendor_name="ExampleVendor", licence_id="LIC-1", survivorship_bias_free=True,
        allowed_for_strategy_promotion=True, calendar=calendar, **_promotion_evidence(),
    )
    ok, issues = verify_dataset_manifest(manifest, path)
    assert not ok
    assert any("no market calendar" in item.lower() for item in issues)


def test_manifest_rejects_boolean_counts_and_naive_review_timestamp(tmp_path):
    path = tmp_path / "good.csv"
    _write_csv(path, ["2026-10-26T09:15:00+05:30,100,101,99,100,10"])
    import hashlib
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="bar_count"):
        DatasetManifest(
            dataset_id="BAD", file_path=str(path), sha256_checksum=digest, vendor_name="Vendor",
            licence_id="LIC", instrument_symbol="NIFTY", venue="NSE", interval="1m",
            timezone_name="Asia/Kolkata", start_timestamp="2026-10-26T03:45:00+00:00",
            end_timestamp="2026-10-26T03:45:00+00:00", bar_count=True,
        )

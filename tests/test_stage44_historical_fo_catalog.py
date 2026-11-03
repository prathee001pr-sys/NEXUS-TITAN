"""Stage44 offline multi-contract catalog tests: synthetic CSV data only."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from nexus_titan.data.historical_fo_bundle import (
    HistoricalBundleDeclaration,
    HistoricalSnapshotFile,
)
from nexus_titan.data.historical_fo_catalog import (
    HistoricalCatalogError,
    HistoricalContractPartition,
    preflight_historical_fo_catalog,
)
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_ingest import COLUMNS, OptionChainIngestionError
from nexus_titan.data.sessions import nse_equity_derivatives_baseline


START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")
EXPIRY = date(2026, 11, 5)


def _fixture(root, dataset_id, underlying="NIFTY", *, start=START, count=3):
    root.mkdir(parents=True, exist_ok=True)
    symbol = underlying + "OPT"
    contract = PointInTimeContractSpec(
        symbol=symbol, underlying=underlying, exchange="NSE",
        segment="OPTIONS", lot_size=25, tick_size=0.05,
        freeze_quantity=1000, max_lots_per_trade=10,
        strike_step=50, effective_from=date(2026, 11, 1),
        effective_to=EXPIRY, expiry_date=EXPIRY,
        source_reference="test/unverified-contract-claim",
        source_verified=True,
    )
    snapshots = []
    for i in range(count):
        when = start + timedelta(minutes=i)
        name = f"chain_{i:03d}.csv"
        rows = []
        for option_type in ("CE", "PE"):
            row = {
                "timestamp": when.isoformat(),
                "symbol": symbol,
                "underlying": underlying,
                "expiry_date": EXPIRY.isoformat(),
                "strike": "100", "option_type": option_type,
                "bid": "5.00", "ask": "5.50", "ltp": "5.25",
                "volume": "1000", "open_interest": "1500",
                "underlying_spot": "100", "lot_size": "25",
            }
            rows.append(",".join(row[field] for field in COLUMNS))
        payload = (",".join(COLUMNS) + "\n" + "\n".join(rows) + "\n").encode()
        (root / name).write_bytes(payload)
        snapshots.append(HistoricalSnapshotFile(
            filename=name, observed_at=when, sha256=hashlib.sha256(payload).hexdigest(),
        ))
    declaration = HistoricalBundleDeclaration(
        dataset_id=dataset_id,
        underlying=underlying,
        provider_reference="synthetic/unverified-source",
        licence_reference="synthetic/unverified-rights",
        calendar_reference="synthetic/unverified-calendar",
        contract_reference=contract.source_reference,
        declared_start=snapshots[0].observed_at,
        declared_end=snapshots[-1].observed_at,
        snapshots=tuple(snapshots),
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    return HistoricalContractPartition(
        root=root, declaration=declaration, contract=contract,
        calendar=nse_equity_derivatives_baseline(),
    )


def test_two_underlyings_are_structurally_valid_but_never_authenticated(tmp_path):
    nifty = _fixture(tmp_path / "nifty", "nifty-synthetic")
    bank = _fixture(tmp_path / "bank", "bank-synthetic", "BANKNIFTY")
    report = preflight_historical_fo_catalog((nifty, bank))
    assert report.dataset_count == 2
    assert report.snapshot_count == 6
    assert report.unique_contracts == 2
    assert report.first_observed_at == START.astimezone(report.first_observed_at.tzinfo)
    assert report.external_source_authenticated is False
    assert report.licence_authenticated is False
    assert report.point_in_time_exchange_metadata_authenticated is False
    assert report.exchange_calendar_authenticated is False
    assert report.full_market_history_coverage_verified is False
    assert report.realistic_fo_backtest_verified is False
    assert report.strategy_promotion_allowed is False
    assert report.live_orders_transmitted == 0
    assert all(not p.preflight.approved_for_strategy_promotion for p in report.partitions)


def test_split_nonoverlapping_partitions_of_same_contract(tmp_path):
    a = _fixture(tmp_path / "a", "a")
    b = _fixture(tmp_path / "b", "b", start=START + timedelta(minutes=3))
    out = preflight_historical_fo_catalog((b, a))
    assert out.unique_contracts == 1
    assert out.snapshot_count == 6


def test_overlap_in_same_contract_is_rejected(tmp_path):
    a = _fixture(tmp_path / "a", "a")
    b = _fixture(tmp_path / "b", "b", start=START + timedelta(minutes=2))
    with pytest.raises(HistoricalCatalogError, match="overlapping"):
        preflight_historical_fo_catalog((a, b))


def test_duplicate_dataset_identity_fails_closed(tmp_path):
    a = _fixture(tmp_path / "a", "same")
    b = _fixture(tmp_path / "b", "same", "BANKNIFTY")
    with pytest.raises(HistoricalCatalogError, match="duplicate dataset_id"):
        preflight_historical_fo_catalog((a, b))


def test_contract_metadata_effective_date_required_for_every_partition(tmp_path):
    item = _fixture(tmp_path / "a", "a")
    invalid = replace(item.contract, effective_from=date(2026, 11, 3))
    with pytest.raises(HistoricalCatalogError, match="effective window"):
        preflight_historical_fo_catalog((replace(item, contract=invalid),))


def test_explicit_expiry_required_and_expired_observations_rejected(tmp_path):
    item = _fixture(tmp_path / "a", "a")
    with pytest.raises(HistoricalCatalogError, match="explicit expiry_date"):
        preflight_historical_fo_catalog((replace(item, contract=replace(item.contract, expiry_date=None)),))
    with pytest.raises(HistoricalCatalogError, match="past contract expiry"):
        preflight_historical_fo_catalog((replace(item, contract=replace(item.contract, expiry_date=date(2026, 11, 1))),))


def test_tampered_second_partition_never_returns_partial_catalog(tmp_path):
    a = _fixture(tmp_path / "a", "a")
    b = _fixture(tmp_path / "b", "b", "BANKNIFTY")
    file_path = b.root / b.declaration.snapshots[1].filename
    file_path.write_bytes(file_path.read_bytes() + b"tampered")
    with pytest.raises(OptionChainIngestionError, match="checksum mismatch"):
        preflight_historical_fo_catalog((a, b))


@pytest.mark.parametrize("limit", ["max_partitions", "max_total_snapshots", "max_total_source_bytes"])
def test_invalid_aggregate_limits_rejected(tmp_path, limit):
    item = _fixture(tmp_path / "a", "a")
    for invalid in (False, 0, -1):
        with pytest.raises(HistoricalCatalogError, match="integer"):
            preflight_historical_fo_catalog((item,), **{limit: invalid})


def test_partition_and_snapshot_budget_caps(tmp_path):
    item = _fixture(tmp_path / "a", "a")
    with pytest.raises(HistoricalCatalogError, match="bounded nonempty"):
        preflight_historical_fo_catalog((item, item), max_partitions=1)
    with pytest.raises(HistoricalCatalogError, match="snapshot count"):
        preflight_historical_fo_catalog((item,), max_total_snapshots=2)
    with pytest.raises(HistoricalCatalogError, match="source byte budget"):
        preflight_historical_fo_catalog((item,), max_total_source_bytes=30)


def test_empty_catalog_and_wrong_entry_types_are_rejected():
    with pytest.raises(HistoricalCatalogError, match="bounded nonempty"):
        preflight_historical_fo_catalog(())
    with pytest.raises(HistoricalCatalogError, match="invalid partition type"):
        preflight_historical_fo_catalog((object(),))


def test_original_snapshot_files_are_never_modified(tmp_path):
    item = _fixture(tmp_path / "a", "a")
    original = {p.name: p.read_bytes() for p in item.root.iterdir()}
    a = preflight_historical_fo_catalog((item,))
    b = preflight_historical_fo_catalog((item,))
    assert a == b
    assert original == {p.name: p.read_bytes() for p in item.root.iterdir()}

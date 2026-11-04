"""Stage71: synthetic NSE F&O as-of joins only; no real market claims."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from nexus_titan.data.historical_fo_bundle import (
    HistoricalBundleDeclaration, HistoricalSnapshotFile,
)
from nexus_titan.data.historical_fo_catalog import (
    HistoricalContractPartition, preflight_historical_fo_catalog,
)
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_ingest import COLUMNS
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.data.stage59_futures_history import (
    Stage59FuturesCSVDeclaration, preflight_stage59_futures_csv,
)
from nexus_titan.data.stage71_fo_asof_alignment import (
    Stage71AlignmentBlocked, align_stage71_fo_research_inputs,
)

ROOT = Path(__file__).resolve().parents[1]
START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")
EXPIRY = date(2026, 11, 5)
F_FIELDS = (
    "timestamp", "symbol", "exchange", "segment", "expiry_date", "lot_size",
    "open", "high", "low", "close", "volume", "open_interest",
)


def contract(underlying: str, segment: str):
    return PointInTimeContractSpec(
        symbol=underlying + ("FUT" if segment == "FUTURES" else "OPT"),
        underlying=underlying, exchange="NSE", segment=segment,
        lot_size=25, tick_size=0.05, freeze_quantity=1000,
        effective_from=date(2026, 11, 1), effective_to=EXPIRY,
        expiry_date=EXPIRY, source_reference="qa/source-is-unverified",
        source_verified=True,
    )


def fixtures(root: Path, underlying="NIFTY", *,
             future_count=4, future_interval=1, option_start_minute=1,
             option_count=2, dataset="qa-options"):
    root.mkdir(parents=True, exist_ok=True)
    cal = nse_equity_derivatives_baseline()
    fc, oc = contract(underlying, "FUTURES"), contract(underlying, "OPTIONS")
    f_root = root / "future"
    o_root = root / "options"
    f_root.mkdir(exist_ok=True)
    o_root.mkdir(exist_ok=True)
    f_body = ",".join(F_FIELDS) + "\n"
    for i in range(future_count):
        vals = {
            "timestamp": (START + timedelta(minutes=i * future_interval)).isoformat(),
            "symbol": fc.symbol, "exchange": "NSE", "segment": "FUTURES",
            "expiry_date": EXPIRY.isoformat(), "lot_size": "25",
            "open": "100.00", "high": "101.00", "low": "99.00",
            "close": "100.05", "volume": "1000", "open_interest": "1500",
        }
        f_body += ",".join(vals[n] for n in F_FIELDS) + "\n"
    (f_root / "future.csv").write_bytes(f_body.encode("utf-8"))
    decl = Stage59FuturesCSVDeclaration(
        dataset_id="qa-futures", filename="future.csv",
        expected_sha256=hashlib.sha256(f_body.encode("utf-8")).hexdigest(),
        provider_reference="qa-provider-unverified", licence_reference="qa-unverified",
        calendar_reference="qa-unverified", contract_reference=fc.source_reference,
        expected_first=START,
        expected_last=START + timedelta(minutes=(future_count-1)*future_interval),
        interval_minutes=future_interval,
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    future = preflight_stage59_futures_csv(
        f_root, declaration=decl, contract=fc, calendar=cal,
    )
    snapshots = []
    for i in range(option_count):
        when = START + timedelta(minutes=option_start_minute+i)
        filename = f"chain_{i}.csv"
        lines = [",".join(COLUMNS)]
        for option_type in ("CE", "PE"):
            vals = {
                "timestamp": when.isoformat(), "symbol": oc.symbol,
                "underlying": underlying, "expiry_date": EXPIRY.isoformat(),
                "strike": "100", "option_type": option_type,
                "bid": "5.00", "ask": "5.50", "ltp": "5.25",
                "volume": "1000", "open_interest": "1500",
                "underlying_spot": "100", "lot_size": "25",
            }
            lines.append(",".join(vals[k] for k in COLUMNS))
        data = ("\n".join(lines) + "\n").encode()
        (o_root / filename).write_bytes(data)
        snapshots.append(HistoricalSnapshotFile(
            filename=filename, observed_at=when,
            sha256=hashlib.sha256(data).hexdigest(),
        ))
    opt = HistoricalBundleDeclaration(
        dataset_id=dataset, underlying=underlying,
        provider_reference="qa-provider-unverified", licence_reference="qa-licence-unverified",
        calendar_reference="qa-calendar-unverified", contract_reference=oc.source_reference,
        declared_start=snapshots[0].observed_at,
        declared_end=snapshots[-1].observed_at,
        snapshots=tuple(snapshots),
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    catalog = preflight_historical_fo_catalog((
        HistoricalContractPartition(
            root=o_root, declaration=opt, contract=oc, calendar=cal,
        ),
    ))
    return future, catalog


def denied(result):
    assert result.vendor_identity_independently_authenticated is False
    assert result.data_licence_independently_authenticated is False
    assert result.point_in_time_exchange_contracts_authenticated is False
    assert result.independent_calendar_verified is False
    assert result.real_market_depth_verified is False
    assert result.historically_complete_fo_universe_verified is False
    assert result.leak_free_full_training_pipeline_verified is False
    assert result.model_performance_verified is False
    assert result.approved_for_strategy_promotion is False
    assert result.paper_order_authorized is False
    assert result.live_trading_enabled is False
    assert result.broker_orders_transmitted == 0
    assert "NO_GO" in result.verdict


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
def test_verified_structural_preflights_align_only_completed_bars(tmp_path, underlying):
    future, catalog = fixtures(tmp_path, underlying=underlying)
    result = align_stage71_fo_research_inputs(future, catalog)
    assert result.aligned_observation_count == 2
    assert result.observed_futures_bars == 4
    assert result.option_dataset_count == 1
    assert len(result.input_alignment_sha256) == 64
    assert result.observations[0].futures_bar_opened_at < result.observations[0].option_observed_at
    assert all(r.futures_bar_closed_at <= r.option_observed_at for r in result.observations)
    assert result.observations[0].futures_age_seconds == 0
    assert result.observations[1].futures_age_seconds == 0
    assert align_stage71_fo_research_inputs(future, catalog) == result
    denied(result)


def test_no_future_candle_close_lookahead(tmp_path):
    future, catalog = fixtures(tmp_path, future_interval=5,
                               future_count=2, option_start_minute=1)
    with pytest.raises(Stage71AlignmentBlocked, match="not completed"):
        align_stage71_fo_research_inputs(future, catalog)


def test_stale_completed_candle_is_rejected(tmp_path):
    future, catalog = fixtures(tmp_path, future_interval=5,
                               future_count=2, option_start_minute=6)
    with pytest.raises(Stage71AlignmentBlocked, match="stale"):
        align_stage71_fo_research_inputs(
            future, catalog, max_futures_age_seconds=0,
        )


def test_mismatched_futures_and_option_underlyings_refused(tmp_path):
    future, _ = fixtures(tmp_path / "a", "NIFTY")
    _, other = fixtures(tmp_path / "b", "BANKNIFTY")
    with pytest.raises(Stage71AlignmentBlocked, match="underlying"):
        align_stage71_fo_research_inputs(future, other)


def test_forged_authority_flags_never_pass(tmp_path):
    future, catalog = fixtures(tmp_path)
    with pytest.raises(Stage71AlignmentBlocked, match="authority"):
        align_stage71_fo_research_inputs(
            replace(future, licence_authenticated=True), catalog,
        )
    with pytest.raises(Stage71AlignmentBlocked, match="authority"):
        align_stage71_fo_research_inputs(
            future, replace(catalog, strategy_promotion_allowed=True),
        )


def test_untrusted_futures_csv_hash_or_count_rejected(tmp_path):
    future, catalog = fixtures(tmp_path)
    with pytest.raises(Stage71AlignmentBlocked, match="SHA-256"):
        align_stage71_fo_research_inputs(replace(future, file_sha256="xyz"), catalog)
    with pytest.raises(Stage71AlignmentBlocked, match="count"):
        align_stage71_fo_research_inputs(replace(future, count=3), catalog)


def test_duplicate_or_out_of_order_option_snapshots_rejected(tmp_path):
    future, catalog = fixtures(tmp_path)
    part = catalog.partitions[0]
    bad_history = replace(
        part.history,
        snapshots=tuple(reversed(part.history.snapshots)),
    )
    with pytest.raises(Stage71AlignmentBlocked, match="out of order"):
        align_stage71_fo_research_inputs(
            future, replace(catalog, partitions=(replace(part, history=bad_history),)),
        )


def test_no_partial_output_for_missing_completed_data(tmp_path):
    future, catalog = fixtures(tmp_path, option_start_minute=1, option_count=3)
    # One snapshot at 09:18 has no 09:18 completed candle: latest is 09:18.
    # Tight zero-age requirement forces entire dataset rejection when last
    # candle source is removed.
    shorter = replace(future, candles=future.candles[:-1],
                      count=3, expected_slots=3,
                      last_observed_at=future.candles[-2].timestamp)
    with pytest.raises(Stage71AlignmentBlocked, match="stale"):
        align_stage71_fo_research_inputs(shorter, catalog, max_futures_age_seconds=0)


@pytest.mark.parametrize("bad", [False, -1, 901, 0.5])
def test_bad_lag_budget_rejected(tmp_path, bad):
    future, catalog = fixtures(tmp_path)
    with pytest.raises(Stage71AlignmentBlocked, match="budgets"):
        align_stage71_fo_research_inputs(future, catalog, max_futures_age_seconds=bad)


def test_forged_internal_option_source_or_empty_chain_rejected(tmp_path):
    future, catalog = fixtures(tmp_path)
    part = catalog.partitions[0]
    first = part.history.snapshots[0]
    bad_history = replace(
        part.history,
        snapshots=(replace(first, quotes=()),) + part.history.snapshots[1:],
    )
    with pytest.raises(Stage71AlignmentBlocked, match="empty chain"):
        align_stage71_fo_research_inputs(
            future, replace(catalog, partitions=(replace(part, history=bad_history),)),
        )


def test_cli_json_always_no_go(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage71_fo_alignment_smoke.py")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    packet = json.loads(completed.stdout)
    assert packet["mode"] == "STAGE71_NO_INPUTS_RESEARCH_NO_GO"
    assert packet["live_trading_enabled"] is False
    assert packet["broker_orders_transmitted"] == 0

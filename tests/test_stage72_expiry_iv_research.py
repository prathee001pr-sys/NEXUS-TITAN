"""Stage72 Greeks/IV envelope bounded synthetic tests. Never real F&O claims."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import subprocess
import sys

import pytest

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_ingest import ResearchOptionChainSnapshot
from nexus_titan.data.stage71_fo_asof_alignment import (
    Stage71AlignedObservation, Stage71FOLearningPreflight,
)
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote
from nexus_titan.derivatives.stage72_expiry_iv_research import (
    Stage72ResearchBlocked, _price, analyse_stage72_options_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")
AT = datetime(2026, 11, 2, 9, 16, tzinfo=IST)
CUTOFF = datetime(2026, 11, 5, 15, 30, tzinfo=IST)
SHA = hashlib.sha256(b"synthetic-stage72").hexdigest()


def fixture(underlying="NIFTY"):
    contract = PointInTimeContractSpec(
        symbol=underlying + "OPT", underlying=underlying, exchange="NSE",
        segment="OPTIONS", lot_size=25, tick_size=0.05,
        freeze_quantity=1000, strike_step=50.0, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1), effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5),
        source_reference="qa/claimed-not-external", source_verified=True,
    )
    days = (CUTOFF - AT).total_seconds() / 86400
    rows = []
    for side in ("CE", "PE"):
        fair = _price(24000.0, 24000.0, days/365.0, 0.20, 0.06, 0.0, side)
        mid = round(round(fair/0.05) * 0.05, 2)
        rows.append(OptionChainQuote(
            timestamp=AT.isoformat(), symbol=contract.symbol,
            underlying=underlying, expiry_date="2026-11-05",
            strike=24000.0, option_type=side,
            bid=round(mid-1.0, 2), ask=round(mid+1.0, 2), ltp=mid,
            volume=1000, open_interest=5000, underlying_spot=24000.0,
            lot_size=25,
        ))
    snapshot = ResearchOptionChainSnapshot(
        quotes=tuple(rows), sha256=SHA, observed_at=AT,
        provider_reference="qa/synthetic", licence_evidence_reference="qa/unverified",
        calendar_evidence_reference="qa/unverified",
        contract_evidence_reference="qa/unverified",
    )
    close = AT - timedelta(minutes=1)
    paired = Stage71AlignedObservation(
        underlying=underlying, option_dataset_id="qa-options",
        option_snapshot_sha256=SHA,
        option_observed_at=AT.astimezone(timezone.utc),
        option_quote_count=2, futures_dataset_id="qa-future",
        futures_csv_sha256=SHA, futures_bar_opened_at=close-timedelta(minutes=1),
        futures_bar_closed_at=close, futures_age_seconds=60,
    )
    aligned = Stage71FOLearningPreflight(
        underlying=underlying, option_dataset_count=1,
        observed_option_snapshots=1, observed_futures_bars=1,
        aligned_observation_count=1,
        first_option_observed_at=AT,
        last_option_observed_at=AT,
        latest_completed_futures_at=close, input_alignment_sha256=SHA,
        observations=(paired,),
    )
    return snapshot, contract, aligned


def run(case, **changes):
    snapshot, contract, aligned = case
    return analyse_stage72_options_snapshot(
        snapshot=snapshot, contract=contract, aligned=aligned,
        declared_expiry_cutoff=CUTOFF,
        risk_free_rate=0.06, dividend_yield=0.0, **changes,
    )


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
def test_mid_bid_ask_iv_and_greeks_bounds_under_synthetic_data(underlying):
    case = fixture(underlying)
    result = run(case)
    assert result.underlying == underlying
    assert len(result.rows) == 2
    assert len(result.research_output_sha256) == 64
    assert result == run(case)
    for row in result.rows:
        assert row.iv_bid < row.iv_mid < row.iv_ask
        assert abs(row.iv_mid - 0.2) < 0.015
        assert row.spread_bps < 1200
        assert row.model_greeks_at_mid.theoretical_price > 0
        if row.option_type == "CE":
            assert 0 < row.model_greeks_at_mid.delta < 1
        else:
            assert -1 < row.model_greeks_at_mid.delta < 0
    for name in (
        "contract_master_independently_authenticated",
        "vendor_and_licence_independently_authenticated",
        "official_expiry_cutoff_authenticated", "tradeable_bid_ask_depth_verified",
        "model_calibration_or_accuracy_verified",
        "expiry_settlement_and_costs_verified",
        "strategy_promotion_authorized", "paper_order_authorized",
        "live_trading_enabled",
    ):
        assert getattr(result, name) is False
    assert result.broker_orders_transmitted == 0
    assert "NO_GO" in result.release_verdict


def test_unpaired_snapshot_source_hash_is_rejected():
    snap, contract, align = fixture()
    with pytest.raises(Stage72ResearchBlocked, match="uniquely"):
        run((replace(snap, sha256=hashlib.sha256(b"other").hexdigest()), contract, align))


def test_future_closed_after_snapshot_is_rejected():
    snap, contract, align = fixture()
    obs = replace(align.observations[0],
                  futures_bar_closed_at=AT + timedelta(seconds=1),
                  futures_age_seconds=-1)
    with pytest.raises(Stage72ResearchBlocked, match="Incomplete|future"):
        run((snap, contract, replace(align, observations=(obs,))))


def test_unauthenticated_expiry_cutoff_is_not_silently_assumed():
    snap, contract, align = fixture()
    with pytest.raises(Stage72ResearchBlocked, match="contract/expiry"):
        analyse_stage72_options_snapshot(
            snapshot=snap, contract=contract, aligned=align,
            declared_expiry_cutoff=CUTOFF + timedelta(days=1),
            risk_free_rate=0.06, dividend_yield=0.0,
        )


def test_near_expiry_greeks_fail_closed():
    snap, contract, align = fixture()
    near = datetime(2026, 11, 5, 15, 0, tzinfo=IST)
    snap = replace(snap, observed_at=near)
    proof = replace(align.observations[0], option_observed_at=near)
    aligned = replace(align, observations=(proof,))
    with pytest.raises(Stage72ResearchBlocked, match="too near"):
        analyse_stage72_options_snapshot(
            snapshot=snap, contract=contract, aligned=aligned,
            declared_expiry_cutoff=CUTOFF, risk_free_rate=0.06, dividend_yield=0.0,
        )


def test_wide_spread_and_unidentifiable_iv_both_refused():
    snap, contract, align = fixture()
    bad = replace(snap.quotes[0], bid=0.05)
    with pytest.raises(Stage72ResearchBlocked, match="unsafe|spread"):
        run((replace(snap, quotes=(bad, snap.quotes[1])), contract, align))
    impossible = replace(snap.quotes[0], bid=10000.0, ask=10001.0, ltp=10000.0)
    with pytest.raises(Stage72ResearchBlocked, match="unsafe|unidentifiable"):
        run((replace(snap, quotes=(impossible, snap.quotes[1])), contract, align))


def test_forged_lineage_or_model_authority_is_refused():
    snap, contract, align = fixture()
    with pytest.raises(Stage72ResearchBlocked, match="authority"):
        run((snap, contract, replace(align, model_performance_verified=True)))
    with pytest.raises(Stage72ResearchBlocked, match="lineage"):
        run((replace(snap, approved_for_strategy_promotion=True), contract, align))


@pytest.mark.parametrize("rate,div", [(float("nan"), 0), (0.06, float("inf")), (True, 0),
                                       (0.06, -0.01), (0.75, 0)])
def test_invalid_rate_assumptions_rejected(rate, div):
    snap, contract, align = fixture()
    with pytest.raises(Stage72ResearchBlocked, match="bounded"):
        analyse_stage72_options_snapshot(
            snapshot=snap, contract=contract, aligned=align,
            declared_expiry_cutoff=CUTOFF, risk_free_rate=rate, dividend_yield=div,
        )


def test_no_partial_output_for_one_bad_quote():
    snap, contract, align = fixture()
    bad = replace(snap.quotes[1], open_interest=0)
    with pytest.raises(Stage72ResearchBlocked, match="unsafe"):
        run((replace(snap, quotes=(snap.quotes[0], bad)), contract, align))


def test_reversed_or_duplicate_option_side_refused():
    snap, contract, align = fixture()
    with pytest.raises(Stage72ResearchBlocked, match="unsafe"):
        run((replace(snap, quotes=(snap.quotes[0], snap.quotes[0])), contract, align))


def test_no_network_cli_explicit_no_go():
    run_cli = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage72_iv_greeks_smoke.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert run_cli.returncode == 0, run_cli.stderr
    result = json.loads(run_cli.stdout)
    assert result["mode"] == "STAGE72_IV_GREEKS_NO_INPUT_RESEARCH_NO_GO"
    assert result["live_trading_enabled"] is False
    assert result["strategy_promotion_authorized"] is False
    assert result["broker_orders_transmitted"] == 0

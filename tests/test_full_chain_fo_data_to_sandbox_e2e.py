"""Non-production A-to-B integration proof: real module calls, fabricated input.

Runs Stage59+Stage44 file import -> 71 as-of -> 72 IV/Greeks -> 73
experience journal -> 74 long-option scenario -> 75 readiness -> 76
portfolio risk screen -> 77 synthetic SQLite hold/fill/cancel.

It is NOT "all stages globally integrated" or a live/real-market test.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
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
    align_stage71_fo_research_inputs,
)
from nexus_titan.derivatives.stage72_expiry_iv_research import (
    analyse_stage72_options_snapshot,
)
from nexus_titan.evolve.stage73_fo_experience import Stage73FOExperienceMemory
from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticPolicy,
)
from nexus_titan.operations.stage69_risk_budget_preflight import Stage69ResearchPreflight
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import (
    Stage76FOResearchPolicy, Stage76UntrustedRiskTelemetry,
    inspect_stage76_fo_portfolio_risk,
)
from nexus_titan.operations.stage77_brokerless_fo_sandbox import (
    Stage77BrokerlessFOSyntheticGateway, Stage77SyntheticGatewayBlocked,
)
from nexus_titan.shadow.stage75_fo_shadow_readiness import (
    Stage75ReadinessBlocked, Stage75VirtualResearchBudget,
    inspect_stage75_fo_shadow_readiness,
)
from nexus_titan.simulation.stage74_fo_options_scenario_lab import (
    simulate_stage74_long_option_scenarios,
)

START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")
EXPIRY = date(2026, 11, 5)
CUT_OFF = datetime.fromisoformat("2026-11-05T15:30:00+05:30")
FUT_COLS = (
    "timestamp", "symbol", "exchange", "segment", "expiry_date", "lot_size",
    "open", "high", "low", "close", "volume", "open_interest",
)
CAPITAL_CENTS = 10_000_000  # Variable synthetic starting balance, not hard-coded by engine.


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _contract(underlying: str, segment: str) -> PointInTimeContractSpec:
    return PointInTimeContractSpec(
        symbol=underlying + ("FUT" if segment == "FUTURES" else "OPT"),
        underlying=underlying,
        exchange="NSE", segment=segment, lot_size=25, tick_size=0.05,
        freeze_quantity=1000, effective_from=date(2026, 11, 1),
        effective_to=EXPIRY, expiry_date=EXPIRY,
        source_reference="synthetic-qa-unverified", source_verified=True,
    )


def _source_files(root: Path, underlying: str, history_bars=4, option_start_minute=1):
    """Generate strictly synthetic but truly ingested CSV files on disk."""
    root.mkdir(parents=True, exist_ok=True)
    froot, oroot = root / "futures", root / "options"
    froot.mkdir()
    oroot.mkdir()
    fc, oc = _contract(underlying, "FUTURES"), _contract(underlying, "OPTIONS")
    calendar = nse_equity_derivatives_baseline()
    futures_lines = [",".join(FUT_COLS)]
    for i in range(history_bars):
        values = {
            "timestamp": (START + timedelta(minutes=i)).isoformat(),
            "symbol": fc.symbol, "exchange": "NSE", "segment": "FUTURES",
            "expiry_date": EXPIRY.isoformat(), "lot_size": "25",
            "open": "100.00", "high": "101.00", "low": "99.00",
            "close": "100.05", "volume": "1000", "open_interest": "1500",
        }
        futures_lines.append(",".join(values[c] for c in FUT_COLS))
    fblob = ("\n".join(futures_lines) + "\n").encode()
    (froot / "futures.csv").write_bytes(fblob)
    fdecl = Stage59FuturesCSVDeclaration(
        dataset_id="qa-futures", filename="futures.csv",
        expected_sha256=_sha(fblob),
        provider_reference="unverified-synthetic-provider",
        licence_reference="unverified-synthetic-licence",
        calendar_reference="unverified-synthetic-calendar",
        contract_reference=fc.source_reference,
        expected_first=START, expected_last=START + timedelta(minutes=history_bars-1),
        interval_minutes=1, dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    futures = preflight_stage59_futures_csv(
        froot, declaration=fdecl, contract=fc, calendar=calendar,
    )
    declared = []
    for i in range(2):
        when = START + timedelta(minutes=i+option_start_minute)
        filename = f"chain{i}.csv"
        lines = [",".join(COLUMNS)]
        for side in ("CE", "PE"):
            quote = {
                "timestamp": when.isoformat(), "symbol": oc.symbol,
                "underlying": underlying, "expiry_date": EXPIRY.isoformat(),
                "strike": "100", "option_type": side, "bid": "5.00",
                "ask": "5.50", "ltp": "5.25", "volume": "1000",
                "open_interest": "1500", "underlying_spot": "100",
                "lot_size": "25",
            }
            lines.append(",".join(quote[c] for c in COLUMNS))
        blob = ("\n".join(lines) + "\n").encode()
        (oroot / filename).write_bytes(blob)
        declared.append(HistoricalSnapshotFile(
            filename=filename, observed_at=when, sha256=_sha(blob),
        ))
    odeclaration = HistoricalBundleDeclaration(
        dataset_id="qa-options",
        underlying=underlying,
        provider_reference="unverified-synthetic-provider",
        licence_reference="unverified-synthetic-licence",
        calendar_reference="unverified-synthetic-calendar",
        contract_reference=oc.source_reference,
        declared_start=declared[0].observed_at,
        declared_end=declared[-1].observed_at,
        snapshots=tuple(declared),
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    catalog = preflight_historical_fo_catalog((
        HistoricalContractPartition(
            root=oroot, declaration=odeclaration, contract=oc, calendar=calendar,
        ),
    ))
    return futures, catalog, oc


def integrated_chain(tmp_path, underlying="NIFTY", capital=CAPITAL_CENTS, history_bars=4, option_start_minute=1,
                     lots=1, option_type='CE'):
    futures, catalog, contract = _source_files(tmp_path, underlying, history_bars, option_start_minute)
    stage71 = align_stage71_fo_research_inputs(futures, catalog)
    snapshot = catalog.partitions[0].history.snapshots[0]
    stage72 = analyse_stage72_options_snapshot(
        snapshot=snapshot, contract=contract, aligned=stage71,
        declared_expiry_cutoff=CUT_OFF,
        risk_free_rate=0.06, dividend_yield=0.0,
    )
    episode = "qa-episode"
    when = stage72.observation_time
    memory = Stage73FOExperienceMemory()
    for model, probability in (("baseline", 0.50), ("challenger", 0.75)):
        memory.add_forecast(
            stage72, episode_id=episode, model_id=model,
            probability_up=probability, regime="TREND",
            predicted_at=when, horizon_at=when + timedelta(minutes=5),
            model_training_cutoff=when - timedelta(days=1),
        )
    memory.record_outcome(
        episode_id=episode, up=True,
        resolved_at=when + timedelta(minutes=6),
        declared_label_sha256=_sha(b"unverified-synthetic-outcome"),
    )
    stage73 = memory.compare(champion="baseline", challenger="challenger",
                             min_paired_samples=2)
    stage74 = simulate_stage74_long_option_scenarios(
        report=stage72, contract=contract, reference_spot=100.0,
        strike=100.0, option_type=option_type, lots=lots,
    )
    stage69 = Stage69ResearchPreflight(
        account_id="qa-fo-portfolio",
        request_id="synthetic-equity-reference",
        source="SYNTHETIC_EQUITY_RESEARCH",
        local_budget_integrity_checked=True,
        local_synthetic_risk_screen_passed=True,
        local_budget_caps_checked=True,
        local_research_preflight_passed=True,
        requested_notional_cents=1000,
        blockers=(), observed_budget_revision=1,
    )
    stage75 = inspect_stage75_fo_shadow_readiness(
        stage71=stage71, stage72=stage72, stage73=stage73,
        stage74=stage74, stage69=stage69,
        budget=Stage75VirtualResearchBudget(
            account_id="qa-fo-portfolio", virtual_capital_cents=capital,
        ),
    )
    pulse = Stage76UntrustedRiskTelemetry(
        account_id="qa-fo-portfolio", daily_realized_loss_bps=0,
        drawdown_bps=0, consecutive_losses=0,
        kill_switch_active=False, risk_engine_healthy=True,
    )
    stage76 = inspect_stage76_fo_portfolio_risk(
        packets=(stage75,), policy=Stage76FOResearchPolicy(),
        telemetry=pulse,
    )
    return {
        "futures": futures, "catalog": catalog,
        "71": stage71, "72": stage72, "73": stage73, "74": stage74,
        "75": stage75, "76": stage76,
        "pulse": pulse, "contract": contract,
    }


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
def test_real_python_calls_connect_synthetic_csv_all_the_way_to_sqlite(tmp_path, underlying):
    chain = integrated_chain(tmp_path / "data", underlying)
    assert chain["71"].aligned_observation_count == 2
    assert len(chain["72"].rows) == 2
    assert chain["73"].paired_count == 1
    assert not chain["73"].research_review_suggested
    assert len(chain["74"].outcomes) == 4
    assert chain["75"].local_chain_structurally_consistent
    assert chain["75"].research_budget_screen_passed
    assert chain["76"].local_research_fence_passed
    assert all(getattr(chain[str(i)], "broker_orders_transmitted") == 0
               for i in (71, 72, 73, 74, 75, 76))
    policy = Stage55SyntheticPolicy(
        max_single_reserve_bps=2000, max_open_reserve_bps=4500,
    )
    book = Stage55IsolatedSyntheticExecutionBook(
        db_path=tmp_path / "sandbox.sqlite", account_id="qa-fo-portfolio",
        starting_cents=CAPITAL_CENTS, policy=policy,
    )
    gateway = Stage77BrokerlessFOSyntheticGateway(
        book=book, research_packets=(chain["75"],),
        policy=Stage76FOResearchPolicy(),
    )
    research_debit = chain["75"].long_option_entry_debit_cents
    ask = next(q.ask for q in chain["72"].rows if q.option_type == "CE")
    quantity = chain["contract"].lot_size
    limit_cents = int(round(ask * 100))
    fee_buffer = research_debit - quantity * limit_cents
    assert 0 <= fee_buffer < research_debit
    reserved = gateway.reserve_synthetic_long_option(
        research_packet_sha256=chain["75"].research_packet_sha256,
        request_id="qa-reserve", symbol=chain["75"].option_symbol,
        lots=1, lot_size=quantity, limit_price_cents=limit_cents,
        fee_buffer_cents=fee_buffer, telemetry=chain["pulse"],
    )
    assert reserved.order_state == "PENDING_SYNTHETIC"
    assert reserved.reserved_cents_after == research_debit
    filled = gateway.record_synthetic_fill(
        request_id="qa-reserve", fill_id="qa-fill",
        quantity=quantity, price_cents=limit_cents,
        fee_cents=fee_buffer, telemetry=chain["pulse"],
    )
    assert filled.order_state == "FILLED_SYNTHETIC"
    assert filled.reserved_cents_after == 0
    status = book.inspect()
    assert status.local_integrity_verified
    assert status.cash_cents == CAPITAL_CENTS - research_debit
    assert status.revision == 2
    assert filled.broker_orders_transmitted == 0
    assert not filled.paper_order_authorized and not filled.live_trading_enabled


def test_end_to_end_bad_lineage_blocks_before_sqlite_reservation(tmp_path):
    chain = integrated_chain(tmp_path / "data")
    with pytest.raises(Stage75ReadinessBlocked, match="source digests"):
        inspect_stage75_fo_shadow_readiness(
            stage71=chain["71"], stage72=chain["72"],
            stage73=chain["73"], stage74=replace(
                chain["74"],
                source_stage71_sha256=_sha(b"mismatched-input"),
            ),
            stage69=Stage69ResearchPreflight(
                account_id="qa-fo-portfolio", request_id="equity-ref",
                source="SYNTHETIC_EQUITY_RESEARCH",
                local_budget_integrity_checked=True,
                local_synthetic_risk_screen_passed=True,
                local_budget_caps_checked=True,
                local_research_preflight_passed=True,
                requested_notional_cents=1000,
                blockers=(), observed_budget_revision=1,
            ),
            budget=Stage75VirtualResearchBudget(
                account_id="qa-fo-portfolio", virtual_capital_cents=CAPITAL_CENTS,
            ),
        )


def test_kill_switch_between_synthetic_reserve_and_fill_blocks_and_allows_cancel(tmp_path):
    chain = integrated_chain(tmp_path / "data")
    book = Stage55IsolatedSyntheticExecutionBook(
        db_path=tmp_path / "kill.sqlite",
        account_id="qa-fo-portfolio", starting_cents=CAPITAL_CENTS,
        policy=Stage55SyntheticPolicy(
            max_single_reserve_bps=2000, max_open_reserve_bps=4500,
        ),
    )
    gateway = Stage77BrokerlessFOSyntheticGateway(
        book=book, research_packets=(chain["75"],),
        policy=Stage76FOResearchPolicy(),
    )
    ask = next(r.ask for r in chain["72"].rows if r.option_type == "CE")
    qty = chain["contract"].lot_size
    price = int(round(ask * 100))
    fees = chain["75"].long_option_entry_debit_cents - qty * price
    gateway.reserve_synthetic_long_option(
        research_packet_sha256=chain["75"].research_packet_sha256,
        request_id="qa-risk-race", symbol=chain["75"].option_symbol,
        lots=1, lot_size=qty, limit_price_cents=price,
        fee_buffer_cents=fees, telemetry=chain["pulse"],
    )
    with pytest.raises(Stage77SyntheticGatewayBlocked, match="Risk gate denies"):
        gateway.record_synthetic_fill(
            request_id="qa-risk-race", fill_id="blocked-fill",
            quantity=qty, price_cents=price, fee_cents=fees,
            telemetry=replace(chain["pulse"], kill_switch_active=True),
        )
    assert book.inspect().revision == 1
    cancelled = gateway.cancel_synthetic_remaining(
        request_id="qa-risk-race", cancel_id="qa-cancel",
    )
    assert cancelled.order_state == "CANCELLED_SYNTHETIC"
    assert book.inspect().cash_cents == CAPITAL_CENTS
    assert book.inspect().open_reserved_cents == 0

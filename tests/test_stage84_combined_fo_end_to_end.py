"""Stage84: real Python synthetic NIFTY+BANKNIFTY end-to-end integration QA.

Reuse Stage59/44 -> 71..77 fixture generator, not mocked intermediate reports.
Runs two option underlyings into ONE Stage55 SQLite account, with Stage82
local stop and Stage83 capital reconciliation. Zero market/broker access.
"""
from __future__ import annotations

import runpy
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticPolicy,
)
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import (
    Stage76FOResearchPolicy, Stage76UntrustedRiskTelemetry,
    Stage76RiskBlocked, inspect_stage76_fo_portfolio_risk,
)
from nexus_titan.operations.stage77_brokerless_fo_sandbox import (
    Stage77BrokerlessFOSyntheticGateway, Stage77SyntheticGatewayBlocked,
)
from nexus_titan.operations.stage83_fo_capital_reconciliation import (
    Stage83LedgerMismatch, inspect_stage83_fo_account_reconciliation,
)

ROOT = Path(__file__).resolve().parents[1]
# Use the already-tested full CSV -> F&O data-chain fixture to avoid
# manufacturing fake Stage71/72/73/74 objects for the combined test.
chain_fixture = runpy.run_path(
    str(ROOT / "tests/test_full_chain_fo_data_to_sandbox_e2e.py")
)["integrated_chain"]
CAP = 10_000_000


def integrated(tmp_path):
    nifty = chain_fixture(tmp_path/"nifty", "NIFTY", CAP)
    bank = chain_fixture(tmp_path/"banknifty", "BANKNIFTY", CAP)
    packets=(nifty["75"],bank["75"])
    pulse=Stage76UntrustedRiskTelemetry(
        account_id="qa-fo-portfolio", daily_realized_loss_bps=0,
        drawdown_bps=0, consecutive_losses=0,
        kill_switch_active=False,risk_engine_healthy=True,
    )
    policy=Stage76FOResearchPolicy()
    research=inspect_stage76_fo_portfolio_risk(
        packets=packets, policy=policy,telemetry=pulse,
    )
    local=Stage55IsolatedSyntheticExecutionBook(
        db_path=tmp_path/"combined.sqlite",
        account_id="qa-fo-portfolio",starting_cents=CAP,
        policy=Stage55SyntheticPolicy(
            max_single_reserve_bps=2000,max_open_reserve_bps=4500,
        ),
    )
    gate=Stage77BrokerlessFOSyntheticGateway(
        book=local,research_packets=packets,policy=policy,
    )
    return nifty,bank,research,pulse,local,gate


def _reserve(gate,chain,pulse,request):
    row=next(r for r in chain["72"].rows if r.option_type=="CE")
    qty=chain["contract"].lot_size
    price=int(round(row.ask*100))
    fees=chain["75"].long_option_entry_debit_cents-qty*price
    assert fees>=0
    return gate.reserve_synthetic_long_option(
        research_packet_sha256=chain["75"].research_packet_sha256,
        request_id=request,symbol=chain["75"].option_symbol,
        lots=1,lot_size=qty,limit_price_cents=price,
        fee_buffer_cents=fees,telemetry=pulse,
    ),price,fees


def test_two_real_synthetic_csv_chains_share_one_virtual_FO_cash_book(tmp_path):
    nifty,bank,research,pulse,local,gate=integrated(tmp_path)
    assert nifty["71"].aligned_observation_count==2
    assert bank["71"].aligned_observation_count==2
    assert len(nifty["74"].outcomes)==4 and len(bank["74"].outcomes)==4
    assert research.local_research_fence_passed
    a,price,fees=_reserve(gate,nifty,pulse,"real-nifty-qa")
    b,_,_=_reserve(gate,bank,pulse,"real-bank-qa")
    assert a.event_revision==1 and b.event_revision==2
    audit=inspect_stage83_fo_account_reconciliation(local,research)
    assert audit.local_single_book_reconciliation_consistent
    assert audit.local_budget_screen_passed
    assert audit.simulated_reserved_cents==(
        nifty["75"].long_option_entry_debit_cents+
        bank["75"].long_option_entry_debit_cents
    )
    assert len(audit.markets)==2
    assert audit.broker_orders_transmitted==0
    qty=nifty["contract"].lot_size
    filled=gate.record_synthetic_fill(
        request_id="real-nifty-qa",fill_id="qa-full-fill",
        quantity=qty,price_cents=price,fee_cents=fees,telemetry=pulse,
    )
    assert filled.order_state=="FILLED_SYNTHETIC"
    after=inspect_stage83_fo_account_reconciliation(local,research)
    assert after.local_single_book_reconciliation_consistent
    assert after.simulated_reserved_cents==bank["75"].long_option_entry_debit_cents
    assert after.simulated_committed_cents<=research.total_hypothetical_debit_cents
    assert not after.global_single_atomic_capital_authority
    assert not after.paper_order_authorized and not after.live_trading_enabled


def test_kill_switch_after_two_reserves_blocks_even_healthy_caller_pulse(tmp_path):
    nifty,bank,research,pulse,local,gate=integrated(tmp_path)
    _,price,fees=_reserve(gate,nifty,pulse,"risk-nifty")
    _reserve(gate,bank,pulse,"risk-bank")
    risk=local.set_local_synthetic_kill_switch(active=True,operation_id="kill")
    assert risk.kill_switch_active
    with pytest.raises(Stage77SyntheticGatewayBlocked,match="simulated fill failed"):
        gate.record_synthetic_fill(
            request_id="risk-nifty",fill_id="blocked-fill",
            quantity=nifty["contract"].lot_size,
            price_cents=price,fee_cents=fees,telemetry=pulse,
        )
    stopped=inspect_stage83_fo_account_reconciliation(local,research)
    assert stopped.local_single_book_reconciliation_consistent
    assert not stopped.local_budget_screen_passed
    gate.cancel_synthetic_remaining(request_id="risk-nifty",cancel_id="cancel-nifty")
    gate.cancel_synthetic_remaining(request_id="risk-bank",cancel_id="cancel-bank")
    assert local.inspect().open_reserved_cents==0
    assert local.snapshot_local_synthetic_portfolio().kill_switch_active
    assert local.inspect().revision==4  # two reserve + two cancel


def test_stage76_rejects_forged_stage75_evidence_before_sqlite(tmp_path):
    nifty,bank,research,pulse,local,_=integrated(tmp_path)
    false_packet=replace(bank["75"],paper_order_authorized=True)
    with pytest.raises(Stage76RiskBlocked,match="authority"):
        inspect_stage76_fo_portfolio_risk(
            packets=(nifty["75"],false_packet),
            policy=Stage76FOResearchPolicy(),telemetry=pulse,
        )
    assert local.inspect().revision==0


def test_stage83_detects_book_corruption_after_real_module_reservation(tmp_path):
    nifty,bank,research,pulse,local,gate=integrated(tmp_path)
    _reserve(gate,nifty,pulse,"tamper")
    with sqlite3.connect(tmp_path/"combined.sqlite") as conn:
        conn.execute("UPDATE execution_head SET cash_cents=cash_cents-1")
    with pytest.raises(Stage83LedgerMismatch,match="replay"):
        inspect_stage83_fo_account_reconciliation(local,research)


def test_differing_capital_policy_blocks_multi_chain_admission(tmp_path):
    nifty,bank,research,pulse,local,gate=integrated(tmp_path)
    mismatched=replace(bank["75"],virtual_capital_cents=CAP-1)
    with pytest.raises(Stage76RiskBlocked,match="capital snapshots"):
        inspect_stage76_fo_portfolio_risk(
            packets=(nifty["75"],mismatched),
            policy=Stage76FOResearchPolicy(),telemetry=pulse,
        )
    assert local.inspect().revision==0


def test_combined_FO_data_and_cash_stay_research_only(tmp_path):
    nifty,bank,research,pulse,local,gate=integrated(tmp_path)
    report=inspect_stage83_fo_account_reconciliation(local,research)
    for chain in (nifty,bank):
        assert chain["75"].live_trading_enabled is False
        assert chain["76"].broker_orders_transmitted==0
    assert report.global_single_atomic_capital_authority is False
    assert report.authenticated_owner_and_risk_telemetry is False
    assert report.paper_order_authorized is False
    assert report.strategy_promotion_authorized is False
    assert report.live_trading_enabled is False
    assert report.broker_orders_transmitted==0
    assert report.verdict.endswith("NO_GO")

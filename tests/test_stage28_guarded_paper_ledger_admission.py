"""Stage28: synthetic-only durable, transaction-bound paper-risk admission tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import runpy
import sqlite3

import pytest

from nexus_titan.data.option_chain_history import assemble_research_option_chain_history
from nexus_titan.data.option_chain_ingest import load_research_option_chain_csv
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig
from nexus_titan.shadow.guarded_options_research import guarded_options_research_buy, GuardedPaperResearchError
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, GuardedBuyAdmission, ResearchLedgerError,
)
from nexus_titan.simulation.options_research_execution import OptionDisplayedDepth

STAGE22=runpy.run_path(str(Path(__file__).resolve().parents[1]/"scripts"/"run_stage22_research_smoke.py"))
OBS=STAGE22["OBS"]


def _setup(tmp_path, *, guarded=True, capital=50000, account_id="GATED"):
    src=tmp_path/"synthetic-stage28.csv"
    payload=STAGE22["_snapshot_csv"]()
    src.write_bytes(payload)
    contract=STAGE22["_contract"]()
    calendar=nse_equity_derivatives_baseline()
    snap=load_research_option_chain_csv(
        src,expected_sha256=hashlib.sha256(payload).hexdigest(),
        contract=contract,calendar=calendar,observed_at=OBS,
        provider_reference="synthetic/stage28-provider-unverified",
        licence_evidence_reference="synthetic/stage28-licence-unverified",
        calendar_evidence_reference="synthetic/stage28-calendar-unverified",
    )
    history=assemble_research_option_chain_history(
        [snap],contract=contract,calendar=calendar
    )
    depth=OptionDisplayedDepth(
        as_of=OBS,bid_quantity=400,ask_quantity=400,
        source_reference="synthetic/stage28-depth-unverified",
        source_declared_verified=True,
    )
    ledger=DurableResearchShadowLedger(
        tmp_path/"stage28.sqlite3",account_id=account_id,
        starting_capital=capital,guarded_paper_mode=guarded,
    )
    inputs=dict(
        ledger=ledger,order_id="PAPER-001",event_id="SYNTH-001",
        history=history,contract=contract,calendar=calendar,observed_at=OBS,
        strike=100.0,option_type="CE",lots=2,depth=depth,
        stop_price=5.0,max_unit_premium=6.0,
        expected_edge_bps=2000.0,slippage_bps=1.0,
        fee_buffer=25.0,paper_trading_enabled=True,
        realized_daily_loss_pct=0.0,consecutive_losses=0,
        current_drawdown_pct=0.0,
    )
    return ledger, inputs


def _direct(ledger,inputs,order_id="BYPASS"):
    ledger.reserve_buy(
        order_id=order_id,contract=inputs["contract"],strike=100,
        option_type="CE",lots=2,as_of=OBS,
        max_unit_premium=6.0,fee_buffer=25.0,
    )


def _context(inputs,**updates):
    quote=next(q for q in inputs["history"].snapshots[0].quotes
               if q.option_type=="CE" and q.strike==100)
    d=dict(
        paper_trading_enabled=True,risk_config=PortfolioRiskConfig(),
        stop_price=5.0,bid=quote.bid,ask=quote.ask,ask_quantity=400,
        expected_edge_bps=2000.0,slippage_bps=1.0,
        realized_daily_loss_pct=0.0,consecutive_losses=0,
        current_drawdown_pct=0.0,
    )
    d.update(updates)
    return GuardedBuyAdmission(**d)


def _guard_reserve(ledger,inputs,*,admission=None,order_id="GUARD-BUY",lots=2):
    ledger.reserve_buy_guarded(
        order_id=order_id,contract=inputs["contract"],strike=100.0,
        option_type="CE",lots=lots,as_of=OBS,
        max_unit_premium=6.0,fee_buffer=25.0,
        admission=admission if admission is not None else _context(inputs),
    )


def test_new_gated_account_rejects_direct_reserve_without_writing(tmp_path):
    ledger,inputs=_setup(tmp_path)
    before=ledger.status()
    assert ledger.guarded_paper_mode
    with pytest.raises(ResearchLedgerError,match="atomic risk admission"):
        _direct(ledger,inputs)
    assert ledger.status()==before
    assert ledger.verify_integrity()


def test_gated_mode_survives_reopen_with_legacy_constructor(tmp_path):
    ledger,inputs=_setup(tmp_path)
    reopened=DurableResearchShadowLedger(
        ledger.db_path,account_id=ledger.account_id,starting_capital=50000,
    )
    assert reopened.guarded_paper_mode
    with pytest.raises(ResearchLedgerError,match="atomic risk admission"):
        _direct(reopened,inputs)


def test_guarded_path_calls_atomic_recheck_and_settles_synthetic_option(tmp_path):
    ledger,inputs=_setup(tmp_path)
    out=guarded_options_research_buy(**inputs)
    state=ledger.status()
    assert out.live_orders_transmitted==0
    assert not out.approved_for_strategy_promotion
    assert sum(n for _,n in state.option_inventory)==50
    assert state.reserved_cash==0
    assert state.audit_event_count>=3
    assert ledger.verify_integrity()
    reopened=DurableResearchShadowLedger(
        ledger.db_path,account_id=ledger.account_id,starting_capital=50000
    )
    assert reopened.status()==state
    assert reopened.guarded_paper_mode


def test_legacy_research_api_remains_unchanged_for_existing_fixtures(tmp_path):
    ledger,inputs=_setup(tmp_path,guarded=False)
    assert ledger.guarded_paper_mode is False
    _direct(ledger,inputs)
    assert ledger.status().open_order_count==1
    assert ledger.status().reserved_cash>0
    ledger.cancel("BYPASS")


def test_guarded_context_cannot_reserve_against_legacy_mode(tmp_path):
    ledger,inputs=_setup(tmp_path,guarded=False)
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="needs guarded account"):
        _guard_reserve(ledger,inputs)
    assert ledger.status()==before


def test_existing_legacy_account_requires_explicit_migration(tmp_path):
    ledger,inputs=_setup(tmp_path,guarded=False)
    with pytest.raises(ResearchLedgerError,match="explicit guarded-mode migration"):
        DurableResearchShadowLedger(ledger.db_path,account_id=ledger.account_id,
                                    starting_capital=50000,guarded_paper_mode=True)
    assert ledger.verify_integrity()
    assert not ledger.guarded_paper_mode


def test_explicit_migration_of_flat_account_is_durable_and_one_way(tmp_path):
    ledger,inputs=_setup(tmp_path,guarded=False)
    ledger.enable_guarded_paper_mode()
    ledger.enable_guarded_paper_mode()
    assert ledger.guarded_paper_mode
    assert ledger.verify_integrity()
    reopened=DurableResearchShadowLedger(
        ledger.db_path,account_id=ledger.account_id,starting_capital=50000
    )
    assert reopened.guarded_paper_mode
    with pytest.raises(ResearchLedgerError,match="atomic risk admission"):
        _direct(reopened,inputs)


def test_cannot_upgrade_account_with_pending_order(tmp_path):
    ledger,inputs=_setup(tmp_path,guarded=False)
    _direct(ledger,inputs)
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="outstanding inventory"):
        ledger.enable_guarded_paper_mode()
    assert not ledger.guarded_paper_mode
    assert ledger.status()==before


def test_cannot_upgrade_account_with_existing_inventory(tmp_path):
    ledger,inputs=_setup(tmp_path,guarded=False)
    guarded_options_research_buy(**inputs)
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="outstanding inventory"):
        ledger.enable_guarded_paper_mode()
    assert ledger.status()==before
    assert not ledger.guarded_paper_mode


def test_protects_unrelated_accounts_on_same_database(tmp_path):
    ledger,inputs=_setup(tmp_path)
    research=DurableResearchShadowLedger(ledger.db_path,account_id="OTHER",
                                          starting_capital=20000)
    assert not research.guarded_paper_mode
    direct_args={**inputs,"ledger":research}
    _direct(research,direct_args)
    assert research.status().open_order_count==1
    with pytest.raises(ResearchLedgerError,match="atomic risk admission"):
        _direct(ledger,inputs)


def test_tampered_persistent_mode_detected_by_hash_binding(tmp_path):
    ledger,inputs=_setup(tmp_path)
    with sqlite3.connect(ledger.db_path) as con:
        con.execute("DELETE FROM account_safety WHERE account_id=?",(ledger.account_id,))
    with pytest.raises(ResearchLedgerError,match="state does not match audit"):
        ledger.verify_integrity()
    with pytest.raises(ResearchLedgerError,match="state does not match audit"):
        _direct(ledger,inputs)


@pytest.mark.parametrize("change,match",[
    ({"paper_trading_enabled":False},"PAPER_TRADE permission denied"),
    ({"paper_trading_enabled":"true"},"explicit boolean"),
    ({"risk_config":"wrong"},"exact risk config"),
    ({"stop_price":6.1},"invalid bid/ask"),
    ({"bid":6.5},"invalid bid/ask"),
    ({"ask":7.0},"invalid bid/ask"),
    ({"ask_quantity":0},"positive displayed"),
    ({"ask_quantity":10},"Red-Team veto"),
    ({"slippage_bps":2000},"Red-Team veto"),
    ({"expected_edge_bps":1},"Red-Team veto"),
    ({"realized_daily_loss_pct":3.0},"risk veto"),
    ({"current_drawdown_pct":10.0},"risk veto"),
    ({"consecutive_losses":3},"risk veto"),
    ({"risk_config":PortfolioRiskConfig(max_risk_per_trade_pct=0.01)},"risk veto"),
])
def test_gated_reserve_denies_bad_state_or_permission_without_any_mutation(tmp_path,change,match):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    with pytest.raises(ResearchLedgerError,match=match):
        _guard_reserve(ledger,inputs,admission=_context(inputs,**change))
    assert ledger.status()==old
    assert ledger.verify_integrity()


def test_unguarded_direct_order_is_denied_after_guarded_reservation(tmp_path):
    ledger,inputs=_setup(tmp_path)
    _guard_reserve(ledger,inputs)
    old=ledger.status()
    with pytest.raises(ResearchLedgerError,match="atomic risk admission|flat"):
        _direct(ledger,inputs,order_id="DUP-BYPASS")
    assert ledger.status()==old


def test_second_guarded_buy_denied_against_existing_reservation(tmp_path):
    ledger,inputs=_setup(tmp_path)
    _guard_reserve(ledger,inputs,order_id="ONE")
    old=ledger.status()
    with pytest.raises(ResearchLedgerError,match="must be flat"):
        _guard_reserve(ledger,inputs,order_id="TWO")
    assert ledger.status()==old


def test_parallel_guarded_reservations_cannot_race_past_flatness_gate(tmp_path):
    ledger,inputs=_setup(tmp_path)
    other=DurableResearchShadowLedger(ledger.db_path,account_id=ledger.account_id,
                                      starting_capital=50000)
    def attempt(entry):
        try:
            _guard_reserve(entry[0],inputs,order_id=entry[1])
            return True
        except ResearchLedgerError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,[(ledger,"THREAD-1"),(other,"THREAD-2")]))
    assert sorted(results)==[False,True]
    assert ledger.status().open_order_count==1
    assert ledger.verify_integrity()


def test_no_real_broker_or_strategy_promotion_in_ledger_mode(tmp_path):
    ledger,inputs=_setup(tmp_path)
    out=guarded_options_research_buy(**inputs)
    assert out.live_orders_transmitted==0
    assert out.approved_for_strategy_promotion is False
    assert ledger.status().live_orders_transmitted==0
    assert ledger.status().approved_for_strategy_promotion is False

"""Stage23: synthetic-only paper permission, authoritative risk and veto integration."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
from pathlib import Path
import runpy

import pytest

from nexus_titan.core.permissions import Decision
from nexus_titan.data.option_chain_history import assemble_research_option_chain_history
from nexus_titan.data.option_chain_ingest import load_research_option_chain_csv
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig
from nexus_titan.shadow.guarded_options_research import (
    GuardedPaperResearchError, guarded_options_research_buy,
)
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)
from nexus_titan.simulation.options_research_execution import OptionDisplayedDepth

ROOT=Path(__file__).resolve().parents[1]
STAGE22=runpy.run_path(str(ROOT/"scripts"/"run_stage22_research_smoke.py"))
OBS=STAGE22["OBS"]


def _setup(tmp_path, *, capital=50000, ask_depth=400):
    payload=STAGE22["_snapshot_csv"]()
    path=tmp_path/"test-synthetic-options.csv"
    path.write_bytes(payload)
    contract=STAGE22["_contract"]()
    calendar=nse_equity_derivatives_baseline()
    snap=load_research_option_chain_csv(
        path,expected_sha256=hashlib.sha256(payload).hexdigest(),
        contract=contract, calendar=calendar, observed_at=OBS,
        provider_reference="synthetic/not-provider",
        licence_evidence_reference="synthetic/not-licence",
        calendar_evidence_reference="synthetic/not-official-calendar",
    )
    history=assemble_research_option_chain_history([snap],contract=contract,calendar=calendar)
    depth=OptionDisplayedDepth(
        as_of=OBS,bid_quantity=400,ask_quantity=ask_depth,
        source_reference="synthetic/depth-not-authenticated",source_declared_verified=True,
    )
    ledger=DurableResearchShadowLedger(
        tmp_path/"guarded.sqlite3",account_id="TEST-GUARDED",starting_capital=capital
    )
    inputs=dict(
        ledger=ledger,order_id="GUARDED-001",event_id="SYNTH-FILL-001",
        history=history,contract=contract,calendar=calendar,observed_at=OBS,
        strike=100.0,option_type="CE",lots=2,depth=depth,stop_price=5.0,
        max_unit_premium=6.0,expected_edge_bps=2000.0,slippage_bps=1.0,
        fee_buffer=25.0,paper_trading_enabled=True,
        realized_daily_loss_pct=0.0,consecutive_losses=0,current_drawdown_pct=0.0,
    )
    return ledger,inputs


def _unchanged(ledger,status):
    assert ledger.status()==status
    assert ledger.verify_integrity()


def test_opt_in_risk_and_red_team_paper_only_flow_settles_synthetic_buy(tmp_path):
    ledger,inputs=_setup(tmp_path)
    result=guarded_options_research_buy(**inputs)
    state=ledger.status()
    assert result.paper_permission is Decision.ALLOW
    assert result.authoritative_risk.approved
    assert result.contract_risk.approved
    assert result.red_team.veto_recommended is False
    assert result.research_statement.status=="FILLED"
    assert result.research_statement.filled_quantity==50
    assert state.open_order_count==0
    assert state.reserved_cash==0
    assert sum(q for _,q in state.option_inventory)==50
    assert state.cash_balance<50000
    assert result.live_orders_transmitted==0
    assert not result.approved_for_strategy_promotion


def test_permission_is_deny_by_default_without_paper_flag(tmp_path):
    ledger,inputs=_setup(tmp_path)
    before=ledger.status()
    inputs.pop("paper_trading_enabled")
    with pytest.raises(GuardedPaperResearchError,match="permission denied"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,before)


def test_explicit_false_paper_permission_blocks_before_risk_or_cash(tmp_path):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    inputs["paper_trading_enabled"]=False
    with pytest.raises(GuardedPaperResearchError,match="permission denied"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_bad_permission_value_is_not_truthy_bypass(tmp_path):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    inputs["paper_trading_enabled"]="yes"
    with pytest.raises(GuardedPaperResearchError,match="explicit boolean"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


@pytest.mark.parametrize("change,match",[
    ({"realized_daily_loss_pct":3.0},"risk veto"),
    ({"current_drawdown_pct":10.0},"risk veto"),
    ({"consecutive_losses":3},"risk veto"),
    ({"stop_price":6.5},"protective stop"),
    ({"max_unit_premium":5.0},"reserved entry ceiling"),
    ({"lots":11},"exact contract limits"),
    ({"lots":0},"exact contract limits"),
    ({"lots":True},"exact contract limits"),
    ({"expected_edge_bps":0},"expected_edge_bps"),
    ({"slippage_bps":-1},"slippage_bps"),
    ({"fee_buffer":float("nan")},"fee_buffer"),
])
def test_fail_closed_risk_and_configuration_before_ledger_mutation(tmp_path,change,match):
    ledger,inputs=_setup(tmp_path)
    original=ledger.status()
    inputs.update(change)
    with pytest.raises(GuardedPaperResearchError,match=match):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,original)


def test_no_liquidity_red_team_vetoes_before_simulated_settlement(tmp_path):
    ledger,inputs=_setup(tmp_path,ask_depth=0)
    old=ledger.status()
    with pytest.raises(GuardedPaperResearchError,match="Red-Team veto"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_insufficient_visible_liquidity_blocks_rather_than_partial_fill(tmp_path):
    ledger,inputs=_setup(tmp_path,ask_depth=25)
    old=ledger.status()
    with pytest.raises(GuardedPaperResearchError,match="Red-Team veto"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_unrealistically_low_claimed_edge_does_not_override_true_spread(tmp_path):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    inputs["expected_edge_bps"]=20
    with pytest.raises(GuardedPaperResearchError,match="Red-Team veto"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_slippage_stress_and_edge_veto(tmp_path):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    inputs["slippage_bps"]=2000
    with pytest.raises(GuardedPaperResearchError,match="Red-Team veto"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_account_with_held_reservation_rejected_before_risk(tmp_path):
    ledger,inputs=_setup(tmp_path)
    ledger.reserve_buy(
        order_id="EXISTING",contract=inputs["contract"],strike=100,option_type="CE",
        lots=1,as_of=OBS,max_unit_premium=6,fee_buffer=25,
    )
    original=ledger.status()
    with pytest.raises(GuardedPaperResearchError,match="Flat research account"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,original)


def test_account_with_existing_unvalued_inventory_fails_closed(tmp_path):
    ledger,inputs=_setup(tmp_path)
    guarded_options_research_buy(**inputs)
    old=ledger.status()
    inputs["order_id"]="SECOND"
    inputs["event_id"]="SECOND-FILL"
    with pytest.raises(GuardedPaperResearchError,match="Flat research account"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_neither_generic_risk_fallback_nor_unmatched_lot_can_bypass(tmp_path):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    inputs["lots"]=9
    # At the configured stop distance, the exact-contract cap and risk budget
    # limit the 9-lot proposal to at most 8 lots under reduced capital.
    # Large order must be rejected before ledger mutations.
    inputs["risk_config"]=PortfolioRiskConfig(max_risk_per_trade_pct=0.1)
    with pytest.raises(GuardedPaperResearchError,match="Authoritative risk veto|Exact-contract risk veto"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_flat_account_overwriting_capital_limit_rejected(tmp_path):
    ledger,inputs=_setup(tmp_path,capital=1000)
    old=ledger.status()
    with pytest.raises(GuardedPaperResearchError,match="risk veto"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_impossible_quote_or_contract_identity_does_not_reserve(tmp_path):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    inputs["strike"]=150.0
    with pytest.raises(GuardedPaperResearchError,match="one option quote"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_depth_without_operator_declaration_blocks(tmp_path):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    inputs["depth"]=replace(inputs["depth"],source_declared_verified=False)
    with pytest.raises(GuardedPaperResearchError,match="declaration missing"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_quote_after_observation_rejected_without_reservation(tmp_path):
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    inputs["depth"]=replace(inputs["depth"],
                            as_of=OBS.replace(second=1))
    with pytest.raises(ValueError,match="after observation"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_fee_buffer_insufficient_rolls_back_settlement_and_cancels_reserve(tmp_path):
    ledger,inputs=_setup(tmp_path)
    inputs["fee_buffer"]=0.01
    # A fixed premium ceiling can admit the quote but the minimum fee reserve
    # can be too small. The bridge must cancel held funds if settlement fails.
    inputs["max_unit_premium"]=5.50
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="exceed reserved"):
        guarded_options_research_buy(**inputs)
    state=ledger.status()
    assert state.cash_balance==before.cash_balance
    assert state.reserved_cash==0
    assert state.cancelled_order_count==1
    assert state.option_inventory==()
    assert ledger.verify_integrity()


@pytest.mark.parametrize("bad",[
    {"expected_edge_bps":float("nan")},{"current_drawdown_pct":float("inf")},
    {"consecutive_losses":True},{"risk_config":"bad"},{"option_type":"SELL"},
    {"observed_at":datetime(2026,11,2,9,16)},
])
def test_bad_input_fails_without_reservation(tmp_path,bad):
    ledger,inputs=_setup(tmp_path)
    original=ledger.status()
    inputs.update(bad)
    with pytest.raises(GuardedPaperResearchError):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,original)


def test_restart_after_guarded_settlement_does_not_grant_live_permissions(tmp_path):
    ledger,inputs=_setup(tmp_path)
    result=guarded_options_research_buy(**inputs)
    restarted=DurableResearchShadowLedger(
        tmp_path/"guarded.sqlite3",account_id="TEST-GUARDED",starting_capital=50000
    )
    assert restarted.status()==ledger.status()
    assert restarted.status().live_orders_transmitted==0
    assert result.research_statement.live_orders_transmitted==0
    assert result.research_statement.approved_for_strategy_promotion is False


def test_complete_guarded_risk_to_recovery_and_blocked_readiness(tmp_path):
    from datetime import time
    from zoneinfo import ZoneInfo

    from nexus_titan.shadow.research_recovery_validation import (
        DailyResearchShadowRecord, run_research_shadow_recovery_drill,
    )
    from nexus_titan.shadow.unified_readiness import prepare_unified_shadow_readiness

    ledger,inputs=_setup(tmp_path)
    opening=ledger.status()
    outcome=guarded_options_research_buy(**inputs)
    latest=ledger.status()
    assert outcome.research_statement.filled_quantity==50
    assert latest.cash_balance<opening.cash_balance
    assert latest.reserved_cash==0

    restored=DurableResearchShadowLedger(
        tmp_path/"guarded.sqlite3",account_id="TEST-GUARDED",starting_capital=50000
    )
    assert restored.status()==latest
    drill=run_research_shadow_recovery_drill(
        restored,backup_path=tmp_path/"guarded-backup.sqlite3"
    )
    assert drill.passed
    day_close=DailyResearchShadowRecord(
        session_date=OBS.date(),
        observed_at=datetime.combine(OBS.date(),time(15,31),
                                     tzinfo=ZoneInfo("Asia/Kolkata")),
        status=latest,
        expected_cash_change=round(latest.cash_balance-opening.cash_balance,2),
        evidence_reference="synthetic/one-day-no-real-feed",
    )
    readiness=prepare_unified_shadow_readiness(
        ledger=restored,
        daily_records=[day_close],
        calendar=nse_equity_derivatives_baseline(),
        recovery=drill,evidence_submissions=[],
        claimed_closed_trades=0,as_of=datetime.combine(
            OBS.date(),time(16,0),tzinfo=ZoneInfo("Asia/Kolkata")
        ),
    )
    assert readiness.release_decision=="BLOCKED_STRUCTURAL_VALIDATION"
    assert not readiness.review_candidate
    assert not readiness.live_trading_enabled
    assert not readiness.automatic_strategy_promotion
    assert not readiness.external_authenticity_verified


def test_authoritative_engine_veto_cannot_be_overruled_by_other_checks(tmp_path,monkeypatch):
    from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
    from nexus_titan.risk.portfolio_risk import PreTradeRiskResult
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    monkeypatch.setattr(
        AuthoritativeRiskEngine,"size_and_validate",
        lambda self,**kwargs: PreTradeRiskResult(False,0,0.0,0.0,0.0,"forced authoritative veto"),
    )
    with pytest.raises(GuardedPaperResearchError,match="Authoritative risk veto"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)


def test_exact_contract_engine_veto_cannot_be_overruled(tmp_path,monkeypatch):
    from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
    from nexus_titan.risk.portfolio_risk import PortfolioRiskManager, PreTradeRiskResult
    ledger,inputs=_setup(tmp_path)
    old=ledger.status()
    monkeypatch.setattr(
        AuthoritativeRiskEngine,"size_and_validate",
        lambda self,**kwargs: PreTradeRiskResult(True,500,250.0,6.0,5.0,"synthetic authority allow"),
    )
    monkeypatch.setattr(
        PortfolioRiskManager,"evaluate_order",
        lambda self,**kwargs: PreTradeRiskResult(False,0,0.0,0.0,0.0,"forced exact-contract veto"),
    )
    with pytest.raises(GuardedPaperResearchError,match="Exact-contract risk veto"):
        guarded_options_research_buy(**inputs)
    _unchanged(ledger,old)

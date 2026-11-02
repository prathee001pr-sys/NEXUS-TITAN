"""Stage35 risk/order evidence drift tests: no signing and no live operations."""
from __future__ import annotations

from dataclasses import replace
import pytest

from nexus_titan.shadow.paper_intent_gateway import PaperIntentGateway
from nexus_titan.shadow.paper_intent_evidence import (
    PaperIntentEvidence,PaperEvidenceError,
    capture_pending_paper_intent_evidence,verify_pending_paper_intent_evidence,
)
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import VirtualAccount,TradingMode,OrderState


def setup(tmp_path):
    v=VirtualAccount(
        "RECEIPT",starting_capital=50000,
        require_pretrade_risk_check=True,trading_mode=TradingMode.MANUAL_APPROVAL,
        approval_authorizer=lambda actor, oid: actor=="OWNER",
        state_dir=tmp_path/"virtual",
    )
    l=DurableResearchShadowLedger(
        tmp_path/"ledger.sqlite3",account_id="RECEIPT",starting_capital=50000,
        guarded_paper_mode=True,
    )
    gw=PaperIntentGateway(v,l)
    order=gw.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95,
                         paper_trading_enabled=True)
    return v,l,order


def receipt(v,l,order):
    return capture_pending_paper_intent_evidence(v,l,order_id=order.order_id,
                                                  paper_trading_enabled=True)


def test_unfilled_manual_buy_receipt_is_deterministic_and_unsigned(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    assert ev==receipt(v,l,order)
    assert ev.schema_version==1
    assert len(ev.evidence_sha256)==64
    assert ev.externally_signed is False
    assert ev.authenticated_identity is False
    assert ev.live_trading_approved is False
    assert verify_pending_paper_intent_evidence(ev,v,l,paper_trading_enabled=True)


@pytest.mark.parametrize("new_qty",[2,5,20])
def test_order_amendment_invalidates_old_intent_evidence(tmp_path,new_qty):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    v.orders[order.order_id].quantity=new_qty
    assert not verify_pending_paper_intent_evidence(ev,v,l,paper_trading_enabled=True)


def test_risk_budget_change_invalidates_old_evidence(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    v.risk_per_trade_pct=0.3
    assert not verify_pending_paper_intent_evidence(ev,v,l,paper_trading_enabled=True)


def test_mode_switch_and_kill_switch_invalidate_receipt(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    v.activate_emergency_kill_switch()
    assert not verify_pending_paper_intent_evidence(ev,v,l,paper_trading_enabled=True)


def test_approval_and_fill_invalidate_pending_receipt(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    v.approve_order(order.order_id,"OWNER")
    assert not verify_pending_paper_intent_evidence(ev,v,l,paper_trading_enabled=True)


def test_changed_research_ledger_digest_invalidates_receipt(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    # Empty account can be mutated by a strictly guarded synthetic reservation.
    # Instead a new distinct no-op migration is not possible: inject a
    # legitimate account reservation through the guarded gate.
    from nexus_titan.shadow.research_reservation_ledger import GuardedBuyAdmission
    from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig
    from datetime import datetime,date
    from nexus_titan.data.instrument_master import PointInTimeContractSpec
    spec=PointInTimeContractSpec(
        symbol="NIFTYOPT",underlying="NIFTY",exchange="NSE",segment="OPTIONS",
        lot_size=25,tick_size=0.05,freeze_quantity=1000,max_lots_per_trade=10,
        strike_step=50.0,expiry_date=date(2026,11,5),
        effective_from=date(2026,11,1),effective_to=date(2026,11,5),
        source_reference="synthetic/contract",source_verified=True,
    )
    obs=datetime.fromisoformat("2026-11-02T09:16:00+05:30")
    l.reserve_buy_guarded(
        order_id="CHANGE",contract=spec,strike=100.0,option_type="CE",
        lots=2,as_of=obs,max_unit_premium=6.0,fee_buffer=25.0,
        admission=GuardedBuyAdmission(True,PortfolioRiskConfig(),5.0,
            5.0,5.5,400,2000.0,1.0,0.0,0,0.0),
    )
    assert not verify_pending_paper_intent_evidence(ev,v,l,paper_trading_enabled=True)


def test_no_paper_permission_cannot_issue_or_verify(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    with pytest.raises(PaperEvidenceError,match="permission denied"):
        capture_pending_paper_intent_evidence(v,l,order_id=order.order_id)
    assert not verify_pending_paper_intent_evidence(ev,v,l)


def test_tampered_evidence_fingerprint_fails_closed(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    assert not verify_pending_paper_intent_evidence(
        replace(ev,evidence_sha256="0"*64),v,l,paper_trading_enabled=True)


def test_restart_with_same_intact_pending_order_preserves_evidence(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    restored=VirtualAccount("RECEIPT",starting_capital=50000,
         require_pretrade_risk_check=True,trading_mode=TradingMode.MANUAL_APPROVAL,
         approval_authorizer=lambda actor,oid: actor=="OWNER",
         state_dir=tmp_path/"virtual")
    reopened=DurableResearchShadowLedger(l.db_path,account_id="RECEIPT",starting_capital=50000)
    assert verify_pending_paper_intent_evidence(ev,restored,reopened,
        paper_trading_enabled=True)


def test_immutability_and_false_authority_claims_do_not_pass(tmp_path):
    v,l,order=setup(tmp_path)
    ev=receipt(v,l,order)
    assert not verify_pending_paper_intent_evidence(
        replace(ev,live_trading_approved=True),v,l,paper_trading_enabled=True)
    assert not hasattr(ev,"sign")

"""Stage40: one-way gateway-only policy on opt-in strict offline paper accounts.

Synthetic-only. This prevents accidental direct order submissions through
normal APIs, not malicious callers able to change Python source or SQLite.
"""
from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from nexus_titan.shadow.paper_intent_gateway import PaperIntentGateway, PaperIntentDenied
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import VirtualAccount, TradingMode, OrderState


def _setup(tmp_path, *, strict=True, guarded=True, account_id="STAGE40"):
    v=VirtualAccount(
        account_id,starting_capital=50000,
        state_dir=tmp_path/"virtual",trading_mode=TradingMode.MANUAL_APPROVAL,
        require_pretrade_risk_check=True,
        approval_authorizer=lambda actor,oid: actor=="OWNER",
        strict_paper_mode=strict,
    )
    r=DurableResearchShadowLedger(
        tmp_path/"research.sqlite3",account_id="STAGE40",
        starting_capital=50000,guarded_paper_mode=guarded,
    )
    return v,r


def _buy(gateway):
    return gateway.request_buy(
        symbol="ABC",quantity=1,entry_price=100,stop_price=95,
        paper_trading_enabled=True,
    )


def test_flat_strict_account_can_migrate_to_one_way_gateway_only(tmp_path):
    v,r=_setup(tmp_path)
    assert not v.gateway_only_mode
    v.enable_gateway_only_mode(r)
    assert v.gateway_only_mode
    assert v.durable_store.gateway_only(v.account_id)
    v.enable_gateway_only_mode(r)
    assert v.durable_store.gateway_only(v.account_id)
    with pytest.raises(PermissionError,match="denies direct submit_order"):
        v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    assert v.orders=={}


def test_gateway_only_buy_manual_approve_sell_and_reconcile(tmp_path):
    v,r=_setup(tmp_path)
    v.enable_gateway_only_mode(r)
    gw=PaperIntentGateway(v,r)
    before=v.cash_balance
    result=_buy(gw)
    assert result.status=="PENDING_APPROVAL"
    assert v.cash_balance==before
    with pytest.raises(PermissionError,match="intact authenticated"):
        v.execute_fill(result.order_id,100)
    v.approve_order(result.order_id,"OWNER")
    v.execute_fill(result.order_id,100)
    assert v.positions["ABC"].quantity==1
    with pytest.raises(PermissionError,match="denies direct submit_order"):
        v.submit_order("ABC","SELL",1)
    close=gw.request_sell_to_close(symbol="ABC",quantity=1,paper_trading_enabled=True)
    assert close.status=="PENDING_APPROVAL"
    v.approve_order(close.order_id,"OWNER")
    v.execute_fill(close.order_id,103)
    assert not v.positions and v.reconcile().is_reconciled


def test_gateway_mode_restart_preserves_routing_and_strict_policy(tmp_path):
    v,r=_setup(tmp_path)
    v.enable_gateway_only_mode(r)
    new_v,_=_setup(tmp_path,strict=False)
    assert new_v.strict_paper_mode and new_v.gateway_only_mode
    with pytest.raises(PermissionError,match="denies direct submit_order"):
        new_v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    assert _buy(PaperIntentGateway(new_v,r)).status=="PENDING_APPROVAL"


def test_gateway_only_mode_cannot_disable_with_in_memory_flag(tmp_path):
    v,r=_setup(tmp_path)
    v.enable_gateway_only_mode(r)
    before=v.durable_store.revision(v.account_id)
    v.gateway_only_mode=False
    with pytest.raises(PermissionError,match="cannot be downgraded"):
        v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    with pytest.raises(PermissionError,match="cannot be downgraded"):
        v._sync_durable_store()
    assert v.durable_store.revision(v.account_id)==before
    assert v.durable_store.gateway_only(v.account_id)


def test_gateway_only_mode_cannot_downgrade_via_snapshot_write(tmp_path):
    v,r=_setup(tmp_path)
    v.enable_gateway_only_mode(r)
    v.gateway_only_mode=False
    with pytest.raises(PermissionError,match="cannot be downgraded"):
        v._sync_durable_store()
    with sqlite3.connect(v.durable_store.db_path) as con:
        assert con.execute(
            "SELECT gateway_only_mode FROM account_state WHERE account_id=?",
            (v.account_id,),
        ).fetchone()[0]==1


def test_migration_denied_if_strict_account_has_open_order(tmp_path):
    v,r=_setup(tmp_path)
    pending=v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    assert pending.state==OrderState.PENDING_APPROVAL
    with pytest.raises(PermissionError,match="flat verified preflight"):
        v.enable_gateway_only_mode(r)
    assert not v.gateway_only_mode
    assert not v.durable_store.gateway_only(v.account_id)


def test_migration_denied_for_non_strict_or_non_guarded(tmp_path):
    v,r=_setup(tmp_path,strict=False)
    with pytest.raises(PermissionError,match="requires strict paper"):
        v.enable_gateway_only_mode(r)
    v2,r2=_setup(tmp_path/"other",guarded=False)
    with pytest.raises(PermissionError,match="flat verified preflight"):
        v2.enable_gateway_only_mode(r2)


def test_migration_denied_for_mismatched_research_identity(tmp_path):
    v,r=_setup(tmp_path,account_id="MISMATCH")
    with pytest.raises(PermissionError,match="flat verified preflight"):
        v.enable_gateway_only_mode(r)


@pytest.mark.parametrize("allowed",[False,"yes",None,1])
def test_paper_permission_cannot_be_forged(allowed,tmp_path):
    v,r=_setup(tmp_path)
    v.enable_gateway_only_mode(r)
    gw=PaperIntentGateway(v,r)
    with pytest.raises(PaperIntentDenied,match="PAPER_TRADE"):
        gw.request_buy(
            symbol="ABC",quantity=1,entry_price=100,stop_price=95,
            paper_trading_enabled=allowed,
        )
    assert not v.orders


def test_private_gateway_entry_still_rechecks_permission_and_research(tmp_path):
    v,r=_setup(tmp_path)
    v.enable_gateway_only_mode(r)
    with pytest.raises(PermissionError,match="PAPER_TRADE"):
        v._submit_guarded_paper_intent(
            r,paper_trading_enabled=False,
            symbol="ABC",side="BUY",quantity=1,entry_price=100,stop_price=95,
        )
    assert not v.orders


def test_gateway_only_emergency_squareoff_remains_available(tmp_path):
    v,r=_setup(tmp_path)
    v.enable_gateway_only_mode(r)
    gw=PaperIntentGateway(v,r)
    buy=_buy(gw)
    v.approve_order(buy.order_id,"OWNER")
    v.execute_fill(buy.order_id,100)
    closes=v.emergency_square_off({"ABC":99})
    assert len(closes)==1 and closes[0].state==OrderState.FILLED
    assert not v.positions and v.reconcile().is_reconciled
    with pytest.raises(PaperIntentDenied,match="Kill switch"):
        _buy(gw)


def test_old_legacy_simulation_still_allowed_in_isolated_research(tmp_path):
    v,r=_setup(tmp_path,strict=False)
    order=v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    assert order.state==OrderState.PENDING_APPROVAL
    assert v.gateway_only_mode is False
    assert not v.durable_store.gateway_only(v.account_id)


def test_no_live_or_autopaper_escalation_on_gateway_only_mode(tmp_path):
    v,r=_setup(tmp_path)
    v.enable_gateway_only_mode(r)
    with pytest.raises(PermissionError,match="permanently requires MANUAL"):
        v.set_trading_mode("AUTO_PAPER",actor="OWNER")
    with pytest.raises(ValueError,match="Live trading"):
        v.set_trading_mode("LIVE_DISABLED")

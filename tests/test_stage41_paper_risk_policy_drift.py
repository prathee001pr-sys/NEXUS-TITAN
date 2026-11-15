"""Stage41: policy-bound BUY approvals and fills on gateway-only paper accounts."""
from __future__ import annotations

from dataclasses import replace
import pytest

from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig
from nexus_titan.shadow.paper_intent_gateway import PaperIntentGateway
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import VirtualAccount,TradingMode,OrderState


def setup(tmp_path):
    def open_account():
        return VirtualAccount(
            "POLICY",starting_capital=50000,state_dir=tmp_path/"virtual",
            require_pretrade_risk_check=True,trading_mode=TradingMode.MANUAL_APPROVAL,
            approval_authorizer=lambda actor, oid: actor=="OWNER",
            strict_paper_mode=False,
        )
    # New strict account first, then use the default constructor on restart.
    v=VirtualAccount(
        "POLICY",starting_capital=50000,state_dir=tmp_path/"virtual",
        require_pretrade_risk_check=True,trading_mode=TradingMode.MANUAL_APPROVAL,
        approval_authorizer=lambda actor,oid: actor=="OWNER",
        strict_paper_mode=True,
    )
    r=DurableResearchShadowLedger(
        tmp_path/"research.sqlite3",account_id="POLICY",starting_capital=50000,
        guarded_paper_mode=True,
    )
    v.enable_gateway_only_mode(r)
    return v,r,open_account


def buy(v,r,qty=1):
    return PaperIntentGateway(v,r).request_buy(
        symbol="ABC",quantity=qty,entry_price=100,stop_price=95,
        paper_trading_enabled=True,
    )


def test_pending_buy_has_durable_risk_policy_fingerprint(tmp_path):
    v,r,_=setup(tmp_path)
    order=buy(v,r)
    record=v.orders[order.order_id]
    assert isinstance(record.risk_policy_fingerprint,str)
    assert len(record.risk_policy_fingerprint)==64
    assert record.state is OrderState.PENDING_APPROVAL
    v.approve_order(order.order_id,"OWNER")
    v.execute_fill(order.order_id,100)
    assert v.positions["ABC"].quantity==1 and v.reconcile().is_reconciled


def test_limit_change_after_intent_blocks_approval_and_fill(tmp_path):
    v,r,_=setup(tmp_path)
    order=buy(v,r)
    v.risk_per_trade_pct=0.1
    with pytest.raises(PermissionError,match="risk policy drift"):
        v.approve_order(order.order_id,"OWNER")
    assert v.orders[order.order_id].state is OrderState.PENDING_APPROVAL
    assert not v.positions
    v.risk_per_trade_pct=1.0
    v.approve_order(order.order_id,"OWNER")
    v.risk_per_trade_pct=0.2
    with pytest.raises(PermissionError,match="risk policy drift"):
        v.execute_fill(order.order_id,100)
    assert not v.positions and v.orders[order.order_id].filled_qty==0


def test_effective_engine_config_tamper_blocks_approval(tmp_path):
    v,r,_=setup(tmp_path)
    order=buy(v,r)
    v.risk_engine._portfolio_mgr.config=PortfolioRiskConfig(max_risk_per_trade_pct=0.1)
    with pytest.raises(PermissionError,match="risk policy drift"):
        v.approve_order(order.order_id,"OWNER")
    assert not v.positions


def test_account_topup_after_intent_invalidates_old_risk_plan(tmp_path):
    v,r,_=setup(tmp_path)
    order=buy(v,r)
    v.adjust_capital(500,"TOP_UP",user_confirmed=True)
    with pytest.raises(PermissionError,match="risk policy drift"):
        v.approve_order(order.order_id,"OWNER")
    assert v.cash_balance==50500
    assert not v.positions


def test_changing_order_fingerprint_cannot_authorize_old_manual_buy(tmp_path):
    v,r,_=setup(tmp_path)
    order=buy(v,r)
    v.orders[order.order_id].risk_policy_fingerprint="0"*64
    with pytest.raises(PermissionError,match="risk policy drift"):
        v.approve_order(order.order_id,"OWNER")


def test_missing_fingerprint_is_fail_closed_on_gateway_only_account(tmp_path):
    v,r,_=setup(tmp_path)
    order=buy(v,r)
    v.orders[order.order_id].risk_policy_fingerprint=None
    v.orders[order.order_id].state=OrderState.ACCEPTED
    with pytest.raises(PermissionError,match="risk policy drift"):
        v.execute_fill(order.order_id,100)


def test_restart_preserves_fingerprint_and_authorized_paper_flow(tmp_path):
    v,r,reopen=setup(tmp_path)
    order=buy(v,r)
    expected=v.orders[order.order_id].risk_policy_fingerprint
    other=reopen()
    assert other.gateway_only_mode and other.strict_paper_mode
    assert other.orders[order.order_id].risk_policy_fingerprint==expected
    other.approve_order(order.order_id,"OWNER")
    other.execute_fill(order.order_id,100)
    assert other.reconcile().is_reconciled


def test_partial_buy_fills_do_not_invalidate_stable_policy(tmp_path):
    v,r,_=setup(tmp_path)
    order=buy(v,r,qty=2)
    v.approve_order(order.order_id,"OWNER")
    v.execute_fill(order.order_id,100,fill_qty=1,idempotency_key="first")
    assert v.orders[order.order_id].state is OrderState.PARTIALLY_FILLED
    v.execute_fill(order.order_id,100,fill_qty=1,idempotency_key="second")
    assert v.orders[order.order_id].state is OrderState.FILLED
    assert v.positions["ABC"].quantity==2
    assert v.reconcile().is_reconciled


def test_approved_owned_sell_remains_risk_reducing_after_policy_change(tmp_path):
    v,r,_=setup(tmp_path)
    order=buy(v,r)
    v.approve_order(order.order_id,"OWNER")
    v.execute_fill(order.order_id,100)
    sell=PaperIntentGateway(v,r).request_sell_to_close(
        symbol="ABC",quantity=1,paper_trading_enabled=True,
    )
    v.approve_order(sell.order_id,"OWNER")
    v.risk_per_trade_pct=0.2
    v.execute_fill(sell.order_id,101)
    assert not v.positions and v.reconcile().is_reconciled


def test_legacy_strict_accounts_without_gateway_only_remain_compatible(tmp_path):
    v=VirtualAccount(
        "LEGACY-STRICT",starting_capital=50000,state_dir=tmp_path,
        require_pretrade_risk_check=True,trading_mode=TradingMode.MANUAL_APPROVAL,
        approval_authorizer=lambda actor,oid: actor=="OWNER",
        strict_paper_mode=True,
    )
    order=v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    assert v.orders[order.order_id].risk_policy_fingerprint is None
    v.approve_order(order.order_id,"OWNER")
    v.execute_fill(order.order_id,100)
    assert v.positions["ABC"].quantity==1

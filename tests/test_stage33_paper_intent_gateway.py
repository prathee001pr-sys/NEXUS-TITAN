"""Stage33: public opt-in paper gateway cannot bypass authorization or inventory."""
from __future__ import annotations
import pytest
from nexus_titan.shadow.paper_intent_gateway import PaperIntentGateway,PaperIntentDenied
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import VirtualAccount,TradingMode,OrderState


def setup(tmp_path,*,manual=True,risk=True,guard=True,callbacks=True,ids=True):
    v=VirtualAccount("GATE",starting_capital=50000,require_pretrade_risk_check=risk,
        trading_mode=TradingMode.MANUAL_APPROVAL if manual else TradingMode.AUTO_PAPER,
        approval_authorizer=(lambda actor,oid: actor=="OWNER") if callbacks else None)
    l=DurableResearchShadowLedger(tmp_path/"ledger.db",account_id="GATE" if ids else "OTHER",
        starting_capital=50000,guarded_paper_mode=guard)
    return v,l,PaperIntentGateway(v,l)


def buy(g,**extra):
    args=dict(symbol="ABC",quantity=1,entry_price=100,stop_price=95,paper_trading_enabled=True)
    args.update(extra)
    return g.request_buy(**args)


def test_buy_only_creates_unfilled_manual_order_with_no_capital_debit(tmp_path):
    v,l,g=setup(tmp_path)
    before=v.cash_balance
    result=buy(g)
    assert result.side=="BUY"
    assert result.requires_manual_approval and result.simulated_only
    assert result.status=="PENDING_APPROVAL"
    assert v.orders[result.order_id].filled_qty==0
    assert v.cash_balance==before
    assert result.live_orders_transmitted==0
    assert not result.approved_for_strategy_promotion


@pytest.mark.parametrize("changes",[
    {"paper_trading_enabled":False},{"paper_trading_enabled":"yes"},
    {"paper_trading_enabled":0},
])
def test_buy_permission_defaults_to_deny(tmp_path,changes):
    v,l,g=setup(tmp_path)
    with pytest.raises(PaperIntentDenied,match="PAPER_TRADE"):
        buy(g,**changes)
    assert not v.orders


@pytest.mark.parametrize("settings,expected",[
    ({"manual":False},"MANUAL_APPROVAL"),({"risk":False},"pretrade risk"),
    ({"guard":False},"Atomic research"),({"callbacks":False},"identity"),
    ({"ids":False},"account IDs"),
])
def test_buy_rejects_unsafe_configuration(tmp_path,settings,expected):
    v,l,g=setup(tmp_path,**settings)
    with pytest.raises(PaperIntentDenied,match=expected):
        buy(g)
    assert v.orders=={}


def test_buy_rejects_second_admission_after_first_is_pending(tmp_path):
    v,l,g=setup(tmp_path)
    buy(g)
    with pytest.raises(PaperIntentDenied,match="preflight denied"):
        buy(g)
    assert len(v.orders)==1


def test_buy_still_enforces_authoritative_risk(tmp_path):
    v,l,g=setup(tmp_path)
    with pytest.raises(ValueError,match="risk gate"):
        buy(g,quantity=10000)
    assert v.orders=={}


def test_sell_requires_owned_position_and_manual_approval(tmp_path):
    v,l,g=setup(tmp_path)
    b=buy(g)
    v.approve_order(b.order_id,"OWNER")
    v.execute_fill(b.order_id,100)
    close=g.request_sell_to_close(symbol="ABC",quantity=1,paper_trading_enabled=True)
    assert close.side=="SELL" and close.status=="PENDING_APPROVAL"
    assert v.positions["ABC"].quantity==1
    assert v.orders[close.order_id].filled_qty==0
    assert len(v.orders)==2


def test_no_naked_short_or_double_close_pending(tmp_path):
    v,l,g=setup(tmp_path)
    with pytest.raises(PaperIntentDenied,match="naked shorts"):
        g.request_sell_to_close(symbol="ABC",quantity=1,paper_trading_enabled=True)
    b=buy(g)
    v.approve_order(b.order_id,"OWNER")
    v.execute_fill(b.order_id,100)
    g.request_sell_to_close(symbol="ABC",quantity=1,paper_trading_enabled=True)
    with pytest.raises(PaperIntentDenied,match="double-close"):
        g.request_sell_to_close(symbol="ABC",quantity=1,paper_trading_enabled=True)


def test_kill_switch_blocks_new_buy_and_sell_intents(tmp_path):
    v,l,g=setup(tmp_path)
    b=buy(g);v.approve_order(b.order_id,"OWNER");v.execute_fill(b.order_id,100)
    v.activate_emergency_kill_switch()
    with pytest.raises(PaperIntentDenied,match="Kill switch"):
        g.request_sell_to_close(symbol="ABC",quantity=1,paper_trading_enabled=True)
    assert len(v.orders)==1
    # The existing dedicated emergency_square_off remains available.
    assert len(v.emergency_square_off({"ABC":100}))==1


def test_gateway_does_not_change_live_disabled_sentinel(tmp_path):
    v,l,g=setup(tmp_path)
    assert not hasattr(g,"submit_live_order")
    assert v.trading_mode is TradingMode.MANUAL_APPROVAL

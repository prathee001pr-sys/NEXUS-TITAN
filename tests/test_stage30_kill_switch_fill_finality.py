"""Stage30 synthetic-only terminal kill-switch and partial BUY regression tests."""
from __future__ import annotations

import pytest
from nexus_titan.virtual.order_manager import (
    OrderState, OrderSide, TradingMode, VirtualAccount,
)


def _account(**kwargs):
    return VirtualAccount(
        "STAGE30", starting_capital=50000,
        require_pretrade_risk_check=False, **kwargs
    )


def test_partial_buy_is_cancelled_and_cannot_complete_after_kill_switch():
    a=_account()
    order=a.submit_order("ABC","BUY",5)
    a.execute_fill(order.order_id,100,fill_qty=2)
    assert order.state==OrderState.PARTIALLY_FILLED
    before=a.cash_balance
    a.activate_emergency_kill_switch("synthetic test")
    assert order.state==OrderState.CANCELLED
    with pytest.raises(PermissionError,match="prohibits all further BUY"):
        a.execute_fill(order.order_id,100,fill_qty=3)
    assert a.cash_balance==before and a.positions["ABC"].quantity==2


def test_lockout_blocks_forged_accepted_order_even_if_state_is_mutated():
    a=_account()
    order=a.submit_order("ABC","BUY",1)
    a.activate_emergency_kill_switch()
    order.state=OrderState.ACCEPTED
    with pytest.raises(PermissionError,match="prohibits all further BUY"):
        a.execute_fill(order.order_id,100)
    assert a.positions=={}


def test_after_kill_partial_position_can_square_off_without_new_buy():
    a=_account()
    buy=a.submit_order("ABC","BUY",5)
    a.execute_fill(buy.order_id,100,fill_qty=2)
    a.activate_emergency_kill_switch()
    closes=a.emergency_square_off({"ABC":98})
    assert len(closes)==1
    assert closes[0].side==OrderSide.SELL
    assert closes[0].filled_qty==2
    assert a.positions=={}
    assert a.reconcile().is_reconciled


def test_pending_manual_approval_cancelled_on_emergency():
    a=_account(trading_mode=TradingMode.MANUAL_APPROVAL,
               approval_authorizer=lambda actor, oid: True)
    order=a.submit_order("ABC","BUY",1)
    assert order.state==OrderState.PENDING_APPROVAL
    a.activate_emergency_kill_switch()
    assert order.state==OrderState.CANCELLED
    with pytest.raises(ValueError,match="not pending"):
        a.approve_order(order.order_id,"OWNER")


def test_forged_pending_state_after_kill_cannot_approve():
    a=_account(trading_mode=TradingMode.MANUAL_APPROVAL,
               approval_authorizer=lambda actor, oid: True)
    order=a.submit_order("ABC","BUY",1)
    a.activate_emergency_kill_switch()
    order.state=OrderState.PENDING_APPROVAL
    with pytest.raises(PermissionError,match="prohibits order approval"):
        a.approve_order(order.order_id,"OWNER")


def test_kill_lock_persists_across_restart_and_old_partial_buy_stays_cancelled(tmp_path):
    a=_account(state_dir=tmp_path)
    order=a.submit_order("ABC","BUY",2)
    a.execute_fill(order.order_id,100,fill_qty=1)
    a.activate_emergency_kill_switch()
    restored=_account(state_dir=tmp_path)
    assert restored.kill_switched
    assert restored.orders[order.order_id].state==OrderState.CANCELLED
    with pytest.raises(PermissionError,match="prohibits all further BUY"):
        restored.execute_fill(order.order_id,100,fill_qty=1)
    assert restored.positions["ABC"].quantity==1


def test_lockout_cannot_grant_live_mode():
    a=_account()
    a.activate_emergency_kill_switch()
    with pytest.raises(ValueError,match="Live trading"):
        a.set_trading_mode(TradingMode.LIVE_DISABLED)


def test_completed_buy_cannot_be_undone_by_kill_but_position_exits():
    a=_account()
    buy=a.submit_order("ABC","BUY",1)
    a.execute_fill(buy.order_id,100)
    a.activate_emergency_kill_switch()
    assert buy.state==OrderState.FILLED
    closes=a.emergency_square_off({"ABC":110})
    assert len(closes)==1 and closes[0].state==OrderState.FILLED
    assert a.reconcile().is_reconciled


def test_repeated_kill_switch_does_not_reenable_buy():
    a=_account()
    a.activate_emergency_kill_switch()
    a.activate_emergency_kill_switch("second")
    rejected=a.submit_order("ABC","BUY",1)
    assert rejected.state==OrderState.REJECTED
    with pytest.raises(ValueError,match="cannot be filled"):
        a.execute_fill(rejected.order_id,100)

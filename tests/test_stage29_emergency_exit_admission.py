"""Stage29: synthetic-only checks that emergency flag is not a public bypass."""
from __future__ import annotations

import pytest

from nexus_titan.virtual.order_manager import (
    OrderSide, OrderState, TradingMode, VirtualAccount,
)


def _account(**kw):
    return VirtualAccount(
        "STAGE29", starting_capital=50000,
        require_pretrade_risk_check=False, **kw,
    )


@pytest.mark.parametrize("flag", [True, "yes", 1, None])
def test_external_caller_cannot_forge_emergency_buy_or_sell(flag):
    account=_account()
    original=account.reconcile()
    for side in ("BUY","SELL"):
        with pytest.raises(PermissionError,match="Public submit_order"):
            account.submit_order("ABC",side,1,is_emergency=flag)
    assert not account.orders
    assert account.reconcile()==original


def test_external_emergency_flag_cannot_bypass_manual_approval():
    account=_account(trading_mode=TradingMode.MANUAL_APPROVAL)
    with pytest.raises(PermissionError,match="Public submit_order"):
        account.submit_order("ABC","BUY",1,is_emergency=True)
    order=account.submit_order("ABC","BUY",1)
    assert order.state==OrderState.PENDING_APPROVAL
    with pytest.raises(ValueError,match="cannot be filled"):
        account.execute_fill(order.order_id,100)


def test_order_field_mutation_cannot_mint_internal_exit_provenance():
    account=_account()
    order=account.submit_order("ABC","BUY",1)
    cash=account.cash_balance
    order.is_emergency=True
    with pytest.raises(PermissionError,match="no current internal"):
        account.execute_fill(order.order_id,100)
    assert account.cash_balance==cash
    assert not account.positions


def test_internal_protective_stop_sell_reduces_existing_position():
    account=_account()
    buy=account.submit_order("ABC","BUY",2,stop_price=95)
    account.execute_fill(buy.order_id,100)
    exits=account.mark_to_market({"ABC":90})
    assert len(exits)==1
    assert exits[0].side==OrderSide.SELL
    assert exits[0].is_emergency is True
    assert exits[0].state==OrderState.FILLED
    assert "ABC" not in account.positions
    assert account.reconcile().is_reconciled


def test_emergency_square_off_works_after_kill_switch_even_manual_mode():
    account=_account(trading_mode=TradingMode.MANUAL_APPROVAL,
                     approval_authorizer=lambda actor,oid: actor=="OWNER")
    buy=account.submit_order("ABC","BUY",1)
    assert buy.state==OrderState.PENDING_APPROVAL
    account.approve_order(buy.order_id,"OWNER")
    account.execute_fill(buy.order_id,100)
    exits=account.emergency_square_off({"ABC":98})
    assert account.kill_switched
    assert len(exits)==1 and exits[0].state==OrderState.FILLED
    assert account.positions=={}
    denied=account.submit_order("OTHER","BUY",1)
    assert denied.state==OrderState.REJECTED


def test_internal_exit_cannot_target_stale_or_forged_position():
    account=_account()
    buy=account.submit_order("ABC","BUY",1)
    account.execute_fill(buy.order_id,100)
    position=account.positions["ABC"]
    from dataclasses import replace
    with pytest.raises(ValueError,match="no longer matches"):
        account._submit_internal_protective_exit(replace(position))
    assert len(account.orders)==1


def test_restarted_inflight_internal_exit_fails_closed_without_runtime_provenance(tmp_path):
    account=_account(state_dir=tmp_path)
    buy=account.submit_order("ABC","BUY",1)
    account.execute_fill(buy.order_id,100)
    emergency=account._submit_internal_protective_exit(account.positions["ABC"])
    reopened=_account(state_dir=tmp_path)
    with pytest.raises(PermissionError,match="no current internal"):
        reopened.execute_fill(emergency.order_id,100)
    assert reopened.positions["ABC"].quantity==1
    assert reopened.reconcile().is_reconciled


def test_live_mode_still_cannot_be_enabled():
    account=_account()
    with pytest.raises(ValueError,match="Live trading"):
        account.set_trading_mode(TradingMode.LIVE_DISABLED)

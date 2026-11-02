"""Stage37: opt-in durable strict-paper account, safety and rollback tests.

Synthetic only: these checks do not authenticate external identity or grant
broker routing. Legacy simulation mode intentionally remains unchanged.
"""
from __future__ import annotations

import sqlite3
import pytest

from nexus_titan.virtual.order_manager import (
    VirtualAccount, TradingMode, OrderState,
)


def _account(tmp_path, *, strict=True, account_id="SAFE", callback=True, **options):
    return VirtualAccount(
        account_id,starting_capital=50000,state_dir=tmp_path,
        trading_mode=TradingMode.MANUAL_APPROVAL,
        require_pretrade_risk_check=True,
        approval_authorizer=(lambda actor, oid: actor=="OWNER") if callback else None,
        strict_paper_mode=strict,**options,
    )


def _buy(account):
    return account.submit_order(
        "ABC","BUY",1,entry_price=100,stop_price=95,
    )


def test_new_strict_account_is_durable_and_pending_by_default(tmp_path):
    a=_account(tmp_path)
    o=_buy(a)
    assert a.strict_paper_mode
    assert o.state is OrderState.PENDING_APPROVAL
    assert o.filled_qty==0
    assert a.durable_store.strict_mode(a.account_id)


def test_no_approval_cannot_fill_even_if_order_state_forged(tmp_path):
    a=_account(tmp_path)
    o=_buy(a)
    cash=a.cash_balance
    o.state=OrderState.ACCEPTED
    with pytest.raises(PermissionError,match="intact authenticated manual approval"):
        a.execute_fill(o.order_id,100)
    assert a.cash_balance==cash and not a.positions


def test_strict_account_rejects_mutated_or_lost_approval_receipt(tmp_path):
    a=_account(tmp_path)
    o=_buy(a)
    a.approve_order(o.order_id,"OWNER")
    o.quantity=2
    with pytest.raises(PermissionError,match="intact authenticated"):
        a.execute_fill(o.order_id,100)
    o.quantity=1
    o.approval=None
    with pytest.raises(PermissionError,match="intact authenticated"):
        a.execute_fill(o.order_id,100)


def test_strict_regular_buy_sell_cycle_and_manual_gates(tmp_path):
    a=_account(tmp_path)
    b=_buy(a)
    a.approve_order(b.order_id,"OWNER")
    a.execute_fill(b.order_id,100)
    assert a.positions["ABC"].quantity==1
    s=a.submit_order("ABC","SELL",1)
    assert s.state is OrderState.PENDING_APPROVAL
    with pytest.raises(PermissionError,match="intact authenticated"):
        a.execute_fill(s.order_id,105)
    a.approve_order(s.order_id,"OWNER")
    a.execute_fill(s.order_id,105)
    assert not a.positions and a.reconcile().is_reconciled


def test_strict_rejects_naked_sell_and_duplicate_pending_close(tmp_path):
    a=_account(tmp_path)
    with pytest.raises(PermissionError,match="existing long inventory"):
        a.submit_order("ABC","SELL",1)
    b=_buy(a);a.approve_order(b.order_id,"OWNER");a.execute_fill(b.order_id,100)
    s=a.submit_order("ABC","SELL",1)
    with pytest.raises(PermissionError,match="duplicate unfinished close"):
        a.submit_order("ABC","SELL",1)
    assert s.state is OrderState.PENDING_APPROVAL


def test_strict_mode_rejects_auto_paper_even_with_identity_callback(tmp_path):
    a=_account(tmp_path)
    with pytest.raises(PermissionError,match="permanently requires MANUAL"):
        a.set_trading_mode("AUTO_PAPER",actor="OWNER")
    assert a.trading_mode is TradingMode.MANUAL_APPROVAL


def test_strict_mode_persists_when_reopened_without_strict_constructor_flag(tmp_path):
    a=_account(tmp_path)
    b=_buy(a)
    restored=_account(tmp_path,strict=False)
    assert restored.strict_paper_mode
    assert restored.orders[b.order_id].state is OrderState.PENDING_APPROVAL
    restored.approve_order(b.order_id,"OWNER")
    restored.execute_fill(b.order_id,100)
    assert restored.positions["ABC"].quantity==1
    assert restored.reconcile().is_reconciled


def test_in_memory_strict_flag_downgrade_is_rejected(tmp_path):
    a=_account(tmp_path)
    a.strict_paper_mode=False
    with pytest.raises(PermissionError,match="cannot be downgraded"):
        _buy(a)
    with pytest.raises(PermissionError,match="cannot be downgraded"):
        a._sync_durable_store()


def test_strict_risk_flag_mutation_fails_closed_before_buy(tmp_path):
    a=_account(tmp_path)
    a.require_pretrade_risk_check=False
    with pytest.raises(PermissionError,match="risk/auth safety"):
        _buy(a)
    assert not a.orders


def test_strict_manual_mode_tamper_blocks_buy(tmp_path):
    a=_account(tmp_path)
    a.trading_mode=TradingMode.AUTO_PAPER
    with pytest.raises(PermissionError,match="manual/risk/auth"):
        _buy(a)


@pytest.mark.parametrize("invalid",[
    {"state_dir":None},
    {"trading_mode":TradingMode.AUTO_PAPER},
    {"require_pretrade_risk_check":False},
    {"approval_authorizer":None},
])
def test_strict_mode_requires_hardening_prerequisites(tmp_path,invalid):
    settings=dict(
        account_id="STRICT",starting_capital=50000,
        state_dir=tmp_path,
        trading_mode=TradingMode.MANUAL_APPROVAL,
        require_pretrade_risk_check=True,
        approval_authorizer=lambda actor,oid: True,
        strict_paper_mode=True,
    )
    settings.update(invalid)
    with pytest.raises(PermissionError,match="Strict paper mode requires"):
        VirtualAccount(**settings)


def test_strict_migration_needs_explicit_method_for_flat_legacy(tmp_path):
    a=_account(tmp_path,strict=False)
    assert not a.strict_paper_mode
    with pytest.raises(PermissionError,match="cannot silently upgrade"):
        _account(tmp_path,strict=True)
    a.enable_strict_paper_mode()
    assert a.strict_paper_mode and a.durable_store.strict_mode("SAFE")
    a.enable_strict_paper_mode()
    restored=_account(tmp_path,strict=False)
    assert restored.strict_paper_mode


def test_strict_migration_rejects_open_order_or_inventory(tmp_path):
    a=_account(tmp_path,strict=False)
    o=_buy(a)
    with pytest.raises(PermissionError,match="requires flat durable manual"):
        a.enable_strict_paper_mode()
    assert not a.strict_paper_mode
    a.approve_order(o.order_id,"OWNER")
    a.execute_fill(o.order_id,100)
    with pytest.raises(PermissionError,match="requires flat durable manual"):
        a.enable_strict_paper_mode()
    assert not a.strict_paper_mode


def test_strict_restart_missing_authorizer_denies_new_operations(tmp_path):
    a=_account(tmp_path)
    _buy(a)
    restored=_account(tmp_path,strict=False,callback=False)
    with pytest.raises(PermissionError,match="manual/risk/auth"):
        restored.submit_order("XYZ","SELL",1)


def test_strict_kill_still_permits_protective_closure(tmp_path):
    a=_account(tmp_path)
    b=_buy(a);a.approve_order(b.order_id,"OWNER");a.execute_fill(b.order_id,100)
    exit_orders=a.emergency_square_off({"ABC":99})
    assert a.kill_switched
    assert exit_orders and exit_orders[0].is_emergency
    assert not a.positions and a.reconcile().is_reconciled
    with pytest.raises(PermissionError,match="intact authenticated|kill"):
        a.execute_fill(b.order_id,100)


def test_database_snapshot_refuses_strict_policy_downgrade(tmp_path):
    a=_account(tmp_path)
    a.strict_paper_mode=False
    with pytest.raises(PermissionError,match="cannot be downgraded"):
        a._sync_durable_store()
    with sqlite3.connect(a.durable_store.db_path) as con:
        row=con.execute("SELECT strict_paper_mode FROM account_state WHERE account_id='SAFE'").fetchone()
        assert row[0]==1


def test_legacy_paper_fixture_unchanged_and_live_still_disabled(tmp_path):
    legacy=VirtualAccount("LEGACY",starting_capital=50000,require_pretrade_risk_check=False)
    o=legacy.submit_order("ABC","BUY",1)
    legacy.execute_fill(o.order_id,100)
    assert legacy.positions["ABC"].quantity==1
    a=_account(tmp_path)
    with pytest.raises(ValueError,match="Live trading"):
        a.set_trading_mode(TradingMode.LIVE_DISABLED)

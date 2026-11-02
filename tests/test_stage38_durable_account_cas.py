"""Stage38: durable SQLite account compare-and-swap and stale writer denial.

Offline, synthetic only. A stale handle must be abandoned after conflict.
This is not a distributed broker-side lock and does not share Stage19 ledgers.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest

from nexus_titan.virtual.durable_store import (
    DurableAccountStore, StaleAccountSnapshotError,
)
from nexus_titan.virtual.order_manager import VirtualAccount,TradingMode


def account(tmp_path,*,id="CAS",strict=False):
    return VirtualAccount(
        id,starting_capital=50000,state_dir=tmp_path,
        require_pretrade_risk_check=True,trading_mode=TradingMode.MANUAL_APPROVAL,
        approval_authorizer=lambda actor,order_id: actor=="OWNER",
        strict_paper_mode=strict,
    )


def seed(tmp_path,*,strict=False):
    a=account(tmp_path,strict=strict)
    # create initial durable state for non-strict accounts without a fill
    if not strict:
        order=a.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
        a.cancel_order(order.order_id)
    return a


def test_revisions_start_at_one_and_advance_on_mutation(tmp_path):
    a=seed(tmp_path,strict=True)
    assert a._snapshot_revision==1
    first=a.durable_store.revision("CAS")
    b=a.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    assert a._snapshot_revision==first+1
    a.cancel_order(b.order_id)
    assert a.durable_store.revision("CAS")==a._snapshot_revision


@pytest.mark.parametrize("strict",[False,True])
def test_second_handle_cannot_overwrite_newer_account_state(tmp_path,strict):
    first=seed(tmp_path,strict=strict)
    other=account(tmp_path,strict=False)
    before=other._snapshot_revision
    first.adjust_capital(100,"TOP_UP")
    assert first.current_capital==50100
    with pytest.raises(StaleAccountSnapshotError,match="changed in another process"):
        other.submit_order("XYZ","BUY",1,entry_price=100,stop_price=95)
    assert other._stale_snapshot_detected
    with pytest.raises(StaleAccountSnapshotError,match="reopen"):
        other.approve_order("UNKNOWN","OWNER")
    restored=account(tmp_path,strict=False)
    assert restored.current_capital==50100
    assert restored.cash_balance==50100
    assert restored._snapshot_revision!=before


def test_direct_store_cas_rejects_even_if_two_handles_bypass_initial_precheck(tmp_path):
    original=seed(tmp_path)
    second=account(tmp_path)
    revision=original._snapshot_revision
    original._sync_durable_store()
    # Force a lower-level stale write to reach BEGIN IMMEDIATE;
    # the store's own compare-and-swap is the true commit boundary.
    with pytest.raises(StaleAccountSnapshotError,match="revision"):
        second.durable_store.save_snapshot(
            account_id="CAS",initial_capital=50000,
            added_capital=0,withdrawn_capital=0,cash_balance=50000,
            blocked_margin=0,realized_pnl=0,total_fees=0,
            peak_equity=50000,risk_per_trade_pct=1,
            max_portfolio_exposure_pct=50,initial_margin_pct=20,
            require_pretrade_risk_check=True,strict_paper_mode=False,
            trading_mode="MANUAL_APPROVAL",kill_switched=False,
            kill_metadata={},orders_dict={},positions_dict={},
            idem_keys=set(),capital_history=[],
            expected_revision=revision,
        )
    assert original.durable_store.revision("CAS")==revision+1


def test_parallel_writers_only_one_wins_same_generation(tmp_path):
    first=seed(tmp_path,strict=True)
    second=account(tmp_path)
    # Two handles with identical start version: exactly one snapshot commits.
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut1=pool.submit(first._sync_durable_store)
        fut2=pool.submit(second._sync_durable_store)
        outcomes=[]
        for future in (fut1,fut2):
            try:
                future.result()
                outcomes.append("OK")
            except StaleAccountSnapshotError:
                outcomes.append("STALE")
    assert sorted(outcomes)==["OK","STALE"]
    assert account(tmp_path)._snapshot_revision==2


def test_stale_emergency_square_off_requires_fresh_account_state(tmp_path):
    first=seed(tmp_path,strict=True)
    b=first.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    first.approve_order(b.order_id,"OWNER")
    first.execute_fill(b.order_id,100)
    old=account(tmp_path)
    first.adjust_capital(100,"TOP_UP")
    with pytest.raises(StaleAccountSnapshotError):
        old.emergency_square_off({"ABC":99})
    reopened=account(tmp_path)
    exits=reopened.emergency_square_off({"ABC":99})
    assert len(exits)==1 and not reopened.positions
    assert reopened.reconcile().is_reconciled


def test_two_independent_account_ids_do_not_conflict(tmp_path):
    a=seed(tmp_path,strict=True)
    b=account(tmp_path,id="OTHER",strict=True)
    a.adjust_capital(100,"TOP_UP")
    b.adjust_capital(200,"TOP_UP")
    assert a.durable_store.revision("CAS")==2
    assert b.durable_store.revision("OTHER")==2


def test_persisted_strict_flag_cannot_downgrade_via_cas(tmp_path):
    a=seed(tmp_path,strict=True)
    before=a._snapshot_revision
    a.strict_paper_mode=False
    with pytest.raises(PermissionError,match="cannot be downgraded"):
        a._sync_durable_store()
    assert a.durable_store.revision("CAS")==before
    assert a.durable_store.strict_mode("CAS")


def test_multiple_versions_reconcile_after_restart(tmp_path):
    a=seed(tmp_path,strict=True)
    b=a.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    a.approve_order(b.order_id,"OWNER")
    a.execute_fill(b.order_id,100)
    restored=account(tmp_path)
    assert restored.positions["ABC"].quantity==1
    assert restored.reconcile().is_reconciled
    assert restored._snapshot_revision==a._snapshot_revision


def test_schema_has_durable_revision_not_only_in_memory(tmp_path):
    a=seed(tmp_path,strict=True)
    with sqlite3.connect(a.durable_store.db_path) as con:
        row=con.execute("SELECT revision FROM account_state WHERE account_id='CAS'").fetchone()
    assert row[0]==a._snapshot_revision


def test_live_execution_remains_disabled(tmp_path):
    a=seed(tmp_path,strict=True)
    with pytest.raises(ValueError,match="Live trading"):
        a.set_trading_mode("LIVE_DISABLED")

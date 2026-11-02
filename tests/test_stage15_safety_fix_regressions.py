"""Focused regression tests for Stage 15 virtual-account safety fixes."""
from __future__ import annotations
import json
import pytest
from nexus_titan.virtual.order_manager import OrderSide, OrderState, TradingMode, VirtualAccount

def _account(account_id: str = "SAFETY-TEST", state_dir=None) -> VirtualAccount:
    return VirtualAccount(account_id=account_id, starting_capital=50_000,
                          require_pretrade_risk_check=False, state_dir=state_dir)

def test_kill_switch_marker_overrides_stale_sqlite_snapshot(tmp_path):
    first = _account("STALE-LOCK", tmp_path)
    assert not first.kill_switched and first.lock_file is not None
    first.lock_file.write_text(json.dumps({"kill_switched": True, "reason": "durable marker"}), encoding="utf-8")
    restored = _account("STALE-LOCK", tmp_path)
    assert restored.kill_switched is True
    assert restored.submit_order("TCS", OrderSide.BUY, 1).state == OrderState.REJECTED

def test_kill_switch_fails_closed_when_sqlite_persist_fails_after_marker(tmp_path, monkeypatch):
    first = _account("DB-WRITE-FAIL", tmp_path)
    def fail_snapshot(**_kwargs):
        raise OSError("simulated SQLite write failure")
    assert first.durable_store is not None
    monkeypatch.setattr(first.durable_store, "save_snapshot", fail_snapshot)
    with pytest.raises(OSError, match="simulated SQLite write failure"):
        first.activate_emergency_kill_switch("test persistence failure")
    restored = _account("DB-WRITE-FAIL", tmp_path)
    assert restored.kill_switched is True
    assert restored.submit_order("INFY", OrderSide.BUY, 1).state == OrderState.REJECTED

def test_corrupt_kill_switch_marker_locks_account_on_restart(tmp_path):
    first = _account("CORRUPT-LOCK", tmp_path)
    assert first.lock_file is not None
    first.lock_file.write_text("{not-json", encoding="utf-8")
    restored = _account("CORRUPT-LOCK", tmp_path)
    assert restored.kill_switched is True
    assert restored.kill_switch_metadata.get("recovery_required") is True
    assert restored.submit_order("TCS", OrderSide.BUY, 1).state == OrderState.REJECTED

def test_fill_idempotency_exact_retry_is_safe_and_cross_order_reuse_conflicts():
    account = _account()
    first = account.submit_order("TCS", OrderSide.BUY, 1)
    second = account.submit_order("INFY", OrderSide.BUY, 1)
    filled = account.execute_fill(first.order_id, 100.0, idempotency_key="fill-key-1")
    cash_after_fill = account.cash_balance
    assert account.execute_fill(first.order_id, 100.0, idempotency_key="fill-key-1") is filled
    assert account.cash_balance == cash_after_fill
    with pytest.raises(ValueError, match="Idempotency key conflict"):
        account.execute_fill(second.order_id, 100.0, idempotency_key="fill-key-1")
    with pytest.raises(ValueError, match="Idempotency key conflict"):
        account.execute_fill(first.order_id, 101.0, idempotency_key="fill-key-1")

def test_fill_idempotency_survives_restart_and_rejects_different_quantity(tmp_path):
    first = _account("FILL-RESTART", tmp_path)
    order = first.submit_order("TCS", OrderSide.BUY, 2)
    first.execute_fill(order.order_id, 100.0, fill_qty=1, idempotency_key="restart-key")
    restored = _account("FILL-RESTART", tmp_path)
    restored_order = restored.orders[order.order_id]
    before = restored.cash_balance
    restored.execute_fill(order.order_id, 100.0, fill_qty=1, idempotency_key="restart-key")
    assert restored.cash_balance == before
    with pytest.raises(ValueError, match="Idempotency key conflict"):
        restored.execute_fill(order.order_id, 100.0, fill_qty=2, idempotency_key="restart-key")
    assert restored_order.filled_qty == 1

def test_manual_approval_snapshot_hash_uses_full_sha256():
    account = VirtualAccount(starting_capital=50_000, trading_mode=TradingMode.MANUAL_APPROVAL,
                             require_pretrade_risk_check=False,
                             approval_authorizer=lambda actor, order_id: actor == "OWNER")
    order = account.submit_order("TCS", OrderSide.BUY, 1)
    approved = account.approve_order(order.order_id, actor="OWNER")
    assert approved.approval is not None
    assert len(approved.approval.order_snapshot_hash) == 64
    assert all(char in "0123456789abcdef" for char in approved.approval.order_snapshot_hash)

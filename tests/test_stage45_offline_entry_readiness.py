"""Stage45 local defense-in-depth paper entry tests; ALL synthetic, no broker."""
from __future__ import annotations

from dataclasses import replace

import pytest

from nexus_titan.operations.paper_deployment import (
    PaperDeploymentConfig, open_paper_only_deployment,
)
from nexus_titan.operations.offline_entry_readiness import (
    Stage45ConservativePaperEntry, Stage45EntryBlocked,
    inspect_stage45_offline_entry,
)
from nexus_titan.virtual.order_manager import OrderState


def _deployment(tmp_path, *, enabled=True, capital=50000):
    cfg = PaperDeploymentConfig(
        account_id="S45-TEST",
        starting_capital=capital,
        virtual_state_dir=tmp_path / "virtual",
        research_db_path=tmp_path / "research.sqlite3",
        paper_orders_enabled=enabled,
    )
    return open_paper_only_deployment(
        cfg, approval_authorizer=lambda actor, resource: actor == "OWNER",
    )


@pytest.mark.parametrize("capital", [50000, 12500, 75000])
def test_fresh_opted_in_flat_accounts_pass_local_gate_only(tmp_path, capital):
    stage43 = _deployment(tmp_path, capital=capital)
    gate = Stage45ConservativePaperEntry(stage43)
    s = gate.status()
    assert s.can_create_new_synthetic_buy_intent
    assert s.virtual_internal_reconciliation_passed
    assert s.research_hash_integrity_passed
    assert s.flat_separate_books_observed
    assert s.exact_starting_cash_match_observed
    assert not s.production_ready
    assert not s.real_market_data_authenticated
    assert not s.externally_authenticated_human_approval
    assert not s.independently_enforced_global_risk_veto
    assert not s.cross_ledger_atomicity_verified
    assert not s.extended_real_shadow_validation_verified
    assert not s.strategy_promotion_allowed
    assert s.broker_orders_transmitted == 0


def test_default_read_only_status_does_not_grant_paper_entry(tmp_path):
    deployment = _deployment(tmp_path, enabled=False)
    gate = Stage45ConservativePaperEntry(deployment)
    status = gate.status()
    assert not status.can_create_new_synthetic_buy_intent
    assert any("disabled by session" in message for message in status.blockers)
    with pytest.raises(Stage45EntryBlocked):
        gate.request_buy(symbol="ABC", quantity=1, entry_price=100, stop_price=95)
    assert not deployment.virtual_account.orders


def test_single_pending_synthetic_buy_is_manual_and_blocks_parallel_entry(tmp_path):
    deployment = _deployment(tmp_path)
    gate = Stage45ConservativePaperEntry(deployment)
    initial_cash = deployment.virtual_account.cash_balance
    first = gate.request_buy(symbol="ABC", quantity=1, entry_price=100, stop_price=95)
    assert first.status == "PENDING_APPROVAL"
    assert first.live_orders_transmitted == 0
    assert deployment.virtual_account.cash_balance == initial_cash
    assert deployment.virtual_account.orders[first.order_id].filled_qty == 0
    with pytest.raises(Stage45EntryBlocked, match="virgin and flat"):
        gate.request_buy(symbol="XYZ", quantity=1, entry_price=100, stop_price=95)
    assert len(deployment.virtual_account.orders) == 1
    assert not gate.status().production_ready


def test_cancelled_unfilled_intent_can_be_followed_by_new_manual_intent(tmp_path):
    deployment = _deployment(tmp_path)
    gate = Stage45ConservativePaperEntry(deployment)
    first = gate.request_buy(symbol="ABC", quantity=1, entry_price=100, stop_price=95)
    cancelled = deployment.virtual_account.cancel_order(first.order_id)
    assert cancelled.state is OrderState.CANCELLED
    assert gate.status().can_create_new_synthetic_buy_intent
    second = gate.request_buy(symbol="XYZ", quantity=1, entry_price=100, stop_price=95)
    assert second.order_id != first.order_id
    assert second.status == "PENDING_APPROVAL"


def test_fill_even_when_internal_reconciled_is_not_cross_ledger_proof(tmp_path):
    deployment = _deployment(tmp_path)
    gate = Stage45ConservativePaperEntry(deployment)
    first = gate.request_buy(symbol="ABC", quantity=1, entry_price=100, stop_price=95)
    deployment.virtual_account.approve_order(first.order_id, "OWNER")
    deployment.virtual_account.execute_fill(first.order_id, 100)
    assert deployment.virtual_account.reconcile().is_reconciled
    report = gate.status()
    assert not report.flat_separate_books_observed
    assert not report.exact_starting_cash_match_observed
    assert not report.can_create_new_synthetic_buy_intent
    with pytest.raises(Stage45EntryBlocked):
        gate.request_buy(symbol="ABC", quantity=1, entry_price=100, stop_price=95)


def test_round_trip_closed_trade_still_blocks_unsafe_cross_book_claim(tmp_path):
    deployment = _deployment(tmp_path)
    gate = Stage45ConservativePaperEntry(deployment)
    first = gate.request_buy(symbol="ABC", quantity=1, entry_price=100, stop_price=95)
    deployment.virtual_account.approve_order(first.order_id, "OWNER")
    deployment.virtual_account.execute_fill(first.order_id, 100)
    exit_intent = deployment.request_sell_to_close(symbol="ABC", quantity=1)
    deployment.virtual_account.approve_order(exit_intent.order_id, "OWNER")
    deployment.virtual_account.execute_fill(exit_intent.order_id, 100)
    assert not deployment.virtual_account.positions
    assert not gate.status().can_create_new_synthetic_buy_intent
    assert not gate.status().cross_ledger_atomicity_verified


def test_local_cash_drift_blocks_new_entry_even_if_hash_audit_is_intact(tmp_path):
    deployment = _deployment(tmp_path)
    gate = Stage45ConservativePaperEntry(deployment)
    deployment.virtual_account.cash_balance -= 100
    report = gate.status()
    assert not report.can_create_new_synthetic_buy_intent
    assert any("Cash" in b or "reconciliation" in b.lower()
               for b in report.blockers)


def test_kill_switch_survives_restart_and_blocks_stage45(tmp_path):
    deployment = _deployment(tmp_path)
    deployment.virtual_account.activate_emergency_kill_switch("synthetic S45")
    reopened = _deployment(tmp_path)
    report = inspect_stage45_offline_entry(reopened)
    assert not report.can_create_new_synthetic_buy_intent
    assert any("kill" in b.lower() for b in report.blockers)
    assert not report.production_ready


def test_stale_handle_cannot_be_reused_for_new_stage45_buy(tmp_path):
    old = _deployment(tmp_path)
    fresh = _deployment(tmp_path)
    first = Stage45ConservativePaperEntry(fresh).request_buy(
        symbol="ABC", quantity=1, entry_price=100, stop_price=95,
    )
    assert first.status == "PENDING_APPROVAL"
    assert not Stage45ConservativePaperEntry(old).status().can_create_new_synthetic_buy_intent
    with pytest.raises(Stage45EntryBlocked):
        Stage45ConservativePaperEntry(old).request_buy(
            symbol="ABC", quantity=1, entry_price=100, stop_price=95,
        )


def test_research_audit_corruption_blocks_without_new_intent(tmp_path):
    import sqlite3
    deployment = _deployment(tmp_path)
    path = deployment.config.research_db_path
    with sqlite3.connect(path) as db:
        db.execute("UPDATE accounts SET cash_cents = cash_cents - 100 WHERE account_id=?", (
            deployment.config.account_id,
        ))
    status = Stage45ConservativePaperEntry(deployment).status()
    assert not status.can_create_new_synthetic_buy_intent
    assert not status.research_hash_integrity_passed


def test_inspect_is_read_only_for_clean_accounts(tmp_path):
    deployment = _deployment(tmp_path)
    gate = Stage45ConservativePaperEntry(deployment)
    revision = deployment.virtual_account._snapshot_revision
    before = deployment.research_ledger.status()
    first = gate.status()
    second = gate.status()
    assert first == second
    assert deployment.virtual_account._snapshot_revision == revision
    assert deployment.research_ledger.status() == before
    assert not deployment.virtual_account.orders


def test_bad_type_fails_and_cannot_create_account():
    with pytest.raises(TypeError):
        Stage45ConservativePaperEntry(object())
    with pytest.raises(TypeError):
        inspect_stage45_offline_entry(None)

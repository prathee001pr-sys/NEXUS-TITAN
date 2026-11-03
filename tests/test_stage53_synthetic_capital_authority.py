"""Stage53: adversarial synthetic capital authority / risk-budget tests.

No real market data, trades, broker, external signer or production capital.
These tests inspect only a standalone disposable SQLite budget database.
"""
from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from nexus_titan.operations.synthetic_capital_authority import (
    Stage53BudgetBlocked,
    Stage53BudgetPolicy,
    Stage53SyntheticCapitalAuthority,
)

def _authority(root, *, capital=5_000_000, account="QA53", policy=None, path=None):
    return Stage53SyntheticCapitalAuthority(
        db_path=path or (root / "stage53_capital.sqlite3"),
        account_id=account,
        starting_cents=capital,
        policy=policy or Stage53BudgetPolicy(),
    )


@pytest.mark.parametrize("capital", [1_250_000, 5_000_000, 17_500_000])
def test_initial_budget_matches_variable_synthetic_capital(tmp_path, capital):
    auth = _authority(tmp_path, capital=capital)
    status = auth.inspect()
    assert status.local_integrity_verified
    assert status.account_id == "QA53"
    assert status.initial_cents == capital
    assert status.held_cents == 0
    assert status.remaining_cents == capital
    assert status.hold_count == 0
    assert status.revision == 0
    assert status.audit_chain_tip == "0" * 64
    assert status.max_single_hold_bps == 2000
    assert status.max_aggregate_held_bps == 5000
    assert not status.blockers
    assert not status.globally_mandatory_for_legacy_api
    assert not status.single_authority_for_existing_virtual_and_research_books
    assert not status.cross_database_atomicity_verified
    assert not status.independent_risk_veto_enforced
    assert not status.independent_authenticated_human_identity
    assert not status.external_quote_or_market_data_verified
    assert not status.signer_key_externally_isolated
    assert not status.live_trading_enabled
    assert status.broker_orders_transmitted == 0
    assert not status.production_ready


def test_atomic_single_budget_hold_updates_only_its_own_ledger(tmp_path):
    auth = _authority(tmp_path)
    receipt = auth.hold_for_synthetic_research(
        request_id="PAPER-REQUEST-1", amount_cents=100_000,
    )
    assert receipt.account_id == "QA53"
    assert receipt.held_cents == 100_000
    assert receipt.total_held_cents == 100_000
    assert receipt.remaining_cents == 4_900_000
    assert receipt.revision == 1
    assert len(receipt.audit_chain_tip) == 64
    assert not receipt.trading_authority
    assert receipt.synthetic_only
    assert receipt.broker_orders_transmitted == 0
    result = auth.inspect()
    assert result.local_integrity_verified
    assert result.held_cents == 100_000
    assert result.remaining_cents == 4_900_000
    assert result.hold_count == 1
    with sqlite3.connect(tmp_path / "stage53_capital.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM budget_holds").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM budget_events").fetchone()[0] == 1


def test_duplicate_request_id_is_rejected_without_changing_total(tmp_path):
    auth = _authority(tmp_path)
    first = auth.hold_for_synthetic_research(request_id="ID:ONE", amount_cents=1000)
    with pytest.raises(Stage53BudgetBlocked, match="Duplicate"):
        auth.hold_for_synthetic_research(request_id="ID:ONE", amount_cents=1000)
    with pytest.raises(Stage53BudgetBlocked, match="Duplicate"):
        auth.hold_for_synthetic_research(request_id="ID:ONE", amount_cents=2000)
    assert auth.inspect().held_cents == 1000
    assert auth.inspect().revision == 1
    assert auth.inspect().audit_chain_tip == first.audit_chain_tip


def test_sequential_reservations_are_capped_by_aggregate_not_cash(tmp_path):
    auth = _authority(tmp_path)
    for i in range(2):
        auth.hold_for_synthetic_research(
            request_id=f"REQ-{i}", amount_cents=1_000_000,
        )
    auth.hold_for_synthetic_research(request_id="REQ-2", amount_cents=500_000)
    with pytest.raises(Stage53BudgetBlocked, match="Aggregate"):
        auth.hold_for_synthetic_research(request_id="REQ-3", amount_cents=1)
    st = auth.inspect()
    assert st.local_integrity_verified
    assert st.held_cents == 2_500_000
    assert st.remaining_cents == 2_500_000
    assert st.hold_count == 3


def test_single_hold_cap_blocks_before_mutation(tmp_path):
    auth = _authority(tmp_path)
    with pytest.raises(Stage53BudgetBlocked, match="per-request"):
        auth.hold_for_synthetic_research(request_id="TOO-LARGE", amount_cents=1_000_001)
    assert auth.inspect().revision == 0


@pytest.mark.parametrize("bad", [None, True, False, 1.0, "100", 0, -1, 900_000_000_000_001])
def test_invalid_amounts_fail_closed_without_mutation(tmp_path, bad):
    auth = _authority(tmp_path)
    with pytest.raises(Stage53BudgetBlocked):
        auth.hold_for_synthetic_research(request_id="BAD", amount_cents=bad)
    assert auth.inspect().revision == 0


@pytest.mark.parametrize("bad", ["", "../parent", "invalid space", "\x00", "x" * 81, None, False, 12])
def test_bad_request_ids_are_refused_without_writes(tmp_path, bad):
    auth = _authority(tmp_path)
    with pytest.raises(Stage53BudgetBlocked):
        auth.hold_for_synthetic_research(request_id=bad, amount_cents=100)
    assert auth.inspect().revision == 0


@pytest.mark.parametrize("bad", [True, None, 0, -1, 1.5, 10001, "5000"])
def test_invalid_policy_caps_are_denied(bad):
    with pytest.raises(Stage53BudgetBlocked):
        Stage53BudgetPolicy(max_single_hold_bps=bad)


def test_single_cap_cannot_exceed_total_cap():
    with pytest.raises(Stage53BudgetBlocked):
        Stage53BudgetPolicy(max_single_hold_bps=5001, max_aggregate_held_bps=5000)


def test_scope_is_bound_to_exact_account_and_policy_and_start_capital(tmp_path):
    _authority(tmp_path)
    with pytest.raises(Stage53BudgetBlocked, match="changed"):
        _authority(tmp_path, account="OTHER")
    with pytest.raises(Stage53BudgetBlocked, match="changed"):
        _authority(tmp_path, capital=6_000_000)
    with pytest.raises(Stage53BudgetBlocked, match="changed"):
        _authority(tmp_path, policy=Stage53BudgetPolicy(1000, 5000))
    same = _authority(tmp_path)
    assert same.inspect().local_integrity_verified


def test_existing_hold_persists_across_new_instance_and_restart(tmp_path):
    auth = _authority(tmp_path)
    first = auth.hold_for_synthetic_research(
        request_id="PERSIST-1", amount_cents=300_000,
    )
    del auth
    reopened = _authority(tmp_path)
    result = reopened.inspect()
    assert result.local_integrity_verified
    assert result.held_cents == 300_000
    assert result.revision == 1
    assert result.audit_chain_tip == first.audit_chain_tip
    with pytest.raises(Stage53BudgetBlocked, match="Duplicate"):
        reopened.hold_for_synthetic_research(
            request_id="PERSIST-1", amount_cents=300_000,
        )
    second = reopened.hold_for_synthetic_research(
        request_id="PERSIST-2", amount_cents=200_000,
    )
    assert second.revision == 2
    assert second.total_held_cents == 500_000
    assert second.audit_chain_tip != first.audit_chain_tip


def test_two_objects_same_sqlite_file_cannot_double_spend_limit(tmp_path):
    a = _authority(tmp_path)
    b = _authority(tmp_path)

    def attempt(instance, rid):
        try:
            return instance.hold_for_synthetic_research(
                request_id=rid, amount_cents=1_500_000,
            )
        except Stage53BudgetBlocked as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        x = pool.submit(attempt, a, "THREAD-A")
        y = pool.submit(attempt, b, "THREAD-B")
        results = [x.result(), y.result()]
    successful = [r for r in results if not isinstance(r, str)]
    denied = [r for r in results if isinstance(r, str)]
    assert len(successful) == 1, results
    assert len(denied) == 1
    assert a.inspect().revision == 1
    assert a.inspect().held_cents == 1_500_000


def test_distinct_concurrent_requests_under_cap_both_commit_safely(tmp_path):
    a = _authority(tmp_path)
    b = _authority(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        x = pool.submit(
            a.hold_for_synthetic_research, request_id="FIRST", amount_cents=400_000,
        )
        y = pool.submit(
            b.hold_for_synthetic_research, request_id="SECOND", amount_cents=500_000,
        )
        receipts = [x.result(), y.result()]
    assert sorted(r.revision for r in receipts) == [1, 2]
    assert a.inspect().held_cents == 900_000
    assert a.inspect().revision == 2
    assert a.inspect().local_integrity_verified


@pytest.mark.parametrize("corrupt", [
    "UPDATE budget_scope SET held_cents=held_cents+1",
    "UPDATE budget_scope SET chain_tip='0'",
    "UPDATE budget_scope SET revision=revision+1",
    "UPDATE budget_holds SET amount_cents=amount_cents+1",
    "UPDATE budget_events SET total_held_cents=total_held_cents+1",
    "UPDATE budget_events SET event_sha='0'",
    "DELETE FROM budget_events",
    "DELETE FROM budget_holds",
])
def test_detects_head_hold_or_event_corruption_and_never_grants_authority(tmp_path, corrupt):
    auth = _authority(tmp_path)
    auth.hold_for_synthetic_research(request_id="A", amount_cents=100_000)
    with sqlite3.connect(tmp_path / "stage53_capital.sqlite3") as db:
        db.execute(corrupt)
    report = auth.inspect()
    assert not report.local_integrity_verified
    assert report.blockers
    assert report.held_cents is None
    with pytest.raises(Stage53BudgetBlocked):
        auth.hold_for_synthetic_research(request_id="NEXT", amount_cents=1)
    assert not report.production_ready


def test_missing_scope_with_existing_holds_fails_closed(tmp_path):
    auth = _authority(tmp_path)
    auth.hold_for_synthetic_research(request_id="A", amount_cents=500)
    with sqlite3.connect(tmp_path / "stage53_capital.sqlite3") as db:
        db.execute("DELETE FROM budget_scope")
    assert not auth.inspect().local_integrity_verified
    with pytest.raises(Stage53BudgetBlocked):
        _authority(tmp_path)


def test_path_alias_and_symlink_are_denied(tmp_path):
    other = tmp_path / "virtual_durable.db"
    with pytest.raises(Stage53BudgetBlocked, match="alias"):
        Stage53SyntheticCapitalAuthority(
            db_path=other, account_id="QA53", starting_cents=5000000,
            excluded_ledger_paths=(other,),
        )
    base = tmp_path / "real.sqlite3"
    _authority(tmp_path, path=base)
    alias = tmp_path / "alias.sqlite3"
    alias.symlink_to(base)
    with pytest.raises(Stage53BudgetBlocked, match="Symlinked"):
        _authority(tmp_path, path=alias)


def test_empty_db_file_remains_reusable_only_with_same_policy(tmp_path):
    a = _authority(tmp_path)
    b = _authority(tmp_path)
    assert a.inspect() == b.inspect()
    with pytest.raises(Stage53BudgetBlocked):
        _authority(tmp_path, policy=Stage53BudgetPolicy(1000, 5000))


def test_preexisting_table_forged_held_budget_requires_scope(tmp_path):
    db = tmp_path / "stage53_capital.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE budget_holds (
            request_id TEXT PRIMARY KEY, amount_cents INTEGER NOT NULL,
            seq INTEGER NOT NULL UNIQUE, created_utc TEXT NOT NULL
        )""")
        conn.execute(
            "INSERT INTO budget_holds VALUES ('SPOOF',100,1,'2026-11-03')"
        )
    with pytest.raises(Stage53BudgetBlocked, match="Missing budget scope"):
        _authority(tmp_path)


def test_receipt_is_non_authoritative_and_no_order_api_is_exposed(tmp_path):
    auth = _authority(tmp_path)
    r = auth.hold_for_synthetic_research(request_id="A", amount_cents=100)
    assert not r.trading_authority
    assert r.synthetic_only
    assert not hasattr(auth, "submit_order")
    assert not hasattr(auth, "execute_fill")
    assert not hasattr(auth, "approve_order")
    assert not hasattr(auth, "release_hold")
    assert not hasattr(auth, "transfer_to_virtual_account")
    assert auth.inspect().globally_mandatory_for_legacy_api is False
    assert auth.inspect().single_authority_for_existing_virtual_and_research_books is False


def test_audit_hash_chain_is_deterministic_and_distinct_per_event(tmp_path):
    auth = _authority(tmp_path)
    first = auth.hold_for_synthetic_research(request_id="ONE", amount_cents=100)
    second = auth.hold_for_synthetic_research(request_id="TWO", amount_cents=100)
    assert second.audit_chain_tip != first.audit_chain_tip
    assert second.revision == 2
    assert second.total_held_cents == 200
    with sqlite3.connect(tmp_path / "stage53_capital.sqlite3") as db:
        first_hash = db.execute(
            "SELECT event_sha FROM budget_events WHERE seq=1"
        ).fetchone()[0]
        prev_hash = db.execute(
            "SELECT prev_sha FROM budget_events WHERE seq=2"
        ).fetchone()[0]
    assert prev_hash == first_hash == first.audit_chain_tip


def test_invalid_account_ids_and_capital_rejected_before_init(tmp_path):
    for acct in ("", "bad/path", "a" * 81, "bad space", None, False):
        with pytest.raises(Stage53BudgetBlocked):
            _authority(tmp_path, account=acct)
    for money in (True, False, 0, -1, 10.5, "50000"):
        with pytest.raises(Stage53BudgetBlocked):
            _authority(tmp_path, capital=money)
    assert not (tmp_path / "stage53_capital.sqlite3").exists()


def test_cli_demo_has_no_real_orders_and_correct_budget(tmp_path):
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_stage53_capital_authority_smoke.py")],
        cwd=root, capture_output=True, text=True, check=False, timeout=35,
    )
    assert run.returncode == 0, run.stderr
    evidence = json.loads(run.stdout)
    assert evidence["mode"] == "STAGE53_LOCAL_SYNTHETIC_BUDGET_ONLY"
    assert evidence["duplicate_request_denied"] is True
    assert evidence["restart_durable_hold_verified"] is True
    assert evidence["held_cents"] == 100000
    assert evidence["hold_count"] == 1
    assert evidence["remaining_cents"] == 4900000
    assert evidence["broker_orders_transmitted"] == 0
    assert evidence["production_ready"] is False
    assert evidence["cross_database_atomicity_verified"] is False
    assert evidence["independent_risk_veto_enforced"] is False

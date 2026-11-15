"""Stage82 local SQLite kill switch regression tests; no real trading."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pytest

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticBookBlocked,
    Stage55SyntheticPolicy,
)


def book(path: Path):
    return Stage55IsolatedSyntheticExecutionBook(
        db_path=path, account_id="stage82-synthetic",
        starting_cents=1000000,
        policy=Stage55SyntheticPolicy(),
    )


def reserve(b, order="opt-a"):
    return b.reserve_synthetic_buy(
        request_id=order, symbol="NIFTYOPT", quantity=10,
        limit_price_cents=1000, fee_buffer_cents=100,
    )


def fill(b, order="opt-a"):
    return b.record_simulated_fill(
        order_id=order, fill_id="fill-"+order, quantity=10,
        price_cents=950, fee_cents=50,
        evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
    )


def test_local_kill_state_survives_restart_and_has_no_live_authority(tmp_path):
    path = tmp_path/"same.sqlite"
    a = book(path)
    assert not a.inspect_local_synthetic_risk_state().kill_switch_active
    killed = a.set_local_synthetic_kill_switch(active=True, operation_id="kill-1")
    assert killed.kill_switch_active and killed.risk_revision == 1
    assert not killed.authenticated_risk_authority
    assert not killed.globally_unbypassable
    b = book(path)
    assert b.inspect_local_synthetic_risk_state().kill_switch_active
    with pytest.raises(Stage55SyntheticBookBlocked, match="kill switch"):
        reserve(b)
    assert b.inspect().revision == 0
    assert b.inspect().local_integrity_verified
    assert b.inspect_local_synthetic_risk_state().live_trading_enabled is False


def test_raw_direct_stage55_buy_and_fill_blocked_but_cancel_works(tmp_path):
    path=tmp_path/"same.sqlite"
    a=book(path)
    reserve(a)
    b=book(path)
    a.set_local_synthetic_kill_switch(active=True, operation_id="risk-stop")
    with pytest.raises(Stage55SyntheticBookBlocked, match="kill switch"):
        reserve(b, "opt-b")
    with pytest.raises(Stage55SyntheticBookBlocked, match="kill switch"):
        fill(b)
    cancelled = b.cancel_unfilled(
        order_id="opt-a", cancel_id="cancel-a",
        evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
    )
    assert cancelled.order_state == "CANCELLED_SYNTHETIC"
    assert cancelled.open_reserved_cents == 0
    assert b.inspect().cash_cents == 1000000


def test_test_only_rearm_is_untrusted_but_resumes_local_simulation(tmp_path):
    a=book(tmp_path/"same.sqlite")
    a.set_local_synthetic_kill_switch(active=True, operation_id="kill")
    cleared=a.set_local_synthetic_kill_switch(active=False, operation_id="operator-untrusted")
    assert cleared.risk_revision == 2
    assert not cleared.kill_switch_active
    assert reserve(a).order_state == "PENDING_SYNTHETIC"
    assert a.inspect().revision == 1


@pytest.mark.parametrize("active", [None, 0, 1, "yes", [], {}])
def test_bad_kill_switch_flag_never_changes_state(tmp_path, active):
    a=book(tmp_path/"same.sqlite")
    with pytest.raises(Stage55SyntheticBookBlocked, match="bool"):
        a.set_local_synthetic_kill_switch(active=active, operation_id="bad")
    assert a.inspect_local_synthetic_risk_state().risk_revision == 0
    assert not a.inspect_local_synthetic_risk_state().kill_switch_active


def test_second_independent_sqlite_file_is_not_globally_fenced(tmp_path):
    a=book(tmp_path/"A.sqlite")
    b=book(tmp_path/"B.sqlite")
    a.set_local_synthetic_kill_switch(active=True, operation_id="stop-A")
    assert reserve(b, "other").order_state == "PENDING_SYNTHETIC"
    assert b.inspect().revision == 1
    assert not b.inspect_local_synthetic_risk_state().kill_switch_active


def test_bad_scope_or_missing_risk_table_block_direct_writes(tmp_path):
    path=tmp_path/"same.sqlite"
    a=book(path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE execution_local_risk SET scope_sha=?", ("0"*64,))
    with pytest.raises(Stage55SyntheticBookBlocked, match="kill-switch state|risk state"):
        reserve(a)
    assert a.inspect().revision == 0


def test_local_kill_race_serialization_on_same_sqlite(tmp_path):
    path=tmp_path/"same.sqlite"
    a,b=book(path),book(path)
    # Force stop first, then simulate a separate direct writer with no CAS.
    a.set_local_synthetic_kill_switch(active=True,operation_id="kill")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda n: attempt(b, n), ("a","b")))
    assert results == [False,False]
    assert b.inspect().revision == 0
    assert b.inspect_local_synthetic_risk_state().kill_switch_active


def attempt(b, n):
    try:
        reserve(b, n)
    except Stage55SyntheticBookBlocked:
        return False
    return True


def test_local_kill_state_refuses_invalid_migration_of_old_nonempty_book(tmp_path):
    path=tmp_path/"same.sqlite"
    a=book(path)
    reserve(a)
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM execution_local_risk")
    with pytest.raises(Stage55SyntheticBookBlocked, match="manual migration"):
        book(path)


def test_local_kill_does_not_modify_independent_order_hash_chain(tmp_path):
    b=book(tmp_path/"single.sqlite")
    old=b.inspect()
    b.set_local_synthetic_kill_switch(active=True,operation_id="stop")
    b.set_local_synthetic_kill_switch(active=False,operation_id="restart-test")
    again=b.inspect()
    assert again.revision == old.revision == 0
    assert again.journal_tip == old.journal_tip
    assert again.local_integrity_verified

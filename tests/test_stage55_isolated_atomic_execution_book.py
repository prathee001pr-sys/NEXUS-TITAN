"""Stage55 synthetic single-domain reserve/fill/cancel accounting adversarial suite.

All tests use temporary local SQLite and *fabricated* order/fill evidence.
This is no broker or live trading proof and creates no real financial orders.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from pathlib import Path

import pytest

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook,
    Stage55SyntheticBookBlocked,
    Stage55SyntheticPolicy,
)


def _book(root, *, capital=5_000_000, account="STAGE55-QA",
          policy=None, path=None, excluded=()):
    return Stage55IsolatedSyntheticExecutionBook(
        db_path=path or root / "synthetic_execution.sqlite3",
        account_id=account, starting_cents=capital,
        policy=policy or Stage55SyntheticPolicy(),
        excluded_ledger_paths=excluded,
    )


def _open(book, rid="ORDER-ONE", *, qty=10, price=10_000, fees=1_000, symbol="QA-ABC"):
    return book.reserve_synthetic_buy(
        request_id=rid, symbol=symbol, quantity=qty,
        limit_price_cents=price, fee_buffer_cents=fees,
    )


def _fill(book, oid="ORDER-ONE", fid="FILL-ONE", *, qty=3, price=9_000, fee=100,
          source="LOCAL_SYNTHETIC_TEST_ONLY"):
    return book.record_simulated_fill(
        order_id=oid, fill_id=fid, quantity=qty,
        price_cents=price, fee_cents=fee, evidence_source=source,
    )


def _cancel(book, oid="ORDER-ONE", cid="CANCEL-ONE",
            source="LOCAL_SYNTHETIC_TEST_ONLY"):
    return book.cancel_unfilled(
        order_id=oid, cancel_id=cid, evidence_source=source,
    )


def _deny_authority(status):
    assert status.synthetic_only
    assert not status.real_broker_fill_evidence_verified
    assert not status.existing_virtual_research_books_integrated
    assert not status.cross_database_atomicity_verified
    assert not status.external_human_identity_verified
    assert not status.independently_enforced_risk_veto
    assert not status.real_market_data_authenticated
    assert not status.unbypassable_global_entry
    assert not status.live_trading_enabled
    assert not status.production_ready
    assert status.broker_orders_transmitted == 0


@pytest.mark.parametrize("capital", [1_250_000, 5_000_000, 17_500_000])
def test_initial_variable_capital_is_non_authoritative_and_exact(tmp_path, capital):
    book = _book(tmp_path, capital=capital)
    state = book.inspect()
    assert state.local_integrity_verified
    assert state.initial_cents == capital
    assert state.cash_cents == state.available_cents == capital
    assert state.open_reserved_cents == state.paid_fees_cents == 0
    assert state.paid_notional_cents == 0
    assert state.total_orders == state.revision == 0
    assert state.journal_tip == "0" * 64
    assert not state.blockers
    _deny_authority(state)


def test_one_intent_reserves_without_spending_or_filling(tmp_path):
    book = _book(tmp_path)
    receipt = _open(book)
    assert receipt.event_kind == "OPEN"
    assert receipt.order_state == "PENDING_SYNTHETIC"
    assert receipt.filled_quantity == 0
    assert receipt.cash_cents == 5_000_000
    assert receipt.open_reserved_cents == 101_000
    assert receipt.available_cents == 4_899_000
    assert receipt.revision == 1
    assert not receipt.trading_authority and receipt.synthetic_only
    assert receipt.live_orders_transmitted == 0
    state = book.inspect()
    assert state.total_orders == state.pending_orders == 1
    assert state.partially_filled_orders == state.filled_orders == 0
    assert state.cash_cents == 5_000_000
    assert state.open_reserved_cents == 101_000
    assert state.paid_notional_cents == state.paid_fees_cents == 0
    _deny_authority(state)


def test_partial_fill_conserves_fees_cash_and_remaining_reserve(tmp_path):
    book = _book(tmp_path)
    _open(book)
    receipt = _fill(book)
    assert receipt.event_kind == "FILL"
    assert receipt.order_state == "PARTIAL_SYNTHETIC"
    assert receipt.filled_quantity == 3
    assert receipt.cash_cents == 4_972_900   # spent 3*9000+100
    assert receipt.open_reserved_cents == 70_900  # 7*10000+900 fees left
    assert receipt.available_cents == 4_902_000
    state = book.inspect()
    assert state.partially_filled_orders == 1
    assert state.paid_notional_cents == 27_000
    assert state.paid_fees_cents == 100
    assert state.cash_cents + state.paid_notional_cents + state.paid_fees_cents == 5_000_000
    assert state.open_reserved_cents <= state.cash_cents
    _deny_authority(state)


def test_final_partial_fill_releases_unused_fee_buffer(tmp_path):
    book = _book(tmp_path)
    _open(book)
    _fill(book)
    done = _fill(book, fid="FILL-TWO", qty=7, price=9500, fee=50)
    assert done.order_state == "FILLED_SYNTHETIC"
    assert done.filled_quantity == 10
    assert done.open_reserved_cents == 0
    assert done.cash_cents == 4_906_350
    assert done.available_cents == done.cash_cents
    state = book.inspect()
    assert state.filled_orders == 1
    assert state.paid_fees_cents == 150
    assert state.paid_notional_cents == 93_500
    assert state.paid_notional_cents + state.paid_fees_cents + state.cash_cents == 5_000_000
    with pytest.raises(Stage55SyntheticBookBlocked):
        _fill(book, fid="FILL-THREE", qty=1)
    with pytest.raises(Stage55SyntheticBookBlocked):
        _cancel(book)


def test_cancel_unfilled_intent_releases_held_only_not_spent_cash(tmp_path):
    book = _book(tmp_path)
    _open(book)
    receipt = _cancel(book)
    assert receipt.order_state == "CANCELLED_SYNTHETIC"
    assert receipt.open_reserved_cents == 0
    assert receipt.cash_cents == receipt.available_cents == 5_000_000
    assert book.inspect().cancelled_orders == 1
    with pytest.raises(Stage55SyntheticBookBlocked):
        _cancel(book, cid="CANCEL-OTHER")
    with pytest.raises(Stage55SyntheticBookBlocked):
        _fill(book)


def test_cancel_after_partial_preserves_paid_notional_and_releases_only_remainder(tmp_path):
    book = _book(tmp_path)
    _open(book)
    _fill(book)
    receipt = _cancel(book)
    assert receipt.order_state == "CANCELLED_SYNTHETIC"
    assert receipt.filled_quantity == 3
    assert receipt.cash_cents == 4_972_900
    assert receipt.open_reserved_cents == 0
    assert receipt.available_cents == 4_972_900
    assert book.inspect().paid_notional_cents == 27_000
    assert book.inspect().paid_fees_cents == 100
    assert book.inspect().cancelled_orders == 1


def test_exact_limit_fill_and_fee_reserve_fully_consumed(tmp_path):
    book = _book(tmp_path)
    _open(book, qty=2, price=1000, fees=25)
    receipt = _fill(book, qty=2, price=1000, fee=25)
    assert receipt.order_state == "FILLED_SYNTHETIC"
    assert receipt.cash_cents == 5_000_000 - 2025
    assert receipt.open_reserved_cents == 0
    assert book.inspect().local_integrity_verified


def test_zero_fee_budget_works_if_fill_has_zero_fees(tmp_path):
    book = _book(tmp_path)
    _open(book, qty=1, price=1000, fees=0)
    receipt = _fill(book, qty=1, price=900, fee=0)
    assert receipt.order_state == "FILLED_SYNTHETIC"
    assert receipt.cash_cents == 5_000_000 - 900


@pytest.mark.parametrize("tamper", [
    {"qty": 11}, {"price": 10_001}, {"fee": 1001},
    {"qty": True}, {"qty": 0}, {"price": float("nan")},
    {"fee": -1}, {"source": "BROKER_CONFIRMED"},
])
def test_invalid_simulated_fills_rejected_without_ledger_change(tmp_path, tamper):
    book = _book(tmp_path)
    _open(book)
    initial = book.inspect()
    kwargs = dict(qty=3, price=9000, fee=100)
    kwargs.update(tamper)
    with pytest.raises(Stage55SyntheticBookBlocked):
        _fill(book, **kwargs)
    assert book.inspect() == initial


@pytest.mark.parametrize("bad", [
    {"qty": 0}, {"qty": True}, {"qty": -1}, {"qty": 1.5},
    {"price": 0}, {"price": True}, {"price": 1.75},
    {"fees": -1}, {"fees": None}, {"fees": float("inf")},
    {"symbol": "BANKNIFTY OPT 2026"}, {"symbol": "abc"}, {"symbol": "../ABC"},
])
def test_invalid_open_requests_block_before_any_budget(tmp_path, bad):
    book = _book(tmp_path)
    with pytest.raises(Stage55SyntheticBookBlocked):
        _open(book, **bad)
    assert book.inspect().revision == 0
    assert book.inspect().open_reserved_cents == 0


@pytest.mark.parametrize("rid", ["", "bad space", "../order", "a" * 81, None, True])
def test_invalid_operation_id_never_commits(tmp_path, rid):
    book = _book(tmp_path)
    with pytest.raises(Stage55SyntheticBookBlocked):
        _open(book, rid=rid)
    assert book.inspect().revision == 0


def test_reused_open_id_and_event_id_rejected_even_with_different_payload(tmp_path):
    book = _book(tmp_path)
    _open(book)
    first = book.inspect()
    with pytest.raises(Stage55SyntheticBookBlocked, match="Repeated|Duplicate"):
        _open(book)
    assert book.inspect() == first
    _fill(book)
    after = book.inspect()
    with pytest.raises(Stage55SyntheticBookBlocked):
        _fill(book, qty=1, fid="FILL-ONE")
    with pytest.raises(Stage55SyntheticBookBlocked):
        _cancel(book, cid="FILL-ONE")
    assert book.inspect() == after


def test_per_order_and_aggregate_budget_limits_are_independent(tmp_path):
    book = _book(tmp_path, policy=Stage55SyntheticPolicy(3000, 5000))
    _open(book, rid="BIG-ONE", qty=1, price=1_500_000, fees=0)
    with pytest.raises(Stage55SyntheticBookBlocked, match="reserve|risk cap"):
        _open(book, rid="BIG-TWO", qty=1, price=1_500_000, fees=0)
    assert book.inspect().open_reserved_cents == 1_500_000
    assert book.inspect().total_orders == 1


def test_per_order_cap_alone_blocks_and_leaves_journal_empty(tmp_path):
    book = _book(tmp_path)
    with pytest.raises(Stage55SyntheticBookBlocked, match="reserve|risk cap"):
        _open(book, qty=1, price=1_000_001, fees=0)
    assert book.inspect().revision == 0


def test_same_db_concurrent_reserves_cannot_exceed_aggregate_cap(tmp_path):
    policy = Stage55SyntheticPolicy(3000, 5000)
    a = _book(tmp_path, policy=policy)
    b = _book(tmp_path, policy=policy)

    def worker(book, rid):
        try:
            return _open(book, rid=rid, qty=1, price=1_500_000, fees=0)
        except Stage55SyntheticBookBlocked as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(worker, a, "CONCURRENT-A")
        fb = pool.submit(worker, b, "CONCURRENT-B")
        results = [fa.result(), fb.result()]
    succeeded = [x for x in results if not isinstance(x, str)]
    assert len(succeeded) == 1, results
    assert len(results) - len(succeeded) == 1
    assert a.inspect().total_orders == 1
    assert a.inspect().open_reserved_cents == 1_500_000


def test_two_concurrent_small_orders_both_have_serial_event_revisions(tmp_path):
    a = _book(tmp_path)
    b = _book(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        x = pool.submit(_open, a, rid="SMALL-A", qty=1, price=1000, fees=10)
        y = pool.submit(_open, b, rid="SMALL-B", qty=1, price=1200, fees=10)
        results = [x.result(), y.result()]
    assert sorted(r.revision for r in results) == [1, 2]
    assert a.inspect().open_reserved_cents == 2220
    assert a.inspect().revision == 2
    assert a.inspect().total_orders == 2


def test_restart_reconstructs_orders_spend_and_unique_ids(tmp_path):
    b = _book(tmp_path)
    _open(b)
    _fill(b)
    st = b.inspect()
    reopened = _book(tmp_path)
    assert reopened.inspect() == st
    with pytest.raises(Stage55SyntheticBookBlocked):
        _fill(reopened, fid="FILL-ONE")
    done = _cancel(reopened)
    assert done.order_state == "CANCELLED_SYNTHETIC"
    assert _book(tmp_path).inspect().open_reserved_cents == 0


def test_injected_exception_after_event_write_rolls_back_entire_tx(tmp_path, monkeypatch):
    book = _book(tmp_path)
    before = book.inspect()
    original = book._write_event

    def fail_after_insert(conn, core, hashed):
        original(conn, core, hashed)
        raise RuntimeError("qa power loss after event insert")

    monkeypatch.setattr(book, "_write_event", fail_after_insert)
    with pytest.raises(RuntimeError, match="power loss"):
        _open(book)
    assert book.inspect() == before
    assert _book(tmp_path).inspect() == before
    with sqlite3.connect(tmp_path / "synthetic_execution.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM execution_events").fetchone()[0] == 0


def test_injected_exception_before_head_commit_rolls_back(tmp_path, monkeypatch):
    book = _book(tmp_path)
    before = book.inspect()

    def fail_before_record(conn, core, hashed):
        raise RuntimeError("synthetic failure before event commit")

    monkeypatch.setattr(book, "_write_event", fail_before_record)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        _open(book)
    assert book.inspect() == before


@pytest.mark.parametrize("sql", [
    "UPDATE execution_head SET reserved_cents=reserved_cents+1",
    "UPDATE execution_head SET cash_cents=cash_cents-1",
    "UPDATE execution_head SET event_sha='bad'",
    "UPDATE execution_head SET revision=revision+1",
    "UPDATE execution_events SET price_cents=price_cents+1 WHERE seq=1",
    "UPDATE execution_events SET previous_sha='bad' WHERE seq=1",
    "UPDATE execution_events SET event_sha='bad' WHERE seq=1",
    "DELETE FROM execution_events WHERE seq=1",
])
def test_detects_sqlite_head_or_journal_tampering_and_refuses_new_holds(tmp_path, sql):
    book = _book(tmp_path)
    _open(book)
    with sqlite3.connect(tmp_path / "synthetic_execution.sqlite3") as db:
        db.execute(sql)
    status = book.inspect()
    assert not status.local_integrity_verified
    assert status.cash_cents is None
    assert status.available_cents is None
    assert status.blockers
    _deny_authority(status)
    with pytest.raises(Stage55SyntheticBookBlocked):
        _open(book, rid="NEW-OTHER")


def test_head_removed_with_events_is_not_reinitialized(tmp_path):
    book = _book(tmp_path)
    _open(book)
    with sqlite3.connect(tmp_path / "synthetic_execution.sqlite3") as db:
        db.execute("DELETE FROM execution_head")
    assert not book.inspect().local_integrity_verified
    with pytest.raises(Stage55SyntheticBookBlocked, match="Missing head"):
        _book(tmp_path)


def test_changed_account_capital_policy_or_existing_db_alias_is_denied(tmp_path):
    _book(tmp_path)
    with pytest.raises(Stage55SyntheticBookBlocked):
        _book(tmp_path, account="OTHER")
    with pytest.raises(Stage55SyntheticBookBlocked):
        _book(tmp_path, capital=6_000_000)
    with pytest.raises(Stage55SyntheticBookBlocked):
        _book(tmp_path, policy=Stage55SyntheticPolicy(1000, 5000))
    target = tmp_path / "other.sqlite3"
    with pytest.raises(Stage55SyntheticBookBlocked, match="reuse"):
        _book(tmp_path, path=target, excluded=(target,))


def test_symlink_db_path_denied(tmp_path):
    real = tmp_path / "synthetic_execution.sqlite3"
    _book(tmp_path)
    alias = tmp_path / "alias.sqlite3"
    try:
        alias.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable on this runner")
    with pytest.raises(Stage55SyntheticBookBlocked, match="unsafe"):
        _book(tmp_path, path=alias)


def test_policy_rejects_bad_caps_and_bool_values():
    for value in (False, True, None, -1, 0, 10001, "2000", 20.5):
        with pytest.raises(Stage55SyntheticBookBlocked):
            Stage55SyntheticPolicy(max_single_reserve_bps=value)
    with pytest.raises(Stage55SyntheticBookBlocked):
        Stage55SyntheticPolicy(max_single_reserve_bps=6000, max_open_reserve_bps=5000)


def test_explicit_synthetic_fill_source_required(tmp_path):
    book = _book(tmp_path)
    _open(book)
    with pytest.raises(Stage55SyntheticBookBlocked, match="synthetic"):
        _fill(book, source="EXCHANGE_REAL")
    with pytest.raises(Stage55SyntheticBookBlocked, match="synthetic"):
        _cancel(book, source="REAL_BROKER")
    assert book.inspect().revision == 1


def test_no_api_to_bypass_into_real_orders_or_global_books(tmp_path):
    book = _book(tmp_path)
    for name in ("submit_order", "approve_order", "execute_fill",
                 "connect_broker", "transmit_real_order", "sync_virtual",
                 "merge_research_books", "emergency_square_off"):
        assert not hasattr(book, name)
    st = book.inspect()
    assert not st.existing_virtual_research_books_integrated
    _deny_authority(st)


def test_smoke_script_synthetic_and_no_live_money():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_stage55_atomic_book_smoke.py")],
        cwd=root, capture_output=True, text=True, check=False, timeout=30,
    )
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    assert data["mode"] == "STAGE55_ISOLATED_SYNTHETIC_SINGLE_DB_ONLY"
    assert data["initial_cents"] == 5_000_000
    assert data["before"]["open_reserved_cents"] == 101_000
    assert data["after_partial"]["paid_notional_cents"] == 27_000
    assert data["after_cancel"]["open_reserved_cents"] == 0
    assert data["after_cancel"]["cash_cents"] == 4_972_900
    assert data["restart_consistency_verified"] is True
    assert data["after_cancel"]["cross_database_atomicity_verified"] is False
    assert data["after_cancel"]["live_trading_enabled"] is False
    assert data["after_cancel"]["broker_orders_transmitted"] == 0

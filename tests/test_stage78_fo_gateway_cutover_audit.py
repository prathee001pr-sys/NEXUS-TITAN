"""Stage78 static cutover and Stage55 synthetic SQLite concurrency QA."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import shutil
import sqlite3
from pathlib import Path
from threading import Barrier

import pytest

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook,
    Stage55SyntheticBookBlocked,
    Stage55SyntheticPolicy,
)
from nexus_titan.operations.risk_boundary_inventory import _KNOWN_DIRECT_SURFACES
from nexus_titan.operations.stage70_fo_integration_gate import _SOURCE_PATHS
from nexus_titan.operations.stage78_fo_gateway_cutover_audit import (
    Stage78CutoverBlocked, inspect_stage78_fo_cutover,
)

ROOT = Path(__file__).resolve().parents[1]
STAGE77 = "src/nexus_titan/operations/stage77_brokerless_fo_sandbox.py"


def source_tree(tmp_path):
    for path in sorted(set(_KNOWN_DIRECT_SURFACES) | set(_SOURCE_PATHS) | {STAGE77}):
        dst = tmp_path / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, dst)
    return tmp_path


def test_current_cutover_inventory_is_explicit_no_go():
    audit = inspect_stage78_fo_cutover(ROOT)
    assert audit.local_source_inventory_complete
    assert audit.local_stage77_expected_calls_observed
    assert audit.inspected_legacy_source_files >= 6
    assert audit.inspected_stage70_source_files == 5
    assert audit.observed_legacy_method_count >= 12
    assert "VirtualAccount.execute_fill" in audit.observed_legacy_direct_methods
    assert "Stage55IsolatedSyntheticExecutionBook.reserve_synthetic_buy" in audit.observed_legacy_direct_methods
    assert len(audit.stage77_gateway_methods) == 3
    assert len(audit.stage77_statically_observed_local_call_pairs) == 3
    assert len(audit.stage77_source_sha256) == 64
    assert len(audit.source_inventory_sha256) == 64
    assert len(audit.release_blockers) >= 8
    assert audit.verdict.endswith("NO_GO")
    assert audit == inspect_stage78_fo_cutover(ROOT)
    for field in (
        "independent_global_risk_gateway_verified",
        "all_legacy_order_fill_paths_fenced",
        "stage55_direct_ledger_writes_disabled",
        "atomically_authored_risk_and_funds_verified",
        "independently_verified_risk_telemetry",
        "restart_with_pending_orders_recovered",
        "authorized_real_market_shadow_trading",
        "owner_merge_approval_verified",
        "live_trading_enabled",
    ):
        assert getattr(audit, field) is False
    assert audit.broker_orders_transmitted == 0


def test_static_inventory_survives_safe_fixture_copy(tmp_path):
    copied = source_tree(tmp_path)
    assert inspect_stage78_fo_cutover(copied) == inspect_stage78_fo_cutover(ROOT)


def test_changed_gateway_risk_precheck_fails_closed_even_with_comment_spoof(tmp_path):
    copied = source_tree(tmp_path)
    file = copied / STAGE77
    original = file.read_text(encoding="utf-8")
    assert "review = self._review(telemetry)" in original
    file.write_text(
        original.replace("review = self._review(telemetry)",
                         "review = self._unverified_review(telemetry)", 1)
        + "\n# review = self._review(telemetry)\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage78CutoverBlocked, match="precheck/book ordering"):
        inspect_stage78_fo_cutover(copied)


def test_changed_book_call_fails_closed_even_with_comment_spoof(tmp_path):
    copied = source_tree(tmp_path)
    file = copied / STAGE77
    original = file.read_text(encoding="utf-8")
    assert "self._book.reserve_synthetic_buy(" in original
    file.write_text(
        original.replace("self._book.reserve_synthetic_buy(",
                         "self._book.fake_reserve_synthetic_buy(", 1)
        + "\n# self._book.reserve_synthetic_buy(\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage78CutoverBlocked, match="precheck/book ordering"):
        inspect_stage78_fo_cutover(copied)


def test_missing_source_and_symlink_not_mistaken_for_global_fence(tmp_path):
    copied = source_tree(tmp_path)
    target = copied / STAGE77
    target.unlink()
    with pytest.raises(Stage78CutoverBlocked, match="Missing"):
        inspect_stage78_fo_cutover(copied)
    target.symlink_to(ROOT / STAGE77)
    with pytest.raises(Stage78CutoverBlocked, match="Symlinked"):
        inspect_stage78_fo_cutover(copied)


def test_renamed_legacy_order_method_is_unknown_not_authorization(tmp_path):
    copied = source_tree(tmp_path)
    source = copied / "src/nexus_titan/virtual/order_manager.py"
    original = source.read_text(encoding="utf-8")
    assert "def execute_fill(" in original
    source.write_text(original.replace("def execute_fill(", "def execute_fill_renamed(", 1))
    with pytest.raises(Stage78CutoverBlocked, match="Stage70|Stage56"):
        inspect_stage78_fo_cutover(copied)


def book(path, *, starting=1_000_000, policy=None):
    return Stage55IsolatedSyntheticExecutionBook(
        db_path=path, account_id="stage78-sandbox",
        starting_cents=starting, policy=policy or Stage55SyntheticPolicy(),
    )


def simultaneous(call_a, call_b):
    barrier = Barrier(2)
    def go(fn):
        barrier.wait(timeout=10)
        try:
            return "accepted", fn()
        except Stage55SyntheticBookBlocked:
            return "denied", None
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(go, call_a)
        b = pool.submit(go, call_b)
        return a.result(timeout=20), b.result(timeout=20)


def test_two_SQLite_instances_same_db_duplicate_order_race_is_idempotent(tmp_path):
    path = tmp_path / "shared.db"
    b1, b2 = book(path), book(path)
    def open_one(b):
        return lambda: b.reserve_synthetic_buy(
            request_id="same-order", symbol="NIFTYOPT", quantity=5,
            limit_price_cents=5000, fee_buffer_cents=500,
        )
    result = simultaneous(open_one(b1), open_one(b2))
    assert sorted(x[0] for x in result) == ["accepted", "denied"]
    status = book(path).inspect()
    assert status.local_integrity_verified
    assert status.revision == 1
    assert status.open_reserved_cents == 25_500
    assert status.available_cents == 1_000_000-25_500
    assert status.total_orders == 1


def test_shared_SQLite_aggregate_cap_blocks_two_different_order_race(tmp_path):
    path = tmp_path / "shared.db"
    policy = Stage55SyntheticPolicy(
        max_single_reserve_bps=4000, max_open_reserve_bps=5000,
    )
    b1, b2 = book(path, policy=policy), book(path, policy=policy)
    def submit(b, order):
        return lambda: b.reserve_synthetic_buy(
            request_id=order, symbol="NIFTYOPT", quantity=5,
            limit_price_cents=60_000, fee_buffer_cents=0,
        )
    result = simultaneous(submit(b1, "order-a"), submit(b2, "order-b"))
    assert sorted(x[0] for x in result) == ["accepted", "denied"]
    status = book(path, policy=policy).inspect()
    assert status.local_integrity_verified
    assert status.open_reserved_cents == 300_000
    assert status.revision == 1


def test_same_SQLite_fill_vs_cancel_race_serializes_either_winner(tmp_path):
    path = tmp_path / "shared.db"
    b1, b2 = book(path), book(path)
    b1.reserve_synthetic_buy(
        request_id="order-one", symbol="NIFTYOPT", quantity=5,
        limit_price_cents=5000, fee_buffer_cents=500,
    )
    result = simultaneous(
        lambda: b1.record_simulated_fill(
            order_id="order-one", fill_id="fill-one", quantity=5,
            price_cents=4900, fee_cents=50,
            evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
        ),
        lambda: b2.cancel_unfilled(
            order_id="order-one", cancel_id="cancel-one",
            evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
        ),
    )
    assert sorted(x[0] for x in result) == ["accepted", "denied"]
    status = book(path).inspect()
    assert status.local_integrity_verified
    assert status.revision == 2
    assert status.open_reserved_cents == 0
    assert status.filled_orders + status.cancelled_orders == 1
    if status.filled_orders:
        assert status.cash_cents == 1_000_000-(5*4900+50)
    else:
        assert status.cash_cents == 1_000_000


def test_injected_precommit_crash_rolls_back_entire_synthetic_event(tmp_path, monkeypatch):
    path = tmp_path / "shared.db"
    b = book(path)
    original = b._write_event

    def crash_after_write(conn, core, hashed):
        original(conn, core, hashed)
        raise RuntimeError("simulated process death before COMMIT")

    monkeypatch.setattr(b, "_write_event", crash_after_write)
    with pytest.raises(RuntimeError, match="before COMMIT"):
        b.reserve_synthetic_buy(
            request_id="crash-order", symbol="NIFTYOPT",
            quantity=5, limit_price_cents=5000, fee_buffer_cents=0,
        )
    reopened = book(path).inspect()
    assert reopened.local_integrity_verified
    assert reopened.revision == 0
    assert reopened.cash_cents == 1_000_000
    assert reopened.open_reserved_cents == 0


def test_identical_account_two_independent_sqlite_files_have_no_global_exclusivity(tmp_path):
    """This is deliberately a NEGATIVE test for global authority claims."""
    first = book(tmp_path / "account-book-A.db")
    second = book(tmp_path / "account-book-B.db")
    for b, request in ((first, "one"), (second, "two")):
        b.reserve_synthetic_buy(
            request_id=request, symbol="NIFTYOPT",
            quantity=5, limit_price_cents=30_000, fee_buffer_cents=0,
        )
    assert first.inspect().open_reserved_cents == 150_000
    assert second.inspect().open_reserved_cents == 150_000
    # The two books independently reserve the *same declared* starting cash.
    # Therefore no cross-file/legacy atomic capital authority is proven.
    assert first.inspect().revision == second.inspect().revision == 1


def test_stage78_cutover_smoke_explicitly_never_approves_trading():
    import json
    import subprocess
    import sys
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage78_fo_cutover_audit.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["local_source_inventory_complete"] is True
    assert report["all_legacy_order_fill_paths_fenced"] is False
    assert report["independent_global_risk_gateway_verified"] is False
    assert report["broker_orders_transmitted"] == 0
    assert report["verdict"].endswith("NO_GO")

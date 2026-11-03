"""Stage49 synthetic capital-fence regression tests (all offline, brokerless)."""
from __future__ import annotations

import json
import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nexus_titan.core.security_gates import CryptographicApprovalVerifier
from nexus_titan.operations.durable_paper_fence import (
    Stage49AdmissionBlocked, Stage49DurablePaperFence,
)
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import (
    open_stage48_signed_paper_session,
)
from nexus_titan.virtual.order_manager import OrderState


def _config(root: Path, *, capital=50000, account="STAGE49-LOCAL", enabled=True):
    return PaperDeploymentConfig(
        account_id=account, starting_capital=capital,
        virtual_state_dir=root / "virtual",
        research_db_path=root / "research.sqlite3",
        paper_orders_enabled=enabled,
    )


def _new(root, *, capital=50000, db_path=None, account="STAGE49-LOCAL", enabled=True):
    verifier = CryptographicApprovalVerifier(
        secret_key=secrets.token_urlsafe(32), db_path=root / "replay.sqlite3",
    )
    session = open_stage48_signed_paper_session(
        _config(root, capital=capital, account=account, enabled=enabled),
        verifier=verifier,
    )
    fence = Stage49DurablePaperFence(
        session, db_path=db_path or (root / "coordinator.sqlite3"),
    )
    return session, fence


def _quote(**kwargs):
    quote = SyntheticQuoteEvidence(
        observed_at=datetime.now(timezone.utc), bid=99.95, ask=100.0,
        displayed_ask_quantity=50, expected_edge_bps=42, slippage_bps=2,
    )
    return replace(quote, **kwargs)


def _proposal(**kwargs):
    return replace(SyntheticBuyProposal(
        symbol="QA-ABC", quantity=1, stop_price=95,
    ), **kwargs)


def _request(fence, *, rid="BUY-ONE", quote=None, proposal=None):
    return fence.request_first_synthetic_buy(
        request_id=rid, proposal=proposal or _proposal(),
        quote=quote or _quote(),
    )


@pytest.mark.parametrize("capital", [12500, 50000, 75000])
def test_one_new_synthetic_buy_per_coordinator_lifetime(tmp_path, capital):
    session, fence = _new(tmp_path, capital=capital)
    before = fence.inspect()
    assert before.can_request_first_synthetic_buy
    assert before.starting_cash_cents == capital * 100
    assert before.virtual_cash_cents == before.research_cash_cents == capital * 100
    order = _request(fence)
    assert order.status == "PENDING_APPROVAL"
    assert order.requires_manual_approval
    assert order.live_orders_transmitted == 0
    assert session._deployment.virtual_account.orders[order.order_id].state is OrderState.PENDING_APPROVAL
    assert not session._deployment.virtual_account.orders[order.order_id].fills
    after = fence.inspect()
    assert after.attempt_count == 1
    assert after.latest_attempt_state == "PENDING"
    assert not after.can_request_first_synthetic_buy
    assert not after.global_legacy_entrypoints_fenced
    assert not after.cross_ledger_atomicity_verified
    assert not after.one_unified_cash_authority_verified
    assert not after.independent_external_identity_verified
    assert not after.licensed_real_market_data_verified
    assert after.broker_orders_transmitted == 0
    assert not after.production_ready


def test_identical_request_id_is_never_replayed(tmp_path):
    session, fence = _new(tmp_path)
    _request(fence)
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence)
    assert len(session._deployment.virtual_account.orders) == 1


def test_different_request_id_still_cannot_create_second_order(tmp_path):
    session, fence = _new(tmp_path)
    _request(fence)
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence, rid="BUY-TWO")
    assert len(session._deployment.virtual_account.orders) == 1


def test_fence_cannot_turn_an_unapproved_order_into_fill(tmp_path):
    session, fence = _new(tmp_path)
    intent = _request(fence)
    assert session._deployment.virtual_account.cash_balance == 50000
    assert session._deployment.virtual_account.orders[intent.order_id].approval is None
    assert session._deployment.virtual_account.orders[intent.order_id].filled_qty == 0
    assert not session._deployment.virtual_account.positions


def test_signed_approval_remains_separate_and_does_not_clear_durable_fence(tmp_path):
    session, fence = _new(tmp_path)
    intent = _request(fence)
    challenge = session.pending_challenge(intent.order_id)
    token = session._verifier.issue_token(
        token_id="QA-49-ONE", actor="QA-HUMAN-DEMO",
        role="PROJECT_OWNER", target_entity_id=challenge.target_entity_id,
        snapshot_hash=challenge.snapshot_hash, ttl_seconds=30,
    )
    order = session.approve_pending_buy(order_id=intent.order_id, token=token)
    assert order.state is OrderState.ACCEPTED
    assert order.filled_qty == 0
    assert fence.inspect().latest_attempt_state == "PENDING"
    assert not fence.inspect().can_request_first_synthetic_buy


def test_after_restart_fence_persists_and_new_session_cannot_repeat(tmp_path):
    session, fence = _new(tmp_path)
    intent = _request(fence)
    second_verifier = CryptographicApprovalVerifier(
        secret_key=secrets.token_urlsafe(32),
        db_path=tmp_path / "replay.sqlite3",
    )
    reopened = open_stage48_signed_paper_session(
        _config(tmp_path), verifier=second_verifier,
    )
    reopened_fence = Stage49DurablePaperFence(
        reopened, db_path=tmp_path / "coordinator.sqlite3",
    )
    state = reopened_fence.inspect()
    assert state.attempt_count == 1
    assert state.latest_attempt_state == "PENDING"
    assert not state.can_request_first_synthetic_buy
    with pytest.raises(Stage49AdmissionBlocked):
        _request(reopened_fence, rid="AFTER-RESTART")
    assert reopened._deployment.virtual_account.orders[intent.order_id].state is OrderState.PENDING_APPROVAL


def test_coordinators_on_shared_sqlite_path_serialize_concurrent_requests(tmp_path):
    session, first = _new(tmp_path)
    second = Stage49DurablePaperFence(
        session, db_path=tmp_path / "coordinator.sqlite3",
    )
    q = _quote()

    def run_one(rid, gateway):
        try:
            return gateway.request_first_synthetic_buy(
                request_id=rid, proposal=_proposal(), quote=q,
            )
        except Stage49AdmissionBlocked as e:
            return str(e)

    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [
            pool.submit(run_one, "THREAD-A", first),
            pool.submit(run_one, "THREAD-B", second),
        ]
        results = [f.result() for f in calls]
    successes = [x for x in results if not isinstance(x, str)]
    denials = [x for x in results if isinstance(x, str)]
    assert len(successes) == 1
    assert len(denials) == 1
    assert first.inspect().attempt_count == 1
    assert len(session._deployment.virtual_account.orders) == 1


def test_committed_preparing_marker_survives_simulated_crash(tmp_path):
    session, fence = _new(tmp_path)
    # Directly emulate a subprocess terminated after its marker commit
    # but before writing any VirtualAccount order. Do not retry implicitly.
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute(
            "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("CRASH-OUTCOME", "STAGE49-LOCAL", "PREPARING", 10000,
             "0" * 64, 0, None, datetime.now(timezone.utc).isoformat()),
        )
    report = fence.inspect()
    assert report.attempt_count == 1
    assert report.latest_attempt_state == "PREPARING"
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence, rid="RETRY-CRASH")
    assert not session._deployment.virtual_account.orders


def test_underlying_gateway_error_after_marker_freezes_unknown_outcome(tmp_path, monkeypatch):
    session, fence = _new(tmp_path)
    orig = session.request_synthetic_buy

    def succeeds_then_crashes(*args, **kwargs):
        orig(*args, **kwargs)  # Commit Stage43 virtual order first.
        raise RuntimeError("synthetic crash immediately after account commit")

    monkeypatch.setattr(session, "request_synthetic_buy", succeeds_then_crashes)
    with pytest.raises(Stage49AdmissionBlocked, match="uncertain"):
        _request(fence)
    assert len(session._deployment.virtual_account.orders) == 1
    record = fence.inspect()
    assert record.attempt_count == 1
    assert record.latest_attempt_state == "UNKNOWN"
    assert not record.can_request_first_synthetic_buy
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence, rid="ANOTHER")


def test_failure_before_account_write_remains_frozen_unknown(tmp_path, monkeypatch):
    session, fence = _new(tmp_path)

    def declines(*args, **kwargs):
        raise RuntimeError("simulated service loss")

    monkeypatch.setattr(session, "request_synthetic_buy", declines)
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence)
    assert fence.inspect().latest_attempt_state == "UNKNOWN"
    assert not session._deployment.virtual_account.orders


@pytest.mark.parametrize("bad", ["", "../xyz", "re play", "\x00", "!" * 81, None, True])
def test_bad_request_id_is_denied_before_coordinator_mutation(tmp_path, bad):
    session, fence = _new(tmp_path)
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence, rid=bad)
    assert fence.inspect().attempt_count == 0
    assert not session._deployment.virtual_account.orders


@pytest.mark.parametrize("ask", [float("inf"), float("nan"), -1, 0, 100.0001, True])
def test_invalid_notional_cannot_hold_slot_or_submit_order(tmp_path, ask):
    session, fence = _new(tmp_path)
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence, quote=_quote(ask=ask))
    assert fence.inspect().attempt_count == 0
    assert not session._deployment.virtual_account.orders


def test_oversized_notional_rejected_before_marker(tmp_path):
    session, fence = _new(tmp_path, capital=500)
    with pytest.raises(Stage49AdmissionBlocked, match="exceeds starting"):
        _request(fence, proposal=_proposal(quantity=200))
    assert fence.inspect().attempt_count == 0


@pytest.mark.parametrize("bad_quote", [
    {"bid": 60}, {"expected_edge_bps": 1},
    {"displayed_ask_quantity": 0},
])
def test_failed_stage47_veto_never_creates_marker_or_order(tmp_path, bad_quote):
    session, fence = _new(tmp_path)
    with pytest.raises(Stage49AdmissionBlocked, match="Stage47"):
        _request(fence, quote=_quote(**bad_quote))
    assert fence.inspect().attempt_count == 0
    assert not session._deployment.virtual_account.orders


def test_separate_ledgers_cash_drift_blocks_admission(tmp_path):
    session, fence = _new(tmp_path)
    session._deployment.virtual_account.cash_balance = 49999.99
    status = fence.inspect()
    assert not status.separate_ledgers_currently_flat
    assert not status.can_request_first_synthetic_buy
    assert status.virtual_cash_cents != status.research_cash_cents
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence)
    assert fence.inspect().attempt_count == 0


def test_manual_capital_adjustment_is_not_silently_reconciled(tmp_path):
    session, fence = _new(tmp_path)
    # Changes in only one account are incompatible with virgin/flat Stage45.
    session._deployment.virtual_account.adjust_capital(100, "TOP_UP", reason="test", user_confirmed=True)
    assert not fence.inspect().can_request_first_synthetic_buy
    assert fence.inspect().attempt_count == 0


def test_read_only_inspection_does_not_create_paper_orders_or_change_revision(tmp_path):
    session, fence = _new(tmp_path)
    rev = session._deployment.virtual_account._snapshot_revision
    a = fence.inspect()
    b = fence.inspect()
    assert a == b
    assert a.can_request_first_synthetic_buy
    assert session._deployment.virtual_account._snapshot_revision == rev
    assert not session._deployment.virtual_account.orders


def test_corrupted_scope_fails_closed_on_read_and_admission(tmp_path):
    session, fence = _new(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute("UPDATE coordinator_scope SET scope_hash=?", ("0" * 64,))
    assert not fence.inspect().coordinator_bound
    assert not fence.inspect().can_request_first_synthetic_buy
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence)


def test_coordinator_path_cannot_alias_virtual_research_or_replay(tmp_path):
    session, fence = _new(tmp_path)
    cfg = session._deployment.config
    for other in [
        cfg.virtual_state_dir / f"{cfg.account_id}_durable.db",
        cfg.research_db_path,
        session._verifier.db_path,
    ]:
        with pytest.raises(Stage49AdmissionBlocked, match="independent"):
            Stage49DurablePaperFence(session, db_path=other)


def test_coordinator_symlink_rejected(tmp_path):
    session, fence = _new(tmp_path)
    alias = tmp_path / "alias.sqlite3"
    alias.symlink_to(tmp_path / "coordinator.sqlite3")
    with pytest.raises(Stage49AdmissionBlocked, match="symlinks"):
        Stage49DurablePaperFence(session, db_path=alias)


def test_scope_cannot_be_rebound_to_second_virtual_account(tmp_path):
    session, fence = _new(tmp_path / "one", db_path=tmp_path / "shared.sqlite3")
    other_session, _ = _new(tmp_path / "two")
    with pytest.raises(Stage49AdmissionBlocked):
        Stage49DurablePaperFence(
            other_session, db_path=tmp_path / "shared.sqlite3",
        )
    assert fence.inspect().can_request_first_synthetic_buy


def test_default_disabled_paper_session_is_read_only(tmp_path):
    session, fence = _new(tmp_path, enabled=False)
    assert not fence.inspect().can_request_first_synthetic_buy
    with pytest.raises(Stage49AdmissionBlocked):
        _request(fence)
    assert not session._deployment.virtual_account.orders


def test_stage49_cli_synthetic_smoke_has_no_broker_or_hidden_fills():
    import subprocess
    import sys
    repo = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [sys.executable, str(repo / "scripts" / "run_stage49_paper_fence_smoke.py")],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["first_request_pending"]
    assert report["duplicate_request_blocked"]
    assert report["restart_reentry_blocked"]
    assert report["coordinator_attempt_count"] == 1
    assert report["broker_orders_transmitted"] == 0
    assert report["virtual_fills"] == 0
    assert not report["cross_ledger_atomicity_verified"]
    assert not report["production_ready"]

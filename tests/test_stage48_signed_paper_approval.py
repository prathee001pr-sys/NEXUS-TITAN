"""Stage48: signed, single-use synthetic BUY approval tests.

All accounts, keys and quotes are ephemeral local QA fixtures. They do NOT
establish independently verified human identity, broker or exchange readiness.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import secrets
import sqlite3
import time

import pytest

from nexus_titan.core.security_gates import (
    CryptographicApprovalVerifier, SignedApprovalToken,
)
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import (
    Stage48ApprovalBlocked, open_stage48_signed_paper_session,
)
from nexus_titan.virtual.order_manager import OrderState


def _config(root, *, enabled=True, account="S48-SYNTHETIC", capital=50000):
    return PaperDeploymentConfig(
        account_id=account,
        starting_capital=capital,
        virtual_state_dir=root / "virtual",
        research_db_path=root / "research.sqlite3",
        paper_orders_enabled=enabled,
    )


def _verifier(root):
    return CryptographicApprovalVerifier(
        secret_key=secrets.token_urlsafe(32),
        db_path=root / "approval-replay.sqlite3",
    )


def _open(root, *, verifier=None, enabled=True):
    verified = verifier or _verifier(root)
    session = open_stage48_signed_paper_session(
        _config(root, enabled=enabled), verifier=verified,
    )
    return session, verified


def _quote(**kw):
    return SyntheticQuoteEvidence(
        observed_at=datetime.now(timezone.utc),
        bid=99.95, ask=100, displayed_ask_quantity=100,
        expected_edge_bps=40, slippage_bps=3, **kw,
    )


def _buy(session, symbol="ABC"):
    result = session.request_synthetic_buy(
        SyntheticBuyProposal(symbol=symbol, quantity=1, stop_price=95),
        _quote(),
    )
    assert result.status == "PENDING_APPROVAL"
    return result.order_id


def _token(verifier, challenge, *, token_id="TEST-TOKEN-1", actor="DEMO-OWNER", role="PROJECT_OWNER", **kw):
    return verifier.issue_token(
        token_id=token_id, actor=actor, role=role,
        target_entity_id=challenge.target_entity_id,
        snapshot_hash=challenge.snapshot_hash,
        ttl_seconds=30, **kw,
    )


@pytest.mark.parametrize("capital", [12500, 50000, 75000])
def test_valid_one_use_signed_buy_becomes_accepted_but_never_filled(tmp_path, capital):
    cfg = _config(tmp_path, capital=capital)
    verifier = _verifier(tmp_path)
    session = open_stage48_signed_paper_session(cfg, verifier=verifier)
    order_id = _buy(session)
    challenge = session.pending_challenge(order_id)
    assert challenge.order_state == "PENDING_APPROVAL"
    assert not challenge.external_identity_verified
    assert not challenge.independently_enforced_authority
    signed = _token(verifier, challenge)
    order = session.approve_pending_buy(order_id=order_id, token=signed)
    assert order.state is OrderState.ACCEPTED
    assert order.approval.actor == "DEMO-OWNER"
    assert order.approval.order_snapshot_hash == order.compute_snapshot_hash()
    assert not order.fills
    assert order.filled_qty == 0
    assert session._deployment.virtual_account.cash_balance == capital
    assert session.status().production_ready is False
    assert session.status().independently_authenticated_human_identity is False
    assert session.status().signer_key_isolated_in_external_service is False
    assert session.status().globally_mandatory_legacy_api_enforcement is False
    assert session.status().cross_ledger_atomicity_verified is False


def test_plain_approval_without_signed_window_fails_closed(tmp_path):
    session, verifier = _open(tmp_path)
    order_id = _buy(session)
    v = session._deployment.virtual_account
    with pytest.raises(PermissionError, match="rejected"):
        v.approve_order(order_id, "DEMO-OWNER")
    assert v.orders[order_id].state is OrderState.PENDING_APPROVAL
    challenge = session.pending_challenge(order_id)
    token = _token(verifier, challenge)
    assert session.approve_pending_buy(order_id=order_id, token=token).state is OrderState.ACCEPTED


def test_default_read_only_session_creates_no_order(tmp_path):
    session, _ = _open(tmp_path, enabled=False)
    assert not session.status().session_paper_orders_enabled
    with pytest.raises(PermissionError):
        _buy(session)
    assert not session._deployment.virtual_account.orders


def test_mutated_order_cannot_reuse_old_signed_challenge(tmp_path):
    session, verifier = _open(tmp_path)
    order_id = _buy(session)
    challenge = session.pending_challenge(order_id)
    token = _token(verifier, challenge)
    order = session._deployment.virtual_account.orders[order_id]
    order.quantity += 1
    with pytest.raises((Stage48ApprovalBlocked, PermissionError)):
        session.approve_pending_buy(order_id=order_id, token=token)
    assert order.state is OrderState.PENDING_APPROVAL
    assert order.approval is None


def test_policy_drift_blocks_even_reissued_token(tmp_path):
    session, verifier = _open(tmp_path)
    order_id = _buy(session)
    c = session.pending_challenge(order_id)
    signed = _token(verifier, c)
    v = session._deployment.virtual_account
    v.risk_per_trade_pct = 40
    with pytest.raises(Stage48ApprovalBlocked):
        session.approve_pending_buy(order_id=order_id, token=signed)
    with pytest.raises(Stage48ApprovalBlocked):
        session.pending_challenge(order_id)
    assert v.orders[order_id].approval is None


def test_kill_switch_blocks_issued_signed_approval(tmp_path):
    session, verifier = _open(tmp_path)
    order_id = _buy(session)
    signed = _token(verifier, session.pending_challenge(order_id))
    session._deployment.virtual_account.activate_emergency_kill_switch("S48 QA kill")
    with pytest.raises(Stage48ApprovalBlocked):
        session.approve_pending_buy(order_id=order_id, token=signed)
    assert session._deployment.virtual_account.orders[order_id].approval is None


def test_wrong_order_token_is_refused_without_mutation(tmp_path):
    session, verifier = _open(tmp_path)
    a = _buy(session)
    session._deployment.virtual_account.cancel_order(a)
    b = _buy(session, symbol="XYZ")
    token = _token(verifier, session.pending_challenge(b))
    with pytest.raises(Stage48ApprovalBlocked):
        session.approve_pending_buy(order_id=a, token=token)
    assert session._deployment.virtual_account.orders[b].state is OrderState.PENDING_APPROVAL


@pytest.mark.parametrize("tamper", ["signature_hex", "actor", "role", "snapshot_hash", "token_id"])
def test_signed_token_tampering_is_refused(tmp_path, tamper):
    session, verifier = _open(tmp_path)
    oid = _buy(session)
    token = _token(verifier, session.pending_challenge(oid))
    value = {
        "signature_hex": "0" * 64,
        "actor": "OTHER",
        "role": "HUMAN_APPROVER",
        "snapshot_hash": "1" * 64,
        "token_id": "DIFFERENT-TOKEN-ID",
    }[tamper]
    bad = replace(token, **{tamper: value})
    with pytest.raises(PermissionError):
        session.approve_pending_buy(order_id=oid, token=bad)
    assert session._deployment.virtual_account.orders[oid].state is OrderState.PENDING_APPROVAL


@pytest.mark.parametrize("role", ["RISK_OWNER", "UNKNOWN"])
def test_non_paper_approver_role_is_rejected(tmp_path, role):
    session, verifier = _open(tmp_path)
    oid = _buy(session)
    challenge = session.pending_challenge(oid)
    # UNKNOWN is blocked by the core token issuer and is also never a valid
    # approver role even if constructed with another signer.
    if role == "UNKNOWN":
        with pytest.raises(PermissionError):
            _token(verifier, challenge, role=role)
    else:
        signed = _token(verifier, challenge, role=role)
        with pytest.raises(Stage48ApprovalBlocked, match="Role"):
            session.approve_pending_buy(order_id=oid, token=signed)
    assert session._deployment.virtual_account.orders[oid].approval is None


def test_expired_signed_token_rejected_by_durable_verifier(tmp_path):
    session, verifier = _open(tmp_path)
    oid = _buy(session)
    expired = _token(
        verifier, session.pending_challenge(oid),
        now_epoch=int(time.time()) - 120,
    )
    with pytest.raises(PermissionError, match="expired"):
        session.approve_pending_buy(order_id=oid, token=expired)
    assert session._deployment.virtual_account.orders[oid].state is OrderState.PENDING_APPROVAL


def test_future_dated_signed_token_rejected(tmp_path):
    session, verifier = _open(tmp_path)
    oid = _buy(session)
    future = _token(
        verifier, session.pending_challenge(oid),
        now_epoch=int(time.time()) + 120,
    )
    with pytest.raises(PermissionError, match="not yet valid"):
        session.approve_pending_buy(order_id=oid, token=future)


def test_replayed_token_id_is_rejected_across_new_order_even_with_matching_signer(tmp_path):
    session, verifier = _open(tmp_path)
    first = _buy(session)
    a = session.pending_challenge(first)
    token = _token(verifier, a, token_id="REUSED-NONCE")
    assert session.approve_pending_buy(order_id=first, token=token).state is OrderState.ACCEPTED
    # Cancel the approved but unfilled paper order, then use same token_id
    # to approve a fresh distinct pending order: SQLite nonce survives.
    session._deployment.virtual_account.cancel_order(first)
    second = _buy(session, symbol="XYZ")
    t2 = _token(verifier, session.pending_challenge(second), token_id="REUSED-NONCE")
    with pytest.raises(PermissionError, match="replay"):
        session.approve_pending_buy(order_id=second, token=t2)
    assert session._deployment.virtual_account.orders[second].state is OrderState.PENDING_APPROVAL


def test_replay_db_survives_restart_and_blocks_old_pending_approval(tmp_path):
    session, verifier = _open(tmp_path)
    first = _buy(session)
    token = _token(verifier, session.pending_challenge(first), token_id="PERSISTENT-NONCE")
    session.approve_pending_buy(order_id=first, token=token)
    opened_again = open_stage48_signed_paper_session(
        _config(tmp_path), verifier=verifier,
    )
    assert opened_again.status().signed_approval_adapter_installed
    with pytest.raises(Stage48ApprovalBlocked, match="provenance"):
        opened_again.approve_pending_buy(order_id=first, token=token)
    assert verifier.db_path.exists()
    with sqlite3.connect(verifier.db_path) as db:
        consumed = db.execute(
            "SELECT COUNT(*) FROM consumed_approval_tokens WHERE token_id=?",
            ("PERSISTENT-NONCE",),
        ).fetchone()[0]
    assert consumed == 1


def test_unapproved_pending_order_after_restart_stays_pending_and_blocked(tmp_path):
    session, verifier = _open(tmp_path)
    oid = _buy(session)
    token = _token(verifier, session.pending_challenge(oid))
    restarted = open_stage48_signed_paper_session(_config(tmp_path), verifier=verifier)
    with pytest.raises(Stage48ApprovalBlocked, match="provenance"):
        restarted.approve_pending_buy(order_id=oid, token=token)
    assert restarted._deployment.virtual_account.orders[oid].state is OrderState.PENDING_APPROVAL
    with pytest.raises(PermissionError):
        restarted._deployment.virtual_account.approve_order(oid, actor=token.actor)


def test_unsigned_order_from_stage43_cannot_get_stage48_approval(tmp_path):
    session, verifier = _open(tmp_path)
    raw = session._deployment.request_buy(
        symbol="ABC", quantity=1, entry_price=100, stop_price=95,
    )
    with pytest.raises(Stage48ApprovalBlocked, match="originate"):
        session.pending_challenge(raw.order_id)
    v = session._deployment.virtual_account
    with pytest.raises(PermissionError):
        v.approve_order(raw.order_id, "DEMO-OWNER")


def test_manual_callback_refuses_out_of_band_and_wrong_thread(tmp_path):
    import threading

    session, verifier = _open(tmp_path)
    oid = _buy(session)
    cb = session._deployment.virtual_account.approval_authorizer
    assert cb("DEMO-OWNER", oid) is False
    outcomes = []
    thread = threading.Thread(target=lambda: outcomes.append(cb("DEMO-OWNER", oid)))
    thread.start()
    thread.join()
    assert outcomes == [False]
    assert not session._deployment.virtual_account.orders[oid].approval


def test_approval_callback_replacement_denied_by_stage48(tmp_path):
    session, verifier = _open(tmp_path)
    oid = _buy(session)
    token = _token(verifier, session.pending_challenge(oid))
    v = session._deployment.virtual_account
    v.approval_authorizer = lambda actor, key: True
    with pytest.raises(Stage48ApprovalBlocked, match="replaced"):
        session.approve_pending_buy(order_id=oid, token=token)
    # This proves app-level mutation remains a global bypass problem:
    assert session.status().globally_mandatory_legacy_api_enforcement is False


def test_cross_account_signed_token_cannot_be_reused(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    verifier = _verifier(tmp_path)
    first = open_stage48_signed_paper_session(_config(a, account="ALPHA"), verifier=verifier)
    second = open_stage48_signed_paper_session(_config(b, account="BRAVO"), verifier=verifier)
    one = _buy(first)
    two = _buy(second)
    token = _token(verifier, first.pending_challenge(one))
    with pytest.raises(Stage48ApprovalBlocked):
        second.approve_pending_buy(order_id=two, token=token)
    assert second._deployment.virtual_account.orders[two].approval is None


def test_replay_db_must_not_equal_virtual_or_research_ledger(tmp_path):
    verifier = _verifier(tmp_path)
    verifier.db_path = _config(tmp_path).research_db_path
    with pytest.raises(Stage48ApprovalBlocked, match="separate"):
        open_stage48_signed_paper_session(_config(tmp_path), verifier=verifier)


def test_no_verifier_or_invalid_deployment_config_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        open_stage48_signed_paper_session(_config(tmp_path), verifier=None)
    with pytest.raises(TypeError):
        open_stage48_signed_paper_session(None, verifier=_verifier(tmp_path))


def test_challenge_generation_is_read_only_and_deterministic(tmp_path):
    session, _ = _open(tmp_path)
    oid = _buy(session)
    revision = session._deployment.virtual_account._snapshot_revision
    first = session.pending_challenge(oid)
    second = session.pending_challenge(oid)
    assert first == second
    assert session._deployment.virtual_account._snapshot_revision == revision


def test_simulated_fill_never_occurs_from_signed_approval(tmp_path):
    session, verifier = _open(tmp_path)
    oid = _buy(session)
    token = _token(verifier, session.pending_challenge(oid))
    session.approve_pending_buy(order_id=oid, token=token)
    v = session._deployment.virtual_account
    assert not v.positions
    assert not v.orders[oid].fills
    assert v.orders[oid].state is OrderState.ACCEPTED
    assert session.status().approved_for_live_trading is False


def test_stage48_cli_local_demo_no_live_orders():
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    done = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_stage48_signed_paper_smoke.py")],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stderr
    evidence = json.loads(done.stdout)
    assert evidence["unsigned_manual_approval_denied"]
    assert evidence["signed_order_accepted_not_filled"]
    assert evidence["durable_token_replay_denied"]
    assert evidence["virtual_fill_count"] == 0
    assert evidence["live_orders_transmitted"] == 0
    assert not evidence["external_human_identity_verified"]
    assert not evidence["production_ready"]

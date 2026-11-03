"""Stage57: persistent negative-only approval revocation and read-only risk binding QA.

All keys/identities are synthetic local fixtures. An HMAC actor label is
NOT an externally verified human. No broker or real money is involved.
"""
from __future__ import annotations

import secrets
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus_titan.core.security_gates import (
    CryptographicApprovalVerifier, SignedApprovalToken,
)
from nexus_titan.operations.brokerless_risk_veto import (
    Stage56SyntheticIntent, Stage56SyntheticQuote, Stage56SyntheticRiskState,
    inspect_stage56_synthetic_risk,
)
from nexus_titan.operations.local_approval_risk_review import (
    inspect_stage57_local_approval_binding,
)
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import (
    Stage48ApprovalBlocked, Stage48ApprovalChallenge,
    open_stage48_signed_paper_session,
)
from nexus_titan.virtual.order_manager import OrderState

_KEY = "QA-STAGE57-SYNTHETIC-HMAC-NOT-REAL"
_ACCOUNT = "STAGE57-SYNTHETIC"


def _verifier(root, *, key=_KEY):
    return CryptographicApprovalVerifier(
        secret_key=key, db_path=root / "approval-replay.sqlite3",
    )


def _token(v, *, token_id="STAGE57-TOKEN-ONE", actor="DEMO-SIGNER",
           role="PROJECT_OWNER", target="STAGE57:PAPER:QA", snapshot="a" * 64,
           now_epoch=None, ttl_seconds=60):
    return v.issue_token(
        token_id=token_id, actor=actor, role=role,
        target_entity_id=target, snapshot_hash=snapshot,
        ttl_seconds=ttl_seconds, now_epoch=now_epoch,
    )


def _consume(v, token, *, now_epoch=None):
    return v.verify_and_consume(
        token, expected_target_id=token.target_entity_id,
        expected_snapshot_hash=token.snapshot_hash,
        now_epoch=now_epoch,
    )


def _session(root, *, capital=50000, enabled=True):
    verifier = _verifier(root)
    session = open_stage48_signed_paper_session(
        PaperDeploymentConfig(
            account_id=_ACCOUNT, starting_capital=capital,
            virtual_state_dir=root / "virtual",
            research_db_path=root / "research.sqlite3",
            paper_orders_enabled=enabled,
        ), verifier=verifier,
    )
    return session, verifier


def _pending_buy(session):
    result = session.request_synthetic_buy(
        SyntheticBuyProposal(symbol="ABC", quantity=1, stop_price=95),
        SyntheticQuoteEvidence(
            observed_at=datetime.now(timezone.utc),
            bid=99.95, ask=100, displayed_ask_quantity=100,
            expected_edge_bps=45, slippage_bps=2,
        ),
    )
    assert result.status == "PENDING_APPROVAL"
    return result.order_id, session.pending_challenge(result.order_id)


def _risk_evidence(order_id, *, account_id=_ACCOUNT, time_at=None):
    if time_at is None:
        time_at = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    intent = Stage56SyntheticIntent(
        request_id=order_id, symbol="QAABC", quantity=1,
        limit_price_cents=10000, stop_price_cents=9500,
        fee_buffer_cents=100,
    )
    quote = Stage56SyntheticQuote(
        observed_at=time_at - timedelta(seconds=1),
        bid_cents=9995, ask_cents=10000,
        ask_depth_units=100, expected_slippage_bps=2,
        expected_edge_bps=45,
    )
    account = Stage56SyntheticRiskState(
        account_id=account_id, initial_cents=5_000_000,
        available_cents=5_000_000, already_reserved_cents=0,
        daily_realized_loss_bps=0, current_drawdown_bps=0,
        consecutive_losses=0, kill_switch_active=False,
        risk_module_healthy=True,
    )
    return intent, quote, account, time_at


def test_revocation_tables_created_without_touching_existing_replay_table(tmp_path):
    verifier = _verifier(tmp_path)
    with sqlite3.connect(verifier.db_path) as db:
        names = {x[0] for x in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert {"consumed_approval_tokens", "revoked_approval_tokens",
            "revoked_approval_actors"} <= names
    assert verifier.local_revocation_status(
        token_id="TEST", actor="DEMO",
    ) == {"token_revoked": False, "actor_revoked": False}


def test_token_revocation_blocks_valid_unused_signed_token(tmp_path):
    v = _verifier(tmp_path)
    token = _token(v)
    assert v.revoke_token(token.token_id)
    with pytest.raises(PermissionError, match="revoked"):
        _consume(v, token)
    assert v.local_revocation_status(
        token_id=token.token_id, actor=token.actor,
    )["token_revoked"]
    with sqlite3.connect(v.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM consumed_approval_tokens").fetchone()[0] == 0


def test_revocation_does_not_revoke_unrelated_actor_token(tmp_path):
    v = _verifier(tmp_path)
    v.revoke_token("BLOCKED")
    token = _token(v, token_id="SAFE-OTHER")
    assert _consume(v, token)
    assert v.local_revocation_status(
        token_id=token.token_id, actor=token.actor,
    ) == {"token_revoked": False, "actor_revoked": False}


def test_actor_revocation_denies_all_current_and_future_tokens(tmp_path):
    v = _verifier(tmp_path)
    prior = _token(v, token_id="ACTOR-ONE")
    assert v.revoke_actor(prior.actor)
    future = _token(v, token_id="ACTOR-TWO")
    for token in (prior, future):
        with pytest.raises(PermissionError, match="revoked"):
            _consume(v, token)
    assert v.local_revocation_status(token_id="ACTOR-TWO", actor=prior.actor) == {
        "token_revoked": False, "actor_revoked": True,
    }


def test_revocation_survives_restart_with_same_local_replay_db(tmp_path):
    first = _verifier(tmp_path)
    t1 = _token(first, token_id="PERSIST-TOKEN", actor="A")
    t2 = _token(first, token_id="OTHER-ID", actor="BAN-ACTOR")
    first.revoke_token(t1.token_id)
    first.revoke_actor(t2.actor)
    del first
    second = _verifier(tmp_path)
    with pytest.raises(PermissionError, match="revoked"):
        _consume(second, t1)
    with pytest.raises(PermissionError, match="revoked"):
        _consume(second, t2)
    assert second.local_revocation_status(
        token_id=t1.token_id, actor=t1.actor,
    )["token_revoked"]


@pytest.mark.parametrize("actor,token_id", [
    ("PROJECT-OWNER", "T-1"), ("HUMAN-APPROVER", "T-2"),
])
def test_revocations_are_idempotent_and_do_not_restore_subject(tmp_path, actor, token_id):
    v = _verifier(tmp_path)
    assert v.revoke_actor(actor, now_epoch=10)
    assert v.revoke_actor(actor, now_epoch=20)
    assert v.revoke_token(token_id, now_epoch=10)
    assert v.revoke_token(token_id, now_epoch=20)
    with sqlite3.connect(v.db_path) as db:
        assert db.execute(
            "SELECT revoked_at_epoch FROM revoked_approval_actors WHERE actor=?", (actor,)
        ).fetchone()[0] == 10
        assert db.execute(
            "SELECT revoked_at_epoch FROM revoked_approval_tokens WHERE token_id=?", (token_id,)
        ).fetchone()[0] == 10


@pytest.mark.parametrize("bad", ["", " ", "a" * 513, None, False, 10])
def test_bad_revocation_subjects_fail_closed(tmp_path, bad):
    v = _verifier(tmp_path)
    with pytest.raises(PermissionError):
        v.revoke_actor(bad)
    with pytest.raises(PermissionError):
        v.revoke_token(bad)


@pytest.mark.parametrize("bad", [False, True, -1, 1.5, "2"])
def test_invalid_revocation_times_rejected_without_rows(tmp_path, bad):
    v = _verifier(tmp_path)
    with pytest.raises(PermissionError):
        v.revoke_token("T", now_epoch=bad)
    with pytest.raises(PermissionError):
        v.revoke_actor("A", now_epoch=bad)
    with sqlite3.connect(v.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM revoked_approval_tokens").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM revoked_approval_actors").fetchone()[0] == 0


def test_revocation_does_not_remove_prior_consumed_token_or_reverse_approval(tmp_path):
    v = _verifier(tmp_path)
    token = _token(v)
    assert _consume(v, token)
    assert v.revoke_token(token.token_id)
    assert v.revoke_actor(token.actor)
    with sqlite3.connect(v.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM consumed_approval_tokens").fetchone()[0] == 1
    with pytest.raises(PermissionError, match="revoked"):
        _consume(v, token)


def test_stage48_pending_synthetic_buy_denied_after_token_revocation(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    signed = _token(
        verifier, token_id="REVOKED-ORDER", target=challenge.target_entity_id,
        snapshot=challenge.snapshot_hash,
    )
    verifier.revoke_token(signed.token_id)
    with pytest.raises(PermissionError, match="revoked"):
        session.approve_pending_buy(order_id=oid, token=signed)
    order = session._deployment.virtual_account.orders[oid]
    assert order.state is OrderState.PENDING_APPROVAL
    assert order.approval is None
    assert not order.fills
    assert order.filled_qty == 0
    assert session.status().production_ready is False


def test_stage48_pending_synthetic_buy_denied_after_actor_revocation(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    signed = _token(
        verifier, token_id="ACTOR-REVOKE", actor="LABEL-ONE",
        target=challenge.target_entity_id, snapshot=challenge.snapshot_hash,
    )
    verifier.revoke_actor(signed.actor)
    with pytest.raises(PermissionError, match="revoked"):
        session.approve_pending_buy(order_id=oid, token=signed)
    order = session._deployment.virtual_account.orders[oid]
    assert order.state is OrderState.PENDING_APPROVAL
    assert order.approval is None
    assert not order.fills
    assert session.status().globally_mandatory_legacy_api_enforcement is False


def test_legacy_stage48_unrevoked_valid_token_still_accepted_only_unfilled(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    signed = _token(
        verifier, target=challenge.target_entity_id, snapshot=challenge.snapshot_hash,
    )
    result = session.approve_pending_buy(order_id=oid, token=signed)
    assert result.state is OrderState.ACCEPTED
    assert result.approval is not None
    assert result.filled_qty == 0
    assert not result.fills
    assert session.status().approved_for_live_trading is False


def test_stage48_expired_token_still_denied_with_stage57_schema(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    signed = _token(
        verifier, target=challenge.target_entity_id, snapshot=challenge.snapshot_hash,
        now_epoch=int(time.time()) - 100, ttl_seconds=30,
    )
    with pytest.raises(PermissionError, match="expired"):
        session.approve_pending_buy(order_id=oid, token=signed)
    assert session._deployment.virtual_account.orders[oid].approval is None


def test_stage48_future_dated_token_still_denied(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    signed = _token(
        verifier, target=challenge.target_entity_id, snapshot=challenge.snapshot_hash,
        now_epoch=int(time.time()) + 100, ttl_seconds=30,
    )
    with pytest.raises(PermissionError, match="not yet valid"):
        session.approve_pending_buy(order_id=oid, token=signed)
    assert session._deployment.virtual_account.orders[oid].approval is None


def test_revocation_and_verification_share_single_sqlite_transaction_lock(tmp_path):
    v1 = _verifier(tmp_path)
    v2 = _verifier(tmp_path)
    token = _token(v1, token_id="RACE-ONE")
    def verify():
        try:
            return _consume(v1, token)
        except PermissionError:
            return False
    def revoke():
        return v2.revoke_token(token.token_id)
    with ThreadPoolExecutor(max_workers=2) as ex:
        a = ex.submit(verify)
        b = ex.submit(revoke)
        results = a.result(), b.result()
    assert results[1] is True
    with sqlite3.connect(v1.db_path) as db:
        consumed_count = db.execute(
            "SELECT COUNT(*) FROM consumed_approval_tokens WHERE token_id=?",
            (token.token_id,),
        ).fetchone()[0]
        revoked_count = db.execute(
            "SELECT COUNT(*) FROM revoked_approval_tokens WHERE token_id=?",
            (token.token_id,),
        ).fetchone()[0]
    assert consumed_count in (0, 1)
    assert consumed_count == int(results[0])
    assert revoked_count == 1
    with pytest.raises(PermissionError):
        _consume(v2, token)


def test_replay_of_revoked_token_after_crash_remains_denied(tmp_path):
    v = _verifier(tmp_path)
    token = _token(v, token_id="CRASH-REPLAY")
    v.revoke_token(token.token_id)
    del v
    reopened = _verifier(tmp_path)
    for _ in range(2):
        with pytest.raises(PermissionError, match="revoked"):
            _consume(reopened, token)
    with sqlite3.connect(reopened.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM consumed_approval_tokens").fetchone()[0] == 0


def test_risk_review_recomputes_fresh_stage56_local_policy_and_quote(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    intent, quote, account, now = _risk_evidence(oid)
    verdict = inspect_stage56_synthetic_risk(intent, quote, account, now=now)
    assert verdict.local_synthetic_screen_passed
    assessment = inspect_stage57_local_approval_binding(
        challenge, intent, quote, account,
        expected_risk_policy_sha256=verdict.policy_sha256,
        expected_risk_input_sha256=verdict.input_sha256,
        now=now,
    )
    assert assessment.local_consistency_observed
    assert not assessment.blockers
    assert assessment.local_risk_screen_passed
    assert assessment.order_snapshot_sha256 == challenge.snapshot_hash
    assert len(assessment.local_review_sha256) == 64
    assert assessment.local_review_sha256 == inspect_stage57_local_approval_binding(
        challenge, intent, quote, account,
        expected_risk_policy_sha256=verdict.policy_sha256,
        expected_risk_input_sha256=verdict.input_sha256, now=now,
    ).local_review_sha256
    assert not assessment.independent_human_identity_verified
    assert not assessment.external_market_quote_authenticated
    assert not assessment.signer_key_isolated_in_trusted_service
    assert not assessment.stage48_challenge_integrates_stage56_review
    assert not assessment.token_issue_authorized
    assert not assessment.order_submission_authorized
    assert not assessment.production_ready
    assert assessment.broker_orders_transmitted == 0


@pytest.mark.parametrize("change", ["quote", "policy", "cash", "kill", "age"])
def test_risk_drift_or_changed_evidence_fails_local_binding(tmp_path, change):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    intent, quote, account, now = _risk_evidence(oid)
    original = inspect_stage56_synthetic_risk(intent, quote, account, now=now)
    kw = {}
    if change == "quote":
        quote = replace(quote, expected_edge_bps=original.observed_spread_bps.__class__(41))
        # A float is malformed for integer-bps Stage56 evidence.
    if change == "policy":
        from nexus_titan.operations.brokerless_risk_veto import Stage56RiskPolicy
        kw["policy"] = Stage56RiskPolicy(max_quote_age_seconds=10)
    if change == "cash":
        account = replace(account, available_cents=4_999_900)
    if change == "kill":
        account = replace(account, kill_switch_active=True)
    if change == "age":
        now = now + timedelta(minutes=2)
    assessment = inspect_stage57_local_approval_binding(
        challenge, intent, quote, account,
        expected_risk_policy_sha256=original.policy_sha256,
        expected_risk_input_sha256=original.input_sha256, now=now, **kw,
    )
    assert not assessment.local_consistency_observed
    assert assessment.blockers
    assert assessment.local_review_sha256 is None
    assert not assessment.order_submission_authorized


@pytest.mark.parametrize("bad", [
    {"target_entity_id": "STAGE48:OTHER:FORGED"},
    {"snapshot_hash": "not-hex"},
    {"order_state": "ACCEPTED"},
    {"external_identity_verified": True},
    {"simulated_only": False},
])
def test_malformed_or_authoritative_stage48_challenge_denied(tmp_path, bad):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    intent, quote, account, now = _risk_evidence(oid)
    r = inspect_stage56_synthetic_risk(intent, quote, account, now=now)
    fake = replace(challenge, **bad)
    result = inspect_stage57_local_approval_binding(
        fake, intent, quote, account,
        expected_risk_policy_sha256=r.policy_sha256,
        expected_risk_input_sha256=r.input_sha256,
        now=now,
    )
    assert not result.local_consistency_observed
    assert "INVALID_STAGE48_CHALLENGE" in result.blockers
    assert result.local_review_sha256 is None


def test_stage48_order_and_stage56_request_mismatch_fails_review(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    intent, quote, account, now = _risk_evidence(oid)
    r = inspect_stage56_synthetic_risk(intent, quote, account, now=now)
    result = inspect_stage57_local_approval_binding(
        challenge, replace(intent, request_id="DIFFERENT-ORDER"),
        quote, account,
        expected_risk_policy_sha256=r.policy_sha256,
        expected_risk_input_sha256=r.input_sha256, now=now,
    )
    assert not result.local_consistency_observed
    assert "PAPER_ORDER_ACCOUNT_RISK_IDENTITY_MISMATCH" in result.blockers


def test_stage48_account_and_stage56_account_mismatch_fails_review(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    intent, quote, account, now = _risk_evidence(oid, account_id="WRONG-ACCOUNT")
    r = inspect_stage56_synthetic_risk(intent, quote, account, now=now)
    result = inspect_stage57_local_approval_binding(
        challenge, intent, quote, account,
        expected_risk_policy_sha256=r.policy_sha256,
        expected_risk_input_sha256=r.input_sha256,
        now=now,
    )
    assert "PAPER_ORDER_ACCOUNT_RISK_IDENTITY_MISMATCH" in result.blockers
    assert not result.local_consistency_observed


@pytest.mark.parametrize("digest", ["", "a" * 64, "not-a-hash", None])
def test_wrong_or_missing_stored_risk_digest_denies(tmp_path, digest):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    intent, quote, account, now = _risk_evidence(oid)
    original = inspect_stage56_synthetic_risk(intent, quote, account, now=now)
    assessment = inspect_stage57_local_approval_binding(
        challenge, intent, quote, account,
        expected_risk_policy_sha256=original.policy_sha256,
        expected_risk_input_sha256=digest, now=now,
    )
    assert not assessment.local_consistency_observed
    assert assessment.local_review_sha256 is None
    assert "RISK_POLICY_OR_INPUT_DIGEST_CHANGED" in assessment.blockers


def test_local_binding_is_read_only_no_token_or_virtual_approval_mutation(tmp_path):
    session, verifier = _session(tmp_path)
    oid, challenge = _pending_buy(session)
    order = session._deployment.virtual_account.orders[oid]
    revision = session._deployment.virtual_account._snapshot_revision
    intent, quote, account, now = _risk_evidence(oid)
    r = inspect_stage56_synthetic_risk(intent, quote, account, now=now)
    for _ in range(3):
        result = inspect_stage57_local_approval_binding(
            challenge, intent, quote, account,
            expected_risk_policy_sha256=r.policy_sha256,
            expected_risk_input_sha256=r.input_sha256, now=now,
        )
        assert result.local_consistency_observed
    assert session._deployment.virtual_account._snapshot_revision == revision
    assert order.state is OrderState.PENDING_APPROVAL
    assert order.approval is None and not order.fills
    with sqlite3.connect(verifier.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM consumed_approval_tokens").fetchone()[0] == 0


def test_stage57_cli_synthetic_smoke_has_no_real_permission():
    root = Path(__file__).resolve().parents[1]
    import subprocess
    import sys
    import json
    run = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_stage57_approval_revocation_smoke.py")],
        cwd=root, text=True, capture_output=True, timeout=35, check=False,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["mode"] == "STAGE57_LOCAL_SIGNER_REVOCATION_QA"
    assert report["token_revocation_denied_paper_approval"]
    assert report["actor_revocation_denied_paper_approval"]
    assert report["risk_binding_local_consistency"]
    assert report["no_orders_filled"]
    assert report["live_orders_transmitted"] == 0
    assert report["external_human_identity_verified"] is False
    assert report["global_legacy_apis_fenced"] is False
    assert report["production_ready"] is False

"""Stage54: offline multi-ledger recovery/consistency adversarial tests.

Four distinct temporary SQLite accounting databases; no real sources, trades,
external identity, broker, automatic order replay or capital release.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nexus_titan.core.security_gates import CryptographicApprovalVerifier
from nexus_titan.operations.durable_paper_fence import Stage49DurablePaperFence
from nexus_titan.operations.multi_ledger_recovery_audit import (
    Stage54ReadOnlyMultiLedgerAudit, Stage54ReconciliationBlocked,
)
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import (
    open_stage48_signed_paper_session,
)
from nexus_titan.operations.synthetic_capital_authority import (
    Stage53SyntheticCapitalAuthority,
)
from nexus_titan.virtual.order_manager import OrderState


def _setup(root, *, capital=50000, account="STAGE54-LOCAL", enabled=True):
    root.mkdir(parents=True, exist_ok=True)
    verifier = CryptographicApprovalVerifier(
        secret_key=secrets.token_urlsafe(32),
        db_path=root / "replay.sqlite3",
    )
    config = PaperDeploymentConfig(
        account_id=account, starting_capital=capital,
        virtual_state_dir=root / "virtual",
        research_db_path=root / "research.sqlite3",
        paper_orders_enabled=enabled,
    )
    session = open_stage48_signed_paper_session(config, verifier=verifier)
    fence = Stage49DurablePaperFence(
        session, db_path=root / "coordinator.sqlite3",
    )
    budget = Stage53SyntheticCapitalAuthority(
        db_path=root / "synthetic_budget.sqlite3", account_id=account,
        starting_cents=capital * 100,
        excluded_ledger_paths=(
            root / "coordinator.sqlite3", root / "research.sqlite3",
            root / "virtual" / f"{account}_durable.db", root / "replay.sqlite3",
        ),
    )
    audit = Stage54ReadOnlyMultiLedgerAudit(
        paper_fence=fence, synthetic_budget=budget,
    )
    return session, fence, budget, audit


def _intent(fence):
    return fence.request_first_synthetic_buy(
        request_id="STAGE54-PAPER-BUY",
        proposal=SyntheticBuyProposal(
            symbol="QA-ABC", quantity=1, stop_price=95,
        ),
        quote=SyntheticQuoteEvidence(
            observed_at=datetime.now(timezone.utc), bid=99.95, ask=100,
            displayed_ask_quantity=100, expected_edge_bps=45, slippage_bps=2,
        ),
    )


def _assert_denied_release(status):
    assert status.cross_database_atomicity_verified is False
    assert status.globally_mandatory_entrypoint is False
    assert status.externally_authenticated_human_identity is False
    assert status.independent_risk_veto_enforced is False
    assert status.real_market_data_authenticated is False
    assert status.automatic_hold_release_enabled is False
    assert status.automatic_order_replay_enabled is False
    assert status.automatic_write_repair_enabled is False
    assert status.combined_available_capital_cents is None
    assert status.broker_orders_transmitted == 0
    assert status.live_trading_enabled is False
    assert status.production_ready is False


@pytest.mark.parametrize("capital", [12500, 50000, 75000])
def test_flat_independent_paper_books_can_only_get_local_review_status(tmp_path, capital):
    session, fence, budget, audit = _setup(tmp_path, capital=capital)
    report = audit.inspect()
    assert report.account_id == "STAGE54-LOCAL"
    assert report.observed_initial_cents == capital * 100
    assert report.virtual_cash_cents == capital * 100
    assert report.research_cash_cents == capital * 100
    assert report.separate_book_cash_equal
    assert report.virtual_internal_reconciled
    assert report.research_local_integrity_verified
    assert report.stage49_coordinator_scope_verified
    assert report.coordinator_attempt_count == 0
    assert report.coordinator_state is None
    assert not report.coordinator_order_link_observed
    assert report.coordinator_linked_virtual_order_state is None
    assert report.budget_local_integrity_verified
    assert report.stage53_synthetic_held_cents == 0
    assert report.stage53_synthetic_remaining_cents == capital * 100
    assert report.stage53_hold_count == 0
    assert report.identified_unlinked_paper_orders == 0
    assert report.recovery_classification == "LOCAL_FLAT_COMPARISON_ONLY"
    assert not report.manual_recovery_required
    assert not report.diagnostic_codes
    _assert_denied_release(report)
    assert json.loads(json.dumps(report.to_dict()))["production_ready"] is False


def test_repeated_read_does_not_change_ledger_business_state(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    v = session._deployment.virtual_account
    r = session._deployment.research_ledger
    rev = v._snapshot_revision
    before = budget.inspect()
    research_before = r.status()
    a = audit.inspect()
    b = audit.inspect()
    after = budget.inspect()
    research_after = r.status()
    assert a == b
    assert before == after
    assert research_before == research_after
    assert v._snapshot_revision == rev
    assert not v.orders
    assert not v.positions
    assert not r.status().open_order_count
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM admission_attempts").fetchone()[0] == 0
    with sqlite3.connect(tmp_path / "synthetic_budget.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM budget_holds").fetchone()[0] == 0


def test_stage49_pending_order_is_only_link_observed_not_capital_authority(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    intent = _intent(fence)
    report = audit.inspect()
    assert report.recovery_classification == "PENDING_ORDER_MANUAL_REVIEW"
    assert report.manual_recovery_required
    assert report.coordinator_attempt_count == 1
    assert report.coordinator_state == "PENDING"
    assert report.coordinator_order_link_observed
    assert report.coordinator_linked_virtual_order_state == "PENDING_APPROVAL"
    assert report.identified_unlinked_paper_orders == 0
    assert report.stage53_synthetic_held_cents == 0
    assert not session._deployment.virtual_account.orders[intent.order_id].fills
    assert "PENDING_ATTEMPT_NEEDS_MANUAL_REVIEW" in report.diagnostic_codes
    _assert_denied_release(report)


def test_signed_pending_approval_still_requires_manual_audit(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    intent = _intent(fence)
    challenge = session.pending_challenge(intent.order_id)
    signed = session._verifier.issue_token(
        token_id="S54-LOCAL-QA", actor="LOCAL-NOT-VERIFIED-HUMAN",
        role="PROJECT_OWNER", target_entity_id=challenge.target_entity_id,
        snapshot_hash=challenge.snapshot_hash, ttl_seconds=30,
    )
    order = session.approve_pending_buy(order_id=intent.order_id, token=signed)
    assert order.state is OrderState.ACCEPTED
    result = audit.inspect()
    assert result.coordinator_order_link_observed
    assert result.coordinator_linked_virtual_order_state == "ACCEPTED"
    assert result.manual_recovery_required
    assert result.recovery_classification == "PENDING_ORDER_MANUAL_REVIEW"
    assert order.filled_qty == 0
    _assert_denied_release(result)


def test_preparing_crash_marker_quarantined_without_order_replay(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute(
            "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("AFTER-COMMIT-CRASH", "STAGE54-LOCAL", "PREPARING",
             10000, "0" * 64, 0, None, datetime.now(timezone.utc).isoformat()),
        )
    result = audit.inspect()
    assert result.recovery_classification == "PREPARING_CRASH_QUARANTINE"
    assert "PREPARING_AFTER_CRASH_NEEDS_MANUAL_REVIEW" in result.diagnostic_codes
    assert result.coordinator_attempt_count == 1
    assert result.coordinator_state == "PREPARING"
    assert not result.coordinator_order_link_observed
    assert not session._deployment.virtual_account.orders
    assert result.manual_recovery_required
    _assert_denied_release(result)


def test_unknown_crash_outcome_never_replayed(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute(
            "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("UNKNOWN-COMMIT", "STAGE54-LOCAL", "UNKNOWN",
             50000, "0" * 64, 0, None, datetime.now(timezone.utc).isoformat()),
        )
    result = audit.inspect()
    assert result.recovery_classification == "UNKNOWN_OUTCOME_QUARANTINE"
    assert result.coordinator_state == "UNKNOWN"
    assert result.manual_recovery_required
    assert not session._deployment.virtual_account.orders
    _assert_denied_release(result)


def test_missing_virtual_order_from_pending_marker_is_flagged(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute(
            "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("BAD-REFERENCE", "STAGE54-LOCAL", "PENDING",
             10000, "0" * 64, 0, "GHOST-ORDER", datetime.now(timezone.utc).isoformat()),
        )
    report = audit.inspect()
    assert report.recovery_classification == "PENDING_ORDER_MANUAL_REVIEW"
    assert not report.coordinator_order_link_observed
    assert "COORDINATOR_REFERENCES_MISSING_VIRTUAL_ORDER" in report.diagnostic_codes


def test_missing_order_id_on_pending_marker_is_flagged(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute(
            "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("BAD-ID", "STAGE54-LOCAL", "PENDING",
             10000, "0" * 64, 0, None, datetime.now(timezone.utc).isoformat()),
        )
    report = audit.inspect()
    assert "PENDING_COORDINATOR_MISSING_ORDER_ID" in report.diagnostic_codes
    assert report.manual_recovery_required


def test_unlinked_legacy_stage43_order_is_not_treated_as_safe(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    raw = session._deployment.request_buy(
        symbol="ABC", quantity=1, entry_price=100, stop_price=95,
    )
    report = audit.inspect()
    assert raw.order_id in session._deployment.virtual_account.orders
    assert report.coordinator_attempt_count == 0
    assert report.identified_unlinked_paper_orders == 1
    assert "VIRTUAL_ORDERS_OUTSIDE_STAGE49_MARKER" in report.diagnostic_codes
    assert report.manual_recovery_required
    _assert_denied_release(report)


def test_local_budget_hold_is_unlinked_not_shared_cash_reduction(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    budget.hold_for_synthetic_research(request_id="RESEARCH-HOLD-ONE", amount_cents=100_000)
    result = audit.inspect()
    assert result.stage53_synthetic_held_cents == 100_000
    assert result.stage53_synthetic_remaining_cents == 4_900_000
    assert result.virtual_cash_cents == result.research_cash_cents == 5_000_000
    assert result.combined_available_capital_cents is None
    assert "UNLINKED_STANDALONE_BUDGET_HOLDS_NEED_MANUAL_REVIEW" in result.diagnostic_codes
    assert result.manual_recovery_required


def test_combined_paper_pending_and_independent_budget_hold_stays_unlinked(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    _intent(fence)
    budget.hold_for_synthetic_research(request_id="UNRELATED-BUDGET", amount_cents=100)
    result = audit.inspect()
    assert result.coordinator_state == "PENDING"
    assert result.stage53_synthetic_held_cents == 100
    assert result.manual_recovery_required
    assert "UNLINKED_STANDALONE_BUDGET_HOLDS_NEED_MANUAL_REVIEW" in result.diagnostic_codes
    assert result.recovery_classification == "PENDING_ORDER_MANUAL_REVIEW"


def test_virtual_cash_adjustment_detected(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    v = session._deployment.virtual_account
    v.adjust_capital(100, "TOP_UP", reason="test synthetic drift", user_confirmed=True)
    result = audit.inspect()
    assert result.virtual_cash_cents == 5_010_000
    assert result.research_cash_cents == 5_000_000
    assert not result.separate_book_cash_equal
    assert "SEPARATE_BOOK_CASH_MISMATCH_OR_UNAVAILABLE" in result.diagnostic_codes
    assert "VIRTUAL_CASH_CHANGED_FROM_INITIAL" in result.diagnostic_codes
    assert result.manual_recovery_required


def test_stage53_journal_tamper_fails_closed(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    budget.hold_for_synthetic_research(request_id="JOURNAL-ONE", amount_cents=100)
    with sqlite3.connect(tmp_path / "synthetic_budget.sqlite3") as db:
        db.execute("UPDATE budget_scope SET held_cents=held_cents+1")
    report = audit.inspect()
    assert not report.budget_local_integrity_verified
    assert report.stage53_synthetic_held_cents is None
    assert "STAGE53_BUDGET_INTEGRITY_UNVERIFIED" in report.diagnostic_codes
    assert report.manual_recovery_required


def test_stage49_scope_tamper_fails_closed(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute("UPDATE coordinator_scope SET scope_hash='broken'")
    report = audit.inspect()
    assert not report.stage49_coordinator_scope_verified
    assert report.coordinator_attempt_count is None
    assert "COORDINATOR_SCOPE_OR_HISTORY_UNAVAILABLE" in report.diagnostic_codes
    assert report.manual_recovery_required


def test_stage49_multiple_attempts_is_not_safe_even_when_cash_matches(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        for idx in range(2):
            db.execute(
                "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
                (f"FORGED-{idx}", "STAGE54-LOCAL", "PREPARING",
                 100, "0" * 64, 0, None, datetime.now(timezone.utc).isoformat()),
            )
    result = audit.inspect()
    assert result.coordinator_attempt_count == 2
    assert "MULTIPLE_COORDINATOR_ATTEMPTS" in result.diagnostic_codes
    assert result.manual_recovery_required


def test_bad_coordinator_marker_fields_fail_closed(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute(
            "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("MALFORMED", "STAGE54-LOCAL", "PREPARING",
             -1, "?", -1, None, datetime.now(timezone.utc).isoformat()),
        )
    result = audit.inspect()
    assert "COORDINATOR_MARKER_FIELDS_INVALID" in result.diagnostic_codes
    assert result.manual_recovery_required


@pytest.mark.parametrize("capital", [12500, 50000])
def test_same_books_can_be_reopened_and_inspected_conservatively(tmp_path, capital):
    session, fence, budget, audit = _setup(tmp_path, capital=capital)
    initial = audit.inspect()
    verifier = CryptographicApprovalVerifier(
        secret_key=secrets.token_urlsafe(32), db_path=tmp_path / "replay.sqlite3",
    )
    fresh = open_stage48_signed_paper_session(
        session._deployment.config, verifier=verifier,
    )
    fresh_fence = Stage49DurablePaperFence(
        fresh, db_path=tmp_path / "coordinator.sqlite3",
    )
    reopened = Stage53SyntheticCapitalAuthority(
        db_path=tmp_path / "synthetic_budget.sqlite3",
        account_id="STAGE54-LOCAL", starting_cents=capital * 100,
    )
    res = Stage54ReadOnlyMultiLedgerAudit(
        paper_fence=fresh_fence, synthetic_budget=reopened,
    ).inspect()
    assert initial.recovery_classification == "LOCAL_FLAT_COMPARISON_ONLY"
    assert res.recovery_classification == initial.recovery_classification
    assert res.virtual_cash_cents == capital * 100
    assert res.budget_local_integrity_verified
    _assert_denied_release(res)


def test_restart_pending_order_not_automatically_approved(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    intent = _intent(fence)
    verifier = CryptographicApprovalVerifier(
        secret_key=secrets.token_urlsafe(32), db_path=tmp_path / "replay.sqlite3",
    )
    fresh = open_stage48_signed_paper_session(session._deployment.config, verifier=verifier)
    fresh_fence = Stage49DurablePaperFence(fresh, db_path=tmp_path / "coordinator.sqlite3")
    resumed = Stage54ReadOnlyMultiLedgerAudit(
        paper_fence=fresh_fence, synthetic_budget=budget,
    ).inspect()
    assert resumed.coordinator_linked_virtual_order_state == "PENDING_APPROVAL"
    assert resumed.manual_recovery_required
    assert fresh._deployment.virtual_account.orders[intent.order_id].approval is None
    assert not hasattr(Stage54ReadOnlyMultiLedgerAudit, "recover_order")
    _assert_denied_release(resumed)


def test_mismatched_account_or_initial_capital_rejected_at_construction(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    other = Stage53SyntheticCapitalAuthority(
        db_path=tmp_path / "other_budget.sqlite3",
        account_id="ANOTHER-ACCOUNT", starting_cents=5_000_000,
    )
    with pytest.raises(Stage54ReconciliationBlocked, match="account IDs"):
        Stage54ReadOnlyMultiLedgerAudit(paper_fence=fence, synthetic_budget=other)
    different = Stage53SyntheticCapitalAuthority(
        db_path=tmp_path / "larger_budget.sqlite3",
        account_id="STAGE54-LOCAL", starting_cents=7_500_000,
    )
    with pytest.raises(Stage54ReconciliationBlocked, match="starting capital"):
        Stage54ReadOnlyMultiLedgerAudit(paper_fence=fence, synthetic_budget=different)


def test_db_path_alias_rejected_before_audit(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    budget._path = fence._db_path  # hostile in-process mutation of private field
    with pytest.raises(Stage54ReconciliationBlocked, match="alias"):
        Stage54ReadOnlyMultiLedgerAudit(paper_fence=fence, synthetic_budget=budget)


def test_symlinked_coordinator_path_rejected_before_audit(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    alias = tmp_path / "alternate_coordinator.sqlite3"
    alias.symlink_to(fence._db_path)
    fence._db_path = alias  # hostile in-process mutation
    with pytest.raises(Stage54ReconciliationBlocked, match="symlink"):
        Stage54ReadOnlyMultiLedgerAudit(paper_fence=fence, synthetic_budget=budget)


def test_concurrent_change_during_review_is_reported(tmp_path, monkeypatch):
    session, fence, budget, audit = _setup(tmp_path)
    account = session._deployment.virtual_account
    original = budget.inspect

    def mutate_during_inspection():
        result = original()
        # Synthetic local authorized paper top-up changes durable revision.
        account.adjust_capital(10, "TOP_UP", reason="QA raced snapshot", user_confirmed=True)
        return result

    monkeypatch.setattr(budget, "inspect", mutate_during_inspection)
    result = audit.inspect()
    assert "VIRTUAL_REVISION_MOVED_DURING_AUDIT" in result.diagnostic_codes
    assert result.manual_recovery_required


def test_recovery_guidance_has_no_executable_actions(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    result = audit.inspect()
    assert result.manual_review_instructions
    assert all(isinstance(x, str) for x in result.manual_review_instructions)
    for forbidden in (
        "submit_order", "release_hold", "execute_fill", "approve_order",
        "replay_order", "repair_database", "merge_ledgers",
    ):
        assert not hasattr(audit, forbidden)
    assert not hasattr(audit, "write_recovery")
    _assert_denied_release(result)


def test_invalid_constructor_types_are_refused(tmp_path):
    session, fence, budget, audit = _setup(tmp_path)
    with pytest.raises(TypeError):
        Stage54ReadOnlyMultiLedgerAudit(paper_fence=None, synthetic_budget=budget)
    with pytest.raises(TypeError):
        Stage54ReadOnlyMultiLedgerAudit(paper_fence=fence, synthetic_budget=None)


def test_offline_stage54_smoke_is_json_and_honest(tmp_path):
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_stage54_multiledger_recovery_smoke.py")],
        cwd=root, capture_output=True, text=True, check=False, timeout=35,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["mode"] == "STAGE54_SYNTHETIC_READ_ONLY_RECOVERY_AUDIT"
    assert data["flat"]["recovery_classification"] == "LOCAL_FLAT_COMPARISON_ONLY"
    assert data["crash"]["recovery_classification"] == "PREPARING_CRASH_QUARANTINE"
    assert data["crash"]["manual_recovery_required"]
    assert data["crash"]["automatic_order_replay_enabled"] is False
    assert data["crash"]["automatic_hold_release_enabled"] is False
    assert data["crash"]["cross_database_atomicity_verified"] is False
    assert data["crash"]["live_trading_enabled"] is False
    assert data["crash"]["broker_orders_transmitted"] == 0
    assert data["crash"]["combined_available_capital_cents"] is None

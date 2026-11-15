"""Stage50 read-only TITAN dashboard / source-binding regressions.

All values are synthetic temporary SQLite research state. No broker, market
feed, signed identity service, real orders, or executable UI controls.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone

import pytest

from nexus_titan.core.security_gates import CryptographicApprovalVerifier
from nexus_titan.dashboard.api_service import DashboardBackendService
from nexus_titan.dashboard.paper_read_model import (
    Stage50DashboardBlocked,
    Stage50ReadOnlyPaperDashboard,
    unattached_stage50_dashboard,
)
from nexus_titan.operations.durable_paper_fence import Stage49DurablePaperFence
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import open_stage48_signed_paper_session
from nexus_titan.virtual.order_manager import OrderState, VirtualAccount


def _fixture(root, *, capital=50000, enabled=True, account="S50"):
    root.mkdir(parents=True, exist_ok=True)
    verifier = CryptographicApprovalVerifier(
        secrets.token_urlsafe(32), db_path=root / "replay.sqlite3",
    )
    session = open_stage48_signed_paper_session(
        PaperDeploymentConfig(
            account_id=account, starting_capital=capital,
            virtual_state_dir=root / "virtual",
            research_db_path=root / "research.sqlite3",
            paper_orders_enabled=enabled,
        ), verifier=verifier,
    )
    fence = Stage49DurablePaperFence(session, db_path=root / "coordinator.sqlite3")
    return session, fence, Stage50ReadOnlyPaperDashboard(fence)


def _quote():
    return SyntheticQuoteEvidence(
        observed_at=datetime.now(timezone.utc), bid=99.95, ask=100.0,
        displayed_ask_quantity=100, expected_edge_bps=45,
        slippage_bps=2,
    )


def _buy(fence):
    return fence.request_first_synthetic_buy(
        request_id="S50-ONE", quote=_quote(),
        proposal=SyntheticBuyProposal(
            symbol="QA-ABC", quantity=1, stop_price=95,
        ),
    )


@pytest.mark.parametrize("capital", [10000, 50000, 175000])
def test_flat_synthetic_dashboard_has_no_fake_market_and_no_double_cash(tmp_path, capital):
    session, fence, view = _fixture(tmp_path, capital=capital)
    report = view.snapshot()
    assert report["schema_version"] == 1
    assert report["component"] == "TITAN_PAPER_SAFETY"
    assert report["data_source"] == "LOCAL_SYNTHETIC_PAPER_SQLITE_ONLY"
    assert report["status"] == "LOCAL_SYNTHETIC_REVIEW_ONLY"
    assert report["account"]["initial_paper_capital_cents"] == capital * 100
    assert report["account"]["virtual_cash_cents"] == capital * 100
    assert report["account"]["research_cash_cents"] == capital * 100
    assert report["account"]["combined_cash_cents"] is None
    assert report["account"]["two_book_cash_match_observed"]
    assert not report["account"]["cross_ledger_atomicity"]
    assert report["paper_orders"]["total"] == 0
    assert report["admission_fence"]["attempt_count"] == 0
    assert report["admission_fence"]["first_synthetic_buy_preflight_passed"]
    assert report["signed_approval"]["configured_local_verifier"]
    assert not report["signed_approval"]["external_identity_authenticated"]
    assert not report["market"]["india_fo_live_data"]
    assert not report["market"]["crypto_live_data"]
    assert report["market"]["latest_price"] is None
    assert report["risk_veto"]["latest_veto_result"] == "NOT_EVALUATED_NO_TRUSTED_QUOTE"
    assert not report["risk_veto"]["new_proposal_risk_evaluated"]
    assert not report["safety"]["production_ready"]
    assert not report["safety"]["paper_order_actions_enabled"]
    assert not report["safety"]["approval_actions_enabled"]
    assert not report["safety"]["live_trading_enabled"]
    assert not report["evolve"]["autonomous_real_orders_enabled"]
    assert report["theme"]["theme_id"] == "NEXUS_TITAN_BLACK_SILVER_LOCKED"
    assert report["theme"]["cybernetic_face_asset"] == "EXTERNAL_APPROVED_REFERENCE_REQUIRED"
    # Renderer can use JSON but no live or user token data is present.
    assert '"production_ready": false' in json.dumps(report, allow_nan=False, sort_keys=True).lower()


def test_read_only_snapshot_does_not_mutate_revision_or_markers(tmp_path):
    session, fence, view = _fixture(tmp_path)
    v = session._deployment.virtual_account
    revision = v._snapshot_revision
    original_cash = v.cash_balance
    first = view.snapshot()
    second = view.snapshot()
    assert first["account"] == second["account"]
    assert first["paper_orders"] == second["paper_orders"]
    assert first["admission_fence"] == second["admission_fence"]
    assert v._snapshot_revision == revision
    assert v.cash_balance == original_cash
    assert not v.orders
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM admission_attempts").fetchone()[0] == 0


def test_pending_intent_displays_counts_not_order_handles_or_secrets(tmp_path):
    session, fence, view = _fixture(tmp_path)
    intent = _buy(fence)
    report = view.snapshot()
    assert report["status"] == "LOCAL_REVIEW_REQUIRED"
    assert report["paper_orders"]["total"] == 1
    assert report["paper_orders"]["counts_by_state"]["PENDING_APPROVAL"] == 1
    assert report["paper_orders"]["pending_manual_approval"] == 1
    assert report["paper_orders"]["fill_fragments"] == 0
    assert report["paper_orders"]["latest_order_ids"] == []
    assert report["admission_fence"]["attempt_count"] == 1
    assert report["admission_fence"]["latest_attempt_state"] == "PENDING"
    assert not report["admission_fence"]["first_synthetic_buy_preflight_passed"]
    encoded = json.dumps(report, allow_nan=False)
    assert intent.order_id not in encoded
    assert "signature_hex" not in encoded
    assert "secret_key" not in encoded
    assert session._deployment.virtual_account.orders[intent.order_id].state is OrderState.PENDING_APPROVAL


def test_signed_local_approval_display_never_implies_fill_or_verified_person(tmp_path):
    session, fence, view = _fixture(tmp_path)
    intent = _buy(fence)
    c = session.pending_challenge(intent.order_id)
    token = session._verifier.issue_token(
        token_id="S50-ONE-TIME", actor="DEMO-NOT-IDENTITY",
        role="PROJECT_OWNER", target_entity_id=c.target_entity_id,
        snapshot_hash=c.snapshot_hash, ttl_seconds=30,
    )
    session.approve_pending_buy(order_id=intent.order_id, token=token)
    report = view.snapshot()
    assert report["paper_orders"]["counts_by_state"]["ACCEPTED"] == 1
    assert report["paper_orders"]["approved_unfilled"] == 1
    assert report["paper_orders"]["fill_fragments"] == 0
    assert report["paper_orders"]["open_position_symbols"] == 0
    assert not report["signed_approval"]["external_identity_authenticated"]
    assert not report["safety"]["broker_connected"]
    assert token.token_id not in json.dumps(report)
    assert token.signature_hex not in json.dumps(report)


def test_coordinator_preparing_marker_remains_an_unresolved_alert(tmp_path):
    session, fence, view = _fixture(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute(
            "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("S50-CRASH", "S50", "PREPARING", 10000, "0" * 64,
             0, None, datetime.now(timezone.utc).isoformat()),
        )
    report = view.snapshot()
    assert report["status"] == "LOCAL_REVIEW_REQUIRED"
    assert report["admission_fence"]["latest_attempt_state"] == "PREPARING"
    assert not report["admission_fence"]["first_synthetic_buy_preflight_passed"]
    assert not report["safety"]["production_ready"]


def test_cash_drift_alert_does_not_invent_consolidated_cash(tmp_path):
    session, fence, view = _fixture(tmp_path)
    session._deployment.virtual_account.adjust_capital(
        100, "TOP_UP", reason="test-only top up", user_confirmed=True,
    )
    report = view.snapshot()
    assert report["status"] == "LOCAL_REVIEW_REQUIRED"
    assert report["account"]["virtual_cash_cents"] == 5010000
    assert report["account"]["research_cash_cents"] == 5000000
    assert report["account"]["combined_cash_cents"] is None
    assert not report["account"]["two_book_cash_match_observed"]
    assert not report["admission_fence"]["first_synthetic_buy_preflight_passed"]


def test_kill_switch_is_reflected_but_not_toggled_by_read(tmp_path):
    session, fence, view = _fixture(tmp_path)
    session._deployment.virtual_account.activate_emergency_kill_switch("Synthetic S50")
    report = view.snapshot()
    assert report["paper_session"]["kill_switch_active"] is True
    assert report["status"] == "LOCAL_REVIEW_REQUIRED"
    assert not report["admission_fence"]["first_synthetic_buy_preflight_passed"]
    assert session._deployment.virtual_account.kill_switched


def test_corrupted_coordinator_is_not_treated_as_operational(tmp_path):
    session, fence, view = _fixture(tmp_path)
    with sqlite3.connect(tmp_path / "coordinator.sqlite3") as db:
        db.execute("UPDATE coordinator_scope SET scope_hash = 'corrupt'")
    report = view.snapshot()
    assert report["status"] == "LOCAL_REVIEW_REQUIRED"
    assert not report["admission_fence"]["coordinator_bound"]
    assert not report["admission_fence"]["first_synthetic_buy_preflight_passed"]


def test_replaced_approval_callback_triggers_dashboard_alert(tmp_path):
    session, fence, view = _fixture(tmp_path)
    session._deployment.virtual_account.approval_authorizer = lambda actor, key: True
    report = view.snapshot()
    assert not report["signed_approval"]["configured_local_verifier"]
    assert not report["safety"]["production_ready"]
    assert report["status"] == "LOCAL_REVIEW_REQUIRED"


def test_default_paper_disabled_report_never_exposes_action(tmp_path):
    session, fence, view = _fixture(tmp_path, enabled=False)
    report = view.snapshot()
    assert report["status"] == "LOCAL_REVIEW_REQUIRED"
    assert not report["paper_session"]["paper_orders_enabled_in_config"]
    assert not report["admission_fence"]["first_synthetic_buy_preflight_passed"]
    assert not report["safety"]["paper_order_actions_enabled"]


def test_dashboard_accepts_only_real_stage49_and_matching_account(tmp_path):
    with pytest.raises(Stage50DashboardBlocked):
        Stage50ReadOnlyPaperDashboard(object())
    session, fence, view = _fixture(tmp_path / "one")
    other_session, other_fence, other = _fixture(tmp_path / "two", account="S50-OTHER")
    with pytest.raises(ValueError, match="same explicit VirtualAccount"):
        DashboardBackendService(
            account=session._deployment.virtual_account,
            stage50_paper_dashboard=other,
        )
    assert view.account is session._deployment.virtual_account
    assert other.account is other_session._deployment.virtual_account


def test_legacy_dashboard_has_no_attached_paper_authority(tmp_path):
    raw = unattached_stage50_dashboard()
    assert raw["status"] == "NOT_ATTACHED"
    assert not raw["paper_order_actions_enabled"]
    assert not raw["approval_actions_enabled"]
    assert not raw["live_trading_enabled"]
    assert raw["data_source"] == "NONE"
    account = VirtualAccount("LEGACY-S50", starting_capital=50000)
    service = DashboardBackendService(account=account, default_csv=tmp_path / "missing.csv")
    result = service.get_stage50_paper_safety()
    assert result["status"] == "NOT_ATTACHED"


def test_existing_dashboard_service_exposes_stage50_read_model_opt_in(tmp_path):
    session, fence, view = _fixture(tmp_path)
    account = session._deployment.virtual_account
    service = DashboardBackendService(
        account=account, default_csv=tmp_path / "missing.csv",
        stage50_paper_dashboard=view,
    )
    rev = account._snapshot_revision
    s = service.get_stage50_paper_safety()
    assert s["component"] == "TITAN_PAPER_SAFETY"
    assert s["account"]["account_id"] == "S50"
    assert account._snapshot_revision == rev
    # Existing rich dashboard telemetry remains backwards-compatible.
    telemetry = service.get_system_telemetry()
    assert telemetry["paper_safety"]["schema_version"] == 1
    assert telemetry["market_data"]["status"] == "NO_PROVIDER_CONNECTED"
    assert telemetry["options_analytics"]["status"] == "WAITING_FOR_MARKET_DATA"
    assert not telemetry["paper_safety"]["safety"]["live_trading_enabled"]


def test_json_contains_no_external_identity_or_market_data_impersonation(tmp_path):
    session, fence, view = _fixture(tmp_path)
    payload = view.snapshot()
    assert payload["market"]["latest_price"] is None
    assert payload["market"]["provider_identity_verified"] is False
    assert payload["signed_approval"]["external_signer_verified"] is False
    assert payload["evolve"]["stage50_evolve_runtime_connected"] is False
    assert payload["admission_fence"]["direct_legacy_entrypoints_blocked"] is False
    assert not payload["safety"]["global_legacy_entrypoints_fenced"]
    assert not payload["safety"]["combined_capital_authority_verified"]
    assert not payload["safety"]["independent_human_identity_verified"]
    assert not payload["safety"]["production_ready"]
    assert json.loads(json.dumps(payload, allow_nan=False))["schema_version"] == 1


def test_stage50_cli_only_prints_display_data(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [sys.executable, str(repo / "scripts" / "run_stage50_paper_dashboard_smoke.py")],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    assert run.returncode == 0, run.stderr
    evidence = json.loads(run.stdout)
    assert evidence["before"]["status"] == "LOCAL_SYNTHETIC_REVIEW_ONLY"
    assert evidence["after"]["status"] == "LOCAL_REVIEW_REQUIRED"
    assert evidence["before"]["paper_orders"]["total"] == 0
    assert evidence["after"]["paper_orders"]["pending_manual_approval"] == 1
    assert evidence["after"]["admission_fence"]["attempt_count"] == 1
    assert not evidence["after"]["safety"]["production_ready"]
    assert not evidence["after"]["market"]["india_fo_live_data"]
    assert "signature_hex" not in run.stdout

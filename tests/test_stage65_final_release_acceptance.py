"""Stage65 final acceptance governance QA: realistic local source, NO RELEASE.

All quotes/trades are fabricated. Frozen selected GitHub pull request diffs
are file-name overlaps, NOT proved git conflicts or current GitHub attestation.
No authenticated market fills, broker credentials or live order APIs run.
"""
from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import pytest

from nexus_titan.operations.integration_candidate_audit import inspect_stage62_candidate
from nexus_titan.operations.stage65_release_acceptance import (
    Stage65AcceptanceBlocked, Stage65FinalAcceptanceReport,
    inspect_stage65_release_acceptance,
)
from nexus_titan.research.stage61_evidence_scorecard import inspect_stage61_fo_evidence
from nexus_titan.shadow.stage64_trial_governance import inspect_stage64_shadow_trial
from scripts.run_stage61_fo_evidence_smoke import _inputs
from scripts.run_stage64_shadow_trial_smoke import _trial, CAL

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/STAGE65_FINAL_PR_REVIEW_SNAPSHOT_2026-11-03.json"


@pytest.fixture(scope="module")
def context(tmp_path_factory):
    root = tmp_path_factory.mktemp("stage65-qa")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    integration = inspect_stage62_candidate(ROOT, pr_snapshot=snapshot)
    cases = {}
    for market in ("NIFTY", "BANKNIFTY"):
        h, o, synthetic_execution = _inputs(root / market.lower(), market)
        research = inspect_stage61_fo_evidence(h, o, execution=synthetic_execution)
        plan, days = _trial(market)
        trial = inspect_stage64_shadow_trial(
            plan, days, calendar=CAL,
            as_of=datetime.fromisoformat("2026-09-29T12:00:00+05:30"),
            fo_evidence=research, integration=integration,
        )
        cases[market] = (research, trial)
    return snapshot, integration, cases


def _assess(snapshot, integration, research, trial, *, root=ROOT):
    return inspect_stage65_release_acceptance(
        root, pr_snapshot=snapshot, fo_evidence=research,
        trial=trial, integration=integration,
    )


def _always_no_go(r: Stage65FinalAcceptanceReport):
    assert r.schema_version == 1
    assert r.scope == "OFFLINE_DEVELOPER_HANDOFF_CHECKLIST_NO_RELEASE_AUTHORITY"
    for name in (
        "github_current_pr_state_authenticated",
        "branch_protection_independently_verified",
        "two_root_branches_reconciled", "PR_file_conflicts_ruled_out",
        "prospective_merged_commit_ci_verified",
        "independent_security_assessment_verified",
        "globally_unbypassable_risk_veto_verified",
        "single_atomic_capital_ledger_verified",
        "independently_authenticated_human_verified",
        "licensed_real_indian_fo_data_verified",
        "executable_depth_and_costs_verified",
        "real_shadow_trading_performance_verified",
        "crypto_real_market_validation_verified",
        "exact_approved_titan_face_integrated",
        "owner_release_approval_verified", "safe_to_merge",
        "strategy_promotion_authorized", "real_money_trading_enabled",
        "production_ready",
    ):
        assert getattr(r, name) is False, name
    assert r.merges_performed == 0
    assert r.broker_orders_transmitted == 0
    assert r.release_verdict == "NO_GO_OWNER_AND_INDEPENDENT_EVIDENCE_REQUIRED"
    assert r.critical_release_blocker_count == len(r.required_owner_actions) == 13
    assert any(code == "P0-GLOBAL-RISK" for code, _ in r.required_owner_actions)
    assert any(code == "P0-REAL-INDIA-FO-DATA" for code, _ in r.required_owner_actions)
    assert any(code == "P0-CRYPTO-INDEPENDENT" for code, _ in r.required_owner_actions)


@pytest.mark.parametrize("market", ["NIFTY", "BANKNIFTY"])
def test_stage65_55_pr_two_roots_three_overlap_paths_and_permanent_no_go(context, market):
    snapshot, integration, cases = context
    r = _assess(snapshot, integration, *cases[market])
    assert r.reviewed_open_pr_count == 55
    assert r.reported_main_protected is False
    assert r.reported_main_sha == "40e93cfb77fa0650e4f57428c6d77f70bb78d564"
    assert r.main_root_pr_numbers == (1, 3)
    assert r.checked_pr_file_list_count == 4
    assert r.uninspected_pr_file_list_count == 51
    assert not r.all_pr_changed_files_observed
    pair = next(
        x for x in r.independent_file_overlap_candidates
        if x.pr_a == 3 and x.pr_b == 6
    )
    assert pair.paths == (
        "src/nexus_titan/intelligence/__init__.py",
        "src/nexus_titan/intelligence/calibration.py",
        "tests/test_probability_calibration.py",
    )
    assert r.stage64_trial_underlying == market
    assert r.stage64_claimed_closed_trades == 40
    assert r.selected_source_and_ci_structural_review_passed
    assert r.stage61_source_claims_locally_consistent
    assert r.stage64_local_trial_kpis_met
    assert r.developer_offline_checklist_completed
    assert len(r.acceptance_packet_sha256) == 64
    assert len(r.checks) == 5 + 4 + 13
    assert any(c.status == "REVIEW_REQUIRED" for c in r.checks)
    assert any(c.status == "EXTERNAL_EVIDENCE_MISSING" for c in r.checks)
    _always_no_go(r)


def test_source_and_trial_report_read_only_repeatability(context):
    snap, integration, cases = context
    a = _assess(snap, integration, *cases["NIFTY"])
    b = _assess(deepcopy(snap), integration, *cases["NIFTY"])
    assert a == b
    assert asdict(a) == asdict(b)
    assert len(json.dumps(asdict(a), default=str, allow_nan=False)) > 1000
    _always_no_go(a)


@pytest.mark.parametrize("field", [
    "genuine_futures_options_backtest_verified",
    "source_licence_authenticated",
    "actual_execution_or_fees_reconciled",
    "independently_verified_human_identity",
    "strategy_promotion_authorized",
    "production_ready",
    "live_trading_enabled",
    "global_risk_veto_unbypassable",
    "unified_capital_settlement_verified",
])
def test_spoofed_stage61_permission_or_data_source_rejected(context, field):
    snap, integration, cases = context
    research, trial = cases["NIFTY"]
    with pytest.raises(Stage65AcceptanceBlocked, match="unauthorized"):
        _assess(snap, integration, replace(research, **{field: True}), trial)


@pytest.mark.parametrize("field", [
    "data_source_independently_authenticated",
    "real_fill_or_fee_calibration_verified", "genuine_net_pnl_verified",
    "prospectively_signed_trial_plan_verified", "audited_full_portfolio_pnl_verified",
    "independently_verified_human_approval",
    "one_authoritative_capital_authority_verified",
    "global_risk_veto_enforced", "merge_authorized",
    "strategy_promotion_authorized", "live_trading_enabled", "production_ready",
])
def test_spoofed_stage64_external_authority_never_promotes(context, field):
    snap, integration, cases = context
    research, trial = cases["NIFTY"]
    with pytest.raises(Stage65AcceptanceBlocked, match="unauthorized"):
        _assess(snap, integration, research, replace(trial, **{field: True}))


@pytest.mark.parametrize("candidate", [
    {"stage": "fo", "field": "broker_orders_transmitted"},
    {"stage": "trial", "field": "broker_orders_transmitted"},
])
def test_any_real_order_counter_rejected(context, candidate):
    snap, integration, cases = context
    fo, trial = cases["NIFTY"]
    if candidate["stage"] == "fo":
        fo = replace(fo, broker_orders_transmitted=1)
    else:
        trial = replace(trial, broker_orders_transmitted=1)
    with pytest.raises(Stage65AcceptanceBlocked, match="broker orders"):
        _assess(snap, integration, fo, trial)


def test_stage64_empty_mandatory_blocker_set_cannot_be_supplied(context):
    snap, integration, cases = context
    fo, trial = cases["NIFTY"]
    with pytest.raises(Stage65AcceptanceBlocked, match="mismatch"):
        _assess(snap, integration, fo,
                replace(trial, mandatory_external_blockers=()))


def test_stage61_missing_research_blockers_is_rejected(context):
    snap, integration, cases = context
    fo, trial = cases["NIFTY"]
    with pytest.raises(Stage65AcceptanceBlocked, match="mismatch"):
        _assess(snap, integration,
                replace(fo, mandatory_release_blockers=()), trial)


def test_underlying_mismatch_between_trial_and_stage61_rejected(context):
    snap, integration, cases = context
    fo, trial = cases["NIFTY"]
    with pytest.raises(Stage65AcceptanceBlocked, match="mismatch"):
        _assess(snap, integration, fo, replace(trial, underlying="BANKNIFTY"))


def test_stage62_review_not_reusable_on_a_different_source_snapshot(context):
    snap, integration, cases = context
    wrong = deepcopy(snap)
    wrong["main_protected"] = True
    with pytest.raises(Stage65AcceptanceBlocked, match="Stage62 report stale"):
        _assess(wrong, integration, *cases["NIFTY"])


def test_live_branch_protection_claim_cannot_authorize_merge(context):
    snap, _integration, cases = context
    changed = deepcopy(snap)
    changed["main_protected"] = True
    current = inspect_stage62_candidate(ROOT, pr_snapshot=changed)
    fo, trial = cases["NIFTY"]
    trial = replace(trial, stage62_local_static_check_observed=current.local_static_review_passed)
    r = _assess(changed, current, fo, trial)
    assert r.reported_main_protected is True
    assert not r.branch_protection_independently_verified
    _always_no_go(r)


def test_false_full_PR_diff_claim_does_not_clear_independent_ambiguities(context):
    snap, _integration, cases = context
    changed = deepcopy(snap)
    for p in changed["pull_requests"]:
        p["changed_paths_complete"] = True
    current = inspect_stage62_candidate(ROOT, pr_snapshot=changed)
    fo, trial = cases["NIFTY"]
    r = _assess(changed, current, fo,
                replace(trial, stage62_local_static_check_observed=current.local_static_review_passed))
    assert r.all_pr_changed_files_observed is True  # UNTRUSTED OPERATOR CLAIM
    assert r.uninspected_pr_file_list_count == 0
    assert r.PR_file_conflicts_ruled_out is False
    assert r.safe_to_merge is False
    _always_no_go(r)


def test_invalid_child_parent_ref_is_not_rewritten_to_appear_safe(context):
    snap, integration, cases = context
    changed = deepcopy(snap)
    child = next(p for p in changed["pull_requests"] if p["number"] == 56)
    child["base_sha"] = "a" * 40
    with pytest.raises(Stage65AcceptanceBlocked, match="Stage62 report stale"):
        _assess(changed, integration, *cases["NIFTY"])


def test_fabricated_trial_digest_can_be_recomputed_not_authenticated(context):
    snap, integration, cases = context
    fo, trial = cases["NIFTY"]
    original = _assess(snap, integration, fo, trial)
    altered = _assess(snap, integration, fo, replace(trial, local_trial_sha256="f" * 64))
    assert original.acceptance_packet_sha256 != altered.acceptance_packet_sha256
    assert altered.safe_to_merge is False
    assert altered.real_shadow_trading_performance_verified is False
    _always_no_go(altered)


def test_false_local_stage61_consistency_is_reported_not_externally_approved(context):
    snap, integration, cases = context
    fo, trial = cases["NIFTY"]
    fo = replace(fo, local_inputs_structurally_consistent=False)
    trial = replace(trial, stage61_local_structural_check_observed=False)
    r = _assess(snap, integration, fo, trial)
    assert not r.stage61_source_claims_locally_consistent
    assert not r.developer_offline_checklist_completed
    assert any(x.check_id == "S65-STAGE61-SYNTHETIC"
               and x.status == "LOCAL_RESEARCH_FAIL" for x in r.checks)
    _always_no_go(r)


def test_false_trial_local_success_reported_not_authorized(context):
    snap, integration, cases = context
    fo, trial = cases["NIFTY"]
    r = _assess(snap, integration, fo, replace(trial, local_trial_criteria_met=False))
    assert not r.stage64_local_trial_kpis_met
    assert not r.developer_offline_checklist_completed
    _always_no_go(r)


def test_dashboard_missing_static_check_keeps_no_go(monkeypatch, context):
    import nexus_titan.operations.stage65_release_acceptance as stage65
    monkeypatch.setattr(stage65, "_local_static_dashboard", lambda root: False)
    snap, integration, cases = context
    r = _assess(snap, integration, *cases["NIFTY"])
    assert not r.developer_offline_checklist_completed
    assert any(x.check_id == "S65-READONLY-OPERATOR-VIEW"
               and x.status == "LOCAL_RESEARCH_FAIL" for x in r.checks)
    _always_no_go(r)


@pytest.mark.parametrize("root", [None, "not-a-Path", 9])
def test_bad_root_refused(context, root):
    snap, integration, cases = context
    with pytest.raises(Stage65AcceptanceBlocked):
        _assess(snap, integration, *cases["NIFTY"], root=root)


def test_wrong_repo_identifier_does_not_inherit_stage62_root_approval(context):
    snap, _integration, cases = context
    changed = deepcopy(snap)
    changed["repository"] = "other-owner/other-project"
    current = inspect_stage62_candidate(ROOT, pr_snapshot=changed)
    fo, trial = cases["NIFTY"]
    with pytest.raises(Stage65AcceptanceBlocked, match="wrong GitHub"):
        _assess(changed, current, fo, replace(
            trial, stage62_local_static_check_observed=current.local_static_review_passed,
        ))


def test_invalid_snapshot_missing_path_or_head_name_fails_closed(context):
    snap, integration, cases = context
    for broken in ("../bad", "", "bad\\path"):
        changed = deepcopy(snap)
        changed["pull_requests"][0]["head_ref"] = broken
        with pytest.raises(Stage65AcceptanceBlocked):
            _assess(changed, integration, *cases["NIFTY"])


def test_missing_stage61_stage62_or_trial_objects_fail_closed(context):
    snap, integration, cases = context
    fo, trial = cases["NIFTY"]
    with pytest.raises(Stage65AcceptanceBlocked):
        _assess(snap, integration, object(), trial)
    with pytest.raises(Stage65AcceptanceBlocked):
        _assess(snap, integration, fo, object())
    with pytest.raises(Stage65AcceptanceBlocked):
        _assess(snap, object(), fo, trial)


def test_stage65_cli_uses_real_code_and_frozen_github_pr_paths_only():
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage65_final_acceptance.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=65,
    )
    assert p.returncode == 0, p.stderr
    output = json.loads(p.stdout)
    assert output["mode"] == "STAGE65_OFFLINE_FINAL_ACCEPTANCE_NO_GO_ONLY"
    assert output["synthetic_untrusted_market_input_only"] is True
    assert output["frozen_pr_snapshot_not_live"] is True
    assert output["real_broker_data_or_identity_present"] is False
    assert output["merged_tree_ci_performed"] is False
    assert output["merges_performed"] == 0
    assert output["broker_orders_transmitted"] == 0
    assert output["production_ready"] is False
    for market in ("nifty", "banknifty"):
        r = output[market]
        assert r["local_selected_code_checks"] is True
        assert r["local_synthetic_trial_criteria_met"] is True
        assert r["developer_offline_checklist_completed"] is True
        assert r["observed_open_pr_count_at_snapshot"] == 55
        assert r["root_pr_numbers"] == [1, 3]
        assert r["fully_listed_pr_diff_count"] == 4
        assert r["pr_diff_lists_uninspected_count"] == 51
        assert r["all_pr_changed_files_observed"] is False
        assert len(r["independent_overlap_candidates"]) >= 1
        assert len(r["owner_actions"]) == 13
        assert r["release_verdict"] == "NO_GO_OWNER_AND_INDEPENDENT_EVIDENCE_REQUIRED"
        assert r["safe_to_merge"] is False
        assert r["production_ready"] is False
        assert r["broker_orders_transmitted"] == 0
        assert r["real_money_trading_enabled"] is False

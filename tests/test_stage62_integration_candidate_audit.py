"""Stage62 adversarial full-stack source/PR/CI audit with no merge authority.

Exercise selected real code source, Stage46 frozen graph, Stage52 subset,
Stage56 legacy API inventory and CI config without executing order paths.
There is no validated real exchange F&O history or broker connection.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest

from nexus_titan.operations.integration_candidate_audit import (
    _IMPORT_EDGES, _WORKFLOW_REQUIREMENTS, inspect_stage62_candidate,
)
from nexus_titan.operations.pr_stack_audit import StackAuditError
from nexus_titan.operations.release_security_audit import (
    _FRONTEND_FILES, _REVIEWED_CODE,
)
from nexus_titan.operations.risk_boundary_inventory import _KNOWN_DIRECT_SURFACES


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "STAGE62_PR_DEPENDENCY_SNAPSHOT_2026-11-03.json"
SCRIPT = ROOT / "scripts" / "run_stage62_integration_audit.py"


def _snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _full_copy(dst):
    needed = set(_REVIEWED_CODE) | set(_FRONTEND_FILES)
    needed.update(_KNOWN_DIRECT_SURFACES)
    needed.add(".github/workflows/ci.yml")
    needed.update(f"src/nexus_titan/{src}.py" for src, _, _ in _IMPORT_EDGES)
    needed.update(f"src/nexus_titan/{dstmod}.py" for _, dstmod, _ in _IMPORT_EDGES)
    for name in needed:
        target = dst / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return dst


def _assert_all_authority_denied(report):
    assert report.schema_version == 1
    assert report.scope == "NO_MERGE_FROZEN_PR_AND_SELECTED_SOURCE_AST_CI_REVIEW_ONLY"
    assert report.github_current_state_independently_verified is False
    assert report.main_branch_protection_independently_verified is False
    assert report.independent_root_stacks_reconciled is False
    assert report.complete_file_diff_conflicts_ruled_out is False
    assert report.prospective_merged_tree_ci_verified is False
    assert report.independent_risk_and_execution_fenced is False
    assert report.one_authoritative_cross_ledger_capital_verified is False
    assert report.authenticated_real_fo_history_and_licence_verified is False
    assert report.independently_verified_human_identity is False
    assert report.owner_merge_approval_verified is False
    assert report.merge_authorized is False
    assert report.real_money_trading_enabled is False
    assert report.strategy_promotion_authorized is False
    assert report.production_ready is False
    assert report.merges_performed == 0
    assert report.broker_orders_transmitted == 0
    assert len(report.blockers) >= 12


def test_actual_frozen_open_pr_stack_and_source_contracts_still_no_go():
    result = inspect_stage62_candidate(ROOT, pr_snapshot=_snapshot())
    assert result.frozen_pr_count == 52
    assert result.frozen_main_sha == "40e93cfb77fa0650e4f57428c6d77f70bb78d564"
    assert result.frozen_main_protected_reported is False
    assert result.frozen_root_prs == (1, 3)
    assert result.frozen_changed_paths_complete is False
    assert result.local_source_structure_passed
    assert result.local_cross_module_import_contracts_passed
    assert result.local_ci_workflow_contracts_passed
    assert result.local_static_review_passed
    assert result.source_subset_sha256 is not None
    assert len(result.source_subset_sha256) == 64
    assert len(result.frozen_pr_snapshot_sha256) == 64
    assert len(result.checks) == len(_IMPORT_EDGES) + len(_WORKFLOW_REQUIREMENTS) + 2
    assert all(check.passed for check in result.checks)
    assert "VirtualAccount.execute_fill" in result.local_reviewed_legacy_entrypoints
    assert "VirtualAccount.submit_order" in result.local_reviewed_legacy_entrypoints
    assert any("Independent main-rooted" in b for b in result.blockers)
    assert any("UNPROTECTED" in b for b in result.blockers)
    assert any("UNKNOWN" in b for b in result.blockers)
    _assert_all_authority_denied(result)


def test_audit_is_repeatable_and_does_not_mutate_local_source():
    frozen = _snapshot()
    original = SNAPSHOT.read_bytes()
    a = inspect_stage62_candidate(ROOT, pr_snapshot=frozen)
    b = inspect_stage62_candidate(ROOT, pr_snapshot=deepcopy(frozen))
    assert a == b
    assert SNAPSHOT.read_bytes() == original
    assert asdict(a) == asdict(b)
    json.dumps(asdict(a), sort_keys=True, allow_nan=False)
    _assert_all_authority_denied(a)


@pytest.mark.parametrize("module_symbol", [
    ("research/stage61_evidence_scorecard", "Stage60OfflineResearchReport"),
    ("research/stage60_purged_oos", "Stage59FuturesHistory"),
    ("data/stage59_futures_history", "inspect_candle_batch"),
    ("simulation/stage58_execution_stress", "MicrostructureSimulator"),
    ("operations/local_approval_risk_review", "Stage48ApprovalChallenge"),
    ("operations/multi_ledger_recovery_audit", "Stage53SyntheticCapitalAuthority"),
])
def test_missing_expected_local_module_import_is_integration_conflict(tmp_path, module_symbol):
    name, symbol = module_symbol
    folder = _full_copy(tmp_path)
    p = folder / "src" / "nexus_titan" / (name + ".py")
    src = p.read_text()
    assert symbol in src
    # Replace only the name in IMPORT AST, without mutating the target
    # file or attempting to execute a potentially broken module.
    tree_marker = symbol
    p.write_text(src.replace(tree_marker, "STAGE62_MISSING_SYMBOL"))
    report = inspect_stage62_candidate(folder, pr_snapshot=_snapshot())
    assert not report.local_cross_module_import_contracts_passed
    assert not report.local_static_review_passed
    assert report.source_subset_sha256 is None
    assert any(
        x.check_id.startswith("S62-IMPORT-") and not x.passed for x in report.checks
    )
    _assert_all_authority_denied(report)


def test_local_import_missing_target_source_is_unknown_not_safe(tmp_path):
    root = _full_copy(tmp_path)
    target = root / "src/nexus_titan/data/stage59_futures_history.py"
    target.unlink()
    review = inspect_stage62_candidate(root, pr_snapshot=_snapshot())
    assert not review.local_source_structure_passed
    assert not review.local_cross_module_import_contracts_passed
    assert not review.local_static_review_passed
    assert review.source_subset_sha256 is None
    _assert_all_authority_denied(review)


def test_import_source_syntax_invalid_fails_without_executing_malicious_code(tmp_path):
    root = _full_copy(tmp_path)
    target = root / "src/nexus_titan/simulation/stage58_execution_stress.py"
    target.write_text("def unsafe(:\n    this_should_not_execute()\n")
    review = inspect_stage62_candidate(root, pr_snapshot=_snapshot())
    assert not review.local_cross_module_import_contracts_passed
    assert review.source_subset_sha256 is None
    _assert_all_authority_denied(review)


@pytest.mark.parametrize("removed", [
    "  pull_request:",
    "  push:",
    "  contents: read",
    "'3.13'",
    "run: python scripts/run_project_validation.py",
    "run: python scripts/run_stage25_full_research_audit.py",
])
def test_missing_ci_safeguard_is_flagged_and_does_not_pass(tmp_path, removed):
    root = _full_copy(tmp_path)
    p = root / ".github/workflows/ci.yml"
    contents = p.read_text()
    assert removed in contents
    p.write_text(contents.replace(removed, "REMOVED-BY-STAGE62-TEST", 1))
    review = inspect_stage62_candidate(root, pr_snapshot=_snapshot())
    assert not review.local_ci_workflow_contracts_passed
    assert not review.local_static_review_passed
    assert review.source_subset_sha256 is None
    assert any(not x.passed and x.check_id.startswith("S62-CI-") for x in review.checks)
    _assert_all_authority_denied(review)


def test_symlink_ci_workflow_rejected_without_following_external_path(tmp_path):
    root = _full_copy(tmp_path / "repo")
    workflow = root / ".github/workflows/ci.yml"
    external = tmp_path / "untrusted.yml"
    external.write_text(workflow.read_text())
    workflow.unlink()
    try:
        workflow.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported")
    report = inspect_stage62_candidate(root, pr_snapshot=_snapshot())
    assert not report.local_ci_workflow_contracts_passed
    assert report.source_subset_sha256 is None
    _assert_all_authority_denied(report)


def test_missing_known_order_api_is_not_proof_global_risk_fenced(tmp_path):
    root = _full_copy(tmp_path)
    p = root / "src/nexus_titan/virtual/order_manager.py"
    p.write_text(p.read_text().replace("def execute_fill(", "def renamed_fill(", 1))
    report = inspect_stage62_candidate(root, pr_snapshot=_snapshot())
    assert not report.local_static_review_passed
    assert not report.local_source_structure_passed
    assert "VirtualAccount.execute_fill" not in report.local_reviewed_legacy_entrypoints
    assert report.independent_risk_and_execution_fenced is False
    _assert_all_authority_denied(report)


def test_reported_protection_true_still_not_independently_verified():
    changed = _snapshot()
    changed["main_protected"] = True
    result = inspect_stage62_candidate(ROOT, pr_snapshot=changed)
    assert result.frozen_main_protected_reported is True
    assert not result.main_branch_protection_independently_verified
    assert result.merge_authorized is False
    _assert_all_authority_denied(result)


def test_fake_full_file_coverage_still_does_not_prove_merge_ready():
    changed = _snapshot()
    for p in changed["pull_requests"]:
        p["changed_paths_complete"] = True
    result = inspect_stage62_candidate(ROOT, pr_snapshot=changed)
    assert result.frozen_changed_paths_complete
    assert result.complete_file_diff_conflicts_ruled_out is False
    assert result.prospective_merged_tree_ci_verified is False
    _assert_all_authority_denied(result)


def test_explicit_stale_parent_sha_will_be_reported_as_graph_blocker():
    changed = _snapshot()
    child = next(p for p in changed["pull_requests"] if p["number"] == 53)
    child["base_sha"] = "f" * 40
    result = inspect_stage62_candidate(ROOT, pr_snapshot=changed)
    assert not result.frozen_topology_consistent
    assert any("SHA mismatch" in b for b in result.blockers)
    _assert_all_authority_denied(result)


@pytest.mark.parametrize("variant", [
    lambda s: s.update(main_sha="invalid"),
    lambda s: s.update(schema_version=True),
    lambda s: s.update(main_ref="prod"),
    lambda s: s["pull_requests"][0].update(head_ref="../bad"),
])
def test_invalid_github_snapshot_rejected_fail_closed(variant):
    s = _snapshot()
    variant(s)
    with pytest.raises(StackAuditError):
        inspect_stage62_candidate(ROOT, pr_snapshot=s)


@pytest.mark.parametrize("bad", ["not-path", None, 7])
def test_invalid_repo_root_is_rejected(bad):
    with pytest.raises(TypeError):
        inspect_stage62_candidate(bad, pr_snapshot=_snapshot())


def _cli(*args):
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        text=True, capture_output=True, cwd=ROOT, timeout=40,
    )
    return p, json.loads(p.stdout)


def test_cli_reports_structural_review_but_still_blocks_merges():
    run, result = _cli()
    assert run.returncode == 0, run.stderr
    assert result["mode"] == "STAGE62_FROZEN_SNAPSHOT_NO_MERGE_LOCAL_AST_ONLY"
    assert result["local_static_review_passed"] is True
    assert result["frozen_pr_count"] == 52
    assert result["frozen_root_prs"] == [1, 3]
    assert result["frozen_changed_paths_complete"] is False
    assert result["merge_authorized"] is False
    assert result["production_ready"] is False
    assert result["broker_orders_transmitted"] == 0
    assert result["prospective_merged_tree_ci_verified"] is False


@pytest.mark.parametrize("bad", [
    '{"schema_version":1,"schema_version":1}',
    '{"schema_version":NaN}',
    "not-json",
    '{"schema_version":Infinity}',
])
def test_cli_strict_json_parser_denies_bogus_snapshots(tmp_path, bad):
    p = tmp_path / "bogus.json"
    p.write_text(bad)
    run, data = _cli("--snapshot", p)
    assert run.returncode == 2
    assert data["local_static_review_passed"] is False
    assert data["merge_authorized"] is False
    assert data["production_ready"] is False


def test_cli_bad_repo_root_is_negative_json(tmp_path):
    run, data = _cli("--root", tmp_path / "not-found")
    assert run.returncode == 2
    assert data["local_static_review_passed"] is False
    assert data["real_money_trading_enabled"] is False
    assert data["broker_orders_transmitted"] == 0


def test_cli_rejects_snapshot_symlink(tmp_path):
    original = tmp_path / "original.json"
    original.write_text(SNAPSHOT.read_text())
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unsupported")
    run, data = _cli("--snapshot", linked)
    assert run.returncode == 2
    assert data["merge_authorized"] is False


def test_cli_oversized_snapshot_refused(tmp_path):
    p = tmp_path / "huge.json"
    p.write_bytes(b"x" * (512 * 1024 + 1))
    run, result = _cli("--snapshot", p)
    assert run.returncode == 2
    assert result["broker_orders_transmitted"] == 0

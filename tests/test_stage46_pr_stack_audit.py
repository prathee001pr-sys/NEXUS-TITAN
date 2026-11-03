"""Stage46 PR graph audit synthetic regressions + frozen snapshot smoke.

No GitHub network operations, pull-request merges, market-data or broker calls.
"""
from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from nexus_titan.operations.pr_stack_audit import (
    StackAuditError, inspect_pr_dependency_snapshot,
)


def sha(i: int) -> str:
    return f"{i:040x}"


def _node(number, base, parent_sha, *, paths=(), complete=True):
    return {
        "number": number,
        "head_ref": f"feature/branch-{number}",
        "head_sha": sha(number),
        "base_ref": base,
        "base_sha": parent_sha,
        "state": "open",
        "draft": True,
        "merged": False,
        "changed_paths_complete": complete,
        "changed_paths": list(paths) if complete else [],
    }


def _snapshot():
    return {
        "schema_version": 1,
        "repository": "research/test",
        "captured_at_utc": "2026-11-03T04:00:00Z",
        "main_ref": "main",
        "main_sha": sha(100),
        "main_protected": False,
        "pull_requests": [
            _node(1, "main", sha(100), paths=["README.md"]),
            _node(3, "main", sha(100), paths=["src/calibration.py"]),
            _node(5, "feature/branch-3", sha(3), paths=["src/calibration.py", "docs/review.md"]),
            _node(6, "feature/branch-1", sha(1), paths=["src/calibration.py", "src/risk.py"]),
        ],
    }


def test_two_root_stacks_report_known_overlap_and_no_merge_authority():
    out = inspect_pr_dependency_snapshot(_snapshot())
    assert out.pr_count == 4
    assert out.root_pr_numbers == (1, 3)
    assert out.topological_pr_numbers == (1, 3, 5, 6)
    assert out.branch_graph_consistent
    assert out.complete_changed_file_coverage
    assert {(x.pr_a, x.pr_b): x.paths for x in out.overlap_candidates} == {
        (3, 6): ("src/calibration.py",),
        (5, 6): ("src/calibration.py",),
    }
    assert any("main branch protection" in b for b in out.blockers)
    assert not out.independently_verified_current_github_state
    assert not out.independently_verified_branch_protection
    assert not out.three_way_merge_conflicts_ruled_out
    assert not out.merged_commit_ci_verified
    assert not out.owner_merge_approval_verified
    assert not out.all_relevant_prs_merge_ready
    assert out.merges_performed == 0
    assert out.live_orders_transmitted == 0
    assert not out.production_ready


def test_parent_child_file_overlap_not_misreported_as_independent():
    out = inspect_pr_dependency_snapshot(_snapshot())
    assert not any((p.pr_a, p.pr_b) == (3, 5) for p in out.overlap_candidates)


def test_valid_single_root_still_never_authorizes_merge():
    snapshot = _snapshot()
    snapshot["pull_requests"] = [snapshot["pull_requests"][0], snapshot["pull_requests"][3]]
    report = inspect_pr_dependency_snapshot(snapshot)
    assert report.root_pr_numbers == (1,)
    assert report.branch_graph_consistent
    assert report.topological_pr_numbers == (1, 6)
    assert not report.all_relevant_prs_merge_ready


def test_main_protection_yes_is_only_snapshot_assertion():
    snapshot = _snapshot()
    snapshot["main_protected"] = True
    report = inspect_pr_dependency_snapshot(snapshot)
    assert report.main_protected_reported
    assert not report.independently_verified_branch_protection
    assert not report.all_relevant_prs_merge_ready


@pytest.mark.parametrize("field, value", [
    ("main_sha", "wrong"), ("main_ref", "master"),
    ("main_protected", 1), ("captured_at_utc", "not-a-date"),
    ("captured_at_utc", "2026-11-03T04:00:00+05:30"),
    ("schema_version", 0), ("schema_version", True),
    ("repository", "../attack"), ("repository", "owner/.."), ("repository", "./repo"),
])
def test_invalid_top_level_claims_rejected(field, value):
    doc = _snapshot()
    doc[field] = value
    with pytest.raises(StackAuditError):
        inspect_pr_dependency_snapshot(doc)


@pytest.mark.parametrize("change", [
    ("number", True), ("number", -10),
    ("head_ref", "../stolen"), ("head_ref", "feature//duplicate"),
    ("head_sha", "A"), ("state", "MERGED"),
    ("draft", "true"), ("merged", 0),
    ("base_sha", "not-sha"),
    ("changed_paths_complete", "yes"),
    ("changed_paths", ["../secrets.txt"]),
    ("changed_paths", ["/absolute/path"]),
    ("changed_paths", ["dup.py", "dup.py"]),
    ("changed_paths", ["file\\name"]),
])
def test_malformed_pr_items_rejected(change):
    snapshot = _snapshot()
    snapshot["pull_requests"][0][change[0]] = change[1]
    with pytest.raises(StackAuditError):
        inspect_pr_dependency_snapshot(snapshot)


def test_duplicate_pr_id_or_head_is_rejected():
    doc = _snapshot()
    doc["pull_requests"].append(deepcopy(doc["pull_requests"][0]))
    with pytest.raises(StackAuditError, match="Duplicate PR"):
        inspect_pr_dependency_snapshot(doc)
    doc = _snapshot()
    doc["pull_requests"][1]["head_ref"] = doc["pull_requests"][0]["head_ref"]
    with pytest.raises(StackAuditError):
        inspect_pr_dependency_snapshot(doc)


def test_stale_parent_branch_sha_fails_closed():
    doc = _snapshot()
    doc["pull_requests"][3]["base_sha"] = sha(444)
    out = inspect_pr_dependency_snapshot(doc)
    assert not out.branch_graph_consistent
    assert any("parent branch SHA mismatch" in x for x in out.blockers)
    assert not out.all_relevant_prs_merge_ready


def test_unknown_or_unexported_parent_never_appears_safe():
    doc = _snapshot()
    doc["pull_requests"][3]["base_ref"] = "feature/missing"
    out = inspect_pr_dependency_snapshot(doc)
    assert not out.branch_graph_consistent
    assert any("missing from exported" in x for x in out.blockers)


def test_actual_parent_cycle_is_reported_and_no_topological_release():
    doc = _snapshot()
    doc["pull_requests"][0]["base_ref"] = "feature/branch-6"
    doc["pull_requests"][0]["base_sha"] = sha(6)
    out = inspect_pr_dependency_snapshot(doc)
    assert not out.branch_graph_consistent
    assert len(out.topological_pr_numbers) < out.pr_count
    assert any("cycle" in x for x in out.blockers)


def test_closed_or_already_merged_pr_blocks_integration_readiness():
    doc = _snapshot()
    doc["pull_requests"][0]["state"] = "closed"
    doc["pull_requests"][0]["draft"] = False
    doc["pull_requests"][0]["merged"] = True
    out = inspect_pr_dependency_snapshot(doc)
    assert any("not an open unmerged draft" in b for b in out.blockers)
    assert not out.all_relevant_prs_merge_ready


def test_partial_file_lists_keep_unknown_conflicts_visible():
    doc = _snapshot()
    doc["pull_requests"][1]["changed_paths_complete"] = False
    doc["pull_requests"][1]["changed_paths"] = []
    out = inspect_pr_dependency_snapshot(doc)
    assert not out.complete_changed_file_coverage
    assert not out.three_way_merge_conflicts_ruled_out
    assert any("Not all PRs" in x for x in out.blockers)


def test_unacknowledged_partial_path_data_is_invalid():
    doc = _snapshot()
    doc["pull_requests"][1]["changed_paths_complete"] = False
    with pytest.raises(StackAuditError, match="ambiguous"):
        inspect_pr_dependency_snapshot(doc)


def _cli(tmp_path, raw):
    snap = tmp_path / "snapshot.json"
    snap.write_text(raw, encoding="utf-8")
    repo = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / "run_stage46_pr_stack_audit.py"),
         "--snapshot", str(snap)],
        cwd=repo, text=True, capture_output=True, check=False,
    )


def test_cli_readonly_success_never_reports_merge_ready(tmp_path):
    raw = json.dumps(_snapshot())
    proc = _cli(tmp_path, raw)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["mode"] == "OFFLINE_PR_SNAPSHOT_REVIEW_ONLY"
    assert report["pr_count"] == 4
    assert report["all_relevant_prs_merge_ready"] is False
    assert report["merges_performed"] == 0
    assert (tmp_path / "snapshot.json").read_text(encoding="utf-8") == raw


def test_cli_rejects_duplicate_json_keys_and_oversized_input(tmp_path):
    doc = _snapshot()
    raw = json.dumps(doc)
    duplicated = raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    bad = _cli(tmp_path, duplicated)
    assert bad.returncode == 2
    assert "Duplicate JSON property" in bad.stderr
    huge = _cli(tmp_path, " " * (512 * 1024 + 1))
    assert huge.returncode == 2


def test_cli_rejects_symlink_snapshot(tmp_path):
    root = Path(__file__).resolve().parents[1]
    target = tmp_path / "true.json"
    target.write_text(json.dumps(_snapshot()), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    proc = subprocess.run([
        sys.executable, str(root / "scripts" / "run_stage46_pr_stack_audit.py"),
        "--snapshot", str(link),
    ], cwd=root, text=True, capture_output=True, check=False)
    assert proc.returncode == 2


def test_frozen_real_pr_snapshot_graph_audited_without_network():
    root = Path(__file__).resolve().parents[1]
    frozen = root / "docs" / "STAGE46_PR_STACK_SNAPSHOT_2026-11-03.json"
    content = json.loads(frozen.read_text(encoding="utf-8"))
    result = inspect_pr_dependency_snapshot(content)
    assert result.pr_count == 36
    assert result.root_pr_numbers == (1, 3)
    assert result.branch_graph_consistent
    assert len(result.topological_pr_numbers) == 36
    assert result.main_protected_reported is False
    assert not result.complete_changed_file_coverage
    assert any("src/nexus_titan/intelligence/calibration.py" in c.paths
               for c in result.overlap_candidates)
    assert result.merges_performed == 0
    assert not result.all_relevant_prs_merge_ready

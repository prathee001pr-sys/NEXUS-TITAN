"""Stage80: full PR-stack snapshot and synthetic F&O cutover fail-closed QA.

All evidence is an untrusted, frozen GitHub export and locally inspected source.
No merge, broker, actual shadow trading, owner authorization or live trading.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from nexus_titan.operations import stage80_integration_candidate_gate as module
from nexus_titan.operations.stage80_integration_candidate_gate import (
    Stage80CutoverBlocked, inspect_stage80_integration_candidate,
)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/STAGE80_FROZEN_OPEN_PR_SNAPSHOT_2026-11-04.json"


def snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def audit(data=None):
    return inspect_stage80_integration_candidate(
        ROOT, frozen_snapshot=snapshot() if data is None else data,
    )


def test_current_pr_graph_and_stage79_FO_cutover_local_contracts():
    result = audit()
    assert result.frozen_open_pr_count == 71
    assert result.frozen_main_protected is False
    assert result.independent_root_prs == (1, 3)
    assert result.graph_topology_locally_consistent
    assert result.changed_file_lists_complete is False
    assert result.changed_file_lists_observed == 4
    assert result.stage78_direct_legacy_method_count >= 12
    assert result.stage78_legacy_paths_still_callable
    assert result.stage79_local_sqlite_cas_shape_locally_inspected
    assert result.stage77_cooperative_cas_call_sites_locally_inspected == 3
    assert result.full_chain_synthetic_e2e_test_count == 3
    assert len(result.source_manifest_sha256) == 64
    assert len(result.frozen_pr_snapshot_sha256) == 64
    assert len(result.action_blockers) >= 8
    assert result.verdict.endswith("NO_GO")
    assert result == audit()
    for name in (
        "current_github_pr_state_independently_authenticated",
        "actual_git_merge_conflicts_ruled_out",
        "signed_merge_candidate_verified",
        "prospective_merged_commit_ci_verified",
        "main_branch_protection_independently_verified",
        "all_legacy_order_fill_paths_unbypassably_fenced",
        "global_atomic_capital_and_risk_admission_verified",
        "independently_authenticated_market_and_kill_telemetry",
        "actual_shadow_trading_validated",
        "owner_merge_approval_authenticated",
        "merge_authorized", "paper_order_authorized",
        "strategy_promotion_authorized", "live_trading_enabled",
    ):
        assert getattr(result, name) is False
    assert result.broker_orders_transmitted == 0


def test_snapshot_topology_is_not_stripped_or_assumed_one_root():
    d = snapshot()
    d["pull_requests"] = [r for r in d["pull_requests"] if r["number"] != 1]
    with pytest.raises(Stage80CutoverBlocked, match="topology"):
        audit(d)


def test_unsafe_main_branch_protection_claim_is_not_fabricated():
    d = snapshot()
    d["main_protected"] = True
    with pytest.raises(Stage80CutoverBlocked, match="graph"):
        audit(d)


def test_inconsistent_main_sha_is_not_silent():
    d = snapshot()
    d["main_sha"] = "0"*40
    with pytest.raises(Stage80CutoverBlocked, match="graph"):
        audit(d)


def test_pr_duplicate_head_and_parent_dependency_errors_fail_closed():
    d = snapshot()
    d["pull_requests"].append(copy.deepcopy(d["pull_requests"][0]))
    with pytest.raises(Stage80CutoverBlocked, match="topology"):
        audit(d)
    d = snapshot()
    d["pull_requests"][-1]["base_ref"] = "not-in-snapshot"
    with pytest.raises(Stage80CutoverBlocked, match="graph"):
        audit(d)


def test_forged_all_file_lists_complete_is_not_merge_proof():
    d = snapshot()
    for pr in d["pull_requests"]:
        pr["changed_paths_complete"] = True
    with pytest.raises(Stage80CutoverBlocked, match="graph"):
        audit(d)


def test_path_traversal_in_git_PR_snapshot_rejected():
    d = snapshot()
    d["pull_requests"][0]["changed_paths_complete"] = True
    d["pull_requests"][0]["changed_paths"] = ["../../secret"]
    with pytest.raises(Stage80CutoverBlocked, match="topology"):
        audit(d)


def patched_source(monkeypatch, path_suffix, original, changed):
    original_read = module._read
    def patch(root, rel):
        contents = original_read(root, rel)
        if rel == path_suffix:
            decoded = contents.decode("utf-8")
            assert original in decoded
            return decoded.replace(original, changed, 1).encode("utf-8")
        return contents
    monkeypatch.setattr(module, "_read", patch)


def test_unprotected_stage55_comparison_direction_is_detected(monkeypatch):
    patched_source(
        monkeypatch, module._STAGE55,
        "expected_revision != rev", "expected_revision == rev",
    )
    with pytest.raises(Stage80CutoverBlocked, match="inequality"):
        audit()


def test_removed_stage55_CAS_forwarding_is_detected(monkeypatch):
    patched_source(
        monkeypatch, module._STAGE55,
        "expected_revision=expected_revision,",
        "expected_revision=None,",
    )
    with pytest.raises(Stage80CutoverBlocked, match="fails to forward"):
        audit()


def test_missing_stage77_gateway_CAS_keyword_is_detected(monkeypatch):
    patched_source(
        monkeypatch, module._STAGE77,
        "expected_revision=current.revision,",
        "expected_revision=None,",
    )
    with pytest.raises(Stage80CutoverBlocked, match="misses exact-head"):
        audit()


def test_missing_stage77_cancel_CAS_keyword_is_detected(monkeypatch):
    original_read = module._read
    def patch(root, rel):
        raw = original_read(root, rel)
        if rel != module._STAGE77:
            return raw
        s = raw.decode("utf-8")
        needle = "order_id=request_id, cancel_id=cancel_id,"
        anchor = s.index(needle)
        start = s.index("expected_journal_tip=current.journal_tip", anchor)
        s = s[:start] + s[start:].replace(
            "expected_journal_tip=current.journal_tip",
            "expected_journal_tip=None", 1,
        )
        return s.encode("utf-8")
    monkeypatch.setattr(module, "_read", patch)
    with pytest.raises(Stage80CutoverBlocked, match="misses exact-head"):
        audit()


def test_removed_gateway_active_head_drift_check_rejected(monkeypatch):
    patched_source(
        monkeypatch, module._STAGE77,
        "status.journal_tip != self._expected_tip",
        "status.journal_tip != '0'*64",
    )
    with pytest.raises(Stage80CutoverBlocked, match="head-drift"):
        audit()


def test_removed_full_chain_FO_test_denies_checklist(monkeypatch):
    patched_source(
        monkeypatch, module._E2E,
        "test_real_python_calls_connect_synthetic_csv_all_the_way_to_sqlite",
        "renamed_not_a_test",
    )
    with pytest.raises(Stage80CutoverBlocked, match="tests missing"):
        audit()


def test_missing_root_and_symlink_do_not_pass():
    with pytest.raises(Stage80CutoverBlocked, match="ordinary repository"):
        inspect_stage80_integration_candidate(
            Path("/missing/stage80/project/root"), frozen_snapshot=snapshot(),
        )


def test_cli_only_writes_NO_GO_local_JSON():
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage80_integration_candidate.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert p.returncode == 0, p.stderr
    report = json.loads(p.stdout)
    assert report["frozen_open_pr_count"] == 71
    assert report["independent_root_prs"] == [1, 3]
    assert report["changed_file_lists_complete"] is False
    assert report["stage77_cooperative_cas_call_sites_locally_inspected"] == 3
    assert report["global_atomic_capital_and_risk_admission_verified"] is False
    assert report["merge_authorized"] is False
    assert report["paper_order_authorized"] is False
    assert report["live_trading_enabled"] is False
    assert report["broker_orders_transmitted"] == 0
    assert report["verdict"].endswith("NO_GO")

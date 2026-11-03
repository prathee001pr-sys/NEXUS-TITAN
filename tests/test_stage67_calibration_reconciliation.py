"""Stage67 research calibration lineage manual reconciliation tests."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus_titan.operations.stage67_calibration_reconcile import (
    PR5_BLOBS, PRIMARY_INIT_BLOB, Stage67LineageError,
    _git_blob_sha, inspect_stage67_calibration_reconciliation,
)

ROOT = Path(__file__).resolve().parents[1]


def temp_source(tmp_path: Path) -> Path:
    paths = [p for p, _ in PR5_BLOBS]
    paths.append("src/nexus_titan/intelligence/__init__.py")
    for rel in paths:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return tmp_path


def test_original_calibration_child_pr_blob_ids_match_complete_candidate():
    report = inspect_stage67_calibration_reconciliation(ROOT)
    assert report.independent_root_pr == 3
    assert report.independent_hardening_pr == 5
    assert report.byte_identical_pr5_path_count == 4
    assert report.inspected_git_blob_pairs == PR5_BLOBS
    assert report.expanded_primary_intelligence_exports_retained
    assert report.frozen_source_lineage_check_passed
    assert _git_blob_sha((ROOT / "src/nexus_titan/intelligence/__init__.py").read_bytes()) == PRIMARY_INIT_BLOB
    assert not report.current_github_ancestry_verified
    assert not report.complete_integrated_diff_review_verified
    assert not report.three_way_conflict_freedom_independently_verified
    assert not report.prospective_combined_tree_ci_verified
    assert not report.main_branch_merged
    assert not report.merge_authorized
    assert not report.production_ready
    assert not report.strategy_promotion_authorized
    assert not report.real_money_trading_enabled
    assert report.broker_orders_transmitted == 0


def test_no_mutation_of_byte_identical_snapshot(tmp_path):
    home = temp_source(tmp_path)
    before = [(p, (home / p).read_bytes()) for p, _ in PR5_BLOBS]
    a = inspect_stage67_calibration_reconciliation(home)
    b = inspect_stage67_calibration_reconciliation(home)
    assert a == b
    assert before == [(p, (home / p).read_bytes()) for p, _ in PR5_BLOBS]


@pytest.mark.parametrize("relative", [p for p, _ in PR5_BLOBS] + [
    "src/nexus_titan/intelligence/__init__.py",
])
def test_modified_any_source_or_export_file_fails_closed(tmp_path, relative):
    home = temp_source(tmp_path)
    with (home / relative).open("ab") as stream:
        stream.write(b"\n# unreviewed drift\n")
    with pytest.raises(Stage67LineageError):
        inspect_stage67_calibration_reconciliation(home)


def test_missing_or_symlinked_calibration_source_fails_closed(tmp_path):
    home = temp_source(tmp_path)
    relative = PR5_BLOBS[0][0]
    target = home / relative
    target.unlink()
    with pytest.raises(Stage67LineageError, match="missing"):
        inspect_stage67_calibration_reconciliation(home)
    target.symlink_to(ROOT / relative)
    with pytest.raises(Stage67LineageError, match="symlinked"):
        inspect_stage67_calibration_reconciliation(home)


def test_invalid_source_size_fails_closed(tmp_path):
    home = temp_source(tmp_path)
    (home / PR5_BLOBS[0][0]).write_bytes(b"X" * (128 * 1024 + 1))
    with pytest.raises(Stage67LineageError, match="size"):
        inspect_stage67_calibration_reconciliation(home)


def test_actual_cli_reports_no_release_permission_even_when_files_match(tmp_path):
    cmd = ROOT / "scripts" / "run_stage67_calibration_reconciliation.py"
    proc = subprocess.run([sys.executable, str(cmd)],
                          cwd=ROOT, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["byte_identical_pr5_path_count"] == 4
    assert payload["merge_authorized"] is False
    assert payload["production_ready"] is False
    assert payload["broker_orders_transmitted"] == 0
    home = temp_source(tmp_path)
    (home / PR5_BLOBS[1][0]).unlink()
    bad = subprocess.run([sys.executable, str(cmd), "--repo-root", str(home)],
                         cwd=ROOT, text=True, capture_output=True, check=False)
    assert bad.returncode == 2
    denied = json.loads(bad.stdout)
    assert denied["merge_authorized"] is False
    assert denied["real_money_trading_enabled"] is False

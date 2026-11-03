"""Stage66 exhaustive *frozen* PR file-list audit adversarial tests."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus_titan.operations.stage66_pr_inventory import (
    Stage66InventoryError, inspect_stage66_inventory,
)

ROOT = Path(__file__).resolve().parents[1]


def copied(tmp_path: Path) -> Path:
    dest = tmp_path / "docs"
    dest.mkdir(parents=True)
    for part in range(1, 7):
        src = ROOT / "docs" / f"STAGE66_PR_FILES_PART_{part:02d}_2026-11-03.json"
        shutil.copy2(src, dest / src.name)
    return tmp_path


def altered(tmp_path: Path, modifier, *, part: int = 1) -> Path:
    home = copied(tmp_path)
    file = home / "docs" / f"STAGE66_PR_FILES_PART_{part:02d}_2026-11-03.json"
    obj = json.loads(file.read_text(encoding="utf-8"))
    modifier(obj)
    file.write_text(json.dumps(obj), encoding="utf-8")
    return home


def test_actual_56_open_pr_filenames_and_two_roots_still_no_go():
    report = inspect_stage66_inventory(ROOT)
    assert report.reviewed_pr_count == 56
    assert report.fully_recorded_changed_file_lists == 56
    assert report.total_changed_file_entries == 429
    assert report.root_pr_numbers == (1, 3)
    assert report.graph_consistent_at_capture
    assert report.frozen_file_list_coverage_complete
    assert {(x.pr_a, x.pr_b): x.paths for x in report.overlap_candidates} == {
        (3, 6): (
            "src/nexus_titan/intelligence/__init__.py",
            "src/nexus_titan/intelligence/calibration.py",
            "tests/test_probability_calibration.py",
        ),
        (5, 6): (
            "docs/PROBABILITY_CALIBRATION.md",
            "src/nexus_titan/intelligence/calibration.py",
            "tests/test_probability_calibration.py",
        ),
    }
    for attribute in (
        "current_github_state_authenticated", "full_source_diff_review_verified",
        "three_way_merge_conflicts_ruled_out",
        "branch_protection_independently_verified", "merged_tree_ci_verified",
        "owner_merge_approval_verified", "safe_to_merge", "production_ready",
        "live_trading_enabled",
    ):
        assert getattr(report, attribute) is False
    assert report.merges_performed == 0
    assert report.broker_orders_transmitted == 0
    assert any("Frozen PR head" in b for b in report.audit_blockers)


def test_copy_of_snapshot_is_readonly_and_idempotent(tmp_path):
    home = copied(tmp_path)
    before = [(x.name, x.read_bytes()) for x in sorted((home / "docs").iterdir())]
    left = inspect_stage66_inventory(home)
    right = inspect_stage66_inventory(home)
    assert left == right
    assert before == [(x.name, x.read_bytes()) for x in sorted((home / "docs").iterdir())]


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema_version=True),
    lambda d: d.update(repository="attacker/repo"),
    lambda d: d.update(expected_open_count=55),
    lambda d: d.update(parts=7),
    lambda d: d.update(part=2),
    lambda d: d.update(captured_at_utc="2026-11-03T15:00:00+05:30"),
    lambda d: d["pull_requests"][0].update(changed_paths_complete=False),
    lambda d: d["pull_requests"][0].update(changed_paths=[]),
    lambda d: d["pull_requests"][0].update(draft=False),
    lambda d: d["pull_requests"][0].update(merged=True),
    lambda d: d["pull_requests"][0].update(base_sha="e" * 40),
    lambda d: d["pull_requests"][0].update(number=999),
    lambda d: d["pull_requests"][1]["changed_paths"].append(
        d["pull_requests"][1]["changed_paths"][0]),
])
def test_tampered_file_parts_fail_closed(tmp_path, change):
    home = altered(tmp_path, change)
    with pytest.raises(Stage66InventoryError):
        inspect_stage66_inventory(home)


def test_stale_parent_sha_is_not_mistaken_for_safe_merge(tmp_path):
    home = altered(
        tmp_path,
        lambda d: d["pull_requests"][3].update(base_sha="d" * 40),
    )
    with pytest.raises(Stage66InventoryError, match="graph"):
        inspect_stage66_inventory(home)


def test_missing_or_symlinked_part_and_duplicate_json_key_fail(tmp_path):
    home = copied(tmp_path)
    file = home / "docs" / "STAGE66_PR_FILES_PART_02_2026-11-03.json"
    file.unlink()
    with pytest.raises(Stage66InventoryError):
        inspect_stage66_inventory(home)
    file.symlink_to(ROOT / "docs" / file.name)
    with pytest.raises(Stage66InventoryError, match="symlink"):
        inspect_stage66_inventory(home)

    home2 = copied(tmp_path / "duplicate")
    f = home2 / "docs" / "STAGE66_PR_FILES_PART_01_2026-11-03.json"
    f.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(Stage66InventoryError, match="duplicate"):
        inspect_stage66_inventory(home2)


def test_cli_fails_closed_and_no_merge_on_real_snapshot(tmp_path):
    runner = ROOT / "scripts" / "run_stage66_pr_inventory.py"
    pass_result = subprocess.run(
        [sys.executable, str(runner)], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    assert pass_result.returncode == 0, pass_result.stderr
    payload = json.loads(pass_result.stdout)
    assert payload["reviewed_pr_count"] == 56
    assert payload["safe_to_merge"] is False
    assert payload["production_ready"] is False
    assert payload["broker_orders_transmitted"] == 0

    home = copied(tmp_path)
    (home / "docs" / "STAGE66_PR_FILES_PART_03_2026-11-03.json").unlink()
    failed = subprocess.run(
        [sys.executable, str(runner), "--repo-root", str(home)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert failed.returncode == 2
    packet = json.loads(failed.stdout)
    assert packet["safe_to_merge"] is False
    assert packet["production_ready"] is False

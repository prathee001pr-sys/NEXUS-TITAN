"""Stage68 selected cross-lineage offline integration candidate regressions."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus_titan.operations.stage67_calibration_reconcile import PR5_BLOBS
from nexus_titan.operations.stage68_combined_candidate import (
    _CRITICAL_PYTHON_PATHS, Stage68CandidateBlocked,
    inspect_stage68_combined_candidate,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_candidate(tmp_path: Path) -> Path:
    paths = [p for p, _ in PR5_BLOBS] + list(_CRITICAL_PYTHON_PATHS) + [
        ".github/workflows/ci.yml",
        "src/nexus_titan/intelligence/__init__.py",
        "src/nexus_titan/dashboard/static/stage63.html",
    ]
    paths += [
        f"docs/STAGE66_PR_FILES_PART_{index:02d}_2026-11-03.json"
        for index in range(1, 7)
    ]
    for relative in set(paths):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return tmp_path


def test_current_selected_candidate_has_only_offline_no_go():
    report = inspect_stage68_combined_candidate(ROOT)
    assert report.candidate_local_checks_passed
    assert report.captured_pr_count == 56
    assert report.captured_changed_file_entry_count == 429
    assert report.independent_root_pr_numbers_at_capture == (1, 3)
    assert report.source_identical_pr5_file_count == 4
    assert report.selected_python_modules_parsed == 7
    assert report.selected_ci_steps_present == 3
    assert len(report.external_release_blockers) >= 8
    assert report.release_verdict.startswith("NO_GO")
    for flag in (
        "current_github_state_authenticated",
        "independent_all_source_diff_review_verified",
        "owner_main_merge_approved", "main_branch_merged",
        "global_risk_veto_independently_verified",
        "atomic_capital_truth_independently_verified",
        "independently_authenticated_real_trading_results",
        "independent_security_recovery_verified",
        "human_release_approval_verified", "safe_to_merge",
        "strategy_promotion_authorized", "production_ready",
        "real_money_trading_enabled",
    ):
        assert getattr(report, flag) is False
    assert report.broker_orders_transmitted == 0


def test_identical_local_review_does_not_write_to_repo(tmp_path):
    home = _copy_candidate(tmp_path)
    before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    a = inspect_stage68_combined_candidate(home)
    b = inspect_stage68_combined_candidate(home)
    assert a == b
    assert before == {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}


@pytest.mark.parametrize("relative", [
    "src/nexus_titan/operations/offline_risk_veto.py",
    "src/nexus_titan/operations/synthetic_capital_authority.py",
    "src/nexus_titan/shadow/stage64_trial_governance.py",
])
def test_unparseable_critical_source_fail_closed(tmp_path, relative):
    home = _copy_candidate(tmp_path)
    (home / relative).write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(Stage68CandidateBlocked, match="unparseable"):
        inspect_stage68_combined_candidate(home)


@pytest.mark.parametrize("relative", [
    "src/nexus_titan/operations/stage65_release_acceptance.py",
    ".github/workflows/ci.yml",
    "src/nexus_titan/dashboard/static/stage63.html",
])
def test_missing_critical_source_fail_closed(tmp_path, relative):
    home = _copy_candidate(tmp_path)
    (home / relative).unlink()
    with pytest.raises(Stage68CandidateBlocked, match="missing"):
        inspect_stage68_combined_candidate(home)


def test_missing_ci_step_or_dashboard_offline_csp_marker_fails(tmp_path):
    home = _copy_candidate(tmp_path)
    file = home / ".github/workflows/ci.yml"
    file.write_text(file.read_text(encoding="utf-8").replace(
        "scripts/run_stage67_calibration_reconciliation.py",
        "scripts/unaudited.py"
    ), encoding="utf-8")
    with pytest.raises(Stage68CandidateBlocked, match="CI"):
        inspect_stage68_combined_candidate(home)

    home = _copy_candidate(tmp_path)
    file = home / "src/nexus_titan/dashboard/static/stage63.html"
    file.write_text(file.read_text(encoding="utf-8").replace(
        "connect-src 'none'", "connect-src *"
    ), encoding="utf-8")
    with pytest.raises(Stage68CandidateBlocked, match="dashboard"):
        inspect_stage68_combined_candidate(home)


def test_stage66_or_stage67_tamper_blocks_stage68(tmp_path):
    home = _copy_candidate(tmp_path)
    file = home / "docs" / "STAGE66_PR_FILES_PART_06_2026-11-03.json"
    file.unlink()
    with pytest.raises(ValueError):
        inspect_stage68_combined_candidate(home)
    home = _copy_candidate(tmp_path)
    with (home / PR5_BLOBS[0][0]).open("ab") as stream:
        stream.write(b"\n# unreviewed calibration change\n")
    with pytest.raises(ValueError):
        inspect_stage68_combined_candidate(home)


def test_stage68_cli_pass_is_never_merge_or_live_authority(tmp_path):
    runner = ROOT / "scripts" / "run_stage68_combined_candidate.py"
    ok = subprocess.run([sys.executable, str(runner)],
                        cwd=ROOT, capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stderr
    report = json.loads(ok.stdout)
    assert report["candidate_local_checks_passed"] is True
    assert report["safe_to_merge"] is False
    assert report["production_ready"] is False
    assert report["real_money_trading_enabled"] is False
    assert report["broker_orders_transmitted"] == 0
    home = _copy_candidate(tmp_path)
    (home / "docs" / "STAGE66_PR_FILES_PART_02_2026-11-03.json").unlink()
    bad = subprocess.run(
        [sys.executable, str(runner), "--repo-root", str(home)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert bad.returncode == 2
    denied = json.loads(bad.stdout)
    assert denied["safe_to_merge"] is False
    assert denied["production_ready"] is False

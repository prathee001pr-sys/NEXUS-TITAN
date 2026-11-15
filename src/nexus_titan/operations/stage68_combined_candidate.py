"""Stage68 — combined offline candidate gate for two-root reconciled development.

Validates selected current checkout sources plus Stage66/67 local evidence.
Never authenticates GitHub branch rules, broker/vendor data, independent security,
a real three-way merge, or signed owner release. No network, git writes or orders.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from nexus_titan.operations.stage66_pr_inventory import inspect_stage66_inventory
from nexus_titan.operations.stage67_calibration_reconcile import (
    inspect_stage67_calibration_reconciliation,
)

_CRITICAL_PYTHON_PATHS = (
    "src/nexus_titan/operations/stage65_release_acceptance.py",
    "src/nexus_titan/operations/stage66_pr_inventory.py",
    "src/nexus_titan/operations/stage67_calibration_reconcile.py",
    "src/nexus_titan/operations/offline_risk_veto.py",
    "src/nexus_titan/operations/synthetic_capital_authority.py",
    "src/nexus_titan/shadow/stage64_trial_governance.py",
    "src/nexus_titan/crypto/crypto_engine.py",
)
_REQUIRED_CI_SCRIPTS = (
    "scripts/run_stage65_final_acceptance.py",
    "scripts/run_stage66_pr_inventory.py",
    "scripts/run_stage67_calibration_reconciliation.py",
)
_EXTERNAL_BLOCKERS = (
    "Current branch rules and independent owner merge approval unavailable",
    "All current PR heads and full diff semantics must be re-verified",
    "Actual integrated main-branch merge/recovery CI has not occurred",
    "Independent globally unbypassable Risk & Veto and atomic capital proof absent",
    "Real identity/key custody and production security/recovery audit absent",
    "Licensed exchange/broker F&O and crypto market/execution sources absent",
    "Prospective authenticated real-feed shadow P&L and strategy evidence absent",
    "Exact user-approved TITAN face asset integration not verified",
)


class Stage68CandidateBlocked(ValueError):
    """Selected source or proof input changed; no integration acceptance."""


@dataclass(frozen=True, slots=True)
class Stage68CandidateReview:
    scope: str
    captured_pr_count: int
    captured_changed_file_entry_count: int
    frozen_pr_file_list_coverage: bool
    independent_root_pr_numbers_at_capture: tuple[int, ...]
    source_identical_pr5_file_count: int
    selected_python_modules_parsed: int
    selected_ci_steps_present: int
    candidate_local_checks_passed: bool
    external_release_blockers: tuple[str, ...]
    # Full project/production claims are never promoted from selected checks.
    current_github_state_authenticated: bool = False
    independent_all_source_diff_review_verified: bool = False
    owner_main_merge_approved: bool = False
    main_branch_merged: bool = False
    global_risk_veto_independently_verified: bool = False
    atomic_capital_truth_independently_verified: bool = False
    independently_authenticated_real_trading_results: bool = False
    independent_security_recovery_verified: bool = False
    human_release_approval_verified: bool = False
    safe_to_merge: bool = False
    strategy_promotion_authorized: bool = False
    production_ready: bool = False
    real_money_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    release_verdict: str = "NO_GO_OWNER_AND_REAL_EVIDENCE_REQUIRED"


def _read_repo_file(root: Path, relative: str, *, maximum: int = 512 * 1024) -> str:
    target = root.joinpath(*relative.split("/"))
    if target.is_symlink() or not target.is_file():
        raise Stage68CandidateBlocked("missing or symlinked selected source: " + relative)
    if not 0 < target.stat().st_size <= maximum:
        raise Stage68CandidateBlocked("invalid selected source size: " + relative)
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Stage68CandidateBlocked("unreadable source: " + relative) from exc


def inspect_stage68_combined_candidate(repo_root: Path) -> Stage68CandidateReview:
    root = Path(repo_root)
    inventory = inspect_stage66_inventory(root)
    calibration = inspect_stage67_calibration_reconciliation(root)
    if not (
        inventory.graph_consistent_at_capture
        and inventory.frozen_file_list_coverage_complete
        and calibration.frozen_source_lineage_check_passed
        and inventory.reviewed_pr_count == 56
        and inventory.total_changed_file_entries == 429
        and (
            calibration.byte_identical_pr5_path_count == 4
            or (calibration.byte_identical_pr5_path_count == 3
                and calibration.reviewed_workflow_security_update_verified)
        )
    ):
        raise Stage68CandidateBlocked("upstream offline integration evidence mismatch")

    for relative in _CRITICAL_PYTHON_PATHS:
        source = _read_repo_file(root, relative)
        try:
            ast.parse(source, filename=relative)
        except SyntaxError as exc:
            raise Stage68CandidateBlocked("unparseable selected source: " + relative) from exc

    workflow = _read_repo_file(root, ".github/workflows/ci.yml")
    if not all(script in workflow for script in _REQUIRED_CI_SCRIPTS):
        raise Stage68CandidateBlocked("missing selected CI smoke action")
    if not all(version in workflow for version in ("3.11", "3.12", "3.13")):
        raise Stage68CandidateBlocked("CI Python matrix missing")
    dashboard = _read_repo_file(
        root, "src/nexus_titan/dashboard/static/stage63.html")
    if ("connect-src 'none'" not in dashboard
            or "APPROVED TITAN FACE" not in dashboard
            or "RELEASE NO-GO" not in dashboard):
        raise Stage68CandidateBlocked("read-only offline dashboard safety marker absent")

    return Stage68CandidateReview(
        scope="STAGE68_SELECTED_OFFLINE_INTEGRATION_CANDIDATE_NO_GO",
        captured_pr_count=inventory.reviewed_pr_count,
        captured_changed_file_entry_count=inventory.total_changed_file_entries,
        frozen_pr_file_list_coverage=True,
        independent_root_pr_numbers_at_capture=inventory.root_pr_numbers,
        source_identical_pr5_file_count=calibration.byte_identical_pr5_path_count,
        selected_python_modules_parsed=len(_CRITICAL_PYTHON_PATHS),
        selected_ci_steps_present=len(_REQUIRED_CI_SCRIPTS),
        candidate_local_checks_passed=True,
        external_release_blockers=_EXTERNAL_BLOCKERS,
    )

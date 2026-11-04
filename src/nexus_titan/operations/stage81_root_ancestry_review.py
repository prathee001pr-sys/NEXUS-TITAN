"""Stage81: inspect both GitHub-root ancestries in one OFFLINE candidate.

The imported evidence is a frozen operator-fetched GitHub compare snapshot.
This cannot authenticate Git history today, prove a conflict-free merge, or
authorize main modification/trading.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

_SHA = re.compile(r"[a-f0-9]{40}\Z")
_PATHS = (
    "src/nexus_titan/intelligence/calibration.py",
    "src/nexus_titan/evolve/stage73_fo_experience.py",
    "tests/test_probability_calibration.py",
    "tests/test_full_chain_fo_data_to_sandbox_e2e.py",
)
_ROOTS = {
    1: "integration/phase6-zip-baseline",
    3: "feature/oos-probability-calibration",
}


class Stage81AncestryBlocked(ValueError):
    """Malformed/inconsistent root ancestry or broken local code hand-off."""


@dataclass(frozen=True, slots=True)
class Stage81TwoRootCandidateReview:
    root_prs_present_in_development_history: tuple[int, ...]
    candidate_parent_snapshot_sha: str
    source_contract_sha256: str
    calibration_runtime_import_contract_found: bool
    independent_root_ancestry_locally_consistent: bool
    main_baseline_unprotected_in_snapshot: bool
    source_file_count_inspected: int
    blockers: tuple[str, ...]
    independent_github_ancestry_authenticated: bool = False
    actual_three_way_merge_review_completed: bool = False
    main_branch_protection_verified: bool = False
    complete_PR_file_diff_conflict_review: bool = False
    global_risk_veto_verified: bool = False
    unified_capital_authority_verified: bool = False
    owner_approved_merge: bool = False
    merge_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE81_BOTH_ROOTS_DEV_ONLY_OWNER_REVIEW_NO_GO"


def _read(root: Path, rel: str) -> bytes:
    current = root
    for name in rel.split("/"):
        current = current / name
        if current.is_symlink():
            raise Stage81AncestryBlocked("Symlink source not trusted")
    if not current.is_file() or not 0 < current.stat().st_size <= 256_000:
        raise Stage81AncestryBlocked("Missing or oversized source: " + rel)
    return current.read_bytes()


def inspect_stage81_candidate(root: Path, evidence: dict) -> Stage81TwoRootCandidateReview:
    if not isinstance(root, Path) or not root.is_dir() or root.is_symlink():
        raise Stage81AncestryBlocked("Explicit regular source directory required")
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 1:
        raise Stage81AncestryBlocked("Versioned frozen GitHub ancestry evidence required")
    if evidence.get("repository") != "prathee001pr-sys/NEXUS-TITAN":
        raise Stage81AncestryBlocked("Unexpected repository")
    sha, main = evidence.get("candidate_sha"), evidence.get("main_sha")
    if (not isinstance(sha, str) or not _SHA.fullmatch(sha)
            or not isinstance(main, str) or not _SHA.fullmatch(main)
            or evidence.get("main_protected") is not False
            or sha == main):
        raise Stage81AncestryBlocked("Candidate/main SHA or reported policy unsupported")
    roots = evidence.get("root_ancestry")
    if not isinstance(roots, list) or len(roots) != len(_ROOTS):
        raise Stage81AncestryBlocked("Both independent root comparisons required")
    seen = set()
    for item in roots:
        if not isinstance(item, dict) or type(item.get("root_pr")) is not int:
            raise Stage81AncestryBlocked("Root comparison record invalid")
        n = item["root_pr"]
        if n in seen or n not in _ROOTS or item.get("base_ref") != _ROOTS[n]:
            raise Stage81AncestryBlocked("Root branch identity mismatch")
        seen.add(n)
        base = item.get("base_sha")
        if (not isinstance(base, str) or not _SHA.fullmatch(base)
                or item.get("merge_base_sha") != base
                or item.get("head_sha") != sha
                or item.get("status") != "ahead"
                or type(item.get("behind_by")) is not int or item["behind_by"] != 0
                or type(item.get("ahead_by")) is not int or item["ahead_by"] <= 0):
            raise Stage81AncestryBlocked("Root must be evidenced as ancestor, not diverged")
    if seen != set(_ROOTS):
        raise Stage81AncestryBlocked("Both root PRs required")
    bodies = {p: _read(root, p) for p in _PATHS}
    try:
        cal = ast.parse(bodies[_PATHS[0]].decode("utf-8"))
        evo = ast.parse(bodies[_PATHS[1]].decode("utf-8"))
        tests = ast.parse(bodies[_PATHS[2]].decode("utf-8"))
        e2e = ast.parse(bodies[_PATHS[3]].decode("utf-8"))
    except (SyntaxError, UnicodeError) as exc:
        raise Stage81AncestryBlocked("Candidate Python source invalid") from exc
    classes = {n.name for n in cal.body if isinstance(n, ast.ClassDef)}
    imports = [
        n for n in evo.body if isinstance(n, ast.ImportFrom)
        and n.module == "nexus_titan.intelligence.calibration"
    ]
    cal_tests = {n.name for n in tests.body if isinstance(n, ast.FunctionDef)}
    e2e_tests = {n.name for n in e2e.body if isinstance(n, ast.FunctionDef)}
    if (not {"ProbabilityCalibrator", "CalibrationObservation"}.issubset(classes)
            or not imports
            or not {"ProbabilityCalibrator", "CalibrationObservation"}.issubset(
                {a.name for node in imports for a in node.names})
            or "test_empty_report_is_explicitly_insufficient" not in cal_tests
            or "test_real_python_calls_connect_synthetic_csv_all_the_way_to_sqlite" not in e2e_tests):
        raise Stage81AncestryBlocked("Calibration-to-FO EVOLVE integration contract missing")
    digest = hashlib.sha256(json.dumps({
        k: hashlib.sha256(v).hexdigest() for k, v in sorted(bodies.items())
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return Stage81TwoRootCandidateReview(
        root_prs_present_in_development_history=(1, 3),
        candidate_parent_snapshot_sha=sha,
        source_contract_sha256=digest,
        calibration_runtime_import_contract_found=True,
        independent_root_ancestry_locally_consistent=True,
        main_baseline_unprotected_in_snapshot=True,
        source_file_count_inspected=len(_PATHS),
        blockers=(
            "FROZEN_COMPARE_RECORDS_NOT_SIGNED_OR_LIVE_AUTHENTICATED",
            "TWO_ROOT_BRANCHES_HAVE_COMMON_DEV_ANCESTRY_NOT_OWNER_REVIEWED_MERGE",
            "MAIN_STILL_UNPROTECTED_AND_UNMERGED",
            "INCOMPLETE_PR_FILE_DIFF_AND_CONFLICT_REVIEW",
            "REAL_GLOBAL_RISK_AND_ATOMIC_FO_CAPITAL_NOT_ENFORCED",
            "NO_REAL_EXCHANGE_DATA_OR_PROSPECTIVE_SHADOW_TRIAL",
        ),
    )

"""Stage67 manual PR#3/#5 calibration lineage reconcile — offline source equality.

Four PR#5 files are retained byte-for-byte, while the primary Stage66 branch's
expanded intelligence exports are preserved. This is a *candidate* resolution,
not a GitHub current-state attestation, automatic merge authority or real trading.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path

# Independently inspected Git blob IDs from PR#5 and Stage66 source.
PR5_BLOBS = (
    ("src/nexus_titan/intelligence/calibration.py",
     "2f0541b85c8ee88139400b7f049b828a72ae49c7"),
    ("tests/test_probability_calibration.py",
     "1316c75483c9daba300f581b9998fb2102d71484"),
    ("docs/PROBABILITY_CALIBRATION.md",
     "e60da3a9f545b37938489936ad04512da2069e68"),
    (".github/workflows/calibration-hardening.yml",
     "46d1d7c95c89a1bc409fd2c00ab51bbea27ff956"),
)
PRIMARY_INIT_BLOB = "9066f3f9ceecd3e6eeb0b227bf5d97d0b3c59336"
PR3_HEAD = "fa8c34eba862108d6cd333c59964c4e3cc6e6405"
PR5_HEAD = "d97b9abef59c479cd7a7c8dfb0ffb0fd44f95148"
PRIMARY_STAGE66_BASE = "d35dad8edaa07462bf0f48a3b28245022bda66dd"


class Stage67LineageError(ValueError):
    """Immutable calibration source candidates have drifted or gone missing."""


@dataclass(frozen=True, slots=True)
class Stage67CalibrationLineageReport:
    scope: str
    independent_root_pr: int
    independent_hardening_pr: int
    independently_staged_pr5_head: str
    primary_stage66_head_at_branch_creation: str
    byte_identical_pr5_path_count: int
    inspected_git_blob_pairs: tuple[tuple[str, str], ...]
    expanded_primary_intelligence_exports_retained: bool
    frozen_source_lineage_check_passed: bool
    # Ancestry and release claims must be externally rechecked on exact final head.
    current_github_ancestry_verified: bool = False
    complete_integrated_diff_review_verified: bool = False
    three_way_conflict_freedom_independently_verified: bool = False
    prospective_combined_tree_ci_verified: bool = False
    main_branch_merged: bool = False
    merge_authorized: bool = False
    production_ready: bool = False
    strategy_promotion_authorized: bool = False
    real_money_trading_enabled: bool = False
    broker_orders_transmitted: int = 0


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}".encode("ascii") + b"\0"
    return hashlib.sha1(header + raw).hexdigest()


def _checked_bytes(root: Path, filename: str) -> bytes:
    path = root.joinpath(*filename.split("/"))
    if path.is_symlink() or not path.is_file():
        raise Stage67LineageError(f"missing or symlinked {filename}")
    if not 0 < path.stat().st_size <= 128 * 1024:
        raise Stage67LineageError(f"invalid file size {filename}")
    return path.read_bytes()


def inspect_stage67_calibration_reconciliation(repo_root: Path) -> Stage67CalibrationLineageReport:
    root = Path(repo_root)
    for relative, expected in PR5_BLOBS:
        if _git_blob_sha(_checked_bytes(root, relative)) != expected:
            raise Stage67LineageError(f"PR5 source blob changed: {relative}")
    init_source = _checked_bytes(root, "src/nexus_titan/intelligence/__init__.py")
    if _git_blob_sha(init_source) != PRIMARY_INIT_BLOB:
        raise Stage67LineageError("primary intelligence exports have drifted")
    try:
        parsed = ast.parse(init_source.decode("utf-8"))
    except (UnicodeError, SyntaxError) as exc:
        raise Stage67LineageError("invalid intelligence package source") from exc
    exported: set[str] = set()
    for node in parsed.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            try:
                values = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError) as exc:
                raise Stage67LineageError("unverifiable intelligence exports") from exc
            if not isinstance(values, (list, tuple)) or not all(
                isinstance(item, str) for item in values
            ):
                raise Stage67LineageError("invalid intelligence exports")
            exported = set(values)
    if not {"CalibrationObservation", "CalibrationReport",
            "ProbabilityCalibrator", "ReliabilityBin",
            "MarketState", "ConsensusEngine",
            "TradingIntelligencePipeline"}.issubset(exported):
        raise Stage67LineageError("primary calibration/pipeline export regression")
    return Stage67CalibrationLineageReport(
        scope="STAGE67_MANUAL_CALIBRATION_LINEAGE_CANDIDATE_OFFLINE_NO_GO",
        independent_root_pr=3,
        independent_hardening_pr=5,
        independently_staged_pr5_head=PR5_HEAD,
        primary_stage66_head_at_branch_creation=PRIMARY_STAGE66_BASE,
        byte_identical_pr5_path_count=len(PR5_BLOBS),
        inspected_git_blob_pairs=PR5_BLOBS,
        expanded_primary_intelligence_exports_retained=True,
        frozen_source_lineage_check_passed=True,
    )

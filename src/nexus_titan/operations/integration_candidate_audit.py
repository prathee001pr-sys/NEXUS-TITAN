"""Stage62: bounded read-only architecture and PR-stack compatibility audit.

Review source AST import contracts, minimal CI safeguards, and frozen PR
metadata alongside existing Stage52/56 audits. Local source compatibility
is NOT runtime behavioral proof. The snapshot is not authenticated current
GitHub state; changed PR file lists are UNKNOWN, so do not claim a clean
merge, safe broker boundary, or production readiness.

No network, git, code execution, SQLite opens/writes, secret loading,
orders, broker credentials, market-feed calls or file modifications.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus_titan.operations.pr_stack_audit import inspect_pr_dependency_snapshot
from nexus_titan.operations.release_security_audit import inspect_stage52_security_sources
from nexus_titan.operations.risk_boundary_inventory import inspect_stage56_bypass_paths


# Explicit cross-stage contracts. Check that the IMPORTING module names a
# concrete exported class/function in its imported module. This does NOT
# guarantee the import's semantics or test unrelated dynamic Python paths.
_IMPORT_EDGES = (
    ("operations/signed_paper_approval", "core/security_gates", "CryptographicApprovalVerifier"),
    ("operations/durable_paper_fence", "operations/signed_paper_approval", "Stage48SignedPaperSession"),
    ("operations/multi_ledger_recovery_audit", "operations/durable_paper_fence", "Stage49DurablePaperFence"),
    ("operations/multi_ledger_recovery_audit", "operations/synthetic_capital_authority", "Stage53SyntheticCapitalAuthority"),
    ("operations/local_approval_risk_review", "operations/signed_paper_approval", "Stage48ApprovalChallenge"),
    ("operations/local_approval_risk_review", "operations/brokerless_risk_veto", "inspect_stage56_synthetic_risk"),
    ("simulation/stage58_execution_stress", "virtual/microstructure", "MicrostructureSimulator"),
    ("simulation/stage58_execution_stress", "cost/charges", "calculate_indian_trade_costs"),
    ("data/stage59_futures_history", "data/quality", "inspect_candle_batch"),
    ("research/stage60_purged_oos", "data/stage59_futures_history", "Stage59FuturesHistory"),
    ("research/stage60_purged_oos", "data/historical_fo_catalog", "HistoricalCatalogResult"),
    ("research/stage61_evidence_scorecard", "data/stage59_futures_history", "Stage59FuturesHistory"),
    ("research/stage61_evidence_scorecard", "research/stage60_purged_oos", "Stage60OfflineResearchReport"),
    ("research/stage61_evidence_scorecard", "simulation/stage58_execution_stress", "Stage58ExecutionScenario"),
    ("operations/stage65_release_acceptance", "operations/integration_candidate_audit", "Stage62IntegrationReview"),
    ("operations/stage65_release_acceptance", "research/stage61_evidence_scorecard", "Stage61FOMarketReadinessScorecard"),
    ("operations/stage65_release_acceptance", "shadow/stage64_trial_governance", "Stage64ShadowTrialGovernanceReport"),
)

_WORKFLOW_REQUIREMENTS = (
    ("CI-PR-TRIGGER", r"(?m)^  pull_request:\s*$"),
    ("CI-PUSH-TRIGGER", r"(?m)^  push:\s*$"),
    ("CI-READONLY-TOKEN", r"(?m)^permissions:\s*\n  contents: read\s*$"),
    ("CI-PYTHON-3-VERSIONS", r"python-version: \['3\.11', '3\.12', '3\.13'\]"),
    ("CI-FULL-VALIDATION", r"run:\s*python scripts/run_project_validation\.py"),
    ("CI-SYNTHETIC-E2E", r"run:\s*python scripts/run_stage25_full_research_audit\.py"),
    ("CI-STAGE62-NO-MERGE", r"run:\s*python scripts/run_stage62_integration_audit\.py"),
)


@dataclass(frozen=True, slots=True)
class Stage62Check:
    check_id: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Stage62IntegrationReview:
    schema_version: int
    scope: str
    source_subset_sha256: str | None
    frozen_pr_snapshot_sha256: str
    frozen_pr_count: int
    frozen_main_sha: str
    frozen_main_protected_reported: bool
    frozen_root_prs: tuple[int, ...]
    frozen_topology_consistent: bool
    frozen_changed_paths_complete: bool
    local_source_structure_passed: bool
    local_cross_module_import_contracts_passed: bool
    local_ci_workflow_contracts_passed: bool
    local_reviewed_legacy_entrypoints: tuple[str, ...]
    checks: tuple[Stage62Check, ...]
    blockers: tuple[str, ...]
    local_static_review_passed: bool
    # These are NOT inferred from filesystem, source AST, or frozen PR data.
    github_current_state_independently_verified: bool = False
    main_branch_protection_independently_verified: bool = False
    independent_root_stacks_reconciled: bool = False
    complete_file_diff_conflicts_ruled_out: bool = False
    prospective_merged_tree_ci_verified: bool = False
    independent_risk_and_execution_fenced: bool = False
    one_authoritative_cross_ledger_capital_verified: bool = False
    authenticated_real_fo_history_and_licence_verified: bool = False
    independently_verified_human_identity: bool = False
    owner_merge_approval_verified: bool = False
    merge_authorized: bool = False
    real_money_trading_enabled: bool = False
    strategy_promotion_authorized: bool = False
    production_ready: bool = False
    merges_performed: int = 0
    broker_orders_transmitted: int = 0


def _read_source(root: Path, relative: str) -> bytes:
    if (relative.startswith("/") or "\\" in relative
            or any(x in ("", ".", "..") for x in relative.split("/"))):
        raise ValueError("Unsafe integration reviewed path")
    path = root
    for component in relative.split("/"):
        path = path / component
        if path.is_symlink():
            raise ValueError("Symlink in integration reviewed source path")
    if not path.is_file() or path.stat().st_size > 512_000:
        raise ValueError("Reviewed source missing, nonfile or oversized")
    return path.read_bytes()


def _declares(tree: ast.Module, symbol: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == symbol for node in tree.body
    )


def inspect_stage62_candidate(
    repo_root: Path,
    *,
    pr_snapshot: dict[str, Any],
) -> Stage62IntegrationReview:
    """Report reviewed subset and frozen PR dependency evidence, never merge.

    Unlike a build/merge simulation, this AST check deliberately cannot
    rule out runtime imports, function signature drift, malicious dynamic
    imports, transitive conflicts, binary artifacts or privilege escapes.
    """
    if not isinstance(repo_root, Path):
        raise TypeError("Explicit repository Path required")
    if not repo_root.is_dir() or repo_root.is_symlink():
        raise ValueError("Existing non-symlink repository root required")
    # The Stage46 strict verifier validates this *operator supplied*
    # single-moment snapshot; it does not contact GitHub.
    graph = inspect_pr_dependency_snapshot(pr_snapshot)
    snapshot_raw = json.dumps(
        pr_snapshot, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    if len(snapshot_raw) > 512_000:
        raise ValueError("PR snapshot exceeds size budget")
    snapshot_sha = hashlib.sha256(snapshot_raw).hexdigest()
    source = inspect_stage52_security_sources(repo_root)
    bypass = inspect_stage56_bypass_paths(repo_root)
    checks: list[Stage62Check] = []
    source_raw: dict[str, bytes] = {}
    modules: dict[str, ast.Module | None] = {}
    missing_paths: set[str] = set()
    paths = {
        f"src/nexus_titan/{s}.py" for s, _, _ in _IMPORT_EDGES
    } | {
        f"src/nexus_titan/{t}.py" for _, t, _ in _IMPORT_EDGES
    }
    paths.add(".github/workflows/ci.yml")
    for path in sorted(paths):
        try:
            body = _read_source(repo_root, path)
            source_raw[path] = body
            if path.endswith(".py"):
                modules[path] = ast.parse(body.decode("utf-8"), filename=path)
        except (ValueError, OSError, UnicodeError, SyntaxError):
            missing_paths.add(path)
            modules[path] = None
    for source_mod, target_mod, symbol in _IMPORT_EDGES:
        srcpath = f"src/nexus_titan/{source_mod}.py"
        destpath = f"src/nexus_titan/{target_mod}.py"
        imported_from = "nexus_titan." + target_mod.replace("/", ".")
        importer = modules.get(srcpath)
        target = modules.get(destpath)
        valid = (
            isinstance(importer, ast.Module)
            and isinstance(target, ast.Module)
            and any(
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module == imported_from
                and any(alias.name == symbol for alias in node.names)
                for node in importer.body
            )
            and _declares(target, symbol)
        )
        checks.append(Stage62Check(
            "S62-IMPORT-" + source_mod.replace("/", "-")
            + "-" + symbol,
            bool(valid),
            "Local AST import and target symbol found (not runtime compatibility)"
            if valid else "Required cross-module import/symbol missing or code uninspectable",
        ))
    workflow_bytes = source_raw.get(".github/workflows/ci.yml")
    workflow = workflow_bytes.decode("utf-8", errors="replace") if workflow_bytes is not None else ""
    for cid, pattern in _WORKFLOW_REQUIREMENTS:
        matches = re.search(pattern, workflow) is not None
        checks.append(Stage62Check(
            "S62-" + cid, matches,
            "Source-level workflow marker present; CI success still needs external evidence"
            if matches else "Required CI workflow source marker missing",
        ))

    all_imports = all(c.passed for c in checks if c.check_id.startswith("S62-IMPORT-"))
    all_workflows = all(c.passed for c in checks if c.check_id.startswith("S62-CI-"))
    source_ok = source.local_structural_controls_passed
    bypass_ok = bypass.local_static_scan_complete
    checks.extend((
        Stage62Check("S62-STAGE52-SOURCE-SUBSET", source_ok,
                     "Read-only Stage52 subset review; production release denied"),
        Stage62Check("S62-STAGE56-DIRECT-ENTRYPOINTS-SEEN", bypass_ok,
                     "AST inventory of KNOWN bypassable Python order/fill APIs; NOT globally fenced"),
    ))
    digest = None
    if len(source_raw) == len(paths) and not missing_paths and all_imports and all_workflows:
        h = hashlib.sha256()
        for name in sorted(source_raw):
            h.update(name.encode("utf-8"))
            h.update(hashlib.sha256(source_raw[name]).digest())
        digest = h.hexdigest()

    blockers = list(source.release_blockers) + list(graph.blockers)
    blockers.extend((
        "S62: The reviewed GitHub pull-request snapshot is frozen and unauthenticated as current state",
        "S62: No real combined merged-tree CI, three-way merge simulation or owner-approved integration",
        "S62: Source import/CI marker AST checks cannot prove behavioral compatibility or global security",
        "S62: Known direct order and fill entrypoints are still exposed outside optional facades",
    ))
    if not source_ok or not bypass_ok or not all_imports or not all_workflows:
        blockers.append("S62: Local review is structurally incomplete; fail closed")
    if graph.root_pr_numbers and len(graph.root_pr_numbers) > 1:
        blockers.append("S62: Independent main-rooted PR branches require manual semantic integration")
    if not graph.complete_changed_file_coverage:
        blockers.append("S62: Missing per-PR changed-file coverage; file conflict status UNKNOWN")
    if not graph.main_protected_reported:
        blockers.append("S62: Frozen GitHub main branch was reported UNPROTECTED")

    return Stage62IntegrationReview(
        schema_version=1,
        scope="NO_MERGE_FROZEN_PR_AND_SELECTED_SOURCE_AST_CI_REVIEW_ONLY",
        source_subset_sha256=digest,
        frozen_pr_snapshot_sha256=snapshot_sha,
        frozen_pr_count=graph.pr_count,
        frozen_main_sha=graph.main_sha,
        frozen_main_protected_reported=graph.main_protected_reported,
        frozen_root_prs=graph.root_pr_numbers,
        frozen_topology_consistent=graph.branch_graph_consistent,
        frozen_changed_paths_complete=graph.complete_changed_file_coverage,
        local_source_structure_passed=source_ok,
        local_cross_module_import_contracts_passed=all_imports,
        local_ci_workflow_contracts_passed=all_workflows,
        local_reviewed_legacy_entrypoints=bypass.known_callable_surfaces,
        checks=tuple(checks),
        blockers=tuple(dict.fromkeys(blockers)),
        local_static_review_passed=(
            source_ok and bypass_ok and all_imports and all_workflows
            and bool(digest)
        ),
    )

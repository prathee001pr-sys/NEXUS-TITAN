"""Stage65 final OFFLINE release acceptance review — no broker/merge authority.

This module is a bounded read-only *developer acceptance checklist* over
Stage61, 62, 64 **synthetic/operator-supplied** evidence and a frozen
operator-exported GitHub PR snapshot. It never authenticates GitHub current
state, vendor licence, broker fill, identity, branch protection, or live
trading safety. It CANNOT approve a merge, a strategy, or any real trade.

No network, git commands, subprocess, DB creation, orders, provider calls
or filesystem writes. The checked-in PR snapshot becomes stale; its
overlap candidates are file-name collisions, not proved git conflicts.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from nexus_titan.operations.integration_candidate_audit import (
    Stage62IntegrationReview, inspect_stage62_candidate,
)
from nexus_titan.operations.pr_stack_audit import (
    OverlapCandidate, inspect_pr_dependency_snapshot,
)
from nexus_titan.research.stage61_evidence_scorecard import Stage61FOMarketReadinessScorecard
from nexus_titan.shadow.stage64_trial_governance import (
    Stage64ShadowTrialGovernanceReport, _MANDATORY_EXTERNAL_BLOCKERS,
)

_SHA = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_RELEASE_ACTIONS: tuple[tuple[str, str], ...] = (
    ("P0-ROOT-STACK", "Owner selects and reconciles both independently main-rooted PR lineages, including overlapping calibration sources; review actual three-way diffs"),
    ("P0-MERGED-TREE-CI", "Produce a reviewed prospective candidate merge commit and run complete Python and end-to-end security CI against THAT combined tree"),
    ("P0-BRANCH-PROTECTION", "Owner enables/reviews GitHub branch protection, rulesets, required checks, reviewers and deployment control"),
    ("P0-GLOBAL-RISK", "Remove or isolate bypassable direct order/fill APIs; enforce independent Risk & Veto and emergency stop at every real execution route"),
    ("P0-ATOMIC-CAPITAL", "Use one independently verified atomic capital/positions/reservation settlement with crash recovery, locking, reconciliation and idempotency"),
    ("P0-HUMAN-IDENTITY", "Authenticate the real owner/operator independently, protect signing keys/broker credentials and verify permission again at fill time"),
    ("P0-REAL-INDIA-FO-DATA", "Obtain legal licensed point-in-time NIFTY/BANKNIFTY F&O instrument, expiry, holiday, option-chain, trade/quote and depth records"),
    ("P0-REAL-EXECUTION", "Verify real trade/fill timestamps and depth, brokerage, STT, taxes, spreads, slippage, margin, exercise, expiry and roll economics"),
    ("P0-SUPERVISED-SHADOW", "Run signed prospective multi-session real-feed shadow trial with independently reconciled net performance and risk violations"),
    ("P0-CRYPTO-INDEPENDENT", "Review crypto virtual data, 24x7 runtime, separate funding, fees, liquidity, exchange access and independent risk boundaries"),
    ("P0-SECURITY-RECOVERY", "Independent credential isolation, adversarial release review, off-host backups, signed artifacts, restart and disaster recovery"),
    ("P1-LOCKED-IDENTITY", "Connect the exact owner-approved black/silver TITAN digital face asset; obtain visual and accessibility acceptance"),
    ("P0-OWNER-RELEASE", "Require explicit human signed decision after all independent acceptance gates; NO automatic live activation"),
)


class Stage65AcceptanceBlocked(ValueError):
    """Unsafe/mismatched source packet cannot become a release candidate."""


@dataclass(frozen=True, slots=True)
class Stage65AcceptanceCheck:
    check_id: str
    status: Literal["LOCAL_RESEARCH_PASS", "LOCAL_RESEARCH_FAIL", "REVIEW_REQUIRED", "EXTERNAL_EVIDENCE_MISSING"]
    detail: str


@dataclass(frozen=True, slots=True)
class Stage65FinalAcceptanceReport:
    schema_version: int
    scope: str
    reviewed_open_pr_count: int
    reported_main_sha: str
    reported_main_protected: bool
    main_root_pr_numbers: tuple[int, ...]
    checked_pr_file_list_count: int
    uninspected_pr_file_list_count: int
    independent_file_overlap_candidates: tuple[OverlapCandidate, ...]
    all_pr_changed_files_observed: bool
    selected_source_and_ci_structural_review_passed: bool
    stage61_source_claims_locally_consistent: bool
    stage64_local_trial_kpis_met: bool
    stage64_trial_underlying: str
    stage64_claimed_closed_trades: int
    checks: tuple[Stage65AcceptanceCheck, ...]
    required_owner_actions: tuple[tuple[str, str], ...]
    critical_release_blocker_count: int
    acceptance_packet_sha256: str
    developer_offline_checklist_completed: bool
    # Passing developer checklist is emphatically NOT any of these.
    github_current_pr_state_authenticated: bool = False
    branch_protection_independently_verified: bool = False
    two_root_branches_reconciled: bool = False
    PR_file_conflicts_ruled_out: bool = False
    prospective_merged_commit_ci_verified: bool = False
    independent_security_assessment_verified: bool = False
    globally_unbypassable_risk_veto_verified: bool = False
    single_atomic_capital_ledger_verified: bool = False
    independently_authenticated_human_verified: bool = False
    licensed_real_indian_fo_data_verified: bool = False
    executable_depth_and_costs_verified: bool = False
    real_shadow_trading_performance_verified: bool = False
    crypto_real_market_validation_verified: bool = False
    exact_approved_titan_face_integrated: bool = False
    owner_release_approval_verified: bool = False
    safe_to_merge: bool = False
    strategy_promotion_authorized: bool = False
    real_money_trading_enabled: bool = False
    production_ready: bool = False
    merges_performed: int = 0
    broker_orders_transmitted: int = 0
    release_verdict: str = "NO_GO_OWNER_AND_INDEPENDENT_EVIDENCE_REQUIRED"


_FALSE61 = (
    "source_vendor_authenticated", "source_licence_authenticated",
    "independently_verified_option_chain",
    "execution_scenario_bound_to_holdout", "real_orderbook_depth_authenticated",
    "actual_execution_or_fees_reconciled",
    "genuine_futures_options_backtest_verified",
    "strategy_promotion_authorized", "global_risk_veto_unbypassable",
    "independently_verified_human_identity",
    "unified_capital_settlement_verified", "live_trading_enabled",
    "production_ready",
)
_FALSE64 = (
    "data_source_independently_authenticated",
    "real_fill_or_fee_calibration_verified", "genuine_net_pnl_verified",
    "prospectively_signed_trial_plan_verified",
    "audited_full_portfolio_pnl_verified",
    "independently_verified_human_approval",
    "one_authoritative_capital_authority_verified", "global_risk_veto_enforced",
    "merge_authorized", "strategy_promotion_authorized",
    "live_trading_enabled", "production_ready",
)


def _require_denied(obj: object, attributes: tuple[str, ...], context: str) -> None:
    if any(getattr(obj, name, None) is not False for name in attributes):
        raise Stage65AcceptanceBlocked(context + " claims unauthorized external approval")
    if getattr(obj, "broker_orders_transmitted", None) != 0 or (
        type(getattr(obj, "broker_orders_transmitted", None)) is not int
    ):
        raise Stage65AcceptanceBlocked(context + " claims transmitted broker orders")


def _local_static_dashboard(root: Path) -> bool:
    """Only verify local Stage63 file presence + offline script/CSP markers.

    No local source marker is a real browser attack or approved face proof.
    """
    base = root / "src/nexus_titan/dashboard/static"
    expected = {
        "stage63.html": ("default-src 'none'", "connect-src 'none'",
                         "RELEASE NO-GO", "APPROVED TITAN FACE",
                         'src="stage63.js"', 'href="stage51.css"'),
        "stage63.css": ("operator-card-grid", "@media", "operator-markets"),
        "stage63.js": ("const STAGE62_FALSE", "const STAGE61_FALSE",
                       "textContent", "MAX_FILE_BYTES", "auditGeneration"),
    }
    for name, markers in expected.items():
        target = base / name
        if (target.is_symlink() or not target.is_file()
                or target.stat().st_size > 256 * 1024):
            return False
        try:
            body = target.read_text(encoding="utf-8")
        except (UnicodeError, ValueError, OSError):
            return False
        if not all(marker in body for marker in markers):
            return False
    return True


def inspect_stage65_release_acceptance(
    repo_root: Path,
    *,
    pr_snapshot: dict[str, Any],
    fo_evidence: Stage61FOMarketReadinessScorecard,
    trial: Stage64ShadowTrialGovernanceReport,
    integration: Stage62IntegrationReview,
) -> Stage65FinalAcceptanceReport:
    """Conservative final developer handoff: never a production permit."""
    if not isinstance(repo_root, Path) or not repo_root.is_dir() or repo_root.is_symlink():
        raise Stage65AcceptanceBlocked("Existing non-symlink local repo root required")
    if not isinstance(fo_evidence, Stage61FOMarketReadinessScorecard):
        raise Stage65AcceptanceBlocked("Typed Stage61 report required")
    if not isinstance(trial, Stage64ShadowTrialGovernanceReport):
        raise Stage65AcceptanceBlocked("Typed Stage64 trial report required")
    if not isinstance(integration, Stage62IntegrationReview):
        raise Stage65AcceptanceBlocked("Typed Stage62 report required")
    _require_denied(fo_evidence, _FALSE61, "Stage61")
    _require_denied(trial, _FALSE64, "Stage64")
    if (trial.release_decision != "BLOCKED_INDEPENDENT_EXTERNAL_EVIDENCE_REQUIRED"
            or trial.mandatory_external_blockers != _MANDATORY_EXTERNAL_BLOCKERS
            or trial.schema_version != 1
            or trial.underlying not in ("NIFTY", "BANKNIFTY")
            or trial.underlying != fo_evidence.underlying
            or trial.stage61_local_structural_check_observed is not fo_evidence.local_inputs_structurally_consistent
            or type(trial.declared_closed_trades) is not int
            or trial.declared_closed_trades < 0
            or _SHA.fullmatch(trial.local_trial_sha256 or "") is None
            or type(trial.local_trial_criteria_met) is not bool
            or len(fo_evidence.mandatory_release_blockers) < 8):
        raise Stage65AcceptanceBlocked("Stage64/Stage61 evidence mismatch or missing mandatory blockers")
    try:
        graph = inspect_pr_dependency_snapshot(pr_snapshot)
        fresh = inspect_stage62_candidate(repo_root, pr_snapshot=pr_snapshot)
    except (TypeError, ValueError, OSError) as exc:
        raise Stage65AcceptanceBlocked("Invalid PR/source audit evidence: "
                                       + type(exc).__name__) from exc
    if (integration != fresh
            or trial.stage62_local_static_check_observed is not fresh.local_static_review_passed):
        raise Stage65AcceptanceBlocked(
            "Stage62 report stale or does not match exact current reviewed source/snapshot")
    if graph.repository != "prathee001pr-sys/NEXUS-TITAN":
        raise Stage65AcceptanceBlocked("Review is for wrong GitHub repository")
    # This count is from selected local snapshot, not a live GitHub assertion.
    known_lists = sum(bool(x["changed_paths_complete"]) for x in pr_snapshot["pull_requests"])
    statuses: list[Stage65AcceptanceCheck] = []
    def local(name: str, value: bool, detail: str) -> None:
        statuses.append(Stage65AcceptanceCheck(
            name, "LOCAL_RESEARCH_PASS" if value else "LOCAL_RESEARCH_FAIL", detail))
    def external(name: str, detail: str) -> None:
        statuses.append(Stage65AcceptanceCheck(name, "EXTERNAL_EVIDENCE_MISSING", detail))
    def review(name: str, detail: str) -> None:
        statuses.append(Stage65AcceptanceCheck(name, "REVIEW_REQUIRED", detail))

    local("S65-SELECTED-AST-CI", fresh.local_static_review_passed,
          "AST/CI source text only; neither runtime security nor actual candidate-merge CI")
    local("S65-PR-GRAPH", graph.branch_graph_consistent,
          "Frozen GitHub PR base/head SHA continuity only; snapshot can go stale")
    local("S65-STAGE61-SYNTHETIC", fo_evidence.local_inputs_structurally_consistent,
          "Synthetic, no-fill F&O evidence has internally consistent declarations only")
    local("S65-STAGE64-SYNTHETIC-TRIAL", trial.local_trial_criteria_met,
          "Self-declared paper KPls only; not a real signed trial or broker P&L")
    local("S65-READONLY-OPERATOR-VIEW", _local_static_dashboard(repo_root),
          "Offline Stage63 dashboard files have selected static markers; no face asset")
    if len(graph.root_pr_numbers) != 1:
        review("S65-INDEPENDENT-STACKS",
               "Two distinct main-rooted stacks require manually reconciled base/merge semantics")
    else:
        review("S65-OWNER-STACK-REVIEW",
               "One visible root does not prove historical branches/merge approval")
    review("S65-CROSS-LINEAGE-OVERLAPS",
           str(len(graph.overlap_candidates))
           + " observed non-ancestor PR filename-overlap candidates; NOT proved merge conflicts")
    review("S65-INCOMPLETE-PR-DIFF-COVERAGE",
           str(graph.pr_count - known_lists)
           + " open PR file lists intentionally UNKNOWN; no conflict-free conclusion possible")
    review("S65-BRANCH-RULES",
           "Reported main.protected=" + str(graph.main_protected_reported)
           + "; current owner policies/rulesets still independently unverified")
    for code, action in _RELEASE_ACTIONS:
        external(code, action)
    local_success = all(c.status == "LOCAL_RESEARCH_PASS"
                        for c in statuses if c.check_id.startswith((
                            "S65-SELECTED-", "S65-PR-GRAPH",
                            "S65-STAGE61-", "S65-STAGE64-", "S65-READONLY-"
                        )))
    # A digest of operator-provided descriptors is NOT signed, authenticated
    # current GitHub state, a trusted trial audit, or real broker proof.
    material = json.dumps({
        "schema": 1,
        "repository": graph.repository,
        "main_sha": graph.main_sha,
        "snapshot_digest": fresh.frozen_pr_snapshot_sha256,
        "source_digest": fresh.source_subset_sha256,
        "trial_digest": trial.local_trial_sha256,
        "stage61_digest": fo_evidence.local_evidence_sha256,
        "overlaps": [(v.pr_a, v.pr_b, v.paths) for v in graph.overlap_candidates],
        "checks": [(x.check_id, x.status) for x in statuses],
    }, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return Stage65FinalAcceptanceReport(
        schema_version=1,
        scope="OFFLINE_DEVELOPER_HANDOFF_CHECKLIST_NO_RELEASE_AUTHORITY",
        reviewed_open_pr_count=graph.pr_count,
        reported_main_sha=graph.main_sha,
        reported_main_protected=graph.main_protected_reported,
        main_root_pr_numbers=graph.root_pr_numbers,
        checked_pr_file_list_count=known_lists,
        uninspected_pr_file_list_count=graph.pr_count - known_lists,
        independent_file_overlap_candidates=graph.overlap_candidates,
        all_pr_changed_files_observed=graph.complete_changed_file_coverage,
        selected_source_and_ci_structural_review_passed=fresh.local_static_review_passed,
        stage61_source_claims_locally_consistent=fo_evidence.local_inputs_structurally_consistent,
        stage64_local_trial_kpis_met=trial.local_trial_criteria_met,
        stage64_trial_underlying=trial.underlying,
        stage64_claimed_closed_trades=trial.declared_closed_trades,
        checks=tuple(statuses),
        required_owner_actions=_RELEASE_ACTIONS,
        critical_release_blocker_count=len(_RELEASE_ACTIONS),
        acceptance_packet_sha256=hashlib.sha256(material.encode()).hexdigest(),
        developer_offline_checklist_completed=local_success,
    )

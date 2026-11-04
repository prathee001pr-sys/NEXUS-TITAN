"""Stage80: offline release-candidate cutover gate, always NO-GO.

Combines a frozen, operator-exported GitHub PR dependency graph with local
Stage78 bypass inventory, Stage79 opt-in exact-head SQLite CAS AST contracts
and the presence of real synthetic F&O E2E tests.

This is NOT a Git three-way merge, actual candidate-commit build, authenticated
GitHub branch policy, control-flow proof, capital authority or trading permit.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus_titan.operations.pr_stack_audit import (
    StackAuditError, inspect_pr_dependency_snapshot,
)
from nexus_titan.operations.stage78_fo_gateway_cutover_audit import (
    Stage78CutoverBlocked, inspect_stage78_fo_cutover,
)

_STAGE55 = "src/nexus_titan/operations/isolated_atomic_execution_book.py"
_STAGE77 = "src/nexus_titan/operations/stage77_brokerless_fo_sandbox.py"
_E2E = "tests/test_full_chain_fo_data_to_sandbox_e2e.py"
_MAX_SOURCE = 512_000
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

_REQUIRED_E2E_TESTS = (
    "test_real_python_calls_connect_synthetic_csv_all_the_way_to_sqlite",
    "test_end_to_end_bad_lineage_blocks_before_sqlite_reservation",
    "test_kill_switch_between_synthetic_reserve_and_fill_blocks_and_allows_cancel",
)
_REQUIRED_CAS_METHODS = (
    ("reserve_synthetic_long_option", "reserve_synthetic_buy"),
    ("record_synthetic_fill", "record_simulated_fill"),
    ("cancel_synthetic_remaining", "cancel_unfilled"),
)
_REQUIRED_SNAPSHOT_ROOTS = (1, 3)
_EXTERNAL_BLOCKERS = (
    "TWO_INDEPENDENT_MAIN_ROOT_PR_LINEAGES_NOT_OWNER_RECONCILED",
    "INCOMPLETE_GITHUB_FILE_DIFF_COVERAGE",
    "GITHUB_MAIN_BRANCH_UNPROTECTED_IN_FROZEN_SNAPSHOT",
    "PROSPECTIVE_MERGED_TREE_CI_NOT_VERIFIED",
    "LEGACY_VIRTUAL_AND_DIRECT_LEDGER_APIS_NOT_GLOBALLY_FENCED",
    "NO_ONE_GLOBAL_AUTHENTICATED_FO_RISK_AND_ATOMIC_CAPITAL_AUTHORITY",
    "RISK_TELEMETRY_AND_REAL_MARKET_EVIDENCE_UNAUTHENTICATED",
    "SIGNED_OWNER_APPROVAL_AND_REAL_SHADOW_TRIAL_MISSING",
)


class Stage80CutoverBlocked(ValueError):
    """Malformed or contradictory integration evidence: fail closed."""


@dataclass(frozen=True, slots=True)
class Stage80IntegrationCandidateReadiness:
    scope: str
    frozen_open_pr_count: int
    frozen_main_sha: str
    frozen_main_protected: bool
    independent_root_prs: tuple[int, ...]
    graph_topology_locally_consistent: bool
    changed_file_lists_complete: bool
    changed_file_lists_observed: int
    known_cross_lineage_overlap_candidates: int
    stage78_direct_legacy_method_count: int
    stage78_legacy_paths_still_callable: bool
    stage79_local_sqlite_cas_shape_locally_inspected: bool
    stage77_cooperative_cas_call_sites_locally_inspected: int
    full_chain_synthetic_e2e_test_count: int
    source_manifest_sha256: str
    frozen_pr_snapshot_sha256: str
    action_blockers: tuple[str, ...]
    # These are all false: source structure + a frozen PR snapshot are
    # not independently authenticated or secure execution/release evidence.
    current_github_pr_state_independently_authenticated: bool = False
    actual_git_merge_conflicts_ruled_out: bool = False
    signed_merge_candidate_verified: bool = False
    prospective_merged_commit_ci_verified: bool = False
    main_branch_protection_independently_verified: bool = False
    all_legacy_order_fill_paths_unbypassably_fenced: bool = False
    global_atomic_capital_and_risk_admission_verified: bool = False
    independently_authenticated_market_and_kill_telemetry: bool = False
    actual_shadow_trading_validated: bool = False
    owner_merge_approval_authenticated: bool = False
    merge_authorized: bool = False
    paper_order_authorized: bool = False
    strategy_promotion_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE80_FO_INTEGRATION_CANDIDATE_RESEARCH_ONLY_NO_GO"


def _read(root: Path, relative: str) -> bytes:
    current = root
    for part in relative.split("/"):
        if part in ("", ".", ".."):
            raise Stage80CutoverBlocked("Unsafe source component")
        current = current / part
        if current.is_symlink():
            raise Stage80CutoverBlocked("Symlinked integration source denied: " + relative)
    if not current.is_file() or not 0 < current.stat().st_size <= _MAX_SOURCE:
        raise Stage80CutoverBlocked("Missing/oversized integration source: " + relative)
    try:
        return current.read_bytes()
    except OSError as exc:
        raise Stage80CutoverBlocked("Integration source unreadable") from exc


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    matches = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    if len(matches) != 1:
        raise Stage80CutoverBlocked("Integration class missing/ambiguous: " + name)
    return matches[0]


def _method(cls: ast.ClassDef, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    matches = [n for n in cls.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == name]
    if len(matches) != 1:
        raise Stage80CutoverBlocked("Integration method missing/ambiguous: " + name)
    return matches[0]


def _calls(fn: ast.AST, object_name: str, method: str) -> list[ast.Call]:
    return [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == method
        and ((
            object_name == "self"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "self"
        ) or (
            object_name == "self._book"
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "_book"
            and isinstance(n.func.value.value, ast.Name)
            and n.func.value.value.id == "self"
        ) or (
            object_name == "conn"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "conn"
        ))
    ]


def _keyword_has_attr(call: ast.Call, key: str, holder: str, attr: str) -> bool:
    for kw in call.keywords:
        if (kw.arg == key and isinstance(kw.value, ast.Attribute)
                and kw.value.attr == attr
                and isinstance(kw.value.value, ast.Name)
                and kw.value.value.id == holder):
            return True
    return False


def _stage79_contract(book_raw: bytes, gateway_raw: bytes) -> int:
    try:
        book_tree = ast.parse(book_raw.decode("utf-8"), filename=_STAGE55)
        gateway_tree = ast.parse(gateway_raw.decode("utf-8"), filename=_STAGE77)
    except (UnicodeError, SyntaxError) as exc:
        raise Stage80CutoverBlocked("Malformed risk/capital source AST") from exc
    book = _class(book_tree, "Stage55IsolatedSyntheticExecutionBook")
    gate = _class(gateway_tree, "Stage77BrokerlessFOSyntheticGateway")

    for name in ("_record", "reserve_synthetic_buy", "record_simulated_fill", "cancel_unfilled"):
        fn = _method(book, name)
        params = {p.arg for p in fn.args.args + fn.args.kwonlyargs}
        if not {"expected_revision", "expected_journal_tip"}.issubset(params):
            raise Stage80CutoverBlocked("Stage55 exact-head parameters missing: " + name)
    record = _method(book, "_record")
    begin = [c for c in _calls(record, "conn", "execute")
             if c.args and isinstance(c.args[0], ast.Constant)
             and c.args[0].value == "BEGIN IMMEDIATE"]
    if len(begin) != 1:
        raise Stage80CutoverBlocked("Stage55 atomic SQLite write begin marker missing")
    # Presence is source-shape evidence, never a dominance/execution proof.
    compares = [n for n in ast.walk(record) if isinstance(n, ast.Compare)]
    revision_checked = any(
        isinstance(c.left, ast.Name) and c.left.id == "expected_revision"
        and any(isinstance(x, ast.Name) and x.id == "rev" for x in c.comparators)
        for c in compares
    )
    head_checked = any(
        isinstance(c.left, ast.Name) and c.left.id == "expected_journal_tip"
        and any(isinstance(x, ast.Name) and x.id == "previous" for x in c.comparators)
        for c in compares
    )
    if not (revision_checked and head_checked):
        raise Stage80CutoverBlocked("Stage55 expected revision or head comparison missing")
    status = _method(gate, "_book_status")
    attr_names = {n.attr for n in ast.walk(status) if isinstance(n, ast.Attribute)}
    if not {"_expected_revision", "_expected_tip", "revision", "journal_tip"}.issubset(attr_names):
        raise Stage80CutoverBlocked("Stage77 active head-drift check missing")
    verified = 0
    for method, book_method in _REQUIRED_CAS_METHODS:
        fn = _method(gate, method)
        writes = _calls(fn, "self._book", book_method)
        checks = _calls(fn, "self", "_book_status")
        if (len(writes) != 1 or len(checks) != 1
                or checks[0].lineno >= writes[0].lineno):
            raise Stage80CutoverBlocked("Stage77 local precheck/write source ordering missing")
        call = writes[0]
        if (not _keyword_has_attr(call, "expected_revision", "current", "revision")
                or not _keyword_has_attr(call, "expected_journal_tip", "current", "journal_tip")):
            raise Stage80CutoverBlocked("Stage77 call misses exact-head SQLite CAS: " + method)
        verified += 1
    return verified


def inspect_stage80_integration_candidate(
    root: Path, *, frozen_snapshot: dict[str, Any],
) -> Stage80IntegrationCandidateReadiness:
    """Read-only source/PR inventory. A successful return is never merge GO."""
    if not isinstance(root, Path) or root.is_symlink() or not root.is_dir():
        raise Stage80CutoverBlocked("Explicit ordinary repository root required")
    try:
        graph = inspect_pr_dependency_snapshot(frozen_snapshot)
        stage78 = inspect_stage78_fo_cutover(root)
    except (StackAuditError, Stage78CutoverBlocked, ValueError, TypeError) as exc:
        raise Stage80CutoverBlocked("PR topology or global bypass inventory invalid") from exc
    if (graph.repository != "prathee001pr-sys/NEXUS-TITAN"
            or graph.pr_count < 70
            or graph.main_protected_reported is not False
            or tuple(graph.root_pr_numbers) != _REQUIRED_SNAPSHOT_ROOTS
            or graph.branch_graph_consistent is not True
            or graph.complete_changed_file_coverage is not False):
        raise Stage80CutoverBlocked("Unexpected frozen candidate PR graph / false protection claim")
    if (not stage78.local_source_inventory_complete
            or not stage78.local_stage77_expected_calls_observed
            or stage78.all_legacy_order_fill_paths_fenced is not False
            or stage78.independent_global_risk_gateway_verified is not False
            or stage78.broker_orders_transmitted != 0):
        raise Stage80CutoverBlocked("Stage78 bypass review claims unearned global authority")
    book_bytes = _read(root, _STAGE55)
    gate_bytes = _read(root, _STAGE77)
    e2e_bytes = _read(root, _E2E)
    call_sites = _stage79_contract(book_bytes, gate_bytes)
    try:
        e2e_tree = ast.parse(e2e_bytes.decode("utf-8"), filename=_E2E)
    except (UnicodeError, SyntaxError) as exc:
        raise Stage80CutoverBlocked("Synthetic E2E test source malformed") from exc
    testnames = {
        n.name for n in e2e_tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("test_")
    }
    if not set(_REQUIRED_E2E_TESTS).issubset(testnames):
        raise Stage80CutoverBlocked("Synthetic A-to-B F&O integration tests missing")
    snapshot_raw = json.dumps(
        frozen_snapshot, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    if not 0 < len(snapshot_raw) <= _MAX_SOURCE:
        raise Stage80CutoverBlocked("Frozen PR snapshot malformed or too large")
    observed_paths = sum(
        item.get("changed_paths_complete") is True
        for item in frozen_snapshot["pull_requests"]
    )
    sources = {
        "stage55": hashlib.sha256(book_bytes).hexdigest(),
        "stage77": hashlib.sha256(gate_bytes).hexdigest(),
        "synthetic_e2e": hashlib.sha256(e2e_bytes).hexdigest(),
        "stage78_local_review": stage78.source_inventory_sha256,
        "snapshot": hashlib.sha256(snapshot_raw).hexdigest(),
    }
    manifest = hashlib.sha256(json.dumps(
        sources, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    blockers = _EXTERNAL_BLOCKERS + tuple(graph.blockers)
    return Stage80IntegrationCandidateReadiness(
        scope="FROZEN_PR_GRAPH_AND_LOCAL_SYNTHETIC_FO_CUTOVER_SOURCES",
        frozen_open_pr_count=graph.pr_count,
        frozen_main_sha=graph.main_sha,
        frozen_main_protected=graph.main_protected_reported,
        independent_root_prs=graph.root_pr_numbers,
        graph_topology_locally_consistent=graph.branch_graph_consistent,
        changed_file_lists_complete=graph.complete_changed_file_coverage,
        changed_file_lists_observed=observed_paths,
        known_cross_lineage_overlap_candidates=len(graph.overlap_candidates),
        stage78_direct_legacy_method_count=stage78.observed_legacy_method_count,
        stage78_legacy_paths_still_callable=True,
        stage79_local_sqlite_cas_shape_locally_inspected=True,
        stage77_cooperative_cas_call_sites_locally_inspected=call_sites,
        full_chain_synthetic_e2e_test_count=len(_REQUIRED_E2E_TESTS),
        source_manifest_sha256=manifest,
        frozen_pr_snapshot_sha256=sources["snapshot"],
        action_blockers=tuple(dict.fromkeys(blockers)),
    )

"""Stage78 offline F&O risk-gateway cutover inventory (permanent NO-GO).

Combines Stage56 selected legacy bypass AST inventory, Stage70 selected
no-authority default audit, and Stage77 brokerless gateway call-surface
inspection. This cannot prove call-graph dominance, close bypasses, atomically
bind risk to capital, authenticate telemetry, or authorize any order.
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from nexus_titan.operations.risk_boundary_inventory import (
    Stage56BypassInventory, inspect_stage56_bypass_paths,
)
from nexus_titan.operations.stage70_fo_integration_gate import (
    Stage70AuditBlocked, Stage70IntegrationAudit, inspect_stage70_fo_integration,
)

_STAGE77 = "src/nexus_titan/operations/stage77_brokerless_fo_sandbox.py"
_EXPECTED_METHOD_CALLS = (
    ("reserve_synthetic_long_option", "_review", "reserve_synthetic_buy"),
    ("record_synthetic_fill", "_review", "record_simulated_fill"),
    ("cancel_synthetic_remaining", "_book_status", "cancel_unfilled"),
)
_REQUIRED_BYPASSES = (
    "VirtualAccount.submit_order",
    "VirtualAccount.approve_order",
    "VirtualAccount.execute_fill",
    "Stage55IsolatedSyntheticExecutionBook.reserve_synthetic_buy",
    "Stage55IsolatedSyntheticExecutionBook.record_simulated_fill",
)
_BLOCKERS = (
    "STAGE56_KNOWN_DIRECT_LEGACY_APIS_REMAIN_CALLABLE",
    "STAGE55_BOOK_DIRECT_MUTATION_REMAINS_CALLABLE",
    "STAGE77_IN_PROCESS_RISK_RECHECK_NOT_ATOMIC_WITH_SQLITE_BOOK",
    "STAGE77_RESTART_PENDING_INTENTS_NOT_AUTOMATICALLY_RECOVERED",
    "NO_SINGLE_GLOBAL_RISK_CAPITAL_OR_FILL_AUTHORITY",
    "NO_INDEPENDENT_KILL_SWITCH_OR_MARKET_DATA_AUTHENTICATION",
    "NO_LICENSED_POINT_IN_TIME_FO_FEED_AND_AUTHENTICATED_SHADOW_EVIDENCE",
    "NO_OWNER_APPROVED_PROTECTED_MAIN_MERGE_CANDIDATE",
)


class Stage78CutoverBlocked(ValueError):
    """Cannot certify a complete local source inventory: stop and review."""


@dataclass(frozen=True, slots=True)
class Stage78FOMandatoryGatewayCutoverAudit:
    inspected_legacy_source_files: int
    observed_legacy_direct_methods: tuple[str, ...]
    observed_legacy_method_count: int
    inspected_stage70_source_files: int
    observed_stage70_entrypoints: tuple[str, ...]
    stage77_gateway_methods: tuple[str, ...]
    stage77_statically_observed_local_call_pairs: tuple[str, ...]
    stage77_source_sha256: str
    source_inventory_sha256: str
    local_source_inventory_complete: bool
    local_stage77_expected_calls_observed: bool
    independent_global_risk_gateway_verified: bool = False
    all_legacy_order_fill_paths_fenced: bool = False
    stage55_direct_ledger_writes_disabled: bool = False
    atomically_authored_risk_and_funds_verified: bool = False
    independently_verified_risk_telemetry: bool = False
    restart_with_pending_orders_recovered: bool = False
    authorized_real_market_shadow_trading: bool = False
    owner_merge_approval_verified: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    release_blockers: tuple[str, ...] = _BLOCKERS
    verdict: str = "STAGE78_STATIC_FO_GLOBAL_CUTOVER_NOT_VERIFIED_NO_GO"


def _read_source(root: Path, relative: str) -> bytes:
    current = root
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink():
            raise Stage78CutoverBlocked("Symlinked cutover source not trusted: " + relative)
    if not current.is_file() or not 0 < current.stat().st_size <= 512_000:
        raise Stage78CutoverBlocked("Missing/oversized cutover source: " + relative)
    try:
        return current.read_bytes()
    except OSError as exc:
        raise Stage78CutoverBlocked("Unreadable cutover source: " + relative) from exc


def _function(cls: ast.ClassDef, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    found = [node for node in cls.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == name]
    if len(found) != 1:
        raise Stage78CutoverBlocked("Stage77 method missing or duplicated: " + name)
    return found[0]


def _call(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if (isinstance(func.value, ast.Name) and func.value.id == "self"):
        return "self." + func.attr
    if (isinstance(func.value, ast.Attribute)
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "self"):
        return "self." + func.value.attr + "." + func.attr
    return None


def _validate_stage77_tree(tree: ast.AST) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(tree, ast.Module):
        raise Stage78CutoverBlocked("Invalid Stage77 AST module")
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "Stage77BrokerlessFOSyntheticGateway"]
    if len(classes) != 1:
        raise Stage78CutoverBlocked("Missing/duplicate Stage77 gateway")
    gateway = classes[0]
    labels: list[str] = []
    names: list[str] = []
    for method, precheck, book_call in _EXPECTED_METHOD_CALLS:
        function = _function(gateway, method)
        calls = [(n.lineno, _call(n)) for n in ast.walk(function)
                 if isinstance(n, ast.Call)]
        calls = [(line, name) for line, name in calls if name is not None]
        before = ("self." + precheck)
        after = "self._book." + book_call
        gate_lines = [line for line, name in calls if name == before]
        write_lines = [line for line, name in calls if name == after]
        if len(gate_lines) != 1 or len(write_lines) != 1 or gate_lines[0] >= write_lines[0]:
            raise Stage78CutoverBlocked(
                "Stage77 expected lexical precheck/book ordering drift: " + method
            )
        names.append(method)
        labels.append(method + ":" + before + " -> " + after)
    # Important: textual AST call order is NOT verified runtime dominance,
    # mutex protection, broker isolation or a global authorization boundary.
    return tuple(names), tuple(labels)


def inspect_stage78_fo_cutover(repo_root: Path) -> Stage78FOMandatoryGatewayCutoverAudit:
    """Review known source surfaces; local inventory completion is NOT GO."""
    if not isinstance(repo_root, Path) or repo_root.is_symlink() or not repo_root.is_dir():
        raise Stage78CutoverBlocked("Explicit real repository directory required")
    first: Stage56BypassInventory = inspect_stage56_bypass_paths(repo_root)
    try:
        second: Stage70IntegrationAudit = inspect_stage70_fo_integration(repo_root)
    except Stage70AuditBlocked as exc:
        raise Stage78CutoverBlocked("Stage70 baseline no-authority audit failed") from exc
    if (not first.local_static_scan_complete or first.unverifiable_sources
            or not first.reviewed_sources_sha256
            or first.legacy_order_paths_globally_disabled is not False
            or first.all_execution_paths_proven_fenced is not False):
        raise Stage78CutoverBlocked("Stage56 source inventory incomplete or claimed authority")
    if not set(_REQUIRED_BYPASSES).issubset(first.known_callable_surfaces):
        raise Stage78CutoverBlocked("Missing selected direct legacy path: cannot infer it was fenced")
    if (not second.static_inventory_complete or second.safe_to_merge is not False
            or second.global_risk_veto_unbypassable is not False
            or second.live_trading_enabled is not False
            or second.broker_orders_transmitted != 0):
        raise Stage78CutoverBlocked("Stage70 review claimed unsupported authorization")
    raw = _read_source(repo_root, _STAGE77)
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=_STAGE77)
    except (UnicodeError, SyntaxError) as exc:
        raise Stage78CutoverBlocked("Stage77 malformed AST") from exc
    methods, calls = _validate_stage77_tree(tree)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = json.dumps({
        "stage56": first.reviewed_sources_sha256,
        "stage70": second.source_digest_sha256,
        "stage77": digest,
        "legacy": first.known_callable_surfaces,
        "gateway_calls": calls,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return Stage78FOMandatoryGatewayCutoverAudit(
        inspected_legacy_source_files=first.inspected_files,
        observed_legacy_direct_methods=first.known_callable_surfaces,
        observed_legacy_method_count=len(first.known_callable_surfaces),
        inspected_stage70_source_files=second.sources_parsed,
        observed_stage70_entrypoints=second.observed_execution_entrypoints,
        stage77_gateway_methods=methods,
        stage77_statically_observed_local_call_pairs=calls,
        stage77_source_sha256=digest,
        source_inventory_sha256=hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
        local_source_inventory_complete=True,
        local_stage77_expected_calls_observed=True,
    )

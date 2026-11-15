"""Stage70: static F&O-first integration inventory; always external release NO-GO.

This audit parses selected local files only. It cannot prove control-flow
dominance, credential isolation, GitHub merge safety, or real market validity.
No modules from the project are imported and no order functions are called.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path

_SOURCE_PATHS = (
    "src/nexus_titan/virtual/order_manager.py",
    "src/nexus_titan/crypto/crypto_engine.py",
    "src/nexus_titan/shadow/guarded_options_research.py",
    "src/nexus_titan/operations/stage69_risk_budget_preflight.py",
    "src/nexus_titan/operations/brokerless_risk_veto.py",
)
_ENTRYPOINTS = (
    ("src/nexus_titan/virtual/order_manager.py", "VirtualAccount", "submit_order"),
    ("src/nexus_titan/virtual/order_manager.py", "VirtualAccount", "approve_order"),
    ("src/nexus_titan/virtual/order_manager.py", "VirtualAccount", "execute_fill"),
    ("src/nexus_titan/crypto/crypto_engine.py", "CryptoVirtualAccount", "execute_crypto_order"),
    ("src/nexus_titan/shadow/guarded_options_research.py", "", "guarded_options_research_buy"),
)
_DENIED_STAGE69 = (
    "caller_risk_telemetry_authenticated",
    "independently_authenticated_market_quote",
    "global_legacy_entrypoints_fenced",
    "single_atomic_authority_for_all_ledger_books",
    "risk_rechecked_at_real_fill",
    "authenticated_owner_approval",
    "budget_hold_performed",
    "order_submission_authorized",
    "strategy_promotion_authorized",
    "real_money_trading_enabled",
    "production_ready",
)
_BLOCKERS = (
    "Review all actual current PR diffs, competing main-root histories and merged-tree CI",
    "Owner enable branch protection, required reviews and release approval",
    "Prove a global unbypassable order/fill gateway and independent risk veto",
    "Prove atomic capital, reservations, fees, positions and crash reconciliation",
    "Authenticate owner, data, broker boundary and credential custody",
    "License and validate point-in-time real India F&O chains, quotes and contract changes",
    "Validate net-cost F&O backtests, real-feed supervised shadow results and stress cases",
    "Complete independent security, recovery and compliance assessment",
)


class Stage70AuditBlocked(ValueError):
    """Selected source or safety marker changed: manual review required."""


@dataclass(frozen=True, slots=True)
class Stage70IntegrationAudit:
    scope: str
    sources_parsed: int
    observed_execution_entrypoints: tuple[str, ...]
    source_digest_sha256: str
    stage69_denied_authority_defaults_checked: int
    stage56_default_instrument: str
    static_inventory_complete: bool
    external_release_blockers: tuple[str, ...]
    # Static names and defaults CANNOT establish these external facts.
    current_github_pr_graph_verified: bool = False
    actual_main_merge_reviewed: bool = False
    branch_protection_verified: bool = False
    global_risk_veto_unbypassable: bool = False
    atomic_capital_authority_verified: bool = False
    licensed_fo_data_verified: bool = False
    live_feed_shadow_pnl_verified: bool = False
    human_release_approval_verified: bool = False
    safe_to_merge: bool = False
    production_ready: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE70_STATIC_INVENTORY_COMPLETE_RELEASE_NO_GO"


def _source(root: Path, relative: str) -> str:
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise Stage70AuditBlocked("symlinked audit input: " + relative)
    if not path.is_file() or not 0 < path.stat().st_size <= 512 * 1024:
        raise Stage70AuditBlocked("missing or oversized audit input: " + relative)
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Stage70AuditBlocked("unreadable audit input: " + relative) from exc


def _klass(tree: ast.Module, name: str) -> ast.ClassDef:
    found = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    if len(found) != 1:
        raise Stage70AuditBlocked("missing or duplicate class: " + name)
    return found[0]


def _has_function(nodes: list[ast.stmt], name: str) -> bool:
    return sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == name for n in nodes) == 1


def _literal_field(cls: ast.ClassDef, field: str, expected: object) -> bool:
    values = [n.value for n in cls.body
              if isinstance(n, ast.AnnAssign)
              and isinstance(n.target, ast.Name) and n.target.id == field]
    return len(values) == 1 and isinstance(values[0], ast.Constant) and (
        type(values[0].value) is type(expected) and values[0].value == expected
    )


def inspect_stage70_fo_integration(repo_root: Path) -> Stage70IntegrationAudit:
    """Fail closed on changed static inventory; never authorize execution."""
    root = Path(repo_root)
    if root.is_symlink() or not root.is_dir():
        raise Stage70AuditBlocked("real local repository directory required")
    parsed: dict[str, ast.Module] = {}
    digester = hashlib.sha256()
    for path in _SOURCE_PATHS:
        body = _source(root, path)
        digester.update(path.encode("utf-8") + b"\0" + body.encode("utf-8") + b"\0")
        try:
            parsed[path] = ast.parse(body, filename=path)
        except SyntaxError as exc:
            raise Stage70AuditBlocked("syntax error in selected source: " + path) from exc
    discovered: list[str] = []
    for path, cls_name, method in _ENTRYPOINTS:
        statements = _klass(parsed[path], cls_name).body if cls_name else parsed[path].body
        if not _has_function(statements, method):
            raise Stage70AuditBlocked("entrypoint changed: " + path + ":" + method)
        discovered.append((cls_name + "." if cls_name else "") + method)
    report = _klass(
        parsed["src/nexus_titan/operations/stage69_risk_budget_preflight.py"],
        "Stage69ResearchPreflight",
    )
    for field in _DENIED_STAGE69:
        if not _literal_field(report, field, False):
            raise Stage70AuditBlocked("Stage69 no-authority default changed: " + field)
    if not _literal_field(report, "broker_orders_transmitted", 0):
        raise Stage70AuditBlocked("Stage69 synthetic broker order default changed")
    intent = _klass(
        parsed["src/nexus_titan/operations/brokerless_risk_veto.py"],
        "Stage56SyntheticIntent",
    )
    if not _literal_field(intent, "instrument_type", "EQUITY_DELIVERY"):
        raise Stage70AuditBlocked("Stage56 research instrument default changed")
    return Stage70IntegrationAudit(
        scope="F_AND_O_FIRST_STATIC_EXECUTION_SURFACE_AUDIT_ONLY",
        sources_parsed=len(parsed),
        observed_execution_entrypoints=tuple(discovered),
        source_digest_sha256=digester.hexdigest(),
        stage69_denied_authority_defaults_checked=len(_DENIED_STAGE69) + 1,
        stage56_default_instrument="EQUITY_DELIVERY",
        static_inventory_complete=True,
        external_release_blockers=_BLOCKERS,
    )

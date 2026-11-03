"""Stage52: bounded read-only source/security inventory for offline TITAN.

This is an evidence-producing developer check, NOT a sandbox, global policy
firewall, authenticated human identity, broker risk service, or production
security attestation. Only a *subset* of repository structure is inspected;
a source file can still behave maliciously despite passing structural checks.
The verdict ALWAYS blocks production/live trading and automatic promotion.

No network, subprocess, source modification, DB creation, token keys or
trading orders. Run against the checked-out *exact* candidate Git tree.
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_REVIEWED_CODE = {
    "src/nexus_titan/operations/paper_deployment.py": {
        "PaperOnlyDeployment": ("request_buy", "request_sell_to_close", "status"),
    },
    "src/nexus_titan/operations/offline_entry_readiness.py": {
        "Stage45ConservativePaperEntry": ("status", "request_buy"),
    },
    "src/nexus_titan/operations/offline_risk_veto.py": {
        "Stage47OfflineRiskVetoEntry": ("inspect", "request_buy"),
    },
    "src/nexus_titan/operations/signed_paper_approval.py": {
        "Stage48SignedPaperSession": ("pending_challenge", "approve_pending_buy"),
    },
    "src/nexus_titan/operations/durable_paper_fence.py": {
        "Stage49DurablePaperFence": ("inspect", "request_first_synthetic_buy"),
    },
    "src/nexus_titan/operations/synthetic_capital_authority.py": {
        "Stage53SyntheticCapitalAuthority": ("inspect", "hold_for_synthetic_research"),
    },
    "src/nexus_titan/operations/multi_ledger_recovery_audit.py": {
        "Stage54ReadOnlyMultiLedgerAudit": ("inspect",),
    },
    "src/nexus_titan/dashboard/paper_read_model.py": {
        "Stage50ReadOnlyPaperDashboard": ("snapshot",),
    },
    "src/nexus_titan/dashboard/api_service.py": {
        "DashboardBackendService": ("get_stage50_paper_safety",),
    },
    "src/nexus_titan/core/security_gates.py": {
        "CryptographicApprovalVerifier": ("verify_and_consume",),
    },
    "src/nexus_titan/virtual/order_manager.py": {
        "VirtualAccount": ("submit_order", "approve_order", "execute_fill"),
    },
}

_FRONTEND_FILES = (
    "src/nexus_titan/dashboard/static/stage51.html",
    "src/nexus_titan/dashboard/static/stage51.css",
    "src/nexus_titan/dashboard/static/stage51.js",
)

_RELEASE_BLOCKERS = (
    "B01: Multiple legacy direct Python order/fill entrypoints remain; optional facades are bypassable",
    "B02: Global independently enforced Risk & Veto boundary has not been demonstrated",
    "B03: Signed HMAC token possession is not independently authenticated human identity",
    "B04: VirtualAccount and research ledger do not share atomic capital/settlement truth",
    "B05: Stage49 coordinator is cooperative, not unbypassable; crash recovery manual",
    "B06: Stage51 static viewer accepts untrusted local files, not authenticated account evidence",
    "B07: Licensed point-in-time real Indian F&O market data is not integrated/validated",
    "B08: Actual market shadow trading and execution quality are unverified",
    "B09: Full PR stack reconciliation, prospective merged-tree CI and owner approval remain",
    "B10: Required original TITAN cybernetic face artwork not yet wired to frontend",
    "B11: Independent signer key custody, credentials revocation and approval/fill-time recheck unverified",
    "B12: No authorized broker connectivity or production deployment security review",
)


@dataclass(frozen=True, slots=True)
class StaticSecurityCheck:
    check_id: str
    passed: bool
    finding: str


@dataclass(frozen=True, slots=True)
class Stage52SecurityReview:
    schema_version: int
    stage: int
    scope: str
    reviewed_source_digest: str | None
    checked_artifact_count: int
    local_structural_controls_passed: bool
    findings: tuple[StaticSecurityCheck, ...]
    known_write_entrypoints: tuple[str, ...]
    release_blockers: tuple[str, ...]
    # ALWAYS false, including for perfectly clean structural review.
    production_release_allowed: bool = False
    genuine_live_data_authenticated: bool = False
    independent_human_identity_verified: bool = False
    global_unbypassable_risk_enforced: bool = False
    unified_capital_atomicity_verified: bool = False
    signed_candidate_commit_or_pr_review_verified: bool = False
    autonomous_strategy_promotion_allowed: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_checked_file(root: Path, relative: str) -> bytes:
    """Refuse symlinks, missing/nonfiles and unexpectedly huge source files.

    This is an inspection guard, not a defense against concurrent replacement
    by a malicious account owner with direct filesystem writes.
    """
    parts = Path(relative).parts
    if (not parts or Path(relative).is_absolute()
            or any(p in ("", ".", "..") for p in parts)):
        raise ValueError("Unsafe relative source path")
    loc = root
    for part in parts:
        loc = loc / part
        if loc.is_symlink():
            raise ValueError("Symlinked source or parent path is unsupported")
    if not loc.is_file():
        raise ValueError("Required reviewed source file missing or not regular")
    if loc.stat().st_size > 512_000:
        raise ValueError("Reviewed source file is unexpectedly large")
    return loc.read_bytes()


def _source_fingerprint(raw: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(raw):
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name.encode("utf-8"))
        digest.update(len(raw[name]).to_bytes(8, "big"))
        digest.update(hashlib.sha256(raw[name]).digest())
    return digest.hexdigest()


def _methods_in(tree: ast.AST, class_name: str) -> set[str]:
    matches = [node for node in ast.walk(tree)
               if isinstance(node, ast.ClassDef) and node.name == class_name]
    if len(matches) != 1:
        return set()
    return {node.name for node in matches[0].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def inspect_stage52_security_sources(repo_root: Path) -> Stage52SecurityReview:
    """Produce a deterministic no-write static audit from checked-out files.

    Passing structural checks is deliberately NOT a release or risk permit.
    Every known blocking security dependency is reported unchanged.
    """
    if not isinstance(repo_root, Path):
        raise TypeError("Explicit pathlib.Path repository root required")
    findings: list[StaticSecurityCheck] = []
    raw: dict[str, bytes] = {}
    root_ok = repo_root.is_dir() and not repo_root.is_symlink()
    if not root_ok:
        findings.append(StaticSecurityCheck(
            "S52-ROOT", False, "Repository path missing, symlinked or not a directory",
        ))
    required = tuple(_REVIEWED_CODE) + _FRONTEND_FILES
    for relative in required:
        try:
            if not root_ok:
                raise ValueError("Repository root unverified")
            raw[relative] = _read_checked_file(repo_root, relative)
        except (OSError, ValueError) as exc:
            findings.append(StaticSecurityCheck(
                "S52-SOURCE-" + relative, False, str(exc),
            ))

    for relative, classes in _REVIEWED_CODE.items():
        if relative not in raw:
            continue
        try:
            tree = ast.parse(raw[relative].decode("utf-8"), filename=relative)
        except (UnicodeError, SyntaxError, ValueError) as exc:
            findings.append(StaticSecurityCheck(
                "S52-AST-" + relative, False,
                "Expected Python module cannot be parsed: " + type(exc).__name__,
            ))
            continue
        for class_name, needed in classes.items():
            actual = _methods_in(tree, class_name)
            missing = sorted(set(needed) - actual)
            findings.append(StaticSecurityCheck(
                "S52-PY-" + class_name,
                not missing,
                "Required code-level interface structurally present" if not missing
                else "Missing named code surface: " + ", ".join(missing),
            ))

    html = raw.get(_FRONTEND_FILES[0], b"").decode("utf-8", errors="replace")
    css = raw.get(_FRONTEND_FILES[1], b"").decode("utf-8", errors="replace")
    js = raw.get(_FRONTEND_FILES[2], b"").decode("utf-8", errors="replace")
    html_markers = (
        "default-src 'none'", "connect-src 'none'", "script-src 'self'",
        "style-src 'self'", "form-action 'none'", "base-uri 'none'",
        'src="stage51.js"', 'href="stage51.css"',
        'type="file"', "APPROVED TITAN FACE",
    )
    missing_html = [mark for mark in html_markers if mark not in html]
    findings.append(StaticSecurityCheck(
        "S52-CSP-AND-FACE-PRESERVATION",
        bool(html) and not missing_html,
        "Offline CSP and locked-face placeholder structurally present"
        if not missing_html and html else "Missing offline HTML markers: " + ", ".join(missing_html),
    ))
    bad_js = [x for x in (
        "innerHTML", "outerHTML", "insertAdjacentHTML", "fetch(",
        "XMLHttpRequest", "WebSocket(", "EventSource(", "sendBeacon(",
        "eval(", "new Function(", "document.cookie", "localStorage.",
        "approve_order(", "execute_fill(", "submit_order(",
    ) if x in js]
    js_required = (
        "textContent", "Object.hasOwn", "file.size <= 256 * 1024",
        "LOCAL_SYNTHETIC_REVIEW_ONLY", "combined_cash_cents",
        "Green local presentation contradicts",
        "Cash-match claim contradicts", "selectionGeneration",
    )
    missing_js = [mark for mark in js_required if mark not in js]
    findings.append(StaticSecurityCheck(
        "S52-OFFLINE-JS-SAFETY",
        bool(js) and not bad_js and not missing_js,
        "Bounded text-only frontend markers found; runtime browser test still required"
        if js and not bad_js and not missing_js
        else "Unsafe or incomplete static frontend: " + ", ".join(bad_js + missing_js),
    ))
    # Compare the actual root theme declarations, not arbitrary color
    # strings in gradients: otherwise a changed --cyan token can be masked
    # by stale color references elsewhere in the stylesheet.
    required_css = (
        "--black:#080b0f", "--panel:#151a20", "--silver:#b9c2cd",
        "--cyan:#54c5d5", "--green:#32af79", "--red:#d65464",
    )
    missing_css = [mark for mark in required_css if mark not in css.lower()]
    findings.append(StaticSecurityCheck(
        "S52-LOCKED-THEME",
        bool(css) and not missing_css,
        "Black/silver restrained accent palette present"
        if css and not missing_css else "Missing locked palette markers: " + ", ".join(missing_css),
    ))
    complete = len(raw) == len(required)
    findings.append(StaticSecurityCheck(
        "S52-REVIEWED-SOURCE-COMPLETE", complete,
        "All bounded reviewed files present" if complete else "One or more reviewed files missing",
    ))
    structural = bool(findings) and all(item.passed for item in findings)
    # Even a passing static inspection does NOT establish global mandatory
    # enforcement; the following public methods make legacy bypass possible.
    known = (
        "VirtualAccount.submit_order",
        "VirtualAccount.approve_order",
        "VirtualAccount.execute_fill",
        "PaperOnlyDeployment.request_buy",
        "Stage48SignedPaperSession.request_synthetic_buy",
    )
    return Stage52SecurityReview(
        schema_version=1,
        stage=52,
        scope="STATIC_LOCAL_SOURCE_INSPECTION_ONLY",
        reviewed_source_digest=_source_fingerprint(raw) if complete else None,
        checked_artifact_count=len(raw),
        local_structural_controls_passed=structural,
        findings=tuple(findings),
        known_write_entrypoints=known,
        release_blockers=_RELEASE_BLOCKERS,
    )

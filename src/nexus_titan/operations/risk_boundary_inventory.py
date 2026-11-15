"""Stage56 local source inventory of *known* bypassable order entrypoints.

An AST inspection of selected repository files can show whether known direct
methods are still present. It CANNOT establish global containment, secure a
process, remove credential access, or identify every hidden call path.
Missing/renamed source is an UNKNOWN failure, never evidence of safety.

The scanner is purely read-only. It cannot approve or make any order.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path


_KNOWN_DIRECT_SURFACES = {
    "src/nexus_titan/virtual/order_manager.py": {
        "VirtualAccount": (
            "submit_order", "approve_order", "execute_fill",
            "cancel_order", "emergency_square_off",
        ),
    },
    "src/nexus_titan/operations/paper_deployment.py": {
        "PaperOnlyDeployment": ("request_buy", "request_sell_to_close"),
    },
    "src/nexus_titan/operations/offline_risk_veto.py": {
        "Stage47OfflineRiskVetoEntry": ("request_buy",),
    },
    "src/nexus_titan/operations/signed_paper_approval.py": {
        "Stage48SignedPaperSession": ("request_synthetic_buy", "approve_pending_buy"),
    },
    "src/nexus_titan/operations/durable_paper_fence.py": {
        "Stage49DurablePaperFence": ("request_first_synthetic_buy",),
    },
    "src/nexus_titan/operations/isolated_atomic_execution_book.py": {
        "Stage55IsolatedSyntheticExecutionBook": (
            "reserve_synthetic_buy", "record_simulated_fill", "cancel_unfilled"
        ),
    },
}


@dataclass(frozen=True, slots=True)
class Stage56BypassInventory:
    scope: str
    inspected_files: int
    known_callable_surfaces: tuple[str, ...]
    unverifiable_sources: tuple[str, ...]
    reviewed_sources_sha256: str | None
    local_static_scan_complete: bool
    legacy_order_paths_globally_disabled: bool = False
    independent_process_credential_isolation_verified: bool = False
    all_execution_paths_proven_fenced: bool = False
    production_ready: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0


def inspect_stage56_bypass_paths(repo_root: Path) -> Stage56BypassInventory:
    """Report selected direct methods; fail closed if code is missing/malformed."""
    if not isinstance(repo_root, Path):
        raise TypeError("Explicit repository Path required")
    paths = []
    missing = []
    digest = hashlib.sha256()
    checked = 0
    for name, classes in sorted(_KNOWN_DIRECT_SURFACES.items()):
        p = repo_root
        try:
            if not repo_root.is_dir() or repo_root.is_symlink():
                raise ValueError("Candidate source root unverified")
            for part in Path(name).parts:
                p = p / part
                if p.is_symlink():
                    raise ValueError("Symlinked reviewed source path")
            if not p.is_file() or p.stat().st_size > 512_000:
                raise ValueError("Missing or oversized reviewed source")
            raw = p.read_bytes()
            source = ast.parse(raw.decode("utf-8"), filename=name)
            checked += 1
            digest.update(name.encode("utf-8"))
            digest.update(hashlib.sha256(raw).digest())
            for cls, methods in classes.items():
                matching = [
                    node for node in source.body
                    if isinstance(node, ast.ClassDef) and node.name == cls
                ]
                if len(matching) != 1:
                    missing.append(name + ":" + cls + " unverified")
                    continue
                found = {
                    node.name for node in matching[0].body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                for method in methods:
                    if method not in found:
                        missing.append(name + ":" + cls + "." + method + " unverified")
                    else:
                        paths.append(cls + "." + method)
        except (OSError, ValueError, UnicodeError, SyntaxError):
            missing.append(name + ": unable to inspect")
    return Stage56BypassInventory(
        scope="STAGE56_SELECTED_SOURCE_AST_ONLY_NOT_GLOBAL_ENFORCEMENT",
        inspected_files=checked,
        known_callable_surfaces=tuple(sorted(paths)),
        unverifiable_sources=tuple(sorted(missing)),
        reviewed_sources_sha256=digest.hexdigest() if checked == len(_KNOWN_DIRECT_SURFACES)
            and not missing else None,
        local_static_scan_complete=(checked == len(_KNOWN_DIRECT_SURFACES) and not missing),
    )

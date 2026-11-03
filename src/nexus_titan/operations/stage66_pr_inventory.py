"""Stage66 — exhaustive, *frozen* PR filename inventory gate.

Only six locally captured, unsigned GitHub REST exports are read.  "100% file
list coverage" means filenames for the captured PR heads, NOT code review,
three-way merge verification, current GitHub attestation or release approval.
No network, broker, market data, git writes or execution access.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus_titan.operations.pr_stack_audit import (
    OverlapCandidate, PRStackAudit, StackAuditError,
    inspect_pr_dependency_snapshot,
)

REPOSITORY = "prathee001pr-sys/NEXUS-TITAN"
RECORDED_MAIN_SHA = "40e93cfb77fa0650e4f57428c6d77f70bb78d564"
PARTS = 6
RECORDED_OPEN_PRS = 56
MAX_PART_BYTES = 256 * 1024


class Stage66InventoryError(ValueError):
    """Malformed, missing or internally inconsistent offline PR evidence."""


@dataclass(frozen=True, slots=True)
class Stage66InventoryReview:
    scope: str
    source_captured_at_start: str
    source_captured_at_end: str
    recorded_main_sha: str
    recorded_main_protection_reported: bool
    reviewed_pr_count: int
    fully_recorded_changed_file_lists: int
    total_changed_file_entries: int
    root_pr_numbers: tuple[int, ...]
    overlap_candidates: tuple[OverlapCandidate, ...]
    graph_consistent_at_capture: bool
    frozen_file_list_coverage_complete: bool
    audit_blockers: tuple[str, ...]
    # All current/external claims are intentionally false.
    current_github_state_authenticated: bool = False
    full_source_diff_review_verified: bool = False
    three_way_merge_conflicts_ruled_out: bool = False
    branch_protection_independently_verified: bool = False
    merged_tree_ci_verified: bool = False
    owner_merge_approval_verified: bool = False
    safe_to_merge: bool = False
    production_ready: bool = False
    live_trading_enabled: bool = False
    merges_performed: int = 0
    broker_orders_transmitted: int = 0


def _unique_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in pairs:
        if k in result:
            raise Stage66InventoryError("duplicate JSON key")
        result[k] = v
    return result


def _reject_constant(value: str) -> None:
    raise Stage66InventoryError("nonfinite JSON number rejected")


def _utc_time(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 50:
        raise Stage66InventoryError("invalid captured_at_utc")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Stage66InventoryError("invalid captured_at_utc") from exc
    if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
        raise Stage66InventoryError("capture timestamp is not UTC")
    return stamp


def inspect_stage66_inventory(repo_root: Path) -> Stage66InventoryReview:
    """Analyze the 56 captured open draft PRs; fail-closed on incomplete export.

    This is *not* an online audit; any branch change after the captures makes
    the evidence stale. The captured main SHA and metadata are operator records.
    """
    folder = Path(repo_root) / "docs"
    entries: list[dict[str, Any]] = []
    times: list[datetime] = []
    for part in range(1, PARTS + 1):
        file = folder / f"STAGE66_PR_FILES_PART_{part:02d}_2026-11-03.json"
        if file.is_symlink() or not file.is_file():
            raise Stage66InventoryError(f"missing or symlinked part {part}")
        size = file.stat().st_size
        if not 0 < size <= MAX_PART_BYTES:
            raise Stage66InventoryError(f"part {part} size invalid")
        try:
            data = json.loads(
                file.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_json_keys,
                parse_constant=_reject_constant,
            )
        except (UnicodeError, json.JSONDecodeError, OSError) as exc:
            raise Stage66InventoryError(f"unreadable part {part}") from exc
        if not isinstance(data, dict):
            raise Stage66InventoryError(f"part {part} not an object")
        if (
            type(data.get("schema_version")) is not int or data["schema_version"] != 1
            or data.get("repository") != REPOSITORY
            or type(data.get("part")) is not int or data["part"] != part
            or type(data.get("parts")) is not int or data["parts"] != PARTS
            or type(data.get("expected_open_count")) is not int
            or data["expected_open_count"] != RECORDED_OPEN_PRS
        ):
            raise Stage66InventoryError(f"part {part} metadata mismatch")
        times.append(_utc_time(data.get("captured_at_utc")))
        rows = data.get("pull_requests")
        if not isinstance(rows, list) or len(rows) != (10 if part < PARTS else 6):
            raise Stage66InventoryError(f"part {part} row count mismatch")
        for row in rows:
            if not isinstance(row, dict):
                raise Stage66InventoryError("invalid PR row")
            if row.get("changed_paths_complete") is not True:
                raise Stage66InventoryError("incomplete changed-file list")
            if not isinstance(row.get("changed_paths"), list) or not row["changed_paths"]:
                raise Stage66InventoryError("empty or invalid changed-file list")
            entries.append(row)
    if any(a > b for a, b in zip(times, times[1:])):
        raise Stage66InventoryError("capture time sequence is out of order")
    numbers = [row.get("number") for row in entries]
    if (len(entries) != RECORDED_OPEN_PRS
            or numbers != sorted(numbers)
            or len(set(numbers)) != RECORDED_OPEN_PRS):
        raise Stage66InventoryError("PR identifiers/coverage incomplete or duplicated")

    snapshot = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "captured_at_utc": times[-1].isoformat(),
        "main_ref": "main",
        "main_sha": RECORDED_MAIN_SHA,
        "main_protected": False,  # captured status, NOT verified ruleset.
        "pull_requests": entries,
    }
    try:
        audit: PRStackAudit = inspect_pr_dependency_snapshot(snapshot)
    except (StackAuditError, TypeError) as exc:
        raise Stage66InventoryError("invalid PR dependency snapshot") from exc
    if (
        not audit.branch_graph_consistent
        or not audit.complete_changed_file_coverage
        or audit.pr_count != RECORDED_OPEN_PRS
        or audit.root_pr_numbers != (1, 3)
        or any(x.get("state") != "open" or x.get("draft") is not True
               or x.get("merged") is not False for x in entries)
    ):
        raise Stage66InventoryError("branch graph/state invalid or drifted")

    return Stage66InventoryReview(
        scope="SIGNED-NONE_FROZEN_PR_FILENAME_AUDIT_NO_GO",
        source_captured_at_start=times[0].isoformat(),
        source_captured_at_end=times[-1].isoformat(),
        recorded_main_sha=RECORDED_MAIN_SHA,
        recorded_main_protection_reported=False,
        reviewed_pr_count=RECORDED_OPEN_PRS,
        fully_recorded_changed_file_lists=RECORDED_OPEN_PRS,
        total_changed_file_entries=sum(len(x["changed_paths"]) for x in entries),
        root_pr_numbers=audit.root_pr_numbers,
        overlap_candidates=audit.overlap_candidates,
        graph_consistent_at_capture=audit.branch_graph_consistent,
        frozen_file_list_coverage_complete=audit.complete_changed_file_coverage,
        audit_blockers=tuple(dict.fromkeys((
            "Frozen PR head file lists can drift after capture",
            "Full source/diff review and prospective three-way combined tree CI absent",
            "Owner branch ruleset, human review and independent security review unverified",
            *audit.blockers,
        ))),
    )

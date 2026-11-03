"""Stage46: deterministic, read-only GitHub PR dependency audit.

Input is an operator-exported *snapshot*, not live authenticated GitHub state.
No network, git writes, merges, branch policy modification, order routing,
market data loading, or trading actions exist in this module.
"""
from __future__ import annotations

import heapq
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class StackAuditError(ValueError):
    """Malformed/untrusted PR snapshot; no merge advice can be authorized."""


@dataclass(frozen=True, slots=True)
class OverlapCandidate:
    pr_a: int
    pr_b: int
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PRStackAudit:
    repository: str
    captured_at_utc: str
    main_sha: str
    main_protected_reported: bool
    pr_count: int
    root_pr_numbers: tuple[int, ...]
    topological_pr_numbers: tuple[int, ...]
    branch_graph_consistent: bool
    complete_changed_file_coverage: bool
    overlap_candidates: tuple[OverlapCandidate, ...]
    blockers: tuple[str, ...]
    # Always false. GitHub state may change after this offline snapshot.
    independently_verified_current_github_state: bool = False
    independently_verified_branch_protection: bool = False
    three_way_merge_conflicts_ruled_out: bool = False
    merged_commit_ci_verified: bool = False
    owner_merge_approval_verified: bool = False
    all_relevant_prs_merge_ready: bool = False
    merges_performed: int = 0
    live_orders_transmitted: int = 0
    production_ready: bool = False


def _require_sha(value: object, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{40}", value) is None:
        raise StackAuditError(f"{name} must be exactly 40 hexadecimal characters")
    return value.lower()


def _branch(value: object, name: str) -> str:
    if (not isinstance(value, str) or len(value) > 200
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", value) is None
            or ".." in value or "//" in value or value.endswith(("/", "."))):
        raise StackAuditError(f"{name} must be a safe nonempty branch ref")
    return value


def _path(value: object) -> str:
    if (not isinstance(value, str) or not value or len(value) > 512
            or value.startswith("/") or "\\" in value or "\x00" in value
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise StackAuditError("Changed-file entry must be a safe relative repository path")
    return value


def _snapshot_time(value: object) -> str:
    if not isinstance(value, str) or len(value) > 50:
        raise StackAuditError("captured_at_utc must be an ISO UTC timestamp")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
            raise ValueError("non UTC")
    except ValueError as exc:
        raise StackAuditError("captured_at_utc must be an ISO UTC timestamp") from exc
    return value


def inspect_pr_dependency_snapshot(snapshot: dict[str, Any]) -> PRStackAudit:
    """Audit a bounded *single moment* PR graph; never declare merge-safe.

    'changed_paths_complete' is operator-reported. Shared files across
    *independent* branch lineages are merely overlap REVIEW CANDIDATES:
    they are not proof of a Git merge conflict. Missing file lists never
    establish non-overlap or successful integration.
    """
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise StackAuditError("Versioned PR snapshot object required")
    repo = snapshot.get("repository")
    if (not isinstance(repo, str)
            or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) is None
            or len(repo) > 200):
        raise StackAuditError("Valid repository owner/name required")
    captured = _snapshot_time(snapshot.get("captured_at_utc"))
    if snapshot.get("main_ref") != "main":
        raise StackAuditError("Explicit main branch required")
    main_sha = _require_sha(snapshot.get("main_sha"), "main_sha")
    protected = snapshot.get("main_protected")
    if not isinstance(protected, bool):
        raise StackAuditError("main_protected must be explicit boolean, not an authority proof")
    entries = snapshot.get("pull_requests")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise StackAuditError("1..100 PR objects required (export pages separately if larger)")

    nodes: dict[int, dict[str, Any]] = {}
    branches: dict[str, int] = {}
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise StackAuditError(f"PR index {index}: object required")
        n = raw.get("number")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 1_000_000:
            raise StackAuditError(f"PR index {index}: invalid PR number")
        if n in nodes:
            raise StackAuditError(f"Duplicate PR number #{n}")
        head = _branch(raw.get("head_ref"), f"PR #{n} head_ref")
        base = _branch(raw.get("base_ref"), f"PR #{n} base_ref")
        if head == "main" or head in branches or head == base:
            raise StackAuditError(f"PR #{n}: duplicate/cyclic/self branch head")
        head_sha = _require_sha(raw.get("head_sha"), f"PR #{n} head_sha")
        base_sha = _require_sha(raw.get("base_sha"), f"PR #{n} base_sha")
        state, draft, merged = raw.get("state"), raw.get("draft"), raw.get("merged")
        if state not in ("open", "closed") or not isinstance(draft, bool) or not isinstance(merged, bool):
            raise StackAuditError(f"PR #{n}: missing explicit state/draft/merged")
        complete = raw.get("changed_paths_complete")
        if not isinstance(complete, bool):
            raise StackAuditError(f"PR #{n}: changed_paths_complete must be boolean")
        paths = raw.get("changed_paths")
        if not isinstance(paths, list) or len(paths) > 1000:
            raise StackAuditError(f"PR #{n}: changed_paths must be bounded list")
        names = tuple(_path(v) for v in paths)
        if len(names) != len(set(names)) or (not complete and names):
            raise StackAuditError(f"PR #{n}: duplicated/partial ambiguous file-list evidence")
        branches[head] = n
        nodes[n] = dict(
            head=head, base=base, head_sha=head_sha, base_sha=base_sha,
            state=state, draft=draft, merged=merged,
            complete=complete, paths=names,
        )

    issues: list[str] = []
    indegree = {number: 0 for number in nodes}
    children: dict[int, list[int]] = {number: [] for number in nodes}
    parent: dict[int, int | None] = {}
    roots: list[int] = []
    if not protected:
        issues.append("main branch protection reported disabled; verify settings independently")
    for n in sorted(nodes):
        node = nodes[n]
        if node["state"] != "open" or not node["draft"] or node["merged"]:
            issues.append(f"PR #{n} is not an open unmerged draft")
        base = node["base"]
        if base == "main":
            roots.append(n)
            parent[n] = None
            if node["base_sha"] != main_sha:
                issues.append(f"PR #{n}: main base SHA drifted within exported snapshot")
        elif base not in branches:
            parent[n] = None
            issues.append(f"PR #{n}: base branch missing from exported PR graph")
        else:
            p = branches[base]
            parent[n] = p
            children[p].append(n)
            indegree[n] += 1
            if node["base_sha"] != nodes[p]["head_sha"]:
                issues.append(f"PR #{n}: parent branch SHA mismatch (stale base or snapshot)")
    for ch in children.values():
        ch.sort()
    ready = [n for n, d in indegree.items() if d == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for child in children[n]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(nodes):
        issues.append("PR parent cycle detected; topological merge plan unavailable")
    if len(roots) > 1:
        issues.append(f"{len(roots)} independent main-rooted PR lineages need manual reconciliation")
    if not roots:
        issues.append("No verified main-rooted integration chain")

    def is_ancestor(a: int, b: int) -> bool:
        current = parent.get(b)
        seen: set[int] = set()
        while current is not None and current not in seen:
            if current == a:
                return True
            seen.add(current)
            current = parent.get(current)
        return False

    overlaps: list[OverlapCandidate] = []
    keys = sorted(nodes)
    for i, a in enumerate(keys):
        node_a = nodes[a]
        if not node_a["complete"]:
            continue
        for b in keys[i+1:]:
            node_b = nodes[b]
            if not node_b["complete"] or is_ancestor(a, b) or is_ancestor(b, a):
                continue
            shared = tuple(sorted(set(node_a["paths"]) & set(node_b["paths"])))
            if shared:
                overlaps.append(OverlapCandidate(a, b, shared[:30]))
    if overlaps:
        issues.append(f"{len(overlaps)} cross-lineage file-overlap candidates need human diff review")
    complete = all(node["complete"] for node in nodes.values())
    if not complete:
        issues.append("Not all PRs have complete changed-file evidence; absence of conflicts unproven")
    issues.extend((
        "Combined post-merge CI has not been verified",
        "Owner approval and independent branch policy checks are required",
    ))
    # No automatic merge readiness based on a local static export.
    return PRStackAudit(
        repository=repo, captured_at_utc=captured, main_sha=main_sha,
        main_protected_reported=protected, pr_count=len(nodes),
        root_pr_numbers=tuple(sorted(roots)),
        topological_pr_numbers=tuple(order),
        branch_graph_consistent=(len(order) == len(nodes) and not any(
            "missing from exported" in s or "SHA mismatch" in s or "drifted" in s
            for s in issues
        )),
        complete_changed_file_coverage=complete,
        overlap_candidates=tuple(overlaps),
        blockers=tuple(dict.fromkeys(issues)),
    )

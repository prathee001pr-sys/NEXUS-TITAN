"""Stage 218: deterministic read-only stage-progress projection, not a web server.

Every status is UNVERIFIED: untrusted labels are never escalated to VERIFIED.
Deployment, authentication and UI route checks are explicitly out of scope.
"""
from __future__ import annotations
from dataclasses import dataclass

from .stage216_progress_evidence import canonical_digest, sha_ok
from .stage217_progress_journal import ProgressEvent, audit_progress_journal, _STATES


@dataclass(frozen=True, slots=True)
class StageProgressRow:
    stage_number: int
    state: str
    evidence_sha256: str
    independently_verified: bool = False


@dataclass(frozen=True, slots=True)
class DashboardProjection:
    stage_limit: int
    rows: tuple[StageProgressRow, ...]
    journal_head_sha256: str
    projection_sha256: str
    verified_count: int = 0
    owner_only_auth_verified: bool = False
    live_trading_authorized: bool = False


def projection_digest(stage_limit: int, rows: tuple[StageProgressRow, ...], head: str) -> str:
    return canonical_digest({'stage_limit': stage_limit, 'journal_head': head,
        'rows': [{'stage': row.stage_number, 'state': row.state,
                  'evidence_sha256': row.evidence_sha256,
                  'independently_verified': False} for row in rows],
        'scope': 'read_only_offline_progress_unverified'})


def project_offline_progress(events: tuple[ProgressEvent, ...], *, stage_limit: int = 220) -> DashboardProjection:
    if type(stage_limit) is not int or not 1 <= stage_limit <= 220:
        raise ValueError('stage_limit out of range')
    receipt = audit_progress_journal(events)
    if not receipt.accepted or any(e.stage_number > stage_limit for e in events):
        raise ValueError('journal invalid or stage above requested limit')
    latest: dict[int, ProgressEvent] = {}
    for event in events:
        latest[event.stage_number] = event
    rows = tuple(StageProgressRow(n, latest[n].state if n in latest else 'UNVERIFIED',
                                  latest[n].evidence_sha256 if n in latest else '')
                 for n in range(1, stage_limit + 1))
    return DashboardProjection(stage_limit, rows, receipt.head_sha256,
                               projection_digest(stage_limit, rows, receipt.head_sha256))


def audit_dashboard_projection(projection: object) -> bool:
    if type(projection) is not DashboardProjection or type(projection.stage_limit) is not int or not 1 <= projection.stage_limit <= 220:
        return False
    if (type(projection.rows) is not tuple or len(projection.rows) != projection.stage_limit
        or not sha_ok(projection.journal_head_sha256) or not sha_ok(projection.projection_sha256)
        or type(projection.verified_count) is not int or projection.verified_count != 0
        or projection.owner_only_auth_verified is not False
        or projection.live_trading_authorized is not False):
        return False
    for i, row in enumerate(projection.rows, 1):
        if (type(row) is not StageProgressRow or type(row.stage_number) is not int or row.stage_number != i
            or row.independently_verified is not False or type(row.state) is not str
            or row.state not in ('UNVERIFIED',) + _STATES
            or not (row.evidence_sha256 == '' if row.state == 'UNVERIFIED' else sha_ok(row.evidence_sha256))):
            return False
    return projection.projection_sha256 == projection_digest(projection.stage_limit,
                                                                projection.rows, projection.journal_head_sha256)

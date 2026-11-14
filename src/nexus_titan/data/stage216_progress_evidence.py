"""Stage 216: strictly bounded, caller-submitted stage-progress evidence intake.

A SHA or claimed GitHub CI success is NEVER proof of GitHub origin or external
verification. This module must not mark any stage independently verified.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_GIT_OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
_BRANCH = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_./-]{0,149}\Z')
_REPO = 'prathee001pr-sys/NEXUS-TITAN'


def canonical_digest(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def sha_ok(x: object) -> bool:
    return type(x) is str and bool(_SHA.fullmatch(x))


@dataclass(frozen=True, slots=True)
class StageProgressEvidence:
    stage_number: int
    repository: str
    branch: str
    commit_oid: str
    test_report_sha256: str
    test_count_reported: int
    github_ci_reported: str
    secret_scan_reported: str
    linked_research_evidence_sha256: str


@dataclass(frozen=True, slots=True)
class StageEvidenceIntakeReceipt:
    accepted_for_offline_progress_tracking: bool
    stage_number: int | None
    evidence_sha256: str
    blockers: tuple[str, ...]
    github_source_independently_verified: bool = False
    tests_independently_verified: bool = False
    production_or_live_authorized: bool = False


def audit_stage_progress_evidence(record: object) -> StageEvidenceIntakeReceipt:
    if type(record) is not StageProgressEvidence:
        return StageEvidenceIntakeReceipt(False, None, '', ('typed progress evidence required',))
    checks = {
        'bounded stage': type(record.stage_number) is int and 1 <= record.stage_number <= 220,
        'expected repository label': type(record.repository) is str and record.repository == _REPO,
        'safe feature branch label': type(record.branch) is str and bool(_BRANCH.fullmatch(record.branch))
            and record.branch.startswith('feature/') and '..' not in record.branch
            and not record.branch.endswith('/') and '//' not in record.branch,
        'git commit oid label': type(record.commit_oid) is str and bool(_GIT_OID.fullmatch(record.commit_oid)),
        'test report sha': sha_ok(record.test_report_sha256),
        'bounded test count': type(record.test_count_reported) is int and 1 <= record.test_count_reported <= 100000,
        'ci label': type(record.github_ci_reported) is str and record.github_ci_reported in ('success', 'pending', 'failed'),
        'secret scan label': type(record.secret_scan_reported) is str and record.secret_scan_reported in ('success', 'pending', 'failed'),
        'linked synthetic research evidence': sha_ok(record.linked_research_evidence_sha256),
    }
    blockers = tuple(name for name, ok in checks.items() if not ok)
    digest = canonical_digest({name: getattr(record, name) for name in record.__dataclass_fields__}) if not blockers else ''
    return StageEvidenceIntakeReceipt(not blockers, record.stage_number if checks['bounded stage'] else None, digest, blockers)

"""Stage 224: fail-closed final *offline* evidence / recovery review.

This is an additive offline audit, NOT a CI provider, crash fix, independent
identity verifier, production acceptance, or trade execution permission gate.
Caller-submitted test counts/CI labels are never treated as authenticated proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1, sha256
import json
from pathlib import Path
from typing import Any

from .stage223_rust_readiness import review_rust_readiness

_STAGE217_BLOB = '8c0138057fec27b21650cf45c944474445da456f'
_STAGE222_BLOB = '6cb2b079e4efe05715f833ee19fb66a58da05f96'
_STAGE223_BLOB = 'd926ee9e18515fc671ffbeed85c8859dd9209cf0'

_REQUIRED_EVIDENCE_KEYS = frozenset({
    'schema', 'run_scope', 'local_pytest_passed', 'local_pytest_failed',
    'local_pytest_skipped', 'full_suite_run_completed',
    'recovery_runs', 'recovery_unexpected', 'recovery_root_cause_proven',
    'authoritative_ci_proof_supplied', 'external_market_data_verified',
    'broker_orders_sent', 'live_trading_enabled', 'risk_controls_changed',
})

_UNRESOLVED = (
    'Stage 121/123 intermittent recovery timeout root cause not independently proven',
    'Historical F&O vendor/source and real-market execution not independently verified',
    'Local test counts and CI labels are not authenticated GitHub checks',
    'Rust replacement not justified by representative production-path evidence',
    'Live trading, autonomous execution and production promotion require separate explicit authorization',
)


@dataclass(frozen=True, slots=True)
class Stage224FinalAuditReceipt:
    accepted_for_offline_evidence_record: bool
    stage223_consistency_verified_locally: bool
    parent_sources_pinned_locally: bool
    local_evidence_digest_sha256: str
    blockers: tuple[str, ...]
    full_regression_verified: bool = False
    independent_recovery_root_cause_verified: bool = False
    authoritative_github_ci_verified: bool = False
    external_market_data_verified: bool = False
    rust_integration_justified: bool = False
    production_replacement_authorized: bool = False
    risk_controls_change_authorized: bool = False
    broker_orders_authorized: bool = False
    autonomous_execution_authorized: bool = False
    live_trading_authorized: bool = False


def _blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def _pinned_sources(root: Path) -> bool:
    # Source pinning is only a local byte-integrity check, not GitHub provenance.
    expected = {
        'data/stage217_progress_journal.py': _STAGE217_BLOB,
        'diagnostics/stage222_journal_candidate.py': _STAGE222_BLOB,
        'diagnostics/stage223_rust_readiness.py': _STAGE223_BLOB,
    }
    try:
        src = root / 'src' / 'nexus_titan'
        return all(_blob_sha(src / name) == digest for name, digest in expected.items())
    except (OSError, ValueError):
        return False


def _nonneg_int(x: object, maximum: int) -> bool:
    return type(x) is int and 0 <= x <= maximum


def _valid_evidence(data: object) -> tuple[bool, tuple[str, ...]]:
    if type(data) is not dict or frozenset(data) != _REQUIRED_EVIDENCE_KEYS:
        return False, ('Invalid bounded local test/recovery evidence schema',)
    issues: list[str] = []
    if data['schema'] != 'titan.stage224.local_audit_evidence.v1':
        issues.append('Invalid evidence version')
    if data['run_scope'] not in ('TARGETED', 'BOUNDED_FULL', 'NOT_RUN') or type(data['run_scope']) is not str:
        issues.append('Invalid run scope')
    for key in ('local_pytest_passed', 'local_pytest_failed', 'local_pytest_skipped'):
        if not _nonneg_int(data[key], 100_000):
            issues.append('Invalid local pytest count: ' + key)
    if not _nonneg_int(data['recovery_runs'], 100) or not _nonneg_int(data['recovery_unexpected'], 100):
        issues.append('Invalid recovery counts')
    elif data['recovery_unexpected'] > data['recovery_runs']:
        issues.append('Unexpected recoveries exceed total')
    if data['full_suite_run_completed'] not in (True, False) or type(data['full_suite_run_completed']) is not bool:
        issues.append('Malformed full-suite flag')
    if data['run_scope'] == 'NOT_RUN' and (
        data['local_pytest_passed'] != 0 or data['local_pytest_failed'] != 0
        or data['local_pytest_skipped'] != 0 or data['full_suite_run_completed'] is True
    ):
        issues.append('Run-scope/count contradiction')
    if data['run_scope'] == 'TARGETED' and data['full_suite_run_completed'] is True:
        issues.append('Targeted run cannot certify full suite')
    if data['run_scope'] == 'BOUNDED_FULL' and data['full_suite_run_completed'] is not True:
        issues.append('Full-suite status contradicted by scope')
    # These are not accepted as independently verifiable claims via local JSON.
    for key in ('recovery_root_cause_proven', 'authoritative_ci_proof_supplied',
                'external_market_data_verified', 'live_trading_enabled', 'risk_controls_changed'):
        if data[key] is not False:
            issues.append('Unsafe, unsupported or malformed evidence assertion: ' + key)
    if data['broker_orders_sent'] != 0 or type(data['broker_orders_sent']) is not int:
        issues.append('Trading operations claimed during offline audit')
    return not issues, tuple(issues)


def evaluate_stage224_final_audit(
    stage222_report: object, local_evidence: object, *,
    project_root: Path | None = None,
) -> Stage224FinalAuditReceipt:
    """Authenticate internal consistency only; always NO-GO for production.

    The caller provides no cryptographically authenticated GitHub/market proof,
    so no local report can mark CI, market data or full recovery independently
    verified. This gate cannot replace the runtime's independent risk veto.
    """
    root = project_root if project_root is not None else Path(__file__).resolve().parents[3]
    pinned = _pinned_sources(root)
    review = review_rust_readiness(stage222_report)
    consistent = review.accepted_for_offline_experiment_review is True
    valid, issues = _valid_evidence(local_evidence)
    blockers = list(issues)
    if not pinned:
        blockers.append('Local parent source blob fingerprint mismatch')
    if not consistent:
        blockers.append('Stage223 independent offline evidence review failed')
    if valid:
        if local_evidence['local_pytest_failed']:
            blockers.append('Observed local regression failures')
        if local_evidence['run_scope'] != 'BOUNDED_FULL' or not local_evidence['full_suite_run_completed']:
            blockers.append('Full repository regression not completed')
        if local_evidence['recovery_runs'] == 0:
            blockers.append('No fresh recovery diagnostics supplied')
        if local_evidence['recovery_unexpected']:
            blockers.append('Unexpected recovery observations present')
    digest = ''
    if valid and pinned and consistent:
        # Digest of untrusted local observations, not an external attestation.
        digest = sha256(json.dumps(local_evidence, sort_keys=True,
                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    return Stage224FinalAuditReceipt(
        accepted_for_offline_evidence_record=bool(valid and pinned and consistent),
        stage223_consistency_verified_locally=consistent,
        parent_sources_pinned_locally=pinned,
        local_evidence_digest_sha256=digest,
        blockers=tuple(dict.fromkeys(blockers + list(_UNRESOLVED))),
    )


def safe_stage224_evidence_template() -> dict[str, Any]:
    """No invented success counts. Script may fill this with observed results."""
    return {
        'schema': 'titan.stage224.local_audit_evidence.v1',
        'run_scope': 'NOT_RUN',
        'local_pytest_passed': 0,
        'local_pytest_failed': 0,
        'local_pytest_skipped': 0,
        'full_suite_run_completed': False,
        'recovery_runs': 0,
        'recovery_unexpected': 0,
        'recovery_root_cause_proven': False,
        'authoritative_ci_proof_supplied': False,
        'external_market_data_verified': False,
        'broker_orders_sent': 0,
        'live_trading_enabled': False,
        'risk_controls_changed': False,
    }

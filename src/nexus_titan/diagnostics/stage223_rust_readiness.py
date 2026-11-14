"""Stage 223: fail-closed, *offline* review of the Stage 222 Python A/B report.

A self-reported benchmark (even with internally valid hashes) is not independent
proof of hardware, data provenance, risk safety, or a need for a Rust port. This
module never authorizes production modification, Rust integration, or trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1, sha256
import json
import math
from pathlib import Path
import statistics

from nexus_titan.data.stage217_progress_journal import audit_progress_journal, make_progress_event
from nexus_titan.diagnostics.stage222_journal_candidate import audit_progress_journal_candidate

# Immutable, independently reviewed GitHub *blob* IDs for the unmodified parent.
_STAGE217_BLOB = '8c0138057fec27b21650cf45c944474445da456f'
_STAGE222_BLOB = '6cb2b079e4efe05715f833ee19fb66a58da05f96'
_SIZES = (30, 300, 1000)
_GATING_REASONS = (
    'No independent verification of representative production workloads or latency requirement',
    'Stage 217 is an offline progress journal, not a live execution hot path',
    'Local Python improvement makes a Rust rewrite unnecessary on current evidence',
    'Intermittent Stage 121/123 recovery timing remains unresolved',
    'No explicit approval to replace production code or introduce Rust integration',
)


@dataclass(frozen=True, slots=True)
class RustReadinessReviewReceipt:
    accepted_for_offline_experiment_review: bool
    report_sha256: str
    observed_speedup_by_event_count: tuple[tuple[int, float], ...]
    blockers: tuple[str, ...]
    rust_integration_justified: bool = False
    production_replacement_authorized: bool = False
    live_trading_authorized: bool = False
    independent_market_data_verified: bool = False
    independent_recovery_verified: bool = False


def _git_blob_hash(path: Path) -> str:
    raw = path.read_bytes()
    return sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def _fixed_journal(count: int) -> tuple:
    # Independent reconstruction of the same fixed Stage 222 research fixture.
    out = []
    prior = '0' * 64
    states = ('SUBMITTED_UNVERIFIED', 'LOCAL_TEST_REPORTED_UNVERIFIED', 'CI_REPORTED_UNVERIFIED')
    for i in range(count):
        evidence = sha256(f'220-experimental-fixed-{i}'.encode('ascii')).hexdigest()
        event = make_progress_event(
            sequence=i + 1, stage_number=216 + (i % 5), state=states[i % 3],
            evidence_sha256=evidence, previous_event_sha256=prior,
        )
        out.append(event)
        prior = event.event_sha256
    return tuple(out)


def _positive_int(x: object, *, limit: int) -> bool:
    return type(x) is int and 1 <= x <= limit


def _valid_row(row: object, *, count: int, samples: int) -> tuple[float, str, str] | None:
    if type(row) is not dict or set(row) != {
        'case', 'event_count', 'fixture_digest', 'output_digest',
        'baseline_median_ns', 'candidate_median_ns', 'observed_speedup_ratio',
        'baseline_samples_ns', 'candidate_samples_ns', 'equivalent_on_fixed_fixture',
    }:
        return None
    if (row['case'] != f'offline_journal_{count}' or type(row['event_count']) is not int
            or row['event_count'] != count or row['equivalent_on_fixed_fixture'] is not True):
        return None
    observed = row['observed_speedup_ratio']
    if type(observed) not in (float, int) or not math.isfinite(observed) or observed <= 0:
        return None
    medians = []
    for prefix in ('baseline', 'candidate'):
        values = row[f'{prefix}_samples_ns']
        if (type(values) is not list or len(values) != samples
                or not all(_positive_int(v, limit=100_000_000_000) for v in values)):
            return None
        median = row[f'{prefix}_median_ns']
        if not _positive_int(median, limit=100_000_000_000):
            return None
        if median != int(statistics.median(values)):
            return None
        medians.append(median)
    expected_ratio = round(medians[0] / medians[1], 3)
    if observed != expected_ratio:
        return None
    journal = _fixed_journal(count)
    baseline, candidate = audit_progress_journal(journal), audit_progress_journal_candidate(journal)
    if (baseline != candidate or baseline.accepted is not True
            or baseline.authoritative_git_verification is not False
            or baseline.live_trading_authorized is not False):
        return None
    fixture_digest = sha256('|'.join(event.event_sha256 for event in journal).encode('ascii')).hexdigest()
    if (type(row['fixture_digest']) is not str or row['fixture_digest'] != fixture_digest
            or type(row['output_digest']) is not str or row['output_digest'] != baseline.head_sha256):
        return None
    return (float(expected_ratio), fixture_digest, baseline.head_sha256)


def review_rust_readiness(report: object) -> RustReadinessReviewReceipt:
    """Validate self-reported offline evidence, then keep integration fail-closed.

    Accepted means *only* that current local report is internally consistent and
    deterministic fixtures agree. It never means authorized deployment or Rust.
    """
    blockers = []
    ratios: list[tuple[int, float]] = []
    if type(report) is not dict or set(report) != {
        'schema', 'implementation', 'python_version', 'system', 'samples',
        'iterations_per_sample', 'stage217_production_modified',
        'production_replacement_authorized', 'rust_rewrite_authorized',
        'real_market_latency_verified', 'live_trading_authorized', 'note', 'results',
    }:
        blockers.append('Expected bounded Stage 222 report schema')
    else:
        if (report['schema'] != 'titan.stage222.offline_python_candidate.v1'
                or report['implementation'] != 'CPython'
                or type(report['python_version']) is not str
                or not 1 <= len(report['python_version']) <= 30
                or type(report['system']) is not str
                or not 1 <= len(report['system']) <= 80
                or type(report['note']) is not str or not 1 <= len(report['note']) <= 500
                or not _positive_int(report['samples'], limit=31)
                or report['samples'] < 3
                or not _positive_int(report['iterations_per_sample'], limit=100)):
            blockers.append('Invalid bounded benchmark metadata')
        for flag in ('stage217_production_modified', 'production_replacement_authorized',
                     'rust_rewrite_authorized', 'real_market_latency_verified',
                     'live_trading_authorized'):
            if report[flag] is not False:
                blockers.append(f'Unsafe evidence claim: {flag}')
        rows = report['results']
        if type(rows) is not list or len(rows) != len(_SIZES):
            blockers.append('Expected exactly three fixed workloads')
        elif not any(b == 'Invalid bounded benchmark metadata' for b in blockers):
            for count, row in zip(_SIZES, rows):
                result = _valid_row(row, count=count, samples=report['samples'])
                if result is None:
                    blockers.append(f'Invalid or non-reproducible {count}-event workload evidence')
                else:
                    ratios.append((count, result[0]))
        root = Path(__file__).resolve().parents[1]
        for relative, expected in (
            ('data/stage217_progress_journal.py', _STAGE217_BLOB),
            ('diagnostics/stage222_journal_candidate.py', _STAGE222_BLOB),
        ):
            try:
                if _git_blob_hash(root / relative) != expected:
                    blockers.append(f'Parent source changed: {relative}')
            except OSError:
                blockers.append(f'Parent source unreadable: {relative}')
    if blockers:
        return RustReadinessReviewReceipt(False, '', (), tuple(dict.fromkeys(blockers)) + _GATING_REASONS)
    # Digest authenticates local bytes *only* if held independently; no signatures.
    digest = sha256(json.dumps(report, sort_keys=True, separators=(',', ':'),
                               ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()
    return RustReadinessReviewReceipt(True, digest, tuple(ratios), _GATING_REASONS)

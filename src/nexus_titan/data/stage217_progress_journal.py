"""Stage 217: bounded, hash-chained offline progress journal; NOT a trusted audit log.

Hash links detect accidental/local edits when the expected head digest is held
separately. They are not digital signatures or authentic GitHub attestations.
"""
from __future__ import annotations
from dataclasses import dataclass

from .stage216_progress_evidence import canonical_digest, sha_ok

_STATES = ('SUBMITTED_UNVERIFIED', 'LOCAL_TEST_REPORTED_UNVERIFIED', 'CI_REPORTED_UNVERIFIED')
_ZERO = '0' * 64


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    sequence: int
    stage_number: int
    state: str
    evidence_sha256: str
    previous_event_sha256: str
    event_sha256: str


@dataclass(frozen=True, slots=True)
class ProgressJournalReceipt:
    accepted: bool
    event_count: int
    head_sha256: str
    blockers: tuple[str, ...]
    authoritative_git_verification: bool = False
    live_trading_authorized: bool = False


def make_progress_event(*, sequence: int, stage_number: int, state: str,
                        evidence_sha256: str, previous_event_sha256: str) -> ProgressEvent:
    values = (sequence, stage_number, state, evidence_sha256, previous_event_sha256)
    if (type(sequence) is not int or not 1 <= sequence <= 1000 or
        type(stage_number) is not int or not 1 <= stage_number <= 220 or
        type(state) is not str or state not in _STATES or
        not sha_ok(evidence_sha256) or not sha_ok(previous_event_sha256)):
        raise ValueError('invalid offline progress event fields')
    body = dict(zip(('sequence', 'stage_number', 'state', 'evidence_sha256', 'previous_event_sha256'), values))
    return ProgressEvent(*values, canonical_digest(body))


def audit_progress_journal(events: object) -> ProgressJournalReceipt:
    if type(events) is not tuple or not 1 <= len(events) <= 1000:
        return ProgressJournalReceipt(False, 0, '', ('bounded event tuple required',))
    prior = _ZERO
    for position, item in enumerate(events, 1):
        if type(item) is not ProgressEvent or item.sequence != position or item.previous_event_sha256 != prior:
            return ProgressJournalReceipt(False, position - 1, '', (f'broken journal sequence/link at event {position}',))
        try:
            rebuilt = make_progress_event(sequence=item.sequence, stage_number=item.stage_number,
                state=item.state, evidence_sha256=item.evidence_sha256,
                previous_event_sha256=item.previous_event_sha256)
        except (ValueError, TypeError):
            return ProgressJournalReceipt(False, position - 1, '', (f'invalid event fields at event {position}',))
        if item != rebuilt:
            return ProgressJournalReceipt(False, position - 1, '', (f'journal digest mismatch at event {position}',))
        prior = item.event_sha256
    return ProgressJournalReceipt(True, len(events), prior, ())

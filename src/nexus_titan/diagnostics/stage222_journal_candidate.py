"""Stage 222: EXPERIMENTAL offline-only candidate for Stage 217 journal hashing.

This is a separate performance experiment, NOT the production implementation.
No auto-promotion, broker access, risk override, deployment, or Rust authorization.
The accepted-event canonical representation is restricted to validated ASCII
hex digests, bounded integers, and an allowlisted state; it must match the
Stage 216 canonical JSON digest exactly. Never accept unvalidated strings.
"""
from __future__ import annotations

import hashlib

from nexus_titan.data.stage217_progress_journal import (
    ProgressEvent, ProgressJournalReceipt,
)
from nexus_titan.data.stage216_progress_evidence import sha_ok

_ALLOWED_STATES = frozenset((
    'SUBMITTED_UNVERIFIED', 'LOCAL_TEST_REPORTED_UNVERIFIED', 'CI_REPORTED_UNVERIFIED',
))
_ZERO = '0' * 64


def _validated_canonical_event_digest(event: ProgressEvent) -> str:
    """No arbitrary JSON input: validate *all* fields before ASCII construction.

    Keys are in json.dumps(sort_keys=True, separators=(',', ':')) order.
    """
    seq, stage, state = event.sequence, event.stage_number, event.state
    evidence, previous = event.evidence_sha256, event.previous_event_sha256
    if (type(seq) is not int or not 1 <= seq <= 1000
            or type(stage) is not int or not 1 <= stage <= 220
            or type(state) is not str or state not in _ALLOWED_STATES
            or not sha_ok(evidence) or not sha_ok(previous)):
        raise ValueError('invalid offline progress event fields')
    raw = (f'{{"evidence_sha256":"{evidence}",'
           f'"previous_event_sha256":"{previous}",'
           f'"sequence":{seq},"stage_number":{stage},"state":"{state}"}}')
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


def audit_progress_journal_candidate(events: object) -> ProgressJournalReceipt:
    """Drop-in *diagnostic* receipt with Stage 217-equivalent bounded semantics.

    This candidate must NOT be imported by trading services or replace Stage 217
    until independent review; it does not establish authenticity of inputs.
    """
    if type(events) is not tuple or not 1 <= len(events) <= 1000:
        return ProgressJournalReceipt(False, 0, '', ('bounded event tuple required',))
    prior = _ZERO
    for position, item in enumerate(events, 1):
        if (type(item) is not ProgressEvent or item.sequence != position
                or item.previous_event_sha256 != prior):
            return ProgressJournalReceipt(False, position - 1, '',
                (f'broken journal sequence/link at event {position}',))
        try:
            digest = _validated_canonical_event_digest(item)
            rebuilt = ProgressEvent(item.sequence, item.stage_number, item.state,
                                    item.evidence_sha256, item.previous_event_sha256, digest)
        except (ValueError, TypeError):
            return ProgressJournalReceipt(False, position - 1, '',
                (f'invalid event fields at event {position}',))
        if item != rebuilt:
            return ProgressJournalReceipt(False, position - 1, '',
                (f'journal digest mismatch at event {position}',))
        prior = item.event_sha256
    return ProgressJournalReceipt(True, len(events), prior, ())

"""Cryptographic integrity and freshness checks for specialist evidence payloads.

A valid digest proves that a payload matches the supplied bytes; it does not
prove that the source is truthful, licensed, independent, or exchange-authentic.
Those claims still require external verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    evidence_id: str
    source_id: str
    payload: dict[str, Any]
    sha256: str
    observed_at: str

    @classmethod
    def build(cls, *, evidence_id: str, source_id: str,
              payload: dict[str, Any], observed_at: str) -> "EvidenceEnvelope":
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
        return cls(evidence_id=evidence_id, source_id=source_id, payload=payload,
                   sha256=hashlib.sha256(canonical).hexdigest(), observed_at=observed_at)


def verify_evidence_envelope(envelope: EvidenceEnvelope, *, now: datetime | None = None,
                             max_age_seconds: int = 300) -> tuple[bool, tuple[str, ...]]:
    """Check identity fields, canonical digest and freshness; never authenticates source."""
    issues: list[str] = []
    if not isinstance(envelope.evidence_id, str) or not envelope.evidence_id.strip():
        issues.append("evidence_id_missing")
    if not isinstance(envelope.source_id, str) or not envelope.source_id.strip():
        issues.append("source_id_missing")
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds < 0:
        raise ValueError("max_age_seconds must be a non-negative integer")
    try:
        observed = datetime.fromisoformat(envelope.observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError
        age = (current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
        if age < -30:
            issues.append("evidence_timestamp_in_future")
        elif age > max_age_seconds:
            issues.append("evidence_stale")
    except (ValueError, AttributeError, TypeError):
        issues.append("evidence_timestamp_invalid")
    try:
        canonical = json.dumps(envelope.payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
        actual = hashlib.sha256(canonical).hexdigest()
        if not isinstance(envelope.sha256, str) or not hmac.compare_digest(actual, envelope.sha256.lower()):
            issues.append("evidence_digest_mismatch")
    except (TypeError, ValueError):
        issues.append("evidence_payload_not_canonicalizable")
    return not issues, tuple(issues)

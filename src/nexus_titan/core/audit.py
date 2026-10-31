"""Tamper-evident in-process audit ledger for core actions.

Persistence and external signing are deliberately deferred. This ledger is
append-only through its public API and hash-chains records for integrity checks.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4


GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class AuditRecord:
    record_id: str
    timestamp: str
    actor: str
    action: str
    outcome: str
    details: dict[str, Any]
    previous_hash: str
    record_hash: str


def _canonical_record(record_id: str, timestamp: str, actor: str, action: str,
                      outcome: str, details: dict[str, Any], previous_hash: str) -> str:
    return json.dumps(
        {
            "record_id": record_id,
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "outcome": outcome,
            "details": details,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class AuditLedger:
    """Append-only hash chain. No edit or delete methods are exposed."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def append(self, *, actor: str, action: str, outcome: str,
               details: dict[str, Any] | None = None) -> AuditRecord:
        if not actor.strip() or not action.strip() or not outcome.strip():
            raise ValueError("actor, action, and outcome must not be empty")
        safe_details = dict(details or {})
        # Ensure details can be serialized deterministically before recording.
        json.dumps(safe_details, sort_keys=True, ensure_ascii=False)
        record_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        previous_hash = self._records[-1].record_hash if self._records else GENESIS_HASH
        canonical = _canonical_record(
            record_id, timestamp, actor, action, outcome, safe_details, previous_hash
        )
        record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        record = AuditRecord(
            record_id, timestamp, actor, action, outcome, safe_details,
            previous_hash, record_hash
        )
        self._records.append(record)
        return record

    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def verify(self) -> bool:
        previous_hash = GENESIS_HASH
        for record in self._records:
            if record.previous_hash != previous_hash:
                return False
            canonical = _canonical_record(
                record.record_id, record.timestamp, record.actor, record.action,
                record.outcome, record.details, record.previous_hash
            )
            expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if record.record_hash != expected:
                return False
            previous_hash = record.record_hash
        return True

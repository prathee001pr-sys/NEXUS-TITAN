"""Hash-chained audit ledger with optional durable SQLite persistence."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
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


def _copy_record(record: AuditRecord) -> AuditRecord:
    """Return a detached copy so callers cannot mutate the ledger's stored row."""
    return AuditRecord(
        record_id=record.record_id,
        timestamp=record.timestamp,
        actor=record.actor,
        action=record.action,
        outcome=record.outcome,
        details=json.loads(json.dumps(record.details, sort_keys=True, ensure_ascii=False)),
        previous_hash=record.previous_hash,
        record_hash=record.record_hash,
    )


def _canonical_record(record_id: str, timestamp: str, actor: str, action: str,
                      outcome: str, details: dict[str, Any], previous_hash: str) -> str:
    return json.dumps(
        {"record_id": record_id, "timestamp": timestamp, "actor": actor,
         "action": action, "outcome": outcome, "details": details,
         "previous_hash": previous_hash},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


class AuditLedger:
    """Append-only hash chain; pass db_path to persist records across restarts."""

    def __init__(self, db_path: str | None = None) -> None:
        self._records: list[AuditRecord] = []
        self._connection = sqlite3.connect(db_path) if db_path is not None else None
        if self._connection is not None:
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS audit_records (
                    record_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, outcome TEXT NOT NULL,
                    details TEXT NOT NULL, previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE
                )
            """)
            self._connection.commit()
            rows = self._connection.execute(
                "SELECT record_id, timestamp, actor, action, outcome, details, "
                "previous_hash, record_hash FROM audit_records ORDER BY rowid"
            ).fetchall()
            self._records = [
                AuditRecord(row[0], row[1], row[2], row[3], row[4],
                            json.loads(row[5]), row[6], row[7])
                for row in rows
            ]

    def append(self, *, actor: str, action: str, outcome: str,
               details: dict[str, Any] | None = None) -> AuditRecord:
        if not actor.strip() or not action.strip() or not outcome.strip():
            raise ValueError("actor, action, and outcome must not be empty")
        safe_details = json.loads(json.dumps(details or {}, sort_keys=True, ensure_ascii=False))
        record_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        previous_hash = self._records[-1].record_hash if self._records else GENESIS_HASH
        canonical = _canonical_record(
            record_id, timestamp, actor, action, outcome, safe_details, previous_hash
        )
        record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        record = AuditRecord(record_id, timestamp, actor, action, outcome,
                             safe_details, previous_hash, record_hash)
        if self._connection is not None:
            self._connection.execute(
                "INSERT INTO audit_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (record_id, timestamp, actor, action, outcome,
                 json.dumps(safe_details, sort_keys=True, ensure_ascii=False),
                 previous_hash, record_hash),
            )
            self._connection.commit()
        self._records.append(record)
        return _copy_record(record)

    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(_copy_record(record) for record in self._records)

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

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

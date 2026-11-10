"""TITAN GUARDIAN: isolated *research-only* durable work and recovery ledger.

No process launcher, shell, network, broker route, trading intent or risk mutation.
The existing health/watchdog modules remain authoritative for health decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import secrets
import sqlite3
import time


ALLOWED_KINDS = frozenset({"source_review", "research_evaluation", "advisor_refresh"})
STATES = frozenset({"QUEUED", "RUNNING", "COMPLETED", "QUARANTINED"})


@dataclass(frozen=True, slots=True)
class GuardianJob:
    job_id: str
    kind: str
    fingerprint: str
    state: str
    attempts: int
    checkpoint: int
    lease_until: float | None
    no_live: bool = True


class GuardianJobLedger:
    """Fail-closed, retry-capped checkpoint ledger with lease-token fencing.

    A worker runs *outside this class* and must be separately sandboxed.
    A lease expiry makes a research job re-claimable, never auto-executes it.
    """

    def __init__(self, db_path: str | Path, *, max_attempts: int = 3) -> None:
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be an integer 1..10")
        self.max_attempts = max_attempts
        self.db = sqlite3.connect(str(db_path), timeout=5, isolation_level=None)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA busy_timeout=5000")
            self.db.execute("""CREATE TABLE IF NOT EXISTS guardian_research_jobs (
                job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, fingerprint TEXT NOT NULL,
                state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                checkpoint INTEGER NOT NULL DEFAULT 0, lease_until REAL,
                lease_token TEXT, last_error TEXT,
                CHECK(state IN ('QUEUED','RUNNING','COMPLETED','QUARANTINED'))
            )""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self) -> "GuardianJobLedger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _now(now: float | None) -> float:
        stamp = time.time() if now is None else now
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not 0 <= stamp < 1e20:
            raise ValueError("invalid clock")
        return float(stamp)

    def _one(self, job_id: str) -> GuardianJob:
        row = self.db.execute(
            "SELECT job_id,kind,fingerprint,state,attempts,checkpoint,lease_until "
            "FROM guardian_research_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError("unknown research job")
        return GuardianJob(*row)

    def get(self, job_id: str) -> GuardianJob:
        return self._one(job_id)

    def submit(self, *, job_id: str, kind: str, fingerprint: str) -> GuardianJob:
        if not isinstance(job_id, str) or not 1 <= len(job_id) <= 100 or not all(
                ch.isascii() and (ch.isalnum() or ch in "-_") for ch in job_id):
            raise ValueError("invalid job_id")
        if kind not in ALLOWED_KINDS:
            raise PermissionError("trading, code-execution and unknown job kinds prohibited")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
            raise ValueError("fingerprint must be lowercase SHA256")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT kind,fingerprint FROM guardian_research_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if existing and existing != (kind, fingerprint):
                raise ValueError("job_id collision: incompatible payload")
            if not existing:
                self.db.execute(
                    "INSERT INTO guardian_research_jobs (job_id,kind,fingerprint,state) VALUES (?,?,?,'QUEUED')",
                    (job_id, kind, fingerprint)
                )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self._one(job_id)

    def claim(self, job_id: str, *, lease_seconds: int = 60, now: float | None = None) -> str:
        stamp = self._now(now)
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 3600:
            raise ValueError("invalid lease duration")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT state,attempts,lease_until FROM guardian_research_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError("unknown research job")
            state, attempts, lease_until = row
            if state == "RUNNING" and lease_until is not None and lease_until > stamp:
                raise PermissionError("job lease currently held")
            if state not in {"QUEUED", "RUNNING"} or attempts >= self.max_attempts:
                raise PermissionError("job already completed/quarantined or retry cap exceeded")
            token = secrets.token_hex(24)
            self.db.execute(
                "UPDATE guardian_research_jobs SET state='RUNNING',attempts=?,lease_until=?,lease_token=? "
                "WHERE job_id=?", (attempts + 1, stamp + lease_seconds, token, job_id)
            )
            self.db.execute("COMMIT")
            return token
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _update(self, job_id: str, token: str, *, new_checkpoint: int | None = None,
                finish: bool = False, error: str | None = None, now: float | None = None) -> GuardianJob:
        stamp = self._now(now)
        if not isinstance(token, str) or len(token) != 48:
            raise PermissionError("invalid lease token")
        if new_checkpoint is not None and (isinstance(new_checkpoint, bool) or not isinstance(new_checkpoint, int) or new_checkpoint < 0):
            raise ValueError("checkpoint must be a nonnegative integer")
        if error is not None and (not isinstance(error, str) or not error.strip()):
            raise ValueError("error label required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT state,attempts,checkpoint,lease_until,lease_token FROM guardian_research_jobs WHERE job_id=?",
                (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError("unknown research job")
            state, attempts, checkpoint, lease_until, recorded_token = row
            if state != "RUNNING" or recorded_token != token or lease_until is None or stamp >= lease_until:
                raise PermissionError("stale or unauthorized worker lease")
            if new_checkpoint is not None and new_checkpoint < checkpoint:
                raise ValueError("checkpoint regression prohibited")
            if error is not None:
                next_state = "QUARANTINED" if attempts >= self.max_attempts else "QUEUED"
            elif finish:
                next_state = "COMPLETED"
            else:
                next_state = "RUNNING"
            self.db.execute(
                "UPDATE guardian_research_jobs SET state=?,checkpoint=?,lease_until=?,lease_token=?,last_error=? "
                "WHERE job_id=?",
                (next_state, checkpoint if new_checkpoint is None else new_checkpoint,
                 lease_until if next_state == "RUNNING" else None,
                 token if next_state == "RUNNING" else None,
                 error[:120] if error else None, job_id)
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self._one(job_id)

    def checkpoint(self, job_id: str, token: str, completed_chunks: int, *, now: float | None = None) -> GuardianJob:
        return self._update(job_id, token, new_checkpoint=completed_chunks, now=now)

    def complete(self, job_id: str, token: str, *, now: float | None = None) -> GuardianJob:
        return self._update(job_id, token, finish=True, now=now)

    def fail(self, job_id: str, token: str, *, reason: str, now: float | None = None) -> GuardianJob:
        return self._update(job_id, token, error=reason, now=now)

    def quarantine_expired(self, *, now: float | None = None) -> int:
        """Retire exhausted *research* jobs; never restarts anything."""
        stamp = self._now(now)
        with self.db:
            cursor = self.db.execute(
                "UPDATE guardian_research_jobs SET state='QUARANTINED',lease_until=NULL,lease_token=NULL "
                "WHERE state='RUNNING' AND lease_until<=? AND attempts>=?",
                (stamp, self.max_attempts),
            )
        return cursor.rowcount

    def renew(self, job_id: str, token: str, *, lease_seconds: int = 60,
              now: float | None = None) -> GuardianJob:
        """Extend lease if and only if the current worker still holds it."""
        stamp = self._now(now)
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 3600:
            raise ValueError('invalid lease duration')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute("SELECT lease_token,state,lease_until FROM guardian_research_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None or row[0] != token or row[1] != 'RUNNING' or row[2] <= stamp:
                raise PermissionError('stale or unauthorized lease renewal')
            self.db.execute('UPDATE guardian_research_jobs SET lease_until=? WHERE job_id=?',
                            (stamp + lease_seconds, job_id))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
        return self._one(job_id)

    def inspect_integrity(self) -> bool:
        return self.db.execute("PRAGMA quick_check").fetchone()[0] == "ok"

    def backup_to(self, destination: str | Path) -> None:
        if Path(destination).resolve() == Path(self.db.execute("PRAGMA database_list").fetchone()[2]).resolve():
            raise ValueError("backup destination must differ")
        copy = sqlite3.connect(str(destination))
        try:
            self.db.backup(copy)
        finally:
            copy.close()

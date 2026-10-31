"""Persistent, evidence-based Master Requirements Register."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import sqlite3


class RequirementStatus(StrEnum):
    DESIGNED = "designed"
    BUILT = "built"
    TESTED = "tested"
    VERIFIED = "verified"


_STATUS_ORDER = (
    RequirementStatus.DESIGNED,
    RequirementStatus.BUILT,
    RequirementStatus.TESTED,
    RequirementStatus.VERIFIED,
)


@dataclass(frozen=True, slots=True)
class Requirement:
    requirement_id: str
    title: str
    scope: str
    acceptance_criteria: tuple[str, ...]
    status: RequirementStatus
    evidence: tuple[str, ...]
    updated_at: datetime


class RequirementsRegister:
    """SQLite-backed register with ordered state transitions and evidence."""

    def __init__(self, db_path: str) -> None:
        if not db_path.strip():
            raise ValueError("db_path must not be empty")
        self._connection = sqlite3.connect(db_path)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS requirements (
                requirement_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                scope TEXT NOT NULL,
                acceptance_criteria TEXT NOT NULL,
                status TEXT NOT NULL,
                evidence TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._connection.commit()

    @staticmethod
    def _from_row(row: tuple) -> Requirement:
        return Requirement(
            requirement_id=row[0],
            title=row[1],
            scope=row[2],
            acceptance_criteria=tuple(json.loads(row[3])),
            status=RequirementStatus(row[4]),
            evidence=tuple(json.loads(row[5])),
            updated_at=datetime.fromisoformat(row[6]),
        )

    def register(self, *, requirement_id: str, title: str, scope: str,
                 acceptance_criteria: tuple[str, ...] | list[str]) -> Requirement:
        criteria = tuple(item.strip() for item in acceptance_criteria if item.strip())
        if not requirement_id.strip() or not title.strip() or not scope.strip():
            raise ValueError("requirement_id, title, and scope must not be empty")
        if not criteria:
            raise ValueError("at least one acceptance criterion is required")
        updated_at = datetime.now(timezone.utc)
        try:
            self._connection.execute(
                "INSERT INTO requirements VALUES (?, ?, ?, ?, ?, ?, ?)",
                (requirement_id, title, scope, json.dumps(criteria),
                 RequirementStatus.DESIGNED.value, "[]", updated_at.isoformat()),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"requirement already exists: {requirement_id}") from exc
        return self.get(requirement_id)

    def get(self, requirement_id: str) -> Requirement:
        row = self._connection.execute(
            "SELECT requirement_id, title, scope, acceptance_criteria, status, "
            "evidence, updated_at FROM requirements WHERE requirement_id = ?",
            (requirement_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown requirement: {requirement_id}")
        return self._from_row(row)

    def list(self, *, status: RequirementStatus | None = None) -> tuple[Requirement, ...]:
        if status is None:
            rows = self._connection.execute(
                "SELECT requirement_id, title, scope, acceptance_criteria, status, "
                "evidence, updated_at FROM requirements ORDER BY requirement_id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT requirement_id, title, scope, acceptance_criteria, status, "
                "evidence, updated_at FROM requirements WHERE status = ? "
                "ORDER BY requirement_id", (status.value,)
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def advance(self, requirement_id: str, status: RequirementStatus,
                *, evidence: str | None = None) -> Requirement:
        current = self.get(requirement_id)
        current_index = _STATUS_ORDER.index(current.status)
        next_index = current_index + 1
        if next_index >= len(_STATUS_ORDER) or _STATUS_ORDER[next_index] is not status:
            raise ValueError(
                f"invalid status transition: {current.status.value} -> {status.value}"
            )
        if status in {RequirementStatus.TESTED, RequirementStatus.VERIFIED}:
            if evidence is None or not evidence.strip():
                raise ValueError("test and verification transitions require evidence")
        evidence_items = list(current.evidence)
        if evidence is not None and evidence.strip():
            evidence_items.append(evidence.strip())
        updated_at = datetime.now(timezone.utc)
        self._connection.execute(
            "UPDATE requirements SET status = ?, evidence = ?, updated_at = ? "
            "WHERE requirement_id = ?",
            (status.value, json.dumps(evidence_items), updated_at.isoformat(),
             requirement_id),
        )
        self._connection.commit()
        return self.get(requirement_id)

    def close(self) -> None:
        self._connection.close()

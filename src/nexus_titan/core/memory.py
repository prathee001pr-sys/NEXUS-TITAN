"""Structured memory with in-memory and SQLite-backed stores."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
import sqlite3
from typing import Iterable
from uuid import uuid4


class MemoryLayer(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    KNOWLEDGE = "knowledge"
    PROCEDURAL = "procedural"


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    content: str
    layer: MemoryLayer
    source: str
    confidence: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    memory_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("memory content must not be empty")
        if not self.source.strip():
            raise ValueError("memory source must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")


class MemoryStore:
    """Simple in-memory store for tests and ephemeral working context."""

    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    def add(self, entry: MemoryEntry) -> None:
        if any(existing.memory_id == entry.memory_id for existing in self._entries):
            raise ValueError(f"duplicate memory_id: {entry.memory_id}")
        self._entries.append(entry)

    def get(self, memory_id: str) -> MemoryEntry | None:
        return next((e for e in self._entries if e.memory_id == memory_id), None)

    def list(self, *, layer: MemoryLayer | None = None) -> tuple[MemoryEntry, ...]:
        entries: Iterable[MemoryEntry] = self._entries
        if layer is not None:
            entries = (e for e in entries if e.layer is layer)
        return tuple(entries)

    def count(self, *, layer: MemoryLayer | None = None) -> int:
        return len(self.list(layer=layer))


class SQLiteMemoryStore:
    """Durable local SQLite store. Protect the database file with OS permissions."""

    def __init__(self, db_path: str) -> None:
        if not db_path.strip():
            raise ValueError("db_path must not be empty")
        self._connection = sqlite3.connect(db_path)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                layer TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                created_at TEXT NOT NULL
            )
        """)
        self._connection.commit()

    def add(self, entry: MemoryEntry) -> None:
        try:
            self._connection.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?)",
                (entry.memory_id, entry.content, entry.layer.value, entry.source,
                 entry.confidence, entry.created_at.isoformat()),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"duplicate memory_id: {entry.memory_id}") from exc

    @staticmethod
    def _from_row(row: tuple) -> MemoryEntry:
        return MemoryEntry(
            content=row[1], layer=MemoryLayer(row[2]), source=row[3],
            confidence=row[4], created_at=datetime.fromisoformat(row[5]),
            memory_id=row[0],
        )

    def get(self, memory_id: str) -> MemoryEntry | None:
        row = self._connection.execute(
            "SELECT memory_id, content, layer, source, confidence, created_at "
            "FROM memories WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def list(self, *, layer: MemoryLayer | None = None) -> tuple[MemoryEntry, ...]:
        if layer is None:
            rows = self._connection.execute(
                "SELECT memory_id, content, layer, source, confidence, created_at "
                "FROM memories ORDER BY rowid"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT memory_id, content, layer, source, confidence, created_at "
                "FROM memories WHERE layer = ? ORDER BY rowid", (layer.value,)
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def count(self, *, layer: MemoryLayer | None = None) -> int:
        if layer is None:
            row = self._connection.execute("SELECT COUNT(*) FROM memories").fetchone()
        else:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM memories WHERE layer = ?", (layer.value,)
            ).fetchone()
        return int(row[0])

    def close(self) -> None:
        self._connection.close()

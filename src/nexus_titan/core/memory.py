"""Minimal structured memory foundation; persistence is intentionally deferred."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
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
    """In-memory store for early development; not durable across restarts."""

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

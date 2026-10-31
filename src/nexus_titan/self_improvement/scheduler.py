"""Persistent scheduled research and knowledge-version management for TITAN EVOLVE.

The worker is deliberately one-shot: run it from Replit Scheduled Deployments,
cron, or an operator-controlled job runner. It never starts a hidden daemon.
Only explicitly registered HTTPS URLs and an explicit hostname allow-list are used.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

from .engine import TitanEvolveEngine
from .llm_research import LLMResearchService
from .research_sources import (
    AllowlistedHTTPSResearchSource,
    ResearchDocument,
    ResearchIngestionService,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class ScheduledResearchSource:
    source_id: str
    url: str
    topic: str
    interval_seconds: int
    enabled: bool
    last_run_at: str | None
    next_run_at: str
    last_status: str
    last_error: str | None
    last_content_sha256: str | None
    created_at: str


@dataclass(frozen=True)
class ScheduledResearchResult:
    source_id: str
    url: str
    status: str
    summary: str
    content_sha256: str | None = None
    learning_id: str | None = None
    skill_proposal_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchScheduleStore:
    """SQLite-backed schedule, run history and source-version registry."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS evolve_research_sources (
                    source_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL UNIQUE,
                    topic TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    last_run_at TEXT,
                    next_run_at TEXT NOT NULL,
                    last_status TEXT NOT NULL,
                    last_error TEXT,
                    last_content_sha256 TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evolve_research_runs (
                    run_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content_sha256 TEXT,
                    learning_id TEXT,
                    skill_proposal_id TEXT,
                    error TEXT,
                    FOREIGN KEY(source_id) REFERENCES evolve_research_sources(source_id)
                );
                CREATE TABLE IF NOT EXISTS evolve_knowledge_versions (
                    source_id TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    learning_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(source_id, content_sha256)
                );
                CREATE INDEX IF NOT EXISTS idx_evolve_research_due
                    ON evolve_research_sources(enabled, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_evolve_research_runs_source
                    ON evolve_research_runs(source_id, started_at);
            """)

    @staticmethod
    def _validate_url(url: str) -> str:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("A research URL is required.")
        parsed = urlsplit(url.strip())
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError("Scheduled research sources must be HTTPS URLs.")
        if parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Research URLs cannot contain credentials or non-standard ports.")
        return url.strip()

    def register_source(self, url: str, topic: str = "scheduled-research",
                        interval_seconds: int = 86_400, enabled: bool = True,
                        run_immediately: bool = True) -> ScheduledResearchSource:
        normalized_url = self._validate_url(url)
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic is required.")
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int):
            raise ValueError("interval_seconds must be an integer.")
        if not 300 <= interval_seconds <= 31 * 86_400:
            raise ValueError("interval_seconds must be between 5 minutes and 31 days.")
        if not isinstance(enabled, bool) or not isinstance(run_immediately, bool):
            raise ValueError("enabled and run_immediately must be booleans.")
        now = _utc_now()
        source_id = str(uuid.uuid4())
        next_run = now if run_immediately else now + timedelta(seconds=interval_seconds)
        with self._connect() as db:
            existing = db.execute("SELECT * FROM evolve_research_sources WHERE url=?",
                                  (normalized_url,)).fetchone()
            if existing:
                db.execute(
                    "UPDATE evolve_research_sources SET topic=?, interval_seconds=?, enabled=?, next_run_at=? WHERE source_id=?",
                    (topic.strip(), interval_seconds, int(enabled), _iso(next_run), existing["source_id"]),
                )
                row = db.execute("SELECT * FROM evolve_research_sources WHERE source_id=?",
                                 (existing["source_id"],)).fetchone()
            else:
                db.execute(
                    "INSERT INTO evolve_research_sources VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (source_id, normalized_url, topic.strip(), interval_seconds, int(enabled),
                     None, _iso(next_run), "NEVER_RUN", None, None, _iso(now)),
                )
                row = db.execute("SELECT * FROM evolve_research_sources WHERE source_id=?",
                                 (source_id,)).fetchone()
        return self._source(row)

    @staticmethod
    def _source(row: sqlite3.Row) -> ScheduledResearchSource:
        return ScheduledResearchSource(
            row["source_id"], row["url"], row["topic"], row["interval_seconds"],
            bool(row["enabled"]), row["last_run_at"], row["next_run_at"],
            row["last_status"], row["last_error"], row["last_content_sha256"],
            row["created_at"],
        )

    def list_sources(self, include_disabled: bool = True) -> list[ScheduledResearchSource]:
        query = "SELECT * FROM evolve_research_sources"
        if not include_disabled:
            query += " WHERE enabled=1"
        query += " ORDER BY next_run_at, url"
        with self._connect() as db:
            rows = db.execute(query).fetchall()
        return [self._source(row) for row in rows]

    def due_sources(self, now: datetime | None = None, limit: int = 20) -> list[ScheduledResearchSource]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        current = _iso(now or _utc_now())
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM evolve_research_sources WHERE enabled=1 AND next_run_at<=? "
                "ORDER BY next_run_at LIMIT ?", (current, limit),
            ).fetchall()
        return [self._source(row) for row in rows]

    def content_version(self, source_id: str, content_sha256: str) -> int | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT version FROM evolve_knowledge_versions WHERE source_id=? AND content_sha256=?",
                (source_id, content_sha256),
            ).fetchone()
        return int(row["version"]) if row else None

    def record_content_version(self, source_id: str, content_sha256: str,
                               learning_id: str, recorded_at: str | None = None) -> int:
        if len(content_sha256) != 64 or not learning_id:
            raise ValueError("A SHA-256 digest and learning_id are required.")
        with self._connect() as db:
            old = db.execute(
                "SELECT version FROM evolve_knowledge_versions WHERE source_id=? AND content_sha256=?",
                (source_id, content_sha256),
            ).fetchone()
            if old:
                return int(old["version"])
            version = int(db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM evolve_knowledge_versions WHERE source_id=?",
                (source_id,),
            ).fetchone()[0])
            db.execute("INSERT INTO evolve_knowledge_versions VALUES(?,?,?,?,?)",
                       (source_id, content_sha256, version, learning_id, recorded_at or _iso(_utc_now())))
            return version

    def finish_run(self, source: ScheduledResearchSource, status: str,
                   content_sha256: str | None = None, learning_id: str | None = None,
                   skill_proposal_id: str | None = None, error: str | None = None,
                   now: datetime | None = None, started_at: datetime | None = None) -> None:
        finished = now or _utc_now()
        started = started_at or finished
        retry_delay = min(source.interval_seconds, 900) if status == "ERROR" else source.interval_seconds
        next_run = finished + timedelta(seconds=retry_delay)
        run_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "UPDATE evolve_research_sources SET last_run_at=?, next_run_at=?, last_status=?, "
                "last_error=?, last_content_sha256=COALESCE(?,last_content_sha256) WHERE source_id=?",
                (_iso(finished), _iso(next_run), status, error, content_sha256, source.source_id),
            )
            db.execute(
                "INSERT INTO evolve_research_runs VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, source.source_id, _iso(started), _iso(finished), status,
                 content_sha256, learning_id, skill_proposal_id, error),
            )

    def stats(self) -> dict[str, int]:
        with self._connect() as db:
            return {
                "scheduled_sources": int(db.execute("SELECT COUNT(*) FROM evolve_research_sources").fetchone()[0]),
                "enabled_sources": int(db.execute("SELECT COUNT(*) FROM evolve_research_sources WHERE enabled=1").fetchone()[0]),
                "research_runs": int(db.execute("SELECT COUNT(*) FROM evolve_research_runs").fetchone()[0]),
                "knowledge_versions": int(db.execute("SELECT COUNT(*) FROM evolve_knowledge_versions").fetchone()[0]),
            }


class ScheduledResearchWorker:
    """Runs due, allow-listed research fetches and stores versioned learning evidence."""

    def __init__(self, engine: TitanEvolveEngine, fetcher: AllowlistedHTTPSResearchSource,
                 llm_provider: Any | None = None) -> None:
        self.engine = engine
        self.store = ResearchScheduleStore(engine.store.db_path)
        self.fetcher = fetcher
        self.llm_provider = llm_provider

    def run_due(self, now: datetime | None = None, limit: int = 20) -> list[ScheduledResearchResult]:
        results: list[ScheduledResearchResult] = []
        for source in self.store.due_sources(now=now, limit=limit):
            started_at = now or _utc_now()
            try:
                document = self.fetcher.fetch(source.url)
                if not document.topic or document.topic == "external-research":
                    document = ResearchDocument(document.title, document.text, document.source,
                                                source.topic, document.published_at)
                body = document.text[:30_000]
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if self.store.content_version(source.source_id, digest) is not None:
                    result = ScheduledResearchResult(
                        source.source_id, source.url, "SKIPPED_UNCHANGED",
                        "Content hash already exists; duplicate learning was suppressed.", digest,
                    )
                    self.store.finish_run(source, result.status, digest, now=now, started_at=started_at)
                    results.append(result)
                    continue

                previous_hash = source.last_content_sha256
                evidence_tags = ["scheduled-research", "untrusted-source",
                                 f"source-id:{source.source_id}"]
                if previous_hash:
                    evidence_tags.append("source-updated")
                learning = ResearchIngestionService(self.engine).ingest_document(
                    ResearchDocument(document.title, body, document.source,
                                     source.topic, document.published_at),
                    tags=evidence_tags,
                )
                version = self.store.record_content_version(
                    source.source_id, digest, learning.learning_id, _iso(now or _utc_now()))
                # LLM output is a low-confidence draft only. It never activates a skill.
                proposal_id = None
                if self.llm_provider is not None:
                    try:
                        synthesis = LLMResearchService(self.engine, self.llm_provider).synthesize([document])
                        draft = synthesis.get("skill_draft", {})
                        if isinstance(draft, dict) and draft.get("name") and draft.get("instructions"):
                            proposal = self.engine.propose_improvement(
                                title=f"Scheduled research skill draft: {draft['name']}",
                                description=str(draft.get("description", "")),
                                rationale="Draft generated from scheduled, provenance-tracked research; requires validation and human approval.",
                                expected_benefit="Potential reusable skill after independent evidence and approval.",
                                risk_level="LOW",
                            )
                            proposal_id = proposal.proposal_id
                    except Exception:
                        proposal_id = None
                status = "KNOWLEDGE_UPDATED" if version > 1 or previous_hash else "INGESTED"
                result = ScheduledResearchResult(
                    source.source_id, source.url, status,
                    f"Stored knowledge version {version}; external content remains untrusted.",
                    digest, learning.learning_id, proposal_id,
                )
                self.store.finish_run(source, status, digest, learning.learning_id,
                                      proposal_id, now=now, started_at=started_at)
                self.engine.store.audit("SCHEDULED_RESEARCH_INGESTED", "research_source",
                                        source.source_id, result.to_dict())
                results.append(result)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"[:1000]
                result = ScheduledResearchResult(source.source_id, source.url, "ERROR",
                                                 "Scheduled research failed safely.", error=message)
                self.store.finish_run(source, "ERROR", error=message, now=now, started_at=started_at)
                results.append(result)
        return results

"""TITAN LEARN: read-only, rights-aware educational source evidence library.

Ingest bounded *user-authorized extracted text*, not course downloads or native video.
Material is always untrusted DATA, never instructions, never executable strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sqlite3

KINDS = frozenset({"pdf", "video_transcript", "course_notes", "article", "research_paper"})
RIGHTS = frozenset({"USER_OWNED", "EXPLICITLY_AUTHORIZED", "PUBLIC_REUSE_PERMITTED"})
CONFIDENCE = frozenset({"UNVERIFIED", "CONFLICTED", "SUPPORTED", "DISPROVEN", "STALE"})
_ANCHOR = re.compile(r"(?:page:[1-9][0-9]{0,5}|time:[0-9]{2,3}:[0-5][0-9]:[0-5][0-9]|section:[a-zA-Z0-9_\-.]{1,64})\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class LearningEvidence:
    evidence_id: str
    source_id: str
    kind: str
    title: str
    reference: str
    citation_anchor: str
    fingerprint: str
    confidence: str = "UNVERIFIED"
    research_only: bool = True
    trade_authorized: bool = False
    strategy_promotion_enabled: bool = False


class LearningEvidenceLibrary:
    """Citation-preserving bounded metadata and excerpts, no HTTP/LLM execution."""

    def __init__(self, db_path: str | Path) -> None:
        self.db = sqlite3.connect(str(db_path), timeout=5, isolation_level=None)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("""CREATE TABLE IF NOT EXISTS titan_learning_evidence (
                evidence_id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                kind TEXT NOT NULL, title TEXT NOT NULL, reference TEXT NOT NULL,
                rights TEXT NOT NULL, citation_anchor TEXT NOT NULL,
                excerpt TEXT NOT NULL, fingerprint TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                confidence TEXT NOT NULL DEFAULT 'UNVERIFIED',
                reviewer TEXT, review_evidence TEXT, reviewed_at TEXT,
                UNIQUE(source_id,citation_anchor,fingerprint)
            )""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self) -> "LearningEvidenceLibrary":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _bounded(value: str, label: str, limit: int) -> str:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or '\x00' in value:
            raise ValueError(f"invalid {label}")
        return value.strip()

    def ingest_excerpt(self, *, kind: str, title: str, reference: str, rights: str,
                       citation_anchor: str, excerpt: str, source_id: str | None = None) -> LearningEvidence:
        if kind not in KINDS:
            raise ValueError("unsupported source kind")
        if rights not in RIGHTS:
            raise PermissionError("source rights/permission not verified")
        # Paid courses must explicitly authorize excerpt processing; no public-URL assumption.
        if kind == "course_notes" and rights == "PUBLIC_REUSE_PERMITTED":
            raise PermissionError("private course requires owned or explicitly authorized notes")
        title = self._bounded(title, "title", 180)
        reference = self._bounded(reference, "source reference", 400)
        excerpt = self._bounded(excerpt, "short educational excerpt", 2048)
        if not isinstance(citation_anchor, str) or not _ANCHOR.fullmatch(citation_anchor):
            raise ValueError("citation must contain page, timestamp or section")
        if source_id is None:
            source_id = hashlib.sha256(f"{kind}\n{reference}".encode()).hexdigest()
        if not isinstance(source_id, str) or not _SHA.fullmatch(source_id):
            raise ValueError("source_id must be sha256")
        digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        evidence_id = hashlib.sha256(f"{source_id}\n{citation_anchor}\n{digest}".encode()).hexdigest()
        stamp = datetime.now(timezone.utc).isoformat()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT kind,title,reference,rights FROM titan_learning_evidence WHERE evidence_id=?",
                (evidence_id,)
            ).fetchone()
            if existing and existing != (kind, title, reference, rights):
                raise ValueError("evidence identity collision or metadata mismatch")
            if not existing:
                self.db.execute("""INSERT INTO titan_learning_evidence
                    (evidence_id,source_id,kind,title,reference,rights,citation_anchor,excerpt,fingerprint,ingested_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (evidence_id, source_id, kind, title, reference, rights,
                     citation_anchor, excerpt, digest, stamp))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.get(evidence_id)

    def get(self, evidence_id: str) -> LearningEvidence:
        row = self.db.execute(
            "SELECT evidence_id,source_id,kind,title,reference,citation_anchor,fingerprint,confidence "
            "FROM titan_learning_evidence WHERE evidence_id=?", (evidence_id,)
        ).fetchone()
        if not row:
            raise KeyError("unknown learning evidence")
        return LearningEvidence(*row)

    def excerpts(self, *, source_id: str | None = None, limit: int = 100) -> tuple[LearningEvidence, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit out of range")
        if source_id is None:
            ids = self.db.execute("SELECT evidence_id FROM titan_learning_evidence ORDER BY rowid LIMIT ?", (limit,)).fetchall()
        else:
            if not isinstance(source_id, str) or not _SHA.fullmatch(source_id):
                raise ValueError("invalid source_id")
            ids = self.db.execute("SELECT evidence_id FROM titan_learning_evidence WHERE source_id=? ORDER BY rowid LIMIT ?", (source_id, limit)).fetchall()
        return tuple(self.get(x[0]) for x in ids)

    def get_excerpt_text(self, evidence_id: str) -> str:
        """Return only untrusted quoted evidence; caller must never treat it as command."""
        row = self.db.execute("SELECT excerpt FROM titan_learning_evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
        if row is None:
            raise KeyError("unknown learning evidence")
        return row[0]

    def annotate_evidence(self, evidence_id: str, *, status: str, reviewer: str, independent_evidence: str) -> LearningEvidence:
        """Human-reviewed evidence label. 'SUPPORTED' is NOT proof of trading alpha."""
        if status not in CONFIDENCE or status == "UNVERIFIED":
            raise ValueError("review status must be a non-default recognized label")
        reviewer = self._bounded(reviewer, "reviewer", 100)
        independent_evidence = self._bounded(independent_evidence, "independent evidence note", 500)
        # No automatic promotion; annotations are intentionally separate from alpha metrics.
        self.get(evidence_id)
        self.db.execute("UPDATE titan_learning_evidence SET confidence=?,reviewer=?,review_evidence=?,reviewed_at=? "
                        "WHERE evidence_id=?", (status, reviewer, independent_evidence,
                        datetime.now(timezone.utc).isoformat(), evidence_id))
        return self.get(evidence_id)


def ingest_local_pdf(
    library: LearningEvidenceLibrary, *, pdf_path: str | Path,
    reference: str, rights: str, max_pages: int = 30, max_bytes: int = 5_000_000,
) -> tuple[LearningEvidence, ...]:
    """Optional local text PDF adapter; no OCR, network, DRM, or PDF script execution.

    Requires optional pypdf; install in an isolated research worker only.
    Each retained snippet is <= 2 Ki characters, not full copyrighted pages.
    """
    if not isinstance(library, LearningEvidenceLibrary):
        raise TypeError("library required")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 100:
        raise ValueError("invalid page limit")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 100 <= max_bytes <= 10_000_000:
        raise ValueError("invalid file limit")
    file_path = Path(pdf_path)
    if not file_path.is_file() or file_path.suffix.lower() != '.pdf' or file_path.stat().st_size > max_bytes:
        raise ValueError("PDF not found or exceeds quota")
    if file_path.stat().st_size < 5:
        raise ValueError("invalid PDF")
    payload = file_path.read_bytes()
    if not payload.startswith(b'%PDF-'):
        raise ValueError("invalid PDF signature")
    try:
        from pypdf import PdfReader  # optional, no project-wide dependency
    except ImportError as exc:
        raise RuntimeError("install optional pypdf in the isolated worker to extract PDF pages") from exc
    import io
    reader = PdfReader(io.BytesIO(payload), strict=True)
    if reader.is_encrypted:
        raise PermissionError("encrypted or DRM-protected PDF unsupported")
    if len(reader.pages) > max_pages:
        raise ValueError("PDF exceeds page quota")
    title = file_path.stem[:180]
    ids: list[LearningEvidence] = []
    for i, page in enumerate(reader.pages, start=1):
        body = (page.extract_text() or '').strip()
        if not body:
            continue
        # Store short excerpt for source traceability rather than replicating full work.
        ids.append(library.ingest_excerpt(kind='pdf',title=title,reference=reference,
                      rights=rights,citation_anchor=f'page:{i}',excerpt=body[:2048]))
    return tuple(ids)


def ingest_permitted_video_transcript(
    library: LearningEvidenceLibrary, *, title: str, reference: str,
    rights: str, segments: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    max_segments: int = 50,
) -> tuple[LearningEvidence, ...]:
    """User-provided authorized timestamped transcript segments; no media download."""
    if not isinstance(library, LearningEvidenceLibrary):
        raise TypeError("library required")
    if isinstance(max_segments, bool) or not isinstance(max_segments, int) or not 1 <= max_segments <= 100:
        raise ValueError("invalid segment limit")
    if not isinstance(segments, (list, tuple)) or len(segments) > max_segments:
        raise ValueError("too many transcript segments")
    results: list[LearningEvidence] = []
    for segment in segments:
        if not isinstance(segment, (list, tuple)) or len(segment) != 2:
            raise ValueError("expected (HH:MM:SS, short text) segment")
        timestamp, text = segment
        if not isinstance(timestamp, str) or not re.fullmatch(r'[0-9]{2,3}:[0-5][0-9]:[0-5][0-9]', timestamp):
            raise ValueError("invalid transcript timestamp")
        results.append(library.ingest_excerpt(kind='video_transcript',title=title,
                       reference=reference,rights=rights,citation_anchor=f'time:{timestamp}',excerpt=text))
    return tuple(results)

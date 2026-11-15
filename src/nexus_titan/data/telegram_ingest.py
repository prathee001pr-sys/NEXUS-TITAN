"""Read-Only Telegram Channel Signal Intelligence & Quarantine Store (Workstream X / docs/TELEGRAM_CHANNEL_INTEGRATION.md).

Strict safety invariants:
1. Default-deny channel allowlist: unknown channels are rejected before parsing.
2. Read-only: no outbound send/reply/forward/join methods exist.
3. Untrusted content boundary: raw message text is never executed; output is a candidate research record only.
4. No broker, order, or live-trading imports or calls.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"(__import__|eval\s*\(|exec\s*\(|subprocess|os\.system)", re.IGNORECASE),
)

_SIGNAL_REGEX = re.compile(
    r"\b(?P<side>BUY|SELL)\s+(?P<symbol>[A-Z0-9_]{3,20})(?:\s+(?P<strike>\d{4,6})\s*(?P<opt>CE|PE))?"
    r".*?(?:@|AT|ENTRY[:\s]*)\s*(?P<entry>\d+(?:\.\d+)?)"
    r".*?(?:SL|STOP[:\s]*)\s*(?P<stop>\d+(?:\.\d+)?)"
    r"(?:.*?(?:TGT|TARGET[:\s]*)\s*(?P<target>\d+(?:\.\d+)?))?",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class AllowlistedChannel:
    channel_id: str
    display_name: str
    enabled: bool
    added_by: str
    added_at: str
    max_message_chars: int = 2000


@dataclass(frozen=True)
class CandidateSignalRecord:
    """Normalized untrusted research candidate extracted from an allowlisted channel post."""

    record_id: str
    channel_id: str
    message_id: int
    edit_version: int
    message_timestamp: str
    ingested_at: str
    raw_text_sha256: str
    status: Literal["CANDIDATE_FOR_RESEARCH", "QUARANTINED_MALFORMED", "QUARANTINED_SUSPICIOUS"]
    symbol: str | None
    side: Literal["BUY", "SELL"] | None
    option_type: Literal["CE", "PE"] | None
    strike: float | None
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    parser_confidence: float
    warnings: tuple[str, ...]
    can_trigger_order: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReadOnlyTelegramIngestionGuard:
    """Enforces allowlist, deduplication/edit tracking, prompt-injection quarantine, and research-only storage (Workstream X)."""

    def __init__(self, db_path: str | Path = "data/telegram_research_quarantine.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS allowlisted_channels (
                    channel_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    added_by TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    max_message_chars INTEGER NOT NULL DEFAULT 2000
                );
                CREATE TABLE IF NOT EXISTS ingested_channel_messages (
                    record_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    edit_version INTEGER NOT NULL,
                    message_timestamp TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    raw_text_sha256 TEXT NOT NULL,
                    raw_text_excerpt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parsed_json TEXT NOT NULL,
                    UNIQUE(channel_id, message_id, edit_version)
                );
            """)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def register_channel(
        self, channel_id: str, display_name: str, *, added_by: str, enabled: bool = True, max_message_chars: int = 2000
    ) -> AllowlistedChannel:
        if not channel_id.strip() or not display_name.strip() or not added_by.strip():
            raise ValueError("channel_id, display_name, and added_by are required.")
        if max_message_chars < 100 or max_message_chars > 10_000:
            raise ValueError("max_message_chars must be between 100 and 10000.")
        now = datetime.now(timezone.utc).isoformat()
        item = AllowlistedChannel(channel_id.strip(), display_name.strip(), bool(enabled), added_by.strip(), now, max_message_chars)
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO allowlisted_channels VALUES (?, ?, ?, ?, ?, ?)",
                (item.channel_id, item.display_name, int(item.enabled), item.added_by, item.added_at, item.max_message_chars),
            )
        return item

    def ingest_post(
        self,
        *,
        channel_id: str,
        message_id: int,
        text: str,
        message_timestamp: str,
        edit_version: int = 0,
    ) -> CandidateSignalRecord:
        """Validate channel allowlist, deduplicate by (channel_id, message_id, edit_version), and parse untrusted signal."""
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id < 1 or edit_version < 0:
            raise ValueError("message_id must be positive integer and edit_version non-negative.")
        with self._connect() as db:
            ch_row = db.execute(
                "SELECT * FROM allowlisted_channels WHERE channel_id = ? AND enabled = 1", (channel_id.strip(),)
            ).fetchone()
            if ch_row is None:
                raise PermissionError(f"Default-deny: channel '{channel_id}' is not in the enabled allowlist.")
            existing = db.execute(
                "SELECT parsed_json FROM ingested_channel_messages WHERE channel_id=? AND message_id=? AND edit_version=?",
                (channel_id.strip(), message_id, edit_version),
            ).fetchone()
            if existing is not None:
                data = json.loads(existing["parsed_json"])
                data["warnings"] = tuple(data.get("warnings", ()))
                return CandidateSignalRecord(**data)

        max_chars = int(ch_row["max_message_chars"])
        safe_text = str(text or "")
        warnings: list[str] = []
        if len(safe_text) > max_chars:
            safe_text = safe_text[:max_chars]
            warnings.append(f"Message truncated to {max_chars} chars.")

        text_hash = hashlib.sha256(safe_text.encode("utf-8")).hexdigest()
        record_id = f"TG-{channel_id.strip()}-{message_id}-v{edit_version}"
        now = datetime.now(timezone.utc).isoformat()

        # Check for prompt injection / hostile content
        for pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(safe_text):
                warnings.append("Suspicious prompt-injection or code-execution pattern detected; quarantined.")
                rec = CandidateSignalRecord(
                    record_id=record_id, channel_id=channel_id.strip(), message_id=message_id,
                    edit_version=edit_version, message_timestamp=message_timestamp, ingested_at=now,
                    raw_text_sha256=text_hash, status="QUARANTINED_SUSPICIOUS",
                    symbol=None, side=None, option_type=None, strike=None,
                    entry_price=None, stop_price=None, target_price=None,
                    parser_confidence=0.0, warnings=tuple(warnings), can_trigger_order=False,
                )
                self._persist(rec, safe_text[:500])
                return rec

        match = _SIGNAL_REGEX.search(safe_text)
        if not match:
            warnings.append("No structured BUY/SELL + ENTRY + SL signal fields found.")
            rec = CandidateSignalRecord(
                record_id=record_id, channel_id=channel_id.strip(), message_id=message_id,
                edit_version=edit_version, message_timestamp=message_timestamp, ingested_at=now,
                raw_text_sha256=text_hash, status="QUARANTINED_MALFORMED",
                symbol=None, side=None, option_type=None, strike=None,
                entry_price=None, stop_price=None, target_price=None,
                parser_confidence=0.0, warnings=tuple(warnings), can_trigger_order=False,
            )
            self._persist(rec, safe_text[:500])
            return rec

        side_val = match.group("side").upper()
        symbol_val = match.group("symbol").upper()
        strike_val = float(match.group("strike")) if match.group("strike") else None
        opt_val = match.group("opt").upper() if match.group("opt") else None
        entry_val = float(match.group("entry"))
        stop_val = float(match.group("stop"))
        target_val = float(match.group("target")) if match.group("target") else None

        # Price sanity check
        valid_levels = True
        if entry_val <= 0 or stop_val <= 0:
            valid_levels = False
            warnings.append("Non-positive entry or stop price.")
        elif side_val == "BUY" and stop_val >= entry_val:
            valid_levels = False
            warnings.append("Contradictory BUY levels: stop_price >= entry_price.")
        elif side_val == "SELL" and stop_val <= entry_val:
            valid_levels = False
            warnings.append("Contradictory SELL levels: stop_price <= entry_price.")

        status: Literal["CANDIDATE_FOR_RESEARCH", "QUARANTINED_MALFORMED"] = (
            "CANDIDATE_FOR_RESEARCH" if valid_levels else "QUARANTINED_MALFORMED"
        )
        rec = CandidateSignalRecord(
            record_id=record_id,
            channel_id=channel_id.strip(),
            message_id=message_id,
            edit_version=edit_version,
            message_timestamp=message_timestamp,
            ingested_at=now,
            raw_text_sha256=text_hash,
            status=status,
            symbol=symbol_val,
            side=side_val,  # type: ignore[arg-type]
            option_type=opt_val,  # type: ignore[arg-type]
            strike=strike_val,
            entry_price=entry_val,
            stop_price=stop_val,
            target_price=target_val,
            parser_confidence=0.75 if (valid_levels and target_val) else (0.55 if valid_levels else 0.0),
            warnings=tuple(warnings),
            can_trigger_order=False,
        )
        self._persist(rec, safe_text[:500])
        return rec

    def _persist(self, record: CandidateSignalRecord, excerpt: str) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO ingested_channel_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.record_id, record.channel_id, record.message_id, record.edit_version,
                    record.message_timestamp, record.ingested_at, record.raw_text_sha256,
                    excerpt, record.status, json.dumps(record.to_dict(), sort_keys=True),
                ),
            )

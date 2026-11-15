"""Audited code-change proposals. Candidate code is parsed, stored and reviewed,
never executed or automatically applied by TITAN EVOLVE.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_ALLOWED_PREFIX = "src/nexus_titan/research/"
_PROTECTED_PREFIXES = (
    "src/nexus_titan/risk/", "src/nexus_titan/virtual/", "src/nexus_titan/storage/",
    "src/nexus_titan/security/", "src/nexus_titan/brokers/",
)
_FORBIDDEN_IMPORTS = {
    "os", "sys", "subprocess", "socket", "ctypes", "pickle", "multiprocessing",
    "importlib", "builtins", "marshal", "pathlib", "shutil", "inspect", "tempfile",
    "glob", "io", "urllib", "http", "ftplib", "asyncio", "threading", "signal",
    "resource", "pty", "fcntl", "webbrowser", "code", "codeop", "runpy",
}
_FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "__import__", "open", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "input", "breakpoint", "memoryview",
}
_FORBIDDEN_ATTR_CALLS = {
    "eval", "exec", "compile", "__import__", "open", "write_text", "write_bytes",
    "read_text", "read_bytes", "unlink", "rmdir", "rmtree", "mkdir", "makedirs",
    "rename", "replace", "chmod", "chown", "system", "popen", "spawn", "getattr",
    "setattr", "delattr", "load", "loads", "dump", "dumps",
}


@dataclass(frozen=True)
class CodeChangeProposal:
    change_id: str
    relative_path: str
    rationale: str
    base_sha256: str
    candidate_sha256: str
    candidate_source: str
    status: str
    created_at: str
    reviewed_by: str | None = None


class CodeChangeProposalManager:
    """Creates reviewable source proposals in the research area only."""

    def __init__(self, db_path: str | Path = "data/titan_learning.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
                entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, details_json TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS code_change_proposals (
                change_id TEXT PRIMARY KEY, relative_path TEXT NOT NULL, rationale TEXT NOT NULL,
                base_sha256 TEXT NOT NULL, candidate_sha256 TEXT NOT NULL, candidate_source TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, reviewed_by TEXT)""")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
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

    @staticmethod
    def _validate_source(source: str) -> None:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ValueError(f"Candidate source has a syntax error: {exc.msg}") from exc
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name.split(".")[0] for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [(node.module or "").split(".")[0]]
                )
                if _FORBIDDEN_IMPORTS.intersection(names):
                    raise PermissionError("Candidate imports a prohibited process/network/filesystem/native module.")
            if isinstance(node, ast.Attribute):
                if node.attr.startswith("__") and node.attr.endswith("__"):
                    raise PermissionError(f"Candidate accesses prohibited dunder attribute: {node.attr}")
            if isinstance(node, ast.Name):
                if node.id in {"__builtins__", "__loader__", "__spec__", "__import__"}:
                    raise PermissionError(f"Candidate references prohibited dunder identifier: {node.id}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
                    raise PermissionError(f"Candidate uses prohibited dynamic execution or reflection: {node.func.id}")
                if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_ATTR_CALLS:
                    raise PermissionError(f"Candidate calls prohibited method or attribute: {node.func.attr}")

    def propose(self, project_root: str | Path, relative_path: str, candidate_source: str,
                rationale: str) -> CodeChangeProposal:
        root = Path(project_root).resolve()
        rel = Path(relative_path).as_posix()
        if not rel.startswith(_ALLOWED_PREFIX) or rel.startswith(_PROTECTED_PREFIXES):
            raise PermissionError("Self-coding proposals are restricted to src/nexus_titan/research/.")
        target = (root / rel).resolve()
        research_root = (root / "src/nexus_titan/research").resolve()
        if research_root not in target.parents or not target.is_file():
            raise PermissionError("Resolved target must remain inside src/nexus_titan/research/.")
        if not rationale.strip() or not candidate_source.strip():
            raise ValueError("rationale and candidate_source are required.")
        self._validate_source(candidate_source)
        base = target.read_bytes()
        candidate = candidate_source.encode("utf-8")
        item = CodeChangeProposal(str(uuid.uuid4()), rel, rationale.strip(),
            hashlib.sha256(base).hexdigest(), hashlib.sha256(candidate).hexdigest(),
            candidate_source, "PROPOSED_FOR_REVIEW", datetime.now(timezone.utc).isoformat())
        with self._connect() as db:
            db.execute("INSERT INTO code_change_proposals VALUES(?,?,?,?,?,?,?,?,?)", (
                item.change_id, item.relative_path, item.rationale, item.base_sha256,
                item.candidate_sha256, item.candidate_source, item.status, item.created_at, None))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                ("CODE_CHANGE_PROPOSED", "code_change", item.change_id,
                 json.dumps({"path": rel, "base_sha256": item.base_sha256, "candidate_sha256": item.candidate_sha256}, sort_keys=True), item.created_at))
        return item

    def is_base_unchanged(self, project_root: str | Path, change_id: str) -> bool:
        """Check whether the source file still matches the proposal's recorded base hash."""
        with self._connect() as db:
            row = db.execute("SELECT relative_path, base_sha256 FROM code_change_proposals WHERE change_id=?",
                             (change_id,)).fetchone()
        if not row:
            raise ValueError("Unknown code change proposal.")
        root = Path(project_root).resolve()
        target = (root / row[0]).resolve()
        research_root = (root / "src/nexus_titan/research").resolve()
        if research_root not in target.parents or not target.is_file():
            return False
        current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        return current_hash == row[1]

    def mark_reviewed(self, change_id: str, reviewed_by: str, accepted: bool) -> CodeChangeProposal:
        if not reviewed_by.strip() or not isinstance(accepted, bool):
            raise ValueError("A reviewer and explicit boolean decision are required.")
        status = "ACCEPTED_FOR_MANUAL_MERGE" if accepted else "REJECTED"
        with self._connect() as db:
            row = db.execute("SELECT * FROM code_change_proposals WHERE change_id=?", (change_id,)).fetchone()
            if not row:
                raise ValueError("Unknown code change proposal.")
            if row[6] != "PROPOSED_FOR_REVIEW":
                raise ValueError("Only unreviewed code proposals can be reviewed.")
            db.execute("UPDATE code_change_proposals SET status=?, reviewed_by=? WHERE change_id=?",
                       (status, reviewed_by.strip(), change_id))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                ("CODE_CHANGE_REVIEWED", "code_change", change_id,
                 json.dumps({"status": status, "reviewed_by": reviewed_by.strip()}), datetime.now(timezone.utc).isoformat()))
            updated = db.execute("SELECT * FROM code_change_proposals WHERE change_id=?", (change_id,)).fetchone()
        return CodeChangeProposal(*updated)

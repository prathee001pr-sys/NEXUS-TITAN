"""Stage122: atomic, operator-staged backups for the Stage117 *research* ledger.

Backup/restore never changes a running database, risk policy, or trade state.
No automatic restore or autonomous promotion. Database history stays local.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class VerifiedResearchSnapshot:
    path: str
    sha256: str
    rows: int
    state: str = "VERIFIED_RESEARCH_BACKUP"
    auto_restored: bool = False
    live_trading_enabled: bool = False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as reader:
        for chunk in iter(lambda: reader.read(128 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _validate_path(path: str | Path, *, source: bool) -> Path:
    p = Path(path)
    if p.is_symlink():
        raise PermissionError('symlink source or target not accepted')
    if source and not p.is_file():
        raise FileNotFoundError('research ledger missing')
    if not source and p.exists():
        raise FileExistsError('restore/backup never overwrites an existing file')
    if not p.parent.is_dir() or p.parent.is_symlink():
        raise FileNotFoundError('destination parent not accessible')
    return p


def _open_readonly(p: Path) -> sqlite3.Connection:
    # Explicit read-only mode: a bad path can never create a fresh empty DB.
    uri = 'file:' + quote(str(p.resolve()), safe='/') + '?mode=ro'
    return sqlite3.connect(uri, uri=True, timeout=5)


def _check_db(con: sqlite3.Connection) -> int:
    if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        raise sqlite3.DatabaseError('research ledger integrity check failed')
    # Fail-closed if this is an unrelated or empty SQLite DB.
    row = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='guardian_research_jobs'").fetchone()
    if row != ('guardian_research_jobs',):
        raise sqlite3.DatabaseError('research ledger schema missing')
    return con.execute('SELECT COUNT(*) FROM guardian_research_jobs').fetchone()[0]


def _link_atomic(temp: Path, target: Path) -> None:
    os.link(temp, target)  # atomic and fails if destination already exists
    dirfd = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


def snapshot_guardian_ledger(db_path: str | Path, backup_path: str | Path) -> VerifiedResearchSnapshot:
    """Use SQLite online backup + fsync + atomic no-overwrite publication."""
    source = _validate_path(db_path, source=True)
    dest = _validate_path(backup_path, source=False)
    if source.resolve() == dest.resolve():
        raise ValueError('source and backup must differ')
    fd, tmpstr = tempfile.mkstemp(prefix='.titan-guardian-', suffix='.sqlite',dir=dest.parent)
    os.close(fd)
    tmp = Path(tmpstr)
    try:
        with closing(_open_readonly(source)) as original:
            rows_before = _check_db(original)
            with closing(sqlite3.connect(tmp)) as target:
                original.backup(target)
        with closing(_open_readonly(tmp)) as test:
            rows_after = _check_db(test)
        if rows_before != rows_after:
            raise sqlite3.DatabaseError('row count changed during backup')
        with tmp.open('rb') as reader:
            os.fsync(reader.fileno())
        digest = _sha256(tmp)
        _link_atomic(tmp, dest)
        return VerifiedResearchSnapshot(str(dest), digest, rows_after)
    finally:
        tmp.unlink(missing_ok=True)


def verify_guardian_backup(path: str | Path, expected_sha256: str) -> VerifiedResearchSnapshot:
    p = _validate_path(path, source=True)
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or any(c not in '0123456789abcdef' for c in expected_sha256):
        raise ValueError('expected lowercase SHA256 required')
    if Path(str(p) + "-wal").exists() and Path(str(p) + "-wal").stat().st_size:
        raise PermissionError("backup checksum cannot be trusted with uncheckpointed WAL")
    if _sha256(p) != expected_sha256:
        raise PermissionError('backup checksum mismatch')
    with closing(_open_readonly(p)) as db:
        rows = _check_db(db)
    return VerifiedResearchSnapshot(str(p), expected_sha256, rows)


def stage_guardian_restore(backup_path: str | Path, destination: str | Path,
                           expected_sha256: str) -> VerifiedResearchSnapshot:
    """Place a verified copy at a NEW path for human review; never activate it."""
    original = verify_guardian_backup(backup_path, expected_sha256)
    target = _validate_path(destination, source=False)
    if Path(backup_path).resolve() == target.resolve():
        raise ValueError('restore destination must differ')
    fd, tmpstr = tempfile.mkstemp(prefix='.titan-restore-', suffix='.sqlite',dir=target.parent)
    os.close(fd)
    tmp = Path(tmpstr)
    try:
        shutil.copyfile(original.path,tmp)
        with tmp.open('rb') as reader:
            os.fsync(reader.fileno())
        if _sha256(tmp) != expected_sha256:
            raise PermissionError('staged recovery checksum mismatch')
        with closing(_open_readonly(tmp)) as db:
            rows = _check_db(db)
        _link_atomic(tmp,target)
        return VerifiedResearchSnapshot(str(target),expected_sha256,rows,
                                        state='STAGED_FOR_HUMAN_REVIEW')
    finally:
        tmp.unlink(missing_ok=True)

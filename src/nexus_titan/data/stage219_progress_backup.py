"""Stage 219: exclusive local JSON snapshot + integrity-checked restore rehearsal.

SHA integrity and local reopen are NOT authenticated provenance, offsite backup,
user access control or disaster recovery certification. Never overwrite files.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
import stat
from pathlib import Path

from .stage216_progress_evidence import canonical_digest, sha_ok
from .stage218_dashboard_projection import (DashboardProjection, StageProgressRow,
    audit_dashboard_projection)

_MAX_BYTES = 300_000


@dataclass(frozen=True, slots=True)
class OfflineBackupReceipt:
    accepted: bool
    snapshot_sha256: str
    blocker: str
    independently_authenticated: bool = False
    offsite_recovery_verified: bool = False
    live_trading_authorized: bool = False


def _payload(proj: DashboardProjection) -> dict:
    return {'schema': 'titan.offline-progress.v1', 'stage_limit': proj.stage_limit,
        'journal_head_sha256': proj.journal_head_sha256,
        'projection_sha256': proj.projection_sha256, 'verified_count': 0,
        'rows': [{'stage_number': r.stage_number, 'state': r.state,
                  'evidence_sha256': r.evidence_sha256, 'independently_verified': False} for r in proj.rows]}


def _canonical_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')


def _decode_object_no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def save_local_progress_snapshot(projection: DashboardProjection, path: str | Path) -> OfflineBackupReceipt:
    if not audit_dashboard_projection(projection):
        return OfflineBackupReceipt(False, '', 'invalid projection')
    if not isinstance(path, (str, Path)) or not str(path).strip():
        return OfflineBackupReceipt(False, '', 'invalid backup path')
    target = Path(path)
    if not target.parent.is_dir() or target.parent.is_symlink():
        return OfflineBackupReceipt(False, '', 'backup parent must be an existing real directory')
    try:
        # Reject symlinks in ancestor components as well as in the immediate parent.
        if target.parent.absolute() != target.parent.resolve(strict=True):
            return OfflineBackupReceipt(False, '', 'backup ancestor symlink or ambiguous path')
    except (OSError, RuntimeError):
        return OfflineBackupReceipt(False, '', 'backup parent cannot be safely resolved')
    payload = _payload(projection)
    wrapped = {'payload': payload, 'snapshot_sha256': canonical_digest(payload)}
    data = _canonical_bytes(wrapped)
    if len(data) > _MAX_BYTES:
        return OfflineBackupReceipt(False, '', 'snapshot exceeds size limit')
    fd = None
    created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        fd = os.open(target, flags, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return OfflineBackupReceipt(True, wrapped['snapshot_sha256'], '')
    except OSError:
        if created:
            target.unlink(missing_ok=True)
        return OfflineBackupReceipt(False, '', 'backup write failed or destination exists')
    finally:
        if fd is not None:
            os.close(fd)


def load_local_progress_snapshot(path: str | Path) -> tuple[DashboardProjection | None, OfflineBackupReceipt]:
    if not isinstance(path, (str, Path)) or not str(path).strip():
        return None, OfflineBackupReceipt(False, '', 'invalid restore path')
    target = Path(path)
    try:
        if target.parent.absolute() != target.parent.resolve(strict=True):
            raise ValueError('snapshot ancestor symlink')
        item = target.lstat()
        if (not stat.S_ISREG(item.st_mode) or item.st_size > _MAX_BYTES or item.st_size <= 0
            or item.st_nlink != 1 or (stat.S_IMODE(item.st_mode) & 0o077)):
            raise ValueError('invalid snapshot file')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(target, flags)
        with os.fdopen(fd, 'rb') as handle:
            if os.fstat(handle.fileno()).st_ino != item.st_ino:
                raise ValueError('snapshot switched during open')
            raw = handle.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise ValueError('oversized snapshot')
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=_decode_object_no_duplicates)
        if type(obj) is not dict or set(obj) != {'payload', 'snapshot_sha256'}:
            raise ValueError('unknown snapshot wrapper')
        payload = obj['payload']
        if (type(payload) is not dict or set(payload) != {'schema', 'stage_limit', 'journal_head_sha256',
              'projection_sha256', 'verified_count', 'rows'} or payload['schema'] != 'titan.offline-progress.v1'
              or not sha_ok(obj['snapshot_sha256']) or canonical_digest(payload) != obj['snapshot_sha256']):
            raise ValueError('integrity or schema mismatch')
        if type(payload['rows']) is not list or len(payload['rows']) > 220:
            raise ValueError('invalid rows')
        rows = []
        for row in payload['rows']:
            if type(row) is not dict or set(row) != {'stage_number','state','evidence_sha256','independently_verified'} or row['independently_verified'] is not False:
                raise ValueError('invalid row')
            rows.append(StageProgressRow(row['stage_number'],row['state'],row['evidence_sha256']))
        if type(payload['verified_count']) is not int or payload['verified_count'] != 0:
            raise ValueError('unsupported externally verified marker')
        result = DashboardProjection(payload['stage_limit'], tuple(rows),payload['journal_head_sha256'],payload['projection_sha256'])
        if not audit_dashboard_projection(result):
            raise ValueError('projection integrity mismatch')
        return result, OfflineBackupReceipt(True, obj['snapshot_sha256'], '')
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, KeyError, OverflowError):
        return None, OfflineBackupReceipt(False, '', 'snapshot cannot be safely restored')

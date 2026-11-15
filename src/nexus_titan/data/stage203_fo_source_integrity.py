"""Stage 203: bounded, read-only source byte hashing; NOT provider authentication."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import stat

_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.csv\Z')
_HEX = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class FOSourceFile:
    dataset_id: str
    filename: str
    sha256: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class FOSourceIntegrityReceipt:
    accepted_byte_integrity: bool
    dataset_ids: tuple[str, ...]
    source_sha256: str
    file_count: int
    blockers: tuple[str, ...]
    licensed_vendor_authenticated: bool = False
    exchange_source_authenticated: bool = False
    live_trading_authorized: bool = False
    source_manifest_sha256: str = ''


def audit_fo_source_files(root: str | Path, files: tuple[FOSourceFile, ...], *, max_total_bytes: int = 128*1024*1024) -> FOSourceIntegrityReceipt:
    errors = []
    if not isinstance(root, (str, Path)) or not isinstance(files, tuple) or not 1 <= len(files) <= 128 or type(max_total_bytes) is not int or not 1 <= max_total_bytes <= 512*1024*1024:
        return FOSourceIntegrityReceipt(False, (), '', 0, ('invalid bounded file manifest',))
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        return FOSourceIntegrityReceipt(False, (), '', 0, ('unsafe or missing source directory',))
    base = base.resolve(strict=True)
    records, names, dataset_ids, total = [], set(), set(), 0
    for i, item in enumerate(files):
        if type(item) is not FOSourceFile:
            errors.append(f'{i}: typed manifest item required'); continue
        if (not isinstance(item.dataset_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', item.dataset_id)
                or not isinstance(item.filename, str) or not _NAME.fullmatch(item.filename)
                or not isinstance(item.sha256, str) or not _HEX.fullmatch(item.sha256)
                or type(item.byte_count) is not int or not 1 <= item.byte_count <= 64*1024*1024):
            errors.append(f'{i}: invalid file declaration'); continue
        key = item.filename
        if key in names:
            errors.append(f'{i}: duplicate source file'); continue
        names.add(key); dataset_ids.add(item.dataset_id)
        total += item.byte_count
        if total > max_total_bytes:
            errors.append('declared source byte budget exceeded'); break
        path = base/item.filename
        try:
            if path.is_symlink() or not path.is_file() or path.resolve(strict=True).parent != base:
                raise ValueError('unsafe source path')
            pre = path.stat()
            if not stat.S_ISREG(pre.st_mode) or pre.st_size != item.byte_count:
                raise ValueError('byte size mismatch')
            hasher = hashlib.sha256()
            with path.open('rb') as handle:
                while True:
                    chunk = handle.read(64*1024)
                    if not chunk: break
                    hasher.update(chunk)
            post = path.stat()
            if (post.st_size != pre.st_size or post.st_mtime_ns != pre.st_mtime_ns
                    or not hmac.compare_digest(hasher.hexdigest(), item.sha256)):
                raise ValueError('content hash or file stability mismatch')
            records.append({'id':item.dataset_id, 'file':item.filename, 'sha256':item.sha256, 'bytes':item.byte_count})
        except (OSError, ValueError) as exc:
            errors.append(f'{i}: {exc}')
    digest = hashlib.sha256(json.dumps(sorted(records,key=lambda x:(x['id'],x['file'])),sort_keys=True,separators=(',',':')).encode()).hexdigest() if not errors else ''
    binding = hashlib.sha256(json.dumps(sorted((r['id'],r['file'],r['sha256']) for r in records),separators=(',',':')).encode()).hexdigest() if not errors else ''
    return FOSourceIntegrityReceipt(not errors, tuple(sorted(dataset_ids)) if not errors else (), digest, len(records) if not errors else 0, tuple(errors), source_manifest_sha256=binding)

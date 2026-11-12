"""Stage 156: bounded immutable snapshot receipt. Read-only; no trading authority."""
from __future__ import annotations
import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SnapshotReceipt:
    accepted: bool
    sha256: str
    size: int
    error: str = ''

def verify_snapshot(path: str | Path, *, max_bytes: int = 100_000_000) -> SnapshotReceipt:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError('invalid byte limit')
    path = Path(path)
    if path.is_symlink():
        return SnapshotReceipt(False, '', 0, 'symlink rejected')
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except OSError:
        return SnapshotReceipt(False, '', 0, 'cannot open source')
    try:
        with os.fdopen(fd, 'rb') as f:
            before = os.fstat(f.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > max_bytes:
                return SnapshotReceipt(False, '', 0, 'invalid source type or size')
            h = hashlib.sha256(); size = 0
            with tempfile.TemporaryFile() as copy:
                while True:
                    chunk = f.read(min(1024*1024, max_bytes + 1 - size))
                    if not chunk: break
                    size += len(chunk)
                    if size > max_bytes: return SnapshotReceipt(False, '', size, 'size exceeded')
                    copy.write(chunk); h.update(chunk)
                after = os.fstat(f.fileno())
                final = path.stat()
                sig = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
                if size != before.st_size or sig(before) != sig(after) or sig(after) != sig(final):
                    return SnapshotReceipt(False, '', size, 'source changed')
                copy.seek(0)
                check = hashlib.sha256()
                while chunk := copy.read(1024*1024): check.update(chunk)
                if check.digest() != h.digest(): return SnapshotReceipt(False, '', size, 'snapshot mismatch')
            return SnapshotReceipt(True, h.hexdigest(), size)
    except OSError:
        return SnapshotReceipt(False, '', 0, 'source read failed')

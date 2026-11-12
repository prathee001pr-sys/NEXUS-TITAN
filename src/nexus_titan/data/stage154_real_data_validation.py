"""Stage 154: bounded, read-only historical data validation on a stable snapshot.

No order execution, strategy promotion or live trading authorization.
"""
from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from nexus_titan.data.canonical import load_canonical_data

IST = ZoneInfo('Asia/Kolkata')


@dataclass(frozen=True, slots=True)
class RealDataReceipt:
    accepted: bool
    sha256: str
    bytes_checked: int
    rows_checked: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def _signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inspect_real_market_csv(
    path: str | Path, *, symbol: str = 'NIFTY', interval: str = '1m',
    source_timezone: str = 'Asia/Kolkata', max_bytes: int = 100_000_000,
    enforce_nse_cash_session: bool = True,
) -> RealDataReceipt:
    """Copy once to a private snapshot; validate the exact bytes that were hashed.

    Session checks only apply to NSE cash-market intraday candles. Holidays,
    special sessions, exchange provenance and derivatives-specific sessions
    are NOT certified. An accepted receipt is not a trading approval.
    """
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError('max_bytes must be a positive integer')
    if symbol not in ('NIFTY', 'BANKNIFTY'):
        return RealDataReceipt(False, '', 0, 0, ('unsupported symbol',), ())
    if not isinstance(interval, str) or not interval:
        return RealDataReceipt(False, '', 0, 0, ('invalid interval',), ())
    try:
        ZoneInfo(source_timezone)
    except (TypeError, ValueError, KeyError):
        return RealDataReceipt(False, '', 0, 0, ('unknown source timezone',), ())
    file_path = Path(path)
    try:
        if file_path.is_symlink():
            return RealDataReceipt(False, '', 0, 0, ('symlink not allowed',), ())
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        fd = os.open(file_path, flags)
    except OSError:
        return RealDataReceipt(False, '', 0, 0, ('source cannot be opened',), ())
    try:
        with os.fdopen(fd, 'rb') as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= max_bytes:
                return RealDataReceipt(False, '', before.st_size, 0, ('invalid source type or size',), ())
            digest = hashlib.sha256()
            total = 0
            with tempfile.TemporaryDirectory(prefix='titan154_') as directory:
                snapshot = Path(directory) / 'snapshot.csv'
                with snapshot.open('wb') as output:
                    while chunk := source.read(min(1024 * 1024, max_bytes + 1 - total)):
                        total += len(chunk)
                        if total > max_bytes:
                            return RealDataReceipt(False, '', total, 0, ('size limit exceeded',), ())
                        digest.update(chunk)
                        output.write(chunk)
                after = os.fstat(source.fileno())
                try:
                    path_after = file_path.stat()
                except OSError:
                    return RealDataReceipt(False, '', total, 0, ('source path disappeared',), ())
                if total != before.st_size or _signature(before) != _signature(after) or _signature(after) != _signature(path_after):
                    return RealDataReceipt(False, '', total, 0, ('source changed during snapshot',), ())
                candles, report = load_canonical_data(snapshot, symbol=symbol, interval=interval,
                                                      source_timezone=source_timezone)
                errors = list(report.errors)
                warnings = ['Exchange provenance, holidays and market completeness are not verified.']
                if enforce_nse_cash_session and interval.endswith('m'):
                    for idx, candle in enumerate(candles, 1):
                        ts = candle.datetime.astimezone(IST)
                        if ts.weekday() >= 5 or not (time(9, 15) <= ts.time() < time(15, 30)):
                            errors.append(f'Candle {idx}: outside regular NSE cash session')
                            if len(errors) >= 25:
                                break
                return RealDataReceipt(not errors and bool(candles), digest.hexdigest(), total,
                                       report.total_rows_checked, tuple(errors), tuple(warnings))
    except OSError:
        return RealDataReceipt(False, '', 0, 0, ('source read failed',), ())

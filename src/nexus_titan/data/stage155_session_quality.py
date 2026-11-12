"""Stage 155: bounded read-only session completeness audit; no trade authorization.

Calendar is caller-supplied and must be independently sourced/verified. Missing
sessions are never assumed to be exchange holidays.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')

@dataclass(frozen=True)
class SessionQualityReceipt:
    accepted: bool
    rows: int
    missing_minutes: int
    missing_sessions: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def audit_nse_minute_csv(path: str | Path, *, start: date, end: date,
                         holidays: frozenset[date] = frozenset(),
                         special_sessions: dict[date, tuple[time, time]] | None = None,
                         max_bytes: int = 100_000_000,
                         max_errors: int = 30) -> SessionQualityReceipt:
    """Check one-minute NSE cash session coverage, not exchange authenticity.

    Timestamps mark candle START. Caller must supply a trusted trading calendar.
    Special sessions override the default 09:15-15:30 session. This audit does
    not certify derivatives contracts or the authenticity of historical data.
    """
    if not isinstance(start, date) or not isinstance(end, date) or start > end:
        raise ValueError('invalid date range')
    if (end - start).days > 366:
        raise ValueError('date range exceeds 367 calendar days')
    if isinstance(max_bytes, bool) or max_bytes <= 0 or max_errors <= 0:
        raise ValueError('invalid bounds')
    sessions = special_sessions or {}
    for day, (begin, finish) in sessions.items():
        if not isinstance(day, date) or not isinstance(begin, time) or not isinstance(finish, time) or begin >= finish or begin.second or finish.second or begin.microsecond or finish.microsecond:
            raise ValueError('invalid special session')
    expected: set[datetime] = set()
    d = start
    while d <= end:
        if d in sessions:
            begin, finish = sessions[d]
        elif d.weekday() < 5 and d not in holidays:
            begin, finish = time(9, 15), time(15, 30)
        else:
            d += timedelta(days=1)
            continue
        ts = datetime.combine(d, begin, IST)
        last = datetime.combine(d, finish, IST)
        while ts < last:
            expected.add(ts.astimezone(timezone.utc))
            ts += timedelta(minutes=1)
        d += timedelta(days=1)
    warnings = ('Holiday/special-session calendar is caller supplied; exchange provenance is unverified.',)
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        return SessionQualityReceipt(False, 0, len(expected), (), ('invalid file type or size',), warnings)
    seen: set[datetime] = set()
    errors: list[str] = []
    rows = 0
    previous = None
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or 'timestamp' not in reader.fieldnames:
                return SessionQualityReceipt(False, 0, len(expected), (), ('missing timestamp column',), warnings)
            for row in reader:
                rows += 1
                try:
                    stamp = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=IST)
                    stamp = stamp.astimezone(timezone.utc)
                    if stamp.second or stamp.microsecond:
                        raise ValueError('timestamp not minute aligned')
                except (ValueError, TypeError, AttributeError):
                    if len(errors) < max_errors:
                        errors.append(f'row {rows}: invalid timestamp')
                    continue
                if stamp in seen and len(errors) < max_errors:
                    errors.append(f'row {rows}: duplicate timestamp')
                if previous is not None and stamp <= previous and len(errors) < max_errors:
                    errors.append(f'row {rows}: non-increasing timestamp')
                if stamp not in expected and len(errors) < max_errors:
                    errors.append(f'row {rows}: outside declared sessions')
                seen.add(stamp)
                previous = stamp
    except (OSError, UnicodeError, csv.Error) as exc:
        return SessionQualityReceipt(False, rows, len(expected), (), (f'read failure: {type(exc).__name__}',), warnings)
    missing = expected - seen
    missing_days = tuple(sorted({ts.astimezone(IST).date().isoformat() for ts in missing}))
    if missing and len(errors) < max_errors:
        errors.append(f'{len(missing)} expected one-minute candles missing')
    return SessionQualityReceipt(not errors and bool(expected), rows, len(missing), missing_days, tuple(errors), warnings)

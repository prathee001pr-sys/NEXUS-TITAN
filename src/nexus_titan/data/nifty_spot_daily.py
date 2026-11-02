"""Stage 27: safe conversion of NSE-style NIFTY 50 *spot index* daily CSV.

The 7-column source uses newest-first dates, aggregate shares traded and
turnover in rupee crores. This is NOT a futures/options trade/volume series.
No data origin or NSE licensing is authenticated by this structural adapter.
No broker actions, network, automatic promotion, or market-data rewriting.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

from nexus_titan.data.canonical import CanonicalCandle


class NiftySpotDailyImportError(ValueError):
    """Invalid or unsupported NIFTY spot-daily source: no rows released."""


HEADERS = ("Date", "Open", "High", "Low", "Close", "Shares Traded", "Turnover (₹ Cr)")
_LOCAL_TZ = ZoneInfo("Asia/Kolkata")
_MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SpotDailyRow:
    session_date: date
    open: float
    high: float
    low: float
    close: float
    index_aggregate_shares_traded: int
    turnover_crore: float


@dataclass(frozen=True, slots=True)
class NiftySpotDailyDataset:
    rows: tuple[SpotDailyRow, ...]
    canonical_candles: tuple[CanonicalCandle, ...]
    input_sha256: str
    input_order: str
    earliest_date: date
    latest_date: date
    raw_row_count: int
    explicitly_declared_weekend_sessions: tuple[date, ...]
    missing_weekdays_without_official_calendar: int
    source_provenance_authenticated: bool = False
    option_chain_coverage_verified: bool = False
    futures_contract_coverage_verified: bool = False
    strategy_promotion_allowed: bool = False
    live_orders_transmitted: int = 0


def _price(value: str, column: str, line: int, *, allow_zero: bool = False) -> float:
    try:
        if not isinstance(value, str) or not value.strip():
            raise ValueError
        out = float(value)
    except (ValueError, TypeError) as exc:
        raise NiftySpotDailyImportError(f"Row {line}: invalid {column}") from exc
    if not math.isfinite(out) or (out < 0 if allow_zero else out <= 0):
        raise NiftySpotDailyImportError(f"Row {line}: nonfinite or negative/zero {column}")
    return out


def _shares(value: str, line: int) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"\d+", value.strip()):
        raise NiftySpotDailyImportError(f"Row {line}: Shares Traded must be a non-negative integer")
    return int(value)


def import_nifty_spot_daily_csv(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    declared_weekend_sessions: frozenset[date] = frozenset(),
    max_rows: int = 5000,
) -> NiftySpotDailyDataset:
    """Validate complete NSE-style CSV, reverse newest-first to canonical order.

    Each OHLC bar is **indexed by its session date** and represented as
    15:30 Asia/Kolkata ISO time solely for the daily research time axis;
    15:30 is not an independently verified actual market closing timestamp.
    The 'volume' field is the index's aggregate *shares traded* activity
    proxy and must never be interpreted as futures/options contract volume.
    """
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or not 2 <= max_rows <= 50000:
        raise NiftySpotDailyImportError("max_rows must be an integer in [2, 50000]")
    if not isinstance(declared_weekend_sessions, frozenset) or any(
        not isinstance(day, date) or isinstance(day, datetime) for day in declared_weekend_sessions
    ):
        raise NiftySpotDailyImportError("declared_weekend_sessions must be frozenset of dates")
    if expected_sha256 is not None and (
        not isinstance(expected_sha256, str) or not re.fullmatch("[A-Fa-f0-9]{64}", expected_sha256)
    ):
        raise NiftySpotDailyImportError("expected_sha256 must be a 64-character hexadecimal digest")
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise NiftySpotDailyImportError("Source must be an existing regular non-symlink CSV file")
    size = source.stat().st_size
    if size == 0 or size > _MAX_FILE_BYTES:
        raise NiftySpotDailyImportError("Source exceeds 2 MiB bound or is empty")
    raw = source.read_bytes()
    if len(raw) > _MAX_FILE_BYTES:
        raise NiftySpotDailyImportError("Source exceeds 2 MiB bound")
    actual_hash = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and actual_hash != expected_sha256.lower():
        raise NiftySpotDailyImportError("Source SHA-256 checksum mismatch")
    try:
        reader = csv.DictReader(
            io.StringIO(raw.decode("utf-8-sig"), newline=""),
            restkey="__EXTRA__", restval=None,
        )
        if reader.fieldnames is None:
            raise NiftySpotDailyImportError("CSV header missing")
        fields = [name.strip() for name in reader.fieldnames]
        if len(fields) != len(HEADERS) or set(fields) != set(HEADERS):
            raise NiftySpotDailyImportError("NIFTY daily CSV must have exactly seven unique expected headers")
        parsed: list[SpotDailyRow] = []
        dates_seen: set[date] = set()
        for line, values in enumerate(reader, start=2):
            if line - 1 > max_rows:
                raise NiftySpotDailyImportError("Source exceeds max_rows")
            if "__EXTRA__" in values:
                raise NiftySpotDailyImportError(f"Row {line}: extra CSV columns")
            row = {key.strip(): (value.strip() if isinstance(value, str) else None)
                   for key, value in values.items()}
            if any(row.get(key) is None for key in HEADERS):
                raise NiftySpotDailyImportError(f"Row {line}: missing CSV column value")
            text_date = row["Date"]
            if not isinstance(text_date, str) or not re.fullmatch(
                r"\d{2}-[A-Za-z]{3}-\d{4}", text_date
            ):
                raise NiftySpotDailyImportError(f"Row {line}: expected DD-MON-YYYY date")
            try:
                day = datetime.strptime(text_date.upper(), "%d-%b-%Y").date()
            except ValueError as exc:
                raise NiftySpotDailyImportError(f"Row {line}: invalid session date") from exc
            if day in dates_seen:
                raise NiftySpotDailyImportError(f"Row {line}: duplicate daily session date")
            dates_seen.add(day)
            if day.weekday() >= 5 and day not in declared_weekend_sessions:
                raise NiftySpotDailyImportError(
                    f"Row {line}: weekend session needs explicit operator declaration: {day.isoformat()}"
                )
            o, h, l, c = (_price(row[k], k, line) for k in ("Open", "High", "Low", "Close"))
            shares = _shares(row["Shares Traded"], line)
            turnover = _price(row["Turnover (₹ Cr)"], "Turnover (₹ Cr)", line, allow_zero=True)
            if h < max(o, l, c) or l > min(o, h, c):
                raise NiftySpotDailyImportError(f"Row {line}: invalid OHLC bounds")
            parsed.append(SpotDailyRow(day, o, h, l, c, shares, turnover))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise NiftySpotDailyImportError(f"Cannot decode/parse strict UTF-8 CSV: {exc}") from exc
    if len(parsed) < 2:
        raise NiftySpotDailyImportError("At least two daily price bars required")
    raw_days = [item.session_date for item in parsed]
    if all(a < b for a,b in zip(raw_days, raw_days[1:])):
        chronological = parsed
        input_order = "oldest_first"
    elif all(a > b for a,b in zip(raw_days, raw_days[1:])):
        chronological = parsed[::-1]
        input_order = "newest_first"
    else:
        raise NiftySpotDailyImportError("Dates must be strictly increasing or strictly decreasing")
    first, last = chronological[0].session_date, chronological[-1].session_date
    range_days = (last-first).days
    if range_days > 365 * 30:
        raise NiftySpotDailyImportError("Research history exceeds 30-year span")
    missing_weekdays = 0
    declared_days = set(raw_days)
    for offset in range(range_days + 1):
        day = first + timedelta(days=offset)
        if day.weekday() < 5 and day not in declared_days:
            missing_weekdays += 1
    candles = tuple(
        CanonicalCandle(
            timestamp=datetime.combine(row.session_date, time(15, 30), tzinfo=_LOCAL_TZ).isoformat(),
            open=row.open, high=row.high, low=row.low, close=row.close,
            volume=float(row.index_aggregate_shares_traded), symbol="NIFTY",
            interval="1d",
        ) for row in chronological
    )
    return NiftySpotDailyDataset(
        rows=tuple(chronological), canonical_candles=candles,
        input_sha256=actual_hash, input_order=input_order, earliest_date=first,
        latest_date=last, raw_row_count=len(parsed),
        explicitly_declared_weekend_sessions=tuple(sorted(
            day for day in declared_weekend_sessions if day in declared_days
        )),
        missing_weekdays_without_official_calendar=missing_weekdays,
    )

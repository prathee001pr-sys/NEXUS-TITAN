"""Dependency-free helpers for validating historical OHLCV CSV files."""
from __future__ import annotations
import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class ValidationReport:
    rows_checked: int
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_ohlcv_csv(path: str | Path) -> ValidationReport:
    file_path = Path(path)
    errors: list[str] = []
    rows_checked = 0
    seen_timestamps: set[datetime] = set()
    previous_timestamp: datetime | None = None
    try:
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = tuple((name or "").strip().lower() for name in (reader.fieldnames or ()))
            missing = [column for column in REQUIRED_COLUMNS if column not in headers]
            if missing:
                return ValidationReport(0, (f"Missing required columns: {', '.join(missing)}",))
            for row_number, raw_row in enumerate(reader, start=2):
                rows_checked += 1
                row = {(key or "").strip().lower(): value for key, value in raw_row.items() if key is not None}
                try:
                    timestamp = datetime.fromisoformat((row.get("timestamp") or "").strip())
                except ValueError:
                    errors.append(f"Row {row_number}: timestamp must be ISO-8601.")
                    continue
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                else:
                    timestamp = timestamp.astimezone(timezone.utc)
                if timestamp in seen_timestamps:
                    errors.append(f"Row {row_number}: duplicate timestamp.")
                    continue
                if previous_timestamp is not None and timestamp <= previous_timestamp:
                    errors.append(f"Row {row_number}: timestamps must be strictly increasing.")
                    continue
                seen_timestamps.add(timestamp)
                previous_timestamp = timestamp
                try:
                    values = [float(row[name]) for name in ("open", "high", "low", "close", "volume")]
                except (ValueError, TypeError, KeyError):
                    errors.append(f"Row {row_number}: OHLCV values must be numeric.")
                    continue
                if not all(math.isfinite(value) for value in values):
                    errors.append(f"Row {row_number}: OHLCV values must be finite numbers.")
                    continue
                open_price, high, low, close, volume = values
                if min(open_price, high, low, close) <= 0:
                    errors.append(f"Row {row_number}: prices must be greater than zero.")
                if volume < 0:
                    errors.append(f"Row {row_number}: volume cannot be negative.")
                if high < max(open_price, low, close):
                    errors.append(f"Row {row_number}: high must be >= open, low, and close.")
                if low > min(open_price, high, close):
                    errors.append(f"Row {row_number}: low must be <= open, high, and close.")
    except OSError as exc:
        return ValidationReport(0, (f"Could not read file: {exc}",))
    if rows_checked == 0 and not errors:
        errors.append("CSV contains no data rows.")
    return ValidationReport(rows_checked, tuple(errors))

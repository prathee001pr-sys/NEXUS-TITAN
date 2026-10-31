"""Strict CSV reader for historical OHLCV candles."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import TextIO

from nexus_titan.data.ohlcv import OHLCVCandle


_REQUIRED_COLUMNS = (
    "symbol", "timeframe", "timestamp", "open", "high",
    "low", "close", "volume",
)


class CSVImportError(ValueError):
    """Raised when a historical OHLCV CSV file is malformed."""


def load_ohlcv_csv(
    file: str | Path | TextIO,
    *,
    source: str,
) -> tuple[OHLCVCandle, ...]:
    """Read rows with the required header and return validated candles.

    Timestamps must be ISO-8601 and include a UTC offset. A source label is
    supplied by the caller rather than trusted from the CSV file.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be a non-empty string")
    owns_file = not hasattr(file, "read")
    handle = Path(file).open("r", encoding="utf-8-sig", newline="") if owns_file else file
    try:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise CSVImportError("CSV is empty or has no header")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise CSVImportError("CSV header contains duplicate column names")
        missing = [name for name in _REQUIRED_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise CSVImportError(f"CSV is missing required columns: {', '.join(missing)}")
        candles: list[OHLCVCandle] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise CSVImportError(f"malformed CSV row at line {line_number}")
            try:
                timestamp_text = row["timestamp"].strip()
                timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
                candle = OHLCVCandle(
                    symbol=row["symbol"].strip(),
                    timeframe=row["timeframe"].strip(),
                    timestamp=timestamp,
                    open=row["open"].strip(),
                    high=row["high"].strip(),
                    low=row["low"].strip(),
                    close=row["close"].strip(),
                    volume=row["volume"].strip(),
                    source=source,
                )
            except (ValueError, TypeError, KeyError) as exc:
                raise CSVImportError(f"invalid candle at line {line_number}: {exc}") from exc
            candles.append(candle)
        return tuple(candles)
    finally:
        if owns_file:
            handle.close()

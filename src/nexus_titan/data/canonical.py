"""Canonical market data schema, strict validation, and quality assessment for NEXUS-TITAN."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class CanonicalCandle:
    """Unified internal representation of an OHLCV market candle."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = "UNKNOWN"
    interval: str = "1d"

    @property
    def datetime(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)

    def to_dict(self) -> dict[str, float | str]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "symbol": self.symbol,
            "interval": self.interval,
        }


@dataclass(frozen=True)
class DataQualityReport:
    """Detailed data quality audit report required by Blueprint P2."""
    total_rows_checked: int
    valid_candles_count: int
    missing_columns: tuple[str, ...] = ()
    duplicate_timestamps: int = 0
    out_of_order_timestamps: int = 0
    impossible_ohlc_errors: int = 0
    non_positive_price_errors: int = 0
    negative_volume_errors: int = 0
    non_finite_values_errors: int = 0
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.valid_candles_count > 0 and len(self.errors) == 0


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def load_canonical_data(
    path: str | Path,
    symbol: str = "NIFTY",
    interval: str = "1d",
) -> tuple[tuple[CanonicalCandle, ...], DataQualityReport]:
    """Load, validate, and audit market data candles from CSV with strict data-quality checks."""
    file_path = Path(path)
    if not file_path.exists():
        report = DataQualityReport(
            total_rows_checked=0,
            valid_candles_count=0,
            errors=(f"File not found: {file_path}",),
        )
        return (), report

    candles: list[CanonicalCandle] = []
    errors: list[str] = []
    seen_timestamps: set[datetime] = set()
    prev_timestamp: datetime | None = None

    duplicate_count = 0
    out_of_order_count = 0
    impossible_ohlc_count = 0
    non_positive_price_count = 0
    negative_volume_count = 0
    non_finite_count = 0
    total_checked = 0

    try:
        with file_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                report = DataQualityReport(
                    total_rows_checked=0,
                    valid_candles_count=0,
                    errors=("CSV file is completely empty or headerless.",),
                )
                return (), report

            headers = {name.strip().lower() for name in reader.fieldnames if name}
            missing = [c for c in REQUIRED_COLUMNS if c not in headers]
            if missing:
                report = DataQualityReport(
                    total_rows_checked=0,
                    valid_candles_count=0,
                    missing_columns=tuple(missing),
                    errors=(f"Missing required columns: {', '.join(missing)}",),
                )
                return (), report

            for row_num, row in enumerate(reader, start=2):
                total_checked += 1
                clean = {
                    (k.strip().lower() if k else ""): (v.strip() if v else "")
                    for k, v in row.items()
                    if k is not None
                }

                raw_ts = clean.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    else:
                        ts = ts.astimezone(timezone.utc)
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid ISO-8601 timestamp '{raw_ts}'")
                    continue

                if ts in seen_timestamps:
                    duplicate_count += 1
                    errors.append(f"Row {row_num}: Duplicate timestamp '{raw_ts}'")
                    continue

                if prev_timestamp is not None and ts <= prev_timestamp:
                    out_of_order_count += 1
                    errors.append(f"Row {row_num}: Timestamps must be strictly increasing")
                    continue

                seen_timestamps.add(ts)
                prev_timestamp = ts

                try:
                    o = float(clean["open"])
                    h = float(clean["high"])
                    l = float(clean["low"])
                    c = float(clean["close"])
                    v = float(clean["volume"])
                except (ValueError, KeyError, TypeError) as exc:
                    errors.append(f"Row {row_num}: Invalid numeric OHLCV values: {exc}")
                    continue

                vals = (o, h, l, c, v)
                if not all(math.isfinite(x) for x in vals):
                    non_finite_count += 1
                    errors.append(f"Row {row_num}: Non-finite numeric value detected")
                    continue
                if min(o, h, l, c) <= 0:
                    non_positive_price_count += 1
                    errors.append(f"Row {row_num}: Prices must be strictly positive")
                    continue
                if v < 0:
                    negative_volume_count += 1
                    errors.append(f"Row {row_num}: Volume cannot be negative")
                    continue
                if h < max(o, l, c) or l > min(o, h, c):
                    impossible_ohlc_count += 1
                    errors.append(f"Row {row_num}: Impossible OHLC bar (High/Low out of bounds)")
                    continue

                candles.append(CanonicalCandle(
                    timestamp=ts.isoformat(), open=o, high=h, low=l,
                    close=c, volume=v, symbol=symbol.upper(), interval=interval,
                ))

    except OSError as exc:
        return (), DataQualityReport(
            total_rows_checked=0, valid_candles_count=0,
            errors=(f"I/O error reading market data: {exc}",),
        )

    if total_checked == 0 and not errors:
        errors.append("CSV contains no market data rows.")

    report = DataQualityReport(
        total_rows_checked=total_checked,
        valid_candles_count=len(candles),
        duplicate_timestamps=duplicate_count,
        out_of_order_timestamps=out_of_order_count,
        impossible_ohlc_errors=impossible_ohlc_count,
        non_positive_price_errors=non_positive_price_count,
        negative_volume_errors=negative_volume_count,
        non_finite_values_errors=non_finite_count,
        errors=tuple(errors),
    )
    return tuple(candles), report

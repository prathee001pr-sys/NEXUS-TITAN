"""Deterministic OHLCV batch quality checks; no network or market-calendar logic."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle


_TIMEFRAME = re.compile(r"^(\d+)(m|h|d)$")


def timeframe_duration(timeframe: str) -> timedelta:
    """Convert supported minute/hour/day intervals to a fixed duration."""
    match = _TIMEFRAME.fullmatch(timeframe)
    if match is None:
        raise ValueError("unsupported timeframe; use values such as 1m, 5m, 1h or 1d")
    amount = int(match.group(1))
    if amount <= 0:
        raise ValueError("timeframe amount must be greater than zero")
    unit = match.group(2)
    return timedelta(minutes=amount) if unit == "m" else (
        timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
    )


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    """Findings for a supplied candle batch; findings never modify input data."""

    candle_count: int
    duplicate_timestamps: tuple[datetime, ...]
    out_of_order_pairs: tuple[tuple[int, int], ...]
    missing_intervals: tuple[tuple[datetime, datetime], ...]
    outside_query: tuple[datetime, ...]
    identity_mismatches: tuple[int, ...]

    @property
    def is_valid(self) -> bool:
        return not any((
            self.duplicate_timestamps,
            self.out_of_order_pairs,
            self.missing_intervals,
            self.outside_query,
            self.identity_mismatches,
        ))


def inspect_candle_batch(
    candles: tuple[OHLCVCandle, ...] | list[OHLCVCandle],
    query: CandleQuery,
) -> DataQualityReport:
    """Inspect order, duplicates, gaps and query identity/bounds.

    Gap detection assumes continuous fixed-duration intervals. Exchange session
    calendars, holidays and trading breaks must be applied by a later calendar-
    aware layer; this function intentionally does not guess market sessions.
    """
    expected = timeframe_duration(query.timeframe)
    duplicates: list[datetime] = []
    seen: set[datetime] = set()
    out_of_order: list[tuple[int, int]] = []
    gaps: list[tuple[datetime, datetime]] = []
    outside: list[datetime] = []
    mismatches: list[int] = []

    previous: tuple[int, OHLCVCandle] | None = None
    for index, item in enumerate(candles):
        if item.symbol != query.symbol or item.timeframe != query.timeframe:
            mismatches.append(index)
        if item.timestamp < query.start or item.timestamp >= query.end:
            outside.append(item.timestamp)
        if item.timestamp in seen and item.timestamp not in duplicates:
            duplicates.append(item.timestamp)
        seen.add(item.timestamp)

        if previous is not None:
            previous_index, previous_item = previous
            if item.timestamp < previous_item.timestamp:
                out_of_order.append((previous_index, index))
            elif item.timestamp > previous_item.timestamp:
                delta = item.timestamp - previous_item.timestamp
                if delta > expected:
                    gaps.append((previous_item.timestamp + expected, item.timestamp))
        previous = (index, item)

    return DataQualityReport(
        candle_count=len(candles),
        duplicate_timestamps=tuple(duplicates),
        out_of_order_pairs=tuple(out_of_order),
        missing_intervals=tuple(gaps),
        outside_query=tuple(outside),
        identity_mismatches=tuple(mismatches),
    )
